# Cộng, trừ, nhân, chia khoảng thời gian theo hợp đồng trong Java 8+

Khi xử lý thời hạn, timeout, lịch gia hạn hoặc thời lượng một cuộc họp, các phép cộng/trừ/nhân/chia tưởng chừng đơn giản nhưng **chỉ đúng khi xác định được "khoảng thời gian" mang ý nghĩa gì**. "Cộng một ngày" có thể là **cộng 24 giờ thực** hoặc **sang cùng giờ đồng hồ của ngày lịch hôm sau**. "Nhân đôi một tháng" có thể là hai tháng lịch chứ không phải 60 ngày; "chia một tháng cho hai" lại không có một đáp án số ngày cố định nếu chưa biết ngày bắt đầu và quy tắc làm tròn.

Java hiện đại phân biệt hai lớp bất biến, vẫn được hỗ trợ từ Java 8:

- **`Duration`**: khoảng theo **thời lượng thực** tính bằng giây và nano giây; phù hợp cho timeout, SLA, thời gian chạy, khoảng cách giữa hai `Instant`.
- **`Period`**: khoảng theo **lịch ISO** gồm năm, tháng, ngày; phù hợp cho gia hạn theo tháng/năm, ngày theo lịch, quy tắc lịch địa phương.

Bài học tập trung vào **`plus`, `minus`, `multipliedBy`, `dividedBy`**, phép toán khi áp dụng vào một mốc ngày giờ, ràng buộc về kiểu/đơn vị, độ chính xác, tràn số, số âm, DST và những quy tắc nghiệp vụ cần viết thành hợp đồng rõ ràng. `Duration.dividedBy(Duration)` ra đời từ **Java 9** và đang được hỗ trợ trên Java 17+, còn các API cơ bản có từ Java 8. Chương trình hoàn chỉnh của bài biên dịch bằng `--release 17`.

## 1. "Theo hợp đồng" nghĩa là gì?

Một phép toán thời gian cần trả lời trước ít nhất sáu câu hỏi:

1. **Đơn vị là thời lượng thực hay đơn vị lịch?** 24 giờ và "một ngày địa phương" không luôn giống nhau.
2. **Mốc bắt đầu là gì?** "Một tháng sau" từ 31/01 sẽ chịu quy tắc cuối tháng; bản thân `Period.ofMonths(1)` chưa phải một số ngày cố định.
3. **Có múi giờ vùng nào tham gia không?** `America/New_York` có đổi giờ DST; `ZoneOffset.of("+07:00")` không phải một múi giờ vùng có quy tắc chuyển đổi.
4. **Đầu vào là âm, bằng 0 hay cực lớn?** Phải biết chia cho 0, tràn số và khoảng âm được xử lý thế nào.
5. **Kết quả phải chính xác tới mức nào?** Nanosecond, microsecond hay millisecond? Phần lẻ sau chia làm tròn ra sao?
6. **Ứng dụng dùng kết quả thế nào?** Timeout cần một độ dài thực, lịch học cần giữ giờ địa phương, báo cáo tài chính theo tháng cần quy tắc lịch và ngày chốt.

Không được âm thầm thay `Period.ofMonths(1)` bằng `Duration.ofDays(30)` hay coi mọi kết quả chia đều bảo toàn chính xác hoàn toàn.

## 2. Chọn đúng kiểu trước khi tính toán

| Ý định | Kiểu phù hợp | Ví dụ |
| --- | --- | --- |
| Thêm 90 phút vào một thời điểm đã xảy ra | `Duration` + `Instant` | `instant.plus(Duration.ofMinutes(90))` |
| Trừ 15 giây khỏi timeout | `Duration` | `timeout.minusSeconds(15)` |
| Chia một thời lượng thành bốn phần bằng nhau | `Duration.dividedBy(4)` | Một giờ chia 4 thành 15 phút |
| Đếm số khoảng 30 phút trọn vẹn trong 95 phút | `Duration.dividedBy(Duration)` (Java 9+) | 3 lượt, dư 5 phút |
| Gia hạn 2 tháng theo lịch | `Period.ofMonths(2)` + `LocalDate` | Ngày 31/01/2024 → 31/03/2024 |
| Cộng 1 ngày địa phương qua DST | `Period.ofDays(1)` + `ZonedDateTime` | Giữ giờ đồng hồ nếu hợp lệ |
| Cộng đúng 24 giờ qua DST | `Duration.ofDays(1)` + `ZonedDateTime` | Thời điểm thực tăng đúng 86.400 giây |
| Sinh nhật hoặc ngày thanh toán hằng năm | `Period.ofYears(1)` và chính sách cuối tháng/ngày nhuận | Không thay bằng 365 ngày |
| Chia một tháng thành hai chu kỳ | **Cần quy tắc lịch bổ sung** | Không có `Period.dividedBy(...)` |

`Duration` và `Period` đều triển khai giao diện `TemporalAmount`, nhưng **không có nghĩa chúng hoán đổi cho nhau trong mọi phép toán**. `TemporalAmount` chỉ mô tả một lượng có thể cộng vào hoặc trừ khỏi một `Temporal` phù hợp. Tập đơn vị được hỗ trợ và kết quả phụ thuộc vào loại lượng, loại mốc và API được gọi.

## 3. `Duration`: cơ chế lưu trữ và tính chất

`Duration` là kiểu bất biến và thread-safe, lưu độ dài theo **`long seconds` + `int nanos`**. Phần nano của giây được chuẩn hóa trong miền `0..999_999_999`, kể cả khi toàn bộ Duration là âm.

```java
Duration base = Duration.ofMinutes(90);
Duration extra = Duration.ofSeconds(45);

Duration result = base.plus(extra);
// result = PT1H30M45S.
// base vẫn là PT1H30M.
```

`Duration` có thể âm, bằng 0 hoặc dương:

```java
Duration.ZERO;
Duration.ofSeconds(-3);
Duration.ofMillis(250);
Duration.ofSeconds(2, 500_000_000);
```

Ví dụ gây nhầm:

```java
Duration negativeOneMillis = Duration.ofMillis(-1);

System.out.println(negativeOneMillis.getSeconds()); // -1
System.out.println(negativeOneMillis.getNano());    // 999000000
```

Giải thích: `-0,001` giây được lưu thành `-1 giây + 0,999 giây`. **`getSeconds()` không phải phép làm tròn tổng giây về 0**; nó là phần giây đã chuẩn hóa. Không được tự suy từ `getNano() > 0` rằng Duration dương.

Nếu chỉ muốn số mili giây cho một khoảng nhỏ hơn khả năng của `long`, dùng `toMillis()`. Phép chuyển đổi này có thể bỏ phần nhỏ hơn millisecond và có thể ném `ArithmeticException` khi vượt miền `long`. Nếu cần kiểm soát precision, chuẩn hóa và test theo hợp đồng thay vì ghép thủ công `seconds * 1000 + nano/1_000_000` mà không xử lý tràn.

### Chuỗi `PT...` là gì?

`Duration.toString()` dùng biểu diễn thời lượng kiểu ISO 8601:

| Lệnh | Kết quả dạng chuỗi |
| --- | --- |
| `Duration.ofMinutes(90)` | `PT1H30M` |
| `Duration.ofSeconds(45)` | `PT45S` |
| `Duration.ofDays(1)` | `PT24H` |
| `Duration.ofNanos(1)` | `PT0.000000001S` |
| `Duration.ofSeconds(-1).dividedBy(3)` | `PT-0.333333333S` |

Ký tự `P` chỉ period/duration theo định dạng, `T` bắt đầu phần time. Với Duration, một ngày được hiểu là **24 giờ tiêu chuẩn**, nên `Duration.ofDays(1)` in `PT24H`. `Duration.parse("P1D")` cũng xử lý `D` trong biểu diễn Duration thành 24 giờ thực; **không** vì chữ `D` mà trở thành một ngày lịch có DST.

## 4. Cộng `Duration`: `plus` và các overload

Các dạng thường dùng:

```java
Duration sum = Duration.ofHours(1)
    .plus(Duration.ofMinutes(30))
    .plusSeconds(45);

Duration byUnit = Duration.ofMinutes(30)
    .plus(15, ChronoUnit.MINUTES);

Duration another = Duration.ofHours(2).plusMillis(250);
```

`ChronoUnit` nằm trong `java.time.temporal`. Các helper như `plusDays`, `plusHours`, `plusMinutes`, `plusSeconds`, `plusMillis`, `plusNanos` sử dụng đơn vị được định nghĩa rõ.

**Lưu ý về `Duration.plus(amount, unit)`:** đơn vị phải có độ dài xác định, hoặc là `ChronoUnit.DAYS` được xử lý đặc biệt như **24 giờ**. Không cộng `ChronoUnit.MONTHS` vào `Duration` vì một tháng không có số giây cố định:

```java
// Đơn vị MONTHS có độ dài ước lượng, không hợp lệ cho Duration:
Duration.of(1, ChronoUnit.MONTHS); // DateTimeException
```

`Duration` không tự nhận biết ngày đầu tháng, năm nhuận, múi giờ hay lịch nghỉ. Nếu bài toán thực sự là cộng tháng theo lịch, hãy dùng `Period` hoặc phép toán trên `LocalDate`.

### Cộng vào một mốc thời gian

```java
Instant start = Instant.parse("2026-01-20T02:30:00Z");
Instant deadline = start.plus(Duration.ofMinutes(90));
// 2026-01-20T04:00:00Z.
```

`Instant.plus(duration)` dịch mốc trên timeline bằng độ dài cố định. Đây là lựa chọn phù hợp cho timeout, TTL, expiration timestamp khi yêu cầu tính bằng số giờ/giây thực. Tên "một ngày" trong business không tự động đồng nghĩa 86.400 giây.

## 5. Trừ `Duration` và độ dài có dấu

Các phương thức tương ứng:

```java
Duration quota = Duration.ofMinutes(90);
Duration remaining = quota.minus(Duration.ofMinutes(15));
// PT1H15M.

Duration back = remaining.minusSeconds(45);
// PT1H14M15S.
```

Một Duration âm không tự động là dữ liệu sai. Nếu deadline đã qua, `Duration.between(now, deadline)` có thể âm và rất hữu ích để thể hiện **đã quá hạn bao lâu**. Chọn cách xử lý đúng hợp đồng:

- Nếu API muốn thời gian còn lại có thể âm: giữ dấu.
- Nếu giao diện chỉ hiển thị từ 0 trở lên: áp dụng logic clamp zero tại tầng trình bày/nghiệp vụ.
- Nếu muốn **độ lớn tuyệt đối**: dùng `abs()`, nhưng cần nhớ `abs()/negated()` có thể tràn với một giá trị cực âm.
- Nếu muốn biết thời hạn còn hiệu lực hay không, so hai `Instant` trực tiếp; đừng chỉ so một Duration đã bị làm tròn về phút.

`Duration.minus(Duration)` và `minus(amount,unit)` đều trả bản sao mới; `Duration` ban đầu không đổi. Có thể kiểm thử:

```java
Duration base = Duration.ofMinutes(90);
Duration extra = Duration.ofSeconds(45);
boolean roundTrip = base.plus(extra).minus(extra).equals(base);
// true, trong miền không tràn.
```

Khi tính toán đi qua biên số nguyên, có thể nhận `ArithmeticException`. Không tự giả định một phép toán sẽ "quấn vòng" theo two's complement hay tự bão hòa ở min/max.

## 6. Nhân `Duration` với hệ số nguyên

`Duration.multipliedBy(long multiplicand)` nhân toàn bộ độ dài theo **hệ số nguyên có dấu**:

```java
Duration segment = Duration.ofMinutes(90);

Duration triple = segment.multipliedBy(3);
// PT4H30M.

Duration negative = segment.multipliedBy(-1);
// PT-1H-30M (kiểm tra bằng toInstant/seconds nếu cần),
// và bản gốc vẫn là PT1H30M.

Duration empty = segment.multipliedBy(0);
// PT0S.
```

Đoạn trên minh họa về dấu; vì `Duration.toString()` có quy tắc định dạng số âm riêng, **không dùng chuỗi tự nhập bằng tay như một hợp đồng mà không kiểm chứng**. Cách xác định kết quả đáng tin hơn là `negative.equals(segment.negated())`.

Không có overload `multipliedBy(double)` trong API `Duration`. Nếu nghiệp vụ nói "tăng 1,5 lần", phải chọn đơn vị/precision và quy tắc làm tròn. Một cách đơn giản cho độ dài có thể biểu diễn chính xác là dùng phân số nguyên:

```java
Duration original = Duration.ofMinutes(20);
Duration scaled = original.multipliedBy(3).dividedBy(2);
// PT30M.
```

Khi phần nano không chia đều, phép chia sẽ làm mất độ chính xác nhỏ hơn nanosecond; nếu cần phép nhân/chia chính xác dạng số hữu tỉ trong báo cáo tài chính, có thể dùng `BigDecimal` ở **đơn vị và scale do domain xác định** rồi mới chuyển về Duration.

**Thứ tự phép tính có thể quan trọng:** `original.multipliedBy(3).dividedBy(2)` và `original.dividedBy(2).multipliedBy(3)` có thể cho kết quả khác nhau khi phép chia trước làm mất phần lẻ. Nếu nhân trước dẫn tới overflow, cũng cần mô hình tính toán giới hạn phù hợp.

## 7. Chia `Duration`: hai overload với hai kiểu kết quả

Có hai phép chia khác nhau; **không được nhầm**.

| API | Java | Kết quả | Nghĩa |
| --- | --- | --- | --- |
| `Duration.dividedBy(long divisor)` | Java 8+ | `Duration` | Chia độ dài cho một số nguyên có dấu |
| `Duration.dividedBy(Duration divisor)` | **Java 9+** | `long` | Số **lần trọn vẹn** một Duration nằm trong Duration khác |

### 7.1. Chia theo số nguyên: còn là Duration

```java
Duration original = Duration.ofMinutes(90);
Duration quarter = original.dividedBy(4);
// PT22M30S.
```

Độ dài 90 phút được chia thành bốn phần 22 phút 30 giây. `dividedBy(long)` nhận số nguyên khác 0, bao gồm số âm; phép chia thực hiện với precision tối đa tới nano giây.

```java
Duration tiny = Duration.ofNanos(1).dividedBy(2);
// PT0S: không thể lưu nửa nanosecond trong Duration.
```

Đây là **mất phần lẻ theo độ phân giải nano giây**, không phải hành vi làm tròn theo chính sách ngân hàng. Nếu chia một độ dài âm:

```java
Duration negativePart =
    Duration.ofSeconds(-1).dividedBy(3);
// PT-0.333333333S.
```

Giá trị thực -0,333333333... giây bị cắt ở mức nano giây, theo hướng về 0. Vì vậy `part.multipliedBy(3)` không khôi phục đủ -1 giây.

**Không thể chia cho 0:**

```java
try {
    Duration.ofSeconds(1).dividedBy(0);
} catch (ArithmeticException ex) {
    // Từ chối tham số divisor = 0 theo hợp đồng.
}
```

Ngay cả chia cho giá trị hợp lệ cũng có thể ném `ArithmeticException` nếu kết quả vượt miền biểu diễn của `Duration`.

### 7.2. Chia cho một Duration: số khoảng trọn vẹn, Java 9+

```java
Duration budget = Duration.ofMinutes(90);
Duration slot = Duration.ofMinutes(35);

long wholeSlots = budget.dividedBy(slot);
// 2: có 2 khoảng 35 phút trọn vẹn trong 90 phút.
```

Dạng này trả về **`long`, không phải Duration**. Số lần được làm tròn **về 0**, kể cả kết quả âm. Do đó đây là công cụ đếm đơn vị trọn vẹn, không phải phép chia để nhận độ dài một phần.

Ví dụ đếm số slot và phần dư:

```java
Duration quota = Duration.ofMinutes(95);
Duration unit = Duration.ofMinutes(30);

long count = quota.dividedBy(unit); // 3.
Duration remainder = quota.minus(unit.multipliedBy(count));
// PT5M.
```

Đây là mẫu thương + phần dư theo **độ dài thực**:

```text
quota = unit × count + remainder
95 phút = 30 phút × 3 + 5 phút
```

Với `quota` âm hoặc `unit` âm, quy tắc làm tròn thương về 0 có thể tạo phần dư có dấu, **không tự giả định** phần dư luôn không âm. Một bài toán tính phí slot thường cần làm tròn **lên** chứ không phải lấy thương trọn vẹn; hãy viết chính sách ceil/floor/round khác nhau một cách rõ ràng.

**Java 8 không có `Duration.dividedBy(Duration)`.** Nếu dự án bắt buộc compile `--release 8`, không gọi overload này; thay bằng phép tính số nguyên trên một đơn vị chính xác và an toàn tràn, ví dụ `toMinutes()` trong miền hợp lệ hoặc sử dụng `BigInteger` cho nhu cầu lớn. Ví dụ hoàn chỉnh cuối bài dùng `--release 17` nên overload này hợp lệ.

## 8. `Period`: khoảng năm, tháng, ngày **theo lịch**

`Period` có ba trường số nguyên: `years`, `months` và `days`. Nó **không phải tổng số giây** và cũng không tự có một độ dài nano giây:

```java
Period renewal = Period.of(1, 14, 3);
// P1Y14M3D.

Period oneMonth = Period.ofMonths(1);
Period twoWeeks = Period.ofWeeks(2);
// P14D.
```

Các thành phần của `Period` được phép có dấu riêng. Một Period có thể có `years=1`, `months=-2` và `days=3`; `isNegative()` trả `true` nếu **bất kỳ** thành phần nào âm, không phải kiểm tra "giá trị tổng thời gian theo ngày" (vốn chưa thể xác định nếu không có mốc).

Sự khác biệt căn bản:

- `Duration.ofDays(1)` = **chính xác 86.400 giây**.
- `Period.ofDays(1)` = **một ngày lịch** được áp dụng cho mốc ngày/giờ thích hợp.
- `Period.ofMonths(1)` = **một tháng lịch**; không có định nghĩa tương đương đúng cho tất cả mốc bắt đầu bằng 28, 29, 30 hay 31 ngày.
- `Period.ofYears(1)` không phải lúc nào cũng 365 ngày vì năm nhuận.

`Period` là kiểu immutable, thread-safe và value-based. Các phép toán `plus`, `minus`, `multipliedBy` trả bản sao, không thay đổi nguồn.

## 9. Cộng và trừ `Period`: cộng **từng thành phần**

Ví dụ:

```java
Period base = Period.of(1, 14, 3);
// P1Y14M3D.

Period added = base.plus(Period.of(0, 2, 4));
// P1Y16M7D.

Period subtracted = base.minus(Period.ofMonths(1));
// P1Y13M3D.
```

`Period.plus(TemporalAmount)`/`minus(TemporalAmount)` trong ngữ cảnh ISO cộng/trừ **years, months, days tương ứng**. Chúng **không tự chuyển 16 tháng thành 1 năm 4 tháng**, cũng **không tự đổi 30 ngày thành 1 tháng**.

Có các helper:

```java
Period result = Period.ofYears(1)
    .plusMonths(6)
    .minusDays(3);
// P1Y6M-3D.
```

Các thành phần âm vẫn hợp lệ về mặt biểu diễn. Tuy nhiên, một Period có hỗn hợp dấu âm/dương có thể khó hiểu khi áp dụng nhiều tháng và ngày vào mốc cuối tháng. Với dữ liệu từ API, nên quy định có cho phép Period hỗn hợp dấu hay yêu cầu các thành phần cùng chiều.

**Không pha thẳng `Period` vào `Duration.plus(...)` để đổi tháng thành giây.** Cần mốc ngày và zone để xác định các tháng và ngày lịch có chiều dài bao nhiêu.

## 10. Nhân `Period` và chuẩn hóa tháng/năm

`Period.multipliedBy(int scalar)` nhân **từng trường**:

```java
Period base = Period.of(1, 14, 3);
Period twice = base.multipliedBy(2);
// P2Y28M6D.
```

`Period` **không tự normalize** sau phép nhân. Nếu muốn đổi các tháng dư thành năm/tháng:

```java
Period normalized = base.normalized();
// P2Y2M3D.

long months = base.toTotalMonths();
// 26, bằng 1*12 + 14.
```

**`normalized()` chỉ xử lý năm và tháng, không chuyển ngày thành tháng.** Ví dụ `Period.ofDays(40).normalized()` vẫn là `P40D`; không có phép chuyển chính xác "40 ngày bằng bao nhiêu tháng" khi chưa biết ngày bắt đầu.

Hai lưu ý:

- `Period.normalized()` đổi dạng biểu diễn, không sửa object gốc. `Period.ofMonths(14)` và `Period.of(1,2,0)` không `equals` theo các trường trước chuẩn hóa, dù có cùng 14 tháng.
- `toTotalMonths()` chỉ tính **năm × 12 + tháng**, **không đếm ngày**. Với `P1Y14M3D`, kết quả là 26 tháng; **3 ngày vẫn còn** và không tự được tính vào thương.

Nếu phép toán trên các trường vượt miền `int`, API ném `ArithmeticException`. Ví dụ `Period.ofYears(Integer.MAX_VALUE).plusYears(1)` là overflow; không tự wrap về số âm hợp lệ.

## 11. Vì sao `Period` không có `dividedBy(...)`?

Java không định nghĩa phương thức `Period.dividedBy(...)`. Đây không phải thiếu sót cần thay bằng chia số giây tùy tiện, bởi phép chia theo lịch **chưa đủ nghĩa** nếu không biết:

- Mốc bắt đầu và mốc kết thúc nào?
- Có chia theo **tháng nguyên**, **ngày nguyên**, **giờ thực** hay tỷ lệ tài chính?
- Nếu một tháng có 31 ngày, chia hai kỳ là 15/16 ngày hay tạo một ngày chốt cố định?
- Nếu rơi vào ngày 29, 30, 31 hoặc ngày chuyển DST, lấy quy tắc gì?
- Nếu kết quả có nửa ngày, domain có cho phép không và lưu dạng gì?

Ba hướng giải quyết tùy hợp đồng:

**A. Chia số đơn vị tháng nguyên** khi Period không chứa ngày và dùng quy tắc đơn vị tháng:

```java
Period term = Period.ofMonths(12);
int installments = 4;
Period perInstallment = Period.ofMonths(
    (int) (term.toTotalMonths() / installments));
// P3M, với giả định số tháng chia hết.
```

Đây chỉ là cách làm hợp lệ nếu **chia hết** và domain cho phép tháng nguyên. Nếu không chia hết, cần chính sách phân phối phần dư tháng, không tự làm tròn âm thầm.

**B. Chia khoảng thời gian thực giữa hai instant** khi yêu cầu là chia đều theo giây/nano:

```java
Instant start = Instant.parse("2026-01-01T00:00:00Z");
Instant end = Instant.parse("2026-01-02T00:00:00Z");

Duration half = Duration.between(start, end).dividedBy(2);
// PT12H.
```

**C. Phân chia lịch theo ngày chốt nghiệp vụ**: xác định các `LocalDate` thanh toán rồi tính từng khoảng thực tế; không biến `Period.ofMonths(1)` thành một Duration cố định.

Vì thế, khi thiết kế API, một field `"period": "P1M"` không thể tự trả lời câu hỏi "bao nhiêu giây?" nếu không có mốc và zone hoặc một chính sách được công bố.

## 12. Tháng cuối tháng và tính không kết hợp của phép áp dụng

Một điểm rất quan trọng: **nhân `Period` không luôn tương đương với việc áp dụng một `Period` nhỏ nhiều lần vào ngày lịch**.

Dữ liệu:

```java
LocalDate start = LocalDate.of(2024, 1, 31);

LocalDate atOnce = start.plus(Period.ofMonths(2));
// 2024-03-31.

LocalDate repeated = start.plusMonths(1).plusMonths(1);
// 2024-03-29.
```

Giải thích từng bước:

1. `31/01/2024 + 2 tháng` trực tiếp → `31/03/2024`, bởi tháng 3 có ngày 31.
2. `31/01/2024 + 1 tháng` → `29/02/2024` (năm nhuận, February không có ngày 31).
3. Sau đó `29/02/2024 + 1 tháng` → `29/03/2024`.

Do đó:

```text
start.plus(Period.ofMonths(2))
    != start.plusMonths(1).plusMonths(1)
```

Đây không phải bug trong `LocalDate`. Đó là kết quả của quy tắc **điều chỉnh sang ngày cuối hợp lệ của tháng** khi một ngày như 31 không có trong tháng đích. Vì vậy cần định nghĩa *hợp đồng gia hạn*:

- **Neo theo ngày ban đầu**: mỗi kỳ được tính từ 31/01 với tổng số tháng kể từ ngày neo.
- **Neo theo ngày đến hạn trước**: mỗi kỳ lấy ngày kỳ trước + 1 tháng, có thể dần dần trở thành ngày 29.
- **Cuối tháng theo nghiệp vụ**: nếu ngày ban đầu là cuối tháng, luôn chọn cuối tháng ở kỳ mới.
- **Không cho tự điều chỉnh**: từ chối hoặc yêu cầu xử lý thủ công khi ngày mục tiêu không tồn tại.

Không ngầm mặc định bất kỳ mô hình nào nếu ảnh hưởng hợp đồng thanh toán hoặc hạn pháp lý.

### Phép trừ lịch không phải luôn là nghịch đảo hoàn hảo trên ngày

Do quy tắc điều chỉnh ngày cuối tháng, không phải mọi mốc đều phục hồi khi cộng rồi trừ tháng:

```java
LocalDate original = LocalDate.of(2024, 1, 31);
LocalDate shifted = original.plusMonths(1); // 2024-02-29.
LocalDate returned = shifted.minusMonths(1); // 2024-01-29.
```

`returned` khác `original`. Đừng kiểm thử lịch bằng định luật `date.plusMonths(1).minusMonths(1).equals(date)` cho tất cả ngày. Thay vào đó, kiểm thử **chính sách điều chỉnh ngày** của domain và các trường hợp ngày 28–31.

## 13. DST: `Period.ofDays(1)` khác `Duration.ofDays(1)`

Đây là ví dụ rõ nhất về cùng chữ **"ngày"** nhưng hai hợp đồng khác nhau.

Ở `America/New_York` trước khi đổi DST mùa xuân năm 2024:

```java
ZoneId ny = ZoneId.of("America/New_York");
ZonedDateTime before = ZonedDateTime.of(
    LocalDate.of(2024, 3, 9), LocalTime.NOON, ny);
// 2024-03-09T12:00-05:00[America/New_York].
```

**Cộng một ngày theo lịch:**

```java
ZonedDateTime nextCalendarDay =
    before.plus(Period.ofDays(1));
// 2024-03-10T12:00-04:00[America/New_York].

long calendarElapsedHours = Duration.between(
    before.toInstant(), nextCalendarDay.toInstant()).toHours();
// 23.
```

Giờ địa phương vẫn **12:00** hôm sau, nhưng giữa hai instant chỉ có **23 giờ thực** vì đồng hồ địa phương đã nhảy tiến một giờ.

**Cộng đúng 24 giờ thực:**

```java
ZonedDateTime after24Hours =
    before.plus(Duration.ofDays(1));
// 2024-03-10T13:00-04:00[America/New_York].

long elapsedHours = Duration.between(
    before.toInstant(), after24Hours.toInstant()).toHours();
// 24.
```

Kết quả là **13:00** địa phương hôm sau. Cả hai kết quả đều đúng theo hợp đồng của chính loại khoảng:

- `Period.ofDays(1)`: *ngày lịch*, cố giữ local clock.
- `Duration.ofDays(1)`: *24 giờ thực*, không cam kết giữ local clock.

Với DST overlap mùa thu, một ngày địa phương có thể dài 25 giờ. Nếu domain yêu cầu thời điểm kết thúc ngày làm việc, truy vấn log theo ngày chi nhánh hoặc lịch học hằng ngày, hãy tạo ranh giới từ `LocalDate` và `ZoneId` thay vì cộng cứng `Duration.ofDays(1)`.

**Lưu ý:** một giờ địa phương rơi vào gap có thể không tồn tại; thao tác lịch có thể phải điều chỉnh theo quy tắc `ZonedDateTime`. Nếu nghiệp vụ cấm tự dịch giờ, dùng `ZoneRules.getValidOffsets(local)` và chính sách giải quyết tường minh.

## 14. Phép toán giữa các loại mốc thời gian

Các loại `Temporal` không nhận cùng bộ đơn vị. Chọn API theo kiểu mốc:

| Dữ liệu | Cộng/trừ thích hợp | Tránh |
| --- | --- | --- |
| `Instant` | `plus(Duration)`, `minus(Duration)`, `Duration.between(instant1,instant2)` | Tự gán tháng lịch thiếu zone |
| `LocalDate` | `plus(Period)`, `plusMonths`, `minusDays`, `Period.between(LocalDate,LocalDate)` | Dùng số giây để thay tháng/ngày lịch |
| `LocalDateTime` | `plus(Duration)` hoặc `plus(Period)` tùy yêu cầu, nhưng chưa có offset | Gọi nó là mốc UTC nếu chưa có hợp đồng |
| `ZonedDateTime` | `plus(Duration)` để giữ thời lượng thực, `plus(Period)` để giữ lịch | Nhầm 24 giờ với ngày địa phương |
| `OffsetDateTime` | `plus(Duration)` tại offset hiện có | Coi offset cố định là toàn bộ quy tắc DST của vùng |
| `LocalTime` | `plusSeconds/plusMinutes` trong ngày theo cơ chế wrap | Dùng LocalTime một mình làm độ dài vượt ngày không mất thông tin |

**`LocalTime` là giờ đồng hồ** và có thể quay vòng trong 24 giờ. `LocalTime.of(23,30).plusHours(2)` thành `01:30`, nhưng **không giữ số ngày đã đi qua**. Nếu cần ngày cụ thể, dùng `LocalDateTime`/`ZonedDateTime` và kiểu khoảng phù hợp.

`Duration.between(...)` thường phù hợp với **hai instant** hoặc hai temporal có hỗ trợ đo theo giây. Với hai `LocalDate` thuần túy, dùng `ChronoUnit.DAYS.between(date1,date2)` hoặc `Period.between(date1,date2)` tùy cần tổng số ngày hay thành phần năm/tháng/ngày. Đừng giả định `Duration.between(LocalDate, LocalDate)` có nghĩa "số ngày × 24h"; LocalDate không cung cấp time-of-day.

## 15. Làm tròn, phần dư, số âm và overflow theo hợp đồng

### 15.1. Precision của Duration là nanosecond

`Duration.ofNanos(1).dividedBy(2)` ra `Duration.ZERO`. Nếu nghiệp vụ yêu cầu chia công bằng một nanosecond giữa hai đối tượng, **không thể** biểu diễn hai phần bằng nhau bằng `Duration` nguyên nano. Cần công bố chính sách phân phối phần dư, ví dụ một bên 1ns và một bên 0ns.

Tương tự, chia 1 giây thành ba phần:

```java
Duration third = Duration.ofSeconds(1).dividedBy(3);
// PT0.333333333S.

Duration reconstructed = third.multipliedBy(3);
// PT0.999999999S, thiếu 1ns.
```

Không dùng `dividedBy` để hứa "tổng các phần bằng bản gốc" nếu phép chia không hết. Đối với khoản phí hoặc quota cần bảo toàn tổng, chọn thuật toán chia thương + phân phối remainder.

### 15.2. Hướng làm tròn phải được nêu rõ

| Bối cảnh | Chính sách thường cần | API liên quan |
| --- | --- | --- |
| Chia Duration cho số nguyên | Bỏ phần vượt quá độ phân giải nano, hướng về 0 | `Duration.dividedBy(long)` |
| Đếm số slot trọn vẹn | Thương nguyên hướng về 0 | `Duration.dividedBy(Duration)` (Java 9+) |
| Tính số slot cần mua nếu còn phút lẻ | Thường làm tròn **lên** cho đầu vào dương | Domain rule riêng, không chỉ `dividedBy` |
| Hiển thị phút nguyên | Cần quy định floor/ceil/round | Không mặc định `toMinutes` phù hợp mọi nghiệp vụ |
| Thanh toán theo tháng | Ngày chốt/đơn vị lịch cụ thể | `Period` + quy tắc lịch |
| Báo cáo tiền từ thời gian | Precision decimal và rounding theo quy tắc tài chính | `BigDecimal`/đơn vị xác định |

`Duration.toMinutes()` trả số phút trọn vẹn theo phép chia số giây và bỏ phần dư; ví dụ `Duration.ofSeconds(119).toMinutes()` là 1. Đó không phải làm tròn 119 giây thành 2 phút theo cách tính phí dịch vụ.

### 15.3. Overflow và chia cho 0

`Duration` có miền giới hạn bởi `long seconds` và phần nano; `Period` lưu ba thành phần kiểu `int`. Có thể ném `ArithmeticException` khi:

- Nhân một Duration lớn với hệ số lớn.
- Cộng vượt giới hạn `Duration` hoặc thành phần `Period`.
- Gọi `dividedBy(0)` hoặc chia cho `Duration.ZERO`.
- Đổi Duration lớn thành `long` nano/milli nếu vượt miền.
- `negated()/abs()` khi trị tuyệt đối không thể biểu diễn.

Ví dụ:

```java
try {
    Duration.ofSeconds(Long.MAX_VALUE).plusSeconds(1);
} catch (ArithmeticException overflow) {
    // Từ chối phép cộng vượt miền.
}

try {
    Period.ofYears(Integer.MAX_VALUE).plusYears(1);
} catch (ArithmeticException overflow) {
    // Từ chối phép cộng năm vượt miền int.
}
```

Một implementation Java hiện hành **không tự clip** về giá trị lớn nhất hợp lệ hoặc wrap sang giá trị âm theo ý người dùng. Nên validate input từ API và định nghĩa response lỗi cho số quá lớn, không tự nuốt exception rồi trả khoảng `Duration.ZERO`.

### 15.4. Số âm và giá trị đặc biệt

`Duration.between(end,start)` có thể âm. `Period.of(1,-2,3)` có thành phần âm và `Period.isNegative()` trả true vì có một trường âm. Nếu API không cho phép khoản âm, cần kiểm tra rõ ngay ở ranh giới.

`Duration.ZERO`, `Period.ZERO` là giá trị hợp lệ cho hợp đồng có "không thời lượng". Trong một số domain, 0 là input không hợp lệ (ví dụ slot phải lớn hơn 0), nhưng đây là **quy tắc nghiệp vụ**, không phải điều Java áp đặt lên toàn bộ Duration.

## 16. Ứng dụng trong thiết kế API, DB và lịch xử lý

### 16.1. API phân biệt kiểu lượng

Một hợp đồng API có thể thiết kế:

```json
{
  "retryDelay": "PT45S",
  "sessionTtl": "PT2H",
  "renewalPeriod": "P1M"
}
```

Giải thích:

- `retryDelay` và `sessionTtl` là `Duration`, đơn vị thực.
- `renewalPeriod` là `Period` tháng lịch, chỉ có nghĩa chính xác khi áp dụng với ngày gia hạn.
- Nếu dùng numeric thay chuỗi, hãy đặt tên có đơn vị như `timeoutMillis` hoặc `intervalSeconds`.
- Không parse `P1M` của `Period` thành Duration một tháng cố định; Duration không chấp nhận MONTHS vì số giây theo tháng là biến thiên.

**Không ép input không hợp lệ thành một con số mặc định.** Ví dụ người dùng gửi `"P1M"` vào field timeout có hợp đồng Duration: nên trả lỗi validation có giải thích, không tự hiểu là 30 ngày.

### 16.2. Lưu trữ theo semantics

- **Thời điểm sự kiện:** `Instant`, lưu vào cột timestamp tương ứng với semantics DB/driver.
- **Thời lượng timeout:** một số nguyên giây/milli/nano với đơn vị rõ, hoặc biểu diễn Duration ISO được kiểm soát.
- **Chu kỳ tháng/năm:** lưu `years/months/days` hoặc chuỗi Period/contract calendar, kèm chính sách day-of-month/zone nếu có.
- **Ngày hạn theo lịch:** lưu `LocalDate`/SQL `DATE`.
- **Lịch chạy lặp:** lưu local time, zone ID và recurrence rule, không chỉ dùng một Duration 24h giữa mọi lần chạy.

PostgreSQL `timestamptz` lưu mốc thực nhưng không giữ toàn bộ region ID gốc; nếu zone của lịch có giá trị domain, lưu `ZoneId` riêng. Các mapping JDBC/ORM và precision cần integration test; không suy từ cùng tên kiểu SQL rằng mọi database có cùng hành vi.

### 16.3. Timeout không đồng nghĩa với lịch hẹn

Timeout "đợi tối đa 90 giây" cần một `Duration`. Nhưng để đo timeout **thực tế theo thời gian trôi qua trong cùng tiến trình**, cân nhắc bộ đo monotonic của nền tảng (`System.nanoTime()` hoặc clock tương thích) thay vì so `Instant.now()` khi đồng hồ hệ thống có thể bị chỉnh. `Duration` biểu diễn độ dài; nó không tự đảm bảo clock dùng để đo là monotonic.

Lịch sự kiện "09:30 thứ Hai mỗi tuần" phải dùng logic calendar và `ZoneId`. Không tự tạo lịch bằng cách cứ cộng `Duration.ofDays(7)` vì sau DST giờ địa phương có thể thay đổi.

## 17. Kiểm thử các bất biến của phép toán

Đừng chỉ test một ví dụ ngày bình thường. Cần kiểm tra các lớp lỗi khác nhau:

| Loại kiểm thử | Ca ví dụ | Điều cần khẳng định |
| --- | --- | --- |
| Cộng/trừ Duration | 90 phút +45s -45s | Trả về 90 phút nếu không overflow |
| Nhân Duration | 90 phút ×3 | 270 phút |
| Chia Duration đều | 90 phút /4 | 22 phút 30 giây |
| Chia không hết | 1ns /2 | 0ns theo độ phân giải |
| Chia âm | -1s /3 | -0.333333333s |
| Chia cho Duration | 95 phút /30 phút | 3 slot, dư 5 phút |
| Chia cho 0 | 1s /0 | `ArithmeticException` |
| Tràn Duration | `Long.MAX_VALUE` seconds +1 | `ArithmeticException` |
| Tràn Period | `Integer.MAX_VALUE` years +1 | `ArithmeticException` |
| Cộng Period | P1Y14M3D + P2M4D | P1Y16M7D, không tự normalize |
| Normalize Period | P1Y14M3D | P2Y2M3D, day giữ nguyên |
| Nhân Period | P1Y14M3D ×2 | P2Y28M6D |
| Tháng cuối tháng | Jan 31 +2 tháng so với +1 tháng hai lần | Hai ngày kết quả **khác nhau** |
| DST qua Period/Duration | New York 09/03/2024 trưa +1 ngày | 12:00 hôm sau so với 13:00 |
| Input MONTHS cho Duration | `Duration.of(1,MONTHS)` | `DateTimeException` |
| Số âm Period hỗn hợp | P1Y-2M3D | `isNegative()` là true |

Với kiểm thử có mốc hiện tại, inject `Clock.fixed(...)` để không phụ thuộc ngày, giờ và timezone mặc định máy CI. Với lịch DST, dùng `ZoneId` vùng và ngày mốc cố định; không phụ thuộc `ZoneId.systemDefault()`. Nếu doanh nghiệp cần tái dựng lịch sử theo các phiên bản timezone rules, quy định chính sách tzdb và dữ liệu audit tương ứng.

## 18. Chương trình Java hoàn chỉnh — kết quả đã kiểm chứng

Tạo file **`TimeAmountArithmeticDemo.java`**. Mã dùng **Java 17+** để sử dụng cả `Duration.dividedBy(Duration)` (được bổ sung từ Java 9). Các phép `plus/minus/multipliedBy` của Duration/Period vẫn có từ Java 8. Chương trình minh họa số âm, phép chia nanosecond, Period normalize, cuối tháng, DST, phần dư và ngoại lệ.

```java
import java.time.*;
import java.time.temporal.ChronoUnit;
import java.util.*;

public class TimeAmountArithmeticDemo {
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        Duration base = Duration.ofMinutes(90);
        Duration delay = Duration.ofSeconds(45);
        System.out.println("duration base: " + base);
        System.out.println("duration plus: " + base.plus(delay));
        System.out.println("duration minus: " + base.minusMinutes(15));
        System.out.println("duration times three: " + base.multipliedBy(3));
        System.out.println("duration quarter: " + base.dividedBy(4));
        System.out.println("duration whole ratio: " +
                base.dividedBy(Duration.ofMinutes(35)));
        System.out.println("duration nanos truncated: " +
                Duration.ofNanos(1).dividedBy(2));
        System.out.println("duration negative third: " +
                Duration.ofSeconds(-1).dividedBy(3));
        System.out.println("duration minus one millis internals: " +
                Duration.ofMillis(-1).getSeconds() + "/" +
                Duration.ofMillis(-1).getNano());
        System.out.println("duration one day: " + Duration.ofDays(1));
        System.out.println("duration 119 seconds to minutes: " +
                Duration.ofSeconds(119).toMinutes());

        Period period = Period.of(1, 14, 3);
        System.out.println("period base: " + period);
        System.out.println("period plus: " +
                period.plus(Period.of(0, 2, 4)));
        System.out.println("period minus: " +
                period.minus(Period.ofMonths(1)));
        System.out.println("period times two: " + period.multipliedBy(2));
        System.out.println("period normalized: " + period.normalized());
        System.out.println("period total months: " + period.toTotalMonths());
        System.out.println("period mixed sign negative: " +
                Period.of(1, -2, 3).isNegative());

        LocalDate endOfJanuary = LocalDate.of(2024, 1, 31);
        LocalDate addTwoAtOnce = endOfJanuary.plus(Period.ofMonths(2));
        LocalDate addOneTwice = endOfJanuary.plusMonths(1).plusMonths(1);
        System.out.println("January 31 plus one month: " +
                endOfJanuary.plus(Period.ofMonths(1)));
        System.out.println("January 31 plus two months: " + addTwoAtOnce);
        System.out.println("January 31 plus one twice: " + addOneTwice);

        ZoneId ny = ZoneId.of("America/New_York");
        ZonedDateTime before = ZonedDateTime.of(
                LocalDate.of(2024, 3, 9), LocalTime.NOON, ny);
        ZonedDateTime calendarDay = before.plus(Period.ofDays(1));
        ZonedDateTime exactDay = before.plus(Duration.ofDays(1));
        System.out.println("DST period +1d: " + calendarDay);
        System.out.println("DST duration +1d: " + exactDay);
        System.out.println("DST period elapsed hours: " +
                Duration.between(before.toInstant(),
                        calendarDay.toInstant()).toHours());
        System.out.println("DST duration elapsed hours: " +
                Duration.between(before.toInstant(),
                        exactDay.toInstant()).toHours());

        Duration quota = Duration.ofMinutes(95);
        Duration unit = Duration.ofMinutes(30);
        long completeUnits = quota.dividedBy(unit);
        Duration left = quota.minus(unit.multipliedBy(completeUnits));
        System.out.println("whole periods in quota: " + completeUnits);
        System.out.println("remainder of quota: " + left);

        try {
            Duration.ofSeconds(1).dividedBy(0);
            throw new AssertionError("zero-divisor not rejected");
        } catch (ArithmeticException ex) {
            System.out.println("divide by zero: ArithmeticException");
        }
        try {
            Duration.ofSeconds(Long.MAX_VALUE).plusSeconds(1);
            throw new AssertionError("overflow not rejected");
        } catch (ArithmeticException ex) {
            System.out.println("duration overflow: ArithmeticException");
        }
        try {
            Period.ofYears(Integer.MAX_VALUE).plusYears(1);
            throw new AssertionError("overflow not rejected");
        } catch (ArithmeticException ex) {
            System.out.println("period overflow: ArithmeticException");
        }
        try {
            Duration.of(1, ChronoUnit.MONTHS);
            throw new AssertionError("estimated unit unexpectedly accepted");
        } catch (DateTimeException ex) {
            System.out.println("duration months invalid: DateTimeException");
        }

        check(base.plus(delay).minus(delay).equals(base),
                "plus-minus roundtrip");
        check(base.dividedBy(4).multipliedBy(4).equals(base),
                "even division roundtrip");
        check(Duration.ofNanos(1).dividedBy(2).isZero(),
                "nanosecond truncation");
        check(period.normalized().getDays() == 3,
                "normalization should not turn days into months");
        check(!addTwoAtOnce.equals(addOneTwice),
                "calendar end-of-month distinction");
        check(Duration.between(before.toInstant(),
                calendarDay.toInstant()).equals(Duration.ofHours(23)),
                "DST elapsed time");
        check(quota.equals(unit.multipliedBy(completeUnits).plus(left)),
                "quotient and remainder");
        System.out.println("all checks passed");
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac --release 17 -encoding UTF-8 TimeAmountArithmeticDemo.java
java TimeAmountArithmeticDemo
```

Kết quả chuẩn, đã kiểm thử:

```text
duration base: PT1H30M
duration plus: PT1H30M45S
duration minus: PT1H15M
duration times three: PT4H30M
duration quarter: PT22M30S
duration whole ratio: 2
duration nanos truncated: PT0S
duration negative third: PT-0.333333333S
duration minus one millis internals: -1/999000000
duration one day: PT24H
duration 119 seconds to minutes: 1
period base: P1Y14M3D
period plus: P1Y16M7D
period minus: P1Y13M3D
period times two: P2Y28M6D
period normalized: P2Y2M3D
period total months: 26
period mixed sign negative: true
January 31 plus one month: 2024-02-29
January 31 plus two months: 2024-03-31
January 31 plus one twice: 2024-03-29
DST period +1d: 2024-03-10T12:00-04:00[America/New_York]
DST duration +1d: 2024-03-10T13:00-04:00[America/New_York]
DST period elapsed hours: 23
DST duration elapsed hours: 24
whole periods in quota: 3
remainder of quota: PT5M
divide by zero: ArithmeticException
duration overflow: ArithmeticException
period overflow: ArithmeticException
duration months invalid: DateTimeException
all checks passed
```

Giải thích các dòng đáng chú ý:

1. `duration quarter` là `PT22M30S`: chia 90 phút cho bốn phần chính xác.
2. `duration whole ratio` bằng 2: chỉ đếm được hai khoảng 35 phút trọn vẹn trong 90 phút.
3. `duration nanos truncated` là `PT0S`; không thể biểu diễn 0,5 nanosecond.
4. `duration negative third` là `PT-0.333333333S`; phần nhỏ hơn một nano giây bị loại theo hướng về 0.
5. `duration minus one millis internals` = `-1/999000000` cho thấy lưu trữ hai trường được chuẩn hóa.
6. `period plus` là `P1Y16M7D`, chưa tự chuyển 16 tháng sang năm.
7. `period normalized` là `P2Y2M3D`, giữ nguyên 3 ngày.
8. Cộng hai tháng một lần từ 31/01/2024 ra 31/03; cộng một tháng hai lần ra 29/03.
9. `DST period +1d` giữ 12:00 theo đồng hồ, nhưng chỉ 23 giờ thực; `DST duration +1d` là 13:00 theo đồng hồ, đủ 24 giờ thực.
10. Phần quota 95 phút được tách 3 slot ×30 phút +5 phút dư.
11. Các trường hợp chia cho 0, overflow và gán MONTHS vào Duration đều ném ngoại lệ được in rõ; nếu không, chương trình chủ động ném `AssertionError`.
12. `all checks passed` chứng minh các bất biến cơ bản và hành vi DST của bộ test đều khớp.

## 19. Những lỗi phổ biến và cách tránh

| Sai lầm | Nguyên nhân | Cách làm đúng |
| --- | --- | --- |
| Coi `Duration.ofDays(1)` và `Period.ofDays(1)` tương đương ở mọi zone | Một bên là 24 giờ, một bên là ngày lịch | Chọn theo business rule |
| Đổi một tháng lịch thành `Duration.ofDays(30)` | Tháng có độ dài khác nhau | `Period.ofMonths(1)` + mốc lịch |
| Mong `Period.dividedBy(...)` chạy được | API `Period` không có phép chia này | Chọn đơn vị tháng/ngày hoặc đổi thành Duration sau khi có mốc |
| Nhầm hai overload `Duration.dividedBy` | Một hàm trả Duration, một hàm trả long | Dựa vào kiểu divisor và kiểu kết quả |
| Dùng overload `dividedBy(Duration)` trong Java 8 | Overload xuất hiện từ Java 9 | Nâng target hoặc dùng phép tính thay thế có kiểm soát |
| Chia 1ns/2 mà kỳ vọng giữ 0,5ns | Duration chỉ tới nano giây | Định nghĩa phần dư và rounding |
| Chia 95 phút/30 phút nhưng coi 3 là số slot tính phí đã làm tròn lên | Chỉ đếm slot trọn vẹn | Xử lý dư 5 phút theo policy |
| Gọi `Duration.of(1, MONTHS)` | MONTHS là đơn vị ước lượng | Dùng `Period` để tính tháng |
| Nghĩ `Period.plus` tự normalize tháng thành năm | Cộng từng trường, có thể còn 16 tháng | Gọi `normalized()` nếu cần |
| Nghĩ `Period.normalized` đổi ngày thành tháng | Số ngày trong tháng biến đổi | Chỉ normalize years/months |
| Dựa vào `Period.toTotalMonths` để có tổng độ dài mọi thành phần | Hàm bỏ qua `days` | Dùng mốc bắt đầu để resolve phần ngày |
| Nghĩ nhân `Period.ofMonths(1)` với 2 như áp dụng hai kỳ liên tiếp | Cuối tháng làm quy tắc calendar khác nhau | Chọn ngày neo/gia hạn rõ |
| Nghĩ cộng rồi trừ một tháng luôn trả mốc gốc | Quy tắc clamping ngày 28–31 | Test cuối tháng/năm nhuận |
| Lấy `Duration.toMinutes` như phép làm tròn lên | Chỉ lấy số phút trọn vẹn | Viết chính sách ceil/floor |
| Dùng `getSeconds` một mình để nhận trị giây âm chính xác | Phần nano được chuẩn hóa dương | Kết hợp `getSeconds/getNano` hoặc dùng API đúng |
| Gộp Duration/Period không xét `Temporal` nhận các đơn vị nào | Có thể thiếu trường giây hoặc lịch | Kiểm tra kiểu mốc và API |
| Cộng một Duration 24h để đặt lịch đúng 09:00 hôm sau ở vùng DST | Giờ địa phương bị lệch | Phép toán ngày lịch với ZoneId |
| Dùng timezone máy server cho lịch người dùng | Có thể đổi kết quả khi deploy | IANA ZoneId theo domain |
| Không xử lý chia cho 0 | `ArithmeticException` | Validate divisor |
| Dùng số lớn và kỳ vọng wrap/clip | API có thể ném khi overflow | Validate miền và bắt lỗi tại boundary |
| Tự format Duration/Period thành một số không ghi đơn vị | Mất semantics | ISO duration/period hoặc field kèm unit |
| Không dùng test ở ngày 29/02 và qua DST | Bỏ lọt lỗi lịch | Thêm case cuối tháng, năm nhuận, gap/overlap |
| Đo timeout bằng đồng hồ hệ thống có thể chỉnh giờ | Thời gian trôi qua bị sai | Chọn monotonic clock cho đo elapsed |
| Suy rằng kết quả stdout phụ thuộc default JVM timezone | Không khóa môi trường | Dùng `ZoneId`/mốc cố định |

## 20. Bài tập tự luyện có lời giải

### Bài 1 — Duration cộng/trừ

Cho `Duration.ofMinutes(80)`. Thêm 25 phút rồi trừ 10 phút được gì?

**Đáp án:** 95 phút = `PT1H35M`.

```java
Duration value = Duration.ofMinutes(80)
    .plusMinutes(25)
    .minusMinutes(10);
```

### Bài 2 — Nhân rồi chia Duration

Một đoạn kéo dài 15 phút. Nhân 8 lần và chia 3 phần bằng nhau được bao nhiêu?

**Đáp án:** `15 × 8 / 3 = 40` phút mỗi phần.

```java
Duration portion = Duration.ofMinutes(15)
    .multipliedBy(8)
    .dividedBy(3);
// PT40M.
```

### Bài 3 — Chia không hết

`Duration.ofNanos(5).dividedBy(2)` cho gì? Hai phần nhân lại có đúng 5ns?

**Đáp án:** `2ns` mỗi phần, nhân hai = `4ns`. Dư `1ns` cần được phân phối nếu hợp đồng đòi bảo toàn tổng.

### Bài 4 — Thương nguyên

Có 95 phút, mỗi slot 30 phút. `dividedBy(Duration.ofMinutes(30))` bằng bao nhiêu?

**Đáp án:** 3 slot **trọn vẹn** và 5 phút còn lại. Nếu tính phí slot dở dang, cần quy tắc ceil theo số slot, không thể suy 3 là đáp án thu phí cuối cùng.

### Bài 5 — Cộng Period

`Period.of(1,14,3).plus(Period.ofMonths(2))` ra gì? Nếu normalized thì sao?

**Đáp án:** `P1Y16M3D` trước normalize; `P2Y4M3D` sau normalize. `normalized()` không thay đổi 3 ngày.

### Bài 6 — Nhân Period

`Period.ofMonths(6).multipliedBy(3)` trả gì? Có tự thành một năm sáu tháng không?

**Đáp án:** `P18M`. Nếu gọi `normalized()` thì `P1Y6M`.

### Bài 7 — Tháng cuối tháng

Từ 31/01/2024, tại sao `plusMonths(2)` khác `plusMonths(1).plusMonths(1)`?

**Đáp án:** Thao tác đầu ra 31/03, thao tác hai lượt phải qua 29/02 rồi 29/03. Domain cần xác định dùng ngày neo hay tiếp nối từng kỳ.

### Bài 8 — Ngày DST

Ở New York, 09/03/2024 trưa, cộng `Period.ofDays(1)` và `Duration.ofDays(1)` có cùng ngày giờ không?

**Đáp án:** Không. Period ra 10/03 lúc 12:00 (-04:00); Duration ra 10/03 lúc 13:00 (-04:00). Một bên trôi qua 23 giờ thực, một bên 24 giờ.

### Bài 9 — Ngày sinh

Có thể tính tuổi theo năm bằng cách chia số giây giữa hai `Instant` cho số giây của 365 ngày không?

**Đáp án:** Không đủ đúng: năm nhuận, múi giờ và lịch ngày sinh làm cách đó sai. Dùng `LocalDate` và `Period.between(birthDate, todayInZone)`.

### Bài 10 — Java phiên bản

Một thư viện phải hỗ trợ Java 8 nhưng muốn gọi `Duration.dividedBy(Duration.ofMinutes(30))`. Có biên dịch `--release 8` được không?

**Đáp án:** Không. Overload này được bổ sung từ Java 9. Phải chọn phép tính thay thế có kiểm soát overflow/precision hoặc tăng JDK mục tiêu.

### Bài 11 — Ngoại lệ

Cần xử lý gì với divisor bằng 0, Period years vượt `Integer.MAX_VALUE` và Duration vượt miền seconds?

**Đáp án:** Bắt/validate theo từng ngữ cảnh; các phép có thể ném `ArithmeticException`. Không tự biến lỗi input thành số 0 mà không có hợp đồng sản phẩm.

### Bài 12 — Kết quả chia bị âm

Một Duration âm chia cho Duration dương bằng số lần trọn vẹn thì phần thương được làm tròn về đâu?

**Đáp án:** `Duration.dividedBy(Duration)` làm tròn **về 0**. Bài toán liên quan ceil/floor theo âm cần tự định nghĩa quy tắc và triển khai phù hợp, không tự giả định chia nguyên luôn là floor toán học.

## 21. Checklist trước khi đưa phép toán thời gian vào production

- [ ] Đơn vị thời gian là **giây thực** hay **đơn vị lịch**?
- [ ] Sử dụng `Duration` cho thời lượng thực và `Period` cho year/month/day calendar?
- [ ] Đã xác định mốc bắt đầu, zone và policy cuối tháng nếu dùng Period?
- [ ] Có phân biệt `Duration.dividedBy(long)` với `Duration.dividedBy(Duration)`?
- [ ] Target JDK có hỗ trợ overload cần dùng (dividedBy(Duration) từ Java 9)?
- [ ] Hệ số nhân/chia có thể bằng 0 hoặc âm? Đã quy định chính sách?
- [ ] Có tràn `long` của Duration hoặc `int` của Period không?
- [ ] Precision millisecond/microsecond/nanosecond và cách xử lý remainder có rõ?
- [ ] Khi chia slot, có cần số slot trọn vẹn hay làm tròn lên để tính phí?
- [ ] `Period.normalized()` chỉ xử lý năm/tháng — có ai nhầm là đổi ngày thành tháng?
- [ ] Cuối tháng và năm nhuận có được test (`28,29,30,31`)?
- [ ] Gia hạn từng kỳ hay lấy ngày neo gốc? Có được mô tả trong domain?
- [ ] Qua DST, nghiệp vụ muốn giữ **24 giờ thực** hay giữ **giờ địa phương hôm sau**?
- [ ] Với lịch lặp, đã lưu quy tắc calendar và IANA `ZoneId`?
- [ ] Hai `Instant` có được so trực tiếp khi tính SLA, TTL, deadline?
- [ ] Khi hiển thị phút/giờ nguyên, cách làm tròn có được kiểm thử?
- [ ] Format API/DB ghi rõ đơn vị và semantics Duration/Period?
- [ ] Trong unit test đã dùng ngày/zone cố định thay vì default system time?
- [ ] Có trường hợp kiểm thử Duration rất nhỏ, số âm, 0, overflow, divide-by-zero?
- [ ] Tính thời gian trôi qua thực tế có dùng nguồn đo monotonic phù hợp?

**Tóm lại:** `Duration` hỗ trợ cộng, trừ, nhân và chia theo thời lượng thực có độ phân giải nano giây; `Period` hỗ trợ cộng, trừ, nhân các thành phần lịch và chuẩn hóa năm/tháng, nhưng **không có phép chia tổng quát**. Viết rõ hợp đồng về đơn vị, mốc, timezone, độ chính xác, hướng làm tròn, phần dư và ngoại lệ thì cùng một phép cộng/trừ/nhân/chia mới cho kết quả đúng với nghiệp vụ.

### Tài liệu API chính thức còn được hỗ trợ

- [`Duration` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html): `plus`, `minus`, `multipliedBy`, `dividedBy(long)`, `dividedBy(Duration)` (Java 9+), độ phân giải nano giây và overflow.
- [`Period` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Period.html): tính toán year/month/day, `multipliedBy`, `normalized` và `toTotalMonths`.
- [`ZonedDateTime` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html): phép cộng theo timeline/local calendar và quy tắc DST.
- [`Instant` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html): sự kiện trên timeline và cộng/trừ Duration.
- [`TemporalAmount` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/TemporalAmount.html): hợp đồng lượng thời gian có thể áp dụng cho một Temporal.
- [`ChronoUnit` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/ChronoUnit.html): đơn vị thời gian có độ dài xác định và đơn vị lịch ước lượng.