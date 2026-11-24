# Invariant property tests — Kiểm thử thuộc tính bất biến nghiệp vụ

## 1. Vì sao bất biến cần được kiểm thử như một thuộc tính?

Trong chương **Property Testing** của nội dung bảo mật logic nghiệp vụ, invariant property tests kiểm tra những điều phải luôn đúng trên các trạng thái nghiệp vụ quan sát được, sau nhiều đầu vào và nhiều chuỗi thao tác được sinh ra có chủ đích.

Ví dụ, hệ thống hoàn tiền phải bảo đảm tổng tiền hoàn được chấp nhận không vượt tiền đã thu. Một kiểm thử “thu 100.000, hoàn 30.000, còn 70.000” minh họa một trường hợp đúng. Một thuộc tính mạnh hơn là: với mọi chuỗi yêu cầu hoàn tiền nằm trong miền đã định nghĩa, sau mỗi lệnh hoàn tất, số tiền đã được sử dụng cho hoàn tiền vẫn nằm trong ngân sách, các bản ghi khớp với tổng và lệnh bị từ chối không tạo tác dụng phụ nghiệp vụ.

Những lỗi như gửi lặp, đổi tenant, dùng số âm, vượt hạn mức sau nhiều lần hoàn hoặc lợi dụng tràn số thường xuất hiện ở các tổ hợp mà người viết test ví dụ chưa nghĩ tới. Property-based testing giúp tìm phản ví dụ cho các quy tắc đã mô tả, nhưng hiệu quả phụ thuộc vào chất lượng của quy tắc, bộ sinh và cách quan sát kết quả.

Sau bài học, bạn có thể:

- Viết một bất biến đủ chính xác để chuyển thành assertion.
- Phân biệt bất biến trạng thái, điều kiện trước/sau lệnh và quan hệ giữa nhiều lần chạy.
- Sinh dữ liệu và chuỗi lệnh có cả trường hợp hợp lệ, không hợp lệ, lặp và sát biên.
- Kiểm tra bất biến sau từng bước, không chỉ tại cuối chuỗi.
- Dùng phản ví dụ thu nhỏ để tạo kiểm thử hồi quy dễ hiểu.
- Xác định phần nào cần được kiểm chứng thêm tại database, transaction và tích hợp bên ngoài.

## 2. Từ câu nghiệp vụ đến một phát biểu kiểm tra được

### 2.1. Các loại thuộc tính có liên quan

| Loại thuộc tính | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Bất biến trạng thái | Trạng thái hợp lệ phải luôn thỏa điều gì? | Tổng tiền hoàn không âm và không vượt tiền đã thu |
| Điều kiện trước | Khi nào lệnh đủ điều kiện được chấp nhận? | Người gọi được hoàn tiền trong tenant của giao dịch |
| Điều kiện sau | Nếu lệnh thành công hoặc thất bại, điều gì phải đúng? | Thành công tăng đúng số tiền; bị từ chối không thay dữ liệu nghiệp vụ |
| Quan hệ giữa các lần chạy | Thay đổi cách gọi có làm thay đổi kết quả ngoài quy tắc không? | Gửi lại cùng lệnh không hoàn thêm lần nữa |
| Thuộc tính chuỗi | Mỗi bước của nhiều lệnh có giữ các điều kiện không? | Nhiều lần hoàn riêng lẻ không cùng vượt ngân sách |

Không nên gọi mọi assertion là bất biến trạng thái. “Số tiền không thay đổi sau lệnh bị từ chối” là quan hệ giữa trạng thái trước và sau lệnh. Nó hỗ trợ bảo vệ bất biến nhưng cần hai snapshot để kiểm tra.

### 2.2. Dạng hình thức đơn giản

Gọi `S0` là trạng thái ban đầu hợp lệ, `c` là một lệnh và `step(S, c)` là kết quả thực thi. Với bất biến `I`, điều muốn kiểm tra là:

```text
I(S0)

Với mỗi lệnh c được thử:
    S' = trạng thái quan sát được sau khi lệnh hoàn tất
    I(S') vẫn đúng

Nếu c bị từ chối:
    businessSnapshot(S') == businessSnapshot(S)
```

Khi chạy trên hệ thống có transaction, “trạng thái quan sát được” thường là trạng thái đã commit sau một command. Không nhất thiết yêu cầu mọi câu SQL trung gian bên trong transaction phải biểu diễn một aggregate hoàn chỉnh đối với chính giao dịch đó. Cần chọn ranh giới quan sát đúng với bảo đảm của hệ thống.

Một lần chạy hữu hạn chỉ kiểm tra được những mẫu đã sinh. Property test không phải chứng minh hình thức cho mọi đầu vào và mọi lịch thực thi có thể tồn tại.

### 2.3. Tránh các phát biểu quá mơ hồ

| Phát biểu chưa đủ rõ | Phát biểu có thể kiểm tra |
| --- | --- |
| Hoàn tiền phải an toàn | Với mỗi giao dịch, tổng ngân sách đã sử dụng cho hoàn tiền nằm trong `[0, captured]` |
| Không được gửi trùng | Cùng tenant, đối tượng, người gọi, khóa và nội dung lệnh không tạo thêm một lần hoàn logic |
| Sai quyền thì không làm gì | Không đổi tổng, bản ghi hoàn, phiên bản hay tác dụng phụ nghiệp vụ của đối tượng |
| Phê duyệt đúng quy trình | Mỗi lần chuyển sang APPROVED phải có trạng thái nguồn và người duyệt thỏa chính sách |
| Giá không bị sửa | Sau bước chốt giá, các lệnh không được phép sửa giá giữ nguyên snapshot giá đáng tin cậy |

Các phát biểu phải dựa trên nghiệp vụ đã được thống nhất. Không suy ra “luôn đúng” chỉ từ hành vi hiện tại của mã nguồn, vì mã hiện tại có thể chính là thứ đang sai.

## 3. Mô hình xuyên suốt: ngân sách hoàn tiền

### 3.1. Giả định của ví dụ

Ta xét một giao dịch thanh toán trong một tenant, đã thu một số tiền dương `capturedVnd`. Mỗi yêu cầu hoàn tiền có người gọi, số tiền và idempotency key. Chính sách minh họa là:

- Chỉ người có năng lực hoàn tiền trong cùng tenant mới được thực hiện lệnh.
- Số tiền hoàn phải dương và không vượt phần ngân sách còn lại.
- Một khóa đã được chấp nhận chỉ phát lại kết quả cho cùng người gọi và cùng số tiền.
- Dùng lại khóa cho một lệnh khác tạo xung đột, không tạo thêm lần hoàn.
- Yêu cầu bị từ chối không làm thay đổi dữ liệu nghiệp vụ.

Trong mô hình thuần ở bài học, `refundedVnd` là **ngân sách đã được chiếm bởi các lần hoàn được chấp nhận**. Nó không khẳng định cổng thanh toán đã chuyển tiền xong. Nếu hệ thống thực tế có `PENDING` và `SETTLED`, thường cần tính cả phần đã giữ cho yêu cầu đang xử lý để tránh nhận quá nhiều lệnh hoàn đồng thời. Quy tắc giải phóng ngân sách khi thất bại phải được mô tả và kiểm thử riêng.

Tiền trong ví dụ dùng `long` theo đơn vị VND nguyên. Với hệ thống hỗ trợ nhiều loại tiền hoặc đơn vị lẻ, cần thêm currency, scale và quy tắc làm tròn vào model và bộ sinh; không cộng trực tiếp các giá trị khác loại tiền.

### 3.2. Danh sách thuộc tính

Gọi `C` là số tiền đã thu, `R` là ngân sách hoàn đã sử dụng và `receipts` là tập bản ghi hoàn được chấp nhận theo khóa.

| ID | Thuộc tính | Assertion chính |
| --- | --- | --- |
| INV-01 | Không chi quá ngân sách | `0 <= R <= C` |
| INV-02 | Tổng và chi tiết khớp nhau | `R == sum(receipts.amount)` |
| INV-03 | Mỗi lần hoàn được chấp nhận có số tiền dương | Mọi receipt có `amount > 0` |
| POST-01 | Một lệnh mới thành công có đúng một tác dụng logic | Thêm một receipt và tăng `R` đúng số tiền |
| POST-02 | Lệnh không được chấp nhận không đổi dữ liệu nghiệp vụ | Snapshot trước và sau bằng nhau |
| AUTH-01 | Khác tenant hoặc thiếu năng lực không được thực hiện | Kết quả DENIED; snapshot giữ nguyên |
| IDEM-01 | Phát lại cùng lệnh không chi thêm ngân sách | Kết quả REPLAYED; snapshot giữ nguyên |
| POS-01 | Lệnh mới hợp lệ thực sự được chấp nhận | Kết quả ACCEPTED và dữ liệu đúng |

POS-01 rất cần thiết. Một hệ thống từ chối mọi yêu cầu vẫn có thể thỏa `0 <= R <= C`, không có receipt âm và không có hoàn trùng. Đó là ví dụ một thuộc tính an toàn đúng nhưng bộ kiểm thử chưa đủ để xác nhận chức năng.

Không coi “số bản ghi không tăng” là toàn bộ bằng chứng không có tác dụng phụ. Trong hệ thống thật còn cần xem phiên bản, ledger, outbox, idempotency store và lệnh gửi tới dịch vụ bên ngoài. Phạm vi snapshot phải được định nghĩa cụ thể.

## 4. Thiết kế bộ sinh theo rủi ro nghiệp vụ

### 4.1. Sinh có chủ đích thay vì ngẫu nhiên thuần túy

| Nhóm dữ liệu | Mẫu cần có | Lỗi nhắm tới |
| --- | --- | --- |
| Tiền đã thu | 1, giá trị thông thường, giá trị lớn được miền hỗ trợ | Sai biên và tràn số |
| Tiền hoàn | -1, 0, 1, đúng phần còn lại, lớn hơn phần còn lại một đơn vị | Chấp nhận số âm, sai toán tử so sánh |
| Danh tính | Người hợp lệ, người khác cùng tenant, người tenant khác, người thiếu năng lực | Nhầm quyền và nhầm phạm vi |
| Khóa | Khóa mới, khóa lặp, cùng khóa khác người hoặc số tiền | Ghi nhận trùng, phát lại sai chủ thể |
| Chuỗi | Rỗng, một lệnh, nhiều lệnh, thành công xen từ chối | Chỉ kiểm tra từng lệnh độc lập |
| Trạng thái nền | Chưa hoàn, đã hoàn một phần, hết ngân sách | Kiểm tra nhầm tổng ban đầu thay vì phần còn lại |

Lựa chọn chuỗi rỗng có ích để kiểm tra trạng thái khởi tạo. Tuy nhiên, nếu phần lớn mẫu đều rỗng hoặc bị từ chối ngay, các nhánh thay đổi dữ liệu sẽ ít được kiểm tra.

### 4.2. Sinh các giá trị phụ thuộc nhau

Để kiểm tra “lệnh hợp lệ được chấp nhận”, cần sinh `amount` trong `[1, captured]`. Nếu sinh hai số độc lập rồi loại gần hết mẫu bằng điều kiện, thời gian kiểm thử có thể chủ yếu dành cho việc loại mẫu.

Để kiểm tra vượt ngân sách sau một lần hoàn, có thể dựng theo cấu trúc:

```text
captured >= 2
first nằm trong [1, captured - 1]
remaining = captured - first
second = remaining + 1

refund(first, key-1)  -> phải thành công
refund(second, key-2) -> phải bị từ chối và không đổi dữ liệu
```

Cần bảo đảm các phép tính trong chính generator không tràn số. Nếu miền sát giới hạn kiểu số, dùng số học chính xác hoặc xây dựng dữ liệu từ những thành phần đã giới hạn rõ ràng.

### 4.3. Sinh cả lệnh hợp lệ lẫn hành vi lạm dụng

Một generator chỉ sinh chuỗi hợp lệ có thể kiểm tra chức năng, nhưng bỏ qua hành vi cố ý sai quyền, sai trạng thái và lặp yêu cầu. Ngược lại, generator chỉ sinh dữ liệu vô hiệu thường không đưa hệ thống tới các trạng thái nhạy cảm.

Nên kết hợp hai nhóm: các thuộc tính có tiền đề được dựng chắc chắn để kiểm tra một quy tắc, và các chuỗi hỗn hợp để tìm tương tác giữa nhiều quy tắc. Không lọc bỏ toàn bộ lệnh sai quyền bằng precondition của bộ sinh, rồi kết luận hệ thống chặn được sai quyền.

## 5. Ví dụ Java: aggregate thuần để kiểm thử

Ví dụ sau dùng Java 17+. Nó là một mô hình thực thi tuần tự trong bộ nhớ, phục vụ việc viết property test. Nó không thay thế transaction, ràng buộc database, xác thực người dùng hay tích hợp cổng thanh toán.

`Actor` biểu diễn ngữ cảnh quyền đã được máy chủ xác minh; `canRefund` không phải một trường người gọi được tự gửi lên để cấp quyền. Ví dụ giả định các định danh của model hợp lệ và không null.

Mã minh họa cho `RefundLedger.java`:

```java
package example.security;

import java.util.HashMap;
import java.util.Map;

public final class RefundLedger {
    public record Actor(String userId, String tenantId, boolean canRefund) {}
    public record Receipt(String actorId, long amountVnd) {}
    public record Snapshot(
            long capturedVnd,
            long refundedVnd,
            Map<String, Receipt> receipts) {}

    public enum Result {
        ACCEPTED, REPLAYED, DENIED, INVALID, CONFLICT, EXCEEDS_CAPTURE
    }

    private final String tenantId;
    private final long capturedVnd;
    private long refundedVnd;
    private final Map<String, Receipt> receipts = new HashMap<>();

    public RefundLedger(String tenantId, long capturedVnd) {
        if (capturedVnd <= 0) {
            throw new IllegalArgumentException("capturedVnd must be positive");
        }
        this.tenantId = tenantId;
        this.capturedVnd = capturedVnd;
    }

    public Result refund(Actor actor, String key, long amountVnd) {
        if (actor == null
                || !tenantId.equals(actor.tenantId())
                || !actor.canRefund()) {
            return Result.DENIED;
        }
        if (key == null || key.isBlank() || amountVnd <= 0) {
            return Result.INVALID;
        }

        Receipt previous = receipts.get(key);
        if (previous != null) {
            return previous.actorId().equals(actor.userId())
                    && previous.amountVnd() == amountVnd
                ? Result.REPLAYED
                : Result.CONFLICT;
        }

        long remainingVnd = capturedVnd - refundedVnd;
        if (amountVnd > remainingVnd) {
            return Result.EXCEEDS_CAPTURE;
        }

        long nextRefundedVnd = Math.addExact(refundedVnd, amountVnd);
        receipts.put(key, new Receipt(actor.userId(), amountVnd));
        refundedVnd = nextRefundedVnd;
        return Result.ACCEPTED;
    }

    public Snapshot snapshot() {
        return new Snapshot(
            capturedVnd, refundedVnd, Map.copyOf(receipts)
        );
    }
}
```

Aggregate chỉ chứa một giao dịch thanh toán; vì vậy map khóa nằm trong phạm vi đối tượng này. Một idempotency store dùng chung cho toàn hệ thống phải có thiết kế phạm vi tenant, operation, đối tượng và chủ thể phù hợp. Không sao chép nguyên map một chiều này thành bảng toàn cục rồi giả định phạm vi vẫn đúng.

Kiểm tra quyền nằm trước nhánh đọc lại kết quả. Một người khác tenant không được lấy kết quả đã lưu chỉ vì đoán đúng key. Trong mô hình này, người cùng tenant có năng lực hoàn nhưng dùng lại key của người khác nhận `CONFLICT`, không nhận nội dung receipt của người đó.

Phép so sánh với `capturedVnd - refundedVnd` tránh cách kiểm tra có nguy cơ tràn số như `refundedVnd + amountVnd > capturedVnd`. `Math.addExact` vẫn làm rõ rằng cập nhật không chấp nhận tràn số; nó không thay thế điều kiện ngân sách.

## 6. Property test bằng jqwik

jqwik cung cấp `@Property`, tham số `@ForAll` và các provider `@Provide` để sinh đầu vào cho nhiều lượt kiểm tra. Khi tìm thấy mẫu làm thuộc tính sai, công cụ có thể thử thu nhỏ mẫu đó. Cách khai báo được mô tả trong [jqwik User Guide — Writing Properties](https://jqwik.net/docs/current/user-guide.html#writing-properties).

Dự án cần có dependency test `net.jqwik:jqwik` ở phiên bản tương thích với môi trường và cấu hình chạy JUnit Platform. Các property của jqwik được chạy bởi engine của jqwik; không giả định lifecycle annotation của JUnit Jupiter điều khiển những lượt sinh này. Đoạn mã dưới đây tạo ledger mới ngay trong mỗi lần gọi property và dùng `AssertionError` trực tiếp, không cần thêm thư viện assertion.

Mã minh họa cho `RefundInvariantProperties.java`, cùng package với aggregate:

```java
package example.security;

import static example.security.RefundLedger.*;

import java.math.BigInteger;
import java.util.List;

import net.jqwik.api.Arbitraries;
import net.jqwik.api.Arbitrary;
import net.jqwik.api.Combinators;
import net.jqwik.api.Example;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import net.jqwik.api.Provide;

class RefundInvariantProperties {
    private static final Actor ALICE =
        new Actor("alice", "tenant-a", true);

    record Attempt(Actor actor, String key, long amountVnd) {}
    record ValidRefund(long capturedVnd, long amountVnd) {}

    @Provide
    Arbitrary<Long> capturedAmounts() {
        return Arbitraries.longs().between(1L, 1_000_000L);
    }

    @Provide
    Arbitrary<List<Attempt>> attempts() {
        Arbitrary<Actor> actors = Arbitraries.of(
            ALICE,
            new Actor("bob", "tenant-a", true),
            new Actor("eve", "tenant-b", true),
            new Actor("auditor", "tenant-a", false)
        );
        Arbitrary<String> keys = Arbitraries.of("k0", "k1", "k2", "k3");
        Arbitrary<Long> amounts = Arbitraries.oneOf(
            Arbitraries.of(-1L, 0L, 1L, 999_999L,
                           1_000_000L, 1_000_001L, Long.MAX_VALUE),
            Arbitraries.longs().between(-2L, 1_000_001L)
        );

        return Combinators.combine(actors, keys, amounts)
            .as(Attempt::new)
            .list().ofMinSize(0).ofMaxSize(40);
    }

    @Provide
    Arbitrary<ValidRefund> validRefunds() {
        return capturedAmounts().flatMap(captured ->
            Arbitraries.longs().between(1L, captured)
                .map(amount -> new ValidRefund(captured, amount))
        );
    }

    @Provide
    Arbitrary<Actor> forbiddenActors() {
        return Arbitraries.of(
            new Actor("eve", "tenant-b", true),
            new Actor("auditor", "tenant-a", false)
        );
    }

    @Property(tries = 500)
    void invariantsHoldAfterEveryAttempt(
            @ForAll("capturedAmounts") long captured,
            @ForAll("attempts") List<Attempt> attempts) {
        RefundLedger ledger = new RefundLedger("tenant-a", captured);
        assertInvariants(ledger.snapshot());

        for (int i = 0; i < attempts.size(); i++) {
            Attempt command = attempts.get(i);
            Snapshot before = ledger.snapshot();
            Result result = ledger.refund(
                command.actor(), command.key(), command.amountVnd()
            );
            Snapshot after = ledger.snapshot();
            String context = "step=" + i + ", command=" + command;

            assertInvariants(after);
            if (result == Result.ACCEPTED) {
                check(command.actor().tenantId().equals("tenant-a")
                        && command.actor().canRefund(), context);
                check(!before.receipts().containsKey(command.key()), context);
                check(after.receipts().size() == before.receipts().size() + 1,
                      context);
                check(after.receipts().get(command.key()).equals(
                    new Receipt(command.actor().userId(), command.amountVnd())
                ), context);

                BigInteger delta = BigInteger.valueOf(after.refundedVnd())
                    .subtract(BigInteger.valueOf(before.refundedVnd()));
                check(delta.equals(BigInteger.valueOf(command.amountVnd())),
                      context);
            } else {
                check(before.equals(after), context + ", result=" + result);
            }
        }
    }

    @Property(tries = 300)
    void validRefundIsAcceptedAndRetryHasNoExtraEffect(
            @ForAll("validRefunds") ValidRefund sample) {
        RefundLedger ledger = new RefundLedger("tenant-a", sample.capturedVnd());

        check(ledger.refund(ALICE, "same-key", sample.amountVnd())
                == Result.ACCEPTED, "valid refund must be accepted");
        Snapshot once = ledger.snapshot();
        check(once.refundedVnd() == sample.amountVnd(), "wrong accepted amount");
        check(once.receipts().size() == 1, "one logical refund expected");
        assertInvariants(once);

        check(ledger.refund(ALICE, "same-key", sample.amountVnd())
                == Result.REPLAYED, "same command must be replayed");
        check(once.equals(ledger.snapshot()), "retry changed business data");
    }

    @Property(tries = 200)
    void forbiddenActorCannotReplayAnAcceptedCommand(
            @ForAll("validRefunds") ValidRefund sample,
            @ForAll("forbiddenActors") Actor forbidden) {
        RefundLedger ledger = new RefundLedger("tenant-a", sample.capturedVnd());
        check(ledger.refund(ALICE, "cached-key", sample.amountVnd())
                == Result.ACCEPTED, "setup must succeed");
        Snapshot before = ledger.snapshot();

        check(ledger.refund(forbidden, "cached-key", sample.amountVnd())
                == Result.DENIED, "authorization must precede replay");
        check(before.equals(ledger.snapshot()), "denied command mutated state");
    }

    @Property(tries = 200)
    void changedPayloadCannotReuseAnAcceptedKey(
            @ForAll("validRefunds") ValidRefund sample) {
        RefundLedger ledger = new RefundLedger("tenant-a", sample.capturedVnd());
        check(ledger.refund(ALICE, "payload-key", sample.amountVnd())
                == Result.ACCEPTED, "setup must succeed");
        Snapshot before = ledger.snapshot();

        // The generator bounds amount to 1_000_000, so +1 cannot overflow.
        check(ledger.refund(ALICE, "payload-key", sample.amountVnd() + 1)
                == Result.CONFLICT, "changed command must conflict");
        check(before.equals(ledger.snapshot()), "conflict mutated state");
    }

    @Example
    void aSecondRefundMustNotWrapAroundLong() {
        RefundLedger ledger = new RefundLedger("tenant-a", Long.MAX_VALUE);
        check(ledger.refund(ALICE, "large", Long.MAX_VALUE - 1)
                == Result.ACCEPTED, "setup must succeed");
        Snapshot before = ledger.snapshot();

        check(ledger.refund(ALICE, "extra", 2L)
                == Result.EXCEEDS_CAPTURE, "overflow must not bypass budget");
        check(before.equals(ledger.snapshot()), "overflow attempt mutated state");
        assertInvariants(ledger.snapshot());
    }

    private static void assertInvariants(Snapshot snapshot) {
        check(snapshot.capturedVnd() > 0, "invalid captured amount");
        check(snapshot.refundedVnd() >= 0, "negative refunded amount");
        check(snapshot.refundedVnd() <= snapshot.capturedVnd(), "over-refund");

        BigInteger sum = BigInteger.ZERO;
        for (Receipt receipt : snapshot.receipts().values()) {
            check(receipt.amountVnd() > 0, "non-positive receipt");
            sum = sum.add(BigInteger.valueOf(receipt.amountVnd()));
        }
        check(sum.equals(BigInteger.valueOf(snapshot.refundedVnd())),
              "receipts and total disagree");
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

### 6.1. Vì sao ví dụ có cả property và example?

Các property duyệt nhiều đầu vào, còn `@Example` khóa một trường hợp biên đã biết. Không cần trông chờ việc sinh ngẫu nhiên sẽ luôn gặp đúng tổ hợp `Long.MAX_VALUE - 1` rồi cộng thêm 2. Kiểm thử ví dụ và kiểm thử thuộc tính bổ sung cho nhau.

Giới hạn tiền ở các generator thông thường giữ cho mẫu dễ đọc; nó cũng giới hạn điều mà những property đó đã kiểm tra. Nếu miền thực tế hỗ trợ giá trị lớn hơn, cần các nhóm generator tương ứng, không suy ra toàn bộ miền `long` đã được kiểm tra chỉ vì có một ví dụ sát biên.

### 6.2. Vì sao dùng BigInteger trong assertion?

Nếu test cộng các receipt bằng cùng kiểu số và cùng cách tính dễ tràn như production, cả hai có thể sai giống nhau. `BigInteger` giúp tính tổng và độ tăng mà không bị wrap-around, tạo một oracle số học độc lập hơn.

Tuy nhiên, snapshot vẫn lấy từ implementation đang kiểm tra. Nếu implementation đồng thời sửa sai cả tổng lẫn receipt nhưng giữ chúng khớp nhau, INV-02 có thể vẫn pass. Các postcondition về lệnh được chấp nhận, số tiền cụ thể, quyền và snapshot trước/sau giúp phát hiện thêm nhóm sai lệch đó. Với nghiệp vụ lớn hơn, có thể cần một reference model độc lập.

### 6.3. Tại sao số lượng key lại nhỏ?

Bốn key làm việc trùng key xuất hiện thường xuyên trong chuỗi, tạo cơ hội kiểm tra replay và conflict. Nếu sinh UUID mới cho mọi lệnh thì các property về yêu cầu trùng có thể gần như không được chạm tới.

Đây không phải quy tắc dùng ít key trong production. Bộ sinh được thiết kế để làm các tương tác rủi ro xuất hiện với tần suất có ích cho test.

Các provider chưa sinh `null`, key trắng hoặc định danh sai cấu trúc. Đó là những nhóm validation cần bổ sung thuộc tính riêng; không mô tả bộ test minh họa là bao phủ toàn bộ đầu vào của một API.

## 7. Kiểm tra sau mỗi bước và quan sát độ phủ

### 7.1. Một bất biến cuối chuỗi có thể che lỗi giữa chuỗi

Giả sử một implementation lỗi cho phép số tiền tạm thời vượt ngân sách, rồi một thao tác điều chỉnh sau đó đưa số tiền về mức hợp lệ. Nếu test chỉ nhìn trạng thái cuối, nó bỏ qua trạng thái sai đã từng được commit và có thể đã kích hoạt tác dụng phụ.

Vì vậy, vòng lặp trong ví dụ kiểm tra INV-01, INV-02 và INV-03 sau từng command. Khi thất bại, thông tin về bước và command giúp xác định đoạn tiền tố đã đưa hệ thống tới trạng thái sai. Với assertion phức tạp hơn, nên đưa ID property, bước, snapshot trước/sau và kết quả lệnh vào thông báo chẩn đoán.

Snapshot phải là bản chụp ổn định. Nếu `before` trỏ vào cùng map mutable mà command sẽ sửa, so sánh trước/sau có thể không còn ý nghĩa. Ví dụ dùng `Map.copyOf` và receipt bất biến để tránh aliasing dữ liệu kiểm tra.

### 7.2. Tránh thuộc tính đúng vì chưa từng đi tới tình huống cần kiểm tra

Xét thuộc tính:

```text
Nếu yêu cầu ở trạng thái APPROVED thì approvedBy khác requesterId.
```

Nếu generator không bao giờ sinh được một lần duyệt thành công, thuộc tính trên có thể luôn đúng mà chưa hề kiểm tra sự phân tách người tạo và người duyệt. Đây là trường hợp tiền đề không xuất hiện, thường gọi là vacuous pass.

Biện pháp thực tế:

- Có generator dựng chắc chắn trạng thái tiền đề, chẳng hạn tạo → gửi duyệt → duyệt bằng người hợp lệ.
- Có property khẳng định lệnh hợp lệ phải thành công, không chỉ kiểm tra dữ liệu không bị phá.
- Theo dõi các nhóm kết quả như ACCEPTED, REPLAYED, DENIED, CONFLICT và EXCEEDS_CAPTURE.
- Kiểm tra các nhóm dữ liệu quan trọng có xuất hiện: hết ngân sách, khác tenant, key lặp, đúng biên.

Thống kê là tín hiệu về mẫu đã chạy, không tự thay thế assertion. Nếu muốn bảo đảm một tình huống được kiểm tra trong mọi lần chạy CI, dùng một property có cấu trúc dựng tình huống đó hoặc một ví dụ cố định thay vì chỉ mong tỉ lệ ngẫu nhiên đủ cao.

### 7.3. Không sao chép toàn bộ implementation làm oracle

Reference model nên nhỏ và biểu diễn đặc tả khác với implementation. Ví dụ, model có thể giữ tập lệnh hoàn đã chấp nhận và tính tổng bằng `BigInteger`, trong khi production dùng cột tổng cùng transaction và outbox.

Nếu model gọi cùng policy, cùng hàm tính tổng và cùng mapper với production, nhiều sai sót có thể được chia sẻ. Ngược lại, một model quá phức tạp và giống hệt hệ thống sẽ trở thành một implementation thứ hai khó tin cậy. Chọn abstraction đủ nhỏ để người đọc đối chiếu được với câu nghiệp vụ.

## 8. Shrinking và phản ví dụ có thể hành động được

### 8.1. Từ chuỗi dài đến một lỗi nghiệp vụ ngắn

Giả sử mã kiểm tra sai bằng điều kiện `amount <= captured` cho từng lệnh, bỏ qua tổng đã hoàn. Một phản ví dụ dễ hiểu là:

```text
captured = 100
refund(60, key-a) -> ACCEPTED
refund(60, key-b) -> ACCEPTED

refunded = 120 > captured
```

Sau quá trình thu nhỏ, một phản ví dụ có thể đơn giản hơn:

```text
captured = 1
refund(1, key-a) -> ACCEPTED
refund(1, key-b) -> ACCEPTED   // sai: ngân sách đã hết
```

Đây là hình dạng minh họa, không phải cam kết jqwik luôn trả đúng hai giá trị này hoặc tìm được mẫu nhỏ nhất toàn cục. Bộ sinh, cách đo độ nhỏ, điều kiện miền và thời gian thu nhỏ đều ảnh hưởng kết quả. Cơ chế được trình bày trong [jqwik User Guide — Result Shrinking](https://jqwik.net/docs/current/user-guide.html#result-shrinking).

### 8.2. Bảo toàn ý nghĩa khi thu nhỏ

Nếu các trường có quan hệ phụ thuộc, phải xây dựng generator sao cho mẫu sau khi thu nhỏ vẫn biểu diễn một tình huống có ý nghĩa. Chẳng hạn, một property khẳng định “hoàn đúng phần còn lại được phép” cần giữ `amount == remaining`, không chỉ tình cờ đúng ở mẫu gốc.

Với chuỗi có ID hoặc key tham chiếu lệnh trước, việc bỏ một bước có thể làm mất đối tượng được tham chiếu. Có thể dùng mô hình lệnh mang tính biểu tượng, hoặc generator có cấu trúc giữ mối quan hệ giữa bước tạo và bước dùng. Không nên bắt mọi lỗi tạo fixture rồi coi là lần chạy thành công; cách đó có thể làm mất chính phản ví dụ.

### 8.3. Quy trình xử lý một property thất bại

1. Lưu seed, mẫu đã thu nhỏ, property ID và revision của mã/generator.
2. Đọc phản ví dụ như một kịch bản nghiệp vụ, không chỉ như một stack trace.
3. Xác định lỗi thuộc implementation, phát biểu thuộc tính, generator hay môi trường quan sát.
4. Tạo kiểm thử ví dụ cố định từ phản ví dụ quan trọng.
5. Sửa nguyên nhân và giữ property để tiếp tục tìm những trường hợp chưa biết.

Có thể tạm gắn seed bằng `@Property(seed = "424242")` để điều tra. Việc tái tạo còn phụ thuộc mã generator, phiên bản công cụ và môi trường thực thi; seed không thay thế việc giữ lại một phản ví dụ cụ thể. Không giữ mãi chỉ một seed rồi coi bộ kiểm thử vẫn đang khám phá nhiều dữ liệu mới.

## 9. Áp dụng cho state machine và phân quyền theo đối tượng

Bất biến có thể kết hợp dữ liệu nghiệp vụ với quy trình duyệt và danh tính, thay vì chỉ kiểm tra các tổng số học.

| Bối cảnh | Bất biến hoặc quan hệ cần kiểm tra | Cách tạo tình huống quan trọng |
| --- | --- | --- |
| Phê duyệt | Người duyệt khác người tạo | Sinh người có nhiều vai trò và thử tự duyệt |
| Quy trình | APPROVED chỉ có được qua bước hợp lệ | Sinh lệnh duyệt trước khi gửi, gửi lại sau duyệt |
| Chốt giá | Giá đã chốt không đổi qua lệnh không được phép | Chèn trường giá/tổng tiền vào lệnh sửa sau bước chốt |
| Cách ly tenant | Lệnh tenant-B không làm đổi aggregate tenant-A | Dùng đối tượng thật thuộc tenant khác |
| Thu hồi quyền | Lệnh mới dùng quyền đúng theo hợp đồng độ mới | Thu hồi quyền đã commit rồi thực hiện lệnh tiếp theo |
| Sự kiện | Chỉ có sự kiện nghiệp vụ cho chuyển trạng thái được chấp nhận | Xen nhiều lệnh bị từ chối, replay và thành công |

Một generator stateful có thể chọn lệnh dựa trên trạng thái hiện tại. Đối với security test, cần giữ khả năng **thử** lệnh không hợp lệ và kiểm tra bị từ chối. Nếu chỉ định nghĩa precondition cho những lệnh hợp lệ rồi bỏ mọi lệnh ngoài precondition, bạn chưa kiểm tra được khả năng chặn thao tác bỏ qua bước.

Một số thuộc tính là phát biểu về lịch sử, không chỉ snapshot hiện tại. `approvedBy != requesterId` chưa chứng minh đối tượng từng đi qua SUBMITTED. Muốn kiểm tra nguồn chuyển trạng thái cần quan sát phiên bản trước/sau, lịch sử chuyển trạng thái đáng tin cậy hoặc model chuỗi lệnh.

Với thay đổi quyền trong thời gian thực, xác định rõ thời điểm hiệu lực. Thu hồi quyền đã commit trước khi một lệnh mới bắt đầu khác với thu hồi đang chạy đồng thời với lệnh đã bắt đầu. Property cần mô tả đúng bảo đảm của hệ thống, không tự giả định mọi thay đổi quyền đều có hiệu lực tức thời ở mọi nơi.

## 10. Từ aggregate thuần đến transaction và hệ thống thật

### 10.1. Property test tuần tự chưa chứng minh an toàn đồng thời

Lớp `RefundLedger` trong ví dụ không thread-safe. Các property tuần tự không chứng minh hai giao dịch thực tế cùng hoàn tiền sẽ giữ ngân sách.

Ví dụ có `captured = 100`, `refunded = 0`, hai lệnh độc lập đều muốn hoàn 80. Mỗi giao dịch có thể thấy ngân sách còn 100 trước khi bên kia commit. Nếu không bảo vệ thao tác đọc–kiểm tra–ghi, cả hai có thể được chấp nhận dù phép tính trong mỗi request riêng lẻ là đúng.

Để kiểm thử tại database:

1. Sinh trạng thái và các lệnh sao cho từng lệnh có thể hợp lệ khi chạy riêng nhưng tổng của chúng vượt phần còn lại.
2. Dùng hai transaction/kết nối riêng và cơ chế đồng bộ xác định để tạo tranh chấp.
3. Đợi các lệnh hoàn tất và commit hoặc rollback theo kết quả.
4. Đọc trạng thái đã commit từ một ngữ cảnh mới.
5. Kiểm tra tổng ngân sách, receipt, outbox và kết quả từng lệnh.

Không suy ra tác dụng ngoại vi từ riêng cột tổng. Nếu cập nhật tổng bị ghi đè khiến `refunded` vẫn là 80 nhưng có hai lệnh hoàn 80 gửi ra ngoài, INV-01 trên cột tổng có thể đúng còn nghiệp vụ đã sai. Đối chiếu tổng với các bản ghi và tác dụng phụ là thiết yếu.

Các kỹ thuật như khóa, optimistic version, conditional update hoặc cơ chế tuần tự hóa phù hợp cần được lựa chọn theo kiến trúc. Property test kiểm tra bảo đảm mong muốn của lựa chọn đó, không tự tạo ra tính nguyên tử.

### 10.2. Đọc trạng thái thật sau khi lệnh hoàn tất

Khi dùng ORM, không chỉ đọc lại entity được cache trong persistence context của test. Cần quan sát trạng thái đã commit bằng transaction/ngữ cảnh mới hoặc cách làm sạch cache thích hợp.

Fixture phải được tạo và commit ở nơi request có thể đọc thấy. Một test được bao trong transaction rollback không tự bảo đảm giao dịch HTTP khác nhìn thấy fixture hoặc mọi lỗi lúc commit đã được thực thi.

Các mẫu property cần được cô lập với nhau. Tạo aggregate mới mỗi lượt trong unit test là đơn giản; với database, có thể cần schema test, dữ liệu theo namespace hoặc cleanup có kiểm soát. Chọn cách không làm mất khả năng thu nhỏ và tái tạo mẫu lỗi.

### 10.3. Tác dụng phụ và lỗi giữa các bước

Nếu một lần hoàn thành công tạo ledger entry và outbox, các thay đổi cần nhất quán với transaction được thiết kế. Property về lỗi có thể dựng các điểm thất bại có kiểm soát:

| Điểm thất bại | Bảo đảm cần kiểm tra |
| --- | --- |
| Trước khi ghi | Không có dữ liệu nghiệp vụ mới |
| Sau ghi ledger nhưng trước commit | Rollback không để lại một phần thay đổi local |
| Sau commit nhưng trước phản hồi | Gửi lại lệnh không tạo lần hoàn logic thứ hai |
| Worker xử lý lại thông điệp | Không tạo thêm hiệu ứng tài chính ngoài quy tắc idempotency |
| Cổng thanh toán có timeout không rõ kết quả | Thực hiện quy trình đối soát/gửi lại theo hợp đồng, không mù quáng hoàn thêm |

Rollback database không thu hồi được một lệnh đã thực hiện ở cổng thanh toán. Vì vậy, cần kiểm tra cách điều phối và idempotency ở ranh giới đó, không chỉ assert không có bản ghi sau rollback.

Bất biến “không phát sinh thêm lần hoàn logic” cũng khác “thông điệp vật lý chỉ giao đúng một lần”. Hệ thống có cơ chế giao nhận phát lại cần kiểm tra việc khử trùng hoặc idempotency phía nhận.

## 11. Duy trì bộ thuộc tính có giá trị

### 11.1. Tách các thuộc tính để chẩn đoán được

Một property dài kiểm tra mọi điều có thể khó biết điều gì sai. Có thể chia thành nhóm số học, quyền, replay, xung đột và chuỗi hỗn hợp, trong khi dùng lại các helper assertion bất biến.

Không nên thay toàn bộ kiểm thử authorization matrix bằng generator ngẫu nhiên. Ma trận bảo đảm những tổ hợp quyền bắt buộc được kiểm tra rõ ràng; property test mở rộng phạm vi dữ liệu và thứ tự thao tác quanh các quy tắc đó.

### 11.2. Đánh giá khả năng phát hiện lỗi

Trong môi trường phát triển, dùng các thay đổi sai có chủ ý để đánh giá bộ test:

| Thay đổi sai | Thuộc tính cần phát hiện |
| --- | --- |
| Chỉ so số tiền mỗi lệnh với captured | INV-01 sau chuỗi nhiều lần hoàn |
| Không kiểm tra amount dương | INV-03 và bất biến không giảm tổng qua lệnh không hợp lệ |
| Cộng lại ngân sách khi replay | IDEM-01, INV-02 hoặc POST-01 |
| Bỏ kiểm tra tenant | AUTH-01 và assertion chủ thể khi ACCEPTED |
| Đọc cache trước phân quyền | Property về người bị cấm phát lại lệnh đã chấp nhận |
| Luôn trả DENIED | POS-01 |
| Dùng phép cộng dễ tràn để kiểm tra giới hạn | Ví dụ biên Long.MAX_VALUE và generator giá trị lớn |
| Chỉ cập nhật tổng, không thêm receipt | INV-02 và POST-01 |

Nếu một thay đổi sai không làm test thất bại, xem lại cả dữ liệu sinh và assertion. Tăng số lượt không sửa được một thuộc tính vốn không quan sát phần bị sai.

### 11.3. Chọn số lượt và giữ khả năng tái tạo

Unit property chạy trong bộ nhớ thường cho phép nhiều mẫu hơn test có database hay network. Chọn số lượt theo chi phí và rủi ro; `tries = 500` trong ví dụ chỉ là một ngân sách minh họa, không phải ngưỡng bảo đảm an toàn.

Giữ các ca biên và phản ví dụ hồi quy chạy ổn định. Dành phần sinh dữ liệu để khám phá thêm. Khi có lỗi, ghi nhận command sequence, seed, revision và phiên bản công cụ; không ghi token, cookie hoặc dữ liệu khách hàng thật vào log kiểm thử.

Nếu tính ngẫu nhiên đến từ thời gian, UUID, thứ tự xử lý hoặc dịch vụ bên ngoài, cân nhắc tiêm clock/nguồn ID/adapter có kiểm soát. Seed của generator không điều khiển được mọi nguồn không xác định trong hệ thống.

## 12. Những lỗi thường gặp

| Lỗi | Hậu quả | Điều chỉnh |
| --- | --- | --- |
| Viết thuộc tính “không ném exception” | Hành vi sai nhưng trả bình thường vẫn pass | Assert quyết định và trạng thái nghiệp vụ |
| Chỉ nhìn trạng thái cuối | Bỏ qua vi phạm đã xuất hiện giữa chuỗi | Kiểm tra sau mỗi command tại ranh giới quan sát |
| Chỉ sinh đầu vào vô hiệu | Hầu hết request bị chặn trước logic chính | Dựng chắc ca hợp lệ và chuỗi đi sâu vào quy trình |
| Lọc hết hành vi lạm dụng | Không kiểm tra được hàng rào bảo mật | Thử lệnh sai và assert bị từ chối đúng cách |
| Chỉ kiểm tra upper bound | Tổng có thể âm hoặc chi tiết không khớp | Kết hợp lower bound, tổng–chi tiết và postcondition |
| Dùng chung mutable fixture giữa lượt chạy | Lỗi phụ thuộc thứ tự, khó tái tạo và thu nhỏ | Reset hoặc tạo trạng thái mới cho mỗi lượt |
| Snapshot tham chiếu map mutable | Bản “trước” bị sửa theo bản “sau” | Chụp dữ liệu bất biến hoặc bản sao sâu phù hợp |
| Tính expected bằng cùng hàm production | Cùng sai thì test vẫn xanh | Dùng đặc tả độc lập và số học chính xác khi cần |
| Đồng nhất rollback local với không có tác dụng bên ngoài | Cổng thanh toán có thể đã thực hiện lệnh | Kiểm tra cả ranh giới side effect và gửi lại |
| Xem nhiều lượt chạy là chứng minh đầy đủ | Bỏ qua miền dữ liệu và lịch thực thi chưa được sinh | Ghi rõ phạm vi, bổ sung kiểm thử tích hợp và đồng thời |

## 13. Bài tập áp dụng

Mở rộng ví dụ để hỗ trợ yêu cầu hoàn đang chờ xử lý và yêu cầu đã hoàn tất:

```text
capturedVnd > 0
reservedVnd >= 0
settledVnd >= 0
reservedVnd + settledVnd <= capturedVnd
```

1. Định nghĩa khi nào một lệnh mới giữ ngân sách, khi nào chuyển phần giữ sang đã hoàn và khi nào giải phóng ngân sách.
2. Viết thuộc tính khẳng định `settle` một yêu cầu đang chờ không làm thay đổi tổng ngân sách đã sử dụng.
3. Sinh chuỗi `request → settle → settle lại`, `request → fail → request mới` và `request → timeout → gửi lại`.
4. Thêm chủ thể khác tenant và cùng key nhưng khác nội dung; assert quyết định và snapshot sau từng bước.
5. Dùng phép tính tổng độc lập tránh tràn số, đồng thời thêm ca xác nhận yêu cầu hợp lệ được chấp nhận.
6. Xác định các tác dụng phụ phải kiểm tra tại database/outbox và những điều mô hình trong bộ nhớ chưa chứng minh được.

Trước khi viết mã, thống nhất cách xử lý một kết quả timeout chưa rõ thành bại. Nếu chưa biết tiền đã được hoàn hay chưa, một thuộc tính tự động giải phóng ngân sách ngay có thể khuyến khích nhận thêm lệnh và gây hoàn vượt tiền đã thu. Phát biểu đúng bất biến và ranh giới trạng thái là phần quyết định giá trị của bộ kiểm thử.
