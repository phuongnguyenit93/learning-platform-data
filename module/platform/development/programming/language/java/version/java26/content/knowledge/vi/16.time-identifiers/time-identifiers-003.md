# Phân biệt plusSaturating với phép cộng báo lỗi khi vượt miền

*Tình trạng API được đối chiếu với Java 26 tại ngày 27/11/2026.*

Java 26 bổ sung `Instant.plusSaturating(Duration)` để cộng một khoảng thời gian vào một thời điểm theo **saturating arithmetic**. Nếu kết quả vượt khỏi miền biểu diễn của `Instant`, phương thức trả về giới hạn gần nhất là `Instant.MIN` hoặc `Instant.MAX`. Nếu kết quả vẫn nằm trong miền hợp lệ, phương thức trả về kết quả giống `Instant.plus(Duration)`.

Điểm khác biệt với phép cộng thông thường là cách xử lý kết quả ngoài miền:

- `Instant.plus(Duration)` báo lỗi bằng `DateTimeException` hoặc `ArithmeticException` khi không thể biểu diễn kết quả.
- `Instant.plusSaturating(Duration)` kẹp kết quả về biên gần nhất, không ném hai loại ngoại lệ đó do vượt miền hoặc tràn số trong phép cộng thời điểm.

Đây là API Java SE ổn định được thêm từ Java 26, không phải preview hay incubator. Nó đặc biệt hữu ích khi tính deadline từ thời điểm hiện tại và timeout, nhưng không nên dùng để che giấu dữ liệu thời gian sai trong nghiệp vụ cần phát hiện lỗi.

## 1. Vấn đề của phép cộng thời gian vượt miền

`Instant` biểu diễn một điểm trên timeline theo giây và nano giây tính từ epoch `1970-01-01T00:00:00Z`. Kiểu này có miền giá trị rất rộng nhưng hữu hạn:

- `Instant.MIN`: `-1000000000-01-01T00:00:00Z`.
- `Instant.MAX`: `+1000000000-12-31T23:59:59.999999999Z`.

Khi cộng một `Duration`, kết quả phải nằm trong miền đó. Ví dụ, cộng thêm năm giây vào một instant chỉ còn cách `Instant.MAX` hai giây sẽ tạo ra một thời điểm không thể biểu diễn.

Với phép cộng thông thường:

```java
Instant nearMax = Instant.MAX.minusSeconds(2);

Instant result = nearMax.plus(Duration.ofSeconds(5));
// Ném DateTimeException vì kết quả vượt Instant.MAX.
```

Điều này là hành vi có chủ đích. Nếu ứng dụng cần biết phép tính không thể biểu diễn, exception giúp phát hiện vấn đề thay vì âm thầm thay đổi ý nghĩa của thời điểm.

Nhưng có những trường hợp cần một giá trị giới hạn hợp lệ để tiếp tục xử lý, ví dụ deadline rất xa trong tương lai. Với các trường hợp đó, Java 26 cung cấp `plusSaturating()`.

## 2. Saturating arithmetic là gì?

Saturating arithmetic là phép tính có giới hạn. Khi kết quả vượt miền, nó được kẹp vào giá trị biên gần nhất thay vì wrap-around hoặc ném lỗi.

Với `Instant.plusSaturating(duration)`:

- Nếu kết quả sớm hơn `Instant.MIN`, trả về `Instant.MIN`.
- Nếu kết quả muộn hơn `Instant.MAX`, trả về `Instant.MAX`.
- Nếu kết quả nằm trong miền hợp lệ, trả về kết quả phép cộng thông thường.

Có thể hình dung:

```text
          kết quả hợp lệ
MIN  <-------------------------->  MAX
 ^                                  ^
 |                                  |
kẹp tại MIN                    kẹp tại MAX
nếu tràn xuống                 nếu tràn lên
```

Saturation khác với wrap-around. Ví dụ, phép cộng số nguyên primitive có thể quay vòng từ số dương lớn sang số âm do biểu diễn bù hai. Saturating arithmetic không quay vòng; nó dừng ở biên.

Saturation cũng khác với checked arithmetic. Checked arithmetic báo lỗi để caller quyết định cách xử lý; saturation trả về một kết quả hợp lệ ở biên để caller tiếp tục.

## 3. Cú pháp và hợp đồng của plusSaturating

Chữ ký Java 26:

```java
public Instant plusSaturating(Duration duration)
```

Tham số là một `Duration`, có thể dương, âm hoặc bằng không. Phương thức trả về một `Instant` mới; `Instant` là immutable nên đối tượng ban đầu không thay đổi.

Ví dụ:

```java
import java.time.Duration;
import java.time.Instant;

public class SaturatingInstant {
    public static void main(String[] args) {
        Instant start = Instant.parse("2026-11-27T10:00:00Z");

        Instant normal = start.plusSaturating(Duration.ofMinutes(15));
        Instant unchanged = start.plusSaturating(Duration.ZERO);
        Instant earlier = start.plusSaturating(Duration.ofMinutes(-5));

        System.out.println(normal);
        System.out.println(unchanged);
        System.out.println(earlier);
    }
}
```

Nếu phép cộng không vượt miền, `plusSaturating()` có kết quả giống `plus()`. Tham số `duration` không được là `null`; truyền `null` vẫn gây `NullPointerException`.

Javadoc nêu rõ phương thức không ném `ArithmeticException` hoặc `DateTimeException` do tràn số hoặc kết quả vượt miền `Instant`. Điều đó không có nghĩa mọi lỗi lập trình đều bị bỏ qua: kiểm tra đầu vào và logic nghiệp vụ vẫn là trách nhiệm của ứng dụng.

## 4. So sánh plus và plusSaturating

| Tình huống | `Instant.plus(duration)` | `Instant.plusSaturating(duration)` |
|---|---|---|
| Kết quả nằm trong miền | Trả về thời điểm đã cộng | Trả về cùng thời điểm |
| Kết quả vượt `Instant.MAX` | Ném `DateTimeException` hoặc lỗi số học liên quan | Trả `Instant.MAX` |
| Kết quả nhỏ hơn `Instant.MIN` | Ném `DateTimeException` hoặc lỗi số học liên quan | Trả `Instant.MIN` |
| Duration bằng không | Trả về instant ban đầu | Trả về instant ban đầu |
| Duration âm | Cộng theo hướng thời gian đi lùi; có thể lỗi nếu vượt MIN | Cộng theo hướng thời gian đi lùi; kẹp tại MIN nếu vượt |
| Duration null | Ném `NullPointerException` | Ném `NullPointerException` |

Chọn phương thức theo chính sách nghiệp vụ:

- Dùng `plus()` khi vượt miền là lỗi cần phát hiện, ghi log hoặc từ chối giao dịch.
- Dùng `plusSaturating()` khi biên thời gian là kết quả fallback hợp lệ, ví dụ một deadline tối đa hoặc tối thiểu.
- Không chọn saturation chỉ vì muốn tránh viết `try/catch`; hãy xác định rõ việc kẹp kết quả có đúng nghĩa nghiệp vụ hay không.

## 5. Ví dụ vượt biên trên và biên dưới

Ví dụ sau minh họa cả hai hướng. `plus()` báo lỗi khi kết quả vượt miền, còn `plusSaturating()` trả về biên tương ứng.

```java
import java.time.DateTimeException;
import java.time.Duration;
import java.time.Instant;

public class InstantBounds {
    public static void main(String[] args) {
        Instant nearMax = Instant.MAX.minusSeconds(2);
        Duration forward = Duration.ofSeconds(5);

        try {
            System.out.println(nearMax.plus(forward));
        } catch (DateTimeException e) {
            System.out.println("plus failed: " + e.getClass().getSimpleName());
        }

        System.out.println(nearMax.plusSaturating(forward));
        // Instant.MAX

        Instant nearMin = Instant.MIN.plusSeconds(2);
        Duration backward = Duration.ofSeconds(-5);

        try {
            System.out.println(nearMin.plus(backward));
        } catch (DateTimeException e) {
            System.out.println("plus failed: " + e.getClass().getSimpleName());
        }

        System.out.println(nearMin.plusSaturating(backward));
        // Instant.MIN
    }
}
```

Kết quả của phần saturating là hai biên được hỗ trợ. Không có phép quay vòng từ MAX sang MIN hoặc từ MIN sang MAX.

Trong ví dụ này, khoảng thời gian đủ nhỏ để lỗi là do giới hạn miền `Instant`. Với những phép tính có thể làm tràn phần số học nội bộ, `plus()` cũng có thể ném `ArithmeticException`. `plusSaturating()` được thiết kế để xử lý cả tràn số trong phép cộng thời điểm lẫn vi phạm miền Instant bằng cách kẹp kết quả.

## 6. Dùng plusSaturating để tính deadline

Một use case được Javadoc nêu trực tiếp là tính deadline từ thời điểm hiện tại và timeout:

```java
import java.time.Duration;
import java.time.Instant;

public class Deadline {
    static Instant deadlineFrom(Instant start, Duration timeout) {
        return start.plusSaturating(timeout);
    }

    public static void main(String[] args) {
        Instant start = Instant.now();
        Duration timeout = Duration.ofSeconds(30);

        Instant deadline = deadlineFrom(start, timeout);
        System.out.println("Deadline: " + deadline);
    }
}
```

Với timeout thông thường, kết quả giống phép cộng thông thường. Nếu timeout cực lớn khiến kết quả vượt miền `Instant`, deadline được kẹp về `Instant.MAX`, cho phép code vẫn có một giá trị thời gian hợp lệ.

Tuy nhiên, cần xác thực timeout trước khi tính:

```java
static Instant deadlineFrom(Instant start, Duration timeout) {
    if (timeout.isNegative()) {
        throw new IllegalArgumentException("Timeout must not be negative");
    }

    return start.plusSaturating(timeout);
}
```

Saturation không tự xác định timeout âm là hợp lệ hay không. Nó chỉ thực hiện phép toán theo hướng của duration. Nếu timeout là cấu hình không hợp lệ theo nghiệp vụ, ứng dụng vẫn phải từ chối nó.

Với timeout rất lớn, `Instant.MAX` có thể được dùng như một deadline xa nhất có thể biểu diễn. Nhưng đừng mặc định mọi API nhận deadline đều hiểu `Instant.MAX` là “không có timeout”; cần xem hợp đồng của API đó.

## 7. Duration.MIN và Duration.MAX trong Java 26

Java 26 cũng bổ sung hai hằng:

- `Duration.MIN`: khoảng thời gian nhỏ nhất, có `Long.MIN_VALUE` giây.
- `Duration.MAX`: khoảng thời gian lớn nhất, có `Long.MAX_VALUE` giây và `999,999,999` nano giây.

Hai hằng này hữu ích làm sentinel value hoặc dữ liệu biên trong test. Chúng không phải giá trị đại diện cho timeout thông thường.

```java
Duration smallest = Duration.MIN;
Duration largest = Duration.MAX;

Instant now = Instant.now();

Instant earliest = now.plusSaturating(smallest);
Instant latest = now.plusSaturating(largest);

System.out.println(earliest.equals(Instant.MIN));
System.out.println(latest.equals(Instant.MAX));
```

Đối với một instant hiện tại nằm trong miền, duration nhỏ nhất sẽ đưa phép cộng xuống dưới `Instant.MIN`, còn duration lớn nhất đưa phép cộng lên trên `Instant.MAX`. Saturation trả về hai giới hạn đó.

Cần phân biệt hai miền:

- `Duration` biểu diễn một độ dài thời gian theo giây và nano giây.
- `Instant` biểu diễn một điểm trên timeline với miền riêng.

Một `Duration` hợp lệ vẫn có thể quá lớn để cộng vào một `Instant` cụ thể mà không vượt miền. Đây chính là trường hợp `plusSaturating()` xử lý.

## 8. plusSaturating không làm phép tính Duration trở nên saturating

`plusSaturating()` chỉ giải quyết phép cộng một `Duration` đã tồn tại vào một `Instant`. Nó không thay đổi cách `Duration` tự thực hiện cộng, nhân hoặc chuyển đổi.

Ví dụ:

```java
Duration tooLarge = Duration.MAX.plusSeconds(1);
// Ném ArithmeticException ngay khi tạo Duration mới.
```

Nếu phép tính tạo ra duration bị tràn, chương trình chưa thể gọi `Instant.plusSaturating()`. Tương tự, các phép `Duration.multipliedBy()`, `Duration.plus()`, `Duration.negated()` vẫn có thể ném `ArithmeticException` khi kết quả vượt miền của Duration.

Vì vậy, cần tách hai bước:

1. Tạo hoặc tính `Duration` hợp lệ.
2. Cộng duration đó vào instant bằng chính sách checked hoặc saturating phù hợp.

Nếu dữ liệu đầu vào là số giây từ bên ngoài, hãy kiểm tra giới hạn trước khi chuyển thành `Duration`. Saturation của Instant không thể sửa lỗi tràn đã xảy ra ở bước xây dựng duration.

## 9. Không nhầm với phép cộng số nguyên primitive

Java primitive `int` và `long` dùng arithmetic có wrap-around. Ví dụ:

```java
long value = Long.MAX_VALUE;
long wrapped = value + 1;

System.out.println(wrapped); // Long.MIN_VALUE
```

Nếu muốn phép cộng primitive báo lỗi khi tràn, dùng `Math.addExact()`:

```java
long checked = Math.addExact(Long.MAX_VALUE, 1);
// Ném ArithmeticException.
```

`Instant.plus()` không hoạt động như phép cộng primitive wrap-around. Nó kiểm tra miền thời gian và báo exception nếu kết quả không thể biểu diễn. `Instant.plusSaturating()` lại dùng chính sách kẹp biên.

| Loại phép toán | Khi vượt miền |
|---|---|
| `long a + b` | Wrap-around theo quy tắc số nguyên Java |
| `Math.addExact(a, b)` | Ném `ArithmeticException` |
| `Instant.plus(Duration)` | Ném `DateTimeException` hoặc `ArithmeticException` |
| `Instant.plusSaturating(Duration)` | Kẹp về `Instant.MIN` hoặc `Instant.MAX` |

Không thay phép tính thời gian bằng cách tự cộng epoch seconds nếu có thể dùng API `java.time`. Các lớp thời gian xử lý cả giây và nano giây, miền hợp lệ và quy tắc chuẩn hóa; tự tính bằng `long` dễ bỏ sót các chi tiết đó.

## 10. plusSaturating chỉ dành cho Instant và Duration

Trong Java 26, API được thêm là `Instant.plusSaturating(Duration)`. Không suy rộng rằng mọi lớp trong `java.time` đều có phương thức cùng tên.

`Instant` là một điểm trên timeline UTC. `Duration` là độ dài thời gian dựa trên giây và nano giây; một ngày của Duration luôn là 24 giờ. Khi cần tính lịch theo múi giờ, ngày địa phương hoặc quy tắc daylight saving time, hãy dùng các API phù hợp như `ZonedDateTime`, `LocalDate`, `Period` và `ZoneId`.

Ví dụ, cộng 24 giờ vào một `Instant` luôn là thêm đúng 86.400 giây theo Java Time-Scale. Nó không mang nghĩa “cùng giờ ngày mai theo lịch địa phương” nếu khu vực có thay đổi DST. `plusSaturating()` chỉ giải quyết giới hạn biểu diễn của Instant, không thay đổi ngữ nghĩa lịch hoặc múi giờ.

## 11. Khi nào nên dùng và khi nào nên báo lỗi?

**Nên dùng `plusSaturating()` khi:**

- Tính deadline từ một instant và timeout có thể rất lớn.
- Xử lý khoảng thời gian đến từ cấu hình hoặc dữ liệu mà biên tối đa/tối thiểu được chấp nhận như kết quả hợp lệ.
- Cần một giá trị Instant luôn nằm trong miền biểu diễn để tiếp tục so sánh hoặc hiển thị.
- Muốn mô hình hóa giới hạn “không sớm hơn MIN” hoặc “không muộn hơn MAX”.

**Nên dùng `plus()` và xử lý exception khi:**

- Vượt miền biểu diễn có nghĩa là dữ liệu sai hoặc lỗi nghiệp vụ.
- Hệ thống tính hạn hợp đồng, thời hạn lưu trữ, thời điểm hiệu lực hoặc lịch thanh toán mà việc kẹp biên có thể che giấu sai số.
- Cần phân biệt một deadline thực sự hợp lệ với dữ liệu vượt giới hạn.
- Cần log và từ chối request có giá trị thời gian không thể biểu diễn.

Saturation là một chính sách dữ liệu. Nó không phải cách “làm cho phép tính luôn thành công” mà không có hệ quả. Nếu kẹp một thời điểm bất thường về `Instant.MAX`, chương trình đã thay đổi giá trị đầu vào theo một quy tắc cụ thể; cần chắc rằng nghiệp vụ chấp nhận điều đó.

## 12. Kiểm thử các trường hợp biên

Nên kiểm tra ít nhất các trường hợp sau:

```java
import java.time.Duration;
import java.time.Instant;

public class SaturatingInstantChecks {
    public static void main(String[] args) {
        Instant base = Instant.parse("2026-11-27T10:00:00Z");

        // Trong miền: hai phương thức cho cùng kết quả.
        assert base.plusSaturating(Duration.ofSeconds(10))
                .equals(base.plus(Duration.ofSeconds(10)));

        // Vượt biên trên.
        assert Instant.MAX.minusSeconds(1)
                .plusSaturating(Duration.ofSeconds(2))
                .equals(Instant.MAX);

        // Vượt biên dưới.
        assert Instant.MIN.plusSeconds(1)
                .plusSaturating(Duration.ofSeconds(-2))
                .equals(Instant.MIN);

        // Các Duration cực trị.
        assert base.plusSaturating(Duration.MAX).equals(Instant.MAX);
        assert base.plusSaturating(Duration.MIN).equals(Instant.MIN);

        // Duration bằng không không đổi instant.
        assert base.plusSaturating(Duration.ZERO).equals(base);
    }
}
```

Chạy assertions bằng:

```bash
javac --release 26 SaturatingInstantChecks.java
java -ea SaturatingInstantChecks
```

Không cần `--enable-preview` vì `plusSaturating()`, `Duration.MIN` và `Duration.MAX` là API Java SE ổn định từ Java 26. `--release 26` giúp compiler xác nhận code chỉ dựa trên API của Java 26 trở xuống.

Khi kiểm thử exception của `plus()`, nên dùng giá trị gần biên như `Instant.MAX.minusSeconds(1)` cộng hai giây, thay vì chỉ dựa vào dữ liệu thực tế hiếm khi vượt miền. Test biên giúp xác nhận chính sách checked và saturating một cách xác định.

## 13. Tóm tắt lựa chọn API

| Nhu cầu | API phù hợp | Lý do |
|---|---|---|
| Cộng thời gian và muốn phát hiện vượt miền | `Instant.plus(Duration)` | Báo lỗi để caller xử lý |
| Cộng thời gian và chấp nhận kẹp tại biên | `Instant.plusSaturating(Duration)` | Luôn trả Instant trong miền |
| Cộng hai Duration và muốn phát hiện tràn | `Duration.plus(Duration)` | Ném `ArithmeticException` nếu vượt miền Duration |
| Cộng hai số nguyên và muốn phát hiện tràn | `Math.addExact()` | Checked primitive arithmetic |
| Cộng hai số nguyên theo quy tắc wrap-around của Java | Toán tử `+` | Dùng khi wrap-around là ngữ nghĩa mong muốn |

Điểm cần nhớ: `plusSaturating()` không thay thế mọi phép cộng có kiểm tra. Nó là lựa chọn có chủ đích cho phép cộng `Duration` vào `Instant` khi chính sách của ứng dụng là kẹp kết quả ở biên thời gian.

## Tài liệu tham chiếu

1. [Oracle Java SE 26 API – Instant.plusSaturating(Duration)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html#plusSaturating(java.time.Duration))
2. [Oracle Java SE 26 API – Instant.MIN và Instant.MAX](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html)
3. [Oracle Java SE 26 API – Duration.MIN và Duration.MAX](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html)
4. [Oracle – Consolidated JDK 26 Release Notes: Adding a Duration to an Instant with Saturation](https://www.oracle.com/java/technologies/javase/26all-relnotes.html)

