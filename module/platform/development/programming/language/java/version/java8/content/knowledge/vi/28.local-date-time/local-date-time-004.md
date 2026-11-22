# Year, YearMonth và MonthDay trong Java: biểu diễn đúng ngày giờ cục bộ

## 1. Ba kiểu dữ liệu cho ba nhu cầu khác nhau

Gói `java.time` (có từ Java 8 và được duy trì trong Java hiện đại) không bắt buộc mọi bài toán lịch phải lưu đủ **năm–tháng–ngày**. Khi thông tin thực sự chỉ bao gồm một phần của ngày, hãy dùng kiểu dữ liệu tương ứng:

- **`Year`** biểu diễn **một năm** theo lịch ISO-8601, ví dụ `2024`. Phù hợp năm học, năm báo cáo, năm sản xuất, kiểm tra năm nhuận.
- **`YearMonth`** biểu diễn **một năm và một tháng**, ví dụ `2024-02`. Phù hợp kỳ thanh toán hàng tháng, kỳ lương, kỳ báo cáo, mốc hết hạn theo tháng.
- **`MonthDay`** biểu diễn **một tháng và một ngày, không chứa năm**, ví dụ `--12-03`. Phù hợp sinh nhật lặp hằng năm, ngày kỷ niệm hoặc ngày quy ước theo năm.
- **`LocalDate`** là lựa chọn khi phải biết **ngày cụ thể** đủ cả năm, tháng và ngày, ví dụ `2024-02-29`.

Chọn đúng kiểu giúp model thể hiện **mức độ chính xác của thông tin thực tế**, tránh việc tự gán ngày 01/01 cho “năm”, ngày 01 cho “tháng”, hoặc gắn năm 2000 vào “sinh nhật 29/2” chỉ để nhét vào `LocalDate`.

| Kiểu | Thành phần có thật | Ví dụ `toString()` | Không chứa | Ứng dụng |
| --- | --- | --- | --- | --- |
| `Year` | Năm | `2024` | Tháng, ngày, giờ, múi giờ | Năm tài chính/năm học |
| `YearMonth` | Năm + tháng | `2024-02` | Ngày, giờ, múi giờ | Kỳ lập hóa đơn hàng tháng |
| `MonthDay` | Tháng + ngày | `--02-29` | Năm, giờ, múi giờ | Sinh nhật, ngày kỷ niệm |
| `LocalDate` | Năm + tháng + ngày | `2024-02-29` | Giờ trong ngày, múi giờ | Ngày chốt đơn, ngày hẹn |

**Không kiểu nào trong ba kiểu chính tự lưu giờ, `ZoneId` hoặc một thời điểm tuyệt đối (`Instant`).** Muốn biểu diễn “ngay bây giờ” phải xét nguồn đồng hồ/múi giờ; việc gọi `now()` chỉ tạo ra **giá trị ngày theo thời điểm hiện tại**, không biến đối tượng thành timestamp.

### 1.1. Sơ đồ kết hợp

```text
Year.of(2024)             -> 2024
       |
       +-- atMonth(FEBRUARY)  -> YearMonth: 2024-02
                                     |
                                     +-- atDay(29)         -> LocalDate: 2024-02-29
                                     +-- atEndOfMonth()    -> LocalDate: 2024-02-29

MonthDay.of(2, 29)        -> --02-29
       |
       +-- atYear(2024)       -> LocalDate: 2024-02-29
       +-- atYear(2025)       -> LocalDate: 2025-02-28  (QUY TẮC ĐIỀU CHỈNH)
```

Dòng cuối là chi tiết đặc biệt quan trọng: `MonthDay.atYear` **không ném lỗi** khi ghép 29/2 với năm thường; nó **điều chỉnh thành 28/2**. Trong khi đó, `YearMonth.of(2025,2).atDay(29)` là yêu cầu tạo ngày cụ thể **không hợp lệ**, nên ném `DateTimeException`. Hai API có chủ đích khác nhau.

## 2. `Year`: năm, năm nhuận và chuyển sang ngày cụ thể

### 2.1. Tạo và đọc `Year`

Các factory và phương thức chính:

```java
Year year = Year.of(2024);
int number = year.getValue();          // 2024
boolean leap = year.isLeap();          // true
int totalDays = year.length();         // 366

Year fromText = Year.parse("2024");   // 2024
Year fromDate = Year.from(LocalDate.of(2024, 6, 15)); // 2024
```

Đây là snippet trong một method, cần import `java.time.Year` và `java.time.LocalDate`. `Year.of(int)` kiểm tra năm thuộc phạm vi hỗ trợ; dữ liệu không hợp lệ dẫn đến `DateTimeException`.

`Year.now()` dùng đồng hồ hệ thống và múi giờ mặc định; `Year.now(ZoneId)` hoặc `Year.now(Clock)` phù hợp khi cần điều khiển nguồn thời gian. Đừng ghi cứng năm hiện tại trong test nếu bài kiểm thử cần tái lập.

### 2.2. Năm nhuận của hệ lịch ISO-8601

`Year.isLeap(yearNumber)` (static) và `year.isLeap()` (instance) áp dụng lịch Gregorian mở rộng (*proleptic Gregorian*):

1. Chia hết cho 4 thường là năm nhuận.
2. Nếu chia hết cho 100 thì không nhuận.
3. Nếu đồng thời chia hết cho 400 thì vẫn là năm nhuận.

```java
Year.isLeap(2024); // true
Year.isLeap(1900); // false
Year.isLeap(2000); // true
Year.of(2025).length(); // 365
```

Lưu ý: quy tắc này được áp dụng đồng nhất cho cả quá khứ rất xa theo mô hình ISO, **không** tự động tái hiện lịch sử một quốc gia trước khi họ áp dụng Gregorian. Với dữ liệu lịch sử cần chọn hệ lịch/ngữ cảnh phù hợp.

### 2.3. Year có năm 0 theo lịch ISO proleptic

`Year` không bị giới hạn chỉ nhận năm dương. Phạm vi hỗ trợ thông thường là từ `-999_999_999` đến `999_999_999`. Theo đánh số năm ISO proleptic, trước năm `1` là năm `0` rồi năm `-1`; điều này khác cách diễn đạt BCE/CE phổ thông không có “năm 0”. Tránh viết parser chỉ chấp nhận bốn chữ số hoặc mặc định năm luôn dương nếu bài toán thực sự có năm ngoài dải thông dụng.

### 2.4. Cộng/trừ năm trả về đối tượng mới

`Year` **bất biến**. Các phép biến đổi không sửa instance cũ:

```java
Year start = Year.of(2024);
Year following = start.plusYears(1);  // 2025
Year previous = start.minusYears(1); // 2023
// start vẫn là 2024
```

Với dữ liệu biên gần giới hạn năm tối đa/tối thiểu, phép cộng có thể thất bại do vượt phạm vi; không coi `plusYears` là phép cộng vô hạn.

### 2.5. Kết hợp `Year` với thành phần khác

```java
Year y = Year.of(2024);

YearMonth period = y.atMonth(Month.FEBRUARY); // 2024-02
LocalDate date = y.atMonth(Month.FEBRUARY).atDay(29);
// 2024-02-29

LocalDate day60 = y.atDay(60);
// 2024-02-29 (vì năm 2024 nhuận)
```

`Year.atMonth(int)` và `Year.atMonth(Month)` tạo `YearMonth`. `Year.atDay(int)` tạo `LocalDate` theo **ngày thứ bao nhiêu của năm**, nên `atDay(366)` chỉ hợp lệ với năm nhuận.

`Year.isValidMonthDay(MonthDay)` trả `true` hoặc `false` mà không cần tạo một ngày cụ thể; đây là cách kiểm tra phù hợp khi kết hợp tháng-ngày với năm.

## 3. `YearMonth`: biểu diễn một kỳ tháng

### 3.1. Tạo, lấy năm/tháng và so sánh

```java
YearMonth period = YearMonth.of(2024, 2);
// 2024-02

int year = period.getYear();          // 2024
int monthNumber = period.getMonthValue(); // 2
Month monthEnum = period.getMonth();  // FEBRUARY

YearMonth parsed = YearMonth.parse("2024-02");
boolean same = period.equals(parsed); // true

boolean earlier = period.isBefore(YearMonth.of(2024, 3));
// true
```

`YearMonth` thích hợp khi kỳ dữ liệu có ý nghĩa theo **tháng lịch**, chẳng hạn “báo cáo tháng 02/2024” hoặc “đợt gia hạn tới tháng 09/2027”. Nó không chứa một ngày mặc định để so sánh; hãy chọn ngày bắt đầu/kết thúc một cách có chủ đích khi cần tạo `LocalDate`.

### 3.2. Kiểm tra tháng dài bao nhiêu ngày

```java
YearMonth febLeap = YearMonth.of(2024, 2);
YearMonth febNormal = YearMonth.of(2025, 2);

int days2024 = febLeap.lengthOfMonth();       // 29
int days2025 = febNormal.lengthOfMonth();     // 28
boolean leap2024 = febLeap.isLeapYear();      // true
boolean day29Valid = febNormal.isValidDay(29); // false
```

`lengthOfMonth()` trả 28, 29, 30 hoặc 31 tùy tháng và năm. `lengthOfYear()` trả 365 hoặc 366. Không hard-code rằng tháng 2 luôn 28 ngày hoặc “mọi năm chia hết cho 4 đều nhuận”.

### 3.3. Đầu tháng, cuối tháng và ngày hợp lệ

```java
LocalDate first = febLeap.atDay(1);       // 2024-02-01
LocalDate last = febLeap.atEndOfMonth();  // 2024-02-29
LocalDate aDay = febLeap.atDay(29);       // 2024-02-29
```

Phương thức `atDay(day)` yêu cầu ngày **hợp lệ trong năm-tháng đã biết**. Ví dụ:

```java
YearMonth feb2025 = YearMonth.of(2025, 2);

// DateTimeException: tháng 2 năm 2025 chỉ có 28 ngày.
// LocalDate bad = feb2025.atDay(29);

if (feb2025.isValidDay(29)) {
    LocalDate allowed = feb2025.atDay(29);
}
```

Khi chỉ cần ngày cuối kỳ kế toán, `atEndOfMonth()` rõ ràng và an toàn hơn việc tự chọn ngày `31` rồi hy vọng thư viện điều chỉnh.

### 3.4. Cộng tháng qua ranh giới năm

```java
YearMonth november = YearMonth.of(2024, 11);
YearMonth afterThree = november.plusMonths(3);
// 2025-02

YearMonth earlier = afterThree.minusMonths(12);
// 2024-02
```

`plusMonths`, `minusMonths` và `plusYears` tạo bản sao bất biến; thư viện xử lý đúng việc chuyển từ tháng 12 sang tháng 1 và trường hợp năm âm/năm 0 theo lịch ISO. Tránh tự tăng `monthNumber++` rồi viết logic chuyển năm thủ công khi có sẵn `YearMonth`.

### 3.5. Khoảng cách giữa hai kỳ tháng

`YearMonth` hỗ trợ phép tính số tháng qua `until` với `ChronoUnit.MONTHS`:

```java
YearMonth first = YearMonth.of(2024, 2);
YearMonth later = YearMonth.of(2025, 5);

long months = first.until(later, ChronoUnit.MONTHS);
// 15
```

Đây là số **tháng lịch** giữa hai mốc năm-tháng, không phải số ngày chia cho 30. Với khoảng kỳ bao gồm cả tháng đầu và cuối theo nghiệp vụ, số kỳ có thể là `months + 1` — chỉ khi điều kiện bao gồm cả hai đầu thực sự được quy định như vậy. Nên nói rõ khoảng thời gian nửa mở hay đóng để tránh lỗi lệch một tháng.

### 3.6. Bài toán chọn kỳ báo cáo

```java
YearMonth candidate = YearMonth.of(2025, 2);
YearMonth from = YearMonth.of(2024, 11);
YearMonth to = YearMonth.of(2025, 3);

boolean withinInclusive =
    !candidate.isBefore(from) && !candidate.isAfter(to);
// true
```

Nếu hệ thống biểu diễn các kỳ theo `YearMonth`, code không phải tự ghép chuỗi `"2025-02"` rồi so sánh từ điển. Khi lưu dữ liệu, thống nhất chuẩn năm-tháng ISO (`yyyy-MM` trong cách hiển thị thông dụng, dùng mẫu `uuuu-MM` khi xây formatter) để giảm rủi ro nhập thiếu số 0 phía trước.

## 4. `MonthDay`: ngày lặp lại hằng năm, không có năm

### 4.1. Tạo và đọc tháng-ngày

```java
MonthDay birthday = MonthDay.of(12, 3);
// --12-03

MonthDay leapDay = MonthDay.of(Month.FEBRUARY, 29);
// --02-29

Month month = birthday.getMonth(); // DECEMBER
int monthValue = birthday.getMonthValue(); // 12
int dayValue = birthday.getDayOfMonth(); // 3
```

`MonthDay` sử dụng định dạng ISO mặc định `--MM-dd`, với **hai dấu gạch ngang đầu tiên** vì không có năm. Đây là cách biểu diễn tháng-ngày, không phải lỗi nhập liệu.

Đặc điểm thú vị: `MonthDay.of(2,29)` **hợp lệ** dù không biết năm, vì tồn tại những năm nhuận có ngày đó. Trong khi đó `MonthDay.of(2,30)` hoặc `MonthDay.of(4,31)` **không hợp lệ với bất kỳ năm nào**, nên ném `DateTimeException`.

### 4.2. `MonthDay` không hỗ trợ cộng ngày/tháng như `LocalDate`

`MonthDay` triển khai `TemporalAccessor` và `TemporalAdjuster`, **không** triển khai `Temporal`. Lý do: thiếu năm, nên phép cộng ngày đi qua 29/2 có thể mơ hồ về mặt lịch. Vì vậy không có phương thức `plusDays` hoặc `plusMonths` trực tiếp trên `MonthDay`.

Nếu cần “30 ngày sau ngày kỷ niệm”, phải xác định một năm cụ thể và chính sách ngày nhuận, chuyển thành `LocalDate` rồi dùng `plusDays(30)`. Đó là quyết định nghiệp vụ, không phải việc `MonthDay` tự suy ra.

### 4.3. Kiểm tra 29/2 có xuất hiện trong năm được chọn không

```java
MonthDay leapBirthday = MonthDay.of(2, 29);

boolean valid2024 = leapBirthday.isValidYear(2024); // true
boolean valid2025 = leapBirthday.isValidYear(2025); // false

boolean yearCheck =
    Year.of(2025).isValidMonthDay(leapBirthday); // false
```

`isValidYear(int)` đặc biệt hữu ích cho sinh nhật 29/2: “Ngày kỷ niệm có tồn tại đúng ngày-tháng trong năm cụ thể này không?”.

### 4.4. Bẫy lớn: `MonthDay.atYear(2025)` trả 28/2, không ném lỗi

```java
MonthDay leapBirthday = MonthDay.of(2, 29);

LocalDate onLeapYear = leapBirthday.atYear(2024);
// 2024-02-29

LocalDate onNormalYear = leapBirthday.atYear(2025);
// 2025-02-28 (điều chỉnh có chủ đích)
```

`atYear` có quy tắc **clamp** 29/2 về 28/2 khi năm không nhuận. Tương tự, `Year.of(2025).atMonthDay(leapBirthday)` trả `2025-02-28`.

Điều này **không đồng nghĩa** mọi hệ thống sinh nhật nên dùng 28/2 trong năm thường. Có ít nhất ba chính sách có thể chấp nhận tùy quy định:

1. **28/2**: ngày kỷ niệm được quy về cuối tháng 2 trong năm không nhuận.
2. **01/3**: ngày kỷ niệm được tính vào đầu tháng 3 trong năm không nhuận.
3. **Chỉ ngày 29/2**: sự kiện chỉ xảy ra vào những năm nhuận.

`MonthDay.atYear` mặc định hỗ trợ chính sách **28/2**. Nếu nghiệp vụ cần **01/3** hoặc **chỉ năm nhuận**, phải kiểm tra `isValidYear` và xử lý rõ ràng, không mặc định hóa trong code mà thiếu đặc tả.

### 4.5. So sánh `MonthDay`

`MonthDay` có `compareTo`, `isBefore`, `isAfter`; thứ tự theo **tháng trước, ngày sau**. Ví dụ `--03-01` đứng sau `--02-29`.

Nhưng khi lọc ngày lặp theo năm, phải cẩn thận chuyện **vòng qua năm mới**. Khoảng “20/12 đến 10/01” không thể kiểm tra đơn giản bằng điều kiện `from <= x <= to` theo `MonthDay`, vì đó là một khoảng vòng qua cuối năm. Có thể dùng điều kiện:

```java
MonthDay from = MonthDay.of(12, 20);
MonthDay to = MonthDay.of(1, 10);
MonthDay x = MonthDay.of(1, 5);

boolean wrapsYear = from.isAfter(to);
boolean inside = wrapsYear
    ? !x.isBefore(from) || !x.isAfter(to)
    : !x.isBefore(from) && !x.isAfter(to);
// true
```

Đây là snippet cần `MonthDay` được import. Trong biểu thức trên, `&&` có độ ưu tiên cao hơn `||`; đặt ngoặc rõ hơn nếu quy tắc nghiệp vụ phức tạp. Không dùng so sánh `String` định dạng tùy ý thay cho kiểu lịch.

## 5. Chuyển đổi giữa `Year`, `YearMonth`, `MonthDay` và `LocalDate`

### 5.1. Lấy từng phần từ `LocalDate`

```java
LocalDate fullDate = LocalDate.of(2024, 12, 3);

Year year = Year.from(fullDate);           // 2024
YearMonth period = YearMonth.from(fullDate); // 2024-12
MonthDay anniversary = MonthDay.from(fullDate); // --12-03
```

Đây là thao tác **rút bớt mức độ chính xác**. `Year.from` lấy năm; `YearMonth.from` lấy năm và tháng; `MonthDay.from` lấy tháng và ngày. Không phải mọi `TemporalAccessor` đều chứa các trường cần thiết:

- `YearMonth.from(Year.of(2024))` không thể suy ra tháng.
- `MonthDay.from(YearMonth.of(2024,2))` không thể suy ra ngày.
- `Year.from(MonthDay.of(2,29))` không thể suy ra năm.

Khi thiếu trường bắt buộc, hàm `from` có thể ném `DateTimeException`. Đừng tự gán tháng/ngày mặc định rồi nói rằng giá trị suy ra từ dữ liệu gốc.

### 5.2. Ghép từng phần thành ngày đủ

```java
Year year = Year.of(2024);
YearMonth period = year.atMonth(Month.FEBRUARY);
LocalDate fullDate = period.atDay(29); // 2024-02-29

MonthDay monthDay = MonthDay.of(12, 3);
LocalDate eventDate = monthDay.atYear(2024); // 2024-12-03
```

Chỉ sau khi ghép đủ năm-tháng-ngày và xác định chính sách ngày nhuận mới có một `LocalDate` cụ thể. Với định dạng lưu lâu dài, tránh trộn `YearMonth` vào cột có nghĩa “ngày hết hạn thực tế” nếu hệ thống cần tính chính xác thời điểm kết thúc.

### 5.3. Tháng hết hạn khác ngày hết hạn

Một thẻ chỉ in `09/2027` thường mang ý nghĩa **tháng hết hạn**, không nhất thiết có ngày trên giấy. `YearMonth.of(2027,9)` lưu đúng điều đó. Nếu quy tắc của tổ chức là “hết hạn cuối ngày cuối tháng”, có thể tính:

```java
YearMonth expiryMonth = YearMonth.of(2027, 9);
LocalDate lastValidDate = expiryMonth.atEndOfMonth();
// 2027-09-30
```

Tuy nhiên, **không** tự biến `lastValidDate` thành thời điểm cuối ngày UTC. Muốn so timestamp hoặc tính hết hạn theo múi giờ, phải bổ sung `ZoneId`, ranh giới thời gian và quy định inclusive/exclusive thích hợp.

## 6. Parse, format và kiểm soát dữ liệu đầu vào

### 6.1. Dạng ISO mặc định

Các phép parse thông dụng:

```java
Year y = Year.parse("2024");
YearMonth ym = YearMonth.parse("2024-02");
MonthDay md = MonthDay.parse("--02-29");

System.out.println(y);  // 2024
System.out.println(ym); // 2024-02
System.out.println(md); // --02-29
```

Các snippet này cần import `java.time.Year`, `YearMonth`, `MonthDay`. Dạng mặc định `YearMonth.parse` thường mong đợi tháng hai chữ số như `02`; `MonthDay.parse` mong đợi hai dấu `--` đầu. Không coi `"2024/2"` hoặc `"02-29"` là định dạng ISO mặc định.

### 6.2. Custom `DateTimeFormatter`

```java
DateTimeFormatter yearMonthPattern =
    DateTimeFormatter.ofPattern("uuuu/MM");

YearMonth period =
    YearMonth.parse("2024/02", yearMonthPattern);

String formattedPeriod = period.format(yearMonthPattern);
// 2024/02

DateTimeFormatter monthDayPattern =
    DateTimeFormatter.ofPattern("MM/dd");

String formattedBirthday =
    MonthDay.of(2, 29).format(monthDayPattern);
// 02/29
```

Chú ý `u` và `y` trong pattern có ý nghĩa khác nhau: `u` là **proleptic year**, còn `y` là **year-of-era**. Với quy tắc ISO và mã cần hỗ trợ cả năm 0/âm, `uuuu` thường biểu diễn đúng mục tiêu hơn. Đừng dùng ký tự `mm` để biểu diễn **tháng**: trong `DateTimeFormatter`, `M` đại diện tháng, còn `m` đại diện **phút**.

Đối với ứng dụng nhiều vùng/ngôn ngữ, có thể chọn `Locale` và formatter tương ứng, nhưng việc nhập liệu cho hệ thống thường nên quy định một chuẩn máy đọc rõ ràng thay vì phụ thuộc locale mặc định.

### 6.3. Đừng tách chuỗi thủ công để kiểm tra lịch

Lỗi dễ gặp là nhận `"2025-02"` rồi tự quy định “tháng 2 luôn 28 ngày” hoặc so ký tự `'2'` theo cách không có padding. `YearMonth.parse` + `isValidDay` đã cung cấp hợp đồng lịch đáng tin cậy.

Khi parse lỗi, `DateTimeParseException` (một dạng `DateTimeException`) cung cấp thông tin để tầng giao diện báo nhập liệu không hợp lệ. Đừng silently đổi dữ liệu lỗi thành tháng hiện tại nếu nghiệp vụ không cho phép.

## 7. Bất biến, value-based và tính an toàn luồng

`Year`, `YearMonth` và `MonthDay` đều **immutable**, **thread-safe** và thuộc nhóm **value-based classes**:

- Mọi thao tác `plus...`, `minus...`, `with...` phù hợp trả về một **đối tượng có giá trị mới**, không sửa giá trị gốc.
- Hai giá trị bằng nhau nên so sánh bằng `equals()`, không dùng toán tử tham chiếu `==` làm tiêu chí nghiệp vụ.
- Không dùng chúng làm **monitor** cho `synchronized(...)`, không dựa vào `System.identityHashCode` hoặc việc một JDK có tái sử dụng instance.
- Có thể sử dụng chúng làm thành phần của object bất biến, key cho `Map`/`Set` theo hợp đồng `equals` và `hashCode`.

```java
YearMonth a = YearMonth.of(2024, 2);
YearMonth b = YearMonth.parse("2024-02");

boolean sameValue = a.equals(b); // true
// Không dùng a == b để kết luận giá trị bằng nhau.
```

Nếu cần so thứ tự, `Year`/`YearMonth`/`MonthDay` triển khai `Comparable` hoặc có các helper như `isBefore`/`isAfter` khi được hỗ trợ. Không áp dụng `YearMonth.isBefore` cho việc so ngày cụ thể trong tháng, vì chính đối tượng đó **không có ngày**.

## 8. So sánh và sắp xếp các mốc thời gian

### 8.1. `Year` và `YearMonth` so thứ tự tự nhiên

`Year.compareTo` so năm số; `YearMonth.compareTo` so **năm trước rồi đến tháng**. Vì vậy:

```java
boolean ordered =
    YearMonth.of(2024, 12).isBefore(YearMonth.of(2025, 1));
// true
```

Với `List<YearMonth>`, có thể gọi `Collections.sort(list)` hoặc `list.sort(Comparator.naturalOrder())`, vì `YearMonth` implements `Comparable<YearMonth>`. Nếu muốn giảm dần, dùng `Comparator.reverseOrder()`. Đó là thứ tự theo kỳ tháng, không phải theo một ngày bên trong kỳ.

### 8.2. `MonthDay` không thể xác định năm sự kiện

`MonthDay.of(12,31)` đứng sau `MonthDay.of(1,1)` theo thứ tự năm lịch. Nhưng nếu “sự kiện tiếp theo kể từ ngày hôm nay” ở tháng 12, `01/01` có thể gần hơn `31/12` của năm tiếp theo hoặc ngược lại. Muốn tính ngày gần nhất, phải kết hợp với **một năm cụ thể**, xét ranh giới năm và chính sách ngày 29/2.

Đừng dùng `monthDayA.compareTo(monthDayB)` để suy ra **số ngày** giữa hai sự kiện, vì nó chỉ trả một số so sánh thứ tự, không phải khoảng cách ngày.

## 9. Sinh nhật 29/2: thiết kế chính sách thay vì dựa vào mặc định

### 9.1. Chính sách 28/2

Nếu ứng dụng quyết định lấy **28/2 trong năm không nhuận**, có thể dùng:

```java
MonthDay birthday = MonthDay.of(2, 29);
LocalDate event2025 = birthday.atYear(2025);
// 2025-02-28
```

Hành vi này có sẵn trong `MonthDay.atYear`. Chỉ dùng khi quy định nghiệp vụ đúng là **28/2**, không coi đó là chân lý pháp lý của mọi địa phương.

### 9.2. Chính sách 01/3

Nếu chọn **01/3 trong năm thường**, kiểm tra:

```java
MonthDay birthday = MonthDay.of(2, 29);
int targetYear = 2025;

LocalDate event = birthday.isValidYear(targetYear)
    ? birthday.atYear(targetYear)
    : LocalDate.of(targetYear, 3, 1);
// 2025-03-01
```

Với birthday khác 29/2, `isValidYear` thông thường là `true` vì `MonthDay.of` đã bảo đảm ngày tháng hợp lệ ở ít nhất một năm.

### 9.3. Chính sách chỉ tổ chức vào năm nhuận

Nếu chỉ tổ chức vào ngày **29/2 thực sự tồn tại**, bỏ qua những năm thường:

```java
MonthDay leapBirthday = MonthDay.of(2, 29);
LocalDate reference = LocalDate.of(2025, 3, 1);
int y = reference.getYear();

while (!leapBirthday.isValidYear(y)
       || leapBirthday.atYear(y).isBefore(reference)) {
    y++;
}
LocalDate nextRealLeapDay = leapBirthday.atYear(y);
// 2028-02-29
```

Đây là snippet trong method (import `MonthDay`, `LocalDate`). Trong hệ thống dài hạn cần xử lý giới hạn năm tối đa và quy định khi không tìm được sự kiện trong miền cho phép, không để vòng lặp tràn qua `Year.MAX_VALUE`. Ví dụ chạy đầy đủ ở mục 11 có helper cho chính sách này.

### 9.4. Bản thân ngày sinh có thể cần lưu **cả năm**

`MonthDay` phù hợp khi chỉ cần **ngày kỷ niệm lặp lại**. Hồ sơ cá nhân, điều kiện tuổi hợp pháp, thời điểm sinh thực tế hoặc báo cáo chính xác thường cần **`LocalDate` đầy đủ**, không thể thay bằng `MonthDay` nếu làm mất năm sinh. Có thể lấy `MonthDay.from(dateOfBirth)` khi chỉ cần hiển thị sinh nhật hằng năm, còn nguồn dữ liệu chính vẫn là `LocalDate`.

## 10. `now()`, `ZoneId` và `Clock`: local không có nghĩa bỏ qua múi giờ khi lấy thời điểm hiện tại

Các giá trị `Year`, `YearMonth` và `MonthDay` không lưu `ZoneId`, nhưng lời gọi `now()` phải xác định **ngày hiện tại theo vùng nào**. Một `Instant` có thể là ngày 28/2 ở UTC nhưng đã sang 29/2 ở châu Á.

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Year currentYear = Year.now(zone);
YearMonth currentPeriod = YearMonth.now(zone);
MonthDay todayMonthDay = MonthDay.now(zone);
```

Đây là code hợp lệ trong method với import các lớp `java.time`. Giá trị phụ thuộc giờ thực tế khi chạy, nên **không có stdout cố định**.

### 10.1. Đặt Clock cố định cho unit test

```java
Clock fixed = Clock.fixed(
    Instant.parse("2024-02-28T18:00:00Z"),
    ZoneId.of("Asia/Ho_Chi_Minh")
);

LocalDate today = LocalDate.now(fixed); // 2024-02-29
Year year = Year.now(fixed);           // 2024
YearMonth ym = YearMonth.now(fixed);    // 2024-02
MonthDay md = MonthDay.now(fixed);      // --02-29
```

`18:00 UTC` cộng `07:00` tại `Asia/Ho_Chi_Minh` là `01:00` ngày `29/2/2024`. Đây là lý do không nên viết unit test kiểu `assertEquals(Year.of(2024), Year.now())`: nó chỉ đúng khi thực sự chạy trong năm 2024. Truyền `Clock` vào code có phụ thuộc “hiện tại” giúp test tái lập chính xác.

### 10.2. Chuyển sang thời điểm thực sự chỉ khi có đủ thông tin

Ví dụ `YearMonth.of(2027,9)` không xác định ngày, giờ và múi giờ để trở thành `Instant`. Nếu nghiệp vụ nói “hết hạn khi bắt đầu tháng sau ở múi giờ cụ thể”, mới có thể diễn đạt bằng một ranh giới nửa mở:

```java
YearMonth expiry = YearMonth.of(2027, 9);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant expiresAtExclusive = expiry.plusMonths(1)
    .atDay(1)
    .atStartOfDay(zone)
    .toInstant();
```

Ở đây `expiresAtExclusive` là **thời điểm bắt đầu tháng 10/2027** theo vùng đã chọn; sự kiện được coi là hết hạn khi `nowInstant >= expiresAtExclusive`. Không dùng `atTime(23,59,59,999...)` để giả định “cuối ngày” nếu quy định khoảng nửa mở diễn đạt rõ và an toàn hơn, đặc biệt trong môi trường có quy tắc đổi giờ ở các múi giờ khác.

## 11. Chương trình Java hoàn chỉnh (Java 8-compatible)

Ví dụ dưới đây minh họa **cả ba kiểu**, tính năm nhuận, kiểm tra ngày hợp lệ, sự khác nhau giữa `atDay` và `atYear`, parse/format, khoảng cách tháng, chính sách sinh nhật và `Clock` cố định. Mã không phụ thuộc vào ngày chạy thực tế.

Lưu vào file **YearYearMonthMonthDayDemo.java**:

```java
import java.time.Clock;
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.Month;
import java.time.MonthDay;
import java.time.Year;
import java.time.YearMonth;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;

public class YearYearMonthMonthDayDemo {
    static LocalDate nextExistingAnniversary(
            MonthDay recurring, LocalDate reference) {
        int year = reference.getYear();
        while (year <= Year.MAX_VALUE) {
            if (recurring.isValidYear(year)) {
                LocalDate candidate = recurring.atYear(year);
                if (!candidate.isBefore(reference)) {
                    return candidate;
                }
            }
            if (year == Year.MAX_VALUE) {
                break;
            }
            year++;
        }
        throw new DateTimeException("No anniversary in supported years");
    }

    public static void main(String[] args) {
        Year year = Year.of(2024);
        System.out.println("Year: " + year
            + ", leap=" + year.isLeap()
            + ", days=" + year.length());
        System.out.println("1900 leap=" + Year.isLeap(1900)
            + ", 2000 leap=" + Year.isLeap(2000));
        System.out.println("Year.atDay(60): " + year.atDay(60));
        System.out.println("Year.atMonth(DECEMBER): "
            + year.atMonth(Month.DECEMBER));

        YearMonth feb = YearMonth.of(2024, Month.FEBRUARY);
        YearMonth nonLeapFeb = feb.plusYears(1);
        System.out.println("YearMonth: " + feb
            + ", length=" + feb.lengthOfMonth());
        System.out.println("2025-02 length: "
            + nonLeapFeb.lengthOfMonth());
        System.out.println("Feb end: " + feb.atEndOfMonth());
        System.out.println("Plus 13 months: " + feb.plusMonths(13));
        System.out.println("Months until 2025-05: "
            + feb.until(YearMonth.of(2025, 5), ChronoUnit.MONTHS));
        System.out.println("2024-02 day29 valid: "
            + feb.isValidDay(29));
        System.out.println("2025-02 day29 valid: "
            + nonLeapFeb.isValidDay(29));

        MonthDay leapDay = MonthDay.of(2, 29);
        System.out.println("MonthDay: " + leapDay);
        System.out.println("MonthDay valid2024="
            + leapDay.isValidYear(2024) + ", valid2025="
            + leapDay.isValidYear(2025));
        System.out.println("MonthDay.atYear(2025): "
            + leapDay.atYear(2025));
        System.out.println("Year(2025) valid MonthDay: "
            + Year.of(2025).isValidMonthDay(leapDay));

        boolean invalidAtDayThrows = false;
        try {
            nonLeapFeb.atDay(29);
        } catch (DateTimeException exception) {
            invalidAtDayThrows = true;
        }
        System.out.println("YearMonth.atDay invalid throws: "
            + invalidAtDayThrows);

        System.out.println("Year.parse: " + Year.parse("2030"));
        System.out.println("YearMonth.parse: "
            + YearMonth.parse("2030-07"));
        System.out.println("MonthDay.parse: "
            + MonthDay.parse("--12-03"));

        DateTimeFormatter periodFormat =
            DateTimeFormatter.ofPattern("uuuu/MM");
        DateTimeFormatter anniversaryFormat =
            DateTimeFormatter.ofPattern("MM/dd");
        System.out.println("Custom format: "
            + feb.format(periodFormat) + " | "
            + leapDay.format(anniversaryFormat));
        System.out.println("MonthDay.from: "
            + MonthDay.from(LocalDate.of(2026, 12, 3)));

        LocalDate reference = LocalDate.of(2025, 3, 1);
        System.out.println("Next real leap anniversary: "
            + nextExistingAnniversary(leapDay, reference));
        System.out.println("Feb 28 fallback: "
            + leapDay.atYear(2025));

        Clock clock = Clock.fixed(
            Instant.parse("2024-02-28T18:00:00Z"),
            ZoneId.of("Asia/Ho_Chi_Minh")
        );
        System.out.println("Fixed local date: "
            + LocalDate.now(clock));
        System.out.println("Fixed Year/YearMonth/MonthDay: "
            + Year.now(clock) + " / " + YearMonth.now(clock)
            + " / " + MonthDay.now(clock));

        System.out.println("YearMonth value equality: "
            + feb.equals(YearMonth.parse("2024-02")));
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac -encoding UTF-8 YearYearMonthMonthDayDemo.java
java YearYearMonthMonthDayDemo
```

**Stdout chính xác:**

```text
Year: 2024, leap=true, days=366
1900 leap=false, 2000 leap=true
Year.atDay(60): 2024-02-29
Year.atMonth(DECEMBER): 2024-12
YearMonth: 2024-02, length=29
2025-02 length: 28
Feb end: 2024-02-29
Plus 13 months: 2025-03
Months until 2025-05: 15
2024-02 day29 valid: true
2025-02 day29 valid: false
MonthDay: --02-29
MonthDay valid2024=true, valid2025=false
MonthDay.atYear(2025): 2025-02-28
Year(2025) valid MonthDay: false
YearMonth.atDay invalid throws: true
Year.parse: 2030
YearMonth.parse: 2030-07
MonthDay.parse: --12-03
Custom format: 2024/02 | 02/29
MonthDay.from: --12-03
Next real leap anniversary: 2028-02-29
Feb 28 fallback: 2025-02-28
Fixed local date: 2024-02-29
Fixed Year/YearMonth/MonthDay: 2024 / 2024-02 / --02-29
YearMonth value equality: true
```

### 11.1. Vì sao những kết quả này đáng tin?

1. `2024` chia hết cho 4 nhưng không chia hết cho 100 nên nhuận; `1900` chia hết cho 100 mà không cho 400 nên không nhuận; `2000` chia hết cho 400 nên nhuận.
2. Năm nhuận có ngày thứ `60` là `29/2`; tháng 2/2024 có 29 ngày trong khi tháng 2/2025 chỉ có 28.
3. `2024-02` cộng 13 tháng thành `2025-03`; tính tới `2025-05` là 15 tháng lịch.
4. `MonthDay.of(2,29)` tồn tại hợp lệ **không cần năm**; `isValidYear(2025)` trả `false`.
5. `MonthDay.atYear(2025)` **điều chỉnh** thành `2025-02-28`, còn `YearMonth.of(2025,2).atDay(29)` ném `DateTimeException`. Chương trình chỉ in một `boolean` cho kiểm tra exception, không phụ thuộc nội dung thông báo của JDK.
6. Parser ISO sử dụng chuỗi có độ dài và dấu phân cách đúng chuẩn; formatter tùy biến xử lý rõ tháng và proleptic year.
7. Hàm `nextExistingAnniversary` chỉ xét năm mà `MonthDay` hợp lệ; với ngày 29/2 kể từ `2025-03-01`, mốc thực tiếp theo là `2028-02-29`. Code minh họa xử lý giới hạn tối đa của `Year` trước khi tăng năm.
8. `Clock.fixed` tạo thời điểm tái lập: UTC `2024-02-28T18:00:00Z` tương ứng `2024-02-29` tại vùng `Asia/Ho_Chi_Minh`; giá trị `Year`, `YearMonth`, `MonthDay` đồng bộ theo cùng Clock.
9. Hai đối tượng `YearMonth` biểu diễn cùng năm-tháng bằng nhau theo `equals`, không cần `==`.

## 12. Các lỗi dễ gặp và cách phòng tránh

### 12.1. Dùng `LocalDate` khi dữ liệu không có ngày

`LocalDate.of(2024,2,1)` lưu **ngày 01/02**, không phải khái niệm “toàn bộ tháng 2/2024”. Nếu API lưu “kỳ tháng”, dùng `YearMonth` để tránh khiến người khác tưởng ngày `1` là dữ liệu có thật.

### 12.2. Không xử lý ngày 29/2 trong năm thường

`MonthDay.atYear` âm thầm điều chỉnh sang 28/2 **theo hợp đồng API**, nên kết quả có thể không đúng chính sách sinh nhật/kỷ niệm của ứng dụng. Phải dùng `isValidYear` để phân biệt chính sách 28/2, 01/3 và “chỉ năm nhuận”.

### 12.3. Đánh đồng `atYear` với `atDay`

`YearMonth.of(2025,2).atDay(29)` ném exception vì yêu cầu ngày không hợp lệ; `MonthDay.of(2,29).atYear(2025)` trả 28/2. Hai API có quy tắc khác nhau, không thể thay thế máy móc.

### 12.4. Trộn năm lịch và thời điểm tuyệt đối

`YearMonth` là “tháng năm” ở hệ lịch ISO, không phải timestamp. Không so `YearMonth.now()` với `Instant` mà không định nghĩa múi giờ, ngày và điểm cắt kỳ cụ thể.

### 12.5. Dùng thời gian thực để kiểm thử phép tính ngày

`Year.now()` phụ thuộc môi trường. Nếu test muốn kết quả xác định, truyền `Clock.fixed`, tránh phụ thuộc ngày chạy hoặc múi giờ mặc định.

### 12.6. Định dạng bằng pattern sai chữ hoa/thường

`MM` là tháng; `mm` là phút. `uuuu` là proleptic year, `yyyy` là year-of-era; những mẫu này không hoàn toàn tương đương với năm 0 hoặc năm âm. Phải kiểm tra đầu vào/đầu ra rõ ràng.

### 12.7. Xử lý khoảng tháng bằng số ngày cố định

Không lấy số ngày chia cho 30 để suy ra tháng tài chính. `YearMonth.plusMonths` và `YearMonth.until(..., MONTHS)` thể hiện đúng số tháng lịch và xử lý qua ranh giới năm.

### 12.8. So sánh value-based bằng `==` hoặc dùng làm lock

`Year`, `YearMonth`, `MonthDay` là value-based. Dùng `equals` cho tính bằng nhau, tránh `synchronized(yearMonth)` và các quyết định dựa vào identity.

### 12.9. Tưởng `MonthDay` có thể cộng ngày độc lập

`MonthDay` không biết năm; muốn tính cộng ngày, phải tạo `LocalDate` bằng cách chọn năm phù hợp với quy tắc. Không tạo tiện ích giả định rằng `MonthDay.plusDays` tồn tại.

### 12.10. Dùng `YearMonth` để biểu diễn ngày sinh thật

`YearMonth` bỏ ngày; `MonthDay` bỏ năm. Nếu cần biết tuổi hoặc ngày sinh đầy đủ, phải lưu `LocalDate` và chỉ rút các phần khi phục vụ báo cáo/hiển thị.

## 13. Chọn kiểu nào theo bài toán?

| Yêu cầu | Kiểu nên dùng | Lưu ý |
| --- | --- | --- |
| Năm sản xuất, năm tuyển sinh | `Year` | Không thêm tháng/ngày giả. |
| Tháng quyết toán, tháng lương | `YearMonth` | Dùng `plusMonths` khi chuyển kỳ. |
| Sinh nhật lặp mỗi năm | `MonthDay` | Định nghĩa chính sách ngày 29/2. |
| Ngày sinh đầy đủ để xác minh tuổi | `LocalDate` | Không làm mất năm/ngày. |
| Kỳ báo cáo bắt đầu/kết thúc tháng | `YearMonth` cho kỳ, `LocalDate` khi cần ranh giới | `atDay(1)` và `atEndOfMonth()`. |
| Hết hạn cuối tháng theo vùng thời gian | `YearMonth` + `ZoneId` để tạo ranh giới | Chọn khoảng nửa mở rõ ràng. |
| Kiểm tra năm nhuận | `Year.isLeap()` / `Year.isLeap(int)` | Không tự viết lại quy tắc nếu không cần. |
| Lấy ngày thứ N trong năm | `Year.atDay(N)` | `366` chỉ hợp lệ với năm nhuận. |
| Xem 29/2 có tồn tại năm X không | `MonthDay.isValidYear(X)` | Khác với `atYear` có thể clamp. |
| So tháng A trước tháng B? | `YearMonth.isBefore/isAfter` | Không có thông tin ngày. |
| Kiểm tra ngày cụ thể hợp lệ trong tháng | `YearMonth.isValidDay(day)` | `atDay` ném exception khi invalid. |
| Test có “ngày hôm nay” | `Clock.fixed` với `now(clock)` | Kết quả không phụ thuộc runtime. |

## 14. Câu hỏi tự luyện có đáp án

1. **`Year.of(1900).isLeap()` trả gì?** `false`, vì năm 1900 chia hết cho 100 nhưng không chia hết cho 400.
2. **`Year.of(2000).isLeap()` trả gì?** `true`, vì 2000 chia hết cho 400.
3. **`YearMonth.of(2024,2).atEndOfMonth()` cho ngày nào?** `2024-02-29`.
4. **`YearMonth.of(2025,2).isValidDay(29)` trả gì?** `false`.
5. **`MonthDay.of(2,29).isValidYear(2025)` trả gì?** `false`.
6. **`MonthDay.of(2,29).atYear(2025)` trả gì?** `2025-02-28` theo quy tắc điều chỉnh của API.
7. **`YearMonth.of(2025,2).atDay(29)` trả gì?** Không trả giá trị: ném `DateTimeException`.
8. **`YearMonth.of(2024,12).plusMonths(2)` trả gì?** `2025-02`.
9. **`MonthDay.parse("02-29")` có đúng định dạng mặc định không?** Không; dùng `MonthDay.parse("--02-29")`.
10. **Để lưu một kỳ lương “tháng 06/2026”, nên lưu `LocalDate.of(2026,6,1)` hay `YearMonth.of(2026,6)`?** `YearMonth` nếu dữ liệu không thực sự có ngày 01.
11. **Sự kiện từ 20/12 đến 10/01 có thể kiểm tra bằng `from <= day <= to` không?** Không, vì khoảng vượt ranh giới năm; cần logic vòng qua năm.
12. **Vì sao `Clock.fixed` hữu ích?** Nó định nghĩa thời điểm và múi giờ cố định, làm kết quả `now(clock)` có thể kiểm thử tái lập.
13. **Có thể cộng 30 ngày trực tiếp trên `MonthDay` không?** Không; hãy chọn năm, chính sách ngày nhuận và dùng `LocalDate.plusDays`.
14. **Năm ISO `0` có hợp lệ với `Year` không?** Có; đây là hệ đánh số proleptic, cần phân biệt với cách biểu diễn năm lịch sử thông dụng.

## 15. Tài liệu API chính thức (còn áp dụng)

Các class trong bài xuất hiện từ Java 8, bất biến, thread-safe và vẫn được duy trì; tham khảo hợp đồng trên JDK hiện đại:

- [`Year` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Year.html): `isLeap`, `length`, `atDay`, `atMonth`, `isValidMonthDay`, `atMonthDay`.
- [`YearMonth` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/YearMonth.html): `lengthOfMonth`, `isValidDay`, `atDay`, `atEndOfMonth`, `plusMonths` và `until`.
- [`MonthDay` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/MonthDay.html): `isValidYear`, `atYear`, `compareTo` và điều chỉnh 29/2 về 28/2.
- [`LocalDate` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDate.html): ngày đủ năm-tháng-ngày.
- [`Clock` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html): nguồn giờ có thể điều khiển trong unit test.
- [`DateTimeFormatter` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html): mẫu `uuuu`, `yyyy`, `MM` và parse/format.
- [`ChronoUnit` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/ChronoUnit.html): `MONTHS` và các đơn vị thời gian.
