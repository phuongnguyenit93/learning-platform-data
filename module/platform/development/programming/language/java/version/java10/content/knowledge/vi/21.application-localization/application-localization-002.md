# Quy ước tiền tệ tường minh trong hiển thị số — Locale và Currency (Java 10+)

## 1. Tình huống: cùng số tiền nhưng cách hiển thị khác nhau

Một hệ thống có thể lưu **1.234.567,89 USD** dưới dạng số tiền có mã tiền tệ `USD`, rồi hiển thị cho người dùng tại Hoa Kỳ, Đức và Việt Nam. Ba giao diện có thể cần các dấu phân nhóm, dấu thập phân, vị trí ký hiệu và dấu cách khác nhau:

- Theo quy ước `en-US`: `$1,234,567.89`.
- Theo quy ước `de-DE`: có thể là `1.234.567,89 $`.
- Theo quy ước `vi-VN`: có thể là `1.234.567,89 US$`.

Đây chỉ là **các cách biểu diễn** của **cùng một số tiền bằng USD**, không phải ba giá trị hoặc ba phép quy đổi ngoại tệ. Dấu cách trước ký hiệu trong một số locale có thể là **U+00A0 NO-BREAK SPACE** hoặc một ký tự không tách dòng khác; dữ liệu locale từ JDK có thể thay đổi giữa phiên bản hoặc nhà cung cấp.

Lỗi dễ gặp là để locale tự động quyết định **cả cách hiển thị lẫn đồng tiền**, hoặc chỉ đổi mã currency mà quên chính sách số chữ số thập phân:

```java
var formatter = java.text.NumberFormat.getCurrencyInstance(
        java.util.Locale.US);

formatter.setCurrency(java.util.Currency.getInstance("VND"));

// Không thể suy luận formatter đã tự đổi số lẻ từ 2 sang 0!
```

Theo Javadoc Java SE hiện hành, `setCurrency(Currency)` **không cập nhật** `minimumFractionDigits`/`maximumFractionDigits`. Nếu nghiệp vụ cần in VND không có chữ số lẻ, phải cấu hình tường minh.

Mục tiêu bài:

1. Tách bạch **Locale hiển thị**, **Currency của khoản tiền**, **số tiền** và **quy tắc làm tròn/độ chính xác**.
2. Sử dụng `NumberFormat.getCurrencyInstance(Locale)` và `Currency.getInstance("USD")`/`"VND"` đúng cách.
3. Định nghĩa số chữ số thập phân và `RoundingMode` khi đổi currency hoặc khi có yêu cầu nghiệp vụ.
4. Dùng `BigDecimal` để lưu/tính số tiền, không đưa lỗi floating-point vào dữ liệu tiền.
5. Kiểm thử nhiều locale, nhiều mã tiền, ký hiệu không duy nhất, khoảng trắng Unicode và thay đổi dữ liệu locale theo JDK.
6. Thiết kế boundary API an toàn: không dùng chuỗi đã format để làm dữ liệu tiền gốc; không chia sẻ mutable `NumberFormat` bừa bãi giữa các thread.

Những API và nguyên tắc sau **vẫn áp dụng trong Java hiện đại**. Chương trình đầy đủ ở mục 12 được biên dịch bằng `javac --release 10`, không dựa vào tính năng Java được giới thiệu sau Java 10.

## 2. Bốn lớp thông tin phải tách biệt

| Thành phần | Đại diện trong Java | Trả lời câu hỏi |
| --- | --- | --- |
| Giá trị số tiền | `BigDecimal` | “Bao nhiêu?” |
| Đơn vị tiền tệ | `Currency`, thường xác định bằng mã ISO 4217 | “USD, VND, EUR hay JPY?” |
| Quy ước trình bày | `Locale` | “Dùng dấu nào, ký hiệu ở đâu, biểu diễn theo ngôn ngữ/khu vực nào?” |
| Chính sách chữ số/làm tròn | `fractionDigits`, `RoundingMode` | “Hiển thị mấy chữ số lẻ, xử lý phần dư thế nào?” |

Ví dụ một giá trị trong hệ thống:

```java
java.math.BigDecimal amount = new java.math.BigDecimal("1234567.89");
java.util.Currency currency = java.util.Currency.getInstance("USD");
java.util.Locale viewerLocale = java.util.Locale.forLanguageTag("vi-VN");
```

Ở đây:

- `amount` không mang ký hiệu `$` hay dấu phân nhóm.
- `currency` là **USD** dù người xem ở Việt Nam.
- `viewerLocale` quyết định **quy ước hiển thị** cho người dùng, không làm số tiền “thành VND”.
- Formatter có thể hiện mã hoặc ký hiệu bản địa hóa phù hợp với sự kết hợp locale–currency.

**Không lấy vị trí địa lý/ngôn ngữ của người dùng làm bằng chứng đơn vị tiền của giao dịch.** Người Việt có thể xem giá bằng USD; người dùng ở Đức có thể xem cùng số tiền USD bằng cách viết theo quy ước Đức.

## 3. Locale được chọn tường minh

Trong Java, `Locale` mô tả thông tin ngôn ngữ và vùng/biến thể có ý nghĩa cho bản địa hóa. Một cách khai báo còn áp dụng từ trước Java 10 đến nay:

```java
java.util.Locale viVN = java.util.Locale.forLanguageTag("vi-VN");
java.util.Locale enUS = java.util.Locale.forLanguageTag("en-US");
java.util.Locale deDE = java.util.Locale.forLanguageTag("de-DE");
```

Tại biên giao diện, có thể lấy locale từ tùy chọn người dùng, nội dung request đã được xác thực hoặc chính sách ứng dụng; sau đó **truyền trực tiếp vào formatter**.

Không dựa vào:

```java
// Có thể lấy locale mặc định của tiến trình, không đúng ý người xem:
java.text.NumberFormat.getCurrencyInstance();
```

Lời gọi không có `Locale` sử dụng locale mặc định liên quan đến **FORMAT** của JVM, có thể không giống preference của từng người dùng. Một server xử lý hàng nghìn request từ nhiều quốc gia không thể xem default locale của process là locale chính xác cho mọi request.

**Không đổi `Locale.setDefault(...)` theo từng request.** Đây là trạng thái cấp tiến trình, có thể ảnh hưởng đồng thời đến những request/đoạn code khác. Hãy truyền `Locale` như một tham số ở đúng tầng trình bày.

### Locale không nhất thiết có quốc gia

Một `Locale` chỉ có ngôn ngữ, ví dụ `"vi"`, chưa đủ để suy ra chắc chắn một quốc gia hoặc đồng tiền giao dịch. Một số extension Unicode cũng có thể ảnh hưởng lựa chọn định dạng trên các provider hỗ trợ. Khi đơn vị tiền đã biết, **chọn `Currency` từ mã của giao dịch**, không suy luận từ người xem.

Nếu locale đến từ chuỗi ngoài, cần validate/canonicalize theo những locale hệ thống thực sự hỗ trợ. `Locale.forLanguageTag` không phải công cụ xác thực tuyệt đối mọi tag đầu vào và có thể chấp nhận/chuẩn hóa các phần hợp lệ; đừng âm thầm dùng một locale sai chỉ vì parser trả một object.

## 4. Currency là đơn vị tiền, không phải một kiểu tỷ giá

`java.util.Currency` biểu diễn currency code theo quy tắc ISO 4217 được JDK hỗ trợ:

```java
java.util.Currency usd = java.util.Currency.getInstance("USD");
java.util.Currency vnd = java.util.Currency.getInstance("VND");
java.util.Currency eur = java.util.Currency.getInstance("EUR");

System.out.println(usd.getCurrencyCode()); // USD
System.out.println(vnd.getCurrencyCode()); // VND
```

Với một mã không được nhận dạng/hợp lệ theo cơ sở dữ liệu currency của JDK, `Currency.getInstance(String)` có thể ném `IllegalArgumentException`. Cần có lớp validation riêng nếu mã currency đến từ người dùng hoặc bên thứ ba.

**Không nhầm:**

- `Currency.getInstance("USD")`: chọn đơn vị tiền USD.
- `Currency.getInstance(Locale.US)`: hỏi đơn vị tiền gắn với một quốc gia/locale theo dữ liệu hiện hành; **không phải nguồn chân lý cho currency của giao dịch**.
- `currency.getSymbol(locale)`: lấy một **ký hiệu để hiển thị** theo locale; ký hiệu không phải mã định danh toàn cầu duy nhất.

Ví dụ ký hiệu `$` có thể liên quan nhiều đơn vị tiền khác nhau; một locale có thể hiển thị `US$` để phân biệt USD. Vì vậy API, database, thông điệp thanh toán và log nghiệp vụ nên giữ **mã currency độc lập**.

### Đổi Currency không quy đổi amount

```java
var f = java.text.NumberFormat.getCurrencyInstance(
        java.util.Locale.US);

f.setCurrency(java.util.Currency.getInstance("EUR"));
```

Hai dòng trên chỉ đổi quy ước/ký hiệu tiền hiển thị trên formatter. Chúng **không tính tỷ giá** từ USD sang EUR và **không thay đổi amount**.

Nếu một giao dịch USD thật sự cần chuyển sang EUR, ứng dụng phải có một bước tính toán riêng với tỷ giá, thời điểm áp dụng, nguồn dữ liệu đáng tin, quy tắc làm tròn và nghĩa vụ lưu vết của nghiệp vụ. Không gọi `setCurrency("EUR")` rồi công bố rằng số USD đã được chuyển đổi.

## 5. Dùng đúng NumberFormat.getCurrencyInstance(Locale)

Cách cơ bản:

```java
var usFormat = java.text.NumberFormat.getCurrencyInstance(
        java.util.Locale.US);

System.out.println(
        usFormat.format(new java.math.BigDecimal("1234567.89"))
); // Ví dụ với locale en-US thường: $1,234,567.89
```

`NumberFormat.getCurrencyInstance(locale)` cung cấp một formatter theo quy ước currency của locale. Nó có thể mang một đơn vị tiền mặc định được suy ra từ locale, nhưng **không nên dựa vào suy luận đó nếu amount đã có mã tiền riêng**.

Cách khai báo tường minh hơn:

```java
java.util.Locale locale =
        java.util.Locale.forLanguageTag("vi-VN");

java.util.Currency currency =
        java.util.Currency.getInstance("USD");

java.text.NumberFormat formatter =
        java.text.NumberFormat.getCurrencyInstance(locale);

formatter.setCurrency(currency);
```

Thứ tự chính:

1. Tạo formatter theo **locale trình bày**.
2. Chọn currency theo **dữ liệu khoản tiền**.
3. Cấu hình **số chữ số thập phân** theo currency và chính sách nghiệp vụ.
4. Cấu hình **quy tắc làm tròn** theo yêu cầu ứng dụng.
5. Gọi `format(amount)` chỉ ở ranh giới hiển thị.

Formatter thường trả chuỗi có dấu phân nhóm, dấu thập phân và vị trí currency marker theo locale. **Không tự chèn dấu chấm, dấu phẩy hoặc nối chuỗi `"$" + amount`** để định dạng tiền quốc tế.

### Không dùng NumberFormat.getNumberInstance cho currency

`NumberFormat.getNumberInstance(locale)` dùng cho số thường, không phải currency style. Chỉ `setCurrency` lên một formatter bất kỳ không bảo đảm nó tự đổi sang currency pattern nếu ban đầu được tạo để format số thường. Khi muốn biểu diễn tiền, bắt đầu từ `getCurrencyInstance(locale)`.

## 6. Bẫy quan trọng: setCurrency không sửa số chữ số phần thập phân

Javadoc của `NumberFormat.setCurrency` và `DecimalFormat.setCurrency` quy định rõ rằng việc đặt currency **không cập nhật**:

- `minimumFractionDigits`;
- `maximumFractionDigits`.

Ví dụ chạy trên formatter US tiêu chuẩn:

```java
var formatter = java.text.NumberFormat.getCurrencyInstance(
        java.util.Locale.US);

formatter.setCurrency(java.util.Currency.getInstance("VND"));

System.out.println(formatter.getCurrency().getCurrencyCode()); // VND
System.out.println(formatter.getMinimumFractionDigits());     // 2
System.out.println(formatter.getMaximumFractionDigits());     // 2
```

VND có **0** chữ số lẻ theo default fraction digits của ISO 4217, nhưng formatter vừa được tạo bằng locale US có thể tiếp tục giữ **2** chữ số lẻ từ pattern ban đầu. Đây không phải phép làm tròn chuẩn cho tất cả nhu cầu VND.

**Cách đúng:** sau khi chọn currency, cấu hình fraction digits chủ động:

```java
var format = java.text.NumberFormat.getCurrencyInstance(
        java.util.Locale.US);

var vnd = java.util.Currency.getInstance("VND");
format.setCurrency(vnd);

int digits = vnd.getDefaultFractionDigits(); // Thông thường 0 đối với VND.
if (digits < 0) {
    throw new IllegalArgumentException(
            "Currency requires an explicit fraction policy");
}
format.setMinimumFractionDigits(digits);
format.setMaximumFractionDigits(digits);
```

Cả `setMinimumFractionDigits` và `setMaximumFractionDigits` cần được đặt để có số lẻ **cố định** khi chính sách mong muốn là hiển thị đúng N chữ số.

Đối với các pseudo-currency đặc biệt, `Currency.getDefaultFractionDigits()` có thể trả **-1**. Không đưa -1 thẳng vào setter rồi ngầm hiểu đó là một chính sách tiền hợp lệ. Hãy định nghĩa quy tắc của ứng dụng cho trường hợp ấy.

## 7. Số chữ số mặc định của currency không phải toàn bộ luật nghiệp vụ

`Currency.getDefaultFractionDigits()` cho số chữ số lẻ mặc định/đơn vị phụ của currency theo dữ liệu ISO 4217 được JDK sử dụng.

Ví dụ thường gặp:

| Currency code | Default fraction digits | Ý nghĩa hiển thị phổ biến |
| --- | ---: | --- |
| `USD` | 2 | Hai chữ số cent |
| `EUR` | 2 | Hai chữ số |
| `VND` | 0 | Thường không hiển thị số lẻ |
| `JPY` | 0 | Thường không hiển thị số lẻ |
| Pseudo-currency như `XXX` | -1 | Không có chính sách default fraction digits thông thường |

Đây là **metadata**, không phải quy tắc xử lý mọi giao dịch. Một số tình huống có thể cần nhiều hoặc ít chữ số hơn:

- Giá đơn vị trong tính toán nội bộ có thể có nhiều chữ số hơn giá thanh toán cuối.
- Phí, lãi hoặc tỷ giá có thể dùng độ chính xác cao để tránh cộng dồn sai số.
- Thanh toán thực tế có thể có quy tắc làm tròn tiền mặt khác số chữ số hiển thị.
- Dữ liệu lịch sử có thể chịu chính sách tiền tệ tại thời điểm giao dịch.
- Hệ thống thanh toán có thể có quy ước minor unit riêng đối với sản phẩm/giao dịch.

Do đó, có thể dùng `getDefaultFractionDigits()` làm **mặc định hiển thị**, nhưng business rule cần rõ ràng hơn khi hệ thống thanh toán, kế toán hoặc đối soát yêu cầu.

Không ép một khoản tiền nội bộ có độ chính xác cao về số lẻ hiển thị ngay khi lưu dữ liệu. **Làm tròn để format text** và **làm tròn giá trị giao dịch** là hai operation khác nhau.

## 8. BigDecimal để bảo toàn giá trị tiền

Các kiểu `float`/`double` biểu diễn nhị phân, không thể giữ chính xác mọi phân số thập phân. Ví dụ `0.1` không có biểu diễn binary floating point hoàn toàn chính xác.

Để lưu/tính giá trị tiền, ưu tiên `BigDecimal`:

```java
java.math.BigDecimal price =
        new java.math.BigDecimal("1234567.895");
```

Không nên tạo từ một decimal `double` bằng constructor:

```java
// Có thể mang sai số nhị phân của literal:
java.math.BigDecimal risky = new java.math.BigDecimal(0.1);

// Đúng theo chuỗi decimal gốc:
java.math.BigDecimal exact = new java.math.BigDecimal("0.1");

// Nếu dữ liệu ban đầu đã là double:
java.math.BigDecimal fromDouble =
        java.math.BigDecimal.valueOf(0.1);
```

`BigDecimal.valueOf(double)` thường dùng cách biểu diễn decimal chuẩn của double, ít gây bất ngờ hơn constructor nhận double; nhưng nếu số đã bị làm tròn/mất thông tin **trước đó**, không có cách tự khôi phục lại giá trị gốc chỉ bằng `BigDecimal`.

Dữ liệu tiền tối thiểu nên lưu **amount + ISO code** thành hai trường có kiểu rõ ràng, không chỉ lưu text định dạng như `"$1,000.00"`.

`NumberFormat.format(amount)` tạo chuỗi trình bày, không mutate `BigDecimal` gốc. Nhưng nó **có thể làm tròn cách hiển thị**, khiến một phần lẻ không xuất hiện trên màn hình. Đó là lý do các phép tính quan trọng phải làm trên amount gốc với chính sách số học riêng.

## 9. Cấu hình rounding rõ ràng

Sau khi quyết định số chữ số lẻ, phải xác định điều gì xảy ra nếu amount có nhiều chữ số hơn. Các lựa chọn của `java.math.RoundingMode` gồm `HALF_EVEN`, `HALF_UP`, `DOWN`, `CEILING`, `FLOOR`, v.v.

Ví dụ đúng điểm hòa (*tie*):

```java
var amount = new java.math.BigDecimal("1.005");

var format = java.text.NumberFormat.getCurrencyInstance(
        java.util.Locale.US);

format.setCurrency(java.util.Currency.getInstance("USD"));
format.setMinimumFractionDigits(2);
format.setMaximumFractionDigits(2);

format.setRoundingMode(java.math.RoundingMode.HALF_EVEN);
System.out.println(format.format(amount)); // $1.00

format.setRoundingMode(java.math.RoundingMode.HALF_UP);
System.out.println(format.format(amount)); // $1.01
```

- `HALF_EVEN` là kiểu làm tròn về chữ số chẵn ở trường hợp hòa. Với `1.005` và 2 chữ số lẻ, giá trị hiển thị là `1.00`.
- `HALF_UP` làm tròn lên khi ở điểm hòa theo hướng xa 0, cho `1.01` ở ví dụ này.
- Khi nghiệp vụ chọn một quy tắc làm tròn, **ghi rõ ở code và test**; không lấy “máy tôi thấy đúng” làm hợp đồng.

Các formatter thông thường trả về từ `NumberFormat.getCurrencyInstance` trên JDK hỗ trợ `setRoundingMode` như ví dụ chạy. Về mặt API, một số subclass `NumberFormat` do provider tùy biến có thể không hỗ trợ các operation nhất định; khi tích hợp provider tùy biến hãy kiểm tra hợp đồng implementation.

**Quan trọng:** `RoundingMode` áp dụng khi biểu diễn hoặc thực hiện phép tính có làm tròn. Nếu người dùng cần thanh toán theo một mức đơn vị khác (ví dụ quy tắc làm tròn tiền mặt theo bội số cụ thể), việc đặt 0 hay 2 chữ số của NumberFormat **không đủ** để triển khai toàn bộ quy tắc đó.

## 10. Ký hiệu, dấu phân nhóm, dấu thập phân và khoảng trắng

Cách hiển thị currency có nhiều phần độc lập:

| Khía cạnh | Có thể thay đổi theo locale? | Tác động |
| --- | --- | --- |
| Dấu phân nhóm hàng nghìn | Có | `1,234,567` hay `1.234.567` |
| Dấu thập phân | Có | `1,234.56` hay `1.234,56` |
| Vị trí ký hiệu | Có | Ký hiệu trước hoặc sau số |
| Dấu cách giữa số và currency | Có | Space thường, NBSP hoặc dạng khác |
| Ký hiệu currency | Có | `$`, `US$`, `₫` hay dạng khác |
| Chữ số phần lẻ | Theo formatter và policy | Không tự thay khi `setCurrency` |
| Kiểu hiển thị số âm | Có | Dấu trừ hoặc pattern khác tùy locale |
| Các chữ số dùng để in | Có thể | Một số locale có cách chọn numbering system khác |

**Không tự tách chuỗi format dựa vào dấu phẩy**, và không xây dựng regex đơn giản kiểu chỉ cho phép `[0-9,.$]` để xử lý mọi locale. Chữ số, dấu cách không tách dòng, dấu tiền và thứ tự có thể khác giữa các hệ thống.

### NBSP và NNBSP trong unit test

Dữ liệu locale có thể chứa các dấu cách:

- `U+0020`: space thường.
- `U+00A0`: NO-BREAK SPACE (NBSP).
- `U+202F`: NARROW NO-BREAK SPACE (NNBSP).

Nhìn bằng mắt chúng khá giống nhau. Test so sánh một string chứa space thường với một string chứa NBSP có thể thất bại dù ảnh giao diện có vẻ giống.

Trong ví dụ đầy đủ, hàm `showSpaces` thay các dấu cách đặc biệt bằng marker `<NBSP>` hoặc `<NNBSP>` **chỉ để in ra console dễ đọc**. Không nên thay chúng khi xuất chính chuỗi đã format cho UI nếu mục tiêu là tôn trọng quy tắc locale.

### Ký hiệu không phải mã định danh

`Currency.getSymbol(locale)` có thể trả ký hiệu phụ thuộc locale; nếu không có symbol phù hợp, nó có thể trả mã ISO. Không dùng string ký hiệu để xác định chính xác currency đầu vào. Nếu sản phẩm hiển thị nhiều đồng tiền có thể gây nhầm, cần thiết kế cách thể hiện **mã ISO** hoặc nhãn rõ ràng cùng giá, theo yêu cầu giao diện.

## 11. Hàm helper tường minh dùng trong ứng dụng

Một helper đơn giản:

```java
static java.text.NumberFormat newMoneyFormat(
        java.util.Locale locale,
        java.util.Currency currency,
        int fractionDigits,
        java.math.RoundingMode roundingMode) {

    if (fractionDigits < 0) {
        throw new IllegalArgumentException("Negative fraction digits");
    }

    var formatter = java.text.NumberFormat.getCurrencyInstance(locale);
    formatter.setCurrency(currency);
    formatter.setMinimumFractionDigits(fractionDigits);
    formatter.setMaximumFractionDigits(fractionDigits);
    formatter.setRoundingMode(roundingMode);
    formatter.setGroupingUsed(true);
    return formatter;
}
```

Đây là phương thức có thể đặt trong một class Java; ví dụ hoàn chỉnh có validation chặt hơn ở mục 12.

Tại ranh giới API:

```java
var amount = new java.math.BigDecimal("1200.50");
var currency = java.util.Currency.getInstance("USD");
var viewerLocale = java.util.Locale.forLanguageTag("vi-VN");

String display = newMoneyFormat(
        viewerLocale, currency, 2,
        java.math.RoundingMode.HALF_EVEN).format(amount);
```

**Các yêu cầu để helper an toàn**:

1. `locale` phải do người dùng hoặc chính sách hiển thị xác định; không tự thay bằng `Locale.getDefault()`.
2. `currency` phải xuất phát từ mã tiền của giao dịch, không phải từ locale hiển thị.
3. `fractionDigits` phải xuất phát từ policy rõ ràng, có thể khởi tạo từ `currency.getDefaultFractionDigits()` khi phù hợp.
4. `roundingMode` do nghiệp vụ xác định.
5. Với concurrent request, **tạo formatter theo lời gọi hoặc per-thread**, không dùng một singleton mutable dùng chung mà không đồng bộ.
6. Không cache formatter bằng một key thiếu currency/fractionDigits/roundingMode: hai request cùng locale nhưng dùng các đơn vị tiền khác nhau **không được dùng cấu hình lẫn nhau**.
7. Không dùng text output để tính lại amount hoặc quy đổi currency.

## 12. Chương trình Java 10+ hoàn chỉnh đã biên dịch và chạy

Tạo tệp **`ExplicitCurrencyLocaleDemo.java`** (lưu source dưới UTF-8):

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;
import java.util.Objects;

public final class ExplicitCurrencyLocaleDemo {
    static final class Money {
        final BigDecimal amount;
        final Currency currency;

        Money(String amount, String isoCode) {
            this.amount = new BigDecimal(amount);
            this.currency = Currency.getInstance(isoCode);
        }
    }

    static NumberFormat newFormatter(
            Locale displayLocale, Currency currency,
            int fractionDigits, RoundingMode roundingMode) {
        Objects.requireNonNull(displayLocale);
        Objects.requireNonNull(currency);
        Objects.requireNonNull(roundingMode);
        if (fractionDigits < 0 || fractionDigits > 12) {
            throw new IllegalArgumentException("fractionDigits out of range");
        }
        NumberFormat formatter =
                NumberFormat.getCurrencyInstance(displayLocale);
        formatter.setCurrency(currency);
        formatter.setMinimumFractionDigits(fractionDigits);
        formatter.setMaximumFractionDigits(fractionDigits);
        formatter.setRoundingMode(roundingMode);
        formatter.setGroupingUsed(true);
        return formatter;
    }

    static String showSpaces(String formatted) {
        return formatted.replace("\u00A0", "<NBSP>")
                .replace("\u202F", "<NNBSP>");
    }

    static String show(Money money, Locale locale, int fractionDigits,
                       RoundingMode roundingMode) {
        NumberFormat formatter = newFormatter(
                locale, money.currency, fractionDigits, roundingMode);
        return showSpaces(formatter.format(money.amount));
    }

    public static void main(String[] args) {
        Locale viVN = Locale.forLanguageTag("vi-VN");
        Locale enUS = Locale.forLanguageTag("en-US");
        Locale deDE = Locale.forLanguageTag("de-DE");

        Money usd = new Money("1234567.895", "USD");
        Money vnd = new Money("1234567.5", "VND");

        System.out.println("usdIso=" + usd.currency.getCurrencyCode()
                + ", defaultDigits=" + usd.currency.getDefaultFractionDigits());
        System.out.println("vndIso=" + vnd.currency.getCurrencyCode()
                + ", defaultDigits=" + vnd.currency.getDefaultFractionDigits());

        System.out.println("USD/en-US="
                + show(usd, enUS, 2, RoundingMode.HALF_UP));
        System.out.println("USD/de-DE="
                + show(usd, deDE, 2, RoundingMode.HALF_UP));
        System.out.println("USD/vi-VN="
                + show(usd, viVN, 2, RoundingMode.HALF_UP));
        System.out.println("VND/vi-VN="
                + show(vnd, viVN, 0, RoundingMode.HALF_UP));

        NumberFormat switched = NumberFormat.getCurrencyInstance(enUS);
        switched.setCurrency(vnd.currency);
        System.out.println("switchCurrencyCode="
                + switched.getCurrency().getCurrencyCode());
        System.out.println("fractionDigitsAfterSwitch="
                + switched.getMinimumFractionDigits()
                + "/" + switched.getMaximumFractionDigits());

        Money tie = new Money("1.005", "USD");
        System.out.println("HALF_EVEN=" +
                show(tie, enUS, 2, RoundingMode.HALF_EVEN));
        System.out.println("HALF_UP=" +
                show(tie, enUS, 2, RoundingMode.HALF_UP));

        String us = show(usd, enUS, 2, RoundingMode.HALF_UP);
        String de = show(usd, deDE, 2, RoundingMode.HALF_UP);
        System.out.println("sameAmount=" +
                usd.amount.equals(new BigDecimal("1234567.895")));
        System.out.println("sameCodeDifferentLocale="
                + (!us.equals(de)));
    }
}
```

Biên dịch và chạy với JDK có hỗ trợ `--release 10`:

```bash
javac -encoding UTF-8 --release 10 ExplicitCurrencyLocaleDemo.java
java ExplicitCurrencyLocaleDemo
```

Stdout **đã kiểm chứng trên môi trường Java của bài**, với NBSP được thay thành marker khi in:

```text
usdIso=USD, defaultDigits=2
vndIso=VND, defaultDigits=0
USD/en-US=$1,234,567.90
USD/de-DE=1.234.567,90<NBSP>$
USD/vi-VN=1.234.567,90<NBSP>US$
VND/vi-VN=1.234.568<NBSP>₫
switchCurrencyCode=VND
fractionDigitsAfterSwitch=2/2
HALF_EVEN=$1.00
HALF_UP=$1.01
sameAmount=true
sameCodeDifferentLocale=true
```

**Đừng xem các dấu phân nhóm, symbol và marker khoảng trắng trong stdout là hợp đồng cứng cho mọi JDK/provider locale.** JDK/CLDR có thể cập nhật dữ liệu localization. Những giá trị được kỳ vọng bền vững về mặt ý nghĩa là *amount không đổi*, *currency code được chọn đúng*, *số chữ số lẻ khi cấu hình tường minh*, và *kết quả số học theo chính sách rounding*.

Giải thích các nhóm:

1. `USD` báo 2 và `VND` báo 0 fraction digits mặc định, phù hợp dữ liệu currency ở môi trường đã test.
2. Ba dòng `USD/...` đều dùng **một amount BigDecimal và currency code USD** nhưng cách hiển thị khác nhau theo locale; không có chuyển đổi ngoại tệ.
3. `VND/vi-VN` cấu hình 0 chữ số lẻ và `HALF_UP` nên `1234567.5` hiển thị thành `1.234.568` cùng ký hiệu VND phù hợp locale.
4. `switchCurrencyCode=VND` nhưng `fractionDigitsAfterSwitch=2/2` cho thấy chỉ dùng `setCurrency(VND)` **không cập nhật** chữ số thập phân của formatter US đã tạo.
5. `HALF_EVEN=$1.00` và `HALF_UP=$1.01` xác nhận rounding khác nhau ở điểm tie `1.005`. Dữ liệu gốc `BigDecimal` không đổi.
6. `sameAmount=true` chứng minh code trình bày không thay đổi amount; `sameCodeDifferentLocale=true` cho thấy cùng currency có thể có chuỗi hiển thị khác nhau.

Lưu ý ví dụ hạn chế `fractionDigits` từ 0 đến 12 bằng **quy tắc minh họa của ứng dụng**, không phải giới hạn chung của `NumberFormat` hoặc ISO 4217. Hệ thống thực tế cần giới hạn theo domain và kiểu dữ liệu đang xử lý.

## 13. Khi nào chọn chính sách số lẻ mặc định và khi nào cần override?

Có thể thiết kế helper lấy mặc định từ metadata:

```java
static int defaultDigitsFor(java.util.Currency currency) {
    int digits = currency.getDefaultFractionDigits();
    if (digits < 0) {
        throw new IllegalArgumentException(
                "No default fraction digits for currency "
                + currency.getCurrencyCode());
    }
    return digits;
}
```

Rồi dùng:

```java
int digits = defaultDigitsFor(currency);
var fmt = newMoneyFormat(
        userLocale, currency, digits,
        java.math.RoundingMode.HALF_EVEN);
```

Ưu điểm là giảm cấu hình lặp cho USD/VND/EUR/JPY. Nhưng hãy cân nhắc những trường hợp cần override có chủ đích:

- Giới hạn thập phân theo loại chứng từ hoặc quy định ngành.
- Giá trên mỗi đơn vị hàng hóa có thập phân cao hơn số tiền thanh toán.
- Mức phí/tỷ giá dùng độ chính xác nội bộ cao hơn.
- Đối tác thanh toán yêu cầu định dạng minor unit khác dữ liệu ISO trong một bối cảnh cụ thể.
- Dữ liệu lịch sử theo một thời điểm mà chính sách đang dùng hiện tại không còn phản ánh chính xác.

Khi đã override, ghi policy cùng quy tắc tính toán/hiển thị và test. Đừng rải hằng số 0, 2, 3 ở nhiều chỗ khác nhau rồi khó giải thích nguồn gốc.

## 14. Số âm, giá trị 0 và số rất lớn

UI tiền tệ thường phải xử lý:

```java
var negative = new java.math.BigDecimal("-1250.50");
var zero = java.math.BigDecimal.ZERO;
var large = new java.math.BigDecimal("12345678901234567890.123456");
```

Khi kiểm thử, cần chú ý:

- **Số âm:** có thể dùng dấu trừ hoặc một pattern khác theo locale. Đừng tự nối `"-"` phía trước một chuỗi đã có currency symbol, vì thứ tự và dấu có thể sai.
- **Zero:** chính sách fraction digits có thể dẫn đến `$0.00` hoặc biểu diễn tương ứng theo locale. Không coi số 0 là “không có tiền tệ”.
- **Số lớn:** tránh ép `BigDecimal` sang `double` trước khi format. Một số số nguyên lớn không thể giữ chính xác trong kiểu double.
- **Số lẻ nhỏ:** `0.004` có thể hiển thị thành `0.00` nếu chỉ hiện hai chữ số. Điều này **không chứng minh giá trị lưu là 0**.
- **Âm không hoặc số học chuyên biệt:** chính sách hiển thị số âm rất nhỏ được làm tròn về 0 cần được thống nhất với quy tắc kế toán và trình bày.

Đừng test số âm bằng cách kiểm tra nhất thiết có dấu ASCII `'-'` ở ký tự đầu. Thứ tự prefix/suffix và ký hiệu trừ có thể là một phần dữ liệu locale.

## 15. Formatting không phải persistence hoặc validation tiền tệ

Chuỗi được format có mục tiêu **trình bày cho con người**:

```text
$1,234.50
1.234,50 US$
1.234,50 $
```

Nó không phải dạng lưu trữ canonical độc lập với locale, và không phải chứng từ đủ để phân biệt mọi đồng tiền.

### Lưu trữ/truyền dữ liệu

Ưu tiên một cấu trúc như:

```json
{
  "amount": "1234.50",
  "currency": "USD"
}
```

Dạng JSON này chỉ là **ví dụ thiết kế payload**, không phải định dạng bắt buộc của Java SE. `amount` là chuỗi thập phân canonical để tránh rủi ro số dấu phẩy động trong các hệ thống có JSON number; mã currency tách riêng.

Nếu hệ thống dùng “minor units” dưới dạng integer, phải định nghĩa rõ scale của từng currency/giao dịch. Không giả định mọi currency đều có hai minor digits.

### Input/parsing

`NumberFormat.parse(...)` có thể đọc một số dạng chuỗi theo locale, nhưng không nên dùng nó như **bộ xác thực duy nhất** cho nghiệp vụ tiền hoặc suy ra mã ISO an toàn từ ký hiệu `$`.

Có thể có các vấn đề:

- Parser mặc định có thể chấp nhận một **prefix hợp lệ** của string rồi bỏ phần dư theo quy tắc parse lenient.
- Cùng một ký tự phân cách mang nghĩa thập phân hoặc hàng nghìn tùy locale.
- Ký hiệu `$` không xác định duy nhất currency.
- Khi parse về `Number` thông thường, phải kiểm tra kiểu/độ chính xác của kết quả trước khi đưa vào `BigDecimal` hoặc hệ thống tiền.

Nếu form cho phép nhập số tiền từ người dùng, nên nhận **currency code riêng** và parse/validate amount theo một locale/contract xác định, kiểm tra toàn bộ input được tiêu thụ, range và scale; khi truyền qua API máy–máy, ưu tiên định dạng decimal canonical thay vì chuỗi trình bày locale.

## 16. Kiểm thử: những gì nên assert, những gì không nên đóng đinh

Một bộ test tốt tách **hành vi ổn định** khỏi **thông tin localization có thể cập nhật**.

| Ca | Input | Điều cần kiểm tra |
| --- | --- | --- |
| T1 | USD + en-US | Currency code đúng, số lẻ và rounding đúng |
| T2 | USD + de-DE | Amount/currency giữ nguyên, pattern theo locale Đức |
| T3 | USD + vi-VN | Không tự đổi USD thành VND chỉ vì locale |
| T4 | VND + vi-VN | 0 chữ số lẻ theo policy, giá trị hiển thị được làm tròn |
| T5 | `setCurrency(VND)` trên format US | Fraction digits **không tự đổi** |
| T6 | `1.005 USD` với HALF_EVEN/HALF_UP | Kết quả làm tròn khác nhau có chủ đích |
| T7 | Giá trị BigDecimal lớn | Không mất precision do ép double |
| T8 | Số âm/0/giá trị nhỏ | Không tự ghép prefix/suffix, format đúng |
| T9 | Currency code không hợp lệ | Validation báo lỗi rõ, không tự gán mã khác |
| T10 | Currency có default fraction digits -1 | Policy riêng, không đưa -1 làm số lẻ |
| T11 | Chuỗi chứa NBSP/NNBSP | UI vẫn đúng; test không nhầm với U+0020 |
| T12 | Nhiều request đồng thời | Không dùng chung formatter mutable bị ghi cấu hình qua lại |
| T13 | Locale format thay đổi theo JDK/CLDR | Test contract quan trọng không phụ thuộc chuỗi symbol rập khuôn |
| T14 | Payload amount + currency | Tái dựng đúng amount/code mà không phải parse chuỗi tiền format |

### Ví dụ assert về số lẻ sau khi set currency

```java
var f = java.text.NumberFormat.getCurrencyInstance(
        java.util.Locale.US);
f.setCurrency(java.util.Currency.getInstance("VND"));

if (f.getMinimumFractionDigits() != 2
        || f.getMaximumFractionDigits() != 2) {
    throw new AssertionError("Unexpected initial US currency format");
}

f.setMinimumFractionDigits(0);
f.setMaximumFractionDigits(0);
if (f.getMinimumFractionDigits() != 0
        || f.getMaximumFractionDigits() != 0) {
    throw new AssertionError("Currency fraction policy not applied");
}
```

Phần assert về `2/2` trong ví dụ này kiểm tra **môi trường được biết đang dùng pattern US thông thường**. Với các locale provider tùy biến hoặc dữ liệu locale khác, không nên biến con số khởi tạo đó thành invariant cho mọi implementation. Bất biến quan trọng là **`setCurrency` không được định nghĩa để tự cập nhật min/max fraction digits**; sau khi đặt policy 0/0, formatter phải phản ánh cấu hình đó trên implementation phù hợp.

### Kỳ vọng locale output phải được quản lý theo môi trường

Có thể làm golden-output tests cho một JDK và cấu hình locale-provider được cố định trong build. Nếu nâng JDK/CLDR, các dạng symbol, spacing hoặc negative pattern có thể thay đổi mà không phải lỗi của nghiệp vụ. Tách test logic tiền (code, amount, scale, rounding) khỏi snapshot hiển thị theo locale, hoặc cập nhật fixture có kiểm soát khi thay data version.

Trong test hiển thị, nếu cần biết chính xác dấu cách đang có, in code point của chuỗi thay vì chỉ dựa vào mắt nhìn.

## 17. Thread safety và lifecycle của NumberFormat

`NumberFormat` và các implementation như `DecimalFormat` là **mutable**; Javadoc khuyến nghị không chia sẻ chúng đồng thời nếu không có đồng bộ hóa phù hợp.

Đây là lỗi dễ gặp trên web server:

```java
// Không an toàn khi nhiều request ghi currency/locale khác nhau:
static final java.text.NumberFormat SHARED =
        java.text.NumberFormat.getCurrencyInstance(
                java.util.Locale.US);
```

Một request có thể đổi `SHARED.setCurrency(USD)`, request khác đổi sang VND, request thứ ba đổi fraction digits. Chuỗi format có thể lấy cấu hình của request khác hoặc gặp race condition.

Các lựa chọn tốt hơn:

1. **Tạo formatter mới** cho mỗi operation hoặc request (mẫu dễ hiểu nhất).
2. Khi phải tối ưu, quản lý formatter **theo thread** hoặc sử dụng pool với ownership và reset cấu hình chính xác; đây là bài toán concurrency phải kiểm chứng, không nên tối ưu sớm.
3. Không đặt `NumberFormat` mutable vào singleton rồi tự đổi cấu hình theo từng người xem.
4. Cache **định nghĩa policy bất biến** (locale tag, currency code, fraction digits, rounding mode) rồi tạo instance formatter từ policy đó nếu cần.
5. Nếu có cache formatter thật sự, cơ chế đồng bộ và invalidation phải bảo đảm không chia sẻ mutable state sai cách.

Tương tự, thay đổi `Locale.setDefault` ở request thread không phải một chiến lược tách biệt locale. Default locale là **trạng thái chung của JVM**.

## 18. Những sai lầm điển hình

**Sai lầm 1 — Nghĩ Locale.VIETNAM luôn có nghĩa VND.** Locale chỉ mô tả quy ước hiển thị/ngôn ngữ/vùng của người xem. Amount giao dịch có thể là USD, EUR hay đơn vị khác.

**Sai lầm 2 — Gọi `NumberFormat.getCurrencyInstance()` không tham số trên server đa quốc gia.** Không bảo đảm dùng locale của người xem; nó dựa vào mặc định của process.

**Sai lầm 3 — Chỉ gọi `setCurrency(VND)` rồi kỳ vọng tự giảm từ 2 chữ số lẻ còn 0.** Javadoc nói không cập nhật min/max fraction digits. Cần đặt tường minh.

**Sai lầm 4 — Coi `Currency.getDefaultFractionDigits()` là luật giao dịch tuyệt đối.** Đây là metadata mặc định; yêu cầu kế toán, thanh toán hoặc lịch sử có thể khác.

**Sai lầm 5 — Trộn `double` và `BigDecimal` tùy tiện.** Có thể gây sai số thập phân; dùng BigDecimal từ String/canonical input khi làm việc với tiền.

**Sai lầm 6 — Cho rằng format bằng EUR nghĩa là đã quy đổi từ USD.** Currency chỉ là đơn vị hiển thị; phải có phép FX riêng nếu cần đổi giá trị tiền.

**Sai lầm 7 — Lấy dấu `$` làm mã định danh.** Ký hiệu có thể dùng chung hoặc phụ thuộc locale; mã ISO là dữ liệu nghiệp vụ cần giữ riêng.

**Sai lầm 8 — Tự ghép `"$" + String.format("%.2f", ...)`.** Vị trí, group, decimal, dấu âm và currency symbol khác nhau theo locale. Dùng currency formatter.

**Sai lầm 9 — So sánh output có space thường với output chứa NBSP/NNBSP.** Nhìn giống nhưng Unicode khác. Test phải phân biệt chính xác ký tự.

**Sai lầm 10 — Ép kết quả format trở lại BigDecimal để lưu số tiền.** Đây là text dành cho UI, không phải canonical representation. Lưu amount và ISO code riêng.

**Sai lầm 11 — Dùng chung formatter mutable giữa các request.** Có nguy cơ race/cấu hình chéo; tạo formatter mới hoặc quản lý ownership rõ.

**Sai lầm 12 — Test chỉ với USD/en-US.** Không phát hiện sai dấu phân nhóm, vị trí currency và ngữ cảnh đa tiền. Cần ít nhất một locale khác và một đồng tiền có số lẻ mặc định khác.

**Sai lầm 13 — Nhầm hai loại làm tròn.** Format rounded text không đồng nghĩa khoản tiền giao dịch đã được làm tròn theo chính sách kế toán; hai bước có thể phải tách.

**Sai lầm 14 — Cho rằng ký hiệu và dấu cách giữ nguyên mãi qua mọi JDK.** Dữ liệu locale có thể được cập nhật; golden tests cần scope cụ thể.

**Sai lầm 15 — Quên xử lý mã currency không hợp lệ hoặc currency đặc biệt có `-1` default fraction digits.** Không ngầm đổi sang USD hay dùng -1 làm số chữ số lẻ.

## 19. Checklist code review

- [ ] Số tiền được lưu/tính dưới dạng decimal chính xác (ví dụ BigDecimal), không phải text đã có dấu tiền.
- [ ] Mã currency là dữ liệu rõ ràng đi kèm amount, không được suy từ locale người xem.
- [ ] Locale được lấy từ preference/request đã validate và truyền trực tiếp vào `NumberFormat.getCurrencyInstance(locale)`.
- [ ] Không dùng `Locale.setDefault` để đổi locale theo request.
- [ ] Formatter đặt `Currency` từ mã ISO 4217 của giao dịch.
- [ ] Fraction digits được chọn tường minh: theo metadata currency hoặc policy nghiệp vụ có thể kiểm chứng.
- [ ] Xử lý trường hợp `getDefaultFractionDigits() == -1`.
- [ ] `RoundingMode` được quyết định và được test, nhất là với số nằm ở điểm hòa.
- [ ] Không nhầm format currency với phép quy đổi tỷ giá.
- [ ] Không ép BigDecimal sang double khi format giá trị lớn hoặc chính xác cao.
- [ ] Mã currency và amount được serialize riêng khi giao tiếp giữa hệ thống.
- [ ] Với nhiều currency, ký hiệu có thể gây nhầm đã được xử lý ở thiết kế UI.
- [ ] Các test bao gồm USD, VND, các locale en-US/de-DE/vi-VN hoặc tương đương.
- [ ] Test không phụ thuộc một cách mù quáng vào U+0020, U+00A0 hoặc U+202F.
- [ ] NumberFormat mutable không bị chia sẻ không đồng bộ.
- [ ] Có test số âm, số 0, số nhỏ, số lớn, locale/provider và currency code không hợp lệ.
- [ ] Giới hạn số chữ số của helper là business rule minh bạch, không gán nhầm cho giới hạn Java SE.
- [ ] Nếu format output được dùng cho tài liệu pháp lý/kế toán, versioning chính sách và locale data được quản lý tương ứng.

## 20. Câu hỏi tự kiểm tra và đáp án

**1.** Người dùng ở Việt Nam xem đơn hàng USD. Chỉ truyền `Locale.forLanguageTag("vi-VN")` cho currency formatter có đảm bảo hiển thị đúng USD không?

**Đáp án:** Không. Locale vi-VN có thể gắn với currency mặc định khác. Phải đặt `Currency.getInstance("USD")` từ dữ liệu giao dịch.

**2.** `setCurrency(VND)` trên currency formatter US có tự chuyển fraction digits 2 thành 0 không?

**Đáp án:** Không. Javadoc quy định `setCurrency` không tự cập nhật min/max fraction digits. Phải đặt `setMinimumFractionDigits(0)` và `setMaximumFractionDigits(0)` theo policy nếu muốn 0 chữ số.

**3.** Dùng cùng amount `1234.50` và cùng USD, nhưng hiển thị theo en-US/de-DE có thể tạo hai chuỗi khác nhau không?

**Đáp án:** Có. Dấu phân nhóm, dấu thập phân, vị trí và hình thức ký hiệu tiền có thể khác. Amount và currency không đổi.

**4.** Lấy ký hiệu `$` từ UI có thể suy ra duy nhất đó là USD không?

**Đáp án:** Không. Nhiều currency có ký hiệu tương tự, và cùng currency có thể được thể hiện khác theo locale. Giữ ISO currency code.

**5.** `new BigDecimal(0.1)` có giống `new BigDecimal("0.1")` không?

**Đáp án:** Không nhất thiết. Constructor nhận double có thể ghi lại sai số biểu diễn nhị phân; constructor nhận String giữ nguyên decimal chính xác.

**6.** Với `1.005 USD`, hai chính sách `HALF_EVEN` và `HALF_UP` có thể cho hai chuỗi hiển thị khác nhau không?

**Đáp án:** Có. Ví dụ 2 chữ số lẻ lần lượt là `$1.00` và `$1.01` trên locale US trong demo đã chạy.

**7.** `Currency.getDefaultFractionDigits()` trả -1 thì có nên đặt cả min/max fraction digits bằng -1 không?

**Đáp án:** Không. Đó là trường hợp metadata không cung cấp số lẻ thông thường cho pseudo-currency; cần business policy rõ ràng.

**8.** `NumberFormat.format(BigDecimal)` có tự thay đổi số tiền trong object BigDecimal không?

**Đáp án:** Không. Nó tạo chuỗi hiển thị; nếu formatter làm tròn chữ số, giá trị gốc vẫn giữ nguyên.

**9.** Một test hiển thị tiền gặp khác biệt `U+00A0` và `U+0020`, phải làm gì?

**Đáp án:** Xác định quy tắc locale/provider đã dùng, inspect code point khi debug; không tự thay đổi chuỗi format nếu UI cần giữ khoảng trắng không ngắt dòng. Golden-output test phải tương ứng môi trường được quản lý.

**10.** Hai request dùng chung một NumberFormat, một request đổi USD, một request đổi VND. Có an toàn không?

**Đáp án:** Không nếu không đồng bộ hoặc tách ownership. NumberFormat mutable và không được bảo đảm thread-safe; nên tạo formatter riêng cho mỗi operation/request.

**11.** Dùng `setCurrency(EUR)` khi amount thực tế là USD có thực hiện đổi USD→EUR không?

**Đáp án:** Không. Nó chỉ thay đơn vị/ký hiệu format; đổi ngoại tệ cần phép tính tỷ giá độc lập và policy làm tròn giao dịch.

**12.** Currency formatter có phù hợp để lưu amount trong database như một chuỗi `"1.234,50 €"` không?

**Đáp án:** Không nên. Lưu amount decimal canonical và mã currency riêng; chuỗi theo locale chỉ dùng cho trình bày, không phải định dạng máy–máy ổn định.

**13.** Khi một hệ thống chỉ có `Locale.forLanguageTag("vi")`, có thể lấy `Currency.getInstance(locale)` và coi là VND không?

**Đáp án:** Không nên. Locale chỉ có ngôn ngữ không gắn chắc với một quốc gia/đơn vị tiền. Dùng mã currency từ giao dịch.

**14.** Muốn giảm thiểu test hỏng khi nâng JDK, nên assert điều gì?

**Đáp án:** Test riêng invariants của amount, currency code, fraction digits, rounding và không đổi dữ liệu gốc; giữ golden-output tests theo locale với JDK/CLDR version cố định, có quy trình cập nhật khi dữ liệu bản địa hóa thay đổi.

## 21. Tài liệu Java chính thức còn hiệu lực

- [Java SE 25 — NumberFormat](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/NumberFormat.html): `getCurrencyInstance(Locale)`, chọn locale, `setCurrency`, fraction digits, rounding mode và tính đồng bộ.
- [Java SE 25 — DecimalFormat](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/DecimalFormat.html): chi tiết pattern, ký hiệu và đặc biệt việc `setCurrency` **không tự cập nhật số lẻ**.
- [Java SE 25 — Currency](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Currency.html): ISO currency code, ký hiệu bản địa hóa, `getDefaultFractionDigits` có thể trả -1, gợi ý BigDecimal.
- [Java SE 25 — Locale](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Locale.html): ngôn ngữ/khu vực, language tag, FORMAT locale và Unicode locale extensions.
- [Java SE 25 — BigDecimal](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html): decimal arithmetic và xử lý chính xác/làm tròn.
- [Java SE 25 — RoundingMode](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/RoundingMode.html): quy tắc `HALF_EVEN`, `HALF_UP` và các mode khác.
- [Java SE 25 — DecimalFormatSymbols](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/DecimalFormatSymbols.html): dấu phân nhóm, dấu thập phân và ký hiệu currency theo locale.

**Kết luận:** Một chuỗi tiền tệ đúng phải được tạo từ **amount chính xác + currency code của giao dịch + locale của người xem + chính sách số lẻ/làm tròn**. `NumberFormat.getCurrencyInstance(locale)` và `Currency.getInstance(code)` cung cấp những phần đó trong Java 10+; việc đặt currency **không tự cập nhật độ chính xác** và **không thực hiện quy đổi tỷ giá**. Thiết kế tường minh giúp hiển thị đúng với nhiều quốc gia, tránh sai số và có bài test đáng tin cậy.
