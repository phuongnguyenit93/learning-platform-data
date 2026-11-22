# Chuyển từ javax.jms sang jakarta.jms và yêu cầu tương thích phiên bản

Khi nâng cấp ứng dụng JMS từ thế hệ Spring Framework 5.x lên Spring Framework 6.x, một thay đổi quan trọng là package của Jakarta Messaging chuyển từ javax.jms sang jakarta.jms. Đây là thay đổi ở cấp tên lớp và binary, vì vậy việc chỉ đổi phiên bản thư viện mà giữ nguyên import cũ sẽ không đủ.

Để migration thành công, cần đồng bộ mã nguồn, dependency API, thư viện client của message broker, Spring Framework hoặc Spring Boot, JDK và môi trường triển khai. Bài này giải thích ranh giới tương thích, chỉ ra các thay đổi cần thực hiện và hướng dẫn kiểm tra ứng dụng sau khi chuyển đổi.

## 1. Vì sao javax.jms đổi thành jakarta.jms?

JMS ban đầu thuộc Java EE và sử dụng namespace javax.jms. Sau khi Java EE được chuyển giao cho Eclipse Foundation và phát triển dưới tên Jakarta EE, Jakarta EE 9 thực hiện thay đổi namespace cấp cao từ javax sang jakarta đối với các API thuộc nền tảng.

Với messaging:

- Java EE 8 sử dụng JMS 2.0 với package javax.jms.
- Jakarta EE 9 đưa Jakarta Messaging 3.0 vào package jakarta.jms.
- Jakarta EE 10 đưa Jakarta Messaging 3.1 vào package jakarta.jms.

Tên đặc tả cũng chuyển từ Java Message Service (JMS) sang Jakarta Messaging, nhưng trong giao tiếp hằng ngày nhiều đội phát triển vẫn gọi ngắn gọn là JMS.

Thay đổi namespace không có nghĩa toàn bộ hành vi messaging được thiết kế lại. Jakarta Messaging 3.0 tiếp tục mô hình và hành vi tương ứng với API JMS trước đó, nhưng các kiểu Java có tên package mới. Vì package là một phần của tên kiểu ở cấp JVM, javax.jms.Message và jakarta.jms.Message là hai kiểu khác nhau.

Đặc tả Jakarta EE 9 xác định việc chuyển namespace không tương thích source và binary với các bản Java EE trước đó. Do đó, một class đã biên dịch với javax.jms không tự động trở thành class tương thích với jakarta.jms chỉ bằng cách thay dependency ở runtime.

## 2. Phạm vi thay đổi trong mã nguồn

Ví dụ các import thường gặp:

| API cũ | API mới |
|---|---|
| javax.jms.ConnectionFactory | jakarta.jms.ConnectionFactory |
| javax.jms.Connection | jakarta.jms.Connection |
| javax.jms.Session | jakarta.jms.Session |
| javax.jms.Destination | jakarta.jms.Destination |
| javax.jms.Queue | jakarta.jms.Queue |
| javax.jms.Topic | jakarta.jms.Topic |
| javax.jms.Message | jakarta.jms.Message |
| javax.jms.TextMessage | jakarta.jms.TextMessage |
| javax.jms.JMSException | jakarta.jms.JMSException |
| javax.jms.JMSContext | jakarta.jms.JMSContext |
| javax.jms.JMSConsumer | jakarta.jms.JMSConsumer |
| javax.jms.JMSProducer | jakarta.jms.JMSProducer |

Ví dụ trước migration:

~~~java
import javax.jms.ConnectionFactory;
import javax.jms.JMSContext;
import javax.jms.Message;
import javax.jms.TextMessage;
~~~

Sau migration:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
~~~

Tên lớp và phương thức trong nhiều trường hợp được giữ nguyên. Thay đổi chủ yếu nằm ở package import và các artifact phụ thuộc. Tuy nhiên, phải biên dịch lại toàn bộ mã nguồn và các module có tham chiếu đến JMS API mới.

### Không thay thế máy móc mọi package javax

Không phải mọi package bắt đầu bằng javax đều đã chuyển sang jakarta. Một số package thuộc Java SE vẫn giữ nguyên, ví dụ:

- javax.sql.DataSource
- javax.naming.Context
- javax.naming.InitialContext
- javax.crypto.Cipher
- javax.management.MBeanServer
- javax.net.ssl.SSLContext

Các API thuộc Java EE/Jakarta EE khác có thể đã chuyển namespace, ví dụ javax.servlet sang jakarta.servlet, javax.persistence sang jakarta.persistence, javax.transaction sang jakarta.transaction và javax.annotation sang jakarta.annotation.

Khi migration JMS, hãy tìm chính xác javax.jms trong source, test, cấu hình và dependency. Một thao tác thay thế toàn bộ chuỗi javax. thành jakarta. có thể làm hỏng những API Java SE vẫn giữ namespace cũ.

## 3. Quan hệ giữa phiên bản Spring, JMS API và Java

Cần nhìn phiên bản Spring và JMS API cùng nhau:

| Thế hệ | Nền tảng messaging | Namespace | Java baseline |
|---|---|---|---|
| Spring Framework 5.3 | JMS 2.0 / Java EE 8 | javax.jms | Tùy bản Spring 5.3 và ứng dụng; hỗ trợ từ Java 8 |
| Spring Framework 6.0 | Jakarta Messaging 3.0 trở lên | jakarta.jms | Java 17+ |
| Spring Framework 6.1 / 6.2 | Jakarta Messaging 3.x | jakarta.jms | Java 17+ |
| Spring Boot 2.7 | Spring Framework 5.3 | javax.jms | Theo baseline của Boot 2.7 |
| Spring Boot 3.x | Spring Framework 6.x | jakarta.jms | Java 17+ |

Spring Framework 6.0 nâng baseline lên Java 17 và Jakarta EE 9. Spring Boot 3.0 yêu cầu Java 17 và Spring Framework 6.0. Các dòng Spring 6.x tiếp tục dùng jakarta.jms.

Jakarta Messaging 3.0 tương ứng với Jakarta EE 9; Jakarta Messaging 3.1 tương ứng với Jakarta EE 10. Phiên bản API cụ thể mà ứng dụng dùng cần tương thích với dòng Spring, provider và runtime đang triển khai. Hãy để Spring Boot BOM hoặc dependency management của dự án quản lý phiên bản khi có thể.

Bảng trên là định hướng theo thế hệ chính. Khi chọn bản vá cụ thể, hãy kiểm tra release notes và dependency management của đúng phiên bản Spring Boot/Spring Framework đang dùng, cùng ma trận hỗ trợ của JMS provider.

## 4. Dependency Maven cần thay đổi

Với ứng dụng JMS cũ, dependency API thường có dạng:

~~~xml
<dependency>
    <groupId>javax.jms</groupId>
    <artifactId>javax.jms-api</artifactId>
    <version>2.0.1</version>
</dependency>
~~~

Dependency API Jakarta Messaging có dạng:

~~~xml
<dependency>
    <groupId>jakarta.jms</groupId>
    <artifactId>jakarta.jms-api</artifactId>
    <version>3.1.0</version>
</dependency>
~~~

Nếu ứng dụng dùng Spring Framework 6.x trực tiếp, module tích hợp Spring JMS là spring-jms:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-jms</artifactId>
    <version>6.2.19</version>
</dependency>
~~~

Trong một ứng dụng Spring Boot, nên dùng starter và BOM do Spring Boot quản lý. Ví dụ, ứng dụng Boot có thể khai báo starter tương ứng với provider đang dùng và để dependency management chọn phiên bản Spring/Jakarta phù hợp. Không nên ghim một phiên bản Jakarta JMS API tùy ý nếu provider hoặc Spring line yêu cầu phiên bản khác.

Lưu ý:

- jakarta.jms-api chỉ cung cấp interface và class API. Nó không phải message broker và không tự tạo ConnectionFactory hoạt động.
- Ứng dụng cần thư viện client của provider như ActiveMQ, Artemis, IBM MQ, Solace hoặc sản phẩm tương ứng.
- Artifact client của provider phải triển khai jakarta.jms nếu ứng dụng đang dùng Spring 6.x.
- Không giữ đồng thời javax.jms-api và jakarta.jms-api chỉ để làm cho compiler hết lỗi. Hai API không thay thế kiểu cho nhau và có thể gây xung đột hoặc nhầm lẫn trong dependency graph.
- Một số provider đóng gói API trong client artifact của họ. Hãy theo hướng dẫn của provider để tránh khai báo API trùng lặp.

## 5. Spring JMS thay đổi gì và giữ nguyên gì?

Package tích hợp của Spring vẫn là org.springframework.jms. Ví dụ:

- org.springframework.jms.core.JmsTemplate
- org.springframework.jms.annotation.JmsListener
- org.springframework.jms.config.DefaultJmsListenerContainerFactory
- org.springframework.jms.support.converter.MessageConverter

Các lớp Spring này không đổi tên package theo namespace Jakarta. Điều thay đổi là các kiểu JMS mà chúng tương tác cùng chuyển sang jakarta.jms.

Ví dụ, JmsTemplate vẫn được import như sau:

~~~java
import org.springframework.jms.core.JmsTemplate;
~~~

Khi làm việc trực tiếp với API JMS, dùng kiểu mới:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.TextMessage;
~~~

Nếu code có cả Spring Message và JMS Message, cần giữ import đúng:

- org.springframework.messaging.Message là abstraction Message của Spring Messaging.
- jakarta.jms.Message là message của Jakarta Messaging provider.

Hai kiểu này phục vụ hai tầng khác nhau. Đổi import nhầm có thể gây lỗi compile hoặc chuyển đổi message sai.

## 6. Thay đổi code trước và sau migration

### Ví dụ gửi message bằng JMSContext

Trước migration:

~~~java
import javax.jms.ConnectionFactory;
import javax.jms.JMSContext;
import javax.jms.Topic;

public class LegacyPublisher {

    public void publish(ConnectionFactory connectionFactory, Topic topic) {
        try (JMSContext context =
                connectionFactory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {
            context.createProducer().send(topic, "OrderCreated");
        }
    }
}
~~~

Sau migration, logic gửi không cần thay đổi; chuyển import sang jakarta.jms:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Topic;

public class JakartaPublisher {

    public void publish(ConnectionFactory connectionFactory, Topic topic) {
        try (JMSContext context =
                connectionFactory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {
            context.createProducer().send(topic, "OrderCreated");
        }
    }
}
~~~

Đoạn code sau migration cần Jakarta JMS provider cung cấp ConnectionFactory và Topic tương thích. Chỉ có API dependency thì chưa thể kết nối tới broker.

### Ví dụ listener trong Spring

Listener dùng Spring annotation vẫn giữ nguyên:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @JmsListener(destination = "orders.events")
    public void receive(String payload) {
        System.out.println("Received: " + payload);
    }
}
~~~

Nếu listener nhận trực tiếp JMS Message, import phải là jakarta.jms.Message:

~~~java
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class RawOrderListener {

    @JmsListener(destination = "orders.events")
    public void receive(Message message) throws Exception {
        if (message instanceof TextMessage textMessage) {
            System.out.println(textMessage.getText());
        }
    }
}
~~~

Spring dùng MessageConverter để chuyển JMS Message sang payload Java khi method listener khai báo kiểu String hoặc DTO. Khi method nhận trực tiếp jakarta.jms.Message, ứng dụng làm việc với message của Jakarta Messaging.

## 7. Yêu cầu tương thích với JMS provider và broker

Đổi import và dependency mới chỉ là một phần của migration. JMS provider cần cung cấp client library tương thích với Jakarta Messaging.

Hãy kiểm tra bốn thành phần:

**API:** ứng dụng biên dịch với jakarta.jms-api phiên bản phù hợp.

**Provider client:** thư viện client của broker phải triển khai đúng namespace jakarta.jms. Một client cũ chỉ triển khai javax.jms.ConnectionFactory không thể được truyền vào code yêu cầu jakarta.jms.ConnectionFactory.

**Broker/server:** phiên bản server phải được provider hỗ trợ bởi client Jakarta đang dùng. Có broker cho phép nâng client mà không phải nâng server; có sản phẩm yêu cầu phiên bản server hoặc cấu hình mới. Cần kiểm tra ma trận tương thích chính thức của nhà cung cấp.

**Runtime/container:** nếu ứng dụng chạy trong application server, server phải cung cấp Jakarta Messaging API và resource phù hợp. Không đóng gói thêm một API version xung đột với API do server cung cấp nếu môi trường yêu cầu dùng shared library.

Namespace là tên kiểu Java, còn giao thức trên mạng và định dạng message là vấn đề riêng. Việc đổi javax.jms sang jakarta.jms không tự thay đổi payload JSON, destination name hoặc protocol của broker. Tuy nhiên, khả năng hai thế hệ client cùng kết nối một broker phụ thuộc provider. Không giả định một JMS client cũ và một Jakarta client mới có thể dùng chung mọi object Java hoặc class ConnectionFactory.

## 8. Tương thích binary và lỗi khi trộn hai namespace

Xét hai kiểu:

~~~java
javax.jms.ConnectionFactory
jakarta.jms.ConnectionFactory
~~~

Dù tên lớp đơn giản giống nhau, JVM xem chúng là hai kiểu độc lập vì tên đầy đủ khác nhau.

Một thư viện đã biên dịch với javax.jms có thể có method signature chứa javax.jms.Message. Spring 6.x gọi method tương ứng với jakarta.jms.Message. Hai chữ ký không tương thích.

Các lỗi thường gặp:

- package javax.jms does not exist: dependency cũ không còn trong classpath hoặc đã chuyển sang Jakarta API.
- package jakarta.jms does not exist: chưa khai báo API Jakarta hoặc provider client phù hợp.
- ClassCastException: code cố ép kiểu giữa hai namespace.
- NoClassDefFoundError: runtime không tìm thấy class mà thư viện đã biên dịch yêu cầu.
- NoSuchMethodError hoặc LinkageError: các phiên bản thư viện không thống nhất hoặc cùng class được nạp từ API khác nhau.
- ClassNotFoundException: tên lớp cũ còn nằm trong cấu hình, reflection hoặc metadata.

Không thể giải quyết bằng cách ép cast, đổi tên biến hay thêm cả hai API vào classpath. Cần đồng bộ tất cả thành phần giao tiếp trực tiếp qua kiểu JMS.

## 9. Quy trình migration từng bước

### Bước 1 — Ghi nhận baseline hiện tại

Trước khi thay đổi, ghi lại:

- Java version.
- Spring Framework hoặc Spring Boot version.
- JMS API version.
- JMS provider và client library version.
- Broker/server version.
- Cách tạo ConnectionFactory, Destination và listener container.
- Các luồng gửi, nhận, transaction, acknowledgment, durable subscription và retry đang được sử dụng.

Chạy test hiện tại để có mốc so sánh.

### Bước 2 — Chọn đích nâng cấp

Nếu ứng dụng đang dùng Spring Boot 2.7 hoặc Spring Framework 5.3, hãy xác định dòng Spring Boot 3.x/Spring Framework 6.x phù hợp. Spring Framework 6.x yêu cầu Java 17 trở lên.

Kiểm tra các thư viện tích hợp khác như Spring Cloud, Spring Integration, Spring Batch, security, tracing và thư viện provider. Mỗi dự án có lịch phát hành và yêu cầu tương thích riêng.

### Bước 3 — Nâng cấp JDK và Spring dependency

Nâng môi trường build và runtime lên JDK 17 trở lên khi chuyển sang Spring 6. Nếu dùng Spring Boot, cập nhật parent/BOM hoặc plugin quản lý dependency và để starter quản lý các module Spring.

Không nâng riêng spring-jms lên một major version mới trong khi các module Spring Framework còn lại vẫn ở dòng cũ.

### Bước 4 — Thay API namespace

Tìm các tham chiếu javax.jms trong:

- Mã nguồn chính.
- Test và test fixture.
- Module dùng chung.
- Cấu hình XML, properties và YAML.
- Reflection, class name dạng chuỗi.
- Adapter hoặc thư viện nội bộ.

Đổi các kiểu JMS sang jakarta.jms, sau đó biên dịch lại toàn bộ module liên quan.

### Bước 5 — Nâng provider client

Thay client library của broker bằng phiên bản hỗ trợ Jakarta Messaging. Kiểm tra cách khai báo ConnectionFactory, JNDI, TLS, authentication, failover, pooling và destination.

Nếu ứng dụng dùng resource do application server cung cấp, kiểm tra resource đó có triển khai Jakarta Messaging API và có thể inject vào Spring hay không.

### Bước 6 — Kiểm tra dependency tree

Dùng Maven:

~~~shell
mvn dependency:tree
~~~

Có thể lọc các artifact JMS:

~~~shell
mvn dependency:tree -Dincludes=javax.jms:javax.jms-api,jakarta.jms:jakarta.jms-api
~~~

Mục tiêu là xác định thư viện nào còn kéo API cũ vào. Nếu một thư viện nội bộ vẫn phụ thuộc javax.jms, cần nâng phiên bản hoặc biên dịch lại thư viện đó.

Với Gradle, dùng:

~~~shell
./gradlew dependencies
~~~

và kiểm tra runtimeClasspath cũng như testRuntimeClasspath.

### Bước 7 — Chạy kiểm thử tích hợp với broker thật

Kiểm tra tối thiểu:

- Producer gửi TextMessage, BytesMessage hoặc loại message đang dùng.
- Consumer nhận và chuyển đổi payload.
- Selector và message properties.
- Queue, Topic và shared/durable subscription nếu có.
- Acknowledgment, session transaction và rollback.
- Redelivery, dead-letter queue và retry.
- Correlation ID và request/reply.
- Reconnect, failover và broker restart.
- TLS, authentication và quyền truy cập destination.
- Concurrency, shutdown và graceful recovery.

Kiểm thử với broker thật rất quan trọng vì việc compile thành công chỉ xác nhận API và kiểu dữ liệu. Nó không chứng minh provider client, broker và cấu hình vận hành tương thích.

### Bước 8 — Triển khai theo từng môi trường

Chạy integration test ở môi trường dev, staging và production-like. Khi rolling deployment, xác định rõ broker có hỗ trợ đồng thời client cũ và mới hay không. Nếu hai phiên bản ứng dụng cùng chạy, tránh chia sẻ object JMS hoặc class Java giữa hai namespace; trao đổi qua broker bằng message payload có schema ổn định.

Theo dõi connection failure, authentication error, message backlog, redelivery, consumer count và lỗi chuyển đổi message sau khi triển khai.

## 10. Ví dụ chạy được: kiểm tra namespace Jakarta JMS

Ví dụ nhỏ dưới đây xác nhận chương trình được biên dịch với API jakarta.jms và module Spring JMS 6.2.19. Nó không kết nối broker, vì mục tiêu là kiểm tra namespace ở compile-time và runtime.

Cấu trúc:

~~~text
jakarta-jms-check/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── JmsNamespaceCheck.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>jakarta-jms-check</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>6.2.19</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/JmsNamespaceCheck.java

~~~java
package demo;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.jms.core.JmsTemplate;

public class JmsNamespaceCheck {

    public static void main(String[] args) {
        System.out.println(ConnectionFactory.class.getName());
        System.out.println(Message.class.getName());
        System.out.println(TextMessage.class.getName());
        System.out.println(JmsTemplate.class.getName());
    }
}
~~~

Chạy tại thư mục chứa pom.xml:

~~~shell
mvn -q compile exec:java -Dexec.mainClass=demo.JmsNamespaceCheck
~~~

Output:

~~~text
jakarta.jms.ConnectionFactory
jakarta.jms.Message
jakarta.jms.TextMessage
org.springframework.jms.core.JmsTemplate
~~~

Kết quả xác nhận mã nguồn đang tham chiếu kiểu Jakarta Messaging và lớp tích hợp Spring JMS. Để kiểm tra kết nối thực tế, cần thêm JMS provider client, cấu hình ConnectionFactory và chạy test gửi/nhận với broker.

## 11. Dùng công cụ hỗ trợ migration

Một số công cụ có thể giúp tìm và chuyển đổi source/dependency:

**OpenRewrite:** có recipe migration cho Spring Boot và Jakarta EE, hỗ trợ đổi package import, cấu hình và dependency trong các trường hợp đã được recipe bao phủ.

**Spring Boot Migrator:** hỗ trợ phân tích và gợi ý một số thay đổi khi nâng cấp ứng dụng Spring Boot.

**IntelliJ IDEA:** có chức năng hỗ trợ migration package và dependency.

**Eclipse Transformer:** có thể chuyển đổi bytecode, resource hoặc archive theo quy tắc namespace trong một số tình huống cần xử lý thư viện chưa có bản Jakarta.

Các công cụ này hỗ trợ công việc cơ học. Chúng không thể tự xác nhận JMS provider, broker, transaction, acknowledgment và failover đang hoạt động đúng. Luôn xem diff, kiểm tra dependency tree, biên dịch và chạy integration test sau khi chuyển đổi.

## 12. Những lỗi và nhầm lẫn phổ biến

**Chỉ đổi import nhưng giữ client cũ:** code có thể không biên dịch hoặc runtime không thể nạp kiểu Jakarta. Nâng provider client cùng lúc.

**Chỉ đổi dependency nhưng không biên dịch lại:** bytecode cũ vẫn chứa tên lớp javax.jms. Cần build lại tất cả module phụ thuộc.

**Thêm cả hai API để tránh lỗi compile:** hai namespace là hai bộ kiểu riêng biệt. Dependency cũ có thể được kéo vào qua thư viện khác; hãy tìm và xử lý nguồn phụ thuộc đó.

**Đổi toàn bộ javax thành jakarta:** một số package thuộc Java SE vẫn giữ javax, chẳng hạn javax.sql và javax.naming. Chỉ thay package đã được chuyển theo đặc tả.

**Nghĩ Spring package cũng đổi:** org.springframework.jms vẫn là package của Spring. Chỉ kiểu JMS API được tham chiếu chuyển sang jakarta.jms.

**Nghĩ đổi namespace làm thay đổi protocol broker:** namespace là tên kiểu Java. Tương thích giao thức và khả năng kết nối phụ thuộc provider client và broker.

**Nghĩ API compile thành công nghĩa là migration hoàn tất:** compile không kiểm tra được kết nối, quyền truy cập, transaction, acknowledgment, redelivery, durable subscription hay failover.

**Nâng Spring mà quên Java:** Spring Framework 6.x yêu cầu Java 17 trở lên. Build JDK và runtime phải thống nhất.

**Quên các thư viện nội bộ:** một module chung hoặc adapter cũ có thể vẫn xuất ra chữ ký javax.jms. Phải nâng hoặc biên dịch lại tất cả module có tương tác JMS trực tiếp.

## 13. Checklist trước khi hoàn tất migration

1. Spring Framework/Boot và JDK đã ở phiên bản tương thích.
2. Mọi import JMS trong source và test đã chuyển sang jakarta.jms.
3. Dependency tree không còn javax.jms-api ngoài trường hợp phụ thuộc được cô lập có chủ đích.
4. JMS provider client hỗ trợ Jakarta Messaging và tương thích broker/server.
5. ConnectionFactory, Destination, JNDI và cấu hình bảo mật hoạt động.
6. Spring JmsTemplate và @JmsListener vẫn được cấu hình đúng.
7. MessageConverter xử lý đúng payload cũ và mới.
8. Queue, Topic, selector, durable/shared subscription hoạt động đúng.
9. Transaction, acknowledgment, rollback, redelivery và DLQ đã được kiểm thử.
10. Request/reply, correlation ID, timeout và retry vẫn hoạt động.
11. Không có lỗi ClassNotFoundException, ClassCastException, NoSuchMethodError hoặc LinkageError.
12. Integration test chạy qua broker tương thích trong môi trường gần production.
13. Có kế hoạch triển khai hỗn hợp client cũ/mới nếu cần rolling deployment.

## 14. Ghi nhớ

- javax.jms thuộc thế hệ Java EE/JMS 2.0; jakarta.jms thuộc Jakarta Messaging 3.x.
- Jakarta EE 9 thực hiện thay đổi namespace và không tương thích source/binary với API Java EE cũ.
- Spring Framework 5.3 dùng thế hệ javax.jms; Spring Framework 6.x dùng jakarta.jms và yêu cầu Java 17 trở lên.
- Spring Boot 2.7 thuộc thế hệ Spring 5.3; Spring Boot 3.x thuộc thế hệ Spring 6.x và Jakarta.
- Spring package org.springframework.jms vẫn giữ nguyên; các kiểu JMS được import từ jakarta.jms.
- Cần nâng API dependency và JMS provider client tương thích, đồng thời kiểm tra broker/server và runtime.
- Không thay toàn bộ javax một cách máy móc vì nhiều package Java SE vẫn giữ namespace này.
- Biên dịch thành công chưa đủ; phải kiểm thử với broker thật về gửi/nhận, transaction, acknowledgment, subscription, redelivery và failover.

## Tài liệu tham khảo

- [Jakarta EE 9 Platform Specification — Namespace and backward compatibility](https://jakarta.ee/specifications/platform/9/jakarta-platform-spec-9.html)
- [Jakarta Messaging — Các phiên bản 2.0, 3.0 và 3.1](https://jakarta.ee/specifications/messaging/)
- [Spring Framework 6.0 Release Notes — Baseline upgrades](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.0-Release-Notes)
- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
- [Spring Framework 6.2 — JMS Integration](https://docs.spring.io/spring-framework/reference/6.2/integration/jms.html)
