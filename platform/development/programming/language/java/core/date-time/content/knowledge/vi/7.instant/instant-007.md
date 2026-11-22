# Instant — Độ chính xác nano giây và mất dữ liệu khi chuyển sang mili giây

## 1. Vấn đề cần giải quyết

`java.time.Instant` biểu diễn **một thời điểm trên dòng thời gian** với độ phân giải đến **1 nano giây** (ns, 10⁻⁹ giây). Trong khi đó, `toEpochMilli()`, `java.util.Date` và nhiều giao thức hoặc cột CSDL chỉ biểu diễn thời điểm tới **mili giây** (ms, 10⁻³ giây). Vì `1 ms = 1.000.000 ns`, khi giảm độ phân giải từ nano xuống mili sẽ không thể giữ mọi thông tin ban đầu.

Ví dụ trực quan:

~~~text
Instant gốc:           1970-01-01T00:00:01.234567890Z
Instant.toEpochMilli:  1234
Khôi phục từ millis:   1970-01-01T00:00:01.234Z
Phần mất:              567890 nano giây
~~~

Bài học giúp bạn xác định rõ **giá trị nào được giữ**, **giá trị nào mất** và **quy tắc xử lý thời điểm trước năm 1970**. Đây là khác biệt quan trọng giữa độ phân giải **biểu diễn** của Java và độ chính xác **thực tế** của đồng hồ, giao thức, cơ sở dữ liệu.

## 2. Mô hình giây và nano của Instant

Một `Instant` lưu khái niệm hai thành phần:

| Thuộc tính | Kiểu | Ý nghĩa |
|---|---|---|
| `getEpochSecond()` | `long` | Giây nguyên từ mốc `1970-01-01T00:00:00Z`, có thể âm |
| `getNano()` | `int` | Phần nano trong giây, luôn từ `0` đến `999_999_999` |

Từ epoch, mỗi giây có 1.000.000.000 nano. Chẳng hạn:

~~~java
Instant value = Instant.ofEpochSecond(1, 234_567_890);
System.out.println(value);
System.out.println(value.getEpochSecond());
System.out.println(value.getNano());
~~~

Stdout:

~~~text
1970-01-01T00:00:01.234567890Z
1
234567890
~~~

`getNano()` là nano **trong một giây**, không phải tổng nano từ epoch. `toEpochMilli()` là số mili **tính từ epoch**, có thể mất phần nano dưới mili giây.

Một số đơn vị cần nhớ:

| Đơn vị | Số nano |
|---|---:|
| 1 giây | 1.000.000.000 |
| 1 mili giây | 1.000.000 |
| 1 micro giây | 1.000 |
| 1 nano giây | 1 |

Đừng truyền milli giây trực tiếp vào tham số nano của `ofEpochSecond(seconds, nanoAdjustment)`. Ví dụ `123 ms` tương ứng `123_000_000 ns`, không phải `123 ns`.

### 2.1. Mốc thời gian và múi giờ

`Instant.EPOCH` là thời điểm `1970-01-01T00:00:00Z`, còn chữ `Z` đánh dấu offset UTC bằng 0. `Instant` không chứa múi giờ vùng hay giờ địa phương. `instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))` chỉ chuyển cùng thời điểm sang biểu diễn theo giờ Việt Nam; nếu không qua API giảm precision, nano giây vẫn được bảo toàn.

`Instant.ofEpochSecond(1)` có nghĩa sau epoch một **giây**, trong khi `Instant.ofEpochMilli(1)` là sau epoch một **mili giây**. Nhầm đơn vị sẽ tạo timestamp sai theo bội số 1.000.

## 3. Tạo Instant giữ nano giây

~~~java
Instant epoch = Instant.EPOCH;
Instant secondOnly = Instant.ofEpochSecond(1);
Instant withNanos = Instant.ofEpochSecond(1, 234_567_890);
Instant fromMillis = Instant.ofEpochMilli(1_234);
Instant parsed = Instant.parse("2024-02-29T12:34:56.123456789Z");
~~~

Các kết quả:

- `withNanos` là `1970-01-01T00:00:01.234567890Z`.
- `fromMillis` là `1970-01-01T00:00:01.234Z`; nó không thể giữ `567890 ns` ngoài mili.
- `parsed` giữ phần nano `123456789` từ chuỗi ISO có đủ chín chữ số.

`Instant.ofEpochSecond(long seconds, long nanoAdjustment)` có thể nhận số nano lớn hơn một tỷ hoặc giá trị âm và **chuẩn hóa**:

~~~java
Instant normalized = Instant.ofEpochSecond(1, 1_234_567_890);
System.out.println(normalized);
~~~

Stdout:

~~~text
1970-01-01T00:00:02.234567890Z
~~~

Bởi 1.234.567.890 nano = 1 giây và 234.567.890 nano. Kết quả `getNano()` luôn nằm trong `0..999999999`.

Với thời điểm âm một nano so với epoch:

~~~java
Instant before = Instant.ofEpochSecond(0, -1);
System.out.println(before);
System.out.println(before.getEpochSecond());
System.out.println(before.getNano());
~~~

Stdout:

~~~text
1969-12-31T23:59:59.999999999Z
-1
999999999
~~~

**Quan trọng:** Java biểu diễn âm một nano bằng **giây -1 cộng 999.999.999 nano**, chứ không lưu trường nano âm.

### 3.1. Độ phân giải không phải độ chính xác đo thực tế

`Instant.now()` trả một thời điểm từ đồng hồ hệ thống. Mặc dù kết quả có trường nano, độ phân giải và sai số thật của clock phụ thuộc JVM, hệ điều hành, nguồn thời gian. Không thể khẳng định “đo chính xác 1 ns” chỉ vì đối tượng in ra chín chữ số.

Có thể dùng `Clock.fixed(...)` trong test:

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2024-02-29T12:34:56.123456789Z"),
        ZoneOffset.UTC);
Instant stable = Instant.now(fixed);
~~~

`stable` luôn bằng instant đã chỉ định. Cách này giúp kiểm thử độc lập với đồng hồ thực.

## 4. Chuyển sang mili: phần nano bị loại thế nào?

~~~java
Instant source = Instant.ofEpochSecond(1, 234_567_890);
long millis = source.toEpochMilli();
Instant restored = Instant.ofEpochMilli(millis);
~~~

Kết quả: `millis == 1234`, `restored == 1970-01-01T00:00:01.234Z`.

Tính toán:

~~~text
Giây nguyên:          1 * 1000 = 1000 ms
234567890 ns trong s:             234 ms + 567890 ns còn dư
Kết quả epochMillis:  1000 + 234 = 1234 ms
Phần nano mất:        567890 ns
~~~

`toEpochMilli()` **không làm tròn đến mili gần nhất**. `1970-01-01T00:00:01.234999999Z` cũng chuyển thành `1234` ms, không thành `1235` ms.

Gọi `s = getEpochSecond()` và `n = getNano()`, trong miền kết quả còn vừa `long`:

~~~text
epochMillis = s * 1000 + floor(n / 1000000)
~~~

Do `n` không âm, phép chia nguyên `n / 1_000_000` có cùng kết quả `floor`. Nhưng khi tự chuyển đổi **tổng số nano có dấu** thành mili, cần đặc biệt xét phép chia số âm trước epoch.

### 4.1. Điều kiện bảo toàn chính xác

~~~java
boolean noSubMillis =
        source.getNano() % 1_000_000 == 0;
~~~

Nếu `noSubMillis` đúng, và `toEpochMilli()` không overflow, chu trình `Instant.ofEpochMilli(source.toEpochMilli())` giữ nguyên `source`. Nếu sai, phần nano không chia hết một triệu **không có cách biểu diễn chính xác** bằng số mili nguyên.

Sai khác giữa thời điểm gốc và thời điểm tái tạo có thể từ **0 đến 999.999 ns**. Không thể khôi phục phần dư chỉ bằng một số mili đã lưu.

## 5. Bẫy trước Unix epoch: âm một nano thành âm một mili

Thời điểm **1 ns trước** `1970-01-01T00:00:00Z`:

~~~java
Instant negative = Instant.parse(
        "1969-12-31T23:59:59.999999999Z");

System.out.println(negative.toEpochMilli());
System.out.println(Instant.ofEpochMilli(
        negative.toEpochMilli()));
~~~

Stdout:

~~~text
-1
1969-12-31T23:59:59.999Z
~~~

Tại sao chuyển `-1 ns` thành `-1 ms`?

~~~text
Thời điểm tương đối epoch = -0.000001 mili giây
Bội số mili lớn nhất không vượt quá thời điểm gốc = -1 ms
~~~

`toEpochMilli()` tuân theo **làm tròn xuống trên trục thời gian**. Nó không “cắt phần thập phân về 0” theo kiểu chia nguyên của Java.

| Giá trị nguồn so với epoch | `toEpochMilli()` | Khôi phục so với epoch |
|---|---:|---|
| +1.234567890 giây | +1234 | +1.234 giây |
| +0.000000001 giây | 0 | 0 giây |
| -0.000000001 giây | -1 | -0.001 giây |
| -0.001000000 giây | -1 | -0.001 giây |

Nếu tự tính bằng `signedEpochNanos / 1_000_000` trong Java thì `-1 / 1_000_000` cho kết quả `0` (cắt về 0), **khác với `toEpochMilli() == -1`**. Nếu cần chia số nguyên âm theo hướng floor, cân nhắc `Math.floorDiv` và kiểm tra overflow, hoặc ưu tiên gọi thẳng phương thức chuẩn.

Với `negative` ở trên, `getEpochSecond() == -1` và `getNano() == 999999999`. Chính mô hình này đảm bảo công thức `s * 1000 + n / 1000000` cho kết quả -1 ms.

## 6. Chương trình Java 17+ tái hiện cả trường hợp dương và âm

Lưu thành **`InstantPrecisionDemo.java`**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Date;

public class InstantPrecisionDemo {
    public static void main(String[] args) {
        Instant precise = Instant.ofEpochSecond(1, 234_567_890);
        long millis = precise.toEpochMilli();
        Instant restored = Instant.ofEpochMilli(millis);

        System.out.println("Source: " + precise);
        System.out.println("Epoch millis: " + millis);
        System.out.println("Restored: " + restored);
        System.out.println("Lost nanos: "
                + Duration.between(restored, precise).toNanos());
        System.out.println("Equal: " + precise.equals(restored));
        System.out.println("Truncated: "
                + precise.truncatedTo(ChronoUnit.MILLIS));

        Instant negative = Instant.parse(
                "1969-12-31T23:59:59.999999999Z");
        long negativeMillis = negative.toEpochMilli();
        Instant negativeRestored =
                Instant.ofEpochMilli(negativeMillis);

        System.out.println("Negative source: " + negative);
        System.out.println("Negative millis: " + negativeMillis);
        System.out.println("Negative restored: " + negativeRestored);
        System.out.println("Negative lost nanos: "
                + Duration.between(
                        negativeRestored, negative).toNanos());

        System.out.println("Through Date: "
                + Date.from(precise).toInstant());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac InstantPrecisionDemo.java
java InstantPrecisionDemo
~~~

Stdout:

~~~text
Source: 1970-01-01T00:00:01.234567890Z
Epoch millis: 1234
Restored: 1970-01-01T00:00:01.234Z
Lost nanos: 567890
Equal: false
Truncated: 1970-01-01T00:00:01.234Z
Negative source: 1969-12-31T23:59:59.999999999Z
Negative millis: -1
Negative restored: 1969-12-31T23:59:59.999Z
Negative lost nanos: 999999
Through Date: 1970-01-01T00:00:01.234Z
~~~

Giải thích kết quả:

1. `Instant` dương ban đầu có 234.567.890 nano; đổi sang mili chỉ giữ `234.000.000` nano, nên mất `567.890` nano.
2. `truncatedTo(MILLIS)` cho cùng giá trị trong trường hợp này: phương thức chỉ giữ các mốc cách nhau 1 ms.
3. Thời điểm trước epoch âm một nano được chuyển thành âm một mili; phần chênh giữa gốc và bản khôi phục là `999.999` nano.
4. `Date.from(precise).toInstant()` cũng chỉ giữ mili giây, vì `java.util.Date` biểu diễn thời gian bằng epoch milliseconds.

## 7. truncatedTo(MILLIS) và các độ phân giải khác

`Instant.truncatedTo(ChronoUnit.MILLIS)` cắt bớt phần nano dưới một mili giây; nó **không làm tròn gần nhất**.

~~~java
Instant input = Instant.parse(
        "2024-02-29T12:34:56.123456789Z");
Instant micros = input.truncatedTo(ChronoUnit.MICROS);
Instant millis = input.truncatedTo(ChronoUnit.MILLIS);
Instant seconds = input.truncatedTo(ChronoUnit.SECONDS);
~~~

Kết quả:

~~~text
micros  = 2024-02-29T12:34:56.123456Z
millis  = 2024-02-29T12:34:56.123Z
seconds = 2024-02-29T12:34:56Z
~~~

| Độ phân giải đích | Bội số nano còn biểu diễn được | Phần lẻ mất |
|---|---:|---|
| `NANOS` | 1 | Không |
| `MICROS` | 1.000 | Dưới micro |
| `MILLIS` | 1.000.000 | Dưới mili |
| `SECONDS` | 1.000.000.000 | Dưới giây |

`truncatedTo(MILLIS)` ở trước epoch cũng đặt giá trị vào ranh giới mili thấp hơn trong phạm vi giây đó. Trường hợp âm một nano thành âm một mili là ví dụ điển hình.

Một chính sách **làm tròn nearest**, **half-up** hoặc **half-even** sẽ cần một quy tắc khác và có thể cho kết quả khác. Đừng ghi tài liệu rằng `toEpochMilli()` là phương thức làm tròn gần nhất.

## 8. Hai cách round-trip

**Cách không mất nano: cặp giây + nano**

~~~java
Instant original = Instant.parse(
        "2024-02-29T12:34:56.123456789Z");

long seconds = original.getEpochSecond();
int nanos = original.getNano();

Instant exact = Instant.ofEpochSecond(seconds, nanos);
System.out.println(exact.equals(original)); // true
~~~

**Cách có thể mất nano: một số milli nguyên**

~~~java
Instant approximate =
        Instant.ofEpochMilli(original.toEpochMilli());
System.out.println(approximate.equals(original)); // false
~~~

Ở cả hai cách, thời điểm có thể vẫn thuộc cùng giây, nhưng `equals` phải so toàn bộ nano. Tương đương ở cấp mili không đồng nghĩa hai `Instant` bằng nhau.

Để chứng minh khi nào milli round-trip chính xác:

~~~java
Instant millisecondAligned = Instant.parse(
        "2024-02-29T12:34:56.123000000Z");

Instant rebuilt = Instant.ofEpochMilli(
        millisecondAligned.toEpochMilli());

System.out.println(rebuilt.equals(millisecondAligned)); // true
~~~

Điều kiện quyết định là phần nano chia hết 1 triệu. Nếu backend đã mất sáu chữ số cuối, frontend không thể “đoán” để tái tạo timestamp nano cũ.

### 8.1. Vì sao không lưu epochNanos trong long cho mọi ngày?

~~~java
// Có thể overflow long khi xa epoch:
long epochNanos = instant.getEpochSecond() * 1_000_000_000L
        + instant.getNano();
~~~

`long` khoảng ±9,22×10¹⁸, chỉ đủ cho tổng nano từ epoch trải dài xấp xỉ **292 năm** mỗi chiều. Miền `Instant` rộng hơn nhiều nhờ lưu giây và nano riêng. Nếu cần một số epochNanos tuyệt đối cho ngày rất xa, phải dùng `BigInteger` hoặc một dạng lưu trữ có miền tương đương; không ép kiểu rồi chấp nhận giá trị tràn.

## 9. Date, JDBC, JSON và hệ thống lưu trữ

`java.util.Date` lưu mili giây kể từ epoch; qua `Date`, phần dưới mili bị mất:

~~~java
Instant nanos = Instant.parse(
        "2024-02-29T12:34:56.123456789Z");
Date legacy = Date.from(nanos);
Instant back = legacy.toInstant();
// back = 2024-02-29T12:34:56.123Z
~~~

`java.sql.Timestamp` có hỗ trợ phần nano, nhưng khi ghi CSDL còn phụ thuộc precision của cột, JDBC driver, ORM và cấu hình hệ thống. Một cột timestamp có thể chỉ hỗ trợ 3 hoặc 6 chữ số phần giây; một số hệ thống làm tròn, một số cắt, nên không thể khẳng định hành vi chỉ từ tên kiểu SQL.

| Kiểu hoặc đường đi | Khả năng giữ nano |
|---|---|
| `Instant` trực tiếp | Có, đến 1 ns |
| `Instant → epochMillis` | Chỉ chính xác đến 1 ms |
| `Instant → java.util.Date` | Chỉ chính xác đến 1 ms |
| `Instant → seconds + nanos` | Có, nếu cả hai trường nguyên vẹn |
| `Instant → chuỗi ISO có đủ phần lẻ` | Có, nếu serializer/parser giữ nguyên precision |
| `Instant → cột database` | Phụ thuộc DB, column precision, driver, mapping |

**Để biết thực tế có giữ nano hay không, bắt buộc kiểm tra round-trip**:

~~~text
Instant gốc
  → serialize / JDBC binding
  → nơi truyền và nơi lưu
  → parse / JDBC read
  → Instant đọc lại
  → so sánh equals(), getNano()
~~~

Nếu gốc là `.123456789` mà dữ liệu cuối chỉ có `.123456`, đã mất ít nhất ba chữ số nano. Nếu cuối chỉ có `.123`, đã mất sáu chữ số. Đừng giả định tất cả database sẽ cắt: có nơi sẽ làm tròn sang giá trị khác. Chính sách phải được xác minh trên hệ thống triển khai.

## 10. Hợp đồng dữ liệu khi cần precision cao

### 10.1. Chấp nhận milli giây

Nếu nhu cầu chỉ đến mili, có thể truyền số nguyên với tên trường mang đơn vị:

~~~json
{
  "epochMillis": 1234
}
~~~

Người nhận dùng `Instant.ofEpochMilli(1234)`. Hợp đồng nên ghi rõ khả năng mất dữ liệu dưới 1 ms.

Không nên dùng tên mơ hồ như `timestamp: 1234` mà không nói đây là giây, mili, micro hay nano. Cùng con số dưới các đơn vị khác nhau biểu diễn thời điểm rất khác nhau.

### 10.2. Giữ nano giây với ISO text

~~~json
{
  "occurredAt": "2024-02-29T12:34:56.123456789Z"
}
~~~

Người nhận dùng `Instant.parse(...)`. Chuỗi có thể giữ chín chữ số phần giây, miễn serializer, parser và database trung gian cũng giữ đủ precision. `Instant.toString()` có thể dùng 3, 6 hoặc 9 chữ số cần thiết; sự rút gọn các chữ số 0 cuối không có nghĩa giá trị đã bị mất.

### 10.3. Giữ nano giây bằng hai trường

~~~json
{
  "epochSecond": 1,
  "nanoOfSecond": 234567890
}
~~~

Người nhận tạo `Instant.ofEpochSecond(seconds, nanos)`. Đây là hợp đồng số đủ để round-trip nếu giây và nano có đơn vị đúng, giới hạn và kiểu lưu hợp lệ. `nanoOfSecond` phải được hiểu là nano **trong một giây** chứ không phải tổng nano từ epoch.

Nếu dùng kiểu số trong JavaScript hoặc ngôn ngữ có giới hạn độ chính xác số nguyên, cần xét kiểu truyền nhận cụ thể và miền giá trị trước khi dùng epochNanos cực lớn hoặc epochMillis ở biên; đừng mặc định mọi số nguyên `long` đều được biểu diễn chính xác bằng một kiểu số dấu phẩy động.

## 11. Lỗi tràn số khi chuyển mili

`Instant` cho phép miền thời gian rộng hơn miền giá trị `long` mili giây. Do đó `toEpochMilli()` có thể ném `ArithmeticException`:

~~~java
try {
    System.out.println(Instant.MAX.toEpochMilli());
} catch (ArithmeticException ex) {
    System.out.println("out of long millis range");
}
~~~

Stdout:

~~~text
out of long millis range
~~~

Nếu ứng dụng buộc lưu epochMillis, hãy xác định miền ngày có thể lưu. Không tự nhân `getEpochSecond() * 1000` và bỏ qua overflow. Ngược lại, `Instant.ofEpochMilli(long)` biểu diễn được đầu vào mili dạng `long` trong miền `Instant`, nhưng không có nghĩa mọi `Instant` chuyển được sang milli dạng `long`.

Khi chỉ đo **phần nano mất sau milli round-trip**, `Duration.between(restored, original).toNanos()` an toàn vì phần mất nhỏ hơn 1 ms. Khi tính khoảng thời gian rất dài, `Duration.toNanos()` cũng có thể overflow `long`; cần xét miền trước khi chuyển.

## 12. Chính sách chuyển đổi chính xác

Một hệ thống không cho phép mất phần nano dưới mili có thể từ chối conversion:

~~~java
static long toEpochMilliExact(Instant instant) {
    if (instant.getNano() % 1_000_000 != 0) {
        throw new IllegalArgumentException(
                "Instant has sub-millisecond precision");
    }
    return instant.toEpochMilli();
}
~~~

Đây là **phương thức minh họa**, đặt trong một class Java có import `java.time.Instant` để biên dịch. Nó từ chối nguồn có phần nano không thể biểu diễn bằng milli. Nếu instant đã chính xác đến ms nhưng quá xa epoch, `toEpochMilli()` vẫn có thể báo overflow; đó là kiểm tra miền giá trị riêng.

Nếu nghiệp vụ **chủ động chấp nhận giảm precision**, hãy đặt tên rõ ràng và tài liệu hóa chính sách, ví dụ ghi dữ liệu audit ở cấp ms. Không gọi phép giảm precision là “không đổi giá trị” khi thực tế có phần nano dư.

## 13. Không nhầm với System.nanoTime()

`System.nanoTime()` trả số đếm tương đối từ một mốc gốc tùy ý, dùng đo **thời lượng đã trôi qua**. Nó **không phải** nano giây từ Unix epoch.

~~~java
long startedAt = System.nanoTime();
// Chạy một công việc
long elapsedNanos = System.nanoTime() - startedAt;
~~~

Trong khi đó, `Instant.now()` lấy thời điểm đồng hồ thực. Một đối tượng `Instant` có độ phân giải biểu diễn tới nano nhưng không phải nguồn đo hiệu năng được bảo đảm có độ chính xác vật lý 1 ns. Không đưa thẳng giá trị `System.nanoTime()` vào `ofEpochSecond()` hoặc chia ra epochMillis: mốc đo không tương thích.

Đối với timestamp sự kiện dùng `Instant`; đối với đo thời gian thực thi ngắn, dùng công cụ đo thời lượng tương đối phù hợp. Khi cần kiểm thử, tiêm `Clock` để làm cố định `Instant.now(clock)`.

## 14. Sai sót thường gặp

1. **Nhầm ms với ns:** `ofEpochSecond(seconds, 123)` thêm 123 nano, không phải 123 milli.
2. **Giả định toEpochMilli() giữ nano:** phần dư dưới 1 ms mất vĩnh viễn.
3. **Giả định làm tròn gần nhất:** API làm tròn xuống cấp mili.
4. **Chia epochNanos âm bằng /:** Java cắt về 0, khác trường hợp `-1 ns → -1 ms`.
5. **Dùng getNano() như tổng nano từ epoch:** nó chỉ là phần nano trong một giây.
6. **Tính epochNanos vào long không kiểm tra miền:** có thể overflow khi cách xa epoch.
7. **Đi qua java.util.Date để giữ nano:** `Date` chỉ có milli.
8. **Tin rằng java.sql.Timestamp chắc chắn giữ chín chữ số trong DB:** schema, driver và mapping có thể giảm precision.
9. **Dựa vào số chữ số của Instant.now() để suy ra độ chính xác đồng hồ:** độ phân giải lưu không chứng minh độ chính xác đo.
10. **Coi System.nanoTime() là UTC timestamp:** nó dùng mốc tùy ý.
11. **Quên toEpochMilli() có thể overflow:** miền `Instant` rộng hơn epochMillis `long`.
12. **Gửi timestamp không có đơn vị:** có thể gây nhầm giây/mili/micro/nano.
13. **Lẫn thay đổi múi giờ với giảm precision:** đổi sang `ZonedDateTime` có thể giữ nguyên nano.
14. **Không kiểm tra round-trip sau serialize/DB:** dữ liệu có thể bị cắt hoặc làm tròn trong pipeline.

## 15. Tự kiểm tra

**Câu 1.** `Instant.ofEpochSecond(1, 234_567_890).toEpochMilli()` trả bao nhiêu?  
**Đáp án:** `1234`, mất `567890` nano khi xây lại bằng `ofEpochMilli(1234)`.

**Câu 2.** Vì sao thời điểm `1969-12-31T23:59:59.999999999Z` đổi ra `-1` ms mà không phải `0`?  
**Đáp án:** Vì `toEpochMilli()` làm tròn xuống mốc mili thấp hơn; âm 1 ns nằm giữa âm 1 ms và epoch.

**Câu 3.** Khi nào round-trip qua milli còn chính xác?  
**Đáp án:** Khi `getNano() % 1_000_000 == 0` và phép `toEpochMilli()` không overflow.

**Câu 4.** Có thể lấy lại `456789` nano từ chuỗi đã bị CSDL rút thành `.123` không?  
**Đáp án:** Không; thông tin đã mất ở bước giảm precision.

**Câu 5.** Làm sao truyền đủ nano qua JSON?  
**Đáp án:** Dùng ISO UTC string giữ tối đa chín chữ số phần giây, hoặc cặp `epochSecond` / `nanoOfSecond`, với serializer và parser đồng nhất.

**Câu 6.** `Date.from(instant).toInstant()` có luôn bằng giá trị gốc không?  
**Đáp án:** Không, `Date` chỉ giữ mili giây.

**Câu 7.** `Instant.MAX.toEpochMilli()` có luôn thành công không?  
**Đáp án:** Không; kết quả vượt `long` nên ném `ArithmeticException`.

**Câu 8.** `System.nanoTime()` có phải là tổng nano từ `1970-01-01T00:00Z` không?  
**Đáp án:** Không, đó là bộ đếm dùng đo khoảng thời gian tương đối với mốc không xác định.

## 16. Ghi nhớ

`Instant` mô tả một thời điểm tới độ phân giải **1 nano giây**, còn epochMillis chỉ giữ **1 mili giây**. Chuyển xuống milli làm mất phần nano không chia hết một triệu; thông tin đó không thể tái tạo. Với thời điểm trước epoch, quy tắc floor gây kết quả dễ nhầm: **âm một nano thành âm một mili**. Cần bảo toàn toàn bộ thì dùng `Instant` xuyên suốt, ISO text đủ phần lẻ hoặc cặp giây–nano. Cần dùng epochMillis thì ghi rõ chính sách giảm precision, kiểm tra miền số và xác minh việc ghi/đọc ở các lớp tích hợp.
