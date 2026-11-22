# Kiểm tra thời gian, số thập phân và sai số được chấp nhận

Trong kiểm thử Java/Spring Boot, **một phép so sánh đúng phải phản ánh ý nghĩa của dữ liệu**. Một thời điểm hết hạn ở đúng ranh giới có thể cần so sánh chính xác đến nano giây; một kết quả tính toán `double` có thể chênh lệch rất nhỏ do biểu diễn nhị phân; còn số tiền thường phải được tính và làm tròn bằng `BigDecimal` theo một quy tắc rõ ràng. Cố dùng một kiểu `assertEquals(expected, actual)` cho mọi trường hợp dễ tạo ra test đỏ sai lý do hoặc, nguy hiểm hơn, test xanh dù nghiệp vụ tính sai.

Bài này giải thích các cách dùng **JUnit Jupiter assertions** để kiểm tra thời gian, số thập phân và **tolerance/delta** (sai số được chấp nhận); cách loại bỏ phụ thuộc vào đồng hồ thật; phân biệt **sai số dữ liệu** với **giới hạn thời gian chạy**; và cách chọn mức chính xác phù hợp khi kiểm thử service, persistence, HTTP trong Spring Boot.

## 1. Ba câu hỏi trước mỗi assertion

Trước khi chọn assertion, trả lời:

1. **Đại lượng đang được so sánh là gì?** Thời điểm (`Instant`), ngày (`LocalDate`), khoảng thời gian (`Duration`), giá trị đo (`double`), hay tiền tệ (`BigDecimal`)?
2. **Hợp đồng yêu cầu chính xác đến đâu?** Chính xác tuyệt đối, đúng sau khi chuẩn hóa đến mili giây, hay nằm trong khoảng sai số có định nghĩa?
3. **Nguồn bất định nằm ở đâu?** Đồng hồ hệ thống, múi giờ/DST, database lưu timestamp độ phân giải thấp, rounding, binary floating point, network/threads hay tải CPU?

| Loại kết quả | Assertion thường phù hợp | Lý do |
| --- | --- | --- |
| Hai `Instant` phải giống hệt nhau | `assertEquals(expected, actual)` | API biểu diễn cùng thời điểm tuyệt đối; không cần delta nếu clock được kiểm soát |
| Mốc thời gian phải trước/sau deadline | `assertTrue(actual.isBefore(deadline))` hoặc `assertFalse(...)` | Kiểm tra quan hệ thứ tự theo quy tắc nghiệp vụ |
| Thời điểm đo được lệch tối đa 50 ms | `assertTrue(Duration.between(expected, actual).abs().compareTo(tolerance) <= 0)` | Định nghĩa tolerance theo đơn vị thời gian |
| Kết quả tính toán `double` | `assertEquals(expected, actual, delta)` | Chấp nhận sai số tuyệt đối có chủ đích |
| Số tiền có scale/rounding bắt buộc | `assertEquals(new BigDecimal("..."), actual)` | So cả giá trị lẫn scale |
| Hai `BigDecimal` chỉ cần bằng nhau về số học | `assertEquals(0, expected.compareTo(actual))` | Bỏ qua khác biệt scale nhưng vẫn so giá trị |
| Thao tác không được chạy quá ngân sách | `assertTimeout(Duration, executable)` | Đo thời lượng chạy, không phải so timestamp nghiệp vụ |

**Không chọn delta chỉ để làm test xanh.** Sai số phải đến từ ý nghĩa miền nghiệp vụ hoặc độ chính xác của hệ thống; test kiểm tra một giá trị tiền tệ sai 1 đồng không nên tự cho phép lệch 1 đồng nếu yêu cầu đòi kết quả chính xác.

## 2. Tại sao số thập phân kiểu double có thể không bằng nhau tuyệt đối?

`float` và `double` dùng biểu diễn dấu phẩy động **nhị phân**. Nhiều phân số thập phân, như `0.1` và `0.2`, không có biểu diễn nhị phân hữu hạn. Một phép cộng có thể tạo giá trị gần `0.3` chứ không đúng bằng literal `0.3` sau khi chuyển sang `double`.

Ví dụ Java 17+:

```java
public class FloatingPointDemo {
    public static void main(String[] args) {
        double actual = 0.1 + 0.2;

        System.out.println(actual);
        System.out.println(actual == 0.3);
        System.out.println(Math.abs(0.3 - actual) < 1e-12);
    }
}
```

Chạy:

```bash
javac FloatingPointDemo.java
java FloatingPointDemo
```

Stdout chính xác:

```text
0.30000000000000004
false
true
```

Giải thích:

- `0.1 + 0.2` được lưu thành một `double` hơi lớn hơn giá trị biểu diễn của literal `0.3`.
- Phép `==` trả `false` vì hai giá trị `double` không có cùng bit giá trị.
- Khoảng cách tuyệt đối nhỏ hơn `1e-12`, vì vậy phép kiểm tra tolerance minh họa trả `true`.

**Lưu ý:** số `1e-12` chỉ phù hợp để minh họa phép cộng rất nhỏ trong ví dụ, không phải ngưỡng dùng cho mọi phép đo. Nếu đại lượng là quãng đường tính bằng km, phần trăm, giây hay nhiệt độ, phải chọn tolerance theo **đơn vị và độ chính xác có thể chấp nhận**.

## 3. Dùng assertEquals(expected, actual, delta) trong JUnit Jupiter

Với số thực `double`, JUnit Jupiter có dạng:

```java
assertEquals(expectedDouble, actualDouble, delta);
```

`delta` là **sai số tuyệt đối tối đa**. Về ý nghĩa thông thường, so sánh thành công khi sai khác không vượt quá khoảng cho phép, với quy tắc đặc biệt của JUnit dành cho những giá trị floating point như NaN/Infinity. Không nên hiểu `delta = 0.01` là tự động cho phép lệch **1%**: nó là **0.01 đơn vị đo**.

Ví dụ một phép tính thực:

```java
@Test
void floatingPointSumUsesAJustifiedTolerance() {
    double actual = 0.1 + 0.2;

    assertEquals(0.3, actual, 1e-12);
}
```

Đây là **method bên trong một JUnit test class** với static import `org.junit.jupiter.api.Assertions.assertEquals` và `@Test` từ `org.junit.jupiter.api.Test`; dùng phép toán trực tiếp để dễ quan sát hiện tượng. Bên dưới ta sẽ kiểm tra mã production thực, không chỉ công thức nằm trong test.

Chọn tolerance:

- Nếu yêu cầu là “độ chính xác trong phạm vi 0,01 °C”, `delta = 0.01` có ý nghĩa tuyệt đối với đơn vị °C.
- Nếu yêu cầu là “kết quả phải nằm trong 0,1% giá trị mong đợi”, phải tính **relative tolerance**, không truyền thẳng `0.001` như một delta tuyệt đối.
- Nếu yêu cầu là “giá cuối cùng phải đúng đến 2 chữ số thập phân sau khi làm tròn HALF_UP”, nên dùng `BigDecimal` và so giá trị đã làm tròn theo quy tắc, thay vì cho phép chênh lệch tùy ý.

Với floating point đặc biệt, `NaN` có thể được JUnit xử lý như một giá trị so sánh bằng `NaN` trong các assertion `double`. Vì vậy, nếu miền nghiệp vụ yêu cầu phép đo hợp lệ, hãy **kiểm tra hữu hạn trước**:

```java
assertTrue(Double.isFinite(actual), "Kết quả phải là số hữu hạn");
assertEquals(0.3, actual, 1e-12);
```

Không dùng tolerance rất lớn để che lỗi logic, chẳng hạn expected `0.3` mà actual `0.8` vẫn được cho qua vì `delta = 1.0`. Tolerance cho phép lỗi biểu diễn/đo lường **đã hiểu rõ**, không nới hợp đồng nghiệp vụ.

## 4. Ví dụ đầy đủ: chính sách thời điểm hết hạn, tiền và phép đo

Ta xây một lớp nhỏ có ba trách nhiệm độc lập để minh họa ba kiểu assertion:

1. Một quyền sử dụng **hết hạn ngay khi thời điểm hiện tại lớn hơn hoặc bằng deadline**.
2. Một hóa đơn tính tiền có thuế, làm tròn **2 chữ số thập phân theo HALF_UP**.
3. Một phép đo cộng hai `double`, chấp nhận sai số biểu diễn nhị phân nhưng từ chối input không hữu hạn.

Dự án Spring Boot sử dụng **Java 17+**, JUnit Jupiter và Gradle. Tệp ví dụ:

```text
src/
├── main/java/example/testing/AmountAndTimePolicy.java
├── main/java/example/testing/AmountAndTimeDemo.java
└── test/java/example/testing/AmountAndTimePolicyTest.java
```

### 4.1. Mã production: clock được tiêm từ ngoài

Tạo `src/main/java/example/testing/AmountAndTimePolicy.java`:

```java
package example.testing;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class AmountAndTimePolicy {
    private final Clock clock;

    public AmountAndTimePolicy(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public boolean isExpired(Instant deadline) {
        Objects.requireNonNull(deadline, "deadline");
        return !Instant.now(clock).isBefore(deadline);
    }

    public BigDecimal totalWithTax(
            BigDecimal subtotal, BigDecimal taxRate) {
        Objects.requireNonNull(subtotal, "subtotal");
        Objects.requireNonNull(taxRate, "taxRate");

        if (subtotal.signum() < 0 || taxRate.signum() < 0) {
            throw new IllegalArgumentException(
                    "subtotal and taxRate must be nonnegative");
        }

        return subtotal.multiply(BigDecimal.ONE.add(taxRate))
                .setScale(2, RoundingMode.HALF_UP);
    }

    public double sumMeasurements(double first, double second) {
        if (!Double.isFinite(first) || !Double.isFinite(second)) {
            throw new IllegalArgumentException(
                    "measurements must be finite");
        }
        return first + second;
    }
}
```

Tại sao thiết kế này dễ test?

- `Clock` cho phép ứng dụng dùng đồng hồ thật khi chạy production và dùng thời điểm **cố định** trong test. Chức năng `isExpired` không phụ thuộc ngày/giờ máy chạy test.
- `Instant` biểu diễn một thời điểm tuyệt đối trên trục thời gian; kiểm tra tại ranh giới tránh phụ thuộc múi giờ.
- `BigDecimal` nhận các giá trị thập phân có ý nghĩa nghiệp vụ; hàm nêu rõ thời điểm làm tròn (sau phép nhân) và chế độ làm tròn.
- `sumMeasurements` kiểm tra đầu vào hữu hạn để không coi `NaN` hay Infinity là kết quả đo hợp lệ. Nếu yêu cầu còn đòi kết quả không được overflow thành Infinity, cần kiểm tra **kết quả** sau phép cộng nữa; ví dụ này chỉ minh họa hai input hữu hạn và tổng trong phạm vi thông thường.

### 4.2. Các test JUnit Jupiter runnable

Tạo `src/test/java/example/testing/AmountAndTimePolicyTest.java`:

```java
package example.testing;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AmountAndTimePolicyTest {

    private static final Instant DEADLINE =
            Instant.parse("2026-03-01T12:00:00Z");

    private static AmountAndTimePolicy policyAt(Instant now) {
        Clock fixedClock = Clock.fixed(now, ZoneOffset.UTC);
        return new AmountAndTimePolicy(fixedClock);
    }

    @Test
    void beforeDeadline_isNotExpired() {
        AmountAndTimePolicy policy =
                policyAt(DEADLINE.minusNanos(1));

        assertFalse(policy.isExpired(DEADLINE));
    }

    @Test
    void exactlyAtDeadline_isExpired() {
        AmountAndTimePolicy policy = policyAt(DEADLINE);

        assertTrue(policy.isExpired(DEADLINE));
    }

    @Test
    void afterDeadline_isExpired() {
        AmountAndTimePolicy policy =
                policyAt(DEADLINE.plusNanos(1));

        assertTrue(policy.isExpired(DEADLINE));
    }

    @Test
    void taxUsesExactDecimalRounding() {
        AmountAndTimePolicy policy = policyAt(DEADLINE);

        BigDecimal actual = policy.totalWithTax(
                new BigDecimal("19.99"),
                new BigDecimal("0.10"));

        assertEquals(new BigDecimal("21.99"), actual);
        assertEquals(2, actual.scale());
    }

    @Test
    void doubleSumUsesExplicitTolerance() {
        AmountAndTimePolicy policy = policyAt(DEADLINE);

        double actual = policy.sumMeasurements(0.1, 0.2);

        assertTrue(Double.isFinite(actual));
        assertEquals(0.3, actual, 1e-12);
    }

    @Test
    void invalidMeasurementIsRejected() {
        AmountAndTimePolicy policy = policyAt(DEADLINE);

        assertThrows(IllegalArgumentException.class,
                () -> policy.sumMeasurements(
                        Double.NaN, 0.2));
    }

    @Test
    void decimalNumericEqualityMayDifferFromObjectEquality() {
        BigDecimal oneDecimal = new BigDecimal("1.0");
        BigDecimal twoDecimals = new BigDecimal("1.00");

        assertNotEquals(oneDecimal, twoDecimals);
        assertEquals(0, oneDecimal.compareTo(twoDecimals));
    }
}
```

Có **7 method test**, trong đó ba test đầu chứng minh ranh giới hết hạn **trước/đúng/sau deadline** ở độ phân giải 1 nano giây theo giá trị `Instant` đã cấp qua `Clock.fixed`. Vì thời gian không trôi trong test, các phép kiểm tra đó không bị flakiness do CPU/scheduler.

Trong một dự án Spring Boot/Gradle đã thiết lập plugin và quản lý version dependencies, phần cấu hình liên quan ở `build.gradle` (Groovy DSL):

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **đoạn cấu hình bổ sung**, không phải `build.gradle` độc lập. Chạy:

```bash
./gradlew test --tests example.testing.AmountAndTimePolicyTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.AmountAndTimePolicyTest"
```

**Kỳ vọng:** 7 test pass nếu project có Java 17+ và dependencies phù hợp. Output Gradle/JUnit phụ thuộc cấu hình logging, nên không khẳng định một chuỗi stdout cố định. Test này **không cần** `@SpringBootTest`, datasource hay web server: ba quy tắc được kiểm tra ở ranh giới Java thuần.

### 4.3. Biên dịch và chạy độc lập bằng javac/java

Tạo `src/main/java/example/testing/AmountAndTimeDemo.java`:

```java
package example.testing;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

public class AmountAndTimeDemo {
    public static void main(String[] args) {
        Instant deadline = Instant.parse(
                "2026-03-01T12:00:00Z");

        AmountAndTimePolicy policy = new AmountAndTimePolicy(
                Clock.fixed(deadline, ZoneOffset.UTC));

        System.out.println(policy.isExpired(deadline));
        System.out.println(policy.totalWithTax(
                new BigDecimal("19.99"),
                new BigDecimal("0.10")).toPlainString());
        System.out.println(
                policy.sumMeasurements(0.1, 0.2));
    }
}
```

Chạy tại thư mục gốc project (có JDK):

```bash
javac -d out src/main/java/example/testing/AmountAndTimePolicy.java src/main/java/example/testing/AmountAndTimeDemo.java
java -cp out example.testing.AmountAndTimeDemo
```

Stdout chính xác:

```text
true
21.99
0.30000000000000004
```

`true` cho thấy hợp đồng “hết hạn ngay tại deadline”; `21.99` cho thấy phép nhân thuế được làm tròn; giá trị cuối phơi bày sai số nhị phân của `double`. Lệnh này chỉ chạy demo Java thuần; **các assertion JUnit được chạy bằng Gradle/test runner** ở mục trên.

## 5. Kiểm thử thời điểm với Instant, Clock và Duration

### 5.1. Đúng thời điểm, trước/sau và ranh giới bao gồm hay loại trừ

`Instant` đại diện một điểm trên dòng thời gian, thích hợp cho expiresAt, createdAt, processedAt, scheduledAt nếu hợp đồng quan tâm thời điểm tuyệt đối.

Giả sử mã nghiệp vụ:

```java
return !Instant.now(clock).isBefore(deadline);
```

Nghĩa là **now >= deadline** thì hết hạn. Vì `isBefore` trả false khi hai giá trị bằng nhau, dấu phủ định cho kết quả true tại đúng deadline. Ba test quan trọng nhất:

| now tương đối với deadline | Kỳ vọng isExpired |
| --- | --- |
| `deadline.minusNanos(1)` | `false` |
| `deadline` | `true` |
| `deadline.plusNanos(1)` | `true` |

Nếu nghiệp vụ định nghĩa “chỉ hết hạn **sau** deadline”, điều kiện tương ứng sẽ là `Instant.now(clock).isAfter(deadline)` và test đúng deadline phải kỳ vọng false. Không có một phép so sánh ranh giới đúng cho mọi ứng dụng: **hợp đồng xác định tính bao gồm**.

Để assert thời điểm tuyệt đối:

```java
Instant expected = Instant.parse("2026-03-01T12:00:00Z");
Instant actual = Instant.parse("2026-03-01T12:00:00Z");

assertEquals(expected, actual);
```

Đây là đoạn nằm trong method test; `Instant.equals` so thời điểm đến độ chính xác mà cả hai object biểu diễn. Không cần tự chuyển sang chuỗi nếu mục tiêu là so ý nghĩa thời gian. Nếu API công khai trả **chuỗi ISO-8601 với format cố định**, có thể thêm một test riêng cho format ở ranh giới serializer.

### 5.2. Clock.fixed để loại bỏ thời gian thật

**Không viết test ranh giới kiểu**:

```java
Instant deadline = Instant.now().plusMillis(5);
assertFalse(service.isExpired(deadline));
```

Nếu service chạy chậm, máy đang tải hoặc debugger dừng, 5 ms có thể đã trôi qua trước assertion. Test đỏ ngẫu nhiên dù logic không thay đổi.

Thiết kế tốt hơn: **inject `Clock`**. Production có thể cung cấp:

```java
@Bean
Clock applicationClock() {
    return Clock.systemUTC();
}
```

Đây là **đoạn method cấu hình Spring**, cần nằm trong class `@Configuration`/nơi khai báo bean thích hợp với các import tương ứng; nó không phải file Java độc lập. Test unit tạo `Clock.fixed(...)` và truyền thẳng qua constructor như ví dụ đầy đủ. Khi cần mô phỏng “tiến thêm 1 giây”, dùng một Clock cố định khác:

```java
Instant t0 = Instant.parse("2026-03-01T12:00:00Z");

Clock before = Clock.fixed(
        t0.minusSeconds(1), ZoneOffset.UTC);
Clock after = Clock.fixed(
        t0.plusSeconds(1), ZoneOffset.UTC);
```

Không cần `Thread.sleep`. Nếu đối tượng cần theo dõi thời gian tiến liên tục trong một test duy nhất, có thể sử dụng clock thử nghiệm có thể điều chỉnh (test clock) thay vì chờ đồng hồ thật. Đừng giả định rằng `Clock.fixed` tự thay đổi theo thời gian; nó luôn trả cùng mốc đã cấu hình.

### 5.3. So khoảng thời gian và sai số theo đơn vị

`Duration` biểu diễn khoảng thời gian, thường dùng cho timeout, latency đo được, TTL và thời lượng giữa hai event. Nếu cần xác nhận hai khoảng bằng nhau hoàn toàn:

```java
Duration expected = Duration.ofSeconds(90);
Duration actual = Duration.between(
        Instant.parse("2026-03-01T12:00:00Z"),
        Instant.parse("2026-03-01T12:01:30Z"));

assertEquals(expected, actual);
```

Nếu hợp đồng cho phép thời điểm lệch **tối đa 50 ms**, so sai số bằng chính kiểu `Duration`:

```java
Instant expected = Instant.parse(
        "2026-03-01T12:00:00Z");
Instant actual = expected.plusMillis(35);
Duration tolerance = Duration.ofMillis(50);

Duration difference =
        Duration.between(expected, actual).abs();

assertTrue(difference.compareTo(tolerance) <= 0,
        () -> "Lệch thời gian: " + difference);
```

`Duration.between(expected, actual)` có dấu: âm nếu actual trước expected, dương nếu sau. `abs()` giúp kiểm tra độ lớn sai khác hai phía. `compareTo(...) <= 0` xem **đúng tại biên 50 ms cũng được chấp nhận**. Nếu hợp đồng yêu cầu nhỏ hơn nghiêm ngặt, dùng `< 0`. Những đoạn trên là code **bên trong một test method**, cần imports từ `java.time` và JUnit.

Sai số 50 ms phải được giải thích, chẳng hạn đồng hồ ở hai thành phần có giới hạn đồng bộ đã biết hoặc nguồn đo đã có độ chính xác tương ứng. Với `Clock.fixed` và logic thuần, thường không cần mở cửa sai số 50 ms.

### 5.4. Múi giờ, DST và độ phân giải

- `Instant` biểu diễn thời điểm tuyệt đối; `ZonedDateTime` mang theo múi giờ; `OffsetDateTime` mang offset. Hai giá trị ở múi giờ khác nhau có thể chỉ cùng một thời điểm — khi hợp đồng so **instant**, chuyển sang `toInstant()` rồi so.
- `LocalDate` là **ngày trên lịch**, không phải thời điểm; hữu ích cho sinh nhật, hạn chót theo ngày làm việc. Khi xác định “ngày hôm nay” ở Việt Nam hay UTC, phải cung cấp `ZoneId` chính thức của nghiệp vụ. Không tự suy ra một ngày từ `Instant` mà không biết timezone.
- `LocalDateTime` **không chứa timezone/offset**. Không coi hai giá trị `LocalDateTime` ở hai hệ thống là cùng thời điểm tuyệt đối nếu không có quy tắc múi giờ.
- DST có thể làm một ngày theo lịch dài **23 hoặc 25 giờ**, trong khi `Duration.ofDays(1)` luôn là 24 giờ. Khi quy tắc là “cùng giờ địa phương ngày hôm sau”, hãy dùng mô hình ngày/zone thích hợp; khi là “sau đúng 24 giờ”, dùng `Duration`.
- Persistence/JSON có thể làm tròn hoặc cắt nano giây thành micro/milli giây. Nếu dữ liệu chỉ có độ phân giải millisecond **theo hợp đồng**, có thể chuẩn hóa rõ ràng hai phía bằng `truncatedTo(ChronoUnit.MILLIS)` trước khi so. Đừng cắt độ chính xác chỉ để làm một bug biến mất.

Ví dụ khi contract công khai xác nhận timestamp đến millisecond:

```java
Instant expected = Instant.parse(
        "2026-03-01T12:00:00.123456Z");
Instant received = Instant.parse(
        "2026-03-01T12:00:00.123Z");

assertEquals(
        expected.truncatedTo(ChronoUnit.MILLIS),
        received.truncatedTo(ChronoUnit.MILLIS));
```

Vì timestamp đầu có thêm 456 micro giây và contract chỉ dùng mili giây, cả hai sau chuẩn hóa là `2026-03-01T12:00:00.123Z`. Đoạn test cần import `java.time.temporal.ChronoUnit` và một quy tắc rõ rằng phần vượt millisecond được **cắt**, không phải làm tròn.

## 6. Sai số tuyệt đối, sai số tương đối và số đo gần 0

### 6.1. Absolute tolerance

Với expected `100.0` và actual `100.004` (đơn vị °C hoặc một đại lượng khác), delta tuyệt đối `0.01` cho phép chênh tối đa **0.01 đơn vị**. JUnit:

```java
assertEquals(100.0, 100.004, 0.01);
```

Nếu hợp đồng xác định ngưỡng sai số theo đơn vị đầu ra, cách này rõ và dễ review.

### 6.2. Relative tolerance

Với đại lượng có thể thay đổi từ `0.001` đến `1_000_000`, một ngưỡng tuyệt đối duy nhất có thể quá chặt với số lớn hoặc quá rộng với số nhỏ. Nếu yêu cầu là “sai số tương đối tối đa 0,1%”, mô hình một biến thể thông dụng là:

```text
allowed = max(absoluteFloor,
              relativeRate × max(|expected|, |actual|))
pass khi |actual − expected| ≤ allowed
```

Dùng `absoluteFloor` để tránh ngưỡng bằng 0 khi giá trị xấp xỉ 0. Chọn công thức theo domain; có lĩnh vực dùng mẫu số `|expected|` thay vì max hai phía. Test phải thể hiện **công thức đã được quyết định**, không tự sáng tạo sai số.

Ví dụ **method assertion helper minh họa** dùng trong test class:

```java
static void assertClose(
        double expected,
        double actual,
        double absTolerance,
        double relTolerance) {

    assertTrue(Double.isFinite(expected));
    assertTrue(Double.isFinite(actual));
    assertTrue(absTolerance >= 0 && relTolerance >= 0);

    double scale = Math.max(
            Math.abs(expected), Math.abs(actual));
    double allowed = Math.max(
            absTolerance, relTolerance * scale);

    assertTrue(Math.abs(actual - expected) <= allowed,
            () -> "expected=" + expected
                    + ", actual=" + actual
                    + ", allowed=" + allowed);
}
```

Đoạn helper giả định `expected` và `actual` hữu hạn, tolerance hợp lệ; ở code kiểm thử chuyên sâu, nên còn cân nhắc overflow của phép trừ hoặc phép nhân cho giá trị cực lớn. Với phép đo thông thường, đây là cách đọc được để minh họa **kết hợp sai số tuyệt đối và tương đối**.

**Ví dụ áp dụng:** khi phép tính trả khoảng `1_000_000` và relative tolerance 0,1%, sai số cho phép về tỷ lệ có thể đến khoảng `1_000` (trừ khi contract đặt ngưỡng chặt hơn). Với giá trị gần 0, absolute floor tránh việc tỷ lệ tương đối trở nên vô nghĩa. Nếu bài toán thực tế cần độ chính xác tiền tệ, không dùng công thức relative tolerance này thay phép so `BigDecimal`.

### 6.3. Chọn dữ liệu biên cho tolerance

Với tolerance tuyệt đối 0,01, nên có các trường hợp:

| Case | Expected | Actual | Mục tiêu |
| --- | ---: | ---: | --- |
| Bằng nhau | 10.00 | 10.00 | So chính xác vẫn qua |
| Lệch nhỏ | 10.00 | 10.005 | Qua nếu ngưỡng là 0,01 |
| Lệch rõ | 10.00 | 10.02 | Phải fail |
| Giá trị âm | -10.00 | -10.005 | Kiểm tra hai phía có dấu |
| NaN/Infinity | 10.00 | NaN hoặc Infinity | Không được coi là phép đo hợp lệ khi contract yêu cầu số hữu hạn |
| Rất gần 0 | 0.00 | 0.000001 | Xem tolerance tuyệt đối hay tương đối thích hợp |

Không nhất thiết dùng những giá trị trong bảng để kiểm tra **đúng biên bằng nhau** của `double` vì các literal thập phân cũng có thể bị biểu diễn sai. Nếu test cần một ranh giới mang ý nghĩa chính xác tuyệt đối, xét BigDecimal hoặc số nguyên của đơn vị nhỏ nhất; nếu chỉ cần chứng minh logic tolerance nói chung, dùng các điểm cách ranh giới đủ rõ để tránh nhiễu binary rounding.

## 7. Tiền tệ và số thập phân chính xác: BigDecimal

### 7.1. Vì sao không nên tính tiền trực tiếp bằng double?

`double` hữu ích cho nhiều phép đo/tính toán gần đúng, nhưng sai số nhị phân thường không phù hợp với yêu cầu tiền tệ chính xác đến một số chữ số thập phân. `BigDecimal` lưu giá trị thập phân dưới dạng số nguyên không scale và scale rõ ràng; quy tắc rounding được khai báo tường minh.

**Nên tạo BigDecimal từ string hoặc giá trị thập phân có chủ đích**:

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = BigDecimal.valueOf(0.1);
```

Cả hai có thể biểu diễn số thập phân 0.1 theo ý nghĩa mà lập trình viên mong muốn ở ví dụ này. Tránh `new BigDecimal(0.1)` khi dự định biểu diễn chính xác thập phân “0.1”, vì constructor từ `double` lưu giá trị nhị phân thực tế gần 0.1, tạo nhiều chữ số không mong đợi.

### 7.2. equals và compareTo có hợp đồng khác nhau

`BigDecimal.equals(...)` yêu cầu cả **giá trị và scale** giống nhau; `compareTo(...) == 0` kiểm tra **bằng nhau về số học**:

```java
BigDecimal left = new BigDecimal("2.0");
BigDecimal right = new BigDecimal("2.00");

assertNotEquals(left, right);
assertEquals(0, left.compareTo(right));
```

Khi nào dùng cách nào?

- Output công khai phải luôn có **2 chữ số thập phân**, kể cả số tiền `2.00`: `assertEquals(new BigDecimal("2.00"), actual)` có thể xác minh cả scale.
- Chỉ cần cùng số tiền về mặt giá trị, không yêu cầu representation: `assertEquals(0, expected.compareTo(actual))` tránh test đỏ chỉ vì `2.0` và `2.00` có scale khác.
- Nếu API trả string `"2.00"`, kiểm tra format/serialization tại boundary riêng; BigDecimal compareTo không chứng minh JSON/string định dạng đúng.

Đừng tự dùng `stripTrailingZeros()` trên cả expected/actual rồi khẳng định mọi quy tắc về scale đã được chứng minh. Nó có thể che mất sai sót khi scale/format là một phần hợp đồng.

### 7.3. RoundingMode là yêu cầu nghiệp vụ, không phải mẹo assertion

Ví dụ `new BigDecimal("1.005").setScale(2, RoundingMode.HALF_UP)` cho `1.01`. Với `RoundingMode.HALF_EVEN`, các tie case có thể cho kết quả khác tùy chữ số cuối được giữ. Quy tắc phù hợp phải đến từ yêu cầu sản phẩm/kế toán, không tự chọn một mode để test pass.

`setScale(2, RoundingMode.HALF_UP)` trả **BigDecimal mới**; BigDecimal là immutable. So kết quả sau khi tính/làm tròn tại đúng bước nghiệp vụ. Nếu làm tròn từng dòng hàng trước khi cộng khác với cộng tổng rồi làm tròn, test cần phản ánh thứ tự được quy định.

Ví dụ:

```java
BigDecimal rounded = new BigDecimal("1.005")
        .setScale(2, RoundingMode.HALF_UP);

assertEquals(new BigDecimal("1.01"), rounded);
```

Khi chia BigDecimal, một phép chia không có biểu diễn thập phân hữu hạn như `1 / 3` có thể ném `ArithmeticException` nếu không có quy tắc precision/rounding. Dùng `divide(divisor, scale, roundingMode)` hoặc `MathContext` theo hợp đồng và kiểm tra kết quả sau rounding; không “chữa” bằng cách chuyển qua `double`.

### 7.4. Số nguyên của đơn vị nhỏ nhất

Với những miền nghiệp vụ dùng đơn vị nhỏ nhất ổn định (ví dụ cents), lưu/tính bằng `long` có thể giúp so chính xác và tránh rounding lặp. Tuy nhiên cần xác định đơn vị, giới hạn tràn số và tỷ giá/thuế; không phải mọi tiền tệ đều có hai chữ số phần thập phân. Chọn `long` hay `BigDecimal` theo mô hình tiền tệ của hệ thống, còn assertion phải mô tả đúng đơn vị.

## 8. AssertTimeout khác kiểm tra thời điểm và khác kiểm tra Duration

JUnit Jupiter có thể kiểm tra *thời lượng thực thi* một callback bằng:

```java
assertTimeout(Duration.ofSeconds(2), () -> {
    // Gọi mã có yêu cầu hoàn thành trong 2 giây
    operationUnderTest();
});
```

Đây là **đoạn minh họa trong test method**, giả định có `operationUnderTest()`; chưa phải class runnable. Với `assertTimeout`, callback được thực thi trong **thread hiện tại** và không bị hủy giữa chừng khi quá ngưỡng: assertion có thể fail **sau khi callback kết thúc**. Nếu callback kẹt vô hạn, `assertTimeout` một mình không bảo đảm dừng được test.

Một biến thể khác là `assertTimeoutPreemptively(...)`: callback chạy ở **thread riêng** và JUnit tìm cách ngắt khi vượt ngưỡng. Điều này có rủi ro đặc biệt trong Spring: transaction của Spring Test thường được quản lý theo `ThreadLocal`, nên mã chạy thread riêng có thể không tham gia test-managed transaction/rollback như mong đợi. Hậu quả có thể là dữ liệu DB bị commit dù test dự kiến rollback. **Không tự thay `assertTimeout` bằng `assertTimeoutPreemptively` trong test giao dịch Spring.**

Ba khái niệm cần phân biệt:

| Mục tiêu | Thời gian đang đo | Giải pháp |
| --- | --- | --- |
| Token hết hạn khi now >= deadline | Thời điểm nghiệp vụ | `Clock.fixed` + `Instant` + assert boolean |
| Event xảy ra trong ±50 ms so với timestamp dự kiến | Sai khác giữa hai thời điểm | `Duration.between(...).abs()` và tolerance có đơn vị |
| Phép tính/phản hồi phải hoàn thành trong 2 s | Thời lượng thực thi | `assertTimeout` hoặc cơ chế timeout phù hợp |

**Test hiệu năng dễ nhiễu** do CI load, GC, JIT warmup, khởi động Spring context, network và scheduling. Timeout quá sát số đo trung bình dễ gây flakiness. Với thuật toán thuần, thường có thể kiểm thử đúng hành vi bằng giá trị đầu ra; ngưỡng thời gian chạy nên được quản lý riêng nếu đó thật sự là SLA, và kiểm thử hiệu năng chuyên dụng phù hợp hơn assertion thời gian quá chặt trong CI.

`@Timeout` của JUnit, cấu hình HTTP client timeout, database statement timeout và SLA HTTP là những cơ chế có mục tiêu khác nhau; không xem một assertion elapsed time là bằng chứng cho toàn bộ các cơ chế timeout production.

## 9. Đặt assertion ở đúng ranh giới Spring Boot

### 9.1. Unit test cho quy tắc thời gian và số

Ví dụ `AmountAndTimePolicyTest` dùng `new AmountAndTimePolicy(Clock.fixed(...))` và không khởi động Spring. Điều này kiểm chứng quy tắc nghiệp vụ chính xác, nhanh và không phụ thuộc môi trường. Đối tượng kiểm thử là **class thật**; clock chỉ là dependency thay thế.

Nếu service thật nhận đồng hồ từ Spring bean, test unit không tự chứng minh bean đã được wiring đúng. Hãy có test cấu hình/tích hợp riêng nếu wiring là yêu cầu có rủi ro.

### 9.2. HTTP/JSON: kiểm tra định dạng và timezone sau serialization

Giả sử endpoint trả `Instant` qua Jackson JSON. Unit test kiểm chứng deadline đúng, nhưng chưa kiểm chứng response JSON có ISO-8601, chữ `Z`/offset hay precision mong muốn. Để chứng minh HTTP contract, dùng test MVC slice (ví dụ `@WebMvcTest` + `MockMvc`) hoặc integration test phù hợp với Jackson config thực.

Nên parse timestamp nhận được thành `Instant` khi hợp đồng quan tâm **thời điểm**; nếu hợp đồng yêu cầu **định dạng chuỗi chính xác**, thêm assertion cho representation. Với số tiền JSON, kiểm tra cả giá trị và định dạng/trailing zeros nếu API specification đòi hỏi; đừng suy diễn từ `BigDecimal.compareTo`.

### 9.3. Persistence: làm rõ precision và nguồn thời gian

Database column loại `TIMESTAMP` có thể chỉ lưu tới milli/micro giây trong cấu hình cụ thể; còn `Instant` trong Java có nanosecond. Nếu code tạo `Instant.now(clock)`, lưu DB, rồi đọc lại, `assertEquals` có thể fail vì DB cắt độ phân giải. Hãy quyết định cách chuẩn hóa hoặc round-trip tolerance dựa vào schema và hợp đồng lưu trữ; một test repository/integration có DB thực mới chứng minh được điều này.

Nếu `createdAt` do **database tự sinh** (DEFAULT CURRENT_TIMESTAMP) hoặc Hibernate/database annotation, một `Clock.fixed` được inject vào service **không bắt buộc điều khiển được** timestamp ấy. Cần test đúng nguồn clock thực sự của trường dữ liệu, đồng thời kiểm tra timezone và precision. Không viết test dựa trên giả định “service clock kiểm soát mọi timestamp” khi database hoặc framework là nơi tạo thời gian.

Với Hibernate/JPA có transaction test, phân biệt thời điểm entity được persist, flush và commit; DB-generated values đôi khi chỉ có sau flush/refresh. So sánh timestamp sau khi có giá trị thực và với precision mà DB thực sự cam kết.

### 9.4. Thời gian bất đồng bộ và eventual consistency

Nếu logic chạy qua scheduler/message, đừng dùng `Thread.sleep(100)` rồi mặc định event đã xong. Ưu tiên tín hiệu có thể quan sát (future, latch, test probe hoặc polling có **thời hạn**), sau đó assert timestamp/giá trị. Kể cả khi polling có timeout, cần tách hai lý do fail: hành vi không bao giờ xảy ra và timestamp khi xảy ra nằm ngoài giới hạn nghiệp vụ.

Nếu mục tiêu là kiểm tra schedule dựa trên múi giờ, cần test trước/đúng/sau mốc và ngày chuyển DST của timezone liên quan; so string ngày giờ cục bộ không đủ chứng minh đúng thời điểm UTC.

## 10. Những ca biên cần có

### Thời gian

- **Trước deadline một đơn vị nhỏ nhất mà hợp đồng phân biệt:** chưa hết hạn.
- **Đúng deadline:** có/không hết hạn theo quy tắc bao gồm hay loại trừ đã nêu.
- **Sau deadline một đơn vị:** hết hạn.
- **Qua nửa đêm hoặc chuyển ngày:** xem ngày theo timezone nghiệp vụ, không theo máy CI.
- **Cùng instant nhưng offset khác:** so `toInstant()` nếu mục tiêu là thời điểm tuyệt đối.
- **Round trip DB/JSON:** kiểm tra precision có chủ đích.
- **Clock gần biên:** không phụ thuộc `Instant.now()` chạy thật giữa các assertion.

### Số thực và tolerance

- Giá trị kỳ vọng giống actual, actual lệch ít hơn và lớn hơn tolerance.
- Giá trị âm, gần 0, rất lớn; tolerance có còn hợp lý theo đơn vị không?
- `NaN`, `+Infinity`, `-Infinity`: đầu vào/kết quả có được phép không?
- Đổi phép cộng thành phép trừ hoặc đảo dấu có bị test phát hiện không?
- Nếu dùng relative tolerance, có **absolute floor** khi expected gần 0 không?
- Nếu dùng delta, có trường hợp actual sai rõ ràng vẫn bị cho qua không?

### BigDecimal

- Scale và rounding theo hợp đồng: ví dụ `1.005 → 1.01` ở HALF_UP với 2 decimal places.
- Hai giá trị cùng số nhưng scale khác: chọn `equals` hay `compareTo` đúng mục tiêu.
- Số âm, zero, mức thuế 0, kết quả rất lớn/tràn giới hạn nếu domain có quy định.
- Phép chia không chia hết: quy tắc rounding rõ, test không dựa vào double.
- Kết quả lưu DB hay serialize JSON có giữ precision/format mong muốn không?

## 11. Lỗi phổ biến

**1. Dùng `assertEquals(0.3, 0.1 + 0.2)` rồi kết luận chương trình sai.** Phép tính `double` có sai số biểu diễn. Nếu phép tính gần đúng được chấp nhận, dùng `assertEquals(expected, actual, delta)` với tolerance phù hợp; nếu là tiền chính xác, dùng BigDecimal.

**2. Truyền `delta` rất lớn để bỏ qua test đỏ.** Một bug tính 50% giá trị vẫn được coi là đúng nếu delta quá rộng. Gắn sai số với yêu cầu và thêm test actual sai rõ ràng phải fail.

**3. Xem delta của assertEquals là phần trăm.** Delta là **sai số tuyệt đối** ở đơn vị của đại lượng. Nếu cần tỷ lệ tương đối, tự tính hoặc dùng matcher phù hợp và nêu rõ cách chuẩn hóa.

**4. Không xét NaN/Infinity.** Một test “xấp xỉ” có thể xử lý các giá trị đặc biệt theo quy tắc riêng của thư viện. Khi domain chỉ chấp nhận số hữu hạn, assert `Double.isFinite` hoặc kiểm tra validation trong production.

**5. So BigDecimal bằng `equals` khi chỉ cần giá trị số học.** `2.0` và `2.00` không equals; nếu scale không thuộc contract, dùng `compareTo(...) == 0`. Nếu scale thuộc contract, giữ phép so equals và test scale rõ.

**6. Dùng `new BigDecimal(0.1)` với kỳ vọng được chính xác `0.1`.** Constructor từ `double` bảo toàn approximation nhị phân, không bảo toàn literal decimal như string. Dùng `new BigDecimal("0.1")` hoặc `BigDecimal.valueOf(0.1)` theo mô hình phù hợp.

**7. Lấy `Instant.now()` liên tiếp trong test timeout/expiry.** Đồng hồ tiếp tục chạy, khiến test gần ranh giới chập chờn. Inject `Clock` và cố định thời điểm khi đang kiểm tra quy tắc thời gian.

**8. Trộn `LocalDateTime` với `Instant` mà bỏ qua zone.** LocalDateTime không mang timezone; chuyển đổi sang instant phải dựa vào zone/offset cụ thể. Kiểm tra hợp đồng thời gian trước khi so.

**9. Cắt timestamp về millisecond ở mọi chỗ để test qua.** Cách đó có thể giấu lỗi mất precision khi API cần micro/nano giây. Chỉ normalize theo contract thực tế của storage/transport.

**10. Dùng `assertTimeoutPreemptively` trong test giao dịch Spring như một thay thế vô hại.** Thread riêng có thể không kế thừa test-managed transaction. Chọn cơ chế timeout theo rủi ro về state, interrupt và rollback; không dựa vào kết quả pass mà bỏ qua side effect.

**11. Dùng `Thread.sleep` để chứng minh time-based rule.** Test vừa chậm vừa dễ fail do scheduling. Đổi thành Clock.fixed/test clock cho nghiệp vụ, đợi tín hiệu observable với timeout khi kiểm tra bất đồng bộ.

**12. Chỉ test ví dụ ở giữa khoảng, bỏ qua các biên.** Bug so sánh `>` và `>=` xuất hiện chính tại deadline; bug rounding xuất hiện tại giá trị như `1.005`; bug tolerance xuất hiện tại giá trị gần ngưỡng.

## 12. Checklist khi review assertion thời gian và số

Trước khi kết luận test đã chứng minh yêu cầu:

- Tôi có mô tả **đại lượng, đơn vị và độ chính xác** cần so chưa?
- Nếu là thời điểm, có dùng đúng `Instant`/`ZonedDateTime`/`LocalDate` và zone theo nghiệp vụ?
- Nếu logic dựa vào thời điểm hiện tại, test đã kiểm soát nguồn `Clock` và bao phủ trước/đúng/sau mốc chưa?
- Nếu dữ liệu đi qua database/JSON, precision và format có được kiểm tra ở đúng boundary chưa?
- Với `double`, tolerance là tuyệt đối hay tương đối, và con số ấy đến từ đâu?
- Test có bắt được output sai rõ ràng, NaN/Infinity không hợp lệ và các trường hợp gần 0?
- Với tiền, có dùng `BigDecimal` hoặc đơn vị nguyên, làm tròn theo policy và chọn đúng `equals`/`compareTo`?
- Nếu dùng `assertTimeout`, đã phân biệt **thời lượng thực thi** với **thời điểm nghiệp vụ**, cân nhắc rủi ro thread/transaction chưa?
- Test có độc lập với giờ máy, tải CI, sleep, timezone mặc định và dữ liệu dùng chung chưa?
- Mỗi assert có nêu lý do pass/fail gắn với hợp đồng thay vì chỉ cố làm test xanh?

**Ghi nhớ:** kiểm thử thời gian đáng tin bắt đầu bằng **đồng hồ có thể kiểm soát và ranh giới được định nghĩa rõ**; kiểm thử phép tính gần đúng dùng **tolerance có đơn vị, được biện minh**; kiểm thử tiền và số thập phân chính xác dùng **BigDecimal cùng quy tắc scale/rounding**. Chọn assertion thể hiện hợp đồng thật của dữ liệu, rồi kiểm thử các biên để bảo đảm nó phát hiện được lỗi.