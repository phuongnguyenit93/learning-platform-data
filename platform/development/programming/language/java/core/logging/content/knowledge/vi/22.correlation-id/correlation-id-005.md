# Truyền Correlation ID qua message trong Java: producer, broker, consumer và retry

## 1. Mục tiêu của bài học

Trong kiến trúc ứng dụng Java bất đồng bộ, một yêu cầu thường không kết thúc ở HTTP controller. Service có thể **publish một message** vào broker; consumer ở một JVM khác nhận message sau vài giây, vài phút hoặc sau khi hệ thống đã restart. Nếu chỉ đặt Correlation ID vào `MDC` của thread producer, consumer **không tự nhận được ID đó**. MDC nằm trong ngữ cảnh runtime của tiến trình, còn message được truyền qua một hệ thống khác.

**Truyền Correlation ID qua message** nghĩa là đưa một mã liên kết từ ngữ cảnh producer vào **metadata/header/property của message**, bảo toàn nó qua các bước truyền, sau đó đọc và gắn lại vào logging context khi consumer xử lý.

Mục tiêu là khi điều tra, có thể trả lời:

- HTTP request nào đã tạo message này?
- Service nào publish message, và message được xử lý ở consumer nào?
- Những bước publish, receive, retry, dead-letter và downstream publish nào cùng thuộc một luồng công việc?
- Lỗi là một lần xử lý thất bại tạm thời hay kết quả cuối cùng?
- Một message bị redeliver có bị đếm nhầm thành hai nghiệp vụ khác nhau không?
- Context có bị lẫn giữa những message chạy liên tiếp trên cùng worker thread không?

Một ví dụ dòng log liên kết:

```text
INFO  cid=corr-42 mid=m-001 event=message.published
INFO  cid=corr-42 mid=m-001 event=message.received attempt=1
WARN  cid=corr-42 mid=m-001 event=message.retry_scheduled
INFO  cid=corr-42 mid=m-001 event=message.received attempt=2
INFO  cid=corr-42 mid=m-001 event=message.processed
INFO  cid=corr-42 mid=m-002 event=message.published
```

`corr-42` là **Correlation ID của luồng công việc**; `m-001` và `m-002` là **hai Message ID khác nhau**. Khi có retry của cùng một message, hệ thống có thể giữ một ID nghiệp vụ ổn định đồng thời phát sinh một delivery attempt mới. Các bản ghi có cùng Correlation ID không nhất thiết là cùng một message hay cùng một lần giao nhận.

**Ý chính:** context phải được truyền **qua ranh giới message** bằng cơ chế của broker/giao thức, rồi mới đưa vào MDC hoặc ThreadContext của consumer. Không được coi một biến `ThreadLocal` hay `MDC.put` ở producer như một header tự được gửi qua mạng.

## 2. Correlation ID khác Message ID, Trace ID và event code

| Thuộc tính | Mục đích chính | Phạm vi | Thường thay đổi khi nào? |
| --- | --- | --- | --- |
| `correlation_id` | Nối các hoạt động liên quan cùng một quy trình/hành trình | Qua nhiều message, service và lần xử lý theo hợp đồng | Khi bắt đầu một hành trình mới |
| `message_id` | Định danh một logical message/event | Một message nghiệp vụ, tùy hệ thống | Khi tạo message logic mới |
| `delivery_attempt` | Ghi nhận lần giao/xử lý thứ mấy | Từng attempt | Khi redelivery/retry |
| `trace_id` | Định danh distributed trace | Qua nhiều span theo tracing instrumentation | Khi tạo trace mới theo quy tắc tracing |
| `span_id` | Định danh một span của trace | Một phần công việc | Theo mỗi span |
| `request_id` | Định danh một request vào một boundary | HTTP request/gateway hoặc theo hợp đồng truyền ID | Tùy API boundary |
| `event_code` | Phân loại **loại sự kiện**, như `order.created` | Có thể lặp lại trên hàng triệu giao dịch | Khi loại sự kiện khác |
| `business_id`, ví dụ `order_id` | Định danh thực thể nghiệp vụ | Qua nhiều request và message | Theo thực thể |

### Một Correlation ID có thể đi qua nhiều message

Ví dụ:

```text
HTTP: POST /orders
  request_id=req-81
  correlation_id=corr-42
        |
        v
order.created
  message_id=m-001
  correlation_id=corr-42
        |
        v
Payment consumer
        |
        +-- publish payment.authorized
              message_id=m-002
              correlation_id=corr-42
                    |
                    v
              Shipping consumer
```

`m-002` **không tái sử dụng** `m-001` nếu là một logical message mới. Nhưng cả hai có thể giữ `corr-42` để điều tra chung một luồng nghiệp vụ.

### Correlation ID không phải idempotency key

Nếu consumer nhận lại cùng một message sau timeout hoặc mất ACK, Correlation ID giúp liên kết log nhưng **không chứng minh rằng một nghiệp vụ chưa được thực thi**. Trong một hành trình có thể có hàng chục message chia sẻ Correlation ID. Chống xử lý trùng cần **message/event ID hoặc idempotency key** và cơ chế lưu trạng thái/transaction thích hợp.

### Correlation ID không tự là W3C Trace ID

`corr-42` là chuỗi mẫu cho correlation nghiệp vụ, **không phải** trace ID hợp lệ theo W3C. Nếu ứng dụng có OpenTelemetry hoặc distributed tracing, dùng SDK/instrumentation để tạo, nhận và truyền `traceparent`/span context; có thể xuất `trace_id` trong log cùng Correlation ID.

**Không tự đặt `trace_id=corr-42`** rồi coi đó là distributed trace đúng chuẩn. Hai loại ID có thể liên quan nhưng mang hợp đồng khác nhau.

## 3. Vì sao chỉ dùng MDC ở producer là chưa đủ?

Giả sử một HTTP handler làm:

```java
MDC.put("correlation_id", "corr-42");
try {
    publisher.publishOrderCreated(order);
} finally {
    MDC.remove("correlation_id");
}
```

Đây là **mã minh họa trong ứng dụng**, giả định có `publisher` và `order`. Một logger ở thread producer có thể in `corr-42` nếu layout/encoder được cấu hình đọc MDC.

Nhưng một JVM ở consumer không tự biết giá trị này:

```text
Producer JVM                           Consumer JVM
-------------                          -------------
MDC: correlation_id=corr-42

publish(payload) ---> broker --->      receive(payload)

                                       MDC của consumer:
                                       không tự có corr-42
```

Để truyền, phải thực hiện rõ ràng:

```text
Producer JVM
  MDC / tracing / application context
       |
       v
  correlation_id
       |
       +--> message header/property: correlation_id=corr-42
               |
               v
             Broker
               |
               v
          Consumer đọc metadata
               |
               v
          Validate correlation_id
               |
               v
          MDC.put("correlation_id", id)
               |
               v
          Logger + appender/encoder
               |
               v
          MDC restore/cleanup trong finally
```

MDC được dùng ở **hai đầu**, nhưng metadata của message mới là kênh thực sự nối hai tiến trình.

## 4. Truyền trong header hay payload?

Nhiều broker có **metadata** hoặc **properties** bên cạnh payload:

- Kafka: record headers.
- RabbitMQ/AMQP: message properties như `correlationId` hoặc custom headers.
- JMS: `JMSCorrelationID` và application properties.
- Các broker/cloud queue khác: message attributes/properties tương ứng.

Một hợp đồng message có thể trông như:

```text
Topic/queue: orders.created
Key:         O-17
Headers:
  correlation_id: corr-42
  event_id:       evt-1001
  schema_version: 1
Payload:
  {"order_id":"O-17","amount_minor":120000,"currency":"VND"}
```

Đây là **mẫu hợp đồng**, không phải cú pháp chung có thể đưa nguyên vào mọi broker.

### Ưu điểm của metadata

1. Không làm thay đổi DTO nghiệp vụ chỉ để thêm thông tin observability.
2. Consumer, middleware và interceptor có thể đọc context trước khi deserialize payload.
3. Một message con được tạo từ message cha có thể **sao chép context theo allowlist** mà không chạm các trường nghiệp vụ.
4. Tách cách liên kết luồng xử lý khỏi định dạng JSON/Avro/Protobuf của payload.

### Khi nào có thể dùng envelope trong payload?

Một số giao thức không có header tiện dụng, hoặc event contract dùng envelope chung:

```json
{
  "metadata": {
    "correlation_id": "corr-42",
    "event_id": "evt-1001",
    "schema_version": 1
  },
  "data": {
    "order_id": "O-17",
    "amount_minor": 120000,
    "currency": "VND"
  }
}
```

Envelope có thể phù hợp nếu được thống nhất và version hóa. Nhưng **không đồng thời duy trì hai nguồn sự thật mâu thuẫn** như header `corr-A` còn payload metadata `corr-B`. Nếu cả hai tồn tại, phải quy định trường nào authoritative, cách kiểm tra mismatch và cách ghi audit.

### Một ID, một tên field, một quy tắc encoding

Chọn một tên như `correlation_id` hoặc `X-Correlation-ID` theo giao thức, thống nhất producer và consumer. Đặt chính sách:

- Tên key có phân biệt hoa/thường không?
- Value được encode UTF-8 hay dùng kiểu string/property của broker?
- Chiều dài tối đa?
- Có chấp nhận ID từ client ngoài không?
- Nếu thiếu/sai định dạng thì tạo mới, từ chối hay đánh dấu thiếu?
- Retry, redelivery và DLQ có giữ nguyên ID không?
- Message do consumer phát tiếp giữ ID cũ hay bắt đầu correlation scope mới?

Tránh producer gửi `correlationId` rồi consumer đọc `correlation_id` và mặc định broker tự chuyển tên.

## 5. Hợp đồng Correlation ID nên được xác định ở ranh giới đầu vào

Một chiến lược phổ biến:

1. **Tại HTTP gateway/entrypoint:** xác định đã có Correlation ID từ nguồn tin cậy chưa. Nếu không có hoặc không hợp lệ, tạo ID mới bằng công cụ thích hợp.
2. **Trong producer:** đọc context đã được xác thực và đặt vào message header/property theo hợp đồng.
3. **Tại consumer:** đọc metadata, kiểm tra giá trị và thiết lập logging context trong phạm vi xử lý message.
4. **Khi publish message con:** lấy Correlation ID đang hoạt động ở consumer và tiếp tục truyền, trừ khi yêu cầu nghiệp vụ định nghĩa một scope mới.
5. **Khi xử lý hoàn tất:** khôi phục/clear context để worker không mang ID sang message tiếp theo.

Điều kiện "từ nguồn tin cậy" quan trọng: client có thể tự gửi header có cùng tên. Correlation ID giúp tìm log, **không phải bằng chứng xác thực người gọi**, không cho phép truy cập tài nguyên hay kho log.

### Không tạo ID mới trong mọi method

Ví dụ sai:

```java
void handle(Message message) {
    String correlationId = UUID.randomUUID().toString();
    // Mỗi lần retry hoặc mỗi service lại có ID mới.
}
```

Đây là **snippet minh họa**. Nếu mỗi retry tạo ID mới, truy vết cùng logical message bị đứt. Thông thường chỉ tạo mới tại **correlation boundary** đã thiết kế; khi một message hợp lệ mang ID thì phải tiếp tục sử dụng.

### Cẩn trọng với công việc chạy rất lâu

Một message có thể tồn tại trong queue nhiều ngày. Correlation ID có thể là liên kết dài hạn, nhưng **tracing span** có vòng đời và ngữ nghĩa khác. Khi consumer nhận một message muộn, tracing instrumentation có thể chọn quan hệ parent/link theo hệ thống. Không cố giữ một span “đang mở” trong suốt thời gian message chờ chỉ vì hai bước có cùng Correlation ID.

## 6. Ví dụ Java 17 + Maven chạy được: truyền qua message headers và khôi phục MDC

Bài thực hành này dùng **SLF4J + Logback** và mô phỏng broker bằng một `ExecutorService`. Không cần Kafka/RabbitMQ server để chạy. Mục tiêu là minh họa chính xác **envelope chứa header**, **consumer đọc header**, **MDC scope**, **retry giữ correlation** và **worker không bị rò ngữ cảnh**.

Dù producer và consumer trong cùng một chương trình thử nghiệm, ta coi `Message` như đối tượng đã qua một ranh giới truyền: consumer **chỉ lấy Correlation ID từ header**, không trông chờ MDC của thread producer.

**Yêu cầu:** JDK 17+, Maven, có quyền lấy dependency khi chưa cache.

Cấu trúc dự án:

```text
message-correlation-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── MessageCorrelationDemo.java
        └── resources/
            └── logback.xml
```

### 6.1. Tệp `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>message-correlation-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.16</version>
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
```

`logback-classic` cung cấp Logback backend và provider SLF4J tương ứng. Version ở đây là **bộ phiên bản ví dụ**, không phải khẳng định đó là bản mới nhất hoặc đã đáp ứng mọi yêu cầu bảo mật của production. Khi tích hợp framework có BOM/dependency management, cần chọn bộ phiên bản được hỗ trợ và tránh nhiều provider cùng runtime.

### 6.2. Tệp `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%level|cid=%X{correlation_id}|mid=%X{message_id}|%msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

- `%X{correlation_id}` đọc Correlation ID từ MDC của event.
- `%X{message_id}` đọc ID của logical message đang được consumer xử lý.
- `%msg` là message đã định dạng; `%n` xuống dòng.
- Pattern không chứa timestamp/thread để **expected output của bài thực hành ổn định**.
- Một production pattern/JSON encoder thường thêm timestamp, service, logger và environment.

### 6.3. Tệp `src/main/java/demo/MessageCorrelationDemo.java`

```java
package demo;

import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class MessageCorrelationDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(MessageCorrelationDemo.class);

    private MessageCorrelationDemo() {
    }

    record Message(
            String messageId,
            String payload,
            Map<String, String> headers,
            int attempt) {

        Message {
            headers = Map.copyOf(headers);
        }

        Message redelivered() {
            return new Message(
                    messageId, payload, headers, attempt + 1);
        }
    }

    private static void restore(Map<String, String> previous) {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }

    private static Message publish(
            String messageId, String payload) {
        String cid = MDC.get("correlation_id");

        if (cid == null || cid.isBlank()) {
            throw new IllegalStateException(
                    "Missing correlation_id at producer");
        }

        Message message = new Message(
                messageId,
                payload,
                Map.of("correlation_id", cid),
                1);

        LOG.info("event=message.published message_id={}", messageId);
        return message;
    }

    private static boolean consume(Message message) {
        Map<String, String> previous =
                MDC.getCopyOfContextMap();

        try {
            String cid = message.headers().get("correlation_id");

            if (cid == null || cid.isBlank()) {
                throw new IllegalArgumentException(
                        "Invalid correlation_id header");
            }

            MDC.put("correlation_id", cid);
            MDC.put("message_id", message.messageId());

            LOG.info("event=message.received attempt={}",
                    message.attempt());

            if (message.messageId().equals("m-001")
                    && message.attempt() == 1) {
                LOG.warn("event=message.retry_scheduled");
                return false;
            }

            LOG.info("event=message.processed payload={}",
                    message.payload());
            return true;
        } finally {
            restore(previous);
        }
    }

    public static void main(String[] args) throws Exception {
        Map<String, String> before =
                MDC.getCopyOfContextMap();

        ExecutorService worker =
                Executors.newSingleThreadExecutor();

        try {
            MDC.put("correlation_id", "corr-42");

            Message first = publish("m-001", "order.created");
            Message second = publish("m-002", "payment.authorized");

            Future<Boolean> firstAttempt =
                    worker.submit(() -> consume(first));

            if (firstAttempt.get()) {
                throw new AssertionError("Expected a retry");
            }

            Future<Boolean> secondAttempt =
                    worker.submit(() -> consume(first.redelivered()));

            if (!secondAttempt.get()) {
                throw new AssertionError("Retry should succeed");
            }

            Future<Boolean> nextMessage =
                    worker.submit(() -> consume(second));

            if (!nextMessage.get()) {
                throw new AssertionError("Next message should succeed");
            }

            worker.submit(() ->
                    LOG.info("event=worker.idle")).get();
        } finally {
            restore(before);
            worker.shutdown();
        }
    }
}
```

### 6.4. Biên dịch và chạy

Từ thư mục `message-correlation-demo`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.MessageCorrelationDemo
```

**Chín dòng log ứng dụng dự kiến:**

```text
INFO|cid=corr-42|mid=|event=message.published message_id=m-001
INFO|cid=corr-42|mid=|event=message.published message_id=m-002
INFO|cid=corr-42|mid=m-001|event=message.received attempt=1
WARN|cid=corr-42|mid=m-001|event=message.retry_scheduled
INFO|cid=corr-42|mid=m-001|event=message.received attempt=2
INFO|cid=corr-42|mid=m-001|event=message.processed payload=order.created
INFO|cid=corr-42|mid=m-002|event=message.received attempt=1
INFO|cid=corr-42|mid=m-002|event=message.processed payload=payment.authorized
INFO|cid=|mid=|event=worker.idle
```

Maven có thể in thêm thông báo của công cụ chạy. Bảng trên mô tả **log của ứng dụng** khi chỉ có backend/configuration của ví dụ được nạp; không phải khẳng định mọi terminal đều hiển thị stdout và stderr cùng một cách.

### 6.5. Giải thích kết quả và giới hạn mô phỏng

1. Producer đọc `MDC.get("correlation_id")` để đưa ID vào `Message.headers`. `message_id` không được đặt vào MDC của producer; nó được ghi vào message bằng placeholder nên ở hai dòng đầu `mid=` còn rỗng.
2. `Map.copyOf` làm bản copy header không sửa được, giúp người nhận không vô tình thay đổi map sau khi publish.
3. Consumer ở worker khác lấy ID **từ header**, không từ MDC producer.
4. `consume` lưu MDC trước đó của worker, đặt `correlation_id` và `message_id`, xử lý rồi **restore trong `finally`**.
5. Lần xử lý đầu của `m-001` được **mô phỏng** là thất bại tạm và lên lịch retry. Không có broker thực, không có ACK/nack hoặc queue delay trong ví dụ.
6. `redelivered()` giữ `messageId`, `payload` và headers, chỉ tăng `attempt`. Đây là **quy ước mô phỏng**, không phải khẳng định broker nào cũng giữ cùng một ID khi republish.
7. `m-002` là message mới, có ID riêng nhưng cùng `corr-42` vì thuộc cùng luồng liên kết.
8. `Future.get()` buộc main thread chờ xử lý xong nên thứ tự các dòng có thể dự đoán.
9. Event `worker.idle` chạy trên **cùng worker thread** sau các message nhưng không còn context: `cid=|mid=`. Đây là kiểm tra trực quan khả năng tránh rò MDC qua worker reuse.

**Điểm học tập quan trọng:** ví dụ chạy **bằng một JVM**, nhưng ranh giới message vẫn thể hiện qua immutable envelope. Trong Kafka/RabbitMQ/JMS thực, các headers/properties được serialize và đi qua broker; producer/consumer không chia sẻ heap hay MDC. Các đoạn tiếp theo giải thích cách gắn vào API thật.

## 7. Kafka: truyền Correlation ID bằng record headers

Trong **Apache Kafka**, mỗi `ProducerRecord` có headers; consumer đọc chúng từ `ConsumerRecord`.

### Producer: thêm header vào record

Ví dụ **snippet minh họa**, giả định đã có `KafkaProducer<String,String> producer`, `key`, `payload`, `correlationId` và cấu hình producer thích hợp:

```java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.producer.ProducerRecord;

ProducerRecord<String, String> record =
        new ProducerRecord<>(
                "orders.events",
                key,
                payload);

record.headers().add(
        "correlation_id",
        correlationId.getBytes(StandardCharsets.UTF_8));

producer.send(record);
```

Đây **không phải chương trình độc lập**; cần `kafka-clients`, broker, serializer, topic và cấu hình lỗi/retry của producer. `ProducerRecord` nhận header dưới dạng bytes; mã dùng UTF-8 một cách tường minh.

### Consumer: đọc header

```java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.common.header.Header;

Header header =
        record.headers().lastHeader("correlation_id");

String correlationId = header == null
        ? null
        : new String(
                header.value(),
                StandardCharsets.UTF_8);
```

Đây là snippet trong callback/loop đã có `ConsumerRecord<?,?> record`. `lastHeader` lấy giá trị cuối cho tên key khi record có nhiều header cùng tên. Nếu hệ thống yêu cầu **duy nhất một correlation header**, nên **kiểm tra duplicate/ambiguous headers** theo chính sách thay vì lặng lẽ chọn cuối trong mọi trường hợp.

### Đưa vào MDC trong thời gian xử lý

```java
Map<String, String> previous =
        MDC.getCopyOfContextMap();

try {
    String cid = validatedCorrelationId(record);
    MDC.put("correlation_id", cid);

    log.info("event=kafka.message.received");
    processRecord(record);
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
```

Đây là **đoạn minh họa**; `validatedCorrelationId` và `processRecord` phải được định nghĩa trong ứng dụng. Vùng `try/finally` chỉ bao thời gian xử lý **một record**. Nếu xử lý batch nhiều record trên cùng poll thread, phải thay context đúng cho từng record.

### Kafka key, offset và message ID không giống nhau

- `record.key()` thường phục vụ partitioning/order hoặc định danh nghiệp vụ; không mặc nhiên là Correlation ID.
- `topic + partition + offset` xác định một record Kafka ở vị trí cụ thể, nhưng một logical event được republish sang retry topic hoặc DLQ sẽ có offset mới.
- Một header `event_id`/`message_id` do ứng dụng quản lý có thể giúp nhận diện cùng logical event xuyên các lần republish.
- `correlation_id` nối nhiều event khác nhau trong một hành trình; không dùng nó làm khóa deduplication duy nhất.

### Kafka retry topic và DLQ

Nếu xử lý lỗi bằng cách **republish** sang retry topic, phải quyết định và **copy/allowlist các headers quan trọng**:

```text
orders.events
  event_id=evt-1001
  correlation_id=corr-42
        |
        v
orders.retry
  event_id=evt-1001
  correlation_id=corr-42
  attempt=2
        |
        v
orders.dlq (nếu hết lượt)
  event_id=evt-1001
  correlation_id=corr-42
  attempt=3
  original_topic=orders.events
  failure_code=...
```

Đây là **một policy minh họa**, không phải hành vi tự động của mọi Kafka framework. Một số thư viện retry/DLT có tiêu chuẩn header riêng, có thể giữ hoặc thêm thông tin theo cơ chế của chúng. Phải đọc hợp đồng cụ thể của hệ thống và test thật.

**Offset và ACK/commit** không được suy ra từ Correlation ID. Khi commit offset trước khi xử lý hoàn tất, message có thể bị mất nghiệp vụ; khi commit sau xử lý, có thể nhận lại message nếu consumer crash. Dùng idempotency và chiến lược giao nhận phù hợp.

## 8. RabbitMQ/AMQP: dùng `correlationId` trong BasicProperties

Với RabbitMQ Java Client theo AMQP 0-9-1, một message có **BasicProperties** gồm `correlationId` và `messageId`. Phân biệt:

- `correlationId`: dùng để liên kết request/reply hoặc một workflow theo hợp đồng.
- `messageId`: một định danh message do producer/ứng dụng đặt nếu có; broker không nhất thiết tự sinh một ID chuẩn cho mọi publish.
- `headers`: chứa các thuộc tính khác theo quy ước ứng dụng, ví dụ `event_id`, `schema_version`.

### Producer: đặt properties

Snippet minh họa, giả định có `Channel channel`, `byte[] body`, `correlationId` và `messageId`, exchange/routing key đã tạo:

```java
import com.rabbitmq.client.AMQP;

AMQP.BasicProperties props =
        new AMQP.BasicProperties.Builder()
                .correlationId(correlationId)
                .messageId(messageId)
                .contentType("application/json")
                .build();

channel.basicPublish(
        "orders.exchange",
        "order.created",
        props,
        body);
```

**Đây không phải chương trình độc lập**; cần RabbitMQ Java Client, connection/channel/exchange/routing config và kiểm tra publisher confirms khi có yêu cầu xác minh broker đã nhận message. Không có guarantee rằng chỉ gọi `basicPublish` là dữ liệu đã được xử lý end-to-end.

### Consumer: nhận properties, đặt MDC, ACK phù hợp

```java
String cid =
        delivery.getProperties().getCorrelationId();
String mid =
        delivery.getProperties().getMessageId();

Map<String, String> previous =
        MDC.getCopyOfContextMap();

try {
    MDC.put("correlation_id", requireValid(cid));
    if (mid != null) {
        MDC.put("message_id", mid);
    }

    processDelivery(delivery);
    // ACK sau khi xử lý thành công theo transaction policy.
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
```

Đây là **mã minh họa** trong callback đã có `delivery`, `requireValid` và `processDelivery`. `basicAck`/`basicNack`, redelivery và DLX/DLQ cần được tổ chức theo hợp đồng độ tin cậy của ứng dụng; không đặt ACK trước khi xử lý quan trọng hoàn tất chỉ để làm log có correlation.

### Request/reply trên RabbitMQ

Một use case truyền thống:

1. Client publish request với `correlationId=corr-42` và `replyTo`.
2. Responder xử lý request và trả reply về địa chỉ `replyTo`.
3. Reply mang Correlation ID giúp client ghép reply với request gốc.

Trong request/reply, `correlationId` có thể phục vụ trực tiếp việc **match reply**, không chỉ logging. Vì vậy, giá trị và lifecycle phải theo hợp đồng giao thức; không tự đổi ID khi responder phát reply.

Nếu hệ thống đồng thời có business correlation ID xuyên nhiều event, có thể cần **tách hai trường** (RPC reply correlation và workflow correlation) để tránh lẫn ngữ nghĩa.

## 9. JMS: `JMSCorrelationID` và ngữ nghĩa request/reply

JMS cung cấp trường header **`JMSCorrelationID`**. Ví dụ với **Jakarta Messaging/JMS API**, một snippet sử dụng `JMSContext`:

```java
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

// context và queue đã được framework/application cung cấp.
TextMessage message =
        context.createTextMessage(payload);

message.setJMSCorrelationID(correlationId);
message.setStringProperty("event_code", "order.created");

context.createProducer().send(queue, message);
```

Đây **không phải chương trình hoàn chỉnh**; cần provider JMS, connection/session/context, destination và variables `context`, `queue`, `payload`, `correlationId`. Tùy phiên bản hệ thống có thể dùng namespace `javax.jms` cũ hoặc `jakarta.jms` mới; không trộn hai namespace trong cùng một ví dụ runnable.

Consumer đọc:

```java
String correlationId =
        message.getJMSCorrelationID();

String eventCode =
        message.getStringProperty("event_code");
```

Trong flow request/reply, có hai quy ước thường thấy:

- Client tự tạo Correlation ID và responder **copy** sang reply.
- Responder đặt Correlation ID của reply thành **`JMSMessageID` của request**, theo hợp đồng request/reply của ứng dụng.

**Không giả định hai quy ước tương đương.** Quyết định dùng cách nào trước rồi xây client matcher và test. Không thay `JMSMessageID` do provider cấp bằng Correlation ID nghiệp vụ chỉ vì muốn nhìn log thuận tiện.

### Message properties không tự hiển thị trong logger

JMS header có ID không có nghĩa `MDC.get("correlation_id")` trong consumer đã có. Consumer/framework listener phải **đọc property và thiết lập logging context**, rồi cleanup khi xử lý message kết thúc.

## 10. Correlation ID đi qua retry, redelivery và dead-letter như thế nào?

Messaging thường vận hành theo **at-least-once delivery** hoặc có những trường hợp nhận lại message. Phải tách:

- **Logical event/message:** một công việc cần xử lý.
- **Delivery attempt:** một lần broker đưa message đến consumer.
- **Processing attempt:** một lần ứng dụng thực thi nghiệp vụ, có thể không khớp 1:1 với delivery.
- **Retry message:** có thể là **record mới** khi ứng dụng republish sang queue/topic khác.
- **DLQ/DLT:** nơi chứa những message không được xử lý thành công theo chính sách.

### Các giá trị nên giữ ổn định

| Thuộc tính | Retry/redelivery cùng logical event | Khi tạo event con mới |
| --- | --- | --- |
| `correlation_id` | Thường **giữ nguyên** | Thường kế thừa nếu cùng workflow |
| `event_id` / logical message ID | Giữ nếu vẫn là cùng logical event | Tạo ID mới cho event mới |
| `delivery_attempt` / `attempt` | Thay đổi theo lần xử lý, nếu đo được đáng tin | Bắt đầu theo chính sách của event mới |
| Broker offset/delivery tag | Có thể thay theo broker/redelivery | Thường khác |
| `event_code` | Giữ hoặc đổi theo semantic retry | Đổi theo loại event con |
| `trace_id` / `span_id` | Theo chính sách tracing/instrumentation | Không tự giả định giữ cùng một span |

**Đừng coi `attempt=3` chỉ vì thấy ba lần log**. Một collector có thể nhận trùng, một logger có thể ghi nhiều lần, một message có thể bị xử lý lại sau crash. Số attempt đáng tin nên lấy từ cơ chế của framework/broker hoặc trạng thái retry do ứng dụng kiểm soát.

### Retry trực tiếp và retry bằng republish

**Redelivery từ broker** có thể giữ nguyên message và metadata ban đầu theo giao thức. **Republish** có thể tạo record mới, nên ứng dụng cần copy header/attribute theo allowlist. Một phương thức resend chỉ copy `payload` mà bỏ headers sẽ làm mất Correlation ID:

```java
// Minh họa lỗi logic: message mới không có correlation_id.
retryPublisher.send(originalPayload);
```

Cách thiết kế tốt hơn là có một **envelope** chứa payload + metadata được allowlist và một hàm copy/augment khi retry. Không sao chép vô hạn các header không tin cậy hoặc những thông tin nhạy cảm.

### DLQ phải giữ đủ thông tin điều tra

Khi message đi vào DLQ, nên có:

- Correlation ID được bảo toàn nếu hợp lệ.
- Logical event/message ID để nhận diện công việc.
- Event code/schema version.
- Nguồn ban đầu (topic/queue/exchange/routing key) theo khả năng và quyền dữ liệu.
- Lý do lỗi được chuẩn hóa, số attempt nếu đáng tin.
- Timestamp/metadata cần điều tra, theo schema.
- **Không dump vô hạn payload hoặc stack trace chứa secret**.

Một DLQ entry có Correlation ID nhưng không có logical message ID có thể nối được flow nhưng khó quyết định message nào đã xử lý thành công hoặc cần replay.

### Khi replay DLQ

Replay là **một lần xử lý mới của dữ liệu cũ**, không nhất thiết một message nghiệp vụ mới. Giữ ID gốc phục vụ đối chiếu, đồng thời có thể thêm `replay_id` hoặc `replay_attempt` để người vận hành biết đây là replay. Không tự thay Correlation ID mọi lần replay nếu mục tiêu là truy cùng incident; nếu replay bắt đầu một workflow mới theo nghiệp vụ, phải quy định rõ.

## 11. Producer/consumer bất đồng bộ và MDC: không rò giữa các message

Thread pool thường tái sử dụng worker. Ví dụ một consumer nhận `m-001` rồi `m-002` trên cùng thread. Nếu không cleanup MDC sau `m-001`, log của `m-002` có thể mang nhầm `correlation_id` hoặc `message_id` cũ.

Cách quản lý scope:

```java
Map<String, String> previous =
        MDC.getCopyOfContextMap();

try {
    MDC.put("correlation_id", validatedCorrelationId);
    MDC.put("message_id", messageId);
    handler.process(message);
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
```

Đây là **đoạn minh họa** trong handler có sẵn variables. Kỹ thuật snapshot/restore có ưu điểm:

1. Không để lại context cũ trên worker sau khi xử lý.
2. Hoạt động cả khi `handler.process` ném exception.
3. Có thể phục hồi những key do framework/scope cha đặt trước khi consumer scope bắt đầu.
4. Hạn chế scope con vô tình xóa toàn bộ ngữ cảnh cha bằng `MDC.clear()`.

Tuy nhiên, nếu instrumentation khác cố ý cập nhật context cha trong lúc handler chạy, việc restore snapshot có thể ghi đè update đó. Cần phân định **ownership và lifecycle** khi thiết kế thực tế.

### Một callback có thể chuyển thread lần nữa

Một consumer callback gửi tiếp task đến `CompletableFuture` hoặc executor khác. Khi đó MDC của callback thread không tự lan sang worker mới:

```java
CompletableFuture.runAsync(() -> {
    log.info("event=async.task.started");
});
```

Đây là snippet minh họa. Nếu cần giữ correlation, hãy dùng wrapper/context propagation của framework hoặc snapshot tại ranh giới submit; worker phải restore ngữ cảnh sau khi hoàn thành. Không dùng `InheritableThreadLocal` làm giải pháp tổng quát cho thread pool được tái sử dụng.

### Consumer batch

Nếu listener nhận một batch gồm A, B, C:

- Không đặt Correlation ID của **bản ghi đầu** rồi xử lý cả batch nếu các record có thể thuộc nhiều flow.
- Với mỗi record, đặt context riêng, xử lý, khôi phục rồi chuyển record tiếp.
- Log tổng hợp batch nên có một `batch_id`; không mượn `correlation_id` của record bất kỳ để đại diện cho toàn batch.
- Nếu batch processing bất đồng bộ, gắn context vào từng task record hoặc cơ chế propagation tương đương.

### Log4j 2 ThreadContext

Nếu dùng Log4j 2 API/Log4j 2 Core, có thể dùng `ThreadContext.put("correlation_id", id)` và `ThreadContext.get`. Đây là API tương tự MDC nhưng không tự đồng nhất với mọi provider SLF4J. Chọn một API logging nhất quán theo kiến trúc và kiểm tra bridge/provider thực tế.

## 12. Khi một consumer publish message mới

Đây là chỗ Correlation ID thường bị đứt:

```text
Producer A -- message m-001, cid=corr-42 --> Consumer B
                                              |
                                              +-- làm nghiệp vụ
                                              |
                                              +-- publish m-002
                                                  thiếu cid  ❌
```

Consumer B không chỉ cần **đọc** correlation để ghi log; nếu xử lý tạo thêm event trong **cùng luồng nghiệp vụ**, publisher của B phải **truyền tiếp**:

```text
Producer A -- m-001, cid=corr-42 --> Consumer B
                                              |
                                              +-- m-002, cid=corr-42
                                                        |
                                                        v
                                                    Consumer C
```

Một API nội bộ có thể thiết kế:

```java
record PublishContext(
        String correlationId,
        String causationId) {
}

void publishFollowUp(
        PublishContext context,
        BusinessEvent event) {
    // Map context vào message headers theo hợp đồng.
}
```

Đây là **phác thảo API**, chưa có implementation broker. `causation_id` có thể chỉ event cha trực tiếp (ví dụ `evt-1001`), còn `correlation_id` nối cả hành trình. Hai trường này có ích trong workflow dài có nhiều nhánh.

### Không nên chỉ đọc MDC trong publisher dùng chung

Một publisher library có thể được gọi từ:

- HTTP handler có MDC.
- Message consumer có MDC.
- Scheduled job không có request context.
- Startup hook không có correlation.
- Callback async chưa được propagate MDC.

Nếu publisher bắt buộc lấy `MDC.get("correlation_id")`, nó có thể thiếu ID trong các trường hợp sau. Thiết kế chắc chắn hơn thường là truyền **PublishContext tường minh** ở boundary hoặc dùng một abstraction context propagation đáng tin, rồi chỉ **chiếu** ID sang MDC để logging.

MDC là kênh quan sát, **không phải nguồn state nghiệp vụ được bảo đảm**. Với workflow quan trọng, correlation nên nằm trong envelope/command metadata mà mã nghiệp vụ có thể kiểm thử.

## 13. Tracing context và Correlation ID trong message

Một hệ thống hiện đại có thể dùng cả:

```text
correlation_id: corr-42
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

`traceparent` ở trên là **ví dụ cấu trúc W3C Trace Context**. Các API của OpenTelemetry/instrumentation có cơ chế inject/extract carrier (Kafka headers, AMQP properties, JMS properties) theo semantic conventions và propagator được cấu hình.

**Hai luồng truyền dữ liệu khác nhau nhưng có thể phối hợp:**

- Correlation ID giúp nối workflow/log theo quy ước nghiệp vụ.
- Tracing context cho phép tạo span/links, quan hệ producer–consumer và phân tích độ trễ.
- Consumer có thể bắt đầu một span mới hoặc liên kết với context của producer theo instrumentation và mô hình xử lý.
- Một message tồn tại trong broker rất lâu; không được giữ một span đang mở chỉ để “duy trì cùng correlation”.

### Không tự parse `traceparent` bằng thao tác chuỗi tùy tiện

Một `traceparent` hợp lệ có quy tắc định dạng, version và tính hợp lệ của Trace ID/Span ID. Sử dụng tracing SDK/propagator thay vì tự cắt substrings, tự tạo trace ID từ Correlation ID hoặc suy luận chỉ dựa trên một header.

### Baggage và thông tin nhạy cảm

Tracing baggage có thể được propagate qua nhiều service và bên thứ ba. Không đưa password, access token, dữ liệu thanh toán hoặc thông tin nhạy cảm vào baggage/header chỉ để tiện log. Hãy dùng allowlist, giới hạn kích thước và xem xét trust boundary trước khi propagate.

## 14. Thiếu, sai định dạng hoặc trùng Correlation ID

Không phải mọi message legacy đều có header. Consumer phải có chính sách rõ thay vì NPE hoặc ghép tất cả message thiếu header dưới một ID giả.

Các lựa chọn phổ biến tùy hệ thống:

1. **Strict contract:** reject hoặc đưa message sang DLQ với mã lỗi `MISSING_CORRELATION_ID` khi trường bắt buộc. Phù hợp contract yêu cầu producer có trách nhiệm.
2. **Compatibility mode:** tạo một Correlation ID mới cho message thiếu, ghi một event chuẩn hóa báo thiếu; hữu ích trong giai đoạn chuyển đổi, nhưng **mất liên kết với nguồn cũ**.
3. **Nullable semantics:** cho phép message độc lập không có correlation, log thiếu field nhưng không tạo ID giả; thích hợp nếu correlation thực sự tùy chọn.
4. **Backfill bằng metadata đáng tin:** nếu envelope có flow ID khác được xác thực, ánh xạ theo quy tắc đã công bố.

**Không nên mặc định `correlation_id=unknown` cho mọi message thiếu**, vì tất cả sẽ bị nhóm chung khi tra log.

### Ví dụ validate theo allowlist

Một chính sách nội bộ có thể dùng ID dài tối đa 64 ký tự, chỉ chứa chữ, số, dấu chấm, gạch dưới và gạch ngang:

```java
static boolean validCorrelationId(String value) {
    return value != null
            && value.length() >= 1
            && value.length() <= 64
            && value.matches("[A-Za-z0-9._-]+");
}
```

Đây là snippet đặt trong class Java. Nếu ID thật của dự án dùng UUID, ULID hoặc format khác, cần thiết kế validator tương ứng; đoạn trên **không phải validator cho W3C Trace ID**.

### Header lặp nhiều lần

Một số API cho phép nhiều header cùng tên. Nếu producer gửi hai `correlation_id` khác nhau, phải xác định:

- Reject message vì dữ liệu mơ hồ?
- Tin một header được ký/xác thực từ một hop tin cậy?
- Chọn header cuối/đầu theo một hợp đồng cụ thể?

**Không chỉ tùy tiện lấy header đầu hay cuối mà không có policy**. Ví dụ Kafka `lastHeader` có semantics chọn cuối; nó là API tiện dụng, không tự giải quyết vấn đề trust.

### Giới hạn kích thước và ký tự điều khiển

Một header do người ngoài kiểm soát có thể chứa chuỗi nhiều MB, newline hoặc Unicode điều khiển. Nếu đưa nguyên vào PatternLayout text, log injection có thể tạo các dòng trông giống sự kiện khác. Do vậy:

- Validate và giới hạn độ dài trước khi đặt vào MDC.
- Không ghi nguyên header không hợp lệ như một message chưa escape.
- Khi cần chẩn đoán, ghi **lý do lỗi/loại lỗi**, không dump toàn bộ raw value.
- Với JSON Lines, dùng encoder có escaping chuẩn.
- Kiểm tra header qua trust boundary, nhất là ở public API/gateway.

Correlation ID là **nhãn tra cứu**, không phải token xác thực.

## 15. Idempotency, ACK và exactly-once: điều Correlation ID không giải quyết

Giả sử consumer nhận `m-001`, gọi DB và xử lý thành công, nhưng crash **trước ACK/offset commit**. Broker có thể đưa lại cùng message. Hai lần xử lý đều mang `corr-42`; điều đó không ngăn việc trừ tiền hoặc gửi email hai lần.

Các cơ chế khác nhau:

| Cơ chế | Giải quyết gì? | Không tự đảm bảo |
| --- | --- | --- |
| Correlation ID | Liên kết log của một workflow | Không deduplicate |
| Message/event ID | Nhận diện logical event | Không tự lưu trạng thái đã xử lý |
| Idempotency store | Ghi nhận event/operation đã xử lý | Phải thiết kế transaction và lỗi cạnh tranh |
| ACK/offset commit | Xác nhận tiến độ tiêu thụ với broker | Không tự atomic với mọi side effect ở DB ngoài |
| Retry policy | Thử lại lỗi tạm | Không đảm bảo không nhân đôi |
| DLQ | Cách ly message không xử lý được | Không tự sửa dữ liệu hoặc bảo toàn replay |
| Distributed tracing | Quan hệ/span và thời gian | Không thay nghiệp vụ giao nhận |

**Correlation ID không phải exactly-once guarantee.** Ngay cả hệ thống có tính năng transactional/exactly-once trong một phạm vi broker cũng không mặc nhiên làm tất cả hiệu ứng bên ngoài (HTTP, payment gateway, DB khác) thành exactly-once.

### Một thiết kế idempotent đơn giản về ý tưởng

Consumer có thể ghi nhận `event_id` vào bảng dedup trong transaction cùng thay đổi dữ liệu nghiệp vụ. Nếu event ID đã được xử lý thành công, bỏ qua side effect, nhưng vẫn có thể log `event=message.duplicate_skipped` cùng Correlation ID.

Đây là **ý tưởng kiến trúc**, không phải implementation transaction hoàn chỉnh. Những race condition khi hai consumer xử lý cùng ID và các side effect bên ngoài DB phải được xử lý riêng.

### Khi nào tạo Message ID mới?

- **Redelivery của cùng record:** nhiều broker giữ record/delivery metadata gốc; logical ID vẫn có thể giữ.
- **Republish cùng logical event sang retry topic:** thường giữ `event_id` làm dedup key, dù record/offset mới.
- **Phát sinh một event khác do xử lý thành công:** tạo `event_id` mới, giữ `correlation_id` nếu thuộc workflow.
- **Replay của event cũ:** cần phân biệt `event_id` gốc với `replay_id` nếu nghiệp vụ có quy tắc replay mới.

Không lấy `correlation_id` làm khóa duy nhất để quyết định toàn bộ workflow đã hoàn thành; một ID correlation thường chứa nhiều event hợp lệ.

## 16. Structured logging để truy vết message hiệu quả

Một pattern text:

```text
%level|cid=%X{correlation_id}|mid=%X{message_id}|%msg%n
```

giúp developer nhìn rõ quan hệ. Nhưng để truy vấn và tổng hợp ổn định ở log store, nên xuất **field riêng** bằng JSON encoder/layout phù hợp:

```json
{
  "timestamp": "2026-01-01T00:00:00Z",
  "level": "WARN",
  "service": "billing-worker",
  "event_code": "message.retry_scheduled",
  "correlation_id": "corr-42",
  "message_id": "m-001",
  "attempt": 1,
  "broker": "kafka",
  "topic": "orders.events",
  "error_code": "UPSTREAM_TIMEOUT",
  "message": "Sẽ thử lại sau lỗi tạm thời"
}
```

Đây là **schema minh họa**, không phải output mặc định của Logback/Log4j 2. Các field của Kafka không áp dụng nguyên cho RabbitMQ/JMS. Đừng đặt tên `partition` hoặc `offset` cho message không có khái niệm đó.

Một cách gửi field event bằng **SLF4J 2.x fluent API**:

```java
log.atWarn()
        .addKeyValue("event_code", "message.retry_scheduled")
        .addKeyValue("message_id", messageId)
        .addKeyValue("attempt", attempt)
        .addKeyValue("error_code", "UPSTREAM_TIMEOUT")
        .log("Sẽ thử lại sau lỗi tạm thời");
```

Đây là snippet trong ứng dụng. `correlation_id` có thể đến từ MDC, còn `attempt` được đưa như số. **Để các key-value thực sự thành field JSON**, backend/encoder phải hỗ trợ và bật tính năng xuất. Chỉ thêm `addKeyValue` không biến PatternLayout text thành JSON tự động.

### Cách lập truy vấn

Một số câu hỏi có thể truy vấn bằng structured fields:

- Tìm theo `correlation_id="corr-42"` để xem toàn bộ workflow.
- Tìm `message_id="m-001"` để so sánh các attempt của cùng message.
- Nhóm `event_code="message.processing_failed"` theo `error_code` để xem lỗi phổ biến.
- Lọc `service="billing-worker"` và `attempt >= 3` khi tìm retry quá nhiều.
- Tìm log của producer và consumer theo cùng Correlation ID để phân biệt lỗi publish với lỗi consume.

Không biến Correlation ID thành **metric label cardinality cao**. Với metrics tổng hợp, thường nhóm theo `service`, `event_code`, `result` hoặc danh mục `error_code` có số lượng giới hạn, còn ID động dành cho log và trace.

## 17. Kiểm thử truyền Correlation ID qua message

Test quan trọng nhất là **kiểm tra metadata được chuyển chính xác từ producer tới consumer**, không chỉ kiểm tra `MDC.get` trong cùng JVM.

### Ma trận kiểm thử

| Kịch bản | Điều phải assert |
| --- | --- |
| Producer có context hợp lệ | Header/property của message có đúng Correlation ID |
| Consumer nhận message hợp lệ | MDC hoặc event context mang đúng ID khi xử lý |
| Message mới do consumer phát | ID được kế thừa nếu cùng workflow, message ID mới |
| Retry cùng logical event | ID không đổi, attempt thay theo hợp đồng |
| Republish sang retry topic | Header được copy đúng, không bỏ field cần thiết |
| Message vào DLQ | Correlation và event ID còn truy được, có lý do lỗi |
| Message thiếu header | Strict reject hoặc fallback theo policy; không NPE |
| Header sai format/ quá dài | Bị từ chối/normalize an toàn, không log injection |
| Header trùng tên khác giá trị | Xử lý theo duplicate policy, không chọn ngẫu nhiên |
| Worker thread tái sử dụng | Message B không mang MDC của A |
| Handler ném exception | `finally` cleanup/restore luôn chạy |
| Async callback/CompletableFuture | Propagation qua mỗi boundary theo thiết kế |
| Batch chứa nhiều Correlation ID | Từng record có context riêng |
| JSON encoder | Correlation ID thành field riêng, không chỉ nằm trong message |
| Broker reconnect/rebalance | Không mất ngữ cảnh của một delivery đang xử lý |
| Collector hoặc DLQ store | Có thể tìm lại theo ID với retention/quyền phù hợp |
| Producer được gọi ngoài HTTP | Có policy khi context thiếu; không lấy ID cũ |
| Duplicate delivery | Không tính hai nghiệp vụ chỉ vì hai log nhận message |

### 17.1. Unit test producer

Với Kafka/RabbitMQ/JMS, dùng producer test double hoặc công cụ test client phù hợp để **bắt đối tượng message được publish** và inspect headers/properties. Không đủ nếu chỉ assert rằng helper `getCorrelationId()` trả giá trị; phải xác minh **thư viện publish nhận đúng header/bytes**.

Với Kafka, kiểm tra value byte được decode UTF-8 đúng, không có nhiều header mâu thuẫn và có field ở record thực. Với RabbitMQ, xem `BasicProperties.getCorrelationId()`. Với JMS, xem `getJMSCorrelationID()`.

### 17.2. Unit test consumer

Tạo message có Correlation ID cố định, đưa vào consumer handler, capture logging event để kiểm tra:

- Đúng `correlation_id` trên sự kiện.
- Đúng `message_id`, `event_code`, mức log.
- Khi handler ném exception, cleanup vẫn chạy.
- Event phát **sau scope** trên cùng worker không mang ID cũ.

Với Logback có thể dùng `ListAppender<ILoggingEvent>` rồi kiểm tra `getMDCPropertyMap()`. Đây là test của **event**, không chứng minh console đã encode đúng text hoặc collector đã nhận dữ liệu.

### 17.3. Integration test broker

Trong môi trường test có broker thực hoặc broker được chạy riêng để kiểm thử:

1. Khởi động producer và consumer qua đường kết nối thật.
2. Đặt `correlation_id=corr-test-1` ở entrypoint hợp lệ.
3. Publish một message và xác minh metadata nhận tại consumer.
4. Tạo một lỗi có thể retry; kiểm tra ID qua các lần xử lý.
5. Tạo điều kiện đưa message vào DLQ; kiểm tra ID và provenance.
6. Publish message B với Correlation ID khác ngay sau A; kiểm tra không rò context.
7. Nếu consumer publish event C, xác minh header của C giữ ID đúng.
8. Nếu dùng tracing, kiểm tra `traceparent` bằng SDK/instrumentation.
9. Kiểm tra idempotency khi delivery trùng, không chỉ việc logging.
10. Theo dõi message cuối cùng tới collector nếu đó là hợp đồng hệ thống.

### 17.4. Test output console/JSON

Đối với Logback text, kiểm tra pattern có `%X{correlation_id}`. Đối với JSON, parse từng dòng thành object và assert type/value của `correlation_id`, `message_id`, `attempt`.

Không so sánh nguyên cả dòng nếu nó chứa timestamp, tên thread hoặc stack trace có thể thay đổi. Với JSON, thứ tự key không phải hợp đồng; so sánh các field đã parse.

### 17.5. Test retry không được nhầm semantics

Nếu ứng dụng log:

```text
event=message.received attempt=1
event=message.received attempt=2
event=message.processed attempt=2
```

thì đây có thể là **hai processing attempts của một logical event**, không phải ba event nghiệp vụ thành công. Hệ thống metric nên dùng mã sự kiện và điều kiện hoàn tất rõ ràng để đếm.

## 18. Chẩn đoán các lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Producer log có ID nhưng consumer không thấy | Không gắn header/property vào message | Inspect message thực ở producer và consumer. |
| Kafka consumer đọc `null` | Key sai tên, header không có hoặc dùng API sai | Kiểm tra record headers, encoding và duplicate policy. |
| RabbitMQ reply không match request | `correlationId` bị đổi, thiếu hoặc client dùng quy ước khác | Đối chiếu properties của request/reply và matcher. |
| JMS reply không ghép được | Nhầm `JMSMessageID` với `JMSCorrelationID` | Xác định request/reply convention. |
| Retry có Correlation ID mới | Handler tự tạo ID mỗi attempt | Giữ metadata gốc xuyên retry theo hợp đồng. |
| DLQ thiếu ID | Republish/DLX không bảo toàn metadata theo pipeline | Kiểm tra headers/properties tại từng hop và cấu hình framework. |
| Consumer B ghi ID của A | Không cleanup MDC ở worker thread | `finally` restore; test worker reuse. |
| Handler async mất ID | Không propagate context qua executor/reactive | Wrapper hoặc SDK propagation tại boundary. |
| Producer ngoài HTTP thiếu ID | Chỉ phụ thuộc MDC của request | PublishContext tường minh hoặc policy tạo ID tại boundary. |
| ID có newline tạo dòng log giả | Tin raw header từ nguồn ngoài | Validate, giới hạn, escape JSON đúng. |
| Hai header cùng key, khác ID | Nhiều middleware thêm header | Chính sách duplicate/conflict rõ ràng. |
| JSON không có field `correlation_id` | Encoder không xuất MDC, mapping collector sai | Kiểm tra event map → encoder → collector. |
| Cùng ID nhưng không phải cùng message | Correlation nối cả workflow | Dùng message/event ID để phân biệt. |
| Xử lý hai lần dù ID giống nhau | At-least-once/redelivery, thiếu idempotency | Dedupe bằng logical event ID và transaction policy. |
| Log có ID nhưng tra không ra lịch sử | Retention/collector, time filter hoặc quyền truy cập | Kiểm tra pipeline và kho trung tâm. |
| Correlation ID bị lộ qua third-party | Header/baggage propagate quá rộng | Áp trust boundary và allowlist. |
| Metric cardinality tăng | Gắn Correlation ID làm label | Dùng event/error code cho metrics; ID cho logs/traces. |
| Span ID giữ nguyên qua nhiều service | Truyền sai tracing context hoặc tái sử dụng span | Dùng instrumentation và kiểm tra parent/span links. |

### Quy trình điều tra theo từng hop

```text
Producer đang có Correlation ID hợp lệ?
   |
   +-- Không -> Entry boundary/context policy.
   |
   +-- Có -> Đã gắn vào message header/property?
                |
                +-- Không -> Publisher/serializer/interceptor.
                |
                +-- Có -> Consumer đọc đúng header/value?
                             |
                             +-- Không -> Key/encoding/transport/retry route.
                             |
                             +-- Có -> MDC/context có được đặt đúng scope?
                                          |
                                          +-- Không -> Consumer wrapper/lifecycle.
                                          |
                                          +-- Có -> Logging event chứa ID?
                                                       |
                                                       +-- Không -> Thread propagation/backend.
                                                       |
                                                       +-- Có -> Encoder xuất field?
                                                                    |
                                                                    +-- Không -> Pattern/JSON config.
                                                                    |
                                                                    +-- Có -> Collector nhận/index?
                                                                                 |
                                                                                 +-- Không -> Pipeline/retention.
                                                                                 |
                                                                                 +-- Có -> Truy vấn log/trace theo ID.
```

Chỉ thấy `MDC.get("correlation_id")` đúng tại một nơi không chứng minh metadata vẫn đúng sau retry hoặc service tiếp theo. Kiểm tra **đúng hop nơi mất ID** sẽ hiệu quả hơn việc thêm log debug hàng loạt.

## 19. An toàn và vận hành production

### Không truyền dữ liệu nhạy cảm để “dễ đối chiếu”

Header correlation chỉ nên chứa ID khó gây rò rỉ, không phải email, phone number, user JWT, session cookie, Authorization header hoặc toàn bộ JSON request. Nếu thực sự phải liên kết đối tượng nghiệp vụ, dùng ID được phép theo chính sách dữ liệu và quyền truy cập.

### Header từ bên ngoài không được mặc nhiên tin cậy

HTTP client, publisher bên thứ ba hoặc message từ queue không có ACL chặt có thể gửi ID giả. Validation format giúp giảm log injection, nhưng **không xác thực quyền**. Có thể phải sinh ID mới ở trust boundary và lưu ID đầu vào như metadata chẩn đoán đã được kiểm soát nếu cần.

### Chính sách log level và error code

Correlation ID rất hữu ích nhưng không có lý do để ghi mọi object vào INFO. Hãy có event code rõ cho:

- `message.published`: publisher tạo/phát event, không nhất thiết broker đã xử lý xong.
- `message.received`: consumer nhận một delivery.
- `message.retry_scheduled`: xử lý tạm lỗi, đã lên lịch retry theo policy.
- `message.processed`: kết quả nghiệp vụ thành công theo ranh giới đã định nghĩa.
- `message.processing_failed`: thất bại cuối cùng hoặc không phục hồi.
- `message.dead_lettered`: message được đưa sang DLQ/DLT, nếu hành vi được xác nhận.

**Đừng phát `message.processed` trước khi transaction quan trọng hoàn tất** và cũng đừng coi `message.published` tự chứng minh broker đã xác nhận. Nếu có publisher confirms/transaction, đặt tên sự kiện chính xác với thời điểm.

### Storage, throughput và sampling

Nếu một workflow có hàng nghìn message, tất cả cùng Correlation ID, việc log quá chi tiết có thể tạo lượng dữ liệu lớn. Chọn mức log, giới hạn payload và sampling có kiểm soát. Đảm bảo vẫn có event bắt đầu, kết thúc, lỗi/ retry quan trọng theo yêu cầu điều tra. Một log event có thể bị mất do queue/appender/collector; Correlation ID không tăng độ bền của pipeline.

### Correlation không bảo đảm order tuyệt đối

Trong hệ thống nhiều partition/consumer, các event cùng Correlation ID có thể xử lý song song hoặc được ingest theo thứ tự khác với thời điểm thực thi. Timestamp, broker offset và event sequence có thể bổ sung bối cảnh, nhưng không tự áp đặt total ordering cho toàn bộ hệ thống. Nếu business cần ordering, thiết kế partition key/consumer concurrency/serialization theo contract riêng.

## 20. Bài tập thực hành có đáp án

### Bài 1 — Correlation ID nằm ở đâu?

Producer đặt `MDC.put("correlation_id","corr-42")` và gọi Kafka producer chỉ với payload JSON không có header. Consumer có tự thấy `corr-42` không?

**Đáp án:** Không. MDC là context local; phải inject Correlation ID vào Kafka record header hoặc envelope theo hợp đồng rồi consumer extract và đặt vào logging context.

### Bài 2 — Hai message, một workflow

Có `m-001` và `m-002` cùng `correlation_id=corr-42`. Đó có phải duplicate message không?

**Đáp án:** Không nhất thiết. Chúng có thể là hai logical event trong một luồng nghiệp vụ. Muốn nhận diện duplicate cần logical message/event ID và idempotency policy.

### Bài 3 — Retry cùng logical event

`m-001` thất bại lần 1 và thành công lần 2. Tên `correlation_id` và `message_id` nên thay đổi như thế nào?

**Đáp án:** Theo policy thường giữ Correlation ID và logical message ID ổn định; attempt tăng. Khi republish qua topic mới, broker record/offset có thể thay dù logical ID được giữ trong metadata.

### Bài 4 — RabbitMQ request/reply

Một client publish request có `correlationId=corr-42`, responder gửi reply với Correlation ID khác. Điều gì có thể xảy ra?

**Đáp án:** Client matcher có thể không ghép được reply với request ban đầu nếu nó dựa trên `correlationId` do client đặt. Cần theo đúng request/reply convention, không tùy tiện tạo ID mới ở responder.

### Bài 5 — JMS ID confusion

Có `JMSMessageID=ID:abc` và `JMSCorrelationID=corr-42`. Hai trường có cùng nghĩa không?

**Đáp án:** Không. `JMSMessageID` là định danh message do provider gán theo cơ chế JMS; `JMSCorrelationID` dùng liên kết theo ứng dụng/giao thức. Trong một số request/reply convention, reply Correlation ID có thể tham chiếu ID message của request.

### Bài 6 — Batch chứa nhiều ID

Kafka consumer poll một batch gồm hai record có Correlation ID khác nhau. Vì sao đặt MDC theo record đầu cho cả batch là sai?

**Đáp án:** Log của record B bị gắn nhầm ID A. Cần đặt/restore context theo từng record hoặc task, và dùng batch ID riêng cho log tổng hợp.

### Bài 7 — DLQ không có metadata

Một handler republish payload sang DLQ nhưng không copy headers. Việc gì trở nên khó khăn?

**Đáp án:** Mất Correlation ID, event ID và metadata gốc; khó truy vấn đường đi, phân biệt retry và đối chiếu replay. Cần policy copy/allowlist fields và test qua DLQ thật.

### Bài 8 — Đọc ID từ nguồn không tin cậy

Một publisher gửi header `correlation_id` dài 100.000 ký tự có newline. Có nên gắn nguyên vào MDC không?

**Đáp án:** Không. Giới hạn format/length, kiểm tra trust boundary, từ chối hoặc thay ID theo chính sách; không in raw header gây log injection.

### Bài 9 — Bảo đảm không bị xử lý trùng

Hai lần giao cùng event đều mang Correlation ID giống nhau. Có thể dùng một bảng với khóa Correlation ID để bỏ lần thứ hai không?

**Đáp án:** Thường không. Một workflow có nhiều event hợp lệ cùng Correlation ID. Dedupe nên dựa trên logical event/idempotency key được định nghĩa cho operation, cùng cơ chế transaction phù hợp.

### Bài 10 — Kiểm thử end-to-end

Hãy đề xuất một bài test producer → broker → consumer → retry → DLQ.

**Đáp án gợi ý:** Đặt Correlation ID xác định; inspect header ở producer; consumer extract và log đúng field; cố tình lỗi tạm cho retry; kiểm tra ID qua retry; cố tình lỗi vĩnh viễn cho DLQ; đảm bảo metadata gốc còn; chạy message B trên cùng worker để phát hiện MDC leak; parse JSON console/collector để tra theo ID.

## 21. Checklist thiết kế và triển khai

- [ ] Xác định Correlation ID dùng cho workflow nào và tạo tại boundary nào.
- [ ] Phân biệt Correlation ID với Message ID, event ID, attempt, Trace ID và Span ID.
- [ ] Chọn tên header/property và encoding thống nhất cho producer/consumer.
- [ ] Có chính sách xử lý header thiếu, rỗng, quá dài, sai format hoặc trùng tên.
- [ ] Producer gắn Correlation ID **vào message thật**, không chỉ đặt trong MDC.
- [ ] Consumer đọc từ transport metadata rồi validate trước khi đưa vào logging context.
- [ ] Listener/callback khôi phục/clear context trong `finally` khi kết thúc một message.
- [ ] Async task, retry callback và worker pool có context propagation đúng.
- [ ] Message con của cùng workflow kế thừa Correlation ID; event ID mới theo semantic.
- [ ] Retry giữ logical ID/context cần thiết, attempt theo policy đáng tin.
- [ ] DLQ/DLT có Correlation ID, logical event ID, nguồn và lỗi phục vụ điều tra.
- [ ] Request/reply tuân theo convention riêng của RabbitMQ/JMS.
- [ ] Nếu có tracing, dùng tracing propagator chuẩn để inject/extract `traceparent`.
- [ ] Không dùng Correlation ID làm idempotency key cho cả workflow một cách mù quáng.
- [ ] Có kế hoạch xử lý duplicate delivery, ACK/commit và transaction.
- [ ] Logging pattern hoặc JSON encoder xuất ID thành text/field theo schema.
- [ ] Test producer header, consumer MDC, message kế tiếp, retry, DLQ và collector.
- [ ] Không log secrets/PII/raw headers; validate ID từ nguồn ngoài.
- [ ] Không đưa ID có cardinality cao thành nhãn metric tổng hợp.
- [ ] Giới hạn retention/volume và thiết kế truy xuất log khi container/node mất.
- [ ] Biết cách phát hiện và sửa ID bị đứt ở đúng một hop của pipeline.

**Kết luận:** Truyền Correlation ID qua message là một **hợp đồng end-to-end**: tạo hoặc nhận ID ở boundary → inject vào header/property/envelope → broker vận chuyển → consumer extract và validate → đưa vào MDC/ThreadContext trong scope xử lý → restore sau khi xong → tiếp tục propagate khi publish event con, retry hoặc DLQ. Làm đúng các bước này giúp truy vết một workflow xuyên service và thread mà không đánh đồng Correlation ID với Message ID, Trace ID hoặc cơ chế chống xử lý trùng.