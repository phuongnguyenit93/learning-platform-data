# Ký hiệu, tên hiển thị và số chữ số phần lẻ mặc định của tiền tệ trong Java

## 1. Bài toán: “USD” không đồng nghĩa “$”, và không phải tiền nào cũng có hai chữ số thập phân

Ứng dụng bán hàng, kế toán và thương mại quốc tế thường cần hiển thị số tiền phù hợp với ngôn ngữ của người đọc. Ví dụ, cùng một số tiền bằng đô la Mỹ có thể được diễn đạt bằng mã `USD`, ký hiệu `$` hoặc `US$`, hoặc tên “US Dollar” / “Đô la Mỹ”. Một số tiền bằng yên Nhật thường hiển thị không có phần lẻ; đồng dinar Kuwait lại có **ba** chữ số phần lẻ trong metadata của Java.

Để xử lý đúng, cần tách ba thông tin:

1. **Đơn vị tiền tệ** — nhận diện bằng mã ISO 4217 như `USD`, `JPY`, `VND`, `KWD`.
2. **Ngôn ngữ/vùng để hiển thị** — lựa chọn bằng `Locale`, quyết định ký hiệu hoặc tên được bản địa hóa.
3. **Số chữ số phần lẻ mặc định** — thông tin gắn với đơn vị tiền tệ, truy cập qua `Currency.getDefaultFractionDigits()`.

Trong Java, `java.util.Currency` mô tả **đơn vị tiền tệ**, còn `java.text.NumberFormat` hoặc `java.text.DecimalFormat` đảm nhiệm **định dạng số tiền**. Không nên suy ra tiền tệ chỉ từ một dấu `$`, và cũng không nên cho rằng mọi số tiền đều có `2` chữ số sau dấu thập phân.

**Mục tiêu bài học:** hiểu chính xác các API `getCurrencyCode()`, `getSymbol(Locale)`, `getDisplayName(Locale)`, `getDefaultFractionDigits()`; biết vai trò của `Locale`; áp dụng metadata khi định dạng; và phân biệt mức chữ số mặc định với quy tắc thanh toán thực tế.

## 2. Currency là gì, có phải số tiền không?

Một đối tượng `Currency` là metadata của **một đơn vị tiền tệ**. Nó không chứa số lượng tiền. Hai giá trị:

```text
amount = 1234.50
currency = USD
```

kết hợp mới mô tả một số tiền. `Currency.getInstance("USD")` tạo/lấy đối tượng cho đơn vị USD, nhưng không chứa `1234.50` và không thể tự tính tổng hay đổi tỷ giá.

Ví dụ các mã thường gặp:

| Mã ISO 4217 | Đơn vị | Chữ số phần lẻ mặc định trong Java |
| --- | --- | ---: |
| `USD` | Đô la Mỹ | 2 |
| `EUR` | Euro | 2 |
| `JPY` | Yên Nhật | 0 |
| `VND` | Đồng Việt Nam | 0 |
| `KWD` | Dinar Kuwait | 3 |
| `XXX` | Mã “không có tiền tệ” trong ISO 4217 | -1 |

Các giá trị phản ánh metadata trong JDK/ISO 4217 tại thời điểm cung cấp dữ liệu; dữ liệu tiền tệ có thể được cập nhật giữa các bản JDK. `XXX` là một mã đặc biệt, không phải tiền tệ có thể dùng để thanh toán.

Những API chính:

| API | Vai trò |
| --- | --- |
| `Currency.getInstance("USD")` | Chọn đơn vị tiền tệ theo mã ISO 4217 |
| `Currency.getInstance(locale)` | Xác định tiền tệ của vùng/thuộc tính `cu` trong locale khi có đủ dữ liệu |
| `getCurrencyCode()` | Mã ISO 4217, ví dụ `"USD"` |
| `getNumericCode()` | Mã số ISO 4217, ví dụ 840 cho USD |
| `getNumericCodeAsString()` | Mã số ISO 4217 dưới dạng chuỗi 3 chữ số |
| `getSymbol(locale)` | Ký hiệu để hiển thị phù hợp locale |
| `getDisplayName(locale)` | Tên tiền tệ được bản địa hóa theo locale |
| `getDefaultFractionDigits()` | Số chữ số phần lẻ mặc định của đơn vị tiền tệ |

`Currency` khác `Locale`: một locale có thể gợi ý tiền tệ thông dụng của vùng, nhưng một locale không chứa **số tiền**. Một website dùng giao diện tiếng Việt vẫn có thể báo giá USD, EUR, JPY hoặc bất kỳ đơn vị nào được hỗ trợ. Không tự chuyển đơn vị tiền tệ chỉ vì người dùng đổi ngôn ngữ.

## 3. Mã tiền tệ, ký hiệu và tên hiển thị khác nhau ra sao?

### 3.1. `getCurrencyCode()`: mã nhận diện ổn định

`Currency.getInstance("USD").getCurrencyCode()` trả về `"USD"`. Mã ISO là dữ liệu kỹ thuật được dùng để mô tả **đơn vị** trong API, cơ sở dữ liệu, báo cáo và giao tiếp giữa các dịch vụ.

Mã `USD` không biến thành `VND` khi đổi locale hiển thị. Muốn chuyển đổi giá trị từ USD sang VND, cần quy tắc tỷ giá và thời điểm áp dụng ở tầng nghiệp vụ; `Currency` không tự đổi tỷ giá.

### 3.2. `getSymbol(Locale)`: ký hiệu phụ thuộc ngữ cảnh hiển thị

`getSymbol(Locale.US)` lấy ký hiệu phù hợp với người đọc theo locale Mỹ. Với USD, thường là `$`. Khi hiển thị USD trong ngữ cảnh Việt Nam, Java có thể dùng `US$` để phân biệt với tiền khác có ký hiệu đô la.

**Không coi ký hiệu là khóa định danh duy nhất.** Nhiều loại tiền khác nhau dùng hoặc chia sẻ dạng ký hiệu `$`; ký hiệu `¥` cũng cần ngữ cảnh để phân biệt yên Nhật và các đơn vị khác. Cần lưu mã tiền tệ bên cạnh số tiền trong model, không chỉ lưu một ký tự ký hiệu.

Ký hiệu do dữ liệu locale của JDK và nhà cung cấp dữ liệu bản địa hóa quyết định. Việc viết cứng `"$"`, `"¥"` hoặc `"₫"` trong logic chung sẽ làm mất khả năng hiển thị tự nhiên ở nhiều locale.

### 3.3. `getDisplayName(Locale)`: tên có thể dịch

`getDisplayName(Locale.US)` cho tên tiền tệ theo tiếng Anh Mỹ. `getDisplayName(Locale.forLanguageTag("vi-VN"))` cố lấy tên theo tiếng Việt. Với USD, tên có thể là “US Dollar” và “Đô la Mỹ” trong dữ liệu JDK/CLDR tương ứng.

Tên này dùng phù hợp trong danh sách chọn tiền tệ, phần giải thích giao dịch hoặc nhãn trợ năng. Một số giao diện nên hiển thị **mã và tên**:

```text
USD — Đô la Mỹ
JPY — Yên Nhật
VND — Đồng Việt Nam
```

Đây là cách diễn đạt minh họa; chuỗi chính xác do dữ liệu bản địa hóa xác định. Nếu không có tên được bản địa hóa, API có thể dự phòng bằng mã tiền tệ. Khi cần nội dung pháp lý hoặc tên thương mại chuẩn của tổ chức, hãy dùng danh mục nội bộ được quản trị và dịch thuật, thay vì giả định mọi tên của JDK đáp ứng hợp đồng đó.

### 3.4. Overload không có Locale

`currency.getSymbol()` và `currency.getDisplayName()` sử dụng locale mặc định thích hợp của JVM. Trong ứng dụng web nhiều người dùng, nên truyền `Locale` cụ thể:

```java
currency.getSymbol(viewerLocale);
currency.getDisplayName(viewerLocale);
```

Không gọi `Locale.setDefault` cho từng request để đổi ngôn ngữ; đó là trạng thái dùng chung của JVM, có thể ảnh hưởng các request song song.

## 4. Ví dụ Java 17+: kiểm tra số chữ số phần lẻ

Ví dụ đầu tiên cố tình dùng **mã tiền tệ và số chữ số**, là các giá trị dễ kiểm tra mà không phụ thuộc cách dịch tên/ký hiệu của các phiên bản JDK.

Tạo tệp `CurrencyFractionDemo.java`:

```java
import java.util.Currency;

public class CurrencyFractionDemo {
    public static void main(String[] args) {
        String[] codes = {"USD", "JPY", "VND", "KWD", "XXX"};

        for (String code : codes) {
            Currency currency = Currency.getInstance(code);
            System.out.println(
                    currency.getCurrencyCode() + " -> "
                    + currency.getDefaultFractionDigits()
            );
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 CurrencyFractionDemo.java
java CurrencyFractionDemo
```

Stdout với dữ liệu tiền tệ phổ biến trong JDK hiện hành:

```text
USD -> 2
JPY -> 0
VND -> 0
KWD -> 3
XXX -> -1
```

Giải thích:

- `2` với USD tức một đơn vị đô la thường chia thành 100 đơn vị phụ (*cent*) theo thông tin chuẩn.
- `0` với JPY và VND nghĩa **mặc định không hiển thị chữ số phần lẻ**. Không đồng nghĩa kiểu dữ liệu trong ứng dụng tuyệt đối không thể chứa lượng nhỏ hơn một đơn vị; phép định lượng và quy tắc chấp nhận thanh toán cần được quyết định riêng.
- `3` với KWD nghĩa ba chữ số phần lẻ theo metadata (một dinar có thể được biểu diễn theo 1000 đơn vị phụ).
- `-1` là giá trị đặc biệt: không áp dụng số chữ số phần lẻ mặc định; không được truyền `-1` vào `setMinimumFractionDigits`/`setMaximumFractionDigits` như một scale bình thường.

Thông tin này là **mặc định theo mã tiền tệ**. Quy định làm tròn tiền mặt, cách tính thuế, số chữ số trong giao thức thanh toán hoặc yêu cầu hóa đơn có thể khác; nên có chính sách nghiệp vụ được định nghĩa rõ.

## 5. Ví dụ Java: một đồng tiền, nhiều cách hiển thị

Chạy chương trình dưới đây để quan sát sự khác nhau giữa mã, ký hiệu và tên. Tên và ký hiệu là dữ liệu bản địa hóa nên **có thể khác giữa phiên bản JDK, cấu hình CLDR/COMPAT và hệ thống**.

```java
import java.util.Currency;
import java.util.Locale;

public class CurrencyDisplayDemo {
    public static void main(String[] args) {
        Currency usd = Currency.getInstance("USD");
        Locale englishUS = Locale.US;
        Locale vietnameseVN = Locale.forLanguageTag("vi-VN");

        System.out.println("Code: " + usd.getCurrencyCode());
        System.out.println("Digits: " + usd.getDefaultFractionDigits());
        System.out.println("US symbol: " + usd.getSymbol(englishUS));
        System.out.println("VN symbol: " + usd.getSymbol(vietnameseVN));
        System.out.println("US name: " + usd.getDisplayName(englishUS));
        System.out.println("VN name: " + usd.getDisplayName(vietnameseVN));
    }
}
```

Lưu `CurrencyDisplayDemo.java` và chạy:

```bash
javac -encoding UTF-8 CurrencyDisplayDemo.java
java CurrencyDisplayDemo
```

Một **kết quả mẫu** trên OpenJDK 24 với dữ liệu locale đã kiểm tra:

```text
Code: USD
Digits: 2
US symbol: $
VN symbol: US$
US name: US Dollar
VN name: Đô la Mỹ
```

Ở đây `usd` không đổi. Chỉ `Locale` truyền vào hàm hiển thị khác. Nếu máy bạn trả một ký hiệu hoặc cách viết tên khác do nguồn locale data, không có nghĩa tiền tệ USD đã thay đổi: hãy kiểm tra `getCurrencyCode()` và môi trường JDK.

**Nguyên tắc:** dùng mã để **nhận diện**, dùng symbol hoặc display name để **trình bày**, và tách biệt chúng trong kiến trúc chương trình.

## 6. `Currency.getInstance(Locale)`: vùng thường quyết định đơn vị, không phải ngôn ngữ

`Currency.getInstance(Locale)` cố chọn tiền tệ theo quốc gia/vùng được chỉ ra bởi locale. Hai locale có **ngôn ngữ khác nhau nhưng cùng vùng US** vẫn thường chọn USD:

```java
import java.util.Currency;
import java.util.Locale;

public class CurrencyRegionDemo {
    public static void main(String[] args) {
        Locale americanEnglish = Locale.forLanguageTag("en-US");
        Locale americanJapanese = Locale.forLanguageTag("ja-US");
        Locale japaneseJapan = Locale.forLanguageTag("ja-JP");
        Locale vietnameseVietnam = Locale.forLanguageTag("vi-VN");

        System.out.println(
                Currency.getInstance(americanEnglish).getCurrencyCode());
        System.out.println(
                Currency.getInstance(americanJapanese).getCurrencyCode());
        System.out.println(
                Currency.getInstance(japaneseJapan).getCurrencyCode());
        System.out.println(
                Currency.getInstance(vietnameseVietnam).getCurrencyCode());
    }
}
```

Tệp `CurrencyRegionDemo.java`:

```bash
javac -encoding UTF-8 CurrencyRegionDemo.java
java CurrencyRegionDemo
```

Stdout theo dữ liệu vùng hiện hành:

```text
USD
USD
JPY
VND
```

**Những điểm cần hiểu đúng:**

1. Phần `ja` trong `ja-US` nói về **ngôn ngữ tiếng Nhật**, nhưng vùng `US` vẫn dẫn tới USD. Ngôn ngữ để dịch nhãn không quyết định đơn vị tiền của giao dịch.
2. `Currency.getInstance(Locale.forLanguageTag("en"))` thiếu thông tin vùng, thường ném `IllegalArgumentException`; không đoán USD chỉ từ tiếng Anh.
3. Java hỗ trợ Unicode locale extension `u-cu` để chỉ tiền tệ mong muốn trong một `Locale`. Ví dụ `Locale.forLanguageTag("en-US-u-cu-jpy")` có thể dẫn đến JPY, dù vùng là US. Vì thế “chỉ dựa trên vùng” là quy tắc **mặc định có ngoại lệ**, không phải quy luật tuyệt đối.
4. Với một số vùng không có tiền tệ ISO thích hợp, kết quả có thể là `null`; ứng dụng cần xử lý. Cách chọn tiền tệ từ vùng không tương đương lựa chọn đơn vị thực sự của mỗi khoản thanh toán.

**Không nên dùng `Currency.getInstance(userLocale)` để gán đơn vị cho số tiền có sẵn.** Nếu đơn hàng có trường `currencyCode="USD"`, phải giữ đơn vị USD bất kể khách hàng truy cập từ Việt Nam hay Nhật Bản. Thay locale chỉ được dùng để chọn kiểu hiển thị, trừ khi có yêu cầu rõ ràng chuyển đổi tiền tệ cùng tỷ giá và thời điểm.

## 7. Số chữ số phần lẻ mặc định dùng ở đâu?

`getDefaultFractionDigits()` trả độ dài phần thập phân **thường** dùng cho đơn vị tiền. Nó không nói số lượng tiền chính xác đang tồn tại hoặc cấm số tiền có nhiều chữ số hơn.

Các tình huống:

| Nhu cầu | Vai trò của fraction digits |
| --- | --- |
| Hiển thị giá USD | Thông thường chọn 2 chữ số, ví dụ `$12.50` |
| Hiển thị giá JPY | Thông thường 0 chữ số, ví dụ `¥1250` tùy cách nhóm và locale |
| Hiển thị KWD | Thông thường 3 chữ số |
| Lưu giá trị nghiệp vụ | Cần scale và `BigDecimal` theo hợp đồng, không chỉ theo formatter |
| Thu tiền mặt | Có thể phải làm tròn theo bước tiền mặt, khác metadata fraction digits |
| Gửi giao dịch qua cổng thanh toán | Phải tuân theo đặc tả riêng về minor unit, scale và loại tiền |

Một số đơn vị có **cash rounding increment** riêng (ví dụ làm tròn tiền mặt theo bước nhất định), không được mã hóa đầy đủ trong một con số `getDefaultFractionDigits()`. Số chữ số mặc định cũng không đảm bảo rằng **mọi hệ thống thanh toán** chấp nhận scale tương ứng. Một hệ thống có thể yêu cầu số nguyên “minor units”, hệ khác dùng chuỗi decimal; đó là hợp đồng API riêng.

Với `digits == -1` (như `XXX`), nên có chính sách riêng thay vì suy đoán `-1` nghĩa “không có phần thập phân”.

## 8. NumberFormat định dạng tiền: đơn vị và kiểu trình bày là hai bước

Để định dạng một số tiền, có thể tạo formatter theo locale:

```java
NumberFormat formatter =
        NumberFormat.getCurrencyInstance(displayLocale);
```

Formatter này thường được cấu hình với tiền tệ mặc định của locale, cách đặt ký hiệu, dấu phân nhóm và số chữ số phần lẻ mặc định. `NumberFormat` có phương thức `setCurrency(Currency)` để đổi **đơn vị được định dạng** mà không thay đổi toàn bộ locale hiển thị.

**Điểm dễ nhầm:** gọi `setCurrency` trên một formatter **không tự động cập nhật** số chữ số phần lẻ tối thiểu và tối đa của formatter đã tồn tại. Ví dụ formatter của US thường có 2 chữ số; nếu chỉ đổi currency sang JPY, formatter có thể vẫn giữ 2 chữ số như trước. Muốn hiển thị theo fraction digits của tiền mới, cần đặt lại min/max một cách có chủ đích.

### Ví dụ Java 17+: thay currency và tự cập nhật chữ số phần lẻ

```java
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class CurrencyFormatterDigitsDemo {
    public static void main(String[] args) {
        NumberFormat format =
                NumberFormat.getCurrencyInstance(Locale.US);

        System.out.println(
                format.getCurrency().getCurrencyCode() + ": "
                + format.getMinimumFractionDigits() + "/"
                + format.getMaximumFractionDigits());

        Currency jpy = Currency.getInstance("JPY");
        format.setCurrency(jpy);

        System.out.println(
                format.getCurrency().getCurrencyCode() + ": "
                + format.getMinimumFractionDigits() + "/"
                + format.getMaximumFractionDigits());

        int digits = jpy.getDefaultFractionDigits();
        if (digits >= 0) {
            format.setMinimumFractionDigits(digits);
            format.setMaximumFractionDigits(digits);
        }

        System.out.println(
                format.getCurrency().getCurrencyCode() + ": "
                + format.getMinimumFractionDigits() + "/"
                + format.getMaximumFractionDigits());
    }
}
```

Lưu thành `CurrencyFormatterDigitsDemo.java`, chạy:

```bash
javac -encoding UTF-8 CurrencyFormatterDigitsDemo.java
java CurrencyFormatterDigitsDemo
```

Stdout với cấu hình tiền US chuẩn:

```text
USD: 2/2
JPY: 2/2
JPY: 0/0
```

Chương trình cho thấy **đổi tiền tệ** và **đổi precision hiển thị** là hai thao tác tách biệt. Sau khi gọi `setCurrency(jpy)`, đối tượng thực sự là formatter cho JPY, nhưng min/max fraction digits chưa thay. Sau khi dùng metadata JPY và đặt lại min/max, formatter sẽ hiển thị 0 chữ số thập phân.

Không dùng `getDefaultFractionDigits()` như một mệnh lệnh để **làm tròn mọi phép tính**. Chỉ áp dụng nó khi chính sách hiển thị tương ứng đã được xác nhận.

### Một hàm cấu hình formatter có kiểm soát

Mã dưới đây là một **hàm minh họa**, dùng trong class Java có import `java.text.NumberFormat`, `java.util.Currency` và `java.util.Locale`. Nó minh họa cách không áp dụng giá trị `-1`:

```java
static NumberFormat currencyFormatter(
        Locale displayLocale, Currency currency) {

    NumberFormat format =
            NumberFormat.getCurrencyInstance(displayLocale);
    format.setCurrency(currency);

    int digits = currency.getDefaultFractionDigits();
    if (digits >= 0) {
        format.setMinimumFractionDigits(digits);
        format.setMaximumFractionDigits(digits);
    }
    return format;
}
```

Trong một dự án thực, bạn có thể thêm các tham số theo chính sách sản phẩm để kiểm soát rounding, format pattern và các trường hợp đặc biệt. `NumberFormat` là một abstraction: không ép cast sang `DecimalFormat` nếu bạn không chắc provider trả instance nào. Khi cần chỉnh pattern chuyên sâu, kiểm tra kiểu formatter và hợp đồng thư viện.

## 9. DecimalFormat, dấu phân nhóm và vị trí ký hiệu

`NumberFormat.getCurrencyInstance(locale)` thường là lựa chọn thích hợp nếu bạn chỉ cần hiển thị tiền theo locale. Nếu cần điều chỉnh định dạng chuyên sâu, `DecimalFormat` hỗ trợ pattern và `DecimalFormatSymbols`:

```java
Locale locale = Locale.US;
NumberFormat base = NumberFormat.getCurrencyInstance(locale);
String formatted = base.format(1234.5);
```

Đoạn mã trên **không phải một chương trình độc lập**, và ví dụ chỉ minh họa API. Với `Locale.US` và USD, đầu ra phổ biến là `$1,234.50`. Ở locale khác, ký hiệu có thể đứng trước hoặc sau, dấu thập phân/nhóm chữ số và khoảng trắng có thể khác.

Trong `DecimalFormat`, ký hiệu `¤` trong pattern có ngữ nghĩa tiền tệ: một `¤` đại diện ký hiệu tiền tệ, hai `¤¤` đại diện mã ISO; các biến thể pattern khác có thể phục vụ cách biểu đạt khác. Đây là **ký tự currency sign U+00A4**, không phải “dấu phần nghìn”, và không nên tự thay `¤` bằng một dấu `$` cứng cho tất cả các đơn vị.

Nếu cần luôn hiển thị mã, xem xét một pattern dùng `¤¤` hoặc cấu trúc UI hiển thị rõ mã ISO. Nhưng khi xây UI đa quốc gia, ưu tiên cách định dạng bản địa hóa của JDK và kiểm thử với dữ liệu thực thay vì tự gắn ký hiệu ở đầu hoặc cuối chuỗi.

**Lưu ý khi định dạng KWD:** nếu formatter theo US ban đầu có 2 chữ số nhưng đổi sang KWD, bạn phải xác nhận việc đưa min/max fraction digits thành 3 là phù hợp. Cấu hình chỉ bằng `setCurrency(KWD)` không đảm bảo định dạng 3 chữ số phần lẻ.

## 10. Lưu số tiền: dùng mã tiền tệ và số có độ chính xác phù hợp

Tách rõ thông tin đơn vị và số lượng:

```java
import java.math.BigDecimal;
import java.util.Currency;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        if (amount == null || currency == null) {
            throw new IllegalArgumentException(
                    "amount and currency are required");
        }
    }
}
```

Lưu đoạn này trong `Money.java`. Vì `record` là tính năng có trong Java 17, đoạn mã là một kiểu dữ liệu có thể biên dịch độc lập. Ví dụ sử dụng trong mã Java khác:

```java
Money price = new Money(
        new BigDecimal("12.50"),
        Currency.getInstance("USD"));
```

Đoạn khởi tạo là **mã minh họa trong một phương thức** và không phải một chương trình riêng. `Money` phía trên không tự áp dụng quy tắc cộng trừ, đổi tỷ giá hoặc rounding; các phép toán đó cần được thiết kế theo nghiệp vụ. Khi lưu hoặc truyền giữa các dịch vụ, cần giữ mã tiền tệ `USD` cùng giá trị decimal.

**Không dùng ký hiệu để suy ra mã tiền.** Một request `{"amount":"12.50","symbol":"$"}` không xác định đủ nó là USD, CAD, AUD hoặc một đơn vị khác. Hợp đồng API nên mang trường `currencyCode`.

Đối với tiền tệ, `BigDecimal` thường phù hợp hơn `double` vì nhiều giá trị thập phân không được biểu diễn chính xác bằng nhị phân dấu phẩy động. Khi cần tạo `BigDecimal` từ chuỗi decimal, dùng `new BigDecimal("12.50")` thay vì tạo trực tiếp từ một giá trị `double` nếu muốn giữ chính xác biểu diễn decimal.

## 11. Một số trường hợp biên của Currency

### 11.1. Currency không xác định

`Currency.getInstance("NOT_A_CODE")` không thể được hiểu là một đơn vị hợp lệ và ném `IllegalArgumentException`. API dùng cho một mã tiền tệ là một bước **kiểm tra mã**, không phải kiểm chứng rằng hệ thống thanh toán của bạn chấp nhận giao dịch bằng loại tiền đó.

`Currency.getInstance(Locale)` cần locale có thông tin quốc gia/vùng phù hợp (trừ trường hợp có extension hợp lệ). Nếu locale thiếu vùng, nó có thể ném `IllegalArgumentException`; trong một số vùng không có đơn vị tương ứng, có thể trả `null`.

### 11.2. Đơn vị có `-1` fraction digits

`XXX` và một số mã đặc biệt không có số chữ số phần lẻ mặc định. Khi `getDefaultFractionDigits() == -1`, phải dùng chính sách riêng. Không truyền giá trị âm cho setter fraction digits và không suy diễn số tiền hợp lệ từ mã đặc biệt.

### 11.3. Mã hiển thị và mã số ISO

`getNumericCode()` và `getNumericCodeAsString()` hữu ích khi tích hợp giao thức dùng **mã số ISO 4217**. Dùng phiên bản chuỗi nếu cần bảo toàn đúng ba chữ số của mã số có leading zero. Không coi numeric code là số lượng tiền hoặc hệ số chuyển đổi.

### 11.4. Dữ liệu tiền tệ thay đổi theo thời gian

Đơn vị tiền tệ, tên, ký hiệu và metadata của vùng có thể thay đổi theo dữ liệu ISO và locale provider của JDK. Vì vậy trong hệ thống pháp lý/tài chính, cần pin phiên bản JDK/CLDR phù hợp, kiểm tra các đơn vị thực sự dùng, và không giả định danh sách tên/ký hiệu bất biến giữa các môi trường.

### 11.5. Currency và Locale đều có vai trò riêng

Một ứng dụng có giao diện `vi-VN`, nhưng bảng giá bằng USD: chọn `Currency.getInstance("USD")` để giữ đơn vị, rồi chọn `vi-VN` làm locale hiển thị. Nếu sau đó người dùng chuyển ngôn ngữ UI sang `en-US`, **số lượng và đơn vị vẫn là USD**; chỉ cách trình bày (tên/ký hiệu/dấu phân cách) thay đổi. Chuyển đổi USD sang VND là thao tác khác có tỷ giá và nghiệp vụ.

## 12. Những lỗi phổ biến

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Lưu `"$"` thay vì `"USD"` | Không nhận diện duy nhất đơn vị tiền | Lưu mã ISO |
| Dùng `getSymbol()` không truyền locale trong web app | Phụ thuộc JVM/server | Truyền locale người dùng |
| Nghĩ `getDisplayName()` là mã ISO | Mã bị đổi theo ngôn ngữ | Dùng `getCurrencyCode()` cho dữ liệu |
| Coi mọi đơn vị có 2 chữ số phần lẻ | JPY/VND/KWD bị format sai | Đọc metadata và áp chính sách cụ thể |
| Gọi `setCurrency(JPY)` và mặc định precision đổi theo | Formatter có thể vẫn giữ 2 chữ số | Đặt lại min/max khi phù hợp |
| Truyền `-1` cho fraction digits setter | Không hợp lệ về scale | Xử lý trường hợp đặc biệt |
| Suy đơn vị của một khoản tiền từ `userLocale` | Đổi tiền ngoài ý muốn | Lưu currency theo giao dịch |
| Dùng symbol làm dấu hiệu tỷ giá | Hai loại tiền có thể cùng ký hiệu | Phân biệt mã ISO, dùng tỷ giá riêng |
| Dùng formatter để chuẩn hóa giá trị lưu trữ | Thất thoát chữ số do làm tròn | Giữ decimal gốc, chỉ format khi hiển thị |
| Nhầm default fraction digits với cash rounding | Sai quy tắc thanh toán | Tuân hợp đồng và quy định cash rounding |
| Chia sẻ `NumberFormat` mutable giữa nhiều luồng | Có thể xảy ra race khi đổi currency/precision | Tạo instance theo request hoặc quản lý đồng thời |
| Coi tên dịch của JDK là nhãn sản phẩm bắt buộc | Tên có thể thay đổi theo CLDR/provider | Kiểm thử, quản lý từ điển sản phẩm nếu cần |

`NumberFormat` và `DecimalFormat` là các formatter có trạng thái thay đổi; không cập nhật chung một formatter theo nhiều request đồng thời. `Currency` mô tả đơn vị và có thể được dùng lại, nhưng phần **formatter định dạng** nên được tạo hoặc quản lý phù hợp theo từng locale/currency/cấu hình.

## 13. Checklist kiểm thử

Khi triển khai, kiểm tra những điểm sau:

1. **Metadata:** USD=2, JPY=0, VND=0, KWD=3, XXX=-1 theo môi trường chạy mục tiêu.
2. **Nhận diện:** `getCurrencyCode()` giữ nguyên dù đổi locale hiển thị.
3. **Tên/ký hiệu:** kiểm thử các locale như `en-US`, `vi-VN`, `ja-JP`; không hard-code cùng ký hiệu cho mọi ngôn ngữ.
4. **Vùng:** `ja-US` cho tiền của vùng US, còn `ja-JP` cho vùng JP; test extension `u-cu` nếu ứng dụng dùng.
5. **Độ chính xác formatter:** sau `setCurrency`, kiểm tra min/max fraction digits; đừng giả định tự cập nhật.
6. **Các đơn vị 0 và 3 chữ số:** kiểm thử hiển thị JPY/VND/KWD với `BigDecimal` và quy tắc làm tròn.
7. **Mã không hợp lệ:** xử lý `IllegalArgumentException`, `null` và fraction digits `-1` theo đúng trường hợp.
8. **Số tiền nghiệp vụ:** lưu cả amount và currency code; không suy currency từ symbol hay locale người dùng.
9. **Môi trường:** test phiên bản JDK và locale provider dự kiến; nếu output tên dịch thay đổi, phân loại đó là khác biệt metadata hay lỗi nghiệp vụ.
10. **Đồng thời:** formatter không bị thay cấu hình từ nhiều thread chung instance.

### Bài tập

- In `getSymbol(Locale.US)`, `getSymbol(Locale.forLanguageTag("vi-VN"))` và hai `getDisplayName` cho USD và JPY. Ghi lại điểm khác nhau, nhưng không biến kết quả thành giả định bất biến giữa mọi JDK.
- Tạo `NumberFormat.getCurrencyInstance(Locale.US)`, đổi sang KWD bằng `setCurrency`, rồi chỉnh min/max fraction digits theo `getDefaultFractionDigits()`. Kiểm tra `3/3`.
- Tạo một `Money` giữ amount `12.50` và USD; đổi locale hiển thị sang `vi-VN` mà không đổi `currency.getCurrencyCode()`.
- Giải thích vì sao `currency.getSymbol(Locale.US).equals("$")` không thể được dùng làm điều kiện kết luận mọi số có ký hiệu `$` đều là USD.
- Giả sử API nhận `amount=1234.567`, `currencyCode=JPY`. Hãy quyết định rõ quy tắc xử lý thập phân theo nghiệp vụ **trước** khi hiển thị; không tự làm tròn dữ liệu chỉ vì formatter mặc định 0 digits.

## 14. Ghi nhớ

**Mã ISO 4217** nhận diện đơn vị tiền; **symbol và display name** là dữ liệu **trình bày theo locale**; **default fraction digits** là metadata chỉ ra số chữ số phần lẻ thường dùng cho đơn vị. Ba thứ này phục vụ ba mục đích khác nhau.

Khi format một số tiền, hãy giữ **amount + currencyCode** trong dữ liệu, chọn **locale hiển thị**, tạo `NumberFormat` phù hợp, đặt currency và xác minh precision nếu đã thay đơn vị. Khi xử lý thanh toán hoặc tính toán chính xác, áp dụng hợp đồng nghiệp vụ và kiểu decimal phù hợp, không đánh đồng fraction digits của JDK với mọi quy tắc tiền mặt hoặc gateway.

## Tài liệu tham khảo

- [Oracle Java 21 — Currency](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Currency.html)
- [Oracle Java 21 — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html)
- [Oracle Java 21 — DecimalFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html)
- [Oracle Java 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
- [ISO 4217 — Currency Codes](https://www.iso.org/iso-4217-currency-codes.html)
