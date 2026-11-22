# Tái sử dụng DateTimeFormatter bất biến giữa nhiều luồng trong Java

`DateTimeFormatter`, thuộc `java.time.format`, là bộ định dạng và phân tích ngày giờ được giới thiệu từ **Java 8**. Khác với một đối tượng định dạng có cấu hình thay đổi trong quá trình sử dụng, **`DateTimeFormatter` là immutable (bất biến) và thread-safe (an toàn luồng)** theo hợp đồng chính thức của Java: có thể tạo một formatter một lần, rồi cho nhiều request hoặc thread cùng gọi `format` và `parse` trên chính instance đó mà **không cần khóa** chỉ để bảo vệ formatter.

~~~java
private static final DateTimeFormatter API_TIMESTAMP =
    DateTimeFormatter.ISO_OFFSET_DATE_TIME;
~~~

Đây là đoạn **minh họa field trong một class**, cần `import java.time.format.DateTimeFormatter;`. Các luồng cùng dùng `API_TIMESTAMP` sẽ không sửa cấu hình của nó khi format hoặc parse.

Điều quan trọng là **phạm vi bảo đảm**: formatter bất biến không có nghĩa mọi đối tượng được truyền vào hoặc mọi bộ đệm đầu ra đều thread-safe. Nó cũng không biến `LocalDateTime` thành một mốc thời gian toàn cầu nếu dữ liệu thiếu offset/zone; không làm một `ArrayList` chứa kết quả parse trở thành an toàn khi nhiều luồng cùng ghi.

Bài tập trung vào **tái sử dụng formatter bất biến giữa nhiều luồng** trong phần **Định dạng ngày giờ**: nguyên tắc safe sharing; `static final`, dependency injection, các biến thể theo locale/zone, cấu hình strict parsing; so sánh formatter với builder; giới hạn của `formatTo`, mutable input và external state; thiết kế cache; ví dụ chạy đa luồng; hiệu năng, kiểm thử và lỗi phổ biến. Tất cả kiến thức/API trình bày **vẫn áp dụng trong Java hiện đại**; chương trình hoàn chỉnh chỉ sử dụng API có từ Java 8, chạy được trên JDK 17+.

## 1. Tại sao tính bất biến giúp chia sẻ formatter?

Một formatter định nghĩa các quy tắc như:

- Pattern xuất/đọc trường ngày giờ: `uuuu-MM-dd`, `dd MMM uuuu HH:mm`, `HH:mm:ssXXX`.
- Locale dùng để đọc/in chữ tháng, thứ và mẫu localized.
- ResolverStyle quy định cách chuyển các trường đã parse thành ngày giờ hợp lệ.
- Override ZoneId khi cần định dạng hoặc parse có ngữ cảnh vùng.
- DecimalStyle/Chronology khi ứng dụng dùng quy tắc phù hợp.

Khi đối tượng định dạng **mutable**, một thread có thể chỉnh cấu hình đúng lúc thread khác đang dùng nó; kết quả sẽ phụ thuộc vào thứ tự truy cập và có thể phát sinh race condition.

`DateTimeFormatter` có thiết kế ngược lại. Sau khi tạo, cấu hình một instance là bất biến. Các phương thức xử lý có thể sử dụng dữ liệu tạm nội bộ theo **từng lời gọi**, nhưng không khiến thread khác thấy formatter bị thay đổi. Java API tuyên bố rõ class này **immutable and thread-safe**. Nhờ đó:

1. Thread A có thể format một `OffsetDateTime`.
2. Thread B có thể parse một `String` theo cùng formatter.
3. Thread C có thể format một `Instant` (nếu formatter có đủ zone/field thích hợp).
4. Không cần bọc **chính các lời gọi formatter** trong `synchronized`.

~~~java
DateTimeFormatter fmt =
    DateTimeFormatter.ISO_LOCAL_DATE;

String x = fmt.format(LocalDate.of(2024, 2, 29));
LocalDate y = LocalDate.parse("2024-02-29", fmt);
~~~

Đây là mã minh họa, cần imports `LocalDate` và `DateTimeFormatter`. Dù hai câu lệnh được chạy từ nhiều thread, cùng một formatter có thể dùng lại an toàn.

**Lưu ý:** điều này không phải cam kết “một instance formatter chỉ tạo một đối tượng tạm trên JVM” hoặc “không có cấp phát bộ nhớ”. API cam kết **tính đúng và an toàn luồng của formatter**, không cam kết số allocations, locks nội bộ hay mức speedup cố định.

## 2. Mô hình tái sử dụng phổ biến: `private static final`

Một định dạng ổn định dùng trên nhiều request nên được khai báo **một lần**:

~~~java
public final class TimestampFormats {
    private TimestampFormats() {
    }

    public static final DateTimeFormatter WIRE =
        DateTimeFormatter.ISO_OFFSET_DATE_TIME;

    public static final DateTimeFormatter DATE =
        DateTimeFormatter
            .ofPattern("uuuu-MM-dd", Locale.ROOT)
            .withResolverStyle(ResolverStyle.STRICT);

    public static final DateTimeFormatter DISPLAY_HCM =
        DateTimeFormatter
            .ofPattern("dd MMM uuuu HH:mm", Locale.ENGLISH)
            .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
}
~~~

Đây là **đoạn minh họa về class tiện ích**; cần import `java.time.ZoneId`, `java.time.format.DateTimeFormatter`, `ResolverStyle` và `java.util.Locale`.

### Ý nghĩa của ba phần

- **`static`:** dùng chung formatter ở cấp lớp. Không cần mỗi request tạo lại cùng pattern.
- **`final`:** không được gán lại reference field sau khi khởi tạo. `final` giúp truyền đạt ý định cấu hình ổn định và tham gia cơ chế công bố field qua quá trình khởi tạo lớp.
- **Đối tượng `DateTimeFormatter`:** bản thân formatter đã immutable/thread-safe theo hợp đồng; **không phải chỉ vì field được gắn `final` mà đối tượng tùy ý nào cũng tự an toàn luồng**.

Java đảm bảo quá trình khởi tạo lớp được đồng bộ theo quy tắc JVM, nên tham chiếu được tạo đúng trong `static final` có cơ chế **safe publication** phù hợp cho các luồng sử dụng sau khi class được khởi tạo.

Nếu formatter là cấu hình runtime thay đổi theo tenant/request, không bắt buộc ép tất cả về `static final`. Ta có thể tạo phiên bản phù hợp, giữ trong cấu hình immutable, tiêm qua constructor, hoặc cache an toàn. Nhưng đừng biến một **formatter dùng chung** thành object mutable: nó vẫn immutable, chỉ có **reference bao quanh** là thứ cần quản lý nếu có thể thay đổi.

## 3. Dùng hằng formatter ISO để tránh tạo pattern lại

Java cung cấp nhiều formatter dựng sẵn, chẳng hạn:

| Hằng | Ví dụ chuỗi | Kiểu thường dùng |
| --- | --- | --- |
| `ISO_LOCAL_DATE` | `2024-02-29` | `LocalDate` |
| `ISO_LOCAL_TIME` | `09:30:45` | `LocalTime` |
| `ISO_LOCAL_DATE_TIME` | `2024-02-29T09:30:45` | `LocalDateTime` |
| `ISO_OFFSET_DATE_TIME` | `2024-02-29T09:30:45+07:00` | `OffsetDateTime` |
| `ISO_ZONED_DATE_TIME` | `2024-02-29T09:30:45+07:00[Asia/Ho_Chi_Minh]` | `ZonedDateTime` |
| `ISO_INSTANT` | `2024-02-29T02:30:45Z` | `Instant` |
| `BASIC_ISO_DATE` | `20240229` | `LocalDate` |

Các hằng này là **formatter immutable** đã được định nghĩa sẵn. Có thể chuyển thẳng chúng vào service:

~~~java
private static final DateTimeFormatter ISO =
    DateTimeFormatter.ISO_OFFSET_DATE_TIME;

public String encode(OffsetDateTime value) {
    return ISO.format(value);
}

public OffsetDateTime decode(String text) {
    return OffsetDateTime.parse(text, ISO);
}
~~~

Đây là đoạn minh họa một phần class. Hợp đồng về thời điểm vẫn phải rõ: `ISO_LOCAL_DATE_TIME` **không cung cấp offset**, còn `ISO_OFFSET_DATE_TIME` có offset cụ thể. Không phải cứ dùng formatter tên ISO là Java có thể xác định duy nhất một instant.

**Lưu ý về giao thức bên ngoài:** `ISO_ZONED_DATE_TIME` có thể xuất phần `[Region/City]`, một phần mở rộng ISO-like của Java. Không mặc định mọi hệ thống chỉ hỗ trợ ISO-8601 thuần đều đọc phần này. Việc tái sử dụng formatter không thay thế thỏa thuận schema giữa các dịch vụ.

## 4. Các phương thức `with...` trả formatter mới, không sửa bản chia sẻ

Một nhầm lẫn rất dễ tạo bug là nghĩ `withLocale` hoặc `withZone` sửa cấu hình **đang dùng chung**. Trong thực tế, chúng **trả về một formatter khác về mặt cấu hình**, instance gốc không bị thay đổi.

~~~java
DateTimeFormatter base =
    DateTimeFormatter
        .ofPattern("dd MMM uuuu HH:mm", Locale.ENGLISH)
        .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

DateTimeFormatter utc =
    base.withZone(ZoneOffset.UTC);
~~~

Ở đây:

- `base` tiếp tục hiển thị theo `Asia/Ho_Chi_Minh`.
- `utc` có override zone `UTC`.
- Nếu nhiều thread đang dùng `base` thì thao tác tạo `utc` **không gây một thay đổi cấu hình bất ngờ** đối với các thread đó.
- Cả hai formatter đều immutable và có thể được chia sẻ độc lập.

Các nhóm method tương tự:

| Phương thức | Biến thể được trả về | Ảnh hưởng đến formatter cũ |
| --- | --- | --- |
| `withLocale(locale)` | Formatter với locale khác | Không sửa |
| `withZone(zone)` | Formatter với override zone khác | Không sửa |
| `withResolverStyle(style)` | Formatter với quy tắc resolve khác | Không sửa |
| `withChronology(chrono)` | Formatter với chronology override | Không sửa |
| `withDecimalStyle(decimalStyle)` | Formatter với cách biểu diễn chữ số phù hợp | Không sửa |
| `withResolverFields(fields)` | Formatter giới hạn các trường dùng khi resolve | Không sửa |

### Đừng bỏ qua kết quả của `with...`

~~~java
DateTimeFormatter english =
    DateTimeFormatter.ofPattern("dd MMM uuuu", Locale.ENGLISH);

english.withLocale(Locale.FRENCH); // Kết quả bị bỏ đi.

// english VẪN mang Locale.ENGLISH.
~~~

Cách đúng:

~~~java
DateTimeFormatter french =
    english.withLocale(Locale.FRENCH);
~~~

Bất biến không có nghĩa mọi formatter luôn “mới theo reference”. Với cấu hình không thay đổi, implementation có thể trả cùng instance; **không kiểm tra `==` để suy ra thay đổi thành công**. Kiểm tra `getLocale()`, `getZone()`, `getResolverStyle()` hoặc hành vi format/parse tương ứng.

### `withLocale` không đồng nghĩa đổi toàn bộ chronology/timezone

`withLocale` chủ yếu tác động đến thông tin bản địa hóa của formatter (ví dụ tên tháng, mẫu localized). Nó không tự biến một `Instant` thành giờ Paris hoặc làm mọi field được sửa theo một lịch tùy ý. Với zone, dùng `withZone` hoặc chuyển temporal qua `atZone`. Có thêm các API bản địa hóa chuyên biệt trên JDK mới, nhưng **không cần chúng để hiểu hoặc dùng đúng `DateTimeFormatter` của Java 8**.

## 5. Formatter bất biến không có nghĩa chuỗi đầu vào và output buffer đều an toàn

### 5.1. `format(temporal)` trả một `String` riêng cho lời gọi

~~~java
String text = formatter.format(temporal);
~~~

Đây là mã minh họa, giả sử `formatter`/`temporal` hợp lệ. `String` là immutable; các lời gọi riêng biệt không yêu cầu các thread phải chia sẻ một bộ đệm đầu ra mutable.

### 5.2. `formatTo(temporal, Appendable)` ghi vào đối tượng do caller đưa vào

API hỗ trợ:

~~~java
StringBuilder out = new StringBuilder();
formatter.formatTo(temporal, out);
~~~

`StringBuilder` **không thread-safe** nếu các thread cùng append vào một instance. `DateTimeFormatter.formatTo` có thể được gọi song song trên **cùng formatter**, nhưng nếu hai thread ghi đồng thời vào **cùng `StringBuilder`**, kết quả có thể sai hoặc bị lẫn văn bản.

**Phản ví dụ:**

~~~java
// SHARED_FORMATTER là DateTimeFormatter hợp lệ,
// nhưng SHARED_BUILDER bị nhiều thread cùng append.
private static final StringBuilder SHARED_BUILDER =
    new StringBuilder();

void unsafe(LocalDate day) {
    SHARED_FORMATTER.formatTo(day, SHARED_BUILDER);
}
~~~

Đoạn trên chỉ minh họa ý tưởng, chưa có khai báo `SHARED_FORMATTER`; không phải class chạy độc lập.

**Cách đúng:** tạo `StringBuilder` cục bộ trong từng lời gọi, truyền buffer độc lập, hoặc dùng trực tiếp `format`:

~~~java
String result = formatter.format(day);

// Hoặc nếu cần nhiều phần vào một buffer:
StringBuilder local = new StringBuilder();
formatter.formatTo(day, local);
String resultFromBuffer = local.toString();
~~~

Một callback format được gọi từ nhiều luồng có thể cùng tái sử dụng formatter; **đối tượng mutable do caller sở hữu vẫn cần quy tắc riêng**.

### 5.3. Input CharSequence mutable cũng cần được kiểm soát

`parse(CharSequence)` nhận `CharSequence`, không bắt buộc là `String`. Nếu một thread thay nội dung `StringBuilder` trong lúc thread khác parse nó, formatter không biến quá trình đọc dữ liệu đang thay đổi thành an toàn.

~~~java
// Cần snapshot input nếu nguồn là dữ liệu mutable chia sẻ:
String stableInput = sharedBuilder.toString();

LocalDate result =
    LocalDate.parse(stableInput, DateTimeFormatter.ISO_LOCAL_DATE);
~~~

Đây là minh họa; `sharedBuilder` được tạo ở nơi khác. **Quan trọng:** chính thao tác lấy snapshot `toString()` cũng phải được phối hợp đúng nếu có writer concurrent, nếu không nội dung snapshot vẫn có thể không nhất quán. An toàn nhất là nhận `String` bất biến đã hoàn tất từ ranh giới I/O hoặc sao chép trong một cơ chế đồng bộ phù hợp.

## 6. Bất biến của formatter khác với trạng thái mutable trong ứng dụng

Hãy tách các tầng:

1. **Formatter:** immutable, thread-safe.
2. **Giá trị ngày giờ chuẩn:** `LocalDate`, `LocalDateTime`, `OffsetDateTime`, `Instant` đều immutable và thread-safe.
3. **Container/biến chứa dữ liệu:** `ArrayList`, `HashMap` mutable, biến tham chiếu có thể gán lại, cache không đồng bộ... có thể **không thread-safe**.
4. **Logic nghiệp vụ và I/O:** database, file, log, queue, gửi email... có hợp đồng concurrency riêng.

Ví dụ **không an toàn**:

~~~java
List<String> results = new ArrayList<>();

// Nếu nhiều thread cùng dùng results:
results.add(DateTimeFormatter.ISO_LOCAL_DATE.format(date));
~~~

Formatter vẫn an toàn; thao tác `results.add` trên cùng `ArrayList` có thể không an toàn. Dùng cơ chế thu thập kết quả theo task, `Future`, thread-safe queue, collector phù hợp hoặc khóa đúng cách.

Một trường hợp khác:

~~~java
private static DateTimeFormatter current =
    DateTimeFormatter.ISO_LOCAL_DATE;

// Một thread:
current = DateTimeFormatter.ofPattern("dd/MM/uuuu");

// Các thread khác đọc current.
~~~

Đây là mô hình dùng **reference có thể đổi** giữa nhiều luồng. Formatter cũ và formatter mới đều immutable, nhưng việc **công bố, thời điểm thay và chính sách nhất quán của biến `current`** phải được thiết kế. Nếu cần thay cấu hình đồng thời, dùng `volatile`/`AtomicReference<DateTimeFormatter>`/cấu hình immutable thay thế nguyên tử hoặc khóa theo yêu cầu, thay vì nghĩ tính immutable tự bảo vệ phép gán reference.

Ngay cả `volatile` cũng không làm một workflow nhiều bước thành transaction. Nếu mỗi request cần một version cấu hình nhất quán, **lấy một snapshot formatter reference ở đầu request** rồi dùng biến cục bộ xuyên suốt request, thay vì đọc biến global nhiều lần và có thể nhận hai version.

## 7. `DateTimeFormatterBuilder` là mutable builder, không chia sẻ lúc cấu hình

`DateTimeFormatterBuilder` cũng thuộc `java.time.format` nhưng **khác hẳn `DateTimeFormatter`**:

- Builder **mutable**, dùng để lắp parser/printer theo các bước.
- Tài liệu Oracle nói builder dành cho **một luồng trong giai đoạn tạo cấu hình**.
- Sau `toFormatter()`, kết quả `DateTimeFormatter` là **immutable và thread-safe** và có thể chia sẻ giữa nhiều thread.

~~~java
DateTimeFormatter fmt =
    new DateTimeFormatterBuilder()
        .appendPattern("uuuu/MM/dd")
        .toFormatter(Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
~~~

Đây là mã minh họa; cần imports `DateTimeFormatter`, `DateTimeFormatterBuilder`, `ResolverStyle` và `Locale`. Có thể đặt `fmt` ở `private static final` sau khi xây xong.

**Không chia sẻ một builder đang gọi `append...` ở nhiều request**:

~~~java
// Thiết kế cần tránh:
private static final DateTimeFormatterBuilder SHARED_BUILDER =
    new DateTimeFormatterBuilder();

// Nhiều thread cùng gọi SHARED_BUILDER.appendPattern(...)
// không có hợp đồng thread-safe.
~~~

`final` ở đây chỉ làm reference builder không bị gán lại, **không làm builder mutable thành immutable**. Đây là bài học bao quát: **phải đọc hợp đồng của class**, không chỉ tên package hoặc cách khai báo field.

Nếu builder chỉ cần lắp cấu hình một lần trong static initializer/class constructor rồi chuyển thành `DateTimeFormatter`, đây là cách dùng đúng. Không cần giữ lại builder để tiếp tục append trong lúc formatter đã được công bố.

## 8. Dùng đúng formatter cho kiểu ngày giờ đang có

Tính thread-safe không thể sửa lỗi thiếu trường dữ liệu.

### 8.1. Ngày/giờ cục bộ không có offset

~~~java
LocalDateTime local =
    LocalDateTime.of(2024, 2, 29, 9, 30, 45);

String text =
    DateTimeFormatter.ISO_LOCAL_DATE_TIME.format(local);
// "2024-02-29T09:30:45"
~~~

`LocalDateTime` không mang zone/offset. Nếu gọi:

~~~java
// Phản ví dụ: local không chứa offset để xuất.
DateTimeFormatter.ISO_OFFSET_DATE_TIME.format(local);
~~~

API có thể ném `DateTimeException` do thiếu field offset; đây không phải race condition. Muốn một timestamp có offset, phải **có thông tin offset/ZoneId thực**, ví dụ gắn local với `ZoneId.of("Asia/Ho_Chi_Minh")` theo quy tắc nghiệp vụ.

### 8.2. Format `Instant` thành giờ địa phương cần ZoneId

`Instant` mang một mốc trên dòng thời gian, nhưng **không chứa các trường ngày-giờ địa phương** theo region. Formatter pattern như `"uuuu-MM-dd HH:mm"` thường cần một override zone hoặc đầu vào `ZonedDateTime`.

~~~java
Instant instant =
    Instant.parse("2024-02-29T02:30:45Z");

DateTimeFormatter inHcm =
    DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm", Locale.ROOT)
        .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(inHcm.format(instant));
// 2024-02-29 09:30
~~~

`withZone` cung cấp vùng cho phép chuyển `Instant` sang các trường local khi format. Tính bất biến giúp các thread dùng formatter chung và cùng zone một cách ổn định; nó **không** khiến các múi giờ khác nhau có thể bị đổi tùy tiện trên cùng instance. Muốn hiển thị UTC, tạo một formatter riêng bằng `inHcm.withZone(ZoneOffset.UTC)`.

### 8.3. Không dùng formatter để thay chính sách DST

`ZoneId` vùng như `Europe/Paris` dùng quy tắc tzdb, có gap/overlap. Nếu input chỉ là `LocalDateTime`, thêm `withZone(zone)` vào formatter **không tự định nghĩa** nên chọn offset nào khi giờ địa phương mơ hồ và không làm dữ liệu có “một instant duy nhất” một cách thần kỳ. Cần một chính sách rõ về `ZoneRules.getValidOffsets`, giờ không tồn tại, giờ lặp lại và instant cố định so với giờ lịch.

Nếu ứng dụng đặt lịch tương lai phải giữ 09:00 giờ Paris theo luật vùng, lưu `LocalDateTime`, `ZoneId` và chính sách DST phù hợp; không chỉ lưu một offset mùa hè lấy từ ngày hiện tại.

## 9. ResolverStyle: một cấu hình phải nhất quán giữa các luồng

Khi parse, Java nhận các trường từ chuỗi rồi **resolve** chúng thành ngày giờ hợp lệ. `ResolverStyle` gồm:

- **`STRICT`:** kiểm tra nghiêm ngặt ngày/giờ hợp lệ.
- **`SMART`:** có thể điều chỉnh một số trường ngày theo quy tắc thông minh.
- **`LENIENT`:** cho phép những kiểu chuẩn hóa giá trị ngoài phạm vi theo quy tắc riêng.

Các formatter ISO dựng sẵn như `ISO_LOCAL_DATE` sử dụng `STRICT`. `DateTimeFormatter.ofPattern(...)` thường tạo formatter mặc định với `SMART`.

~~~java
DateTimeFormatter smart =
    DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT);

DateTimeFormatter strict =
    smart.withResolverStyle(ResolverStyle.STRICT);

LocalDate adjusted =
    LocalDate.parse("2024-02-30", smart);
// 2024-02-29

// LocalDate.parse("2024-02-30", strict)
// ném DateTimeParseException.
~~~

Điểm liên quan đến chia sẻ formatter: `strict` và `smart` là **hai cấu hình riêng bất biến**, có thể được dùng đồng thời. Tạo formatter strict **không thay đổi** việc một thread khác dùng `smart`.

Trong dữ liệu giao dịch/ngày đến hạn, nếu yêu cầu là phải từ chối ngày không tồn tại, chọn `STRICT` và unit test. Nếu yêu cầu cố ý “chỉnh về ngày cuối tháng”, nêu rõ policy SMART; đừng để một thay đổi cấu hình tình cờ tạo sai ngày trong hệ thống.

### `uuuu` khác `yyyy` và `YYYY`

- `uuuu`: proleptic year; phù hợp với ngày ISO khi parse strict không có era.
- `yyyy`: year-of-era; parse STRICT có thể cần thông tin era.
- `YYYY`: week-based-year; có thể khác năm lịch gần cuối/đầu năm.

Với ngày ISO thông dụng, `ofPattern("uuuu-MM-dd")` rõ ràng hơn `"yyyy-MM-dd"` trong trường hợp strict. Tính immutable giúp formatter cố định cách hiểu ký hiệu, nhưng **không giúp một pattern sai trở nên đúng**.

## 10. Locale và timezone: tái sử dụng theo cấu hình cụ thể

Nếu có nhiều nhóm người dùng, tránh một formatter global cố gắng thay locale theo request. Thay vào đó, dùng **một formatter cơ sở** và tạo biến thể:

~~~java
DateTimeFormatter base =
    DateTimeFormatter.ofPattern(
        "dd MMM uuuu", Locale.ENGLISH);

DateTimeFormatter french =
    base.withLocale(Locale.FRENCH);

DateTimeFormatter german =
    base.withLocale(Locale.GERMAN);
~~~

Các formatter này không thay đổi lẫn nhau. Có thể giữ chúng trong cấu hình bất biến hoặc cache khi số lượng biến thể được kiểm soát.

### 10.1. Locale có thể ảnh hưởng output, nhưng không phải dữ liệu cần lưu

Một ngày `LocalDate.of(2024,2,29)` có cùng giá trị khi format bằng tiếng Anh, Pháp hoặc Việt; chữ tháng hiển thị khác vì locale. Đối với giao tiếp máy–máy, nên dùng một schema ISO rõ ràng như `ISO_LOCAL_DATE` hoặc `ISO_OFFSET_DATE_TIME` thay vì giá trị phụ thuộc locale của giao diện.

### 10.2. Formatter có cấu hình cố định không cố định bản dữ liệu ngôn ngữ/tzdb của JDK

`DateTimeFormatter` immutable bảo đảm **cấu hình instance không bị sửa**; nó **không hứa** mọi phiên bản JDK, dữ liệu locale, tzdb hoặc rule múi giờ trong mọi môi trường sẽ tạo output giống hệt cho mọi ngày. Ví dụ `ofLocalizedDate(FormatStyle.LONG)` có thể dùng pattern/dữ liệu locale khác theo runtime, và một vùng có thể đổi luật DST về sau.

Với test cần output chính xác, chọn `Locale` tường minh, input cụ thể, `ZoneId` rõ ràng và kiểm chứng rules/runtime. Đừng dùng `Locale.getDefault()` hoặc `ZoneId.systemDefault()` một cách vô tình cho định dạng API cần tái lập.

### 10.3. Tạo formatter theo request có phải sai?

Không. Tạo một formatter per-request **vẫn đúng về chức năng**, nhưng nếu mỗi request lặp lại cùng một pattern/locale/zone, có thể tăng số lần xử lý pattern và cấp phát không cần thiết. Với cấu hình **động** ít dùng, tạo phiên bản trên request có thể đơn giản và an toàn hơn một cache phức tạp. Cân nhắc hiệu năng bằng số liệu thực tế chứ không tối ưu quá sớm.

## 11. Thiết kế cache formatter khi số lượng biến thể tăng

Trường hợp cố định vài formatter, dùng `static final` hoặc DI singleton. Khi ứng dụng thật sự cần nhiều tổ hợp pattern + locale + zone + resolver style, có thể xây một cache nhỏ:

~~~java
ConcurrentMap<Locale, DateTimeFormatter> formats =
    new ConcurrentHashMap<>();

DateTimeFormatter forLocale(Locale locale) {
    return formats.computeIfAbsent(
        locale,
        key -> DateTimeFormatter.ofPattern(
            "dd MMM uuuu", key)
    );
}
~~~

Đây là đoạn **minh họa một phần class**, cần imports `ConcurrentMap`, `ConcurrentHashMap`, `Locale` và `DateTimeFormatter`. Mỗi giá trị cache là immutable nên sau khi công bố, các thread có thể cùng format/parse. `ConcurrentHashMap.computeIfAbsent` phối hợp việc gắn formatter cho một key để tránh “check rồi put” thiếu nguyên tử.

### Tránh thiết kế cache có khóa không đủ thông tin

Nếu formatter phụ thuộc **pattern, locale, zone, resolver style**, chỉ dùng key là locale thì kết quả có thể sai. Thiết kế key bất biến (value object) chứa toàn bộ cấu hình cần phân biệt.

Không cache không giới hạn các pattern tự do do người dùng gửi nếu tập giá trị có thể tăng mãi; cân nhắc giới hạn cardinality, kiểm soát input, eviction và đo bộ nhớ. Những kỹ thuật như LRU hay thư viện cache chuyên dụng chỉ dùng khi workload thực sự cần, không phải mặc định cho vài hằng ISO.

### Đừng cho side effect vào mapping function

Hàm tạo formatter nên **thuần và nhẹ**; không làm I/O, thanh toán hoặc sửa một shared state bên ngoài. API cache có thể được thay implementation, và remapping callbacks ở những cấu trúc concurrent khác nhau có hợp đồng khác nhau về retry. Cần tách việc parse pattern ra khỏi logic nghiệp vụ khó lặp.

**Đơn giản nhất** vẫn là `private static final` khi schema không đổi. `ConcurrentHashMap` không tự làm một thiết kế cache thiếu chính sách locale/zone trở nên đúng.

## 12. Ví dụ Java hoàn chỉnh: dùng chung formatter với 6 luồng

Chương trình **`SharedDateTimeFormatterDemo.java`** dưới đây có các đặc điểm:

1. Dùng **cùng một instance `DateTimeFormatter`** để format/parse timestamp từ nhiều worker.
2. Dùng formatter strict cho ngày và formatter hiển thị theo một `ZoneId` tường minh.
3. Tạo formatter biến thể UTC bằng `withZone` mà không sửa bản HCM.
4. Chứng minh `DateTimeFormatterBuilder` chỉ dùng ở thời điểm cấu hình rồi trả formatter bất biến.
5. Dùng `CountDownLatch` để các worker cùng bắt đầu; dùng `Future.get()` để chờ hoàn tất và nhận exception; không cho nhiều worker ghi vào một `ArrayList` kết quả chung.
6. Dữ liệu đầu vào cố định nên output kiểm thử không phụ thuộc đồng hồ hiện tại hoặc thứ tự thread hoàn thành.

Mọi API trong chương trình có từ Java 8; có thể chạy trên JDK 17+.

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class SharedDateTimeFormatterDemo {
    private static final int WORKERS = 6;
    private static final int PER_WORKER = 400;

    private static final ZoneId BUSINESS_ZONE =
            ZoneId.of("Asia/Ho_Chi_Minh");

    // Formatter chung cho timestamp có UTC offset.
    private static final DateTimeFormatter API =
            DateTimeFormatter.ISO_OFFSET_DATE_TIME;

    // Cấu hình rõ ràng, từ chối ngày không tồn tại.
    private static final DateTimeFormatter STRICT_DATE =
            DateTimeFormatter
                    .ofPattern("uuuu-MM-dd", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    // Formatter hiển thị chung, zone và locale cố định.
    private static final DateTimeFormatter DISPLAY_HCM =
            DateTimeFormatter
                    .ofPattern(
                        "dd MMM uuuu HH:mm", Locale.ENGLISH)
                    .withZone(BUSINESS_ZONE);

    // withZone trả một formatter mới, không sửa DISPLAY_HCM.
    private static final DateTimeFormatter DISPLAY_UTC =
            DISPLAY_HCM.withZone(ZoneOffset.UTC);

    private static final DateTimeFormatter SMART_DATE =
            DateTimeFormatter
                    .ofPattern("uuuu-MM-dd", Locale.ROOT);

    // Builder chỉ được dùng trong lúc cấu hình.
    private static final DateTimeFormatter BUILT =
            new DateTimeFormatterBuilder()
                    .appendPattern("uuuu/MM/dd")
                    .toFormatter(Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    private SharedDateTimeFormatterDemo() {
    }

    public static void main(String[] args) throws Exception {
        OffsetDateTime base = OffsetDateTime.parse(
                "2024-02-29T09:30:45+07:00", API);
        Instant instant = base.toInstant();

        System.out.println("api=" + API.format(base));
        System.out.println("instant=" + instant);
        System.out.println("date="
                + STRICT_DATE.format(base.toLocalDate()));
        System.out.println("displayHcm="
                + DISPLAY_HCM.format(instant));
        System.out.println("displayUtc="
                + DISPLAY_UTC.format(instant));
        System.out.println("originalZone="
                + DISPLAY_HCM.getZone().getId());
        System.out.println("otherZone="
                + DISPLAY_UTC.getZone().getId());
        System.out.println("builder="
                + BUILT.format(base.toLocalDate()));

        System.out.println("smartAccepted="
                + LocalDate.parse("2024-02-30", SMART_DATE));

        try {
            LocalDate.parse("2024-02-30", STRICT_DATE);
            System.out.println("strictRejected=false");
        } catch (DateTimeParseException ex) {
            System.out.println("strictRejected=true");
        }

        ExecutorService pool =
                Executors.newFixedThreadPool(WORKERS);
        CountDownLatch ready = new CountDownLatch(WORKERS);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Integer>> futures = new ArrayList<>();

        try {
            for (int worker = 0; worker < WORKERS; worker++) {
                final int workerId = worker;

                Callable<Integer> task = () -> {
                    ready.countDown();
                    start.await();

                    int validated = 0;

                    for (int i = 0; i < PER_WORKER; i++) {
                        OffsetDateTime candidate =
                                base.plusSeconds(
                                    (long) workerId * PER_WORKER + i);

                        // Các task dùng cùng formatter API.
                        String wire = API.format(candidate);
                        OffsetDateTime roundTrip =
                                OffsetDateTime.parse(wire, API);

                        if (!candidate.equals(roundTrip)) {
                            throw new AssertionError(
                                "OffsetDateTime round trip");
                        }

                        // Các task cũng dùng formatter hiển thị chung.
                        String display =
                                DISPLAY_HCM.format(
                                    candidate.toInstant());

                        if (!display.equals(
                                DISPLAY_HCM.format(
                                    roundTrip.toInstant()))) {
                            throw new AssertionError(
                                "Display mismatch");
                        }

                        String dateText = STRICT_DATE.format(
                                candidate.toLocalDate());

                        if (!candidate.toLocalDate().equals(
                                LocalDate.parse(
                                    dateText, STRICT_DATE))) {
                            throw new AssertionError(
                                "LocalDate round trip");
                        }
                        validated++;
                    }
                    return validated;
                };

                futures.add(pool.submit(task));
            }

            ready.await();
            start.countDown();

            int total = 0;
            for (Future<Integer> future : futures) {
                total += future.get();
            }

            System.out.println("roundTrips=" + total);
        } finally {
            start.countDown();
            pool.shutdown();
        }
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac -encoding UTF-8 SharedDateTimeFormatterDemo.java
java SharedDateTimeFormatterDemo
~~~

**Đầu ra kỳ vọng:**

~~~text
api=2024-02-29T09:30:45+07:00
instant=2024-02-29T02:30:45Z
date=2024-02-29
displayHcm=29 Feb 2024 09:30
displayUtc=29 Feb 2024 02:30
originalZone=Asia/Ho_Chi_Minh
otherZone=Z
builder=2024/02/29
smartAccepted=2024-02-29
strictRejected=true
roundTrips=2400
~~~

### Vì sao có thể tin vào output này?

- `base` dùng ngày nhuận `2024-02-29` có offset `+07:00`, nên `toInstant` là `2024-02-29T02:30:45Z`.
- `DISPLAY_HCM` dùng locale English và zone `Asia/Ho_Chi_Minh`, hiển thị 09:30; `DISPLAY_UTC` là formatter khác với zone `Z`, hiển thị 02:30 nhưng bản gốc **không đổi**.
- Builder đã được dùng xong để tạo formatter `uuuu/MM/dd`; kết quả `2024/02/29` là ngày có các trường hợp lệ.
- `SMART_DATE` có thể điều chỉnh `2024-02-30` thành `2024-02-29`, còn `STRICT_DATE` từ chối giá trị này.
- Mỗi task xử lý các offset giây khác nhau trên **cùng dữ liệu base bất biến**. `WORKERS=6`, `PER_WORKER=400` nên có **2.400 lượt round-trip**. Giá trị in ra được tổng hợp bằng `Future.get()` sau khi các task kết thúc.
- Các thread **không cùng sửa** một formatter, `StringBuilder` hay một List kết quả. `futures` chỉ được thread main cập nhật; kết quả từng task được trả qua `Future`.
- `CountDownLatch` tạo một thời điểm bắt đầu tương đối đồng thời, hữu ích để thể hiện tranh chấp khi chạy nhiều worker; nó không tự chứng minh một benchmark về tốc độ.
- Không có `now()`, timezone mặc định hoặc output ghi từ worker vào stdout. Thứ tự task hoàn tất không làm thay đổi các dòng kết quả.

**Phạm vi chứng minh:** ví dụ cho thấy cách áp dụng hợp đồng an toàn luồng trong một chương trình cụ thể. Việc chạy thành công nhiều lần không thay thế tài liệu API, không tự chứng minh ứng dụng phức tạp đã hết mọi data race.

## 13. So sánh ba cách tạo và sử dụng formatter

| Cách | Có đúng không? | Khi phù hợp | Chi phí/lưu ý |
| --- | --- | --- | --- |
| `DateTimeFormatter.ISO_*` trực tiếp | Có | Schema ISO dựng sẵn | Không cần thiết kế một pattern mới |
| `private static final DateTimeFormatter` | Có | Pattern/locale/zone dùng chung ổn định | Tạo một lần, chia sẻ mọi request |
| Formatter được tạo trong constructor và giữ ở `final` field | Có | Service có cấu hình riêng theo instance | Cấu hình bất biến, dễ tiêm và test |
| `withLocale/withZone` tạo biến thể theo yêu cầu | Có | Nhiều người dùng/vùng | Giữ biến thể nếu sử dụng lại nhiều |
| `new DateTimeFormatterBuilder()` cục bộ rồi `toFormatter()` | Có | Cần cấu hình phức tạp | Builder mutable chỉ dùng khi cấu hình |
| Tạo `ofPattern` mỗi request | Có | Cấu hình động, ít gọi | Có thể tốn tạo pattern/cấp phát không cần thiết |
| `ThreadLocal<DateTimeFormatter>` chỉ vì sợ race | Thường không cần | Hiếm có lý do khác theo ứng dụng | `DateTimeFormatter` đã thread-safe |
| Chia sẻ `DateTimeFormatterBuilder` đang bị sửa | Không nên | Không phù hợp | Builder không có bảo đảm thread-safe |

Mục tiêu là **dễ hiểu và đúng trước khi tối ưu**. Với một vài schema ổn định, hằng ISO hoặc `static final` thường đủ. Với nhiều cấu hình tenant, ưu tiên key đầy đủ, giá trị bất biến, chính sách cache hợp lý và test chính xác.

## 14. Những lỗi thường gặp khi chia sẻ formatter

### Lỗi 1 — Khóa mọi lần gọi `format`/`parse` không cần thiết

~~~java
synchronized (FORMATTER) {
    return FORMATTER.format(value);
}
~~~

Đây là phản ví dụ trong một method (giả sử FORMATTER/value đã định nghĩa). Formatter immutable đã thread-safe; `synchronized` trên một object dùng chung có thể tạo contention không cần thiết. Còn một lưu ý khác: các đối tượng value-based của java.time không nên được dùng làm khóa monitor theo identity. Nếu nghiệp vụ thực sự phải đồng bộ tài nguyên bên ngoài, khóa **tài nguyên đó** bằng một lock thích hợp, không khóa formatter một cách tùy tiện.

### Lỗi 2 — Tưởng `withZone` sửa formatter chung

~~~java
BASE.withZone(ZoneOffset.UTC);
// BASE vẫn cấu hình cũ nếu không dùng giá trị trả về.
~~~

Dùng `DateTimeFormatter utc = BASE.withZone(ZoneOffset.UTC);`. Ngược lại, đừng lo việc tạo biến thể UTC sẽ làm thread khác đang dùng BASE đổi output.

### Lỗi 3 — Dùng chung một `StringBuilder` làm output

`formatter.formatTo(value, sharedBuilder)` ghi vào đối tượng mutable do caller đưa vào. Nếu nhiều worker append cùng một builder không đồng bộ, kết quả có thể hỏng dù formatter an toàn. Dùng `formatter.format(value)` hoặc buffer riêng từng lời gọi.

### Lỗi 4 — Cùng một formatter nhưng logic parse/format sai kiểu

`ISO_OFFSET_DATE_TIME` không tự thêm offset cho `LocalDateTime`. Nếu input thiếu zone/offset, phải xác định nghiệp vụ trước. Đừng che `DateTimeException` bằng cách gắn UTC ngẫu nhiên.

### Lỗi 5 — Cho rằng `final StringBuilder`/builder tự an toàn

`final` bảo vệ việc gán lại reference, **không** bảo vệ trạng thái mutable của instance. `DateTimeFormatterBuilder` là ví dụ điển hình.

### Lỗi 6 — Dùng `yyyy` hoặc `YYYY` sai trường năm

Ở strict parsing, `yyyy` là year-of-era có thể yêu cầu era; `YYYY` là năm theo tuần, không phải năm lịch. Dùng `uuuu` khi mong muốn proleptic year của ngày ISO. Test ranh giới 31/12–01/01.

### Lỗi 7 — Dùng formatter SMART khi input phải tuyệt đối hợp lệ

`ofPattern` mặc định dùng `ResolverStyle.SMART`. Khi cần từ chối ngày 30/2, thêm `withResolverStyle(STRICT)`; các thread có thể dùng formatter strict chia sẻ mà không cần khóa.

### Lỗi 8 — Dùng Locale/Zone mặc định rồi mong output giữa các server như nhau

Cùng formatter logic nhưng kết quả hiển thị có thể khác do locale, zone, tzdb của môi trường. Với API cần đầu ra ổn định, truyền locale và zone tường minh.

### Lỗi 9 — Trông chờ tạo formatter mới trong từng request là cách tránh data race duy nhất

Đây là thói quen không cần thiết đối với `DateTimeFormatter`. Tạo lại có thể làm tăng cấp phát, nhưng cũng không sửa race condition ở `ArrayList` hoặc state nghiệp vụ dùng chung.

### Lỗi 10 — Thay một global formatter reference mà không có chiến lược đồng bộ

Cả formatter cũ và mới đều immutable; biến global `currentFormatter` được thay bởi một thread và đọc bởi các thread khác vẫn cần safe publication/visibility và chính sách nhất quán của request. Dùng cấu hình immutable, `volatile`/`AtomicReference` khi phù hợp.

### Lỗi 11 — Dùng builder mutable như singleton trên nhiều thread

Chỉ dùng `DateTimeFormatterBuilder` trong giai đoạn tạo cấu hình (thường trong một thread), gọi `toFormatter`, rồi chia sẻ formatter kết quả.

### Lỗi 12 — Cache formatter theo mỗi locale nhưng pattern/zone lại thay đổi

Key của cache phải mô tả đầy đủ các thành phần ảnh hưởng kết quả. Nếu dùng pattern không kiểm soát làm key vô hạn, cache có thể ăn bộ nhớ ngày càng nhiều.

### Lỗi 13 — Dùng custom callback/TemporalAccessor có shared mutable state

`DateTimeFormatter` có thể tương tác với `TemporalAccessor`, `TemporalQuery`, `TemporalField` hoặc logic do ứng dụng tự triển khai. Tính thread-safe của formatter chuẩn **không tự bảo đảm** một `TemporalAccessor` tùy chỉnh có trạng thái mutable cũng thread-safe. Nếu nhiều thread dùng dữ liệu tùy chỉnh, kiểm tra hợp đồng/đồng bộ của chính implementation đó.

### Lỗi 14 — Cho rằng thread-safe đảm bảo format cực nhanh trong mọi workload

Thread safety là tính đúng, **không phải benchmark**. Chi phí pattern/locale lookup, zone conversion, độ dài input, GC và contention của ứng dụng đều ảnh hưởng tốc độ. Dùng JMH nếu tối ưu là mục tiêu thực sự.

### Lỗi 15 — Không test ngày tháng biên và input sai

Bài toán concurrency chỉ là một phần. Test năm nhuận, ngày không tồn tại, giờ ranh giới 00:00/23:59, offset +/-, locale có chữ tháng, DST gap/overlap và precision nanosecond nếu cần. Tránh giả định một formatter tái sử dụng đúng về thread thì mọi schema/logic cũng đúng.

## 15. Kiểm thử concurrency và benchmark thực tế

Để kiểm thử việc dùng formatter chung, nên:

1. **Cố định cấu hình:** pattern, locale, zone, resolver style và dữ liệu đầu vào.
2. **Sử dụng cùng formatter:** các task giữ cùng reference `static final` hoặc cùng object được tiêm.
3. **Tạo input độc lập:** mỗi task có chuỗi/ngày giờ riêng hoặc dùng cùng các value immutable.
4. **Round-trip:** `parse(format(x))` phải khớp các trường được formatter biểu diễn; với ISO_OFFSET_DATE_TIME có thể so đầy đủ `OffsetDateTime.equals`.
5. **Đối chiếu kết quả:** không chỉ đếm số task, mà kiểm tra đúng nội dung format và kiểu temporal.
6. **Lặp các case biên:** ngày nhuận, giờ qua nửa đêm, offset khác nhau, lịch có DST khi dùng zone.
7. **Thu thập thread-safe:** `Future`, queue/collector phù hợp, không append vào cùng `ArrayList` hoặc `StringBuilder` thiếu đồng bộ.
8. **Lan truyền lỗi:** dùng `Future.get()` hoặc cơ chế phù hợp để test thất bại nếu task ném exception.
9. **Bảo đảm cleanup:** `shutdown()` executor sau khi kiểm thử; xử lý interruption theo chính sách ứng dụng.
10. **Không biến kiểm thử thành kết luận tốc độ:** bài test chức năng không đo được throughput và latency một cách tin cậy.

Khi cần đo hiệu năng thật, dùng **JMH** và so sánh cấu hình hợp lệ: hằng ISO, `ofPattern` mỗi lần, formatter dùng chung, và các workload với locale/zone. Đo allocations, throughput, GC và latency ở kích thước dữ liệu mục tiêu. Đừng dựa vào `System.nanoTime()` trong một vòng lặp ngắn để khẳng định formatter dùng chung nhanh hơn chính xác bao nhiêu lần.

**Điểm thiết kế quan trọng:** tái sử dụng formatter immutable có thể giảm công việc tạo cấu hình lại, nhưng mục tiêu lớn nhất là **đơn giản hóa quyền sở hữu, làm rõ schema và tránh biến động cấu hình khi nhiều thread đang dùng**.

## 16. Checklist áp dụng trong dịch vụ thực tế

- Formatter sử dụng có phải **`DateTimeFormatter`** chuẩn, không phải một builder mutable?
- Formatter có được khởi tạo một lần qua `static final`, DI singleton hoặc một cơ chế safe publication tương đương khi cần dùng chung?
- Có dùng đúng hằng ISO theo dữ liệu: local date, local datetime, offset datetime, instant?
- Pattern tùy chỉnh có được cố định và dùng đúng `uuuu`, `MM`/`mm`, `HH`, offset hay zone không?
- Locale/ZoneId có được cung cấp rõ ràng cho dữ liệu cần tái lập giữa server?
- `withLocale`, `withZone`, `withResolverStyle` có được **giữ giá trị trả về** hay bị gọi rồi bỏ?
- Nếu thay cấu hình ở runtime, có cơ chế công bố reference và chụp snapshot cấu hình theo request?
- Input có là `String` ổn định hoặc một `CharSequence` được bảo vệ đúng khi nhiều thread truy cập?
- Khi dùng `formatTo`, mỗi thread có một Appendable/`StringBuilder` riêng không?
- `TemporalAccessor` tùy chỉnh và callback do ứng dụng viết có thread-safe nếu được chia sẻ không?
- Kết quả parse/format có được gom vào một container thread-safe hay qua `Future`/collector đúng hợp đồng?
- Nếu dùng cache theo tenant/locale/zone, key có đủ thông tin và số lượng mục có được quản lý?
- Có test cả correctness và negative paths, không chỉ kiểm tra “không xảy ra exception”?
- Có tránh khóa trên formatter chỉ để format/parse khi không có tài nguyên mutable khác cần bảo vệ?
- Đã phân biệt khả năng thread-safe với hiệu năng thật, và đo bằng workload phù hợp khi cần tối ưu?
- Có nhận thức rằng thay đổi tzdb/locale data của runtime có thể tác động output hiển thị dù formatter vẫn immutable không?

**Kết luận:** `DateTimeFormatter` là **immutable và thread-safe** theo hợp đồng Java; tái sử dụng một instance qua `private static final` hoặc dependency injection là một giải pháp hiện hành, rõ ràng và phù hợp với ứng dụng đồng thời. `withZone`/`withLocale`/`withResolverStyle` tạo cấu hình khác mà không sửa bản chia sẻ. Nhưng các đối tượng **mutable bao quanh** như `StringBuilder` đầu ra, builder lúc cấu hình, collection chứa kết quả, input mutable và reference cấu hình có thể đổi **không tự trở nên thread-safe**. Chọn đúng kiểu ngày giờ, locale, zone, resolver style và kiểm thử round-trip là điều kiện quan trọng không kém tái sử dụng object.

## Tài liệu chính thức

- [Oracle Java SE 26 — DateTimeFormatter: immutable and thread-safe; format/parse; withLocale, withZone, ResolverStyle](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Oracle Java SE 26 — DateTimeFormatterBuilder: mutable builder intended for use from a single thread](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html)
- [Oracle Java SE 26 — ResolverStyle STRICT, SMART, LENIENT](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/ResolverStyle.html)
- [Oracle Java SE 26 — java.time: main date-time types immutable/thread-safe](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/package-summary.html)
- [Oracle Java SE 26 — LocalDate and OffsetDateTime](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/OffsetDateTime.html)
- [Oracle Java SE 26 — ConcurrentHashMap for an optional safe formatter cache](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
