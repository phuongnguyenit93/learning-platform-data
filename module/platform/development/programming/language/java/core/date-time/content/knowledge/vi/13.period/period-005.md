# Chuẩn hóa năm và tháng bằng `Period.normalized()`

## 1. Hiểu đúng việc chuẩn hóa

`Period` biểu diễn một lượng thời gian theo lịch ISO bằng ba thành phần: năm, tháng và ngày. Khi nhập thời hạn gia hạn là 17 tháng, ta có thể muốn hiển thị thành 1 năm 5 tháng; khi cộng thêm nhiều tháng vào một thời hạn đã có năm, phần tháng cũng có thể vượt quá 11.

`normalized()` trả về một giá trị `Period` có phần năm–tháng được thu gọn theo quan hệ **12 tháng = 1 năm**. Phần ngày được giữ nguyên. Đối tượng ban đầu không bị sửa vì `Period` là bất biến. Các quy tắc API này được mô tả tại [Java SE 21 — Period.normalized()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Period.html#normalized()).

Ví dụ tự xây dựng trong bài:

```text
1 năm + 17 tháng + 40 ngày
          ↓ normalized()
2 năm +  5 tháng + 40 ngày
```

Hai cách viết đều có phần năm–tháng tương ứng 29 tháng. Không có bước biến 40 ngày thành 1 tháng 10 ngày: muốn biết 40 ngày đi qua những tháng nào phải có ngày bắt đầu và lịch cụ thể.

## 2. Cơ chế tính: gom tháng rồi tách lại

Có thể tự tính kết quả để kiểm tra cách dùng API bằng công thức sau. Đây là mô hình giải thích; mã ứng dụng nên gọi trực tiếp `normalized()`:

```java
// Minh họa bên trong một phương thức; p là một Period đã có.
long totalMonths = p.getYears() * 12L + p.getMonths();
int years = Math.toIntExact(totalMonths / 12);
int months = (int) (totalMonths % 12);
Period result = Period.of(years, months, p.getDays());
```

Hậu tố `L` làm cho phép nhân được thực hiện bằng `long`, tránh tràn `int` ở bước trung gian. Sau khi chuẩn hóa thành công:

- Tổng tháng được bảo toàn: `p.toTotalMonths() == p.normalized().toTotalMonths()`.
- Phần tháng nằm trong khoảng `-11` đến `11`.
- Nếu năm và tháng đều khác 0 thì chúng cùng dấu.
- Phần ngày bằng đúng phần ngày ban đầu, kể cả khi âm hoặc lớn hơn 31.
- Chuẩn hóa lần nữa không đổi giá trị: `n.equals(n.normalized())` là `true`.

Không nên chỉ lấy `getMonths() / 12` rồi cộng vào năm cũ: cách tính đó có thể bỏ sót việc triệt tiêu giữa năm dương và tháng âm. Chẳng hạn `(1 năm, -17 tháng)` phải gom thành `12 - 17 = -5` tháng, rồi mới tách lại thành `(0 năm, -5 tháng)`.

### Số âm và dấu của phần dư

Phép chia số nguyên trong Java cắt phần thập phân về 0. Vì vậy `-17 / 12` bằng `-1`, còn `-17 % 12` bằng `-5`. Kết quả là âm 1 năm âm 5 tháng, không phải âm 2 năm dương 7 tháng. Không thay phép chia này bằng `Math.floorDiv` nếu đang muốn mô phỏng đúng `normalized()`.

| Giá trị tạo ra | Tổng tháng trước chuẩn hóa | Kết quả `normalized()` | Điều cần quan sát |
| --- | ---: | --- | --- |
| `Period.ofMonths(24)` | 24 | `P2Y` | Tháng bằng 0 được lược khi in |
| `Period.ofMonths(-17)` | -17 | `P-1Y-5M` | Năm và tháng âm cùng dấu |
| `Period.of(1, -17, 4)` | -5 | `P-5M4D` | Ngày dương không bị đổi theo dấu tháng |
| `Period.of(-1, 17, -4)` | 5 | `P5M-4D` | Ngày âm vẫn còn nguyên |
| `Period.of(1, -12, 0)` | 0 | `P0D` | Năm và tháng triệt tiêu hoàn toàn |
| `Period.ofDays(40)` | 0 | `P40D` | 40 ngày không trở thành tháng |

Các chuỗi `P...Y...M...D` trong bảng là cách `Period.toString()` in giá trị; `M` ở đây là tháng. Chuẩn hóa năm–tháng không phải là thao tác lấy trị tuyệt đối, cũng không đảm bảo mọi thành phần của cả `Period` cùng dấu.

## 3. Chương trình kiểm chứng đầy đủ

Lưu mã sau vào `PeriodNormalizedDemo.java`. Chương trình dùng API có trên Java 17 trở lên, không cần thư viện ngoài:

```java
import java.time.LocalDate;
import java.time.Period;

public class PeriodNormalizedDemo {
    public static void main(String[] args) {
        Period original = Period.of(1, 17, 40);
        Period normalized = original.normalized();
        System.out.println("original = " + original);
        System.out.println("normalized = " + normalized);
        System.out.println("total months = " + original.toTotalMonths()
                + " -> " + normalized.toTotalMonths());
        System.out.println("normalized again = "
                + normalized.equals(normalized.normalized()));

        Period[] samples = {
            Period.ofMonths(24),
            Period.ofMonths(-17),
            Period.of(1, -17, 4),
            Period.of(-1, 17, -4),
            Period.of(1, -12, 0),
            Period.of(0, 0, 40)
        };
        for (Period sample : samples) {
            System.out.println(sample + " -> " + sample.normalized());
        }

        Period a = Period.ofMonths(17);
        Period b = Period.of(1, 5, 0);
        System.out.println("equals before = " + a.equals(b));
        System.out.println("equals after = "
                + a.normalized().equals(b.normalized()));

        LocalDate start = LocalDate.of(2024, 1, 31);
        System.out.println("date before = " + start.plus(original));
        System.out.println("date after = " + start.plus(normalized));

        try {
            Period.of(Integer.MAX_VALUE, 12, 0).normalized();
        } catch (ArithmeticException ex) {
            System.out.println("overflow = ArithmeticException");
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 PeriodNormalizedDemo.java
java PeriodNormalizedDemo
```

Kết quả chuẩn:

```text
original = P1Y17M40D
normalized = P2Y5M40D
total months = 29 -> 29
normalized again = true
P24M -> P2Y
P-17M -> P-1Y-5M
P1Y-17M4D -> P-5M4D
P-1Y17M-4D -> P5M-4D
P1Y-12M -> P0D
P40D -> P40D
equals before = false
equals after = true
date before = 2026-08-09
date after = 2026-08-09
overflow = ArithmeticException
```

`original` vẫn là `P1Y17M40D`, chứng minh lời gọi đã tạo giá trị kết quả mà không sửa đầu vào. Cả hai cách biểu diễn đều đưa ngày `2024-01-31` tới `2026-08-09` trong ví dụ: phần năm–tháng tương ứng 29 tháng, sau đó cộng 40 ngày. Việc chuẩn hóa không cần biết ngày bắt đầu; thao tác cộng lên một ngày mới cần ngày bắt đầu.

Không suy rộng ví dụ thành quy tắc rằng mọi chuỗi lệnh cộng riêng rẽ đều tương đương. Chẳng hạn, tự viết nhiều lần `plusYears` rồi `plusMonths` có thể làm phát sinh điều chỉnh cuối tháng ở các bước trung gian. Trong chương trình, ta cộng nguyên một `Period` bằng `start.plus(period)`.

## 4. Khi nào nên gọi và khi nào cần giữ đầu vào?

### Khi cần biểu diễn năm–tháng thống nhất

Một màn hình có thể nhận thời hạn bằng tháng nhưng trình bày theo năm và tháng. Với dữ liệu 17 tháng, gọi `normalized()` trước khi đọc `getYears()` và `getMonths()` sẽ cho 1 năm 5 tháng. Nếu chỉ cần con số tổng tháng thì dùng `toTotalMonths()`; phương thức đó không đổi cả `Period` và không tính phần ngày vào tổng tháng.

Các phép tạo hoặc cộng không đảm bảo tự thu gọn tháng. Ví dụ minh họa trong một phương thức:

```java
Period term = Period.ofMonths(11).plusMonths(8);
System.out.println(term);              // P19M
term = term.normalized();
System.out.println(term);              // P1Y7M
```

Phải sử dụng kết quả trả về. Chỉ viết `term.normalized();` rồi tiếp tục dùng `term` sẽ vẫn giữ giá trị cũ.

### Khi so sánh hoặc dùng làm khóa

Chương trình kiểm chứng cho thấy `Period.ofMonths(17)` không `equals` với `Period.of(1, 5, 0)` trước chuẩn hóa; sau chuẩn hóa thì chúng bằng nhau. Khi nghiệp vụ chấp nhận hai cách viết này là cùng một thời hạn, có thể chuẩn hóa cả hai trước khi so sánh hoặc trước khi đưa vào tập hợp/khóa ánh xạ. Chuẩn hóa một phía không đủ nếu phía kia còn cách biểu diễn chưa thu gọn.

Đó là quyết định về cách biểu diễn dữ liệu. Nếu yêu cầu giữ nguyên điều khoản “17 tháng” do người dùng nhập, nên lưu đầu vào riêng thay vì thay thế mọi giá trị bằng “1 năm 5 tháng”. Đồng thời, không dùng `normalized()` để kết luận 1 tháng bằng 30 ngày: phần ngày vẫn độc lập.

## 5. Giới hạn và lỗi thường gặp

**Tràn số vẫn có thể xảy ra.** Mỗi thành phần của `Period` được lưu bằng `int`. Ví dụ cuối chương trình tạo được `(Integer.MAX_VALUE năm, 12 tháng, 0 ngày)`, nhưng chuẩn hóa sẽ cần thêm 1 năm nên ném `ArithmeticException`. Chỉ bắt ngoại lệ khi chương trình có cách xử lý dữ liệu không hợp lệ rõ ràng; không đổi lỗi tràn thành `Period.ZERO` vì như vậy sẽ làm sai thời hạn.

**Không tính thời lượng theo giây.** Kết quả sau chuẩn hóa vẫn là lượng thời gian theo lịch, không thành `Duration` và không cho tổng số giây. Nếu bài toán hỏi bao nhiêu ngày thực tế từ một mốc cụ thể, hãy xác định mốc và tính trên ngày; chia số ngày cho 30 không phải chuẩn hóa `Period`.

**Không dùng để kiểm tra thời hạn có hợp lệ về nghiệp vụ hay không.** `P5M-4D` có thể là kết quả chuẩn hóa hợp lệ nhưng vẫn trái quy định “mọi thành phần phải không âm” của ứng dụng. Kiểm tra nghiệp vụ là bước riêng sau khi xác định rõ quy định áp dụng cho dữ liệu gốc hay dữ liệu chuẩn hóa.

## 6. Tự thực hành

Trước khi chạy, tự dự đoán giá trị của `Period.of(2, -25, 7).normalized()` và giải thích vì sao phần ngày không đổi. Đáp án là `P-1M7D`: `2 * 12 - 25 = -1` tháng, còn 7 ngày giữ nguyên.

Tiếp theo, dự đoán `Period.of(0, 12, -365).normalized()`. Đáp án là `P1Y-365D`, không phải `P0D`: thao tác chỉ đổi 12 tháng thành 1 năm, không triệt tiêu năm với 365 ngày. Hai câu này giúp kiểm tra xem bạn đã phân biệt được chuẩn hóa cách biểu diễn năm–tháng với tính khoảng cách giữa các ngày hay chưa.
