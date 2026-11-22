# Sequence number và sequence size

**Resequencer** là một Enterprise Integration Pattern (EIP) giúp **khôi phục thứ tự logic của các message đến không đúng thứ tự**. Trong Spring Integration, Resequencer sử dụng metadata của từng message để đưa các phần tử của cùng một chuỗi về thứ tự mong đợi. Hai header cần hiểu rõ nhất là **`sequenceNumber`** — vị trí của message trong chuỗi — và **`sequenceSize`** — tổng số phần tử dự kiến của chuỗi. Thông thường, chúng đi kèm **`correlationId`** để biết các message thuộc chuỗi nào.

Bài này thuộc chương **Resequencer** của module **SPRING_INTEGRATION_PATTERN**. Module học cách thực hành Enterprise Integration Patterns bằng Spring Integration, kết hợp Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation nhằm tạo luồng thông điệp ít phụ thuộc, dễ mở rộng, có kiểm thử và quan sát được.

**Thông điệp chính:** `sequenceNumber` và `sequenceSize` mô tả **vị trí** và **kích thước dự kiến**, không chứng minh message đã được xử lý thành công, không thay thế correlation key và không tự giải quyết message mất, trùng hoặc đến muộn.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích nhiệm vụ của Resequencer và phân biệt nó với Aggregator, Splitter, Router, Filter và Transformer.
2. Đọc đúng bộ metadata `correlationId`, `sequenceNumber`, `sequenceSize` trong `MessageHeaders`.
3. Hiểu rằng sequence number trong các phần được Splitter tạo ra thường **bắt đầu từ 1**, không phải 0.
4. Phân biệt thứ tự **message đến**, thứ tự **xử lý**, thứ tự **phát output** và thứ tự **business commit**.
5. Mô tả cách Resequencer nhóm các message, chờ đủ và phát nhiều message đã sắp xếp mà không gộp payload như Aggregator.
6. Phân biệt **complete-sequence release** và **partial-sequence release**; hiểu gap ảnh hưởng việc phát output thế nào.
7. Hiểu `sequenceSize=0` hoặc sequence size không đáng tin cậy và khi nào cần custom release/timeout.
8. Viết Java DSL `.resequence()`, gửi message có sequence headers qua channel thực và test thứ tự output với JUnit 5.
9. Thiết kế validation cho metadata sai, thiếu, không đồng nhất, trùng sequence number, out-of-range và nhầm correlation group.
10. Xử lý timeout, expiry, duplicate, retry, late arrival, state store, concurrency, bảo mật và observability.

## 2. Vì sao cần Resequencer?

Giả sử một đơn hàng có bốn bước hoặc bốn dòng dữ liệu được xử lý đồng thời. Hệ thống phát ra các message theo thứ tự ban đầu:

~~~text
Part 1 → Part 2 → Part 3 → Part 4
~~~

Sau khi đi qua executor, broker hoặc nhiều consumer, các message có thể đến downstream theo thứ tự:

~~~text
Part 3 → Part 1 → Part 4 → Part 2
~~~

Nếu downstream cần xử lý theo thứ tự logic ban đầu, nó không thể tự giả định **thứ tự đến** là **thứ tự đúng**.

~~~mermaid
flowchart LR
    S["Splitter: 1, 2, 3, 4"] --> E["Xử lý song song"]
    E --> A["Đến: 3"]
    E --> B["Đến: 1"]
    E --> C["Đến: 4"]
    E --> D["Đến: 2"]
    A --> R["Resequencer"]
    B --> R
    C --> R
    D --> R
    R --> O["Phát: 1, 2, 3, 4"]
~~~

Resequencer giúp sắp xếp **các message của cùng chuỗi** theo metadata. Nó không biến bốn payload thành một collection như Aggregator.

### 2.1. Bốn loại thứ tự cần phân biệt

| Loại thứ tự | Ý nghĩa | Ví dụ |
|---|---|---|
| **Logical sequence** | Thứ tự gốc mà producer/contract xác định | 1, 2, 3, 4 |
| **Arrival order** | Thứ tự Resequencer nhận message | 3, 1, 4, 2 |
| **Resequenced output order** | Thứ tự các message được Resequencer phát đi | 1, 2, 3, 4 |
| **Business completion order** | Thứ tự transaction/side effect thực sự hoàn tất | Có thể khác nếu downstream async |

**Resequencer bảo đảm thứ tự phát theo chính sách của nó**, không tự bảo đảm các worker bất đồng bộ phía sau commit database đúng thứ tự. Nếu yêu cầu strict processing order xuyên nhiều worker, cần thêm cơ chế serialize theo key hoặc partitioning và xác nhận xử lý.

## 3. Bộ ba correlationId, sequenceNumber và sequenceSize

Spring Integration dùng các header thuộc contract của message sequence. Khi Splitter biết tổng số phần, thông thường nó tạo:

~~~text
Message 1:
  correlationId = batch-1001
  sequenceNumber = 1
  sequenceSize = 4

Message 2:
  correlationId = batch-1001
  sequenceNumber = 2
  sequenceSize = 4

Message 3:
  correlationId = batch-1001
  sequenceNumber = 3
  sequenceSize = 4

Message 4:
  correlationId = batch-1001
  sequenceNumber = 4
  sequenceSize = 4
~~~

Bộ ba này trả lời ba câu hỏi khác nhau:

- **`correlationId`**: *Message thuộc nhóm/chuỗi nào?*
- **`sequenceNumber`**: *Message đứng ở vị trí nào trong chuỗi đó?*
- **`sequenceSize`**: *Theo hợp đồng, chuỗi này dự kiến có bao nhiêu phần?*

### 3.1. Sequence number bắt đầu từ 1

Khi Splitter phân tách một collection thông thường thành N phần và tạo sequence metadata, các vị trí thường được đánh số **1, 2, ..., N**.

| `sequenceNumber` | `sequenceSize` | Cách hiểu |
|---:|---:|---|
| 1 | 4 | Phần đầu của chuỗi bốn phần |
| 2 | 4 | Phần thứ hai |
| 3 | 4 | Phần thứ ba |
| 4 | 4 | Phần cuối |
| 0 | 4 | Không hợp lệ theo hợp đồng 1-based của ví dụ |
| 5 | 4 | Vượt kích thước của chuỗi |

Không được nhầm `sequenceNumber=1` với index 1 của một Java `List` (phần tử thứ **hai** theo zero-based index). Nếu cần lấy phần tử trong list, vị trí tương ứng là `sequenceNumber - 1` sau khi đã validation.

### 3.2. Sequence size không phải số message đã đến

Khi nhìn thấy `sequenceSize=4`, đó là **kích thước dự kiến** của chuỗi, không phải "hiện đã có bốn message trong store".

Ví dụ tại một thời điểm:

~~~text
group.key = batch-1001
expected sequenceSize = 4
received numbers = [1, 3]
received message count = 2
missing numbers = [2, 4]
~~~

Nếu một message số 3 đến trước, `sequenceSize` vẫn là 4. Resequencer có thể giữ nó lại đến khi đủ điều kiện phát.

### 3.3. CorrelationId không phải MessageHeaders.ID

`MessageHeaders.ID` là ID của một **message instance**. Nếu bốn phần được Splitter tạo ra, mỗi phần có thể mang ID khác nhau nhưng dùng chung `correlationId`.

~~~text
ID(msg1) = UUID-A      correlationId = batch-1001
ID(msg2) = UUID-B      correlationId = batch-1001
ID(msg3) = UUID-C      correlationId = batch-1001
ID(msg4) = UUID-D      correlationId = batch-1001
~~~

Nếu nhóm theo ID từng message, mỗi message trở thành một group riêng, Resequencer sẽ không có đủ các phần liên quan để sắp xếp.

### 3.4. Java constants

Spring Integration cung cấp các tên header qua `IntegrationMessageHeaderAccessor`:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;

String correlationHeader =
        IntegrationMessageHeaderAccessor.CORRELATION_ID;

String numberHeader =
        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER;

String sizeHeader =
        IntegrationMessageHeaderAccessor.SEQUENCE_SIZE;
~~~

Nên dùng constants thay cho việc tự gõ chuỗi header rải rác ở nhiều file. Khi tích hợp với producer ở ngoài Spring, cần xác nhận **tên, kiểu, cách serialize** và ý nghĩa của metadata ở ranh giới giao tiếp.

## 4. Resequencer khác Aggregator như thế nào?

Cả hai đều có thể dùng `MessageGroupStore` và correlation/release strategy, nhưng **hình dạng output khác nhau**.

~~~mermaid
flowchart TB
    I["Các part đến: 3,1,2"] --> R["Resequencer"]
    I --> A["Aggregator"]
    R --> R1["Message(1)"]
    R --> R2["Message(2)"]
    R --> R3["Message(3)"]
    A --> O["Một Message(Collection[1,2,3])"]
~~~

| Tiêu chí | Resequencer | Aggregator |
|---|---|---|
| Mục tiêu | Khôi phục thứ tự message | Kết hợp nhiều message thành kết quả |
| Input | N message liên quan | N message liên quan |
| Output thường gặp | N message phát theo thứ tự | Một message tổng hợp |
| Payload | Giữ payload của từng message | Tạo payload tập hợp hoặc DTO mới |
| Sequence number | Dùng làm khóa sắp xếp | Có thể dùng cho điều kiện release |
| Sequence size | Giúp biết khi nào chuỗi đủ | Giúp biết nhóm đủ trong trường hợp Splitter |
| Group state | Có | Có |
| Partial release | Có thể phát tiền tố liên tục | Có thể phát kết quả tổng hợp một phần theo config |
| Khi nào dùng | Downstream cần từng item đúng thứ tự | Downstream cần kết quả chung |

**Không thêm Aggregator chỉ để sắp xếp** nếu downstream vẫn cần từng message độc lập. Ngược lại, nếu downstream cần tổng tiền của cả đơn, Resequencer chưa tạo ra `OrderTotal`; có thể dùng `.resequence().aggregate()` hoặc một output processor phù hợp.

## 5. Các header được Splitter tạo ra như thế nào?

Một `AbstractMessageSplitter` có trách nhiệm bổ sung correlation/sequence metadata cho các message con. Với một collection đã biết kích thước, chuỗi có thể được biểu diễn đầy đủ.

~~~java
import java.util.List;

List<String> parts = List.of(
        "parse", "validate", "persist", "publish");
~~~

Khi message chứa collection này đi qua Splitter, các message con có thể mang:

~~~text
payload="parse"     sequenceNumber=1 sequenceSize=4
payload="validate"  sequenceNumber=2 sequenceSize=4
payload="persist"   sequenceNumber=3 sequenceSize=4
payload="publish"   sequenceNumber=4 sequenceSize=4
~~~

Tất cả phải có **cùng correlationId của split batch**. Đây là lý do pattern Splitter → ExecutorChannel → Resequencer phổ biến: Splitter tạo metadata, executor cho xử lý các phần bất đồng bộ, Resequencer dùng metadata ấy để khôi phục thứ tự phát.

### 5.1. Không có Splitter vẫn có thể dùng Resequencer

Một producer bên ngoài cũng có thể gửi những message với metadata sequence, ví dụ một batch file chia chunk ở service A rồi truyền qua broker.

Tuy nhiên, không phải mọi message broker tự động có `sequenceNumber` và `sequenceSize` tương thích với Spring Integration. Khi tự gắn headers, bạn phải công bố và kiểm tra:

- Mỗi group có một correlation key không trùng với group khác.
- Mỗi part có sequence number dương theo convention đã chọn.
- Các part trong cùng group có sequence size nhất quán.
- Không có hai payload khác nhau cùng số thứ tự mà không có conflict policy.
- Message đến muộn, mất hoặc replay được xử lý theo contract.
- Header không thể bị giả mạo để trộn dữ liệu của tenant khác.

### 5.2. Khi Splitter có iterator không biết kích thước

Spring Integration có thể split một `Iterator`/`Iterable` mà không biết trước số phần. Trong trường hợp không suy ra được số phần, `sequenceSize` có thể được đặt **0**.

~~~text
iterator -> part #1: sequenceNumber=1, sequenceSize=0
         -> part #2: sequenceNumber=2, sequenceSize=0
         -> ...
         -> part #N: sequenceNumber=N, sequenceSize=0
~~~

**`sequenceSize=0` mang nghĩa "chưa biết tổng số phần" trong trường hợp này, không phải chuỗi chắc chắn có 0 phần.** Một release strategy mặc định cần biết kích thước đầy đủ sẽ không thể dựa vào số 0 để xác định đã nhận hết.

Hướng thiết kế:

1. Nếu có thể, materialize một collection hữu hạn và biết N trước khi split; cân nhắc memory.
2. Dùng một event/end marker tường minh để xác định kết thúc.
3. Cấu hình custom release policy dựa trên completion signal đã xác thực.
4. Sử dụng timeout/expiry có kết quả partial chỉ nếu nghiệp vụ cho phép.
5. Nếu stream rất dài, xem xét công cụ stream processing/partitioning thay vì một resequencer giữ toàn bộ group.

**Không tự đổi `sequenceSize=0` thành kích thước đoán được** để buộc nhóm release.

## 6. Cơ chế grouping và sắp xếp

Giả sử producer phát một chuỗi N=4, nhưng arrival order là:

~~~text
3 → 1 → 4 → 2
~~~

Resequencer thường làm việc theo các bước:

1. Đọc `correlationId` để tìm group.
2. Lưu message vào `MessageGroupStore` của group.
3. Đọc `sequenceNumber` để xác định thứ tự logic.
4. Dùng release policy để quyết định có đủ phần cần thiết hay chưa.
5. Phát các message theo thứ tự số sequence.
6. Duy trì hoặc hoàn tất metadata group theo cấu hình để xử lý late arrivals.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant R as Resequencer
    participant S as MessageGroupStore
    participant O as Output

    P->>R: Part 3/4
    R->>S: Store (3)
    P->>R: Part 1/4
    R->>S: Store (1,3)
    P->>R: Part 4/4
    R->>S: Store (1,3,4)
    P->>R: Part 2/4
    R->>S: Store (1,2,3,4)
    S-->>R: Group complete
    R->>O: Part 1
    R->>O: Part 2
    R->>O: Part 3
    R->>O: Part 4
~~~

Sơ đồ mô tả **chế độ chỉ phát sau khi đủ toàn bộ chuỗi**. Khi bật partial release, một số phần có thể được phát sớm hơn nhưng vẫn phải tôn trọng điều kiện về thứ tự.

## 7. Complete-sequence release (mặc định)

Theo tài liệu Spring Integration, `releasePartialSequences` mặc định là `false`: Resequencer chờ **nhóm hoàn chỉnh** trước khi phát các message đã sắp xếp.

Giả sử group có `sequenceSize=4`:

| Arrival | Các sequence đã lưu | Output ngay lúc đó |
|---|---|---|
| 3 | [3] | Chưa có |
| 1 | [1,3] | Chưa có |
| 4 | [1,3,4] | Chưa có |
| 2 | [1,2,3,4] | Phát 1,2,3,4 theo thứ tự |

Ưu điểm:

- Đơn giản để đảm bảo đã đủ cả chuỗi trước khi phát.
- Hợp lý khi downstream chỉ được nhận phần nếu toàn bộ batch hoàn tất.
- Dễ test bằng QueueChannel: output rỗng cho tới part cuối.

Nhược điểm:

- Một part mất làm tất cả part đang chờ bị giữ lại.
- Latency phụ thuộc part cuối.
- Message store phải giữ nhiều phần khi có gap.
- Không phù hợp một chuỗi vô hạn hoặc sequence size không thể xác định.

### 7.1. "Đủ" phải xét theo sequence metadata

Không nên chỉ tự viết:

~~~java
// Anti-pattern cho những nguồn có thể gửi duplicate:
return group.size() == expectedSequenceSize;
~~~

Nếu group có hai message cùng `sequenceNumber=2` và thiếu `sequenceNumber=3`, số lượng message không phản ánh chuỗi đầy đủ. Hãy sử dụng release policy có hiểu biết về sequence/duplicates, đồng thời có dedup hoặc conflict policy trước resequencer.

Spring Integration có default release behavior tương ứng sequence metadata, nhưng **không được hiểu default là cơ chế exactly-once** của business.

## 8. Partial-sequence release: phát dần khi có đoạn liên tục

Resequencer cũng hỗ trợ `releasePartialSequences(true)`: cho phép phát một **đoạn sequence có thể xác định thứ tự hợp lệ** sớm hơn, thay vì chờ đủ toàn bộ group.

Ví dụ chuỗi N=4 và arrival order:

~~~text
2 → 1 → 4 → 3
~~~

Hành vi mong đợi theo ý tưởng phát dần đoạn liên tục:

| Message đến | Các phần có sẵn | Phần có thể phát theo thứ tự |
|---:|---|---|
| 2 | [2] | Chưa có phần 1, giữ lại |
| 1 | [1,2] | Phát 1 rồi 2 |
| 4 | [4] đang chờ | Chưa có phần 3, giữ lại |
| 3 | [3,4] | Phát 3 rồi 4 |

~~~mermaid
flowchart LR
    A["Arrival: 2"] --> B["Giữ số 2"]
    B --> C["Arrival: 1"]
    C --> D["Emit: 1,2"]
    D --> E["Arrival: 4"]
    E --> F["Giữ số 4"]
    F --> G["Arrival: 3"]
    G --> H["Emit: 3,4"]
~~~

**Quan trọng:** partial release **không cho phép nhảy qua lỗ hổng** một cách tùy tiện. Khi đã phát 1,2, nếu 4 đến mà thiếu 3, không được phát 4 trước 3 chỉ vì 4 đã có mặt.

### 8.1. Khi nào dùng partial release?

- Downstream có thể bắt đầu xử lý prefix sớm.
- Những part đã phát không cần chỉnh sửa khi part sau tới.
- Latency quan trọng hơn việc chờ đủ batch.
- Một lỗ hổng tạm thời vẫn phải được theo dõi.
- Có chính sách timeout/expiry khi một số phần không bao giờ tới.

### 8.2. Partial release không thay timeout/expiry

`releasePartialSequences(true)` cho phép gửi phần hợp lệ sớm. Còn `sendPartialResultOnExpiry` liên quan xử lý khi **group hết hạn**, là cơ chế khác. Không nhầm "partial" trong hai tên cấu hình: một bên nói về **phát đoạn liên tục trong quá trình nhận**, một bên nói về **xử lý nhóm hết hạn**.

### 8.3. Chi phí của partial release

Tìm các đoạn hợp lệ liên tục và theo dõi sequence đã phát có thể tốn CPU/memory, nhất là group lớn hoặc có nhiều gap. Resequencer phù hợp nhất với những chuỗi **tương đối ngắn và ít lỗ hổng**. Với event stream lớn vô hạn, cân nhắc key partitioning hay stream processor có state store chuyên dụng.

## 9. Đọc metadata bằng Java một cách an toàn

Không nên ép kiểu tùy tiện từ `MessageHeaders`, đặc biệt khi dữ liệu đến từ broker hoặc HTTP adapter có header mapper/serializer khác nhau.

### 9.1. Snapshot quan sát

~~~java
public record SequenceSnapshot(
        String stage,
        String correlationId,
        int sequenceNumber,
        int sequenceSize
) {}
~~~

`sequenceNumber` và `sequenceSize` là metadata của **message đang quan sát**. Một Resequencer phát 1,2,3,4 không biến tất cả message output thành cùng số sequence.

### 9.2. Hàm đọc từ Message

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;

public final class SequenceInspector {

    private SequenceInspector() {}

    public static SequenceSnapshot snapshot(
            String stage, Message<?> message) {

        Object correlation = message.getHeaders().get(
                IntegrationMessageHeaderAccessor.CORRELATION_ID);

        Integer number = message.getHeaders().get(
                IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                Integer.class);

        Integer size = message.getHeaders().get(
                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                Integer.class);

        if (correlation == null
                || number == null
                || size == null) {
            throw new IllegalArgumentException(
                    "SEQUENCE_HEADERS_REQUIRED");
        }

        if (number < 1) {
            throw new IllegalArgumentException(
                    "SEQUENCE_NUMBER_INVALID");
        }

        // size=0: unknown size; size>0: known length.
        if (size < 0 || (size > 0 && number > size)) {
            throw new IllegalArgumentException(
                    "SEQUENCE_SIZE_INVALID");
        }

        return new SequenceSnapshot(
                stage,
                correlation.toString(),
                number,
                size);
    }
}
~~~

Hàm này phục vụ **inspector/validation** cho ví dụ, không thay thế framework resequencing strategy. Việc gọi `toString()` cho correlation chỉ thích hợp với một contract quan sát có kiểu/giá trị đã được kiểm soát; nếu cần group key bảo mật hoặc byte array, hãy có bộ mã hóa định danh riêng và không log toàn bộ object tùy ý.

### 9.3. Validation tại ingress

Nếu các message được tạo bởi Splitter nội bộ, Spring có thể tự tạo headers đúng. Nhưng với dữ liệu từ client không tin cậy, nên xác nhận:

- Correlation ID có mặt, đúng namespace và thuộc đúng tenant.
- Sequence number thuộc kiểu số nguyên dương, bắt đầu từ 1.
- Sequence size là số nguyên dương, hoặc 0 **chỉ khi contract cho phép unknown length**.
- Với known size, `sequenceNumber <= sequenceSize`.
- Mọi message trong group có cùng sequence size theo contract.
- Không có hai payload xung đột cùng sequence number.
- Giới hạn size tối đa để tránh DoS bằng metadata giả tạo.

**Không** tự động sửa `sequenceNumber=0` thành 1 hay `sequenceSize=-1` thành 0. Đó là dữ liệu không hợp lệ hoặc không tương thích, phải xử lý theo hợp đồng.

## 10. Tạo message có sequence headers khi không dùng Splitter

Bên dưới là ví dụ kiểm thử/adapter tự tạo metadata. Khi có Splitter thật, **ưu tiên để Splitter tạo headers** thay vì dựng thủ công.

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public record Part(String batchId, String value) {}

public final class SequencedMessages {

    private SequencedMessages() {}

    public static Message<Part> part(
            String batchId, int number, int total, String value) {

        if (batchId == null || batchId.isBlank()) {
            throw new IllegalArgumentException(
                    "BATCH_ID_REQUIRED");
        }
        if (total < 1 || number < 1 || number > total) {
            throw new IllegalArgumentException(
                    "INVALID_SEQUENCE_RANGE");
        }

        return MessageBuilder
                .withPayload(new Part(batchId, value))
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        batchId)
                .setHeader(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                        number)
                .setHeader(
                        IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                        total)
                .setHeader("businessCorrelationId", batchId)
                .build();
    }
}
~~~

**Lưu ý Java:** hai khai báo top-level `public` trong ví dụ cần ở hai source file riêng có tên `Part.java` và `SequencedMessages.java` khi đưa vào project thực.

Đặt thêm `businessCorrelationId` để thuận tiện truy vết nghiệp vụ, nhưng không nhầm trường đó với `correlationId` do Resequencer dùng theo cấu hình mặc định.

## 11. Java DSL: Resequencer trong Spring Integration

Spring Integration Java DSL hỗ trợ `.resequence()`. Ví dụ dưới đây tạo một flow **độc lập** nhận message đã có sequence headers.

### 11.1. Flow complete-sequence mặc định

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class CompleteResequencerConfig {

    @Bean(name = "resequencer.complete.input")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "resequencer.complete.output")
    public PollableChannel output() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow completeResequencerFlow() {
        return IntegrationFlow
                .from("resequencer.complete.input")
                .resequence()
                .channel("resequencer.complete.output")
                .get();
    }
}
~~~

Đây là một resequencer với correlation/release behavior mặc định cho chuỗi có metadata đầy đủ. `DirectChannel` nhận input đồng bộ, `QueueChannel` giữ output để JUnit test đọc từng message.

Không cần viết một method annotated `@Resequencer`: tài liệu Spring Integration không cung cấp annotation chuyên dụng tương đương với một số endpoint khác. Hãy dùng DSL hoặc XML/bean endpoint phù hợp phiên bản.

### 11.2. Flow partial release

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class PartialResequencerConfig {

    @Bean(name = "resequencer.partial.input")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "resequencer.partial.output")
    public PollableChannel output() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow partialResequencerFlow() {
        return IntegrationFlow
                .from("resequencer.partial.input")
                .resequence(s ->
                        s.releasePartialSequences(true))
                .channel("resequencer.partial.output")
                .get();
    }
}
~~~

Hai configuration classes là **hai ví dụ thay thế**, có thể chạy/test riêng. Nếu dùng chúng trong cùng project và context, tên bean khác nhau như trên để tránh cạnh tranh endpoint hoặc nhầm input/output channel.

### 11.3. Mô hình Splitter → Executor → Resequencer

Một flow chuẩn được Spring Integration mô tả có dạng:

~~~java
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.MessageChannels;
import org.springframework.context.annotation.Bean;

// taskExecutor là executor bean đã được cấu hình trong ứng dụng.
@Bean
IntegrationFlow splitResequenceAggregateFlow() {
    return IntegrationFlow.from("work.batch")
            .split()
            .channel(MessageChannels.executor(taskExecutor))
            .resequence()
            .aggregate()
            .get();
}
~~~

Đây là **đoạn cấu hình minh họa trong một class có biến/bean `taskExecutor` đã tồn tại**, không phải class Java có thể biên dịch độc lập. Nó cho thấy:

1. Splitter tạo sequence headers.
2. ExecutorChannel có thể làm các part đến không theo thứ tự ban đầu.
3. Resequencer phục hồi thứ tự.
4. Aggregator có thể gom các message đã phát thành một result chung.

Nếu chỉ cần downstream xử lý từng part **đã xếp thứ tự**, hãy **bỏ `.aggregate()`**. Nếu muốn tập hợp toàn bộ kết quả, Aggregator là một bước khác với Resequencer.

## 12. Integration test complete-sequence release

Test thực hiện theo đúng tình huống: gửi `3,1,4,2` vào một `DirectChannel` rồi đọc output từ QueueChannel.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.ArrayList;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = CompleteResequencerConfig.class)
class CompleteResequencerFlowTest {

    @Autowired
    @Qualifier("resequencer.complete.input")
    MessageChannel input;

    @Autowired
    @Qualifier("resequencer.complete.output")
    PollableChannel output;

    @Test
    void holdsUntilCompleteAndEmitsInSequenceOrder() {
        String group = "batch-complete-1001";

        assertTrue(input.send(
                SequencedMessages.part(group, 3, 4, "C")));
        assertNull(output.receive(0));

        assertTrue(input.send(
                SequencedMessages.part(group, 1, 4, "A")));
        assertNull(output.receive(0));

        assertTrue(input.send(
                SequencedMessages.part(group, 4, 4, "D")));
        assertNull(output.receive(0));

        assertTrue(input.send(
                SequencedMessages.part(group, 2, 4, "B")));

        List<Integer> numbers = new ArrayList<>();
        List<String> values = new ArrayList<>();

        for (int i = 0; i < 4; i++) {
            Message<?> next = output.receive(1000);
            assertNotNull(next);

            numbers.add(next.getHeaders().get(
                    IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                    Integer.class));

            values.add(((Part) next.getPayload()).value());
        }

        assertEquals(List.of(1, 2, 3, 4), numbers);
        assertEquals(List.of("A", "B", "C", "D"), values);
        assertNull(output.receive(0));
    }
}
~~~

**Điều test chứng minh:**

- Sequence number từ **1** đến **4** có ý nghĩa thứ tự.
- Resequencer mặc định chưa phát output khi group chưa đủ.
- Thứ tự output theo sequence, **không theo arrival**.
- Output vẫn là bốn **message riêng**, không phải một collection.
- Group key được dùng để nhận biết bốn message cùng chuỗi.

Test không chứng minh các message đã được xử lý thành công ở database hay broker downstream. Nếu nối qua async channel, phải kiểm thử thêm thời điểm consumer thực sự hoàn thành.

### 12.1. Test với hai correlation groups độc lập

Khi nhận:

~~~text
A#2, B#1, A#1, B#2
~~~

Resequencer phải nhóm theo `correlationId` và phát từng group đúng thứ tự. Nó không cần đảm bảo **toàn cục** rằng tất cả message của group A phát trước group B nếu hai nhóm độc lập.

Với `sequenceSize=2` cho mỗi group, một integration test nên dùng group keys duy nhất và kiểm tra:

- Group A phát A#1 trước A#2.
- Group B phát B#1 trước B#2.
- Không có payload của group A xuất hiện trong metadata của B.
- Không bắt buộc một global order giữa hai group khi concurrency tăng.

## 13. Integration test partial-sequence release

Test thứ hai kiểm tra chế độ có thể phát các prefix liên tục mà không chờ toàn bộ sequence size.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = PartialResequencerConfig.class)
class PartialResequencerFlowTest {

    @Autowired
    @Qualifier("resequencer.partial.input")
    MessageChannel input;

    @Autowired
    @Qualifier("resequencer.partial.output")
    PollableChannel output;

    private int nextSequence() {
        Message<?> next = output.receive(1000);
        assertNotNull(next);
        return next.getHeaders().get(
                IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                Integer.class);
    }

    @Test
    void emitsOnlyContiguousPrefixAsItBecomesAvailable() {
        String group = "batch-partial-2001";

        input.send(SequencedMessages.part(group, 2, 4, "B"));
        assertNull(output.receive(0));

        input.send(SequencedMessages.part(group, 1, 4, "A"));
        assertEquals(1, nextSequence());
        assertEquals(2, nextSequence());
        assertNull(output.receive(0));

        input.send(SequencedMessages.part(group, 4, 4, "D"));
        assertNull(output.receive(0));

        input.send(SequencedMessages.part(group, 3, 4, "C"));
        assertEquals(3, nextSequence());
        assertEquals(4, nextSequence());
        assertNull(output.receive(0));
    }
}
~~~

Các assert mô tả behavior mong muốn của `releasePartialSequences(true)` với một group hữu hạn, không có duplicate và có gap tạm thời. Việc chạy test trên phiên bản thư viện của project giúp xác minh implementation và lifecycle settings thực tế, nhất là nếu dự án cấu hình custom release strategy hoặc message store.

### 13.1. Vì sao không test partial bằng một batch split đồng bộ?

Nếu Splitter gửi toàn bộ part 1,2,3,4 ngay và downstream không thay đổi thứ tự, test có thể pass dù Resequencer không có tác dụng. Gửi trực tiếp thứ tự **2,1,4,3** giúp chứng minh logic giữ gap rồi phát prefix.

## 14. Unit test validator/inspector

Một unit test độc lập với Spring context giúp kiểm tra các ràng buộc metadata.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.integration.IntegrationMessageHeaderAccessor;

class SequenceInspectorTest {

    @Test
    void readsExpectedSequenceHeaders() {
        Message<Part> message =
                SequencedMessages.part("batch-1", 2, 4, "B");

        SequenceSnapshot snapshot =
                SequenceInspector.snapshot("ingress", message);

        assertEquals("batch-1", snapshot.correlationId());
        assertEquals(2, snapshot.sequenceNumber());
        assertEquals(4, snapshot.sequenceSize());
    }

    @Test
    void rejectsMissingCorrelationHeader() {
        Message<String> input =
                MessageBuilder.withPayload("data")
                        .setHeader(
                                IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                                1)
                        .setHeader(
                                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                                2)
                        .build();

        assertThrows(
                IllegalArgumentException.class,
                () -> SequenceInspector.snapshot("ingress", input));
    }

    @Test
    void rejectsNumberLargerThanKnownSize() {
        Message<String> input =
                MessageBuilder.withPayload("data")
                        .setHeader(
                                IntegrationMessageHeaderAccessor.CORRELATION_ID,
                                "batch-2")
                        .setHeader(
                                IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                                5)
                        .setHeader(
                                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                                4)
                        .build();

        assertThrows(
                IllegalArgumentException.class,
                () -> SequenceInspector.snapshot("ingress", input));
    }

    @Test
    void acceptsUnknownSizeWhenPolicyAllowsIt() {
        Message<String> input =
                MessageBuilder.withPayload("data")
                        .setHeader(
                                IntegrationMessageHeaderAccessor.CORRELATION_ID,
                                "stream-1")
                        .setHeader(
                                IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                                3)
                        .setHeader(
                                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                                0)
                        .build();

        SequenceSnapshot snapshot =
                SequenceInspector.snapshot("ingress", input);

        assertEquals(0, snapshot.sequenceSize());
    }
}
~~~

**Giới hạn của test:** việc `SequenceInspector` chấp nhận `sequenceSize=0` không có nghĩa Resequencer mặc định sẽ hoàn tất chuỗi ấy. Đó chỉ là một trạng thái metadata hợp lệ nếu contract ứng dụng cho phép **unknown length**; cách release vẫn phải được thiết kế riêng.

## 15. Các lỗi sequence metadata phổ biến

| Input metadata | Vấn đề | Hướng xử lý |
|---|---|---|
| `sequenceNumber=0`, `size=4` | Sai 1-based convention | Reject/validation |
| `number=-1` | Vị trí không hợp lệ | Reject |
| `number=5`, `size=4` | Ngoài phạm vi | Reject |
| `number=2`, không có `correlationId` | Không xác định group | Reject hoặc custom correlation |
| `number=2`, `size="4"` là String | Sai kiểu so với contract | Chuẩn hóa tại adapter hoặc reject |
| `number=3`, `size=0` | Unknown size | Custom completion policy nếu cần full release |
| `number=2` xuất hiện hai lần | Duplicate/conflict | Dedup theo eventId/partId |
| Trong cùng group size 4 và 5 | Metadata không nhất quán | Quarantine/contract violation |
| Hai tenant dùng cùng group key | Nguy cơ trộn dữ liệu | Composite trusted key |
| Có part 1,3,4 mà thiếu 2 | Gap | Wait, timeout, partial policy |
| Sequence size cực lớn do client gửi | Nguy cơ tiêu tốn tài nguyên | Limit size và quota |
| Message đến sau khi group đóng | Late arrival | Discard/correction theo policy |

### 15.1. Duplicate sequenceNumber

Hai message cùng `sequenceNumber=2` có thể là:

- **Redelivery của cùng event**: có thể dedup theo `eventId`.
- **Dữ liệu xung đột**: hai payload khác nhau cùng vị trí, cần reject hoặc version policy.
- **Bug upstream**: Splitter/producer tạo sequence không ổn định.

Không nên chỉ đếm số message rồi coi group đủ. **Dedup theo MessageHeaders.ID** cũng không đủ xuyên replay nếu message mới có UUID khác. Dùng event/part identity bền vững do ứng dụng quản lý.

### 15.2. Sequence size thay đổi giữa các part

Nếu part 1 mang `sequenceSize=4` còn part 2 mang `sequenceSize=5`, đó là tình huống **không nhất quán trong hợp đồng chuỗi**. Resequencer không thể suy ra một kết thúc chính xác chỉ từ các số đó khi chưa có policy rõ. Nên validate toàn group hoặc chuẩn hóa ở producer, đồng thời đưa nhóm vào error/quarantine khi xung đột.

### 15.3. Không dùng timestamp thay sequence number khi yêu cầu thứ tự tuyệt đối

Timestamp có thể bị trùng, lệch clock, hoặc được tạo ở nhiều producer không đồng bộ. Nếu nghiệp vụ yêu cầu thứ tự nghiêm ngặt, dùng một **logical sequence** được phân bổ bởi nguồn đáng tin cậy (hoặc key-partitioning phù hợp) thay vì hy vọng sort theo wall-clock luôn đúng.

## 16. Resequencer với Transformer, Filter và Router

### 16.1. Transformer có thể làm mất sequence headers

Nếu Transformer trả **payload mới** theo API Spring Integration, framework thường truyền headers phù hợp. Nếu ứng dụng trả một `Message<?>` tự tạo, các headers sequence có thể bị mất nếu không được copy/mapper xử lý.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public Message<String> normalize(Message<String> input) {
    return MessageBuilder
            .withPayload(input.getPayload().strip())
            .copyHeaders(input.getHeaders())
            .build();
}
~~~

Đoạn `copyHeaders(...)` dành cho **flow nội bộ tin cậy**. Ở ranh giới broker/API, cần whitelist header thích hợp để tránh serializing `replyChannel`, security token hoặc object nội bộ.

### 16.2. Filter loại một part

Nếu Splitter đặt `sequenceSize=4` nhưng Filter loại phần 2:

~~~text
Available: 1,3,4
Missing:   2
Expected:  4
~~~

- Complete release sẽ không có chuỗi đủ.
- Partial release có thể phát phần 1, nhưng 3 và 4 phải chờ lỗ hổng số 2.
- Khi đến timeout, cần một expiry/partial policy rõ.
- Một Filter trả `false` là một quyết định nghiệp vụ, **không tự sửa sequence size**.

Các cách thiết kế:

1. Filter collection trước Splitter, để chỉ split các phần cần xử lý.
2. Phát một **skipped result/marker** tại vị trí 2 nếu downstream yêu cầu đủ chỗ.
3. Dùng custom release/correction policy cho những phần cố ý bỏ qua.
4. Cấu hình timeout/expiry nếu business chấp nhận mất part.

### 16.3. Router chia nhánh sau Splitter

Nếu Router đưa part 1,3 qua nhánh A và 2,4 qua B, mỗi nhánh có thể không có một sequence hoàn chỉnh để Resequencer release độc lập. Khi cần fan-in, phải thiết kế output channel hội tụ và bảo toàn correlation/sequence headers.

### 16.4. Splitter → Resequencer → Aggregator

~~~mermaid
flowchart LR
    IN["List batch"] --> SPLIT["Splitter"]
    SPLIT --> EX["ExecutorChannel"]
    EX --> RS["Resequencer"]
    RS --> AG["Aggregator"]
    AG --> OUT["Một aggregate result"]
~~~

Resequencer giúp **đảm bảo thứ tự các message đi vào Aggregator**, nhưng Aggregator vẫn là endpoint khác dùng group và output processor. Nếu Aggregator không yêu cầu thứ tự part để tính kết quả, có thể không cần Resequencer; tránh thêm state/latency chỉ vì nó tồn tại như một EIP.

### 16.5. Publish–Subscribe

Một channel publish–subscribe có thể tạo nhiều nhánh cùng nhận một message. Nếu hai nhánh cùng phát kết quả về chung Resequencer mà không có convention riêng cho sequence, có thể tạo duplicate sequence numbers. Cần định nghĩa **sequence của kết quả fan-in**, không dùng lại metadata từ bản sao broadcast một cách mù quáng.

## 17. Timeout, expiry, late arrivals và nhóm trống

Resequencer không thể buộc một producer gửi part bị thiếu. Nếu thiếu part 2, nhóm có thể giữ các part 3,4 quá lâu.

~~~mermaid
flowchart TD
    G["Group đang chờ"] --> C{"Đã đủ phần hợp lệ?"}
    C -->|Có| OUT["Phát theo sequence order"]
    C -->|Chưa| T{"Group timeout/expiry?"}
    T -->|Chưa| WAIT["Tiếp tục chờ"]
    T -->|Rồi| P{"Policy cho partial on expiry?"}
    P -->|Có| PART["Phát phần được phép theo policy"]
    P -->|Không| DISC["Discard / report incomplete"]
~~~

### 17.1. Timeout không đồng nghĩa sendTimeout

- **Group timeout/expiry**: giới hạn **thời gian chờ** message còn thiếu.
- **Send timeout**: thời gian cho một thao tác gửi output vào channel có giới hạn capacity, như QueueChannel hữu hạn.

Nếu nhóm chưa đủ vì thiếu part, tăng `sendTimeout` sẽ không giúp nhóm release. Ngược lại, group đã đủ nhưng output queue đầy là một vấn đề dispatch/backpressure.

### 17.2. Phát partial khi group hết hạn

Spring Integration có tùy chọn `sendPartialResultOnExpiry` theo cấu hình correlating handler. Nó khác với `releasePartialSequences(true)`. Khi nghiệp vụ cho phép phát các message đang giữ khi group hết hạn, phải nêu rõ:

- Có chấp nhận **gap** trong chuỗi không?
- Downstream có biết thiếu part nào không?
- Một message phát lúc expiry có được coi là final không?
- Late arrival sau đó được discard, correction hay mở group mới?
- Nhóm đã được cleanup nhưng metadata completed có cần giữ để chống replay không?

Không phát nhóm thiếu vào nhánh business **đòi complete** nếu chưa có hợp đồng partial result.

### 17.3. Completed-group metadata

Khi group release/expire, Spring Integration có thể giữ metadata nhóm đã hoàn tất trong store để nhận diện các message tới muộn. Cơ chế lưu metadata, thời gian retention và lựa chọn xóa group tùy cấu hình message store/expiry.

Nếu xóa metadata quá sớm, một part đến muộn có thể tạo **group mới bị thiếu prefix** và chờ tiếp. Nếu giữ vô hạn, store có thể tăng. Cần quy định retention theo thời gian replay hợp lý.

## 18. MessageGroupStore, concurrency và durability

Resequencer giống Aggregator ở chỗ cần lưu những part chưa thể release. Message store trong bộ nhớ thích hợp cho test hoặc ứng dụng chấp nhận mất state khi restart. Nếu cần durability, chọn persistent `MessageGroupStore` và kiểm thử.

### 18.1. Một JVM

- Một `DirectChannel` cho flow đồng bộ dễ quan sát.
- Nhiều producer thread vẫn có thể gửi cùng group đồng thời.
- Không tự thay store bằng một `ArrayList` global thiếu locking.
- Test group còn gap, complete, duplicate và timeout.

### 18.2. Nhiều worker

Với `ExecutorChannel`, các part có thể đến sai thứ tự. Resequencer phục hồi thứ tự **phát**, nhưng output downstream nếu lại qua executor khác vẫn có thể hoàn tất out-of-order. Nếu nghiệp vụ cần strict serial commit, phải kiểm soát thread/concurrency theo key ở downstream.

### 18.3. Nhiều JVM

Nếu message cùng correlation key được chia cho hai app instances với hai in-memory stores riêng, mỗi instance có thể chỉ nhận một phần và không đủ nhóm. Giải pháp có thể là:

- Partition input theo correlation key để cùng group tới cùng instance.
- Dùng shared/persistent message group store và locking phù hợp.
- Dùng stream-processing framework có keyed state và ordered partition semantics.
- Thiết kế process manager nếu chuỗi là workflow dài hạn.

### 18.4. Performance

Resequencer phù hợp cho chuỗi hữu hạn tương đối ngắn, ít gap. Nếu nhận hàng triệu group rời rạc và nhiều message bị thiếu, bộ nhớ/CPU có thể tăng do các group mở quá lâu. Monitor số group, tuổi group và khoảng trống; áp dụng quota, timeout và bảo mật trước khi đưa dữ liệu vào store.

## 19. Retry và idempotency

### 19.1. Retry input part

Nếu broker redeliver part số 2, Resequencer có thể nhận lại một message với cùng logical sequence number nhưng Message ID khác. Cần:

- `eventId` hoặc `partId` ổn định qua replay.
- Dedup hoặc conflict policy khi cùng sequence number xuất hiện.
- Validation tất cả part thuộc cùng correlation group.
- Giới hạn số lần retry của lỗi hạ tầng.
- Không retry vô hạn input sai metadata.

### 19.2. Retry downstream

Resequencer có thể phát message 1,2,3 theo thứ tự, nhưng handler downstream đã ghi DB cho 1 rồi lỗi ở 2. Khi retry cả flow, part 1 có thể bị phát lại. Resequencer **không cung cấp exactly-once side effects**.

Dùng idempotency key ở handler, transaction/outbox nếu cần, và quan sát outcome thật. Không coi "đã phát theo đúng sequence" là "đã commit tất cả theo đúng sequence".

### 19.3. Error channel

Trong `DirectChannel` đồng bộ, lỗi gửi/output có thể nổi về caller. Trong executor/broker async, exception có thể đi qua `ErrorMessage` và error handling tùy adapter. Message bị thiếu dẫn đến group chưa release **không nhất thiết là exception**, nên cần metric/timeout riêng thay vì chỉ chờ error channel.

## 20. Monitoring sequenceNumber/sequenceSize

Một hệ thống Resequencer cần quan sát cả **số message đầu vào** lẫn **mức hoàn chỉnh và độ trễ của từng chuỗi**.

| Metric/log | Ý nghĩa | Lưu ý |
|---|---|---|
| `resequencer_messages_received_total` | Số part vào | Có thể label theo flow |
| `resequencer_messages_emitted_total` | Số part phát ra | Không đồng nhất với số group |
| `resequencer_groups_open` | Số chuỗi đang chờ | Monitor memory/store |
| `resequencer_group_age_seconds` | Tuổi nhóm | Phát hiện stuck group |
| `resequencer_gaps_detected_total` | Số lần thấy lỗ hổng | Phân biệt gap tạm/thật |
| `resequencer_expired_total` | Số group quá hạn | Điều tra missing part |
| `resequencer_duplicates_total` | Sequence number/event ID trùng | Dedup/conflict policy |
| `resequencer_late_arrivals_total` | Part đến sau khi nhóm đóng | Retention/producer SLA |
| `resequencer_output_failures_total` | Lỗi dispatch | Khác group timeout |
| `resequencer_buffered_messages` | Số part đang giữ | Capacity/backpressure |

Một log có cấu trúc:

~~~text
flow=invoice-line-resequence
correlationId=batch-1001
sequenceNumber=3
sequenceSize=4
receivedUnique=[1,3]
missingCount=2
releaseMode=COMPLETE
emitted=false
groupAgeMs=1500
traceId=trace-1001
~~~

Ví dụ này nhằm diễn giải trạng thái. Không log toàn bộ payload chứa thông tin khách hàng hoặc thanh toán. Không đưa `correlationId`, `orderId`, `eventId`, `traceId` làm metric labels có cardinality cao; đặt chúng trong logs/traces có chính sách bảo mật.

### 20.1. Sequence gap không tự chứng minh mất dữ liệu

Nếu thấy part 1 và 3 nhưng chưa thấy 2, có thể:

- Part 2 đang xử lý chậm.
- Broker đang retry.
- Producer bỏ sót phần.
- Metadata của part 2 sai khiến nó vào group khác.
- Filter/Router loại part 2.
- Event có thể tới muộn sau deadline.

Do đó nên quan sát `groupAge` và deadline trước khi kết luận part đã mất.

### 20.2. Trace và business correlation

`traceId` dùng để theo dõi các chặng qua service. `correlationId` giúp Resequencer nhóm các part. `businessCorrelationId` liên kết một nghiệp vụ dài hạn như order/invoice. Chúng có thể liên quan nhau nhưng **không mặc định đồng nhất**, đặc biệt trong hệ thống nhiều request/producer.

## 21. Sai lầm thường gặp

### Sai lầm 1 — Dùng zero-based sequenceNumber

**Triệu chứng:** producer tạo part 0,1,2 cho chuỗi size=3; Resequencer không xử lý theo hợp đồng 1-based.

**Khắc phục:** đánh số 1..N, hoặc adapter chuyển đổi theo contract ngay ở ingress và có test.

### Sai lầm 2 — Hiểu sequenceSize là số part đã nhận

**Triệu chứng:** khi group có hai message, code đặt `sequenceSize=2` dù producer dự kiến bốn.

**Khắc phục:** giữ sequenceSize là **tổng dự kiến**, quản lý received count riêng.

### Sai lầm 3 — Không gắn correlationId

**Triệu chứng:** các part không vào cùng group hoặc xảy ra lỗi thiếu group key.

**Khắc phục:** dùng key duy nhất đúng phạm vi batch/tenant và kiểm tra trước Resequencer.

### Sai lầm 4 — Duplicate làm nhóm đủ giả

**Triệu chứng:** part 2 xuất hiện hai lần và ứng dụng đếm đủ ba message mặc dù thiếu part 3.

**Khắc phục:** dedup theo eventId/sequence key và validation của tập sequence; không release chỉ bằng raw count.

### Sai lầm 5 — SequenceSize=0 nhưng chờ complete release

**Triệu chứng:** iterator sinh sequenceSize=0; flow mặc định không xác định được lúc nào kết thúc.

**Khắc phục:** có explicit end signal/custom release hoặc chuyển sang collection hữu hạn khi phù hợp.

### Sai lầm 6 — Bật partial release rồi hiểu là bỏ qua gap

**Triệu chứng:** ứng dụng mong phát part 4 khi chưa có part 3.

**Khắc phục:** partial release chỉ phát đoạn sequence hợp lệ, không nhảy qua phần thiếu một cách tự động.

### Sai lầm 7 — Không có timeout/expiry

**Triệu chứng:** group thiếu part giữ state mãi, memory tăng.

**Khắc phục:** đặt deadline và incomplete-group policy, monitor group age.

### Sai lầm 8 — Mất headers sau Transformer

**Triệu chứng:** payload còn nhưng sequence headers biến mất khi tạo Message mới.

**Khắc phục:** kiểm tra propagation của `correlationId`, `sequenceNumber`, `sequenceSize`, trace và business ID qua mọi bước.

### Sai lầm 9 — Dùng Timestamp thay logical sequence

**Triệu chứng:** clock lệch hoặc timestamp trùng làm thứ tự kết quả không ổn định.

**Khắc phục:** dùng sequence number ổn định từ nguồn có quyền cấp thứ tự.

### Sai lầm 10 — Dùng Resequencer để thay Aggregator

**Triệu chứng:** downstream mong một collection nhưng nhận nhiều message riêng.

**Khắc phục:** thêm Aggregator nếu cần N→1; Resequencer chỉ N→N có thứ tự.

### Sai lầm 11 — Tin rằng resequencing là strict DB commit ordering

**Triệu chứng:** output 1,2,3 nhưng các worker async commit 2 trước 1.

**Khắc phục:** kiểm soát concurrency/partition/processing acknowledgement ở downstream.

### Sai lầm 12 — Chia một group vào nhiều app instances

**Triệu chứng:** mỗi in-memory store giữ một phần, không group nào đủ.

**Khắc phục:** route cùng correlation key về một instance hoặc dùng shared store/locking.

### Sai lầm 13 — Bỏ quên late arrival sau group completion

**Triệu chứng:** part cũ tạo group mới, lặp output hoặc chờ mãi.

**Khắc phục:** completed-group metadata retention và late-arrival policy.

### Sai lầm 14 — Tin tưởng sequence headers do client tự khai

**Triệu chứng:** một client gửi correlationId của tenant khác hoặc sequenceSize rất lớn, gây trộn dữ liệu/DoS.

**Khắc phục:** xác thực/ủy quyền, giới hạn size, namespace group keys và validate dữ liệu tại ingress.

## 22. Bài tập thực hành

**Bài 1 — Nhận biết metadata.** Với một batch bốn part, viết bảng `correlationId`, `sequenceNumber`, `sequenceSize`, giải thích vì sao sequence number bắt đầu từ 1.

**Bài 2 — Complete release.** Dựng `CompleteResequencerConfig`. Gửi thứ tự 3,1,4,2; kiểm tra chưa có output đến khi đủ và sau đó nhận 1,2,3,4.

**Bài 3 — Partial release.** Dựng `PartialResequencerConfig`. Gửi 2,1,4,3 và assert output được phát theo hai đoạn 1,2 và 3,4.

**Bài 4 — Hai group xen kẽ.** Gửi A#2, B#1, A#1, B#2. Assert mỗi group có thứ tự đúng và không trộn payload.

**Bài 5 — Unknown sequenceSize.** Tạo một Splitter dựa trên Iterator không biết kích thước, quan sát `sequenceSize=0`. Thiết kế end signal hoặc release strategy thay vì chờ default complete release.

**Bài 6 — Duplicate message.** Gửi hai message cùng sequenceNumber=2 nhưng có eventId khác nhau. Chọn dedup/reject/resolve policy rồi kiểm thử không release sai.

**Bài 7 — Transformer làm mất header.** Tạo Transformer trả Message mới nhưng không copy sequence headers, quan sát lỗi flow. Sửa bằng header mapping phù hợp và kiểm tra readback.

**Bài 8 — Filter bỏ part.** Split 1..4, Filter loại phần 2, đưa phần còn lại qua Resequencer. Quan sát gap và thiết kế skipped marker/timeout.

**Bài 9 — Splitter → Executor → Resequencer.** Thêm chậm ngẫu nhiên vào handler các part để tạo arrival disorder. Assert thứ tự output luôn theo sequence number, không bắt buộc thứ tự business commit của async consumer sau đó.

**Bài 10 — Resequencer → Aggregator.** Sau khi sắp thứ tự, thêm Aggregator để tạo một collection. So sánh N→N với N→1 và các metadata output.

**Bài 11 — Late arrival.** Hoàn tất group rồi gửi lại một part; ghi outcome theo completed-group retention và error/discard policy.

**Bài 12 — Test resource limits.** Tạo nhiều group thiếu part để kiểm tra timeout/expiry, số nhóm mở, memory và metric.

### Câu hỏi tự kiểm tra

1. `sequenceNumber` và `sequenceSize` khác nhau như thế nào?
2. Vì sao `sequenceNumber` bắt đầu từ 1 trong ví dụ Splitter chuẩn?
3. `correlationId` có nhiệm vụ gì mà sequenceNumber không thay được?
4. `sequenceSize=4` có chứng minh đã nhận đủ bốn part không?
5. Resequencer có biến N message thành một collection không?
6. Complete-sequence release và partial-sequence release khác gì?
7. Khi part 4 tới trước part 3, partial release có được phát 4 không?
8. Tại sao `sequenceSize=0` cần chính sách completion riêng?
9. Vì sao hai message cùng sequenceNumber có thể gây lỗi?
10. Nếu Filter bỏ part, Resequencer gặp vấn đề gì?
11. `replyChannel` hoặc `traceId` có thay correlationId được không?
12. Nếu output 1,2,3 đúng thứ tự, liệu DB downstream đã commit cùng thứ tự chưa?
13. Lỗi nào nên retry, lỗi nào là metadata không hợp lệ không nên retry vô hạn?
14. Khi restart JVM, in-memory MessageGroupStore có đảm bảo giữ gap state không?
15. Vì sao cần limit sequenceSize và kiểm tra tenant khi nhận message từ client?
16. Cần test gì để chứng minh hệ thống không trộn hai batch khác nhau?
17. `sendPartialResultOnExpiry` khác `releasePartialSequences(true)` thế nào?
18. Khi nào nên bỏ Resequencer và dùng keyed stream processing?

## 23. Checklist triển khai

- [ ] Có định nghĩa rõ sequence 1-based và trường hợp unknown sequence size.
- [ ] Mỗi message có correlation key phù hợp, không trộn tenant/nhóm.
- [ ] Known sequence size là tổng dự kiến, thống nhất trong toàn group.
- [ ] Không dùng raw group count thay xác nhận tập sequence đầy đủ.
- [ ] Có validation cho thiếu/sai kiểu/out-of-range/duplicate headers.
- [ ] Đã chọn complete hoặc partial release có chủ đích.
- [ ] Có timeout, expiry và incomplete-group policy.
- [ ] Đã phân biệt releasePartialSequences với sendPartialResultOnExpiry.
- [ ] MessageGroupStore phù hợp yêu cầu memory/durability.
- [ ] Có xử lý concurrency, shared store/locking khi nhiều worker hoặc instances.
- [ ] Splitter/Transformer/Router/Filter giữ metadata cần thiết theo contract.
- [ ] Không dùng sequenceNumber như evidence của business commit.
- [ ] Downstream có idempotency với các event có thể replay/redeliver.
- [ ] Có kiểm thử thứ tự đến 3,1,4,2 và 2,1,4,3.
- [ ] Có test hai nhóm xen kẽ, duplicate, missing part, late arrival.
- [ ] Có metric group age/gaps/expired/received/emitted.
- [ ] Có giới hạn input size/quota và bảo mật header từ nguồn ngoài.
- [ ] Không chạy một chuỗi vô hạn qua resequencer bộ nhớ mà không có chiến lược phân đoạn/expiry.

## 24. Tổng kết

Trong Spring Integration, **`sequenceNumber` chỉ vị trí logic của message**, **`sequenceSize` chỉ tổng số phần dự kiến**, còn **`correlationId` xác định chuỗi liên quan**. Với các phần do Splitter tạo từ collection có kích thước đã biết, `sequenceNumber` thường là **1..N**, `sequenceSize=N` và correlation ID được chia sẻ trong batch. Resequencer giữ các message cùng nhóm, phát chúng **theo thứ tự số sequence** thay vì thứ tự đến, nhưng **không gộp chúng** như Aggregator.

Cấu hình mặc định thường chờ đủ chuỗi; `releasePartialSequences(true)` cho phép phát sớm các đoạn liên tục đã hợp lệ. Trường hợp `sequenceSize=0` do Splitter không biết độ dài, part bị thiếu, duplicate hoặc group hết hạn cần một chính sách bổ sung; các metadata này không thể tự đảm bảo completion hoặc exactly-once.

Để áp dụng trong **SPRING_INTEGRATION_PATTERN**, hãy dùng Splitter/Java DSL để tạo và bảo toàn sequence metadata, Resequencer để sắp thứ tự, Aggregator chỉ khi thật sự cần N→1, và kết hợp Filter, Router, Gateway, retry, error channel cùng tracing/correlation để vận hành an toàn. Quan trọng nhất là **kiểm thử thứ tự phát thực tế**, error/expiry behavior và idempotency thay vì chỉ tin vào các con số trong header.

### Tài liệu tham khảo

- Spring Integration Reference — Resequencer: https://docs.spring.io/spring-integration/reference/resequencer.html
- Spring Integration Reference — Splitter: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference — Aggregators and Resequencers (Java DSL): https://docs.spring.io/spring-integration/reference/dsl/java-aggregators.html
- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference — Message Store: https://docs.spring.io/spring-integration/reference/message-store.html
- Spring Integration API — ResequencerSpec: https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/ResequencerSpec.html
- Spring Integration API — SequenceSizeReleaseStrategy: https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/SequenceSizeReleaseStrategy.html
- Spring Integration API — IntegrationMessageHeaderAccessor: https://docs.spring.io/spring-integration/api/org/springframework/integration/IntegrationMessageHeaderAccessor.html
- JUnit 5 User Guide — Testing with JUnit Jupiter: https://junit.org/junit5/docs/current/user-guide/

