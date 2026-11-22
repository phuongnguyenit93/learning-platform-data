# Giữ kiểm thử độc lập với `Locale` mặc định của máy chạy — Java 10+ và Java hiện đại

## 1. Vì sao cùng một bài test lại chạy đúng ở máy này nhưng thất bại ở máy khác?

Hãy xét một hàm định dạng số:

```java
static String price(double value) {
    return String.format("%,.2f", value);
}
```

Người viết kiểm thử kỳ vọng:

```java
assertEquals("1,234.50", price(1234.5));
```

Kết quả có thể đúng khi môi trường mặc định dùng cách trình bày số của Hoa Kỳ, nhưng không đúng nếu môi trường dùng quy ước dấu thập phân của Đức. Khi đó chuỗi tương ứng có thể là `1.234,50`.

**Lỗi nằm ở giả định ngầm trong test:** `String.format(String, Object...)` không nhận `Locale` tường minh và có thể phụ thuộc **Locale mặc định khi định dạng**. Test đang ngầm kiểm tra cấu hình máy của người chạy, thay vì chỉ kiểm tra logic ứng dụng.

Một vấn đề tương tự xuất hiện với chữ hoa/chữ thường:

```java
String key = "TITLE".toLowerCase();
```

Ở nhiều locale, kết quả là `title`. Nhưng trong locale tiếng Thổ Nhĩ Kỳ, chữ `I` có quy tắc viết thường đặc biệt nên `"TITLE".toLowerCase()` có thể tạo `tıtle` — ký tự thứ hai là **dotless i** (`ı`, U+0131) thay vì `i`.

Đối với khóa giao thức, mã cấu hình và tên trường kỹ thuật, đây là lỗi thật, không chỉ là khác biệt về giao diện.

**Mục tiêu bài học:** viết ứng dụng và test mà kết quả **được quyết định bởi input và quy tắc được khai báo**, chứ không phụ thuộc ngôn ngữ/vùng mặc định của máy laptop, server, CI hoặc container.

Bài thuộc chủ đề **Locale trong ứng dụng** ở module Java 10. `Locale` và các API dùng ở đây đã có từ trước Java 10 nhưng **vẫn áp dụng đầy đủ trong Java hiện đại**; không giới thiệu chúng như tính năng chỉ mới xuất hiện trong Java 10.

## 2. Mục tiêu học tập

Bạn sẽ biết cách:

1. Giải thích `Locale.getDefault()`, `Locale.getDefault(Locale.Category.FORMAT)` và `DISPLAY`.
2. Phân biệt test **logic thuần** với test vô tình kiểm tra cấu hình OS/JVM.
3. Truyền `Locale` tường minh vào `String.format`, `NumberFormat`, `DecimalFormatSymbols`, `DateTimeFormatter` và những API nhạy cảm với vùng.
4. Sử dụng `Locale.ROOT` cho thao tác kỹ thuật độc lập ngôn ngữ, đặc biệt chuẩn hóa khóa bằng `toLowerCase`/`toUpperCase`.
5. Sử dụng `Locale.US`, `Locale.GERMANY` hoặc locale nghiệp vụ phù hợp khi cần kiểm thử giao diện số.
6. Tách **Locale** khỏi **Charset**, **ZoneId/Clock** và **Currency**, tránh đưa những phụ thuộc khác vào test.
7. Parse số từ văn bản theo Locale, kiểm tra toàn bộ nội dung được tiêu thụ và dùng `BigDecimal` khi cần.
8. Test hành vi locale-aware bằng nhiều locale **không đổi trạng thái toàn JVM**.
9. Nhận diện khi nào nên test bằng literal string, khi nào nên test thuộc tính ngữ nghĩa vì CLDR/provider có thể thay đổi.
10. Cô lập và khôi phục trạng thái khi thật sự buộc phải test code cũ dùng default locale.
11. Tránh race condition khi test chạy song song; biết hướng sử dụng cơ chế khóa tài nguyên của JUnit Jupiter.
12. Chạy cùng test trên các JVM có default locale khác nhau mà không sửa source.

## 3. `Locale` là gì và khi nào có “mặc định”?

`java.util.Locale` mô tả ngôn ngữ, vùng, script và tùy chọn mở rộng có thể ảnh hưởng tới định dạng văn bản, ngày giờ, số, tên hiển thị và một số thao tác xử lý ký tự.

Ví dụ:

```java
Locale us = Locale.US;
Locale germany = Locale.GERMANY;
Locale turkish = Locale.forLanguageTag("tr-TR");
Locale neutral = Locale.ROOT;
```

Đây là đoạn minh họa trong phương thức có `import java.util.Locale`.

- `Locale.US`: tiếng Anh ở Hoa Kỳ.
- `Locale.GERMANY`: tiếng Đức ở Đức.
- `Locale.forLanguageTag("tr-TR")`: tiếng Thổ Nhĩ Kỳ tại Thổ Nhĩ Kỳ.
- `Locale.ROOT`: locale **trung lập, không gắn với ngôn ngữ hoặc vùng cụ thể**.

### Default Locale của JVM

Nếu một API không được truyền Locale, nó thường dùng một default locale thích hợp:

```java
Locale current = Locale.getDefault();
```

Default locale ban đầu được xác định khi JVM khởi động dựa trên môi trường và cấu hình hệ thống. Một ứng dụng cũng có thể thay đổi giá trị mặc định ở runtime bằng `Locale.setDefault(...)`.

**Không có bảo đảm** máy dev, CI, máy người dùng và image container sẽ có cùng Locale mặc định. Vì vậy không nên thiết kế test phụ thuộc một chuỗi tiếng Anh hoặc dấu thập phân dấu chấm chỉ vì máy của mình đang cho kết quả như vậy.

### Đọc thuộc tính một Locale

```java
Locale locale = Locale.forLanguageTag("de-DE");
System.out.println(locale.getLanguage()); // de
System.out.println(locale.getCountry());  // DE
```

Một Locale là **dữ liệu cấu hình quy ước**, không phải một biến toàn cục bắt buộc. Hầu hết logic có thể nhận Locale như một tham số, thay vì tự lấy mặc định.

## 4. Không có một default locale duy nhất cho mọi hoạt động

Từ Java 7, Java phân biệt hai category:

- `Locale.Category.FORMAT`: mặc định dùng cho những công việc như định dạng số, ngày giờ và tiền tệ.
- `Locale.Category.DISPLAY`: mặc định dùng cho tên hiển thị của locale/ngôn ngữ/vùng trong giao diện.

Đọc chúng riêng biệt:

```java
Locale base = Locale.getDefault();
Locale formatting = Locale.getDefault(Locale.Category.FORMAT);
Locale display = Locale.getDefault(Locale.Category.DISPLAY);
```

Trên một số máy, chúng có thể giống nhau; trên máy khác, **các category có thể khác nhau** theo cấu hình.

Ví dụ:

```java
Locale.setDefault(Locale.Category.FORMAT, Locale.GERMANY);
Locale.setDefault(Locale.Category.DISPLAY, Locale.US);
```

Đây là **mã minh họa thao tác global state**, **không khuyến khích chạy tùy tiện trong bộ test song song**. Nó khiến API định dạng không nhận Locale sử dụng quy tắc FORMAT kiểu Đức, còn API hiển thị tên không nhận Locale sử dụng DISPLAY kiểu Mỹ.

### API thường dùng category nào?

| API | Khi không chỉ định Locale | Cách tránh phụ thuộc |
| --- | --- | --- |
| `NumberFormat.getNumberInstance()` | Default `FORMAT` | `getNumberInstance(locale)` |
| `NumberFormat.getCurrencyInstance()` | Default `FORMAT` | `getCurrencyInstance(locale)` |
| `String.format("%,.2f", n)` | Default locale cho formatting | `String.format(locale, "%,.2f", n)` |
| `Locale.GERMANY.getDisplayCountry()` | Default `DISPLAY` | `getDisplayCountry(locale)` |
| `"TITLE".toLowerCase()` | `Locale.getDefault()` không có category | `toLowerCase(Locale.ROOT)` cho khóa kỹ thuật |
| `"title".toUpperCase()` | `Locale.getDefault()` không có category | `toUpperCase(Locale.ROOT)` cho khóa kỹ thuật |
| `DateTimeFormatter.ofPattern("MMMM")` | Locale FORMAT mặc định khi tạo formatter | `ofPattern("MMMM", locale)` |

**Tính chất quan trọng:** `Locale.setDefault(locale)` (overload không category) đặt lại **default cơ sở và cả hai default category**. Ngược lại, `Locale.setDefault(Category.FORMAT, locale)` chỉ đặt mặc định cho category tương ứng. Vì vậy test chỉ nhớ một giá trị `Locale.getDefault()` có thể **không đủ để khôi phục đầy đủ trạng thái category** nếu đã chỉnh riêng FORMAT/DISPLAY.

## 5. Quy tắc thiết kế ưu tiên: truyền Locale như một input tường minh

Hàm có phụ thuộc văn hóa vùng nên nhận Locale như một đối số hoặc dependency được cấu hình:

```java
static String formatPrice(BigDecimal price, Locale locale) {
    return String.format(locale, "%,.2f", price);
}
```

Mã minh họa trên cần import `BigDecimal` và `Locale`. Test:

```java
BigDecimal amount = new BigDecimal("1234.50");

System.out.println(formatPrice(amount, Locale.US));      // 1,234.50
System.out.println(formatPrice(amount, Locale.GERMANY)); // 1.234,50
```

Hai kết quả được quyết định **bởi tham số**, không bởi hệ điều hành. Ưu điểm:

- Unit test dễ viết và chạy ổn định trên máy có ngôn ngữ khác.
- Code review nhìn thấy rõ format được kỳ vọng.
- Dùng cùng một hàm để hỗ trợ nhiều locale.
- Không phải thay đổi `Locale.setDefault` trong test.
- Các test có thể chạy song song mà không tranh chấp global default Locale (miễn không có dependency khác làm vậy).
- Khi người dùng chọn locale mới, gọi hàm với locale mới thay vì đổi trạng thái chung.

Trong ứng dụng thực tế, thông số Locale có thể đến từ thông tin người dùng, headers request, configuration hoặc một `FormattingContext` đã được validation.

### Đừng truyền `Locale.getDefault()` ở mọi nơi rồi nghĩ đã độc lập

```java
formatPrice(amount, Locale.getDefault()); // Vẫn phụ thuộc máy chạy
```

Hàm nhận Locale tường minh là tốt, nhưng **test phải truyền một Locale xác định**. Nếu product cần “dùng mặc định của người dùng”, hãy kiểm thử phần logic format với tham số cụ thể và có một integration test riêng cho quy trình xác định Locale của người dùng.

## 6. `Locale.ROOT` dành cho xử lý kỹ thuật độc lập ngôn ngữ

Khi một chuỗi là mã máy, protocol token, enum key, tên cột, tên định danh hoặc mã cấu hình, bạn thường cần một quy tắc xử lý chữ hoa/chữ thường ổn định.

Không nên:

```java
String key = "TITLE".toLowerCase(); // Có thể đổi dưới locale Thổ Nhĩ Kỳ
```

Nên dùng:

```java
String key = "TITLE".toLowerCase(Locale.ROOT);
System.out.println(key); // title
```

`Locale.ROOT` không đại diện “Locale của tất cả người dùng” mà là **ngữ cảnh trung lập để tránh phụ thuộc quy tắc ngôn ngữ cụ thể**.

### Trường hợp Turkish I

```java
Locale turkish = Locale.forLanguageTag("tr-TR");

System.out.println("TITLE".toLowerCase(Locale.ROOT));
// title

System.out.println("TITLE".toLowerCase(turkish));
// tıtle (chữ ı không chấm)
```

Chữ `I` viết thường khác nhau giữa cách chuyển chữ không theo tiếng Thổ Nhĩ Kỳ và quy tắc của tiếng Thổ Nhĩ Kỳ. Nếu test chỉ so sánh `"title"` rồi chạy trên máy ở Thổ Nhĩ Kỳ với `toLowerCase()` không đối số, test có thể thất bại.

**Phân biệt mục tiêu:**

- **Mã kỹ thuật:** dùng `Locale.ROOT` khi phép biến đổi ký tự độc lập ngôn ngữ là đúng với protocol.
- **Văn bản của con người:** dùng Locale thật của ngôn ngữ/người dùng khi yêu cầu thay đổi chữ hoa–thường đúng theo ngôn ngữ.
- **Unicode case folding/caseless matching đầy đủ:** `String.toLowerCase(Locale.ROOT)` không phải một thuật toán canonicalization bảo đảm cho mọi ngôn ngữ, chuẩn hóa Unicode hoặc chống spoofing. Khi cần những đặc tính ấy, thiết kế riêng theo chuẩn của domain.

### Viết hoa mã máy

```java
String code = "usd".toUpperCase(Locale.ROOT);
System.out.println(code); // USD
```

Cách này phù hợp để chuẩn hóa mã ký tự alphabetic theo hợp đồng. Nếu đầu vào có ký tự không thuộc tập chữ mà protocol cho phép, cần validate thêm chứ không coi `toUpperCase` là kiểm tra hợp lệ.

## 7. Kiểm thử format số: luôn chọn Locale

Các cách viết dễ gây test phụ thuộc máy:

```java
String a = String.format("%,.2f", 1234.5);
NumberFormat b = NumberFormat.getNumberInstance();
```

Nếu yêu cầu output theo Mỹ hoặc Đức, chọn rõ:

```java
String us = String.format(Locale.US, "%,.2f", 1234.5);
String de = String.format(Locale.GERMANY, "%,.2f", 1234.5);

System.out.println(us); // 1,234.50
System.out.println(de); // 1.234,50
```

Đoạn minh họa cần import `Locale`.

### NumberFormat cũng cần Locale

```java
var amount = new BigDecimal("1234.50");

NumberFormat format = NumberFormat.getNumberInstance(Locale.GERMANY);
format.setGroupingUsed(true);
format.setMinimumFractionDigits(2);
format.setMaximumFractionDigits(2);

String formatted = format.format(amount);
// "1.234,50" trên dữ liệu locale chuẩn tương ứng
```

Đây là mã minh họa có import `NumberFormat`, `BigDecimal`, `Locale`.

**Lưu ý mutable:** `NumberFormat`/`DecimalFormat` nói chung có trạng thái có thể chỉnh sửa như grouping, min/max fraction digits, rounding. Đừng chia sẻ một formatter mutable cho nhiều test hoặc thread mà không có thiết kế phối hợp.

### Có nên dùng `Locale.ROOT` cho mọi định dạng số?

Không. `Locale.ROOT` phù hợp khi bạn muốn tránh phụ thuộc một ngôn ngữ/vùng và có hợp đồng dữ liệu tương ứng; nhưng **giao diện người dùng** nên dùng Locale do sản phẩm chọn. Đối với giao thức máy–máy có cú pháp số riêng (ví dụ một kiểu JSON number), nên dùng serializer/parser theo đặc tả giao thức, không mặc định mọi chuỗi do `NumberFormat(Locale.ROOT)` tạo ra đều tương thích giao thức.

## 8. Parse số trong test: chọn Locale cả ở chiều đọc

Test không chỉ bị ảnh hưởng ở bước định dạng. Khi parse văn bản do người dùng nhập, các dấu phân nhóm nghìn/dấu thập phân cũng phải được hiểu theo vùng.

Ví dụ:

```java
String german = "1.234,50";

NumberFormat parser =
        NumberFormat.getNumberInstance(Locale.GERMANY);

Number result = parser.parse(german);
System.out.println(result.doubleValue()); // 1234.5
```

Đây là đoạn minh họa có import `NumberFormat`, `Locale` và xử lý `ParseException`. Nếu bạn dùng `NumberFormat.getNumberInstance()` thay vì overload nhận `Locale.GERMANY`, kết quả có thể khác khi chạy trên máy mặc định Mỹ.

### Parse thành BigDecimal nếu cần decimal chính xác

```java
DecimalFormat formatter = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.GERMANY));
formatter.setParseBigDecimal(true);

Number parsed = formatter.parse("1.234,50");
BigDecimal value = (BigDecimal) parsed;
```

Đoạn này cần import `DecimalFormat`, `DecimalFormatSymbols`, `BigDecimal`, `Locale` và xử lý `ParseException`.

Để test nghiêm túc một trường chỉ chứa số, kiểm tra **toàn bộ văn bản đã được tiêu thụ** bằng `ParsePosition`; parser có thể nhận một tiền tố hợp lệ rồi bỏ qua phần sau.

```java
ParsePosition pos = new ParsePosition(0);
Number parsed = formatter.parse(input, pos);

if (parsed == null || pos.getIndex() != input.length()) {
    throw new IllegalArgumentException("Invalid number");
}
```

Đây là mã minh họa giả định `formatter` và `input` đã có. Kiểm tra parse hết giúp phát hiện suffix dư, nhưng chưa bảo đảm mọi quy tắc nghiệp vụ nghiêm ngặt như grouping chính xác hoặc scale tối đa. Nếu nghiệp vụ có schema số chặt, thêm validation phù hợp.

### `Double.parseDouble` và `BigDecimal(String)`

Các API này đọc chuỗi theo cú pháp đã định nghĩa, **không tự lấy dấu thập phân theo default Locale**:

```java
System.out.println(new BigDecimal("1234.50")); // 1234.50
// new BigDecimal("1.234,50"); // NumberFormatException
```

Với dữ liệu máy–máy đã canonical hóa, đó là lợi thế. Với input giao diện theo quốc gia, dùng parser locale-aware trước khi tính toán.

## 9. Ngày giờ: chỉ định Locale, nhưng đừng quên múi giờ là một biến khác

Một test về ngày có thể phụ thuộc ít nhất ba đầu vào:

1. **Locale:** ngôn ngữ của tên tháng/ngày và định dạng văn hóa.
2. **ZoneId:** múi giờ khi diễn giải instant thành local date/time.
3. **Clock:** thời điểm hiện tại khi gọi `now()`.

Đây là **ba khái niệm độc lập**. Đổi Locale không đồng nghĩa đổi timezone; dùng `Locale.US` không ngăn `LocalDate.now()` đổi ngày lúc nửa đêm.

### Chỉ định Locale cho DateTimeFormatter

```java
LocalDate date = LocalDate.of(2024, 1, 2);

DateTimeFormatter english =
        DateTimeFormatter.ofPattern("d MMMM uuuu", Locale.US);

DateTimeFormatter german =
        DateTimeFormatter.ofPattern("d MMMM uuuu", Locale.GERMANY);

String enText = english.format(date);
String deText = german.format(date);
```

Đây là mã minh họa có import `LocalDate`, `DateTimeFormatter` và `Locale`. Ngôn ngữ tên tháng được chọn rõ trong formatter.

**Không hardcode mọi tên tháng/ký tự khoảng trắng của date format trên tất cả JDK/provider** nếu yêu cầu chỉ kiểm “không phụ thuộc default locale”. Dữ liệu CLDR và provider có thể thay đổi. Test thuộc tính bất biến dưới thay đổi default Locale sẽ bền hơn, hoặc pin môi trường và output nếu nghiệp vụ thật sự bắt buộc đúng text đó.

### Formatter ISO cho dữ liệu máy–máy

```java
LocalDate date = LocalDate.of(2024, 1, 2);
String stable = DateTimeFormatter.ISO_LOCAL_DATE.format(date);

System.out.println(stable); // 2024-01-02
```

Nếu giao thức yêu cầu ISO date, dùng ISO formatter thay vì formatter localized.

### Clock cố định nếu test có thời gian hiện tại

```java
Clock fixed = Clock.fixed(
        Instant.parse("2024-01-02T03:04:05Z"),
        ZoneOffset.UTC);

LocalDate date = LocalDate.now(fixed);
System.out.println(date); // 2024-01-02
```

Đoạn minh họa cần import `Clock`, `Instant`, `ZoneOffset`, `LocalDate`.

**Locale mặc định độc lập** không đủ nếu test còn dùng `LocalDate.now()` hoặc timezone mặc định của máy. Một test ổn định cần kiểm soát tất cả nguồn biến thiên có liên quan.

## 10. Charset không phải Locale: đọc test fixture nhất quán

Một test có thể vẫn thất bại khi truyền Locale đúng vì **đọc fixture file bằng charset sai**.

Ví dụ, dữ liệu tiếng Việt hoặc tiếng Đức phải được giải mã đúng:

```java
String text = Files.readString(
        Path.of("fixture.txt"),
        StandardCharsets.UTF_8);
```

Đây là mã minh họa cần fixture thực sự tồn tại, import `Files`, `Path`, `StandardCharsets` và xử lý `IOException`.

**Charset** quyết định cách byte được giải mã thành `String`. **Locale** quyết định cách parse/format số, chữ hoa–thường theo ngôn ngữ hoặc tên hiển thị sau khi đã có chuỗi.

Nên tách:

```text
Byte file UTF-8 ── Charset.UTF_8 ──► "1.234,50"
                                  │
                                  └─ Locale.GERMANY ──► BigDecimal 1234.50
```

Dù nhiều API của JDK hiện đại có UTF-8 là default charset theo JEP 400 (Java 18+), vẫn nên khai báo charset của fixture/protocol khi test cần byte-to-text ổn định. **Đừng coi Locale.GERMANY là encoding ISO-8859-1**: hai khái niệm không liên quan trực tiếp.

## 11. Tại sao không nên thay `Locale.setDefault(...)` trong unit test thông thường?

`Locale.setDefault(locale)` thay đổi **trạng thái cấp JVM**, ảnh hưởng tới các API đang dùng default Locale trong nhiều phần của cùng tiến trình.

Ví dụ dễ gây nhiễu:

```java
@Test
void testGermanNumber() {
    Locale.setDefault(Locale.GERMANY);
    assertEquals("1.234,50", String.format("%,.2f", 1234.5));
}
```

Đây là **mã minh họa JUnit**, không phải tệp Java độc lập; import `@Test`/`assertEquals` theo phiên bản JUnit thích hợp.

Vấn đề:

- Nếu không khôi phục, test sau có thể thừa hưởng Locale Đức.
- Test chạy trước có thể đã thay default sang locale khác.
- Test chạy **song song** có thể thay default trong lúc test này đang chạy.
- Các formatter/cache/đối tượng đã tạo trước khi thay default có thể giữ cấu hình từ lúc tạo, làm kết quả khó đoán.
- `Locale.setDefault(locale)` ảnh hưởng **cả category defaults**, không chỉ phép format trong test.

Thay vì sửa global default để kiểm một hàm đơn giản, tốt nhất **truyền Locale vào chính hàm đang test**:

```java
@Test
void testGermanNumber() {
    assertEquals("1.234,50",
            formatPrice(new BigDecimal("1234.50"), Locale.GERMANY));
}
```

Khi test không thay trạng thái chung, chạy song song sẽ ít rủi ro hơn, và lỗi phản ánh logic của hàm thay vì thứ tự test.

### Không dùng `System.setProperty("user.language", "de")` như cách đổi Locale tức thời

Javadoc hiện hành nêu rằng các thuộc tính locale như `user.language`/`user.country` được dùng **khi runtime khởi tạo default Locale**. Việc gọi `System.setProperty(...)` sau JVM startup **không cập nhật tự động `Locale.getDefault()`**. Nếu thật sự muốn thay default ở runtime, API tương ứng là `Locale.setDefault` — nhưng phải hiểu đó là global state.

Muốn test cấu hình **khởi động JVM**, dùng JVM process riêng với tùy chọn `-Duser.language` và `-Duser.country` như mục 13.

## 12. Nếu bắt buộc test đường code sử dụng default Locale

Đôi khi bạn đang bảo trì một API cũ có chữ ký không nhận Locale, hoặc cần bảo đảm behavior của chức năng “dùng default của JVM”. Khi đó có thể tạo **integration test biệt lập**, thay default có kiểm soát, rồi **khôi phục**.

### Bắt buộc lưu cả ba default values

```java
Locale beforeBase = Locale.getDefault();
Locale beforeFormat = Locale.getDefault(Locale.Category.FORMAT);
Locale beforeDisplay = Locale.getDefault(Locale.Category.DISPLAY);

try {
    Locale.setDefault(Locale.GERMANY);

    // Chỉ chạy các assertion nhạy với default Locale ở đây.
    // KHÔNG chạy song song với test khác đụng global Locale.

} finally {
    Locale.setDefault(beforeBase);
    Locale.setDefault(Locale.Category.FORMAT, beforeFormat);
    Locale.setDefault(Locale.Category.DISPLAY, beforeDisplay);
}
```

Đây là đoạn Java minh họa. Thứ tự khôi phục quan trọng: `setDefault(beforeBase)` **ghi đè cả category defaults**; do đó phải phục hồi `FORMAT` và `DISPLAY` sau đó nếu trước test hai category khác base.

### Vì sao `try/finally` vẫn chưa đủ nếu chạy song song?

`finally` bảo đảm test này cố gắng khôi phục khi kết thúc, nhưng không ngăn test khác **đọc hoặc thay đổi default** trong thời gian ở giữa. Đây là race condition trên state cấp JVM.

Đối với test thực sự cần đổi default:

- Ưu tiên **một JVM con riêng** để không ảnh hưởng bộ test chính.
- Hoặc đánh dấu test **không chạy song song** với các test đụng Locale.
- Với JUnit Jupiter, có thể dùng `@ResourceLock(Resources.LOCALE)` (xem mục 14) nếu mọi test có khả năng đụng tài nguyên chung đều hợp tác với cùng lock.
- Không nên dùng cơ chế đồng bộ trên một object tùy ý rồi cho rằng code thư viện/test khác sẽ tự tuân thủ lock ấy.

Trong code mới, lựa chọn tốt nhất vẫn là **dependency injection của Locale** thay vì tác động đến global state.

## 13. Test trên hai JVM có default locale khác nhau

Để phát hiện các phụ thuộc môi trường ẩn, chạy cùng chương trình trong những **process** khác nhau:

```bash
javac --release 17 -encoding UTF-8 LocaleIndependentTestsDemo.java

java -Duser.language=en -Duser.country=US LocaleIndependentTestsDemo
java -Duser.language=de -Duser.country=DE LocaleIndependentTestsDemo
java -Duser.language=tr -Duser.country=TR LocaleIndependentTestsDemo
```

Trong các lệnh trên:

- Từng lệnh `java` khởi chạy **một JVM mới**.
- `user.language` và `user.country` được chỉ định **trước khi JVM tạo default Locale**.
- Kiểm thử được thiết kế đúng nên cùng các assertion dựa trên Locale tường minh sẽ PASS ở cả ba tiến trình.
- Không cần đoán Locale mặc định ở máy người dùng; test matrix chủ động đưa ra nhiều cấu hình.

**Lưu ý:** nếu môi trường triển khai có cấu hình riêng `user.language.format`, `user.country.format`, `user.language.display`, `user.country.display`, hoặc locale providers khác, cần hiểu các giá trị ấy khi dựng test matrix. `-Duser.language=...` chỉ là một cách tạo môi trường kiểm thử, không đảm bảo override mọi cấu hình format/display đã được cung cấp riêng.

Một matrix CI có thể chạy Java test ở các môi trường khác nhau mà **không đổi mã nguồn và không sửa Locale toàn cục trong tiến trình đang chạy**.

## 14. JUnit Jupiter: bảo vệ các test buộc phải đổi Locale

Đây là **đoạn mã JUnit minh họa**, **không** thuộc chương trình Java độc lập mục 16 và chỉ dùng khi dự án có dependency JUnit Jupiter tương ứng:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.junit.jupiter.api.parallel.Resources;

class LegacyLocaleTest {
    @Test
    @ResourceLock(Resources.LOCALE)
    void legacyFormatterUsesGermanDefault() {
        Locale oldBase = Locale.getDefault();
        Locale oldFormat =
                Locale.getDefault(Locale.Category.FORMAT);
        Locale oldDisplay =
                Locale.getDefault(Locale.Category.DISPLAY);

        try {
            Locale.setDefault(Locale.GERMANY);
            assertEquals("1.234,50",
                    String.format("%,.2f", 1234.5));
        } finally {
            Locale.setDefault(oldBase);
            Locale.setDefault(Locale.Category.FORMAT, oldFormat);
            Locale.setDefault(Locale.Category.DISPLAY, oldDisplay);
        }
    }
}
```

Đoạn code còn cần import `java.util.Locale`. `@ResourceLock(Resources.LOCALE)` khai báo có sử dụng tài nguyên Locale chung; JUnit Jupiter có cơ chế phối hợp tài nguyên khi chạy parallel.

**Giới hạn cần hiểu đúng:** ResourceLock chỉ phối hợp **những test đang chạy trong cùng JUnit scheduler** và sử dụng lock phù hợp. Nó không ngăn code ngoài JUnit, một thread nền tùy ý hoặc thư viện khác thay global default. Nếu môi trường có nhiều nguồn thay Locale không kiểm soát được, dùng process isolation sẽ rõ ràng hơn.

Các test bình thường truyền `Locale.US`/`Locale.GERMANY` thẳng vào đối tượng cần kiểm **không cần** khóa loại này.

## 15. Kiểm thử kết quả theo ngữ nghĩa, tránh assert chuỗi giòn với CLDR

Không phải mọi chuỗi địa phương đều ổn định tuyệt đối qua phiên bản JDK.

Ví dụ một bài test về formatter ngày:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("d MMMM uuuu", Locale.GERMANY);

String actual = formatter.format(LocalDate.of(2024, 1, 2));
```

Đoạn minh họa cần import `DateTimeFormatter`, `LocalDate`, `Locale`. Tên tháng, ký hiệu tiền tệ, cách nhóm chữ số và một số dấu cách có thể khác khi **dữ liệu CLDR/provider** thay đổi.

### Chọn mức assertion phù hợp

**Nếu hợp đồng thật sự quy định literal output**, ví dụ API nội bộ phải xuất `"1,234.50"` theo mẫu của bạn:

- Dùng Formatter/pattern và Locale tường minh.
- Chọn dữ liệu test ít phụ thuộc provider nếu có thể.
- Nếu cần chính xác cả spacing/names, pin hoặc ghi nhận phiên bản provider/runtime và định nghĩa rõ format.

**Nếu mục tiêu chỉ là “không bị thay đổi khi default locale khác đi”**:

- Gọi cùng formatter/hàm với Locale tường minh trong hai môi trường.
- So sánh output của **cùng Locale** giữa hai lần đổi default, thay vì hardcode mọi tên tháng hoặc ký hiệu tiền tệ.
- Kiểm kết quả **parse ngược** hoặc thuộc tính quan trọng (currency code, giá trị số, ngày) khi API hỗ trợ.
- Không dùng `Locale.getDefault()` để tạo expected value; đó là lặp lại phụ thuộc mà bạn muốn loại bỏ.

### Cảnh báo về provider/dữ liệu locale

JDK có nhiều nguồn locale data như CLDR, service provider hoặc HOST provider trên một số platform. Một test chạy ổn trên JDK này có thể đổi text localized khi nâng cấp JDK hoặc thay provider mà vẫn đúng hợp đồng.

Độc lập **default Locale** là một mục tiêu; độc lập **phiên bản dữ liệu localization** là một mục tiêu khác. Đừng tuyên bố chỉ cần truyền Locale tường minh thì mọi string localized sẽ mãi mãi giống nhau trên mọi JDK/provider.

## 16. Chương trình Java 17+ độc lập chứng minh tính bất biến theo default

Tạo file **`LocaleIndependentTestsDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class LocaleIndependentTestsDemo {
    static String formatPrice(BigDecimal amount, Locale locale) {
        return String.format(locale, "%,.2f", amount);
    }

    static BigDecimal parseNumber(String text, Locale locale) {
        var symbols = DecimalFormatSymbols.getInstance(locale);
        var parser = new DecimalFormat("#,##0.00", symbols);
        parser.setParseBigDecimal(true);

        var position = new ParsePosition(0);
        Number parsed = parser.parse(text, position);
        if (parsed == null || position.getIndex() != text.length()) {
            throw new IllegalArgumentException("Invalid number");
        }
        return (BigDecimal) parsed;
    }

    static String protocolKey(String text) {
        return text.toLowerCase(Locale.ROOT);
    }

    static String localizedMonth(LocalDate date, Locale locale) {
        return DateTimeFormatter.ofPattern("MMMM", locale).format(date);
    }

    static void require(boolean ok, String name) {
        if (!ok) {
            throw new AssertionError(name);
        }
    }

    public static void main(String[] args) {
        var amount = new BigDecimal("1234.50");
        var date = LocalDate.of(2024, 1, 2);
        Locale tr = Locale.forLanguageTag("tr-TR");

        // Assertions thuần: không phụ thuộc default Locale của JVM.
        String us = formatPrice(amount, Locale.US);
        String de = formatPrice(amount, Locale.GERMANY);
        require("1,234.50".equals(us), "us-number");
        require("1.234,50".equals(de), "de-number");
        require("title".equals(protocolKey("TITLE")), "root-case");
        require(amount.compareTo(parseNumber(de, Locale.GERMANY)) == 0,
                "parse-german");

        System.out.println("us=" + us);
        System.out.println("de=" + de);
        System.out.println("rootKey=" + protocolKey("TITLE"));
        System.out.println("turkishExplicitDifferent="
                + !protocolKey("TITLE").equals("TITLE".toLowerCase(tr)));
        System.out.println("germanParsed="
                + parseNumber(de, Locale.GERMANY).toPlainString());

        System.out.println("isoDate="
                + DateTimeFormatter.ISO_LOCAL_DATE.format(date));

        Clock clock = Clock.fixed(
                Instant.parse("2024-01-02T03:04:05Z"),
                ZoneOffset.UTC);
        System.out.println("fixedDate=" + LocalDate.now(clock));

        byte[] utf8 = "Tiếng Việt".getBytes(StandardCharsets.UTF_8);
        String restored = new String(utf8, StandardCharsets.UTF_8);
        System.out.println("utf8RoundTrip="
                + "Tiếng Việt".equals(restored));

        // Test độc lập literal tên tháng, nhưng có Locale rõ.
        String monthUS = localizedMonth(date, Locale.US);
        String monthDE = localizedMonth(date, Locale.GERMANY);
        require(!monthUS.isBlank() && !monthDE.isBlank(), "month-nonblank");

        // Chỉ minh họa thay default bên trong một process test đơn độc.
        // Không chạy phần này đồng thời với test khác trong cùng JVM.
        Locale oldBase = Locale.getDefault();
        Locale oldFormat = Locale.getDefault(Locale.Category.FORMAT);
        Locale oldDisplay = Locale.getDefault(Locale.Category.DISPLAY);

        try {
            Locale.setDefault(Locale.US);
            String implicitUS = String.format("%,.2f", amount);
            String explicitUS1 = formatPrice(amount, Locale.US);
            String monthUS1 = localizedMonth(date, Locale.US);
            String keyRoot1 = protocolKey("TITLE");

            Locale.setDefault(Locale.GERMANY);
            String implicitDE = String.format("%,.2f", amount);
            String explicitUS2 = formatPrice(amount, Locale.US);
            String monthUS2 = localizedMonth(date, Locale.US);
            String keyRoot2 = protocolKey("TITLE");

            System.out.println("implicitChanged="
                    + !implicitUS.equals(implicitDE));
            System.out.println("explicitStable="
                    + explicitUS1.equals(explicitUS2));
            System.out.println("monthStableAcrossDefaults="
                    + monthUS1.equals(monthUS2));
            System.out.println("rootKeyStableAcrossDefaults="
                    + keyRoot1.equals(keyRoot2));

            Locale.setDefault(tr);
            System.out.println("implicitTurkishCaseDifferent="
                    + !"title".equals("TITLE".toLowerCase()));
            System.out.println("explicitRootStillTitle="
                    + "title".equals(protocolKey("TITLE")));

            Locale.setDefault(Locale.Category.FORMAT, Locale.GERMANY);
            Locale.setDefault(Locale.Category.DISPLAY, Locale.US);
            System.out.println("formatCategory="
                    + Locale.getDefault(
                            Locale.Category.FORMAT).toLanguageTag());
            System.out.println("displayCategory="
                    + Locale.getDefault(
                            Locale.Category.DISPLAY).toLanguageTag());
            System.out.println("categoryNumber="
                    + String.format("%,.2f", amount));
        } finally {
            // Khôi phục đầy đủ, kể cả category trước đó khác base.
            Locale.setDefault(oldBase);
            Locale.setDefault(Locale.Category.FORMAT, oldFormat);
            Locale.setDefault(Locale.Category.DISPLAY, oldDisplay);
        }

        System.out.println("defaultsRestored="
                + (oldBase.equals(Locale.getDefault())
                && oldFormat.equals(
                        Locale.getDefault(Locale.Category.FORMAT))
                && oldDisplay.equals(
                        Locale.getDefault(Locale.Category.DISPLAY))));

        System.out.println("testResult=PASS");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 LocaleIndependentTestsDemo.java
java LocaleIndependentTestsDemo
```

**Stdout dự kiến chính xác:**

```text
us=1,234.50
de=1.234,50
rootKey=title
turkishExplicitDifferent=true
germanParsed=1234.50
isoDate=2024-01-02
fixedDate=2024-01-02
utf8RoundTrip=true
implicitChanged=true
explicitStable=true
monthStableAcrossDefaults=true
rootKeyStableAcrossDefaults=true
implicitTurkishCaseDifferent=true
explicitRootStillTitle=true
formatCategory=de-DE
displayCategory=en-US
categoryNumber=1.234,50
defaultsRestored=true
testResult=PASS
```

### Giải thích từng nhóm kết quả

1. **`us` và `de`**: cùng giá trị `1234.50` nhưng mẫu định dạng địa phương khác nhau. Assertion vẫn giống khi máy chạy có default Locale khác.
2. **`rootKey`**: mã kỹ thuật `TITLE` luôn thành `title` nhờ `Locale.ROOT`.
3. **`turkishExplicitDifferent`**: việc xử lý chữ hoa–thường theo tiếng Thổ Nhĩ Kỳ có thể khác, chứng minh lý do không dùng default Locale cho protocol keys.
4. **`germanParsed`**: `DecimalFormatSymbols(Locale.GERMANY)` và `ParsePosition` giúp đọc số Đức và không bỏ qua suffix.
5. **`isoDate` và `fixedDate`**: ISO formatter và Clock cố định tránh thêm hai phụ thuộc môi trường thường gặp của test ngày giờ.
6. **`utf8RoundTrip`**: charset được chọn tường minh, không liên quan default Locale.
7. **`implicitChanged`**: gọi `String.format` **không truyền Locale** tạo kết quả khác khi default chuyển US → Germany.
8. **`explicitStable`, `monthStableAcrossDefaults`, `rootKeyStableAcrossDefaults`**: các hàm có Locale tường minh hoặc ROOT không đổi theo default.
9. **`implicitTurkishCaseDifferent`** so với **`explicitRootStillTitle`**: minh họa rõ lỗi Turkish-I của lời gọi `toLowerCase()` không đối số.
10. **`formatCategory` và `displayCategory`**: hai category được đặt riêng và giữ các giá trị khác nhau.
11. **`categoryNumber`** cho thấy `String.format` không Locale dùng quy tắc FORMAT đang được cấu hình.
12. **`defaultsRestored`**: `finally` phục hồi base, FORMAT và DISPLAY ngay cả khi ban đầu khác nhau.
13. **`testResult=PASS`** chỉ được in nếu các assertion logic của chương trình không ném `AssertionError`.

**Điểm quản lý test rất quan trọng:** chương trình này chủ động đổi default Locale để minh họa, nhưng chạy như **một chương trình độc lập**. Đừng sao chép riêng đoạn thay global default vào các unit test chạy song song; cách tốt nhất vẫn là test các hàm có Locale tường minh ở đầu chương trình.

## 17. Chạy lại chương trình dưới nhiều default Locale

Sau khi biên dịch, chạy các lệnh riêng:

```bash
java -Duser.language=en -Duser.country=US LocaleIndependentTestsDemo
java -Duser.language=de -Duser.country=DE LocaleIndependentTestsDemo
java -Duser.language=tr -Duser.country=TR LocaleIndependentTestsDemo
```

Khi tạo JVM mới, mỗi lệnh có một default locale ban đầu khác nhau. Vì chương trình:

- Dùng Locale tường minh cho logic cần ổn định.
- Chỉ đổi default ở đoạn kiểm thử có `finally` khôi phục.
- Không assert text localized dễ biến động ngoài các mẫu số phổ biến, rõ ràng.
- Không dùng `LocalDate.now()` không có Clock hoặc charset mặc định.

nên phần hành vi cần kiểm vẫn có thể PASS trong cả ba môi trường trên.

**Tuy nhiên, test nội dung chuẩn xác còn có phạm vi riêng:** các locale provider không tiêu chuẩn hoặc JDK bị cấu hình custom có thể tạo string locale-specific khác nhau. Nếu nhóm sản phẩm muốn bảo đảm chính xác một output cụ thể trên mọi môi trường, phải quy định cả nguồn dữ liệu localization hoặc sử dụng thuật toán định dạng cố định theo đặc tả của chính sản phẩm.

### Nên chạy thêm kiểm thử ở Locale bất ngờ

Ngoài Mỹ và Đức, thử tiếng Thổ Nhĩ Kỳ để tìm lỗi `toLowerCase()`/`toUpperCase()`, hoặc một locale dùng ký hiệu phân nhóm/khoảng trắng khác để tìm test so sánh literal thiếu kiểm soát. Không nhất thiết chọn tất cả các Locale có sẵn: hãy chọn **những trường hợp phân biệt mạnh nhất với giả định của code**.

## 18. Những lỗi kiểm thử thường gặp

### Lỗi A: Assert chuỗi số kiểu Mỹ nhưng không truyền Locale

```java
String actual = String.format("%,.2f", 1234.5);
assertEquals("1,234.50", actual); // Phụ thuộc FORMAT default!
```

**Sửa:** `String.format(Locale.US, "%,.2f", 1234.5)`.

### Lỗi B: Dùng `String.toLowerCase()` cho mã kỹ thuật

```java
String actual = "TITLE".toLowerCase();
```

**Sửa:** `toLowerCase(Locale.ROOT)` nếu đó là protocol key; dùng Locale của người dùng cho chữ ngôn ngữ tự nhiên.

### Lỗi C: Chỉ chuyển test sang máy CI dùng tiếng Anh để “sửa”

Đặt CI mặc định Mỹ có thể tạm che lỗi. **Sửa đúng:** truyền Locale tường minh trong production code/test và chạy thêm test matrix dưới Locale khác.

### Lỗi D: Gọi `Locale.setDefault(Locale.US)` một lần ở `@BeforeAll`

Việc này thay JVM-global state, có thể ảnh hưởng test khác và vi phạm giả định của những module khác. **Sửa:** test hàm nhận Locale; chỉ thay global state trong test cô lập có rollback.

### Lỗi E: Khôi phục chỉ `Locale.getDefault()`

Nếu test thay `FORMAT` và `DISPLAY` riêng, chỉ lưu/khôi phục base locale không bảo đảm giữ cấu hình gốc của từng category.

**Sửa:** lưu cả base + FORMAT + DISPLAY rồi khôi phục theo đúng thứ tự.

### Lỗi F: Nghĩ `try/finally` giải quyết cả test song song

`finally` giải quyết cleanup của **test hiện tại**, nhưng không ngăn thread/test khác đọc global Locale trong lúc đang bị đổi.

**Sửa:** process isolation hoặc cơ chế phối hợp scheduler như JUnit Jupiter resource lock khi phù hợp.

### Lỗi G: Dùng Locale đúng nhưng ngày vẫn khác vì timezone

`LocalDate.now()` hoặc thời điểm hệ thống có thể đổi theo múi giờ và lúc chạy. **Sửa:** truyền `Clock.fixed`/`ZoneId` khi test cần thời gian cố định.

### Lỗi H: Dùng Locale đúng nhưng fixture sai vì charset

`Locale.GERMANY` không tự biến bytes ISO-8859-1 thành UTF-8. **Sửa:** giải mã bằng `StandardCharsets.UTF_8` hoặc charset được hợp đồng quy định.

### Lỗi I: Test cứng ký hiệu tiền tệ trên mọi JDK

Ký hiệu, dấu cách, tên tháng và một số dạng format có thể thay khi CLDR/provider thay đổi. **Sửa:** chọn assertion theo hợp đồng, kiểm code/các thuộc tính ngữ nghĩa, pin runtime/provider khi exact output là yêu cầu.

### Lỗi J: Dùng `new BigDecimal(0.1)` rồi đổ lỗi cho Locale

Sai số của `double` là vấn đề số học, không phải Locale. **Sửa:** dùng chuỗi decimal canonical hoặc parser `BigDecimal` theo Locale.

### Lỗi K: Dùng `NumberFormat.parse(String)` rồi tin chắc mọi ký tự đều hợp lệ

Một parser có thể chỉ tiêu thụ phần đầu. **Sửa:** kiểm `ParsePosition` và validation domain.

### Lỗi L: Chia sẻ `NumberFormat`/`DecimalFormat` mutable giữa các test

Ngay cả khi Locale đã explicit, object formatter dùng chung có thể bị thay state như grouping, min/max fraction digits hoặc rounding. **Sửa:** mỗi test tạo formatter riêng hoặc quản lý đồng bộ đúng hợp đồng.

### Lỗi M: Thay `System.setProperty("user.language", ...)` rồi tin default Locale đã đổi

JVM khởi tạo default locale lúc startup; thay system property về sau không tự đổi Locale mặc định.

**Sửa:** dùng process riêng với `-D...` nếu đang test startup behavior, hoặc `Locale.setDefault` trong test đã cô lập nếu thật sự cần.

## 19. Checklist review trước khi viết test quốc tế hóa

1. **Mục tiêu test là gì?** Logic độc lập môi trường hay giao diện theo Locale thật?
2. **Có lời gọi `String.format`/`printf` không truyền Locale không?**
3. **Có `NumberFormat.getInstance()` hoặc `DateFormat.getDateInstance()` không Locale không?**
4. **Có `DateTimeFormatter.ofPattern(...)` mà thiếu Locale khi pattern có tên tháng/ngày không?**
5. **Có `toLowerCase()`/`toUpperCase()` không đối số cho protocol keys không?**
6. **Đã phân biệt `Locale.Category.FORMAT` và `DISPLAY` chưa?**
7. **Locale được truyền từ input đã validation hay lấy ngầm từ môi trường?**
8. **Test kiểm literal output hay hành vi/ý nghĩa?** Literal phụ thuộc CLDR cần hợp đồng rõ.
9. **Có parse số và kiểm toàn bộ input được tiêu thụ không?**
10. **Có dùng `BigDecimal` khi cần chính xác thập phân không?**
11. **Có dùng default timezone hoặc `now()` không kiểm soát không?**
12. **Có dùng default charset khi đọc fixture không?**
13. **Có dùng symbol tiền tệ làm ID hoặc hardcode localized name không?**
14. **Có dùng `Locale.setDefault(...)` trong test không?** Nếu có, xem có thể bỏ không.
15. **Nếu không bỏ được global state, đã lưu và khôi phục ba giá trị base/FORMAT/DISPLAY chưa?**
16. **Test có chạy song song không?** Có cần resource lock hoặc process riêng?
17. **Có formatter mutable dùng chung không?**
18. **Có test matrix `en-US`, `de-DE`, `tr-TR` cho các giả định quan trọng không?**
19. **Có phụ thuộc startup system properties và provider không?** Kiểm cấu hình CI.
20. **Nếu thấy fail trên máy khác, đã xác định nguồn phụ thuộc là Locale/ZoneId/Clock/Charset/CLDR chưa?**

## 20. Bài tập tự kiểm tra

**Câu 1.** Vì sao `String.format("%,.2f", 1234.5)` có thể trả text khác trên hai máy?

**Câu 2.** Cách viết nào khiến kết quả số theo quy tắc Mỹ không phụ thuộc default Locale?

**Câu 3.** Với một khóa kỹ thuật `"TITLE"`, tại sao không dùng `toLowerCase()` không đối số?

**Câu 4.** Khi nào `Locale.ROOT` phù hợp, và khi nào không?

**Câu 5.** `Locale.Category.FORMAT` khác `DISPLAY` như thế nào?

**Câu 6.** `Locale.setDefault(Locale.GERMANY)` có thay đổi chỉ FORMAT không?

**Câu 7.** Test muốn phục hồi trạng thái Locale sau khi thay đổi category, cần lưu những gì?

**Câu 8.** Vì sao `try/finally` không đủ để chống race giữa các test chạy song song?

**Câu 9.** Có thể dùng `@ResourceLock(Resources.LOCALE)` để phối hợp test nào?

**Câu 10.** Vì sao thay `System.setProperty("user.language","de")` sau JVM startup không phải cách đáng tin để đổi default locale?

**Câu 11.** Nếu test format ngày với `Locale.US` vẫn flake lúc giao ngày, còn nguồn biến thiên nào?

**Câu 12.** Nếu test đọc file tiếng Việt khác nhau trên máy, nên kiểm tra gì ngoài Locale?

**Câu 13.** Vì sao không nên hardcode mọi dấu cách/ký hiệu tiền tệ khi nâng JDK hoặc đổi provider?

**Câu 14.** `NumberFormat.parse(...)` trả Number có nghĩa toàn bộ chuỗi số đã hợp lệ không?

**Câu 15.** Nên kiểm thử cùng hàm theo Đức và Mỹ bằng cách đổi global Locale hay truyền đối số Locale?

**Câu 16.** Tại sao JDK `Locale` và Java `Charset` là hai phụ thuộc khác nhau?

**Câu 17.** Cách nào tốt hơn để test default Locale lúc **khởi động JVM**?

**Câu 18.** Vì sao chỉ chuyển production code sang `Locale.ROOT` ở tất cả nơi không phải giải pháp quốc tế hóa tốt?

**Đáp án:**

1. Vì overload không Locale dùng default `FORMAT`, có thể khác giữa máy.
2. `String.format(Locale.US, "%,.2f", 1234.5)`.
3. Locale Thổ Nhĩ Kỳ có quy tắc I/i khác, làm hỏng key kỹ thuật.
4. Phù hợp cho xử lý độc lập ngôn ngữ như protocol keys; không thay Locale thật khi cần hiển thị cho người dùng.
5. FORMAT dùng cho số/ngày/tiền tệ; DISPLAY dùng cho tên giao diện/locale.
6. Không, overload không category đặt cả base và defaults của các category.
7. `Locale.getDefault()`, `getDefault(FORMAT)` và `getDefault(DISPLAY)`; khôi phục base trước rồi hai category.
8. Vì các thread/test khác vẫn có thể nhìn thấy hoặc thay đổi state chung trong khoảng thời gian test đang chạy.
9. Những test JUnit Jupiter cần truy cập/đổi default Locale chia sẻ và hợp tác với resource lock.
10. Default Locale đã được khởi tạo từ startup properties; thay property sau đó không tự cập nhật Locale object.
11. Clock/thời điểm hiện tại và ZoneId/múi giờ, cần kiểm soát riêng.
12. Charset giải mã byte của fixture, ví dụ UTF-8.
13. Dữ liệu CLDR/provider có thể đổi một số chi tiết localized; assert theo hợp đồng.
14. Không; có thể chỉ parse tiền tố. Kiểm `ParsePosition` và validation.
15. Truyền Locale tường minh; không cần tranh chấp global state.
16. Locale điều khiển quy tắc văn hóa, Charset điều khiển byte↔ký tự.
17. Chạy test trong JVM process riêng với `-Duser.language`/`-Duser.country` và cấu hình category nếu cần.
18. `Locale.ROOT` không diễn đạt nhu cầu ngôn ngữ/vùng của người dùng; dùng Locale thực cho UI.

## 21. Tổng kết và tài liệu chính thức còn áp dụng

- **Mục tiêu cốt lõi:** kiểm thử phải quyết định kết quả từ input và Locale **tường minh**, không phụ thuộc cấu hình mặc định của OS/JVM.
- `Locale.getDefault()` có giá trị cơ sở và hai category `FORMAT`, `DISPLAY`. Các API không nhận Locale có thể dùng một trong những mặc định này.
- Với **mã kỹ thuật**, `toLowerCase(Locale.ROOT)` và `toUpperCase(Locale.ROOT)` giúp tránh lỗi chữ I kiểu Thổ Nhĩ Kỳ.
- Với **giao diện người dùng**, truyền Locale có ý nghĩa như `Locale.US` hoặc `Locale.GERMANY` vào formatter.
- Với **date/time**, truyền Locale và kiểm soát độc lập `Clock`, `ZoneId` khi test có thời điểm.
- Với **fixture I/O**, truyền charset xác định, thường `StandardCharsets.UTF_8`.
- Hạn chế thay `Locale.setDefault` trong unit tests; nếu bắt buộc, cô lập, dùng `try/finally`, khôi phục base + category và tránh chạy song song.
- Với **CLDR/provider**, Locale tường minh giúp độc lập default nhưng không tự bảo đảm mọi text localized bất biến qua mọi phiên bản runtime.
- Các API và nguyên tắc này vẫn còn hiệu lực trên Java 17/21/26; không dùng giải pháp đã lỗi thời.

Nguồn chính thức:

1. [Java SE 26 — `java.util.Locale`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html): default Locale, category-specific defaults, cách thay đổi/khôi phục và cách JVM khởi tạo.
2. [Java SE 26 — `Locale.Category`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.Category.html): ý nghĩa `FORMAT` và `DISPLAY`.
3. [Java SE 26 — `String.toLowerCase(Locale)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html#toLowerCase(java.util.Locale)): quy tắc chuyển chữ, Turkish I và khuyến nghị `Locale.ROOT` cho identifier.
4. [Java SE 26 — `NumberFormat`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/NumberFormat.html): định dạng/phân tích số theo locale, mutable formatters và xử lý đồng thời.
5. [Java SE 26 — `DateTimeFormatter`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html): `ofPattern(..., Locale)`, `withLocale` và các formatter ISO.
6. [Java SE 26 — `DecimalFormat`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/DecimalFormat.html): format/parse decimal theo ký hiệu locale.
7. [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): giải thích charset mặc định của Java hiện đại (phân biệt với Locale).
8. [JUnit Jupiter — Parallel Execution, ResourceLock](https://docs.junit.org/current/user-guide/#writing-tests-parallel-execution-synchronization): cơ chế khóa tài nguyên `LOCALE` khi test dùng chung JVM global state.
