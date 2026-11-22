# Lỗi classpath javax/jakarta và tính năng JMS chưa được provider hỗ trợ

> **Chương:** Chẩn đoán sự cố  
> **Mô-đun:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — tìm hiểu Apache ActiveMQ Classic và Artemis trong giao tiếp bất đồng bộ bằng queue, topic, routing và JMS; thực hành producer/consumer Java, acknowledgment, transaction, redelivery, DLQ, bảo mật và vận hành broker đáng tin cậy.  
> **Mục tiêu:** Chẩn đoán lỗi do trộn `javax.jms` với `jakarta.jms`, lệch API/provider hoặc classloader; phân biệt lỗi nạp lớp với tính năng JMS 2.0/Jakarta Messaging chưa được triển khai; chọn đúng client artifact cho Artemis, Classic và Spring; kiểm chứng feature ở đúng phiên bản broker/client trước khi đưa vào production.

## 1. Hai nhóm lỗi có biểu hiện gần giống nhưng nguyên nhân khác nhau

Một ứng dụng Java có thể biên dịch thành công nhưng lỗi ngay khi khởi động hoặc chỉ lỗi khi gọi một phương thức JMS mới. Cần tách hai nhóm:

1. **Lỗi namespace/classpath/linkage:** ứng dụng và provider dùng hai API binary khác nhau, thiếu API JAR, có nhiều phiên bản API/provider hoặc classloader nạp sai class.
2. **Lỗi capability của provider:** method có trong API và code biên dịch được, nhưng provider/version chưa hỗ trợ đầy đủ tính năng hoặc chỉ hỗ trợ một phần semantics.

Ví dụ: ứng dụng dùng Spring 6, import `jakarta.jms.ConnectionFactory` nhưng runtime lại nạp client Classic cũ triển khai `javax.jms.ConnectionFactory`. Đây là lỗi tương thích kiểu dữ liệu, không phải broker từ chối kết nối. Ngược lại, ứng dụng dùng đúng Jakarta API và kết nối thành công, nhưng gọi asynchronous send với `CompletionListener` trên một phiên bản Classic chưa triển khai tính năng đó; đây là lỗi capability.

| Dấu hiệu | Nhóm lỗi thường gặp | Điểm bắt đầu điều tra |
| --- | --- | --- |
| `package jakarta.jms does not exist` khi compile | Thiếu Jakarta API hoặc dependency client sai | Compile classpath, artifact và imports |
| `NoClassDefFoundError: javax/jms/ConnectionFactory` | Runtime thiếu Javax API | Runtime dependency tree và classloader |
| `ClassCastException` giữa hai ConnectionFactory | Trộn namespace hoặc classloader | Kiểu thực tế của factory và nguồn JAR |
| `NoSuchMethodError` / `AbstractMethodError` | API/provider binary version lệch | Dependency tree, duplicate JAR, provider version |
| `UnsupportedOperationException` khi gọi method JMS mới | Provider chưa hỗ trợ feature | Feature matrix của đúng provider/version |
| `JMSException` / `JMSRuntimeException` | Lỗi provider, transport, auth, destination hoặc feature | Error code, linked exception, broker log |
| Kết nối được nhưng delay/async/shared consumer không đúng kỳ vọng | Feature chưa hỗ trợ hoặc semantics khác | Integration test đo hành vi thực tế |

**Không xử lý mọi lỗi JMS bằng cách đổi version API.** Nếu lỗi là provider chưa hỗ trợ feature, thêm JAR API mới chỉ làm method xuất hiện lúc compile; nó không tự bổ sung implementation vào provider.

## 2. `javax.jms` và `jakarta.jms` là hai namespace binary khác nhau

### 2.1. Package name là một phần của kiểu dữ liệu JVM

Trước Jakarta EE 9, JMS API sử dụng package `javax.jms`. Từ Jakarta Messaging, package đổi thành `jakarta.jms`.

```text
javax.jms.ConnectionFactory
jakarta.jms.ConnectionFactory
```

Hai tên trên đại diện cho **hai class/interface khác nhau** trong JVM. Chúng có thể có method tương tự và cùng khái niệm nghiệp vụ, nhưng không thể cast hoặc truyền trực tiếp cho nhau.

Ví dụ:

```java
javax.jms.ConnectionFactory legacyFactory = obtainLegacyFactory();

// Không thể gán trực tiếp sang Jakarta API:
jakarta.jms.ConnectionFactory jakartaFactory = legacyFactory;
```

Đoạn code không biên dịch. Nếu framework hoặc reflection tạo object rồi ép kiểu ở runtime, lỗi tương đương có thể xuất hiện dưới dạng `ClassCastException`.

Việc đổi import không biến implementation Javax thành implementation Jakarta. Phải chọn **provider client artifact được biên dịch cho đúng namespace**.

### 2.2. Namespace API không phải protocol trên dây

JMS là API lập trình Java. Wire protocol do client và broker sử dụng có thể là OpenWire, Artemis Core hoặc protocol khác.

Artemis triển khai JMS facade ở phía client: thao tác qua `jakarta.jms` hoặc `javax.jms` được chuyển thành thao tác Core client trước khi gửi tới broker. Broker Artemis xử lý protocol/core operation, không nhận đối tượng Java `jakarta.jms.ConnectionFactory` qua mạng.

Điều này giải thích vì sao:

- Một broker Artemis có thể phục vụ nhiều loại client/protocol.
- Hai ứng dụng dùng hai namespace JMS khác nhau vẫn có thể kết nối cùng broker bằng client artifact tương ứng.
- Nhưng trong **cùng một JVM/classloader graph**, không được truyền factory/session/message Javax sang code yêu cầu Jakarta hoặc ngược lại.
- Embedded broker, in-VM transport và remote client có thể có ràng buộc khác nhau vì broker và client cùng chia sẻ classpath.

Không suy ra rằng mọi phiên bản client đều tương thích với mọi phiên bản broker. Namespace và wire-protocol compatibility là hai phép kiểm tra riêng.

### 2.3. Dependency API tương ứng

| API | Maven coordinates | Import |
| --- | --- | --- |
| JMS 2.0 / Java EE namespace | `javax.jms:javax.jms-api` | `javax.jms.*` |
| Jakarta Messaging 3.1 | `jakarta.jms:jakarta.jms-api` | `jakarta.jms.*` |

Thông thường provider client kéo API phù hợp theo dependency transitive. Nếu tự khai báo API, phải dùng đúng namespace và version mà provider/framework hỗ trợ.

**Không thêm cả hai API để “thử cho chạy”.** Hai artifact có thể cùng tồn tại về mặt classpath, nhưng chúng không làm implementation của namespace này tương thích với namespace kia. Một số hệ thống lớn có thể cô lập hai ứng dụng bằng classloader riêng; đó không phải lý do để trộn hai API trong cùng module ứng dụng.

## 3. Chọn đúng client artifact cho Artemis và ActiveMQ Classic

### 3.1. Apache ActiveMQ Artemis

Artemis cung cấp client artifact riêng cho hai namespace:

| Artifact | API mà ứng dụng import | Trường hợp dùng |
| --- | --- | --- |
| `org.apache.activemq:artemis-jms-client` | `javax.jms` | Ứng dụng JMS 2.0 Javax |
| `org.apache.activemq:artemis-jakarta-client` | `jakarta.jms` | Ứng dụng Jakarta Messaging |

Ví dụ Maven cho Jakarta:

```xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-client</artifactId>
    <version>2.42.0</version>
</dependency>
```

Ví dụ Maven cho Javax:

```xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jms-client</artifactId>
    <version>2.42.0</version>
</dependency>
```

`2.42.0` là phiên bản minh họa theo tài liệu client; hãy pin version phù hợp với broker/server đang vận hành và kiểm tra release notes trước khi nâng cấp. **Chọn một trong hai artifact cho một ứng dụng**, không khai báo đồng thời.

Ví dụ import Jakarta:

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
```

Ví dụ import Javax dùng cùng lớp provider nhưng namespace API khác:

```java
import javax.jms.ConnectionFactory;
import javax.jms.JMSContext;
import javax.jms.Queue;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
```

Không copy import Jakarta sang project đang dùng `artemis-jms-client` hoặc ngược lại. Nếu có JNDI, kiểu interface trả về từ lookup cũng phải khớp API client đang sử dụng.

### 3.2. ActiveMQ Classic 5.x và 6.x

Artifact của Classic thay đổi theo major release:

| Dòng Classic | Artifact thường gặp | Namespace | Lưu ý |
| --- | --- | --- | --- |
| 5.x | `activemq-client` | `javax.jms` | Client truyền thống; hỗ trợ JMS 1.1 và một phần JMS 2.0 tùy release |
| 5.18.1+ | `activemq-client-jakarta` | `jakarta.jms` | Module chuyển tiếp cho Jakarta client; chỉ remote client, không dùng chung JVM với Classic broker/client Javax |
| 6.x | `activemq-client` | `jakarta.jms` | Namespace Jakarta là mặc định; hỗ trợ Jakarta Messaging/JMS 2.0 theo ma trận feature từng release |

Ví dụ Classic 5.x với Javax:

```xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>activemq-client</artifactId>
    <version>5.18.3</version>
</dependency>
```

Ví dụ module Jakarta chuyển tiếp trên Classic 5.18.x:

```xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>activemq-client-jakarta</artifactId>
    <version>5.18.3</version>
</dependency>
```

Ví dụ Classic 6.x dùng Jakarta:

```xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>activemq-client</artifactId>
    <version>6.0.0</version>
</dependency>
```

Các version trên chỉ minh họa cách chọn artifact theo nhánh; không phải khuyến nghị dùng bản cũ nhất hoặc bản mới nhất. Chọn bản còn được hỗ trợ và kiểm tra bảng tương thích hiện hành.

**Ràng buộc đặc biệt của `activemq-client-jakarta` trên Classic 5.18.x:** đây là module chuyển tiếp cho client Jakarta kết nối broker từ xa. Không nạp nó cùng `activemq-client` Javax hoặc embedded broker Classic dùng Javax trong cùng JVM. Với embedded broker/VM transport, phải dùng tổ hợp namespace được hỗ trợ bởi chính broker đó.

### 3.3. Spring Framework và Spring Boot

Spring JMS cũng có namespace theo major line:

| Nền tảng | JMS namespace | Hệ quả |
| --- | --- | --- |
| Spring Framework 5.x / Spring Boot 2.x | `javax.jms` | Chọn provider client Javax |
| Spring Framework 6.x / Spring Boot 3.x | `jakarta.jms` | Chọn provider client Jakarta |
| Spring Framework 7.x | `jakarta.jms` | Tiếp tục dùng Jakarta API; vẫn kiểm tra provider version |

Ví dụ Spring 6/Boot 3 với Artemis:

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class MessagingConfiguration {

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        return new JmsTemplate(connectionFactory);
    }
}
```

Nếu compiler báo không thể chuyển `ActiveMQConnectionFactory` sang `jakarta.jms.ConnectionFactory`, kiểm tra provider artifact trước khi thay code Spring. Không giải quyết bằng cách cast thủ công.

Trong application server, kiểm tra JMS API do container cung cấp. Nếu container đã export Jakarta Messaging, việc đóng gói thêm API không tương thích có thể tạo classloader conflict. Chỉ dùng Maven scope `provided` khi runtime thực sự cung cấp đúng API/provider theo deployment contract.

## 4. Nhận diện lỗi theo giai đoạn compile, load và invoke

### 4.1. Compile-time: package không tồn tại hoặc method không tìm thấy

Ví dụ:

```text
package jakarta.jms does not exist
cannot find symbol: class JMSContext
method setDeliveryDelay(long) cannot be found
```

Kiểm tra:

1. Code import đúng namespace với provider artifact chưa?
2. Dependency có nằm trong compile classpath không?
3. Framework/BOM có loại dependency do exclusion không?
4. Version API có chứa method đang dùng không?
5. IDE và Maven/Gradle có đang dùng cùng dependency graph không?

Nếu code dùng `JMSContext` nhưng project chỉ có JMS 1.1 API, lỗi là compile dependency. Nếu API có method nhưng provider runtime cũ, code vẫn có thể compile và lỗi xuất hiện ở giai đoạn invoke.

### 4.2. Runtime: đọc đúng exception

| Exception/error | Ý nghĩa thường gặp | Cách xử lý |
| --- | --- | --- |
| `ClassNotFoundException` | Class được tìm bằng tên nhưng classloader không tìm thấy | Kiểm tra classpath/classloader |
| `NoClassDefFoundError` | JVM cần class lúc link/load nhưng runtime không có hoặc khởi tạo thất bại | Kiểm tra API/provider JAR và lỗi khởi tạo trước đó |
| `ClassCastException` | Object không implement đúng interface class đang ép kiểu; có thể khác namespace hoặc classloader | In tên class, loader và code source |
| `NoSuchMethodError` | Bytecode gọi method không tồn tại trên class được nạp | Lệch API/provider version hoặc duplicate JAR |
| `AbstractMethodError` | Implementation runtime không cung cấp method mà caller mong đợi | API mới hơn implementation hoặc binary skew |
| `UnsupportedOperationException` | Method có trong API nhưng provider chủ động báo không hỗ trợ | Đối chiếu feature matrix và chọn fallback |
| `JMSException` / `JMSRuntimeException` | Lỗi JMS tổng quát/provider/runtime | Đọc errorCode, linked exception và broker log |
| `InvalidDestinationException` | Destination không hợp lệ/không tồn tại theo provider | Kiểm tra address/queue, auto-create và mapping |
| `JMSSecurityException` | Authentication/authorization | Kiểm tra credential và SEND/CONSUME permission |

**`JMSRuntimeException` không tự động có nghĩa feature unsupported.** Nó cũng có thể đại diện lỗi mạng, transaction, authentication hoặc provider. Chỉ phân loại unsupported khi exception type, error code hoặc tài liệu provider xác nhận.

Với `JMSException`, ghi lại:

```java
System.err.println("message=" + exception.getMessage());
System.err.println("errorCode=" + exception.getErrorCode());
System.err.println("linked=" + exception.getLinkedException());
```

Không chỉ log stack trace ngoài cùng rồi bỏ qua linked exception. Nguyên nhân thực có thể là `NoClassDefFoundError`, lỗi transport hoặc server trả về.

### 4.3. Bẫy duplicate classloader

Ngay cả khi hai JAR có cùng class name, JVM vẫn coi class được nạp bởi hai classloader khác nhau là hai kiểu khác nhau. Điều này thường gặp khi:

- Ứng dụng đóng gói JMS API nhưng application server cũng export API.
- Plugin/OSGi module mang bản client riêng.
- Fat JAR có cả dependency trực tiếp và bản lồng trong thư viện khác.
- Container dùng parent-first/child-first khác nhau giữa module.

Thông báo `com.example.Foo cannot be cast to com.example.Foo` thường là dấu hiệu hai classloader. Ghi tên classloader và code source để biết class đến từ đâu; không chỉ xóa ngẫu nhiên một JAR.

## 5. Kiểm tra dependency tree trước khi sửa code

### 5.1. Maven

Chạy tại thư mục module ứng dụng:

```bash
mvn dependency:tree -Dverbose -Dincludes=javax.jms:javax.jms-api,jakarta.jms:jakarta.jms-api,org.apache.activemq:*,org.apache.activemq.artemis:*
```

Đọc kết quả để xác định:

- Có bao nhiêu phiên bản `javax.jms-api` hoặc `jakarta.jms-api`?
- Provider client artifact nào thực sự được resolve?
- Dependency nào kéo thêm Classic client trong ứng dụng Artemis (hoặc ngược lại)?
- Có dependency bị `omitted for conflict` không?
- Scope runtime có khác scope compile không?

Xem effective POM khi dependency management/exclusion đến từ parent/BOM:

```bash
mvn help:effective-pom
```

Nếu dependency tree chỉ có một artifact nhưng lỗi vẫn xảy ra, kiểm tra JAR được đóng gói trong executable/fat JAR hoặc thư viện do application server cung cấp.

### 5.2. Gradle

Xem runtime graph:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Truy vết một API cụ thể:

```bash
./gradlew dependencyInsight --dependency jakarta.jms-api --configuration runtimeClasspath
./gradlew dependencyInsight --dependency javax.jms-api --configuration runtimeClasspath
```

Kiểm tra thêm configuration mà task chạy thực tế sử dụng. `testRuntimeClasspath` có thể khác `runtimeClasspath`; test pass không chứng minh production artifact có cùng classpath.

### 5.3. Kiểm tra nội dung JAR và class được nạp

Với executable JAR hoặc thư viện nghi ngờ:

```powershell
jar tf target/application.jar | Select-String 'javax/jms|jakarta/jms|activemq'
```

Với JDK 17, bật log class loading để xem class được nạp từ đâu:

```powershell
java -Xlog:class+load=info -jar target/application.jar
```

Có thể lọc log theo `javax.jms`, `jakarta.jms` hoặc tên provider. Với fat JAR có nested JAR, cần kiểm tra cả thư viện lồng bên trong; lệnh `jar tf` trên archive ngoài chỉ cho biết tên nested JAR, không liệt kê nội dung của từng JAR con.

## 6. In thông tin API và provider tại runtime

`ConnectionMetaData` giúp ghi lại provider name/version và JMS API version của **kết nối đang dùng**. Nó cũng cung cấp danh sách JMSX properties được hỗ trợ. Đây là bước quan trọng để so log của máy local, staging và production.

Ví dụ Jakarta JMS:

```java
package example.messaging;

import java.security.CodeSource;
import java.util.Enumeration;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.ConnectionMetaData;
import jakarta.jms.JMSException;

public final class JmsRuntimeDiagnostics {

    private JmsRuntimeDiagnostics() {}

    public static void print(ConnectionFactory factory) throws JMSException {
        printClassOrigin(ConnectionFactory.class);
        printClassOrigin(factory.getClass());

        try (Connection connection = factory.createConnection()) {
            ConnectionMetaData metadata = connection.getMetaData();

            System.out.printf(
                "provider=%s providerVersion=%s jmsVersion=%s api=%d.%d%n",
                metadata.getJMSProviderName(),
                metadata.getProviderVersion(),
                metadata.getJMSVersion(),
                metadata.getJMSMajorVersion(),
                metadata.getJMSMinorVersion()
            );

            Enumeration<?> names = metadata.getJMSXPropertyNames();
            while (names.hasMoreElements()) {
                System.out.println("JMSX=" + names.nextElement());
            }
        }
    }

    private static void printClassOrigin(Class<?> type) {
        CodeSource source = type.getProtectionDomain().getCodeSource();
        String location = source == null
                ? "<container or bootstrap classloader>"
                : source.getLocation().toString();

        System.out.printf(
            "class=%s loader=%s source=%s%n",
            type.getName(),
            type.getClassLoader(),
            location
        );
    }
}
```

Gọi helper với factory đã được cấu hình:

```java
ActiveMQConnectionFactory factory =
        new ActiveMQConnectionFactory("tcp://localhost:61616");

JmsRuntimeDiagnostics.print(factory);
```

Trong ví dụ thật, tạo factory theo đúng constructor/client API của provider và truyền credential qua cấu hình an toàn. Không ghi password hoặc token vào log.

**Giới hạn của `ConnectionMetaData`:**

- `getJMSMajorVersion()`/`getJMSMinorVersion()` cho biết phiên bản JMS/Jakarta Messaging mà provider khai báo hỗ trợ.
- `getJMSProviderName()`/`getProviderVersion()` giúp nhận diện implementation.
- `getJMSXPropertyNames()` chỉ liệt kê JMSX properties được hỗ trợ.
- Metadata **không cung cấp một API chuẩn dạng `supports(DELIVERY_DELAY)`** để hỏi mọi optional feature.

Vì vậy provider báo JMS 2.0 hoặc Jakarta Messaging 3.1 không chứng minh mọi tính năng optional đã được triển khai. Phải kiểm tra ma trận chính thức và chạy integration test cho đúng method/semantics ứng dụng cần.

## 7. Tính năng JMS có trong API nhưng provider có thể chưa hỗ trợ

### 7.1. JMS 2.0/Jakarta Messaging bổ sung API nào?

Một số khả năng quan trọng được thêm vào simplified API và các phiên bản JMS mới:

| Feature | API tiêu biểu | Ý nghĩa |
| --- | --- | --- |
| Simplified API | `JMSContext`, `JMSProducer`, `JMSConsumer` | Kết hợp connection/session và API gửi/nhận gọn hơn |
| Asynchronous send | `CompletionListener` | Nhận callback khi provider hoàn thành xử lý send theo contract |
| Delivery delay | `JMSProducer.setDeliveryDelay()` | Yêu cầu broker/provider trì hoãn thời điểm giao message |
| Shared topic consumer | `createSharedConsumer()` | Nhiều consumer cùng chia sẻ một subscription |
| Shared durable consumer | `createSharedDurableConsumer()` | Subscription bền vững có thể được chia sẻ |
| Typed body receive | `receiveBody(Class<T>)` | Nhận body theo kiểu mong đợi |
| XA/simplified API additions | Các phương thức XA và API liên quan | Tích hợp transaction theo khả năng provider/container |

Một số thao tác trong JMS là optional hoặc có hỗ trợ khác nhau theo provider/version. Tên method tồn tại trong interface API không có nghĩa implementation cụ thể đã thực hiện đầy đủ.

### 7.2. Classic có lịch sử hỗ trợ một phần

ActiveMQ Classic công bố hỗ trợ một phần JMS 2.0/Jakarta Messaging ở các nhánh chuyển tiếp. Tài liệu chính thức nêu những ví dụ từng chưa được hỗ trợ gồm:

- Async send với `CompletionListener`.
- Producer delivery delay.
- Shared topic consumers.
- Tùy chọn hiếm dùng như tắt JMS message ID.

Theo tiến độ release, một số method được bổ sung trong các bản sau; do đó không dùng một kết luận chung cho mọi bản 5.x hoặc 6.x. Ví dụ bảng hỗ trợ của Classic ghi nhận `receiveBody()` được hoàn thành ở một nhánh release cụ thể, trong khi async send/shared topic/delivery delay có mốc triển khai khác. **Đọc bảng feature support và release notes của đúng version**, không lấy kết quả thử trên máy dev làm hợp đồng cho production.

### 7.3. Artemis có API JMS facade và Core API riêng

Artemis cung cấp JMS client cho Javax/Jakarta và Core client API. JMS là lớp API tiêu chuẩn; Core API mở thêm chức năng riêng của Artemis. Nếu một tính năng không có trong JMS hoặc semantics JMS không đủ, có thể cân nhắc Core API nhưng cần chấp nhận:

- Code phụ thuộc Artemis, giảm tính portable sang broker khác.
- Cần integration test riêng cho Artemis version/protocol.
- Không thể giả định ứng dụng dùng Core API sẽ chạy với ActiveMQ Classic JMS client.
- Không chuyển tùy tiện message/session object giữa JMS facade và Core API.

Ưu tiên JMS cho nghiệp vụ cần portable. Chỉ dùng extension/Core API khi có yêu cầu thực tế và đã cô lập adapter theo provider.

## 8. Kiểm chứng một feature an toàn

### 8.1. Đừng chỉ kiểm tra method có tồn tại

Reflection có thể xác nhận API JAR có method:

```java
boolean methodExists;
try {
    jakarta.jms.JMSProducer.class.getMethod("setDeliveryDelay", long.class);
    methodExists = true;
} catch (NoSuchMethodException absentFromApi) {
    methodExists = false;
}
```

Nhưng điều này chỉ chứng minh **API đang compile có method**. Nó không chứng minh provider runtime thực thi method đó. Một provider có thể ném `UnsupportedOperationException`, bỏ qua tùy chọn hoặc chỉ hỗ trợ một phần semantics.

Phải kiểm tra ba lớp:

1. **API surface:** method có trong JMS API version đang compile?
2. **Provider implementation:** provider/version có công bố hỗ trợ?
3. **Observed behavior:** integration test với broker thật chứng minh semantics đúng?

### 8.2. Probe delivery delay trên destination riêng

Dùng queue kiểm thử đã provision và không chứa message nghiệp vụ. Ghi thời điểm gửi và thời điểm consumer nhận:

```java
import java.time.Instant;

import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

public final class DeliveryDelayProbe {

    private DeliveryDelayProbe() {}

    public static void sendProbe(
            JMSContext context, Queue probeQueue, long delayMillis) {
        TextMessage message = context.createTextMessage("compatibility-probe");
        message.setStringProperty("probeId", "delivery-delay-001");
        message.setLongProperty("sentAtEpochMs", Instant.now().toEpochMilli());

        try {
            context.createProducer()
                    .setDeliveryDelay(delayMillis)
                    .send(probeQueue, message);
        } catch (UnsupportedOperationException unsupported) {
            throw new IllegalStateException(
                "Provider does not implement JMS delivery delay", unsupported);
        }
    }
}
```

Phần test consumer phải ghi `receivedAtEpochMs` và assert message không được giao trước `sentAtEpochMs + delayMillis`, đồng thời có timeout để test không treo. Không dùng queue production. Một provider có thể trả giá trị getter mặc định hoặc có behavior khác theo release; **thời điểm giao thực tế mới là assertion quan trọng**.

### 8.3. Probe async send và shared consumer

Async send trên Jakarta JMS:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import jakarta.jms.CompletionListener;
import jakarta.jms.JMSProducer;
import jakarta.jms.Message;
import jakarta.jms.Queue;

CountDownLatch completed = new CountDownLatch(1);
AtomicReference<Exception> failure = new AtomicReference<>();

JMSProducer producer = context.createProducer();

try {
    producer.send(probeQueue, context.createTextMessage("async-probe"),
        new CompletionListener() {
            @Override
            public void onCompletion(Message message) {
                completed.countDown();
            }

            @Override
            public void onException(Message message, Exception exception) {
                failure.set(exception);
                completed.countDown();
            }
        });
} catch (UnsupportedOperationException unsupported) {
    throw new IllegalStateException(
        "Provider does not support CompletionListener async send", unsupported);
}

if (!completed.await(10, TimeUnit.SECONDS)) {
    throw new IllegalStateException("No async completion callback before timeout");
}
if (failure.get() != null) {
    throw new IllegalStateException("Async send failed", failure.get());
}
```

Chạy test trên queue riêng, có timeout và cleanup. Callback hoàn tất không đồng nghĩa business transaction ở database đã commit; chỉ kết luận theo semantics JMS/provider đã công bố.

Shared consumer có thể thử bằng subscription tạm trong integration test:

```java
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Topic;

Topic topic = context.createTopic("compat.probe.topic");

try (JMSConsumer consumer =
         context.createSharedConsumer(topic, "compat-probe-subscription")) {
    // Test đăng ký và nhận message bằng hai consumer cùng subscription.
} catch (UnsupportedOperationException unsupported) {
    throw new IllegalStateException(
        "Provider does not support shared topic consumers", unsupported);
}
```

Để kiểm chứng semantics chia tải, cần mở **hai consumer cùng subscription name**, gửi một số message có ID riêng và xác nhận mỗi message được phân phối một lần trong nhóm theo contract. Không dùng hai subscription name khác nhau: hai subscription độc lập có thể nhận bản sao riêng, không phải shared consumer.

Nếu dùng shared durable subscription, dọn subscription bằng API `unsubscribe` phù hợp sau khi tất cả consumer đã đóng. Không để probe tạo durable subscription rác trong broker.

### 8.4. Phân loại lỗi khi probe

- `UnsupportedOperationException`: provider đã báo rõ method chưa hỗ trợ; ghi feature/version và chọn fallback.
- `JMSRuntimeException`/`JMSException`: xem error code và linked exception. Có thể là destination, authorization, network, transaction hoặc provider error; không tự gắn nhãn unsupported.
- Timeout không có callback: điều tra callback path, connection health, executor và broker logs; timeout không tự chứng minh feature không được hỗ trợ.
- Method trả bình thường nhưng behavior không đúng: provider có thể chưa triển khai semantics đầy đủ; test phải fail và không bật feature trong production.

## 9. Ma trận tương thích phải được quản lý theo provider/version

Không có một cột “JMS 2.0 = tất cả tính năng hoạt động”. Lập ma trận theo ứng dụng và lưu cùng release artifact:

| Provider/client | Namespace | Feature cần dùng | Kết quả integration test | Quyết định |
| --- | --- | --- | --- | --- |
| Artemis client phiên bản đã pin | Jakarta | `JMSContext`, delay, shared consumer | PASS/FAIL theo test suite | Enable/disable |
| Classic client phiên bản đã pin | Javax | Async send, delivery delay | PASS/FAIL theo test suite | Enable/disable |
| Classic Jakarta transition client | Jakarta | Remote client và feature cần dùng | PASS/FAIL theo test suite | Enable/disable |
| Provider trong application server | Namespace do server cung cấp | XA, MDB, shared subscription | PASS/FAIL trong container thật | Enable/disable |

Một record capability có thể được lưu trong cấu hình ứng dụng:

```yaml
messaging:
  provider: activemq-classic
  providerVersion: "5.18.3"
  apiNamespace: javax
  features:
    jmsContext: true
    completionListenerAsyncSend: false
    deliveryDelay: false
    sharedTopicConsumer: false
```

Các giá trị trên chỉ là **ví dụ minh họa cho một capability profile**, không phải cam kết rằng mọi patch release có cùng trạng thái. Hãy tạo profile từ tài liệu chính thức và integration tests chạy trên đúng artifact.

Khi deploy, ứng dụng nên log provider name/version, namespace, feature profile và build ID. Nếu runtime provider khác profile đã kiểm chứng, fail fast hoặc cảnh báo rõ; đừng để một feature quan trọng chỉ thất bại khi có message production đầu tiên.

## 10. Phương án fallback phải giữ đúng semantics nghiệp vụ

| Feature không hỗ trợ | Fallback có thể dùng | Khác biệt phải chấp nhận |
| --- | --- | --- |
| `JMSContext` | API cổ điển `Connection`/`Session`/`MessageProducer`/`MessageConsumer` | Code dài hơn; vẫn dùng được JMS 1.1 style |
| Async send với `CompletionListener` | Synchronous send; hoặc executor riêng gọi synchronous send | Executor không tạo ra cùng provider callback/durability contract |
| Delivery delay | Scheduler/outbox phía ứng dụng; hoặc provider-native scheduled delivery trong adapter riêng | Phải quản lý retry, persistence và clock/deadline |
| Shared topic consumer | Một durable subscription riêng cho mỗi subscriber; hoặc chuyển sang queue nếu nghiệp vụ là competing consumers | Nhiều subscription nhận bản sao; queue có semantics phân phối khác topic |
| `receiveBody(Class<T>)` | `receive()` rồi kiểm tra `TextMessage`, `BytesMessage` hoặc kiểu body cụ thể | Code phải xử lý type conversion rõ ràng |
| Tắt JMS message ID | Chấp nhận ID do provider cấp; dùng application `eventId` riêng | Không phụ thuộc provider bỏ qua header chuẩn |
| Provider-specific extension | Adapter riêng cho từng provider | Tăng chi phí bảo trì và kiểm thử portability |

### 10.1. Fallback cho delivery delay

Nếu provider không hỗ trợ JMS delivery delay, không tự đặt một property tùy ý rồi giả định broker sẽ hiểu. Các lựa chọn:

- Ghi command vào database/outbox với trường `available_at`, worker chỉ publish khi đến hạn.
- Dùng scheduler có persistence và cơ chế retry.
- Dùng scheduled-delivery extension riêng của provider, đặt sau interface adapter và test trên broker thật.

Nếu yêu cầu là “không giao trước thời điểm X”, fallback phải kiểm chứng cả restart và failover; timer trong memory của một JVM không đủ cho lịch gửi bền vững.

### 10.2. Fallback cho shared topic consumer

Shared subscription và competing consumers trên queue không có cùng ngữ nghĩa:

- **Shared topic subscription:** nhóm consumer chia sẻ một subscription; mỗi message phù hợp được xử lý bởi một consumer trong nhóm.
- **Hai durable subscriptions riêng:** mỗi subscription nhận bản sao message độc lập; phù hợp cho hai hệ thống cần cùng sự kiện.
- **Queue:** message được phân phối cho một consumer trong nhóm; phù hợp work queue, không tự tạo bản sao cho nhiều subscriber độc lập.

Không chuyển topic sang queue chỉ để né `UnsupportedOperationException` nếu nghiệp vụ cần broadcast tới nhiều subscriber độc lập.

### 10.3. Fallback cho async send

Nếu `CompletionListener` không có, có thể dùng synchronous send trên worker executor để tránh chặn request thread. Tuy nhiên:

- Giới hạn kích thước executor và queue nội bộ để tạo backpressure.
- Xử lý exception trong worker, không nuốt lỗi.
- Không coi callback tự viết là provider completion callback.
- Định nghĩa retry/idempotency khi kết quả send không rõ sau network failure.
- Đo latency và shutdown behavior trước khi deploy.

## 11. Spring: tránh lỗi namespace ở ConnectionFactory và listener container

### 11.1. Kiểm tra kiểu mà Spring thực sự yêu cầu

Spring 6 dùng `jakarta.jms.ConnectionFactory`. Nếu provider factory chỉ implement `javax.jms.ConnectionFactory`, wiring có thể thất bại dù class provider tồn tại.

Lỗi thường thấy:

```text
BeanNotOfRequiredTypeException:
Bean named 'connectionFactory' is expected to be of type
'jakarta.jms.ConnectionFactory' but was actually of type
'org.apache.activemq.ActiveMQConnectionFactory'
```

Hãy in `factory.getClass().getInterfaces()` và code source, sau đó đối chiếu namespace interface mà class implement. Không ép kiểu hoặc tạo proxy chỉ để che mismatch.

### 11.2. Kiểm tra dependency alignment

Trong project Spring Boot, để dependency management của đúng Boot BOM quản lý Spring modules. Tránh tự pin `spring-jms` ở major khác với `spring-core`/`spring-context` và tránh thêm JMS API không khớp provider.

Ví dụ kiểm tra Maven:

```bash
mvn dependency:tree -Dverbose -Dincludes=org.springframework:*,javax.jms:*,jakarta.jms:*,org.apache.activemq:*,org.apache.activemq.artemis:*
```

Một ứng dụng Boot 3/Spring 6 cần provider client Jakarta. Ứng dụng Boot 2/Spring 5 cần tổ hợp Javax được hỗ trợ. Khi nâng Boot 2 lên Boot 3, phải cập nhật cả imports, provider artifact, API namespace, listener container integration và thư viện nội bộ có khai báo kiểu JMS.

### 11.3. Đừng dùng cache/pool để che lỗi provider

`CachingConnectionFactory`, pool hoặc JCA adapter có thể gọi thêm JMS methods để quản lý resource. Một provider JMS 1.1 hoặc provider JMS 2.0 partial có thể chạy được đường code cơ bản nhưng thất bại khi framework dùng `JMSContext`, shared consumer hoặc async send.

Nếu stack trace xuất hiện trong Spring infrastructure:

1. Xác định method JMS cuối cùng trước exception.
2. Xem Spring major/minor và provider client version.
3. Kiểm tra release notes của Spring xem có gọi API mới không.
4. Chạy integration test không qua pool/cache để cô lập provider.
5. Thử lại với đúng connection factory/pool được dùng production.

Không tắt cache/pool như giải pháp lâu dài nếu lỗi gốc là provider thiếu method; chỉ dùng nó như bước cô lập nguyên nhân.

## 12. Runbook chẩn đoán từ triệu chứng đến sửa lỗi

### Bước 1 — Thu thập thông tin

Ghi lại:

- JDK/JVM version.
- Spring Framework/Boot version.
- Broker product/version và topology (remote hay embedded).
- Provider client artifact/version.
- JMS API artifact/version và namespace import.
- Exception đầy đủ, linked exception và dòng code gây lỗi.
- Runtime class origin của `ConnectionFactory`, `JMSContext` và provider factory.

Không ghi credential, TLS private key hoặc message payload nhạy cảm vào ticket.

### Bước 2 — Xác nhận namespace thống nhất

Đối chiếu bốn điểm:

1. Imports trong source code.
2. JMS API trên compile classpath.
3. Provider artifact trên runtime classpath.
4. Kiểu JMS mà Spring/application server yêu cầu.

Bốn điểm phải cùng namespace cho một dependency path. Nếu có embedded broker, kiểm tra cả namespace của broker engine.

### Bước 3 — Xác nhận đúng artifact và version

- Artemis: chọn `artemis-jms-client` hoặc `artemis-jakarta-client`.
- Classic 5.x: chọn Javax client hoặc module Jakarta chuyển tiếp theo đúng deployment model.
- Classic 6.x: chọn `activemq-client` Jakarta.
- Spring: khớp Spring 5/Boot 2 với Javax; Spring 6/Boot 3 với Jakarta.
- Đọc compatibility/release notes của đúng version, không dựa vào một sample POM cũ.

### Bước 4 — Phân loại exception

- Thiếu class → dependency/classloader.
- Linkage error → binary version skew/duplicate JAR.
- Cast error → namespace/classloader.
- Unsupported operation → capability.
- JMS exception thông thường → đọc linked cause và broker log trước khi đổi API.

### Bước 5 — Chạy capability test riêng

Tạo queue/topic prefix `compat.probe`, credential test và message có marker riêng. Kiểm tra feature theo thứ tự:

1. Connect và đọc `ConnectionMetaData`.
2. Tạo queue producer/consumer cơ bản.
3. Gửi/nhận persistent message và ACK/transaction cơ bản.
4. Test `JMSContext` nếu ứng dụng cần.
5. Test async send/delivery delay/shared consumer nếu ứng dụng cần.
6. Đóng consumer/session/context và dọn resource probe.

Không chạy probe trên destination nghiệp vụ hoặc dùng message giả có thể bị consumer production xử lý.

### Bước 6 — Sửa và ngăn tái phát

- Loại dependency API/provider không đúng namespace.
- Đồng bộ BOM và loại duplicate JAR.
- Chọn fallback phù hợp semantics hoặc nâng provider tới version đã hỗ trợ.
- Thêm integration test vào pipeline cho từng feature bắt buộc.
- Ghi provider name/version và feature profile khi ứng dụng khởi động.

## 13. Ma trận triệu chứng và cách khắc phục

| Triệu chứng | Nguyên nhân khả dĩ | Cách khắc phục |
| --- | --- | --- |
| Compile không tìm thấy `jakarta.jms` | Đang dùng Javax client hoặc thiếu Jakarta API | Chọn Jakarta provider artifact |
| Runtime thiếu `javax.jms` | API Javax bị loại khỏi runtime | Kiểm tra transitive dependency và packaging |
| Spring 6 không nhận factory Classic 5 Javax | Spring cần Jakarta nhưng factory implement Javax | Dùng provider Jakarta client hoặc nhánh tương thích |
| Classic 5 embedded broker lỗi khi thêm Jakarta client | Trộn module Jakarta client với broker Javax cùng JVM | Dùng namespace Javax hoặc chuyển broker/client sang nhánh hỗ trợ Jakarta |
| `NoSuchMethodError` trên `JMSContext` | API/provider version lệch hoặc class cũ được nạp | Align API và provider, loại duplicate JAR |
| `UnsupportedOperationException` khi gọi async send | Provider/version chưa triển khai `CompletionListener` | Dùng sync send/executor hoặc nâng version đã hỗ trợ |
| Delivery delay getter trả 0 hoặc message đến ngay | Feature chưa triển khai đầy đủ hoặc provider không áp delay | Kiểm tra release matrix và đo thời điểm nhận |
| Shared topic consumer không tạo được | Provider chưa hỗ trợ shared subscriptions | Dùng subscription riêng hoặc topology queue theo đúng semantics |
| Feature test pass ở unit test nhưng fail production | Unit test dùng mock/embedded provider khác | Chạy test với đúng artifact và broker version production |
| Lỗi chỉ xuất hiện trong app server | Classloader/container cung cấp API khác với WAR/EAR | Kiểm tra module visibility, provided scope và server JMS integration |

## 14. Bài tập kiểm chứng

### Bài tập A — Namespace mismatch

Project dùng Spring 6 và import `jakarta.jms.ConnectionFactory`. Runtime dependency tree chỉ có `org.apache.activemq:activemq-client:5.18.3`.

**Yêu cầu:** Xác định vì sao Spring không nhận factory và chọn cách sửa theo mô hình remote hoặc embedded.

*Định hướng:* Classic 5.18.x client mặc định Javax; Spring 6 cần Jakarta. Với remote-only có thể xem module chuyển tiếp Jakarta nếu version hỗ trợ; embedded broker Javax không thể cùng JVM với module chuyển tiếp đó. Hoặc nâng sang dòng Classic Jakarta phù hợp.

### Bài tập B — Thiếu API hay provider thiếu feature?

Code compile với `JMSProducer.setDeliveryDelay()`, nhưng runtime ném `UnsupportedOperationException`.

**Yêu cầu:** Vì sao thêm `jakarta.jms-api` mới không giải quyết? Cần thu những thông tin nào?

*Định hướng:* API method tồn tại nhưng provider implementation không hỗ trợ. Thu provider name/version, client artifact, feature matrix, exception type và integration test result.

### Bài tập C — NoSuchMethodError

Application build thành công với JMS API 3.x nhưng runtime container nạp provider client cũ.

**Yêu cầu:** Phân biệt lỗi này với `ClassNotFoundException`; dùng công cụ nào để tìm JAR thực tế?

*Định hướng:* Class đã được tìm thấy nhưng method mà bytecode gọi không có trên class runtime; dùng dependency tree, `-Xlog:class+load=info`, code source và kiểm tra nested JAR.

### Bài tập D — Shared topic consumer

Ứng dụng muốn 4 worker cùng chia một subscription; provider không hỗ trợ `createSharedConsumer()`.

**Yêu cầu:** Có thể tạo bốn durable subscriptions khác tên không? Hành vi sẽ thay đổi thế nào?

*Định hướng:* Bốn subscription riêng có thể nhận bốn bản sao, không chia tải một subscription. Cân nhắc nâng provider hoặc dùng queue nếu nghiệp vụ thực sự là work distribution.

### Bài tập E — JMSContext không được hỗ trợ

Một provider cũ hỗ trợ JMS 1.1 nhưng application framework gọi `ConnectionFactory.createContext()`.

**Yêu cầu:** Viết hướng fallback mà không đổi semantics transaction/ACK.

*Định hướng:* Dùng `Connection`/`Session`, chọn đúng acknowledge mode hoặc transacted session, giữ lifecycle/commit/rollback tương đương; kiểm thử lại redelivery và exception behavior.

### Bài tập F — Provider metadata

`ConnectionMetaData` báo provider version và JMS major/minor là 2.0, nhưng async send vẫn unsupported.

**Yêu cầu:** Giải thích vì sao metadata không mâu thuẫn với lỗi và cần quản lý capability thế nào.

*Định hướng:* Metadata không liệt kê từng optional feature. Lập ma trận provider/version + integration tests, không dùng JMS major/minor làm capability flag duy nhất.

### Bài tập G — Runtime có cả Javax và Jakarta API

Fat JAR chứa cả `javax.jms-api` và `jakarta.jms-api`; ứng dụng dùng hai thư viện khác nhau.

**Yêu cầu:** Khi nào điều này có thể hợp lệ, khi nào gây lỗi?

*Định hướng:* Chỉ có thể cô lập nếu hai dependency graph/classloader độc lập và không truyền object qua ranh giới. Nếu cùng một ConnectionFactory được cast/tiêm qua framework namespace khác, lỗi type/linkage sẽ xảy ra.

### Bài tập H — Lỗi trong Spring listener container

`@JmsListener` khởi động được nhưng fail khi tạo consumer; native JMS sample dùng cùng broker vẫn chạy.

**Yêu cầu:** Những lớp nào cần so sánh?

*Định hướng:* Spring major/version, provider artifact, connection factory wrapper/pool, method được listener container gọi, API namespace, classloader và broker/client logs.

## 15. Checklist trước khi phát hành

- [ ] Namespace trong source/imports khớp provider client artifact.
- [ ] Runtime dependency tree không có provider/API version xung đột.
- [ ] Không dùng `activemq-client-jakarta` Classic 5.x cùng embedded broker/client Javax trong một JVM.
- [ ] Spring Framework/Boot major phù hợp namespace JMS.
- [ ] Đã ghi provider name/version và JMS API version khi khởi động.
- [ ] Đã đọc feature matrix/release notes của đúng provider version.
- [ ] Từng optional feature quan trọng có integration test với broker thật.
- [ ] Test fallback cho async send, delivery delay, shared consumers nếu ứng dụng phụ thuộc.
- [ ] Test transaction, ACK, redelivery và shutdown sau khi thay client artifact.
- [ ] Test runtime packaging/fat JAR/application server, không chỉ compile hoặc unit test.
- [ ] Không log credential, secret hoặc payload nhạy cảm trong diagnostic output.
- [ ] Feature unsupported được xử lý fail-fast/có fallback, không retry vô hạn như lỗi mạng tạm thời.

## 16. Tài liệu tham khảo chính thức

1. Apache ActiveMQ Classic — [JMS 2.0 và Jakarta Messaging support](https://activemq.apache.org/components/classic/documentation/jms2): artifact Javax/Jakarta, giới hạn module chuyển tiếp và trạng thái các feature như CompletionListener, delivery delay, shared consumers.
2. Apache ActiveMQ Classic — [New Features in 6.0](https://activemq.apache.org/components/classic/documentation/new-features-in-60): chuyển namespace Jakarta và thay đổi API/runtime.
3. Apache ActiveMQ Classic — [Download và version support matrix](https://activemq.apache.org/components/classic/download/): broker/client JMS API, Java và Spring version theo nhánh release.
4. Apache ActiveMQ Artemis — [The Client Classpath](https://artemis.apache.org/components/artemis/documentation/latest/client-classpath.html): chọn `artemis-jms-client` và `artemis-jakarta-client`.
5. Apache ActiveMQ Artemis — [General Concepts / Messaging APIs](https://artemis.apache.org/components/artemis/documentation/latest/): JMS facade, Core client API và protocol-agnostic broker.
6. Jakarta Messaging — [Specification 3.1](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): API, ConnectionMetaData, optional operations, exception handling và semantics.
7. Jakarta Messaging — [ConnectionMetaData API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/connectionmetadata): provider name/version, JMS API version và JMSX properties.
8. Spring Framework — [Spring 6 JMS connection package](https://docs.spring.io/spring-framework/docs/6.0.x/javadoc-api/org/springframework/jms/connection/package-summary.html): các abstraction JMS dùng Jakarta API.
9. Spring Framework — [CachingConnectionFactory](https://docs.spring.io/spring-framework/docs/6.0.23/javadoc-api/org/springframework/jms/connection/CachingConnectionFactory.html): cache/session lifecycle và yêu cầu JMS API runtime.
10. Maven — [Dependency Plugin: dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): truy vết dependency graph.
11. Gradle — [Viewing and debugging dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): dependencyInsight và runtime classpath.

> **Ghi nhớ:** `javax.jms` và `jakarta.jms` là hai hệ kiểu binary riêng. Chọn đúng client artifact, framework namespace và classloader trước khi điều tra broker. Sau khi kết nối thành công, vẫn phải xác minh từng feature theo provider/version: `ConnectionMetaData` chỉ cho biết phiên bản API/provider, không phải bảng capability. Hãy phân loại rõ lỗi classpath, linkage và `UnsupportedOperationException`; test hành vi thật trên broker tương ứng; chọn fallback giữ đúng semantics transaction, delivery và subscription của nghiệp vụ.
