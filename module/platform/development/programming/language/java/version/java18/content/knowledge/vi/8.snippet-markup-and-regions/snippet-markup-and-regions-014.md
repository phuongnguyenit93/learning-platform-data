# Kết hợp region được trích xuất với markup highlight, link và replace

## Mục tiêu bài học

Một file external snippet có thể chứa nhiều ví dụ, method hoặc phần cấu hình. Thuộc tính `region` của `{@snippet}` chọn đoạn cần đưa vào tài liệu; các markup tag `@highlight`, `@link` và `@replace` điều chỉnh cách đoạn đó được trình bày.

Hai nhiệm vụ phối hợp với nhau:

1. **Chọn nội dung:** marker `@start region="..."` và `@end region="..."` xác định đoạn external mà `{@snippet}` sẽ trích.
2. **Định dạng nội dung:** markup comment nằm trong đoạn được chọn làm nổi bật văn bản, liên kết đến API hoặc thay placeholder trong bản HTML.

Cơ chế snippet được giới thiệu trong Java 18 qua JEP 413 và tiếp tục được hỗ trợ trong JDK hiện đại. Bài học thuộc chương **Markup và region** của module `JAVA_VERSION_JAVA18`. Module khám phá các thay đổi Java 18 còn hữu ích trên JDK hiện đại, trong đó có UTF-8 mặc định, Simple Web Server và snippet trong Javadoc; bài này tập trung vào việc tạo ví dụ API có thể tái sử dụng, dễ đọc và dễ kiểm chứng.

Sau bài học, bạn có thể:

- Chọn một vùng external bằng `{@snippet file="..." region="..."}`.
- Đặt `@highlight`, `@link` và `@replace` ngay trong vùng được trích.
- Phân biệt marker chọn vùng external với region mở phạm vi cho markup action.
- Kết hợp nhiều markup action trên các dòng khác nhau trong cùng snippet.
- Dùng placeholder hợp lệ trong source rồi thay bằng văn bản dễ hiểu hơn ở HTML.
- Kiểm tra target của hyperlink và nội dung sau replacement.
- Sinh Javadoc và đối chiếu HTML với file external gốc.

## 1. Hai nhiệm vụ: trích đoạn và trình bày

Giả sử file nguồn có nhiều phần:

~~~java
public class ApiExamples {
    public static void main(String... args) {
        String raw = args.length == 0 ? "  Java  " : args[0];
        String normalized = raw.strip();
        System.out.println(normalized);
    }

    public static void anotherExample() {
        // Một ví dụ khác không liên quan
    }
}
~~~

Tài liệu chỉ cần phần chuẩn hóa. Ta đánh dấu đoạn đó bằng region:

~~~java
// @start region="normalize"
String raw = args.length == 0 ? "  Java  " : args[0];
String normalized = raw.strip();
System.out.println(normalized);
// @end region="normalize"
~~~

Trong class đang được tạo tài liệu, dùng:

~~~java
/**
 * Ví dụ chuẩn hóa chuỗi:
 * {@snippet file="ApiExamples.java" region="normalize"}
 */
public class ApiDoc {
}
~~~

Thuộc tính `region="normalize"` chọn nội dung giữa hai marker. Các dòng nằm ngoài vùng không được đưa vào snippet này.

Sau khi đã chọn đúng đoạn, có thể thêm markup comment vào những dòng bên trong file external:

~~~java
String normalized = raw.strip(); // @link substring="strip()" target="java.lang.String#strip()"
System.out.println(normalized);   // @highlight substring="normalized" type=highlighted
~~~

Các markup comment được Javadoc xử lý khi tạo snippet. Chúng không xuất hiện như comment trong mã hiển thị.

| Cơ chế | Câu hỏi được giải quyết |
| --- | --- |
| `@start region` / `@end region` và thuộc tính `region` của `{@snippet}` | Đoạn nào của file được đưa vào tài liệu? |
| `@highlight` | Phần văn bản nào cần được nhấn mạnh? |
| `@link` | Phần văn bản nào cần liên kết đến declaration API? |
| `@replace` | Phần văn bản nào cần được thay bằng nội dung trình bày khác? |

Một markup comment có thể chứa nhiều markup tag. Khi các action nhắm đến những dòng khác nhau, cách dễ đọc là đặt comment tương ứng ở cuối từng dòng; nếu comment đứng riêng và kết thúc bằng dấu hai chấm, các tag trong comment áp dụng lên dòng ngay sau đó.

## 2. Cấu trúc external snippet có markup

Một file Java external có thể chứa nhiều region và nhiều markup comment. Ví dụ cấu trúc:

~~~text
src/
└── demo/
    ├── ApiDoc.java
    └── snippet-files/
        └── ApiExamples.java
~~~

File `ApiExamples.java`:

~~~java
package demo;

public final class ApiExamples {
    private ApiExamples() {
    }

    public static void main(String... args) {
        // @start region="normalize"
        String raw = args.length == 0 ? "  Java  " : args[0];
        String normalized = raw.strip(); // @link substring="strip()" target="java.lang.String#strip()"
        String token = "placeholder"; // @replace substring='"placeholder"' replacement="..."
        System.out.println(normalized); // @highlight substring="normalized" type=highlighted
        // @end region="normalize"
    }
}
~~~

File `ApiDoc.java`:

~~~java
package demo;

/**
 * Chuẩn hóa đầu vào và trình bày kết quả:
 * {@snippet file="ApiExamples.java" region="normalize"}
 */
public final class ApiDoc {
}
~~~

Trong ví dụ này, `normalize` là vùng được trích xuất. Ba markup comment bên trong vùng thực hiện ba nhiệm vụ riêng:

- `@link` gắn liên kết cho `strip()` đến method `String.strip()`.
- `@replace` thay string literal `"placeholder"` bằng dấu ba chấm trong HTML.
- `@highlight` làm nổi bật chữ `normalized` trong câu lệnh in.

Nội dung source vẫn là mã Java hợp lệ. Các marker region và markup comment được xử lý khi sinh tài liệu; file external trên đĩa không bị chỉnh sửa.

## 3. Kết hợp `@highlight` trong vùng được trích

`@highlight` có thể làm nổi bật một chuỗi literal bằng `substring` hoặc một mẫu bằng `regex`. Khi không có selector, toàn bộ dòng được làm nổi bật.

Ví dụ trong file external:

~~~java
// @start region="validation"
if (input == null) {
    throw new IllegalArgumentException("input");
}
if (input.isBlank()) {
    throw new IllegalArgumentException("blank input");
}
// @end region="validation"
~~~

Muốn nhấn mạnh tên biến và các vị trí có chữ `input`, đặt markup comment trong region:

~~~java
// @start region="validation"
if (input == null) { // @highlight substring="input" type=bold
    throw new IllegalArgumentException("input");
}
if (input.isBlank()) {
    throw new IllegalArgumentException("blank input");
}
// @end region="validation"
~~~

Javadoc tham chiếu:

~~~java
{@snippet file="ValidationExamples.java" region="validation"}
~~~

Kết quả hiển thị vẫn có đầy đủ các dòng kiểm tra; những phần khớp selector trên dòng có markup được làm nổi bật. Markup comment chỉ áp dụng lên dòng chứa comment nếu không mở region cho action.

### 3.1. Làm nổi bật nhiều lần xuất hiện trên cùng một dòng

~~~java
System.out.println("input=" + input); // @highlight substring="input" type=highlighted
~~~

Selector `substring` tìm các lần xuất hiện của chuỗi được chỉ định trong phạm vi của markup action trên dòng đó. Nếu muốn chọn một mẫu linh hoạt, dùng `regex`:

~~~java
System.out.println("status=ready"); // @highlight regex='".*"' type=italic
~~~

Regex trong ví dụ khớp phần string literal nằm giữa dấu nháy kép. Khi dùng regex, hãy mở HTML sau khi sinh Javadoc để xác nhận chính xác đoạn được chọn.

### 3.2. Dùng region cho phạm vi của một markup action

Nếu cần áp dụng một highlight trên nhiều dòng trong nội dung snippet, markup action có thể tự mở region:

~~~java
// @highlight region="names" substring="input" type=bold :
if (input == null) {
    throw new IllegalArgumentException("input");
}
boolean blank = input.isBlank();
// @end region="names"
~~~

Đây là **region của action highlight**. Nó xác định phạm vi mà `@highlight` tìm selector. Khi snippet external còn cần một vùng trích xuất, hãy giữ marker `@start region="validation"` riêng để `{@snippet region="validation"}` chọn nội dung. Không dùng tên region của action như thể nó tự động thay thế marker `@start` dành cho việc trích external snippet.

## 4. Kết hợp `@link` để dẫn đến API

`@link` tạo hyperlink từ văn bản trong snippet đến một declaration API. Thuộc tính `target` dùng cú pháp reference giống inline tag `{@link ...}` trong Javadoc.

Ví dụ external:

~~~java
// @start region="normalization"
String normalized = raw.strip(); // @link substring="strip()" target="java.lang.String#strip()"
String upper = normalized.toUpperCase(Locale.ROOT);
// @end region="normalization"
~~~

Javadoc:

~~~java
{@snippet file="TextExamples.java" region="normalization"}
~~~

Khi sinh HTML:

- Dòng khai báo `normalized` vẫn hiển thị.
- Chữ `strip()` trở thành hyperlink đến `String.strip()`.
- Các phần còn lại của dòng không bị thay đổi.

### 4.1. Chọn chính xác phần cần liên kết

Nên dùng `substring` để chọn đúng tên API:

~~~java
var result = String.join(" ", values); // @link substring="String.join" target="java.lang.String#join(java.lang.CharSequence, java.lang.CharSequence[])"
~~~

Nếu target có overload, hãy ghi đúng parameter list. Không đưa tên tham số hoặc kiểu trả về vào reference. Với API trong module hoặc package khác, có thể dùng tên class đầy đủ để tránh mơ hồ.

Ví dụ target:

~~~text
java.lang.String#strip()
java.util.List#of(java.lang.Object[])
java.lang.String#join(java.lang.CharSequence, java.lang.CharSequence[])
~~~

Tên và kiểu tham số phải khớp declaration API. Javadoc phân giải target theo quy tắc reference; nó không dựa vào giá trị runtime của đối số.

### 4.2. Khi target không phân giải

Nếu Javadoc báo không tìm thấy target:

1. Kiểm tra tên class và package.
2. Kiểm tra tên method và chữ hoa/thường.
3. Nếu method overloaded, kiểm tra số lượng, kiểu và thứ tự parameter list.
4. Dùng tên đầy đủ như `java.lang.String` nếu tên ngắn không phân giải được.
5. Sinh lại Javadoc và kiểm tra hyperlink trong HTML.

Một dòng snippet có thể hiển thị đúng nhưng target link vẫn sai. Vì vậy, kiểm tra cả nội dung mã lẫn URL của anchor.

## 5. Kết hợp `@replace` để thay placeholder

`@replace` thay văn bản trong snippet hiển thị. Đây là cách giữ source hợp lệ nhưng trình bày một giá trị tượng trưng hoặc dấu ba chấm cho người đọc.

Ví dụ external:

~~~java
// @start region="configuration"
String endpoint = "https://api.example.test"; // @replace substring='"https://api.example.test"' replacement="BASE_URL"
int timeoutSeconds = 30; // @replace substring="30" replacement="DEFAULT_TIMEOUT"
// @end region="configuration"
~~~

Javadoc:

~~~java
{@snippet file="ConfigExamples.java" region="configuration"}
~~~

Nội dung hiển thị có dạng:

~~~java
String endpoint = BASE_URL;
int timeoutSeconds = DEFAULT_TIMEOUT;
~~~

File external vẫn giữ hai literal ban đầu. Replacement chỉ tác động lên văn bản được trình bày trong HTML.

### 5.1. Dùng placeholder hợp lệ để thay bằng dấu ba chấm

~~~java
String token = "placeholder"; // @replace substring='"placeholder"' replacement="..."
~~~

Kết quả:

~~~java
String token = ...;
~~~

`"placeholder"` là string literal hợp lệ trong source. Dấu ba chấm ở bản hiển thị cho biết giá trị cụ thể không phải trọng tâm của ví dụ.

### 5.2. Dùng regex replacement

Khi phần cần thay có dạng biến đổi, `@replace` có thể dùng `regex`:

~~~java
String version = "release-18"; // @replace regex='release-([0-9]+)' replacement="$1"
~~~

Kết quả hiển thị:

~~~java
String version = "18";
~~~

`$1` tham chiếu capture group đầu tiên theo quy tắc replacement của Java regex. Khi dùng dấu dollar hoặc backslash trong replacement, cần tuân theo quy tắc escape của replacement, không nhầm với cú pháp string literal Java.

### 5.3. Replacement không sửa source và không che bí mật

`@replace` chỉ biến đổi bản trình bày. File external vẫn chứa source gốc; vì vậy, không dùng replacement rỗng hoặc dấu ba chấm để che mật khẩu, token, private key hay dữ liệu nhạy cảm. Hãy loại bỏ dữ liệu bí mật khỏi source trước khi đưa file vào tài liệu.

## 6. Kết hợp cả ba markup action trong cùng một extracted region

Đây là ví dụ tổng hợp. Một region external được chọn một lần; bên trong region, mỗi dòng có thể có markup action phù hợp.

File `TextExamples.java`:

~~~java
package demo;

public final class TextExamples {
    private TextExamples() {
    }

    public static void main(String... args) {
        // @start region="text-flow"
        String raw = args.length == 0 ? "  Java  " : args[0];
        String normalized = raw.strip(); // @link substring="strip()" target="java.lang.String#strip()"
        String label = "placeholder"; // @replace substring='"placeholder"' replacement="DISPLAY_LABEL"
        System.out.println(normalized + ": " + label); // @highlight substring="normalized" type=bold
        // @end region="text-flow"
    }
}
~~~

File `TextApiDoc.java`:

~~~java
package demo;

/**
 * Chuẩn hóa và trình bày một giá trị:
 * {@snippet file="TextExamples.java" region="text-flow"}
 */
public final class TextApiDoc {
}
~~~

Ba markup action phối hợp như sau:

| Dòng trong source | Markup | Kết quả trình bày |
| --- | --- | --- |
| `String normalized = raw.strip();` | `@link substring="strip()" target="java.lang.String#strip()"` | `strip()` trở thành liên kết đến API. |
| `String label = "placeholder";` | `@replace substring='"placeholder"' replacement="DISPLAY_LABEL"` | Literal được thay bằng tên tượng trưng. |
| `System.out.println(normalized + ": " + label);` | `@highlight substring="normalized" type=bold` | Chữ `normalized` được làm nổi bật. |

Nội dung mã hiển thị có dạng:

~~~java
String raw = args.length == 0 ? "  Java  " : args[0];
String normalized = raw.strip();
String label = DISPLAY_LABEL;
System.out.println(normalized + ": " + label);
~~~

Trong HTML thực tế, ngoài văn bản mã còn có kiểu hiển thị của highlight và anchor hyperlink. Code block ở trên chỉ mô tả phần văn bản sau khi replacement; nó không thể hiện kiểu chữ hoặc URL của liên kết.

## 7. Nhiều extracted region trong một file, mỗi vùng có markup riêng

Một file external có thể định nghĩa nhiều region. Mỗi tag `{@snippet}` chọn một vùng khác nhau; các markup comment trong từng vùng được áp dụng khi tạo snippet tương ứng.

Ví dụ file `WorkflowExamples.java`:

~~~java
package demo;

public final class WorkflowExamples {
    public static void main(String... args) {
        // @start region="prepare"
        String raw = args.length == 0 ? "  Java  " : args[0];
        String normalized = raw.strip(); // @link substring="strip()" target="java.lang.String#strip()"
        // @end region="prepare"

        // @start region="display"
        String label = "placeholder"; // @replace substring='"placeholder"' replacement="DISPLAY_LABEL"
        System.out.println(normalized + ": " + label); // @highlight substring="normalized" type=highlighted
        // @end region="display"
    }
}
~~~

File tài liệu:

~~~java
/**
 * Chuẩn bị dữ liệu:
 * {@snippet file="WorkflowExamples.java" region="prepare"}
 *
 * Trình bày kết quả:
 * {@snippet file="WorkflowExamples.java" region="display"}
 */
public class WorkflowApiDoc {
}
~~~

Mỗi snippet có phạm vi riêng:

- `prepare` hiển thị bước chuẩn hóa và liên kết đến `String.strip()`.
- `display` hiển thị placeholder được thay và tên biến được làm nổi bật.
- Các dòng ngoài vùng được chọn không xuất hiện trong snippet tương ứng.

Cách tổ chức này hữu ích khi cùng một file chứa ví dụ hoàn chỉnh nhưng tài liệu muốn giải thích từng bước ở các phần khác nhau.

## 8. Phân biệt region trích xuất và region của markup action

Trong một external snippet, hai kiểu region có vai trò khác nhau:

| Cú pháp | Vai trò |
| --- | --- |
| `@start region="text-flow"` ... `@end region="text-flow"` | Đánh dấu đoạn external để `{@snippet region="text-flow"}` trích ra. |
| `@highlight region="focus"` ... `@end region="focus"` | Mở phạm vi nhiều dòng để action highlight tìm selector. |
| `@replace region="details"` ... `@end region="details"` | Mở phạm vi nhiều dòng để action replace tìm nội dung. |
| `@link region="apiCalls"` ... `@end region="apiCalls"` | Mở phạm vi nhiều dòng để action link tìm văn bản. |

Không dùng tên của action region thay cho tên vùng được chọn bởi thuộc tính `region` của `{@snippet}`. Nếu cần cả hai cơ chế, hãy đặt tên khác nhau và giữ marker mở/đóng rõ ràng.

Ví dụ:

~~~java
// @start region="whole-example"
String raw = input.strip(); // @link substring="strip()" target="java.lang.String#strip()"
// @highlight region="variable-uses" substring="raw" type=bold :
String normalized = raw;
System.out.println(raw);
// @end region="variable-uses"
String result = normalized;
// @end region="whole-example"
~~~

Trong ví dụ:

- `whole-example` là vùng external mà tag `{@snippet file=... region="whole-example"}` lựa chọn.
- `variable-uses` là vùng action để highlight các lần xuất hiện của `raw`.
- Hai tên phục vụ hai mục đích khác nhau và có cặp marker riêng.

## 9. Comment và marker phải phù hợp định dạng file

Markup comment được viết theo cú pháp comment của ngôn ngữ hoặc định dạng chứa snippet.

| Định dạng | Marker region và markup comment |
| --- | --- |
| Java | `// @start region="name"`, `// @end region="name"`, `// @highlight ...` |
| Properties | `# @start region="name"`, `# @end region="name"`, `# @replace ...` |
| XML | `<!-- @start region="name" -->`, `<!-- @end region="name" -->` |
| HTML | `<!-- @start region="name" -->`, `<!-- @end region="name" -->` |

Với file không phải Java, dùng thuộc tính `file` để tham chiếu và đặt `lang` phù hợp nếu cần chỉ định ngôn ngữ hiển thị. Đừng chèn cú pháp comment Java vào properties hoặc XML nếu nó không phải comment hợp lệ của định dạng.

Ví dụ file properties:

~~~properties
# @start region="server"
# @highlight substring="localhost" type=bold :
server.host=localhost
server.port=8080
server.protocol=https
# @end region="server"
~~~

Javadoc:

~~~java
{@snippet lang="properties" file="application.properties" region="server"}
~~~

Dòng `# @highlight ... :` là markup comment đứng riêng. Dấu hai chấm chuyển action sang dòng thuộc tính ngay sau nó; comment và marker không xuất hiện trong khối mã hiển thị.

Lưu ý: cú pháp comment của từng định dạng có thể có quy tắc riêng về vị trí comment. Hãy đặt markup comment ở vị trí hợp lệ và kiểm tra output thực tế. Với properties, ký tự `#` bắt đầu comment; không dùng `//` như trong Java.

## 10. Đường dẫn file và cấu hình tìm external snippet

File external thường được đặt trong thư mục `snippet-files` dưới package chứa class có documentation comment.

Cấu trúc ví dụ:

~~~text
src/
└── demo/
    ├── TextApiDoc.java
    └── snippet-files/
        ├── TextExamples.java
        └── application.properties
~~~

Trong Javadoc:

~~~java
{@snippet file="TextExamples.java" region="text-flow"}
{@snippet file="application.properties" region="server"}
~~~

Chạy Javadoc từ thư mục gốc:

~~~bash
javadoc -d docs -sourcepath src demo
~~~

Nếu file external nằm ở một thư mục khác, dùng `--snippet-path`:

~~~text
project/
├── src/
│   └── demo/
│       └── TextApiDoc.java
└── snippets/
    └── TextExamples.java
~~~

~~~bash
javadoc -d docs -sourcepath src --snippet-path snippets demo
~~~

Đường dẫn trong thuộc tính `file` là đường dẫn tương đối theo thư mục snippet được tìm kiếm. Không dùng đường dẫn tuyệt đối tùy tiện trong tag.

## 11. Quy trình kiểm chứng đầu ra

Khi kết hợp extraction và markup, cần xác nhận cả ba việc: chọn đúng region, áp dụng đúng markup và source vẫn phù hợp mục tiêu.

### 11.1. Biên dịch file external Java

Từ thư mục gốc:

~~~bash
javac -d out src/demo/snippet-files/TextExamples.java
~~~

Nếu lệnh thành công, source external là một compilation unit Java hợp lệ. Markup comment không thay đổi cú pháp chương trình vì compiler xem chúng là comment.

### 11.2. Sinh Javadoc

~~~bash
javadoc -d docs -sourcepath src demo
~~~

Nếu Javadoc không tìm thấy file, kiểm tra:

- File có nằm trong `snippet-files` đúng package không?
- Thuộc tính `file` có đúng tên và phần mở rộng không?
- Nếu dùng thư mục riêng, `--snippet-path` đã được truyền chưa?
- Tên region trong `{@snippet}` có khớp `@start`/`@end` không?

### 11.3. Kiểm tra HTML

Mở `docs/demo/TextApiDoc.html` và xác nhận:

1. Chỉ nội dung nằm giữa `@start region="text-flow"` và `@end region="text-flow"` được trích.
2. Marker chọn vùng không xuất hiện trong khối mã.
3. `strip()` có hyperlink và URL đích trỏ đến declaration `String.strip()`.
4. Literal `"placeholder"` được thay bằng `...`.
5. Chữ `normalized` được làm nổi bật.
6. Các dòng ngoài vùng `text-flow` không xuất hiện trong snippet.
7. File external trên đĩa vẫn giữ source gốc.

Trong trình duyệt, có thể dùng Inspect để xem anchor và thuộc tính `href`. Để kiểm tra nội dung replacement, so sánh HTML với file external ban đầu.

### 11.4. Nếu một markup không hoạt động

- **Không có highlight:** kiểm tra selector, chính tả và dòng chứa markup comment.
- **Không có hyperlink:** kiểm tra `target`, parameter list nếu method overloaded và link trong HTML.
- **Không có replacement:** kiểm tra `substring`/`regex` có khớp chính xác văn bản source không, và replacement có hợp lệ không.
- **Sai đoạn được trích:** kiểm tra `region` trong `{@snippet}` với cặp `@start`/`@end`.
- **Markup comment xuất hiện như code:** kiểm tra comment syntax có đúng ngôn ngữ và tên markup tag có được nhận diện không.

Javadoc báo lỗi khi markup tag đã nhận diện nhưng thuộc tính hoặc cú pháp không hợp lệ. Nếu comment bắt đầu bằng một tên không được nhận diện như markup tag, nó có thể được giữ lại như comment thông thường trong output. Vì vậy, kiểm tra spelling của tag và sinh lại tài liệu sau mỗi lần sửa.

## 12. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Dùng `@highlight region` để chọn vùng external cho `{@snippet}`. | Region của action và region được trích có vai trò khác nhau. | Dùng `@start region`/`@end region` cho vùng external; đặt markup action bên trong. |
| Đặt markup comment ngoài vùng được trích. | Markup không nằm trong nội dung snippet đang chọn. | Di chuyển comment vào bên trong cặp marker external phù hợp. |
| Dùng sai tên ở thuộc tính `region`. | Javadoc không tìm được vùng có tên tương ứng. | Đối chiếu `@start`, `@end` và `{@snippet region=...}`. |
| Dùng `@replace` nhưng selector không khớp. | Chuỗi source có thể khác dấu nháy, khoảng trắng hoặc chữ hoa/thường. | Sao chép đúng chuỗi cần thay hoặc dùng regex được kiểm tra. |
| Dùng `@link` nhưng target sai overload. | Tên method đúng nhưng parameter list không khớp declaration. | Kiểm tra kiểu và thứ tự tham số; dùng tên class đầy đủ. |
| Nghĩ replacement sửa file external. | Replacement chỉ tác động lên bản HTML. | Mở file source để xác nhận nó còn nguyên. |
| Dùng replacement để che secret. | Giá trị gốc vẫn tồn tại trong file external. | Loại bỏ secret khỏi source trước khi sinh tài liệu. |
| Dùng `//` trong properties. | Properties dùng `#` để bắt đầu comment. | Dùng `# @start`, `# @end` và `# @highlight`/`# @replace` khi phù hợp. |
| Chỉ kiểm tra source mà không mở HTML. | Source không cho biết chắc Javadoc đã trích và định dạng đúng chưa. | Sinh Javadoc và kiểm tra anchor, highlight, replacement trong HTML. |

## 13. Bài tập tự đánh giá

### Bài 1 — Chọn region và làm nổi bật

File external:

~~~java
// @start region="usage"
String normalized = input.strip();
System.out.println(normalized);
// @end region="usage"
~~~

Muốn trích vùng và làm nổi bật `normalized` trên dòng in kết quả. Viết tag `{@snippet}` và markup comment thế nào?

**Đáp án:**

~~~java
// @start region="usage"
String normalized = input.strip();
System.out.println(normalized); // @highlight substring="normalized" type=bold
// @end region="usage"
~~~

~~~java
{@snippet file="Examples.java" region="usage"}
~~~

### Bài 2 — Thêm liên kết API

Muốn liên kết `strip()` đến method của `java.lang.String`:

**Đáp án:**

~~~java
String normalized = input.strip(); // @link substring="strip()" target="java.lang.String#strip()"
~~~

### Bài 3 — Thay placeholder mà vẫn giữ source hợp lệ

Source có:

~~~java
String token = "placeholder";
~~~

Muốn HTML hiển thị dấu ba chấm:

**Đáp án:**

~~~java
String token = "placeholder"; // @replace substring='"placeholder"' replacement="..."
~~~

### Bài 4 — Vì sao snippet không được trích?

Documentation comment dùng:

~~~java
{@snippet file="Examples.java" region="main"}
~~~

Nhưng file external chỉ có `@start region="usage"` và `@end region="usage"`.

**Đáp án:** Tên region không khớp. Đổi thuộc tính thành `region="usage"` hoặc đổi tên marker ở file external để thống nhất.

### Bài 5 — Phân biệt hai loại region

`@start region="example"` và `@highlight region="focus"` có cùng nhiệm vụ không?

**Đáp án:** Không. `@start region` đánh dấu nội dung external để `{@snippet region=...}` trích. `@highlight region` mở phạm vi mà action highlight tìm selector. Hai region có thể cùng tồn tại nhưng nên dùng tên riêng.

### Bài 6 — Kiểm tra source và output

Sau khi Javadoc sinh HTML, dòng `String token = ...;` không biên dịch được. Điều này có chứng minh file external sai không?

**Đáp án:** Không. `@replace` có thể thay literal hợp lệ trong source bằng dấu ba chấm ở HTML. Hãy biên dịch file external gốc bằng `javac` và kiểm tra riêng output bằng `javadoc`.

## Tổng kết

- Thuộc tính `region` của `{@snippet file=...}` chọn đoạn external được hiển thị; cặp `@start region`/`@end region` đánh dấu đoạn đó.
- Markup comment `@highlight`, `@link` và `@replace` có thể được đặt bên trong vùng được trích để điều chỉnh cách trình bày.
- `@highlight` chọn văn bản bằng `substring` hoặc `regex`; `@link` dùng `target` để liên kết đến declaration API; `@replace` thay placeholder trong HTML.
- Region trích xuất và region của markup action có nhiệm vụ khác nhau. Khi kết hợp, đặt tên và marker rõ ràng để tránh chọn nhầm phạm vi.
- Một file external có thể có nhiều region và mỗi region có markup riêng; nhiều `{@snippet}` có thể tham chiếu cùng file ở các phần tài liệu khác nhau.
- Markup comment phải dùng đúng comment syntax của ngôn ngữ/định dạng chứa snippet.
- `@replace` không sửa source và không che bí mật; source gốc vẫn được giữ.
- Dùng `javac` để kiểm tra file Java external, `javadoc` để sinh tài liệu và đọc HTML để xác nhận region, highlight, hyperlink và replacement.

## Nguồn tham khảo chính thức

1. [Oracle — JavaDoc Guide: Snippets, JDK 26, mục External Snippets](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html): kết hợp vùng external được chọn với markup comment để sửa văn bản hiển thị.
2. [Oracle — JavaDoc Documentation Comment Specification, JDK 26, mục External snippets, Markup tags và Regions](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html): cú pháp external snippet, các markup tag và vai trò của region.
3. [Oracle — JavaDoc Guide, JDK 26, chương External Snippets](https://docs.oracle.com/en/java/javase/26/javadoc/javadoc-guide.pdf): ví dụ chọn named region và đặt `@replace` bên trong vùng external.
4. [OpenJDK — JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): tính năng snippet được đưa vào Java 18 và tiếp tục được hỗ trợ trong JDK hiện đại.
