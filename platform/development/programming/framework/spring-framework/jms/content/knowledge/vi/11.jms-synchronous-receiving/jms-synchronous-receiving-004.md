# receiveSelected với biểu thức lọc trong Spring JMS

## 1. Mục tiêu và bài toán

Trong Spring JMS, phương thức `JmsTemplate.receive(destination)` lấy một message phù hợp với destination được chỉ định. Khi cùng một Queue chứa nhiều loại sự kiện, nhiều tenant hay nhiều mức ưu tiên nghiệp vụ, ứng dụng đôi khi chỉ muốn **nhận đồng bộ những message có metadata thỏa điều kiện**.

`JmsTemplate.receiveSelected(destinationName, selector)` là API dành cho tình huống đó. Nó tạo một JMS consumer có **message selector**; provider đánh giá selector trên **JMS headers và JMS properties**, rồi mới giao những message match cho consumer.

~~~java
Message message = jmsTemplate.receiveSelected(
        "orders.queue",
        "tenant = 'north' AND amount >= 100");
~~~

Đây không phải hàm truy vấn database, không dùng SQL `SELECT`, và cũng không phải phép lọc JSON body. Nó là **một lời gọi nhận đồng bộ có thể block**, theo receive timeout được cấu hình.

Ví dụ:

~~~text
Queue orders.queue
  |
  +-- order-1: tenant=north; amount=50
  +-- order-2: tenant=north; amount=150
  +-- order-3: tenant=south; amount=300
  |
  v
receiveSelected(
  "orders.queue",
  "tenant = 'north' AND amount >= 100"
)
  |
  +-- Nhận order-2
  +-- order-1, order-3 không bị consumer này lấy
~~~

Trong **Queue**, message không match có thể tiếp tục chờ một consumer khác (hoặc một lần nhận khác có selector phù hợp), theo chính sách broker. Không nên hiểu `receiveSelected` là gọi `receive` lấy message bất kỳ rồi tự bỏ message không phù hợp.

Mục tiêu bài học:

1. Hiểu hợp đồng `receiveSelected` và `receiveSelectedAndConvert` của Spring.
2. Viết selector với so sánh, `AND`, `OR`, `NOT`, `IN`, `BETWEEN`, `LIKE` và `IS NULL`.
3. Phân biệt JMS properties/headers với JSON body.
4. Xử lý đúng kiểu property, logic ba giá trị `TRUE/FALSE/UNKNOWN`, timeout và kết quả `null`.
5. Xây ví dụ Spring Boot + Artemis + Java 17 có thể chạy được.
6. Phân tích transaction/ACK, competing consumers, hiệu năng, an toàn và kiểm thử.

## 2. Vị trí của API trong Spring

`org.springframework.jms.core.JmsOperations` là interface tập hợp các thao tác JMS, còn `org.springframework.jms.core.JmsTemplate` là implementation thường dùng. Trong Spring Framework 6:

| API | Giá trị trả về | Ý nghĩa |
| --- | --- | --- |
| `receive(String destinationName)` | `jakarta.jms.Message` hoặc `null` | Nhận không có selector |
| `receiveSelected(String destinationName, String messageSelector)` | `Message` hoặc `null` | Nhận raw JMS message theo selector |
| `receiveSelectedAndConvert(String destinationName, String messageSelector)` | `Object` hoặc `null` | Nhận theo selector và chuyển đổi body bằng converter |
| `receiveSelected(String messageSelector)` | `Message` hoặc `null` | Dùng **default destination** đã cấu hình |
| `receiveSelectedAndConvert(String messageSelector)` | `Object` hoặc `null` | Chuyển đổi message từ default destination |
| `receiveSelected(Destination destination, String messageSelector)` | `Message` hoặc `null` | Dùng JMS `Destination` object thay cho tên |

**Lưu ý overload:** lời gọi có **một** String như `receiveSelected("tenant = 'north'")` nhận tham số selector, không phải tên Queue. Muốn nêu cả Queue và filter, dùng overload **hai** tham số.

Các API thuộc Spring JMS chứ không phải API gốc `jakarta.jms.MessageConsumer`. Spring sẽ sử dụng `ConnectionFactory`, `Session` và `MessageConsumer` bên dưới và chuyển checked `JMSException` thành runtime `org.springframework.jms.JmsException`.

~~~text
Application thread
      |
      v
JmsOperations / JmsTemplate
      |
      +-- ConnectionFactory và Session
      +-- MessageConsumer(destination, selector)
      |
      v
JMS broker/provider
      |
      +-- Chọn message match từ header/property
      |
      v
Message hoặc null khi timeout
~~~

### 2.1. Vì sao nhận đồng bộ khác listener?

- `receiveSelected` do thread nghiệp vụ chủ động gọi; thread có thể chờ.
- `@JmsListener(selector = "...")` chạy trong listener container do Spring quản lý, phù hợp xử lý liên tục.
- Cả hai có thể sử dụng cùng một cú pháp JMS selector nhưng vòng đời resource, thời gian chờ và mô hình concurrency khác nhau.
- Một lời gọi `receiveSelected` thành công **tiêu thụ** message theo chính sách ACK/transaction; không phải một lệnh “peek”.

## 3. Selector chỉ nhìn metadata, không đọc JSON body

Producer gửi JSON:

~~~java
jmsTemplate.convertAndSend(
        "orders.queue",
        "{\"orderId\":\"O-42\",\"region\":\"VN\",\"amount\":150}",
        message -> {
            message.setStringProperty("region", "VN");
            message.setIntProperty("amount", 150);
            message.setStringProperty("eventType", "order.created");
            return message;
        });
~~~

Đoạn trên có hai phần độc lập:

- **Body:** String JSON chứa các trường `orderId`, `region`, `amount`.
- **JMS properties:** `region` dạng String, `amount` dạng int, `eventType` dạng String.

Selector hợp lệ:

~~~sql
region = 'VN' AND amount >= 100 AND eventType = 'order.created'
~~~

Selector **không thể** đọc trường JSON như:

~~~sql
body.region = 'VN'
JSON_VALUE(body, '$.amount') >= 100
~~~

Hai dòng trên không phải biểu thức selector chuẩn JMS. Nếu producer chỉ để `region` trong body mà không gọi `setStringProperty("region", "VN")`, filter `region = 'VN'` sẽ không match.

**Nguyên tắc thiết kế:** những trường cần broker chọn lọc nên được xuất bản thành property có tên và kiểu dữ liệu ổn định. Dữ liệu nghiệp vụ chi tiết ở trong body. Nếu selector cần xem quá nhiều trường JSON, hãy cân nhắc cách phân tách Queue hoặc routing, thay vì sao chép toàn bộ payload lên properties.

### 3.1. Những JMS header được phép tham chiếu

Jakarta Messaging 3.1 chỉ cho phép tham chiếu trực tiếp các standard JMS header fields sau trong selector:

- `JMSDeliveryMode`
- `JMSPriority`
- `JMSMessageID`
- `JMSTimestamp`
- `JMSCorrelationID`
- `JMSType`

Ví dụ:

~~~sql
JMSType = 'order.created'
JMSPriority >= 6
JMSCorrelationID = 'corr-42'
~~~

Không coi mọi header có prefix `JMS` đều portable trong selector. `JMSRedelivered`, `JMSDestination`, `JMSReplyTo`, `JMSExpiration` và `JMSDeliveryTime` không thuộc danh sách header tham chiếu chuẩn nói trên; một provider có thể có extension nhưng phải kiểm chứng riêng.

`JMSX...` là vùng property do Jakarta Messaging định nghĩa; `JMS_...` là vùng provider-specific; application properties thông thường nên dùng tên như `eventType`, `tenant`, `schemaVersion`, `amount`.

## 4. Ngữ pháp biểu thức lọc

JMS selector là **một biểu thức điều kiện** dựa trên tập con cú pháp SQL-92, không phải câu truy vấn SQL đầy đủ. Không thêm `WHERE`, `FROM` hoặc `SELECT`.

### 4.1. Toán tử so sánh

~~~sql
eventType = 'order.created'
eventType <> 'order.cancelled'
amount >= 100
attemptCount < 3
JMSPriority > 5
~~~

- Chuỗi được đặt trong dấu nháy đơn `'...'`.
- Số được ghi như literal số, không phải chuỗi.
- `<>` là so sánh khác chuẩn SQL/JMS; đừng mặc định `!=` được mọi provider hiểu.
- So sánh chuỗi, số và boolean có quy tắc kiểu; không tự ép kiểu như một số ngôn ngữ scripting.

### 4.2. AND, OR, NOT và ngoặc

~~~sql
eventType = 'order.created' AND amount >= 100

region = 'VN' OR region = 'SG'

eventType = 'order.created'
  AND (region = 'VN' OR region = 'SG')

NOT (status = 'cancelled')
~~~

Thứ tự ưu tiên logic thông thường là `NOT`, `AND`, `OR`; dùng ngoặc làm rõ ý định và tránh kết quả không mong muốn.

### 4.3. IN và BETWEEN

~~~sql
region IN ('VN', 'SG', 'TH')
amount BETWEEN 100 AND 500
eventType NOT IN ('debug', 'test')
~~~

`IN` kiểm tra thành viên trong tập giá trị phù hợp grammar. `BETWEEN` kiểm tra khoảng, bao gồm hai đầu. Đây vẫn là một String selector, không có PreparedStatement hay Java List được truyền vào API.

### 4.4. LIKE và wildcard

~~~sql
eventType LIKE 'order.%'
reference LIKE 'INV_2026%'
reference NOT LIKE 'TEST%'
~~~

Trong `LIKE`:

- `%` khớp chuỗi ký tự có độ dài tùy ý, kể cả chuỗi rỗng.
- `_` khớp đúng một ký tự.
- `ESCAPE` được dùng khi cần match ký tự `%` hoặc `_` theo nghĩa literal.

Ví dụ `region LIKE 'V_'` match `VN` nhưng không match `VNM`. Đây không phải regular expression; mẫu `order.*` không có nghĩa tương đương `order.%`.

### 4.5. IS NULL và IS NOT NULL

~~~sql
traceId IS NULL
traceId IS NOT NULL
~~~

Nếu JMS property không tồn tại, selector xem giá trị của nó như `NULL`. So sánh với NULL có ý nghĩa đặc biệt, trình bày ở phần 5.

### 4.6. Boolean, giá trị số và tên property

~~~sql
urgent = TRUE
isTest = FALSE
amount >= 100
attemptCount <= 2
~~~

Để các selector trên hoạt động, producer cần đặt đúng kiểu:

~~~java
message.setBooleanProperty("urgent", true);
message.setBooleanProperty("isTest", false);
message.setIntProperty("amount", 150);
message.setIntProperty("attemptCount", 1);
~~~

Khác với:

~~~java
message.setStringProperty("amount", "150");
~~~

Property `amount` dạng String không tự trở thành số nguyên khi dùng `amount >= 100`. Quy tắc chuyển đổi có thể có ở các getter property **không áp dụng tự động** cho biểu thức selector.

### 4.7. Literal và phân biệt chữ hoa

Tên identifier/property phân biệt chữ hoa chữ thường: `eventType` khác `EventType`. Keyword `AND`, `OR`, `LIKE` không phân biệt hoa thường, nhưng **giá trị string literal** so sánh theo ký tự.

Dấu nháy đơn bên trong String literal được nhân đôi:

~~~sql
customerName = 'O''Hara'
~~~

để biểu diễn tên `O'Hara`. `NULL` khác chuỗi `'NULL'`. Đặt tên property theo quy tắc JMS identifier; không dùng các keyword của selector làm tên property.

## 5. TRUE, FALSE và UNKNOWN: vì sao nhiều message không match?

JMS selector dùng **logic ba giá trị**: `TRUE`, `FALSE` và `UNKNOWN`. Chỉ message có biểu thức đánh giá thành **TRUE** mới match. Nếu property thiếu hoặc là NULL, nhiều phép so sánh trả UNKNOWN.

Message không có property `status`:

| Biểu thức | Kết quả | Có match? |
| --- | --- | --- |
| `status = 'NEW'` | UNKNOWN | Không |
| `status <> 'CANCELLED'` | UNKNOWN | Không |
| `NOT (status = 'CANCELLED')` | UNKNOWN | Không |
| `status IS NULL` | TRUE | Có |
| `status IS NOT NULL` | FALSE | Không |
| `status IS NULL OR status <> 'CANCELLED'` | TRUE | Có |

Sai lầm thường gặp:

~~~sql
status <> 'CANCELLED'
~~~

không có nghĩa “mọi message không phải CANCELLED, kể cả thiếu status”. Nếu mục đích là nhận cả message thiếu status:

~~~sql
status IS NULL OR status <> 'CANCELLED'
~~~

**Hệ quả vận hành:** một Queue có backlog vẫn có thể khiến `receiveSelected` trả `null` vì tất cả message còn lại thiếu property, sai kiểu hoặc không thỏa filter.

### 5.1. Property absent khác giá trị chuỗi rỗng

Nếu producer không đặt `region` thì `region IS NULL` match. Nếu producer đặt `setStringProperty("region", "")` thì property có tồn tại và không còn là NULL. Nếu producer đặt `setStringProperty("region", "null")` thì đó là String gồm bốn ký tự, không phải null JMS.

Đừng thay việc kiểm tra missing property bằng `region = ''` hoặc `region = 'null'`. Data contract nên định nghĩa rõ cách biểu diễn “không xác định”: bỏ property hay dùng một giá trị hợp lệ cụ thể.

## 6. Thời gian chờ và kết quả null

`receiveSelected` là **nhận đồng bộ**, nên thread gọi có thể block cho đến khi có message match hoặc hết thời gian chờ.

Trong Spring Boot:

~~~properties
spring.jms.template.receive-timeout=1500ms
~~~

Hoặc khi cấu hình `JmsTemplate`:

~~~java
// Snippet cấu hình, thực hiện trước khi dùng chung template:
jmsTemplate.setReceiveTimeout(1500L);
~~~

Quy ước của Spring `JmsTemplate`:

| Receive timeout | Hành vi |
| --- | --- |
| Số dương (milliseconds) | Chờ tối đa khoảng thời gian chỉ định |
| `0` | Chờ không giới hạn |
| Số âm như `-1` | `receiveNoWait`, kiểm tra ngay không block |

Khi hết timeout:

~~~java
// Đoạn minh họa trong service đã inject JmsOperations:
Message received = operations.receiveSelected(
        "orders.queue", "eventType = 'order.created'");
if (received == null) {
    // Không có message MATCH trong thời gian chờ.
    // Điều này không chứng minh Queue rỗng.
}
~~~

Đừng diễn giải `null` thành lỗi broker ngay lập tức. Broker có thể đang hoạt động tốt nhưng Queue chỉ có message không match. Mặt khác, kết nối thất bại hoặc selector sai cú pháp thường gây `JmsException`, không phải một kết quả null thông thường.

Nếu gọi từ một HTTP request handler, timeout quá lớn làm tốn thread và tài nguyên. Với worker tiêu thụ liên tục, `@JmsListener` thường thích hợp hơn vòng lặp polling.

## 7. Dự án Spring Boot 3.3 + Java 17 + ActiveMQ Artemis

Bài thực hành gửi ba message vào Queue riêng, nhận lần lượt bằng selector và kiểm tra message không match vẫn có thể nhận tiếp. Ứng dụng không cần listener bất đồng bộ vì đang học **nhận đồng bộ**.

### 7.1. Chạy broker local

Máy có Docker:

~~~bash
docker run -d --rm --name artemis-selector-lab -p 127.0.0.1:61616:61616 -p 127.0.0.1:8161:8161 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest
~~~

Đợi broker sẵn sàng, kiểm tra:

~~~bash
docker logs artemis-selector-lab
~~~

Đây là tài khoản demo và port chỉ mở trên loopback host; không dùng credential này ở production. Broker mẫu thường hỗ trợ tự tạo Queue. Nếu môi trường chặn auto-create thì cần cấp Queue và quyền gửi/nhận trước.

### 7.2. Dự án Gradle

Cây thư mục:

~~~text
jms-selector-lab/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/demo/jms/SelectedReceiveApplication.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-selector-lab'
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

Dùng JDK 17+ và Gradle tương thích với plugin được khai báo. Spring Boot 3 sử dụng `jakarta.jms`, không trộn với client `javax.jms` đời cũ.

`src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_BROKER_USER:demo}
spring.artemis.password=${JMS_BROKER_PASSWORD:demo}
spring.jms.pub-sub-domain=false
spring.jms.template.receive-timeout=1500ms
~~~

Các biểu thức `${...}` trong bản thảo được ghi thành cú pháp property placeholder Spring chuẩn khi lưu nội dung. `pub-sub-domain=false` nghĩa là dùng Queue. Mật khẩu fallback chỉ dành cho local lab; production dùng secret manager hoặc biến môi trường bắt buộc.

### 7.3. Java class có thể chạy

`src/main/java/demo/jms/SelectedReceiveApplication.java`:

~~~java
package demo.jms;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import java.util.UUID;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class SelectedReceiveApplication {

    public static void main(String[] args) {
        SpringApplication.run(SelectedReceiveApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(JmsTemplate jmsTemplate) {
        return args -> {
            String queue = "lesson.selector." + UUID.randomUUID();

            send(jmsTemplate, queue, "order-1", "north", 50);
            send(jmsTemplate, queue, "order-2", "north", 150);
            send(jmsTemplate, queue, "order-3", "south", 300);

            Message highNorth = jmsTemplate.receiveSelected(
                    queue, "tenant = 'north' AND amount >= 100");
            System.out.println("HIGH_NORTH=" + text(highNorth));

            Object south = jmsTemplate.receiveSelectedAndConvert(
                    queue, "tenant = 'south'");
            System.out.println("SOUTH=" + south);

            Message remaining = jmsTemplate.receive(queue);
            System.out.println("REMAINING=" + text(remaining));

            Message missing = jmsTemplate.receiveSelected(
                    queue, "tenant = 'east'");
            System.out.println("NO_MATCH=" + (missing == null));
        };
    }

    private static void send(JmsTemplate template, String queue,
                             String body, String tenant, int amount) {
        template.convertAndSend(queue, body, message -> {
            message.setStringProperty("tenant", tenant);
            message.setIntProperty("amount", amount);
            return message;
        });
    }

    private static String text(Message message) throws JMSException {
        if (message == null) {
            return "(none)";
        }
        if (message instanceof TextMessage text) {
            return text.getText();
        }
        throw new IllegalStateException("Expected a TextMessage");
    }
}
~~~

**Giải thích:**

1. Dùng `UUID.randomUUID()` để chọn Queue riêng mỗi lần chạy, tránh message thừa từ lần trước làm thay đổi kết quả. Trong production không nên tạo Queue ngẫu nhiên không có lifecycle cleanup; cách này chỉ dành cho lab có auto-create.
2. `send(...)` đặt `tenant` dạng String và `amount` dạng int lên JMS properties; body `order-N` là String được converter mặc định thành TextMessage.
3. `receiveSelected(queue, "tenant = 'north' AND amount >= 100")` khớp `order-2`, không nhận `order-1` và `order-3`.
4. `receiveSelectedAndConvert(queue, "tenant = 'south'")` khớp `order-3`; converter mặc định đưa TextMessage thành String.
5. `receive(queue)` không selector lấy message còn lại `order-1`.
6. `receiveSelected(queue, "tenant = 'east'")` không có match và trả `null` sau thời gian chờ.
7. Không dùng `@EnableJms` vì chương trình không có `@JmsListener`; đây là mô hình receive đồng bộ.

### 7.4. Chạy và kết quả

~~~bash
gradle bootRun
~~~

Với broker đang chạy, credential đúng, Queue cho phép tạo và không có consumer khác cạnh tranh, các dòng do chương trình in ra là:

~~~text
HIGH_NORTH=order-2
SOUTH=order-3
REMAINING=order-1
NO_MATCH=true
~~~

Spring Boot và Gradle có thể in log khác xen kẽ. Do tên Queue ngẫu nhiên **không được in**, bốn dòng trên vẫn cố định trong điều kiện demo. Nhận ở lượt cuối chờ khoảng 1500ms trước khi trả null; không phải chương trình bị treo.

Dừng broker:

~~~bash
docker stop artemis-selector-lab
~~~

## 8. Message không match sẽ ra sao?

**Với Queue**, selector quyết định message nào eligible cho consumer. Nếu consumer hiện tại chỉ nhận `tenant = 'north'`, những message `tenant='south'` có thể chờ trong Queue cho consumer khác hoặc lần nhận khác. Message không tự bị xóa vì filter không match. Tuy nhiên, message có thể hết TTL, bị tác động bởi policy broker hoặc được một consumer cạnh tranh khác nhận.

**Với Topic**, subscription model thay đổi cách message được giữ. Non-durable subscription thường không giữ message gửi khi subscriber offline. Selector của một subscription quyết định những message được giao cho subscription đó; message không match không được giữ riêng “để sau này đổi selector rồi nhận lại”. Durable/shared subscriptions có các quy tắc danh tính và cập nhật selector riêng.

**Cảnh báo:** không suy luận “trả null = Queue rỗng”. Một Queue chứa hàng nghìn message không match selector vẫn có thể khiến receiver này hết timeout.

## 9. Nhận đồng bộ không phải thao tác browse/peek

`receiveSelected` thực hiện **receive và tiêu thụ** message theo mode ACK/transaction. Nó không phải API để “xem thử” Queue rồi để nguyên message.

~~~java
// Snippet: Đây là consume, không phải peek:
Message message = jmsTemplate.receiveSelected(
        "orders.queue", "eventType = 'order.created'");
~~~

Nếu chỉ muốn xem message mà không tiêu thụ, cân nhắc `JmsTemplate.browse(...)` / Jakarta JMS `QueueBrowser`. Nội dung Queue có thể đổi đồng thời; browser không phải snapshot tuyệt đối và không nên coi là metric chính xác thay cho broker monitoring.

Khi session không transacted, xác nhận có thể xảy ra theo cơ chế acknowledge được cấu hình. Với transacted session, outcome tiêu thụ phụ thuộc commit/rollback của session. Đừng nhận message chỉ để đếm rồi bỏ qua ACK semantics.

## 10. @JmsListener(selector = ...) so với receiveSelected

Cùng dùng JMS selector nhưng khác mô hình thực thi:

| Tiêu chí | `receiveSelected` | `@JmsListener(selector = "...")` |
| --- | --- | --- |
| Cách nhận | Thread chủ động poll | Listener container chủ động deliver |
| Có block thread gọi? | Có thể có | Container quản lý thread riêng |
| Timeout | Theo `JmsTemplate` | Theo container configuration |
| Resource lifecycle | Gắn với mỗi thao tác receive | Consumer được container quản lý lâu dài |
| Selector | Có thể thay đổi mỗi lời gọi | Thường được khai báo trong annotation/factory |
| Dùng tốt khi | Job, CLI, poll có giới hạn, workflow chờ | Consumer xử lý liên tục/high throughput |
| Khi không có message | `null` khi hết timeout | Không gọi handler |
| Xử lý lỗi | Code gọi nhận Spring `JmsException` | Listener error handler, transaction/retry config |

Ví dụ listener riêng (không thêm vào chương trình mẫu vì sẽ tranh Queue):

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class NorthOrderListener {
    @JmsListener(
        destination = "orders.queue",
        selector = "tenant = 'north' AND amount >= 100")
    public void onOrder(String body) {
        System.out.println("HANDLED=" + body);
    }
}
~~~

Đây là đoạn minh họa cần listener infrastructure bật trong ứng dụng thật. Nếu test cạnh tranh với một `receiveSelected` trên cùng Queue thì kết quả nhận có thể không như mong đợi vì hai consumer cùng đủ điều kiện nhận message.

## 11. Selector động: escape literal, không xem là bảo mật

Một selector là String chứ không phải PreparedStatement có parameter binding chuẩn. Nối thẳng input của người dùng vào biểu thức có thể làm thay đổi logic:

~~~java
// Không nên:
String selector = "tenant = '" + rawTenant + "'";
~~~

Nếu cần dựng selector từ giá trị đã validate, escape dấu nháy đơn bằng hai dấu nháy:

~~~java
// Method tiện ích minh họa:
static String selectorLiteral(String value) {
    if (value == null || value.length() > 64) {
        throw new IllegalArgumentException("Invalid selector value");
    }
    return "'" + value.replace("'", "''") + "'";
}
~~~

Sau đó:

~~~java
String selector = "tenant = " + selectorLiteral(validatedTenant);
~~~

Nên kiểm soát allowlist tên property, toán tử và giới hạn độ dài; ưu tiên selector cố định cho nghiệp vụ ổn định. Đừng cho client bên ngoài gửi selector tùy ý rồi sử dụng nguyên văn trong broker.

**Selector không phải authorization.** Filter `tenant = 'north'` không bảo vệ dữ liệu tenant khác khi account JMS có thể consume Queue rộng. Cần ACL, tách destination và cơ chế tenant isolation phù hợp.

## 12. Transactions, ACK và redelivery

Selector trả lời “message nào được nhận”; transaction/acknowledgment trả lời “việc nhận đã được xác nhận thế nào”. Hai nhóm cơ chế khác nhau.

Quy trình xử lý message quan trọng:

1. `receiveSelected` chọn một message.
2. Ứng dụng validate schema/body/business metadata.
3. Thực hiện cập nhật DB/tác dụng phụ.
4. Commit/ACK theo chính sách.
5. Nếu lỗi thì rollback/redelivery/DLQ theo contract.

Không suy ra rằng nhận được `Message` nghĩa là database đã commit; cũng không suy ra message sẽ không được nhận lại nếu JMS transaction rollback.

Một số lựa chọn Spring Boot cho template (chỉ áp dụng khi hiểu lifecycle của transaction):

~~~properties
spring.jms.template.session.transacted=true
spring.jms.template.session.acknowledge-mode=auto
~~~

Không dùng `@Transactional` của database rồi mặc nhiên coi JMS và DB thuộc cùng XA transaction. Đối với hệ thống quan trọng, cần idempotency/outbox hoặc transaction manager phối hợp đúng.

Selector không thay thế chiến lược chống duplicate. Một message được redeliver vẫn có thể match biểu thức lần nữa. Dùng business event ID và lưu trạng thái xử lý bền vững nếu tác dụng phụ không được lặp.

## 13. Hiệu năng và giám sát

Selector có thể giảm lượng message không liên quan được giao tới consumer, nhưng hiệu quả phụ thuộc provider, cách broker lưu/index properties, mức backlog và số consumer. Không có bảo đảm chung rằng một selector phức tạp luôn nhanh hơn tách Queue.

Các vấn đề thường gặp:

- Queue chứa nhiều tenant nhưng chỉ vài tenant có consumer: message không match tích tụ.
- Tạo consumer mới trong vòng poll quá dày gây overhead session/connection/broker.
- Selector có nhiều `OR`, `LIKE` và tên property không ổn định khiến khó tối ưu.
- Consumer chờ quá lâu trong HTTP handler gây cạn request thread.
- Nhiều consumer có selector overlap tạo cạnh tranh nhận, ảnh hưởng thứ tự xử lý.
- Đặt selector quá chặt khiến queue depth tăng dù ứng dụng vẫn sống.

Theo dõi queue depth, message age, consumer count, retry/redelivery, số lần poll timeout, thời gian chờ `receiveSelected`, và lỗi `InvalidSelectorException`. Với backlog không match, phải có consumer/routing/TTL/DLQ policy hợp lý.

**Không dùng selector để giải quyết mọi nhu cầu routing:** nếu mỗi nhóm công việc phải được xử lý riêng, hoặc tenant isolation là yêu cầu bảo mật, việc tách Queue và cấu hình broker có thể rõ ràng hơn.

## 14. Kiểm thử: những gì mock không chứng minh được

Unit test có thể verify selector string và kết quả null handling. Ví dụ JUnit 5/Mockito (snippet cần nằm trong một test class với dependency test):

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.jms.core.JmsOperations;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@Test
void receivesOnlyHighValueNorthOrders() {
    JmsOperations operations = mock(JmsOperations.class);
    String filter = "tenant = 'north' AND amount >= 100";

    when(operations.receiveSelectedAndConvert(
            "orders.queue", filter)).thenReturn("order-2");

    Object body = operations.receiveSelectedAndConvert(
            "orders.queue", filter);

    assertEquals("order-2", body);
    verify(operations).receiveSelectedAndConvert(
            "orders.queue", filter);
}
~~~

Mockito không chạy parser JMS ở broker. Test trên chỉ chứng minh code gọi đúng method/selector String và xử lý mock.

**Integration test với broker** mới chứng minh provider hiểu selector như dự kiến. Bộ test nên có:

1. Message có int/long/String/boolean property đúng kiểu.
2. Message thiếu property, `IS NULL` và biểu thức `NOT`.
3. Case mismatch `EventType` vs `eventType`.
4. String literal chứa dấu nháy đơn cần escape.
5. Selector không match -> `null` sau receive timeout.
6. Sau selected receive, message không match vẫn tồn tại trong Queue cho consumer khác.
7. Selector sai cú pháp -> exception, không bị biến thành `null`.
8. Transaction rollback/redelivery và đồng thời nhiều consumer nếu production cần.

Khi kiểm thử, dùng Queue riêng, làm sạch message test và tránh có listener khác tranh message. Trong CI có thể dùng broker container/Testcontainers; không dùng broker production để thử lỗi selector.

## 15. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `receiveSelected` trả `null` trong khi Queue có message | Không có message match hoặc timeout | Kiểm tra property thực, ngữ pháp và TTL |
| `amount >= 100` không match body ghi 150 | Body không phải JMS property | Gắn `amount` bằng `setIntProperty` |
| `amount >= 100` không match String `"150"` | Property sai kiểu | Đồng bộ contract số, không mong tự ép kiểu |
| `body.status = 'NEW'` không hoạt động | JMS không truy cập JSON body | Dùng JMS property `status` |
| `status <> 'CANCELLED'` bỏ qua message thiếu status | NULL -> UNKNOWN | Sử dụng `status IS NULL OR ...` khi phù hợp |
| Selector báo lỗi ngay | Cú pháp sai/quote sai | Kiểm tra grammar, escape nháy đơn |
| Thread block quá lâu | Timeout mặc định vô hạn | Đặt receive timeout hữu hạn |
| Một tham số String bị hiểu sai | Overload `receiveSelected(String)` là selector của default destination | Dùng overload hai tham số |
| Consumer khác lấy mất message | Competing consumers | Dùng Queue riêng hoặc kiểm thử cô lập |
| Message không match bị backlog | Không có consumer phù hợp | Sửa routing hoặc lifecycle policy |
| Topic subscriber không thấy message cũ | Non-durable subscription/offline | Chọn subscription model phù hợp |
| Consumer nhận lặp | Rollback/redelivery | Idempotency, transaction, retry/DLQ |
| Unit test pass nhưng broker nhận sai | Mock không chạy JMS selector engine | Thêm integration test |

## 16. Checklist triển khai

- [ ] Destination và Queue/Topic mode đã đúng.
- [ ] Selector tham chiếu JMS header/property hợp lệ, không truy vấn JSON body.
- [ ] Producer đặt property đúng tên và đúng kiểu.
- [ ] Giá trị null/UNKNOWN và `IS NULL` được kiểm tra.
- [ ] Chọn receive timeout hữu hạn phù hợp SLA; xử lý `null` rõ.
- [ ] Không dùng receiveSelected để browse/peek.
- [ ] Có consumer thích hợp cho những message không match.
- [ ] Nếu selector dựng động: validate và escape String literal.
- [ ] ACL/tenant isolation được thiết kế độc lập với selector.
- [ ] Transaction, ACK và redelivery được xử lý.
- [ ] Có integration test trên broker thật cùng loại sẽ triển khai.
- [ ] Có metric backlog, message age, timeout và consumer count.

## 17. Câu hỏi tự đánh giá

**1.** Vì sao `receiveSelected` không tương đương nhận message trước rồi lọc Java `if`?

Vì selector được đưa vào consumer và JMS provider chỉ giao message match; message không match không bị consumer đó tiêu thụ.

**2.** Có thể lọc `orderId` chỉ nằm trong JSON body không?

Không. Selector chuẩn JMS không đọc body; muốn lọc hãy đặt orderId thành JMS property hoặc đổi routing.

**3.** `setStringProperty("amount", "150")` có match `amount >= 100` không?

Không như ý định so sánh số. Dùng `setIntProperty`/`setLongProperty` và literal số đúng kiểu.

**4.** `receiveSelected` trả `null` chứng minh điều gì?

Không có message match được nhận trong thời gian chờ của thao tác; không chứng minh Queue rỗng.

**5.** `status <> 'CANCELLED'` có chọn được message thiếu `status` không?

Không. UNKNOWN không match; thêm `status IS NULL` nếu muốn bao gồm message thiếu property.

**6.** Message không match có tự biến mất khỏi Queue không?

Không chỉ vì selector không match. Nó có thể chờ consumer khác theo policy/TTL của broker.

**7.** `receiveSelected("orders.queue")` có ý nghĩa “nhận từ Queue orders.queue” không?

Không. Overload một tham số là selector cho default destination; nên dùng overload `receiveSelected(queueName, selector)`.

**8.** Khi nào dùng `@JmsListener(selector=...)`?

Khi cần xử lý liên tục với container quản lý consumer, concurrency và resource, thay vì poll đồng bộ.

**9.** Selector có thay thế broker ACL trong ứng dụng đa tenant không?

Không. Đó chỉ là cơ chế lọc nhận, không phải rào chắn bảo mật.

**10.** Muốn xem Queue mà không consume thì làm thế nào?

Dùng `QueueBrowser`/`JmsTemplate.browse` hoặc metrics broker, thay vì `receiveSelected`.

## 18. Tài liệu chính thức

- Jakarta Messaging 3.1 Specification, phần **Message selection**: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging API — Message selectors: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message
- Jakarta Messaging API — MessageConsumer: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageconsumer
- Spring Framework 6.1 — `JmsTemplate`, `receiveSelected`, `receiveSelectedAndConvert`: https://docs.spring.io/spring-framework/docs/6.1.1/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Framework 6.1 — `JmsOperations`: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/jms/core/JmsOperations.html
- Spring Framework — Using Spring JMS: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Boot 3.3 — JMS and Artemis: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html

**Ghi nhớ:** `receiveSelected` là nhận đồng bộ có **selector được đánh giá trên JMS headers/properties**, không phải truy vấn body. Một ứng dụng dùng đúng phải thống nhất tên/kiểu property, biết xử lý NULL và timeout, hiểu ACK/transaction, và chuẩn bị cách xử lý message không match.
