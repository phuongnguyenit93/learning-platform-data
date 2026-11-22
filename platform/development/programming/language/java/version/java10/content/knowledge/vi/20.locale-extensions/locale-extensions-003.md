# Khóa `cu` cho loại tiền tệ trong Unicode Locale Extension (Java 10+)

## 1. `cu` là gì, và vì sao Java 10 hỗ trợ?

Một `Locale` trong Java mô tả ngôn ngữ, vùng và các quy ước địa phương. Thông thường, loại tiền tệ mặc định được suy ra từ **vùng**: `en-US` thường đi với `USD`, `ja-JP` với `JPY`, và `vi-VN` với `VND`. Nhưng trong thực tế, một ứng dụng có thể cần **giữ ngôn ngữ/vùng hiển thị của người dùng** mà vẫn chọn một loại tiền tệ khác để đọc hoặc trình bày giá.

**Khóa `cu`** (*currency type*) là một khóa thuộc **Unicode locale extension** trong thẻ ngôn ngữ IETF **BCP 47**. Nó yêu cầu các dịch vụ quốc tế hóa hỗ trợ khóa này sử dụng **loại tiền tệ được chỉ định**, thay vì chỉ suy ra loại tiền tệ mặc định từ vùng của locale.

Ví dụ:

~~~text
en-US             → tiếng Anh, vùng Hoa Kỳ
en-US-u-cu-eur    → tiếng Anh, vùng Hoa Kỳ, yêu cầu tiền tệ EUR
en-US-u-cu-jpy    → tiếng Anh, vùng Hoa Kỳ, yêu cầu tiền tệ JPY
vi-VN-u-cu-usd    → tiếng Việt, vùng Việt Nam, yêu cầu tiền tệ USD
~~~

Tính năng **hỗ trợ khóa `cu` trong các dịch vụ liên quan** được bổ sung ở **Java 10**, thuộc **JEP 314 — Additional Unicode Language-Tag Extensions**. Bên cạnh `cu`, Java 10 cũng bổ sung hỗ trợ phù hợp cho `fw`, `rg` và `tz`. Khả năng này **vẫn được hỗ trợ trong Java hiện đại**, nên không phải một kỹ thuật legacy.

**Kết luận quan trọng:**

- `cu` là **mã lựa chọn loại tiền tệ**, **không phải tỷ giá hối đoái**.
- `cu` **không đổi ngôn ngữ hay mã vùng cơ sở** của `Locale`.
- `cu` có thể ảnh hưởng kết quả `Currency.getInstance(locale)` và dịch vụ định dạng tiền tệ hỗ trợ extension.
- Không phải mọi dịch vụ dùng `Locale` đều bắt buộc phải hiểu mọi Unicode extension; cần đọc hợp đồng API và lưu ý dữ liệu/provider của JDK.
- Chỉ định `EUR` cho một locale `en-US` **không tự chuyển số tiền USD thành EUR**.

## 2. Đọc cú pháp `-u-cu-...` trong BCP 47

Thẻ ngôn ngữ:

~~~text
en-US-u-cu-eur
~~~

có thể phân tích thành các phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `en` | Mã ngôn ngữ: tiếng Anh |
| `US` | Vùng: Hoa Kỳ |
| `u` | Bắt đầu **Unicode locale extension** |
| `cu` | Khóa Unicode locale: **currency type** |
| `eur` | Loại tiền tệ mong muốn: **EUR** |

Cấu trúc chung:

~~~text
<language>-<region>-u-cu-<currency-type>
~~~

Đây là sơ đồ đơn giản; thẻ BCP 47 thực tế có thể có script, variant và nhiều extension. Trong các ví dụ của bài, `currency-type` là mã tiền tệ ba chữ cái, chẳng hạn `usd`, `eur`, `jpy`, `vnd` hoặc `gbp`.

**Hai cách viết ở hai tầng:**

- Trong **thẻ ngôn ngữ**, viết theo dạng chuẩn hóa BCP 47, thường là chữ thường: `en-US-u-cu-eur`.
- Khi gọi `Currency.getCurrencyCode()`, nhận **mã ISO 4217 chữ hoa**: `EUR`.

Khóa `cu` là viết tắt của **currency type**. Nó không phải tên biến tùy ý do Java phát minh; nguồn ngữ nghĩa của khóa thuộc hệ thống định danh locale của Unicode/CLDR.

### Không dùng `toString()` để phân tích BCP 47

~~~java
import java.util.Locale;

// Đoạn mã trong một phương thức:
Locale locale = Locale.forLanguageTag("en-US-u-cu-eur");

System.out.println(locale.toLanguageTag());
// en-US-u-cu-eur
~~~

`toLanguageTag()` là API phù hợp để xuất thẻ BCP 47. `Locale.toString()` có định dạng tương thích lịch sử của Java và **không nên bị tách chuỗi bằng dấu `-` như một language tag**.

## 3. Tạo Locale có `cu` bằng `Locale.forLanguageTag`

Cách ngắn gọn nhất khi đã có thẻ BCP 47:

~~~java
import java.util.Currency;
import java.util.Locale;

// Đoạn minh họa đặt trong một phương thức:
Locale us = Locale.forLanguageTag("en-US");
Locale usEuro = Locale.forLanguageTag("en-US-u-cu-eur");

System.out.println(
        Currency.getInstance(us).getCurrencyCode()); // USD

System.out.println(
        Currency.getInstance(usEuro).getCurrencyCode()); // EUR
~~~

**Giải thích:**

1. `Locale.forLanguageTag(...)` tạo một đối tượng `Locale` từ chuỗi BCP 47.
2. `Currency.getInstance(us)` lấy đơn vị tiền tệ của vùng Hoa Kỳ: `USD`.
3. `Currency.getInstance(usEuro)` nhận biết extension `cu=eur` và lấy `EUR`.
4. Phần `en-US` **không bị đổi**: locale vẫn mang ngôn ngữ `en`, vùng `US`.

Có thể truy vấn thành phần riêng:

~~~java
System.out.println(usEuro.getLanguage()); // en
System.out.println(usEuro.getCountry());  // US
System.out.println(usEuro.getUnicodeLocaleType("cu")); // eur
~~~

`getUnicodeLocaleType("cu")` trả về **giá trị của khóa Unicode** trong locale, ví dụ `eur`. Nếu locale không có khóa này, kết quả là `null`, khác với việc kiểu tiền tệ mặc định của vùng là rỗng.

**Đừng nhầm:** `Locale.forLanguageTag` xây dựng và lưu các thành phần thẻ ngôn ngữ; **chính `Currency.getInstance(locale)` mới lấy đối tượng tiền tệ** theo thông tin locale và các extension liên quan.

## 4. Tạo Locale bằng `Locale.Builder`

Khi ngôn ngữ, vùng và mã tiền tệ xuất phát từ các biến riêng, `Locale.Builder` là một phương án rõ ràng và kiểm tra **cú pháp** của các thành phần:

~~~java
import java.util.Locale;
import java.util.Currency;

// Ví dụ trong một phương thức:
Locale vietnameseWithUsd = new Locale.Builder()
        .setLanguage("vi")
        .setRegion("VN")
        .setUnicodeLocaleKeyword("cu", "usd")
        .build();

System.out.println(vietnameseWithUsd.toLanguageTag());
// vi-VN-u-cu-usd

System.out.println(
        vietnameseWithUsd.getUnicodeLocaleType("cu")); // usd

System.out.println(
        Currency.getInstance(vietnameseWithUsd).getCurrencyCode());
// USD
~~~

`setUnicodeLocaleKeyword("cu", "usd")` có hai đối số:

- `"cu"`: mã khóa Unicode locale.
- `"usd"`: giá trị loại tiền tệ được yêu cầu.

`Locale.Builder` tự chuẩn hóa chữ hoa/thường phù hợp cho key/type. Ví dụ mã được dùng chữ thường trong tag; đối tượng `Currency` vẫn có mã `USD`.

### Chọn cách tạo nào?

| Bài toán | Cách tạo phù hợp |
| --- | --- |
| Đã có thẻ BCP 47 hợp lệ từ cấu hình | `Locale.forLanguageTag("en-US-u-cu-eur")` |
| Đã có các trường language/region/currency riêng | `new Locale.Builder().setLanguage(...).setRegion(...).setUnicodeLocaleKeyword("cu", ...).build()` |
| Chỉ cần một đơn vị tiền tệ mà không cần Locale | `Currency.getInstance("EUR")` |
| Đã có Locale và muốn thêm một khóa `cu` | `new Locale.Builder().setLocale(existing).setUnicodeLocaleKeyword("cu", "eur").build()` |

**Không cần dùng các constructor `new Locale(...)` cũ** cho ví dụ mới. Java hiện đại khuyến khích các factory như `Locale.forLanguageTag`, `Locale.of` (từ Java 19) hoặc `Locale.Builder`. Đối với code cần chạy **từ Java 10**, `Locale.forLanguageTag` và `Locale.Builder` đã đủ và vẫn còn hiện hành.

### Khi muốn bỏ khóa `cu`

Theo Javadoc `Locale.Builder.setUnicodeLocaleKeyword`, truyền `null` làm type sẽ loại bỏ khóa Unicode tương ứng khỏi builder:

~~~java
Locale withoutCurrencyOverride = new Locale.Builder()
        .setLocale(vietnameseWithUsd)
        .setUnicodeLocaleKeyword("cu", null)
        .build();

System.out.println(
        withoutCurrencyOverride.getUnicodeLocaleType("cu")); // null
~~~

Sau khi bỏ override, dịch vụ tiền tệ sẽ dựa trên thông tin vùng và các extension còn lại theo quy tắc API của nó.

## 5. `Currency.getInstance(Locale)` thực sự xử lý `cu` ra sao?

`Currency` trong `java.util` đại diện cho **một loại tiền tệ**. Với `Currency.getInstance(locale)`, logic thông thường là dựa vào vùng của locale; từ Java 10, phương thức này nhận biết cả `cu` và `rg` khi các extension hợp lệ được hỗ trợ.

~~~java
import java.util.Currency;
import java.util.Locale;

// Ví dụ trong phương thức:
Locale base = Locale.forLanguageTag("en-US");
Locale euro = Locale.forLanguageTag("en-US-u-cu-eur");
Locale yen = Locale.forLanguageTag("en-US-u-cu-jpy");

Currency baseCurrency = Currency.getInstance(base);
Currency euroCurrency = Currency.getInstance(euro);
Currency yenCurrency = Currency.getInstance(yen);

System.out.println(baseCurrency.getCurrencyCode()); // USD
System.out.println(euroCurrency.getCurrencyCode()); // EUR
System.out.println(yenCurrency.getCurrencyCode());  // JPY
~~~

**Không phải `Locale` được “chuyển sang châu Âu hay Nhật Bản”:** cả ba ví dụ vẫn có `getCountry()` bằng `US`. Điều khác nhau là **loại tiền tệ được yêu cầu**.

Bảng ví dụ:

| Locale BCP 47 | Ngôn ngữ/vùng cơ sở | Yêu cầu `cu` | Mã Currency mong đợi trong JDK có hỗ trợ |
| --- | --- | --- | --- |
| `en-US` | `en`/`US` | Không có | `USD` |
| `en-US-u-cu-eur` | `en`/`US` | `eur` | `EUR` |
| `en-US-u-cu-jpy` | `en`/`US` | `jpy` | `JPY` |
| `vi-VN-u-cu-usd` | `vi`/`VN` | `usd` | `USD` |
| `ja-JP-u-cu-eur` | `ja`/`JP` | `eur` | `EUR` |

**Lưu ý lịch sử dữ liệu:** loại tiền tệ gắn với một quốc gia có thể thay đổi theo thời gian. Javadoc `Currency.getInstance(Locale)` nói rõ kết quả dựa vùng có thể thay đổi khi các quốc gia đổi tiền tệ; vì vậy **không hardcode mọi quan hệ vùng–tiền tệ như một quy luật vĩnh viễn**. Các override `cu` trực tiếp hữu ích khi ứng dụng thực sự cần mã tiền tệ xác định thay vì suy ra từ vùng.

### Currency không phải số tiền

~~~java
Currency currency = Currency.getInstance("EUR");

String isoCode = currency.getCurrencyCode(); // EUR
~~~

`Currency` **không lưu số lượng tiền**; nó mô tả đơn vị. Một giao dịch thường cần cả **số tiền** (ví dụ `BigDecimal`) và **mã Currency**. Không lấy kết quả `Currency.getInstance(locale)` rồi suy ra rằng Java đã tính ra giá trị tiền mới.

## 6. Ưu tiên giữa `cu` và `rg`

Khóa Unicode `rg` (*region override*) có thể yêu cầu dùng quy tắc vùng khác với region cơ sở của thẻ. Trong ngữ cảnh tiền tệ, `Currency.getInstance(Locale)` từ Java 10 hỗ trợ cả `cu` lẫn `rg`.

Ví dụ, một locale có `en-US` nhưng yêu cầu quy tắc vùng `GB`:

~~~java
Locale britishRules = Locale.forLanguageTag(
        "en-US-u-rg-gbzzzz");

System.out.println(
        Currency.getInstance(britishRules).getCurrencyCode());
// GBP (theo dữ liệu vùng GB hiện hành)
~~~

Phần giá trị `gbzzzz` là định dạng chuẩn được dùng cho khóa `rg`: **mã vùng `GB` đi kèm hậu tố `zzzz`**. Đây **không phải** một mã tiền tệ. Nó yêu cầu quy tắc địa phương áp dụng vùng GB ở những API có hỗ trợ extension này.

Khi có **cả `cu` và `rg`**, **`cu` được ưu tiên** trong quyết định đơn vị tiền tệ:

~~~java
Locale combined = Locale.forLanguageTag(
        "en-US-u-cu-jpy-rg-gbzzzz");

System.out.println(
        Currency.getInstance(combined).getCurrencyCode()); // JPY
~~~

Tại đây:

1. Locale cơ sở là `en-US`.
2. `rg=gbzzzz` yêu cầu quy tắc vùng GB.
3. `cu=jpy` yêu cầu tiền tệ JPY.
4. **Kết quả là `JPY`**, không phải `USD` hay `GBP`.

Quy tắc ưu tiên này được nêu trong Javadoc Java SE hiện hành: nếu cả `cu` và `rg` xuất hiện, giá trị `cu` **thay thế loại tiền tệ ngầm định do `rg` chỉ ra**.

**Không suy luận** rằng `cu` loại bỏ toàn bộ tác động `rg` đối với những dữ liệu locale khác. `cu` tập trung vào **tiền tệ**; `rg` có thể ảnh hưởng các quy ước vùng khác ở những API có hỗ trợ.

## 7. `NumberFormat.getCurrencyInstance` và khóa `cu`

`Currency.getInstance(locale)` lấy **đơn vị tiền tệ**; `NumberFormat.getCurrencyInstance(locale)` tạo một **bộ định dạng giá trị tiền** theo quy tắc locale.

~~~java
import java.text.NumberFormat;
import java.util.Locale;

// Trong phương thức:
Locale locale = Locale.forLanguageTag("en-US-u-cu-eur");

NumberFormat formatter =
        NumberFormat.getCurrencyInstance(locale);

System.out.println(
        formatter.getCurrency().getCurrencyCode()); // EUR
~~~

Với các dịch vụ locale hỗ trợ `cu` trong JDK hiện hành, định dạng được tạo bằng `NumberFormat.getCurrencyInstance(locale)` có thể dùng đơn vị tiền tệ do `cu` chỉ định. Cần phân biệt:

- **Loại tiền tệ:** `formatter.getCurrency()`.
- **Quy tắc trình bày:** ký hiệu, dấu phân cách hàng nghìn, dấu thập phân, khoảng trắng, mẫu hiển thị... còn dựa vào locale và dữ liệu quốc tế hóa.
- **Số tiền:** giá trị truyền vào `formatter.format(amount)`, **không được chuyển đổi tỷ giá**.

Ví dụ:

~~~java
NumberFormat formatter = NumberFormat.getCurrencyInstance(
        Locale.forLanguageTag("en-US-u-cu-eur"));

String formatted = formatter.format(1234.50);
// Chuỗi minh họa chịu ảnh hưởng của provider/CLDR.
// Không cố định một literal để kiểm thử xuyên mọi JDK/locale.
~~~

Một bản JDK với dữ liệu CLDR nhất định có thể hiển thị biểu tượng euro theo cách riêng. **Không viết kiểm thử bắt buộc chính xác ký hiệu hoặc vị trí khoảng trắng** nếu mục tiêu là xác nhận `cu` đã chọn đúng đơn vị tiền tệ. Hãy dùng:

~~~java
String code = formatter.getCurrency().getCurrencyCode();
System.out.println(code.equals("EUR")); // true
~~~

### `cu` khác `cf`

Trong Java hiện đại còn có khóa `cf` liên quan đến **currency format style**, ví dụ `cf=account` để yêu cầu cách hiển thị số âm kiểu kế toán khi provider hỗ trợ.

- **`cu`**: chọn **loại tiền tệ** (`EUR`, `USD`, `JPY`...).
- **`cf`**: chọn **phong cách định dạng tiền tệ**, không tự xác định loại tiền tệ.
- **`nu`**: chọn **hệ chữ số**, không tự xác định tiền tệ.
- **`rg`**: yêu cầu **quy tắc vùng** với các dịch vụ có hỗ trợ.

Không nên lẫn lộn các khóa vì chúng có thể cùng xuất hiện dưới extension `-u-`. Bài này tập trung vào **`cu`** được Java 10 mở rộng hỗ trợ; các khóa khác được nhắc để phân biệt chức năng hiện hành.

### `NumberFormat.setCurrency` không đồng nghĩa tạo formatter mới

~~~java
NumberFormat existing =
        NumberFormat.getCurrencyInstance(Locale.US);

existing.setCurrency(Currency.getInstance("JPY"));
~~~

`setCurrency` thay **đơn vị tiền tệ được liên kết** với formatter, nhưng Javadoc nói rõ phương thức này **không tự cập nhật giá trị minimum/maximum fraction digits**. Nếu mục tiêu là định dạng tiền tệ theo toàn bộ quy tắc locale mới, nên tạo formatter mới từ locale phù hợp, hoặc cấu hình chi tiết một cách có chủ đích.

Đây là lý do việc chọn loại tiền tệ không đồng nghĩa với mọi quy tắc định dạng tự được cập nhật theo cách bạn kỳ vọng.

## 8. Chọn mã tiền tệ hợp lệ và xử lý dữ liệu không tin cậy

Một giá trị `cu` theo Unicode locale data thường dùng mã tiền tệ ba chữ cái theo ISO 4217 hoặc mã được định nghĩa trong dữ liệu Unicode/CLDR.

~~~text
usd   eur   jpy   vnd   gbp
~~~

Nhưng cần phân biệt **hợp lệ về cú pháp** và **được runtime hỗ trợ về ngữ nghĩa**:

- `Locale.Builder.setUnicodeLocaleKeyword` kiểm tra tính **well-formed** của khóa/type Unicode extension, không phải một dịch vụ kiểm tra mọi mã tiền tệ hiện hành.
- `Locale.forLanguageTag` phân tích language tag BCP 47, không phải trình xác minh mã ISO 4217 của nghiệp vụ.
- `Currency.getInstance(String)` yêu cầu một **mã tiền tệ được Java hỗ trợ**; mã không được hỗ trợ sẽ gây `IllegalArgumentException`.
- Dữ liệu tiền tệ, trạng thái mã hiện hành/lịch sử và provider có thể thay đổi theo phiên bản JDK.

Nếu người dùng nhập mã tiền tệ dưới dạng chuỗi, có thể chuẩn hóa và xác thực **trước khi** xây Locale:

~~~java
import java.util.Currency;
import java.util.Locale;

// Trong phương thức:
String inputCode = "eur"; // Ví dụ đến từ cấu hình đáng tin cậy.

String canonicalCode =
        inputCode.trim().toUpperCase(Locale.ROOT);

Currency selected = Currency.getInstance(canonicalCode);
// Nếu mã không được hỗ trợ, có thể ném IllegalArgumentException.

Locale locale = new Locale.Builder()
        .setLanguage("en")
        .setRegion("US")
        .setUnicodeLocaleKeyword(
                "cu",
                selected.getCurrencyCode().toLowerCase(Locale.ROOT))
        .build();
~~~

**Đừng chỉ kiểm tra regex `[A-Za-z]{3}`** rồi xem đó là mã tiền tệ Java hỗ trợ. Độ dài ba chữ là điều kiện cú pháp phổ biến, nhưng chưa chắc là mã đã đăng ký. Trong ứng dụng thanh toán, còn cần kiểm tra **danh sách loại tiền tệ mà nghiệp vụ thực tế hỗ trợ**, không chỉ kiểm tra trong Java.

Với đầu vào không tin cậy, cần bắt và xử lý lỗi đầu vào có chủ đích. Không tự chọn một mã dự phòng im lặng nếu điều đó có thể làm thay đổi đơn vị tiền tệ của giao dịch.

### Tránh giả định “mọi Locale luôn có Currency”

Javadoc `Currency.getInstance(Locale)` nói rằng có những vùng **không có loại tiền tệ**, do đó kết quả có thể là **`null`**. Nó cũng có thể ném `IllegalArgumentException` khi vùng không được hỗ trợ và `NullPointerException` khi đối số locale là null. Vì vậy khi dùng các locale động/ít gặp, không nên luôn dereference kết quả một cách mù quáng.

~~~java
Currency resolved = Currency.getInstance(locale);

if (resolved == null) {
    // Ứng dụng quyết định cách xử lý vùng không có tiền tệ.
}
~~~

Đoạn trên minh họa trong phương thức, với `locale` đã tồn tại và có dữ liệu hợp lệ. Một locale có `cu` hợp lệ có thể yêu cầu đơn vị rõ ràng; nhưng vẫn cần xử lý đúng các trường hợp dữ liệu cấu hình không hợp lệ.

## 9. Chương trình đầy đủ: `cu`, `rg`, Builder và NumberFormat

Lưu mã sau thành tệp **`CurrencyCuDemo.java`**. Ví dụ dùng các API có mặt từ Java 10 hoặc trước đó và chạy tốt với **JDK 17+**.

~~~java
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class CurrencyCuDemo {

    public static void main(String[] args) {
        Locale us = Locale.forLanguageTag("en-US");
        Locale eur = Locale.forLanguageTag("en-US-u-cu-eur");
        Locale jpy = Locale.forLanguageTag("en-US-u-cu-jpy");

        Locale viUsd = new Locale.Builder()
                .setLanguage("vi")
                .setRegion("VN")
                .setUnicodeLocaleKeyword("cu", "usd")
                .build();

        Locale rg = Locale.forLanguageTag(
                "en-US-u-rg-gbzzzz");

        Locale both = Locale.forLanguageTag(
                "en-US-u-cu-jpy-rg-gbzzzz");

        System.out.println("base=" + us.toLanguageTag());
        System.out.println("euTag=" + eur.toLanguageTag());
        System.out.println(
                "cuType=" + eur.getUnicodeLocaleType("cu"));

        System.out.println("usCurrency="
                + Currency.getInstance(us).getCurrencyCode());
        System.out.println("overrideEUR="
                + Currency.getInstance(eur).getCurrencyCode());
        System.out.println("overrideJPY="
                + Currency.getInstance(jpy).getCurrencyCode());

        System.out.println("vnTag=" + viUsd.toLanguageTag());
        System.out.println("vnCurrency="
                + Currency.getInstance(viUsd).getCurrencyCode());

        System.out.println("rgCurrency="
                + Currency.getInstance(rg).getCurrencyCode());
        System.out.println("combinedCurrency="
                + Currency.getInstance(both).getCurrencyCode());

        // Kiểm tra mã đơn vị; không phụ thuộc chuỗi ký hiệu tiền tệ.
        System.out.println("formatterEUR="
                + NumberFormat.getCurrencyInstance(eur)
                        .getCurrency().getCurrencyCode());
        System.out.println("formatterJPY="
                + NumberFormat.getCurrencyInstance(jpy)
                        .getCurrency().getCurrencyCode());
        System.out.println("formatterVNUSD="
                + NumberFormat.getCurrencyInstance(viUsd)
                        .getCurrency().getCurrencyCode());

        System.out.println("sameLocaleCountry="
                + us.getCountry().equals(eur.getCountry()));

        System.out.println("selectedCode="
                + Currency.getInstance("EUR").getCurrencyCode());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CurrencyCuDemo.java
java CurrencyCuDemo
~~~

**`stdout` được kiểm thử trên JDK 24 với dữ liệu locale tiêu chuẩn:**

~~~text
base=en-US
euTag=en-US-u-cu-eur
cuType=eur
usCurrency=USD
overrideEUR=EUR
overrideJPY=JPY
vnTag=vi-VN-u-cu-usd
vnCurrency=USD
rgCurrency=GBP
combinedCurrency=JPY
formatterEUR=EUR
formatterJPY=JPY
formatterVNUSD=USD
sameLocaleCountry=true
selectedCode=EUR
~~~

Cách đọc kết quả:

1. `euTag=en-US-u-cu-eur` và `cuType=eur`: `Locale` đã lưu extension `cu` theo thẻ BCP 47.
2. `usCurrency=USD`: locale Hoa Kỳ không override suy ra đơn vị USD từ vùng.
3. `overrideEUR=EUR`, `overrideJPY=JPY`: chính khóa `cu` chọn đơn vị tiền tệ khác, **không thay vùng US**.
4. `vnTag=vi-VN-u-cu-usd` và `vnCurrency=USD`: `Locale.Builder` tạo extension `cu` chính xác.
5. `rgCurrency=GBP`: với `rg=gbzzzz`, quy tắc vùng GB chọn GBP trong bộ dữ liệu hiện hành.
6. `combinedCurrency=JPY`: khi có cả `rg` và `cu`, **`cu` được ưu tiên** để chọn đơn vị tiền tệ.
7. Ba dòng `formatter...` đọc **mã của Currency đang được NumberFormat sử dụng**, tránh phụ thuộc biểu tượng hiển thị và khoảng trắng giữa các quốc gia.
8. `sameLocaleCountry=true` chứng minh `cu` không đổi trường vùng cơ sở của Locale.
9. `selectedCode=EUR` cho thấy có thể lấy trực tiếp một `Currency` từ mã ISO 4217 mà không cần xây Locale khi không muốn biểu diễn ngữ cảnh địa phương.

**Giới hạn của `stdout`:** Đây là kết quả theo bộ dữ liệu và locale provider tiêu chuẩn của JDK được thử. Tài liệu `NumberFormat` lưu ý provider có thể không hỗ trợ mọi extension; không nên hứa tuyệt đối mọi phiên bản/triển khai Java tùy biến có biểu tượng, pattern hoặc fraction digits giống nhau. Riêng nội dung về cơ chế `cu` và thứ tự ưu tiên `cu`/`rg` dựa trên đặc tả Java hiện hành.

## 10. Khóa `cu` không thực hiện quy đổi tỷ giá

Một hiểu nhầm nguy hiểm trong ứng dụng tài chính là xem việc đổi `USD` sang `EUR` bằng `cu` như một phép đổi tiền.

~~~java
Locale displayLocale =
        Locale.forLanguageTag("en-US-u-cu-eur");

NumberFormat format =
        NumberFormat.getCurrencyInstance(displayLocale);

String displayed = format.format(100);
// Đây là cách ĐỊNH DẠNG số 100 với đơn vị được chọn.
// Không có bước tự chuyển 100 USD thành số EUR tương ứng.
~~~

**`cu` chỉ chọn đơn vị của biểu diễn tiền tệ**, không lưu hay tìm tỷ giá, không tính toán số lượng đơn vị mới.

Ví dụ nghiệp vụ: hệ thống đã có giá **100 USD**. Muốn biểu diễn số tiền tương đương bằng **EUR**, cần:

1. Xác định nguồn và thời điểm tỷ giá `USD → EUR` theo chính sách nghiệp vụ.
2. Tính toán bằng loại số phù hợp (thường dùng `BigDecimal`).
3. Áp dụng quy tắc làm tròn/đơn vị phụ phù hợp với kết quả.
4. Gắn rõ Currency `EUR` cho giá trị sau khi đã quy đổi.
5. Dùng locale/formatter phù hợp để **trình bày** giá trị đó.

Nếu bỏ bước quy đổi mà chỉ thay `cu=eur`, chương trình có thể hiển thị **100 EUR** trong khi dữ liệu gốc vẫn là **100 USD**, gây sai nghĩa tiền tệ nghiêm trọng.

### Với tiền nên dùng `BigDecimal`

~~~java
import java.math.BigDecimal;
import java.util.Currency;

// Đây là dữ liệu mô hình hóa ví dụ, không phải tỷ giá thị trường.
BigDecimal amount = new BigDecimal("100.00");
Currency unit = Currency.getInstance("USD");
~~~

`BigDecimal` xử lý số thập phân chính xác hơn `double` cho nhiều phép tính tiền tệ. Tuy nhiên nó cũng **không tự thực hiện quy đổi tỷ giá** hoặc tự biết quy tắc hạch toán. Cần thiết kế nghiệp vụ đầy đủ.

## 11. Mã `cu`, ký hiệu, quy tắc phần thập phân và locale provider

### Đừng nhầm ISO code với ký hiệu hiển thị

`USD` và `EUR` là **mã tiền tệ**; ký hiệu `$` và `€` là dữ liệu phục vụ hiển thị. Ký hiệu có thể thay đổi theo locale hoặc theo quy tắc phân biệt nhiều đồng tiền dùng chung biểu tượng.

~~~java
Currency currency = Currency.getInstance("EUR");

String code = currency.getCurrencyCode(); // EUR
String symbol = currency.getSymbol(Locale.US);
// symbol phụ thuộc dữ liệu hiển thị của locale.
~~~

Để truyền dữ liệu giữa các hệ thống, **mã tiền tệ** thường rõ ràng hơn ký hiệu. Một ký hiệu không phải một định danh duy nhất cho mọi loại tiền tệ.

### Fraction digits không phải tỷ giá

`Currency.getDefaultFractionDigits()` trả về số chữ số thập phân mặc định cho Currency trong dữ liệu runtime, ví dụ **USD thường là 2**, **JPY thường là 0**. Điều đó là quy tắc biểu diễn đơn vị phụ; **không có nghĩa JPY được tính bằng 100 lần USD** hay tương tự.

~~~java
Currency usd = Currency.getInstance("USD");
Currency jpy = Currency.getInstance("JPY");

// Ví dụ theo dữ liệu thông dụng:
System.out.println(usd.getDefaultFractionDigits()); // 2
System.out.println(jpy.getDefaultFractionDigits()); // 0
~~~

Với ứng dụng thanh toán, hãy đối chiếu quy tắc làm tròn, chữ số phần thập phân và dữ liệu tiền tệ mà nghiệp vụ thực sự hỗ trợ. Một số loại tiền tệ đặc biệt có thể không có giá trị chữ số phần thập phân thông thường.

### Kết quả có thể phụ thuộc dữ liệu địa phương

Java sử dụng locale data provider, thường gồm dữ liệu **CLDR**. Phiên bản dữ liệu này có thể thay đổi qua JDK, các provider cài đặt thêm có thể ảnh hưởng biểu tượng và mẫu định dạng. Việc cắt giảm module locale data trong một runtime tùy biến cũng có thể thay đổi khả năng hiển thị với một locale cụ thể.

**Vì thế:** nếu muốn kiểm tra `cu`, hãy ưu tiên đọc `getUnicodeLocaleType("cu")` và `Currency.getCurrencyCode()`, hơn là cố định chuỗi đã format chứa ký hiệu, khoảng trắng, dấu thập phân trong bài test không kiểm soát provider.

## 12. Các lưu ý khi sử dụng trong ứng dụng

### Đừng sửa `Locale` toàn cục chỉ để định dạng một giá trị

~~~java
// Không cần thay Locale mặc định của toàn JVM:
Locale requested = Locale.forLanguageTag("en-US-u-cu-eur");

NumberFormat formatter =
        NumberFormat.getCurrencyInstance(requested);
~~~

Ưu tiên truyền **`Locale` tường minh** tới API cần nó. Gọi `Locale.setDefault(...)` thay default JVM có thể ảnh hưởng những đoạn code khác cùng tiến trình, nhất là trong dịch vụ có nhiều người dùng.

### `Locale` và `Currency` không phải nơi lưu trạng thái thay đổi liên tục

Các đối tượng `Locale` và `Currency` dùng để mô tả thuộc tính quốc tế hóa/đơn vị. Không dùng chúng như một cache tỷ giá hoặc nơi lưu giá tiền đang biến động.

### `NumberFormat` không được bảo đảm an toàn đồng thời

Theo Javadoc, các đối tượng `NumberFormat` nói chung **không synchronized**. Nếu nhiều luồng cùng dùng một instance và có thao tác đọc/đổi cấu hình, cần kiểm soát đồng bộ. Cách đơn giản là **tạo formatter riêng cho từng luồng/lượt xử lý** hoặc có giao thức quản lý instance an toàn.

### Xác thực quyết định tiền tệ theo nghiệp vụ

Một người dùng có thể chọn locale `vi-VN-u-cu-usd` để xem báo giá bằng USD. Điều đó chỉ xác định **đơn vị được yêu cầu để trình bày**. Hệ thống vẫn phải kiểm tra:

- Đồng tiền giao dịch có được phép sử dụng trong thị trường/sản phẩm cụ thể không?
- Giá gốc là đồng nào?
- Có cần tỷ giá, thuế, phí và làm tròn theo đơn vị tiền tệ không?
- Đơn vị hiển thị có nhất quán với đơn vị được thanh toán/lưu trữ không?
- Có phải locale được người dùng tự nhập từ nguồn thiếu tin cậy không?

Đừng tin một chuỗi `cu` từ client như bằng chứng đơn vị thanh toán thực tế. Định danh tiền tệ phải được xác nhận theo dữ liệu giao dịch ở phía xử lý nghiệp vụ.

## 13. Các lỗi hay gặp

| Sai lầm | Giải thích đúng |
| --- | --- |
| “`cu` là tên quốc gia.” | `cu` chọn loại tiền tệ, không thay `getCountry()`. |
| “`en-US-u-cu-eur` là tiếng Anh ở châu Âu.” | Vùng cơ sở vẫn `US`; chỉ yêu cầu tiền tệ EUR. |
| “`cu` thực hiện quy đổi tỷ giá.” | Không; nó không tính hay lưu tỷ giá. |
| “`getUnicodeLocaleType("cu")` trả `EUR`.” | Thường nhận `eur` theo chuẩn tag; mã `Currency` lấy qua `getCurrencyCode()` là `EUR`. |
| “`rg` có quyền ưu tiên hơn `cu` khi chọn tiền tệ.” | Theo `Currency.getInstance(Locale)`, `cu` **ưu tiên** hơn loại tiền tệ ngầm định từ `rg`. |
| “Locale có `cu` nên mọi API quốc tế hóa đều phải hiểu `cu`.” | Hợp đồng hỗ trợ tùy API/provider; không thể suy rộng. |
| “Có thể dùng `Locale.Builder` để kiểm tra toàn bộ mã tiền tệ ISO.” | Builder kiểm tra cú pháp; cần xác thực hỗ trợ/nghiệp vụ riêng. |
| “`NumberFormat` sẽ in ký hiệu giống nhau ở mọi JDK.” | Mẫu/ký hiệu phụ thuộc locale và dữ liệu/provider. |
| “Đổi `formatter.setCurrency` tự cập nhật fraction digits.” | Javadoc nói rõ không tự cập nhật min/max fraction digits. |
| “Nên dùng `new Locale("en", "US")` cho mã Java mới.” | Constructor đã deprecated trong Java hiện đại; dùng `forLanguageTag`/`Builder` hoặc factory phù hợp. |
| “Mỗi thẻ Locale luôn suy ra được một loại tiền tệ.” | Một số vùng không có currency; còn có trường hợp cấu hình không hợp lệ. |
| “Có thể dùng ký hiệu `$` thay mã ISO 4217 trong dữ liệu giao dịch.” | Ký hiệu có thể mơ hồ; lưu mã tiền tệ rõ ràng. |

## 14. Bài tập tự kiểm tra

### Câu 1: `cu` thay đổi điều gì?

~~~java
Locale locale = Locale.forLanguageTag("en-US-u-cu-jpy");
~~~

**Đáp án:** Locale cơ sở vẫn `en-US`, khóa `cu` yêu cầu tiền tệ `JPY` cho các API hỗ trợ. `locale.getCountry()` vẫn trả `US`. Không có bước tự động chuyển đổi một số tiền USD sang JPY.

### Câu 2: Cùng vùng, khác tiền tệ

~~~java
Locale us = Locale.forLanguageTag("en-US");
Locale usEuro = Locale.forLanguageTag("en-US-u-cu-eur");
~~~

Kết quả `Currency.getInstance(...)` cho hai đối tượng là gì?

**Đáp án:** `USD` và `EUR` theo dữ liệu tiêu chuẩn hiện hành. `getCountry()` của cả hai đều là `US`.

### Câu 3: Khi `cu` và `rg` cùng xuất hiện

~~~java
Locale locale = Locale.forLanguageTag(
        "en-US-u-cu-jpy-rg-gbzzzz");
~~~

Loại tiền tệ nào có quyền ưu tiên, và mã Currency là gì?

**Đáp án:** `cu=jpy` ưu tiên hơn tiền tệ ngầm định do `rg=gbzzzz`, nên `Currency.getInstance(locale).getCurrencyCode()` là `JPY`.

### Câu 4: Đọc giá trị extension

~~~java
Locale locale = Locale.forLanguageTag("vi-VN-u-cu-usd");
System.out.println(locale.getUnicodeLocaleType("cu"));
~~~

**Đáp án:** In `usd`. Hàm này đọc type của extension; nếu muốn mã tiền tệ ISO chữ hoa, dùng `Currency.getInstance(locale).getCurrencyCode()` và nhận `USD`.

### Câu 5: Một con số được định dạng thành EUR đã được quy đổi?

Ứng dụng có giá gốc `100 USD` và gọi `NumberFormat.getCurrencyInstance(Locale.forLanguageTag("en-US-u-cu-eur")).format(100)`. Điều này đã tính số EUR tương đương chưa?

**Đáp án:** **Chưa.** Formatter chỉ trình bày con số `100` bằng quy ước tiền tệ được chọn. Cần thực hiện chuyển đổi tỷ giá theo nghiệp vụ trước khi hiển thị một số tiền thực sự định giá bằng EUR.

### Câu 6: Chọn API tạo Locale

Khi một hệ thống có ba biến `language="vi"`, `region="VN"`, `currency="USD"` và cần code Java 10+, có thể tạo Locale như thế nào?

~~~java
var locale = new Locale.Builder()
        .setLanguage("vi")
        .setRegion("VN")
        .setUnicodeLocaleKeyword("cu", "usd")
        .build();
~~~

**Đáp án:** Đúng; kết quả `toLanguageTag()` là `vi-VN-u-cu-usd`. Dùng builder hiện hành, không cần constructor Locale deprecated.

### Câu 7: Cần kiểm thử điều gì cho `cu`?

**Đáp án:** Kiểm tra `getUnicodeLocaleType("cu")`, `Currency.getInstance(locale).getCurrencyCode()`, và khi cần `NumberFormat.getCurrencyInstance(locale).getCurrency().getCurrencyCode()`. Không mặc định kiểm tra chuỗi ký hiệu `$`/`€` với dấu cách hoặc quy tắc phân cách giống nhau trên mọi provider.

## 15. Tổng kết

- **`cu` là khóa Unicode locale extension cho `currency type`**, được Java 10 mở rộng hỗ trợ theo **JEP 314**, và vẫn dùng được ở Java hiện đại.
- Thẻ như **`en-US-u-cu-eur`** giữ language/region cơ sở `en-US` nhưng yêu cầu **EUR** thay vì tiền tệ mặc định vùng Hoa Kỳ.
- Tạo locale bằng **`Locale.forLanguageTag`** hoặc **`Locale.Builder.setUnicodeLocaleKeyword("cu", "...")`**; đọc khóa bằng **`getUnicodeLocaleType("cu")`**.
- **`Currency.getInstance(Locale)`** nhận biết `cu`; **khi có cả `cu` và `rg`, `cu` được ưu tiên** để quyết định loại tiền tệ.
- **`NumberFormat.getCurrencyInstance(locale)`** có thể sử dụng loại tiền tệ đó trong môi trường hỗ trợ, nhưng kiểu hiển thị và ký hiệu phụ thuộc locale/provider.
- **Không nhầm chọn currency với đổi tỷ giá**; `Currency` không chứa số tiền, còn `cu` không thay đổi giá trị số.
- **Xác thực mã Currency và nghiệp vụ**, ưu tiên mã ISO rõ ràng; cân nhắc dữ liệu CLDR và cách quản lý formatter trong ứng dụng nhiều luồng.

### Tham khảo chính thức và hiện hành

1. [OpenJDK — JEP 314: Additional Unicode Language-Tag Extensions](https://openjdk.org/jeps/314) — nguồn gốc hỗ trợ `cu`/`rg` từ Java 10.
2. [Java SE 26 — `Currency.getInstance(Locale)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Currency.html#getInstance(java.util.Locale)) — quy tắc `cu`/`rg` và thứ tự ưu tiên.
3. [Java SE 26 — `Locale`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html) — language tags, Unicode extensions, `getUnicodeLocaleType`.
4. [Java SE 26 — `Locale.Builder.setUnicodeLocaleKeyword`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.Builder.html#setUnicodeLocaleKeyword(java.lang.String,java.lang.String)) — tạo và thay đổi khóa Unicode.
5. [Java SE 26 — `NumberFormat`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/NumberFormat.html) — locale extensions, currency formatting, provider và synchronization.
6. [Unicode UTS #35 — Unicode Currency Identifier](https://unicode.org/reports/tr35/) — định nghĩa khóa `cu` trong CLDR/LDML.
7. [Oracle — Supported Locales in JDK 26](https://www.oracle.com/java/technologies/javase/jdk26-supported-locales.html) — provider và Unicode locale extensions được hỗ trợ.
