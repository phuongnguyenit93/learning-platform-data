# Release một lần khi đủ tín hiệu

## 1. Bài toán: nhiều nhánh hoàn tất, nhưng chỉ được mở cổng một lần

Trong module **SPRING_INTEGRATION_PATTERN**, ta dùng Spring Integration triển khai các Enterprise Integration Patterns nhằm xây dựng luồng message ít phụ thuộc và dễ mở rộng. Một Gateway nhận lệnh, Router tách các quyết định nghiệp vụ, Filter kiểm tra dữ liệu, Transformer đổi cấu trúc payload; các kết quả được gửi qua channel tới những handler khác nhau. Khi có nhiều xử lý song song, một bước tiếp theo có thể cần đợi **đủ tín hiệu** trước khi thực hiện.

Ví dụ một đơn hàng chỉ được chuyển sang bước **READY_TO_SHIP** khi cùng lúc đã có:

1. **PAYMENT_AUTHORIZED** — thanh toán được xác nhận.
2. **STOCK_RESERVED** — hàng đã được giữ thành công.
3. **FRAUD_APPROVED** — bước kiểm tra rủi ro đã chấp thuận.

Ba sự kiện có thể đến **khác thứ tự**, từ nhiều Service Activator, qua các channel và có thể bị giao lại do retry. Yêu cầu không chỉ là “nhận được đủ ba lần gọi”, mà là:

- Mỗi đơn hàng được đánh giá bằng đúng **correlation key**.
- Chỉ tính **tín hiệu hợp lệ, khác loại và thuộc cùng lần xử lý**.
- Khi đủ điều kiện, phát **một quyết định release duy nhất** cho đơn hàng đó.
- Tín hiệu trùng lặp, đến muộn hoặc đến đồng thời **không tạo thêm release**.
- Nếu hết thời hạn chờ, có đường timeout/error rõ ràng thay vì giữ nhóm mãi.

Đây là bài toán **Barrier**: chỉ cho công việc vượt qua một điểm đồng bộ khi điều kiện đã đạt. Với yêu cầu “đủ nhiều tín hiệu”, ta thường dùng **Aggregator hoặc một bộ điều phối trạng thái** để gom điều kiện, sau đó tạo **một trigger release** cho barrier. Không nên giả định một Barrier handler có sẵn luôn tự đếm mọi tín hiệu N-of-M theo ý nghĩa nghiệp vụ.

~~~mermaid
flowchart TD
    A[Gateway: Create order] --> B[WAITING: order-101]
    C[PAYMENT_AUTHORIZED] --> D[Correlate + Deduplicate]
    E[STOCK_RESERVED] --> D
    F[FRAUD_APPROVED] --> D
    D --> G{Đủ 3 loại tín hiệu?}
    G -->|Chưa| H[Tiếp tục WAITING]
    G -->|Đủ| I{Chưa release và chưa timeout?}
    I -->|Có| J[Đổi trạng thái thành RELEASED]
    J --> K[Phát một ReleaseCommand]
    I -->|Không| L[Bỏ qua trùng / xử lý sự kiện muộn]
    K --> M[Ship flow]
~~~

**Release một lần** nói về **quyết định mở cổng theo từng barrier instance**. Nó không có nghĩa message chỉ được giao đúng một lần qua mạng, hay tác vụ phía sau được thực thi exactly-once mà không cần idempotency.

## 2. Định nghĩa đúng “đủ tín hiệu”

Có hai kiểu điều kiện cần phân biệt:

| Chính sách | Ví dụ | Cách tính |
| --- | --- | --- |
| **All-of** | Cần payment, stock **và** risk | Tập tín hiệu phải chứa đủ ba loại bắt buộc |
| **Quorum / K-of-N** | Cần 2 trong 3 nguồn xác nhận độc lập | Đếm **nguồn hợp lệ khác nhau**, không đếm message trùng |

Trong ví dụ đơn hàng, điều kiện là:

~~~text
required = {PAYMENT_AUTHORIZED, STOCK_RESERVED, FRAUD_APPROVED}
received = tập các loại tín hiệu hợp lệ thuộc cùng barrierId
ready    = received chứa đủ required
~~~

Nếu nhận **PAYMENT_AUTHORIZED** ba lần, ta vẫn chỉ có **một loại tín hiệu** và không được release. Nếu nhận **PAYMENT_AUTHORIZED**, **STOCK_RESERVED** và **FRAUD_REJECTED**, ta cũng không được release: tín hiệu từ chối khác với chấp thuận.

Một tín hiệu cần có ít nhất:

| Trường | Mục đích |
| --- | --- |
| **barrierId / correlationId** | Chọn chính xác nhóm đang chờ |
| **signalType** | Xác định điều kiện nghiệp vụ đã thỏa mãn |
| **eventId** | Nhận diện delivery trùng của cùng một sự kiện |
| **workflowAttempt / version** | Không trộn tín hiệu của lần xử lý cũ với lần mới |
| **occurredAt** | Phục vụ kiểm tra thời hạn, audit và xử lý sự kiện trễ |
| **tenant context được xác thực** | Không ghép tín hiệu giữa hai tenant khác nhau |

Correlation key nên là **tenant + order + workflow attempt** hoặc một định danh gate duy nhất đã được cấp tại ingress, không chỉ là một mã đơn hàng có thể được tái sử dụng.

## 3. Một state machine có trạng thái kết thúc

Một barrier cần phân biệt **đang chờ**, **đã release** và **đã hết hạn**.

~~~mermaid
stateDiagram-v2
    [*] --> WAITING
    WAITING --> WAITING: Tín hiệu mới nhưng chưa đủ
    WAITING --> WAITING: Tín hiệu trùng, bỏ qua
    WAITING --> RELEASED: Đủ tín hiệu, chuyển trạng thái nguyên tử
    WAITING --> EXPIRED: Quá thời hạn chờ
    RELEASED --> RELEASED: Trùng hoặc đến muộn, không release lại
    EXPIRED --> EXPIRED: Tín hiệu đến trễ, không tự mở cổng
~~~

| Trạng thái | Tín hiệu mới | Có phát release? |
| --- | --- | --- |
| **WAITING**, chưa đủ | Lưu tín hiệu hợp lệ chưa thấy | Không |
| **WAITING**, đủ bộ | Đổi thành RELEASED **một lần** | Chỉ caller thắng điều kiện chuyển trạng thái |
| **RELEASED** | Trùng hoặc đến muộn | Không |
| **EXPIRED** | Tín hiệu muộn | Không; xử lý theo chính sách late-event |
| **CANCELLED** (nếu nghiệp vụ có) | Đơn bị hủy trước khi đủ điều kiện | Không |

Để tránh việc một luồng báo đủ tín hiệu và luồng khác báo timeout cùng thắng, cả hai phải cạnh tranh trên **một trạng thái chung** bằng compare-and-set hoặc giao dịch. Chỉ một trong các chuyển đổi **WAITING → RELEASED** và **WAITING → EXPIRED** được phép thành công.

Trạng thái RELEASED cũng phải được giữ đủ lâu để các bản tin lặp không mở lại barrier. Nếu xóa state ngay sau khi phát release và một bản tin cũ quay lại, nhóm mới vô tình có thể được tạo và release lần hai.

## 4. Barrier không phải CountDownLatch hay Aggregator

Các cơ chế dễ bị nhầm lẫn:

| Cơ chế | Vai trò | Giới hạn cần nhớ |
| --- | --- | --- |
| **Barrier EIP** | Chặn một request cho tới khi nhận tín hiệu mở cổng có correlation phù hợp | Không mặc định biết ba loại tín hiệu nghiệp vụ |
| **Aggregator EIP** | Gom nhiều message theo correlation và release strategy | Cần completion, timeout và duplicate handling chính xác |
| **CountDownLatch / CyclicBarrier Java** | Đồng bộ thread trong một tiến trình | Không lưu bền message, không phù hợp làm cơ chế bảo đảm giao dịch phân tán |
| **Coordinator có trạng thái** | Theo dõi tập tín hiệu, quyết định release một lần | Cần atomicity, lifecycle, durability và dọn dẹp |
| **Durable outbox** | Ghi sự kiện release để gửi tin cậy sau commit | Consumer vẫn cần idempotency vì giao hàng có thể lặp |

**Spring Integration Barrier** thường được hình dung như điểm giữ một request cho tới khi có trigger tương ứng. Nếu yêu cầu **ba sự kiện khác nhau** trước khi trigger, có thể đặt một **Aggregator/coordinator phía trước trigger channel**. Một signal tới trigger channel chỉ có ý nghĩa release khi bản thân signal đó đã đại diện cho việc **đủ điều kiện**, chứ không phải mỗi tín hiệu con đều được phép mở barrier.

~~~mermaid
flowchart LR
    R[Request chờ] --> B[Barrier: order-101]
    S1[Payment signal] --> A[Aggregator / Coordinator]
    S2[Stock signal] --> A
    S3[Risk signal] --> A
    A -->|Đủ điều kiện, một trigger| T[Release trigger]
    T --> B
    B --> O[Request được tiếp tục xử lý]
~~~

Nếu hệ thống cần giữ một thread chờ, phải kiểm soát timeout và concurrency. Với nhiều đơn hàng hoặc thời gian đợi dài, nên ưu tiên **điều phối bất đồng bộ bằng trạng thái bền vững** thay vì giữ hàng nghìn thread trong một in-memory barrier.

## 5. Các race condition gây release trùng

Xét ba worker nhận ba tín hiệu gần như đồng thời. Một cách triển khai không an toàn:

~~~java
// PHẢN VÍ DỤ: read-check-write không nguyên tử.
State state = repository.load(barrierId);
state.add(signal);

if (state.hasAllRequired() && !state.isReleased()) {
    sendRelease(barrierId);
    state.setReleased(true);
}
repository.save(state);
~~~

Hai worker có thể cùng đọc **released = false**, cùng thấy đủ tín hiệu và cùng gửi release. Dù cuối cùng database lưu released = true, side effect **đã xảy ra hai lần**.

Cách an toàn hơn là:

1. Nhận và deduplicate tín hiệu theo eventId hoặc ràng buộc nghiệp vụ.
2. Cập nhật tập tín hiệu bằng một thao tác đồng bộ hóa theo barrierId.
3. Nếu tập đủ, thử chuyển trạng thái **WAITING → RELEASED** bằng thao tác **nguyên tử**.
4. **Chỉ tiến trình thắng** được tạo release decision.
5. Để chịu được crash giữa việc ghi trạng thái và gửi message, ghi **outbox** trong cùng transaction.
6. Consumer dùng **idempotency key** để không thực hiện side effect hai lần khi broker giao lại outbox event.

Không đưa thao tác gọi REST, publish broker hoặc commit nghiệp vụ **vào trong hàm compute/lock** dài; phần giữ khóa nên ngắn và xác định được kết quả. Nếu phát event ngoài transaction mà không có outbox, vẫn tồn tại cửa sổ crash làm mất release.

## 6. Java: coordinator trong một JVM để minh họa one-shot decision

Đoạn code sau chỉ minh họa **một quyết định release cho một key trong một tiến trình**. Nó hữu ích khi học atomic state transition, nhưng **không phải** phương án production đầy đủ vì không chịu được restart, không có timeout bền vững và không tự bảo đảm delivery.

### 6.1. Hợp đồng message

~~~java
public enum SignalKind {
    PAYMENT_AUTHORIZED,
    STOCK_RESERVED,
    FRAUD_APPROVED
}

public record BarrierSignal(
        String barrierId,
        String eventId,
        SignalKind kind
) {}

public record ReleaseCommand(
        String barrierId,
        String releaseKey
) {}

public record GateState(
        Set<SignalKind> received,
        boolean released
) {}
~~~

Ví dụ này dùng **mỗi signal kind là một điều kiện boolean**. Một sự kiện trùng kind không tăng số lượng điều kiện đã hoàn tất. Nếu cùng kind có nhiều nguồn cần đếm độc lập, key dedup phải bao gồm **sourceId** hoặc định danh khác theo hợp đồng.

### 6.2. Thao tác chuyển trạng thái nguyên tử theo barrierId

~~~java
@Component
public class BarrierCoordinator {

    private static final Set<SignalKind> REQUIRED = Set.of(
            SignalKind.PAYMENT_AUTHORIZED,
            SignalKind.STOCK_RESERVED,
            SignalKind.FRAUD_APPROVED
    );

    private final ConcurrentHashMap<String, GateState> states =
            new ConcurrentHashMap<>();

    /**
     * Trả null nếu chưa đủ hoặc barrier đã RELEASED.
     * Chỉ một luồng có thể nhận ReleaseCommand cho một barrierId.
     */
    public ReleaseCommand onSignal(BarrierSignal signal) {
        AtomicReference<ReleaseCommand> firstRelease =
                new AtomicReference<>();

        states.compute(signal.barrierId(), (id, previous) -> {
            if (previous != null && previous.released()) {
                return previous;
            }

            EnumSet<SignalKind> received =
                    EnumSet.noneOf(SignalKind.class);

            if (previous != null) {
                received.addAll(previous.received());
            }
            received.add(signal.kind());

            boolean ready = received.containsAll(REQUIRED);

            if (ready) {
                firstRelease.set(
                        new ReleaseCommand(id, "release:" + id)
                );
            }

            return new GateState(Set.copyOf(received), ready);
        });

        return firstRelease.get();
    }
}
~~~

**Vì sao đoạn code chỉ quyết định release một lần?** Với cùng một key, **ConcurrentHashMap.compute** tuần tự hóa việc cập nhật bản ghi. Luồng đầu tiên thấy đủ tín hiệu đổi released thành true và nhận ReleaseCommand. Các luồng tiếp theo thấy released = true, trả lại state mà không tạo lệnh mới.

Trong ví dụ này **eventId** được lưu trong event nhưng chưa được dùng để deduplicate riêng. Quy tắc mỗi kind chỉ được tính một lần đã được bảo đảm bởi Set. Khi nghiệp vụ có tín hiệu nhiều lần theo kind hoặc cần audit eventId, phải bổ sung lưu tập eventId hay unique constraint bền vững.

**Giới hạn rất quan trọng:**

- State chỉ nằm trong RAM; restart sẽ làm mất lịch sử release.
- Không có deadline, EXPIRED hoặc CANCELLED; production phải bổ sung.
- Map tăng theo số barrierId và chưa có lifecycle cleanup. Xóa quá sớm có nguy cơ late event tạo release trùng.
- Nếu release command được tạo nhưng ứng dụng crash trước khi gửi, **lệnh release có thể mất**.
- Nếu gửi tới broker rồi consumer xử lý và message bị phát lại, **side effect vẫn có thể lặp**.

Vì thế ví dụ này minh họa **at-most-once release decision trong một JVM còn sống**, không hứa hẹn exactly-once delivery hay exactly-once business execution.

## 7. Nối coordinator vào Spring Integration Java DSL

Spring Integration có thể nhận tín hiệu từ các adapter khác nhau rồi chuẩn hóa về một payload **BarrierSignal** và đưa đến cùng channel.

~~~java
@Configuration
@EnableIntegration
public class BarrierFlowConfiguration {

    @Bean
    public IntegrationFlow barrierSignalFlow(
            BarrierCoordinator coordinator
    ) {
        return IntegrationFlow.from("barrier.signals")
                .handle(
                        BarrierSignal.class,
                        (signal, headers) ->
                                coordinator.onSignal(signal)
                )
                .channel("barrier.release.commands")
                .get();
    }

    @Bean
    public IntegrationFlow barrierReleaseFlow(
            ReleasePort releasePort
    ) {
        return IntegrationFlow.from("barrier.release.commands")
                .handle(
                        ReleaseCommand.class,
                        (command, headers) -> {
                            releasePort.deliver(command);
                            return null;
                        }
                )
                .get();
    }
}

public interface ReleasePort {
    void deliver(ReleaseCommand command);
}
~~~

Ở flow này:

- **barrier.signals** nhận các message **BarrierSignal** đã được xác thực và chuẩn hóa.
- **BarrierCoordinator.onSignal** trả **null** khi chưa đủ điều kiện hoặc đã release trước đó. Với Service Activator, kết quả null nghĩa là không có reply message để chuyển tiếp.
- Khi lần đầu đủ điều kiện, handler trả **ReleaseCommand**, được gửi qua **barrier.release.commands**.
- **ReleasePort** là abstraction của ứng dụng để tiếp tục công việc hoặc gửi sự kiện; đoạn code không tự tạo một consumer hay storage bền vững.

Các interface/record là ví dụ ứng dụng, không phải API mặc định của Spring Integration. Tùy phiên bản Spring Integration và cách dùng request-reply, cần xác minh hành vi không sinh reply của handler trong flow thực tế.

**Rủi ro crash trong ví dụ:** coordinator có thể đánh dấu RELEASED trong RAM, sau đó ReleasePort thất bại. Tín hiệu được retry sẽ thấy đã release và **không phát lại command**. Muốn bảo đảm có thể giao hàng sau lỗi, hãy chuyển sang mô hình transaction + outbox ở phần tiếp theo. Không thêm retry vào ReleasePort rồi coi như đã giải quyết tính nhất quán.

## 8. Production: transaction + unique constraint + outbox

Trong hệ thống nhiều pod, một map in-memory không phải nguồn trạng thái chung. Cần một cơ chế atomic mà các worker đều nhìn thấy, chẳng hạn transaction trên database có ràng buộc duy nhất.

Một thiết kế dữ liệu khái niệm:

~~~text
barrier_instance(
    barrier_id PRIMARY KEY,
    tenant_id,
    workflow_attempt,
    status,          -- WAITING | RELEASED | EXPIRED | CANCELLED
    created_at,
    deadline_at,
    released_at
)

barrier_signal(
    barrier_id,
    signal_kind,
    event_id,
    occurred_at,
    UNIQUE(barrier_id, signal_kind),
    UNIQUE(barrier_id, event_id)
)

outbox(
    event_id PRIMARY KEY,  -- "release:" + barrier_id
    barrier_id,
    event_type,
    payload,
    delivery_status,
    created_at
)
~~~

**Bản ghi barrier_instance** cần được tạo khi bắt đầu workflow (hoặc có cơ chế khởi tạo nguyên tử đáng tin cậy) để signal đến sớm không bị mất. Các ràng buộc UNIQUE nêu trên là ý tưởng về identity và dedup; nếu ứng dụng cho phép nhiều event cùng loại, phải thiết kế khóa khác theo nguồn/scope thực tế.

### 8.1. Một giao dịch quyết định release

~~~text
BEGIN TRANSACTION

1. SELECT barrier_instance WHERE barrier_id = :id FOR UPDATE
   -> khóa hàng để xử lý tuần tự các signal cùng barrierId.

2. Nếu status != WAITING hoặc đã quá deadline:
   -> không phát release; xử lý late/expired signal theo policy.

3. INSERT barrier_signal(...), bỏ qua nếu UNIQUE conflict.
   -> duplicate delivery không tạo thêm điều kiện.

4. Đọc số loại tín hiệu bắt buộc khác nhau đã được ghi nhận.
   Nếu còn thiếu:
   -> COMMIT và kết thúc, không tạo release.

5. Nếu đã đủ:
   UPDATE barrier_instance
      SET status = RELEASED, released_at = now()
    WHERE barrier_id = :id AND status = WAITING.
   -> chỉ tiếp tục nếu update đúng một row.

6. INSERT outbox(event_id = "release:" + :id, ...)
   với event_id duy nhất; trong cùng transaction.

COMMIT
~~~

Đây là **pseudocode giao dịch**, không phải cú pháp SQL có thể chạy nguyên văn ở mọi hệ quản trị. Nó diễn đạt hai bất biến:

1. Một barrierId chỉ có thể chuyển từ **WAITING sang RELEASED một lần**.
2. Bản ghi **RELEASED** và outbox release event xuất hiện **cùng commit**; không có trường hợp commit trạng thái xong nhưng mất quyết định phát event vì crash trước publish.

Một **outbox publisher** độc lập phát các event chưa giao và đánh dấu kết quả theo chính sách. Nếu broker ack bị mất, cùng outbox event có thể được phát lại. Do đó **consumer phải idempotent**, chẳng hạn lưu releaseKey đã xử lý bằng unique constraint trước khi gọi side effect, hoặc để upstream nhận idempotency key.

### 8.2. At-most-once, at-least-once và exactly-once

| Mục tiêu | Giải pháp và giới hạn |
| --- | --- |
| **Một release decision** | Atomic state transition cho từng barrierId |
| **Không mất release khi process crash** | Ghi outbox cùng transaction với quyết định |
| **Đưa release tới consumer dù bị lỗi tạm thời** | At-least-once delivery với retry có giới hạn |
| **Không thực hiện side effect trùng** | Idempotent consumer / idempotency key và đối soát |
| **Exactly-once end-to-end** | Không tự có chỉ vì dùng barrier, transaction hay broker; phải xem từng boundary |

Nếu lệnh release là “trừ tiền”, tiêu chí idempotency còn chặt hơn: cần hợp đồng trả lại kết quả cũ khi nhận trùng key và cơ chế reconciliation cho trường hợp kết quả bên ngoài không rõ.

## 9. Timeout và sự kiện đến muộn

Một barrier không thể đợi mãi trong trường hợp một hệ thống con không phản hồi. Cần một **deadline** được tạo khi bắt đầu workflow và được lưu cùng barrier instance.

Ví dụ:

| Thời điểm | Sự kiện | Trạng thái |
| --- | --- | --- |
| 09:00:00 | Tạo barrier, hạn 09:00:30 | WAITING |
| 09:00:05 | PAYMENT_AUTHORIZED | WAITING, 1/3 |
| 09:00:11 | STOCK_RESERVED | WAITING, 2/3 |
| 09:00:30 | Job timeout chuyển WAITING → EXPIRED | EXPIRED |
| 09:00:32 | FRAUD_APPROVED đến muộn | **Không** release vì EXPIRED |

Nếu tín hiệu cuối và job timeout đến **cùng lúc**, cả hai phải dùng cùng transaction/atomic compare-and-set trên state WAITING. Chỉ một nhánh được thắng; ứng dụng phải định nghĩa rõ quy tắc dùng thời gian (ví dụ server-side deadline, so sánh now với deadline_at) để tránh mỗi pod quyết định khác nhau.

Những lựa chọn khi hết hạn:

- **Fail fast** và trả kết quả **UNAVAILABLE/TIMEOUT** cho người dùng.
- **Hủy hoặc bù trừ** những thao tác đã thực hiện, ví dụ giải phóng giữ hàng khi không được duyệt.
- **Partial result** nếu hợp đồng nghiệp vụ thực sự cho phép.
- **Dead-letter / manual review** với correlation và lịch sử tín hiệu.

Đừng âm thầm phát release sau khi expired chỉ vì tín hiệu cuối cùng đến. Nếu nghiệp vụ cần cho phép mở lại workflow, hãy tạo **workflowAttempt mới và barrierId mới**, không tái sử dụng gate đã có trạng thái terminal.

### 9.1. Dọn state và chống replay trễ

Có thể xóa chi tiết signal sau TTL để tiết kiệm lưu trữ, nhưng phải giữ **tombstone/terminal marker** hoặc idempotency record đủ lâu so với khoảng mà duplicate delivery còn có thể xuất hiện.

Nếu xóa toàn bộ bản ghi RELEASED rồi để một signal cũ đến tạo barrier mới cùng key, ứng dụng có thể release lần nữa. Đó là lý do **retention policy**, định danh attempt và thời gian tối đa redelivery phải được thiết kế cùng nhau.

## 10. Retry, error channel và correlation

Trong Spring Integration, mỗi tín hiệu có thể được gửi qua QueueChannel, ExecutorChannel, broker adapter hoặc flow đồng bộ. Cần xác định điều gì xảy ra khi handler lỗi.

### 10.1. Retry không được đếm thêm tín hiệu

Nếu một signal **PAYMENT_AUTHORIZED** được broker phát lại ba lần do mất ACK, nó vẫn chỉ góp **một điều kiện payment**. Không dùng “đã nhận đủ ba message” nếu yêu cầu là “đã nhận đủ ba loại tín hiệu”.

Retry cần:

- Nhận diện event trùng bằng **eventId** hoặc uniqueness của **barrierId + signalKind**.
- Có giới hạn attempts và backoff nếu storage/broker lỗi.
- Không làm phát release lại sau terminal state.
- Giữ nguyên **barrierId, workflowAttempt, tenant context và traceId**.
- Dùng idempotency cho side effect do ReleaseCommand kích hoạt.

Một trigger bị gửi lại trong hệ thống at-least-once là điều bình thường; **một quyết định release duy nhất** không loại bỏ nhu cầu chống trùng ở consumer.

### 10.2. Error channel khác timeout của barrier

Trong flow đồng bộ qua **DirectChannel**, exception có thể truyền thẳng về Gateway caller. Trong flow bất đồng bộ, lỗi có thể đi qua **ErrorMessage/error channel** tùy cách cấu hình endpoint.

**Error channel** xử lý exception của một message; còn **barrier timeout** là tình trạng nhóm không nhận đủ tín hiệu theo deadline. Không thể chỉ đăng ký error channel rồi mặc định hệ thống sẽ tự hết hạn barrier. Cần scheduler/expiry workflow hoặc cơ chế completion timeout được component phù hợp hỗ trợ.

Nếu một signal đã được lưu bền vững nhưng logic release bị lỗi, error handler cần bảo đảm retry theo **cùng idempotency key** chứ không tạo barrier mới.

### 10.3. Correlation của Splitter và Aggregator

Splitter có thể sinh nhiều message con với **correlation ID**, **sequence number** và **sequence size**. Aggregator có thể dùng các header này để gom kết quả. Khi dùng nó tạo release trigger:

1. Gom đúng group theo **barrierId/workflowAttempt**, không chỉ dựa trên message đến cùng lúc.
2. Dùng correlation và completion strategy đủ chặt để xác định **đúng loại tín hiệu**.
3. Deduplicate trước khi kiểm tra đủ số nguồn.
4. Định nghĩa group timeout, expired-group handling và discard/error path.
5. Giữ định danh release duy nhất khi gửi trigger xuống barrier.

Một Aggregator hoàn tất nhóm và phát một message **không tự bảo đảm một side effect chỉ xảy ra một lần** trong môi trường crash/retry. Các bước tiêu thụ kết quả vẫn cần idempotency.

## 11. An toàn khi nhiều tenant và nhiều instance

Trong ứng dụng đa tenant hoặc nhiều pod:

- **Tenant ID phải được xác thực** ở ingress; không lấy trực tiếp từ header do bên ngoài tùy ý gửi mà tin là đúng.
- **BarrierId** phải phân biệt tenant và workflow attempt; không ghép signal giữa các tenant.
- Các pod phải dùng **một nguồn trạng thái chung** hoặc một hình thức phân vùng consumer bảo đảm atomicity; ConcurrentHashMap trên mỗi pod sẽ tạo những kết luận release khác nhau.
- Transaction, unique constraint, lease/lock và outbox cần được thiết kế theo storage thực tế.
- Không đưa **order ID, tenant ID chi tiết hoặc correlation ID** vào metric tags có cardinality cao; dùng log/trace được phân quyền để điều tra.
- Nếu barrier là bước trong giao dịch có tác dụng phụ, dùng **idempotency key** xuyên suốt downstream và một cơ chế đối soát khi cần.

Các nhóm đợi lâu cũng có nguy cơ tiêu tốn bộ nhớ hoặc làm đầy database. Cần giới hạn số barrier đang WAITING, TTL, quota và backpressure.

## 12. Kiểm thử release đúng một lần

Một bài test tốt phải đồng thời kiểm chứng:

- **Chưa đủ** các loại tín hiệu → không có release.
- **Đủ** → một release decision.
- **Trùng** cùng signalType/eventId → không có release bổ sung.
- **Khác thứ tự** → vẫn đạt cùng kết quả.
- **Đến đồng thời** → chỉ một luồng thắng.
- **Sau timeout/đã released** → không tạo release lại.
- **Restart và broker redelivery** → nếu yêu cầu bền vững, không mất release hoặc gây side effect trùng.

### 12.1. Unit test với coordinator in-memory

~~~java
@Test
void releasesOnceWhenAllDistinctSignalsArrive() {
    BarrierCoordinator coordinator = new BarrierCoordinator();
    String id = "tenant-A:order-101:attempt-1";

    assertNull(coordinator.onSignal(
            new BarrierSignal(id, "evt-1",
                    SignalKind.PAYMENT_AUTHORIZED)));

    assertNull(coordinator.onSignal(
            new BarrierSignal(id, "evt-2",
                    SignalKind.PAYMENT_AUTHORIZED)));

    assertNull(coordinator.onSignal(
            new BarrierSignal(id, "evt-3",
                    SignalKind.STOCK_RESERVED)));

    ReleaseCommand release = coordinator.onSignal(
            new BarrierSignal(id, "evt-4",
                    SignalKind.FRAUD_APPROVED));

    assertNotNull(release);
    assertEquals("release:" + id, release.releaseKey());

    // Replay sau RELEASED không làm phát thêm lần nữa.
    assertNull(coordinator.onSignal(
            new BarrierSignal(id, "evt-4",
                    SignalKind.FRAUD_APPROVED)));
}
~~~

### 12.2. Test đồng thời với nhiều tín hiệu trùng

~~~java
@Test
void concurrentSignalsProduceOnlyOneRelease() throws Exception {
    BarrierCoordinator coordinator = new BarrierCoordinator();
    String id = "tenant-A:order-102:attempt-1";

    List<BarrierSignal> events = List.of(
            new BarrierSignal(id, "p1",
                    SignalKind.PAYMENT_AUTHORIZED),
            new BarrierSignal(id, "s1",
                    SignalKind.STOCK_RESERVED),
            new BarrierSignal(id, "r1",
                    SignalKind.FRAUD_APPROVED),
            new BarrierSignal(id, "p1",
                    SignalKind.PAYMENT_AUTHORIZED),
            new BarrierSignal(id, "r1",
                    SignalKind.FRAUD_APPROVED)
    );

    ExecutorService workers = Executors.newFixedThreadPool(5);
    CountDownLatch start = new CountDownLatch(1);
    List<Future<ReleaseCommand>> futures = new ArrayList<>();

    try {
        for (BarrierSignal event : events) {
            futures.add(workers.submit(() -> {
                start.await();
                return coordinator.onSignal(event);
            }));
        }
        start.countDown();

        int releaseDecisions = 0;
        for (Future<ReleaseCommand> future : futures) {
            if (future.get() != null) {
                releaseDecisions++;
            }
        }
        assertEquals(1, releaseDecisions);
    } finally {
        workers.shutdownNow();
    }
}
~~~

Test này chỉ kiểm tra **atomic decision trong cùng JVM**. Nó không kiểm tra database transaction, outbox hoặc broker delivery. Với hệ thống nhiều pod, cần integration test có các worker thực sự cạnh tranh cập nhật **cùng một barrierId trên storage chung**, và test crash ở các điểm trước/sau commit.

### 12.3. Ma trận kiểm thử production

| Tình huống | Kỳ vọng |
| --- | --- |
| Thiếu một trong ba loại tín hiệu | WAITING, không release |
| Một loại signal được gửi nhiều lần | Dedup, không hoàn tất giả |
| Ba loại tín hiệu đến không đúng thứ tự | Đúng một release |
| Các tín hiệu đến đồng thời | Một lần chuyển WAITING → RELEASED |
| Worker restart giữa lúc chờ | Có thể phục hồi trạng thái từ storage |
| Crash sau commit nhưng trước broker publish | Outbox còn release event để phát |
| Broker giao release event hai lần | Consumer không thực hiện side effect trùng |
| Timeout và signal cuối cùng đua nhau | Chỉ một nhánh terminal thắng |
| Signal đến sau EXPIRED | Không tự release; đi theo late-event policy |
| Signal từ workflow attempt cũ | Không ghép vào attempt mới |
| Signal của tenant khác | Bị từ chối, không làm đủ điều kiện |
| Aggregator group thiếu nhánh | Timeout/partial/error path, không chờ vô hạn |
| Retry/error channel xử lý event trùng | Giữ correlation và idempotency |
| Outbox publisher thất bại tạm thời | Retry hữu hạn/backoff, không mất event |

## 13. Quan sát và vận hành

Theo dõi Barrier ở mức **group**, **signal**, **release decision** và **downstream outcome**:

| Metric/log | Cần biết gì? |
| --- | --- |
| **barriers_waiting** | Bao nhiêu group chưa đủ tín hiệu? |
| **barrier_wait_age** | Group nào sắp hết hạn? |
| **signals_received_by_type** | Điều kiện nào thường đến chậm? |
| **signals_duplicate / invalid** | Có replay, dữ liệu lỗi hoặc cố tình gửi trùng không? |
| **barrier_released_total** | Bao nhiêu group đã được quyết định release? |
| **barrier_expired_total** | Bao nhiêu group không bao giờ đủ tín hiệu? |
| **outbox_pending / oldest_age** | Quyết định release có đang chờ publish không? |
| **release_delivery_attempts** | Publisher có phải retry quá nhiều không? |
| **downstream_idempotent_duplicates** | Consumer có gặp delivery trùng không? |
| **Gateway/flow latency, Aggregator pending groups** | Barrier có gây chậm hoặc kẹt luồng EIP không? |

Log/trace nên giữ **barrierId, correlationId, workflowAttempt, eventId, signalType, state transition** và nguyên nhân timeout. Không nhét từng barrierId/orderId vào nhãn metric, vì điều đó tạo cardinality rất cao. Nếu cần so sánh các loại workflow, dùng metric tags ổn định như **flow name**, **signal kind** và **terminal state**.

Một dấu hiệu cần xử lý sớm là **barriers_waiting tăng liên tục trong khi barrier_released_total không tăng**. Có thể một nguồn signal ngừng phát, correlation bị sai, timeout chưa hoạt động hoặc event đang nằm trong error channel/DLQ.

## 14. Những lỗi thiết kế thường gặp

1. **Đếm message thay vì đếm điều kiện:** ba lần PAYMENT_AUTHORIZED không có nghĩa đủ cả payment, stock và risk.
2. **Dùng check-then-send không nguyên tử:** hai worker đồng thời phát release trùng.
3. **Gửi trước rồi mới đánh dấu RELEASED:** crash hoặc retry gây phát nhiều lần.
4. **Đánh dấu RELEASED rồi gửi không có outbox:** crash có thể làm mất release.
5. **Nhầm một quyết định release với exactly-once delivery:** broker vẫn có thể giao lại message.
6. **Xóa terminal state quá sớm:** event cũ tái tạo barrier và mở lại.
7. **Không xử lý deadline:** WAITING tồn tại mãi và chiếm tài nguyên.
8. **Dùng CountDownLatch để đợi hàng nghìn workflow:** giữ thread/bộ nhớ và không chịu được restart.
9. **Trộn correlation của nhiều tenant hoặc attempt:** nhóm phát release sai đơn hàng.
10. **Tưởng Aggregator completion là side effect once-only:** consumer vẫn cần idempotency.
11. **Không quan sát source signal bị thiếu:** chỉ thấy Gateway timeout mà không biết nhánh nào chưa hoàn tất.
12. **Phát lại lệnh ghi không có idempotency:** tạo đơn hàng hoặc thanh toán trùng.

## 15. Checklist áp dụng vào Spring Integration

- [ ] Xác định rõ all-of hoặc quorum, danh sách signalType và điều kiện từ chối.
- [ ] Mỗi barrier có key ổn định theo tenant/order/workflowAttempt.
- [ ] Validate nguồn signal và deduplicate theo identity phù hợp.
- [ ] Chỉ chuyển WAITING → RELEASED bằng thao tác nguyên tử.
- [ ] Race giữa release và timeout được giải quyết qua cùng một trạng thái terminal.
- [ ] Nếu dùng Spring Integration Barrier, trigger chỉ được gửi khi aggregator/coordinator xác nhận đủ điều kiện.
- [ ] Nếu cần bền vững/multi-pod, có database transaction, unique constraint và outbox.
- [ ] Consumer release idempotent; delivery trùng không tạo side effect trùng.
- [ ] Có deadline, late-event policy, terminal marker và retention tránh replay trễ.
- [ ] Retry và error channel giữ eventId, correlation ID, attempt và message gốc.
- [ ] Gateway, Router, Filter, Transformer, Splitter/Aggregator có đường partial/error rõ ràng.
- [ ] Có test thiếu tín hiệu, trùng lặp, bất kỳ thứ tự, đồng thời, timeout race và crash.
- [ ] Theo dõi pending groups, signal lag, expired groups, outbox backlog và release outcomes.

**Release một lần khi đủ tín hiệu** là một bất biến của workflow: với mỗi barrierId hợp lệ, chỉ một quyết định **WAITING → RELEASED** được phép thành công sau khi các điều kiện được thỏa mãn. Kết hợp Barrier với Aggregator/coordinator, correlation, atomic state transition, timeout, outbox và idempotency sẽ giúp luồng Spring Integration tiếp tục xử lý đúng thời điểm, không mất tín hiệu và không tạo side effect trùng khi có retry hoặc nhiều worker chạy đồng thời.
