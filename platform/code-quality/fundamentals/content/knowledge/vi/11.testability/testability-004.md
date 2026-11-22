# Giảm trạng thái toàn cục và sự phụ thuộc thứ tự chạy

> **Chương:** Khả năng kiểm thử  
> **Học phần:** CODE_QUALITY_FUNDAMENTALS — Hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không.

Một bài kiểm thử Java có thể thành công khi chạy riêng, nhưng thất bại khi chạy cùng các bài khác. Đổi thứ tự kiểm thử, chạy song song hoặc chuyển sang máy CI lại cho kết quả khác. Hiện tượng đó thường được gọi là *flaky test* khi kết quả không ổn định dù mã và đầu vào mong đợi không đổi. Một nguyên nhân quan trọng là bài kiểm thử đang phụ thuộc vào **trạng thái có thể thay đổi nằm ngoài phạm vi của nó**, hoặc ngầm giả định rằng một bài kiểm thử khác sẽ chạy trước.

Ví dụ, bài kiểm thử A thay ngưỡng miễn phí giao hàng trong một biến `static`; bài kiểm thử B lại giả định ngưỡng ban đầu chưa bị thay. Khi chạy B độc lập, nó đạt. Khi A chạy trước B, B có thể thất bại. Vấn đề không nằm ở việc JUnit “chạy sai thứ tự” mà ở chỗ **hai bài kiểm thử chưa thực sự độc lập**.

**Khả năng kiểm thử** (*testability*) cao nghĩa là ta có thể thiết lập đầu vào và trạng thái cần thiết, thực hiện hành vi rồi quan sát kết quả một cách đáng tin cậy, với ít phụ thuộc ngầm vào môi trường hoặc lịch sử chạy. Giảm trạng thái toàn cục có thể thay đổi và giảm phụ thuộc vào thứ tự là hai cách quan trọng để đạt điều đó.

Sau bài học, bạn có thể:

- Nhận diện trạng thái dùng chung làm kiểm thử ảnh hưởng lẫn nhau.
- Phân biệt dữ liệu bất biến dùng chung với trạng thái toàn cục có thể sửa đổi.
- Chuyển một chính sách Java từ biến `static` sang cấu hình được truyền qua constructor.
- Kiểm soát đồng hồ, dữ liệu, tài nguyên và tác dụng phụ để kiểm thử độc lập, tái lập được.
- Đánh giá đúng khi nào việc reset trạng thái, cố định thứ tự hoặc chạy tuần tự là giải pháp tạm thời chứ không phải cách khắc phục gốc.

## 1. Thế nào là kiểm thử độc lập với thứ tự chạy?

Một bài kiểm thử nên có khả năng chạy **một mình**, chạy **cùng cả bộ** và chạy **sau một bài kiểm thử bất kỳ** mà vẫn kiểm tra cùng một yêu cầu. Điều này không có nghĩa hai lần chạy luôn thành công: nếu hệ thống có lỗi thật, test cần thất bại nhất quán. Mục tiêu là **kết quả phụ thuộc vào hành vi cần kiểm tra, không phụ thuộc vào lịch sử của bài kiểm thử khác**.

Mô hình một bài kiểm thử dễ tin cậy:

```text
Thiết lập dữ liệu và phụ thuộc riêng
              |
              v
       Gọi hành vi cần kiểm tra
              |
              v
       Xác minh kết quả / tác dụng phụ
              |
              v
   Giải phóng tài nguyên hoặc cô lập dữ liệu
```

Có thể dùng cách nghĩ **Arrange – Act – Assert**:

1. **Arrange:** xây dựng đầy đủ tiền điều kiện và phụ thuộc.
2. **Act:** thực hiện hành vi.
3. **Assert:** kiểm tra kết quả, ngoại lệ và trạng thái quan sát được.

Nếu phần Arrange chỉ thiết lập một nửa điều kiện và dựa vào bài kiểm thử khác để chuẩn bị phần còn lại, test đã có **phụ thuộc thứ tự**.

| Đặc tính | Kiểm thử độc lập | Kiểm thử phụ thuộc thứ tự |
| --- | --- | --- |
| Dữ liệu ban đầu | Được tạo hoặc thiết lập rõ cho chính test | Giả định test khác đã tạo sẵn |
| Cấu hình | Được truyền hoặc cô lập trong phạm vi test | Đọc biến toàn cục do test khác thay |
| Thời gian | Dùng đồng hồ điều khiển được hoặc điều kiện thời gian rõ | Phụ thuộc thời điểm máy chạy |
| Kết quả | Có cùng ý nghĩa trong những điều kiện đã định | Thay đổi theo thứ tự chạy, máy hoặc lịch sử |
| Dọn dẹp | Tài nguyên được quản lý có kiểm soát | Dữ liệu và trạng thái rò sang test sau |

**Độc lập với thứ tự** khác với **không có tác dụng phụ**. Kiểm thử một phương thức ghi cơ sở dữ liệu vẫn có thể độc lập nếu mỗi bài kiểm thử sở hữu dữ liệu riêng và làm sạch đúng phạm vi.

## 2. Trạng thái toàn cục thường ẩn ở những đâu?

Trong Java, trạng thái dùng chung không chỉ là biến `public static`. Bất kỳ dữ liệu có thể thay đổi nào được chia sẻ ngoài ý muốn giữa các lời gọi hoặc bài kiểm thử đều cần được xem xét.

| Nguồn trạng thái | Ví dụ | Vì sao dễ gây phụ thuộc ngầm? |
| --- | --- | --- |
| Trường `static` có thể sửa | `static int retryLimit` | Một test thay thì test khác cùng JVM có thể thấy |
| Singleton có dữ liệu bên trong | Singleton cache hoặc bộ đếm | Các nơi gọi sử dụng cùng một đối tượng và lịch sử |
| Collection dùng chung | `static final Map` có thể `put()` | `final` chỉ cố định tham chiếu, không làm nội dung bất biến |
| Thuộc tính JVM và môi trường | `System.setProperty(...)`, `Locale.setDefault(...)`, `TimeZone.setDefault(...)` | Thay đổi có thể ảnh hưởng mã ở nơi khác trong cùng tiến trình |
| Đồng hồ hoặc ngẫu nhiên không kiểm soát | `Instant.now()`, giá trị random không có nguồn xác định | Kết quả phụ thuộc thời điểm và chuỗi giá trị ngoài test |
| Tài nguyên bên ngoài | Bảng cơ sở dữ liệu dùng chung, hàng đợi, tệp cố định | Test này ghi hoặc xóa dữ liệu của test kia |
| Trạng thái cấp ứng dụng | Bean singleton, cache phiên, feature flag trong bộ nhớ | Mọi test dùng chung context có thể nhìn thấy tác dụng phụ |
| Tác vụ nền | Thread, timer, callback đang chạy | Kết quả test thay đổi tùy thời điểm tác vụ hoàn tất |

Một giá trị **toàn cục nhưng bất biến** không tự động gây vấn đề. Ví dụ:

```java
private static final long STANDARD_SHIPPING_FEE_VND = 30_000L;
```

Hằng số nguyên thủy này không bị thay đổi khi chạy test nên thường an toàn để dùng chung. Ngược lại:

```java
private static final Map<String, Integer> COUNTERS = new HashMap<>();
```

Tham chiếu `COUNTERS` là `final` nhưng nội dung `HashMap` vẫn có thể bị sửa. Nó có thể rò trạng thái giữa các test và không an toàn khi nhiều luồng cập nhật đồng thời nếu không có cơ chế bảo vệ.

**Không phải cứ thấy `static` là phải xóa.** Cần hỏi: *giá trị này có thể thay đổi không, ai sở hữu việc thay đổi, phạm vi tồn tại là bao lâu và người gọi có nhận biết nó như một phụ thuộc hay không?*

## 3. Ví dụ lỗi điển hình: test A làm thay đổi kết quả của test B

Giả sử chính sách minh họa: phí giao hàng tiêu chuẩn bằng **30.000 VND**, được miễn nếu tổng tiền hàng sau giảm giá đạt một ngưỡng cấu hình.

### 3.1. Cài đặt với trạng thái `static` có thể thay đổi

```java
public final class LegacyShippingFee {
    private static long freeShippingThresholdVnd = 500_000L;

    private LegacyShippingFee() {
    }

    public static void setFreeShippingThresholdVnd(long thresholdVnd) {
        if (thresholdVnd < 0L) {
            throw new IllegalArgumentException("Negative threshold");
        }
        freeShippingThresholdVnd = thresholdVnd;
    }

    public static long calculateVnd(long subtotalAfterDiscountVnd) {
        if (subtotalAfterDiscountVnd < 0L) {
            throw new IllegalArgumentException("Negative subtotal");
        }
        return subtotalAfterDiscountVnd >= freeShippingThresholdVnd
                ? 0L
                : 30_000L;
    }
}
```

Phương thức `calculateVnd(...)` chỉ có một tham số, nhưng kết quả thực tế phụ thuộc thêm vào **ngưỡng đang lưu trong biến toàn cục**. Giá trị này có thể do bất kỳ nơi gọi nào đã chạy trước đó thay đổi.

Hai bài kiểm thử minh họa vấn đề:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class LegacyShippingFeeTest {
    @Test
    void promotionCanRaiseFreeShippingThreshold() {
        LegacyShippingFee.setFreeShippingThresholdVnd(600_000L);

        assertEquals(30_000L, LegacyShippingFee.calculateVnd(550_000L));
    }

    @Test
    void defaultThresholdMakesFiveHundredThousandFree() {
        assertEquals(0L, LegacyShippingFee.calculateVnd(500_000L));
    }
}
```

Nếu test thứ hai chạy trong một JVM mới với giá trị ban đầu 500.000 VND, nó thành công. Nếu test thứ nhất thay ngưỡng thành 600.000 VND trước, test thứ hai thất bại. JUnit 5 không bảo đảm rằng hai bài kiểm thử trong lớp này luôn được chạy theo thứ tự viết ở tệp, nên cả việc “chạy thường thấy vẫn xanh” cũng không chứng minh chúng độc lập.

Các vấn đề đáng chú ý:

- Một lần gọi `setFreeShippingThresholdVnd(...)` làm thay đổi ngữ nghĩa của những lần gọi `calculateVnd(...)` **sau đó** trong cùng JVM.
- Test không công bố đủ đầu vào: ngưỡng bị ẩn trong trạng thái toàn cục.
- Chạy riêng một test không đảm bảo phát hiện phụ thuộc thứ tự.
- Nếu hai test chạy song song, việc đọc/ghi một trường `long` dùng chung không có đồng bộ phù hợp còn tạo rủi ro về tính nhìn thấy và tính nhất quán của trạng thái giữa các luồng.

Không nên “sửa” test thứ hai bằng cách giả định một thứ tự luôn cố định. Điều cần cải thiện là **quyền sở hữu trạng thái và cách truyền cấu hình**.

## 4. Thay phụ thuộc ngầm bằng dữ liệu được truyền tường minh

Nếu ngưỡng là cấu hình cho một lần tính chính sách, hãy biến nó thành dữ liệu thuộc về một đối tượng chính sách cụ thể thay vì biến dùng chung có thể sửa tùy ý.

### 4.1. Định nghĩa chính sách bất biến

```java
// ShippingPolicy.java
public final class ShippingPolicy {
    private final long freeShippingThresholdVnd;
    private final long standardShippingFeeVnd;

    public ShippingPolicy(
            long freeShippingThresholdVnd,
            long standardShippingFeeVnd) {
        if (freeShippingThresholdVnd < 0L || standardShippingFeeVnd < 0L) {
            throw new IllegalArgumentException("Negative shipping values");
        }
        this.freeShippingThresholdVnd = freeShippingThresholdVnd;
        this.standardShippingFeeVnd = standardShippingFeeVnd;
    }

    public long freeShippingThresholdVnd() {
        return freeShippingThresholdVnd;
    }

    public long standardShippingFeeVnd() {
        return standardShippingFeeVnd;
    }
}
```

Hai trường `final` chứa các giá trị nguyên thủy và không có setter, vì vậy mỗi đối tượng `ShippingPolicy` giữ một cấu hình ổn định sau khi được tạo.

### 4.2. Truyền chính sách qua constructor

```java
// ShippingFeeCalculator.java
import java.util.Objects;

public final class ShippingFeeCalculator {
    private final ShippingPolicy policy;

    public ShippingFeeCalculator(ShippingPolicy policy) {
        this.policy = Objects.requireNonNull(policy, "policy");
    }

    public long calculateVnd(long subtotalAfterDiscountVnd) {
        if (subtotalAfterDiscountVnd < 0L) {
            throw new IllegalArgumentException("Negative subtotal");
        }
        if (subtotalAfterDiscountVnd >= policy.freeShippingThresholdVnd()) {
            return 0L;
        }
        return policy.standardShippingFeeVnd();
    }
}
```

**Phụ thuộc đã trở nên rõ ràng:** để tạo `ShippingFeeCalculator`, bên dùng phải cung cấp một `ShippingPolicy`. Khi kiểm thử, ta được quyền chọn cấu hình riêng mà không sửa một giá trị toàn cục.

Điều này còn có lợi cho bảo trì: một luồng tạo báo giá với chính sách mới có thể dùng một đối tượng mới, trong khi một bài kiểm thử khác sử dụng ngưỡng cũ không bị ảnh hưởng. Trong hệ thống thật, quy tắc nào được áp dụng cho giao dịch nào vẫn phải được quản lý theo phiên bản hoặc thời điểm hiệu lực; dependency injection **không tự giải quyết việc đồng bộ chính sách giữa các dịch vụ**.

### 4.3. Test không còn phụ thuộc vào thứ tự

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class ShippingFeeCalculatorTest {
    @Test
    void thresholdAtFiveHundredThousandIsFree() {
        ShippingPolicy policy = new ShippingPolicy(500_000L, 30_000L);
        ShippingFeeCalculator calculator = new ShippingFeeCalculator(policy);

        assertEquals(0L, calculator.calculateVnd(500_000L));
        assertEquals(30_000L, calculator.calculateVnd(499_999L));
    }

    @Test
    void campaignPolicyHasIndependentThreshold() {
        ShippingPolicy campaignPolicy = new ShippingPolicy(600_000L, 30_000L);
        ShippingFeeCalculator calculator =
                new ShippingFeeCalculator(campaignPolicy);

        assertEquals(30_000L, calculator.calculateVnd(550_000L));
        assertEquals(0L, calculator.calculateVnd(600_000L));
    }

    @Test
    void invalidAmountsAreRejected() {
        ShippingFeeCalculator calculator =
                new ShippingFeeCalculator(new ShippingPolicy(500_000L, 30_000L));

        assertThrows(IllegalArgumentException.class,
                () -> calculator.calculateVnd(-1L));
    }
}
```

Mỗi test thiết lập đầy đủ chính sách mà nó cần. Chúng không dùng biến `static` có thể sửa, không có `setThreshold()` chung và không đòi hỏi test khác chạy trước. **Thứ tự thực thi không nằm trong hợp đồng của những test này.**

### Trước và sau refactor

| Khía cạnh | Biến `static` có thể sửa | Đối tượng chính sách được truyền vào |
| --- | --- | --- |
| Đầu vào quyết định kết quả | Một tham số công khai và trạng thái ngầm | Tham số và chính sách của chính đối tượng |
| Cách thiết lập trong test | Sửa giá trị toàn cục | Tạo đối tượng với giá trị test cần |
| Ảnh hưởng lên test khác | Có thể rò sang mọi nơi trong JVM | Không ảnh hưởng nếu từng test sở hữu đối tượng riêng |
| Chạy song song | Dễ tranh chấp nếu cùng sửa cấu hình | Các đối tượng bất biến riêng biệt tránh tranh chấp cấu hình |
| Thay đổi chính sách | Mọi caller thấy thay đổi từ một setter toàn cục | Chọn hoặc phát hành phiên bản chính sách theo luồng phù hợp |

Một đối tượng **được truyền qua constructor vẫn có thể là mutable và bị chia sẻ**. Dependency injection không tự động bảo đảm độc lập; cách quản lý vòng đời và khả năng thay đổi của đối tượng mới là yếu tố quyết định.

## 5. Kiểm soát thời gian để test không phụ thuộc vào lúc chạy

Trạng thái ngầm không chỉ nằm trong biến `static` do ta viết. Đồng hồ hệ thống cũng là một phụ thuộc toàn cục:

```java
boolean canSendReminder(Instant scheduledAt) {
    return !Instant.now().isBefore(scheduledAt);
}
```

Nếu test chọn thời điểm chỉ cách hiện tại vài mili giây, kết quả có thể thay đổi tùy tốc độ máy, độ tải hoặc thời điểm thực thi. Sử dụng `Thread.sleep(...)` để chờ đến một thời điểm thường khiến test chậm và vẫn có thể không ổn định.

Trong Java, `Clock` cho phép truyền nguồn thời gian tường minh:

```java
// ReminderEligibility.java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class ReminderEligibility {
    private final Clock clock;

    public ReminderEligibility(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public boolean canSendAt(Instant scheduledAt) {
        Objects.requireNonNull(scheduledAt, "scheduledAt");
        Instant now = Instant.now(clock);
        return !now.isBefore(scheduledAt);
    }
}
```

Trong ứng dụng thật, có thể tạo bằng `Clock.systemUTC()`. Trong test, dùng `Clock.fixed(...)`:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class ReminderEligibilityTest {
    private static final Instant FIXED_NOW =
            Instant.parse("2026-01-01T12:00:00Z");

    @Test
    void doesNotSendBeforeScheduledTime() {
        Clock clock = Clock.fixed(FIXED_NOW, ZoneOffset.UTC);
        ReminderEligibility eligibility = new ReminderEligibility(clock);

        assertFalse(eligibility.canSendAt(
                Instant.parse("2026-01-01T12:00:01Z")));
    }

    @Test
    void CanSendExactlyAtScheduledTime() {
        Clock clock = Clock.fixed(FIXED_NOW, ZoneOffset.UTC);
        ReminderEligibility eligibility = new ReminderEligibility(clock);

        assertTrue(eligibility.canSendAt(FIXED_NOW));
    }
}
```

Trong ví dụ trên, kết quả phụ thuộc vào **thời điểm cố định do test chọn**, không phụ thuộc vào đồng hồ thật. Việc viết giờ theo UTC với `Instant` và `ZoneOffset.UTC` cũng giúp tránh nhầm lẫn từ múi giờ mặc định trong phép so sánh này. Với nghiệp vụ tính theo ngày địa phương, cần công bố và kiểm thử **múi giờ nghiệp vụ**, không mặc định mọi vấn đề thời gian đều dùng UTC để hiển thị.

Tương tự, với hành vi có ngẫu nhiên, có thể tiêm một nguồn tạo giá trị qua interface hoặc nguồn sinh số có thể kiểm soát trong test. **Không dùng bộ sinh ngẫu nhiên cố định cho mục đích bảo mật ở môi trường thật** chỉ vì cách đó giúp test dễ hơn.

## 6. Cô lập trạng thái trong bộ nhớ và vòng đời của đối tượng

### 6.1. Tạo đối tượng mới khi test cần trạng thái riêng

Giả sử một bộ đếm đơn giản:

```java
public final class RequestCounter {
    private int count;

    public void increment() {
        count++;
    }

    public int value() {
        return count;
    }
}
```

Mỗi test có thể tạo một `RequestCounter` mới và khẳng định giá trị ban đầu là `0`. Nếu đưa bộ đếm vào một singleton dùng chung hoặc một trường `static`, các test sẽ vô tình dùng chung lịch sử.

Đoạn lớp trên chỉ dùng để minh họa **quyền sở hữu trạng thái**: nó không an toàn cho nhiều luồng cùng tăng `count` mà không đồng bộ. Nếu ứng dụng thực tế cần bộ đếm dùng chung giữa các luồng, có thể dùng cơ chế đồng bộ, `AtomicInteger` hoặc cấu trúc phù hợp. Khi đó, test vẫn cần sở hữu một đối tượng riêng hoặc thiết lập ranh giới cô lập rõ ràng.

### 6.2. Hiểu vòng đời mặc định của JUnit 5

Với JUnit Jupiter, mặc định mỗi phương thức `@Test` có một instance mới của lớp test (*PER_METHOD*). Điều đó giúp cách ly các trường instance của lớp kiểm thử, nhưng **không reset** trạng thái `static`, singleton, thuộc tính JVM hoặc dữ liệu trong cơ sở dữ liệu.

JUnit hỗ trợ `@BeforeEach` để chuẩn bị dữ liệu trước mỗi test và `@AfterEach` để dọn dẹp, nhưng hai annotation này không thay thế được việc thiết kế ranh giới trạng thái phù hợp. Nếu một test sửa một cấu hình toàn cục trong khi test khác chạy song song, reset trong `@AfterEach` vẫn có thể diễn ra quá muộn để tránh xung đột.

### 6.3. Đừng hiểu “reset” là luôn an toàn

Một cách chữa cháy thường gặp:

```java
@AfterEach
void resetGlobalPolicy() {
    LegacyShippingFee.setFreeShippingThresholdVnd(500_000L);
}
```

Giải pháp này có thể giảm rò rỉ khi chạy tuần tự, nhưng còn nhiều hạn chế:

- Giả định **500.000 VND** luôn là giá trị gốc đúng, dù cấu hình có thể đổi.
- Nếu test thất bại vì tác vụ chạy nền hoặc trạng thái ngoài JVM, reset giá trị chưa giải quyết được.
- Hai test chạy đồng thời vẫn có thể đọc ngưỡng của nhau giữa lúc bắt đầu và dọn dẹp.
- Cách làm này để lại **phụ thuộc ngầm** trong mã sản phẩm.

Nếu chưa thể refactor mã cũ, test có thể phải sao lưu và phục hồi trạng thái trong một vùng chạy tuần tự có kiểm soát. Hãy ghi rõ đó là **biện pháp chuyển tiếp**, không phải chứng minh rằng hệ thống đã không còn phụ thuộc toàn cục.

## 7. Tác động của chạy song song và bất đồng bộ

Các test không phụ thuộc thứ tự vẫn có thể không an toàn khi chạy song song nếu chúng cùng sửa một tài nguyên. Ví dụ, hai bài kiểm thử sử dụng cùng tên tệp `output.json` và một bài xóa tệp khi bài khác đang đọc.

```text
Test A: ghi output.json ------- xóa output.json
                       ^
Test B: ----------- đọc output.json
```

Một cách giảm xung đột là để **mỗi test sở hữu tài nguyên riêng**:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ReportFileTest {
    @TempDir
    Path workDir;

    @Test
    void writesReportInsideIsolatedDirectory() throws Exception {
        Path report = workDir.resolve("report.txt");
        Files.writeString(report, "ready");

        org.junit.jupiter.api.Assertions.assertEquals(
                "ready", Files.readString(report));
    }
}
```

`@TempDir` tạo một thư mục tạm được JUnit quản lý cho bài kiểm thử, giúp tránh dùng tên tệp toàn cục cố định. Ví dụ sử dụng `Files.writeString(...)` (Java 11 trở lên); nếu dự án dùng Java cũ hơn cần chọn API I/O tương thích.

### Đồng bộ không đồng nghĩa độc lập

Khóa `synchronized` hoặc `AtomicInteger` có thể giảm lỗi tranh chấp cập nhật nhưng **không làm các test độc lập về ngữ nghĩa**. Hai test dùng chung một bộ đếm được đồng bộ có thể không làm hỏng dữ liệu, nhưng giá trị đếm cuối cùng vẫn phụ thuộc vào việc có bao nhiêu test đã tăng bộ đếm.

Với tác vụ bất đồng bộ, tránh giả định “sau 100 ms chắc chắn đã xong”. Thay vào đó, nên dùng tín hiệu hoàn thành, `Future`, `CompletionStage` hoặc công cụ đồng bộ với thời hạn rõ. Các test cần đợi **điều kiện có ý nghĩa** và dọn dẹp tác vụ đã khởi chạy. Không để thread nền từ test trước tiếp tục thay trạng thái trong test sau.

## 8. Dữ liệu và môi trường bên ngoài cũng cần được cô lập

### 8.1. Cơ sở dữ liệu dùng chung

Một test ghi đơn hàng có `id = 1`, test khác cũng dùng `id = 1` và kỳ vọng bản ghi chưa tồn tại. Nếu cơ sở dữ liệu được dùng chung, kết quả có thể phụ thuộc vào thứ tự hoặc các lần chạy trước.

Các chiến lược thường dùng tùy dự án:

| Chiến lược | Lợi ích | Giới hạn |
| --- | --- | --- |
| Tạo định danh và dữ liệu riêng cho mỗi test | Ít va chạm, rõ đối tượng được kiểm thử | Cần dọn dẹp và tránh trùng ở những khóa khác |
| Dùng transaction rồi rollback ở cuối test | Hạn chế dữ liệu còn sót trong phạm vi giao dịch | Không bao trùm mọi tác vụ bất đồng bộ hay lời gọi dịch vụ ngoài transaction |
| Dùng schema/database/container riêng | Cách ly tốt khi test đồng thời | Tốn tài nguyên, thời gian khởi tạo |
| Dùng repository giả hoặc in-memory fake cho unit test | Nhanh, dễ điều khiển các trường hợp lỗi | Không chứng minh tương thích với database thật |

Không phải cứ “xóa toàn bộ bảng ở `@AfterEach`” là an toàn. Khi test chạy đồng thời hoặc dùng chung môi trường, thao tác dọn dẹp quá rộng có thể xóa dữ liệu của test khác. Phải xác định quyền sở hữu và phạm vi dữ liệu được phép dọn.

### 8.2. Cấu hình JVM và môi trường

`Locale.setDefault(...)`, `TimeZone.setDefault(...)` và `System.setProperty(...)` có thể ảnh hưởng tới nhiều thành phần trong cùng JVM. Nếu phải thay đổi chúng để kiểm tra chức năng cũ, cần phục hồi giá trị trước đó trong `finally` hoặc cơ chế dọn dẹp phù hợp, và tránh chạy song song với test cũng đọc/ghi cùng trạng thái.

Giải pháp bền vững hơn thường là **truyền cấu hình vào thành phần**:

```java
final class InvoiceFormatter {
    private final Locale locale;

    InvoiceFormatter(Locale locale) {
        this.locale = Objects.requireNonNull(locale, "locale");
    }

    // Các phương thức định dạng sử dụng locale của đối tượng,
    // không đọc Locale.getDefault() mỗi khi được gọi.
}
```

Đoạn trên minh họa ranh giới cấu hình; khi dùng, cần import `java.util.Locale` và `java.util.Objects`. Khi ứng dụng thật cần nhận một locale mặc định, hãy chọn nó ở **điểm khởi tạo**, thay vì để mọi phương thức tự đọc một biến toàn cục có thể bị thay.

### 8.3. Dịch vụ ngoài và sự kiện

Test gửi email thật hoặc phát thông điệp vào hàng đợi dùng chung có thể tạo tác dụng ngoài phạm vi test. Unit test thường nên thay phụ thuộc đó bằng fake/mock có hợp đồng rõ; integration test có thể sử dụng môi trường riêng và kiểm tra tác dụng thực tế.

Với API có retry, idempotency hoặc xử lý bất đồng bộ, không thể chỉ reset một biến Java để xóa mọi tác dụng đã gửi ra ngoài. Cần thiết kế **định danh thử nghiệm, vùng dữ liệu thử nghiệm và quy trình làm sạch hoặc đối soát phù hợp**.

## 9. “Ép thứ tự test” có chữa được lỗi không?

JUnit 5 cung cấp cơ chế sắp xếp thứ tự khi một bộ kiểm thử **cố ý kiểm tra quy trình có trạng thái**. Tuy nhiên, thêm `@TestMethodOrder` hoặc đặt tên test theo số thứ tự chỉ để khiến một bộ test đang lỗi chuyển sang xanh thường **che nguyên nhân**.

Phân biệt hai trường hợp:

| Tình huống | Cách kiểm thử nên hướng tới |
| --- | --- |
| Hai chức năng độc lập nhưng test B phải chờ test A thiết lập dữ liệu | Để B tự thiết lập dữ liệu của nó; loại bỏ phụ thuộc thứ tự |
| Một quy trình nghiệp vụ thực sự phải đi từ “tạo đơn → thanh toán → giao hàng” | Trong **một bài kiểm thử kịch bản**, thực hiện các bước theo thứ tự nghiệp vụ và xác minh từng chuyển trạng thái |

Ví dụ kiểm thử kịch bản:

```java
@Test
void orderLifecycleFollowsExpectedTransitions() {
    Order order = createNewOrder();
    pay(order);
    pack(order);

    assertEquals(OrderStatus.PACKED, order.getStatus());
}
```

Trong ví dụ, `Order`, `OrderStatus` và các thao tác là thành phần giả định của ứng dụng. Sự phụ thuộc **giữa các bước nghiệp vụ trong cùng một test** là có chủ đích. Nó khác với việc test `payOrder()` chỉ chạy được sau một test `createOrder()` riêng biệt, cùng chia sẻ đơn hàng toàn cục.

Một bộ test tốt cho phép chọn và chạy lại riêng kịch bản đang thất bại mà không cần phải chạy một chuỗi test khác để dựng lịch sử trạng thái.

## 10. Cách phát hiện test bị phụ thuộc trạng thái

Các dấu hiệu đáng điều tra:

1. Test **chạy riêng thì đạt, chạy cả lớp hoặc cả suite thì thất bại**.
2. Kết quả thay đổi khi bật hoặc tắt chạy song song.
3. Test chỉ đạt sau khi xóa cache, khởi động lại JVM hoặc làm sạch database.
4. Một test sửa `static`, singleton, system property, múi giờ hoặc biến cấu hình rồi không phục hồi đúng.
5. Test dùng tên tệp, khóa dữ liệu hoặc tài khoản cố định chung với test khác.
6. Test dùng `Thread.sleep()` và hy vọng tác vụ khác hoàn tất đúng lúc.
7. Test có chú thích “phải chạy sau test X” dù chúng được khai báo là hai test độc lập.

Một quy trình điều tra có kiểm soát:

- **Tái hiện** bằng cách chạy một test riêng, chạy cùng các test liên quan và thử các thứ tự khác nhau nếu công cụ hỗ trợ. Không tự kết luận lỗi chỉ vì nó xuất hiện ngẫu nhiên.
- **Tìm phụ thuộc ngầm**: biến `static` có thể sửa, singleton, cache, time, random, filesystem, database, queue và tác vụ nền.
- **Xác định quyền sở hữu trạng thái**: test nào tạo, test nào sửa, test nào có quyền xóa và liệu các test có chạy đồng thời không.
- **Ưu tiên loại bỏ trạng thái chung**: truyền phụ thuộc và tạo tài nguyên riêng trong Arrange.
- **Giữ bằng chứng kiểm thử**: sau refactor, chạy lại các trường hợp thành công/lỗi và kiểm tra có thay đổi hành vi ngoài ý muốn không.

Chạy lặp lại nhiều lần có thể giúp phát hiện tính không ổn định, nhưng một trăm lần xanh **không chứng minh** không còn lỗi cạnh tranh. Cần đánh giá thiết kế trạng thái và cách đồng bộ dựa trên đường thực thi thực tế.

## 11. Những đánh đổi và ngộ nhận thường gặp

### “Cứ bỏ tất cả `static` là sẽ test tốt”

Không đúng. Hằng số bất biến, phương thức thuần và dữ liệu cấu hình không thể sửa có thể dùng chung an toàn. Vấn đề chủ yếu nằm ở **trạng thái toàn cục có thể thay đổi** và những phụ thuộc ngầm không được kiểm soát.

### “Dùng dependency injection là test tự động độc lập”

Nếu mọi test cùng nhận một singleton có bộ đếm mutable, chúng vẫn chia sẻ trạng thái. Phải xét cả **vòng đời và khả năng thay đổi** của đối tượng được inject.

### “Chỉ cần `@BeforeEach` reset trạng thái”

Reset có thể hữu ích nhưng không bảo vệ được mọi trường hợp chạy song song, callback còn chạy hoặc tác dụng phụ đã gửi sang hệ thống khác. Khi phù hợp, hãy tạo trạng thái riêng ngay từ đầu.

### “Khóa đồng bộ giải quyết mọi flaky test”

Khóa giúp xử lý một số race condition, nhưng không ngăn việc test khác thay ngữ nghĩa của dữ liệu chung. Tính độc lập và tính an toàn luồng là **hai thuộc tính khác nhau**.

### “Nếu muốn test thứ tự chạy, phải dùng `@TestMethodOrder`”

Nếu nghiệp vụ đòi hỏi một chuỗi hành động, có thể đưa chuỗi đó vào một kịch bản kiểm thử với bước Arrange rõ ràng. Sắp thứ tự các test độc lập để vá lỗi rò trạng thái thường làm vấn đề khó thấy hơn.

### “Mock mọi thứ thì đạt được khả năng kiểm thử cao nhất”

Mock có thể cô lập đơn vị xử lý, nhưng quá nhiều mock khiến test gắn chặt vào chi tiết triển khai và bỏ sót lỗi tích hợp thật. Kết hợp unit test và integration test ở mức phù hợp với rủi ro để có bằng chứng đáng tin cậy.

### “Test không ổn định thì chỉ cần chạy lại đến khi xanh”

Retry test trong CI có thể giúp chẩn đoán hoặc giảm gián đoạn tạm thời, nhưng nếu không điều tra nguyên nhân, nó có thể che lỗi sản phẩm, lỗi đồng thời hoặc dữ liệu rò rỉ. Kết quả kiểm thử không đáng tin sẽ làm giảm giá trị của mọi quyết định phát hành dựa vào nó.

## 12. Checklist khi review khả năng kiểm thử

| Câu hỏi | Dấu hiệu cần cải thiện |
| --- | --- |
| Test có tạo đầy đủ dữ liệu đầu vào của chính nó không? | Dựa vào bản ghi hoặc test khác đã chạy |
| Đối tượng được kiểm thử có đọc trạng thái mutable toàn cục không? | `static` setter, singleton cache, biến JVM dùng chung |
| Có thể cung cấp thời gian và cấu hình kiểm soát được không? | Phụ thuộc `Instant.now()`, múi giờ mặc định hoặc file cấu hình sửa tại runtime |
| Test có làm thay đổi tài nguyên chung không? | Ghi vào tệp cố định, bảng dữ liệu hoặc hàng đợi chung |
| Dọn dẹp có đúng phạm vi tài nguyên do test tạo không? | Xóa dữ liệu của test khác hoặc để sót trạng thái |
| Chạy đồng thời có làm hai test tranh chấp không? | Sửa singleton hoặc collection dùng chung |
| Test có kiểm tra kết quả và tác dụng phụ theo hợp đồng không? | Chỉ kiểm tra không ném ngoại lệ |
| Bộ test có cần một thứ tự ngầm để chạy xanh không? | Test B đòi test A phải chạy trước |
| Test còn đáng tin khi đổi máy hoặc tốc độ xử lý không? | `Thread.sleep()` hoặc phụ thuộc thời gian quá sát |
| Đã kiểm tra các trường hợp lỗi ở ranh giới ngoài chưa? | Mock chỉ trả đường thành công |

## 13. Bài tập thực hành

Một hệ thống cho phép thiết lập giới hạn số lần thử đăng nhập. Mã cũ:

```java
final class LoginPolicy {
    static int maxFailedAttempts = 5;

    static boolean shouldLock(int failedAttempts) {
        return failedAttempts >= maxFailedAttempts;
    }
}
```

Hai bài kiểm thử:

```java
@Test
void strictPolicyLocksAfterThreeFailures() {
    LoginPolicy.maxFailedAttempts = 3;
    assertTrue(LoginPolicy.shouldLock(3));
}

@Test
void defaultPolicyAllowsFourFailures() {
    assertFalse(LoginPolicy.shouldLock(4));
}
```

Giả sử chính sách mặc định của ứng dụng là khóa sau **5 lần thất bại**, còn một nhóm thử nghiệm sử dụng ngưỡng **3 lần**.

Hãy thực hiện:

1. Chỉ rõ **đầu vào ngầm** của `shouldLock(...)` là gì và vì sao hai test có thể ảnh hưởng lẫn nhau.
2. Thay biến `static` có thể sửa bằng một lớp cấu hình bất biến được truyền vào đối tượng quyết định khóa. Làm rõ phạm vi hợp lệ của `maxFailedAttempts` (ví dụ phải lớn hơn 0) và của `failedAttempts` (không âm).
3. Viết lại hai test để mỗi test tự tạo chính sách **5 lần** hoặc **3 lần** và không phụ thuộc vào thứ tự chạy.
4. Viết thêm các trường hợp biên: `failedAttempts = 0`, ngay dưới ngưỡng, đúng ngưỡng, trên ngưỡng và đầu vào không hợp lệ.
5. Nếu giới hạn được tải từ một dịch vụ cấu hình có thể thay đổi trong lúc ứng dụng chạy, hãy giải thích ai sở hữu phiên bản cấu hình, thời điểm một yêu cầu bắt đầu dùng phiên bản mới và cách test mô phỏng các phiên bản mà không sửa cấu hình toàn cục.
6. Nếu nhiều yêu cầu đăng nhập đồng thời cập nhật số lần thất bại của **cùng tài khoản**, tại sao việc bỏ `static` trong `LoginPolicy` chưa đủ bảo đảm không vượt quá giới hạn? Bạn sẽ cần làm rõ cập nhật nguyên tử và hợp đồng trạng thái tài khoản như thế nào?

**Gợi ý:** một đối tượng chính sách bất biến có thể làm phép quyết định đơn giản và kiểm thử được, nhưng số lần đăng nhập thất bại là **trạng thái nghiệp vụ thực** cần được lưu và đồng bộ nhất quán. Mục tiêu không phải xóa mọi trạng thái, mà là đặt đúng trạng thái ở đúng nơi sở hữu.

## Ghi nhớ

Kiểm thử đáng tin cậy cần **đầu vào rõ ràng, trạng thái được sở hữu và kết quả có thể tái lập**. Hãy tránh để biến toàn cục có thể sửa, singleton mutable, đồng hồ, tài nguyên ngoài hoặc lịch sử test trở thành điều kiện ngầm. Ưu tiên phụ thuộc được truyền tường minh, dữ liệu và tài nguyên riêng cho mỗi test, cùng cơ chế điều khiển thời gian và dọn dẹp có kiểm soát. Khi test có thể chạy độc lập, kết quả xanh hoặc đỏ mới trở thành bằng chứng hữu ích cho tính đúng đắn của mã.
