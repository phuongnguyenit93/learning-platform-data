# NumberFormat.getCurrencyInstance và setCurrency

Trong Java, `NumberFormat.getCurrencyInstance(...)` tạo bộ định dạng số tiền theo **quy ước hiển thị của một locale**; `setCurrency(...)` cho phép gắn **loại tiền tệ cụ thể** vào bộ định dạng đó. Hai thông tin này liên quan nhưng **không đồng nhất**:

- **`Locale`** trả lời: người đọc mong đợi kiểu hiển thị nào (vị trí ký hiệu tiền, dấu thập phân, dấu phân nhóm, chữ số và một số quy tắc trình bày)?
- **`Currency`** trả lời: giá trị được định danh bằng **đồng tiền nào**, chẳng hạn `USD`, `EUR`, `JPY` hay `VND`?
- **Giá trị số** trả lời: số tiền là bao nhiêu, trước khi làm tròn để trình bày.
- **Quy tắc nghiệp vụ** trả lời: có cần quy đổi tỷ giá, làm tròn tại bước tính hay yêu cầu số chữ số lẻ riêng hay không?

Ví dụ một khách hàng dùng giao diện tiếng Anh Mỹ có thể thanh toán **100 EUR**, còn một khách hàng tại Đức có thể xem một khoản **100 USD**. Vì vậy, không nên coi tiền tệ mặc định suy ra từ locale luôn là tiền tệ thực sự của giao dịch.

Bài học giải thích cách tạo currency formatter, thay currency với `setCurrency`, quản lý số chữ số thập phân, ký hiệu và rounding, cùng cách tránh nhầm **format tiền** với **quy đổi tiền**. Ví dụ dùng Java 17+.

## 1. Đối tượng liên quan và vai trò

| API | Vai trò | Lưu ý |
| --- | --- | --- |
| `java.text.NumberFormat` | Kiểu trừu tượng để format/parse số | Có các factory theo locale |
| `NumberFormat.getCurrencyInstance(locale)` | Tạo formatter tiền theo locale | Thường mang đồng tiền mặc định của locale |
| `NumberFormat.getCurrencyInstance()` | Tạo formatter tiền theo default locale của category `FORMAT` | Không phù hợp khi cần locale riêng cho mỗi người dùng |
| `NumberFormat.setCurrency(currency)` | Đổi đồng tiền gắn với formatter | **Không tự cập nhật min/max fraction digits** |
| `NumberFormat.getCurrency()` | Đọc đồng tiền đang gắn | Không phải API đổi tỷ giá |
| `java.util.Currency` | Đại diện đồng tiền theo mã ISO 4217 | Ví dụ `Currency.getInstance("EUR")` |
| `Currency.getDefaultFractionDigits()` | Số chữ số lẻ thường dùng của đồng tiền | Có thể trả `-1` cho trường hợp không áp dụng |
| `java.text.DecimalFormat` | Triển khai phổ biến, cho phép pattern chi tiết | Mutable, không bảo đảm thread-safe |
| `java.text.DecimalFormatSymbols` | Bộ ký hiệu hiển thị theo locale | Ký hiệu tiền và phân cách có thể khác theo môi trường |

Có thể xem `getCurrencyInstance` là **factory chọn cấu hình hiển thị ban đầu**, còn `setCurrency` là **thao tác sửa một phần cấu hình trên formatter đã tạo**.

## 2. Tạo currency formatter theo locale

Hai overload:

~~~java
NumberFormat byDefault = NumberFormat.getCurrencyInstance();
NumberFormat byLocale =
        NumberFormat.getCurrencyInstance(Locale.US);
~~~

Đây là **snippet trong phương thức**, với import `java.text.NumberFormat` và `java.util.Locale`.

- Overload **không tham số** phụ thuộc mặc định locale dành cho định dạng tại thời điểm gọi. Trên máy khác nhau hoặc trong server có default thay đổi, đầu ra có thể khác.
- Overload **nhận `Locale`** cho phép xác định rõ quy ước trình bày. Ví dụ `Locale.US` thường có đồng tiền mặc định `USD` và dùng dấu `$`, dấu thập phân `.`, dấu phân nhóm `,`.
- Formatter được tạo có cấu hình về tiền tệ, số chữ số lẻ, dấu âm và các ký hiệu phụ thuộc locale/provider.

Tạo tệp **`CurrencyInstanceDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

public class CurrencyInstanceDemo {
    public static void main(String[] args) {
        NumberFormat us = NumberFormat.getCurrencyInstance(Locale.US);

        System.out.println(us.getCurrency().getCurrencyCode());
        System.out.println(us.getMinimumFractionDigits());
        System.out.println(us.getMaximumFractionDigits());
        System.out.println(us.format(new BigDecimal("1234.50")));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CurrencyInstanceDemo.java
java CurrencyInstanceDemo
~~~

Kết quả trên JDK có dữ liệu locale Mỹ thông dụng:

~~~text
USD
2
2
$1,234.50
~~~

`NumberFormat.getCurrencyInstance(Locale.US)` dùng cả **quy tắc định dạng** và **currency mặc định** phù hợp với locale. Nhưng một giao dịch có đồng tiền `EUR` không nên được đổi thành USD chỉ vì người xem có `Locale.US`.

**Quan trọng:** Ký hiệu tiền, khoảng trắng Unicode, cách thể hiện giá trị âm và một số mẫu có thể khác giữa các locale hoặc phiên bản JDK/CLDR. Không biến một ví dụ chuỗi ở một locale thành quy tắc chung cho mọi locale.

## 3. `Currency`: mã tiền không phải locale

`java.util.Currency` đại diện cho đơn vị tiền tệ theo mã như:

~~~java
Currency usd = Currency.getInstance("USD");
Currency eur = Currency.getInstance("EUR");
Currency jpy = Currency.getInstance("JPY");
Currency vnd = Currency.getInstance("VND");
~~~

Đây là **snippet**, cần import `java.util.Currency`. Currency được nhận diện bằng **mã**, không bằng cách tự suy ra từ tên người dùng hoặc ký hiệu như `$`. Dấu `$` có thể gắn với nhiều đồng tiền trong nhiều bối cảnh; chỉ nhìn ký hiệu không đủ để khẳng định ISO currency code.

`Currency.getInstance("USD")` lấy đối tượng đại diện USD, không tạo formatter và không làm thay đổi bất kỳ giá trị tiền nào. Nếu đưa mã không hợp lệ vào API này, Java có thể ném `IllegalArgumentException`; vì vậy đầu vào từ API/người dùng cần được kiểm tra.

`Currency.getInstance(Locale.US)` có thể lấy currency của vùng quốc gia trong locale; đó là **mặc định theo vùng**, không phải luôn là loại tiền được ghi trong hóa đơn. Các locale không xác định quốc gia phù hợp có thể không có currency xác định hoặc không được chấp nhận bởi đường tra cứu này; không dựa vào nó để suy ra currency giao dịch.

### Currency code, ký hiệu và tên hiển thị

- `getCurrencyCode()`: mã ổn định hơn để lưu/truyền dữ liệu, ví dụ `USD`.
- `getSymbol(locale)`: ký hiệu dùng khi hiển thị cho người đọc tại locale cụ thể; không phải mã giao dịch duy nhất.
- `getDisplayName(locale)`: tên hiển thị theo locale nếu dữ liệu runtime có hỗ trợ.
- `getDefaultFractionDigits()`: số chữ số thập phân thường dùng khi hiển thị đồng tiền.

**Không lưu chỉ chuỗi đã format** như `"$1,234.50"` làm dữ liệu tiền gốc; nó phụ thuộc cách hiển thị. Thay vào đó, lưu **số lượng**, **currency code** và các thông tin nghiệp vụ cần thiết.

## 4. `setCurrency` đổi đơn vị được hiển thị, không đổi giá trị số

Ví dụ:

~~~java
NumberFormat formatter =
        NumberFormat.getCurrencyInstance(Locale.US);

formatter.setCurrency(Currency.getInstance("EUR"));

String text = formatter.format(new BigDecimal("1234.50"));
~~~

Đây là **snippet**, cần import `NumberFormat`, `Locale`, `Currency` và `BigDecimal`. Với formatter hỗ trợ currency formatting, `setCurrency` chuyển currency metadata/ký hiệu dùng để hiển thị sang EUR trong khuôn trình bày của `Locale.US`.

**Nó không thực hiện:**

1. Chuyển `1234.50 USD` thành một lượng EUR theo tỷ giá.
2. Tra cứu tỷ giá hối đoái.
3. Thay thế phép tính thuế, chiết khấu hoặc quy tắc kế toán.
4. Tự cập nhật mọi cấu hình chữ số lẻ của formatter.
5. Đổi `Locale.US` thành `Locale.GERMANY`.

Nếu một số `1234.50` thực chất là USD nhưng code gọi `setCurrency(EUR)` rồi format chính số ấy, kết quả sẽ **gắn nhãn EUR cho con số USD** — một lỗi nghiệp vụ nghiêm trọng. Chỉ gọi `setCurrency` khi **đơn vị của dữ liệu số thực sự là currency được gắn**, hoặc sau khi hệ thống đã thực hiện phép quy đổi đúng.

## 5. Điểm dễ bỏ sót nhất: `setCurrency` không tự đổi số chữ số lẻ

Mỗi đồng tiền có số chữ số lẻ thông dụng khác nhau:

- `USD` thường có 2 chữ số sau dấu thập phân.
- `EUR` thường có 2 chữ số.
- `JPY` và `VND` thường có 0 chữ số theo dữ liệu currency của JDK.
- Một số đồng tiền có 3 chữ số lẻ.

Điểm mấu chốt trong Java: gọi `setCurrency(Currency)` **không tự điều chỉnh** `getMinimumFractionDigits()` và `getMaximumFractionDigits()` của formatter đã tồn tại.

Hãy xem ví dụ **`SetCurrencyDigitsDemo.java`**:

~~~java
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class SetCurrencyDigitsDemo {
    public static void main(String[] args) {
        NumberFormat formatter =
                NumberFormat.getCurrencyInstance(Locale.US);

        Currency yen = Currency.getInstance("JPY");

        System.out.println("Before: " +
                formatter.getCurrency().getCurrencyCode() + " / " +
                formatter.getMinimumFractionDigits() + " / " +
                formatter.getMaximumFractionDigits());

        formatter.setCurrency(yen);

        System.out.println("After: " +
                formatter.getCurrency().getCurrencyCode() + " / " +
                formatter.getMinimumFractionDigits() + " / " +
                formatter.getMaximumFractionDigits());

        System.out.println("JPY standard digits: " +
                yen.getDefaultFractionDigits());

        int digits = yen.getDefaultFractionDigits();
        if (digits >= 0) {
            formatter.setMinimumFractionDigits(digits);
            formatter.setMaximumFractionDigits(digits);
        }

        System.out.println("Adjusted: " +
                formatter.getMinimumFractionDigits() + " / " +
                formatter.getMaximumFractionDigits());
    }
}
~~~

~~~bash
javac SetCurrencyDigitsDemo.java
java SetCurrencyDigitsDemo
~~~

Kết quả với JDK thông dụng:

~~~text
Before: USD / 2 / 2
After: JPY / 2 / 2
JPY standard digits: 0
Adjusted: 0 / 0
~~~

Giải thích:

- Factory ban đầu tạo formatter tiền theo Mỹ/`USD`, với 2 chữ số lẻ.
- `setCurrency(JPY)` đổi currency sang JPY nhưng **giữ nguyên 2/2**.
- Muốn mặc định **không hiện phần lẻ** theo JPY, chương trình lấy `yen.getDefaultFractionDigits()` rồi đặt cả min/max về 0.

Trong ví dụ minh họa, nếu format `1234.5` **ngay sau** `setCurrency(JPY)` nhưng **trước** khi chỉnh digits, formatter vẫn có thể hiển thị phần lẻ hai chữ số, cùng ký hiệu JPY. Điều đó khác với formatter được tạo từ `Locale.JAPAN` ngay từ đầu, vốn thường có 0 chữ số lẻ cho JPY.

**Tại sao có kiểm tra `digits >= 0`?** `Currency.getDefaultFractionDigits()` có thể trả `-1` cho các mã không có quy tắc chữ số lẻ áp dụng. Khi gặp tình huống này, ứng dụng cần quyết định quy tắc riêng thay vì truyền `-1` vào mọi setter mà không kiểm tra.

### Có phải luôn ép theo currency mặc định không?

Không. `getDefaultFractionDigits()` là **giá trị thông dụng** của currency, không phải thay thế cho mọi quy tắc hạch toán. Một hệ thống có thể cần độ chính xác nội bộ cao hơn, hoặc một sản phẩm chứng khoán/tỷ giá cần 4–8 chữ số thập phân.

Hãy tách:
- **Độ chính xác tính toán/lưu trữ**: theo quy tắc nghiệp vụ.
- **Độ chính xác hiển thị**: theo currency, loại giao dịch và yêu cầu người dùng.
- **Quy tắc làm tròn**: được xác định tường minh, tránh làm tròn lặp không chủ ý.

## 6. So sánh tạo formatter theo currency của locale với thay currency

Hai trường hợp:

~~~java
NumberFormat japan =
        NumberFormat.getCurrencyInstance(Locale.JAPAN);

NumberFormat usWithYen =
        NumberFormat.getCurrencyInstance(Locale.US);

usWithYen.setCurrency(Currency.getInstance("JPY"));
~~~

Cả hai có thể đều mang `Currency JPY`, nhưng **không tương đương toàn bộ cấu hình**:

| Thuộc tính | `getCurrencyInstance(Locale.JAPAN)` | `getCurrencyInstance(Locale.US)` rồi `setCurrency(JPY)` |
| --- | --- | --- |
| Ngữ cảnh locale | Nhật Bản | Mỹ |
| Currency sau tạo/cấu hình | JPY | JPY |
| Số chữ số lẻ ban đầu thông dụng | 0 | 2, vẫn giữ 2 sau `setCurrency` |
| Dấu phân cách, vị trí ký hiệu | Theo mẫu Nhật | Theo mẫu Mỹ |
| Kiểu số âm/space | Theo dữ liệu locale Nhật | Theo dữ liệu locale Mỹ |

Vì vậy, **cùng currency không đồng nghĩa cùng cách hiển thị**. Một khách hàng người Mỹ nhìn số tiền JPY có thể muốn cách đặt ký hiệu và dấu nhóm theo tiếng Anh Mỹ, trong khi khách hàng Nhật muốn cách hiển thị khác.

Khi doanh nghiệp cần **định dạng độc lập theo locale người đọc và currency của giao dịch**, hãy thiết kế hai tham số riêng thay vì cố lấy mọi thông tin từ một `Locale`.

## 7. Ví dụ thiết kế một hàm định dạng tiền với hai tham số độc lập

Một hàm service nên nhận **số tiền**, **currency** và **locale** rõ ràng, thay vì đọc mặc định toàn JVM.

Tạo **`CurrencyDisplayService.java`**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class CurrencyDisplayService {
    public static String format(
            BigDecimal amount,
            Currency currency,
            Locale locale) {

        NumberFormat formatter =
                NumberFormat.getCurrencyInstance(locale);

        formatter.setCurrency(currency);

        int digits = currency.getDefaultFractionDigits();
        if (digits >= 0) {
            formatter.setMinimumFractionDigits(digits);
            formatter.setMaximumFractionDigits(digits);
        }

        formatter.setRoundingMode(RoundingMode.HALF_UP);
        return formatter.format(amount);
    }

    public static void main(String[] args) {
        Currency usd = Currency.getInstance("USD");
        Currency jpy = Currency.getInstance("JPY");

        BigDecimal amount = new BigDecimal("1234.50");

        System.out.println(format(amount, usd, Locale.US));
        System.out.println(format(amount, jpy, Locale.US)
                .endsWith(".50"));
    }
}
~~~

~~~bash
javac CurrencyDisplayService.java
java CurrencyDisplayService
~~~

Kết quả với locale Mỹ thông dụng:

~~~text
$1,234.50
false
~~~

Dòng thứ hai chỉ in **boolean** để minh họa JPY đã không còn hậu tố `.50`. Ký hiệu JPY thực tế có thể phụ thuộc locale và JDK/provider nên ví dụ không hardcode chuỗi ký hiệu yen vào stdout.

**Cần hiểu đúng phương thức trên:** Đây là helper **định dạng** minh họa, không phải quy trình quy đổi. Nó mặc định chính sách “hiển thị đúng số chữ số lẻ thông dụng của currency” và `HALF_UP`. Nếu nghiệp vụ cần `HALF_EVEN`, giữ nhiều chữ số hơn hoặc hiển thị số thập phân tùy chọn, phải điều chỉnh chính sách tương ứng.

Có thể đặt quy tắc hiển thị ở một lớp chuyên biệt, ví dụ `MoneyDisplayPolicy`, thay vì áp dụng mọi nghiệp vụ với một rounding mode duy nhất.

## 8. `setCurrency` ảnh hưởng ký hiệu như thế nào?

Trong các triển khai currency formatter phổ biến của Java, `setCurrency` cập nhật currency mà formatter sử dụng để hiển thị. Với `DecimalFormat`, nó còn cập nhật các biểu diễn liên quan đến ký hiệu tiền trong `DecimalFormatSymbols` được quản lý.

Một số ví dụ về phần tiền hiển thị:

- Với locale Mỹ và currency USD, kết quả thường có ký hiệu `$` đứng trước số.
- Với locale Đức và currency EUR, dấu decimal là dấu phẩy, grouping thường là dấu chấm, và ký hiệu thường đứng sau số kèm khoảng trắng phù hợp.
- Với locale Mỹ nhưng currency EUR, formatter vẫn có thể dùng **thứ tự/dấu phân cách kiểu Mỹ**, chỉ phần ký hiệu/mã tiền thay đổi.

Ví dụ **`CurrencyCodeDemo.java`**:

~~~java
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class CurrencyCodeDemo {
    public static void main(String[] args) {
        NumberFormat us = NumberFormat.getCurrencyInstance(Locale.US);
        System.out.println(us.getCurrency().getCurrencyCode());

        us.setCurrency(Currency.getInstance("EUR"));
        System.out.println(us.getCurrency().getCurrencyCode());

        System.out.println(us.getMinimumFractionDigits());
        System.out.println(us.getMaximumFractionDigits());
    }
}
~~~

~~~bash
javac CurrencyCodeDemo.java
java CurrencyCodeDemo
~~~

Kết quả:

~~~text
USD
EUR
2
2
~~~

Ví dụ chọn in **ISO currency code** thay vì biểu tượng `€` để không phụ thuộc các chi tiết locale data/Unicode của môi trường chạy.

### Ký hiệu ngắn không phải mã tiền tệ duy nhất

Dấu `$` thường có thể chỉ nhiều đồng tiền khác nhau. Nếu thông tin phải rõ ràng qua biên giới, ứng dụng có thể hiển thị **mã ISO** hoặc tên tiền tệ bên cạnh theo yêu cầu thiết kế, và luôn lưu mã currency riêng. Không tự tách currency code từ chuỗi đã format.

Trong mã nguồn, nếu cần truy xuất ký hiệu theo một locale cụ thể, có thể dùng `currency.getSymbol(locale)`; để truy xuất mã dùng `currency.getCurrencyCode()`.

## 9. Cách dùng mặc định theo locale và tác động của `Locale.getDefault()`

Nếu gọi:

~~~java
NumberFormat formatter = NumberFormat.getCurrencyInstance();
~~~

Java chọn locale định dạng mặc định của runtime tại thời điểm tạo formatter (liên quan `Locale.Category.FORMAT`). Do đó đầu ra có thể khác nếu JVM chạy ở máy khác hoặc nếu một nơi trong chương trình thay đổi default.

Lời gọi:

~~~java
NumberFormat formatter =
        NumberFormat.getCurrencyInstance(requestLocale);
~~~

lấy `requestLocale` là biến `Locale` đã xác định theo người dùng/request. Đây là cách kiểm soát locale tường minh.

**Không gọi `Locale.setDefault(...)` theo từng HTTP request để đổi currency display.** Default locale là trạng thái chia sẻ trong JVM, nên hai request đồng thời có thể gây xung đột. Việc thay default cũng không tự cập nhật những formatter đã được cache từ trước.

Nếu người dùng lưu ngôn ngữ `vi-VN` nhưng giao dịch USD, hai thông tin phải đi vào chương trình riêng: locale lựa chọn hiển thị là `vi-VN`, currency giao dịch là `USD`. Không suy ra USD là VND chỉ vì người dùng có locale Việt Nam.

## 10. Vì sao `setCurrency` không phải phép quy đổi ngoại tệ?

Giả sử dữ liệu là:

~~~text
amount = 100.00
currency = USD
~~~

Khi gọi:

~~~java
NumberFormat display =
        NumberFormat.getCurrencyInstance(Locale.US);
display.setCurrency(Currency.getInstance("EUR"));
System.out.println(display.format(100));
~~~

Đây là **snippet** với import thích hợp. Kết quả theo cách hiển thị tiền EUR, nhưng **số 100 vẫn là 100**; nó không trở thành số EUR tương đương với 100 USD.

Để **quy đổi USD → EUR** đúng về nghiệp vụ, cần có:
1. Đồng tiền nguồn và đích.
2. Tỷ giá có nguồn đáng tin, ngày/giờ áp dụng, loại tỷ giá và phí.
3. Quy tắc tính toán và làm tròn theo sản phẩm.
4. Giá trị được tính toán bằng kiểu số phù hợp, thường là `BigDecimal`.
5. Currency đích gắn với **giá trị kết quả thực sự đã quy đổi**, rồi mới format.

Không bịa một tỷ giá cố định chỉ để “định dạng”; những ví dụ trong bài cố ý không thực hiện quy đổi tiền.

## 11. Rounding mode và `BigDecimal` khi hiển thị tiền

`NumberFormat` có thể làm tròn khi số chữ số thập phân của dữ liệu vượt mức đã cấu hình. Ví dụ với formatter tiền `Locale.US`, giá trị `1234.565` cần ba chữ số lẻ, nhưng formatter hiển thị hai chữ số thì phải quyết định kết quả.

- `RoundingMode.HALF_EVEN`: tại điểm giữa chính xác, chọn chữ số cuối chẵn.
- `RoundingMode.HALF_UP`: tại điểm giữa chính xác, làm tròn tăng độ lớn.
- Các mode khác phù hợp cho các quy tắc nghiệp vụ khác nhau.

Tạo **`CurrencyRoundingDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.util.Locale;

public class CurrencyRoundingDemo {
    public static void main(String[] args) {
        NumberFormat f = NumberFormat.getCurrencyInstance(Locale.US);
        BigDecimal amount = new BigDecimal("1234.565");

        f.setRoundingMode(RoundingMode.HALF_EVEN);
        System.out.println(f.format(amount));

        f.setRoundingMode(RoundingMode.HALF_UP);
        System.out.println(f.format(amount));
    }
}
~~~

~~~bash
javac CurrencyRoundingDemo.java
java CurrencyRoundingDemo
~~~

Kết quả theo formatter USD Mỹ:

~~~text
$1,234.56
$1,234.57
~~~

`BigDecimal("1234.565")` giữ chính xác giá trị thập phân trong ví dụ. Nếu tạo `new BigDecimal(1234.565)` từ `double`, dữ liệu có thể không còn chính xác tại điểm giữa do biểu diễn nhị phân; tránh cách đó khi dạy hoặc xử lý tiền tệ.

**Lưu ý:** Format tiền chỉ tạo chuỗi để hiển thị. Doanh nghiệp thường phải làm tròn ở bước phù hợp của phép tính, không chỉ lúc render. Nếu đã làm tròn dữ liệu nghiệp vụ theo một quy tắc thì không nên vô tình làm tròn khác lần nữa mà không kiểm soát.

## 12. Phân biệt min/max fraction digits với số chữ số của currency

Có ba khái niệm:

| Thuộc tính | Câu hỏi trả lời |
| --- | --- |
| `currency.getDefaultFractionDigits()` | Đồng tiền thường hiển thị bao nhiêu chữ số lẻ? |
| `formatter.getMinimumFractionDigits()` | Khi hiển thị, phải in ít nhất bao nhiêu chữ số lẻ? |
| `formatter.getMaximumFractionDigits()` | Khi hiển thị, cho phép tối đa bao nhiêu chữ số lẻ trước khi làm tròn? |

Giả sử `JPY` có mặc định 0. Bạn vẫn có thể cấu hình formatter với min 0 / max 2 khi cần thể hiện một dữ liệu phân số theo chính sách đặc biệt. Ngược lại, nếu muốn hiện JPY không có phần lẻ, đặt cả min và max về 0.

Đừng ép mọi currency thành 2 chữ số vì USD và EUR có 2. Đồng tiền khác có thể có 0 hoặc 3 chữ số lẻ; và quy tắc thương mại riêng có thể khác số chữ số mặc định của ISO.

Khi thay cả min/max, cách diễn đạt code nên rõ ràng và kiểm tra currency hợp lệ:

~~~java
int digits = currency.getDefaultFractionDigits();
if (digits >= 0) {
    formatter.setMinimumFractionDigits(digits);
    formatter.setMaximumFractionDigits(digits);
}
~~~

Đoạn này dùng biến `formatter` và `currency` đã được tạo. Nếu dự án cần số chữ số lẻ tùy giao dịch, nên truyền tham số policy riêng thay vì luôn lấy default.

## 13. Parsing chuỗi tiền tệ: không dùng như kiểm tra toàn chuỗi mặc định

`NumberFormat.getCurrencyInstance(locale)` cũng có phương thức `parse` để đọc chuỗi theo định dạng locale/currency tương ứng. Nhưng parsing có các giới hạn quan trọng:

- Kết quả `parse` là một `Number`, không phải đối tượng `Money` tự mang currency code và quy tắc nghiệp vụ.
- Chuỗi định dạng tiền ở các locale có thể dùng dấu cách đặc biệt, dấu ngoặc cho số âm hoặc ký hiệu tiền khác nhau.
- Parsing có thể chấp nhận một **tiền tố hợp lệ** và dừng trước ký tự còn lại; đừng mặc định toàn bộ input luôn được kiểm tra.
- Ký hiệu tiền như `$` có thể mơ hồ nếu không có ngữ cảnh currency.

Ví dụ kiểm chứng vị trí parser:

~~~java
NumberFormat f = NumberFormat.getCurrencyInstance(Locale.US);
String input = "$1,234.50xxx";
ParsePosition pos = new ParsePosition(0);
Number n = f.parse(input, pos);

System.out.println(n);
System.out.println(pos.getIndex() == input.length());
~~~

Đây là **snippet trong phương thức**, cần import `java.text.NumberFormat`, `java.text.ParsePosition` và `java.util.Locale`. Với JDK locale Mỹ thông dụng, parser đọc được phần đầu và có thể bỏ lại hậu tố; kết quả boolean không được mặc định là true. Muốn xác thực, kiểm tra `n != null`, `pos.getErrorIndex()` và `pos.getIndex() == input.length()`.

Đối với API thanh toán, cách vững chắc hơn thường là nhận **số dạng chuẩn hóa và currency code riêng** (ví dụ trong DTO), xác thực chúng, rồi format chỉ ở tầng trình bày. Đừng dựa vào chuỗi hiển thị người dùng làm dữ liệu tính toán đáng tin.

## 14. Có nên ép kiểu sang `DecimalFormat`?

Trong các JDK phổ biến, `getCurrencyInstance` thường trả về một đối tượng `DecimalFormat`. Điều đó cho phép tùy chỉnh pattern hoặc `DecimalFormatSymbols`:

~~~java
NumberFormat general =
        NumberFormat.getCurrencyInstance(Locale.US);

if (general instanceof DecimalFormat decimal) {
    // Có thể cấu hình những chức năng đặc thù của DecimalFormat.
    System.out.println(decimal.toPattern());
}
~~~

Đây là **snippet**, cần import `NumberFormat`, `DecimalFormat` và `Locale`. Cú pháp `instanceof ... decimal` là pattern variable hỗ trợ trong Java 17+.

**Không ép kiểu vô điều kiện** chỉ để gọi `setCurrency`, vì `setCurrency` đã có ngay trên `NumberFormat`. Trong môi trường có locale service provider tùy biến hoặc lớp formatter khác, việc cast cứng có thể gây `ClassCastException`. Chỉ dùng chức năng riêng của `DecimalFormat` khi cần và khi đã kiểm tra kiểu triển khai.

Nếu dùng pattern `¤#,##0.00` trong `DecimalFormat`, ký hiệu `¤` liên quan đến việc hiển thị currency. Tuy nhiên chỉnh pattern có thể thay đổi cách đặt ký hiệu và số chữ số lẻ, không thay thế chính sách currency/locale do sản phẩm đã xác định.

## 15. Thread safety và vòng đời formatter

`NumberFormat` và `DecimalFormat` là những formatter **mutable** và không bảo đảm an toàn khi cùng instance được truy cập đồng thời từ nhiều luồng mà không đồng bộ. `setCurrency` cũng là một thao tác **thay đổi trạng thái**.

Đoạn code sau rất dễ sai trong HTTP server:

~~~java
// Ví dụ KHÔNG nên dùng chung cho nhiều request:
static final NumberFormat SHARED =
        NumberFormat.getCurrencyInstance(Locale.US);
~~~

Nếu request A gọi `SHARED.setCurrency(USD)` rồi request B gọi `SHARED.setCurrency(EUR)` trước khi A format, A có thể nhận chuỗi có ký hiệu tiền của B. Nếu đồng thời sửa min/max fraction digits, rounding mode và pattern, kết quả còn khó kiểm soát hơn.

Các lựa chọn an toàn:

1. **Tạo instance mới theo lần sử dụng** hoặc theo request. Cách này rõ ràng và thường là điểm khởi đầu tốt.
2. Nếu có cache, ưu tiên cache **cấu hình bất biến** (locale, currency, rounding policy, fraction digits) rồi tạo formatter mutable khi dùng.
3. Nếu thật sự chia sẻ instance, cần đồng bộ toàn bộ chuỗi thao tác cấu hình + format, nhưng thiết kế này dễ thành điểm nghẽn và cần đo đạc.
4. Có thể cân nhắc bản sao formatter đã cấu hình hoặc cơ chế theo thread, với chính sách vòng đời rõ ràng, tránh rò rỉ ngữ cảnh request giữa tác vụ.

Không dùng `Locale.setDefault(...)` để thay currency cho các request đồng thời. Default locale là trạng thái chung, và đổi default cũng không tự thay đổi tất cả formatter đã tạo.

## 16. Những lỗi phổ biến

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Dùng `getCurrencyInstance(Locale.US)` và nghĩ mọi số đều là USD | Locale chỉ định cấu hình ban đầu | Truyền currency thật của giao dịch |
| Gọi `setCurrency(EUR)` để “đổi USD sang EUR” | Không có phép nhân tỷ giá | Quy đổi nghiệp vụ trước, format sau |
| Gọi `setCurrency(JPY)` rồi nghĩ decimals tự về 0 | Min/max fraction digits giữ nguyên | Đặt min/max theo policy rõ ràng |
| Hiển thị 2 chữ số cho mọi currency | Có currency 0 hoặc 3 chữ số lẻ | Kiểm tra `getDefaultFractionDigits()` và yêu cầu nghiệp vụ |
| Lưu `"$1,234.50"` làm tiền gốc | Phụ thuộc locale, dấu phân cách và ký hiệu | Lưu số + currency code |
| Parse văn bản format để lấy lại currency code | `Number` không mang đơn vị tiền | Lưu/tra currency code độc lập |
| Dùng `double` để biểu diễn giá tiền cần chính xác | Sai số nhị phân có thể ảnh hưởng tính toán | Cân nhắc `BigDecimal` |
| Hardcode `$` cho mọi USD ở mọi locale | Ký hiệu/spacing có thể thay đổi | Dùng formatter với locale tường minh |
| Dùng chung `NumberFormat` mutable giữa nhiều thread | Có thể gây race và rò rỉ currency | Tạo formatter riêng hoặc đồng bộ chặt |
| Đổi default JVM ở từng request | Trạng thái JVM dùng chung | Truyền `Locale` tường minh |

Một lỗi đặc biệt nguy hiểm: **sai đơn vị tiền nhưng chuỗi nhìn vẫn hợp lệ**. `€1,234.50` trông giống số tiền bình thường, song nếu thực chất con số là USD chưa quy đổi thì lỗi nằm ở dữ liệu và nghiệp vụ, không phải ở formatter.

## 17. Checklist kiểm thử thực tế

Nên có các kiểm thử sau:

- **Khởi tạo theo locale:** `Locale.US` chọn USD và định dạng số theo kiểu Mỹ; `Locale.JAPAN` chọn JPY và số chữ số lẻ thông dụng khác.
- **Thay currency:** từ formatter USD sang JPY bằng `setCurrency`, xác nhận mã tiền đổi nhưng số chữ số lẻ **chưa tự đổi**.
- **Áp dụng policy:** sau khi đặt min/max theo JPY, kiểm tra phần lẻ được xử lý như mong đợi.
- **Khác locale, cùng currency:** USD được hiển thị khác nhau ở `en-US` và `de-DE`; không thay đổi giá trị số.
- **Cùng locale, khác currency:** `en-US` có thể hiển thị USD và EUR nhưng phải phân biệt rõ đồng tiền thật.
- **Rounding boundary:** thử `1.005`, `1.015` hoặc giá trị chính xác với `BigDecimal` để kiểm tra mode.
- **Null/invalid currency:** kiểm tra đầu vào và không để thông báo lỗi khó hiểu từ cấu hình sai.
- **ISO code:** lưu và trả mã tiền chính xác theo giao dịch.
- **Concurrency:** hai request dùng currency khác nhau không làm thay đổi formatter của nhau.
- **Parse:** nếu chấp nhận chuỗi hiển thị làm đầu vào, kiểm tra đã tiêu thụ hết chuỗi và dấu phân cách đúng locale.
- **Runtime data:** khi cập nhật JDK/provider, đánh giá thay đổi ký hiệu, dấu cách Unicode, vị trí ký hiệu và số chữ số.

Đối với snapshot test chuỗi localized, nên kiểm soát phiên bản JDK/locale provider. Đừng xem ký tự khoảng trắng thông thường (`U+0020`) giống hệt khoảng trắng không ngắt (`U+00A0`) hay khoảng trắng hẹp không ngắt (`U+202F`).

## 18. Bài tập có đáp án

**Câu 1.** `NumberFormat.getCurrencyInstance(Locale.US)` thường chọn currency nào?

**Đáp án:** `USD`, theo quy ước mặc định của locale Mỹ. Đây là currency **khởi tạo**, không nhất thiết là currency của một hóa đơn cụ thể.

**Câu 2.** Gọi `formatter.setCurrency(Currency.getInstance("JPY"))` trên formatter USD với min/max=2. Sau đó min/max có tự thành 0 không?

**Đáp án:** **Không**. `setCurrency` không tự cập nhật số chữ số lẻ. Cần thiết lập theo yêu cầu hiển thị.

**Câu 3.** Nếu người dùng dùng tiếng Đức nhưng thanh toán bằng USD, nên dùng locale và currency nào?

**Đáp án:** Chọn locale của người đọc, ví dụ `Locale.GERMANY`, và currency giao dịch `USD`; không tự đổi USD thành EUR.

**Câu 4.** `setCurrency(EUR)` có tự lấy tỷ giá USD/EUR không?

**Đáp án:** Không. Nó chỉ đổi đơn vị dùng cho **hiển thị**, không thực hiện quy đổi.

**Câu 5.** Vì sao nên lưu `Currency.getCurrencyCode()` thay vì chỉ ký hiệu `$`?

**Đáp án:** Ký hiệu có thể mơ hồ giữa nhiều đồng tiền; mã ISO giúp định danh đơn vị giao dịch rõ ràng hơn.

**Câu 6.** Hai request dùng chung `NumberFormat` và gọi `setCurrency` khác nhau. Nguy cơ là gì?

**Đáp án:** Formatter mutable có thể bị sửa giữa các thao tác của hai thread, khiến một request hiển thị currency của request khác.

**Câu 7.** Nếu `getDefaultFractionDigits()` trả `-1`, có nên ép min/max bằng giá trị đó?

**Đáp án:** Không nên áp dụng máy móc. Cần chọn chính sách hiển thị phù hợp với loại currency/nghiệp vụ.

**Câu 8.** Vì sao `BigDecimal("1234.565")` phù hợp để kiểm tra rounding hơn `new BigDecimal(1234.565)`?

**Đáp án:** Constructor từ chuỗi giữ chính xác số thập phân; constructor từ `double` có thể mang sai số nhị phân.

## 19. Tổng kết

Có thể ghi nhớ luồng sử dụng như sau:

~~~text
Số tiền gốc + Currency code + Locale người đọc
              |
              v
NumberFormat.getCurrencyInstance(locale)
              |
              v
formatter.setCurrency(currency)
              |
              v
Chọn fraction digits + rounding policy phù hợp
              |
              v
formatter.format(amount)
              |
              v
Chuỗi hiển thị theo locale và currency thực tế
~~~

**Ba nguyên tắc quan trọng nhất:**

1. **`getCurrencyInstance(locale)` quyết định cấu hình hiển thị ban đầu theo locale.**
2. **`setCurrency(currency)` thay currency nhưng không tự chuyển đổi giá trị và không tự điều chỉnh min/max fraction digits.**
3. **Currency của giao dịch, locale của người đọc và chính sách làm tròn là các dữ kiện riêng**; truyền chúng tường minh để tránh lỗi tiền tệ trong ứng dụng thực tế.

Tài liệu Java SE 17: [NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html), [Currency](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html), [DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html).