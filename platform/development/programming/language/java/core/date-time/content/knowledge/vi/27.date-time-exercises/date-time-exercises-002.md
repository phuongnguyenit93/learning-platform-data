# Tính tuổi, ngày kỷ niệm và hạn cuối tháng

## 1. Bài toán thực hành và các quyết định phải nêu trước

Ba yêu cầu nghe quen thuộc nhưng chứa những quy tắc khác nhau:

1. **Tính tuổi tròn** tại một ngày tham chiếu.
2. **Tìm ngày kỷ niệm kế tiếp** tính từ một ngày cho trước.
3. **Xác định hạn vào cuối một tháng đích**.

Chỉ lấy hiệu năm hoặc cộng một lượng ngày cố định chưa giải quyết đúng những yêu cầu này. Phải xử lý năm nhuận, ngày chưa đến trong năm hiện tại và tháng có độ dài khác nhau.

Bài thực hành chọn các hợp đồng sau:

| Yêu cầu | Chính sách dùng trong bài |
| --- | --- |
| Tuổi | Số năm đã hoàn thành theo ngày kỷ niệm trong năm tham chiếu |
| Ngày sinh ở tương lai | Từ chối |
| Kỷ niệm “kế tiếp” | Lần xuất hiện gần nhất **vào hoặc sau** ngày tham chiếu, có tính hôm nay |
| Ngày 29/2 trong năm thường | Truyền rõ một trong hai chính sách: 28/2 hoặc 1/3 |
| Hạn cuối tháng | Chọn tháng gốc + số tháng đi tới, rồi lấy ngày cuối tháng đó |
| Hạn chỉ có ngày | Ngày hạn vẫn được tính là còn hạn; ngày sau mới quá hạn |

Hai chính sách 29/2 là lựa chọn minh họa để làm rõ thiết kế. Ứng dụng thực tế phải chọn theo yêu cầu của mình, không tự lấy hành vi mặc định của một phương thức làm chính sách mà chưa kiểm tra.

Các hàm nhận `LocalDate asOf` hoặc `from` thay vì tự gọi đồng hồ. Bên gọi có trách nhiệm xác định ngày tham chiếu theo múi giờ nghiệp vụ. Nhờ vậy, kết quả có thể kiểm thử bằng ngày cố định.

## 2. Chọn kiểu cho từng phần dữ liệu

| Thông tin | Kiểu |
| --- | --- |
| Ngày sinh đầy đủ | `LocalDate` |
| Ngày tham chiếu | `LocalDate` |
| Mẫu ngày kỷ niệm lặp hằng năm | `MonthDay` |
| Năm muốn tạo lần kỷ niệm cụ thể | `Year` hoặc số năm được xác thực |
| Kỳ cần tìm ngày cuối tháng | `YearMonth` |
| Số ngày chờ đến lần kỷ niệm | Kết quả `long` từ `ChronoUnit.DAYS.between` |

Không dùng `MonthDay` thay toàn bộ ngày sinh khi cần tính tuổi: nó không giữ năm sinh. Ngược lại, khi chỉ mô tả mẫu nhắc ngày hằng năm, `MonthDay` nói rõ rằng chưa chọn năm cụ thể.

`LocalDate` biểu diễn ngày lịch, không chứa giờ hay múi giờ; các phép tính trong bài đều theo ngày. Xem mô hình ở [LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html).

## 3. Tính tuổi tròn bằng một ngày kỷ niệm rõ chính sách

### 3.1. Vì sao hiệu năm chưa đủ?

Người sinh ngày 10/5/1990, tại 9/5/2024:

```text
Hiệu hai số năm: 2024 - 1990 = 34
Tuổi tròn:      33, vì chưa đến ngày 10/5
```

Đúng ngày 10/5/2024, tuổi mới thành 34.

Thuật toán phù hợp với hợp đồng của bài:

1. Từ chối nếu ngày sinh sau ngày tham chiếu.
2. Lấy hiệu số năm làm giá trị ban đầu.
3. Tạo ngày kỷ niệm trong năm tham chiếu theo chính sách đã chọn.
4. Nếu ngày tham chiếu còn trước ngày kỷ niệm, giảm một tuổi.

Không tính tuổi bằng số ngày chia cho 365 hoặc 365,25. Tuổi theo ngày kỷ niệm là một quy tắc lịch, không phải một khoảng thời gian trung bình.

### 3.2. Ngày sinh 29/2 cần quy tắc bổ sung

Với ngày sinh 29/2/2000 và ngày tham chiếu 28/2/2023:

| Chính sách ở năm thường | Ngày kỷ niệm năm 2023 | Tuổi tròn |
| --- | --- | --- |
| Dùng 28/2 | `2023-02-28` | 23 |
| Dùng 1/3 | `2023-03-01` | 22 |

Đến 1/3/2023, cả hai đều cho 23. Trong năm nhuận 2024, ngày kỷ niệm là 29/2 ở cả hai chính sách; ngày 28/2 vẫn chưa đến kỷ niệm.

Một enum như `LeapDayPolicy` làm lựa chọn này hiện rõ tại nơi gọi. Không nên giấu chính sách trong một nhánh phụ mà người dùng hàm không biết.

### 3.3. Period không thay việc xác định chính sách

`Period.between(birthDate, asOf)` trả chênh lệch lịch gồm năm, tháng và ngày. `getYears()` lấy thành phần năm, không phải lời tuyên bố về mọi quy tắc tuổi của ứng dụng.

Với 29/2/2000 đến 28/2/2023, thành phần năm là 22. Trong khi đó, hàm tuổi theo chính sách kỷ niệm 28/2 của bài trả 23. Hai kết quả đang theo hai quy tắc đã được xác định khác nhau.

Có thể dùng `Period` khi hợp đồng chênh lệch lịch của nó đúng với nhu cầu. Không cần viết lại mọi phép tính, nhưng phải hiểu kết quả trước khi gọi nó là tuổi. Xem [Period](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Period.html).

## 4. Dùng chung một hàm tạo lần kỷ niệm trong năm

Hàm `occurrence(monthDay, year, policy)` trong chương trình làm điểm dùng chung:

- Với ngày bình thường: ghép tháng-ngày với năm.
- Với 29/2 trong năm nhuận: trả đúng 29/2.
- Với 29/2 trong năm thường: chọn 28/2 hoặc 1/3 theo enum.

`Year.atMonthDay` tự lùi 29/2 về 28/2 ở năm thường. Bài chỉ dùng hành vi đó cho nhánh chính sách 28/2; nhánh 1/3 được thể hiện riêng.

Nhờ dùng chung hàm, phép tính tuổi và chức năng nhắc kỷ niệm không vô tình áp hai chính sách khác nhau. Tuy vậy, nếu hai chức năng thực sự có yêu cầu khác nhau, chúng có thể truyền enum khác nhau một cách có chủ đích.

Hợp đồng của tháng-ngày và phép gắn năm được mô tả tại [MonthDay](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/MonthDay.html).

## 5. Tìm ngày kỷ niệm kế tiếp, có tính hôm nay

Hàm `nextOnOrAfter` thực hiện:

1. Tạo lần kỷ niệm trong năm của ngày tham chiếu.
2. Nếu ngày đó chưa qua, trả ngay.
3. Nếu đã qua, tạo lại lần kỷ niệm từ **tháng-ngày gốc** trong năm kế tiếp.

Ví dụ kỷ niệm ngày 10/5:

| Ngày tham chiếu | Kết quả |
| --- | --- |
| `2024-05-09` | `2024-05-10` |
| `2024-05-10` | `2024-05-10` |
| `2024-05-11` | `2025-05-10` |

Nếu yêu cầu là “lần tiếp theo sau hôm nay” và loại trừ ngày hiện tại, điều kiện phải thay đổi rõ ràng. Không dùng cùng một tên mơ hồ rồi để bên gọi tự đoán.

### Không cộng một năm vào ngày đã bị điều chỉnh

Với mẫu gốc 29/2 và chính sách 28/2, lần năm 2023 là 28/2/2023. Nếu lấy ngày đó rồi `plusYears(1)`, kết quả là 28/2/2024, không tự khôi phục ngày 29.

Cần giữ `MonthDay.of(2, 29)` rồi ghép với năm 2024. Kết quả mới đúng là 29/2/2024.

Đó là lý do thuật toán giữ mẫu gốc thay vì chỉ giữ lần xuất hiện đã điều chỉnh. Tương tự, số năm đã kỷ niệm đòi hỏi ngày bắt đầu đầy đủ; một `MonthDay` riêng lẻ chỉ đủ mô tả mẫu ngày lặp.

## 6. Tính hạn cuối tháng bằng YearMonth

Hợp đồng `endOfTargetMonth(base, monthsAhead)`:

- `monthsAhead = 0`: cuối tháng chứa `base`.
- `monthsAhead = 1`: cuối tháng kế tiếp.
- `monthsAhead = 2`: cuối tháng cách hai tháng.
- Giá trị âm bị từ chối trong bài này.

Cách tính là:

```text
LocalDate gốc → YearMonth gốc
             → cộng số tháng
             → atEndOfMonth()
```

Ví dụ:

| Ngày gốc | Số tháng đi tới | Hạn |
| --- | --- | --- |
| `2024-01-31` | 1 | `2024-02-29` |
| `2024-01-31` | 2 | `2024-03-31` |
| `2023-01-31` | 1 | `2023-02-28` |
| `2024-12-10` | 1 | `2025-01-31` |

Không thay bằng “cộng 30 ngày”. Cũng không cộng tháng lặp trên ngày đã bị lùi rồi mong ngày cuối tháng luôn được khôi phục.

`YearMonth` mô hình hóa đúng kỳ tháng, còn `atEndOfMonth` chọn ngày cuối cùng theo năm-tháng đích. Xem [YearMonth](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/YearMonth.html).

Nếu hạn rơi vào cuối tuần hoặc ngày nghỉ, bài vẫn trả đúng ngày cuối tháng. Di chuyển sang ngày làm việc khác là một quy tắc bổ sung cần được nêu riêng, không tự thêm vào phép tính.

## 7. Ngày hạn khác thời điểm hết hạn

Bài dùng hạn dạng `LocalDate` và chọn chính sách **còn hạn trong chính ngày hạn**:

```text
asOf trước hạn     → chưa quá hạn
asOf bằng hạn      → chưa quá hạn
asOf sau hạn       → quá hạn
```

Theo hợp đồng này, điều kiện quá hạn là `asOf.isAfter(deadline)`.

Nếu hệ thống cần quyết định ở mức thời điểm, chẳng hạn khóa thao tác khi vừa sang ngày mới, phải bổ sung múi giờ và ranh giới thời điểm. Có thể lấy đầu ngày sau hạn làm cận trên loại trừ theo vùng đã quy định. Không tự coi `LocalDate` là UTC hoặc ghép `23:59:59` như thể đó luôn là cuối cùng của ngày.

Các hàm trong chương trình không xử lý giờ chốt, lịch nghỉ hoặc vùng thời gian. Chúng nhận ngày tham chiếu đã được bên gọi xác định.

## 8. Chương trình Java 17+ chạy độc lập

Lưu mã sau thành `CalendarBusinessPractice.java`. Chương trình dùng dữ liệu cố định để tái lập kết quả, không cần thư viện ngoài.

```java
import java.time.LocalDate;
import java.time.MonthDay;
import java.time.Period;
import java.time.Year;
import java.time.YearMonth;
import java.time.temporal.ChronoUnit;
import java.util.Objects;

public class CalendarBusinessPractice {
    public enum LeapDayPolicy { FEBRUARY_28, MARCH_1 }

    private static LocalDate d(String value) {
        return LocalDate.parse(value);
    }

    public static LocalDate occurrence(MonthDay day, int year,
                                       LeapDayPolicy policy) {
        Objects.requireNonNull(day, "day");
        Objects.requireNonNull(policy, "policy");
        Year target = Year.of(year);
        if (day.equals(MonthDay.of(2, 29)) && !target.isLeap()
                && policy == LeapDayPolicy.MARCH_1) {
            return LocalDate.of(year, 3, 1);
        }
        return target.atMonthDay(day);
    }

    public static int ageOn(LocalDate birthDate, LocalDate asOf,
                            LeapDayPolicy policy) {
        Objects.requireNonNull(birthDate, "birthDate");
        Objects.requireNonNull(asOf, "asOf");
        Objects.requireNonNull(policy, "policy");
        if (birthDate.isAfter(asOf)) {
            throw new IllegalArgumentException("birthDate must not be in the future");
        }
        int age = asOf.getYear() - birthDate.getYear();
        LocalDate anniversary = occurrence(MonthDay.from(birthDate),
                asOf.getYear(), policy);
        return asOf.isBefore(anniversary) ? age - 1 : age;
    }

    public static LocalDate nextOnOrAfter(MonthDay day, LocalDate from,
                                         LeapDayPolicy policy) {
        Objects.requireNonNull(from, "from");
        LocalDate candidate = occurrence(day, from.getYear(), policy);
        if (candidate.isBefore(from)) {
            return occurrence(day, from.getYear() + 1, policy);
        }
        return candidate;
    }

    public static LocalDate endOfTargetMonth(LocalDate base, long monthsAhead) {
        Objects.requireNonNull(base, "base");
        if (monthsAhead < 0) {
            throw new IllegalArgumentException("monthsAhead must be non-negative");
        }
        return YearMonth.from(base).plusMonths(monthsAhead).atEndOfMonth();
    }

    private static int checks;

    private static void eq(Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    private static void rejects(Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            checks++;
            return;
        }
        throw new AssertionError("Expected IllegalArgumentException");
    }

    public static void main(String[] args) {
        LeapDayPolicy feb28 = LeapDayPolicy.FEBRUARY_28;
        LeapDayPolicy mar1 = LeapDayPolicy.MARCH_1;
        LocalDate birth = d("1990-05-10");
        LocalDate asOf = d("2024-05-09");
        eq(ageOn(birth, asOf, feb28), 33);
        eq(ageOn(birth, d("2024-05-10"), feb28), 34);
        eq(ageOn(birth, d("2024-05-11"), feb28), 34);
        eq(ageOn(birth, birth, feb28), 0);
        rejects(() -> ageOn(d("2025-01-01"), asOf, feb28));

        LocalDate leapBirth = d("2000-02-29");
        eq(ageOn(leapBirth, d("2023-02-28"), feb28), 23);
        eq(ageOn(leapBirth, d("2023-02-28"), mar1), 22);
        eq(ageOn(leapBirth, d("2023-03-01"), feb28), 23);
        eq(ageOn(leapBirth, d("2023-03-01"), mar1), 23);
        eq(ageOn(leapBirth, d("2024-02-28"), feb28), 23);
        eq(ageOn(leapBirth, d("2024-02-29"), feb28), 24);
        eq(ageOn(leapBirth, d("2024-02-29"), mar1), 24);
        eq(Period.between(leapBirth, d("2023-02-28")).getYears(), 22);

        MonthDay birthday = MonthDay.from(birth);
        eq(nextOnOrAfter(birthday, asOf, feb28), d("2024-05-10"));
        eq(nextOnOrAfter(birthday, d("2024-05-10"), feb28), d("2024-05-10"));
        eq(nextOnOrAfter(birthday, d("2024-05-11"), feb28), d("2025-05-10"));
        MonthDay leapDay = MonthDay.of(2, 29);
        eq(nextOnOrAfter(leapDay, d("2023-02-28"), feb28), d("2023-02-28"));
        eq(nextOnOrAfter(leapDay, d("2023-02-28"), mar1), d("2023-03-01"));
        eq(nextOnOrAfter(leapDay, d("2023-03-01"), feb28), d("2024-02-29"));

        eq(endOfTargetMonth(asOf, 0), d("2024-05-31"));
        eq(endOfTargetMonth(d("2024-01-31"), 1), d("2024-02-29"));
        eq(endOfTargetMonth(d("2024-01-31"), 2), d("2024-03-31"));
        eq(endOfTargetMonth(d("2023-01-31"), 1), d("2023-02-28"));
        eq(endOfTargetMonth(d("2024-12-10"), 1), d("2025-01-31"));
        rejects(() -> endOfTargetMonth(asOf, -1));

        LocalDate nextBirthday = nextOnOrAfter(birthday, asOf, feb28);
        LocalDate deadline = endOfTargetMonth(asOf, 0);
        eq(ChronoUnit.DAYS.between(asOf, nextBirthday), 1L);
        eq(deadline.isAfter(deadline), false);
        eq(deadline.plusDays(1).isAfter(deadline), true);

        System.out.println("asOf=" + asOf);
        System.out.println("age=" + ageOn(birth, asOf, feb28));
        System.out.println("nextBirthday=" + nextBirthday);
        System.out.println("daysUntilBirthday=" + ChronoUnit.DAYS.between(asOf, nextBirthday));
        System.out.println("monthEndDeadline=" + deadline);
        System.out.println("leapAgeFeb28Policy=" + ageOn(leapBirth, d("2023-02-28"), feb28));
        System.out.println("leapAgeMarch1Policy=" + ageOn(leapBirth, d("2023-02-28"), mar1));
        System.out.println("PASS checks=" + checks);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 CalendarBusinessPractice.java
java CalendarBusinessPractice
```

Stdout:

```text
asOf=2024-05-09
age=33
nextBirthday=2024-05-10
daysUntilBirthday=1
monthEndDeadline=2024-05-31
leapAgeFeb28Policy=23
leapAgeMarch1Policy=22
PASS checks=28
```

Hàm `eq` chủ động ném `AssertionError` khi kết quả sai nên không cần cờ `-ea`. Hàm `rejects` xác nhận các đầu vào nằm ngoài hợp đồng bị từ chối.

Bộ kiểm tra gồm:

- Trước, đúng và sau sinh nhật.
- Tuổi bằng 0 tại ngày sinh.
- Ngày sinh nằm trong tương lai.
- Sinh 29/2 ở năm thường với hai chính sách.
- Ngày 29/2 thật trong năm nhuận.
- Kỷ niệm có tính hôm nay và qua năm tiếp theo.
- Khôi phục 29/2 từ mẫu gốc.
- Cuối tháng 2 năm thường/nhuận.
- Hạn đi qua ranh giới năm.
- Số tháng âm và ý nghĩa ngày quá hạn.

Các kết quả năm 2023/2024 là dữ liệu giả lập phục vụ kiểm thử, không phải “ngày hiện tại” tại thời điểm chạy.

## 9. Đọc luồng xử lý của tình huống tổng hợp

Với người sinh `1990-05-10` và ngày tham chiếu `2024-05-09`:

1. Hiệu năm ban đầu là 34.
2. Kỷ niệm trong năm tham chiếu là 10/5/2024.
3. Ngày tham chiếu còn trước kỷ niệm, nên tuổi tròn là 33.
4. Kỷ niệm gần nhất vào hoặc sau ngày tham chiếu vẫn là 10/5/2024.
5. Chênh lệch hai `LocalDate` là một ngày.
6. Kỳ tháng của ngày tham chiếu là 2024-05, nên hạn cuối tháng là 31/5/2024.

Mỗi bước dùng kiểu đúng với ý nghĩa. Không định dạng thành chuỗi rồi tách năm/tháng/ngày để tính. Khi cần hiển thị, mới định dạng các kết quả ở đầu ra.

Việc trả riêng tuổi, lần kỷ niệm và hạn giúp mỗi quy tắc có đầu vào rõ ràng. Không nên gom ba kết quả vào một chuỗi mô tả rồi bắt chức năng khác phân tích lại.

## 10. Những lỗi dễ mắc

| Lỗi | Ví dụ sai lệch | Cách tránh |
| --- | --- | --- |
| Chỉ trừ số năm | Chưa đến sinh nhật nhưng đã tăng tuổi | So với kỷ niệm trong năm tham chiếu |
| Chia số ngày cho 365 | Không theo ngày kỷ niệm | Dùng phép tính lịch đúng chính sách |
| Không có quy tắc 29/2 | Hai chức năng trả tuổi khác nhau | Truyền chính sách rõ ràng |
| Mặc định `Period.getYears` đúng mọi yêu cầu | Khác chính sách 28/2 trong ví dụ | Đối chiếu hợp đồng trước khi dùng |
| Cộng năm vào ngày đã lùi | Năm nhuận sau vẫn còn 28/2 | Ghép lại từ `MonthDay` gốc |
| Cộng 30 ngày để lấy tháng sau | Sai với độ dài tháng thực tế | Dùng `YearMonth.plusMonths` |
| Mặc định ngày cuối tháng luôn là 31 | Tháng 2 hoặc tháng 4 không có ngày đó | Dùng `atEndOfMonth` |
| Không xác định có tính hôm nay không | Nhắc kỷ niệm bị nhảy sang năm sau | Đặt rõ điều kiện bao gồm/loại trừ |
| Gọi đồng hồ nhiều nơi trong cùng tác vụ | Ngày tham chiếu có thể lệch qua nửa đêm | Truyền một `asOf` đã xác định |

## 11. Bài tập mở rộng với kết quả mong đợi

### Bài 1: Tuổi ở hai phía sinh nhật

Người sinh 20/12/2000:

- Tại 19/12/2024: 23 tuổi.
- Tại 20/12/2024: 24 tuổi.
- Tại 21/12/2024: 24 tuổi.

Thêm ba ca này mà không dùng ngày hệ thống.

### Bài 2: Kỷ niệm nghiêm ngặt sau ngày tham chiếu

Viết hàm chỉ trả lần xuất hiện **sau** ngày tham chiếu:

- Với mẫu 10/5 và ngày 10/5/2024, kết quả phải là 10/5/2025.
- Với ngày 9/5/2024, kết quả vẫn là 10/5/2024.

Chỉ thay đổi điều kiện chọn ứng viên, không làm mất mẫu tháng-ngày gốc.

### Bài 3: Ngày nhuận và năm thế kỷ

Với mẫu 29/2:

- Năm 2100 không nhuận: chọn 28/2 hoặc 1/3 tùy chính sách.
- Năm 2000 nhuận: giữ 29/2.

Không dùng điều kiện “chia hết cho 4” làm toàn bộ quy tắc.

### Bài 4: Dãy hạn cuối tháng

Từ tháng gốc 1/2024, tạo ba kỳ đầu bằng số tháng 0, 1, 2:

```text
2024-01-31
2024-02-29
2024-03-31
```

Mỗi kỳ nên được tính từ tháng gốc và số thứ tự kỳ. Đừng dùng ngày đã điều chỉnh ở kỳ trước làm toàn bộ quy tắc của kỳ sau.

### Bài 5: Chính sách ngày nghỉ

Giữ nguyên hàm tìm ngày cuối tháng. Thiết kế một bước riêng điều chỉnh ngày hạn theo lịch làm việc được cung cấp. Nêu rõ được phép lùi hay tiến, và điều chỉnh đó có được chuyển sang tháng khác không. Chưa có lịch nghỉ và quy tắc thì chưa thể khẳng định một ngày hạn thay thế.

Các bài toán lịch đúng không chỉ cần một API trả ngày hợp lệ. Chúng cần đầu vào đúng kiểu, ngày tham chiếu nhất quán và các chính sách ranh giới được biểu đạt rõ trong mã cùng ca kiểm tra.
