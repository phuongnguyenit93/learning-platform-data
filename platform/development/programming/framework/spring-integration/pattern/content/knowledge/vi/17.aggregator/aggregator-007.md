# Expire group và xử lý phần chưa hoàn tất

> **Chương:** Aggregator  
> **Module:** `SPRING_INTEGRATION_PATTERN` — học triển khai Enterprise Integration Patterns với Spring Integration để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng; thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử và quan sát các nhánh. Bài này tập trung vào **hết hạn nhóm message (group expiration)** và **cách xử lý các phần chưa đến hoặc chưa hoàn tất** mà không làm sai kết quả nghiệp vụ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **message group** của Aggregator được hình thành, lưu, release và expire như thế nào; phân biệt **release thành công**, **expire vì timeout**, **xóa nhóm đã hoàn thành** và **dọn nhóm tồn lâu trong MessageStore**.
2. Thiết kế chính sách **đủ phần, thiếu phần, không có phần nào, đến muộn, đến trùng và lỗi một phần**, thay vì mặc định Aggregator chỉ cần đếm message.
3. Hiểu vai trò của `correlationStrategy`, `releaseStrategy`, `groupTimeout`, `sendPartialResultOnExpiry`, `expireGroupsUponCompletion` và cơ chế `MessageGroupStoreReaper` theo đúng phạm vi.
4. Xây dựng một flow Spring Integration dùng **Splitter → các handler độc lập → Aggregator** và tạo `BatchOutcome` thể hiện rõ **độ đầy đủ** và **kết quả nghiệp vụ**.
5. Xử lý **partial result**, callback timeout, retry, idempotency, late arrival, group tombstone và giới hạn bộ nhớ/backpressure.
6. Kiểm thử cả trường hợp hoàn chỉnh lẫn hết hạn, group không có phản hồi, duplicate/out-of-order, sự cố restart và những tác dụng phụ không được lặp.

## 2. Bài toán: ba yêu cầu kiểm tra tồn kho, chỉ nhận về hai phản hồi

Đơn `ORD-801` có ba dòng hàng. Splitter tạo ba request độc lập để kiểm tra tồn kho tại các kho khác nhau:

~~~text
Batch ORD-801 / execution RUN-001
  expected item IDs = [LINE-1, LINE-2, LINE-3]
       |
       v
   Splitter (3 child requests)
       |
       +--> LINE-1 -> Inventory A -> reply RESERVED
       +--> LINE-2 -> Inventory B -> reply NOT_AVAILABLE
       +--> LINE-3 -> Inventory C -> không có reply
       |
       v
   Aggregator nhận 2/3 replies
~~~

Nếu Aggregator chỉ release khi đủ ba kết quả, nó có thể giữ nhóm vô thời hạn khi `LINE-3` bị mất hoặc consumer không phản hồi. Nhưng nếu cứ đếm đủ **hai** kết quả rồi coi toàn bộ batch đã thành công, ứng dụng sẽ bỏ qua một dòng hàng quan trọng.

**Group expiration** giải quyết câu hỏi: *Sau một thời hạn mà nhóm chưa đủ điều kiện release, cần làm gì với nhóm và những message đã nhận?*

~~~mermaid
flowchart TD
    S["Splitter: 3 requests"] --> A["Aggregator group RUN-001"]
    R1["Reply LINE-1"] --> A
    R2["Reply LINE-2"] --> A
    R3["LINE-3: chưa có"] -.-> A
    A --> D{"Đã đủ tất cả replies?"}
    D -->|Có| C["Release: ALL_REPLIES"]
    D -->|Chưa| T{"Deadline / timeout?"}
    T -->|Chưa| W["Giữ group, chờ tiếp"]
    T -->|Đã hết| P["Expire: PARTIAL / ERROR / RECONCILE"]
    W --> D
~~~

Một kết quả partial minh họa:

~~~json
{
  "batchId": "ORD-801",
  "executionId": "RUN-001",
  "expectedCount": 3,
  "receivedCount": 2,
  "completeness": "PARTIAL_EXPIRED",
  "businessOutcome": "INCOMPLETE",
  "missingItemIds": ["LINE-3"]
}
~~~

Kết quả này **không** nói rằng `LINE-3` hết hàng, cũng không tuyên bố kiểm tra tồn kho thất bại tại kho C. Nó chỉ nói rằng **chưa có một phản hồi hợp lệ của item đó trước khi nhóm hết hạn**.

## 3. Những trạng thái phải phân biệt

| Khái niệm | Ý nghĩa | Ví dụ | Điều không được suy ra |
| --- | --- | --- | --- |
| **Group created/open** | Đã có ít nhất một message được đưa vào nhóm | Reply đầu tiên cho `RUN-001` | Toàn bộ batch đã bắt đầu thành công |
| **Group complete** | Release strategy xác định đã đủ phần theo contract | Đủ LINE-1, LINE-2, LINE-3 | Tất cả kho đều trả kết quả `RESERVED` |
| **Group released** | Aggregator tạo output từ nhóm | `BatchOutcome` được gửi ra | Consumer cuối đã commit nghiệp vụ |
| **Group expired** | Nhóm quá hạn theo timeout/expiry policy | Nhận 2/3 trước deadline | Phần còn thiếu đã thất bại về mặt nghiệp vụ |
| **Partial result** | Output chứa thông tin từ một tập con phần mong đợi | 2/3 item replies | Kết quả có thể thay thế kết quả đầy đủ |
| **Group removed** | Dữ liệu nhóm được xóa/giải phóng từ store | Sau hoàn thành hoặc expiry | Late reply sẽ được nhận diện là cũ |
| **Group tombstone** | Dấu vết nhóm đã đóng được lưu riêng hoặc trong chính sách store | `RUN-001: CLOSED` | Có thể tái sử dụng khóa group an toàn ngay |

**Hai trục độc lập:** *độ đầy đủ* và *kết quả nghiệp vụ*. Nhóm có thể **đã đầy đủ** nhưng một item trả `NOT_AVAILABLE`, hoặc nhóm **chưa đầy đủ** dù cả hai item đã nhận đều thành công.

| Độ đầy đủ | Kết quả nghiệp vụ | Ví dụ |
| --- | --- | --- |
| `ALL_REPLIES` | `ALL_SUCCEEDED` | Đủ ba replies, cả ba RESERVED |
| `ALL_REPLIES` | `SOME_FAILED` | Đủ ba replies, một NOT_AVAILABLE |
| `PARTIAL_EXPIRED` | `INCOMPLETE` | Mới có hai replies, item còn lại chưa rõ |
| `NO_REPLIES_TIMEOUT` | `INCOMPLETE` | Không có reply nào; phải có deadline ngoài Aggregator nếu group chưa tồn tại |

Không nên gộp cả bốn trường hợp thành một Boolean `success`.

## 4. Vòng đời message group của Aggregator

Một Aggregator thường gồm các thành phần logic:

1. **Correlation strategy:** xác định reply thuộc nhóm nào.
2. **Message group store:** giữ các message đang chờ cùng metadata của nhóm.
3. **Release strategy:** quyết định khi nào đủ điều kiện phát output.
4. **Output processor:** tạo kết quả tổng hợp từ các message trong nhóm.
5. **Expiry/timeout policy:** quyết định phải làm gì khi nhóm chưa đủ mà đã quá hạn.
6. **Group cleanup:** quản lý metadata nhóm, tài nguyên và trạng thái nhóm sau release/expiry.

~~~mermaid
flowchart LR
    IN["Item replies"] --> COR["Correlation strategy"]
    COR --> G["MessageGroupStore: group RUN-001"]
    G --> REL{"Release strategy"}
    REL -->|Đủ| O["Output processor: complete"]
    REL -->|Chưa| WAIT["Waiting group"]
    WAIT -->|Timeout| EXP{"Expiration policy"}
    EXP -->|Send partial| PO["Output processor: partial"]
    EXP -->|No partial| ER["Discard / error / observe"]
    O --> CLEAN["Cleanup / tombstone"]
    PO --> CLEAN
    ER --> CLEAN
~~~

### 4.1. `release` khác `expire`

**Release:** policy thấy đã đủ điều kiện, chẳng hạn nhận được **mỗi item mong đợi đúng một kết quả hợp lệ**. Aggregator tạo outcome và đưa nó tới downstream.

**Expire:** chưa đủ điều kiện release nhưng chính sách timeout, expiration hoặc dọn group đã can thiệp. Tùy cấu hình, nhóm có thể phát **partial result** hoặc được xử lý theo đường discard/error/quarantine. Không nên mô tả mọi expiration như một successful release.

### 4.2. `expireGroupsUponCompletion` khác group timeout

`expireGroupsUponCompletion` điều khiển **cách nhóm được xử lý sau khi release hoàn chỉnh**. Nó không phải “thời gian chờ 30 giây”. Nếu xóa group ngay sau completion, một late/duplicate reply cùng correlation key có thể tạo **nhóm mới**, trừ khi còn cơ chế chặn nhóm đã đóng.

`groupTimeout` là một cơ chế timeout của Aggregator cho **nhóm chưa hoàn tất**. Cần hiểu đúng thời điểm kích hoạt theo phiên bản/cấu hình: nó không nên được mặc định diễn giải thành “deadline cố định từ lúc batch được sinh” nếu ứng dụng chưa thiết lập điều đó.

### 4.3. `MessageGroupStoreReaper` khác per-group timeout

`MessageGroupStoreReaper` phục vụ **dọn/expire các nhóm cũ trong message group store** theo lịch quét. Nó có thể cần thiết khi muốn cleanup các nhóm tồn lâu hoặc khi sử dụng store bền vững; nhưng nó **không thay thế** một quy tắc deadline nghiệp vụ rõ ràng và có thể có độ trễ bằng chu kỳ quét.

Ví dụ, nếu yêu cầu “mọi đơn phải có kết quả ở hoặc trước mốc 12:00:00Z”, một job reaper quét mỗi phút **không được xem là bảo đảm đúng mốc thời gian tuyệt đối**.

## 5. Bốn chính sách khi group hết hạn

Hãy chọn chính sách dựa trên **tác dụng nghiệp vụ** của từng phần.

| Chính sách | Hành vi khi thiếu phần | Khi phù hợp | Rủi ro |
| --- | --- | --- | --- |
| **Phát partial result** | Trả kết quả đã có + danh sách thiếu | Dashboard, thống kê, báo cáo tiến độ, nghiệp vụ chấp nhận incomplete | Consumer coi partial là complete |
| **Không phát partial; gửi lỗi/timeout** | Kết thúc nhóm với outcome lỗi có kiểm soát | Thanh toán, tạo đơn nguyên tử theo hợp đồng, phê duyệt bắt buộc đủ nguồn | Caller cần nhận reply/error thay vì chờ mãi |
| **Retry/reconcile trước khi đóng** | Tra cứu những item chưa phản hồi, phát lại có idempotency | Outbound có lỗi mạng không rõ kết quả | Side effect trùng nếu retry không an toàn |
| **Giữ trạng thái chờ / chuyển manual review** | Tạm dừng với trạng thái pending rồi nhân viên/worker xử lý | Workflow dài ngày, yêu cầu quyết định thủ công | MessageGroupStore và state phải bền, có TTL/monitoring |

**Quy tắc lựa chọn:** với hàng tồn kho, partial có thể tạo kết quả `INCOMPLETE` và yêu cầu tra cứu lại. Nhưng với “trừ tiền thành công sau đủ ba bước”, không được cho phép downstream coi partial là lệnh commit đã hoàn tất.

### 5.1. `sendPartialResultOnExpiry(true)` để làm gì?

Khi dùng Aggregator và một cơ chế expiration phù hợp, cấu hình `sendPartialResultOnExpiry(true)` cho phép **đưa những message đã tích lũy trong nhóm vào output processor khi nhóm expire**. Output processor cần tạo một hợp đồng **có đánh dấu thiếu dữ liệu**, chứ không được coi partial message list như một nhóm đầy đủ.

Trong demo dưới đây, ta đánh giá `PARTIAL_EXPIRED` khi bộ item ID đã nhận chưa bằng bộ item ID mong đợi. Đó là một quy ước có chủ đích của **flow minh họa**, không phải lời hứa mọi `MessageGroup` đều luôn chứa sẵn một header tên `partial`.

### 5.2. `sendPartialResultOnExpiry(false)` có ý nghĩa gì?

Khi không phát partial, phải thiết kế **cách ghi nhận và báo lỗi/đóng workflow**. Không nên chỉ tắt partial rồi mặc định Gateway sẽ nhận `TimeoutResponse`; output có thể không được phát và caller có thể chờ tới timeout riêng.

Một ứng dụng có thể cần handler ghi `BatchTimedOut` vào state store, phát event error/timeout riêng hoặc đưa vào reconciliation queue. Hãy kiểm thử cụ thể theo cách cấu hình expiration/discard của phiên bản Spring Integration đang dùng.

### 5.3. Hết hạn “nhóm” không phải hết hạn “từng child”

Nếu một child reply đến sau 31 giây trong khi deadline group là 30 giây, câu hỏi phải được giải quyết ở **mức batch**: nhận late reply để cập nhật kết quả cuối, đưa vào compensating flow, hay bỏ qua có audit? Đừng đặt một Filter timeout trên từng child rồi coi đó là expiry policy hoàn chỉnh của Aggregator.

## 6. Thiết kế hợp đồng dữ liệu: biết chính xác những gì đang chờ

Chỉ có `expectedCount=3` chưa đủ để kiểm soát duplicate. Ví dụ nhận `LINE-1` hai lần và `LINE-2` một lần: có **ba message**, nhưng vẫn thiếu `LINE-3`.

Để tránh đếm sai, nên biết **danh sách ID mong đợi** hoặc ít nhất một định danh item ổn định. Trong bài học, mỗi batch có một hợp đồng:

~~~text
GroupContract
  executionId = RUN-001         // Một lần thực thi cụ thể
  batchId = ORD-801             // Mã đơn nghiệp vụ
  expectedItemIds = [LINE-1, LINE-2, LINE-3]

ItemReply
  batchId = ORD-801
  itemId = LINE-1
  outcome = RESERVED
  reasonCode = null
~~~

**Tại sao có cả `batchId` và `executionId`?** Một đơn `ORD-801` có thể được xử lý lại do yêu cầu hợp lệ mới hoặc replay. Nếu dùng duy nhất `batchId` để correlation, hai lần thực thi có thể bị gom lẫn. `executionId` định danh **phiên gom**; idempotency của side effect cần một khóa khác theo contract, ví dụ `(commandId, lineId, operation)`.

### 6.1. Java 17 record bất biến

~~~java
import java.util.Objects;
import java.util.Set;
import java.util.List;

enum ItemState {
    RESERVED, NOT_AVAILABLE, FAILED
}

record GroupContract(
    String executionId,
    String batchId,
    Set<String> expectedItemIds
) {
    GroupContract {
        if (executionId == null || executionId.isBlank()
                || batchId == null || batchId.isBlank()) {
            throw new IllegalArgumentException("Group identity missing");
        }
        expectedItemIds = Set.copyOf(
            Objects.requireNonNull(expectedItemIds, "expectedItemIds"));
        if (expectedItemIds.isEmpty()) {
            throw new IllegalArgumentException(
                "Empty group requires a separate ingress outcome");
        }
        if (expectedItemIds.stream().anyMatch(
                id -> id == null || id.isBlank())) {
            throw new IllegalArgumentException("Invalid expected item ID");
        }
    }
}

record ItemReply(
    String batchId,
    String itemId,
    ItemState state,
    String reasonCode
) {
    ItemReply {
        if (batchId == null || batchId.isBlank()
                || itemId == null || itemId.isBlank()) {
            throw new IllegalArgumentException("Reply identity missing");
        }
        Objects.requireNonNull(state, "state");
    }
}

enum CompletionState {
    ALL_REPLIES,
    PARTIAL_EXPIRED
}

enum BusinessOutcome {
    ALL_SUCCEEDED,
    SOME_FAILED,
    INCOMPLETE
}

record BatchOutcome(
    String executionId,
    String batchId,
    int expectedCount,
    int receivedCount,
    CompletionState completeness,
    BusinessOutcome businessOutcome,
    List<ItemReply> replies,
    List<String> missingItemIds
) {
    BatchOutcome {
        replies = List.copyOf(replies);
        missingItemIds = List.copyOf(missingItemIds);
    }
}
~~~

Các `record` trên chỉ mô tả contract demo trong cùng JVM. Nếu `ItemReply` đi qua Kafka/AMQP/HTTP, cần **schema và header mapping** phù hợp để tái tạo `GroupContract` an toàn tại ingress; không mặc định một Java record đặt trong header sẽ tự được serialize mọi nơi.

### 6.2. Trust boundary của expected list

`expectedItemIds` phải được xác định ở nơi có quyền lập batch (ví dụ sau validation/Splitter), không lấy từ một reply do dịch vụ bên ngoài tự khai. Nếu một consumer có thể tự sửa `expectedCount` từ 3 xuống 1, nó có thể khiến Aggregator release sớm.

Trong production, một cách vững chắc hơn là lưu **GroupContract bất biến trong một store có thẩm quyền** bằng `executionId` và validate từng reply dựa trên bản ghi đó. Header ở demo chỉ giúp trình bày thuật toán khi test nội bộ.

## 7. Logic release: đủ tất cả item ID, không đếm message mù quáng

Một message group có thể gồm nhiều reply, thậm chí có duplicate do redelivery. Ta nên release khi **các item mong đợi đã có reply hợp lệ**, không phải khi `group.size() >= expectedCount`.

~~~java
import java.util.HashSet;
import java.util.Set;

import org.springframework.integration.store.MessageGroup;
import org.springframework.messaging.Message;

final class BatchGroupLogic {
    private BatchGroupLogic() {}

    static GroupContract contract(MessageGroup group) {
        Object value = group.getOne()
            .getHeaders().get("batchContract");
        if (!(value instanceof GroupContract contract)) {
            throw new IllegalArgumentException("Batch contract missing");
        }
        return contract;
    }

    static boolean allExpectedReceived(MessageGroup group) {
        GroupContract contract = contract(group);
        Set<String> ids = new HashSet<>();

        for (Message<?> message : group.getMessages()) {
            if (!(message.getPayload() instanceof ItemReply reply)
                    || !contract.batchId().equals(reply.batchId())
                    || !contract.expectedItemIds().contains(reply.itemId())) {
                // Dữ liệu bất hợp lệ cần được chặn ở ingress;
                // không coi nó là bằng chứng nhóm đã đủ.
                return false;
            }
            ids.add(reply.itemId());
        }

        return ids.equals(contract.expectedItemIds());
    }
}
~~~

**Không đưa logic validate/authorize hoàn toàn vào release strategy.** Phần này chỉ quyết định nhóm đủ hay chưa. Trước khi đưa reply vào Aggregator, nên kiểm tra `executionId`, source/tenant đã xác thực, `itemId` thuộc expected set và contract/schema hợp lệ. Một reply không hợp lệ cần tới error/rejection flow thay vì nằm trong group mãi.

### 7.1. Duplicate và conflicting duplicate

Nếu `LINE-1` được trả hai lần với cùng outcome, downstream có thể de-duplicate theo `itemId`. Nhưng nếu reply thứ hai nói `FAILED` trong khi reply thứ nhất nói `RESERVED`, hệ thống có **mâu thuẫn**. Không nên chọn ngẫu nhiên reply “đến cuối cùng” rồi coi là hợp lệ.

Nên:

1. Xác định khóa idempotency cho reply ở ingress, như `(executionId, itemId, attempt/operation)`.
2. Áp chính sách **first committed result wins**, version/attempt cao hơn thắng, hoặc trạng thái tổng hợp có kiểm soát — tùy contract.
3. Ghi cảnh báo và reconciliation nếu hai reply cùng khóa nhưng nội dung mâu thuẫn.
4. Chặn duplicate không cần thiết trước Aggregator hoặc xử lý rõ trong output processor.

### 7.2. Sequence headers có đủ không?

`correlationId`, `sequenceNumber` và `sequenceSize` do Splitter tạo có thể hỗ trợ Aggregator. Nhưng `sequenceSize=3` **không chứng minh** đã nhận ba item khác nhau. Khi yêu cầu chống duplicate và đối chiếu từng SKU/dòng, business item ID vẫn cần thiết.

Ngoài ra, sau khi qua broker hoặc Transformer, sequence headers có thể mất hoặc bị remap nếu không có cấu hình truyền metadata. Đừng trông chờ dữ liệu grouping tồn tại qua mọi boundary khi chưa kiểm thử.

## 8. Output processor: phân biệt complete, partial và business failure

Khi release hoặc expire, output processor tạo một `BatchOutcome` có danh sách reply đã nhận và danh sách ID còn thiếu. Ví dụ sau mở rộng `BatchGroupLogic` (đặt các phương thức dưới đây cùng class ấy khi sử dụng trong project):

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.integration.store.MessageGroup;
import org.springframework.messaging.Message;

static BatchOutcome toOutcome(MessageGroup group) {
    GroupContract contract = contract(group);
    Map<String, ItemReply> unique = new LinkedHashMap<>();

    for (Message<?> message : group.getMessages()) {
        ItemReply reply = (ItemReply) message.getPayload();
        if (!contract.batchId().equals(reply.batchId())
                || !contract.expectedItemIds().contains(reply.itemId())) {
            throw new IllegalStateException("UNEXPECTED_REPLY_IN_GROUP");
        }

        ItemReply old = unique.putIfAbsent(reply.itemId(), reply);
        if (old != null && !old.equals(reply)) {
            throw new IllegalStateException("CONFLICTING_DUPLICATE_REPLY");
        }
    }

    List<String> missing = contract.expectedItemIds().stream()
        .filter(id -> !unique.containsKey(id))
        .sorted()
        .toList();

    CompletionState completeness = missing.isEmpty()
        ? CompletionState.ALL_REPLIES
        : CompletionState.PARTIAL_EXPIRED;

    BusinessOutcome business;
    if (!missing.isEmpty()) {
        business = BusinessOutcome.INCOMPLETE;
    } else if (unique.values().stream().allMatch(
            reply -> reply.state() == ItemState.RESERVED)) {
        business = BusinessOutcome.ALL_SUCCEEDED;
    } else {
        business = BusinessOutcome.SOME_FAILED;
    }

    return new BatchOutcome(
        contract.executionId(),
        contract.batchId(),
        contract.expectedItemIds().size(),
        unique.size(),
        completeness,
        business,
        List.copyOf(unique.values()),
        missing);
}
~~~

**Đây là fragment phương thức bổ sung vào `BatchGroupLogic`**, không phải một class Java độc lập. Nó giả định chỉ có **hai đường output của demo**: release khi đã nhận đủ ID, hoặc partial khi timeout. Nếu bạn có release strategy khác, `missing.isEmpty()` chỉ nói nhóm thiếu/đủ dữ liệu, **không xác nhận nguyên nhân release là timeout**; khi cần phân biệt tỉ mỉ, hãy truyền explicit reason/event từ lifecycle handler hoặc state store.

Lưu ý `toOutcome` ném lỗi nếu gặp reply bất hợp lệ hoặc duplicate mâu thuẫn. Đó là tín hiệu rõ ràng cho bài học, nhưng production cần **đưa các dữ liệu đó tới quarantine/reconciliation trước khi group expiry** để không làm mất khả năng phát partial result lúc timeout.

### 8.1. Vì sao không chỉ trả `List<ItemReply>`?

Một list có hai reply không cho caller biết **đáng lẽ phải có bao nhiêu phần**, phần nào còn thiếu hoặc có còn được cập nhật tiếp hay không. `BatchOutcome` cần mang đủ metadata:

- `expectedCount` và `receivedCount`.
- `missingItemIds` để follow-up/reconciliation.
- `completeness` nói **độ đầy đủ**.
- `businessOutcome` nói **thành công hay thất bại nghiệp vụ trong phần đã xác định**.
- `executionId` và `batchId` để trace và tránh nhầm lần chạy.

### 8.2. Thứ tự output không đồng nghĩa thứ tự input

`MessageGroup.getMessages()` không nên được coi là một danh sách có thứ tự nghiệp vụ ổn định qua mọi store và transport. Nếu downstream yêu cầu thứ tự dòng hàng gốc, dùng `lineIndex`/`sequenceNumber` được xác nhận rồi **sắp xếp tường minh** trong output processor. Ví dụ trên chỉ sắp `missingItemIds`, không hứa thứ tự `replies` theo danh sách gốc.

## 9. Spring Integration Java DSL: expire và gửi partial result

Ví dụ dưới đây dùng một `DirectChannel` để tiếp nhận các `ItemReply` đã được kiểm tra và một `QueueChannel` để nhận `BatchOutcome`. Group timeout minh họa là **30 giây**. Đây là cấu hình in-memory để học cơ chế — không cam kết durability khi restart.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class BatchAggregationConfiguration {

    @Bean("inventory.replies.in")
    DirectChannel repliesInput() {
        return new DirectChannel();
    }

    @Bean("inventory.batch.outcomes")
    QueueChannel batchOutcomes() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow aggregateItemReplies() {
        return IntegrationFlow.from("inventory.replies.in")
            .aggregate(a -> a
                .correlationStrategy(message -> {
                    GroupContract contract = (GroupContract)
                        message.getHeaders().get("batchContract");
                    return contract.executionId();
                })
                .releaseStrategy(BatchGroupLogic::allExpectedReceived)
                .groupTimeout(30_000L)
                .sendPartialResultOnExpiry(true)
                .expireGroupsUponCompletion(true)
                .outputProcessor(BatchGroupLogic::toOutcome))
            .channel("inventory.batch.outcomes")
            .get();
    }
}
~~~

**Những giả định bắt buộc trước Aggregator trong demo:**

1. Mỗi message có `ItemReply` hợp lệ và một header `batchContract` kiểu `GroupContract` đã được xác minh.
2. `executionId` là khóa group duy nhất cho một phiên xử lý; không tái sử dụng cho phiên khác.
3. Tập `expectedItemIds` nhất quán giữa mọi reply thuộc cùng execution.
4. Từng reply không được phép tự sửa contract đã phát hành.
5. Khi có duplicate, input được dedup/validate theo chính sách để không tạo xung đột trong group.

Code cố tình không đưa adapter/Filter validation vào cùng đoạn để rõ phần **Aggregator**. Đây không phải ví dụ production có thể nhận raw Internet requests trực tiếp.

### 9.1. Ý nghĩa từng phần DSL

| DSL | Trách nhiệm |
| --- | --- |
| `.correlationStrategy(...)` | Chọn group theo `executionId`, không chọn theo UUID message đơn lẻ |
| `.releaseStrategy(...)` | Release khi **đủ các item ID được mong đợi** |
| `.groupTimeout(30_000L)` | Thiết lập timeout group theo cơ chế Aggregator được framework hỗ trợ |
| `.sendPartialResultOnExpiry(true)` | Khi group expire, cho phép output processor xử lý phần đã nhận |
| `.expireGroupsUponCompletion(true)` | Cho phép dọn/expire group sau khi hoàn tất; cần policy với late replies |
| `.outputProcessor(...)` | Tạo `BatchOutcome` để phân biệt ALL_REPLIES và PARTIAL_EXPIRED |

**Lưu ý về phiên bản:** ký hiệu DSL được minh họa theo họ API Spring Integration hiện đại. Trong dự án cụ thể, cần kiểm tra phiên bản và TaskScheduler/message store được cấu hình; công việc STEP 4 này **chưa chạy build hoặc Content QA chuyên sâu**.

### 9.2. Group timeout không luôn là “deadline cố định từ lúc sinh batch”

Một `groupTimeout` đơn giản có thể được lên lịch lại khi nhóm nhận thêm message theo cơ chế Aggregator. Vì thế, với một batch đã sinh lúc T0 nhưng reply đầu tiên tới T0+20 giây, deadline group không nhất thiết là T0+30 giây.

Nếu nghiệp vụ muốn **deadline tuyệt đối** (ví dụ “kết thúc trong 45 giây kể từ lúc tạo batch”), hãy lưu `createdAt/deadlineAt` từ nguồn đáng tin cậy và áp một chính sách timeout được tính theo deadline đó; test với đồng hồ điều khiển được. Không lấy thời gian của JVM khác hoặc header client tự khai mà không kiểm soát drift/clock skew.

### 9.3. Không có output nếu chưa có group

Aggregator chỉ biết những group đã được hình thành bởi **message đến**. Nếu Splitter tạo ba request nhưng **không có reply nào**, có thể **chưa tồn tại group** để per-group timeout kích hoạt.

Do đó, bài toán “zero replies” cần một **batch-level deadline watcher** hoặc workflow registry:

~~~text
BatchCreated(RUN-001, expected=[A,B,C], deadline=T)
       |
       +--> Dispatch requests
       |
       +--> Deadline watcher at T
             |
             +--> Nếu đã COMPLETE: no-op
             +--> Nếu PARTIAL: đánh dấu incomplete/reconcile
             +--> Nếu NO_REPLIES: phát BatchTimedOut(no replies)
~~~

Watcher phải phối hợp với Aggregator theo một **trạng thái kết thúc duy nhất**, tránh vừa phát partial từ Aggregator vừa phát timeout từ watcher thành **hai final outcomes**.

## 10. Xử lý late replies sau khi group đã expire

Giả sử group `RUN-001` expire ở giây 30 và output đã phát `PARTIAL_EXPIRED`. Reply `LINE-3` đến ở giây 31. Ba cách xử lý thường gặp:

1. **Discard có audit:** ghi late arrival, không sửa kết quả đã phát.
2. **Reconcile/upsert:** cập nhật state của batch, phát một **event version mới** (không ngụy trang là output đầu tiên).
3. **Compensation/manual review:** xử lý nếu reply chứng minh side effect đã xảy ra mà workflow tưởng đã thất bại.

**Không được** tự tạo một Aggregator group mới rồi coi reply muộn như một batch mới chỉ vì group cũ đã bị xóa.

### 10.1. Late message và nhóm đã xóa

Khi `expireGroupsUponCompletion(true)` hoặc expiry cleanup xóa group khỏi store, hệ thống có thể không còn metadata để biết `executionId` đã đóng. Late reply có thể bị nhận vào nhóm mới trống mang cùng key, chờ timeout rồi sinh **partial outcome thứ hai**.

Một chính sách có **closed-group registry/tombstone** sẽ chặn hiện tượng này:

~~~text
Incoming reply
   |
   v
Lookup BatchExecutionState by executionId
   |
   +--> OPEN     -> validate itemId -> Aggregator
   +--> COMPLETE -> duplicate/late path -> audit or ignore
   +--> EXPIRED  -> late path -> reconcile or quarantine
   +--> UNKNOWN  -> reject or manual investigation
~~~

Trong production, registry cần TTL và lưu bền theo **độ trễ tối đa/replay window**. Nếu message có thể được replay sau nhiều ngày, tombstone chỉ giữ vài giây sẽ không đủ. Cũng cần chống race giữa “nhóm vừa expire” và “reply đến đúng lúc expire”, bằng transaction/CAS/state transition phù hợp.

### 10.2. Late reply không phải tự động retry

Một late reply có thể báo `RESERVED` — nghĩa là kho đã thực hiện việc giữ hàng trước đó, dù hệ thống tổng hợp đã phát `INCOMPLETE`. Retry `RESERVE_STOCK` thêm lần nữa có thể tạo side effect trùng. Hãy **tra cứu/đối chiếu kết quả** trước khi phát lệnh lại.

## 11. MessageGroupStore và dọn dẹp nhóm tồn lâu

Aggregator dùng MessageStore/MessageGroupStore để lưu reply và metadata grouping. In-memory store đơn giản cho ví dụ; production có thể cần store bền vững để khôi phục nhóm sau restart, tùy SLA và topology.

| Vấn đề | In-memory đơn giản | Persistent store / cluster |
| --- | --- | --- |
| Restart khi group còn mở | Có nguy cơ mất phần đã nhận | Có thể giữ trạng thái nếu cấu hình giao dịch/khôi phục đúng |
| Dữ liệu tăng dần | Chiếm heap | Chiếm database/store và I/O |
| Group timeout | Dựa scheduler trong process | Cần phối hợp scheduling, restart và recovery |
| Nhiều instance | Mỗi instance có group riêng nếu không phối hợp | Cần shared store, locking và routing/ownership rõ |
| Group cleanup | Release/expiry giải phóng bộ nhớ | Cần expire/reaper và retention policy |
| Trùng message | Có thể thêm vào group nhiều lần | Cần idempotency + store consistency; persistence không tự dedup |

**Một store bền vững không mặc nhiên tạo “exactly once”.** Nếu consumer redeliver message hoặc hai node cùng xử lý group, vẫn cần concurrency control, dedup và idempotency downstream.

### 11.1. MessageGroupStoreReaper

Message group store reaper quét các nhóm và kích hoạt expiration theo chính sách. Khi dùng nó, cần quyết định:

- **Scan interval:** quét bao lâu một lần?
- **Group timeout/age:** nhóm tồn bao lâu thì được xem là quá hạn?
- **Partial policy:** group bị quét hết hạn có phát partial output hay chỉ cleanup?
- **Concurrency:** nếu Aggregator vừa release trong lúc reaper quét, ai được phép đóng group?
- **Monitoring:** reaper lỗi hoặc ngừng chạy được phát hiện bằng chỉ số nào?
- **Retention:** tombstone/closed-state giữ lại bao lâu?

Không đặt `groupTimeout` và reaper không kiểm soát để cùng phát **hai partial results**. Những cơ chế timeout/cleanup phải được phối hợp, và output cuối phải được bảo vệ bằng trạng thái idempotent `OPEN → CLOSED`.

### 11.2. Tối ưu số lượng nhóm đang mở

Ước lượng đơn giản:

~~~text
100 batch/s × 60 s thời gian nhóm mở trung bình
≈ 6.000 nhóm đang chờ

Nếu mỗi nhóm lưu 4 replies × 2 KiB payload:
≈ 48.000 KiB chỉ tính payload (~47 MiB),
chưa tính headers, object/store metadata và indexes.
~~~

Nếu group không expire hoặc reaper không hoạt động, số nhóm tăng lâu dài có thể làm cạn heap hoặc message store. Theo dõi **open group count**, **oldest group age**, **store size**, **expiry rate**, **late reply rate** và **partial result rate**.

## 12. Correlation và release strategy: lỗi thường không nằm ở timeout

Một Aggregator chờ mãi không chỉ vì worker chậm. Những nguyên nhân khác:

| Nguyên nhân | Triệu chứng | Cách kiểm tra |
| --- | --- | --- |
| Correlation key khác | Replies cùng batch bị tách thành nhiều group | Kiểm tra `executionId` và header mapping |
| Thiếu một child do Filter drop | 2/3, không có ItemRejected | Kiểm tra discard channel và release policy |
| Sequence size sai | Aggregator chờ số phần không có thật | Kiểm tra Splitter/source collection |
| Duplicate thay reply còn thiếu | Group count đủ nhưng unique IDs thiếu | Đếm theo item ID |
| Không có consumer của một nhánh | Reply của một item không bao giờ về | Queue/poller/handler health |
| ReplyChannel mất qua broker | Handler xử lý nhưng không trả đúng nơi | Message header mapping / reply routing |
| Item handler lỗi async | Lỗi đi `errorChannel`, không thành ItemReply | Error flow và timeout |
| Group key tái sử dụng | Late replies bị trộn với batch mới | Unique execution ID + closed registry |
| Reaper cấu hình sai | Group không được dọn | TaskScheduler, lifecycle, store age |
| Clock/deadline sai | Expiry sớm/muộn bất thường | UTC, clock skew, policy start time |

**Đừng sửa lỗi bằng cách giảm `expectedCount` cho vừa số replies đã nhận.** Cách đó làm hệ thống có vẻ hoàn tất nhưng che mất item bị thiếu, sai hợp đồng và có thể gây thiếu hàng/thiếu giao dịch.

### 12.1. Correlation không thay idempotency

Correlation trả lời “reply thuộc **nhóm nào**?”. Idempotency trả lời “cùng **tác vụ nghiệp vụ** này đã thực hiện hay chưa?”. Một batch có thể được replay trong cùng hoặc khác execution, nhưng việc giữ hàng cho cùng `lineId` không được thực hiện hai lần nếu contract yêu cầu một lần.

Tại Inventory Gateway/handler, idempotency key có thể là:

~~~text
(commandId, lineId, "RESERVE_STOCK")
~~~

Đó là khóa thiết kế theo nghiệp vụ, không phải `MessageHeaders.id` do framework tạo ở mỗi lần gửi.

## 13. Error channel, retry và các kết quả “chưa chắc chắn”

Khi một item reply chưa đến, có thể có ít nhất bốn tình huống:

1. Request chưa bao giờ rời queue.
2. Request đã tới consumer, consumer lỗi trước khi thực hiện.
3. Consumer đã thực hiện side effect nhưng response bị mất.
4. Consumer trả lời muộn sau deadline.

Chỉ nhìn vào group còn thiếu item **không thể phân biệt được** các tình huống đó. Vì vậy một `BatchOutcome(INCOMPLETE)` nên là tín hiệu để **reconcile**, không phải mặc định chạy lại mọi request.

### 13.1. Retry theo item, không phát lại toàn batch vô tội vạ

Nếu `LINE-1` và `LINE-2` đã có kết quả, chỉ `LINE-3` chưa rõ, cần kiểm tra trạng thái `LINE-3` trước. Retry toàn bộ `OrderBatch` từ đầu có thể làm hệ thống kho nhận lại cả ba lệnh.

Khi retry theo item, cần:

- Timeout và backoff hữu hạn.
- Idempotency tại consumer có side effect.
- Theo dõi số lần thử, request ID và kết quả tra cứu.
- Không tự đổi owner của tác vụ nếu đã có bên nhận/commit.
- Định nghĩa khi nào chuyển từ retry sang manual reconciliation.

### 13.2. `errorChannel` khác `partial result`

Với `DirectChannel`, exception từ handler có thể lan ngược. Với poller/ExecutorChannel/broker, exception có thể được gửi dưới dạng `ErrorMessage` đến error channel theo cấu hình. Một message lỗi kỹ thuật **không tự trở thành** `ItemReply(FAILED)` chỉ vì Aggregator chờ nó.

Nếu muốn Aggregator release đủ phần khi một handler trả lỗi, có thể có **error-to-result adapter** chuyển lỗi đã phân loại thành `ItemReply(FAILED)` theo contract; nhưng cần tránh biến lỗi “không biết carrier/kho đã xử lý hay chưa” thành `FAILED` chắc chắn nếu đó là `UNKNOWN`.

### 13.3. Expiration không phải rollback

Aggregator expire nhóm **không hủy được side effect đã commit** ở các hệ thống bên ngoài. Nếu hai kho đã giữ hàng mà đơn cần cả ba kho đồng ý, việc giải phóng các phần đã giữ có thể đòi **compensating commands**; chúng có thể thất bại và cần retry/observability riêng.

## 14. Gateway request–reply và “không có phản hồi nào”

Một Gateway đồng bộ yêu cầu kết quả cho `OrderBatch` có thể chờ Aggregator. Nếu nhóm expire với partial, nó có thể nhận `BatchOutcome(INCOMPLETE)` *nếu flow reply được thiết kế đúng*. Nếu cấu hình không phát partial và không có nhánh báo lỗi, caller có thể **timeout riêng**.

Cần có một hợp đồng API rõ:

| Tình huống | Response/event theo contract gợi ý |
| --- | --- |
| Đủ replies và tất cả reserved | `BatchOutcome(ALL_REPLIES, ALL_SUCCEEDED)` |
| Đủ replies nhưng có not available | `BatchOutcome(ALL_REPLIES, SOME_FAILED)` |
| Expire khi có một số reply | `BatchOutcome(PARTIAL_EXPIRED, INCOMPLETE)` |
| Không có reply nào | `BatchTimedOut(NO_REPLIES)` từ deadline watcher |
| Bad correlation / spoofed reply | Reject/quarantine và error/audit |
| Downstream timeout không biết kết quả | `RECONCILIATION_REQUIRED`, không tự xác nhận thất bại cuối |

**Quan trọng:** Nếu dùng Gateway, message do Aggregator phát ra phải có reply routing/correlation phù hợp. Qua broker/adapter, `replyChannel` có thể không serializable hoặc không được truyền; cần thiết kế request/reply ID và consumer riêng thay vì chỉ dựa vào một channel object trong header.

## 15. Kiểm thử release hoàn chỉnh với Spring Integration

Dùng `BatchAggregationConfiguration` ở mục 9 với `QueueChannel` nhận output để kiểm chứng **đủ ba ID → một `BatchOutcome` hoàn chỉnh**.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(BatchAggregationConfiguration.class)
class AggregatorCompleteTest {

    @Autowired @Qualifier("inventory.replies.in")
    MessageChannel input;

    @Autowired @Qualifier("inventory.batch.outcomes")
    PollableChannel output;

    @Test
    void releasesOnceAllExpectedItemIdsHaveArrived() {
        GroupContract contract = new GroupContract(
            "RUN-001", "ORD-801",
            Set.of("LINE-1", "LINE-2", "LINE-3"));

        assertTrue(send(contract, "LINE-1", ItemState.RESERVED));
        assertTrue(send(contract, "LINE-2", ItemState.NOT_AVAILABLE));

        // Chưa đủ unique IDs: chưa release nhóm.
        assertNull(output.receive(0));

        assertTrue(send(contract, "LINE-3", ItemState.RESERVED));

        Message<?> message = output.receive(1000);
        assertNotNull(message);
        assertInstanceOf(BatchOutcome.class, message.getPayload());

        BatchOutcome result = (BatchOutcome) message.getPayload();
        assertEquals("RUN-001", result.executionId());
        assertEquals(3, result.expectedCount());
        assertEquals(3, result.receivedCount());
        assertEquals(CompletionState.ALL_REPLIES, result.completeness());
        assertEquals(BusinessOutcome.SOME_FAILED, result.businessOutcome());
        assertTrue(result.missingItemIds().isEmpty());

        assertNull(output.receive(0), "No extra batch outcome");
    }

    private boolean send(
            GroupContract contract, String itemId, ItemState state) {
        ItemReply reply = new ItemReply(
            contract.batchId(), itemId, state, null);

        return input.send(MessageBuilder.withPayload(reply)
            .setHeader("batchContract", contract)
            .setHeader("businessCorrelationId", contract.batchId())
            .build());
    }
}
~~~

### 15.1. Test này chứng minh gì?

- Các replies được đặt vào cùng group nhờ `executionId`.
- Hai reply **chưa đủ** thì không có kết quả complete.
- Đủ cả ba item ID thì release.
- Một reply `NOT_AVAILABLE` làm kết quả nghiệp vụ `SOME_FAILED` dù độ đầy đủ là `ALL_REPLIES`.
- Output là **một kết quả của nhóm**, không phải ba kết quả batch.

Test **không** chứng minh các API kho thật đã ghi transaction, một group store bền khi restart hoặc late reply sẽ bị ngăn. Cần test riêng cho các boundary đó.

### 15.2. Cẩn thận với state test

Nhóm chưa hoàn tất nằm trong MessageGroupStore; Spring Test có thể cache application context. Những test timeout/duplicate khác không nên dùng lại `executionId` và queue cũ mà không reset state. Sử dụng execution ID duy nhất theo test hoặc context/store được cô lập, và cleanup đúng cách để tránh flaky test.

## 16. Kiểm thử partial expiry: phải có scheduler và timeout thật

Bài test partial cần thiết lập timeout ngắn **ở test configuration riêng**, ví dụ vài trăm mili-giây, cùng TaskScheduler phù hợp. Không đổi timeout 30 giây của production chỉ để test và không dùng `Thread.sleep(100)` rồi đoán sự kiện đã xảy ra.

**Kịch bản kiểm thử có thể thực thi:**

~~~text
Given:
  Group RUN-EXP-1 expected LINE-1, LINE-2, LINE-3
  Aggregator configured with groupTimeout=shortTimeout
  sendPartialResultOnExpiry=true
  outputProcessor returns BatchOutcome

When:
  Send LINE-1 and LINE-2
  Do NOT send LINE-3
  Wait for outcome using QueueChannel.receive(timeout)
     with timeout comfortably greater than configured group timeout

Then:
  Exactly one BatchOutcome
  completeness = PARTIAL_EXPIRED
  businessOutcome = INCOMPLETE
  expectedCount = 3
  receivedCount = 2
  missingItemIds = [LINE-3]
  No successful business completion event is emitted
~~~

Đoạn trên là **kịch bản test**, không phải code JUnit đã chạy. Để test chắc chắn, cần xác minh thời điểm kích hoạt `groupTimeout` của phiên bản/framework, cung cấp scheduler, cô lập group store và đợi output theo điều kiện với timeout hữu hạn.

### 16.1. Kiểm thử timeout gần lúc nhận message cuối

Đây là tình huống race quan trọng:

~~~text
T ~ deadline:
  Thread A: nhận reply LINE-3, đủ 3/3
  Thread B: timeout/expiration callback, thấy 2/3
~~~

Hành vi mong muốn phải được xác định bằng **một state transition cuối**: complete **hoặc** partial (theo thứ tự atomic thắng cuộc), **không phát hai final outcomes** cho cùng execution. Cần test ở mức concurrency và store/lock policy thực tế, đặc biệt trong multi-node.

### 16.2. Test late reply sau expiry

Sau khi nhận `PARTIAL_EXPIRED`, gửi reply `LINE-3` cho cùng `executionId`. Assert một trong các hợp đồng đã chọn:

- Late reply được **discard/audit**; không phát batch result mới.
- Late reply được **reconcile**; phát `BatchOutcomeUpdated(version=2)`, không ghi đè sự kiện version 1 không có dấu vết.
- Nếu chưa có late-handling trong demo, test **phải làm lộ** nguy cơ tạo group mới, không được tuyên bố production đã an toàn.

### 16.3. Test zero replies từ deadline watcher

Không gửi message nào vào Aggregator cho `RUN-NO-REPLY`. Bộ kiểm thử phải tạo **BatchStarted** trong registry và kích hoạt deadline watcher; assert rằng hệ thống phát `BatchTimedOut(NO_REPLIES)` đúng **một lần**. Không viết test kỳ vọng Aggregator expire một group chưa hề tồn tại.

## 17. Ma trận kiểm thử nâng cao

| Case | Input/trạng thái | Kỳ vọng |
| --- | --- | --- |
| Đủ 1/1 | Một reply đã được mong đợi | Release complete |
| Đủ 3/3, tất cả reserved | Ba ID riêng biệt | `ALL_REPLIES + ALL_SUCCEEDED` |
| Đủ 3/3, một not available | Ba replies nhưng một thất bại nghiệp vụ | `ALL_REPLIES + SOME_FAILED` |
| Nhận 2/3 rồi timeout | LINE-3 không về | `PARTIAL_EXPIRED + INCOMPLETE` |
| 0/3 replies | Chưa có group | Batch deadline watcher phát timeout |
| 1/3 rồi error | Child handler ném exception | Error flow và partial/reconcile đúng contract |
| Duplicate LINE-1 | Có hai message cùng item ID | Không tính thành hai unique replies |
| Conflicting duplicate | LINE-1 vừa RESERVED vừa FAILED | Quarantine/reconcile; không chọn bừa |
| Out-of-order | LINE-3, LINE-1, LINE-2 | Release đúng; không phụ thuộc arrival order |
| Wrong correlation ID | Reply bị gắn `RUN-OTHER` | Không nhập nhầm nhóm |
| Header contract mismatch | Hai replies cùng group nhưng expected set khác | Reject/alert trước aggregation |
| Filter drop một child | Không có ItemRejected | Timeout hoặc sinh kết quả rejection theo policy |
| Late reply sau expiry | LINE-3 đến ở giây 31 | Không tạo final outcome thứ hai |
| Late reply sau complete | Duplicate gửi lại | Không lập group mới gây output sai |
| Batch bị retry | Một số kho đã commit | Không lặp side effect |
| Restart khi còn 2/3 | Store in-memory vs persistent | Phù hợp recovery contract |
| Scheduler dừng | Không kích hoạt expiry | Có monitoring/alert cho oldest group |
| Reaper và timer cùng chạy | Hai cơ chế expire cạnh tranh | Không phát hai final outcomes |
| Group vượt kích thước | Batch 100.000 item | Quota/chunk/backpressure |
| Caller Gateway chờ reply | Partial hoặc no replies | Response/error đúng SLA, không chờ mãi |
| Multi-node cùng xử lý group | Hai instance thấy replies | Lock/store/idempotency đúng |

**Không chỉ đo line coverage.** Một suite đáng tin cần xác nhận **lifecycle transitions, race conditions và tính chất “không phát kết quả cuối hai lần”**, kể cả khi một số child bị mất hoặc đến muộn.

## 18. Observability: đo group còn mở và nhóm hết hạn

Nếu chỉ log `aggregator output=OK`, bạn sẽ không biết hệ thống đã chờ bao nhiêu item và item nào mất phản hồi. Cần phân biệt bốn loại tín hiệu:

| Điểm đo | Tín hiệu | Ý nghĩa |
| --- | --- | --- |
| Splitter | Batch count, expected item count | Số phần phải được xử lý |
| Child handlers | Send/accepted/processed, retry, error | Trạng thái mỗi item |
| Aggregator | Open groups, received unique parts, age | Batch đang chờ gì |
| Timeout/expiry | Partial count, missing count, timeout reason | Nhóm hết hạn vì sao |
| MessageGroupStore | Store size, oldest group, cleanup lag | Nguy cơ leak/persistence lag |
| Late-handler | Late arrivals, reconciled, discarded | Phản hồi đến sau khi đóng |
| Final outcome | Complete/partial/failed, business result | Kết quả được báo cáo cho caller |
| Reaper/scheduler | Tick success, last scan time, expiry failures | Cơ chế dọn dẹp có hoạt động không |

**Metric tags:** `completeness`, `businessOutcome`, `endpoint`, `errorCategory` là các nhãn thường có cardinality thấp. `batchId`, `executionId`, `lineId`, `correlationId` thường có cardinality cao; nên lưu trong log/trace có quyền truy cập thay vì metric tags.

### 18.1. Một log quyết định hữu ích

~~~json
{
  "event": "aggregation_expired",
  "executionId": "RUN-001",
  "batchId": "ORD-801",
  "expectedCount": 3,
  "receivedCount": 2,
  "missingItemIds": ["LINE-3"],
  "completionState": "PARTIAL_EXPIRED",
  "businessOutcome": "INCOMPLETE"
}
~~~

Trong production, hãy xét bảo mật dữ liệu: ID và business metadata có thể là thông tin nhạy cảm; không log toàn bộ payload, thông tin thanh toán, token hoặc PII ở từng bước chỉ để debug timeout.

### 18.2. Channel send khác business completion

Một `postSend(sent=true)` trên channel nhận reply chỉ phản ánh send ở ranh giới đó. Một message đi tới `inventory.batch.outcomes` cũng **không chứng minh** consumer kết quả cuối đã lưu xong hoặc xử lý bù trừ đã hoàn tất. Hãy đo outcome tại nơi **chịu trách nhiệm nghiệp vụ** và giữ idempotency theo execution/event.

## 19. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ dùng `group.size() == expectedCount` | Duplicate làm release sớm dù thiếu item khác | Đếm unique item IDs và kiểm tra expected set |
| Coi `PARTIAL_EXPIRED` là `SUCCESS` | Bỏ qua phần chưa biết | Tách completeness và business outcome |
| Không có timeout/cleanup | Group tồn mãi trong store | Group timeout/reaper/deadline watcher phù hợp |
| Chỉ dùng group timeout cho case 0 replies | Không có group để expire | Deadline watcher từ `BatchStarted` |
| Coi `groupTimeout` là deadline tuyệt đối từ batch creation | Timeout sai SLA | Lưu deadline đáng tin cậy và test timing |
| Xóa group rồi quên late replies | Late message tạo group mới | Closed registry/tombstone, late path |
| Retry toàn batch khi một item mất reply | Side effect lặp ở item đã thành công | Retry theo item và idempotency |
| Dùng `correlationId` làm business dedup key | Reprocess có thể tạo trùng hoặc gom sai | Operation ID/line ID và execution ID riêng |
| Tắt partial nhưng không có error/reply | Gateway chờ timeout không kiểm soát | Explicit timeout/rejection response |
| Error channel không trả ItemResult mà vẫn chờ đủ | Aggregator không bao giờ release | Error-to-result hoặc timeout/reconciliation |
| Cho hai instance expire cùng group không có coordination | Hai final outcomes hoặc mất dữ liệu | Shared store, locking/CAS, idempotent emission |
| Dùng in-memory MessageStore cho SLA vượt restart | Mất nhóm khi restart | Persistent MessageGroupStore nếu cần |
| Tưởng `sequenceSize` bảo đảm tất cả child đều xử lý | Không phát hiện mất message/duplicate | Theo dõi từng item và business ACK |
| Không giới hạn group/item count | Store/heap đầy và throughput giảm | Quota, chunking, backpressure |
| Ghi toàn bộ payload/PII khi timeout | Rò rỉ dữ liệu | Log reason/ID tối thiểu, phân quyền |

## 20. Checklist trước khi triển khai

- [ ] Mỗi batch có một **execution ID** duy nhất và danh sách item ID mong đợi đáng tin cậy.
- [ ] Correlation strategy và release strategy được kiểm thử với duplicates/out-of-order.
- [ ] Có contract riêng cho **độ đầy đủ** và **kết quả nghiệp vụ**.
- [ ] Group timeout, deadline nghiệp vụ, reaper và group cleanup không bị nhầm với nhau.
- [ ] Quyết định rõ có phát partial result hay không, caller xử lý partial thế nào.
- [ ] Trường hợp **không có reply nào** được deadline watcher xử lý.
- [ ] Mỗi child có error/retry/reconciliation riêng; không tự động retry cả batch.
- [ ] Late reply sau completion/expiration có chính sách discard, reconcile hoặc update có version.
- [ ] Có cơ chế chặn **hai final outcomes** cho cùng execution khi timeout cạnh tranh với reply cuối.
- [ ] Với multi-instance, group store, locks, transactions và TaskScheduler được điều phối phù hợp.
- [ ] Group store có TTL/retention/cleanup và quan sát oldest-group age.
- [ ] Có idempotency key ổn định ở handler tạo side effect.
- [ ] Gateway request–reply có timeout/error response rõ, không chờ vô hạn.
- [ ] Có unit tests của policy và integration tests của Aggregator lifecycle.
- [ ] Có metrics/logging cho incomplete/late/duplicate/reaper nhưng không lộ dữ liệu nhạy cảm.

## 21. Bài tập thực hành

Một hệ thống tổng hợp báo giá bảo hiểm gửi yêu cầu tới ba nhà cung cấp `P1`, `P2`, `P3`. Một báo giá có `quoteId`, `providerId`, `price` và `validUntil`. API công khai có SLA 8 giây. Một nhà cung cấp có thể phản hồi sau 12 giây; có lúc hệ thống không nhận reply nào.

**Yêu cầu:**

1. Định nghĩa `QuoteBatch(executionId, requestedProviders, deadlineAt)` và `QuoteReply(providerId, ...)`.
2. Viết correlation strategy theo `executionId`, release strategy theo tập `providerId` đã nhận chứ không chỉ `group.size()`.
3. Thiết kế policy **đủ 3/3**, **partial 2/3**, **0 replies** và **lỗi giá trị báo giá** (giá âm, hết hạn) theo contract rõ ràng.
4. Cấu hình Aggregator có timeout/partial policy phù hợp; giải thích vì sao 8 giây từ lúc tạo request có thể cần deadline watcher riêng.
5. Khi `P3` trả reply ở giây thứ 12, quyết định ignore, update v2 hay reconcile; đảm bảo không có hai “final response” không có version.
6. Thiết kế MessageGroupStore nếu bắt buộc khôi phục nhóm qua restart. Nêu TaskScheduler, cleanup/reaper và monitoring.
7. Viết các test: 3/3, 2/3 timeout, 0/3, duplicate P1, P3 đến muộn, out-of-order và race gần deadline.
8. Nếu nhiều replica cùng nhận replies, bạn kiểm soát quyền release/expire như thế nào?
9. Phân biệt `QuoteBatchResult(ALL_REPLIES, SOME_FAILED)` với `QuoteBatchResult(PARTIAL_EXPIRED, INCOMPLETE)`; khi nào được trả kết quả tối ưu cho người dùng?
10. Đề xuất logging/metrics không ghi số hợp đồng hoặc thông tin cá nhân làm metric tag.

**Gợi ý:** `Gateway → Recipient List gửi request → Outbound Gateways → Reply channels → Aggregator → QuoteBatchOutcome`, kèm deadline watcher và một **execution-state registry** để xử lý 0 reply/late reply. Nếu provider trả lỗi kỹ thuật, cần phân biệt `FAILED` (đã biết outcome) với `UNKNOWN` (chưa biết tác vụ đã xảy ra hay chưa).

## 22. Tổng kết

**Expire group và xử lý phần chưa hoàn tất** là phần quan trọng để Aggregator không giữ nhóm mãi mãi hoặc phát kết quả sai. Cần hiểu **khi nào nhóm đủ điều kiện release, khi nào timeout/expiry phải can thiệp, có được phát partial hay không, và kết quả partial có nghĩa gì với nghiệp vụ**. Một `BatchOutcome` tốt không chỉ chứa các replies đã nhận mà còn ghi **item nào thiếu, độ đầy đủ, trạng thái nghiệp vụ, execution ID**.

Trong Spring Integration, `correlationStrategy` và `releaseStrategy` xác định nhóm/điều kiện hoàn tất; `groupTimeout`, `sendPartialResultOnExpiry`, `expireGroupsUponCompletion` và cơ chế cleanup/reaper giúp quản lý vòng đời nhóm theo cấu hình. Nhưng **không có group thì per-group timeout không tự phát hiện 0 replies; xóa group cũng không tự chặn late reply**. Vì vậy các workflow có SLA nghiêm ngặt cần thêm deadline watcher, closed-state/tombstone, idempotency, retry/reconciliation theo item, MessageGroupStore phù hợp và kiểm thử concurrency để không mất dữ liệu hoặc phát hai kết quả cuối cho cùng một batch.

**Tài liệu tham khảo:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Aggregator, Message Sequence, Correlation Identifier, Splitter); tài liệu Spring Integration về Aggregator, Message Groups, MessageGroupStore, MessageGroupStoreReaper, Java DSL, Error Handling và Testing; Java SE về `Set`, `Map`, `AtomicReference` và concurrency primitives.

