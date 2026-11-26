# Độ bao phủ trạng thái và đường đi nghiệp vụ

Trong chương **Coverage theo module** của **SPRING_MODULITH_VERIFICATION_TESTING**, độ bao phủ trạng thái (*state coverage*) và đường đi nghiệp vụ (*business-path coverage*) trả lời câu hỏi sâu hơn số dòng lệnh đã chạy: **ứng dụng đi qua đúng những trạng thái, chuyển trạng thái và kết quả nghiệp vụ nào?** Với ứng dụng Spring Modulith, cần theo dấu hành vi trong từng application module, các tương tác qua API/event giữa module, trạng thái lưu trong database và tính nhất quán transaction. Kiểm chứng ranh giới bằng `ApplicationModules` và quality gate CI vẫn quan trọng; bài này tập trung vào **lựa chọn, hiện thực và đo lường kịch bản nghiệp vụ**.

Ta dùng xuyên suốt module **orders** xử lý đơn hàng và tương tác với **inventory**; các ví dụ giả định Java 17+, Spring Boot 3, Spring Modulith và JUnit Jupiter. Quy tắc như “đơn đã xác nhận không được hủy” chỉ là hợp đồng **của ví dụ**, cần thay bằng hợp đồng thật khi áp dụng.

## 1. Phân biệt state, transition và business-path coverage

Ba cấp độ được đo trên mô hình nghiệp vụ đã thống nhất, không được suy ra trực tiếp từ tỷ lệ line coverage:

| Loại | Đối tượng cần kiểm tra | Ví dụ với orders | Điểm mù |
| --- | --- | --- | --- |
| **State coverage** | Trạng thái hợp lệ nào đã được tạo và xác minh | `CREATED`, `RESERVED`, `CONFIRMED`, `CANCELLED`, `REJECTED` | Đã thấy state nhưng chưa chắc cách đi đến state đúng |
| **Transition coverage** | Cạnh hợp lệ và chuyển trạng thái bị cấm nào được kiểm tra | `RESERVED → CANCELLED` | Đã test cạnh nhưng chưa test chuỗi lệnh, side effect |
| **Business-path coverage** | Chuỗi bước từ khởi tạo đến kết quả, kể cả guard và hệ quả | Tạo → giữ hàng → xác nhận; giữ hàng → hủy → trả lại hàng | State cuối đúng nhưng event, tiền hoặc tồn kho sai |

Một test đi qua `CREATED → RESERVED → CONFIRMED` không kiểm tra được **hủy sau giữ hàng**. Một test khởi tạo trực tiếp đối tượng ở `CANCELLED` không chứng minh việc chuyển từ `CREATED` hoặc `RESERVED` sang trạng thái đó là hợp lệ. Hơn nữa, với retry, vòng lặp và thao tác lặp lại, tổng số đường đi có thể tăng rất lớn hoặc vô hạn; không tuyên bố “100% mọi path”. Hãy **định nghĩa tập hành trình nghiệp vụ bắt buộc và mẫu số được duyệt**.

## 2. Chốt mô hình trạng thái, bất biến và điểm kết thúc

| Trạng thái | Ý nghĩa | Bất biến cần giữ |
| --- | --- | --- |
| `CREATED` | Đơn được tạo, chưa giữ hàng | Chưa được xác nhận giao hàng |
| `RESERVED` | Đã giữ hàng thành công | Có reservation còn hiệu lực |
| `CONFIRMED` | Đơn được chốt | Không nhận lệnh hủy trong workflow ví dụ |
| `CANCELLED` | Đơn được hủy hợp lệ | Nếu từng giữ hàng, đã yêu cầu giải phóng đúng một lần |
| `REJECTED` | Đơn không đủ điều kiện | Không chuyển sang xác nhận |

Trong mô hình này, `CONFIRMED`, `CANCELLED`, `REJECTED` là các trạng thái kết thúc:

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> RESERVED: RESERVE
    CREATED --> CANCELLED: CANCEL
    CREATED --> REJECTED: REJECT
    RESERVED --> CONFIRMED: CONFIRM
    RESERVED --> CANCELLED: CANCEL
    CONFIRMED --> [*]
    CANCELLED --> [*]
    REJECTED --> [*]
~~~

**Bất biến** phải được kiểm tra tại chỗ quan sát được: với `RESERVED`, xác minh reservation trong inventory; với `CANCELLED`, xác minh reservation được giải phóng nếu đã tồn tại; với `CONFIRMED`, xác minh các tiền điều kiện. Chỉ so sánh enum trạng thái chưa đủ nếu side effect không phù hợp.

## 3. Lập ma trận chuyển trạng thái trước khi viết code

Thay vì tạo test theo các nhánh hiện có trong implementation, hãy lấy hợp đồng nghiệp vụ làm đầu vào. Với bốn command `RESERVE`, `CONFIRM`, `CANCEL`, `REJECT`:

| State hiện tại | `RESERVE` | `CONFIRM` | `CANCEL` | `REJECT` |
| --- | --- | --- | --- | --- |
| `CREATED` | `RESERVED` | **Cấm** | `CANCELLED` | `REJECTED` |
| `RESERVED` | **Cấm** | `CONFIRMED` | `CANCELLED` | **Cấm** |
| `CONFIRMED` | **Cấm** | **Cấm** | **Cấm** | **Cấm** |
| `CANCELLED` | **Cấm** | **Cấm** | **Cấm** | **Cấm** |
| `REJECTED` | **Cấm** | **Cấm** | **Cấm** | **Cấm** |

Với ma trận này có **5 trạng thái đạt được** từ `CREATED`, **5 cạnh hợp lệ** và **15 cặp state–command bị cấm** trong tổng số `5 × 4 = 20` cặp. Đây là các mẫu số có thể kiểm tra tự động. Đường đi nghiệp vụ không chỉ là một cạnh: cần danh sách kịch bản được product owner/BA xác nhận.

Phân biệt **cấm theo thứ tự** (ví dụ `CONFIRM` khi chưa giữ hàng) với **không đủ điều kiện** (hết hàng nên phải `REJECT`). State machine chặn loại thứ nhất; guard/policy lựa chọn nhánh nghiệp vụ ở loại thứ hai.

## 4. Tách quy tắc chuyển trạng thái thuần Java

Một state machine không phụ thuộc DB giúp duyệt mọi cặp state–command bằng JUnit nhanh chóng:

~~~java
// src/main/java/com/example/shop/orders/OrderWorkflow.java
package com.example.shop.orders;

import java.util.Objects;

public final class OrderWorkflow {

    public enum Status {
        CREATED, RESERVED, CONFIRMED, CANCELLED, REJECTED
    }

    public enum Command {
        RESERVE, CONFIRM, CANCEL, REJECT
    }

    private OrderWorkflow() {
    }

    public static Status next(Status current, Command command) {
        Objects.requireNonNull(current, "current");
        Objects.requireNonNull(command, "command");

        return switch (current) {
            case CREATED -> switch (command) {
                case RESERVE -> Status.RESERVED;
                case CANCEL -> Status.CANCELLED;
                case REJECT -> Status.REJECTED;
                default -> invalid(current, command);
            };
            case RESERVED -> switch (command) {
                case CONFIRM -> Status.CONFIRMED;
                case CANCEL -> Status.CANCELLED;
                default -> invalid(current, command);
            };
            case CONFIRMED, CANCELLED, REJECTED -> invalid(current, command);
        };
    }

    private static Status invalid(Status current, Command command) {
        throw new IllegalStateException(
                "Cannot " + command + " from " + current);
    }
}
~~~

**Điểm thiết kế:** `next(...)` nhận đủ dữ liệu để quyết định trạng thái kế tiếp; nó không tự gửi event, lưu DB hoặc gọi bean module khác. Những tác vụ đó thuộc service ứng dụng. Việc không truyền null là contract bắt buộc và đã được kiểm tra rõ ràng. Khi orders cần kiểm tra tồn kho, nó gọi API **được công bố** của inventory qua service/policy; test kiến trúc `ApplicationModules.of(...).verify()` vẫn cần chạy độc lập để phát hiện coupling qua package nội bộ.

## 5. Dùng JUnit 5 bao phủ 5 cạnh hợp lệ và 15 cặp bị cấm

Mỗi test dữ liệu phải assert **kết quả đích chính xác**, và mỗi cạnh cấm phải bị từ chối. Danh sách expected trong test là một hợp đồng độc lập để reviewer so sánh với ma trận:

~~~java
// src/test/java/com/example/shop/orders/OrderWorkflowTests.java
package com.example.shop.orders;

import static com.example.shop.orders.OrderWorkflow.Command.*;
import static com.example.shop.orders.OrderWorkflow.Status.*;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.params.provider.Arguments.arguments;

import java.util.Arrays;
import java.util.Set;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import com.example.shop.orders.OrderWorkflow.Command;
import com.example.shop.orders.OrderWorkflow.Status;

class OrderWorkflowTests {

    @ParameterizedTest(name = "{0} + {1} -> {2}")
    @MethodSource("allowedEdges")
    void acceptsEachAllowedEdge(
            Status current, Command command, Status expected) {
        assertEquals(expected, OrderWorkflow.next(current, command));
    }

    static Stream<Arguments> allowedEdges() {
        return Stream.of(
                arguments(CREATED, RESERVE, RESERVED),
                arguments(CREATED, CANCEL, CANCELLED),
                arguments(CREATED, REJECT, REJECTED),
                arguments(RESERVED, CONFIRM, CONFIRMED),
                arguments(RESERVED, CANCEL, CANCELLED));
    }

    @ParameterizedTest(name = "{0} + {1} is forbidden")
    @MethodSource("forbiddenPairs")
    void rejectsForbiddenPair(Status current, Command command) {
        assertThrows(IllegalStateException.class,
                () -> OrderWorkflow.next(current, command));
    }

    static Stream<Arguments> forbiddenPairs() {
        Set<String> allowed = Set.of(
                "CREATED:RESERVE",
                "CREATED:CANCEL",
                "CREATED:REJECT",
                "RESERVED:CONFIRM",
                "RESERVED:CANCEL");
        return Arrays.stream(Status.values())
                .flatMap(current -> Arrays.stream(Command.values())
                        .filter(command -> !allowed.contains(
                                current.name() + ":" + command.name()))
                        .map(command -> arguments(current, command)));
    }

    @Test
    void rejectsNullInput() {
        assertThrows(NullPointerException.class,
                () -> OrderWorkflow.next(null, RESERVE));
        assertThrows(NullPointerException.class,
                () -> OrderWorkflow.next(CREATED, null));
    }
}
~~~

Bộ test tạo **5 case hợp lệ**, **15 case bị cấm**, **2 case null**. Khi thêm enum value, kiểm tra các cặp mới tự mở rộng, còn việc thêm cạnh hợp lệ phải cập nhật cả `allowedEdges()` và tập `allowed`. Nếu bỏ quên, test cố tình fail để yêu cầu xem xét thay đổi. Ở tầng module, các case bị cấm còn phải chứng minh **không ghi DB và không phát event**.

## 6. Kiểm thử business path bằng checkpoint ở từng bước

Ma trận kiểm tra từng cạnh chưa chứng minh thứ tự command, bất biến trung gian hoặc kết quả cuối:

| Mã | Kịch bản | Chuỗi trạng thái | Side effect ở test tích hợp |
| --- | --- | --- | --- |
| `P1` | Đơn thành công | `CREATED → RESERVED → CONFIRMED` | Giữ hàng và xác nhận một lần |
| `P2` | Hủy trước khi giữ | `CREATED → CANCELLED` | Không giữ hàng |
| `P3` | Hủy sau khi giữ | `CREATED → RESERVED → CANCELLED` | Hoàn reservation |
| `P4` | Bị từ chối | `CREATED → REJECTED` | Không xác nhận đơn |
| `P5` | Xác nhận quá sớm | `CREATED → CONFIRM` bị chặn | Giữ nguyên state, không phát event |
| `P6` | Callback xác nhận lặp | Sau `CONFIRMED` nhận lại `CONFIRM` | Chặn hoặc idempotent theo contract, không làm side effect kép |

JUnit parameterized test cho **bốn journey hợp lệ** với assertion sau từng bước:

~~~java
// src/test/java/com/example/shop/orders/OrderJourneyTests.java
package com.example.shop.orders;

import static com.example.shop.orders.OrderWorkflow.Command.*;
import static com.example.shop.orders.OrderWorkflow.Status.*;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.params.provider.Arguments.arguments;

import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import com.example.shop.orders.OrderWorkflow.Command;
import com.example.shop.orders.OrderWorkflow.Status;

class OrderJourneyTests {

    @ParameterizedTest(name = "{0}")
    @MethodSource("journeys")
    void observesEachCheckpoint(
            String name, List<Command> commands, List<Status> expected) {
        Status current = CREATED;
        List<Status> observed = new ArrayList<>();
        observed.add(current);

        for (Command command : commands) {
            current = OrderWorkflow.next(current, command);
            observed.add(current);
        }

        assertEquals(expected, observed);
    }

    static Stream<Arguments> journeys() {
        return Stream.of(
                arguments("P1 confirm",
                        List.of(RESERVE, CONFIRM),
                        List.of(CREATED, RESERVED, CONFIRMED)),
                arguments("P2 cancel early",
                        List.of(CANCEL),
                        List.of(CREATED, CANCELLED)),
                arguments("P3 cancel reserved",
                        List.of(RESERVE, CANCEL),
                        List.of(CREATED, RESERVED, CANCELLED)),
                arguments("P4 reject",
                        List.of(REJECT),
                        List.of(CREATED, REJECTED)));
    }
}
~~~

`P5` và `P6` cần test từ chối hoặc idempotency đúng hợp đồng, **có assertion về state và side effect sau lỗi**. Journey test thuần Java chỉ chứng minh chuỗi trạng thái. Test module/tích hợp phải lặp lại các checkpoint quan trọng trên dữ liệu được lưu, event và thay đổi của module inventory.

## 7. Guard coverage: tổ hợp điều kiện, biên và lỗi phụ thuộc

Không phải cạnh hợp lệ nào cũng nên xảy ra với mọi dữ liệu. Ví dụ, giữ hàng chỉ xảy ra khi còn hàng **và** thanh toán được duyệt. Tách guard thành policy có thể test độc lập:

~~~java
// src/main/java/com/example/shop/orders/ReservationPolicy.java
package com.example.shop.orders;

import com.example.shop.orders.OrderWorkflow.Command;

public final class ReservationPolicy {

    private ReservationPolicy() {
    }

    public static Command choose(
            boolean stockAvailable, boolean paymentApproved) {
        return stockAvailable && paymentApproved
                ? Command.RESERVE
                : Command.REJECT;
    }
}
~~~

~~~java
// src/test/java/com/example/shop/orders/ReservationPolicyTests.java
package com.example.shop.orders;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import com.example.shop.orders.OrderWorkflow.Command;

class ReservationPolicyTests {

    @ParameterizedTest
    @CsvSource({
            "true,  true,  RESERVE",
            "true,  false, REJECT",
            "false, true,  REJECT",
            "false, false, REJECT"
    })
    void handlesInputCombinations(
            boolean inStock, boolean paymentApproved, Command expected) {
        assertEquals(expected,
                ReservationPolicy.choose(inStock, paymentApproved));
    }
}
~~~

Hai cặp `true/true` với `false/true`, và `true/true` với `true/false` còn chứng minh từng điều kiện có ảnh hưởng độc lập đến quyết định (*MC/DC* cho biểu thức ví dụ). Trong luồng thật, boolean “còn hàng” thường đến từ inventory; phải test biên `availableQuantity == requestedQuantity`, thiếu một đơn vị, timeout, lỗi hệ thống và retry. Đạt cả true/false cho biểu thức `A && B` chưa bảo đảm đã xét đầy đủ tổ hợp `A=false, B=true` và `A=true, B=false`.

## 8. Bao phủ event và đường đi qua ranh giới module

Orders có thể phát event khi chuyển state để inventory hoặc module khác phản ứng. Để đo một path xuyên module, cần kiểm tra **event đúng payload, đúng số lần, gắn cùng correlation ID và tác động của consumer**. Ví dụ dưới minh họa **publication** trong một Spring test context:

~~~java
// src/main/java/com/example/shop/orders/OrderStateChanged.java
package com.example.shop.orders;

import java.util.UUID;
import com.example.shop.orders.OrderWorkflow.Status;

public record OrderStateChanged(
        UUID orderId, Status from, Status to) {
}
~~~

~~~java
// src/main/java/com/example/shop/orders/OrderTransitionService.java
package com.example.shop.orders;

import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import com.example.shop.orders.OrderWorkflow.Command;
import com.example.shop.orders.OrderWorkflow.Status;

@Service
public class OrderTransitionService {

    private final ApplicationEventPublisher publisher;

    public OrderTransitionService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public Status apply(UUID id, Status current, Command command) {
        Status next = OrderWorkflow.next(current, command);
        publisher.publishEvent(new OrderStateChanged(id, current, next));
        return next;
    }
}
~~~

~~~java
// src/test/java/com/example/shop/orders/OrderTransitionModuleTests.java
package com.example.shop.orders;

import static com.example.shop.orders.OrderWorkflow.Command.*;
import static com.example.shop.orders.OrderWorkflow.Status.*;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;

@ApplicationModuleTest
@RecordApplicationEvents
class OrderTransitionModuleTests {

    @Autowired
    OrderTransitionService transitions;

    @Autowired
    ApplicationEvents recordedEvents;

    @Test
    void publishesOneEventForValidEdge() {
        UUID id = UUID.randomUUID();

        assertEquals(RESERVED, transitions.apply(id, CREATED, RESERVE));

        var matching = recordedEvents.stream(OrderStateChanged.class)
                .filter(event -> event.orderId().equals(id))
                .toList();
        assertEquals(1, matching.size());
        assertEquals(CREATED, matching.get(0).from());
        assertEquals(RESERVED, matching.get(0).to());
    }

    @Test
    void publishesNothingForForbiddenEdge() {
        UUID id = UUID.randomUUID();

        assertThrows(IllegalStateException.class,
                () -> transitions.apply(id, CONFIRMED, CANCEL));

        assertEquals(0L, recordedEvents.stream(OrderStateChanged.class)
                .filter(event -> event.orderId().equals(id))
                .count());
    }
}
~~~

`@ApplicationModuleTest` đặt ở package **orders**; `@RecordApplicationEvents` và `ApplicationEvents` thuộc Spring Test. Đoạn test chỉ chứng minh event **đã được publish trong test context**. Nó chưa bảo đảm inventory nhận và xử lý thành công, transaction commit, hoặc listener `@TransactionalEventListener(phase = AFTER_COMMIT)` đã chạy. Khi kiểm tra đường đi liên module, cần test tích hợp với transaction thực sự commit, trace cùng `orderId` từ command → event → consumer → DB. Với listener bất đồng bộ, dùng cơ chế đợi điều kiện có giới hạn thay vì giả định callback chạy tức thì.

## 9. Transaction, DB và cạnh tranh trạng thái

Với JPA, quy tắc về trạng thái phải đúng **sau flush/commit**, không chỉ trên entity còn trong bộ nhớ. Ví dụ một entity dùng optimistic locking để phát hiện hai transaction đồng thời:

~~~java
// Trích đoạn entity nằm trong module orders
@Enumerated(EnumType.STRING)
@Column(nullable = false)
private OrderWorkflow.Status status = OrderWorkflow.Status.CREATED;

@Version
private long version;

public void apply(OrderWorkflow.Command command) {
    status = OrderWorkflow.next(status, command);
}
~~~

Ma trận test tích hợp nên bao gồm:

1. **Thành công:** tạo đơn, thực hiện `RESERVE`, flush/commit, đọc lại trong persistence context mới; assert `RESERVED` cùng reservation tồn tại.
2. **Lệnh sai:** cố `CONFIRM` khi `CREATED`; assert exception, rollback và state đọc lại vẫn `CREATED`; không có event thành công.
3. **Hủy sau giữ hàng:** sau commit `CANCEL`, state là `CANCELLED`, reservation đã giải phóng; nếu consumer xử lý qua event thì kiểm tra kết quả consumer.
4. **Tranh chấp:** hai transaction độc lập đọc cùng version, cùng cập nhật; một lần commit hợp lệ, giao dịch còn lại bị phát hiện conflict hoặc retry theo hợp đồng. Với JPA, conflict có thể xuất hiện khi flush/commit và được Spring chuyển thành `ObjectOptimisticLockingFailureException`.
5. **Retry/callback trùng:** không nhân đôi giữ hàng, thanh toán hay event; dùng idempotency key và unique constraint khi cần.

Hai lời gọi tuần tự trong một transaction **không phải** concurrency test; phải tạo hai transaction độc lập và đồng bộ điểm đọc/ghi. `@Version` cũng không bảo đảm *exactly once* cho message broker. Khi dùng event handler `AFTER_COMMIT`, test tự động rollback sẽ không quan sát được hành vi sau commit: cần transaction boundary rõ ràng và môi trường DB đủ giống production để kiểm tra constraint/isolation/migration.

## 10. Báo cáo state/path coverage và thiết kế quality gate CI

Hãy duy trì **ma trận test–yêu cầu** để tránh đếm các test trùng mà bỏ sót một path quan trọng:

| Chỉ số | Mẫu số của mô hình ví dụ | Bằng chứng |
| --- | --- | --- |
| State coverage | 5 state có thể đạt được | Journey checkpoint, DB state |
| Legal transition coverage | 5 cạnh hợp lệ | `allowedEdges()`, test module |
| Forbidden transition coverage | 15 cặp bị cấm | `forbiddenPairs()` |
| Required path coverage | 6 path `P1–P6` đã được duyệt | JUnit scenario và test side effect |
| Side-effect coverage | Các hệ quả được liệt kê trong tiêu chí chấp nhận | DB, inventory, event, transaction |

Mẫu số path **không** phải tổng số đường đi tổ hợp trên đồ thị; nó là danh sách được xác nhận theo nghiệp vụ và cập nhật mỗi lần đổi contract. Ví dụ unit test có thể đạt 5/5 cạnh, 15/15 cặp bị cấm nhưng chưa có test xác nhận inventory trả hàng sau hủy. Không cộng các chỉ số thành một “điểm chất lượng” duy nhất.

Trong CI, duy trì các gate riêng: **JUnit contract** kiểm tra ma trận legal/forbidden; **journey tests** kiểm tra P1–P6 cùng side effect; **ApplicationModules verification** phát hiện vi phạm phụ thuộc; **JaCoCo** phát hiện vùng code thiếu test; **integration tests** xác nhận event và database sau commit. Có thể chạy:

~~~yaml
- name: Verify module boundaries, journeys and code coverage
  run: ./gradlew check jacocoTestReport
~~~

Lệnh này chỉ bao phủ những test/task **đã gắn vào `check`**. Nếu nhóm có task riêng như `integrationTest`, phải thêm task đó vào pipeline và tổng hợp coverage liên quan; nếu chỉ chạy unit test thì chưa có bằng chứng cho path liên module. Nên đánh dấu rõ path nào **chưa có test** trong báo cáo thay vì bỏ khỏi mẫu số để tỷ lệ trông đẹp.

## 11. Checklist nghiệm thu và bài tập thực hành

- [ ] Danh sách state, terminal state, command và invariant được duyệt theo nghiệp vụ.
- [ ] Ma trận legal/forbidden công khai; quy tắc xử lý command lặp được quyết định rõ.
- [ ] JUnit assert state **đích**, exception cho cạnh bị cấm và không có thay đổi phụ.
- [ ] Có checkpoint cho các đường đi thành công, hủy sớm, hủy sau reservation, từ chối và lỗi.
- [ ] Guard được test với tổ hợp điều kiện, giá trị biên và lỗi từ API module phụ thuộc.
- [ ] Event có `orderId`, kiểm tra payload/số lần phát; khi cần có test consumer và commit.
- [ ] DB test kiểm tra flush/commit/rollback, conflict và idempotency tại ranh giới transaction.
- [ ] Các mẫu số state, transition, path là tài liệu có thể review; JaCoCo không thay chúng.
- [ ] `ApplicationModules.verify()` và test module/tích hợp chạy trong quality gate CI.
- [ ] Báo cáo có thể chỉ ra path nào chưa được test hoặc đang fail cùng yêu cầu liên quan.

**Bài tập:** mở rộng workflow cho phép `RESERVED → REJECTED` khi thanh toán bị thu hồi. Trước khi sửa code, hãy cập nhật sơ đồ, ma trận và các mẫu số; viết test legal edge mới, loại cặp này khỏi forbidden pairs; bổ sung path `CREATED → RESERVED → REJECTED` và test giải phóng reservation sau commit. Chủ động tạo lỗi “phát event hai lần” để chứng minh test side effect phát hiện được, dù trạng thái cuối vẫn đúng.

**Tiêu chí hoàn thành:** người học xác định được mẫu số coverage từ hợp đồng state machine, viết JUnit parameterized test cho transition, kiểm tra checkpoint của journey và phân biệt bằng chứng domain với bằng chứng event/DB/transaction qua ranh giới module Spring Modulith.
