# Duration trong Java: Cộng, trừ, nhân, chia, đổi dấu và lấy trị tuyệt đối

## 1. Mục tiêu

`java.time.Duration` biểu diễn một **lượng thời gian đã trôi qua**, dựa trên giây và nano giây. Trong Java 17+, Duration là immutable: các phép toán trả về giá trị mới, không sửa đối tượng ban đầu.

Bài học này trình bày các phép cộng, trừ, nhân, chia, đổi dấu và lấy trị tuyệt đối; cách xử lý duration âm, phần dư khi chia và tràn số. Không nhầm Duration với Period: Duration phù hợp với lượng thời gian theo giây/nano giây, còn Period biểu diễn năm, tháng và ngày theo lịch.

## 2. Tạo Duration

```java
Duration a = Duration.ofSeconds(3);
Duration b = Duration.ofMillis(1500);
Duration c = Duration.ofMinutes(2);
Duration d = Duration.ofNanos(250);
Duration e = Duration.ofDays(1);
```

Đây là mã minh họa trong một phương thức, cần `import java.time.Duration;`.

| Cách tạo | Độ dài tương đương |
| --- | ---: |
| `Duration.ofSeconds(1)` | 1 giây |
| `Duration.ofMillis(1500)` | 1,5 giây |
| `Duration.ofNanos(1_000)` | 1 micro giây |
| `Duration.ofMinutes(2)` | 120 giây |
| `Duration.ofDays(1)` | 86.400 giây |

`Duration.ofDays(1)` nghĩa là 24 giờ cố định, không phải “ngày lịch kế tiếp” ở mọi múi giờ. Một ngày địa phương qua DST có thể dài 23 hoặc 25 giờ; thao tác ngày lịch cần các API ngày giờ theo vùng phù hợp.

`Duration.toString()` thường hiển thị theo ISO-8601, ví dụ `PT3.5S`, `PT2M` hoặc `PT-0.5S`.

## 3. Cộng bằng plus

Dùng `plus(Duration)` để cộng duration, hoặc các phương thức như `plusSeconds`, `plusMillis` và `plusNanos` khi đơn vị đã rõ.

```java
Duration base = Duration.ofSeconds(2);
Duration extra = Duration.ofMillis(500);

Duration total = base.plus(extra);
Duration alsoTotal = base.plusMillis(500);

System.out.println(total);       // PT2.5S
System.out.println(alsoTotal);   // PT2.5S
System.out.println(base);        // PT2S
```

Đây là mã minh họa trong phương thức, cần `import java.time.Duration;`. Kết quả cho thấy `base` không đổi. Mỗi lời gọi tạo ra giá trị trả về mới.

```java
Duration timeout = Duration.ofSeconds(1)
        .plusMillis(250)
        .plusNanos(40);
System.out.println(timeout); // PT1.25000004S
```

Các phép cộng nối chuỗi được. Nếu kết quả vượt phạm vi Duration, phép toán có thể ném `ArithmeticException`.

## 4. Trừ bằng minus

Dùng `minus(Duration)` hoặc các overload như `minusSeconds`, `minusMillis`, `minusNanos`.

```java
Duration meeting = Duration.ofSeconds(3);
Duration breakTime = Duration.ofMillis(500);

System.out.println(meeting.minus(breakTime)); // PT2.5S
System.out.println(meeting.minusMillis(500)); // PT2.5S
System.out.println(meeting);                  // PT3S
```

Kết quả không cập nhật biến gốc. Phép trừ có thể cho duration âm:

```java
Duration remaining = Duration.ofSeconds(2).minusSeconds(5);
System.out.println(remaining); // PT-3S
System.out.println(remaining.isNegative()); // true
```

Duration âm hợp lệ. Ví dụ, `Duration.between(start, end)` thường âm khi end đứng trước start. Không ép mọi giá trị âm thành 0 trừ khi đó là yêu cầu nghiệp vụ.

## 5. Nhân bằng multipliedBy

`multipliedBy(long)` nhân duration với số nguyên.

```java
Duration interval = Duration.ofMillis(1500);

System.out.println(interval.multipliedBy(3));  // PT4.5S
System.out.println(interval.multipliedBy(0));  // PT0S
System.out.println(interval.multipliedBy(-2)); // PT-3S
System.out.println(interval);                  // PT1.5S
```

Đây là mã minh họa, cần Duration. Nhân với 0 tạo Duration.ZERO; nhân với số âm đảo chiều dấu. Đối tượng gốc vẫn là PT1.5S.

Phép nhân có thể vượt phạm vi biểu diễn và gây `ArithmeticException`. Dùng API chuẩn thay vì tự nhân các thành phần giây/nano mà không kiểm tra tràn số.

## 6. Chia bằng dividedBy(long)

`dividedBy(long)` chia một duration cho số nguyên và vẫn trả về Duration. Độ phân giải tối đa là nano giây, vì vậy phần nano phân số không thể giữ lại.

```java
System.out.println(Duration.ofSeconds(5).dividedBy(2)); // PT2.5S

Duration fiveNanos = Duration.ofNanos(5);
System.out.println(fiveNanos.dividedBy(2)); // PT0.000000002S
System.out.println(fiveNanos.dividedBy(3)); // PT0.000000001S
```

5 ns chia 2 có giá trị toán học 2,5 ns nhưng Duration không thể biểu diễn nửa nano giây; kết quả là 2 ns. Chia cho 0 ném `ArithmeticException`.

Không nhầm `dividedBy(long)` với phép chia duration cho duration; chúng trả về hai loại kết quả khác nhau.

## 7. Chia Duration cho Duration

Overload `dividedBy(Duration)` trả số lần nguyên mà một duration nằm trong duration kia.

```java
System.out.println(Duration.ofSeconds(10)
        .dividedBy(Duration.ofSeconds(3))); // 3

System.out.println(Duration.ofSeconds(1)
        .dividedBy(Duration.ofMillis(250))); // 4

System.out.println(Duration.ofSeconds(1)
        .dividedBy(Duration.ofMillis(300))); // 3
```

Đây là mã minh họa, cần Duration. Một giây chứa ba khối trọn vẹn 300 ms, còn 100 ms dư bị bỏ qua. Kết quả là số nguyên, không phải tỷ số thập phân. Duration divisor bằng 0 gây `ArithmeticException`.

Nếu cần tỷ số thập phân, hãy xác định rõ chính sách độ chính xác và làm tròn khi chuyển sang kiểu số phù hợp; đừng tự giả định kết quả chia của Duration là số thực.

## 8. Đổi dấu với negated()

`negated()` trả về duration có độ lớn tương đương nhưng dấu ngược lại.

```java
Duration positive = Duration.ofMillis(1500);
Duration negative = positive.negated();

System.out.println(positive); // PT1.5S
System.out.println(negative); // PT-1.5S
System.out.println(negative.negated()); // PT1.5S
```

Đổi dấu không sửa đối tượng gốc; duration 0 vẫn bằng 0. Giá trị cực trị có thể không có đối dấu tương ứng trong phạm vi biểu diễn và khi đó phép toán ném `ArithmeticException`.

## 9. Trị tuyệt đối với abs()

`abs()` trả về duration có độ lớn không âm.

```java
Duration late = Duration.ofMillis(-1500);

System.out.println(late);       // PT-1.5S
System.out.println(late.abs()); // PT1.5S
System.out.println(late);       // PT-1.5S
```

Dùng `abs()` khi chỉ cần độ lớn chênh lệch. Nếu dấu cho biết sự kiện còn trước hạn hay đã quá hạn, hãy giữ dấu cho tới khi quyết định nghiệp vụ. Trường hợp cực trị không thể đảo dấu có thể ném `ArithmeticException`.

## 10. Duration âm: seconds và nanos

Duration được chuẩn hóa với thành phần giây và nano. Thành phần nano luôn từ 0 đến 999.999.999, kể cả khi toàn duration âm.

```java
Duration d = Duration.ofNanos(-1);

System.out.println(d);               // PT-0.000000001S
System.out.println(d.getSeconds());  // -1
System.out.println(d.getNano());     // 999999999
System.out.println(d.toMillis());    // 0
```

Với -1 ns, biểu diễn chuẩn là -1 giây + 999.999.999 ns, tổng cộng -1 ns. `getNano()` không phải tổng nano giây và cũng không bắt buộc mang cùng dấu với toàn Duration.

`toMillis()` trả mili giây nguyên; khi duration là -1 ns, phần nhỏ hơn 1 ms bị bỏ về 0. Điều đó không biến duration gốc thành Duration.ZERO. Nếu tính tổng nano giây bằng long, `toNanos()` có thể ném `ArithmeticException` khi giá trị vượt phạm vi.

## 11. Chia nguyên, cắt phần lẻ và làm tròn

Hai hoạt động khác nhau:

- `Duration.dividedBy(long)` trả Duration với độ phân giải nano giây.
- `toMillis()` hoặc `toNanos()` trả số nguyên theo đơn vị đích; phần nhỏ hơn đơn vị bị loại bỏ.

```java
Duration d = Duration.ofNanos(1_999_999);

System.out.println(d.toMillis());   // 1
System.out.println(d.toNanos());    // 1999999
System.out.println(d.dividedBy(2)); // PT0.000999999S
```

`toMillis()` trả 1 vì 1.999.999 ns tương đương 1,999999 ms và phép chuyển sang ms lấy phần nguyên. `dividedBy(2)` có giá trị 999.999,5 ns; phần nano phân số không thể biểu diễn, nên kết quả là 999.999 ns.

Nếu nghiệp vụ cần làm tròn gần nhất, làm tròn luôn lên hoặc dùng ties-to-even, hãy triển khai chính sách tường minh. Duration không tự áp dụng một quy tắc làm tròn nghiệp vụ chung cho mọi thao tác.

## 12. Tràn số và xử lý ngoại lệ

Các phép toán nhân, đổi dấu và chuyển đơn vị có thể vượt phạm vi. Ví dụ:

```java
Duration huge = Duration.ofSeconds(Long.MAX_VALUE);

try {
    System.out.println(huge.multipliedBy(2));
} catch (ArithmeticException ex) {
    System.out.println("overflow");
}

try {
    System.out.println(Duration.ofSeconds(Long.MIN_VALUE).negated());
} catch (ArithmeticException ex) {
    System.out.println("negation overflow");
}
```

Đầu ra:

```text
overflow
negation overflow
```

Các giá trị lớn có thể đến từ dữ liệu bên ngoài. Hãy kiểm tra đầu vào và xử lý `ArithmeticException` theo hợp đồng; đừng bắt mọi ngoại lệ rồi bỏ qua vì dễ che lỗi thật.

## 13. Chương trình Java hoàn chỉnh

Lưu file **`DurationArithmeticDemo.java`**:

```java
import java.time.Duration;

public class DurationArithmeticDemo {
    public static void main(String[] args) {
        Duration base = Duration.ofSeconds(3);
        Duration halfSecond = Duration.ofMillis(500);

        System.out.println("plus = " + base.plus(halfSecond));
        System.out.println("minus = " + base.minus(halfSecond));
        System.out.println("times3 = " + halfSecond.multipliedBy(3));
        System.out.println("divide2 = " + Duration.ofSeconds(5).dividedBy(2));
        System.out.println("ratio = "
                + Duration.ofSeconds(1).dividedBy(Duration.ofMillis(300)));
        System.out.println("negated = " + halfSecond.negated());
        System.out.println("abs = " + Duration.ofMillis(-1500).abs());
        System.out.println("negativeNano = " + Duration.ofNanos(-1));
        System.out.println("negativeMillis = " + Duration.ofNanos(-1).toMillis());
        System.out.println("original = " + base);
    }
}
```

Biên dịch và chạy Java 17+:

```bash
javac DurationArithmeticDemo.java
java DurationArithmeticDemo
```

Đầu ra xác định:

```text
plus = PT3.5S
minus = PT2.5S
times3 = PT1.5S
divide2 = PT2.5S
ratio = 3
negated = PT-0.5S
abs = PT1.5S
negativeNano = PT-0.000000001S
negativeMillis = 0
original = PT3S
```

Phép toán trả duration mới; chia duration cho duration trả số khối nguyên; đổi dấu/lấy trị tuyệt đối không đổi biến gốc; duration -1 ns có thể chuyển sang 0 ms khi lấy phần nguyên.

## 14. Áp dụng trong chương trình thực tế

| Nhu cầu | API | Lưu ý |
| --- | --- | --- |
| Tổng thời gian hai bước công việc | `a.plus(b)` | Kết quả là giá trị mới |
| Thời gian còn lại = deadline - now | `Duration.between(now, deadline)` | Có thể âm khi quá hạn |
| Nhân thời gian mỗi tác vụ với số lần lặp | `perTask.multipliedBy(count)` | Kiểm tra overflow |
| Chia tổng tải thành các phần đều | `total.dividedBy(parts)` | Phần dư có thể không chia đều tới ns |
| Đếm khối nguyên trong tổng thời gian | `total.dividedBy(block)` | Trả long, bỏ phần lẻ |
| Lấy độ lớn của chênh lệch | `difference.abs()` | Chỉ dùng khi không cần dấu |
| Lật dấu một hiệu số | `difference.negated()` | Có thể overflow ở giá trị cực trị |
| Biểu diễn khoảng chờ 24 giờ | `Duration.ofDays(1)` | Khác ngày lịch tại vùng DST |
| Đổi sang mili giây cho API cũ | `duration.toMillis()` | Có thể mất micro/nano; kiểm tra phạm vi |

Với timeout hoặc thời lượng hiệu năng, giữ Duration càng lâu càng tốt rồi chỉ chuyển sang số nguyên ở ranh giới API. Luôn ghi rõ đơn vị khi dùng số nguyên: milliseconds khác nanoseconds dù cùng kiểu Java.

## 15. Lỗi thường gặp

1. **Cho rằng Duration là mutable.** `duration.plusSeconds(5);` không cập nhật biến nếu kết quả bị bỏ đi.
2. **Quên chiều của phép trừ.** `Duration.between(start, end)` là end - start; có thể âm.
3. **Nhầm chia duration với tỷ số thập phân.** `dividedBy(Duration)` trả số khối nguyên.
4. **Nhầm getNano() là tổng nano giây.** Đây là thành phần nano đã chuẩn hóa.
5. **Coi toMillis() luôn làm tròn gần nhất.** Phần nhỏ hơn ms bị loại bỏ về phía 0.
6. **Bỏ qua overflow.** Nhân, đổi dấu và chuyển đổi đơn vị có thể thất bại.
7. **Dùng abs() rồi mất thông tin nghiệp vụ.** Giữ dấu nếu cần biết trước hạn hay quá hạn.
8. **Dùng Duration cho tháng lịch.** Tháng không có độ dài cố định; hãy dùng Period và kiểu ngày giờ thích hợp.

## 16. Bài tập tự kiểm tra

**Câu 1.** `Duration.ofSeconds(3).plusMillis(500)` in ra gì?

**Đáp án:** `PT3.5S`.

**Câu 2.** `Duration.ofSeconds(5).dividedBy(2)` có giá trị gì?

**Đáp án:** `PT2.5S`.

**Câu 3.** `Duration.ofSeconds(1).dividedBy(Duration.ofMillis(300))` trả mấy?

**Đáp án:** `3`, vì chỉ đếm ba khối trọn vẹn 300 ms.

**Câu 4.** Tại sao `Duration.ofNanos(-1).toMillis()` bằng 0?

**Đáp án:** Phép đổi sang mili giây nguyên bỏ phần lẻ về 0; duration gốc vẫn là âm 1 ns.

**Câu 5.** `Duration.ofSeconds(Long.MAX_VALUE).multipliedBy(2)` gây gì?

**Đáp án:** Ném `ArithmeticException` do tràn số.

**Câu 6.** Có thể dùng `Duration.ofDays(1)` thay cho một ngày lịch ở Paris qua DST không?

**Đáp án:** Không nên. Duration là 24 giờ cố định; ngày địa phương có thể dài 23 hoặc 25 giờ.

**Ghi nhớ:** Duration hỗ trợ cộng, trừ, nhân, chia, đổi dấu và lấy trị tuyệt đối bằng các phương thức bất biến. Hiểu rõ dấu, độ phân giải nano giây, quy tắc chia nguyên và giới hạn số học giúp tránh lỗi ở timeout, đo thời lượng, lịch tác vụ và chuyển đổi đơn vị.