# Chọn JMS provider và thư viện khách tương thích trong Spring

## 1. Vì sao phải chọn đúng cả provider và client?

**JMS (Jakarta Messaging, trước đây là Java Message Service)** là một **API chuẩn** để chương trình Java gửi/nhận message bất đồng bộ. API mô tả những khái niệm như `ConnectionFactory`, `Connection`, `Session`, `MessageProducer`, `MessageConsumer`, `Queue` và `Topic`; nhưng bản thân API **không phải message broker** và **không chuẩn hóa giao thức mạng giữa client và broker**.

Một hệ JMS hoạt động cần ít nhất ba phần:

~~~text
Ứng dụng Spring                         Hạ tầng messaging
┌─────────────────────────────────┐
│ Service / @JmsListener          │
│      ↓                          │
│ JmsTemplate / listener container│
│      ↓                          │
│ jakarta.jms.ConnectionFactory   │  ← API chuẩn
│      ↑                          │
│ JMS client của provider         │  ← hiện thực API, TLS, reconnect,
└────────────┬────────────────────┘     codec, protocol, authentication
             │ giao thức mạng phù hợp
             ▼
        JMS broker / provider
        (Artemis / ActiveMQ Classic / IBM MQ / ...)
~~~

Spring JMS có thể dùng cùng mô hình lập trình với nhiều provider vì phụ thuộc vào `jakarta.jms.ConnectionFactory`. Nhưng client library phải tương thích ở **hai phía**: (1) các interface Java mà phiên bản Spring dùng và (2) broker, protocol, phiên bản server, bảo mật và tính năng JMS thực sự cần.

**Mục tiêu bài học:** biết đặt câu hỏi khi chọn broker, tìm đúng thư viện khách (không nhầm API jar với provider jar), hiểu ranh giới `javax.jms`/`jakarta.jms`, cấu hình với Spring Boot và chạy phép thử end-to-end trước khi quyết định dùng trong production.

## 2. Phân biệt năm lớp tương thích

| Lớp | Câu hỏi phải trả lời | Ví dụ lỗi nếu bỏ qua |
|---|---|---|
| **API Java** | Client triển khai `jakarta.jms` hay `javax.jms`? Phiên bản API có phù hợp Spring Framework? | `NoClassDefFoundError`, `ClassCastException`, không gán được `ConnectionFactory`. |
| **Client implementation** | JAR cụ thể nào tạo `ConnectionFactory` và triển khai các phương thức JMS cần dùng? | Chỉ thêm `jakarta.jms-api` nên không có provider thực tế. |
| **Giao thức / transport** | Broker nhận Core, OpenWire, AMQP 1.0 hay giao thức riêng? Client có nói đúng protocol trên đúng port/acceptor? | Kết nối TCP mở nhưng protocol handshake thất bại. |
| **Tính năng / ngữ nghĩa** | Cần Queue, Topic, durable/shared subscription, selector, delayed delivery, acknowledgement, transaction/XA, DLQ, failover? | Code compile nhưng một operation trả `UnsupportedOperationException` hoặc hành vi khác kỳ vọng. |
| **Vận hành và bảo mật** | TLS, SASL, credentials, ACL, high availability, quota, quan sát, bản vá, license/support, độ trễ có phù hợp? | Hoạt động ở local nhưng lỗi chứng chỉ, phân quyền hoặc failover khi triển khai. |

Thỏa mãn một lớp **không suy ra** thỏa mãn tất cả các lớp. “Cùng là JMS” không có nghĩa “client của broker A luôn kết nối trực tiếp được đến broker B”.

### API JMS không phải giao thức trên dây

Ví dụ Apache ActiveMQ Artemis hỗ trợ các giao thức như **Core, AMQP 1.0, OpenWire, MQTT, STOMP**. Các khả năng đó phục vụ những loại client khác nhau; JMS API của ứng dụng Java được client/provider chuyển thành protocol riêng. Một client hỗ trợ AMQP 1.0 có thể giao tiếp với broker Artemis nếu acceptor và tính năng tương thích, nhưng phải thử semantics JMS cụ thể. Không suy ra rằng client `javax.jms` cũ có thể cắm vào Spring Framework 6 chỉ vì cùng protocol mạng.

## 3. Câu hỏi về nhu cầu trước khi so sánh sản phẩm

Đầu tiên, mô tả workload bằng thông tin đo được:

1. **Cách phát message:** Queue chia việc giữa consumer hay Topic phát cho các subscription? Có cần durable subscriptions, shared subscriptions, selectors, message priority hoặc message TTL không?
2. **Mức bảo đảm giao nhận:** Có chấp nhận at-least-once và deduplication không? Khi consumer offline, message tồn bao lâu? Retry, poison message và dead-letter queue sẽ được xử lý ở đâu?
3. **Tải:** Message mỗi giây, kích thước trung bình và tối đa, số producer/consumer, số connection/session, peak, backlog cho phép và độ trễ chấp nhận được.
4. **Transaction:** Chỉ JMS local transaction, kết hợp DB bằng outbox/inbox hay thực sự cần XA/JTA? Không suy ra rằng mọi provider đều triển khai đầy đủ XA.
5. **Hệ thống hiện có:** Doanh nghiệp đã có broker nào, chuẩn vận hành nào, yêu cầu tương tác giữa Java với .NET/Node/Python hay với hệ thống di sản?
6. **Hạ tầng:** On-premises, container/Kubernetes hay managed service; HA, cluster, replication, TLS/mTLS, identity, monitoring, backup, chính sách lưu trữ và hỗ trợ thương mại.
7. **Tương thích kỹ thuật:** JDK, phiên bản Spring Framework/Spring Boot, `jakarta.jms`/`javax.jms`, provider client và server version.

Một câu “muốn gửi sự kiện cho nhiều dịch vụ” chưa đủ để chọn broker. Cần biết nếu một subscriber tắt thì có phải nhận lại, có chia tải trong cùng subscription và có yêu cầu độ trễ/retention nào.

## 4. So sánh những lựa chọn thường gặp

| Lựa chọn | Khi đáng cân nhắc | Client Java / hệ tích hợp Spring | Điều phải kiểm chứng |
|---|---|---|---|
| **Apache ActiveMQ Artemis** | Dự án JMS mới, tự vận hành broker, cần Queue/Topic và khả năng kết nối đa giao thức. | Spring Boot: `spring-boot-starter-artemis`; client Jakarta: `artemis-jakarta-client`. | Broker version, acceptor/protocol, anycast/multicast routing, persistence, HA, TLS và subscription. |
| **Apache ActiveMQ Classic** | Đang có hệ thống ActiveMQ Classic/OpenWire; muốn giữ broker và từng bước nâng client. | Boot: `spring-boot-starter-activemq`; nhánh client `5.18.x`/`6.x` có ranh giới `javax`/`jakarta` khác nhau. | Hạn chế một số API JMS 2.0/Jakarta 3.1, shared subscription, chuyển đổi từ 5 sang 6, embedded vs remote. |
| **IBM MQ** | Môi trường doanh nghiệp đang dùng queue manager, cần integration, support, tính năng bảo mật/vận hành theo tiêu chuẩn IBM. | Client Jakarta Messaging tương ứng và starter `com.ibm.mq:mq-jms-spring-boot-starter` phù hợp phiên bản Boot. | Queue manager/channel, CCSID, TLS, authority, CCDT, client version, licensing và quy tắc kết nối/failover. |
| **Broker hỗ trợ AMQP 1.0 với Qpid JMS** | Muốn ứng dụng `jakarta.jms` kết nối đến một endpoint AMQP 1.0 tương thích. | `org.apache.qpid:qpid-jms-client` dòng `2.x` (Jakarta 3.1). | AMQP mapping đến JMS destinations/headers/selectors, durable/shared semantics, SASL/TLS/failover. Qpid JMS là **client**, không tự cung cấp broker. |
| **Provider JMS khác** | Đã có nền tảng enterprise/managed messaging với thư viện Jakarta được nhà cung cấp hỗ trợ. | Vendor JAR/starter hoặc một `@Bean ConnectionFactory` tùy sản phẩm. | Chứng nhận Spring/JDK/Jakarta, protocol, tài liệu XA, security, support và hạn chế license. |

**RabbitMQ với `spring-boot-starter-amqp`** sử dụng Spring AMQP và RabbitMQ Java client, **không tự động là JMS provider**. Kafka với Spring Kafka cũng không trở thành JMS broker chỉ vì cùng giải quyết messaging. Nếu định dùng những công nghệ đó, ưu tiên API tích hợp đúng hệ sinh thái; chỉ đưa lớp JMS vào khi có adapter JMS chính thức và đã kiểm tra tính năng.

### Một lựa chọn có thể đúng vì hạ tầng sẵn có

Nếu tổ chức đã dùng IBM MQ và có chuẩn vận hành/chứng chỉ, chọn IBM MQ và Jakarta client tương thích thường hợp lý hơn thay broker chỉ vì một ví dụ Spring dùng Artemis. Ngược lại, khi cần lab JMS dễ dựng cho Java/Spring, Artemis là lựa chọn thực hành thuận tiện. Quyết định dựa vào chi phí toàn vòng đời và các tính năng **đã được thử**, không chỉ vào tên sản phẩm.

## 5. Quy tắc tương thích quan trọng nhất: javax.jms hay jakarta.jms?

Lịch sử tối giản:

| Nhóm ứng dụng/API | Package ở mã Java | Nhóm thư viện cần tìm |
|---|---|---|
| Java EE / JMS 1.1, JMS 2.0; phần lớn Spring Framework 5 và Spring Boot 2 | `javax.jms.*` | Client hiện thực `javax.jms` phù hợp broker. |
| Jakarta Messaging 3.x; Spring Framework 6 và Spring Boot 3 | `jakarta.jms.*` | Client hiện thực `jakarta.jms` phù hợp broker. |
| Spring Framework 7 / Spring Boot 4 | `jakarta.jms.*` | Tiếp tục dùng client Jakarta, nhưng phải kiểm tra yêu cầu phiên bản Spring/JDK và migration của Boot. |

Spring Framework 6 cần Java 17+ và dùng namespace Jakarta; **đổi mỗi import ứng dụng từ `javax.jms` sang `jakarta.jms` là chưa đủ**. Client implementation cũng phải implement interface đúng namespace. Các lớp:

~~~java
javax.jms.ConnectionFactory
jakarta.jms.ConnectionFactory
~~~

là **hai kiểu nhị phân khác nhau** đối với JVM. Đừng thử cast một provider factory hiện thực `javax.jms.ConnectionFactory` thành `jakarta.jms.ConnectionFactory`. Việc giao tiếp giữa ứng dụng cũ và mới qua **broker/protocol chung** có thể vẫn khả thi; khác package trong một process là câu chuyện khác với tương tác qua network.

### Chỉ có API jar không làm được gửi/nhận

~~~groovy
dependencies {
    // Chỉ là interface/specification, không có broker implementation:
    compileOnly 'jakarta.jms:jakarta.jms-api:3.1.0'
}
~~~

Đoạn Gradle này minh họa **dependency chưa đủ**; nếu chỉ có API, Spring không tự tạo được một provider `ConnectionFactory` khả dụng. Trong ứng dụng Boot, nên dùng starter được hỗ trợ hoặc chọn client JAR cụ thể rồi tự cấu hình factory; BOM quản lý version thích hợp. Không thêm hàng loạt các client khác nhau “cho chắc”: chúng dễ gây xung đột transitive dependencies và làm auto-configuration khó đoán.

## 6. Chọn đúng client artifact theo provider

### 6.1. Apache ActiveMQ Artemis

Với ứng dụng Spring Framework 6 / Boot 3, ưu tiên:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

Starter tích hợp Spring và client Jakarta thích hợp theo BOM của Boot. Nếu ứng dụng thuần Spring, không dùng starter, chọn `org.apache.activemq:artemis-jakarta-client` (Jakarta Messaging 3.x) cùng `spring-jms` và khai báo `ConnectionFactory`.

**Cẩn thận tên artifact:**
- `artemis-jms-client` là dòng client theo namespace cũ `javax.jms`, phục vụ JMS 2.0.
- `artemis-jakarta-client` là dòng client `jakarta.jms`.
- `artemis-jakarta-server` là thành phần broker nhúng khi muốn chạy **embedded Artemis** trong ví dụ/lab, **không phải thư viện client cần cho một ứng dụng chỉ kết nối broker ngoài**.

Giữ các module Artemis theo phiên bản được Boot BOM quản lý khi có thể. Đừng tự ép một bản client mới hơn vào một tập module Artemis cũ mà chưa chạy dependency resolution và thử tương thích.

### 6.2. Apache ActiveMQ Classic: khác biệt giữa 5.18.x và 6.x

Đây là ví dụ dễ gây nhầm vì **cùng tên** `activemq-client` nhưng namespace thay đổi qua major version:

| Nhánh ActiveMQ Classic | Artifact client | API package | Ghi chú |
|---|---|---|---|
| `5.18.x` bình thường | `org.apache.activemq:activemq-client` | `javax.jms` | Phù hợp mã JMS cũ. |
| `5.18.1+` chuyển tiếp Jakarta | `org.apache.activemq:activemq-client-jakarta` | `jakarta.jms` | Client-only, dùng broker từ xa; không đồng thời nạp client/broker `javax` cũ trong cùng JVM để dùng embedded/VM transport. |
| `6.x` | `org.apache.activemq:activemq-client` | `jakarta.jms` | Không còn cần artifact `activemq-client-jakarta`. |

Theo tài liệu ActiveMQ Classic, **một số API JMS 2.0/Jakarta 3.1 chưa được hỗ trợ đầy đủ** tùy bản, chẳng hạn shared topic consumers hoặc delayed/async send. Một chương trình chỉ dùng `Queue`, `send` và `receive` có thể chạy ổn nhưng dự án yêu cầu `createSharedDurableConsumer` lại thất bại. Phải xem bảng implementation progress/release notes đúng version và thử API sẽ dùng; đừng chỉ dựa vào version API khai báo trong POM.

Spring Boot 3 cung cấp `spring-boot-starter-activemq`; chọn đúng các dependency đi kèm, tránh kéo ngược client `javax.jms` vào context Jakarta. Với broker Classic 5.x và client Jakarta chuyển tiếp, ưu tiên kết nối **remote** theo tài liệu vendor, không cố nhúng broker `javax` cùng JVM Boot 3.

### 6.3. IBM MQ

IBM MQ có các thư viện JMS cũ và Jakarta Messaging khác nhau. IBM MQ từ **9.3.0** đã hỗ trợ client Jakarta Messaging; các thư viện này dùng `jakarta.jms` và có thể tương tác qua queue manager với client JMS cũ, nhưng không nên trộn hai dòng client trong **cùng ứng dụng**.

Với Spring Boot, starter do IBM cung cấp là:

~~~groovy
dependencies {
    // Chọn version của IBM starter tương thích với major/minor Spring Boot
    // (không copy version từ một bài hướng dẫn cũ).
    implementation 'com.ibm.mq:mq-jms-spring-boot-starter:<compatible-version>'
}
~~~

Ví dụ trên là **ký pháp lựa chọn dependency**, chưa phải khối Gradle có thể resolve nguyên trạng: thay `<compatible-version>` bằng version IBM xác nhận tương thích. Khi thực sự cấu hình, xác nhận queue manager, channel, hostname/port, TLS truststore và quyền truy cập. Đối với Spring Boot 3, dùng dòng starter/client Jakarta; không lắp nhầm `com.ibm.mq.allclient` theo ví dụ Spring Boot 2.

### 6.4. AMQP 1.0 với Apache Qpid JMS

Qpid JMS **2.x** là client `jakarta.jms` trên protocol **AMQP 1.0**, dùng được với broker có AMQP endpoint phù hợp; Qpid JMS **1.x** là dòng `javax.jms`:

~~~groovy
dependencies {
    implementation 'org.springframework:spring-jms'
    implementation 'org.apache.qpid:qpid-jms-client:2.11.0'
}
~~~

Đây là fragment dependency cho ứng dụng Jakarta đã được quản lý version của Spring riêng. Còn phải cấu hình bean `jakarta.jms.ConnectionFactory` của Qpid và endpoint AMQP, không có auto-configuration Spring Boot Artemis/Classic cho Qpid chỉ vì có `spring-jms`. Nhà cung cấp broker có thể dùng AMQP 1.0 nhưng không triển khai mọi đặc tính JMS theo cách Qpid kỳ vọng; **thử selectors, message headers, durable subscriptions, transactions và security** trước khi chốt.

## 7. Spring Boot và việc quản lý dependency

Khi có starter tương thích, để BOM của Spring Boot quản lý các dependency mà BOM đã khai báo. Đây là cấu hình Gradle **độc lập cho lab** với Java 17+ và Spring Boot 3.5.16 (đại diện nhánh Spring Framework 6):

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-provider-compat'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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

    // Chỉ cần để chạy Artemis broker nhúng cho lab.
    runtimeOnly 'org.apache.activemq:artemis-jakarta-server'
}
~~~

Bản `3.5.16` được chọn làm mốc tái lập ví dụ Spring Framework 6, **không phải lời khuyên cố định version production**. Chọn nhánh Spring Boot/JDK còn được hỗ trợ theo vòng đời ứng dụng, dùng Gradle tương thích (Boot 3.5 hỗ trợ Gradle 8.x từ 8.4), và cập nhật theo advisory bảo mật. Các dòng Boot 4 có thể thay đổi quy tắc starter/auto-configuration; kiểm tra tài liệu tương ứng khi nâng major.

**Đừng dùng đồng thời `spring-boot-starter-artemis` và `spring-boot-starter-activemq`** như cách “lắp cả hai để chọn runtime”. Nếu cần hai provider trong một ứng dụng, khai báo hai `ConnectionFactory` có tên, chọn rõ `JmsTemplate` và listener container tương ứng, xử lý transaction riêng và xem xét cách loại trừ auto-config.

### Kiểm tra cây phụ thuộc Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency jakarta.jms-api
./gradlew dependencyInsight --configuration runtimeClasspath --dependency artemis-jakarta-client
~~~

Trên Windows PowerShell, thay `./gradlew` bằng `.\gradlew.bat` nếu dự án có Wrapper. Khi kiểm tra, cần thấy provider client mong đợi, phiên bản Jakarta API và Spring đồng bộ; điều tra mọi `javax.jms-api` hoặc cả hai loại client Artemis/Classic trong classpath. **Có `javax.jms` gián tiếp chưa tự động chứng minh lỗi**, nhưng không được để runtime gửi nhầm loại `ConnectionFactory` hay expose API cũ vào Spring 6.

Nếu cần biết thư viện thực thi nào hiện có, xét dependency graph và kiểm tra implementation bean thực tại runtime, không chỉ nhìn compile classpath.

## 8. Demo chạy được: kiểm tra Artemis embedded bằng round-trip

Demo này làm rõ tiêu chí cuối cùng: không chỉ “đã resolve dependency” mà có thể **gửi và nhận một `TextMessage` thực sự** với provider. Dùng Spring Boot 3.5.16, Java 17, Gradle như mục 7. Không cần Docker hay broker cài ngoài vì có thêm Artemis server nhúng.

Cấu trúc:

~~~text
jms-provider-compat/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/jms/ProviderSmoke.java
    └── resources/application.yml
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: embedded
    embedded:
      queues: compat.check
      persistent: false
~~~

`src/main/java/example/jms/ProviderSmoke.java`:

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class ProviderSmoke {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(ProviderSmoke.class, args)) {

            // Đảm bảo Spring đã inject được factory triển khai jakarta.jms.
            ConnectionFactory factory =
                    context.getBean(ConnectionFactory.class);
            System.out.println("ConnectionFactory="
                    + factory.getClass().getName());

            JmsTemplate template = context.getBean(JmsTemplate.class);
            template.setReceiveTimeout(3_000);

            // Không có listener cạnh tranh, nên đọc lại từ cùng queue.
            template.convertAndSend("compat.check", "ping");
            Object received = template.receiveAndConvert("compat.check");

            if (!"ping".equals(received)) {
                throw new IllegalStateException(
                        "Unexpected JMS payload: " + received);
            }

            System.out.println("ROUND_TRIP_OK=ping");
        }
    }
}
~~~

Chạy từ thư mục chứa `build.gradle`:

~~~bash
./gradlew bootRun
~~~

Nếu dùng Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Sau các dòng log của Spring Boot và Artemis, nếu chạy thành công sẽ xuất hiện dòng:

~~~text
ROUND_TRIP_OK=ping
~~~

Dòng `ConnectionFactory=...` phụ thuộc class cụ thể và wrapper/cache nên **không cố định tên lớp trong output**. Bài kiểm thử này chứng minh starter, provider client, broker embedded, Queue, `String` ↔ `TextMessage` và send/receive hoạt động **trong một process**. Nó chưa chứng minh kết nối mạng, TLS, failover, XA hay durability khi broker khởi động lại. `persistent: false` chỉ phù hợp lab, không phải mặc định đảm bảo lưu trữ cho production.

### Chuyển sang Artemis broker ở ngoài

Khi chạy broker riêng, **bỏ dependency server nhúng** và đổi cấu hình ứng dụng như sau (hostname/port phải là endpoint thực của broker):

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
~~~

Cấp username/password từ biến môi trường hay secret manager theo hướng dẫn triển khai; ví dụ không lưu mật khẩu trong Git. Tạo Queue `compat.check` trên broker hoặc cho phép auto-create theo chính sách broker. Chạy lại `./gradlew bootRun` và xác minh `ROUND_TRIP_OK=ping`; khi đó mới kiểm chứng được **network protocol** của client với broker. Nếu broker dùng TLS, phải cấu hình connector, truststore/certificate và URL đúng chuẩn provider, không chỉ thay `tcp://` bằng một tiền tố tưởng tượng.

### Nếu dùng ActiveMQ Classic

Một dự án **khác** có thể thay starter Artemis bằng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-activemq'
}
~~~

và khai báo:

~~~yaml
spring:
  activemq:
    broker-url: tcp://localhost:61616
~~~

Đây là mẫu **kết nối remote**; ứng dụng phải có broker Classic tương thích và Queue phù hợp. Đừng giữ `artemis-jakarta-server` trong dự án Classic hoặc dùng cả hai starter. Dòng Gradle/Java ở phần demo chỉ cần thư viện JMS chung nhờ sử dụng API `jakarta.jms`; phần không portable nằm ở provider JAR, URL, authentication và capability.

## 9. Nếu không dùng starter: tự cung cấp ConnectionFactory cho Spring

Spring JMS cần một bean `jakarta.jms.ConnectionFactory`. Với Boot, starter có thể tạo sẵn; với ứng dụng Spring Framework thuần hoặc provider không được Boot auto-config trực tiếp, bạn phải tạo bean bằng lớp client vendor hoặc lookup từ JNDI/container.

Ví dụ khung cấu hình (minh họa bean factory được cấp sẵn bởi container/provider):

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@EnableJms
public class JmsWiring {
    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        return new JmsTemplate(connectionFactory);
    }

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-3");
        return factory;
    }
}
~~~

Lớp này chỉ đầy đủ khi đã có bean `ConnectionFactory` tương ứng, do container/vendor configuration tạo. Nó **không** tự triển khai provider. Khi `@JmsListener` không chỉ rõ `containerFactory`, Spring tìm bean tên `jmsListenerContainerFactory`. Trong Boot, nhiều phần auto-configuration đã có sẵn; không nhất thiết tự tạo mọi bean.

### JNDI, pooling và quản lý connection

- Một application server có thể cung cấp `ConnectionFactory` qua JNDI/resource adapter. Khi đó dùng **managed factory** để khớp container-managed transactions/security; không tùy tiện tạo native client song song.
- Spring `CachingConnectionFactory` giúp tái sử dụng connection/session; provider pool như `pooled-jms` lại có chính sách pooling khác. Chọn và đo đạc theo workload, không mặc định “pool càng nhiều càng tốt”.
- Nếu cần durable subscription với client ID, phải xem quy tắc quản lý connection/client ID và concurrency; shared subscription và unshared durable khác nhau.
- Với nhiều provider trong cùng context, dùng `@Qualifier` hoặc factory riêng cho publisher/listener. Chỉ chọn một `ConnectionFactory` mặc định khi ứng dụng thực sự có một broker logic.

## 10. Bài test tương thích phải kiểm tra những gì?

Một phép thử `connect()` là cần thiết nhưng chưa đủ. Nên thực hiện lần lượt trên **chính phiên bản broker, client, JDK và cấu hình triển khai dự kiến**:

| Cấp kiểm thử | Thao tác | Điều kiện đạt |
|---|---|---|
| **Build** | Resolve dependency; compile import `jakarta.jms.ConnectionFactory`. | Không có xung đột class, `NoSuchMethodError` hay mismatch `javax`/`jakarta`. |
| **Connection** | Kết nối broker thật qua URL/protocol dự kiến. | Đúng host/port, handshake, authentication, TLS và ACL. |
| **Queue** | Gửi `TextMessage` có ID; nhận và xác nhận. | Payload, headers, properties, correlation ID và acknowledgement chính xác. |
| **Topic** | Hai subscription độc lập nhận sự kiện; thử shared/durable nếu cần. | Phân phối theo đúng subscription; backlog khi offline hoạt động như hợp đồng. |
| **Rollback/Retry** | Listener cố ý throw exception; thử redelivery và DLQ. | Số lần retry, duplicate và poison message đúng chính sách. |
| **Transaction** | Kiểm tra JMS local transaction hoặc XA/JTA thật sự được yêu cầu. | Commit/rollback và failure boundary nhất quán; không chỉ thấy annotation `@Transactional`. |
| **Vận hành** | Kill/restart broker, đứt mạng, hết quota, rotate credential/chứng chỉ. | Reconnect, failover, timeout và recovery theo mục tiêu SLA. |
| **Tải & khả năng theo dõi** | Load test đỉnh và dài hạn, đo backlog/lag/redelivery. | Đáp ứng throughput/latency, không rò resource và có log/metric đủ chẩn đoán. |

**Thử tính năng quan trọng, không chỉ phiên bản chuẩn công bố.** Ví dụ consumer thường hoạt động với ActiveMQ Classic chưa đảm bảo `shared durable subscription` hỗ trợ trên đúng bản đang chạy. Trên broker đa giao thức, một queue có thể mang kiểu routing khác tùy protocol; hãy kiểm tra cả mapping tương ứng.

### Kiểm tra tối thiểu với môi trường thật

1. Dùng **broker dev/test**, không thử xóa/truncate Queue production.
2. Tạo destination có tên rõ ràng và đúng loại Queue/Topic; set TTL nhỏ và message ID để truy dấu.
3. Gửi message từ Spring, nhận bằng Spring; nếu tích hợp đa ngôn ngữ, gửi/nhận chéo với client khác.
4. Thử client offline, broker restart, network partition và xác thực sai.
5. Lưu lại tuple gồm **JDK + Spring Boot/Framework + provider client + broker version + protocol + cấu hình bảo mật + tính năng đã kiểm**.

Chỉ khi tuple này đã qua kiểm thử mới coi cấu hình “tương thích” cho yêu cầu cụ thể; khả năng chạy trong lab không phải bằng chứng tương đương production.

## 11. Lỗi thường gặp và cách khoanh vùng

| Triệu chứng | Nguyên nhân khả dĩ | Bước kiểm tra |
|---|---|---|
| `package javax.jms does not exist` hoặc không compile `jakarta.jms` | Sai namespace so với API đang import. | Kiểm tra Spring major, dependency tree và import, thay đúng dòng client. |
| `NoClassDefFoundError: javax/jms/...` trong Boot 3 | Provider JAR hoặc thư viện phụ vẫn dùng `javax`. | `dependencyInsight`, xác định artifact gây ra và thay bản Jakarta. |
| `ClassCastException` hoặc factory không gán được vào `jakarta.jms.ConnectionFactory` | Client triển khai interface của namespace khác. | Kiểm tra interface thật của vendor factory, không ép cast. |
| `No qualifying bean of type 'jakarta.jms.ConnectionFactory'` | Chỉ có JMS API, chưa có starter/provider bean hoặc auto-config không chạy. | Xem startup condition report và khai báo đúng starter/factory. |
| Kết nối từ chối hoặc treo tại handshake | Broker chưa chạy, sai endpoint/port, protocol hoặc firewall. | Kiểm tra listener/acceptor thực, network reachability và logs hai phía. |
| `JMSSecurityException`, TLS handshake failure | Sai user, channel authority, truststore, hostname/certificate. | Kiểm tra ACL và TLS profile từ vendor, không log credentials. |
| Gửi được nhưng listener không nhận | Queue/Topic nhầm kiểu, khác destination, thiếu subscription/selector, sai transaction. | Xác minh routing type và listener factory, subscription, broker metrics. |
| `UnsupportedOperationException` ở một JMS API | Client/provider chưa triển khai tính năng JMS cần dùng. | Đọc feature matrix đúng version, kiểm thử API và cân nhắc provider khác. |
| Nhiều `ConnectionFactory` khiến injection mơ hồ | Kéo nhiều starter/provider hoặc tự khai báo thêm factory. | Loại dependency dư; nếu multi-broker dùng `@Qualifier`/tên bean. |
| Test broker embedded chạy, production lỗi | Embedded bỏ qua networking/TLS/ACL/failover thực. | Test với broker thật, cấu hình tương đương môi trường chạy. |

### Ba ngộ nhận cần sửa ngay

- **“Tôi thêm `jakarta.jms-api` là đủ.”** Sai: đó là hợp đồng interface; cần client implementation và endpoint provider.
- **“Broker nói hỗ trợ AMQP/JMS thì client nào cũng kết nối được.”** Sai: JMS không chuẩn hóa wire protocol; xác thực, version negotiation và các mapping tính năng vẫn khác nhau.
- **“Spring Boot tạo JmsTemplate nên broker đã sẵn sàng.”** Sai: bean tồn tại lúc startup chưa chứng minh đã kết nối, có quyền truy cập Queue/Topic hoặc thực hiện được round-trip. Hãy chạy integration test.

## 12. Bài tập chọn giải pháp theo tình huống

**Tình huống A.** Ứng dụng Spring Boot 3 mới, yêu cầu JMS Queue/Topic, có thể vận hành broker riêng, muốn thử nghiệm local nhanh.  
**Gợi ý:** Bắt đầu đánh giá **Artemis + `spring-boot-starter-artemis`**; tạo embedded smoke test rồi kiểm thử remote broker với TLS, durable subscriber và failover nếu cần.

**Tình huống B.** Doanh nghiệp có ActiveMQ Classic 5.18 broker; ứng dụng mới dùng `jakarta.jms`, chỉ kết nối remote.  
**Gợi ý:** Kiểm tra client chuyển tiếp `activemq-client-jakarta` đúng nhánh 5.18.1+ hoặc phương án nâng broker/client 6.x; không dùng `activemq-client` 5.18.x `javax` như factory Spring 6; kiểm chứng API thực sự dùng và hạn chế shared subscription.

**Tình huống C.** Môi trường đang có IBM MQ queue manager, chuẩn ACL/TLS và license đầy đủ; Spring Boot 3 cần kết nối.  
**Gợi ý:** Dùng starter và **Jakarta client** do IBM công bố tương thích với Boot 3; thiết lập channel, TLS, permissions, kiểm tra version queue manager và failover thay vì đổi broker không cần thiết.

**Tình huống D.** Broker có endpoint AMQP 1.0; đội Java muốn dùng `@JmsListener` mà không dùng driver vendor.  
**Gợi ý:** Đánh giá **Qpid JMS 2.x** bằng một `ConnectionFactory` riêng; chứng minh broker hỗ trợ những semantic JMS cần thiết. Một AMQP broker bất kỳ không tự bảo đảm mọi tính năng JMS.

**Tình huống E.** Hệ thống dùng RabbitMQ với Spring AMQP và không có yêu cầu JMS.  
**Gợi ý:** Dùng `spring-boot-starter-amqp` và API Spring AMQP; không thêm JMS layer chỉ vì JMS cũng hỗ trợ message queue.

## 13. Checklist trước khi chốt dependency

- [ ] Đã chọn một **provider/broker** phù hợp yêu cầu, không nhầm tên client/JAR với broker.
- [ ] Đã xác định **Spring + JDK + `javax.jms`/`jakarta.jms`** và một client implementation đúng namespace.
- [ ] Đã xác nhận **protocol/port/transport** client dùng trùng endpoint broker hỗ trợ.
- [ ] Đã dùng **BOM/version matrix** phù hợp và kiểm tra runtime dependency tree.
- [ ] Đã thử **Queue/Topic** và các tính năng thật sự dùng: shared/durable, selector, TTL, transactions, redelivery, DLQ.
- [ ] Đã thử **TLS/auth/ACL** và phương án HA/recovery theo yêu cầu.
- [ ] Đã chạy round-trip gửi–nhận với môi trường gần production, có metric/log để chẩn đoán.
- [ ] Đã ghi lại **ma trận phiên bản đã kiểm thử**; có kế hoạch nâng cấp và vá bảo mật.

## 14. Tài liệu chính thức để đối chiếu

- [Spring Framework — Using JMS, ConnectionFactory, resource handling](https://docs.spring.io/spring-framework/reference/integration/jms/using.html).
- [Spring Framework — Annotation-driven @JmsListener](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html).
- [Spring Boot 3.4 — JMS (ActiveMQ Classic, Artemis, configuration)](https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html).
- [Spring Boot 3.5 — Managing Dependencies](https://docs.spring.io/spring-boot/3.5/gradle-plugin/managing-dependencies.html).
- [Apache ActiveMQ Artemis — JMS/Jakarta client classpath](https://artemis.apache.org/components/artemis/documentation/latest/client-classpath).
- [Apache ActiveMQ Artemis — Protocols and interoperability](https://artemis.apache.org/components/artemis/documentation/latest/protocols-interoperability.html).
- [Apache ActiveMQ Classic — Jakarta Messaging/JMS support matrix](https://activemq.apache.org/components/classic/documentation/jms2).
- [IBM MQ — Jakarta Messaging client overview](https://www.ibm.com/docs/en/ibm-mq/10.0.x?topic=messaging-mq-classes-jakarta-overview).
- [IBM MQ JMS Spring starter — README và version support](https://github.com/ibm-messaging/mq-jms-spring).
- [Apache Qpid JMS — Jakarta Messaging AMQP 1.0 client](https://qpid.apache.org/components/jms/index.html).
