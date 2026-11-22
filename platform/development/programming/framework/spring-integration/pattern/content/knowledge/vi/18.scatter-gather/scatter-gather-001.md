# Scatter-Gather gửi một yêu cầu đến nhiều nhánh

## 1. Bài toán: một yêu cầu cần nhiều kết quả trước khi quyết định

Một hệ thống đặt hàng nhận yêu cầu `ConfirmOrder(orderId, customerId, quantity)`. Trước khi trả lời **đơn đã được xác nhận**, hệ thống phải kiểm tra ít nhất hai điều kiện độc lập:

1. **Inventory**: kho có thể giữ đủ số lượng hàng hay không?
2. **Fraud**: yêu cầu có vượt qua kiểm tra rủi ro hay không?

Nếu chỉ gọi Inventory rồi lập tức xác nhận, yêu cầu có thể vẫn chưa được Fraud phê duyệt. Nếu chỉ phát một event cho cả hai bên mà không thu kết quả, hệ thống biết rằng đã **gửi yêu cầu**, nhưng chưa biết đã **đủ điều kiện xác nhận**.

**Scatter–Gather** là Enterprise Integration Pattern giải quyết bài toán **phân tán một yêu cầu đến nhiều nhánh xử lý (scatter)** và **thu thập kết quả liên quan để đưa ra câu trả lời chung (gather)**. Trong Spring Integration, mô hình này có thể kết hợp Recipient List/Publish–Subscribe với Aggregator và Gateway, đồng thời có hỗ trợ Scatter–Gather chuyên dụng.

~~~mermaid
flowchart LR
    C[Caller] --> G[Gateway]
    G --> S{Scatter}
    S --> I[Inventory check]
    S --> F[Fraud check]
    I --> RI["InventoryReply"]
    F --> RF["FraudReply"]
    RI --> A[Gather / Aggregator]
    RF --> A
    A --> P{Decision policy}
    P -->|Đủ hai PASS| OK["CONFIRMED"]
    P -->|Có FAIL| NO["REJECTED"]
    P -->|Thiếu reply| TO["PENDING / TIMED_OUT"]
    OK --> C
    NO --> C
    TO --> C
~~~

Chìa khóa của pattern là: **những nhánh đang trả lời cùng một request phải được gom đúng nhóm**, và hệ thống phải có quy tắc rõ **khi nào đủ kết quả**, **thiếu kết quả thì làm gì**, **reply trùng/đến muộn xử lý ra sao**.

Bài thuộc chương **Scatter gather** của module `SPRING_INTEGRATION_PATTERN`. Module hướng dẫn triển khai Enterprise Integration Patterns với Spring Integration để xây dựng các message flow ít phụ thuộc, dễ mở rộng; kết hợp Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation và kiểm thử/quan sát từng nhánh.

### Mục tiêu bài học

Sau khi hoàn thành, bạn có thể:

1. Giải thích rõ hai pha scatter và gather, phân biệt **phát yêu cầu** với **nhận đủ reply**.
2. Phân biệt Scatter–Gather với Recipient List, Publish–Subscribe, Splitter và Content-Based Router.
3. Thiết kế request/reply payload, `requestId`, `recipientId` và expected recipient set.
4. Cấu hình flow Java DSL có Gateway, hai nhánh và logic tổng hợp kết quả.
5. Giải thích correlation, sequence headers, release strategy, timeout và message group.
6. Kiểm thử success, rejected, missing, duplicate, foreign và late replies.
7. Thiết kế retry, error channel, idempotency, backpressure và observability theo đúng mốc xử lý.

## 2. Hai pha của Scatter–Gather

### 2.1. Scatter: phân phối một yêu cầu đến những nhánh cần trả kết quả

**Scatter** là bước lấy một request logic, quyết định tập nhánh sẽ xử lý và phát message tới mỗi nhánh đó. Ví dụ:

~~~text
CheckOrder(requestId=REQ-1001, orderId=ORD-1001)
     |
     +--> InventoryCheck(REQ-1001, ORD-1001)
     |
     +--> FraudCheck(REQ-1001, ORD-1001)
~~~

Một điểm quan trọng: scatter là **one-to-many về đích xử lý**. Không mặc định rằng việc gửi được thực hiện đồng thời trên nhiều thread. Với `DirectChannel`, các handler có thể chạy đồng bộ trong call stack của publisher. Khi dùng `ExecutorChannel`, broker hoặc các consumer riêng, nhánh có thể xử lý bất đồng bộ. **Fan-out không tự đồng nghĩa parallel execution hoặc durable delivery.**

### 2.2. Gather: kết hợp các reply thuộc cùng yêu cầu

Mỗi nhánh phải tạo một **reply mang định danh đủ để biết nó thuộc yêu cầu nào và do ai trả**:

~~~text
InventoryReply(
  requestId=REQ-1001,
  recipientId=inventory,
  outcome=PASS)

FraudReply(
  requestId=REQ-1001,
  recipientId=fraud,
  outcome=PASS)
~~~

Gatherer nhận cả hai và có thể đưa ra:

~~~text
CombinedDecision(
  requestId=REQ-1001,
  confirmed=true,
  inventory=PASS,
  fraud=PASS)
~~~

Nếu Fraud trả `FAIL`, kết quả chung phải phản ánh đúng chính sách. Nếu Fraud không có reply, **không được tự quy đổi “không phản hồi” thành “PASS”**.

### 2.3. “Một yêu cầu” khác “một message duy nhất”

Ở mức nghiệp vụ, chỉ có một `REQ-1001`. Ở mức messaging:

- Gateway tạo một message request.
- Scatterer tạo/gửi thông điệp tương ứng đến các recipient.
- Mỗi handler có thể tạo message reply mới.
- Aggregator lưu và phát một message kết quả.
- Adapter có thể tạo lại message/hệ thống ID trên các ranh giới.

Vì vậy, **`MessageHeaders.ID` không phải khóa nghiệp vụ bền vững cho toàn bộ hành trình**. Nên dùng `requestId` trong payload/metadata và áp dụng correlation phù hợp; nếu có broker, cần mapping header rõ ràng.

## 3. Khác gì với các mẫu liên quan?

| Mẫu | Câu hỏi nó trả lời | Có tự gom reply? |
|---|---|---|
| **Publish–Subscribe** | “Một event cần thông báo cho những subscriber nào?” | Không mặc định. |
| **Recipient List Router** | “Message cần được gửi đến những channel nào?” | Không mặc định. |
| **Content-Based Router** | “Dựa trên payload, message đi tới nhánh nào?” | Không mặc định. |
| **Splitter** | “Một payload lớn được chia thành những phần nào?” | Không; cần Aggregator nếu muốn gom. |
| **Aggregator** | “Khi nào và bằng cách nào gom các message cùng nhóm?” | Có ở mức gom, nhưng không tự làm scatter. |
| **Scatter–Gather** | “Gửi một yêu cầu đến nhiều nhánh và chờ/tổng hợp kết quả ra sao?” | Đó chính là phần gather được cấu hình. |
| **Routing Slip** | “Message cần đi qua chuỗi bước nào?” | Không mặc định; chủ yếu là lộ trình tuần tự. |

### 3.1. Không nên dùng Scatter–Gather cho mọi fan-out

Khi `OrderCreated` được gửi tới Audit, Email, Analytics và caller **không cần đợi cả ba**, một Publish–Subscribe Channel hoặc Recipient List có recovery riêng từng nhánh có thể đơn giản hơn. Ngược lại, nếu **Inventory và Fraud là điều kiện để xác nhận đơn**, kết quả của cả hai phải tham gia quyết định; đó là nhu cầu Scatter–Gather rõ ràng.

### 3.2. Không đồng nhất Scatter với Splitter

~~~text
Scatter–Gather:
  Một order check request
    -> Inventory check cùng order
    -> Fraud check cùng order
    -> gather hai kết quả khác loại

Splitter–Aggregator:
  Batch gồm 100 order lines
    -> 100 WorkItem messages
    -> process từng item
    -> aggregate 100 kết quả
~~~

Hai mô hình đều có fan-out/fan-in, nhưng **Scatter–Gather thường đưa cùng một yêu cầu nghiệp vụ tới nhiều chuyên gia/nhánh**, còn Splitter chia dữ liệu thành phần. Trong một flow thực tế, chúng có thể kết hợp.

### 3.3. Parallelism là một quyết định độc lập

Các nhánh xử lý có thể:

- **Đồng bộ:** dễ debug, nhưng một nhánh chậm có thể chặn toàn bộ đường gửi.
- **Bất đồng bộ trong JVM:** giảm ràng buộc thread gọi nhưng có executor saturation, queue và error handling riêng.
- **Phân tán qua broker/HTTP:** cách ly tiến trình tốt hơn nhưng cần reply correlation, timeout, retry, idempotency, durability/ack và xử lý response muộn.

Chọn cơ chế thực thi theo latency/SLO và mức cách ly lỗi, không dựa đơn thuần vào tên “Scatter–Gather”.

## 4. Thiết kế hợp đồng request/reply trước khi viết DSL

### 4.1. Các trường tối thiểu

| Entity | Field quan trọng | Vì sao cần? |
|---|---|---|
| `CheckOrderRequest` | `requestId`, `orderId`, `quantity`, `amountVnd` | Xác định yêu cầu và dữ liệu cho từng nhánh. |
| `BranchReply` | `requestId`, `recipientId`, `outcome`, `reasonCode` | Ghép đúng nhóm, phát hiện nhánh nào đã phản hồi. |
| `CombinedDecision` | `requestId`, `status`, `resultsByRecipient` | Câu trả lời cuối có đủ căn cứ. |
| `ExpectedRecipients` | `{inventory, fraud}` | Biết tập nhánh **phải** có reply, không chỉ đếm tổng message. |
| `deadline` | Mốc phải kết luận/đổi trạng thái. | Không để group và Gateway chờ vô hạn. |
| `attemptId` (nếu retry) | ID lần thử trên từng recipient. | Phân biệt duplicate với retry có chủ đích. |

Ở ví dụ này, `requestId` là khóa của **một lần yêu cầu kiểm tra**. Nếu một đơn được kiểm tra lại sau khi sửa dữ liệu, nên tạo request mới hoặc version/attempt mới theo contract; không để reply cũ của lần kiểm tra trước trộn vào nhóm mới.

### 4.2. Expected recipient set phải chính xác

Trong bài ta chọn cố định:

~~~text
expectedRecipients = {inventory, fraud}
~~~

Nếu một workflow khác chỉ cần Inventory, không được giữ `expectedCount=2` rồi chờ Fraud mãi. Nếu một yêu cầu thực tế chọn `{inventory, fraud, compliance}`, phải chốt **tập ba recipient thực sự được scatter** và cho gather biết tập đó.

Chỉ dùng `expectedCount=2` có thể bị đánh lừa:

~~~text
Nhận: inventory PASS
Nhận: inventory PASS  (duplicate)
Chưa nhận: fraud

messageCount = 2
uniqueRecipientCount = 1
complete = false
~~~

**Khi kết quả có thể đến trùng hoặc đến từ nhánh không mong đợi, điều kiện release dựa vào tập recipient duy nhất an toàn hơn điều kiện chỉ dựa vào số lượng.**

### 4.3. Quy tắc nghiệp vụ minh họa

| Inventory | Fraud | Kết luận |
|---|---|---|
| PASS | PASS | `CONFIRMED` |
| FAIL | PASS | `REJECTED` |
| PASS | FAIL | `REJECTED` |
| FAIL | FAIL | `REJECTED` |
| PASS | Chưa phản hồi | `PENDING` hoặc `TIMED_OUT` theo deadline |
| Chưa phản hồi | PASS | `PENDING` hoặc `TIMED_OUT` |
| Duplicate Inventory PASS, chưa có Fraud | Không đủ kết quả | Không `CONFIRMED` |

Một số nghiệp vụ có thể **fail-fast** khi một nhánh trả FAIL, nhưng phải hiểu những nhánh còn lại có thể vẫn đang xử lý. Phải xử lý kết quả muộn và side effect của chúng, không giả định fail-fast tự động hủy tất cả.

## 5. Correlation, sequence và release strategy

### 5.1. Correlation ID để gom đúng nhóm

Spring Integration có các header sequence/correlation phục vụ routing, splitter và aggregation trong những cấu hình tương ứng, thường gồm:

- `correlationId`: nhận diện một message group.
- `sequenceNumber`: vị trí một phần trong sequence.
- `sequenceSize`: kích thước sequence khi được xác định.

Scatterer/Gatherer cần tạo hoặc truyền thông tin nhóm phù hợp. **Không mặc định header `correlationId` luôn bằng payload `requestId`** hoặc tự có sau mọi loại adapter. Nếu dựa vào correlation của framework, hãy kiểm tra cấu hình cụ thể của Scatter–Gather và header mapping qua các ranh giới.

### 5.2. Một requestId khác một traceId

| ID | Chức năng |
|---|---|
| `requestId` | Nhóm các kết quả của **một lần kiểm tra**. |
| `orderId` | Thực thể nghiệp vụ có thể được kiểm tra nhiều lần. |
| `traceId` | Liên kết các bước quan sát xuyên service/thread. |
| `correlationId` | Khóa nhóm được Aggregator sử dụng theo cấu hình. |
| `recipientId` | Phân biệt InventoryReply với FraudReply. |
| `MessageHeaders.ID` | ID của một message cụ thể; không bền qua mọi conversion/replay. |

Ví dụ cùng một `traceId` có thể chứa nhiều lần thử của cùng order; dùng traceId làm group ID mà không thêm request/attempt ID có thể gom nhầm.

### 5.3. Release strategy quyết định lúc nào gather đủ

Một Aggregator có hai trách nhiệm liên quan nhưng khác nhau:

1. **Correlation strategy:** message nào thuộc cùng một group?
2. **Release strategy:** khi nào group được phép phát kết quả?

Nếu release chỉ kiểm tra `group.size() == 2`, nó **chưa tự chứng minh** có đủ hai recipient khi duplicate có thể tồn tại, hoặc không có một reply lạ. Một chiến lược nghiệp vụ vững hơn phải nhìn `recipientId`, `requestId` và loại kết quả được chấp nhận; kiểm soát duplicate và foreign replies trước khi quyết định.

### 5.4. Message group không phải database giao dịch

Aggregator có thể dùng `MessageGroupStore` để giữ reply đang chờ và quản lý expiration. Tùy cấu hình, group store có thể nằm trong memory hoặc bền vững. **Đừng suy từ tên Aggregator rằng group tự tồn tại qua JVM crash, tự replay reply hoặc bảo đảm exactly-once.**

Muốn phục hồi sau crash cần xem xét:

- Store có durable không và transaction boundary thế nào?
- Group đã release/expired được dọn và tombstone ra sao?
- Reply đến muộn có bị xem là group mới không?
- Broker ack trước hay sau khi reply được lưu vào group?
- Retry một nhánh có tạo duplicate outcome/side effect không?

## 6. Domain model cho một yêu cầu đi qua nhiều nhánh

### 6.1. Dùng DTO rõ identity và outcome

Ví dụ hướng tới **Java 17+, Spring Boot 3.x, Spring Integration 6.x** cùng `spring-boot-starter-integration`. Các type trong những khối code dưới đây được hiểu là thuộc cùng package; khi đưa vào dự án, hãy tách những type `public` thành các file Java theo quy tắc ngôn ngữ.

~~~java
import java.math.BigDecimal;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

record CheckOrderRequest(
        String requestId,
        String orderId,
        int quantity,
        BigDecimal amountVnd) {

    CheckOrderRequest {
        if (requestId == null || requestId.isBlank()
                || orderId == null || orderId.isBlank()
                || quantity <= 0 || amountVnd == null
                || amountVnd.signum() <= 0) {
            throw new IllegalArgumentException("INVALID_CHECK_REQUEST");
        }
    }
}

enum BranchVerdict {
    PASS, FAIL
}

record BranchReply(
        String requestId,
        String recipientId,
        BranchVerdict verdict,
        String reasonCode) {

    BranchReply {
        if (requestId == null || requestId.isBlank()
                || recipientId == null || recipientId.isBlank()) {
            throw new IllegalArgumentException("INVALID_REPLY_ID");
        }
        Objects.requireNonNull(verdict, "verdict");
    }
}

enum DecisionStatus {
    CONFIRMED, REJECTED
}

record CombinedDecision(
        String requestId,
        DecisionStatus status,
        Map<String, BranchReply> repliesByRecipient) {

    CombinedDecision {
        Objects.requireNonNull(requestId, "requestId");
        Objects.requireNonNull(status, "status");
        repliesByRecipient = Map.copyOf(repliesByRecipient);
    }
}
~~~

Ở đây `CombinedDecision` chỉ tồn tại khi **đã có kết quả đầy đủ và hợp lệ**. Trạng thái `PENDING`/`TIMED_OUT` được mô tả bằng loại phản hồi khác hoặc error/recovery workflow ở phần sau. Không tạo `CONFIRMED` rồi để `repliesByRecipient` thiếu một nhánh.

### 6.2. Tại sao `recipientId` phải nằm trong reply?

Hai branch có thể trả cùng cấu trúc dữ liệu `PASS` hoặc `FAIL`. Nếu chỉ nhận:

~~~text
PASS
PASS
~~~

gatherer không biết đây là hai nhánh khác nhau, hay cùng Inventory gửi lại hai lần. Vì vậy reply cần có:

~~~text
{requestId: "REQ-1", recipientId: "inventory", verdict: "PASS"}
{requestId: "REQ-1", recipientId: "fraud", verdict: "PASS"}
~~~

**Không tin recipientId do client ngoài tự đặt tùy ý.** Trong flow nội bộ, branch handler biết identity của mình và tạo reply dựa trên logic phía server. Với reply qua broker/HTTP, cần xác thực nguồn, phân quyền và kiểm tra payload/schema.

### 6.3. Tách nhánh xử lý khỏi quyết định chung

Một nhánh chỉ nên biết trách nhiệm riêng:

~~~java
final class InventoryCheck {
    BranchReply check(CheckOrderRequest request) {
        boolean enoughStock = request.quantity() <= 10;
        return new BranchReply(
                request.requestId(),
                "inventory",
                enoughStock ? BranchVerdict.PASS : BranchVerdict.FAIL,
                enoughStock ? "STOCK_OK" : "INSUFFICIENT_STOCK");
    }
}

final class FraudCheck {
    private static final BigDecimal REVIEW_LIMIT =
            new BigDecimal("10000000");

    BranchReply check(CheckOrderRequest request) {
        boolean acceptable =
                request.amountVnd().compareTo(REVIEW_LIMIT) <= 0;
        return new BranchReply(
                request.requestId(),
                "fraud",
                acceptable ? BranchVerdict.PASS : BranchVerdict.FAIL,
                acceptable ? "RISK_OK" : "RISK_REVIEW_REQUIRED");
    }
}
~~~

Hai quy tắc này **chỉ để minh họa**: Inventory không truy vấn kho thật; Fraud không phải bộ máy chống gian lận production. Chúng trả reply một cách xác định để dễ kiểm thử pattern mà không cần gọi API ngoài.

### 6.4. Không cho nhánh tự quyết định kết luận của toàn đơn

Nếu Inventory trả PASS, nó chỉ xác nhận **điều kiện tồn kho theo contract Inventory**. Không nên để nó trả `CONFIRMED` cho toàn order, vì Fraud có thể FAIL. Quyết định chung thuộc về **decision policy sau gather**, khi đã biết đúng tập reply.

## 7. Decision combiner: đối chiếu reply trước khi ra kết luận

### 7.1. Luật gom kết quả

Giả sử mỗi yêu cầu cần **đúng một kết quả cuối** từ Inventory và Fraud. Ta cần:

- Hai `recipientId` thuộc allowlist.
- Cùng một `requestId` mong đợi.
- Không có duplicate recipient.
- Không thiếu recipient.
- Mỗi reply có `verdict` hợp lệ.
- `CONFIRMED` chỉ khi cả hai PASS.
- Ngược lại, khi đủ hai reply nhưng có FAIL, trả `REJECTED`.

~~~java
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

final class ReplyCombiner {
    static final Set<String> REQUIRED =
            Set.of("inventory", "fraud");

    CombinedDecision combine(
            String requestId, Collection<BranchReply> replies) {

        if (requestId == null || requestId.isBlank()) {
            throw new IllegalArgumentException("INVALID_REQUEST_ID");
        }
        Objects.requireNonNull(replies, "replies");

        Map<String, BranchReply> byRecipient =
                new LinkedHashMap<>();

        for (BranchReply reply : replies) {
            Objects.requireNonNull(reply, "reply");
            if (!requestId.equals(reply.requestId())) {
                throw new IllegalArgumentException(
                        "FOREIGN_REQUEST_REPLY");
            }
            if (!REQUIRED.contains(reply.recipientId())) {
                throw new IllegalArgumentException(
                        "UNEXPECTED_RECIPIENT");
            }
            if (byRecipient.putIfAbsent(
                    reply.recipientId(), reply) != null) {
                throw new IllegalArgumentException(
                        "DUPLICATE_RECIPIENT_REPLY");
            }
        }

        if (!byRecipient.keySet().equals(REQUIRED)) {
            throw new IllegalStateException(
                    "INCOMPLETE_RECIPIENT_RESULTS");
        }

        boolean allPassed = byRecipient.values().stream()
                .allMatch(reply ->
                        reply.verdict() == BranchVerdict.PASS);

        return new CombinedDecision(
                requestId,
                allPassed
                        ? DecisionStatus.CONFIRMED
                        : DecisionStatus.REJECTED,
                byRecipient);
    }
}
~~~

### 7.2. Tại sao không đơn giản dùng `allMatch(PASS)`?

~~~java
// Anti-pattern: chỉ đọc những reply đã đến.
boolean confirmed = replies.stream()
        .allMatch(r -> r.verdict() == BranchVerdict.PASS);
~~~

Với collection chỉ chứa Inventory PASS, kết quả trên là `true`, dù Fraud chưa trả lời. Với collection **rỗng**, `allMatch` cũng trả `true` theo quy tắc logic của stream. Do đó **phải kiểm tra completeness trước**.

Tương tự:

~~~java
boolean complete = replies.size() == 2;
~~~

vẫn sai khi collection có hai Inventory replies mà không có Fraud.

### 7.3. Duplicate là lỗi dữ liệu hoặc vận chuyển cần xử lý

Trong ví dụ, `ReplyCombiner` **từ chối duplicate**, giúp test dễ bắt lỗi. Production có thể **deduplicate có chủ đích** nếu dùng broker at-least-once, nhưng cần:

1. Khóa kết quả gồm `requestId + recipientId` và một `attemptId` nếu chính sách retry cho phép nhiều lần.
2. Quy tắc chọn kết quả có thẩm quyền: final-only, version mới nhất, CAS first-commit hoặc status machine.
3. Audit và metric cho duplicate; không im lặng đếm thành một recipient mới.
4. Kiểm tra hai reply trùng có kết luận **mâu thuẫn** hay không.
5. Idempotency ở side effect trước khi tạo reply.

Đừng cứ lấy reply “đến cuối” làm đúng nếu không biết attempt ordering, trạng thái commit và transport delay.

### 7.4. Fail-fast có thể là một chính sách khác

Nếu Inventory FAIL, một số hệ thống muốn trả REJECTED ngay mà không cần chờ Fraud. Điều này **khác luật wait-for-all của mã ví dụ**. Với fail-fast:

- Vẫn cần biết các nhánh đã dispatch và có thể còn in-flight.
- Không giả định cancel Future hoặc Gateway timeout sẽ rollback hoạt động ở nhánh khác.
- Cần lưu/giải quyết late reply, group state và side effect.
- Hợp đồng phản hồi phải nói rõ kết quả sớm có được coi **final** không.

Bài này ưu tiên **wait-for-all** để thể hiện rõ Scatter–Gather; fail-fast được xem là bài toán mở rộng có rủi ro khác.

## 8. Unit test combiner trước khi tích hợp framework

### 8.1. Trường hợp đủ hai PASS

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReplyCombinerSuccessTest {
    private final ReplyCombiner combiner = new ReplyCombiner();

    private static BranchReply reply(
            String branch, BranchVerdict verdict) {
        return new BranchReply(
                "REQ-1", branch, verdict, "TEST");
    }

    @Test
    void bothRecipientsPassReturnsConfirmed() {
        CombinedDecision result = combiner.combine(
                "REQ-1",
                List.of(
                        reply("inventory", BranchVerdict.PASS),
                        reply("fraud", BranchVerdict.PASS)));

        assertEquals(DecisionStatus.CONFIRMED, result.status());
        assertEquals(2, result.repliesByRecipient().size());
        assertEquals("REQ-1", result.requestId());
    }

    @Test
    void arrivalOrderDoesNotAffectDecision() {
        CombinedDecision result = combiner.combine(
                "REQ-1",
                List.of(
                        reply("fraud", BranchVerdict.PASS),
                        reply("inventory", BranchVerdict.PASS)));

        assertEquals(DecisionStatus.CONFIRMED, result.status());
    }
}
~~~

Kết quả có cùng meaning dù thứ tự reply là Fraud → Inventory hay ngược lại. Trong một hệ thống bất đồng bộ, **không dựa vào thứ tự nhận** để phân biệt hai nhánh.

### 8.2. Một nhánh FAIL, kết quả chung REJECTED

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReplyCombinerRejectTest {
    private final ReplyCombiner combiner = new ReplyCombiner();

    @Test
    void fraudFailureMakesCombinedDecisionRejected() {
        CombinedDecision decision = combiner.combine(
                "REQ-7",
                List.of(
                        new BranchReply("REQ-7", "inventory",
                                BranchVerdict.PASS, "STOCK_OK"),
                        new BranchReply("REQ-7", "fraud",
                                BranchVerdict.FAIL, "RISK_DENIED")));

        assertEquals(DecisionStatus.REJECTED,
                decision.status());
        assertEquals(BranchVerdict.FAIL,
                decision.repliesByRecipient().get("fraud").verdict());
    }
}
~~~

### 8.3. Kiểm thử thiếu, trùng và sai request

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;

class ReplyCombinerInvalidTest {
    private final ReplyCombiner combiner = new ReplyCombiner();

    @Test
    void inventoryOnlyCannotConfirmTheOrder() {
        assertThrows(IllegalStateException.class, () ->
                combiner.combine("REQ-8", List.of(
                        new BranchReply("REQ-8", "inventory",
                                BranchVerdict.PASS, "OK"))));
    }

    @Test
    void twoInventoryRepliesCannotSubstituteFraud() {
        BranchReply inventory = new BranchReply(
                "REQ-9", "inventory", BranchVerdict.PASS, "OK");

        assertThrows(IllegalArgumentException.class, () ->
                combiner.combine("REQ-9",
                        List.of(inventory, inventory)));
    }

    @Test
    void foreignRequestResultIsRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                combiner.combine("REQ-10", List.of(
                        new BranchReply("REQ-10", "inventory",
                                BranchVerdict.PASS, "OK"),
                        new BranchReply("REQ-OLD", "fraud",
                                BranchVerdict.PASS, "OK"))));
    }

    @Test
    void unknownRecipientIsRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                combiner.combine("REQ-11", List.of(
                        new BranchReply("REQ-11", "inventory",
                                BranchVerdict.PASS, "OK"),
                        new BranchReply("REQ-11", "analytics",
                                BranchVerdict.PASS, "OK"))));
    }

    @Test
    void emptyResultSetCannotBecomeConfirmed() {
        assertThrows(IllegalStateException.class, () ->
                combiner.combine("REQ-12", List.of()));
    }
}
~~~

Những test này chỉ kiểm tra **kết quả sau khi đã nhận được collection reply**. Chúng chưa kiểm tra Spring Integration scatterer có phát tới hai nhánh, reply có quay về gatherer, gateway có timeout đúng, hay broker có giữ correlation. Đó là nội dung của integration tests phía sau.

## 9. Triển khai Scatter–Gather trong Spring Integration

### 9.1. Vai trò của các thành phần framework

Spring Integration có thành phần `ScatterGatherHandler` và các API Java DSL tương ứng giúp xây dựng luồng scatter/gather. Về mặt kiến trúc:

~~~text
MessagingGateway
  |
  v
order.checks.input
  |
  v
ScatterGatherHandler
  |
  +-- Scatter: RecipientListRouter / PublishSubscribeChannel
  |       +-- Inventory service
  |       +-- Fraud service
  |
  +-- Gather: AggregatingMessageHandler
          -> release strategy
          -> output processor / combined decision
          -> reply to Gateway
~~~

**Hai kiểu scatter phổ biến** là dùng danh sách recipient (có thể chọn theo điều kiện) hoặc phát tới những subscriber của một Publish–Subscribe Channel. Dù chọn cách nào, gather phải biết **kết quả từ những recipient nào được trông đợi**, nhận message reply chứ không chỉ sự kiện đã gửi, và có timeout/error policy.

### 9.2. Ví dụ Java DSL: hai recipient flows, một kết quả

Để tập trung vào pattern, hai nhánh dùng service đồng bộ trong cùng JVM và trả `BranchReply`. Không có database, HTTP hay broker thật. Đây là một **cấu hình minh họa theo phong cách Java DSL Spring Integration 6.x**; khi đưa vào dự án cần kiểm tra chữ ký DSL và behavior của phiên bản dependency đang dùng, đặc biệt đối với `scatterGather`, `recipientFlow`, `releaseStrategy` và `outputProcessor`.

~~~java
import java.util.List;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;

@MessagingGateway
interface OrderCheckGateway {
    @Gateway(
            requestChannel = "order.checks.input",
            replyTimeout = 5000)
    CombinedDecision evaluate(CheckOrderRequest request);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class ScatterGatherOrderConfiguration {

    @Bean
    InventoryCheck inventoryCheck() {
        return new InventoryCheck();
    }

    @Bean
    FraudCheck fraudCheck() {
        return new FraudCheck();
    }

    @Bean
    ReplyCombiner replyCombiner() {
        return new ReplyCombiner();
    }

    @Bean
    IntegrationFlow scatterGatherOrders(
            InventoryCheck inventory,
            FraudCheck fraud,
            ReplyCombiner combiner) {

        return IntegrationFlow.from("order.checks.input")
                .scatterGather(
                        scatterer -> scatterer
                                .recipientFlow(flow -> flow
                                        .handle(
                                                CheckOrderRequest.class,
                                                (request, headers) ->
                                                        inventory.check(request)))
                                .recipientFlow(flow -> flow
                                        .handle(
                                                CheckOrderRequest.class,
                                                (request, headers) ->
                                                        fraud.check(request))),
                        gatherer -> gatherer
                                .releaseStrategy(group -> {
                                    Set<String> seen =
                                            group.getMessages().stream()
                                                    .map(Message::getPayload)
                                                    .map(BranchReply.class::cast)
                                                    .map(BranchReply::recipientId)
                                                    .collect(
                                                            java.util.stream.Collectors
                                                                    .toSet());
                                    return seen.containsAll(
                                            ReplyCombiner.REQUIRED);
                                })
                                .outputProcessor(group -> {
                                    List<BranchReply> replies =
                                            group.getMessages().stream()
                                                    .map(Message::getPayload)
                                                    .map(BranchReply.class::cast)
                                                    .toList();
                                    if (replies.isEmpty()) {
                                        throw new IllegalStateException(
                                                "NO_BRANCH_REPLIES");
                                    }
                                    return combiner.combine(
                                            replies.get(0).requestId(),
                                            replies);
                                }))
                .get();
    }
}
~~~

**Ý nghĩa từng phần:**

1. Gateway nhận `CheckOrderRequest` và cần **một** `CombinedDecision`.
2. Scatterer tạo đường đến **hai recipient flows** độc lập: Inventory và Fraud.
3. Mỗi handler **phải trả `BranchReply`**, thay vì chỉ làm side effect rồi `return null`.
4. Release strategy chờ đến khi thấy cả `inventory` và `fraud`. Nó không release chỉ vì tổng số reply bằng hai.
5. Output processor chuyển tập reply thành quyết định nghiệp vụ qua `ReplyCombiner`, tiếp tục kiểm tra ID, duplicate và foreign recipients.
6. Sau gather, kết quả hoàn tất theo reply path của Gateway; caller không nhận một danh sách message thô nếu contract chỉ cần `CombinedDecision`.

### 9.3. Điều kiện để code trên có ý nghĩa đúng

Ở một flow thật, **metadata correlation mà gatherer dùng để group** phải được scatterer phát và các branch reply phải giữ đúng đường return/correlation. Nếu thêm một Transformer tạo lại message, một outbound adapter hoặc custom handler làm mất `replyChannel`, `correlationId` hoặc sequence headers cần thiết, reply có thể không quay về group mà Gateway đang chờ.

Vì vậy, code mẫu tập trung vào request/reply **trong một application context**. Khi chuyển sang HTTP/Kafka/JMS/AMQP phải bổ sung adapter-level test, reply destination, durable correlation store nếu cần, và timeout/recovery. Không tự suy luận có thể serialize nguyên `replyChannel` object của một JVM sang process khác.

### 9.4. Vì sao release strategy chưa đủ để giải quyết duplicate?

Release strategy trong ví dụ chờ đủ **hai recipient ID duy nhất**. Nếu Inventory gửi reply **hai lần** rồi Fraud trả một lần, group có thể có ba message và vẫn đạt điều kiện release. Sau đó `ReplyCombiner` **ném lỗi duplicate**: kết quả không được công bố là thành công.

Đây là lựa chọn **fail closed để phát hiện bug**, không phải hệ thống deduplication hoàn chỉnh. Production có thể cần lọc duplicate **trước** Aggregator hoặc thiết kế một group processor chấp nhận một final result/recipient theo khóa idempotency và attempt/version, tùy delivery semantics. Không đặt release strategy `group.size() >= 2` nếu hoàn cảnh có thể có duplicate.

### 9.5. Điểm cuối của recipient flow phải tạo reply

Nếu nhánh Inventory viết:

~~~java
// One-way endpoint: không trả lời Gatherer.
.handle(message -> {
    inventoryClient.reserve(message.getPayload());
})
~~~

thì yêu cầu có thể đã gây side effect ở kho nhưng gatherer không có `InventoryReply` để đưa ra quyết định. Khi thiết kế Scatter–Gather, hãy:

- Định nghĩa loại reply cụ thể của từng recipient.
- Chỉ báo PASS khi nghiệp vụ nhánh đã đáp ứng contract, không chỉ khi message được nhận.
- Nêu rõ nếu một nhánh có tác vụ dài hạn: trả PENDING hay chờ đến deadline?
- Không trả `null` rồi chờ Aggregator tự tạo kết quả.
- Nếu handler sinh ra nhiều reply, phải định nghĩa liệu một recipient có được có nhiều kết quả hay không.

### 9.6. Tại sao không dùng một Gateway gọi hai service tuần tự?

Gọi tuần tự Inventory rồi Fraud có thể là cách **đơn giản và đúng** khi nghiệp vụ nhỏ, latency thấp và không cần mở rộng độc lập. Scatter–Gather có thêm những lợi ích/chi phí:

| Cách tiếp cận | Lợi thế | Hạn chế |
|---|---|---|
| Service tuần tự | Dễ hiểu, transaction/error path ngắn. | Latency có thể cộng dồn, phụ thuộc trực tiếp vào thứ tự service. |
| Scatter–Gather đồng bộ | Tách hai nhánh, hợp đồng gom rõ. | Vẫn có thể chạy trong thread gọi, latency chịu ảnh hưởng các handler. |
| Scatter–Gather bất đồng bộ | Có thể xử lý song song, cách ly thread. | Correlation, timeout, queue, late reply, error recovery khó hơn. |
| Workflow orchestrator bền vững | Quản lý công việc dài hạn, retries, human approvals. | Chi phí thiết kế/vận hành cao hơn. |

Đừng chọn Scatter–Gather chỉ vì có hai hàm cần gọi. Chọn khi **hợp đồng nhiều nhánh và tập reply** thực sự là một phần quan trọng của kiến trúc.

## 10. Integration test cho flow Scatter–Gather

### 10.1. Hai nhánh cùng PASS

~~~java
import java.math.BigDecimal;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(ScatterGatherOrderConfiguration.class)
class ScatterGatherHappyPathTest {
    @Autowired
    OrderCheckGateway gateway;

    @Test
    void oneRequestProducesTwoRepliesAndOneDecision() {
        CheckOrderRequest request = new CheckOrderRequest(
                "REQ-A", "ORD-A", 2, new BigDecimal("5000000"));

        CombinedDecision result = gateway.evaluate(request);

        assertEquals("REQ-A", result.requestId());
        assertEquals(DecisionStatus.CONFIRMED, result.status());
        assertEquals(Set.of("inventory", "fraud"),
                result.repliesByRecipient().keySet());
        assertEquals(BranchVerdict.PASS,
                result.repliesByRecipient().get("inventory").verdict());
        assertEquals(BranchVerdict.PASS,
                result.repliesByRecipient().get("fraud").verdict());
    }
}
~~~

Test này, khi chạy trên cấu hình Java DSL phù hợp với version Spring Integration của dự án, kiểm tra **cả fan-out, reply-producing handlers, gather, output processor và Gateway reply**. Khác với unit test ở mục 8, nó cần Spring context và cơ chế correlation thật của framework.

### 10.2. Một nhánh FAIL vẫn phải trả một quyết định đúng

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(ScatterGatherOrderConfiguration.class)
class ScatterGatherRejectionTest {
    @Autowired
    OrderCheckGateway gateway;

    @Test
    void fraudRejectsHighValueOrder() {
        CheckOrderRequest request = new CheckOrderRequest(
                "REQ-B", "ORD-B", 2, new BigDecimal("15000000"));

        CombinedDecision decision = gateway.evaluate(request);

        assertEquals(DecisionStatus.REJECTED, decision.status());
        assertEquals(BranchVerdict.PASS,
                decision.repliesByRecipient().get("inventory").verdict());
        assertEquals(BranchVerdict.FAIL,
                decision.repliesByRecipient().get("fraud").verdict());
    }

    @Test
    void inventoryRejectsQuantityAboveAvailableStock() {
        CheckOrderRequest request = new CheckOrderRequest(
                "REQ-C", "ORD-C", 12, new BigDecimal("5000000"));

        CombinedDecision decision = gateway.evaluate(request);

        assertEquals(DecisionStatus.REJECTED, decision.status());
        assertEquals(BranchVerdict.FAIL,
                decision.repliesByRecipient().get("inventory").verdict());
        assertEquals(BranchVerdict.PASS,
                decision.repliesByRecipient().get("fraud").verdict());
    }
}
~~~

Ở đây `REJECTED` là một **business outcome hợp lệ** đã được cả hai branch đánh giá, khác với **technical failure** như lookup timeout, handler exception hoặc missing reply.

### 10.3. Những gì test đồng bộ chưa chứng minh

Đây là demo dùng services trong JVM, không có hệ thống ngoài. Các test trên **chưa** chứng minh:

- Hai nhánh thực sự chạy song song về thời gian.
- Reply có thể đi qua message broker rồi quay đúng group.
- Group tồn tại qua crash/restart.
- Duplicate và retry không tạo side effect.
- Gateway trả PENDING/TIMED_OUT theo hợp đồng khi thiếu một reply.
- Thread pool/reply queue hoạt động đúng khi bị quá tải.
- Metrics và error channel được quan sát đúng.

Các phần sau bổ sung kế hoạch kiểm thử cho những trường hợp này mà không nhầm accepted/dispatch với completed.

## 11. Một nhánh không phản hồi: timeout không phải PASS

### 11.1. Chuyện gì xảy ra khi Fraud không reply?

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Gateway
    participant S as Scatter
    participant I as Inventory
    participant F as Fraud
    participant A as Gatherer
    C->>G: CheckOrder REQ-20
    G->>S: Dispatch request
    S->>I: Inventory check
    S->>F: Fraud check
    I-->>A: inventory PASS
    Note over F: Timeout / không có reply
    Note over A: Chưa có Fraud result
    A--xG: Không thể phát complete decision
    G-->>C: Timeout hoặc pending theo contract
~~~

Nếu gatherer đòi đủ hai recipient, **một Inventory PASS chưa đủ để tạo `CONFIRMED`**. Với Gateway đồng bộ, request có thể chờ đến `replyTimeout` và gặp timeout. Nhưng timeout của Gateway **không chắc đồng thời hết hạn message group** hoặc hủy task Fraud.

### 11.2. Phân biệt ba deadline

| Loại thời gian | Câu hỏi | Điểm cấu hình liên quan |
|---|---|---|
| **Branch timeout** | Inventory/Fraud được gọi trong bao lâu? | HTTP client, DB, outbound gateway, broker request/reply. |
| **Gather/group timeout** | Khi nào group không đủ reply phải expire/release/đi recovery? | Aggregator/group store/expiry strategy. |
| **Caller/Gateway reply timeout** | Caller sẵn sàng chờ bao lâu? | MessagingGateway, HTTP ingress, SLA. |

Không nhất thiết cả ba timeout có cùng giá trị. Ví dụ một Gateway chờ 3 giây, nhưng một Fraud consumer chỉ trả sau 5 giây: caller đã timeout còn Fraud vẫn có thể tiếp tục. Nếu group store vẫn giữ group, phải có chiến lược giải phóng, hết hạn hoặc xử lý late reply.

**Sai lầm nguy hiểm:** Bắt exception timeout rồi trả `CONFIRMED` cho caller vì Inventory đã PASS. Đó là vi phạm chính sách hai điều kiện bắt buộc.

### 11.3. Chính sách khi thiếu kết quả

Các lựa chọn hợp lệ tùy nghiệp vụ:

1. **Fail closed:** trả `TIMED_OUT`/`CANNOT_CONFIRM`, không xác nhận đơn.
2. **PENDING:** tạo operation ID, cho caller kiểm tra trạng thái sau; hợp lý khi nghiệp vụ cho phép xử lý dài hơn HTTP request.
3. **Partial result:** báo rõ Inventory PASS, Fraud MISSING, tuyệt đối không trình bày như kết luận đầy đủ.
4. **Retry Fraud:** retry đúng nhánh theo deadline, max attempts và idempotency.
5. **Manual review:** đưa request sang hàng chờ theo policy nếu không thể xác minh tự động.

Không có lựa chọn “luôn tốt nhất” nếu chưa biết điều kiện xác nhận và yêu cầu SLO.

### 11.4. Một DTO cho báo cáo thiếu kết quả

Nếu cần báo cáo khi deadline hết, tách nó khỏi `CombinedDecision`:

~~~java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

record IncompleteCheckReport(
        String requestId,
        Set<String> responded,
        Set<String> missing,
        String status) {}

final class MissingReplyInspector {
    IncompleteCheckReport inspect(
            String requestId,
            Collection<BranchReply> observed) {

        Set<String> responded = new LinkedHashSet<>();
        for (BranchReply reply : observed) {
            if (!requestId.equals(reply.requestId())) {
                throw new IllegalArgumentException("FOREIGN_REPLY");
            }
            if (!ReplyCombiner.REQUIRED.contains(
                    reply.recipientId())) {
                throw new IllegalArgumentException(
                        "UNEXPECTED_RECIPIENT");
            }
            responded.add(reply.recipientId());
        }

        Set<String> missing =
                new LinkedHashSet<>(ReplyCombiner.REQUIRED);
        missing.removeAll(responded);

        return new IncompleteCheckReport(
                requestId,
                Set.copyOf(responded),
                Set.copyOf(missing),
                missing.isEmpty() ? "ALL_REPLIED" : "INCOMPLETE");
    }
}
~~~

Đây chỉ là **hàm ứng dụng kiểm tra tập reply đã quan sát**. Nó không tự chờ, không tự cấu hình `groupTimeout`, cũng không tự tạo `ErrorMessage`. Vì vậy test Inspector không được dùng để tuyên bố timeout của Scatter–Gather framework đã hoạt động.

### 11.5. Test thiếu reply mà không chờ thật

~~~java
import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MissingReplyInspectorTest {
    @Test
    void inventoryOnlyLeavesFraudMissing() {
        IncompleteCheckReport report =
                new MissingReplyInspector().inspect(
                        "REQ-55",
                        List.of(new BranchReply(
                                "REQ-55", "inventory",
                                BranchVerdict.PASS, "OK")));

        assertEquals(Set.of("inventory"), report.responded());
        assertEquals(Set.of("fraud"), report.missing());
        assertEquals("INCOMPLETE", report.status());
    }
}
~~~

## 12. Đồng bộ, bất đồng bộ và fan-out thực sự song song

### 12.1. Đồng bộ: một nhánh chậm có thể chặn cả request

Nếu hai nhánh đều dùng `DirectChannel` và handler xử lý đồng bộ, thời gian của đường gửi có thể bị ảnh hưởng bởi thời gian của từng nhánh. Dù sơ đồ phân thành hai đường, không nên hứa “hai cuộc gọi luôn chạy song song” chỉ vì đã cấu hình Scatter–Gather.

Ví dụ Inventory mất 50 ms, Fraud mất 2 giây. Trong cấu hình đồng bộ, caller có thể phải đợi gần 2 giây hoặc hơn, tùy thứ tự dispatch và cách thực hiện branch handlers. Đừng coi thời gian đơn giản là `max(50ms, 2s)` trong mọi cấu hình nếu thực chất xử lý nối tiếp.

### 12.2. Bất đồng bộ: nhanh hơn nhưng khó hơn

Một kiến trúc có executor/broker:

~~~mermaid
flowchart TB
    G[Gateway] --> S[Scatter]
    S --> Q1[(inventory.requests)]
    S --> Q2[(fraud.requests)]
    Q1 --> W1[Inventory Worker]
    Q2 --> W2[Fraud Worker]
    W1 --> R1[(inventory.replies)]
    W2 --> R2[(fraud.replies)]
    R1 --> C[Correlated Gatherer]
    R2 --> C
    C --> D[Combined Decision / Timeout]
~~~

Lợi ích:

- Hai worker có thể xử lý độc lập và cùng lúc.
- Có thể cấp thread pool, queue và retry policy riêng.
- Có thể tách tiến trình khi dùng broker/adapter.

Đổi lại:

- `send` thành công có thể chỉ là đã enqueue.
- Queue đầy, executor từ chối task hoặc broker mất kết nối cần đường lỗi riêng.
- Worker có thể crash sau commit nhưng trước khi gửi reply.
- Reply có thể đến sai thứ tự, trùng, mất hoặc đến sau deadline.
- Nếu group store in-memory, một JVM crash có thể làm mất trạng thái gather.
- Một message từ hệ thống khác phải có correlation/reply destination có thể truyền qua transport.

### 12.3. TaskExecutor không đồng nghĩa durable broker

Nếu thêm `TaskExecutor` vào scatter channel, handler có thể chạy trên worker thread. Nhưng các task trong bộ nhớ **không tự lưu bền vững qua JVM restart**. Và một executor **dùng chung** cho Fraud/Inventory có thể bị nhánh chậm chiếm hết worker, gây starve nhánh còn lại.

Khi cần cách ly mạnh hơn, có thể đặt recipient sau **queue/broker riêng**, kèm consumer capacity, retry, DLQ và idempotency theo từng nhánh. Nhưng “broker” cũng không tự có chính sách durability/ack/retention thích hợp nếu chưa cấu hình.

### 12.4. Khi nào Gateway nên trả ngay?

Nếu kiểm tra Fraud mất hàng phút hoặc cần người phê duyệt, giữ một Gateway đồng bộ chờ đủ reply có thể không hợp lý. Thay vì vậy:

~~~text
POST /check-orders
  -> 202 Accepted
  -> requestId / status URL

Workers process asynchronously
  -> Gatherer updates durable status

GET /check-orders/{requestId}
  -> PENDING / CONFIRMED / REJECTED / TIMED_OUT
~~~

Mẫu này vẫn dùng scatter/gather ở tầng xử lý nhưng **hợp đồng API** được chuyển thành eventual result. Đó là thay đổi kiến trúc có chủ đích, không phải thuộc tính mặc định của `@MessagingGateway`.

## 13. Error handling: một nhánh thất bại ảnh hưởng gì?

### 13.1. Một nhánh ném exception khác một nhánh trả FAIL

Giả sử Fraud trả:

~~~java
new BranchReply(
        "REQ-100",
        "fraud",
        BranchVerdict.FAIL,
        "RISK_DENIED");
~~~

Đây là **kết quả nghiệp vụ** và có thể được gatherer dùng để đưa ra `REJECTED`. Trái lại:

~~~java
throw new IllegalStateException("Fraud service unavailable");
~~~

là **lỗi kỹ thuật**, thường **không tạo `BranchReply` bình thường** trừ khi error flow được thiết kế rõ để chuyển lỗi thành một result có status thích hợp. Khi nhánh ném exception:

- Trong flow đồng bộ, exception có thể lan truyền tới sender/Gateway.
- Trong flow bất đồng bộ, lỗi có thể đi vào `ErrorMessage`/`errorChannel` hoặc error handler tùy adapter/poller/executor.
- Một branch đã được scatter nhưng không có reply có thể khiến group thiếu kết quả.
- Các branch khác có thể đã tạo side effect trước khi lỗi xảy ra.

Không tự bắt mọi exception và biến thành `PASS` để “đủ số kết quả”.

### 13.2. Ma trận lỗi theo tầng

| Tầng | Lỗi ví dụ | Biện pháp |
|---|---|---|
| **Input** | Thiếu requestId/amount, quantity sai. | Validation trước scatter; không tạo N requests từ input malformed. |
| **Scatter** | Recipient không có consumer, channel không tồn tại. | Config/readiness check, dispatch error, fallback có kiểm soát. |
| **Executor/queue** | Queue full, task rejected. | Backpressure/bounded retry/overload status, không silent drop. |
| **Branch** | Inventory HTTP timeout, Fraud service unavailable. | Retry riêng, deadline, error/recovery, idempotency. |
| **Reply transport** | Reply mất hoặc sai correlation header. | Correlation mapping, durable replies, late reply policy. |
| **Gather** | Duplicate, unexpected recipient, group expired. | Dedupe/quarantine, release và cleanup policy. |
| **Decision** | Data mismatch hoặc status không hợp lệ. | Từ chối kết luận, audit, không Confirm. |
| **Gateway** | Reply timeout trước gather. | Contract PENDING/TIMED_OUT; không giả định task đã cancel. |

### 13.3. `errorChannel` không tự tạo một reply hợp lệ

Trong Spring Integration, `ErrorMessage` có thể mang exception để error flow xử lý. Tuy nhiên, **không phải mọi lỗi được tự động gửi vào mọi `errorChannel`**, và **một ErrorMessage không đương nhiên thỏa contract `BranchReply`**. Nếu muốn gatherer vẫn trả kết quả tổng hợp khi một nhánh lỗi:

1. Định nghĩa branch result có trạng thái `ERROR`/`UNAVAILABLE` hoặc một trạng thái nghiệp vụ phù hợp.
2. Chuyển lỗi thành branch result **đúng requestId + recipientId** chỉ khi điều đó được cho phép trong hợp đồng.
3. Phân biệt **branch technical error** với **business FAIL**; không đánh đồng.
4. Quyết định fail-fast, wait-for-all hoặc partial-result theo policy và deadline.
5. Đảm bảo error flow không lặp vô hạn khi chính nó cũng lỗi.

Ví dụ, một hệ thống có thể trả `CANNOT_CONFIRM_INVENTORY_UNAVAILABLE` thay vì `REJECTED_FRAUD`. Cả hai đều không phải `CONFIRMED`, nhưng khác nhau về nguyên nhân và khả năng retry.

### 13.4. Retry ở đâu?

**Không mặc định retry cả Scatter–Gather** khi chỉ Fraud lỗi. Một lần retry toàn request có thể khiến Inventory được gọi lại dù đã thành công, và nếu Inventory đã giữ hàng, có thể tạo **reservation kép**.

Thiết kế thường an toàn hơn:

~~~text
REQ-200
  inventory -> PASS (reservationId=R-1)
  fraud     -> TIMEOUT

Retry policy:
  inventory -> giữ outcome cũ nếu còn hiệu lực
  fraud     -> retry trong giới hạn
~~~

Chú ý outcome Inventory còn hiệu lực hay không cũng là quy tắc nghiệp vụ: giữ hàng có thể hết hạn, số lượng thay đổi hoặc reservation bị hủy. Không luôn tái sử dụng Inventory PASS vô thời hạn.

### 13.5. Idempotency và compensation

Nếu một branch chỉ **đọc trạng thái**, retry thường ít rủi ro side effect hơn. Nếu Inventory **reserve stock**, Fraud **ghi một record kiểm tra**, việc gọi lại có thể làm phát sinh trạng thái mới.

Vì thế:

- Dùng operation key ổn định theo `requestId + recipientId` hoặc một reservation ID được hệ thống đích hỗ trợ.
- Dùng retry attempt ID riêng để quan sát các lần gọi.
- Thiết kế timeout với outcome không chắc chắn: tra cứu/reconcile trước khi lặp reservation.
- Nếu Fraud FAIL sau khi Inventory đã reserve, có thể cần **release reservation/compensation**.
- Không giả định Scatter–Gather tạo transaction phân tán bao trùm cả hai nhánh.

## 14. Số nhánh thay đổi theo message: expected recipients không được hardcode

### 14.1. Khi nào chỉ có hai nhánh và khi nào có ba?

Ở ví dụ trước, mọi yêu cầu đều cần `inventory` và `fraud`. Trong thực tế, đơn quốc tế có thể cần thêm `compliance`:

~~~text
Đơn VN:
  expectedRecipients = {inventory, fraud}

Đơn INTL:
  expectedRecipients = {inventory, fraud, compliance}
~~~

Một Recipient List Router có thể lựa chọn recipients tùy điều kiện. **Gatherer phải biết đúng tập đã scatter**, nếu không:

- Yêu cầu VN có thể chờ Compliance không tồn tại.
- Yêu cầu INTL có thể release sau hai reply rồi bỏ qua Compliance bắt buộc.
- Retry/resend có thể phát recipient khác với bản request ban đầu nếu policy thay đổi giữa chừng.

### 14.2. Lập kế hoạch recipient trước khi scatter

Có thể định nghĩa một plan bất biến:

~~~java
import java.util.Set;

record ScatterPlan(
        String requestId,
        String policyVersion,
        Set<String> expectedRecipients) {

    ScatterPlan {
        if (requestId == null || requestId.isBlank()
                || policyVersion == null || policyVersion.isBlank()) {
            throw new IllegalArgumentException("INVALID_SCATTER_PLAN");
        }
        expectedRecipients = Set.copyOf(expectedRecipients);
        if (expectedRecipients.isEmpty()) {
            throw new IllegalArgumentException("NO_RECIPIENTS");
        }
    }
}

final class RecipientPlanner {
    ScatterPlan plan(String requestId, String market) {
        return switch (market) {
            case "VN" -> new ScatterPlan(
                    requestId, "policy-v1",
                    Set.of("inventory", "fraud"));
            case "INTL" -> new ScatterPlan(
                    requestId, "policy-v1",
                    Set.of("inventory", "fraud", "compliance"));
            default -> throw new IllegalArgumentException(
                    "UNSUPPORTED_MARKET");
        };
    }
}
~~~

Đây là **Java policy minh họa**, không phải config DSL đầy đủ cho dynamic Recipient List trong Spring Integration. Khi áp dụng:

1. Planner phải chọn recipient từ **allowlist đáng tin**.
2. Scatterer phải thực sự gửi đến **đúng những recipient đã chọn**.
3. Gatherer phải nhận đúng plan hoặc expected set và không tự đoán lại bằng policy “latest”.
4. Plan cần có version nếu policy thay đổi khi request vẫn đang chạy.
5. Với fail-fast/retry, không tự giảm expected set sau khi một recipient bị lỗi.

### 14.3. Snapshot policy tránh thay đổi nửa đường

~~~text
T1: Request REQ-1 lập plan v1
    expected = {inventory, fraud}

T2: Cấu hình đổi sang policy v2
    expected cho yêu cầu mới = {inventory, fraud, compliance}

T3: REQ-1 nhận đủ inventory và fraud
~~~

Nếu gatherer lấy **policy v2** để tính expected set cho REQ-1 ở T3, nó sẽ chờ một Compliance reply **chưa từng được scatter**. Vì vậy phải dùng expected recipients của **plan đã chốt tại T1** hoặc một cơ chế replan/checkpoint có hợp đồng rõ ràng.

### 14.4. Không fan-out tới channel tùy ý từ payload client

Nếu client tự cung cấp tên channel như `orders.admin.internal` và yêu cầu scatter đến đó, hệ thống có nguy cơ **route injection** hoặc gửi dữ liệu sang nhánh không được phép. Dynamic recipient list cần:

- Xác thực/ủy quyền tại ingress.
- Phân biệt business key với bean/channel name.
- Mapping qua allowlist server-side.
- Giới hạn số recipient để tránh fan-out vô hạn.
- Kiểm soát payload nhạy cảm mỗi recipient được phép xem.
- Ghi policy version và recipient selection trong log/audit thích hợp.

## 15. Correlation khi reply qua nhiều thread hoặc nhiều hệ thống

### 15.1. Cùng request, không cùng thread

Khi Inventory và Fraud chạy trên executor khác nhau, hai reply có thể đến gatherer theo thứ tự bất kỳ:

~~~mermaid
sequenceDiagram
    participant G as Gatherer
    participant I as Inventory
    participant F as Fraud
    I-->>G: Inventory PASS REQ-1
    F-->>G: Fraud PASS REQ-2
    F-->>G: Fraud PASS REQ-1
    I-->>G: Inventory PASS REQ-2
    Note over G: Phải phân thành hai nhóm REQ-1 và REQ-2
~~~

Nếu chỉ dùng thứ tự arrival hoặc cùng `orderId` khi có nhiều lần kiểm tra, group sẽ bị ghép sai. Khi xử lý song song, khóa correlation phải **ổn định và đủ phân biệt**.

### 15.2. Quy tắc tương quan tối thiểu

Mỗi reply nên được kiểm tra:

~~~text
requestId    : không rỗng; nhóm cần trả lời
recipientId  : thuộc expectedRecipients đã chốt
attemptId    : nếu có retry/redelivery cần phân biệt
status       : giá trị hợp lệ của recipient
payload      : đúng schema và identity tham chiếu
traceContext : nếu cần theo dõi xuyên transport
~~~

Với Inventory reply có `reservationId`, cần đảm bảo reservation thuộc đúng `orderId`/`requestId`; chỉ kiểm tra recipientId chưa đủ để chống ghép nhầm dữ liệu giữa đơn khác nhau.

### 15.3. Không serialize nguyên `replyChannel` nội bộ qua broker

Spring Integration Gateway/Scatter–Gather trong cùng JVM có thể sử dụng message headers chứa channel hoặc cơ chế return address nội bộ. Khi qua Kafka, JMS, HTTP, AMQP, một object `MessageChannel` của JVM A **không có ý nghĩa trực tiếp** ở JVM B.

Thay vì thế, xác định:

1. Một **reply topic/queue/endpoint** hợp lệ có consumer gather.
2. Correlation ID/request ID được serialize bằng kiểu có thể chuyển.
3. Header mapper cho phép các metadata cần thiết.
4. Authentication và authorization của reply producer.
5. TTL/retention/dead-letter strategy cho reply đã quá hạn.
6. Group state store có độ bền phù hợp với yêu cầu restart.

### 15.4. Khi reply đến sau deadline

~~~text
12:00:00  Request REQ-9 được scatter
12:00:01  Inventory PASS
12:00:03  Gateway trả TIMED_OUT
12:00:05  Fraud PASS đến gatherer
~~~

Các khả năng xử lý:

- **Late reply bị loại có chủ đích**, ghi metric/audit; không tạo một quyết định thứ hai tới caller đã timeout.
- **Cập nhật trạng thái operation** nếu API cho phép truy vấn/reconciliation sau timeout.
- **Thực hiện compensation** nếu nhánh trước đã tạo side effect nhưng kết quả chung không còn hợp lệ.
- **Gửi event điều chỉnh** nếu downstream cần được thông báo về kết quả cuối.

**Rủi ro:** nếu group cũ đã expire rồi gatherer tạo group mới từ Fraud PASS, không được coi đó là một request mới cần chờ Inventory vô hạn. Cần policy cho **late arrivals và completed/expired group IDs**, không chỉ cleanup memory.

## 16. Kiểm thử bất đồng bộ có kiểm soát

### 16.1. Vì sao `Thread.sleep` không phải tín hiệu hoàn tất

Một test kiểu:

~~~java
gateway.evaluate(request);
Thread.sleep(500);
assertEquals(2, resultCounter.get());
~~~

dễ thất bại không ổn định trên CI vì thread scheduling và tải máy khác nhau. Với kiểm thử Scatter–Gather async, nên dùng:

- `CountDownLatch` để xác nhận handler **đã bắt đầu**.
- Một latch khác để điều khiển **khi nào cho phép trả reply**.
- `Future` để quan sát Gateway có chờ/timed out đúng không.
- `await(timeout)` thay vì ngủ cố định.
- `finally` để luôn giải phóng latch và dọn executor.

### 16.2. Kế hoạch test một nhánh chậm

~~~text
Given:
  Inventory Handler nhanh, trả PASS.
  Fraud Handler đã bắt đầu nhưng chờ release latch.

When:
  Gửi REQ-X qua Gateway trên một thread riêng.
  Chờ Fraud báo started.

Then (trước khi release):
  Gateway chưa có CombinedDecision hoàn tất.
  Gatherer chưa được release.

When:
  Mở release latch cho Fraud trả PASS.

Then:
  Gateway nhận một CombinedDecision CONFIRMED.
  repliesByRecipient có đúng inventory và fraud.
~~~

Không dùng một thread cho cả Gateway đồng bộ và logic điều khiển latch; nếu thread test bị giữ ở `gateway.evaluate(...)`, nó sẽ không thể mở latch đúng lúc.

### 16.3. Test timeout phải có kết quả dự kiến

Khi Fraud không phản hồi:

1. Gửi request ở một thread/future để tránh chặn test.
2. Dùng một deadline hữu hạn cho `Future.get` và Gateway reply timeout.
3. Xác minh không có `CombinedDecision(CONFIRMED)` giả.
4. Kiểm tra trạng thái group hoặc error/recovery đã cấu hình.
5. Thả latch trong `finally` và đảm bảo worker/executor shutdown.
6. Cho Fraud trả late reply sau deadline để kiểm thử late-result policy riêng.

Lưu ý: loại exception của Gateway có thể thay đổi theo config/phiên bản; test nên xác minh **business outcome và cause chain** thay vì phụ thuộc một message text không ổn định.

### 16.4. Test duplicate và reply từ nhóm khác

Nếu framework không có sẵn một cách inject reply trực tiếp qua API phù hợp, có thể tạo một test integration riêng:

- Scatterer giả gửi Inventory PASS hai lần, Fraud chưa trả.
- Gatherer **không** phát CONFIRMED dựa trên hai message đó.
- Khi Fraud trả, group processor xử lý duplicate theo contract (fail closed hoặc dedupe đã cấu hình).
- Reply từ `REQ-OLD` không được đưa vào group `REQ-NEW`.
- Unknown recipient không được tính vào expected set.

Để kiểm tra semantics release/dedupe của `AggregatingMessageHandler`, test cần đi qua cấu hình thật của handler, **không chỉ gọi `ReplyCombiner.combine(...)`**.

### 16.5. Kết quả test phải phân biệt từng mốc

| Assertion | Bằng chứng |
|---|---|
| Scatterer chọn hai recipients | Mỗi handler được gọi/nhận yêu cầu. |
| Broker/executor accepted | Submit/enqueue được thừa nhận theo contract. |
| Branch finished | Có `BranchReply` hợp lệ hoặc failure outcome. |
| Gather completed | Đúng group và release strategy cho kết quả. |
| Gateway returned | Caller nhận `CombinedDecision`/status/error. |
| Side effects committed | Có bằng chứng từ DB/transport/remote service, không chỉ counter. |

Một test chỉ quan sát “handler được gọi” chưa chứng minh được **gather đã kết hợp kết quả**. Ngược lại, chỉ assert Gateway trả `CONFIRMED` có thể không phát hiện duplicate hoặc một branch bị bỏ qua nếu combiner/release strategy thiết kế sai.

## 17. Observability: theo dõi từng nhánh và từng group

### 17.1. Một request phải có thể truy ngược đến từng reply

Sơ đồ vận hành mong muốn:

~~~text
REQ-1001
  SCATTER_PLANNED expected={inventory,fraud}
  RECIPIENT_DISPATCHED inventory
  RECIPIENT_DISPATCHED fraud
  BRANCH_COMPLETED inventory PASS
  BRANCH_COMPLETED fraud PASS
  GATHER_RELEASED uniqueRecipients=2
  DECISION_RETURNED CONFIRMED
~~~

Với request lỗi:

~~~text
REQ-1002
  SCATTER_PLANNED expected={inventory,fraud}
  BRANCH_COMPLETED inventory PASS
  BRANCH_FAILED fraud FRAUD_SERVICE_TIMEOUT
  GATHER_EXPIRED missing={fraud}
  DECISION_UNAVAILABLE status=TIMED_OUT
~~~

Đây là **schema log do ứng dụng đề xuất**, không phải output mặc định của Spring Integration. Không ghi `BRANCH_COMPLETED` ngay khi queue nhận task; phải đợi kết quả theo contract của nhánh.

### 17.2. Structured log fields

| Trường | Mục đích |
|---|---|
| `requestId` | Nối scatter, branch replies và gather trong một lần kiểm tra. |
| `orderId` | Điều tra nghiệp vụ, có thể liên quan nhiều requests. |
| `traceId`/`spanId` | Distributed tracing xuyên thread/service. |
| `recipientId` | Nhánh được gọi, đang chờ hoặc thất bại. |
| `policyVersion` | Phiên bản rule chọn recipient/release. |
| `expectedRecipients` | Tập nhánh được chốt khi scatter. |
| `attemptId` | Phân biệt lần thử khi retry/redelivery. |
| `durationMs` | Latency của branch và toàn request. |
| `outcome`/`reasonCode` | PASS/FAIL/ERROR/TIMED_OUT và nguyên nhân. |
| `groupState` | Waiting, completed, expired theo workflow. |

Không log toàn bộ thông tin khách hàng, token, request payload nhạy cảm hoặc nội dung Fraud score nếu không có quyền và mục đích rõ. Với tracing, cũng cần kiểm tra context propagation khi chuyển sang `TaskExecutor` hoặc transport khác: MDC/thread-local không tự đi theo mọi worker thread.

### 17.3. Metrics cần tách scatter, gather và business result

| Metric minh họa | Tác dụng |
|---|---|
| `scatter_requests_total` | Có bao nhiêu yêu cầu bắt đầu fan-out? |
| `scatter_recipient_dispatch_total{recipient}` | Đã thử gửi đến mỗi nhánh bao nhiêu lần? |
| `branch_completed_total{recipient,outcome}` | Branch có bao nhiêu kết quả cuối? |
| `branch_failed_total{recipient,reason}` | Lỗi kỹ thuật từng nhánh. |
| `branch_latency_seconds{recipient}` | Nhánh nào gây latency cao? |
| `gather_groups_pending` | Bao nhiêu nhóm chưa đủ kết quả? |
| `gather_groups_completed_total` | Bao nhiêu group được release theo policy? |
| `gather_groups_expired_total` | Bao nhiêu group không đủ reply trước deadline? |
| `gather_duplicate_replies_total{recipient}` | Có redelivery/duplicate nhiều không? |
| `scatter_combined_decisions_total{status}` | CONFIRMED/REJECTED và status hợp đồng khác. |
| `reply_late_total{recipient}` | Reply nào đến sau group expiry? |
| `executor_queue_depth` | Worker pool có bão hòa? |

Đây là tên metric **minh họa**, không phải các meter Spring Integration tự động đăng ký trong mọi project. Dùng label cardinality hữu hạn như recipient/status/reason code; **không** dùng `requestId`, `orderId`, `traceId` làm metric labels vì chúng có số giá trị rất lớn. Các ID thuộc log/tracing có retention và quyền truy cập thích hợp.

### 17.4. Message History không thay business audit

Spring Integration Message History có thể cho thấy một message đi qua các component nào khi được bật, nhưng:

- Không tự chứng minh mỗi branch đã commit side effect.
- Không tự lưu expected recipient set cho một request.
- Không tự đối chiếu recipient duplicates hoặc reply sai nhóm.
- Không thay thế distributed tracing qua transport.
- Không tự làm group store bền vững.

Với workflow quan trọng, cần lưu **request context/expected set, reply outcomes, decision version và trạng thái xử lý cuối** ở nơi đáp ứng yêu cầu audit/recovery.

## 18. Ma trận kiểm thử Scatter–Gather

| ID | Kịch bản | Điều cần xác minh |
|---|---|---|
| SG-01 | Một request, Inventory PASS, Fraud PASS | Trả đúng một `CONFIRMED`, đủ hai recipient. |
| SG-02 | Inventory FAIL, Fraud PASS | `REJECTED`, không `CONFIRMED`. |
| SG-03 | Inventory PASS, Fraud FAIL | `REJECTED`, giữ reason của Fraud. |
| SG-04 | Cả hai FAIL | `REJECTED`, không bỏ qua một kết quả. |
| SG-05 | Fraud trả trước Inventory | Kết quả như khi đảo thứ tự. |
| SG-06 | Chỉ Inventory reply | Không release complete decision. |
| SG-07 | Chỉ Fraud reply | Không release complete decision. |
| SG-08 | Hai Inventory replies, Fraud chưa có | Duplicate không thay cho recipient còn thiếu. |
| SG-09 | Reply của request khác | Không ghép vào group hiện tại. |
| SG-10 | Reply từ recipient lạ | Bị từ chối hoặc quarantine theo policy. |
| SG-11 | Một branch trả `null` / one-way | Không tuyên bố all replied; timeout/error rõ. |
| SG-12 | Input thiếu requestId | Validation chặn trước fan-out. |
| SG-13 | Hai requests chạy đồng thời | Không trộn reply, có đúng hai groups. |
| SG-14 | Fraud chậm, Inventory nhanh | Gateway không trả CONFIRMED trước Fraud. |
| SG-15 | Fraud timeout | Deadline/recovery, không ngầm PASS. |
| SG-16 | Late reply sau group expiry | Có policy rõ: bỏ qua, cập nhật status hoặc reconcile. |
| SG-17 | Branch ném technical exception | Phân biệt lỗi kỹ thuật với business FAIL. |
| SG-18 | Executor bão hòa | Rejection/backpressure không silent drop. |
| SG-19 | Recipient channel thiếu consumer | Dispatch failure/timeout được quan sát. |
| SG-20 | Broker redelivery reply | Dedupe/duplicate detection đúng. |
| SG-21 | Worker commit rồi mất ack | Retry không nhân đôi side effect. |
| SG-22 | Gateway timeout trước gather timeout | Group/late reply được xử lý độc lập. |
| SG-23 | Group store reset/restart | Phù hợp durability/recovery contract đã chọn. |
| SG-24 | Đơn INTL thêm Compliance | Expected set chính xác ba recipients. |
| SG-25 | Đơn VN chỉ hai recipients | Không đợi Compliance không được scatter. |
| SG-26 | Thay policy khi một request đang chờ | Expected set chốt lúc scatter không tự đổi. |
| SG-27 | Dữ liệu Fraud trả sai `orderId` | Reconciliation từ chối kết quả sai identity. |
| SG-28 | Reply qua HTTP/Kafka/JMS adapter | Correlation và schema được khôi phục chính xác. |
| SG-29 | Group release nhưng one branch FAIL | Không đánh đồng release với business success. |
| SG-30 | Inventory đã reserve, Fraud FAIL | Compensation/release reservation đúng policy. |
| SG-31 | Recipient List cho một recipient có điều kiện | Expected subset/release logic không hardcode hai. |
| SG-32 | Fail-fast với một FAIL | Những branch đang chạy, late reply và side effect có xử lý. |

### 18.1. Phân chia cấp kiểm thử

| Cấp | Kiểm tra | Không tự chứng minh |
|---|---|---|
| **Unit test branch** | Logic Inventory/Fraud và tạo đúng BranchReply. | Message đã đến gatherer. |
| **Unit test combiner** | Required IDs, duplicate, foreign, PASS/FAIL. | Gateway timeout, group persistence. |
| **Spring Integration test** | Scatterer, subscriber/recipient, correlation, release, output processor, Gateway. | Broker serialization nếu không dùng broker. |
| **Adapter test** | Reply destination, header mapping, transport ack/retry. | Mọi side effect nghiệp vụ nếu chỉ mock. |
| **System test** | Deadline, failover, crash, replay, compensation và status cuối. | Mọi trường hợp lỗi thực tế ngoài phạm vi môi trường test. |

Với những yêu cầu cần độ tin cậy cao, cần kết hợp các tầng. **Unit test combiner không thay integration test**; còn test Gateway happy path không đủ chứng minh duplicate hay timeout đã xử lý đúng.

## 19. Quy trình chẩn đoán một Scatter–Gather bị kẹt

Giả sử Gateway hết timeout còn Fraud chưa được ghi nhận. Một chuỗi điều tra hiệu quả:

1. **Input:** request có hợp lệ, `requestId` có thực sự duy nhất cho lần kiểm tra này không?
2. **Planner:** expected recipient set là gì? Inventory/Fraud/Compliance có được chọn đúng policy version không?
3. **Scatter:** đã dispatch tới từng channel/queue đích chưa? Có rejection, queue full hoặc endpoint stopped không?
4. **Branch started:** Fraud handler có nhận request? Có dừng ở HTTP/DB/gateway nào không?
5. **Branch outcome:** Fraud hoàn tất nhưng không phát `BranchReply`, hay reply sai schema/recipient ID?
6. **Reply transport:** return destination và correlation headers có qua adapter không? Có reply đến một channel không có consumer?
7. **Gather:** reply có vào đúng message group, group đã expire/release chưa, duplicate/foreign có làm policy từ chối không?
8. **Gateway:** caller reply timeout trước gather hay sau? Caller retry có tạo request mới trong khi request cũ còn chạy?
9. **Recovery:** cần retry riêng Fraud, reconcile trạng thái ngoài, hay compensation cho Inventory reservation?
10. **Observability:** lưu dấu nguyên nhân, test hồi quy và cân nhắc alert cho backlog/group age.

Nếu Inventory PASS có log nhưng Fraud không có `BRANCH_STARTED`, ưu tiên kiểm tra scatter/dispatch và consumer readiness, không vội tăng Fraud HTTP timeout. Nếu Fraud hoàn tất nhưng gather không thấy reply, tập trung vào return route/correlation và transport. Nếu cả hai reply đến nhưng group không release, kiểm tra release strategy và message group state.

## 20. Những lỗi thiết kế thường gặp

| Hiểu nhầm | Hậu quả | Cách thiết kế phù hợp |
|---|---|---|
| “Scatter–Gather giống Publish–Subscribe, chỉ cần phát đến nhiều nơi.” | Không có bước thu kết quả và quyết định chung. | Định nghĩa gather/correlation/release/output contract. |
| “Fan-out nghĩa là mọi handler chạy song song.” | Latency cao khi channel/handler đồng bộ. | Kiểm tra execution model, executor và broker. |
| “Hai replies là đủ cho hai recipients.” | Hai duplicate từ Inventory thay cho Fraud. | Kiểm tra **recipientId duy nhất** và expected set. |
| “Reply đầu tiên PASS thì có thể Confirm.” | Bỏ qua Fraud hoặc Compliance. | Wait-for-all hoặc fail-fast được phê duyệt; không confirm thiếu điều kiện. |
| “`group.size()==2` luôn chính xác.” | Duplicate và foreign message làm release sai. | Release theo tập expected và validate reply. |
| “Không có reply nghĩa là nhánh FAIL nghiệp vụ.” | Trộn timeout/transport error với business refusal. | Lỗi kỹ thuật/PENDING/TIMED_OUT riêng, có retry policy. |
| “`send=true` nghĩa là hai nhánh đã xử lý xong.” | API công bố success quá sớm. | Theo dõi dispatched, accepted, completed, gathered, committed. |
| “Gateway timeout làm mọi worker tự hủy.” | Side effect vẫn tiếp tục, reply đến muộn. | Late reply, idempotency và compensation có chủ đích. |
| “Có `errorChannel` là gatherer tự nhận ERROR reply.” | Group thiếu reply và timeout. | Error flow phải trả result theo hợp đồng khi thích hợp. |
| “Dùng `traceId` làm group ID luôn được.” | Nhiều requests trong cùng trace bị trộn. | Dùng request/group ID chuyên biệt và version khi cần. |
| “Khi thêm recipient, chỉ sửa Scatterer.” | Gatherer chờ sai số lượng hoặc release sớm. | Chốt expected recipients cho từng request. |
| “Retry toàn request khi chỉ một nhánh timeout.” | Nhân đôi reservation, email hoặc side effect. | Retry đúng recipient, idempotency/reconciliation. |
| “Group store luôn bền vững.” | Mất state khi restart. | Chọn store/transaction/delivery semantics theo yêu cầu. |
| “Reply channel Java có thể serialize sang Kafka.” | Consumer ở JVM khác không biết đích trả. | Reply topic/queue và correlation header có mapping rõ. |
| “Order ID là đủ để ghép mọi reply.” | Hai lần check cùng order bị trộn. | Request ID + attempt/version theo hợp đồng. |
| “Aggregator release tức là business success.” | Có thể nhận đủ kết quả nhưng một nhánh FAIL. | Tách **completeness** và **decision status**. |
| “`@MessagingGateway` luôn trả một object nếu đã gửi được.” | Timeout hoặc thiếu reply; có thể không có result. | Thiết kế timeout/error/status response rõ. |
| “Một branch FAIL thì các branch khác đã rollback.” | Partial side effect và tồn kho bị giữ. | Compensation hoặc trạng thái saga khi cần. |
| “Thêm branch lạ vào recipient list không sao.” | Rò rỉ dữ liệu sang channel trái phép. | Server-side allowlist/authorization. |
| “Message History chứng minh mọi branch đã commit.” | Không có dữ liệu kết quả nghiệp vụ. | Structured outcome/audit/monitoring riêng. |

## 21. Bài tập thực hành

1. **Fan-out cơ bản:** dùng `InventoryCheck` và `FraudCheck`; gửi một `CheckOrderRequest`, thu hai `BranchReply` và tạo `CombinedDecision`.
2. **Kiểm tra danh tính:** làm Inventory và Fraud cùng trả PASS nhưng khác `requestId`; xác nhận combiner không trả CONFIRMED.
3. **Duplicate:** cho Inventory trả hai lần và Fraud chưa trả. Viết test chứng minh group **không đủ** chỉ vì đã có hai message.
4. **Thứ tự khác nhau:** đảo thứ tự hai replies và chứng minh kết luận không đổi.
5. **Business rejection:** cho Inventory FAIL, Fraud PASS; phân biệt `REJECTED` với exception trong handler.
6. **One-way handler:** thay Fraud handler bằng hàm không trả reply. Quan sát gather/gateway và xác định vì sao message group không hoàn tất.
7. **Java DSL:** cấu hình `scatterGather` với hai `recipientFlow`; kiểm tra cả two-branch replies và output processor của một request.
8. **Dynamic Recipient List:** đơn VN chọn hai recipient, đơn INTL ba recipient. Đảm bảo expected set được chốt theo từng request.
9. **Release strategy:** thử release theo `group.size()==2` và tạo duplicate; thay bằng rule theo recipient identity và so sánh kết quả.
10. **Chạy song song:** đưa hai branch vào executor thích hợp. Dùng latch để chứng minh có thể xử lý đồng thời và Gateway vẫn chờ đủ.
11. **Timeout:** làm Fraud không có reply. Test Gateway deadline, group expiry và không phát CONFIRMED giả.
12. **Late reply:** Fraud trả sau deadline. Thiết kế chính sách bỏ qua, cập nhật status hoặc reconciliation; test không tạo decision trùng.
13. **Retry có kiểm soát:** cho Fraud timeout lần đầu rồi PASS lần hai; chỉ retry Fraud, không gọi lại Inventory khi đã reserve.
14. **Compensation:** Inventory đã reserve, Fraud FAIL. Tạo mô hình release reservation với idempotency và đánh giá failure khi compensation cũng lỗi.
15. **Transport:** đưa Fraud ra broker/HTTP. Định nghĩa reply destination và correlation mapper, test round-trip qua adapter.
16. **Hai requests cùng order:** gửi `REQ-A` và `REQ-B` cho `ORD-1`, đảo reply rồi chứng minh không trộn nhóm.
17. **Response schema:** cho một reply có `recipientId=inventory` nhưng `orderId` không khớp; bổ sung validation để không ghép nhầm.
18. **Crash/restart:** giả lập gatherer restart khi mới nhận Inventory reply; thiết kế group store/recovery theo delivery contract.
19. **Observability:** thêm log `SCATTER_PLANNED`, `BRANCH_COMPLETED`, `GATHER_RELEASED`, `GATHER_EXPIRED` và dashboard per-recipient.
20. **SLO:** so sánh giải pháp chờ Gateway với API trả `202 Accepted` + status endpoint khi một nhánh xử lý dài hạn.

### Tiêu chí hoàn thành

Một implementation có thể coi là đã đáp ứng bài này khi:

- Có hợp đồng trả lời cụ thể của **mỗi recipient**.
- Định nghĩa expected recipient set cho từng request, không chỉ hardcode tổng số messages.
- Không ghép reply của request/attempt khác hoặc recipient lạ.
- Không biến duplicate thành bằng chứng đã đủ nhánh.
- Phân biệt business FAIL với technical error, timeout và missing reply.
- Có deadline cho caller và group, cùng chính sách late reply.
- Có cách theo dõi accepted/processed/gathered, không chỉ nhìn `send`.
- Có retry/idempotency/compensation phù hợp nếu nhánh có side effect.
- Có unit test combiner và integration test chạy qua scatter/gather thật.

## 22. Câu hỏi tự kiểm tra

**Câu 1:** Một request cần Inventory và Fraud. Inventory PASS, Fraud chưa có reply. Có được trả CONFIRMED không?

**Không.** Theo hợp đồng wait-for-all, phải có hai kết quả hợp lệ. Có thể trả PENDING/TIMED_OUT tùy deadline nhưng không giả định Fraud đã PASS.

**Câu 2:** Hai message nhận được đều mang `recipientId=inventory`. Aggregator đã đủ hai message, có nghĩa đủ hai nhánh chưa?

**Chưa.** Đây có thể là duplicate Inventory; tập recipient duy nhất vẫn thiếu Fraud.

**Câu 3:** Scatter–Gather có bảo đảm hai handler chạy song song không?

**Không.** Concurrency phụ thuộc channel/executor/broker và cấu hình execution, không chỉ phụ thuộc pattern.

**Câu 4:** Một Fraud handler trả `BranchReply(verdict=FAIL)` khác gì ném exception?

**FAIL** là một business result để combiner tạo REJECTED; exception là technical failure và có thể khiến không có reply bình thường, cần error/recovery policy.

**Câu 5:** `correlationId` có chắc luôn bằng `requestId`?

**Không.** Phải kiểm tra cơ chế correlation trong flow và mapping qua adapter; requestId vẫn nên có như định danh nghiệp vụ ổn định.

**Câu 6:** Khi client timeout, có chắc Inventory chưa giữ hàng không?

**Không.** Handler có thể đã commit và reply bị mất/chậm. Cần idempotency/reconciliation trước khi retry.

**Câu 7:** Nếu Gateway nhận đủ hai replies và một FAIL, Aggregator có thể release không?

**Có**, nếu release strategy quy định đủ hai kết quả cuối; nhưng **decision status** phải là REJECTED, không phải CONFIRMED.

**Câu 8:** Tại sao retry toàn bộ Scatter–Gather khi Fraud lỗi là nguy hiểm?

**Vì** có thể gọi lại Inventory dù đã giữ hàng hoặc tạo side effect, dẫn tới reservation trùng nếu không có idempotency.

**Câu 9:** Một request INTL cần thêm Compliance. Gatherer cũ chỉ chờ Inventory/Fraud có còn đúng không?

**Không.** Expected set phải gồm Compliance, nếu không có thể xác nhận sớm dù chưa kiểm tra điều kiện bắt buộc.

**Câu 10:** Vì sao không nên dùng `traceId` làm duy nhất group key?

**Vì** nhiều kiểm tra có thể nằm trong cùng một trace. Cần request/group ID riêng để tránh trộn reply.

**Câu 11:** Khi Fraud trả reply sau group expiry, có nên tự mở một group mới rồi gửi thêm kết luận cho caller cũ không?

**Không mặc định.** Cần late-result policy, trạng thái operation và cách tránh duplicate decisions.

**Câu 12:** Test `ReplyCombiner` PASS có chứng minh Scatterer và Gateway hoạt động chưa?

**Chưa.** Đó là unit test logic gom. Cần integration test cho routing, reply path, correlation, group release và timeout.

**Câu 13:** Dùng broker có làm Scatter–Gather tự có exactly-once không?

**Không.** Broker có delivery/ack semantics riêng; cần dedupe, idempotency, durable store và transaction/recovery thích hợp.

**Câu 14:** Khi Fraud FAIL còn Inventory đã reserve thành công, điều gì có thể cần làm?

**Compensation**, ví dụ release reservation, nếu hợp đồng nghiệp vụ không cho phép tiếp tục giữ hàng. Phải quản lý cả trường hợp compensation lỗi.

## 23. Kết luận

**Scatter–Gather gửi một yêu cầu đến nhiều nhánh** để nhận **các góc đánh giá/kết quả độc lập**, rồi **gom đúng các reply liên quan** trước khi đưa ra kết luận. Trong Spring Integration, scatterer có thể dùng Recipient List hoặc Publish–Subscribe, còn gatherer dựa vào Aggregator, correlation, release strategy và output processor để tạo câu trả lời chung.

Điểm quyết định không phải “gửi đi được bao nhiêu message” mà là **đã nhận đúng và đủ những kết quả nào**. Một tập reply chỉ có thể đáng tin khi kiểm tra `requestId`, `recipientId`, expected set, duplicate, foreign replies, business status và thời hạn. Với flow bất đồng bộ hoặc phân tán, còn phải xử lý executor/queue, timeout ở nhiều tầng, error channel, retry, idempotency, late reply và side effect từng nhánh.

Trong `SPRING_INTEGRATION_PATTERN`, hãy bắt đầu từ **hợp đồng nghiệp vụ**, viết unit test cho decision/reconciliation, rồi integration test Gateway → Scatter → Branch Replies → Gather. Nếu caller không cần chờ kết quả thì Publish–Subscribe đơn giản có thể phù hợp hơn; nếu cần **đủ nhiều điều kiện để xác nhận**, Scatter–Gather là lựa chọn có ý nghĩa. Thiết kế đúng sẽ giúp message flow ít phụ thuộc, dễ mở rộng, kiểm thử được và truy nguyên rõ ràng khi một nhánh gặp sự cố.
