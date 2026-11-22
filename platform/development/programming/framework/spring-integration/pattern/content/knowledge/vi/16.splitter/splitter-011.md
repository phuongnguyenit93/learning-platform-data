# Đối chiếu output với input ban đầu

## 1. Đặt vấn đề: Splitter tạo ra những gì và làm sao biết có thiếu?

Trong hệ thống xử lý đơn hàng, một message có thể chứa nhiều dòng hàng. **Splitter** là mẫu Enterprise Integration Patterns (EIP) chia message lớn thành nhiều message nhỏ để mỗi phần được xử lý độc lập.

Ví dụ, đầu vào là một đơn có ba dòng:

~~~text
BatchRequest(batchId=BAT-10, processingId=RUN-10)
  L-01: SKU-A × 2
  L-02: SKU-B × 1
  L-03: SKU-C × 5
~~~

Sau Splitter, ta mong nhận được ba message con:

~~~text
WorkItem(BAT-10, RUN-10, L-01, SKU-A, 2)
WorkItem(BAT-10, RUN-10, L-02, SKU-B, 1)
WorkItem(BAT-10, RUN-10, L-03, SKU-C, 5)
~~~

Nhưng khi các message đi qua Filter, Router, outbound adapter hoặc handler bất đồng bộ, hệ thống có thể quan sát:

~~~text
Result(RUN-10, L-01, SUCCESS)
Result(RUN-10, L-02, REJECTED)
Result(RUN-10, L-02, REJECTED)  // duplicate
Result(RUN-10, L-99, SUCCESS)   // không thuộc input
// L-03: chưa có kết quả
~~~

**Chỉ đếm “đã có ba hay bốn kết quả” là không đủ.** Cần đối chiếu output với input ban đầu theo **danh tính từng phần, phiên xử lý, số lượng, trạng thái nghiệp vụ và ranh giới thời gian**. Hai kết quả trùng `L-02` không được thay cho một kết quả thiếu của `L-03`.

~~~mermaid
flowchart TD
    I["Input: L-01, L-02, L-03"] --> S[Splitter]
    S --> A[WorkItem L-01]
    S --> B[WorkItem L-02]
    S --> C[WorkItem L-03]
    A --> OA["Outcome L-01: SUCCESS"]
    B --> OB["Outcome L-02: REJECTED"]
    B -. redelivery .-> OB2["Outcome L-02: REJECTED"]
    C -. timeout .-> MISS["Chưa thấy outcome"]
    OA --> R[Reconciler]
    OB --> R
    OB2 --> R
    R --> V["Missing: L-03 | Duplicate: L-02"]
~~~

Điểm cần phân biệt: **Splitter chia message**, còn **Reconciler/Aggregator** hoặc logic nghiệp vụ phía sau mới có thể khẳng định các phần đã được xử lý đầy đủ. Một lệnh `send(...)` thành công không mặc nhiên xác nhận nghiệp vụ của mọi phần đã hoàn tất.

Bài học thuộc chương **Splitter** của module `SPRING_INTEGRATION_PATTERN`: triển khai Enterprise Integration Patterns bằng Spring Integration để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng, kết hợp Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử và theo dõi từng nhánh xử lý.

### Mục tiêu

Sau bài này, người học có thể:

1. Xác định **hợp đồng input/output** của Splitter trước khi viết assertion.
2. Phân biệt **child message**, **processing outcome** và **aggregate result**.
3. Chọn khóa đối chiếu ổn định: `processingId`, `batchId`, `lineId`, thay vì dựa duy nhất vào vị trí hoặc Spring message ID.
4. Kiểm tra mất phần, phần thừa, kết quả trùng, sai phiên, sai thứ tự và kết quả đến muộn.
5. Viết unit test cho logic reconciliation và integration test cho Splitter của Spring Integration bằng Java DSL/JUnit 5.
6. Phối hợp Filter, Aggregator, Gateway, retry, error channel và quan sát để không báo hoàn tất sai.

## 2. Phải làm rõ đang đối chiếu ở mốc nào

### 2.1. Ba tầng output khác nhau

Một Splitter có thể tạo child message, rồi các child message được xử lý và cuối cùng được gom:

~~~mermaid
flowchart LR
    I["BatchRequest: 3 items"] --> S[Splitter]
    S --> C["3 WorkItem messages"]
    C --> H[Handlers / Router / Filter]
    H --> O["0–n WorkOutcome messages"]
    O --> A[Aggregator / Reconciler]
    A --> R[BatchReport]
~~~

| Tầng | “Output” là gì? | Có thể khẳng định điều gì? |
|---|---|---|
| **A. Splitter output** | Các child `Message<WorkItem>`. | Splitter đã phát các phần nào theo hợp đồng tách message. |
| **B. Downstream outcome** | `WorkOutcome` cho các phần đã được xử lý hoặc từ chối. | Handler đã báo kết quả gì cho từng phần. |
| **C. Aggregate/report output** | `BatchReport` sau khi kết hợp kết quả. | Nhóm đã thỏa điều kiện release/reconciliation nào. |

Một test chỉ chặn message ở **ngay sau Splitter** có thể chứng minh đủ ba phần đã được tạo, nhưng không chứng minh API ngoài đã được gọi thành công. Ngược lại, test `BatchReport` chỉ có `status=COMPLETED` có thể bỏ sót bug Aggregator đếm duplicate thành đủ số nếu không kiểm tra danh tính các phần.

### 2.2. Hợp đồng Splitter có thể là 1→N, 1→0 hay 1→N có điều kiện

| Hợp đồng | Ví dụ | Cách đối chiếu |
|---|---|---|
| **1 phần tử đầu vào → 1 child** | Mỗi dòng hàng thành một `WorkItem`. | So sánh ID/chi tiết từng dòng, expected count. |
| **1 phần tử đầu vào → nhiều child** | Một tệp được chia theo các cửa sổ kích thước. | Đối chiếu bằng `parentId + chunkIndex`, độ phủ/ranh giới, không chỉ count. |
| **N phần tử → ít phần tử hơn có chủ đích** | Loại dòng trống trước khi split. | Ghi rule đã loại và tập `expected` sau normalization. |
| **Input có thể rỗng** | Batch không có dòng. | Định nghĩa rõ trả empty, reject hay zero-child, không chờ Aggregator vô hạn. |
| **Splitter streaming** | Iterator/Flux thay vì List đã biết kích thước. | Không giả định luôn biết `sequenceSize`; cần end-of-stream/đóng nhóm hoặc policy thời gian. |
| **Message bị Filter loại sau split** | Một item không đủ điều kiện. | Lưu outcome `REJECTED` hoặc thiết kế release thích hợp, không coi mất dữ liệu là thành công. |

Bài này chọn hợp đồng **một dòng hàng hợp lệ tạo đúng một `WorkItem`**, với danh sách đầu vào hữu hạn và không rỗng. Khi muốn áp dụng cho batch rỗng, streaming, one-to-many hoặc Splitter phức tạp, phải điều chỉnh những invariant tương ứng.

### 2.3. “Đã gửi” khác “đã xử lý xong”

Với `DirectChannel` và handler đồng bộ, thao tác gửi có thể bao gồm luôn thời gian handler thực thi. Với `ExecutorChannel`, `QueueChannel`/poller hoặc broker, nguồn gửi có thể chỉ xác nhận **đã tiếp nhận**; handler có thể chạy sau, retry hoặc thất bại.

Vì thế, ta nên đặt tên metric/sự kiện:

~~~text
SPLIT_CHILD_CREATED   // child được tạo bởi Splitter
CHILD_DISPATCHED      // đã gửi theo contract channel
CHILD_PROCESSING_DONE // handler đã xử lý
CHILD_OUTCOME_STORED  // kết quả đã được ghi theo contract
BATCH_RECONCILED      // đã đối chiếu đủ điều kiện
~~~

Không dùng một biến `processedCount` chung cho tất cả những mốc này.

## 3. Danh tính từng phần: chìa khóa đối chiếu

### 3.1. Không dùng vị trí làm danh tính duy nhất

Giả sử input:

~~~text
index 0: L-01, SKU-A
index 1: L-02, SKU-B
index 2: L-03, SKU-C
~~~

Nếu xử lý song song, kết quả có thể đến theo thứ tự `L-03, L-01, L-02`. So sánh `output[0]` với `input[0]` sẽ báo sai dù cả ba đều đúng. **Thứ tự nhận kết quả không nhất thiết là thứ tự của input**.

Đề xuất tách:

- `batchId`: mã batch nghiệp vụ.
- `processingId`: danh tính **một lần xử lý** batch; phân biệt replay, retry toàn batch hay hai workflow chạy cùng lúc.
- `lineId`: danh tính **một dòng gốc trong batch**.
- `item/attemptId`: ID lần xử lý cụ thể nếu có retry/redelivery ở từng dòng.
- `correlationId`: header do hạ tầng dùng để gom các message liên quan, phải được chuyển qua các bước nếu Aggregator cần.
- `MessageHeaders.ID`: định danh một Spring message; có thể thay đổi khi tạo message mới, không thay thế `lineId`.

### 3.2. Ví dụ lineage xuyên các thành phần

~~~text
BatchRequest:
  batchId=BAT-10
  processingId=RUN-10
  lineId=L-02

Child WorkItem:
  batchId=BAT-10
  processingId=RUN-10
  lineId=L-02

WorkOutcome:
  batchId=BAT-10
  processingId=RUN-10
  lineId=L-02
  status=REJECTED
~~~

Nếu một outbound adapter tái tạo message, `MessageHeaders.ID` có thể mới. Nhưng business lineage vẫn phải cho phép kết luận outcome thuộc đúng **batch/processing/line**. Đừng chỉ so sánh correlation header nếu nó có thể bị lọc qua transport mà chưa có mapping được xác minh.

### 3.3. Những lỗi identity thường xuất hiện

| Lỗi | Ví dụ | Hậu quả |
|---|---|---|
| Trùng `lineId` ở input | Có hai dòng đều là `L-02`. | Không biết một outcome đại diện dòng nào. |
| Kết quả trùng | `L-02` có hai outcomes vì redelivery. | Có thể đếm sai thành đủ `N`. |
| Kết quả lạ | `L-99` không nằm trong input. | Có thể ghép nhầm batch. |
| Sai `processingId` | Outcome của `RUN-09` đến `RUN-10`. | Replay cũ bị tính thành kết quả mới. |
| Đổi `lineId` trong Transformer | Input `L-02`, output `L02`. | Đối chiếu sai nếu không có mapping ổn định. |
| Trả kết quả không mang `batchId` | Chỉ còn SKU, số lượng. | Không thể xác định chính xác nguồn nếu nhiều batch dùng cùng SKU. |
| Dùng `sequenceNumber` làm business ID | Sequence 1 của nhiều batch. | Ghép nhầm message giữa hai nhóm. |

Khi dòng hàng không có ID từ upstream, có thể tạo một ID ổn định theo **batch + input index** tại biên đã xác thực, nhưng phải lưu mapping và xử lý trường hợp input được sắp xếp lại. Không lấy một thứ tự tình cờ của `HashMap` làm business identity.

## 4. Những invariant quan trọng của reconciliation

Ta định nghĩa `I` là tập line ID kỳ vọng của input hợp lệ và `O` là multiset (đa tập) các outcome thực nhận thuộc đúng `batchId` và `processingId`.

| Invariant | Ý nghĩa |
|---|---|
| **Completeness** | Mỗi ID trong `I` có outcome đúng theo contract. |
| **No unexpected ID** | Không có line ID ở `O` nằm ngoài `I`. |
| **No duplicates** | Một line không có nhiều outcome cuối cùng nếu contract quy định 1 kết quả/line. |
| **Correct lineage** | Mỗi outcome thuộc đúng batch và processing ID. |
| **Payload integrity** | Child giữ đúng `sku`/`quantity` từ input, trừ biến đổi có chủ đích và có mapping. |
| **Business success** | Mọi kết quả đủ điều kiện đạt trạng thái thành công — khác với completeness. |
| **Stable correlation** | Kết quả có thể được ghép đúng nhóm kể cả qua adapter/threads. |
| **Order** | Chỉ bắt buộc nếu contract yêu cầu; khi cần, kiểm bằng `lineId` hoặc input index. |

### 4.1. Complete không phải successful

Ví dụ:

~~~text
Input:      {L-01, L-02, L-03}
Output IDs: {L-01, L-02, L-03}
Statuses:   SUCCESS, REJECTED, SUCCESS

structurallyComplete = true
allSucceeded        = false
~~~

Ngược lại:

~~~text
Input:      {L-01, L-02, L-03}
Output IDs: {L-01, L-01, L-02}

structurallyComplete = false
allSucceeded        = false
missing            = {L-03}
duplicates         = {L-01}
~~~

Một Aggregator chỉ đếm `sequenceSize=3` và nhận ba message có thể **release sai** nếu duplicate và missing không được xử lý trong quy tắc nhóm. Các header sequence rất hữu ích, nhưng **cần kiểm tra contract và danh tính kết quả**.

### 4.2. Có được phép “không có output”?

Với Filter sau Splitter, một phần có thể bị loại theo policy. Khi đó phải chọn rõ:

1. **Tạo `WorkOutcome(REJECTED)`:** reconciliation thấy dòng đó đã được đánh giá và loại; đầy đủ về kết quả nhưng không phải tất cả thành công.
2. **Cho phép drop có chủ đích:** snapshot danh sách ID bị loại và thay đổi expected set/release policy có kiểm chứng.
3. **Không cho drop:** mọi phần bắt buộc có success/failure result; im lặng là missing và phải timeout/recovery.

Không được mặc định “ít output hơn input” luôn là lỗi, cũng không được mặc định một missing message luôn là business rejection. **Hợp đồng đầu vào–đầu ra quyết định cách hiểu.**

## 5. Mô hình Java: giữ input gốc và lineage của từng phần

Ví dụ hướng tới **Java 17+, Spring Boot 3.x, Spring Integration 6.x**. Các type dùng ở nhiều đoạn code được xem như nằm cùng package, và type `public` cần tách thành file tương ứng nếu đưa vào dự án thực.

### 5.1. Đầu vào bất biến

~~~java
import java.util.List;
import java.util.Objects;

record OrderLine(String lineId, String sku, int quantity) {
    OrderLine {
        if (lineId == null || lineId.isBlank()
                || sku == null || sku.isBlank()
                || quantity <= 0) {
            throw new IllegalArgumentException("INVALID_ORDER_LINE");
        }
    }
}

record BatchRequest(
        String batchId,
        String processingId,
        List<OrderLine> lines) {
    BatchRequest {
        if (batchId == null || batchId.isBlank()
                || processingId == null || processingId.isBlank()) {
            throw new IllegalArgumentException("INVALID_BATCH_ID");
        }
        Objects.requireNonNull(lines, "lines");
        lines = List.copyOf(lines);
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("EMPTY_BATCH");
        }
        long uniqueLines = lines.stream()
                .map(OrderLine::lineId)
                .distinct()
                .count();
        if (uniqueLines != lines.size()) {
            throw new IllegalArgumentException("DUPLICATE_INPUT_LINE_ID");
        }
    }
}
~~~

**Tại sao phải copy `lines`?** Nếu caller thay đổi một `ArrayList` sau khi gửi batch, expected set của reconciliation có thể đổi trong lúc các child message đang chạy. `List.copyOf` tạo snapshot bất biến về **container**; ở ví dụ các `OrderLine` là record chứa field bất biến. Nếu component bên trong là mutable POJO/List/array, cần defensive copy sâu hơn theo contract.

Batch rỗng được **từ chối có chủ đích** trong bài. Một ứng dụng khác có thể cho phép zero-child và trả báo cáo thành công rỗng; nếu vậy phải bổ sung semantics Aggregator/reply cho case này, thay vì để Gateway chờ vô hạn.

### 5.2. Child message mang thông tin gốc

~~~java
record WorkItem(
        String batchId,
        String processingId,
        String lineId,
        String sku,
        int quantity) {}

final class BatchSplitterPolicy {
    List<WorkItem> split(BatchRequest input) {
        return input.lines().stream()
                .map(line -> new WorkItem(
                        input.batchId(),
                        input.processingId(),
                        line.lineId(),
                        line.sku(),
                        line.quantity()))
                .toList();
    }
}
~~~

Mỗi `WorkItem` chứa **business lineage** để đối chiếu sau xử lý. Việc nhân bản một số trường ID không thay thế metadata `correlationId`/`sequenceNumber` do Splitter tạo, nhưng giúp downstream không mất khả năng đối chiếu khi đi qua adapter có header mapping.

### 5.3. Outcome có trạng thái rõ

~~~java
enum WorkStatus {
    SUCCESS,
    REJECTED,
    FAILED
}

record WorkOutcome(
        String batchId,
        String processingId,
        String lineId,
        WorkStatus status) {
    WorkOutcome {
        Objects.requireNonNull(batchId, "batchId");
        Objects.requireNonNull(processingId, "processingId");
        Objects.requireNonNull(lineId, "lineId");
        Objects.requireNonNull(status, "status");
    }
}
~~~

Một `FAILED` outcome **vẫn là một outcome có ID** để reconciliation biết phần nào đã kết thúc thất bại. Nếu handler throw mà **không phát outcome**, phần đó sẽ được ghi nhận là missing cho đến khi có error/recovery policy tạo kết quả hoặc deadline hết.

### 5.4. Không tự lấy số lượng output làm kết luận

~~~java
// Không đủ để khẳng định:
boolean complete = outcomes.size() == input.lines().size();
~~~

Một cách đúng cần xác minh **ID, nhóm, duplicate, missing, trạng thái**, không chỉ độ dài danh sách. Các phần tiếp theo triển khai hàm reconciliation và kiểm thử từng trường hợp.

## 6. Thuật toán đối chiếu một input batch với nhiều outcomes

### 6.1. Báo cáo phân biệt đầy đủ và thành công

Chúng ta cần hai cờ khác nhau:

- `structurallyComplete`: mỗi line ID trong input có **đúng một** kết quả, không có ID lạ và không có kết quả của batch/processing khác.
- `allSucceeded`: cấu trúc đã đầy đủ **và** tất cả status là `SUCCESS`.

Ngoài hai cờ, báo cáo cần chỉ ra chính xác **dòng nào thiếu, thừa, trùng hoặc sai phiên**.

~~~java
import java.util.List;
import java.util.Map;

record BatchReconciliation(
        String batchId,
        String processingId,
        List<String> missingLineIds,
        List<String> unexpectedLineIds,
        List<String> duplicateLineIds,
        List<String> foreignResults,
        Map<String, WorkStatus> firstStatusByLine,
        boolean structurallyComplete,
        boolean allSucceeded) {}
~~~

Trong production, có thể bổ sung `observedAt`, deadline, số message đã thử lại, kết quả cuối có hiệu lực và trạng thái pending. Báo cáo minh họa ở đây chỉ đối chiếu **tập outcomes đã nhận tại thời điểm gọi hàm**; không tự đợi một reply chưa đến.

### 6.2. Reconciler độc lập Spring Integration

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

final class BatchReconciler {

    BatchReconciliation reconcile(
            BatchRequest original,
            Collection<WorkOutcome> observed) {

        Objects.requireNonNull(original, "original");
        Objects.requireNonNull(observed, "observed");

        Set<String> expected = new LinkedHashSet<>();
        for (OrderLine line : original.lines()) {
            expected.add(line.lineId());
        }

        Map<String, Integer> counts = new LinkedHashMap<>();
        Map<String, WorkStatus> firstStatus = new LinkedHashMap<>();
        List<String> foreign = new ArrayList<>();

        for (WorkOutcome outcome : observed) {
            Objects.requireNonNull(outcome, "outcome");

            boolean sameBatch =
                    original.batchId().equals(outcome.batchId());
            boolean sameProcessing =
                    original.processingId().equals(
                            outcome.processingId());

            if (!sameBatch || !sameProcessing) {
                foreign.add(
                        outcome.batchId() + "/"
                        + outcome.processingId() + "/"
                        + outcome.lineId());
                continue;
            }

            counts.merge(outcome.lineId(), 1, Integer::sum);
            firstStatus.putIfAbsent(
                    outcome.lineId(), outcome.status());
        }

        List<String> missing = expected.stream()
                .filter(id -> !counts.containsKey(id))
                .toList();

        List<String> unexpected = counts.keySet().stream()
                .filter(id -> !expected.contains(id))
                .toList();

        List<String> duplicates = counts.entrySet().stream()
                .filter(entry -> entry.getValue() > 1)
                .map(Map.Entry::getKey)
                .toList();

        boolean complete = missing.isEmpty()
                && unexpected.isEmpty()
                && duplicates.isEmpty()
                && foreign.isEmpty();

        boolean successful = complete
                && expected.stream().allMatch(id ->
                        firstStatus.get(id) == WorkStatus.SUCCESS);

        return new BatchReconciliation(
                original.batchId(),
                original.processingId(),
                missing,
                unexpected,
                duplicates,
                List.copyOf(foreign),
                Map.copyOf(firstStatus),
                complete,
                successful);
    }
}
~~~

### 6.3. Từng bước của thuật toán

1. Tập `expected` lấy từ **input đã xác thực**. Không tự suy ra input từ những output đã đến, vì sẽ không bao giờ phát hiện được output thiếu.
2. Outcome có `batchId` hoặc `processingId` sai được đưa vào `foreign`; không tính như kết quả hợp lệ của input này.
3. Với mỗi line đúng phiên, ghi **số lần xuất hiện**; cần một multiset, không chỉ một `Set` vì `Set` sẽ che duplicate.
4. `missing` là ID kỳ vọng nhưng không có outcome.
5. `unexpected` là ID xuất hiện ở kết quả nhưng không thuộc input.
6. `duplicates` là ID có số lần xuất hiện lớn hơn một. Vì bài này yêu cầu **đúng một outcome cuối cho mỗi line**, duplicate làm báo cáo không đầy đủ.
7. Chỉ khi hoàn toàn khớp cấu trúc mới xét `allSucceeded`. Một `REJECTED` hoặc `FAILED` là kết quả **đã nhận**, nhưng không phải kết quả nghiệp vụ thành công.

**Hạn chế cố ý:** `firstStatusByLine` lưu trạng thái đầu tiên chỉ để báo cáo đơn giản; khi có hai kết quả khác nhau cho cùng line, cả group bị coi là duplicate. Production không nên âm thầm lấy lần đầu hoặc lần cuối làm “kết quả cuối” khi không có luật rõ về `attemptId`, `resultVersion` và nguồn tin cậy. Để hợp nhất retry có chủ đích, hãy thêm mô hình attempt/deduplication trước lớp reconciliation này.

### 6.4. Ví dụ chạy với một batch

~~~java
import java.util.List;

BatchRequest original = new BatchRequest(
        "BAT-10", "RUN-10", List.of(
                new OrderLine("L-01", "SKU-A", 2),
                new OrderLine("L-02", "SKU-B", 1),
                new OrderLine("L-03", "SKU-C", 5)));

List<WorkOutcome> received = List.of(
        new WorkOutcome("BAT-10", "RUN-10",
                "L-01", WorkStatus.SUCCESS),
        new WorkOutcome("BAT-10", "RUN-10",
                "L-02", WorkStatus.REJECTED),
        new WorkOutcome("BAT-10", "RUN-10",
                "L-02", WorkStatus.REJECTED),
        new WorkOutcome("BAT-10", "RUN-10",
                "L-99", WorkStatus.SUCCESS));

BatchReconciliation report =
        new BatchReconciler().reconcile(original, received);

// report.missingLineIds()     == [L-03]
// report.unexpectedLineIds()  == [L-99]
// report.duplicateLineIds()   == [L-02]
// report.structurallyComplete()== false
// report.allSucceeded()       == false
~~~

**Điều cần suy ra:** có ba input và bốn output không cho phép kết luận batch đã xử lý hết. Trường hợp này có **ba loại chênh lệch độc lập**: một dòng thiếu, một ID thừa và một ID trùng.

## 7. Unit test JUnit 5 cho thuật toán đối chiếu

### 7.1. Fixture dùng chung

~~~java
import java.util.List;

final class BatchFixtures {
    static BatchRequest threeLines() {
        return new BatchRequest(
                "BAT-1", "RUN-1", List.of(
                        new OrderLine("L-1", "SKU-A", 1),
                        new OrderLine("L-2", "SKU-B", 2),
                        new OrderLine("L-3", "SKU-C", 3)));
    }

    static WorkOutcome success(String lineId) {
        return new WorkOutcome(
                "BAT-1", "RUN-1", lineId, WorkStatus.SUCCESS);
    }
}
~~~

### 7.2. Đủ ba phần, dù output đến không đúng thứ tự

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BatchReconcilerSuccessTest {
    private final BatchReconciler reconciler =
            new BatchReconciler();

    @Test
    void outOfOrderResultsStillMatchTheirOriginalLines() {
        BatchReconciliation report = reconciler.reconcile(
                BatchFixtures.threeLines(),
                List.of(
                        BatchFixtures.success("L-3"),
                        BatchFixtures.success("L-1"),
                        BatchFixtures.success("L-2")));

        assertTrue(report.structurallyComplete());
        assertTrue(report.allSucceeded());
        assertTrue(report.missingLineIds().isEmpty());
        assertTrue(report.unexpectedLineIds().isEmpty());
        assertTrue(report.duplicateLineIds().isEmpty());
        assertEquals(3, report.firstStatusByLine().size());
    }
}
~~~

Với một hợp đồng **không yêu cầu output giữ nguyên thứ tự**, test này nên PASS. Nếu nghiệp vụ yêu cầu restore thứ tự input cho báo cáo, hãy tạo danh sách kết quả theo **thứ tự `original.lines()`** sau khi đối chiếu bằng ID. Không sắp xếp lại các kết quả theo thời điểm đến rồi mặc định đó là thứ tự gốc.

### 7.3. Thiếu, trùng, thừa và sai phiên

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BatchReconcilerFailureTest {
    private final BatchReconciler reconciler =
            new BatchReconciler();

    @Test
    void missingOneLineDoesNotCompleteTheBatch() {
        BatchReconciliation report = reconciler.reconcile(
                BatchFixtures.threeLines(),
                List.of(
                        BatchFixtures.success("L-1"),
                        BatchFixtures.success("L-2")));

        assertEquals(List.of("L-3"), report.missingLineIds());
        assertFalse(report.structurallyComplete());
        assertFalse(report.allSucceeded());
    }

    @Test
    void duplicateCannotCompensateForMissingLine() {
        BatchReconciliation report = reconciler.reconcile(
                BatchFixtures.threeLines(),
                List.of(
                        BatchFixtures.success("L-1"),
                        BatchFixtures.success("L-1"),
                        BatchFixtures.success("L-2")));

        assertEquals(List.of("L-3"), report.missingLineIds());
        assertEquals(List.of("L-1"), report.duplicateLineIds());
        assertFalse(report.structurallyComplete());
    }

    @Test
    void unexpectedLineIsReported() {
        BatchReconciliation report = reconciler.reconcile(
                BatchFixtures.threeLines(),
                List.of(
                        BatchFixtures.success("L-1"),
                        BatchFixtures.success("L-2"),
                        BatchFixtures.success("L-3"),
                        BatchFixtures.success("L-99")));

        assertEquals(List.of("L-99"),
                report.unexpectedLineIds());
        assertFalse(report.structurallyComplete());
    }

    @Test
    void aForeignProcessingAttemptIsNotAccepted() {
        BatchReconciliation report = reconciler.reconcile(
                BatchFixtures.threeLines(),
                List.of(
                        BatchFixtures.success("L-1"),
                        BatchFixtures.success("L-2"),
                        new WorkOutcome("BAT-1", "OLD-RUN",
                                "L-3", WorkStatus.SUCCESS)));

        assertEquals(List.of("L-3"), report.missingLineIds());
        assertEquals(List.of("BAT-1/OLD-RUN/L-3"),
                report.foreignResults());
        assertFalse(report.structurallyComplete());
    }

    @Test
    void allOutcomesPresentButOneRejectedIsNotAllSucceeded() {
        BatchReconciliation report = reconciler.reconcile(
                BatchFixtures.threeLines(),
                List.of(
                        BatchFixtures.success("L-1"),
                        new WorkOutcome("BAT-1", "RUN-1",
                                "L-2", WorkStatus.REJECTED),
                        BatchFixtures.success("L-3")));

        assertTrue(report.structurallyComplete());
        assertFalse(report.allSucceeded());
    }
}
~~~

Test cuối rất quan trọng: **đầy đủ kết quả** không có nghĩa tất cả dòng hàng được chấp nhận. Nếu nghiệp vụ cho phép rejection là một kết quả cuối hợp lệ, có thể đánh dấu batch `COMPLETED_WITH_REJECTIONS` thay vì `SUCCESS` hoặc `PENDING`.

### 7.4. Kiểm tra chất lượng input trước khi split

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;

class BatchInputValidationTest {
    @Test
    void duplicateInputLineIdIsRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                new BatchRequest("BAT-1", "RUN-1", List.of(
                        new OrderLine("L-1", "SKU-A", 1),
                        new OrderLine("L-1", "SKU-B", 2))));
    }

    @Test
    void emptyBatchHasAnExplicitValidationOutcome() {
        assertThrows(IllegalArgumentException.class, () ->
                new BatchRequest("BAT-1", "RUN-1", List.of()));
    }

    @Test
    void invalidQuantityCannotBecomeAChild() {
        assertThrows(IllegalArgumentException.class, () ->
                new OrderLine("L-1", "SKU-A", 0));
    }
}
~~~

Nếu input không hợp lệ nhưng code tự lọc các dòng trùng trước khi Splitter chạy, số child nhận được có thể vẫn khớp *input đã làm sạch*, nhưng không khớp **request gốc**. Khi normalization làm thay đổi cardinality, cần lưu rõ `originalCount`, `normalizedCount`, các ID bị loại và lý do.

## 8. Đối chiếu nội dung từng child, không chỉ danh tính

### 8.1. Identity khớp chưa chắc payload đúng

Giả sử input dòng `L-2` là `SKU-B × 2`, nhưng child được tạo thành `SKU-B × 20`. Thuật toán mục 6 chỉ kiểm tra **outcome identity**, nên có thể vẫn cho `structurallyComplete=true` nếu các status và ID đầy đủ.

Để kiểm thử độ chính xác của **Split output**, cần thêm phép so sánh dữ liệu:

~~~java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

final class SplitPayloadAssertions {
    static Map<String, WorkItem> indexChildren(
            List<WorkItem> children) {
        return children.stream().collect(Collectors.toMap(
                WorkItem::lineId,
                Function.identity(),
                (left, right) -> {
                    throw new IllegalArgumentException(
                            "Duplicate child lineId: " + left.lineId());
                }));
    }
}
~~~

Với mỗi child, kiểm tra `sku` và `quantity` so với input theo `lineId`:

~~~java
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class BatchSplitterPolicyTest {
    @Test
    void splitPreservesEveryInputLineAndBusinessLineage() {
        BatchRequest input = BatchFixtures.threeLines();
        List<WorkItem> children =
                new BatchSplitterPolicy().split(input);

        Map<String, WorkItem> byId =
                SplitPayloadAssertions.indexChildren(children);
        assertEquals(input.lines().size(), byId.size());

        for (OrderLine original : input.lines()) {
            WorkItem child = byId.get(original.lineId());
            assertEquals(input.batchId(), child.batchId());
            assertEquals(input.processingId(), child.processingId());
            assertEquals(original.sku(), child.sku());
            assertEquals(original.quantity(), child.quantity());
        }
    }
}
~~~

Với Transformer sau Splitter, có thể **chủ đích** thay đổi trường (ví dụ chuẩn hóa SKU). Khi đó không assert byte-for-byte các field đã được transform; thay vào đó, định nghĩa hàm/mapping mong đợi và kiểm tra cả **giá trị trước** và **giá trị sau**. Đối chiếu phải dựa trên hợp đồng, không phải giả định mọi output luôn y nguyên input.

### 8.2. Một phần tử input tạo nhiều output

Nếu một dòng `L-1` được chia thành ba chunk, khóa child phải thể hiện cả **parent line ID** lẫn **chunk index/ID**:

~~~text
Input parent: L-1, bytes=12

Output:
  L-1/chunk-0: bytes [0..3]
  L-1/chunk-1: bytes [4..7]
  L-1/chunk-2: bytes [8..11]
~~~

Cần kiểm tra **độ phủ, không chồng lấn, không thiếu khoảng**, checksum khi phù hợp, và chỉ tái lắp theo vị trí đã khai báo. `count=3` không chứng minh đã đủ ba khoảng nếu cả ba chunk đều chứa đoạn `[0..3]`.

## 9. Khi nào dùng checksum hoặc fingerprint đầu vào?

Với dữ liệu nhạy về chính xác (tệp, batch tài chính, dữ liệu vận chuyển), có thể lưu một **digest của biểu diễn chuẩn hóa** trước Splitter và đối chiếu sau khi tái tập hợp. Nhưng cần phân biệt:

- **Byte-level equivalence:** phục hồi chính xác chuỗi bytes ban đầu.
- **Semantic equivalence:** dữ liệu nghiệp vụ tương đương dù thứ tự JSON object fields, whitespace hoặc định dạng số thay đổi.

Checksum byte-level sẽ thất bại nếu một serializer thay whitespace hoặc field order dù dữ liệu không đổi. Còn một digest semantic phải có **hợp đồng canonicalization**: schema version, chuẩn Unicode, định dạng thời gian, thứ tự các dòng, cách biểu diễn số, các field được phép bỏ qua.

Không dùng checksum làm **bằng chứng duy nhất** rằng mọi handler downstream đã thành công. Nó có thể chứng minh dữ liệu tái lắp khớp, không chứng minh side effect đã commit hoặc không có duplicate ngoài hệ thống.

## 10. Splitter trong Spring Integration Java DSL

### 10.1. Wiring flow tách batch thành các phần

Ta triển khai:

~~~mermaid
flowchart LR
    P[Batch Publisher] --> I[(batch.input)]
    I --> S[Splitter BatchRequest → WorkItem]
    S --> C[(work.items)]
    C --> H[Probe handler]
    H --> O["Captured children + headers"]
~~~

Các child ở đây **được ghi nhận bởi một handler kiểm thử một chiều**; flow chưa tạo `WorkOutcome` hoặc Aggregator. Điều này giúp test **Split output** không bị trộn với lỗi xử lý nghiệp vụ.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

record CapturedChild(
        WorkItem item,
        Object correlationId,
        Integer sequenceNumber,
        Integer sequenceSize) {}

final class ChildProbe {
    final List<CapturedChild> captured =
            new CopyOnWriteArrayList<>();

    void capture(WorkItem item, Map<String, Object> headers) {
        Integer sequenceNumber = numberAsInteger(
                headers.get("sequenceNumber"));
        Integer sequenceSize = numberAsInteger(
                headers.get("sequenceSize"));

        captured.add(new CapturedChild(
                item,
                headers.get("correlationId"),
                sequenceNumber,
                sequenceSize));
    }

    private static Integer numberAsInteger(Object number) {
        return number instanceof Number value
                ? value.intValue() : null;
    }
}

@Configuration
@EnableIntegration
class SplitBatchConfiguration {

    @Bean(name = "batch.input")
    MessageChannel batchInput() {
        return new DirectChannel();
    }

    @Bean(name = "work.items")
    MessageChannel workItems() {
        return new DirectChannel();
    }

    @Bean
    BatchSplitterPolicy splitterPolicy() {
        return new BatchSplitterPolicy();
    }

    @Bean
    ChildProbe childProbe() {
        return new ChildProbe();
    }

    @Bean
    IntegrationFlow splitBatch(BatchSplitterPolicy policy) {
        return IntegrationFlow.from("batch.input")
                .split(BatchRequest.class, policy::split)
                .channel("work.items")
                .get();
    }

    @Bean
    IntegrationFlow captureWorkItems(ChildProbe probe) {
        return IntegrationFlow.from("work.items")
                .handle(WorkItem.class, (item, headers) -> {
                    probe.capture(item, headers);
                    return null; // Handler cuối, không phát reply.
                })
                .get();
    }
}
~~~

**Giải thích các quyết định thiết kế:**

- `.split(BatchRequest.class, policy::split)` đưa input qua phương thức trả một `List<WorkItem>`; Splitter tạo từng child message từ các phần tử.
- `BatchSplitterPolicy` giữ logic mapping độc lập hạ tầng, đã có unit test về nội dung từng child.
- `work.items` là `DirectChannel`, nên handler probe chạy đồng bộ trong demo. Khi đổi thành queue/executor, phải chờ tín hiệu xử lý trong test.
- `ChildProbe` chụp payload và metadata của message tại **ngay sau Splitter**; chưa đo kết quả xử lý nghiệp vụ.
- Các tên `correlationId`, `sequenceNumber`, `sequenceSize` là header phổ biến phục vụ sequence/group của Spring Integration. Khi dùng Splitter khác, kiểu output khác hoặc thay cấu hình sequence, cần kiểm tra **header thực có** và semantics từng phiên bản.

### 10.2. Header sequence và correlation có nghĩa gì?

Với Splitter trả một collection có số phần tử đã biết, Spring Integration thường gắn metadata nhóm phục vụ việc gom lại, gồm:

| Header | Mục đích | Không nên suy ra |
|---|---|---|
| `correlationId` | Liên kết các message được chia từ một message nguồn. | Nó chính là business `batchId` trong mọi trường hợp. |
| `sequenceNumber` | Vị trí một phần trong sequence. | Đây là business `lineId` ổn định qua mọi replay. |
| `sequenceSize` | Kích thước nhóm/sequence theo cấu hình và loại Splitter. | Mọi Splitter streaming đều biết kích thước chính xác. |
| `MessageHeaders.ID` | Định danh từng Spring message. | Đây là cùng ID cho tất cả child hoặc là ID bền vững qua broker. |

Các header sequence chỉ có ý nghĩa nếu được **áp dụng và giữ lại** theo cấu hình của Splitter và các adapter liên quan. Với `Iterator`/streaming hoặc message producer không biết trước số phần tử, `sequenceSize` có thể không biểu diễn được tổng cuối cùng như `List` hữu hạn. Với một số flow, sequence headers còn có thể bị thay đổi bởi bước split lồng nhau hoặc các thành phần tương quan khác.

**Thực hành tốt:** dùng `batchId`/`processingId`/`lineId` cho đối chiếu nghiệp vụ, và dùng correlation/sequence của Spring Integration đúng mục đích của hạ tầng. Không thay cái này bằng cái kia mà không kiểm tra.

### 10.3. Unit/integration test đừng phụ thuộc duy nhất vào header

Ta muốn kiểm tra hai lớp:

1. **Payload:** đúng tập line ID, đúng SKU/quantity, đúng batch/processing ID.
2. **Message metadata:** các child được gắn correlation và sequence hợp lý theo hợp đồng Splitter cụ thể.

Nếu một adapter sau Splitter bỏ mất `correlationId`, payload có thể vẫn đầy đủ trong worker nhưng Aggregator dùng header đó không gom được. Ngược lại, có `correlationId` không chứng minh payload không bị biến đổi sai.

## 11. JUnit integration test cho Splitter

### 11.1. Test ba phần tử được phát đủ, đúng nội dung

~~~java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(SplitBatchConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class SplitBatchIntegrationTest {

    @Autowired
    @Qualifier("batch.input")
    private MessageChannel input;

    @Autowired
    private ChildProbe probe;

    @Test
    void splitterProducesOneChildPerOriginalLine() {
        BatchRequest batch = BatchFixtures.threeLines();
        boolean sent = input.send(
                MessageBuilder.withPayload(batch).build(), 1_000);

        assertTrue(sent);
        assertEquals(batch.lines().size(), probe.captured.size());

        Map<String, WorkItem> byLineId = probe.captured.stream()
                .map(CapturedChild::item)
                .collect(Collectors.toMap(
                        WorkItem::lineId,
                        Function.identity()));

        for (OrderLine original : batch.lines()) {
            WorkItem child = byLineId.get(original.lineId());
            assertEquals(batch.batchId(), child.batchId());
            assertEquals(batch.processingId(), child.processingId());
            assertEquals(original.sku(), child.sku());
            assertEquals(original.quantity(), child.quantity());
        }
    }

    @Test
    void singleLineProducesExactlyOneChild() {
        BatchRequest batch = new BatchRequest(
                "BAT-ONE", "RUN-ONE",
                List.of(new OrderLine("L-ONLY", "SKU-ONE", 1)));

        assertTrue(input.send(
                MessageBuilder.withPayload(batch).build(), 1_000));
        assertEquals(1, probe.captured.size());
        assertEquals("L-ONLY",
                probe.captured.get(0).item().lineId());
    }
}
~~~

**Vì sao dùng `@DirtiesContext`?** `ChildProbe` là bean lưu state; mỗi test cần trạng thái độc lập hoặc reset có kiểm soát. Test không nên phụ thuộc test nào chạy trước. Khi nhiều test chạy song song, phải tránh chia sẻ probe/context mà không có cơ chế cô lập thích hợp.

### 11.2. Test correlation và sequence

Trong cấu hình **Splitter trả `List` và sequence metadata được bật**, ta mong các child cùng thuộc một group và có thứ tự sequence hợp lệ.

~~~java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(SplitBatchConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class SplitSequenceMetadataTest {

    @Autowired
    @Qualifier("batch.input")
    private MessageChannel input;

    @Autowired
    private ChildProbe probe;

    @Test
    void finiteListCarriesSequenceInformation() {
        assertTrue(input.send(
                MessageBuilder.withPayload(
                        BatchFixtures.threeLines()).build(), 1_000));

        assertEquals(3, probe.captured.size());

        Set<Object> groups = probe.captured.stream()
                .map(CapturedChild::correlationId)
                .collect(Collectors.toSet());

        assertEquals(1, groups.size());
        assertNotNull(probe.captured.get(0).correlationId());
        assertEquals(Set.of(1, 2, 3),
                probe.captured.stream()
                        .map(CapturedChild::sequenceNumber)
                        .collect(Collectors.toSet()));
        assertTrue(probe.captured.stream().allMatch(
                child -> Integer.valueOf(3)
                        .equals(child.sequenceSize())));
    }
}
~~~

Đây là một **expectation test** cho flow đang dùng. Nếu tùy chọn `applySequence` hoặc loại splitter được thay đổi, test phải phản ánh contract thực được phê duyệt. Không “sửa cho xanh” bằng cách bỏ mọi assertion về metadata khi phía sau còn Aggregator phụ thuộc chính các header này.

### 11.3. Test hai batch không bị trộn kết quả

Một lỗi tương quan chỉ hiện ra khi có hơn một batch:

~~~text
BAT-A / RUN-A: L-1, L-2
BAT-B / RUN-B: L-1, L-2
~~~

Hai batch có thể **dùng cùng line ID cục bộ**, nhưng `batchId` và `processingId` khác nhau. Trong test, gửi cả hai input vào Splitter và khẳng định:

- Mỗi child giữ đúng `batchId` và `processingId` từ input tương ứng.
- Không trộn metadata của batch A sang batch B.
- Reconciler nhận outcomes của batch B trong group A phải báo **foreignResults**, không tính vào `expected` của A.
- Nếu dùng Aggregator dựa trên correlation header, hai batch phải có group key khác nhau hoặc được cấu hình grouping tương ứng.

Điều này đặc biệt quan trọng khi nhiều producer cùng tạo `lineId=1` hoặc dùng sequence number `1,2,3` giống nhau.

### 11.4. Nếu output đi qua executor

Ví dụ ở phần 10 dùng `DirectChannel`, nên probe đã được gọi khi `send` thành công trong điều kiện không lỗi. Nếu đổi sang `ExecutorChannel`/`QueueChannel`, **không** assert counter ngay sau `send` như một quy tắc chung.

Dùng `CountDownLatch`/await có timeout hoặc một `BlockingQueue<CapturedChild>` trong test handler, đợi các phần tử xuất hiện rồi mới kiểm tra; luôn cleanup executor/poller và hạn chế test dựa vào `Thread.sleep`. Vẫn cần kiểm tra negative cases: consumer lỗi, queue đầy, duplicate do retry, timeout và message đến trễ.

## 12. Không nên coi Aggregator mặc định là đối chiếu đầy đủ

### 12.1. Aggregator là cơ chế gom, reconciliation là hợp đồng nghiệp vụ

Một flow có thể nối:

~~~mermaid
flowchart LR
    I[BatchRequest] --> S[Splitter]
    S --> W[Process each WorkItem]
    W --> A[Aggregator]
    A --> R[BatchResult]
    R --> V[Business Reconciler]
~~~

Aggregator của Spring Integration có thể dùng correlation và sequence headers để tập hợp các message thuộc cùng nhóm, tùy release strategy và message group store. Nhưng:

- **Group đã release** không tự chứng minh mỗi business line ID xuất hiện đúng một lần.
- **Sequence metadata** có thể bị đổi/mất qua Transformer/adapter hoặc split lồng nhau.
- **Một handler fail** có thể không phát message reply, làm group chờ đến timeout.
- **Một Filter drop child** có thể làm `sequenceSize` ban đầu không còn phù hợp với số message đến.
- **Redelivery/duplicate** cần chính sách dedupe phù hợp, không chỉ so `messageCount`.

Đối chiếu output với input ban đầu vẫn cần **một snapshot input hoặc expected IDs** được lưu/đưa vào group hợp lệ.

### 12.2. Đừng dùng correlationId như business line ID

Các child trong cùng group có thể mang cùng `correlationId`; nếu Reconciler dùng header này làm khóa duy nhất của từng phần, nó sẽ tưởng tất cả là **một dòng**. Ngược lại, nếu group theo mỗi `lineId`, ba dòng khác nhau không gom về cùng batch.

Phân tách trách nhiệm:

~~~text
correlationId / processingId: "Những message nào cùng một nhóm?"
lineId:                     "Đây là phần tử nào của nhóm?"
sequenceNumber:             "Vị trí của phần tử theo cơ chế sequence?"
attemptId / deliveryId:     "Đây là lần giao/xử lý nào?"
~~~

Khi dùng `MessageGroupStore`, cần kiểm tra **khóa group, release strategy, group expiration và state cleanup**. Nếu cùng business batch được replay mà còn group cũ, message mới có thể bị gom nhầm nếu reuse correlation không có policy rõ.

### 12.3. Thứ tự của output sau Aggregator

Các message có thể được xử lý song song và đến theo thứ tự khác nhau. Nếu báo cáo kết quả phải hiển thị theo đúng dòng đầu vào, hãy:

1. Giữ `lineId` hoặc `originalIndex` trong WorkItem.
2. Xác minh đầy đủ/không trùng/không thừa.
3. Sắp xếp kết quả theo **thứ tự original** sau reconciliation.
4. Không dùng thứ tự ngẫu nhiên trong `HashMap`, thời điểm arrival hay thứ tự hoàn tất handler làm thứ tự nghiệp vụ.

### 12.4. Khi một phần là REJECTED

Nếu `WorkOutcome(L-2, REJECTED)` đã được lưu, câu hỏi nghiệp vụ là: cần chờ `L-2` success hay chỉ cần biết nó đã được đánh giá và từ chối?

- Với hợp đồng “mỗi dòng có **kết quả cuối cùng**”, `REJECTED` có thể đóng một vị trí trong group; batch hoàn tất với trạng thái `COMPLETED_WITH_REJECTIONS`.
- Với hợp đồng “mọi dòng phải **thành công**”, batch không thể coi `allSucceeded=true`; có thể cần bù trừ/từ chối toàn batch.
- Nếu Filter **im lặng drop `L-2`**, group cần một cách biết nó bị loại; nếu không, chỉ thấy thiếu message và chờ đến timeout.

Không áp dụng một release strategy dựa trên số lượng khi điều kiện thành công yêu cầu kiểm tra business status chi tiết.

## 13. Timeout, retry, duplicate và kết quả đến muộn

### 13.1. Phân loại trạng thái mỗi phần

Một mô hình thực tế có thể phân biệt:

| Trạng thái | Ý nghĩa | Có nên xem là outcome cuối? |
|---|---|---|
| `PENDING` | Child đã được dispatch/queued nhưng chưa có kết quả. | Chưa. |
| `IN_PROGRESS` | Worker đã bắt đầu xử lý. | Chưa. |
| `SUCCESS` | Đã hoàn thành theo hợp đồng của worker. | Có. |
| `REJECTED` | Dữ liệu hợp lệ nhưng business policy từ chối. | Có nếu contract định nghĩa như vậy. |
| `FAILED_RETRYABLE` | Lỗi tạm thời, còn khả năng thử lại. | Chưa, khi vẫn có retry. |
| `FAILED_FINAL` | Không còn retry; có kết quả thất bại cuối. | Có, nhưng không phải thành công. |
| `TIMED_OUT` | Quá deadline, kết quả không đến hoặc outcome không chắc chắn. | Cần contract xử lý riêng. |

`WorkStatus` trong code mục 5 chỉ có ba giá trị để tập trung vào reconciliation. Trạng thái vận hành chi tiết hơn nên được thiết kế ở **lớp xử lý/retry**, không ép mọi trạng thái trung gian thành một `WorkOutcome` cuối quá sớm.

### 13.2. Không đếm mỗi delivery là một kết quả độc lập

Ví dụ broker giao lại cùng phần:

~~~text
eventId=EVENT-1, processingId=RUN-1, lineId=L-1

delivery #1 -> Worker xử lý, commit thành công
             -> ack bị mất
delivery #2 -> Worker nhận lại cùng message
~~~

Nếu cả hai delivery đều tạo outcome và Aggregator chỉ đếm hai message, hệ thống có thể giải phóng group sai. Cần:

- Một **business processing key** ổn định, ví dụ `processingId + ":" + lineId`.
- Một **delivery/attempt ID** khác để truy vết mỗi lần giao.
- Idempotency hoặc deduplication ở nơi tạo side effect.
- Policy khi nhận nhiều outcome của cùng business key.
- Kiểm thử kết quả trùng, kể cả hai outcome có status khác nhau.

**Không nên dùng `MessageHeaders.ID` làm idempotency key duy nhất:** redelivery/rebuild message có thể làm ID thay đổi, còn cùng ID không chứng minh side effect chưa chạy. Khóa phải gắn với **operation nghiệp vụ**.

### 13.3. Timeout không chứng minh child chưa xử lý

~~~mermaid
sequenceDiagram
    participant A as Aggregator
    participant W as Worker L-3
    participant D as Database
    A->>W: Chờ outcome L-3
    W->>D: Ghi kết quả
    D-->>W: Commit thành công
    Note over W,A: Network chậm / reply thất lạc
    A--xA: Deadline hết, đánh dấu missing/timeout
    W-->>A: Outcome L-3 đến muộn
~~~

Trong sơ đồ, `L-3` **không hẳn chưa xử lý** dù Reconciler ở thời điểm deadline thấy thiếu outcome. Tùy contract:

1. Mark batch `TIMED_OUT / PARTIALLY_OBSERVED` và cho phép reconciliation lại.
2. Kiểm tra trạng thái ở hệ thống đích trước khi retry để tránh duplicate side effect.
3. Đưa late outcome vào đường xử lý riêng: cập nhật report có version, bỏ qua theo policy hoặc tạo sự kiện điều chỉnh.
4. Dọn message group store sau expiry; không để group chờ vô hạn.
5. Truy nguyên cả **deadline của batch** và **deadline của từng worker**.

### 13.4. Retry chỉ phần lỗi hay retry toàn batch?

Giả sử ba dòng:

~~~text
L-1 SUCCESS
L-2 FAILED_RETRYABLE
L-3 SUCCESS
~~~

**Retry toàn batch** có nguy cơ khiến `L-1` và `L-3` chạy lại dù đã thành công. **Retry theo phần** giữ đúng `processingId`/`lineId` hoặc tạo một attempt ID mới cho `L-2`, tùy contract.

Khi retry:

- Nếu yêu cầu giữ **cùng một lần xử lý logic**, giữ `processingId` và dùng `attemptId`/`deliveryId` cho lần thử mới; dedupe các kết quả cuối.
- Nếu thực sự tạo **một lần xử lý batch mới**, tạo `processingId` mới và không nhập outcome của phiên cũ vào phiên mới.
- Không để reply của attempt cũ đến muộn ghi đè trạng thái mới theo cách không kiểm soát.
- Không coi exception retryable đồng nghĩa an toàn để gọi lại một HTTP API có side effect.

### 13.5. Khi Gateway timeout

Nếu client gửi batch qua Gateway request–reply nhưng toàn bộ batch cần xử lý nhiều giây hoặc phút, Gateway có thể timeout trước khi Reconciler nhận đủ outcome.

~~~text
HTTP/Gateway request -> Splitter -> async workers -> Aggregator
Client timeout 5s          worker L-3 completes at 7s
~~~

**Timeout của caller không tự hủy tác vụ downstream.** Nếu client retry tạo một batch mới nhưng dùng lại `batchId`, phải xác định có giữ `processingId`/operation ID cũ hay tạo phiên mới, kiểm tra idempotency và cách trả kết quả đến muộn. Với batch dài hạn, một API `202 Accepted + status endpoint` có thể phù hợp hơn một Gateway giữ thread chờ tất cả.

## 14. Message bị Filter loại hoặc lỗi khi qua Router/Transformer

### 14.1. Filter sau Splitter có thể làm thay đổi số message đến Aggregator

~~~mermaid
flowchart LR
    B["Batch 3 lines"] --> S[Splitter]
    S --> L1[L-1]
    S --> L2[L-2]
    S --> L3[L-3]
    L1 --> F{Filter}
    L2 --> F
    L3 --> F
    F -->|true| H[Process]
    F -->|false| D[Discard / rejection flow]
    H --> A[Aggregator]
    D -. outcome REJECTED nếu thiết kế .-> A
~~~

Nếu Filter loại `L-2` mà không tạo outcome, Aggregator mong đủ ba có thể **không bao giờ thấy message thứ ba**. Không khắc phục bằng cách đặt `sequenceSize=2` một cách tùy tiện sau khi các child đã phát. Cần một trong các hợp đồng:

- Filter phát `WorkOutcome(REJECTED)` cho dòng bị loại.
- Planner tính trước tập eligible và chỉ split phần đó, đồng thời ghi rejected IDs để đối chiếu với input gốc.
- Release strategy/timeout nhận biết drop và chính sách partial success.

**Không bao giờ tuyên bố đủ ba dòng chỉ vì Aggregator nhận đủ hai dòng được Filter cho qua.** Phải biết rằng dòng thứ ba đã bị loại có chủ đích.

### 14.2. Transformer có thể làm mất lineage

Một Transformer sau Splitter có thể chỉ trả:

~~~java
// Sai nếu downstream cần lineId để đối chiếu:
String normalizeSku(WorkItem item) {
    return item.sku().trim().toUpperCase();
}
~~~

Output chỉ là `String`, không còn `batchId`/`processingId`/`lineId` trong payload. Nếu framework propagate headers, correlation có thể còn nhưng **business identity của từng phần không còn rõ**.

Một DTO mới giữ lineage:

~~~java
record NormalizedWorkItem(
        String batchId,
        String processingId,
        String lineId,
        String normalizedSku,
        int quantity) {}

NormalizedWorkItem normalize(WorkItem item) {
    return new NormalizedWorkItem(
            item.batchId(),
            item.processingId(),
            item.lineId(),
            item.sku().trim().toUpperCase(),
            item.quantity());
}
~~~

Với validation/normalization có chủ đích, test phải so sánh dữ liệu theo transformation rule thay vì yêu cầu SKU output giống input từng byte.

### 14.3. Router có thể gửi các phần tới nhánh khác nhau

Một Router theo SKU/region có thể đưa `L-1` vào handler nội địa, `L-2` vào review, `L-3` vào hệ thống đối tác. Việc đối chiếu phải gom outcome từ **tất cả các nhánh cần thiết**, không chỉ từ nhánh nhanh nhất.

~~~text
RUN-1 / L-1 -> domestic  -> SUCCESS
RUN-1 / L-2 -> review    -> PENDING
RUN-1 / L-3 -> partner   -> SUCCESS
~~~

Tại thời điểm này, reconciliation báo **L-2 chưa có outcome cuối**. Đừng mặc định nhánh review lỗi chỉ vì xử lý lâu hơn; cần deadline, SLA và trạng thái hợp lệ cho từng route.

### 14.4. Content Enricher làm child lớn hơn original

Một child `WorkItem` sau Content Enricher có thể được bổ sung `ProductInfo`, giá, tồn kho hoặc metadata. Nếu cần kiểm tra **giữ đúng input ban đầu**, hãy dùng wrapper:

~~~text
EnrichedWorkItem:
  original: WorkItem
  productInfo: ...
  enrichmentMetadata: ...
~~~

Sau bước này, **payload equality toàn object** không còn đúng giữa input và output vì enrichment là chủ đích. Hãy so sánh `enriched.original` với `WorkItem` ban đầu theo identity và field business, đồng thời kiểm tra kết quả enrich riêng theo hợp đồng.

### 14.5. Split lồng nhau

Nếu một batch được Splitter A chia thành các đơn, sau đó Splitter B chia mỗi đơn thành các line, có **hai tầng correlation/sequence**:

~~~text
Batch
  -> Order 1
       -> Line 1.1
       -> Line 1.2
  -> Order 2
       -> Line 2.1
~~~

Đừng mặc định chỉ một `correlationId`/`sequenceNumber` là đủ diễn tả đầy đủ cây nguồn. Có thể cần `batchId`, `orderId`, `lineId` và mapping giữa các tầng, hoặc quy tắc lưu original hierarchy. Khi một Splitter tạo sequence mới, cần kiểm tra header nào được giữ/thay và Aggregator ở mỗi cấp đang gom theo **đúng parent**.

## 15. Khi phải đi qua adapter hoặc broker

### 15.1. Header không phải payload

Giữa hai JVM, HTTP/Kafka/JMS/AMQP adapter có thể ánh xạ headers sang protocol theo cách khác nhau:

| Dữ liệu | Vị trí | Rủi ro |
|---|---|---|
| `batchId`, `processingId`, `lineId` | Payload business envelope | Có thể mất nếu serializer bỏ field hoặc converter sai version. |
| `correlationId`/`sequenceSize` | Spring MessageHeaders | Có thể bị mapper lọc/đổi kiểu/mất qua transport. |
| `replyChannel`/`errorChannel` | Headers nội bộ | Có thể là object channel JVM, không thể đem sang process khác nguyên dạng. |
| `MessageHeaders.ID` | Header message cụ thể | Có thể được sinh mới khi tái dựng message. |
| `trace context` | Headers theo instrumentation | Cần propagation đúng qua thread/transport. |

Nếu bên gửi có `sequenceSize=3` còn bên nhận chỉ còn payload String của một line, không thể khẳng định Aggregator phía nhận sẽ biết group gốc. Với transport có thể làm mất header, cần **schema explicit** hoặc header mapper và test round-trip.

### 15.2. Test round-trip

Một bài test end-to-end nên đi qua:

~~~text
BatchRequest
  -> Splitter (Spring Integration)
  -> Serializer / Outbound Adapter
  -> Broker / HTTP
  -> Inbound Adapter / Deserializer
  -> WorkItem
  -> Worker
  -> WorkOutcome
  -> Reconciler
~~~

Kiểm tra:

1. Mọi `WorkItem` có đúng `batchId`/`processingId`/`lineId`.
2. Kích thước/tập expected được truyền hoặc lưu ở nơi Reconciler có thể đọc.
3. Các header correlation/sequence **thực sự** được khôi phục nếu Aggregator dùng chúng.
4. Không có thay đổi vô ý về số lượng/định dạng của `quantity`.
5. Không bị trộn outcome của batch khác hoặc phiên cũ.
6. Broker redelivery không tạo thêm business success.
7. Khi một consumer lỗi, có retry/DLQ/quarantine và timeout/release policy rõ.

Không tự xem một serializer test thuần Java là bằng chứng toàn bộ adapter/broker giữ metadata. Cần ít nhất một kiểm thử ở **đúng ranh giới** mà production sử dụng.

## 16. Observability: thấy rõ input, output và chênh lệch

### 16.1. Structured events đề xuất

~~~text
event=BATCH_RECEIVED
  batchId=BAT-10 processingId=RUN-10 inputCount=3

event=SPLIT_COMPLETED
  batchId=BAT-10 processingId=RUN-10 producedCount=3

event=CHILD_PROCESSING_STARTED
  processingId=RUN-10 lineId=L-02 attempt=1

event=CHILD_OUTCOME_RECORDED
  processingId=RUN-10 lineId=L-02 status=REJECTED

event=BATCH_RECONCILED
  processingId=RUN-10 expectedCount=3
  observedUnique=2 duplicateCount=1
  missingCount=1 unexpectedCount=1
  structurallyComplete=false allSucceeded=false
~~~

Đây là **schema gợi ý do ứng dụng định nghĩa**, không phải output mặc định của Spring Integration. Để truy nguyên, log có thể thêm trace ID, channel/endpoint và reason code, nhưng tránh ghi toàn bộ payload, token hoặc thông tin cá nhân.

### 16.2. Đừng chỉ nhìn tổng số message

Các số lượng có thể khác vì những lý do hợp lệ hoặc bất thường:

| Chỉ số | Ý nghĩa |
|---|---|
| `input_batch_total` | Số batch đầu vào. |
| `input_line_total` | Tổng dòng hợp lệ kỳ vọng sau bước validation. |
| `split_child_created_total` | Số child được Splitter tạo. |
| `child_dispatched_total` | Số child đã gửi theo contract channel. |
| `child_outcome_total{status}` | Số outcome đã nhận theo status. |
| `child_duplicate_total` | Outcome/delivery trùng được phát hiện. |
| `child_missing_after_deadline_total` | Dòng chưa có kết quả khi hết deadline. |
| `batch_reconciled_total{outcome}` | Số batch complete/partial/failed. |
| `batch_group_pending` | Nhóm Aggregator còn chờ. |
| `batch_group_expired_total` | Nhóm hết hạn/được giải phóng theo policy. |

Các tên ở trên là **metric minh họa**. Không dùng `batchId`, `lineId`, `processingId` hoặc `traceId` làm metric label có cardinality cao; để các ID này trong log/tracing hoặc store có phân quyền. Nên giới hạn label vào status, component, destination hoặc các nhóm hữu hạn.

### 16.3. Message History và lineage khác nhau

**Message History** của Spring Integration giúp biết message đi qua thành phần nào khi tracking được bật. Nó không tự là:

- Snapshot input ban đầu với đầy đủ line IDs.
- Business outcome của từng worker.
- Bằng chứng side effect đã commit ở database.
- Distributed trace bền vững qua mọi broker/adapter.
- Tập expected để xác định missing/duplicate.

Để điều tra chính xác, kết hợp **Message History, correlation/trace headers, input snapshot, outcome store và reconciliation report**. Một log “Splitter chạy thành công” không đủ giải thích tại sao batch report thiếu `L-03`.

### 16.4. Tìm nguyên nhân một batch thiếu kết quả

Nếu báo cáo `missingLineIds=[L-03]`, kiểm tra theo thứ tự:

1. **Input snapshot:** `L-03` có thực sự thuộc original không?
2. **Splitter output:** có child `L-03` được tạo không?
3. **Channel/adapter:** child có được dispatch/serialize/ack theo contract không?
4. **Router/Filter:** child có bị loại hoặc gửi sang nhánh khác không?
5. **Worker:** có `STARTED`, `COMPLETED`, `FAILED` hoặc timeout không?
6. **Outcome transport:** response đã gửi nhưng bị mất/trễ/đổi ID không?
7. **Aggregator/Reconciler:** đã có group đúng, release strategy, dedupe và timeout chưa?
8. **Retry/late reply:** có một attempt khác đang chạy hoặc outcome tới sau deadline không?

Chỉ khi xác định được **mốc đầu tiên mà line bị mất dấu** mới sửa đúng thành phần. Không đổi ngẫu nhiên `sequenceSize` hoặc tăng timeout vô hạn để che vấn đề.

## 17. Ma trận kiểm thử input–output

| ID | Trường hợp | Mong đợi | Khẳng định phủ định |
|---|---|---|---|
| SP-01 | Input một line | Đúng một `WorkItem` | Không tạo child dư. |
| SP-02 | Input ba line khác nhau | Đúng ba child, đủ IDs | Không thiếu, không trùng. |
| SP-03 | Original list bị caller sửa sau khi tạo batch | Snapshot input không thay đổi | Không thay expected set ngầm. |
| SP-04 | Input `lineId` trùng | Validation exception | Không chọn ngẫu nhiên một line. |
| SP-05 | Input có quantity 0/âm | Validation exception | Không tạo child sai dữ liệu. |
| SP-06 | Batch rỗng | Theo contract bài: reject `EMPTY_BATCH` | Không để Gateway/Aggregator chờ vô hạn. |
| SP-07 | Child được xử lý sai thứ tự | Reconciliation vẫn complete khi ID đầy đủ | Không so theo arrival index. |
| SP-08 | Thiếu `L-3` | `missing=[L-3]` | Không báo complete. |
| SP-09 | `L-1` đến hai lần, `L-3` thiếu | Có duplicate và missing | Count=3 không đánh lừa. |
| SP-10 | Có `L-99` không thuộc input | Có unexpected | Không coi output lạ là hợp lệ. |
| SP-11 | Kết quả mang `processingId` cũ | Đưa vào foreign | Không ghép với phiên hiện hành. |
| SP-12 | Sai `batchId` dù processing ID giống | Foreign/mismatch | Không gộp sai batch. |
| SP-13 | Đủ IDs, mọi status SUCCESS | Complete và allSucceeded | Không có false negative. |
| SP-14 | Đủ IDs, một status REJECTED | Complete nhưng không allSucceeded | Không đánh đồng completeness và success. |
| SP-15 | Đủ IDs, một status FAILED | Complete nhưng không allSucceeded | Không báo batch business success. |
| SP-16 | Child giữ đúng lineId nhưng sai SKU/quantity | Payload integrity test fail | Không chỉ check IDs. |
| SP-17 | Splitter finite List có sequence metadata | Sequence/correlation được kiểm tra | Không bỏ test headers nếu Aggregator cần. |
| SP-18 | Child đi qua Transformer | Lineage vẫn đọc được | Không còn mỗi SKU String. |
| SP-19 | Filter drop một child | Reject outcome hoặc missing/timeout đúng policy | Không release “đủ” giả. |
| SP-20 | Một handler throw đồng bộ | Error path rõ | Không khẳng định mọi child đã chạy. |
| SP-21 | Async handler trả kết quả muộn | Deadline/late reply policy đúng | Không suy từ `send=true`. |
| SP-22 | Broker redelivery cùng child | Dedupe theo operation key | Không nhân đôi side effect. |
| SP-23 | Gateway timeout khi workers còn chạy | Trạng thái pending/late outcome rõ | Không coi timeout là cancel mọi việc. |
| SP-24 | Hai batch có cùng lineId cục bộ | Không ghép lẫn nhờ batch/processing IDs | Không chỉ group theo line ID. |
| SP-25 | Splitter lồng nhau | Giữ parent hierarchy và correlation đúng | Không trộn cấp Order/Line. |
| SP-26 | Child qua HTTP/Kafka/JMS | Payload + metadata round-trip theo contract | Không mất header silently. |
| SP-27 | Retry một child lỗi | Không retry cả batch vô ích | Không lặp side effect thành công. |
| SP-28 | One-to-many chunks | Đủ coverage, đúng offset/length | Count đúng nhưng các chunk trùng nội dung. |
| SP-29 | Streaming chưa biết số phần tử | End-of-stream/expiration policy phù hợp | Không tự chờ sequenceSize cố định sai. |
| SP-30 | Process restart khi còn pending | Recovery từ store/broker nếu contract yêu cầu | Không dựa vào queue in-memory để bảo đảm durability. |

### 17.1. Tầng kiểm thử nên triển khai

| Tầng | Nên đặt assertion | Không thể tự chứng minh |
|---|---|---|
| **Unit test Splitter policy** | Số child, IDs, original payload fields. | Dispatcher/channel có hoạt động. |
| **Unit test Reconciler** | Missing/duplicate/unexpected/foreign, success vs complete. | Broker redelivery và consumer thực. |
| **Spring Integration test** | Splitter tạo child messages, headers, channel đúng, endpoint lifecycle. | Serialization giữa hai process nếu không qua adapter. |
| **Adapter integration test** | Header mapping, encoding, transport retry/ack, data round-trip. | Business side effect đã commit nếu chỉ gửi mock. |
| **System/end-to-end test** | Bắt đầu từ batch input đến outcome/report, timeout, retry, recovery. | Mọi failure mode trên production ở mọi thời điểm. |

Tránh để một unit test “xanh” bị hiểu là mọi thành phần phía sau đã đúng. Bài học tập trung vào phép đối chiếu có thể chạy độc lập, sau đó phải có test đi qua **đúng ranh giới mà message có nguy cơ bị mất**.

## 18. Những sai lầm thường gặp

| Hiểu nhầm | Hậu quả | Cách đúng |
|---|---|---|
| “Số output bằng số input thì chắc chắn đủ.” | Duplicate che missing. | So sánh multiset theo identity. |
| “Output đến theo đúng thứ tự input.” | Báo sai khi chạy song song. | Match bằng line ID, restore order nếu cần. |
| “Message ID là ID của dòng hàng.” | Không bền qua rebuild/adapter. | Dùng business `lineId` + `processingId`. |
| “Một outcome `REJECTED` là missing.” | Báo thiếu sai dù đã có kết quả cuối. | Tách completeness khỏi allSucceeded. |
| “Aggregator release thì toàn batch thành công.” | Release dựa count nhưng vẫn có status FAILED hoặc duplicate. | Chạy business reconciliation sau gather. |
| “Filter drop một phần thì Aggregator tự biết.” | Group chờ hoặc release không đúng. | Phát rejection outcome hoặc release/expected policy rõ. |
| “`correlationId` thay được `lineId`.” | Tất cả child cùng group bị coi là một dòng. | Group key và item key có trách nhiệm khác nhau. |
| “`sequenceNumber` không bao giờ đổi.” | Split lồng nhau/adapter khiến metadata đổi. | Kiểm tra propagation và tầng sequence. |
| “`List.copyOf` deep-copy mọi child.” | Mutable element vẫn có thể thay đổi. | Defensive copy phù hợp. |
| “Một child có đúng lineId là payload luôn đúng.” | Quantity/SKU bị biến đổi sai. | So các trường dữ liệu theo contract. |
| “Async `send` thành công nghĩa là xử lý xong.” | Báo batch complete sớm. | Theo dõi processing outcome độc lập. |
| “Timeout nghĩa là worker chưa commit.” | Retry gây side effect trùng. | Reconcile/requery trạng thái và idempotency. |
| “Retry toàn batch luôn đơn giản và an toàn.” | Chạy lại các phần đã thành công. | Retry theo phần hoặc policy replay rõ. |
| “Batch rỗng tự cho ra một reply empty.” | Gateway có thể chờ hoặc flow không phát message. | Quy định zero-child semantics rõ. |
| “Message History là báo cáo đối chiếu.” | Thiếu original snapshot và business outcome. | Lưu input expected IDs và result statuses. |
| “Qua broker mọi headers Spring còn nguyên.” | Aggregator mất correlation/sequence. | Header mapper/serializer contract và integration test. |
| “Kết quả lạ chỉ cần bỏ qua.” | Có thể che ghép nhầm tenant/batch. | Báo foreign/unexpected, audit, xử lý bảo mật. |
| “Cứ tăng timeout là hết missing.” | Che queue backlog, retry storm hoặc cấu hình sai. | Tìm hop đầu tiên mất dấu, sửa đúng nguyên nhân. |

## 19. Bài tập thực hành

1. **Đối chiếu 1→N:** tạo `BatchRequest` ba dòng, dùng `BatchSplitterPolicy`; kiểm tra đủ ba `WorkItem` với ID/SKU/quantity chính xác.
2. **Duplicate input:** cố ý tạo hai dòng cùng `lineId`, xác minh constructor từ chối; giải thích vì sao không thể dùng một `Map` để “sửa” dữ liệu trùng mà không báo.
3. **Kết quả đến sai thứ tự:** tạo outcomes theo thứ tự `L-3, L-1, L-2`; kiểm tra reconciliation vẫn complete/allSucceeded.
4. **Count đánh lừa:** tạo outcomes `L-1, L-1, L-2` khi input có `L-1, L-2, L-3`; chứng minh thiếu `L-3` và duplicate `L-1`.
5. **Unexpected:** thêm `L-99` vào outcomes; test report không cho batch complete dù mọi input ID cũng có đủ.
6. **Foreign result:** cho outcome của `RUN-OLD` đến `RUN-NEW`; chứng minh không được dùng kết quả cũ thay một line còn thiếu.
7. **Business rejection:** trả đủ outcomes nhưng có `REJECTED`; viết business status `COMPLETED_WITH_REJECTIONS` khác `SUCCESS`.
8. **Spring Integration DSL:** dựng `SplitBatchConfiguration`, gửi một batch và kiểm tra số message chụp tại `work.items`.
9. **Sequence headers:** kiểm tra `correlationId`, `sequenceNumber`, `sequenceSize` của Splitter hữu hạn; thử thay configuration/streaming và giải thích khác biệt.
10. **Transformer:** chuyển SKU thành uppercase, giữ `lineId`/`processingId`; kiểm tra input snapshot còn truy xuất được và output khớp transformation rule.
11. **Filter:** bỏ một child `L-2`; so sánh phương án discard im lặng với phát `WorkOutcome(REJECTED)` cho Aggregator.
12. **Aggregation:** nối child worker với Aggregator, thêm duplicate và lỗi một nhánh; thiết kế release strategy và group expiration trước khi gọi Reconciler.
13. **Retry:** mô phỏng `L-2` thất bại hai lần rồi thành công; dùng attempt ID để dedupe, không tính ba kết quả cuối khác nhau.
14. **Timeout:** cho `L-3` đến sau deadline. Quy định trạng thái batch lúc timeout và cách xử lý late outcome.
15. **Hai batch đồng thời:** tạo hai `BatchRequest` có cùng line IDs nhưng processing ID khác. Chứng minh outcomes không bị trộn.
16. **Split lồng nhau:** chia batch thành order, rồi order thành line; dùng IDs cấp batch/order/line để dựng lại đúng cây.
17. **One-to-many:** chia một binary payload thành chunk offsets; kiểm tra mọi byte được bao phủ đúng một lần, không thiếu và không trùng.
18. **Kafka/HTTP round-trip:** gửi `WorkItem` qua serializer/adapter thật, kiểm tra các ID và sequence headers cần thiết không mất.
19. **Observability:** tạo các sự kiện `BATCH_RECEIVED`, `SPLIT_COMPLETED`, `CHILD_OUTCOME_RECORDED`, `BATCH_RECONCILED`; truy nguyên một missing line.
20. **Tính bền vững:** giả lập crash khi một child đang queued; so sánh queue in-memory với durable store/broker, xây dựng replay không tạo duplicate side effect.

### Checklist hoàn thành bài thực hành

Một implementation đáng tin cậy nên trả lời được:

- Có **snapshot input đúng thời điểm** và tập ID kỳ vọng không?
- Có phân biệt output **ngay sau Splitter** với outcome sau xử lý không?
- Khi kết quả bị đổi thứ tự, có thể đối chiếu không?
- Có tìm thấy missing, duplicate, unexpected và foreign results không?
- Có phân biệt batch structurally complete với business success không?
- Khi timeout/retry, có biết phần nào đã thực sự hoàn tất hoặc còn không chắc chắn không?
- Có thể đi từ một `lineId` trong báo cáo về đúng original `OrderLine` không?
- Có dữ liệu để debug một message qua Router, Filter, Transformer và adapter không?

## 20. Câu hỏi tự kiểm tra

**Câu 1:** Input có ba line ID `A, B, C`; outputs `A, A, B`. Số output bằng input, có complete không?  
**Không.** `C` thiếu, `A` trùng. Cần so multiset theo ID, không chỉ đếm.

**Câu 2:** Input `A, B, C`; outcomes `C, A, B` đến theo thứ tự đảo. Có thiếu message không?  
**Không**, nếu identity và trạng thái đầy đủ. Thứ tự arrival không mặc nhiên mang ý nghĩa nghiệp vụ.

**Câu 3:** Một batch nhận đủ ba outcomes nhưng `B=REJECTED`. Có complete không, có allSucceeded không?  
**Có thể structurally complete nhưng không allSucceeded**, theo hợp đồng một outcome cuối cho mỗi line.

**Câu 4:** Có thể dùng `MessageHeaders.ID` để nhận diện một dòng hàng xuyên mọi adapter và retry không?  
**Không nên.** Message ID có thể thay khi tạo lại message; dùng business key ổn định như `processingId + lineId`.

**Câu 5:** `correlationId` và `sequenceNumber` có cùng ý nghĩa không?  
**Không.** Correlation dùng nhóm các message liên quan; sequence number dùng vị trí trong một sequence theo semantics tương ứng.

**Câu 6:** Splitter trả ba child có nghĩa cả ba HTTP calls xuống downstream thành công chưa?  
**Chưa.** Đó mới là mốc tạo/phát child, chưa phải kết quả xử lý của từng handler.

**Câu 7:** Một Filter loại message con thứ hai. Aggregator mặc định có chắc biết phải chờ hai thay vì ba không?  
**Không.** Phải có release/expected-set policy hoặc phát rejection outcome riêng.

**Câu 8:** Vì sao cần `processingId` dù đã có `batchId`?  
**Vì** cùng một business batch có thể được replay/chạy lại; outcomes của lần cũ không được tự động gộp vào lần mới.

**Câu 9:** Một outcome timeout rồi đến muộn có chứng minh worker chưa commit không?  
**Không.** Timeout có thể chỉ do reply chậm/mất; cần trạng thái downstream và chính sách late reply.

**Câu 10:** Output mang đúng `lineId` nhưng khác `quantity` có được coi đối chiếu thành công không?  
**Không**, nếu hợp đồng yêu cầu bảo toàn quantity. Reconciler ID phải được bổ sung payload integrity test.

**Câu 11:** Khi Splitter tạo một `List` hữu hạn, test có nên kiểm tra sequence metadata không?  
**Có**, nếu flow dùng metadata đó, đặc biệt cho Aggregator; cần xác minh semantics/cấu hình thực của phiên bản Spring Integration.

**Câu 12:** Đổi `QueueChannel` thành `DirectChannel` có làm thay đổi ý nghĩa `send` không?  
**Có thể.** Đồng bộ và bất đồng bộ khác nhau về mốc accepted/processed; assertion phải phù hợp execution model.

**Câu 13:** Một child bị retry ba lần có nên được coi là ba kết quả nghiệp vụ không?  
**Không mặc định.** Phân biệt attempt/delivery với outcome cuối và dùng deduplication/idempotency.

**Câu 14:** Có thể dùng Message History thay `BatchRequest` gốc để tính missing IDs không?  
**Không.** History chỉ phản ánh component được tracking; expected set phải có nguồn dữ liệu ban đầu hoặc snapshot tương đương.

**Câu 15:** Nếu một input line chủ đích tạo ba chunk, so sánh số dòng input và output bằng nhau có đúng không?  
**Không.** Với one-to-many, phải kiểm tra theo hợp đồng child count/offset/coverage của từng parent.

## 21. Kết luận

**Đối chiếu output với input ban đầu** là phần thiết yếu khi sử dụng **Splitter**. Với một batch được chia thành nhiều message, ta cần giữ **snapshot input**, định danh mỗi phần bằng **business lineage ổn định**, sau đó kiểm tra output theo **ID và nội dung**, không chỉ theo số lượng hoặc thứ tự đến.

Trong Spring Integration, Splitter giúp tạo và phân phối child messages; sequence/correlation headers hỗ trợ gom nhóm, còn Router, Filter, Transformer, Gateway và outbound adapter có thể làm thay đổi hành trình hoặc kết quả của từng phần. **Aggregator release không tự đồng nghĩa batch đã thành công**. Phải phân biệt completeness, business success, retry, duplicate, timeout và kết quả đến muộn.

Với module `SPRING_INTEGRATION_PATTERN`, phương pháp thực hành phù hợp là: **unit test Splitter policy → unit test Reconciler → integration test channel/headers → adapter/end-to-end test**. Kết hợp structured logging, error channel, correlation, message group expiration và idempotency để trả lời chính xác: **“Input ban đầu có những phần nào, từng phần đã đi đâu, và đã có kết quả cuối nào — còn thiếu, thừa hoặc trùng phần nào?”**
