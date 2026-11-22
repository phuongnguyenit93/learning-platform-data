# Locale và dấu phân cách số

## 1. Cùng một giá trị, nhiều cách viết đúng

Giá trị một nghìn hai trăm ba mươi tư phẩy năm có thể được trình bày như:

```text
1,234.50
1.234,50
```

Nếu đọc theo đúng quy ước vùng, hai chuỗi có thể biểu diễn cùng một giá trị. Dấu chấm và dấu phẩy không có một vai trò cố định trong mọi ngôn ngữ.

`Locale` mô tả ngữ cảnh ngôn ngữ/vùng văn hóa mà một API nhạy theo vùng sử dụng. Trong định dạng số, nó ảnh hưởng các chi tiết như dấu thập phân, dấu phân nhóm và có thể cả hệ chữ số.

Điều cần tách rõ:

```text
Giá trị số
   + mẫu định dạng
   + locale
        ↓
Chuỗi để hiển thị
```

Locale thay đổi cách biểu diễn, không đổi số lượng mà giá trị biểu diễn. Bài tập trung vào Formatter/printf và các dấu phân cách, sử dụng kiến thức vẫn áp dụng trong Java hiện đại. Chương trình minh họa chạy trên Java 17 trở lên.

## 2. Hai loại dấu không có cùng chức năng

| Thành phần | Vai trò | Ví dụ theo Locale.US |
| --- | --- | --- |
| Dấu thập phân | Ngăn phần nguyên và phần lẻ | Dấu chấm trong `1234.50` |
| Dấu phân nhóm | Giúp đọc nhóm chữ số trong phần nguyên | Dấu phẩy trong `1,234.50` |

Với Locale.GERMANY trong cấu hình dữ liệu locale chuẩn dùng ở ví dụ, hai ký hiệu đổi vai trò:

```text
US:      1,234.50
Germany: 1.234,50
```

Không nên đặt tên biến là “comma” nếu ý định thực sự là “decimalSeparator”. Một tên theo vai trò giúp mã không gắn nhầm quy tắc của một vùng vào mọi người dùng.

Dấu phân nhóm là phần trình bày để con người đọc dễ hơn. Nó không phải một phần cần thêm vào mọi giá trị khi lưu trữ. Một cột số trong cơ sở dữ liệu giữ giá trị số; việc hiển thị cho người dùng mới là nơi áp dụng dấu theo locale.

## 3. Dấu phẩy và dấu chấm trong mẫu Formatter

Mẫu:

```java
"%,.2f"
```

cần đọc như sau:

- `,` là cờ yêu cầu phân nhóm.
- `.2` là độ chính xác hai chữ số sau dấu thập phân của dạng f.
- `f` yêu cầu biểu diễn dạng thập phân cố định.

Dấu phẩy trong mẫu **không yêu cầu luôn in ký tự dấu phẩy**. Nó yêu cầu sử dụng dấu phân nhóm theo locale.

Tương tự, dấu chấm trước số `2` là cú pháp của mẫu, không phải yêu cầu dấu thập phân đầu ra phải là dấu chấm.

Ví dụ:

```java
String us = String.format(
        Locale.US, "%,.2f", new BigDecimal("1234.50"));

String de = String.format(
        Locale.GERMANY, "%,.2f", new BigDecimal("1234.50"));
```

Đoạn minh họa cần import `java.util.Locale` và `java.math.BigDecimal`. Với dữ liệu locale chuẩn của môi trường ví dụ, kết quả là `1,234.50` và `1.234,50`.

Nếu bỏ cờ phân nhóm, như `"%.2f"`, phần nguyên không tự có dấu phân nhóm chỉ vì đã chọn một locale. Locale cung cấp quy ước; mẫu vẫn quyết định có yêu cầu phân nhóm hay không.

## 4. Chỉ định locale ở đúng lời gọi

Với String.format:

```java
String text = String.format(Locale.ROOT, "%.2f", amount);
```

Với PrintStream.printf:

```java
System.out.printf(Locale.US, "%,.2f%n", amount);
```

Với Formatter gắn vào một đích:

```java
StringBuilder output = new StringBuilder();
try (Formatter formatter =
             new Formatter(output, Locale.GERMANY)) {
    formatter.format("%,.2f", amount);
}
```

Đây là các đoạn minh họa có biến amount đã được định nghĩa. Cần các import tương ứng; chương trình đầy đủ nằm ở phần sau.

Một số lựa chọn thường gặp:

| Lựa chọn | Khi dùng |
| --- | --- |
| `Locale.forLanguageTag("vi-VN")` | Nội dung hiển thị theo ngữ cảnh tiếng Việt tại Việt Nam |
| `Locale.US` hoặc locale cụ thể khác | Yêu cầu hiển thị đã xác định vùng |
| `Locale.ROOT` | Cần cách định dạng trung lập, không dựa vào locale mặc định của người chạy |

Dùng `Locale.forLanguageTag` là cách hiện hành để tạo locale theo thẻ ngôn ngữ. Không cần dựa vào các constructor Locale cũ đã bị ngừng khuyến nghị ở các JDK mới.

Locale.ROOT giúp nêu rõ ý định trung lập cho lời gọi, nhưng không biến mọi mẫu thành biểu diễn hợp lệ cho máy. Ví dụ `%,.2f` với ROOT vẫn có phân nhóm. Giao thức dữ liệu có yêu cầu riêng về dấu, chữ số, độ chính xác và các giá trị đặc biệt.

## 5. Ví dụ chạy được: hiển thị và kiểm tra ký hiệu

Lưu thành `LocaleNumberDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class LocaleNumberDemo {
    private static void show(String label, Locale locale, BigDecimal value) {
        System.out.println(label + "="
                + String.format(locale, "%,.2f", value));
    }

    public static void main(String[] args) {
        BigDecimal value = new BigDecimal("1234567.89");
        Locale vietnamese = Locale.forLanguageTag("vi-VN");

        show("root", Locale.ROOT, value);
        show("us", Locale.US, value);
        show("de", Locale.GERMANY, value);
        show("vi", vietnamese, value);

        System.out.println("viWithoutGrouping="
                + String.format(vietnamese, "%.2f", value));
        System.out.println("plainValue=" + value.toPlainString());

        DecimalFormatSymbols us =
                DecimalFormatSymbols.getInstance(Locale.US);
        DecimalFormatSymbols de =
                DecimalFormatSymbols.getInstance(Locale.GERMANY);

        System.out.printf(Locale.ROOT,
                "usSymbols=decimal:U+%04X grouping:U+%04X%n",
                (int) us.getDecimalSeparator(),
                (int) us.getGroupingSeparator());

        System.out.printf(Locale.ROOT,
                "deSymbols=decimal:U+%04X grouping:U+%04X%n",
                (int) de.getDecimalSeparator(),
                (int) de.getGroupingSeparator());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 LocaleNumberDemo.java
java LocaleNumberDemo
```

Stdout với dữ liệu locale chuẩn của JDK 17 đã dùng để kiểm chứng:

```text
root=1,234,567.89
us=1,234,567.89
de=1.234.567,89
vi=1.234.567,89
viWithoutGrouping=1234567,89
plainValue=1234567.89
usSymbols=decimal:U+002E grouping:U+002C
deSymbols=decimal:U+002C grouping:U+002E
```

Đọc kết quả:

1. Bốn lần hiển thị dùng cùng đối tượng BigDecimal; dữ liệu không bị sửa.
2. Dòng viWithoutGrouping vẫn dùng dấu phẩy thập phân nhưng không có dấu phân nhóm vì mẫu không chứa cờ tương ứng.
3. `toPlainString()` của BigDecimal cho biểu diễn giá trị không dùng quy tắc hiển thị theo locale.
4. Hai dòng cuối đọc ký hiệu từ DecimalFormatSymbols và in mã Unicode bằng mẫu kỹ thuật có Locale.ROOT.

U+002E là dấu chấm; U+002C là dấu phẩy. In mã ký tự giúp tránh nhầm giữa những ký hiệu nhìn giống nhau.

Dữ liệu locale được cung cấp bởi môi trường Java và các nhà cung cấp locale; nó có thể thay đổi giữa bản phát hành hoặc cấu hình nhà cung cấp. Các dòng ví dụ là kết quả kiểm chứng trên cấu hình đã nêu, không phải cam kết rằng mọi bản Java tương lai sẽ giữ mọi chi tiết hiển thị của mọi locale.

## 6. Locale mặc định là phụ thuộc môi trường

Nếu không truyền locale:

```java
String text = String.format("%,.2f", amount);
```

thì kết quả có thể phụ thuộc locale định dạng mặc định. Điều đó giải thích một lớp lỗi phổ biến: chương trình trên máy phát triển có dấu chấm nhưng ở máy CI hoặc máy người dùng lại có dấu phẩy.

Có thể xem ngữ cảnh định dạng mặc định:

```java
Locale current = Locale.getDefault(Locale.Category.FORMAT);
System.out.println(current.toLanguageTag());
```

Kết quả đoạn này phụ thuộc môi trường nên không nên gắn một stdout duy nhất cho mọi máy.

Đừng suy ra locale người dùng chỉ từ vị trí đặt máy chủ. Một dịch vụ chạy trên máy chủ có locale tiếng Anh vẫn có thể phục vụ người dùng Việt Nam, Đức và Pháp trong các yêu cầu khác nhau. Locale hiển thị nên đi theo yêu cầu hoặc hồ sơ người dùng theo quy tắc của ứng dụng.

`Locale.setDefault` thay trạng thái toàn cục. Thay nó trong một yêu cầu hoặc một test có thể ảnh hưởng phần việc khác, đặc biệt khi chạy đồng thời. Ưu tiên truyền locale vào thao tác cần định dạng.

Nếu một test đặc biệt thực sự cần đổi mặc định, phải quản lý việc khôi phục và tránh chạy chồng với những test dùng cùng trạng thái toàn cục. Đó là ngoại lệ có kiểm soát, không phải cách cấu hình theo từng người dùng.

## 7. Dấu phân nhóm không nhất thiết là dấu cách ASCII

Một số quy ước dùng ký tự có hình dạng gần dấu cách để phân nhóm. Trong dữ liệu locale thực tế có thể gặp các ký tự như:

| Mã | Ký tự | Tính chất cần lưu ý |
| --- | --- | --- |
| U+0020 | Space | Dấu cách thông thường |
| U+00A0 | No-break space | Dấu cách không ngắt |
| U+202F | Narrow no-break space | Dấu cách không ngắt hẹp |

Ba ký tự này không bằng nhau khi so sánh String, dù trên một số phông chữ trông rất giống.

Vì vậy, khi một chuỗi định dạng “nhìn đúng” nhưng test không khớp, hãy kiểm tra mã Unicode thay vì lập tức thay mọi dấu cách. Có thể quan sát một kết quả bất kỳ:

```java
String formatted = String.format(Locale.FRANCE, "%,.2f", amount);
formatted.codePoints().forEach(
        cp -> System.out.printf(Locale.ROOT, "U+%04X ", cp));
System.out.println();
```

Đoạn minh họa cần biến amount có sẵn. Các mã thực tế phụ thuộc kết quả và dữ liệu locale của runtime; mục đích là lấy bằng chứng tại môi trường đang chẩn đoán.

Không dùng trim hoặc replace dấu cách để che khác biệt nếu chính yêu cầu hiển thị cần giữ dấu không ngắt. Nếu ứng dụng cần một kiểu ký hiệu cố định riêng, hãy thiết kế quy tắc đó rõ ràng, không coi mọi khác biệt Unicode là lỗi.

Cũng không mặc định các vùng đều nhóm chữ số theo cách giống nhau. Quy tắc hiển thị thuộc bộ dữ liệu và API được chọn; kiểm thử những vùng thực sự nằm trong phạm vi sản phẩm.

## 8. DecimalFormatSymbols giúp quan sát, không đổi cấu hình Formatter khác

`DecimalFormatSymbols.getInstance(locale)` cung cấp các ký hiệu theo locale cho hệ định dạng DecimalFormat. Nó hữu ích để hiểu dấu thập phân, dấu nhóm và chữ số.

Nhưng tạo một đối tượng symbols rồi sửa nó không tự thay các lời gọi String.format đã có:

```text
Một DecimalFormatSymbols được sửa
          ≠
Cấu hình toàn cục cho mọi Formatter
```

Nếu yêu cầu là một quy tắc số tùy biến, có thể xét DecimalFormat với symbols cấu hình riêng. Đó là API có mô hình mẫu và quyền sở hữu đối tượng riêng; không trộn cú pháp của DecimalFormat với mẫu kiểu printf.

Ví dụ `%,.2f` là mẫu Formatter. Không truyền nguyên nó cho DecimalFormat rồi mong hai lớp hiểu giống nhau.

Khi định dạng kiểu tiền tệ, phần trăm hoặc định dạng số cho người dùng ở mức cao hơn, NumberFormat có thể diễn đạt mục đích phù hợp hơn. Việc chọn locale vẫn cần rõ ràng; chọn một API khác không loại bỏ yêu cầu đó.

## 9. Hiển thị, phân tích đầu vào và trao đổi dữ liệu là ba việc khác nhau

Chuỗi `1,234` có thể được hiểu là một nghìn hai trăm ba mươi tư hoặc một phẩy hai trăm ba mươi tư, tùy hợp đồng đầu vào.

Vì vậy không sửa mọi chuỗi bằng:

```java
// Nguy hiểm nếu chưa xác định quy ước đầu vào.
input.replace(",", ".");
```

Thao tác đó không biết dấu phẩy là dấu thập phân hay dấu phân nhóm; nó có thể làm sai giá trị hoặc tạo hai dấu thập phân.

Nếu nhận số đã bản địa hóa từ người dùng, cần một bộ phân tích theo locale và quy tắc kiểm tra dữ liệu phù hợp. Khi dùng những API phân tích có thể chấp nhận một phần chuỗi, phải xác minh toàn bộ đầu vào đã được tiêu thụ, không chỉ một tiền tố hợp lệ.

`Double.parseDouble` và constructor BigDecimal nhận chuỗi không phải các bộ phân tích tùy ý theo locale người dùng. Chuỗi trong mã:

```java
new BigDecimal("1234567.89")
```

dùng cú pháp số của API đó; nó không đổi dấu chấm sang dấu phẩy vì locale hiển thị.

Với dữ liệu gửi máy, tuân thủ giao thức:

- Dữ liệu JSON nên dùng bộ tuần tự hóa JSON đúng kiểu số.
- Tham số số trong cơ sở dữ liệu nên truyền dưới dạng kiểu số, không chèn chuỗi đã nhóm.
- CSV có quy tắc phân tách cột và bao chuỗi riêng; dấu phẩy trong một số hiển thị có thể xung đột với dấu phân tách cột.
- Một giao thức kỹ thuật yêu cầu dấu chấm không nên phụ thuộc locale mặc định của hệ thống.

ROOT chỉ là một phần của quyết định định dạng. Nó không tự xử lý thoát chuỗi, cấu trúc bản tin, miền giá trị hoặc quy tắc làm tròn.

## 10. Locale không thay thế mã hóa và quy tắc nghiệp vụ

Locale quyết định cách hiển thị theo vùng; charset quyết định cách ký tự được mã hóa thành byte. Chọn UTF-8 không làm `1,234.50` thành `1.234,50`, và chọn vi-VN không tự sửa một luồng xuất đang dùng sai mã hóa.

Tương tự, chọn locale không:

- Quyết định số tiền thuộc loại tiền nào.
- Tự tính tỷ giá.
- Thực hiện quy tắc thuế.
- Xác định cách làm tròn nghiệp vụ.
- Đổi giá trị BigDecimal đã có.

Hãy xử lý giá trị và quy tắc nghiệp vụ trước, rồi tạo cách hiển thị phù hợp. Định dạng thành hai chữ số không tự chứng minh dữ liệu tiền tệ đã được tính đúng.

## 11. Kiểm thử để lỗi locale không phụ thuộc máy

Một nhóm kiểm thử hữu ích nên có:

1. Cùng giá trị với ít nhất hai locale có dấu khác nhau, chẳng hạn US và Germany.
2. Có và không có cờ phân nhóm.
3. Giá trị âm, bằng không, có phần lẻ và nhiều chữ số.
4. Ký hiệu Unicode của các locale sản phẩm hỗ trợ nếu có dấu cách khó phân biệt.
5. Đường tạo dữ liệu kỹ thuật không phụ thuộc locale mặc định.
6. Quy tắc xử lý dữ liệu đầu vào bản địa hóa, nếu ứng dụng có nhận nó.

Chỉ định locale trong test thay vì hy vọng máy chạy có đúng mặc định. Nếu kiểm thử kết quả hiển thị chính xác từng ký tự, ghi nhận phiên bản runtime và dữ liệu locale liên quan khi nâng JDK.

Đừng thay mọi dấu chấm/phẩy trong expected để test đi qua; trước tiên xác định test đang kiểm tra giao diện cho người dùng hay giao thức cho máy. Hai mục tiêu có thể yêu cầu hai biểu diễn khác nhau.

## 12. Tự kiểm tra

1. Dấu phẩy trong `%,.2f` có bắt buộc đầu ra chứa dấu phẩy phân nhóm không?
2. Vì sao `%.2f` với Germany vẫn có dấu phẩy dù mẫu chứa dấu chấm?
3. Nếu muốn phục vụ người dùng Việt Nam, locale của máy chủ có phải nguồn quyết định duy nhất không?
4. Có thể thay toàn bộ dấu phẩy thành dấu chấm để phân tích mọi số không?
5. Hai dấu cách nhìn giống nhau có nhất thiết bằng nhau trong String không?
6. Locale.ROOT có tự làm chuỗi thành JSON hợp lệ không?

Đáp án:

1. Không; đó là yêu cầu phân nhóm, ký hiệu thực tế do locale quyết định.
2. Dấu chấm trong mẫu mở phần độ chính xác; nó không phải ký hiệu đầu ra cố định.
3. Không; cần quy tắc chọn locale theo người dùng hoặc yêu cầu.
4. Không; sẽ lẫn dấu nhóm và dấu thập phân.
5. Không; cần xem mã Unicode.
6. Không; JSON có quy tắc riêng.

Luôn tách giá trị, quy tắc hiển thị và hợp đồng trao đổi dữ liệu. Khi ba phần này rõ ràng, dấu phân cách khác nhau trở thành hành vi có chủ ý thay vì lỗi chỉ xuất hiện trên một số máy.

## Tài liệu đối chiếu

- [Locale — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Locale.html): ngữ cảnh vùng và dữ liệu locale.
- [Formatter — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Formatter.html): các quy tắc bản địa hóa trong định dạng số.
- [DecimalFormatSymbols — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/DecimalFormatSymbols.html): ký hiệu thập phân và phân nhóm.
