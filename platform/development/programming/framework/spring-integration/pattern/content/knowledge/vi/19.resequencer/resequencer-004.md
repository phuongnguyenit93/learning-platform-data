# Buffer message đến sớm

## 1. Bài toán: message số 3 đến trước message số 1

Một hệ thống vận chuyển xử lý các sự kiện của cùng một lô hàng theo trình tự nghiệp vụ:

~~~text
1. SHIPMENT_CREATED
2. ITEMS_PACKED
3. HANDOVER_CONFIRMED
4. DELIVERED
~~~

Trong môi trường tích hợp, các sự kiện có thể đi qua executor, queue, HTTP gateway hoặc message broker. Nếu các worker xử lý song song hoặc đường truyền có độ trễ khác nhau, **thứ tự đến consumer có thể khác thứ tự tạo sự kiện**:

~~~text
Thứ tự nghiệp vụ:  1  2  3  4
Thứ tự đến:        3  1  4  2
~~~

Nếu handler chạy `HANDOVER_CONFIRMED` trước `SHIPMENT_CREATED`, nó có thể không tìm thấy hồ sơ lô hàng hoặc cập nhật trạng thái sai. **Resequencer** trong Enterprise Integration Patterns (EIP) xử lý tình huống này bằng cách **giữ các message đến sớm trong buffer**, đợi những phần còn thiếu rồi phát message theo thứ tự sequence.

Trong bài này, “đến sớm” không có nghĩa timestamp nhỏ hơn hay đồng hồ chạy nhanh hơn: nó có nghĩa **sequenceNumber của message lớn hơn vị trí mà nhóm đang chờ**.

~~~mermaid
flowchart LR
    I["Arrival: #3, #1, #4, #2"] --> R[Resequencer]
    R --> B["Buffer theo correlation key"]
    B --> C{Đã đủ điều kiện release?}
    C -->|Chưa| W["Chờ #2 / kiểm tra deadline"]
    C -->|Đủ| O["Output: #1 → #2 → #3 → #4"]
    O --> H[Ordered Handler]
~~~

**Mấu chốt:** Resequencer không tự biến một kênh phân tán thành “exactly-once và luôn đúng thứ tự” trong mọi hoàn cảnh. Nó cần **định danh nhóm**, **số thứ tự**, **điều kiện release**, **message store**, **quy tắc timeout/duplicate**, và các bảo đảm phù hợp khi phát ra downstream.

Bài học thuộc chương **Resequencer** trong module `SPRING_INTEGRATION_PATTERN`. Module tập trung triển khai Enterprise Integration Patterns bằng Spring Integration, xây dựng message flow ít phụ thuộc và dễ mở rộng, phối hợp Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation và kiểm thử, theo dõi các nhánh xử lý.

### Mục tiêu

Sau bài này, bạn có thể:

1. Giải thích vì sao message đến sai thứ tự và vì sao cần buffer những message “đi trước” vị trí đang chờ.
2. Phân biệt **Resequencer**, **Aggregator**, **Splitter**, **Filter**, queue FIFO và **Message Store**.
3. Thiết kế `correlationId`, `sequenceNumber`, `sequenceSize` và business identifiers cho từng group.
4. So sánh **chờ đủ cả sequence** với **release các đoạn liên tiếp đã đủ điều kiện**.
5. Cấu hình một Spring Integration flow dùng Resequencer và kiểm thử thứ tự phát message.
6. Xử lý missing sequence, duplicate, late arrival, timeout, group expiration, memory pressure và restart.
7. Quan sát đầu vào, buffer, output và lỗi để phân biệt “đang chờ” với “đã xử lý thành công”.

## 2. Resequencer hoạt động thế nào?

### 2.1. Một nhóm, nhiều vị trí trong trình tự

Mỗi message cần thuộc **một nhóm logic**, chẳng hạn các sự kiện của lô hàng `SHIP-42` trong một lần phát hành `RUN-7`:

~~~text
Group: SHIP-42 / RUN-7
sequenceSize: 4

sequenceNumber=1 -> SHIPMENT_CREATED
sequenceNumber=2 -> ITEMS_PACKED
sequenceNumber=3 -> HANDOVER_CONFIRMED
sequenceNumber=4 -> DELIVERED
~~~

Nếu message `#3` đến trước, Resequencer không thể phát nó như message đầu tiên khi hợp đồng yêu cầu thứ tự từ `#1`. Nó cần **giữ #3** và tiếp tục chờ.

### 2.2. Diễn tiến buffer với chính sách release đoạn liên tiếp

Một mô hình dễ hiểu là giữ biến `nextExpected=1`, chỉ phát những vị trí liên tục từ đó:

| Lần đến | Incoming | Buffer sau khi nhận | `nextExpected` trước release | Có thể phát |
|---|---|---|---|---|
| 1 | `#3` | `{3}` | 1 | Chưa có `#1` → không phát |
| 2 | `#1` | `{1,3}` | 1 | Phát `#1` nếu cho phép partial release |
| 3 | `#4` | `{3,4}` | 2 | Còn thiếu `#2` → chờ |
| 4 | `#2` | `{2,3,4}` | 2 | Phát `#2, #3, #4` liên tiếp |

Kết quả downstream theo chính sách này vẫn là:

~~~text
#1 -> #2 -> #3 -> #4
~~~

Tuy nhiên, **có hai kiểu release cần phân biệt**:

- **Full-sequence release:** giữ cả nhóm cho đến khi đủ điều kiện hoàn chỉnh, sau đó phát các message theo thứ tự. Với arrival `3,1,4,2`, không có output ở ba lần nhận đầu.
- **Partial-sequence release:** được phép phát một **tiền tố liên tục** đã có, ví dụ phát `#1` sau lần nhận thứ hai, rồi giữ `#3, #4` đến khi `#2` đến.

Trong Spring Integration, hành vi partial release phải được cấu hình và kiểm chứng theo phiên bản Resequencer đang dùng; **đừng xem đây là thuộc tính ngầm định của mọi Aggregator/Resequencer**. Kịch bản `3,2,1` ở bài integration test sẽ hợp lệ cho cả hai kiểu: không thể phát trước khi `#1` đến, và cuối cùng phải có thứ tự `1,2,3`.

### 2.3. “Đến sớm” khác “xử lý sớm”

Một message `#3` có thể đã được **nhận và lưu vào buffer**, nhưng chưa được **phát cho handler nghiệp vụ**. Trong log cần phân biệt:

~~~text
MESSAGE_RECEIVED  group=SHIP-42 seq=3
MESSAGE_BUFFERED  group=SHIP-42 seq=3
... waiting for seq=1,2 ...
MESSAGE_RELEASED  group=SHIP-42 seq=3
HANDLER_COMPLETED group=SHIP-42 seq=3
~~~

Đây là schema log ứng dụng minh họa, không phải output mặc định của Spring Integration. **Buffered** không đồng nghĩa **processed**, và **released** không đồng nghĩa downstream đã commit.

## 3. Resequencer khác Aggregator và queue FIFO

| Thành phần | Mục tiêu | Input/output điển hình | Có tự xử lý mất message? |
|---|---|---|---|
| **Resequencer** | Phát lại message trong thứ tự sequence phù hợp. | N message → các message ban đầu theo thứ tự. | Không; cần timeout/recovery. |
| **Aggregator** | Gom nhiều message thành một kết quả chung theo rule. | N message → một payload/nhóm kết quả. | Không; cần release/expiration policy. |
| **Splitter** | Chia payload thành nhiều message con. | Một batch → nhiều item messages. | Không; chỉ tạo các phần. |
| **FIFO queue** | Giữ thứ tự *enqueue* trong giới hạn semantics queue. | Enqueue → dequeue cùng thứ tự queue. | Không phục hồi thứ tự nghiệp vụ đã bị đảo trước enqueue. |
| **Filter** | Loại message không đáp ứng predicate. | Một message → đi tiếp hoặc bị loại. | Có thể khiến Resequencer chờ thiếu sequence. |
| **Message Store** | Lưu message/group state theo implementation. | State để các endpoint dùng. | Durability phụ thuộc loại store và transaction. |

Ví dụ queue đã nhận `3,1,2`. FIFO có thể phát đúng **3,1,2** vì đó chính là thứ tự enqueue. Nếu nghiệp vụ cần **1,2,3**, phải có cơ chế dùng sequence/correlation để reorder.

### 3.1. Có thể thay bằng sort một List không?

Nếu tất cả message đã nằm trong một `List` hoàn chỉnh, việc sort đơn giản hơn:

~~~java
events.stream()
        .sorted(java.util.Comparator.comparingInt(
                ShipmentEvent::sequenceNumber))
        .toList();
~~~

Resequencer trở nên hữu ích khi các message **đến rải rác theo thời gian**, có thể từ các thread/queue khác nhau, và chưa biết message nào sẽ đến tiếp. Lúc đó cần state của nhóm, điều kiện release, timeout và giám sát buffer.

### 3.2. Resequencer không thay thế transaction nghiệp vụ

Ngay cả khi `#1, #2, #3` được phát đúng thứ tự, một downstream handler có thể lỗi ở `#2` trong khi `#3` đã được dispatch tiếp ở một cơ chế bất đồng bộ. “Đã phát có thứ tự” **không tự bảo đảm** handler đã **commit tuần tự**. Nếu nghiệp vụ cần xử lý chặt chẽ lần lượt, phải kiểm tra thêm channel, concurrency của consumer, transaction boundary và quy tắc acknowledgment.

## 4. Thông tin bắt buộc để buffer an toàn

### 4.1. Correlation key: nhóm nào đang chờ?

Giả sử hai lô hàng cùng nhận `sequenceNumber=2`:

~~~text
SHIP-42 / RUN-7 / #2
SHIP-99 / RUN-3 / #2
~~~

Chúng **không được vào chung một message group**. Spring Integration thường dùng `correlationId` trong Resequencer để nhóm theo ngữ cảnh hạ tầng. Trong payload nghiệp vụ, ta nên giữ những khóa đủ phân biệt:

- `shipmentId`: thực thể nghiệp vụ.
- `runId` hoặc `streamVersion`: một sequence cụ thể, tránh trộn replay/bản phát hành mới.
- `eventId`: ID của sự kiện, có thể phục vụ deduplication/observability.
- `sequenceNumber`: vị trí trong sequence.
- `sequenceSize`: tổng số phần nếu đã biết và phù hợp với hợp đồng.

**Không mặc định `correlationId` chỉ bằng `shipmentId`** nếu cùng shipment được tái xử lý theo nhiều đợt. Một group key có thể là `shipmentId + ":" + runId`, nhưng phải bảo đảm encoding không gây va chạm và phù hợp với schema trên transport.

### 4.2. Sequence number và size

| Trường | Điều kiện ví dụ | Vì sao? |
|---|---|---|
| `sequenceNumber` | Nguyên dương, bắt đầu từ 1. | Mỗi vị trí có một ý nghĩa xác định. |
| `sequenceSize` | Nguyên dương, cố định trong cùng group. | Biết khi nào một sequence hữu hạn đã đủ. |
| `sequenceNumber <= sequenceSize` | Bắt buộc trong bài toán hữu hạn. | Tránh một vị trí nằm ngoài phạm vi. |
| Unique sequence position | Một event cho một vị trí cuối cùng. | Tránh duplicate/mâu thuẫn. |
| Group key ổn định | Không đổi qua retry và adapter. | Tránh group bị tách hoặc trộn. |

Khi sequence **không có kích thước trước** (stream dài hạn, dynamic number of fragments), `sequenceSize` có thể không biết hoặc không có giá trị hoàn chỉnh. Không áp dụng máy móc điều kiện “đủ từ 1 đến N” khi N không được xác định; cần **end-of-stream marker**, watermark, một quy tắc release khác hoặc một workflow state phù hợp.

### 4.3. Các tình huống bắt buộc phân loại

| Tình huống | Ví dụ | Cách nhìn đúng |
|---|---|---|
| Out-of-order hợp lệ | `#3` đến trước `#2`. | Giữ `#3`, chờ phần còn thiếu. |
| Missing message | `#1, #3` đến, `#2` không bao giờ xuất hiện. | Head-of-line blocking; cần deadline/recovery. |
| Duplicate pending | Nhận `#3` hai lần trước `#2`. | Không được đếm thành hai vị trí. |
| Duplicate already released | `#1` lại đến sau khi đã phát `#1`. | Policy dedupe/late delivery, không phát hai lần vô ý. |
| Inconsistent size | Cùng group một reply size=3, reply khác size=5. | Lỗi schema/group contract. |
| Foreign message | `#2` của RUN-8 vào RUN-7. | Không ghép nhầm, kiểm tra correlation. |
| Gap timeout | Đợi `#2` quá deadline. | Expiration/partial failure/quarantine. |
| Late missing message | `#2` đến sau khi group đã expire. | Chính sách late arrival rõ, không mở lại tùy tiện. |
| Consumer lỗi sau release | Message phát đúng thứ tự nhưng handler failed. | Là lỗi downstream, không phải lỗi sort. |

## 5. Ví dụ dữ liệu Java bất biến

Ta dùng **Java 17+, Spring Boot 3.x, Spring Integration 6.x** trong các ví dụ. Các type mô phỏng được hiểu là nằm cùng package; khi triển khai production, cần tách các `public` type thành file phù hợp.

~~~java
record ShipmentEvent(
        String shipmentId,
        String runId,
        String eventId,
        int sequenceNumber,
        int sequenceSize,
        String eventType) {

    ShipmentEvent {
        if (shipmentId == null || shipmentId.isBlank()
                || runId == null || runId.isBlank()
                || eventId == null || eventId.isBlank()
                || eventType == null || eventType.isBlank()
                || sequenceSize <= 0
                || sequenceNumber <= 0
                || sequenceNumber > sequenceSize) {
            throw new IllegalArgumentException(
                    "INVALID_SHIPMENT_SEQUENCE_EVENT");
        }
    }
}

record SequenceGroup(String shipmentId, String runId) {
    SequenceGroup {
        if (shipmentId == null || shipmentId.isBlank()
                || runId == null || runId.isBlank()) {
            throw new IllegalArgumentException("INVALID_GROUP_KEY");
        }
    }
}
~~~

Trong bài này, `ShipmentEvent` là một **DTO nghiệp vụ minh họa**. Trạng thái vận chuyển không được áp dụng cho hệ thống thật chỉ vì chuỗi eventType là `DELIVERED`; production còn phải kiểm tra quyền, state machine nghiệp vụ và nguồn phát sự kiện.

Một số sự kiện ví dụ:

~~~java
ShipmentEvent first = new ShipmentEvent(
        "SHIP-42", "RUN-7", "EVT-1", 1, 3, "CREATED");
ShipmentEvent second = new ShipmentEvent(
        "SHIP-42", "RUN-7", "EVT-2", 2, 3, "PACKED");
ShipmentEvent third = new ShipmentEvent(
        "SHIP-42", "RUN-7", "EVT-3", 3, 3, "HANDED_OVER");
~~~

Ở đây message có `sequenceSize=3`; sự kiện thứ tư của một lô hàng phải thuộc **một hợp đồng sequence khác** hoặc ban đầu chọn size=4. Không tự đổi size của nhóm đang chạy vì một event mới xuất hiện.

## 6. Thuật toán buffer để hiểu bản chất Resequencer

Trước khi cấu hình Spring Integration, hãy mô tả một buffer đơn giản bằng Java thuần. Mô hình này **phát các tiền tố liên tiếp đã sẵn sàng**; nó phù hợp để hiểu việc message đến sớm phải chờ vị trí còn thiếu, nhưng **không thay thế implementation của Spring Integration**, đặc biệt về message store, release strategy, transaction và error handling.

### 6.1. Dữ liệu trả về sau một lần nhận

~~~java
import java.util.List;

record BufferUpdate(
        List<ShipmentEvent> ready,
        int pendingCount,
        int nextExpected,
        boolean complete) {

    BufferUpdate {
        ready = List.copyOf(ready);
    }
}
~~~

Ý nghĩa:

- `ready`: những message đã đủ điều kiện phát **ở lần nhận này**.
- `pendingCount`: số message được giữ lại vì còn gap.
- `nextExpected`: vị trí sẽ cần tiếp theo.
- `complete`: cả sequence hữu hạn đã đi qua thứ tự từ 1 đến N trong thuật toán.

`complete` ở mức buffer **không chứng minh** handler downstream đã xử lý thành công hoặc side effect đã commit.

### 6.2. Một buffer trong bộ nhớ, tách nhóm theo key

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;

final class SequenceBuffer {

    private final Map<SequenceGroup, PendingGroup> groups =
            new HashMap<>();

    synchronized BufferUpdate accept(ShipmentEvent event) {
        Objects.requireNonNull(event, "event");

        SequenceGroup key = new SequenceGroup(
                event.shipmentId(), event.runId());

        PendingGroup state = groups.get(key);
        if (state == null) {
            state = new PendingGroup(event.sequenceSize());
            groups.put(key, state);
        }

        if (state.declaredSize != event.sequenceSize()) {
            throw new IllegalArgumentException(
                    "INCONSISTENT_SEQUENCE_SIZE");
        }
        if (state.complete) {
            throw new IllegalStateException(
                    "SEQUENCE_ALREADY_COMPLETED");
        }
        if (event.sequenceNumber() < state.nextExpected) {
            throw new IllegalStateException(
                    "DUPLICATE_OR_LATE_SEQUENCE");
        }
        if (state.pending.putIfAbsent(
                event.sequenceNumber(), event) != null) {
            throw new IllegalStateException(
                    "DUPLICATE_PENDING_POSITION");
        }

        List<ShipmentEvent> ready = new ArrayList<>();

        // Chỉ phát một đoạn liên tiếp bắt đầu từ nextExpected.
        while (true) {
            ShipmentEvent next =
                    state.pending.remove(state.nextExpected);
            if (next == null) {
                break;
            }
            ready.add(next);
            state.nextExpected++;
        }

        state.complete =
                state.nextExpected > state.declaredSize;

        return new BufferUpdate(
                ready,
                state.pending.size(),
                state.nextExpected,
                state.complete);
    }

    private static final class PendingGroup {
        final int declaredSize;
        int nextExpected = 1;
        boolean complete;
        final TreeMap<Integer, ShipmentEvent> pending =
                new TreeMap<>();

        PendingGroup(int declaredSize) {
            this.declaredSize = declaredSize;
        }
    }
}
~~~

### 6.3. Đọc từng dòng logic quan trọng

1. `SequenceGroup(shipmentId, runId)` chia các message thành những nhóm độc lập. Không gộp message có cùng số thứ tự nhưng thuộc các run khác nhau.
2. `declaredSize` chụp kích thước nhóm từ message đầu tiên và kiểm tra các message sau phải thống nhất.
3. `pending` là một `TreeMap` theo vị trí, nên biết message nào đang được giữ.
4. `putIfAbsent` phát hiện **duplicate ở vị trí chưa release** thay vì ghi đè âm thầm.
5. Nếu một vị trí đã release lại đến, `sequenceNumber < nextExpected` gây lỗi **duplicate/late**.
6. Vòng `while` chỉ phát khi tồn tại message ở `nextExpected`; nếu chờ `#2` thì `#3` dù đã đến vẫn không thể tự vượt qua.
7. `synchronized` làm thao tác đọc/sửa state và tạo `ready` nhất quán **trong một JVM và một buffer instance**.

### 6.4. Một mô phỏng cụ thể

~~~java
SequenceBuffer buffer = new SequenceBuffer();

BufferUpdate a = buffer.accept(third);
// a.ready() = []
// a.pendingCount() = 1; a.nextExpected() = 1

BufferUpdate b = buffer.accept(first);
// b.ready() = [first]
// b.pendingCount() = 1; b.nextExpected() = 2

BufferUpdate c = buffer.accept(second);
// c.ready() = [second, third]
// c.pendingCount() = 0; c.nextExpected() = 4
// c.complete() = true
~~~

Sơ đồ này dùng **partial-prefix release**; khi cấu hình full-sequence release, có thể giữ `first` trong group và phát `first, second, third` cùng lúc khi đã đủ ba message. Cả hai có thể tạo **cùng thứ tự cuối**, nhưng có latency và semantics timeout khác nhau.

### 6.5. Giới hạn thực tế của thuật toán minh họa

Mã `SequenceBuffer` có chủ đích **chưa** hỗ trợ:

- TTL, giới hạn bộ nhớ, maximum group size, eviction policy và snapshot bền vững.
- Thay đổi sequenceSize giữa chừng hoặc stream không biết N.
- Phát message theo transaction cùng với cập nhật cursor.
- Exactly-once publication sang broker hoặc cơ chế recovery sau crash.
- Late reply và idempotency khi group đã bị dọn.
- Phân biệt message trùng **cùng nội dung** với message mâu thuẫn **khác nội dung** ở cùng sequenceNumber.
- Parallel delivery của những kết quả `ready` ra downstream.

**Rủi ro cần nhớ:** `synchronized accept(...)` chỉ bảo đảm thứ tự **tính toán**. Nếu thread A nhận `ready=[#1]` rồi chưa kịp publish, thread B nhận `ready=[#2,#3]` và publish trước, downstream vẫn có thể thấy `#2` trước `#1`. Muốn bảo đảm **thứ tự publish**, cần serialize việc phát message cho từng group, thiết kế một single-writer/ordered outbox hoặc dùng endpoint và channel có contract phù hợp. Đừng tự dùng buffer này làm production resequencer chỉ vì unit test pass.

## 7. Unit test cho “message đến sớm”

### 7.1. `#3` phải được giữ cho đến khi có những vị trí trước

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SequenceBufferEarlyArrivalTest {
    private final SequenceBuffer buffer =
            new SequenceBuffer();

    private static ShipmentEvent event(int number) {
        return new ShipmentEvent(
                "SHIP-42", "RUN-7", "EVT-" + number,
                number, 3, "TYPE-" + number);
    }

    @Test
    void buffersFutureMessagesUntilMissingPredecessorArrives() {
        BufferUpdate after3 = buffer.accept(event(3));
        assertTrue(after3.ready().isEmpty());
        assertEquals(1, after3.pendingCount());
        assertEquals(1, after3.nextExpected());

        BufferUpdate after1 = buffer.accept(event(1));
        assertEquals(List.of(1),
                after1.ready().stream()
                        .map(ShipmentEvent::sequenceNumber)
                        .toList());
        assertFalse(after1.complete());

        BufferUpdate after2 = buffer.accept(event(2));
        assertEquals(List.of(2, 3),
                after2.ready().stream()
                        .map(ShipmentEvent::sequenceNumber)
                        .toList());
        assertEquals(0, after2.pendingCount());
        assertTrue(after2.complete());
    }

    @Test
    void reversedArrivalStillReleasesInOrder() {
        BufferUpdate after3 = buffer.accept(event(3));
        BufferUpdate after2 = buffer.accept(event(2));
        BufferUpdate after1 = buffer.accept(event(1));

        assertTrue(after3.ready().isEmpty());
        assertTrue(after2.ready().isEmpty());
        assertEquals(List.of(1, 2, 3),
                after1.ready().stream()
                        .map(ShipmentEvent::sequenceNumber)
                        .toList());
        assertTrue(after1.complete());
    }
}
~~~

Test thứ hai là tình huống cốt lõi của bài: **message #3 và #2 đến trước #1**, không có gì được phát trong hai lần đầu. Khi `#1` đến, cả ba đã đủ và có thể phát theo thứ tự.

### 7.2. Hai group xen kẽ không được ảnh hưởng nhau

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SequenceBufferGroupIsolationTest {
    @Test
    void twoGroupsKeepIndependentNextExpected() {
        SequenceBuffer buffer = new SequenceBuffer();

        ShipmentEvent a2 = new ShipmentEvent(
                "SHIP-A", "RUN-1", "A-2", 2, 2, "PACKED");
        ShipmentEvent b1 = new ShipmentEvent(
                "SHIP-B", "RUN-1", "B-1", 1, 2, "CREATED");
        ShipmentEvent a1 = new ShipmentEvent(
                "SHIP-A", "RUN-1", "A-1", 1, 2, "CREATED");
        ShipmentEvent b2 = new ShipmentEvent(
                "SHIP-B", "RUN-1", "B-2", 2, 2, "PACKED");

        assertTrue(buffer.accept(a2).ready().isEmpty());
        assertEquals(List.of("B-1"),
                buffer.accept(b1).ready().stream()
                        .map(ShipmentEvent::eventId).toList());
        assertEquals(List.of("A-1", "A-2"),
                buffer.accept(a1).ready().stream()
                        .map(ShipmentEvent::eventId).toList());
        assertEquals(List.of("B-2"),
                buffer.accept(b2).ready().stream()
                        .map(ShipmentEvent::eventId).toList());
    }
}
~~~

Hai group có thể **xen kẽ ở đầu ra tổng thể**, nhưng trong từng group phải giữ thứ tự. Đừng đòi toàn hệ thống phát `SHIP-A` trước toàn bộ `SHIP-B` khi nghiệp vụ không yêu cầu global ordering; điều đó làm giảm throughput và tạo head-of-line blocking không cần thiết giữa các nhóm.

### 7.3. Duplicate, inconsistent size và late position

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;

class SequenceBufferInvalidTest {
    private final SequenceBuffer buffer =
            new SequenceBuffer();

    private static ShipmentEvent e(int position, int total) {
        return new ShipmentEvent(
                "SHIP-1", "RUN-1", "EVT-" + position,
                position, total, "TYPE-" + position);
    }

    @Test
    void duplicateBufferedPositionIsRejected() {
        buffer.accept(e(3, 3));
        assertThrows(IllegalStateException.class, () ->
                buffer.accept(e(3, 3)));
    }

    @Test
    void duplicateAlreadyReleasedPositionIsRejected() {
        buffer.accept(e(1, 3));
        assertThrows(IllegalStateException.class, () ->
                buffer.accept(e(1, 3)));
    }

    @Test
    void inconsistentSequenceSizeIsRejected() {
        buffer.accept(e(2, 3));
        assertThrows(IllegalArgumentException.class, () ->
                buffer.accept(e(1, 4)));
    }

    @Test
    void sequenceNumberOutsideDeclaredRangeIsRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                e(4, 3));
    }
}
~~~

Trong production, duplicate có thể xuất hiện bình thường với broker at-least-once. **Ném exception** ở bài học giúp bắt được trường hợp nhưng **không phải chiến lược vận hành duy nhất**. Hệ thống có thể dedupe cùng operation ID, ghi metric và acknowledge duplicate hợp lệ, đồng thời báo lỗi nếu hai payload mâu thuẫn ở cùng vị trí.

## 8. Tích hợp Resequencer trong Spring Integration Java DSL

### 8.1. Kiến trúc flow

Spring Integration có **Resequencer** cho các Spring `Message` mang thông tin nhóm/sequence thích hợp. Về bản chất, nó là một dạng message group processor dùng để **reorder rồi phát message** thay vì gộp mọi payload thành một payload tổng hợp như Aggregator thông thường.

~~~mermaid
flowchart LR
    P[Message Producer] --> I[(shipment.events.in)]
    I --> R[Spring Integration Resequencer]
    R --> S[(Message Group Store)]
    S -->|Đủ điều kiện release| R
    R --> O[(shipment.events.ordered)]
    O --> H[Ordered Handler]
~~~

Mẫu này tách rõ ba trách nhiệm:

1. **Upstream** cung cấp correlation/sequence metadata đúng hợp đồng.
2. **Resequencer** quản lý nhóm, giữ message và quyết định khi nào release.
3. **Downstream** thực hiện xử lý nghiệp vụ theo thứ tự message được phát.

### 8.2. Cấu hình hai channel và một Resequencer

Ví dụ Java DSL dành cho **Java 17+ và Spring Integration 6.x**:

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

final class OrderedEventProbe {
    private final List<ShipmentEvent> observed =
            new CopyOnWriteArrayList<>();

    void record(ShipmentEvent event) {
        observed.add(event);
    }

    List<ShipmentEvent> snapshot() {
        return List.copyOf(observed);
    }
}

@Configuration
@EnableIntegration
class ShipmentResequencerConfiguration {

    @Bean(name = "shipment.events.in")
    MessageChannel incomingEvents() {
        return new DirectChannel();
    }

    @Bean(name = "shipment.events.ordered")
    MessageChannel orderedEvents() {
        return new DirectChannel();
    }

    @Bean
    OrderedEventProbe orderedEventProbe() {
        return new OrderedEventProbe();
    }

    @Bean
    IntegrationFlow reorderShipmentEvents() {
        return IntegrationFlow.from("shipment.events.in")
                .resequence()
                .channel("shipment.events.ordered")
                .get();
    }

    @Bean
    IntegrationFlow handleOrderedEvents(OrderedEventProbe probe) {
        return IntegrationFlow.from("shipment.events.ordered")
                .handle(ShipmentEvent.class, (event, headers) -> {
                    probe.record(event);
                    return null; // Terminal handler trong bài học.
                })
                .get();
    }
}
~~~

Ở cấu hình demo, `DirectChannel` giữ quá trình dispatch đồng bộ với caller. Điều này giúp test xác minh số event probe đã nhận sau khi các message đủ điều kiện release. Nhưng **buffer/group lifecycle** vẫn là trách nhiệm của Resequencer, không phải của `DirectChannel`.

Đoạn code dùng `.resequence()` trong Java DSL. Khi triển khai thực tế, hãy xác minh **API/phiên bản cụ thể** của `spring-integration-core`, cấu hình message store, release partial sequences, timeout và xử lý group expiration. Ví dụ trên **không** bổ sung durable store, không có retry/error flow sản xuất và không dùng cho workflow quan trọng mà không hoàn thiện những thành phần đó.

### 8.3. Tạo message có correlation và sequence headers

Đây là một điểm thiết yếu: Spring Integration Resequencer không thể tự suy ra “eventType=PACKED là #2” nếu bạn chỉ đưa payload mà không định nghĩa thứ tự hoặc header thích hợp.

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class ShipmentMessageFactory {

    static Message<ShipmentEvent> toMessage(
            ShipmentEvent event) {
        String correlationKey =
                event.shipmentId() + ":" + event.runId();

        return MessageBuilder.withPayload(event)
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        correlationKey)
                .setHeader(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                        event.sequenceNumber())
                .setHeader(
                        IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                        event.sequenceSize())
                .build();
    }
}
~~~

**Lưu ý:**

- `correlationId` ở đây là chuỗi được xây dựng trong **ứng dụng**. Khi dữ liệu đầu vào có dấu phân cách tự do, cần một encoding không gây va chạm, hoặc dùng ID nhóm đã được chuẩn hóa.
- `sequenceNumber` trong ví dụ là số nguyên từ 1 đến N, không phải timestamp.
- `sequenceSize` thống nhất trong cả group, tạo điều kiện cho release một sequence hữu hạn.
- Header `MessageHeaders.ID` sẽ là ID của message cụ thể; không dùng nó thay `shipmentId` hoặc `runId`.
- Nếu upstream là **Splitter** đã tạo sequence headers, không nên tự đặt lại ngẫu nhiên mà phải kiểm tra headers nào đang được giữ và có phù hợp với group cần resequence hay không.

Nếu event được chuyển qua HTTP/Kafka/JMS/AMQP, adapter có thể map header sang dạng wire khác hoặc lọc chúng. Cần test header propagation ở đúng ranh giới transport. Việc có `shipmentId` trong payload **không đủ** nếu Resequencer đang group bằng một header khác bị mất.

## 9. Integration test: message #3 và #2 bị buffer trước #1

### 9.1. Kiểm tra flow thực chứ không chỉ sort List

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(ShipmentResequencerConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ShipmentResequencerIntegrationTest {

    @Autowired
    @Qualifier("shipment.events.in")
    private MessageChannel input;

    @Autowired
    private OrderedEventProbe probe;

    private ShipmentEvent event(int number) {
        return new ShipmentEvent(
                "SHIP-42", "RUN-7", "EVT-" + number,
                number, 3, "TYPE-" + number);
    }

    private void send(ShipmentEvent event) {
        assertTrue(input.send(
                ShipmentMessageFactory.toMessage(event), 1_000));
    }

    @Test
    void earlyThirdAndSecondWaitUntilFirstArrives() {
        send(event(3));
        assertTrue(probe.snapshot().isEmpty());

        send(event(2));
        assertTrue(probe.snapshot().isEmpty());

        send(event(1));
        assertEquals(List.of(1, 2, 3),
                probe.snapshot().stream()
                        .map(ShipmentEvent::sequenceNumber)
                        .toList());
    }

    @Test
    void alreadyOrderedInputIsEventuallyReleasedInOrder() {
        send(event(1));
        send(event(2));
        send(event(3));

        assertEquals(List.of(1, 2, 3),
                probe.snapshot().stream()
                        .map(ShipmentEvent::sequenceNumber)
                        .toList());
    }
}
~~~

**Vì sao chọn arrival `3,2,1`?** Nó kiểm tra rõ yêu cầu “buffer message đến sớm” mà **không cần giả định** Resequencer có phát partial prefix khi `#1` đến trước `#3` hay không. Trước khi `#1` đến, không có tiền tố liên tục nào bắt đầu từ 1. Sau khi `#1` đến, cả nhóm đã đủ nên output có thứ tự 1,2,3.

**Giới hạn của test:** nó kiểm tra kênh và Resequencer trong một JVM, không kiểm tra broker durability, restart, timeout hoặc exactly-once. Nếu đang dùng release strategy được tùy chỉnh, xác nhận những assertion về khi nào một prefix được phát theo đúng contract.

### 9.2. Test không trộn hai shipment

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(ShipmentResequencerConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ShipmentResequencerIsolationTest {

    @Autowired
    @Qualifier("shipment.events.in")
    private MessageChannel input;

    @Autowired
    private OrderedEventProbe probe;

    private void send(String shipment, int sequenceNumber) {
        ShipmentEvent e = new ShipmentEvent(
                shipment, "RUN-1",
                shipment + "-E" + sequenceNumber,
                sequenceNumber, 2, "TYPE");
        assertTrue(input.send(
                ShipmentMessageFactory.toMessage(e), 1_000));
    }

    @Test
    void interleavedGroupsAreOrderedIndependently() {
        send("SHIP-A", 2);
        send("SHIP-B", 2);
        send("SHIP-B", 1);
        send("SHIP-A", 1);

        Map<String, List<Integer>> byShipment =
                probe.snapshot().stream().collect(
                        Collectors.groupingBy(
                                ShipmentEvent::shipmentId,
                                Collectors.mapping(
                                        ShipmentEvent::sequenceNumber,
                                        Collectors.toList())));

        assertEquals(List.of(1, 2), byShipment.get("SHIP-A"));
        assertEquals(List.of(1, 2), byShipment.get("SHIP-B"));
    }
}
~~~

Test này **không** cố gắng áp một thứ tự toàn cục giữa SHIP-A và SHIP-B. Nó chỉ bảo đảm từng nhóm có thứ tự đúng, cho phép các nhóm khác nhau chạy độc lập.

### 9.3. Vì sao dùng `@DirtiesContext`?

`OrderedEventProbe` giữ state giữa các message trong cùng Spring context; Resequencer có thể cũng giữ group state trong Message Store. Để test độc lập, dùng `@DirtiesContext` hoặc cơ chế reset rõ ràng. Không để test đầu tiên đã tạo group chưa hoàn tất rồi test sau tái sử dụng cùng group ID gây kết quả khó đoán.

### 9.4. Cấu hình partial release là một lựa chọn

Nếu nghiệp vụ muốn phát `#1` ngay khi nó đã đến, dù `#2` chưa có, có thể cân nhắc tùy chọn **release partial sequences** của Resequencer. Hình dung:

~~~text
Arrival: 3 -> 1 -> 2

Wait-for-all:
  after 3: output []
  after 1: output []
  after 2: output [1,2,3]

Contiguous partial release:
  after 3: output []
  after 1: output [1]
  after 2: output [2,3]
~~~

Khi cấu hình bằng Java DSL, hãy kiểm tra API `releasePartialSequences` và các điều kiện release được hỗ trợ bởi **phiên bản Spring Integration bạn đang chạy**. Không sao chép expectation của wait-for-all sang một cấu hình partial release hoặc ngược lại. Đặc biệt, phát prefix trước khi toàn nhóm hoàn tất làm thay đổi **ý nghĩa timeout, duplicate và group cleanup**.

### 9.5. Không kết luận nghiệp vụ từ `send=true`

Ở hai test trên, kết quả cuối được lấy từ `OrderedEventProbe` sau handler. `MessageChannel.send(...)` chỉ cho biết thao tác dispatch ở đầu vào theo semantics của channel; message `#3` có thể được Resequencer **buffer thành công** mà chưa có một `ShipmentEvent` nào được handler downstream nhận. Đó chính là hành vi đúng.

## 10. Khi message còn thiếu không bao giờ đến

### 10.1. Head-of-line blocking

Giả sử Resequencer nhận:

~~~text
Group SHIP-42/RUN-7

received = {1, 3, 4, 5}
missing  = {2}
~~~

Trong chính sách yêu cầu thứ tự tuyệt đối, message `#3` không được phát trước `#2`. Hệ quả là **một vị trí thiếu có thể giữ cả những message đã đến sau nó**. Hiện tượng này gọi là **head-of-line blocking** trong phạm vi một sequence.

~~~mermaid
flowchart LR
    B["Buffer: 3,4,5"] --> G{"nextExpected = 2"}
    G -->|Chưa có #2| WAIT["Chờ / kiểm tra deadline"]
    G -->|#2 đã đến| RELEASE["Phát 2 → 3 → 4 → 5"]
    WAIT --> TIMEOUT["Expiration / recovery"]
~~~

### 10.2. Đợi bao lâu là hợp lý?

Cần xác định deadline theo nhu cầu nghiệp vụ:

| Luồng | Kỳ vọng | Gợi ý |
|---|---|---|
| Sensor telemetry có thể mất gói | Chấp nhận một số gap với nhãn dữ liệu thiếu. | Window/watermark, gap report, chính sách partial. |
| Đơn hàng phải tạo trước khi giao | Không được phát giao hàng trước tạo đơn. | Fail closed, replay/recover message thiếu. |
| Audit log cần order đầy đủ | Không được bỏ sự kiện không giải thích. | Durable store, báo cáo missing, retention. |
| Dashboard thống kê ít nhạy | Có thể cho phép bỏ gap sau một thời gian. | Expiration và metadata mô tả gap rõ. |

**Không có timeout mặc định phù hợp cho mọi hệ thống.** Một group chờ vô hạn gây rò rỉ bộ nhớ/state; nhưng expire quá sớm có thể khiến các sự kiện hợp lệ đến chậm bị loại.

### 10.3. Group timeout khác business timeout

Tùy cách cấu hình, Spring Integration có khả năng quản lý **group timeout, group expiration, discard/expired group handling** hoặc release partial sequences cho thành phần liên quan. Cần phân biệt:

- **Group waiting time:** từ lúc các message trong nhóm bắt đầu được lưu đến lúc trigger timeout theo policy.
- **Upstream delivery timeout:** producer/broker đã chờ gửi hoặc nhận ack bao lâu.
- **Downstream handler timeout:** sau khi Resequencer release, handler xử lý mất bao lâu.
- **Business deadline:** quy trình vận chuyển/phê duyệt cho phép chờ đến khi nào.

Chúng có thể là các đồng hồ khác nhau. **Không mặc định một Gateway timeout sẽ tự làm Resequencer expire group**, hoặc một group expire sẽ tự hủy mọi worker đang chạy.

### 10.4. Những hướng xử lý khi quá hạn

1. **Quarantine toàn group:** giữ metadata, danh sách vị trí có/thiếu và lý do, cho phép operator xử lý.
2. **Yêu cầu redelivery:** xin phát lại message `#2` từ upstream/broker hoặc event store.
3. **Phát partial có gắn trạng thái thiếu:** chỉ khi nghiệp vụ cho phép, dùng schema có missing/gap markers.
4. **Dừng một workflow và báo lỗi:** tránh xử lý sự kiện sau không có tiền đề.
5. **Bỏ group theo retention policy:** chỉ khi kết quả không cần phục hồi và việc mất dữ liệu được chấp nhận.

Không nên tự **tăng `nextExpected` từ 2 lên 3** chỉ vì đã hết thời gian chờ nếu nghiệp vụ cấm bỏ qua bước số 2.

## 11. Kiểm tra gap một cách độc lập và xác định

Để test **message nào chưa đến** mà không dựa vào thread scheduling, có thể viết một inspector thuần Java, tách khỏi Resequencer. Inspector này đọc một snapshot hiện trạng, **không tự giải phóng group**.

### 11.1. Snapshot trạng thái chờ

~~~java
import java.time.Instant;
import java.util.Set;

record SequenceObservation(
        SequenceGroup group,
        int sequenceSize,
        Set<Integer> received,
        Instant firstObservedAt) {

    SequenceObservation {
        if (group == null || firstObservedAt == null
                || sequenceSize <= 0 || sequenceSize > 1000) {
            throw new IllegalArgumentException(
                    "INVALID_SEQUENCE_OBSERVATION");
        }
        received = Set.copyOf(received);
        if (received.stream().anyMatch(
                n -> n == null || n < 1 || n > sequenceSize)) {
            throw new IllegalArgumentException(
                    "INVALID_RECEIVED_POSITION");
        }
    }
}

record GapReport(
        SequenceGroup group,
        java.util.List<Integer> missingPositions,
        boolean deadlineReached) {

    GapReport {
        missingPositions = java.util.List.copyOf(missingPositions);
    }
}
~~~

Giới hạn `sequenceSize <= 1000` là **quy tắc minh họa do ứng dụng chọn** để tránh tạo danh sách quá lớn; nó không phải hằng số mặc định của Spring Integration. Production nên chọn giới hạn theo capacity và policy.

### 11.2. Hàm đọc gap và deadline

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.stream.IntStream;

final class GapInspector {

    GapReport inspect(
            SequenceObservation observation,
            Instant now,
            Duration maxWait) {

        if (now == null || maxWait == null
                || maxWait.isNegative() || maxWait.isZero()
                || now.isBefore(observation.firstObservedAt())) {
            throw new IllegalArgumentException(
                    "INVALID_GAP_INSPECTION_TIME");
        }

        List<Integer> missing =
                IntStream.rangeClosed(1, observation.sequenceSize())
                        .filter(n -> !observation.received().contains(n))
                        .boxed()
                        .toList();

        boolean deadlineReached =
                !now.isBefore(
                        observation.firstObservedAt().plus(maxWait));

        return new GapReport(
                observation.group(), missing, deadlineReached);
    }
}
~~~

Đây là logic **quan sát**, không phải logic tự kích hoạt expiration của framework. Với group đã partial release, danh sách `received` cần được định nghĩa là **toàn bộ vị trí đã từng nhận**, gồm cả vị trí đã release, nếu muốn tính missing trên toàn sequence. Nếu chỉ đọc những message đang còn trong `MessageGroupStore`, các vị trí đã release có thể không còn trong store và bị báo thiếu giả.

### 11.3. Test không dùng `Thread.sleep`

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GapInspectorTest {

    @Test
    void missingTwoIsVisibleBeforeAndAfterDeadline() {
        Instant first = Instant.parse("2026-01-01T00:00:00Z");
        SequenceObservation observed = new SequenceObservation(
                new SequenceGroup("SHIP-42", "RUN-7"),
                4,
                Set.of(1, 3, 4),
                first);

        GapInspector inspector = new GapInspector();

        GapReport before = inspector.inspect(
                observed,
                first.plusSeconds(20),
                Duration.ofSeconds(30));
        assertEquals(List.of(2), before.missingPositions());
        assertFalse(before.deadlineReached());

        GapReport after = inspector.inspect(
                observed,
                first.plusSeconds(30),
                Duration.ofSeconds(30));
        assertEquals(List.of(2), after.missingPositions());
        assertTrue(after.deadlineReached());
    }

    @Test
    void completeGroupHasNoMissingPositions() {
        Instant first = Instant.EPOCH;
        SequenceObservation observed = new SequenceObservation(
                new SequenceGroup("SHIP-1", "RUN-1"),
                3, Set.of(1, 2, 3), first);

        GapReport report = new GapInspector().inspect(
                observed,
                first.plusSeconds(5),
                Duration.ofSeconds(10));

        assertTrue(report.missingPositions().isEmpty());
        assertFalse(report.deadlineReached());
    }
}
~~~

**Lợi ích:** một test như vậy có thể tái hiện “sau 30 giây, vẫn thiếu #2” mà không cần đợi 30 giây trong CI. Nhưng muốn chứng minh **Spring Integration group timeout/expiration handler thực sự chạy**, cần một integration test có cấu hình timeout và clock/scheduler hoặc cơ chế đợi có timeout phù hợp với framework.

## 12. Bộ nhớ buffer không phải vô hạn

### 12.1. Khi nhiều nhóm đều thiếu một vị trí

Một ví dụ vận hành:

~~~text
10.000 groups
Mỗi group nhận #2..#20 nhưng chưa nhận #1

Số pending messages = 10.000 × 19 = 190.000
~~~

Đó là số lượng **chỉ để minh họa phép nhân**, không phải số đo thực tế của Spring Integration. Nếu message còn mang JSON lớn hoặc attachments, mức sử dụng memory/disk có thể tăng nhanh.

### 12.2. Những giới hạn cần đặt

| Giới hạn | Tại sao cần? | Phản ứng khi vượt |
|---|---|---|
| Maximum sequence size | Tránh khai báo size khổng lồ do bug/đầu vào giả mạo. | Validation/reject trước khi buffer. |
| Maximum pending per group | Không một group giữ quá nhiều message. | Quarantine/backpressure theo policy. |
| Maximum active groups | Giới hạn tổng footprint. | Admission control, spill to durable store hoặc reject có kiểm soát. |
| Group TTL/idle timeout | Dọn group mất message lâu dài. | Expiration/recovery và late-arrival policy. |
| Message size | Chặn payload quá lớn. | Validate, chunking hoặc object store reference. |
| Store capacity | Tránh đầy heap/disk/DB. | Alert và backpressure thay vì silent drop. |
| Retry attempts | Chặn resend loop khi gap không thể phục hồi. | DLQ/manual repair sau deadline. |

Các giới hạn này là **chính sách ứng dụng và vận hành**, không mặc nhiên được thực thi chỉ nhờ gọi `.resequence()`. Khi dùng `MessageGroupStore` bền vững, vẫn cần theo dõi số nhóm, dung lượng lưu, transaction contention và cleanup.

### 12.3. Backpressure ở đâu?

Trong một flow đồng bộ, nếu Resequencer không còn chỗ buffer thì upstream có thể nhận error/không thể gửi. Trong flow bất đồng bộ, queue/broker có thể tiếp tục nhận message trong lúc Resequencer chậm tiêu thụ, dẫn đến backlog ở nơi khác.

Đừng giải quyết đầy bộ nhớ bằng cách **bỏ các message đến sớm không log**. Nếu chính sách cho phép drop, đó phải là quyết định có metric, audit hoặc trạng thái nghiệp vụ rõ ràng. Nếu không, cần backpressure, giới hạn input rate và đường recover.

## 13. Durability và phục hồi sau restart

### 13.1. In-memory group store

Một Resequencer dùng state trong JVM có thể giữ:

~~~text
SHIP-42/RUN-7:
  buffered = {#3, #4}
  waiting = #1, #2
~~~

Nếu process chết, **state in-memory có thể mất**. Khi consumer restart, broker có thể redeliver những message chưa ack hoặc không, tùy transaction/ack policy. Không được coi buffer in-memory là durable chỉ vì Resequencer đã “accepted” message.

### 13.2. Persistent message group store

Khi yêu cầu phục hồi cao, cần cân nhắc `MessageGroupStore` có persistence phù hợp (ví dụ JDBC-backed store hoặc một implementation được hỗ trợ trong hệ thống), transaction boundaries và cleanup.

~~~mermaid
flowchart LR
    B[(Broker / Input)] --> R[Resequencer]
    R --> S[(Durable Group Store)]
    R --> O[(Ordered Output)]
    O --> H[Handler]
    H --> D[(Business DB)]
~~~

Cần trả lời:

- Store lưu **payload, correlation, sequence, group state** như thế nào?
- Một message được **ack** trước hay sau khi đã được lưu vào store?
- Release message downstream có nằm cùng transaction với việc cập nhật group state không?
- Nếu crash sau khi release nhưng trước ack, output có thể bị phát lại không?
- Khi group expire, state/tombstone được giữ bao lâu?
- Version/schema serialization của các message cũ còn đọc được sau deploy không?

**Durable group store không tự tạo exactly-once xuyên broker, message store và DB của handler.** Có thể cần outbox/inbox, transactional channel adapter, deduplication và idempotency theo operation key.

### 13.3. Restart và message đã được release

Ví dụ:

~~~text
T1: Resequencer nhận đủ #1, #2, #3
T2: Release #1 và #2 đến downstream
T3: Process crash trước khi trạng thái release được lưu bền
T4: Restart, broker redeliver
~~~

Nếu downstream đã commit `#1` và `#2`, việc phát lại hai message này có thể làm side effect trùng. Vì vậy:

- Nghiệp vụ nên có **idempotency key** theo group + sequence/event ID.
- Handler cần nhận diện message đã xử lý trước đó.
- Broker redelivery phải được phân biệt với một sự kiện mới.
- Recovery phải biết policy phát lại/replay của cả nhóm, không giả định “đúng thứ tự” có nghĩa “đúng số lần”.

## 14. Duplicate và late arrivals: không tự ghép lại nhóm đã đóng

### 14.1. Hai dạng duplicate

1. **Duplicate đang chờ:** `#3` được nhận hai lần khi còn thiếu `#2`.
2. **Duplicate sau release:** `#1` được gửi lại khi consumer/resequencer đã phát `#1`.

Trong bài Java thuần, cả hai bị từ chối. Trong Spring Integration, cách message group xử lý duplicate phụ thuộc message identity, store và processor settings cụ thể. **Đừng suy rằng cùng sequenceNumber tự được dedupe như một business operation** khi không kiểm tra cấu hình và test.

### 14.2. Payload mâu thuẫn ở cùng sequenceNumber

~~~text
SHIP-42 / RUN-7 / seq=2:
  eventId=A, eventType=PACKED, quantity=5

SHIP-42 / RUN-7 / seq=2:
  eventId=B, eventType=PACKED, quantity=50
~~~

Hai event này không thể đơn giản “last-write-wins” nếu số lượng gói hàng ảnh hưởng đến nghiệp vụ. Phải xác minh:

- Đây là redelivery của cùng event hay hai phiên bản dữ liệu?
- Có update/correction protocol riêng không?
- Producer nào được phép tạo sequence này?
- Cần quarantine hoặc operator review không?

Không cho một payload ngoại lai chiếm vị trí `#2` chỉ vì sequence number khớp. Cần identity, schema và authorization phù hợp.

### 14.3. Tombstone cho group đã hoàn tất/expire

Nếu group `SHIP-42/RUN-7` đã hoàn tất và được xóa khỏi store, một message `#3` đến muộn có thể bị hiểu là **khởi đầu group mới** nếu không có quy tắc nhận diện group đã đóng.

Một hướng thiết kế là lưu trạng thái/tombstone tối thiểu:

~~~text
groupKey = SHIP-42/RUN-7
state = COMPLETED
completedAt = ...
lastSequence = 3
retentionUntil = ...
~~~

**Tombstone là cơ chế ứng dụng/thiết kế lưu trữ gợi ý**, không phải bảo đảm mọi MessageGroupStore tự sinh record như trên. Phải chọn retention theo replay horizon và giới hạn lưu trữ, bảo mật.

### 14.4. Late missing message sau timeout

Giả sử `#3` bị giữ vì thiếu `#2`, sau 30 giây group expire; đến giây 35 `#2` mới tới. Những lựa chọn:

- **Reconcile từ durable event log:** xây lại sequence đúng theo policy và phát event điều chỉnh nếu cần.
- **Quarantine late arrival:** operator xem xét trước khi replay.
- **Ignore có audit:** chỉ nếu nghiệp vụ chấp nhận dữ liệu cũ không còn giá trị.
- **Resume group:** chỉ khi state, side effect và version tương thích; không tự nối lại group đã hết hạn.

Không tạo một group mới và tự coi `#2` là message đầu tiên của sequence, vì như vậy sẽ làm lẫn **lần xử lý cũ với lần mới**.

## 15. Thứ tự phát không tự bảo đảm thứ tự hoàn tất

### 15.1. Resequencer làm đúng nhưng worker vẫn có thể xử lý đảo

Giả sử Resequencer phát:

~~~text
#1 -> #2 -> #3
~~~

Sau đó message được gửi vào `ExecutorChannel` có ba worker:

~~~text
Worker A nhận #1, xử lý 2 giây
Worker B nhận #2, xử lý 100 ms
Worker C nhận #3, xử lý 50 ms

Thứ tự commit có thể thành: #3, #2, #1
~~~

Như vậy Resequencer đã **sắp đúng thứ tự dispatch**, nhưng một consumer bất đồng bộ có thể làm sai **thứ tự nghiệp vụ của side effect** nếu không có cơ chế điều phối tiếp.

### 15.2. Chọn semantics thực sự cần bảo đảm

| Yêu cầu | Biện pháp có thể cần |
|---|---|
| Chỉ cần downstream **nhận** đúng thứ tự. | Resequencer + channel giữ thứ tự gửi/nhận. |
| Handler phải **bắt đầu** theo thứ tự. | Consumer serialization/per-key ordering và kiểm tra lifecycle. |
| Side effect phải **commit** đúng thứ tự. | Per-group serialization, transactions/state machine, idempotency. |
| Các shipment độc lập được xử lý song song. | Partition/shard theo shipment group, single writer mỗi group. |
| Cần đúng thứ tự qua nhiều service. | Event version, ordered outbox/inbox, durable correlation/replay. |

Một hệ thống có thể chọn **thứ tự chặt chẽ trong từng shipment nhưng song song giữa các shipment**. Đây thường là lựa chọn cân bằng giữa tính đúng đắn và throughput; không cần khóa toàn bộ hệ thống thành một luồng duy nhất.

### 15.3. FIFO không vượt được giới hạn transport

Ngay cả khi output channel trong JVM bảo toàn thứ tự, một adapter hoặc consumer group downstream có thể chia messages vào nhiều partition. Nếu `#1` và `#2` của cùng shipment đi vào **hai broker partitions khác nhau**, không có bảo đảm chung rằng consumer sẽ xử lý chúng theo cùng trình tự.

Phải kiểm tra:

- Partition key có được giữ theo `shipmentId`/group key không?
- Số consumer threads và acknowledgment semantics thế nào?
- Retry có chuyển message sang queue khác và phá thứ tự không?
- Dead-letter/replay có bỏ qua một event cũ không?
- Handler có kiểm tra version/expected sequence trong business store không?

**Resequencing ở một vị trí không tạo ra ordering xuyên tất cả các ranh giới phía sau.**

## 16. Kết hợp với các EIP khác

### 16.1. Splitter → Resequencer → Aggregator

Một flow có thể:

~~~mermaid
flowchart LR
    A["Batch 3 items"] --> S[Splitter]
    S --> P[Parallel processing]
    P --> R[Resequencer]
    R --> G[Aggregator]
    G --> O["Batch Result"]
~~~

Ý nghĩa:

- **Splitter** tạo các phần và thường có sequence/correlation metadata khi cấu hình phù hợp.
- Các worker có thể hoàn tất theo thứ tự khác nhau.
- **Resequencer** phát các message theo sequence mong muốn.
- **Aggregator** gom các kết quả thành một payload chung nếu nghiệp vụ yêu cầu.

Nhưng không phải mọi flow cần cả hai **Resequencer và Aggregator**. Nếu Aggregator có thể gom theo ID, không phụ thuộc arrival order rồi tự sắp danh sách output, dùng thêm Resequencer có thể chỉ làm tăng latency và buffer. Chọn mô hình theo hợp đồng downstream.

### 16.2. Filter trước Resequencer có thể tạo gap vĩnh viễn

~~~text
Splitter tạo #1, #2, #3 với sequenceSize=3

Filter:
  #1 -> accepted
  #2 -> rejected/discarded
  #3 -> accepted

Resequencer nhận #1 và #3, còn thiếu #2
~~~

Nếu Filter im lặng loại `#2` nhưng Resequencer vẫn chờ cả sequence gốc, group có thể **không bao giờ đủ**.

Các hướng thiết kế:

1. **Không discard mà phát placeholder/tombstone cho vị trí #2** nếu hợp đồng cho phép, để downstream biết vị trí này bị loại có chủ đích.
2. **Tính lại sequence sau Filter** chỉ khi có thể làm đầy đủ và nhất quán cho toàn bộ nhóm; không thay số/size tùy tiện trên từng message.
3. **Đưa Filter sau Resequencer** nếu chính sách nghiệp vụ cho phép và cần giữ thứ tự gốc trước khi loại.
4. **Chỉnh release/expiration policy** nếu nghiệp vụ có thể bỏ một số phần.

Ví dụ một placeholder:

~~~text
Position 2:
  sequenceNumber = 2
  outcome = FILTERED_OUT
  reason = NOT_ELIGIBLE
~~~

Đây là **schema ứng dụng đề xuất**, không phải message Resequencer tự sinh. Consumer cần biết một placeholder không có nghĩa nghiệp vụ xử lý thành công ở vị trí đó.

### 16.3. Router có thể tạo nhiều đường đến khác nhau

Nếu Router phân một nhóm message sang hai queue trước Resequencer, các message có thể đến với độ trễ khác nhau; đây là một lý do dùng Resequencer. Nhưng nếu mỗi nhánh tạo **correlationId khác** hoặc chỉ một nhánh đến Resequencer, flow sẽ không thể xây lại sequence ban đầu.

Hãy kiểm tra:

- Mọi message thuộc một sequence sẽ quay về **cùng group** hay không?
- Router có gửi đúng một message cho mỗi vị trí, hay tạo thêm bản sao?
- Channel và adapter có giữ sequence headers không?
- Một nhánh bị lỗi có tạo placeholder/error outcome hoặc deadline rõ không?
- Nếu route phụ thuộc policy version, replay message cũ có được gom đúng group không?

### 16.4. Transformer không được làm mất sequence context

Transformer có thể trả một payload mới:

~~~java
record NormalizedEvent(
        String shipmentId,
        String runId,
        int sequenceNumber,
        String normalizedType) {}

NormalizedEvent normalize(ShipmentEvent event) {
    return new NormalizedEvent(
            event.shipmentId(),
            event.runId(),
            event.sequenceNumber(),
            event.eventType().trim().toUpperCase());
}
~~~

Khi payload thay đổi, các sequence headers cần cho Resequencer **vẫn phải được truyền theo framework/adapter contract**. Đừng nhầm `NormalizedEvent.sequenceNumber` trong payload với `IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER` được Resequencer dùng; nếu header bị mất, chỉ có field trong payload chưa chắc đủ để framework tự reorder.

### 16.5. Content Enricher và sequence latency

Một Content Enricher gọi Customer Profile Service có thể làm message `#2` bị chậm hơn `#3`. Resequencer phía sau giúp sắp đúng khi cả hai hoàn tất, nhưng không loại bỏ nguyên nhân chậm. Nếu latency tăng kéo dài, cần đo **enricher latency**, **gap age**, **buffered count** và **timeout** thay vì chỉ tăng nhóm timeout.

### 16.6. Gateway request–reply và kết quả Resequencer

Một Gateway yêu cầu **một reply cho một request** có thể không phù hợp nếu Resequencer còn giữ message chờ nhiều event khác trong group. Ví dụ:

~~~text
Gateway gửi message #3, chờ reply 2 giây
Resequencer buffer #3 vì thiếu #1 và #2
Gateway timeout sau 2 giây
#1 và #2 đến sau 5 giây
~~~

Message `#3` sau đó có thể được phát, nhưng caller đã timeout. Không giả định Gateway timeout tự xóa `#3` khỏi group. Nếu message cần chờ nhiều lần event khác nhau, nên cân nhắc API bất đồng bộ/trạng thái operation thay vì giữ request–reply đồng bộ quá lâu.

## 17. Error handling: ai chịu trách nhiệm ở từng mốc?

### 17.1. Các lớp lỗi khác nhau

~~~mermaid
flowchart TD
    I[Incoming Message] --> V{Header + payload hợp lệ?}
    V -->|Không| E1[Input validation / malformed]
    V -->|Có| B[Resequencer buffer]
    B -->|Store lỗi/đầy| E2[Store / capacity failure]
    B -->|Thiếu sequence| W[Wait / timeout]
    W --> E3[Group expiration / recovery]
    B -->|Release được| D[Ordered dispatch]
    D -->|Không có subscriber| E4[Delivery failure]
    D -->|Handler nhận| H[Business handler]
    H -->|Thất bại| E5[Processing failure]
    H -->|Thành công| OK[Business outcome]
~~~

**Đừng gộp tất cả vào một metric `resequencer_failed`.** Lỗi schema, group timeout, store failure, dispatch failure và downstream processing failure có remediation khác nhau.

### 17.2. Đồng bộ và bất đồng bộ

Với `DirectChannel`, exception từ endpoint có thể lan ngược đến sender trong call stack. Với `ExecutorChannel`, `QueueChannel`/poller hoặc broker, lỗi có thể xuất hiện sau khi upstream nhận acknowledgment; lúc đó cần error flow theo **execution context**.

Spring Integration hỗ trợ `ErrorMessage` và `errorChannel` trong những hoàn cảnh cấu hình phù hợp, nhưng:

- Không phải mọi lỗi đều được gửi tới cùng một global error channel.
- Một event bị buffer chờ gap **không tự là error** để error channel xử lý ngay.
- Group expiration phải có chiến lược timeout/cleanup và recovery riêng.
- Error flow nhận `Throwable` không tự biết missing sequence trong toàn group nếu không lấy đúng state/context.
- Retry trên adapter có thể tái đưa message cũ vào group, cần duplicate handling.

### 17.3. Retry thường cần đặt ở đâu?

Nếu broker mất kết nối khi đưa message `#2` vào flow, retry **gửi/nhận #2** có thể giúp lấp gap. Nhưng nếu business handler của `#2` đã commit rồi ack bị mất, retry có thể tạo side effect trùng.

Nên phân biệt:

1. Retry **vận chuyển message đến Resequencer**.
2. Retry **lưu message vào group store**.
3. Retry **phát message sau release**.
4. Retry **handler nghiệp vụ** sau khi đã nhận.

Chúng là các retry scope khác nhau và không tự an toàn như nhau. Với message có side effect, cần idempotency theo operation key ổn định.

### 17.4. Quá hạn nên có đủ dữ liệu điều tra

Một bản ghi expiration hữu ích:

~~~text
event=RESEQUENCE_GROUP_EXPIRED
  shipmentId=SHIP-42
  runId=RUN-7
  expectedSequenceSize=4
  observedPositions=[1,3,4]
  missingPositions=[2]
  groupAgeMs=30000
  action=QUARANTINE
~~~

Đây là schema log ứng dụng, **không** phải dữ liệu tự động có ở mọi cấu hình Resequencer. Nếu group đã partial release, phải giữ snapshot vị trí đã nhận/phát để không báo những vị trí đã release thành missing giả.

## 18. Kiểm thử với transport và xử lý song song

### 18.1. Unit test không đủ

Unit test `SequenceBuffer` chứng minh thuật toán giữ `#3` khi thiếu `#2`, nhưng nó không kiểm tra:

- Header mapping qua Kafka/HTTP/JMS.
- Bộ đệm và transactional message store của Spring Integration.
- Group expiry và cleanup khi Resequencer thực sự chạy.
- Hành vi broker khi redelivery hoặc consumer restart.
- Thứ tự commit của downstream handler bất đồng bộ.

Cần bổ sung integration/system tests tương ứng với ranh giới lỗi có thể xảy ra.

### 18.2. Một kế hoạch test end-to-end

~~~text
Producer
  -> send #3
  -> send #1
  -> send #2
  -> broker input (có correlation/sequence headers)
  -> Spring Integration Resequencer
  -> broker output (partition theo shipment)
  -> ordered consumer
  -> business DB + observed outcomes
~~~

Kiểm tra:

1. Sau `#3`, group buffer có message nhưng consumer ordered chưa thấy `#3`.
2. Sau `#1`, hành vi release đúng profile full/partial đã cấu hình.
3. Sau `#2`, consumer quan sát sequence đúng `1,2,3`.
4. Khi restart giữa chừng, cách phục hồi phù hợp store/ack contract.
5. Khi `#2` được gửi lặp, không tạo side effect trùng.
6. Khi `#2` không bao giờ đến, group expire/recovery đúng.
7. Khi output được đưa vào nhiều partitions, thứ tự per shipment còn đúng.
8. Khi input payload sai sequenceSize, message không được đưa vào một group hợp lệ một cách mù quáng.

### 18.3. Không dùng `Thread.sleep` để đoán message đã phát

Với async tests, dùng `CountDownLatch` hoặc một `BlockingQueue` trong test handler và `poll(timeout)` để chờ output. Không assert ngay sau `send` trừ khi execution model đồng bộ đã được xác nhận. Latch cũng có thể mô phỏng worker thứ hai chậm, nhưng phải luôn release trong `finally` và cleanup executor.

### 18.4. Một kịch bản kiểm tra thứ tự sau release

Nếu business yêu cầu **commit** đúng thứ tự:

~~~text
Given:
  Resequencer đã nhận đủ #1, #2, #3.
  Downstream handler #1 bị chặn trên latch.

When:
  Chưa cho #1 hoàn tất.

Then:
  #2 không được phép commit trước #1 theo hợp đồng.

When:
  Mở latch cho #1.

Then:
  #1, #2, #3 commit lần lượt theo business version.
~~~

Test này không chỉ kiểm tra Resequencer. Nó còn kiểm tra **cấu hình consumer/transaction và trạng thái nghiệp vụ**. Nếu một ExecutorChannel có nhiều worker khiến #2 commit trước #1, Resequencer không phải thành phần duy nhất cần sửa.

## 19. Observability: message đang nằm ở đâu?

### 19.1. Các mốc nên ghi nhận

~~~text
event=SEQUENCE_MESSAGE_RECEIVED
  group=SHIP-42/RUN-7 seq=3 total=4

event=SEQUENCE_MESSAGE_BUFFERED
  group=SHIP-42/RUN-7 seq=3 waitingFor=1

event=SEQUENCE_MESSAGE_RECEIVED
  group=SHIP-42/RUN-7 seq=1 total=4

event=SEQUENCE_PREFIX_RELEASED
  group=SHIP-42/RUN-7 positions=[1]

event=SEQUENCE_GAP_DETECTED
  group=SHIP-42/RUN-7 nextExpected=2 pending=[3]

event=SEQUENCE_GROUP_EXPIRED
  group=SHIP-42/RUN-7 missingPositions=[2,4]
~~~

Các sự kiện trên chỉ là **đề xuất structured logging**. Với cấu hình full-group release, log `SEQUENCE_PREFIX_RELEASED positions=[1]` có thể **không xuất hiện** cho đến khi toàn nhóm đã đủ; không áp một mô hình partial release cho mọi flow.

### 19.2. Những trường quan trọng

| Trường | Dùng để trả lời |
|---|---|
| `shipmentId`/`runId` | Message thuộc nhóm nào và lần xử lý nào? |
| `sequenceNumber`/`sequenceSize` | Vị trí nào đến, tổng số phần hợp lệ là bao nhiêu? |
| `nextExpected` | Đang chờ vị trí nào, nếu release theo prefix? |
| `bufferedPositions` hoặc `bufferedCount` | Những phần nào vẫn bị giữ? |
| `receivedPositions` | Những vị trí nào đã từng đến, kể cả đã release nếu được tracking? |
| `groupCreatedAt`/`lastReceivedAt` | Group tồn tại bao lâu, bao lâu rồi không có phần mới? |
| `groupState` | OPEN, WAITING, COMPLETED, EXPIRED, RECOVERING? |
| `policyVersion` | Luật sequence/release nào đã áp dụng? |
| `traceId` | Nối log qua adapter/thread/service. |
| `errorCode` | Mismatch size, duplicate, timeout, store error? |

Không cần log toàn bộ payload sự kiện nếu nó chứa dữ liệu khách hàng, địa chỉ giao hàng hay token. ID nghiệp vụ cũng có thể nhạy cảm; cần retention, masking và phân quyền theo chính sách vận hành.

### 19.3. Metrics hữu ích

| Metric minh họa | Ý nghĩa |
|---|---|
| `resequencer_messages_received_total` | Số message đầu vào được quan sát. |
| `resequencer_messages_buffered_total` | Số lần message được giữ để chờ. |
| `resequencer_messages_released_total` | Số message đã được phát theo sequence. |
| `resequencer_groups_active` | Số group chưa hoàn tất. |
| `resequencer_pending_messages` | Số message đang giữ trong buffer/store. |
| `resequencer_group_age_seconds` | Độ tuổi các group còn mở. |
| `resequencer_gap_wait_seconds` | Thời gian chờ gap hoặc thời gian đến khi release. |
| `resequencer_groups_expired_total` | Số group hết hạn/chuyển recovery. |
| `resequencer_duplicates_total` | Số duplicate được phát hiện. |
| `resequencer_invalid_headers_total` | Số message sai sequence/correlation metadata. |
| `resequencer_store_failures_total` | Lỗi đọc/ghi group store. |
| `ordered_handler_failures_total` | Lỗi downstream sau khi message đã release. |

Đây là **tên metric do ứng dụng đề xuất**, không có nghĩa chúng là meter mặc định của mọi bản Spring Integration. Giữ label hữu hạn (component, reason, environment); **không** dùng `shipmentId`, `runId`, `eventId` hay `traceId` làm metric labels có cardinality cao. Dùng log/tracing hoặc audit store để tìm từng group cụ thể.

### 19.4. Message History không thay thế sequence audit

Spring Integration Message History có thể giúp biết message đi qua component nào khi tracking được cấu hình. Tuy nhiên, nó không tự lưu:

- Tập sequence positions **mong đợi** của mọi group.
- Tập message còn đang buffer.
- Gap nào chưa có message và đã chờ bao lâu.
- Thứ tự **commit** downstream.
- Kết quả retry/replay sau khi JVM crash.

Khi điều tra một group bị kẹt, cần kết hợp **message headers, group state, message store, structured logs, tracing và business outcome**. Một log “đã qua Resequencer” không đủ để xác định một business event đã hoàn tất.

## 20. Ma trận kiểm thử “buffer message đến sớm”

| ID | Input/kịch bản | Expected outcome | Điều không được xảy ra |
|---|---|---|---|
| RS-01 | Một message size=1, seq=1 | Release đúng một message. | Chờ vô hạn. |
| RS-02 | Arrival `1,2,3` | Output `1,2,3`. | Đảo thứ tự. |
| RS-03 | Arrival `3,2,1` | Buffer `3`, `2` rồi output `1,2,3`. | Phát `3` trước `1`. |
| RS-04 | Arrival `2,3,1` | Không release trước `1`, cuối cùng output đúng. | Dựa vào arrival order. |
| RS-05 | Arrival `3,1,2`, full release | Chờ đủ rồi phát `1,2,3`. | Phát prefix ngoài contract. |
| RS-06 | Arrival `3,1,2`, partial release | Có thể phát `1` sau khi đến, rồi `2,3`. | Phát `3` khi `2` còn thiếu. |
| RS-07 | Hai shipment xen kẽ | Thứ tự đúng trong từng group. | Ghép message của SHIP-A vào SHIP-B. |
| RS-08 | Cùng shipment nhưng run khác | Hai group tách biệt. | Replay cũ lấp gap của run mới. |
| RS-09 | `sequenceNumber=0` | Reject malformed. | Tạo vị trí 0 hợp lệ. |
| RS-10 | `sequenceNumber > sequenceSize` | Reject malformed. | Buffer vô hạn. |
| RS-11 | Cùng group nhưng sequenceSize mâu thuẫn | Error/quarantine. | Chấp nhận thay N âm thầm. |
| RS-12 | Duplicate `#3` đang chờ | Dedupe/duplicate policy có kiểm chứng. | Đếm là hai vị trí. |
| RS-13 | Duplicate `#1` đã release | Idempotency/late policy. | Downstream side effect trùng. |
| RS-14 | Cùng vị trí, hai eventId khác payload | Detect conflicting position. | Last-write-wins không audit. |
| RS-15 | Thiếu `#2` sau khi nhận `1,3,4` | Gap được nhận diện. | Kết luận group hoàn tất. |
| RS-16 | Đến deadline khi còn gap | Expiration/recovery theo policy. | Group sống vô hạn không quan sát. |
| RS-17 | `#2` đến sau expiration | Late-arrival policy. | Mở lại group như chưa có lịch sử. |
| RS-18 | Maximum sequence size vượt ngưỡng ứng dụng | Input bị chặn. | Tạo buffer vô hạn. |
| RS-19 | Active groups vượt capacity | Backpressure/reject/recovery. | Silent drop. |
| RS-20 | Downstream handler ném lỗi khi release `#2` | Processing error được quan sát. | Coi là lỗi sort hoặc group missing. |
| RS-21 | Resequencer output sang multi-worker executor | Test commit-order contract riêng. | Tin dispatch order là commit order. |
| RS-22 | Filter bỏ `#2` trước resequencer | Có placeholder/release/expiration policy. | Chờ mãi mà không phát hiện. |
| RS-23 | Transformer tạo payload mới | Sequence/correlation headers đúng. | Mất group context. |
| RS-24 | Splitter tạo sequence headers | Resequencer đọc đúng group/size. | Gắn group của batch khác. |
| RS-25 | Nested split | Sequence/correlation của đúng tầng. | Gom nhầm cấp cha/con. |
| RS-26 | Broker redelivery sau crash | Recovery/dedupe theo contract. | Đếm duplicate thành event mới. |
| RS-27 | Group store in-memory + crash | Hạn chế được ghi nhận/test. | Tuyên bố buffer vẫn bền vững. |
| RS-28 | Durable store + restart | Group được phục hồi theo transaction/ack policy. | Bỏ mất buffered messages âm thầm. |
| RS-29 | Header mapping qua Kafka/JMS/HTTP | Correlation/sequence round-trip. | Reorder sai vì header rơi. |
| RS-30 | Gateway timeout khi group còn chờ | Caller status và group state rõ. | Giả định timeout đã cancel mọi task. |
| RS-31 | Sequence streaming không biết N | Có end-of-stream/window policy. | Dùng `sequenceSize` giả vô hạn. |
| RS-32 | Có message đủ sequence nhưng downstream fail | Tách released vs processed metrics. | Báo business success chỉ vì group release. |
| RS-33 | Resequencer sau Content Enricher chậm | Đo gap/buffer/lookup latency. | Chỉ tăng timeout vô điều kiện. |
| RS-34 | Many groups thiếu vị trí đầu | Capacity, group age và cleanup được giám sát. | OOM/disk exhaustion không cảnh báo. |

### 20.1. Chọn đúng cấp kiểm thử

| Cấp kiểm thử | Nên kiểm tra | Chưa tự chứng minh |
|---|---|---|
| **Unit test** | Vị trí chờ, buffer, duplicate, validation, tính toán gap/deadline. | Framework routing/store hoạt động đúng. |
| **Spring Integration test** | `.resequence()`, headers, correlation, group release, output channel. | Broker restart/serialization nếu không dùng broker. |
| **Adapter integration test** | Header mapping, ACK, redelivery, partitioning, reply routing. | Business DB commit nếu chỉ dùng mock. |
| **System/load test** | Buffer capacity, hot groups, backpressure, failover, recovery. | Mọi sự cố production trong mọi điều kiện. |

Không cần biến tất cả unit test thành end-to-end test rất chậm. Nhưng với những rủi ro có thể làm mất thứ tự hoặc dữ liệu, phải có ít nhất một kiểm thử ở **đúng tầng mà rủi ro xuất hiện**.

## 21. Cách chẩn đoán một Resequencer không phát message

Giả sử `SHIP-42` có `#3` và `#4` nhưng không thấy downstream nhận message nào.

1. **Xác minh mục tiêu:** có yêu cầu output bắt đầu từ `#1` hay một vị trí khác? Có dùng full/partial release không?
2. **Kiểm tra input headers:** `correlationId`, `sequenceNumber`, `sequenceSize` có đúng kiểu/giá trị và nhất quán không?
3. **Kiểm tra group key:** message bị gửi vào group khác do runId, tenant, policy version hoặc string encoding không?
4. **Kiểm tra message store:** group có tồn tại, buffered positions là gì, đã quá hạn chưa?
5. **Kiểm tra missing positions:** chưa có `#1`/`#2` thật hay message bị Filter/Router đưa sang nhánh khác?
6. **Kiểm tra ingress adapter:** broker có nhận `#1`/`#2`, ack/delivery/retry ra sao?
7. **Kiểm tra capacity:** group store hoặc executor có nghẽn làm chậm xử lý không?
8. **Kiểm tra release strategy:** wait-for-all hay partial, có custom timeout/expiration khiến group bị xóa không?
9. **Kiểm tra downstream channel:** message đã release nhưng không có subscriber, handler stopped hoặc queue full không?
10. **Kiểm tra late/duplicate:** group đã hoàn tất/expire và message tới bị xử lý theo chính sách nào?
11. **Kiểm tra business outcome:** handler nhận message có commit không, hay chỉ mới dispatch?
12. **Ghi nhận nguyên nhân:** bổ sung test regression, metric và log đủ để lần sau phân biệt gap với delivery error.

Nếu group đang chờ `#2`, **tăng số thread ở downstream handler** sẽ không khiến `#2` tự xuất hiện. Nếu message đã được release nhưng handler lỗi, **tăng groupTimeout** cũng không giải quyết nguyên nhân. Hãy tìm mốc đầu tiên nơi message bị mất dấu.

## 22. Những sai lầm thường gặp

| Nhận định sai | Hậu quả | Cách làm đúng |
|---|---|---|
| “Resequencer là một FIFO queue.” | Không phục hồi được thứ tự nghiệp vụ khi arrival đã đảo. | Dựa trên correlation và sequence, không chỉ enqueue order. |
| “Message #3 đến trước thì cứ phát #3.” | Sai state machine downstream. | Buffer cho đến khi release condition hợp lệ. |
| “Timestamp nhỏ nhất luôn là sequence đầu.” | Clock skew/đồng hồ không đồng bộ. | Dùng sequenceNumber/ordering contract đáng tin. |
| “`correlationId` là cùng một shipmentId cho mọi lần xử lý.” | Reply/replay của nhiều runs bị trộn. | Dùng group key có run/version khi cần. |
| “`sequenceSize` có thể đổi tùy message.” | Group không biết khi nào hoàn tất. | Chốt một sequence contract nhất quán. |
| “Có `DirectChannel` là message đã được xử lý.” | Buffered nhưng chưa released. | Quan sát các mốc riêng. |
| “Resequencer release thì DB đã commit.” | Handler downstream còn có thể fail. | Test commit/order ở consumer và transaction. |
| “Partial release luôn bật hoặc luôn tắt.” | Test sai semantics hoặc mất latency mong muốn. | Cấu hình và verify theo phiên bản. |
| “Filter drop một phần không ảnh hưởng.” | Group chờ gap vĩnh viễn. | Placeholder/release/expected set có chủ đích. |
| “Message ID đủ để dedupe.” | Message rebuild/redelivery có ID mới. | Business operation key, event ID và version. |
| “Một duplicate có thể lấp vị trí còn thiếu.” | Release sai dù missing thực tế. | Dedupe theo sequence position và identity. |
| “Group timeout bằng Gateway timeout.” | Caller timeout còn group sống hoặc ngược lại. | Định nghĩa deadline từng tầng. |
| “Group store tự bền vững.” | Mất state khi restart. | Chọn persistent store, ack/transaction policy. |
| “Resequencer ngăn mọi xử lý đồng thời.” | Executor downstream commit ngược. | Serializing/partitioning per group khi cần. |
| “Sắp xếp trong một JVM bảo đảm qua Kafka.” | Consumer partitions có thể đảo. | Partition key và consumer ordering contract. |
| “Chỉ cần tăng buffer vô hạn.” | Memory/disk exhaustion. | Giới hạn capacity, group expiration và backpressure. |
| “Message History là danh sách còn thiếu.” | Thiếu input expected set và store state. | Gap inspector + group state/audit. |
| “Late event có thể tự mở nhóm cũ.” | Reprocessing và side effect trùng. | Tombstone/reconciliation/late policy. |
| “Không có event #2 nghĩa là event #2 thất bại nghiệp vụ.” | Nhầm delivery loss với business failure. | Phân biệt not received, received, released, processed. |
| “Hễ có `errorChannel` là mọi group bị kẹt sẽ báo lỗi.” | Group chờ mãi mà không có error event. | Cấu hình timeout/expiration monitoring và recovery. |

## 23. Bài tập thực hành

1. **Thứ tự đảo hoàn toàn:** dùng `SequenceBuffer` gửi lần lượt `#4, #3, #2, #1` cùng group, `sequenceSize=4`. Assert không phát trước `#1` và cuối cùng phát `1,2,3,4`.
2. **Partial-prefix release:** gửi `#3, #1, #4, #2`. Ghi lại `ready` tại từng lần nhận, chỉ ra gap ảnh hưởng đến `#3` ra sao.
3. **Wait-for-all:** sửa bản mô phỏng để không phát prefix trước khi đủ cả sequence, rồi so sánh latency và lượng dữ liệu phải giữ với partial release.
4. **Một message đơn:** gửi sequenceSize=1 và sequenceNumber=1, kiểm tra không chờ thêm.
5. **Hai group xen kẽ:** gửi A#2, B#2, B#1, A#1; kiểm tra thứ tự per-group mà không áp global order.
6. **Replay khác run:** gửi sự kiện cùng shipment nhưng `RUN-1` và `RUN-2`, chứng minh group key không trộn dữ liệu hai lần xử lý.
7. **Duplicate pending:** gửi `#3` hai lần trước khi có `#1`. Thiết kế policy dedupe hoặc báo lỗi theo eventId/position.
8. **Duplicate đã release:** gửi lại `#1` sau khi prefix đã phát, xác minh không tạo output nghiệp vụ lặp.
9. **Sai sequenceSize:** gửi `#2/3` rồi `#1/4` cùng group, kiểm tra lỗi input/schema được phát hiện.
10. **Mất một phần:** giữ input `#1,#3,#4`, dùng `GapInspector` nhận diện missing `#2` và tính trạng thái trước/sau deadline bằng thời gian cố định.
11. **Late arrival:** giả lập group đã expire rồi `#2` mới đến, thiết kế quarantine hoặc recovery; không tự mở lại group mới.
12. **Giới hạn bộ nhớ:** sinh nhiều group nhận `#2..#20` nhưng không có `#1`; đề xuất max active groups và backpressure policy có metric.
13. **Java DSL:** dựng `ShipmentResequencerConfiguration`, gửi `#3,#2,#1` qua `ShipmentMessageFactory` và kiểm tra `OrderedEventProbe`.
14. **Header test:** kiểm tra cả correlationId, sequenceNumber, sequenceSize trên messages trước Resequencer và sau một adapter giả.
15. **Full/partial profile:** tạo hai test context có release strategy khác nhau; kiểm tra thời điểm nhận `#1` trong arrival `3,1,2` có phù hợp contract từng profile.
16. **Filter gap:** đặt Filter loại message `#2` trước Resequencer, rồi thiết kế placeholder hoặc group expiration để không treo vô hạn.
17. **Transformer:** biến payload thành `NormalizedEvent`, giữ metadata sequence; xác minh Resequencer vẫn phát đúng.
18. **Splitter + Resequencer:** split batch thành ba phần, xử lý bất đồng bộ tạo output theo thứ tự đảo, rồi resequence để restore sequence nếu downstream cần.
19. **Commit order:** phát đầu ra ordered sang executor nhiều worker; chặn #1 và quan sát #2 có thể hoàn tất trước không. Đề xuất per-group serialization phù hợp.
20. **Message group store:** dùng store phù hợp phiên bản Spring Integration, kiểm tra pending group và expiration/cleanup theo contract; không chỉ nhìn probe.
21. **Restart:** giả lập process restart sau khi buffer `#3` và trước khi `#1/#2` đến. So sánh in-memory với persistent group store và tính đúng đắn của replay.
22. **Broker retry:** giả lập side effect của handler #2 đã commit nhưng acknowledgment mất; áp dụng business idempotency key để ngăn cập nhật lặp.
23. **Monitoring:** xây dựng `SEQUENCE_MESSAGE_BUFFERED`, `SEQUENCE_PREFIX_RELEASED`, `RESEQUENCE_GROUP_EXPIRED` logs và dashboard pending groups/gap age.
24. **Security:** gửi message với `sequenceSize` cực lớn hoặc correlationId mạo danh tenant khác. Chặn trước Resequencer, kiểm tra allowlist và isolation.
25. **Luồng không biết N:** thiết kế watermark hoặc end-of-stream marker cho stream sự kiện, giải thích vì sao không thể chỉ chờ đủ `sequenceSize` cố định.

### 23.1. Tiêu chí đánh giá bài thực hành

Một implementation đáng tin cậy cần trả lời được:

- Nó giữ message `#3` đến sớm như thế nào khi `#1/#2` còn thiếu?
- Group key có ngăn lẫn shipment, tenant và lần replay không?
- Thứ tự release là **full sequence** hay **contiguous prefix**?
- Duplicate/mismatch có thể làm một group phát sai không?
- Missing sequence có deadline và đường recovery rõ không?
- Buffer/store có giới hạn, durability và cleanup phù hợp không?
- Sau release, downstream có thực sự cần commit theo thứ tự không?
- Tests có kiểm tra channel/adapter thật ngoài unit algorithm không?
- Có log/metric đủ để tìm group bị kẹt và vị trí thiếu không?

## 24. Câu hỏi tự kiểm tra

**Câu 1:** Với sequence `1,2,3`, message `#3` đến trước. Có được phát ngay không?

**Không**, nếu hợp đồng yêu cầu bắt đầu từ `#1`. `#3` phải được buffer cho tới khi điều kiện release thỏa.

**Câu 2:** “Message đến sớm” ở đây có nghĩa timestamp nhỏ hơn những message khác không?

**Không.** Nó có sequenceNumber ở phía sau vị trí đang chờ nhưng **đến trước** các message tiền nhiệm. Ordering nên dựa trên sequence/causal contract đáng tin, không đơn thuần timestamp.

**Câu 3:** Resequencer có đảm bảo group hoàn tất khi thiếu `#2` không?

**Không.** Nó cần timeout/expiration/recovery hoặc policy bỏ gap có chủ đích. Buffer vô hạn không tự khôi phục message chưa đến.

**Câu 4:** FIFO queue nhận theo thứ tự `3,1,2` có tự phát `1,2,3` không?

**Không.** FIFO giữ thứ tự queue đã nhận; Resequencer dùng sequence metadata để phục hồi thứ tự mong muốn.

**Câu 5:** Phân biệt Resequencer với Aggregator?

**Resequencer** sắp thứ tự và phát lại các message theo sequence; **Aggregator** gom nhiều message thành một kết quả theo policy. Cả hai có thể dùng group/correlation nhưng hợp đồng output khác.

**Câu 6:** `sequenceNumber=2` của hai shipment khác nhau có thuộc cùng một group không?

**Không.** Chúng phải có correlation/group key riêng; dùng sequenceNumber đơn lẻ không đủ.

**Câu 7:** `sequenceSize=4` ở message đầu và size=5 ở message sau cùng group có nên được chấp nhận không?

**Không** theo hợp đồng nhóm hữu hạn của bài. Đây là lỗi metadata cần xử lý trước khi release.

**Câu 8:** Arrival `3,1,2` theo full-sequence release và partial-prefix release khác nhau như thế nào?

**Full release** giữ cả nhóm đến khi đủ rồi phát `1,2,3`. **Partial release** có thể phát `1` trước, sau đó phát `2,3` khi gap được lấp; cần cấu hình/kiểm thử đúng framework version.

**Câu 9:** Dùng `DirectChannel` và `send(...)` trả true sau khi gửi `#3` có nghĩa handler ordered đã nhận `#3` chưa?

**Chưa.** Resequencer có thể chỉ nhận vào buffer; handler chưa được gọi.

**Câu 10:** Nếu `#1` đã release nhưng broker redeliver nó, Resequencer có tự bảo đảm business side effect không lặp không?

**Không mặc định.** Cần duplicate/replay policy và idempotency ở đúng điểm có side effect.

**Câu 11:** Với một `MessageGroupStore` bền vững, tất cả message đã phát downstream có chắc đúng một lần không?

**Không.** Durability của group state không đồng nghĩa exactly-once end-to-end qua broker, output channel và database.

**Câu 12:** Sau Resequencer là ExecutorChannel ba worker. Thứ tự commit chắc chắn giống thứ tự release không?

**Không.** Cần thêm ràng buộc xử lý/commit tuần tự per group nếu nghiệp vụ yêu cầu.

**Câu 13:** Một Filter bỏ message `#2` trong nhóm ba phần. Resequencer có tự biết đây là bỏ hợp lệ không?

**Không.** Phải có placeholder, expected-set/release policy hoặc timeout/recovery được thiết kế.

**Câu 14:** Khi Gateway timeout nhưng `#2` đến sau đó, có chắc group tự hủy và worker không còn chạy không?

**Không.** Gateway timeout, group timeout và downstream processing là những lifecycle khác nhau.

**Câu 15:** Có cần giữ `sequenceNumber` cả trong payload và header không?

**Không bắt buộc ở mọi thiết kế**. Nhưng nếu cần business lineage qua adapter, payload chứa sequence có thể hữu ích; Resequencer phải nhận metadata đúng theo API và mapping của framework. Hai bản phải nhất quán.

**Câu 16:** `MessageHeaders.ID` có thay thế được `eventId` cho idempotency không?

**Không nên.** Message có thể được tạo lại qua adapter/retry và có ID khác; key nên phản ánh cùng business operation.

**Câu 17:** Một group có đủ sequence nhưng downstream thất bại ở `#2`. Có thể coi toàn workflow thành công không?

**Không.** Group release chỉ là một mốc; business processing/commit cần được theo dõi riêng.

**Câu 18:** Khi nhiều group không có `#1`, điều gì giúp tránh đầy bộ nhớ?

Giới hạn số nhóm và message pending, TTL/expiration, durable store khi cần, backpressure, monitoring và recovery policy. Không chỉ tăng heap vô hạn.

## 25. Kết luận

**Buffer message đến sớm** là trách nhiệm quan trọng của **Resequencer**: khi các message của cùng một sequence đến không đúng thứ tự, những message đứng sau vị trí còn thiếu phải được **giữ lại**, rồi được **phát theo sequence** khi đủ điều kiện. Để làm điều đó an toàn, hệ thống cần một **group key đúng, sequence headers nhất quán, release strategy rõ ràng, giới hạn buffer, timeout/expiration và phương án xử lý duplicate/late arrivals**.

Trong Spring Integration, Resequencer hỗ trợ thao tác nhóm và sắp xếp message; tuy nhiên, **full-group release** và **partial-prefix release** mang semantics khác nhau. Việc release đúng thứ tự không tự bảo đảm downstream xử lý, commit hay ack đúng thứ tự, đặc biệt khi qua executor/broker phân tán. Message store bền vững giúp phục hồi state nhưng không tự tạo exactly-once; cần kết hợp idempotency, transaction và correlation.

Với module `SPRING_INTEGRATION_PATTERN`, phương pháp thực hành hữu ích là **unit test thuật toán buffer → integration test Resequencer và headers → adapter test cho transport → system test cho timeout/retry/restart**. Kết hợp Router, Filter, Transformer, Splitter, Aggregator, Gateway, error channel và tracing theo đúng hợp đồng để người vận hành luôn trả lời được: **“Message nào đến sớm, đang chờ vị trí nào, khi nào được release và downstream đã xử lý đến đâu?”**
