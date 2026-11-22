# Tham chiếu ngược tới nhóm có tên (named-group backreference) trong Java Regex

## 1. Khái niệm và mục đích

**Nhóm bắt có tên** (named capturing group) lưu một đoạn văn bản đã khớp dưới một tên dễ hiểu. **Tham chiếu ngược tới nhóm có tên** (named backreference) yêu cầu một vị trí về sau trong cùng lần khớp phải xuất hiện lại **đúng nội dung mà nhóm đó vừa bắt được**. Tính năng này có từ Java 7 và tiếp tục được hỗ trợ trong `java.util.regex.Pattern` của các JDK hiện đại.

Chẳng hạn, định dạng `AB-123-AB` yêu cầu hai mã chữ ở đầu và cuối giống hệt nhau. Kiểm tra hai đoạn bằng cùng một mẫu `[A-Z]{2}` chỉ đảm bảo *cùng kiểu dữ liệu*, còn `\k<code>` đảm bảo *cùng giá trị thực tế*.

| Cú pháp | Ý nghĩa | Ngữ cảnh sử dụng |
| --- | --- | --- |
| `(?<code>[A-Z]{2})` | Bắt đúng hai chữ cái ASCII viết hoa và lưu tên `code` | Bên trong biểu thức chính quy |
| `\k<code>` | Khớp lại đúng chuỗi nhóm `code` đã bắt trong lần khớp hiện tại | Bên trong biểu thức chính quy |
| `matcher.group("code")` | Lấy chuỗi nhóm `code` sau khi `find()` hoặc `matches()` thành công | Java API |
| `${code}` | Chèn chuỗi nhóm `code` vào văn bản thay thế | Chuỗi replacement của `replaceAll`/`appendReplacement` |
| `\1` | Tham chiếu ngược theo số thứ tự nhóm bắt thứ nhất | Bên trong biểu thức chính quy |

**Lưu ý:** `\k<code>`, `group("code")` và `${code}` giải quyết ba việc khác nhau: kiểm tra sự lặp lại ngay khi *matching*, đọc kết quả sau khi *matching*, và xuất kết quả khi *replacement*.

## 2. Cơ chế khớp từng bước

Xét regex (viết theo cú pháp regex thuần, chưa escape cho chuỗi Java):

```regex
(?<code>[A-Z]{2})-\d{3}-\k<code>
```

Với đầu vào `AB-123-AB`, bộ máy regex thực hiện:

1. `(?<code>[A-Z]{2})` khớp `AB` và lưu `code = "AB"`.
2. `-` khớp dấu nối, `\d{3}` khớp `123`, rồi `-` khớp dấu nối tiếp.
3. `\k<code>` đòi hỏi chính xác `AB` đã bắt ở bước 1; vì thế đầu vào hợp lệ.

`AB-123-CD` không hợp lệ: `CD` vẫn là hai chữ cái viết hoa nhưng **khác `AB`**. Tham chiếu ngược không chạy lại `[A-Z]{2}` để nhận một giá trị bất kỳ; nó so với giá trị được lưu. Mỗi lần `Matcher.find()`/`matches()` thực hiện một phép khớp mới, các giá trị nhóm được xác lập cho phép khớp đó.

## 3. Ví dụ Java chạy độc lập: xác minh mã lặp

Tạo file **`NamedGroupBackreferenceDemo.java`**:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class NamedGroupBackreferenceDemo {
    public static void main(String[] args) {
        Pattern pattern = Pattern.compile(
                "(?<prefix>[A-Z]{2})-(?<number>\\d{3})-\\k<prefix>");

        String[] samples = {
                "AB-123-AB",
                "AB-123-CD",
                "XY-007-XY"
        };

        for (String input : samples) {
            Matcher matcher = pattern.matcher(input);
            if (matcher.matches()) {
                System.out.printf(
                        "%s -> match, prefix=%s, number=%s%n",
                        input,
                        matcher.group("prefix"),
                        matcher.group("number"));
            } else {
                System.out.printf("%s -> no match%n", input);
            }
        }
    }
}
```

Chạy trên JDK 17 trở lên (mã cũng chỉ sử dụng API regex đã có từ Java 7):

```bash
javac -encoding UTF-8 NamedGroupBackreferenceDemo.java
java NamedGroupBackreferenceDemo
```

Kết quả:

```text
AB-123-AB -> match, prefix=AB, number=123
AB-123-CD -> no match
XY-007-XY -> match, prefix=XY, number=007
```

Giải thích: `Matcher.matches()` yêu cầu **toàn bộ chuỗi** khớp regex. Nếu muốn tìm một đoạn phù hợp trong văn bản dài hơn, dùng `Matcher.find()` và chỉ đọc `group("prefix")`/`group("number")` sau khi tìm được match. `Pattern` có thể biên dịch một lần rồi dùng lại; đối tượng `Matcher` chứa trạng thái của từng phép khớp.

### Hai tầng escape trong Java

Regex cần các ký hiệu `\d` và `\k<prefix>`, nhưng dấu `\` cũng là ký tự escape của **Java string literal**. Vì vậy phải viết:

- Regex thuần: `(?<prefix>[A-Z]{2})-\d{3}-\k<prefix>`
- Chuỗi Java: `"(?<prefix>[A-Z]{2})-\\d{3}-\\k<prefix>"`

Viết `"\k<prefix>"` trực tiếp trong Java string gây lỗi escape ở lúc biên dịch Java; quên escape là một lỗi phổ biến khi chuyển regex từ tài liệu sang source code.

## 4. Áp dụng với tiếng Việt và Unicode

**Tên nhóm** trong `(?<name>...)`/`\k<name>` phải gồm các chữ cái ASCII `A–Z`/`a–z` và chữ số `0–9`, bắt đầu bằng chữ cái; ví dụ `word`, `ma2` hợp lệ, còn `ten_nhom`, `2word`, `từ` không hợp lệ. **Nội dung được bắt** hoàn toàn có thể là Unicode, kể cả tiếng Việt.

Đối với từ có dấu, `[\p{L}\p{M}]+` nhận cả ký tự thuộc loại *Letter* và dấu kết hợp thuộc loại *Mark*, phù hợp hơn `[A-Za-z]+`. Hai cách mã hóa Unicode có thể hiển thị giống nhau nhưng chứa dãy mã khác nhau, chẳng hạn `é` (U+00E9) và `e` + U+0301. Khi yêu cầu so khớp ổn định, hãy chuẩn hóa dữ liệu về cùng dạng (thường là NFC) trước khi áp dụng backreference.

Tạo file **`UnicodeNamedBackreferenceDemo.java`**:

```java
import java.text.Normalizer;
import java.util.regex.Pattern;

public class UnicodeNamedBackreferenceDemo {
    public static void main(String[] args) {
        String regex = "(?<word>[\\p{L}\\p{M}]+)\\s+\\k<word>";
        Pattern strict = Pattern.compile(regex);

        String same = "học học";
        String differentCase = "học Học";
        String mixedNormalization = "café cafe\u0301";

        System.out.println("same=" + strict.matcher(same).matches());
        System.out.println("caseChanged=" + strict.matcher(differentCase).matches());
        System.out.println("mixedNormalization="
                + strict.matcher(mixedNormalization).matches());

        Pattern ignoreCase = Pattern.compile(
                regex, Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);
        System.out.println("unicodeIgnoreCase="
                + ignoreCase.matcher(differentCase).matches());

        String normalized = Normalizer.normalize(
                mixedNormalization, Normalizer.Form.NFC);
        System.out.println("normalized="
                + strict.matcher(normalized).matches());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 UnicodeNamedBackreferenceDemo.java
java UnicodeNamedBackreferenceDemo
```

Kết quả:

```text
same=true
caseChanged=false
mixedNormalization=false
unicodeIgnoreCase=true
normalized=true
```

**Vì sao?** Mặc định so sánh có phân biệt chữ hoa/thường nên `học` và `Học` khác nhau. Với `CASE_INSENSITIVE | UNICODE_CASE`, Java xét quy tắc phân biệt hoa/thường của Unicode khi matching. Hai flag này **không tự chuẩn hóa NFC/NFD**; `Normalizer.normalize` xử lý sự khác biệt biểu diễn Unicode trước khi đối chiếu. Nếu đầu vào dùng khoảng trắng Unicode rộng hơn ASCII, cân nhắc `Pattern.UNICODE_CHARACTER_CLASS` cho cách hiểu các lớp định sẵn như `\s`, `\w`, `\d`.

## 5. Phân biệt backreference với truy xuất nhóm và thay thế

Đoạn sau minh họa lệnh thay thế (đặt trong một phương thức Java, có `import java.util.regex.Pattern;`):

```java
Pattern p = Pattern.compile("(?<code>[A-Z]{2})-(?<digits>\\d{3})");
String result = p.matcher("AB-123 XY-007")
                 .replaceAll("${digits}/${code}");
System.out.println(result); // 123/AB 007/XY
```

`${digits}` và `${code}` **chỉ xuất lại nội dung đã bắt vào chuỗi thay thế**, không yêu cầu một đoạn của đầu vào phải lặp lại. Ngược lại, `\k<code>` nằm trong regex và tham gia quyết định có match hay không. Khi thay thế bằng nội dung lấy từ người dùng, dùng `Matcher.quoteReplacement(text)` nếu cần giữ nguyên dấu `$` và `\` theo nghĩa literal; nếu không, chúng có thể bị hiểu như cú pháp replacement.

Nhóm có tên vẫn có **số thứ tự nhóm**, nên có thể đọc bằng `group(1)` hoặc tham chiếu bằng `\1` trong trường hợp tương ứng. Tuy vậy, `\k<name>` bền hơn khi ta thêm/bớt các nhóm bắt trước đó. Dùng `(?:...)` nếu chỉ cần nhóm cấu trúc mà không cần lưu giá trị, giúp tránh thay đổi số thứ tự nhóm không cần thiết.

## 6. Các lỗi phổ biến và giới hạn

1. **Sai tên nhóm hoặc trùng tên:** `(?<ten_nhom>...)`, `(?<2ten>...)` và khai báo cùng tên hai lần không hợp lệ trong Java regex. Tên được phân biệt chữ hoa/thường; phải dùng chính xác cùng tên trong `\k<name>` và `group("name")`.
2. **Tham chiếu nhóm không tồn tại:** regex chứa `\k<missing>` không có nhóm được khai báo tương ứng sẽ lỗi khi biên dịch `Pattern` (`PatternSyntaxException`). Gọi `group("missing")` sau một match hợp lệ cũng gây `IllegalArgumentException`.
3. **Quên escape Java:** biểu thức `\k<name>` cần viết `\\k<name>` trong Java string literal; tương tự `\p{L}` cần `\\p{L}`.
4. **Nhầm khớp toàn chuỗi và tìm đoạn:** `matches()` kiểm tra toàn bộ đầu vào; `find()` dò từng đoạn. Không gọi `group(...)` nếu chưa có một match thành công (nếu không có thể nhận `IllegalStateException`).
5. **Nhầm “cùng mẫu” với “cùng chữ”:** dùng hai lần `[A-Z]{2}` chấp nhận `AB-CD`; dùng `(?<x>[A-Z]{2})-\\k<x>` chỉ chấp nhận khi phần sau đúng bằng phần trước (theo chế độ so khớp được chọn).
6. **Không xử lý chuẩn hóa Unicode:** chuỗi giống nhau khi hiển thị có thể khác dãy code point; chuẩn hóa đầu vào khi nghiệp vụ cần coi chúng tương đương, đồng thời chọn chính sách hoa/thường một cách rõ ràng.
7. **Dùng regex cho cấu trúc lồng nhau phức tạp:** backreference phù hợp để kiểm tra một đoạn lặp lại, mã định danh/cặp dấu đơn giản; không thay thế parser cho XML, HTML hoặc một ngôn ngữ có cấu trúc đệ quy. Với đầu vào rất lớn hoặc không tin cậy, tránh các pattern có định lượng lồng nhau dễ gây backtracking quá mức.

## 7. Ghi nhớ và tự kiểm tra

- `(?<name>...)` **bắt và đặt tên**; `\k<name>` **đòi lặp lại đúng giá trị đã bắt**.
- Trong Java string cần escape backslash; ví dụ `"(?<id>\\d+)-\\k<id>"` nhận `"123-123"` nhưng từ chối `"123-456"`.
- Với Unicode, tách biệt **quy tắc nhận ký tự** (`\p{L}`, `\p{M}`), **quy tắc hoa/thường** (`UNICODE_CASE`) và **chuẩn hóa ký tự** (`Normalizer`).
- Khi đọc kết quả dùng `matcher.group("name")`, khi thay thế dùng `${name}`; hai thao tác đó không tự kiểm tra chuỗi lặp lại.

**Tài liệu API chính thức:** [Pattern — named capturing groups, backreferences và Unicode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html); [Matcher — group(String), matches/find, replaceAll](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Matcher.html); [Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html).
