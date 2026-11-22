# Currency, mã tiền tệ và locale hiển thị trong Java

## 1. Một khoản tiền có hai thông tin độc lập

Giả sử hệ thống ghi nhận **1.234,50 USD**. Người xem ở Hoa Kỳ có thể thấy `$1,234.50`, còn người xem ở Đức có thể thấy `1.234,50 $`. Cả hai đang xem **cùng một khoản tiền bằng USD**, chứ không phải hệ thống đã quy đổi sang EUR.

Trong Java, cần phân biệt:

- **`java.util.Currency`**: mô tả **đơn vị tiền tệ**, thường được nhận diện bằng mã ISO 4217 như `USD`, `EUR`, `JPY`, `VND`.
- **`java.util.Locale`**: mô tả **quy ước hiển thị** của người đọc, như dấu nhóm hàng nghìn, dấu thập phân, ký hiệu và vị trí ký hiệu tiền.
- **`java.text.NumberFormat`**: định dạng **giá trị số** thành chuỗi tiền tệ theo locale và currency được cấu hình.
- **`BigDecimal`**: kiểu số thường phù hợp với giá trị tiền cần tính toán thập phân chính xác.

Ba khía cạnh cần quản lý tách biệt là **số tiền (amount)**, **đơn vị tiền (currency)** và **locale người xem (display locale)**.

| Amount | Currency | Display locale | Chuỗi thường thấy |
| ---: | --- | --- | --- |
| `1234.50` | `USD` | `en-US` | `$1,234.50` |
| `1234.50` | `USD` | `de-DE` | `1.234,50 $` |
| `1234.50` | `EUR` | `de-DE` | `1.234,50 €` |
| `1234` | `JPY` | `ja-JP` | `￥1,234` hoặc ký hiệu yen tương đương tùy JDK/provider |

Đầu ra cụ thể phụ thuộc dữ liệu locale, JDK và provider. Ví dụ ký hiệu tiền có thể là `$`, `US$`, `USD` hoặc ký tự khác theo ngữ cảnh; dấu cách trước ký hiệu có thể là **NBSP** (`U+00A0`) hoặc dạng khoảng trắng đặc biệt. Không nên viết test dựa trên hình thức ký hiệu của mọi locale nếu không kiểm soát môi trường chạy.

**Điểm mấu chốt:** `Locale.GERMANY` **không biến** khoản tiền `USD` thành `EUR`. Nó chỉ cung cấp quy ước để trình bày. Việc đổi đơn vị tiền là một **nghiệp vụ chuyển đổi tiền tệ** riêng, cần tỷ giá, thời điểm áp dụng và quy tắc làm tròn.

## 2. `Currency` là gì? Mã ISO 4217 có nghĩa gì?

`java.util.Currency` đại diện cho đơn vị tiền tệ theo dữ liệu tiền tệ được JDK cung cấp. Đối tượng này là **bất biến**. Cách tạo thường dùng là:

~~~java
Currency usd = Currency.getInstance("USD");
Currency eur = Currency.getInstance("EUR");
Currency jpy = Currency.getInstance("JPY");
Currency vnd = Currency.getInstance("VND");
~~~

Đoạn trên là **mảnh mã trong method**, cần `import java.util.Currency;`.

### 2.1. Mã tiền tệ không phải mã quốc gia

Ví dụ:

| Mã | Đơn vị tiền | Mã quốc gia/vùng liên quan trong ví dụ |
| --- | --- | --- |
| `USD` | US dollar | `US` |
| `EUR` | Euro | `DE` và nhiều nước thuộc khu vực dùng euro |
| `JPY` | Japanese yen | `JP` |
| `VND` | Vietnamese đồng | `VN` |

`USD`, `EUR` là **currency code** theo ISO 4217. `US`, `DE`, `JP`, `VN` là **region code** trong locale. Chúng khác mục đích và **không thể thay thế cho nhau**.

Ví dụ sai:

~~~java
// Sai: "US" là mã vùng, không phải mã tiền tệ ISO 4217.
Currency wrong = Currency.getInstance("US");
~~~

Lời gọi này có thể ném `IllegalArgumentException` vì mã không hợp lệ. Tương tự, không thể tạo một locale bằng mã `USD` rồi hy vọng nó đại diện đúng người xem.

### 2.2. Các phương thức hữu ích

| API | Giá trị/trách nhiệm |
| --- | --- |
| `Currency.getInstance("USD")` | Lấy currency theo mã ISO 4217 |
| `Currency.getInstance(locale)` | Lấy đơn vị tiền gắn với vùng của locale nếu có |
| `getCurrencyCode()` | Trả mã ba chữ cái, ví dụ `USD` |
| `getNumericCode()` | Trả mã số ISO 4217, ví dụ `840` cho USD |
| `getDefaultFractionDigits()` | Số chữ số thập phân mặc định theo đơn vị tiền; có thể là `-1` cho một số mã đặc biệt |
| `getSymbol(locale)` | Ký hiệu tiền phù hợp locale được truyền |
| `getDisplayName(locale)` | Tên hiển thị của tiền theo ngôn ngữ/locale |
| `Currency.getAvailableCurrencies()` | Tập các currency mà JDK biết |

`getNumericCode()` trả `int` nên nếu cần trao đổi **mã số ISO có ba chữ số**, phải xử lý padding theo quy định giao thức thay vì mặc định `int` luôn giữ số 0 ở đầu.

**Không dùng `getDefaultFractionDigits()` làm “quy tắc kế toán duy nhất”**: nó là thông tin số chữ số mặc định, không phải mọi quy tắc về thanh toán tiền mặt, chuyển khoản, pricing, thuế, khấu trừ hay rounding. Ví dụ một giao dịch có thể yêu cầu precision khác tùy hệ thống tài chính, dù currency code giống nhau.

## 3. Tạo Currency bằng mã và bằng Locale

Hai lời gọi sau có mục đích khác nhau:

~~~java
Currency byCode = Currency.getInstance("USD");
Currency byRegion = Currency.getInstance(Locale.GERMANY);
~~~

Đoạn trên cần import `java.util.Currency` và `java.util.Locale`.

- `getInstance("USD")` chọn **chính xác currency USD** mà dữ liệu nhận diện.
- `getInstance(Locale.GERMANY)` chọn currency gắn với **vùng DE**, thông thường là `EUR`.
- Locale có thể thiếu quốc gia hoặc thuộc vùng không có currency hợp lệ. Không được giả định mọi `Locale` đều sinh ra `Currency`; API có thể ném `IllegalArgumentException` khi thiếu region, hoặc trả `null` đối với vùng không có tiền tệ trong dữ liệu JDK.

Đặc biệt, lấy currency từ locale chỉ phù hợp khi **yêu cầu nghiệp vụ thật sự là “đơn vị tiền mặc định của vùng này”**. Nó không phù hợp khi đã có mã tiền của giao dịch.

Ví dụ, cùng một người xem `Locale.GERMANY` có thể nhận hóa đơn `USD`, `EUR` hoặc `JPY`. **Hãy giữ currency của giao dịch trong dữ liệu** thay vì suy ra một cách không chính xác từ địa điểm hoặc ngôn ngữ người xem.

## 4. Ví dụ đầy đủ: đọc mã, mã số, số lẻ mặc định

Lưu thành `CurrencyIdentityDemo.java`:

~~~java
import java.util.Currency;
import java.util.Locale;

public class CurrencyIdentityDemo {
    public static void main(String[] args) {
        Currency usd = Currency.getInstance("USD");
        Currency jpy = Currency.getInstance("JPY");

        System.out.println("USD code: " + usd.getCurrencyCode());
        System.out.println("USD numeric: " + usd.getNumericCode());
        System.out.println("USD digits: " + usd.getDefaultFractionDigits());

        System.out.println("JPY code: " + jpy.getCurrencyCode());
        System.out.println("JPY digits: " + jpy.getDefaultFractionDigits());

        System.out.println("DE default: "
                + Currency.getInstance(Locale.GERMANY).getCurrencyCode());
        System.out.println("JP default: "
                + Currency.getInstance(Locale.JAPAN).getCurrencyCode());
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 CurrencyIdentityDemo.java
java CurrencyIdentityDemo
~~~

Trên dữ liệu ISO 4217 phổ biến của JDK, kết quả:

~~~text
USD code: USD
USD numeric: 840
USD digits: 2
JPY code: JPY
JPY digits: 0
DE default: EUR
JP default: JPY
~~~

Diễn giải:

- `Currency.getInstance("USD")` không phụ thuộc locale hiển thị.
- `getNumericCode()` cung cấp mã số chuẩn của currency, **không** phải tỷ giá hay số tiền.
- `USD` thường có hai chữ số lẻ mặc định, `JPY` không có chữ số lẻ mặc định.
- Currency mặc định từ `Locale.GERMANY` là `EUR` và từ `Locale.JAPAN` là `JPY` theo dữ liệu hiện hành.

Dữ liệu currency của JDK có thể được cập nhật khi một nước đổi tiền hoặc quy tắc ISO thay đổi. Với nghiệp vụ nhạy cảm về lịch sử giao dịch, lưu rõ currency code và ngày giao dịch; không tự suy từ locale ở thời điểm hiển thị.

## 5. Cùng một Currency, nhiều Locale hiển thị

Đây là kịch bản phổ biến nhất của ứng dụng đa ngôn ngữ: **số tiền và đơn vị tiền không đổi**, nhưng người xem khác nhau sẽ thấy cách nhóm số, dấu thập phân và ký hiệu khác nhau.

### Ví dụ Java 17+ hoàn chỉnh

Tạo `CurrencyDisplayDemo.java`:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class CurrencyDisplayDemo {
    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("1234.50");
        Currency currency = Currency.getInstance("USD");

        NumberFormat forUS =
                NumberFormat.getCurrencyInstance(Locale.US);
        forUS.setCurrency(currency);
        forUS.setMinimumFractionDigits(2);
        forUS.setMaximumFractionDigits(2);

        NumberFormat forGermany =
                NumberFormat.getCurrencyInstance(Locale.GERMANY);
        forGermany.setCurrency(currency);
        forGermany.setMinimumFractionDigits(2);
        forGermany.setMaximumFractionDigits(2);

        System.out.println("Amount: " + amount.toPlainString());
        System.out.println("Currency: " + currency.getCurrencyCode());
        System.out.println("US view: " + forUS.format(amount));
        System.out.println("DE view: " + forGermany.format(amount));
        System.out.println("Still USD: " + currency.getCurrencyCode());
    }
}
~~~

Lệnh chạy:

~~~bash
javac -encoding UTF-8 CurrencyDisplayDemo.java
java CurrencyDisplayDemo
~~~

Kết quả minh họa với JDK/provider CLDR thông dụng:

~~~text
Amount: 1234.50
Currency: USD
US view: $1,234.50
DE view: 1.234,50 $
Still USD: USD
~~~

**Lưu ý Unicode:** Khoảng trắng trước dấu `$` ở dòng tiếng Đức trên là dấu cách không ngắt `U+00A0` (NBSP), không phải dấu cách ASCII thông thường. Ký hiệu và khoảng cách có thể khác trên môi trường/provider khác. Nếu kiểm thử tự động cần so sánh chuỗi chính xác, hãy biết phiên bản JDK/provider đang dùng và kiểm tra code point thay vì nhìn màn hình.

Các bước trong mã:

1. `amount` là số tiền, được lưu bằng `BigDecimal`.
2. `currency` luôn là `USD`, được xác định từ mã currency.
3. Hai `NumberFormat` được tạo từ **hai locale hiển thị khác nhau**.
4. `setCurrency(currency)` áp dụng USD cho từng formatter.
5. Hai formatter tạo hai chuỗi trình bày khác nhau, nhưng `amount` và `currency` không đổi.

**Quy tắc:** Đừng dịch ký hiệu tiền bằng cách ghép chuỗi thủ công `"$" + amount` hoặc `amount + " USD"` trừ khi giao thức/thiết kế yêu cầu hình thức cố định. Vị trí ký hiệu, khoảng cách, dấu và quy ước chữ số là vấn đề locale.

## 6. `NumberFormat.getCurrencyInstance(locale)` có tự chọn currency không?

Có. Khi bạn gọi:

~~~java
NumberFormat formatter =
        NumberFormat.getCurrencyInstance(Locale.GERMANY);
~~~

Formatter mặc định dùng quy ước tiền của locale đó, thường với `EUR` trong `de-DE`. Nhưng điều này chỉ đúng khi ứng dụng muốn **hiển thị tiền mặc định của vùng**, không tự động đúng cho một giao dịch USD.

Đối với giao dịch có currency code riêng, cần thiết lập tường minh:

~~~java
NumberFormat formatter =
        NumberFormat.getCurrencyInstance(Locale.GERMANY);
formatter.setCurrency(Currency.getInstance("USD"));
~~~

**Điều quan trọng:** `setCurrency(...)` là thay đổi currency mà formatter sử dụng khi tạo ký hiệu tiền và thông tin liên quan. Theo hợp đồng API, **nó không nhất thiết cập nhật số chữ số thập phân tối thiểu/tối đa của formatter**. Những thuộc tính đó có thể vẫn là cấu hình lúc formatter được tạo.

### 6.1. Vì sao setCurrency không đủ để đổi precision?

Thử chương trình `CurrencyDigitsDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class CurrencyDigitsDemo {
    public static void main(String[] args) {
        Currency jpy = Currency.getInstance("JPY");
        NumberFormat format =
                NumberFormat.getCurrencyInstance(Locale.US);

        format.setCurrency(jpy);
        System.out.println("Digits after setCurrency: "
                + format.getMaximumFractionDigits());

        format.setMinimumFractionDigits(jpy.getDefaultFractionDigits());
        format.setMaximumFractionDigits(jpy.getDefaultFractionDigits());
        format.setRoundingMode(RoundingMode.HALF_UP);

        System.out.println("Digits after configuration: "
                + format.getMaximumFractionDigits());
        System.out.println("JPY amount: "
                + format.format(new BigDecimal("1234.50")));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 CurrencyDigitsDemo.java
java CurrencyDigitsDemo
~~~

Với JDK/provider thường gặp, kết quả:

~~~text
Digits after setCurrency: 2
Digits after configuration: 0
JPY amount: ¥1,235
~~~

Giải thích:

- Formatter tạo từ `Locale.US` có độ chính xác tiền tệ ban đầu thường là **hai** chữ số lẻ (currency USD mặc định).
- Gọi `setCurrency(JPY)` không tự đổi giới hạn chữ số lẻ.
- Sau đó, mã đặt tường minh số chữ số lẻ theo `jpy.getDefaultFractionDigits()` (thường bằng `0`).
- `RoundingMode.HALF_UP` làm rõ cách xử lý `1234.50 → 1235` khi hiển thị không có phần thập phân.

Ký hiệu yen hiển thị có thể khác dạng Unicode hoặc theo dữ liệu locale. Không lấy dấu `¥` làm mã nhận diện duy nhất của currency; tiền Nhật và một số đồng tiền khác có thể dùng ký hiệu hình thức gần giống nhau.

**Với currency trả `getDefaultFractionDigits() == -1`:** Không gọi trực tiếp `setMinimumFractionDigits(-1)` hay `setMaximumFractionDigits(-1)`; các phương thức đòi hỏi giá trị không âm. Xác định quy tắc precision riêng hoặc chính sách fallback cho mã đặc biệt. Đối với ứng dụng thanh toán, số chữ số lẻ phải xuất phát từ **quy tắc nghiệp vụ cụ thể**, không đơn thuần lấy mặc định trình bày của JDK.

## 7. `Currency.getSymbol(locale)` và `getDisplayName(locale)`

Hai phương thức này sử dụng locale để biểu diễn **cùng một currency**:

~~~java
Currency usd = Currency.getInstance("USD");

String code = usd.getCurrencyCode();               // "USD"
String usSymbol = usd.getSymbol(Locale.US);        // thường là "$"
String germanSymbol = usd.getSymbol(Locale.GERMANY);
String germanName = usd.getDisplayName(Locale.GERMANY);
~~~

Đoạn trên cần import `java.util.Currency`, `java.util.Locale` và được đặt trong method.

- `getCurrencyCode()`: mã ổn định dùng để **nhận diện** đơn vị tiền.
- `getSymbol(locale)`: ký hiệu để **trình bày** theo locale.
- `getDisplayName(locale)`: tên để **trình bày** theo ngôn ngữ người đọc.

Trên JDK có dữ liệu CLDR tiếng Đức, tên `USD` có thể được biểu diễn là `US-Dollar`; ký hiệu có thể là `$` hoặc dạng phân biệt như `US$` tùy dữ liệu/provider. Những chuỗi này là dữ liệu giao diện có thể được cập nhật, **không phải định danh để lưu giao dịch**.

Không dùng `getSymbol()` làm khóa hệ thống, bởi ký hiệu như `$` được nhiều đồng tiền sử dụng. Không phân tích một chuỗi có dấu `$` rồi tự suy ra đó là USD nếu hệ thống chấp nhận tiền Canada, Australia hoặc nhiều đồng tiền khác.

## 8. Đơn vị tiền khác với locale và khác với chuyển đổi ngoại tệ

Giả sử hệ thống có số tiền:

~~~text
amount = 100.00
currency = USD
displayLocale = de-DE
~~~

Lệnh:

~~~java
NumberFormat format =
        NumberFormat.getCurrencyInstance(Locale.GERMANY);
format.setCurrency(Currency.getInstance("EUR"));
String text = format.format(new BigDecimal("100.00"));
~~~

Đây là **mảnh mã minh họa** trong method, cần import `java.text.NumberFormat`, `java.util.Currency`, `java.util.Locale` và `java.math.BigDecimal`.

Đoạn này chỉ làm formatter hiển thị **100 EUR**, **không** đổi `100 USD` thành một số EUR tương đương. Nếu `100` ban đầu là USD, in thêm ký hiệu EUR là **sai đơn vị**.

### Chuyển đổi tiền tệ là bài toán riêng

Để chuyển đổi:

\[
\text{amount}_{EUR}
=
\text{amount}_{USD}
\times
\text{tỷ giá}_{USD \rightarrow EUR}
\]

Bạn cần có tỷ giá được lấy từ nguồn có thẩm quyền cho nghiệp vụ, thời điểm tỷ giá có hiệu lực, chính sách làm tròn và quy định ghi nhận giao dịch. Java SE không cung cấp hàm `Currency.convert(...)` hoặc một tỷ giá hiện hành tự động trong `java.util.Currency`.

Ví dụ minh họa **chỉ dùng tỷ giá giả định, không phải báo giá thực tế**:

~~~java
BigDecimal usdAmount = new BigDecimal("100.00");
BigDecimal exampleRate = new BigDecimal("0.90"); // Tỷ giá giả định
BigDecimal eurAmount = usdAmount.multiply(exampleRate);
System.out.println(eurAmount.toPlainString()); // 90.0000
~~~

Đoạn trên là mảnh mã trong method, cần import `java.math.BigDecimal`. Kết quả phép nhân ở đây có thể giữ scale theo các toán hạng; nếu trong ví dụ trên hai `BigDecimal` có scale 2 thì `100.00 × 0.90 = 90.0000`. Sau đó mới áp dụng quy tắc rounding/scale nghiệp vụ cho số tiền EUR và **chỉ cuối cùng** format để hiển thị.

**Không nhầm “đổi ký hiệu” với “đổi đơn vị”.** Một cách thiết kế an toàn là gói `amount` và `currencyCode` trong cùng đối tượng nghiệp vụ, để không thể vô ý thay đổi mỗi ký hiệu hiển thị mà quên quy đổi số.

## 9. Chọn kiểu lưu tiền: BigDecimal và mã tiền tệ

Java không có một kiểu giá trị tiền chung trong Java SE vừa chứa amount, Currency, phép toán, tỷ giá và các quy tắc nghiệp vụ. `Currency` chỉ mô tả đơn vị tiền, **không chứa số tiền**.

Một thiết kế dữ liệu đơn giản:

~~~java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
    }
}
~~~

Lưu thành `Money.java`. Với record Java 17, chương trình có thể tạo:

~~~java
Money invoice = new Money(
        new BigDecimal("1234.50"),
        Currency.getInstance("USD")
);
~~~

Đây là **mảnh mã trong phương thức**, sử dụng class `Money` đã định nghĩa; import `java.math.BigDecimal` và `java.util.Currency`.

Ưu điểm:

- Amount và currency đi cùng nhau, tránh nhầm khoản USD với EUR.
- Các phép cộng/trừ có thể kiểm tra currency trước khi thao tác.
- Chương trình quyết định rõ khi nào thực hiện quy đổi.
- Locale hiển thị được truyền riêng vào tầng giao diện, không cố định cùng bản ghi.

**Cần bổ sung theo nghiệp vụ thực tế:** phép cộng hai `Money` khác currency phải từ chối hoặc dùng bước quy đổi được kiểm soát. Đối với thanh toán, cần quy định cách rounding và precision. `BigDecimal` không tự giải quyết mọi vấn đề như làm tròn tiền mặt, quy định pháp lý, ngày giao dịch hay scale hợp lệ của từng phương thức thanh toán.

### Ví dụ mô hình hóa đúng ranh giới

~~~text
Dữ liệu giao dịch:
  amount       = 1234.50
  currencyCode = USD
          |
          v
  Currency.getInstance("USD")
          |
          +-----------------------------+
          |                             |
          v                             v
Display locale = en-US        Display locale = de-DE
          |                             |
          v                             v
  $1,234.50                  1.234,50 $ (ví dụ)
          \                             /
           \___________________________/
               Vẫn là 1234.50 USD
~~~

Việc thêm `locale` ở tầng hiển thị **không** làm thay đổi currency của giao dịch trong dữ liệu.

## 10. Phân tích chuỗi tiền tệ và nhận diện đơn vị tiền

`NumberFormat.getCurrencyInstance(locale)` có thể được dùng để parse một chuỗi theo quy ước locale:

~~~java
NumberFormat parser =
        NumberFormat.getCurrencyInstance(Locale.US);
Number number = parser.parse("$1,234.50");
~~~

Đây là mảnh mã trong method, cần import `java.text.NumberFormat`, `java.util.Locale`; `parse` có thể ném `ParseException` nên cần xử lý exception hoặc khai báo.

Tuy nhiên, **không coi `NumberFormat.parse(...)` là bước xác thực currency code của giao dịch**. Nó có thể đọc ra giá trị số theo mẫu của formatter, nhưng không tự cung cấp một bản ghi business `(amount, currencyCode)` được xác thực một cách độc lập.

Ví dụ chuỗi `"$1,234.50"` **không phải định danh currency đáng tin** vì `$` có thể được dùng trong nhiều hệ thống tiền tệ. Nguồn dữ liệu nghiệp vụ nên truyền mã ISO 4217 **riêng** với amount.

### Nếu cần parser ở giao diện

1. Biết trước **currencyCode** mà biểu mẫu cho phép, ví dụ `USD`.
2. Biết **displayLocale** của người nhập để đọc đúng dấu nhóm, dấu thập phân và chữ số.
3. Dùng formatter/parser phù hợp và xác minh **đã tiêu thụ toàn bộ chuỗi**.
4. Kiểm tra giá trị hợp lệ: không âm hay được phép âm, giới hạn, precision, ngày giao dịch.
5. Không tự suy currency từ ký hiệu hiển thị duy nhất.

Có thể dùng `ParsePosition` để kiểm tra phần đầu hợp lệ:

~~~java
ParsePosition position = new ParsePosition(0);
Number parsed = parser.parse(input, position);

if (parsed == null || position.getIndex() != input.length()) {
    throw new IllegalArgumentException("Invalid currency input");
}
~~~

Đây là **mảnh mã minh họa** trong method; cần import `java.text.ParsePosition`, biến `parser` đã là `NumberFormat` và `input` là chuỗi cần kiểm tra. Kiểm tra tiêu thụ toàn bộ input là cần thiết nhưng **chưa đảm bảo** parser đã kiểm tra mọi quy tắc nghiệp vụ hoặc đúng mã currency. Đối với API máy-máy, ưu tiên chuyển amount và currencyCode theo hai trường tường minh, không đưa chuỗi tiền đã bản địa hóa làm định dạng giao tiếp.

### `DecimalFormat.setParseBigDecimal(true)`

Để phân tích số thập phân với precision tốt hơn, khi formatter thực sự là `DecimalFormat`, có thể cấu hình:

~~~java
DecimalFormat parser = (DecimalFormat)
        NumberFormat.getCurrencyInstance(Locale.US);
parser.setParseBigDecimal(true);
~~~

Đây là mảnh mã cần import `java.text.DecimalFormat`, `java.text.NumberFormat`, `java.util.Locale`. **Không giả định mọi implementation của `NumberFormat` bắt buộc là `DecimalFormat`**. Nếu dùng cast trong mã cần chạy trên nhiều provider/JDK, kiểm tra kiểu thực tế hoặc xây dựng parser phù hợp với hệ thống. `setParseBigDecimal` không tự xác thực mã currency.

## 11. Những lỗi thường gặp

| Hiểu sai | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| “Locale là currency.” | Lấy sai tiền của hóa đơn | Lưu currencyCode của giao dịch và displayLocale riêng |
| “`Locale.GERMANY` nghĩa là mọi hóa đơn đều bằng EUR.” | Đổi nhầm đơn vị USD thành EUR | `getCurrencyInstance(Locale.GERMANY)` chỉ chọn currency mặc định của vùng |
| “Gọi `setCurrency(EUR)` là đổi USD sang EUR.” | Giữ nguyên số tiền, nhưng đổi ký hiệu làm sai bản chất | Muốn quy đổi phải có tỷ giá và phép tính riêng |
| “Mọi currency đều có hai chữ số thập phân.” | Sai với JPY và các trường hợp khác | Kiểm tra `getDefaultFractionDigits()` cùng quy tắc nghiệp vụ |
| “`setCurrency` luôn cập nhật fraction digits.” | Có thể hiển thị JPY với hai chữ số lẻ | Thiết lập min/max fraction digits tường minh khi cần |
| “Symbol `$` là định danh duy nhất của USD.” | Nhầm với CAD, AUD và currency khác | Lưu/trao đổi mã ISO 4217 |
| “`NumberFormat.parse` trả amount và currency chính xác.” | Không xác minh được mã tiền của giao dịch | Parse amount theo locale, currencyCode xác nhận riêng |
| “`double` luôn đủ chính xác cho tiền.” | Có thể sinh sai số số học nhị phân | Cân nhắc `BigDecimal` và quy tắc rounding |
| “Gọi `Currency.getInstance(Locale)` lúc nào cũng có kết quả.” | Locale thiếu country hoặc vùng không có currency | Kiểm tra điều kiện, xử lý `null`/exception theo API |
| “Dùng ký hiệu tiền trong log/API là ổn.” | Ký hiệu/locale thay đổi làm dữ liệu khó phân tích | Truyền amount và currencyCode theo giao thức nhất quán |
| “`NumberFormat` dùng chung mọi request là an toàn.” | Trạng thái mutable có thể bị thay đổi giữa các luồng | Tạo/copy formatter theo request hoặc đồng bộ phù hợp |
| “Currency code tự chứa tỷ giá.” | Tính toán chuyển đổi sai | Tỷ giá là dữ liệu độc lập có thời điểm hiệu lực |

## 12. Checklist ứng dụng và kiểm thử

**Khi thiết kế model và API:**

- Lưu **amount** và **currencyCode** tường minh, chẳng hạn `1234.50` và `"USD"`.
- Cân nhắc `BigDecimal` cho tiền; quy định rõ scale, rounding và precision tại ranh giới nghiệp vụ.
- Tách **locale hiển thị** khỏi currency của giao dịch.
- Nếu tự chọn currency theo vùng, ghi rõ đó là currency mặc định của vùng và xử lý trường hợp không có.
- Không cho phép đổi currency trong model chỉ bằng thao tác sửa ký hiệu của formatter.

**Khi định dạng:**

- Gọi `NumberFormat.getCurrencyInstance(displayLocale)`.
- Nếu currency giao dịch đã biết, gọi `setCurrency(currency)`.
- Cấu hình fraction digits và rounding theo yêu cầu; không giả định `setCurrency` tự thay tất cả.
- Kiểm thử trên locale `en-US`, `de-DE`, `vi-VN` và ít nhất currency có số lẻ khác nhau, ví dụ USD/JPY.
- Đảm bảo code không phụ thuộc `Locale.getDefault()` của máy chủ khi đã có locale người dùng.
- Kiểm tra các ký tự Unicode trong output nếu yêu cầu so sánh chuỗi chính xác.

**Khi xử lý dữ liệu:**

- Không parse chuỗi hiển thị để lấy mã currency nếu hệ thống có trường currencyCode riêng.
- Không lưu biểu diễn chuỗi như `"1.234,50 $"` thay cho amount và code trong cơ sở dữ liệu chính.
- Khi đổi currency, ghi nhận nguồn tỷ giá, thời điểm và quy tắc tính.
- Nếu API nhận mã tiền từ người dùng, validate mã với `Currency.getInstance(code)` và chính sách đồng tiền sản phẩm cho phép.

## 13. Bài tập tự kiểm tra

1. Tạo `Currency.getInstance("USD")`, in `getCurrencyCode()`, `getNumericCode()` và `getDefaultFractionDigits()`. Vì sao ba giá trị này khác `Locale.US`?
2. Một người dùng có `Locale.GERMANY` muốn xem số dư `1234.50 USD`. Hãy sử dụng `NumberFormat.getCurrencyInstance(Locale.GERMANY)` rồi `setCurrency(USD)`; giải thích vì sao không được đổi thành EUR nếu không có tỷ giá.
3. Tạo một formatter từ `Locale.US`, gọi `setCurrency(JPY)`, kiểm tra `getMaximumFractionDigits()` trước và sau khi cấu hình `getDefaultFractionDigits()`. Vì sao nên ghi rõ precision?
4. Giải thích vì sao `Currency.getSymbol(Locale.US)` không thể thay `getCurrencyCode()` trong cấu trúc lưu giao dịch.
5. Thiết kế lớp/record `Money` chứa amount và currency. Viết quy tắc kiểm tra khi cộng hai khoản tiền khác currency.
6. Tỷ giá **giả định** 1 USD = 0.90 EUR. Với amount `100.00 USD`, tính giá trị EUR bằng `BigDecimal` và phân biệt bước **quy đổi amount** với bước **định dạng kết quả**.
7. Vì sao không nên parse `"$1,234.50"` để tự suy ra đơn vị USD? Nếu dữ liệu đến từ biểu mẫu, bạn cần thêm thông tin nào?
8. Kiểm thử cùng `Money(1234.50, USD)` trên `Locale.US` và `Locale.GERMANY`. Những thuộc tính nào được phép khác và những thuộc tính nào phải bất biến?

**Ghi nhớ:** `Currency` xác định **đơn vị tiền** bằng mã như `USD` hoặc `EUR`; `Locale` xác định **quy ước hiển thị**; `NumberFormat` kết hợp hai thông tin đó để tạo chuỗi tiền. **Đổi currency trong formatter không phải chuyển đổi tỷ giá**, và **đổi locale không làm khoản tiền đổi đơn vị**. Hãy giữ amount, currency code và display locale riêng, dùng `BigDecimal` khi cần chính xác, đồng thời cấu hình precision/rounding phù hợp.

### Tài liệu tham khảo

- [Java SE 17 — Currency](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html) — mã ISO 4217, ký hiệu/tên hiển thị và số chữ số lẻ mặc định.
- [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html) — `getCurrencyInstance`, `setCurrency`, formatting và parsing theo locale.
- [Java SE 17 — DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html) — chính sách pattern, fraction digits và parsing số thập phân.
- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html) — giá trị số thập phân và quy tắc rounding.