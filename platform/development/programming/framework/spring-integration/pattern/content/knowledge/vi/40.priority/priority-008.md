# Đảm bảo priority được truyền đúng trong Spring Integration

## 1. Bài toán: một message có priority cao nhưng bị xử lý như message thường

Một dịch vụ đặt hàng nhận sự kiện `PaymentRiskDetected` từ HTTP, gán priority cao rồi chuyển qua các bước:

~~~mermaid
flowchart LR
    A["HTTP / Gateway"] --> B["Validate và gán priority"]
    B --> C["Transformer"]
    C --> D{"Router"}
    D --> E["Splitter"]
    E --> F["Aggregator"]
    F --> G["PriorityChannel"]
    G --> H["Service Activator"]
~~~

Tại đầu vào, hệ thống ghi log `priority=9`. Nhưng khi consumer nhận từ `PriorityChannel`, message lại có priority mặc định, hoặc thậm chí thiếu header `priority`. Nó phải chờ sau các message ít khẩn cấp hơn.

Nguyên nhân có thể đến từ nhiều nơi:

- Một Transformer tạo `Message` mới và **không giữ** header cần thiết.
- Một Gateway chỉ gửi payload, làm mất metadata hoặc chuyển sang một API không truyền được header mong muốn.
- Một Router chuyển message qua nhánh/adapter không hỗ trợ cùng hợp đồng priority.
- Một Splitter hoặc Aggregator tạo nhiều message mới, nhưng không có quy tắc priority cho từng message con hoặc kết quả tổng hợp.
- Một adapter đưa message sang JMS/RabbitMQ/Kafka mà **không ánh xạ** header nội bộ sang cơ chế ưu tiên tương ứng, hoặc broker không hỗ trợ/không bật priority.
- Giá trị priority được lưu dưới kiểu dữ liệu không hợp lệ, bị thay thế bởi default hoặc bị nguồn không đáng tin cậy tự nâng lên.

**Đảm bảo priority được truyền đúng** không chỉ là “gán `priority` vào một message”. Đó là một **hợp đồng metadata xuyên suốt**: định nghĩa giá trị, nơi phát sinh, phép biến đổi, cách đi qua EIP và adapter, tiêu chí kiểm thử, cùng bằng chứng tại điểm chọn message để xử lý.

Trong module `SPRING_INTEGRATION_PATTERN`, cách tổ chức này giúp Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation hoạt động ít phụ thuộc nhưng vẫn giữ đúng **ý định ưu tiên của nghiệp vụ**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Chuẩn hóa header `priority` và phân biệt **business priority** với **broker priority**.
2. Kiểm tra việc giữ headers khi tạo `Message` mới, transform, split, aggregate, route hoặc gọi Gateway.
3. Thiết kế bộ chuyển đổi priority rõ ràng tại ranh giới HTTP, JMS, RabbitMQ và Kafka.
4. Chống việc client tự gán HIGH không được cấp quyền hoặc gán giá trị sai định dạng.
5. Viết unit/integration test xác minh priority **ở từng boundary**, không chỉ ở producer.
6. Theo dõi trường hợp bị mất, hạ, nâng hoặc hiểu sai priority trong vận hành.

## 2. “Đúng priority” cần những điều kiện nào?

| Yêu cầu | Câu hỏi kiểm chứng |
| --- | --- |
| **Giá trị** | Priority là integer, enum hay một miền số rõ ràng? |
| **Ngữ nghĩa** | Số lớn hơn có nghĩa là quan trọng hơn không? |
| **Nguồn tin cậy** | Ai có quyền phân loại HIGH, NORMAL, LOW? |
| **Tính liên tục** | Khi message được tạo lại, priority có bị thiếu hoặc ghi đè không? |
| **Quy tắc phân nhánh** | Message con hoặc kết quả tổng hợp thừa kế, hạ, nâng priority ra sao? |
| **Tương thích adapter** | Header của Spring có được ánh xạ thành property/metadata mà đích sử dụng không? |
| **Tính quan sát được** | Có xác minh priority ở trước và sau mọi boundary quan trọng không? |
| **Tính đúng nghiệp vụ** | Priority có khiến tác vụ ít quan trọng bị đói hoặc tác vụ sai quyền chiếm worker không? |

Một cách thiết kế rõ ràng là định nghĩa hai khái niệm:

- **`businessPriority`**: quyết định do nghiệp vụ đưa ra, chẳng hạn `HIGH`, `NORMAL`, `LOW`; có thể là trường trong payload/metadata canonical.
- **`priority`**: giá trị số dùng cho một scheduler, `PriorityChannel` hoặc một adapter cụ thể; thường được sinh từ business priority.

Nếu producer gửi `businessPriority=HIGH` nhưng adapter đích chỉ hiểu số `priority`, phải có mapping rõ, kiểm tra đầu ra, và không giả định adapter tự hiểu enum nghiệp vụ.

## 3. Header priority trong Spring Messaging

Trong Spring Integration, `Message<T>` gồm:

~~~text
Message
  ├─ payload: nội dung nghiệp vụ
  └─ headers:
       id, timestamp,
       priority,
       correlationId, sequenceNumber,
       businessEventId, ...
~~~

Header dùng cho mức ưu tiên thường có tên **`priority`**. Với `PriorityChannel`, thứ tự lựa chọn message dựa trên header priority của message (hoặc một comparator được cấu hình); giá trị cao thường được ưu tiên trước theo quy tắc mặc định.

Định nghĩa contract trong code ứng dụng:

~~~java
final class PriorityHeaders {
    private PriorityHeaders() {}

    static final String PRIORITY = "priority";
    static final String ORIGINAL_PRIORITY = "originalPriority";
    static final String PRIORITY_SOURCE = "prioritySource";
    static final String BUSINESS_EVENT_ID = "businessEventId";
}

enum WorkClass {
    HIGH, NORMAL, LOW
}

record WorkCommand(String eventId, String type) {}

static int toPriority(WorkClass type) {
    return switch (type) {
        case HIGH -> 9;
        case NORMAL -> 5;
        case LOW -> 1;
    };
}
~~~

Các mức 9–5–1 là **chính sách minh họa của ứng dụng**, không phải danh sách bắt buộc của Spring Integration. Nếu một đích sử dụng miền 0–9 như JMS, cần xác định mapping; đừng gán một giá trị như 100 rồi giả định mọi đích sẽ giữ nguyên.

### Gắn priority khi tạo message

~~~java
Message<WorkCommand> message = MessageBuilder
        .withPayload(new WorkCommand("E-17", "PAYMENT_RISK"))
        .setHeader(PriorityHeaders.PRIORITY, 9)
        .setHeader(PriorityHeaders.ORIGINAL_PRIORITY, 9)
        .setHeader(PriorityHeaders.PRIORITY_SOURCE, "business-policy-v1")
        .setHeader(PriorityHeaders.BUSINESS_EVENT_ID, "E-17")
        .build();
~~~

Trong ví dụ này, `WorkCommand` là kiểu payload nghiệp vụ do dự án định nghĩa. Header `businessEventId` phải được giữ **ổn định** qua retry/redelivery; không nên dùng `MessageHeaders.ID` của một message instance làm định danh duy nhất cho nghiệp vụ.

### Quy tắc kiểu dữ liệu

Một hợp đồng tốt nên quy định:

- `priority` là **`Integer`** (hoặc kiểu số mà toàn bộ các endpoint thực sự hỗ trợ), nằm trong miền được ứng dụng cho phép.
- Giá trị **lớn hơn** là ưu tiên cao hơn trên channel được chọn.
- Thiếu hoặc sai kiểu sẽ được **từ chối hoặc chuyển về một default có kiểm soát**, chứ không âm thầm nâng thành HIGH.
- `originalPriority` được dùng để audit khi có aging hay escalation; không phải header mà `PriorityChannel` tự hiểu.
- Mọi thay đổi `priority` cần có nguyên nhân, ví dụ `prioritySource` hoặc `priorityPolicyVersion`.

Chú ý: `MessageHeaders.ID` và `MessageHeaders.TIMESTAMP` là metadata đặc biệt thường được framework tạo lại khi dựng message mới. Sao chép headers không bảo đảm giữ nguyên hai trường này; đồng thời chúng không thay thế business event ID.

## 4. Hiểu rõ ranh giới: lưu header không đồng nghĩa thực thi đúng thứ tự

~~~mermaid
flowchart TD
    A["Message có priority=9"] --> B{"Đi qua thành phần nào?"}
    B --> C["DirectChannel"]
    B --> D["PriorityChannel"]
    B --> E["ExecutorChannel"]
    B --> F["Broker adapter"]
    C --> G["Dispatch đồng bộ; không tự reorder"]
    D --> H["Lấy từ queue theo priority/comparator"]
    E --> I["Bàn giao executor; scheduling của thread pool riêng"]
    F --> J["Cần mapping + khả năng của broker"]
~~~

| Thành phần | Nếu header vẫn là `priority=9` | Có bảo đảm “chạy trước” không? |
| --- | --- | --- |
| `DirectChannel` | Header tới handler nếu không bị sửa. | Không: đây là đồng bộ, không phải priority queue. |
| `ExecutorChannel` | Header có thể tới worker. | Không: executor scheduling chịu ảnh hưởng thread pool và thời điểm task được submit. |
| `QueueChannel` FIFO | Header được lưu cùng message. | Không: queue thường lấy theo thứ tự hàng đợi, không theo header priority. |
| `PriorityChannel` | Header được đọc bởi logic priority/comparator. | Có thứ tự lấy theo policy đối với những message **đang chờ**; không preempt task đang chạy. |
| `PublishSubscribeChannel` | Subscriber có thể nhìn thấy header. | Không: mỗi subscriber không tự trở thành một priority scheduler. |
| External broker | Header phải được map đúng để broker/consumer sử dụng. | Phụ thuộc hỗ trợ, cấu hình queue/topic và consumer. |

Ví dụ: consumer đã nhận một message LOW và đang xử lý 30 giây. Sau đó message HIGH tới `PriorityChannel`. HIGH chỉ có thể được ưu tiên **so với các message còn nằm trong queue** khi có lần lấy tiếp theo; nó không tự ngắt handler LOW đang chạy.

## 5. Transformer: nguồn gây mất priority phổ biến nhất

Một Transformer có thể trả về **payload** hoặc **`Message` hoàn chỉnh**. Khi trả về payload, Spring Integration có các cơ chế chuyển tiếp request headers trong nhiều kiểu endpoint. Nhưng khi Transformer tự dựng response `Message`, có logic lọc/ghi đè header hoặc qua một adapter tùy chỉnh, **không nên coi việc giữ mọi header là điều chắc chắn**.

### Cách dễ sai: tạo Message mới chỉ với payload

~~~java
// Phản ví dụ: chỉ gọi trực tiếp helper này, không đăng ký song song
// với Transformer đúng trên cùng inputChannel.
public Message<NormalizedCommand> transformBad(
        Message<RawCommand> incoming) {

    NormalizedCommand payload = normalize(incoming.getPayload());

    // Vô tình bỏ toàn bộ business headers nếu tự tạo Message mới.
    return MessageBuilder.withPayload(payload).build();
}
~~~

Khi gọi trực tiếp helper này, kết quả `priority=9` ở message đầu vào bị mất, cùng với `businessEventId` và các header mà downstream cần. Một số Transformer endpoint có cơ chế copy/merge request headers và có thể bảo toàn các header nhất định ngay cả khi processor trả về Message; vì vậy **phải kiểm thử output thực tế của đúng version/configuration**, không chỉ nhìn vào một dòng `MessageBuilder`. Tuy nhiên, khi đã chọn tự xây `Message`, chính sách giữ/ghi đè header phải được nêu rõ trong code.

### Cách rõ ràng: sao chép có chủ đích và chuẩn hóa lại

Ví dụ các kiểu payload và logic chuẩn hóa đơn giản (đặt trong các class thích hợp của ứng dụng):

~~~java
record RawCommand(String orderId, String type) {}
record NormalizedCommand(String orderId, String action) {}

static NormalizedCommand normalize(RawCommand raw) {
    return new NormalizedCommand(
            raw.orderId(),
            raw.type().trim().toUpperCase(Locale.ROOT));
}
~~~

~~~java
@Transformer(inputChannel = "rawCommands",
             outputChannel = "normalizedCommands")
public Message<NormalizedCommand> normalizeAndPreserve(
        Message<RawCommand> incoming) {

    NormalizedCommand payload = normalize(incoming.getPayload());
    int priority = requirePriority(incoming.getHeaders());

    return MessageBuilder.withPayload(payload)
            .copyHeaders(incoming.getHeaders())
            .setHeader(PriorityHeaders.PRIORITY, priority)
            .build();
}

private static int requirePriority(MessageHeaders headers) {
    Object raw = headers.get(PriorityHeaders.PRIORITY);
    if (!(raw instanceof Integer priority)
            || priority < 0 || priority > 9) {
        throw new IllegalArgumentException(
                "priority must be an integer between 0 and 9");
    }
    return priority;
}
~~~

Ở đây `copyHeaders(...)` thích hợp để minh họa **luồng nội bộ** đã nhận metadata đáng tin cậy. **Đừng copy toàn bộ headers ra HTTP/JMS/Kafka một cách mù quáng**: headers có thể chứa reply channel object, error channel, thông tin nội bộ hoặc kiểu dữ liệu không serialize được. Ở boundary bên ngoài, dùng **allowlist** những header được phép truyền.

### Tại sao nên kiểm tra lại sau Transformer?

Một Transformer có thể:

- Thay payload nhưng nên giữ priority.
- Tách một command thành một command khác có mức độ quan trọng riêng.
- Nhận vào header có kiểu `String` ("9") trong khi downstream muốn `Integer`.
- Dùng `MessageBuilder` nhưng sau đó gọi `setHeader("priority", null)` hoặc ghi đè từ một property không đáng tin.

Nếu đây là Transformer chuẩn hóa, hợp đồng nên là “**priority đầu ra bằng priority đã được policy xác nhận**”, không phải “nếu tồn tại thì giữ nguyên mọi giá trị từ nguồn”.

## 6. Header Enricher: áp dụng chính sách tại một điểm rõ ràng

Spring Integration có **Header Enricher** để gắn thêm hoặc cập nhật metadata cho message mà không phải trộn logic header vào mọi business handler.

Ý tưởng:

~~~text
Inbound raw message
  -> validate trusted fields
  -> classify(WorkClass)
  -> Header Enricher (priority = 9/5/1)
  -> Transformer / Filter / Router
  -> priority-aware destination
~~~

Ví dụ Java DSL minh họa:

~~~java
@Bean
IntegrationFlow inboundPriorityFlow() {
    return IntegrationFlow.from("classifiedInput")
            .enrichHeaders(headers -> headers
                    .headerFunction("priority",
                            message -> priorityFromTrustedPayload(
                                    message.getPayload())))
            .channel("priorityReady")
            .get();
}
~~~

Hàm `priorityFromTrustedPayload(...)` do ứng dụng định nghĩa, trả về giá trị số hợp lệ theo policy. Với các phiên bản Spring Integration khác nhau, hãy kiểm tra signature của DSL `HeaderEnricherSpec` trong bản đang dùng. Điều quan trọng là **classify từ dữ liệu đã kiểm chứng**, không phải lấy nguyên giá trị priority chưa xác thực từ client.

### Gắn một lần hay tính lại nhiều lần?

- **Gắn ở ingress**: thuận tiện khi message đã được phân loại và mọi bước downstream cùng hiểu một contract.
- **Kiểm tra ở các boundary**: khi qua external adapter, deserialize, gộp/tách hoặc thay đổi nghiệp vụ, cần xác nhận lại giá trị.
- **Tính lại tại Router**: chỉ khi chính sách quy định priority phụ thuộc nhánh. Nếu không, việc route không nên tự nâng/hạ priority.
- **Tính lại trước broker**: nếu broker dùng miền số khác, mapping phải explicit và ghi log cả giá trị trước/sau.

Một quy tắc hữu ích: **mỗi nơi được phép thay đổi priority phải công bố được lý do, hàm mapping và bộ test**.

## 7. Router và Filter: quyết định đường đi nhưng đừng làm mất metadata

### Router

Router thường quyết định destination dựa trên payload hoặc headers. Một router chỉ chọn channel **không tự yêu cầu thay đổi priority**; nhưng nhánh đi qua adapter đặc biệt có thể làm mất hoặc chuyển nghĩa metadata.

~~~mermaid
flowchart LR
    A["Message priority=9"] --> B{"Router"}
    B --> H["urgentInput"]
    B --> N["normalInput"]
    H --> C["Urgent Transformer"]
    N --> D["Normal Transformer"]
    C --> E["PriorityChannel"]
    D --> E
    E --> F["Handler"]
~~~

Hãy kiểm tra cùng một contract tại điểm hội tụ: message từ **cả hai nhánh** có priority đúng kiểu, đúng giá trị. Một nhánh Transformer tự dựng Message có thể làm mất metadata trong khi nhánh còn lại vẫn giữ.

### Filter

`Filter` quyết định message có được đi tiếp hay không. Nếu Filter loại message, không có “priority được truyền tiếp” ở nhánh thành công. Vì vậy:

- Đừng hiểu `PriorityChannel` trống là bằng chứng priority đã bị mất; có thể message bị lọc.
- Ghi metric riêng cho `filtered_total{class}` và `priority_missing_total`.
- Nếu message bị lọc cần chuyển vào discard channel, hãy kiểm tra priority của message gửi đến discard/error path.
- Nếu policy không cho phép loại một message HIGH, Filter phải có quy tắc nghiệp vụ rõ, không chỉ ưu tiên xử lý HIGH.

Priority cao **không miễn trừ validation hoặc authorization**. Một HIGH sai schema vẫn phải bị từ chối/quarantine theo chính sách.

## 8. Splitter: message con nên thừa kế hay được tính priority mới?

Giả sử một event `OrderConfirmed` có 20 dòng hàng. Splitter tách thành `ReserveItem` cho từng SKU. Có ít nhất ba chính sách:

| Chính sách | Ý nghĩa | Khi nào phù hợp |
| --- | --- | --- |
| **Inherit** | Mọi message con dùng priority của message cha. | Cả đơn hàng có cùng mức khẩn cấp. |
| **Derive** | Tính priority từng dòng theo thuộc tính đáng tin. | Một mặt hàng có quy trình đặc biệt/sự cố riêng. |
| **Cap/escalate** | Giữ trong khoảng cho phép, nâng/hạ theo deadline của từng dòng. | Có SLA khác nhau; cần log lý do thay đổi. |

Ví dụ logic phân chia ở application layer:

~~~java
static Message<ReserveItem> childMessage(
        Message<OrderCommand> parent,
        ReserveItem item) {

    int parentPriority = requirePriority(parent.getHeaders());
    int childPriority = item.isPerishable()
            ? Math.max(parentPriority, 7)
            : parentPriority;

    return MessageBuilder.withPayload(item)
            .setHeader(PriorityHeaders.PRIORITY, childPriority)
            .setHeader(PriorityHeaders.ORIGINAL_PRIORITY, parentPriority)
            .setHeader(PriorityHeaders.BUSINESS_EVENT_ID,
                    parent.getHeaders()
                            .get(PriorityHeaders.BUSINESS_EVENT_ID))
            .setHeader("parentOrderId", parent.getPayload().orderId())
            .build();
}
~~~

`ReserveItem`, `OrderCommand` và `isPerishable()` là kiểu/hàm domain minh họa. Nếu dùng **Splitter endpoint** của Spring Integration, framework còn có thể gắn các header correlation và sequence để **Aggregator** tập hợp kết quả. **Không tự xây message con rồi vô tình loại bỏ `correlationId`, `sequenceNumber` hoặc metadata cần cho Aggregator**. Khi tự quản lý message hoàn toàn, phải kiểm tra xem framework có tự bổ sung correlation/sequence ở output hay không.

### Đừng tạo event ID mới cho mỗi lần retry của cùng message con

Khi tạo nhiều message con, cần khóa riêng cho từng nhiệm vụ con, ví dụ:

~~~text
parentEventId = ORD-17
childBusinessId = ORD-17:SKU-A
childBusinessId = ORD-17:SKU-B
~~~

Nếu retry cùng `ORD-17:SKU-A`, giữ nguyên `childBusinessId` để dedupe. `MessageHeaders.ID` có thể thay đổi khi Message được dựng lại; không nên dùng làm business key.

## 9. Aggregator: priority của output phải có chính sách

Aggregator nhận nhiều message, lưu correlation state và phát một message tổng hợp khi release condition đạt. Một output có thể được tạo từ các message có priority khác nhau:

~~~text
Item A: priority=9
Item B: priority=5
Item C: priority=1
             |
          Aggregator
             |
       BatchResult: priority=?
~~~

Không nên dựa vào việc một header tình cờ được copy từ message đến đầu tiên, đến cuối cùng hoặc một message nào đó. **Priority đầu ra phải là quyết định nghiệp vụ rõ ràng.**

Một số chính sách:

- **MAX**: output bằng priority cao nhất trong nhóm; hợp lý nếu chỉ cần một thành phần khẩn cấp là cả batch khẩn cấp.
- **MIN**: output bằng thấp nhất; hợp lý khi tất cả thành phần cần đạt tiêu chuẩn trước khi tiếp tục, nhưng dễ làm nghẽn batch quan trọng.
- **Weighted aggregation**: output phụ thuộc tỷ lệ, mức độ rủi ro hoặc deadline của group.
- **Fixed parent priority**: output giữ priority gốc của toàn bộ workflow, bất kể message con thay đổi.

Ví dụ quyết định dùng MAX:

~~~java
static int aggregatePriority(List<Message<?>> parts) {
    return parts.stream()
            .mapToInt(message -> requirePriority(message.getHeaders()))
            .max()
            .orElseThrow(() -> new IllegalArgumentException(
                    "Cannot aggregate empty group"));
}

static Message<BatchResult> aggregateResult(
        List<Message<?>> parts,
        BatchResult payload,
        String correlationId) {

    int priority = aggregatePriority(parts);
    return MessageBuilder.withPayload(payload)
            .setHeader(PriorityHeaders.PRIORITY, priority)
            .setHeader("correlationId", correlationId)
            .build();
}
~~~

Đây là logic business dùng khi xây output aggregator; cấu hình `@Aggregator`/Java DSL và xử lý correlation group cần dựa trên cấu trúc flow thực tế. Đảm bảo `correlationId` không bị thay đổi ngoài ý muốn, đồng thời kiểm tra priority của output **sau khi Aggregator release**.

### Timeout, partial release và message trễ

Nếu Aggregator phát kết quả khi timeout dù chưa đủ message con:

- Chính sách priority phải định nghĩa cho **tập message thực sự đã tới**, hoặc sử dụng parent priority đã lưu bền vững.
- Message đến trễ có thể tạo một kết quả mới hoặc bị bỏ qua tùy cấu hình; không nên vô tình nâng priority của workflow đã hoàn tất.
- Duplicate message do redelivery có thể khiến group sai số lượng hoặc priority; cần deduplication và release strategy phù hợp.

Aggregator có persistent message store cũng **không tự bảo đảm** mọi header custom sẽ tồn tại sau serialize/restart; hãy kiểm thử loại message thực tế và converter/store đang dùng.

## 10. Gateway và Request–Reply: hai hướng metadata riêng

Một Gateway kết nối lời gọi method với message flow. Cần phân biệt:

1. **Request priority**: mức ưu tiên khi yêu cầu đi vào flow.
2. **Reply priority**: mức ưu tiên của response sau khi flow xử lý xong.

Không có lý do chung rằng reply phải có cùng priority với request. Ví dụ, trả về kết quả cho người dùng có thể cần một chính sách riêng, trong khi phản hồi nội bộ chỉ dùng để hoàn tất correlation.

### Typed Gateway gửi Message rõ headers

~~~java
@MessagingGateway(defaultRequestChannel = "commandInput")
interface CommandGateway {
    void submit(Message<WorkCommand> command);
}
~~~

Caller chủ động tạo message:

~~~java
gateway.submit(MessageBuilder
        .withPayload(new WorkCommand("E-17", "PAYMENT_RISK"))
        .setHeader(PriorityHeaders.PRIORITY, 9)
        .setHeader(PriorityHeaders.BUSINESS_EVENT_ID, "E-17")
        .build());
~~~

Điểm kiểm thử là message nhận ở channel `commandInput`, không chỉ các tham số method caller.

Nếu Gateway chỉ nhận payload `submit(WorkCommand command)`, metadata phải được **suy ra hoặc bổ sung** từ method mapping/annotation/policy tại ingress. Đừng kỳ vọng priority tự tồn tại khi payload không chứa nó và caller không cấp headers.

### Header reply/error channel

Spring Integration sử dụng một số header nội bộ như reply channel và error channel để điều phối request–reply, timeout và lỗi. Khi xây message mới:

- Giữ các header cần cho **request–reply protocol** nếu cùng flow cần sử dụng.
- Không đưa những header chứa object channel nội bộ ra broker/HTTP tùy tiện.
- Không để một header custom `priority` ghi đè hoặc làm sai contract reply routing.
- Với async boundary, một reply có thể đến sau khi Gateway đã timeout; việc nó có priority cao không làm request hết timeout trở lại.

## 11. Mapping priority qua HTTP: yêu cầu phải tin cậy trước

HTTP không có cơ chế xếp hàng priority chung có thể thay thế `PriorityChannel`. Có thể truyền thông tin ưu tiên bằng **header ứng dụng** hoặc trường JSON, nhưng phía nhận phải tự mapping.

Ví dụ một upstream gửi:

~~~http
POST /api/work
Content-Type: application/json
X-Work-Priority: HIGH
X-Event-Id: E-17

{"type":"PAYMENT_RISK","orderId":"ORD-17"}
~~~

Đây là contract riêng của ứng dụng, không phải đặc tính tự có của Spring Integration. Hệ thống nhận:

1. Xác thực nguồn và quyền gán mức HIGH.
2. Validate header hoặc payload; không cho giá trị bất kỳ ngoài tập cho phép.
3. Nếu chỉ client đáng tin được quyền chỉ định, ánh xạ HIGH → 9; còn lại phân loại bằng server-side rules.
4. Gắn `priority=9` vào message nội bộ.
5. Ghi log/trace `prioritySource=trusted-api-v1` và event ID.

### Tại sao không dùng nguyên header client?

Nếu Internet client có thể gửi `X-Work-Priority: HIGH` và được xử lý như HIGH, một actor có thể chiếm toàn bộ worker cho request thường. Priority là **quyền phân bổ tài nguyên**, không phải metadata vô hại.

Đối với lời gọi giữa service:

- Dùng authentication/authorization theo service identity.
- Có allowlist quyền escalation theo endpoint/event type.
- Hạn chế tốc độ và quota theo tenant hoặc caller.
- Không cho phép retry thông điệp LOW tự nâng lên HIGH không giới hạn.
- Nếu dùng proxy/load balancer, kiểm tra header có được giữ nguyên hoặc bị thay tên/case/multi-value không.

## 12. Mapping priority qua JMS

JMS có khái niệm **message priority** trong header chuẩn `JMSPriority`, thường có miền **0–9**, với mặc định producer priority **4** nếu không đặt khác. Đây là một thuộc tính của JMS message, **khác** với việc Spring message chỉ có một custom header `priority`.

~~~text
Spring message:
  headers["priority"] = 9
        |
        | JMS outbound adapter / header mapping / producer QoS
        v
JMS message:
  JMSPriority = 9
        |
      JMS broker
~~~

Muốn bảo đảm mapping, cần xác minh **đúng adapter, header mapper và producer configuration** trong phiên bản đang dùng:

- Priority của Spring message đã được ánh xạ sang JMS priority thực tế chưa?
- Adapter có cài QoS/explicit QoS hoặc default producer setting ghi đè giá trị không?
- Broker/destination có honoring priority không, và thứ tự dưới cạnh tranh consumer ra sao?
- Khi nhận inbound, `JMSPriority` có được map về `priority` theo contract nội bộ không?

**Đừng chỉ assert `message.getHeaders().get("priority") == 9` ở trước JMS outbound adapter.** Điều đó chứng minh metadata ở phía Spring, **không** chứng minh JMS message thực tế mang `JMSPriority=9`.

### Test end-to-end cho JMS

1. Publish thông điệp với mức `9` và `1` qua adapter thật.
2. Dùng JMS consumer/test probe đọc `JMSPriority` từ message gốc.
3. Dùng Spring Integration JMS inbound adapter để kiểm tra giá trị priority ở đầu vào flow.
4. Khi test ordering, giữ consumer chưa chạy cho đến khi các message đã được enqueue; nếu HIGH đến sau LOW đã được deliver, broker không thể “thu hồi” LOW khỏi consumer.

Kết quả ordering còn phụ thuộc broker và consumer concurrency; **priority metadata truyền đúng** và **broker thực thi priority ordering** là hai bài kiểm tra tách biệt.

## 13. Mapping priority qua RabbitMQ / AMQP

Trong AMQP 0-9-1, message có thuộc tính **`BasicProperties.priority`**. RabbitMQ có thể hỗ trợ priority ordering khi **queue được cấu hình hỗ trợ priority**, thường qua argument `x-max-priority` tại lúc khai báo queue.

~~~text
Spring Message priority=9
  -> outbound adapter mapping
  -> AMQP BasicProperties.priority=9
  -> RabbitMQ queue khai báo x-max-priority
  -> broker chọn message chờ theo ưu tiên
~~~

Nếu adapter chỉ gửi một **custom application header** tên `priority` mà không đặt `BasicProperties.priority`, RabbitMQ không nhất thiết dùng nó để chọn thứ tự delivery.

Checklist AMQP:

| Điểm cần xác minh | Hệ quả nếu thiếu |
| --- | --- |
| Giá trị được map vào `BasicProperties.priority`. | Broker có thể coi mọi message cùng mức. |
| Queue được khai báo với cấu hình hỗ trợ priority. | Message có property priority nhưng queue có thể không reorder theo priority. |
| Miền priority hợp lệ và nhất quán với queue. | Giá trị cao bị giới hạn/chuẩn hóa khác kỳ vọng. |
| Prefetch và consumer concurrency phù hợp. | Message LOW đã được prefetch trước khi HIGH đến có thể vẫn xử lý trước. |
| Retry/requeue có quy tắc giữ business priority. | Message phát lại có thể mất hoặc bị nâng priority. |

Một kết quả thực tế cần nhớ: **priority của message trong broker chỉ có tác dụng đối với công việc chưa được giao cho consumer**. Consumer prefetch lớn khiến nhiều message LOW đã rời broker queue; message HIGH mới không thể tự chiếm vị trí của task đã nằm trong bộ nhớ consumer.

Không thay đổi argument `x-max-priority` trên queue đang tồn tại mà giả định broker sẽ áp dụng ngay: tùy chính sách khai báo queue, thay đổi properties có thể yêu cầu migration/redeclare có kiểm soát.

## 14. Kafka: không có broker priority queue mặc định cho từng record

Kafka lưu record theo **partition và offset**. Kafka record có headers, nhưng các header ứng dụng như `priority=9` **không khiến Kafka tự reorder record theo priority** bên trong một partition.

Do đó có hai mục tiêu khác nhau:

- **Mang priority xuyên Kafka**: encode vào record header hoặc payload, inbound mapper đọc lại để dựng Spring message đúng.
- **Thực thi priority scheduling**: tách topic/partition/consumer pool có quota, dùng dispatcher sau khi consume, hoặc thiết kế thứ tự chọn công việc ở tầng ứng dụng.

### Ví dụ contract qua Kafka

~~~text
Producer:
  businessEventId = E-17
  priority = 9
  topic = work-events

Kafka record:
  key = ORD-17
  headers["work-priority"] = bytes("9")
  value = serialized WorkCommand

Consumer:
  decode bytes("9") -> Integer(9)
  validate domain policy
  Spring Message headers["priority"] = 9
~~~

Ví dụ chỉ mô tả **wire contract**. Spring Kafka/Spring Integration Kafka adapters có những header mappers và serializer khác nhau theo phiên bản/cấu hình. Không giả định kiểu `Integer` được giữ nguyên sau khi đi qua binary header nếu chưa xác minh codec. Với các sự kiện quan trọng, nên có contract test encode/decode và versioning.

### Cần xử lý ordering thế nào?

| Yêu cầu | Thiết kế khả thi |
| --- | --- |
| Bảo toàn thứ tự theo `orderId` | Dùng key/partition strategy thống nhất; không tùy ý reorder record cùng aggregate nếu nghiệp vụ phụ thuộc thứ tự. |
| HIGH cần capacity riêng | Tách topic hoặc consumer group/worker pool có quota theo class. |
| Priority phải quyết định dequeue | Consume vào một tầng durable work scheduler có chính sách rõ và xử lý offset/ACK phù hợp. |
| Vừa bảo toàn ordering, vừa ưu tiên HIGH | Xem xét trade-off: reorder xuyên cùng aggregate có thể vi phạm thứ tự nghiệp vụ. |

**Không đánh đồng Kafka record header `priority` với priority scheduling của broker.** Việc header còn nguyên chỉ mới đạt một nửa yêu cầu.

## 15. Header mapping: không copy blindly qua ranh giới process

Trong flow nội bộ, `copyHeaders` giúp giữ metadata. Nhưng khi gửi message sang hệ thống khác, cần một **allowlist** và schema có version.

Ví dụ contract truyền ra:

~~~text
Required:
  businessEventId     : string
  workPriority        : integer 0..9
  priorityPolicyVersion: string

Optional:
  correlationId       : string
  originalPriority    : integer 0..9
  deadlineEpochMillis : long

Do not export:
  replyChannel object
  errorChannel object
  internal authentication context
  Java class instances not supported by wire serializer
~~~

Khi gửi qua broker:

1. Map canonical priority → thuộc tính/protocol phù hợp (JMS priority, AMQP property, Kafka header).
2. Serialize kiểu dữ liệu theo contract wire; không giả định Java object còn nguyên.
3. Ghi metadata ở source of truth; nếu cần audit, lưu `prioritySource` và policy version.
4. Ở inbound, xác minh/giải mã rồi dựng `Message` mới có `priority` chuẩn.
5. Đừng cho broker user/bên ngoài tự nâng priority vượt policy dù header đã decode thành công.

Một số mapping có thể lọc header hoặc rename key. Nếu chỉ test publisher và consumer cùng dùng một in-memory channel thì **chưa kiểm tra được boundary wire**.

## 16. Priority thay đổi theo thời gian: phân biệt original và effective

Để tránh starvation, hệ thống có thể dùng aging hoặc deadline escalation. Khi đó cần **hai giá trị**:

- `originalPriority`: mức được business policy gán lúc ingress.
- `priority` hoặc `effectivePriority`: mức scheduler dùng **tại thời điểm quyết định**.

Ví dụ:

~~~text
T0: originalPriority=1, effectivePriority=1
T+30s: effectivePriority=5 (aging policy)
T+60s: effectivePriority=9 (deadline escalation)
~~~

Không nên **ghi đè originalPriority** rồi mất lịch sử. Nếu message được gửi sang broker khác, cần quyết định rõ việc nào được truyền: original, effective, hay cả hai. Khi retry:

- Giữ `businessEventId` ổn định.
- Giữ `originalEnqueueTime` để thời gian chờ không bị reset.
- Nếu priority được nâng, ghi lý do và phiên bản policy.
- Giới hạn escalation để retry storm không biến mọi LOW lỗi thành HIGH.

### Đừng dùng comparator đọc đồng hồ rồi kỳ vọng heap tự reorder

Một `PriorityChannel` hoặc priority queue dựa trên heap không tự sắp lại toàn bộ phần tử chỉ vì `System.currentTimeMillis()` tăng. Muốn aging thật sự, cần **promotion/requeue/rebuild hoặc một scheduler** xét lại tuổi khi chọn message. Điều này là một bài toán scheduling, không thể giải chỉ bằng cách header được truyền chính xác.

## 17. Retry, redelivery và error channel: priority có đi cùng lỗi không?

Khi handler ném exception, lỗi có thể:

- Truyền về caller/poller và kích hoạt rollback.
- Được bọc trong `ErrorMessage` đi tới `errorChannel`.
- Được chuyển tới retry queue/DLQ.
- Được broker redeliver theo ACK/offset policy.

Ở từng đường đi cần xác nhận **metadata nào được giữ**. Một `ErrorMessage` có payload là exception, không phải payload nghiệp vụ ban đầu; đọc `errorMessage.getHeaders().get("priority")` không mặc định tương đương priority của failed message. Tùy exception, nguồn và error handler, có thể phải truy xuất failed message gốc trong `MessagingException` rồi chuẩn hóa metadata cho DLQ/retry.

### Quy tắc retry đề xuất

| Hạng mục | Chính sách |
| --- | --- |
| Business event ID | Giữ nguyên qua mọi attempt. |
| Original priority | Giữ nguyên để audit và khôi phục chính sách. |
| Effective priority | Có thể thay đổi theo retry/age, nhưng chỉ theo một policy đã định nghĩa. |
| Attempt count | Tăng theo số lần thử, được lưu bền vững nếu cần. |
| Error reason | Phân biệt lỗi tạm thời và vĩnh viễn. |
| DLQ | Giữ đủ event ID, priority source, context lỗi, payload đã sanitize. |
| ACK/offset | Chỉ kết thúc delivery theo contract khi side effect hoặc durable handoff đạt yêu cầu. |

### Lỗi thường gặp: retry được gắn priority mới không chủ ý

~~~java
Message<WorkCommand> retry = MessageBuilder
        .withPayload(failedMessage.getPayload())
        .build();
~~~

Đoạn này thiếu hợp đồng priority và business event ID. Nếu retry adapter gửi message mới rồi consumer nhận thiếu metadata, nó có thể rơi về priority mặc định hoặc gây duplicate khó kiểm soát.

Ở ranh giới retry nên dựng message từ **những trường canonical đã xác thực**, ví dụ:

~~~java
Message<WorkCommand> retry = MessageBuilder
        .withPayload(failedMessage.getPayload())
        .setHeader(PriorityHeaders.PRIORITY,
                requirePriority(failedMessage.getHeaders()))
        .setHeader(PriorityHeaders.BUSINESS_EVENT_ID,
                failedMessage.getHeaders()
                        .get(PriorityHeaders.BUSINESS_EVENT_ID))
        .setHeader("attempt",
                ((Number) failedMessage.getHeaders()
                        .getOrDefault("attempt", 0)).intValue() + 1)
        .build();
~~~

Đây là ví dụ tái dựng metadata trong **đường xử lý nội bộ**; với broker thật, cần serialize, ACK và tránh vòng lặp retry vô hạn. Không để một poison HIGH message chiếm mọi suất xử lý; retry hữu hạn, backoff và DLQ phải được phối hợp với fairness.

## 18. Ví dụ một flow nội bộ kiểm chứng priority end-to-end

Mẫu đơn giản sau giữ mục tiêu hẹp: gán priority rõ ở đầu vào, Transformer có chủ đích giữ metadata, rồi đưa vào `PriorityChannel`. Poller xử lý theo thứ tự của channel.

~~~mermaid
flowchart LR
    A["Request -> priorityAssigned"] --> B["Normalize + validate headers"]
    B --> C["PriorityChannel"]
    C --> D["Poller"]
    D --> E["Service Activator"]
    E --> F["Business DB / metrics"]
~~~

Java configuration:

~~~java
@Configuration
@EnableIntegration
class PriorityFlowConfig {

    @Bean("priorityReady")
    MessageChannel priorityReady() {
        return new DirectChannel();
    }

    @Bean("pendingPriority")
    PollableChannel pendingPriority() {
        return new PriorityChannel(200);
    }

    @Bean
    IntegrationFlow enqueuePriorityFlow() {
        return IntegrationFlow.from("priorityReady")
                .channel("pendingPriority")
                .get();
    }

    @Bean
    IntegrationFlow consumePriorityFlow(PriorityWorkHandler handler) {
        return IntegrationFlow.from(
                        "pendingPriority",
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(200)
                                        .maxMessagesPerPoll(1)))
                .handle(handler, "handle")
                .get();
    }
}
~~~

Service Activator:

~~~java
@Service
class PriorityWorkHandler {
    public void handle(Message<WorkCommand> message) {
        int priority = requirePriority(message.getHeaders());
        String eventId = String.valueOf(
                message.getHeaders().get(
                        PriorityHeaders.BUSINESS_EVENT_ID));

        // Thực hiện nghiệp vụ và ghi metric theo priority/eventId.
        // Idempotency + transaction riêng khi có side effect quan trọng.
    }
}
~~~

Đoạn code sử dụng `MessageChannel` và `PollableChannel` theo tên bean trong DSL. `PriorityWorkHandler` gọi hàm validate được trình bày ở phần 5 (đưa vào class dùng chung khi triển khai). Đây là **queue RAM minh họa**; không phải cấu hình bảo đảm không mất message khi process crash.

### Những giới hạn cần nói rõ

- `PriorityChannel` chọn giữa các message **chưa được consume**, không hủy một handler đang chạy.
- Thứ tự khi nhiều message cùng mức có thể cần tie-breaker riêng.
- Poller có thể chạy đồng thời hoặc có nhiều instance trong hệ thống thực, làm thứ tự **completion** khác thứ tự dequeue.
- Chỉ giữ header đúng **không** tự ngăn priority starvation khi HIGH đến liên tục.
- Nếu cần durable message và redelivery, chọn store/broker hỗ trợ, xác minh transaction boundary, ACK, idempotency và schema metadata.

## 19. Kiểm thử contract ở từng boundary

Một bộ kiểm thử tốt phải kiểm tra **trước/sau Transformer**, **sau Router**, **sau Splitter/Aggregator**, **trước/sau adapter wire** và **tại consumer**.

### Test 1 — Transformer giữ priority khi thay payload

~~~java
@Test
void transformerPreservesTrustedPriority() {
    RawCommand raw = new RawCommand("ORD-17", "PAYMENT_RISK");
    Message<RawCommand> input = MessageBuilder.withPayload(raw)
            .setHeader(PriorityHeaders.PRIORITY, 9)
            .setHeader(PriorityHeaders.BUSINESS_EVENT_ID, "E-17")
            .build();

    Message<NormalizedCommand> output =
            transformer.normalizeAndPreserve(input);

    assertEquals(9,
            output.getHeaders().get(PriorityHeaders.PRIORITY));
    assertEquals("E-17",
            output.getHeaders().get(PriorityHeaders.BUSINESS_EVENT_ID));
    assertEquals("ORD-17", output.getPayload().orderId());
    assertEquals("PAYMENT_RISK", output.getPayload().action());
}
~~~

Test trên giả định sử dụng các kiểu `RawCommand`, `NormalizedCommand` và bean Transformer như ở phần 5. Kiểm thử **method trực tiếp** giúp xác nhận chính sách code, nhưng cần thêm **integration test qua endpoint** để thấy cách Spring Integration thực tế copy/merge headers của reply.

### Test 2 — PriorityChannel lấy message cao trước

~~~java
@Test
void priorityChannelReceivesHigherPriorityFirst() {
    PriorityChannel channel = new PriorityChannel(20);
    channel.send(MessageBuilder.withPayload("LOW")
            .setHeader("priority", 1).build());
    channel.send(MessageBuilder.withPayload("HIGH")
            .setHeader("priority", 9).build());

    assertEquals("HIGH", channel.receive(0).getPayload());
    assertEquals("LOW", channel.receive(0).getPayload());
}
~~~

Lưu ý test này phải enqueue **cả hai message trước khi receive**. Nếu LOW đã được consumer nhận trước khi HIGH được gửi, priority không làm quay ngược một delivery đã diễn ra.

### Test 3 — Reject sai kiểu và giá trị ngoài miền

~~~java
@Test
void rejectsInvalidPriorityInsteadOfSilentlyEscalating() {
    Message<String> invalid = MessageBuilder.withPayload("WORK")
            .setHeader("priority", "9")
            .build();

    assertThrows(IllegalArgumentException.class,
            () -> requirePriority(invalid.getHeaders()));
}
~~~

Nếu HTTP/JMS/Kafka adapter chuyển priority từ string/bytes về number, hãy kiểm thử **decoder** riêng để kết quả là `Integer(9)` trước khi chuyển vào `PriorityChannel`.

### Test 4 — Aggregator chọn policy MAX

~~~java
@Test
void aggregateUsesHighestPriorityOfChildren() {
    List<Message<?>> parts = List.of(
            MessageBuilder.withPayload("A")
                    .setHeader("priority", 1).build(),
            MessageBuilder.withPayload("B")
                    .setHeader("priority", 9).build(),
            MessageBuilder.withPayload("C")
                    .setHeader("priority", 5).build());

    assertEquals(9, aggregatePriority(parts));
}
~~~

### Test 5 — Header mapper với broker thật

| Boundary | Kiểm tra đầu ra |
| --- | --- |
| HTTP ingress | Priority từ nguồn chưa tin cậy bị validate/re-classify. |
| Transformer | `priority` được giữ/biến đổi đúng policy, có `businessEventId`. |
| Router/Filter | Cả nhánh thành công và discard/error có metadata theo contract. |
| Splitter | Child priority theo inherit/derive, correlation/sequence không bị phá. |
| Aggregator | Output priority theo MAX/parent/deadline, không ngẫu nhiên theo message cuối. |
| Gateway | Request priority tới đúng channel; reply priority nếu cần có policy riêng. |
| JMS outbound | JMS message thực sự có `JMSPriority` dự kiến. |
| RabbitMQ outbound | `BasicProperties.priority` đúng, queue có hỗ trợ priority. |
| Kafka | Priority được encode/decode chính xác; không khẳng định Kafka reorder theo header. |
| Retry/DLQ | Event ID, original/effective priority, attempt và lý do lỗi tồn tại sau replay. |

Các test broker nên dùng Testcontainers hoặc broker staging phù hợp nếu cần kiểm tra kỹ adapter thực tế. Không chạy một “test truyền header” duy nhất rồi suy ra cả khả năng broker scheduling và business commit đều đúng.

## 20. Quan sát vận hành: phát hiện priority bị đổi ở đâu

Hãy theo dõi ba mốc:

1. **Assigned**: priority sau khi policy xác thực tại ingress.
2. **Enqueued**: priority ngay trước queue/broker.
3. **Consumed**: priority mà handler thực sự nhận và dùng để quyết định.

Với mỗi message, trace có thể ghi:

~~~text
eventId = E-17
correlationId = ORD-17
assignedPriority = 9
enqueuedPriority = 9
consumedPriority = 9
prioritySource = business-policy-v1
destination = pendingPriority
adapter = local-priority-channel
~~~

Metrics:

| Metric | Ý nghĩa |
| --- | --- |
| `priority_missing_total{endpoint}` | Message đến endpoint nhưng thiếu header theo contract. |
| `priority_invalid_total{endpoint}` | Header sai kiểu/ngoài miền hoặc không được cấp quyền. |
| `priority_changed_total{from,to,reason}` | Theo dõi thay đổi hợp lệ hoặc bất thường. |
| `priority_mismatch_total{boundary}` | Priority wire/consumer khác priority đã xác nhận ngoài policy. |
| `queue_depth{priority}` | Số message pending theo mức, giúp thấy workload. |
| `oldest_pending_age_seconds{priority}` | Phát hiện starvation dù priority vẫn truyền đúng. |
| `retries_total{priority}` | Lỗi/retry gây thay đổi lưu lượng theo mức ưu tiên. |
| `processed_total{priority}` | Lưu lượng thực sự được xử lý theo mức, không chỉ enqueue. |

Với tracing, có thể thêm metadata chuẩn hóa vào span/log **đã lọc dữ liệu nhạy cảm**. Tránh ghi payload thô, token, full HTTP headers hoặc thông tin cá nhân không cần thiết.

### Debug một message HIGH bị xử lý trễ

Theo dõi từ `eventId`:

~~~text
1. Policy đã phân loại HIGH chưa?
2. Header Spring ngay sau ingress là Integer(9) chưa?
3. Transformer nào tạo Message mới hoặc ghi đè header?
4. Router đã chuyển đúng destination chưa?
5. Splitter/Aggregator đã áp policy cho output chưa?
6. Outbound adapter map đúng broker property chưa?
7. Queue/topic đích có hỗ trợ priority scheduling không?
8. LOW đã được prefetch/đang xử lý trước khi HIGH đến chưa?
9. Consumer đọc priority đúng nhưng backlog HIGH quá lớn hay không?
10. Có retry, timeout, lock DB hoặc worker saturation không?
~~~

Nếu priority được truyền đúng ở tất cả mốc nhưng HIGH vẫn chậm, nguyên nhân có thể nằm ở **capacity, scheduling, retry hoặc downstream** — không phải mất header.

## 21. Các anti-pattern cần tránh

| Anti-pattern | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Chỉ gán `priority` ở producer rồi không kiểm thử downstream. | Một EIP hoặc adapter có thể làm mất/đổi metadata. | Contract test tại mỗi boundary và wire integration test. |
| Tạo `MessageBuilder.withPayload(...)` trong custom Transformer và không định nghĩa header policy. | Metadata quan trọng có thể không còn ở output. | Copy có chủ đích, validate lại, test endpoint thực. |
| Copy mọi header nội bộ vào HTTP/JMS/Kafka. | Có thể lộ metadata, chứa object không serialize, hoặc bị mapper bỏ silently. | Header allowlist + versioned wire contract. |
| Cho client ngoài tự gán HIGH. | Có thể chiếm worker/queue, phá quota. | Server-side classification, authz và rate limiting. |
| Gán priority=9 cho Kafka rồi kỳ vọng record được đọc vượt offset trước. | Kafka không tự reorder theo custom header. | Tách topic/consumer hoặc application scheduling. |
| Gắn `priority` Spring nhưng không cấu hình AMQP/JMS mapping. | Broker property có thể không được gán hoặc bị default override. | Kiểm tra property trên message ở broker. |
| Nhầm `PriorityChannel` với `DirectChannel`. | DirectChannel không reorder theo priority. | Đặt queue/scheduler thực sự ở điểm cần ưu tiên. |
| Aggregator để output priority phụ thuộc message đến cuối. | Kết quả không ổn định theo concurrency/retry. | Policy MAX/MIN/parent/deadline rõ và test. |
| Retry tạo event ID mới hoặc xóa originalPriority. | Duplicate khó chặn, mất lịch sử escalation. | Giữ business ID và original metadata bền vững. |
| Chỉ kiểm tra header, bỏ qua starvation. | High priority vẫn có thể áp đảo mọi công việc khác. | Có aging/fairness, quota và đo tuổi queue. |

## 22. Bài tập thực hành

**Bài 1 — giữ priority khi transform.** Tạo `RawCommand` với header `priority=9` và `businessEventId`. Viết Transformer tạo `NormalizedCommand`, kiểm tra output sau endpoint. Thử phiên bản mất headers, tìm nguyên nhân và sửa.

**Bài 2 — policy ingress.** Cho HTTP client gửi `X-Work-Priority=HIGH`. Thiết kế service-side classification: caller được cấp quyền thì gán 9; caller thường gửi HIGH cho report thì hạ về 1 và ghi metric. Kiểm thử cả sai kiểu/trống/giá trị ngoài miền.

**Bài 3 — Router hai nhánh.** Route message HIGH và LOW qua hai Transform khác nhau rồi hội tụ tại `PriorityChannel`. Chứng minh cả hai nhánh giữ `priority` và business event ID.

**Bài 4 — Splitter/Aggregator.** Một đơn có ba item lần lượt nhận priority 9, 5, 1. Triển khai policy MAX cho output Aggregator và kiểm thử duplicate/timeout/partial release với correlation ID ổn định.

**Bài 5 — JMS/AMQP adapter.** Gửi message có Spring header priority 9. Trên broker, đọc thuộc tính chuẩn `JMSPriority` hoặc `BasicProperties.priority`; nếu sai, xác định header mapper/producer QoS/queue configuration gây ra.

**Bài 6 — Kafka.** Encode priority thành record header bytes và decode thành `Integer` tại consumer. Giải thích vì sao hai record cùng partition vẫn theo offset chứ không theo giá trị priority custom.

**Bài 7 — retry và DLQ.** Message HIGH lỗi tạm thời ba lần. Kiểm tra các bản retry giữ event ID, original priority và attempt count, sau đó được DLQ/quarantine đúng policy.

**Bài 8 — observability.** Bổ sung trace cho assigned/enqueued/consumed priority. Thêm metric mismatches và oldest pending age. Tái hiện hai lỗi: mất header và header đúng nhưng consumer bị nghẽn; phân biệt tín hiệu.

### Câu hỏi tự đánh giá

**1. Header `priority=9` có khiến `DirectChannel` thực thi message trước `priority=1` không?** Không. DirectChannel dispatch đồng bộ, không có priority queue.

**2. Khi Transformer trả về Message mới, có nên mặc định mọi header đều giữ nguyên không?** Không. Phải định nghĩa policy và kiểm thử output endpoint, nhất là với Message được tạo lại/custom mapper.

**3. Aggregator lấy priority từ message nào?** Phải do nghiệp vụ định nghĩa; ví dụ MAX của các message con hoặc parent priority đã lưu.

**4. Spring message priority=9 có đồng nghĩa JMSPriority=9 không?** Không được mặc định. Phải kiểm tra adapter mapping và giá trị JMS message thực tế.

**5. RabbitMQ có xử lý priority nếu chỉ đặt custom application header `priority`?** Không nên giả định; cần `BasicProperties.priority` cùng queue được cấu hình hỗ trợ priority.

**6. Kafka có sắp xếp theo custom `priority` header không?** Không. Kafka giữ record theo offset/partition và các semantics riêng.

**7. Tại sao phải giữ `originalPriority` khi dùng aging?** Để biết mức gốc, truy vết escalation và tránh reset lịch sử qua retry.

**8. Header đã đúng ở consumer nhưng message HIGH vẫn chậm vì sao?** Có thể do capacity, prefetch, backlog, handler dài, concurrency hoặc resource downstream chứ không phải mất metadata.

## 23. Checklist trước khi đưa vào production

- [ ] Công bố contract priority: kiểu, miền giá trị, thứ tự, default và semantic HIGH/NORMAL/LOW.
- [ ] Xác định service/policy được quyền phân loại, không tin nguyên priority từ client bên ngoài.
- [ ] Gắn `businessEventId` ổn định, `originalPriority` và metadata nguồn khi cần audit.
- [ ] Kiểm thử sau mọi Transformer tự dựng message và mọi bước có header enrichment.
- [ ] Xác nhận Router giữ đúng header tại từng nhánh, Filter/discard/error path có cách xử lý rõ.
- [ ] Splitter có policy inherit/derive; không phá correlation/sequence metadata.
- [ ] Aggregator có priority policy output rõ, kiểm thử timeout/duplicate/partial release.
- [ ] Gateway/request–reply có hợp đồng request và reply priority riêng khi cần.
- [ ] HTTP ingress validate nguồn và mapping, áp quota/authorization theo tenant.
- [ ] JMS kiểm tra `JMSPriority` thực tế; RabbitMQ kiểm tra `BasicProperties.priority` và queue; Kafka kiểm tra encode/decode, không giả định reorder.
- [ ] Mọi external boundary dùng allowlist và schema version; không copy object headers nội bộ bừa bãi.
- [ ] Retry/DLQ giữ business ID, priority gốc, attempt, lý do lỗi; tránh poison HIGH chiếm mọi capacity.
- [ ] Có test message cao và thấp đồng thời chờ trước lúc poll, không chỉ test send order.
- [ ] Đo assigned/enqueued/consumed priority, mismatch counts, queue age và retry theo lớp.
- [ ] Thiết kế fairness/aging/capacity riêng để tránh starvation; priority metadata đúng chưa đủ.
- [ ] Với nguồn bền vững, kiểm tra transaction/ACK/redelivery, idempotency và khôi phục sau crash.

**Ghi nhớ:** **Priority chỉ có ý nghĩa nếu được chuẩn hóa, truyền đúng qua mọi lần tạo message, được ánh xạ đúng tại adapter và thực sự được scheduler/broker đích sử dụng.** Spring Integration cho phép tổ chức các EIP ít phụ thuộc; đổi lại, mỗi Transformer, Splitter, Aggregator, Gateway và external boundary phải có hợp đồng metadata rõ. Hãy kiểm thử ở **điểm sử dụng priority**, không chỉ ở nơi đầu tiên gắn header.

### Tài liệu tham khảo

- [Spring Integration — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html): các loại channel và PriorityChannel.
- [Spring Integration — Message Headers](https://docs.spring.io/spring-integration/reference/message.html): cấu trúc Message và header trong flow.
- [Spring Integration — Transformer](https://docs.spring.io/spring-integration/reference/transformer.html): biến đổi message và xử lý reply headers theo endpoint.
- [Spring Integration — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): correlation, sequence, release và output.
- [RabbitMQ — Priority Queues](https://www.rabbitmq.com/docs/priority): ưu tiên ở broker và cấu hình queue.
- [Apache Kafka — Documentation](https://kafka.apache.org/documentation/): partition, offset và record headers.

*Các ví dụ trình bày contract và nguyên tắc thiết kế. Trước khi áp dụng vào dự án, cần xác minh API, mapper, serialization và hành vi priority trong chính phiên bản Spring Integration/Spring Framework/broker đang sử dụng; chưa thay thế integration test ở hệ thống thật.*
