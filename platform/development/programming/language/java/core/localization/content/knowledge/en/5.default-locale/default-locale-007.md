# Rủi ro khác kết quả giữa máy phát triển, kiểm thử và máy chủ khi dùng Locale mặc định

Một chương trình Java có thể chạy đúng trên laptop lập trình viên nhưng cho kết quả khác trong CI hoặc máy chủ **dù mã nguồn và dữ liệu đầu vào giống nhau**. Một nguyên nhân phổ biến là chương trình vô tình phụ thuộc **Locale mặc định** của JVM. Khi locale khác, việc định dạng số, phân tích dữ liệu người dùng, chuyển hoa/thường, lấy tên ngày tháng, sắp xếp chuỗi và tìm bản dịch có thể thay đổi. Tác động có thể chỉ là giao diện hiển thị khác, nhưng cũng có thể làm bài kiểm thử thất bại, đọc sai dữ liệu hoặc tạo ra lỗi nghiệp vụ.

Bài này tập trung vào **rủi ro khác kết quả do Locale mặc định giữa môi trường phát triển (dev), kiểm thử (test/CI) và máy chủ (production)**: nguyên nhân, ví dụ có thể tái hiện, cách chẩn đoán, lựa chọn thiết kế và kiểm thử để tránh phụ thuộc môi trường không chủ đích.

## 1. Locale mặc định là gì và vì sao mỗi môi trường có thể khác nhau?

**java.util.Locale** biểu diễn ngôn ngữ và quy ước địa phương, có thể gồm mã ngôn ngữ, vùng, chữ viết và các phần mở rộng. Ví dụ **vi-VN**, **en-US**, **de-DE** hoặc **tr-TR**.

Java cung cấp một **Locale mặc định toàn JVM**, đọc qua **Locale.getDefault()**. JVM cũng có hai mặc định theo loại mục đích:

- **Locale.Category.FORMAT**: dùng cho các thao tác định dạng/phân tích theo ngữ cảnh địa phương, chẳng hạn số, ngày giờ.
- **Locale.Category.DISPLAY**: dùng cho tên ngôn ngữ, tên quốc gia/vùng hiển thị cho người dùng.
- **Locale.getDefault()** không truyền category: lấy locale mặc định chung, là nguồn được nhiều API sử dụng.

Vào lúc khởi tạo, giá trị mặc định chịu ảnh hưởng từ hệ điều hành, thiết lập môi trường chạy và cấu hình JVM. Cùng một ứng dụng có thể chạy trên máy dev được cấu hình tiếng Việt, runner CI tiếng Anh và container máy chủ dùng một locale khác. Ngoài ra, mã Java có thể gọi **Locale.setDefault(...)** trong lúc tiến trình đang chạy và thay đổi mặc định được các phần khác nhìn thấy.

Ví dụ kiểm tra trạng thái thực tế:

~~~java
import java.util.Locale;

public class InspectDefaultLocale {
    public static void main(String[] args) {
        System.out.println("Global : " +
                Locale.getDefault().toLanguageTag());
        System.out.println("FORMAT : " +
                Locale.getDefault(Locale.Category.FORMAT)
                      .toLanguageTag());
        System.out.println("DISPLAY: " +
                Locale.getDefault(Locale.Category.DISPLAY)
                      .toLanguageTag());
    }
}
~~~

Lưu thành **InspectDefaultLocale.java**, chạy:

~~~bash
javac InspectDefaultLocale.java
java InspectDefaultLocale
~~~

Chương trình in ra **ba language tag của chính môi trường đang chạy**. Không thể đưa một stdout cố định mà đúng trên mọi máy: khác biệt đó chính là điều cần kiểm tra. Khi đối chiếu dev, CI và production, hãy thu thập kết quả của cùng chương trình cùng thời điểm khởi động.

**Phân biệt rõ:** locale mặc định **không phải** múi giờ, charset hay ngôn ngữ giao diện mà người dùng đã chủ động chọn. Chúng là các quyết định có liên quan nhưng độc lập. **ZoneId.systemDefault()**, **Charset.defaultCharset()** và **Locale.getDefault()** phải được kiểm tra riêng khi một kết quả có thể chịu ảnh hưởng của nhiều yếu tố.

## 2. Điều kiện gây khác kết quả: API ngầm đọc mặc định

Nhiều API Java có overload **không nhận Locale**. Overload đó thường dùng một mặc định theo hợp đồng của API, do đó cùng một lệnh có thể cho kết quả khác nhau khi chạy tại môi trường khác. Những ví dụ quan trọng:

| Nhóm chức năng | Cách phụ thuộc ngầm | Cách kiểm soát tường minh |
| --- | --- | --- |
| Định dạng văn bản chứa số | **String.format("%.2f", value)** dùng locale mặc định dành cho định dạng | **String.format(Locale.US, "%.2f", value)** hoặc locale đã chọn |
| Định dạng số/tiền/phần trăm | **NumberFormat.getNumberInstance()**, **getCurrencyInstance()** | Factory nhận **Locale** |
| Phân tích số nhập | **NumberFormat.getInstance().parse(text)** | Tạo formatter với locale của chính dữ liệu đầu vào |
| Định dạng ngày giờ | **DateTimeFormatter.ofLocalizedDate(style)** và các factory tương tự | Sử dụng **withLocale(locale)**; timezone xử lý riêng |
| Chuyển hoa/thường | **String.toLowerCase()**, **toUpperCase()** | Overload nhận **Locale**; dùng **Locale.ROOT** cho quy tắc ngôn ngữ trung lập khi thích hợp |
| Sắp xếp văn bản | **Collator.getInstance()** | **Collator.getInstance(locale)** |
| Phân tách văn bản | **BreakIterator.getWordInstance()** và factory tương tự | Truyền locale theo nội dung văn bản |
| Tra cứu chuỗi đa ngôn ngữ | **ResourceBundle.getBundle("messages")** | Truyền locale được chọn và xác định chính sách fallback |

Không phải mọi API Java phụ thuộc locale. **Integer.parseInt("123")** dùng cú pháp số xác định của Java; **LocalDate.parse("2026-10-28")** dùng định dạng ISO theo mặc định; **String.compareTo** so sánh đơn vị UTF-16 mà không áp dụng ngôn ngữ địa phương. Cần biết API nào biến đổi theo locale để không truy tìm sai nguyên nhân.

## 3. Thí nghiệm có stdout chính xác: cùng mã, khác FORMAT locale

Ví dụ đầy đủ sau giả lập hai môi trường trong một lần chạy. Nó đặt mặc định **FORMAT** lần lượt là Hoa Kỳ và Đức để cho thấy kết quả của overload ngầm định. Đồng thời, chương trình luôn định dạng tường minh bằng **Locale.US** để so sánh.

**File DefaultLocaleRiskDemo.java**

~~~java
import java.util.Locale;

public class DefaultLocaleRiskDemo {
    public static void main(String[] args) {
        Locale originalGlobal = Locale.getDefault();
        Locale originalFormat =
                Locale.getDefault(Locale.Category.FORMAT);
        Locale originalDisplay =
                Locale.getDefault(Locale.Category.DISPLAY);

        try {
            compare(Locale.US);
            compare(Locale.GERMANY);
        } finally {
            Locale.setDefault(originalGlobal);
            Locale.setDefault(
                    Locale.Category.FORMAT, originalFormat);
            Locale.setDefault(
                    Locale.Category.DISPLAY, originalDisplay);
        }
    }

    private static void compare(Locale environmentLocale) {
        Locale.setDefault(
                Locale.Category.FORMAT, environmentLocale);

        String implicit = String.format("%.2f", 1.5);
        String explicit =
                String.format(Locale.US, "%.2f", 1.5);

        System.out.println(
                environmentLocale.toLanguageTag()
                + " | implicit=" + implicit
                + " | explicit=" + explicit);
    }
}
~~~

Lưu đúng tên **DefaultLocaleRiskDemo.java** và chạy trên Java 17+:

~~~bash
javac -encoding UTF-8 DefaultLocaleRiskDemo.java
java DefaultLocaleRiskDemo
~~~

Stdout chính xác:

~~~text
en-US | implicit=1.50 | explicit=1.50
de-DE | implicit=1,50 | explicit=1.50
~~~

**Giải thích:** Khi locale mặc định cho **FORMAT** là **en-US**, dấu thập phân là dấu chấm. Khi chuyển sang **de-DE**, overload **String.format("%.2f", ...)** dùng dấu phẩy. Còn overload **String.format(Locale.US, ...)** giữ nguyên cách biểu diễn trong cả hai trường hợp. Đây là ví dụ thay đổi **kết quả hiển thị**, giá trị số **double 1.5** trong bộ nhớ không thay đổi.

**Giới hạn quan trọng:** Ví dụ cố ý gọi **Locale.setDefault** để minh họa lỗi, với giả định một chương trình console chạy độc lập. Việc khôi phục trong **finally** giảm ảnh hưởng sau thí nghiệm nhưng **không bảo đảm an toàn nếu nhiều luồng đang chạy song song**. Không sử dụng thủ thuật đổi default theo từng request trong server.

## 4. Rủi ro 1: số và tiền tệ hiển thị hoặc được phân tích sai

### 4.1. Kết quả hiển thị khác nhau

Giả sử mã nguồn dùng:

~~~java
String displayed = String.format("%.2f", 1234.5);
~~~

Đây là đoạn minh họa đặt trong một phương thức. Với mặc định FORMAT **en-US**, kết quả là **1234.50**; với **de-DE**, kết quả là **1234,50**. Nếu chương trình tạo bản báo cáo, nội dung email, file dữ liệu hoặc snapshot kiểm thử từ **displayed**, chỉ thay môi trường có thể làm kết quả khác.

Với các formatter có phân nhóm chữ số và định dạng tiền tệ, cách hiển thị còn chịu dữ liệu bản địa hóa theo JDK: vị trí ký hiệu, dấu cách đặc biệt, dấu phân cách và chữ số. Đừng giả định hai phiên bản JDK đều trả một chuỗi byte-for-byte giống nhau chỉ vì cùng language tag.

### 4.2. Phân tích số có thể làm thay đổi giá trị

Sự khác biệt không dừng ở vẻ ngoài. Chuỗi **"1,234"** có thể mang nghĩa **một nghìn hai trăm ba mươi tư** khi dùng quy ước Hoa Kỳ, nhưng mang nghĩa **một phẩy hai ba bốn** trong ngữ cảnh Đức. Nếu một dịch vụ nhận input theo quy ước cụ thể mà lại dùng **NumberFormat.getInstance()** không truyền locale, kết quả phân tích có thể khác giữa dev và production.

Khi đọc số từ người dùng, phải biết **locale của dữ liệu nhập**:

~~~java
import java.text.NumberFormat;
import java.text.ParseException;
import java.util.Locale;

public class ParsingLocaleDemo {
    public static void main(String[] args) throws ParseException {
        String text = "1,234";
        Number us = NumberFormat
                .getNumberInstance(Locale.US).parse(text);
        Number germany = NumberFormat
                .getNumberInstance(Locale.GERMANY).parse(text);

        System.out.println("US: " + us);
        System.out.println("Germany: " + germany);
    }
}
~~~

Lưu **ParsingLocaleDemo.java**, chạy:

~~~bash
javac ParsingLocaleDemo.java
java ParsingLocaleDemo
~~~

Kết quả theo quy tắc số của hai locale:

~~~text
US: 1234
Germany: 1.234
~~~

Kết quả thể hiện hai **giá trị số khác nhau**. Đừng lưu chuỗi số đã bản địa hóa rồi đọc ngược bằng mặc định hệ thống. Với API, cơ sở dữ liệu, file trao đổi giữa máy, hãy dùng hợp đồng biểu diễn ổn định (ví dụ số JSON hoặc định dạng số đã quy định) và chỉ dùng locale khi hiển thị hoặc phân tích dữ liệu thật sự do con người nhập.

**Lưu ý phân tích dữ liệu:** **NumberFormat.parse(String)** có thể chấp nhận một phần chuỗi và trả về kết quả cho tiền tố hợp lệ. Với input cần được kiểm tra đầy đủ, dùng **ParsePosition** để xác nhận đã tiêu thụ hết chuỗi, kèm validation về khoảng giá trị và kiểu dữ liệu. Với tiền tệ có yêu cầu chính xác, cân nhắc **BigDecimal** thay vì **double**.

## 5. Rủi ro 2: lỗi chữ hoa/thường do ngôn ngữ mặc định

Những lệnh tưởng đơn giản như **String.toLowerCase()** có thể phụ thuộc ngôn ngữ. Tiếng Thổ Nhĩ Kỳ có quy tắc chữ **I/i** khác tiếng Anh. Nếu dùng cách chuyển chữ mặc định để chuẩn hóa khóa máy, tên quyền hoặc mã lệnh, cùng một chuỗi có thể biến đổi khác nhau giữa môi trường.

Ví dụ tự chứa, tránh phụ thuộc môi trường:

**File CaseMappingDemo.java**

~~~java
import java.util.Locale;

public class CaseMappingDemo {
    public static void main(String[] args) {
        String command = "TITLE";

        System.out.println(
                command.toLowerCase(Locale.ROOT));
        System.out.println(
                command.toLowerCase(Locale.forLanguageTag("tr-TR")));
    }
}
~~~

Lưu **CaseMappingDemo.java**, chạy:

~~~bash
javac CaseMappingDemo.java
java CaseMappingDemo
~~~

Stdout:

~~~text
title
tıtle
~~~

Dòng thứ hai chứa chữ **ı** không dấu chấm (U+0131), khác chữ **i** thường (U+0069). Nếu gọi **command.toLowerCase()** không tham số, kết quả có thể phản ánh locale mặc định chung. Với **mã định danh kỹ thuật** mà hợp đồng yêu cầu quy tắc độc lập ngôn ngữ, dùng **Locale.ROOT** khi chuyển chữ, đồng thời quy định bảng ký tự hợp lệ và chuẩn hóa dữ liệu. Với **văn bản tự nhiên** của người dùng, dùng locale đúng của ngôn ngữ đó; không mặc định rằng Locale.ROOT phù hợp mọi trường hợp.

Cảnh báo: chuyển hoa/thường không phải phương pháp đầy đủ để chuẩn hóa Unicode hay kiểm tra tính tương đương của mọi ngôn ngữ. Nếu cần so khớp văn bản theo ngôn ngữ, cân nhắc **Collator**; nếu cần chuẩn hóa dạng Unicode, xem **Normalizer** và thiết kế quy tắc tách biệt với quyền/định danh.

## 6. Rủi ro 3: ngày giờ và snapshot kiểm thử

Trong Java hiện đại, **java.time** nên được dùng cho ngày giờ. Tuy vậy, **DateTimeFormatter.ofLocalizedDate(...)** tạo formatter dùng quy ước địa phương; khi không chỉ định locale, kết quả có thể chịu ảnh hưởng mặc định **FORMAT**. Tên tháng, trật tự thành phần ngày và dấu phân cách có thể khác nhau.

Ví dụ minh họa:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class DateFormattingDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 28);

        DateTimeFormatter us = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.LONG)
                .withLocale(Locale.US);
        DateTimeFormatter vietnamese = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.LONG)
                .withLocale(Locale.forLanguageTag("vi-VN"));

        System.out.println(us.format(date));
        System.out.println(vietnamese.format(date));
    }
}
~~~

Lưu **DateFormattingDemo.java** và chạy **javac DateFormattingDemo.java**, **java DateFormattingDemo**. Hai dòng trình bày cùng **ngày 28/10/2026** bằng quy ước của từng locale. Cách viết tháng/chèn khoảng trắng có thể thay đổi theo dữ liệu CLDR của JDK, vì vậy ví dụ không gán một stdout cố định cho các môi trường không chốt phiên bản runtime.

Nếu một snapshot test yêu cầu nguyên văn chuỗi ngày tiếng Việt theo CLDR, việc nâng cấp Java/JDK có thể làm test đổi kết quả ngay cả khi application code không đổi. Muốn kiểm tra **ý nghĩa của ngày** nên assert đối tượng **LocalDate**, còn muốn kiểm tra format cụ thể thì chỉ định locale, lựa chọn style/pattern và kiểm soát phiên bản môi trường.

**Locale khác TimeZone:** cùng một **Instant** khi hiển thị ở **Asia/Ho_Chi_Minh** và **America/New_York** cho giờ địa phương khác nhau dù locale giữ nguyên. Một test chạy đúng ở dev nhưng sai production có thể bị ảnh hưởng **cả locale và múi giờ**. Không dùng **ZoneId.systemDefault()** nếu hợp đồng xử lý thời gian phải thống nhất; truyền **ZoneId** rõ ràng hoặc dùng **UTC** cho dữ liệu thời điểm trao đổi qua API.

## 7. Rủi ro 4: bản dịch và ResourceBundle thay đổi

Giả sử classpath có các file:

~~~text
messages.properties
messages_vi.properties
messages_en.properties
~~~

Nếu mã gọi:

~~~java
ResourceBundle bundle = ResourceBundle.getBundle("messages");
String title = bundle.getString("title");
~~~

Đoạn minh họa cần import **java.util.ResourceBundle**, tệp resource thực tế và một khóa **title**. Overload không truyền locale sử dụng mặc định JVM để lựa chọn resource. Khi dev chạy trong môi trường tiếng Việt còn máy chủ mặc định tiếng Anh, cùng một khóa có thể trả bản dịch khác nhau.

Cách kiểm soát:

~~~java
Locale chosen = Locale.forLanguageTag("vi-VN");
ResourceBundle bundle =
        ResourceBundle.getBundle("messages", chosen);
String title = bundle.getString("title");
~~~

Đoạn minh họa cần import **java.util.Locale** và **java.util.ResourceBundle**. **chosen** nên đến từ cơ chế chọn locale của người dùng hoặc chính sách ứng dụng; chỉ định locale giúp tránh phụ thuộc mặc định ở bước chọn bundle. Tuy nhiên, **ResourceBundle** có cơ chế tìm bản dịch và fallback riêng, trong một số trường hợp có thể xét locale mặc định của JVM nếu không có candidate phù hợp. Vì vậy, một hệ thống cần fallback tuyệt đối xác định còn phải **thiết kế chính sách bundle** và kiểm thử trường hợp thiếu resource.

Với resource bundle dạng properties trên classpath có hỗ trợ **ResourceBundle.Control**, có thể dùng **getNoFallbackControl(...)** để loại bỏ bước fallback theo locale JVM mà vẫn giữ chuỗi candidate và resource gốc. Đối với named modules, API nhận **Control** có những hạn chế; cần áp dụng cơ chế tài nguyên/provider tương ứng.

**Điều cần kiểm tra:** kiểm thử bản dịch thiếu khóa, locale không được hỗ trợ, cache bundle và default locale của JVM. Khi nhiều request dùng cùng server, không gọi **Locale.setDefault** để đổi giao diện theo từng người dùng.

## 8. Rủi ro 5: thứ tự sắp xếp và xử lý văn bản khác nhau

**Collator.getInstance()** không nhận locale có thể tạo bộ so sánh theo ngữ cảnh mặc định. Các chữ cái có dấu, chữ ghép và thứ tự chữ cái thay đổi giữa quy tắc ngôn ngữ; danh sách tên hiển thị có thể được sắp theo cách khác trên hai máy.

~~~java
import java.text.Collator;
import java.util.Arrays;
import java.util.Locale;

public class ExplicitCollationDemo {
    public static void main(String[] args) {
        String[] names = {"Anh", "Ánh", "Bình", "Ân"};
        Collator collator = Collator.getInstance(
                Locale.forLanguageTag("vi-VN"));
        Arrays.sort(names, collator);
        System.out.println(Arrays.toString(names));
    }
}
~~~

Lưu **ExplicitCollationDemo.java**, chạy bằng **javac** và **java**. Các tên được sắp theo Collator của locale đã chỉ định thay vì locale mặc định. Kết quả cụ thể còn có thể phụ thuộc dữ liệu và nhà cung cấp locale của JDK, nên nếu thứ tự được xem là hợp đồng dữ liệu phải kiểm thử trong runtime triển khai thực tế.

Không dùng kết quả của **Collator** để xác định quyền truy cập hay tính duy nhất của mã định danh bảo mật. So sánh ngôn ngữ phục vụ hiển thị/tìm kiếm và so sánh định danh kỹ thuật giải quyết hai bài toán khác nhau.

Tương tự, **BreakIterator** không nhận locale có thể chọn quy tắc phân tách văn bản theo mặc định. Nếu ứng dụng xử lý tiếng Thái, tiếng Việt hoặc emoji/cụm ký tự Unicode, thay đổi JDK/dữ liệu Unicode còn có thể tác động tới ranh giới ký tự. Việc truyền đúng locale giúp xác định ngữ cảnh mong muốn nhưng **không bảo đảm không có thay đổi giữa mọi phiên bản JDK**.

## 9. Hai lớp khác biệt: cấu hình runtime và dữ liệu bản địa hóa của JDK

Cần phân biệt hai nguyên nhân có dấu hiệu giống nhau.

### 9.1. Mặc định khác nhau do môi trường

Các máy có thể cho **Locale.getDefault()** khác nhau vì:
- Người dùng hệ điều hành và cài đặt vùng khác nhau.
- Cách chạy trong IDE, terminal, CI, container hay service manager khác nhau.
- Thuộc tính JVM như **user.language** và **user.country** được đặt khi khởi động.
- Mã ứng dụng hoặc thư viện gọi **Locale.setDefault**.
- Mặc định theo category **FORMAT**/**DISPLAY** được tùy chỉnh riêng.

Nếu app sử dụng overload ngầm, thay đổi những yếu tố trên có thể làm kết quả khác mà không cần sửa một dòng Java nào.

### 9.2. Cùng locale nhưng dữ liệu JDK khác nhau

Giả sử cả hai môi trường đều có mặc định **vi-VN**. Output vẫn có khả năng khác do:
- Phiên bản JDK hoặc bản cập nhật JDK khác.
- Dữ liệu **CLDR** (Unicode Common Locale Data Repository) được JDK tích hợp thay đổi.
- Cấu hình locale providers trong runtime khác nhau.
- Các API ngày giờ phụ thuộc dữ liệu múi giờ (**tzdb**) khác nhau, vốn là vấn đề độc lập với locale.

Điều này thường xảy ra ở **dấu cách phân nhóm số, ký hiệu tiền tệ, định dạng ngày tháng, tên địa danh, cách viết chữ và collation**. Java 17+ dùng dữ liệu locale từ runtime và có thể cập nhật dữ liệu theo các bản phát hành. **Truyền locale tường minh giải quyết sự phụ thuộc vào default, nhưng không khóa phiên bản dữ liệu CLDR.**

Vì thế để kết quả hiển thị ổn định tuyệt đối, cần xác định cả **locale** lẫn **JDK/runtime**, và trong một số hợp đồng phải dùng định dạng kỹ thuật bất biến được chỉ định rõ thay vì định dạng bản địa hóa.

## 10. Cách tái hiện và chẩn đoán trong dev, CI và production

### 10.1. Ghi lại thông tin có ích

Khi gặp lỗi “chỉ xảy ra trên máy chủ”, bắt đầu từ những thông tin liên quan đến sự khác biệt thay vì phỏng đoán:

~~~java
import java.nio.charset.Charset;
import java.time.ZoneId;
import java.util.Locale;

public class RuntimeLocaleDiagnostic {
    public static void main(String[] args) {
        System.out.println("Java: " +
                Runtime.version());
        System.out.println("Global locale: " +
                Locale.getDefault().toLanguageTag());
        System.out.println("Format locale: " +
                Locale.getDefault(Locale.Category.FORMAT)
                      .toLanguageTag());
        System.out.println("Display locale: " +
                Locale.getDefault(Locale.Category.DISPLAY)
                      .toLanguageTag());
        System.out.println("Zone: " +
                ZoneId.systemDefault().getId());
        System.out.println("Charset: " +
                Charset.defaultCharset().name());
    }
}
~~~

Lưu **RuntimeLocaleDiagnostic.java** rồi chạy:

~~~bash
javac RuntimeLocaleDiagnostic.java
java RuntimeLocaleDiagnostic
~~~

**Không có stdout cố định** vì chương trình cố tình đọc môi trường thật. Chạy nó hoặc tích hợp phần đo tương đương trong môi trường dev, test và server. Ghi nhận thêm tên JDK vendor/build, image/container version, cấu hình locale của JVM, cấu hình startup và phiên bản gói triển khai nếu cần tái hiện.

Với ứng dụng có nhiều người dùng, chỉ log thông tin môi trường ở mức phù hợp để chẩn đoán; không ghi token, cookie hoặc dữ liệu cá nhân nhạy cảm. Khi kết quả sai chỉ xuất hiện trong một request, log **resolved locale** của request và nguồn lựa chọn locale ở mức an toàn, tránh quy mọi lỗi cho JVM default.

### 10.2. Chạy thử với default khác nhau

Nếu chạy Java 17+ bằng command line, có thể thử tạo hai tiến trình riêng với các thuộc tính JVM:

~~~bash
java -Duser.language=en -Duser.country=US RuntimeLocaleDiagnostic
java -Duser.language=de -Duser.country=DE RuntimeLocaleDiagnostic
~~~

Các thuộc tính **-D...** đặt trước tên main class. Sau khi chạy, kiểm tra **Locale.getDefault(...)** in ra thực tế vì cấu hình theo category và các điều kiện runtime khác có thể tác động. Đây là cách kiểm tra hành vi phụ thuộc môi trường theo **từng process**, phù hợp hơn với việc đổi default ngay trong những bài kiểm thử chạy song song.

Để quan sát chênh lệch cụ thể trong NumberFormat, định dạng ngày hoặc ResourceBundle, chạy chính chức năng nghi ngờ trong hai tiến trình. Đừng kết luận chỉ dựa vào việc hai máy có **LANG** khác nhau: JVM có thể xử lý locale khác các chương trình shell, và giá trị thực tế cần được lấy từ API Java.

### 10.3. Quy trình khoanh vùng

1. **So sánh đầu vào gốc**: dữ liệu nghiệp vụ, phiên bản cấu hình, ngôn ngữ do request hoặc người dùng chọn.
2. **Ghi nhận default thực tế**: global, FORMAT, DISPLAY; đồng thời kiểm tra zone/charset nếu đầu ra có liên quan.
3. **Tìm các overload không truyền locale** và nơi gọi **Locale.setDefault** trong ứng dụng hoặc thư viện.
4. **Gọi lại với locale tường minh** trên cùng dữ liệu để xem khác biệt có biến mất không.
5. **Đối chiếu JDK và dữ liệu locale** khi cả hai nơi đã dùng cùng một locale nhưng kết quả chuỗi vẫn khác.
6. **Xác định hợp đồng output**: hiển thị theo người dùng hay dữ liệu trao đổi cần bất biến. Sau đó sửa tại ranh giới phù hợp, viết kiểm thử bảo vệ hành vi.

Nếu xử lý bản dịch thiếu khóa, kiểm tra thứ tự fallback ResourceBundle trước khi đổ lỗi cho default. Nếu giờ bị lệch nhưng ngôn ngữ/format tương đồng, điều tra ZoneId và dữ liệu tzdb riêng.

## 11. Cách thiết kế để kết quả ổn định

### 11.1. Truyền locale tường minh

Các phương thức xử lý theo ngôn ngữ nên nhận locale như một tham số hoặc nhận một đối tượng ngữ cảnh chứa locale đã resolve:

~~~java
import java.text.NumberFormat;
import java.util.Locale;

public class LocaleAwarePrice {
    public static String showAmount(
            Number amount, Locale displayLocale) {
        NumberFormat formatter =
                NumberFormat.getNumberInstance(displayLocale);
        formatter.setMinimumFractionDigits(2);
        formatter.setMaximumFractionDigits(2);
        return formatter.format(amount);
    }
}
~~~

Lưu **LocaleAwarePrice.java**; class biên dịch với Java 17+. Đây là phương thức tiện ích không có **main**, dùng từ một caller khi đã xác định **displayLocale**. Tách việc **chọn locale** khỏi việc **định dạng** giúp cùng một dữ liệu cho kết quả thống nhất khi được truyền cùng ngữ cảnh.

Lưu ý **NumberFormat** mutable, không nên dùng chung một instance rồi đổi locale/định dạng giữa các thread. Đối với ngày giờ, **DateTimeFormatter** immutable và thích hợp chia sẻ nếu đã cấu hình đúng.

### 11.2. Có mặc định riêng của ứng dụng

Nếu người dùng không chọn locale, dùng một **application default** rõ ràng, nằm trong danh sách locale mà ứng dụng hỗ trợ, ví dụ **vi-VN**. Giá trị có thể đến từ cấu hình triển khai hoặc cấu hình sản phẩm, nhưng phải được xác minh khi khởi động. Đừng mặc định rằng default của JVM là ngôn ngữ mà hệ thống đã chuẩn bị bản dịch.

Với ứng dụng đa người dùng, chính sách thực tế có thể là:

~~~text
Lựa chọn hiện tại của người dùng
    -> Cấu hình đã lưu của người dùng
    -> Ngôn ngữ client được hỗ trợ
    -> Mặc định tenant/tổ chức (nếu có)
    -> Mặc định ứng dụng
~~~

Đây là **ví dụ chính sách**, không phải thứ tự Java Core tự áp đặt. Một resolver chịu trách nhiệm trả về **Locale** được hỗ trợ trước khi phần hiển thị xử lý dữ liệu. Không dùng **Locale.setDefault** để chuyển ngôn ngữ theo request.

### 11.3. Dữ liệu máy cần hợp đồng độc lập ngôn ngữ

Không xuất số, ngày hoặc mã định danh bằng cách gọi formatter phụ thuộc locale ngầm rồi kỳ vọng hệ thống khác tự đọc giống như máy nguồn:

- Với ngày/giờ trao đổi máy, dùng kiểu dữ liệu chính xác và một biểu diễn được quy định, ví dụ **ISO-8601**, kèm offset/zone khi cần.
- Với số của JSON/API, dùng cú pháp số theo hợp đồng dữ liệu; không nhúng số bản địa hóa vào trường string trừ khi hợp đồng yêu cầu.
- Với mã định danh kỹ thuật, quy định rõ so sánh case-sensitive hay canonicalization; không phụ thuộc chữ hoa/thường trong ngôn ngữ của máy chủ.
- Với văn bản dành cho người đọc, định dạng theo locale của người đọc và kiểm tra dữ liệu bản địa hóa trong runtime được hỗ trợ.

Cùng một trường dữ liệu thường có **giá trị chuẩn** và **chuỗi hiển thị** khác nhau. Hãy lưu giá trị chuẩn và chỉ sinh chuỗi hiển thị ở biên phù hợp.

### 11.4. Không sử dụng Locale.setDefault theo request

**Locale.setDefault(...)** sửa trạng thái ở mức JVM. Nếu request A đặt **vi-VN** và request B đặt **de-DE**, request A có thể vô tình định dạng theo locale của B do hai request chạy xen kẽ. Việc dùng **try/finally** để trả lại default cũng không loại bỏ race trong quá trình chạy.

Thay vì thay toàn bộ tiến trình, giữ locale trong biến/ngữ cảnh request và truyền cho formatter, bundle, collator. Với xử lý bất đồng bộ, chuyển ngữ cảnh tường minh theo nhiệm vụ; một **ThreadLocal** không được tự động mang sang mọi executor và phải dọn sạch khi dùng thread pool.

## 12. Kiểm thử: tránh kết quả phụ thuộc môi trường

### 12.1. Kiểm thử hành vi tường minh, không dựa vào máy CI

Ví dụ kiểm tra số theo hai locale bằng một chương trình độc lập:

**File StableFormattingCheck.java**

~~~java
import java.util.Locale;

public class StableFormattingCheck {
    public static void main(String[] args) {
        String us = String.format(
                Locale.US, "%.2f", 1.5);
        String german = String.format(
                Locale.GERMANY, "%.2f", 1.5);

        if (!"1.50".equals(us)) {
            throw new AssertionError("Unexpected US format: " + us);
        }
        if (!"1,50".equals(german)) {
            throw new AssertionError(
                    "Unexpected German format: " + german);
        }

        System.out.println("PASS");
    }
}
~~~

Lưu **StableFormattingCheck.java**, chạy:

~~~bash
javac StableFormattingCheck.java
java StableFormattingCheck
~~~

Kết quả chính xác:

~~~text
PASS
~~~

Bài kiểm tra này xác minh quy tắc dấu thập phân đơn giản với tham số locale tường minh. Nếu muốn kiểm tra một chuỗi ngày dài hoặc tiền tệ phụ thuộc dữ liệu CLDR, cần kiểm soát JDK/provider hoặc thiết kế assertion kiểm tra hành vi thay vì buộc một văn bản bản địa hóa cụ thể trên mọi phiên bản runtime.

### 12.2. Ma trận kiểm thử thiết yếu

| Kiểm thử | Mục đích | Điều cần xác minh |
| --- | --- | --- |
| Chạy cùng bài test ở **en-US** và **de-DE** default | Phát hiện overload phụ thuộc default | Logic nghiệp vụ không đổi; chỉ output được chủ đích địa phương hóa mới khác |
| Dùng **tr-TR** khi xử lý chữ **I/i** | Phát hiện case mapping ngầm | Mã kỹ thuật không bị biến dạng bởi locale hệ thống |
| **vi-VN** trên hai bản JDK được hỗ trợ | Phát hiện thay đổi dữ liệu locale | Chuỗi hiển thị/format thay đổi có được chấp nhận hay không |
| Tài khoản **en-US** trên server **vi-VN** | Phát hiện dùng sai nguồn locale | UI theo lựa chọn người dùng, không theo server |
| Missing locale hoặc thiếu ResourceBundle | Kiểm tra fallback | Không xuất nội dung trộn ngôn ngữ ngoài chính sách |
| Parse số từ input định dạng **de-DE** | Tránh sai giá trị | Giá trị số đúng và kiểm tra hết input |
| Date/Instant qua hai ZoneId | Tách locale khỏi timezone | Thời điểm gốc được giữ; giờ hiển thị đúng zone |
| Hai request ngôn ngữ khác nhau chạy đồng thời | Bắt race do shared default/formatter | Không lẫn bản dịch hay dấu phân cách |
| Runner CI image hoặc JDK nâng cấp | Kiểm tra tính tái lập | Chênh lệch format được dự kiến, khóa hoặc chấp nhận có kiểm soát |

Không nên để các bài test chạy song song cùng gọi **Locale.setDefault** rồi dựa vào giá trị đổi qua lại. Nếu cần test tính nhạy cảm với JVM default, chạy theo **process riêng**; hoặc bảo đảm test được cô lập hoàn toàn và khôi phục mặc định. Dù khôi phục trong finally, một test khác chạy đồng thời trong cùng JVM vẫn có thể bị ảnh hưởng.

### 12.3. Snapshot và golden file

Snapshot test so sánh nguyên văn chuỗi đầu ra thường nhạy cảm với locale. Ví dụ cùng một ngày được bản địa hóa theo cách khác hoặc có dấu cách Unicode khác khiến snapshot fail. Khi fixture là văn bản tiếng Việt, hãy **chỉ định locale** thay vì để lấy theo CI. Nếu cần so sánh byte-for-byte lâu dài, chốt hoặc xác định giới hạn phiên bản JDK và bộ dữ liệu locale.

Với logic chỉ quan tâm giá trị nghiệp vụ, tốt hơn là assert **BigDecimal**, **LocalDate**, **Instant** và các thuộc tính cấu trúc. Tránh đưa định dạng giao diện vào tầng kiểm thử phải độc lập locale.

## 13. Vận hành và triển khai: quản trị khác biệt môi trường

Để tránh tình trạng dev khác test khác production, quy trình triển khai nên:

1. **Cố định phiên bản/bản build JDK cho mỗi môi trường** trong phạm vi cần tái lập, đặc biệt khi golden file phụ thuộc dữ liệu locale.
2. **Định nghĩa application default** và supported locales bằng cấu hình rõ ràng; xác minh lúc khởi động.
3. **Kiểm tra startup options** và không để các cờ **-Duser.language**, **-Duser.country** vô tình thay đổi hành vi mà không được quan sát.
4. **Ghi nhận runtime locale FORMAT/DISPLAY** trong thông tin chẩn đoán phù hợp; xử lý locale theo request riêng.
5. **Truyền locale tường minh** tới những API phục vụ con người; sử dụng format bất biến cho hợp đồng giữa máy.
6. **Kiểm thử container/CI như thực tế** đối với những đầu ra có tính bản địa hóa; chú ý cả JDK, locale, zone và charset.
7. **Giám sát lỗi thiếu bản dịch hoặc dữ liệu parse không hợp lệ** để phát hiện fallback bất thường thay vì âm thầm làm sai dữ liệu.

Nếu hệ thống xuất bản báo cáo theo locale của tổ chức, hãy ghi rõ locale dùng lúc tạo báo cáo cùng các tham số định dạng quan trọng khi cần tái tạo kết quả về sau. Chỉ lưu locale mà không biết phiên bản runtime vẫn có thể chưa đủ để tái hiện chính xác các quy tắc dữ liệu địa phương hóa của JDK cũ.

## 14. Những hiểu lầm dễ dẫn đến lỗi

**“Java code giống nhau nên output chắc chắn giống nhau.”** Sai với những API dùng default locale, dữ liệu locale hoặc timezone. Hãy kiểm tra các tham số ngầm.

**“Locale.getDefault() là locale của người dùng đang gửi request.”** Không đúng trong server đa người dùng. Nó là mặc định của JVM, không biết user nào đang gọi.

**“Chỉ cần Locale.setDefault ở đầu request.”** Sai vì default dùng chung; request đồng thời có thể can thiệp nhau.

**“Truyền Locale.US khắp hệ thống sẽ giải quyết mọi vấn đề.”** Nó có thể làm dữ liệu trao đổi kỹ thuật ổn định ở một số tình huống, nhưng giao diện người dùng cần locale họ đã chọn. Phải tách hợp đồng máy và giao diện.

**“Cùng locale thì mọi JDK phải định dạng giống từng byte.”** Không chắc đúng: dữ liệu CLDR, provider và phiên bản runtime có thể khác.

**“Locale tự bao gồm múi giờ và tiền tệ đang giao dịch.”** Không đúng. Quản lý **ZoneId** và mã **Currency** theo nguồn yêu cầu riêng.

**“Một bài test pass với mặc định en-US chứng tỏ không có bug locale.”** Không đủ. Cần kiểm tra ít nhất một locale có quy tắc khác rõ ràng và những dữ liệu nhạy cảm với ngôn ngữ.

## 15. Tình huống tổng hợp: tìm nguyên nhân một lỗi production

Giả sử dev xuất file báo cáo giá **"1234.50"**, CI xác minh thành công, nhưng production lại xuất **"1234,50"**. Một job downstream đọc file theo cú pháp dấu chấm và báo lỗi.

Quy trình hợp lý:

1. Kiểm tra cùng input giá số là **1234.5** ở ba nơi.
2. Kiểm tra code xuất: phát hiện **String.format("%.2f", price)** không truyền locale.
3. In **Locale.getDefault(Locale.Category.FORMAT)** ở mỗi nơi; production dùng locale mà dấu thập phân là dấu phẩy.
4. Xác định hợp đồng file này là dữ liệu máy đọc và yêu cầu dấu chấm, không phải báo cáo dành cho người đọc theo locale.
5. Đổi thành **String.format(Locale.US, "%.2f", price)** cho trường đó; nếu cần độ chính xác tiền tệ, thiết kế dữ liệu và quy tắc làm tròn bằng **BigDecimal** phù hợp.
6. Kiểm thử kết quả cố định dưới ít nhất hai mặc định JVM khác nhau. Sau đó kiểm thử tại môi trường tương đương production trước triển khai.

Ngược lại, nếu cùng trường đó là số **hiển thị cho người dùng Đức**, việc cho ra **1234,50** có thể đúng. **Đúng hay sai phụ thuộc vào hợp đồng của dữ liệu**, không phụ thuộc mặc định hiện có của máy. Vì vậy sửa lỗi phải bắt đầu từ mục đích đầu ra, rồi mới quyết định format theo locale nào.

## 16. Ghi nhớ

**Rủi ro chính là phụ thuộc một tham số ngầm: Locale mặc định của JVM.** Dev, CI và production có thể dùng mặc định khác nhau; ngay cả cùng locale, các bản JDK cũng có thể khác dữ liệu bản địa hóa. Hậu quả từ chênh lệch dấu thập phân và bản dịch đến parse sai dữ liệu, snapshot thất bại hoặc lỗi xử lý mã định danh.

Giải pháp là **xác định locale của người dùng hoặc ứng dụng một cách tường minh**, truyền nó cho các API định dạng/xử lý văn bản, bảo vệ hợp đồng trao đổi dữ liệu bằng format ổn định, không thay đổi JVM default theo request và kiểm thử bằng nhiều locale, nhiều môi trường đúng phạm vi hỗ trợ. Khi kết quả vẫn khác, kiểm tra riêng phiên bản JDK/CLDR, múi giờ và charset thay vì quy mọi khác biệt về một nguyên nhân.
