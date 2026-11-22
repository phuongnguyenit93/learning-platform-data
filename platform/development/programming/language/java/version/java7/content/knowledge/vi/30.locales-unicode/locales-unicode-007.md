# Currency: tên hiển thị và mã tiền tệ dạng số trong Java

**Chủ đề:** Java 7 — Locale và Unicode  
**Bài học:** Currency: tên hiển thị và mã tiền tệ dạng số  
**Phiên bản:** Java 17+; những API `java.util.Currency.getDisplayName(Locale)` và `getNumericCode()` được thêm ở Java 7 vẫn **hiện hành**. `getNumericCodeAsString()` được bổ sung từ Java 9 và nên ưu tiên khi cần một mã số ISO 4217 chính xác ba ký tự. Nội dung không sử dụng kỹ thuật đã lỗi thời/legacy; các ví dụ biên dịch được bằng JDK 17+, không cần thư viện ngoài.

## 1. Cần phân biệt ba ý nghĩa của “tên tiền tệ”

Khi phần mềm hiển thị một số tiền cho người dùng, thường có ít nhất ba biểu diễn liên quan đến **cùng một đơn vị tiền tệ**:

1. **Mã chữ ISO 4217:** ví dụ `USD`, `VND`, `AUD`. Đây là định danh dạng ba chữ cái, phù hợp trao đổi dữ liệu giữa các hệ thống.
2. **Mã số ISO 4217:** ví dụ `840`, `704`, `036`. Đây là mã định danh ba chữ số, **không phải số tiền, tỷ giá hay số chữ số thập phân**.
3. **Tên hiển thị bản địa hóa:** ví dụ USD có thể được hiển thị là `US Dollar` với `Locale.US` và `Đô la Mỹ` với locale tiếng Việt theo dữ liệu bản địa hóa của JDK đang chạy.

Một biểu diễn thứ tư là **ký hiệu tiền tệ** — `$`, `₫`, `¥`, `€`… — nhưng ký hiệu có thể dùng chung giữa nhiều đồng tiền hoặc thay đổi tùy locale; không dùng nó làm ID.

**`Currency` chỉ mô tả đơn vị tiền tệ** (ISO code, name/symbol, minor units); bản thân nó không chứa giá trị tiền, không tính tỷ giá và không xác minh giao dịch thanh toán. Nếu ứng dụng nhận “12.50 USD”, số `12.50` nên được lưu trong `BigDecimal` hoặc một kiểu money chuyên biệt, còn `USD` là định danh của `Currency`.

### 1.1. Cách nhìn đúng về dữ liệu

```text
                  Một Currency: USD
                         |
      +------------------+--------------------+
      |                  |                    |
getCurrencyCode()  getNumericCode()  getDisplayName(locale)
      |                  |                    |
     "USD"              840          "US Dollar" / "Đô la Mỹ" ...
      |                  |                    |
  định danh chữ     định danh số       nhãn hiển thị cho UI
      |
      +-- getSymbol(locale) -> ký hiệu phụ thuộc ngữ cảnh
      +-- getDefaultFractionDigits() -> minor unit gợi ý, không là tỷ giá
```

**Trọng tâm bài:** hiểu rõ `Currency.getDisplayName(Locale)` và **mã tiền tệ dạng số**, bao gồm tình huống mã số có số `0` đầu, mối quan hệ với `Locale` và Unicode, những lỗi định dạng/lưu trữ thường gặp và các cách dùng API đúng trong ứng dụng hiện đại.

## 2. API java.util.Currency còn được hỗ trợ

`java.util.Currency` là `final class` trong `java.base`. Nó có cơ chế quản lý instance theo từng code, không có public constructor; lấy qua các factory `Currency.getInstance(...)`.

| Method | Kết quả và ý nghĩa | Lưu ý |
| --- | --- | --- |
| `getInstance("USD")` | Lấy Currency theo mã chữ ISO 4217 | Code phải được JDK hỗ trợ; input sai → exception |
| `getInstance(Locale.US)` | Lấy tiền tệ gắn với vùng/lãnh thổ của locale | Khác việc dịch tên; có thể trả `null` cho vùng không có tiền tệ |
| `getCurrencyCode()` | `String` mã chữ như `USD` | ID để lưu/trao đổi dữ liệu |
| `getNumericCode()` | `int` như `36` cho AUD | Có từ Java 7; **không giữ số 0 đầu** |
| `getNumericCodeAsString()` | `String` ba chữ số như `036` | Có từ Java 9; **giữ đủ ba ký tự** |
| `getDisplayName()` | Tên hiển thị theo default `DISPLAY` locale | Có từ Java 7; phụ thuộc global display locale |
| `getDisplayName(Locale locale)` | Tên hiển thị theo locale chỉ định | Nên ưu tiên cho request/user cụ thể |
| `getSymbol(Locale locale)` | Ký hiệu của đơn vị tiền tệ trong locale | Ký hiệu không bảo đảm duy nhất |
| `getDefaultFractionDigits()` | Số chữ số sau dấu phân cách theo default minor unit | Có thể trả `-1` cho pseudo-currency |
| `getAvailableCurrencies()` | Tập codes mà runtime biết | Có thể chứa code cũ/không còn giao dịch |
| `toString()` | Mã chữ ISO 4217 | Không phải tên hiển thị |

**Về mốc phiên bản:** Java 7 đã có `getNumericCode()`, `getDisplayName()` và `getDisplayName(Locale)`. `getNumericCodeAsString()` xuất hiện **từ Java 9** — vì vậy dự án chạy Java 17+ nên dùng phương thức hiện đại này khi cần đúng chuỗi ba chữ số; không viết bài Java 7 mà khẳng định method đó tồn tại từ Java 7.

### 2.1. Định danh tiền tệ khác dữ liệu ngôn ngữ

`Currency.getInstance("USD")` không mang theo ngôn ngữ English/Vietnamese. Tên chỉ xuất hiện khi bạn hỏi `currency.getDisplayName(locale)`. Cùng một Currency có thể có tên khác nhau với các locale khác nhau, nhưng code `USD` và numeric code `840` không thay đổi chỉ vì đổi ngôn ngữ hiển thị.

### 2.2. Không tạo object Currency bằng new

Không có public `new Currency(...)`. Nếu cần một đơn vị tiền tệ được JDK biết tới, dùng:

```java
Currency currency = Currency.getInstance("VND");
```

Đây là **snippet** trong class có `import java.util.Currency;`. `Currency` được thiết kế để cùng mã tiền tệ chỉ có một instance do factory quản lý; không tự tự định nghĩa/deserialize một object giả thay vì dùng factory.

## 3. Chương trình 1 — mã chữ, mã số và bản sắc Currency

Tạo file `CurrencyBasicDemo.java`:

```java
import java.util.Currency;
import java.util.Locale;
public class CurrencyBasicDemo {
  public static void main(String[] args) {
    Currency byCode = Currency.getInstance("USD");
    Currency byCountry = Currency.getInstance(Locale.US);
    System.out.println("code=" + byCode.getCurrencyCode());
    System.out.println("numeric=" + byCode.getNumericCode());
    System.out.println("numeric-text=" + byCode.getNumericCodeAsString());
    System.out.println("same-currency-instance=" + (byCode == byCountry));
    System.out.println("toString-is-code=" + byCode.toString().equals("USD"));
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CurrencyBasicDemo.java
java CurrencyBasicDemo
```

**stdout đã kiểm thử:**

```text
code=USD
numeric=840
numeric-text=840
same-currency-instance=true
toString-is-code=true
```

**Giải thích:**

- `getInstance("USD")` chọn đơn vị USD trực tiếp.
- `getInstance(Locale.US)` tìm tiền tệ theo vùng US; trong dữ liệu hiện hành là USD.
- Cả hai factory trả cùng object Currency cho cùng code.
- `getCurrencyCode()` trả mã chữ; `getNumericCode()` trả số nguyên; `getNumericCodeAsString()` trả chuỗi ba ký tự.
- `toString()` là code `USD`; **không thay thế `getDisplayName(locale)`** trong một UI đa ngôn ngữ.

**Không suy rằng `getInstance(Locale)` phải luôn trả một currency**: một số vùng lãnh thổ không có đơn vị tiền tệ hoặc dữ liệu runtime có thể thay đổi theo thời gian.

## 4. ISO 4217 numeric code: số 36 không phải chuỗi "036"

Đây là lỗi quan trọng nhất khi dùng mã số tiền tệ.

ISO 4217 có **numeric currency code ba chữ số**. Một số mã bắt đầu bằng `0`. Nhưng `int` không ghi nhớ độ rộng ban đầu: giá trị `036` nếu diễn giải theo “số nguyên” về mặt ý nghĩa chỉ còn `36`.

Ví dụ thường dùng:

| Mã chữ | Mã số ISO 4217 dạng text | `getNumericCode()` | `getNumericCodeAsString()` |
| --- | --- | ---: | --- |
| `USD` | `840` | `840` | `"840"` |
| `VND` | `704` | `704` | `"704"` |
| `AUD` | `036` | `36` | `"036"` |
| `JPY` | `392` | `392` | `"392"` |
| `EUR` | `978` | `978` | `"978"` |
| `KWD` | `414` | `414` | `"414"` |
| `XXX` | `999` | `999` | `"999"` |

**Bảng là các mã cụ thể được JDK thử nghiệm hỗ trợ; mọi danh mục currency và country assignment phải được cập nhật theo ISO/JDK hiện hành.** Không hard-code toàn bộ bảng tiền tệ thế giới rồi dùng mãi mãi.

### 4.1. Khi nào lấy int và khi nào lấy String?

- Nếu một API nội bộ thật sự định nghĩa numeric currency ID dưới dạng **number** và không yêu cầu giữ ký tự số 0 đầu, có thể dùng `getNumericCode()`.
- Nếu giao thức trao đổi hoặc cơ sở dữ liệu yêu cầu **đúng ba chữ số ISO**, dùng `getNumericCodeAsString()`.
- Nếu đang dùng Java 7/8 cũ trong môi trường phải hỗ trợ legacy, có thể zero-pad với `String.format(Locale.ROOT, "%03d", getNumericCode())`; nhưng bài tập trung Java 17+, nên **không cần fallback lỗi thời**.
- Không tính toán `036 + 1` như “mã tiền tệ tiếp theo”: numeric code chỉ là **ID**, không chứa thứ tự nghiệp vụ.
- Không coi numeric code là country ISO 3166 numeric code; dù dữ liệu có liên quan lịch sử, **hai bộ định danh không phải một loại**.

### 4.2. Chương trình 2 — giữ số 0 đầu

Tạo `CurrencyLeadingZeroDemo.java`:

```java
import java.util.Currency;
import java.util.Locale;
public class CurrencyLeadingZeroDemo {
  public static void main(String[] args) {
    Currency aud = Currency.getInstance("AUD");
    Currency usd = Currency.getInstance("USD");
    Currency vnd = Currency.getInstance("VND");
    System.out.println("AUD-int=" + aud.getNumericCode());
    System.out.println("AUD-string=" + aud.getNumericCodeAsString());
    System.out.println("USD-string=" + usd.getNumericCodeAsString());
    System.out.println("VND-string=" + vnd.getNumericCodeAsString());
    System.out.println("zero-pad-match=" +
        aud.getNumericCodeAsString().equals(String.format(Locale.ROOT, "%03d", aud.getNumericCode())));
    System.out.println("all-three-digits=" +
        (aud.getNumericCodeAsString().matches("[0-9]{3}") &&
         usd.getNumericCodeAsString().matches("[0-9]{3}")));
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CurrencyLeadingZeroDemo.java
java CurrencyLeadingZeroDemo
```

**stdout đã kiểm thử:**

```text
AUD-int=36
AUD-string=036
USD-string=840
VND-string=704
zero-pad-match=true
all-three-digits=true
```

**Vì sao cách này đáng học?** Nếu một hệ thống gửi `"036"` mà hệ thống nhận parse thành int rồi serialize lại thành `"36"`, định danh không còn đúng schema ISO dạng ba chữ số. Trong XML/JSON, hãy giữ numeric code dạng **string** khi giao thức yêu cầu fixed width; không lẫn chuỗi ba chữ số với giá trị monetary amount.

### 4.3. Tránh phụ thuộc default locale khi format numeric ID

`String.format("%03d", n)` có thể chịu tác động locale/default formatting. Nếu phải định dạng thủ công, truyền `Locale.ROOT`. Nhưng với Java 17+ ưu tiên `getNumericCodeAsString()`: đơn giản, đúng contract, không phụ thuộc default display locale của hệ thống.

## 5. getDisplayName(Locale): tên phù hợp với ngôn ngữ UI

`Currency.getDisplayName(Locale locale)` trả tên tiền tệ **phù hợp để hiển thị** bằng locale được yêu cầu. Ví dụ cùng USD có thể được hiển thị khác nhau cho tiếng Anh và tiếng Việt.

**Điều mà API bảo đảm:** tên hiển thị thích hợp theo locale nếu dữ liệu có; nếu không tìm thấy tên thích hợp, **trả về mã chữ ISO 4217**. API không hứa một chuỗi văn bản cụ thể sẽ luôn như nhau trên mọi JDK, locale provider hay mọi năm.

### 5.1. Chương trình 3 — xem tên USD bằng English và tiếng Việt

Tạo `CurrencyDisplayNamesDemo.java`:

```java
import java.util.Currency;
import java.util.Locale;
public class CurrencyDisplayNamesDemo {
  public static void main(String[] args) {
    Currency usd = Currency.getInstance("USD");
    Locale english = Locale.US;
    Locale vietnamese = Locale.forLanguageTag("vi-VN");
    String en = usd.getDisplayName(english);
    String vi = usd.getDisplayName(vietnamese);
    System.out.println("english-name=" + en);
    System.out.println("vietnamese-name=" + vi);
    System.out.println("both-nonempty=" + (!en.isBlank() && !vi.isBlank()));
    System.out.println("identifier-unchanged=" + usd.getCurrencyCode().equals("USD"));
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CurrencyDisplayNamesDemo.java
java CurrencyDisplayNamesDemo
```

**stdout đã kiểm thử trên JDK có dữ liệu CLDR tiếng Việt:**

```text
english-name=US Dollar
vietnamese-name=Đô la Mỹ
both-nonempty=true
identifier-unchanged=true
```

**Quan trọng:** hai dòng tên hiển thị là **đầu ra từ bộ dữ liệu locale của JDK trong lần chạy thử**, không phải chuỗi cứng để assert trên mọi phiên bản. Nếu JDK/CLDR thay đổi thuật ngữ, chính tả, dấu hoặc format bản địa hóa, bản dịch có thể khác mà API vẫn đúng. Tránh unit test `assertEquals("Đô la Mỹ", usd.getDisplayName(vi))` trừ khi đang kiểm soát cố định locale data version và đó chính là đối tượng kiểm thử.

### 5.2. Không suy tiền tệ từ ngôn ngữ hiển thị

`Locale.forLanguageTag("vi-VN")` có thể là locale hiển thị của một người dùng Việt Nam, nhưng người đó vẫn có thể trả USD. Vì vậy:

```java
Currency chargeCurrency = Currency.getInstance("USD");
String label = chargeCurrency.getDisplayName(Locale.forLanguageTag("vi-VN"));
```

đúng khi muốn **hiển thị USD bằng tiếng Việt**. Thay thành `Currency.getInstance(Locale.forLanguageTag("vi-VN"))` lại chọn **VND theo vùng** — đó là một bước **thay đổi đơn vị tiền tệ**, không phải dịch tên.

### 5.3. Tên hiển thị không phải định danh bền vững

Không lưu “US Dollar” hoặc “Đô la Mỹ” làm key trong database/bộ định tuyến payment. Các chuỗi có thể thay đổi do:

- Ngôn ngữ, vùng, variant hoặc Unicode extensions của locale.
- Bản dịch từ CLDR, bản vá dữ liệu locale/JDK.
- Lựa chọn locale provider ở runtime.
- Fallback khi thiếu bản dịch.
- Yêu cầu copywriting/UI của sản phẩm.

Lưu `currency.getCurrencyCode()`, và tạo display label ở UI/server presentation layer theo ngôn ngữ người dùng.

## 6. getDisplayName() không tham số và default DISPLAY locale

Overload không tham số:

```java
currency.getDisplayName()
```

theo JavaDoc tương đương:

```java
currency.getDisplayName(Locale.getDefault(Locale.Category.DISPLAY))
```

Tương tự, `getSymbol()` cũng dùng **default DISPLAY locale**, không nhất thiết trùng `Locale.Category.FORMAT`. Hai categories có mục đích khác nhau:

- `DISPLAY`: tên gọi để hiển thị trong giao diện.
- `FORMAT`: quy ước định dạng số, ngày, tiền cho người dùng.

### 6.1. Chương trình 4 — hai default locale categories độc lập

Tạo `CurrencyDisplayDefaultDemo.java`:

```java
import java.util.Currency;
import java.util.Locale;
public class CurrencyDisplayDefaultDemo {
  public static void main(String[] args) {
    Locale originalDisplay = Locale.getDefault(Locale.Category.DISPLAY);
    Locale originalFormat = Locale.getDefault(Locale.Category.FORMAT);
    try {
      Locale.setDefault(Locale.Category.DISPLAY, Locale.US);
      Locale.setDefault(Locale.Category.FORMAT, Locale.FRANCE);
      Currency usd = Currency.getInstance("USD");
      System.out.println("display-uses-display-category=" +
          usd.getDisplayName().equals(usd.getDisplayName(Locale.US)));
      System.out.println("symbol-uses-display-category=" +
          usd.getSymbol().equals(usd.getSymbol(Locale.US)));
      System.out.println("format-category-remains-france=" +
          Locale.getDefault(Locale.Category.FORMAT).equals(Locale.FRANCE));
      System.out.println("currency-code-stable=" + usd.getCurrencyCode().equals("USD"));
    } finally {
      Locale.setDefault(Locale.Category.DISPLAY, originalDisplay);
      Locale.setDefault(Locale.Category.FORMAT, originalFormat);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CurrencyDisplayDefaultDemo.java
java CurrencyDisplayDefaultDemo
```

**stdout đã kiểm thử:**

```text
display-uses-display-category=true
symbol-uses-display-category=true
format-category-remains-france=true
currency-code-stable=true
```

**Cảnh báo production:** `Locale.setDefault(...)` thay đổi global JVM default, có thể ảnh hưởng threads/requests khác. Demo dùng một process thử nghiệm và **restore bằng finally**. Trong ứng dụng đa người dùng, hãy truyền `Locale` **tường minh theo từng request** vào `getDisplayName(locale)` và formatter thay vì sửa global default locale trong request handler.

### 6.2. Locale.ROOT dùng để làm gì?

`Locale.ROOT` hữu ích cho phép xử lý chuỗi/định dạng máy không gắn ngôn ngữ của người dùng (ví dụ zero-pad ID). Nó **không** có nghĩa một display name tiếng Anh tiêu chuẩn bất biến. Để hiển thị cho người dùng English-US, hãy truyền `Locale.US`; đối với Việt Nam, truyền `Locale.forLanguageTag("vi-VN")`.

## 7. Locale vùng quốc gia và Unicode extensions: cu, rg

`Currency.getInstance(Locale)` mặc định chọn đơn vị theo **vùng/quốc gia** của locale. Nhưng Unicode locale extensions có thể ảnh hưởng kết quả:

- `u-cu-usd`: currency override, yêu cầu chọn USD.
- `u-rg-uszzzz`: region override, ví dụ vùng effective US khi dữ liệu hỗ trợ.
- Nếu có **cả `cu` và `rg`**, currency từ `cu` được ưu tiên khi xác định Currency.

**Đừng nhầm:** `getDisplayName(locale)` dùng locale để lấy tên hiển thị; còn `Currency.getInstance(locale)` dùng locale để xác định Currency. Hai method giải quyết hai câu hỏi khác nhau.

### 7.1. Chương trình 5 — Unicode cu thắng rg

Tạo `CurrencyUnicodeExtensionDemo.java`:

```java
import java.util.Currency;
import java.util.Locale;
public class CurrencyUnicodeExtensionDemo {
  public static void main(String[] args) {
    Locale vietnam = Locale.forLanguageTag("vi-VN");
    Locale chooseUsd = Locale.forLanguageTag("vi-VN-u-cu-usd");
    Locale regionUs = Locale.forLanguageTag("vi-VN-u-rg-uszzzz");
    Locale both = Locale.forLanguageTag("vi-VN-u-cu-jpy-rg-uszzzz");
    System.out.println("country-currency=" + Currency.getInstance(vietnam).getCurrencyCode());
    System.out.println("cu-override=" + Currency.getInstance(chooseUsd).getCurrencyCode());
    System.out.println("rg-override=" + Currency.getInstance(regionUs).getCurrencyCode());
    System.out.println("cu-wins-over-rg=" + Currency.getInstance(both).getCurrencyCode());
    System.out.println("selected-name-localized=" +
        !Currency.getInstance(both).getDisplayName(vietnam).isBlank());
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CurrencyUnicodeExtensionDemo.java
java CurrencyUnicodeExtensionDemo
```

**stdout đã kiểm thử:**

```text
country-currency=VND
cu-override=USD
rg-override=USD
cu-wins-over-rg=JPY
selected-name-localized=true
```

**Lý giải từng trường hợp:**

1. `vi-VN` → theo vùng VN, mặc định VND.
2. `vi-VN-u-cu-usd` → explicit currency USD, dù language/country vẫn là vi/VN.
3. `vi-VN-u-rg-uszzzz` → effective region override US, mặc định USD.
4. `vi-VN-u-cu-jpy-rg-uszzzz` → cả hai có mặt, `cu=jpy` được ưu tiên, nên JPY.

Trong nghiệp vụ, một request đã chỉ định đơn vị `USD` qua field riêng thì **không nên suy lại** từ locale và ghi đè nó. Unicode extension có thể là một lựa chọn presentation hoặc currency preference, nhưng việc **thu phí đồng tiền nào** phải theo business contract.

### 7.2. BCP 47 và input không tin cậy

`Locale.forLanguageTag(tag)` parse language tag, nhưng chỉ parse được không nghĩa tag có đủ country/currency data hay được ứng dụng chấp nhận. Validate supported locale list/policy; không lấy user locale string làm bằng chứng authorization hoặc jurisdiction.

Với locale không có country hợp lệ, `Currency.getInstance(locale)` có thể ném `IllegalArgumentException`; với territory không có currency, có thể trả `null`. Hai trường hợp này **khác nhau**.

## 8. Nhận biết đầu vào sai: NullPointerException và IllegalArgumentException

`Currency.getInstance(String currencyCode)` nhận mã chữ được JDK hỗ trợ. Các input sai thường gặp:

- `"usd"`: sai format/case khi contract yêu cầu ISO alphabetic code.
- `"840"`: đây là **numeric code**, không phải tham số alphabetic của `getInstance(String)`.
- `"US"`: không đủ ba chữ cái.
- `"ZZZ"`: không phải code được JDK thử nghiệm hỗ trợ.
- `null`: ném `NullPointerException`.
- `Currency.getInstance((Locale)null)`: ném `NullPointerException`.
- `usd.getDisplayName(null)`: ném `NullPointerException`.
- Locale với country `ZZ` không được hỗ trợ: `IllegalArgumentException` khi tìm Currency.

**Không gọi `Currency.getInstance("840")` để “giải ngược” numeric code.** Factory đó nhận **mã chữ**, không phải chuỗi numeric code. Nếu protocol đầu vào là numeric code, ứng dụng cần mapping đã được quản lý, có version và chính sách xử lý trường hợp không nhận diện được/không còn hiệu lực.

### 8.1. Chương trình 6 — kiểm thử lỗi rõ từng nhóm

Tạo `CurrencyInputErrorsDemo.java`:

```java
import java.util.Currency;
import java.util.Locale;
public class CurrencyInputErrorsDemo {
  public static void main(String[] args) {
    int invalidCodes = 0;
    for (String code : new String[]{"usd", "840", "US", "ZZZ"}) {
      try { Currency.getInstance(code); }
      catch (IllegalArgumentException ex) { invalidCodes++; }
    }
    boolean nullCode = false, nullLocale = false, nullDisplay = false, invalidCountry = false;
    try { Currency.getInstance((String) null); }
    catch (NullPointerException ex) { nullCode = true; }
    try { Currency.getInstance((Locale) null); }
    catch (NullPointerException ex) { nullLocale = true; }
    try { Currency.getInstance("USD").getDisplayName(null); }
    catch (NullPointerException ex) { nullDisplay = true; }
    try { Currency.getInstance(Locale.forLanguageTag("en-ZZ")); }
    catch (IllegalArgumentException ex) { invalidCountry = true; }
    System.out.println("invalid-codes=" + invalidCodes);
    System.out.println("null-code-rejected=" + nullCode);
    System.out.println("null-locale-rejected=" + nullLocale);
    System.out.println("null-display-rejected=" + nullDisplay);
    System.out.println("unsupported-country-rejected=" + invalidCountry);
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CurrencyInputErrorsDemo.java
java CurrencyInputErrorsDemo
```

**stdout đã kiểm thử:**

```text
invalid-codes=4
null-code-rejected=true
null-locale-rejected=true
null-display-rejected=true
unsupported-country-rejected=true
```

### 8.2. Catch đúng ngoại lệ, không biến mọi lỗi thành USD

Một anti-pattern:

```java
try {
    return Currency.getInstance(rawCode);
} catch (Exception ignored) {
    return Currency.getInstance("USD");
}
```

Đây là **snippet sai** nếu `rawCode` được người dùng dùng để chỉ định đồng tiền giao dịch: invalid input bị biến âm thầm thành USD, có thể tạo thanh toán bằng sai đơn vị. Hãy trả validation error và yêu cầu sửa input; chỉ áp dụng default currency nếu business contract rõ ràng cho phép một default.

### 8.3. Thông báo lỗi không cần tiết lộ nội bộ

Một API có thể trả `{"error":"UNSUPPORTED_CURRENCY_CODE"}` hoặc thông báo tương đương. Không cần lộ full classpath, JVM internal locale data file, stack trace hay cấu hình environment trong response công khai. Logs có thể giữ error classification nhưng cần giới hạn input length và tránh payload logging nhạy cảm.

## 9. Numeric code không liên quan tới số chữ số thập phân

`Currency.getDefaultFractionDigits()` trả **ISO 4217 minor units mặc định**; khác hoàn toàn `getNumericCode()`.

Ví dụ:

| Currency | Numeric code | Default fraction digits | Ý nghĩa |
| --- | ---: | ---: | --- |
| USD | 840 | 2 | Thông thường 1 USD = 100 đơn vị cent |
| JPY | 392 | 0 | Đồng yên thông thường không có phần lẻ trong minor-unit convention |
| KWD | 414 | 3 | Ba chữ số phần lẻ theo ISO minor unit |
| XXX | 999 | -1 | Pseudo code / không có minor unit xác định |

Các values này minh họa theo dữ liệu đã kiểm thử. Không dùng minor units để **suy tỷ giá**, không coi mọi settlement service đều cho phép đúng mức precision mặc định, và lưu ý quy tắc tiền mặt/rounding của một số thị trường có thể khác minor unit của ISO.

### 9.1. Chương trình 7 — fraction digits và pseudo-currency XXX

Tạo `CurrencyFractionDemo.java`:

```java
import java.util.Currency;
public class CurrencyFractionDemo {
  public static void main(String[] args) {
    Currency usd = Currency.getInstance("USD");
    Currency jpy = Currency.getInstance("JPY");
    Currency kwd = Currency.getInstance("KWD");
    Currency none = Currency.getInstance("XXX");
    System.out.println("USD-digits=" + usd.getDefaultFractionDigits());
    System.out.println("JPY-digits=" + jpy.getDefaultFractionDigits());
    System.out.println("KWD-digits=" + kwd.getDefaultFractionDigits());
    System.out.println("XXX-digits=" + none.getDefaultFractionDigits());
    System.out.println("XXX-numeric=" + none.getNumericCodeAsString());
    System.out.println("numeric-is-not-fraction-digits=" +
        (usd.getNumericCode() != usd.getDefaultFractionDigits()));
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CurrencyFractionDemo.java
java CurrencyFractionDemo
```

**stdout đã kiểm thử:**

```text
USD-digits=2
JPY-digits=0
KWD-digits=3
XXX-digits=-1
XXX-numeric=999
numeric-is-not-fraction-digits=true
```

**Giải thích:** `XXX` là special/pseudo currency code ISO khi không có một đơn vị tiền tệ cụ thể. Việc runtime biết `XXX` không làm nó phù hợp cho giao dịch; nếu business chỉ cho phép USD/EUR/VND, phải có **allowlist riêng**. Nếu `getDefaultFractionDigits()==-1`, không tự `setScale(-1)` rồi coi đây là quy tắc tiền tệ hợp lệ.

### 9.2. Vì sao không khẳng định mọi currency đều có hai chữ số?

Nhiều ví dụ UI in `$12.34` khiến người mới học tưởng mọi tiền tệ có 2 phần lẻ. Điều này sai: `JPY` có default 0, `KWD` có 3, pseudo-currencies có thể trả -1. Ứng dụng còn có domain-specific precision/rounding/settlement constraints riêng.

## 10. getSymbol(Locale) khác getDisplayName(Locale)

Một Currency có thể có:

- Mã chữ: `USD`.
- Mã số: `840`.
- Tên: `US Dollar`/`Đô la Mỹ` tùy locale.
- Ký hiệu: ví dụ `$`/`US$` tùy locale và cách ký hiệu currency được localize.

`currency.getSymbol(locale)` cho **ký hiệu phù hợp** với locale; JavaDoc nói nếu không xác định được ký hiệu thì **fallback về mã ISO 4217**. `currency.getDisplayName(locale)` cũng fallback code nếu không có tên hiển thị thích hợp. Nhưng hai phương thức phục vụ nhu cầu UI khác nhau.

**Không dùng ký hiệu làm định danh:** `$` có thể được dùng cho USD, CAD, AUD và nhiều currency khác trong các ngữ cảnh. Khi in lịch sử giao dịch hoặc hợp đồng, nên hiển thị cả mã `USD` khi cần tránh mơ hồ.

### 10.1. Đừng giả định một tên tiếng Anh cố định

Ngay trong tiếng Anh, cách đặt tên có thể khác theo locale, kiểu tiếng Anh địa phương, nguồn dữ liệu CLDR, thay đổi quy ước và JDK version. Với tiếng Việt, Unicode accents, capitalization, spacing và cách gọi có thể thay đổi. **Không viết bài test so chính tả của bản dịch khi mục tiêu thực sự là xác minh mã tiền tệ và pipeline localization.**

### 10.2. Unicode và font

Ký hiệu `₫`, `€`, `¥` cần font có glyph phù hợp. Một app có thể thấy ô vuông/tofu nếu font không hỗ trợ. Đây là vấn đề **font rendering**, không phải Currency.getCurrencyCode. Tên bản địa hóa có thể chứa nhiều code points Unicode, combining marks hoặc script không Latin; đừng cắt label theo độ dài byte UTF-8 hay giả định `String.length()` bằng số ký tự người dùng nhìn thấy.

## 11. NumberFormat.getCurrencyInstance và Currency.setCurrency

`NumberFormat.getCurrencyInstance(locale)` tạo formatter tiền tệ theo quy ước **FORMAT locale** được chỉ định. Một formatter mang currency setting, grouping, decimal separator, prefix/suffix, fraction digits... Tên hiển thị là một hoạt động **khác**: `currency.getDisplayName(locale)`.

### 11.1. Bẫy: setCurrency không nhất thiết cập nhật fraction digits

Một đối tượng `NumberFormat` tạo từ `Locale.US` có thể đang dùng min/max fraction digits 2. Nếu bạn `setCurrency(JPY)`, JavaDoc của `DecimalFormat.setCurrency` nói nó **không tự cập nhật minimum/maximum fraction digits**. Nếu muốn hiển thị JPY không có số thập phân, phải cấu hình fraction digit policy rõ ràng.

### 11.2. Chương trình 8 — tách currency unit và formatter precision

Tạo `CurrencyFormatDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;
public class CurrencyFormatDemo {
  public static void main(String[] args) {
    NumberFormat formatter = NumberFormat.getCurrencyInstance(Locale.US);
    Currency jpy = Currency.getInstance("JPY");
    int fractionBefore = formatter.getMaximumFractionDigits();
    formatter.setCurrency(jpy);
    int afterCurrencyChange = formatter.getMaximumFractionDigits();
    formatter.setMinimumFractionDigits(0);
    formatter.setMaximumFractionDigits(0);
    formatter.setRoundingMode(RoundingMode.HALF_EVEN);
    String rendered = formatter.format(new BigDecimal("1234"));
    System.out.println("usd-locale-fractions=" + fractionBefore);
    System.out.println("setCurrency-keeps-max-fractions=" + (fractionBefore == afterCurrencyChange));
    System.out.println("configured-jpy-digits=" + (formatter.getMaximumFractionDigits() == 0));
    System.out.println("formatted-nonempty=" + !rendered.isBlank());
    System.out.println("currency-code=" + formatter.getCurrency().getCurrencyCode());
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CurrencyFormatDemo.java
java CurrencyFormatDemo
```

**stdout đã kiểm thử với default locale data của JDK:**

```text
usd-locale-fractions=2
setCurrency-keeps-max-fractions=true
configured-jpy-digits=true
formatted-nonempty=true
currency-code=JPY
```

**Lưu ý:** số 2 trong dòng đầu là default của currency format `Locale.US` ở JDK đã thử nghiệm. Đừng assert mọi locale/JDK luôn có hai fraction digits. Demo không in nguyên văn string `rendered` vì separator, ký hiệu, vị trí currency và nonbreaking spaces có thể tùy dữ liệu formatter.

### 11.3. Không dùng chung một NumberFormat mutable giữa threads

`NumberFormat`/`DecimalFormat` thường có mutable state và **không mặc định thread-safe**. Đừng cache một `NumberFormat` toàn cục rồi gọi `setCurrency`/`format` đồng thời cho nhiều requests. Có thể tạo formatter theo request, theo thread có lifecycle đúng, hoặc dùng strategy immutable phù hợp.

**`Currency` là đối tượng mã tiền tệ khác `NumberFormat`**, tránh nhầm tính ổn định của Currency với tính đồng bộ của formatter.

## 12. BigDecimal cho số tiền: Currency không lưu amount

Đối với giá trị tài chính, nên dùng `BigDecimal` được tạo từ **chuỗi decimal**, hoặc một money library phù hợp. Binary floating-point kiểu `double` có thể không biểu diễn chính xác số thập phân thường gặp như `0.1`.

Ví dụ:

```java
BigDecimal amount = new BigDecimal("0.10").add(new BigDecimal("0.20"));
```

cho `0.30` về giá trị decimal. Nhưng không tự động cho phép cộng USD với JPY: **currency unit phải được kiểm tra** ở domain layer. Cần chính sách rounding/scale gắn với hợp đồng thanh toán.

### 12.1. Chương trình 9 — scale theo minor units và fail fast

Tạo `CurrencyBigDecimalDemo.java`:

```java
import java.math.*;
import java.util.Currency;
public class CurrencyBigDecimalDemo {
  static BigDecimal scaled(String raw, Currency currency) {
    int digits = currency.getDefaultFractionDigits();
    if (digits < 0) throw new IllegalArgumentException("undefined currency minor unit");
    return new BigDecimal(raw).setScale(digits, RoundingMode.UNNECESSARY);
  }
  public static void main(String[] args) {
    Currency usd = Currency.getInstance("USD");
    BigDecimal sum = scaled("0.10", usd).add(scaled("0.20", usd));
    boolean excessRejected = false, pseudoRejected = false;
    try { scaled("12.345", usd); } catch (ArithmeticException ex) { excessRejected = true; }
    try { scaled("1", Currency.getInstance("XXX")); }
    catch (IllegalArgumentException ex) { pseudoRejected = true; }
    System.out.println("exact-sum=" + sum.toPlainString());
    System.out.println("excess-fraction-rejected=" + excessRejected);
    System.out.println("pseudo-minor-unit-rejected=" + pseudoRejected);
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CurrencyBigDecimalDemo.java
java CurrencyBigDecimalDemo
```

**stdout đã kiểm thử:**

```text
exact-sum=0.30
excess-fraction-rejected=true
pseudo-minor-unit-rejected=true
```

**Giải thích:**

- `BigDecimal("0.10")` và `BigDecimal("0.20")` cộng chính xác ra `0.30`.
- `RoundingMode.UNNECESSARY` khiến đầu vào có phần thập phân vượt precision và làm mất giá trị bị reject, không tự cắt.
- `XXX` có `-1` fraction digits, nên helper báo lỗi thay vì gọi `setScale(-1)` một cách mù quáng.

Đây là **ví dụ policy nghiêm ngặt**: có hệ thống cho phép internal calculations có precision cao hơn ISO minor units rồi chỉ làm tròn lúc settlement. Điều đó hợp lệ nếu domain đã định nghĩa rõ. Không lấy `getDefaultFractionDigits` làm luật bất biến cho mọi ngành hoặc mọi kênh thanh toán.

### 12.2. Currency không hỗ trợ FX conversion

`BigDecimal("100.00")` USD và `BigDecimal("100.00")` EUR không cùng giá trị kinh tế. Không tự chuyển bằng phép cộng/trừ amount khi units khác nhau. FX cần rate, nguồn cung cấp, ngày/giờ định giá, spread, fees, precision và reconciliation policy.

## 13. Validate mã tiền tệ theo hai tầng

Một chuỗi khớp regex `[A-Z]{3}` **không bảo đảm là ISO code được JDK biết**. Một code được JDK biết **không bảo đảm business chấp nhận thanh toán** bằng code đó. Tách rõ:

1. **Syntax:** đúng ba ký tự Latin uppercase.
2. **Recognition:** `Currency.getInstance(code)` chấp nhận.
3. **Business allowlist:** có được dùng trong nghiệp vụ hiện tại không?
4. **Scope/availability:** khu vực, PSP, method, ngày hiệu lực, version, user account... nếu ứng dụng cần.

Không dùng `Currency.getAvailableCurrencies()` như danh sách auto-allow-all, vì có thể chứa obsolete/pseudo codes.

### 13.1. Chương trình 10 — allowlist bảo vệ nghiệp vụ

Tạo `CurrencyCodeGuardDemo.java`:

```java
import java.util.*;
public class CurrencyCodeGuardDemo {
  static Currency accepted(String raw) {
    if (raw == null || !raw.matches("[A-Z]{3}"))
      throw new IllegalArgumentException("expected 3 uppercase letters");
    Currency currency = Currency.getInstance(raw);
    if (!Set.of("USD", "EUR", "VND").contains(currency.getCurrencyCode()))
      throw new IllegalArgumentException("currency not accepted by business");
    return currency;
  }
  public static void main(String[] args) {
    boolean acceptedUsd = accepted("USD").getNumericCodeAsString().equals("840");
    int rejected = 0;
    for (String raw : new String[]{"usd", "840", "ZZZ", "XXX", "US", null}) {
      try { accepted(raw); } catch (IllegalArgumentException ex) { rejected++; }
    }
    System.out.println("accepted-usd=" + acceptedUsd);
    System.out.println("rejected-inputs=" + rejected);
    System.out.println("supported-vnd=" + accepted("VND").getCurrencyCode().equals("VND"));
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CurrencyCodeGuardDemo.java
java CurrencyCodeGuardDemo
```

**stdout đã kiểm thử:**

```text
accepted-usd=true
rejected-inputs=6
supported-vnd=true
```

**Vì sao reject `XXX` dù Currency.getInstance nhận?** `XXX` đại diện tình trạng không có đồng tiền cụ thể; nó không phù hợp làm đơn vị charge trong policy minh họa. Một công ty dùng các đồng tiền khác có thể xây allowlist khác; không copy danh sách `USD/EUR/VND` này thành “danh sách ISO hợp lệ toàn cầu”.

### 13.2. Có nên uppercase input "usd" tự động?

Tùy giao thức. Nếu API tuyên bố nhận case-insensitive, có thể chuẩn hóa `raw.trim().toUpperCase(Locale.ROOT)` **trước validation**, nhưng phải định nghĩa rõ xử lý whitespace, Unicode lookalikes và security policy. Nếu API đòi canonical ISO code, reject input không canonical giúp tránh mơ hồ.

**Không dùng `toUpperCase()` thiếu `Locale.ROOT`** trong logic định danh có thể phụ thuộc quy tắc ngôn ngữ của máy/chủ tài khoản.

## 14. getAvailableCurrencies: danh mục runtime không đồng nghĩa danh mục hoạt động

`Currency.getAvailableCurrencies()` trả một `Set<Currency>` các currencies mà JDK biết. Theo JavaDoc, tập này **có thể chứa những mã ISO 4217 đã lỗi thời**. Có thể sửa set được trả về mà **không thay đổi tập currencies bên trong runtime**.

Điều này quan trọng khi bạn muốn tạo dropdown tiền tệ:

- **Đừng** hiển thị toàn bộ set mà không lọc.
- **Đừng** giả định thứ tự iteration cố định.
- **Đừng** dùng current count như hằng số trong unit tests.
- **Đừng** biến “runtime biết code” thành “giao dịch được bằng code”.
- **Đừng** tự viết hệ thống thanh toán chỉ dựa trên numeric code và JDK data.
- Nếu cần danh mục thực sự active, dùng nguồn dữ liệu và version quy định rõ bởi nghiệp vụ/PSP/ISO.

### 14.1. Chương trình 11 — set copy không sửa registry

Tạo `CurrencyAvailableSetDemo.java`:

```java
import java.util.*;
public class CurrencyAvailableSetDemo {
  public static void main(String[] args) {
    Set<Currency> localCopy = Currency.getAvailableCurrencies();
    boolean usdPresent = localCopy.contains(Currency.getInstance("USD"));
    boolean xxxPresent = localCopy.contains(Currency.getInstance("XXX"));
    localCopy.clear();
    Set<Currency> fresh = Currency.getAvailableCurrencies();
    System.out.println("USD-in-available=" + usdPresent);
    System.out.println("XXX-in-available=" + xxxPresent);
    System.out.println("copy-cleared=" + localCopy.isEmpty());
    System.out.println("fresh-still-has-USD=" + fresh.contains(Currency.getInstance("USD")));
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CurrencyAvailableSetDemo.java
java CurrencyAvailableSetDemo
```

**stdout đã kiểm thử:**

```text
USD-in-available=true
XXX-in-available=true
copy-cleared=true
fresh-still-has-USD=true
```

**Lưu ý:** thao tác `clear()` chỉ thực hiện trên **bản set được trả về** để minh họa API; trong ứng dụng thực thường nên giữ bản copy immutable/sắp xếp khi xây UI. Không có lý do nghiệp vụ để gọi `clear()` trước mỗi request.

### 14.2. Không xây reverse map numeric→alphabetic một cách ngây thơ

Mã số ISO 4217 là identifier, nhưng mapping cần data version/time context, có thể bao gồm pseudo/obsolete codes. Một map `Map<Integer,Currency>` dựng tự động từ toàn `getAvailableCurrencies` có thể bỏ qua collision, giá trị lịch sử hoặc domain unsupported. Nếu protocol của bạn nhận numeric code:

- Xác định chuẩn/version/nguồn dữ liệu mapping được chấp nhận.
- Lưu numeric code dạng ba ký tự nếu schema yêu cầu.
- Xử lý mã không nhận diện/obsolete/pseudo theo policy.
- Xác định timezone/effective date nếu liên quan đổi currency theo quốc gia.
- Không dùng numeric code làm phép toán/“mã kế tiếp”.

## 15. Locale quốc gia chọn currency; locale ngôn ngữ chọn cách hiển thị

Một người có thể sống ở VN nhưng sử dụng giao diện English; hoặc sống ở US nhưng chọn Vietnamese UI. `Currency.getInstance(Locale)` dựa chủ yếu vào **territory**, không phải dịch tên theo ngôn ngữ. `getDisplayName(Locale)` lại dùng locale làm **đích bản địa hóa**.

### 15.1. Chương trình 12 — cùng VN, hai languages

Tạo `CurrencyRegionAndLanguageDemo.java`:

```java
import java.util.Currency;
import java.util.Locale;
public class CurrencyRegionAndLanguageDemo {
  public static void main(String[] args) {
    Locale vietEnglish = Locale.forLanguageTag("en-VN");
    Locale vietVietnamese = Locale.forLanguageTag("vi-VN");
    Currency a = Currency.getInstance(vietEnglish);
    Currency b = Currency.getInstance(vietVietnamese);
    Locale antarctica = Locale.forLanguageTag("en-AQ");
    System.out.println("same-region-ignores-language=" + (a == b));
    System.out.println("same-VND-code=" + a.getCurrencyCode().equals("VND"));
    System.out.println("no-currency-AQ=" + (Currency.getInstance(antarctica) == null));
    System.out.println("locale-display-uses-specified-language=" +
        !a.getDisplayName(vietVietnamese).isBlank());
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CurrencyRegionAndLanguageDemo.java
java CurrencyRegionAndLanguageDemo
```

**stdout đã kiểm thử:**

```text
same-region-ignores-language=true
same-VND-code=true
no-currency-AQ=true
locale-display-uses-specified-language=true
```

**Không hiểu dòng `no-currency-AQ` là mọi vùng địa lý đều có một currency code:** JavaDoc nêu các territories không có currency, ví dụ Antarctica, có thể trả `null`. Nếu code trực tiếp gọi `Currency.getInstance(locale).getCurrencyCode()` mà không kiểm null, sẽ gặp NPE. Trong production, quản lý cả cases thiếu country, unsupported country và no-currency territory.

### 15.2. Country assignment thay đổi theo thời gian

Quốc gia có thể đổi đơn vị tiền tệ. JavaDoc của `Currency.getInstance(Locale)` nói kết quả có thể thay đổi theo thời gian. Đừng dùng phương thức này để tái tạo lịch sử “đồng tiền pháp định ở quốc gia X vào ngày Y” nếu thiếu dữ liệu lịch sử/effective dates. Lưu currency code cụ thể cho **mỗi giao dịch**.

## 16. Unicode: tên hiển thị là văn bản ngôn ngữ, không phải ID

Tên như `Đô la Mỹ` gồm Unicode characters có dấu, khác với mã máy `USD`. Khi lưu/truyền UI string:

- Dùng encoding UTF-8 cho IO/JSON.
- Không giả định chuỗi toàn ASCII.
- Không phân loại một currency theo cách so display name/casefold.
- Nếu cần normalize để so text theo quy tắc UI, dùng `java.text.Normalizer` với một normalization form có chủ đích; **không biến display name thành primary key**.
- Không cắt chuỗi theo số byte hoặc UTF-16 code units mà tưởng bằng số grapheme clusters.
- Với ký hiệu/tiếng Ả Rập, tiếng Hindi, tiếng Việt, dựa vào UI layout/font/bidi đúng ngôn ngữ.
- Kiểm tra font fallback; bản dịch từ JDK/CLDR có thể đổi giữa versions.

### 16.1. Chương trình 13 — Unicode normalization không thay đổi currency identity

Tạo `CurrencyUnicodeNormalizationDemo.java`:

```java
import java.text.Normalizer;
import java.util.Currency;
import java.util.Locale;
public class CurrencyUnicodeNormalizationDemo {
  public static void main(String[] args) {
    Currency eur = Currency.getInstance("EUR");
    Locale french = Locale.FRANCE;
    String name = eur.getDisplayName(french);
    String normalized = Normalizer.normalize(name, Normalizer.Form.NFC);
    System.out.println("localized-name-present=" + !name.isBlank());
    System.out.println("normalized-is-nfc=" + Normalizer.isNormalized(normalized, Normalizer.Form.NFC));
    System.out.println("name-not-currency-identity=" + eur.getCurrencyCode().equals("EUR"));
    System.out.println("numeric-not-display-text=" + eur.getNumericCodeAsString().equals("978"));
    System.out.println("unicode-codepoints-positive=" + (normalized.codePointCount(0, normalized.length()) > 0));
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CurrencyUnicodeNormalizationDemo.java
java CurrencyUnicodeNormalizationDemo
```

**stdout đã kiểm thử:**

```text
localized-name-present=true
normalized-is-nfc=true
name-not-currency-identity=true
numeric-not-display-text=true
unicode-codepoints-positive=true
```

**Giới hạn:** chương trình chỉ chứng minh normalization form của chuỗi kết quả và rằng metadata `EUR/978` không phụ thuộc tên localized. Nó **không** chứng minh mọi ngôn ngữ đều có bản dịch cụ thể, hoặc `String.length()` bằng số chữ/grapheme mà người dùng nhìn thấy.

### 16.2. Cần tên chính xác theo thương hiệu?

Nếu một sản phẩm bắt buộc dùng copywriting riêng (ví dụ tên thân thiện rút gọn, nhãn danh mục, tên áp dụng trong hợp đồng), xây translation resources/ICU message catalog có version riêng, nhưng **vẫn lưu Currency code** làm định danh và phải giữ cách mapping rõ. `getDisplayName(locale)` phù hợp cho tên chung theo JDK locale data, không phải nguồn duy nhất cho mọi yêu cầu pháp lý/marketing.

## 17. Kết hợp amount và Currency bằng một value object

Cách trình bày dữ liệu tiền gọn và ít lỗi là tách **amount** và **currency** thành hai trường bất biến, kiểm tra cùng đơn vị trước khi cộng.

Trong Java 17 có thể dùng `record` để giữ logic đúng scope. `Currency` không tự làm arithmetic; record định nghĩa trách nhiệm nghiệp vụ rõ.

### 17.1. Chương trình 14 — Money record kiểm tra mismatch

Tạo `CurrencyMoneyRecordDemo.java`:

```java
import java.math.*;
import java.util.*;
public class CurrencyMoneyRecordDemo {
  record Money(BigDecimal amount, Currency currency) {
    Money {
      Objects.requireNonNull(amount, "amount");
      Objects.requireNonNull(currency, "currency");
    }
    Money plus(Money other) {
      Objects.requireNonNull(other, "other");
      if (!currency.equals(other.currency))
        throw new IllegalArgumentException("currency mismatch");
      return new Money(amount.add(other.amount), currency);
    }
    String machineCode() { return currency.getCurrencyCode(); }
  }
  public static void main(String[] args) {
    Money first = new Money(new BigDecimal("10.25"), Currency.getInstance("USD"));
    Money second = new Money(new BigDecimal("0.75"), Currency.getInstance("USD"));
    Money sum = first.plus(second);
    boolean mismatch = false;
    try { first.plus(new Money(BigDecimal.ONE, Currency.getInstance("JPY"))); }
    catch (IllegalArgumentException ex) { mismatch = true; }
    System.out.println("sum=" + sum.amount().toPlainString());
    System.out.println("unit=" + sum.machineCode());
    System.out.println("numeric-id=" + sum.currency().getNumericCodeAsString());
    System.out.println("mixed-currencies-rejected=" + mismatch);
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CurrencyMoneyRecordDemo.java
java CurrencyMoneyRecordDemo
```

**stdout đã kiểm thử:**

```text
sum=11.00
unit=USD
numeric-id=840
mixed-currencies-rejected=true
```

**Đọc đúng:** trong ví dụ, `Money.plus` chỉ cho cộng hai amounts cùng Currency, không tự chuyển JPY thành USD. Record không tự enforce fraction digits/negative amount/currency allowlist; các validations đó phải được đưa vào constructor/use case theo business contract.

### 17.2. JSON/API response đề xuất

Ví dụ một payload nguyên tắc:

```json
{
  "amount": "11.00",
  "currency": "USD",
  "numericCurrencyCode": "840",
  "display": {
    "locale": "vi-VN",
    "currencyName": "Đô la Mỹ"
  }
}
```

**Ví dụ dữ liệu**; nội dung `display.currencyName` là minh họa có thể thay đổi theo phiên bản data/locale. Hãy ưu tiên `"amount"` ở dạng decimal string hoặc minor-unit integer theo API contract, `"currency"` là ISO chữ; `"numericCurrencyCode"` là **chuỗi ba chữ số** để không mất 0 đầu. Không cho client ghi đè `display.currencyName` rồi coi đó là currency ID.

### 17.3. Database schema

Một thiết kế phổ biến:

```text
payment_amount_decimal  DECIMAL(...)     -- hoặc minor units theo contract
currency_code_alpha     CHAR(3)          -- ví dụ USD
currency_code_numeric   CHAR(3)          -- chỉ lưu nếu protocol thực sự yêu cầu
locale_tag              VARCHAR(...)     -- ví dụ vi-VN, dùng cho presentation
```

Đây là **schema minh họa**, không phải cú pháp SQL portable cho mọi database. Nếu chỉ cần một ID tiền tệ, lưu alphabetic code là đủ trong nhiều hệ thống; không bắt buộc lưu cả hai loại code. Display name thường được **tạo khi render**, không cần persist cùng giao dịch.

## 18. Xây bảng tên/biểu tượng theo nhiều locale

Một UI có thể cho user chọn ngôn ngữ độc lập với loại tiền. Để tạo danh sách:

1. Xác định danh mục Currency code được **business hỗ trợ**.
2. Lấy Currency từng code bằng `getInstance(String)`.
3. Với locale UI, dùng `getDisplayName(locale)` và `getSymbol(locale)`.
4. Dùng `Collator` của locale khi cần sort tên theo ngôn ngữ, không sort theo byte UTF-8.
5. Giữ ID/code trong value của option; label chỉ là presentation.
6. Tránh dùng symbols làm duy nhất option label nếu có thể mơ hồ.
7. Test display fallback/code khi thiếu dữ liệu bản dịch.
8. Cache theo locale + code + version nếu có yêu cầu ổn định, không giả định labels bất biến mãi.

### 18.1. Chương trình 15 — display matrix với ba locale

Tạo `CurrencyDisplayMatrixDemo.java`:

```java
import java.util.*;
public class CurrencyDisplayMatrixDemo {
  public static void main(String[] args) {
    List<Locale> views = List.of(Locale.US, Locale.FRANCE, Locale.forLanguageTag("vi-VN"));
    Currency usd = Currency.getInstance("USD");
    int nonEmptyLabels = 0, nonEmptySymbols = 0;
    for (Locale view : views) {
      if (!usd.getDisplayName(view).isBlank()) nonEmptyLabels++;
      if (!usd.getSymbol(view).isBlank()) nonEmptySymbols++;
    }
    System.out.println("view-locales=" + views.size());
    System.out.println("nonempty-display-names=" + nonEmptyLabels);
    System.out.println("nonempty-symbols=" + nonEmptySymbols);
    System.out.println("fixed-identifier=" + usd.getCurrencyCode());
    System.out.println("fixed-numeric-string=" + usd.getNumericCodeAsString());
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CurrencyDisplayMatrixDemo.java
java CurrencyDisplayMatrixDemo
```

**stdout đã kiểm thử:**

```text
view-locales=3
nonempty-display-names=3
nonempty-symbols=3
fixed-identifier=USD
fixed-numeric-string=840
```

**Đặc tính của unit test:** các nhãn cụ thể có thể thay đổi nhưng **ID `USD` và numeric code `840`** không phụ thuộc vào locale hiển thị. Tests kiểm tra labels/symbols tồn tại thay vì hard-code toàn bộ bản dịch.

### 18.2. Nếu cần render đúng mẫu cho giao diện

UI thực tế phải kiểm tra cùng một JDK build/CLDR provider và locale settings như production. Một golden test có thể snapshot output **kèm version** của dữ liệu; khi nâng JDK, review bản dịch và thông báo thay đổi thay vì coi đó luôn là bug.

## 19. CLDR, ISO và sự thay đổi dữ liệu theo phiên bản JDK

Ba nguồn khái niệm không được nhập nhằng:

- **ISO 4217:** tiêu chuẩn cho các mã chữ, mã số và minor units.
- **Locale/CLDR:** dữ liệu bản địa hóa tên, ký hiệu và quy ước hiển thị theo ngôn ngữ/vùng.
- **Java runtime/JDK version:** cung cấp implementation và bản dữ liệu đã đóng gói; có thể được cập nhật theo release/patch/configuration.

JavaDoc của `Currency` cho biết Java runtime có thể được điều chỉnh currency data bằng system property `java.util.currency.data` khi khởi động. Đây là một khả năng configuration đặc biệt, **không phải lời khuyên cho ứng dụng tự ý ghi đè ISO data trong runtime**. Nếu doanh nghiệp buộc dùng currency metadata khác tiêu chuẩn, cần quy trình quản trị dữ liệu/version/audit riêng.

### 19.1. Hệ quả đối với test

- Unit tests cho logic ID: assert `USD`, `getNumericCodeAsString()` ba ký tự và input validation trong tập dữ liệu được kiểm soát.
- Unit tests cho localization: kiểm nonempty, fallback và render behavior theo locale; tránh exact strings nếu dữ liệu có thể đổi.
- Integration tests: so behavior trên JDK/vendor/locale providers mà production chạy thực tế.
- Snapshot tests có thể giữ localized labels, nhưng phải ghi rõ locale data/JDK version và chuẩn review khi nâng cấp.
- Lịch sử tiền tệ: `Currency.getInstance(Locale)` chọn currency **hiện theo runtime**, không phải historical lookup theo ngày bất kỳ.

### 19.2. Đừng suy “tên dịch chính xác” từ numeric code

Không có phép toán từ `840` ra “US Dollar” mà không có bảng metadata/localization. Numeric code là identifier; tên được lookup từ data provider. Việc format `String.format("%03d",840)` chỉ ra `"840"`, **không dịch tên**. Đó là lý do API tách `getNumericCodeAsString` và `getDisplayName(locale)`.

## 20. Tiền tệ, locale và Unicode trong hệ thống phân tán

Giả sử máy chủ A chạy JDK có nhãn hiển thị Vietnamese là “Đô la Mỹ” nhưng máy chủ B đã nâng locale data và dùng một biến thể khác. Nếu database lưu **tên hiển thị làm key**, hai máy có thể không đồng ý. Nếu database lưu `USD`, cả hai đều hiểu cùng identifier và chỉ render label riêng.

### 20.1. Quy tắc an toàn khi giao tiếp qua services

- **Payload machine:** ISO chữ, hoặc numeric code **string đúng ba ký tự** nếu contract yêu cầu.
- **Payload amount:** decimal string/typed amount với precision và rounding policy.
- **Locale UI:** BCP 47 language tag, độc lập với currency.
- **Presentation:** display name/symbol/format được tạo từ locale cụ thể.
- **Versioning:** schema và currency directory có version khi cần historical correctness.
- **Idempotency:** cùng currency/amount phải được kiểm tra consistency khi retry.
- **Security:** validate currency input, allowlist business units; không tin client gửi tên dịch.
- **Observability:** log canonical code thay vì chỉ ký hiệu `$` hoặc tên đa ngôn ngữ.
- **Privacy:** không in amount/token/transaction ID nhạy cảm trong demo/log tùy tiện.
- **Fail closed:** unsupported currency không tự biến thành USD để chạy tiếp.

### 20.2. Thiết kế API “chọn tiền tệ rồi hiển thị”

```text
Client sends currencyCode="AUD", displayLocale="vi-VN"
           |
           v
Validate exact currency code, business allowlist
           |
           v
Currency.getInstance("AUD")   ---> machine code "AUD"
           |
           +-- getNumericCodeAsString() ---> "036"
           |
           +-- getDisplayName(vi-VN) ---> localized text (JDK data)
           |
           +-- getSymbol(vi-VN) ---> localized symbol/fallback code
           |
           +-- Money amount + currency type safety/rounding policy
           |
           v
Return structured payload; keep machine identifiers separate from labels
```

**Điểm quyết định:** không bao giờ parse localized label trở lại thành currency code bằng split/replace thủ công. Với nhiều currency share symbol hoặc localized names đổi theo version, suy ngược không bảo đảm duy nhất.

## 21. Hai loại “mã dạng số” dễ bị nhầm

Đối với ISO 4217, **numeric code** được biểu diễn bằng ba ký tự decimal khi dùng ở dạng chuỗi. Điều đó khác:

1. **ISO 3166 numeric country code:** mã định danh quốc gia, không phải mã currency.
2. **Minor units:** số chữ số thập phân theo tiền tệ, ví dụ USD là 2.
3. **Payment gateway internal currency ID:** có thể là integer riêng của nhà cung cấp, không chắc trùng ISO 4217.
4. **FX rate:** giá một đơn vị tiền tệ theo đơn vị tiền khác, thay đổi theo thời điểm.
5. **Số tiền:** BigDecimal/minor-unit amount, hoàn toàn không phải code.

Một user nhìn mã `036` của AUD có thể hiểu sai nó là “36 xu” hoặc “36 nước Úc”; bài toán nghiệp vụ phải đặt tên field rõ như `numericCurrencyCode` thay vì `currencyNumber` mơ hồ.

## 22. Những lỗi phổ biến và hướng sửa

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `getNumericCode()` rồi serialize `AUD` thành `36` khi schema yêu cầu ba số | Mất `0` đầu | `getNumericCodeAsString()` → `"036"` |
| Gọi `Currency.getInstance("840")` | Factory nhận mã chữ, không numeric string | Dùng `USD` hoặc mapping chuẩn có version |
| Coi `getDisplayName()` là English ở mọi server | Dùng default DISPLAY locale | `getDisplayName(userLocale)` |
| Lưu display name vào database làm primary key | Bản dịch có thể đổi | Lưu `getCurrencyCode()` |
| Coi symbol `$` là duy nhất | Nhiều currencies share symbol | Hiển thị thêm ISO code khi cần |
| Giả định all currencies có 2 fraction digits | JPY=0, KWD=3, XXX=-1 | Dùng metadata + domain policy |
| Lẫn numeric code với fraction digits | `840` không phải `2` | Phân biệt fields |
| Chọn currency theo `Locale.forLanguageTag("vi-VN")` thay vì explicit charge unit | Đổi USD thành VND ngoài ý định | Currency field độc lập với locale |
| Không kiểm `Currency.getInstance(Locale)` có thể null | Territories không có currency | Handle null/unsupported country |
| Tin `getAvailableCurrencies()` là tập đang được PSP chấp nhận | Có obsolete/pseudo codes | Business allowlist |
| Không phân biệt `cu` và `rg` | Có currency/region overrides | Tuân theo Unicode extension precedence |
| Set default locale trong request thread | Thay global process state | Explicit per-request Locale |
| `NumberFormat.setCurrency(JPY)` rồi nghĩ fraction digits tự thành 0 | Formatter giữ min/max digits | Cấu hình fraction digits/rounding |
| Dùng `double` cho tiền | Floating point precision | `BigDecimal`/money type |
| Cộng USD với JPY | Khác đơn vị | Kiểm currency, có FX policy nếu chuyển |
| Dùng `String.format("%03d",n)` thiếu locale trong máy xử lý ID | Locale có thể ảnh hưởng digits | `getNumericCodeAsString()` |
| Đồng nhất “runtime biết” với “được phép charge” | ISO != business policy | Validate syntax, recognition, allowlist |
| Dùng regex `[A-Z]{3}` là đủ | ZZZ hợp pattern nhưng không recognized | `Currency.getInstance` + allowlist |
| Catch mọi lỗi và default USD | Nguy cơ giao dịch sai currency | Fail fast, validation response |
| Hard-code “Đô la Mỹ” trong test không kiểm soát CLDR | Nhãn đổi khi nâng JDK | Test stable properties/versioned snapshot |
| Bỏ qua Unicode accents/glyph/bidi | Lỗi render UI | UTF-8/font/bidi và locale-aware testing |
| Parse ký hiệu thành code | Ký hiệu không duy nhất | Value field là ISO alphabetic code |
| Xem `getNumericCode` là exchange rate | Code là định danh | FX service/data policy |
| Dùng `XXX` như currency thanh toán thật | Pseudo-currency không phù hợp charge | Chặn theo business policy |
| Không versioning lịch sử currency | Country assignment đổi theo năm | Lưu code per transaction + lịch sử |
| Chia sẻ mutable NumberFormat giữa threads | Formatting state không thread-safe | Formatter per-use hoặc đồng bộ |
| Cache display names vĩnh viễn không kèm locale | Dữ liệu localized/version-dependent | Cache theo locale/version, invalidate khi cần |

## 23. Checklist review trước khi phát hành

1. Currency được lấy bằng `Currency.getInstance(String)` từ mã chữ đã validate chưa?
2. Có kiểm currency được JDK hỗ trợ và business chấp nhận không?
3. Nếu input numeric, schema có giữ đủ **ba chữ số** kể cả `0` đầu không?
4. Có phân biệt `getNumericCodeAsString()` (Java 9+) và `getNumericCode()` (Java 7+) không?
5. Có tránh dùng display name/symbol làm key trong database không?
6. Display label có được tạo bằng `getDisplayName(userLocale)` không?
7. Có truyền explicit Locale thay vì phụ thuộc process default locale không?
8. Có phân biệt `Locale.Category.DISPLAY` và `FORMAT` không?
9. Có kiểm code không đổi khi user đổi ngôn ngữ hiển thị không?
10. Nếu dùng `Currency.getInstance(Locale)`, có hiểu country/`cu`/`rg` selection không?
11. Có xử lý locale không có country, unsupported country, territory without currency không?
12. Có tách amount (BigDecimal) khỏi currency identifier không?
13. Có validate amount scale/rounding theo đúng domain không, không chỉ minor unit mặc định?
14. Có phân biệt numeric code với fraction digits và exchange rate không?
15. Có tránh mixed-currency arithmetic khi chưa chuyển đổi theo FX policy không?
16. Nếu dùng `NumberFormat.setCurrency`, fraction digits đã cấu hình phù hợp chưa?
17. Có không chia sẻ mutable NumberFormat giữa threads không?
18. Có test Unicode names, accents, glyph/bidi/font trong UI locales hỗ trợ không?
19. Có xử lý bản dịch không có, fallback về ISO code không?
20. Có không hard-code exact translated strings nếu JDK locale data có thể thay đổi không?
21. Có đưa ISO 4217/JDK currency data update vào quy trình upgrade/release không?
22. Có không lấy obsolete/pseudo codes làm danh mục active mặc định không?
23. Có thiết kế API fields có tên rõ `currencyCode` và `numericCurrencyCode` không?
24. Có không tự ý uppercase theo default language của server không?
25. Có tránh global `Locale.setDefault` trong web request không?
26. Có unit test mã AUD `036` không bị thành `36` khi serialize không?
27. Có logging canonical code thay vì chỉ ký hiệu `$` không?
28. Có document rõ JDK version và locale provider cho snapshot tests không?
29. Có không tự coi một currency code là thuộc một quốc gia vĩnh viễn không?
30. Có thực hiện input validation độc lập với người dùng chọn ngôn ngữ nào không?

## 24. Bài tập thực hành

**Bài 1 — Currency instance.** Chạy `CurrencyBasicDemo`. Giải thích vì sao `getInstance("USD")` và `getInstance(Locale.US)` cho cùng instance trong dữ liệu hiện hành.

**Bài 2 — Mã số ba chữ số.** Chạy `CurrencyLeadingZeroDemo`; vì sao `AUD-int=36` nhưng `AUD-string=036`? Viết JSON payload giữ numeric ID đúng ba ký tự.

**Bài 3 — Tên bản địa hóa.** Chạy `CurrencyDisplayNamesDemo` với `Locale.FRANCE`, `Locale.GERMANY` và `vi-VN`. Tại sao không dùng bản dịch làm database key?

**Bài 4 — DISPLAY vs FORMAT.** Chạy `CurrencyDisplayDefaultDemo`. Tại sao `getDisplayName()` theo DISPLAY locale mà `NumberFormat` có thể theo FORMAT locale?

**Bài 5 — Unicode cu extension.** Chạy `CurrencyUnicodeExtensionDemo`, thay `cu-jpy` bằng `cu-eur`; giải thích precedence so với `rg-uszzzz`.

**Bài 6 — Input errors.** Chạy `CurrencyInputErrorsDemo`, bổ sung unsupported code và xử lý NPE/IAE riêng. Không swallow exception bằng cách tự chuyển sang USD.

**Bài 7 — Fraction digits.** Chạy `CurrencyFractionDemo`; so USD/JPY/KWD/XXX. Vì sao numeric code không suy ra được minor unit?

**Bài 8 — NumberFormat.** Chạy `CurrencyFormatDemo` và cố bỏ `setMaximumFractionDigits(0)`; quan sát output và giải thích lý do.

**Bài 9 — BigDecimal.** Chạy `CurrencyBigDecimalDemo`. Thêm test xử lý `"12.340"` theo `RoundingMode.UNNECESSARY` và giải thích ý nghĩa không mất giá trị.

**Bài 10 — Allowlist.** Chạy `CurrencyCodeGuardDemo`, sửa allowlist theo một danh mục test khác, reject `XXX` và unsupported codes.

**Bài 11 — Available set.** Chạy `CurrencyAvailableSetDemo`. Vì sao thay đổi bản copy không làm `Currency.getInstance("USD")` ngừng hoạt động?

**Bài 12 — Locale region.** Chạy `CurrencyRegionAndLanguageDemo`. Giải thích vì sao người dùng English ở VN vẫn có VND mặc định, còn tiếng Việt ở US có thể dùng USD.

**Bài 13 — Unicode NFC.** Chạy `CurrencyUnicodeNormalizationDemo`. Phân biệt code point, UTF-16 code unit và giao diện grapheme cluster.

**Bài 14 — Money record.** Chạy `CurrencyMoneyRecordDemo`, thêm JPY và thử cộng với USD; thiết kế thông báo lỗi nghiệp vụ rõ.

**Bài 15 — Locale matrix.** Chạy `CurrencyDisplayMatrixDemo`, thêm `Locale.JAPAN` và `Locale.KOREA`. Assert các labels không rỗng, không assert một bản dịch exact cố định.

**Bài 16 — Numeric code key.** Thiết kế database có `CHAR(3)` cho numeric currency identifier; chứng minh `"036"` được giữ nguyên khi serialize roundtrip.

**Bài 17 — Sorting UI.** Xây danh sách dropdown currency dùng `Collator.getInstance(locale)` để sort theo localized display names, nhưng value của option vẫn là mã chữ.

**Bài 18 — Fallback.** Giả lập locale thiếu bản dịch và kiểm tra UI hiển thị ISO currency code, không trắng màn hình.

**Bài 19 — History.** Mô tả vì sao lịch sử giao dịch phải lưu explicit currency code, không suy ra lại từ quốc gia hiện tại.

**Bài 20 — Exchange rate.** Thiết kế một FX conversion DTO có source/target ISO code, rate, timestamp, source, rounding policy. Không tự lấy tỷ giá từ `Currency`.

**Bài 21 — CLDR upgrade test.** Tạo snapshot tên hiển thị ba locale trên một JDK cố định; khi nâng JDK, review diff và chỉ chấp nhận thay đổi được kỳ vọng.

**Bài 22 — Security.** Thiết kế validation pipeline cho đầu vào `currencyCode` và `displayLocale`, phân biệt lỗi syntax, unsupported, forbidden by business.

**Bài 23 — Pseudo currency.** Dùng `Currency.getInstance("XXX")`, giải thích vì sao ISO có special code nhưng PSP không nên chấp nhận charge.

**Bài 24 — Multi-thread.** Tạo nhiều tasks format money với `NumberFormat` riêng theo request locale; giải thích vì sao không nên share một mutable formatter.

## 25. Tổng kết

- `Currency` là **metadata về đơn vị tiền tệ**, không phải money amount, không phải FX rate.
- `getDisplayName(Locale)` trả tên bản địa hóa **cho UI**; đầu ra phụ thuộc locale/JDK data và có thể fallback về mã ISO.
- `getNumericCode()` (Java 7+) trả `int`; vì vậy `AUD=036` sẽ hiện thành `36` nếu serialize thẳng.
- `getNumericCodeAsString()` (Java 9+, sẵn trong Java 17) trả **chuỗi ba chữ số**: lựa chọn ưu tiên cho ISO numeric ID dạng fixed width.
- `getCurrencyCode()` trả mã chữ như `USD`, rất phù hợp làm canonical storage/API ID.
- `getSymbol(Locale)` là ký hiệu presentation, **không duy nhất**.
- `getDisplayName()`/`getSymbol()` không tham số dùng default `Locale.Category.DISPLAY`; trong ứng dụng nhiều users nên truyền locale tường minh.
- `getInstance(Locale)` dựa vào country và Unicode `cu`/`rg` overrides; đây không phải dịch tên.
- `getDefaultFractionDigits()` chỉ là minor units mặc định, không liên quan numeric code và có thể là `-1` cho pseudo-currency.
- `Currency.getAvailableCurrencies()` có thể chứa obsolete codes; cần business allowlist.
- Dùng `BigDecimal` và policy tiền tệ rõ cho số tiền; tránh cộng trộn currencies/rounding ngầm.
- Bản dịch, Unicode và CLDR có thể thay đổi; test stable properties và quản lý locale data version.
- Những API giới thiệu đều **còn áp dụng trong Java 17+**; không cần kiến thức legacy.

## Tài liệu chính thức

- [Currency — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html): `getDisplayName`, `getNumericCode`, `getNumericCodeAsString`, `getInstance`, `getSymbol`, `getDefaultFractionDigits`.
- [Currency — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Currency.html): đối chiếu API hiện hành và mốc `since 1.7`/`since 9`.
- [Locale — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html): BCP 47, `Locale.Category`, Unicode `cu`/`rg` extensions, ngôn ngữ và vùng.
- [NumberFormat — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html): currency format, min/max fraction digits.
- [DecimalFormat — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html): `setCurrency` không tự đổi min/max fraction digits, formatting và thread safety.
- [BigDecimal — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): decimal arithmetic, scale, rounding.
- [Normalizer — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html): Unicode normalization.
- [JDK 21 Supported Locales — Oracle](https://www.oracle.com/java/technologies/javase/jdk21-supported-locales.html): locale data providers, CLDR và phạm vi hỗ trợ.
- [ISO 4217 currency codes — ISO](https://www.iso.org/iso-4217-currency-codes.html): chuẩn định danh tiền tệ.
