# Chấp nhận partial result hay fail toàn bộ

> **Chương:** Scatter gather  
> **Module:** `SPRING_INTEGRATION_PATTERN` — học triển khai Enterprise Integration Patterns bằng Spring Integration để xây dựng luồng thông điệp ít phụ thuộc và dễ mở rộng; thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử và theo dõi từng nhánh. Bài này tập trung vào **quyết định chấp nhận kết quả một phần (partial result) hay coi cả tác vụ là thất bại** khi một số recipient chưa phản hồi hoặc trả kết quả lỗi.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả hai pha **scatter** (phân phát cùng yêu cầu tới nhiều đơn vị xử lý) và **gather** (tập hợp phản hồi theo correlation) của EIP Scatter-Gather.
2. Phân biệt **đã nhận đủ phản hồi**, **thành công nghiệp vụ**, **đủ quorum**, **phản hồi thiếu**, **timeout**, **lỗi kỹ thuật**, **lỗi nghiệp vụ** và **reply đến muộn**.
3. Thiết kế một chính sách tường minh: **all-or-nothing**, **partial accepted có điều kiện**, **quorum** hoặc **manual review**, với các recipient bắt buộc và ngưỡng chất lượng.
4. Cấu hình hướng triển khai với Spring Integration, gồm Scatter-Gather, Recipient List/Publish-Subscribe, Aggregator, correlation, release, timeout và partial expiry.
5. Giải thích vì sao `groupTimeout` **không mặc nhiên là deadline tuyệt đối từ thời điểm request vào**, và vì sao **zero replies** cần một cơ chế deadline ở mức yêu cầu.
6. Viết policy Java có thể unit test, thiết kế integration tests cho 0/1/N replies, duplicate, late reply, partial, fail toàn bộ và race gần deadline.
7. Kiểm soát retry/idempotency, side effect, compensating actions, observability và bảo mật thông tin qua nhiều recipient.

## 2. Ví dụ nghiệp vụ: lấy báo giá từ ba nhà cung cấp

Một nền tảng thương mại điện tử cần báo giá vận chuyển từ ba đối tác `FAST`, `ECONOMY` và `GLOBAL`. Một yêu cầu `QuoteRequest` gửi cùng điều kiện giao hàng tới cả ba nhà cung cấp; kết quả có thể đến với độ trễ khác nhau.

~~~text
QuoteRequest(requestId=REQ-901, destination=VN)
                  |
                  v
             Scatter
                  |
          +-------+--------+
          |       |        |
        FAST   ECONOMY   GLOBAL
          |       |        |
       80.000   65.000   ...timeout...
          |       |        |
          +-------+--------+
                  |
                  v
              Gather
             2 / 3 replies
                  |
                  v
    Nên trả mức giá tốt nhất từ 2 bên,
    hay từ chối toàn bộ vì thiếu GLOBAL?
~~~

Câu trả lời phụ thuộc **hợp đồng nghiệp vụ**, không thể quyết định chỉ bằng khả năng kỹ thuật của Aggregator.

- Với **gợi ý giá vận chuyển cho người mua**, hai báo giá hợp lệ có thể đủ để hiển thị; kết quả phải đánh dấu “chưa nhận đủ báo giá”.
- Với **quy trình đối soát tài chính bắt buộc đủ ba nguồn**, thiếu một phản hồi có thể làm yêu cầu **không được phép hoàn tất**, dù hai nguồn đã thành công.
- Với **một đích quan trọng bắt buộc** như `FAST` do điều kiện vận chuyển hàng nguy hiểm, nếu đích này chưa phản hồi thì hai kết quả còn lại **không được coi là đủ**.
- Với **quorum** (ví dụ tối thiểu hai nguồn độc lập), có thể chấp nhận kết quả hai nguồn nếu cả hai hợp lệ và không vi phạm chính sách nguồn bắt buộc.

~~~mermaid
flowchart TD
    IN["QuoteRequest"] --> S["Scatter tới FAST, ECONOMY, GLOBAL"]
    S --> A["Gather replies theo executionId"]
    A --> C{"Đủ điều kiện hoàn tất?"}
    C -->|"Đủ tất cả, hợp lệ"| OK["COMPLETE: accepted"]
    C -->|"Đủ quorum, cho phép partial"| PART["PARTIAL_ACCEPTED + missing list"]
    C -->|"Thiếu / còn deadline"| WAIT["WAITING"]
    C -->|"Hết hạn, không đủ điều kiện"| FAIL["FAILED / RECONCILIATION"]
    WAIT --> A
~~~

**Quy tắc học thuật quan trọng:** “Có hai trên ba replies” **không tự động bằng** “thành công 2/3”. Reply có thể báo từ chối nghiệp vụ, lỗi định dạng hoặc giá không hợp lệ. Phải kiểm tra **tính hợp lệ và ý nghĩa** của từng kết quả trước khi áp chính sách partial.

## 3. Scatter-Gather: hai pha, hai trách nhiệm khác nhau

**Scatter:** truyền một yêu cầu tới nhiều recipient có thể xử lý độc lập; có thể dùng Recipient List Router hoặc Publish-Subscribe theo topology được cấu hình.

**Gather:** nhận các replies, tương quan chúng về **cùng một lần thực thi**, áp một điều kiện release và tạo một kết quả tổng hợp cho caller hoặc downstream.

~~~mermaid
flowchart LR
    Q["Request"] --> SC["Scatterer"]
    SC --> P1["Provider FAST"]
    SC --> P2["Provider ECONOMY"]
    SC --> P3["Provider GLOBAL"]
    P1 --> RP["Reply / correlation"]
    P2 --> RP
    P3 --> RP
    RP --> AG["Gatherer / Aggregator"]
    AG --> OUT["Combined response"]
~~~

Scatter-Gather khác với “gọi lần lượt ba HTTP API” ở chỗ các nhánh có thể **tiến hành độc lập**, caller cần một chiến lược **khi nào đủ phản hồi**. Tuy nhiên, một flow Scatter-Gather **không tự cam kết xử lý song song**: điều đó phụ thuộc channel, executor, Gateway và hạ tầng sử dụng.

### 3.1. So sánh với những EIP gần gũi

| Pattern | Trọng tâm | Ví dụ |
| --- | --- | --- |
| **Scatter-Gather** | Gửi yêu cầu tới nhiều recipient và **thu replies** theo chính sách | Hỏi ba đối tác, tổng hợp báo giá |
| **Recipient List** | Chọn tập recipient nhận message; **không nhất thiết chờ replies** | Phát event tới audit và analytics |
| **Publish-Subscribe Channel** | Phân phối message tới các subscriber | Một event cho nhiều consumer |
| **Splitter** | Chia **một payload gồm nhiều phần** thành các message con | Ba dòng hàng → ba yêu cầu kiểm kho |
| **Aggregator** | Gom replies/messages cùng nhóm | Tổng hợp ba kết quả về một |
| **Content-Based Router** | Chọn nhánh theo điều kiện | Hàng lạnh → kho lạnh |

Một hệ thống có thể dùng **Splitter → xử lý từng item → Aggregator** mà không phải Scatter-Gather theo nghĩa “cùng một request hỏi nhiều provider”; điều cần phân biệt là **cùng một câu hỏi gửi đến nhiều recipient** hay **nhiều phần dữ liệu khác nhau cần xử lý**.

### 3.2. Hai câu hỏi không được gộp

1. **Scatter đã thành công chưa?** Message có được phát đến từng channel/adapter cần thiết không?
2. **Gather đã có kết quả đáng tin chưa?** Có đủ phản hồi thực sự xác minh nghiệp vụ theo policy không?

`MessageChannel.send(...) == true` hoặc một broker ACK có thể chỉ xác nhận **đã nhận message ở ranh giới kỹ thuật**, không chứng minh provider đã tính xong giá hoặc ghi xong tác vụ.

## 4. Phân biệt completeness với business outcome

Thiết kế một kết quả tổng hợp bằng **hai chiều độc lập**:

- **Completeness:** đã nhận bao nhiêu phản hồi hợp lệ so với số recipient mong đợi?
- **Business outcome:** những phản hồi đã nhận có đáp ứng chính sách hay không?

| Completeness | Business outcome | Ý nghĩa |
| --- | --- | --- |
| `ALL_RESPONDED` | `ALL_ACCEPTED` | Mọi recipient đều phản hồi và đạt điều kiện |
| `ALL_RESPONDED` | `SOME_REJECTED` | Đã đủ phản hồi nhưng có provider từ chối |
| `PARTIAL_TIMED_OUT` | `PARTIAL_ACCEPTED` | Chưa đủ replies, nhưng có đủ điều kiện dùng một tập con |
| `PARTIAL_TIMED_OUT` | `FAILED` | Chưa đủ replies và không đạt mức tối thiểu/bắt buộc |
| `NO_REPLIES` | `FAILED` | Không có phản hồi nào trước deadline |

**Cảnh báo:** `ALL_RESPONDED` không có nghĩa `ALL_ACCEPTED`. Một provider có thể phản hồi rất nhanh rằng không hỗ trợ địa chỉ giao hàng. Đây là **một reply đã nhận**, nhưng không phải **báo giá sử dụng được**.

### 4.1. Reply kỹ thuật và reply nghiệp vụ

Một phản hồi HTTP 200 chứa báo giá hợp lệ khác với HTTP 200 chứa `status=REJECTED`. HTTP 503, timeout, mất kết nối lại là tình huống kỹ thuật có thể **không biết nhà cung cấp đã xử lý yêu cầu chưa**.

Với Scatter-Gather:

- **Reply ACCEPTED:** dữ liệu có thể tham gia lựa chọn theo contract.
- **Reply REJECTED:** recipient đã trả một quyết định nghiệp vụ kết thúc, không được đếm là successful quote.
- **Không reply / timeout:** trạng thái **UNKNOWN/NOT_RECEIVED**, không được giả là REJECTED.
- **Malformed reply:** lỗi schema; đưa error/quarantine, không cộng vào số reply hợp lệ.
- **Duplicate reply:** phải deduplicate theo recipient/operation identity.

## 5. Bốn chính sách phổ biến: strict, partial, quorum và fail-fast

### 5.1. Strict all-or-nothing

**Chỉ hoàn tất thành công khi tất cả recipient bắt buộc đều có phản hồi thành công.** Nếu bất kỳ phản hồi nào bị từ chối cuối cùng, hoặc hết deadline mà còn thiếu phản hồi, toàn bộ yêu cầu được đánh dấu không hoàn tất theo contract.

~~~text
Expected: [FAST, ECONOMY, GLOBAL]
Accepted: [FAST, ECONOMY]
Missing:  [GLOBAL]
Deadline: reached

Result: FAILED / INCOMPLETE
~~~

Thích hợp với trường hợp **không được phép ra quyết định khi thiếu dữ liệu**, ví dụ một thủ tục phê duyệt phải có sự chấp thuận của ba đơn vị độc lập.

**Strict result không đồng nghĩa transaction rollback.** Nếu các recipient đã tạo side effect (giữ hàng, chuyển tiền, đặt lịch), đánh dấu fail **không tự đảo ngược** những việc đã commit.

### 5.2. Partial result được chấp nhận có điều kiện

Có thể trả kết quả khi:

1. Một số provider còn thiếu hoặc đã từ chối.
2. Đã có **ít nhất N báo giá hợp lệ**.
3. Những provider **bắt buộc** đã trả hợp lệ.
4. Deadline hoặc quy tắc release có kiểm soát đã xác định thời điểm dừng chờ.
5. Caller/downstream **biết kết quả là partial** và có quy tắc xử lý tương ứng.

Ví dụ `minAccepted=2`, `mandatory={FAST}`:

~~~text
FAST:    ACCEPTED 80.000
ECONOMY: ACCEPTED 65.000
GLOBAL:  NO_REPLY

At deadline: PARTIAL_ACCEPTED
Best known quote: ECONOMY 65.000
Missing providers: [GLOBAL]
~~~

**“Best known quote” không bảo đảm giá thấp nhất có thể**, vì GLOBAL chưa có dữ liệu. Nếu giao diện muốn hiển thị, cần diễn đạt rõ đây là giá tốt nhất **trong những báo giá đã nhận**.

### 5.3. Quorum theo ngưỡng

Quorum có thể là `2/3`, `3/5` hoặc điều kiện dựa trên **trọng số và độ độc lập của nguồn**. Chỉ đếm số replies là không đủ:

- Hai replies từ **cùng một logical provider** không tạo thành quorum hai bên.
- Một provider có nhiều alias/channel cũng không nên bị đếm hai lần.
- Một số bên có thể **bắt buộc**; chúng phải xuất hiện bất kể đã đủ số lượng.
- Với giá trị có ảnh hưởng pháp lý/tài chính, “đa số trả về” không chắc tương đương “đủ bằng chứng”.

**Quorum không phải luôn chờ đến timeout.** Nếu policy cho phép release ngay khi đủ hai câu trả lời và không quan tâm kết quả thứ ba, Aggregator có thể release sớm; nhưng khi đó có thể hy sinh cơ hội nhận kết quả tốt hơn. Cần chọn rõ giữa **latency tối ưu** và **chất lượng kết quả**.

### 5.4. Fail-fast khi điều kiện không thể phục hồi

Nếu một provider **bắt buộc** trả một lỗi nghiệp vụ kết thúc, ví dụ `NOT_ELIGIBLE`, chính sách strict có thể **fail sớm**, không cần đợi những provider còn lại. Tuy nhiên, nếu đó chỉ là lỗi mạng có thể retry, việc fail-fast ngay có thể quá sớm.

Định nghĩa rõ:

- **Terminal rejection:** kết luận cuối cùng theo contract; có thể fail-fast.
- **Transient failure:** lỗi kỹ thuật có thể khôi phục; giữ chờ/retry trong deadline.
- **Uncertain outcome:** chưa biết side effect đã xảy ra; reconcile trước khi quyết định bù trừ.
- **Deadline reached:** một điểm đóng tập kết quả theo SLA, không biến UNKNOWN thành terminal rejection.

## 6. Decision table: khi nào partial thực sự hợp lệ?

Giả sử expected `{FAST, ECONOMY, GLOBAL}`, mandatory `{FAST}`, minimum accepted = 2.

| FAST | ECONOMY | GLOBAL | Đến deadline? | Quyết định partial policy |
| --- | --- | --- | --- | --- |
| ACCEPTED | ACCEPTED | ACCEPTED | Không cần chờ | `ACCEPTED_COMPLETE` |
| ACCEPTED | ACCEPTED | Thiếu | Chưa | `WAITING` |
| ACCEPTED | ACCEPTED | Thiếu | Có | `ACCEPTED_PARTIAL` |
| ACCEPTED | Thiếu | ACCEPTED | Có | `ACCEPTED_PARTIAL` |
| Thiếu | ACCEPTED | ACCEPTED | Có | `FAILED` (thiếu mandatory) |
| REJECTED cuối | ACCEPTED | ACCEPTED | Bất kỳ | `FAILED` (mandatory rejected) |
| ACCEPTED | REJECTED cuối | ACCEPTED | Không cần chờ | `ACCEPTED_PARTIAL` (đủ 2, cả 3 đã phản hồi) |
| ACCEPTED | Thiếu | Thiếu | Có | `FAILED` (chỉ 1 accepted) |
| Thiếu | Thiếu | Thiếu | Có | `FAILED` (zero replies) |
| ACCEPTED | ACCEPTED | ACCEPTED | Có | `ACCEPTED_COMPLETE` |

Nếu đổi thành chính sách **strict all-or-nothing**, mọi hàng có thiếu hoặc REJECTED đều không thể trở thành `ACCEPTED_COMPLETE`. Chính sách cần được **gắn phiên bản**, đặc biệt nếu tổ chức thay đổi ngưỡng hoặc mandatory provider giữa một lượt xử lý.

### 6.1. Không “giảm expectedCount” để đạt quorum

Giả sử GLOBAL bị timeout, đừng âm thầm đổi `expectedCount=3` thành `expectedCount=2` rồi ghi trạng thái `COMPLETE`. Việc ấy đánh mất bằng chứng rằng GLOBAL đã không phản hồi.

Hãy giữ **tập expected gốc** và ghi rõ:

~~~json
{
  "executionId": "RUN-901",
  "expectedProviders": ["FAST", "ECONOMY", "GLOBAL"],
  "respondedProviders": ["FAST", "ECONOMY"],
  "missingProviders": ["GLOBAL"],
  "decision": "ACCEPTED_PARTIAL",
  "policyVersion": "quote-policy-v2"
}
~~~

## 7. Contract phải có expected recipients và execution identity

Trong Scatter-Gather, một request có thể được thực hiện lại, và cùng một provider có thể gửi reply hai lần. Vì thế, **số message nhận được khác số provider duy nhất đã phản hồi**.

~~~text
Request REQ-901
   execution RUN-901-A
     expected FAST, ECONOMY, GLOBAL
     FAST reply accepted
     FAST reply accepted (duplicate)
     ECONOMY reply accepted
     GLOBAL missing

Raw reply count = 3
Unique respondent count = 2
Completeness = PARTIAL
~~~

Một policy đúng phải đếm theo **provider ID đáng tin cậy**, không chỉ `group.size()` hoặc `sequenceSize`.

### 7.1. Phân biệt các định danh

| Trường | Ý nghĩa | Gợi ý |
| --- | --- | --- |
| `requestId` | Yêu cầu nghiệp vụ của caller | `REQ-901` |
| `executionId` | Một lần scatter cụ thể; khóa group | `RUN-901-A` |
| `providerId` | Recipient logic được cho phép | `FAST` |
| `operationId` | Khóa idempotency cho tác vụ có side effect | `quote-op-901` |
| `correlationId` | Liên kết replies với scatter execution | `RUN-901-A` hoặc khóa grouping tương ứng |
| `messageId` | Định danh envelope do framework quản lý | Có thể thay qua replay/adapter |
| `policyVersion` | Quy tắc chấp nhận kết quả | `quote-policy-v2` |

**Correlation không thay idempotency.** Correlation là cơ chế gom replies. Một response đến chậm vẫn phải có đường kiểm tra execution đã đóng; một request được phát lại vẫn có thể tạo side effect nếu downstream không có idempotency key ổn định.

### 7.2. Expected recipients là dữ liệu có thẩm quyền

Nếu user tự gửi `expectedProviders=["FAST"]` để ép hệ thống bỏ qua những provider bắt buộc, partial policy sẽ bị vô hiệu hóa. Expected set phải được tính bởi **routing policy đáng tin cậy**, dựa trên dữ liệu đã xác thực và version đã chọn.

Nếu recipient list được lựa chọn động, `sequenceSize` phải phản ánh **số recipient thực sự được chọn** khi có sequence; còn business policy phải biết rõ **recipient bắt buộc theo hợp đồng**, không chỉ số lượng kênh hiện tại.

## 8. Java 17: mô hình dữ liệu và policy độc lập với framework

Để tách ý nghĩa nghiệp vụ khỏi cấu hình Spring Integration, ta định nghĩa một policy Java thuần đánh giá phản hồi tại thời điểm đã cho.

### 8.1. Records và các trạng thái

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.Set;

enum ProviderStatus {
    ACCEPTED,
    REJECTED
}

record ProviderReply(
    String providerId,
    ProviderStatus status,
    BigDecimal price
) {
    ProviderReply {
        if (providerId == null || providerId.isBlank()) {
            throw new IllegalArgumentException("providerId required");
        }
        Objects.requireNonNull(status, "status");

        if (status == ProviderStatus.ACCEPTED
                && (price == null || price.signum() < 0)) {
            throw new IllegalArgumentException(
                "Accepted quote needs non-negative price");
        }
    }
}

record ScatterPlan(
    String executionId,
    String requestId,
    String policyVersion,
    Set<String> expectedProviders,
    Set<String> mandatoryProviders,
    int minimumAccepted,
    boolean allowPartial,
    Instant deadline
) {
    ScatterPlan {
        if (executionId == null || executionId.isBlank()
            || requestId == null || requestId.isBlank()
            || policyVersion == null || policyVersion.isBlank()) {
            throw new IllegalArgumentException("Identity/version required");
        }
        expectedProviders = Set.copyOf(
            Objects.requireNonNull(expectedProviders));
        mandatoryProviders = Set.copyOf(
            Objects.requireNonNull(mandatoryProviders));
        Objects.requireNonNull(deadline);

        if (expectedProviders.isEmpty()
            || !expectedProviders.containsAll(mandatoryProviders)
            || minimumAccepted < 1
            || minimumAccepted > expectedProviders.size()) {
            throw new IllegalArgumentException("Invalid scatter plan");
        }
    }
}

enum DecisionStatus {
    WAITING,
    ACCEPTED_COMPLETE,
    ACCEPTED_PARTIAL,
    FAILED
}

record ScatterDecision(
    DecisionStatus status,
    int expectedCount,
    int respondedCount,
    List<String> acceptedProviders,
    List<String> missingProviders,
    String reasonCode
) {
    ScatterDecision {
        acceptedProviders = List.copyOf(acceptedProviders);
        missingProviders = List.copyOf(missingProviders);
    }
}
~~~

`ProviderStatus.REJECTED` ở đây chỉ biểu diễn **một quyết định nghiệp vụ kết thúc**; lỗi HTTP 503, timeout hoặc response chưa biết kết quả **không được tự động biến thành REJECTED**. Những lỗi kỹ thuật đi qua retry/error/reconciliation, và provider vẫn được coi là **chưa có valid terminal reply** nếu chưa xác định được outcome.

### 8.2. Policy nhận N replies, khử trùng và áp các điều kiện

~~~java
import java.time.Instant;
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

final class ScatterDecisionPolicy {
    private ScatterDecisionPolicy() {}

    static ScatterDecision evaluate(
            ScatterPlan plan,
            Collection<ProviderReply> replies,
            Instant now) {

        Objects.requireNonNull(plan);
        Objects.requireNonNull(replies);
        Objects.requireNonNull(now);

        Map<String, ProviderReply> unique = new HashMap<>();

        for (ProviderReply reply : replies) {
            if (reply == null
                    || !plan.expectedProviders().contains(reply.providerId())) {
                throw new IllegalArgumentException(
                    "Unknown/null provider reply");
            }
            ProviderReply previous =
                unique.putIfAbsent(reply.providerId(), reply);
            if (previous != null && !previous.equals(reply)) {
                throw new IllegalArgumentException(
                    "Conflicting duplicate provider reply");
            }
        }

        Set<String> accepted = unique.values().stream()
            .filter(r -> r.status() == ProviderStatus.ACCEPTED)
            .map(ProviderReply::providerId)
            .collect(Collectors.toSet());

        List<String> missing = plan.expectedProviders().stream()
            .filter(id -> !unique.containsKey(id))
            .sorted()
            .toList();

        List<String> acceptedIds = accepted.stream().sorted().toList();
        int responded = unique.size();
        boolean allResponded = missing.isEmpty();
        boolean allAccepted = accepted.size() == plan.expectedProviders().size();
        boolean mandatoryAccepted =
            accepted.containsAll(plan.mandatoryProviders());
        boolean mandatoryRejected = plan.mandatoryProviders().stream()
            .anyMatch(id -> unique.containsKey(id)
                && unique.get(id).status() == ProviderStatus.REJECTED);
        boolean quorumSatisfied =
            accepted.size() >= plan.minimumAccepted() && mandatoryAccepted;
        boolean deadlineReached = !now.isBefore(plan.deadline());

        DecisionStatus status;
        String reason;

        if (mandatoryRejected) {
            // Lỗi nghiệp vụ terminal ở recipient bắt buộc.
            status = DecisionStatus.FAILED;
            reason = "MANDATORY_PROVIDER_REJECTED";
        } else if (allResponded && allAccepted) {
            status = DecisionStatus.ACCEPTED_COMPLETE;
            reason = "ALL_PROVIDERS_ACCEPTED";
        } else if (allResponded || deadlineReached) {
            if (plan.allowPartial() && quorumSatisfied) {
                status = DecisionStatus.ACCEPTED_PARTIAL;
                reason = "PARTIAL_POLICY_SATISFIED";
            } else {
                status = DecisionStatus.FAILED;
                reason = deadlineReached
                    ? "DEADLINE_WITHOUT_REQUIRED_RESULTS"
                    : "INSUFFICIENT_VALID_REPLIES";
            }
        } else {
            status = DecisionStatus.WAITING;
            reason = "AWAITING_REPLIES";
        }

        return new ScatterDecision(
            status,
            plan.expectedProviders().size(),
            responded,
            acceptedIds,
            missing,
            reason);
    }
}
~~~

**Ý nghĩa chính xác của hàm:**

- **Đếm unique provider**, không đếm duplicate message.
- Một provider **bắt buộc đã REJECTED** khiến yêu cầu fail-fast theo policy minh họa.
- Khi **đã đủ mọi phản hồi và mọi provider ACCEPTED**, trả `ACCEPTED_COMPLETE`.
- Khi **tất cả đã phản hồi**, hoặc **deadline đạt tới**, có thể trả `ACCEPTED_PARTIAL` **chỉ nếu allowPartial=true, đủ minimum và không thiếu mandatory accepted**.
- Nếu chưa đủ và còn thời gian, trả `WAITING`.
- Nếu không thỏa điều kiện khi đóng nhóm, trả `FAILED`.
- Bộ lọc không coi reply không hợp lệ, unknown provider hoặc conflicting duplicate là dữ liệu hợp lệ có thể âm thầm bỏ qua.

**Giới hạn quan trọng:** hàm `evaluate` là **policy thuần**, không tự dispatch, lập lịch timeout hoặc lưu closed-state. Nó được thiết kế để được gọi khi có reply mới hoặc khi deadline watcher kích hoạt. Production còn cần quản lý **chuyển trạng thái nguyên tử** của execution để kết quả cuối không được phát hai lần.

### 8.3. All-or-nothing được thể hiện thế nào?

Ví dụ strict:

~~~java
ScatterPlan strict = new ScatterPlan(
    "RUN-901-STRICT",
    "REQ-901",
    "quote-policy-strict-v1",
    Set.of("FAST", "ECONOMY", "GLOBAL"),
    Set.of("FAST", "ECONOMY", "GLOBAL"),
    3,
    false,
    Instant.parse("2026-11-21T10:00:05Z"));
~~~

Ví dụ partial có ngưỡng:

~~~java
ScatterPlan partial = new ScatterPlan(
    "RUN-901-PARTIAL",
    "REQ-901",
    "quote-policy-v2",
    Set.of("FAST", "ECONOMY", "GLOBAL"),
    Set.of("FAST"),
    2,
    true,
    Instant.parse("2026-11-21T10:00:05Z"));
~~~

Hai policy cùng sử dụng một cơ chế scatter/gather nhưng **quyết định nghiệp vụ khác nhau**. Đừng thay `allowPartial` trong lúc execution đang chờ mà không lưu policy version/snapshot; nếu không, cùng một tập replies có thể cho hai kết quả khác nhau sau retry.

## 9. Thời điểm release: đủ replies khác đủ quorum

Có hai cách phổ biến khi gặp `2/3` replies:

1. **Release ngay khi đủ quorum:** giảm latency, nhưng có thể bỏ lỡ giá tốt hơn hoặc một yếu tố bắt buộc chưa biết. Cần có hợp đồng chỉ quan tâm “đủ hai nguồn” thay vì “chọn tốt nhất từ tất cả”.
2. **Chờ tới deadline hoặc đủ toàn bộ:** cải thiện cơ hội nhận phản hồi còn thiếu, rồi chấp nhận partial nếu policy cho phép. Đây là chiến lược của `ScatterDecisionPolicy` phía trên.

### 9.1. Đặt release strategy cho Aggregator

Nếu chọn chiến lược chờ toàn bộ, Gatherer có thể:

- Correlate theo `executionId`.
- Release đủ khi có **mỗi expected provider một valid reply**.
- Nếu hết hạn nhóm khi còn thiếu, cấu hình cơ chế **partial expiry**.
- Đưa những phản hồi đã nhận vào output processor/policy để quyết định `ACCEPTED_PARTIAL` hay `FAILED`.

Nếu muốn release **ngay đủ quorum**, Gatherer phải dựa trên **unique accepted providers** cùng mandatory condition; không sử dụng `group.size() >= 2` vì duplicate hoặc một REJECTED reply có thể làm đủ số lượng sai.

### 9.2. Đừng lấy `Aggregator released` làm bằng chứng policy chấp thuận

Việc Aggregator **release** một nhóm là quyết định **kỹ thuật về thời điểm phát kết quả**. Nó có thể release vì đủ replies, quorum hoặc timeout. Sau release, **business decision processor** vẫn phải đánh giá điều kiện và trả kết quả có trạng thái rõ.

Ví dụ nhóm đủ ba replies nhưng GLOBAL bị REJECTED có thể được Aggregator release bình thường; theo strict policy, **business decision vẫn là FAILED**.

## 10. Spring Integration: Scatter-Gather và chính sách partial expiry

Spring Integration hỗ trợ EIP Scatter-Gather với **scatterer** và **gatherer**, có thể được cấu hình thông qua Java DSL và các endpoint liên quan. Ở pha scatter, một Recipient List hoặc Publish-Subscribe phân phát yêu cầu tới những channel/flow recipient; ở pha gather, cơ chế Aggregator nhận các reply có correlation và áp release strategy.

### 10.1. Sơ đồ topology đề xuất

~~~text
quotes.in
  |
  v
Validate / authenticate / create ScatterPlan snapshot
  |
  v
Scatter-Gather
  +-- scatter: FAST request handler ------> reply FAST
  +-- scatter: ECONOMY request handler ---> reply ECONOMY
  +-- scatter: GLOBAL request handler ----> reply GLOBAL
  |
  +-- gather: correlate executionId
      |
      +-- all replies → combined group
      +-- expiry → partial group (if configured)
      |
      v
Business decision processor (strict / partial / quorum)
  |
  +--> quotes.accepted.complete
  +--> quotes.accepted.partial
  +--> quotes.failed / quotes.reconciliation
~~~

**Các giả định thiết kế:** recipient handlers **thực sự trả reply** qua cơ chế Scatter-Gather, không chỉ gọi adapter một chiều rồi kết thúc. Khi qua broker/HTTP bất đồng bộ, phải thiết kế reply route, correlation và state store thay vì mong một HTTP request thread giữ chờ vô hạn.

### 10.2. Java DSL minh họa cấu hình cơ chế

Ví dụ dưới đây là **phác thảo cấu hình DSL** thể hiện các trách nhiệm, không phải một chương trình độc lập có thể biên dịch ngay khi chưa khai báo các handler `fastHandler`, `economyHandler`, `globalHandler` và topology reply:

~~~java
// Phác thảo Spring Integration Java DSL:
// Kiểm tra chữ ký overload và cấu hình endpoint theo phiên bản sử dụng.
IntegrationFlow quoteScatterGather() {
    return IntegrationFlow.from("quotes.in")
        .scatterGather(
            scatterer -> scatterer
                .recipientFlow(f -> f.handle(fastHandler))
                .recipientFlow(f -> f.handle(economyHandler))
                .recipientFlow(f -> f.handle(globalHandler)),
            gatherer -> gatherer
                .groupTimeout(5_000L)
                .sendPartialResultOnExpiry(true))
        .channel("quotes.gathered")
        .get();
}
~~~

Các handler có thể cần Gateway/adapter riêng và reply message được tạo đúng contract. `groupTimeout` là cơ chế timeout nhóm trong Gatherer; `sendPartialResultOnExpiry(true)` **không tự biến partial thành success**. Đặt một **policy processor** sau Gatherer để xác định `ACCEPTED_PARTIAL` hoặc `FAILED`; và một **deadline watcher** ở mức request nếu SLA phải tính từ thời điểm bắt đầu scatter.

**Lưu ý:** phương thức cụ thể trên các DSL specs và lifecycle của Scatter-Gather có thể khác theo Spring Integration version. Đây là bài về **kiến trúc và quyết định partial-vs-fail**, không phải hướng dẫn khẳng định chạy qua mọi phiên bản mà không kiểm tra API. Phần `ScatterDecisionPolicy` là mã Java thuần để kiểm thử logic nghiệp vụ độc lập.

### 10.3. Không nên trộn control-flow vào một callback

Nếu callback Scatterer có nhiệm vụ vừa chọn recipient, vừa tự gọi ba external APIs, vừa bắt exception, vừa tính kết quả và ghi database, thì việc phân biệt error/timeout sẽ rất khó. Tách:

- **Scatter policy:** chọn expected recipients hợp lệ.
- **Recipient handler:** thực thi hoặc chuyển yêu cầu cho từng provider.
- **Reply mapper:** tạo `ProviderReply` hợp lệ có `executionId/providerId`.
- **Gatherer:** gom theo correlation, release/expire theo policy kỹ thuật.
- **Business policy processor:** chấp nhận partial hay fail.
- **Finalization/registry:** chỉ phát **một quyết định cuối** cho execution.

## 11. Vì sao group timeout chưa đủ bảo đảm SLA?

Một yêu cầu bắt đầu ở T0. Provider FAST trả ở T0+1 giây; ECONOMY ở T0+3; GLOBAL không trả. Nếu SLA tổng thể là 5 giây, hệ thống phải quyết định tại T0+5, bất kể Aggregator đã nhận message đầu tiên vào thời điểm nào.

~~~text
T0       Scatter request created; deadline=T0+5s
T0+1     FAST reply -> Aggregator creates group
T0+3     ECONOMY reply -> Aggregator updates group
T0+5     Business deadline must settle outcome
T0+9     GLOBAL late reply
~~~

Một `groupTimeout(5000)` có thể được tính/lên lịch lại dựa trên trạng thái group và thời điểm nhận message. Vì vậy **không nên diễn giải nó thành deadline tuyệt đối đúng T0+5** nếu chưa kiểm tra tính chất của phiên bản và cấu hình thực tế.

### 11.1. Deadline watcher ở mức request

Một kiến trúc vững chắc lưu khi scatter:

~~~text
ScatterExecution:
    executionId    = RUN-901
    requestId      = REQ-901
    expected       = [FAST, ECONOMY, GLOBAL]
    mandatory      = [FAST]
    createdAt      = T0
    deadlineAt     = T0 + 5 seconds
    policyVersion  = quote-policy-v2
    state          = OPEN
~~~

Watcher có thể chạy theo scheduler, queue delay hoặc workflow engine có persistence. Tại deadline:

1. Đọc state của execution.
2. Đọc replies hợp lệ đã được ghi nhận.
3. Gọi business decision policy.
4. Dùng **CAS/transaction** chuyển `OPEN → CLOSED` đúng một lần.
5. Phát một output cuối tương ứng, hoặc đưa vào outbox nếu cần độ tin cậy qua sự cố.
6. Các reply sau đó đi vào late/reconciliation path.

### 11.2. Không có reply nào thì sao?

Nếu tất cả ba provider đều không trả lời, Gatherer có thể **chưa từng tạo message group**. Vì không có group, **per-group timeout không có gì để expire**. Deadline watcher phải phát `FAILED(NO_REPLIES)` hoặc một `BatchTimedOut` theo contract.

Không được thiết kế API hứa “luôn có phản hồi sau 5 giây” mà chỉ cài `groupTimeout` trên Aggregator. Hãy test trường hợp zero replies **từ registry của scatter request**, không chỉ gửi một reply rồi chờ.

## 12. Late reply, duplicate và race gần deadline

Giả sử đã phát `ACCEPTED_PARTIAL` lúc T0+5 khi có FAST và ECONOMY. Lúc T0+7, GLOBAL trả giá tốt hơn cả hai. Có ba lựa chọn:

| Chính sách | Hành vi | Đánh đổi |
| --- | --- | --- |
| **Ignore + audit** | Không sửa quyết định đã trả, ghi nhận late reply | Dễ giữ contract một kết quả cuối; bỏ lỡ giá tốt |
| **Versioned update** | Phát `QuoteResultUpdated(v2)` với giá mới nếu còn được phép | Caller phải hỗ trợ cập nhật và version |
| **Reconcile/manual review** | Xử lý theo workflow khác, không ghi đè result đầu tiên | Nhiều trạng thái nhưng dễ kiểm soát |

**Không nên phát một `QuoteResult(FINAL)` thứ hai với cùng execution ID và không có version.** Điều đó khiến consumer có thể tính tiền/đặt vận chuyển hai lần.

### 12.1. Tombstone hoặc closed execution registry

Sau Aggregator release/expire, group có thể bị xóa khỏi store. Late reply cùng correlation có thể tạo một group mới nếu không có cơ chế chặn. Dùng registry:

~~~text
Reply arrives:
  execution OPEN      -> validate/dedup -> gather
  execution COMPLETE  -> duplicate / late handling
  execution EXPIRED   -> reconciliation / audit
  execution UNKNOWN   -> reject / investigation
~~~

Retention của tombstone phải phù hợp **thời gian message có thể đến muộn hoặc replay**. Giữ tombstone 10 giây không đủ nếu broker còn replay sau nhiều ngày.

### 12.2. Race: reply cuối cùng và timeout đồng thời

~~~text
Thread A: nhận GLOBAL, đủ 3/3
Thread B: deadline watcher thấy 2/3
~~~

Một execution chỉ được **commit một outcome cuối**. Dùng compare-and-set/transaction cùng một source of truth, rồi phát final event qua outbox/idempotent publisher khi cần. Kết quả có thể là COMPLETE **hoặc** PARTIAL tùy thứ tự atomic thắng cuộc, nhưng không phải **cả hai**.

### 12.3. Duplicate reply không phải quorum bổ sung

Nhận FAST hai lần và ECONOMY một lần chưa phải ba provider. Validate và dedup theo `(executionId, providerId, responseId/operationId)` phù hợp. Nếu hai replies cùng provider nhưng giá khác nhau, cần chính sách **version/attempt** rõ hoặc quarantine; không “last write wins” tùy tiện.

## 13. All-or-nothing với side effect: fail cả yêu cầu không đồng nghĩa rollback

Ví dụ lấy giá thường là phép đọc. Nhưng nếu scatter gửi ba **command đặt chỗ** thay vì request hỏi giá, cả ba recipient có thể tạo side effect. Một nhánh thất bại không khiến hai nhánh đã thành công được tự động hoàn tác.

~~~mermaid
flowchart TD
    X["Scatter: reserve 3 resources"] --> A["A committed"]
    X --> B["B committed"]
    X --> C["C failed / unknown"]
    A --> F["Global all-or-nothing outcome = FAILED"]
    B --> F
    C --> F
    F --> COMP["Compensation / reconciliation"]
    COMP --> R["Release A, B nếu cần"]
~~~

**Đây không phải distributed transaction tự động.** Phải có quy tắc bù trừ (Saga/compensating actions), idempotency, xác minh đã commit hay chưa, và theo dõi chính các thao tác bù trừ.

### 13.1. Đừng dùng Scatter-Gather cho một command chỉ có một owner

Nếu `ChargePayment` chỉ nên được thực hiện bởi **một** hệ thống thanh toán chịu trách nhiệm, gửi cùng command tới ba provider như Recipient List có thể gây ba giao dịch. Với những thao tác độc quyền sở hữu, dùng Router chọn **một owner**, rồi phát event cho các bên phụ thuộc sau khi hoàn tất. Scatter-Gather thích hợp khi nhiều bên **được phép xử lý song song cùng một yêu cầu độc lập**.

### 13.2. Retry theo recipient

Nếu ECONOMY và FAST đã trả, chỉ GLOBAL timeout, retry toàn bộ scatter có thể gửi lại yêu cầu tới cả ba. Với request đọc có thể không nghiêm trọng nhưng vẫn tăng tải; với side effect là rủi ro lớn.

Ưu tiên:

- Retry **tại nhánh thất bại** trong deadline, với backoff/limit.
- Idempotency key ổn định ở external consumer cho command có side effect.
- Tra cứu trạng thái khi timeout không rõ kết quả.
- Không reset deadline vô hạn qua mỗi lần retry.
- Reconciliation khi hết retry mà chưa biết outcome.

## 14. Error channel khác partial result

Một lỗi trong handler có thể xuất hiện ở **trước hoặc sau** khi request được chấp nhận bởi channel:

| Tình huống | Cần làm gì | Có tính là một valid reply? |
| --- | --- | --- |
| Provider trả ACCEPTED hợp lệ | Normalize `ProviderReply` | Có |
| Provider trả REJECTED nghiệp vụ | Normalize terminal reply | Có, nhưng không là accepted |
| HTTP 503 / timeout | Retry/error path theo policy | Không, trừ khi contract định nghĩa một terminal outcome riêng |
| JSON malformed | Reject/quarantine, alert contract | Không |
| Source không được xác thực | Không cho vào Gatherer | Không |
| ReplyChannel mất qua broker | Sửa header mapping/reply routing | Không |
| Adapter nhận response nhưng mất trước khi ghi state | Có thể retry/redeliver | Cần dedup và recovery |

Với `DirectChannel` đồng bộ, exception có thể truyền ngược lên caller; với executor/poller/broker, lỗi thường được xử lý qua error channel hoặc cơ chế lỗi theo transport. Một `ErrorMessage` **không tự động trở thành** một `ProviderReply(REJECTED)` cho Gatherer.

### 14.1. Khi muốn tính lỗi thành phản hồi để đóng nhóm sớm

Có thể tạo một **failure result có kiểu** như `ProviderOutcome(providerId, TECHNICAL_ERROR)` sau khi đã hết retries và xác định trạng thái, rồi Gatherer tính nhóm theo expected set. Nhưng phải phân biệt:

- **Terminal business rejection:** xác nhận được bên nhận từ chối.
- **Technical failure:** không xử lý được request, có thể chưa biết side effect.
- **Timeout/unknown:** không có kết quả tin cậy.

Đừng ép cả ba thành `REJECTED` rồi tuyên bố đã đủ phản hồi nghiệp vụ.

## 15. JUnit 5: unit tests cho quyết định partial-vs-fail

Các ví dụ dùng các record và `ScatterDecisionPolicy` ở mục 8. Thời gian được truyền qua tham số `Instant now` để test **không phụ thuộc đồng hồ thật hoặc `Thread.sleep`**.

### 15.1. Test chấp nhận partial khi đủ quorum và mandatory

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

class ScatterDecisionPolicyTest {
    private static final Instant DEADLINE =
        Instant.parse("2026-11-21T10:00:05Z");

    private static ScatterPlan plan(boolean allowPartial) {
        return new ScatterPlan(
            "RUN-901", "REQ-901", "quote-policy-v2",
            Set.of("FAST", "ECONOMY", "GLOBAL"),
            Set.of("FAST"), 2, allowPartial, DEADLINE);
    }

    private static ProviderReply accepted(String id, String price) {
        return new ProviderReply(id, ProviderStatus.ACCEPTED,
            new BigDecimal(price));
    }

    @Test
    void acceptsPartialOnlyAfterDeadlineWhenQuorumIsSatisfied() {
        List<ProviderReply> replies = List.of(
            accepted("FAST", "80000"),
            accepted("ECONOMY", "65000"));

        ScatterDecision before = ScatterDecisionPolicy.evaluate(
            plan(true), replies, DEADLINE.minusSeconds(1));
        assertEquals(DecisionStatus.WAITING, before.status());

        ScatterDecision after = ScatterDecisionPolicy.evaluate(
            plan(true), replies, DEADLINE);
        assertEquals(DecisionStatus.ACCEPTED_PARTIAL, after.status());
        assertEquals(2, after.respondedCount());
        assertEquals(List.of("GLOBAL"), after.missingProviders());
    }

    @Test
    void strictPolicyFailsWithSameTwoRepliesAtDeadline() {
        List<ProviderReply> replies = List.of(
            accepted("FAST", "80000"),
            accepted("ECONOMY", "65000"));

        ScatterDecision result = ScatterDecisionPolicy.evaluate(
            plan(false), replies, DEADLINE);

        assertEquals(DecisionStatus.FAILED, result.status());
        assertEquals(List.of("GLOBAL"), result.missingProviders());
    }

    @Test
    void requiredProviderMissingCannotBeOverriddenByQuorum() {
        List<ProviderReply> replies = List.of(
            accepted("ECONOMY", "65000"),
            accepted("GLOBAL", "60000"));

        ScatterDecision result = ScatterDecisionPolicy.evaluate(
            plan(true), replies, DEADLINE);

        assertEquals(DecisionStatus.FAILED, result.status());
        assertEquals(List.of("FAST"), result.missingProviders());
    }

    @Test
    void completeAndSuccessfulRepliesAreAcceptedComplete() {
        List<ProviderReply> replies = List.of(
            accepted("FAST", "80000"),
            accepted("ECONOMY", "65000"),
            accepted("GLOBAL", "60000"));

        ScatterDecision result = ScatterDecisionPolicy.evaluate(
            plan(true), replies, DEADLINE.minusSeconds(2));

        assertEquals(DecisionStatus.ACCEPTED_COMPLETE, result.status());
        assertEquals(3, result.respondedCount());
        assertTrue(result.missingProviders().isEmpty());
    }

    @Test
    void terminalRejectionFromMandatoryProviderFailsEarly() {
        List<ProviderReply> replies = List.of(
            new ProviderReply("FAST", ProviderStatus.REJECTED, null));

        ScatterDecision result = ScatterDecisionPolicy.evaluate(
            plan(true), replies, DEADLINE.minusSeconds(4));

        assertEquals(DecisionStatus.FAILED, result.status());
        assertEquals("MANDATORY_PROVIDER_REJECTED", result.reasonCode());
    }

    @Test
    void duplicateReplyDoesNotCountAsAnotherProvider() {
        ProviderReply fast = accepted("FAST", "80000");

        ScatterDecision result = ScatterDecisionPolicy.evaluate(
            plan(true), List.of(fast, fast), DEADLINE);

        assertEquals(1, result.respondedCount());
        assertEquals(DecisionStatus.FAILED, result.status());
    }

    @Test
    void conflictingDuplicateMustNotChooseRandomWinner() {
        assertThrows(IllegalArgumentException.class, () ->
            ScatterDecisionPolicy.evaluate(
                plan(true), List.of(
                    accepted("FAST", "80000"),
                    accepted("FAST", "70000")), DEADLINE));
    }

    @Test
    void noReplyFailsAtDeadlineRatherThanInventingSuccess() {
        ScatterDecision result = ScatterDecisionPolicy.evaluate(
            plan(true), List.of(), DEADLINE);

        assertEquals(DecisionStatus.FAILED, result.status());
        assertEquals(0, result.respondedCount());
        assertEquals(3, result.missingProviders().size());
    }
}
~~~

**Đây là unit test nghiệp vụ**, không chứng minh Gatherer, Scheduler, MessageGroupStore hay external provider chạy đúng. Nó giúp kiểm tra chính sách mà không phải đợi 5 giây cho mỗi test.

### 15.2. Test cần bổ sung: tất cả trả lời, một bên từ chối

Một case quan trọng không nằm trong ví dụ JUnit trên:

~~~text
FAST: ACCEPTED
ECONOMY: REJECTED
GLOBAL: ACCEPTED

Expected group size = 3
Received group size = 3
Accepted count = 2

Strict policy  -> FAILED
Partial policy -> ACCEPTED_PARTIAL
Completeness   -> ALL_RESPONDED
~~~

Do đó, **“partial” trong business policy không nhất thiết đồng nghĩa “thiếu reply”**. Có thể **đủ mọi reply** nhưng chỉ **một phần** thành công. Hãy giữ hai chiều `completeness` và `business decision` trong response/metrics nếu cần giải thích kết quả.

## 16. Integration tests cho Spring Integration Scatter-Gather

Để kiểm thử toàn bộ flow, thay external providers bằng **test handlers** hoặc **Gateway stubs** kiểm soát được phản hồi. Dùng `QueueChannel` làm điểm thu final result, và test từng tình huống có timeout hữu hạn.

### 16.1. Test happy path 3/3

~~~text
Given:
  ScatterPlan expected = [FAST, ECONOMY, GLOBAL]
  All three fake handlers return a valid ProviderReply
  Reply messages preserve executionId/correlation

When:
  Send QuoteRequest into quotes.in

Then:
  Gatherer emits one combined group
  Policy result = ACCEPTED_COMPLETE
  Unique respondent count = 3
  No duplicate final output
  Each provider received exactly one request
~~~

Cần assert **đúng tập recipient được scatter**, không chỉ assert có output ở Gatherer. Nếu cả ba test handlers nhận do một misconfiguration duplicate, group có thể “đủ số lượng” nhưng thực ra thiếu provider khác.

### 16.2. Test timeout partial 2/3

~~~text
Given:
  FAST replies at once
  ECONOMY replies at once
  GLOBAL deliberately does not reply
  ScatterPlan allows partial after deadline

When:
  Start scatter-gather execution
  Trigger the configured group expiry / deadline
  Wait for final output with a bounded timeout

Then:
  One final decision = ACCEPTED_PARTIAL
  Missing provider = GLOBAL
  Caller does not see an unqualified "complete" result
  No second final decision after deadline
~~~

**Không dùng `Thread.sleep` ngẫu nhiên để suy ra thời điểm timeout.** Test nên có `TaskScheduler`/clock điều khiển được hoặc thời hạn ngắn với chờ theo điều kiện, đủ dư để tránh flaky test trên CI. Nhớ rằng group timeout khác deadline của request.

### 16.3. Test strict failure với cùng dữ liệu

Với **cùng hai replies FAST + ECONOMY**, nhưng `allowPartial=false`, assert:

- Kết quả cuối `FAILED`, reason `DEADLINE_WITHOUT_REQUIRED_RESULTS`.
- Missing list chứa `GLOBAL`.
- Không gọi downstream handler có side effect của **luồng accepted**.
- Error/rejection được gửi theo một hợp đồng rõ, không chỉ im lặng drop.
- Không retry toàn bộ scatter vô hạn.

### 16.4. Test zero replies

Không cho bất kỳ fake provider nào trả về. Xác nhận:

1. Deadline watcher (được kích hoạt từ `ScatterExecution`) quan sát execution mở.
2. Không có `MessageGroup` trong Gatherer nếu chưa có reply.
3. Finalizer phát `FAILED(NO_REPLIES)` hoặc `QuoteTimedOut` đúng một lần.
4. Gateway/caller nhận timeout response theo SLA đã định.
5. Không có late reply nào được tự tạo một new execution.

### 16.5. Test duplicate, out-of-order, late reply và race

| Kịch bản | Kết quả cần assert |
| --- | --- |
| Replies đến `GLOBAL → FAST → ECONOMY` | Nhóm đúng, không phụ thuộc arrival order |
| FAST gửi hai lần | Unique reply count vẫn 1 |
| FAST gửi hai giá khác nhau | Quarantine/conflict, không chọn giá ngẫu nhiên |
| Reply từ provider không expected | Bị từ chối trước Gatherer |
| Reply thiếu executionId | Không trộn nhóm, error path rõ |
| GLOBAL đến sau PARTIAL | Late/reconcile; không phát final thứ hai |
| Cả ba xong đúng sát deadline | Một outcome cuối qua atomic finalize |
| Scheduler không chạy | Có alert, không chờ group vô hạn |
| Restart khi mới có 2/3 | Phù hợp với MessageGroupStore/recovery contract |
| Hai JVM cùng xử lý group | Có lock/CAS/shared-state, không double-release |

Các integration tests cần **cô lập state**; không tái sử dụng cùng execution ID giữa test nếu MessageGroupStore hoặc context được cache mà không cleanup.

## 17. Release và completion với Gateway request–reply

Nếu caller sử dụng `@MessagingGateway` hoặc một Gateway đợi kết quả Scatter-Gather, cần biết:

- **Gateway reply timeout** là hạn chờ tại ranh giới caller.
- **Recipient timeout** là thời hạn một request riêng tới provider.
- **Group timeout** là chính sách đợi/expire của Gatherer.
- **Business deadline** là SLA tuyệt đối do quy trình xác định.

Các giá trị phải tương thích. Ví dụ deadline nghiệp vụ 5 giây nhưng Gateway timeout chỉ 3 giây sẽ làm caller bỏ cuộc trước khi hệ thống đánh giá partial, dù Gatherer có thể trả tại giây 5.

Tương tự, Gateway timeout 60 giây trong khi business deadline 5 giây có thể khiến caller chờ thừa nếu finalizer không phát output. **Timeout ở các tầng không thay thế nhau**.

### 17.1. Cần trả gì cho client khi partial?

Một response có thể mang:

~~~json
{
  "requestId": "REQ-901",
  "executionId": "RUN-901",
  "status": "ACCEPTED_PARTIAL",
  "completeness": "MISSING_REPLIES",
  "acceptedQuotes": [
    {"providerId": "FAST", "price": 80000},
    {"providerId": "ECONOMY", "price": 65000}
  ],
  "missingProviders": ["GLOBAL"],
  "selectedProvider": "ECONOMY",
  "policyVersion": "quote-policy-v2"
}
~~~

Tùy contract, hệ thống có thể trả một mã HTTP phù hợp và trạng thái trong body. **Không mặc định partial luôn tương ứng một mã HTTP riêng nào đó**. Với API tài chính/bảo hiểm, một partial có thể là trạng thái **pending** thay vì cho phép người dùng tiến hành giao dịch.

### 17.2. Business response không được leak danh sách internal providers

Nếu tên provider, route nội bộ hoặc giá nhạy cảm không được phép lộ ra ngoài, DTO response cần một **projection** hợp lệ. Internal `ScatterDecision` có thể giữ thông tin rộng hơn; outbound Transformer chỉ xuất trường client được quyền xem.

## 18. Thống kê hiệu quả: latency và chất lượng kết quả

Quyết định partial-vs-fail luôn có **trade-off** giữa latency, availability, completeness và correctness.

| Chỉ số | Điều trả lời | Cảnh báo |
| --- | --- | --- |
| `scatter_request_count` | Có bao nhiêu lượt scatter? | Không bằng tổng số request gửi tới provider |
| `recipient_request_count` | Mỗi provider nhận bao nhiêu request? | Retry có thể làm số này tăng |
| `reply_valid_count` | Bao nhiêu valid replies? | Một reply hợp lệ có thể là REJECTED |
| `unique_accepted_count` | Bao nhiêu provider được chấp nhận? | Dedup theo logical provider |
| `partial_accepted_count` | Bao nhiêu kết quả partial được phép dùng? | Cần phân biệt quality với success |
| `strict_failed_count` | Bao nhiêu request fail toàn bộ? | Có thể do deadline, mandatory hoặc business rejection |
| `no_reply_count` | Bao nhiêu yêu cầu không nhận reply nào? | Cần watcher ở mức request |
| `late_reply_count` | Bao nhiêu reply đến sau đóng? | Có thể báo SLA/network issues |
| `group_open_age` | Có group nào giữ quá lâu? | Cảnh báo leak/reaper failure |
| `provider_latency_p95/p99` | Provider nào khiến deadline bị vượt? | Chỉ đo các reply thành công gây survivor bias |
| `business_conversion/outcome` | Partial có thực sự hữu ích? | Không chỉ nhìn tỷ lệ dispatch success |

### 18.1. Đừng chỉ tối ưu tỷ lệ partial accepted

Một chính sách cho phép partial ngay sau reply đầu tiên có thể giảm latency rất mạnh nhưng **tăng rủi ro giá cao**, kết quả thiếu dữ liệu hoặc vi phạm compliance.

Theo dõi **chất lượng quyết định**, ví dụ chênh lệch giữa giá được chọn ở thời điểm partial với giá tối ưu từ tất cả báo giá khi chúng đến sau, nếu policy/đạo đức dữ liệu cho phép đo. Không dùng thông tin tới muộn để ngầm chỉnh sửa giao dịch đã xác nhận.

### 18.2. Logging và metric cardinality

`executionId`, `requestId`, `customerId` và `correlationId` có cardinality cao: nên ở log/trace có phân quyền, không là tag metric tổng hợp. Các tag như `providerType`, `decisionStatus`, `timeoutReason` và `policyVersion` có thể kiểm soát hơn, nhưng cũng cần giới hạn tập giá trị và không log PII/secret của payload.

## 19. Một số anti-pattern cần tránh

| Anti-pattern | Hệ quả | Hướng cải thiện |
| --- | --- | --- |
| Đủ 2/3 replies là tự coi success | Reply có thể REJECTED hoặc duplicate | Đếm unique accepted providers và policy |
| Đổi expected từ 3 thành 2 sau timeout | Che giấu provider thiếu | Giữ expected gốc, đánh dấu partial |
| Dùng `group.size()` làm quorum | Duplicate làm đủ giả | Dedupe theo provider/business ID |
| Coi `sendPartialResultOnExpiry(true)` là business success | Caller dùng dữ liệu thiếu sai mục đích | Business decision processor sau Gatherer |
| Chỉ dùng group timeout cho zero reply | Không có group để expire | Request-level deadline watcher |
| Gắn `groupTimeout=5000` rồi tuyên bố SLA T0+5 | Deadline có thể bị tính từ sự kiện group | Lưu deadlineAt độc lập |
| Mọi lỗi HTTP đều tính là REJECTED | Lỗi mạng khác kết quả nghiệp vụ | Phân biệt terminal business/technical/unknown |
| Tắt partial mà không có lỗi/reply | Gateway có thể chờ timeout không rõ | Explicit failed/timeout response |
| Fail all nhưng không bù trừ side effect | Tài nguyên/tiền đã commit vẫn tồn tại | Saga/compensation/reconciliation |
| Retry toàn bộ scatter khi một provider mất | Gửi lặp tới bên đã thành công | Retry theo recipient với idempotency |
| Xóa group mà quên late replies | Tạo group mới hoặc final thứ hai | Tombstone/closed-state |
| Caller tự chọn mandatory provider | Vượt quy tắc bắt buộc | Trusted routing policy và authorization |
| Dùng `MessageHeaders.id` làm business key | Replay sinh ID khác | Stable operation ID, provider ID |
| Chỉ test policy mà không test reply routing | Wiring lỗi vẫn có thể timeout | Integration test scatter/gather thật |
| Test timeout bằng `Thread.sleep` cố định | Flaky dưới tải CI | Controllable clock/scheduler hoặc bounded await |
| Log mọi raw reply để debug | Rò rỉ PII/thông tin đối tác | Log reason và metadata tối thiểu |

## 20. Checklist trước khi triển khai

- [ ] Xác định **expected recipient set** và **mandatory recipient set** từ policy đáng tin cậy.
- [ ] Phân biệt **valid reply**, **accepted business result**, **rejected terminal result**, **technical error** và **unknown/missing**.
- [ ] Viết decision table cho strict, partial, quorum, mandatory và fail-fast.
- [ ] Không cho phép duplicate làm tăng số provider thành công.
- [ ] Đóng băng `ScatterPlan` và `policyVersion` cho một execution; không đổi nghĩa khi replay.
- [ ] Có `executionId`/correlation riêng cho mỗi lượt, và idempotency key ổn định cho side effects.
- [ ] Cấu hình Scatterer/Gatherer/reply channels đúng topology, bảo toàn headers cần thiết qua adapters.
- [ ] Định nghĩa release strategy và timeout/partial expiry có kiểm thử theo Spring Integration version đang dùng.
- [ ] Có deadline watcher ở mức request cho **zero replies** và deadline tuyệt đối.
- [ ] Có closed-state/tombstone để late reply không tạo final outcome thứ hai.
- [ ] Fail-all có quy tắc compensation/reconciliation khi recipient có side effect.
- [ ] Gateway timeout, recipient timeout, group timeout và business deadline nhất quán.
- [ ] Có unit tests policy và integration tests các nhánh happy/partial/strict/no-reply/duplicate/late/race.
- [ ] Có MessageGroupStore/recovery phù hợp nếu workflow phải sống qua restart.
- [ ] Monitor open groups, timeout, missing recipients, partial quality, late reply và idempotent finalization.
- [ ] Không để raw payload hoặc thông tin nhạy cảm rò qua logs/metric tags/outbound response.

## 21. Bài tập thực hành

Một dịch vụ duyệt hạn mức doanh nghiệp gửi yêu cầu đến ba bộ phận: `COMPLIANCE`, `RISK` và `CREDIT`. Cả ba phản hồi `APPROVED`, `REJECTED` hoặc không phản hồi trước deadline 8 giây. Theo quy định:

- `COMPLIANCE` là bên bắt buộc.
- `RISK` và `CREDIT` là hai nguồn đánh giá bổ sung.
- Chỉ được phê duyệt nếu `COMPLIANCE=APPROVED` **và** có ít nhất một trong `RISK`, `CREDIT` cũng `APPROVED`.
- `REJECTED` từ `COMPLIANCE` khiến yêu cầu thất bại ngay.
- Nếu một nguồn chưa phản hồi, được phép trả **`PENDING_PARTIAL`** phục vụ hiển thị tiến độ, nhưng **không được phép thực thi lệnh giải ngân** dựa trên kết quả đó.

**Yêu cầu:**

1. Vẽ sơ đồ Scatter-Gather với three recipients, Aggregator, business decision processor và output channels `approved`, `pending`, `failed`.
2. Lập decision table cho các tổ hợp 0/1/2/3 phản hồi, mandatory missing, terminal rejection và timeout.
3. Định nghĩa `ScatterPlan` có `executionId`, `deadlineAt`, `expectedSet`, `mandatorySet`, `policyVersion`.
4. Phân biệt “đủ điều kiện đề xuất duyệt” với “đã được phép giải ngân”; giải thích tại sao partial view không tương đương quyết định pháp lý cuối.
5. Thiết kế correlation, release strategy và timeout, tránh cho duplicate `RISK` làm đủ quorum giả.
6. Viết unit tests với đồng hồ giả, không dùng `Thread.sleep`, cho một điều kiện strict và một điều kiện partial.
7. Thiết kế request-level watcher cho 0 replies và late reply path sau khi request đã đóng.
8. Với một external service timeout nhưng có thể đã ghi nhận kết quả, đề xuất reconciliation/idempotency thay vì tự giả định đã bị từ chối.
9. Đề xuất observability: open groups, missing/rejected, policy version, retry, late reply và final decision, không lộ dữ liệu cá nhân.

**Gợi ý:** chính sách của bài tập **khác** ví dụ báo giá: partial ở đây chỉ được phép là **trạng thái quan sát chưa hoàn tất**, không phải quyền kích hoạt side effect giải ngân. Hãy tách hai enum hoặc hai trạng thái riêng `decisionCompleteness` và `authorizationToDisburse`.

## 22. Tổng kết

**Chấp nhận partial result hay fail toàn bộ** là một **quyết định nghiệp vụ** nằm trên cơ chế Scatter-Gather. Scatterer phân phát yêu cầu; Gatherer/MessageGroupStore/correlation gom replies và xác định thời điểm release hoặc expire. Nhưng **đủ số message không đồng nghĩa đủ kết quả có ích**, và **đã release một group không đồng nghĩa quyền thực hiện bước nghiệp vụ tiếp theo**.

Một thiết kế tốt giữ nguyên expected set, xác thực **unique provider replies**, quy định **mandatory recipients**, số lượng kết quả tối thiểu, deadline, cách trả partial và xử lý trường hợp fail-all. Với Spring Integration, cần cấu hình Scatter-Gather, Aggregator, `groupTimeout`, `sendPartialResultOnExpiry`, reply routing và error channel phù hợp; thêm **deadline watcher cho 0 replies**, closed-state/tombstone cho late replies, idempotency và compensation khi có side effect. Kiểm thử cả **độ đầy đủ, quyết định nghiệp vụ, race gần deadline và không phát hai final outcomes** để hệ thống vừa nhanh, vừa đúng hợp đồng, vừa có thể truy vết.

**Tài liệu tham khảo:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Scatter-Gather, Recipient List, Aggregator, Correlation Identifier); tài liệu Spring Integration về Scatter-Gather, Aggregators, Message Groups, Java DSL, Error Handling và Testing; Java SE về `Set`, `Map`, `Instant`, `BigDecimal` và concurrency primitives.

