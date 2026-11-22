# Đánh giá hai cách triển khai cùng một yêu cầu

Khi review một thay đổi, ta thường phải lựa chọn giữa hai cách triển khai đều có vẻ hợp lý. Một cách có thể dùng các điều kiện tuần tự rất rõ ràng; cách kia tổ chức quy tắc thành một danh sách có thể mở rộng. Cả hai có thể cho cùng kết quả hôm nay, nhưng khác nhau về cách đọc, khả năng thêm quy tắc, thứ tự ưu tiên, chi phí kiểm thử và rủi ro khi yêu cầu thay đổi.

Nếu chỉ nhìn số dòng hoặc mức độ “hiện đại” của kỹ thuật, ta dễ chọn nhầm. Một abstraction tổng quát có thể hữu ích khi quy tắc thay đổi thường xuyên, nhưng cũng có thể tạo thêm lớp gián tiếp cho một bài toán nhỏ. Một phương thức tuần tự có thể rất dễ hiểu ở hiện tại, nhưng trở nên khó mở rộng khi có nhiều quy tắc độc lập và thứ tự xử lý phức tạp.

Trong chương **Thực hành** của `CODE_QUALITY_FUNDAMENTALS`, bài học này đặt bạn vào vai trò reviewer: **đánh giá hai cách triển khai cùng một yêu cầu** bằng bằng chứng về hành vi, độ rõ ràng, khả năng thay đổi, kiểm thử và rủi ro vận hành. Nội dung gắn với mục tiêu của module: hiểu những thuộc tính khiến mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**.

Bạn sẽ làm việc với một bài toán đăng ký workshop. Hai triển khai Java 17 sử dụng cùng mô hình dữ liệu, cùng quy tắc và cùng thứ tự ưu tiên kết quả. Nhiệm vụ của bạn là kiểm tra chúng có thực sự tương đương không, xác định ưu/nhược điểm và chọn cách phù hợp với bối cảnh đã cho.

Sau bài học, bạn có thể:

- Chuyển yêu cầu tự nhiên thành quy tắc và trường hợp kiểm thử có thể quan sát.
- So sánh hai triển khai mà không để phong cách cá nhân thay thế bằng chứng.
- Phát hiện khác biệt ở giá trị biên, thứ tự ưu tiên và xử lý dữ liệu không hợp lệ.
- Đánh giá readability, maintainability, reliability, testability và chi phí thực thi.
- Viết nhận xét review nêu rõ rủi ro, tác động và bằng chứng cần bổ sung.
- Phân biệt quyết định đủ điều kiện với thao tác giữ chỗ thực tế trong hệ thống đồng thời.

## 1. Tình huống thực hành: kiểm tra điều kiện đăng ký workshop

Một nền tảng tổ chức workshop cần quyết định một người tham gia có đủ điều kiện đăng ký một buổi học hay không. Service đã tải dữ liệu cần thiết và tạo một snapshot gồm thông tin người tham gia, thời điểm hiện tại, thời điểm đóng đăng ký, số chỗ còn lại và việc người đó đã đăng ký trước đó hay chưa.

Ta cần viết một policy thuần để đánh giá snapshot và trả về một quyết định. Policy **không truy cập database, không gửi thông báo và không giữ chỗ**. Nó chỉ đánh giá dữ liệu đầu vào.

### 1.1. Yêu cầu nghiệp vụ đã được xác nhận

Các quy tắc phải được áp dụng theo thứ tự sau. **Quy tắc đầu tiên khớp sẽ quyết định kết quả**:

1. Nếu snapshot là `null`, mã người tham gia hoặc mã workshop rỗng, hoặc thiếu thời điểm hiện tại/thời điểm đóng đăng ký, trả `INVALID_INPUT`.
2. Nếu số chỗ còn lại âm, trả `INVALID_STATE`. Đây là dữ liệu không hợp lệ, không được hiểu như workshop đã hết chỗ.
3. Nếu thời điểm hiện tại bằng hoặc sau thời điểm đóng đăng ký, trả `REGISTRATION_CLOSED`. Thời điểm đóng là mốc **không còn được phép đăng ký**.
4. Nếu số chỗ còn lại bằng 0, trả `WORKSHOP_FULL`.
5. Nếu người tham gia đã đăng ký workshop này, trả `ALREADY_REGISTERED`.
6. Nếu không có điều kiện nào ở trên, cho phép đăng ký bằng `NONE`.

Các quy tắc có chủ ý phân biệt `remainingSeats < 0` với `remainingSeats == 0`: số âm biểu thị trạng thái dữ liệu bất thường cần điều tra; số 0 là tình trạng hết chỗ hợp lệ.

### 1.2. Thứ tự ưu tiên cũng là một phần của hợp đồng

Nếu workshop vừa đóng vừa hết chỗ, kết quả phải là `REGISTRATION_CLOSED`. Nếu workshop còn mở nhưng hết chỗ và người tham gia đã có tên, kết quả phải là `WORKSHOP_FULL`.

Điều này quan trọng vì một quyết định không chỉ có giá trị `accepted` hay `rejected`; lý do từ chối có thể được API hiển thị, ghi log hoặc dùng để hướng dẫn người dùng. Đổi thứ tự kiểm tra có thể đổi kết quả bên ngoài dù cả hai phiên bản đều từ chối đăng ký.

### 1.3. Phạm vi bài toán

Bài tập giả định dữ liệu snapshot đã được tải và truyền vào policy. Ta đang đánh giá **quyết định đủ điều kiện**, chưa thực hiện thao tác ghi nhận đăng ký.

Một policy đúng không tự bảo đảm còn chỗ khi request được ghi vào database. Nếu nhiều request chạy đồng thời, phần giữ chỗ phải được bảo vệ bằng transaction, cập nhật có điều kiện hoặc cơ chế đồng bộ phù hợp. Ta sẽ quay lại giới hạn này ở phần sau.

## 2. Mô hình dữ liệu dùng chung

Hai cách triển khai sử dụng cùng các kiểu sau. Hãy xem đây là hợp đồng đầu vào/đầu ra chung; khi so sánh, không thay đổi model để làm một phương án có lợi hơn.

```java
import java.time.Instant;
import java.util.Objects;

record RegistrationFacts(
        String participantId,
        String workshopId,
        Instant now,
        Instant registrationClosesAt,
        int remainingSeats,
        boolean alreadyRegistered) {}

enum RejectionReason {
    NONE,
    INVALID_INPUT,
    INVALID_STATE,
    REGISTRATION_CLOSED,
    WORKSHOP_FULL,
    ALREADY_REGISTERED
}

record RegistrationDecision(
        boolean accepted,
        RejectionReason reason) {

    RegistrationDecision {
        Objects.requireNonNull(reason, "reason");

        if (accepted && reason != RejectionReason.NONE) {
            throw new IllegalArgumentException(
                    "Accepted decision must use NONE");
        }
        if (!accepted && reason == RejectionReason.NONE) {
            throw new IllegalArgumentException(
                    "Rejected decision must have a reason");
        }
    }

    static RegistrationDecision allow() {
        return new RegistrationDecision(true, RejectionReason.NONE);
    }

    static RegistrationDecision deny(RejectionReason reason) {
        if (reason == RejectionReason.NONE) {
            throw new IllegalArgumentException(
                    "NONE cannot be a rejection reason");
        }
        return new RegistrationDecision(false, reason);
    }
}

interface RegistrationPolicy {
    RegistrationDecision evaluate(RegistrationFacts facts);
}
```

`RegistrationDecision` bảo vệ một bất biến nhỏ: quyết định được chấp nhận phải có lý do `NONE`, còn quyết định bị từ chối phải có lý do cụ thể. Nhờ đó, caller không thể tạo một kết quả mâu thuẫn như `accepted=true, reason=WORKSHOP_FULL`.

`RegistrationFacts` là record bất biến ở mức tham chiếu. Những trường `String` và `Instant` không bị thay đổi qua accessor; policy không được sửa snapshot trong lúc đánh giá.

## 3. Cách triển khai A: các điều kiện tuần tự tường minh

Cách A biểu diễn yêu cầu theo đúng thứ tự ưu tiên đã mô tả. Mỗi nhánh trả về ngay khi tìm thấy lý do đầu tiên.

```java
final class DirectRegistrationPolicy implements RegistrationPolicy {

    @Override
    public RegistrationDecision evaluate(RegistrationFacts facts) {
        if (!hasRequiredInput(facts)) {
            return RegistrationDecision.deny(
                    RejectionReason.INVALID_INPUT);
        }

        if (facts.remainingSeats() < 0) {
            return RegistrationDecision.deny(
                    RejectionReason.INVALID_STATE);
        }

        if (!facts.now().isBefore(facts.registrationClosesAt())) {
            return RegistrationDecision.deny(
                    RejectionReason.REGISTRATION_CLOSED);
        }

        if (facts.remainingSeats() == 0) {
            return RegistrationDecision.deny(
                    RejectionReason.WORKSHOP_FULL);
        }

        if (facts.alreadyRegistered()) {
            return RegistrationDecision.deny(
                    RejectionReason.ALREADY_REGISTERED);
        }

        return RegistrationDecision.allow();
    }

    private static boolean hasRequiredInput(RegistrationFacts facts) {
        return facts != null
                && facts.participantId() != null
                && !facts.participantId().isBlank()
                && facts.workshopId() != null
                && !facts.workshopId().isBlank()
                && facts.now() != null
                && facts.registrationClosesAt() != null;
    }
}
```

Điểm đáng chú ý:

- Phương thức đi từ kiểm tra đầu vào đến kiểm tra nghiệp vụ theo thứ tự ưu tiên.
- Guard clauses giúp người đọc thấy ngay điều kiện từ chối và lý do tương ứng.
- `hasRequiredInput` đặt logic kiểm tra dữ liệu bắt buộc ở một nơi.
- Không tạo danh sách rule hoặc object bổ sung cho mỗi lần đánh giá.
- Thứ tự ưu tiên hiện rõ ngay trong thân phương thức.

Với sáu quy tắc cố định, người đọc có thể lần theo từ trên xuống dưới mà không cần tìm một cấu hình khác.

## 4. Cách triển khai B: danh sách rule có thứ tự

Cách B biểu diễn mỗi quy tắc bằng một predicate và một lý do. Danh sách được duyệt tuần tự; rule đầu tiên khớp sẽ kết thúc việc đánh giá.

```java
import java.util.List;
import java.util.function.Predicate;

final class OrderedRuleRegistrationPolicy implements RegistrationPolicy {

    private record Rule(
            Predicate<RegistrationFacts> matches,
            RejectionReason reason) {}

    private static final List<Rule> RULES = List.of(
            new Rule(
                    facts -> !hasRequiredInput(facts),
                    RejectionReason.INVALID_INPUT),
            new Rule(
                    facts -> facts.remainingSeats() < 0,
                    RejectionReason.INVALID_STATE),
            new Rule(
                    facts -> !facts.now().isBefore(
                            facts.registrationClosesAt()),
                    RejectionReason.REGISTRATION_CLOSED),
            new Rule(
                    facts -> facts.remainingSeats() == 0,
                    RejectionReason.WORKSHOP_FULL),
            new Rule(
                    RegistrationFacts::alreadyRegistered,
                    RejectionReason.ALREADY_REGISTERED)
    );

    @Override
    public RegistrationDecision evaluate(RegistrationFacts facts) {
        for (Rule rule : RULES) {
            if (rule.matches().test(facts)) {
                return RegistrationDecision.deny(rule.reason());
            }
        }

        return RegistrationDecision.allow();
    }

    private static boolean hasRequiredInput(RegistrationFacts facts) {
        return facts != null
                && facts.participantId() != null
                && !facts.participantId().isBlank()
                && facts.workshopId() != null
                && !facts.workshopId().isBlank()
                && facts.now() != null
                && facts.registrationClosesAt() != null;
    }
}
```

Điểm đáng chú ý:

- Các rule nằm trong một danh sách bất biến, có thứ tự.
- Vòng lặp chung xử lý việc tìm rule đầu tiên khớp.
- Có thể thêm một rule bằng cách bổ sung phần tử vào danh sách.
- `Predicate` giúp biểu diễn điều kiện thành dữ liệu có thể truyền hoặc cấu hình.
- Thứ tự danh sách vẫn quyết định lý do từ chối nếu nhiều rule cùng khớp.

Cách B không tự động tốt hơn vì dùng abstraction. Nó chuyển một phần luồng điều khiển từ các câu lệnh `if` sang cấu trúc dữ liệu và lambda. Người đọc cần hiểu thêm `Rule`, `Predicate`, danh sách `RULES` và nguyên tắc “first match wins”.

**Lưu ý về null:** Rule đầu tiên phải bắt mọi trường hợp thiếu input. Các rule sau chỉ được chạy khi rule đầu không khớp, nên có thể truy cập `facts.remainingSeats()` và các thời điểm an toàn. Nếu ai đó di chuyển hoặc xóa rule đầu, các rule sau có thể ném `NullPointerException`. Thứ tự ở đây vừa là ưu tiên nghiệp vụ, vừa là một phần của điều kiện an toàn.

## 5. Kiểm tra hai cách có thực sự đáp ứng cùng yêu cầu

Không thể kết luận hai cách tương đương chỉ vì chúng trông giống nhau. Ta cần kiểm tra **từng quy tắc**, **thứ tự ưu tiên**, **giá trị biên** và **đường input lỗi**.

### 5.1. Bảng ca kiểm thử kỳ vọng

Thời điểm đóng đăng ký trong ví dụ là `2026-12-01T10:00:00Z`.

| Ca | Snapshot | Kết quả kỳ vọng |
| --- | --- | --- |
| **T1 – Hợp lệ** | Đủ ID, hiện tại trước giờ đóng, còn 2 chỗ, chưa đăng ký | `accepted=true`, `NONE` |
| **T2 – Snapshot null** | `facts == null` | `INVALID_INPUT` |
| **T3 – ID rỗng** | `participantId` chỉ chứa khoảng trắng | `INVALID_INPUT` |
| **T4 – Thiếu thời gian** | `now == null` | `INVALID_INPUT` |
| **T5 – Số chỗ âm** | `remainingSeats = -1` | `INVALID_STATE` |
| **T6 – Đúng giờ đóng** | `now == registrationClosesAt` | `REGISTRATION_CLOSED` |
| **T7 – Sau giờ đóng** | `now` sau `registrationClosesAt` | `REGISTRATION_CLOSED` |
| **T8 – Hết chỗ** | Còn 0 chỗ, chưa đóng, chưa đăng ký | `WORKSHOP_FULL` |
| **T9 – Đã đăng ký** | Còn chỗ, chưa đóng, `alreadyRegistered=true` | `ALREADY_REGISTERED` |
| **T10 – Đóng và hết chỗ** | Đã đóng, còn 0 chỗ | `REGISTRATION_CLOSED` |
| **T11 – Hết chỗ và trùng đăng ký** | Còn 0 chỗ, đã đăng ký, chưa đóng | `WORKSHOP_FULL` |

T10 và T11 không phải ca phụ. Chúng kiểm tra **thứ tự ưu tiên**. Nếu bỏ chúng, hai implementation có thể trả về các lý do khác nhau nhưng toàn bộ test cơ bản vẫn xanh.

### 5.2. Contract test chạy cùng bộ ca cho cả hai implementation

Một cách hữu ích là tạo cùng một bộ test cho mọi implementation của `RegistrationPolicy`. Trong ví dụ đơn giản, ta có thể duyệt hai policy trực tiếp:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;

class RegistrationPolicyContractTest {

    private static final Instant BEFORE_CLOSE =
            Instant.parse("2026-12-01T09:59:59Z");

    private static final Instant CLOSES_AT =
            Instant.parse("2026-12-01T10:00:00Z");

    private final List<RegistrationPolicy> policies = List.of(
            new DirectRegistrationPolicy(),
            new OrderedRuleRegistrationPolicy()
    );

    @Test
    void allowsValidRegistration() {
        RegistrationFacts facts = facts(
                BEFORE_CLOSE, CLOSES_AT, 2, false);

        assertForAll(facts, RegistrationDecision.allow());
    }

    @Test
    void rejectsNullSnapshot() {
        assertForAll(
                null,
                RegistrationDecision.deny(
                        RejectionReason.INVALID_INPUT));
    }

    @Test
    void rejectsBlankParticipantId() {
        RegistrationFacts facts = new RegistrationFacts(
                " ", "workshop-1", BEFORE_CLOSE,
                CLOSES_AT, 2, false);

        assertForAll(
                facts,
                RegistrationDecision.deny(
                        RejectionReason.INVALID_INPUT));
    }

    @Test
    void rejectsMissingTime() {
        RegistrationFacts facts = new RegistrationFacts(
                "participant-1", "workshop-1", null,
                CLOSES_AT, 2, false);

        assertForAll(
                facts,
                RegistrationDecision.deny(
                        RejectionReason.INVALID_INPUT));
    }

    @Test
    void distinguishesNegativeSeatsFromFullWorkshop() {
        assertForAll(
                facts(BEFORE_CLOSE, CLOSES_AT, -1, false),
                RegistrationDecision.deny(
                        RejectionReason.INVALID_STATE));

        assertForAll(
                facts(BEFORE_CLOSE, CLOSES_AT, 0, false),
                RegistrationDecision.deny(
                        RejectionReason.WORKSHOP_FULL));
    }

    @Test
    void closesRegistrationAtTheExactDeadline() {
        assertForAll(
                facts(CLOSES_AT, CLOSES_AT, 2, false),
                RegistrationDecision.deny(
                        RejectionReason.REGISTRATION_CLOSED));
    }

    @Test
    void closedReasonTakesPrecedenceOverFullReason() {
        assertForAll(
                facts(CLOSES_AT, CLOSES_AT, 0, false),
                RegistrationDecision.deny(
                        RejectionReason.REGISTRATION_CLOSED));
    }

    @Test
    void fullReasonTakesPrecedenceOverAlreadyRegistered() {
        assertForAll(
                facts(BEFORE_CLOSE, CLOSES_AT, 0, true),
                RegistrationDecision.deny(
                        RejectionReason.WORKSHOP_FULL));
    }

    @Test
    void rejectsAlreadyRegisteredParticipantWhenSeatExists() {
        assertForAll(
                facts(BEFORE_CLOSE, CLOSES_AT, 2, true),
                RegistrationDecision.deny(
                        RejectionReason.ALREADY_REGISTERED));
    }

    private void assertForAll(
            RegistrationFacts facts,
            RegistrationDecision expected) {
        for (RegistrationPolicy policy : policies) {
            assertEquals(
                    expected,
                    policy.evaluate(facts),
                    policy.getClass().getSimpleName());
        }
    }

    private static RegistrationFacts facts(
            Instant now,
            Instant closesAt,
            int remainingSeats,
            boolean alreadyRegistered) {
        return new RegistrationFacts(
                "participant-1",
                "workshop-1",
                now,
                closesAt,
                remainingSeats,
                alreadyRegistered);
    }
}
```

Bộ test này kiểm tra **kết quả mong đợi độc lập** cho cả hai policy. Đây là điểm quan trọng: nếu chỉ viết test so sánh A bằng B, hai implementation cùng sai vẫn có thể vượt qua.

Trong dự án thật, có thể tổ chức contract test bằng JUnit 5 `@TestFactory`, test interface hoặc parameterized test. Cách tổ chức nào phù hợp phụ thuộc số implementation và quy ước test của dự án; bài tập này ưu tiên cách đọc đơn giản.

### 5.3. Đối chiếu kết quả không thay thế test hợp đồng

Có thể thêm một test so sánh trực tiếp:

```java
@Test
void bothImplementationsAgreeForRepresentativeInputs() {
    RegistrationPolicy direct = new DirectRegistrationPolicy();
    RegistrationPolicy ordered = new OrderedRuleRegistrationPolicy();

    List<RegistrationFacts> examples = List.of(
            facts(BEFORE_CLOSE, CLOSES_AT, 2, false),
            facts(CLOSES_AT, CLOSES_AT, 0, false),
            facts(BEFORE_CLOSE, CLOSES_AT, 0, true),
            facts(BEFORE_CLOSE, CLOSES_AT, -1, false)
    );

    for (RegistrationFacts example : examples) {
        assertEquals(
                direct.evaluate(example),
                ordered.evaluate(example));
    }
}
```

Test này hữu ích để phát hiện khác biệt giữa hai phiên bản trong các ca được chọn. Nhưng nó không thay thế test kỳ vọng cụ thể ở mục trước. Nếu cả hai implementation cùng trả sai `WORKSHOP_FULL` thay vì `REGISTRATION_CLOSED`, test parity vẫn xanh.

## 6. So sánh theo các chiều chất lượng

Hai cách triển khai đều có thể đáp ứng đúng hợp đồng. Việc chọn cách nào phụ thuộc quy mô quy tắc, tần suất thay đổi, khả năng mở rộng và mức độ quen thuộc của nhóm.

| Tiêu chí | Cách A – Điều kiện tuần tự | Cách B – Danh sách rule |
| --- | --- | --- |
| **Đọc luồng điều khiển** | Rất trực tiếp; đọc từ trên xuống | Phải hiểu rule, predicate, list và vòng lặp |
| **Thấy thứ tự ưu tiên** | Thể hiện trực tiếp trong các nhánh | Phụ thuộc thứ tự phần tử trong danh sách |
| **Thêm một quy tắc cố định** | Thêm một guard clause | Thêm một `Rule` vào list |
| **Tái sử dụng rule** | Cần trích xuất phương thức hoặc policy riêng | Predicate có thể được truyền/tái sử dụng, nhưng cần quản lý phụ thuộc |
| **Kiểm tra null** | Có thể thấy quan hệ giữa các guard rõ ràng | Rule sau phụ thuộc rule trước đã loại input lỗi |
| **Debug** | Breakpoint theo từng nhánh đơn giản | Cần lần vào predicate và thứ tự duyệt |
| **Chi phí runtime** | Ít cấu trúc phụ trợ hơn | Có vòng lặp, predicate và indirection; thường nhỏ nhưng cần đo nếu nóng |
| **Khả năng cấu hình** | Không phải mục tiêu chính | Có thể phù hợp nếu rule list thật sự cần thay đổi theo cấu hình |
| **Nguy cơ overengineering** | Thấp với số rule nhỏ | Cao hơn nếu danh sách chỉ là lớp bọc cho vài `if` |
| **Nguy cơ rule order bị đổi** | Có thể xảy ra khi sắp xếp lại code | Có thể xảy ra khi di chuyển/thêm phần tử trong list |

### 6.1. Readability: người đọc phải giữ bao nhiêu thông tin trong đầu?

Ở cách A, một người mới có thể lần theo sáu nhánh ngay tại một phương thức. Các điều kiện và lý do từ chối ở gần nhau.

Ở cách B, phần điều kiện được đặt trong danh sách, còn cơ chế thực thi nằm trong vòng lặp. Cách này có thể dễ mở rộng, nhưng người đọc cần biết quy tắc “first match wins” và đảm bảo rule không có tác dụng phụ.

Nếu số quy tắc ít và cố định, abstraction của B có thể làm tăng số khái niệm mà không giảm độ phức tạp nghiệp vụ. Nếu danh sách rule được quản lý như một policy pipeline có cấu hình rõ, B có thể làm cho cấu trúc dễ hiểu hơn.

### 6.2. Maintainability: thêm quy tắc có dễ và an toàn không?

Giả sử yêu cầu mới là người tham gia bị khóa không được đăng ký. Cả hai cách đều có thể thêm quy tắc.

Với A, thêm một guard clause ở đúng vị trí ưu tiên. Với B, thêm một `Rule` vào đúng vị trí trong list. Không cách nào tự giải quyết câu hỏi **quy tắc mới phải ưu tiên trước hay sau quy tắc cũ**. Điều đó phải đến từ hợp đồng và test.

Nếu nhóm thường xuyên thêm/bớt rule qua cấu hình, plugin hoặc module độc lập, B có thể tạo một điểm mở rộng có chủ đích. Nhưng khi ấy cần thêm kiểm soát: ai có thể đăng ký rule, rule nào được phép chạy, cách xác định thứ tự, cách xử lý lỗi và cách quan sát.

### 6.3. Reliability: điều kiện lỗi và thứ tự có được bảo vệ không?

Cả A và B đều dùng short-circuit: khi một điều kiện từ chối đầu tiên khớp, các điều kiện sau không được đánh giá.

Với B, nếu một predicate có side effect hoặc phụ thuộc thứ tự ẩn, việc sắp xếp rule có thể làm thay đổi hành vi. Vì thế, predicate nên **thuần**, không ghi dữ liệu, không gửi event, không sửa snapshot và không phụ thuộc đồng hồ hệ thống bên trong. Thời điểm `now` được truyền vào snapshot để kết quả có thể tái lập.

Cả hai implementation cũng cần kiểm tra null trước khi truy cập các trường khác. B phụ thuộc rõ hơn vào rule đầu tiên, vì vậy thứ tự của list cần được bảo vệ bằng test.

### 6.4. Testability: kiểm thử có dễ đọc và dễ bảo trì không?

Hai cách cùng triển khai một interface nên có thể dùng chung contract tests. Đây là lợi thế của việc xác định hợp đồng trước khi so sánh.

Với B, có thể cần thêm test cho:

- Danh sách rule không rỗng và thứ tự đã định.
- Predicate không có tác dụng phụ.
- Rule mới được chèn đúng vị trí.
- Không có rule cấu hình trùng hoặc mâu thuẫn.

Với A, test tập trung vào các nhánh và thứ tự ưu tiên. Không cần test riêng một cấu trúc danh sách không tồn tại.

### 6.5. Performance: không đoán từ hình thức

Với sáu rule, cả hai cách đều thực hiện một số lượng phép kiểm tra nhỏ. Chênh lệch runtime có thể không đáng kể so với chi phí đọc database để tạo snapshot.

Không nên chọn A chỉ vì nó có ít abstraction hơn và khẳng định nó nhanh hơn đáng kể; cũng không nên chọn B vì lambda “tối ưu hơn”. Nếu policy nằm trên đường xử lý cực nóng, hãy benchmark bằng workload đại diện và đo chi phí toàn luồng. Nếu chưa có bằng chứng hiệu năng là vấn đề, readability và khả năng thay đổi thường là tiêu chí quyết định quan trọng hơn.

## 7. Hai implementation có thể cùng đúng nhưng phù hợp với bối cảnh khác nhau

### 7.1. Bối cảnh hiện tại: sáu rule cố định, nhóm cần đọc dễ dàng

Giả định:

- Bộ quy tắc nhỏ và đã được xác định.
- Chỉ nhóm sở hữu module mới thay đổi code.
- Không cần tải rule từ cấu hình hoặc plugin.
- Thứ tự ưu tiên là hợp đồng quan trọng.
- Policy chạy sau khi snapshot đã được tạo.
- Không có yêu cầu đo hiệu năng đặc biệt.

Trong bối cảnh này, **cách A thường là lựa chọn mặc định dễ hiểu hơn**. Nó biểu diễn đúng quy trình bằng guard clauses, không cần framework rule. Cách B vẫn hợp lệ nếu nhóm thấy danh sách rule rõ hơn, nhưng lợi ích mở rộng chưa chắc đủ bù indirection.

### 7.2. Bối cảnh thay đổi: rule được cấu hình theo từng chương trình

Giả sử nền tảng mở rộng để nhiều chương trình workshop có các quy tắc bổ sung, nhưng vẫn giữ một số rule chung. Các rule được đăng ký theo một pipeline có thứ tự và có owner.

Khi đó, cách B hoặc một thiết kế policy pipeline có kiểu rõ ràng có thể phù hợp hơn. Tuy nhiên, không nên đơn giản lấy `Predicate` tùy ý từ file cấu hình. Cấu hình thường chỉ nên chọn **các rule đã được định nghĩa và kiểm soát trong code**, với thứ tự, version và phạm vi rõ ràng.

Ví dụ cấu hình khái niệm:

```yaml
registrationRules:
  - INVALID_INPUT
  - INVALID_STATE
  - REGISTRATION_CLOSED
  - WORKSHOP_FULL
  - ALREADY_REGISTERED
```

Đây là ví dụ cấu hình, không phải đề xuất cho phép người dùng viết biểu thức code tùy ý. Nếu rule list được cấu hình, ứng dụng cần từ chối rule không hợp lệ, phát hiện rule trùng, xác định hành vi khi thiếu rule bắt buộc và kiểm tra thứ tự khi khởi động.

### 7.3. Khi cần trả về tất cả lý do từ chối

Hợp đồng hiện tại quy định **lý do đầu tiên**. Nếu sản phẩm muốn hiển thị đồng thời nhiều lý do, chẳng hạn “đã đóng đăng ký” và “đã hết chỗ”, thì cả hai implementation phải thay đổi hợp đồng.

A có thể tích lũy kết quả qua các điều kiện. B có thể duyệt toàn bộ danh sách thay vì dừng ở rule đầu tiên. Nhưng phải quyết định:

- Có trả mọi lỗi hay chỉ lỗi có thể hành động?
- Có thứ tự hiển thị không?
- Lỗi input có chặn việc đánh giá rule nghiệp vụ không?
- Một rule không thể chạy do thiếu dữ liệu được thể hiện thế nào?
- Có cần phân biệt lỗi hệ thống với lý do từ chối nghiệp vụ?

Đây là thay đổi yêu cầu, không phải lý do tự động để chọn B.

## 8. Ranh giới quan trọng: đánh giá đủ điều kiện không phải giữ chỗ

Hai policy trên chỉ nhận snapshot. Giả sử snapshot nói còn một chỗ:

1. Request A đọc `remainingSeats = 1`.
2. Request B cũng đọc `remainingSeats = 1`.
3. Cả A và B đều nhận quyết định `accepted=true`.
4. Nếu cả hai ghi đăng ký mà không có bảo vệ nguyên tử, hệ thống có thể nhận hai người vào một chỗ.

Đây là lỗi ở **ranh giới thực thi và đồng thời**, không phải khác biệt giữa hai kiểu viết điều kiện.

Một thao tác database có điều kiện có thể là một phần của giải pháp:

```sql
UPDATE workshops
SET remaining_seats = remaining_seats - 1
WHERE id = ?
  AND remaining_seats > 0;
```

Ứng dụng phải kiểm tra số hàng bị cập nhật. Nếu là 0, không có chỗ để giữ tại thời điểm thực thi. Việc ghi đăng ký người tham gia cần nằm trong transaction phù hợp và có ràng buộc duy nhất trên cặp `(workshop_id, participant_id)` để chặn đăng ký trùng trong cạnh tranh. Nếu thao tác sau thất bại, transaction phải hoàn tác việc giảm chỗ.

Đây chỉ là **mảnh minh họa**, không phải thiết kế transaction đầy đủ cho mọi database. Chi tiết locking, isolation, retry và xử lý duplicate phụ thuộc hệ quản trị dữ liệu cùng mô hình ghi của ứng dụng.

Điều reviewer cần nhận ra:

- Cả hai policy có thể đúng với snapshot đầu vào.
- Snapshot có thể cũ ngay sau khi được đọc.
- Quyết định đủ điều kiện không thay thế thao tác giữ chỗ nguyên tử.
- Test unit cho policy không chứng minh hệ thống không oversell.
- Cần integration/concurrency tests ở ranh giới database nếu đây là yêu cầu.

## 9. Bài tập thực hành: tự review trước khi xem gợi ý

Hãy dành thời gian tự đánh giá hai implementation ở mục 3 và 4. Không đọc phần gợi ý trước khi ghi lại nhận xét của bạn.

### Nhiệm vụ A — Kiểm tra tính tương đương

Với mỗi rule trong yêu cầu ở mục 1, hãy đánh dấu:

- Cách A có triển khai không?
- Cách B có triển khai không?
- Có phụ thuộc thứ tự không?
- Có ca test nào chứng minh kết quả không?

Đặc biệt kiểm tra T2, T5, T6, T10 và T11. Đây là các trường hợp dễ phát hiện khác biệt về null safety, dữ liệu bất thường và thứ tự ưu tiên.

### Nhiệm vụ B — Review chất lượng mã

Viết tối thiểu ba nhận xét cho mỗi implementation:

1. Một nhận xét về readability.
2. Một nhận xét về khả năng thay đổi.
3. Một nhận xét về độ tin cậy hoặc khả năng kiểm thử.

Mỗi nhận xét phải có cấu trúc:

- **Quan sát:** Dòng code hoặc cấu trúc nào gây chú ý?
- **Rủi ro/tác động:** Điều gì có thể khó hiểu, bị sai hoặc tốn chi phí?
- **Đề xuất:** Có thể làm gì cụ thể?
- **Điều kiện:** Đề xuất có phù hợp với yêu cầu hiện tại không?

Tránh nhận xét kiểu “B tốt hơn vì hiện đại hơn” hoặc “A xấu vì có nhiều if”. Hãy chỉ ra bằng chứng và bối cảnh.

### Nhiệm vụ C — Chọn phương án theo bối cảnh

Hãy chọn A hoặc B cho từng tình huống và giải thích:

1. Có sáu rule cố định, thay đổi ít, nhóm muốn code dễ debug.
2. Có nhiều rule đã được định nghĩa trong các module, được đăng ký theo thứ tự có kiểm soát.
3. Rule được người dùng cuối tự nhập dưới dạng biểu thức.
4. Cần trả về tất cả lý do từ chối, không chỉ lý do đầu tiên.
5. Policy nằm trên đường nóng của một dịch vụ xử lý lượng lớn request nhưng chưa có benchmark.

Không có một câu trả lời duy nhất cho mọi trường hợp. Một lựa chọn tốt cần nêu rõ **giả định, rủi ro và bằng chứng còn thiếu**.

### Nhiệm vụ D — Bổ sung một rule mới

Yêu cầu mới: người tham gia có trạng thái `SUSPENDED` không được đăng ký, với lý do `PARTICIPANT_SUSPENDED`.

Hãy:

1. Thêm trường hoặc thông tin phù hợp vào snapshot.
2. Xác định rule này đứng trước hay sau `REGISTRATION_CLOSED`.
3. Cập nhật cả hai implementation.
4. Bổ sung test cho trường hợp chỉ bị suspended.
5. Bổ sung test khi vừa suspended vừa workshop đã đóng để bảo vệ ưu tiên.
6. Kiểm tra những nơi tạo `RegistrationFacts` có cần cập nhật không.

Đừng tự chọn thứ tự nếu yêu cầu chưa xác định. Hãy nêu câu hỏi cần người sở hữu nghiệp vụ trả lời.

### Nhiệm vụ E — Review ranh giới thực thi

Giả sử service gọi `policy.evaluate(facts)` rồi gọi `registrationRepository.insert(...)`. Hai request đồng thời có thể dùng cùng snapshot. Hãy mô tả:

- Bất biến nào có thể bị phá?
- Kiểm tra nào phải diễn ra trong transaction?
- Ràng buộc dữ liệu nào có thể giúp chặn đăng ký trùng?
- Test nào cần chạy ngoài unit test của policy?

## 10. Rubric chấm bài: đánh giá có bằng chứng

Tổng điểm đề xuất là **20 điểm**. Đây là rubric dùng để tự đánh giá hoặc review cùng đồng đội, không phải thước đo tuyệt đối cho mọi hệ thống.

| Tiêu chí | Điểm tối đa | Bằng chứng cần có |
| --- | ---: | --- |
| **Đúng hợp đồng** | 5 | Đối chiếu đầy đủ các rule, null, thời điểm đóng và thứ tự ưu tiên |
| **Chất lượng test** | 4 | Có expected result độc lập, giá trị biên, invalid state và trường hợp nhiều điều kiện cùng khớp |
| **Readability** | 3 | Giải thích được luồng điều khiển, tên và mức độ gián tiếp |
| **Maintainability** | 3 | Đánh giá chi phí thêm/sửa rule, phạm vi ảnh hưởng và khả năng kiểm soát thứ tự |
| **Reliability và ranh giới** | 3 | Nhận ra snapshot/concurrency và giới hạn của policy thuần |
| **Lập luận lựa chọn** | 2 | Nêu bối cảnh, đánh đổi và điều kiện khiến lựa chọn thay đổi |

### 10.1. Cách hiểu mức điểm

- **0 điểm:** Không có bằng chứng hoặc kết luận trái với yêu cầu.
- **Khoảng một nửa điểm:** Nhận ra vấn đề nhưng giải thích chung chung, thiếu test hoặc bối cảnh.
- **Đạt tối đa:** Lập luận cụ thể, kiểm tra được, phân biệt điều đã biết với giả định và nêu giới hạn.

Một bài chọn A có thể đạt điểm tối đa; bài chọn B cũng vậy nếu lập luận phù hợp bối cảnh. **Không chấm theo việc người học chọn phương án giống đáp án tham khảo**, mà chấm theo chất lượng phân tích.

## 11. Gợi ý đáp án và lập luận tham khảo

Phần này giúp đối chiếu sau khi bạn đã tự làm. Nó không phải đáp án duy nhất; nếu bối cảnh bổ sung khác đi, kết luận có thể thay đổi.

### 11.1. Hai implementation có tương đương không?

Theo hợp đồng đã cho, cả A và B:

- Từ chối snapshot null và trường bắt buộc thiếu.
- Phân biệt số chỗ âm với số chỗ bằng 0.
- Đóng đăng ký tại đúng thời điểm `now == registrationClosesAt`.
- Ưu tiên trạng thái đóng trước hết chỗ.
- Ưu tiên hết chỗ trước đã đăng ký.
- Cho phép nếu không có điều kiện từ chối.

B có một phụ thuộc quan trọng: rule đầu tiên phải bắt dữ liệu không hợp lệ trước khi predicate sau truy cập trường. Cả hai đều dựa vào helper `hasRequiredInput`, nên cùng quy tắc kiểm tra input.

Kết luận này dựa trên **đọc code và contract tests đã mô tả**, không có nghĩa hai cách sẽ tương đương với mọi thay đổi trong tương lai. Khi thêm rule, phải cập nhật test và kiểm tra lại thứ tự.

### 11.2. Lựa chọn mặc định cho bối cảnh hiện tại

Với sáu rule cố định, chỉ được thay đổi bởi nhóm sở hữu module, cách A thường có lợi thế:

- Luồng từ chối nhìn thấy trực tiếp.
- Thứ tự ưu tiên rõ mà không cần hiểu một cơ chế rule riêng.
- Ít khái niệm hơn.
- Dễ đặt breakpoint và debug.
- Không cần tạo abstraction chỉ để chứa vài predicate.

Cách B không sai. Nó có thể đáng dùng nếu danh sách rule thật sự là một cấu trúc cần mở rộng, cấu hình hoặc kết hợp theo một hợp đồng rõ ràng. Khi ấy cần tài liệu về thứ tự, kiểm tra cấu hình và test riêng cho pipeline.

### 11.3. Những nhận xét review có thể chấp nhận

**Với A:**

> “Các guard clause đang đi theo thứ tự ưu tiên đã nêu trong yêu cầu, nên reviewer có thể đọc trực tiếp luồng từ chối. Nếu danh sách rule vẫn nhỏ và cố định, cấu trúc này dễ hiểu. Khi thêm rule mới, nhớ bổ sung test cho trường hợp nó cùng khớp với rule khác để bảo vệ thứ tự.”

> “Phương thức hiện chỉ đánh giá snapshot, nên không bảo đảm giữ chỗ khi nhiều request đồng thời. Service cần thực hiện cập nhật có điều kiện trong transaction và kiểm tra số hàng bị tác động.”

**Với B:**

> “Danh sách `RULES` làm cho việc thêm rule có cấu trúc, nhưng thứ tự phần tử quyết định lý do trả về. Nên giữ contract test cho các cặp điều kiện cùng khớp và ghi rõ nguyên tắc first-match-wins.”

> “Các predicate sau phụ thuộc rule đầu đã loại `null` và trường thiếu. Hãy giữ helper kiểm tra đầu vào ở đầu pipeline và bảo đảm predicate thuần, không có tác dụng phụ.”

### 11.4. Những nhận xét review chưa đủ căn cứ

- “B tốt hơn vì dùng functional programming.” Đây là sở thích về kỹ thuật, chưa chứng minh lợi ích.
- “A không maintainable vì có nhiều `if`.” Sáu guard clause có thể rất dễ hiểu.
- “B chắc chắn chậm hơn.” Chưa có benchmark hoặc bằng chứng tác động.
- “A an toàn hơn khi concurrency.” Cả hai chỉ đánh giá snapshot; cả hai đều cần ranh giới giữ chỗ nguyên tử.
- “Test parity xanh nên không có bug.” Hai implementation có thể cùng sai; cần expected result độc lập.
- “Nên dùng rule list vì sau này có thể cần plugin.” Khả năng tương lai chưa có bằng chứng; cần cân nhắc chi phí abstraction ngay bây giờ.

## 12. Những điều cần xem lại khi yêu cầu thay đổi

Một cách triển khai phù hợp hôm nay không phải cam kết vĩnh viễn. Khi yêu cầu thay đổi, hãy đánh giá lại cả hai phương án.

| Thay đổi yêu cầu | Điều cần xem lại |
| --- | --- |
| Thêm rule `SUSPENDED` | Vị trí ưu tiên, snapshot, cả hai policy và test xung đột |
| Trả nhiều lý do từ chối | Short-circuit có còn phù hợp không? |
| Rule theo từng loại workshop | Cấu hình/version và cách kiểm soát rule |
| Rule do module khác sở hữu | Hợp đồng plugin, dependency và quyền đăng ký |
| Tăng số rule lên hàng chục | Khả năng nhóm rule, đặt tên, quan sát và test |
| Yêu cầu audit lý do từ chối | Mã reason ổn định, log có kiểm soát dữ liệu |
| Dữ liệu snapshot lấy từ nhiều nguồn | Tính nhất quán và thời điểm chụp snapshot |
| Giữ chỗ đồng thời | Transaction, conditional update, unique constraint và retry |
| Thay múi giờ hoặc lịch workshop | Time source, timezone và quy tắc mốc đóng |
| Cần đánh giá hiệu năng | Benchmark đại diện và profiling toàn luồng |

### 12.1. Không để policy tự đọc đồng hồ hệ thống

Cả hai implementation nhận `now` qua `RegistrationFacts`. Đây là chủ ý: kết quả không phụ thuộc thời điểm máy chạy test.

Nếu policy tự gọi `Instant.now()` ở bên trong, hai lần đánh giá cùng input có thể cho kết quả khác nhau khi đi qua thời điểm đóng. Việc truyền thời gian vào giúp test xác định chính xác trường hợp biên và giúp caller kiểm soát nguồn thời gian.

Nếu hệ thống có yêu cầu timezone nghiệp vụ, cần xác định thời điểm đóng được lưu dưới dạng instant hay local date/time kèm zone. Bài tập dùng `Instant` để tránh mơ hồ về múi giờ trong ví dụ.

### 12.2. Không log toàn bộ snapshot một cách tùy tiện

Snapshot có ID người tham gia và workshop. Nếu cần ghi nhận lý do từ chối, hãy dùng dữ liệu tối thiểu cần thiết, chính sách retention và quyền truy cập phù hợp. Không đưa thông tin cá nhân hoặc dữ liệu nhạy cảm vào log chỉ để debug thuận tiện.

## 13. Checklist review khi đánh giá hai cách triển khai

Khi so sánh hai phương án cùng một yêu cầu, hãy lần lượt hỏi:

1. **Yêu cầu có rõ và có thể kiểm tra không?** Các điều kiện và kết quả đã được định nghĩa?
2. **Cả hai có cùng input/output contract không?** Kiểu dữ liệu, null, lỗi và lý do từ chối?
3. **Giá trị biên có được định nghĩa không?** Trước, đúng và sau deadline?
4. **Thứ tự ưu tiên có phải hợp đồng không?** Có ca nhiều điều kiện cùng khớp?
5. **Hai implementation có cùng kết quả mong đợi không?** Test có expected value độc lập?
6. **Có giả định ẩn nào không?** Null safety, timezone, snapshot freshness, side effects?
7. **Luồng điều khiển có dễ theo dõi không?** Người mới có tìm được lý do kết quả?
8. **Abstraction có mang lại lợi ích hiện tại không?** Có giảm lặp hoặc tạo extension point thực sự?
9. **Thêm rule mới sẽ thay đổi những gì?** Code, cấu hình, thứ tự và test?
10. **Có hành vi không thuần không?** Predicate có đọc clock, ghi dữ liệu hoặc gọi dịch vụ?
11. **Hiệu năng có phải ràng buộc đã xác nhận không?** Có số đo đại diện?
12. **Ranh giới thực thi có bảo vệ bất biến không?** Policy có bị nhầm với thao tác reservation?
13. **Bằng chứng kiểm thử có đúng phạm vi không?** Unit test, integration, concurrency và contract?
14. **Lựa chọn có phù hợp năng lực nhóm và cách vận hành không?** Có thể debug, theo dõi và thay đổi?
15. **Điều gì khiến ta cần đánh giá lại lựa chọn?** Trigger và điều kiện xem lại đã rõ?

## 14. Bài tập mở rộng

### Bài tập 1 — Đổi thứ tự ưu tiên

Sản phẩm yêu cầu nếu người tham gia đã đăng ký thì luôn trả `ALREADY_REGISTERED`, kể cả workshop đã đóng hoặc hết chỗ.

- Cập nhật thứ tự quy tắc.
- Thay đổi cả A và B.
- Viết ít nhất hai test xung đột.
- Giải thích tác động đến thông báo hiển thị cho người dùng.

### Bài tập 2 — Trả về nhiều lý do

Yêu cầu mới là trả danh sách tất cả lý do từ chối.

- Thiết kế kiểu kết quả phù hợp.
- Cân nhắc lỗi input có nên chặn các rule còn lại không.
- Sửa cả hai implementation theo cùng semantics.
- Test thứ tự và tính ổn định của danh sách lý do.

### Bài tập 3 — Rule theo chương trình

Mỗi chương trình workshop có thể bổ sung tối đa ba rule đã được code review và đăng ký sẵn.

- Đề xuất một interface có kiểu cho rule.
- Xác định ai sở hữu thứ tự và cách kiểm tra rule trùng.
- Đặt giới hạn cho việc cấu hình.
- Giải thích vì sao không nên cho cấu hình chứa mã Java tùy ý.

### Bài tập 4 — Dữ liệu không nhất quán

Một service đọc `remainingSeats` từ cache, còn `alreadyRegistered` từ database. Hai giá trị có thể thuộc hai thời điểm khác nhau.

- Rủi ro nào phát sinh?
- Có thể tạo snapshot nhất quán hơn bằng cách nào?
- Policy thuần có thể giải quyết phần nào và không thể giải quyết phần nào?
- Test tích hợp hoặc kiểm tra vận hành nào cần thêm?

### Bài tập 5 — Đánh giá hiệu năng

Một benchmark nhỏ cho thấy B chậm hơn A một lượng nhỏ, nhưng database lookup để tạo snapshot chiếm gần như toàn bộ thời gian request.

- Chênh lệch có ảnh hưởng SLA không?
- Cần benchmark ở cấp độ nào?
- Có đáng hy sinh readability để tối ưu không?
- Bằng chứng nào cần có trước khi thay đổi?

## Ghi nhớ

**Đánh giá hai cách triển khai cùng một yêu cầu phải bắt đầu từ hợp đồng và bằng chứng, rồi mới so sánh cấu trúc.** Hãy kiểm tra các rule, giá trị biên, thứ tự ưu tiên và đường lỗi bằng expected results độc lập. Sau đó mới cân nhắc readability, maintainability, reliability, testability và hiệu năng trong bối cảnh thực tế.

Với bộ rule nhỏ, cố định, các guard clause tuần tự thường dễ đọc và dễ review. Danh sách rule có thứ tự có thể phù hợp khi pipeline là một phần có chủ đích của thiết kế và thật sự cần mở rộng. **Không có phương án tốt nhất nếu thiếu bối cảnh**; lựa chọn tốt là lựa chọn đáp ứng hợp đồng với chi phí hiểu, kiểm thử và thay đổi hợp lý.

Cuối cùng, luôn phân biệt quyết định đủ điều kiện với thao tác ghi dữ liệu. Một policy thuần có thể trả kết quả chính xác cho snapshot nhưng không tự bảo đảm chỗ ngồi còn trống khi nhiều request cạnh tranh. Review tốt nhìn cả phần code đang so sánh lẫn ranh giới nơi hệ thống thực thi hành vi, để mã nguồn tiếp tục **đáng tin cậy, dễ hiểu và dễ thay đổi**.
