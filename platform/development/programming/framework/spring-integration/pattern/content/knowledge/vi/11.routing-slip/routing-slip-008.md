# Theo dõi bước hiện tại trong message

**Routing Slip** là một Enterprise Integration Pattern (EIP) trong đó message mang theo lộ trình xử lý của chính nó. Thay vì mỗi endpoint tự quyết định cứng bước tiếp theo, Spring Integration có thể đọc một header chứa các chặng cần đi và cập nhật **con trỏ vị trí** sau mỗi lần chọn kênh.

Bài thuộc chương **Routing slip** của module **SPRING_INTEGRATION_PATTERN**. Module hướng đến việc thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng, có kiểm thử và theo dõi từng nhánh.

Trọng tâm ở đây là **theo dõi bước hiện tại trong message**: cấu trúc header `routingSlip`, ý nghĩa của `routingSlipIndex`, thời điểm con trỏ thay đổi, cách đọc nó một cách an toàn và vì sao không thể dùng nó làm bằng chứng rằng một bước nghiệp vụ đã hoàn thành.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Mô tả Routing Slip khác Router và một chuỗi channel tĩnh như thế nào.
2. Giải thích cấu trúc header `routingSlip` gồm **path** và **index**, trong đó index bắt đầu từ 0.
3. Phân biệt **handler đang xử lý**, **chặng đã được chọn** và **chặng sẽ được xét tiếp**.
4. Xác định thời điểm Spring Integration dùng routing slip: **một message-producing endpoint có reply nhưng không cấu hình `outputChannel` rõ ràng**.
5. Giải thích vì sao một channel name làm index tăng, còn `RoutingSlipRouteStrategy` có thể giữ index nguyên qua nhiều lần gọi.
6. Khởi tạo lộ trình bằng `HeaderEnricher` hoặc Java DSL, rồi ghi nhận tiến độ trong một ứng dụng Java.
7. Viết kiểm thử JUnit xác nhận từng chặng và từng giá trị index trong flow thật.
8. Nhận diện trường hợp lặp vô hạn, mất header, reply timeout, retry, serialization và dữ liệu không đáng tin cậy.

## 2. Routing Slip: lộ trình đi cùng message

Giả sử cần xử lý đơn hàng qua ba bước: `prepare`, `validate` và `save`. Một cách cấu hình là nối cố định ba channel. Với Routing Slip, ta có thể khai báo bước đầu vào trước, sau đó mang các bước tiếp theo ngay trong metadata.

~~~mermaid
flowchart LR
    IN["Request / Gateway"] --> EN["HeaderEnricher"]
    EN --> A["prepare"]
    A -->|"routingSlip: validate"| B["validate"]
    B -->|"routingSlip: save"| C["save"]
    C -->|"hết path"| R["replyChannel"]
~~~

Ví dụ:

~~~text
message payload:
  orderId: ORDER-1001

message headers:
  traceId: trace-1001
  businessCorrelationId: ORDER-1001
  routingSlip:
    path: [validateChannel, saveChannel]
    index: 0
~~~

Đoạn trên là **cách diễn giải phục vụ học tập**, không phải JSON hay format serialize thực tế của Spring. Message có header riêng tên `routingSlip`, với một cấu trúc bên trong biểu diễn path/index.

Khi handler `prepare` tạo reply, framework chọn `validateChannel` từ path và tăng con trỏ trong reply. Sau khi `validate` tạo reply, framework chọn `saveChannel` và tăng con trỏ lần nữa. Cuối cùng, khi không còn phần tử trong lộ trình, cơ chế reply thông thường tiếp tục.

**Routing Slip không phải audit trail.** Nó lưu **đường đi dự kiến và vị trí xử lý routing**, không ghi trạng thái commit, thời gian hoàn tất hoặc side effect thành công của từng handler.

### So sánh các pattern gần nhau

| Mô hình | Mục đích | Khác biệt khi theo dõi |
|---|---|---|
| **Content-Based Router** | Chọn đích theo payload hoặc headers tại thời điểm quyết định | Không nhất thiết giữ một con trỏ lộ trình trên message |
| **Header-Based Router** | Map một giá trị header sang channel | Header thường là routing key, không phải toàn bộ hành trình |
| **Routing Slip** | Message mang danh sách bước và vị trí xét tiếp | Có **path + index** trên message |
| **Recipient List Router** | Chọn nhiều recipient theo điều kiện | Có thể fan-out tới nhiều đích |
| **Publish–Subscribe** | Phát tới các subscriber đang đăng ký | Không tự quản lý một lộ trình tuần tự |
| **Process Manager** | Điều phối quy trình nhiều bước có state phức tạp | Có thể cần state/persistence/recovery ngoài header |

Nếu quy trình chỉ có vài bước luôn cố định, `IntegrationFlow` nối các endpoint có thể dễ hiểu hơn. Routing Slip hữu ích nhất khi **lộ trình có thể thay đổi theo từng message** hoặc có các strategy quyết định động.

## 3. Header routingSlip gồm những gì?

Spring Integration dùng hằng số `IntegrationMessageHeaderAccessor.ROUTING_SLIP`. Khi được tạo bởi `RoutingSlipHeaderValueMessageProcessor`, giá trị thường có dạng **`Map<List<Object>, Integer>`** chứa một cặp:

- **Key**: `List<Object>` là path có thứ tự, bao gồm tên channel, strategy bean hoặc thành phần strategy được framework xử lý.
- **Value**: `Integer` là `routingSlipIndex`, chỉ vị trí sẽ được xét tiếp trong path.

~~~text
routingSlip = {
  ["validateChannel", "saveChannel"] : 0
}
~~~

Đây là biểu diễn ý nghĩa của map. **Không có một top-level message header riêng tên `routingSlipIndex` được tự động tạo theo mô hình này.** Nếu muốn đọc index, bạn phải đọc giá trị header `routingSlip` rồi lấy value của entry path/index.

### 3.1. Ý nghĩa của index

Giả sử `path = ["validateChannel", "saveChannel"]`:

| Giá trị index | Chặng sẽ xét tiếp | Điều có thể kết luận |
|---:|---|---|
| 0 | `validateChannel` | Chưa chọn phần tử channel đầu tiên |
| 1 | `saveChannel` | Phần tử ở vị trí 0 đã được chọn làm đích |
| 2 | Hết path | Không còn entry tĩnh nào để chọn |
| Bất kỳ giá trị khác phạm vi 0..2 | Dữ liệu cần kiểm tra | Không tự sửa index để "chạy tiếp" |

Một lỗi rất thường gặp là đọc `routingSlipIndex=1` trong handler `validateChannel` rồi kết luận bước validate đã hoàn thành. Trên thực tế, index có thể đã tăng **trước lúc message được đưa tới handler validate**; handler đó có thể chưa thực hiện bất kỳ thao tác nghiệp vụ nào.

### 3.2. Ba khái niệm phải phân biệt

1. **Current handler**: tên endpoint mà message đang được xử lý, ví dụ `validate`.
2. **Next path index**: vị trí Routing Slip sẽ xét tiếp khi một reply được tạo và cần tìm output channel, ví dụ `1`.
3. **Business completion**: trạng thái nghiệp vụ thật, như "validation passed", "database committed" hay "notification delivered".

Hệ thống cần ghi nhận từng khái niệm ở đúng chỗ. RoutingSlipIndex **không thay thế** outcome của transaction hoặc tracing span.

### 3.3. Routing slip khác các metadata khác

| Header/field | Ý nghĩa |
|---|---|
| `routingSlip` | Điều phối path/index của luồng |
| `MessageHeaders.ID` | ID của một message instance, có thể đổi khi tạo message mới |
| `traceId` | Theo dõi hành trình qua nhiều endpoint/services |
| `businessCorrelationId` | Liên kết các message của cùng một đơn/giao dịch |
| `replyChannel` | Đường nhận reply theo request–reply |
| `errorChannel` | Đường đi của error message theo topology hỗ trợ |
| `sequenceNumber`/`sequenceSize` | Metadata cho Splitter/Aggregator khi có nhóm |

## 4. Khi nào Spring Integration tham chiếu routing slip?

Routing Slip được Spring Integration tích hợp trong cơ chế **chọn output channel** của `AbstractMessageProducingHandler`.

Điều kiện cốt lõi là:

1. Endpoint nhận request message.
2. Endpoint **tạo reply**.
3. Endpoint **không có `outputChannel` được khai báo trực tiếp**.
4. Framework xét header `routingSlip` để tìm channel cho reply.

~~~mermaid
flowchart TD
    I["Request message đến endpoint"] --> P{"Có reply?"}
    P -->|Không| STOP["Không có reply để tiếp tục slip"]
    P -->|Có| FIX{"Endpoint có outputChannel cố định?"}
    FIX -->|Có| OUT["Dùng outputChannel đã cấu hình"]
    FIX -->|Không| SLIP{"Routing slip còn entry?"}
    SLIP -->|Có| NEXT["Đánh giá path[index]"]
    SLIP -->|Không| REPLY["Dùng replyChannel thông thường"]
    NEXT --> SEND["Gửi reply tới đích đã chọn"]
~~~

**Hai hệ quả quan trọng:**

- Nếu bạn khai báo `outputChannel="next"` cho một endpoint, không thể mong routing slip tự quyết định kênh khác tại chính endpoint đó. Cấu hình output channel rõ ràng được dùng trước.
- Nếu endpoint trả `void`, hoặc hoàn toàn không sinh reply, Routing Slip không tự "bơm" message mới sang bước tiếp theo.

Ví dụ một handler đi theo routing slip:

~~~java
import org.springframework.integration.annotation.ServiceActivator;

public class PrepareHandler {
    @ServiceActivator(inputChannel = "prepareChannel")
    public String prepare(String payload) {
        return payload + "|prepared";
    }
}
~~~

Method trên tạo một reply bằng chuỗi kết quả và **không** chỉ định output channel cố định. Nếu header routingSlip hợp lệ, reply có thể tiếp tục theo path.

Ngược lại:

~~~java
@ServiceActivator(
        inputChannel = "prepareChannel",
        outputChannel = "fixedChannel")
public String prepareWithFixedChannel(String payload) {
    return payload + "|prepared";
}
~~~

Ở đây có output channel được khai báo, nên lộ trình do endpoint quyết định thay vì Routing Slip.

## 5. Cách Spring cập nhật routingSlipIndex

### 5.1. Path entry là channel name

Khi `path[index]` là tên bean của `MessageChannel`, framework dùng tên đó để resolve channel đích và **tăng index trong reply message**.

Giả sử:

~~~text
path = [validateChannel, saveChannel]
index = 0
~~~

Sau khi `prepare` tạo reply và chọn `validateChannel`, message được đưa tới validate với index **1**. Khi `validate` tạo reply và chọn `saveChannel`, message được đưa tới save với index **2**.

~~~mermaid
sequenceDiagram
    participant A as prepare
    participant B as validateChannel
    participant C as saveChannel
    participant R as replyChannel

    Note over A: path=[validate,save], index=0
    A->>B: Reply sang validate, index=1
    Note over B: B đang chạy, index đã là 1
    B->>C: Reply sang save, index=2
    Note over C: C đang chạy, path đã hết
    C-->>R: Reply cuối
~~~

Không nên gọi chỉ số 1 là "đã xong validate"; nó chỉ cho biết **validate đã được chọn làm chặng** và con trỏ chuyển sang ứng viên tiếp.

### 5.2. Path entry là RoutingSlipRouteStrategy

Path cũng có thể chứa một `RoutingSlipRouteStrategy`. Interface có phương thức:

~~~text
RoutingSlipRouteStrategy (API Spring Integration):
    Object getNextPath(Message<?> requestMessage, Object reply)
~~~

Đây là **chữ ký phương thức của interface trong thư viện**, không phải yêu cầu tạo lại interface trùng tên trong mã ứng dụng. Ví dụ triển khai thật ở mục 5.3 sử dụng interface đã import từ Spring Integration.

Quy tắc đặc biệt:

- Nếu `getNextPath` trả **một channel name hoặc channel hợp lệ**, framework dùng đích đó **nhưng chưa tăng index**.
- Nếu `getNextPath` trả `null` hoặc chuỗi rỗng `""`, framework **tăng index**, rồi tìm tiếp phần tử tiếp theo.
- Strategy có thể được gọi lặp lại ở cùng vị trí cho đến khi không còn đích cần thực hiện.

| Lần gọi strategy ở index 0 | Kết quả | Index sau quyết định | Diễn giải |
|---|---|---:|---|
| 1 | `"reviewChannel"` | 0 | Tiếp tục review |
| 2 | `"reviewChannel"` | 0 | Tiếp tục review lần nữa |
| 3 | `null` | 1 | Bỏ qua strategy, xét mục tiếp |
| Mục 1 là `"archiveChannel"` | `"archiveChannel"` | 2 | Đã chọn archive |

**Cảnh báo:** nếu strategy luôn trả cùng channel mà không có điều kiện dừng, message có thể lặp vô hạn. Phải có giới hạn số lượt, timeout và chính sách retry/idempotency.

### 5.3. Ví dụ một strategy có điều kiện

~~~java
import org.springframework.integration.routingslip.RoutingSlipRouteStrategy;
import org.springframework.messaging.Message;

// Kiểu domain minh họa:
record ReviewState(int remainingChecks) {}

public final class OptionalReviewStrategy
        implements RoutingSlipRouteStrategy {

    @Override
    public Object getNextPath(
            Message<?> requestMessage, Object reply) {

        if (reply instanceof ReviewState state) {
            return state.remainingChecks() > 0
                    ? "reviewChannel"
                    : null;
        }
        return null;
    }
}
~~~

Đây là ví dụ **chính sách**, không phải cấu hình flow hoàn chỉnh. Trong thực tế, `reply` có thể là **domain object**, `Message<?>` hoặc `AbstractIntegrationMessageBuilder` tùy endpoint. Strategy phải xử lý đúng những kiểu thực sự được truyền tới nó; không giả định luôn là `ReviewState`.

Nếu muốn lặp có kiểm soát, handler phải trả một `ReviewState` cập nhật `remainingChecks`; strategy khi không còn bước nào trả `null` để index được tăng. **Không dùng chính routingSlipIndex làm bộ đếm số lần lặp** vì index vẫn giữ nguyên khi strategy tiếp tục trả channel.

## 6. Khởi tạo Routing Slip đúng cách

Spring Integration có `RoutingSlipHeaderValueMessageProcessor`, một bộ xử lý header được dùng với `HeaderEnricher`. Nó tạo cấu trúc path/index thích hợp và chuẩn bị việc resolve tên channel/strategy.

### 6.1. Cấu hình Java dùng HeaderEnricher

~~~java
import java.util.Collections;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.annotation.Transformer;
import org.springframework.integration.transformer.HeaderEnricher;
import org.springframework.integration.transformer.support.RoutingSlipHeaderValueMessageProcessor;

@Configuration
class RoutingSlipHeaderConfiguration {

    @Bean
    @Transformer(
            inputChannel = "slip.input",
            outputChannel = "slip.prepare")
    HeaderEnricher routingSlipHeaderEnricher() {
        return new HeaderEnricher(
                Collections.singletonMap(
                        IntegrationMessageHeaderAccessor.ROUTING_SLIP,
                        new RoutingSlipHeaderValueMessageProcessor(
                                "slip.validate",
                                "slip.finish")));
    }
}
~~~

Ý nghĩa:

- `slip.input` là channel nhận message chưa có routing slip.
- Header enricher tạo `routingSlip` với path gồm `slip.validate` và `slip.finish`, index ban đầu bằng 0.
- Header enricher được khai báo **outputChannel=slip.prepare**, vì thế chặng `prepare` chạy đầu tiên.
- Handler `prepare` không có output channel sẽ dùng routing slip để đến `slip.validate`; rồi `validate` dùng phần tử tiếp theo.

**Không đưa cả hai phiên bản cấu hình trong bài vào một Spring context**: phần tiếp theo có bản cấu hình đầy đủ riêng để minh họa flow.

### 6.2. Tương đương bằng Java DSL

Với phiên bản Spring Integration có `HeaderEnricherSpec.routingSlip(...)`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
IntegrationFlow routeEntrance() {
    return IntegrationFlow.from("slip.input")
            .enrichHeaders(h ->
                    h.routingSlip("slip.validate", "slip.finish"))
            .channel("slip.prepare")
            .get();
}
~~~

Dùng **một** cấu hình cho input `slip.input`; không đồng thời khai báo annotation enricher và DSL flow cùng nhận một `DirectChannel` nếu mục tiêu là một chuỗi nối tiếp.

### 6.3. Đừng tự set routingSlip bằng một chuỗi

~~~java
// Anti-pattern: không phải cấu trúc routingSlip mà framework mong đợi.
MessageBuilder.withPayload("ORDER-1001")
        .setHeader("routingSlip", "slip.validate;slip.finish")
        .build();
~~~

Một routing slip hợp lệ gồm path/index. Việc gắn chuỗi tùy ý không có nghĩa Spring sẽ parse nó như một header đã được processor tạo. Sử dụng HeaderEnricher/DSL hoặc API chính thức tương ứng phiên bản thư viện.

## 7. Theo dõi từng bước bằng cách đọc snapshot

Để quan sát routing slip, nên viết một hàm chỉ **đọc** và tạo bản snapshot. Không nên ép kiểu thẳng về `Map<List<String>, Integer>` vì path có thể chứa strategy object, không chỉ string.

### 7.1. Một kiểu dữ liệu dùng cho quan sát

~~~java
public record StepObservation(
        String stage,
        int nextIndex,
        int pathSize,
        String nextEntry,
        String traceId
) {}
~~~

Các trường có ý nghĩa:

- `stage`: handler nơi ta ghi lại trạng thái.
- `nextIndex`: index của routing slip tại thời điểm quan sát.
- `pathSize`: số phần tử trong path.
- `nextEntry`: tên ứng viên kế tiếp nếu là channel string, hoặc nhãn tổng quát.
- `traceId`: metadata riêng để liên kết các quan sát.

### 7.2. Đọc một header routingSlip

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;

public final class SlipInspector {

    private SlipInspector() {}

    public static StepObservation snapshot(
            String stage, Message<?> message) {

        Object raw = message.getHeaders().get(
                IntegrationMessageHeaderAccessor.ROUTING_SLIP);

        if (!(raw instanceof Map<?, ?> slip) || slip.size() != 1) {
            throw new IllegalArgumentException(
                    "Routing slip header is missing or malformed");
        }

        Map.Entry<?, ?> entry =
                slip.entrySet().iterator().next();

        if (!(entry.getKey() instanceof List<?> path)
                || !(entry.getValue() instanceof Integer index)) {
            throw new IllegalArgumentException(
                    "Expected path list and integer index");
        }

        if (index < 0 || index > path.size()) {
            throw new IllegalArgumentException(
                    "Invalid routing slip index");
        }

        String nextEntry;
        if (index == path.size()) {
            nextEntry = "<end>";
        } else if (path.get(index) instanceof String name) {
            nextEntry = name;
        } else {
            nextEntry = "<strategy-or-channel>";
        }

        return new StepObservation(
                stage,
                index,
                path.size(),
                nextEntry,
                message.getHeaders().get("traceId", String.class));
    }
}
~~~

Hàm này minh họa đọc **cấu trúc path/index** mà không mutate header. Ở production, có thể chỉ ghi nhận `stage`, `index` và `size`, hoặc **whitelist** những tên channel được phép log để tránh lộ bean name, expression hay thông tin nội bộ.

### 7.3. Vì sao không sửa header trực tiếp?

~~~java
// Không nên tự sửa map bên trong routingSlip:
Object raw = message.getHeaders().get(
        IntegrationMessageHeaderAccessor.ROUTING_SLIP);

// Tránh cast rồi put(...), sửa path list hoặc "tăng index" thủ công.
~~~

`MessageHeaders` có cấu trúc map đọc-được nhưng giá trị header vẫn có thể chứa object phức tạp. Mutate path/index ngoài cơ chế framework có thể làm sai trạng thái, gây vòng lặp hoặc bỏ qua bước. Hãy để Spring cập nhật con trỏ khi nó chọn channel cho reply.

## 8. Ví dụ ba chặng: prepare, validate, finish

Một flow đầy đủ giúp nhìn thấy chỉ số **0 → 1 → 2**. Các handler sử dụng `@ServiceActivator` và **không khai báo outputChannel**, vì vậy reply của chúng có thể đi theo routing slip.

### 8.1. Handler lưu quan sát để kiểm thử

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;

public final class SlipStages {

    private final List<StepObservation> states =
            new CopyOnWriteArrayList<>();

    @ServiceActivator(inputChannel = "slip.prepare")
    public String prepare(Message<String> input) {
        states.add(SlipInspector.snapshot("prepare", input));
        return input.getPayload() + "|prepared";
    }

    @ServiceActivator(inputChannel = "slip.validate")
    public String validate(Message<String> input) {
        states.add(SlipInspector.snapshot("validate", input));
        return input.getPayload() + "|validated";
    }

    @ServiceActivator(inputChannel = "slip.finish")
    public String finish(Message<String> input) {
        states.add(SlipInspector.snapshot("finish", input));
        return input.getPayload() + "|finished";
    }

    public List<StepObservation> observations() {
        return List.copyOf(states);
    }

    public void resetForTest() {
        states.clear();
    }
}
~~~

Danh sách `CopyOnWriteArrayList` ở đây là fixture quan sát cho test; ứng dụng thật cần logging/metrics/tracing thay vì lưu vô hạn trong memory.

### 8.2. Cấu hình các channel

~~~java
import java.util.Collections;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.annotation.Transformer;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.transformer.HeaderEnricher;
import org.springframework.integration.transformer.support.RoutingSlipHeaderValueMessageProcessor;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class SlipFlowConfiguration {

    @Bean(name = "slip.input")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "slip.prepare")
    public MessageChannel prepareChannel() {
        return new DirectChannel();
    }

    @Bean(name = "slip.validate")
    public MessageChannel validateChannel() {
        return new DirectChannel();
    }

    @Bean(name = "slip.finish")
    public MessageChannel finishChannel() {
        return new DirectChannel();
    }

    @Bean
    @Transformer(
            inputChannel = "slip.input",
            outputChannel = "slip.prepare")
    public HeaderEnricher routingSlipHeaderEnricher() {
        return new HeaderEnricher(Collections.singletonMap(
                IntegrationMessageHeaderAccessor.ROUTING_SLIP,
                new RoutingSlipHeaderValueMessageProcessor(
                        "slip.validate", "slip.finish")));
    }

    @Bean
    public SlipStages slipStages() {
        return new SlipStages();
    }
}
~~~

Đây là phiên bản cấu hình **đủ cho ví dụ**, thay cho `RoutingSlipHeaderConfiguration` ở mục 6. Nếu đưa tất cả class này vào project, đặt chúng trong package và import thích hợp; dùng một bản khai báo `slip.input` và một endpoint khởi tạo header.

### 8.3. Dòng thời gian trong message

~~~mermaid
sequenceDiagram
    participant E as HeaderEnricher
    participant A as prepare
    participant B as validate
    participant C as finish
    participant R as replyChannel

    E->>A: path=[validate,finish], index=0
    Note over A: Quan sát index=0, next=validate
    A->>B: Reply, index=1
    Note over B: Quan sát index=1, next=finish
    B->>C: Reply, index=2
    Note over C: Quan sát index=2, next=end
    C-->>R: Reply cuối
~~~

| Handler đang thực thi | Index đọc được | Phần tử kế tiếp | Điều không được suy diễn |
|---|---:|---|---|
| `prepare` | 0 | `slip.validate` | Validate chưa chắc đã được gọi |
| `validate` | 1 | `slip.finish` | Validate chưa chắc hoàn thành nghiệp vụ |
| `finish` | 2 | Hết path | Ghi DB chưa chắc đã commit thành công |
| Reply cuối | Hết lộ trình | `replyChannel` nếu có | Không có nghĩa hệ thống khác đã nhận dữ liệu |

## 9. Kiểm thử Spring Integration flow và routingSlipIndex

Tạo một `QueueChannel` tạm để nhận reply, tương tự hành vi mà Gateway cần ở một flow request–reply. Test không yêu cầu broker hoặc HTTP server.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = SlipFlowConfiguration.class)
class RoutingSlipProgressTest {

    @Autowired
    @Qualifier("slip.input")
    MessageChannel input;

    @Autowired
    SlipStages stages;

    @BeforeEach
    void clearObservations() {
        stages.resetForTest();
    }

    @Test
    void followsPathAndTracksTheNextIndex() {
        QueueChannel replies = new QueueChannel();

        boolean accepted = input.send(
                MessageBuilder.withPayload("ORDER-1001")
                        .setHeader("traceId", "trace-1001")
                        .setReplyChannel(replies)
                        .build());

        assertTrue(accepted);

        Message<?> reply = replies.receive(1000);
        assertNotNull(reply);
        assertEquals(
                "ORDER-1001|prepared|validated|finished",
                reply.getPayload());

        List<StepObservation> observed = stages.observations();

        assertEquals(
                List.of("prepare", "validate", "finish"),
                observed.stream()
                        .map(StepObservation::stage)
                        .toList());

        assertEquals(
                List.of(0, 1, 2),
                observed.stream()
                        .map(StepObservation::nextIndex)
                        .toList());

        assertEquals(
                List.of("slip.validate", "slip.finish", "<end>"),
                observed.stream()
                        .map(StepObservation::nextEntry)
                        .toList());

        assertTrue(observed.stream().allMatch(s ->
                s.pathSize() == 2
                        && "trace-1001".equals(s.traceId())));
    }
}
~~~

Đây là kiểm thử **behavior của Spring Integration**, khác với unit test chỉ gọi `prepare(...)`. Khi chạy bằng `DirectChannel` đồng bộ, thứ tự quan sát có thể xác định theo flow đơn giản. Nếu thay bằng executor/broker hoặc mở rộng concurrency, cần test độc lập, thời gian chờ phù hợp và tránh chia sẻ state giữa các message.

### 9.1. Unit test cho hàm đọc routing slip

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class SlipInspectorTest {

    @Test
    void readsIndexAndNextCandidate() {
        List<Object> path = List.of("first", "second");

        Message<String> message = MessageBuilder
                .withPayload("payload")
                .setHeader(
                        IntegrationMessageHeaderAccessor.ROUTING_SLIP,
                        Map.of(path, 1))
                .setHeader("traceId", "trace-42")
                .build();

        StepObservation observed =
                SlipInspector.snapshot("first", message);

        assertEquals(1, observed.nextIndex());
        assertEquals(2, observed.pathSize());
        assertEquals("second", observed.nextEntry());
        assertEquals("trace-42", observed.traceId());
    }

    @Test
    void rejectsMissingHeader() {
        Message<String> message =
                MessageBuilder.withPayload("payload").build();

        assertThrows(IllegalArgumentException.class,
                () -> SlipInspector.snapshot("unknown", message));
    }
}
~~~

Đoạn test này chỉ kiểm tra **observer** trên một map theo contract; không có ý định khuyên tự dựng routingSlip header bằng `Map.of(...)` ở flow production. Khi cần chạy thật, dùng `HeaderEnricher` để khởi tạo header đúng API.

## 10. RoutingSlipRouteStrategy và một index có thể lặp

Hãy xét path:

~~~text
path = [reviewStrategy, archiveChannel]
index = 0
~~~

Chiến lược có thể chọn `reviewChannel` nhiều lần trước khi trả `null` để tiến tới `archiveChannel`.

~~~mermaid
flowchart TB
    START["index=0, reviewStrategy"] --> Q{"Còn việc phải review?"}
    Q -->|Có| REVIEW["reviewChannel"]
    REVIEW -->|reply cập nhật state| Q
    Q -->|Không: null| NEXT["index=1"]
    NEXT --> ARCHIVE["archiveChannel"]
    ARCHIVE --> END["index=2, hết path"]
~~~

**Bài học về theo dõi:** dù review chạy 5 lần, index ở phần tử strategy vẫn có thể bằng **0** trong nhiều lần liên tiếp. Muốn biết số lượt review, cần `reviewAttempt` hoặc một trường trạng thái nghiệp vụ khác.

### 10.1. Dùng con trỏ index để đếm bước đã xong là sai

~~~java
// Sai về ngữ nghĩa:
int completedSteps = routingSlipIndex;

// Đúng hơn: theo dõi outcome từ từng endpoint, correlation
// và số lần lặp riêng do ứng dụng quản lý.
~~~

Ngay cả khi path chỉ gồm tên channel, index tăng ở lúc **chọn đích**, không phải sau khi một DB transaction ở downstream được commit.

### 10.2. Kiểm thử điều kiện dừng

Một bộ test cho strategy nên có:

- Khi cần review, `getNextPath` trả channel hợp lệ.
- Khi hoàn tất, `getNextPath` trả `null` hoặc `""`.
- Với số lần review tối đa, hệ thống không lặp vô hạn.
- Nếu reply không đúng kiểu, không ép kiểu mù.
- Khi strategy dừng, con trỏ tiến tới entry tiếp theo.
- Khi một lần gọi review lỗi, chính sách retry/idempotency được áp dụng ở đúng handler.

Tách phần quyết định thành hàm thuần nếu có thể để test nhanh; bổ sung integration test để chắc chắn Spring đi đến channel đúng.

## 11. Theo dõi bằng log, Wire Tap và trace

Routing Slip hỗ trợ chẩn đoán **lộ trình tiếp theo**. Muốn biết message đi tới đâu và xử lý thành công hay thất bại, cần ghi quan sát tại các endpoint hoặc channel.

### 11.1. Nên ghi những trường nào?

| Trường | Tác dụng | Lưu ý |
|---|---|---|
| `stageName` | Chặng đang được quan sát | Lấy từ endpoint, không đoán bằng index |
| `routingSlipIndex` | Entry tiếp theo cần xét | Không xem là trạng thái commit |
| `pathSize` | Số entry của lộ trình | Không tương đương tổng handler đã hoàn thành |
| `nextCandidate` | Đích tiếp theo nếu biết | Chỉ log tên channel đã kiểm soát |
| `traceId` | Theo dõi nhiều span | Không dùng làm label metric cardinality cao |
| `businessCorrelationId` | Liên kết cùng đơn/giao dịch | Không đồng nhất với MessageHeaders.ID |
| `eventId` | Định danh event qua replay | Phục vụ idempotency |
| `outcome` | SUCCESS/REJECT/ERROR | Lấy theo kết quả thật |
| `durationMs` | Thời gian xử lý | Đo tại endpoint |

Một log có cấu trúc:

~~~text
traceId=trace-1001
stage=validate
routingSlipIndex=1
routingSlipPathSize=2
nextCandidate=slip.finish
outcome=SUCCESS
durationMs=14
~~~

Dòng log này có nghĩa `validate` đã được quan sát và `nextCandidate` đang là `slip.finish`. **Không thể kết luận `slip.finish` đã xử lý thành công** chỉ từ dòng đó.

### 11.2. Wire Tap và interceptor thấy trạng thái ở thời điểm nào?

Nếu một `ChannelInterceptor` ghi log khi message **vừa tới** `slip.validate`, nó quan sát index đã được tăng bởi endpoint trước khi chọn kênh validate. Nếu đặt quan sát **sau** một handler, có thể nhìn thấy reply mới với con trỏ khác.

Khi nhiều executor cùng chạy:

- Dòng log có thể xuất hiện lệch thứ tự giữa thread.
- Một timestamp không đủ khẳng định mối quan hệ nhân quả.
- Nên kết hợp trace span, `eventId`, correlation và tên stage.
- Không nên log toàn bộ object strategy, header nhạy cảm hoặc payload chứa thông tin cá nhân.

### 11.3. Metric hữu ích

Có thể đo:

- `routing_stage_invocations_total{stage}`.
- `routing_stage_failures_total{stage,type}`.
- `routing_stage_duration_seconds{stage}`.
- `routing_slip_exhausted_total`.
- `routing_strategy_iterations_total{strategy}`.

Chỉ dùng các nhãn có tập giá trị nhỏ; đặt `traceId`, `orderId` và `eventId` trong log/trace có kiểm soát thay vì metric label.

## 12. Routing Slip và metadata khi qua Transformer

Một Transformer có thể đổi payload, trong khi Routing Slip cần tiếp tục nằm trên message. Nếu Transformer **trả payload**, Spring Integration thường tạo output message và truyền các headers thích hợp theo mặc định. Nếu Transformer **trả `Message<?>` hoàn chỉnh**, code phải chủ động giữ những header cần thiết.

Ví dụ:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public Message<String> normalize(Message<String> input) {
    return MessageBuilder.withPayload(
                    input.getPayload().trim().toUpperCase())
            .copyHeaders(input.getHeaders())
            .build();
}
~~~

Ví dụ `copyHeaders` phù hợp với luồng nội bộ tin cậy; khi message đi qua broker/API, cần chọn lọc headers theo ranh giới bảo mật. Không sao chép mù `replyChannel`, `errorChannel`, token hoặc object không thể serialize sang hệ thống ngoài.

Nếu code trả message mới và **đánh rơi routingSlip**, endpoint sau có thể mất lộ trình. Nếu đánh rơi `replyChannel`, Gateway có thể chờ reply không bao giờ tới. Hãy bổ sung test propagation qua những bước tạo message mới.

## 13. Với Filter, Router, Splitter và Aggregator

Routing Slip không thay thế các pattern còn lại.

### 13.1. Filter

Filter quyết định message có được đi tiếp hay không. Nếu nó reject message và không tạo reply, **đường Routing Slip không tự tiếp tục**. Cần `discardChannel`, error flow hoặc kết quả reject riêng tùy hợp đồng.

### 13.2. Router

Router có thể chọn nhánh dựa trên payload/header. Routing Slip mang **một kế hoạch lộ trình**. Nếu một endpoint Router có output channel rõ ràng hoặc nhiều đích, cần kiểm tra tương tác với routing slip thay vì mặc định rằng index sẽ tăng như một chặng tuyến tính thông thường.

### 13.3. Splitter/Aggregator

Một Splitter tạo nhiều phần có correlation và sequence metadata; Routing Slip là lộ trình của message, không phải khóa gom nhóm. Khi các phần đi những nhánh khác nhau:

- Mỗi message con cần metadata tương ứng với lộ trình riêng.
- Tránh chia sẻ payload hoặc path mutable giữa các thread.
- Aggregator cần correlation/release strategy và timeout riêng.
- Một phần bị discard có thể khiến nhóm không hoàn tất.

Không dùng `routingSlipIndex` để thay thế `sequenceNumber` hoặc `correlationId`.

### 13.4. Publish–Subscribe

Publish–Subscribe phát một message tới nhiều subscriber. Routing Slip thường dẫn một message qua **chuỗi** chặng. Nếu fan-out đang dùng chung một routing slip có object mutable, hành vi của các nhánh có thể khó dự đoán; nên thiết kế lộ trình ở đúng cấp độ mỗi nhánh và dùng snapshot bất biến.

## 14. Routing Slip với Gateway và replyChannel

Một Gateway gửi request và thường chờ kết quả theo timeout. Ví dụ hành trình:

~~~mermaid
sequenceDiagram
    participant G as Gateway
    participant E as HeaderEnricher
    participant A as prepare
    participant B as validate
    participant C as finish

    G->>E: Request + replyChannel
    E->>A: Slip index=0
    A->>B: Reply index=1
    B->>C: Reply index=2
    C-->>G: Reply khi path hết
~~~

Khi path đã hết, Spring Integration quay về quy tắc `replyChannel` thông thường. Nếu header reply bị xóa, handler cuối trả void, hoặc một strategy lặp không dừng, Gateway có thể timeout hoặc phát sinh lỗi theo topology.

Cần kiểm thử: reply cuối thật sự tới Gateway, lỗi được phân loại, deadline được tuân thủ. **Chỉ số 2 không phải xác nhận rằng Gateway đã nhận reply.**

## 15. Lỗi, retry và idempotency

### 15.1. Index tăng không đồng nghĩa thành công bền vững

Framework tăng index khi quyết định output channel; việc gửi qua kênh, gọi handler, ghi DB hoặc broker có thể thất bại sau đó. Ví dụ index đã tăng từ 0 lên 1 khi chọn `validateChannel`, nhưng validate gặp exception trước khi commit.

Hệ thống cần ghi **outcome thật** của từng bước. Khi retry, phải biết:

- Retry lại handler nào?
- Có side effect nào đã thành công trước khi lỗi?
- Event ID nào được dùng để chống lặp?
- Có cần phát lại routing slip từ đầu, hay resume tại state đã lưu?
- Những chặng nào có khả năng chạy lại an toàn?

### 15.2. Routing Slip không cung cấp exactly-once

Một message có thể được retry hoặc replay và được đóng gói lại thành Message mới với `MessageHeaders.ID` khác. Việc con trỏ routing slip có giá trị nhất định **không tự tạo idempotency** hay transaction xuyên DB/email/broker.

Dùng một `eventId` bền vững, idempotency key cho từng side effect, transaction/outbox khi cần, và kiểm soát retry có giới hạn.

### 15.3. Error channel và xử lý bất đồng bộ

Trong channel đồng bộ, exception có thể lan về thread caller. Trong luồng async, lỗi có thể đi qua `ErrorMessage` và `errorChannel` tùy cấu hình. Routing Slip không tự phân loại exception thành lỗi có thể retry hay lỗi dữ liệu cố định.

Đặt retry/error handling ở ranh giới hợp lý và giữ correlation trên nhánh lỗi. Với strategy có vòng lặp, một lỗi cố định không được làm message quay lại cùng chặng vô hạn.

## 16. Routing Slip trong môi trường phân tán

Tài liệu Spring Integration nhấn mạnh một giới hạn: các **inline SpEL expression** trong routing slip có thể được framework chuyển thành `ExpressionEvaluatingRoutingSlipRouteStrategy` chứa dependency tới `BeanFactory`. Những object như vậy không phải một dạng dữ liệu serializable thuận tiện; khi message qua broker hoặc persistent `MessageStore` có thể gặp `NotSerializableException`.

Khuyến nghị:

1. Ưu tiên tên **bean strategy được đăng ký** thay vì inline expression được nhúng thành object trong header khi cần đi qua ranh giới serialization.
2. Kiểm tra rằng các tên channel/strategy có ý nghĩa tại đúng application context nhận message.
3. Đừng giả định một `MessageChannel` object ở JVM A dùng trực tiếp được ở JVM B.
4. Kiểm thử serialization/deserialize thật với adapter hoặc store sẽ triển khai.
5. Không để bên gửi không đáng tin tự quyết định danh sách channel nội bộ bằng header `routingSlip`.
6. Nếu quy trình cần restart/resume sau crash, phải có cơ chế state/persistence, không chỉ phụ thuộc routing slip trong bộ nhớ.

Với lộ trình đi qua nhiều service, cần coi routing slip là một phần của **hợp đồng giao tiếp được kiểm soát**, kèm version/whitelist và chính sách bảo mật.

## 17. Những lỗi phổ biến và cách chẩn đoán

### Lỗi 1 — Nhìn index rồi xác nhận sai bước đã hoàn tất

**Triệu chứng:** log ghi `index=1` tại validate, người vận hành hiểu rằng validate đã xong.

**Khắc phục:** log thêm `stageName` và `outcome`. Index là con trỏ định tuyến; outcome của handler/transaction được ghi riêng.

### Lỗi 2 — Index không tăng

**Khả năng:** path entry là `RoutingSlipRouteStrategy` tiếp tục trả channel; endpoint có outputChannel cố định; observer ghi ở cùng phía của một chặng.

**Khắc phục:** đọc loại path entry tại index, xem cách handler sinh reply và kiểm tra nơi đặt interceptor.

### Lỗi 3 — Handler có outputChannel cố định

**Triệu chứng:** reply đi channel cố định thay vì bước trong routing slip.

**Khắc phục:** bỏ cấu hình outputChannel ở những handler cần dùng slip, hoặc chủ động chấp nhận rằng tuyến cố định có ưu tiên.

### Lỗi 4 — Strategy lặp vô hạn

**Triệu chứng:** cùng một chặng được gọi liên tục, index giữ nguyên.

**Khắc phục:** chiến lược phải có điều kiện dừng và giới hạn vòng; dùng state nghiệp vụ riêng, không dùng index làm bộ đếm.

### Lỗi 5 — Handler trả void

**Triệu chứng:** flow dừng ở một chặng dù path chưa hết.

**Khắc phục:** endpoint cần tạo reply để có thể gửi tiếp hoặc thiết kế một cơ chế chuyển message rõ ràng. Routing Slip không tự sinh reply.

### Lỗi 6 — Mất header sau Transformer

**Triệu chứng:** message không còn đi theo path sau khi tạo Message mới.

**Khắc phục:** bảo toàn `routingSlip` cùng các metadata cần thiết; kiểm tra kiểu trả payload hay Message và cấu hình header propagation.

### Lỗi 7 — Path hết nhưng Gateway timeout

**Triệu chứng:** index đã bằng path size, request không có reply.

**Khắc phục:** kiểm tra `replyChannel`, handler cuối có reply không và error flow. Viết test với `QueueChannel` làm reply channel.

### Lỗi 8 — Sai định dạng routingSlip

**Triệu chứng:** handler hoặc observer không hiểu header; xuất hiện cast exception hoặc lỗi routing.

**Khắc phục:** dùng `HeaderEnricher` / `routingSlip(...)` thay vì gắn chuỗi/map tùy ý. Kiểm tra path/index trước khi quan sát.

### Lỗi 9 — Serialization thất bại

**Triệu chứng:** `NotSerializableException` khi lưu message hoặc gửi qua broker.

**Khắc phục:** tránh inline expression/strategy object không serializable trong path; dùng bean name theo khuyến nghị và kiểm thử adapter thực tế.

### Lỗi 10 — Dùng dữ liệu client để tạo path tự do

**Triệu chứng:** caller có thể chọn một channel nội bộ không được phép.

**Khắc phục:** authentication/authorization và whitelist tại ingress; chỉ nguồn đáng tin mới được gắn/đổi routing slip.

## 18. Bài thực hành

**Bài 1 — Ba chặng và con trỏ.** Dùng cấu hình `prepare → validate → finish`; ghi lại stage, path, index. Assert ba index **0, 1, 2** và payload cuối đi đủ ba bước.

**Bài 2 — Output channel cố định.** Thêm một `outputChannel` vào endpoint validate, rồi quan sát routing slip không còn chọn chặng ở đúng điểm đó. Giải thích hành vi bằng điều kiện sử dụng Routing Slip.

**Bài 3 — Handler một chiều.** Thay `validate` thành method trả `void`; xem message có tiếp tục không và Gateway có nhận reply không. Bổ sung cơ chế reject/error thích hợp.

**Bài 4 — Strategy lặp.** Đặt một `RoutingSlipRouteStrategy` vào path, trả reviewChannel hai lần rồi `null`. Kiểm chứng index không tăng khi strategy còn trả channel nhưng tăng khi nó dừng.

**Bài 5 — Quan sát không gây side effect lên header.** Viết `SlipInspector` lấy snapshot và test với header thiếu, sai cấu trúc, index âm, index vượt path size.

**Bài 6 — Correlation.** Gửi nhiều order khác nhau cùng lúc; dùng `traceId` và `businessCorrelationId` để khôi phục các quan sát cho từng message, không nhóm theo `routingSlipIndex`.

**Bài 7 — Retry.** Giả lập save thành công nhưng lỗi khi gửi reply. Thiết kế idempotency theo `eventId`, nêu rõ cách xử lý phát lại để không ghi trùng.

**Bài 8 — Cross-JVM.** So sánh route slip chỉ chứa channel/bean names với một path chứa inline SpEL object khi serialization; xác minh cấu hình được hỗ trợ bởi broker/store.

### Câu hỏi tự kiểm tra

1. `routingSlip` được lưu ở đâu, và index nằm ở vị trí nào trong giá trị header?
2. Index 1 trong validate có chứng minh validate đã hoàn thành không?
3. Vì sao một endpoint có `outputChannel` cố định có thể bỏ qua routing slip?
4. Nếu endpoint không tạo reply, routing slip có tự sinh message tiếp theo không?
5. Khi path entry là tên channel, con trỏ tăng vào thời điểm nào?
6. Vì sao strategy có thể được gọi nhiều lần mà index giữ nguyên?
7. Nếu strategy luôn trả cùng một channel, điều gì xảy ra?
8. Khi không còn path entry, cơ chế nào nhận reply?
9. RoutingSlipIndex có thể dùng thay `sequenceNumber` của Aggregator không?
10. Làm sao quan sát outcome riêng thay vì suy từ con trỏ?
11. Vì sao inline SpEL object có thể gây lỗi khi serialize message?
12. Cần những loại test nào để bảo đảm đường reply/error và độ an toàn của flow?

## 19. Checklist triển khai

- [ ] Chỉ dùng Routing Slip khi lộ trình có giá trị rõ ràng so với flow tĩnh.
- [ ] Tạo header bằng HeaderEnricher hoặc API routing slip chính thức.
- [ ] Hiểu path/index và xác định rõ **index sẽ xét tiếp**.
- [ ] Các endpoint sử dụng slip có reply và không khai báo outputChannel cố định ngoài ý định.
- [ ] Strategy có điều kiện dừng và giới hạn số lần lặp.
- [ ] Không mutate map path/index thủ công trong header.
- [ ] Có traceId, eventId và correlation riêng với routingSlipIndex.
- [ ] Log từng stage với outcome thật, không chỉ index.
- [ ] Kiểm thử flow qua channel thực và xác nhận chuỗi index.
- [ ] Kiểm tra propagation nếu Transformer tạo Message mới.
- [ ] Có replyChannel, error flow, timeout và chính sách retry/idempotency.
- [ ] Với broker/store, kiểm thử serialization của header.
- [ ] Không cho phép caller không đáng tin chọn channel/strategy tùy ý.
- [ ] Không dùng Routing Slip làm audit log hay cơ chế persistence duy nhất.

## 20. Tổng kết

Trong Spring Integration, **Routing Slip** gắn một **path** và một **index** lên message để xác định lộ trình tiếp theo. Khi một `AbstractMessageProducingHandler` tạo reply mà không có outputChannel cố định, framework xét phần tử hiện tại. **Path entry là channel name** làm index tăng trong reply; **path entry là `RoutingSlipRouteStrategy`** có thể giữ index nguyên cho tới khi strategy trả `null` hoặc `""`. Khi path đã hết, việc gửi reply tiếp tục theo cơ chế `replyChannel` thông thường.

Để **theo dõi bước hiện tại**, cần kết hợp con trỏ với tên endpoint đang quan sát, trace/correlation và kết quả xử lý. **RoutingSlipIndex không phải số bước đã commit**, không thay thế kiểm thử integration flow, retry, idempotency hay monitoring. Dùng đúng HeaderEnricher, chiến lược có điều kiện dừng, quan sát có cấu trúc và giới hạn ranh giới tin cậy sẽ giúp hệ thống **SPRING_INTEGRATION_PATTERN** linh hoạt, dễ kiểm thử và dễ chẩn đoán trong production.

### Tài liệu tham khảo

- Spring Integration Reference — Routing Slip: https://docs.spring.io/spring-integration/reference/router/routing-slip.html
- Spring Integration API — RoutingSlipHeaderValueMessageProcessor: https://docs.spring.io/spring-integration/api/org/springframework/integration/transformer/support/RoutingSlipHeaderValueMessageProcessor.html
- Spring Integration API — RoutingSlipRouteStrategy: https://docs.spring.io/spring-integration/api/org/springframework/integration/routingslip/RoutingSlipRouteStrategy.html
- Spring Integration API — HeaderEnricherSpec: https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/HeaderEnricherSpec.html
- Spring Integration Reference — Message endpoints: https://docs.spring.io/spring-integration/reference/endpoint.html

