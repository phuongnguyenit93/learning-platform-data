# Cắt bớt độ chính xác khác với làm tròn thời gian trong Java

Khi timestamp cần lưu ở độ phân giải thấp hơn giá trị đang có, chẳng hạn từ nano giây xuống mili giây, có hai cách phổ biến: **cắt bỏ phần nhỏ hơn độ phân giải đích (truncation)** và **làm tròn về giá trị gần nhất (rounding)**. Hai cách này không giống nhau. Nếu cơ sở dữ liệu chỉ lưu mili giây, trong khi ứng dụng gửi nano giây, lựa chọn cắt hay làm tròn có thể khiến thời điểm lệch gần một mili giây; với dữ liệu trước epoch, sai lầm về quy tắc còn dễ gây lỗi một phía.

Trong Java, `Instant.truncatedTo(ChronoUnit.MILLIS)` cắt bỏ phần nhỏ hơn mili giây; nó **không tự làm tròn**. API `java.time` không cung cấp một phương thức `Instant.roundToMillis()` tổng quát, nên ứng dụng cần lựa chọn và triển khai chính sách làm tròn phù hợp với yêu cầu nghiệp vụ.

## 1. Độ phân giải và độ chính xác là gì?

- **Độ phân giải (resolution):** bước nhỏ nhất mà định dạng hoặc hệ thống lưu trữ có thể biểu diễn, ví dụ 1 giây, 1 mili giây hoặc 1 micro giây.
- **Độ chính xác (precision):** số chữ số thập phân của phần giây được lưu hoặc đo. `Instant` biểu diễn đến nano giây.
- **Độ chính xác đo lường (accuracy):** mức độ gần với thời điểm thực mà nguồn đồng hồ đo được. Một timestamp có 9 chữ số nano giây không chứng minh đồng hồ thực sự chính xác đến nano giây.

Ví dụ, `2026-10-24T10:15:30.123789456Z` có độ phân giải biểu diễn nano giây. Nếu hệ thống đích chỉ lưu mili giây, ta phải chọn một chính sách để quy về bước `0.001` giây.

| Input | Độ phân giải đích | Cắt bớt | Làm tròn gần nhất |
| --- | --- | --- | --- |
| `10:15:30.123100Z` | 1 ms | `10:15:30.123Z` | `10:15:30.123Z` |
| `10:15:30.123500Z` | 1 ms | `10:15:30.123Z` | `10:15:30.124Z` theo chính sách tie về phía sau |
| `10:15:30.123789Z` | 1 ms | `10:15:30.123Z` | `10:15:30.124Z` |
| `10:15:30.999900Z` | 1 ms | `10:15:30.999Z` | `10:15:31.000Z` |

Làm tròn có thể **đẩy timestamp sang giây, ngày hoặc tháng kế tiếp**, vì bước làm tròn đi tới ranh giới đích. Cắt bớt thì giữ phần nguyên của đơn vị đích theo mốc thời gian mà kiểu API sử dụng, nhưng cũng cần hiểu rõ cách xử lý với instant âm.

## 2. Cắt bớt bằng `truncatedTo()`

`Instant.truncatedTo(TemporalUnit)` trả về một instant mới được cắt xuống đơn vị được chọn. Các đơn vị thường dùng gồm `ChronoUnit.SECONDS`, `MILLIS`, `MICROS`, `MINUTES` hoặc `HOURS`; đơn vị phải được hỗ trợ bởi `Instant`.

```java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

Instant value = Instant.parse("2026-10-24T10:15:30.123789456Z");

System.out.println(value.truncatedTo(ChronoUnit.SECONDS));
// 2026-10-24T10:15:30Z

System.out.println(value.truncatedTo(ChronoUnit.MILLIS));
// 2026-10-24T10:15:30.123Z

System.out.println(value.truncatedTo(ChronoUnit.MICROS));
// 2026-10-24T10:15:30.123789Z

System.out.println(value.truncatedTo(ChronoUnit.MINUTES));
// 2026-10-24T10:15:00Z
```

`truncatedTo` **không sửa** đối tượng ban đầu. Hãy lưu giá trị trả về nếu muốn sử dụng timestamp đã được giảm độ phân giải:

```java
Instant original = Instant.parse("2026-10-24T10:15:30.123789456Z");
original.truncatedTo(ChronoUnit.MILLIS); // Bỏ qua kết quả
System.out.println(original);
// 2026-10-24T10:15:30.123789456Z
```

Nếu cần giữ lại mili giây trong biến mới, dùng `Instant millis = original.truncatedTo(ChronoUnit.MILLIS);`.

### Cắt bớt trong `LocalTime` và kiểu địa phương

`LocalTime` và `LocalDateTime` cũng hỗ trợ `truncatedTo`:

```java
LocalTime time = LocalTime.of(10, 15, 30, 987_654_321);
System.out.println(time.truncatedTo(ChronoUnit.SECONDS));
// 10:15:30

LocalDateTime local = LocalDateTime.of(2026, 10, 24, 10, 15, 30, 987_654_321);
System.out.println(local.truncatedTo(ChronoUnit.MILLIS));
// 2026-10-24T10:15:30.987
```

Cắt bớt `LocalDateTime` chỉ điều chỉnh các trường ngày giờ địa phương; nó không tự thêm offset hoặc vùng. Nếu sau này gắn nó vào vùng có DST, cần phân giải quy tắc vùng riêng.

`ZonedDateTime.truncatedTo` cũng hoạt động trên các đơn vị được hỗ trợ, nhưng khi làm tròn/cắt các đơn vị lịch quanh DST, phải xác định rõ ngữ nghĩa mong muốn. Ví dụ `DAYS` trên vùng là ngày địa phương, có thể dài 23 hoặc 25 giờ theo instant. Đối với timestamp tuyệt đối cần cắt về bội số mili giây/giây, thao tác trực tiếp trên `Instant` thường thể hiện ý định rõ hơn.

## 3. Cắt bớt không phải là chia số rồi làm tròn

Một nhầm lẫn phổ biến là nghĩ `truncatedTo` giống một hàm toán học “bỏ chữ số cuối” mà không cần xét timeline. Với `Instant`, giây epoch và phần nano được biểu diễn theo cách chuẩn hóa: `epochSecond` là giây nguyên theo epoch, `nano` nằm trong khoảng 0–999.999.999.

Xét các mốc gần epoch:

| Instant | `getEpochSecond()` | `getNano()` | Cắt xuống mili giây |
| --- | ---: | ---: | --- |
| `1970-01-01T00:00:00.0009Z` | 0 | 900000 | `1970-01-01T00:00:00Z` |
| `1969-12-31T23:59:59.9999Z` | -1 | 999900000 | `1969-12-31T23:59:59.999Z` |
| `1969-12-31T23:59:59.5004Z` | -1 | 500400000 | `1969-12-31T23:59:59.500Z` |
| `1969-12-31T23:59:59.9990Z` | -1 | 999000000 | `1969-12-31T23:59:59.999Z` |

Với instant âm, `getEpochSecond()` có thể là `-1` trong khi `getNano()` gần một tỷ. Ví dụ `1969-12-31T23:59:59.9999Z` chính là **0.1 mili giây trước epoch**. Cắt xuống độ phân giải mili giây theo ranh giới timeline cho `...59.999Z`, tức -1 ms so với epoch. Không chia `getNano()` độc lập rồi quên phần giây âm; cũng không dùng `Math.abs` để xử lý timestamp.

## 4. Làm tròn là gì và vì sao cần chính sách?

Làm tròn quy giá trị về điểm lưới gần nhất của độ phân giải đích. Nhưng khi một giá trị nằm **chính xác giữa hai điểm**, có nhiều quy tắc hợp lệ:

| Quy tắc | Khi đúng điểm giữa | Ví dụ số học |
| --- | --- | --- |
| Half-up trên trục thời gian | Chọn điểm phía sau (instant lớn hơn) | 1.5 → 2; -1.5 theo timeline → -1 |
| Half-away-from-zero | Đi xa số 0 | 1.5 → 2; -1.5 → -2 |
| Half-even (banker's rounding) | Chọn điểm có chữ số cuối chẵn | 2.5 → 2; 3.5 → 4 |
| Toward zero | Gần về số 0 | 1.9 → 1; -1.9 → -1 |
| Floor | Chọn bội không lớn hơn input | -1.2 → -2 |
| Ceiling | Chọn bội không nhỏ hơn input | -1.2 → -1 |

Đối với timestamp, “phía sau” nên được định nghĩa trên **trục thời gian**, nghĩa là instant muộn hơn, chứ không phải phía dương/âm của số. Hai chính sách half-up và half-away-from-zero khác nhau ở thời gian âm: half-up theo timeline đưa đúng điểm giữa về phía thời điểm muộn hơn; half-away-from-zero đưa thời gian âm ra xa epoch.

Vì thế, trước khi viết helper làm tròn, hãy chốt:

- Đơn vị đích: giây, mili giây hay micro giây?
- Điểm giữa: đi về phía instant muộn hơn, phía sớm hơn, về số 0 hay chọn chẵn?
- Có xử lý timestamp trước epoch không?
- Có overflow ở biên phạm vi không?
- Dữ liệu chuẩn hóa có cần giống nhau giữa Java, database và các ngôn ngữ khác không?

## 5. Làm tròn `Instant` về mili giây: half-up trên timeline

Một cách đơn giản để làm tròn tới mili giây và chọn điểm **muộn hơn** nếu chính xác ở nửa mili giây là cộng nửa bước (500.000 nano giây), sau đó cắt xuống mili giây:

```java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

static Instant roundToMillisHalfUpTimeline(Instant value) {
    return value.plusNanos(500_000L)
            .truncatedTo(ChronoUnit.MILLIS);
}
```

Hàm này cần đặt trong lớp Java; code fence là đoạn phương thức, không phải chương trình độc lập. Hàm áp dụng quy tắc “nửa bước trở lên chọn điểm kế tiếp” trên **trục timeline**, bao gồm thời điểm âm. Một vài ví dụ:

| Input | Cắt bằng `truncatedTo(MILLIS)` | Half-up trên timeline |
| --- | --- | --- |
| `1970-01-01T00:00:00.0004Z` | `...00.000Z` | `...00.000Z` |
| `1970-01-01T00:00:00.0005Z` | `...00.000Z` | `...00.001Z` |
| `1970-01-01T00:00:00.0006Z` | `...00.000Z` | `...00.001Z` |
| `1969-12-31T23:59:59.9994Z` | `...59.999Z` | `...59.999Z` |
| `1969-12-31T23:59:59.9995Z` | `...59.999Z` | `1970-01-01T00:00:00Z` |
| `1969-12-31T23:59:59.9996Z` | `...59.999Z` | `1970-01-01T00:00:00Z` |

Cộng 500.000 nano giây với một timestamp âm cũng hoạt động bởi `Instant` chuẩn hóa giây và nano theo timeline. **Đây là half-up theo phía instant muộn hơn**, không phải half-away-from-zero cho số âm. Đồng thời, phép cộng có thể ném `DateTimeException` nếu input đã ở quá sát `Instant.MAX`; hệ thống cần quy tắc rõ cho trường hợp biên.

### Vì sao không dùng `Math.round(value.toEpochMilli())`?

`toEpochMilli()` đã bỏ phần dưới mili giây trước khi gọi `Math.round`. Thông tin cần để làm tròn đã mất, nên `Math.round` không thể khôi phục lại. Ví dụ hai instant `.1231Z` và `.1239Z` đều có thể trở về cùng epoch millisecond sau `toEpochMilli()`, dù một số chính sách có thể đưa giá trị thứ hai lên mili giây kế tiếp.

Hãy làm tròn trên `Instant` gốc trước khi chuyển sang đơn vị lưu trữ thấp hơn; đừng chuyển thành `long` mili giây trước, rồi mong làm tròn được phần nano ban đầu.

## 6. Làm tròn đến micro giây và giây

Ý tưởng cộng nửa bước rồi cắt có thể áp dụng cho một số đơn vị cố định khác được `Instant.truncatedTo` hỗ trợ:

```java
static Instant roundToMicrosHalfUpTimeline(Instant value) {
    return value.plusNanos(500L)
            .truncatedTo(ChronoUnit.MICROS);
}

static Instant roundToSecondsHalfUpTimeline(Instant value) {
    return value.plusNanos(500_000_000L)
            .truncatedTo(ChronoUnit.SECONDS);
}
```

- Micro giây có bước 1.000 nano giây, nên nửa bước là 500 ns.
- Một giây có nửa bước 500.000.000 ns.
- Mili giây có bước 1.000.000 ns, nên nửa bước là 500.000 ns.

Các hàm trên dùng cùng một chính sách **half-up theo trục instant**, với trường hợp exact tie đi về instant muộn hơn. Không áp dụng máy móc công thức này cho mọi đơn vị lịch như tháng, năm hay ngày trong `ZonedDateTime`. Một ngày địa phương qua DST không nhất thiết là 86.400 giây; “làm tròn tới ngày lịch” cần một chính sách lịch riêng.

Ngoài ra, `plusNanos` có giới hạn phạm vi tương tự mọi phép toán trên `Instant`. Nếu xử lý các instant cực đại, hãy xác định cách báo lỗi hoặc dùng thuật toán có kiểm tra biên.

## 7. Làm tròn tới mili giây theo `long` epoch: cẩn thận với số âm

Một số hệ thống lưu timestamp dưới dạng số `long` mili giây kể từ epoch. Nếu vẫn đang ở **đơn vị mili giây** và chỉ cần quy số nguyên đó thành bội của 10 ms hoặc 1.000 ms, phải chọn quy tắc số học rõ ràng. Không trộn đơn vị nano với mili.

Ví dụ, nếu input là `epochMillis` và muốn làm tròn tới 100 ms theo half-up hướng dương thông thường, có thể tách thương và dư bằng `floorDiv`/`floorMod` theo bước dương để xử lý số âm đúng theo timeline:

```java
static long roundMillisTo100msHalfUpTimeline(long epochMillis) {
    long step = 100L;
    long lower = Math.floorDiv(epochMillis, step) * step;
    long remainder = Math.floorMod(epochMillis, step);
    return remainder < step / 2 ? lower : lower + step;
}
```

Đây là helper cho **bội 100 mili giây**. Tại đúng điểm giữa, nó chọn bội muộn hơn. Tuy nhiên, `lower + step` có thể overflow khi input gần `Long.MAX_VALUE`; mã production cần kiểm tra biên bằng `Math.addExact` hoặc chính sách overflow cụ thể.

Ví dụ: `epochMillis = -1` nằm giữa `-100` và `0`, gần 0 hơn nên trả 0; `epochMillis = -50` đúng điểm giữa nên cũng trả 0 theo quy tắc tie đi về phía timeline muộn hơn. Một phép tính kiểu `(epochMillis + step / 2) / step * step` có thể sai vì phép chia số nguyên của Java làm tròn về 0 và cộng/trừ gần biên có thể tràn số.

Nếu dữ liệu bắt đầu là `Instant` với độ phân giải nano, nên ưu tiên làm tròn trực tiếp trên `Instant` gốc. Helper số nguyên trên chỉ phù hợp khi bạn biết input đã là epoch milliseconds và quy tắc đầu ra cũng là mili giây.

## 8. Cắt bớt có giống `toEpochMilli()` không?

`Instant.toEpochMilli()` trả `long` mili giây từ epoch và **loại bỏ độ chính xác nhỏ hơn mili giây**. Với instant chuẩn, hành vi này gắn với millisecond timeline và xử lý phần âm; không được tự thay bằng phép tính `epochSecond * 1000 + nano / 1_000_000` mà không chứng minh cách xử lý số âm và overflow.

```java
Instant precise = Instant.parse("1969-12-31T23:59:59.999999999Z");
System.out.println(precise.truncatedTo(ChronoUnit.MILLIS));
// 1969-12-31T23:59:59.999Z
System.out.println(precise.toEpochMilli());
// -1
```

`toEpochMilli()` không trả timestamp dạng double hay float; nó trả số nguyên `long`. Các instant có nano khác nhau nhưng cùng mili giây có thể cho cùng kết quả `toEpochMilli()`, vì vậy **đây là chuyển đổi mất độ phân giải**.

Nếu hệ thống cần phân biệt chính xác sự kiện nằm trước/sau ranh giới mili giây, giữ `Instant` hoặc một cặp giây/nano. Nếu schema đích cố ý lưu milli giây, việc mất phần nano cần được coi là một quyết định chính sách chứ không phải tác dụng phụ vô tình.

## 9. Hãy xác định nơi áp dụng precision reduction

Giảm độ phân giải ở các tầng khác nhau có thể cho kết quả không nhất quán:

- **Định dạng để hiển thị:** chỉ cần văn bản dễ đọc, có thể hiển thị 3 chữ số mili giây mà không thay đổi instant nội bộ. Không nên làm tròn giá trị cốt lõi chỉ vì UI hiển thị ít chữ số.
- **Lưu cơ sở dữ liệu:** kiểm tra kiểu timestamp và độ phân giải của cột/driver. Một số driver hoặc database tự cắt/làm tròn; cần test bằng cách ghi và đọc lại giá trị biên.
- **Giao tiếp API:** quy định ISO instant bao nhiêu chữ số thập phân hoặc quy tắc số epoch là ms/µs/ns. Hai bên cần thống nhất tie policy nếu round.
- **So sánh/deduplicate:** làm tròn/cắt trước rồi so sánh có thể khiến hai sự kiện khác nhau trở thành cùng timestamp. Nếu uniqueness có ý nghĩa nghiệp vụ, dùng event ID riêng thay vì chỉ dựa vào thời điểm.
- **Đo thời lượng:** precision của timestamp wall-clock không giống độ chính xác đo. Với elapsed-time trong một tiến trình, cân nhắc `System.nanoTime()` thay vì làm tròn `Instant.now()`.

**Đặc biệt:** không nên làm tròn chỉ ở phía đọc mà cắt ở phía ghi nếu kết quả so sánh hoặc chữ ký dữ liệu cần thống nhất. Chọn một canonicalization policy tại biên hệ thống, ghi rõ và áp dụng đồng nhất.

## 10. Chương trình Java 17+ chạy độc lập

Tạo file **`PrecisionReductionDemo.java`**:

```java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

public class PrecisionReductionDemo {
    static Instant truncateMillis(Instant value) {
        return value.truncatedTo(ChronoUnit.MILLIS);
    }

    static Instant roundMillisHalfUpTimeline(Instant value) {
        return value.plusNanos(500_000L)
                .truncatedTo(ChronoUnit.MILLIS);
    }

    static Instant roundMicrosHalfUpTimeline(Instant value) {
        return value.plusNanos(500L)
                .truncatedTo(ChronoUnit.MICROS);
    }

    public static void main(String[] args) {
        Instant[] samples = {
                Instant.parse("2026-10-24T10:15:30.123100Z"),
                Instant.parse("2026-10-24T10:15:30.123500Z"),
                Instant.parse("2026-10-24T10:15:30.123789Z"),
                Instant.parse("1969-12-31T23:59:59.999400Z"),
                Instant.parse("1969-12-31T23:59:59.999500Z"),
                Instant.parse("1969-12-31T23:59:59.999600Z")
        };

        for (Instant input : samples) {
            System.out.println("input = " + input);
            System.out.println("  trunc ms = " + truncateMillis(input));
            System.out.println("  round ms = "
                    + roundMillisHalfUpTimeline(input));
        }

        Instant value = Instant.parse("2026-10-24T10:15:30.123789456Z");
        System.out.println("trunc micros = "
                + value.truncatedTo(ChronoUnit.MICROS));
        System.out.println("round micros = "
                + roundMicrosHalfUpTimeline(value));
        System.out.println("original = " + value);
    }
}
```

Biên dịch và chạy:

```bash
javac PrecisionReductionDemo.java
java PrecisionReductionDemo
```

Đầu ra dự kiến:

```text
input = 2026-10-24T10:15:30.123100Z
  trunc ms = 2026-10-24T10:15:30.123Z
  round ms = 2026-10-24T10:15:30.123Z
input = 2026-10-24T10:15:30.123500Z
  trunc ms = 2026-10-24T10:15:30.123Z
  round ms = 2026-10-24T10:15:30.124Z
input = 2026-10-24T10:15:30.123789Z
  trunc ms = 2026-10-24T10:15:30.123Z
  round ms = 2026-10-24T10:15:30.124Z
input = 2026-10-24T10:15:30.999400Z
  trunc ms = 2026-10-24T10:15:30.999Z
  round ms = 2026-10-24T10:15:30.999Z
input = 2026-10-24T10:15:30.999500Z
  trunc ms = 2026-10-24T10:15:30.999Z
  round ms = 2026-10-24T10:15:31Z
input = 2026-10-24T10:15:30.999600Z
  trunc ms = 2026-10-24T10:15:30.999Z
  round ms = 2026-10-24T10:15:31Z
trunc micros = 2026-10-24T10:15:30.123789Z
round micros = 2026-10-24T10:15:30.123789Z
original = 2026-10-24T10:15:30.123789456Z
```

Các dòng cuối cho thấy cắt về micro giây và làm tròn micro giây có thể trùng nhau khi phần dư nhỏ hơn nửa bước; ở các giá trị khác, hai kết quả sẽ khác. `original` vẫn giữ nguyên nano giây vì `Instant` bất biến.

## 11. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách đúng |
| --- | --- | --- |
| Gọi `truncatedTo(MILLIS)` và kỳ vọng nó làm tròn | Luôn bỏ phần nhỏ hơn mili giây | Dùng quy tắc làm tròn tường minh nếu cần điểm gần nhất |
| Gọi `toEpochMilli()` trước khi làm tròn | Nano đã mất, không thể khôi phục | Làm tròn `Instant` gốc trước |
| Dùng chia nguyên cho timestamp âm mà không xét quy tắc | Có thể lệch một bước gần epoch | Dùng API `Instant` hoặc `floorDiv`/`floorMod` với đơn vị xác định |
| Làm tròn số nano đã bị chuyển thành `long` mili | Thông tin dưới mili giây đã biến mất | Giữ độ phân giải nguồn đến khi áp dụng chính sách |
| Cho rằng mọi hệ thống dùng cùng quy tắc tie | Java, database, ngôn ngữ và cấu hình có thể khác nhau | Ghi rõ half-up, half-even, floor, truncation... trong hợp đồng |
| Dùng double để lưu epoch nano | Mất chính xác số nguyên lớn | Dùng kiểu nguyên thích hợp, cặp seconds+nanos hoặc chuỗi |
| Làm tròn mỗi lần tính trung gian | Sai số tích lũy qua các bước | Giữ giá trị chính xác và chỉ giảm độ phân giải tại biên đã chọn |
| Chỉ so timestamp sau làm tròn để loại trùng | Hai sự kiện sát nhau có thể thành một mốc | Dùng ID sự kiện và quy tắc dedup riêng |
| Áp phép cộng nửa bước mà không xét overflow | Giá trị cực đại có thể ném ngoại lệ | Validate phạm vi và xác định cách xử lý biên |
| Nhầm độ phân giải nano với độ chính xác đo | Tin timestamp chính xác hơn nguồn thực | Tách precision của kiểu khỏi accuracy của clock |

## 12. Checklist lựa chọn chính sách

1. **Xác định đơn vị đích:** 1 s, 1 ms, 1 µs hay một đơn vị khác.
2. **Chọn phép biến đổi:** truncation/floor hay rounding về gần nhất.
3. **Chốt cách xử lý điểm giữa:** half-up theo timeline, half-even hay half-away-from-zero.
4. **Kiểm tra timestamp âm:** thêm test trước epoch, gồm ngay dưới, đúng tại và ngay trên các nửa bước.
5. **Kiểm tra carry:** phần làm tròn có thể chuyển qua giây/ngày mới.
6. **Kiểm tra giới hạn:** `Instant.MIN/MAX`, overflow của epoch long và cơ sở dữ liệu.
7. **Định nghĩa nơi chuẩn hóa:** API, ứng dụng, driver hay database; tránh nhiều tầng thực hiện các chính sách khác nhau.
8. **Giữ dữ liệu gốc khi cần audit:** nếu độ phân giải bị loại bỏ có ý nghĩa, lưu giá trị ban đầu cùng giá trị chuẩn hóa hoặc metadata của chính sách.

### Câu hỏi tự kiểm tra

**1.** `Instant.parse("2026-10-24T10:15:30.123789Z").truncatedTo(MILLIS)` trả gì?  
→ `2026-10-24T10:15:30.123Z`, vì nó cắt bỏ phần nano thấp hơn mili giây.

**2.** Theo helper half-up trên timeline, `.123500Z` làm tròn tới mili giây nào?  
→ `.124Z`, vì đó là đúng nửa mili giây và chính sách chọn instant muộn hơn.

**3.** Vì sao `Math.round(instant.toEpochMilli())` không làm tròn nano giây ban đầu?  
→ `toEpochMilli()` đã bỏ phần dưới mili giây trước khi `Math.round` được gọi.

**4.** `Instant` trước epoch có `getEpochSecond()` âm nhưng `getNano()` dương có hợp lệ không?  
→ Có; nano được chuẩn hóa từ 0 đến 999.999.999.

**5.** Có nên áp dụng cộng nửa bước rồi cắt trực tiếp cho “làm tròn một ngày địa phương” trên mọi `ZonedDateTime` không?  
→ Không; ngày địa phương có thể 23/25 giờ quanh DST. Làm tròn ngày lịch cần quy tắc lịch riêng.

**6.** Nếu cột DB chỉ lưu mili giây, ứng dụng có thể mặc định bỏ nano mà không cần thỏa thuận?  
→ Nên xác định và kiểm thử chính sách chuẩn hóa ở ranh giới lưu/đọc, vì driver hoặc DB có thể cắt/làm tròn khác nhau.

### Tài liệu API chính thức

- [Java SE 17 — `Instant`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): cấu trúc giây+nano, `truncatedTo`, `toEpochMilli`, `plusNanos`.
- [Java SE 17 — `ChronoUnit`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/ChronoUnit.html): đơn vị mili giây, micro giây, giây và các đơn vị thời gian được hỗ trợ.
- [Java SE 17 — `LocalTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalTime.html): cắt các trường giờ địa phương.
- [Java SE 17 — `ZonedDateTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html): phép toán địa phương và quy tắc vùng/DST.

**Ghi nhớ:** `truncatedTo` cắt bỏ phần nhỏ hơn đơn vị, còn rounding chọn bội gần nhất theo một chính sách cụ thể. Giữ `Instant` đầy đủ cho tới khi biết nơi lưu trữ yêu cầu độ phân giải nào; xác định chính sách điểm giữa, kiểm thử timestamp âm và thống nhất quy tắc giữa mọi hệ thống.
