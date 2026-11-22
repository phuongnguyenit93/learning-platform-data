# Kiểm thử regex với dấu chấm, gạch chéo, đô la và nhóm trong Java

Khi viết regex trong Java, dấu **chấm `.`**, **gạch chéo `/`**, **dấu đô la `$`** và **ngoặc nhóm `(...)`** có ý nghĩa khác nhau tùy chúng đang nằm trong **mẫu regex**, **chuỗi Java** hay **chuỗi thay thế (replacement)**. Một biểu thức có vẻ đúng đôi khi khớp cả dữ liệu sai, trích xuất nhầm nhóm hoặc tạo kết quả thay thế ngoài ý muốn.

Bài này tập trung vào cách **kiểm thử các ký hiệu đó** bằng `java.util.regex.Pattern` và `Matcher` trên Java 17+, với test âm/dương, các đoạn mã chạy được và cách đọc kết quả. Hai nguyên tắc xuyên suốt: phân biệt **cú pháp regex** với **escape trong Java String literal**; phân biệt **mẫu tìm kiếm** với **cú pháp chuỗi thay thế**.

## 1. Bản đồ ý nghĩa của bốn nhóm ký hiệu

| Ký hiệu trong **regex** | Ý nghĩa khi đứng ở vị trí thông thường | Muốn khớp ký tự thật |
| --- | --- | --- |
| `.` | Khớp một ký tự bất kỳ, ngoại trừ line terminator nếu không bật `DOTALL` | `\.` |
| `/` (forward slash) | Dấu gạch chéo xuôi thông thường; Java `Pattern` không dùng `/` để bao regex | Cứ viết `/` |
| `\` (backslash) | Dấu escape hoặc mở đầu lớp viết tắt như `\d`; hữu ích khi kiểm thử đường dẫn Windows | Regex `\\` |
| `$` | Neo vị trí cuối đầu vào/vùng, có quy tắc đặc biệt quanh kết thúc dòng | `\$` |
| `(...)` | Tạo nhóm bắt; dùng để gom và truy xuất nội dung | `\(` và `\)` nếu muốn khớp ngoặc thật |
| `(?:...)` | Nhóm **không bắt**, chỉ gom các phần | Không tạo chỉ số nhóm |
| `(?<name>...)` | Nhóm bắt có tên | Truy xuất bằng `group("name")` |

**Quan trọng:** Bảng trên nói về **mẫu regex**, không phải cách viết chuỗi Java. Trong mã nguồn Java, dấu `\` của regex phải viết thành `\\`. Ví dụ regex `\.` phải truyền vào Java bằng `"\\."`. Còn regex `/` chỉ cần Java string `"/"`.

Trong tài liệu Java, `Pattern.compile(regex)` biên dịch mẫu, `Matcher` thực hiện khớp, và `String.matches(regex)` cũng kiểm tra **toàn bộ** chuỗi. Để tránh khó hiểu khi soạn test, nên lưu rõ regex và input, rồi xác định mong muốn **toàn chuỗi** hay **đoạn con** trước khi chạy.

## 2. Dấu chấm: wildcard `.` khác dấu chấm thật `\.`

Trong regex, `.` là một **metacharacter**. Mẫu `report.txt` có nghĩa là các chữ `report`, **một ký tự bất kỳ** rồi `txt`. Vì thế nó có thể khớp cả `reportXtxt`, `report-txt` hoặc `report/txt` khi dùng `matches()`.

Để chỉ chấp nhận dấu chấm thật, escape thành `\.` trong regex và viết `"\\."` trong Java:

~~~java
Pattern.matches("report.txt",  "reportXtxt"); // true: dấu . là wildcard
Pattern.matches("report\\.txt", "report.txt"); // true: dấu chấm thật
Pattern.matches("report\\.txt", "reportXtxt"); // false
~~~

Ba dòng trên **chỉ là lời gọi minh họa** (cần import `java.util.regex.Pattern` và đặt trong phương thức Java).

Dấu `.` mặc định **không khớp line terminator** như `\n`. Cờ `Pattern.DOTALL` (hoặc `(?s)` trong regex) cho phép `.` khớp cả line terminator:

~~~java
Pattern.matches("a.b", "a\nb"); // false
Pattern.compile("a.b", Pattern.DOTALL)
       .matcher("a\nb").matches(); // true
~~~

Đừng nhầm `DOTALL` với `MULTILINE`: `DOTALL` thay đổi cách `.` khớp xuống dòng; `MULTILINE` thay đổi cách neo `^` và `$` áp dụng với các dòng.

Một biến thể viết dấu chấm thật là lớp ký tự `[.]`. Cả regex `\.` và `[.]` đều khớp một ký tự `.` theo cách đang xét. Khi muốn tách file name theo dấu chấm, cũng phải nhớ `String.split(...)` nhận **regex**:

~~~java
String[] parts = "a.b".split("\\."); // ["a", "b"]
~~~

Đây là đoạn minh họa. Viết `"a.b".split(".")` khiến regex `.` khớp các ký tự thay vì đóng vai trò dấu phân cách `.`; kết quả không phải mảng mong muốn.

### Test tối thiểu cho dấu chấm

| Regex viết trong Java | Input | `matches()` | Vì sao |
| --- | --- | --- | --- |
| `"file.txt"` | `fileXtxt` | `true` | `.` nhận `X` |
| `"file\\.txt"` | `file.txt` | `true` | `\.` chỉ nhận dấu chấm |
| `"file\\.txt"` | `file-txt` | `false` | Thiếu dấu chấm thật |
| `"a.b"` | `a` + newline + `b` | `false` | `.` mặc định không nhận xuống dòng |
| `"(?s)a.b"` | `a` + newline + `b` | `true` | Bật DOTALL |

Nếu đầu vào chứa **ký tự người dùng cung cấp** như tên file `report.2026`, đừng tự thay mọi dấu chấm bằng các chuỗi escape thủ công trong một regex phức tạp; `Pattern.quote(userText)` phù hợp hơn để trích dẫn nguyên văn toàn bộ giá trị (phần 8).

## 3. Dấu gạch chéo: `/` không phải delimiter trong Java regex

Một số ngôn ngữ hoặc công cụ viết mẫu theo dạng `/pattern/flags` (ví dụ JavaScript regex literal), khiến người học tưởng mọi regex đều cần hai dấu `/` bao ngoài. Trong Java, `Pattern.compile("api/v1/users")` dùng **trực tiếp** nội dung chuỗi như mẫu, vì vậy dấu `/` đơn lẻ khớp đúng dấu slash trong đường dẫn.

~~~java
Pattern.matches("api/v\\d+/users", "api/v2/users"); // true
Pattern.matches("api/v\\d+/users", "api\\v2\\users"); // false
~~~

Hai dòng này là lời gọi minh họa. Regex `api/v\d+/users` có dấu slash thường, `\d+` mới là phần regex đặc biệt. Viết thêm hai dấu `/` bao ngoài, chẳng hạn `Pattern.compile("/api/v1/")`, sẽ khiến Java tìm **cả các dấu slash đó như nội dung của mẫu**; nó không tự hiểu đây là cặp delimiter.

Cần phân biệt **hai loại gạch chéo**:

- `/` (*forward slash*): thường không cần escape trong Java regex, rất phổ biến trong URL/path kiểu Unix.
- `\` (*backslash*): là dấu escape của regex **và** của chuỗi Java. Để khớp **một** ký tự backslash thật, regex cần `\\`; Java string literal truyền cho `Pattern` phải viết `"\\\\"`.

Ví dụ minh họa đường dẫn Windows trong Java:

~~~java
String path = "C:\\temp\\x.txt";              // dữ liệu: C:\temp\x.txt
String regex = "C:\\\\temp\\\\x\\.txt";        // regex tìm dấu \ thật và dấu . thật
boolean correct = Pattern.matches(regex, path); // true
~~~

Đoạn trên dùng `Pattern` sau khi import. Nếu viết `"C:\temp\x.txt"` trong Java source, chuỗi có thể chứa escape ngoài ý định (như `\t`) hoặc không biên dịch vì escape không hợp lệ. Khi xử lý **tên đường dẫn dạng văn bản**, cân nhắc `Path`/`Files` thay vì regex nếu mục tiêu là thao tác file; dấu phân cách phụ thuộc ngữ cảnh hệ điều hành và nguồn dữ liệu.

## 4. Dấu đô la: neo kết thúc `$` hay ký tự tiền tệ `\$`?

Trong **mẫu regex**, `$` là **neo vị trí**, không tiêu thụ ký tự. Ví dụ:

~~~java
Pattern.matches("^AB\\d{2}$", "AB12");  // true
Pattern.matches("^AB\\d{2}$", "xAB12"); // false
~~~

`^` neo đầu và `$` neo cuối theo quy tắc Java regex. Lệnh `matches()` vốn đã yêu cầu **toàn chuỗi** khớp; trong tình huống này neo giúp người đọc dễ thấy ý định nhưng không phải điều kiện bắt buộc. Ngược lại, khi dùng `find()`, dấu `^`/`$` thay đổi những vị trí đoạn con có thể khớp.

Nếu muốn kiểm tra **dấu `$` thật** của tiền tệ, viết regex `\$` và Java literal `"\\$"`:

~~~java
Pattern.matches("total=\\$\\d+", "total=$25"); // true
~~~

Regex ở ví dụ là `total=\$\d+`: tìm `total=`, dấu `$` thật, rồi một hoặc nhiều chữ số. Nếu bỏ backslash trước `$`, mẫu không còn nghĩa tương tự.

**Cẩn thận với xuống dòng cuối:** `$` có thể nhận vị trí trước một line terminator kết thúc chuỗi; với `Pattern.MULTILINE`, nó còn phù hợp ở cuối từng dòng. `\z` biểu diễn **cuối đầu vào tuyệt đối** khi cần kiểm soát vị trí thật chặt trong regex; dấu `\z` cần viết thành `"\\z"` trong Java. `Pattern.matches(...)` và `Matcher.matches()` vẫn là cách rõ ràng để kiểm tra **toàn bộ** input.

### Kiểm thử `MULTILINE`

~~~java
Pattern p = Pattern.compile("^cat$", Pattern.MULTILINE);
boolean foundLine = p.matcher("cat\nbird").find();    // true
boolean wholeText = p.matcher("cat\nbird").matches(); // false
~~~

`find()` tìm riêng dòng `cat` vì `^`/`$` được diễn giải theo từng dòng. `matches()` không cho phép bỏ phần `\nbird` còn lại.

## 5. Nhóm bắt và nhóm không bắt: `(...)`, `(?:...)` và `(?<name>...)`

Ngoặc tròn có hai vai trò chính:

1. **Gom phần mẫu** để lượng từ hay phép chọn `|` tác động lên cả nhóm, ví dụ `(ab)+` khác `ab+`.
2. **Bắt (capture) đoạn khớp** để lấy lại bằng `Matcher.group(...)` hoặc tham chiếu trong chuỗi thay thế.

Nhóm bắt mặc định được đánh số **1, 2, ...** theo thứ tự dấu `(` mở của nhóm bắt, tính từ trái sang phải. Nhóm `0` là **toàn bộ lần khớp**. `(?:...)` chỉ gom, **không tăng số thứ tự nhóm**. Nhóm đặt tên `(?<ext>txt|csv)` vừa là nhóm bắt vừa có thể truy xuất theo `"ext"`.

Ví dụ file đơn giản:

~~~java
Pattern pattern = Pattern.compile(
        "^(?<base>[a-z]+)\\.(?<ext>txt|csv)$");
Matcher m = pattern.matcher("notes.txt");

if (m.matches()) {
    System.out.println(m.group(0));      // notes.txt
    System.out.println(m.group("base")); // notes
    System.out.println(m.group("ext"));  // txt
}
~~~

Đây là đoạn minh họa (cần import `Pattern`/`Matcher`). Lưu ý `m.group("base")` là lời gọi API với **tên nhóm đã khai báo trong regex**. Mẫu `(?<base>[a-z]+)` dùng dấu ngoặc để bắt `notes`, còn `\\.` trong Java dùng để khớp dấu chấm trước phần mở rộng.

**Chỉ gọi `group()`, `start()`, `end()` sau khi `find()` hoặc `matches()` thành công.** Nếu không có match hiện hành, `Matcher` ném `IllegalStateException`. Với nhóm tùy chọn không tham gia, `group(n)` có thể là `null`, `start(n)`/`end(n)` là `-1`. Các chỉ số `start/end` là **chỉ số UTF-16**, và `end` là vị trí exclusive.

Khi chỉ cần gom mà không trích xuất, dùng nhóm không bắt, chẳng hạn `(?:txt|csv)`. Việc này giúp giảm nguy cơ vô tình thay đổi vị trí `group(1)` khi sửa regex:

~~~java
Pattern noCapture = Pattern.compile("^[a-z]+\\.(?:txt|csv)$");
boolean okay = noCapture.matcher("notes.txt").matches(); // true
~~~

## 6. Tên nhóm và dấu đô la trong replacement: quy tắc khác regex

Một trong những bẫy phổ biến nhất: trong **mẫu regex**, `$` nghĩa là **neo**; trong **chuỗi thay thế** của `Matcher.replaceAll`, `$1` hay `${name}` nghĩa là **chèn nội dung nhóm bắt**.

| Bối cảnh | Cú pháp | Nghĩa |
| --- | --- | --- |
| Regex | `$` | Neo cuối |
| Regex | `\$` | Dấu đô la thật |
| Regex | `(abc)` | Bắt nội dung vào nhóm 1 |
| Regex | `(?<name>abc)` | Bắt nhóm tên `name` |
| Replacement của `Matcher`/`String.replaceAll` | `$1` | Đưa nội dung nhóm 1 vào kết quả |
| Replacement | `${name}` | Đưa nội dung nhóm có tên vào kết quả |
| Replacement | `\$` | Escape một dấu `$` trong **chuỗi replacement**, không có nghĩa là neo |
| Replacement | `Matcher.quoteReplacement(text)` | Dùng `text` theo nghĩa nguyên văn, kể cả `$` và `\` |

Ví dụ:

~~~java
String result = Pattern.compile("id=(\\d+)")
        .matcher("id=42; id=7")
        .replaceAll("item[$1]");
// item[42]; item[7]
~~~

Mẫu `(\\d+)` (trong Java literal) bắt một dãy chữ số thành nhóm 1. Replacement `"item[$1]"` lấy lại nội dung nhóm đó. **`$1` chỉ có tác dụng đặc biệt trong replacement**, không phải cách viết tham chiếu ngược bên trong mẫu regex. Nếu cần tham chiếu lại nội dung nhóm trong regex, dùng `\1` (Java literal `"\\1"`) hoặc `\k<name>` (Java literal `"\\k<name>"`).

Với nhóm có tên:

~~~java
String reordered = Pattern.compile("(?<word>[a-z]+)-(?<num>\\d+)")
        .matcher("abc-12")
        .replaceAll("${num}:${word}");
// 12:abc
~~~

**Nếu dữ liệu replacement do người dùng cung cấp**, đưa thẳng `"$9\\temp"` vào `replaceAll` có thể khiến regex engine cố tham chiếu nhóm không tồn tại hoặc xem `\` là escape. Dùng `Matcher.quoteReplacement(...)`:

~~~java
String rawReplacement = "$9\\temp";
String safe = Pattern.compile("TOKEN")
        .matcher("path=TOKEN")
        .replaceAll(Matcher.quoteReplacement(rawReplacement));
// path=$9\temp
~~~

Trong Java, `String.replace(old, new)` thay các chuỗi **nguyên văn**; `String.replaceAll(regex, replacement)` dùng **regex** và cú pháp replacement. Nếu chỉ muốn thay dấu chấm bằng dấu gạch ngang, `text.replace(".", "-")` đơn giản hơn `text.replaceAll("\\.", "-")`.

## 7. Chương trình Java 17: kiểm thử dấu chấm, slash và đô la

Chương trình sau cố tình gồm cả trường hợp **đáng chấp nhận** và **đáng bác bỏ**, tránh chỉ kiểm thử đầu vào đẹp:

~~~java
// RegexSymbolsDemo.java
import java.util.regex.Pattern;

public class RegexSymbolsDemo {
    static void check(String name, String regex, String input) {
        System.out.println(name + " = " + Pattern.matches(regex, input));
    }

    public static void main(String[] args) {
        check("literal dot", "report\\.txt", "report.txt");
        check("reject fake dot", "report\\.txt", "reportXtxt");
        check("wildcard dot", "report.txt", "reportXtxt");
        check("slash path", "api/v\\d+/users", "api/v2/users");
        check("reject backslashes", "api/v\\d+/users", "api\\v2\\users");
        check("literal dollar", "total=\\$\\d+", "total=$25");
        check("end anchor", "^AB\\d{2}$", "AB12");
        check("reject prefix", "^AB\\d{2}$", "xAB12");
        check("dot not newline", "a.b", "a\nb");

        boolean dotAll = Pattern.compile("a.b", Pattern.DOTALL)
                .matcher("a\nb")
                .matches();
        System.out.println("dotall newline = " + dotAll);

        Pattern line = Pattern.compile("^cat$", Pattern.MULTILINE);
        System.out.println("multiline find = "
                + line.matcher("cat\nbird").find());
        System.out.println("multiline matches = "
                + line.matcher("cat\nbird").matches());
    }
}
~~~

Lưu thành `RegexSymbolsDemo.java`, sau đó chạy:

~~~bash
javac --release 17 RegexSymbolsDemo.java
java RegexSymbolsDemo
~~~

Stdout:

~~~text
literal dot = true
reject fake dot = false
wildcard dot = true
slash path = true
reject backslashes = false
literal dollar = true
end anchor = true
reject prefix = false
dot not newline = false
dotall newline = true
multiline find = true
multiline matches = false
~~~

**Cách đọc test:** `"wildcard dot = true"` là kết quả chạy **đúng theo ngữ nghĩa regex** nhưng lại là **hành vi sai nếu yêu cầu nghiệp vụ chỉ nhận dấu chấm thật**. Đây là lý do test regex phải có **negative cases** ngoài positive cases. `"multiline find"` và `"multiline matches"` không mâu thuẫn: chúng hỏi hai câu khác nhau về phạm vi khớp.

## 8. Chương trình Java 17: nhóm, replacement và dữ liệu cần escape

~~~java
// RegexGroupsAndReplacementDemo.java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class RegexGroupsAndReplacementDemo {
    public static void main(String[] args) {
        Pattern file = Pattern.compile(
                "^(?<base>[a-z]+)\\.(?<ext>txt|csv)$");
        Matcher m = file.matcher("notes.txt");

        System.out.println("matches = " + m.matches());
        System.out.println("full = " + m.group(0));
        System.out.println("base = " + m.group(1));
        System.out.println("extension = " + m.group("ext"));
        System.out.println("base range = "
                + m.start("base") + ".." + m.end("base"));

        String byNumber = Pattern.compile("id=(\\d+)")
                .matcher("id=42; id=7")
                .replaceAll("item[$1]");
        System.out.println("by number = " + byNumber);

        String byName = Pattern.compile(
                "(?<word>[a-z]+)-(?<num>\\d+)")
                .matcher("abc-12")
                .replaceAll("${num}:${word}");
        System.out.println("by name = " + byName);

        String literal = "$9\\temp";
        String safe = Pattern.compile("TOKEN")
                .matcher("path=TOKEN")
                .replaceAll(Matcher.quoteReplacement(literal));
        System.out.println("safe replacement = " + safe);
    }
}
~~~

Lệnh chạy:

~~~bash
javac --release 17 RegexGroupsAndReplacementDemo.java
java RegexGroupsAndReplacementDemo
~~~

Stdout:

~~~text
matches = true
full = notes.txt
base = notes
extension = txt
base range = 0..5
by number = item[42]; item[7]
by name = 12:abc
safe replacement = path=$9\temp
~~~

Ở chương trình này, `group(0)` trả về toàn bộ `notes.txt`, nhóm `base` trả về `notes`, còn `ext` trả về `txt`. Kết quả `base range = 0..5` là khoảng **bắt đầu gồm, kết thúc không gồm**. Test cho replacement cho thấy muốn đưa ký tự `$`/backslash nguyên văn vào kết quả thì `Matcher.quoteReplacement` tránh các quy tắc thay thế nhóm.

## 9. Chương trình Java 17: kiểm thử chuỗi literal động và backslash

Nếu một giá trị do người dùng nhập vào chỉ cần tìm **nguyên văn** trong dữ liệu, hãy dùng `Pattern.quote(...)`. Việc viết:

~~~java
Pattern.matches("v1.2/$", "v1.2/$");
~~~

không đảm bảo đúng theo nghĩa nguyên văn, vì dấu `.` đang là wildcard và `$` là neo (không nhận một ký tự đô la thật). Dùng `Pattern.quote` khi cả chuỗi cần coi như literal:

~~~java
// RegexLiteralInputDemo.java
import java.util.regex.Pattern;

public class RegexLiteralInputDemo {
    public static void main(String[] args) {
        String literal = "v1.2/$";
        String regex = "^" + Pattern.quote(literal) + "$";
        System.out.println("literal = "
                + Pattern.matches(regex, "v1.2/$"));

        String windows = "C:\\temp\\x.txt";
        String windowsRegex = "C:\\\\temp\\\\x\\.txt";
        System.out.println("windows = "
                + Pattern.matches(windowsRegex, windows));

        String price = "Cost: $25";
        String changed = Pattern.compile("\\$")
                .matcher(price)
                .replaceAll("USD ");
        System.out.println("changed = " + changed);

        String kept = Pattern.compile("\\$")
                .matcher(price)
                .replaceAll("\\$");
        System.out.println("kept = " + kept);
    }
}
~~~

Lệnh chạy:

~~~bash
javac --release 17 RegexLiteralInputDemo.java
java RegexLiteralInputDemo
~~~

Stdout:

~~~text
literal = true
windows = true
changed = Cost: USD 25
kept = Cost: $25
~~~

`Pattern.quote` biến `v1.2/$` thành mẫu tìm kiếm literal hoàn chỉnh cho phần dữ liệu được quote; cặp `^...$` bên ngoài thể hiện ý định ràng buộc toàn chuỗi (dù `matches()` đã thực hiện việc đó). Ví dụ đường dẫn Windows kiểm tra cách escape đúng qua **hai tầng**. Hai dòng cuối cùng cố tình dùng `\\$` trong mẫu để tìm dấu đô la thật, rồi thực hiện **hai chính sách replacement khác nhau**.

## 10. Thiết kế test regex có ý nghĩa

Trước khi chấp nhận một regex, nên phân loại test theo các câu hỏi:

| Loại test | Input mẫu | Điều cần xác minh |
| --- | --- | --- |
| **Đúng định dạng** | `report.txt`, `api/v2/users` | Mẫu nhận văn bản hợp lệ |
| **Ký tự đặc biệt khác nghĩa** | `reportXtxt`, `api\v2\users` | Dấu chấm/slash không bị đọc sai |
| **Đô la thật so với neo** | `total=$25`, `total=25` | `\$` nhận tiền tệ, `$` giới hạn vị trí |
| **Tiền/hậu tố** | `xAB12`, `AB12x` | Kiểm tra toàn chuỗi hay đoạn con |
| **Xuống dòng** | `a\nb`, `cat\nbird` | Hiệu ứng DOTALL/MULTILINE đúng yêu cầu |
| **Nhóm bắt** | `notes.txt`, `notes.exe` | `matches()` và `group(...)` trả đúng nội dung |
| **Nhóm tùy chọn** | Có và không có phần tùy chọn | Xử lý `null`, không dùng group sai |
| **Replacement không tin cậy** | Chuỗi chứa `$` và `\` | Không thay thế nhóm ngoài ý định hoặc phát sinh lỗi |
| **Unicode, input rỗng/dài** | Tên có dấu, chuỗi rỗng, chuỗi rất dài | Nhận đúng theo đặc tả, không giả định ASCII hoặc chạy quá chậm |

Một vài quy tắc thực tế:

1. **Viết rõ mong đợi:** test tên `shouldRejectWrongExtensionSeparator` tốt hơn test mơ hồ `testRegex`.
2. **Dùng `matches()` cho định dạng toàn chuỗi, `find()` cho trích xuất**; nếu kiểm thử cả hai, đặt tên kết quả rõ ràng.
3. **Tránh khẳng định chuỗi “khớp” chỉ vì `find()` trả true** nếu nghiệp vụ đòi mọi ký tự hợp lệ.
4. **Kiểm tra cặp dấu đóng/mở của nhóm** và thứ tự nhóm; khi thay đổi `(...)` thành `(?:...)`, số nhóm có thể đổi.
5. **Kiểm tra cả regex lẫn replacement**: khớp đúng vẫn có thể tạo ra đầu ra sai nếu `$1`, `${name}` hoặc backslash trong replacement bị hiểu ngoài dự kiến.
6. **Không nối trực tiếp input chưa tin cậy vào regex** nếu chỉ muốn tìm nguyên văn. Dùng `Pattern.quote`, kiểm soát giới hạn độ dài/độ phức tạp và chú ý khả năng backtracking rất chậm của mẫu không chặt chẽ.
7. **Dùng dữ liệu thực và test hồi quy** sau khi thay đổi mẫu: regex ngắn không có nghĩa là dễ đoán trong mọi trường hợp.

### Minh họa kiểm thử bằng JUnit 5

Nếu dự án đã có JUnit 5, các assertion có thể được viết gọn như sau. **Đây là phương thức test nằm trong lớp test của dự án**, không phải chương trình Java độc lập; cần dependency JUnit 5 và các import phù hợp.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.regex.Pattern;

class RegexSymbolsTest {
    @Test
    void literalDotMustNotAcceptOtherSeparators() {
        String regex = "file\\.txt";
        assertTrue(Pattern.matches(regex, "file.txt"));
        assertFalse(Pattern.matches(regex, "fileXtxt"));
    }

    @Test
    void slashAndDollarAreDifferentFromRegexAnchors() {
        assertTrue(Pattern.matches("api/v\\d+", "api/v2"));
        assertTrue(Pattern.matches("price=\\$\\d+", "price=$12"));
        assertFalse(Pattern.matches("price=\\$\\d+", "price=12"));
    }

    @Test
    void namedGroupCapturesCorrectExtension() {
        var matcher = Pattern.compile(
                "^(?<stem>[a-z]+)\\.(?<ext>txt|csv)$")
                .matcher("notes.csv");
        assertTrue(matcher.matches());
        assertEquals("notes", matcher.group("stem"));
        assertEquals("csv", matcher.group("ext"));
    }
}
~~~

Test đọc dễ hơn khi **mỗi assertion kiểm tra đúng một đặc điểm**. Tránh test chỉ chứa những ví dụ hợp lệ vì dấu `.` wildcard rất dễ “lọt” những chuỗi gần đúng.

## 11. Lỗi phổ biến cần tránh

- **Viết `"\\. "` thay vì `"\\."`** (thừa dấu cách) hoặc `"."` (chấm wildcard) trong lúc muốn tìm dấu chấm thật. Chuỗi Java phải tạo ra đúng regex dự kiến.
- **Nhầm cách viết `/regex/` trong JavaScript với Java `Pattern`:** ở Java, hai slash đó được tính vào nội dung mẫu; không phải delimiter.
- **Nhầm dấu gạch xuôi và gạch ngược:** `/` thường là literal; `\` bắt đầu escape trong regex, và phải được escape tiếp trong Java string.
- **Dùng `$` để biểu diễn đô la tiền tệ:** trong pattern `$` là anchor, muốn dấu thật dùng `\$`; trong Java literal là `"\\$"`.
- **Dùng `"$1"` trong pattern với kỳ vọng tham chiếu nhóm:** `$1` là cú pháp của **replacement**, không phải backreference regex. Trong pattern, tham chiếu nhóm theo số dùng `\1` (Java `"\\1"`).
- **Dùng dữ liệu replacement có `$`/`\` trực tiếp:** `replaceAll` xử lý cú pháp nhóm/escape; cần `Matcher.quoteReplacement` cho literal.
- **Lấy `group(1)` trước khi có match:** dẫn tới `IllegalStateException`; kiểm tra thành công của `matches()` hoặc `find()` trước.
- **Vô tình thêm nhóm bắt:** số nhóm thay đổi làm `$1`/`group(1)` mang ý nghĩa khác. Dùng `(?:...)` nếu chỉ gom.
- **Quên thử xuống dòng:** DOTALL và MULTILINE là hai tùy chọn khác nhau; đừng suy ra từ một đầu vào chỉ có một dòng.
- **Đoán đúng đắn từ một kết quả true:** test phải có cả chuỗi sai sát biên, chuỗi có dấu đặc biệt, dòng mới, nhóm tùy chọn và dữ liệu replacement.
- **Phân tích cấu trúc phức tạp chỉ bằng regex:** đường dẫn/URL/JSON/HTML có quy tắc cú pháp riêng; khi bài toán cần hiểu cấu trúc hoàn chỉnh, chọn parser hoặc API chuyên dụng.

## 12. Bài luyện tập

**Bài 1.** Tại sao regex `a.b` nhận `a/b` khi dùng `matches()`? Viết Java regex chỉ nhận đúng `a.b`.

**Đáp án:** `.` là wildcard, nhận cả slash. Cần `Pattern.matches("a\\.b", "a.b")`.

**Bài 2.** Viết regex Java kiểm tra toàn chuỗi dạng `/user/123` (chính xác hai slash xuôi, chữ `user`, và ba chữ số).

**Đáp án:** `Pattern.matches("/user/\\d{3}", "/user/123")`. Slash xuôi không phải ký hiệu escape đặc biệt.

**Bài 3.** Với regex Java `"^\\$\\d+$"`, `"$15"` có khớp không? `"15$"` có khớp không?

**Đáp án:** `"$15"` khớp, `"15$"` không khớp. Regex yêu cầu dấu đô la **đầu** chuỗi, rồi một hoặc nhiều chữ số đến hết.

**Bài 4.** Với mẫu `(?<first>[a-z]+)-(?<second>\d+)` trong regex (Java literal cần `\\d`), muốn output `"42:abc"` từ `"abc-42"` thì nên dùng replacement nào?

**Đáp án:** `"${second}:${first}"`. Tên nhóm trong replacement nằm sau dấu `$`, được bao bằng cặp `{...}`.

**Bài 5.** Chuỗi replacement đến từ người dùng là `"$2\folder"`. Vì sao không truyền thẳng vào `Matcher.replaceAll(...)`?

**Đáp án:** `$2` có thể bị hiểu là tham chiếu nhóm 2 và `\` có ý nghĩa escape trong replacement. Dùng `Matcher.quoteReplacement(userReplacement)` để chèn nguyên văn.

**Bài 6.** Vì sao mẫu `"report\\.txt"` qua `find()` vẫn có thể trả true đối với `"backup_report.txt.old"`?

**Đáp án:** `find()` tìm được một **đoạn con** `report.txt` trong chuỗi dài hơn. Nếu kiểm tra **đúng toàn bộ tên file**, dùng `matches()` hoặc ràng buộc phù hợp trong mẫu.

## Ghi nhớ

- **`.` trong regex**: wildcard; **`\.`**: dấu chấm thật; Java literal của mẫu sau là `"\\."`.
- **`/` trong Java regex**: ký tự thường, không phải dấu bao mẫu. **`\`**: ký tự escape trong cả regex và Java source.
- **`$` trong regex**: neo cuối; **`\$`**: dấu đô la thật. **`$1` hoặc `${name}` trong replacement**: nội dung nhóm bắt.
- **`(...)`**: nhóm bắt; **`(?:...)`**: nhóm không bắt; **`(?<name>...)`**: nhóm có tên.
- **Kiểm thử thực tế**: kết hợp đầu vào đúng/sai, `matches()`/`find()`, xuống dòng, replacement đặc biệt và những chuỗi chứa dấu câu.

Có thể đối chiếu chi tiết tại [Java 17 Pattern API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html) và [Java 17 Matcher API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Matcher.html).
