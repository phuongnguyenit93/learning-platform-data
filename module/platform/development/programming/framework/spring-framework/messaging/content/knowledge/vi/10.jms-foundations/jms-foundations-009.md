# Chế độ lưu bền, độ ưu tiên và thời hạn tồn tại của message trong JMS

Khi gửi message bằng Jakarta Messaging (JMS), producer có thể chỉ định ba thuộc tính chất lượng dịch vụ (Quality of Service – QoS):

- **Delivery mode:** message cần được lưu bền khi provider gặp sự cố hay có thể chấp nhận mất message để giảm chi phí truyền tải.
- **Priority:** provider nên ưu tiên message nào khi có nhiều message đang chờ.
- **Time to live (TTL):** message còn hợp lệ trong bao lâu trước khi hết hạn.

Ba thuộc tính này độc lập với nhau. Một message có thể vừa persistent, vừa priority cao, vừa có TTL ngắn. Trong Spring Framework, `JmsTemplate` và API fluent `JmsClient` giúp cấu hình các giá trị này khi gửi.

## 1. Delivery mode: PERSISTENT và NON_PERSISTENT

JMS định nghĩa hai chế độ qua `jakarta.jms.DeliveryMode`:

| Hằng số | Giá trị | Ý nghĩa |
| --- | ---: | --- |
| `DeliveryMode.PERSISTENT` | 2 | Yêu cầu provider ghi message vào bộ lưu trữ ổn định trong quá trình gửi |
| `DeliveryMode.NON_PERSISTENT` | 1 | Không yêu cầu provider ghi message vào bộ lưu trữ ổn định; ưu tiên chi phí và throughput thấp hơn |

### PERSISTENT

Khi gửi một message persistent, provider phải lưu message vào stable storage như một phần của thao tác gửi. Mục tiêu là hạn chế mất message khi provider gặp sự cố. Theo hợp đồng JMS, chỉ sự cố phần cứng lưu trữ nghiêm trọng mới được xem là nguyên nhân có thể làm mất message persistent.

Nên chọn persistent cho các message mà việc mất trong lúc vận chuyển gây hậu quả nghiệp vụ, ví dụ:

- Lệnh tạo hoặc cập nhật đơn hàng.
- Yêu cầu thanh toán hoặc ghi nhận giao dịch.
- Sự kiện nghiệp vụ cần được giữ lại để consumer xử lý sau khi broker khởi động lại.

Persistent có thể tăng chi phí I/O, dung lượng lưu trữ và độ trễ gửi. Mức tác động thực tế phụ thuộc broker, cấu hình journal/store, batching và cách provider triển khai.

### NON_PERSISTENT

Với non-persistent, provider không cần ghi message vào stable storage. Đây là chế độ có overhead thấp hơn, phù hợp khi ứng dụng chấp nhận mất một số message trong trường hợp provider lỗi, ví dụ:

- Telemetry tần suất cao.
- Metrics hoặc dữ liệu quan sát có thể tái tạo.
- Cập nhật trạng thái tạm thời mà bản cập nhật mới hơn sẽ thay thế bản cũ.

JMS yêu cầu non-persistent có bảo đảm at-most-once: provider có thể làm mất message nhưng không được phát cùng message hai lần theo hợp đồng này.

### Delivery mode không thay thế acknowledgement và transaction

Delivery mode chủ yếu điều chỉnh độ tin cậy khi provider vận chuyển message đến destination. Nó không tự bảo đảm message sẽ được giữ vô hạn tại queue sau khi consumer nhận, cũng không thay thế transaction hoặc acknowledgement của consumer.

Retention policy của destination và cách consumer acknowledge/commit quyết định thời điểm message được loại khỏi destination. Nếu consumer xử lý message rồi rollback hoặc mất kết nối trước acknowledgement, provider có thể redeliver tùy session/transaction semantics. Ứng dụng vẫn nên thiết kế consumer idempotent cho nghiệp vụ quan trọng.

## 2. Priority: mức ưu tiên từ 0 đến 9

JMS định nghĩa mười mức priority:

- `0`: thấp nhất.
- `9`: cao nhất.
- `0–4`: các mức thông thường (normal).
- `5–9`: các mức ưu tiên cao (expedited).
- Giá trị mặc định: `4`.

Priority là chỉ dẫn cho provider khi lựa chọn message tiếp theo để giao. Provider nên cố gắng giao message expedited trước message normal, nhưng JMS **không bắt buộc provider phải thực hiện sắp xếp nghiêm ngặt theo priority**.

Điều này có nghĩa:

- Priority cao không bảo đảm message được giao ngay.
- Message đã được giao cho consumer hoặc đang xử lý không bị priority cao hơn “ngắt ngang”.
- Không nên dựa vào priority để thay thế thiết kế thứ tự nghiệp vụ.
- Hành vi thực tế phụ thuộc broker, cấu hình queue và tải của consumer.

Ví dụ phân loại:

| Priority | Cách sử dụng minh họa |
| ---: | --- |
| 0–2 | Tác vụ nền ít khẩn cấp |
| 3–4 | Công việc thông thường |
| 5–7 | Công việc cần xử lý sớm |
| 8–9 | Message khẩn cấp, số lượng ít |

Đây chỉ là quy ước của ứng dụng. JMS không gán ý nghĩa nghiệp vụ cố định cho từng số.

Đừng đặt mọi message ở priority 9. Nếu tất cả đều được đánh dấu khẩn cấp, priority không còn giúp phân biệt tải quan trọng; message thường có thể bị trì hoãn lâu khi broker ưu tiên liên tục các message mới.

## 3. Time to live: thời hạn tồn tại của message

TTL là khoảng thời gian tính bằng milliseconds mà message còn hợp lệ sau khi được gửi.

| TTL | Ý nghĩa |
| ---: | --- |
| `0` | Không hết hạn; message không có thời điểm expiration |
| `5_000` | Hết hạn sau khoảng 5 giây |
| `60_000` | Hết hạn sau khoảng 1 phút |
| `300_000` | Hết hạn sau khoảng 5 phút |

Khi producer gửi message với TTL lớn hơn 0, provider tính thời điểm hết hạn:

```text
JMSExpiration = send time + timeToLive
```

`JMSExpiration` là thời điểm tuyệt đối theo milliseconds tính từ Unix epoch (1970-01-01 UTC). Đây là header do provider thiết lập sau khi gửi; ứng dụng không đặt expiration bằng cách sửa trực tiếp header của message.

Khi message chưa được giao và thời điểm expiration đã đến, provider nên hủy message. Consumer không nên nhận message đã hết hạn, nhưng JMS không bảo đảm tuyệt đối rằng điều đó không bao giờ xảy ra. JMS cũng không định nghĩa một notification chuẩn cho việc message hết hạn. Nếu ứng dụng cần biết message bị loại do TTL, cần dùng cơ chế giám sát hoặc dead-letter/expired-message riêng của broker.

### TTL không phải processing timeout

TTL giới hạn thời gian message chờ được giao khi còn ở phía provider. Nó không đặt thời gian tối đa cho consumer xử lý sau khi message đã được giao.

Ví dụ: message có TTL 30 giây được consumer nhận ở giây thứ 20. Consumer có thể xử lý tiếp sau giây thứ 30; TTL không tự hủy một lần xử lý đã bắt đầu. Nếu cần giới hạn thời gian xử lý, hãy cấu hình timeout ở tầng consumer/service.

### TTL và transaction

Với message được gửi trong một transacted session, JMS tính thời điểm bắt đầu TTL tại thời điểm client gọi send, không phải thời điểm transaction commit. Nếu transaction mất nhiều thời gian mới commit, message có thể đã tiêu hao một phần TTL trước khi trở nên khả dụng cho consumer.

### TTL và delivery delay là hai thuộc tính khác nhau

- **TTL:** message hết hạn sau một khoảng thời gian.
- **Delivery delay:** message không được giao trước khi hết một khoảng trì hoãn.

Nếu cần “chỉ giao sau 30 giây và hết hạn sau 5 phút”, hãy cấu hình delivery delay và TTL riêng nếu provider hỗ trợ JMS 2.0. TTL không phải cách để lên lịch gửi message trong tương lai.

## 4. Cấu hình QoS bằng JmsTemplate

`JmsTemplate` cung cấp các thuộc tính:

- `setDeliveryMode(int)` hoặc `setDeliveryPersistent(boolean)`.
- `setPriority(int)`.
- `setTimeToLive(long)`.
- `setExplicitQosEnabled(boolean)`.
- `setQosSettings(QosSettings)`.

Điểm dễ nhầm là `JmsTemplate` lưu các giá trị QoS mặc định như sau:

| Thuộc tính | Giá trị mặc định |
| --- | --- |
| Delivery mode | `PERSISTENT` |
| Priority | `4` |
| Time to live | `0` |
| `explicitQosEnabled` | `false` |

Khi `explicitQosEnabled=false`, `JmsTemplate` gọi phương thức send không truyền bộ QoS tường minh. Provider có thể dùng các giá trị mặc định được cấu hình bằng quản trị trên ConnectionFactory/broker. Vì vậy, chỉ gọi `setPriority(7)` hoặc `setTimeToLive(60_000)` chưa đủ để bảo đảm những giá trị đó được áp dụng khi gửi.

Muốn `JmsTemplate` sử dụng các giá trị của chính nó, bật explicit QoS:

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@Bean
JmsTemplate orderJmsTemplate(ConnectionFactory connectionFactory) {
    JmsTemplate template = new JmsTemplate(connectionFactory);

    template.setDeliveryPersistent(true);
    template.setPriority(7);
    template.setTimeToLive(60_000);

    // Bắt buộc bật để áp dụng các giá trị QoS đã cấu hình.
    template.setExplicitQosEnabled(true);

    return template;
}
```

Sau khi cấu hình, có thể gửi payload như bình thường:

```java
jmsTemplate.convertAndSend("orders", order);
```

`JmsTemplate` dùng bộ QoS đã cấu hình cho các thao tác gửi. Hãy cấu hình template một lần trước khi chia sẻ cho nhiều service; template được thiết kế thread-safe sau khi đã cấu hình.

### Dùng QosSettings

Có thể gom ba giá trị QoS vào một object:

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

`setQosSettings` tự bật `explicitQosEnabled=true` và gán delivery mode, priority, TTL cho template.

Dùng `DeliveryMode.NON_PERSISTENT` nếu ứng dụng chấp nhận mất message để giảm chi phí lưu trữ. Hãy đặt priority và TTL theo SLA của loại message đang gửi.

## 5. Cấu hình riêng từng lần gửi bằng JmsClient (Spring Framework 7.0+)

Spring Framework 7.0 bổ sung API fluent `JmsClient`. `OperationSpec` cho phép cấu hình QoS theo từng thao tác, hữu ích khi một ứng dụng gửi nhiều loại message có chính sách khác nhau:

```java
import org.springframework.jms.core.JmsClient;

JmsClient client = JmsClient.create(connectionFactory);

client.destination("orders")
        .withDeliveryPersistent(true)
        .withPriority(8)
        .withTimeToLive(30_000)
        .send("urgent-order:42");

client.destination("telemetry")
        .withDeliveryPersistent(false)
        .withPriority(2)
        .withTimeToLive(5_000)
        .send("cpu=0.72");
```

Ví dụ đầu gửi message persistent, priority 8, TTL 30 giây. Ví dụ sau gửi non-persistent, priority 2, TTL 5 giây. Cả hai đều cần một JMS `ConnectionFactory` đã cấu hình và các destination tương ứng trên provider.

Các phương thức `withDeliveryPersistent`, `withPriority` và `withTimeToLive` thuộc cấu hình của operation hiện tại. Điều này thuận tiện hơn khi không muốn thay đổi trạng thái QoS toàn cục của một `JmsTemplate` dùng chung.

## 6. Ví dụ Java 17+: kiểm tra cấu hình QoS của JmsTemplate

Ví dụ sau không cần kết nối broker; nó kiểm tra các giá trị cấu hình mà Spring giữ trong `JmsTemplate`. Việc gửi message thật vẫn cần một JMS provider và ConnectionFactory.

Tạo file `src/main/java/JmsQosConfigDemo.java`:

```java
import jakarta.jms.DeliveryMode;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.QosSettings;

public class JmsQosConfigDemo {

    private static String modeName(int mode) {
        return switch (mode) {
            case DeliveryMode.PERSISTENT -> "PERSISTENT";
            case DeliveryMode.NON_PERSISTENT -> "NON_PERSISTENT";
            default -> "UNKNOWN(" + mode + ")";
        };
    }

    private static void print(String label, JmsTemplate template) {
        System.out.println(label + " deliveryMode: "
                + modeName(template.getDeliveryMode()));
        System.out.println(label + " priority: " + template.getPriority());
        System.out.println(label + " timeToLiveMs: "
                + template.getTimeToLive());
        System.out.println(label + " explicitQosEnabled: "
                + template.isExplicitQosEnabled());
    }

    public static void main(String[] args) {
        JmsTemplate template = new JmsTemplate();
        print("default", template);

        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        template.setPriority(7);
        template.setTimeToLive(60_000);
        print("configuredButNotExplicit", template);

        template.setExplicitQosEnabled(true);
        print("explicit", template);

        template.setQosSettings(new QosSettings(
                DeliveryMode.NON_PERSISTENT, 2, 5_000));
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
    <artifactId>jms-qos-config-demo</artifactId>
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
                    <mainClass>JmsQosConfigDemo</mainClass>
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
default deliveryMode: PERSISTENT
default priority: 4
default timeToLiveMs: 0
default explicitQosEnabled: false
configuredButNotExplicit deliveryMode: PERSISTENT
configuredButNotExplicit priority: 7
configuredButNotExplicit timeToLiveMs: 60000
configuredButNotExplicit explicitQosEnabled: false
explicit deliveryMode: PERSISTENT
explicit priority: 7
explicit timeToLiveMs: 60000
explicit explicitQosEnabled: true
qosSettings deliveryMode: NON_PERSISTENT
qosSettings priority: 2
qosSettings timeToLiveMs: 5000
qosSettings explicitQosEnabled: true
```

Output cho thấy việc đặt delivery mode, priority và TTL chỉ thay đổi cấu hình đang lưu trong template. Cần bật explicit QoS hoặc dùng `setQosSettings` để template áp dụng các giá trị đó trong thao tác gửi.

## 7. Chọn chính sách theo loại message

| Loại message | Delivery mode | Priority | TTL gợi ý |
| --- | --- | ---: | --- |
| Lệnh thanh toán/đơn hàng | Persistent | 5–8 theo mức khẩn cấp | 0 hoặc theo thời hạn nghiệp vụ |
| Sự kiện cập nhật hồ sơ | Persistent | 4 | Theo thời gian sự kiện còn hữu ích |
| Telemetry có thể bỏ qua | Non-persistent | 1–3 | Ngắn, ví dụ vài giây |
| Trạng thái hiện thời, bản mới thay bản cũ | Non-persistent nếu chấp nhận mất | 2–4 | Ngắn |
| Cảnh báo vận hành quan trọng | Persistent | 7–9 | Đủ dài để consumer có thể phục hồi |

Các giá trị TTL trong bảng chỉ là điểm khởi đầu. Hãy xác định TTL từ thời gian tối đa mà nghiệp vụ còn chấp nhận xử lý message cũ. Với lệnh tài chính, đặt TTL quá ngắn có thể làm mất một yêu cầu hợp lệ khi consumer đang gián đoạn; đặt TTL quá dài có thể khiến command lỗi thời được xử lý sau khi hệ thống phục hồi.

Đừng dùng priority để thay thế queue riêng cho các workload có SLA khác nhau. Nếu message khẩn cấp cần tài nguyên hoặc consumer riêng, tách destination và giới hạn tải có thể dễ vận hành hơn.

## 8. Các điểm cần kiểm tra ở broker

JMS cho phép quản trị viên cấu hình provider ghi đè các giá trị QoS do client gửi. Ngoài ra, từng broker có thể khác nhau về cách lưu bền, lập lịch priority, dọn message hết hạn và đưa message vào dead-letter queue.

Khi triển khai thực tế, cần xác minh:

- Broker có bật persistence store/journal và có chính sách lưu trữ phù hợp không.
- Destination có giới hạn dung lượng, message age hoặc retention policy nào không.
- Priority có được broker bật/áp dụng cho destination đó không.
- TTL được dọn theo chu kỳ nào và message hết hạn có được chuyển sang dead-letter hay bị loại bỏ.
- Giá trị QoS client gửi có bị broker policy ghi đè không.
- Transaction, acknowledgement và redelivery policy có phù hợp với yêu cầu nghiệp vụ không.

Đừng suy ra hành vi của broker chỉ từ giá trị getter trên `JmsTemplate`. Nếu cần xác nhận, gửi message thử qua provider thật và đọc các header do provider thiết lập như `JMSDeliveryMode`, `JMSPriority`, `JMSExpiration`.

## 9. Lỗi thường gặp

1. **Gọi `setPriority(8)` nhưng quên bật explicit QoS.** `JmsTemplate` có thể vẫn dùng default do provider hoặc quản trị viên cấu hình.
2. **Cho rằng persistent bảo đảm message được xử lý đúng một lần ở tầng nghiệp vụ.** Delivery mode không thay thế transaction, acknowledgement và idempotency.
3. **Cho rằng non-persistent chắc chắn luôn mất khi broker restart.** JMS cho phép provider giữ lại, nhưng không yêu cầu provider ghi stable storage; ứng dụng phải chấp nhận rủi ro mất.
4. **Cho rằng priority 9 luôn được giao trước mọi message khác.** Provider chỉ phải cố gắng ưu tiên, không cần thực thi strict ordering.
5. **Dùng TTL như timeout xử lý consumer.** TTL áp dụng cho thời gian message chờ được giao, không tự dừng xử lý đã bắt đầu.
6. **Đặt TTL bằng 0 khi muốn message hết hạn ngay.** Trong JMS, 0 nghĩa là không hết hạn.
7. **Sửa trực tiếp `JMSExpiration`, `JMSPriority` hoặc `JMSDeliveryMode` trên message.** Đây là các header do provider thiết lập khi gửi; cấu hình qua producer, JmsTemplate hoặc JmsClient.
8. **Giả định message hết hạn luôn phát notification.** JMS không định nghĩa notification chuẩn cho expiration.
9. **Cấu hình QoS trên template dùng chung sau khi ứng dụng đã chạy.** Nên cấu hình xong trước khi chia sẻ template; dùng `JmsClient` khi cần QoS riêng từng operation.
10. **Không kiểm tra broker policy.** Broker có thể ghi đè QoS hoặc có giới hạn retention riêng.

## 10. Checklist trước khi gửi

- Chọn persistent nếu mất message trong lúc vận chuyển là không chấp nhận được.
- Chọn non-persistent chỉ khi nghiệp vụ chịu được mất message.
- Đặt priority 0–9 có ý nghĩa và tránh đánh dấu mọi message là khẩn cấp.
- Xác định TTL từ thời hạn hữu ích của nghiệp vụ; nhớ 0 nghĩa là không hết hạn.
- Với `JmsTemplate`, bật `explicitQosEnabled` hoặc dùng `setQosSettings`.
- Dùng `JmsClient` khi cần QoS theo từng thao tác.
- Xác minh QoS thực tế và policy trên broker.
- Thiết kế acknowledgement, transaction, redelivery và idempotency độc lập với delivery mode.

## 11. Tài liệu tham khảo

- [Spring Framework – Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework – JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Spring Framework – JmsClient Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsClient.html)
- [Spring Framework – QosSettings Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/QosSettings.html)
- [Jakarta Messaging – DeliveryMode Javadoc](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/deliverymode)
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.pdf)
