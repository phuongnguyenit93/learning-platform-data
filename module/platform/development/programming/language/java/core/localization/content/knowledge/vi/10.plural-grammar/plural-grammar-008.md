# Nhận diện khi yêu cầu ngôn ngữ vượt khả năng API Java Core

Bản địa hóa không chỉ là đổi nhãn giao diện. Một câu thông báo có thể phải thay **dạng số nhiều**, **giống ngữ pháp**, **cách chia động từ**, **thứ tự từ**, **cách/case của danh từ**, **dạng thứ tự (ordinal)** hoặc cả cấu trúc câu theo ngôn ngữ. Java Core hỗ trợ lưu bản dịch bằng `ResourceBundle`, định dạng số/ngày bằng `NumberFormat` và `DateFormat`, chèn biến vào câu bằng `MessageFormat`, cùng lựa chọn theo khoảng số qua `ChoiceFormat`. Tuy nhiên, các API này **không phải hệ thống ngữ pháp tổng quát** và không tự triển khai quy tắc số nhiều theo CLDR cho mọi ngôn ngữ.

Mục tiêu của bài là biết **nhận diện lúc yêu cầu ngôn ngữ đã vượt khả năng của API Java Core** để chọn kiến trúc và công cụ đúng, thay vì cố ép ngữ pháp phức tạp vào vài điều kiện `if`, vào `ResourceBundle` hoặc vào `ChoiceFormat`.

## 1. Ranh giới giữa định dạng dữ liệu và tạo câu tự nhiên

Hãy phân biệt ba việc:

1. **Lấy bản dịch đã viết sẵn:** `ResourceBundle.getString("cart.title")` trả về văn bản theo khóa và locale, có thể fallback sang bundle cha. Nó không tự chia danh từ.
2. **Định dạng giá trị:** `NumberFormat` định dạng `1234.5` theo locale; `DateFormat` định dạng ngày. Những API này không quyết định cả câu nên dùng dạng động từ hoặc danh từ nào.
3. **Tạo thông điệp phụ thuộc ngữ pháp:** “1 file” / “2 files”, “1 объект” / “2 объекта” / “5 объектов”, hoặc biến đổi cấu trúc lời chào tùy giới/cách ngữ pháp của các thành phần trong câu. Đây là bài toán ngôn ngữ học, không chỉ là chèn số.

Ví dụ tiếng Anh đơn giản:

~~~text
0 files
1 file
2 files
~~~

Nếu giả định mọi ngôn ngữ đều dùng quy tắc “bằng 1 là số ít, còn lại số nhiều”, ứng dụng sẽ sai với những ngôn ngữ có nhiều dạng theo số đếm, với phân số và trong nhiều tình huống có ngữ cảnh ngữ pháp khác nhau.

Một ví dụ chỉ về **phân loại số nguyên tiếng Nga**:

~~~text
1  → one
2  → few
5  → many
11 → many
21 → one
22 → few
~~~

Đây là **tên các nhóm phân loại**, không phải bản dịch đầy đủ và không bao trùm số thập phân. Điều quan trọng là `21` có thể thuộc nhóm giống `1`, trong khi `11` lại thuộc nhóm khác: quy tắc đơn giản `count == 1` không đủ.

## 2. Java Core làm được gì, không làm được gì?

| Công cụ Java 17 | Khả năng phù hợp | Giới hạn cần nhận diện |
| --- | --- | --- |
| `Locale` | Mô tả ngôn ngữ/vùng/script và tùy chọn locale | Không chứa sẵn bộ máy biến đổi câu và quy tắc ngữ pháp tổng quát |
| `ResourceBundle` | Tải văn bản/tài nguyên theo khóa và chuỗi locale | Không tự chọn plural category, giống, cách hoặc dạng động từ |
| `MessageFormat` (`java.text`) | Chèn đối số vào mẫu, định dạng number/date/time/choice | Không hỗ trợ cú pháp ICU `plural`, `select`, `selectordinal` của MessageFormat ICU trong Java 17 |
| `ChoiceFormat` | Chọn chuỗi theo ngưỡng số bằng pattern đã khai báo | Không tự áp dụng quy tắc CLDR phụ thuộc locale; không phải bộ máy plural tổng quát |
| `NumberFormat` | Định dạng số, phân tách hàng nghìn/chữ số tùy locale | Không chọn dạng từ ngữ hay cấu trúc câu |
| `DateFormat` | Định dạng ngày/giờ theo locale | Không bảo đảm sinh mọi cấu trúc ngữ pháp cần trong câu tự nhiên |

Cần phân biệt **API Java Core** với thư viện ngoài có lớp hoặc tên gần giống. Chẳng hạn `java.text.MessageFormat` **khác** `com.ibm.icu.text.MessageFormat` của ICU4J: không được lấy pattern ICU rồi truyền vào `java.text.MessageFormat` và kỳ vọng nó hiểu toàn bộ cú pháp đó.

**Cảnh báo về phiên bản:** Phần nhận định và ví dụ ở đây nhắm đến Java 17. Khi cập nhật JDK hoặc thêm thư viện/framework, hãy kiểm tra hợp đồng API thực tế; không coi mọi lớp mang tên `MessageFormat` là tương đương.

## 3. Dấu hiệu thứ nhất: plural không còn là “1 và nhiều”

Khi yêu cầu có số lượng, đặt câu hỏi:

- Tập ngôn ngữ đích gồm những ngôn ngữ nào?
- Số lượng là **số nguyên** hay có thể là **thập phân** (`1.0`, `1.5`, `2.25`)?
- Có thể là **âm**, rất lớn, hoặc dùng số được hiển thị sau làm tròn?
- Đang nói về **cardinal** (đếm “bao nhiêu”) hay **ordinal** (thứ “mấy”)?
- Tên danh từ/đơn vị đi kèm có thay đổi theo **giống, cách hoặc ngữ cảnh** không?

Trong CLDR, các nhóm plural được đặt tên `zero`, `one`, `two`, `few`, `many`, `other`. Đây là **tên nhóm quy tắc**, không có nghĩa một ngôn ngữ nhất thiết dùng đủ sáu nhóm, và `zero` không đơn giản là “số 0”, `one` cũng không có nghĩa luôn là giá trị số học 1. Nhóm được xác định theo quy tắc của ngôn ngữ và ngữ cảnh cardinal/ordinal.

Ví dụ:

- Tiếng Anh trong quy tắc cardinal thường phân biệt `one` và `other`, nhưng cách xử lý số thập phân cần theo CLDR thay vì chỉ dựa trên một phép so sánh tùy ý.
- Tiếng Nga có nhóm `one`, `few`, `many` cho nhiều số nguyên và các trường hợp thập phân cần xử lý riêng; `11` và `21` không nên suy ra từ cùng một kiểm tra hàng đơn vị.
- Tiếng Ả Rập có nhiều nhóm đếm, thường vượt xa một lựa chọn số ít/số nhiều.
- Tiếng Việt nói chung không bắt buộc biến tố danh từ theo số đếm giống tiếng Anh, nhưng thông điệp vẫn có thể đòi hỏi lựa chọn từ, phân loại từ hoặc cách diễn đạt khác; không áp đặt công thức Anh cho tiếng Việt.

**Khi nào vượt Java Core?** Khi sản phẩm phải quyết định plural category theo ngôn ngữ cho nhiều locale, đặc biệt với số thập phân và cardinal/ordinal, `ChoiceFormat` không tự cung cấp bộ quy tắc đó. Bạn sẽ phải duy trì các quy tắc riêng — khó và dễ sai — hoặc sử dụng công cụ có dữ liệu/quy tắc plural tương ứng.

### ChoiceFormat chỉ là lựa chọn theo ngưỡng số

`ChoiceFormat` có thể biểu diễn:

~~~text
0#no files|1#one file|1<many files
~~~

Trong pattern trên, `#` chọn từ một ngưỡng bao gồm; `<` chọn ngưỡng lớn hơn (theo quy tắc của `ChoiceFormat`). Nó hữu dụng cho một bài toán hữu hạn và quy tắc đã xác định. Nhưng không có tham số nào ở đây bảo Java tự chuyển sang plural category tiếng Nga, tiếng Ả Rập hoặc tiếng Ba Lan.

Các ngưỡng số và các nhóm CLDR **không cùng khái niệm**. Quy tắc tiếng Nga phụ thuộc vào chữ số hàng đơn vị và hai chữ số cuối; một vài khoảng cố định sẽ không tổng quát cho mọi số nguyên không giới hạn.

## 4. Dấu hiệu thứ hai: ordinal khác cardinal

Câu “3 files” thuộc loại **cardinal**; câu “3rd place” thuộc loại **ordinal** trong tiếng Anh. Hai loại dùng quy tắc và thông điệp khác nhau. Không lấy logic `one/other` cardinal để tạo đuôi `st/nd/rd/th` một cách đơn giản:

~~~text
1st, 2nd, 3rd, 4th
11th, 12th, 13th
21st, 22nd, 23rd
~~~

Một rule “hàng đơn vị là 1 thì thêm `st`” sẽ sai với `11th`. Khi triển khai nhiều ngôn ngữ, một số ngôn ngữ có dạng ordinal rất khác hoặc không dùng hậu tố như tiếng Anh.

**Tín hiệu vượt khả năng API:** Yêu cầu hỗ trợ thứ hạng, ngày thứ, vị trí hoặc thứ tự theo nhiều locale với quy tắc ordinal đúng, chứ không chỉ hiển thị con số. `NumberFormat` định dạng số không tự sinh ordinal trong câu; `MessageFormat` Java 17 không hỗ trợ pattern ICU `selectordinal`.

Một hệ thống có thể chọn viết cả câu riêng cho từng thứ hạng hữu hạn (ví dụ top 3) nếu nghiệp vụ chỉ có đúng những trường hợp ấy. Khi đầu vào là mọi số và mọi ngôn ngữ, giải pháp hữu hạn thường không đủ.

## 5. Dấu hiệu thứ ba: chọn giống và cấu trúc câu, không chỉ tên từ

Một số thông điệp cần biến đổi theo **giống ngữ pháp của danh từ**, **loại chủ thể**, **cách xưng hô**, hoặc sự hòa hợp giữa các từ trong câu.

Ví dụ đặc tả:

~~~text
subjectCategory = masculine | feminine | neuter | other
count = 1 | 2 | 5 | ...
message = một câu đầy đủ phù hợp subjectCategory và count
~~~

Đây là **mô hình dữ liệu**, không phải pattern Java Core. Không nên đồng nhất `subjectCategory` với giới tính sinh học của người dùng; ở nhiều ngôn ngữ, **giống ngữ pháp là thuộc tính của từ**. Việc thu thập dữ liệu giới tính cá nhân chỉ để chia câu có thể không cần thiết và gây rủi ro riêng tư. Hãy mô hình hóa thông tin ngôn ngữ thực sự cần cho thông điệp.

Khi một câu thay đổi theo **cả count và grammatical gender**, số nhánh có thể là tích của các lựa chọn và đôi khi còn phụ thuộc cách, thứ tự hoặc ngữ cảnh. Việc ghép “prefix + translated noun + suffix” có thể tạo câu sai ở ngôn ngữ khác do thứ tự từ và tính hòa hợp.

**Tín hiệu vượt khả năng API:** Người dịch phải viết các câu hoàn chỉnh khác nhau dựa trên `gender/select` và `plural`, đặc biệt khi chúng lồng nhau. Java Core `MessageFormat` không có cú pháp `select`/plural ICU để mô tả các nhánh ngữ pháp đó bằng dữ liệu bản dịch theo cách trực tiếp.

## 6. Dấu hiệu thứ tư: case, agreement, context và inflection

Các ngôn ngữ có thể thay đổi dạng danh từ, tính từ, số từ hoặc động từ theo:

- **Cách ngữ pháp (grammatical case):** vị trí của từ trong câu làm thay đổi hình thái, ví dụ các vai trò chủ ngữ, bổ ngữ hoặc sở hữu ở một số ngôn ngữ.
- **Sự hòa hợp (agreement):** tính từ hoặc động từ biến đổi để phù hợp danh từ/chủ thể.
- **Ngữ cảnh câu:** một nhãn ngắn đứng riêng có thể khác dạng khi được đặt trong một câu.
- **Giới từ hoặc dạng rút gọn:** quyết định dựa trên âm/cấu trúc câu, không chỉ dịch từng token.
- **Từ loại hoặc mức độ lịch sự:** dạng mệnh lệnh, câu hỏi hoặc lời nhắc có thể thay đổi đáng kể.

Ví dụ yêu cầu nghiệp vụ “Hiển thị `{count}` sản phẩm trong `{location}` bằng một câu tự nhiên cho 12 ngôn ngữ” có thể đòi thay danh từ theo số, thay giới từ, cách của địa danh, và trật tự thành phần. `MessageFormat` Java Core có thể chèn số và địa điểm vào câu mẫu, nhưng **không tự suy luận cú pháp ngôn ngữ**.

Thay vì cố tạo câu bằng nhiều fragment, hãy để người dịch kiểm soát mẫu câu **ở mức một thông điệp hoàn chỉnh**, và dùng API hoặc thư viện phù hợp để điều kiện ngữ pháp nằm trong nội dung được quản lý. Trong trường hợp đặc biệt phức tạp, ngay cả formatter plural/select cũng có thể chưa đủ; có thể cần các mẫu câu chuyên biệt, dữ liệu biến tố do chuyên gia ngôn ngữ cung cấp, hoặc một lớp sinh ngôn ngữ tự nhiên được kiểm thử riêng.

## 7. Ví dụ Java 17 chạy được: Java Core hỗ trợ đến đâu?

Chương trình sau làm ba việc:

1. Dùng `java.text.MessageFormat` với nhánh `choice` cho **một ví dụ tiếng Anh đơn giản**.
2. Minh họa **quy tắc tùy chỉnh** phân nhóm **số nguyên cardinal không âm tiếng Nga**, chỉ để làm rõ tại sao logic “1 hay khác 1” không đủ. Hàm này **không phải** bộ máy CLDR tổng quát.
3. Chỉ ra pattern ICU `plural` **không** được `java.text.MessageFormat` Java 17 chấp nhận.

Tạo tệp **`CoreGrammarLimitsDemo.java`**:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class CoreGrammarLimitsDemo {
    static String simpleEnglish(int count) {
        if (count < 0) {
            throw new IllegalArgumentException("count must be >= 0");
        }
        MessageFormat format = new MessageFormat(
                "{0,choice,0#no files|1#one file|1<{0,number,integer} files}",
                Locale.US);
        return format.format(new Object[] { count });
    }

    // Chỉ minh họa nhóm cardinal của số nguyên không âm tiếng Nga.
    // KHÔNG xử lý thập phân, ordinal, giống hay cách ngữ pháp.
    static String russianIntegerCategory(long count) {
        if (count < 0) {
            throw new IllegalArgumentException("count must be >= 0");
        }
        long last10 = count % 10;
        long last100 = count % 100;
        if (last10 == 1 && last100 != 11) {
            return "one";
        }
        if (last10 >= 2 && last10 <= 4
                && (last100 < 12 || last100 > 14)) {
            return "few";
        }
        return "many";
    }

    public static void main(String[] args) {
        for (int count : new int[] { 0, 1, 2 }) {
            System.out.println(
                    "EN " + count + ": " + simpleEnglish(count));
        }
        for (long count : new long[] { 1, 2, 5, 11, 21, 22 }) {
            System.out.println("RU " + count + ": "
                    + russianIntegerCategory(count));
        }

        try {
            new MessageFormat(
                    "{count, plural, one{item} other{items}}",
                    Locale.US);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "ICU plural pattern: unsupported by Java 17");
        }
    }
}
~~~

Biên dịch và chạy (JDK 17 trở lên):

~~~bash
javac -encoding UTF-8 CoreGrammarLimitsDemo.java
java CoreGrammarLimitsDemo
~~~

Stdout đã kiểm tra bằng JDK:

~~~text
EN 0: no files
EN 1: one file
EN 2: 2 files
RU 1: one
RU 2: few
RU 5: many
RU 11: many
RU 21: one
RU 22: few
ICU plural pattern: unsupported by Java 17
~~~

Giải thích:

- `choice` là cách xử lý hợp lý cho thông điệp tiếng Anh minh họa với số nguyên không âm, nhưng pattern này do lập trình viên viết **cố định**, không phát sinh từ CLDR.
- `russianIntegerCategory` thể hiện quy tắc nhóm theo `% 10` và `% 100`, nên `11` thuộc `many` còn `21` thuộc `one`. Bài toán thực còn xét dạng thập phân và các yếu tố CLDR khác; không dùng hàm minh họa này làm quy tắc production cho mọi dạng số.
- Từ khóa `plural` trong pattern ICU không phải một kiểu format của `java.text.MessageFormat` Java 17. Constructor ném `IllegalArgumentException`, được bắt để chứng minh giới hạn.
- Câu trả lời `one/few/many` chỉ là **nhãn phân loại**, chưa phải bản dịch tiếng Nga hoàn chỉnh. Với bản dịch thực, người dịch phải cung cấp mẫu cho mỗi category phù hợp, và có thể còn phải xét case/giống/ngữ cảnh.

**Không hiểu nhầm:** Việc một ứng dụng có thể tự viết `if`, `switch` hoặc thuật toán biến tố bằng Java không có nghĩa **API chuẩn của Java Core đã cung cấp đầy đủ dữ liệu và quy tắc ngữ pháp đó**. Khi tự viết, toàn bộ gánh nặng đúng ngôn ngữ, bảo trì và kiểm thử thuộc về ứng dụng.

## 8. Khi nào Java Core vẫn đủ?

Không phải mọi thông điệp chứa số đều cần thư viện ngoài. Java Core có thể đủ khi:

- Hệ thống chỉ hỗ trợ **ít ngôn ngữ và quy tắc đã được giới hạn, xác minh**.
- Mỗi lựa chọn ngữ pháp có **tập hữu hạn nhỏ** và sản phẩm có thể dùng các thông điệp hoàn chỉnh riêng.
- Các câu không phụ thuộc giống/case/ordinal phức tạp; chỉ cần định dạng dữ liệu và chọn một mẫu đã viết sẵn.
- Đội ngũ có thể xác minh toàn bộ tập đầu vào và cập nhật bản dịch đúng quy trình.

Một thiết kế đơn giản, tường minh:

~~~properties
# messages_en.properties
notification.one=You have {0} notification.
notification.other=You have {0} notifications.
~~~

~~~java
// Đoạn minh họa trong chương trình đã có ResourceBundle bundle,
// số count kiểu int hợp lệ, Locale locale của người dùng.
String key = (count == 1)
        ? "notification.one"
        : "notification.other";

String template = bundle.getString(key);
String message = new MessageFormat(template, locale)
        .format(new Object[] { count });
~~~

Đoạn này chỉ minh họa cách **ứng dụng** chọn key. `ResourceBundle` không tự chọn `one/other`; `MessageFormat` chỉ chèn giá trị vào mẫu. Nếu đổi sang tiếng Nga hoặc tiếng Ả Rập, không được giữ nguyên phép chọn `count == 1`.

Nên đặt câu hoàn chỉnh cho từng nhánh, thay vì để người dịch nhận nhiều mảnh như `prefix`, `noun`, `suffix` rồi ghép bằng toán tử `+`. Trật tự từ và cách chia có thể khác nhau giữa các ngôn ngữ.

## 9. Khi nào phải chọn thư viện i18n có quy tắc ngôn ngữ?

Cần đánh giá giải pháp chuyên dụng khi một hoặc nhiều yêu cầu sau xuất hiện:

| Tín hiệu yêu cầu | Nguy cơ nếu chỉ dùng Java Core | Tiêu chí giải pháp cần có |
| --- | --- | --- |
| Nhiều ngôn ngữ với plural khác nhau | Đếm sai hoặc dạng danh từ sai | Có CLDR cardinal plural theo locale |
| Số thập phân và quy tắc phức tạp | `count == 1`/modulo số nguyên sai | Đúng operands và nhóm của số thập phân |
| Ordinal theo locale | Sinh sai thứ hạng | Có quy tắc ordinal riêng |
| Chọn theo giống ngữ pháp | Ghép câu lỗi hoặc sai cách chia | Có điều kiện `select` hoặc mẫu câu tương đương |
| Lồng plural và select | Bùng nổ `if/else` trong code | Hỗ trợ biểu diễn nhánh lồng và kiểm thử |
| Nhiều biến thể case/agreement | Sai cấu trúc câu | Có dữ liệu/chiến lược mẫu câu do người dịch kiểm soát |
| Bản dịch cập nhật thường xuyên | Logic ngôn ngữ bị rải trong mã nguồn | Quản lý mẫu tập trung, kiểm định và versioning |
| Mẫu được dịch bởi đội nhiều ngôn ngữ | Người dịch không thể sửa logic Java | Định dạng message có cú pháp nhất quán và tooling |

Một lựa chọn phổ biến trong hệ Java là **ICU4J** cùng dữ liệu/quy tắc dựa trên CLDR. ICU4J có các API liên quan đến plural rules và message formatting, bao gồm khả năng chọn nhánh plural/select trong các phiên bản có hỗ trợ. Tuy nhiên:

- ICU4J là **thư viện bên ngoài JDK**; phải khai báo dependency, kiểm tra phiên bản và bản quyền theo chính sách dự án.
- **Không** truyền mẫu ICU vào `java.text.MessageFormat`; phải dùng lớp formatter của thư viện tương ứng.
- Một thư viện plural/select tốt cũng **không tự dịch nội dung**. Người dịch vẫn cần cung cấp thông điệp đúng và làm rõ yêu cầu ngôn ngữ.
- Hãy xác minh dữ liệu CLDR và phiên bản ICU được dùng khi quy tắc thay đổi; việc cập nhật thư viện có thể làm thay đổi kết quả phân loại tại các trường hợp biên.
- Đừng giả định một API có thể tự giải quyết mọi case/agreement/inflection. Trường hợp ngữ pháp phức tạp có thể cần nhiều mẫu hoàn chỉnh, dữ liệu biến tố hoặc quy trình biên tập ngôn ngữ.

Ví dụ **pattern ở cấp khái niệm theo cú pháp ICU MessageFormat**, **không chạy bằng `java.text.MessageFormat` Java 17**:

~~~text
{count, plural,
    one {# item}
    other {# items}
}
~~~

Pattern này chỉ minh họa việc lưu lựa chọn plural trong tài nguyên mà người dịch có thể quản lý. Không dùng trực tiếp nó như đoạn code Java có thể chạy. Nhóm nào cần có, văn bản mỗi nhóm và việc chèn số phải kiểm tra theo locale đích. Với ngôn ngữ khác tiếng Anh, chỉ ghi `one/other` có thể không đủ.

## 10. Không thể chỉ trông vào Locale và ResourceBundle

`Locale.forLanguageTag("ru-RU")` tạo một `Locale` hợp lệ, nhưng **không phải bằng chứng rằng chương trình có bộ quy tắc số nhiều tiếng Nga**. `NumberFormat.getInstance(locale)` định dạng số theo locale, nhưng không phân biệt `one/few/many` của thông điệp. `ResourceBundle.getBundle("messages", locale)` chọn bộ tài nguyên theo locale và có thể truy cập bundle cha, nhưng **không tự phân tích count hay grammatical gender**.

Một nhầm lẫn khác là coi việc fallback sang tài nguyên cha như fallback ngữ pháp. Khi bộ `ru-RU` thiếu khóa plural `files.few`, Java có thể tìm được một chuỗi từ bundle cha; chuỗi đó chưa chắc phù hợp với ngữ cảnh số nhiều của tiếng Nga. Cần coi **đủ và đúng các nhánh ngôn ngữ** là yêu cầu dữ liệu bản dịch, không chỉ yêu cầu `containsKey` trả `true`.

Thứ tự xử lý điển hình:

~~~text
Yêu cầu của người dùng / locale
       |
       v
Chọn locale mà ứng dụng hỗ trợ
       |
       v
Phân loại điều kiện ngữ pháp theo locale
    (count, ordinal, select, context...)
       |
       v
Lấy thông điệp phù hợp do người dịch cung cấp
       |
       v
Định dạng giá trị và các placeholder
       |
       v
Kiểm thử câu đầu ra hoàn chỉnh
~~~

Các bước có thể được một thư viện formatter chuyên dụng kết hợp trong cùng một API, nhưng vẫn nên kiểm tra từng trách nhiệm khi thiết kế hệ thống.

## 11. Lập danh sách câu hỏi trước khi quyết định công cụ

Trước khi chọn `MessageFormat` Java Core hoặc ICU4J/framework i18n, hãy viết rõ:

1. **Ngôn ngữ và phiên bản vùng nào** được yêu cầu? Ví dụ `en-US`, `ru-RU`, `ar`, `pl-PL`, `vi-VN`.
2. **Dữ liệu đếm loại gì?** Chỉ số nguyên không âm, hay có cả `0`, `-1`, `1.0`, `1.5`, `2.25`, số rất lớn?
3. **Dùng cardinal hay ordinal?** Một UI có thể có cả “3 items” và “3rd item”.
4. **Có điều kiện phi số không?** Giống ngữ pháp, vai trò, loại đối tượng, trạng thái hành động, ngôi xưng?
5. **Các lựa chọn có lồng nhau không?** Ví dụ count và gender ảnh hưởng đồng thời tới câu.
6. **Dữ liệu bản dịch do ai quản lý?** Developer hay translator; có cần điều chỉnh mà không phát hành code?
7. **Fallback được phép đến đâu?** Có thể dùng ngôn ngữ khác không, hay cần từ chối nếu thiếu mẫu đúng?
8. **Tiêu chí kiểm thử là gì?** Một vài ví dụ minh họa hay ma trận locale × category × loại số × ngữ cảnh?
9. **Có yêu cầu dữ liệu ngôn ngữ được cập nhật không?** Nếu dùng CLDR, phiên bản nào và chính sách nâng cấp ra sao?
10. **Có ràng buộc pháp lý hoặc tính chính xác cao không?** Với nội dung nhạy cảm, cần người dịch/chuyên gia ngôn ngữ phê duyệt.

Sau khi trả lời, có thể đưa ra quyết định kỹ thuật có thể kiểm chứng:

- Nếu thông điệp hoàn toàn tĩnh: `ResourceBundle` đủ.
- Nếu cần chèn ngày/số và ít lựa chọn hữu hạn: `MessageFormat`/Java Core có thể đủ.
- Nếu cần plural/ordinal nhiều ngôn ngữ dựa trên CLDR: cân nhắc thư viện có quy tắc tương ứng.
- Nếu có giống/case/agreement hay điều kiện lồng: cần formatter và mô hình tài nguyên cho nhánh ngữ pháp, cùng kiểm định ngôn ngữ.
- Nếu phải biến tố tự nhiên theo ngữ cảnh mở: xác minh liệu formatter có đủ hay cần kiến trúc chuyên biệt và biên tập ngôn ngữ.

## 12. Những lỗi phổ biến và hệ quả

| Sai lầm | Vì sao sai | Cách phòng tránh |
| --- | --- | --- |
| Dùng `count == 1` cho mọi ngôn ngữ | Các locale có số lượng nhóm và quy tắc khác nhau | Xác định quy tắc theo locale và loại plural |
| Dùng cùng logic cho cardinal và ordinal | Nhóm và ngữ cảnh khác nhau | Tách mục đích đếm/thứ tự |
| Dùng `ChoiceFormat` như CLDR plural engine | Choice chọn theo ngưỡng, không tự có quy tắc ngôn ngữ | Dùng engine/rules khi nhiều locale |
| Truyền pattern ICU `plural` vào `java.text.MessageFormat` | Cú pháp không được Java 17 hỗ trợ | Dùng formatter thực sự hỗ trợ syntax |
| Cho rằng `ResourceBundle` tự chọn `files.one`/`files.other` | Bundle chỉ lấy value theo key | Viết logic rõ hoặc dùng formatter chuyên dụng |
| Ghép câu bằng prefix + số + noun | Sai thứ tự từ, agreement hoặc cách ngữ pháp | Dùng mẫu câu hoàn chỉnh do translator viết |
| Chia plural chỉ dựa trên số đã làm tròn | Có thể đổi nhóm do operands của số thập phân | Thiết kế chính sách định dạng/đếm và kiểm thử |
| Dùng “giới tính người dùng” thay cho giống ngữ pháp | Mô hình sai và thu thập dữ liệu thừa | Phân biệt thuộc tính ngôn ngữ với dữ liệu cá nhân |
| Cho rằng mọi thiếu key có thể fallback an toàn sang ngôn ngữ gốc | Mẫu fallback có thể sai ngữ pháp | QA tính đầy đủ và chính sách fallback theo nội dung |
| Dùng vài ví dụ 1, 2, 3 làm bằng chứng hỗ trợ ngôn ngữ | Không kiểm tra 0, 11, 21, thập phân và ordinal | Kiểm thử theo các nhóm CLDR và ranh giới |
| Đưa các quy tắc ngôn ngữ không được kiểm chứng vào nhiều `if` | Khó bảo trì và dễ lỗi khi mở rộng ngôn ngữ | Tập trung rules/mẫu và có kiểm định chuyên môn |

## 13. Kiểm thử đúng giới hạn, không chỉ kiểm thử format

Một kế hoạch kiểm thử cho hệ bản địa hóa có số nhiều/ngữ pháp nên bao gồm:

- **Theo locale:** test mỗi ngôn ngữ thật sự hỗ trợ, không chỉ `Locale.US`.
- **Theo category:** test đại diện từng plural category có thể xuất hiện ở locale đó.
- **Theo loại số:** `0`, `1`, `2`, `5`, `11`, `21`, `22`, `101`, phân số và số thập phân nếu nghiệp vụ cho phép.
- **Theo ngữ cảnh:** cardinal, ordinal, giống/case/agreement nếu có.
- **Theo dữ liệu tài nguyên:** thiếu nhánh, thiếu key, sai placeholder, sai số lượng tham số, lỗi escaping và thay đổi sau cập nhật bản dịch.
- **Theo độ ổn định:** thay đổi locale mặc định JVM không được âm thầm thay quyết định nghiệp vụ; thay phiên bản ICU/CLDR cần kiểm tra kết quả có chủ đích.
- **Theo kết quả cuối:** test không chỉ category mà cả câu sau khi chèn số và các đối số, được duyệt bởi người biết ngôn ngữ.

Ví dụ bảng kiểm thử giới hạn cho hàm minh họa tiếng Nga **chỉ nhận số nguyên không âm** trong mục 7:

| Input | Category mong đợi | Giải thích |
| ---: | --- | --- |
| 0 | `many` | Trường hợp 0 trong tập số nguyên được minh họa |
| 1 | `one` | Hàng đơn vị 1, không thuộc 11 |
| 2 | `few` | Hàng đơn vị 2, không thuộc 12 |
| 5 | `many` | Không thuộc các nhánh one/few |
| 11 | `many` | Ngoại lệ 11 |
| 12 | `many` | Ngoại lệ 12 |
| 14 | `many` | Ngoại lệ 14 |
| 21 | `one` | Hai chữ số cuối 21 |
| 22 | `few` | Hai chữ số cuối 22 |
| 101 | `one` | Hai chữ số cuối 01 |

**Không mở rộng kết luận này sang thập phân**. Trong CLDR, số 1 và cách biểu diễn như `1.0` có thể tác động tới operands hoặc quy tắc plural tùy ngôn ngữ và API. Cần quyết định mô hình dữ liệu số và formatter của thư viện trước khi đặt kỳ vọng.

## 14. Bài tập tự đánh giá

**Câu 1.** Một hệ thống chỉ có tiếng Việt và tiếng Anh, chỉ hiển thị nhãn tĩnh và một con số được định dạng theo locale. Có bắt buộc dùng ICU4J không?

**Đáp án:** Không. Nếu không có yêu cầu ngữ pháp phức tạp, `ResourceBundle` và `NumberFormat` có thể đủ. Quyết định dựa vào yêu cầu, không dựa vào việc có bao nhiêu thư viện.

**Câu 2.** Một sản phẩm muốn hỗ trợ tiếng Nga, tiếng Ba Lan, tiếng Ả Rập, có số đếm nguyên và thập phân. Chỉ dùng `ChoiceFormat` có được xem là hỗ trợ plural đúng không?

**Đáp án:** Không thể kết luận như vậy. `ChoiceFormat` không tự áp dụng quy tắc CLDR cho từng ngôn ngữ và loại số. Cần chọn quy tắc/engine phù hợp, kiểm tra cách biểu diễn số và kiểm thử từng category.

**Câu 3.** Vì sao `Locale.forLanguageTag("ru-RU")` không tự làm thông điệp trở thành tiếng Nga đúng ngữ pháp?

**Đáp án:** `Locale` chỉ mô tả ngữ cảnh ngôn ngữ; bản dịch, quy tắc plural và biến tố vẫn cần dữ liệu và logic phù hợp.

**Câu 4.** Có thể truyền `"{count, plural, one{...} other{...}}"` vào `java.text.MessageFormat` Java 17 không?

**Đáp án:** Không. Đó là dạng pattern ICU, không phải cú pháp plural của `java.text.MessageFormat` Java 17; cần formatter hỗ trợ ICU pattern hoặc chọn thiết kế khác.

**Câu 5.** Vì sao biến `gender` trong một mẫu câu không nên mặc định là dữ liệu giới tính người dùng?

**Đáp án:** Giống ngữ pháp có thể là thuộc tính của danh từ/đối tượng trong câu, độc lập với giới tính con người. Chỉ thu thập và sử dụng dữ liệu thật sự cần cho nghiệp vụ và đúng ngữ cảnh.

**Bài thực hành.** Viết tài liệu yêu cầu cho thông điệp “{count} mục đã được xử lý bởi {actor}” với ba locale và tùy chọn hiển thị thứ hạng. Chỉ ra phần nào được `NumberFormat` xử lý, phần nào cần plural/ordinal/select và phần nào phải được người dịch xác nhận. Xây bảng kiểm thử có cả 0, 1, 2, 11, 21 và một số thập phân. Sau đó đánh giá liệu Java Core có đủ hay cần một engine ngữ pháp khác, nêu lý do từng quyết định.

## 15. Tài liệu tham khảo

- [Java SE 17 — MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html): cú pháp của `java.text.MessageFormat`, các kiểu format và `choice`.
- [Java SE 17 — ChoiceFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ChoiceFormat.html): lựa chọn theo dải số và giới hạn của pattern.
- [Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html): lưu thông điệp theo locale, không phải bộ máy ngữ pháp.
- [Unicode CLDR — Language Plural Rules](https://cldr.unicode.org/index/cldr-spec/plural-rules): quy tắc plural theo ngôn ngữ và nguyên tắc phân nhóm.
- [ICU User Guide — Formatting Messages](https://unicode-org.github.io/icu/userguide/format_parse/messages/): các khái niệm plural/select trong hệ sinh thái ICU.

**Kết luận:** Java Core làm tốt việc **chọn locale, tìm tài nguyên, định dạng dữ liệu và chèn đối số**. Khi yêu cầu đòi hỏi **plural/ordinal chuẩn theo locale, chọn giống, agreement, case hoặc điều kiện ngữ pháp lồng nhau**, hãy nhận diện đây là một bài toán **ngôn ngữ học có quy tắc**, đánh giá một formatter/library phù hợp và xây kiểm thử với bản dịch được duyệt. Không mặc định một vài nhánh `if` hoặc `ChoiceFormat` đã giải quyết đúng mọi ngôn ngữ.
