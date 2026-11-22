# Vai trò chữ viết trong các locale có cùng ngôn ngữ

## 1. Vấn đề cần hiểu

Một **ngôn ngữ** có thể được viết bằng nhiều **hệ chữ viết** (*script*). Vì vậy, hai locale có cùng mã ngôn ngữ và thậm chí cùng vùng lãnh thổ vẫn có thể cần nội dung giao diện, tài nguyên dịch và cách hiển thị khác nhau.

Ví dụ:

| Locale (BCP 47) | Ngôn ngữ | Chữ viết | Vùng | Ý nghĩa |
| --- | --- | --- | --- | --- |
| `sr-Latn-RS` | Tiếng Serbia (`sr`) | Latin (`Latn`) | Serbia (`RS`) | Tiếng Serbia viết bằng chữ Latin tại Serbia |
| `sr-Cyrl-RS` | Tiếng Serbia (`sr`) | Cyrillic (`Cyrl`) | Serbia (`RS`) | Tiếng Serbia viết bằng chữ Cyrillic tại Serbia |
| `zh-Hans-CN` | Tiếng Trung (`zh`) | Chữ Hán giản thể (`Hans`) | Trung Quốc (`CN`) | Lựa chọn phổ biến cho giao diện tiếng Trung giản thể |
| `zh-Hant-TW` | Tiếng Trung (`zh`) | Chữ Hán phồn thể (`Hant`) | Đài Loan (`TW`) | Lựa chọn phổ biến cho giao diện tiếng Trung phồn thể |

Cặp `sr-Latn-RS` / `sr-Cyrl-RS` đặc biệt hữu ích để phân tích: **language và region giống nhau, chỉ script khác nhau**. Nếu hệ thống chỉ so khớp theo `sr` hoặc `sr-RS`, nó có thể chọn sai bộ tài nguyên mà người dùng mong muốn.

> **Phân biệt:** `script` là thông tin về hệ chữ viết; `language` mô tả ngôn ngữ, còn `region` mô tả quốc gia/vùng. Mã script **không** phải bảng mã ký tự, font chữ hay thao tác chuyển tự động từ chữ Latin sang chữ Cyrillic.

## 2. Script nằm ở đâu trong mô hình Locale?

Thẻ ngôn ngữ theo chuẩn **BCP 47** thường có cấu trúc:

`language-Script-REGION`

Trong đó:

- `language` thường là mã ngôn ngữ ISO 639, ví dụ `sr`, `zh`, `az`.
- `Script` là mã hệ chữ viết **ISO 15924** gồm bốn chữ cái, thường chuẩn hóa theo dạng chữ đầu viết hoa: `Latn`, `Cyrl`, `Hans`, `Hant`.
- `REGION` là mã vùng, thường gồm hai chữ cái viết hoa, ví dụ `RS`, `CN`, `TW`.
- BCP 47 còn cho phép variant, extension và private-use subtag trong các trường hợp cần thiết; ví dụ trên chỉ thể hiện ba thành phần liên quan trực tiếp đến bài này.

Không phải locale nào cũng khai báo script. `sr-RS` có ngôn ngữ và vùng nhưng **không ghi rõ hệ chữ viết**; đây không phải thẻ tương đương một cách tuyệt đối với `sr-Cyrl-RS`. Dữ liệu địa phương hóa hoặc hệ thống lựa chọn ngôn ngữ có thể suy luận chữ viết thường dùng dựa trên quy ước, nhưng giá trị script trong đối tượng `Locale` của Java vẫn để trống nếu thẻ đầu vào không chỉ rõ script.

**Vì sao script quan trọng?**

1. **Đúng bản dịch và dạng chữ:** hai bản dịch có thể dùng cùng ngôn ngữ nhưng được biên tập bằng hai hệ chữ viết khác nhau.
2. **Lựa chọn tài nguyên:** ứng dụng có thể có các tập chuỗi, hướng dẫn hoặc hình ảnh chứa chữ phù hợp từng script.
3. **Trải nghiệm người dùng:** nhãn chọn ngôn ngữ nên phân biệt được “Serbian (Latin)” và “Serbian (Cyrillic)” khi sản phẩm hỗ trợ cả hai.
4. **Tìm kiếm, sắp xếp và hiển thị:** dữ liệu, font hỗ trợ glyph, phương pháp nhập và đôi khi quy tắc đối chiếu có thể khác nhau theo chữ viết. Kết quả cụ thể còn tùy thư viện, dữ liệu locale và môi trường chạy; mã script tự nó không thực thi các xử lý này.
5. **Tính chính xác của ưu tiên người dùng:** không nên suy ra chữ viết chỉ từ quốc gia khi người dùng đã chọn script cụ thể.

## 3. Biểu diễn script bằng `java.util.Locale` trong Java 17+

Java hỗ trợ thành phần script qua `Locale.forLanguageTag`, `Locale.Builder` và `getScript`.

~~~java
import java.util.Locale;

public class ScriptParts {
    public static void main(String[] args) {
        Locale latin = Locale.forLanguageTag("sr-Latn-RS");
        Locale cyrillic = new Locale.Builder()
                .setLanguage("sr")
                .setScript("Cyrl")
                .setRegion("RS")
                .build();
        Locale unspecified = Locale.forLanguageTag("sr-RS");

        System.out.println(latin.toLanguageTag());
        System.out.println(latin.getLanguage());
        System.out.println(latin.getScript());
        System.out.println(latin.getCountry());
        System.out.println(cyrillic.toLanguageTag());
        System.out.println(unspecified.getScript().isEmpty());
    }
}
~~~

Lưu thành `ScriptParts.java` rồi chạy:

~~~bash
javac -encoding UTF-8 ScriptParts.java
java ScriptParts
~~~

Kết quả:

~~~text
sr-Latn-RS
sr
Latn
RS
sr-Cyrl-RS
true
~~~

Giải thích:

- `toLanguageTag()` tạo lại thẻ BCP 47 với dấu gạch nối (`-`).
- `getLanguage()` trả về `sr`; `getCountry()` trả về `RS`.
- `getScript()` trả về `Latn` hoặc `Cyrl` khi có script, và chuỗi rỗng `""` khi không khai báo.
- `Locale.Builder` giúp tạo locale có đủ language, script, region và kiểm tra subtag hợp lệ. Đối với thẻ từ nguồn ngoài, cần kiểm tra/chuẩn hóa dữ liệu đầu vào; `Locale.forLanguageTag` có thể xử lý thẻ không chuẩn theo cách bỏ qua phần không hợp lệ thay vì luôn ném lỗi.
- Hai đối tượng `Locale` khác nhau về script không nên bị gộp làm một khi script là yêu cầu chức năng của ứng dụng.

**Lưu ý quan trọng:** Java `String` dùng Unicode, nên cùng một ứng dụng có thể chứa “Zdravo” và “Здраво”. Việc chọn `Locale.forLanguageTag("sr-Cyrl-RS")` **không tự biến** chuỗi “Zdravo” thành “Здраво”. Ứng dụng phải cung cấp tài nguyên tương ứng hoặc áp dụng bộ chuyển tự riêng nếu thật sự có yêu cầu chuyển tự.

## 4. Ứng dụng thực tế: chọn đúng `ResourceBundle` theo script

Giả sử một giao diện Java hỗ trợ tiếng Serbia bằng hai hệ chữ viết. Có thể tổ chức các tài nguyên sau trong cùng thư mục/classpath:

~~~text
.
├── LocaleScriptDemo.java
├── Messages.properties
├── Messages_sr_Latn.properties
└── Messages_sr_Cyrl.properties
~~~

Nội dung `Messages.properties` (bản dự phòng):

~~~properties
hello=Hello
~~~

Nội dung `Messages_sr_Latn.properties`:

~~~properties
hello=Zdravo
~~~

Nội dung `Messages_sr_Cyrl.properties` (lưu file UTF-8):

~~~properties
hello=Здраво
~~~

Tạo `LocaleScriptDemo.java`:

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

public class LocaleScriptDemo {
    public static void main(String[] args) {
        String[] tags = {"sr-Latn-RS", "sr-Cyrl-RS"};

        for (String tag : tags) {
            Locale locale = Locale.forLanguageTag(tag);
            ResourceBundle bundle = ResourceBundle.getBundle("Messages", locale);

            System.out.printf(
                    "%s | language=%s | script=%s | region=%s | hello=%s%n",
                    locale.toLanguageTag(),
                    locale.getLanguage(),
                    locale.getScript(),
                    locale.getCountry(),
                    bundle.getString("hello")
            );
        }
    }
}
~~~

Từ thư mục chứa tất cả các file trên, chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 LocaleScriptDemo.java
java -cp . LocaleScriptDemo
~~~

Kết quả mong đợi:

~~~text
sr-Latn-RS | language=sr | script=Latn | region=RS | hello=Zdravo
sr-Cyrl-RS | language=sr | script=Cyrl | region=RS | hello=Здраво
~~~

**Điều gì xảy ra?**

1. `Locale.forLanguageTag` đọc thẻ locale và giữ lại script.
2. `ResourceBundle.getBundle("Messages", locale)` tìm tài nguyên tương ứng. Với các file có mặt ở ví dụ này, locale Latin chọn `Messages_sr_Latn.properties`, locale Cyrillic chọn `Messages_sr_Cyrl.properties`.
3. `getString("hello")` trả về văn bản đã được chuẩn bị cho đúng chữ viết.
4. Java 9+ hỗ trợ đọc tài nguyên `.properties` của `PropertyResourceBundle` theo UTF-8 mặc định (có cơ chế dự phòng cho một số byte không hợp lệ). Ví dụ dùng JDK 17+ và file được lưu UTF-8 để giữ nguyên chữ Cyrillic.

Tên thẻ BCP 47 dùng **dấu nối** như `sr-Latn-RS`, còn quy ước tên file `ResourceBundle` dùng **dấu gạch dưới** như `Messages_sr_Latn.properties`; không nhầm hai cú pháp này.

### Nếu thiếu tài nguyên theo script thì sao?

`ResourceBundle` có cơ chế tìm chuỗi ứng viên và fallback; ứng dụng có thể sử dụng tài nguyên mức khái quát hơn, bản gốc (`Messages.properties`), hoặc trong một số tình huống thử cả locale mặc định của JVM. Không nên cho rằng mọi trường hợp thiếu `Messages_sr_Latn.properties` đều tự động nhận một bản Latin đúng ý hoặc luôn rơi thẳng về file gốc. Hãy kiểm thử thực tế với tập tài nguyên và cấu hình fallback của ứng dụng.

Đối với nội dung bắt buộc đúng script, nên **định nghĩa quy tắc fallback có chủ đích**: chọn ưu tiên cùng ngôn ngữ + script, cảnh báo nếu thiếu tài nguyên, rồi chọn phương án đã được sản phẩm chấp thuận. Dùng nhầm bản Cyrillic để phục vụ yêu cầu Latin (hoặc ngược lại) có thể làm giao diện khó đọc dù mã ngôn ngữ vẫn đúng.

## 5. Quy tắc thiết kế ứng dụng đa ngôn ngữ

### Khi chọn và lưu locale

- Lưu đầy đủ thẻ `language-Script-REGION` khi script đã được người dùng chọn, ví dụ `sr-Latn-RS`; đừng rút gọn thành `sr` hoặc `sr-RS` làm mất ưu tiên chữ viết.
- Chỉ yêu cầu chọn script khi cần phân biệt thực sự; không phải ngôn ngữ nào cũng có nhiều script thông dụng trong sản phẩm.
- Với đầu vào không có script, giữ rõ trạng thái “chưa chỉ định”, rồi áp dụng chính sách mặc định dựa trên nhu cầu sản phẩm và dữ liệu locale. Không giả định `getScript()` sẽ tự điền.
- Hiển thị lựa chọn bằng tên dễ hiểu cho người dùng, ví dụ “Srpski (latinica)” và “Српски (ћирилица)”, thay vì chỉ hiện hai mã `sr` giống nhau.
- Xây dựng test với ít nhất hai locale có cùng language và region nhưng khác script để phát hiện việc bỏ sót thành phần script trong khóa cache, cơ chế matching hoặc định tuyến tài nguyên.

### Khi xử lý văn bản

- **Địa phương hóa** (*localization*): cung cấp nội dung và định dạng phù hợp với locale mục tiêu.
- **Chuyển tự** (*transliteration*): chuyển cách viết giữa các hệ chữ; đây là một quá trình xử lý văn bản riêng, có thể cần quy tắc ngôn ngữ và xử lý ngoại lệ.
- **Dịch** (*translation*): chuyển ý nghĩa giữa các ngôn ngữ. Hai locale chỉ khác script vẫn có thể yêu cầu nội dung biên tập và từ ngữ khác, không nhất thiết giải quyết được bằng chuyển tự.
- **Font/rendering**: vẫn phải có font hỗ trợ các ký tự cần hiển thị. `Locale` không tự cài font, đổi encoding hoặc bảo đảm glyph hiện đúng.

Với `zh-Hans` và `zh-Hant`, giản thể/phồn thể có liên hệ với hệ chữ Hán, nhưng việc chuẩn bị nội dung phù hợp có thể gồm cả khác biệt về thuật ngữ và cách diễn đạt. Không xem bài toán này chỉ là thay thế ký tự một-một.

## 6. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu và xử lý đúng |
| --- | --- |
| “Cùng `language` nghĩa là cùng nội dung giao diện.” | Phải xem thêm `script` và những khác biệt locale cần hỗ trợ. `sr-Latn-RS` và `sr-Cyrl-RS` không thay thế vô điều kiện cho nhau. |
| “Có `region=RS` thì `getScript()` tự trả `Cyrl`.” | Nếu thẻ nguồn không khai báo script, `getScript()` trả chuỗi rỗng; suy luận thường dùng ở hệ thống khác không thay đổi đối tượng `Locale` này. |
| “Thay `Locale` sẽ tự chuyển tự toàn bộ chuỗi.” | `Locale` giữ metadata để chọn cách xử lý/tài nguyên; cần bản dịch theo script hoặc thuật toán chuyển tự riêng. |
| “`Script` là mã vùng hoặc encoding.” | `Latn`/`Cyrl` là mã ISO 15924; `RS` là mã vùng; UTF-8 là encoding, thuộc khái niệm khác. |
| “Tên file bundle giống hệt thẻ BCP 47.” | Thẻ dùng `-`, hậu tố bundle dùng `_`. |
| “Chỉ test `sr-RS` là đủ.” | Test từng script tường minh, cả trường hợp thiếu script hoặc thiếu bundle, và quan sát đường fallback. |

## 7. Cách tự kiểm tra kiến thức

1. Tạo ba locale `sr-Latn-RS`, `sr-Cyrl-RS`, `sr-RS`. So sánh `getLanguage()`, `getCountry()`, `getScript()`. Trường nào phân biệt hai locale đầu tiên?
2. Chạy ví dụ `ResourceBundle`; đổi tên `Messages_sr_Latn.properties` tạm thời để quan sát thực tế fallback, sau đó khôi phục file. Vì sao kết quả đó cần được kiểm soát khi giao diện phải đúng script?
3. Thiết kế khóa lưu bản dịch cho ngôn ngữ Serbia. Vì sao chỉ dùng `language + region` sẽ tạo nguy cơ va chạm?
4. Giải thích vì sao “chọn `zh-Hant-TW`” không đồng nghĩa với “Java tự chuyển toàn bộ văn bản giản thể đang có thành phồn thể”.

**Ghi nhớ:** Khi nhiều locale chia sẻ cùng một ngôn ngữ, **script là thành phần định danh quan trọng của lựa chọn hiển thị và tài nguyên**. Trong Java, hãy biểu diễn script tường minh bằng BCP 47/`Locale` khi cần, bảo toàn nó xuyên suốt quá trình chọn locale và kiểm thử fallback của tài nguyên.