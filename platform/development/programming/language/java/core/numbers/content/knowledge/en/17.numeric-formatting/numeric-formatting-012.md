# `setParseBigDecimal` và giới hạn an toàn khi dùng formatter đồng thời trong Java

`java.text.DecimalFormat` là một formatter/parser số thực linh hoạt của Java: nó hỗ trợ **ký hiệu thập phân, phân nhóm hàng nghìn, định dạng theo mẫu và locale**. Tuy nhiên, hai vấn đề cần xử lý cẩn thận khi dùng với dữ liệu quan trọng:

1. **Kiểu và độ chính xác của kết quả parse.** `DecimalFormat#setParseBigDecimal(true)` yêu cầu parser trả `BigDecimal` cho **các số hữu hạn bình thường**, nhờ đó tránh ép kết quả parse trước hết qua `double`. Điều này đặc biệt hữu ích cho dữ liệu tiền tệ hoặc số thập phân dài.
2. **An toàn đồng thời (thread safety).** `DecimalFormat` và `NumberFormat` dạng dùng phổ biến **không bảo đảm thread-safe**. Không được chia sẻ một instance mutable để nhiều luồng cùng `format`, `parse` hoặc thay đổi cấu hình mà không có cơ chế đồng bộ phù hợp.

Ví dụ nhập chuỗi theo chuẩn dấu phân cách của Hoa Kỳ:

```java
java.text.DecimalFormatSymbols symbols =
    java.text.DecimalFormatSymbols.getInstance(java.util.Locale.US);

java.text.DecimalFormat df =
    new java.text.DecimalFormat("#,##0.00", symbols);

df.setParseBigDecimal(true);

Number result = df.parse("1,234.50");
// Kiểu thực tế của result: BigDecimal; giá trị thập phân: 1234.50.
```

Đây là **đoạn mã minh họa** trong một phương thức có khai báo/nhận `ParseException` thích hợp. Khi dùng `new DecimalFormat(..., symbols)`, ta quy định rõ ý nghĩa dấu phẩy và dấu chấm thay vì phụ thuộc locale mặc định của môi trường.

**Quan trọng:** Bật `setParseBigDecimal(true)` **không làm formatter trở thành thread-safe**, **không bảo đảm mọi chuỗi đầu vào hợp lệ về nghiệp vụ** và **không biến NaN/vô cực thành `BigDecimal`**. Những giới hạn này độc lập với nhau.

## 1. Phân biệt định dạng (`format`) và phân tích (`parse`)

`DecimalFormat` có hai hướng sử dụng:

- **`format(number)`**: nhận một giá trị số và tạo `String` theo mẫu ký tự, số chữ số thập phân, dấu phân cách, locale và quy tắc làm tròn.
- **`parse(text)`**: đọc văn bản đã nhập thành `Number` theo ký hiệu của formatter. `Number` là kiểu cha; giá trị thực tế có thể thuộc nhiều class khác nhau.

```java
java.text.DecimalFormat df = new java.text.DecimalFormat(
    "#,##0.00",
    java.text.DecimalFormatSymbols.getInstance(java.util.Locale.US)
);

String display = df.format(1234.5); // "1,234.50"
Number parsed = df.parse("1,234.50");
```

Kiểu khai báo của `parse(String)` là **`Number`**, không phải `BigDecimal` hay `Double`. Vì vậy nếu muốn thao tác an toàn dựa trên kiểu cụ thể, cần biết **cấu hình parser** và kiểm tra giá trị trước khi cast.

**Đừng suy ra rằng mẫu `#,##0.00` tự ép parser chỉ được nhận đúng hai chữ số thập phân.** Mẫu chủ yếu điều khiển cách format và một số quy tắc parse; parse còn có thể nhận những chuỗi không đúng chính sách nhập của ứng dụng. Nếu cần ràng buộc định dạng cố định, phải kiểm tra đầu vào riêng.

## 2. `setParseBigDecimal(true)` thay đổi điều gì?

`DecimalFormat#setParseBigDecimal(boolean newValue)` điều khiển cách chuyển chuỗi số thành `Number`:

- Khi **`true`**: với giá trị số hữu hạn phân tích thông thường, phương thức trả **`java.math.BigDecimal`**. Giá trị được xây từ chữ số thập phân đã nhận, thay vì bắt buộc đi qua một `double`.
- Khi **`false`** (thông thường là mặc định): parser có thể trả **`Long`** nếu giá trị số nguyên có thể biểu diễn dưới dạng `long`, hoặc **`Double`** khi giá trị không phù hợp kiểu `Long`/mang phần lẻ. Không nên mặc định mọi kết quả đều là `Double`.
- **Ngoại lệ quan trọng:** `NaN` và `±Infinity` vẫn được biểu diễn bằng **`Double`**, ngay cả khi `setParseBigDecimal(true)`.

```java
java.text.DecimalFormat df = new java.text.DecimalFormat(
    "#,##0.00",
    java.text.DecimalFormatSymbols.getInstance(java.util.Locale.US)
);

df.setParseBigDecimal(true);
Number precise = df.parse("1,234.50"); // BigDecimal 1234.50

df.setParseBigDecimal(false);
Number ordinary = df.parse("42");      // Long 42 trên JDK theo quy tắc parse này
```

Vì khai báo return type `Number` giữ nguyên, **không thể ép kiểu `BigDecimal` một cách mù quáng chỉ dựa trên lời gọi `parse`**. Cần biết instance nào đã được cấu hình và kiểm tra các giá trị đặc biệt.

### Vì sao `BigDecimal` hữu ích?

`double` chỉ có khoảng 15–17 chữ số thập phân có ý nghĩa, nên các chữ số dài có thể bị làm tròn khi chuyển qua binary floating point. `BigDecimal` biểu diễn số **thập phân** bằng phần nguyên độ chính xác tùy ý và scale.

Ví dụ chuỗi:

```text
9,007,199,254,740,993.00
```

`9007199254740993` là số nguyên lớn hơn `2^53`, không thể biểu diễn **chính xác** bằng `double`. Khi bật `setParseBigDecimal(true)`, parser trả một `BigDecimal` với nội dung thập phân **`9007199254740993.00`**. Nếu chuyển dữ liệu không nguyên rất lớn qua `double`, việc làm tròn có thể làm đổi những chữ số cuối.

**Không nhầm:** Bật chế độ `BigDecimal` chỉ giữ độ chính xác của **các chữ số parser thực sự đọc được**. Nếu dữ liệu đã được làm tròn ở hệ thống gửi, hoặc đầu vào sai định dạng, parser không thể khôi phục chữ số gốc đã mất.

## 3. `setParseBigDecimal` không phải bộ lọc NaN và vô cực

`BigDecimal` không có các giá trị `NaN`, `+Infinity` hoặc `-Infinity` như `double`. Vì thế `DecimalFormat` sử dụng `Double` cho các giá trị đặc biệt này ngay cả khi chế độ parse `BigDecimal` được bật.

```java
df.setParseBigDecimal(true);

Number nan = df.parse(df.getDecimalFormatSymbols().getNaN());
Number infinity = df.parse(df.getDecimalFormatSymbols().getInfinity());

// nan và infinity có kiểu thực tế Double, không phải BigDecimal.
```

Các chuỗi ký hiệu NaN/vô cực phụ thuộc cấu hình `DecimalFormatSymbols`/locale. Nếu parser được tạo từ locale khác, không nên mặc định các ký hiệu luôn được viết đúng là `"NaN"` và `"Infinity"` bằng chữ ASCII.

Với một API bắt buộc trả thập phân hữu hạn, có thể xác thực:

```java
Number number = df.parse(text);
if (!(number instanceof java.math.BigDecimal)) {
    throw new IllegalArgumentException("finite decimal required");
}
java.math.BigDecimal value = (java.math.BigDecimal) number;
```

Đây là đoạn mã minh họa cần đặt trong phương thức có xử lý `ParseException`. Điều kiện `instanceof` giúp **không cast nhầm `Double.NaN` hoặc vô cực sang `BigDecimal`**.

Ngoài việc chọn kiểu số, ứng dụng còn cần xác định điều gì được phép về **độ lớn, dấu, số chữ số và đơn vị đo**. Parse thành `BigDecimal` không đồng nghĩa với việc dữ liệu đã được nghiệp vụ xác thực.

## 4. Mất dấu của `-0.0` và những khác biệt về Number

Một góc cạnh tinh tế: kiểu dấu phẩy động có **`+0.0` và `-0.0`** với bit dấu khác nhau, nhưng `BigDecimal` **không lưu dấu zero âm riêng biệt**.

```java
df.setParseBigDecimal(true);
Number zero = df.parse("-0");
// BigDecimal có giá trị 0, không giữ dấu âm của zero.
```

Khi `setParseBigDecimal(false)` và `isParseIntegerOnly()` là `false`, parser có thể trả **`Double(-0.0)`**, giúp giữ dấu zero trong trường hợp này.

Do đó, không thể xem chế độ `BigDecimal` là “luôn bảo toàn mọi khía cạnh biểu diễn của chuỗi”. Nó bảo toàn **giá trị thập phân** cho số hữu hạn nhưng không giữ mọi dấu hiệu văn bản, kiểu dấu phẩy động hay thông tin trình bày ban đầu.

Nếu cần **giữ chính xác chuỗi mà người dùng đã nhập** để hiển thị lại hoặc kiểm toán, lưu riêng chuỗi gốc cùng giá trị `BigDecimal` đã parse. Giá trị số được phân tích không nhất thiết giữ dấu cộng đầu, chữ số 0 dẫn đầu, cách nhóm dấu phẩy, các ký hiệu locale hoặc sự khác biệt `-0`/`0`.

## 5. Cẩn thận với `setParseIntegerOnly` và các cài đặt khác

`setParseBigDecimal(true)` **không ghi đè mọi tùy chọn parser**. Ví dụ, `NumberFormat#setParseIntegerOnly(true)` làm parser chỉ nhận phần nguyên trong nhiều cấu hình:

```java
java.text.DecimalFormat df = new java.text.DecimalFormat(
    "#,##0.00",
    java.text.DecimalFormatSymbols.getInstance(java.util.Locale.US)
);
df.setParseBigDecimal(true);
df.setParseIntegerOnly(true);

Number value = df.parse("12.75");
// Parser có thể dừng tại dấu thập phân và chỉ nhận phần nguyên.
```

Không nên xem việc bật `parseBigDecimal` là bảo đảm giữ mọi phần thập phân nếu những cài đặt khác ngăn parser đọc chúng. Ngược lại, `setRoundingMode` điều khiển **làm tròn khi format**; nó không tự biến dữ liệu nhập thập phân thành giá trị đã làm tròn trong quá trình parse.

Các cài đặt của `DecimalFormat` như pattern, symbols, grouping, `setParseIntegerOnly`, `setParseBigDecimal`, `setMaximumFractionDigits` và `setRoundingMode` đều nên được xác định **trước khi formatter được dùng** theo nhiệm vụ. Thay đổi chúng trên một instance chia sẻ giữa các luồng sẽ tạo rủi ro logic và thread safety.

## 6. `parse(String)` có thể chấp nhận phần đầu chuỗi

Một lỗi dữ liệu nguy hiểm: `DecimalFormat.parse(String)` không nhất thiết buộc **toàn bộ chuỗi đầu vào** phải được tiêu thụ. Nó có thể đọc phần đầu hợp lệ rồi để lại hậu tố mà không ném lỗi.

```java
Number parsed = df.parse("1,234.50oops");
// Có thể parse được 1234.50, dù phần "oops" còn lại.
```

Lời gọi parse thành công **không đủ** chứng minh chuỗi đã phù hợp hợp đồng nhập.

Nếu phải nhận trọn vẹn đầu vào, dùng **`ParsePosition`**:

```java
static java.math.BigDecimal parseAll(
        java.text.DecimalFormat format, String input) {

    java.text.ParsePosition position = new java.text.ParsePosition(0);
    Number result = format.parse(input, position);

    if (result == null
            || position.getIndex() != input.length()
            || !(result instanceof java.math.BigDecimal)) {
        throw new IllegalArgumentException("invalid decimal");
    }
    return (java.math.BigDecimal) result;
}
```

Hàm yêu cầu caller dùng formatter đã bật `setParseBigDecimal(true)`. Nó kiểm tra ba việc: parse không thất bại ngay, **tiêu thụ hết chuỗi**, và kết quả thực tế là `BigDecimal` (loại NaN/vô cực). `ParsePosition` tránh ngoại lệ `ParseException` do parser trả null cùng vị trí lỗi, nhưng đoạn mã chủ động ném `IllegalArgumentException` nếu không đạt hợp đồng.

**Giới hạn:** Tiêu thụ toàn bộ chuỗi **chưa đảm bảo nhóm dấu phẩy đặt đúng mọi vị trí hoặc đúng số chữ số phần thập phân theo chính sách ứng dụng**. Nếu chỉ cho phép hai chữ số thập phân hoặc định dạng nghiêm ngặt, bổ sung bước xác thực chuỗi đầu vào/format grammar tương ứng. Đừng chỉ tin vào pattern formatter như một bộ validator hoàn chỉnh.

### Khi nào nên dùng `BigDecimal(String)` thay vì `DecimalFormat`?

Nếu đầu vào là định dạng máy **không phụ thuộc locale** như `"1234.50"`, hãy cân nhắc `new BigDecimal("1234.50")`:

```java
java.math.BigDecimal value = new java.math.BigDecimal("1234.50");
```

Constructor này phân tích chuỗi thập phân theo cú pháp của `BigDecimal`, không tự hiểu dấu phân nhóm kiểu `"1,234.50"`. `DecimalFormat` phù hợp hơn khi cần nhập/xuất số theo **locale của người dùng**; `BigDecimal(String)` phù hợp khi có **định dạng decimal canonical** ở API hoặc file cấu hình.

## 7. DecimalFormat không thread-safe: vấn đề nằm ở đâu?

`DecimalFormat` là một đối tượng **mutable**, lưu pattern, ký hiệu, chế độ parse và trạng thái liên quan. Tài liệu Java yêu cầu nếu nhiều luồng cùng truy cập một formatter, ứng dụng phải **đồng bộ bên ngoài**.

Ví dụ không an toàn về mặt thiết kế:

```java
// KHÔNG nên dùng chung như thế này:
static final java.text.DecimalFormat SHARED =
    new java.text.DecimalFormat("#,##0.00");

// Thread A:
String output = SHARED.format(1234.5);

// Thread B:
Number number = SHARED.parse("1,234.50");
```

Đây là các mảnh mã minh họa, không phải file độc lập. `static final` chỉ làm tham chiếu không thể gán sang formatter khác; **không** làm đối tượng `DecimalFormat` bất biến hoặc biến các phương thức thành thread-safe.

Rủi ro khi truy cập cùng lúc không đồng bộ gồm **kết quả parse/format sai, trạng thái nội bộ bị ảnh hưởng hoặc hành vi không xác định ổn định**. Không nên tạo một “ví dụ race” và hứa cứ chạy là tái hiện, vì lỗi đồng thời có thể phụ thuộc lịch chạy, JDK và tải hệ thống.

Việc nhiều thread **chỉ gọi format** cũng không được coi mặc định là an toàn. Một formatter có thể sử dụng trạng thái nội bộ khi làm việc; không dựa vào cảm giác rằng “chỉ đọc” thì thread-safe. Khi vừa format/parse vừa thay đổi pattern, symbols hoặc `setParseBigDecimal` trên một instance chung, nguy cơ càng rõ.

## 8. Ba cách sử dụng formatter an toàn giữa nhiều luồng

### Cách A — tạo instance cục bộ: đơn giản và dễ đúng

```java
static java.math.BigDecimal parseAmount(String input) {
    java.text.DecimalFormat formatter = makeFormatter();
    return parseAll(formatter, input);
}

static java.text.DecimalFormat makeFormatter() {
    var symbols = java.text.DecimalFormatSymbols.getInstance(java.util.Locale.US);
    var formatter = new java.text.DecimalFormat("#,##0.00", symbols);
    formatter.setParseBigDecimal(true);
    return formatter;
}
```

Mã minh họa trong một class có các phương thức tương ứng. Mỗi lần gọi có một formatter riêng, không có đối tượng mutable dùng chung giữa threads. Cách này phù hợp khi **độ rõ ràng và an toàn quan trọng hơn chi phí khởi tạo** hoặc số lần gọi vừa phải.

**Ưu điểm:** không cần lock; cấu hình không rò giữa lời gọi. **Nhược điểm:** có chi phí tạo formatter và symbols mỗi lần. Nếu đây là điểm nóng về hiệu năng, hãy đo trước khi tối ưu.

### Cách B — `ThreadLocal<DecimalFormat>`: formatter riêng theo thread

```java
private static final ThreadLocal<java.text.DecimalFormat> LOCAL =
    ThreadLocal.withInitial(() -> {
        var symbols =
            java.text.DecimalFormatSymbols.getInstance(java.util.Locale.US);
        var formatter = new java.text.DecimalFormat("#,##0.00", symbols);
        formatter.setParseBigDecimal(true);
        return formatter;
    });

static java.math.BigDecimal parseLocal(String input) {
    return parseAll(LOCAL.get(), input);
}
```

Mỗi luồng nhận một `DecimalFormat` riêng. Cần **không chuyển formatter từ một luồng sang luồng khác** và không thay đổi tùy chọn ở một lời gọi rồi giả định lần sau sẽ tự reset. Nếu sử dụng thread pool dài hạn và đối tượng trong `ThreadLocal` có vòng đời lớn, cân nhắc `LOCAL.remove()` khi phạm vi dùng kết thúc, hoặc đơn giản dùng formatter cục bộ để quản lý vòng đời rõ ràng hơn.

`ThreadLocal` chỉ ngăn *cùng instance* được chia sẻ ngẫu nhiên nếu sử dụng đúng, **không tự biến một formatter mutable thành immutable**. Việc phụ thuộc trạng thái của formatter cục bộ do thread trước trong pool để lại cũng có thể gây lỗi ngữ nghĩa.

### Cách C — đồng bộ bên ngoài khi thật sự phải dùng chung

```java
private static final java.text.DecimalFormat LOCKED = makeFormatter();

static java.math.BigDecimal parseLocked(String input) {
    synchronized (LOCKED) {
        return parseAll(LOCKED, input);
    }
}

static String formatLocked(java.math.BigDecimal amount) {
    synchronized (LOCKED) {
        return LOCKED.format(amount);
    }
}
```

Mọi truy cập vào cùng instance, **kể cả đọc/đổi cấu hình và lời gọi parse/format**, phải phối hợp sử dụng cùng một lock. Chỉ khóa một phương thức mà bỏ sót các đường dùng khác thì chưa giải quyết được vấn đề.

**Ưu điểm:** phù hợp khi bắt buộc chia sẻ một formatter. **Nhược điểm:** có lock contention, các luồng phải chờ; dễ mắc lỗi nếu có code khác dùng formatter ngoài lock. Tránh công khai instance `LOCKED` cho mã ngoài có thể gọi trực tiếp.

**Khuyến nghị thực hành:** Nếu không có lý do đặc biệt để chia sẻ, **tạo formatter riêng mỗi lần hoặc riêng mỗi thread** thường dễ lý giải hơn dùng một formatter chung có lock.

## 9. Locale, parsing và độ chính xác là ba quyết định độc lập

### Locale xác định dấu thập phân và dấu phân nhóm

`DecimalFormatSymbols` xác định ký hiệu dùng để đọc và hiển thị số. Ví dụ pattern `#,##0.00` với `Locale.US` hiển thị `1234.50` thành `"1,234.50"`, dấu **chấm** làm dấu thập phân, dấu **phẩy** phân nhóm. Trong các locale khác, ký hiệu có thể khác, kể cả ký tự khoảng trắng đặc biệt.

```java
var symbols = java.text.DecimalFormatSymbols.getInstance(java.util.Locale.US);
var df = new java.text.DecimalFormat("#,##0.00", symbols);
df.setParseBigDecimal(true);
```

**Đừng tạo formatter bằng locale mặc định ở nơi gửi rồi parse bằng giả định dấu phân cách US ở nơi nhận.** Định dạng giao tiếp máy nên được định nghĩa độc lập với UI locale; dữ liệu nhập từ người dùng cần gắn đúng locale và chính sách phân tích.

### Parse `BigDecimal` không quyết định làm tròn khi hiển thị

```java
var df = new java.text.DecimalFormat(
    "#,##0.00",
    java.text.DecimalFormatSymbols.getInstance(java.util.Locale.US)
);
df.setParseBigDecimal(true);
df.setRoundingMode(java.math.RoundingMode.HALF_UP);

java.math.BigDecimal amount = new java.math.BigDecimal("1.005");

String shown = df.format(amount); // "1.01"
```

`amount` vẫn là `1.005`; formatter chỉ tạo **chuỗi đã làm tròn cho hiển thị**. Nếu cần lưu giá trị đã làm tròn thành đúng hai chữ số thập phân, dùng API của `BigDecimal`, ví dụ `amount.setScale(2, RoundingMode.HALF_UP)`, và xác định rõ chính sách nghiệp vụ.

Đừng lấy `df.format(value)` rồi `df.parse(...)` làm cách làm tròn số học cốt lõi: quá trình round-trip qua string/locale làm tăng tính phức tạp và có thể mất thông tin (ví dụ số chữ số thập phân, negative zero hoặc biểu diễn chuỗi khác). Hãy tách **tính toán số** và **định dạng hiển thị**.

## 10. Chương trình Java 17+ chạy độc lập

Tạo tệp `BigDecimalParseDemo.java`:

```java
public class BigDecimalParseDemo {
    static java.text.DecimalFormat makeFormatter() {
        var symbols =
            java.text.DecimalFormatSymbols.getInstance(java.util.Locale.US);
        var format = new java.text.DecimalFormat("#,##0.00", symbols);
        format.setParseBigDecimal(true);
        return format;
    }

    static java.math.BigDecimal parseAll(
            java.text.DecimalFormat format, String s) {

        java.text.ParsePosition pos = new java.text.ParsePosition(0);
        Number number = format.parse(s, pos);

        if (number == null
                || pos.getIndex() != s.length()
                || !(number instanceof java.math.BigDecimal)) {
            throw new IllegalArgumentException("invalid decimal");
        }
        return (java.math.BigDecimal) number;
    }

    public static void main(String[] args) throws Exception {
        var df = makeFormatter();

        Number precise = df.parse("9,007,199,254,740,993.00");
        System.out.println("precise type: "
            + precise.getClass().getSimpleName());
        System.out.println("precise value: "
            + ((java.math.BigDecimal) precise).toPlainString());

        Number cents = df.parse("1,234.50");
        System.out.println("cents: "
            + ((java.math.BigDecimal) cents).toPlainString());

        System.out.println("negative zero: "
            + df.parse("-0").getClass().getSimpleName()
            + " " + df.parse("-0"));

        df.setParseBigDecimal(false);
        Number ordinary = df.parse("9,007,199,254,740,993.00");
        System.out.println("ordinary type: "
            + ordinary.getClass().getSimpleName());
        System.out.println("ordinary value: " + ordinary);
        System.out.println("integer type: "
            + df.parse("42").getClass().getSimpleName());

        df.setParseBigDecimal(true);
        System.out.println("NaN type: "
            + df.parse("NaN").getClass().getSimpleName());
        System.out.println("Infinity type: "
            + df.parse(df.getDecimalFormatSymbols().getInfinity())
                .getClass().getSimpleName());

        java.text.ParsePosition pos = new java.text.ParsePosition(0);
        Number prefix = df.parse("1,234.50oops", pos);
        System.out.println("prefix parsed: " + prefix
            + ", consumed: " + pos.getIndex());

        System.out.println("strict valid: "
            + parseAll(df, "1,234.50").toPlainString());

        try {
            parseAll(df, "1,234.50oops");
        } catch (IllegalArgumentException ex) {
            System.out.println("strict trailing: rejected");
        }
        try {
            parseAll(df, "NaN");
        } catch (IllegalArgumentException ex) {
            System.out.println("strict NaN: rejected");
        }

        df.setRoundingMode(java.math.RoundingMode.HALF_UP);
        System.out.println("formatted: "
            + df.format(new java.math.BigDecimal("1.005")));
        System.out.println("input unchanged: "
            + new java.math.BigDecimal("1.005").toPlainString());
    }
}
```

Biên dịch/chạy:

```bash
javac BigDecimalParseDemo.java
java BigDecimalParseDemo
```

Kết quả stdout đã kiểm chứng bằng JDK:

```text
precise type: BigDecimal
precise value: 9007199254740993.00
cents: 1234.50
negative zero: BigDecimal 0
ordinary type: Long
ordinary value: 9007199254740993
integer type: Long
NaN type: Double
Infinity type: Double
prefix parsed: 1234.50, consumed: 8
strict valid: 1234.50
strict trailing: rejected
strict NaN: rejected
formatted: 1.01
input unchanged: 1.005
```

**Giải thích output:**

1. Parse BigDecimal giữ `9007199254740993.00` và `1234.50` ở dạng thập phân. `-0` trở thành `BigDecimal 0`.
2. Khi tắt `parseBigDecimal`, giá trị nguyên có thể trả `Long`, không phải lúc nào cũng trả `Double`. Với giá trị có phần lẻ không thể trả `Long`, parser có thể trả `Double` và gây sai số nhị phân.
3. NaN và vô cực vẫn là `Double`; chế độ parse BigDecimal không biến chúng thành đối tượng thập phân.
4. Parser đã tiêu thụ 8 ký tự của `"1,234.50oops"` và để lại hậu tố; `parseAll` kiểm tra toàn bộ đầu vào để từ chối.
5. `RoundingMode.HALF_UP` ảnh hưởng chuỗi **format** `1.005 → "1.01"`, không thay đổi giá trị `BigDecimal` gốc.

Ví dụ tạo một formatter **cục bộ cho phương thức main**, không đưa cùng instance vào nhiều thread. Đây là cách dùng an toàn về chia sẻ trạng thái ở phạm vi ví dụ; trong dịch vụ nhiều luồng, áp dụng mẫu của mục 8.

## 11. Checklist thiết kế API parse/format có độ tin cậy

- **Định nghĩa định dạng đầu vào:** chuỗi từ người dùng theo locale nào, hay chuỗi canonical cho hệ thống máy?
- **Quyết định kiểu kết quả:** `BigDecimal` cho số thập phân hữu hạn cần độ chính xác, hay `Double` khi chấp nhận số thực nhị phân?
- **Kiểm tra đầy đủ chuỗi:** dùng `ParsePosition` và đối chiếu `getIndex() == input.length()`; bổ sung validation nghiêm ngặt nếu yêu cầu dấu nhóm/số chữ số cụ thể.
- **Từ chối giá trị đặc biệt nếu không hợp lệ:** `NaN` và `Infinity` vẫn có thể trả `Double` dù `setParseBigDecimal(true)`.
- **Xác định quy tắc làm tròn riêng:** `RoundingMode` cho format/`BigDecimal.setScale` cho kết quả số học theo nghiệp vụ.
- **Tách formatter khỏi các luồng:** instance cục bộ, `ThreadLocal` dùng đúng, hoặc đồng bộ toàn bộ truy cập cùng một instance.
- **Tránh cấu hình mutable thay đổi giữa các lời gọi:** không để thread A đổi locale/pattern/parse mode trong khi thread B đang parse.
- **Kiểm thử đầu vào biên:** chuỗi dài, phần lẻ nhiều chữ số, âm, signed zero, NaN, vô cực, dấu nhóm sai, chuỗi có hậu tố, số lớn hơn độ chính xác của `double`.
- **Giám sát hiệu năng sau khi đúng:** khởi tạo formatter mỗi lần có chi phí, nhưng dùng shared instance không đồng bộ là cách tối ưu sai. Chỉ chọn phương án khác sau khi đo thực tế.

Độ an toàn **đồng thời** và độ chính xác **số học** là hai bài toán độc lập: bật `setParseBigDecimal` giúp tránh làm tròn qua `double` khi parse số hữu hạn, nhưng không thể loại data race. Ngược lại, khóa formatter không tự làm dữ liệu thập phân chính xác nếu vẫn parse ra `Double`.

## 12. Sai lầm thường gặp

1. **“Bật `setParseBigDecimal(true)` thì `parse` luôn trả `BigDecimal`.”** Sai: NaN/vô cực vẫn có thể là `Double`.
2. **“Tắt `setParseBigDecimal` luôn trả `Double`.”** Sai: giá trị nguyên vừa miền có thể trả `Long`.
3. **“`parse(String)` thành công thì đã đọc hết chuỗi.”** Sai: parser có thể chỉ nhận prefix; dùng `ParsePosition` nếu yêu cầu đầy đủ.
4. **“Đúng pattern `#,##0.00` thì chuỗi nhập chắc chắn có đúng hai chữ số phần lẻ.”** Sai: formatter pattern không thay thế validation theo nghiệp vụ.
5. **“`BigDecimal` tự lưu dấu của zero âm.”** Sai: `BigDecimal` không có signed zero như `double`.
6. **“`parseBigDecimal` giữ nguyên ký tự dấu phân nhóm và locale input trong object kết quả.”** Sai: đó là parse thành giá trị số; muốn lưu văn bản gốc phải lưu riêng.
7. **“`setRoundingMode` khiến parser parse các chữ số vào `BigDecimal` đã làm tròn.”** Sai: `setRoundingMode` dùng khi định dạng; muốn làm tròn dữ liệu số dùng `BigDecimal.setScale` rõ ràng.
8. **“`static final DecimalFormat` an toàn cho nhiều luồng.”** Sai: final chỉ giữ tham chiếu, không biến đối tượng mutable thành thread-safe.
9. **“Nếu các luồng chỉ gọi `format` thì chia sẻ formatter mặc nhiên an toàn.”** Sai: không có bảo đảm thread-safe chung.
10. **“`ThreadLocal` luôn phù hợp và không cần quản lý trạng thái.”** Sai: thread pool dài hạn có thể giữ instance và trạng thái qua các nhiệm vụ; nên tránh rò cấu hình/vòng đời.
11. **“Đồng bộ chỉ riêng lời gọi `parse`, còn `setParseBigDecimal` thì khỏi cần lock.”** Sai: mọi truy cập vào cùng formatter chia sẻ phải phối hợp theo cùng cơ chế.
12. **“`new BigDecimal(double)` có thể khôi phục chính xác chuỗi thập phân người dùng nhập ban đầu.”** Sai: số `double` đã làm tròn nhị phân không chứa đủ thông tin nguồn.
13. **“Dùng một formatter singleton sẽ chắc chắn nhanh nhất.”** Sai: đồng bộ gây tranh chấp; chi phí khởi tạo hoặc thread confinement phải được benchmark.
14. **“Dùng `DecimalFormat` để serialize mọi số sang format máy ổn định mà không chỉ định locale.”** Sai: locale mặc định có thể thay đổi và ảnh hưởng ký tự số.

## 13. Tự kiểm tra

**1. `DecimalFormat.parse(String)` được khai báo trả kiểu gì?** → `Number`.

**2. Bật `setParseBigDecimal(true)` làm gì?** → Parse các giá trị số hữu hạn thông thường thành `BigDecimal`, tránh đường chuyển qua `double`.

**3. Có trường hợp chế độ đó vẫn trả `Double` không?** → Có: `NaN` và `Infinity`.

**4. Nếu tắt `setParseBigDecimal`, kết quả luôn là `Double`?** → Không; parser có thể trả `Long` cho giá trị nguyên.

**5. `parse("1,234.50oops")` trả số có nghĩa chuỗi hợp lệ hoàn toàn không?** → Không. Cần `ParsePosition` và kiểm tra đã tiêu thụ hết chuỗi.

**6. Pattern hai số lẻ đảm bảo validate đúng hai số lẻ của chuỗi input không?** → Không; cần xác thực định dạng độc lập nếu đây là điều kiện bắt buộc.

**7. Parse `"-0"` thành `BigDecimal` có giữ signed zero không?** → Không; giá trị BigDecimal bằng 0.

**8. Có thể dùng một `static final DecimalFormat` từ nhiều luồng mà không đồng bộ không?** → Không có bảo đảm thread-safe; dùng instance riêng hoặc khóa đầy đủ.

**9. Cách đơn giản nhất để tránh chia sẻ formatter mutable giữa threads là gì?** → Tạo formatter cục bộ cho từng lời gọi.

**10. `setRoundingMode(HALF_UP)` có thay đổi object `BigDecimal("1.005")` sau `format` không?** → Không; chỉ chuỗi hiển thị bị làm tròn theo formatter.

**Ghi nhớ:** `setParseBigDecimal(true)` giúp `DecimalFormat` trả **`BigDecimal` cho số thập phân hữu hạn được parse**, nhưng không áp dụng cho `NaN`/vô cực, không tự kiểm tra toàn bộ chuỗi và không bảo vệ khỏi mọi mất mát biểu diễn gốc. `DecimalFormat` là **mutable và không thread-safe**: mỗi luồng/lần gọi cần formatter riêng hoặc mọi truy cập chung phải được đồng bộ. Hãy phân tách **xác thực input, parse chính xác, format làm tròn và quản lý đồng thời** thành bốn trách nhiệm rõ ràng.
