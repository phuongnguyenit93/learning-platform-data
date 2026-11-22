# Thay kế thừa bằng kết hợp (Replace Inheritance with Composition) trong Java OOP

## 1. Vấn đề cần giải quyết

**Kế thừa** cho phép một lớp mở rộng lớp khác bằng cú pháp `extends`. Đây là cơ chế hữu ích khi quan hệ phân loại giữa hai lớp thực sự phù hợp với quy tắc **is-a**: đối tượng lớp con có thể được dùng ở mọi nơi chấp nhận lớp cha mà vẫn giữ đúng hợp đồng hành vi.

Tuy nhiên, trong thực tế có trường hợp một lớp kế thừa chỉ vì muốn **tận dụng vài phương thức** của lớp khác. Khi đó lớp con bị ràng buộc vào API, trạng thái và thay đổi của lớp cha. Một thay đổi trong lớp cha có thể ảnh hưởng ngoài ý muốn tới lớp con; lớp con cũng dễ phải ghi đè phương thức không liên quan đến trách nhiệm của mình.

**Thay kế thừa bằng kết hợp (Replace Inheritance with Composition)** là cách tái cấu trúc từ thiết kế "lớp A extends lớp B để mượn hành vi" sang thiết kế "lớp A **chứa một đối tượng** cung cấp hành vi cần dùng và **ủy quyền** công việc cho đối tượng đó".

Mục đích:
- Tách **trách nhiệm nghiệp vụ** khỏi **cơ chế thực thi**.
- Giảm sự phụ thuộc vào chi tiết của lớp cha.
- Cho phép cấu hình các cách thực hiện qua interface.
- Giúp viết unit test bằng fake/stub mà không phải kích hoạt hệ thống thật.
- Giữ nguyên hành vi quan sát được khi refactor, trừ những thay đổi API đã được lên kế hoạch.

Đây **không phải quy tắc cấm kế thừa**. Kế thừa vẫn đúng khi có quan hệ phân loại ổn định và lớp con thỏa hợp đồng của lớp cha. Vấn đề là chọn cơ chế phù hợp với trách nhiệm của đối tượng.

## 2. Phân biệt kế thừa và kết hợp

| Góc nhìn | Kế thừa | Kết hợp (composition) |
| --- | --- | --- |
| Quan hệ mô hình | **is-a**: một loại của lớp cha | **has-a/uses-a**: sở hữu hoặc sử dụng cộng tác viên |
| Java | `class Child extends Parent` | Trường tham chiếu: `private final Capability capability;` |
| Tái sử dụng | Nhận phương thức và cơ chế của lớp cha | Gọi phương thức trên đối tượng được tiêm vào |
| Mức phụ thuộc | Thường gắn chặt vào cấu trúc/hợp đồng lớp cha | Có thể phụ thuộc vào interface nhỏ |
| Thay cách thực hiện | Thường cần lớp con khác hoặc sửa cấu trúc kế thừa | Có thể cung cấp implementation khác khi tạo đối tượng |
| Kiểm thử | Dễ bị kéo theo hành vi của lớp cha | Tiêm fake/mock ở ranh giới cộng tác |
| Chi phí | Ít đối tượng ủy quyền hơn; dễ hiểu nếu is-a thực sự đúng | Thêm field, constructor và mã ủy quyền; cần thiết kế vòng đời |

Lưu ý: trong Java, **kế thừa lớp** bằng `extends` và **thực thi interface** bằng `implements` không đồng nghĩa về mức độ ràng buộc. Một đối tượng vẫn có thể `implements MessageChannel` để tuân thủ hợp đồng, trong khi một đối tượng khác sử dụng `MessageChannel` qua kết hợp.

## 3. Ví dụ trước khi refactor: lớp cảnh báo kế thừa bộ gửi email

Giả sử một hệ thống cần gửi cảnh báo nghiêm trọng cho nhân viên vận hành. Phiên bản đầu dùng email:

~~~java
class EmailSender {
    public void send(String address, String text) {
        System.out.println("EMAIL -> " + address + ": " + text);
    }
}

// Kế thừa chỉ để tận dụng phương thức send().
class CriticalAlert extends EmailSender {
    public void notifyOperator(String address, String incident) {
        send(address, "[CRITICAL] " + incident);
    }
}
~~~

Mã hoạt động khi chỉ có email, nhưng quan hệ `CriticalAlert extends EmailSender` không mô tả đúng nghiệp vụ: **cảnh báo không phải là một loại bộ gửi email**. Cảnh báo chỉ *sử dụng* phương tiện gửi tin.

Khi bổ sung SMS, webhook hoặc kênh thông báo nội bộ, thiết kế này dễ dẫn tới nhân bản các lớp cảnh báo theo từng loại kênh. Lớp cảnh báo cũng thừa hưởng toàn bộ API public/protected của EmailSender, kể cả những phương thức có thể được thêm sau này nhưng không phù hợp với vai trò cảnh báo.

Nếu một lớp con phải ghi đè phương thức cha để ném `UnsupportedOperationException` hoặc thay đổi hậu điều kiện mà caller của lớp cha đang trông đợi, còn có nguy cơ vi phạm **Liskov Substitution Principle (LSP)**. Không phải mọi quan hệ kế thừa đều vi phạm LSP; vấn đề xuất hiện khi lớp con không thể thay thế lớp cha theo hợp đồng.

Có thể hình dung trước và sau:

~~~mermaid
classDiagram
    class EmailSender {
        +send(address, text)
    }
    class CriticalAlertOld {
        +notifyOperator(address, incident)
    }
    EmailSender <|-- CriticalAlertOld : kế thừa để dùng send

    class AlertService {
        -MessageChannel channel
        +sendCritical(recipient, incident)
    }
    class MessageChannel {
        <<interface>>
        +send(recipient, body)
    }
    class EmailChannel {
        +send(recipient, body)
    }
    class SmsChannel {
        +send(recipient, body)
    }
    class RetryingChannel {
        -MessageChannel delegate
        +send(recipient, body)
    }
    AlertService o--> MessageChannel : chứa và ủy quyền
    MessageChannel <|.. EmailChannel
    MessageChannel <|.. SmsChannel
    MessageChannel <|.. RetryingChannel
    RetryingChannel o--> MessageChannel : bọc
~~~

## 4. Thiết kế sau refactor: kết hợp qua interface

Ta tách hai trách nhiệm:
- `AlertService` hiểu nghiệp vụ: thế nào là cảnh báo nghiêm trọng và cách đặt nội dung cảnh báo.
- `MessageChannel` hiểu việc gửi thông điệp. Email, SMS, và kênh có retry là các cách thực hiện khác nhau.

`AlertService` **có một** `MessageChannel`, chứ không **là một** `MessageChannel`.

Quy trình được ủy quyền:

~~~mermaid
sequenceDiagram
    actor Operator as Ứng dụng
    participant A as AlertService
    participant C as MessageChannel
    Operator->>A: sendCritical(recipient, incident)
    A->>A: Kiểm tra dữ liệu và tạo nội dung
    A->>C: send(recipient, "[CRITICAL] ...")
    C-->>A: Trả về hoặc ném lỗi
    A-->>Operator: Hoàn thành hoặc truyền lỗi
~~~

### 4.1. Cấu trúc dự án

Ví dụ dưới đây dùng **Java 17, Maven và JUnit Jupiter 5**. Các lớp production được viết ở từng tệp Java để có thể sao chép và chạy được.

~~~text
composition-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/
    │   ├── MessageChannel.java
    │   ├── AlertService.java
    │   ├── EmailChannel.java
    │   ├── SmsChannel.java
    │   ├── DeliveryException.java
    │   ├── RetryingChannel.java
    │   └── Main.java
    └── test/java/vn/example/
        └── AlertServiceTest.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>composition-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 4.2. Định nghĩa hợp đồng gửi thông điệp

**src/main/java/vn/example/MessageChannel.java**

~~~java
package vn.example;

@FunctionalInterface
public interface MessageChannel {
    /**
     * Gửi nội dung tới người nhận. Có thể ném RuntimeException nếu lỗi.
     * Trả về bình thường nghĩa là kênh đã xử lý yêu cầu theo hợp đồng.
     */
    void send(String recipient, String body);
}
~~~

Một interface nhỏ đủ cho nhu cầu của AlertService. Nó không ép lớp cảnh báo biết SMTP, HTTP endpoint hay định dạng SMS. Trong dự án thực tế, hợp đồng cần nói rõ `send` đồng nghĩa với đã giao tới nhà cung cấp, đã xếp vào hàng đợi hay đã đến thiết bị nhận; các mức bảo đảm này không giống nhau.

### 4.3. Đối tượng nghiệp vụ chỉ ủy quyền cho cộng tác viên

**src/main/java/vn/example/AlertService.java**

~~~java
package vn.example;

import java.util.Objects;

public final class AlertService {
    private final MessageChannel channel;

    public AlertService(MessageChannel channel) {
        this.channel = Objects.requireNonNull(channel, "channel");
    }

    public void sendCritical(String recipient, String incident) {
        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException("recipient is blank");
        }
        if (incident == null || incident.isBlank()) {
            throw new IllegalArgumentException("incident is blank");
        }

        channel.send(recipient, "[CRITICAL] " + incident);
    }
}
~~~

Điểm quan trọng:
1. Constructor injection cho phép cung cấp đối tượng phụ thuộc tại nơi dựng ứng dụng.
2. `final` giữ cộng tác viên cố định trong vòng đời AlertService; không bị thay bất ngờ trong lúc xử lý.
3. Phương thức public biểu đạt **hành vi nghiệp vụ**, không phơi bày toàn bộ API của kênh gửi.
4. Việc validate xảy ra **trước khi gọi kênh**, nên input không hợp lệ không gây tác dụng phụ.
5. AlertService không biết implementation cụ thể; chỉ yêu cầu kênh thực thi hợp đồng `send`.

### 4.4. Hai implementation email và SMS

Để chương trình có thể chạy trực tiếp mà không cần tài khoản bên ngoài, hai lớp dưới đây **in ra console**. Chúng đại diện cho adapter minh họa, không gửi email/SMS thật.

**src/main/java/vn/example/EmailChannel.java**

~~~java
package vn.example;

public final class EmailChannel implements MessageChannel {
    @Override
    public void send(String recipient, String body) {
        System.out.println("EMAIL -> " + recipient + ": " + body);
    }
}
~~~

**src/main/java/vn/example/SmsChannel.java**

~~~java
package vn.example;

public final class SmsChannel implements MessageChannel {
    @Override
    public void send(String recipient, String body) {
        System.out.println("SMS -> " + recipient + ": " + body);
    }
}
~~~

Cả hai tuân thủ cùng interface và không phải là lớp cha của AlertService. Do đó, khi cần phương tiện mới, ta thêm implementation, thay vì cho lớp nghiệp vụ kế thừa một loại phương tiện mới.

### 4.5. Kết hợp nhiều khả năng: wrapper thử lại khi gặp lỗi đã phân loại

Giả sử muốn thử gửi lại khi xảy ra lỗi tạm thời. Nếu dùng kế thừa, người ta dễ tạo các lớp như `RetryingEmailChannel`, `RetryingSmsChannel`, `LoggingRetryingEmailChannel`... gây nhiều tổ hợp lớp.

Với kết hợp, ta tạo một đối tượng **bọc (decorator)** implement cùng interface và chứa một `MessageChannel` khác. Chỉ khi delegate ném `DeliveryException` thì wrapper mới retry.

**src/main/java/vn/example/DeliveryException.java**

~~~java
package vn.example;

/** Trong ví dụ, biểu thị lỗi có thể thử lại. */
public final class DeliveryException extends RuntimeException {
    public DeliveryException(String message) {
        super(message);
    }
}
~~~

**src/main/java/vn/example/RetryingChannel.java**

~~~java
package vn.example;

import java.util.Objects;

public final class RetryingChannel implements MessageChannel {
    private final MessageChannel delegate;
    private final int maxAttempts;

    public RetryingChannel(MessageChannel delegate, int maxAttempts) {
        this.delegate = Objects.requireNonNull(delegate, "delegate");
        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                    "maxAttempts must be at least 1");
        }
        this.maxAttempts = maxAttempts;
    }

    @Override
    public void send(String recipient, String body) {
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                delegate.send(recipient, body);
                return;
            } catch (DeliveryException failure) {
                if (attempt == maxAttempts) {
                    throw failure;
                }
            }
        }
    }
}
~~~

Ta có thể kết hợp tùy ý:
- `new RetryingChannel(new EmailChannel(), 3)`
- `new RetryingChannel(new SmsChannel(), 3)`
- `new AlertService(new EmailChannel())`
- `new AlertService(new RetryingChannel(new SmsChannel(), 3))`

**Đếm đúng số lượt:** `maxAttempts = 3` nghĩa là nhiều nhất **3 lần gửi tổng cộng**, không phải một lượt ban đầu cộng ba lượt retry. Wrapper này không có backoff, timeout hoặc chính sách idempotency; nó chỉ phục vụ việc học cách kết hợp hành vi.

### 4.6. Composition root: chỗ chọn implementation

**src/main/java/vn/example/Main.java**

~~~java
package vn.example;

public final class Main {
    public static void main(String[] args) {
        MessageChannel reliableEmail =
                new RetryingChannel(new EmailChannel(), 3);
        AlertService emailAlerts = new AlertService(reliableEmail);

        AlertService smsAlerts =
                new AlertService(new SmsChannel());

        emailAlerts.sendCritical(
                "ops@example.com", "Database is unavailable");
        smsAlerts.sendCritical(
                "+84900000000", "API latency is high");
    }
}
~~~

Chạy tại thư mục chứa `pom.xml`:

~~~bash
mvn test
mvn -q -DskipTests package
java -cp target/classes vn.example.Main
~~~

Đầu ra demo dự kiến:

~~~text
EMAIL -> ops@example.com: [CRITICAL] Database is unavailable
SMS -> +84900000000: [CRITICAL] API latency is high
~~~

Các lựa chọn cụ thể nằm tại **composition root** — nơi dựng đồ thị đối tượng lúc khởi động ứng dụng. AlertService không có nhánh kiểu `if (channelType.equals("SMS"))` và cũng không tạo `new EmailChannel()` bên trong phương thức nghiệp vụ.

## 5. Unit test: xác minh sự thay thế được và quy tắc retry

Ta kiểm tra chức năng bằng các implementation giả trong bộ nhớ, không cần kết nối email hay SMS thật.

**src/test/java/vn/example/AlertServiceTest.java**

~~~java
package vn.example;

import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

class AlertServiceTest {
    record Sent(String recipient, String body) {}

    private static final class RecordingChannel implements MessageChannel {
        final List<Sent> messages = new ArrayList<>();

        @Override
        public void send(String recipient, String body) {
            messages.add(new Sent(recipient, body));
        }
    }

    private static final class FlakyChannel implements MessageChannel {
        final int failuresBeforeSuccess;
        int calls;
        int successfulSends;

        FlakyChannel(int failuresBeforeSuccess) {
            this.failuresBeforeSuccess = failuresBeforeSuccess;
        }

        @Override
        public void send(String recipient, String body) {
            calls++;
            if (calls <= failuresBeforeSuccess) {
                throw new DeliveryException("Temporary error");
            }
            successfulSends++;
        }
    }

    @Test
    void sendsCriticalMessageThroughInjectedChannel() {
        RecordingChannel channel = new RecordingChannel();
        AlertService alerts = new AlertService(channel);

        alerts.sendCritical("ops@example.com", "Disk full");

        assertEquals(
                List.of(new Sent("ops@example.com", "[CRITICAL] Disk full")),
                channel.messages);
    }

    @Test
    void invalidInputDoesNotTouchTheChannel() {
        RecordingChannel channel = new RecordingChannel();
        AlertService alerts = new AlertService(channel);

        assertThrows(IllegalArgumentException.class,
                () -> alerts.sendCritical(" ", "Disk full"));
        assertThrows(IllegalArgumentException.class,
                () -> alerts.sendCritical("ops@example.com", ""));
        assertThrows(IllegalArgumentException.class,
                () -> alerts.sendCritical(null, "Disk full"));
        assertThrows(IllegalArgumentException.class,
                () -> alerts.sendCritical("ops@example.com", null));

        assertTrue(channel.messages.isEmpty());
    }

    @Test
    void retryingChannelEventuallySucceeds() {
        FlakyChannel flaky = new FlakyChannel(2);
        AlertService alerts = new AlertService(
                new RetryingChannel(flaky, 3));

        alerts.sendCritical("ops@example.com", "Database down");

        assertEquals(3, flaky.calls);
        assertEquals(1, flaky.successfulSends);
    }

    @Test
    void retryingChannelStopsAfterAttemptLimit() {
        FlakyChannel flaky = new FlakyChannel(10);
        AlertService alerts = new AlertService(
                new RetryingChannel(flaky, 2));

        assertThrows(DeliveryException.class,
                () -> alerts.sendCritical(
                        "ops@example.com", "Database down"));

        assertEquals(2, flaky.calls);
        assertEquals(0, flaky.successfulSends);
    }

    @Test
    void unexpectedExceptionIsNotRetried() {
        AtomicInteger calls = new AtomicInteger();
        MessageChannel broken = (recipient, body) -> {
            calls.incrementAndGet();
            throw new IllegalArgumentException("Bad configuration");
        };

        AlertService alerts =
                new AlertService(new RetryingChannel(broken, 5));

        assertThrows(IllegalArgumentException.class,
                () -> alerts.sendCritical("ops@example.com", "Disk full"));
        assertEquals(1, calls.get());
    }

    @Test
    void dependenciesAndRetryLimitMustBeValid() {
        assertThrows(NullPointerException.class,
                () -> new AlertService(null));
        assertThrows(NullPointerException.class,
                () -> new RetryingChannel(null, 3));
        assertThrows(IllegalArgumentException.class,
                () -> new RetryingChannel(new RecordingChannel(), 0));
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Với đúng các tệp ở trên, JUnit có **6 phương thức `@Test`**. Các ca kiểm tra không cần môi trường mạng, có thể chủ động dựng tình huống thành công, lỗi tạm thời và lỗi không được retry.

| Kiểm thử | Điều được xác minh | Giá trị của thiết kế kết hợp |
| --- | --- | --- |
| sendsCriticalMessageThroughInjectedChannel | Nội dung và người nhận được chuyển đúng tới cộng tác viên | Dùng fake thay email thật mà không thay đổi AlertService |
| invalidInputDoesNotTouchTheChannel | Input sai bị chặn trước tác dụng phụ | Quy tắc nghiệp vụ độc lập implementation |
| retryingChannelEventuallySucceeds | Thất bại 2 lần, thành công lần 3 | Wrapper có thể bọc một implementation bất kỳ |
| retryingChannelStopsAfterAttemptLimit | Giới hạn tối đa 2 lần gọi được tuân thủ | Chính sách retry có thể kiểm thử riêng |
| unexpectedExceptionIsNotRetried | Lỗi không thuộc loại retry không bị gọi lặp | Ranh giới chính sách lỗi rõ ràng |
| dependenciesAndRetryLimitMustBeValid | Không tạo object ở trạng thái thiếu phụ thuộc | Constructor xác lập bất biến |

Vì AlertService nhận một `MessageChannel`, việc kiểm thử cả các trường hợp gửi email, SMS hoặc fake dùng chung phần nghiệp vụ trở nên đơn giản. Các adapter giao tiếp dịch vụ ngoài vẫn phải có **integration test riêng** để xác minh API, cấu hình và lỗi thực tế.

## 6. Các bước tái cấu trúc từ kế thừa sang kết hợp

Không nên xóa `extends` ngay khi chưa hiểu các caller và hợp đồng public. Trình tự an toàn:

1. **Xác nhận quan hệ hiện tại.** Hỏi "AlertService có thực sự là EmailSender không?" và "nó kế thừa vì quan hệ phân loại hay chỉ muốn dùng `send`?".
2. **Chốt hành vi đang sử dụng.** Viết test cho thông điệp, tham số, lỗi và số lần gửi. Đặc biệt kiểm tra code hiện tại có phụ thuộc vào việc lớp con được dùng như lớp cha hay không.
3. **Tìm phụ thuộc tối thiểu.** Nếu lớp con chỉ cần `send(recipient, body)`, tạo interface `MessageChannel` thay vì kéo toàn bộ API của EmailSender vào đối tượng mới.
4. **Tạo trường kết hợp.** Thêm `private final MessageChannel channel` và constructor nhận interface. Nếu chuyển đổi theo từng bước, giữ API cũ bằng phương thức ủy quyền ngắn trong giai đoạn chuyển tiếp.
5. **Đổi các lời gọi kế thừa.** Thay `send(...)` bằng `channel.send(...)`. Test hồi quy phải tiếp tục đạt.
6. **Chuyển các caller.** Nơi trước đây tạo `new CriticalAlert()` nay cung cấp implementation phù hợp. Nếu có API nhận `EmailSender` và truyền `CriticalAlert`, cần phân tích thiết kế hoặc adapter chuyển tiếp; bỏ `extends` sẽ là **thay đổi tương thích kiểu**.
7. **Loại bỏ kế thừa dư thừa.** Sau khi rà soát các caller và điều kiện tương thích, xóa `extends` và các override chỉ tồn tại vì lớp cha.
8. **Kiểm chứng cả thiết kế lẫn hành vi.** Biên dịch, unit test, integration test cần thiết, kiểm tra API public và khả năng chọn implementation theo cấu hình.

~~~mermaid
flowchart TD
    A["Lớp con extends lớp cha chỉ để dùng một chức năng"] --> B["Khoanh vùng hợp đồng và các caller"]
    B --> C["Viết test hồi quy"]
    C --> D["Tạo interface cho chức năng cần dùng"]
    D --> E["Tiêm đối tượng qua constructor"]
    E --> F["Đổi lời gọi kế thừa thành ủy quyền"]
    F --> G["Chuyển caller và kiểm tra tính tương thích"]
    G --> H{"Test và hợp đồng đạt?"}
    H -->|Không| I["Chỉnh sai lệch hoặc adapter chuyển tiếp"]
    I --> G
    H -->|Có| J["Bỏ extends dư thừa, rà soát thiết kế"]
~~~

### 6.1. Khi nào cần giữ adapter tương thích?

Ví dụ, nếu một thư viện công khai cung cấp `CriticalAlert extends EmailSender`, code bên ngoài có thể viết:

~~~java
// Ví dụ từ API cũ:
EmailSender sender = new CriticalAlert();
~~~

Sau khi đổi CriticalAlert thành lớp có trường MessageChannel, dòng trên **không còn biên dịch**. Đây không phải lỗi thuật toán nhưng là breaking change đối với caller. Cần xác định yêu cầu tương thích nhị phân/nguồn, lên kế hoạch version hoặc dùng một lớp adapter công khai trong thời gian chuyển đổi.

Trong một codebase nội bộ có toàn quyền sửa caller, có thể di chuyển gọn hơn. Với API đã phát hành, thay đổi quan hệ kế thừa cần đánh giá kỹ hơn việc thay phương thức private.

## 7. Strategy, Decorator và Dependency Injection liên quan thế nào?

**Composition** là quan hệ một đối tượng chứa/sử dụng đối tượng khác. Nó là cơ chế nền.

**Strategy pattern** sử dụng các implementation có thể thay thế nhau cho cùng một interface. Trong bài, `EmailChannel` và `SmsChannel` là các chiến lược gửi khác nhau; chọn chiến lược tại lúc tạo AlertService.

**Decorator pattern** bọc một implementation bằng một implementation cùng interface để bổ sung hành vi. `RetryingChannel` vừa implement `MessageChannel` vừa chứa `MessageChannel`, thêm chính sách retry nhưng không buộc sửa EmailChannel/SmsChannel.

**Dependency Injection (DI)** là cách cung cấp collaborator từ bên ngoài. `new AlertService(new SmsChannel())` đã là constructor injection; không cần framework DI mới dùng được kết hợp.

| Câu hỏi | Khái niệm phù hợp |
| --- | --- |
| Đối tượng A sử dụng năng lực của B như thế nào? | Composition + delegation |
| Chọn email hay SMS cho cùng một nhu cầu? | Strategy |
| Thêm retry hoặc logging mà không sửa kênh cơ sở? | Decorator |
| Ai khởi tạo và đưa kênh vào AlertService? | Dependency injection / composition root |

Các mẫu này **có thể phối hợp**, không loại trừ nhau. `AlertService` dùng Strategy được tiêm qua constructor; Strategy ấy có thể là Decorator bọc một adapter khác.

## 8. Khi nào kế thừa vẫn là lựa chọn hợp lý?

Kế thừa có giá trị khi lớp con là một dạng chuyên biệt đúng nghĩa của lớp cha, dựa trên hợp đồng ổn định và không thay đổi tiền/hậu điều kiện làm caller bị bất ngờ. Ví dụ một hierarchy nội bộ có các hook được thiết kế công khai để mở rộng hoặc một base class ổn định trong framework. Dù vậy, vẫn cần test hợp đồng của lớp cha trên các lớp con khi điều này có ý nghĩa.

Ngược lại, nếu lớp con ghi đè nhiều phương thức để làm rỗng, ném lỗi, hoặc cần biết trường `protected` của lớp cha để giữ trạng thái nhất quán, đó là tín hiệu nên xét lại thiết kế.

Một quyết định thực tế:

| Dấu hiệu | Hướng ưu tiên |
| --- | --- |
| "A là một B" và có thể thay B theo đúng hợp đồng | Có thể dùng kế thừa |
| "A có một B", "A dùng dịch vụ của B" | Kết hợp |
| Cần chọn nhiều cách thực hiện theo môi trường | Kết hợp qua interface |
| Cần ghép logging, retry, metrics theo lớp | Kết hợp/Decorator |
| Các lớp con phình ra theo mọi tổ hợp tính năng | Tách chức năng độc lập, kết hợp |
| Thay lớp cha khiến nhiều lớp con hỏng ngoài dự kiến | Giảm ràng buộc với lớp cha, xem lại kết hợp |
| Chỉ có một thuật toán nhỏ, không có lý do thay thế | Có thể để trực tiếp trong lớp, tránh abstraction thừa |

**Đừng tạo interface cho mọi lớp một cách máy móc.** Nếu một phép tính thuần túy đơn giản không có nhiều implementation hợp lý hoặc ranh giới cần cô lập, thêm interface và đối tượng delegate chỉ làm tăng công việc đọc code.

## 9. Các lỗi thường gặp khi chuyển đổi

### 9.1. Chuyển extends thành field nhưng vẫn lộ toàn bộ API

~~~java
// Ví dụ cách chuyển chưa tốt:
class PoorAlertService {
    private final EmailChannel email = new EmailChannel();

    void sendRaw(String recipient, String body) {
        email.send(recipient, body);
    }
}
~~~

Nó đã dùng kết hợp về cú pháp, nhưng vẫn tự khóa vào `EmailChannel` cụ thể và public API còn phản ánh hoạt động gửi thô thay vì nghiệp vụ cảnh báo. Nếu nhu cầu thực sự có nhiều kênh, nhận `MessageChannel` qua constructor sẽ tách trách nhiệm tốt hơn.

### 9.2. Biến một service thành "God Object"

Dùng kết hợp không có nghĩa một lớp được giữ hàng chục dependency và quyết định mọi thứ. Nếu AlertService vừa tính tiền, vừa phân quyền, vừa lập lịch, vừa gửi email, vấn đề chính vẫn là trách nhiệm quá lớn. Hãy tách use case, policy và adapter theo nhu cầu.

### 9.3. Retry bừa các thao tác không idempotent

Ví dụ retry chỉ định nghĩa cho `DeliveryException` của kênh. Trong dịch vụ thật, request đầu tiên có thể đã được nhà cung cấp tiếp nhận nhưng phản hồi bị mất; gửi lại có thể tạo hai email/SMS. Với các hành động quan trọng như thanh toán, cần idempotency key, lưu trạng thái bền vững, truy vấn/đối soát, backoff và quy tắc retry cụ thể. Composition giúp **đặt** chính sách tại lớp thích hợp, không tự bảo đảm chính sách ấy an toàn.

### 9.4. Nhầm lẫn kết hợp với kế thừa interface

`EmailChannel implements MessageChannel` là sử dụng interface để khai báo hợp đồng. `AlertService` kết hợp `MessageChannel` bởi nó có trường `channel`. Hai quan hệ cùng xuất hiện là điều bình thường và có mục đích khác nhau.

### 9.5. Bỏ qua vòng đời và thread-safety

Nếu nhiều thread dùng chung một collaborator có trạng thái thay đổi, cần xác định collaborator có an toàn đồng thời hay không. `private final` chỉ cố định **tham chiếu**, không bảo đảm đối tượng được tham chiếu là immutable hoặc thread-safe.

## 10. Thực hành có hướng dẫn

**Bài tập 1 — Thêm kênh Webhook.** Tạo `WebhookChannel implements MessageChannel` với implementation demo chỉ ghi URL và thông điệp vào danh sách. Dùng `new AlertService(new WebhookChannel(...))` và kiểm tra nội dung cảnh báo, không sửa AlertService.

**Bài tập 2 — Thêm LoggingChannel.** Viết một decorator bọc `MessageChannel` để ghi số lần gọi. Thử `new LoggingChannel(new RetryingChannel(new EmailChannel(), 3))` và `new RetryingChannel(new LoggingChannel(new EmailChannel()), 3)`. Hai cách sắp thứ tự wrapper có thể ghi các số liệu khác nhau; giải thích vì sao.

**Bài tập 3 — Đánh giá test retry.** Viết fake thất bại lần 1 rồi thành công lần 2. Kiểm tra maxAttempts = 1 thì lỗi được truyền ra, maxAttempts = 2 thì thành công. Đảm bảo không retry `IllegalArgumentException`.

**Bài tập 4 — Nhận diện quan hệ.** Cho các câu: "Car dùng Engine", "SavingsAccount là một Account", "OrderService dùng EmailSender", "CSV exporter là một Formatter". Với mỗi câu, chỉ ra đâu là quan hệ dữ liệu/nghiệp vụ thật, đâu là khả năng có thể thay thế; giải thích khi nào `extends`, `implements` hoặc field kết hợp là hợp lý.

**Bài tập 5 — Đánh giá API public.** Tìm những caller đang sử dụng đối tượng lớp con dưới kiểu lớp cha trước refactor. Ghi lại các lời gọi phụ thuộc quan hệ kế thừa và đề xuất adapter/đường chuyển đổi trước khi bỏ extends.

### Checklist sau refactor

- [ ] Vai trò của mỗi lớp có thể giải thích bằng một trách nhiệm rõ ràng.
- [ ] Lớp sử dụng phụ thuộc vào interface nhỏ, không biết cấu trúc của adapter cụ thể khi không cần thiết.
- [ ] Không để lộ các phương thức kế thừa không phù hợp với ngữ nghĩa lớp sử dụng.
- [ ] Các trường hợp thành công, lỗi, validation và giới hạn retry có test.
- [ ] Các caller và hợp đồng public được kiểm tra về tính tương thích.
- [ ] Các tác dụng phụ thực tế được kiểm thử tích hợp ở ranh giới hạ tầng.
- [ ] Kết hợp được dùng vì làm thiết kế rõ hơn, không chỉ để tránh từ khóa `extends`.

**Kết quả cần đạt:** Bạn có thể thay phương tiện gửi cảnh báo hoặc bổ sung retry bằng cách **lắp ghép đối tượng**, không sửa lớp nghiệp vụ và không tạo thêm phân cấp lớp con cho mỗi tổ hợp tính năng.