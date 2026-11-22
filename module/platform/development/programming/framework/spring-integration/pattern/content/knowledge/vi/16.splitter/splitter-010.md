# Không để một phần tử làm mất toàn bộ batch ngoài ý muốn

## 1. Vì sao một phần tử lỗi có thể ảnh hưởng cả batch?

Trong chương **Splitter** thuộc module **SPRING_INTEGRATION_PATTERN**, chúng ta học triển khai các Enterprise Integration Patterns với **Spring Integration** để xây dựng luồng message ít phụ thuộc, dễ mở rộng, có kiểm thử và quan sát được. Một Splitter nhận một message lớn rồi tạo ra các message con. Các message con có thể được xử lý độc lập qua Transformer, Filter, Router, Service Activator và sau đó được Aggregator ghép thành kết quả chung.

Giả sử hệ thống nhập **một batch gồm 5 dòng đơn hàng**:

| Dòng | Mã hàng | Số lượng nhập | Kết quả dự kiến |
| --- | --- | --- | --- |
| 1 | SKU-A | 3 | Hợp lệ |
| 2 | SKU-B | 2 | Hợp lệ |
| 3 | SKU-C | abc | Sai định dạng số |
| 4 | SKU-D | 5 | Hợp lệ |
| 5 | SKU-E | 1 | Hợp lệ |

Nếu chính sách nghiệp vụ là **partial success**, dòng 3 cần được đánh dấu lỗi để người dùng sửa, còn bốn dòng hợp lệ vẫn phải được xử lý. Nhưng một thiết kế thiếu kiểm soát có thể khiến:

- Transformer ở dòng 3 ném exception và **luồng đồng bộ dừng trước khi dispatch dòng 4, 5**.
- Dòng 3 bị Filter loại, khiến **Aggregator đợi đủ 5 kết quả nhưng chỉ nhận 4**.
- Một nhánh bất đồng bộ thất bại, nhưng lỗi chỉ xuất hiện trên **errorChannel**, không có kết quả tương ứng đi vào Aggregator.
- Retry cả batch sau partial success, khiến những dòng đã ghi database ở lần đầu bị ghi trùng.
- Batch được đánh dấu **SUCCESS** dù một số dòng chưa từng hoàn tất.

~~~mermaid
flowchart LR
    B["Batch 5 dòng"] --> S["Splitter"]
    S --> R1["Line 1 OK"]
    S --> R2["Line 2 OK"]
    S --> R3["Line 3 lỗi"]
    S --> R4["Line 4 OK"]
    S --> R5["Line 5 OK"]
    R1 --> A["Aggregator"]
    R2 --> A
    R3 -->|"Kết quả FAILED rõ ràng"| A
    R4 --> A
    R5 --> A
    A --> O["BatchReport: 4 OK, 1 FAILED"]
~~~

**Mục tiêu bài học**

1. Phân biệt **lỗi trước Splitter**, **lỗi trong phép split**, **lỗi của một message con** và **lỗi lúc aggregate**.
2. Hiểu correlation, sequenceNumber và sequenceSize, đặc biệt khi một item không sinh reply.
3. Thiết kế kết quả có kiểu cho từng phần tử: SUCCESS, REJECTED hoặc trạng thái phục hồi phù hợp.
4. Chọn đúng chính sách **fail-fast**, **partial success** hoặc **all-or-nothing** thay vì để hành vi mặc định quyết định thay nghiệp vụ.
5. Cấu hình một flow Splitter–Transformer–Aggregator có thể giữ lỗi dữ liệu ở phạm vi phần tử.
6. Tổ chức retry, dead-letter/quarantine, idempotency, transaction và quan sát cho batch.
7. Kiểm thử phần tử lỗi ở đầu, giữa, cuối; lỗi đồng bộ, bất đồng bộ; duplicate và timeout.

## 2. Splitter có và không có trách nhiệm gì?

**Splitter** là pattern tách một message thành nhiều phần:

~~~text
Message<Batch>
      |
      v
    Splitter
      |
      +--> Message<Item 1>
      +--> Message<Item 2>
      +--> Message<Item 3>
      +--> ...
~~~

Spring Integration hỗ trợ Splitter từ:

- Collection hoặc array.
- Iterable hoặc Iterator.
- Stream và một số nguồn reactive, tùy phiên bản.
- Một POJO method trả về tập phần tử.
- Một implementation của AbstractMessageSplitter khi cần điều khiển nâng cao.

Splitter **không tự bảo đảm** từng phần tử sẽ được xử lý thành công, mỗi phần tử được lưu bền hay một lỗi nghiệp vụ không ảnh hưởng tới các phần tử khác. Đó là trách nhiệm của **kiến trúc pipeline**, error handling và hệ thống lưu trạng thái.

### 2.1. Bốn ranh giới lỗi cần phân biệt

| Ranh giới | Ví dụ | Phạm vi ảnh hưởng có thể có |
| --- | --- | --- |
| **Trước split** | BatchId rỗng, file không parse được cấu trúc chính | Cả batch bị từ chối trước khi chia |
| **Trong split** | Hàm tách ném exception khi đọc nguồn | Có thể chưa phát đủ các phần tử |
| **Sau split, tại item handler** | Dòng 3 chứa quantity=abc | Tùy thiết kế: chỉ dòng 3 lỗi hoặc fan-out bị gián đoạn |
| **Khi aggregate/persist** | MessageStore lỗi, không đủ sequence, DB unavailable | Batch summary có thể không được tạo |

Nếu một lỗi thuộc **hợp đồng chung của cả batch** (file không có batchId, chữ ký sai, không đủ quyền import), từ chối **toàn batch trước split** là một quyết định chính đáng. Bài này nói đến việc **không vô tình làm mất cả batch** vì một lỗi **cục bộ của một dòng**, chứ không yêu cầu mọi lỗi luôn phải bị nuốt đi.

### 2.2. Chính sách không nên được đoán từ exception

| Chính sách | Ý nghĩa nghiệp vụ | Khi item lỗi |
| --- | --- | --- |
| **Fail-fast** | Chỉ cần một phần tử sai là không được tiếp tục | Dừng có chủ đích, báo batch bị từ chối |
| **All-or-nothing** | Hoặc toàn bộ thay đổi commit, hoặc không thay đổi gì | Rollback bằng transaction thật sự nếu có thể |
| **Partial success** | Các item hợp lệ vẫn được xử lý; item lỗi được báo riêng | Sinh kết quả FAILED cho item, các item khác đi tiếp |
| **Best effort** | Cố thực hiện nhiều nhất có thể, thiếu được chấp nhận | Phải có trạng thái và SLA rõ; không âm thầm mất item |
| **Eventual completion** | Item lỗi tạm thời được retry độc lập, batch hoàn tất sau | Lưu trạng thái PENDING/RETRYING, không báo SUCCESS quá sớm |

Chính sách là **quyết định nghiệp vụ**, không phải thuộc tính mặc định của Splitter. Cùng một lỗi quantity=abc, ứng dụng nhập dữ liệu hàng loạt có thể cho partial success, nhưng ứng dụng chuyển khoản theo batch có thể buộc toàn bộ batch bị từ chối trước khi thực hiện bất kỳ giao dịch nào.

## 3. Correlation và sequence: vì sao Aggregator có thể đợi mãi?

Khi Splitter tạo các message con, Spring Integration mặc định thêm những metadata sequencing phục vụ luồng splitter–aggregator:

| Header | Vai trò |
| --- | --- |
| **correlationId** | Xác định nhóm các message con thuộc cùng lần split |
| **sequenceNumber** | Vị trí của message con trong chuỗi |
| **sequenceSize** | Số phần tử mà nhóm kỳ vọng |

Ví dụ sau khi split một danh sách **5 phần tử**:

~~~text
line 1: correlationId=group-X, sequenceNumber=1, sequenceSize=5
line 2: correlationId=group-X, sequenceNumber=2, sequenceSize=5
line 3: correlationId=group-X, sequenceNumber=3, sequenceSize=5
line 4: correlationId=group-X, sequenceNumber=4, sequenceSize=5
line 5: correlationId=group-X, sequenceNumber=5, sequenceSize=5
~~~

**Aggregator mặc định** có thể dùng correlationId để lập nhóm và sequenceSize để xác định khi nào nhóm đã đủ; cụ thể, **SequenceSizeReleaseStrategy** chờ đủ chuỗi theo metadata. Nếu chỉ **4 message** tới Aggregator vì dòng 3 bị drop, nhóm 5 phần tử **không tự trở thành một batch 4 phần tử hoàn tất**.

~~~mermaid
flowchart TD
    S["Splitter: sequenceSize = 5"] --> A["Message 1"]
    S --> B["Message 2"]
    S --> C["Message 3"]
    S --> D["Message 4"]
    S --> E["Message 5"]
    A --> G["Aggregator"]
    B --> G
    C --> F["Filter discard / exception"]
    D --> G
    E --> G
    F -.->|"Không có reply"| X["Thiếu item #3"]
    G --> W["Chỉ có 4/5: chờ timeout hoặc policy khác"]
~~~

### 3.1. Không sửa sequenceSize thành 4 để che lỗi

Tự sửa sequenceSize của bốn message còn lại thành 4 chỉ để Aggregator release có thể:

- Làm mất bằng chứng dòng 3 đã tồn tại.
- Khiến batch được hiểu nhầm là thành công đầy đủ.
- Tạo xung đột nếu item 3 được retry hoặc redeliver muộn.
- Làm sai correlation của các luồng Splitter lồng nhau.

Nếu yêu cầu là partial success, nên truyền **kết quả thất bại có kiểu** của item 3 vào nhóm để nhóm vẫn có đủ **5 outcomes**, trong đó một outcome là FAILED.

### 3.2. Sequence size bằng 0 không có nghĩa batch rỗng

Tài liệu Spring Integration nêu rằng khi Splitter nhận **Iterator/Iterable** mà không biết số phần tử từ trước, header **sequenceSize** có thể là **0**, vì không biết tổng độ dài. Khi đó không thể dựa vào default SequenceSizeReleaseStrategy để phát hiện nhóm đầy đủ. Cần một **release policy** khác, marker cuối, timeout hoặc materialize collection có giới hạn trước khi split.

Đối với batch có số item nhỏ và giới hạn rõ ràng, dùng **List đã validate** là lựa chọn đơn giản để tạo sequenceSize biết trước. Với stream cực lớn, không materialize vô hạn vào bộ nhớ chỉ để lấy số lượng; hãy thiết kế giao thức kết thúc batch và aggregation state phù hợp.

### 3.3. Correlation ID kỹ thuật khác batchId nghiệp vụ

Một batchId như **batch-2026-11-21-01** có thể được dùng nhiều lần khi retry/replay. Còn correlationId do Splitter gắn thường thuộc một **lần chia message cụ thể**. Nếu tạo lại request Message khi replay, correlationId kỹ thuật có thể khác.

Vì vậy:

- **batchId**: định danh logic ổn định để tra cứu trạng thái và chống lặp nghiệp vụ.
- **lineId/lineNo**: định danh phần tử ổn định qua retry.
- **correlationId**: nối các message con trong một lần xử lý nhóm.
- **sequenceNumber/sequenceSize**: phục vụ luồng sequencing, không phải idempotency key.

Nếu nhiều batch có cùng lineNo, tuyệt đối không deduplicate toàn cục theo lineNo đơn lẻ.

## 4. Sai lầm thường gặp khiến cả batch bị gián đoạn

### 4.1. Để exception dữ liệu thoát ra khỏi mỗi item Transformer

~~~java
// Phản ví dụ với chính sách partial success:
.split(ImportBatch.class, ImportBatch::lines)
.transform(ImportLine.class, line ->
        new BigDecimal(line.quantityText())) // "abc" ném lỗi.
.channel("validatedLinesChannel")
~~~

Nếu dispatch qua **DirectChannel đồng bộ**, exception của item có thể truyền ngược qua call stack của Splitter. Khi Splitter chưa gửi các phần tử phía sau, những phần tử đó **có thể không được dispatch** trong attempt hiện tại.

Đây không phải bằng chứng rằng Splitter luôn rollback mọi item: những item trước đó có thể đã được xử lý và commit. Kết quả **nửa thành công, nửa dừng** thường nguy hiểm hơn cả một lỗi rõ ràng.

### 4.2. Filter loại item rồi chờ Aggregator nhận đủ

~~~java
// Phản ví dụ nếu Aggregator vẫn cần 5 outcomes:
.split(ImportBatch.class, ImportBatch::lines)
.filter(ImportLine.class, line -> isValid(line))
.aggregate()
~~~

Filter discard có thể hợp lệ trong nghiệp vụ nơi item bị loại **không tính là một kết quả cần báo**. Nhưng nếu batch report phải có kết quả cho mọi dòng đầu vào, Filter loại im lặng sẽ làm mất thông tin lỗi và có thể để nhóm chờ.

### 4.3. Bắt Exception rồi trả null trong Transformer

~~~java
// Không biến null thành "skip item" trong Transformer.
.transform(ImportLine.class, line -> {
    try {
        return normalize(line);
    } catch (Exception ex) {
        return null;
    }
})
~~~

**Transformer của Spring Integration không cho phép trả null như một kết quả chuyển đổi thành công.** Null là lỗi transformation. Muốn tiếp tục sau lỗi dữ liệu, trả về **một object outcome không null**; muốn bỏ message theo policy, dùng Filter và thiết kế nhánh discard/aggregation phù hợp.

### 4.4. Gửi lỗi sang errorChannel nhưng không trả outcome

ErrorMessage giúp quan sát lỗi nhưng không phải là một LineOutcome tự động đi vào Aggregator. Nếu item 3 lỗi ở worker async và chỉ gửi ErrorMessage tới errorChannel, Aggregator vẫn có thể chỉ nhận 4/5 reply.

Muốn Aggregator hoàn tất, một thành phần recovery cần **tạo một failure outcome hợp lệ** gắn đúng batchId/lineNo và đưa nó tới luồng kết quả (theo hợp đồng), hoặc cả batch cần được đánh dấu failed/expired có chủ đích. Không được âm thầm coi message lỗi đã biến mất.

### 4.5. Retry toàn batch sau khi một item đã commit

~~~text
Attempt 1:
  line 1 -> COMMITTED
  line 2 -> COMMITTED
  line 3 -> FAIL

Retry toàn batch:
  line 1 -> xử lý lần nữa?
  line 2 -> xử lý lần nữa?
  line 3 -> retry?
~~~

Nếu mỗi item có side effect, bản retry phải dùng **khóa idempotency ổn định** hoặc một cơ chế transaction có cùng phạm vi với thay đổi nghiệp vụ. Một lời gọi send() thành công không chứng minh side effect đã commit.

## 5. Thiết kế kết quả riêng cho từng phần tử

Với chính sách partial success, một nguyên tắc dễ kiểm thử là:

> **Mỗi input item đã được chấp nhận để chia phải tạo đúng một terminal outcome trong lần xử lý batch, kể cả khi dữ liệu của item không hợp lệ.**

Terminal outcome có thể là:

- **SUCCESS**: item đã qua bước xử lý theo hợp đồng, hoặc side effect được xác nhận hoàn tất nếu đó là mục tiêu.
- **REJECTED**: item sai dữ liệu hoặc vi phạm chính sách không retry tự động.
- **FAILED_FINAL**: một lỗi hệ thống đã được kết luận không thể tiếp tục tự động.

**PENDING/RETRYING/UNKNOWN** là các trạng thái **chưa terminal** nếu hệ thống còn phải retry hoặc đối soát. Không gom chúng thành SUCCESS; có thể chọn giữ batch ở trạng thái IN_PROGRESS hoặc phát một báo cáo tạm có đánh dấu incomplete.

Một failure outcome là dữ liệu nghiệp vụ, **không phải Throwable được serialise tùy ý**. Nó chỉ chứa mã lỗi an toàn, lineNo, batchId và metadata cần thiết để điều tra.

~~~mermaid
flowchart TD
    I["ImportLine"] --> P{"Xử lý một dòng"}
    P -->|"Hợp lệ"| S["LineOutcome SUCCESS"]
    P -->|"Sai dữ liệu"| F["LineOutcome REJECTED"]
    P -->|"Lỗi transient"| R["Retry riêng item<br/>hoặc PENDING trong store bền"]
    R -->|"Thành công"| S
    R -->|"Hết retry, terminal"| X["LineOutcome FAILED_FINAL"]
    S --> A["Aggregator"]
    F --> A
    X --> A
    A --> B["BatchReport minh bạch<br/>successCount + failureCount"]
~~~

### 5.1. Vì sao không bắt mọi Exception?

Một đoạn code kiểu **catch (Exception ex) → REJECTED** có thể biến lỗi DB/network thành lỗi dữ liệu vĩnh viễn. Người dùng không thể sửa input để chữa một outage, trong khi một bản báo cáo REJECTED sẽ làm hệ thống ngừng retry.

Nên chỉ chuyển **expected domain/validation errors** thành outcome lỗi. Các lỗi bất ngờ cần đường xử lý riêng: retry có điều kiện, ErrorMessage, quarantine hoặc fail batch có báo trạng thái, tùy SLA. Với lỗi không thể biết side effect đã xảy ra hay chưa, cần một trạng thái **UNKNOWN** và đối soát; đừng trả SUCCESS/FAILED một cách đoán mò.

## 6. Ví dụ Java 17: mô hình batch và outcome

Ví dụ tự chứa dưới đây mô phỏng một lần nhập dữ liệu với **batchId**, các dòng có **lineNo** ổn định và dữ liệu quantity dưới dạng chuỗi. Chúng ta bắt đầu từ một Transformer **thuần**, không ghi database, để thấy rõ cơ chế tiếp tục xử lý khi một dòng sai.

### 6.1. Input model và validation mức batch

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

record ImportLine(
        String batchId,
        int lineNo,
        String sku,
        String quantityText) {}

record ImportBatch(String batchId, List<ImportLine> lines) {
    ImportBatch {
        if (batchId == null || !batchId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("INVALID_BATCH_ID");
        }
        Objects.requireNonNull(lines, "lines");
        if (lines.isEmpty() || lines.size() > 1000) {
            throw new IllegalArgumentException("INVALID_BATCH_SIZE");
        }

        lines = List.copyOf(lines);
        Set<Integer> seenLineNumbers = new HashSet<>();
        for (ImportLine line : lines) {
            if (!batchId.equals(line.batchId())
                    || line.lineNo() <= 0
                    || !seenLineNumbers.add(line.lineNo())) {
                throw new IllegalArgumentException(
                        "INVALID_LINE_IDENTITY");
            }
        }
    }
}
~~~

**Vì sao kiểm tra riêng?** batchId không hợp lệ, danh sách trống, lineNo trùng hoặc một dòng thuộc batch khác là lỗi **cấu trúc nhóm**. Nếu cấu trúc nhóm đã sai, không nên sinh ra các message con có identity mơ hồ. Ngược lại, quantityText="abc" chỉ là lỗi **dữ liệu một dòng**, nên vẫn được đưa qua Splitter để tạo một outcome REJECTED.

Giới hạn 1.000 dòng là **quy tắc ví dụ** của ứng dụng, không phải giới hạn mặc định của Spring Integration. Với batch lớn hơn, cần chunk/streaming và cơ chế completion khác phù hợp.

### 6.2. Kết quả của từng dòng

~~~java
import java.util.List;

record LineOutcome(
        String batchId,
        int lineNo,
        String sku,
        String status,
        Integer quantity,
        String errorCode) {

    static LineOutcome success(ImportLine line, int quantity) {
        return new LineOutcome(
                line.batchId(), line.lineNo(), line.sku(),
                "SUCCESS", quantity, null);
    }

    static LineOutcome rejected(ImportLine line, String code) {
        return new LineOutcome(
                line.batchId(), line.lineNo(), line.sku(),
                "REJECTED", null, code);
    }
}

record BatchReport(
        String batchId,
        int total,
        long successCount,
        long failureCount,
        List<LineOutcome> outcomes) {}
~~~

Trong thực tế có thể dùng enum **LineStatus** và enum **ErrorCode** thay cho chuỗi, đồng thời thêm trạng thái xử lý bền. Ví dụ record này dùng String để tập trung vào cơ chế Splitter–Aggregator.

### 6.3. Transformer một dòng luôn trả outcome cho lỗi dữ liệu

~~~java
final class ImportLineProcessor {

    LineOutcome process(ImportLine line) {
        String sku = line.sku();
        if (sku == null || !sku.matches("[A-Za-z0-9_-]{1,40}")) {
            return LineOutcome.rejected(line, "INVALID_SKU");
        }

        String raw = line.quantityText();
        if (raw == null || raw.isBlank()) {
            return LineOutcome.rejected(line, "MISSING_QUANTITY");
        }

        int quantity;
        try {
            quantity = Integer.parseInt(raw.trim());
        } catch (NumberFormatException ex) {
            return LineOutcome.rejected(
                    line, "INVALID_QUANTITY_FORMAT");
        }

        if (quantity < 1 || quantity > 10000) {
            return LineOutcome.rejected(
                    line, "INVALID_QUANTITY_RANGE");
        }

        return LineOutcome.success(line, quantity);
    }
}
~~~

**Đặc điểm của processor:**

1. Cùng một input tạo cùng kết quả, không có side effect.
2. Lỗi dữ liệu **đã dự đoán** chuyển thành một outcome REJECTED **không null**.
3. Dòng hợp lệ tạo outcome SUCCESS.
4. Không tự nuốt các lỗi RuntimeException không mong đợi.
5. Có batchId và lineNo để báo cáo không phụ thuộc thứ tự message đến.

Vì đây là **bước validate/normalize thuần**, SUCCESS ở đây chỉ có nghĩa **được xác nhận hợp lệ**. Nếu sau đó ứng dụng cần ghi kho hoặc gửi hàng, phải coi việc lưu/dispatch là **một bước nghiệp vụ khác**, không được báo đã commit chỉ từ kết quả validate.

## 7. Tổng hợp các outcomes thành BatchReport

Để tránh báo cáo khó đọc khi xử lý bất đồng bộ, chúng ta sắp xếp kết quả theo **lineNo**, không dựa vào thứ tự message đến Aggregator.

~~~java
import java.util.Comparator;
import java.util.List;

import org.springframework.integration.store.MessageGroup;

final class BatchReports {
    private BatchReports() {}

    static BatchReport summarize(MessageGroup group) {
        List<LineOutcome> outcomes = group.getMessages().stream()
                .map(message -> (LineOutcome) message.getPayload())
                .sorted(Comparator.comparingInt(LineOutcome::lineNo))
                .toList();

        if (outcomes.isEmpty()) {
            throw new IllegalStateException("EMPTY_OUTCOME_GROUP");
        }

        String batchId = outcomes.get(0).batchId();
        for (LineOutcome outcome : outcomes) {
            if (!batchId.equals(outcome.batchId())) {
                throw new IllegalStateException(
                        "MIXED_BATCH_IDENTITIES");
            }
        }

        long successful = outcomes.stream()
                .filter(outcome -> "SUCCESS".equals(outcome.status()))
                .count();

        return new BatchReport(
                batchId,
                outcomes.size(),
                successful,
                outcomes.size() - successful,
                List.copyOf(outcomes));
    }
}
~~~

**Quan trọng:** việc nhóm các message bằng correlationId là trách nhiệm của Aggregator. Phương thức trên **không tự tạo group**, nó chỉ tạo kết quả khi framework đã quyết định group được release. Với cấu hình mặc định và List đã có kích thước, khi mọi child đều tạo outcome thì Aggregator có đủ điều kiện nhận toàn bộ chuỗi. Nếu mất một outcome do lỗi hạ tầng, nhóm vẫn cần timeout/recovery policy.

Trong ứng dụng có replay trùng một line, còn phải kiểm tra identity **batchId + lineNo**, duplicate attempt và trạng thái của group. Dùng List.size() làm total chỉ đúng khi group chứa đúng **một outcome cuối cùng cho từng item kỳ vọng**.

## 8. Ghép các bước thành Spring Integration Java DSL

Spring Integration hỗ trợ **split(Class, function)** để biến collection trả về từ một POJO method thành từng child message. Khi Splitter có tập phần tử biết kích thước, framework gắn sequencing headers mặc định. Transformer tạo một LineOutcome cho mỗi item; Aggregator dùng correlation/sequence để gom thành BatchReport.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class PartialImportFlowConfig {

    @Bean
    ImportLineProcessor importLineProcessor() {
        return new ImportLineProcessor();
    }

    @Bean
    MessageChannel importBatchInput() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel importBatchReports() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow partialImportFlow(ImportLineProcessor processor) {
        return IntegrationFlow.from("importBatchInput")
                .split(ImportBatch.class, ImportBatch::lines)
                .transform(ImportLine.class, processor::process)
                .aggregate(aggregator -> aggregator
                        .outputProcessor(BatchReports::summarize))
                .channel("importBatchReports")
                .get();
    }
}
~~~

### 8.1. Đường đi khi item 3 có quantityText="abc"

~~~text
ImportBatch (5 lines)
    -> Splitter
        -> ImportLine #1 -> LineOutcome SUCCESS
        -> ImportLine #2 -> LineOutcome SUCCESS
        -> ImportLine #3 -> LineOutcome REJECTED
        -> ImportLine #4 -> LineOutcome SUCCESS
        -> ImportLine #5 -> LineOutcome SUCCESS
    -> Aggregator (correlation của cùng lần split; sequenceSize=5)
    -> BatchReport(total=5, successCount=4, failureCount=1)
~~~

**Vì sao nó tiếp tục được?** item 3 không ném lỗi parse ra ngoài endpoint, mà tạo **một message kết quả** như những item khác. Vì thế các item còn lại vẫn được Splitter dispatch trong flow đồng bộ minh họa, và Aggregator có đủ 5 reply.

**Điều ví dụ không bảo đảm:** kết quả được lưu qua restart, các side effect đã commit, hoặc khi có exception unexpected trong chính processor. Những yêu cầu đó cần cấu hình thông điệp bền, error flow, retry và trạng thái xử lý như các phần sau.

### 8.2. Không nhầm output aggregation với một transaction toàn batch

Việc nhận BatchReport chỉ chứng minh những kết quả **đã đến Aggregator** và được tổng hợp theo rule. Nó không đồng nghĩa bốn dòng SUCCESS đã cùng commit một database transaction. Nếu business yêu cầu **all-or-nothing**, phải thiết kế transaction theo đúng phạm vi của các thay đổi, thường là validate hết trước rồi mới commit theo batch.

## 9. Ba chính sách vận hành: chọn trước khi viết flow

### 9.1. Partial success

Áp dụng khi **mỗi item độc lập** và nghiệp vụ chấp nhận xử lý phần hợp lệ:

1. Kiểm tra batch identity và giới hạn số item trước Splitter.
2. Mỗi item được validate độc lập.
3. Item sai trả outcome REJECTED với errorCode, không bị Filter bỏ mất.
4. Item hợp lệ được đưa sang một bước xử lý nghiệp vụ riêng nếu cần.
5. BatchReport chỉ được đánh dấu COMPLETED khi đã có một **terminal outcome cho mỗi item**.

Phù hợp với import catalog, cập nhật hàng loạt không phụ thuộc giữa các dòng hoặc xử lý một tập sự kiện độc lập.

### 9.2. All-or-nothing

Áp dụng khi **chỉ một lỗi là phải hủy toàn bộ yêu cầu**:

~~~mermaid
flowchart TD
    B["Batch input"] --> V["Validate toàn bộ item (không side effect)"]
    V -->|"Có item sai"| R["Reject toàn batch, báo lỗi rõ"]
    V -->|"Tất cả hợp lệ"| T["Bắt đầu transaction nghiệp vụ"]
    T --> S["Apply tất cả thay đổi trong cùng DB"]
    S --> C{"Commit thành công?"}
    C -->|"Có"| OK["Batch SUCCESS"]
    C -->|"Không"| X["Rollback / trạng thái lỗi"]
~~~

Nếu mọi thay đổi nằm trong **một database transaction**, có thể rollback tất cả khi có lỗi. Nhưng không được khẳng định transaction của database cũng rollback được email, thanh toán hay API bên ngoài. Với nhiều hệ thống, có thể cần **Saga/compensation** hoặc từ chối yêu cầu trước khi bắt đầu side effect.

### 9.3. Eventual completion với lỗi tạm thời

Áp dụng khi một item cần chờ dịch vụ ngoài phục hồi:

~~~text
Batch 5 items:
  line 1 = COMPLETED
  line 2 = COMPLETED
  line 3 = RETRYING
  line 4 = COMPLETED
  line 5 = COMPLETED

Batch state = IN_PROGRESS (4 terminal, 1 còn pending)
~~~

Nếu sau các lần thử có kiểm soát, line 3 được xác nhận không thể tiếp tục, trạng thái cuối có thể là FAILED_FINAL và batch report là PARTIAL_SUCCESS. Nếu line 3 thành công, batch có thể hoàn tất toàn bộ.

**Không dùng một result PENDING tạm thời để làm Aggregator báo đã hoàn tất batch** nếu hợp đồng yêu cầu kết quả cuối cùng. Có thể phát một báo cáo **snapshot** riêng được đánh dấu IN_PROGRESS, nhưng đó khác với một báo cáo terminal.

## 10. Khi item xử lý có side effect: idempotency từng dòng

Nếu mỗi dòng hợp lệ được ghi vào database hoặc gửi tới hệ thống khác, một bản replay có thể xử lý lại những dòng đã thành công. Khi đó logic per-item cần **idempotent**.

Định danh phổ biến:

~~~text
logicalItemKey = tenantId + ":" + batchId + ":" + lineNo + ":" + revision
~~~

- **tenantId** phải đến từ identity/context đã xác thực, không chỉ từ header do client tự đặt.
- **batchId** nhận diện một batch nghiệp vụ.
- **lineNo** nhận diện vị trí item ổn định trong batch.
- **revision** phân biệt bản sửa hợp lệ sau khi item bị từ chối với bản replay của cùng một yêu cầu. Nếu không hỗ trợ sửa cùng batch, có thể cố định revision=1 và tạo batchId mới cho lần nộp mới.

Không dùng MessageHeaders.ID hoặc sequenceNumber đơn lẻ làm khóa nghiệp vụ: ID message có thể đổi sau khi tạo lại, còn sequenceNumber chỉ có ý nghĩa trong một lần split.

### 10.1. Trạng thái item cần được lưu bền

| Trạng thái | Ý nghĩa | Khi nhận lại cùng khóa |
| --- | --- | --- |
| **PENDING** | Chưa có effect | Có thể claim để xử lý |
| **PROCESSING** | Một worker đang thực hiện | Kiểm tra lease/lock, tránh hai worker cùng chạy |
| **COMPLETED** | Effect được xác nhận commit | Không tạo side effect lần hai; trả lại outcome cũ |
| **REJECTED** | Lỗi dữ liệu terminal của revision này | Trả lại errorCode cũ, không retry vô hạn |
| **FAILED_RETRYABLE** | Lỗi hạ tầng tạm thời | Retry có backoff và ngân sách |
| **UNKNOWN** | Không rõ external effect đã xảy ra chưa | Đối soát theo operation key |
| **FAILED_FINAL** | Không còn retry tự động | Quarantine, cần can thiệp |

Một implementation có thể ghi LineOutcome cùng trạng thái trong bảng inbox hoặc processing ledger. Nếu worker crash, một process khác dùng lại khóa item để biết cần tiếp tục hay bỏ qua.

### 10.2. Ví dụ SQL với unique constraint

~~~sql
CREATE TABLE batch_line_execution (
    tenant_id VARCHAR(80) NOT NULL,
    batch_id VARCHAR(80) NOT NULL,
    line_no INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    status VARCHAR(24) NOT NULL,
    error_code VARCHAR(80),
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, batch_id, line_no, revision)
);

CREATE TABLE import_stock_adjustment (
    tenant_id VARCHAR(80) NOT NULL,
    batch_id VARCHAR(80) NOT NULL,
    line_no INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, batch_id, line_no, revision)
);
~~~

Giả sử cùng một database/transaction manager và có một method ghi nhận item sau validation:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class StockImportService {
    private final JdbcTemplate jdbc;

    StockImportService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void applyOnce(
            String trustedTenantId,
            LineOutcome result,
            int revision) {

        if (!"SUCCESS".equals(result.status())) {
            throw new IllegalArgumentException("Item chưa hợp lệ");
        }

        int acquired = jdbc.update("""
                INSERT INTO batch_line_execution
                    (tenant_id, batch_id, line_no, revision, status)
                VALUES (?, ?, ?, ?, 'PROCESSING')
                ON CONFLICT DO NOTHING
                """,
                trustedTenantId,
                result.batchId(), result.lineNo(), revision);

        if (acquired == 0) {
            String status = jdbc.queryForObject("""
                    SELECT status FROM batch_line_execution
                     WHERE tenant_id = ? AND batch_id = ?
                       AND line_no = ? AND revision = ?
                    """,
                    String.class,
                    trustedTenantId,
                    result.batchId(), result.lineNo(), revision);
            if ("COMPLETED".equals(status)) {
                return; // Idempotent: đã ghi effect trong lần trước.
            }
            throw new IllegalStateException(
                    "Item đã được claim nhưng chưa completed");
        }

        jdbc.update("""
                INSERT INTO import_stock_adjustment
                    (tenant_id, batch_id, line_no, revision, sku, quantity)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                trustedTenantId,
                result.batchId(), result.lineNo(), revision,
                result.sku(), result.quantity());

        jdbc.update("""
                UPDATE batch_line_execution
                   SET status = 'COMPLETED',
                       completed_at = CURRENT_TIMESTAMP
                 WHERE tenant_id = ? AND batch_id = ?
                   AND line_no = ? AND revision = ?
                """,
                trustedTenantId,
                result.batchId(), result.lineNo(), revision);
    }
}
~~~

Đoạn code này minh họa **ghi một adjustment record duy nhất**, chưa cập nhật số lượng stock thực tế và chưa xử lý mọi lỗi domain. Để thay đổi tồn kho, cần thêm thao tác có constraint phù hợp **trong cùng transaction**. Giá trị tenantId phải được xác minh, revision phải là phiên bản hợp lệ và input/quantity phải được kiểm tra trước khi gọi service.

Nếu mọi thao tác DB cùng transaction, lần đầu ghi ledger và adjustment rồi commit; lần retry nhận được COMPLETED sẽ không ghi adjustment mới. Nếu exception khiến transaction rollback trước commit, cả ledger và adjustment bị rollback, cho phép retry. Khi hai worker đụng cùng khóa, unique constraint và khóa transaction bảo vệ khỏi effect trùng.

**Giới hạn:** điều này không tạo exactly-once effect khi item gọi HTTP hoặc gửi email ở hệ thống ngoài. Cần idempotency key của provider, outbox và đối soát tương ứng.

### 10.3. Partial success không có nghĩa retry cả batch bằng mọi giá

Giả sử 4 dòng đã được ghi adjustment, dòng 3 bị REJECTED vì sai định dạng. Khi người dùng sửa dòng 3:

- Giữ identity batchId + lineNo nhưng **tăng revision** hoặc tạo operation ID mới theo hợp đồng.
- Chỉ nộp lại phần tử cần sửa; không phát sinh effect lặp cho bốn dòng đã COMPLETED.
- Nếu vẫn replay toàn batch, từng item processor phải kiểm tra idempotency để bỏ qua side effect đã hoàn tất.
- Batch report cần phân biệt **bản báo cáo revision 1** và **trạng thái hiện hành sau sửa**, không ghi đè lịch sử mà không có audit.

## 11. Error channel và phạm vi exception

Một Splitter **không tự tạo fault isolation** chỉ vì đã tách message. Cách handler và channel được bố trí quyết định lỗi lan truyền.

### 11.1. DirectChannel đồng bộ

~~~text
Splitter -> DirectChannel -> item handler
                                  |
                                  +-- throws RuntimeException
~~~

Handler chạy trong call stack của sender. Một exception chưa được xử lý có thể chặn việc gửi các child tiếp theo, trong khi child trước đã được xử lý. Caller có thể nhận một exception của lần gửi batch, nhưng **không được suy ra mọi effect trước đó đều rollback**.

### 11.2. ExecutorChannel / QueueChannel / broker

~~~text
Splitter -> executor/queue -> item worker
                               |
                               +-- success -> LineOutcome -> Aggregator
                               |
                               +-- failure -> ErrorMessage/errorChannel
~~~

Lỗi ở worker async có thể được Spring Integration đưa đến **ErrorMessage** qua error channel được cấu hình; không nhất thiết quay về thread tạo batch. Tuy nhiên ErrorMessage **không tự biến thành LineOutcome**, và một message bị lỗi không tự được coi là thành viên của group Aggregator.

Nếu cần báo cáo cuối cho mọi item, hãy thiết kế **recovery adapter**:

1. Xác định batchId và lineNo đáng tin của failedMessage/originalMessage (có thể không tồn tại trong một số lỗi).
2. Phân loại lỗi: dữ liệu vĩnh viễn, transient hoặc UNKNOWN.
3. Retry riêng item hoặc lưu trạng thái.
4. Chỉ khi kết luận trạng thái terminal, tạo **một LineOutcome duy nhất** với metadata correlation/sequence đúng; không tự phát thêm outcome trùng nếu worker cũng đã thành công.
5. Đưa outcome tới Aggregator hoặc tới storage báo cáo theo hợp đồng.

### 11.3. Đừng xem ErrorMessage là DLQ bền

Một channel mang tên **batchItemErrors** chưa đảm bảo rằng failedMessage được lưu sau khi ứng dụng restart. Nếu các item phải được replay, cần store/broker bền, xác định ack/commit và chính sách retry/DLQ. Nếu error flow cũng ném exception, phải có giám sát riêng; không route lỗi về chính Splitter một cách vô hạn.

### 11.4. Phân loại lỗi để không che sự cố

| Loại lỗi | Có thể trả REJECTED ngay? | Quy tắc |
| --- | --- | --- |
| Số lượng không parse được | Có | Mã lỗi rõ, item khác tiếp tục |
| SKU thiếu | Có | Validation error, không retry mù |
| Item vi phạm quyền tenant | Có thể là reject hoặc security failure batch | Không xử lý các item vượt quyền |
| DB deadlock | Không | Retry transaction theo item |
| Database offline | Không | Giữ PENDING/RETRYING hoặc fail batch có thể phục hồi |
| HTTP timeout sau side effect | Không thể kết luận | UNKNOWN, đối soát/idempotency key |
| NullPointerException do bug | Không nên tự gọi REJECTED | Alert, sửa lỗi, có replay policy |
| Không có consumer của output channel | Không | Lỗi topology/dispatch |

**Catch đúng loại lỗi tại đúng ranh giới.** Không dùng một catch(Throwable) chung để biến lỗi hệ thống hoặc lỗi lập trình thành một status REJECTED có vẻ hợp lệ.

## 12. Aggregator timeout và partial results

Khi một message con không đi đến Aggregator, cần một chính sách **cho nhóm chưa đầy đủ**:

- **groupTimeout**: thời gian cho phép nhóm chờ thêm message.
- **sendPartialResultOnExpiry**: có cho phép phát những message đã tới khi nhóm hết thời gian hay không.
- **MessageGroupStore**: nơi lưu trạng thái nhóm; dùng persistent store nếu cần sống qua restart.
- **discard channel**: xử lý message đến muộn hoặc bị loại theo chính sách.
- **expire groups**: quản lý group lifecycle và tránh group treo tăng vô hạn.

Các cấu hình này phải được điều chỉnh theo **phiên bản Spring Integration** và hợp đồng nghiệp vụ; chúng không tự tạo failed outcome cho từng item thiếu.

### 12.1. Partial aggregation không phải batch success

~~~text
Expected line numbers: [1, 2, 3, 4, 5]
Arrived outcomes:      [1, 2,    4, 5]
Timeout:               30 seconds

Partial report:
  batchStatus = INCOMPLETE
  expected = 5
  received = 4
  missing = [3]
~~~

Nếu bật partial result khi timeout, phải **đánh dấu báo cáo INCOMPLETE** và công bố danh sách item thiếu dựa trên manifest/metadata đáng tin. Không dùng default BatchReports.summarize() từ ví dụ trước rồi tự nhận total=4 là hoàn tất, vì nó không biết manifest kỳ vọng là 5 khi một item mất hoàn toàn.

Để biết chính xác item nào thiếu, lưu **manifest gồm batchId + các lineNo**, hoặc lưu bộ expected item identities trong một processing store bền. Chỉ số sequenceSize cung cấp số lượng kỳ vọng, nhưng không thay thế một manifest hoàn chỉnh khi cần đối soát theo item identity.

### 12.2. Message đến muộn và group lifecycle

Một item có thể đến **sau khi group đã release hoặc expire**:

- Nếu group còn dấu tombstone/empty-group để nhận biết đã hoàn tất, late message có thể bị discard theo policy.
- Nếu group đã bị xóa hết, late message cùng correlation có thể tạo **một group mới**, gây báo cáo lặp.
- Nếu group tồn tại quá lâu, message store có thể tăng không giới hạn.

Phải xác định rõ late-arrival policy, retention, unique batch report key và điều kiện upsert/sửa báo cáo. Không coi việc bật expireGroupsUponCompletion là vô hại: nó ảnh hưởng xử lý message đến muộn và duplicate.

### 12.3. Không nhất thiết phải dùng Aggregator cho mọi batch

Với workflow có item cần chờ nhiều ngày, một **bảng trạng thái batch/item** và một job xác định completion dựa trên số terminal outcomes có thể đáng tin hơn giữ group messaging chờ rất lâu.

~~~mermaid
flowchart LR
    B["Batch manifest DB"] --> D["Phân phối item tasks"]
    D --> W["Workers riêng từng item"]
    W --> S["Item status DB"]
    S --> C{"Đủ terminal statuses?"}
    C -->|"Không"| P["Batch IN_PROGRESS"]
    C -->|"Có"| R["BatchReport COMPLETED / PARTIAL"]
~~~

Đây vẫn là pattern **Split xử lý độc lập rồi Aggregate kết quả**, nhưng phần aggregate cuối dùng **bộ trạng thái bền** thay vì chỉ một in-memory MessageGroup. Cách chọn phụ thuộc kích thước batch, thời gian chờ, SLA và khả năng replay.

## 13. Unit test: một dòng lỗi không ảnh hưởng các dòng khác

Trước khi test Spring context, kiểm thử ImportLineProcessor như một hàm thuần. Các test dưới đây dùng JUnit 5.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class ImportLineProcessorTest {
    private final ImportLineProcessor processor =
            new ImportLineProcessor();

    @Test
    void validLineProducesSuccessOutcome() {
        ImportLine line = new ImportLine(
                "batch-10", 1, "SKU-A", "3");

        LineOutcome result = processor.process(line);

        assertEquals("SUCCESS", result.status());
        assertEquals(3, result.quantity());
        assertNull(result.errorCode());
        assertEquals("batch-10", result.batchId());
        assertEquals(1, result.lineNo());
    }

    @Test
    void oneMalformedLineProducesRejectedOutcome() {
        ImportLine bad = new ImportLine(
                "batch-10", 3, "SKU-C", "abc");

        LineOutcome outcome = processor.process(bad);

        assertNotNull(outcome);
        assertEquals("REJECTED", outcome.status());
        assertEquals(
                "INVALID_QUANTITY_FORMAT",
                outcome.errorCode());
        assertEquals(3, outcome.lineNo());
    }

    @Test
    void malformedMiddleDoesNotChangeOtherResults() {
        LineOutcome first = processor.process(
                new ImportLine("batch-10", 1, "SKU-A", "3"));
        LineOutcome middle = processor.process(
                new ImportLine("batch-10", 2, "SKU-B", "invalid"));
        LineOutcome last = processor.process(
                new ImportLine("batch-10", 3, "SKU-C", "5"));

        assertEquals("SUCCESS", first.status());
        assertEquals("REJECTED", middle.status());
        assertEquals("SUCCESS", last.status());
    }

    @Test
    void rejectsMissingSkuAndOutOfRangeQuantity() {
        assertEquals("INVALID_SKU", processor.process(
                new ImportLine("batch-10", 1, "", "3"))
                .errorCode());
        assertEquals("INVALID_QUANTITY_RANGE", processor.process(
                new ImportLine("batch-10", 2, "SKU-B", "10001"))
                .errorCode());
    }
}
~~~

### 13.1. Kiểm tra cấu trúc batch trước Splitter

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class ImportBatchContractTest {

    @Test
    void duplicateLineNumbersAreRejectedBeforeSplit() {
        assertThrows(IllegalArgumentException.class,
                () -> new ImportBatch("batch-11", List.of(
                        new ImportLine("batch-11", 1, "SKU-A", "2"),
                        new ImportLine("batch-11", 1, "SKU-B", "3"))));
    }

    @Test
    void emptyBatchRequiresExplicitBusinessHandling() {
        assertThrows(IllegalArgumentException.class,
                () -> new ImportBatch("batch-12", List.of()));
    }

    @Test
    void invalidQuantityIsStillPermittedForItemLevelReporting() {
        ImportBatch batch = new ImportBatch("batch-13", List.of(
                new ImportLine("batch-13", 1, "SKU-A", "abc")));
        assertEquals(1, batch.lines().size());
    }
}
~~~

Test cuối rất quan trọng: **không validate quantity ở constructor mức batch** nếu mục tiêu là báo lỗi riêng từng dòng. Nếu constructor ném exception với item 1 sai, người dùng có thể không nhận được report của tất cả item còn lại.

## 14. Integration test: ba outcomes cho ba item

Dùng DirectChannel và QueueChannel trong test để quan sát kết quả ngay sau khi send(). Không cần dùng Thread.sleep, vì ví dụ này xử lý đồng bộ.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(PartialImportFlowConfig.class)
class PartialImportFlowTest {

    @Autowired
    @Qualifier("importBatchInput")
    MessageChannel input;

    @Autowired
    @Qualifier("importBatchReports")
    QueueChannel reports;

    @BeforeEach
    void clearReports() {
        while (reports.receive(0) != null) {
            // Dọn queue nếu Spring context được dùng lại giữa tests.
        }
    }

    @Test
    void oneBadMiddleItemDoesNotLoseTheBatch() {
        ImportBatch batch = new ImportBatch("batch-201", List.of(
                new ImportLine("batch-201", 1, "SKU-A", "3"),
                new ImportLine("batch-201", 2, "SKU-B", "abc"),
                new ImportLine("batch-201", 3, "SKU-C", "5")));

        assertTrue(input.send(
                MessageBuilder.withPayload(batch).build()));

        Message<?> response = reports.receive(0);
        assertNotNull(response);
        BatchReport report = (BatchReport) response.getPayload();

        assertEquals("batch-201", report.batchId());
        assertEquals(3, report.total());
        assertEquals(2, report.successCount());
        assertEquals(1, report.failureCount());
        assertEquals(
                List.of(1, 2, 3),
                report.outcomes().stream()
                        .map(LineOutcome::lineNo).toList());
        assertEquals(
                "INVALID_QUANTITY_FORMAT",
                report.outcomes().get(1).errorCode());
        assertEquals("SUCCESS", report.outcomes().get(2).status());
        assertNull(reports.receive(0));
    }

    @Test
    void allInvalidItemsStillProduceACompleteReport() {
        ImportBatch batch = new ImportBatch("batch-202", List.of(
                new ImportLine("batch-202", 1, "", "2"),
                new ImportLine("batch-202", 2, "SKU-B", "0")));

        assertTrue(input.send(
                MessageBuilder.withPayload(batch).build()));

        Message<?> response = reports.receive(0);
        assertNotNull(response);
        BatchReport report = (BatchReport) response.getPayload();

        assertEquals(2, report.total());
        assertEquals(0, report.successCount());
        assertEquals(2, report.failureCount());
        assertEquals(
                List.of("REJECTED", "REJECTED"),
                report.outcomes().stream()
                        .map(LineOutcome::status).toList());
    }

    @Test
    void firstAndLastFailuresDoNotHideValidMiddle() {
        ImportBatch batch = new ImportBatch("batch-203", List.of(
                new ImportLine("batch-203", 1, "SKU-A", "abc"),
                new ImportLine("batch-203", 2, "SKU-B", "7"),
                new ImportLine("batch-203", 3, "SKU-C", "-1")));

        assertTrue(input.send(
                MessageBuilder.withPayload(batch).build()));

        BatchReport report = (BatchReport) reports.receive(0).getPayload();
        assertEquals(1, report.successCount());
        assertEquals(2, report.failureCount());
        assertEquals("SUCCESS", report.outcomes().get(1).status());
    }
}
~~~

### 14.1. Chính xác thì integration test trên chứng minh gì?

Nó chứng minh:

- Một input ImportBatch được Splitter tạo ra nhiều child message.
- Lỗi dữ liệu của một child thành **LineOutcome REJECTED không null**.
- Các child khác vẫn có outcome thành công.
- Aggregator release một BatchReport đúng số lượng trong luồng sync minh họa.

Nó **chưa chứng minh**:

- Error channel sẽ tự chuyển mọi unexpected exception thành outcome.
- Batch đã được lưu bền hoặc có thể phục hồi sau restart.
- Các side effect được thực hiện đúng một lần khi retry/redelivery.
- Kết quả đồng bộ đồng nghĩa với semantics của ExecutorChannel/broker.

Chỉ kết luận những gì test thật sự quan sát.

## 15. Kiểm thử missing item, retry và phân phối bất đồng bộ

Với ExecutorChannel, một worker xử lý line 3 có thể timeout trong khi line 1, 2, 4, 5 hoàn tất. Trường hợp này **không giống** line 3 có lỗi validation: có thể chưa có terminal outcome cho line 3.

### 15.1. Test một item lỗi bất ngờ

Tạo processor kiểm thử chủ động ném IllegalStateException với line 3. Xác minh:

1. ErrorMessage có thông tin xác định item nếu cấu hình error channel hỗ trợ.
2. Không có BatchReport thành công đầy đủ nếu thiếu outcome line 3.
3. Batch state được giữ là IN_PROGRESS/FAILED theo chính sách, không báo toàn bộ đã thành công.
4. Nếu dùng timeout/partial release, report có **expected=5, received=4, missing=[3]**.
5. Nếu lỗi được phục hồi bằng retry, line 3 tạo **một** terminal outcome và batch hoàn tất.

### 15.2. Test concurrency khi cùng item bị giao lại

Giả lập hai worker xử lý cùng key **tenant-A:batch-204:3:revision-1**:

- Chỉ một worker được phép commit side effect.
- Worker còn lại trả outcome đã lưu hoặc chờ trạng thái để trả đúng kết quả.
- Nếu worker đầu crash trước commit, worker sau có đường retry hợp lệ.
- Nếu worker đầu đã commit nhưng response mất, redelivery **không ghi effect lần hai**.

Dùng database thật với primary key/unique constraint và transaction để xác minh, không suy luận từ một ConcurrentHashMap cục bộ rằng nhiều instance đã an toàn.

### 15.3. Test Aggregator timeout và late arrival

Với một group kỳ vọng 5 messages, cố ý chỉ gửi 4 outcomes:

1. Xác minh mặc định chưa có BatchReport hoàn tất.
2. Kích hoạt group timeout theo cấu hình thử nghiệm, quan sát policy discard/partial result.
3. Nếu phát partial report, **bắt buộc có INCOMPLETE status** trong hợp đồng kết quả.
4. Gửi outcome thứ 5 sau timeout và xác minh late-arrival policy: discard, cập nhật report phiên bản mới hoặc reconcile theo trạng thái bền.
5. Dùng cùng batchId nhưng một lần replay correlationId mới; đảm bảo không ghi hai bản báo cáo terminal như hai batch độc lập.

### 15.4. Test Iterator với sequenceSize chưa biết

Dùng Splitter phát từ Iterator thay vì List. Xác minh sequenceSize không đủ để release group theo default. Sau đó thiết kế rõ completion marker hoặc release strategy phù hợp. Không chỉnh sequenceSize tùy tiện thành số lượng đã thấy trước khi nguồn báo kết thúc.

## 16. Chặn những dạng mất dữ liệu không dễ nhận ra

### 16.1. Empty input

Nếu Splitter trả **collection rỗng**, không có child message để Aggregator nhận. Tùy phiên bản và cấu hình, Splitter hỗ trợ **discardChannel** để nhận request không tạo được item; null từ phép split có semantics khác với collection rỗng.

Với bài toán import, có thể chọn:

- **Reject batch rỗng trước split** như ImportBatch constructor đã làm.
- Trả một **BatchReport rỗng có chủ đích** từ nhánh riêng nếu business cho phép.
- Gửi request tới discard channel để logging/đối soát.

Không đợi Aggregator tự tạo báo cáo từ một nhóm **không hề có message**.

### 16.2. Một element chứa null

Một List có phần tử null có thể gặp giới hạn của Java, conversion hoặc message payload (Spring Message không chấp nhận null payload theo hợp đồng thông thường). Nếu payload có thể thiếu một dòng, biểu diễn nó bằng **một object lỗi dữ liệu có identity** hoặc validate batch và tạo REJECTED outcome tương ứng; không dựa vào việc gửi null làm một child message.

Trong ví dụ này, **List.copyOf** từ chối null item khi tạo ImportBatch, coi đó là lỗi cấu trúc của batch. Đó là chính sách cố ý của ví dụ; ứng dụng có yêu cầu báo lỗi từng dòng trống cần model biểu diễn dòng rỗng rõ ràng (ví dụ RawLine với trường optional), không truyền null.

### 16.3. Lỗi đọc một file/stream giữa chừng

Khi Splitter lấy item từ Iterator, một exception trong quá trình đọc phần tử thứ 501 có thể xảy ra **sau khi 500 item đầu đã được phát đi**. Nếu cần replay bền và đối soát:

1. Lưu input hoặc manifest theo các chunk có checksum/offset.
2. Ghi rõ các item đã được dispatch và các item đã terminal.
3. Không coi việc đọc source tới EOF là chắc chắn nếu iterator ném exception.
4. Khi phục hồi, dùng offset/lineId ổn định và per-item idempotency.
5. Với stream không biết số lượng, có giao thức **end-of-batch marker** hoặc completion state riêng.

### 16.4. Một nhánh bị Filter loại

Filter có discardChannel có thể **chuyển message bị loại sang một nhánh khác**. Nếu cần batch report đủ các item, nhánh discard có thể tạo **REJECTED outcome** và gửi về cùng aggregate input theo cơ chế được thiết kế; phải giữ đúng correlation và tránh trùng terminal outcome.

Tuy nhiên, nếu Filter đứng **trước Splitter** để loại toàn batch không đạt điều kiện xác thực, đó là quyết định khác: không cần tạo outcomes cho từng item của một batch không được chấp nhận.

### 16.5. Thay đổi order trong xử lý song song

Khi dùng ExecutorChannel, item 5 có thể hoàn tất trước item 1. Aggregator có thể nhận message theo **thứ tự đến**, không theo lineNo. Vì vậy:

- Không giả định iteration order của MessageGroup đồng nghĩa thứ tự nhập.
- Sắp xếp report theo **lineNo** như BatchReports.summarize().
- Nếu cần thực hiện side effect **đúng thứ tự**, phải thiết kế sequencing/resequencer hoặc serial processing riêng; một report đã sort không làm side effect trước đó trở nên ordered.

### 16.6. Một output cho hai lần xử lý cùng item

Redelivery có thể làm item 3 tạo **hai LineOutcome**. Nếu đưa cả hai vào Aggregator mà không có dedup policy, có thể gây:

- Số lượng outcome cao hơn số item thực.
- Group release sai thời điểm hoặc late message bị discard.
- Hai báo cáo terminal cho cùng batch nếu group lifecycle không được kiểm soát.

Đừng dùng sequenceSize để che lặp; hãy bảo vệ bằng **item identity + revision**, inbox/ledger bền và nguyên tắc **một terminal outcome duy nhất cho mỗi logical item**.

## 17. Monitoring theo batch và item

Muốn biết một dòng có làm mất batch hay không, cần đo cả hai cấp độ:

| Metric/trạng thái | Mục đích |
| --- | --- |
| **batch_received_total** | Số batch được tiếp nhận |
| **batch_rejected_total{reason}** | Batch lỗi cấu trúc/quyền trước split |
| **batch_items_expected** | Số item trong manifest, không phải số message đã tới |
| **item_attempts_total{step}** | Số lần thử xử lý item |
| **item_outcomes_total{status,error_code}** | Số terminal outcomes theo loại |
| **item_retry_total** | Số attempt retry |
| **batch_completed_total{status}** | Batch terminal thành công/toàn lỗi/partial |
| **batch_incomplete_total** | Batch chưa đủ outcome khi hết SLA |
| **aggregator_group_timeout_total** | Nhóm hết thời gian chờ |
| **aggregator_late_arrival_total** | Outcome đến sau khi group đóng |
| **duplicate_item_skipped_total** | Số lần tránh được side effect trùng |
| **error_channel_delivery_failed_total** | Đường báo lỗi bị lỗi |
| **batch_processing_age_seconds** | Tuổi batch chưa terminal |

Hạn chế số lượng giá trị của metric labels. **Không gắn batchId, lineNo, userId hoặc tenantId** trực tiếp làm label nếu cardinality lớn; dùng trace/log có kiểm soát truy cập để tra cứu chi tiết.

### 17.1. Ví dụ log lỗi item

~~~json
{
  "batchId": "batch-201",
  "lineNo": 2,
  "stage": "quantity-validation",
  "status": "REJECTED",
  "errorCode": "INVALID_QUANTITY_FORMAT",
  "retryable": false
}
~~~

Không log raw payload hoặc secrets của item để tránh lộ dữ liệu. Nếu cần giữ input lỗi để người dùng sửa, lưu trong quarantine với quyền truy cập và retention phù hợp.

### 17.2. Đối soát số lượng

Một invariant hữu ích:

~~~text
expectedItemCount =
    completedItemCount
  + rejectedItemCount
  + failedFinalItemCount
  + pendingItemCount
~~~

Trong hệ thống có retries, các count trên phải đại diện cho **logical items duy nhất**, không phải số attempts. Nếu một item được thử 5 lần, nó vẫn chỉ là **một item** trong manifest. Kiểm tra invariant này giúp phát hiện item đã mất dấu hoặc outcome trùng.

### 17.3. Alert theo nghiệp vụ thay vì chỉ exception rate

Nên cảnh báo khi:

- Batch ở trạng thái IN_PROGRESS quá SLA.
- Có expected item chưa có terminal outcome và cũng không có retry job.
- Aggregator có nhiều group chờ hoặc timeout.
- Tỷ lệ REJECTED tăng đột biến (producer có thể thay schema).
- Một item bị retry liên tục nhưng không chuyển trạng thái.
- Nhiều kết quả terminal xuất hiện cho cùng batchId + lineNo + revision.
- Có batch report SUCCESS nhưng count không khớp manifest.
- Error flow không thể lưu/quarantine failed message.

## 18. Bài thực hành: batch đối soát vận đơn

Thiết kế một pipeline nhận:

~~~java
record RawShipmentRow(
        String batchId,
        int rowNo,
        String shipmentId,
        String declaredWeightGrams) {}

record ShipmentImportBatch(
        String batchId,
        java.util.List<RawShipmentRow> rows) {}
~~~

Đầu vào có 6 dòng, trong đó:

| Dòng | shipmentId | declaredWeightGrams | Mong đợi |
| --- | --- | --- | --- |
| 1 | SH-101 | 500 | SUCCESS |
| 2 | SH-102 | 250 | SUCCESS |
| 3 | SH-103 | wrong | REJECTED |
| 4 | SH-104 | 1000 | SUCCESS |
| 5 | SH-105 | -10 | REJECTED |
| 6 | SH-106 | 700 | SUCCESS |

**Yêu cầu**

1. Kiểm tra batchId, số dòng tối đa và rowNo duy nhất trước split.
2. Tách từng dòng thành message độc lập với correlation/sequence phù hợp.
3. Mỗi dòng phải có **RowOutcome** terminal, gồm rowNo, status, errorCode và dữ liệu đã chuẩn hóa nếu thành công.
4. Hai dòng sai không khiến bốn dòng hợp lệ bị mất.
5. Aggregator tạo một report có **6 outcomes, 4 SUCCESS và 2 REJECTED**.
6. Report được sắp theo rowNo dù xử lý song song.
7. Nếu database offline ở dòng 4, dòng đó phải có trạng thái RETRYING/UNKNOWN phù hợp, không bị đổi thành lỗi validation.
8. Khi retry cùng logical item, không ghi một adjustment hai lần.
9. Nếu một item không bao giờ tạo outcome, batch phải có trạng thái INCOMPLETE và cách phục hồi.

**Các bước thực hiện**

1. Viết ShipmentBatchValidator kiểm tra cấu trúc nhóm.
2. Viết ShipmentRowTransformer thuần, trả một RowOutcome có kiểu cho lỗi dữ liệu.
3. Dựng IntegrationFlow với Splitter → Transformer → Aggregator → report channel.
4. Kiểm thử item lỗi ở đầu, giữa, cuối và trường hợp mọi item đều sai.
5. Thử thay Transformer bằng logic ném exception ở dòng 3 để quan sát khác biệt với failure outcome.
6. Thêm một Filter trước Aggregator, loại dòng 3, sau đó chứng minh group thiếu kết quả và không được báo SUCCESS.
7. Chuyển sang ExecutorChannel có bounded executor và test kết quả đến không theo thứ tự.
8. Tạo processing ledger dùng batchId + rowNo + revision, test retry sau commit và rollback.
9. Thiết kế manifest/timeout để phát hiện item chưa terminal và late arrival.
10. Đưa ra dashboard với batch status, item status, nhóm đang chờ và thời gian hoàn tất p95.

### Câu hỏi tự kiểm tra

1. Splitter có tự tạo fault isolation cho từng item không?
2. Khi item thứ 3 ném exception trên DirectChannel, điều gì có thể xảy ra với item 4, 5?
3. Vì sao Filter loại item 3 có thể khiến Aggregator chờ mãi?
4. Ba headers correlationId, sequenceNumber và sequenceSize có vai trò gì?
5. sequenceSize=0 từ Iterator có nghĩa là batch rỗng không?
6. Tại sao LineOutcome REJECTED khác một ErrorMessage trên errorChannel?
7. Khi nào lỗi một item phải khiến cả batch bị reject theo chính sách all-or-nothing?
8. Vì sao không catch tất cả Exception rồi gọi mọi item là REJECTED?
9. Làm thế nào bảo đảm mỗi item có đúng một terminal outcome qua redelivery?
10. Một BatchReport tạo bởi Aggregator có chứng minh database đã commit chưa?
11. Partial result khi timeout có được tự báo là toàn batch SUCCESS không?
12. Khi sửa dòng sai và replay, vì sao cần revision hoặc operation identity khác?
13. Tại sao group timeout, persistence và late-arrival policy phải thiết kế cùng nhau?
14. Nếu dùng ExecutorChannel, thứ tự outcome đến Aggregator có còn là thứ tự dòng ban đầu không?

## 19. Checklist trước khi triển khai

- Đã chọn rõ **fail-fast, all-or-nothing, partial success hoặc eventual completion**.
- Batch structural validation tách khỏi item-level validation.
- Input có batchId/lineNo ổn định và manifest/count đáng tin.
- Giới hạn batch size và resource usage; không materialize collection vô hạn.
- Mỗi item hợp lệ hoặc sai dữ liệu có **một terminal outcome**, không tự trả null.
- Lỗi hệ thống/transient/UNKNOWN không bị biến thành REJECTED sai nghĩa.
- Splitter và downstream giữ correlation/sequence đúng khi dùng Aggregator.
- Iterator/stream có completion policy; không mặc định sequenceSize luôn biết trước.
- Filter discard và errorChannel được xử lý có chủ đích, không làm mất outcome.
- Aggregator timeout/partial result được đánh dấu INCOMPLETE khi thiếu item.
- MessageGroupStore, group expiration và late-arrival policy phù hợp SLA.
- Những side effect dùng **idempotency theo logical item + revision**.
- Database effect có unique constraint/transaction; external effect có key/reconciliation.
- Có quy tắc sửa dữ liệu và replay mà không duplicate những item đã hoàn tất.
- Error flow/quarantine có consumer, độ bền và retention thích hợp.
- Test bao phủ lỗi item đầu/giữa/cuối, all-invalid, missing, async, retry và crash.
- Monitoring phân biệt attempts, logical items, terminal outcomes và batch completion.

**Kết luận:** Splitter chỉ tách message thành phần tử; nó không tự quyết định cả batch phải dừng hay có thể tiếp tục. Muốn **một phần tử lỗi không làm mất toàn bộ batch ngoài ý muốn**, hãy công bố chính sách partial success, giữ identity từng item, biến lỗi dữ liệu dự đoán thành **outcome có kiểu và không null**, và dùng Aggregator với đủ correlation/sequence để tạo báo cáo trung thực. Với lỗi hạ tầng, cần retry riêng từng phần tử, trạng thái bền, timeout và idempotency. Như vậy một phần tử hỏng không vô tình xóa dấu những phần tử còn lại, đồng thời lỗi nghiêm trọng vẫn được phát hiện thay vì bị che giấu.

## Tài liệu tham khảo

- [Spring Integration Reference — Splitter](https://docs.spring.io/spring-integration/reference/splitter.html): vai trò Splitter, message headers, Iterator/sequenceSize và discard semantics.
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): correlation, release strategy, group timeout, partial result, late-arrival và MessageGroupStore.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): các cấu hình split, aggregate và channel.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): DirectChannel, async error messages và error channel.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, ExecutorChannel, QueueChannel và semantics dispatch.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): hỗ trợ dedup và giới hạn của một claim trước side effect.
- [Enterprise Integration Patterns — Splitter](https://www.enterpriseintegrationpatterns.com/patterns/messaging/Sequencer.html): nền tảng kỹ thuật của Splitter và quy tắc chia message.
- [Enterprise Integration Patterns — Aggregator](https://www.enterpriseintegrationpatterns.com/patterns/messaging/Aggregator.html): tổng hợp các message liên quan thành một kết quả.
