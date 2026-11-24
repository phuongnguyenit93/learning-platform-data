# Bridge giữa adapter và channel khác

## 1. Bối cảnh và mục tiêu

Trong Spring Integration, một inbound adapter thường phát message vào `MessageChannel`. Phần xử lý phía sau có thể đã được xây dựng với một channel khác, hoặc tổ chức thành nhiều integration flow độc lập. Khi cần nối **đầu ra của adapter** với **channel đầu vào của flow tiếp theo** mà không thực hiện biến đổi nghiệp vụ, ta dùng **Bridge**.

Bridge là một *Enterprise Integration Pattern*: một endpoint tiêu thụ message từ channel nguồn và chuyển nó sang channel đích. Spring Integration cung cấp cơ chế bridge thông qua Java DSL, XML namespace và các thành phần framework tương ứng. Bridge đặc biệt hữu ích khi hai phần của hệ thống dùng tên channel ổn định nhưng được cấu hình, triển khai hoặc di chuyển theo từng giai đoạn.

Bài này thuộc chương **Tạo integration flow** của module **SPRING_INTEGRATION_ADAPTERS**. Phạm vi của module là kết nối hệ thống ngoài qua inbound/outbound adapter, gateway, poller và `MessageChannel`; triển khai luồng với file, SFTP, HTTP, JMS, AMQP, Kafka, cơ sở dữ liệu; đồng thời xử lý hợp đồng message, lỗi và vòng đời kết nối.

Sau bài học, người học có thể:

- Giải thích vì sao cần Bridge và phân biệt bridge với channel, router, transformer, gateway.
- Nối một file inbound adapter với channel của một integration flow khác bằng Java DSL `.bridge()`.
- Cấu hình `<int:bridge>` trong XML namespace.
- Phân biệt hành vi bridge qua `DirectChannel` và qua `QueueChannel` cần poller.
- Hiểu bridge giữ payload/headers và ảnh hưởng của channel lên thread, transaction, timeout.
- Thiết kế lỗi, retry, backpressure và chống xử lý trùng khi ghép hai flow.
- Kiểm thử đường đi thực sự qua **channel nguồn → bridge → channel đích → handler**.

**Giới hạn:** Bridge là bước nối message. Nó không tự chuyển đổi schema, bảo đảm lưu bền vững, nhận ACK từ broker hoặc bảo đảm exactly-once khi hệ thống ngoài xử lý.

## 2. Bridge thực hiện điều gì?

Giả sử file inbound adapter quét thư mục `./inbox` rồi gửi từng `Message<File>` vào `adapter.files`. Trong khi đó, một flow xử lý CSV hiện có bắt đầu từ `processing.files`. Để nối hai phần mà vẫn giữ nguyên tên channel, ta thêm bridge:

~~~mermaid
flowchart LR
    DIR[("Thư mục inbox")]
    SRC["File inbound adapter<br/>+ poller"]
    A["adapter.files<br/>DirectChannel"]
    B["Bridge endpoint"]
    C["processing.files<br/>DirectChannel"]
    VALID["Filter / Validate"]
    HANDLER["CSV processor<br/>hoặc outbound adapter"]
    DIR --> SRC --> A --> B --> C --> VALID --> HANDLER
~~~

Bridge thường nhận một message và **chuyển tiếp cùng nội dung nghiệp vụ** sang channel đích. Không có quy tắc parse CSV, chuyển kiểu dữ liệu hay tự nhận biết đích HTTP/SFTP/JMS chỉ vì message đi qua bridge.

| Thành phần | Câu hỏi nó giải quyết | Ví dụ |
| --- | --- | --- |
| Inbound adapter | Dữ liệu từ bên ngoài được đưa vào hệ thống thế nào? | File/SFTP poller, JMS listener. |
| `MessageChannel` | Producer và consumer bàn giao message qua đâu? | `adapter.files`, `processing.files`. |
| **Bridge** | Làm thế nào nối hai channel mà không thay payload theo nghiệp vụ? | `adapter.files → processing.files`. |
| Transformer | Payload cần đổi từ kiểu nào sang kiểu nào? | `File → List<Order>`. |
| Filter | Message nào được phép tiếp tục? | Bỏ file rỗng hoặc từ chối bản ghi sai. |
| Router | Message phải được đưa đến nhánh nào? | `VND → payments.vnd`, `USD → payments.usd`. |
| Gateway | Một request có cần reply để quay về caller/flow không? | HTTP outbound gateway, messaging gateway. |

### 2.1. Bridge không giống một channel

Channel là đường truyền message; Bridge là **endpoint** có đầu vào và đầu ra. Khi cấu hình:

~~~text
source-channel  ──> Bridge ──> destination-channel
~~~

framework phải có consumer cho `source-channel` và có consumer tiếp theo cho `destination-channel` nếu muốn message được xử lý đến cuối. Việc khai báo hai channel cùng tồn tại **không tự tạo liên kết** giữa chúng.

Nếu adapter có thể cấu hình trực tiếp tới channel đích và không cần giữ ranh giới trung gian, có thể trỏ adapter thẳng tới channel đó. Bridge phát huy tác dụng khi cần giữ hợp đồng channel cũ, nối hai flow độc lập, hoặc thay đổi hành vi bàn giao tại một ranh giới rõ ràng.

### 2.2. Bridge có làm message thành message mới không?

Về mặt nghiệp vụ, bridge chỉ chuyển tiếp: payload và các header phục vụ xử lý/correlation tiếp tục đi qua. Trong điều kiện thông thường, BridgeHandler không yêu cầu đổi dữ liệu nghiệp vụ. Tuy nhiên, không nên dựa vào **danh tính object Java** hoặc tưởng rằng sau khi đi qua một broker, serializer hay mapper thì mọi header nội bộ vẫn giống hệt.

Điểm cần kiểm tra là **hợp đồng**: kiểu payload, correlation ID, metadata nghiệp vụ và các header cần thiết để trả reply/lỗi phải có ở đầu bên kia theo cơ chế transport đang dùng.

## 3. Java DSL: bridge hai channel sẵn có

Ví dụ rút gọn:

~~~java
@Bean
IntegrationFlow filesBridgeFlow() {
    return IntegrationFlow.from("adapter.files")
            .bridge()
            .channel("processing.files")
            .get();
}
~~~

Giả định trong Spring context đã có hai bean channel tên `adapter.files` và `processing.files`. Flow trên đăng ký một Bridge endpoint nhận message ở `adapter.files` và chuyển sang `processing.files`.

- `IntegrationFlow.from("adapter.files")`: chỉ ra channel đầu vào của flow.
- `.bridge()`: tạo handler trung gian với mục đích chuyển tiếp message.
- `.channel("processing.files")`: xác định channel nhận đầu ra của bridge.
- `.get()`: hoàn tất khai báo flow để Spring đăng ký endpoint.

Đây là một **flow nối channel**, không phải adapter chủ động đọc nguồn. Nó không có `MessageSource` hay `Poller` trừ khi channel nguồn là kiểu cần poll hoặc do flow khác cung cấp message.

Cú pháp Java DSL có thể dùng bean reference cho channel thay vì ID chuỗi, tùy cách tổ chức cấu hình. Khi dùng tên chuỗi, phải khớp chính xác bean name; ví dụ `processing.file` và `processing.files` là hai tên khác nhau.

### 3.1. Có cần viết .bridge() ở mọi lần chuyển channel không?

**Không.** Trong một `IntegrationFlow` tuyến tính, có thể chuyển message qua `.channel(...)` rồi tiếp tục bước xử lý. Framework DSL cung cấp cơ chế nối các endpoint và channel trong flow.

Bridge tường minh phù hợp khi **đích chỉ là một channel của flow khác** hoặc muốn người đọc thấy rõ ranh giới nối hai channel. Ví dụ:

~~~java
@Bean
IntegrationFlow normalizeAndForward() {
    return IntegrationFlow.from("raw.orders")
            .filter(Order.class, order -> order.amount() > 0)
            .transform(Order.class, this::normalizeOrder)
            .channel("normalized.orders")
            .get();
}
~~~

Đoạn này là *minh họa*: `Order` và `normalizeOrder` do ứng dụng tự cung cấp. Trong flow có transform/filter rồi chuyển channel; không cần thêm bridge thuần túy trước mỗi bước.

Ngược lại, nếu chỉ muốn nối `adapter.files` sang `processing.files` mà không chuyển đổi dữ liệu, flow `.bridge()` ở đầu mục diễn đạt mục đích trực tiếp hơn.

## 4. Ví dụ hoàn chỉnh: file inbound adapter → bridge → processing flow

Tình huống thực hành: ứng dụng đọc file `*.csv` từ `./inbox` mỗi 5 giây. Adapter phát `Message<File>` vào `adapter.files`. Một Bridge chuyển nó sang `processing.files`. Flow cuối kiểm tra file không rỗng, sau đó ghi tên file và header vào một bean nhận kết quả.

Kiến trúc cố ý chia **ba flow nhỏ**: nguồn file, bridge, xử lý. Cách này cho phép thay nguồn file thành SFTP/JMS/Kafka mà vẫn dùng lại phần xử lý nếu hợp đồng payload/headers tương thích.

### 4.1. Dependencies

Với Spring Boot đã quản lý phiên bản dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-file</artifactId>
</dependency>
~~~

Ví dụ dùng Java 17+ và API phổ biến của Spring Integration 6.x. Đặt toàn bộ mã dưới đây trong tệp `BridgeApplication.java`, package `demo.bridge`. Chỉ một class có modifier `public`, các class khác package-private để minh họa gọn.

### 4.2. Cấu hình nguồn, bridge và consumer

~~~java
package demo.bridge;

import java.io.File;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.FileReadingMessageSource;
import org.springframework.integration.file.filters.AcceptOnceFileListFilter;
import org.springframework.integration.file.filters.CompositeFileListFilter;
import org.springframework.integration.file.filters.SimplePatternFileListFilter;
import org.springframework.messaging.MessageChannel;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class BridgeApplication {
    public static void main(String[] args) {
        SpringApplication.run(BridgeApplication.class, args);
    }
}

@Configuration
class BridgeConfiguration {

    @Bean(name = "adapter.files")
    MessageChannel adapterFiles() {
        return new DirectChannel();
    }

    @Bean(name = "processing.files")
    MessageChannel processingFiles() {
        return new DirectChannel();
    }

    @Bean
    MessageSource<File> csvFileSource(
            @Value("${app.inbox:./inbox}") String inbox) {

        File directory = new File(inbox);
        if (!directory.exists() && !directory.mkdirs()) {
            throw new IllegalStateException(
                    "Không tạo được thư mục nguồn: " + directory);
        }
        if (!directory.isDirectory()) {
            throw new IllegalStateException(
                    "Đường dẫn nguồn không phải thư mục: " + directory);
        }

        var source = new FileReadingMessageSource();
        source.setDirectory(directory);

        var filters = new CompositeFileListFilter<File>();
        filters.addFilter(new SimplePatternFileListFilter("*.csv"));
        filters.addFilter(new AcceptOnceFileListFilter<>());
        source.setFilter(filters);

        return source;
    }

    // Flow 1: inbound adapter phát message vào channel nguồn.
    @Bean
    IntegrationFlow fileInboundFlow(MessageSource<File> csvFileSource) {
        return IntegrationFlow
                .from(csvFileSource,
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(Duration.ofSeconds(5))
                                        .maxMessagesPerPoll(5)))
                .channel("adapter.files")
                .get();
    }

    // Flow 2: bridge nối hai channel mà không đổi payload.
    @Bean
    IntegrationFlow fileBridgeFlow() {
        return IntegrationFlow.from("adapter.files")
                .bridge()
                .channel("processing.files")
                .get();
    }

    // Flow 3: xử lý sau bridge.
    @Bean
    IntegrationFlow fileProcessingFlow(FileReceiver receiver) {
        return IntegrationFlow.from("processing.files")
                .filter(File.class,
                        file -> file.isFile() && file.length() > 0)
                .handle(File.class, (file, headers) -> {
                    receiver.record(
                            file.getName(),
                            (String) headers.get("traceId"));
                    return null; // one-way: không sinh reply
                })
                .get();
    }
}

record ReceivedFile(String fileName, String traceId) {}

@Component
class FileReceiver {

    private final List<ReceivedFile> results =
            new CopyOnWriteArrayList<>();

    void record(String name, String traceId) {
        results.add(new ReceivedFile(name, traceId));
        System.out.println("CSV accepted: " + name);
    }

    List<ReceivedFile> received() {
        return List.copyOf(results);
    }

    void clear() {
        results.clear();
    }
}
~~~

Các phần được nối ra sao?

1. `csvFileSource` là bean `MessageSource<File>`. `fileInboundFlow` gắn poller vào source; khi tìm được file CSV, source phát `Message<File>`.
2. `fileInboundFlow` gửi message đến `adapter.files`. Nó không gọi trực tiếp `FileReceiver`.
3. `fileBridgeFlow` subscribe `adapter.files`, dùng BridgeHandler chuyển message sang `processing.files`.
4. `fileProcessingFlow` subscribe `processing.files`, kiểm tra file và ghi nhận vào `FileReceiver`.
5. `FileReceiver` lưu thông tin cho mục đích demo và test; nó không gửi HTTP hoặc ghi database.

Ví dụ trên sử dụng `DirectChannel` ở hai ranh giới, nên khi một message được nguồn gửi vào `adapter.files`, bridge và handler phía sau thường thực thi trong cùng thread cho đến khi xử lý kết thúc. Poller vẫn chịu trách nhiệm kích hoạt nguồn; bridge không có lịch riêng.

### 4.3. Đường đi của một file

~~~mermaid
sequenceDiagram
    participant P as File poller
    participant S as csvFileSource
    participant A as adapter.files
    participant B as Bridge
    participant C as processing.files
    participant H as FileReceiver
    P->>S: receive()
    S-->>P: Message<File> hoặc null
    P->>A: send(Message<File>)
    A->>B: handle(message)
    B->>C: send(message)
    C->>H: filter + record
    H-->>P: hoàn tất xử lý đồng bộ
~~~

Nếu poller chạy mà không có file, `receive()` có thể trả `null` và không có message nào được đưa vào bridge. Nếu handler đọc CSV sau này chậm, `DirectChannel` sẽ làm lượt poll kéo dài; cấu hình `fixedDelay` không bảo đảm số file được xử lý mỗi giây.

**Tính tin cậy của demo:** `AcceptOnceFileListFilter` chỉ nhớ file đã nhận trong bộ nhớ của tiến trình. Nó không đủ để chống đọc trùng xuyên restart, nhiều instance hay trường hợp file đã bị nhận nhưng handler phía sau thất bại. Muốn an toàn hơn cần policy file-đã-ghi-xong, metadata store bền vững, archive/quarantine và idempotency theo nghiệp vụ.

## 5. Kiểm thử bridge có thực sự nối hai channel

Để kiểm chứng Bridge, hãy gửi message trực tiếp vào **channel adapter** và quan sát consumer của **channel processing**. Cách này kiểm tra wiring của hai flow mà không phải đợi lịch poll.

Thêm dependency kiểm thử:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tạo `BridgeApplicationTest.java` trong package `demo.bridge`:

~~~java
package demo.bridge;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest(properties = "app.inbox=./target/bridge-test-inbox")
class BridgeApplicationTest {

    @Autowired
    @Qualifier("adapter.files")
    MessageChannel adapterFiles;

    @Autowired
    FileReceiver receiver;

    @BeforeEach
    void clearResults() {
        receiver.clear();
    }

    @Test
    void forwardsFileAndKeepsTraceHeader() throws Exception {
        Path csv = Files.createTempFile("bridge-", ".csv");
        try {
            Files.writeString(csv, "id,amount\n1,100\n",
                    StandardCharsets.UTF_8);

            boolean sent = adapterFiles.send(
                    MessageBuilder.withPayload(csv.toFile())
                            .setHeader("traceId", "trace-test-01")
                            .build());

            assertTrue(sent);
            assertEquals(
                    List.of(new ReceivedFile(
                            csv.getFileName().toString(), "trace-test-01")),
                    receiver.received());
        } finally {
            Files.deleteIfExists(csv);
        }
    }
}
~~~

Test trên xác nhận:

- `adapter.files` tồn tại và có Bridge consumer.
- Bridge chuyển được message sang `processing.files`.
- Consumer phía sau nhận payload `File`.
- Header `traceId` được bảo toàn trên đường đi qua bridge.
- Hai `DirectChannel` giúp test có thể kiểm tra kết quả ngay sau `send()`.

**Giới hạn kiểm thử:** test gửi trực tiếp vào channel nên **không** kiểm tra poller, quét thư mục hay filter `*.csv` ở source. Để kiểm tra inbound adapter thật, đặt file vào thư mục test trước/sau khi context chạy và chờ kết quả bằng điều kiện có timeout. Không dùng `Thread.sleep(...)` tùy ý làm bằng chứng rằng poller hoạt động đúng.

## 6. Bridge trên QueueChannel: khi nào cần poller?

Trong ví dụ mục 4, `adapter.files` là `DirectChannel`: sender bàn giao ngay cho bridge subscriber. Nếu cần tách tốc độ nhận file với tốc độ xử lý phía sau, có thể thay ranh giới bằng `QueueChannel`. Khi đó **Bridge là consumer của một pollable channel**, nên phải có poller để lấy message khỏi queue.

~~~mermaid
flowchart LR
    A["Inbound adapter"]
    Q["buffered.files<br/>QueueChannel(capacity=100)"]
    P["Bridge endpoint<br/>với Poller"]
    D["processing.files<br/>DirectChannel"]
    H["Handler"]
    A -->|"offer/message"| Q
    Q -->|"poll()"| P
    P --> D --> H
~~~

### 6.1. Cấu hình bằng Java DSL

Ví dụ dưới đây là **biến thể** cho một ranh giới message; không đăng ký đồng thời với bridge trên `adapter.files` ở ví dụ mục 4 nếu chưa thiết kế lại topology.

~~~java
@Bean(name = "buffered.files")
QueueChannel bufferedFiles() {
    return new QueueChannel(100);
}

@Bean
IntegrationFlow queueToProcessingBridge() {
    return IntegrationFlow.from("buffered.files")
            .bridge(endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofMillis(500))
                            .maxMessagesPerPoll(10)))
            .channel("processing.files")
            .get();
}
~~~

Trong snippet này cần import `QueueChannel`, `IntegrationFlow`, `Pollers`, `Duration` và `@Bean`; `processing.files` cùng flow consumer phía sau phải được cấu hình riêng.

- `QueueChannel(100)` đặt sức chứa bộ đệm để tránh queue tăng không giới hạn; cần xử lý chính sách khi queue đầy.
- `.bridge(endpoint -> endpoint.poller(...))` tạo consumer có lịch lấy message từ queue.
- `maxMessagesPerPoll(10)` giới hạn số message xử lý trong mỗi lần kích hoạt poller; nó không tự gộp mười message thành một batch.
- `processing.files` nhận từng message từ Bridge, sau đó chuyển đến handler theo loại channel đích.

**Chú ý:** `QueueChannel` mặc định sử dụng bộ đệm trong bộ nhớ và không tự cung cấp độ bền qua restart. Nếu ứng dụng dừng khi message đang nằm trong queue, message có thể mất nếu không có persistent message store hoặc cơ chế giao hàng bền vững khác.

### 6.2. DirectChannel và QueueChannel khác nhau ở đâu?

| Tiêu chí | `DirectChannel → Bridge → DirectChannel` | `QueueChannel → Bridge poller → DirectChannel` |
| --- | --- | --- |
| Khi nào Bridge chạy? | Ngay khi source gửi message. | Khi poller lấy message khỏi queue. |
| Thread thông thường | Cùng thread producer. | Thread polling khác với thread đưa message vào queue. |
| Có bộ đệm giữa hai phần? | Không có queue do DirectChannel tạo. | Có queue với capacity được cấu hình. |
| Cần poller tại Bridge? | Không. | Có, vì đầu vào là `PollableChannel`. |
| Transaction của producer | Có thể xuyên qua các bước đồng bộ trên cùng thread. | Không tự động đi xuyên qua ranh giới queue/thread. |
| Áp lực tải | Handler chậm làm producer chậm theo. | Queue hấp thụ một phần chênh lệch tốc độ, nhưng có nguy cơ đầy. |
| Khôi phục sau restart | Phụ thuộc nguồn/đích. | Cần chính sách bền vững cho queue và ack/retry. |

Đặt QueueChannel làm vùng đệm là **quyết định kiến trúc**, không phải cách bật chế độ “gửi tin cậy” bằng một dòng cấu hình. Cần quyết định capacity, chính sách full queue, transaction, retry, trạng thái message đang xử lý và giám sát backlog.

## 7. Cấu hình Bridge với XML namespace

Spring Integration cũng hỗ trợ Bridge trong core XML namespace. Ví dụ hai channel đồng bộ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:int="http://www.springframework.org/schema/integration"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           http://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/integration
           http://www.springframework.org/schema/integration/spring-integration.xsd">

    <int:channel id="adapter.files"/>
    <int:channel id="processing.files"/>

    <int:bridge id="filesBridge"
                input-channel="adapter.files"
                output-channel="processing.files"/>

    <!-- Consumer tiếp theo của processing.files được cấu hình riêng. -->
</beans>
~~~

`<int:bridge>` tạo endpoint chuyển message từ `input-channel` sang `output-channel`. Nó không tự đăng ký file inbound adapter; producer cần gửi message vào `adapter.files`, đồng thời phải có consumer phù hợp ở `processing.files`.

### 7.1. XML khi bridge nhận từ QueueChannel

~~~xml
<int:channel id="buffered.files">
    <int:queue capacity="100"/>
</int:channel>

<int:channel id="processing.files"/>

<int:bridge id="bufferedFilesBridge"
            input-channel="buffered.files"
            output-channel="processing.files">
    <int:poller fixed-delay="500"
                max-messages-per-poll="10"/>
</int:bridge>
~~~

Cấu hình trên là **một ví dụ độc lập**; `<int:queue>` tạo queue và poller lấy message khỏi đó. Tên channel phải khớp với nơi adapter gửi message vào. Nếu nguồn là inbound file adapter, đầu ra có thể trỏ thẳng tới `buffered.files`.

Nếu ứng dụng dùng Spring Boot, có thể nạp XML qua `@ImportResource("classpath:integration/bridge-flow.xml")`. Tránh đăng ký thêm một Java DSL bridge trên cùng hai channel nếu không muốn có nhiều consumer trùng chức năng.

## 8. Bridge với inbound/outbound adapter của các giao thức

Bridge hoạt động với message của nhiều nguồn khi channel và payload contract tương thích. Các trường hợp phổ biến:

| Nguồn hoặc đích | Bridge kết nối ở đâu? | Điều cần kiểm soát |
| --- | --- | --- |
| File inbound | File adapter → channel đầu ra → Bridge → flow parse CSV. | File đã ghi xong, accept-once, archive và lỗi parse. |
| SFTP inbound | SFTP adapter → channel chung → Bridge → file processor. | Remote filter, local sync, session, reconnect và duplicate. |
| HTTP inbound gateway | HTTP gateway → channel → Bridge → handler trả reply. | Giữ đường `replyChannel`, timeout, response mapping. |
| JMS/AMQP inbound | Message-driven adapter → Bridge → business flow. | Transaction/ack, redelivery, converter và DLQ. |
| Kafka inbound | Kafka adapter → Bridge → flow xử lý. | Topic/partition, offset commit, ordering và idempotency. |
| JDBC polling | JDBC message source → Bridge → validation/handler. | Query checkpoint, lock, transaction và dữ liệu trùng. |
| HTTP/JMS/Kafka outbound | Business flow → Bridge → channel tới outbound endpoint. | Producer acknowledgement, lỗi không chắc chắn và retry. |

**Bridge không tạo ra kết nối giao thức.** Ví dụ SFTP cần session factory và adapter riêng; JMS cần connection factory/listener container; Kafka cần producer/consumer configuration. Bridge chỉ nhìn thấy message đã được Spring Integration nhận vào channel.

### 8.1. Đổi adapter mà không thay logic downstream

Có thể tổ chức một channel hợp đồng, ví dụ `orders.normalized`, rồi mỗi adapter dùng một flow chuẩn hóa dữ liệu trước khi chuyển vào channel này:

~~~mermaid
flowchart TB
    F["File/SFTP inbound"]
    K["Kafka inbound"]
    H["HTTP inbound"]
    TF["Parse CSV → OrderEvent"]
    TK["Deserialize → OrderEvent"]
    TH["Validate JSON → OrderEvent"]
    C["orders.normalized<br/>MessageChannel"]
    P["Business processor"]
    F --> TF --> C
    K --> TK --> C
    H --> TH --> C
    C --> P
~~~

Đây là ví dụ cho **tái sử dụng channel**, chưa nhất thiết cần bridge ở mỗi nhánh. Khi adapter đã phát payload đúng `OrderEvent` và chỉ cần chuyển đến channel chuẩn, bridge là phù hợp. Khi payload còn là `File`, byte array hoặc DTO riêng giao thức, phải **transform/validate trước** rồi mới bridge. Đừng đưa dữ liệu sai hợp đồng qua bridge với kỳ vọng downstream tự hiểu.

### 8.2. Bridge không thay thế router hoặc publish–subscribe

Nếu cần chọn **một trong nhiều đích** theo currency hoặc loại sự kiện, dùng router. Nếu cần phát **cùng một message tới nhiều consumer**, dùng `PublishSubscribeChannel` hoặc flow multicast có chiến lược xử lý lỗi. Một Bridge cơ bản chỉ nối **một channel đầu vào với một channel đầu ra**, không tạo fan-out tự động.

Nếu có hai Bridge cùng subscribe một `DirectChannel`, message thường được dispatcher của channel bàn giao cho một subscriber theo chiến lược phân phối, không mặc nhiên đi qua cả hai. Để nhân bản dữ liệu cho hai hệ thống ngoài, cần thiết kế broadcast, transaction và idempotency ở từng nhánh riêng.

## 9. Hợp đồng message: payload, headers và reply

Bridge giúp tách topology mà không thay đổi thông tin nghiệp vụ. Chính vì thế, hai bên cần thỏa thuận rõ **contract**.

~~~text
Message<OrderEvent>
  payload:
    eventId: "evt-4711"
    orderId: "ORD-1001"
    amount: 250000
  headers:
    correlationId: "trace-ord-1001"
    sourceSystem: "sftp-import"
    idempotencyKey: "order:ORD-1001"
~~~

| Thành phần | Bridge nên làm gì? | Điều downstream phải hiểu |
| --- | --- | --- |
| Payload type | Chuyển tiếp payload đã có. | DTO/schema/serialization tương thích consumer. |
| `correlationId` | Giữ metadata được dùng để truy vết. | Nối log giữa adapter, bridge, handler và đích. |
| `sourceSystem` | Không làm mất nguồn gốc dữ liệu. | Xác định chính sách xử lý theo nguồn. |
| `idempotencyKey` | Chuyển tiếp giá trị ổn định nếu có. | Chống side effect lặp tại handler/đích. |
| `replyChannel` | Bảo toàn đường reply khi flow request–reply dùng channel nội bộ. | Handler phải phát reply đúng nơi. |
| `errorChannel` | Bảo toàn thông tin điều hướng lỗi khi có. | Error handler phải được cấu hình phù hợp. |

Không đưa toàn bộ `MessageHeaders` qua HTTP, JMS, AMQP hay Kafka một cách vô điều kiện: header nội bộ có thể là object `MessageChannel` không phù hợp để serialize. Mapper của adapter giao thức quyết định header nào có thể đi qua ranh giới mạng.

### 9.1. Bridge trong flow request–reply

Giả sử một `@MessagingGateway` gọi channel `orders.requests`, Bridge chuyển sang `orders.processor` và service activator cuối trả `OrderResult`. Nếu đường reply được giữ và handler tạo kết quả, gateway có thể nhận reply từ flow phía sau.

~~~mermaid
sequenceDiagram
    participant G as MessagingGateway
    participant A as orders.requests
    participant B as Bridge
    participant P as orders.processor
    participant H as Handler
    G->>A: Request + replyChannel
    A->>B: Message
    B->>P: Message
    P->>H: handle
    H-->>G: Reply tới replyChannel
~~~

Tuy nhiên Bridge **không tự sinh reply**. Nếu handler cuối trả `void` hoặc filter loại message âm thầm, gateway mong đợi một DTO có thể chờ tới timeout. Với channel bất đồng bộ, reply có thể đến muộn; cần quy định rõ timeout và trạng thái nghiệp vụ chưa chắc chắn.

## 10. Thread, transaction và backpressure tại điểm Bridge

Bridge không tự quyết định đồng bộ hay bất đồng bộ; **loại channel và endpoint** quyết định chuyện đó.

- Với `DirectChannel → Bridge → DirectChannel`, xử lý thường diễn ra cùng thread gửi message. Exception từ handler đích có thể lan ngược tới inbound endpoint hoặc caller.
- Với `QueueChannel → Bridge poller`, việc nhận message từ queue nằm trên thread poller, nên không tự chia sẻ transaction với thread đặt message vào queue.
- Với `ExecutorChannel`, downstream có thể chạy trên thread của executor; cần giới hạn thread pool, queue nội bộ và xử lý error độc lập.
- Với broker JMS/Kafka/AMQP, nguồn có cơ chế ack/offset riêng; Bridge trong Spring Integration không tự quyết định thời điểm commit của broker.

Một Bridge đi vào QueueChannel có thể giúp hấp thụ chênh lệch tốc độ, nhưng khi đích chậm hơn nguồn trong thời gian dài, backlog vẫn tăng cho đến khi chạm giới hạn. Lúc đó producer có thể block, send thất bại hoặc hệ thống áp dụng chính sách overload tương ứng.

### 10.1. Transaction có đi xuyên Bridge không?

Nếu tất cả bước dùng `DirectChannel` đồng bộ, phạm vi transaction của thread có thể bao gồm cả handler phía sau khi được cấu hình phù hợp. Nhưng một Bridge **không tự tạo transaction**. Khi chuyển qua queue, executor hoặc broker, không nên giả định cùng một transaction database vẫn bao phủ cả bên nhận.

Ví dụ nguồn JDBC đọc record và handler gửi HTTP qua Bridge: transaction JDBC không thể tự động rollback HTTP request đã được đối tác xử lý. Cần cân nhắc outbox, trạng thái gửi, idempotency và đối soát theo hợp đồng.

### 10.2. Khi nào không nên thêm một channel trung gian?

Nếu chỉ có một adapter, một transformer và một handler trong cùng flow, việc chèn nhiều channel/bridge chỉ để “chia nhỏ code” có thể làm topology khó đọc hơn mà không đem lại lợi ích. Nên có ranh giới channel khi cần:

1. Giữ giao diện tích hợp ổn định giữa các nhóm/module.
2. Nối flow cấu hình từ nhiều nơi hoặc quá trình migration.
3. Chọn một cơ chế bàn giao khác (queue, executor, publish–subscribe).
4. Quản lý, đo đạc hoặc thay đổi consumer ở ranh giới cụ thể.

Đối với mục tiêu đơn giản, có thể nối trực tiếp adapter vào channel đích hoặc dùng một `IntegrationFlow` tuyến tính.

## 11. Xử lý lỗi khi bridge ghép hai luồng

Có ít nhất ba vị trí lỗi:

~~~mermaid
flowchart TD
    S["Inbound adapter nhận dữ liệu"]
    B["Bridge chuyển message"]
    H["Handler / outbound adapter"]
    OK["Hoàn thành theo hợp đồng"]
    E1["Lỗi nguồn / polling"]
    E2["Lỗi dispatch / không có subscriber"]
    E3["Lỗi xử lý / hệ thống đích"]
    S --> B --> H --> OK
    S -.-> E1
    B -.-> E2
    H -.-> E3
~~~

| Lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Lỗi nguồn | SFTP timeout, file permission, JDBC query thất bại. | Retry/backoff ở nguồn, reconnect và cảnh báo. |
| Không dispatch được | Channel đích không có consumer, queue đầy, endpoint dừng. | Kiểm tra wiring, giới hạn queue và lifecycle. |
| Lỗi validation | Message đi qua bridge nhưng payload sai format. | Validate đúng chỗ, error flow/quarantine thay vì retry vô hạn. |
| Đích thất bại | HTTP timeout, JMS broker unavailable, database rollback. | Retry có idempotency, DLQ, trạng thái gửi và đối soát. |
| Kết quả không rõ | Đối tác xử lý thành công nhưng response bị mất. | Kiểm tra bằng business key; tránh gửi lặp mù quáng. |

**Không xem việc message đã được Bridge chuyển sang channel là “đã hoàn tất nghiệp vụ”.** Thành công ở ranh giới này chứng minh message được bàn giao nội bộ, còn trạng thái thực tế phải được xác nhận ở handler/đích theo protocol.

### 11.1. Error channel và thread

Với channel đồng bộ, exception có thể truyền theo call stack về poller hoặc gateway. Với poller, executor, listener hoặc queue, exception có thể được phát thành `ErrorMessage` tới một `errorChannel` được cấu hình, hoặc được xử lý theo policy của endpoint.

Bridge không phải nơi xử lý toàn bộ lỗi. Hãy đặt retry ở tầng biết rõ nguyên nhân: lỗi kết nối được xử lý ở adapter/client; lỗi schema ở validator; lỗi side effect ở outbound handler với idempotency và chiến lược phục hồi.

### 11.2. Hành vi khi downstream tạm dừng

Nếu `processing.files` chưa có subscriber hoặc consumer đang dừng, một `DirectChannel` có thể không dispatch được message. Nếu phía trước là inbound file source sử dụng accept-once trong RAM, file có thể đã bị đánh dấu trong source trước khi lỗi downstream xuất hiện. Cần cơ chế phục hồi và kiểm thử cụ thể; chỉ start lại Bridge/handler không tự chứng minh file sẽ được phát lại.

Nếu muốn tách thời điểm nhận dữ liệu và xử lý, chọn queue/broker có chính sách lưu trữ cùng cơ chế giám sát thích hợp, thay vì trông chờ Bridge giữ message.

## 12. Lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Adapter gửi message nhưng flow sau không chạy. | Sai tên channel, không có Bridge consumer, endpoint chưa start. | Kiểm tra bean channel và `IntegrationFlow.from(...)`/XML bridge. |
| Bridge không được gọi dù có message trong QueueChannel. | Thiếu poller cho Bridge consumer. | Cấu hình `.bridge(endpoint -> endpoint.poller(...))` hoặc XML `<int:poller>`. |
| Hai bridge cùng nhận một DirectChannel nhưng chỉ một chạy. | `DirectChannel` không mặc định broadcast. | Dùng `PublishSubscribeChannel` nếu yêu cầu fan-out. |
| Payload đến đích sai kiểu. | Bridge không làm transform; source phát `File` nhưng consumer đòi `Order`. | Chuẩn hóa/validate payload trước ranh giới channel. |
| Request–reply bị timeout. | Mất đường reply, handler không tạo reply hoặc message bị filter loại. | Kiểm tra `replyChannel`, phản hồi nghiệp vụ và timeout. |
| Poller chậm sau khi thêm Bridge. | Downstream xử lý đồng bộ và giữ thread poller. | Đo latency, giới hạn công việc mỗi poll và chọn channel phù hợp. |
| Message mất khi restart sau khi thêm QueueChannel. | Queue chỉ lưu RAM; không có persistent state. | Dùng persistent message store hoặc broker và retry phù hợp. |
| File bị xử lý trùng. | Hai nguồn/poller cùng đọc, filter không bền vững hoặc redelivery. | Một nguồn rõ ràng, lock/checkpoint và idempotency. |
| Đích nhận hai lần sau retry. | Side effect thành công nhưng response bị mất. | Dùng idempotency key và đối soát. |
| Lỗi chỉ thấy trong log background. | Chuyển thread nhưng thiếu error flow/metric. | Thiết kế error channel, DLQ và correlation ID. |

## 13. Kiểm tra topology khi triển khai thực tế

Trước khi đưa Bridge vào flow đang vận hành, cần xác minh từng đầu nối bằng một message mẫu:

1. Xác nhận inbound adapter thực sự tạo payload kiểu gì và header nào đi kèm.
2. Xác nhận tên channel mà adapter gửi ra và loại channel (`DirectChannel` hay `QueueChannel`).
3. Xác nhận Bridge đăng ký đúng **input channel**, không có consumer trùng ngoài dự kiến.
4. Xác nhận Bridge gửi tới **output channel** chính xác.
5. Xác nhận downstream có subscriber/poller và handler nhận đúng payload.
6. Dùng correlation ID để kiểm tra message đi qua tất cả bước; đo thời gian gửi/nhận và lỗi.
7. Mô phỏng dừng downstream, queue đầy, exception và restart để kiểm chứng phục hồi.

Một lưu ý khi kết hợp XML và Java DSL: cả hai cùng đăng ký bean trong application context. Không nên vừa khai báo `<int:bridge input-channel="adapter.files" ...>` vừa thêm flow `.bridge()` cùng mục đích mà không chủ động thiết kế nhiều consumer. Việc này có thể làm message được phân phối không như dự kiến.

### 13.1. Các metric hữu ích

Ở ranh giới Bridge, theo dõi số message tới channel nguồn, số message được chuyển tiếp, số message xử lý thành công ở downstream, lỗi gửi channel, độ sâu queue và độ trễ. Nếu có broker hoặc outbound side effect, theo dõi thêm xác nhận/ack, retry, dead-letter và duplicate theo business key.

Trường hợp Spring Integration version/config hỗ trợ Micrometer hoặc observation, có thể cấu hình metric/trace tại endpoint và channel. Đừng log toàn bộ payload hoặc headers nhạy cảm chỉ để theo dõi một bridge; ID và metadata có chọn lọc thường đủ để truy vết.

## 14. Thực hành: bridge file inbound với flow thanh toán

**Tình huống:** một inbound adapter nhận file thanh toán CSV từ SFTP và phát `Message<File>`. Một service xử lý thanh toán hiện có chỉ lắng nghe `payments.files`. Bạn cần nối hai phần mà không thay đổi code xử lý hiện tại.

Yêu cầu:

1. Định nghĩa channel nguồn `sftp.files` và channel đích `payments.files`.
2. Tạo Bridge bằng Java DSL, bảo toàn payload `File` và header `sourceSystem`.
3. Thêm poller ở SFTP inbound adapter; giải thích vì sao với `DirectChannel` Bridge không cần poller riêng.
4. Thay `sftp.files` bằng `QueueChannel(100)`, chuyển poller sang Bridge consumer và giải thích khác biệt về thread/transaction.
5. Viết test gửi `Message<File>` có `correlationId` vào `sftp.files`; xác minh handler nhận đúng header và payload.
6. Thiết kế một nhánh quarantine cho file sai cấu trúc trước khi ghi database.
7. Mô phỏng lỗi database sau khi file đã được source nhận; xác định cách replay file an toàn và chống ghi trùng.
8. Mô phỏng hai instance cùng poll SFTP; đề xuất lock/partition/checkpoint thích hợp.

**Tiêu chí hoàn thành:** sơ đồ có đúng nguồn, channel, Bridge và consumer; test đi qua Bridge thật; giải thích được vì sao message không cần thay payload khi đã cùng hợp đồng và vì sao Bridge không tự bảo đảm retry/ACK.

## 15. Câu hỏi tự kiểm tra

1. Bridge khác `MessageChannel` thế nào?
2. Khi nào nên dùng `IntegrationFlow.from("source").bridge().channel("target")`?
3. Có thể trỏ adapter trực tiếp tới channel đích mà không dùng Bridge không? Khi nào phù hợp?
4. Bridge có tự parse `File` thành `Order` không?
5. Tại sao Bridge nhận từ `QueueChannel` cần poller?
6. `maxMessagesPerPoll(10)` đếm message hay số dòng trong một file?
7. Với `DirectChannel`, handler downstream chậm tác động thế nào đến thread của inbound adapter?
8. Hai Bridge cùng subscribe một `DirectChannel` có mặc nhiên cùng nhận mỗi message không?
9. Bridge có thể giữ `replyChannel` cho request–reply không? Điều kiện nào để caller nhận phản hồi?
10. Vì sao một `QueueChannel` trong RAM không bảo đảm khôi phục sau restart?
11. Khi handler lỗi sau khi file đã được accept-once, poller tiếp theo có tự phát lại file không?
12. Bằng cách nào kiểm tra hợp đồng payload/headers khi thay file inbound bằng Kafka inbound?

**Gợi ý:** Bridge là endpoint chuyển tiếp giữa hai channel; poller dành cho nguồn pollable; thread do channel/endpoint quyết định; adapter nguồn và handler đích chịu trách nhiệm về tính tin cậy theo giao thức và trạng thái nghiệp vụ.

## 16. Ghi nhớ

**Bridge giữa adapter và channel khác** là cách nối hai vùng của một hệ thống Spring Integration mà không làm biến đổi nội dung nghiệp vụ của message. Bridge giúp giữ tên channel ổn định, tách cấu hình nguồn và downstream, hỗ trợ tổ chức các flow Java DSL/XML theo ranh giới rõ ràng.

Khi kết nối file, SFTP, HTTP, JMS, AMQP, Kafka hoặc cơ sở dữ liệu, Bridge chỉ chuyển message trên hệ thống channel. **Hợp đồng payload/headers, đồng bộ hay queue/poller, xử lý lỗi, idempotency và xác nhận của đích** vẫn phải được thiết kế riêng. Kiểm thử qua cả hai channel và downstream là cách chứng minh Bridge đã được đăng ký, kết nối và vận hành đúng.

