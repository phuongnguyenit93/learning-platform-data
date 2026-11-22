# Cấu hình profile, tài khoản, URL, TLS và timeout

> **Chương:** Spring Boot  
> **Học phần:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — Apache ActiveMQ Classic và Artemis trong giao tiếp bất đồng bộ với queue, topic, routing và JMS; thực hành producer/consumer Java, acknowledgment, transaction, redelivery, DLQ, bảo mật và vận hành broker đáng tin cậy.  
> **Trọng tâm:** Tổ chức cấu hình Spring Boot theo `local`, `staging`, `prod`, quản lý credential, lựa chọn broker URL, kết nối TLS và xác định đúng phạm vi của từng timeout. Ví dụ dùng **Spring Boot 3.4.5, Java 17, Jakarta JMS và Artemis native client**. Những khác biệt với ActiveMQ Classic được nêu riêng, không trộn hai họ client.

## 1. Bài toán: cùng một worker nhưng ba môi trường khác nhau

Dịch vụ `shipping-worker` tiêu thụ queue `shipping.commands`. Trong máy lập trình, Artemis chạy ở `127.0.0.1:61616`. Ở staging, broker chạy trong mạng riêng và có TLS. Ở production, hệ thống yêu cầu chứng chỉ hợp lệ, tài khoản chuyên dụng, timeout và retry được kiểm soát.

Những sai lầm thực tế:

- Ứng dụng production vô tình kết nối `localhost` vì một cấu hình mặc định từ file chung.
- Mật khẩu broker được commit vào Git hoặc in ra log khi bật debug.
- Client bật TLS nhưng chứng chỉ server có SAN không khớp hostname; developer tắt xác thực chứng chỉ để “sửa nhanh”.
- Đặt `spring.jms.template.receive-timeout=3s` rồi tưởng mọi callback của `@JmsListener` sẽ bị ngắt sau ba giây.
- Producer nhận timeout ở lệnh gửi rồi retry bằng ID mới, trong khi broker có thể đã nhận message trước khi phản hồi bị mất.
- Ứng dụng tăng số reconnect attempts nhưng tưởng mình đã thiết lập HA, dù broker chỉ có một node.

Cần phân biệt **bốn lớp**:

~~~mermaid
flowchart LR
  P["Spring profiles & configuration sources"] --> C["ConnectionFactory / Artemis native client"]
  C --> N["Netty TCP/TLS + authentication"]
  N --> B["Artemis acceptor CORE + authorization"]
  C --> J["Spring JMS template / listener container"]
  J --> W["Nghiệp vụ + database"]
  B --> Q["Address / queue / redelivery"]
~~~

Profile quyết định **đưa thông số nào vào ứng dụng**; client quyết định **kết nối thế nào**; broker quyết định **chấp nhận và phân quyền thế nào**; listener quyết định **ACK và xử lý nghiệp vụ thế nào**. Một thuộc tính của lớp này không tự thay thế thuộc tính lớp khác.

## 2. Chọn đúng Spring Boot starter và JMS namespace

Với Artemis native JMS và Spring Boot 3.x, dùng starter Artemis do Boot quản lý dependency:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.4.5</version>
    <relativePath/>
  </parent>
  <groupId>lab</groupId>
  <artifactId>shipping-worker</artifactId>
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

Spring Boot BOM quản lý phiên bản Artemis JMS client tương ứng; không thêm tùy ý một bản `artemis-jakarta-client` khác và cho rằng chắc chắn tương thích. Mốc phiên bản minh họa trên **không** phải tuyên bố “mới nhất”; khi nâng cấp cần kiểm thử khả năng tương thích client/broker, TLS và reconnect.

**Phân biệt:**

| Chủ đề | Artemis native | ActiveMQ Classic |
|---|---|---|
| Spring Boot starter | `spring-boot-starter-artemis` | `spring-boot-starter-activemq` tương ứng bản Boot/client |
| Property nhóm kết nối | `spring.artemis.*` | `spring.activemq.*` |
| Client wire protocol điển hình | Artemis **Core** | Classic **OpenWire** |
| API JMS trong Boot 3 | `jakarta.jms` | Phải chọn Classic client tương thích **Jakarta**; Classic 5.x cũ có `javax.jms` |
| TLS và URL option | Netty transport option Artemis | Tùy chọn transport riêng của Classic/OpenWire |

**Port 61616 không quyết định protocol.** Artemis broker có thể mở acceptor đa giao thức, nhưng nếu code dùng Artemis native client thì acceptor phải chấp nhận **CORE**. Không thay client Classic bằng Artemis chỉ bằng cách đổi URL.

## 3. Thiết kế cấu hình profile: chung, local, staging, prod

Tổ chức tập tin:

~~~text
src/main/resources/
  application.yml
  application-local.yml
  application-staging.yml
  application-prod.yml
~~~

Profile là công cụ chọn **nguồn cấu hình**, không phải cơ chế bảo mật. Một file riêng vẫn không an toàn nếu commit mật khẩu thật.

### 3.1. Cấu hình chung: `application.yml`

~~~yaml
spring:
  application:
    name: shipping-worker
  artemis:
    mode: native
    user: "${ARTEMIS_USER}"
    password: "${ARTEMIS_PASSWORD}"
  jms:
    listener:
      auto-startup: true
      concurrency: 1
      max-concurrency: 3
    template:
      receive-timeout: 3s

app:
  jms:
    shipping-queue: shipping.commands
~~~

- `spring.artemis.mode=native` nói rõ ứng dụng sẽ kết nối **broker ngoài tiến trình**, không dựa vào embedded server khi classpath/môi trường thay đổi.
- User/password là **credential broker**, được lấy từ nguồn ngoài qua placeholder. Không có default như `admin/admin`.
- Không đặt broker URL mặc định ở file chung; mỗi profile cung cấp endpoint rõ ràng.
- `spring.jms.listener.concurrency` và `max-concurrency` áp dụng cho Spring JMS listener container khi được cấu hình qua Boot hoặc Boot configurer; đây là số consumer, **không** phải số broker hay số connection HA.
- `spring.jms.template.receive-timeout` chỉ ảnh hưởng thao tác **receive đồng bộ** bằng `JmsTemplate`, không trực tiếp quy định thời gian callback `@JmsListener`.

### 3.2. Profile `local`

`application-local.yml`:

~~~yaml
spring:
  artemis:
    broker-url: "tcp://127.0.0.1:61616"
  jms:
    listener:
      concurrency: 1
      max-concurrency: 1
~~~

Điều kiện: broker Artemis local thực sự lắng nghe endpoint đó. Nếu worker chạy **trong Docker container**, `127.0.0.1` chỉ chính container worker; hãy dùng DNS của service broker, không dùng loopback của host theo thói quen.

### 3.3. Profile `staging`

`application-staging.yml`:

~~~yaml
spring:
  artemis:
    broker-url: "${ARTEMIS_STAGING_URL}"
  jms:
    listener:
      concurrency: 1
      max-concurrency: 2
~~~

Staging nên mô phỏng **TLS, DNS và quyền truy cập** của production thay vì luôn chạy plaintext. Biến `ARTEMIS_STAGING_URL` được cấp khi triển khai; nếu thiếu, không fallback sang local.

### 3.4. Profile `prod` có TLS

`application-prod.yml`:

~~~yaml
spring:
  artemis:
    broker-url: "tcp://${ARTEMIS_HOST}:${ARTEMIS_PORT:61617}?sslEnabled=true;trustStorePath=${ARTEMIS_TRUSTSTORE_PATH};trustStorePassword=${ARTEMIS_TRUSTSTORE_PASSWORD};trustStoreType=PKCS12;verifyHost=true"
  jms:
    listener:
      concurrency: 2
      max-concurrency: 6
~~~

Giải thích từng phần:

- `ARTEMIS_HOST` phải là DNS hostname thật của broker và **khớp SAN** trên chứng chỉ server.
- Cổng **61617** chỉ là ví dụ về **acceptor TLS**; broker thực tế phải được cấu hình đúng port.
- `sslEnabled=true` kích hoạt TLS của Artemis Netty connector.
- `trustStorePath` và `trustStorePassword` cấu hình vật liệu tin cậy của client, không phải mật khẩu đăng nhập broker.
- `verifyHost=true` yêu cầu xác minh server hostname; không tắt trong production.
- Không có default cho hostname/truststore/mật khẩu; thiếu secret phải được coi là lỗi triển khai.

**Lưu ý bảo mật:** URI chứa `trustStorePassword`, dù giá trị đến từ environment variable, **vẫn có thể lộ** khi log resolved URL, crash dump, actuator config hoặc diagnostics. Với yêu cầu bảo mật cao, nên đưa secret vào **native transport configuration** hoặc cơ chế secret/SSL configuration do đội vận hành quản lý, không in connection URL đã nội suy. Ví dụ URI giúp hiểu mapping, **không phải** cách tốt nhất để truyền secret trong mọi production.

### 3.5. Kích hoạt profile và xác định nguồn override

Trên PowerShell, phát triển local:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:ARTEMIS_USER = "lab"
$env:ARTEMIS_PASSWORD = "mat-khau-cua-broker-lab"
mvn spring-boot:run
~~~

Production cấp `SPRING_PROFILES_ACTIVE=prod` và các biến host/truststore/credential từ secret manager hoặc deployment configuration, không lấy credential development.

Spring Boot có nhiều property source. **Command-line argument, environment variable, profile-specific YAML và base YAML có thứ tự precedence**; trong các trường hợp thông dụng, command-line/env có thể override file. Chẳng hạn `SPRING_ARTEMIS_BROKER_URL` có thể thay giá trị trong profile. Vì vậy:

1. Xác minh profile đang active.
2. Xác minh **nguồn cấu hình cuối cùng** của URL/user nhưng không in password.
3. Rà biến môi trường cũ còn trong deployment.
4. Không bật `local` và `prod` đồng thời trừ khi có quy tắc override rõ và đã kiểm chứng.

`ARTEMIS_USER` là biến **tự chọn tên** được Spring resolve bằng placeholder; `SPRING_ARTEMIS_USER` là tên relaxed binding trực tiếp vào property `spring.artemis.user`. Nếu cả hai có mặt, cần hiểu precedence thực tế, không nhìn một file YAML rồi kết luận ứng dụng đang dùng một giá trị nhất định.

## 4. URL, transport và xác thực: chẩn đoán từ dưới lên

Một connection đi qua các lớp:

~~~text
Spring Boot ConnectionFactory
          |
          v
DNS / TCP socket / firewall / container networking
          |
          v
TLS handshake và xác thực chứng chỉ broker (nếu bật)
          |
          v
Artemis acceptor cho phép CORE protocol
          |
          v
Broker authentication (user/password)
          |
          v
Broker authorization (send/consume/create queue...)
          |
          v
Address/queue routing
~~~

| Triệu chứng | Kiểm tra lớp nào trước? |
|---|---|
| `Connection refused` | Port listener, Docker/Kubernetes mapping, firewall |
| DNS không resolve | Hostname/service discovery, DNS search domain |
| TLS handshake failed | Chứng chỉ, CA, truststore, TLS version/cipher |
| Hostname mismatch | SAN certificate so với host của URL |
| Kết nối TCP được nhưng protocol handshake lỗi | Acceptor có `CORE` không; client đúng dòng Artemis? |
| Authentication failed | `spring.artemis.user/password` và broker user store |
| Authorization denied | Role và `security-setting` trên đúng address/queue |
| Listener kết nối nhưng queue luôn rỗng | Routing, destination, selector, scheduled/expiry, không vội đổi timeout |

**Không sửa lỗi TLS bằng cách tăng receive timeout**, và không sửa lỗi authorization bằng cách bật quyền admin toàn cục.

### 4.1. Broker credential khác secret TLS

| Secret/tài nguyên | Chức năng |
|---|---|
| `ARTEMIS_USER` / `ARTEMIS_PASSWORD` | Danh tính đăng nhập broker |
| Client truststore | Tin CA/certificate server để xác thực broker |
| Truststore password | Mở truststore nếu định dạng/cấu hình yêu cầu |
| Broker keystore | Chứng chỉ + private key broker cung cấp cho TLS |
| Client keystore khi mTLS | Chứng chỉ + private key do client xuất trình |
| Broker roles | Quyền `send`, `consume`, `browse` và tạo destination |

TLS bảo vệ kết nối và xác thực server; broker authentication/authorization vẫn là lớp riêng. **TLS thành công không có nghĩa user có quyền consume.**

### 4.2. Quyền tối thiểu ở broker

Trích đoạn XML trong phần `security-settings` của Artemis `broker.xml` khi các role đã được khai báo đúng:

~~~xml
<security-setting match="shipping.#">
    <permission type="send" roles="shipping-producer"/>
    <permission type="consume" roles="shipping-consumer"/>
</security-setting>
~~~

Nếu service chỉ tiêu thụ, cấp role consume; nếu vừa phát vừa nhận, cấp các role cần thiết. Hợp nhất với rule hiện có; không tạo nhiều rule trùng/đè mâu thuẫn. Không dùng tài khoản quản trị broker cho tất cả service.

## 5. TLS phía broker và client phải đồng bộ

### 5.1. Artemis acceptor CORE dùng TLS

Trong phần `acceptors` **hiện hữu** của Artemis `broker.xml`, ví dụ một acceptor riêng:

~~~xml
<!-- Ví dụ cấu trúc: KHÔNG để REPLACE_ME trong production. -->
<acceptor name="core-tls">
    tcp://0.0.0.0:61617?protocols=CORE;sslEnabled=true;keyStorePath=/run/secrets/broker.p12;keyStorePassword=REPLACE_ME;keyStoreType=PKCS12;needClientAuth=false
</acceptor>
~~~

- `protocols=CORE`: Artemis JMS native client dùng Core wire protocol.
- `sslEnabled=true`: bật TLS tại acceptor.
- `keyStorePath`: chứa private key và chứng chỉ server.
- `needClientAuth=false`: **server-authenticated TLS**, client không bắt buộc xuất trình cert của riêng mình; broker vẫn yêu cầu user/password theo auth settings.
- `0.0.0.0`: listener bind các interface trong môi trường broker. Cần bảo vệ bằng firewall/network policy; **không tự public port lên Internet**.

Đoạn XML chỉ minh họa cấu hình; mật khẩu sản xuất cần xử lý bằng secret/password masking cơ chế của version broker, không lưu plaintext vào repo. Với mTLS, broker bật yêu cầu client cert và truststore phù hợp, client bổ sung keystore/certificate. **Không gọi server-auth TLS là mTLS.**

### 5.2. Xác minh SAN và truststore

Giả sử URL là `tcp://mq.internal.example:61617` và certificate có DNS SAN `mq.internal.example`: hostname verification có cơ sở thành công.

Nếu URL dùng IP `10.10.4.8` nhưng certificate chỉ có DNS SAN `mq.internal.example`, xác minh hostname **có thể thất bại** dù CA được tin cậy. Sửa URL/DNS hoặc phát hành cert SAN đúng, **không** tắt `verifyHost`.

Không dùng `trustAll=true`, `verifyHost=false`, “accept all certificates” hoặc truststore vô hiệu trong production. Khi certificate rotation, chuẩn bị **giai đoạn overlap trust**, kiểm thử staging và kế hoạch restart/reload ConnectionFactory nếu client không tự đọc lại truststore.

### 5.3. Không log chuỗi URL đã chứa secret

Khi khởi động app, có thể log:

~~~text
profile=prod brokerHost=mq.internal.example brokerPort=61617
tlsEnabled=true jmsListenerContainers=1
~~~

Không log:

~~~text
spring.artemis.broker-url=<full URL with trustStorePassword>
spring.artemis.password=<secret>
~~~

Hạn chế truy cập `/actuator/env`, `/actuator/configprops` và debug log; yêu cầu sanitization, authentication và phân quyền. Không dùng command-line args với mật khẩu thực khi có cơ chế secret quản lý phù hợp vì chúng có thể xuất hiện trong process listing, lịch sử lệnh hoặc telemetry.

## 6. Timeout: một tên gọi nhưng nhiều ranh giới khác nhau

Bảng sau là phần quan trọng nhất khi vận hành:

| Deadline/cơ chế | Thuộc API hoặc property | Nó giới hạn điều gì? | Không giới hạn điều gì? |
|---|---|---|---|
| **TCP connect / TLS handshake** | Artemis Netty transport-specific options | Thiết lập socket và TLS theo transport | Thời gian xử lý JMS message |
| **Broker call timeout** | `ActiveMQConnectionFactory.setCallTimeout(...)` | Chờ phản hồi của một số thao tác đồng bộ phía client/provider | Không chứng minh consumer xử lý xong |
| **Connection liveness** | `clientFailureCheckPeriod`, `connectionTTL` và broker policy | Phát hiện kết nối không còn hoạt động | Callback nghiệp vụ dài bao lâu |
| **Native reconnect** | `retryInterval`, `reconnectAttempts` | Khoảng cách/số lần client thử khôi phục | Không tự sinh broker HA |
| **Spring JMS listener receive polling** | `DefaultJmsListenerContainerFactory.setReceiveTimeout(...)` | Thời gian chờ một vòng receive nội bộ container | Không giết callback đang xử lý |
| **Spring JMS listener recovery** | `setRecoveryInterval(...)` | Nhịp container thử phục hồi khi lỗi | Không sửa sai mật khẩu/protocol |
| **JmsTemplate sync receive** | `spring.jms.template.receive-timeout` | Thời gian một lệnh `JmsTemplate.receive(...)` chờ message | Không áp dụng cho `@JmsListener` |
| **Message TTL** | JMS time-to-live / broker expiry | Thời hạn tồn tại của message | Không phải timeout producer send |
| **HTTP/DB timeout** | HTTP client, JDBC driver, DB transaction | Deadline nghiệp vụ/downstream | Không tự chốt JMS ACK khi không có xử lý lỗi |

### 6.1. Ví dụ hai lỗi đặt sai timeout

**Lỗi A — nghĩ 3 giây là thời gian tối đa của listener.** `spring.jms.template.receive-timeout: 3s` chỉ dùng cho `JmsTemplate.receive`. Nếu `@JmsListener` gọi HTTP mất 90 giây mà HTTP client không đặt deadline, callback vẫn có thể kẹt; phải cấu hình timeout cho HTTP/DB và cách xử lý exception/rollback.

**Lỗi B — coi timeout send là message chắc chắn không tới broker.** Nếu broker nhận/commit nhưng phản hồi bị mất do network, client có thể báo timeout. Producer retry có thể gửi trùng. Dùng **eventId ổn định, transactional outbox khi có DB write, idempotent consumer** để xử lý kết quả không chắc chắn.

### 6.2. Recovery không tương đương HA

`setRetryInterval(2_000)` và `setReconnectAttempts(10)` giúp client thử lại; nếu broker chỉ có một node đang hỏng, những giá trị này không tạo server dự phòng. Broker HA yêu cầu topology, backup/replication hoặc shared-store, và client biết các endpoint/failover topology phù hợp.

`connectionTTL`, `clientFailureCheckPeriod` cũng không phải timeout business transaction. Đặt TTL quá ngắn có thể gây false disconnect khi GC pause hoặc mạng trễ; cân chỉnh bằng latency thực và kiểm thử failover, không tùy tiện giảm xuống vài trăm mili giây.

## 7. Hai cách cấu hình Artemis ConnectionFactory

### 7.1. Phương án A — Spring Boot auto-configuration

Nếu chỉ cần URL, user, password và listener/template properties, dùng `spring.artemis.*` + `spring.jms.*` từ profile như mục 3. Đây là lựa chọn đơn giản, tránh tự tạo bean và bỏ lỡ customizations mặc định.

Spring Boot tự cung cấp bean JMS cần thiết khi classpath và configuration thỏa điều kiện. Việc dùng `spring.jms.listener.concurrency`, `max-concurrency` phụ thuộc listener container được Boot tạo/configurer áp dụng.

### 7.2. Phương án B — native ConnectionFactory cho call timeout/retry

Nếu cần kiểm soát **Artemis-specific** API, tạo bean rõ ràng và dùng một nhóm property do ứng dụng sở hữu:

~~~yaml
app:
  artemis-client:
    url: "${ARTEMIS_BROKER_URL}"
    user: "${ARTEMIS_USER}"
    password: "${ARTEMIS_PASSWORD}"
~~~

~~~java
package lab.shipping;

import jakarta.jms.ConnectionFactory;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ArtemisNativeClientConfig {

    @Bean
    public ConnectionFactory connectionFactory(
            @Value("${app.artemis-client.url}") String url,
            @Value("${app.artemis-client.user}") String user,
            @Value("${app.artemis-client.password}") String password) {

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(url, user, password);

        factory.setCallTimeout(15_000L);
        factory.setRetryInterval(2_000L);
        factory.setReconnectAttempts(10);
        return factory;
    }
}
~~~

**Không bật đồng thời hai chiến lược một cách mơ hồ.** Khi tự tạo bean `ConnectionFactory`, Boot auto-configuration có thể back off, nên `spring.artemis.broker-url/user/password` **không mặc nhiên áp lên bean tự tạo**. Nếu dùng phương án B, các property `app.artemis-client.*` là nguồn dữ liệu cho factory. Cần kiểm tra cấu hình caching/pooling và lifecycle khi thay bean mặc định.

`setCallTimeout` là timeout cấp **Artemis client**, không phải JMS-standard timeout và không phải business processing deadline. `setReconnectAttempts(10)` là policy client, không đảm bảo failover sang broker khác. Sau timeout vẫn cần idempotency khi retry.

**TLS không được bỏ qua ở phương án B:** `url` vẫn cần transport SSL/truststore hợp lệ, hoặc cấu hình native TransportConfiguration an toàn. Khi password của truststore không được phép nằm trong URL/log, cần cấp nó qua một secret-aware transport configuration phù hợp.

## 8. Listener: bật transaction và đặt recovery timeout rõ ràng

Bổ sung `@EnableJms` và bean Spring JMS listener factory. Để **giữ các thuộc tính listener từ Spring Boot profile**, dùng `DefaultJmsListenerContainerFactoryConfigurer` trước, sau đó override phần cần thiết:

~~~java
package lab.shipping;

import jakarta.jms.ConnectionFactory;
import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration(proxyBeanMethods = false)
public class JmsListenerConfig {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            DefaultJmsListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        configurer.configure(factory, connectionFactory);

        factory.setSessionTransacted(true);
        factory.setRecoveryInterval(5_000L);
        factory.setReceiveTimeout(1_000L);
        return factory;
    }
}
~~~

**Đọc đúng ý nghĩa:**

- `setSessionTransacted(true)`: listener hoàn tất thành công thì container commit transaction JMS; lỗi phù hợp dẫn đến rollback/redelivery theo provider/broker policy.
- `setRecoveryInterval(5000L)`: nhịp khôi phục listener của Spring; không áp lên producer call.
- `setReceiveTimeout(1000L)`: khoảng chờ receive nội bộ của container, không ngắt business handler sau 1 giây.
- `configurer.configure(...)`: giữ các thiết lập Boot, gồm concurrency được lấy từ profile; setter gọi **sau** configurer có quyền override từng giá trị.
- Nếu muốn thay recovery/receive interval theo profile, thay số hardcode bằng property `app.jms.*` có kiểu và đơn vị rõ ràng.

Ứng dụng Spring Boot:

~~~java
package lab.shipping;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class ShippingApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShippingApplication.class, args);
    }
}
~~~

Listener minh họa:

~~~java
package lab.shipping;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class ShippingListener {

    @JmsListener(
        destination = "${app.jms.shipping-queue}",
        containerFactory = "jmsListenerContainerFactory")
    public void onMessage(String orderId) {
        if (orderId.startsWith("FAIL:")) {
            throw new IllegalStateException("Lỗi nghiệp vụ mô phỏng");
        }
        // Demo chưa ghi DB. Production cần idempotency + DB commit.
        System.out.println("BUSINESS_SIMULATED orderId=" + orderId);
    }
}
~~~

Nếu code **catch exception rồi return bình thường**, container có thể **commit JMS ACK dù nghiệp vụ thất bại**. Không nuốt lỗi chỉ vì muốn giảm log. Với real DB, phải commit thay đổi nghiệp vụ trước khi ACK JMS; crash giữa hai commit có thể gây redelivery, nên consumer phải nhận diện trùng theo eventId.

## 9. Producer Spring JMS và sự khác biệt giữa send, receive, TTL

Sử dụng `JmsTemplate` cho producer:

~~~java
package lab.shipping;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class ShippingPublisher {

    private final JmsTemplate template;
    private final String queue;

    public ShippingPublisher(JmsTemplate template,
            @Value("${app.jms.shipping-queue}") String queue) {
        this.template = template;
        this.queue = queue;
    }

    public void publish(String eventId, String orderId) {
        template.convertAndSend(queue, orderId, message -> {
            message.setStringProperty("eventId", eventId);
            return message;
        });
    }
}
~~~

`convertAndSend` hoàn tất không có nghĩa consumer đã xử lý xong. Đó là một **mốc producer** theo semantics provider/client. Nếu timeout đúng khi broker trả response, kết quả có thể chưa rõ; giữ eventId ổn định để retry và dedup.

`spring.jms.template.receive-timeout` chỉ áp dụng cho việc gọi `template.receive(queue)`/các phương thức receive đồng bộ liên quan; **không phải timeout của `template.convertAndSend`**. Nếu thiết lập JMS time-to-live (TTL) cho message, đó là **thời hạn tồn tại của message**, không phải kết nối mạng, thời gian consumer hoặc producer call timeout.

## 10. Chạy thử và fault injection theo profile

### 10.1. Local smoke test

Với Artemis broker đã chạy, queue `shipping.commands` tồn tại và user có quyền, chạy:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:ARTEMIS_USER = "lab"
$env:ARTEMIS_PASSWORD = "mat-khau-cua-lab"
mvn spring-boot:run
~~~

Quan sát:

- Spring Boot xác nhận active profile là local.
- Listener container được tạo và kết nối đến đúng broker.
- Broker management cho thấy consumer gắn vào đúng queue.
- Khi gọi `ShippingPublisher.publish(eventId, orderId)` từ một endpoint/test harness được cấp quyền, message vào queue; listener xử lý mẫu và commit JMS nếu thành công.
- Với payload bắt đầu `FAIL:`, listener ném exception; quan sát redelivery/DLQ theo chính sách broker. Không phát thử poison message trên queue sản xuất.

### 10.2. Thử TLS trước khi lên production

Ở staging, triển khai URI TLS/truststore qua secret provider; kiểm tra độc lập:

1. Đúng host và port acceptor, không dùng loopback sai namespace.
2. Acceptor hỗ trợ Core và có TLS.
3. Certificate chain được truststore tin, SAN đúng tên DNS.
4. Đăng nhập broker hợp lệ.
5. Quyền `send`/`consume` khớp address.
6. Khi broker restart, listener phục hồi theo policy; redelivery không tạo tác dụng nghiệp vụ trùng.

### 10.3. Ma trận chẩn đoán

| Thử nghiệm | Kỳ vọng / cách phân loại |
|---|---|
| Thiếu `ARTEMIS_HOST` ở prod | Property không đủ để tạo URL hợp lệ; không fallback về local |
| Dùng nhầm `localhost` trong container | Lỗi kết nối TCP/DNS; sửa service discovery |
| Acceptor chỉ AMQP/OpenWire | Artemis native Core client không khớp protocol |
| Broker TLS, client plaintext | TLS/transport handshake lỗi |
| Truststore không có CA | Không xác thực được certificate chain |
| URL host khác SAN | Hostname verification thất bại |
| Sai broker user/password | Authentication failed |
| Đúng user nhưng thiếu role consume | Authorization denied |
| Queue không có/route sai | Listener có thể không nhận hoặc bị lỗi theo broker policy |
| `spring.jms.template.receive-timeout` giảm từ 3s còn 1s | Chỉ thay thời gian chờ lệnh receive đồng bộ |
| `setCallTimeout` nhỏ hơn độ trễ broker | Có thể báo timeout với kết quả gửi không chắc chắn |
| Broker mất kết nối rồi trở lại | Kiểm tra client reconnect, Spring listener recovery, redelivery |
| Downstream HTTP treo | Cần deadline HTTP riêng; listener receive-timeout không sửa được |

Không giải quyết **TLS handshake failure** bằng cách tăng `receiveTimeout`. Không giải quyết **authentication failed** bằng cách giảm connection TTL. Không giải quyết message duplicate bằng cách chặn mọi retry.

## 11. Đối chiếu cấu hình khi dùng ActiveMQ Classic

Với ứng dụng được xây bằng **ActiveMQ Classic client** tương thích phiên bản Spring Boot đang dùng, nhóm property khác Artemis:

~~~yaml
# Dành cho ứng dụng dùng starter/client Classic,
# KHÔNG ghép vào cấu hình Artemis native của ví dụ chính.
spring:
  activemq:
    broker-url: "tcp://classic-broker.internal:61616"
    user: "${CLASSIC_USER}"
    password: "${CLASSIC_PASSWORD}"
~~~

Những khác biệt phải kiểm tra:

- Starter phù hợp có thể là `spring-boot-starter-activemq`, không phải Artemis starter.
- OpenWire transport của Classic và Core transport của Artemis khác nhau; một URL `tcp://` không chứng minh chúng tương thích.
- Classic cũ có client `javax.jms`; Spring Boot 3 dùng `jakarta.jms`. Chọn bộ client tương thích, không thay package/import một cách tùy tiện.
- TLS URL/options, reconnect, send sync/async, prefetch và redelivery policy của Classic có tên/cơ chế riêng. **Không copy `sslEnabled`/`trustStorePath` trong Artemis URL sang Classic và mặc định chạy được.**
- Các API chung của Spring JMS như `JmsTemplate` và listener container vẫn có cách dùng tương tự; phần vendor-specific phải được cấu hình theo provider đã chọn.

Nếu Artemis broker mở acceptor tương thích OpenWire cho một Classic client, ứng dụng đó vẫn mang **cấu hình client Classic**, không chuyển sang `spring.artemis.*` chỉ vì tên broker.

## 12. Những sai lầm cấu hình khó phát hiện

### 12.1. Có default mật khẩu hoặc endpoint production sai

~~~yaml
# KHÔNG nên là default dùng được trong production:
spring:
  artemis:
    broker-url: "tcp://localhost:61616"
    user: admin
    password: admin
~~~

Thay bằng profile rõ ràng và biến bắt buộc. Không coi file `application-prod.yml` là secret store; nó vẫn thường nằm trong Git/JAR.

### 12.2. Tắt TLS validation

Các tùy chọn như `trustAll=true`, `verifyHost=false` hoặc bỏ qua certificate checks có thể khiến connection “thành công” nhưng làm mất đảm bảo danh tính server. Trong production, sửa CA chain, SAN hoặc host name.

### 12.3. Một biến timeout áp cho mọi chỗ

- `receive-timeout` của JmsTemplate không giới hạn listener callback.
- Recovery interval Spring JMS không phải reconnectAttempts của Artemis client.
- Call timeout không là message TTL.
- Connection TTL không là DB/HTTP deadline.
- TCP connect timeout không xác định trạng thái transaction nghiệp vụ.

### 12.4. Tăng concurrency trong khi lỗi là một hot group

Nếu nhiều message của cùng `JMSXGroupID` chỉ được đưa đến một owner để bảo toàn thứ tự, tăng `spring.jms.listener.max-concurrency` không làm nhóm đó xử lý đồng thời. Nếu bottleneck là DB connection pool, tăng listener cũng có thể làm hệ tệ hơn.

### 12.5. Tạo custom ConnectionFactory nhưng chờ Boot tự bind

Khi `@Bean ConnectionFactory` đã được tự khai báo, đừng nghĩ Boot luôn lấy `spring.artemis.broker-url` và sửa bean đó. Phải xác định **đúng property được custom bean dùng** và kiểm thử effective configuration.

### 12.6. Ứng dụng ready nhưng listener không khỏe

Spring ApplicationContext khởi động hoặc HTTP health trả OK chưa chắc listener đã kết nối broker và xử lý được message. Với hệ phụ thuộc JMS, cần monitoring consumer count, oldest message age, redelivery và health/recovery policy rõ ràng.

## 13. Runbook triển khai an toàn

**Bước 1 — kiểm tra nguồn cấu hình.** Xác định active profile, các environment variables và config mount. Chỉ log tên profile/host đã redact; không in password, URL có secret hoặc nội dung truststore.

**Bước 2 — xác minh broker endpoint.** DNS, service name, port, acceptor protocol CORE, firewall, network policy và container namespace.

**Bước 3 — xác minh TLS.** Truststore, SAN, CA chain, certificate expiry, server-auth hay mTLS, version/cipher. Không disable hostname verification.

**Bước 4 — xác minh credential/RBAC.** User/password riêng theo service, role send/consume, secret rotation và số auth failures.

**Bước 5 — đối chiếu từng timeout.** Ghi rõ giá trị, đơn vị, owner, thao tác mà timeout áp dụng và expected recovery. Tránh cấu hình vô hạn không có giám sát.

**Bước 6 — kiểm thử ngắt kết nối.** Broker restart, lost network, timeout khi send/commit, consumer crash và delayed downstream. Kiểm tra trạng thái không chắc chắn của producer, redelivery và business idempotency.

**Bước 7 — nghiệm thu quan sát.** Theo dõi kết nối/listener consumer count, queue age, enqueue/dequeue, message redelivery, DLQ, TLS/auth failures, p95/p99 xử lý. Không chỉ nhìn “connection succeeded”.

## 14. Câu hỏi kiểm tra

**1. Đặt `spring.jms.template.receive-timeout=2s` có giết callback `@JmsListener` sau 2 giây không?**  
Không. Đây là timeout receive đồng bộ của `JmsTemplate`. Business handler cần HTTP/DB timeout riêng và cách rollback/retry phù hợp.

**2. TLS handshake thành công nhưng listener bị từ chối `consume` có mâu thuẫn không?**  
Không. TLS, broker authentication và authorization là các lớp độc lập.

**3. Client báo timeout khi producer gửi persistent message; có thể kết luận message chắc chắn chưa đến broker?**  
Không. Broker có thể đã xử lý trước khi response mất. Retry phải giữ eventId và consumer idempotent.

**4. Một custom `ConnectionFactory` bean đọc `app.artemis-client.url`. Đổi `spring.artemis.broker-url` có chắc đổi endpoint không?**  
Không. Custom bean chỉ dùng các property nó thật sự đọc.

**5. Bật `reconnectAttempts=10` tạo được broker HA chưa?**  
Chưa. Cần broker topology/backup, HA/failover configuration và recovery test thực tế.

**6. Vì sao không bỏ password truststore thẳng trong URI rồi log URL khi startup?**  
URI đã nội suy có thể lộ credential; cần secret management và redaction.

**7. Khi chạy Spring Boot trong container, URL `tcp://127.0.0.1:61616` trỏ tới đâu?**  
Trỏ vào network namespace của container worker, không tự trỏ tới broker container khác.

## 15. Checklist trước deploy

- [ ] Đúng starter/client và JMS namespace cho Artemis hoặc Classic.
- [ ] Profile local/staging/prod được khai báo và kích hoạt rõ ràng.
- [ ] Base config không có credential/URL production giả định.
- [ ] Broker URL dùng đúng DNS, port, namespace và protocol acceptor.
- [ ] Broker user/password cấp qua secret provider, có role tối thiểu.
- [ ] TLS bật cả client và server, verify hostname, truststore hợp lệ.
- [ ] Phân biệt broker auth và TLS client cert/mTLS.
- [ ] Không log URL chứa truststore password hoặc expose Actuator config public.
- [ ] Mọi timeout có lớp, đơn vị và mục tiêu rõ ràng.
- [ ] Reconnect/recovery có giới hạn và được thử với broker restart.
- [ ] Listener transaction/rollback phù hợp; lỗi nghiệp vụ không bị nuốt.
- [ ] Producer retry giữ event ID, consumer idempotent.
- [ ] Nếu tự tạo ConnectionFactory, đã xác minh thuộc tính thực sự được bind.
- [ ] Đã thử sai DNS, sai password, sai SAN, mất broker và consumer redelivery.
- [ ] Có metrics: consumer count, queue age, error/timeout rate, redelivery và DLQ.

## 16. Kết luận

**Profile xác định cấu hình nào có hiệu lực; URL và TLS xác định endpoint cùng danh tính broker; user/password và role xác định quyền; timeout xác định ranh giới của từng thao tác.** Không dùng một giá trị `timeout` để thay thế mọi deadline, cũng không coi TLS thành công là đã được cấp quyền xử lý queue.

Với Spring Boot và Artemis, nên ưu tiên cấu hình chuẩn `spring.artemis.*` và `spring.jms.*` khi đáp ứng đủ nhu cầu; chỉ tạo native ConnectionFactory riêng khi cần API provider-specific và kiểm soát được việc override. Dù cấu hình tốt đến đâu, **send thành công hoặc reconnect thành công vẫn không chứng minh nghiệp vụ consumer đã hoàn tất**: transaction, idempotency, redelivery/DLQ và vận hành phải được kiểm chứng riêng.
