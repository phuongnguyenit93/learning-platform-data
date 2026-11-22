# Kiểm thử khóa tài nguyên và tham số mẫu giữa các bản dịch

Ứng dụng Java có thể chạy ổn với `ResourceBundle` tiếng Anh nhưng lỗi khi người dùng đổi sang tiếng Việt, Pháp hoặc Nhật. Một khóa bị gõ sai, một placeholder `{0}` bị đổi thành `{1}`, hoặc một thông điệp dùng `{0,date}` thay cho `{0,number}` đều có thể làm UI hiển thị sai — đôi khi không ném ngoại lệ. Do đó, **kiểm thử nội dung localization là một phần của hợp đồng giữa code và người dịch**.

Bài học tập trung vào ba mục tiêu: **tập khóa giữa các bản dịch**, **tập chỉ số/thông tin kiểu tham số trong `MessageFormat`**, và **kiểm chứng trên đường chạy thực tế**. Các ví dụ Java 17+ sử dụng `.properties`, `PropertyResourceBundle`, `MessageFormat` và một chương trình kiểm thử không cần thư viện ngoài.

Điều cần nhớ từ đầu: **`ResourceBundle` có cơ chế fallback**, nên việc `getString` thành công không chứng minh file locale được dịch đầy đủ. Đồng thời **`MessageFormat` dùng ngữ pháp riêng cho dấu nháy đơn, ngoặc nhọn và nested `choice`**, vì vậy một regex tìm `{số}` không phải bộ phân tích pattern tổng quát.

## 1. Một bộ bundle và hợp đồng cần giữ

Giả sử dự án có hai tệp:

**`Messages_en.properties`**

~~~properties
welcome=Hello {0}!
items={0} has {1,number,integer} items.
created=Created on {0,date,medium}.
~~~

**`Messages_vi.properties`**

~~~properties
welcome=Xin chào {0}!
items={0} có {1,number,integer} mặt hàng.
created=Được tạo ngày {0,date,medium}.
~~~

Các tệp có **ba key giống nhau**, nhưng văn bản và trật tự từ có thể khác. Hợp đồng của từng thông điệp gồm:

| Key | Đối số bắt buộc | Kiểu/ý nghĩa |
| --- | --- | --- |
| `welcome` | `{0}` | Tên người |
| `items` | `{0}` và `{1}` | Tên người và số lượng |
| `created` | `{0}` | Ngày tạo, dùng định dạng ngày |

Không cần hai bản dịch dùng cùng vị trí placeholder trong câu. Ví dụ câu dịch có thể đặt `{1}` trước `{0}` để đúng ngữ pháp, miễn giữ cùng **hợp đồng đối số**.

Kiểm thử đáng tin cần kiểm tra cả **đầy đủ key**, **đối số** và **định dạng thực tế**, không chỉ mở file xem bằng mắt.

## 2. Vì sao fallback dễ che một key bị thiếu?

Nếu dự án có:

~~~text
Messages.properties
Messages_en.properties
Messages_vi.properties
~~~

và `Messages_vi.properties` thiếu `created` nhưng `Messages.properties` vẫn có key đó, `ResourceBundle.getBundle("Messages", locale)` có thể trả giá trị từ bundle cha/root.

Chương trình:

~~~java
ResourceBundle vi = ResourceBundle.getBundle(
        "Messages", Locale.forLanguageTag("vi-VN"));

String text = vi.getString("created");
~~~

có thể vẫn chạy, nhưng `text` là câu mặc định chưa được dịch.

**`ResourceBundle.keySet()` bao gồm những key có thể truy xuất từ parent**, không chỉ key khai báo tại file hiện tại. Vì vậy `en.keySet().equals(vi.keySet())` trên các bundle đã qua fallback **không chứng minh** các file gốc có cùng tập khóa.

Giải pháp: đối với bài kiểm thử **parity của nguồn**, hãy nạp **từng file bản dịch độc lập**, không dùng `getBundle` có fallback. Sau đó có thêm test runtime để kiểm tra đường tìm tài nguyên thực tế.

## 3. Kiểm thử raw keys bằng `PropertyResourceBundle(Reader)`

Có thể đọc trực tiếp file UTF-8:

~~~java
try (Reader reader = Files.newBufferedReader(
        Path.of("Messages_vi.properties"),
        StandardCharsets.UTF_8)) {

    ResourceBundle bundle = new PropertyResourceBundle(reader);
    Set<String> keys = bundle.keySet();
}
~~~

Đây là **snippet** trong method có `throws IOException`, cần import `Reader`, `Files`, `Path`, `StandardCharsets`, `ResourceBundle`, `PropertyResourceBundle` và `Set`.

Đối tượng mới tạo từ file trực tiếp không được thuật toán `ResourceBundle.getBundle` gán parent locale, nên `keySet` phản ánh nội dung file đó.

Lưu ý encoding: `Properties.load(InputStream)` có quy tắc ISO-8859-1 truyền thống, trong khi `Reader` cho phép chọn UTF-8 tường minh. Hãy dùng đúng đường đọc phù hợp build và nội dung thật.

## 4. Chính sách kiểm thử exact parity hay có ngoại lệ

Có hai lựa chọn:

**Exact parity:** mọi locale đã phát hành phải có tập key bằng canonical.

~~~text
keys(en) = keys(vi) = keys(fr)
~~~

**Partial coverage được kiểm soát:** locale thử nghiệm có thể chỉ có một tập con.

~~~text
requiredKeys ⊆ keys(locale)
exceptions(locale) có chủ sở hữu và lý do rõ ràng
~~~

Với locale dạng vùng `fr_CA`, dự án có thể chủ động chỉ lưu những key **override** so với `fr`; exact parity áp lên riêng file `fr_CA` khi đó là chính sách sai. Kiểm thử phải nhận biết **layer bản dịch** và chính sách fallback được phê duyệt.

Dù chọn cách nào, hãy báo cụ thể:
- **Missing key**: canonical có, locale thiếu.
- **Extra key**: locale có, canonical không có.
- **Empty value**: key có nhưng value trống/không đạt chính sách.
- **Duplicate key**: nhiều lần khai báo cùng key.
- **Stale key**: không còn nơi nào trong code cần key.

Tập key sau parse **không phát hiện duplicate declarations** nếu parser chỉ giữ giá trị cuối. Muốn cấm duplicate, cần linter nguồn biết dấu continuation, escapes và cấu trúc `.properties`.

## 5. Các placeholder của `MessageFormat`

`java.text.MessageFormat` dùng **đối số có index**:

~~~text
{0}
{1,number,integer}
{2,date,medium}
{3,time,short}
{0,choice,0#none|1#one|1<many}
~~~

Ví dụ runnable **`MessageArgumentsDemo.java`**:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageArgumentsDemo {
    public static void main(String[] args) {
        MessageFormat format = new MessageFormat(
                "Hello {0}, you have {1,number,integer} files.",
                Locale.US);

        System.out.println(format.format(
                new Object[]{"Lan", 5}));
    }
}
~~~

~~~bash
javac MessageArgumentsDemo.java
java MessageArgumentsDemo
~~~

Kết quả:

~~~text
Hello Lan, you have 5 files.
~~~

`{0}` lấy đối số đầu tiên và `{1}` lấy đối số thứ hai. **Một bản dịch có quyền sắp xếp lại trật tự xuất hiện**, nhưng không nên tự ý gắn nghĩa `{0}` cho số lượng nếu code đang truyền tên vào đó.

## 6. Thiếu đối số không nhất thiết báo lỗi

Ví dụ:

~~~java
MessageFormat f = new MessageFormat(
        "Hi {0} {1,number}", Locale.US);

System.out.println(
        f.format(new Object[]{"Lan"}));
~~~

Kết quả:

~~~text
Hi Lan {1}
~~~

Java có thể để **placeholder chưa có đối số** nguyên dạng `{1}`, không nhất thiết ném exception. Nếu test chỉ format rồi không kiểm output hoặc tập chỉ số, lỗi có thể lọt đến UI.

Vì vậy cần **đối chiếu các index được dùng với chữ ký hàm/fixture**. Đối số index cao như `{7}` có thể được người dịch vô tình thêm dù ứng dụng chỉ truyền hai đối số.

## 7. Không nên so thứ tự hoặc số lần xuất hiện

Hai bản:

~~~text
English: {0} sent {1,number} messages.
Other:   {1,number} messages were sent by {0}.
~~~

có cùng **tập index `{0,1}`**, nên về mặt vị trí đối số chúng tương thích. Một bản khác có thể nhắc lại `{0}` hai lần theo ngữ pháp. Đừng coi lặp index là lỗi mặc định.

Nên kiểm tra:
1. Tập index được dùng.
2. Vai trò dữ liệu ở từng index.
3. Các định dạng tương thích với kiểu đối số.
4. Các yêu cầu riêng như plural hoặc giới tính.

Không dùng phép so sánh nguyên chuỗi hai locale để kiểm tra sự tương thích.

## 8. Cùng index nhưng sai formatter type

Ví dụ:

~~~text
en: Created on {0,date,medium}.
vi: Được tạo ngày {0,number,integer}.
~~~

Hai bên dùng cùng index `0`, nhưng khác formatter. Nếu `{0}` nhận `Date`, bản tiếng Việt có thể lỗi khi format số; nếu nhận `Number`, bản tiếng Anh có thể lỗi.

**Kiểm tra index parity là điều kiện cần, không phải đủ.** Test cần có **fixture đúng kiểu dữ liệu thực sự** và — khi yêu cầu nghiệp vụ rõ — kiểm tra `number`/`date`/`time`/`choice` của từng key.

Ví dụ runnable **`FormatTypeDemo.java`**:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class FormatTypeDemo {
    public static void main(String[] args) {
        MessageFormat number = new MessageFormat(
                "{0,number,integer}", Locale.US);

        System.out.println(number.format(new Object[]{5}));

        try {
            number.format(new Object[]{"five"});
        } catch (IllegalArgumentException ex) {
            System.out.println("Wrong argument type");
        }
    }
}
~~~

~~~bash
javac FormatTypeDemo.java
java FormatTypeDemo
~~~

Kết quả:

~~~text
5
Wrong argument type
~~~

Không dùng một `String "X"` làm fixture cho mọi parameter: điều đó tạo lỗi giả ở pattern `number`/`date` hoàn toàn hợp lệ.

## 9. Quote của `MessageFormat` rất dễ bị linter hiểu sai

Trong `MessageFormat`, dấu nháy đơn `'` có vai trò **quote literal**. Hai dấu `''` tạo một apostrophe thật.

| Pattern | Khi đối số `{0} = "ready"` |
| --- | --- |
| `It''s {0}` | `It's ready` |
| `'{0}'` | `{0}` (literal) |
| `''{0}''` | `'ready'` |

Ví dụ runnable **`QuotedArgumentsDemo.java`**:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class QuotedArgumentsDemo {
    public static void main(String[] args) {
        Object[] data = {"ready"};

        System.out.println(
                new MessageFormat("It''s {0}", Locale.US)
                        .format(data));
        System.out.println(
                new MessageFormat("'{0}'", Locale.US)
                        .format(data));
        System.out.println(
                new MessageFormat("''{0}''", Locale.US)
                        .format(data));
    }
}
~~~

~~~bash
javac QuotedArgumentsDemo.java
java QuotedArgumentsDemo
~~~

Kết quả:

~~~text
It's ready
{0}
'ready'
~~~

Một regex quét mọi `{0}` có thể đếm cả placeholder literal trong `'{0}'`, gây false positive. Ngược lại, apostrophe sai có thể làm placeholder đáng lẽ được format biến thành literal. Khi kiểm thử cần hiểu cú pháp quote của parser thật.

## 10. Pattern syntax và lỗi thời điểm parse

`new MessageFormat(pattern, locale)` phân tích cú pháp. Pattern bị thiếu ngoặc, format type không hợp lệ hoặc chỉ số không đúng có thể ném `IllegalArgumentException`.

Một kiểm thử phù hợp:

~~~java
try {
    new MessageFormat(pattern, locale);
} catch (IllegalArgumentException ex) {
    throw new AssertionError(
            "Invalid pattern: locale=" + locale
                    + ", key=" + key, ex);
}
~~~

Đây là **snippet trong method** với biến `pattern`, `locale` và `key` đã có.

**Parse thành công không chứng minh mọi thứ đúng**: parser không biết hợp đồng code yêu cầu `{0}` là tên, `{1}` là số, bản dịch đã dùng thiếu index hay không, hoặc câu đã đúng nghĩa.

## 11. `getFormatsByArgumentIndex` không phải bộ liệt kê index hoàn chỉnh

`MessageFormat.getFormatsByArgumentIndex()` trả mảng `Format[]` được sắp theo index, có thể dùng để quan sát thông tin format. Nhưng với pattern:

~~~text
{2} and {0}
~~~

mảng có thể dài **3** do index lớn nhất bằng 2, trong khi `{1}` **không xuất hiện**. Các entry `null` có thể tương ứng tham số không khai báo formatter, không đủ để phân biệt tất cả trường hợp.

Nếu có nested `choice`, formatter outer còn không phản ánh toàn bộ tham số dùng trong các nhánh được parse lại.

Do đó **không lấy độ dài mảng để khẳng định số tham số cần**, và không mặc định regex sẽ giải quyết đủ mọi cú pháp MessageFormat.

## 12. Bộ test Java 17+ cho file properties và pattern phẳng

Chương trình sau đủ để dùng làm điểm khởi đầu trong dự án có **pattern phẳng**. Nó:
- nạp `Messages_en.properties` và `Messages_vi.properties` độc lập bằng UTF-8;
- so sánh exact key sets;
- dùng `MessageFormat` phân tích syntax;
- quét các placeholder top-level với quy tắc apostrophe;
- so sánh set index;
- format các fixture đúng kiểu;
- dừng bằng `AssertionError` nếu phát hiện vấn đề.

**Giới hạn của scanner:** nó cố tình từ chối `{...}` lồng bên trong format element, bao gồm nested `choice`. Nó không là parser đầy đủ của grammar MessageFormat; dự án dùng pattern phức tạp phải sử dụng parser chuyên dụng hoặc test các nhánh có kiểm soát.

Tạo **`BundleContractTest.java`**:

~~~java
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.text.MessageFormat;
import java.util.Date;
import java.util.Locale;
import java.util.Map;
import java.util.PropertyResourceBundle;
import java.util.ResourceBundle;
import java.util.Set;
import java.util.SortedSet;
import java.util.TreeSet;

public final class BundleContractTest {
    private static ResourceBundle read(String name)
            throws Exception {
        try (Reader r = Files.newBufferedReader(
                Path.of(name), StandardCharsets.UTF_8)) {
            return new PropertyResourceBundle(r);
        }
    }

    // Chỉ dùng cho pattern phẳng, không nested choice.
    private static Set<Integer> indexes(String pattern) {
        new MessageFormat(pattern, Locale.ROOT);

        SortedSet<Integer> result = new TreeSet<>();
        boolean quoted = false;

        for (int i = 0; i < pattern.length();) {
            char ch = pattern.charAt(i);

            if (ch == '\'') {
                if (i + 1 < pattern.length()
                        && pattern.charAt(i + 1) == '\'') {
                    i += 2;
                } else {
                    quoted = !quoted;
                    i++;
                }
                continue;
            }

            if (!quoted && ch == '{') {
                int start = i + 1;
                int p = start;
                while (p < pattern.length()
                        && pattern.charAt(p) >= '0'
                        && pattern.charAt(p) <= '9') {
                    p++;
                }

                if (start == p || p == pattern.length()
                        || (pattern.charAt(p) != '}'
                            && pattern.charAt(p) != ',')) {
                    throw new IllegalArgumentException(
                            "Bad placeholder at " + i);
                }

                result.add(Integer.parseInt(
                        pattern.substring(start, p)));

                if (pattern.charAt(p) == '}') {
                    i = p + 1;
                    continue;
                }

                ++p;
                while (p < pattern.length()
                        && pattern.charAt(p) != '}') {
                    if (pattern.charAt(p) == '{') {
                        throw new IllegalArgumentException(
                                "Unsupported nested pattern");
                    }
                    p++;
                }

                if (p == pattern.length()) {
                    throw new IllegalArgumentException(
                            "Unclosed placeholder");
                }
                i = p + 1;
            } else {
                i++;
            }
        }

        return result;
    }

    public static void main(String[] args) throws Exception {
        ResourceBundle en = read("Messages_en.properties");
        ResourceBundle vi = read("Messages_vi.properties");

        SortedSet<String> a = new TreeSet<>(en.keySet());
        SortedSet<String> b = new TreeSet<>(vi.keySet());

        if (!a.equals(b)) {
            SortedSet<String> missing = new TreeSet<>(a);
            missing.removeAll(b);
            SortedSet<String> extra = new TreeSet<>(b);
            extra.removeAll(a);
            throw new AssertionError(
                    "vi missing=" + missing + ", extra=" + extra);
        }

        Map<String, Object[]> fixture = Map.of(
                "welcome", new Object[]{"Lan"},
                "items", new Object[]{"Lan", 5},
                "created", new Object[]{new Date(0)}
        );

        for (String key : a) {
            String enPattern = en.getString(key);
            String viPattern = vi.getString(key);
            Set<Integer> enIndexes = indexes(enPattern);
            Set<Integer> viIndexes = indexes(viPattern);

            if (!enIndexes.equals(viIndexes)) {
                throw new AssertionError(
                        key + ": " + enIndexes
                            + " != " + viIndexes);
            }

            Object[] values = fixture.get(key);
            if (values == null) {
                throw new AssertionError(
                        "No fixture for " + key);
            }

            for (int index : enIndexes) {
                if (index >= values.length) {
                    throw new AssertionError(
                            key + ": missing argument " + index);
                }
            }

            new MessageFormat(enPattern, Locale.US)
                    .format(values);
            new MessageFormat(
                    viPattern, Locale.forLanguageTag("vi-VN"))
                    .format(values);
        }

        System.out.printf("PASS keys=%d patterns=%d%n",
                a.size(), 2 * a.size());
    }
}
~~~

Trong thư mục chứa ba tệp, dùng:

~~~bash
javac -encoding UTF-8 BundleContractTest.java
java BundleContractTest
~~~

Với hai file properties ở phần 1:

~~~text
PASS keys=3 patterns=6
~~~

**Phạm vi kiểm tra rõ ràng:** chương trình kiểm tra syntax, index và việc format fixture mẫu, **không** kiểm tra đầy đủ mọi kiểu format, cú pháp lồng nhau hoặc tính đúng của câu dịch. Nếu một bản thay `{0,date}` thành `{0}`, cả hai có thể format thành công, nhưng điều đó vẫn cần review bằng quy tắc về định dạng ngày.

## 13. Minh họa lỗi mà test phát hiện

Đổi từng trường hợp trong `Messages_vi.properties`:

**Thiếu khóa:**

~~~properties
welcome=Xin chào {0}!
items={0} có {1,number,integer} mặt hàng.
~~~

Test báo thiếu `created`. Lưu ý đó là kiểm tra file thô, không có fallback.

**Sai index:**

~~~properties
items={0} có {2,number,integer} mặt hàng.
~~~

Test có thể báo:

~~~text
items: [0, 1] != [0, 2]
~~~

**Sai kiểu tại runtime:**

~~~properties
items={0} có {1,date,medium} mặt hàng.
~~~

Index giống nhau nhưng fixture truyền `5` (Number) vào date formatter; có thể phát sinh `IllegalArgumentException`.

**Lỗi không được scanner hỗ trợ:**

~~~properties
items={1,choice,0#không có|1#có một|1<có {1} mục}
~~~

Scanner từ chối nested brace. Đây là hành vi **fail-closed**, không phải chứng minh bản dịch sai: dự án cần kiểm tra pattern bằng công cụ thích hợp với cú pháp choice.

## 14. ChoiceFormat và pattern lồng nhau

`MessageFormat` cho phép:

~~~text
{0,choice,0#no files|1#one file|1<{0,number,integer} files}
~~~

Nhánh của `ChoiceFormat` có thể được parse thêm nếu chứa ngoặc nhọn MessageFormat. Do vậy, placeholder trong nhánh **không hẳn** được tìm qua một lượt quét top-level đơn giản.

Ví dụ **`ChoiceBranchesDemo.java`**:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class ChoiceBranchesDemo {
    public static void main(String[] args) {
        MessageFormat format = new MessageFormat(
                "{0,choice,0#no files|1#one file"
                        + "|1<{0,number,integer} files}",
                Locale.US);

        System.out.println(format.format(new Object[]{0}));
        System.out.println(format.format(new Object[]{1}));
        System.out.println(format.format(new Object[]{5}));
    }
}
~~~

~~~bash
javac ChoiceBranchesDemo.java
java ChoiceBranchesDemo
~~~

Kết quả:

~~~text
no files
one file
5 files
~~~

Muốn kiểm thử pattern choice, cần dữ liệu tại **các ranh giới** (0, 1, 2, số lớn), kiểm tra **mọi nhánh có thể chọn** và đối số lồng. Một bản dịch có thể dùng số nhánh khác do ngữ pháp; đó không nhất thiết là sai index, nhưng cần đánh giá ngữ nghĩa.

Với plural phức tạp theo các ngôn ngữ có nhiều loại số lượng, `ChoiceFormat` không tự đại diện đầy đủ quy tắc CLDR. Có thể dùng ICU MessageFormat/plural, nhưng **cú pháp ICU khác `java.text.MessageFormat`**; chọn parser và test đúng format thật của sản phẩm.

## 15. Regex đơn giản chỉ phù hợp cho quy ước đơn giản

Regex:

~~~java
Pattern.compile("\\{(\\d+)\\}");
~~~

chỉ nhìn ra các placeholder không có format type, dễ bỏ sót `{1,number}`, `{2,date,medium}` và `choice`.

Regex rộng hơn để tìm mọi `{số` vẫn có thể:
- đếm nhầm placeholder literal `'{0}'`;
- không phân biệt nested syntax;
- xử lý sai apostrophe;
- không phát hiện ngoặc nhọn không cân bằng hoặc chỉ số ngoài giới hạn;
- không biết kiểu dữ liệu thực của một arg.

**Không nên “fix” bằng cách tăng dần độ phức tạp regex và xem đó là parser đầy đủ.** Nếu dự án chuẩn hóa một subset pattern, scanner có thể kiểm tra subset và từ chối phần còn lại; với đầy đủ cú pháp phải dùng parser tương ứng hoặc thư viện được kiểm thử.

## 16. Kiểm tra type contract và fixture có chủ đích

Với các thông điệp nghiệp vụ, nên có một registry khai báo:

~~~text
welcome  → {0: String name}
items    → {0: String name, 1: Number count}
created  → {0: Date createdAt}
price    → {0: Number amount, currency policy riêng}
~~~

Đó là mô tả hợp đồng, không phải cú pháp `MessageFormat`.

Kiểm thử động:
1. Truyền `String` cho tên.
2. Truyền `Integer`/`BigDecimal` khi formatter yêu cầu `number`.
3. Truyền `java.util.Date` hoặc kiểu được adapter của ứng dụng hỗ trợ cho `date/time` chuẩn.
4. Với `choice`, truyền `Number` và chạy nhiều giá trị biên.
5. Kiểm tra độ dài mảng args đủ cho **max index thực sự dùng**.
6. Kiểm tra output không để lộ placeholder bị thiếu, nhưng nhớ rằng một literal `'{0}'` hợp lệ cũng có thể tạo chuỗi `{0}` — không được kết luận bằng string search đơn lẻ.

Không dùng một mảng fixture cố định cho mọi key nếu hợp đồng tham số của chúng khác nhau.

## 17. Kiểm thử bản dịch theo locale nhưng không so chuỗi literal

`MessageFormat` tạo đối tượng formatter theo `Locale`. Ví dụ số có dấu phân cách khác giữa `Locale.US` và `Locale.GERMANY`; ngày/tháng cũng có thứ tự khác.

Kiểm thử đúng:
- Truyền **locale tương ứng**.
- Xác nhận formatter chạy với kiểu đối số đúng.
- Kiểm các thành phần nghiệp vụ quan trọng có mặt.
- Dùng snapshot chỉ khi cố định JDK/CLDR/provider và hiểu khác biệt Unicode whitespace.
- Không yêu cầu output giữa các locale phải giống chuỗi.

Nếu formatter date/time dùng `Date` và timezone mặc định, snapshot có thể thay đổi theo máy. Cần cố định timezone cho test có ngày giờ hoặc kiểm tra thuộc tính không phụ thuộc timezone khi chỉ muốn test độ tương thích.

## 18. Empty values, duplicate keys và encoding

Tập key giống nhau vẫn không bảo đảm chất lượng:

- `welcome=` có thể là **empty value** không hợp lệ cho một màn hình, dù key tồn tại.
- Một key khai báo hai lần có thể bị map parser ghi đè; `keySet` không báo duplicate.
- `.properties` có line continuation và `\uXXXX` escape; linter dòng đơn giản cần hiểu cú pháp ấy.
- Dữ liệu UTF-8 không hợp lệ có thể bị thay ký tự nếu API decoder dùng replacement.
- Giá trị có newline hoặc HTML markup cần validation theo ngữ cảnh hiển thị.
- String có NFC/NFD khác nhau không phải lỗi key parity, nhưng có thể ảnh hưởng tìm kiếm/so sánh.

Tách kiểm tra **source syntax/encoding** khỏi **MessageFormat syntax**: một file được đọc đúng chưa chắc pattern hợp lệ; một pattern hợp lệ chưa chắc bản dịch được trình bày đúng.

## 19. Không chỉ parity: kiểm tra key đang được code dùng

Một số key có trong mọi file nhưng không còn nơi nào sử dụng. Ngược lại, code có thể gọi một key chưa tồn tại.

Có thể tạo registry key dạng enum:

~~~java
enum MessageKey {
    WELCOME("welcome"),
    ITEMS("items"),
    CREATED("created");

    final String value;
    MessageKey(String value) {
        this.value = value;
    }
}
~~~

Đây là **snippet enum**, không có `main`. Registry làm giảm typo, nhưng không tự biến `ResourceBundle` thành type-safe.

Nếu project tạo key động, ví dụ `"status." + status.name()`, một công cụ tìm text thuần có thể bỏ sót. Hãy test các tổ hợp value hoặc tạo registry cho những key được xây động.

## 20. Named module và integration tests

Java 9+ hỗ trợ named modules và đóng gói tài nguyên theo JPMS. Unit test nạp file trực tiếp không chứng minh rằng file `.properties` đã được copy đúng vào JAR hoặc ứng dụng production có thể tải nó.

Nên có integration test:
- chạy trên module path như môi trường triển khai;
- kiểm tra các locale quan trọng;
- xác nhận `ResourceBundle.getBundle` tìm được bundle;
- xác nhận fallback/parent đúng chính sách;
- xác nhận key có giá trị runtime như mong muốn.

Các overload `ResourceBundle.getBundle(..., Control)` không được hỗ trợ khi gọi từ named module; đừng dùng chúng như một cách mặc định để “tắt fallback” trong integration test modular. Để kiểm tra parity của file nguồn, đọc raw files như ở trên; để kiểm tra runtime, dùng API/module/provider phù hợp.

## 21. Ma trận thử nghiệm cần có

| Trường hợp | Cách kiểm tra | Kỳ vọng |
| --- | --- | --- |
| Key thiếu | Xóa `created` khỏi vi | Báo missing |
| Key thừa | Thêm `unknown` | Báo extra |
| Index đảo thứ tự | `{1}` trước `{0}` | Hợp lệ nếu vai trò giữ nguyên |
| Index thiếu | Bỏ `{1}` | Phát hiện sai lệch |
| Index lạ | Đổi `{1}` → `{2}` | Phát hiện sai lệch |
| Literal quote | `'{0}'` | Không đếm là arg thật |
| Apostrophe | `It''s {0}` | Hiển thị apostrophe đúng |
| Sai kiểu number | Truyền String vào number format | Báo lỗi |
| Nested choice | 0, 1, 2, 5 | Mỗi nhánh hoạt động |
| Date/time | Fixture thích hợp | Format không lỗi |
| Fallback | Key chỉ tồn tại ở root | Báo coverage thiếu trong locale |
| Duplicate key | Hai khai báo cùng key | Source linter cảnh báo |
| Encoding | Vietnamese UTF-8 | Không mojibake |
| Module packaging | Runtime module path | Tải bundle thành công |
| Empty value | `key=` | Theo policy lỗi/cho phép |

## 22. CI pipeline và báo cáo lỗi

Một pipeline hợp lý:

~~~text
Pull request thay bản dịch
    ↓
Đọc raw resource + xác thực UTF-8
    ↓
Kiểm duplicate/empty/key naming
    ↓
So sánh tập key theo chính sách
    ↓
Parse MessageFormat
    ↓
So sánh placeholder indexes/types
    ↓
Format fixtures và các nhánh choice
    ↓
Integration test ResourceBundle runtime
    ↓
Review văn bản dịch/UI khi cần
~~~

Đối với locale bắt buộc, thiếu key hoặc sai index nên **fail CI**. Với locale preview, có thể cảnh báo theo ngoại lệ có thời hạn. Một thông báo đủ rõ:

~~~text
locale=vi key=items
reason=ARGUMENT_INDEX_MISMATCH
expected=[0, 1]
actual=[0, 2]
~~~

Điều này hữu ích hơn báo `IllegalArgumentException` không có ngữ cảnh. Tránh log dữ liệu nhạy cảm từ fixture hoặc nội dung người dùng thật.

## 23. Sai lầm phổ biến

1. **Chỉ thử `getString`**: fallback có thể che key thiếu.
2. **So sánh `ResourceBundle.keySet` sau khi có parent**: key thừa từ parent làm kiểm tra không chính xác.
3. **Chỉ kiểm số placeholder**: `{1}` và `{2}` khác nghĩa dù cùng số lượng.
4. **So thứ tự placeholder**: có thể đánh lỗi một bản dịch đảo trật tự câu hợp lệ.
5. **Bỏ type checking**: index giống nhau chưa chắc format number/date đúng.
6. **Dùng regex vạn năng**: quote, typed format, nested choice gây sai.
7. **Tin constructor `MessageFormat` chứng minh đủ đối số**: không có dữ liệu thực thì chưa kiểm được.
8. **Không test giới hạn plural/choice**: chỉ một giá trị mẫu không đủ.
9. **Dùng cùng chuỗi đầu ra để so các locale**: quy ước số/ngày khác nhau.
10. **Để test dùng default charset/locale bất định**: có thể khác môi trường.
11. **Quên test resource sau build**: resource có trên source tree nhưng thiếu trong JAR.
12. **Tự động “sửa” câu dịch theo regex**: có thể phá ngữ pháp.
13. **Không công bố chính sách exact/partial coverage**: cảnh báo sai hoặc bỏ sót bản dịch chưa hoàn tất.
14. **Không review nghĩa của câu**: parity kỹ thuật không đảm bảo chất lượng ngôn ngữ.

## 24. Bài tập tự kiểm tra

**Câu 1.** Vì sao `getString("created")` thành công không chứng minh `Messages_vi.properties` có key `created`?

**Đáp án:** Giá trị có thể được lấy từ bundle cha/root qua fallback.

**Câu 2.** Bản Anh có `{0} {1}`, bản Việt có `{1} {0}`. Có phải lỗi không?

**Đáp án:** Không nhất thiết; thứ tự xuất hiện có thể thay đổi, miễn giữ cùng vai trò đối số.

**Câu 3.** Hai bản đều dùng `{0}` nhưng một bên là `number`, bên kia là `date`. Kiểm tra index có đủ không?

**Đáp án:** Không, cần kiểm tra kiểu định dạng và chạy fixture đúng loại.

**Câu 4.** Pattern `'{0}'` có thực sự cần arg `0` không?

**Đáp án:** Không. Trong `MessageFormat`, dấu nháy quote biến đoạn đó thành literal.

**Câu 5.** `MessageFormat` có luôn ném exception khi thiếu arg `{1}` không?

**Đáp án:** Không; nó có thể hiển thị `{1}` nguyên dạng.

**Câu 6.** Vì sao bộ scanner trong ví dụ từ chối nested `choice`?

**Đáp án:** Vì nó chỉ triển khai grammar phẳng; từ chối cú pháp ngoài phạm vi an toàn hơn báo PASS giả.

**Câu 7.** Có thể khẳng định ngữ pháp plural đúng bằng key/index parity không?

**Đáp án:** Không; cần kiểm tra nhánh, quy tắc ngôn ngữ và có thể cần ICU/CLDR.

**Câu 8.** Khi nào exact parity không phù hợp với file `fr_CA`?

**Đáp án:** Khi file vùng chỉ chủ động chứa override và kế thừa `fr`.

**Câu 9.** Tại sao cần unit test lẫn integration test?

**Đáp án:** Unit test kiểm tra nguồn file/pattern, integration test xác nhận ResourceBundle thực sự tải được sau build/module packaging.

**Câu 10.** CI nên báo gì khi thiếu placeholder?

**Đáp án:** Locale, key, reason và tập expected/actual, không chỉ một stack trace chung chung.

## 25. Tổng kết và nguyên tắc áp dụng

1. Đặt **một canonical bundle** và chính sách coverage cho từng locale.
2. Kiểm tra **raw locale entries**, không dựa vào fallback để chứng minh bản dịch đủ key.
3. So sánh **set placeholder index**, không ép thứ tự câu hay số lần lặp.
4. Bổ sung **type/semantic contract** cho number, date, time, choice và các tham số nghiệp vụ.
5. Dùng `MessageFormat` để kiểm tra syntax và format fixture; với nested pattern, dùng parser hoặc bài test riêng theo nhánh.
6. Ghi rõ giới hạn của linter, **fail-closed** khi gặp cú pháp không hỗ trợ.
7. Test encoding, duplicate key, empty value, locale fallback, build packaging và JPMS.
8. Tích hợp vào **CI**, nhưng giữ **người review ngôn ngữ** cho plural, ngữ nghĩa và bố cục giao diện.

**Ghi nhớ:** Kiểm thử localization không chỉ là “có file dịch”. Một bộ bản dịch đáng tin phải đồng bộ **khóa tài nguyên, đối số mẫu, định dạng kiểu và hành vi runtime**. `ResourceBundle` fallback có thể che nội dung thiếu; `MessageFormat` có thể giữ placeholder khi thiếu tham số. Chỉ khi phối hợp kiểm tra tĩnh, fixture đúng kiểu, test nhánh và integration test, hệ thống mới có thể phát hiện sớm lỗi giữa các bản dịch.

**Tài liệu Java SE 17:** [ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html), [PropertyResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html), [MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html), [ChoiceFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ChoiceFormat.html).