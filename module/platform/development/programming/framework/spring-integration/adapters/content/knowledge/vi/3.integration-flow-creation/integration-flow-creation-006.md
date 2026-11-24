# Đăng ký adapter như một bean độc lập

## 1. Bài toán và mục tiêu

Trong Spring Integration, một **adapter** nối hệ thống bên ngoài với luồng message. Một inbound adapter nhận dữ liệu từ bên ngoài rồi phát `Message<?>` vào `MessageChannel`; một outbound adapter nhận message từ channel rồi gửi dữ liệu ra ngoài. Có thể khai báo adapter trực tiếp trong `IntegrationFlow`, nhưng đôi khi sẽ hữu ích hơn khi đăng ký **thành phần kết nối như một Spring bean riêng** và nối bean đó vào flow.

Bài này thuộc chương **Tạo integration flow** của module **SPRING_INTEGRATION_ADAPTERS**, tập trung kết nối hệ thống ngoài qua inbound/outbound adapter, gateway, poller và `MessageChannel`. Các tình huống file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu đều đặt ra cùng một câu hỏi: **thành phần nào đọc/gửi dữ liệu, thành phần nào kích hoạt nó, và thành phần nào xử lý message?** Thiết kế độc lập bean giúp trả lời rõ ba trách nhiệm đó, kiểm soát lỗi và vòng đời kết nối.

Sau bài học, người học có thể:

- Phân biệt **bean chứa khả năng đọc/gửi** với **endpoint có đăng ký channel và lifecycle**.
- Tạo một `MessageSource<File>` bằng `@Bean` và kích hoạt nó bằng `@InboundChannelAdapter` hoặc Java DSL.
- Tạo một `MessageHandler` cho outbound bằng `@Bean`, nối với channel qua `@ServiceActivator` hoặc `IntegrationFlow.handle(...)`.
- Dùng dependency injection thay cho việc tự `new` adapter trong nhiều nơi.
- Hiểu cách đặt tên bean, chia sẻ cấu hình nguồn/đích và không đăng ký hai endpoint cạnh tranh.
- Phân tích các nguy cơ polling trùng, lỗi khi xử lý, timeout, transaction và dừng/khởi động adapter.
- Kiểm thử cả bean riêng lẻ lẫn tuyến message thực sự qua Spring context.

**Điểm quan trọng nhất:** đăng ký một `MessageSource` hay `MessageHandler` thành bean **chưa tự bảo đảm có integration endpoint hoạt động**. Nguồn cần một polling/message-driven endpoint; handler cần một consumer đăng ký với channel. Bean độc lập cung cấp năng lực và dependency, còn endpoint xác định thời điểm và cách gọi bean đó.

## 2. Tách ba lớp: bean, endpoint và integration flow

Xét một ứng dụng quét thư mục CSV rồi chuyển file sang thư mục đích.

~~~mermaid
flowchart LR
    SRC[("Thư mục nguồn")]
    MS["Bean MessageSource<File><br/>FileReadingMessageSource"]
    EP1["Inbound polling endpoint<br/>+ Poller"]
    IN["files.detected<br/>MessageChannel"]
    FLOW["IntegrationFlow<br/>lọc / chuyển đổi"]
    OUT["files.toArchive<br/>MessageChannel"]
    EP2["Outbound endpoint<br/>Service activator"]
    MH["Bean MessageHandler<br/>FileWritingMessageHandler"]
    DST[("Thư mục đích")]
    SRC --> MS
    EP1 -->|"receive()"| MS
    MS -->|"Message<File>"| EP1
    EP1 --> IN --> FLOW --> OUT --> EP2 --> MH --> DST
~~~

| Thành phần | Là gì? | Đăng ký bằng gì? |
| --- | --- | --- |
| `FileReadingMessageSource` | Một bean biết cách tìm file và trả `Message<File>` khi `receive()`. | `@Bean` hoặc một bean XML. |
| Inbound polling endpoint | Thành phần gọi source theo lịch rồi gửi message tới channel. | `@InboundChannelAdapter`, Java DSL `IntegrationFlow.from(source, ...)` hoặc XML. |
| `MessageChannel` | Đường bàn giao message; có thể đồng bộ hoặc bất đồng bộ. | `@Bean DirectChannel`, channel DSL hoặc XML. |
| `IntegrationFlow` | Tuyến biến đổi, lọc và điều hướng message giữa các endpoint. | Method `@Bean` trả `IntegrationFlow`. |
| `FileWritingMessageHandler` | Bean biết cách ghi dữ liệu ra hệ thống file. | `@Bean`. |
| Outbound consumer endpoint | Đăng ký handler nhận message từ channel đích. | `@ServiceActivator`, Java DSL `.handle(handler)` hoặc XML. |

Trong Spring, **bean** là đối tượng do container quản lý với injection, cấu hình và vòng đời phụ thuộc kiểu của nó. Trong Spring Integration, **endpoint** là cấu hình hoạt động tại một ranh giới message: nó nhận hoặc phát message qua channel, đôi khi tự có thread, poller hoặc listener.

Hai khái niệm liên quan nhưng không đồng nhất:

- Chỉ có `@Bean MessageSource<File>`: source tồn tại nhưng **không có scheduler tự gọi `receive()`**.
- Chỉ có `@Bean MessageHandler`: handler tồn tại nhưng **không tự subscribe vào channel**.
- Có bean nguồn **và** annotation/DSL tạo inbound endpoint: poller bắt đầu đọc nguồn khi endpoint chạy.
- Có bean handler **và** endpoint nhận từ channel: message được chuyển đến handler khi có consumer tương ứng.

Lợi ích của việc tách là có thể inject cùng bean vào những đối tượng cần kiểm tra cấu hình, viết unit test cho logic, thay thế bằng fake trong test và lựa chọn hình thức wiring thích hợp mà không gắn chặt code kết nối với toàn bộ flow.

## 3. Những cách đăng ký adapter được Spring Integration hỗ trợ

Có hai nhóm cách tổ chức thường dùng:

**Cách A: annotation trên method tạo bean.** Method `@Bean` trả source hoặc handler, còn `@InboundChannelAdapter` hay `@ServiceActivator` tạo endpoint tương ứng. Khai báo ngắn gọn, nhìn từ bean có thể thấy ngay channel đầu/cuối.

~~~java
@Bean
@InboundChannelAdapter(
        value = "files.detected",
        poller = @Poller(fixedDelay = "5000"))
MessageSource<File> csvFileSource() {
    return createFileSource();
}

@Bean
@ServiceActivator(inputChannel = "files.toArchive")
MessageHandler archiveHandler() {
    return createFileWriter();
}
~~~

`createFileSource()` và `createFileWriter()` là factory method minh họa; ví dụ chạy được ở mục 4 triển khai thực tế.

**Cách B: bean thuần + DSL nối sau.** Bean nguồn và handler không chứa thông tin endpoint. `IntegrationFlow` inject các bean đó rồi tạo polling endpoint và consumer.

~~~java
@Bean
MessageSource<File> csvFileSource() {
    return createFileSource();
}

@Bean
MessageHandler archiveHandler() {
    return createFileWriter();
}

@Bean
IntegrationFlow csvFlow(MessageSource<File> csvFileSource,
                        MessageHandler archiveHandler) {
    return IntegrationFlow
            .from(csvFileSource,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(Duration.ofSeconds(5))))
            .handle(archiveHandler)
            .get();
}
~~~

Các đoạn trên là **hai lựa chọn thay thế**. Nếu cùng một source vừa được `@InboundChannelAdapter` kích hoạt vừa được `IntegrationFlow.from(source, poller)` sử dụng, hai poller có thể cạnh tranh đọc dữ liệu. Nếu cùng handler được đăng ký thêm hai lần, ứng dụng có thể gửi lặp hoặc phân phối message không như dự kiến.

Tách bean độc lập là một lựa chọn tổ chức code; **không đồng nghĩa phải tạo hai endpoint cho cùng một adapter**.

## 4. Ví dụ hoàn chỉnh: đăng ký inbound và outbound adapter bằng bean riêng

Ta xây ứng dụng quét file `.csv` trong `./inbox`, bỏ qua file rỗng và copy các file còn lại sang `./archive`.

Kiến trúc có ba phần:

1. Bean `FileReadingMessageSource` biết cách tìm file trong thư mục.
2. Bean `FileWritingMessageHandler` biết cách ghi file vào thư mục đích.
3. Annotation `@InboundChannelAdapter` và `@ServiceActivator` kết nối hai bean với các channel. `IntegrationFlow` ở giữa chịu trách nhiệm kiểm tra.

Mã dưới đây dùng Java 17+, Spring Boot với phiên bản Spring Integration tương thích. Đây là ví dụ để hiểu bean và endpoint; **chưa có quy trình chống duplicate và transaction bền vững giữa nguồn và đích**.

### 4.1. Dependencies

Trong Maven, dùng dependency management của Spring Boot:

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

`spring-boot-starter-integration` cung cấp phần core Spring Integration; module `spring-integration-file` cung cấp `FileReadingMessageSource` và `FileWritingMessageHandler`. Không cần tự ghi version nếu BOM phù hợp đã quản lý.

### 4.2. Code ứng dụng

Tạo tệp `AdapterBeansApplication.java` trong package `demo.adapterbeans`:

~~~java
package demo.adapterbeans;

import java.io.File;
import java.nio.file.Files;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.file.FileReadingMessageSource;
import org.springframework.integration.file.FileWritingMessageHandler;
import org.springframework.integration.file.filters.AcceptOnceFileListFilter;
import org.springframework.integration.file.filters.CompositeFileListFilter;
import org.springframework.integration.file.filters.SimplePatternFileListFilter;
import org.springframework.integration.file.support.FileExistsMode;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@SpringBootApplication
@EnableIntegration
public class AdapterBeansApplication {

    public static void main(String[] args) {
        SpringApplication.run(AdapterBeansApplication.class, args);
    }
}

@Configuration
class AdapterBeansConfiguration {

    @Bean(name = "files.detected")
    MessageChannel filesDetected() {
        return new DirectChannel();
    }

    @Bean(name = "files.toArchive")
    MessageChannel filesToArchive() {
        return new DirectChannel();
    }

    // Nguồn inbound là bean độc lập.
    @Bean
    @InboundChannelAdapter(
            value = "files.detected",
            poller = @Poller(
                    fixedDelay = "5000",
                    maxMessagesPerPoll = "3"))
    MessageSource<File> csvFileSource(
            @Value("${app.inbox:./inbox}") String inbox) {

        File directory = new File(inbox);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException(
                    "Không tạo được thư mục: " + directory);
        }

        var source = new FileReadingMessageSource();
        source.setDirectory(directory);

        var filters = new CompositeFileListFilter<File>();
        filters.addFilter(new SimplePatternFileListFilter("*.csv"));
        filters.addFilter(new AcceptOnceFileListFilter<>());
        source.setFilter(filters);

        return source;
    }

    // Flow biến đổi/lọc độc lập với chi tiết đọc/ghi file.
    @Bean
    IntegrationFlow csvValidationFlow() {
        return IntegrationFlow.from("files.detected")
                .filter(File.class,
                        file -> file.isFile() && file.length() > 0)
                .channel("files.toArchive")
                .get();
    }

    // Bộ ghi outbound cũng là bean độc lập.
    @Bean
    @ServiceActivator(inputChannel = "files.toArchive")
    MessageHandler archiveWriter(
            @Value("${app.archive:./archive}") String archive) {

        File directory = new File(archive);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException(
                    "Không tạo được thư mục: " + directory);
        }

        var writer = new FileWritingMessageHandler(directory);
        writer.setFileExistsMode(FileExistsMode.REPLACE);
        writer.setExpectReply(false);
        return writer;
    }
}
~~~

Cấu hình hoạt động:

- `filesDetected()` và `filesToArchive()` tạo hai bean channel với tên tường minh. `DirectChannel` thường gọi subscriber ngay trên thread gửi.
- `csvFileSource(...)` trả bean `MessageSource<File>`. Annotation `@InboundChannelAdapter` đăng ký endpoint **polling** để gọi `receive()` và phát message vào `files.detected`.
- Bộ lọc `SimplePatternFileListFilter("*.csv")` chọn file theo tên. `AcceptOnceFileListFilter` giúp tránh phát lặp cùng file trong vòng đời của bộ lọc ở bộ nhớ; không cung cấp checkpoint bền vững xuyên restart.
- `csvValidationFlow()` nhận `Message<File>`, loại file rỗng và chuyển message hợp lệ sang `files.toArchive`.
- `archiveWriter(...)` tạo bean `MessageHandler` có khả năng ghi file. Annotation `@ServiceActivator` đăng ký consumer của channel `files.toArchive`.
- `FileExistsMode.REPLACE` là một lựa chọn minh họa khi tên file đích đã tồn tại. Production cần xác định có được phép ghi đè hay phải tạo tên duy nhất/đưa vào kiểm tra.
- `setExpectReply(false)` thể hiện bước ghi file là một thao tác **outbound one-way**: handler không cần trả message tiếp cho flow.

Trong method tạo bean có `@Value`, Spring inject cấu hình từ application properties. Giá trị mặc định ở ví dụ là `./inbox` và `./archive`. Các thư mục được tạo khi khởi tạo bean để demo dễ khởi động.

Để dùng đường dẫn tùy chỉnh:

~~~properties
app.inbox=./runtime/inbox
app.archive=./runtime/archive
~~~

Tệp có thể là `application.properties` trong `src/main/resources` hoặc cấu hình tương đương của Spring Boot. Với hệ thống thật, đường dẫn phải được kiểm soát quyền truy cập, dung lượng đĩa và phân vùng lưu trữ.

### 4.3. Message đi qua các bean thế nào?

~~~mermaid
sequenceDiagram
    participant P as Poller endpoint
    participant S as csvFileSource bean
    participant C as files.detected
    participant F as csvValidationFlow
    participant O as files.toArchive
    participant H as archiveWriter bean
    P->>S: receive()
    S-->>P: Message<File> hoặc null
    P->>C: send(Message<File>)
    C->>F: filter file hợp lệ
    F->>O: send(Message<File>)
    O->>H: handleMessage(message)
    H-->>H: Copy file vào archive
~~~

Điểm dễ nhầm nhất: Spring không cần gọi lại method Java `csvFileSource()` sau mỗi 5 giây. Method đó chạy khi tạo bean; endpoint định kỳ gọi `receive()` trên **object MessageSource** đã được tạo.

Tương tự, Spring không tạo `FileWritingMessageHandler` mới mỗi khi file xuất hiện. Bean handler được dùng lại theo lifecycle của container. Nếu client/handler giữ session hoặc connection pool, việc tạo nó một lần giúp quản lý cấu hình và tài nguyên thống nhất.

## 5. Biến thể: đăng ký adapter chỉ bằng @Bean rồi nối qua Java DSL

Nhiều dự án muốn đặt adapter trong một class cấu hình riêng và giữ mọi thông tin channel/poller trong `IntegrationFlow`. Khi đó bỏ hai annotation endpoint khỏi factory method: source và handler chỉ là bean thuần.

Ví dụ sau là **cấu hình thay thế** cho phần tương ứng ở mục 4, không được đăng ký đồng thời trên cùng nguồn/đích.

~~~java
@Configuration
class SeparateAdapterConfiguration {

    @Bean
    MessageSource<File> independentFileSource() {
        var source = new FileReadingMessageSource();
        source.setDirectory(new File("./inbox"));
        source.setFilter(new SimplePatternFileListFilter("*.csv"));
        return source;
    }

    @Bean
    MessageHandler independentFileWriter() {
        var writer = new FileWritingMessageHandler(
                new File("./archive"));
        writer.setExpectReply(false);
        return writer;
    }

    @Bean
    IntegrationFlow fileCopyFlow(
            MessageSource<File> independentFileSource,
            MessageHandler independentFileWriter) {

        return IntegrationFlow
                .from(independentFileSource,
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(
                                        Duration.ofSeconds(5))))
                .filter(File.class,
                        file -> file.isFile() && file.length() > 0)
                .handle(independentFileWriter)
                .get();
    }
}
~~~

Các import cần có gồm `@Configuration`, `@Bean`, `MessageSource`, `MessageHandler`, `IntegrationFlow`, `Pollers`, `Duration`, `File`, `FileReadingMessageSource`, `FileWritingMessageHandler` và `SimplePatternFileListFilter`.

Ở biến thể này:

1. `independentFileSource()` tạo bean nguồn.
2. `independentFileWriter()` tạo bean handler đích.
3. Method `fileCopyFlow(...)` nhận **bean đã được Spring inject** qua tham số, tránh gọi trực tiếp một method `@Bean` để lấy đối tượng mới.
4. `IntegrationFlow.from(source, endpoint -> endpoint.poller(...))` tạo inbound polling endpoint dùng bean nguồn.
5. `.handle(handler)` tạo consumer endpoint dùng bean handler.

**Lưu ý riêng cho demo này:** sử dụng `SimplePatternFileListFilter` đơn lẻ chỉ lọc theo tên, không cung cấp cơ chế *accept once*. Để tránh phát lại file trong các lượt poll, bổ sung `AcceptOnceFileListFilter` hoặc một cơ chế lọc/trạng thái bền vững phù hợp. Đồng thời tạo thư mục nguồn/đích trước khi chạy như phần trước.

Hai phương án thể hiện **cùng trách nhiệm**:

| Mục đích | Annotation + bean | Bean thuần + Java DSL |
| --- | --- | --- |
| Tạo nguồn | `@Bean MessageSource<File>` | `@Bean MessageSource<File>` |
| Tạo lịch đọc | `@InboundChannelAdapter(... @Poller)` | `IntegrationFlow.from(source, poller)` |
| Khai báo channel | `@Bean MessageChannel` | `@Bean` hoặc DSL `.channel(...)` |
| Tạo handler | `@Bean MessageHandler` | `@Bean MessageHandler` |
| Gắn handler vào channel | `@ServiceActivator(inputChannel=...)` | `.handle(handler)` |
| Quản lý logic xử lý | Bean/`IntegrationFlow` riêng | `IntegrationFlow` dùng các bean đã inject |

Sự lựa chọn phụ thuộc tiêu chuẩn dự án. Với nhiều adapter dùng chung cấu hình client, bean thuần giúp tách rõ đối tượng kết nối và topology. Với một endpoint nhỏ, annotation giúp nhìn ngay channel của adapter.

## 6. Đăng ký bean độc lập không có nghĩa dùng chung một adapter ở mọi flow

Một adapter thường giữ **trạng thái hoặc tài nguyên**: bộ lọc file đã đọc, session SFTP, connection factory, producer Kafka hoặc rate limiter. Việc dùng cùng instance trong nhiều flow có thể tạo cạnh tranh hoặc trùng side effect.

Ví dụ một `FileReadingMessageSource` có trạng thái filter và thứ tự file. Nếu gắn **hai poller** vào cùng object source:

~~~mermaid
flowchart TD
    S["Một FileReadingMessageSource bean"]
    P1["Poller của flow A"]
    P2["Poller của flow B"]
    C1["Channel A"]
    C2["Channel B"]
    P1 --> S
    P2 --> S
    P1 --> C1
    P2 --> C2
~~~

Hai poller có thể gọi `receive()` ở những thời điểm khác nhau và cạnh tranh nhận file. Dù source có khóa nội bộ, bạn vẫn chưa thiết kế rõ file nào thuộc flow nào. Đừng xem đây là cơ chế fan-out.

Nếu cần **một lần đọc nhưng nhiều consumer**, thường nên có một inbound endpoint, sau đó dùng **`PublishSubscribeChannel`** hoặc routing có chủ đích để phân phối message. Nếu cần hai luồng độc lập, mỗi luồng nên có source/filter/trạng thái phù hợp hoặc cơ chế phân vùng rõ ràng.

Đối với outbound handler, nếu cùng `MessageHandler` được nối từ nhiều channel, cần biết handler có thread-safe không, có giữ trạng thái per-request không, và liệu việc xử lý song song có được hệ thống đích hỗ trợ không. Đặt bean singleton là cơ chế quản lý instance, không tự bảo đảm an toàn đồng thời.

## 7. Quản lý tên bean, injection và tránh đăng ký trùng

### 7.1. Đặt tên đủ rõ để quan sát

Nên phân biệt tên **source bean**, **handler bean**, **channel** và **endpoint**:

| Loại | Ví dụ | Lý do |
| --- | --- | --- |
| Source bean | `csvFileSource` | Chứa logic đọc file. |
| Inbound channel | `files.detected` | Producer gửi file đã phát hiện tới đây. |
| Flow bean | `csvValidationFlow` | Mô tả validation/routing. |
| Outbound channel | `files.toArchive` | Điểm nhận cuối trước ghi file. |
| Handler bean | `archiveWriter` | Chứa logic ghi file. |
| Endpoint | Được framework tạo từ annotation/DSL, có lifecycle riêng. | Có thể quản lý start/stop và thống kê qua cơ chế framework. |

Không nên tự tạo thêm bean tên `files.detected` bằng một nơi khác nếu đã khai báo `@Bean(name = "files.detected")`. Khi component scan và import configuration từ nhiều module, kiểm tra trùng ID hoặc đăng ký nhiều consumer không mong đợi.

### 7.2. Inject theo kiểu hoặc @Qualifier

Nếu có nhiều bean `MessageSource<File>`, injection theo kiểu có thể mơ hồ. Dùng `@Qualifier`:

~~~java
@Bean
IntegrationFlow inboundFlow(
        @Qualifier("csvFileSource")
        MessageSource<File> source) {
    return IntegrationFlow.from(
                    source,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(Duration.ofSeconds(10))))
            .channel("files.detected")
            .get();
}
~~~

Snippet chỉ dùng với phương án **bean thuần**. Nếu `csvFileSource` đã có `@InboundChannelAdapter` như mục 4 thì không thêm flow này, vì sẽ tạo endpoint polling thứ hai.

Tương tự, các handler cho HTTP, JMS, Kafka hoặc file có thể đều triển khai `MessageHandler`. Lúc nối vào DSL, inject theo tên để tránh chọn nhầm đích.

### 7.3. Không gọi @Bean factory thủ công như service

Trong class `@Configuration`, các method `@Bean` có thể được Spring proxy để trả bean singleton tùy cơ chế cấu hình. Nhưng gọi trực tiếp `csvFileSource()` từ business code hoặc khởi tạo class configuration bằng `new` khiến hành vi phụ thuộc cách cấu hình.

Với adapter độc lập, cách nhất quán là **để Spring inject bean** vào flow hoặc test. Việc đó bảo toàn lifecycle và tránh vô tình tạo thêm một instance sử dụng cùng thư mục, cùng connection hoặc cùng state.

## 8. Hợp đồng Message ở ranh giới adapter

Dù được đăng ký bằng bean hay DSL, adapter cần công bố **kiểu payload và headers** mà các consumer nhận.

| Thành phần | Ví dụ | Kiểm soát |
| --- | --- | --- |
| Payload | `File`, `byte[]`, DTO nghiệp vụ, `String`. | Transformer/handler downstream phải nhận đúng kiểu. |
| Correlation ID | `traceId` hoặc `correlationId`. | Giữ qua các bước để truy vết request và lỗi. |
| Định danh sự kiện | `eventId`, `orderId` hoặc checksum file. | Idempotency khi nguồn gửi lặp. |
| Header giao thức | Tên file, remote directory, topic/partition. | Không giả định mọi header được truyền ra hệ thống khác. |
| Reply/error | `replyChannel`, `errorChannel`. | Đường phản hồi của gateway và đường lỗi của endpoint. |
| Kết quả xử lý | Ack từ đích, mã phản hồi nghiệp vụ. | Phân biệt nhận message với hoàn tất tác vụ. |

Ví dụ, `FileReadingMessageSource` phát `Message<File>`; nó chưa parse CSV và chưa bảo đảm mỗi dòng là một event hợp lệ. Nếu handler đích muốn `OrderCommand`, thêm một bước đọc/parse/validate/transform giữa adapter nguồn và adapter đích.

Headers `replyChannel` và `errorChannel` có thể tham chiếu các đối tượng channel nội bộ. Khi gửi HTTP, JMS, AMQP hoặc Kafka, chỉ map những header an toàn, có ích và tương thích giao thức. Không đưa toàn bộ `MessageHeaders` lên wire một cách mù quáng.

### 8.1. Bean độc lập và adapter giao thức khác

Với các giao thức khác, cách tách vẫn tương tự:

- **SFTP:** tạo bean `SessionFactory` dùng cấu hình kết nối/xác thực; tạo source hoặc message handler dựa trên bean đó; gắn endpoint nhận/gửi qua DSL hoặc XML.
- **HTTP:** tái sử dụng client cấu hình timeout, converter, auth và connection pool; message handler/gateway outbound thực hiện HTTP call.
- **JMS/AMQP:** khai báo `ConnectionFactory`/template/listener infrastructure như bean; endpoint xử lý ack, transaction và listener container.
- **Kafka:** chia bean producer/consumer factory, message handler hoặc adapter; lưu ý offset, topic, partition, serialization và commit.
- **Database:** dùng `DataSource`, transaction manager, JDBC message source/handler; query cần checkpoint và chiến lược phân phối giữa instance.

Không phải mọi thành phần kết nối đều trực tiếp là `MessageSource`. Message-driven inbound endpoint có thể dựa trên listener container/callback thay vì poller. Đăng ký thành bean giúp tái sử dụng config nhưng cách kích hoạt phụ thuộc từng giao thức.

## 9. Lỗi, retry và tính toàn vẹn khi nguồn/đích tách thành bean

Một flow có thể có đủ bean và endpoint hợp lệ nhưng vẫn mất dữ liệu nếu xử lý lỗi chưa rõ.

~~~mermaid
flowchart TD
    R["Source nhận file / event"]
    S["MessageSource / listener"]
    C["Gửi vào channel"]
    H["Handler outbound"]
    A{"Hệ thống đích xác nhận?"}
    OK["Đánh dấu thành công"]
    ERR["Chính sách lỗi và phục hồi"]
    R --> S --> C --> H --> A
    A -->|"Có"| OK
    A -->|"Không / chưa rõ"| ERR
~~~

Cần phân biệt ba cột mốc:

1. **Source đã phát message**: dữ liệu được chuyển vào Spring Integration.
2. **Handler đã gửi/ghi dữ liệu**: thao tác outbound được thực hiện ở một mức nhất định.
3. **Đích đã hoàn tất nghiệp vụ**: hệ thống ngoài xác nhận theo hợp đồng.

Ví dụ, source dùng filter `AcceptOnceFileListFilter` có thể đã ghi nhận file trước khi handler ghi thư mục archive thất bại. Nếu không có cơ chế replay hoặc đánh dấu bền vững, chỉ chờ lần poll tiếp theo là chưa đủ để khôi phục. Ngược lại, handler đã gửi HTTP thành công nhưng response mất; retry có thể tạo tác dụng phụ hai lần.

Thiết kế cần lựa chọn theo từng nguồn/đích:

- **Lỗi nguồn:** cảnh báo, reconnect, backoff, điều kiện tiếp tục polling.
- **Lỗi validation:** đưa payload lỗi vào quarantine với mã và nguyên nhân rõ ràng.
- **Lỗi gửi ra ngoài:** retry có giới hạn, timeout, circuit breaker khi phù hợp.
- **Kết quả không chắc chắn:** đối soát bằng ID nghiệp vụ hoặc idempotency key tại đích.
- **Restart hoặc nhiều instance:** dùng checkpoint, lock/partition, trạng thái bền vững, unique constraint khi cần.

**Chỉ vì handler là singleton bean không có nghĩa delivery là exactly-once.** Độ tin cậy phụ thuộc hành vi của source, channel, endpoint, transaction và hệ thống đích.

### 9.1. Lỗi đồng bộ và bất đồng bộ

Với `DirectChannel`, handler thường chạy trên thread đang gửi message. Exception từ `FileWritingMessageHandler` có thể lan về endpoint inbound đang poll. Poller/error infrastructure có thể xử lý lỗi, nhưng không nên mặc định rằng file sẽ được gửi lại.

Nếu thay `files.toArchive` bằng `QueueChannel` hoặc `ExecutorChannel`, handler có thể chạy trên thread khác. Lúc đó cần poller hoặc executor consumer thích hợp và đường lỗi như `errorChannel`, `ErrorMessage`, retry advice hoặc kho dead-letter. Một queue trong bộ nhớ không bảo đảm message sống qua restart.

## 10. Bean lifecycle và quản lý kết nối

Các adapter và resource bean nằm trong Spring context. Những thành phần triển khai các interface lifecycle có thể được start/stop theo container. Endpoint polling, listener container và connection/session pool có vòng đời riêng; chúng không đồng nhất với object `MessageSource` hoặc `MessageHandler`.

Ví dụ khi vận hành:

| Sự kiện | Điều gì cần xét? |
| --- | --- |
| Ứng dụng startup | Bean source/handler đã tạo xong? Endpoint có consumer? Thư mục và credentials có hợp lệ? |
| Poller start | Tần suất đọc, `maxMessagesPerPoll`, giới hạn thread và tốc độ xử lý. |
| Đích chậm | Timeout client, backpressure, queue capacity và retry. |
| Mất kết nối SFTP/JMS/DB | Session reconnect, recovery của listener và trạng thái message chưa xác nhận. |
| Graceful shutdown | Ngừng nhận dữ liệu mới, xử lý in-flight, đóng connection, lưu checkpoint. |
| Chạy nhiều instance | Có cùng poll một record/file? Có lock/partition hoặc cơ chế claim không? |

Bean độc lập thuận tiện để inject cấu hình bên ngoài như `DataSource`, client credentials, serializer, retry policy và metric registry. Tốt nhất dành trách nhiệm kết nối cho bean client/session factory, còn flow tập trung vào **dòng message và quy tắc xử lý**.

### 10.1. Không dùng một source để tạo nhiều scheduler ngoài ý muốn

Nếu một source được khai báo `@Bean + @InboundChannelAdapter`, không bổ sung một `@Scheduled` gọi `source.receive()` hoặc một `IntegrationFlow.from(source, poller)` thứ hai mà không thiết kế rõ. Điều đó có thể tạo hai luồng lấy dữ liệu, gây cạnh tranh, đọc trùng hoặc bỏ sót.

Tương tự, khi dùng Spring Integration với JMS/Kafka listener, hãy tránh tự tạo thêm listener đọc cùng nguồn nếu muốn chỉ có một consumer logic.

## 11. Kiểm thử bean riêng và wiring endpoint

Có thể kiểm thử ở hai cấp:

1. **Unit test bean:** cấu hình source hoặc handler và kiểm tra cách nó đọc/ghi khi được gọi trực tiếp.
2. **Integration test endpoint:** khởi động Spring context, gửi message vào channel thật hoặc đặt dữ liệu ở nguồn, quan sát đầu ra sau một lần poll.

Kiểm thử cấp hai rất cần thiết để phát hiện thiếu `@InboundChannelAdapter`, sai channel name hoặc handler chưa đăng ký consumer — những lỗi unit test gọi trực tiếp handler sẽ không thấy.

### 11.1. Test flow và outbound handler qua channel

Trong ví dụ mục 4, dùng `files.detected` làm điểm bắt đầu cho test: file được đưa qua validation flow rồi đến bean ghi file; việc này kiểm tra **consumer endpoint** mà không cần chờ poller.

Đặt `AdapterBeansApplicationTest.java` trong package `demo.adapterbeans`:

~~~java
package demo.adapterbeans;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest(properties = {
        "app.inbox=./target/adapter-beans-inbox",
        "app.archive=./target/adapter-beans-archive"
})
class AdapterBeansApplicationTest {

    @Autowired
    @Qualifier("files.detected")
    MessageChannel detectedFiles;

    @Test
    void validFileGoesThroughFlowAndIndependentWriter() throws Exception {
        Path input = Files.createTempFile("adapter-bean-", ".csv");
        Path exported = Path.of("./target/adapter-beans-archive")
                .resolve(input.getFileName());

        byte[] data = "orderId,amount\nORD-1001,250000\n"
                .getBytes(StandardCharsets.UTF_8);
        try {
            Files.write(input, data);

            boolean accepted = detectedFiles.send(
                    MessageBuilder.withPayload(input.toFile()).build());

            assertTrue(accepted);
            assertTrue(Files.isRegularFile(exported));
            assertArrayEquals(data, Files.readAllBytes(exported));
        } finally {
            Files.deleteIfExists(input);
            Files.deleteIfExists(exported);
        }
    }
}
~~~

Dự án cần `spring-boot-starter-test` trong test scope. Ở đây test dùng một file tạm bên ngoài `app.inbox` để chứng minh flow và outbound endpoint được nối đúng. Cần tạo bean/source theo cấu hình ở mục 4 để Spring context khởi động; source không cần phát file mới trong chính test này. Với `DirectChannel`, handler chạy đồng bộ nên có thể kiểm tra file sau `send()`.

**Điểm giới hạn:** test này **không xác minh cơ chế polling inbound** vì nó gửi message vào channel trực tiếp. Để kiểm thử nguồn, đặt file trong thư mục inbox dành riêng cho test, chờ kết quả bằng điều kiện có timeout, rồi thử file rỗng, file không đúng pattern và restart.

### 11.2. Test bean độc lập để kiểm tra cấu hình

Có thể inject bean nguồn và gọi `receive()` trong unit/integration test riêng. Nếu source đang được một poller chạy đồng thời, không gọi `receive()` trực tiếp trên cùng bean trong test vì sẽ cạnh tranh tiêu thụ dữ liệu. Nên tạo source riêng với thư mục tạm hoặc tạm dừng endpoint khi kiểm thử trạng thái.

Với handler outbound, test kiểm tra đường dẫn đích, tên file, chính sách tồn tại file, quyền ghi và xử lý lỗi. Khi chuyển sang SFTP, JMS, HTTP hoặc Kafka, cần thêm test về timeout, reconnect, ack/offset, duplicate và khởi động lại.

## 12. So sánh với XML namespace và annotation trên service method

Cùng một mô hình có thể được diễn đạt bằng nhiều cách mà không thay đổi hợp đồng message.

| Hình thức | Bean adapter ở đâu? | Endpoint ở đâu? |
| --- | --- | --- |
| `@Bean + @InboundChannelAdapter` | Method `@Bean` trả `MessageSource`. | Annotation tạo endpoint polling. |
| `@Bean + @ServiceActivator` | Method `@Bean` trả `MessageHandler`. | Annotation tạo consumer endpoint. |
| `@Bean` + Java DSL | Bean nguồn/handler được tạo riêng. | `IntegrationFlow.from(...)` và `.handle(...)` tạo endpoint. |
| XML namespace | Có thể khai báo source, handler và client bằng `<bean>`. | Các tag `<int:...>` hoặc namespace adapter nối endpoint và channel. |
| `@Component` + method `@ServiceActivator` | Bean là service Java. | Annotation trên method tạo endpoint handler. |

Nếu đổi từ XML sang Java DSL, hãy giữ thống nhất kiểu payload, tên channel, header contract, retry và ý nghĩa thành công. Không nhập cùng XML rồi thêm DSL mới cho **cùng endpoint** trước khi quyết định cách chuyển đổi, vì có thể làm application tạo hai consumer hoặc hai poller.

Khi đăng ký adapter như một bean độc lập, ưu tiên **constructor injection**, cấu hình tập trung và test có ranh giới rõ. Adapter chuyên dụng xử lý chi tiết giao thức; flow thể hiện luồng dữ liệu và chính sách nghiệp vụ.

## 13. Lỗi thiết kế hay gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Tạo `MessageSource` bean nhưng không thấy message. | Chưa có polling endpoint dùng bean đó. | Thêm `@InboundChannelAdapter` hoặc `IntegrationFlow.from(source, poller)`. |
| Tạo `MessageHandler` nhưng không có outbound. | Chưa có consumer endpoint gắn handler với channel. | Dùng `@ServiceActivator(inputChannel=...)` hoặc DSL `.handle(handler)`. |
| Cùng file được đọc hai lần bởi hai flow. | Cùng source có nhiều poller hoặc có hai adapter đọc chung thư mục. | Một inbound endpoint rồi route/fan-out, hoặc partition nguồn rõ ràng. |
| Message không đến được handler. | Sai tên channel, endpoint dừng, không có subscriber. | So khớp channel ID và lifecycle, kiểm tra wiring bằng integration test. |
| Hai handler trên một `DirectChannel` nhưng chỉ một được gọi. | `DirectChannel` là point-to-point, không tự multicast. | Dùng publish–subscribe nếu cần phát cho nhiều consumer. |
| Spring không biết inject handler nào. | Nhiều bean cùng kiểu `MessageHandler`. | Dùng `@Qualifier` hoặc injection theo tên rõ ràng. |
| Nhiều object client cùng kết nối một đích. | Tạo bằng `new` ngoài container hoặc config trùng. | Dùng bean được Spring quản lý và injection. |
| Poller tiếp tục nhưng message lỗi không được retry. | Source đã đánh dấu đã đọc; không có replay/checkpoint. | Thiết kế trạng thái nguồn và retry ở đúng tầng. |
| Ứng dụng mất message sau restart. | Queue và filter chỉ lưu trong RAM. | Kho bền vững, idempotency, ack/transaction đúng. |
| Method gateway timeout khi outbound đã xử lý xong. | Reply bị mất hoặc handler one-way không trả kết quả. | Phân biệt one-way/request–reply và đường phản hồi. |
| Ghi vào hệ thống ngoài bị duplicate. | Retry sau kết quả không rõ, không có khóa idempotent. | Dùng idempotency key/unique constraint và đối soát. |
| Test gọi handler trực tiếp pass nhưng flow không chạy. | Chưa kiểm thử Spring context và channel thật. | Thêm integration test qua endpoint/channel. |

## 14. Bài tập: tách adapter SFTP và database thành bean riêng

Giả sử hệ thống nhận file CSV qua SFTP, chuẩn hóa từng dòng thành `Invoice` rồi lưu vào database. Hãy thiết kế theo hướng:

1. Bean quản lý kết nối SFTP/session factory có cấu hình endpoint, bảo mật host key, timeout và reconnect.
2. Bean đồng bộ/nhận file từ SFTP, gắn **một inbound endpoint** với poller.
3. Channel `invoices.raw` nhận file hoặc message nguồn; transformation và validation tạo `Invoice`.
4. Bean ghi database dùng `DataSource` và transaction manager; consumer endpoint nhận `Invoice` qua `invoices.valid`.
5. File không parse được chuyển quarantine, không bị xử lý lặp không kiểm soát.
6. Với retry database, idempotency key theo mã hóa đơn, đảm bảo ghi hai lần không sinh hai bản ghi.
7. Cấu hình hai instance: đề xuất lock/partition hoặc claim record để không cùng xử lý một file.
8. Viết test chứng minh thiếu endpoint khiến bean tồn tại nhưng flow không tự chạy; sau đó xác minh wiring đúng khi endpoint được đăng ký.

**Tiêu chí đạt:** người học chỉ ra rõ bean nào giữ kết nối, bean nào đọc/ghi, endpoint nào kích hoạt, channel nào chuyển message, điểm nào bắt đầu/hoàn tất transaction và khi lỗi có thể replay từ đâu.

## 15. Câu hỏi tự kiểm tra

1. Vì sao `@Bean MessageSource<File>` không tự quét thư mục?
2. Method `@Bean` và method `MessageSource.receive()` được gọi ở những thời điểm nào?
3. `@ServiceActivator` có tác dụng gì khi gắn với một bean `MessageHandler`?
4. Vì sao nên inject một bean adapter vào Java DSL thay vì gọi factory bằng `new`?
5. Có thể vừa dùng `@InboundChannelAdapter` vừa dùng `IntegrationFlow.from(source, poller)` trên cùng source không? Rủi ro là gì?
6. Nếu muốn một message đi đến hai handler, `DirectChannel` có đáp ứng multicast không?
7. Một filter chỉ lưu file đã đọc trong bộ nhớ có chặn duplicate sau restart không?
8. Bean singleton có bảo đảm handler an toàn khi được gọi từ nhiều thread không?
9. `MessageChannel.send()` thành công chứng minh được điều gì, và chưa chứng minh được điều gì?
10. Vì sao unit test trực tiếp handler chưa đủ để xác nhận integration flow đã được đăng ký?

**Gợi ý:** bean là đối tượng do Spring quản lý, còn endpoint tạo cơ chế nhận/gửi message. Source cần poller/listener, handler cần channel subscriber. Độ tin cậy đòi hỏi thiết kế thêm trạng thái bền vững, retry, idempotency và xác nhận ở đích.

## 16. Ghi nhớ

**Đăng ký adapter như một bean độc lập** giúp tách đối tượng đọc/ghi dữ liệu khỏi cấu hình tuyến message. Với Spring Integration, hãy nhận diện rõ: **`MessageSource` hoặc `MessageHandler` là bean thực hiện chức năng; inbound/outbound endpoint là nơi kết nối chúng với poller/channel; `IntegrationFlow` thể hiện các bước xử lý**.

Mô hình này áp dụng cho file, SFTP, HTTP, JMS, AMQP, Kafka và database dù từng giao thức có cách tạo client, listener hoặc ack khác nhau. Khi thiết kế, ưu tiên bean được Spring quản lý, tên channel nhất quán, chỉ một đường kích hoạt cho mỗi trách nhiệm, contract payload/headers rõ ràng và kiểm thử cả wiring lẫn hành vi khi lỗi. Đó là cơ sở để kết nối nhiều hệ thống có thể vận hành và khôi phục ổn định.

