# MessageCollector nhận message trong test của Spring Integration Runtime

## Mục tiêu và một phân biệt quan trọng về API

Trong **SPRING_INTEGRATION_RUNTIME**, một IntegrationFlow có thể nhận message từ channel, xử lý bằng transformer, service activator, poller hoặc executor rồi gửi tiếp tới một output channel. Khi kiểm thử, câu hỏi cơ bản là: **message nào đã đến đầu ra, với payload/header nào, theo thứ tự nào, và trong khoảng thời gian bao lâu?**

**MessageCollector** thường được nhắc đến trong ví dụ kiểm thử message flow vì nó **thu thập message đã phát ra để test lấy ra và assert**. Tuy nhiên cần xác định đúng thư viện:

> **MessageCollector với API forChannel(...) thuộc test support binder đời cũ của Spring Cloud Stream**, cụ thể là **org.springframework.cloud.stream.test.binder.MessageCollector**, không phải một bean/API mặc định được cung cấp bởi **spring-integration-test** hiện đại. Spring Cloud Stream đã chuyển sang test binder với **InputDestination/OutputDestination**; một ứng dụng **Spring Integration thuần** thường kiểm tra output bằng **QueueChannel, WireTap hoặc mock MessageHandler**.

Ba cách tiếp cận đều cùng mục đích **quan sát message sau flow**, nhưng có ranh giới framework và dependency khác nhau. Bài này trình bày đầy đủ **MessageCollector legacy** đúng ngữ cảnh, sau đó hướng dẫn triển khai hành vi tương đương cho các runtime Spring Integration hiện đại.

Kết thúc bài, bạn có thể:

- Giải thích cách **MessageCollector.forChannel(MessageChannel)** trả về một queue để lấy message trong test legacy.
- Dùng **poll(timeout, unit)** để tránh test giả thất bại khi xử lý bất đồng bộ.
- Assert payload, headers, correlation, số lượng, duplicate và thứ tự có/không được bảo đảm.
- Biết khi nào cần **QueueChannel** trong Spring Integration và **OutputDestination** trong Spring Cloud Stream.
- Thu thập message từ một **DirectChannel đang có business consumer** mà không vô tình cướp message bằng cách chọn **WireTap** đúng.
- Điều khiển poller, executor, errorChannel, retry, message store và lifecycle trong test để giảm flaky test.
- Phân biệt test trong JVM với kiểm thử broker thật, transaction, persistence và restart.

## 1. Vị trí của collector trong một message flow

Ví dụ nghiệp vụ đơn giản: nhận OrderSubmitted, chuẩn hóa dữ liệu, gửi OrderAccepted hoặc ErrorMessage.

~~~mermaid
flowchart LR
    T["JUnit test"] --> I["inputChannel"]
    I --> F["IntegrationFlow<br/>transformer / handler"]
    F --> O["outputChannel"]
    O --> C["Message collector<br/>test sink"]
    C --> A["Assertion<br/>payload, headers, count"]
    F -. "exception" .-> E["errorChannel"]
    E --> CE["Error collector"]
~~~

Một bài test tối thiểu sẽ thực hiện:

1. **Arrange:** tạo application context, channel/flow, nguồn input và vị trí ghi nhận output.
2. **Act:** gửi một message có payload/header xác định.
3. **Await:** nhận message đầu ra từ queue bằng timeout hữu hạn.
4. **Assert:** kiểm tra message có tồn tại, payload đúng và correlation/header được bảo toàn theo hợp đồng.
5. **Cleanup:** dọn queue hoặc cách ly context, reset mocks và dừng endpoint sinh message tự động.

### Vì sao không chỉ assert send() trả true?

~~~java
boolean sent = input.send(message);
assertTrue(sent);
~~~

Lệnh này chủ yếu xác minh **channel chấp nhận việc gửi**. Nếu sau đó flow đi qua **ExecutorChannel** hoặc QueueChannel với polling consumer, xử lý nghiệp vụ có thể **chưa hoàn thành** khi send() trả về. Ngay cả ở DirectChannel, test cần kiểm tra **message đầu ra và side effect** thay vì chỉ kiểm tra kết quả dispatch.

### Ba cơ chế nên phân biệt

| Thành phần | Thuộc hệ sinh thái nào? | Dùng để làm gì? |
| --- | --- | --- |
| **MessageCollector** + TestSupportBinder | **Spring Cloud Stream legacy test-support** | Thu các message outbound trên binding/channel để test lấy bằng BlockingQueue |
| **OutputDestination / InputDestination** | **Spring Cloud Stream test binder hiện đại** | Nhận/gửi message ở ranh giới **binding/destination** giả lập bằng in-JVM binder |
| **QueueChannel, WireTap, MockIntegrationContext, MockMessageHandler** | **Spring Integration / spring-integration-test** | Quan sát và điều khiển message ở channel/endpoint trong IntegrationFlow |

Không nên autowire **MessageCollector** trong một project chỉ thêm **spring-integration-test** rồi kỳ vọng Spring tự tạo bean này. Nếu không có **legacy Spring Cloud Stream test-support**, bean/class có thể không tồn tại; hướng đúng cho flow thuần Spring Integration là dùng các công cụ của chính Spring Integration.

## 2. MessageCollector legacy hoạt động như thế nào?

Trong những thế hệ Spring Cloud Stream dùng **@EnableBinding**, **Processor**, **Source** và **Sink**, module **spring-cloud-stream-test-support** cung cấp **TestSupportBinder**. Test binder này thay thế binder thật trong test context theo auto-configuration phù hợp.

Đối với output binding, test support ghi nhận các message được phát vào một **MessageCollector**. Test gọi:

~~~java
BlockingQueue<Message<?>> captured =
        messageCollector.forChannel(processor.output());
~~~

Sau đó lấy message:

~~~java
Message<?> received = captured.poll(5, TimeUnit.SECONDS);
assertNotNull(received);
~~~

### Các thành phần của API

| Đoạn code | Ý nghĩa |
| --- | --- |
| **messageCollector** | Bean kiểu org.springframework.cloud.stream.test.binder.MessageCollector từ **test-support legacy** |
| **forChannel(processor.output())** | Lấy queue chứa message thu thập từ **output binding channel** chỉ định |
| **BlockingQueue<Message<?>>** | Hàng đợi thread-safe để test lấy message đã thu |
| **poll()** | Lấy ngay một message nếu đã có; nếu rỗng trả null |
| **poll(timeout, unit)** | Đợi tối đa timeout; trả message hoặc null; có thể ném InterruptedException |
| **take()** | Đợi cho tới khi có message; thường **không nên** dùng trong test vì có thể treo vô hạn |

**Collector giữ message để test quan sát, không phải broker production.** Nó không mô phỏng đầy đủ durability, ack, offset commit, rebalance, broker ordering, network partition hay crash recovery.

### Vì sao test nên dùng poll có timeout?

Giả sử một handler chạy trên executor và mất 150 ms để phát kết quả:

~~~text
T0       Test gửi input.
T0+1ms   Test gọi queue.poll() ngay → null.
T0+150ms Worker đưa output vào collector.
~~~

Test có thể thất bại dù flow chạy đúng, vì **poll() không chờ**. Dùng **poll(5, TimeUnit.SECONDS)** giảm race bằng cách chờ một khoảng hợp lý. **Timeout là hạn chót của assertion**, không phải cấu hình deadline của message flow.

## 3. Dependency và điều kiện áp dụng trong dự án legacy

Ví dụ Gradle cho dự án **Spring Cloud Stream thế hệ cũ**:

~~~groovy
dependencies {
    // Version được quản lý bởi Spring Cloud BOM tương thích với project.
    testImplementation 'org.springframework.cloud:spring-cloud-stream-test-support'
}
~~~

Hoặc Maven:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-support</artifactId>
    <scope>test</scope>
</dependency>
~~~

**Không dùng đoạn dependency này như khuyến nghị cho project Spring Cloud Stream mới.** Đây là phần giải thích/duy trì codebase legacy. Các phiên bản Spring Cloud Stream hiện đại sử dụng **spring-cloud-stream-test-binder** và các API khác; ví dụ mới sẽ có ở phần sau.

Trước khi chạy test:

- Xác nhận dependency và version tương thích của **Spring Boot, Spring Cloud Stream và Spring Integration**.
- Xác nhận project thực sự dùng **legacy binding model** như @EnableBinding, Processor.
- Xác nhận TestSupportBinder đang được bật trong test context.
- Không trộn **legacy test support binder** và **test binder mới** trong cùng một test mà chưa có kế hoạch rõ ràng; auto-configuration có thể cạnh tranh với binder thật.
- Đặt dependency **test scope**, không kéo test binder vào production runtime.

## 4. Ví dụ JUnit với MessageCollector nhận message

Ví dụ dưới đây là **mẫu legacy**, dựa trên API của Spring Cloud Stream đời cũ, không phải code mẫu cho Spring Integration 6/7 hoặc Spring Cloud Stream functional model hiện đại.

~~~java
import static org.junit.Assert.*;

import java.util.Locale;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.annotation.EnableBinding;
import org.springframework.cloud.stream.messaging.Processor;
import org.springframework.cloud.stream.test.binder.MessageCollector;
import org.springframework.integration.annotation.Transformer;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;
import org.springframework.test.context.junit4.SpringRunner;

@RunWith(SpringRunner.class)
@SpringBootTest(classes = LegacyCollectorTest.App.class)
public class LegacyCollectorTest {

    @Autowired
    private Processor processor;

    @Autowired
    private MessageCollector messageCollector;

    @Test
    public void receivesTheTransformedOutput() throws Exception {
        BlockingQueue<Message<?>> captured =
                messageCollector.forChannel(processor.output());

        processor.input().send(new GenericMessage<>("hello"));

        Message<?> result = captured.poll(5, TimeUnit.SECONDS);
        assertNotNull("Expected a message within 5 seconds", result);
        assertEquals("HELLO", result.getPayload());
    }

    @SpringBootApplication
    @EnableBinding(Processor.class)
    public static class App {
        @Transformer(inputChannel = Processor.INPUT,
                     outputChannel = Processor.OUTPUT)
        public String uppercase(String value) {
            return value.toUpperCase(Locale.ROOT);
        }
    }
}
~~~

Điểm cần đọc kỹ:

1. **@EnableBinding(Processor.class)** tạo input/output binding theo mô hình annotation cũ.
2. **@Transformer** là Spring Integration endpoint làm thay đổi payload, nhưng collector là **test support của Spring Cloud Stream**, không phải API của @Transformer.
3. **messageCollector.forChannel(processor.output())** lấy queue nhận output tương ứng với binding channel đã định nghĩa.
4. **processor.input().send(...)** kích hoạt processing; test lấy message với timeout hữu hạn.
5. Test kiểm tra **payload đã transform**; khi nghiệp vụ cần correlation/header, phải assert riêng.
6. Test binder dùng trong JVM nên **không chứng minh broker thật** xử lý ack/redelivery/persistence giống production.
7. Nếu dùng nhiều test với context chung, queue có thể còn message từ test trước. Cần dọn hàng đợi hoặc cô lập context.

### Thêm assertion cho header

Một message có payload đúng vẫn có thể bị mất correlation:

~~~java
import org.springframework.messaging.support.MessageBuilder;

Message<String> input = MessageBuilder.withPayload("hello")
        .setHeader("requestId", "request-42")
        .setHeader("correlationId", "flow-42")
        .build();

processor.input().send(input);
Message<?> output = captured.poll(5, TimeUnit.SECONDS);
assertNotNull(output);
assertEquals("HELLO", output.getPayload());
assertEquals("request-42", output.getHeaders().get("requestId"));
~~~

Đây là **fragment dùng cùng fixture/queue trong test được tổ chức riêng**. Kết quả có giữ header nào còn phụ thuộc transformer, binder, mapping và cấu hình flow; vì vậy assertion phải theo **hợp đồng thực tế**. Một header bị loại bởi adapter không thể tự được collector tái tạo.

## 5. Thu nhiều message: thứ tự, số lượng và dữ liệu chưa đến

Với nhiều message được gửi vào cùng output binding:

~~~java
BlockingQueue<Message<?>> captured =
        messageCollector.forChannel(processor.output());

processor.input().send(new GenericMessage<>("a"));
processor.input().send(new GenericMessage<>("b"));
processor.input().send(new GenericMessage<>("c"));

Message<?> one = captured.poll(5, TimeUnit.SECONDS);
Message<?> two = captured.poll(5, TimeUnit.SECONDS);
Message<?> three = captured.poll(5, TimeUnit.SECONDS);

assertNotNull(one);
assertNotNull(two);
assertNotNull(three);
~~~

**Đừng mặc định assert thứ tự A–B–C trong mọi topology.** Nếu upstream là executor nhiều thread, broker nhiều partition hoặc router có xử lý song song, kết quả có thể đến **C–A–B** mà vẫn đúng nghiệp vụ.

### Trường hợp cần kiểm tra không mất message

Lấy đủ N message với **N lần poll có deadline**. Sau đó:

- Kiểm tra **tập business IDs**, không chỉ số lượng.
- Kiểm tra **không có duplicate eventId** nếu đó là hợp đồng.
- Chỉ assert **thứ tự** khi topology/protocol thực sự có ordering guarantee.
- Kiểm tra kết quả unexpected từ test trước hoặc flow khác không lẫn vào queue.

### Không có output là một assertion khác

~~~java
Message<?> unexpected = captured.poll(300, TimeUnit.MILLISECONDS);
assertNull("Must not emit output before all parts arrive", unexpected);
~~~

Điều này chỉ chứng minh **không có message trong cửa sổ quan sát 300 ms**, không chứng minh message **sẽ không bao giờ** được phát. Với aggregator timeout, cần test cơ chế timeout theo thời gian riêng. Với case kiểm thử “message không đủ điều kiện”, thường nên kiểm tra cả **state MessageGroupStore** và event timeout/discard khi tới hạn.

## 6. Với Spring Integration thuần: QueueChannel là một collector đơn giản

Nếu ứng dụng chỉ dùng **Spring Integration Java DSL/XML**, cách dễ kiểm soát nhất là đặt một **QueueChannel** làm output riêng của flow test:

~~~mermaid
flowchart LR
    J["JUnit 5 test"] --> I["input<br/>DirectChannel"]
    I --> T["Transformer"]
    T --> Q["results<br/>QueueChannel"]
    Q --> A["results.receive(timeout)<br/>Assertions"]
~~~

**QueueChannel** triển khai **PollableChannel**, cung cấp **receive(timeoutMillis)**. Nó là một channel thật của Spring Integration, không cần legacy MessageCollector.

### Cấu hình Spring Integration Java DSL

~~~java
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class UppercaseFlowConfig {

    @Bean
    MessageChannel input() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel results() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow uppercaseFlow() {
        return IntegrationFlow.from("input")
                .<String, String>transform(
                        value -> value.toUpperCase(Locale.ROOT))
                .channel("results")
                .get();
    }
}
~~~

**Giải thích:** Trong ví dụ này, results là **output endpoint** được thiết kế cho test. Một hệ thống production đang cần gửi message sang consumer khác không nên **tùy tiện thay channel của production** chỉ để test, vì như vậy có thể thay đổi topology. Hãy dùng test-only configuration hoặc WireTap thích hợp nếu cần quan sát một channel vốn đã có consumer.

### JUnit 5 đọc trực tiếp message từ output

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = UppercaseFlowConfig.class)
class UppercaseFlowTest {

    @Autowired
    @Qualifier("input")
    MessageChannel input;

    @Autowired
    @Qualifier("results")
    QueueChannel results;

    @Test
    void collectsAResponse() {
        Message<String> request =
                MessageBuilder.withPayload("hello")
                        .setHeader("requestId", "R-42")
                        .build();

        assertTrue(input.send(request));

        Message<?> received = results.receive(2_000);
        assertNotNull(received);
        assertEquals("HELLO", received.getPayload());
        assertEquals("R-42", received.getHeaders().get("requestId"));
        assertNull(results.receive(0), "No extra message expected");
    }
}
~~~

Ưu điểm của test này:

- **Không cần broker** và không cần Spring Cloud Stream.
- Tạo/khởi chạy **IntegrationFlow thật**, không gọi riêng method transformer.
- **receive(2_000)** tránh race khi test triển khai thêm xử lý async.
- Có thể kiểm tra message đầy đủ, gồm headers.
- Chỉ làm việc với một **test channel rõ tên** nên ít gây tác dụng phụ lên các subscriber khác.

Giới hạn: Đây là test **trong JVM** với QueueChannel in-memory. Nó chưa xác minh **transaction rollback, broker ack, Kafka partition ordering, Redis/JDBC MessageStore durability hay restart**.

### QueueChannel.receive(...) khác BlockingQueue.poll(...) thế nào?

| MessageCollector legacy | QueueChannel thuần Spring Integration |
| --- | --- |
| collector.forChannel(outputBinding) | autowire bean QueueChannel output test |
| BlockingQueue<Message<?>> | PollableChannel/QueueChannel |
| queue.poll(5, TimeUnit.SECONDS) | results.receive(5_000) |
| Queue lưu message do legacy TestSupportBinder thu | Channel trực tiếp giữ message trong flow |
| Kích hoạt qua Processor.input() | Kích hoạt qua MessageChannel.send() |
| Thuộc Spring Cloud Stream test-support cũ | Thuộc Spring Integration core |

Lưu ý **receive() tiêu thụ message**. Một lần receive thành công làm message được lấy khỏi QueueChannel; nếu hai test cùng nhận từ một channel, chúng có thể giành nhau message. Không dùng cùng QueueChannel vừa làm queue nghiệp vụ vừa làm test observer nếu điều đó thay đổi luồng xử lý thực.

## 7. Test output đang có consumer: vì sao nên dùng WireTap?

Không phải lúc nào output cũng là QueueChannel mà test được phép lấy message. Ví dụ:

~~~text
Input
  → Handler A
  → DirectChannel businessOutput
  → Handler B (ghi DB)
~~~

Nếu test đăng ký thêm một **MessageHandler** vào **DirectChannel businessOutput** rồi kỳ vọng **cả test lẫn Handler B đều nhận mọi message**, đó có thể là một sai lầm. DirectChannel thông thường dùng dispatcher để **chọn một subscriber xử lý mỗi lần send** (có thể cân bằng tải); nó **không mặc nhiên broadcast** cho tất cả subscriber.

### Dùng WireTap để chụp bản sao tại một điểm đã định nghĩa

~~~mermaid
flowchart LR
    A["Producer"] --> D["businessOutput<br/>DirectChannel"]
    D --> B["Business handler"]
    D -. "WireTap copy" .-> Q["captured<br/>QueueChannel"]
    Q --> T["Test assertions"]
~~~

**WireTap** quan sát message đi qua channel mà không biến collector thành một business subscriber cạnh tranh trên DirectChannel. Điều này hữu ích khi muốn kiểm thử một **điểm bên trong flow** trước khi handler cuối tạo side effect.

Một cách minh họa ở Java DSL:

~~~java
@Bean
QueueChannel captured() {
    return new QueueChannel();
}

@Bean
IntegrationFlow observedFlow() {
    return IntegrationFlow.from("input")
            .<String, String>transform(String::toUpperCase)
            .wireTap("captured")
            .channel("businessOutput")
            .get();
}
~~~

Đoạn này là **mảnh cấu hình**, cần có input, businessOutput và các bean liên quan trong context. Trong test, gọi **captured.receive(timeout)** để quan sát bản sao; **businessOutput** tiếp tục gửi cho consumer nghiệp vụ của nó.

### Những ranh giới của WireTap cần nhớ

- WireTap quan sát message tại **vị trí nó được gắn**, không tự thu tất cả message ở mọi channel.
- Bản sao thường là **cùng một Message hoặc Message mới chứa payload/header tương ứng** theo cách framework triển khai; nếu payload là **object mutable**, một consumer sửa object sau đó có thể làm assertion không ổn định. Nên dùng immutable payload hoặc snapshot có kiểm soát.
- Nếu tap gửi tới channel không sẵn sàng, cần kiểm tra cách xử lý lỗi/capacity để nó không làm test hoặc flow production bị ảnh hưởng ngoài ý muốn.
- WireTap trong cấu hình test nên được gỡ bỏ sau test hoặc chỉ tồn tại trong test profile, không để queue capture tích tụ không giới hạn trong production.
- Nếu downstream phát thêm output sau tap, collector tại tap **không đại diện cho kết quả cuối cùng**.

Với **PublishSubscribeChannel**, các subscriber có thể nhận broadcast theo cơ chế của nó, nhưng phải hiểu error handling, threading và các subscriber hiện có. Không tự thay DirectChannel bằng PublishSubscribeChannel trong production chỉ để làm test nếu điều đó thay đổi ngữ nghĩa xử lý.

## 8. Spring Cloud Stream hiện đại: OutputDestination thay cho MessageCollector

Nếu project sử dụng **Spring Cloud Stream functional model**, hãy dùng test binder hiện đại:

~~~groovy
dependencies {
    testImplementation 'org.springframework.cloud:spring-cloud-stream-test-binder'
}
~~~

Các lớp thường dùng thuộc package:

~~~java
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.cloud.stream.binder.test.TestChannelBinderConfiguration;
~~~

Ví dụ ứng dụng tối giản với một function:

~~~java
import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.stream.binder.test.TestChannelBinderConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(TestChannelBinderConfiguration.class)
class StreamFunctionApp {

    @Bean
    Function<String, String> uppercase() {
        return input -> input.toUpperCase(Locale.ROOT);
    }
}
~~~

JUnit 5 dùng test binder:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;

@SpringBootTest(classes = StreamFunctionApp.class)
class StreamBinderOutputTest {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void readsOutboundMessageFromTestBinder() {
        input.send(new GenericMessage<>(
                "hello".getBytes(StandardCharsets.UTF_8)),
                "uppercase-in-0");

        Message<byte[]> received =
                output.receive(5_000, "uppercase-out-0");

        assertNotNull(received);
        assertEquals("HELLO", new String(
                received.getPayload(), StandardCharsets.UTF_8));
    }
}
~~~

**Chú ý phiên bản:** Một số thế hệ Spring Cloud Stream dùng **@Import(TestChannelBinderConfiguration.class)** như ví dụ này; tài liệu của những phiên bản mới còn dùng **@EnableTestBinder**. Chọn **một cách tương thích với phiên bản và BOM hiện tại**, không sao chép tùy ý cả hai hay trộn với legacy **spring-cloud-stream-test-support**.

### Khác biệt quan trọng khi chuyển từ collector sang OutputDestination

~~~text
Legacy:
  MessageCollector.forChannel(channels.output())
  → BlockingQueue<Message<?>>

Modern:
  OutputDestination.receive(timeout, "uppercase-out-0")
  → Message<byte[]> hoặc null
~~~

- **MessageCollector** nhắm trực tiếp **output channel của binding legacy**.
- **OutputDestination** nhận theo **binding/destination** của test binder mới, thường có tên dạng **functionName-out-0** hoặc tên được cấu hình rõ.
- Payload của OutputDestination có thể ở dạng **byte[] sau conversion**, vì vậy phải decode theo **content type/encoding** phù hợp.
- Nếu có nhiều output destinations, hãy truyền tên destination/binding chính xác; không mặc định chỉ tồn tại một queue output.
- Test binder mới vẫn là **in-JVM test binder**, không chứng minh các semantics đặc thù của Kafka/Rabbit thật.

### Chuyển đổi API khi nâng cấp

| Legacy Spring Cloud Stream | Functional Spring Cloud Stream |
| --- | --- |
| @EnableBinding(Processor.class) | @Bean Function/Consumer/Supplier và function definition |
| Processor.input()/output() | Binding/destination của function |
| spring-cloud-stream-test-support | spring-cloud-stream-test-binder |
| MessageCollector.forChannel(...) | OutputDestination.receive(...) |
| TestSupportBinder | Spring Integration-based test binder |
| @RunWith(SpringRunner.class), JUnit 4 thường gặp | JUnit 5, @SpringBootTest thường gặp |

**Không chỉ đổi import.** Bản chất binding model, function name, content-type conversion và cách test binder mô phỏng transport đều khác. Sau migration, cần xác minh headers, serialization và destination mapping thay vì chỉ assert một payload String.

## 9. Test header, correlation và batch message

Một message gồm **payload + headers**. Kiểm thử flow chỉ dựa vào payload có thể bỏ sót các lỗi runtime nghiêm trọng:

- Mất **correlationId** sau transformer/gateway.
- Mất **requestId** hoặc **idempotencyKey**, khiến retry/redelivery tạo side effect trùng.
- Mất **sequenceNumber/sequenceSize** của splitter, khiến aggregator không release.
- Content type sai, khiến downstream converter giải mã nhầm.
- Header mới chứa object không serialize được trong persistent MessageStore.

Ví dụ assertion tổng quát:

~~~java
Message<?> captured = results.receive(5_000);
assertNotNull(captured);

assertEquals("O-42", captured.getHeaders().get("orderId"));
assertEquals("batch-7", captured.getHeaders().get("correlationId"));
assertEquals("ev-1001", captured.getHeaders().get("eventId"));
~~~

**Ví dụ này là fragment**, chỉ hợp lệ nếu flow được cấu hình để truyền đúng các header trên. Không mặc định mọi biến business sẽ được Spring Integration tự tạo.

### Khi nhiều message đến lệch thứ tự

Giả sử ba nhánh gửi PaymentResult, InventoryResult, AddressResult. Với ExecutorChannel, thứ tự nhận có thể khác nhau:

~~~text
Input sequence:  PAYMENT → INVENTORY → ADDRESS
Output observed: ADDRESS → PAYMENT → INVENTORY
~~~

Nếu hợp đồng chỉ yêu cầu đủ ba loại kết quả, test nên:

1. Lấy đúng **3 message** bằng các lần poll có timeout.
2. Chuyển payload sang một tập/map theo business key.
3. Kiểm tra mỗi loại chỉ xuất hiện một lần, cùng orderId/runId.
4. Không assert theo vị trí index cố định.

Nếu hợp đồng yêu cầu thứ tự tuyệt đối, cần có một **resequencer/sequence strategy** hoặc guarantee của transport phù hợp; assertion phải nêu rõ điều kiện đó. Queue test thu được một thứ tự quan sát, nhưng không tự chứng minh source đảm bảo ordering trong cluster.

## 10. Thu ErrorMessage: errorChannel khác outputChannel

Một flow có thể không phát output bình thường nếu handler ném exception:

~~~mermaid
flowchart LR
    I["Input"] --> H["ServiceActivator"]
    H -- "Success" --> O["outputChannel"]
    H -. "Failure" .-> E["errorChannel"]
    E --> R["Error handler / test collector"]
~~~

**Spring Integration có ErrorMessage**, với payload là Throwable; một MessagingException có thể giữ failedMessage. Khi kiểm thử phải xác định **lỗi được publish qua errorChannel** hay **truyền ngược về thread gửi**.

### Lỗi đồng bộ qua DirectChannel

Nếu test gửi vào **DirectChannel** và một handler đồng bộ ném RuntimeException, lời gọi send() có thể ném exception ở **thread test**:

~~~java
assertThrows(RuntimeException.class,
        () -> input.send(badMessage));
~~~

Đây là fragment test; loại exception cụ thể có thể bị Spring Integration bọc thành MessagingException. Không nên mặc định sẽ có ErrorMessage ở global errorChannel nếu endpoint không phát error theo cơ chế tương ứng.

### Lỗi trong ExecutorChannel hoặc polling consumer

Khi lỗi xuất hiện trên worker/poller thread, người gửi ban đầu có thể đã hoàn tất send(). Nếu error flow được cấu hình, test có thể định tuyến ErrorMessage tới một QueueChannel chuyên kiểm thử:

~~~java
@Bean
QueueChannel testErrors() {
    return new QueueChannel();
}
~~~

Phải **wiring endpoint error handler/route** để ErrorMessage thực sự được đưa vào channel testErrors. Sau đó:

~~~java
Message<?> error = testErrors.receive(5_000);
assertNotNull(error);
assertTrue(error instanceof
        org.springframework.messaging.support.ErrorMessage);

Throwable failure =
        ((org.springframework.messaging.support.ErrorMessage) error)
                .getPayload();
assertNotNull(failure);
~~~

Chỉ khai báo QueueChannel không khiến mọi exception của ứng dụng tự chạy vào nó. Nếu RetryAdvice recovery callback bắt lỗi rồi trả về thành công, đường error cũng có thể khác kỳ vọng.

**Correlation trong error path:** Khi ErrorMessage được tạo, xem originalMessage hoặc MessagingException.failedMessage nếu có. Không giả định ErrorMessage headers luôn chứa requestId/eventId của message gốc; lỗi xảy ra trước khi MessageSource nhận message cũng có thể thiếu failedMessage.

## 11. Kiểm soát poller để MessageCollector nhận đúng message

Một poller không được kiểm soát có thể chạy **trước khi test bắt đầu**, phát nhiều message hơn dự kiến, hoặc chưa kịp poll lần nào trước khi test lấy output.

~~~text
TaskScheduler
  → Poller
      → MessageSource.receive()
      → Channel
      → Handler
      → Output collector
~~~

Spring Integration Test Framework có công cụ hỗ trợ:

- **@SpringIntegrationTest(noAutoStartup = {...})**: ngăn các endpoint khởi động tự động theo pattern tên bean/endpoint.
- **MockIntegrationContext**: thay MessageSource hoặc MessageHandler trong endpoint đang được test, rồi reset sau mỗi test.
- **MockIntegration.mockMessageSource(...)**: tạo nguồn message có dữ liệu cố định.
- **MockMessageHandler** và Mockito ArgumentCaptor: kiểm tra message được giao tới handler thay vì chạy side effect thật.
- **OnlyOnceTrigger**: phục vụ một số test cần poll chính xác một lần.

Đây là các tiện ích của **spring-integration-test**, **không** phải MessageCollector legacy. Chúng phối hợp được với QueueChannel test nhưng cần ID endpoint chính xác và cấu hình test context thích hợp.

### Test mock source: ví dụ skeleton

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.integration.test.mock.MockIntegration.mockMessageSource;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.test.context.MockIntegrationContext;
import org.springframework.integration.test.context.SpringIntegrationTest;
import org.springframework.messaging.Message;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = PollingTestConfig.class)
@SpringIntegrationTest(noAutoStartup = "ordersSourceEndpoint")
class SourcePollingTest {

    @Autowired
    MockIntegrationContext mocks;

    @Autowired
    QueueChannel results;

    @AfterEach
    void resetMocks() {
        mocks.resetBeans();
    }

    @Test
    void receivesDataFromControlledSource() {
        mocks.substituteMessageSourceFor(
                "ordersSourceEndpoint",
                mockMessageSource("O-42"));

        // Trigger/start ordersSourceEndpoint qua fixture test thích hợp.
        // Sau khi poller thực sự chạy:
        Message<?> received = results.receive(5_000);
        assertNotNull(received);
    }
}
~~~

**Đây là skeleton minh họa**, chưa phải lớp test chạy độc lập: cần định nghĩa PollingTestConfig, endpoint có ID ordersSourceEndpoint, chủ động start/trigger poller và wiring output. Thay MessageSource **không tự kích hoạt poller**.

### Chờ theo tín hiệu

Tránh:

~~~java
Thread.sleep(2_000);
assertNotNull(results.receive(0));
~~~

Ưu tiên:

~~~java
Message<?> received = results.receive(5_000);
assertNotNull(received);
~~~

Hoặc dùng CountDownLatch/Awaitility với deadline. Với trường hợp cần chạy đúng một lượt poll, dùng trigger/test scheduler kiểm soát được thay vì dựa vào thời gian máy CI.

## 12. Retry và duplicate: collector đếm message nào?

Một message nguồn có thể sinh nhiều **delivery** và nhiều **handler attempts**:

~~~text
delivery #1:
    handler attempt #1 → exception
    handler attempt #2 → success
    output #1

Crash trước broker ACK.

delivery #2:
    handler attempt #1 → success / duplicate suppressed
    output #2 nếu không có idempotency
~~~

**MessageCollector đếm các message tại nơi quan sát**, không tự biết chúng biểu thị bao nhiêu business operations. Phải phân biệt:

| Đơn vị | Kiểm thử ở đâu? |
| --- | --- |
| Broker delivery | Adapter/broker instrumentation hoặc test broker thực |
| Handler attempt | Mock/spy handler hoặc metric tại handler/advice |
| Output message | MessageCollector, QueueChannel hoặc OutputDestination |
| Side effect nghiệp vụ | DB/inbox/outbox/provider state, idempotency key |

Nếu RetryAdvice thử handler 3 lần rồi thành công, collector output có thể chỉ nhận **một success message**. Nhưng nếu retry xảy ra sau khi side effect đã commit, có thể có duplicate khi chạy lại. **Không suy ra exactly-once từ việc collector chỉ thấy một output**.

### Test hai delivery cùng eventId

~~~java
Message<String> first =
        MessageBuilder.withPayload("PAYMENT_ACCEPTED")
                .setHeader("eventId", "EV-42")
                .build();

Message<String> redelivered =
        MessageBuilder.withPayload("PAYMENT_ACCEPTED")
                .setHeader("eventId", "EV-42")
                .build();

input.send(first);
input.send(redelivered);
~~~

Hai Spring Message có thể có MessageHeaders.ID khác nhau nhưng **cùng business eventId**. Nếu flow có idempotent receiver/filter, test output count theo hợp đồng; nếu flow phát output cho cả hai delivery, kiểm tra **consumer downstream/DB** vẫn chỉ áp dụng một business effect.

**Không dựa vào correlationId đơn thuần để kết luận duplicate:** Một workflow thường có nhiều message hợp lệ cùng correlationId.

## 13. Test isolation: vì sao message từ test trước xuất hiện?

Spring Test có thể **cache ApplicationContext**, và queue của collector/test channel có thể còn chứa message chưa được tiêu thụ.

~~~text
Test A:
  Input A → output A
  Queue còn A khi test kết thúc.

Test B:
  Input B → output B
  poll() lấy A trước → assert expected B thất bại.
~~~

Không nhất thiết có lỗi business flow; vấn đề là **fixture không được cách ly**.

### Các lựa chọn xử lý

1. Dùng **ApplicationContext độc lập** hoặc **test configuration riêng** cho nhóm test cần trạng thái riêng.
2. Với queue chỉ dùng để quan sát test, **drain/reset có kiểm soát** ở thời điểm không còn producer in-flight.
3. Tạo **groupKey/testRunId** khác nhau để xác định kết quả của mỗi kịch bản; vẫn phải điều tra message ngoài dự kiến.
4. Tránh chạy song song các test cùng dùng **một output queue**, trừ khi đã thiết kế bộ phân luồng message theo testRunId.
5. Với MockIntegrationContext, gọi **resetBeans()** sau test; tránh để endpoint của test này vẫn nhận mock source ở test khác.
6. Có thể sử dụng **@DirtiesContext** khi state quá phức tạp để reset, nhưng chấp nhận chi phí tái tạo ApplicationContext.

**Cẩn trọng với clear():** Xóa queue trong khi worker/poller vẫn chạy có thể che giấu lỗi “message đến trễ” hoặc làm mất output thuộc chính test đang xác minh. Tốt hơn là kiểm soát endpoint lifecycle, đợi in-flight kết thúc, rồi mới reset.

### Test nhiều message theo tập thay vì thứ tự

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.springframework.messaging.Message;

List<Message<?>> collected = new ArrayList<>();
for (int i = 0; i < 3; i++) {
    Message<?> item = results.receive(5_000);
    assertNotNull(item, "Missing output " + i);
    collected.add(item);
}

Set<Object> eventIds = new HashSet<>();
for (Message<?> item : collected) {
    eventIds.add(item.getHeaders().get("eventId"));
}

assertEquals(Set.of("EV-1", "EV-2", "EV-3"), eventIds);
assertEquals(3, collected.size());
assertNull(results.receive(0), "Unexpected fourth output");
~~~

Đây là fragment trong test có sẵn results/input và flow tạo ba output. **Set assertion** thích hợp khi yêu cầu đủ ba eventId và không cần thứ tự. Nếu muốn chắc chắn không có eventId trùng, có thể kiểm tra tất cả eventId khác null và số lượng phần tử của tập bằng số message.

### Khẳng định “không phát message” cần thời hạn quan sát

~~~java
Message<?> unexpected = results.receive(250);
assertNull(unexpected);
~~~

Nó chỉ xác nhận output **không xuất hiện trong 250 ms quan sát**. Để chứng minh aggregator không phát sớm khi thiếu phần, có thể xác minh **MessageGroupStore** còn incomplete, release strategy chưa đạt, rồi tạo phần cuối và đợi output đúng. Nếu có group timeout, phải kiểm thử cả nhánh expiry.

## 14. Chọn đúng công cụ collector theo mục tiêu

| Mục tiêu kiểm thử | Công cụ đề xuất | Hạn chế |
| --- | --- | --- |
| Duy trì code **Spring Cloud Stream legacy** đang dùng @EnableBinding | **MessageCollector.forChannel(...)** | API legacy và test binder cũ, không phù hợp dùng mặc định cho project mới |
| Kiểm tra binding function Spring Cloud Stream hiện đại | **InputDestination/OutputDestination** | Không mô phỏng đầy đủ Kafka/Rabbit semantics |
| Flow Spring Integration kết thúc bằng một output test | **QueueChannel.receive(timeout)** | Cần wiring rõ; receive tiêu thụ message |
| Quan sát message đi qua channel đang có business consumer | **WireTap → QueueChannel test** | Snapshot tại điểm tap; cần tránh side effect instrumentation |
| Xác minh handler có được gọi và nhận message gì | **MockMessageHandler/ArgumentCaptor** | Có thể thay thế logic handler, không kiểm thử side effect thật |
| Điều khiển polling source / endpoint lifecycle | **@SpringIntegrationTest + MockIntegrationContext** | Cần ID endpoint đúng, vẫn phải trigger/start poller |
| Kiểm tra exception ở worker/poller | **errorChannel route → test QueueChannel** | Phải wiring error flow; exception đồng bộ có thể truyền ngược thay vì publish |
| Kiểm tra broker ack, redelivery và restart thật | **Integration test với broker/store thật** | Chậm hơn, cần hạ tầng/fault injection |

### Thang mức độ bảo đảm của các bài test

~~~mermaid
flowchart TD
    U["Unit test transformer / release strategy"] --> C["In-JVM IntegrationFlow + QueueChannel"]
    C --> S["Spring Cloud Stream test binder"]
    S --> I["Test với DB / message store / broker thật"]
    I --> F["Crash, restart, redelivery, nhiều instance"]
~~~

Sơ đồ thể hiện **phạm vi kiểm chứng bổ sung**, không phải một thứ tự giá trị tuyệt đối: test binder dùng cho project Spring Cloud Stream, còn QueueChannel dùng cho Spring Integration thuần; hai lựa chọn này có thể **song song** chứ không bắt buộc chạy lần lượt.

## 15. Các giới hạn cần ghi rõ khi báo cáo kết quả test

**Test collector trong JVM xác minh message đã đi tới điểm quan sát**, không tự xác minh:

- **Broker durability:** một event đã được broker persist/ack thực sự hay chưa.
- **Offset/ack/redelivery:** sau crash một message được broker giao lại thế nào.
- **Cross-process ordering:** message đến từ nhiều partition/consumer ở cluster có giữ thứ tự hay không.
- **Transaction atomicity:** thao tác DB, MessageStore và external HTTP có commit cùng nhau hay không.
- **Side effect exactly-once:** một payment/email/order effect chỉ xảy ra một lần khi retry và restart.
- **Serialization compatibility:** payload/headers có sống qua persistent store và deploy phiên bản mới không.
- **Error channel mặc định:** message lỗi có được định tuyến đúng trong toàn bộ production topology hay không.
- **Backpressure/capacity:** queue in-memory của test có thể chưa tái hiện giới hạn/bottleneck của broker thật.

Vì vậy một assertion như:

~~~text
Collector received exactly one OrderCreated message.
~~~

chỉ là bằng chứng tại điểm test, không phải chứng minh toàn bộ hệ thống đã đạt **exactly-once**.

### Kết hợp kiểm tra side effect bền vững

Khi output dẫn tới DB/outbox:

1. Đo business output trên collector/QueueChannel nếu có.
2. Kiểm tra **DB row, unique business key, outbox event** đã commit.
3. Gửi lại cùng eventId với Spring Message ID khác.
4. Kiểm tra không có duplicate DB effect/outbox logical event.
5. Nếu test crash/restart, tắt process giữa **side effect commit và ack**, khởi động lại với cùng store/broker và xác minh recovery.

Collector hỗ trợ xác minh *message flow*, còn DB/provider/broker assertions xác minh *business semantics*.

## 16. Một test plan áp dụng cho flow runtime có poller và executor

**Đề bài:** Ứng dụng đọc file đơn hàng theo poller, gửi vào QueueChannel bền vững, xử lý trên executor, gọi DB, rồi phát OrderAccepted hoặc chuyển lỗi sang recovery. Thỉnh thoảng message đến lệch thứ tự và có redelivery.

Một test suite có thể thiết kế như sau:

| Ca | Arrange / Act | Điều cần assert |
| --- | --- | --- |
| 1 | Một order hợp lệ | Collector nhận đúng OrderAccepted, payload/header đúng |
| 2 | Hai order khác nhau | Thu đủ hai kết quả; không lẫn correlation |
| 3 | Handler async bị chặn bằng latch | Timed poll đợi; không assert send() đồng nghĩa hoàn tất |
| 4 | Order payload thiếu trường bắt buộc | Không có success output; lỗi vào đúng error path/exception |
| 5 | MessageSource không trả message trong một lượt poll | Không có output; poller vẫn hoạt động theo trigger |
| 6 | Poller có thể chạy nhiều lượt | Chỉ thu đúng số output có nguồn hợp lệ |
| 7 | RetryAdvice fail hai lần rồi success | Một business success output, số attempt kiểm tra bằng spy/metric |
| 8 | Redelivery cùng eventId | Không tạo side effect nghiệp vụ trùng |
| 9 | Ba message với thứ tự bất kỳ | Assert tập business IDs, không giả định thứ tự khi executor chạy song song |
| 10 | MessageGroup chưa đủ phần | Không release sớm; test timeout/expiry riêng |
| 11 | Stop poller | Không có lượt receive mới sau khi stop hoàn tất theo contract |
| 12 | Start poller | Các message hợp lệ tiếp theo được xử lý |
| 13 | Persistent store restart | State đã commit sống qua restart, kết quả phục hồi đúng |
| 14 | Broker test thực và crash trước ack | Redelivery đúng nguồn, business idempotency đúng |

### Một fixture đáng tin cậy nên có

- **Input được kiểm soát:** MessageSource mock, in-memory channel hoặc test binder, theo topology.
- **Endpoint IDs tường minh:** thuận tiện cho MockIntegrationContext và lifecycle control.
- **Output channel/collector riêng:** có tiêu chí consume/reset giữa các test.
- **Error collector riêng:** errorChannel thực sự được cấu hình đến điểm quan sát.
- **Deadline hữu hạn:** timed poll và bounded await; không treo vô hạn.
- **Correlation test-run:** testRunId ổn định trong một case, khác nhau giữa cases.
- **Không có task mồ côi:** dừng polling/executor, đóng context/connection đúng cách sau test.
- **Ngoại tác test được cô lập:** DB test, fake HTTP server hoặc test container, không gọi service production.

### Runbook chẩn đoán khi collector timeout

~~~text
1. Test có thực sự gửi được input không?
2. Endpoint đã subscribe/start chưa?
3. Poller có bị noAutoStartup hoặc trigger chưa chạy không?
4. Message có vào đúng channel và qua đúng router/filter không?
5. Handler có bị block ở executor, DB hoặc HTTP không?
6. Có exception bị publish sang errorChannel không?
7. Retry/recovery có tiêu thụ exception và thay đổi output không?
8. Output có đúng channel/binding/destination mà collector đang nghe không?
9. Collector queue có đang bị test khác nhận message không?
10. Test có dùng poll() không chờ hoặc timeout quá ngắn không?
~~~

Đừng sửa bằng cách kéo timeout lên vô hạn khi nguyên nhân thật là sai binding name hoặc một endpoint đang stop. Trước tiên xác minh đường đi của message, sau đó chọn thời gian chờ phù hợp.

## 17. Câu hỏi tự kiểm tra

**1. MessageCollector của Spring Cloud Stream legacy có nằm sẵn trong spring-integration-test không?**

**Không.** API MessageCollector.forChannel(...) là của **spring-cloud-stream-test-support** cũ. Trong Spring Integration thuần dùng QueueChannel, WireTap, mock handlers và các tiện ích của spring-integration-test.

**2. Vì sao queue.poll() trả null dù flow không lỗi?**

**Vì** poll() không chờ, trong khi handler/poller có thể chạy bất đồng bộ. Dùng poll(timeout, unit), kiểm tra endpoint và giới hạn thời gian test.

**3. Có thể thêm test subscriber vào DirectChannel để mọi message vừa tới consumer nghiệp vụ vừa tới test không?**

**Không mặc định.** DirectChannel không phải kênh broadcast. Dùng WireTap hoặc cấu trúc PublishSubscribeChannel được thiết kế có chủ đích.

**4. Vì sao OutputDestination thường trả byte[] thay vì String?**

**Vì** test binder quan sát message ở ranh giới binding có thể đã trải qua content-type conversion. Decode theo encoding/content type và test trên byte[] hoặc object theo hợp đồng thực tế.

**5. Collector nhận đúng một message thì có chứng minh exactly-once qua crash/restart không?**

**Không.** Nó chỉ chứng minh tại một điểm của một lượt chạy trong JVM. Cần kiểm thử durable storage, broker redelivery và idempotent business effect.

**6. Một test nhận message lỗi từ errorChannel bằng QueueChannel nhưng DirectChannel handler ném lỗi trực tiếp về test. Test sai ở đâu?**

**Có thể** test giả định sai ranh giới error delivery. Lỗi đồng bộ thường có thể truyền về thread gửi; error flow chỉ xuất hiện khi endpoint/adapter cấu hình publish error phù hợp.

**7. Test nhiều output qua ExecutorChannel có nên assert thứ tự đúng như lúc gửi?**

**Chỉ khi** topology quy định ordering và test đang xác minh đúng hợp đồng đó. Nếu không, so sánh tập các message theo business key.

## 18. Checklist trước khi đưa test vào CI

- Xác định project là **Spring Integration thuần**, **Spring Cloud Stream legacy** hay **Spring Cloud Stream functional**?
- Nếu dùng MessageCollector, dependency legacy có chủ đích và API forChannel(...) thuộc đúng version?
- Nếu dùng test binder mới, InputDestination/OutputDestination nhận đúng binding/destination name?
- Nếu dùng QueueChannel, nó là channel test riêng và không vô tình thay đổi consumer nghiệp vụ?
- Nếu quan sát DirectChannel có business consumer, đã dùng WireTap hoặc cơ chế phù hợp?
- Dùng timed poll/receive, không dùng take() treo vô hạn?
- Assert cả **payload, headers, correlation và số lượng**, không chỉ message khác null?
- Với executor, không coi send() trả true là downstream hoàn tất?
- Với message đến lệch thứ tự, chỉ assert thứ tự khi có ordering guarantee?
- Có test **no output before release**, timeout và late arrival đúng cách?
- Có quan sát errorChannel/exception theo đúng thread boundary và endpoint?
- Khi retry, phân biệt **handler attempt** với **output message/business operation**?
- Có chống nhiễm queue giữa các test, không xóa message trong khi worker vẫn in-flight?
- Poller có trigger/start/stop được kiểm soát, test context được reset/đóng đúng?
- Test có timeout hữu hạn và diagnostic hữu ích khi output không đến?
- Có thêm test broker/persistent store thật nếu yêu cầu ack, redelivery, transaction và restart?

## Kết luận

**MessageCollector** trong Spring Cloud Stream test-support đời cũ là một tiện ích đơn giản để **nhận message từ outbound binding thông qua BlockingQueue**. Cú pháp điển hình là **collector.forChannel(channel).poll(timeout, unit)**, sau đó assert payload và headers. Điểm quan trọng nhất là **chờ đúng thời điểm và quan sát đúng output**, không chỉ kiểm tra input.send() đã thành công.

Trong **Spring Integration Runtime hiện đại**, một flow thuần Spring Integration thường test bằng **QueueChannel, WireTap, MockMessageHandler hoặc MockIntegrationContext**; nếu ứng dụng thuộc **Spring Cloud Stream functional model**, dùng **InputDestination/OutputDestination** của test binder mới. Chọn đúng API theo dependency và phiên bản là điều kiện đầu tiên để tránh lỗi khó hiểu.

Cuối cùng, collector chỉ chứng minh **message đến một điểm quan sát trong test**. Nó không tự chứng minh transaction, error recovery, broker acknowledgment, exactly-once hoặc persistence qua restart. Cần phối hợp output assertions với **correlation, retry, message store, side effect thật và các bài test end-to-end** khi hệ thống có yêu cầu độ tin cậy cao.

## Tài liệu tham khảo

- [Spring Cloud Stream — Testing bằng legacy TestSupportBinder và MessageCollector](https://cloud.spring.io/spring-cloud-stream/single/spring-cloud-stream.html)
- [Spring Cloud Stream — Testing bằng Spring Integration Test Binder hiện đại](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring Cloud Stream — Test binder và OutputDestination](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream.html)
- [Spring Integration Reference — Testing Support](https://docs.spring.io/spring-integration/reference/testing.html)
- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint/polling-consumer.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
