# receiveTimeout trong Spring JMS: chờ hữu hạn, không chờ và chờ không giới hạn

## 1. Mục tiêu học tập

Trong **Spring Framework JMS**, `JmsTemplate.receive(...)` và `JmsTemplate.receiveAndConvert(...)` thực hiện **nhận message đồng bộ**: thread gọi phương thức trực tiếp tham gia chờ message từ JMS destination. Nếu Queue chưa có thông điệp phù hợp, chương trình phải quyết định sẽ **chờ bao lâu**.

Thuộc tính **`receiveTimeout`** của `JmsTemplate` điều khiển ba cách hành xử:

1. **Chờ hữu hạn:** chờ tối đa một khoảng thời gian dương, ví dụ 2.000 ms; nếu không có message thì trả `null`.
2. **Không chờ:** kiểm tra message sẵn có ngay lúc nhận; nếu chưa có thì trả `null` mà không cố đợi message tới trong tương lai.
3. **Chờ không giới hạn:** thread có thể bị block cho tới khi có message, consumer bị đóng hoặc xuất hiện lỗi.

Cơ chế này đặc biệt quan trọng khi xây dựng job đồng bộ, thao tác kiểm tra Queue, API request/reply, công cụ quản trị hoặc worker pull-message. Đây là **timeout của thao tác nhận**, không phải timeout của HTTP, timeout kết nối broker, thời hạn sống của JMS message hay tần suất chạy `@JmsListener`.

```text
             JmsTemplate.receive("orders.in")
                            |
                   Có message ngay?
                      /          \
                    Có           Không
                    |             |
                 return        receiveTimeout
                 Message         /   |   \
                              > 0   < 0   = 0
                               |     |     |
                            chờ tối  không  chờ
                            đa N ms  chờ    vô hạn
                               |     |     |
                         message/  message/ message/
                           null     null    lỗi/đóng
```

**Kết quả `null` không tự chứng minh rằng destination vĩnh viễn không có dữ liệu**; nó chỉ cho biết thao tác nhận hiện tại không lấy được message theo chế độ chờ và điều kiện tại thời điểm đó.

## 2. Bảng giá trị chuẩn: dễ nhầm nhưng phải nhớ chính xác

Với **Spring Framework 6 / Spring JMS**, cách hiểu `JmsTemplate.setReceiveTimeout(long)` là:

| Giá trị | Chế độ | Lời gọi JMS nền tảng | Ý nghĩa khi chưa có message |
| --- | --- | --- | --- |
| `receiveTimeout > 0`, ví dụ `2_000L` | **Chờ hữu hạn** | `MessageConsumer.receive(2000)` | Có thể đợi khoảng tối đa 2 giây để nhận một message; quá hạn trả `null`. |
| `receiveTimeout = 0L` | **Chờ không giới hạn** | `MessageConsumer.receive()` hoặc ngữ nghĩa tương đương | Chờ đến khi message xuất hiện, consumer đóng hoặc xảy ra lỗi. |
| `receiveTimeout < 0L`, thường `-1L` | **Không chờ** | `MessageConsumer.receiveNoWait()` | Trả message đang sẵn có hoặc `null`, không đợi message xuất hiện trong tương lai. |

Hai hằng số được Spring định nghĩa trong `org.springframework.jms.support.destination.JmsDestinationAccessor`:

```java
JmsDestinationAccessor.RECEIVE_TIMEOUT_NO_WAIT
// giá trị -1L

JmsDestinationAccessor.RECEIVE_TIMEOUT_INDEFINITE_WAIT
// giá trị 0L
```

Trong `JmsTemplate` có thể dùng trực tiếp `setReceiveTimeout`:

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.JmsDestinationAccessor;

JmsTemplate template = new JmsTemplate(connectionFactory);

// Chỉ chờ hữu hạn 2 giây.
template.setReceiveTimeout(2_000L);

// Nếu muốn không chờ, thay dòng trên bằng:
template.setReceiveTimeout(
        JmsDestinationAccessor.RECEIVE_TIMEOUT_NO_WAIT);

// Nếu muốn chờ không giới hạn, thay bằng:
template.setReceiveTimeout(
        JmsDestinationAccessor.RECEIVE_TIMEOUT_INDEFINITE_WAIT);
```

Đây là **các lựa chọn cấu hình thay thế nhau**, không phải ba lệnh nên chạy liên tục trên cùng một bean trong sản phẩm thật. Biến `connectionFactory` ở đây là một `jakarta.jms.ConnectionFactory` đã được cấu hình; snippet không phải class chạy độc lập.

**Mặc định của `JmsTemplate` là chờ không giới hạn, tức giá trị `0L`.** Vì vậy, một lệnh `receive("orders.in")` trên Queue đang trống có thể chặn thread mãi nếu không cấu hình timeout.

### Cảnh báo về số 0 ở JMS API gốc

Jakarta Messaging định nghĩa `MessageConsumer.receive(long timeout)` như sau: **`receive(0)` cũng là chờ không giới hạn**. Để thăm dò tức thời, gọi `receiveNoWait()`.

Do đó, **sai** khi suy đoán `setReceiveTimeout(0)` nghĩa là “không chờ”. Trong Spring JMS, phải dùng giá trị **âm**, tốt nhất là hằng số `RECEIVE_TIMEOUT_NO_WAIT`.

## 3. Nhận đồng bộ trong JmsTemplate hoạt động thế nào?

Một lời gọi như:

```java
Message message = jmsTemplate.receive("orders.in");
```

thường diễn ra theo các bước:

1. `JmsTemplate` sử dụng `ConnectionFactory` để có JMS connection/session theo cấu hình và transaction context.
2. Spring resolve `"orders.in"` thành một `Destination` thích hợp (mặc định dùng Queue domain khi `pubSubDomain=false`).
3. Spring tạo `MessageConsumer` cho destination (và selector nếu có).
4. Spring gọi cách nhận tương ứng với `receiveTimeout`.
5. Nếu có message, phương thức trả lại `jakarta.jms.Message`. Nếu không có message trong giới hạn hoặc trong lần thăm dò, nó thường trả `null`.
6. Spring giải phóng consumer và quản lý session/connection/ack/commit theo contract của template.

`receiveTimeout` chủ yếu điều khiển **giai đoạn chờ message của consumer**, không phải cam kết rằng toàn bộ lời gọi Java (kể cả lookup destination, tạo connection, DNS, TLS, broker authentication, cleanup) phải hoàn tất đúng trong số mili-giây đã đặt.

Ví dụ đặt timeout 500 ms nhưng broker mất vài giây để kết nối hoặc hệ thống đang thiếu tài nguyên: **tổng thời gian thực thi có thể lớn hơn 500 ms**. Nếu ứng dụng có SLA HTTP chặt chẽ, cần thêm timeout ở tầng kết nối và giới hạn toàn request tương ứng.

### Message, null và exception

```java
jakarta.jms.Message msg = jmsTemplate.receive("orders.in");

if (msg == null) {
    System.out.println("Không có message trong lượt nhận");
} else {
    System.out.println("Đã nhận một JMS Message");
}
```

- Có message: trả object có thể là `TextMessage`, `BytesMessage`, `MapMessage`, v.v.
- Hết thời gian hoặc thăm dò không thấy message: trả `null`.
- Không kết nối được broker, sai quyền, provider lỗi, định dạng message không hỗ trợ: có thể ném một `org.springframework.jms.JmsException` hoặc exception liên quan. **Không** gộp mọi exception thành “Queue trống”.

Với `receiveAndConvert(...)`, Spring dùng `MessageConverter` để biến message thành payload. Ví dụ `TextMessage` thường được converter mặc định chuyển thành `String`. Nếu không nhận message, giá trị trả cũng là `null`; với converter tùy chỉnh, việc diễn giải `null` còn tùy contract chuyển đổi.

## 4. Chế độ 1: chờ hữu hạn (`receiveTimeout > 0`)

Chờ hữu hạn là lựa chọn nên cân nhắc cho phần lớn tác vụ đồng bộ vì thread không phải chờ vô thời hạn chỉ để đợi một Queue chưa có dữ liệu.

```java
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setReceiveTimeout(1_500L); // 1,5 giây

Object payload = template.receiveAndConvert("orders.in");

if (payload == null) {
    System.out.println("Hết lượt chờ hoặc chưa có message");
} else {
    System.out.println("Nhận: " + payload);
}
```

**Đây là snippet trong method có `connectionFactory` hợp lệ.** Nếu message xuất hiện sau 100 ms, phương thức có thể trả sớm; nếu Queue trống trong khoảng chờ, thường nhận `null` sau gần 1,5 giây. Thời gian đo được chỉ có tính tương đối do broker, OS scheduling, networking và overhead.

### Điều gì xảy ra nếu message tới ngay sát timeout?

Một message đến đúng ranh giới thời gian có thể được nhận trong lượt hiện tại hoặc chỉ còn khả dụng cho lượt sau, tùy scheduler và JMS provider. Không nên viết logic nghiệp vụ kiểu “chờ 1.000 ms thì chắc chắn mọi message gửi trước mốc 1.000 ms đều đã được nhận”.

### Chọn khoảng chờ thế nào?

| Tình huống | Gợi ý lựa chọn | Lý do |
| --- | --- | --- |
| HTTP endpoint chỉ có vài giây ngân sách | Một thời gian dương nhỏ hơn ngân sách toàn request | Không chiếm thread quá lâu; vẫn cần cộng thời gian kết nối/chuyển đổi. |
| Job kiểm tra kết quả định kỳ | 200 ms – vài giây tùy tải thực tế | Hạn chế vòng lặp quá nhanh nhưng cho phép shutdown. |
| CLI hay ứng dụng quản trị chờ phản hồi | Chờ hữu hạn và hiển thị “không có kết quả” nếu hết hạn | Tránh UI/terminal treo mãi. |
| Batch worker pull-message | Timeout dương + kiểm tra tín hiệu dừng | Có cơ hội thoát vòng lặp an toàn. |

Các con số là ví dụ để thiết kế, **không phải quy định bắt buộc của Spring hoặc broker**. Sự lựa chọn phải dựa vào nhu cầu xử lý, latency và giá trị thực tế đo được.

## 5. Chế độ 2: không chờ (`receiveTimeout < 0`)

Chế độ này tương ứng với `MessageConsumer.receiveNoWait()`: kiểm tra một message **đã sẵn sàng cho consumer ngay thời điểm nhận**, không đợi message mới đến.

```java
import org.springframework.jms.support.destination.JmsDestinationAccessor;

JmsTemplate polling = new JmsTemplate(connectionFactory);
polling.setReceiveTimeout(
        JmsDestinationAccessor.RECEIVE_TIMEOUT_NO_WAIT);

Object payload = polling.receiveAndConvert("orders.in");

System.out.println(
        payload == null ? "Không có message sẵn ngay"
                        : "Nhận: " + payload
);
```

**Cẩn thận với chữ “ngay”:**

- Không có giai đoạn **chờ message đến**, nhưng việc tạo connection/consumer, trao đổi với provider, phân giải tên Queue và cleanup **vẫn có chi phí thời gian**.
- `null` không chứng minh Queue đang rỗng tuyệt đối: có thể có consumer cạnh tranh, dispatch/prefetch chưa chuyển message tới consumer vừa tạo hoặc selector không khớp.
- Liên tục gọi `receiveNoWait` trong vòng lặp không nghỉ có thể gây **busy polling**, tăng CPU, network traffic và load broker.

Một vòng lặp polling có kiểm soát:

```java
while (running.get()) {
    Object payload = polling.receiveAndConvert("orders.in");

    if (payload != null) {
        process(payload);
    } else {
        Thread.sleep(250L);
    }
}
```

Đây là **đoạn minh họa cần biến `AtomicBoolean running` và method `process` đã được định nghĩa**; nó phải chạy trong một worker do ứng dụng quản lý và xử lý `InterruptedException` theo chính sách shutdown. Không sao chép nguyên đoạn vào Java class rồi kỳ vọng biên dịch nếu chưa khai báo các thành phần đó.

Trong hệ thống xử lý message liên tục, thay vì tự dựng vòng lặp, **`@JmsListener`** và listener container thường phù hợp hơn vì Spring quản lý concurrency, recovery và consumer lifecycle.

## 6. Chế độ 3: chờ không giới hạn (`receiveTimeout = 0`)

Khi không cấu hình gì thêm:

```java
JmsTemplate blocking = new JmsTemplate(connectionFactory);
// Giá trị mặc định tương đương:
// blocking.setReceiveTimeout(0L);

Object payload = blocking.receiveAndConvert("orders.in");
System.out.println("Nhận: " + payload);
```

Nếu Queue chưa có message thì thread có thể block **mãi**. Khi message đến, consumer được đóng hoặc JMS provider báo lỗi, lời gọi có thể trả về hoặc ném exception. **“Không giới hạn” không có nghĩa chương trình không thể bị ảnh hưởng bởi lỗi mạng, đóng connection hay transaction timeout.**

### Khi nào chờ vô hạn có thể chấp nhận?

- Một luồng chuyên trách có **lifecycle/cancellation** được thiết kế rõ, và có cách đóng consumer/connection phù hợp để thoát.
- Một công cụ demo cục bộ trong đó **message chắc chắn đã sẵn có** trước khi gọi `receive()`.
- Một hệ thống có quản trị riêng cho việc khởi động/dừng và đã kiểm thử hoạt động trong trường hợp broker gián đoạn.

### Khi nào nên tránh?

- Trong HTTP request thread: một Queue trống có thể chiếm hết thread pool và làm API chậm dần.
- Trong `@Scheduled` job hoặc `ApplicationRunner` mà không có đường thoát: startup/shutdown có thể bị mắc kẹt.
- Trong transaction hoặc luồng xử lý cần deadline: việc chờ vô hạn rất khó cân đối SLA.
- Khi sử dụng cơ chế polling với nhiều worker mà không có giám sát và chính sách hủy.

**Lưu ý về interruption:** không mặc định rằng `Thread.interrupt()` luôn phá được một `MessageConsumer.receive()` bị chặn trên mọi JMS provider. Phải thiết kế cơ chế shutdown theo contract consumer/connection và test trực tiếp provider đang dùng.

## 7. Dùng `receive`, `receiveAndConvert` và selector

`receiveTimeout` là thuộc tính của một **instance `JmsTemplate`**, không nằm riêng trong mỗi overload. Cùng cấu hình timeout được áp dụng khi gọi các phương thức nhận tương ứng.

| Method | Kết quả | Cách chọn đích |
| --- | --- | --- |
| `receive()` | `jakarta.jms.Message` hoặc `null` | Dùng default destination của template. |
| `receive("orders.in")` | `Message` hoặc `null` | Chọn destination theo tên. |
| `receive(destination)` | `Message` hoặc `null` | Dùng object `jakarta.jms.Destination`. |
| `receiveAndConvert("orders.in")` | Object payload hoặc `null` | Tự chuyển đổi message bằng converter. |
| `receiveSelected("orders.in", selector)` | `Message` hoặc `null` | Chỉ nhận các message có JMS headers/properties khớp selector. |
| `receiveSelectedAndConvert("orders.in", selector)` | Object payload hoặc `null` | Selector + converter. |

Ví dụ:

```java
template.setDefaultDestinationName("orders.in");
template.setReceiveTimeout(700L);

Message message = template.receive(); // dùng orders.in

Object payload = template.receiveAndConvert("orders.audit");
// dùng orders.audit nhưng vẫn chờ tối đa 700 ms cho thao tác nhận
```

Nếu gọi `receive()` khi chưa cấu hình default destination, Spring không biết phải nhận từ đâu và thường ném `IllegalStateException`; nó **không** trả `null` chỉ vì thiếu đích.

### Selector không tìm kiếm trong body

```java
template.setReceiveTimeout(1_000L);

Message invoice = template.receiveSelected(
        "orders.in",
        "eventType = 'INVOICE'"
);
```

Selector ở đây đối chiếu **JMS headers/properties** thích hợp, ví dụ property `eventType`; nó không tự đọc JSON body để tìm khóa `eventType`. Nếu Queue có message nhưng **không message nào khớp selector**, lời gọi vẫn có thể hết hạn và trả `null`.

Một consumer khác có thể nhận cùng Queue trước, vì vậy `null` cũng không đồng nghĩa message đã bị mất hay broker chưa từng chứa message.

## 8. Cấu hình bằng Spring Framework thuần

Ví dụ khai báo bean trong ứng dụng Spring Framework 6 đã có `jakarta.jms.ConnectionFactory`:

```java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.JmsDestinationAccessor;

@Configuration
public class ReceiveTimeoutConfig {

    @Bean("boundedJmsTemplate")
    public JmsTemplate boundedJmsTemplate(ConnectionFactory factory) {
        var template = new JmsTemplate(factory);
        template.setDefaultDestinationName("orders.in");
        template.setReceiveTimeout(1_000L);
        return template;
    }

    @Bean("pollingJmsTemplate")
    public JmsTemplate pollingJmsTemplate(ConnectionFactory factory) {
        var template = new JmsTemplate(factory);
        template.setReceiveTimeout(
                JmsDestinationAccessor.RECEIVE_TIMEOUT_NO_WAIT);
        return template;
    }

    @Bean("blockingJmsTemplate")
    public JmsTemplate blockingJmsTemplate(ConnectionFactory factory) {
        var template = new JmsTemplate(factory);
        template.setReceiveTimeout(
                JmsDestinationAccessor.RECEIVE_TIMEOUT_INDEFINITE_WAIT);
        return template;
    }
}
```

Đây là một class Java biên dịch được khi có Spring JMS/Jakarta Messaging và `ConnectionFactory` bean hợp lệ. **Không** có bean `ConnectionFactory` được định nghĩa trong class này: ứng dụng phải khai báo hoặc để Boot tạo bean từ provider.

Trong service có nhiều bean cùng kiểu `JmsTemplate`, cần chọn bean bằng `@Qualifier`:

```java
public OrderPullService(
        @Qualifier("boundedJmsTemplate") JmsTemplate template) {
    this.template = template;
}
```

Đoạn constructor ở trên nằm trong class `OrderPullService` có field `JmsTemplate template`, cần import `org.springframework.beans.factory.annotation.Qualifier` và `org.springframework.jms.core.JmsTemplate`.

**Không đổi `setReceiveTimeout` liên tục trên một singleton JmsTemplate đang được nhiều thread sử dụng.** Instance template được thiết kế để dùng chung sau khi cấu hình hoàn chỉnh; thay timeout tại runtime có thể khiến request A vô tình sử dụng timeout do request B đặt. Nếu có nhiều chính sách chờ, dùng nhiều template độc lập được inject bằng qualifier hoặc tạo template riêng phù hợp với từng tác vụ.

## 9. Spring Boot: cấu hình `spring.jms.template.receive-timeout`

Spring Boot hỗ trợ bind timeout cho `JmsTemplate` được auto-configured:

```yaml
# src/main/resources/application.yml
spring:
  jms:
    pub-sub-domain: false
    template:
      default-destination: orders.in
      receive-timeout: 2s
```

Ở đây `2s` là **2 giây**; Spring Boot chuyển thành timeout ở mức mili-giây khi cấu hình template. Có thể dùng các đơn vị thời gian dễ đọc như `500ms`, `2s`. Khai báo một số nguyên không kèm hậu tố có thể dễ gây hiểu lầm; nên ghi đơn vị rõ ràng.

Ba chế độ có thể biểu đạt qua property:

```yaml
# CHỌN một giá trị cho spring.jms.template.receive-timeout:
receive-timeout: 1500ms   # hữu hạn
receive-timeout: -1ms     # không chờ
receive-timeout: 0ms      # chờ không giới hạn
```

Đây là **ba dòng thay thế nhau**, không phải ba khóa YAML lặp lại trong một cấu hình hợp lệ.

**Lưu ý:** khi tự `new JmsTemplate(connectionFactory)` và khai báo bean tùy chỉnh, không nên mặc định rằng property của Spring Boot được tự động áp dụng lên mọi instance. Cần dùng auto-configuration phù hợp hoặc tự gọi `setReceiveTimeout`.

### `spring.jms.listener.receive-timeout` không phải cùng một cấu hình

Spring Boot còn có một property khác:

```yaml
spring:
  jms:
    listener:
      receive-timeout: 1s
```

Property này liên quan **chu kỳ nhận trong JMS listener container** do Boot cấu hình, **không phải timeout cho `JmsTemplate.receive(...)`**. Listener container thường cần cơ hội trở về từ receive để kiểm tra tín hiệu shutdown/recovery; đặt listener receive vô hạn không suy ra nó cũng an toàn như template riêng.

Tóm lại:

| Property | Phạm vi |
| --- | --- |
| `spring.jms.template.receive-timeout` | Các thao tác nhận đồng bộ qua auto-configured `JmsTemplate`; cũng có thể ảnh hưởng chờ reply trong `sendAndReceive` của chính template. |
| `spring.jms.listener.receive-timeout` | Thao tác receive nội bộ của listener container; ảnh hưởng kiểm tra dừng/recovery. |
| `spring.jms.template.default-destination` | Tên destination mặc định nếu lệnh template không truyền đích. |
| `spring.jms.template.time-to-live` | Thời gian sống của message **được gửi**, không phải thời gian chờ nhận. |

Không nhầm timeout của JMS listener với timeout của HTTP hay timeout toàn bộ công việc.

## 10. Demo Java 17/Spring Boot/Artemis: quan sát đủ ba chế độ

Ví dụ dưới đây là một ứng dụng **Java 17 + Spring Boot 3.3.x + ActiveMQ Artemis**, không cần tự cài một JMS server vào classpath ứng dụng. Dùng các Queue thử nghiệm có tên riêng:

- `demo.timeout.empty`: giả định **trống** trong cả hai lần kiểm tra đầu.
- `demo.timeout.ready`: producer gửi trước một message, sau đó consumer nhận trong chế độ “chờ không giới hạn” để **không vô tình làm ví dụ treo**.

### 10.1. Chạy Artemis bằng Docker

Nếu máy có Docker:

```bash
docker run --detach --rm --name artemis-timeout-demo -p 61616:61616 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:2.57.0-alpine
```

Đợi broker sẵn sàng và kiểm tra `docker logs artemis-timeout-demo`. Tên Queue `demo.timeout.empty` và `demo.timeout.ready` cần được **provision** hoặc broker phải cho phép tạo tự động. Đây là tài khoản/môi trường thử nghiệm cục bộ; production phải bảo vệ broker bằng cấu hình xác thực và TLS phù hợp.

### 10.2. Cấu trúc dự án

```text
receive-timeout-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── resources/application.yml
    └── java/example/jms/ReceiveTimeoutApplication.java
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'receive-timeout-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Tệp `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
  jms:
    pub-sub-domain: false
```

Đây là kết nối **native** đến broker bên ngoài. Spring Boot tạo `ConnectionFactory` phù hợp cho Artemis. Ví dụ tự tạo ba template để thể hiện rõ ba chế độ timeout, thay vì ghi đè một singleton liên tục trong khi các request khác đang chạy.

### 10.3. File Java đầy đủ

Tạo `src/main/java/example/jms/ReceiveTimeoutApplication.java`:

```java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.JmsDestinationAccessor;

@SpringBootApplication
public class ReceiveTimeoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReceiveTimeoutApplication.class, args);
    }

    @Bean
    ApplicationRunner demonstrate(ConnectionFactory connectionFactory) {
        return args -> {
            String emptyQueue = "demo.timeout.empty";
            String readyQueue = "demo.timeout.ready";

            // 1) Chờ hữu hạn: 250 ms.
            JmsTemplate finite = new JmsTemplate(connectionFactory);
            finite.setReceiveTimeout(250L);
            Object a = finite.receiveAndConvert(emptyQueue);
            System.out.println("FINITE: " + describe(a));

            // 2) Không chờ: -1 ms.
            JmsTemplate noWait = new JmsTemplate(connectionFactory);
            noWait.setReceiveTimeout(
                    JmsDestinationAccessor.RECEIVE_TIMEOUT_NO_WAIT);
            Object b = noWait.receiveAndConvert(emptyQueue);
            System.out.println("NO_WAIT: " + describe(b));

            // 3) Chờ không giới hạn: 0 ms.
            // Gửi trước để tránh demo bị chặn vô hạn trên Queue trống.
            JmsTemplate sender = new JmsTemplate(connectionFactory);
            sender.convertAndSend(readyQueue, "READY");

            JmsTemplate indefinite = new JmsTemplate(connectionFactory);
            indefinite.setReceiveTimeout(
                    JmsDestinationAccessor.RECEIVE_TIMEOUT_INDEFINITE_WAIT);
            Object c = indefinite.receiveAndConvert(readyQueue);
            System.out.println("INDEFINITE: " + describe(c));
        };
    }

    private static String describe(Object result) {
        return result == null ? "NONE" : result.toString();
    }
}
```

Điểm cần để ý:

1. Cả ba template đều dùng cùng **`ConnectionFactory`**, nhưng mỗi template có policy chờ riêng.
2. `finite` và `noWait` đều đọc cùng một Queue **được giả định trống**, nên phần kết quả minh họa không phụ thuộc vào việc message xuất hiện muộn.
3. `indefinite` là template `0L` thật, nhưng **producer đã gửi `"READY"` trước**, nên trong điều kiện broker hoạt động, thông điệp đang có sẵn và không cần chờ lâu.
4. `receiveAndConvert` biến `TextMessage("READY")` thành `String` khi dùng converter mặc định phù hợp.
5. Không có `@JmsListener` cạnh tranh trong demo: cả ba lần nhận là **đồng bộ trên thread chạy `ApplicationRunner`**.

### 10.4. Chạy và kết quả

Với JDK 17 và Gradle 8.x tương thích Spring Boot 3.3.x:

```bash
gradle bootRun
```

Nếu có Gradle Wrapper, Linux/macOS dùng `./gradlew bootRun`, Windows dùng `gradlew.bat bootRun`.

Khi broker sạch, hai Queue được tạo hợp lệ, message `"READY"` được gửi/nhận thành công và không có consumer cạnh tranh, các dòng do ứng dụng in ra là:

```text
FINITE: NONE
NO_WAIT: NONE
INDEFINITE: READY
```

Đây là **kết quả dự kiến với các điều kiện nêu trên**, không phải log đã thu từ một lần chạy thực tế trong bài. Ngoài những dòng này còn có log khởi động của Spring Boot. Nếu `demo.timeout.empty` còn message từ lần chạy trước, hai dòng đầu có thể không còn là `NONE`. Nếu broker lỗi hoặc destination không được provision, ứng dụng có thể ném exception thay vì in đủ ba dòng.

Khi xong, dừng broker:

```bash
docker stop artemis-timeout-demo
```

### 10.5. Thử chế độ chờ hữu hạn khi message đến trễ

Muốn thấy `receive(2_000)` trả về **sớm hơn 2 giây** khi message đến, có thể dùng một luồng producer độc lập gửi sau khoảng 500 ms. Đây là một đoạn **thí nghiệm riêng** (không dán trực tiếp vào sample mà không xử lý thread lifecycle):

```java
try (var executor = java.util.concurrent.Executors
        .newSingleThreadExecutor()) {
    executor.submit(() -> {
        Thread.sleep(500L);
        sender.convertAndSend("demo.timeout.delayed", "ARRIVED");
        return null;
    });

    finite.setReceiveTimeout(2_000L);
    Object result = finite.receiveAndConvert("demo.timeout.delayed");
    System.out.println("DELAYED: " + result);
}
```

**Lưu ý quan trọng:** `ExecutorService` chỉ có `AutoCloseable` trong **Java 19+**, nên đoạn `try-with-resources` ở trên không dành cho Java 17. Nếu thực hành bằng Java 17, hãy sử dụng phiên bản đúng dưới đây:

```java
java.util.concurrent.ExecutorService executor =
        java.util.concurrent.Executors.newSingleThreadExecutor();

try {
    executor.submit(() -> {
        Thread.sleep(500L);
        sender.convertAndSend("demo.timeout.delayed", "ARRIVED");
        return null;
    });

    finite.setReceiveTimeout(2_000L);
    Object result = finite.receiveAndConvert("demo.timeout.delayed");
    System.out.println("DELAYED: " + result);
} finally {
    executor.shutdown();
}
```

Đoạn Java 17 hợp lệ này được dùng **bên trong method có biến `sender` và `finite`**, cần Queue `demo.timeout.delayed` tồn tại hoặc được phép tạo. Trong môi trường bình thường, bạn có thể thấy `DELAYED: ARRIVED`, nhưng không có bảo đảm tuyệt đối về mốc 500 ms vì thread scheduling và broker startup. Nếu producer task thất bại mà consumer đặt timeout 2 giây, người gọi sẽ thoát ra với `null` thay vì đợi vô hạn. Trong code production, cần kiểm tra `Future` của producer để không bỏ sót lỗi gửi.

## 11. Chờ message và chờ reply: không trộn thời hạn

Một ứng dụng request-reply thường dùng `JmsTemplate.sendAndReceive(...)` để gửi request, rồi chờ reply trên một response destination thích hợp. Trong Spring JMS, cơ chế `sendAndReceive` của `JmsTemplate` cũng dùng **`receiveTimeout`** khi chờ response.

Ví dụ:

```java
JmsTemplate rpc = new JmsTemplate(connectionFactory);
rpc.setReceiveTimeout(3_000L);

Message reply = rpc.sendAndReceive(
        "orders.requests",
        session -> session.createTextMessage("STATUS:42")
);
```

Đây là snippet trong method có `connectionFactory`; cần import `jakarta.jms.Message`. Tùy phiên bản/overload, Spring có thể dùng temporary reply Queue, đặt `JMSReplyTo` trên request, rồi đợi response. Nếu không có reply phù hợp trong thời hạn, kết quả có thể là `null`.

**Đừng nhầm các mốc thời gian:**

| Thiết lập | Điều khiển điều gì? |
| --- | --- |
| `receiveTimeout` | Thời gian chờ message/reply của thao tác nhận tương ứng trên template. |
| `timeToLive` / JMSExpiration | Thời gian sống của message sau khi **gửi**; quá hạn có thể bị broker expire. |
| `deliveryDelay` | Thời gian yêu cầu broker trì hoãn delivery của message gửi. |
| HTTP client timeout | Khoảng thời gian HTTP client chịu chờ server. |
| Business SLA/deadline | Ngân sách thời gian toàn quy trình nghiệp vụ. |

Một request hết hạn trước khi consumer xử lý sẽ không tự có reply. Một client chờ 3 giây rồi timeout có thể bỏ lỡ reply đến muộn dù message phản hồi vẫn còn tồn tại trên broker. Do đó, request-reply cần **correlation ID, retry/idempotency và cleanup** phù hợp, không chỉ đặt một giá trị `receiveTimeout`.

Trong hệ thống thực tế, không nên dùng `receiveTimeout=0` mặc định cho một HTTP request đang chờ remote service, vì request có thể bị treo và giữ tài nguyên.

## 12. Nhận đồng bộ khác gì listener bất đồng bộ?

### `JmsTemplate.receive`: người gọi chủ động chờ

```java
Object msg = template.receiveAndConvert("orders.in");
// Chỉ chạy tiếp khi nhận message, hết timeout hoặc lỗi.
```

**Thread gọi** phương thức bị giữ cho đến khi thao tác nhận hoàn tất. Nếu Queue có ít message, mỗi lần polling tạo consumer tạm thời và có thể có overhead. Cách này hợp lý cho công cụ, job hữu hạn hoặc tích hợp request-reply đặc thù.

### `@JmsListener`: container tự quản lý consumer

```java
@JmsListener(destination = "orders.in")
public void onMessage(String text) {
    System.out.println("Received: " + text);
}
```

Đây là method trong Spring bean, cần `@EnableJms` hoặc auto-registration phù hợp. Listener container duy trì consumer và dispatch khi message đến; không cần tự viết vòng lặp `receive()` trong code nghiệp vụ.

**Cảnh báo Queue cạnh tranh:** nếu một `@JmsListener` và `JmsTemplate.receive` cùng đọc một Queue, chúng là các consumer cạnh tranh. Một message có thể vào listener trước khi `receive` lấy được, nên lời gọi đồng bộ có thể trả `null` dù nhà sản xuất vừa gửi message. Không thể suy từ kết quả đó rằng JMS bị lỗi.

### Trường hợp nào chọn cách nào?

- Nhận liên tục, concurrency cao, recovery/giám sát: thường chọn listener container.
- Cần kiểm tra một lần hay chờ một kết quả có deadline: nhận đồng bộ với **timeout dương**.
- Muốn kiểm tra Queue tức thời để hỗ trợ vận hành: **no-wait**, nhưng tránh busy loop.
- Cố tình chờ mãi: chỉ dùng trong context kiểm soát được shutdown và exception.

## 13. Timeout không phải transaction, ACK hay redelivery policy

`receiveTimeout` quyết định **thời gian chờ một message**, không quyết định:

- Session dùng `AUTO_ACKNOWLEDGE`, `CLIENT_ACKNOWLEDGE` hay transaction.
- Khi nào local/JTA transaction commit hoặc rollback.
- Message nhận xong có thể redeliver khi consumer crash hay không.
- Message có bị lọc bằng selector hoặc hết hạn TTL hay không.
- Queue có bao nhiêu consumer cạnh tranh hoặc số lần retry.

Ví dụ:

```java
template.setReceiveTimeout(500L);
Message message = template.receive("orders.in");

if (message != null) {
    // Xử lý nghiệp vụ cần idempotency và transaction phù hợp.
    handleBusinessEvent(message);
}
```

Đây là snippet cần method `handleBusinessEvent` được khai báo. Nếu `template.receive` đã trả message, trách nhiệm ACK/transaction còn tùy cấu hình session/template/provider. **Không** giả định việc đặt timeout ngắn làm message “an toàn hơn” hoặc tự giải quyết duplication.

Trong một transaction đang hoạt động, deadline giao dịch và transaction-aware session management cũng có thể ảnh hưởng việc chờ/commit. Muốn bảo đảm deadline toàn nghiệp vụ, kiểm tra rõ transaction manager và cả thời gian mở connection, gửi/nhận, chuyển đổi, ghi DB.

### Null không phải rollback

Nếu `receive` trả `null`, nghĩa là thao tác hiện tại không nhận được JMS message phù hợp; thông thường không có body để xử lý/ACK. Không nên coi đây là lỗi bắt buộc phải rollback transaction; ứng dụng có thể chọn “no work”, retry sau, hoặc kết thúc job một cách bình thường.

## 14. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách sửa đúng |
| --- | --- | --- |
| Gọi `setReceiveTimeout(0)` nhưng ứng dụng treo | `0` là **chờ vô hạn**, không phải no-wait. | Dùng `RECEIVE_TIMEOUT_NO_WAIT` (`-1L`) hoặc timeout dương. |
| Gọi `setReceiveTimeout(-1)` rồi thấy `null` dù Queue có message | Thăm dò ngay, message chưa được dispatch hoặc consumer khác nhận. | Nếu muốn đợi message, dùng timeout dương; kiểm tra broker và consumer cạnh tranh. |
| Đặt `2_000L` nhưng mất hơn 2 giây | Timeout áp dụng chủ yếu cho giai đoạn `receive`, chưa bao gồm connect/setup/cleanup. | Đo từng bước; cấu hình connect timeout và deadline ở tầng gọi. |
| `receive()` không biết nhận từ đâu | Thiếu default destination trên template. | Gọi `receive("queue")` hoặc `setDefaultDestinationName("queue")`. |
| Có Queue message nhưng `receiveSelected` luôn `null` | Selector không khớp JMS properties/header. | Kiểm tra selector và properties, không tìm theo JSON body. |
| `receiveAndConvert` trả `null` | Không có message trong lượt nhận hoặc converter tùy biến trả null. | Thử raw `receive`, kiểm tra converter và broker. |
| Đặt `spring.jms.listener.receive-timeout` nhưng `JmsTemplate` vẫn block | Đây là property của listener container, không phải template. | Đặt `spring.jms.template.receive-timeout` hoặc gọi setter trên template. |
| Đặt `spring.jms.template.receive-timeout` nhưng bean custom không đổi | Tự tạo `new JmsTemplate` mà không áp thuộc tính. | Cấu hình trực tiếp custom bean hoặc dùng Boot auto-config. |
| `receive` trả message khác loại kỳ vọng | Có nhiều message type/producer trên Queue, converter hoặc selector chưa phù hợp. | Đọc raw headers/type; dùng converter/schema đúng. |
| API chậm hoặc cạn thread | Chờ vô hạn hoặc timeout quá dài trong mỗi HTTP request. | Giảm timeout, dùng async listener/service hoặc giải pháp event-driven. |
| CPU/broker load cao dù không có message | Polling no-wait lặp quá nhanh, không backoff. | Dùng chờ hữu hạn, delay/backoff hoặc listener. |
| Message “biến mất” khỏi lượt nhận của mình | Consumer khác trên Queue đã nhận. | Kiểm tra concurrency, routing, consumer groups/provider policy. |
| Gặp `JmsException` | Broker mất kết nối, sai quyền, session lỗi. | Log root cause và kiểm tra provider, không nuốt lỗi thành “không có message”. |
| Worker không chịu dừng | Có lệnh nhận vô hạn đang block và provider không thoát chỉ nhờ interrupt. | Chuyển timeout dương, thiết kế shutdown đóng resource đúng contract. |

Một quy trình debug thực tế:

1. Ghi lại template bean đang dùng và **`getReceiveTimeout()`**.
2. Xác minh destination name, Queue/Topic domain, `DestinationResolver` và selector.
3. Kiểm tra broker log: kết nối, quyền, Queue depth, dispatched message, consumer count.
4. Xác nhận có consumer cạnh tranh hay không; thử trên Queue sạch và consumer duy nhất.
5. Đo thời gian **toàn lời gọi** rồi phân biệt thời gian mở connection/resolve với thời gian chờ message.
6. Kiểm tra ACK, transaction, redelivery và converter nếu message đã nhận nhưng ứng dụng không thấy payload kỳ vọng.

## 15. Kiểm thử nên có

### Unit test

Với code thuần tùy chọn timeout, không nên giả định một `JmsTemplate` mock sẽ tự chạy ngữ nghĩa `receive`. Có thể kiểm tra cấu hình bean:

```java
assertEquals(1_000L, boundedTemplate.getReceiveTimeout());
assertEquals(-1L, pollingTemplate.getReceiveTimeout());
assertEquals(0L, blockingTemplate.getReceiveTimeout());
```

Đây là đoạn **JUnit assertion minh họa** trong test đã có ba bean template phù hợp; cần import `org.junit.jupiter.api.Assertions.assertEquals`.

Kiểm tra setter/hằng số giúp tránh lỗi nhập `0` và `-1` nhưng **không thay thế** test nhận message thực tế.

### Integration test với broker

1. Tạo Queue sạch không có consumer khác.
2. Với template `-1`, gọi `receive` trên Queue trống, xác nhận trả `null` (nhưng không đặt điều kiện thời gian chính xác tới mili-giây).
3. Với template `300L`, gọi nhận trên Queue trống, xác nhận trả `null` sau khoảng thời gian chờ hữu hạn, cho phép sai số môi trường.
4. Gửi một `TextMessage`, rồi dùng template `0L` để nhận; gửi **trước** để tránh test treo.
5. Gửi message sau một độ trễ nhỏ bằng producer chạy riêng và xác nhận template hữu hạn có thể nhận trước hạn.
6. Kiểm tra selector không khớp trên Queue đang có message; xác nhận việc chờ/không chờ dựa trên **message phù hợp**, không dựa trên tổng số message trong Queue.
7. Chạy thử khi broker mất kết nối; kiểm tra exception được phân biệt với `null`.
8. Nếu sản phẩm dùng HTTP hoặc transaction, đo toàn deadline; bổ sung test cancellation/shutdown thay vì chỉ test happy path.

Nên tránh `assertEquals(300, elapsedMillis)` vì scheduling, broker dispatch, network và thời gian tạo resource có sai số. Thay bằng một khoảng hợp lý, cộng quan sát metric/log khi cần.

## 16. Bài tập tự kiểm tra

**Câu 1.** `receiveTimeout=0` thì `receive("orders.in")` trả về `null` ngay khi Queue trống, đúng hay sai?

**Đáp án:** **Sai**. Giá trị `0` là **chờ không giới hạn**; thread có thể block đến khi có message, consumer bị đóng hoặc lỗi.

**Câu 2.** Muốn kiểm tra message sẵn có mà không đợi message mới xuất hiện, dùng giá trị nào?

**Đáp án:** Một giá trị **âm**, thường là `JmsDestinationAccessor.RECEIVE_TIMEOUT_NO_WAIT` (`-1L`).

**Câu 3.** Giá trị `1_500L` có chắc khiến toàn bộ `receiveAndConvert` luôn hoàn thành trong tối đa đúng 1,5 giây?

**Đáp án:** Không. Đây là timeout **cho việc chờ message**, chưa phải deadline bao trùm việc kết nối, tạo consumer, xử lý converter và cleanup.

**Câu 4.** Nếu một Queue có hai consumer và message được giao cho consumer A, consumer B nhận `null` sau timeout có nghĩa broker mất message?

**Đáp án:** Không. Với Queue, các consumer cạnh tranh; một message đã được giao cho A thì B có thể không nhận nó.

**Câu 5.** `spring.jms.listener.receive-timeout` có cấu hình `JmsTemplate.receive` không?

**Đáp án:** Không. Đây là cấu hình cho listener container; template dùng `spring.jms.template.receive-timeout` hoặc `setReceiveTimeout` trực tiếp.

**Câu 6.** `MessageConsumer.receive(0)` theo API JMS chuẩn là không chờ, đúng không?

**Đáp án:** **Không**. Theo Jakarta Messaging, `receive(0)` có nghĩa **chờ vô hạn**; thăm dò tức thời là `receiveNoWait()`.

**Câu 7.** `receiveSelected("orders.in", "type = 'X'")` hết thời gian và trả `null`, trong khi Queue có message `type='Y'`. Kết quả có hợp lý không?

**Đáp án:** Có. Consumer với selector chỉ nhận message khớp; các message `Y` không phải đầu vào phù hợp cho lượt nhận đó.

**Câu 8.** Khi nào nên dùng chờ không giới hạn?

**Đáp án:** Chỉ khi có môi trường kiểm soát resource, lifecycle và shutdown rõ ràng; tránh trong HTTP thread hoặc worker không có cơ chế hủy.

## 17. Tài liệu chính thức

- [Spring Framework – Receiving a Message (Synchronous Receipt)](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework 6.2 – JmsTemplate: setReceiveTimeout và receive](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Spring Framework 6.2 – JmsDestinationAccessor: RECEIVE_TIMEOUT_NO_WAIT / INDEFINITE_WAIT](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/destination/JmsDestinationAccessor.html)
- [Spring Framework – JmsTemplate API hằng số và JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/constant-values.html)
- [Spring Boot 3 – Cấu hình JMS](https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html)
- [Spring Boot – Common Application Properties: spring.jms.template.receive-timeout](https://docs.spring.io/spring-boot/3.4/appendix/application-properties/)
- [Jakarta Messaging 3.1 – MessageConsumer.receive / receiveNoWait](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageconsumer)
- [Apache ActiveMQ Artemis – Hướng dẫn chạy broker bằng Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)

**Ghi nhớ quan trọng nhất:** Trong **Spring JMS `JmsTemplate`**, **giá trị dương = chờ hữu hạn**, **`-1` (âm) = không chờ**, **`0` = chờ không giới hạn**. Chọn timeout theo mục tiêu nghiệp vụ và lifecycle thread, xử lý `null` khác với `JmsException`, và đừng nhầm timeout của template với timeout của listener hoặc TTL của message.
