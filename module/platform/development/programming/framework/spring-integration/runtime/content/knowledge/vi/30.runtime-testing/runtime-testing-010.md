# Test integration graph và observability hook trong Spring Integration runtime

## 1. Mục tiêu: kiểm chứng cả topology lẫn tín hiệu vận hành

Trong **SPRING_INTEGRATION_RUNTIME**, một message flow không chỉ là một hàm Java gọi hàm khác. Spring Integration tạo một mạng lưới gồm channel, consumer endpoint, handler, poller, gateway, router, error flow và những thành phần vòng đời có thể quản trị. Khi flow được sửa bằng Java DSL, annotation hoặc cấu hình XML, test chỉ gửi một message rồi kiểm tra payload cuối **chưa đủ** để phát hiện:

- Nhầm input channel hoặc output channel;
- Thiếu subscriber, endpoint chưa start hay lifecycle sai;
- Nhánh `errorChannel`, `discardChannel` hoặc route bị đứt;
- Endpoint động được thêm nhưng runtime graph chưa refresh;
- Metrics/tracing/observation không phát ra dù nghiệp vụ chạy thành công;
- Retry, executor, poller hoặc broker khiến lỗi xuất hiện ở thread khác;
- Observation được tạo nhưng thiếu low-cardinality tags, bị leak scope hoặc không kết thúc.

Đề bài **Testing runtime → Test integration graph và observability hook** yêu cầu viết các bài test có thể **chứng minh cấu trúc được nối đúng** và **chứng minh tín hiệu quan sát xuất hiện đúng tại runtime**, mà không phụ thuộc vào một server monitoring thực ngoài mạng.

Một chiến lược hữu ích có ba lớp:

1. **Graph assertions:** `IntegrationGraphServer` có các node/link quan trọng, có đúng đường đi của message và topology được làm mới sau khi đăng ký/xóa flow động.
2. **Behavior assertions:** gửi message thật qua channel, kiểm tra output, error path, trạng thái endpoint, correlation, transaction/retry theo scenario.
3. **Observability assertions:** `ObservationRegistry` và `ObservationHandler` nhận các sự kiện start/stop/error; metric/tracing hook được cấu hình đúng; không có tag cardinality cao trong metrics.

~~~mermaid
flowchart TD
    T["JUnit / Spring Test"] --> G["IntegrationGraphServer.getGraph()"]
    T --> M["MessageChannel.send(message)"]
    T --> O["TestObservationRegistry / custom ObservationHandler"]
    G --> A["Assert nodes + typed links"]
    M --> B["Assert output / failure / lifecycle"]
    O --> C["Assert observation started/stopped, name/tags"]
    A --> R{"Test đạt?"}
    B --> R
    C --> R
    R -->|Có| P["Flow wiring + runtime hooks được kiểm chứng"]
    R -->|Không| D["Chẩn đoán đúng tầng lỗi"]
~~~

**Không đánh đồng:** graph có cạnh `ordersIn -> ordersHandler` không chứng minh handler đã nhận message; metric có timer không chứng minh DB đã commit. Cần kết hợp cả cấu trúc, xử lý thực tế và trạng thái durable resource nếu nghiệp vụ yêu cầu.

## 2. Integration graph là gì?

Spring Integration cung cấp **`IntegrationGraphServer`**, một bean thu thập runtime object model và trả về đối tượng **`Graph`**. Graph không phải bản thiết kế tĩnh: nó được tổng hợp từ các Spring Integration components thực sự có trong `ApplicationContext`.

Ba nhóm thông tin cơ bản:

| Phần graph | API Java dòng Spring Integration 6.x | Vai trò |
| --- | --- | --- |
| `contentDescriptor` | `graph.getContentDescriptor()` | Thông tin provider, application name, format/version |
| `nodes` | `graph.getNodes()` | Channels, endpoints, producers, handlers và metadata |
| `links` | `graph.getLinks()` | Kết nối giữa node IDs, kèm loại liên kết |

Các node kế thừa `IntegrationNode`, trong đó có:

- `getNodeId()`: ID số của node trong graph hiện tại;
- `getName()`: tên component;
- `getComponentType()`: loại component;
- `getProperties()`: thuộc tính quan sát được;
- `isObserved()` (Spring Integration 6.0.1+): cho biết component được instrument qua ObservationRegistry theo trạng thái quản trị.

Mỗi `LinkNode` trong Spring Integration **6.5.x** có `getFrom()`, `getTo()` và `getType()`. Kiểu liên kết có thể là `input`, `output`, `route`, `discard` hoặc `error`.

> **Lưu ý phiên bản:** trên Spring Integration **7.1**, `LinkNode` được biểu diễn dưới dạng Java record với accessor `from()`, `to()`, `type()`, không còn nhất thiết dùng `getFrom()/getTo()/getType()` như code 6.x. Ví dụ test dưới đây có mục tiêu cụ thể là API **Spring Integration 6.5.x**; nếu dự án dùng 7.x, thay các accessor theo Javadoc phiên bản tương ứng.

Một graph minh họa:

~~~text
nodes:
  #11: ordersIn       [channel]
  #12: normalize       [transforming consumer]
  #13: normalizedOrders[channel]
  #14: auditHandler    [service activator]

links:
  11 --input--> 12
  12 --output--> 13
  13 --input--> 14
~~~

Các node IDs `11`, `12` chỉ là ví dụ. **Không hardcode** các ID số này trong test, vì chúng phụ thuộc runtime context/graph rebuild. Hãy tra node ID bằng **component name** ổn định hoặc thuộc tính phù hợp.

## 3. Để graph có giá trị test, đặt tên component ổn định

Khi Spring Integration tự sinh endpoint ID, tên có thể chứa method name, bean name, index hoặc suffix theo cách framework tạo bean. Refactor một method có thể làm test so khớp nguyên chuỗi bị hỏng dù luồng nghiệp vụ vẫn đúng.

Với những endpoint là **contract kiến trúc** cần test, ưu tiên đặt ID tường minh:

~~~java
@Bean
IntegrationFlow orderFlow(OrderService service) {
    return IntegrationFlow.from("ordersIn")
        .transform(String.class, String::trim,
                endpoint -> endpoint.id("trimOrderEndpoint"))
        .handle(service, "process",
                endpoint -> endpoint.id("orderProcessorEndpoint"))
        .get();
}
~~~

Đoạn trên minh họa ý tưởng Java DSL; cần `OrderService`, các imports và đối chiếu overload DSL đúng version đang dùng. Đối với endpoint được sinh từ annotation, hãy kiểm tra tên endpoint thực qua graph hoặc khai báo bean/endpoint rõ ràng khi cần contract ổn định.

**Đặt tên rõ không đồng nghĩa mọi thành phần đều trở thành một node riêng.** Graph builder thể hiện cấu trúc theo loại component thực tế và có thể gộp một handler vào endpoint node. Test nên dựa vào các liên kết đầu vào/đầu ra và những node thực sự được công bố ở version hiện tại.

## 4. Đăng ký và lấy graph trong test

Graph server được cung cấp như một Spring bean:

~~~java
@Bean
IntegrationGraphServer integrationGraphServer() {
    return new IntegrationGraphServer();
}
~~~

Khi context đã refresh, có thể lấy cached graph:

~~~java
Graph graph = integrationGraphServer.getGraph();

Collection<IntegrationNode> nodes = graph.getNodes();
Collection<LinkNode> links = graph.getLinks();
~~~

Nếu có thêm hoặc hủy component sau khi graph đã được tạo, gọi:

~~~java
Graph refreshed = integrationGraphServer.rebuild();
~~~

**`getGraph()` lấy graph cached**; metadata/metrics của node có thể thay đổi theo runtime, nhưng **topology mới thêm/xóa** phải được kiểm tra với `rebuild()` khi thay đổi cấu trúc. `rebuild()` dùng để refresh mô hình, **không** tự start endpoint, tạo subscriber hoặc sửa flow.

Một integration test không nhất thiết phải khởi động web server hoặc bật Actuator:

~~~text
JUnit + Spring ApplicationContext
          |
          +-- IntegrationGraphServer (bean)
          +-- channels, endpoints, handlers
          +-- ObservationRegistry / test hook
~~~

HTTP endpoint `integrationgraph` của Spring Boot Actuator có thể hữu ích cho smoke test deployment, nhưng test tại JVM trực tiếp tránh phải cấu hình remote access, security và port mạng. Actuator exposure là **vấn đề riêng**, không bắt buộc để kiểm tra `Graph` object.

## 5. Assertion graph: tên, ID và liên kết có kiểu

Sai lầm phổ biến:

~~~java
assertTrue(graph.getNodes().size() > 0);
~~~

Ứng dụng có thể có nhiều node mặc định và assertion vẫn pass khi **toàn bộ flow bạn định test bị mất**.

Một test có ích hơn phải xác minh:

1. Node `graphInput` thực sự tồn tại;
2. Node `graphOutput` thực sự tồn tại;
3. Có endpoint nhận input từ `graphInput`;
4. **Chính endpoint đó** phát output đến `graphOutput`.

Ví dụ helper cho Spring Integration **6.5.x**:

~~~java
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.springframework.integration.graph.Graph;
import org.springframework.integration.graph.IntegrationNode;
import org.springframework.integration.graph.LinkNode;

import static org.junit.jupiter.api.Assertions.*;

static void assertFlowPath(
        Graph graph, String inputName, String outputName) {

    Map<String, IntegrationNode> byName = graph.getNodes()
        .stream()
        .collect(Collectors.toMap(
            IntegrationNode::getName,
            Function.identity(),
            (left, right) -> left));

    IntegrationNode input = byName.get(inputName);
    IntegrationNode output = byName.get(outputName);

    assertNotNull(input, "Input node missing: " + inputName);
    assertNotNull(output, "Output node missing: " + outputName);

    Set<Integer> consumers = graph.getLinks().stream()
        .filter(link -> link.getFrom() == input.getNodeId())
        .filter(link -> link.getType() == LinkNode.Type.input)
        .map(LinkNode::getTo)
        .collect(Collectors.toSet());

    assertFalse(consumers.isEmpty(),
        "No consumer connected to " + inputName);

    boolean pathExists = graph.getLinks().stream()
        .filter(link -> link.getTo() == output.getNodeId())
        .filter(link -> link.getType() == LinkNode.Type.output)
        .anyMatch(link -> consumers.contains(link.getFrom()));

    assertTrue(pathExists,
        inputName + " has no consumer writing to " + outputName);
}
~~~

Helper cố tình không hardcode numeric node IDs. Nó **không tự tìm mọi đường đi nhiều hop**; mục tiêu là một transformer/handler ở giữa hai channels. Nếu flow có `router -> queue -> poller -> handler`, cần thuật toán duyệt graph theo typed edges tương ứng.

**Phân biệt đầu vào/đầu ra:** một link `input` thường nối **channel → endpoint**, còn `output` nối **endpoint → channel**. Kiểm tra `from/to` phải theo chiều link được graph công bố, không suy từ tên biến.

### Khi nào test cần nhìn cả `route`, `discard`, `error`?

| Kiểu link | Ví dụ flow | Assertion quan trọng |
| --- | --- | --- |
| `input` | `ordersIn → transformer` | Consumer được nối vào đúng channel |
| `output` | `transformer → normalizedOrders` | Output channel được cấu hình |
| `route` | `@Router` có nhiều nhánh | Có đường tới mỗi channel nghiệp vụ cần thiết |
| `discard` | Filter hoặc idempotent receiver | Có discard sink thực, không nuốt message ngoài chủ đích |
| `error` | Poller/adapter có error channel | Error path được wire đúng theo component hỗ trợ |

Trong vài trường hợp, một adapter/endpoint không biểu diễn mọi đường đi động bằng static graph. Ví dụ handler tự gọi `MessageChannel.send()` được resolve ở runtime có thể không hiện output link như một `AbstractReplyProducingMessageHandler` có output channel cấu hình. **Không được suy tính đúng sai nghiệp vụ chỉ từ graph** trong tình huống topology dynamic hoặc custom routing.

## 6. Micrometer Observation: hook khác integration graph

Từ Spring Integration **6.0**, framework hỗ trợ **Micrometer Observation API**. Mỗi Observation có context, name, low/high cardinality key values và các lifecycle callbacks được phân phối tới `ObservationHandler` tương ứng.

Khi Spring Integration cần instrument những `IntegrationManagement` components:

1. Có bean **`ObservationRegistry`** trong application context.
2. Bật `@EnableIntegrationManagement`.
3. Cấu hình `observationPatterns` để chọn component cần instrument.
4. Có `ObservationHandler` phù hợp để thật sự **thu thập test observations, metrics hoặc trace spans**.

**Rất dễ bỏ sót:** chỉ khai báo một bean `ObservationRegistry` **chưa đủ**; trong Spring Integration, mặc định **không** instrument mọi management component nếu không chọn observation patterns. Trong test có thể đặt `"*"` để bao toàn bộ, còn production nên chọn vừa đủ.

~~~java
@Configuration
@EnableIntegration
@EnableIntegrationManagement(observationPatterns = "*")
class ObservationConfig {

    @Bean
    ObservationRegistry observationRegistry() {
        return ObservationRegistry.create();
    }
}
~~~

**Nhưng** `ObservationRegistry.create()` mặc định **không tự xuất Prometheus metrics hoặc trace spans** khi chưa đăng ký ObservationHandler thích hợp. Để test trực tiếp, hãy dùng `TestObservationRegistry` từ `micrometer-observation-test` hoặc tự cài custom `ObservationHandler`.

### Phân biệt ba thứ dễ nhầm

| Cơ chế | Mục đích | Có bằng chứng test nào? |
| --- | --- | --- |
| `IntegrationGraphServer` | Kiểm tra topology: nodes/links | Node/link assertions |
| `ObservationRegistry` + `ObservationHandler` | Kiểm tra hoạt động observability hooks | Observation được start/stop/error, tên và tags |
| `MeterRegistry` + meter observation handler | Kiểm tra metrics thực như timer/counter | Meter/timer xuất hiện trong registry, sample count tăng |

**Đừng** assert một metric trong `SimpleMeterRegistry` nếu chỉ có `TestObservationRegistry` và chưa cấu hình meter ObservationHandler; khi đó test không có lý do để thấy timer.

## 7. Instrumented components và tên observation

Tài liệu Spring Integration 6.x liệt kê các loại component đáng chú ý:

- `AbstractMessageChannel.send()`: producer observation;
- `AbstractMessageHandler`: handler/consumer observation;
- `MessageProducerSupport`: inbound producer được quan sát ở phía nhận;
- `MessagingGatewaySupport`: gateway/request-reply observation;
- `SourcePollingChannelAdapter`: từ Spring Integration **6.5**, có observation support ở polling inbound.

Một số tên observation tiêu biểu:

| Tên | Phạm vi | Lưu ý |
| --- | --- | --- |
| `spring.integration.producer` | Channel send/message producer | Thường dùng khi assert channel `send()` |
| `spring.integration.handler` | Message handler | Có thể không áp dụng cho handler lambda không phải `AbstractMessageHandler` |
| `spring.integration.gateway` | Messaging gateway | Không luôn hiện nếu test không đi qua gateway |

Tên/tag chính xác phụ thuộc **convention và phiên bản**. Tài liệu metric sử dụng các low-cardinality key như `spring.integration.name` và `spring.integration.type`. Không nhầm observation name với export name của Prometheus có thể được hệ thống chuyển đổi.

### Observed vs managed

`IntegrationNode.isObserved()` được công bố từ Spring Integration 6.0.1, dùng để xem component có được instrument bằng ObservationRegistry hay không. Đây là **tín hiệu cấu hình**, chưa chứng minh đã có một observation được start/stop trong test.

Một bài test nên có hai bước:

~~~text
Graph node isObserved?  -> instrument flag/management configuration
Send message            -> actual ObservationHandler recorded event?
~~~

Nếu node `isObserved()` true mà không có sample, có thể test chưa gửi qua component, chưa có subscriber, hoặc registry handler không thu thập được dữ liệu.

## 8. Dùng TestObservationRegistry để test không phụ thuộc monitoring server

Micrometer cung cấp artifact **`micrometer-observation-test`** cho test scope. `TestObservationRegistry` có sẵn handler lưu observations và validator kiểm tra lifecycle hợp lệ.

Dependency mẫu Gradle (chỉ để người học tham khảo, **không chạy Gradle trong STEP 4**):

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-integration")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.micrometer:micrometer-observation-test")
}
~~~

Các dependency version nên đi theo BOM tương thích Spring Boot/Spring Integration của dự án. Nếu chưa dùng BOM, cần pin version rõ; không trộn tùy tiện Micrometer 1.x/2.x với Spring Framework khác đời.

Một test observation độc lập với Spring Integration để hiểu API:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistryAssert;

TestObservationRegistry registry = TestObservationRegistry.create();

Observation.createNotStarted("order.validate", registry)
    .lowCardinalityKeyValue("operation", "validate")
    .observe(() -> {
        // Logic được instrument
    });

TestObservationRegistryAssert.assertThat(registry)
    .doesNotHaveAnyRemainingCurrentObservation()
    .hasObservationWithNameEqualTo("order.validate")
    .that()
    .hasLowCardinalityKeyValue("operation", "validate")
    .hasBeenStarted()
    .hasBeenStopped();
~~~

Đây là đoạn minh họa đặt trong một JUnit test method. Nó chứng minh test registry hoạt động, **không** chứng minh Spring Integration instrumentation đã được bật. Để kiểm tra integration hook thực tế, phải gửi qua **channel/handler do Spring Integration quản lý**.

## 9. Ví dụ tích hợp: JUnit test graph và observation trong một context

Ví dụ nhắm tới **Java 17+, Spring Integration 6.5.x, Spring Framework 6.x, JUnit 5 và Micrometer Observation 1.x**. Đặt toàn bộ vào file test `RuntimeGraphObservationTest.java` trong package `demo.integration`.

Ví dụ tạo:

- `DirectChannel` tên `graphInput`;
- `QueueChannel` tên `graphOutput`;
- Một transformer xử lý `"hello"` thành `"HELLO"`;
- `IntegrationGraphServer` để kiểm tra nodes/links;
- `TestObservationRegistry` và `@EnableIntegrationManagement(observationPatterns = "*")` để thu nhận observations.

~~~java
package demo.integration;

import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

import io.micrometer.observation.tck.TestObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistryAssert;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.Transformer;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.config.EnableIntegrationManagement;
import org.springframework.integration.graph.Graph;
import org.springframework.integration.graph.IntegrationGraphServer;
import org.springframework.integration.graph.IntegrationNode;
import org.springframework.integration.graph.LinkNode;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(RuntimeGraphObservationTest.Config.class)
class RuntimeGraphObservationTest {

    @Autowired
    private IntegrationGraphServer graphServer;

    @Autowired
    @Qualifier("graphInput")
    private MessageChannel input;

    @Autowired
    @Qualifier("graphOutput")
    private PollableChannel output;

    @Autowired
    private TestObservationRegistry observations;

    @BeforeEach
    void clearObservations() {
        observations.clear();
    }

    @Test
    void graphContainsWiredInputAndOutput() {
        Graph graph = graphServer.getGraph();

        Map<String, IntegrationNode> nodes = graph.getNodes()
            .stream()
            .collect(Collectors.toMap(
                IntegrationNode::getName,
                Function.identity(),
                (a, b) -> a));

        IntegrationNode in = nodes.get("graphInput");
        IntegrationNode out = nodes.get("graphOutput");

        assertNotNull(in, "graphInput node missing");
        assertNotNull(out, "graphOutput node missing");

        Set<Integer> consumers = graph.getLinks()
            .stream()
            .filter(l -> l.getFrom() == in.getNodeId())
            .filter(l -> l.getType() == LinkNode.Type.input)
            .map(LinkNode::getTo)
            .collect(Collectors.toSet());

        assertFalse(consumers.isEmpty(),
            "No input consumer connected to graphInput");

        boolean outputConnected = graph.getLinks()
            .stream()
            .filter(l -> l.getTo() == out.getNodeId())
            .filter(l -> l.getType() == LinkNode.Type.output)
            .anyMatch(l -> consumers.contains(l.getFrom()));

        assertTrue(outputConnected,
            "Transformer does not send to graphOutput");
    }

    @Test
    void sendsMessageAndPublishesObservation() {
        boolean accepted = input.send(
            MessageBuilder.withPayload("hello").build());

        assertTrue(accepted);

        Message<?> response = output.receive(1_000);
        assertNotNull(response, "No reply on graphOutput");
        assertEquals("HELLO", response.getPayload());

        // Channel send là một operation được SI instrument.
        TestObservationRegistryAssert.assertThat(observations)
            .doesNotHaveAnyRemainingCurrentObservation()
            .hasObservationWithNameEqualTo(
                "spring.integration.producer")
            .that()
            .hasBeenStarted()
            .hasBeenStopped();
    }

    @Configuration
    @EnableIntegration
    @EnableIntegrationManagement(observationPatterns = "*")
    static class Config {

        @Bean
        IntegrationGraphServer integrationGraphServer() {
            return new IntegrationGraphServer();
        }

        @Bean
        TestObservationRegistry observationRegistry() {
            return TestObservationRegistry.create();
        }

        @Bean("graphInput")
        MessageChannel graphInput() {
            return new DirectChannel();
        }

        @Bean("graphOutput")
        PollableChannel graphOutput() {
            return new QueueChannel();
        }

        @Bean
        UppercaseTransformer uppercaseTransformer() {
            return new UppercaseTransformer();
        }
    }

    @MessageEndpoint
    static class UppercaseTransformer {

        @Transformer(
            inputChannel = "graphInput",
            outputChannel = "graphOutput")
        public String upper(String payload) {
            return payload.toUpperCase(java.util.Locale.ROOT);
        }
    }
}
~~~

### Tại sao cần cả hai test?

- `graphContainsWiredInputAndOutput()` kiểm tra **topology**: channel thực sự có đường tới endpoint và endpoint trả ra output.
- `sendsMessageAndPublishesObservation()` kiểm tra **behavior** và **instrumentation**: có một message `"HELLO"` thực sự đi vào queue, và registry thấy producer observation.
- Test không cần Prometheus, Zipkin hoặc OpenTelemetry collector.
- `QueueChannel.receive(1_000)` dùng **timeout hữu hạn**, không chờ vô thời hạn.
- `@BeforeEach observations.clear()` ngăn observations từ test trước gây false positive.

**Cần chú ý:** `@EnableIntegrationManagement(observationPatterns = "*")` bật observation cho các component mà Integration Management có thể instrument. Nếu một component bị loại bởi pattern khác hoặc một test harness custom thay hẳn component, assertion cần điều chỉnh theo wiring thật.

### Các chi tiết version đáng lưu ý

Ví dụ dùng accessors của `LinkNode` trong **6.5.x**. Với **Spring Integration 7.1**, chuyển:

~~~java
link.getFrom()   // 6.x
link.getTo()     // 6.x
link.getType()   // 6.x

link.from()      // 7.1 record
link.to()        // 7.1 record
link.type()      // 7.1 record
~~~

Không trộn cả hai bộ phương thức trong một code target. Những assertions khác (`Graph.getNodes()`, `IntegrationNode.getName()`, `getNodeId()`) có thể giữ nguyên theo Javadoc được kiểm tra.

**Không chạy bài học bằng cách suy rằng code đã được CI xác nhận:** trong STEP 4, tài liệu được author, chưa chạy build/test và chưa qua Content QA học thuật. Trong môi trường dự án, pin version BOM rồi chạy test để xác nhận wiring theo dependency thực tế.

## 10. Test hook độc lập: custom ObservationHandler

`TestObservationRegistry` giúp assert name/tags, nhưng đôi khi bạn cần kiểm tra **hook do ứng dụng tự cài** — ví dụ đếm observation start/stop và ghi telemetry audit. Có thể tự triển khai `ObservationHandler<Observation.Context>`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;

final class CountingObservationHandler
        implements ObservationHandler<Observation.Context> {

    private final AtomicInteger starts = new AtomicInteger();
    private final AtomicInteger stops = new AtomicInteger();
    private final AtomicInteger errors = new AtomicInteger();

    @Override
    public boolean supportsContext(Observation.Context context) {
        return true;
    }

    @Override
    public void onStart(Observation.Context context) {
        starts.incrementAndGet();
    }

    @Override
    public void onStop(Observation.Context context) {
        stops.incrementAndGet();
    }

    @Override
    public void onError(Observation.Context context) {
        errors.incrementAndGet();
    }

    public int starts() {
        return starts.get();
    }

    public int stops() {
        return stops.get();
    }

    public int errors() {
        return errors.get();
    }

    public void reset() {
        starts.set(0);
        stops.set(0);
        errors.set(0);
    }
}
~~~

Đăng ký handler này với `TestObservationRegistry` trước khi gửi message:

~~~java
CountingObservationHandler hook =
        new CountingObservationHandler();

TestObservationRegistry registry =
        TestObservationRegistry.create();

registry.observationConfig().observationHandler(hook);

// Thực thi operation được instrument.
Observation.createNotStarted("test.operation", registry)
        .observe(() -> { });

assertEquals(1, hook.starts());
assertEquals(1, hook.stops());
assertEquals(0, hook.errors());
~~~

Trong test Spring Integration, có thể biến hook thành bean và đăng ký lên registry trong cấu hình test, rồi reset counters **trước** lần gửi message. Khi hai handler cùng nhận observations (hook và TestObservationRegistry handler), không nên giả định thứ tự callback giữa các handler là business contract.

### Testing start/stop/error có điều kiện

| Hook callback | Khi nào xảy ra | Nên assert gì? |
| --- | --- | --- |
| `onStart` | Observation bắt đầu | Có invocation khi message đi qua component |
| `onStop` | Observation kết thúc | Không leak observation; counter kết thúc |
| `onError` | Code gọi `Observation.error(ex)` | Có đánh dấu lỗi theo convention đang dùng |
| `onEvent` | Có observation event được phát | Event name và context khi ứng dụng chủ động thêm event |
| `onScopeOpened` / `onScopeClosed` | Scope được mở/đóng | Lifecycle đúng trong async/threading scenario |

**Không mặc định mọi Java exception tự làm `onError` tăng** nếu instrumentation scope không gọi `Observation.error(...)`. Với custom hook test, tạo lỗi cố tình rồi kiểm tra thực tế loại observation hỗ trợ của phiên bản đang dùng.

## 11. Graph node isObserved() không thay được runtime hook assertion

Trong graph, `IntegrationNode.isObserved()` cho biết component tương ứng có được instrument với observation registry không, nhưng:

~~~text
isObserved == true
    ≠ đã phát sample
    ≠ trace được export
    ≠ metric timer đã tăng
    ≠ message đã xử lý thành công
~~~

Có thể kiểm tra:

~~~java
Graph graph = graphServer.getGraph();

IntegrationNode channel = graph.getNodes()
        .stream()
        .filter(node -> "graphInput".equals(node.getName()))
        .findFirst()
        .orElseThrow();

assertTrue(channel.isObserved());
~~~

Với Spring Integration 6.0.1+ và `observationPatterns` bao component. Tuy nhiên khi dùng test metadata khác version hoặc `ObservationRegistry.NOOP`, trạng thái này có thể không như mong đợi. Nếu assertion fail, kiểm tra configurer/pattern/registry thay vì tăng timeout một cách vô hạn.

Tách hai vấn đề:

1. **Được instrument?** Dựa vào `isObserved()` và config.
2. **Thực sự được gọi?** Dựa vào `TestObservationRegistry` hoặc custom `ObservationHandler`.

## 12. Testing link graph: tránh brittle tests

### 12.1. Đừng snapshot toàn bộ graph mà không kiểm soát

Graph có thể chứa nhiều default components như `errorChannel`, `nullChannel`, internal error logger và những beans do auto configuration thêm. Một snapshot so sánh toàn bộ JSON có thể hỏng mỗi khi framework đổi metadata hoặc thay package version, dù nghiệp vụ không hề sai.

Nên kiểm tra theo **contract kiến trúc**:

~~~text
MUST: graphInput exists
MUST: graphOutput exists
MUST: a consumer connects graphInput to graphOutput
MUST: error recovery path exists if business contract requires it

MAY: extra default nodes
MAY: additional metrics properties
MAY: different numeric nodeIds
~~~

### 12.2. Không chỉ kiểm tra node names

Node tồn tại mà không có link vẫn có thể là channel **không được nối**. Với flow có router:

- Assert có input link từ source channel đến router.
- Assert route/discard/error links cho các nhánh bắt buộc.
- Gửi message để test **route được chọn thực tế** theo header/payload.
- Với dynamic route được resolve runtime, graph có thể không mô tả đầy đủ mọi đích động.

### 12.3. Tách behavior khi topology phức tạp

Một path có nhiều hops:

~~~mermaid
flowchart LR
    I["ordersIn"] --> R["Router"]
    R -->|priority| Q1["priorityQueue"]
    R -->|normal| Q2["regularQueue"]
    Q1 --> P1["Priority poller"]
    Q2 --> P2["Regular poller"]
    P1 --> H["Handler"]
    P2 --> H
    H --> O["results"]
~~~

Từ graph, có thể viết thuật toán BFS/DFS trên `nodeId` và typed links. Tuy nhiên test tuyến đi của message **không thể chỉ BFS**: router chọn nhánh dựa vào dữ liệu, poller phụ thuộc trigger và handler có thể throw. Một graph path là **kết nối có thể tồn tại**, không phải chứng minh mọi input chạy qua path đó.

## 13. Graph runtime và flow đăng ký động

Spring Integration hỗ trợ `IntegrationFlowContext` để đăng ký/hủy flow trong lúc application đang chạy. Đối với graph, phải làm mới topology sau thay đổi:

~~~java
IntegrationFlowContext.IntegrationFlowRegistration registration =
        flowContext.registration(newFlow)
                .id("tenantAFlow")
                .autoStartup(false)
                .register();

Graph newGraph = graphServer.rebuild();

// Assert các node/links do tenantAFlow tạo đã hiện diện.

registration.start();
// Test message flow và observation hooks.

registration.stop();
registration.destroy();

Graph afterRemoval = graphServer.rebuild();

// Assert component đã hủy biến mất nếu không dùng chung.
~~~

Đây là **snippet minh họa**; `flowContext` là bean `IntegrationFlowContext`, `newFlow` là Java DSL flow được xây hợp lệ và imports cần bổ sung. Khi hủy flow, các bean/channel dùng chung với flow khác không nhất thiết bị xóa; test không được assert tất cả dependencies biến mất nếu chúng vẫn được dùng.

### Những điều nên assert

| Thời điểm | Graph test | Behavior/observation test |
| --- | --- | --- |
| Trước registration | Node flow mới chưa tồn tại | Không có consumer mới |
| Sau registration + `rebuild()` | Node/link đã tạo xuất hiện | Endpoint có thể chưa chạy do `autoStartup=false` |
| Sau `start()` | Node vẫn tồn tại | Message thực sự xử lý; observations xuất hiện |
| Sau `stop()` | Node có thể vẫn còn trong graph | Message mới không được xử lý bởi endpoint đã dừng |
| Sau `destroy()` + `rebuild()` | Node riêng của flow biến mất | Không còn subscription/side effect của flow cũ |

**Stop không đồng nghĩa destroy**, và graph có node không chứng minh endpoint đang running. `IntegrationGraphServer` có callback thêm properties, nên có thể bổ sung `SmartLifecycle.isRunning()` cho diagnostics, nhưng **đừng mặc định mọi node có thuộc tính `"running"`** khi chưa cấu hình.

## 14. Thêm thuộc tính lifecycle vào graph để test

`IntegrationGraphServer.setAdditionalPropertiesCallback(...)` cho phép thêm metadata của `NamedComponent` vào node. Ví dụ:

~~~java
@Bean
IntegrationGraphServer integrationGraphServer() {
    IntegrationGraphServer server = new IntegrationGraphServer();

    server.setAdditionalPropertiesCallback(component -> {
        if (component instanceof SmartLifecycle lifecycle) {
            return Map.of(
                "running", lifecycle.isRunning(),
                "autoStartup", lifecycle.isAutoStartup());
        }

        return Map.of();
    });

    return server;
}
~~~

Cần import `org.springframework.context.SmartLifecycle` và `java.util.Map`. Đây là cách quan sát state được công bố qua graph, không phải thay đổi chính lifecycle. Một application có thể cần quyền quản trị để gọi `start/stop`, còn graph chỉ hiển thị.

Test:

~~~java
IntegrationNode endpoint = graphServer.getGraph().getNodes()
        .stream()
        .filter(node -> "orderPollingEndpoint".equals(node.getName()))
        .findFirst()
        .orElseThrow();

assertEquals(Boolean.TRUE,
        endpoint.getProperties().get("running"));
~~~

**Chú ý caching:** graph có thể cache node/metadata; `getGraph()` giữ topology cache, nhưng tài liệu cho biết những stats trong graph có thể dynamic. Với custom properties callback, để chắc chắn test sau thay đổi structural/lifecycle, hãy dùng `rebuild()` và kiểm tra behavior thực. Không tự suy mọi custom property được refresh live theo cùng quy tắc.

## 15. Test Message History bên cạnh observation

Message History và Micrometer Observation giải quyết hai câu hỏi khác nhau:

| Cơ chế | Dấu vết | Hạn chế |
| --- | --- | --- |
| `MessageHistory` | Những component được track đã đi qua | Header có thể dài, không chứng minh commit |
| `Observation` | Một operation start/stop/error, timers/spans theo conventions | Không tự lưu toàn bộ tuyến đường dưới dạng history |
| `IntegrationGraphServer` | Topology đang được cấu hình | Không nói message đã đi qua nhánh nào |
| Logs/traces | Context và diễn biến sự cố | Phải có propagation/retention hợp lý |

Có thể bật `@EnableMessageHistory` trong test rồi kiểm tra:

~~~java
Message<?> message = output.receive(1_000);

MessageHistory history = MessageHistory.read(message);
assertNotNull(history);

boolean passedThroughInput = history.stream()
    .anyMatch(properties ->
        "graphInput".equals(properties.getProperty(
            MessageHistory.NAME_PROPERTY)));

assertTrue(passedThroughInput);
~~~

Đoạn này áp dụng khi `graphInput` nằm trong tập tracked components và output message giữ header history. Cần import `org.springframework.integration.history.MessageHistory` và cấu hình `@EnableMessageHistory` theo tên component thật. **Không hardcode số entries**: số hop phụ thuộc framework, handler và tracking pattern.

Chú ý từ Spring Integration 6.3, Message History có cách append-only/clone ở fan-out. Test splitter/router custom cần bảo đảm histories của hai nhánh **không lẫn** nhau nếu mỗi nhánh tiếp tục qua các component khác nhau.

## 16. Test metrics qua SimpleMeterRegistry: đừng nhầm với TestObservationRegistry

`TestObservationRegistry` ghi nhận observation lifecycle. Nếu mục tiêu là assertion **timer/count**, cần `MeterRegistry` và `ObservationHandler` chuyển observation thành meters.

Ví dụ Micrometer cơ bản:

~~~java
SimpleMeterRegistry meterRegistry = new SimpleMeterRegistry();
ObservationRegistry observationRegistry = ObservationRegistry.create();

observationRegistry.observationConfig()
    .observationHandler(
        new DefaultMeterObservationHandler(meterRegistry));

Observation.createNotStarted("demo.operation", observationRegistry)
    .lowCardinalityKeyValue("component", "test")
    .observe(() -> { });

Timer timer = meterRegistry.find("demo.operation").timer();

assertNotNull(timer);
assertEquals(1L, timer.count());
~~~

Cần import `io.micrometer.core.instrument.simple.SimpleMeterRegistry`, `io.micrometer.core.instrument.Timer`, `io.micrometer.observation.Observation`, `io.micrometer.observation.ObservationRegistry`, `io.micrometer.core.instrument.observation.DefaultMeterObservationHandler`, và JUnit assertions. Ví dụ cần dependencies `micrometer-core`/`micrometer-observation` tương thích.

**Điều kiện then chốt:** meter handler được đăng ký. Nếu chỉ gọi `ObservationRegistry.create()` mà không có handler, việc observation start/stop **không tự sinh timer**.

Trong Spring Integration, còn có cơ chế metrics captor trước đây. Khi một `ObservationRegistry` được cung cấp, `IntegrationManagement` ưu tiên observation và có thể bỏ qua `MetricsCaptor` riêng. Đừng assert cùng một metric được ghi từ cả hai đường mà không hiểu version và management config.

## 17. Error path: assert exception, ErrorMessage và hook ở đúng boundary

Ba kiểu lỗi thường gặp:

| Lỗi xảy ra tại | Cách nó lộ ra | Test gì? |
| --- | --- | --- |
| `DirectChannel`/handler đồng bộ | Exception tới `send()` nếu không bị nuốt | `assertThrows`, resource rollback |
| Poller/`ExecutorChannel` | Worker/poller error handler có thể publish `ErrorMessage` | Bounded await cho error channel, original/failed message |
| Reactive publisher | `onError` terminal signal | `StepVerifier` hoặc subscriber; không mặc định có ErrorMessage |

Ví dụ exception đồng bộ:

~~~java
RuntimeException thrown = assertThrows(
        RuntimeException.class,
        () -> input.send(MessageBuilder
                .withPayload("force-error")
                .build()));

assertNotNull(thrown);
~~~

Đây là assertion cho một handler đã được **cấu hình ném lỗi** khi payload `"force-error"` tới. Nó không áp dụng trực tiếp cho flow test ở mục 9 vì transformer ở đó chỉ uppercase.

### Assert ErrorMessage trên error channel

~~~java
Message<?> error = errors.receive(2_000);
assertNotNull(error);
assertInstanceOf(ErrorMessage.class, error);

Throwable cause = ((ErrorMessage) error).getPayload();
assertNotNull(cause);
~~~

Cần `errors` là **pollable error channel** đã được adapter/poller/worker cấu hình thực sự gửi lỗi đến đó. Đừng mong global `errorChannel` luôn nhận exception đồng bộ của một `DirectChannel` mà không có publishing boundary.

### Observation error hook

Không giả định `TestObservationRegistry` tăng một counter tên `errors` bất kể exception nào. Để test lỗi, cần biết component instrumentation có gọi `Observation.error(ex)` hay không, có đưa exception qua recovery trước khi observation kết thúc không, và tên/tag convention của version. Trong integration test, nếu quan sát đúng event:

~~~java
assertTrue(hook.errors() > 0);
~~~

Assertion này chỉ hợp lệ khi `hook` đã được cài vào cùng `ObservationRegistry`, và component/adapter ở test thực sự report error cho observation. Nếu sai, điều tra **observation boundary** trước khi sửa bằng cách tăng sleep.

## 18. Async: test không ngủ cố định

### Sai lầm phổ biến

~~~java
input.send(message);
Thread.sleep(2_000);
assertEquals(1, counter.get());
~~~

Ở máy nhanh sẽ lãng phí thời gian; ở CI chậm vẫn có thể flake. Ngoài ra, một handler xong sau 2 giây nhưng transaction/ack chưa commit cũng làm assertion trở nên sai.

### Dùng QueueChannel receive timeout

~~~java
Message<?> result = results.receive(2_000);
assertNotNull(result, "Message not processed within bounded wait");
~~~

Với `QueueChannel`, đây là cách đơn giản để đợi **message thực sự đến**. Test nên có finite timeout và trạng thái rõ khi timeout.

### Dùng Awaitility hoặc điều kiện polling

Nếu kết quả được ghi vào `AtomicInteger`/DB thay vì queue:

~~~java
await()
    .atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertEquals(3, processedCounter.get()));
~~~

Cần dependency Awaitility trong test và import `org.awaitility.Awaitility.await`, `java.time.Duration`. Hãy kiểm tra business state ổn định (DB row, idempotency marker) thay vì chỉ đợi một log line.

### Khi bật mock clock?

Với Reactor có `StepVerifier.withVirtualTime` có thể kiểm tra retry/backoff theo virtual scheduler. Nhưng poller Spring Integration dùng trigger/task scheduler riêng; **không giả định** Reactor virtual time điều khiển poller thực. Với poller, cân nhắc test trigger deterministic, mock source hoặc giới hạn thời gian bằng một scheduler/integration test có kiểm soát.

## 19. Spring Integration testing support và mock endpoints

Artifact `spring-integration-test` và `spring-integration-test-support` cung cấp tiện ích:

- `MockIntegrationContext` để thay message source/handler trong endpoint đang cấu hình;
- `MockIntegration` để tạo stub/mock MessageSource, MessageHandler, MessageChannel;
- Các helper cho test message flow không gọi external dependencies.

Ví dụ cấu trúc (cần context test đã cấu hình):

~~~java
mockIntegrationContext.substituteMessageHandlerFor(
    "remoteRequestEndpoint",
    MockIntegration.mockMessageHandler()
        .handleNext(message -> captured.add(message)));
~~~

**Đây là snippet minh họa, không phải bài test standalone.** Cần xem signature overload và Mockito/static imports phù hợp đúng phiên bản test module. Bài test nên xác nhận **endpoint ID** của target, không dùng tên tùy đoán.

Đừng thay real handler bằng mock rồi vẫn khẳng định đã test instrumentation của **real handler**: một mock không phải `AbstractMessageHandler` có thể không phát cùng observation; khi kiểm tra topology/management hãy test ít nhất một đường thật.

### So sánh hai kiểu test

| Test type | Ưu điểm | Khi dùng |
| --- | --- | --- |
| Unit test handler/service | Nhanh, kiểm tra business rules | Nhiều edge cases |
| Spring Integration context test với stub adapter | Kiểm tra channel, advice, graph, observations | Wires và policies |
| Embedded/real broker, DB (Testcontainers) | Kiểm tra ack, transaction, store, redelivery | End-to-end reliability |
| Deployment smoke test với Actuator graph | Kiểm tra topology của artifact chạy thật | Sau rollout |
| Load/chaos test | Kiểm tra executor, poller, retry storm | Non-functional/SLA |

**Một test graph-only không thể thay cho integration test nghiệp vụ**, và một test unit handler-only không chứng minh topology thật.

## 20. Poller, executor và observation hook

### Poller test

Với `QueueChannel`/message source + `PollingConsumer`, cần assert:

1. Endpoint đã `isRunning()` đúng.
2. Có message thật được poll và tới handler.
3. Sau `stop()`, không poll thêm message mới (sau khi in-flight drain theo contract).
4. Có metric/observation trên những component được instrument ở version ứng dụng.
5. Khi handler throw, error flow đúng và source/store rollback/redelivery nếu được thiết kế.

**Version caveat:** Spring Integration 6.5 bổ sung observation cho `SourcePollingChannelAdapter`; không phải mọi loại poller có cùng observation hook trên mọi phiên bản. Nếu muốn kiểm tra poller duration, nên đo qua instrumented component cụ thể hoặc custom hook đáng tin cậy của test.

### ExecutorChannel test

~~~mermaid
sequenceDiagram
    participant Test as Test thread
    participant Ex as ExecutorChannel
    participant W as Worker thread
    participant Reg as ObservationRegistry
    Test->>Ex: send(Message)
    Ex-->>Test: handoff accepted
    Ex->>W: deliver
    W->>Reg: Observation start
    W->>W: handler process
    W->>Reg: Observation stop/error
    W-->>Test: result through QueueChannel / DB marker
~~~

Không assert observation ngay sau `send()` nếu handler chạy ở worker khác: quan sát có thể chưa hoàn tất. Đợi **tín hiệu end-to-end** trước (reply, DB state, bounded latch), rồi mới kiểm tra hook. Nếu observation handler `onStop` chạy sau khi output đã được enqueue, đôi khi vẫn cần bounded wait riêng cho sample completion.

### Context propagation

`Observation` scope có thể liên quan ThreadLocal và tracing context. Qua executor, thread không tự mang mọi context của caller; phải cấu hình task decorator/context propagation phù hợp. Test không được chỉ kiểm tra tên observation rồi kết luận trace parent-child được nối đúng.

Dùng `traceId` trong message headers cho correlation và kiểm chứng trace propagation ở adapter cụ thể. Với Reactor dùng `Reactor Context` và tracing integration của stack đang dùng, không cố sao chép ThreadLocal thủ công.

## 21. Retry, transaction, message store và correlation

**Observability hook được gọi không chứng minh business transaction thành công.**

Ví dụ một handler:

~~~text
Message received
  -> Observation start
  -> JDBC INSERT
  -> handler throws
  -> Transaction rollback
  -> Observation error/stop
  -> broker redelivery (nếu adapter cấu hình)
~~~

Test nên assert từng tầng:

| Điều cần chứng minh | Assertion nên dùng |
| --- | --- |
| Endpoint/flow được nối đúng | Graph nodes + links |
| Handler đã được gọi | Output queue hoặc spy counter |
| Retry xảy ra đúng số attempts | Retry callback/counter, không suy từ graph |
| DB rollback | Truy vấn row sau transaction kết thúc |
| Broker redelivery | Ack/nack, deliveries trong broker test |
| Correlation không mất | `eventId`, `correlationId`, sequence headers |
| ErrorMessage đúng | Error channel nhận original/failed message |
| Observability hook hoạt động | Registry recorded start/stop/error |
| Message được persist an toàn | Readback từ message store sau restart |

Một retry advice có thể gọi handler nhiều lần nhưng **không** tạo nhiều observation samples đúng bằng attempt count nếu observation nằm ngoài retry scope. Ví dụ observation bao endpoint có thể ghi một sample cho cả chuỗi retry, trong khi handler được gọi ba lần. Muốn đo attempts, instrument tại đúng retry callback hoặc handler invocation.

### Message store test

Với durable `QueueChannel` hoặc `MessageGroupStore`, graph chỉ cho biết component **có tồn tại và nối với nhau**. Nó không chứng minh bytes trong store có thể đọc lại sau restart, correlation group release hay retry idempotency. Cần persistence test riêng và kiểm tra serializer/versioning.

### LockRegistry và hiệu năng

Aggregator có thể bị chậm vì `LockRegistry` contention theo `correlationId`. Một graph hợp lệ và observations có sample vẫn không nói critical section bị nghẽn ở đâu. Dùng lock wait/hold metrics, group size/age, database waits và message history để chẩn đoán.

## 22. Test custom observation convention, tags và privacy

Tài liệu Spring Integration cho phép tùy biến `ObservationConvention` trên component hỗ trợ, ví dụ `AbstractMessageHandler.setObservationConvention(...)` với `MessageReceiverObservationConvention` thích hợp.

Bài test nên kiểm tra:

- **Low cardinality**: tên endpoint/loại operation, trạng thái `success/failure`, không đưa event ID duy nhất thành tag.
- **High cardinality**: eventId/traceId được đưa vào trace attributes khi thích hợp, không đẩy thẳng vào time-series metrics.
- Không log payload, token, thông tin cá nhân hoặc endpoint URL bí mật ra telemetry.
- Error sampling và failure tags không tạo ra hàng triệu unique label combinations.

Ví dụ test assertion cho custom observation:

~~~java
TestObservationRegistryAssert.assertThat(registry)
    .hasObservationWithNameEqualTo("order.validate")
    .that()
    .hasLowCardinalityKeyValue("operation", "validate")
    .hasBeenStarted()
    .hasBeenStopped();
~~~

Không hardcode `order.validate` là tên mặc định Spring Integration; đây là **custom observation của ứng dụng**. Với framework-managed observation, tham khảo tên/convention mà version thực tế công bố.

## 23. Test dynamic graph refresh và topology drift

Một regression khó phát hiện là **drift**: cùng một tên flow nhưng bean wiring khác sau refactor hoặc starter update.

Kỹ thuật có ích:

1. Định nghĩa một tập **invariants**: input/output/route/error channel quan trọng phải hiện diện.
2. Snapshot **chọn lọc**: component names/types và các links liên quan, không snapshot tất cả default nodes.
3. Chạy test trên profile staging tương ứng production.
4. Đăng ký và hủy dynamic flow, gọi `rebuild()` sau mỗi thay đổi.
5. Xác minh không còn orphan handlers/subscribers sau `destroy()`.
6. Nếu graph diff thay đổi, review đây là thay đổi được phép hay regression.
7. Trong deployment smoke test, so sánh graph **sau context refresh** với expected contract và bảo vệ Actuator exposure.

### Một ví dụ normalize graph để so sánh

~~~java
Set<String> channelNames = graph.getNodes().stream()
    .filter(node -> node.getComponentType() != null)
    .map(IntegrationNode::getName)
    .collect(Collectors.toSet());

assertTrue(channelNames.containsAll(
        Set.of("graphInput", "graphOutput")));
~~~

Đây mới là **assert tên node**, chưa assert links; kết hợp helper ở mục 5. Không dùng `Graph.getContentDescriptor().get("providerVersion")` làm giá trị cố định nếu test phải chạy trên các patch versions khác nhau.

## 24. Các lỗi test phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hành động kiểm tra |
| --- | --- | --- |
| Graph chỉ có default nodes | Endpoint chưa đăng ký/context chưa refresh | Kiểm tra `@EnableIntegration`, bean config, graph server |
| Node tồn tại nhưng không có input link | Sai input channel hoặc node chỉ là bean không active | Kiểm tra `Graph.getLinks()` theo ID |
| Link không xuất hiện sau đăng ký flow mới | Đang đọc graph cache | Gọi `rebuild()` |
| Test link hỏng khi đổi SI 6.x sang 7.1 | `LinkNode` chuyển từ class getter sang record accessor | Dùng API theo version |
| Behavior test pass nhưng graph test fail | Handler gửi channel động không được static graph biểu diễn | Phân biệt dynamic routing với declared links |
| `isObserved()` false | Thiếu registry/pattern hoặc node không instrumented | Kiểm tra `@EnableIntegrationManagement` và bean registry |
| TestObservationRegistry rỗng | Không có handler, chưa thực thi component, pattern không match | Gửi message qua managed channel thật |
| Micrometer meter không xuất hiện | Chỉ có ObservationRegistry, thiếu meter handler | Đăng ký `DefaultMeterObservationHandler` |
| Handler đã chạy, sample vẫn chưa stop | Async task chưa hoàn tất hoặc assertion quá sớm | Đợi điều kiện end-to-end, bounded await |
| ErrorMessage không tới channel | Exception đồng bộ không có error publishing boundary | Kiểm tra worker/poller/adapter error handler |
| `isRunning()` true nhưng không có output | Poller rỗng, handler lỗi, queue đầy, wrong route | Queue depth, retry/error flow và metrics |
| Test flake trên CI | Sleep cố định, shared static state, thread pool không cleanup | `receive(timeout)`, per-test context, Awaitility |
| Test count tăng bất thường | TestObservationRegistry không clear hoặc nhiều operations sinh sample | Reset trước test, filter theo name/tags |
| Thấy trace ID nhưng không có parent-child relation | Context propagation sai qua executor/broker | Assert span relationship với tracer test backend |
| Dùng request ID làm metric tag | Cardinality cao, chi phí monitoring tăng | Chuyển event ID sang trace/log |
| Stop flow nhưng graph còn node | `stop()` không phải `destroy()` | Test lifecycle riêng với structural removal |

### Checklist debug từng lớp

1. **Context:** test profile, dependency versions, `@EnableIntegration`, component bean names.
2. **Graph:** `getGraph()` hay `rebuild()`, node names, node IDs, typed links.
3. **Message:** input send accepted, output/error queue, payload, headers, correlation.
4. **Runtime:** running state, poller/executor, thread, async completion.
5. **Observation:** registry bean, patterns, custom handlers, sample lifecycle.
6. **Metrics/tracing:** handler/exporter, names/tags, sampling/context propagation.
7. **Durable side effects:** transaction, broker ack/requeue, message store/DB.
8. **Cleanup:** no leaked executor tasks, subscriptions, dynamic registrations.

## 25. Bộ bài thực hành

1. **Graph căn bản:** dựng `graphInput → transformer → graphOutput`, assert tồn tại cả hai channel nodes và hai typed links.
2. **Negative graph test:** cố tình đổi transformer `outputChannel` sang channel khác, xem test fail đúng tại liên kết output.
3. **Observation pattern:** thay `observationPatterns = "*"` bằng pattern chỉ chọn một channel; so sánh `IntegrationNode.isObserved()` và TestObservationRegistry.
4. **Thiếu registry:** bỏ `TestObservationRegistry` bean; kiểm tra có observation thực sự được thu hay không.
5. **Meter handler:** thêm `SimpleMeterRegistry` và `DefaultMeterObservationHandler`, assert timer count sau gửi message.
6. **Custom hook:** cài `CountingObservationHandler`, tạo một custom observation rồi kiểm tra starts=stops=1, errors=0.
7. **Error hook:** cho handler throw; xác nhận `assertThrows` trên DirectChannel, không suy global errorChannel có message.
8. **ErrorMessage:** chuyển sang poller hoặc executor đã cấu hình error channel, assert `ErrorMessage` qua `receive(timeout)`.
9. **Dynamic flow:** đăng ký flow với `IntegrationFlowContext`, test `rebuild()` sau register và destroy.
10. **Message History:** bật `@EnableMessageHistory` với pattern chọn lọc, so sánh hops trên output với graph nodes.
11. **Executor:** chuyển handler sang `ExecutorChannel`, dùng queue/latch để đợi, tránh `Thread.sleep` cố định.
12. **Poller:** test lifecycle start/stop và message backlog trên `QueueChannel`; assert observation ở component được instrument trong version.
13. **Retry:** cấu hình handler fail hai lần rồi thành công; test attempts bằng counter, không dùng observation count thay thế.
14. **Transaction:** fail sau JDBC INSERT, kiểm tra rollback row và observation error/stop độc lập.
15. **Correlation:** splitter/aggregator có `correlationId` và `sequenceNumber`, test output + group state + graph.
16. **Privacy:** thêm một eventId duy nhất, kiểm tra không bị dùng làm low-cardinality metric tag.
17. **Observability outage:** mô phỏng collector không khả dụng, đảm bảo business flow không bị hỏng do một telemetry hook ngoại vi.
18. **Version update:** chuyển test graph từ SI 6.x sang 7.1, sửa LinkNode accessors, xác minh contract topology không đổi.

### Câu hỏi tự kiểm tra

- Tại sao kiểm tra `graph.getNodes().size() > 0` chưa đủ?
- `getGraph()` và `rebuild()` khác nhau khi đăng ký flow động thế nào?
- Vì sao node ID số không nên hardcode?
- `LinkNode.Type.input`, `output`, `error`, `route`, `discard` khác nhau ra sao?
- `@EnableIntegrationManagement(observationPatterns = "*")` và `ObservationRegistry` có vai trò riêng gì?
- Tại sao một `TestObservationRegistry` có observation không chứng minh đã export Prometheus timer?
- `isObserved()` có chứng minh observation start/stop không?
- Khi dùng ExecutorChannel, nên đợi điều kiện nào trước khi assert hook?
- Tại sao `ErrorMessage` không tự xuất hiện khi DirectChannel handler ném exception?
- Một handler được retry ba lần có nhất thiết có ba observation samples không?
- Vì sao message history không thay distributed tracing hoặc transaction test?
- Nên test những invariants nào khi rollout một dynamic flow?

## 26. Checklist trước khi chuyển STEP 6 QA

- Nội dung test có **graph assertions**, **behavior assertions** và **observation assertions** tách biệt.
- Endpoint/channel ID được chọn ổn định, tránh so khớp tên sinh tự động khi không cần.
- Test graph kiểm tra typed links, không chỉ số node.
- Test graph sau thay đổi cấu trúc gọi `rebuild()`.
- Đã khóa API mục tiêu: ví dụ chính dùng Spring Integration 6.5.x; 7.1 thay LinkNode getters.
- Có `ObservationRegistry` bean, `@EnableIntegrationManagement`, `observationPatterns` đúng.
- `TestObservationRegistry` được reset giữa tests; assertions kiểm tra observations đã start và stop.
- Không coi có ObservationRegistry là tự có metrics/traces exporter.
- Có finite timeout cho async/poller; không sleep cố định.
- Retry attempts, transaction rollback, broker ack và correlation được kiểm chứng bằng trạng thái thật.
- Không đưa eventId/orderId vào low-cardinality metric tags.
- Có lỗi giả lập để test error publishing boundary và recovery flow.
- Sau mỗi test dynamic flow có cleanup registrations và executor workers.
- Các ví dụ/versions được đối chiếu khi đưa vào project; ở STEP 4 chưa chạy Gradle/Content QA.

## 27. Tài liệu tham khảo chính thức

- [Spring Integration — Integration Graph](https://docs.spring.io/spring-integration/reference/graph.html): cấu trúc graph, nodes, typed links, cache/rebuild.
- [Spring Integration API — IntegrationGraphServer 6.5](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/graph/IntegrationGraphServer.html): `getGraph()`, `rebuild()`, properties callback.
- [Spring Integration API — Graph 6.5](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/graph/Graph.html): `getContentDescriptor()`, `getNodes()`, `getLinks()`.
- [Spring Integration API — IntegrationNode 6.5](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/graph/IntegrationNode.html): `getName()`, `getNodeId()`, `isObserved()`.
- [Spring Integration API — LinkNode 6.5](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/graph/LinkNode.html): `getFrom()`, `getTo()`, `getType()`.
- [Spring Integration API — LinkNode 7.1](https://docs.spring.io/spring-integration/api/org/springframework/integration/graph/LinkNode.html): các record accessors `from()`, `to()`, `type()`.
- [Spring Integration — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html): ObservationRegistry, management patterns, convention names.
- [Spring Integration — Testing Support](https://docs.spring.io/spring-integration/reference/testing.html): `MockIntegrationContext`, `MockIntegration`, endpoint testing.
- [Spring Integration — Java DSL Runtime Flows](https://docs.spring.io/spring-integration/reference/dsl/java-runtime-flows.html): dynamic flow registration và destroy.
- [Micrometer — Observation Testing](https://docs.micrometer.io/micrometer/reference/observation/testing.html): TestObservationRegistry và lifecycle assertions.
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html): ObservationHandler, conventions, cardinality.
- [Spring Framework — Observability](https://docs.spring.io/spring-framework/reference/integration/observability.html): observations và metrics/tracing.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): ErrorMessage và error publishing boundaries.
- [Spring Integration — Message History](https://docs.spring.io/spring-integration/reference/message-history.html): header history và tracked components.
