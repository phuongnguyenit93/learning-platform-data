# Phân biệt đơn vị tiền tệ với quy ước trình bày theo Locale

## 1. Hai câu hỏi khác nhau: bao nhiêu tiền và hiển thị thế nào?

Giả sử một hóa đơn có số tiền **1.234,50 USD** và được hiển thị cho hai người dùng:

- Người dùng ở Hoa Kỳ có thể thấy `$1,234.50`.
- Người dùng sử dụng quy ước Đức có thể thấy `1.234,50 $` (có thể có khoảng trắng không ngắt giữa số và ký hiệu).

Đây là **cùng một khoản 1.234,50 đô la Mỹ**, không phải hai khoản tiền khác nhau. Các dấu phân tách, vị trí ký hiệu và khoảng trắng thay đổi theo quy ước trình bày; **đơn vị tiền tệ USD không thay đổi**.

Ngược lại, `100 USD` và `100 EUR` là **hai khoản tiền mang đơn vị khác nhau** dù cùng có phần số `100`. Đổi dấu phân cách hoặc đổi ký hiệu bên ngoài không thể biến USD thành EUR. Muốn chuyển đổi đơn vị tiền tệ phải có **tỷ giá, thời điểm tỷ giá, quy tắc làm tròn và nghiệp vụ** rõ ràng.

Trong Java, hai khái niệm này được biểu diễn riêng:

- `java.util.Currency`: nhận diện **đơn vị tiền tệ**, ví dụ `USD`, `EUR`, `JPY`, `VND` theo các mã ISO 4217 được JDK hỗ trợ.
- `java.util.Locale`: nhận diện **quy ước ngôn ngữ và vùng**, ví dụ `en-US`, `de-DE`, `vi-VN`, được đưa cho formatter để chọn cách hiển thị.
- `java.math.BigDecimal`: biểu diễn **giá trị số thập phân** chính xác, thích hợp cho các phép tính tiền có quy tắc rõ ràng.
- `java.text.NumberFormat` và `java.text.DecimalFormat`: tạo **chuỗi trình bày** theo locale và cấu hình đơn vị tiền tệ.

Một quy tắc thiết kế: **tiền của giao dịch là dữ liệu nghiệp vụ; locale là lựa chọn trình bày của người đọc**. Không lấy locale để tự suy ra loại tiền của hóa đơn khi hệ thống đã biết hóa đơn là USD, EUR hay VND.

## 2. Phân biệt Currency, Locale và Amount

| Khái niệm | Trả lời câu hỏi | Ví dụ | API thường dùng |
| --- | --- | --- | --- |
| Giá trị (`amount`) | Số lượng tiền là bao nhiêu? | `1234.50` | `BigDecimal` |
| Đơn vị (`currency`) | 1234.50 được tính bằng tiền gì? | `USD` | `Currency` |
| Quy ước trình bày (`locale`) | Người đọc muốn số và ký hiệu hiện ra thế nào? | `Locale.GERMANY` | `Locale` |
| Formatter | Biến giá trị + currency thành chuỗi theo locale như thế nào? | `1.234,50 $` | `NumberFormat`/`DecimalFormat` |
| Tỷ giá | Đổi một đơn vị tiền sang đơn vị tiền khác theo giá nào? | Tỷ giá USD/EUR tại thời điểm cụ thể | Dịch vụ/dữ liệu nghiệp vụ, **không phải** `NumberFormat` |

**Ví dụ tư duy:**

1. `amount = 1234.50`, `currency = USD`, `locale = en-US` → trình bày theo kiểu Mỹ.
2. Giữ **amount và currency**, đổi `locale = de-DE` → trình bày theo kiểu Đức.
3. Giữ amount và locale nhưng đổi `currency = EUR` → **đã thay đổi ý nghĩa khoản tiền**, không còn là cùng đơn vị.
4. Muốn giá trị EUR tương đương với 1234.50 USD, phải thực hiện phép **chuyển đổi bằng tỷ giá** trước, rồi định dạng số tiền mới.

Với lưu trữ và API, một khoản tiền thường cần ít nhất hai trường: **số tiền** và **mã tiền tệ**. Chuỗi hiển thị là kết quả để đọc, không phải nguồn dữ liệu chuẩn để tính toán.

## 3. java.util.Currency: mã và thuộc tính của đơn vị tiền

### 3.1. Lấy đối tượng Currency

Tạo đơn vị từ mã tiền tệ được hỗ trợ:

```java
import java.util.Currency;

Currency usd = Currency.getInstance("USD");
Currency eur = Currency.getInstance("EUR");
Currency vnd = Currency.getInstance("VND");
Currency jpy = Currency.getInstance("JPY");
```

Mã phải có dạng phù hợp và được bộ dữ liệu tiền tệ của JDK hỗ trợ. `getInstance(String)` có thể ném `IllegalArgumentException` nếu mã không hợp lệ/không được hỗ trợ. Không tự động coi một chuỗi ba chữ cái bất kỳ là mã tiền được chấp nhận trong sản phẩm.

`Currency` còn cho phép:

```java
usd.getCurrencyCode();           // "USD"
usd.getNumericCode();            // Mã số ISO 4217 do JDK cung cấp
usd.getDefaultFractionDigits();  // Thường là 2 đối với USD
usd.getSymbol(Locale.US);        // Ký hiệu thích hợp cho locale
usd.getDisplayName(Locale.US);   // Tên hiển thị theo locale
```

Ký hiệu và tên hiển thị có thể phụ thuộc dữ liệu locale/provider của phiên bản JDK. Một ký hiệu như `$` **không đủ để xác định đơn vị tiền** vì nhiều đơn vị có thể dùng ký hiệu tương tự. Để trao đổi dữ liệu và ghi sổ, ưu tiên mã `USD`/`CAD`/`AUD` cụ thể thay vì cố đoán từ ký hiệu.

### 3.2. Currency.getInstance(Locale) có nghĩa gì?

`Currency.getInstance(locale)` cố tìm loại tiền **gắn với quốc gia/vùng trong locale**, theo dữ liệu tiền tệ của JDK. Ví dụ:

```java
Currency regional = Currency.getInstance(Locale.GERMANY);
System.out.println(regional.getCurrencyCode()); // EUR
```

Điều này **không chứng minh** mọi hóa đơn đang hiển thị ở Đức đều phải là EUR. Một khách hàng Đức hoàn toàn có thể thanh toán hóa đơn bằng USD. `Locale.GERMANY` chỉ giúp formatter hiểu cách hiển thị và có thể xác định **tiền mặc định theo vùng** trong bối cảnh phù hợp.

Không suy ra tiền tệ chỉ từ language `"en"` hoặc `"vi"`: một ngôn ngữ được dùng ở nhiều quốc gia. `Currency.getInstance(Locale)` cần thông tin vùng phù hợp; locale không có country có thể gây `IllegalArgumentException`. Một số vùng không có đơn vị tiền tệ hiện hành có thể cho kết quả `null`. Vì vậy, nếu ứng dụng **cần tiền giao dịch**, nên lưu/nhận currency một cách tường minh thay vì dựa trên ngôn ngữ UI.

### 3.3. Default fraction digits

`Currency.getDefaultFractionDigits()` trả số chữ số thập phân mặc định theo dữ liệu ISO 4217 của JDK:

| Tiền tệ | Giá trị thường gặp | Ý nghĩa |
| --- | ---: | --- |
| `USD` | 2 | Thường biểu diễn phần cent với hai chữ số |
| `EUR` | 2 | Thường biểu diễn phần cent với hai chữ số |
| `JPY` | 0 | Đơn vị yên thường không có phân số thập phân |
| `VND` | 0 | Đồng Việt Nam thường có không chữ số lẻ trong quy ước này |

Một số mã đặc biệt có thể trả `-1` để báo không áp dụng số chữ số phân số mặc định. **Đừng giả định mọi currency luôn có 2 chữ số.**

Nhưng đây là **thuộc tính mặc định**, không phải luật làm tròn cuối cùng cho mọi nghiệp vụ. Ví dụ: đơn giá nội bộ có thể cần nhiều chữ số hơn số tiền thanh toán; hệ thống kế toán có thể giữ scale riêng; quy định thuế hoặc phương thức thanh toán có thể yêu cầu làm tròn ở bước khác. Hãy định nghĩa các quy tắc đó tường minh.

## 4. java.util.Locale quyết định quy ước hiển thị

`Locale` tác động đến những yếu tố như:

- **Dấu thập phân**: nhiều định dạng tiếng Anh dùng `.`, nhiều định dạng Đức dùng `,`.
- **Dấu phân nhóm**: có thể là dấu phẩy, dấu chấm, khoảng trắng, khoảng trắng không ngắt hoặc ký tự khác tùy locale.
- **Vị trí và cách trình bày ký hiệu**: trước hoặc sau số, có thể thêm khoảng trắng.
- **Ký hiệu/mã đơn vị tiền tệ**: cùng USD có thể hiển thị `$`, `US$`, hoặc tên/mã khác tùy ngữ cảnh và dữ liệu locale.
- **Cách hiển thị số âm** và các quy ước kế toán nếu formatter được cấu hình phù hợp.
- **Hệ chữ số** và dữ liệu địa phương hóa khác trong những locale có extension thích hợp.

Các quyết định này **không làm thay đổi giá trị số học**. Nếu bạn định dạng cùng `BigDecimal("1234.50")`, số tiền gốc vẫn là `1234.50` dù màn hình dùng dấu khác nhau.

`Locale.forLanguageTag("de-DE")` chỉ định quy ước Đức; `Locale.forLanguageTag("vi-VN")` chỉ định ngữ cảnh tiếng Việt ở Việt Nam. Không được xem `Locale` là “đơn vị tiền tệ”. Cũng không nên thay đổi `Locale.setDefault(...)` trên toàn JVM để định dạng từng request của web server: mặc định là trạng thái chia sẻ, gây rủi ro giữa nhiều người dùng. Truyền `Locale` tường minh cho formatter.

## 5. NumberFormat.getCurrencyInstance và setCurrency

### 5.1. Tạo formatter theo locale

`NumberFormat.getCurrencyInstance(locale)` tạo formatter tiền tệ với các quy ước trình bày mặc định của locale. Ví dụ:

```java
NumberFormat us = NumberFormat.getCurrencyInstance(Locale.US);
NumberFormat germany = NumberFormat.getCurrencyInstance(Locale.GERMANY);
```

Thông thường, formatter tạo cho `Locale.US` sử dụng USD theo mặc định và formatter tạo cho `Locale.GERMANY` sử dụng EUR theo mặc định. Tuy vậy, đơn vị được formatter chọn ban đầu chỉ là **giá trị mặc định liên quan locale**, không phải tiền tệ bắt buộc của dữ liệu đang cần in.

### 5.2. Đơn vị của giao dịch cần đặt rõ ràng

Nếu cùng một giao dịch USD được hiển thị cho hai người dùng:

```java
Currency transactionCurrency = Currency.getInstance("USD");
BigDecimal amount = new BigDecimal("1234.50");

NumberFormat usFormat =
        NumberFormat.getCurrencyInstance(Locale.US);
NumberFormat deFormat =
        NumberFormat.getCurrencyInstance(Locale.GERMANY);

usFormat.setCurrency(transactionCurrency);
deFormat.setCurrency(transactionCurrency);

String forAmericanUser = usFormat.format(amount);
String forGermanUser = deFormat.format(amount);
```

Hai chuỗi có thể khác nhau đáng kể về dấu phân cách, vị trí ký hiệu và khoảng trắng. **Cả hai vẫn định dạng 1234.50 USD**; không có phép nhân/chia tỷ giá nào trong `setCurrency` hoặc `format`.

Một cách viết có tính quyết định rõ hơn là:

```java
String formatMoney(BigDecimal amount, Currency currency, Locale locale) {
    NumberFormat fmt = NumberFormat.getCurrencyInstance(locale);
    fmt.setCurrency(currency);
    return fmt.format(amount);
}
```

Đây là **snippet phương thức** (không phải file Java độc lập), cần các import `java.math.BigDecimal`, `java.util.Currency`, `java.util.Locale`, `java.text.NumberFormat`. Phần sau có một chương trình đầy đủ.

### 5.3. Bẫy quan trọng: setCurrency không tự đổi fraction digits

`setCurrency(currency)` trên `NumberFormat` thay đổi currency được formatter sử dụng; theo API, nó **không tự cập nhật** `getMinimumFractionDigits()` và `getMaximumFractionDigits()`. Đây là điều khác với trực giác “đổi sang JPY thì luôn tự bỏ các chữ số lẻ”.

Ví dụ:

```java
NumberFormat fmt =
        NumberFormat.getCurrencyInstance(Locale.US);
int before = fmt.getMaximumFractionDigits();

fmt.setCurrency(Currency.getInstance("JPY"));

int after = fmt.getMaximumFractionDigits();
// Theo hợp đồng setCurrency: before == after.
```

Do formatter `Locale.US` thông thường đã được thiết lập hai chữ số sau dấu thập phân, đổi currency sang JPY mà không cấu hình lại có thể tạo chuỗi JPY với **hai chữ số lẻ**, trong khi `Currency.getInstance("JPY").getDefaultFractionDigits()` là 0.

Nếu chính sách trình bày của sản phẩm là dùng số chữ số mặc định của currency, cần cập nhật riêng:

```java
int digits = currency.getDefaultFractionDigits();
if (digits >= 0) {
    fmt.setMinimumFractionDigits(digits);
    fmt.setMaximumFractionDigits(digits);
}
```

Đây là snippet với biến `currency`/`fmt` đã được khởi tạo. Quy tắc này là **một lựa chọn trình bày**, không thay thế chính sách thanh toán/kế toán. Đặc biệt, không đặt một số `-1` làm fraction digits; phải xét trường hợp currency không có mặc định.

### 5.4. Currency.getSymbol và pattern tiền tệ

`Currency.getSymbol(locale)` trả ký hiệu theo ngữ cảnh hiển thị. `NumberFormat.getCurrencyInstance(locale)` có thể chọn cả vị trí ký hiệu, khoảng trắng, grouping và dạng dấu âm — không thể tái tạo đầy đủ bằng phép nối:

```java
currency.getSymbol(locale) + amount.toString()
```

Cách nối này có thể sai dấu thập phân, sai vị trí ký hiệu và thiếu dấu cách. Với `DecimalFormat`, ký hiệu `¤` trong pattern đại diện cho currency; `¤¤` thường yêu cầu mã tiền tệ thay cho ký hiệu, nhưng các pattern tùy chỉnh phải được áp dụng cùng `DecimalFormatSymbols` thích hợp. Không nên áp dụng pattern cố định của một locale cho toàn bộ ngôn ngữ khác.

## 6. Ví dụ Java 17+ chạy độc lập: cùng USD, hai locale

Tạo file UTF-8 tên **`CurrencyAndLocaleDemo.java`**:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class CurrencyAndLocaleDemo {
    public static void main(String[] args) {
        Currency usd = Currency.getInstance("USD");
        Currency jpy = Currency.getInstance("JPY");
        BigDecimal amount = new BigDecimal("1234.50");

        NumberFormat us = NumberFormat.getCurrencyInstance(Locale.US);
        NumberFormat german =
                NumberFormat.getCurrencyInstance(Locale.GERMANY);

        us.setCurrency(usd);
        german.setCurrency(usd);

        System.out.println("Region currency: "
                + Currency.getInstance(Locale.GERMANY).getCurrencyCode());
        System.out.println("Transaction currency: "
                + usd.getCurrencyCode());
        System.out.println("US formatter currency: "
                + us.getCurrency().getCurrencyCode());
        System.out.println("DE formatter currency: "
                + german.getCurrency().getCurrencyCode());

        String usText = us.format(amount);
        String germanText = german.format(amount);
        System.out.println("Different presentation: "
                + !usText.equals(germanText));
        System.out.println("Amount unchanged: " + amount.toPlainString());

        System.out.println("USD fraction digits: "
                + usd.getDefaultFractionDigits());
        System.out.println("JPY fraction digits: "
                + jpy.getDefaultFractionDigits());

        NumberFormat usJpy =
                NumberFormat.getCurrencyInstance(Locale.US);
        int before = usJpy.getMaximumFractionDigits();
        usJpy.setCurrency(jpy);

        System.out.println("JPY configured: "
                + usJpy.getCurrency().getCurrencyCode());
        System.out.println("Maximum fraction digits unchanged: "
                + (before == usJpy.getMaximumFractionDigits()));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 CurrencyAndLocaleDemo.java
java CurrencyAndLocaleDemo
```

Kết quả trên JDK có dữ liệu tiền tệ/locale hiện đại:

```text
Region currency: EUR
Transaction currency: USD
US formatter currency: USD
DE formatter currency: USD
Different presentation: true
Amount unchanged: 1234.50
USD fraction digits: 2
JPY fraction digits: 0
JPY configured: JPY
Maximum fraction digits unchanged: true
```

Giải thích:

1. Currency lấy theo **vùng Đức** là EUR, nhưng dữ liệu giao dịch được chọn rõ ràng là USD.
2. Cả hai formatter đều được cấu hình `USD` dù một cái trình bày theo `Locale.US`, cái kia theo `Locale.GERMANY`.
3. `Different presentation: true` kiểm tra khác biệt kết quả hiển thị mà **không hardcode** dấu, khoảng trắng hoặc vị trí biểu tượng có thể thay đổi theo dữ liệu locale của JDK.
4. `amount.toPlainString()` vẫn là `1234.50`; việc định dạng không thực hiện đổi tiền hoặc sửa `BigDecimal`.
5. USD có mặc định hai chữ số lẻ, JPY có mặc định không chữ số lẻ. Sau `setCurrency(jpy)`, `getMaximumFractionDigits` vẫn không bị thay đổi tự động.

Nếu bạn cần quan sát chính xác chuỗi tiền theo hai locale trên máy mình, hãy in thêm `usText` và `germanText`. Chuỗi có thể chứa **non-breaking space** hoặc ký hiệu tiền tệ do CLDR/JDK cung cấp; vì vậy không nên lấy ví dụ hiển thị trong tài liệu làm hợp đồng cố định giữa mọi phiên bản môi trường.

## 7. Lưu trữ tiền bằng BigDecimal và Currency

### 7.1. Không dùng double làm nguồn sự thật cho tiền

Giá trị `double` là xấp xỉ nhị phân. Trong các phép tính tiền nhiều bước, đặc biệt phép cộng, phân bổ tỷ lệ, tính thuế và lãi, dùng `double` có thể phát sinh kết quả không đúng kỳ vọng thập phân. Một kiểu dữ liệu nền tảng đơn giản:

```java
import java.math.BigDecimal;
import java.util.Currency;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        if (amount == null || currency == null) {
            throw new IllegalArgumentException(
                    "Amount and currency are required");
        }
    }
}
```

Đây là **một file Java độc lập tên `Money.java`** nếu được đưa vào project; record hỗ trợ từ Java 16, nên chạy được với Java 17+. Không nên biến mỗi khoản tiền thành một chuỗi đã định dạng ngay tại tầng dữ liệu. Record trên minh họa việc lưu đúng hai thành phần, **chưa triển khai mọi quy tắc nghiệp vụ** như không âm, scale hợp lệ, kiểm soát overflow hoặc rounding.

Ví dụ thao tác:

```java
Money bill = new Money(
        new BigDecimal("1234.50"),
        Currency.getInstance("USD")
);
```

Khi gửi qua JSON/API, nên truyền mã tiền tệ và amount dạng số thập phân chính xác (hoặc chuỗi thập phân canonical tùy hợp đồng), không dùng chuỗi đã thêm `$`/dấu phân nhóm. Phía nhận phải xác thực lại currency code và amount.

### 7.2. Cộng khác tiền tệ phải bị ngăn chặn

Hai số `100 USD` và `100 EUR` không thể đơn giản cộng `100 + 100 = 200` rồi xem đó là một số tiền có đơn vị hợp lệ. Ngay cả khi cả hai có hai chữ số lẻ, **đơn vị khác nhau**. Hàm cộng phải kiểm tra currency bằng nhau, hoặc yêu cầu quá trình chuyển đổi tỷ giá trước:

```java
static Money add(Money a, Money b) {
    if (!a.currency().equals(b.currency())) {
        throw new IllegalArgumentException("Currency mismatch");
    }
    return new Money(
            a.amount().add(b.amount()),
            a.currency()
    );
}
```

Đây là **snippet** trong một lớp có thể truy cập record `Money` ở trên. Cách kiểm tra đơn vị là phần cốt lõi, vì một formatter hoàn toàn có thể in cùng kiểu cho hai giá trị khác đơn vị nhưng không làm chúng trở nên tương đương.

### 7.3. Định dạng không được quyết định tỷ giá

`fmt.setCurrency(Currency.getInstance("EUR"))` chỉ bảo formatter dùng EUR khi tạo text. Nó **không** chuyển `1234.50 USD` thành một số EUR có giá trị tương đương. Hành động đó đòi hỏi:

- Nguồn tỷ giá đáng tin và cặp tiền tệ đúng chiều.
- Thời điểm hiệu lực của tỷ giá.
- Quy tắc làm tròn/scale được quyết định bởi nghiệp vụ.
- Xử lý phí, spread, thuế và ghi nhận chênh lệch nếu có.

Sau khi tính được giá trị EUR mới, mới format với currency EUR và locale của người đọc. API `Currency`/`NumberFormat` không cung cấp tỷ giá hối đoái.

## 8. Fraction digits và RoundingMode: nghiệp vụ trước, trình bày sau

Giả sử đơn hàng JPY có giá trị tính trung gian `1234.50`. Một formatter dùng số chữ số lẻ mặc định JPY có thể hiển thị số nguyên đã làm tròn; điều đó **không tự chứng minh** hệ thống đã được phép thu/trả đúng số nguyên ấy. Bước tính tiền cuối cùng phải theo chính sách sản phẩm/phương thức thanh toán, rồi mới hiển thị.

Đối với `BigDecimal`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal exact = new BigDecimal("1234.50");
BigDecimal rounded = exact.setScale(0, RoundingMode.HALF_UP);

System.out.println(rounded.toPlainString()); // 1235
```

Đây là **snippet trong phương thức**, không phải chương trình Java hoàn chỉnh. `setScale(...)` tạo giá trị mới; `exact` không bị sửa vì `BigDecimal` bất biến. Nếu tiền giao dịch dùng JPY, việc chọn `HALF_UP` chỉ là ví dụ chính sách, không phải quy tắc bắt buộc quốc tế.

Để trình bày sau khi tính:

```java
NumberFormat formatter =
        NumberFormat.getCurrencyInstance(locale);
formatter.setCurrency(currency);
formatter.setRoundingMode(RoundingMode.HALF_UP);

int digits = currency.getDefaultFractionDigits();
if (digits >= 0) {
    formatter.setMinimumFractionDigits(digits);
    formatter.setMaximumFractionDigits(digits);
}

String label = formatter.format(amount);
```

Snippet này giả định biến `locale` kiểu `Locale`, `currency` kiểu `Currency`, `amount` kiểu `BigDecimal`; cần import `java.text.NumberFormat` và `java.math.RoundingMode`. Đặt rounding mode của formatter chỉ kiểm soát **chuỗi hiển thị**; nếu nghiệp vụ cần làm tròn số tiền được ghi nhận, hãy làm điều đó trong lớp domain bằng `BigDecimal` và chính sách có kiểm thử.

**Đừng giả định "2 chữ số lẻ" đồng nghĩa mọi loại tiền đều có cent.** Ngoài USD/EUR, nhiều đồng tiền có 0 hoặc số chữ số khác; một số giá trị trung gian tính giá/đơn vị hàng hóa lại cần scale lớn hơn mặc định. Giữ riêng quy tắc của currency và quy tắc tính toán.

## 9. Parsing: có thể đọc được số, chưa chắc biết tiền tệ

Định dạng là chiều **giá trị → chuỗi**, còn parsing là **chuỗi → giá trị**. Với dữ liệu từ người dùng, phân tích theo locale đòi hỏi biết dấu thập phân/phân nhóm mà UI dùng. `NumberFormat.parse(...)` có thể trả `Long` hoặc `Double` và **không tự mang theo Currency** trong giá trị số được trả về.

Với số thập phân cần chính xác, trên formatter thực sự là `DecimalFormat` có thể bật:

```java
DecimalFormat parser = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US)
);
parser.setParseBigDecimal(true);
```

Sau đó parse text số với `ParsePosition` và kiểm tra đã đọc hết chuỗi; kết quả thường là `BigDecimal` cho số hữu hạn. Cần nhập `java.text.DecimalFormat`, `DecimalFormatSymbols` và `java.util.Locale`. Nếu input là một **chuỗi tiền có ký hiệu**, phải có pattern/parser phù hợp; không tự xóa mọi ký tự không phải chữ số vì như vậy sẽ làm mất dấu âm, dấu phân cách và **không xác thực được loại tiền**.

**Ràng buộc đơn vị:** Dù parser hiểu chuỗi `"1,234.50"` thành `BigDecimal("1234.50")`, ứng dụng vẫn phải biết nó là USD, EUR hay VND từ trường currency riêng hoặc lựa chọn sản phẩm. Ký hiệu `$` có thể không đủ phân biệt USD/CAD/AUD; không xem kết quả parse là bằng chứng đã kiểm tra currency.

**Ràng buộc bảo mật và dữ liệu:** Giới hạn độ dài đầu vào, độ lớn và số chữ số thập phân; kiểm tra parse hết chuỗi, kiểm soát ký tự Unicode không mong muốn; tránh nhận một giá trị tiền không hợp lệ chỉ vì formatter đủ linh hoạt để đọc một phần chuỗi.

## 10. Cách hiển thị đúng khi người dùng và giao dịch có vùng khác nhau

Trong thực tế:

**Tình huống A: người mua tại Đức, hóa đơn USD.** Lưu amount `1234.50` và currency `USD`; dùng `Locale.GERMANY` trong formatter. Không thay currency bằng EUR chỉ vì người mua đang dùng `de-DE`.

**Tình huống B: người dùng Việt Nam xem giá bằng JPY.** Lưu currency `JPY`; dùng `Locale.forLanguageTag("vi-VN")` nếu muốn thông điệp và cách trình bày quen thuộc ở Việt Nam. Khi áp dụng fraction digits theo JPY, chính sách hiển thị có thể không có phần lẻ; không được tự đổi JPY sang VND.

**Tình huống C: hai báo cáo cùng số liệu, hai locale.** Giữ các `BigDecimal` và `Currency` từ cùng một nguồn dữ liệu; format riêng cho từng người đọc. Không parse lại chuỗi đã format ở locale A rồi định dạng sang locale B để tạo bản báo cáo B, bởi parsing có thể mất precision, làm tròn hoặc sai dấu.

**Tình huống D: cần hiển thị mã thay vì ký hiệu.** Một giao diện tài chính có thể chọn hiển thị `USD 1,234.50` hoặc `1.234,50 USD` theo quy tắc riêng để tránh ký hiệu `$` mơ hồ. Điều này vẫn là quyết định **trình bày**. Mã currency cần giữ trong model, không cố suy luận từ nhãn hiển thị.

**Tình huống E: tỷ giá thay đổi.** Nếu đã chuyển USD sang EUR, dữ liệu mới cần lưu cả currency EUR và giá trị EUR theo thời điểm tỷ giá; biểu diễn khác nhau ở màn hình không được coi là thao tác chuyển đổi.

## 11. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng `Currency.getInstance(userLocale)` làm tiền giao dịch | Giao dịch USD có thể bị gán thành EUR/VND theo người đọc | Nhận currency từ đơn hàng, hợp đồng hoặc sản phẩm |
| Chỉ lưu `"1.234,50 $"` thay vì amount và currency | Khó phân biệt ký hiệu, khó parse, mất dữ liệu chuẩn | Lưu `BigDecimal` và mã ISO currency |
| Coi `setCurrency(EUR)` là đổi USD sang EUR | Đổi nhãn nhưng không áp dụng tỷ giá | Thực hiện conversion nghiệp vụ trước |
| Dùng `NumberFormat.getCurrencyInstance(locale)` nhưng không setCurrency cho dữ liệu khác vùng | Sử dụng tiền mặc định của vùng, sai đơn vị | `setCurrency(transactionCurrency)` |
| Tin rằng `setCurrency(JPY)` tự đặt 0 fraction digits | Có thể vẫn in 2 chữ số do formatter gốc | Cấu hình minimum/maximum fraction digits tường minh |
| Mặc định mọi currency có hai chữ số lẻ | Sai với JPY/VND và nhiều mã khác | Kiểm tra `getDefaultFractionDigits()` và chính sách riêng |
| Nối `currency.getSymbol(locale) + amount` | Sai dấu, vị trí, khoảng trắng | Dùng currency-aware formatter |
| Đọc dấu `$` và kết luận chắc chắn USD | Biểu tượng dùng chung nhiều đồng tiền | Lưu/truyền mã `USD`, `CAD`, `AUD` cụ thể |
| Dùng `double` để tính/giữ số tiền | Sai số nhị phân, lỗi khi cộng/nhân nhiều lần | Dùng `BigDecimal`, rounding rõ ràng |
| Sử dụng chuỗi hiển thị để tính lại số tiền | Parse phụ thuộc locale, có thể đã làm tròn | Giữ giá trị domain chính xác và format tại ranh giới |
| Thay `Locale.setDefault` theo từng request | Tác động global tới request khác | Truyền locale tường minh |
| Dùng một `NumberFormat` mutable chung cho nhiều luồng và đổi currency liên tục | Dễ lẫn kết quả, formatter không bảo đảm thread-safe | Tạo formatter riêng hoặc bảo vệ đồng bộ |
| So sánh output có khoảng trắng/ký hiệu như ASCII cố định | Dễ fail khi dữ liệu CLDR/JDK thay đổi | Test cấu trúc/ngữ nghĩa, cố định provider hoặc cập nhật golden test |

Một số tiền tệ có thay đổi mã, vùng lưu hành hoặc thuộc tính theo thời gian. Dữ liệu `Currency` phụ thuộc phiên bản/configuration JDK; đối với hệ thống tài chính cần lưu trữ lâu dài, **ghi lại mã currency gốc và quy tắc có hiệu lực của giao dịch**, không xem default hiện tại của JDK là bằng chứng lịch sử.

## 12. Checklist kiểm thử

| Trường hợp | Kết quả cần đảm bảo |
| --- | --- |
| Cùng amount + USD, trình bày `en-US` và `de-DE` | Vẫn là USD, chỉ khác chuỗi hiển thị |
| Cùng locale, đổi currency USD sang EUR | Formatter dùng EUR, **không** tự quy đổi số |
| `Currency.getInstance(Locale.GERMANY)` | Trả currency vùng Đức, không đại diện mặc định cho giao dịch bất kỳ |
| `getDefaultFractionDigits` của USD/JPY/VND | Không giả định tất cả là 2 |
| `setCurrency(JPY)` trên formatter gốc US | Min/max fraction digits không đổi nếu chưa cấu hình lại |
| Amount `1234.50` là `BigDecimal` | Không mất precision do đường ép `double` |
| Giá trị âm và số rất lớn | Dấu, grouping và rounding hợp lệ |
| Locale có vị trí ký hiệu khác | Khoảng trắng, mã tiền và dấu được hiển thị đúng |
| Mã currency không hợp lệ | Bị từ chối/được xử lý bằng thông báo phù hợp |
| Input có ký hiệu `$` | Không suy luận currency từ ký hiệu mơ hồ |
| Money khác currency được cộng | Bị từ chối hoặc phải chuyển đổi theo nghiệp vụ |
| Multi-thread request với locale khác nhau | Không lẫn formatter hoặc thay đổi default JVM |
| Nâng cấp JDK/dữ liệu locale | Các golden tests UI được đánh giá lại có chủ đích |

Ngoài unit test, nên kiểm thử trên UI thực tế vì khoảng trắng không ngắt, hướng chữ, độ rộng ký hiệu và căn chỉnh các con số có thể khác nhau theo font, nền tảng và locale. Việc đúng giá trị tiền tệ nhưng bố cục khó đọc vẫn là lỗi sản phẩm.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Hóa đơn là `100 USD`, người đọc dùng `Locale.GERMANY`. Java có tự đổi thành EUR không?

**Đáp án:** Không. `Locale.GERMANY` quyết định cách trình bày; phải truyền `Currency.getInstance("USD")` cho formatter. Muốn ra EUR phải có một phép đổi tỷ giá nghiệp vụ riêng.

**Câu 2.** `Currency.getInstance("JPY").getDefaultFractionDigits()` thường là bao nhiêu? Điều đó có đảm bảo formatter đang dùng sẽ tự bỏ phần lẻ sau `setCurrency(JPY)`?

**Đáp án:** Giá trị mặc định là 0 trong dữ liệu hiện hành, nhưng `setCurrency` không tự điều chỉnh các thuộc tính minimum/maximum fraction digits của formatter. Cần cấu hình riêng theo chính sách.

**Câu 3.** `$1,234.50` và `1.234,50 $` có thể là cùng khoản tiền không?

**Đáp án:** Có, nếu cùng amount `1234.50` và cùng currency USD. Khác biệt chỉ đến từ quy ước trình bày. Chỉ ký hiệu `$` thôi chưa đủ để kết luận một giá trị chắc chắn là USD.

**Câu 4.** Tại sao lưu `BigDecimal` với `Currency` tốt hơn lưu một chuỗi tiền đã format?

**Đáp án:** Nó giữ số thập phân chính xác và đơn vị không mơ hồ, cho phép tính toán/đổi tỷ giá đúng và format theo nhiều locale mà không parse ngược chuỗi trình bày.

**Câu 5.** Muốn hiển thị `1234.50 USD` cho người dùng tiếng Việt và tiếng Anh, đâu là dữ liệu cần giữ cố định?

**Đáp án:** Giữ amount `1234.50` và currency `USD`; thay locale của formatter theo người dùng. Chỉ các yếu tố trình bày thay đổi.

**Câu 6.** Nếu người dùng chọn tiền tệ `EUR` nhưng đơn hàng gốc lưu USD, có thể chỉ gọi `formatter.setCurrency(EUR)` rồi coi như chuyển đổi thành công không?

**Đáp án:** Không. Việc đổi currency trên formatter chỉ đổi cấu hình định dạng. Cần tính ra amount EUR bằng tỷ giá và quy tắc giao dịch hợp lệ, sau đó mới định dạng kết quả.

## 14. Ghi nhớ và tham khảo

- **Currency là đơn vị tiền, Locale là quy ước trình bày.** Hai khái niệm độc lập và phải được đặt đúng vai trò.
- `Currency.getInstance("USD")` xác định đơn vị cụ thể; `Currency.getInstance(locale)` chỉ lấy currency gắn với vùng theo dữ liệu JDK, không xác nhận tiền thật của đơn hàng.
- `NumberFormat.getCurrencyInstance(locale)` tạo quy tắc hiển thị; `setCurrency(currency)` đặt đơn vị tiền cho nhãn. **Không API nào trong số này thực hiện chuyển đổi tỷ giá**.
- `setCurrency` không tự cập nhật các giới hạn số chữ số lẻ. Xem `getDefaultFractionDigits` và áp dụng chính sách hiển thị/tính toán của ứng dụng.
- Lưu amount dưới dạng `BigDecimal` và currency dưới dạng mã rõ ràng, không dùng `double` làm nguồn sự thật hoặc dùng chuỗi đã format cho tính toán.
- Format theo locale ở tầng giao diện, kiểm thử encoding/ký hiệu/khoảng trắng và dùng formatter riêng cho các luồng xử lý.

**Tài liệu chính thức:**

- [Java SE 21 — Currency](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Currency.html)
- [Java SE 21 — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html)
- [Java SE 21 — DecimalFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html)
- [Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
