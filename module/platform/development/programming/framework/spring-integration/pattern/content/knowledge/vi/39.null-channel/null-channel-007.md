# Kiểm tra flow kết thúc tại null channel trong Spring Integration

## 1. Mục tiêu: kết thúc luồng một cách có chủ đích

Trong một hệ thống xử lý message, không phải nhánh nào cũng cần tạo kết quả hoặc chuyển dữ liệu đến consumer tiếp theo. Ví dụ, sự kiện telemetry đã được ghi nhận ở bước trước có thể được **kết thúc có chủ đích**, request không thuộc phạm vi xử lý có thể bị **bỏ qua theo chính sách**, hoặc một Service Activator đã thực hiện side effect nhưng caller không cần sử dụng reply.

Spring Integration cung cấp **`nullChannel`**, một channel đặc biệt có hành vi gần giống `/dev/null`: nhận message rồi bỏ qua, không chuyển cho một consumer nghiệp vụ khác. Bài học này không chỉ nói cách cấu hình nó, mà tập trung vào **kiểm tra (test) rằng một flow thực sự kết thúc tại `nullChannel`**, thay vì tình cờ không phát ra kết quả vì lỗi, thiếu subscriber hoặc mất message.

Bài **“Kiểm tra flow kết thúc tại null channel”** thuộc chương **Null channel** của module **SPRING_INTEGRATION_PATTERN**. Module hướng dẫn triển khai Enterprise Integration Patterns với Spring Integration để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng; kết hợp Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation và thực hành kiểm thử, theo dõi các nhánh.

Sau bài học, bạn có thể:

1. Mô tả chính xác hợp đồng `send`/`receive` của `NullChannel`.
2. Cấu hình một output channel hoặc nhánh Router kết thúc rõ ràng ở `nullChannel`.
3. Phân biệt **đã xử lý ở bước trước và chủ động bỏ reply** với **chưa hề được xử lý**.
4. Viết JUnit test kiểm tra nhánh bị bỏ, nhánh được giữ, side effect và lỗi.
5. Nhận ra những phép assert yếu như “output queue rỗng” hoặc “`send()` trả `true`”.
6. Thiết kế metric, log, tracing và audit phù hợp khi một nhánh intentionally discarded.

## 2. Hợp đồng thực tế của NullChannel

Spring Integration đăng ký các channel đặc biệt **`errorChannel`** và **`nullChannel`** trong application context đã bật cơ chế integration. Tên `nullChannel` được dành riêng để tham chiếu channel bỏ message; không nên tự định nghĩa một bean nghiệp vụ khác cùng tên đó.

Theo API `org.springframework.integration.channel.NullChannel`, channel này triển khai `PollableChannel` với các tính chất:

| Thao tác | Kết quả | Diễn giải đúng |
| --- | --- | --- |
| `nullChannel.send(message)` | `true` | Đã chấp nhận message để bỏ qua; **không** xác nhận nghiệp vụ thành công |
| `nullChannel.send(message, timeout)` | `true` | Không cần slot queue để chứa message bình thường |
| `nullChannel.receive()` | `null` | Không có message nào để consumer lấy lại |
| `nullChannel.receive(timeout)` | `null` | Không nhận lại payload đã bỏ |
| Gửi message bình thường | Ghi log ở mức `DEBUG` | Không đảm bảo có log ở `INFO` hoặc trên dashboard |
| Payload là `Publisher` reactive | Được subscribe, dữ liệu phát ra bị bỏ | Không được mặc định là “không có tác dụng nào” |

Ngoại lệ ở dòng cuối đáng lưu ý: từ các phiên bản Spring Integration hỗ trợ Reactive Streams, khi **payload là `org.reactivestreams.Publisher`**, `NullChannel` có thể **subscribe** để khởi chạy publisher rồi bỏ các phần tử nhận được. Lỗi từ publisher có thể được ghi ở mức `WARN`. Do đó, không nên dùng `NullChannel` để giả định một publisher lạnh sẽ **không được thực thi**.

~~~mermaid
flowchart LR
    IN["Producer"] -->|"send(message)"| N["nullChannel"]
    N -->|"true"| ACK["Lần gửi được chấp nhận"]
    N -.->|"Không có consumer nghiệp vụ"| END["Kết thúc nhánh"]
    N -.->|"DEBUG"| LOG["Log nếu được bật"]
~~~

### Ba khẳng định phải giữ riêng

- **Đã gửi:** Producer gọi `send()` và nhận kết quả chấp nhận.
- **Đã đi qua bước nghiệp vụ:** Handler, Transformer hoặc Router cụ thể đã được gọi đúng cách.
- **Đã hoàn tất nghiệp vụ:** Có kết quả, side effect hay trạng thái đã commit phù hợp với hợp đồng.

`NullChannel` **chỉ hỗ trợ xác nhận loại thứ nhất tại ranh giới channel**. Nó không tự chứng minh hai loại còn lại. Khi kiểm thử, phải gắn assertion ở điểm phù hợp.

## 3. Khi nào nên kết thúc tại null channel?

| Tình huống | Lý do dùng `nullChannel` | Điều kiện phải xem xét |
| --- | --- | --- |
| Bỏ reply của một handler one-way | Không có consumer nào cần kết quả trả về | Side effect đã được kiểm chứng ở handler |
| Nhánh Router cố ý loại message | Quy tắc nghiệp vụ cho phép bỏ | Ghi nhận quyết định loại và lý do |
| Filter discard theo chính sách | Message không đạt điều kiện xử lý | Không biến message hợp lệ thành mất dữ liệu |
| Kết thúc flow sau thao tác log/observability | Tránh reply vô nghĩa ở cuối flow | Log không thay thế audit bền vững |
| Thử nghiệm sink black-hole | Xác minh không có xử lý tiếp downstream | Dùng dữ liệu test, không phải message quan trọng |

Không nên dùng `nullChannel` như một “đường xử lý lỗi mặc định” cho thanh toán, cập nhật trạng thái quan trọng, event bắt buộc phải lưu hoặc các message cần recovery. Nếu có lỗi hoặc dữ liệu không hợp lệ, ưu tiên error channel, dead-letter, retry có giới hạn hoặc cơ chế phản hồi nghiệp vụ rõ ràng.

### Phân biệt các cơ chế gần giống

| Cơ chế | Hành vi chính | Có thay thế NullChannel không? |
| --- | --- | --- |
| `NullChannel` | Nhận rồi bỏ message | Phù hợp khi chủ đích kết thúc ở sink |
| `QueueChannel` | Giữ message cho consumer poll | Không; queue vẫn lưu và có thể đầy |
| `DirectChannel` | Giao cho subscriber theo lời gọi đồng bộ | Không; thiếu subscriber có thể gây lỗi |
| `errorChannel` | Luồng phân phối/thao tác với lỗi | Không; không có nghĩa tự sửa lỗi |
| Filter loại message | Quyết định message có đi tiếp hay không | Khác: Filter là điều kiện, sink là đích |
| Handler trả `null` | Có thể không tạo reply message | Khác: không chứng minh message đã đi tới `nullChannel` |

## 4. Sơ đồ một flow kết thúc rõ ràng

Giả sử một ứng dụng nhận sự kiện từ Router. Nhánh `KEEP` phải đi đến queue lưu tạm; nhánh `DROP` chỉ cần ghi lại quyết định và kết thúc.

~~~mermaid
flowchart TD
    IN["Input events"] --> R{"Router theo policy"}
    R -->|"KEEP"| Q["kept.output\nQueueChannel"]
    R -->|"DROP"| N["nullChannel\nbỏ message"]
    IN2["drop.input"] --> T["Transformer\ntrim payload"]
    T --> H["Handler\nđánh dấu đã xử lý"]
    H --> N
    N -.-> MON["Log/metric quan sát ở trước sink"]
~~~

Để kết luận *flow kết thúc đúng ở null channel*, cần **kết hợp bằng chứng về cấu hình và hành vi**:

1. Configuration có **đích `nullChannel` tường minh** ở cuối nhánh.
2. Message tới được bước ngay trước sink; có một test probe, spy hoặc side effect nhỏ chứng minh.
3. Sau đó không có message nghiệp vụ ở output channel mà lẽ ra chỉ nhận nhánh `KEEP`.
4. Đường thành công và lỗi được phân biệt: một handler ném exception **không** được xem là “discard thành công”.

Chỉ một assertion `keptOutput.receive(0) == null` là **chưa đủ**: queue rỗng có thể vì input chưa vào flow, Router sai route hoặc handler đã lỗi.

## 5. Cấu hình Java DSL: hướng tới NullChannel

Một flow rất ngắn có thể kết thúc như sau:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableIntegration
class SimpleDiscardFlow {

    @Bean
    IntegrationFlow cleanAndDiscard() {
        return IntegrationFlow.from("clean.input")
                .transform(String.class, String::trim)
                .channel("nullChannel")
                .get();
    }
}
~~~

Khi `clean.input` nhận một String, Transformer tạo kết quả đã trim và output được gửi đến channel đặc biệt tên `nullChannel`. **Message đã bỏ không thể nhận lại bằng `receive()`**; nếu cần xác minh payload sau transform, có thể gắn một probe **trước** NullChannel hoặc dùng một test độc lập cho Transformer.

Java DSL cũng có toán tử `nullChannel()` dành cho việc kết thúc luồng một cách rõ ràng ở những phiên bản hỗ trợ. Khi code cần tương thích với nhiều bản Spring Integration 6.x, việc tham chiếu `.channel("nullChannel")` là cách diễn đạt minh bạch, dễ kiểm tra trong bài này.

### Kết hợp với log

~~~java
@Bean
IntegrationFlow logAndDiscard() {
    return IntegrationFlow.from("log.input")
            .transform(String.class, String::trim)
            .log()
            .channel("nullChannel")
            .get();
}
~~~

Spring Integration 6.x xem `log()` là bước quan sát (wire tap) chứ **không** tự trở thành consumer kết thúc flow. Sau `log()`, tham chiếu rõ `nullChannel` giúp người đọc code hiểu rằng **reply không còn đích sử dụng**. Tránh nhầm “đã log” với “đã gửi được kết quả nghiệp vụ”.

### XML khi hệ thống dùng namespace configuration

~~~xml
<int:channel id="cleanupInput"/>

<int:transformer input-channel="cleanupInput"
                 output-channel="nullChannel"
                 expression="payload.trim()"/>
~~~

Đoạn XML minh họa cần được đặt trong cấu hình có namespace `int` và schema tương thích. Bạn không cần tự tạo `<int:channel id="nullChannel"/>`: đó là special channel do Spring Integration cung cấp.

## 6. Test hành vi trực tiếp của NullChannel

Trước khi kiểm thử một flow nhiều bước, cần có test nhỏ chứng minh hành vi của chính loại channel này.

Với **Java 17, Spring Integration 6.x, JUnit 5 và AssertJ**:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.NullChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class NullChannelContractTest {

    @Test
    void send_accepts_message_but_never_makes_it_available_to_receive() {
        NullChannel sink = new NullChannel();
        Message<String> message = MessageBuilder
                .withPayload("not-retained")
                .setHeader("requestId", "req-1")
                .build();

        assertThat(sink.send(message)).isTrue();
        assertThat(sink.receive(0)).isNull();

        assertThat(sink.send(message, 0)).isTrue();
        assertThat(sink.receive(100)).isNull();
    }
}
~~~

Test này khẳng định **hợp đồng của NullChannel**, chưa chứng minh một `IntegrationFlow` cụ thể đã được nối vào sink này. Đó là mục tiêu khác và cần test context ở phần tiếp theo.

**Không dùng `send() == true` như bằng chứng message đã được lưu hoặc xử lý**; với NullChannel, chính sự chấp nhận và bỏ qua là hành vi mong muốn.

## 7. Integration test: một nhánh kết thúc, một nhánh được giữ

Ta xây dựng ba đường để làm đối chứng:

- `drop.input`: Transformer → handler có probe → `nullChannel`.
- `route.input` với payload bắt đầu bằng `DROP:`: Router → `nullChannel`.
- `route.input` với payload bắt đầu bằng `KEEP:`: Router → `kept.output` (`QueueChannel`).

Như vậy test có cả **đường bị bỏ** lẫn **đường đối chứng được giữ**. Nếu route cấu hình sai khiến cả hai đều bị mất, test KEEP sẽ phát hiện.

### Cấu hình và test đầy đủ

Tạo `src/test/java/example/NullChannelTerminalFlowTest.java`:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.NullChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(NullChannelTerminalFlowTest.FlowConfig.class)
class NullChannelTerminalFlowTest {

    @Autowired
    @Qualifier("drop.input")
    MessageChannel dropInput;

    @Autowired
    @Qualifier("route.input")
    MessageChannel routeInput;

    @Autowired
    @Qualifier("kept.output")
    QueueChannel keptOutput;

    @Autowired
    @Qualifier("nullChannel")
    PollableChannel nullChannel;

    @Autowired
    TerminalProbe probe;

    record Seen(String payload, String requestId) {}

    static final class TerminalProbe {
        private final List<Seen> events =
                new CopyOnWriteArrayList<>();

        void record(String payload, String requestId) {
            events.add(new Seen(payload, requestId));
        }

        List<Seen> snapshot() {
            return List.copyOf(events);
        }

        void clear() {
            events.clear();
        }
    }

    @BeforeEach
    void resetObservations() {
        probe.clear();
        while (keptOutput.receive(0) != null) {
            // Cô lập trạng thái queue giữa các test.
        }
    }

    private static Message<String> event(
            String payload, String requestId) {
        return MessageBuilder.withPayload(payload)
                .setHeader("requestId", requestId)
                .build();
    }

    @Test
    void drop_flow_reaches_last_handler_then_terminates_at_null_channel() {
        assertThat(dropInput.send(event("  hello  ", "req-drop-1")))
                .isTrue();

        // Bằng chứng bước trước sink đã thực sự chạy.
        assertThat(probe.snapshot())
                .containsExactly(new Seen("hello", "req-drop-1"));

        // Nhánh DROP không đi vào output dành cho KEEP.
        assertThat(keptOutput.receive(0)).isNull();

        // NullChannel không giữ một reply để poll lại.
        assertThat(nullChannel).isInstanceOf(NullChannel.class);
        assertThat(nullChannel.receive(0)).isNull();
    }

    @Test
    void router_explicitly_discards_drop_branch() {
        assertThat(routeInput.send(event("DROP:debug", "req-route-1")))
                .isTrue();

        assertThat(keptOutput.receive(0)).isNull();
        assertThat(probe.snapshot()).isEmpty();
    }

    @Test
    void control_branch_still_delivers_to_real_consumer_channel() {
        assertThat(routeInput.send(event("KEEP:order", "req-route-2")))
                .isTrue();

        Message<?> kept = keptOutput.receive(1_000);
        assertThat(kept).isNotNull();
        assertThat(kept.getPayload()).isEqualTo("KEEP:order");
        assertThat(kept.getHeaders().get("requestId"))
                .isEqualTo("req-route-2");
        assertThat(keptOutput.receive(0)).isNull();
    }

    @Test
    void handler_error_does_not_become_a_successful_discard() {
        assertThatThrownBy(() ->
                dropInput.send(event("  FAIL  ", "req-fail")))
                .satisfies(error -> {
                    Throwable root = error;
                    while (root.getCause() != null) {
                        root = root.getCause();
                    }
                    assertThat(root)
                            .isInstanceOf(IllegalStateException.class);
                });

        assertThat(probe.snapshot()).isEmpty();
        assertThat(keptOutput.receive(0)).isNull();
    }

    @Configuration
    @EnableIntegration
    static class FlowConfig {

        @Bean("drop.input")
        DirectChannel dropInput() {
            return new DirectChannel();
        }

        @Bean("route.input")
        DirectChannel routeInput() {
            return new DirectChannel();
        }

        @Bean("kept.output")
        QueueChannel keptOutput() {
            return new QueueChannel();
        }

        @Bean
        TerminalProbe probe() {
            return new TerminalProbe();
        }

        @Bean
        IntegrationFlow terminalFlow(TerminalProbe probe) {
            return IntegrationFlow.from("drop.input")
                    .transform(String.class, String::trim)
                    .handle(String.class, (payload, headers) -> {
                        if (payload.equals("FAIL")) {
                            throw new IllegalStateException("forced failure");
                        }
                        probe.record(
                                payload, (String) headers.get("requestId"));
                        // Cố ý tạo reply để kiểm chứng terminal routing.
                        return "processed:" + payload;
                    })
                    .channel("nullChannel")
                    .get();
        }

        @Bean
        IntegrationFlow routerFlow() {
            return IntegrationFlow.from("route.input")
                    .route(String.class,
                            payload -> payload.startsWith("DROP:")
                                    ? "nullChannel"
                                    : "kept.output")
                    .get();
        }
    }
}
~~~

**Điểm then chốt trong cấu hình:** Handler ở `terminalFlow` **trả lại String** `processed:...`, tức có reply message để chuyển tiếp. Cấu hình `.channel("nullChannel")` khiến reply đó bị loại một cách tường minh. Nếu handler trả `null`, test có thể cho kết quả “không thấy reply” nhưng **không xác nhận được đường ra của handler đã đi vào sink**.

### Test này chứng minh gì và chưa chứng minh gì?

| Assertion | Bằng chứng | Giới hạn |
| --- | --- | --- |
| `probe.snapshot()` có một phần tử | Transformer và handler đã chạy tới trước sink | Chưa độc lập chứng minh từng lần gửi vào sink |
| `keptOutput.receive(0) == null` sau DROP | Không có message ở output nhánh KEEP | Riêng assertion này không đủ |
| `nullChannel` là `NullChannel` và `receive(0) == null` | Special channel không giữ message để nhận lại | Không chứng minh một lần gửi cụ thể đã diễn ra |
| `KEEP` có message và header đúng | Router đối chứng hoạt động, output thực nhận được | Không thay cho kiểm thử toàn bộ ứng dụng |
| Exception được quan sát trên DirectChannel | Lỗi handler không tự bị sink nuốt | Luồng async/error channel có semantics khác |
| `.channel("nullChannel")` trong cấu hình | Có kết nối đích tường minh | Với quy trình đòi bằng chứng cấp send, thêm spy/probe đúng ranh giới |

Nếu yêu cầu audit rất nghiêm ngặt là **xác minh một message cụ thể được gọi `send` vào channel nào**, có thể thiết lập một **test-only sending probe**, wire tap ở channel trung gian, hoặc kiểm tra graph của integration flow. Không nên kết luận duy nhất từ việc “sau một thời gian không thấy message” vì đó là assertion về *sự vắng mặt*, vốn dễ bị lỗi do race hoặc cấu hình sai.

## 8. Sử dụng Wire Tap hoặc probe mà không đổi semantics

Khi một message được gửi vào `nullChannel`, chính sink không còn giữ bản sao để test đọc lại. Nếu cần quan sát trước khi bỏ, **đặt probe ở bước ngay trước sink**:

~~~mermaid
flowchart LR
    H["Last Handler"] --> STAGE["Observable stage"]
    STAGE --> NULL["nullChannel"]
    STAGE -. "Wire Tap" .-> TAP["Test / Audit / Log Channel"]
~~~

Ví dụ sử dụng `WireTap` với một `DirectChannel` có thể đăng ký:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.channel.interceptor.WireTap;

@Bean("terminal.probe")
QueueChannel terminalProbeQueue() {
    return new QueueChannel();
}

@Bean("terminal.observed")
DirectChannel observedStage(
        @Qualifier("terminal.probe") QueueChannel terminalProbeQueue) {
    DirectChannel channel = new DirectChannel();
    channel.addInterceptor(new WireTap(terminalProbeQueue));
    return channel;
}
~~~

Sau đó nối một endpoint từ `terminal.observed` tới `nullChannel` (ví dụ bridge) và kiểm tra `terminal.probe` có message trước khi sink bỏ. **Wire Tap tạo thêm nhánh quan sát**, nên chính bản sao ở queue tap không có nghĩa message của nhánh chính đã được lưu ở `nullChannel`.

Nếu dùng Wire Tap trong sản phẩm, cần xét độ bền, capacity, phản hồi khi tap bị lỗi và thông tin nhạy cảm. Một tap đo/debug không nên vô tình trở thành đường bắt buộc làm hỏng flow chính hoặc sao chép payload nhạy cảm sang log.

## 9. Một cách kiểm tra cấu hình không phụ thuộc timing

Đối với flow đồng bộ với `DirectChannel`, test có thể kiểm tra ngay sau `send()`, vì handler chạy trong cùng đường gọi. Tuy nhiên, **đừng mở rộng giả định đó** sang:

- `QueueChannel` có poller khác thread.
- `ExecutorChannel` phân phối xử lý bất đồng bộ.
- Kafka, JMS hoặc HTTP adapter vượt qua process.
- Retry/backoff khiến message đến sink sau.
- Splitter/Aggregator giữ fragment để chờ nhóm.

Với flow bất đồng bộ, dùng một **tín hiệu hoàn tất trước sink** (latch hoặc `QueueChannel` quan sát) rồi mới assert queue nghiệp vụ vẫn rỗng. Vẫn cần **kiểm tra đích routing tường minh**, nếu không có thể chỉ đang chứng minh một tác vụ chưa chạy.

Mẫu test bất đồng bộ hợp lý:

~~~java
// Pseudocode: một probe riêng nằm ngay trước nullChannel.
sendAsyncMessage("DROP");
Message<?> beforeSink = probeChannel.receive(2_000);
assertThat(beforeSink).isNotNull();
assertThat(beforeSink.getHeaders().get("requestId"))
        .isEqualTo("req-100");

// Sau đó xác minh flow routing tới nullChannel theo cấu hình.
assertThat(realBusinessOutput.receive(0)).isNull();
~~~

**Không dùng** `Thread.sleep(500)` rồi thấy queue rỗng để kết luận discard thành công: trên CI, consumer có thể chưa chạy, hoặc có lỗi được gửi tới error channel.

## 10. Log ở null channel có phải bằng chứng thành công?

Theo tài liệu Spring Integration, `nullChannel` ghi message vào log ở mức **`DEBUG`** rồi bỏ. Trong vận hành, điều này có các hệ quả:

1. Ở mức log `INFO`, bạn có thể **không thấy dòng log nào** dù message đã gửi vào sink.
2. Log `DEBUG` là tín hiệu chẩn đoán, không phải hóa đơn xác nhận giao dịch đã hoàn tất.
3. Bật `DEBUG` có thể làm log lớn hoặc để lộ payload/header nếu không lọc dữ liệu nhạy cảm.
4. Không nên viết test so sánh **nguyên văn** message log nội bộ giữa nhiều phiên bản thư viện.

Nếu cần audit đáng tin, hãy đặt một bước **audit event hoặc counter trước sink**, với khóa correlation phù hợp. Một số metric ứng dụng hữu ích:

| Metric ứng dụng đề xuất | Nhãn ít giá trị | Ý nghĩa |
| --- | --- | --- |
| `flow_terminal_discard_total` | `flow`, `reason`, `route` | Số message bị bỏ có chủ đích |
| `flow_terminal_drop_error_total` | `flow`, `errorType` | Lỗi ở bước trước terminal sink |
| `flow_processed_total` | `flow`, `outcome` | Handler đã xử lý đến bước cần đo |
| `flow_terminal_latency_seconds` | `flow`, `route` | Thời gian đến ranh giới kết thúc |

Đây là **tên metric gợi ý**, không phải tất cả đều do Spring Integration tự động cung cấp. Không đặt `requestId`, `messageId`, `correlationId` hay `userId` làm label metric nếu mỗi message có giá trị mới; dùng chúng ở structured log/trace để điều tra từng trường hợp.

### Phân biệt “dropped” với “processed successfully”

Ví dụ event:

~~~json
{
  "event": "message.discarded",
  "flow": "telemetry-cleanup",
  "route": "ignored",
  "reason": "non_actionable",
  "requestId": "req-100",
  "correlationId": "corr-100",
  "outcome": "intentionally_discarded"
}
~~~

Nên phân biệt `intentionally_discarded` với `successfully_processed`, `failed`, `timed_out`. Những trạng thái này không thể suy ra chỉ từ `send() == true`.

## 11. Router/Filter và đích NullChannel

### Router

Một Router có thể chọn `nullChannel` cho nhánh không cần xử lý:

~~~java
@Bean
IntegrationFlow routeUnknownToNull() {
    return IntegrationFlow.from("events.in")
            .route(String.class, payload ->
                    payload.startsWith("KNOWN:")
                            ? "events.known"
                            : "nullChannel")
            .get();
}
~~~

**Đây là một quyết định routing tường minh.** Khi kiểm thử phải kiểm tra **cả nhánh KNOWN** để chắc rằng default hoặc điều kiện không đẩy toàn bộ thông điệp vào sink.

Đối với message quan trọng nhưng không xác định route, chỉ gửi vào `nullChannel` là nguy hiểm. Cân nhắc `resolutionRequired`, default route đến xử lý lỗi hoặc dead-letter theo hợp đồng nghiệp vụ.

### Filter

Một Filter loại message là quyết định về điều kiện, có thể **kết thúc flow trước khi tới `nullChannel`**. Nếu mục tiêu của test là “message đi vào `nullChannel`”, việc thấy Filter đã reject **không tương đương**.

Có thể cấu hình discard channel là `nullChannel` khi business policy cho phép, nhưng test nên phân biệt rõ:

- **Filter rejected:** Điều kiện không đạt.
- **Discard sent:** Message đi vào discard channel được cấu hình.
- **Final outcome:** Bỏ message có chủ đích, hay cần audit/lỗi?

Với Filter cần giải trình, hãy ghi `reason` hoặc metric trước khi gửi đến sink, thay vì coi Filter reject là lỗi hạ tầng.

## 12. Gateway: nếu caller đang chờ reply thì sao?

Đây là một bẫy quan trọng của request–reply. Một message đi đến `nullChannel` **không tự tạo reply cho Gateway**. Nếu caller dùng phương thức trả về dữ liệu (ví dụ `String submit(...)`), caller có thể chờ tới `replyTimeout` hoặc gặp exception theo chính sách timeout.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Gateway
    participant N as nullChannel
    C->>G: submit(request)
    G->>N: send(request)
    N-->>G: accepted=true
    Note over N: Bỏ message, không tạo reply
    Note over G: Caller vẫn đang chờ reply
    G-->>C: timeout / null / exception tùy policy
~~~

Ngược lại, phương thức one-way `void submit(...)` có thể phù hợp nếu chỉ cần chấp nhận/giao tác vụ và không yêu cầu reply. Nhưng **không được hiểu `void` hoặc `send()==true` là đã commit side effect**.

Test nên phân biệt:

- Gateway one-way không đợi result; contract chỉ yêu cầu enqueue/send thành công.
- Gateway request–reply có `defaultReplyTimeout` tường minh; nếu đích thực sự là sink, xác minh policy timeout.
- Nếu muốn trả lời “đã chấp nhận”, phải có một thành phần chủ động tạo **acknowledgment nghiệp vụ** trước khi flow kết thúc, không kỳ vọng NullChannel tự phát ra ACK.

Với DirectChannel và handler đồng bộ chạy lâu, timeout của Gateway không nhất thiết cắt được handler đang thực thi trên caller thread. Khi kiểm thử thời gian chờ cần làm rõ ranh giới bất đồng bộ.

## 13. Error channel, retry và NullChannel là ba trách nhiệm khác nhau

Không nên mặc định mọi exception đều được chuyển tới `nullChannel`. Một handler đồng bộ ném exception **trước** khi phát message ra sink sẽ làm luồng thất bại; test trong mục 7 chủ động kiểm tra điều này.

Ở luồng bất đồng bộ, lỗi có thể được gửi đến `errorChannel` hoặc đường recovery theo cấu hình. Nếu hệ thống cố tình định tuyến `ErrorMessage` vào `nullChannel`, phần xử lý lỗi đó cũng có thể bị bỏ qua. Đây là **chính sách che giấu lỗi**, không phải cách xử lý an toàn mặc định.

~~~text
Input
  |
  +--> Handler thành công --> nullChannel        (discard có chủ đích)
  |
  +--> Handler thất bại  --> error/retry path    (không coi là success)
                               |
                               +--> recovery / dead-letter / alert
~~~

Đối với retry:

1. Nếu request bị lặp do producer timeout, có thể gọi handler nhiều lần **trước khi** reply bị bỏ.
2. Nếu handler thực hiện side effect (ghi DB/gọi API), `nullChannel` **không ngăn duplicate side effect**.
3. Nên dùng idempotency key, transaction/outbox hoặc dedup khi nghiệp vụ yêu cầu.
4. Retry cần giới hạn lượt thử và recovery path rõ ràng; tránh vô hạn.
5. Khi drop đúng policy, ghi sự kiện `intentionally_discarded` thay vì giả lập `success`.

## 14. Splitter, Aggregator và correlation ID

Một flow có Splitter thường tạo nhiều fragment. Nếu vô tình trỏ một nhánh fragment vào `nullChannel`, Aggregator có thể không bao giờ nhận đủ phần tử và group không được release.

~~~mermaid
flowchart TD
    IN["Request"] --> S["Splitter"]
    S -->|"fragment 1"| A["Aggregator"]
    S -->|"fragment 2"| N["nullChannel"]
    A -->|"Đợi fragment 2"| WAIT["Group chưa complete / timeout"]
~~~

Do đó, khi test một flow “kết thúc tại NullChannel” cần xác định **cái gì được phép bị bỏ**:

- Toàn bộ request bị loại theo policy?
- Chỉ phần kết quả đã được xử lý, không còn consumer?
- Một fragment trung gian mà Aggregator thực tế đang chờ?

Nếu có correlation, giữ rõ:

| Header | Mục đích |
| --- | --- |
| `requestId` | Truy vết một request nghiệp vụ |
| `correlationId` của EIP | Nhóm fragment hoặc ghép barrier theo strategy |
| `sequenceNumber` | Thứ tự fragment trong nhóm |
| `sequenceSize` | Kích thước nhóm dự kiến |

Không nên dùng `nullChannel` để “sửa” vấn đề một fragment lỗi mà không có release strategy/timeout hoặc chính sách partial result. Thao tác đó có thể tạo **message mất im lặng** và làm consumer khác chờ lâu.

## 15. Trường hợp reactive Publisher: ngoại lệ cần biết

Với payload thông thường, `NullChannel` bỏ message nhanh. Nhưng khi payload là một **Reactive Streams Publisher**, framework có hành vi riêng: subscribe Publisher để khởi chạy luồng rồi **bỏ các phần tử** do Publisher phát ra. Vì vậy:

- Không thể nói chắc “gửi vào nullChannel thì logic Publisher không chạy”.
- Publisher có side effect khi subscribe vẫn có thể thực thi.
- Lỗi từ Publisher có thể được log ở mức `WARN`; điều này **không tự tạo một quy trình recovery**.
- Nếu lỗi phải được xử lý nghiệp vụ, áp dụng error handling/reactive advice có chủ đích, ví dụ `ReactiveRequestHandlerAdvice` hoặc một pipeline xử lý error đã test.

Không cần thêm Reactor vào project chỉ để kiểm tra nhánh discard thông thường. Nếu ứng dụng thật dùng `Mono`/`Flux`, bổ sung test riêng xác nhận tác dụng của subscription và đường lỗi; không lấy kết quả test String làm bảo đảm cho payload Publisher.

## 16. Ma trận kiểm thử đề xuất

| Kịch bản | Thiết lập | Assertion chính |
| --- | --- | --- |
| NullChannel contract | Gửi message trực tiếp | `send=true`, `receive=null` |
| Terminal flow thành công | Handler trả output rồi route tới `nullChannel` | Probe thấy handler chạy, cấu hình sink tường minh |
| Router DROP | `DROP:...` | Không có output business, route đến `nullChannel` |
| Router KEEP (đối chứng) | `KEEP:...` | Output queue nhận message đúng |
| Handler ném exception | Input `FAIL` | Lỗi vẫn quan sát được; không bị tính là discard |
| Filter discard | Filter loại theo policy | Có lý do loại và discard destination đúng |
| Không có subscriber | Thay sink bằng DirectChannel rỗng | Test phân biệt wiring lỗi với drop |
| Gateway chờ reply | Request–reply đi vào `nullChannel` | Reply timeout đúng policy, không có reply giả |
| Retry | Hai lần gửi cùng ID | Side effect xử lý theo idempotency contract |
| Aggregator thiếu fragment | Một fragment đi vào sink | Không giả định group complete |
| Async sink | Queue/Executor trước sink | Probe xác nhận hoàn tất trước khi assert vắng mặt |
| Reactive Publisher | Payload Publisher | Subscription và lỗi đúng policy |
| Observability | Nhánh bị bỏ có requestId | Log/metric audit có trạng thái intentionally discarded |

### Đặt tên test theo hành vi, không theo mong muốn

Tên test `message_is_successfully_processed_when_sent_to_null_channel` dễ gây hiểu sai. Tên rõ hơn:

~~~text
null_channel_accepts_but_discards_message()
handler_runs_then_reply_is_discarded()
unknown_route_is_explicitly_discarded()
accepted_route_still_reaches_consumer()
handler_failure_is_not_silently_treated_as_discard()
~~~

Từ ngữ `accepted`, `processed`, `discarded` và `completed` phải được dùng nhất quán giữa code, test, metric và tài liệu vận hành.

## 17. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ assert `send()==true` | Nhầm chấp nhận với thành công nghiệp vụ | Assert handler/probe và contract |
| Chỉ assert output rỗng | Không phân biệt đã drop với chưa xử lý | Positive control route và probe |
| Handler trả `null` rồi nói đã qua sink | Flow có thể kết thúc trước NullChannel | Tạo output và trỏ đích sink tường minh |
| Coi DEBUG log là bằng chứng audit bền vững | Khó đối soát khi log bị tắt/xóa | Ghi audit event trước sink khi cần |
| Gửi message lỗi vào sink để khỏi ném exception | Che mất sự cố thật | Error channel/recovery riêng |
| Gắn mọi route mặc định vào `nullChannel` | Message hợp lệ có thể bị bỏ im lặng | Kiểm tra route KEEP/unknown |
| Dùng Gateway chờ reply với sink không trả reply | Caller timeout bất ngờ | Phương thức one-way hoặc reply policy rõ |
| Giả định NullChannel lưu backlog | Không thể lấy lại dữ liệu | Dùng QueueChannel/broker/store khi cần lưu |
| Quên special case Publisher | Reactive side effect vẫn chạy | Test subscribe và error policy |
| Không theo dõi drop rate | Không thấy lượng dữ liệu bỏ tăng đột biến | Counter/drop reason, alert |
| Dùng `Thread.sleep` để chứng minh async flow dừng | Test dễ flaky | Probe/latch và timeout hữu hạn |
| Không tính fragment Aggregator | Group thiếu dữ liệu | Release/timeout policy và correlation test |

## 18. Bài thực hành

### Bài A — Test contract của NullChannel

Tạo `new NullChannel()`, gửi hai message có payload khác nhau. Xác minh cả hai lần gửi trả `true`, mọi `receive(0)` đều trả `null`. Giải thích vì sao đó không phải thông báo “đã xử lý thành công”.

### Bài B — Flow chuẩn hóa rồi discard

Tạo `input → Transformer(trim) → Service Activator → nullChannel`. Service Activator phải trả output không rỗng để có message cuối flow. Dùng một probe để ghi nhận payload và requestId ở bước trước sink, sau đó kiểm tra không có output nghiệp vụ sau terminal route.

### Bài C — Hai route đối chứng

Tạo Router với `KEEP` tới `QueueChannel`, `DROP` tới `nullChannel`. Test với hai request, mỗi request có ID khác nhau. Xác minh `KEEP` đến đúng queue và `DROP` được chọn vào sink. Thêm một input không thuộc hai nhóm và định nghĩa rõ chính sách unknown route.

### Bài D — Failure trước sink

Làm Service Activator ném exception khi payload là `FAIL`. Xác nhận `nullChannel` không tự “nuốt” exception trước khi message đến sink. Sau đó thử cấu hình bất đồng bộ và kiểm tra đúng đường error channel, không chỉ đợi output rỗng.

### Bài E — Kiểm thử Gateway

Cho Gateway one-way gửi vào flow cuối cùng tới `nullChannel`. So sánh với Gateway request–reply trả `String` và có timeout hữu hạn. Xác định policy phải dùng trong ứng dụng thực tế và không đánh đồng `send accepted` với `reply delivered`.

### Bài F — Quan sát và audit

Thêm `flow_terminal_discard_total{flow,reason}` ở bước trước sink; thêm log có `requestId` và `outcome=intentionally_discarded`. Dùng test gửi ba message bị bỏ và một message KEEP; kiểm tra counter tăng chính xác và không đưa requestId làm label metric. Nếu có yêu cầu audit bền vững, thiết kế write/recovery hoặc outbox thích hợp.

### Bài G — Fragment và reactive payload

Tạo một flow Splitter/Aggregator có một fragment bị route nhầm vào sink. Kiểm tra group không được coi là đã hoàn tất bình thường. Với nhánh khác sử dụng `Publisher`, viết test riêng chứng minh side effect của subscription (nếu có) và bảo đảm không giả định dữ liệu reactive không chạy.

## 19. Checklist để kết luận “flow kết thúc đúng ở null channel”

1. Cấu hình có đích `nullChannel` tường minh, không chỉ vô tình thiếu output?
2. Input đã được chấp nhận và endpoint cần chạy **thực sự được gọi**?
3. Có probe/positive control để loại trừ khả năng message bị mất từ trước?
4. Nếu handler cần tạo reply, test đã cấu hình handler trả output không rỗng?
5. Nhánh DROP không đi tới consumer nghiệp vụ ngoài dự kiến?
6. Nhánh KEEP vẫn đi tới output thật khi điều kiện phù hợp?
7. Exception trước sink vẫn được nhận diện và không bị tính thành discard success?
8. Gateway one-way và request–reply có hợp đồng riêng, timeout rõ ràng?
9. Khi flow async, test đợi tín hiệu hoàn tất thay vì dùng sleep?
10. NullChannel không bị dùng để thay QueueChannel, broker hoặc dead-letter cần độ bền?
11. Nếu có Publisher payload, đã kiểm tra subscription và lỗi?
12. Log, metric và audit có phân biệt trạng thái **intentionally discarded** với **success** và **failed**?
13. Correlation/requestId được giữ để điều tra mà không làm bùng nổ cardinality metric?
14. Splitter/Aggregator, retry và error channel không bị làm hỏng bởi việc bỏ message giữa chừng?
15. Test có tính độc lập, dọn queue/probe và không phụ thuộc trùng hợp thời gian?

**Kết luận:** Kiểm tra một flow kết thúc tại `nullChannel` không chỉ là “không nhận được message ở output”. Cần chứng minh **đường định tuyến rõ ràng**, **bước xử lý trước sink đã chạy**, **nhánh đối chứng vẫn hoạt động** và **lỗi không bị che giấu**. Trong Spring Integration, `NullChannel` là công cụ hợp lý để kết thúc một nhánh không cần output, miễn việc loại bỏ là quyết định nghiệp vụ có chủ đích và được kiểm thử, giám sát, ghi nhận đúng mức.

### Tài liệu tham khảo

- [Spring Integration Reference 6.4 — Special Channels](https://docs.spring.io/spring-integration/reference/6.4/channel/special-channels.html): channel đặc biệt `nullChannel`, DEBUG logging và Publisher payload.
- [Spring Integration API 6.4.2 — NullChannel](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/channel/NullChannel.html): `send`/`receive` và hợp đồng `PollableChannel`.
- [Spring Integration Reference — Java DSL `log()`](https://docs.spring.io/spring-integration/reference/dsl/java-log.html): log là operator quan sát, có thể kết thúc rõ bằng `nullChannel()`.
- [Spring Integration Reference — Logging Channel Adapter](https://docs.spring.io/spring-integration/reference/logging-adapter.html): phân biệt logging endpoint và channel bỏ message.
