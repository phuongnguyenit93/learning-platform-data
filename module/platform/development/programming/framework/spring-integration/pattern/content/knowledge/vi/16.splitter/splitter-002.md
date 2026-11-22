# Splitter theo danh sách hoặc collection

> **Chương:** Splitter  
> **Module:** `SPRING_INTEGRATION_PATTERN` — học triển khai Enterprise Integration Patterns (EIP) với Spring Integration để xây dựng luồng thông điệp ít phụ thuộc và dễ mở rộng. Thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử, theo dõi các nhánh xử lý. Bài này tập trung vào **tách một message chứa danh sách/collection thành các message con**, rồi điều phối, kiểm thử và nếu cần thì tổng hợp kết quả.

## 1. Mục tiêu học tập

Sau khi hoàn thành bài học, bạn có thể:

1. Giải thích vì sao **Splitter** tách *payload có nhiều phần tử* thành nhiều message độc lập về mặt xử lý, không nhầm với **Recipient List** gửi cùng một nội dung tới nhiều đích.
2. Chọn hợp đồng phù hợp cho payload đầu vào kiểu `List<T>`, `Collection<T>` hoặc một DTO chứa danh sách; xác định rõ cách xử lý `null`, danh sách rỗng và phần tử lỗi.
3. Sử dụng **Spring Integration Java DSL** với `.split()` cho payload collection và `.split(OrderBatch.class, OrderBatch::lines)` khi cần lấy danh sách từ một đối tượng nghiệp vụ.
4. Hiểu **correlation ID, sequence number và sequence size**, vai trò của chúng đối với Aggregator, retry và theo dõi từng phần tử.
5. Phân tích việc **thứ tự xử lý có thể thay đổi** sau executor/queue/broker, cùng những vấn đề về backpressure, dữ liệu mutable và số lượng phần tử rất lớn.
6. Viết **unit test và integration test** để chứng minh số message được tách, payload từng message, metadata được giữ, không gửi lặp và hành vi với collection rỗng hoặc dữ liệu sai.

## 2. Tình huống: một đơn hàng, nhiều dòng sản phẩm

Giả sử dịch vụ tiếp nhận một đơn có ba dòng hàng:

~~~json
{
  "orderId": "ORD-701",
  "lines": [
    {"sku": "BOOK-1", "quantity": 2},
    {"sku": "PEN-5", "quantity": 4},
    {"sku": "BAG-2", "quantity": 1}
  ]
}
~~~

Hệ thống cần kiểm tra tồn kho cho **từng dòng** vì mỗi SKU có thể thuộc kho hoặc chính sách khác nhau. Nếu đưa cả đơn tới một handler duy nhất, handler phải tự lặp danh sách, theo dõi lỗi từng phần và xử lý nhiều loại nghiệp vụ. Một **Splitter endpoint** đặt ranh giới rõ ràng:

~~~mermaid
flowchart LR
    A["OrderBatch: 3 lines"] --> S{"Splitter"}
    S --> M1["Message: BOOK-1 × 2"]
    S --> M2["Message: PEN-5 × 4"]
    S --> M3["Message: BAG-2 × 1"]
    M1 --> C["Per-item processing"]
    M2 --> C
    M3 --> C
    C --> G["Aggregator nếu cần kết quả chung"]
~~~

Message đầu vào là **một message về đơn hàng**; đầu ra của Splitter là **ba message con**, mỗi message có payload đại diện cho một dòng. Mỗi message con có thể đi qua một Router theo SKU, một Filter kiểm tra điều kiện kho, một Gateway gọi dịch vụ tồn kho hoặc một Transformer tạo request cho API ngoài.

**Không mặc định ba message con được xử lý song song.** Khả năng đồng thời phụ thuộc output channel và endpoint phía sau. Splitter mô tả **phân tách message**, không tự cam kết threading, persistence hay thứ tự hoàn thành.

## 3. EIP Splitter: đổi một message thành nhiều message

Trong Enterprise Integration Patterns, **Splitter** chia một thông điệp tổng hợp thành những phần có thể được xử lý riêng. Với danh sách/collection, ý tưởng cơ bản là:

~~~text
Input Message<List<Item>>
    payload = [itemA, itemB, itemC]
               |
               v
            Splitter
               |
               +--> Message<Item>(itemA)
               +--> Message<Item>(itemB)
               +--> Message<Item>(itemC)
~~~

Với DTO chứa danh sách:

~~~text
Message<OrderBatch>
  payload = OrderBatch(orderId="ORD-701", lines=[A,B,C])
               |
               v
        Extract lines + Splitter
               |
               +--> Message<OrderLine>(A)
               +--> Message<OrderLine>(B)
               +--> Message<OrderLine>(C)
~~~

Một Splitter có thể sử dụng phương thức/biểu thức để tạo ra collection, mảng hoặc một nguồn các phần tử phù hợp với contract. Hành vi với nguồn lazy hoặc collection không có kích thước biết trước cần được xác nhận trên phiên bản Spring Integration đang dùng — đặc biệt nếu workflow phụ thuộc vào metadata sequence.

### 3.1. So sánh với các EIP liên quan

| Pattern | Câu hỏi chính | Số message hoặc recipient | Ví dụ |
| --- | --- | --- | --- |
| **Splitter** | Một payload có những **phần nào** cần xử lý riêng? | Một message đầu vào → nhiều message có payload con | Một đơn → ba dòng hàng |
| **Recipient List** | Những **đích nào** cần nhận message này? | Một message → nhiều recipient, thường nội dung nghiệp vụ giống nhau | `OrderPlaced` → audit và analytics |
| **Content-Based Router** | Message hiện tại đi **nhánh nào**? | Lựa chọn output theo policy | Dòng chứa hàng lạnh → kho lạnh |
| **Aggregator** | Các message con thuộc nhóm nào và **khi nào đủ** để kết thúc? | Nhiều message → kết quả nhóm | Ba kết quả tồn kho → một kết quả đơn |
| **Transformer** | Cần đổi **biểu diễn** payload như thế nào? | Thường một output đã chuyển kiểu | `OrderLine` → `ReserveStockCommand` |
| **Filter** | Message này có được **đi tiếp** không? | Giữ hoặc loại message | Loại dòng quantity không hợp lệ |

Nếu chỉ cần đổi `List<PartnerLine>` thành `List<WarehouseLine>` **trong một payload**, đó có thể là Transformer. Nếu thật sự phát **một message cho mỗi item**, đó là Splitter.

### 3.2. Điều gì được tách và điều gì được giữ?

Trong thiết kế đơn giản, **payload đổi từ collection sang từng phần tử**, còn các headers liên quan có thể được chuyển tiếp hoặc được bổ sung cho việc xử lý nhóm. Chẳng hạn:

- `businessCorrelationId`: định danh nghiệp vụ do ứng dụng sử dụng để truy vết.
- `correlationId`: metadata grouping/sequence của Spring Integration khi được cấu hình và áp dụng.
- `sequenceNumber`: thứ tự phần tử theo sequence của Splitter.
- `sequenceSize`: số phần tử dự kiến, nếu biết và có áp dụng sequence.
- `replyChannel` / `errorChannel`: phục vụ cơ chế reply/error khi phù hợp.

**Không nên giả định mọi header đều được giữ nguyên qua mọi Transformer, Gateway hoặc broker**, cũng không coi `MessageHeaders.id` của các message con là business ID của đơn gốc.

## 4. Chọn kiểu collection và semantics của thứ tự

Ở tầng Java, `List`, `Set`, `Collection` và `Iterable` đều có thể biểu diễn nhiều phần tử, nhưng **ngữ nghĩa thứ tự và khả năng xác định số lượng khác nhau**.

| Nguồn dữ liệu | Đặc điểm | Lưu ý khi chia |
| --- | --- | --- |
| `List<OrderLine>` | Có thứ tự theo chỉ số | Phù hợp khi phải giữ vị trí dòng hàng |
| `ArrayList<T>` | List mutable | Có thể bị producer sửa trong lúc xử lý nếu không snapshot |
| `List.copyOf(source)` | List không sửa được ở cấu trúc ngoài | Các **phần tử mutable** bên trong vẫn có thể thay đổi |
| `LinkedHashSet<T>` | Không trùng và có thứ tự lặp theo insertion | Dễ vô tình bỏ những dòng hàng trùng giá trị |
| `HashSet<T>` | Không cam kết encounter order ổn định | Không dùng sequence index để suy ra thứ tự nghiệp vụ |
| `Collection<T>` | Không bảo đảm mọi implementation có thứ tự | Phải biết contract cụ thể trước khi kỳ vọng ordering |
| `Iterable<T>` / iterator | Có thể đánh giá lazy, kích thước chưa biết | Không mặc định `sequenceSize` luôn có giá trị hữu ích |
| `Stream<T>` | Một lần tiêu thụ, có thể vô hạn | Cần kiểm tra API hỗ trợ và giới hạn dữ liệu; không dùng làm danh sách hữu hạn một cách tùy tiện |
| `Map<K,V>` | Cấu trúc khóa–giá trị | Định nghĩa rõ cần tách `entrySet`, `values` hay DTO khác |

**Khuyến nghị:** Với đơn hàng thông thường có số dòng hữu hạn và thứ tự cần bảo toàn, dùng `List<OrderLine>` bất biến. Nếu nghiệp vụ xử lý tập hợp **không có thứ tự**, đừng gán ý nghĩa kinh doanh cho `sequenceNumber`.

### 4.1. Thứ tự phát không đồng nghĩa thứ tự hoàn thành

Giả sử nguồn List là `[A,B,C]`. Trong một flow nội bộ đồng bộ, các message thường được phát theo encounter order. Nhưng nếu sau Splitter có executor hoặc broker, thời gian xử lý có thể là:

~~~text
Dispatch:  A -> B -> C
Complete:  B -> C -> A
~~~

Vì vậy, test nên phân biệt rõ **thứ tự Splitter tạo message** và **thứ tự downstream hoàn tất**. Một Aggregator không nên yêu cầu các kết quả đến đúng `1,2,3` nếu cơ sở hạ tầng cho phép out-of-order delivery.

### 4.2. Vì sao `Set` có thể làm mất dữ liệu nghiệp vụ?

Nếu hai dòng hàng tình cờ có cùng SKU và quantity nhưng thuộc hai vị trí đặt hàng khác nhau, ép `List` sang `Set` có thể **loại một dòng** dựa trên `equals/hashCode`. Splitter chỉ phát theo **collection được cấp**, không có cách tự biết rằng dữ liệu đã bị loại trước đó.

Khi có các dòng trùng về giá trị nhưng cần xử lý riêng, hãy giữ **lineId/lineIndex** ổn định và dùng List hoặc một model bảo toàn multiplicity.

## 5. Hợp đồng dữ liệu: một batch gồm những gì?

Để minh họa, ta định nghĩa hai Java records (Java 17+). `OrderLine` là một phần tử nghiệp vụ; `OrderBatch` đại diện cho đơn chứa nhiều phần tử.

~~~java
import java.util.List;
import java.util.Objects;

record OrderLine(String sku, int quantity) {
    OrderLine {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
    }
}

record OrderBatch(String orderId, List<OrderLine> lines) {
    OrderBatch {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
        lines = List.copyOf(
            Objects.requireNonNull(lines, "lines"));
    }
}
~~~

Chúng ta **cho phép danh sách rỗng** trong model để chủ động thảo luận semantics. Đây không có nghĩa mọi nghiệp vụ đơn hàng phải chấp nhận đơn 0 dòng. Một hệ thống bán hàng có thể từ chối từ validation trước Splitter; một event đồng bộ trạng thái lại có thể coi danh sách rỗng là một kết quả hợp lệ.

### 5.1. Snapshot tại thời điểm tiếp nhận

~~~java
import java.util.ArrayList;
import java.util.List;

List<OrderLine> original = new ArrayList<>();
original.add(new OrderLine("BOOK-1", 2));
original.add(new OrderLine("PEN-5", 4));

OrderBatch batch = new OrderBatch("ORD-701", original);
original.clear();

System.out.println(batch.lines().size()); // 2
~~~

`List.copyOf` tránh việc sửa **danh sách ngoài** sau khi tạo batch. Nhưng nếu `OrderLine` chứa trường `List<MutableAdjustment>` hoặc mảng `byte[]`, record vẫn có thể chia sẻ các phần tử mutable. Khi phân phối message qua nhiều thread, nên dùng **toàn bộ object graph bất biến** hoặc tạo defensive copy có chủ đích.

### 5.2. Không giữ nguyên batch trong payload của từng item

Trong thiết kế mặc định, payload của child message là `OrderLine`. Nếu handler kho cần `orderId`, có ba lựa chọn thường gặp:

1. Đưa business correlation vào header đáng tin cậy, ví dụ `businessOrderId`.
2. Tạo DTO `OrderLineTask(orderId, lineIndex, line)` ở bước mapping/splitting.
3. Lưu metadata ở workflow state store và truy cập theo business key khi có yêu cầu rõ.

Không nên bắt mọi handler đọc lại toàn bộ `OrderBatch` chỉ để lấy ID hoặc tự tìm index của item, vì việc đó làm mất lợi ích chia nhỏ.

## 6. Spring Integration Java DSL: Splitter cho payload List trực tiếp

Khi payload đầu vào chính là một `List<OrderLine>`, có thể dùng **DefaultMessageSplitter** qua `.split()`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class ListSplitterConfiguration {

    @Bean("items.list.in")
    DirectChannel listInput() {
        return new DirectChannel();
    }

    @Bean("items.list.out")
    QueueChannel listOutput() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow splitListPayload() {
        return IntegrationFlow.from("items.list.in")
            .split()
            .channel("items.list.out")
            .get();
    }
}
~~~

Dòng `.split()` ở đây dựa trên kiểu payload collection. Với một List hữu hạn hợp lệ, các phần tử được phát thành **các message có payload tương ứng**. `QueueChannel` ở đích chỉ làm điểm thu cho bài học và kiểm thử; nó **không** thể hiện một consumer nghiệp vụ đã xử lý thành công.

Ví dụ gửi vào input channel đã được inject:

~~~java
import java.util.List;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

List<OrderLine> lines = List.of(
    new OrderLine("BOOK-1", 2),
    new OrderLine("PEN-5", 4),
    new OrderLine("BAG-2", 1));

Message<List<OrderLine>> request = MessageBuilder.withPayload(lines)
    .setHeader("businessCorrelationId", "ORD-701")
    .build();

listInputChannel.send(request);
~~~

Kết quả mong đợi về **payload** tại `items.list.out`:

~~~text
Message<OrderLine>(sku="BOOK-1", quantity=2)
Message<OrderLine>(sku="PEN-5",  quantity=4)
Message<OrderLine>(sku="BAG-2",  quantity=1)
~~~

### 6.1. Khi không nên dùng default List Splitter?

Nếu payload không phải List mà là một DTO `OrderBatch` chứa `lines`, `.split()` không biết business contract nào cần được trích ra. Nên dùng **expression/method splitter** hoặc một bước chuyển đổi rõ ràng để lấy danh sách. Ngoài ra, nếu cần tạo task cho từng dòng kèm `orderId` và `lineIndex`, hãy dùng một **typed method splitter** thay vì mong framework tự sinh business metadata.

## 7. Spring Integration Java DSL: tách danh sách nằm trong DTO

Tình huống phổ biến hơn là message mang `OrderBatch`. Java DSL có thể gọi một phương thức trả collection:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class BatchSplitterConfiguration {

    @Bean("orders.batch.in")
    DirectChannel batchInput() {
        return new DirectChannel();
    }

    @Bean("orders.items.out")
    QueueChannel itemOutput() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow splitBatchLines() {
        return IntegrationFlow.from("orders.batch.in")
            .split(OrderBatch.class, OrderBatch::lines)
            .channel("orders.items.out")
            .get();
    }
}
~~~

Ở đây, phương thức `OrderBatch::lines` nhận đối tượng batch và trả `List<OrderLine>`. Spring Integration dùng kết quả đó để tạo các message con. Đây là hai hành động phân biệt:

1. **Trích list từ aggregate payload** bằng typed function.
2. **Tách list thành từng message** thông qua Splitter endpoint.

Đừng nhầm với một Transformer đơn thuần:

~~~java
// Chỉ đổi payload OrderBatch -> List<OrderLine>.
// Nếu không có Splitter tiếp theo thì vẫn chỉ có một message với List.
.transform(OrderBatch.class, OrderBatch::lines)
~~~

Nếu handler đích cần xác định dòng thứ bao nhiêu trong đơn, hãy thêm field `lineIndex` hoặc `lineId` **trong contract của child DTO**. `sequenceNumber` (nếu có) mô tả vị trí trong quá trình split; nó không nhất thiết là chỉ số nghiệp vụ bất biến qua retry, reordering hoặc thay đổi tập dòng.

### 7.1. Thiết kế task giàu metadata nghiệp vụ

Một cách rõ ràng là biến từng dòng thành task bất biến trước khi chia:

~~~java
import java.util.ArrayList;
import java.util.List;

record OrderLineTask(String orderId, int lineNumber, OrderLine line) {}

final class LineTaskFactory {

    List<OrderLineTask> tasks(OrderBatch batch) {
        List<OrderLineTask> result = new ArrayList<>();
        for (int i = 0; i < batch.lines().size(); i++) {
            result.add(new OrderLineTask(
                batch.orderId(), i + 1, batch.lines().get(i)));
        }
        return List.copyOf(result);
    }
}
~~~

Có thể dùng method splitter trích `LineTaskFactory.tasks(batch)`, trả về collection `List<OrderLineTask>`. Khi đó business identity đi trong payload và không phụ thuộc hoàn toàn vào header sequence. Đây là lựa chọn hữu ích nếu mỗi task được lưu vào broker, replay độc lập hoặc consumer phía ngoài không bảo toàn header Spring Integration.

## 8. Correlation, sequence number và sequence size

Splitter thường đi cùng **Aggregator**. Muốn gom đúng kết quả, hệ thống phải biết những message con nào xuất phát từ cùng một message nguồn và **khi nào nhóm đủ phần**.

~~~text
Parent: OrderBatch("ORD-701") -> split into 3 items
          |
          +-> Item 1: correlation group G, sequenceNumber=1, sequenceSize=3
          +-> Item 2: correlation group G, sequenceNumber=2, sequenceSize=3
          +-> Item 3: correlation group G, sequenceNumber=3, sequenceSize=3
~~~

Đây là **minh họa khi sequence metadata được áp dụng**. Trong Spring Integration, khả năng gắn các header như `correlationId`, `sequenceNumber`, `sequenceSize` phụ thuộc loại Splitter, cấu hình `applySequence` và tính chất nguồn dữ liệu. Khi downstream cần Aggregator dựa vào sequence, hãy **bật/kiểm tra áp dụng sequence theo API của phiên bản đang dùng** và viết integration test xác nhận header thực tế; không chỉ giả định dựa vào sơ đồ.

| Metadata | Chức năng | Điều cần tránh |
| --- | --- | --- |
| `correlationId` | Nhóm các child messages thuộc cùng phiên split | Không mặc định đó là `orderId` |
| `sequenceNumber` | Thứ tự child message trong sequence | Không dùng làm business line ID ổn định |
| `sequenceSize` | Tổng số phần dự kiến khi biết trước | Không giả định luôn biết với nguồn lazy/vô hạn |
| `businessCorrelationId` | Business trace do ứng dụng thêm | Không tự thay thế duplicate detection |
| `MessageHeaders.id` | ID envelope của từng message | Không dùng làm idempotency key của business operation |

**Ví dụ:** Một đơn `ORD-701` có thể được xử lý hai lần ở hai thời điểm do reprocess. Hai lần split có thể sinh **hai correlation groups** khác nhau. Nếu dùng duy nhất `orderId` để gom, có nguy cơ trộn kết quả của hai phiên xử lý; nếu dùng duy nhất correlation group do framework tạo để chống side effect trùng, có nguy cơ tạo vận đơn/giữ hàng lặp qua replay. Hai mục đích **grouping** và **idempotency** cần được thiết kế riêng.

### 8.1. Số phần tử phải khớp contract

Với List ba phần tử, nhóm mong đợi có ba child messages. Nếu một Filter làm rơi child số 2 trước Aggregator, nhóm chỉ còn 2/3 và có thể **không bao giờ release** theo chiến lược chờ đủ.

Lúc đó cần quyết định:

- Gửi **kết quả từ chối của item 2** về aggregator, có cùng correlation group.
- Hoặc dùng một release strategy/timeout và kết quả `PARTIAL` được định nghĩa rõ.
- Hoặc kết thúc workflow bằng error/compensation thay vì giả vờ cả ba item đều thành công.

Không dùng Filter drop im lặng một message con nếu downstream đang chờ kết quả của tất cả phần tử.

## 9. Tách danh sách rỗng và phần tử không hợp lệ

### 9.1. Collection rỗng

~~~text
Input: OrderBatch(orderId="ORD-EMPTY", lines=[])
Splitter -> zero item messages
~~~

Đối với một danh sách rỗng hợp lệ, Splitter có thể không phát child message nào. Nếu phía sau chỉ có Aggregator chờ child message, **sẽ không có nhóm mới** để release hay phát kết quả “không có phần tử”.

Vì thế phải xử lý tại **trước Splitter** nếu nghiệp vụ yêu cầu ACK hay trạng thái cuối:

~~~mermaid
flowchart LR
    IN["OrderBatch"] --> V{"lines.isEmpty()?"}
    V -->|Yes| E["Emit EMPTY_RESULT / reject theo contract"]
    V -->|No| S["Splitter"]
    S --> P["Process each item"]
    P --> A["Aggregate results"]
~~~

Có thể dùng Router hoặc Filter có `discardChannel` **và handler tạo reply** phù hợp. Với Gateway đồng bộ chờ kết quả, **không được** im lặng tạo zero output rồi mặc định caller sẽ nhận một response hoàn tất.

### 9.2. Null collection

`Message<?>` không cho payload null theo contract messaging thông thường. Nhưng đối tượng `OrderBatch` có field `lines=null`, hoặc một splitter method trả null, là một vấn đề khác. Hãy xác định chính sách **validation failure** trước split thay vì ngầm coi null là empty hoặc để lỗi `NullPointerException` không có mã nguyên nhân.

Trong ví dụ, constructor của `OrderBatch` đã từ chối `lines=null`. Nếu một API ngoài cho phép trường này, inbound mapper phải làm rõ đây là dữ liệu hợp lệ hay lỗi schema.

### 9.3. Phần tử null

`List.copyOf` không chấp nhận phần tử null; nhiều collection mutable có thể chứa null. Một splitter không nên tạo message với payload null rồi hy vọng downstream tự hiểu. Với đầu vào không tin cậy, validation phải có chính sách cho phần tử null, kiểu sai hoặc field thiếu; tùy nghiệp vụ, **reject cả batch** hoặc tạo **ItemRejected** có index rõ ràng.

### 9.4. Một item lỗi có làm hỏng cả batch?

Không có câu trả lời chung. Hai chính sách thường gặp:

1. **All-or-nothing:** nếu một item không hợp lệ, từ chối cả batch trước khi split; phù hợp tác vụ cần tính nhất quán chặt.
2. **Partial processing:** những item hợp lệ tiếp tục, mỗi item lỗi tạo một kết quả từ chối, sau đó Aggregator tổng hợp `SUCCESS/PARTIAL/FAILED`.

Chọn chính sách **trước khi viết Splitter**, vì nó quyết định Filter, Aggregator release strategy, reply/error contract và cách lưu audit.

## 10. Xử lý từng child message: Router, Transformer, Handler

Sau Splitter, mỗi item có thể đi theo những nhánh khác nhau:

~~~mermaid
flowchart LR
    S["Splitter<OrderLine>"] --> R{"Router theo nhóm SKU"}
    R -->|Sách| B["Book inventory handler"]
    R -->|Văn phòng phẩm| O["Office inventory handler"]
    R -->|Khác| X["Review / unsupported"]
    B --> A["Aggregator"]
    O --> A
    X --> A
~~~

Ví dụ chuỗi trách nhiệm:

~~~text
Batch input
 → Validate whole batch
 → Split into OrderLineTask
 → Filter/Router each task
 → Transformer task → ReserveStockCommand
 → Outbound Gateway to inventory
 → Convert response to ItemResult
 → Aggregator by correlation group
 → Final OrderReservationResult
~~~

**Lưu ý:** Routing **một child** tới một kho không bảo đảm nó đã được giữ hàng. `send()` thành công ở channel chỉ cho biết việc gửi đến ranh giới đó theo semantics của channel, chưa phải nghiệp vụ của kho đã commit.

### 10.1. Vì sao không gọi API kho trong splitter function?

Một splitter method như `OrderBatch::lines` nên đơn giản: trả các phần tử cần xử lý. Nếu chính phương thức split vừa loop, gọi API kho, cập nhật database rồi trả list, retry sẽ khó phân biệt lỗi **phân tách** với lỗi **thực thi nghiệp vụ**, và có thể tạo side effect trùng.

Giữ Splitter **thuần và có thể lặp lại**; đưa I/O, retry và giao dịch vào endpoint chịu trách nhiệm sau nó.

## 11. Aggregator: gom lại theo nhóm, không chỉ đếm ba item

Nếu workflow chỉ cần thông báo/stream mỗi child tới một consumer độc lập, **không bắt buộc** phải dùng Aggregator. Nhưng nếu Gateway cần kết quả “đơn đã giữ đủ hàng hay chưa”, thì cần cơ chế fan-in rõ ràng.

~~~text
Order ORD-701
   |
   +-> Line 1 -> Reserved
   +-> Line 2 -> OutOfStock
   +-> Line 3 -> Reserved
   |
   v
Aggregator
   |
   v
OrderReservationResult(
  orderId="ORD-701",
  outcome="PARTIAL",
  itemResults=[Reserved, OutOfStock, Reserved])
~~~

Để Aggregator hoạt động đáng tin, cần quyết định:

| Vấn đề | Câu hỏi triển khai |
| --- | --- |
| **Correlation strategy** | Nhóm child theo một split execution ID hay business key nào? |
| **Release strategy** | Chờ đủ `sequenceSize`, số kết quả đã biết, hay timeout? |
| **Order of results** | Có phải sắp theo `lineIndex` không, hay thứ tự đến là đủ? |
| **Group timeout** | Khi mất child, trả partial, retry hay giữ chờ? |
| **Group expiration** | Xóa/lưu nhóm khi hoàn thành hoặc hết hạn ra sao? |
| **Duplicate handling** | Một result redeliver có bị tính hai lần? |
| **Persistent state** | Nếu restart giữa chừng, có cần MessageStore bền không? |

### 11.1. Không coi `sequenceSize` là lời bảo đảm delivery

`sequenceSize=3` là **thông tin về số phần dự kiến**, không phải bằng chứng rằng ba child đã được gửi thành công hoặc ba handler đã hoàn thành. Một child có thể lỗi, bị retry hoặc đến muộn; release strategy và error handling phải phản ánh điều đó.

### 11.2. Correlation kỹ thuật và nghiệp vụ khác nhau

Nếu hai đơn có cùng `orderId` nhưng là hai lần thử nghiệp vụ khác nhau, gom dựa duy nhất trên orderId có thể trộn chúng. Có thể dùng **splitExecutionId** để gom các child của một lần chạy và giữ `orderId` làm business context. Idempotency downstream lại dựa trên operation ID ổn định, chẳng hạn `(commandId, lineId, operation)`.

### 11.3. Không có Aggregator thì sao?

Trường hợp batch chỉ dùng để phát một `PriceChanged` cho từng SKU đến những hệ thống khác, mỗi child có thể được xử lý độc lập. Không cần Aggregator nếu upstream không chờ kết quả tổng hợp. Nhưng phải nêu rõ semantics ACK của message gốc: **đã tách xong** khác với **tất cả child đã xử lý xong**.

## 12. Đồng bộ, bất đồng bộ và giới hạn tài nguyên

Một List 3 phần tử đơn giản không tạo nhiều áp lực. Nhưng một batch 100.000 phần tử có thể biến một message đầu vào thành 100.000 message con, gây áp lực lên CPU, heap, queue, broker, database, tracing và downstream rate limits.

| Kênh/transport | Tác động khi Splitter phát nhiều child | Điều cần kiểm soát |
| --- | --- | --- |
| `DirectChannel` + handler đồng bộ | Có thể giữ thread gửi trong suốt chuỗi xử lý | Latency, exception lan ngược, giới hạn request |
| `QueueChannel` nội bộ | Các message được enqueue | Dung lượng queue, consumer poll rate, memory/backpressure |
| `ExecutorChannel` | Chuyển công việc cho executor | Bounded pool/queue, rejection policy, concurrency |
| Kafka/AMQP/JMS outbound | Publish mỗi child ra broker | Batch size, ack, transaction boundary, redelivery |
| HTTP outbound Gateway từng child | Một API call cho mỗi dòng | Rate limit, timeout, retry, circuit breaker nếu phù hợp |

**Không mặc định một `QueueChannel` in-memory là durable** qua restart. Nếu phải replay, audit hay khôi phục nhóm sau sự cố, cần thiết kế persistence/broker theo yêu cầu thật.

### 12.1. Batch lớn: kiểm tra trước khi split

Một số kiểm soát hữu ích:

- Giới hạn `lines.size()` trước khi tạo message con.
- Dùng chunking theo hợp đồng nếu downstream chấp nhận xử lý **nhóm nhỏ** thay vì từng item.
- Đặt queue/executor **có giới hạn** phù hợp và cách báo quá tải.
- Không copy nguyên batch vào **mỗi** child header; điều này có thể nhân bộ nhớ theo số phần tử.
- Giảm số lần truy vấn lặp bằng cách enrich dữ liệu chung **trước** Splitter nếu tất cả item cần cùng metadata đã được xác minh.
- Theo dõi processing lag, queue age, throughput và tỉ lệ lỗi từng item.

### 12.2. Streaming khác List hữu hạn

Nếu nguồn dữ liệu là một cursor database hoặc stream rất lớn, việc dùng `toList()` trước Splitter có thể tạo spike heap. Nhưng dùng Iterator/Stream lazy lại thay đổi cách xác định tổng số child và khả năng Aggregator chờ đủ phần. Đây là **quyết định kiến trúc**, không chỉ đổi một kiểu Java.

Khi dữ liệu quá lớn, cân nhắc **pagination/chunked messages**, checkpoint, consumer độc lập, và một chính sách kết thúc nhóm theo batch/page ID thay vì dựa vào `sequenceSize` chưa chắc biết trước.

## 13. Lỗi từng child, retry và idempotency

Giả sử ba dòng hàng được tách đúng. Handler cho `PEN-5` gọi inventory timeout sau khi hệ thống kho có thể đã giữ hàng. Retry toàn bộ message `OrderBatch` từ đầu sẽ phát lại cả ba child, có thể khiến `BOOK-1` và `BAG-2` bị giữ hàng thêm lần nữa.

~~~mermaid
flowchart TD
    A["Splitter tạo 3 child"] --> B["Item handler"]
    B --> C{"Business result?"}
    C -->|Success| S["ItemResult: SUCCESS"]
    C -->|Transient error| R["Retry hữu hạn theo item"]
    C -->|Permanent reject| F["ItemResult: REJECTED"]
    R -->|Success| S
    R -->|Exhausted / uncertain| E["Error / reconcile / manual review"]
    S --> G["Aggregator"]
    F --> G
    E --> G
~~~

Trong thực tế, nhánh `E` có thể tạo một `ItemResult(UNKNOWN)` cho Aggregator hoặc kết thúc nhóm theo error contract. Đừng mặc định mọi lỗi kỹ thuật đều tạo được phản hồi thành công hoặc rằng Aggregator luôn release.

### 13.1. Idempotency theo item và thao tác

Một khóa phù hợp có thể là:

~~~text
(commandId, lineId, "RESERVE_STOCK")
~~~

Không nên dùng `MessageHeaders.id` làm khóa duy nhất: khi message được xây dựng lại qua broker/retry, message ID có thể thay đổi dù nghiệp vụ vẫn là cùng thao tác. Không nên chỉ dùng `sku` vì hai đơn khác nhau có thể cùng SKU.

### 13.2. `send()` thành công chưa phải item thành công

Phân biệt ít nhất ba mốc:

1. **Splitter emitted:** đã tạo child message.
2. **Channel accepted:** target channel/queue/broker nhận message theo semantics.
3. **Item processed:** consumer đã trả kết quả nghiệp vụ và lưu side effect cần thiết.

Chỉ mốc thứ ba, hoặc một acknowledgment nghiệp vụ tương đương, mới có thể làm căn cứ đánh dấu một item đã hoàn tất.

### 13.3. Error channel và rejected item

Với flow đồng bộ, exception có thể lan về caller; với poller hoặc executor, exception có thể đến error channel theo cấu hình. Một **ItemRejected vì không đủ hàng** là outcome nghiệp vụ khác với **TimeoutException khi gọi kho**. Thiết kế mã trạng thái, retry, dead-letter và quyền can thiệp riêng cho mỗi loại.

## 14. Kiểm thử unit: dữ liệu và task identity

Một bài học về Splitter cần kiểm tra trước hết **batch có được tạo với danh sách đúng hay không**. Unit test giúp phát hiện lỗi do model mutable, quantity không hợp lệ và line index.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderBatchTest {

    @Test
    void batchKeepsStableListSnapshot() {
        List<OrderLine> source = new ArrayList<>();
        source.add(new OrderLine("BOOK-1", 2));

        OrderBatch batch = new OrderBatch("ORD-701", source);
        source.add(new OrderLine("PEN-5", 4));

        assertEquals(1, batch.lines().size());
        assertEquals("BOOK-1", batch.lines().get(0).sku());
    }

    @Test
    void lineTaskFactoryKeepsBusinessLineNumbers() {
        OrderBatch batch = new OrderBatch("ORD-702", List.of(
            new OrderLine("BOOK-1", 2),
            new OrderLine("PEN-5", 4)));

        List<OrderLineTask> tasks =
            new LineTaskFactory().tasks(batch);

        assertEquals(2, tasks.size());
        assertEquals(1, tasks.get(0).lineNumber());
        assertEquals(2, tasks.get(1).lineNumber());
        assertEquals("ORD-702", tasks.get(0).orderId());
    }

    @Test
    void rejectsNonPositiveQuantity() {
        assertThrows(IllegalArgumentException.class,
            () -> new OrderLine("PEN-5", 0));
    }

    @Test
    void allowsEmptyListOnlyAtTheModelLevel() {
        OrderBatch batch = new OrderBatch("ORD-EMPTY", List.of());
        assertTrue(batch.lines().isEmpty());

        // Business validation ở ingress có thể từ chối batch rỗng
        // tùy hợp đồng; record này không tự quyết định điều đó.
    }
}
~~~

Đây là test model/mapper; nó **chưa chứng minh** Spring Integration phát đúng số message con. Bước tiếp theo là integration test với `IntegrationFlow` và channel thật.

## 15. Integration test: đếm và kiểm tra từng child message

Với `BatchSplitterConfiguration` ở mục 7, có thể dùng Spring Test để gửi `OrderBatch` tới `orders.batch.in` rồi đọc từng `OrderLine` từ `orders.items.out`.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(BatchSplitterConfiguration.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class BatchSplitterIntegrationTest {

    @Autowired @Qualifier("orders.batch.in")
    MessageChannel input;

    @Autowired @Qualifier("orders.items.out")
    PollableChannel output;

    @Test
    void splitsThreeLinesAndRetainsBusinessCorrelation() {
        OrderBatch batch = new OrderBatch("ORD-701", List.of(
            new OrderLine("BOOK-1", 2),
            new OrderLine("PEN-5", 4),
            new OrderLine("BAG-2", 1)));

        Message<OrderBatch> source = MessageBuilder
            .withPayload(batch)
            .setHeader("businessCorrelationId", "ORD-701")
            .build();

        assertTrue(input.send(source));

        Message<?> first = output.receive(1000);
        Message<?> second = output.receive(1000);
        Message<?> third = output.receive(1000);

        assertNotNull(first);
        assertNotNull(second);
        assertNotNull(third);

        // Topology demo là đồng bộ và output QueueChannel
        // để quan sát lần lượt các phần tử đã được tách.
        assertEquals(new OrderLine("BOOK-1", 2), first.getPayload());
        assertEquals(new OrderLine("PEN-5", 4), second.getPayload());
        assertEquals(new OrderLine("BAG-2", 1), third.getPayload());

        for (Message<?> child : List.of(first, second, third)) {
            assertEquals("ORD-701",
                child.getHeaders().get("businessCorrelationId"));
        }

        assertNull(output.receive(0), "Không có child thứ tư");
    }

    @Test
    void emptyCollectionProducesNoChildMessage() {
        OrderBatch empty = new OrderBatch("ORD-EMPTY", List.of());
        assertTrue(input.send(MessageBuilder.withPayload(empty).build()));

        assertNull(output.receive(0),
            "Batch rỗng không tự tạo ItemResult");
    }
}
~~~

**Phạm vi của test:** xác nhận Splitter, mapping output channel và payload từng item **trong một JVM**. Nó không kiểm tra xử lý tồn kho thật, không chứng minh Aggregator đã release và không bảo đảm cùng thứ tự hoàn thành nếu về sau chuyển sang xử lý bất đồng bộ.

### 15.1. Kiểm thử List payload trực tiếp

Với flow `ListSplitterConfiguration` ở mục 6, một test tương tự có thể gửi `List.of(A,B)` vào `items.list.in` và assert đúng hai message `OrderLine` ở `items.list.out`, không có message thứ ba. Để tránh trùng code, nên viết helper đọc N message và so sánh payload theo danh sách kỳ vọng.

### 15.2. Kiểm thử sequence metadata cần cấu hình thực

Nếu nghiệp vụ cần Aggregator dựa trên sequence, hãy bổ sung một integration test với **`applySequence` được cấu hình rõ ràng trên Splitter** theo API của phiên bản Spring Integration đang chạy. Test phải xác minh:

- Tất cả child cùng correlation group.
- `sequenceNumber` được đánh đúng 1..N theo source List.
- `sequenceSize` bằng N khi danh sách hữu hạn và hợp đồng áp dụng sequence.
- Header business correlation vẫn đúng.
- Nhóm độc lập của hai batch không bị trộn.

**Không** viết test khẳng định metadata này tồn tại trong mọi source `Iterator/Stream` hoặc mọi lựa chọn cấu hình; hành vi ấy cần được kiểm tra trên topology thực tế.

## 16. Ma trận kiểm thử thực tế

| Nhóm | Input | Kỳ vọng |
| --- | --- | --- |
| Một item | List có 1 phần tử | Phát đúng 1 child |
| Nhiều item | List có 3 phần tử | Phát đúng 3 child có payload tương ứng |
| List rỗng | `[]` | Không phát child; upstream có đường phản hồi EMPTY nếu contract cần |
| List null | DTO có `lines=null` | Rejection/validation rõ ràng trước Splitter |
| Item null | List chứa null | Không tạo payload null; xử lý theo policy |
| Item sai quy tắc | Quantity 0 | Reject cả batch hoặc ItemRejected được thiết kế |
| Dòng trùng giá trị | Hai item giống nhau nhưng có line ID khác | Không bị Set loại nhầm |
| List mutable | Producer sửa list sau publish | Snapshot/immutability bảo toàn dữ liệu |
| HashSet | Dữ liệu không có ordering | Không assert thứ tự nghiệp vụ |
| Sequence | N item với applySequence phù hợp | Correlation/number/size đúng |
| Hai batch đồng thời | ORD-701 và ORD-702 | Không trộn correlation groups |
| Child qua Router | Item SKU nhóm A/B | Đúng nhánh, không đi nhầm |
| Một child bị Filter loại | 2 accepted, 1 rejected | Aggregator có outcome đủ phần/timeout theo contract |
| Handler exception | Một child timeout | Retry/error theo item, không giả success |
| Redelivery | Cùng command được giao lại | Không lặp side effect ở consumer |
| Queue backlog | Nhiều child vào queue giới hạn | Backpressure và monitoring đúng |
| Consumer out-of-order | Child 3 hoàn tất trước child 1 | Aggregator không nhầm thứ tự kết quả |
| Gateway đồng bộ | Batch cần response cuối | Không timeout do empty/missing group |
| Restart | Nhóm xử lý dở | Có quyết định persistence/recovery theo yêu cầu |

### 16.1. Assert nhánh **không** được chọn

Khi Splitter đi qua Router theo SKU, một test chỉ assert `books.out` nhận item sách vẫn chưa đủ: item đó có thể bị gửi nhầm thêm vào `office.out`. Nếu nghiệp vụ yêu cầu **một owner cho mỗi child**, assert:

~~~text
Input Item BOOK-1
expected:
    books.out   = 1
    office.out  = 0
    review.out  = 0
~~~

Khác với Recipient List, nơi cùng một event được **chủ đích gửi tới nhiều người nhận**, Splitter + Content-Based Router thường yêu cầu mỗi item đi **một nhánh xử lý nghiệp vụ**.

## 17. Quan sát số lượng child và hành trình xử lý

Sau Splitter, metric `message count` có thể tăng mạnh. Nếu một input chứa 10 dòng, output có thể tạo 10 child. Không được đọc `outboundMessageCount=10` như có 10 đơn hàng mới.

| Điểm đo | Tín hiệu gợi ý | Câu hỏi |
| --- | --- | --- |
| Ingress | Batch count, average item count | Có bao nhiêu đơn và bao nhiêu dòng? |
| Splitter | Child count/batch, split latency, empty batches | Mỗi batch được tách đúng số phần? |
| Child Router | Channel/lane chosen, item outcomes | SKU đi đúng kho nào? |
| Queue/executor | Queue depth, wait age, rejected tasks | Có đang bị nghẽn do fan-out? |
| Item handler | Success/error, retry attempts, duration | Item nào chưa hoàn tất? |
| Aggregator | Open groups, age, incomplete/expired groups | Có batch nào đang chờ thiếu child? |
| Final response | FULL/PARTIAL/FAILED | Đơn đã hoàn tất theo nghĩa nghiệp vụ chưa? |

**Tránh cardinality cao:** `orderId`, `lineId`, `correlationId` hữu ích trong log/trace có phân quyền; không nên dùng làm metric tags thông thường. Các tag như `endpoint`, `outcome`, `errorClass` và `warehouseRegion` có thể kiểm soát cardinality tốt hơn.

### 17.1. Tracing khi một span tách thành nhiều nhánh

Một trace của batch có thể có nhiều span xử lý từng item. Trace context có thể được truyền qua message headers ở các boundary được cấu hình; qua broker/HTTP cần kiểm tra propagation. Không mặc định cứ có `correlationId` của Aggregator là distributed tracing hoạt động hoàn chỉnh.

### 17.2. Audit kết quả từng item

Với quy trình có side effect, nên lưu dấu theo **operation ID + line ID + attempt/outcome**, phân biệt `DISPATCHED` với `SUCCEEDED`. Điều này giúp reconcile khi một child có thể đã xử lý thành công ở kho nhưng response bị mất do timeout.

## 18. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Hướng cải thiện |
| --- | --- | --- |
| Nhầm Splitter với Recipient List | Mỗi đích nhận nhầm toàn bộ batch hoặc nhiều bản command | Chọn đúng EIP theo payload và recipient |
| Chỉ dùng Transformer đổi `OrderBatch` thành `List<OrderLine>` | Vẫn chỉ một message mang List | Sử dụng Splitter nếu cần từng message con |
| Đổi List sang Set để “khử trùng” | Có thể mất dòng hàng trùng nhưng hợp lệ | Giữ List, dùng business line ID và policy dedup riêng |
| Dùng `HashSet` nhưng mong thứ tự ổn định | Sequence không phản ánh order ban đầu | Dùng List/ordered collection theo contract |
| Đưa toàn bộ batch vào header của từng child | Nhân memory/serialization cost theo N | Chỉ gửi metadata tối thiểu hoặc business task DTO |
| Không xử lý collection rỗng | Gateway/Aggregator chờ phản hồi không đến | Nhánh EMPTY/validation trước split |
| Filter âm thầm drop một child | Aggregator chờ mãi hoặc timeout không rõ | Tạo ItemRejected hoặc release/expiry policy |
| Dùng `orderId` duy nhất để gom mọi replay | Kết quả từ hai phiên chạy trộn nhau | Split execution ID + business context riêng |
| Dùng `MessageHeaders.id` làm idempotency key | Redelivery tạo ID mới, side effect trùng | Command/line/operation key ổn định |
| Retry từ đầu batch khi 1 item timeout | Gửi lại item đã thành công | Retry theo child, idempotent handler |
| Cho Splitter thực hiện network I/O | Khó test, khó tách lỗi, retry lẫn side effect | Splitter thuần; Gateway/handler riêng |
| Tưởng `QueueChannel` luôn bền qua restart | Mất dữ liệu khi ứng dụng dừng | Broker/MessageStore theo yêu cầu durability |
| Split 100.000 item không giới hạn | Heap/queue/consumer quá tải | Quota, chunking, bounded executor và monitoring |
| Test chỉ đếm message, không kiểm payload | Lỗi map sai line có thể bị bỏ sót | Assert payload, metadata, count và negative paths |

## 19. Checklist trước khi triển khai

- [ ] Xác định đầu vào là `List` trực tiếp hay DTO chứa collection.
- [ ] Hợp đồng cho collection rỗng, null, item null và item không hợp lệ được viết rõ.
- [ ] Biết collection có thứ tự hay không; không dùng `HashSet` khi order quan trọng.
- [ ] Không vô tình loại duplicate hợp lệ khi chuyển List thành Set.
- [ ] Các item/DTO được snapshot hoặc thiết kế immutable trước khi chia bất đồng bộ.
- [ ] Splitter trả collection cần thiết, không làm network I/O hay side effect.
- [ ] Mỗi child có business key ổn định, correlation và tracing theo contract.
- [ ] Khi dùng Aggregator, `applySequence` / correlation / release strategy được kiểm tra thực tế.
- [ ] Khi có Filter, rejected item vẫn được biểu diễn thành outcome hoặc nhóm có timeout.
- [ ] Có phân biệt child dispatch, channel accepted và business completion.
- [ ] Có retry từng item, idempotency key và xử lý kết quả không chắc chắn.
- [ ] Có bounded queues/executors, quota số item, backpressure và monitoring.
- [ ] Có unit test DTO/task factory và integration test thật qua message channels.
- [ ] Có test out-of-order, duplicate, empty batch và group expiry khi cần fan-in.
- [ ] Không log toàn bộ payload/headers nhạy cảm ở mọi child.

## 20. Bài tập thực hành

Một sàn thương mại điện tử nhận `ImportProductBatch` gồm `batchId`, `tenantId` và `List<ProductRow>`. Mỗi dòng gồm `sku`, `priceMinor`, `currency`, `warehouseCode`. Dữ liệu có thể đến từ upload CSV đã được parse vào List hoặc từ API JSON.

**Yêu cầu:**

1. Tạo hai record `ProductRow` và `ImportProductBatch`; dùng immutable list, validate số dòng và quy định một batch rỗng có hợp lệ không.
2. Viết Spring Integration Java DSL tách `batch.rows()` bằng Splitter; mỗi child giữ `batchId`/`tenantId` từ nguồn **đã xác thực**.
3. Tạo `ProductImportTask(batchId, rowNumber, row)` để giữ business row identity độc lập với sequence header.
4. Sau Splitter, dùng Router theo `warehouseCode` và Filter kiểm tra currency/price; đảm bảo item bị từ chối vẫn có kết quả `RowRejected`.
5. Thiết kế Aggregator trả `ImportResult(total, imported, rejected)`; mô tả correlation/release/timeout và việc các child có thể hoàn tất không đúng thứ tự.
6. Viết integration test với ba dòng: một hợp lệ kho A, một hợp lệ kho B, một bị reject. Assert số child, nhánh nhận, kết quả và không gửi trùng.
7. Khi message con đi qua Kafka hoặc queue khác, bạn chọn idempotency key nào để một row được import đúng một lần về mặt nghiệp vụ?
8. Với batch 200.000 dòng, nêu quota, chunking, backpressure, tiến độ và kế hoạch khôi phục khi ứng dụng restart.
9. Nếu một row có dữ liệu PII hoặc token, thiết kế cách **không** copy trường không cần thiết sang mọi downstream consumer.

**Gợi ý:** `Gateway/Adapter → Validate batch → Splitter → (Filter/Router từng row) → Transformer → Handler → Aggregator`. Khi không cần trả kết quả tổng hợp, không nhất thiết dùng Aggregator; nhưng phải xác định rõ khi nào upload được đánh dấu đã tiếp nhận, đang xử lý và hoàn tất.

## 21. Tổng kết

**Splitter theo danh sách hoặc collection** là mẫu EIP biến một message mang nhiều phần tử thành **những message con có thể xử lý độc lập**. Với Spring Integration, có thể dùng `.split()` khi payload là List trực tiếp hoặc typed splitter để trích danh sách từ một DTO nghiệp vụ. Số lượng item, ngữ nghĩa thứ tự và tính bất biến của dữ liệu phải được quyết định rõ trước khi mở rộng fan-out.

Để flow hoạt động bền vững, phải phân biệt **Split** với **Recipient List**, tách **business identity** khỏi sequence headers, có chính sách cho **empty/null/invalid item**, và khi dùng Aggregator thì xác định **correlation, release, timeout, duplicate/out-of-order**. Kết hợp Router, Filter, Transformer, Gateway, retry, error channel, idempotency, backpressure và kiểm thử các message con để mỗi item đi **đúng nhánh, đúng số lần và có thể truy vết tới batch gốc**.

**Tài liệu tham khảo:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Splitter, Aggregator, Correlation Identifier, Message Sequence, Pipes and Filters); tài liệu Spring Integration về Splitter, Java DSL, Message Channels, Aggregator, Error Handling và Testing; tài liệu Java SE về `List`, `Collection` và immutable records.

