
# Locale, dữ liệu CLDR và định dạng số hoặc tiền tệ

Trong quá trình nâng cấp Java, nhiều lỗi tương thích không xuất hiện dưới dạng compile error, `NoSuchMethodError` hay `UnsupportedClassVersionError`. Ứng dụng vẫn khởi động bình thường nhưng báo cáo tài chính hiển thị dấu phân cách khác, ký hiệu tiền tệ xuất hiện ở vị trí mới, số được nhóm chữ số theo cách khác, hoặc parser không còn chấp nhận một chuỗi đã lưu từ phiên bản cũ. Các khác biệt này có thể bắt nguồn từ **Locale mặc định**, **dữ liệu quốc tế hóa**, **nguồn dữ liệu CLDR** và cách Java lựa chọn bộ cung cấp dữ liệu locale.

Đây là vấn đề thuộc nhóm **Hành vi mặc định** trong *Java Advance Compatibility Migration*: mã nguồn, bytecode và API công khai có thể không thay đổi, nhưng kết quả quan sát được ở runtime lại thay đổi do JDK, dữ liệu locale, môi trường triển khai và dependency.

Bài học giải thích mối quan hệ giữa `java.util.Locale`, Unicode CLDR, `NumberFormat`, `DecimalFormat`, `DecimalFormatSymbols`, `Currency` và các điểm cần kiểm chứng khi nâng JDK. Trọng tâm là phát hiện **thay đổi hành vi có ảnh hưởng đến người dùng và giao thức**, thay vì cố ghi nhớ một chuỗi định dạng cố định của mọi phiên bản Java.

## 1. Vì sao thay JDK có thể làm đổi định dạng mà không đổi code?

Xét mã Java:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;

public class Report {
    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("1234567.89");
        System.out.println(NumberFormat.getCurrencyInstance().format(amount));
    }
}
~~~

Đoạn mã không chỉ định locale. `NumberFormat.getCurrencyInstance()` vì vậy phụ thuộc vào **default formatting locale** của tiến trình. Kết quả có thể khác giữa máy phát triển và môi trường production hoặc giữa các cấu hình JDK.

Ngay cả khi locale được chỉ rõ:

~~~java
NumberFormat formatter =
        NumberFormat.getCurrencyInstance(Locale.forLanguageTag("fr-FR"));
~~~

vẫn còn yếu tố dữ liệu: cách viết ký hiệu tiền tệ, quy tắc grouping, dấu thập phân, khoảng trắng và các pattern định dạng được cung cấp bởi locale data provider của JDK. Tập dữ liệu này có thể được cập nhật qua các bản JDK.

Các nguồn dẫn đến thay đổi gồm:

- Locale mặc định của JVM khác nhau giữa môi trường.
- JDK thay đổi thứ tự hoặc tập locale data provider.
- Phiên bản Unicode CLDR được JDK sử dụng được cập nhật.
- Quy tắc định dạng của một locale được sửa.
- Mặc định về số chữ số thập phân hoặc ký hiệu tiền tệ được cập nhật.
- Dependency như ICU4J hoặc thư viện JSON/templating có phiên bản hay cấu hình khác.
- Mã ứng dụng dựa vào `Locale.getDefault()` hoặc `NumberFormat.getInstance()` ở vị trí không chủ đích.

**Phân biệt ba lớp:** *giá trị nghiệp vụ* (ví dụ 1234567.89), *quy tắc biểu diễn* (locale, pattern, currency) và *chuỗi được xuất ra* (text hiển thị). Nếu trộn chúng vào nhau, một thay đổi trình bày có thể trở thành lỗi dữ liệu.

## 2. Locale là gì?

`java.util.Locale` mô tả lựa chọn ngôn ngữ, vùng, script và các extension liên quan đến cách xử lý dữ liệu theo văn hóa/ngôn ngữ.

Ví dụ:

~~~java
import java.util.Locale;

Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale german = Locale.forLanguageTag("de-DE");
Locale usEnglish = Locale.forLanguageTag("en-US");

System.out.println(vietnamese.toLanguageTag());
System.out.println(german.getLanguage());
System.out.println(usEnglish.getCountry());
~~~

Các thành phần thường gặp:

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Language | `vi`, `en`, `de` | Ngôn ngữ |
| Region | `VN`, `US`, `DE` | Vùng hoặc quốc gia theo mã tương ứng |
| Script | `Latn`, `Cyrl` | Hệ chữ viết |
| Variant | Tùy locale | Biến thể bổ sung |
| Unicode locale extension | `u-nu-latn` | Chọn các đặc điểm xử lý locale mà provider hỗ trợ |

Không nên đồng nhất locale với múi giờ, charset hay đơn vị tiền tệ:

- `Locale` là ngữ cảnh ngôn ngữ/vùng để chọn quy tắc trình bày.
- `ZoneId` là định danh múi giờ.
- `Charset` là quy tắc mã hóa ký tự.
- `Currency` là mã đơn vị tiền tệ và thông tin liên quan.
- `BigDecimal` biểu diễn số thập phân chính xác, không chứa locale.

Một locale có thể gợi ý đơn vị tiền mặc định, nhưng **giao dịch tài chính phải lưu currency riêng**. Ví dụ một khách hàng ở Việt Nam vẫn có thể thanh toán bằng USD.

### 2.1. Locale mặc định và Locale được chọn tường minh

So sánh:

~~~java
NumberFormat a = NumberFormat.getNumberInstance();
NumberFormat b =
        NumberFormat.getNumberInstance(Locale.forLanguageTag("vi-VN"));
~~~

`a` phụ thuộc default locale của JVM; `b` sử dụng locale do ứng dụng chỉ rõ. Cả hai vẫn có thể phụ thuộc vào data provider và phiên bản dữ liệu trong JDK.

Khi xuất dữ liệu máy đọc, dùng default locale thường là sai thiết kế. Khi hiển thị cho người dùng, locale phải đến từ hồ sơ người dùng, request, cấu hình sản phẩm hoặc quy tắc nghiệp vụ đã xác định.

### 2.2. Default locale có hai category quan trọng

Java hỗ trợ category mặc định:

- `Locale.Category.DISPLAY`: dùng cho tên hiển thị và nội dung giao diện.
- `Locale.Category.FORMAT`: dùng cho các thao tác formatting theo locale.

Ví dụ:

~~~java
import java.util.Locale;

public final class Defaults {
    public static void main(String[] args) {
        System.out.println(Locale.getDefault());
        System.out.println(
                Locale.getDefault(Locale.Category.DISPLAY));
        System.out.println(
                Locale.getDefault(Locale.Category.FORMAT));
    }
}
~~~

`NumberFormat` thường dựa vào default formatting locale khi không được truyền locale tường minh. Không nên giả định `DISPLAY` và `FORMAT` luôn bằng nhau.

Đổi locale mặc định trong cùng một JVM bằng `Locale.setDefault(...)` là thao tác ảnh hưởng toàn tiến trình và có thể làm các thread khác chịu tác động. Trong dịch vụ nhiều request, nên truyền locale rõ ràng thay vì sửa global state theo từng người dùng.

### 2.3. BCP 47 và lựa chọn locale

`Locale.forLanguageTag("vi-VN")` thích hợp khi nhận language tag từ cấu hình. Mã locale được chuẩn hóa và không nhất thiết có cấu trúc giống mọi chuỗi cũ ở dạng `language_COUNTRY`.

Ví dụ xây dựng tường minh:

~~~java
Locale locale = new Locale.Builder()
        .setLanguage("vi")
        .setRegion("VN")
        .build();
~~~

Nếu nhận locale do client cung cấp, cần xác định danh sách locale được sản phẩm hỗ trợ, quy tắc fallback và cách xử lý đầu vào không hợp lệ. Không nên nhận một language tag bất kỳ rồi giả định mọi dữ liệu format đều có đầy đủ cho tag đó.

## 3. CLDR là gì và vì sao quan trọng khi nâng JDK?

**Unicode Common Locale Data Repository (CLDR)** là tập dữ liệu quốc tế hóa mô tả các quy tắc về tên ngôn ngữ, vùng, định dạng số, dấu phân cách, ký hiệu tiền tệ, pattern ngày giờ, plural rule và nhiều thông tin bản địa hóa khác.

Java có thể sử dụng dữ liệu xuất phát từ CLDR để phục vụ các API như `NumberFormat`, `DateFormat` và những thành phần localization khác.

### 3.1. CLDR không phải là API gọi trực tiếp

Với code:

~~~java
NumberFormat formatter =
        NumberFormat.getNumberInstance(Locale.forLanguageTag("de-DE"));
~~~

lập trình viên gọi Java SE API. Kết quả phụ thuộc implementation và dữ liệu locale của runtime; không có lời gọi “trực tiếp tới CLDR” trong đoạn code.

Điểm này giải thích tại sao cùng một API vẫn có thể trả về chuỗi khác sau nâng JDK:

- Bản JDK mới mang theo dữ liệu locale được cập nhật.
- Một quy tắc của CLDR được thay đổi/corrected.
- Provider được chọn khác trước.
- Dữ liệu fallback cho locale thiếu thông tin được chọn khác.

**Không có bảo đảm chung rằng ký tự output của mọi locale sẽ giống hệt qua mọi JDK update.**

### 3.2. Mốc thay đổi về provider

JDK 9 đưa CLDR thành nguồn locale data được ưu tiên theo định hướng của JEP 252, thay vì chỉ giữ bộ dữ liệu tương thích cũ làm mặc định trong các JDK trước đó. Các release tiếp theo cũng có thay đổi về những provider được cung cấp và dữ liệu tương ứng.

Điều cần nhớ khi migration:

1. JDK nguồn và đích có thể **khác provider mặc định**.
2. Một số tên/alias provider và cơ chế COMPAT thuộc giai đoạn lịch sử của JDK; đừng giả định chúng tồn tại mãi trên bản Java mới.
3. Dữ liệu CLDR có thể đổi ngay cả khi provider vẫn là CLDR.
4. Cần đọc release notes, migration guide và kiểm chứng trên JDK thực tế, không suy ra từ tên phiên bản đơn thuần.

### 3.3. Property java.locale.providers

Trên các JDK hỗ trợ, có thể chỉ định thứ tự locale provider bằng system property:

~~~bash
java -Djava.locale.providers=CLDR,SPI -jar app.jar
~~~

Ví dụ trên yêu cầu xem xét CLDR rồi đến SPI theo cơ chế provider của JDK. Nó **không làm cho dữ liệu CLDR bất biến** và cũng không có nghĩa mọi application server/framework đều tuân theo một nguồn định dạng duy nhất.

Một số hệ thống cũ dùng cấu hình kiểu:

~~~text
-Djava.locale.providers=COMPAT,CLDR
~~~

Nhưng `COMPAT` là bộ dữ liệu tương thích lịch sử, không nên dùng làm chiến lược lâu dài nếu JDK đích không còn cung cấp hoặc không hỗ trợ provider đó. Cần kiểm tra tài liệu của phiên bản JDK cụ thể trước khi đề xuất property.

**Không coi việc ép provider cũ là giải pháp migration mặc định.** Ưu tiên xác định hợp đồng format và sửa code/test để chấp nhận quy tắc được công bố.

### 3.4. LocaleServiceProvider và SPI

Java có cơ chế Service Provider Interface (`java.util.spi`) cho một số dịch vụ locale. Một ứng dụng có thể đóng gói provider riêng nếu cần quy tắc đặc thù. Điều này tạo thêm nguồn biến đổi ngoài dữ liệu JDK.

Khi phân tích sự khác biệt:

- Kiểm tra có implementation SPI trên classpath/module path không.
- Kiểm tra `META-INF/services` hoặc khai báo module phù hợp.
- Kiểm tra property `java.locale.providers` có cho phép dùng SPI không.
- Kiểm tra thứ tự ưu tiên và fallback.
- Kiểm tra artifact thực tế, không chỉ source.

Không nên tự thêm SPI để “đóng băng” mọi locale khi chỉ một format giao thức cần ổn định. Một định dạng canonical riêng thường đơn giản và dễ kiểm thử hơn.

## 4. Quy tắc định dạng số gồm những thành phần nào?

Một số như `1234567.89` có thể được biểu diễn theo nhiều cách tùy locale:

- Dấu phân cách hàng nghìn/grouping.
- Dấu thập phân.
- Quy tắc đặt dấu âm.
- Số chữ số tối thiểu/tối đa ở phần thập phân.
- Hệ chữ số/digit set.
- Ký hiệu phần trăm hoặc exponent.
- Khoảng trắng đặc biệt giữa số và đơn vị.
- Pattern của số âm, số dương và ký hiệu.

Ví dụ về cách biểu diễn theo những quy ước phổ biến (chỉ minh họa, **không phải output được cam kết của một phiên bản JDK**):

| Locale hoặc cách viết | Chuỗi ví dụ | Ghi chú |
|---|---|---|
| Quy ước en-US | `1,234,567.89` | Dấu phẩy grouping, dấu chấm decimal |
| Quy ước de-DE | `1.234.567,89` | Dấu chấm grouping, dấu phẩy decimal |
| Một quy ước kiểu Pháp | `1 234 567,89` | Dấu phân cách nhóm có thể là khoảng trắng Unicode hẹp |
| Chuỗi máy đọc canonical | `1234567.89` | Dùng dấu chấm, không grouping |

Các ký tự trông giống khoảng trắng có thể khác nhau ở code point: `U+0020` (space), `U+00A0` (no-break space) và `U+202F` (narrow no-break space). Thay đổi một ký tự trong những ký tự này có thể làm snapshot test hoặc parser thủ công thất bại.

### 4.1. NumberFormat.getNumberInstance

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

public class NumberExample {
    public static void main(String[] args) {
        BigDecimal value = new BigDecimal("1234567.89");
        Locale[] locales = {
                Locale.forLanguageTag("en-US"),
                Locale.forLanguageTag("de-DE"),
                Locale.forLanguageTag("vi-VN")
        };

        for (Locale locale : locales) {
            NumberFormat formatter =
                    NumberFormat.getNumberInstance(locale);
            System.out.println(
                    locale.toLanguageTag() + ": " +
                    formatter.format(value));
        }
    }
}
~~~

Chạy cùng class file trên hai JDK để ghi nhận output. Đừng ghi cố định expected string từ tài liệu ví dụ nếu ứng dụng cần hỗ trợ nhiều provider/JDK; thay vào đó, hãy có kế hoạch test rõ cho các contract cần ổn định.

### 4.2. DecimalFormatSymbols

`DecimalFormatSymbols` giúp quan sát các ký hiệu theo locale:

~~~java
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class SymbolsExample {
    static String codePoint(char value) {
        return String.format("U+%04X", (int) value);
    }

    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("fr-FR");
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(locale);

        System.out.println(
                "decimal=" + codePoint(symbols.getDecimalSeparator()));
        System.out.println(
                "grouping=" + codePoint(symbols.getGroupingSeparator()));
        System.out.println(
                "currency=" + symbols.getCurrencySymbol());
    }
}
~~~

Việc in code point giúp phân biệt các ký tự nhìn tương tự. Nếu cần so sánh chính xác chuỗi Unicode chứa cả những ký tự supplementary, hãy duyệt bằng `String.codePoints()`; ví dụ trên dùng `char` vì các getter cụ thể trả về ký tự `char`.

### 4.3. Pattern không hoàn toàn thay thế locale

Với `DecimalFormat`, pattern quyết định cấu trúc định dạng, nhưng các ký hiệu trong kết quả vẫn có thể lấy từ `DecimalFormatSymbols` của locale.

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class PatternExample {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("de-DE");
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(locale);

        DecimalFormat format =
                new DecimalFormat("#,##0.00", symbols);

        System.out.println(
                format.format(new BigDecimal("1234567.8")));
    }
}
~~~

Trong pattern không localized, dấu phẩy và dấu chấm mang vai trò cú pháp pattern; khi in ra, các ký hiệu thực tế phụ thuộc `symbols`. Nếu ứng dụng cần chuỗi máy đọc cố định, không nên cho phép locale khác tự thay đổi cách xuất dữ liệu.

## 5. Định dạng tiền tệ: hai quyết định độc lập

Tiền tệ cần cả **giá trị số** và **đơn vị tiền tệ**. Locale chủ yếu quyết định cách trình bày, còn giao dịch quyết định currency.

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class CurrencyExample {
    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("1234567.89");
        Locale viewerLocale = Locale.forLanguageTag("vi-VN");
        Currency transactionCurrency =
                Currency.getInstance("USD");

        NumberFormat formatter =
                NumberFormat.getCurrencyInstance(viewerLocale);
        formatter.setCurrency(transactionCurrency);

        System.out.println(formatter.format(amount));
    }
}
~~~

Trong ví dụ, người dùng có locale tiếng Việt tại Việt Nam, nhưng giao dịch được định danh là USD. `setCurrency` chọn đơn vị tiền để biểu diễn; kết quả chuỗi, ký hiệu và các quy tắc format khác có thể phụ thuộc locale/provider và cấu hình formatter. Không được suy luận currency của giao dịch chỉ từ locale người xem.

### 5.1. Locale không phải currency code

| Giá trị | Ví dụ | Mục đích |
|---|---|---|
| Locale | `vi-VN` | Lựa chọn quy tắc trình bày |
| Currency code | `VND`, `USD`, `EUR` | Định danh đơn vị tiền |
| Amount | `new BigDecimal("125000.50")` | Giá trị số chính xác |
| Currency symbol | `₫`, `$`, `€` | Ký hiệu hiển thị, có thể tùy locale |
| Formatted text | Ví dụ một chuỗi theo locale | Dành cho người đọc, không phải định danh máy |

Một ký hiệu như `$` có thể dùng cho nhiều loại tiền. Vì thế, **mã ISO 4217** thường là lựa chọn định danh an toàn hơn ký hiệu trong dữ liệu giao tiếp. Nếu sản phẩm dùng tài sản hoặc đơn vị ngoài tập ISO 4217, cần thiết kế mã riêng có hợp đồng rõ.

### 5.2. Số chữ số thập phân của currency

`Currency.getDefaultFractionDigits()` cung cấp số chữ số thập phân mặc định của đơn vị tiền, theo dữ liệu do runtime có. Không phải mọi currency đều có hai chữ số.

~~~java
import java.util.Currency;

public class Digits {
    public static void main(String[] args) {
        for (String code : new String[] {"USD", "VND", "JPY"}) {
            Currency currency = Currency.getInstance(code);
            System.out.println(
                    code + " -> " +
                    currency.getDefaultFractionDigits());
        }
    }
}
~~~

Với một số đơn vị đặc biệt, giá trị có thể là `-1` khi fraction digits không áp dụng. Khi thiết kế dữ liệu tiền tệ, cần xác định quy tắc precision, rounding và pháp lý/kinh doanh của sản phẩm; thông tin fraction digits mặc định không tự thay thế quy tắc nghiệp vụ.

Một lỗi thường gặp là xem formatter như máy tính tiền và để nó tự làm tròn số tiền giao dịch. `NumberFormat` chỉ xuất chuỗi; giá trị tính toán phải được xử lý trước theo policy riêng.

### 5.3. Vị trí ký hiệu và khoảng trắng

Một locale có thể đặt currency symbol trước hoặc sau số, có hoặc không có khoảng cách; đôi khi dùng ký hiệu hẹp, mã tiền ba chữ cái hoặc dấu không ngắt dòng. Những chi tiết này có thể đổi theo dữ liệu CLDR.

**Không parse tiền tệ bằng cách xóa một ký hiệu cố định, rồi thay dấu phân cách thủ công.** Cách đó hỏng khi ký hiệu xuất hiện ở vị trí khác, khoảng trắng Unicode khác, hoặc ký hiệu mơ hồ giữa các currency.

### 5.4. setCurrency không tương đương chỉ định toàn bộ quy tắc số

Đặt currency vào `NumberFormat` không phải cam kết formatter sẽ tự áp dụng mọi yêu cầu precision nghiệp vụ. Nếu cần số chữ số thập phân cụ thể, cấu hình tường minh và kiểm thử:

~~~java
NumberFormat formatter =
        NumberFormat.getCurrencyInstance(
                Locale.forLanguageTag("en-US"));

formatter.setCurrency(Currency.getInstance("USD"));
formatter.setMinimumFractionDigits(2);
formatter.setMaximumFractionDigits(2);
~~~

Việc đặt giới hạn fraction digits là **định dạng kết quả**. Trong tính toán kế toán, `BigDecimal.setScale(...)` với `RoundingMode` phù hợp phải được quyết định theo nghiệp vụ trước khi render.

## 6. BigDecimal, double và rounding khi xử lý tiền

### 6.1. Không xây dựng giá trị tiền chính xác từ literal double tùy tiện

Ví dụ:

~~~java
import java.math.BigDecimal;

BigDecimal risky = new BigDecimal(0.1);
BigDecimal exact = new BigDecimal("0.1");
~~~

`new BigDecimal(0.1)` nhận giá trị nhị phân thực của `double`, không phải chính xác số thập phân “0.1” như người dùng nhập. Trong các phép tính tài chính, ưu tiên tạo `BigDecimal` từ chuỗi thập phân canonical hoặc dữ liệu đầu vào đã kiểm chứng.

### 6.2. Rounding là quyết định nghiệp vụ, không phải locale

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal raw = new BigDecimal("19.995");
BigDecimal displayAmount =
        raw.setScale(2, RoundingMode.HALF_EVEN);
~~~

`RoundingMode.HALF_EVEN` chỉ là lựa chọn minh họa. Các lĩnh vực như thuế, hóa đơn, thanh toán hoặc hối đoái có thể yêu cầu quy tắc khác, thời điểm làm tròn khác hoặc xử lý theo từng dòng thay vì tổng.

Cần xác định:

- Precision nội bộ.
- Scale lúc lưu trữ.
- Scale lúc tính toán.
- Quy tắc rounding từng bước.
- Scale hiển thị theo đơn vị tiền và chính sách sản phẩm.
- Nguồn tỷ giá và precision của tỷ giá nếu có chuyển đổi tiền.

Đừng để thay đổi CLDR vô tình thay đổi thuật toán tính tổng hoặc kết quả thanh toán. Locale chỉ nên tác động phần trình bày khi hợp đồng nghiệp vụ không nói khác.

### 6.3. DecimalFormat không bảo đảm thread-safe

`NumberFormat` và `DecimalFormat` là các formatter có trạng thái và nhìn chung **không an toàn để dùng đồng thời mà không đồng bộ**. Không nên chia sẻ một instance mutable toàn ứng dụng rồi thay currency, locale hoặc fraction digits theo từng request.

Ví dụ nên tạo formatter riêng theo request hoặc scope phù hợp:

~~~java
static String formatMoney(
        BigDecimal amount, Currency currency, Locale locale) {
    NumberFormat formatter =
            NumberFormat.getCurrencyInstance(locale);
    formatter.setCurrency(currency);
    return formatter.format(amount);
}
~~~

Nếu cần cache formatter, phải có chiến lược thread safety và không để trạng thái của request này rò sang request khác.

## 7. Parse số theo locale: nguồn lỗi âm thầm

Khi đọc input do người dùng nhập, `NumberFormat.parse` có thể diễn giải dấu chấm và dấu phẩy khác nhau theo locale. Ví dụ `"1.234"` có thể là một nghìn hai trăm ba mươi bốn hoặc một phẩy hai ba bốn tùy quy ước.

~~~java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class ParseExample {
    public static void main(String[] args) {
        String input = "1.234";
        Locale locale = Locale.forLanguageTag("de-DE");

        NumberFormat parser =
                NumberFormat.getNumberInstance(locale);

        ParsePosition pos = new ParsePosition(0);
        Number parsed = parser.parse(input, pos);

        boolean consumedAll =
                parsed != null && pos.getIndex() == input.length();

        System.out.println("parsed=" + parsed);
        System.out.println("consumedAll=" + consumedAll);
    }
}
~~~

### 7.1. Phải kiểm tra đã parse hết input

Một số API parse có thể chỉ đọc prefix hợp lệ và dừng trước phần còn lại. Nếu chỉ kiểm tra kết quả khác `null`, chuỗi có ký tự thừa vẫn có thể được chấp nhận.

Dùng `ParsePosition` để xác nhận:

- Parser trả về giá trị.
- Không có lỗi parse tại vị trí được báo.
- `pos.getIndex() == input.length()` nếu hợp đồng yêu cầu toàn chuỗi hợp lệ.

Đây mới là kiểm tra cú pháp theo locale; vẫn cần xác thực khoảng giá trị, dấu âm, số chữ số và policy nghiệp vụ.

### 7.2. Parse về BigDecimal khi cần chính xác

Nếu formatter thực tế là `DecimalFormat`, có thể cấu hình:

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.util.Locale;

NumberFormat numberFormat =
        NumberFormat.getNumberInstance(
                Locale.forLanguageTag("de-DE"));

if (numberFormat instanceof DecimalFormat decimalFormat) {
    decimalFormat.setParseBigDecimal(true);
    Number value = decimalFormat.parse("1234,56");
    BigDecimal exact = (BigDecimal) value;
    System.out.println(exact.toPlainString());
}
~~~

Cần kiểm soát type trước khi cast, input và vị trí parse. `setParseBigDecimal(true)` áp dụng cho `DecimalFormat`, không phải một lời hứa rằng mọi subclass của `NumberFormat` đều có lựa chọn này.

### 7.3. Không parse ngược chuỗi hiển thị như giao thức máy

Một chuỗi currency được render cho người dùng có thể chứa:

- Currency symbol theo locale.
- Khoảng trắng không ngắt dòng.
- Ký tự bidi trong một số ngôn ngữ.
- Grouping separator khác.
- Rounding mất chữ số so với giá trị gốc.
- Dấu âm ở vị trí khác.

Không nên dùng nó để lưu ledger, chuyển giữa service hoặc tính toán lại. Hãy truyền **amount chuẩn hóa + currency code** ở dạng có schema.

## 8. Định dạng giao thức và định dạng giao diện phải tách biệt

### 8.1. Dạng canonical cho máy đọc

Một hệ thống có thể chọn JSON:

~~~json
{
  "amount": "1234567.89",
  "currency": "USD"
}
~~~

Giá trị `amount` được truyền dưới dạng decimal string theo contract; `currency` là code riêng. Trường hợp khác có thể dùng integer minor units nếu tất cả bên thống nhất scale. Không có một representation duy nhất đúng cho mọi hệ thống; điều cần thiết là **định nghĩa và version hóa contract**.

Khi serialize một `BigDecimal` thành JSON number, cần xem thư viện và consumer có bảo toàn precision không. JavaScript và các hệ khác có thể sử dụng floating point cho JSON number. Chuỗi decimal hoặc integer minor units có thể dễ bảo toàn hơn nếu contract được thiết kế đúng.

### 8.2. `Locale.ROOT` không tự giải quyết tất cả

`Locale.ROOT` có thể hữu ích cho các thao tác không phụ thuộc một ngôn ngữ/vùng cụ thể:

~~~java
String normalized = "status".toUpperCase(Locale.ROOT);
~~~

Nhưng không nên suy ra rằng `NumberFormat.getCurrencyInstance(Locale.ROOT)` là cách tạo dữ liệu tiền canonical. Root locale không tự cung cấp currency giao dịch, precision hay schema. Với dữ liệu máy đọc, dùng API và format được quy định rõ—ví dụ `BigDecimal.toPlainString()` cho decimal string—thay vì chọn một locale bất kỳ để đạt chuỗi “trông giống chuẩn”.

### 8.3. CSV, Excel, log và report

Với CSV, quyết định rõ dữ liệu đang phục vụ người đọc hay máy:

- CSV cho máy: số canonical, không grouping, cột currency riêng, escape theo CSV chuẩn.
- CSV cho người dùng: có thể format theo locale nhưng phải biết parser nào sẽ mở file.
- Excel: số nên ở cell numeric nếu quy trình cho phép, với number format riêng; không tự chuyển mọi số sang text có ký hiệu tiền.
- Log: ưu tiên dữ liệu cấu trúc hoặc số canonical để dễ query; UI logging/observability có thể format lại theo locale khi hiển thị.
- PDF/report: cần locale theo người nhận và kiểm tra font/Unicode nếu ký hiệu tiền hoặc khoảng trắng đặc biệt.

Không nên để default locale của server quyết định ngầm định dạng file dùng trao đổi giữa các hệ thống.

## 9. Unicode trong output: một thay đổi khó nhìn thấy

Kết quả định dạng có thể khác nhau ở mức code point dù nhìn gần giống hệt:

- `U+0020`: SPACE.
- `U+00A0`: NO-BREAK SPACE.
- `U+202F`: NARROW NO-BREAK SPACE.
- `U+200E`: LEFT-TO-RIGHT MARK.
- `U+200F`: RIGHT-TO-LEFT MARK.

Một snapshot test so sánh text chính xác có thể thất bại chỉ vì khoảng trắng không ngắt dòng. Ngược lại, một consumer thực hiện `trim()` hoặc thay space thủ công có thể bỏ sót ký tự Unicode có ý nghĩa khác.

### 9.1. Công cụ in code point phục vụ chẩn đoán

~~~java
public class UnicodeInspector {
    public static String describe(String input) {
        StringBuilder result = new StringBuilder();

        input.codePoints().forEach(cp -> {
            if (result.length() > 0) {
                result.append(' ');
            }
            result.append(String.format("U+%04X", cp));
        });

        return result.toString();
    }

    public static void main(String[] args) {
        String value = "\u00A0\u202F";
        System.out.println(describe(value));
    }
}
~~~

Khi so sánh Java 17 với Java 21 hoặc phiên bản khác, có thể lưu cả chuỗi render và dãy code point. Mục tiêu là hiểu **khác ở đâu** trước khi sửa test hoặc code.

### 9.2. Không tự thay mọi whitespace

Một số khoảng trắng Unicode mang vai trò ngăn xuống dòng giữa số và đơn vị. Thay chúng bằng dấu cách thường có thể làm layout hoặc ngữ nghĩa bản địa hóa kém đi.

Nếu output là format máy, nên thay thiết kế serialization chứ không normalize chuỗi hiển thị tùy tiện. Nếu output là UI, nên giữ quy tắc của locale được hỗ trợ, trừ khi có yêu cầu thiết kế sản phẩm cụ thể.

## 10. Các nguồn default locale trong thực tế

Kết quả `Locale.getDefault()` có thể phụ thuộc hệ điều hành, thiết lập môi trường, property JVM và cách ứng dụng khởi tạo locale. Một container có thể có locale khác máy developer.

Những điểm cần ghi lại khi điều tra:

- JDK vendor, version và build.
- OS và container image.
- `Locale.getDefault()`.
- `Locale.getDefault(Locale.Category.FORMAT)`.
- `Locale.getDefault(Locale.Category.DISPLAY)`.
- Các JVM properties liên quan đến ngôn ngữ/vùng khi được cấu hình.
- `java.locale.providers` và SPI provider thực tế.
- Version dependency formatting/serialization.
- Value, pattern, currency code và rounding policy.

### 10.1. Cờ JVM để thiết lập locale mặc định

Với các JVM hỗ trợ các system property tương ứng, có thể cấu hình tại startup:

~~~bash
java -Duser.language=vi -Duser.country=VN -jar app.jar
~~~

Tuy nhiên, default locale là **cấu hình toàn tiến trình**. Nếu ứng dụng phục vụ người dùng nhiều vùng, hãy truyền locale theo request thay vì dựa vào một cài đặt của server.

Nếu code chủ động gọi `Locale.setDefault` sau startup, giá trị quan sát cũng có thể đổi; cần lưu ý thứ tự khởi tạo và phạm vi ảnh hưởng.

### 10.2. Locale data trong container tối giản

Container image tối giản có thể thiếu tài nguyên hệ điều hành hoặc cấu hình region dự kiến. Nhưng Java locale data có thể đến từ JDK, không nhất thiết từ tất cả package locale của OS.

Vì vậy, không kết luận rằng chỉ cần cài một OS locale package là mọi khác biệt Java formatting sẽ biến mất. Cần kiểm tra actual provider, JDK build và code formatting đang chạy.

## 11. Quy trình migration khi nâng JDK

Có thể triển khai theo từng bước để tránh đổi hành vi mà không có bằng chứng.

~~~mermaid
flowchart TD
    A["Ghi JDK cũ và cấu hình locale"] --> B["Thu thập output đại diện"]
    B --> C["Chạy cùng artifact/test trên JDK đích"]
    C --> D{"Khác biệt có ảnh hưởng hợp đồng?"}
    D -->|Không| E["Cập nhật snapshot/bằng chứng có kiểm soát"]
    D -->|Có| F["Phân loại UI, dữ liệu, API hay parser"]
    F --> G["Chọn explicit locale hoặc canonical format"]
    G --> H["Kiểm thử regression và consumer"]
    E --> H
    H --> I["Ghi quyết định và theo dõi rollout"]
~~~

### Bước 1: Khảo sát điểm format/parse

Tìm các API và luồng dữ liệu:

~~~bash
rg -n "NumberFormat|DecimalFormat|DecimalFormatSymbols|Currency" src
rg -n "Locale.getDefault|Locale.setDefault|forLanguageTag" src
rg -n "String.format|Formatter|printf|parseBigDecimal" src
rg -n "toString\\(|parse\\(|setCurrency|setRoundingMode" src
~~~

Các lệnh chỉ là ví dụ cho repository của người học; cần sửa đường dẫn và kết hợp phân tích thủ công. Ngoài source ứng dụng, xem code trong template engine, report generator, UI và framework serialization.

### Bước 2: Lập bảng điểm phụ thuộc

| Điểm sử dụng | Loại output | Locale hiện tại | Rủi ro | Hợp đồng |
|---|---|---|---|---|
| Trang chi tiết đơn hàng | UI | Theo người dùng | Thấp-trung bình | Định dạng bản địa hóa |
| CSV trao đổi đối tác | Máy đọc | Mặc định JVM | Cao | Decimal canonical và currency code |
| Hóa đơn PDF | Tài liệu | Theo thị trường | Cao | Quy tắc nghiệp vụ, tiền và bố cục |
| Import số do người dùng nhập | Parser | Theo người dùng | Cao | Chỉ chấp nhận đầu vào hợp lệ |
| Log giao dịch | Observability | Mặc định JVM | Trung bình | Giá trị cấu trúc, parse ổn định |
| Test snapshot | Test | Locale ngầm định | Trung bình | Phải phân biệt format với business behavior |

### Bước 3: Ghi baseline trên JDK cũ

Với mỗi case tiêu biểu, ghi:

- Dữ liệu đầu vào, bao gồm giá trị âm, số lớn, số nhỏ, zero và giá trị sát quy tắc rounding.
- Locale, currency code và pattern.
- Output string và code points.
- Kết quả parse và vị trí parse nếu có.
- Phiên bản JDK, provider, locale-related properties.
- Thư viện và config format ngoài Java SE.

Không chỉ lấy một giá trị `1234.56`. Cần có test cho số âm, grouping, currency không dùng hai chữ số decimal, số phần trăm và ký tự Unicode.

### Bước 4: Chạy cùng phép thử trên JDK mục tiêu

Chạy cùng test/harness, cùng dependency version nếu đang cô lập thay đổi JDK. Sau đó mới kết hợp thay đổi dependency; nếu nâng tất cả cùng lúc, khó biết khác biệt do CLDR/JDK hay framework.

**Không nên làm tròn hoặc normalize output trước khi so sánh** nếu mục tiêu là phát hiện khác biệt. Hãy phân loại nguyên nhân trước rồi quyết định contract nên giữ nguyên hay cập nhật.

### Bước 5: Chọn chiến lược xử lý

Có ba tình huống chính:

1. **UI mong muốn theo locale mới:** cập nhật snapshot phù hợp sau khi xác nhận sản phẩm chấp nhận quy tắc mới.
2. **Dữ liệu máy bị thay đổi:** chuyển sang format canonical, số và currency code tách biệt; kiểm thử consumer cũ.
3. **Nghiệp vụ yêu cầu chuỗi hiển thị cố định:** công bố pattern/format riêng, điều chỉnh tường minh và duy trì test theo contract đó.

Đừng ghim mọi hệ thống vào provider lịch sử chỉ để làm các snapshot cũ tiếp tục PASS; cách đó có thể không được hỗ trợ trên JDK đích và che giấu thiết kế phụ thuộc default locale.

### Bước 6: Kiểm tra trên artifact và môi trường triển khai

Build theo quy trình sản phẩm, sau đó kiểm tra artifact cuối cùng trên JDK đích trong container/OS tương ứng. Nếu là service, thử với cấu hình locale từ production và request mang locale khác nhau. Nếu là report, kiểm tra cả output byte-level và hình thức hiển thị.

### Bước 7: Triển khai và giám sát

Ghi rõ tiêu chí rollback:

- Tỷ lệ import/parse lỗi.
- Giá trị giao dịch không hợp lệ.
- Sai lệch schema/CSV/API contract.
- Lỗi hiển thị ảnh hưởng hóa đơn hoặc tuân thủ.
- Lỗi regression trên client/consumer.

Không rollback chỉ vì khác biệt whitespace ở UI đã được duyệt, nhưng cũng không bỏ qua thay đổi làm mất precision hoặc khiến parser diễn giải sai số tiền.

## 12. Tạo test có giá trị thay vì test dễ vỡ

### 12.1. Test logic số độc lập với locale

Logic nghiệp vụ:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class PriceCalculator {
    public static BigDecimal calculateTax(BigDecimal net) {
        return net.multiply(new BigDecimal("0.10"))
                .setScale(2, RoundingMode.HALF_UP);
    }
}
~~~

Kiểm thử nên so sánh giá trị số dựa trên policy nghiệp vụ, không so sánh chuỗi đã format từ default locale.

### 12.2. Test formatting có locale tường minh

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public final class MoneyView {
    public static String render(
            BigDecimal amount, String code, Locale locale) {
        NumberFormat format =
                NumberFormat.getCurrencyInstance(locale);
        format.setCurrency(Currency.getInstance(code));
        return format.format(amount);
    }
}
~~~

Test formatting cần chỉ rõ:

- Locale.
- Currency.
- Input và rounding policy.
- JDK/provider áp dụng cho golden output.
- Quy định cho phép hay không cho phép CLDR thay đổi.

Nếu sản phẩm yêu cầu ký tự exact (ví dụ file in hóa đơn), test golden output có ích nhưng phải gắn với phiên bản runtime và có quy trình duyệt khi CLDR thay đổi.

### 12.3. Property-based và round-trip test

Các thuộc tính có thể kiểm:

- Định dạng không làm crash với số hợp lệ trong miền sản phẩm.
- Parser chỉ chấp nhận đầu vào hợp lệ và tiêu thụ toàn bộ chuỗi.
- Khi format rồi parse ngược trong một **locale và cấu hình cố định**, giá trị được so sánh theo precision do format lưu giữ, không kỳ vọng khôi phục mọi chữ số đã làm tròn.
- Một amount/currency canonical không đổi khi locale của UI đổi.
- Kết quả nghiệp vụ không phụ thuộc cấu hình locale của thread hoặc máy.

Không dùng round-trip như cam kết tuyệt đối với currency formatter có rounding: nếu output giới hạn hai chữ số decimal, parse không thể khôi phục các chữ số bị bỏ.

### 12.4. Chạy ma trận JDK/locale

Ví dụ ma trận:

| Runtime | Locale | Currency | Mục tiêu |
|---|---|---|---|
| JDK tối thiểu | en-US | USD | Baseline |
| JDK đích | en-US | USD | Phát hiện đổi mặc định |
| JDK đích | vi-VN | VND | Hiển thị thị trường Việt Nam |
| JDK đích | de-DE | EUR | Kiểm tra decimal comma/grouping |
| JDK đích | fr-FR | EUR | Kiểm tra Unicode whitespace |
| JDK đích | en-US | JPY | Kiểm tra fraction digits theo currency |

Các locale/currency chỉ là ví dụ; bộ kiểm thử phải chọn theo thị trường và contract thực tế. Với JDK đích, còn cần đối chiếu trên các update/vendor đã cam kết hỗ trợ nếu kết quả chính xác phụ thuộc dữ liệu provider.

## 13. Những lỗi thường gặp

### 13.1. Không chỉ định locale khi in báo cáo

~~~java
String text = NumberFormat.getInstance().format(amount);
~~~

Nếu báo cáo cần format `de-DE` nhưng server chạy mặc định `en-US`, output sẽ không đúng kỳ vọng. Giải pháp là truyền `Locale` do sản phẩm quyết định, không sửa global default theo từng request.

### 13.2. Coi dấu chấm luôn là dấu thập phân

Một chuỗi `1.234` có thể có nghĩa khác nhau. Phải xác định locale của input; với API máy đọc nên dùng định dạng canonical.

### 13.3. Lưu chuỗi có grouping thay vì số

Lưu `"1,234.56"` rồi parse bằng locale khác sẽ tạo lỗi hoặc sai giá trị. Lưu numeric/decimal canonical và currency code; chỉ format khi hiển thị.

### 13.4. Dùng double để tính tiền

`double` thuận tiện cho nhiều bài toán số, nhưng phép tính tài chính chính xác theo thập phân thường cần `BigDecimal` hoặc minor units với policy rõ ràng.

### 13.5. Sử dụng currency symbol làm ID

Ký hiệu tiền không duy nhất và có thể đổi theo locale. Dùng currency code làm identifier trong giao thức và database.

### 13.6. Sửa snapshot bằng cách xóa mọi whitespace

Cách này che giấu khác biệt Unicode có thể có ý nghĩa đối với UI và không giải quyết vấn đề nguồn dữ liệu. Cần phân biệt visual formatting với canonical serialization.

### 13.7. Dùng một NumberFormat instance cho tất cả thread

`NumberFormat` và `DecimalFormat` có trạng thái mutable; việc tái sử dụng mà không kiểm soát đồng thời có thể sinh sai kết quả hoặc lẫn cấu hình giữa request.

### 13.8. Giả định locale chỉ ảnh hưởng dấu phân cách

Locale còn có thể tác động hệ chữ số, thứ tự, ký hiệu âm, currency pattern và các quy tắc khác. Một chỉnh sửa thay dấu chấm/phẩy thủ công không tương đương locale-aware formatting.

### 13.9. Ép một provider cũ mà không kiểm tra JDK đích

Cấu hình `java.locale.providers` là phụ thuộc runtime. Có provider cũ không tồn tại trong JDK đích; ngay cả provider CLDR cũng có dữ liệu cập nhật qua phiên bản.

### 13.10. Dùng Locale.ROOT cho dữ liệu tiền giao dịch

Root locale không xác định currency và precision nghiệp vụ. Dữ liệu giao dịch cần code tiền, amount chính xác và schema rõ ràng.

### 13.11. Chỉ test một locale trên máy developer

Một lỗi về grouping, no-break space hoặc dấu âm có thể chỉ xuất hiện với locale nhất định. Cần test ma trận thực tế, bao gồm production runtime và container.

## 14. Tình huống migration tổng hợp

Giả sử dịch vụ hóa đơn ban đầu chạy trên JDK cũ và xuất CSV bằng:

~~~java
String row = orderId + "," +
        NumberFormat.getCurrencyInstance().format(total);
~~~

Khi nâng JDK hoặc thay container image:

- Locale mặc định đổi.
- Currency output chứa dấu phẩy, phá cấu trúc CSV vì chưa được escape.
- Ký hiệu currency xuất hiện trước/sau số khác trước.
- Số được group bằng một Unicode space không giống space thường.
- Đối tác parse giá tiền từ text không còn đọc được.
- Unit test logic tính tổng vẫn xanh.

Vấn đề cốt lõi không phải CLDR “sai”; ứng dụng đã dùng **format trình bày như dữ liệu giao thức**.

Một thiết kế tốt hơn:

~~~java
import java.math.BigDecimal;

public record InvoiceAmount(
        BigDecimal amount,
        String currencyCode) {
}
~~~

Xuất CSV có các cột tách biệt và quy ước canonical:

~~~text
invoice_id,amount,currency
INV-001,1234567.89,USD
~~~

Khi hiển thị hóa đơn cho người dùng, dùng locale tường minh:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
NumberFormat view = NumberFormat.getCurrencyInstance(locale);
view.setCurrency(Currency.getInstance("USD"));
String displayAmount =
        view.format(new BigDecimal("1234567.89"));
~~~

Thiết kế này tách:

1. **Giá trị** `1234567.89`.
2. **Đơn vị** `USD`.
3. **Biểu diễn UI** phụ thuộc `vi-VN` và JDK/provider.

Cần test CSV với consumer đối tác và test UI với locale/JDK mục tiêu. Nếu CSV cần hỗ trợ ký tự phức tạp ở các cột khác, dùng writer CSV chuẩn để xử lý escape/quote; ví dụ trên chỉ minh họa ba cột đơn giản.

## 15. Hướng dẫn chọn chiến lược theo mục tiêu

| Mục tiêu | Khuyến nghị |
|---|---|
| UI đa ngôn ngữ | Truyền locale theo user/request; dùng NumberFormat |
| Hóa đơn hoặc chứng từ theo thị trường | Locale tường minh, currency tường minh, business rounding, golden tests |
| Dữ liệu DB | Numeric decimal/minor units và currency code riêng |
| API JSON | Decimal canonical theo schema + currency code; tránh format presentation |
| CSV tích hợp | Không grouping, decimal separator thống nhất; escape CSV đúng |
| Parser input người dùng | NumberFormat theo locale, kiểm tra parse hết và validation |
| Financial calculation | BigDecimal và rounding policy rõ |
| Log/observability | Structured fields hoặc canonical numeric values |
| Regression qua JDK | So sánh output + code points + provider/JDK metadata |
| Xử lý thay đổi CLDR | Phân loại hợp đồng, sửa design/test hoặc duyệt output mới |
| Kết quả UI “y hệt mọi JDK” | Tự quản lý quy tắc/data version ở phạm vi cần thiết; không mặc định có bảo đảm từ runtime |

## 16. Checklist trước khi tuyên bố tương thích

### Locale và môi trường

- [ ] Đã ghi JDK vendor, version, locale provider và container/OS.
- [ ] Đã ghi `Locale.getDefault()` và hai category `DISPLAY`, `FORMAT`.
- [ ] Đã kiểm tra property `java.locale.providers` khi hệ thống sử dụng.
- [ ] Đã xác nhận locale từ request/user hoặc cấu hình nghiệp vụ.
- [ ] Đã phân biệt locale với timezone, charset và currency.

### Định dạng số

- [ ] Đã kiểm tra grouping separator và decimal separator trên locale mục tiêu.
- [ ] Đã kiểm tra khoảng trắng Unicode bằng code points khi output khác.
- [ ] Đã kiểm tra số âm, zero, giá trị lớn/nhỏ và rounding.
- [ ] Đã kiểm tra `DecimalFormatSymbols` và pattern tùy chỉnh nếu có.
- [ ] Đã tách format UI khỏi định dạng máy đọc.

### Tiền tệ

- [ ] Amount chính xác được tách khỏi currency code.
- [ ] Không lưu currency symbol như định danh duy nhất.
- [ ] Đã xác định precision và rounding policy theo nghiệp vụ.
- [ ] Không tính tiền bằng cách parse ngược chuỗi tiền hiển thị.
- [ ] Đã kiểm tra currency fraction digits và ngoại lệ phù hợp.
- [ ] Đã kiểm tra output tiền tệ trên các thị trường được hỗ trợ.

### Migration và test

- [ ] Đã thu output baseline trên JDK nguồn.
- [ ] Đã chạy cùng case trên JDK đích và ghi lại code points.
- [ ] Đã phân biệt thay đổi CLDR/provider với thay đổi dependency.
- [ ] Đã kiểm tra parser tiêu thụ hết input và xử lý dữ liệu không hợp lệ.
- [ ] Đã chạy integration test cho CSV, JSON, DB, report và client.
- [ ] Đã kiểm tra thread safety của formatter.
- [ ] Đã ghi rõ golden string nào cần ổn định và vì sao.
- [ ] Đã có kế hoạch rollout/rollback nếu thay đổi ảnh hưởng giao dịch.

## Kết luận

`Locale` quyết định ngữ cảnh định dạng; **CLDR** cung cấp dữ liệu quốc tế hóa; `NumberFormat` và `DecimalFormat` biến số thành chuỗi phù hợp locale; `Currency` định danh đơn vị tiền và mang metadata liên quan. Khi nâng JDK, những thành phần này có thể cho kết quả khác dù source và bytecode không đổi. Đó là một dạng **behavioral compatibility risk**.

Để nâng cấp an toàn, hãy truyền locale và currency tường minh cho các chức năng hiển thị, giữ amount bằng kiểu chính xác như `BigDecimal`, tách dữ liệu máy đọc khỏi chuỗi trình bày, và kiểm thử trên JDK/provider thực tế. Với output cần bất biến, định nghĩa format như một hợp đồng riêng có version và golden tests; không kỳ vọng default locale hay dữ liệu CLDR của mọi JDK giữ nguyên mãi mãi.

