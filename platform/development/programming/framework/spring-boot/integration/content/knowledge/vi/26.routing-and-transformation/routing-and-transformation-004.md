# Splitter và chia một thông điệp thành nhiều đơn vị xử lý

## Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot kết nối HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter của Spring Integration để xây dựng những luồng tích hợp có thể vận hành thực tế. Một đơn hàng chứa 100 dòng sản phẩm, một tệp CSV chứa 10.000 bản ghi hoặc một batch sự kiện lấy từ database thường đi vào ứng dụng dưới dạng **một message**. Tuy nhiên, mỗi dòng/bản ghi có thể cần kiểm tra, biến đổi, định tuyến, lưu trạng thái hoặc gửi sang downstream độc lập.

**Splitter** là mẫu tích hợp **Message Splitter** trong Enterprise Integration Patterns (EIP): nhận một thông điệp đầu vào, phân tách payload thành nhiều phần và phát **nhiều thông điệp đầu ra**, mỗi thông điệp đại diện cho một đơn vị xử lý.

Bài thuộc chương **Định tuyến và biến đổi**, tập trung vào **Splitter và chia một thông điệp thành nhiều đơn vị xử lý** trong Spring Integration. Nội dung kết nối cách cấu hình Java DSL, annotation và splitter tùy biến với các vấn đề thật: hợp đồng dữ liệu, message headers, transaction, xử lý đồng thời, lỗi, retry/idempotency, aggregation, kiểm thử và observability.

Sau bài này, bạn có thể:

1. Phân biệt Splitter với Transformer, Filter, Router, Publish-Subscribe và Aggregator.
2. Dùng `IntegrationFlow.split()` hoặc `@Splitter` để tách danh sách thành message con.
3. Hiểu `payload`, headers, `correlationId`, `sequenceNumber` và `sequenceSize`.
4. Chọn cách xử lý đầu ra tuần tự, bất đồng bộ hoặc song song mà không làm mất kiểm soát tải.
5. Biết khi nào dùng Aggregator/Resequencer và vì sao lọc hoặc lỗi một phần có thể làm nhóm chờ mãi.
6. Xây dựng flow tách batch rồi xử lý SQL/HTTP/broker với khóa idempotency ổn định.
7. Thiết kế kiểm thử, dead-letter, checkpoint và metrics cho từng cấp batch/item.

> **Nguyên tắc:** Splitter làm thay đổi **đơn vị vận chuyển và xử lý message**; nó không tự tạo transaction trên mọi message con, không tự bảo đảm thứ tự khi dùng concurrency và không tự biến mỗi item thành exactly-once.

## 1. Một message đầu vào trở thành nhiều message đầu ra

Giả sử hệ thống nhận lô cập nhật tồn kho:

~~~json
{
  "batchId": "B-2026-001",
  "lines": [
    {"lineId": "L-1", "sku": "P-100", "quantity": 4},
    {"lineId": "L-2", "sku": "P-200", "quantity": 2},
    {"lineId": "L-3", "sku": "P-300", "quantity": 6}
  ]
}
~~~

Một Splitter có thể biến message chứa `List<InventoryLine>` thành ba message:

~~~text
Message<List<InventoryLine>>
    |
    +--> Message<InventoryLine(L-1)> --> Validate --> Apply
    |
    +--> Message<InventoryLine(L-2)> --> Validate --> Apply
    |
    +--> Message<InventoryLine(L-3)> --> Validate --> Apply
~~~

Nếu lô có 3 phần tử, số message đầu ra thường là 3; nếu danh sách rỗng, splitter có thể không phát message nào. Kết quả cụ thể tùy implementation và cấu hình. Không mặc định một batch rỗng sẽ luôn phát một message đặc biệt báo “hoàn thành”; nếu nghiệp vụ cần tín hiệu đó, phải thiết kế rõ.

### 1.1. Mô hình EIP

~~~mermaid
flowchart LR
    A["Message<Batch>"] --> B["Splitter"]
    B --> C["Message<Item 1>"]
    B --> D["Message<Item 2>"]
    B --> E["Message<Item N>"]
    C --> F["Handler / Transformer"]
    D --> F
    E --> F
    F --> G["SQL, HTTP, cache, broker"]
~~~

Splitter **không nhất thiết chạy song song**. Với `DirectChannel`, handler được gọi trong cùng luồng thread của người gửi; đầu ra có thể được xử lý tuần tự ngay trong lúc splitter phát message. Muốn thực sự làm việc bất đồng bộ, cần channel/executor hoặc một hệ thống hàng đợi phù hợp.

### 1.2. Splitter khác những EIP gần giống

| Thành phần | Đầu vào → đầu ra | Dùng khi |
| --- | --- | --- |
| **Splitter** | Một message chứa tập phần tử → nhiều message con | Xử lý từng dòng của batch |
| **Transformer** | Một message → một message với payload được chuyển đổi | JSON → DTO, DTO → format khác |
| **Filter** | Một message → cho qua hoặc loại bỏ | Bỏ bản ghi không phù hợp |
| **Router** | Một message → chọn đích xử lý theo điều kiện | Chọn queue theo region/status |
| **Publish-Subscribe Channel** | Cùng một message → nhiều subscribers | Fan-out cho các chức năng độc lập |
| **Recipient List Router** | Một message → nhiều endpoint nhận bản sao tùy quy tắc | Gửi cùng event tới nhiều bộ phận |
| **Aggregator** | Nhiều message có tương quan → một kết quả nhóm | Ghép kết quả xử lý lại thành batch |
| **Resequencer** | Nhiều message có sequence → sắp lại thứ tự | Đảm bảo xử lý/đầu ra theo thứ tự khi cần |

Ví dụ thông điệp `List<Item>` đi qua **publish-subscribe** vẫn giữ nguyên danh sách trong mỗi bản sao gửi tới subscriber. Đi qua **splitter** thì mỗi message đầu ra có payload là **một Item** (hoặc một kết quả chia cụ thể khác). Hai cách tạo fan-out không đồng nghĩa nhau.

## 2. Các đối tượng Spring Integration liên quan

Spring Integration dựa trên Spring Messaging:

- `Message<T>`: mang `payload` kiểu `T` và bộ `headers`.
- `MessageChannel`: kênh chuyển message.
- `MessageHandler`: consumer xử lý message.
- `MessageProducer` và các inbound adapters: đưa message từ HTTP, file, broker, database...
- **Splitter endpoint**: nhận một message và tạo một hoặc nhiều output messages.
- `IntegrationFlow`: cấu hình chain xử lý qua Java DSL.
- `@Splitter`: annotation đánh dấu method chuyên tách payload.

Các triển khai quan trọng:

| API/lớp | Vai trò |
| --- | --- |
| `IntegrationFlow.split()` | Java DSL split payload theo cách mặc định |
| `DefaultMessageSplitter` | Splitter chuẩn cho các dạng payload tập hợp được hỗ trợ |
| `AbstractMessageSplitter` | Base class cho splitter tùy biến |
| `@Splitter` | Đăng ký method splitter qua annotation |
| `@ServiceActivator` | Đặt handler xử lý từng message con |
| `MessageGroupStore` | Lưu message group của Aggregator/Resequencer khi cần |
| `IntegrationMessageHeaderAccessor` | Constants cho correlation/sequence headers |
| `MessageBuilder` | Tạo message, đặt headers từ gateway hoặc adapter |

### 2.1. Đừng lẫn payload nghiệp vụ với message envelope

Một `Message<List<InventoryLine>>` có:

~~~text
payload = [L-1, L-2, L-3]

headers:
  id = UUID của message hiện tại
  timestamp = thời điểm tạo message
  batchId = "B-2026-001"             (business context tự định nghĩa)
  source = "inventory-import"          (business context tự định nghĩa)
  ...
~~~

Sau split, mỗi output message cần mang:

- **Payload con**: `InventoryLine`.
- **Headers liên quan**: ví dụ `batchId`, `source`.
- **Sequence/correlation metadata** khi bật/áp dụng sequence để hỗ trợ aggregation.

Các headers kỹ thuật như `id` và `timestamp` có quy tắc tạo mới theo Spring Messaging; không nên giả định mọi header được copy nguyên vẹn. Nếu output do custom splitter tạo từ `Message<?>` riêng, cần đặc biệt kiểm tra cách headers được bảo toàn/ghi đè.

## 3. Cài đặt Spring Integration trong Spring Boot

Trong Gradle Groovy DSL, ví dụ tối thiểu:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'

    // Khi cần quan sát bằng Micrometer/Actuator:
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Trong test:
    testImplementation 'org.springframework.integration:spring-integration-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Spring Boot tự cấu hình nền cho Spring Integration khi dependency phù hợp. Một số adapter cụ thể cần module riêng, ví dụ JDBC, HTTP, AMQP hoặc Kafka; **starter integration không tự cung cấp tất cả các transport**.

Để giữ bài tập trung vào Splitter, ví dụ dưới đây dùng `DirectChannel` làm input và một bean service nhận từng dòng. Luồng tương tự có thể được gọi từ HTTP controller, broker listener, JDBC poller hoặc adapter của Spring Integration.

### 3.1. Model của batch

~~~java
// InventoryLine.java
public record InventoryLine(
        String lineId,
        String sku,
        int quantity) {
}
~~~

~~~java
// InventoryBatch.java
import java.util.List;

public record InventoryBatch(
        String batchId,
        List<InventoryLine> lines) {
}
~~~

Đây là model Java 17+ để mô tả hợp đồng dữ liệu. Trong production, cần kiểm tra `batchId`, `lineId`, SKU, số lượng, số phần tử tối đa và trường hợp danh sách null. Splitter không tự kiểm tra nghiệp vụ.

## 4. Dùng Java DSL với split() mặc định

Khi **payload đầu vào đã là collection**, cách đơn giản nhất là `split()`.

~~~java
// InventorySplitFlowConfiguration.java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration(proxyBeanMethods = false)
public class InventorySplitFlowConfiguration {

    @Bean
    MessageChannel inventoryBatchInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow inventoryLineFlow(
            MessageChannel inventoryBatchInput,
            InventoryLineProcessor processor) {

        return IntegrationFlow.from(inventoryBatchInput)
                .split()
                .handle(InventoryLine.class,
                        (line, headers) -> {
                            processor.process(line);
                            return null;
                        })
                .get();
    }
}
~~~

`InventoryLineProcessor` là port xử lý một dòng, ví dụ:

~~~java
// InventoryLineProcessor.java
public interface InventoryLineProcessor {
    void process(InventoryLine line);
}
~~~

Mỗi message có một `InventoryLine` được chuyển tới handler. Lệnh `return null` trong handler ở đây thể hiện **one-way endpoint không phát reply payload**; điều đó phù hợp khi không cần aggregation ở phía sau. Nếu muốn gộp kết quả bằng Aggregator, handler phải phát một kết quả tương ứng, không trả null.

### 4.1. Gửi batch vào input channel

~~~java
import java.util.List;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public class InventoryBatchPublisher {

    private final MessageChannel input;

    public InventoryBatchPublisher(
            MessageChannel inventoryBatchInput) {
        this.input = inventoryBatchInput;
    }

    public void publish(InventoryBatch batch) {
        boolean accepted = input.send(
                MessageBuilder.withPayload(batch.lines())
                        .setHeader("batchId", batch.batchId())
                        .build());

        if (!accepted) {
            throw new IllegalStateException(
                    "Không chuyển được batch vào IntegrationFlow");
        }
    }
}
~~~

`MessageBuilder.withPayload(...)` **không chấp nhận payload null**; kiểm tra `batch.lines()` trước khi gửi. Với `DirectChannel`, `send(...)` thường gọi downstream **đồng bộ trên cùng thread**; nếu handler lỗi, exception có thể được ném ra trước khi `send` hoàn tất.

Đoạn code tạo một Spring message có payload `List<InventoryLine>` và header nghiệp vụ `batchId`; đây là kiểu payload phù hợp với `split()` mặc định.

**Lưu ý thiết kế:** nếu đã nhận một `InventoryBatch` thay vì `List<InventoryLine>`, đừng kỳ vọng `split()` tự tìm property `lines` của mọi domain record. Có thể **transform** batch thành danh sách trước split, hoặc dùng method splitter tùy biến, như mục tiếp theo.

### 4.2. Kiểm soát số lượng phần tử

Một batch chứa 2 item tạo 2 message, batch chứa 100.000 item có thể tạo lượng xử lý lớn. Vì vậy:

- Giới hạn `maxItemsPerBatch` ở ingress.
- Dùng paging/chunking khi đọc database hoặc tệp lớn.
- Không materialize một list khổng lồ nếu nguồn có thể stream.
- Nếu dùng queue/executor phía sau, chọn capacity và policy quá tải.
- Theo dõi số item đầu vào và số item thật sự hoàn thành.

Không giả định tách 100.000 phần tử qua Java DSL sẽ tự cung cấp **backpressure end-to-end** với mọi loại channel và transport.

## 5. Dùng @Splitter khi payload là một đối tượng batch

Nếu input payload là `InventoryBatch`, có thể khai báo method splitter:

~~~java
// InventoryBatchSplitter.java
import java.util.List;
import org.springframework.integration.annotation.Splitter;
import org.springframework.stereotype.Component;

@Component
public class InventoryBatchSplitter {

    @Splitter(
            inputChannel = "inventoryBatchRequests",
            outputChannel = "inventoryLines")
    public List<InventoryLine> split(
            InventoryBatch batch) {

        if (batch.lines() == null) {
            throw new IllegalArgumentException(
                    "InventoryBatch.lines không được null");
        }

        return List.copyOf(batch.lines());
    }
}
~~~

Chỉ cần publisher gửi `InventoryBatch` vào channel `inventoryBatchRequests` và downstream subscribe `inventoryLines` theo đúng định nghĩa flow. Method được Spring Integration gọi, kết quả `List<InventoryLine>` trở thành các phần tử output của splitter.

**Phân biệt:** `@Splitter` là annotation riêng của Spring Integration. Nó không phải `@GetMapping` hoặc `@Async`; việc annotate method không tự tạo một HTTP endpoint hay thread pool mới.

Trong một ứng dụng thực, kiểm soát source channel names thống nhất và không vô tình đăng ký thêm một splitter DSL khác vào cùng input làm batch bị xử lý hai lần.

### 5.1. Có thể tách theo quy tắc nghiệp vụ

Ví dụ một batch chứa 200 dòng nhưng downstream chỉ nhận tối đa 50 dòng/lần. Khi đó splitter không nhất thiết trả về từng line; có thể chia thành **các chunk**:

~~~java
import java.util.ArrayList;
import java.util.List;

public List<List<InventoryLine>> splitChunks(
        InventoryBatch batch, int chunkSize) {

    if (chunkSize <= 0) {
        throw new IllegalArgumentException(
                "chunkSize phải > 0");
    }

    List<InventoryLine> lines = batch.lines();
    if (lines == null) {
        throw new IllegalArgumentException(
                "lines không được null");
    }

    List<List<InventoryLine>> chunks =
            new ArrayList<>();

    for (int start = 0; start < lines.size();
            start += chunkSize) {

        int end = Math.min(
                start + chunkSize, lines.size());

        chunks.add(List.copyOf(
                lines.subList(start, end)));
    }

    return chunks;
}
~~~

Nếu method này được nối làm splitter, mỗi output payload là **`List<InventoryLine>` của một chunk**, không phải một `InventoryLine`. Điều này thay đổi message contract của handler phía sau: có thể cần batch SQL insert hoặc HTTP bulk API thay vì single-item endpoint.

Chia chunk là một quyết định về **độ lớn đơn vị xử lý**, cần cân nhắc timeout, giới hạn HTTP body, throughput và phạm vi transaction.

## 6. DefaultMessageSplitter và custom splitter

### 6.1. Splitter mặc định xử lý dạng nào?

`DefaultMessageSplitter` có thể tách nhiều payload dạng tập hợp được hỗ trợ:

| Dạng payload | Kết quả thường gặp | Lưu ý |
| --- | --- | --- |
| `List<Item>` / `Collection<Item>` | Một message cho mỗi item | Kích thước biết trước |
| Java array | Một message cho mỗi phần tử | Cần xem kiểu phần tử |
| `Map<K,V>` | Các phần tử kiểu `Map.Entry` | Không tự biến thành V |
| Iterator/Iterable/stream khi version hỗ trợ | Theo lần duyệt | Kích thước có thể không biết trước |
| Domain object `InventoryBatch` | **Không mặc định biết property lines** | Dùng method tùy biến |

Không dựa vào việc một provider trả `Stream`/`Iterator` là tương đương một collection có kích thước sẵn. Stream có thể tiêu thụ một lần, đọc dữ liệu lười và phụ thuộc tài nguyên còn mở. Nếu một iterator đang dựa trên JDBC ResultSet mà transaction đóng trước khi splitter tiêu thụ hết, flow có thể thất bại giữa chừng.

### 6.2. Khi nào viết AbstractMessageSplitter?

Custom splitter hữu ích nếu phải:

- Phân tích một file batch dạng phức tạp.
- Tách payload theo business segmentation hoặc JSON nested paths.
- Phát output `Message<?>` riêng có headers nghiệp vụ khác nhau.
- Chia các khối theo window, trang hoặc kích thước tối đa.
- Kiểm tra payload trước khi bắt đầu fan-out.

Spring Integration cung cấp `AbstractMessageSplitter` làm base class. Với những bài toán đơn giản, method `@Splitter` hoặc Java DSL thường dễ hiểu và dễ kiểm thử hơn custom class.

Nếu custom splitter tạo `Message<?>` cho từng phần tử, không nên copy nguyên `id`/`timestamp` hay tự ghi đè tất cả sequencing headers một cách tùy tiện. Trách nhiệm xác định identity của từng message con và correlation phải được kiểm thử với các endpoint phía sau.

### 6.3. Splitter không phải JSON parser

Với HTTP inbound JSON:

~~~text
HTTP JSON → DTO/record → List<InventoryLine> → Splitter
~~~

Để biến JSON thành Java object, dùng HTTP message conversion/Jackson hoặc transformer phù hợp. Splitter không thay thế JSON schema validation hoặc type mapping. Nếu broker consumer nhận byte[] JSON, đừng dùng splitter lên byte[] rồi vô tình tạo một message cho từng byte; hãy decode/validate payload trước.

## 7. Headers correlation và sequence metadata

Khi một message đầu vào được chia thành nhiều message con, Aggregator cần biết **message nào thuộc cùng batch** và **đã nhận đủ chưa**. Spring Integration hỗ trợ các headers thường gặp:

| Header | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `correlationId` | Nhận diện nhóm con cùng nguồn | ID của original request/split group |
| `sequenceNumber` | Số thứ tự của message con | 1, 2, 3 |
| `sequenceSize` | Tổng số phần tử dự kiến của sequence | 3 |
| `id` | ID Spring message riêng | UUID cho từng output message |
| `timestamp` | Thời gian tạo message | Thời điểm của message |
| `batchId` (tùy biến) | Business ID ổn định theo lô | B-2026-001 |
| `lineId` (tùy biến) | Business ID ổn định theo dòng | L-1 |

Một output ví dụ:

~~~text
Message<InventoryLine L-2>
  correlationId = 7b...          (correlation của split)
  sequenceNumber = 2
  sequenceSize = 3
  batchId = B-2026-001
  id = UUID khác với message L-1
~~~

**Điểm khác biệt quan trọng:**

- `correlationId` của Splitter là metadata kỹ thuật để nhóm các message trong một quá trình split.
- `batchId` / `lineId` là khóa nghiệp vụ để truy xuất, đối soát và chống xử lý trùng.
- Nếu cùng business batch được **split lại do retry/replay**, correlation ID kỹ thuật có thể thay đổi.
- `sequenceNumber` chỉ cho biết vị trí trong kết quả tách, không đủ làm idempotency key dài hạn.
- `sequenceSize` hữu ích khi tập phần tử có kích thước xác định; với nguồn streaming/iterator có kích thước chưa biết, không được giả định luôn có tổng chính xác.

### 7.1. Header sequence có được áp dụng tự động?

`AbstractMessageSplitter` có tính năng **apply sequence** để gắn correlation/sequence cho output. Chính sách mặc định và cách cấu hình có thể khác nhau giữa các đời Spring Integration, endpoint và những kiểu split đặc biệt; khi downstream phụ thuộc vào Aggregator/Resequencer, hãy **kiểm tra trên phiên bản đang sử dụng và cấu hình rõ**.

Ví dụ ý tưởng cấu hình splitter:

~~~java
import org.springframework.integration.splitter.DefaultMessageSplitter;

DefaultMessageSplitter splitter =
        new DefaultMessageSplitter();

splitter.setApplySequence(true);
~~~

Đây là snippet tạo splitter; để được dùng trong pipeline, nó phải được đăng ký thành endpoint/bean qua Java DSL hoặc XML config tương ứng. Việc bật apply sequence không tự giải quyết vấn đề **nhóm chờ kết quả thất bại hoặc bị filter bỏ**.

### 7.2. Không tự làm hỏng headers khi transform

Một transformer phía sau splitter có thể tạo output mới. Nếu transformer trả payload mới qua Spring Integration endpoint thông thường, framework có cơ chế quản lý/copy các header phù hợp. Nếu code tự xây một `Message<?>` mới rồi chỉ đặt payload, có nguy cơ mất `correlationId` và sequence metadata.

Khi kết hợp `split → transform → aggregate`, cần test rằng output từ transformer **vẫn mang headers cần cho aggregator**. Đừng giữ nguyên một header lỗi thời qua các lần nested split rồi khiến hai nhóm khác nhau bị nhập chung.

## 8. Kết hợp Splitter → Handler/Transformer → Aggregator

Một cách dùng phổ biến là tách batch, xử lý từng item và ghép kết quả:

~~~mermaid
flowchart LR
    A["Message<List<OrderLine>>"] --> B["Splitter"]
    B --> C1["OrderLine 1"]
    B --> C2["OrderLine 2"]
    B --> C3["OrderLine 3"]
    C1 --> D["Pricing transformer"]
    C2 --> D
    C3 --> D
    D --> E["Aggregator"]
    E --> F["Message<List<PricedLine>>"]
~~~

Ví dụ domain:

~~~java
public record OrderLine(
        String lineId, String sku, int quantity) {
}

public record PricedLine(
        String lineId, long totalMinor) {
}

public interface PricingService {
    PricedLine price(OrderLine line);
}
~~~

Một Java DSL minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration(proxyBeanMethods = false)
public class PricingFlowConfiguration {

    @Bean
    IntegrationFlow pricingFlow(PricingService pricingService) {
        return IntegrationFlow.from("pricingInput")
                .split()
                .handle(OrderLine.class,
                        (line, headers) ->
                                pricingService.price(line))
                .aggregate()
                .channel("pricingResults")
                .get();
    }
}
~~~

Ở đây:

1. Input là `List<OrderLine>`.
2. Splitter tạo một message cho mỗi `OrderLine`.
3. Handler trả **`PricedLine`** thay vì null.
4. Aggregator thu các message cùng correlation, chờ điều kiện release.
5. Output là một message nhóm, thường là tập các `PricedLine`.

Ví dụ mô tả **happy path** với sequence information đầy đủ và mọi item đều trả kết quả. `pricingResults` cần channel/consumer phù hợp với môi trường sử dụng; nếu một gateway mong đợi reply thì cấu hình reply routing cũng phải đúng. Không dùng ví dụ này như bảo đảm aggregator luôn hoàn tất khi có lỗi, filter, timeout hoặc streaming size không xác định.

### 8.1. Vì sao Filter sau Splitter có thể làm Aggregator đợi mãi?

Giả sử splitter phát 3 item, `sequenceSize=3`. Một `Filter` loại item thứ hai mà **không gửi replacement/completion message**. Aggregator lúc này chỉ nhận 2 item, vẫn chờ số lượng 3 và có thể không release.

Cách xử lý phụ thuộc nghiệp vụ:

- **Lọc trước khi split**, sao cho sequence size phản ánh số item thực cần xử lý.
- **Trả một kết quả cho mọi input**, ví dụ `Processed` / `Skipped` / `Failed`, để Aggregator vẫn nhận đủ.
- Tùy chỉnh release strategy theo business completion count.
- Có group timeout và policy rõ cho incomplete groups.
- Nếu không cần ghép, đừng thêm Aggregator chỉ vì đã dùng Splitter.

Không tự đặt `sequenceSize=2` trên vài message khi đã có 3 output từ Splitter mà không kiểm soát correlation toàn nhóm.

### 8.2. Aggregator cần lưu trạng thái nhóm

Aggregator giữ **message group** cho tới khi đủ điều kiện release. Với flow xử lý lâu, nhiều batch đồng thời hoặc restart giữa chừng, cần quyết định:

- Message group store là in-memory hay persistent?
- Group timeout bao lâu?
- Khi quá hạn: bỏ nhóm, gửi partial result hay đánh dấu lỗi?
- Ai cleanup completed/expired groups?
- Nếu một item được gửi lại, Aggregator nhận diện duplicate ra sao?
- Nếu sequence metadata thiếu hoặc sai, nhóm được release thế nào?

Spring Integration có `MessageGroupStore` và các triển khai có thể lưu group lâu dài khi cấu hình phù hợp, nhưng **persistent group store không tự tạo exactly-once**. Các message đã xử lý side effect ở downstream vẫn phải có idempotency.

### 8.3. Resquencer khác Aggregator

**Resequencer** tổ chức các message theo thứ tự sequence, thường tiếp tục phát **từng message**. **Aggregator** gộp nhiều message thành **một kết quả**.

Nếu mục tiêu chỉ là lưu các dòng theo thứ tự business, có thể cần thứ tự ở DB hoặc một serialized channel; dùng Aggregator để gom lại rồi sort theo `lineId` đôi khi dễ quản lý hơn. Với concurrency, không dựa vào thời điểm completion để suy ra thứ tự ban đầu.

## 9. Xử lý đồng bộ và bất đồng bộ sau split

Bản chất split không cấp nhiều thread. **Channel** quyết định ranh giới thực thi.

| Channel | Tính chất thường gặp | Điều cần lưu ý |
| --- | --- | --- |
| `DirectChannel` | Dispatch đồng bộ trong thread caller | Error có thể ném ngược về sender; chậm một item làm cả flow chậm |
| `ExecutorChannel` | Dispatch qua `TaskExecutor` | Chạy song song, thay đổi thread và transaction context |
| `QueueChannel` | Lưu message trong queue nội bộ, consumer/poller đọc | Phải giới hạn capacity và quản lý startup/shutdown |
| `PublishSubscribeChannel` | Phân phối cùng một message cho nhiều subscribers | Không phải splitter, có thể kết hợp |
| Broker channel/adapter | Hàng đợi bền vững tùy broker và cấu hình | Ack/redelivery/idempotency cần thiết |

### 9.1. Đồng bộ: tất cả item được xử lý trên thread caller

~~~text
Inbound handler
  └─ DirectChannel → Splitter
      ├─ Item 1 → service call (xong)
      ├─ Item 2 → service call (xong)
      └─ Item 3 → service call (xong)
  → send() hoàn tất
~~~

Ưu điểm: đơn giản, dễ theo dõi exception, có thể tham gia transaction cục bộ nếu ranh giới được cấu hình phù hợp. Hạn chế: một item chậm có thể giữ HTTP request thread hoặc broker listener lâu, gây timeout, tăng backlog và ảnh hưởng throughput.

### 9.2. Bất đồng bộ: ExecutorChannel

Cấu hình minh họa một bounded thread pool:

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class InventoryAsyncChannelConfiguration {

    @Bean
    ThreadPoolTaskExecutor inventoryExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("inventory-item-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.initialize();

        return executor;
    }

    @Bean
    ExecutorChannel inventoryWorkChannel(
            ThreadPoolTaskExecutor inventoryExecutor) {
        return new ExecutorChannel(inventoryExecutor);
    }
}
~~~

Nếu muốn thực hiện sau split bất đồng bộ, nối output của splitter đến bean channel `inventoryWorkChannel` rồi đặt handler kế tiếp sau channel đó. Ví dụ DSL concept:

~~~java
return IntegrationFlow.from(inventoryBatchInput)
        .split()
        .channel(inventoryWorkChannel)
        .handle(InventoryLine.class,
                (line, headers) -> {
                    processor.process(line);
                    return null;
                })
        .get();
~~~

Snippet là **thân phương thức bean** có các biến `inventoryBatchInput`, `inventoryWorkChannel` và `processor` được inject; không phải class đầy đủ. Khi thread pool đầy và queue đạt giới hạn, `AbortPolicy` báo rejected execution. Phải chuyển lỗi này thành retry/DLQ/backpressure phù hợp, không để âm thầm mất message.

**Transaction context không tự đi theo thread mới.** Nếu message được ack ở broker hoặc HTTP trả response trước khi các task async hoàn tất, lỗi của item sau đó sẽ không tự rollback/throw về caller. Cần thiết kế **handoff durable**, completion tracking và error handling.

### 9.3. QueueChannel và backpressure

`QueueChannel` có thể giữ message trong RAM giữa splitter và poller/consumer. Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.QueueChannel;

@Bean
QueueChannel inventoryPendingQueue() {
    return new QueueChannel(500);
}
~~~

Đây là queue **bounded trong memory**, không tương đương broker durable. Nếu process crash, những message chỉ ở RAM sẽ mất. Nếu cần không mất việc, dùng broker bền vững hoặc ghi từng item work vào SQL outbox/work table trước khi ack batch inbound.

Việc gửi qua queue có capacity hữu hạn cần policy khi đầy: block có timeout, reject, retry có backoff hoặc chuyển vào durable store. Không dùng queue không giới hạn để che downstream bị chậm vì có thể gây out-of-memory.

## 10. Splitter và ranh giới transaction

Giả sử một batch gồm L1, L2, L3 cần cập nhật một database. Có hai chiến lược khác nhau.

### 10.1. Một transaction bao trùm cả batch

Nếu toàn bộ quá trình là **đồng bộ, trên cùng thread, cùng transaction manager**, có thể đặt transaction ở service gọi flow. Khi L2 lỗi, có thể rollback các SQL changes của L1/L2/L3 trong cùng transaction nếu các điều kiện transaction đúng.

Nhưng:

- L1 có thể đã gọi HTTP, phát broker hoặc gửi email; những tác động đó **không rollback** cùng SQL.
- Một transaction bao trùm nhiều dòng có thể giữ connection/lock rất lâu.
- Khi chuyển sang `ExecutorChannel`, transaction thread-local ban đầu **không tự bao trùm** các worker threads.
- Nếu handler catch và nuốt exception, transaction có thể commit dù một item lỗi.

### 10.2. Mỗi item có transaction riêng

Một lựa chọn hay gặp là mỗi `InventoryLine` được xử lý trong một transaction ngắn:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JdbcInventoryLineProcessor
        implements InventoryLineProcessor {

    private final InventoryRepository repository;

    public JdbcInventoryLineProcessor(
            InventoryRepository repository) {
        this.repository = repository;
    }

    @Override
    @Transactional
    public void process(InventoryLine line) {
        repository.applyInventoryChange(
                line.lineId(), line.sku(), line.quantity());
    }
}
~~~

`InventoryRepository` là port minh họa; implementation phải sử dụng cơ chế **claim/idempotent update** phù hợp. Nếu chỉ cộng số lượng tồn kho mỗi lần gọi mà không kiểm tra `lineId` đã xử lý, broker redelivery hoặc retry sẽ làm số tồn sai.

Chọn transaction per item khi muốn retry từng dòng độc lập, song phải có nơi lưu **trạng thái batch** và chính sách partial failure. Không có transaction chung giữa các item có nghĩa L1 có thể commit dù L2 thất bại.

### 10.3. Handoff bền vững trước khi split

Với batch rất quan trọng nhận từ HTTP/broker, cân nhắc:

~~~mermaid
flowchart LR
    A["Inbound batch"] --> B["Validate whole batch"]
    B --> C["SQL transaction: batch + work items"]
    C --> D["Commit + acknowledge inbound"]
    D --> E["Worker claims items"]
    E --> F["Process item"]
    F --> G["Persist outcome"]
    G --> H["Batch completion / aggregate status"]
~~~

Điểm mấu chốt: **lưu các item hoặc ý định xử lý** bền vững trước khi ack nguồn. Nếu splitter chỉ phát vào RAM rồi broker source được ack ngay, process crash có thể làm mất những item chưa xử lý.

Không có một cấu hình Splitter duy nhất tự đảm bảo handoff durable; phải xác định nguồn message, channel, transaction manager, broker ack và business work table.

## 11. Idempotency cho từng item và cả batch

Message headers `correlationId` và `sequenceNumber` phục vụ flow. Chống xử lý trùng phải dựa vào **business identity** có thể ổn định qua retry.

Khóa thường dùng:

- `batchId`: định danh lô nghiệp vụ.
- `lineId` hoặc `(batchId, lineId)`: định danh phần tử.
- `sourceVersion`: version của thay đổi từ upstream.
- `operationType`: phân biệt cập nhật/tạo/xóa khi cùng lineId có nhiều tác động hợp lệ.

Ví dụ bảng SQL PostgreSQL:

~~~sql
CREATE TABLE processed_inventory_lines (
    batch_id VARCHAR(100) NOT NULL,
    line_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (batch_id, line_id)
);
~~~

Một SQL claim minh họa:

~~~sql
INSERT INTO processed_inventory_lines(
    batch_id, line_id, processed_at)
VALUES (?, ?, CURRENT_TIMESTAMP)
ON CONFLICT (batch_id, line_id) DO NOTHING;
~~~

Nếu thao tác insert trả **số dòng được ghi = 0**, dòng đã được claim/xử lý trước đó theo hợp đồng; không nên áp dụng thay đổi tồn kho lần nữa. **Quan trọng:** việc claim và business update phải ở **cùng một transaction**; nếu claim commit rồi update lỗi, retry có thể bỏ qua dòng chưa thực sự xử lý.

Với tồn kho nhận nhiều version cho cùng SKU, business unique key có thể cần `sourceEventId` hoặc version cụ thể. Chọn khóa dedupe theo ý nghĩa event, không chỉ theo vị trí của phần tử trong danh sách.

### 11.1. Vì sao sequenceNumber không đủ?

Nếu batch lần đầu chứa `[L1, L2, L3]`, L2 có `sequenceNumber=2`. Khi upstream retry với một batch đã được lọc `[L2, L3]`, L2 có thể thành sequence 1. Dựa vào sequence làm idempotency key sẽ thất bại.

Nếu một batch được phát lại, `Message.id` và Splitter correlation metadata có thể mới hoàn toàn. **Business key cần độc lập với cách fan-out**.

## 12. Xử lý lỗi một phần và quyết định retry

Giả sử L1 xử lý thành công, L2 gặp HTTP 503 và L3 chưa chạy. Hành vi khác nhau tùy channel/transaction:

| Kiểu flow | Hậu quả có thể xảy ra | Điều cần quyết định |
| --- | --- | --- |
| `DirectChannel` đồng bộ, exception lan ra | Sender nhận lỗi; các item trước đó có thể đã side effect | Rollback/replay/idempotency |
| `ExecutorChannel` async, một item lỗi | Lỗi xuất hiện ở worker/error channel | Retry item, DLQ, batch completion |
| `QueueChannel` trong RAM, process crash | Message chưa tiêu thụ có thể mất | Cần durable queue/store |
| Broker durable per item | Broker có thể redeliver khi chưa ack | Inbox/unique constraint theo item |
| Split → transform → aggregate | Thiếu output của item lỗi | Timeout/partial result/failure marker |
| Split + filter | Output bị bỏ theo policy | Điều chỉnh sequence/release strategy |

### 12.1. Lỗi message và errorChannel

Spring Integration có cơ chế `errorChannel` và `ErrorMessage` cho các tình huống phù hợp, đặc biệt với ranh giới bất đồng bộ. Exception từ handler có thể được wrap thành `MessageHandlingException` hoặc các lỗi messaging khác, chứa failed message giúp chẩn đoán.

**Không assume mọi lỗi đều xuất hiện trên errorChannel.** Với flow hoàn toàn đồng bộ qua DirectChannel, exception thường được ném lên caller. Với async task/broker listener, cách publish error message phụ thuộc poller, adapter, channel và error handler được cấu hình.

Khi thiết kế:

- Phân loại validation error (vĩnh viễn), network/429/503 (tạm thời), timeout có outcome không xác định.
- Đưa vào retry policy có số lần hữu hạn và backoff/jitter.
- Lưu bản ghi thất bại kèm `batchId`/`lineId` trong audit/work table.
- Gửi dead-letter/parking lot message khi không thể xử lý tự động.
- Không đưa raw payload hoặc thông tin nhạy cảm vào logs/error descriptions.
- Nếu có Aggregator, phát `FailedLine` result hoặc quyết định release partial group rõ ràng.

### 12.2. Mẫu kết quả một dòng

Một model đầu ra có thể giữ trạng thái đầy đủ:

~~~java
public record LineResult(
        String batchId,
        String lineId,
        LineStatus status,
        String errorCode) {

    public enum LineStatus {
        APPLIED,
        DUPLICATE,
        SKIPPED,
        FAILED
    }
}
~~~

Với kiểu này, nếu nghiệp vụ muốn có **báo cáo cuối batch**, handler có thể phát một `LineResult` cho **mọi input line**, bao gồm cả lỗi đã được phân loại, thay vì nuốt lỗi rồi không phát message. Lỗi hạ tầng chưa thể xác định outcome có thể cần lưu PENDING_RETRY thay vì kết luận FAILED vĩnh viễn.

Aggregator nhận đủ messages nhưng **business status** vẫn cần xét: có thể phải trả kết quả `PARTIALLY_SUCCEEDED` thay vì coi group đã đủ sequence là thành công.

## 13. Thứ tự xử lý và kết quả đầu ra

Một danh sách đầu vào có thứ tự `[L1, L2, L3]` không đồng nghĩa **thứ tự hoàn thành** cũng như vậy khi xử lý async:

~~~text
Split order:
  L1 → L2 → L3

Completion with parallel workers:
  L3 (120ms) → L1 (500ms) → L2 (800ms)
~~~

Nếu cần giữ thứ tự cho cùng một aggregate/SKU/account:

- Route các item của cùng business key vào một **partition/serialized consumer**.
- Dùng một worker cho những keys phải tuần tự.
- Ghi `sourceVersion` và kiểm soát update theo optimistic locking/version.
- Dùng Resquencer khi cần sắp lại message outputs theo sequence.
- Hoặc gom kết quả rồi **sort theo business order** trước khi sử dụng.

Không dùng Resquencer để “sửa” một lần side effect sai thứ tự đã commit ở database. Nếu điều kiện đúng đắn là “không áp dụng event version 5 trước version 4”, logic update/locking cần bảo vệ ngay ở repository/consumer.

### 13.1. Nested split và correlation

Có thể chia file thành chunks, rồi mỗi chunk lại chia thành lines:

~~~text
FileBatch
  ├─ Chunk 1
  |   ├─ Line 1
  |   └─ Line 2
  └─ Chunk 2
      ├─ Line 3
      └─ Line 4
~~~

Mỗi cấp có thể cần correlation khác nhau: file ID, chunk ID, line ID. Đừng để header correlation của cấp bên trong ghi đè rồi làm Aggregator cấp ngoài nhóm sai. Khi nested split/gather, phải thiết kế hierarchy của metadata hoặc dùng business keys riêng; kiểm thử grouping thực tế.

## 14. Large payload: file, CSV và database batches

### 14.1. FileSplitter và line-oriented processing

Spring Integration có các adapter và splitter chuyên cho file/text trong module phù hợp, ví dụ `FileSplitter` xử lý nội dung file theo dòng/marker tùy cấu hình. Không cần đọc toàn bộ file khổng lồ thành một `List<String>` mới dùng `DefaultMessageSplitter`.

Luồng thực tế:

~~~text
File inbound adapter
   ↓
Validate file metadata + size
   ↓
FileSplitter / line reader
   ↓
Parse CSV row → DTO
   ↓
Validate record
   ↓
Batch insert / HTTP adapter
   ↓
Checkpoint + result
~~~

Cần chú ý:

- Charset/BOM, CSV quoting và escaping.
- Tệp có header/trailer và bản ghi không hợp lệ.
- Giới hạn line length/row count, không để payload cực lớn gây OOM.
- Duplicate rows, checkpoint và trạng thái file sau lỗi.
- File move/archive chỉ khi xử lý đủ theo contract.
- Nếu một line bị lỗi, xác định fail whole file hay quarantine line đó.

### 14.2. Database paging thay vì tải toàn bộ

Khi một reconciliation job đọc 2 triệu dòng SQL, việc `SELECT *` rồi split toàn bộ vào RAM thường là sai. Thay bằng:

1. Query có pagination/keyset theo khóa ổn định.
2. Tạo các work chunks có ID/version.
3. Ghi checkpoint sau mỗi chunk commit.
4. Split từng chunk thành items trong giới hạn có thể xử lý.
5. Tiếp tục từ checkpoint nếu crash, không reprocess mù.

**Cảnh báo với stream JDBC/JPA:** một cursor/stream thường gắn với connection/transaction. Nếu splitter xử lý bất đồng bộ sau khi scope transaction kết thúc, cursor có thể đóng. Với các job cần durability, materialize work items nhỏ hoặc store chúng trước khi chuyển thread/process.

### 14.3. Khác biệt từ cấu hình transport

Một request REST có thể có timeout 2 giây; một batch 5.000 items không nên xử lý đồng bộ toàn bộ trong request rồi trả 200 chỉ vì đã nhận. Có thể trả 202 Accepted kèm batch ID nếu hợp đồng cho phép, lưu work durable, xử lý phía sau rồi cung cấp status endpoint.

Tương tự, broker consumer không nên ack một batch trước khi các items đã được nhận trách nhiệm bền vững bởi downstream, nếu contract đòi không mất việc.

## 15. Thiết kế quan sát batch-level và item-level

Splitter là nơi fan-out, nên **đếm số batch không đủ để hiểu tải item**.

| Metric/Observation | Ý nghĩa |
| --- | --- |
| `integration.batch.received` | Số batch nhận vào |
| `integration.batch.size` | Phân bố số item trong batch |
| `integration.item.started` | Số item bắt đầu xử lý |
| `integration.item.completed` | Kết quả item success/duplicate/skipped/failure |
| `integration.item.duration` | Latency từng item |
| `integration.item.retry` | Attempt/retry count |
| `integration.batch.completed` | Batch hoàn tất, đủ theo contract |
| `integration.queue.depth` | Backlog/buffer sau splitter |
| `integration.batch.oldest.age` | Batch tồn đọng lâu nhất |
| `integration.deadletter.count` | Item cần xử lý thủ công |

**Không tự cộng “đã split thành N message” thành “đã xử lý thành công N bản ghi”.** Nếu downstream lỗi/timeout/rollback, output count chỉ cho biết splitter đã phát message.

### 15.1. Một Observation cho xử lý item

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class ObservedInventoryLineProcessor
        implements InventoryLineProcessor {

    private final InventoryRepository repository;
    private final ObservationRegistry registry;

    public ObservedInventoryLineProcessor(
            InventoryRepository repository,
            ObservationRegistry registry) {
        this.repository = repository;
        this.registry = registry;
    }

    @Override
    public void process(InventoryLine line) {
        Observation.createNotStarted(
                        "integration.inventory.item.process",
                        registry)
                .lowCardinalityKeyValue(
                        "operation", "apply_inventory")
                .observe(() ->
                        repository.applyInventoryChange(
                                line.lineId(),
                                line.sku(),
                                line.quantity()));
    }
}
~~~

`InventoryRepository` là cổng nghiệp vụ minh họa. Code đo **method synchronous**; khi underlying operation là reactive/asynchronous, không đặt observation chỉ quanh thao tác tạo `Mono`/`CompletableFuture` rồi cho rằng nó đo toàn bộ thời gian thực thi. Cần bắt lifecycle completion và context propagation đúng.

Tag phù hợp: `flow=inventory-import`, `operation=apply_inventory`, `outcome=success/error` với tập giá trị nhỏ. Không dùng `batchId`, `lineId`, SKU riêng lẻ hoặc `correlationId` làm metric labels vì cardinality rất cao.

### 15.2. Distributed tracing qua async boundary

Với `DirectChannel` synchronous, trace context thường ở thread hiện tại khi instrumentation được cấu hình. Khi dùng `ExecutorChannel`, broker hoặc một hệ thống ngoài, trace context có thể không tự đi theo mọi ranh giới nếu executor/transport không được instrument.

Một trace của batch có thể liên kết nhiều item spans, nhưng cần:

- Quyết định sampling vì fan-out hàng nghìn item tạo nhiều spans.
- Truyền context qua boundary theo cơ chế Micrometer/Spring hỗ trợ.
- Không biến trace/span ID thành idempotency key.
- Có business correlation IDs trong audit log được bảo vệ để đối soát các lần retry.
- Đo cả batch completion và final business state, không chỉ HTTP request nhận batch.

## 16. Kiểm thử Splitter và các headers đầu ra

Kiểm thử nên ở **ba cấp**: pure split logic, messaging flow wiring và end-to-end transaction/retry.

### 16.1. Unit test hàm chia chunk

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ChunkSplitTest {

    @Test
    void dividesFiveLinesIntoThreeChunks() {
        var batch = new InventoryBatch(
                "B-1",
                List.of(
                        new InventoryLine("L-1", "P1", 1),
                        new InventoryLine("L-2", "P2", 1),
                        new InventoryLine("L-3", "P3", 1),
                        new InventoryLine("L-4", "P4", 1),
                        new InventoryLine("L-5", "P5", 1)));

        var chunks = splitChunks(batch, 2);

        assertEquals(3, chunks.size());
        assertEquals(2, chunks.get(0).size());
        assertEquals(2, chunks.get(1).size());
        assertEquals(1, chunks.get(2).size());
    }

    // splitChunks(...) là hàm minh họa ở mục 5.1,
    // có thể được đặt vào service được inject.
}
~~~

Đây là unit-test sketch; để compile, đặt `splitChunks` vào class fixture/service phù hợp và gọi instance/static method tương ứng. Test cần bổ sung danh sách rỗng, `chunkSize=0`, `chunkSize=1` và biên batch rất lớn.

### 16.2. Spring Integration test với QueueChannel

Một flow test có thể dùng `QueueChannel` có capacity 10 để **thu các output messages** của splitter:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration(proxyBeanMethods = false)
public class SplitterTestConfiguration {

    @Bean
    MessageChannel batchInput() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel lineOutput() {
        return new QueueChannel(10);
    }

    @Bean
    IntegrationFlow testSplitFlow(
            MessageChannel batchInput,
            QueueChannel lineOutput) {
        return IntegrationFlow.from(batchInput)
                .split()
                .channel(lineOutput)
                .get();
    }
}
~~~

Test:

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = SplitterTestConfiguration.class)
class SplitterFlowTest {

    @Autowired
    @Qualifier("batchInput")
    MessageChannel batchInput;

    @Autowired
    @Qualifier("lineOutput")
    QueueChannel lineOutput;

    @Test
    void emitsOneMessagePerLine() {
        var lines = List.of(
                new InventoryLine("L-1", "P1", 1),
                new InventoryLine("L-2", "P2", 2));

        assertTrue(batchInput.send(
                MessageBuilder.withPayload(lines)
                        .setHeader("batchId", "B-1")
                        .build()));

        var first = lineOutput.receive(1000);
        var second = lineOutput.receive(1000);

        assertNotNull(first);
        assertNotNull(second);
        assertEquals("L-1",
                ((InventoryLine) first.getPayload()).lineId());
        assertEquals("L-2",
                ((InventoryLine) second.getPayload()).lineId());

        assertEquals("B-1",
                first.getHeaders().get("batchId"));
        assertEquals("B-1",
                second.getHeaders().get("batchId"));

        assertNull(lineOutput.receive(10));
    }
}
~~~

Test này kiểm tra output count, payload và business header, không kiểm tra sequence metadata. Khi flow phụ thuộc vào Aggregator, cần test **correlationId, sequenceNumber và sequenceSize theo cấu hình/version**. `QueueChannel` trong test không đại diện cho durability production.

### 16.3. Test các lỗi quan trọng

| Tình huống | Điều cần assert |
| --- | --- |
| Input collection rỗng | Không sinh message ngoài contract, batch hoàn tất theo quy tắc |
| Input null | Fail validation trước khi split |
| Batch cực lớn | Giới hạn hoặc chia chunk, không OOM |
| Message có business headers | Header cần thiết không bị mất |
| apply sequence | Correlation và sequence hợp lệ cho group |
| Transformer trả kết quả | Aggregator có đủ output để release |
| Filter bỏ một item | Group không chờ vô hạn nếu policy yêu cầu hoàn thành |
| Handler ném exception ở item 2 | Side effects và retry theo ranh giới transaction |
| Executor queue full | Rejection không làm mất item âm thầm |
| Crash sau inbound ack | Durable handoff bảo vệ item chưa xử lý |
| Duplicate broker delivery | Cùng business key không apply lần hai |
| Parallel out-of-order completion | Business state vẫn đúng theo version |
| Nested split/aggregate | Correlation cấp ngoài/cấp trong không trộn lẫn |

### 16.4. Không coi unit test Splitter là test transactional integration

Test Java DSL chỉ chứng minh routing/wiring ở mức Spring messaging. Với xử lý thật, cần integration test PostgreSQL/Testcontainers, HTTP stub và/hoặc broker test fixture để xác minh:

1. Inbox/outbox/checkpoint được ghi **cùng transaction** với business updates khi yêu cầu.
2. Message ACK phù hợp thời điểm nhận trách nhiệm bền vững.
3. Crash/replay không làm phát duplicate business effects.
4. Một item fail không làm mất những item chưa xử lý.
5. Completion status của batch chỉ đạt success khi hợp đồng nghiệp vụ cho phép.

## 17. Những lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Splitter phát một message duy nhất chứa cả batch | Input chưa đúng kiểu collection hoặc method không phải splitter | Kiểm tra payload/annotation/flow |
| `@Splitter` không chạy | Input channel chưa được wire, thiếu integration config | Kiểm tra bean scan/channel names |
| Có 100 input items nhưng chỉ xử lý 99 | Filter/drop/error một item hoặc queue mất | Audit per item, error flow, durability |
| Tưởng split chạy song song nhưng vẫn chậm | `DirectChannel` synchronous | ExecutorChannel/broker có giới hạn |
| Chuyển async rồi mất transaction | Transaction context thread-local | Định nghĩa transaction mỗi item và durable handoff |
| Aggregator không release | Mất sequence, filter item, error hoặc size không biết | Release strategy, failure markers, timeout |
| Aggregator gộp lẫn hai batch | Correlation header sai/trùng hoặc nested split | Thiết kế correlation và test |
| Xử lý trùng sau retry | Dùng sequence/id message làm idempotency key | Business key ổn định + unique constraint |
| Pool/DB quá tải sau split | Fan-out không giới hạn và không backpressure | Chunk, queue capacity, concurrency budget |
| Mất message sau restart | Chỉ dùng QueueChannel RAM, ack upstream sớm | Broker durable/SQL work table/outbox |
| Data không theo thứ tự | Executor chạy song song | Version guards/partition/resequencer |
| XML/JSON byte[] bị tách thành phần tử sai | Split trước bước decode/validation | Deserialize/transform trước |
| Stream JDBC lỗi giữa chừng | Cursor/transaction đóng trước khi split hết | Materialize chunk hoặc quản lý stream scope |
| Metrics đếm split success như business success | Chỉ đo fan-out, không đo completion | Item outcome + batch completion |
| Lỗi item async không đến caller | Boundary ExecutorChannel/ErrorMessage | Error channel, retry/DLQ/audit |

## 18. Checklist trước khi vận hành Splitter

- [ ] Đã xác định rõ một message đầu vào chứa **collection, chunk hay domain batch object**.
- [ ] Chọn `split()` mặc định hoặc `@Splitter`/custom splitter phù hợp contract.
- [ ] Đã xử lý danh sách rỗng, null, giới hạn kích thước và phần tử không hợp lệ.
- [ ] Business headers (`batchId`, `lineId`, version) được bảo toàn theo flow.
- [ ] Nếu cần Aggregator, correlation/sequence metadata được cấu hình và kiểm thử.
- [ ] Filter/error sau split không làm Aggregator chờ vô hạn.
- [ ] Không giả định Splitter tự chạy song song; channel/thread model được thiết kế rõ.
- [ ] Thread pool và queue có capacity/concurrency limit, overflow/rejection policy.
- [ ] Đã xác định transaction boundary theo batch hay từng item, kể cả khi đổi thread.
- [ ] Upstream ACK chỉ diễn ra khi downstream/work items được nhận trách nhiệm theo durability contract.
- [ ] Idempotency dùng **business key ổn định**, không dùng technical sequence/message ID.
- [ ] Retry có giới hạn, phân loại lỗi và đường DLQ/reconciliation.
- [ ] Có chính sách order/version với các item cùng business aggregate.
- [ ] Có test Splitter output, headers, Aggregator, concurrency, crash/replay và duplicate.
- [ ] Metrics/trace phân biệt fan-out count, item completion, retry và backlog.

**Ghi nhớ:** Splitter tách một message thành **nhiều đơn vị xử lý**, nhưng không tự quyết định một đơn vị là bao lớn, có chạy song song không, transaction nằm đâu hay có thể retry an toàn không. Khi kết hợp `split → handle/transform → aggregate`, cần bảo toàn correlation/sequence và thiết kế xử lý phần tử thiếu. Khi kết hợp với HTTP/SQL/cache/broker trong Spring Boot, độ tin cậy phụ thuộc vào **hợp đồng dữ liệu, durable handoff, idempotency, transaction, error handling, kiểm thử và observability**.

## Tài liệu tham khảo

- [Spring Integration — Splitter](https://docs.spring.io/spring-integration/reference/splitter.html): Message Splitter, annotation, Java DSL và sequence metadata.
- [Spring Integration — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): correlation, release strategy, message groups.
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, ExecutorChannel, QueueChannel và các ranh giới xử lý.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): xử lý lỗi đồng bộ/bất đồng bộ, error channels.
- [Spring Integration — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): IntegrationFlow, endpoints và Java configuration.
- [Spring Boot — Spring Integration](https://docs.spring.io/spring-boot/reference/messaging/spring-integration.html): Spring Integration auto-configuration trong Boot.
- [Enterprise Integration Patterns — Splitter](https://www.enterpriseintegrationpatterns.com/patterns/messaging/Sequencer.html): mẫu chia một message thành các thành phần.
