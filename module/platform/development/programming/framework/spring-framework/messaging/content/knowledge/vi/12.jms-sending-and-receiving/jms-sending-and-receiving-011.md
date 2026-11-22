# Cấu hình explicitQosEnabled, deliveryMode, priority và timeToLive trong Spring JMS

Khi gửi message bằng JMS, producer có thể chỉ định ba thuộc tính QoS (Quality of Service):

- **deliveryMode:** yêu cầu provider lưu message bền vững hay cho phép gửi không bền vững.
- **priority:** mức ưu tiên của message, từ 0 đến 9.
- **timeToLive:** thời gian message còn hợp lệ, tính bằng milliseconds.

Trong Spring Framework, `JmsTemplate` cung cấp các setter để cấu hình ba giá trị này. Tuy nhiên, có một cờ quyết định các giá trị đó có thực sự được truyền vào thao tác gửi hay không: `explicitQosEnabled`.

Đây là điểm dễ gây lỗi cấu hình nhất: chỉ đặt `deliveryMode`, `priority` và `timeToLive` chưa đủ. Cần bật `explicitQosEnabled=true`, hoặc dùng `setQosSettings` để Spring bật cờ này tự động.

## 1. Bốn thuộc tính và ý nghĩa

### explicitQosEnabled

`explicitQosEnabled` điều khiển cách `JmsTemplate` gọi JMS `MessageProducer`:

- Khi `false`, Spring gọi `MessageProducer.send(message)`. Provider sử dụng QoS mặc định của producer.
- Khi `true`, Spring gọi `MessageProducer.send(message, deliveryMode, priority, timeToLive)`. Ba giá trị đã cấu hình trên template được truyền tường minh vào lần gửi.

Giá trị mặc định của `explicitQosEnabled` là `false`.

Vì vậy, nếu chỉ gọi:

```java
template.setPriority(8);
template.setTimeToLive(30_000);
```

thì các giá trị này được lưu trong `JmsTemplate`, nhưng chưa được dùng làm tham số QoS khi gửi nếu cờ explicit vẫn là `false`.

### deliveryMode

JMS định nghĩa hai hằng số trong `jakarta.jms.DeliveryMode`:

| Hằng số | Giá trị | Ý nghĩa |
| --- | ---: | --- |
| `DeliveryMode.PERSISTENT` | 2 | Yêu cầu provider lưu message vào bộ lưu trữ ổn định |
| `DeliveryMode.NON_PERSISTENT` | 1 | Không yêu cầu provider lưu message vào bộ lưu trữ ổn định |

Trong Spring có hai cách đặt:

```java
template.setDeliveryMode(DeliveryMode.PERSISTENT);
template.setDeliveryPersistent(true);
```

`setDeliveryPersistent(true)` tương đương chọn `PERSISTENT`; `false` tương đương `NON_PERSISTENT`.

Chọn persistent cho command hoặc event không được phép mất trong lúc provider vận chuyển. Chọn non-persistent cho dữ liệu có thể tái tạo hoặc có thể chấp nhận mất khi broker gặp sự cố. Delivery mode không thay thế transaction, acknowledgement hoặc idempotency ở phía consumer.

### priority

Priority là số nguyên từ 0 đến 9:

- `0`: thấp nhất.
- `9`: cao nhất.
- Mặc định JMS: `4`.

Ví dụ:

```java
template.setPriority(7);
```

Priority là gợi ý cho provider khi chọn message tiếp theo để giao. Nó không bảo đảm strict ordering hoặc preemption một message consumer đang xử lý. Broker có thể có policy riêng về việc áp dụng priority.

Nên định nghĩa quy ước priority trong ứng dụng, ví dụ 0–2 cho tác vụ nền, 3–4 cho công việc thông thường và 5–9 cho công việc cần xử lý sớm. Tránh gán mức cao nhất cho mọi message.

### timeToLive

TTL là thời hạn tồn tại của message, tính bằng milliseconds:

```java
template.setTimeToLive(30_000); // 30 giây
```

- `0`: message không hết hạn.
- `5_000`: hết hạn sau khoảng 5 giây.
- `60_000`: hết hạn sau khoảng 1 phút.

Provider dùng TTL để xác định thời điểm expiration. Message đã hết hạn trong lúc chờ giao nên được loại bỏ theo chính sách của provider. TTL không phải processing timeout: nó không dừng consumer nếu consumer đã nhận message và đang xử lý.

## 2. Giá trị mặc định của JmsTemplate

Trong Spring Framework 7.0.10, các giá trị mặc định của `JmsTemplate` là:

| Thuộc tính | Giá trị mặc định |
| --- | --- |
| `deliveryMode` | `DeliveryMode.PERSISTENT` (2) |
| `priority` | `4` |
| `timeToLive` | `0` |
| `explicitQosEnabled` | `false` |

Điểm cần hiểu là các giá trị getter này không đồng nghĩa Spring luôn truyền chúng vào producer. Khi `explicitQosEnabled=false`, Spring gọi overload `send(message)`, để producer/provider sử dụng QoS mặc định của nó.

JMS producer mặc định thường dùng persistent, priority 4 và TTL 0. Tuy vậy, broker có thể áp dụng policy riêng hoặc ghi đè QoS do client yêu cầu. Nếu cần bảo đảm ứng dụng gửi đúng một bộ QoS cụ thể, hãy bật explicit và kiểm tra hành vi trên provider thật.

## 3. Cấu hình tường minh bằng các setter

Ví dụ cấu hình một template dành cho queue đơn hàng:

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import org.springframework.jms.core.JmsTemplate;

JmsTemplate template = new JmsTemplate(connectionFactory);

template.setDeliveryMode(DeliveryMode.PERSISTENT);
template.setPriority(7);
template.setTimeToLive(60_000);

// Bật để Spring truyền ba giá trị trên vào MessageProducer.send(...).
template.setExplicitQosEnabled(true);
```

Sau khi cấu hình, các lệnh gửi dùng template sẽ áp dụng bộ QoS này:

```java
template.convertAndSend("orders", orderCreated);
```

Cũng có thể dùng cách viết ngắn hơn:

```java
template.setDeliveryPersistent(true);
template.setPriority(7);
template.setTimeToLive(60_000);
template.setExplicitQosEnabled(true);
```

`setDeliveryPersistent(true)` đặt delivery mode thành `PERSISTENT`; nó không tự bật `explicitQosEnabled`.

### Đăng ký thành Spring bean

Trong ứng dụng Spring, nên cấu hình template một lần trước khi chia sẻ cho các service:

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class JmsConfiguration {

    @Bean
    JmsTemplate ordersJmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);

        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        template.setPriority(7);
        template.setTimeToLive(60_000);
        template.setExplicitQosEnabled(true);

        return template;
    }
}
```

Các service inject `JmsTemplate` này rồi gửi message qua destination tương ứng. Tránh thay đổi các setter QoS liên tục theo từng request trên một template dùng chung, vì nhiều luồng có thể gửi đồng thời và dùng chung cấu hình.

## 4. Dùng QosSettings để cấu hình cả ba giá trị

Spring cung cấp `org.springframework.jms.support.QosSettings` để gom delivery mode, priority và TTL thành một object:

```java
import jakarta.jms.DeliveryMode;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.QosSettings;

JmsTemplate template = new JmsTemplate(connectionFactory);

template.setQosSettings(new QosSettings(
        DeliveryMode.PERSISTENT,
        8,
        30_000
));
```

Điểm quan trọng: trong Spring Framework 7.0.10, `setQosSettings(settings)`:

1. Kiểm tra settings không null.
2. Tự gọi `setExplicitQosEnabled(true)`.
3. Gán delivery mode.
4. Gán priority.
5. Gán time to live.

Vì vậy không cần gọi thêm `setExplicitQosEnabled(true)` sau `setQosSettings`.

Dùng `QosSettings` khi muốn gom bộ QoS vào một cấu hình dễ đọc hoặc truyền bộ cấu hình giữa các thành phần. Các giá trị vẫn là cấu hình của template; template đó áp dụng cùng bộ QoS cho các lần gửi qua nó.

## 5. Cách Spring thực sự gửi message

Về mặt logic, phần gửi của `JmsTemplate` tương đương:

```java
if (template.isExplicitQosEnabled()) {
    producer.send(
            message,
            template.getDeliveryMode(),
            template.getPriority(),
            template.getTimeToLive()
    );
}
else {
    producer.send(message);
}
```

Đây là mã mô tả nhánh xử lý, không phải đoạn thay thế implementation nội bộ của Spring.

| explicitQosEnabled | Overload JMS được gọi | Nguồn QoS |
| --- | --- | --- |
| `false` | `send(message)` | Default của producer/provider |
| `true` | `send(message, deliveryMode, priority, timeToLive)` | Giá trị cấu hình trên `JmsTemplate` |

Sự khác biệt này giải thích vì sao ứng dụng có thể đọc getter thấy `priority=8` nhưng message gửi ra vẫn có priority mặc định nếu cờ explicit chưa được bật.

Nếu broker có policy override, giá trị cuối cùng được broker sử dụng vẫn có thể khác với giá trị client gửi. Getter của template chỉ cho biết cấu hình ở phía Spring, không chứng minh broker đã áp dụng nó.

## 6. Cấu hình QoS theo từng lần gửi bằng JmsClient

Nếu các message trong cùng ứng dụng cần QoS khác nhau, Spring Framework 7.0+ có API fluent `JmsClient`. Mỗi operation có thể chỉ định QoS riêng:

```java
import org.springframework.jms.core.JmsClient;

JmsClient client = JmsClient.create(connectionFactory);

client.destination("orders")
        .withDeliveryPersistent(true)
        .withPriority(8)
        .withTimeToLive(30_000)
        .send(urgentOrder);

client.destination("telemetry")
        .withDeliveryPersistent(false)
        .withPriority(2)
        .withTimeToLive(5_000)
        .send(telemetryEvent);
```

Trong ví dụ:

- Message gửi đến `orders` là persistent, priority 8, TTL 30 giây.
- Message gửi đến `telemetry` là non-persistent, priority 2, TTL 5 giây.

Các operation có cấu hình riêng mà không cần thay đổi setter của một `JmsTemplate` dùng chung. Ví dụ cần một `ConnectionFactory` hợp lệ và các destination đã được provider cấu hình. Đây là ví dụ API; đoạn chương trình kiểm tra cấu hình ở phần sau không kết nối broker.

## 7. Ví dụ Java 17+: kiểm tra các giá trị QoS

Ví dụ sau xác nhận default, việc đặt các setter khi explicit chưa bật, bật explicit và dùng `QosSettings`. Nó không cần broker vì chỉ đọc cấu hình được lưu trong `JmsTemplate`.

Tạo file `src/main/java/JmsTemplateQosDemo.java`:

```java
import jakarta.jms.DeliveryMode;
import org.springframework.jms.core.JmsClient;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.QosSettings;

public class JmsTemplateQosDemo {

    private static String modeName(int mode) {
        return switch (mode) {
            case DeliveryMode.PERSISTENT -> "PERSISTENT";
            case DeliveryMode.NON_PERSISTENT -> "NON_PERSISTENT";
            default -> "UNKNOWN(" + mode + ")";
        };
    }

    private static void print(String label, JmsTemplate template) {
        System.out.println(label + ".deliveryMode="
                + modeName(template.getDeliveryMode()));
        System.out.println(label + ".priority=" + template.getPriority());
        System.out.println(label + ".timeToLiveMs="
                + template.getTimeToLive());
        System.out.println(label + ".explicitQosEnabled="
                + template.isExplicitQosEnabled());
    }

    // Cần JmsClient đã được cấu hình với provider để thực sự gửi.
    static void sendUrgent(JmsClient client, String payload) {
        client.destination("orders")
                .withDeliveryPersistent(true)
                .withPriority(8)
                .withTimeToLive(30_000)
                .send(payload);
    }

    public static void main(String[] args) {
        JmsTemplate template = new JmsTemplate();
        print("default", template);

        template.setDeliveryMode(DeliveryMode.NON_PERSISTENT);
        template.setPriority(7);
        template.setTimeToLive(60_000);
        print("configuredWithoutExplicit", template);

        template.setExplicitQosEnabled(true);
        print("explicit", template);

        template.setQosSettings(new QosSettings(
                DeliveryMode.PERSISTENT, 9, 5_000));
        print("qosSettings", template);
    }
}
```

Tạo `pom.xml` ở thư mục gốc:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>jms-template-qos-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>7.0.10</version>
        </dependency>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>JmsTemplateQosDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q clean compile exec:java
```

Kết quả stdout:

```text
default.deliveryMode=PERSISTENT
default.priority=4
default.timeToLiveMs=0
default.explicitQosEnabled=false
configuredWithoutExplicit.deliveryMode=NON_PERSISTENT
configuredWithoutExplicit.priority=7
configuredWithoutExplicit.timeToLiveMs=60000
configuredWithoutExplicit.explicitQosEnabled=false
explicit.deliveryMode=NON_PERSISTENT
explicit.priority=7
explicit.timeToLiveMs=60000
explicit.explicitQosEnabled=true
qosSettings.deliveryMode=PERSISTENT
qosSettings.priority=9
qosSettings.timeToLiveMs=5000
qosSettings.explicitQosEnabled=true
```

Output cho thấy việc gọi ba setter không tự bật explicit QoS. `setQosSettings` thì tự bật cờ và thay toàn bộ ba giá trị.

## 8. Lựa chọn cấu hình phù hợp

| Nhu cầu | Cách cấu hình |
| --- | --- |
| Một bộ QoS chung cho toàn bộ message của template | Ba setter + `setExplicitQosEnabled(true)` |
| Gom delivery mode, priority và TTL thành một object | `setQosSettings(new QosSettings(...))` |
| Mỗi lần gửi có QoS khác nhau | `JmsClient` với `withDeliveryPersistent`, `withPriority`, `withTimeToLive` |
| Dùng default của JMS provider | Giữ `explicitQosEnabled=false` và không kỳ vọng các setter QoS của template được áp dụng |

Nếu cần nhiều bộ QoS cố định cho các loại message khác nhau, có thể tạo nhiều bean `JmsTemplate` được cấu hình riêng. Nếu cần thay đổi QoS theo từng operation, dùng `JmsClient` hoặc một abstraction gửi message riêng có cấu hình per-send rõ ràng.

Không thay đổi các setter của một `JmsTemplate` dùng chung ngay trước mỗi lần gửi để mô phỏng QoS per-message. Nhiều thread có thể gửi đồng thời và đọc các giá trị ở những thời điểm khác nhau.

## 9. Lưu ý về provider và thời hạn

### Provider có thể áp dụng policy riêng

`explicitQosEnabled=true` bảo đảm Spring gọi overload gửi có ba tham số QoS. Nó không bảo đảm broker bỏ qua policy quản trị. Broker có thể giới hạn priority, áp dụng expiration policy hoặc override delivery behavior. Hãy kiểm tra message thực tế trên broker và cấu hình destination.

### TTL không phải timeout của consumer

TTL tính thời gian message còn hợp lệ khi chờ được giao. Nếu consumer đã nhận message, TTL không tự ngắt logic đang chạy. Dùng timeout riêng ở service/consumer nếu cần giới hạn thời gian xử lý.

### TTL và delivery delay độc lập

Spring JMS còn có `setDeliveryDelay(long)` trong các phiên bản hỗ trợ JMS 2.0. Delivery delay quy định thời điểm sớm nhất provider được giao message; TTL quy định thời điểm message hết hạn. Không dùng TTL thay cho lịch gửi trễ.

### Transaction không làm TTL bắt đầu lại

Với transacted session, TTL được tính từ thời điểm client gửi message. Nếu transaction commit muộn, một phần TTL đã trôi qua trước khi message được consumer nhìn thấy.

## 10. Lỗi thường gặp

1. **Đặt priority hoặc TTL nhưng quên bật explicit QoS.** Template vẫn gọi `send(message)`, nên producer/provider default được dùng.
2. **Nghĩ `setDeliveryPersistent(true)` tự bật explicit.** Setter này chỉ thay delivery mode.
3. **Nhầm `deliveryMode` với acknowledgement mode.** Delivery mode điều khiển độ bền khi provider vận chuyển; acknowledgement mode điều khiển xác nhận nhận message của consumer.
4. **Đặt priority ngoài phạm vi 0–9.** JMS chỉ định mười mức priority; dùng hằng số hoặc giá trị đã kiểm tra.
5. **Đặt TTL theo giây thay vì milliseconds.** Ví dụ 30 giây phải truyền `30_000`.
6. **Dùng TTL 0 để yêu cầu hết hạn ngay.** Trong JMS, TTL 0 nghĩa là không hết hạn.
7. **Cho rằng getter của template chứng minh broker đã nhận QoS đó.** Getter chỉ phản ánh cấu hình Spring; broker có thể áp dụng policy khác.
8. **Dùng một template chung rồi thay QoS trước mỗi lần gửi.** Cấu hình mutable dùng chung có thể tạo race condition giữa các thread.
9. **Dùng TTL làm processing timeout.** TTL không dừng consumer sau khi message đã được giao.
10. **Cấu hình `QosSettings` rồi tiếp tục đặt setter rời rạc mà không chủ ý.** Các setter sau đó ghi đè từng phần giá trị trong bộ QoS đã cấu hình.

## 11. Checklist trước khi gửi

- Chọn delivery mode theo mức độ chấp nhận mất message.
- Chọn priority trong phạm vi 0–9 và định nghĩa quy ước dùng chung.
- Chọn TTL theo thời gian nghiệp vụ còn chấp nhận message cũ; nhớ đơn vị milliseconds.
- Quyết định có dùng default của provider hay cần truyền QoS tường minh.
- Nếu dùng các setter riêng, bật `explicitQosEnabled=true`.
- Nếu dùng `QosSettings`, nhớ rằng phương thức này tự bật explicit QoS.
- Dùng `JmsClient` hoặc template riêng khi cần các bộ QoS khác nhau.
- Kiểm tra policy và giá trị thực tế trên broker.
- Theo dõi message hết hạn, priority, redelivery và lỗi gửi trong môi trường tích hợp.

## 12. Tài liệu tham khảo

- [Spring Framework – JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Spring Framework – QosSettings Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/QosSettings.html)
- [Spring Framework – JmsClient Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsClient.html)
- [Jakarta Messaging – MessageProducer Javadoc](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer)
- [Jakarta Messaging – DeliveryMode Javadoc](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/deliverymode)
