# Quản lý formatter khả biến và bộ nhớ đệm theo Locale trong ứng dụng Java

## 1. Vấn đề thiết kế: formatter dùng lại được, nhưng dùng chung chưa chắc an toàn

Ứng dụng Java đa ngôn ngữ thường định dạng hàng nghìn giá trị số, tiền tệ, ngày giờ và chuỗi văn bản trong mỗi giây. Một ý tưởng hấp dẫn là tạo formatter một lần rồi lưu trong `static Map<Locale, Formatter>` để tái sử dụng cho mọi request.

Ý tưởng này **có thể sai** với nhiều formatter của API cũ:

- `java.text.NumberFormat` và `DecimalFormat` là các đối tượng **khả biến (mutable)**, không an toàn khi nhiều thread cùng sử dụng mà không đồng bộ phù hợp.
- `java.text.DateFormat` và `SimpleDateFormat` cũng mutable, có trạng thái lịch (`Calendar`), múi giờ (`TimeZone`), leniency và pattern.
- `java.text.MessageFormat`, `ChoiceFormat`, `Collator` và các lớp xử lý định dạng/so sánh tương tự cũng có cấu hình có thể đổi.
- `java.time.format.DateTimeFormatter` lại được thiết kế **immutable và thread-safe**, có thể dùng chung sau khi tạo xong.

Ngoài vấn đề thread safety, **`Locale` không luôn đủ làm khóa cache**. Với cùng `Locale.US`, ứng dụng có thể cần định dạng hai chữ số thập phân hoặc không có chữ số thập phân, dùng hai tiền tệ hoặc hai múi giờ, hoặc hiển thị ngày dưới những mẫu khác nhau.

Bài học này tập trung vào cách **thiết kế, quản lý vòng đời và cache formatter theo locale/cấu hình** trong Java 17+, gồm:

1. Vì sao cache một formatter mutable và trả trực tiếp cho caller dễ gây lỗi.
2. Cách tạo formatter mỗi lần, cache prototype rồi clone, hoặc dùng instance riêng cho thread.
3. Cách cache `DateTimeFormatter` immutable theo khóa đầy đủ.
4. Cách định nghĩa cache key bao gồm locale, pattern, rounding, currency, timezone và các chính sách khác.
5. Giới hạn về memory, eviction, tính nhất quán sau đổi cấu hình và kiểm thử đa luồng.

**Nguyên tắc ngắn:** *Dùng chung dữ liệu cấu hình bất biến; không vô tình dùng chung trạng thái formatter có thể bị sửa.*

## 2. Bản đồ các formatter thường gặp

| API | Tính khả biến / thread safety | Gợi ý quản lý |
|---|---|---|
| `NumberFormat` | Mutable; không bảo đảm thread-safe khi dùng chung | Tạo theo request, clone prototype hoặc quản lý theo thread |
| `DecimalFormat` | Mutable; có pattern, symbols, rounding, min/max digits | Không trả reference cache gốc để caller sửa |
| `DateFormat` | Mutable; chứa Calendar/TimeZone và các tùy chọn parse | Tạo/clone riêng, ưu tiên API `java.time` khi có thể |
| `SimpleDateFormat` | Mutable, không thread-safe | Không dùng một instance `static` chung thiếu đồng bộ |
| `MessageFormat` | Mutable; có pattern/format subobjects | Clone hoặc tạo mới; kiểm soát cả các subformats |
| `ChoiceFormat` | Mutable | Tạo/clone theo ngữ cảnh khi thay pattern/limits |
| `Collator` | Mutable; strength/decomposition thay đổi được | Clone/tạo theo request, tránh sửa comparator đang được cấu trúc dữ liệu dùng |
| `DateTimeFormatter` | Immutable, thread-safe | Có thể cache và chia sẻ trực tiếp |
| `DateTimeFormatterBuilder` | Builder có trạng thái khi dựng formatter | Không chia sẻ builder đang bị chỉnh; cache kết quả `toFormatter(...)` |
| `DecimalFormatSymbols`, `DateFormatSymbols` | Có thể sửa các ký hiệu / tên | Không coi object cấu hình mutable là key ổn định |

Trong thiết kế thực tế, formatter còn có thể chứa hoặc tham chiếu những đối tượng phụ khả biến, như `Calendar` hoặc `Format` con. **Không chỉ nhìn tên class bên ngoài** mà bỏ qua các đối tượng nó sử dụng.

Một `Locale` là mô tả ngôn ngữ/vùng. Nó không tự mã hóa toàn bộ lựa chọn của một formatter, chẳng hạn `RoundingMode.HALF_UP`, currency `EUR`, mẫu `dd/MM/uuuu`, `ZoneId.of("Asia/Ho_Chi_Minh")` hay `ResolverStyle.STRICT`.

## 3. Thấy lỗi ngay với một cache mutable dùng chung

Ví dụ sau đơn giản nhưng **không nên áp dụng cho hệ thống thật**:

```java
import java.text.NumberFormat;
import java.util.Locale;

public class UnsafeSharedFormat {
    private static final NumberFormat SHARED =
            NumberFormat.getNumberInstance(Locale.US);

    public static String format(double value) {
        SHARED.setMaximumFractionDigits(0);
        return SHARED.format(value);
    }
}
```

Vấn đề:

- `SHARED` là một formatter có thể thay đổi cấu hình.
- Một lời gọi khác có thể muốn hai chữ số thập phân và đặt `setMaximumFractionDigits(2)`.
- Khi hai request cùng gọi, cấu hình có thể bị thay đổi **trước khi một request format xong**.
- Ngay cả khi các thread không chạy đồng thời, thay cấu hình trong request trước có thể làm request sau nhận trạng thái không mong muốn.
- Bản thân `NumberFormat` không hứa hẹn an toàn cho các thao tác format/parse đồng thời trên cùng instance.

Không thể khắc phục triệt để chỉ bằng việc dùng `ConcurrentHashMap<Locale, NumberFormat>`. Map có thể thread-safe ở thao tác **get/put**, nhưng **formatter chứa bên trong vẫn mutable**.

Điều này minh họa hai tầng an toàn độc lập:

1. **An toàn của cấu trúc cache:** nhiều thread có thể get/put mà không hỏng cấu trúc map.
2. **An toàn của đối tượng được cache:** nhiều thread có thể gọi formatter mà không xung đột trạng thái.

`ConcurrentHashMap` giải quyết tầng thứ nhất; nó **không làm `DecimalFormat` trở thành thread-safe**.

## 4. Formatter mutable lưu trong cache có thể sai ngay cả khi không có concurrency

Xét hai request lần lượt:

```java
DecimalFormat shared = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));

shared.setMaximumFractionDigits(0);
String first = shared.format(1234.5);

shared.setMaximumFractionDigits(2);
String second = shared.format(1234.5);
```

Không có concurrency ở đây. Nhưng nếu caller A thay maximum rồi bỏ quên reset, caller B lấy cùng instance từ cache sẽ nhận cấu hình của A. Do đó, việc coi “không có race vì mỗi lần xử lý một request” **vẫn chưa đủ**.

Hơn nữa, các setter của `NumberFormat` có thể tương tác: khi tăng minimum vượt maximum, maximum có thể được điều chỉnh. Không nên viết code dựa trên giả định một setter chỉ đổi một trường duy nhất.

### Ví dụ Java 17+ kiểm chứng ảnh hưởng của clone

Lưu `MutableFormatterDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class MutableFormatterDemo {
    public static void main(String[] args) {
        DecimalFormat prototype = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US));
        prototype.setRoundingMode(RoundingMode.HALF_EVEN);

        DecimalFormat copy =
                (DecimalFormat) prototype.clone();
        copy.setMaximumFractionDigits(0);

        BigDecimal value = new BigDecimal("1234.50");

        System.out.println(
                "prototype=" + prototype.format(value));
        System.out.println("clone=" + copy.format(value));
        System.out.println(
                "prototypeAgain=" + prototype.format(value));
    }
}
```

Chạy:

```bash
javac MutableFormatterDemo.java
java MutableFormatterDemo
```

Kết quả đã kiểm chứng với JDK:

```text
prototype=1,234.50
clone=1,234
prototypeAgain=1,234.50
```

`copy` có cấu hình riêng. Việc đổi maximum của clone không làm thay đổi prototype. Đó là một đặc tính quan trọng để xây dựng **prototype cache**: lưu bản mẫu và **trả một bản clone cho mỗi lần sử dụng**, không trả bản mẫu.

**Lưu ý:** `clone()` của một API cụ thể cần được hiểu theo hợp đồng lớp đó. Với `DecimalFormat` và `DateFormat` của JDK, các bản clone được thiết kế để có cấu hình/đối tượng định dạng độc lập cho mục đích dùng này. Đừng mở rộng kết luận sang mọi class tuỳ biến chỉ vì nó có phương thức `clone()`.

## 5. Phương án đơn giản nhất: tạo formatter mới mỗi lần

Nếu hệ thống không có bằng chứng rằng chi phí tạo formatter gây chậm đáng kể, cách rõ ràng và dễ kiểm soát là tạo instance trong phạm vi xử lý:

```java
static String formatAmount(
        BigDecimal amount,
        Locale locale) {

    DecimalFormat formatter = new DecimalFormat(
            "#,##0.00",
            DecimalFormatSymbols.getInstance(locale));
    formatter.setRoundingMode(RoundingMode.HALF_UP);
    return formatter.format(amount);
}
```

Đây là **mảnh code** cần import `BigDecimal`, `Locale`, `DecimalFormat`, `DecimalFormatSymbols` và `RoundingMode`.

Lợi ích:

- Không có formatter mutable dùng chung giữa các request.
- Mỗi instance nhận đúng locale và cấu hình hiện tại.
- Không cần cơ chế evict hay invalidate cache.
- Test đơn giản và không có bộ nhớ cache tích lũy theo nhiều người dùng.

Đánh đổi: tạo formatter có thể liên quan đến thiết lập pattern và locale data, nên có chi phí khi gọi cực nhiều lần. Nhưng **không nên quyết định cache chỉ từ trực giác**. Hãy benchmark với workload thực, tính cả GC và concurrency, rồi mới chọn cấu trúc phức tạp.

Nếu ứng dụng format ít giá trị trong một request, một instance tạo cho request đó rồi dùng tuần tự nhiều lần là lựa chọn hợp lý: **re-use trong phạm vi một thread/request** khác với **share toàn cục giữa các thread**.

## 6. Cache prototype rồi clone: một thiết kế cho DecimalFormat

Khi việc tạo formatter thực sự đáng kể và tập cấu hình không quá lớn, có thể cache **bản mẫu cấu hình**. Mỗi caller nhận clone mới.

Ví dụ Java 17 dùng `record` làm key và `ConcurrentHashMap` để tạo prototype an toàn khi nhiều thread cùng yêu cầu một key.

### Chương trình Java 17+ hoàn chỉnh

Lưu `DecimalFormatCacheDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public class DecimalFormatCacheDemo {
    record Key(
            Locale locale,
            String pattern,
            RoundingMode rounding) {}

    private static final ConcurrentMap<Key, DecimalFormat> PROTOTYPES =
            new ConcurrentHashMap<>();

    private static DecimalFormat fresh(Key key) {
        DecimalFormat template =
                PROTOTYPES.computeIfAbsent(key, k -> {
                    DecimalFormat f = new DecimalFormat(
                            k.pattern(),
                            DecimalFormatSymbols.getInstance(k.locale()));
                    f.setRoundingMode(k.rounding());
                    return f;
                });

        return (DecimalFormat) template.clone();
    }

    public static void main(String[] args) {
        Key us = new Key(
                Locale.US, "#,##0.00", RoundingMode.HALF_UP);
        Key de = new Key(
                Locale.GERMANY, "#,##0.00", RoundingMode.HALF_UP);

        DecimalFormat a = fresh(us);
        DecimalFormat b = fresh(us);
        DecimalFormat c = fresh(de);

        a.setMaximumFractionDigits(0);

        BigDecimal value = new BigDecimal("1234.50");

        System.out.println("changed=" + a.format(value));
        System.out.println("unchanged=" + b.format(value));
        System.out.println("germany=" + c.format(value));
        System.out.println("keys=" + PROTOTYPES.size());
    }
}
```

Biên dịch/chạy:

```bash
javac DecimalFormatCacheDemo.java
java DecimalFormatCacheDemo
```

Đầu ra đã kiểm chứng:

```text
changed=1,235
unchanged=1,234.50
germany=1.234,50
keys=2
```

Giải thích:

- `Key` chứa `Locale`, pattern và rounding mode. Hai bản US dùng cùng một prototype, German dùng prototype khác.
- `computeIfAbsent` giúp tạo và công bố prototype theo key trong concurrent map; không để caller tự điều phối một race get–create–put thô.
- `fresh(key)` **trả clone**; `a` và `b` không phải chung object. Việc `a.setMaximumFractionDigits(0)` không đổi `b`.
- `PROTOTYPES.size() == 2` vì có hai bộ key.
- Prototype **không bị sửa sau khi được đưa vào cache**, một bất biến quan trọng của thiết kế.

Tuy nhiên, phương án này **không tự giới hạn số lượng key**: nếu caller tạo pattern ngẫu nhiên hoặc hàng nghìn biến thể, map sẽ tăng. Cần kiểm soát tập cấu hình cho phép hoặc dùng cache có eviction, expiration hoặc quota phù hợp.

### Lý do không trả trực tiếp prototype

Sai:

```java
return PROTOTYPES.computeIfAbsent(key, this::createFormatter);
```

Đây là **mảnh minh họa sai**, không phải chương trình độc lập. Trả formatter gốc khiến mọi caller cùng sửa/cùng format trên một instance. Một cache thread-safe không ngăn được hành vi này.

Đúng với thiết kế prototype:

```java
DecimalFormat prototype = PROTOTYPES.get(key);
return (DecimalFormat) prototype.clone();
```

Chỉ dùng đoạn này khi prototype đã được tạo, không `null` và **không thay đổi cấu hình** sau publication. Trong mã thực, phương thức `fresh(...)` phía trên đã xử lý cả khởi tạo và clone.

### Có phải clone luôn nhanh hơn new?

Không có bảo đảm phổ quát. Clone có thể giảm công việc thiết lập cấu hình, nhưng vẫn phân bổ instance mới và có chi phí copy. Hãy đo hiệu năng với cấu hình, locale, phiên bản JDK và tải thực tế. Nếu tạo formatter mới đủ rẻ, phương án đơn giản hơn thường đáng ưu tiên.

## 7. Khóa cache phải mô tả đầy đủ hành vi định dạng

Một map chỉ có `Locale` làm key thường không đủ:

```java
Map<Locale, DecimalFormat> byLocale;
```

Với cùng `Locale.US`, có thể có:

- Pattern `#,##0.00` và `0.###`.
- `RoundingMode.HALF_UP` và `HALF_EVEN`.
- Minimum/maximum fraction digits khác nhau.
- Currency `USD` và `EUR` với ký hiệu/độ chính xác khác nhau.
- Bật/tắt grouping.
- Chế độ parse `setParseBigDecimal(true)` hoặc số nguyên `setParseIntegerOnly(true)`.
- Ký hiệu `DecimalFormatSymbols` tùy chỉnh.
- Prefix/suffix do ứng dụng đặt.
- Các quy tắc riêng như hiển thị phần trăm, số âm, NaN, infinity và dấu số.

Nếu hai formatter có cùng locale nhưng khác **kết quả đầu ra hoặc cách parse**, chúng cần key khác nhau, hoặc không được cache cùng cấu hình.

Một record minh họa:

```java
record NumberKey(
        Locale locale,
        String pattern,
        RoundingMode roundingMode,
        boolean grouping,
        int minimumFraction,
        int maximumFraction,
        String currencyCode) {}
```

Đây là mô hình minh họa, chưa phải một cache triển khai đầy đủ. Cần kiểm soát consistency, ví dụ `minimumFraction <= maximumFraction`, currency code hợp lệ, các pattern/locale được phép, và cách áp các setter để đảm bảo cùng key tạo ra cùng formatter.

**Đừng dùng đối tượng mutable `DecimalFormat` hay `DecimalFormatSymbols` làm key** nếu chúng có thể bị thay đổi sau khi put. Key dùng trong `HashMap` / `ConcurrentHashMap` phải có `equals()`/`hashCode()` ổn định khi nằm trong map. Các thành phần như `String`, `Locale`, `RoundingMode`, enum và primitive là cơ sở tốt cho key.

## 8. Thứ tự áp dụng cấu hình cũng là một phần hợp đồng

`DecimalFormat` có các setter mà thứ tự sử dụng có thể ảnh hưởng kết quả:

```java
DecimalFormat f = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));

f.setMaximumFractionDigits(0);
f.setMinimumFractionDigits(3);
```

Sau lời gọi cuối, formatter có thể tự tăng max để bảo đảm min không vượt max. Vì vậy, khi tạo prototype từ key, nên:

1. Khởi tạo pattern và symbols theo locale.
2. Đặt currency/grouping và các lựa chọn khác.
3. Thiết lập max/min digits với thứ tự được xác định rõ.
4. Đặt rounding mode và parsing policy.
5. Đọc lại getter quan trọng trong unit test để xác nhận cấu hình cuối.

Không thay pattern bằng `applyPattern(...)` **sau cùng** nếu setter trước đó đã thiết lập min/max digits mà bạn muốn giữ: `applyPattern` có thể đặt lại các giới hạn theo pattern mới.

Khi cache, một key chỉ đáng tin nếu factory **thuần theo key và chính sách cấu hình bất biến**. Nếu factory dùng `Locale.getDefault()`, default timezone của server hoặc trạng thái config toàn cục thay đổi âm thầm, cùng một key có thể tạo hai formatter khác nhau.

## 9. DateFormat/SimpleDateFormat: nguy cơ lớn hơn vì có Calendar

`java.text.DateFormat` và `SimpleDateFormat` chứa trạng thái định dạng/ngày giờ, thường dùng `Calendar` trong các thao tác format/parse. Việc gọi chung một `SimpleDateFormat` từ nhiều thread có thể gây lỗi, kết quả sai hoặc hành vi không xác định dưới concurrency.

Ví dụ **không an toàn**:

```java
private static final SimpleDateFormat SHARED =
        new SimpleDateFormat("yyyy-MM-dd HH:mm:ss");
```

Ngoài thread safety, `SimpleDateFormat` có thể chịu ảnh hưởng của timezone mặc định hoặc bị caller đổi bằng:

```java
SHARED.setTimeZone(TimeZone.getTimeZone("UTC"));
SHARED.applyPattern("dd/MM/yyyy");
SHARED.setLenient(false);
```

Đây là các đoạn code minh họa, không phải chương trình hoàn chỉnh. Nếu formatter này được cache dưới khóa chỉ có locale, caller có thể vô tình áp **timezone hoặc pattern của request trước** lên request sau.

### Nếu bắt buộc dùng DateFormat

Các lựa chọn:

- Tạo mới cho một request / operation.
- Lưu prototype theo đủ `Locale + pattern + timezone + leniency` rồi `clone()` mỗi lượt.
- Dùng thread-local instance **chỉ khi toàn bộ cấu hình gắn chặt với key/thread và vòng đời được quản lý đúng**.
- Đồng bộ toàn bộ truy cập vào một instance mutable (có thể đúng nhưng có chi phí contention và không cho caller đổi cấu hình ngoài lock).

Trong code mới, khi không bị ràng buộc API cũ, **ưu tiên `java.time` + `DateTimeFormatter`**: giảm đáng kể việc quản lý mutable state.

### Clone DateFormat phải bao gồm chính sách time zone

Ví dụ một đoạn có thể chạy trong phương thức đã import:

```java
SimpleDateFormat prototype =
        new SimpleDateFormat("dd/MM/yyyy HH:mm", Locale.US);
prototype.setTimeZone(TimeZone.getTimeZone("UTC"));
prototype.setLenient(false);

SimpleDateFormat copy =
        (SimpleDateFormat) prototype.clone();

copy.setTimeZone(
        TimeZone.getTimeZone("Asia/Ho_Chi_Minh"));
```

Nếu dùng `copy` cho yêu cầu địa phương, đừng sửa prototype hay một clone đang được request khác dùng. Khi hai formatter có timezone khác nhau, **không được cache dưới cùng key chỉ gồm Locale.US**.

### Cẩn thận khi parse

`DateFormat` còn có `setLenient`. Nếu một request muốn STRICT-ish parsing và request khác muốn lenient parsing, đây là khác biệt lớn về nghiệp vụ. Hơn nữa, `setLenient(false)` của legacy parser **không thay cho kiểm tra phần dư** với `ParsePosition`. Một cache parser cần key và kiểm thử bao gồm cả parsing mode, pattern và việc tiêu thụ hết input.

## 10. DateTimeFormatter: immutable và chia sẻ trực tiếp

`java.time.format.DateTimeFormatter` được thiết kế **bất biến và thread-safe**, nên sau khi tạo có thể chia sẻ giữa nhiều thread mà không cần clone hoặc synchronization cho thao tác format/parse.

Ví dụ:

```java
import java.time.format.DateTimeFormatter;

public final class Dates {
    public static final DateTimeFormatter ISO_DAY =
            DateTimeFormatter.ISO_LOCAL_DATE;
}
```

Dùng cùng formatter cho nhiều ngày:

```java
String text = Dates.ISO_DAY.format(
        java.time.LocalDate.of(2024, 3, 1));
```

Kết quả là `2024-03-01` và formatter không bị sửa. Các phương thức dạng `withLocale(...)`, `withZone(...)`, `withResolverStyle(...)`, `withDecimalStyle(...)` tạo/cho ra một formatter có cấu hình mong muốn mà **không thay đổi formatter gốc**.

Ví dụ:

```java
DateTimeFormatter base =
        DateTimeFormatter.ofPattern(
                "dd/MM/uuuu HH:mm", Locale.US);

DateTimeFormatter vietnam =
        base.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

DateTimeFormatter utc =
        base.withZone(ZoneOffset.UTC);
```

Cả `base`, `vietnam` và `utc` có thể chia sẻ an toàn sau khi cấu hình. Khi format `Instant`, `vietnam` và `utc` cho giờ địa phương khác nhau.

**Lưu ý:** immutable ở đây là **formatter instance**, không có nghĩa mọi đối tượng đầu vào đều immutable hoặc thời gian hiện tại không thể thay đổi. `java.time` cũng có `DateTimeFormatterBuilder` mutable: builder chỉ dùng trong giai đoạn xây dựng, kết quả `toFormatter(...)` mới là đối tượng có thể chia sẻ.

## 11. Cache DateTimeFormatter bằng key chứa locale, pattern và zone

Với nhiều pattern/locale/zone, cache immutable `DateTimeFormatter` rất tự nhiên:

```java
ConcurrentHashMap<DateKey, DateTimeFormatter>
```

Vì formatter đã immutable, cache được phép **trả trực tiếp instance gốc** cho các caller. Không cần clone.

### Chương trình Java 17+ hoàn chỉnh

Lưu `DateTimeFormatterCacheDemo.java`:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public class DateTimeFormatterCacheDemo {
    record Key(
            Locale locale,
            String pattern,
            ZoneId zone) {}

    private static final ConcurrentMap<Key, DateTimeFormatter> CACHE =
            new ConcurrentHashMap<>();

    private static DateTimeFormatter get(Key key) {
        return CACHE.computeIfAbsent(key, k ->
                DateTimeFormatter.ofPattern(
                        k.pattern(), k.locale())
                        .withZone(k.zone()));
    }

    public static void main(String[] args) {
        Instant timestamp =
                Instant.parse("2024-03-01T00:00:00Z");

        Key local = new Key(
                Locale.US,
                "dd/MM/uuuu HH:mm",
                ZoneId.of("Asia/Ho_Chi_Minh"));

        Key utc = new Key(
                Locale.US,
                "dd/MM/uuuu HH:mm",
                ZoneOffset.UTC);

        System.out.println(
                "local=" + get(local).format(timestamp));
        System.out.println(
                "utc=" + get(utc).format(timestamp));
        System.out.println(
                "sameObj=" + (get(local) == get(local)));
        System.out.println("cacheSize=" + CACHE.size());
    }
}
```

Biên dịch và chạy:

```bash
javac DateTimeFormatterCacheDemo.java
java DateTimeFormatterCacheDemo
```

Kết quả kiểm chứng:

```text
local=01/03/2024 07:00
utc=01/03/2024 00:00
sameObj=true
cacheSize=2
```

Kết quả cho thấy:

1. `Key` chứa cả `Locale`, pattern và `ZoneId`.
2. `computeIfAbsent` tạo một formatter bất biến cho mỗi key, công bố qua concurrent map.
3. Hai zone khác nhau tạo **hai key** và hai kết quả giờ.
4. Hai lần gọi với cùng key nhận lại chính instance đã cache (nên `sameObj=true`).
5. Không caller nào sửa được cấu hình của instance từ cache. Muốn cấu hình khác, tạo formatter mới bằng `withZone/withLocale` hoặc dùng key khác.

Đây là ví dụ cache **không có giới hạn kích thước**, phù hợp minh họa nhưng chưa đủ cho mọi hệ thống production có số lượng zone/pattern/locale động.

## 12. Khóa cache của DateTimeFormatter còn có thể cần nhiều trường hơn

`Locale + pattern + ZoneId` là một điểm khởi đầu, **không phải công thức bao phủ mọi formatter**. Những lựa chọn khác ảnh hưởng kết quả:

- `ResolverStyle`: `STRICT`, `SMART`, `LENIENT` khi parse.
- `Chronology`: ví dụ lịch ISO so với JapaneseChronology hoặc ThaiBuddhistChronology.
- `DecimalStyle`: dấu âm, dấu thập phân và chữ số theo locale/numbering system.
- Các cấu hình `DateTimeFormatterBuilder` như optional sections, parse case-insensitive, parse strict/lenient, defaulting fields.
- Kiểu pattern, localized style (SHORT/MEDIUM/LONG/FULL), và lựa chọn có/không zone override.
- Version của chính sách pattern hoặc cấu hình ứng dụng.

Nếu ứng dụng tạo formatter với `withResolverStyle(STRICT)` cho parse input, nhưng cache key chỉ ghi `Locale + pattern` và trả một formatter `SMART`, đó là **lỗi chức năng**, không phải tối ưu hóa chưa tốt.

Một key đầy đủ hơn có thể là:

```java
record DateKey(
        Locale locale,
        String pattern,
        ZoneId zone,
        ResolverStyle resolverStyle,
        Chronology chronology) {}
```

Đây là **mô hình minh họa**, cần import `java.time.format.ResolverStyle` và `java.time.chrono.Chronology`. Nếu app có nhiều `DecimalStyle` hoặc các builder flags, cũng cần lưu chúng trong khóa hoặc tách thành các cache theo chức năng.

Không phải lúc nào cũng phải nhét mọi thuộc tính vào một record. Một cách sạch hơn là định nghĩa **một factory/formatter riêng cho mỗi use case**, với key chỉ có tham số thực sự biến đổi. Quan trọng là hai cấu hình khác nhau **không được alias cùng một entry**.

## 13. ThreadLocal: dùng đúng chỗ, không phải bộ nhớ đệm thần kỳ

`ThreadLocal<T>` cho phép mỗi thread có một instance riêng. Với legacy `SimpleDateFormat`, ví dụ:

```java
private static final ThreadLocal<SimpleDateFormat> UTC_FORMAT =
        ThreadLocal.withInitial(() -> {
            SimpleDateFormat f =
                    new SimpleDateFormat(
                            "yyyy-MM-dd'T'HH:mm:ss",
                            Locale.US);
            f.setTimeZone(TimeZone.getTimeZone("UTC"));
            f.setLenient(false);
            return f;
        });
```

Đây là mảnh code cần import `SimpleDateFormat`, `ThreadLocal`, `Locale`, `TimeZone`. Mỗi thread sẽ có một formatter của riêng mình khi gọi `UTC_FORMAT.get()`.

Nó giải quyết việc **cùng một instance bị nhiều thread truy cập đồng thời**, nhưng có những điều kiện:

- Formatter trong ví dụ phải luôn giữ **cùng pattern/locale/zone**; không sửa nó theo request rồi để thread phục vụ request khác.
- Thread pools tái sử dụng thread giữa nhiều request, nên dữ liệu hoặc cấu hình còn sót lại có thể ảnh hưởng request tiếp theo.
- Một `ThreadLocal` gắn với nhiều trường cấu hình động không tự biến thành cache theo locale. Nếu thread xử lý locale US rồi DE, formatter không tự đổi locale.
- Thread-local values có thể giữ object lâu trong thread pool. Quản lý vòng đời và `remove()` khi appropriate, đặc biệt nếu chứa dữ liệu nhạy cảm/ngữ cảnh request.
- Với Java virtual threads hoặc số lượng thread rất lớn, giữ một formatter cho **mỗi thread** có thể không kinh tế; hãy đo bộ nhớ và workload.

### Sai lầm: ThreadLocal nhưng sửa locale tùy request

Ví dụ sai về mặt thiết kế:

```java
SimpleDateFormat f = UTC_FORMAT.get();
f.applyPattern(requestPattern);
f.setTimeZone(requestZone);
String text = f.format(date);
```

Nếu không phục hồi cấu hình một cách đầy đủ, thread sau nhận formatter còn pattern/zone của request trước. `ThreadLocal` **không ngăn leakage giữa các request dùng chung thread theo thời gian**.

Lựa chọn tốt hơn cho pattern/locale/zone động:

- Tạo formatter mới theo request.
- Cache prototype theo key đầy đủ và clone.
- Hoặc ưu tiên `DateTimeFormatter` bất biến.

Một ThreadLocal cố định cho đúng một cấu hình có thể hợp lý; một ThreadLocal được chỉnh tùy hứng ở mọi request thường khó kiểm chứng.

## 14. Dùng synchronization trên formatter chung: đúng nhưng phải đủ phạm vi

Có thể đồng bộ để bảo vệ một formatter mutable:

```java
synchronized (sharedFormatter) {
    String result = sharedFormatter.format(value);
    // Dùng result tại đây.
}
```

Nhưng khi cần thay đổi cấu hình, **toàn bộ chuỗi thao tác chỉnh cấu hình + format/parse** cũng phải nằm trong cùng một cơ chế lock. Nếu thread A đặt timezone ngoài lock, thread B có thể format ngay trước khi A vào synchronized.

Các nguy cơ:

- **Contention:** nhiều thread phải chờ cùng formatter.
- **Locking sai phạm vi:** code khác truy cập object mà không dùng cùng lock.
- **Khóa không theo locale:** nếu nhiều locale cùng sử dụng một formatter, đồng bộ không tự thiết lập cấu hình đúng.
- **Lỗi tích hợp:** formatter được đưa ra ngoài (escaped) khiến caller khác gọi không qua lock.

Vì vậy, synchronize một formatter chung **có thể bảo đảm an toàn nếu tất cả truy cập được quản lý chặt chẽ**, nhưng thường không phải thiết kế tốt nhất cho web server nhiều request. Tạo mới/clone hay immutable formatter giúp tránh chia sẻ mutable state ngay từ đầu.

## 15. MessageFormat và Collator cũng cần cùng nguyên tắc

### MessageFormat

`MessageFormat` có pattern, locale và những formatter con có thể thay đổi. Ví dụ cùng pattern hiển thị tổng số item, ứng dụng có thể thay `setLocale`, `applyPattern` hoặc custom subformats. Nếu các request dùng chung một instance rồi sửa, kết quả có thể lẫn nhau.

Tạo mới theo locale:

```java
MessageFormat message =
        new MessageFormat(
                "You have {0,number,integer} items.",
                Locale.US);

String result = message.format(new Object[]{1234});
```

Đây là mảnh code, cần import `MessageFormat` và `Locale`. Với các thông điệp nội địa hóa, nên dùng pattern từ resource bundle và cache key chứa **locale + message key + pattern/version + cấu hình formats** khi thực sự cần cache. Không coi message key là đủ khi bản dịch có thể thay đổi.

Nếu dùng clone, phải đảm bảo cả subformats và trạng thái format không bị caller khác chia sẻ/sửa theo cách trái hợp đồng. Không cache một `MessageFormat` rồi trả trực tiếp cho code tự do thay `applyPattern(...)`.

### Collator

`Collator` có `setStrength` và `setDecomposition`; kết quả so sánh thay đổi theo hai trường này. Cache chỉ bằng locale khi một request dùng `PRIMARY` để tìm kiếm linh hoạt còn request khác dùng `TERTIARY` để sắp xếp có thể gây sai.

Ví dụ mảnh code:

```java
Collator prototype = Collator.getInstance(Locale.FRENCH);
prototype.setStrength(Collator.TERTIARY);

Collator perRequest = (Collator) prototype.clone();
perRequest.setStrength(Collator.PRIMARY);
```

Bản clone có thể được sửa mà không ảnh hưởng prototype. Với `TreeMap`/`TreeSet`, **không thay comparator khi collection đang dùng nó**, kể cả comparator chỉ được sửa trong cùng thread: quan hệ thứ tự thay đổi nhưng cây không được xây dựng lại.

## 16. ResourceBundle có nên cache như formatter không?

`ResourceBundle` phục vụ **tra cứu bản dịch**, khác formatter số/ngày. `ResourceBundle.getBundle(...)` có cơ chế cache nội bộ và fallback theo locale. Bài toán quản lý resource bundles cần phân biệt:

- Dịch/chuỗi UI có bản `messages_vi.properties` hay không.
- Locale yêu cầu và locale thực tế của bundle được chọn.
- Chính sách reload và `ResourceBundle.Control` (với những giới hạn áp dụng cho named modules).
- Vòng đời class loader/module và phiên bản dữ liệu dịch.

Không nên tự tạo một `ConcurrentHashMap<Locale, ResourceBundle>` chỉ vì đang cache `DecimalFormat`. Cache built-in của `ResourceBundle` có thể đã phù hợp; nếu cần reload bản dịch, cần chính sách rõ thay vì giữ reference cũ mãi.

**Đặc biệt:** thay đổi locale của formatter không tự thay nội dung bản dịch UI. Ngược lại, có `messages_vi.properties` cũng không bảo đảm `NumberFormat` đang dùng đúng data locale của JDK. Hai luồng cấu hình cần được quản lý độc lập.

## 17. Quy tắc lựa chọn cache key theo chức năng

Hãy mô tả yêu cầu của từng loại định dạng trước khi thiết kế key:

| Chức năng | Những chiều cấu hình có thể cần đưa vào key |
|---|---|
| Số thập phân | Locale, pattern, rounding, min/max digits, grouping, symbols |
| Tiền tệ | Locale hiển thị, currency, fraction digits, rounding, pattern |
| Phần trăm | Locale, mẫu/scale, rounding, min/max digits |
| Ngày giờ legacy | Locale, pattern, `TimeZone`, leniency, chronology/calendar |
| Ngày giờ `java.time` | Locale, pattern/style, zone, chronology, resolver, decimal style |
| Thông điệp `MessageFormat` | Locale, message key, pattern/version, custom formats |
| Collation | Locale, strength, decomposition, rule/version/provider |
| Parsing đầu vào | Locale, pattern, leniency, full-consumption policy, numeric type |

Một key cache là **hợp đồng đồng nhất cấu hình**: hai request chỉ nên dùng chung entry khi factory tạo ra hành vi phù hợp với cả hai. Nếu key thiếu một chiều, bug có thể xảy ra dù không có concurrency.

Một chiến lược khác là tách cache thành các use cases cố định: `NUMBER_TWO_DECIMALS`, `NUMBER_INTEGER`, `CURRENCY_DISPLAY`, `SHORT_DATE`. Khi đó locale là chiều biến đổi duy nhất trong **mỗi cache chuyên biệt** — nhưng cần đảm bảo chính sách các use cases đó không thay đổi âm thầm.

## 18. Thiết kế một factory formatter theo ngữ cảnh người dùng

Thay vì rải `Locale.getDefault()` và formatter cache ở nhiều nơi, có thể gom cấu hình đầu vào vào một lớp/record:

```java
record FormattingContext(
        Locale locale,
        ZoneId zone,
        Currency currency,
        RoundingMode rounding) {}
```

Đây là mảnh code, yêu cầu import `Locale`, `ZoneId`, `Currency` và `RoundingMode`.

Mỗi request chọn `FormattingContext` từ profile, tenant, language header hoặc chính sách nghiệp vụ được xác thực. Sau đó các factory tạo formatter theo đúng bối cảnh:

```text
HTTP request / user settings
           |
           v
FormattingContext (locale, zone, currency, rounding)
           |
           +--> immutable date formatter cache
           |
           +--> mutable number formatter factory/clone
           |
           +--> localized messages / ResourceBundle
           |
           v
Response/UI
```

Tách locale khỏi timezone: `vi-VN` là mô tả ngôn ngữ/vùng, nhưng một người dùng nói tiếng Việt có thể đang ở Paris; múi giờ không suy ra một-một từ locale. Tách currency khỏi locale: giao dịch dùng `EUR` vẫn có thể hiển thị bằng format tiếng Việt. Rounding cũng là chính sách nghiệp vụ, không thể luôn đoán từ locale.

**Đừng ghi thay đổi bối cảnh request vào global `Locale.setDefault(...)` hoặc `TimeZone.setDefault(...)`.** Chúng là trạng thái toàn cục, có thể ảnh hưởng request đồng thời.

## 19. Lưu ý với cache unbounded và key do người dùng cung cấp

`ConcurrentHashMap` giữ các entry cho tới khi xóa hoặc map bị thu gom. Nếu key chứa pattern hoặc locale tag do client tự nhập, tập key có thể tăng vô hạn:

```text
locale=vi-VN, pattern=A
locale=vi-VN, pattern=B
locale=vi-VN, pattern=C
...
```

Một request lỗi hoặc không tin cậy có thể cố ý tạo vô số pattern khác nhau, làm tăng bộ nhớ và áp lực GC. Cần:

1. **Giới hạn tập pattern** được chấp nhận từ ứng dụng.
2. **Xác thực locale tag** và chỉ cho phép tập locale sản phẩm hỗ trợ khi phù hợp.
3. Có chính sách eviction/maximum size nếu số tổ hợp thực sự lớn.
4. Đặt timeout/metrics cho việc tạo entry có chi phí đáng kể.
5. Không đưa dữ liệu chứa secret hoặc user-specific content vào cache toàn cục nếu không có lý do và cơ chế cô lập.
6. Theo dõi hit ratio, tổng entry count, chi phí xây formatter, allocation và GC.

Với cấu hình chỉ có vài locale/pattern cố định, một `Map` nhỏ có thể hoàn toàn đủ. Với số lượng tổ hợp lớn, sử dụng cache library hỗ trợ maximum size/expiry (nếu dự án có dependency và yêu cầu rõ) thường tiện hơn viết cơ chế LRU đồng bộ từ đầu.

**Tránh cache theo `Locale.toString()` nếu sản phẩm dùng BCP 47 extensions.** Dùng `Locale` immutable trực tiếp hoặc `toLanguageTag()` khi chuẩn hóa/kiểm soát key theo yêu cầu, bảo đảm giữ những extension thực sự ảnh hưởng output.

## 20. Invalidating cache khi đổi cấu hình và nâng cấp dữ liệu

Một cache đúng tại thời điểm tạo có thể trở nên **lỗi thời (stale)** sau khi:

- Sửa pattern ngày/số trong cấu hình triển khai.
- Thay đổi chính sách rounding/currency.
- Người dùng đổi locale hoặc timezone.
- Bộ bản dịch được reload.
- Deploy JDK mới với dữ liệu CLDR/locale cập nhật.
- Cập nhật timezone database (tzdb) hoặc thay quy tắc lịch.

Đừng lấy một key `Locale` cố định nhưng factory đọc trực tiếp `globalConfig.getPattern()` rồi cho rằng entry tự refresh khi pattern đổi. Có thể:

- Đưa `pattern/version/configRevision` vào key.
- Gắn cache với lifecycle của cấu hình và **clear/rebuild** khi thay đổi.
- Tạo cache mới cho mỗi phiên bản cấu hình.
- Giới hạn TTL khi phù hợp, nhưng TTL **không thay thế** yêu cầu tính đúng tức thời nếu nghiệp vụ cần.

Các cache formatter built dưới JDK này không nên được serialize thành dữ liệu bền vững hoặc dùng làm nền tảng cho identity/sort key mà không có versioning. Ví dụ locale collation có thể thay đổi theo JDK/provider; khi thay đổi cần rebuild index hoặc regression test.

Với `ZoneId`, khả năng tính thời gian tương lai phụ thuộc tzdb được runtime cung cấp; nên test các ngày DST nhạy cảm sau khi thay bản JDK. Không giả định một cache immutable có thể “tự cập nhật dữ liệu tzdb” khi runtime đang chạy mà không có cơ chế rõ.

## 21. Cache key và dữ liệu mặc định: tránh phụ thuộc vào global state

Ví dụ không nên thiết kế factory như sau:

```java
DecimalFormat createFormatter() {
    Locale locale = Locale.getDefault();
    return (DecimalFormat)
            NumberFormat.getNumberInstance(locale);
}
```

Đây là mảnh code không có class/import, chỉ để minh họa. Kết quả phụ thuộc global default locale của JVM. Nếu key cache không ghi locale thực tế hoặc môi trường thay default locale, các call tương lai có thể dùng sai entry.

Lựa chọn rõ ràng hơn:

```java
DecimalFormat createFormatter(Locale locale) {
    return new DecimalFormat(
            "#,##0.00",
            DecimalFormatSymbols.getInstance(locale));
}
```

Với timezone cũng vậy: `ZoneId.systemDefault()` nên được lấy một lần khi cấu hình có chủ đích hoặc được truyền theo yêu cầu, không được đọc ngẫu nhiên trong cache factory nơi key chỉ có locale.

Một cấu hình tốt có tính **deterministic**: cùng key và cùng data/runtime version tạo hành vi giống nhau, giúp test đơn giản và cache đáng tin.

## 22. Kiểm thử concurrency: tránh “thử 1.000 thread thấy ổn” là đủ

Không có lỗi trong một vòng stress test **không chứng minh** `SimpleDateFormat` trở thành thread-safe. Các race có thể phụ thuộc timing, JIT, lõi CPU và input.

Các test nên gồm:

- Hai request cùng locale nhưng khác pattern.
- Hai request cùng locale nhưng khác rounding mode/min-max digits.
- Hai request cùng pattern nhưng khác timezone.
- Một request clone formatter, chỉnh cấu hình và xác nhận prototype/clone khác không thay đổi.
- Số lượng request đồng thời lớn hơn số thread xử lý; kiểm tra không lẫn trạng thái.
- Parser strict vs lenient dùng cùng locale.
- Thay cấu hình cache (version/reload) khi có request đang xử lý.
- Dùng locale có dấu thập phân khác US; đừng chỉ test `12` vì khó nhìn sai locale.
- DateTimeFormatter format một instant sát nửa đêm, vì timezone khác nhau có thể dẫn tới ngày khác nhau.
- Kiểm tra Memory/metrics khi có nhiều locale tags.

### Test invariant cho clone

Ví dụ invariant có giá trị:

```text
prototype.format(1234.50) == "1,234.50"
cloneA.setMaximumFractionDigits(0)
cloneA.format(1234.50) == "1,235"
cloneB.format(1234.50) == "1,234.50"
prototype.format(1234.50) == "1,234.50"
```

Test nên dùng `BigDecimal("1234.50")` để tránh kết quả bị ảnh hưởng bởi biểu diễn nhị phân khi thử các điểm làm tròn.

### Test invariant cho immutable cache

Với `DateTimeFormatterCacheDemo`:

```text
local=01/03/2024 07:00
utc=01/03/2024 00:00
sameObj=true
cacheSize=2
```

Một formatter cache đúng không được trộn các zone hoặc trả lại pattern bị request khác sửa. Test này không cần chạy đồng thời để kiểm chứng rằng **key đã chứa zone** và formatter được reuse đúng.

## 23. Benchmark đúng chỗ, không tối ưu bằng cảm giác

Chọn cache vì số liệu, không phải vì formatter “trông nặng”:

- **Throughput:** số operations/s khi dùng per-call creation, clone prototype hoặc cached immutable formatter.
- **Latency:** phân vị p95/p99 dưới tải đa luồng thực.
- **Allocation:** số byte được phân bổ cho formatter mới/clone.
- **GC pressure:** chi phí thu gom tăng hay giảm.
- **Cache hit ratio:** tỷ lệ các requests dùng lại cùng cấu hình.
- **Memory retained:** số entry và đối tượng con sống lâu.
- **Contention:** synchronized shared instance có làm nghẽn pipeline không?

Để benchmark Java tương đối tin cậy, thường sử dụng JMH thay vì đo một vòng lặp đơn giản bằng `System.nanoTime()` mà không warmup/kiểm soát JIT. Kết quả cần chạy trên cùng version JDK, cùng tập locale và workload đại diện.

**Một cache có thể làm chương trình chậm hoặc tốn RAM hơn** nếu key đa dạng, ít hit, nhiều eviction hoặc mỗi entry có cấu trúc phức tạp. Cache prototype còn clone theo request, nên không đạt lợi ích “không cấp phát formatter”; chỉ giảm một phần chi phí thiết lập.

## 24. Quy tắc thiết kế gợi ý theo tình huống

| Tình huống | Hướng tiếp cận ưu tiên |
|---|---|
| Vài số cần format trong một request | Tạo `DecimalFormat` mới; dùng tuần tự trong request |
| Nhiều số cùng cấu hình trong một request | Dùng một formatter của request, không share ngoài request |
| Pattern/locale lặp lại nhiều, creation costly | Cache prototype và `clone()` trước sử dụng |
| Legacy date formatter bắt buộc | Tạo/clone hoặc ThreadLocal cấu hình cố định; test |
| Ngày giờ dùng `java.time` | Cache/share `DateTimeFormatter` immutable |
| Collator cho sort nhiều locale | Cache rule/prototype theo locale + strength + decomposition, clone nếu cần sửa |
| Input mang pattern không tin cậy | Validate allowlist, tránh unbounded cache |
| Thay cấu hình runtime | Version key hoặc rebuild/clear cache |
| Nhiều request đồng thời | Không trả formatter mutable chia sẻ không đồng bộ |
| Thực sự cần maximal throughput | Benchmark, cân nhắc bounded cache và metrics |

Một lựa chọn “an toàn nhất” không nhất thiết là “ít object nhất”. Hướng tiếp cận lý tưởng là **giảm chia sẻ mutable state**, sau đó tối ưu phần thực sự nóng theo số liệu.

## 25. Những lỗi phổ biến

1. **`ConcurrentHashMap` là thread-safe nên `DecimalFormat` bên trong cũng thread-safe.** Sai: safety của map và value là hai vấn đề.
2. **Cache chỉ theo locale dù formatter khác pattern.** Có thể trả kết quả sai trong cùng ngôn ngữ.
3. **Trả prototype mutable trực tiếp.** Caller có thể sửa cấu hình và phá request khác.
4. **Đổi timezone của `SimpleDateFormat` chung cho từng request.** Dễ lẫn ngữ cảnh và gây race.
5. **Dùng một `static SimpleDateFormat` không đồng bộ.** Không an toàn khi format/parse đồng thời.
6. **Giả định ThreadLocal tự thay locale theo user.** Thread pool tái sử dụng thread; config có thể còn sót.
7. **Dùng pattern/currency/user input không giới hạn làm key.** Cache có nguy cơ tăng vô hạn.
8. **Coi `DateTimeFormatter` mutable và clone/synchronize vô ích.** Nó immutable/thread-safe, có thể chia sẻ trực tiếp.
9. **Nhầm builder và formatter.** `DateTimeFormatterBuilder` có trạng thái; kết quả `toFormatter` mới bất biến.
10. **Bỏ `ResolverStyle` khỏi cache key parse ngày.** Có thể vô tình nhận parser SMART thay STRICT.
11. **Không ghi timezone trong cache key ngày giờ.** Hai người dùng khác zone có thể nhận cùng local time sai.
12. **Cho rằng locale xác định luôn currency và timezone.** Hai lựa chọn này không đồng nhất.
13. **Mutate comparator `Collator` khi `TreeMap` đang dùng nó.** Có thể làm hỏng tính nhất quán của cấu trúc cây.
14. **Đổi pattern của `MessageFormat` cached mà không quản lý version.** Bản dịch và output có thể sai.
15. **Dùng `Locale.setDefault` cho mỗi request.** Thay global state và ảnh hưởng các thread khác.
16. **Chỉ benchmark một thread.** Có thể bỏ qua contention và chi phí đồng bộ.
17. **Quên invalidation khi đổi config/JDK/tzdb.** Cache giữ hành vi cũ.
18. **Lấy `new Date()`/`Instant.now()` làm test cố định.** Kết quả không ổn định và che lỗi timezone.
19. **Nhầm một cache hit với bảo đảm đúng ngữ nghĩa.** Cache đúng là cache có key đủ, lifecycle đúng và không rò mutable state.
20. **Tối ưu hóa trước khi kiểm chứng chức năng locale.** Một output nhanh nhưng sai dấu số/ngày giờ vẫn là lỗi.

## 26. Tự kiểm tra kiến thức

**Câu 1.** Vì sao `ConcurrentHashMap<Locale, DecimalFormat>` chưa đủ để format an toàn giữa nhiều thread?  
**Đáp án:** Map bảo đảm thao tác cache, nhưng `DecimalFormat` là đối tượng mutable và không được bảo đảm thread-safe khi dùng chung.

**Câu 2.** Khác biệt giữa cache prototype và cache instance dùng chung là gì?  
**Đáp án:** Cache prototype giữ một bản mẫu chỉ đọc và trả `clone()` cho caller; cache instance dùng chung trả cùng đối tượng mutable, dễ bị sửa/tranh chấp.

**Câu 3.** Với cache `DateTimeFormatter`, có cần clone trước mỗi `format()` không?  
**Đáp án:** Không. `DateTimeFormatter` immutable và thread-safe; có thể trả instance trong cache trực tiếp.

**Câu 4.** Tại sao cùng `Locale.US` vẫn cần hai entry cho hai timezone?  
**Đáp án:** Cùng instant ở hai timezone có thể tương ứng với giờ/ngày địa phương khác nhau.

**Câu 5.** `ThreadLocal<SimpleDateFormat>` có tự bảo đảm locale request không bị lẫn nhau?  
**Đáp án:** Không. Thread pool có thể chạy nhiều request theo thứ tự trên cùng thread; nếu instance bị sửa theo request mà không reset chính xác, cấu hình sẽ rò sang request sau.

**Câu 6.** Cache key nên chứa những gì?  
**Đáp án:** Tất cả thông tin ảnh hưởng hành vi format/parse của entry: locale, pattern, rounding, timezone, currency, digits, resolver và những lựa chọn khác tùy loại formatter.

**Câu 7.** Cần xử lý thế nào nếu ứng dụng cho phép hàng nghìn pattern từ user?  
**Đáp án:** Validate/allowlist, tránh unbounded map và cân nhắc bounded cache hoặc không cache cấu hình hiếm.

**Câu 8.** Nếu có `SimpleDateFormat` chung nhưng mọi lời gọi `format` nằm trong synchronized, còn `setTimeZone` nằm ngoài, đã an toàn chưa?  
**Đáp án:** Chưa. Mọi thao tác có ảnh hưởng trạng thái cần đi theo cùng cơ chế đồng bộ.

**Câu 9.** Vì sao trong test cần format số như `1234.50` thay vì chỉ `12`?  
**Đáp án:** Số có phân nhóm và phần thập phân giúp phát hiện sai locale/pattern/rounding rõ hơn.

**Câu 10.** Khi đổi pattern triển khai mà cache key chỉ có locale, điều gì xảy ra?  
**Đáp án:** Entry cũ có thể vẫn được dùng; cần version key, cache invalidation hoặc rebuild theo cấu hình mới.

## 27. Kết luận

**Formatter mutable cần được cô lập hoặc kiểm soát đồng bộ; formatter immutable có thể chia sẻ an toàn.** Với Java 17+:

- `NumberFormat`, `DecimalFormat`, `SimpleDateFormat`, `MessageFormat` và `Collator` nên có instance riêng theo request, bản clone từ prototype hoặc chiến lược concurrency/vòng đời rõ ràng.
- `DateTimeFormatter` của `java.time` có thể được cache và dùng chung trực tiếp vì immutable/thread-safe.
- Cache key phải diễn tả **đầy đủ cấu hình ảnh hưởng output**; chỉ `Locale` thường không đủ.
- Cache cần giới hạn kích thước, invalidation/versioning và kiểm thử khi cấu hình hoặc dữ liệu locale/timezone thay đổi.
- ThreadLocal và synchronization không biến một thiết kế cache thiếu thông tin thành đúng ngữ nghĩa.
- Ưu tiên **tính đúng của dữ liệu đa ngôn ngữ**, sau đó đo lường và tối ưu đường xử lý nóng.

**Tài liệu chính thức:** [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html) · [DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html) · [DateFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DateFormat.html) · [SimpleDateFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/SimpleDateFormat.html) · [MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html) · [Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html) · [DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html) · [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html) · [ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html).
