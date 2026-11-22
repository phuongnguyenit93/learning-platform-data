# Đếm ngày bằng ChronoUnit và sinh dãy ngày bằng datesUntil() trong Java LocalDate

## 1. Mục tiêu

Bài học tập trung vào hai thao tác thường gặp với `java.time.LocalDate`:

1. **Tính khoảng cách theo ngày** giữa hai ngày bằng `ChronoUnit.DAYS.between(start, end)` hoặc `start.until(end, ChronoUnit.DAYS)`.
2. **Sinh các ngày trong một khoảng** bằng `start.datesUntil(endExclusive)` hoặc `start.datesUntil(endExclusive, step)`, rồi dùng Java Stream để lọc, đếm và biến đổi.

Sau bài này, bạn sẽ biết cách xử lý đầu cuối khoảng **bao gồm đầu, loại trừ cuối** `[start, end)`, năm nhuận, chiều tính ngày, các bước theo ngày/tuần/tháng, giới hạn stream và những tình huống biên.

Các ví dụ dùng **Java 17+**, chỉ dựa trên thư viện chuẩn và ngày xác định để không phụ thuộc ngày hiện tại.

## 2. Đặt đúng ngữ cảnh: LocalDate là một ngày lịch

`LocalDate` biểu diễn **năm, tháng, ngày** theo lịch ISO-8601, ví dụ `2024-02-29`. Giá trị này:

- Không chứa giờ, phút, giây.
- Không chứa múi giờ (`ZoneId`) hoặc độ lệch UTC (`ZoneOffset`).
- Không tự chỉ tới một thời điểm duy nhất trên trục thời gian toàn cầu.
- Là đối tượng **bất biến (immutable)**: `plusDays`, `minusDays`, `withDayOfMonth` trả về kết quả, không thay đổi giá trị gốc.

Ví dụ:

```java
LocalDate first = LocalDate.of(2024, 2, 28);
LocalDate second = first.plusDays(1);

System.out.println(first);  // 2024-02-28
System.out.println(second); // 2024-02-29
```

Đây là **đoạn minh họa**, cần `import java.time.LocalDate;` và được đặt trong thân phương thức.

Khi yêu cầu là “từ ngày A đến ngày B có bao nhiêu ngày **trên lịch**?”, `LocalDate` rất phù hợp. Khi yêu cầu là “hai sự kiện cách nhau chính xác bao nhiêu giờ/giây?”, hãy dùng `Instant`, `Duration` hoặc kiểu có múi giờ phù hợp. Một ngày lịch địa phương không nhất thiết luôn dài 24 giờ khi có thay đổi giờ mùa hè (DST).

## 3. Đếm số ngày bằng ChronoUnit.DAYS.between()

`ChronoUnit` nằm trong gói `java.time.temporal`. Phương thức:

```java
long days = ChronoUnit.DAYS.between(startInclusive, endExclusive);
```

Đây là đoạn minh họa, cần `import java.time.LocalDate;` và `import java.time.temporal.ChronoUnit;`; cả hai tham số là `LocalDate`.

**Kết quả là số ngày lịch có dấu** cần đi từ `start` tới `end`. Khi bắt đầu và kết thúc cùng ngày, kết quả bằng `0`. Khi kết thúc sau bắt đầu, kết quả dương; khi kết thúc trước bắt đầu, kết quả âm.

| Start | End | `DAYS.between(start, end)` | Diễn giải |
| --- | --- | ---: | --- |
| 2024-05-01 | 2024-05-01 | 0 | Cùng ngày |
| 2024-05-01 | 2024-05-02 | 1 | Cách một ngày |
| 2024-05-01 | 2024-05-04 | 3 | Ba ngày |
| 2024-05-04 | 2024-05-01 | -3 | Đi ngược ba ngày |
| 2024-02-27 | 2024-03-02 | 4 | Có 29/2 vì năm 2024 nhuận |

Chú ý tên `endExclusive` diễn tả quy ước thường dùng khi **đếm/sinh các ngày trong khoảng**. Phép `between` tính **độ chênh giữa hai mốc ngày**; nó không tự có khái niệm “bao gồm ngày kết thúc” của một danh sách.

Ví dụ minh họa:

```java
LocalDate start = LocalDate.of(2024, 2, 27);
LocalDate end = LocalDate.of(2024, 3, 2);

long forward = ChronoUnit.DAYS.between(start, end); // 4
long backward = ChronoUnit.DAYS.between(end, start); // -4
```

Năm nhuận được xử lý bởi thư viện: các ngày 27/2 → 28/2 → 29/2 → 1/3 → 2/3 có **bốn bước dịch chuyển một ngày**.

### 3.1. until() là cách viết tương ứng

`LocalDate` cung cấp `until(Temporal endExclusive, TemporalUnit unit)`:

```java
long a = ChronoUnit.DAYS.between(start, end);
long b = start.until(end, ChronoUnit.DAYS);
```

Đây là đoạn minh họa, cần import như trên và hai biến `start`, `end` là `LocalDate`. Trong trường hợp hai `LocalDate` như ví dụ, `a == b`.

Dạng `ChronoUnit.DAYS.between(a, b)` đặc biệt dễ đọc khi cần nói “khoảng cách giữa hai giá trị”. Dạng `start.until(end, ChronoUnit.DAYS)` thuận tiện khi đã có biến `start` và đang làm việc theo API của nó.

`ChronoUnit.DAYS.between` cũng có thể làm việc với các kiểu `Temporal` được hỗ trợ khác; **đơn vị và quy tắc tính khác nhau theo loại temporal**. Bài này chỉ nói về **hai LocalDate** nên đếm theo ngày lịch.

### 3.2. Không đồng nhất số ngày với Period và Duration

Ba API trả lời những câu hỏi khác nhau:

| API | Trả về | Hợp đồng |
| --- | --- | --- |
| `ChronoUnit.DAYS.between(a,b)` | `long` | Chênh lệch theo **số ngày lịch** giữa hai `LocalDate` |
| `Period.between(a,b)` | `Period` | Khoảng cách theo **năm-tháng-ngày** |
| `Duration.between(a,b)` | `Duration` | Khoảng cách theo **giây và nano giây**, không áp dụng trực tiếp cho hai `LocalDate` vì chúng không có giờ |

Ví dụ với ngày cuối tháng:

```java
LocalDate a = LocalDate.of(2024, 1, 31);
LocalDate b = LocalDate.of(2024, 2, 29);

System.out.println(ChronoUnit.DAYS.between(a, b));   // 29
System.out.println(ChronoUnit.MONTHS.between(a, b)); // 0
System.out.println(Period.between(a, b));            // P29D
```

Đây là đoạn minh họa, cần `import java.time.LocalDate;`, `import java.time.Period;` và `import java.time.temporal.ChronoUnit;`. Kết quả `MONTHS.between == 0` xuất phát từ quy tắc **tháng hoàn chỉnh**, không có nghĩa hai ngày thuộc cùng tháng. Với câu hỏi “bao nhiêu ngày?”, hãy yêu cầu `DAYS`.

### 3.3. Có nên dùng getDays() của Period để đếm ngày?

**Không.** `Period.getDays()` chỉ trả về **thành phần ngày còn lại** trong một period gồm năm, tháng và ngày; nó không tự trả về tổng số ngày.

```java
Period period = Period.between(
        LocalDate.of(2024, 1, 1),
        LocalDate.of(2024, 3, 1));

System.out.println(period);           // P2M
System.out.println(period.getDays()); // 0
System.out.println(ChronoUnit.DAYS.between(
        LocalDate.of(2024, 1, 1),
        LocalDate.of(2024, 3, 1)));    // 60
```

Đây là đoạn minh họa trong một phương thức với các import `LocalDate`, `Period` và `ChronoUnit`. Muốn đếm tổng ngày giữa hai `LocalDate`, hãy dùng `ChronoUnit.DAYS.between()`.

## 4. datesUntil(endExclusive): sinh dãy ngày liên tiếp

Từ Java 9, `LocalDate` có phương thức:

```java
Stream<LocalDate> days = start.datesUntil(endExclusive);
```

Đây là đoạn minh họa cần `import java.time.LocalDate;` và `import java.util.stream.Stream;`. Phương thức trả về một **Stream các LocalDate**, bắt đầu tại `start` (nếu khoảng không rỗng), tiến thêm **một ngày mỗi phần tử**, và **không chứa endExclusive**.

Với `start = 2024-02-27` và `endExclusive = 2024-03-02`:

```text
Khoảng: [2024-02-27, 2024-03-02)
Phần tử: 2024-02-27
         2024-02-28
         2024-02-29
         2024-03-01
Không gồm: 2024-03-02
```

Các quy tắc của overload một tham số:

- `start.isBefore(endExclusive)` → stream tiến theo từng ngày.
- `start.equals(endExclusive)` → stream rỗng.
- `endExclusive.isBefore(start)` → `IllegalArgumentException`; nếu cần dãy giảm dần, dùng overload với `Period` âm phù hợp.
- `datesUntil()` **không sửa** giá trị `start`.
- Stream mang tính **lazy**: phần tử được xử lý khi một terminal operation như `count()`, `forEach()`, `toList()` được thực thi.

Khi đầu cuối cách nhau `n` ngày dương, dãy bước một ngày có đúng `n` phần tử:

```java
LocalDate a = LocalDate.of(2024, 2, 27);
LocalDate b = LocalDate.of(2024, 3, 2);

long difference = ChronoUnit.DAYS.between(a, b); // 4
long count = a.datesUntil(b).count();              // 4
```

Đây là đoạn minh họa trong một phương thức cần `LocalDate` và `ChronoUnit`. **Không cần tạo stream chỉ để đếm độ dài của một khoảng ngày**: `DAYS.between()` đơn giản hơn và thể hiện ý định trực tiếp.

## 5. Chương trình Java 17+ hoàn chỉnh: đếm và sinh ngày

Lưu file **`DateRangeBasicsDemo.java`**:

```java
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.List;

public class DateRangeBasicsDemo {
    public static void main(String[] args) {
        LocalDate start = LocalDate.of(2024, 2, 27);
        LocalDate endExclusive = LocalDate.of(2024, 3, 2);

        long days = ChronoUnit.DAYS.between(start, endExclusive);
        long reverse = ChronoUnit.DAYS.between(endExclusive, start);
        List<LocalDate> dates = start.datesUntil(endExclusive).toList();

        System.out.println("days = " + days);
        System.out.println("reverse = " + reverse);
        System.out.println("dates = " + dates);
        System.out.println("count = " + dates.size());
        System.out.println("start = " + start);
    }
}
```

Chạy:

```bash
javac DateRangeBasicsDemo.java
java DateRangeBasicsDemo
```

Đầu ra xác định:

```text
days = 4
reverse = -4
dates = [2024-02-27, 2024-02-28, 2024-02-29, 2024-03-01]
count = 4
start = 2024-02-27
```

Điểm quan trọng:

1. `ChronoUnit.DAYS.between()` tự biết 2024 là năm nhuận.
2. `datesUntil()` có ngày đầu, loại ngày cuối.
3. `toList()` là terminal operation có trong Java 16+, phù hợp Java 17+. Danh sách trả về là **unmodifiable**, vì vậy không gọi `add()` lên danh sách này.
4. `LocalDate` ban đầu bất biến.

## 6. Bài toán ngày cuối có được tính hay không?

Trong hệ thống thực tế, yêu cầu thường nói “từ ngày 1 đến ngày 3” nhưng không nói ngày 3 có được tính hay không. Hai quy ước dẫn tới đáp án khác nhau:

| Quy ước | Ví dụ 2024-05-01 → 2024-05-03 | Số ngày | Dãy |
| --- | --- | ---: | --- |
| `[start, end)`, không gồm ngày cuối | 1/5 tới trước 3/5 | 2 | 1/5, 2/5 |
| `[start, end]`, gồm cả ngày cuối | 1/5 đến hết 3/5 | 3 | 1/5, 2/5, 3/5 |

Nếu hợp đồng đầu vào là **bao gồm cả hai đầu**, có thể chuyển sang end-exclusive bằng cách thêm một ngày:

```java
LocalDate start = LocalDate.of(2024, 5, 1);
LocalDate endInclusive = LocalDate.of(2024, 5, 3);

List<LocalDate> includingEnd =
        start.datesUntil(endInclusive.plusDays(1)).toList();
// [2024-05-01, 2024-05-02, 2024-05-03]

long inclusiveCount =
        ChronoUnit.DAYS.between(start, endInclusive) + 1;
// 3
```

Đây là đoạn minh họa với import `java.time.LocalDate`, `java.time.temporal.ChronoUnit` và `java.util.List`. Công thức `+1` **chỉ đúng** cho khoảng bao gồm hai đầu với `start <= endInclusive`. Nếu `start > endInclusive`, hãy xác thực và trả lỗi/stream rỗng theo hợp đồng, thay vì cho ra số ngày sai.

**Biên đặc biệt:** `LocalDate.MAX.plusDays(1)` vượt phạm vi của `LocalDate`. Vì vậy không dùng thủ thuật `endInclusive.plusDays(1)` một cách mù quáng khi xử lý giá trị biên tối đa. Nếu ứng dụng hỗ trợ toàn bộ phạm vi và chỉ cần đếm, có thể dựa vào `ChronoUnit.DAYS.between(start, endInclusive) + 1` sau khi kiểm tra `start <= endInclusive`; nếu cần stream đến MAX, có thể dùng `start.datesUntil(endInclusive)` rồi thêm `endInclusive` như một phần tử riêng khi phạm vi hợp lệ.

Nên đặt tên biến thể hiện chính sách, ví dụ `startInclusive`, `endExclusive`, `endInclusive`, `rangeStart` và `rangeEnd`.

## 7. datesUntil(endExclusive, Period step): chọn bước nhảy

Overload thứ hai:

```java
Stream<LocalDate> sequence = start.datesUntil(endExclusive, step);
```

Trong đó `step` là `Period`, ví dụ:

- `Period.ofDays(2)` → cách hai ngày.
- `Period.ofWeeks(1)` → cách một tuần, tức bảy ngày.
- `Period.ofMonths(1)` → các mốc cách một tháng lịch.
- `Period.ofYears(1)` → cách một năm lịch.
- `Period.ofDays(-2)` → đi ngược hai ngày khi end ở trước start.

Overload này cũng **loại ngày kết thúc**. Quy tắc đầu-cuối/bước phải cùng chiều:

- Bước dương sinh dãy ngày **tăng**; end phải cùng hoặc sau start.
- Bước âm sinh dãy ngày **giảm**; end phải cùng hoặc trước start.
- Bước bằng 0 hoặc `Period` trộn thành phần dương và âm không hợp lệ sẽ gây `IllegalArgumentException`.
- Nếu end bằng start, kết quả rỗng.
- Thành phần ngày, tháng và năm của `Period` là thành phần lịch; một tháng không phải một số ngày cố định.

Các tham số `start`, `endExclusive` và `step` cần hợp lệ, không null.

### 7.1. Bước cố định theo ngày

Lưu file **`SteppedDatesDemo.java`**:

```java
import java.time.LocalDate;
import java.time.Period;

public class SteppedDatesDemo {
    public static void main(String[] args) {
        LocalDate monday = LocalDate.of(2024, 4, 1);
        LocalDate end = LocalDate.of(2024, 4, 9);

        System.out.println("every2Days = "
                + monday.datesUntil(end, Period.ofDays(2)).toList());

        LocalDate descendingStart = LocalDate.of(2024, 3, 5);
        LocalDate descendingEnd = LocalDate.of(2024, 2, 28);

        System.out.println("descending = "
                + descendingStart.datesUntil(
                        descendingEnd, Period.ofDays(-2)).toList());
    }
}
```

Chạy:

```bash
javac SteppedDatesDemo.java
java SteppedDatesDemo
```

Kết quả:

```text
every2Days = [2024-04-01, 2024-04-03, 2024-04-05, 2024-04-07]
descending = [2024-03-05, 2024-03-03, 2024-03-01]
```

Hãy để ý: với bước âm, `descendingEnd = 2024-02-28` vẫn **không được đưa vào dãy** vì nó là mốc loại trừ; dãy dừng khi phần tử tiếp theo không còn nằm đúng phía của end.

### 7.2. Bước theo tháng và ngày cuối tháng

Sinh theo `Period.ofMonths(1)` dễ bị hiểu nhầm là “lấy phần tử vừa sinh rồi cộng thêm một tháng”. Thực tế `datesUntil` tính mốc thứ `n` từ **ngày gốc** với bội của step, nhờ vậy tránh tích lũy sai lệch do ngày cuối tháng bị điều chỉnh.

Ví dụ bắt đầu 31/1 năm nhuận:

```java
LocalDate start = LocalDate.of(2024, 1, 31);

List<LocalDate> monthly = start.datesUntil(
        LocalDate.of(2024, 6, 1),
        Period.ofMonths(1)
).toList();
```

Đây là đoạn minh họa với import `java.time.LocalDate`, `java.time.Period` và `java.util.List`. Giá trị `monthly` là:

```text
[2024-01-31, 2024-02-29, 2024-03-31, 2024-04-30, 2024-05-31]
```

So sánh với việc lặp từ **kết quả của lần trước**:

```java
LocalDate cursor = LocalDate.of(2024, 1, 31);
cursor = cursor.plusMonths(1); // 2024-02-29
cursor = cursor.plusMonths(1); // 2024-03-29, không phải 2024-03-31
```

Đây là đoạn minh họa cần `import java.time.LocalDate;`. Các tháng không có ngày 31 sẽ được điều chỉnh theo quy tắc của `LocalDate.plusMonths`. Nếu mục tiêu là ngày cuối mỗi tháng, hãy **quy định rõ** nghiệp vụ; có thể sinh theo mốc ngày đầu tháng rồi áp dụng `TemporalAdjusters.lastDayOfMonth()`. Đừng coi “cộng 30 ngày”, “cộng một tháng” và “ngày cuối tháng kế tiếp” là cùng một thao tác.

### 7.3. Công thức tổng quát của bước Period

Với `step` là một `Period` hợp lệ, ngày thứ `n` được tính theo ý tưởng:

```text
start
  + n * tổng số tháng trong step (years * 12 + months)
  + n * số ngày trong step
```

Phần cộng tháng và ngày tuân theo quy tắc lịch của `LocalDate`. Đây là **ý tưởng tính toán**, không phải yêu cầu tự hiện thực phép nhân có thể tràn. Các phần tử được xét so với end-exclusive để quyết định dừng. Tính từ cùng ngày gốc là khác biệt cốt lõi so với vòng lặp `cursor = cursor.plus(step)` nếu step có phần tháng và thao tác trước đó đã điều chỉnh ngày cuối tháng.

## 8. Kết hợp Stream: lọc cuối tuần, ngày làm việc và lịch

Dãy ngày từ `datesUntil()` là một `Stream<LocalDate>`. Bạn có thể dùng các toán tử stream quen thuộc:

- `filter(...)`: chọn ngày thỏa điều kiện.
- `map(...)`: chuyển đổi ngày thành biểu diễn khác.
- `count()`: đếm phần tử sau lọc.
- `toList()`: thu thành danh sách khi dãy đủ nhỏ.
- `forEach(...)`: thực hiện thao tác quan sát/ghi nhận.

Ví dụ đếm **ngày trong tuần từ thứ Hai đến thứ Sáu**, không xét ngày lễ, trong khoảng `[2024-05-01, 2024-05-08)`:

Lưu file **`WeekdayRangeDemo.java`**:

```java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.util.List;

public class WeekdayRangeDemo {
    public static void main(String[] args) {
        LocalDate start = LocalDate.of(2024, 5, 1);
        LocalDate endExclusive = LocalDate.of(2024, 5, 8);

        List<LocalDate> weekdays = start.datesUntil(endExclusive)
                .filter(day -> {
                    DayOfWeek dow = day.getDayOfWeek();
                    return dow != DayOfWeek.SATURDAY
                            && dow != DayOfWeek.SUNDAY;
                })
                .toList();

        System.out.println("weekdays = " + weekdays);
        System.out.println("weekdayCount = " + weekdays.size());
    }
}
```

Chạy:

```bash
javac WeekdayRangeDemo.java
java WeekdayRangeDemo
```

Kết quả:

```text
weekdays = [2024-05-01, 2024-05-02, 2024-05-03, 2024-05-06, 2024-05-07]
weekdayCount = 5
```

Điều kiện “không phải thứ Bảy/Chủ nhật” chỉ là **ngày trong tuần**, chưa chắc là **ngày làm việc thật**: ngày lễ, lịch nghỉ công ty và lịch làm việc khác vùng địa lý cần được kiểm tra riêng.

Khi cần thống kê số ngày làm việc:

```java
long weekdayCount = start.datesUntil(endExclusive)
        .filter(date -> date.getDayOfWeek() != DayOfWeek.SATURDAY)
        .filter(date -> date.getDayOfWeek() != DayOfWeek.SUNDAY)
        .count();
```

Đây là đoạn minh họa trong một phương thức cần `import java.time.LocalDate;` và `import java.time.DayOfWeek;`. Sử dụng `count()` trực tiếp khi chỉ cần số lượng để tránh thu toàn bộ phần tử thành danh sách.

## 9. Xử lý đầu vào đảo chiều một cách tường minh

`ChronoUnit.DAYS.between(a, b)` **cho phép kết quả âm**. Ngược lại, `a.datesUntil(b)` mặc định tăng từng ngày, nên `b < a` sẽ không tạo dãy như dự tính.

Có ba cách nghiệp vụ khác nhau:

1. **Khoảng phải hợp lệ theo thứ tự tăng:** xác thực `end >= start`, ném lỗi khi nhập sai.
2. **Muốn đếm độ dài không dấu:** dùng `Math.abs(ChronoUnit.DAYS.between(start, end))`. Với `LocalDate` ISO, giá trị chênh lệch vẫn nằm an toàn trong phạm vi `long`.
3. **Muốn giữ chiều giảm:** gọi `datesUntil(endExclusive, Period.ofDays(-1))` với start ở sau end.

Ví dụ đơn giản:

```java
LocalDate later = LocalDate.of(2024, 5, 5);
LocalDate earlier = LocalDate.of(2024, 5, 2);

long signedDays = ChronoUnit.DAYS.between(later, earlier); // -3
long absoluteDays = Math.abs(signedDays);                   // 3
List<LocalDate> backwards =
        later.datesUntil(earlier, Period.ofDays(-1)).toList();
// [2024-05-05, 2024-05-04, 2024-05-03]
```

Đây là đoạn minh họa với các import `LocalDate`, `Period`, `ChronoUnit` và `List`. Đảo đầu-cuối tùy tiện có thể che một lỗi nhập dữ liệu. Hãy thống nhất hợp đồng rõ ràng trước khi quyết định lấy trị tuyệt đối hay sinh ngược.

## 10. Sinh các ngày trong một tháng

Từ `YearMonth`, có thể dùng đầu tháng và đầu tháng tiếp theo làm hai mốc cho `datesUntil()`:

```java
YearMonth month = YearMonth.of(2024, 2);
LocalDate first = month.atDay(1);
LocalDate nextFirst = first.plusMonths(1);

List<LocalDate> daysOfMonth = first.datesUntil(nextFirst).toList();
System.out.println(daysOfMonth.size()); // 29
```

Đây là đoạn minh họa cần `import java.time.YearMonth;`, `import java.time.LocalDate;` và `import java.util.List;`. Với tháng 2/2024, danh sách có 29 phần tử từ 1/2 đến 29/2. Ví dụ này hữu ích để vẽ lưới lịch, tạo ô ngày trên giao diện hoặc phát sinh các ngày cần tính phí.

Nếu chỉ cần **số ngày trong tháng**, sử dụng `month.lengthOfMonth()` thay vì sinh danh sách. Nếu chỉ cần biết **hai LocalDate cách nhau bao nhiêu ngày**, dùng `DAYS.between` thay vì mở Stream. Hãy tạo phần tử chỉ khi thực sự cần xử lý từng ngày.

## 11. Stream lazy, tài nguyên và hiệu năng

`datesUntil()` trả về một stream, vì vậy các thao tác trung gian như `filter()`, `map()` là lazy. Khi có terminal operation, pipeline mới được thực thi. Một stream **không được tái sử dụng** sau terminal operation:

```java
var stream = LocalDate.of(2024, 1, 1)
        .datesUntil(LocalDate.of(2024, 1, 4));
long count = stream.count(); // 3
// stream.toList(); // không hợp lệ: stream đã được tiêu thụ
```

Đây là đoạn minh họa trong một phương thức cần `import java.time.LocalDate;`. Nếu cần chạy hai pipeline độc lập, tạo stream mới bằng cách gọi lại `datesUntil()`.

Các quyết định hiệu năng:

- `DAYS.between(a,b)` tính trực tiếp khoảng cách ngày; không phát sinh từng `LocalDate`.
- `datesUntil(...).filter(...).count()` phù hợp khi phải đánh giá điều kiện trên **từng ngày**.
- `toList()` giữ toàn bộ phần tử trong bộ nhớ; tránh dùng cho khoảng quá rộng hoặc danh sách không thực sự cần thiết.
- `limit(n)` và `takeWhile(...)` có thể hữu ích để kiểm soát số phần tử được xử lý trong pipeline, nhưng không thể sửa đầu vào sai hoặc các giới hạn phạm vi ngày.
- Khi ghi dữ liệu ra ngoài (DB, file, HTTP) theo từng ngày, cân nhắc batching, kiểm soát giao dịch và khả năng chạy lại; `forEach` với side effect nên được dùng có chủ đích.
- Stream không tự làm cho thao tác I/O hiệu quả; `parallel()` không mặc nhiên nhanh hơn và có thể làm thứ tự/side effect khó kiểm soát.

Không được giả định khoảng thời gian vài năm luôn quá lớn. Chọn cách xử lý theo số lượng phần tử thực tế và khối lượng công việc trên mỗi ngày.

## 12. Lỗi thường gặp và ca kiểm thử quan trọng

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Dùng `Period.getDays()` để lấy tổng số ngày giữa hai ngày | Chỉ lấy thành phần ngày, bỏ tháng/năm | `ChronoUnit.DAYS.between(a,b)` |
| Nghĩ `datesUntil(end)` bao gồm end | Thiếu hoặc thừa một ngày | Quy ước `[start,end)` ngay từ tên biến |
| Lấy `between(start,end) + 1` với mọi khoảng | Sai khi start > end hoặc hợp đồng end-exclusive | Chỉ cộng 1 khi đếm khoảng inclusive và đã kiểm tra thứ tự |
| Gọi `datesUntil(end)` khi end trước start | `IllegalArgumentException` | Xác thực đầu-cuối hoặc truyền `Period` âm |
| Truyền `Period.ZERO` làm step | `IllegalArgumentException` | Chọn bước khác 0, đúng hướng và nhất quán dấu |
| Coi `Period.ofMonths(1)` như 30 ngày | Sai ở tháng 28/29/30/31 ngày | Hiểu tháng theo lịch |
| Sinh tháng bằng cách cộng dồn từ ngày 31 | Ngày 31 dễ bị co thành 29/30 và giữ sai lệch | Tính mỗi kỳ từ ngày gốc / dùng `datesUntil(..., Period.ofMonths(1))` |
| Dùng `LocalDate` để suy ra số giờ elapsed qua DST | Có thể sai 1 giờ hoặc hơn | Chọn `ZonedDateTime`/`Instant` theo câu hỏi |
| Thu hàng triệu ngày vào `toList()` chỉ để đếm | Dùng bộ nhớ không cần thiết | Dùng `DAYS.between` hoặc `count()` sau lọc |
| Dùng `endInclusive.plusDays(1)` tại `LocalDate.MAX` | Vượt phạm vi hợp lệ | Xử lý riêng ranh giới giá trị |

Nên có test ít nhất cho các cặp:

- Ngày bằng nhau: khoảng 0, stream rỗng.
- Hai ngày liên tiếp: khoảng 1, stream chứa đúng ngày đầu.
- Trước/sau 29/2 của năm nhuận và 28/2 của năm không nhuận.
- Giao tháng, giao năm và năm âm/dương nếu miền ứng dụng cho phép.
- Khoảng đảo chiều với `between` và với cả hai overload `datesUntil`.
- End-inclusive so với end-exclusive.
- Bước dương, bước âm, bước zero, bước theo tháng từ ngày 29/30/31.
- Biên `LocalDate.MIN`, `LocalDate.MAX` nếu dữ liệu có thể chạm tới.

## 13. Chương trình tích hợp: tổng hợp khoảng ngày và lịch theo bước tháng

Lưu **`DateRangeSummaryDemo.java`**:

```java
import java.time.LocalDate;
import java.time.Period;
import java.time.temporal.ChronoUnit;
import java.util.List;

public class DateRangeSummaryDemo {
    public static void main(String[] args) {
        LocalDate from = LocalDate.of(2024, 1, 31);
        LocalDate until = LocalDate.of(2024, 6, 1);

        long calendarDays = ChronoUnit.DAYS.between(from, until);
        List<LocalDate> monthlyDates = from.datesUntil(
                until, Period.ofMonths(1)).toList();

        System.out.println("calendarDays = " + calendarDays);
        System.out.println("monthlyDates = " + monthlyDates);
        System.out.println("monthlyCount = " + monthlyDates.size());

        LocalDate a = LocalDate.of(2024, 5, 1);
        LocalDate b = LocalDate.of(2024, 5, 4);
        System.out.println("days = " + ChronoUnit.DAYS.between(a, b));
        System.out.println("allDates = " + a.datesUntil(b).toList());
    }
}
```

Biên dịch và chạy:

```bash
javac DateRangeSummaryDemo.java
java DateRangeSummaryDemo
```

Kết quả:

```text
calendarDays = 122
monthlyDates = [2024-01-31, 2024-02-29, 2024-03-31, 2024-04-30, 2024-05-31]
monthlyCount = 5
days = 3
allDates = [2024-05-01, 2024-05-02, 2024-05-03]
```

Ý nghĩa: từ 31/1 tới trước 1/6/2024 có 122 ngày lịch; dãy các mốc hằng tháng gồm 5 phần tử nhưng **5 mốc không đồng nghĩa khoảng cách chỉ có 5 ngày**. Hãy chọn đại lượng cần đo: tổng số ngày giữa hai mốc, hay số phần tử của một dãy có bước nhảy.

## 14. Tự kiểm tra

**Câu 1:** `ChronoUnit.DAYS.between(2024-02-28, 2024-03-01)` là bao nhiêu (giả sử tham số là `LocalDate`)?

**Đáp án:** `2`, vì 2024 có ngày 29/2.

**Câu 2:** `LocalDate.of(2024, 5, 1).datesUntil(LocalDate.of(2024, 5, 4))` sinh những ngày nào?

**Đáp án:** 1/5, 2/5 và 3/5/2024; **không bao gồm ngày 4/5**.

**Câu 3:** Có nên dùng `Period.between(a,b).getDays()` để đếm tổng số ngày không?

**Đáp án:** Không. `getDays()` chỉ là phần ngày của `Period`. Dùng `ChronoUnit.DAYS.between(a,b)`.

**Câu 4:** `datesUntil(end)` có tự sinh dãy lùi nếu end trước start không?

**Đáp án:** Không. Overload mặc định dùng bước một ngày và báo `IllegalArgumentException` khi end trước start. Nếu thật sự cần đi lùi, sử dụng overload với `Period.ofDays(-1)` và mốc end phù hợp.

**Câu 5:** Tại sao bước `Period.ofMonths(1)` khác bước `Period.ofDays(30)`?

**Đáp án:** Tháng lịch dài khác nhau; một tháng tính từ 31/1/2024 tới 29/2/2024, trong khi 30 ngày từ 31/1/2024 tới 1/3/2024.

**Câu 6:** Khi cần đếm số ngày của một khoảng lớn có nên bắt buộc gọi `datesUntil(...).toList().size()` không?

**Đáp án:** Không. Chỉ đếm ngày giữa hai `LocalDate` thì dùng `ChronoUnit.DAYS.between()`. Chỉ sinh Stream khi cần thực sự xử lý từng ngày.

**Ghi nhớ:** `ChronoUnit.DAYS.between(start,end)` đo **số ngày lịch có dấu** giữa hai `LocalDate`. `LocalDate.datesUntil(endExclusive)` tạo **stream ngày tăng từng ngày** trong khoảng `[start,end)`; overload `datesUntil(endExclusive, Period step)` tạo các mốc theo bước lịch, có thể tăng hoặc giảm đúng hướng. Xác định rõ **ngày cuối có được tính không**, chiều của khoảng và ý nghĩa của bước nhảy trước khi viết code.