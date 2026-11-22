# Giới hạn suy ra tiền tệ chỉ từ ngôn ngữ hoặc khu vực trong Java

## 1. Ngôn ngữ, khu vực và đơn vị tiền tệ là ba khái niệm khác nhau

Một ứng dụng quốc tế hóa thường biết **ngôn ngữ giao diện** và **khu vực** của người dùng. Tuy nhiên, hai thông tin đó **không đủ để khẳng định đồng tiền của một giao dịch**. Java cung cấp các API hữu ích để lấy *đồng tiền thường gắn với một khu vực*, nhưng kết quả ấy là gợi ý theo dữ liệu của runtime, không phải một quyết định tài chính hoàn chỉnh.

Cần phân biệt:

| Thông tin | Ví dụ | Trả lời câu hỏi |
| --- | --- | --- |
| Ngôn ngữ | `vi`, `en`, `es` | Người dùng đọc/nghe ngôn ngữ nào? |
| Khu vực của `Locale` | `VN`, `US`, `GB` | Quy ước văn hóa/định dạng nào được ưu tiên? |
| Mã tiền tệ | `VND`, `USD`, `GBP`, `EUR` | Số tiền có đơn vị kế toán/giao dịch nào? |
| Giá trị tiền | `125.50` cùng `USD` | Giao dịch thực sự có giá trị bao nhiêu và bằng tiền gì? |
| Tỷ giá và ngày hiệu lực | USD → VND ở một thời điểm | Nếu phải quy đổi, sử dụng tỷ giá nào? |

Các cặp sau đều hợp lý về mặt sản phẩm:

- Giao diện **tiếng Việt** hiển thị giá của một dịch vụ quốc tế bằng **USD**.
- Giao diện **tiếng Anh** tại Việt Nam hiển thị phí bằng **VND**.
- Người dùng sống tại Anh mua dịch vụ có **đơn vị thanh toán EUR**.
- Người dùng ở Mỹ đang xem giá **JPY** hoặc **EUR** và không muốn tự động quy đổi.
- Một nhà bán hàng niêm yết bằng một đồng tiền nhưng cổng thanh toán quyết toán bằng đồng tiền khác.

**Nguyên tắc:** `Locale` điều khiển *cách biểu diễn* và gợi ý theo vùng; `Currency` cùng giá trị số xác định *đơn vị của khoản tiền*. Không được suy luận `currency = language` hay `currency = userLocale.getCountry()` trong dữ liệu nghiệp vụ.

## 2. Java có thể suy ra điều gì từ Locale?

Java SE 17 có hai phương thức thường gặp trong `java.util.Currency`:

~~~java
Currency fromRegion = Currency.getInstance(Locale.US);
Currency explicit = Currency.getInstance("USD");
~~~

Đây là **hai câu lệnh minh họa trong một phương thức Java**, yêu cầu `import java.util.Currency;` và `import java.util.Locale;`. Chương trình độc lập nằm ở mục 7.

### 2.1. Currency.getInstance(Locale): gợi ý theo khu vực

`Currency.getInstance(locale)` xác định currency từ **country/region** trong locale theo dữ liệu của JDK. Với locale thông thường, **language** và **variant** không quyết định đồng tiền. Ngoại lệ quan trọng là các Unicode locale extension `cu` và `rg`, được phân tích ở mục 3.

Ví dụ kinh điển:

| Locale đầu vào | Khu vực liên quan | Mã thường được trả về | Ý nghĩa |
| --- | --- | --- | --- |
| `en-US` | Mỹ | `USD` | Tiếng Anh tại Mỹ |
| `es-US` | Mỹ | `USD` | Tiếng Tây Ban Nha tại Mỹ, **vẫn** USD |
| `en-GB` | Anh | `GBP` | Cùng tiếng Anh nhưng khu vực khác |
| `vi-VN` | Việt Nam | `VND` | Gợi ý tiền tệ theo VN |
| `en` | Không chỉ định country | Không xác định được theo region; thường ném `IllegalArgumentException` | Ngôn ngữ **không phải** mã khu vực |
| `en-AQ` | Nam Cực | `null` | Vùng không có đồng tiền được gán theo API |

Các kết quả là ví dụ cho JDK có dữ liệu ISO tương ứng, **không phải lời khẳng định rằng mọi hóa đơn phát sinh trong vùng ấy đều thanh toán bằng đồng đó**.

Theo hợp đồng Java SE 17, `Currency.getInstance(Locale)` có thể:

1. Trả về một `Currency` có mã ISO 4217.
2. Trả về `null` nếu lãnh thổ không có currency được gán, ví dụ Antarctica (`AQ`).
3. Ném `IllegalArgumentException` khi country của locale không phải mã ISO 3166 được hỗ trợ hoặc không đủ thông tin để xác định; vì vậy `Locale.forLanguageTag("en")` không phải cơ sở đầy đủ để lấy đồng tiền.
4. Ném `NullPointerException` nếu truyền `locale == null`.

Trường hợp thiếu khu vực cần được giải quyết bằng **dữ liệu giao dịch hoặc một chính sách chọn tiền tệ rõ ràng**, không tự đoán “người nói tiếng Anh chắc chắn dùng USD”.

### 2.2. Currency.getInstance(String): dùng mã được xác định rõ

`Currency.getInstance("USD")` nhận **mã tiền tệ ISO 4217**, phù hợp khi hệ thống đã biết đơn vị qua hợp đồng, bảng giá, lựa chọn thanh toán hoặc bản ghi giao dịch.

~~~java
Currency currency = Currency.getInstance("EUR");
System.out.println(currency.getCurrencyCode()); // EUR
~~~

Đây là **đoạn minh họa**, yêu cầu import `Currency`. Mã không được runtime hỗ trợ sẽ gây `IllegalArgumentException`; input `null` gây `NullPointerException`.

API chỉ xác nhận rằng runtime biết mã. Nó không tự kiểm tra **đồng tiền có đang được phép dùng trong giao dịch này, được cổng thanh toán hỗ trợ, còn lưu hành tại ngày giao dịch, hay có tỷ giá cho cặp tiền hay không**. Những điều kiện đó phải do nghiệp vụ và hệ thống thanh toán xử lý.

### 2.3. Kết quả theo khu vực có thể đổi theo thời gian

Tài liệu `Currency.getInstance(Locale)` nêu rõ kết quả **có thể thay đổi theo thời gian khi một nước thay đổi đồng tiền**. JDK mang dữ liệu ISO và các quy tắc hiệu lực; một country không có bảo đảm luôn được ánh xạ đến một currency duy nhất cho mọi thời điểm lịch sử/tương lai.

Hệ quả quan trọng:

- **Không tính lại currency của hóa đơn cũ** bằng cách gọi `Currency.getInstance(customerLocale)` ở thời điểm hiện tại.
- Đã xác nhận giao dịch dùng currency nào thì lưu **mã currency** ngay trên đơn hàng/chứng từ, bên cạnh `BigDecimal` amount.
- Nếu nghiệp vụ phải tái hiện quy tắc tiền tệ **theo ngày hiệu lực lịch sử**, cần nguồn dữ liệu và chính sách phiên bản phù hợp; `Currency.getInstance(Locale)` không phải API tra cứu tỷ giá hoặc currency theo một ngày tùy chọn.
- Dữ liệu runtime có thể được cập nhật qua các bản JDK. Kiểm thử tích hợp cần kiểm soát runtime khi phụ thuộc ánh xạ mã cụ thể.

## 3. Ngoại lệ quan trọng: Unicode locale extension cu và rg

Không nên nói một cách tuyệt đối rằng Java **luôn bỏ qua mọi phần khác ngoài country**. Java SE 17 hỗ trợ **Unicode locale extension** trong language tag:

- `u-cu-xxx` yêu cầu **currency** dạng mã ISO 4217. Ví dụ `en-US-u-cu-eur` thể hiện giao diện tiếng Anh/Mỹ nhưng ưu tiên Euro trong metadata locale.
- `u-rg-xxzzzz` cho phép **region override** cho các dịch vụ bản địa hóa. Ví dụ `en-US-u-rg-gbzzzz` có country cơ sở là US nhưng region override là GB.

Kết quả cụ thể theo Java 17:

~~~text
en-US                 -> USD
es-US                 -> USD
en-GB                 -> GBP
en-US-u-cu-eur        -> EUR
en-US-u-rg-gbzzzz     -> GBP
~~~

Nếu có cả `cu` lẫn `rg`, currency được chỉ định bởi `cu` được ưu tiên trước kết quả gián tiếp từ region override `rg`.

**Lưu ý về an toàn và nghiệp vụ:** các extension là **gợi ý/thiết lập trong Locale**, không phải bằng chứng khách hàng đã chọn đổi đồng tiền thanh toán. Một request tự khai báo `u-cu-eur` **không được tự ý thay đổi currency** của giá hàng hóa hoặc đơn đã được báo bằng USD. Nếu sản phẩm cho phép người dùng chọn currency, hãy ghi nhận lựa chọn qua một trường input có kiểm tra quyền và hỗ trợ, không dùng language tag như kênh âm thầm sửa giao dịch.

Ngoài ra, `Locale.forLanguageTag` là parser có thể chấp nhận một phần tag khi gặp đoạn sai cú pháp. Với input locale không tin cậy cần kiểm tra cấu trúc nghiêm ngặt, dùng `new Locale.Builder().setLanguageTag(raw).build()` và xử lý `IllformedLocaleException`, sau đó mới áp dụng chính sách hỗ trợ sản phẩm. **Đúng cú pháp locale không chứng minh currency nghiệp vụ hợp lệ.**

## 4. Những giới hạn thực tế của việc suy ra từ khu vực

### 4.1. Một khu vực không có nghĩa mọi giao dịch dùng một currency

Một quốc gia/khu vực có thể dùng nhiều đơn vị trong thanh toán, niêm yết, ngoại thương hoặc giao dịch trực tuyến. Đồng tiền **được sử dụng trong một hợp đồng cụ thể** có thể do nhà cung cấp, khách hàng, chính sách thuế, ngân hàng hoặc cổng thanh toán quyết định.

Ví dụ:

~~~text
Customer locale  : vi-VN
Product price    : 50.00 USD
Invoice currency : USD
Display language : vi
Settlement currency (nếu có chuyển đổi) : VND
~~~

Trong tình huống đó, nếu gọi `Currency.getInstance(Locale.forLanguageTag("vi-VN"))` để thay `USD` trên giá sản phẩm thành `VND`, hệ thống sẽ **gắn sai đơn vị cho cùng trị số 50.00**, không phải quy đổi. Giá 50 USD không bao giờ được biến thành “50 VND” chỉ bằng việc đổi ký hiệu.

### 4.2. Người dùng, cửa hàng và tài khoản có thể ở các vùng khác nhau

Cần phân biệt tối thiểu:

| Nguồn dữ liệu | Tác dụng chính | Có đủ quyết định currency giao dịch không? |
| --- | --- | --- |
| `Accept-Language` trên HTTP | Ưu tiên ngôn ngữ và locale hiển thị | Không |
| Quốc tịch/ngôn ngữ của khách hàng | Thông tin người dùng | Không |
| Vị trí IP/GPS | Gợi ý vị trí hiện tại | Không |
| Quốc gia giao hàng | Thuế, vận chuyển và chính sách sản phẩm | Không, trừ khi chính sách quy định rõ |
| Quốc gia tài khoản/cửa hàng | Gợi ý currency bán hàng mặc định | Không cho mọi giao dịch |
| Currency đã lưu trên price quote/order | Đơn vị của số tiền báo giá/giao dịch | **Có**, theo contract giao dịch |
| Currency được cổng thanh toán xác nhận | Đơn vị capture/settlement | **Có**, trong phạm vi kết quả cổng thanh toán |

Ngay cả khi biết khu vực chính xác, **giá trị giao dịch phải có đơn vị tường minh** nếu ứng dụng xử lý tiền thật. Locale có thể được dùng để **gợi ý giá trị mặc định** tại bước tạo đơn mới theo chính sách, nhưng phải kiểm tra xem đồng tiền đó có được nhà bán hàng và phương thức thanh toán hỗ trợ hay không.

### 4.3. Không phải mọi mã trong API đều đang là legal tender

`Currency.getAvailableCurrencies()` trả tập các currency được runtime biết, **có thể bao gồm mã đã lỗi thời** theo dữ liệu Java. Vì thế:

~~~java
Set<Currency> known = Currency.getAvailableCurrencies();
~~~

Đây là đoạn minh họa, cần import `java.util.Set` và `java.util.Currency`. Việc mã nằm trong tập này chỉ nói **JDK có dữ liệu về mã**, không đảm bảo:

- Currency đang là legal tender.
- Mã đó được hệ thống ngân hàng/cổng thanh toán hỗ trợ.
- Sản phẩm cho phép niêm yết, thanh toán hoặc hoàn tiền bằng mã đó.
- Có tỷ giá giao dịch hiện hành.
- Mã đã/đang còn hiệu lực ở thời điểm lịch sử liên quan.

Trong luồng thanh toán, hãy kiểm tra **allowlist currency được hỗ trợ bởi dịch vụ** và quy định hiệu lực/nghiệp vụ riêng.

## 5. Định dạng tiền không giống quy đổi tiền

Java thường dùng `NumberFormat.getCurrencyInstance(displayLocale)` để tạo formatter có quy ước trình bày tiền phù hợp với locale.

~~~java
NumberFormat formatter =
        NumberFormat.getCurrencyInstance(Locale.GERMANY);
formatter.setCurrency(Currency.getInstance("USD"));
String shown = formatter.format(new BigDecimal("125.50"));
~~~

Đoạn minh họa trên cần các import: `java.text.NumberFormat`, `java.util.Locale`, `java.util.Currency`, `java.math.BigDecimal`.

Ở đây:

- `Locale.GERMANY` điều khiển phần **cách hiển thị**: dấu phân cách, vị trí đơn vị, quy ước ký hiệu.
- `Currency.getInstance("USD")` là đơn vị **được hiển thị**.
- `new BigDecimal("125.50")` là trị số **không thay đổi**; không có tỷ giá hoặc phép nhân/chia nào xảy ra.

**Quan trọng:** `NumberFormat.setCurrency(currency)` **không tự cập nhật** `minimumFractionDigits` và `maximumFractionDigits`. Nếu currency thay đổi từ EUR sang JPY hay ngược lại, cần kiểm soát số chữ số lẻ theo tiền tệ và yêu cầu của nghiệp vụ; không giả định một lệnh `setCurrency` đã đặt lại precision thích hợp.

`Currency.getDefaultFractionDigits()` trả số chữ số phần nhỏ mặc định theo ISO 4217; ví dụ thường là **USD: 2** và **JPY: 0**. Giá trị **-1** có thể xuất hiện với pseudo-currency. Đây là metadata về *minor unit theo ISO*, không có nghĩa mọi cổng thanh toán hoặc quy định làm tròn tiền mặt đều tuân theo số đó cho mọi loại giao dịch.

Một số giao dịch còn yêu cầu **bước làm tròn tiền mặt**, cách tính thuế hay quy định đặc thù của nhà cung cấp. Cần xác định rule đó trong domain/payment layer, rồi đặt số chữ số hiển thị riêng.

### 5.1. Ký hiệu không phải mã định danh duy nhất

`Currency.getSymbol(locale)` và `getDisplayName(locale)` chỉ phục vụ **văn bản hiển thị**. Dấu `$` có thể dùng cho nhiều currency; chữ viết tắt hoặc ký hiệu thay đổi theo locale:

~~~java
Currency usd = Currency.getInstance("USD");
String symbol = usd.getSymbol(Locale.US);
String name = usd.getDisplayName(Locale.US);
~~~

Đây là đoạn minh họa; code và tên currency ổn định hơn để định danh trong dữ liệu. **Không parse một ký hiệu `$` thành USD mà không có ngữ cảnh**, và không lưu mỗi ký hiệu thay cho mã ISO 4217 trên hóa đơn.

### 5.2. Khi thật sự cần chuyển đổi

Quy đổi tiền cần ít nhất:

- Số tiền và mã currency nguồn.
- Currency đích.
- Tỷ giá đáng tin cậy, thời điểm hiệu lực và hướng báo giá.
- Quy tắc precision/rounding, phí và các quy tắc tuân thủ liên quan.

Ví dụ cách tổ chức dữ liệu:

~~~text
originalAmount  = 125.50
originalCurrency = USD
targetCurrency  = VND
exchangeRate    = (do dịch vụ tỷ giá cung cấp, không tự đoán)
effectiveAt     = (thời điểm tỷ giá)
convertedAmount = (kết quả tính với quy tắc rounding đã chọn)
~~~

Java `Currency`, `Locale` và `NumberFormat` **không tự cung cấp tỷ giá**. Không xây luồng đổi tiền bằng cách thay ký hiệu qua `setCurrency` hoặc `Locale.setDefault`.

## 6. Mô hình dữ liệu: gắn Currency với BigDecimal từ đầu

Một mô hình nhỏ, độc lập với locale hiển thị:

~~~java
record Money(BigDecimal amount, Currency currency) {}
~~~

Đây là phần khai báo Java 17, cần import `BigDecimal`, `Currency`; trong hệ thống thật, nên có constructor kiểm tra `amount`/`currency` khác `null` và bất biến nghiệp vụ (ví dụ không cho số tiền âm khi là giá niêm yết).

**Không lưu một số tiền đơn lẻ như `125.50` rồi suy ra đơn vị từ ngôn ngữ giao diện về sau.** Nên lưu ít nhất:

| Trường | Ví dụ | Lưu ý |
| --- | --- | --- |
| `amount` | `125.50` | `BigDecimal` hoặc dạng decimal có precision xác định |
| `currencyCode` | `USD` | Mã ISO 4217 được xác minh trong domain |
| `displayLocale` | `vi-VN` | Tùy chọn UI, không thay đổi hai trường trên |
| `exchangeRate` | Nếu có quy đổi | Dữ liệu có nguồn và thời điểm |
| `settlementCurrency` | Nếu khác currency giao dịch | Cần đối soát rõ ràng |

Tầng nghiệp vụ cần kiểm soát việc cộng/trừ tiền:

- Không cộng 5 USD với 10 EUR rồi lưu kết quả 15 ở một currency không xác định.
- Muốn tổng hợp nhiều currency thì phải chuyển đổi theo chính sách tỷ giá có chứng cứ.
- Không so sánh hoặc làm tròn tiền qua **chuỗi đã format**; giữ số và currency trong object/domain.
- Nếu UI thay ngôn ngữ giữa lúc đặt hàng, **currency trên đơn đã xác nhận không đổi** trừ khi có thao tác đổi tiền được người dùng yêu cầu và hệ thống hỗ trợ.

Locale hiển thị có thể thay đổi qua request context mà không phá vỡ hợp đồng tiền tệ của đối tượng `Money`.

## 7. Chương trình Java 17 hoàn chỉnh: giới hạn suy luận qua ví dụ

Đặt nội dung sau trong file **`CurrencyInferenceDemo.java`**. Mã cố ý chỉ in mã currency và giá trị gốc để stdout ít phụ thuộc phiên bản dữ liệu ký hiệu hiển thị của từng locale.

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class CurrencyInferenceDemo {
    record Money(BigDecimal amount, Currency currency) {}

    static String inferredCode(String languageTag) {
        Locale locale = Locale.forLanguageTag(languageTag);
        try {
            Currency currency = Currency.getInstance(locale);
            return currency == null ? "none" : currency.getCurrencyCode();
        } catch (IllegalArgumentException e) {
            return "not-resolvable";
        }
    }

    static NumberFormat formatterFor(Money money, Locale displayLocale) {
        NumberFormat format = NumberFormat.getCurrencyInstance(displayLocale);
        format.setCurrency(money.currency());
        int digits = money.currency().getDefaultFractionDigits();
        if (digits >= 0) {
            format.setMinimumFractionDigits(digits);
            format.setMaximumFractionDigits(digits);
        }
        return format;
    }

    public static void main(String[] args) {
        for (String tag : new String[] {
                "en-US", "es-US", "en-GB", "en",
                "en-AQ", "en-US-u-cu-eur", "en-US-u-rg-gbzzzz"
        }) {
            System.out.println(tag + " -> " + inferredCode(tag));
        }

        Money payment = new Money(
                new BigDecimal("125.50"), Currency.getInstance("USD"));
        NumberFormat shownInGermany =
                formatterFor(payment, Locale.GERMANY);
        System.out.println("payment amount: "
                + payment.amount().toPlainString());
        System.out.println("payment currency: "
                + shownInGermany.getCurrency().getCurrencyCode());
        System.out.println("JPY default fraction: "
                + Currency.getInstance("JPY").getDefaultFractionDigits());
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac -encoding UTF-8 CurrencyInferenceDemo.java
java CurrencyInferenceDemo
~~~

Stdout đã kiểm tra trên JDK với dữ liệu currency tương ứng:

~~~text
en-US -> USD
es-US -> USD
en-GB -> GBP
en -> not-resolvable
en-AQ -> none
en-US-u-cu-eur -> EUR
en-US-u-rg-gbzzzz -> GBP
payment amount: 125.50
payment currency: USD
JPY default fraction: 0
~~~

**Giải thích kết quả:**

1. `en-US` và `es-US` khác **ngôn ngữ**, nhưng cùng **khu vực US**, nên ánh xạ mặc định là USD.
2. `en-GB` vẫn dùng tiếng Anh nhưng khu vực GB nên cho GBP: language đơn lẻ không quyết định currency.
3. `en` không có khu vực cần thiết cho ánh xạ ISO country; helper bắt `IllegalArgumentException` và in `not-resolvable`.
4. `en-AQ` minh họa một lãnh thổ không có currency được gán: Java trả `null`, helper in `none`.
5. `en-US-u-cu-eur` cho EUR qua extension `cu` dù country cơ sở là US.
6. `en-US-u-rg-gbzzzz` cho GBP do region override `rg`, dù language tag còn country US.
7. Giá trị tiền `125.50` vẫn là USD ngay cả khi formatter được tạo theo `Locale.GERMANY`. Lệnh `setCurrency(USD)` **không phải phép quy đổi**.
8. JPY có 0 chữ số thập phân mặc định theo ISO; chi tiết thanh toán thực tế vẫn phụ thuộc hợp đồng cổng thanh toán và quy tắc nghiệp vụ.

Trong code ví dụ, helper `inferredCode` nhận `Locale.forLanguageTag` cho tiện trình diễn. **Đối với input người dùng không tin cậy**, nên xác thực language tag và hạn chế extension bằng quy tắc rõ ràng trước khi dùng thông tin cho quyết định tiền tệ. Không sử dụng helper như một dịch vụ xác định currency để thu tiền.

## 8. Luồng nghiệp vụ nên chọn currency theo thứ tự nào?

Một cách thiết kế có kiểm soát là **ưu tiên nguồn sự thật của giao dịch**:

~~~text
1. Giao dịch / bảng giá / hợp đồng có currency tường minh?
   |-- Có --> giữ mã đó, kiểm tra được phép và tương thích thanh toán
   |
   '-- Không --> 
       2. Người dùng đã chọn currency bằng chức năng được hỗ trợ?
          |-- Có --> kiểm tra allowlist, ghi nhận lựa chọn
          |
          '-- Không -->
              3. Có chính sách chọn mặc định theo merchant/market/region?
                 |-- Có --> dùng dữ liệu policy đã version hóa
                 |
                 '-- Không --> yêu cầu xác định currency, không tự đoán
                               chỉ từ language hoặc Accept-Language
~~~

Có thể dùng `Currency.getInstance(locale)` như một **gợi ý UI** ở bước chọn mặc định nếu policy cho phép, nhưng vẫn phải xử lý `null`/`IllegalArgumentException`, kiểm tra currency được hỗ trợ và không tự ý ghi đè đồng tiền đã được xác định.

Sau khi domain đã có `Money(amount, currency)`:

1. Presenter chọn `Locale` theo ngôn ngữ người dùng.
2. Presenter tạo formatter theo `Locale`.
3. Presenter gọi `formatter.setCurrency(money.currency())` và áp dụng quy tắc số lẻ/rounding rõ ràng.
4. Chuỗi được trả ra chỉ là **bản trình bày**, không trở thành dữ liệu nguồn của đơn hàng.

Nếu chưa có currency, **không dùng `Locale.getDefault()` của JVM như một cơ chế fallback cho thanh toán**: default locale có thể do máy chủ/CI/container quyết định và không phản ánh user hay merchant.

## 9. Các lỗi thường gặp

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| “Tiếng Anh luôn dùng USD” | `en-US`, `en-GB` và nhiều locale dùng chung language | Chỉ dùng language cho ngôn ngữ UI |
| “Biết country là biết currency trên hóa đơn” | Currency giao dịch phụ thuộc hợp đồng/merchant/payment | Lưu mã currency tường minh trên khoản tiền |
| Dùng `Currency.getInstance(Locale.forLanguageTag("en"))` và giả định có kết quả | Thiếu country, có thể ném lỗi | Kiểm tra đầu vào và chính sách fallback |
| Không xử lý kết quả `null` | Một số lãnh thổ không có currency được gán | Hỗ trợ trạng thái không xác định |
| Bỏ qua Unicode extensions `cu` và `rg` | Currency có thể khác ánh xạ country cơ sở | Hiểu đầy đủ hợp đồng API, không dùng extension làm lệnh thanh toán |
| Gọi `setCurrency(EUR)` rồi nghĩ 100 USD thành 100 EUR đã quy đổi | Chỉ thay **đơn vị được hiển thị**, trị số giữ nguyên | Dùng dịch vụ tỷ giá và lưu conversion record |
| Coi `Currency.getAvailableCurrencies()` là danh sách tiền đang được chấp nhận | Có thể gồm mã cũ hoặc mã không được provider hỗ trợ | Allowlist theo product/payment/hiệu lực |
| Lưu dấu `$` thay cho mã currency | Nhiều currency chia sẻ ký hiệu | Lưu `USD`/`CAD`/... rõ ràng |
| Gọi `setCurrency` và nghĩ precision tự thay | `setCurrency` không reset min/max fraction | Cấu hình fraction digits và rounding riêng |
| Đổi locale màn hình rồi làm đổi đơn vị hóa đơn | Locale chỉ liên quan trình bày | Giữ `Money` và currency immutable theo contract |
| Dùng `double` cho tính toán tiền cần chính xác | Có sai số nhị phân | Dùng `BigDecimal` với rounding rule |
| Suy tỷ giá từ locale | Locale không có tỷ giá | Lấy tỷ giá có nguồn, thời điểm và quy tắc |

## 10. Kiểm thử cần có

Tách riêng **kiểm thử Java API** và **kiểm thử nghiệp vụ**.

### Kiểm thử hành vi của Java

- `en-US` với `es-US` cùng gợi ý USD: language không đổi country.
- `en-US` với `en-GB` khác currency: country có tác dụng trong ánh xạ.
- Locale chỉ có language như `en`: xử lý lỗi rõ ràng; không tự gán USD.
- Vùng `AQ`: xử lý `null` thay vì giả định mọi country có currency.
- `u-cu-eur` và `u-rg-gbzzzz`: xác minh extension và chính sách nhận input.
- `Currency.getInstance("USD")` với mã sai/không được hỗ trợ: xử lý `IllegalArgumentException`.
- `NumberFormat.getCurrencyInstance(locale)` sau khi `setCurrency`: đơn vị hiển thị đổi nhưng số gốc không đổi; fraction digits cần được kiểm soát.

### Kiểm thử nghiệp vụ

- Đơn 125.50 USD mở trên UI tiếng Việt, tiếng Đức và tiếng Anh **vẫn là USD**.
- Tạo đơn khi không biết currency: yêu cầu lựa chọn hoặc áp dụng policy đã công bố, không đoán từ language.
- Ngôn ngữ UI hoặc country giao hàng đổi sau khi tạo đơn: đồng tiền đơn đã xác nhận không tự đổi.
- Cổng thanh toán không hỗ trợ mã currency do UI đề xuất: từ chối/chọn lại theo policy, không thay đổi âm thầm.
- Quy đổi USD → VND: bắt buộc có tỷ giá, thời điểm, rounding và dữ liệu audit.
- Hóa đơn cũ theo dữ liệu lịch sử: không dùng ánh xạ country hiện thời để viết lại currency của giao dịch.
- Currency code và amount được lưu/đọc từ database/API mà không phụ thuộc locale của server.

Với tình huống bắt buộc theo thời gian, thiết kế test cố định dataset/version và mốc hiệu lực; kết quả ánh xạ theo country có thể thay đổi khi JDK cập nhật dữ liệu tiền tệ.

## 11. Bài tập thực hành

1. Gọi `Currency.getInstance` với `Locale.forLanguageTag("fr-CA")` và `Locale.forLanguageTag("en-CA")`; giải thích vì sao cùng region có thể cho cùng mã dù ngôn ngữ khác.
2. Thử `en-US-u-cu-jpy`; phân biệt region của locale với currency extension, và lý do không dùng extension tự động sửa hóa đơn.
3. Tạo `Money(new BigDecimal("100.00"), Currency.getInstance("USD"))`; định dạng theo `Locale.GERMANY`, rồi theo `Locale.US`. So sánh **chuỗi hiển thị** và **giá trị nghiệp vụ**.
4. Thử `Currency.getInstance(Locale.forLanguageTag("en"))` và một mã country không được hỗ trợ; xử lý kết quả hoặc ngoại lệ.
5. Kiểm tra `Currency.getInstance("JPY").getDefaultFractionDigits()`, sau đó format khoản tiền JPY; đặt rõ min/max fraction digits trong presenter.
6. Tạo danh sách `supportedCurrencies` do merchant quyết định, rồi thử locale đề xuất một currency không nằm trong danh sách.
7. Viết hàm `createQuote(BigDecimal amount, String currencyCode)` xác thực mã ISO và allowlist, không nhận locale làm nguồn currency.
8. Giải thích vì sao chuyển `"$125.50"` thành `Money` có thể gây nhập nhằng nếu thiếu mã currency và locale.

## 12. Kết luận

**Locale không phải đồng tiền giao dịch.** Language chủ yếu quyết định ngôn ngữ UI; region có thể giúp Java **gợi ý** một currency, nhưng không xác định chắc currency của mọi giao dịch. `Currency.getInstance(Locale)` có thể trả mã được ánh xạ, `null`, ném lỗi hoặc chịu tác động từ các Unicode extension `cu`/`rg`.

Khi làm phần mềm có tiền thật, hãy lưu `BigDecimal` **kèm `Currency` tường minh** từ nguồn đáng tin cậy; dùng `Locale` chỉ để trình bày, tách riêng tỷ giá/quy đổi và kiểm soát quy tắc làm tròn. Cách tách bạch đó ngăn lỗi nguy hiểm nhất: **đổi ký hiệu hoặc ngôn ngữ rồi vô tình thay đổi ý nghĩa của số tiền**.

**Tài liệu tham khảo:**

- Java SE 17, `java.util.Currency`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html
- Java SE 17, `java.util.Locale`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html
- Java SE 17, `java.text.NumberFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html
- Java SE 17, `java.math.BigDecimal`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
- Oracle Internationalization Guide: https://docs.oracle.com/en/java/javase/17/intl/
