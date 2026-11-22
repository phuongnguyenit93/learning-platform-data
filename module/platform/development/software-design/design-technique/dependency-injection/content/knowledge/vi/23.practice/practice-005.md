# Truyền clock để kiểm thử quy tắc phụ thuộc thời gian

## 1. Vì sao đồng hồ hệ thống là một dependency?

Trong **Dependency Injection (DI)**, một lớp nhận những cộng tác viên mà nó cần từ bên ngoài, thường qua constructor, thay vì tự tìm hoặc tự tạo chúng. Với **Inversion of Control (IoC)**, quyền chọn implementation và lắp ghép được chuyển tới **composition root**. Ta thường nghĩ dependency là repository, HTTP client hay email sender, nhưng **nguồn thời gian hiện tại** cũng là một dependency.

Xem quy tắc nghiệp vụ: chương trình cho phép áp dụng khuyến mãi từ 08:00 đến trước 09:00 UTC. Code sau có vẻ đơn giản:

```java
// Ví dụ cần cải thiện: đọc đồng hồ thật ngay trong nghiệp vụ.
boolean isPromotionActive(Instant startsAt, Instant endsAt) {
    Instant now = Instant.now();
    return !now.isBefore(startsAt) && now.isBefore(endsAt);
}
```

Đoạn trên có ba vấn đề quan trọng:

1. **Không thể chọn thời điểm trong test:** muốn kiểm tra đúng 09:00 phải chờ đồng hồ thật hoặc tìm cách thay thế phương thức tĩnh toàn cục.
2. **Dễ sinh test chập chờn:** một test có thể chạy sát thời điểm đổi ngày/hết hạn và cho kết quả khác nhau tùy tốc độ máy.
3. **Quyết định lấy giờ bị giấu trong logic:** production, test và các môi trường có nhu cầu khác nhau nhưng đều buộc dùng đồng hồ thật do code tự chọn.

Java cung cấp `java.time.Clock` để giải quyết đúng loại bài toán này. Một lớp có thể nhận `Clock` qua constructor, sau đó dùng `clock.instant()` hoặc `LocalDate.now(clock)`. Composition root lựa chọn **`Clock.systemUTC()` trong ứng dụng** và **`Clock.fixed(...)` trong bài test**.

**Mục tiêu của bài thực hành:**

- Xác định các quy tắc nghiệp vụ thật sự phụ thuộc thời gian và khai báo nguồn thời gian thành dependency tường minh.
- Tổ chức constructor injection với `Clock`, không cần DI container hay framework mocking.
- Kiểm thử chính xác thời điểm **trước, tại và sau** ranh giới bắt đầu/kết thúc.
- Phân biệt `Instant`, `LocalDate`, `Duration`, `ZoneId` và vai trò của timezone khi tính ngày nghiệp vụ.
- Hiểu phạm vi của `Clock.fixed`, `Clock.offset`, `Clock.tick` và `Clock.systemUTC`.
- Tránh lẫn đồng hồ lịch (*wall clock*) với đồng hồ đo thời gian trôi có tính đơn điệu (*monotonic elapsed time*), đồng thời kiểm soát độ trễ và lỗi trong hệ thống thật.

**Phạm vi:** Java thuần với API `java.time` tiêu chuẩn (ví dụ chạy trên JDK 8 trở lên). Bài này là thực hành thiết kế DI, chưa bàn đến việc framework tự đăng ký bean `Clock`.

## 2. Tách “thời điểm hiện tại” khỏi quy tắc nghiệp vụ

Trước khi viết code, cần xác định **hợp đồng thời gian** của nghiệp vụ.

Giả sử một chương trình khuyến mãi có:

- `startsAt`: thời điểm bắt đầu có hiệu lực, **bao gồm** thời điểm này.
- `endsAt`: thời điểm hết hiệu lực, **không bao gồm** thời điểm này.
- `now`: một thời điểm hiện tại được lấy từ `Clock` khi thực hiện thao tác.

Quy tắc:

```text
            startsAt                         endsAt
---------------|================================|---------------
      UPCOMING           ACTIVE                     EXPIRED
                        [startsAt, endsAt)
```

Biểu thức tương đương:

```java
boolean active = !now.isBefore(startsAt)
        && now.isBefore(endsAt);
```

Dùng khoảng **nửa mở** `[startsAt, endsAt)` giúp hai chương trình liên tiếp không cùng được tính là có hiệu lực đúng tại mốc đổi chương trình. Nhưng đây là **quyết định hợp đồng**, không phải quy tắc Java bắt buộc. Một hợp đồng khác có thể nói hạn cuối là **bao gồm**; khi đó biểu thức kiểm tra phải thay đổi và test phải ghi nhận điều đó.

Không viết mơ hồ “được dùng đến hết ngày 18/11” nếu chưa nói rõ **múi giờ nào** và thời điểm kết thúc chính xác. Ví dụ, “đến hết 18/11 theo giờ Việt Nam” thường được mô hình hóa bằng mốc đầu ngày 19/11 tại múi giờ nghiệp vụ, và dùng điều kiện `now.isBefore(endExclusive)`.

### 2.1. Ba khái niệm cần giữ riêng

| Khái niệm | Kiểu Java hay dùng | Ví dụ và ý nghĩa |
| --- | --- | --- |
| **Một thời điểm tuyệt đối** | `Instant` | `2026-11-18T09:00:00Z`, cùng một mốc trên dòng thời gian toàn cục. |
| **Ngày lịch theo múi giờ** | `LocalDate` cùng `ZoneId` | Ngày 19/11 tại `Asia/Ho_Chi_Minh`, có thể vẫn là 18/11 theo UTC. |
| **Khoảng thời gian trôi** | `Duration` | 30 phút, 24 giờ, 90 giây; dùng để cộng/trừ thời lượng hoặc xác định deadline. |

`Clock` cung cấp một nguồn `Instant` và một timezone đi kèm. Nhưng **timezone của Clock không nên ngầm quyết định mọi quy tắc**: nếu ứng dụng phục vụ nhiều thị trường, hãy truyền rõ `ZoneId` nghiệp vụ hoặc tạo `Clock` với zone thích hợp ở composition root.

## 3. Đối chiếu các cách tiếp cận

### 3.1. Gắn cứng đồng hồ trong service

```java
final class LegacyPromotionService {
    boolean active(Instant startsAt, Instant endsAt) {
        Instant now = Instant.now();
        return !now.isBefore(startsAt) && now.isBefore(endsAt);
    }
}
```

Đơn giản lúc đầu nhưng buộc các test dùng đồng hồ thật. Nếu cần một ngày cụ thể, test dễ phải dùng cách sửa static API hoặc đợi theo thời gian, làm tăng coupling.

### 3.2. Truyền `Instant now` vào phương thức

```java
boolean active(Instant now, Instant startsAt, Instant endsAt) {
    return !now.isBefore(startsAt) && now.isBefore(endsAt);
}
```

Cách này **hoàn toàn hợp lệ** và rất tốt cho một hàm thuần. Logic không cần biết đồng hồ. Caller chịu trách nhiệm cung cấp `now` khi gọi.

Nếu nhiều phương thức trong một service đều cần thời gian hiện tại, inject `Clock` vào service giúp **không bắt mọi caller tự cung cấp giờ**. Cả hai cách có thể phối hợp: `PromotionService` đọc `clock.instant()` một lần, rồi gọi `PromotionWindow.statusAt(now)` là hàm thuần.

### 3.3. Constructor injection với `Clock`

```java
final class PromotionService {
    private final Clock clock;

    PromotionService(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    PromotionStatus evaluate(PromotionWindow window) {
        return window.statusAt(clock.instant());
    }
}
```

Đây là thiết kế chính của bài thực hành. Dependency được khai báo rõ và có thể thay ở nơi lắp ghép; Java kiểm tra kiểu tham số tại thời điểm biên dịch.

`Clock` **không phải dịch vụ lập lịch**. Nó cho biết “bây giờ là lúc nào” khi được hỏi, chứ không tự đánh thức chương trình tại deadline. Nếu cần thực thi một job đúng giờ, còn cần scheduler, queue hoặc timer có lifecycle và khả năng kiểm thử riêng.

## 4. Chương trình Java thuần: khuyến mãi theo cửa sổ thời gian

Ta xây một lớp `PromotionWindow` thuần dữ liệu/quy tắc, một lớp `PromotionService` nhận `Clock`, và một lớp `BusinessCalendar` nhận `Clock` cùng `ZoneId` để lấy ngày của thị trường.

- Khuyến mãi bắt đầu lúc **08:00 UTC** ngày 18/11/2026.
- Khuyến mãi kết thúc lúc **09:00 UTC** cùng ngày (mốc kết thúc không bao gồm).
- Trong demo ta dùng đồng hồ cố định **08:30 UTC**, để đầu ra luôn giống nhau.
- Ví dụ ngày lịch dùng **17:30 UTC**, khi đó tại `Asia/Ho_Chi_Minh` đã là **00:30 ngày 19/11**.

Lưu toàn bộ mã vào file `TimeRuleDemo.java`:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Objects;

enum PromotionStatus {
    UPCOMING, ACTIVE, EXPIRED
}

// Đối tượng giá trị: chỉ chứa mốc và quy tắc, không đọc đồng hồ.
final class PromotionWindow {
    private final String code;
    private final Instant startsAt;
    private final Instant endsAt;

    PromotionWindow(String code, Instant startsAt, Instant endsAt) {
        if (code == null || code.trim().isEmpty()) {
            throw new IllegalArgumentException("INVALID_PROMOTION_CODE");
        }

        this.code = code;
        this.startsAt = Objects.requireNonNull(startsAt, "startsAt");
        this.endsAt = Objects.requireNonNull(endsAt, "endsAt");

        if (!startsAt.isBefore(endsAt)) {
            throw new IllegalArgumentException(
                    "PROMOTION_WINDOW_MUST_HAVE_POSITIVE_LENGTH");
        }
    }

    String code() {
        return code;
    }

    PromotionStatus statusAt(Instant now) {
        Objects.requireNonNull(now, "now");

        if (now.isBefore(startsAt)) {
            return PromotionStatus.UPCOMING;
        }
        if (!now.isBefore(endsAt)) {
            return PromotionStatus.EXPIRED;
        }
        return PromotionStatus.ACTIVE;
    }
}

// Application service: chỉ đọc thời gian qua Clock đã inject.
final class PromotionService {
    private final Clock clock;

    PromotionService(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    PromotionStatus evaluate(PromotionWindow promotion) {
        Objects.requireNonNull(promotion, "promotion");

        // Lấy đúng một snapshot thời gian cho một quyết định.
        Instant now = clock.instant();
        return promotion.statusAt(now);
    }
}

// Quy tắc ngày lịch: ZoneId nghiệp vụ được cung cấp tường minh.
final class BusinessCalendar {
    private final Clock clock;
    private final ZoneId businessZone;

    BusinessCalendar(Clock clock, ZoneId businessZone) {
        this.clock = Objects.requireNonNull(clock, "clock");
        this.businessZone = Objects.requireNonNull(
                businessZone, "businessZone");
    }

    LocalDate businessDate() {
        Instant now = clock.instant();
        return now.atZone(businessZone).toLocalDate();
    }
}

public class TimeRuleDemo {
    public static void main(String[] args) {
        // Composition root của demo: chọn thời điểm cố định.
        Clock demoClock = Clock.fixed(
                Instant.parse("2026-11-18T08:30:00Z"),
                ZoneOffset.UTC);

        PromotionWindow promotion = new PromotionWindow(
                "NOV2026",
                Instant.parse("2026-11-18T08:00:00Z"),
                Instant.parse("2026-11-18T09:00:00Z"));

        PromotionService service = new PromotionService(demoClock);
        System.out.println("Status: " + service.evaluate(promotion));

        // Cùng một Instant nhưng ngày lịch tùy timezone.
        Clock nearMidnightUtc = Clock.fixed(
                Instant.parse("2026-11-18T17:30:00Z"),
                ZoneOffset.UTC);

        BusinessCalendar vietnam = new BusinessCalendar(
                nearMidnightUtc, ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("Business day: "
                + vietnam.businessDate());
    }
}
```

Chạy bằng JDK (Java 8+):

```bash
javac TimeRuleDemo.java
java TimeRuleDemo
```

Đầu ra dự kiến:

```text
Status: ACTIVE
Business day: 2026-11-19
```

**Giải thích:**

1. `PromotionWindow` không gọi `Instant.now()`; nó có phương thức `statusAt(Instant)` thuần, dễ kiểm tra biên.
2. `PromotionService` nhận `Clock` từ constructor và lấy **một** `Instant` cho mỗi quyết định.
3. `TimeRuleDemo.main` là composition root minh họa, lựa chọn `Clock.fixed` để kết quả không thay đổi theo ngày chạy.
4. `BusinessCalendar` tách riêng `ZoneId` nghiệp vụ để tránh phụ thuộc ngầm vào múi giờ mặc định của máy chạy.
5. Không có database, mạng hay DI container: bài tập tập trung vào mô hình nguồn thời gian như một dependency.

### 4.1. Cấu hình production sẽ khác ở đâu?

Với ứng dụng thật, composition root thường tạo:

```java
// Minh họa một phần bootstrap; các class đã có ở mục 4.
Clock productionClock = Clock.systemUTC();
PromotionService service = new PromotionService(productionClock);

// Zone dùng cho tính ngày nghiệp vụ có thể là cấu hình đã kiểm tra.
BusinessCalendar calendar = new BusinessCalendar(
        productionClock, ZoneId.of("Asia/Ho_Chi_Minh"));
```

`Clock.systemUTC()` cho một nguồn thời gian thực theo UTC. Nó **không làm thời gian tuyệt đối “chính xác tuyệt đối”**: độ lệch đồng hồ hệ điều hành, đồng bộ NTP, điều chỉnh clock và latency vẫn có thể ảnh hưởng hành vi. Nhưng việc lắp ghép được tập trung và có thể thay thế nguồn thời gian khi kiểm thử.

**Không nên dùng `Clock.systemDefaultZone()` chỉ vì tiện** nếu quy tắc không thực sự muốn phụ thuộc múi giờ môi trường chạy. Chuyển máy chủ từ múi giờ này sang múi giờ khác có thể đổi ngày nghiệp vụ mà không có thay đổi code.

## 5. Bảng ca kiểm thử ranh giới

Với `startsAt = 08:00:00Z` và `endsAt = 09:00:00Z`, ta cần xác minh ít nhất những thời điểm:

| Thời điểm UTC ngày 18/11/2026 | Trạng thái mong đợi | Giải thích |
| --- | --- | --- |
| `07:59:59.999999999Z` | `UPCOMING` | Sớm hơn đúng 1 nano-giây so với bắt đầu. |
| `08:00:00Z` | `ACTIVE` | Đúng mốc bắt đầu, **bao gồm**. |
| `08:30:00Z` | `ACTIVE` | Nằm giữa cửa sổ hiệu lực. |
| `08:59:59.999999999Z` | `ACTIVE` | Sớm hơn đúng 1 nano-giây so với kết thúc. |
| `09:00:00Z` | `EXPIRED` | Đúng mốc kết thúc, **không bao gồm**. |
| `09:00:00.000000001Z` | `EXPIRED` | Muộn hơn mốc kết thúc. |

**Tại sao kiểm thử đúng mốc quan trọng?** Lỗi phổ biến là dùng `now.isAfter(startsAt)`, vô tình loại cả mốc bắt đầu, hoặc dùng `!now.isAfter(endsAt)`, vô tình chấp nhận mốc kết thúc. Chỉ test tại 08:30 sẽ không phát hiện được những sai lệch này.

Test không cần chạy đúng vào ngày 18/11/2026. Ta **truyền clock cố định** với timestamp muốn kiểm tra, nên test chạy được ở bất kỳ thời điểm nào và trên máy có timezone khác nhau.

## 6. Bài kiểm thử Java thuần không cần `sleep` hoặc mock static

Tạo file `TimeRuleTest.java` cùng thư mục với `TimeRuleDemo.java`:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Objects;

// Spy clock minh họa: đếm số lần service yêu cầu Instant.
final class CountingClock extends Clock {
    private final Clock delegate;
    int instantCalls;

    CountingClock(Clock delegate) {
        this.delegate = Objects.requireNonNull(delegate, "delegate");
    }

    @Override
    public ZoneId getZone() {
        return delegate.getZone();
    }

    @Override
    public Clock withZone(ZoneId zone) {
        return new CountingClock(delegate.withZone(zone));
    }

    @Override
    public Instant instant() {
        instantCalls++;
        return delegate.instant();
    }
}

public class TimeRuleTest {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static Clock fixedAt(String timestamp) {
        return Clock.fixed(Instant.parse(timestamp), ZoneOffset.UTC);
    }

    static void expectStatus(PromotionWindow window,
                             String timestamp,
                             PromotionStatus expected) {
        PromotionService service = new PromotionService(
                fixedAt(timestamp));
        PromotionStatus actual = service.evaluate(window);
        check(actual == expected,
                "Sai tại " + timestamp + ": " + actual);
    }

    static void boundaryTests() {
        PromotionWindow window = new PromotionWindow(
                "NOV2026",
                Instant.parse("2026-11-18T08:00:00Z"),
                Instant.parse("2026-11-18T09:00:00Z"));

        expectStatus(window,
                "2026-11-18T07:59:59.999999999Z",
                PromotionStatus.UPCOMING);
        expectStatus(window,
                "2026-11-18T08:00:00Z",
                PromotionStatus.ACTIVE);
        expectStatus(window,
                "2026-11-18T08:30:00Z",
                PromotionStatus.ACTIVE);
        expectStatus(window,
                "2026-11-18T08:59:59.999999999Z",
                PromotionStatus.ACTIVE);
        expectStatus(window,
                "2026-11-18T09:00:00Z",
                PromotionStatus.EXPIRED);
        expectStatus(window,
                "2026-11-18T09:00:00.000000001Z",
                PromotionStatus.EXPIRED);

        boolean invalidWindowRejected = false;
        Instant sameTime = Instant.parse("2026-11-18T08:00:00Z");
        try {
            new PromotionWindow("INVALID", sameTime, sameTime);
        } catch (IllegalArgumentException expected) {
            invalidWindowRejected = true;
        }
        check(invalidWindowRejected,
                "Cửa sổ rỗng phải bị từ chối");

        System.out.println("BOUNDARIES PASS");
    }

    static void offsetAndIsolationTests() {
        Clock base = fixedAt("2026-11-18T08:30:00Z");
        Clock shifted = Clock.offset(base, Duration.ofMinutes(45));

        PromotionWindow window = new PromotionWindow(
                "NOV2026",
                Instant.parse("2026-11-18T08:00:00Z"),
                Instant.parse("2026-11-18T09:00:00Z"));

        PromotionService serviceA = new PromotionService(base);
        PromotionService serviceB = new PromotionService(shifted);

        check(serviceA.evaluate(window) == PromotionStatus.ACTIVE,
                "Clock nền phải còn trong khoảng hiệu lực");
        check(serviceB.evaluate(window) == PromotionStatus.EXPIRED,
                "Clock offset phải vượt mốc hết hạn");

        // Hai service không can thiệp vào đồng hồ của nhau.
        check(serviceA.evaluate(window) == PromotionStatus.ACTIVE,
                "Clock đã bị ảnh hưởng bởi service khác");

        // withZone không đổi Instant, chỉ đổi zone của clock.
        Clock vietnamZone = base.withZone(
                ZoneId.of("Asia/Ho_Chi_Minh"));
        check(new PromotionService(vietnamZone).evaluate(window)
                        == PromotionStatus.ACTIVE,
                "Status theo Instant không nên đổi vì timezone");

        System.out.println("OFFSET PASS");
    }

    static void calendarTests() {
        Clock fixed = fixedAt("2026-11-18T17:30:00Z");

        LocalDate dateUtc = new BusinessCalendar(
                fixed, ZoneOffset.UTC).businessDate();

        LocalDate dateVn = new BusinessCalendar(
                fixed, ZoneId.of("Asia/Ho_Chi_Minh"))
                .businessDate();

        check(LocalDate.of(2026, 11, 18).equals(dateUtc),
                "Ngày UTC không đúng");
        check(LocalDate.of(2026, 11, 19).equals(dateVn),
                "Ngày tại Việt Nam không đúng");

        System.out.println("CALENDAR PASS");
    }

    static void clockUsageTests() {
        CountingClock spy = new CountingClock(
                fixedAt("2026-11-18T08:30:00Z"));
        PromotionService service = new PromotionService(spy);

        check(spy.instantCalls == 0,
                "Constructor không nên đọc đồng hồ");

        PromotionWindow window = new PromotionWindow(
                "NOV2026",
                Instant.parse("2026-11-18T08:00:00Z"),
                Instant.parse("2026-11-18T09:00:00Z"));

        check(service.evaluate(window) == PromotionStatus.ACTIVE,
                "Sai trạng thái tại thời điểm cố định");
        check(spy.instantCalls == 1,
                "Một phép đánh giá chỉ nên lấy một snapshot giờ");

        boolean missingClockRejected = false;
        try {
            new PromotionService(null);
        } catch (NullPointerException expected) {
            missingClockRejected = true;
        }
        check(missingClockRejected,
                "Không từ chối Clock null");

        System.out.println("CLOCK USAGE PASS");
    }

    public static void main(String[] args) {
        boundaryTests();
        offsetAndIsolationTests();
        calendarTests();
        clockUsageTests();
        System.out.println("ALL PASS");
    }
}
```

Biên dịch và chạy:

```bash
javac TimeRuleDemo.java TimeRuleTest.java
java TimeRuleTest
```

Đầu ra dự kiến:

```text
BOUNDARIES PASS
OFFSET PASS
CALENDAR PASS
CLOCK USAGE PASS
ALL PASS
```

### 6.1. Bài test chứng minh gì?

- **Kiểm thử biên:** cả hai đầu khoảng `[startsAt, endsAt)` đều có hành vi được xác định và kiểm tra tại mức nano-giây.
- **Tính xác định:** `Clock.fixed` luôn trả cùng `Instant`, không phụ thuộc ngày chạy và không cần `Thread.sleep`.
- **Mô phỏng thời gian tiến tới:** `Clock.offset` giúp thử một thời điểm cách đồng hồ gốc 45 phút mà không sửa thời gian hệ điều hành.
- **Tách biệt graph:** hai service nhận hai clock khác nhau và cho hai kết quả khác nhau mà không tác động qua trạng thái global.
- **Timezone:** một `Instant` có thể ứng với hai `LocalDate` khác nhau theo zone nghiệp vụ, nhưng trạng thái dựa trên `Instant` không đổi khi chỉ thay zone.
- **Số lần đọc thời gian:** spy `CountingClock` chứng minh constructor không cần đọc giờ và mỗi lần đánh giá chỉ cần một snapshot.
- **Fail-fast:** thiếu dependency bắt buộc bị phát hiện ngay khi tạo service.

Đây là **unit test cho quy tắc thời gian và cách dùng dependency**, không chứng minh hệ thống thực chạy job đúng lịch hoặc đồng hồ máy chủ không sai. Những phần đó cần kiểm thử tích hợp và giám sát vận hành riêng.

## 7. Tại sao nên lấy `now` một lần cho mỗi quyết định?

Một anti-pattern khác là lấy nhiều timestamp ở các nhánh của cùng một quyết định:

```java
// Không nên đọc hai thời điểm khác nhau cho một invariant.
if (!clock.instant().isBefore(windowStarts)
        && clock.instant().isBefore(windowEnds)) {
    // ...
}
```

Hai lần đọc có thể nằm ở hai phía của deadline. Nếu clock thực bị điều chỉnh giữa hai lần hoặc phép tính phức tạp kéo dài, logic có thể đang so sánh **hai trạng thái thời gian khác nhau**. Với những quyết định cần nhất quán, hãy chụp một snapshot:

```java
Instant now = clock.instant();

if (!now.isBefore(windowStarts)
        && now.isBefore(windowEnds)) {
    // ...
}
```

Ngoài ra, timestamp được ghi vào một event nên có ý nghĩa rõ: thời điểm **ra quyết định**, thời điểm **nhận request**, hay thời điểm **lưu dữ liệu thành công**? Chúng có thể khác nhau. Không nên ép tất cả dùng cùng giá trị nếu hợp đồng thực sự cần đo các mốc khác nhau; hãy đặt tên rõ và tách chúng thành các sự kiện theo vòng đời.

### 7.1. Tạo đối tượng không nên tự đọc đồng hồ khi không cần

Trong demo, `PromotionService` chỉ giữ `Clock` ở constructor. Điều đó có nghĩa bạn có thể tạo service tại 07:00 rồi đánh giá khuyến mãi vào 08:30 đúng theo thời gian lúc gọi `evaluate`. Nếu constructor lưu `Instant now = clock.instant()` rồi tái sử dụng cho mọi request, một application-scoped service có thể **mãi mãi quyết định theo giờ khởi động**.

Chỉ lấy snapshot ở constructor nếu chính đối tượng biểu diễn một **ảnh chụp tại thời điểm tạo** và đó là hợp đồng nghiệp vụ. Nếu service cần giờ hiện hành cho từng thao tác, lấy giờ trong thao tác.

## 8. `Clock.fixed`, `Clock.offset`, `Clock.tick` và clock thật

| API | Đặc tính | Tình huống |
| --- | --- | --- |
| `Clock.systemUTC()` | Nguồn giờ hệ thống với zone UTC. | Composition root production cho quy tắc dựa trên `Instant`. |
| `Clock.system(zone)` | Giờ hệ thống với `ZoneId` chỉ định. | Ứng dụng làm việc với ngày/giờ địa phương có zone rõ. |
| `Clock.fixed(instant, zone)` | Luôn trả một `Instant` cố định. | Test mốc thời gian và trường hợp biên. |
| `Clock.offset(base, duration)` | Lấy giá trị của clock gốc rồi dịch theo khoảng thời gian. | Test trạng thái trước/sau một thời điểm; có thể dùng với clock cố định để được kết quả xác định. |
| `Clock.tick(base, duration)` | Làm tròn về các nấc thời gian xác định; có thể cache để tối ưu. | Mô phỏng độ phân giải thấp hoặc ứng dụng không cần thay đổi theo từng nano-giây. |

**Đừng dùng `Clock.tick` làm cơ chế đảm bảo job chạy đúng nấc.** Nó chỉ ảnh hưởng timestamp được trả khi đọc, không tự lịch trình thực thi. Với `Clock.offset(Clock.systemUTC(), duration)`, kết quả vẫn **thay đổi theo thời gian thật**; muốn test hoàn toàn xác định, hãy offset trên một clock fixed hoặc fake được điều khiển.

### 8.1. Có cần viết `FakeClock` riêng?

Đối với phần lớn **test quy tắc tại một thời điểm**, `Clock.fixed` đã đủ. Khi use case cần quan sát **nhiều bước với thời gian tiến dần** trong cùng một luồng kiểm thử, có thể viết một `MutableClock` kiểm soát được; nhưng khi đó cần đặc tả concurrency và vùng sở hữu của clock.

Ví dụ phác thảo minh họa (chạy tuần tự):

```java
// Đoạn minh họa triển khai một Clock thay đổi được.
final class MutableClock extends Clock {
    private Instant now;
    private final ZoneId zone;

    MutableClock(Instant initial, ZoneId zone) {
        this.now = Objects.requireNonNull(initial);
        this.zone = Objects.requireNonNull(zone);
    }

    void advance(Duration delta) {
        now = now.plus(Objects.requireNonNull(delta));
    }

    @Override
    public Instant instant() {
        return now;
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId newZone) {
        return new MutableClock(now, newZone);
    }
}
```

Đoạn này là **ví dụ code đặt trong ngữ cảnh có các import `java.time` và `java.util.Objects` ở trên**, không phải một file độc lập. `withZone` tạo clock mới với snapshot hiện tại, nên **không chia sẻ các lần advance sau đó**; nếu ứng dụng cần hai view cùng tiến thời gian, hãy thiết kế trạng thái chia sẻ và đồng bộ hóa rõ ràng.

**Không dùng nguyên `MutableClock` đơn luồng này làm singleton cho test song song.** Một test thay giờ có thể làm test khác đổi kết quả. Khởi tạo clock riêng cho từng test, hoặc dùng trạng thái immutable/fixed khi có thể.

## 9. Đồng hồ lịch, múi giờ và giờ mùa hè (DST)

Không phải mọi quy tắc thời gian đều nên dùng `Instant` trực tiếp. Có hai nhóm phổ biến:

### 9.1. Thời hạn tuyệt đối

Ví dụ: một token hết hạn tại `2026-11-18T09:00:00Z`. Trong trường hợp này, `Instant` phù hợp vì biểu diễn một thời điểm duy nhất trên toàn cầu.

```java
Instant now = clock.instant();
boolean expired = !now.isBefore(expiresAt);
```

Quy tắc này không phụ thuộc vào múi giờ hiển thị. Thay zone của clock mà giữ nguyên `Instant` không làm thay kết quả.

### 9.2. Quy tắc theo ngày địa phương

Ví dụ: “giảm giá cho các đơn được tạo trong ngày 19/11 theo giờ Việt Nam”. Quy tắc dùng `LocalDate` theo `ZoneId`:

```java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate today = clock.instant()
        .atZone(businessZone)
        .toLocalDate();

boolean specialDay = today.equals(LocalDate.of(2026, 11, 19));
```

Dùng `ZoneId` có ý nghĩa thay vì “cộng cứng 7 giờ” để mô tả timezone nghiệp vụ. Với khu vực có thay đổi DST hoặc quy tắc múi giờ theo lịch sử, phép đổi **ngày-giờ địa phương sang Instant** phải tuân theo quy tắc của zone. Một `LocalDateTime` tự nó **không xác định duy nhất một Instant** vào các thời điểm địa phương bị lặp hoặc không tồn tại do DST.

**Ví dụ cảnh báo:** “ngày mai cùng giờ địa phương” có thể khác “sau đúng 24 giờ” tại vùng có DST. `plusDays(1)` trên `ZonedDateTime` và `plus(Duration.ofHours(24))` không phải luôn cùng ý nghĩa. Phải dùng cách tương ứng với hợp đồng nghiệp vụ.

### 9.3. Mô hình “hết ngày” cho đúng

Thay vì đặt `23:59:59.999` rồi đoán đơn vị chính xác của dữ liệu, có thể dùng mốc bắt đầu ngày kế tiếp **không bao gồm**:

```java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

LocalDate lastEligibleDay = LocalDate.of(2026, 11, 19);
Instant endExclusive = lastEligibleDay.plusDays(1)
        .atStartOfDay(businessZone)
        .toInstant();

boolean stillEligible = clock.instant().isBefore(endExclusive);
```

Cách này biểu diễn quy tắc theo lịch địa phương rồi đổi sang thời điểm tuyệt đối. Nó cũng tránh hard-code số mili-giây tối đa của một ngày. Khi vùng có DST hoặc lịch thay đổi, `atStartOfDay(zone)` sử dụng quy tắc zone để chọn thời điểm đầu ngày hợp lệ.

### 9.4. Tránh lấy timezone mặc định của JVM một cách ngầm

`LocalDate.now()` hoặc `ZonedDateTime.now()` không truyền `Clock` sẽ lấy nguồn thời gian hệ thống mặc định. Test chạy trên CI ở UTC có thể khác máy cá nhân ở châu Á. Khi ngày địa phương là một phần của quy tắc, truyền **`Clock` và `ZoneId`** hoặc một `Clock` đã gắn đúng zone ở composition root.

## 10. `Clock` không phải đồng hồ đo thời gian trôi đơn điệu

Đây là ranh giới kỹ thuật rất quan trọng.

`Clock.instant()` cung cấp **thời gian lịch**: dùng cho ngày, mốc hết hạn, timestamp sự kiện và so sánh với deadline theo UTC. Đồng hồ lịch trên máy có thể bị điều chỉnh bởi hệ điều hành, đồng bộ thời gian hoặc thao tác quản trị; nó **không phải nguồn monotonic**.

Với bài toán **đo thời lượng thực thi**, ta thường dùng một nguồn đo thời gian trôi như `System.nanoTime()`:

```java
long started = System.nanoTime();

performOperation();

long elapsedNanos = System.nanoTime() - started;
```

`performOperation()` là lời gọi giả định. `nanoTime` không cung cấp mốc thời gian lịch và **không nên chuyển trực tiếp thành `Instant`**. Giá trị này thích hợp để đo khoảng thời gian tương đối trong cùng runtime, không để ghi timestamp vào database hay kiểm tra khuyến mãi hết hạn lúc 09:00 UTC.

Nếu phần đo elapsed time cũng cần test xác định, có thể định nghĩa một **`Ticker`/monotonic time source** riêng (ví dụ interface trả `long` nanosecond tương đối), rồi inject nó. Đừng cố dùng `Clock.fixed` để kiểm tra thuật toán đo elapsed time vì clock fixed không tiến lên.

### 10.1. Timeout và retry có thêm phụ thuộc nào?

Một client được cấu hình timeout 2 giây không tự chạy timeout chỉ vì `Clock.instant()` trả thời điểm sau 2 giây. Muốn kiểm thử timeout/retry **không chờ thật**, thường cần điều khiển thêm scheduler, timer hoặc executor.

```text
Hỏi giờ hiện tại         -> Clock
Đo thời lượng trôi       -> nguồn monotonic / Ticker
Chạy công việc sau 2 giây -> Scheduler / Timer / Executor
```

Mỗi abstraction có trách nhiệm khác nhau. Composition root có thể lắp từng thành phần phù hợp, còn unit test thay riêng phần mà nó cần điều khiển.

## 11. Những lỗi thiết kế và test thường gặp

### 11.1. Dùng `Thread.sleep` để chờ thời điểm hết hạn

```java
// Không nên kiểm tra quy tắc giờ bằng cách chờ thật.
Thread.sleep(1_000);
assertTrue(service.expired());
```

Test này chậm, phụ thuộc scheduler và có thể sai ở môi trường CI tải cao. Với quy tắc dựa trên `Clock`, hãy inject `Clock.fixed` ở **sau mốc hết hạn** và kiểm tra ngay.

### 11.2. So sánh với ngày chạy test

```java
// Có thể sai khi test chạy gần nửa đêm hoặc khác timezone.
LocalDate today = LocalDate.now();
```

Không tạo dữ liệu test dựa trên `today` nếu chính mục tiêu là kiểm tra ngày cụ thể. Dùng mốc cố định có ý nghĩa trong hợp đồng.

### 11.3. Mock static `Instant.now()` cho mọi bài test

Dù một thư viện có thể thay cách trả về của static API, cách đó thường tăng coupling với cơ chế mock, phạm vi ảnh hưởng và cleanup. Inject `Clock` giúp dependency của service **được công bố tường minh**, khiến từng bài test có nguồn thời gian riêng. Không cần thêm một interface `ClockProvider` chỉ để bao bọc lại `Clock` nếu API chuẩn đã đủ.

### 11.4. Lấy giờ lúc constructor chạy rồi giữ mãi

```java
// Sai nếu service phải đánh giá theo giờ của mỗi request.
final class BadPromotionService {
    private final Instant startupTime;

    BadPromotionService(Clock clock) {
        startupTime = clock.instant();
    }

    // Các quyết định sau sẽ mãi dùng giờ khởi tạo.
}
```

Đây là một lỗi vòng đời: inject `Clock` rồi nhưng dùng nó sai thời điểm. Nếu service được dùng chung suốt ứng dụng, `startupTime` không phải “hiện tại” cho mọi request.

### 11.5. Dùng `LocalDateTime` không có timezone để biểu diễn expiry toàn cục

Khi timestamp được lưu hoặc trao đổi giữa các hệ thống, `LocalDateTime` thiếu zone/offset có thể gây hiểu nhầm. Dùng `Instant` cho mốc tuyệt đối hoặc `ZonedDateTime`/`OffsetDateTime` khi semantics cần zone/offset. Chỉ lưu `LocalDateTime` khi nghiệp vụ thật sự nói về thời gian địa phương chưa gắn một instant cụ thể.

### 11.6. Dùng clock fixed cho integration test dựa trên scheduler thật

Một service nhận `Clock.fixed` có thể đánh giá đúng thời hạn, nhưng scheduler của framework vẫn dựa trên đồng hồ thực. Nếu integration test mong scheduler chạy, phải có cách kích hoạt và kiểm soát scheduler, không chỉ thay clock của use case.

### 11.7. Dùng clock dùng chung có thể thay đổi giữa các test

Một `MutableClock` static được nhiều test chỉnh giờ làm test phụ thuộc thứ tự chạy. Mỗi test nên tạo clock hoặc object graph mới và không giữ trạng thái cross-test.

### 11.8. Bỏ qua lệch giờ giữa các máy chủ

`Clock.systemUTC()` không đảm bảo hai JVM trên hai máy có cùng giờ chính xác đến nano-giây. Quy tắc hết hạn quan trọng còn chịu ảnh hưởng của đồng bộ thời gian, độ trễ, kiểm chứng ở phía server có thẩm quyền và cách phát hành token/deadline. Trong hệ thống phân tán, có thể cần chính sách dung sai clock skew được xác định rõ, thay vì tự cộng một khoảng tùy tiện ở mọi service.

## 12. Khi kết hợp với repository hoặc sự kiện nghiệp vụ

Một use case thực tế thường không chỉ tính trạng thái mà còn **ghi dữ liệu**. Khi đó có thể inject đồng thời repository và clock:

```java
// Minh họa API; các type phụ thuộc là hợp đồng giả định.
final class BookingService {
    private final Clock clock;
    private final BookingRepository repository;

    BookingService(Clock clock, BookingRepository repository) {
        this.clock = Objects.requireNonNull(clock, "clock");
        this.repository = Objects.requireNonNull(
                repository, "repository");
    }

    void requestCancellation(String bookingId) {
        Instant now = clock.instant();

        Booking booking = repository.find(bookingId);
        if (!now.isBefore(booking.cancellationDeadline())) {
            throw new IllegalStateException(
                    "CANCELLATION_DEADLINE_PASSED");
        }

        repository.saveCancellation(bookingId, now);
    }
}
```

Đoạn này **không phải chương trình độc lập** vì `BookingRepository` và `Booking` chưa được định nghĩa; nó minh họa sự kết hợp dependency. Unit test dùng fake repository và `Clock.fixed` có thể xác minh **được/hết quyền hủy** mà không gọi database thật.

**Cần xem xét race condition:** thời gian và trạng thái trong database có thể thay đổi giữa lúc đọc booking và lúc ghi cancellation. Nếu điều kiện hết hạn là quy tắc bảo toàn dữ liệu bắt buộc, hệ thống thật có thể cần kiểm tra **trong transaction hoặc câu lệnh cập nhật có điều kiện**, dùng nguồn thời gian và mức nhất quán phù hợp. Clock injection chỉ làm quyết định thời gian **kiểm thử được**, không tự đảm bảo transaction hoặc đồng bộ với thời gian của database.

### 12.1. Event timestamp nên lấy ở đâu?

Nếu một service ghi `PromotionEvaluatedEvent`, hãy xác định timestamp là:

- Thời điểm **nhận request**;
- Thời điểm **đánh giá quy tắc**;
- Thời điểm **ghi event vào storage**; hoặc
- Thời điểm **event được publish**.

Chúng là bốn thời điểm có thể khác nhau. Đưa `Clock` vào đúng thành phần sở hữu ngữ nghĩa timestamp, tránh để mỗi adapter tự sinh thời gian mà code nghiệp vụ tưởng chúng giống nhau.

## 13. Quy trình thực hành khi đưa Clock vào code cũ

Một lộ trình refactor an toàn:

1. **Tìm điểm đọc giờ:** `Instant.now()`, `LocalDate.now()`, `ZonedDateTime.now()`, `System.currentTimeMillis()`, `new Date()` và cách tính hạn trong code.
2. **Phân loại theo ngữ nghĩa:** mốc tuyệt đối, ngày địa phương, thời lượng trôi, lịch thực thi hay timeout? Không ép tất cả cùng dùng `Clock`.
3. **Định nghĩa hợp đồng biên:** `>= startsAt`, `< endsAt`, ngày theo zone nào, thời điểm làm tròn ra sao? Ghi vào test.
4. **Inject `Clock` cho nơi thật sự cần giờ hiện tại** và chuyển phép tính có thể thuần sang method nhận `Instant` nếu hợp lý.
5. **Lắp tại composition root:** `Clock.systemUTC()` cho production và `Clock.fixed(...)` trong test; truyền `ZoneId` nghiệp vụ khi cần.
6. **Viết test cố định:** trước, đúng tại, sau từng mốc; kiểm tra giá trị không hợp lệ và hành vi qua nhiều lần gọi.
7. **Kiểm soát đường I/O:** nếu sử dụng repository, sự kiện hoặc job, bổ sung fake/spy phù hợp và test tích hợp cho adapter thật.
8. **Rà soát concurrency/lifecycle:** tránh clock mutable chia sẻ không an toàn, state theo request bị giữ trong singleton, scheduler và clock khác nhau.
9. **Đo và quan sát production:** lỗi do clock skew, timezone, deadline và dữ liệu ngày tháng cần có cách theo dõi phù hợp, không log thông tin nhạy cảm.

**DI container xuất hiện khi nào?** Khi ứng dụng lớn, framework có thể cấu hình một bean `Clock` dùng chung và inject nó vào các service. Điều này giảm mã wiring, nhưng không thay thế việc chọn đúng `Instant`/`LocalDate`, đúng zone, đúng ranh giới và test thực tế. Học cách truyền `Clock` thủ công bằng Java thuần giúp hiểu các quyết định trước khi tự động hóa.

## 14. Bài tập thực hành mở rộng

**Bối cảnh:** hệ thống cho phép hủy lịch đặt phòng tới trước 24 giờ so với thời điểm nhận phòng. Lịch nhận phòng được lưu dưới dạng `Instant`. Hệ thống cũng gửi nhắc nhở vào **ngày lịch trước ngày check-in** theo múi giờ của từng địa điểm.

Hãy thực hiện:

1. **Viết hợp đồng deadline:** nếu check-in là `2026-12-10T08:00:00Z`, deadline hủy miễn phí là thời điểm nào? Ngay đúng deadline có được hủy không? Chọn một quy tắc và nêu rõ.
2. **Thiết kế service:** tạo `CancellationPolicy` nhận `Clock` và `Duration cancellationWindow`, kiểm tra constructor và dùng `clock.instant()`.
3. **Kiểm thử biên:** `Clock.fixed` tại 1 nano-giây trước, đúng tại và 1 nano-giây sau deadline; assert kết quả.
4. **Đổi thời gian có kiểm soát:** dùng `Clock.offset` để thử đơn đã qua hạn mà không ngủ chờ.
5. **Kiểm tra timezone:** cùng một `Instant` có thể là hai ngày khác nhau ở `Asia/Ho_Chi_Minh` và `America/New_York`. Tạo `ReminderDayPolicy` dùng `ZoneId` của địa điểm, không dùng timezone mặc định của server.
6. **Phân biệt 24 giờ và một ngày lịch:** khi vùng có DST, tính `checkIn.minus(Duration.ofHours(24))` có tương đương “ngày hôm trước cùng giờ địa phương” không? Giải thích và chọn semantics phù hợp.
7. **Lắp ghép test:** tạo fake `BookingRepository` để kiểm tra khi quá hạn không ghi cancellation; khi đủ điều kiện thì dùng timestamp do clock cung cấp.
8. **Xử lý concurrency:** nếu request tới sát deadline hoặc một admin thay lịch check-in đồng thời, đề xuất nơi kiểm tra điều kiện trong transaction.
9. **Giới hạn của Clock:** nếu muốn tự động gửi reminder đúng giờ, còn cần dependency scheduler nào? Bạn sẽ kiểm thử lịch chạy mà không chờ giờ thật thế nào?
10. **Kiểm thử triển khai:** thiết kế một integration test kiểm tra cách lưu timestamp và timezone trong database và một test dùng zone có DST.

**Gợi ý tự đối chiếu:** với quy tắc “hủy được đến **trước** deadline”, điều kiện là `clock.instant().isBefore(checkIn.minus(Duration.ofHours(24)))`. Nếu hợp đồng cho phép hủy **tại** deadline, phải thay biểu thức và test. Quy tắc “ngày hôm trước” phải nêu zone và semantics lịch; `Duration.ofHours(24)` không luôn tương đương một ngày lịch ở vùng có DST. Fake repository xác minh điều phối nghiệp vụ, nhưng không thay kiểm thử transaction/integration thật.

## 15. Checklist cuối bài

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Service còn gọi `Instant.now()` hoặc `LocalDate.now()` không? | Nguồn thời gian được truyền tường minh khi cần test hoặc thay đổi môi trường. |
| Có ghi rõ khoảng hiệu lực và tính bao gồm/không bao gồm? | Có bảng ca kiểm thử trước/tại/sau từng mốc. |
| Dùng loại thời gian phù hợp? | `Instant` cho timestamp tuyệt đối; `LocalDate` + zone cho ngày lịch; `Duration` cho khoảng. |
| Có lấy thời gian nhất quán trong một quyết định? | Dùng một snapshot `clock.instant()` khi quy tắc cần cùng thời điểm. |
| Unit test có dùng `sleep` hoặc dựa ngày hiện tại? | Dùng `Clock.fixed`, `Clock.offset` hoặc fake theo mục đích; chạy nhanh và xác định. |
| Timezone có được cấu hình rõ? | Không phụ thuộc ngầm vào timezone của JVM/CI. |
| Có nhầm Clock với scheduler hoặc ticker? | Biết phân biệt lịch, elapsed time và thời điểm kích hoạt công việc. |
| Scope và concurrency có được kiểm soát? | Clock mutable không chia sẻ bừa bãi; state theo request không bị giữ lâu ngoài scope. |
| Có test tích hợp cho ranh giới ngoài không? | Kiểm tra database, timezone, deadline và scheduler theo hành vi thật khi cần. |

**Điểm cần nhớ:** Thời gian hiện tại là một **dependency có thể inject**. Dùng `java.time.Clock` giúp chuyển quyền chọn nguồn giờ về composition root, kiểm thử các quy tắc theo mốc bằng Java thuần và loại bỏ sự phụ thuộc vào `Thread.sleep` hay đồng hồ thật. Hãy làm rõ ranh giới hiệu lực, múi giờ và ý nghĩa timestamp; sau đó mới kết hợp với repository, lifecycle và DI container để giải quyết những bài toán lớn hơn.
