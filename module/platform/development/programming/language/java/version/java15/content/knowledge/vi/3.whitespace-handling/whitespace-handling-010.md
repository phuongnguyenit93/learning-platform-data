# Java 15 — Cảnh báo compiler với `-Xlint:text-blocks`: kiểm soát khoảng trắng trong Text Blocks

## 1. Vấn đề cần nhận biết

**Text Blocks** trở thành tính năng chính thức từ Java 15 và vẫn được sử dụng trong Java hiện đại để viết chuỗi nhiều dòng rõ ràng hơn, chẳng hạn JSON, SQL, HTML, log template và dữ liệu kiểm thử. Giá trị của một text block vẫn là `String`. Trình biên dịch chuẩn hóa dòng, loại **khoảng trắng thụt đầu dòng chỉ để trình bày** (*incidental indentation*) và loại khoảng trắng cuối dòng trước khi xử lý các escape sequence.

Chính vì dấu cách và tab thường không hiển thị rõ trong editor, text block có thể **biên dịch thành công nhưng tạo chuỗi khác ý định**. Javac cung cấp cảnh báo riêng để phát hiện hai kiểu rủi ro này:

~~~bash
javac -Xlint:text-blocks TenLop.java
~~~

Tùy chọn `-Xlint:text-blocks` **vẫn có trong tài liệu `javac` của các JDK hiện đại**, không phải cơ chế preview hoặc cách viết đã lỗi thời. Nó áp dụng lúc **biên dịch bằng `javac`**, không phải tham số cho lệnh `java` chạy chương trình.

Mục tiêu sau bài:

- Hiểu vì sao khoảng trắng hiển thị trong nguồn và khoảng trắng nằm trong `String` có thể khác nhau.
- Phân biệt hai thông báo `[text-blocks] inconsistent white space indentation` và `[text-blocks] trailing white space will be removed`.
- Bật và đọc đúng cảnh báo bằng `javac`; biết khi nào `-Werror` làm quá trình build thất bại.
- Sửa nguồn để vừa tránh cảnh báo vừa giữ **đúng nội dung chuỗi cần thiết**, đặc biệt bằng escape `\s`.
- Tích hợp kiểm tra vào bước biên dịch của dự án và đánh giá đúng giới hạn của lint.

## 2. Cơ chế khoảng trắng: tại sao compiler cần cảnh báo?

Một text block có cú pháp ba dấu nháy kép mở `"""`, **ngay sau đó phải có xuống dòng**; ba dấu nháy kép đóng kết thúc nội dung. Ví dụ:

~~~java
String message = """
    Xin chào,
      Java!
    """;
~~~

Đây là **đoạn mã minh họa bên trong một phương thức**, không phải tệp Java độc lập. Tại đây, dòng thứ hai có thêm hai dấu cách đầu dòng so với dòng thứ nhất; khoảng thụt chung sẽ được loại, hai dấu cách thêm có chủ đích vẫn nằm trong chuỗi. Kết quả tương ứng:

~~~text
Xin chào,
  Java!
~~~

Với text block, quá trình xử lý quan trọng gồm:

1. Chuẩn hóa line terminator của nguồn về `\n`.
2. Xác định và loại phần thụt đầu dòng chung chỉ để căn mã nguồn. Những dòng có nội dung và vị trí dấu đóng ảnh hưởng tới lề được loại.
3. Loại các dấu cách thừa ở **cuối dòng nguồn** trong text block.
4. Diễn giải escape sequence, ví dụ `\n`, `\t`, `\s` và dấu `\` dùng để nối dòng nguồn.

**Điểm dễ nhầm nhất:** một ký tự tab ở đầu dòng **được tính là một ký tự khoảng trắng** khi xử lý indent; editor có thể vẽ tab rộng bằng bốn hoặc tám cột. Vì thế nhìn nhiều dòng thẳng hàng trên màn hình không chứng minh rằng chúng có cùng độ thụt theo cách compiler đếm.

Một dòng có thêm **space** để thể hiện cấu trúc nhiều cấp (ví dụ JSON lồng nhau) là hợp lệ; `-Xlint:text-blocks` không ép tất cả dòng phải có độ thụt bằng nhau. Điều cần tránh là hỗn hợp khoảng trắng nguồn làm quy tắc cắt lề cho ra dữ liệu bất ngờ.

## 3. Hai loại cảnh báo của `-Xlint:text-blocks`

| Cảnh báo của `javac` | Nguyên nhân điển hình | Nguy cơ đối với chuỗi kết quả | Cách xử lý |
| --- | --- | --- | --- |
| `inconsistent white space indentation` | Dùng các ký tự thụt dòng không nhất quán, thường là tab lẫn space | Một số dòng còn nhiều space, một số dòng bị cắt khác kỳ vọng | Thống nhất quy tắc indent của text block; dùng space nhất quán hoặc tab nhất quán theo chuẩn dự án |
| `trailing white space will be removed` | Có khoảng trắng thật ở cuối dòng bên trong text block | Khoảng trắng cuối dòng trong nguồn bị compiler loại bỏ | Xóa khoảng trắng dư; nếu muốn giữ nó trong chuỗi, dùng `\s` hoặc escape thích hợp |

Đây là **warning**, nên khi chỉ dùng `-Xlint:text-blocks`, việc phát hiện cảnh báo **không tự làm lệnh `javac` thất bại**. Chương trình vẫn có thể biên dịch và chạy, nhưng dữ liệu sinh ra có thể sai. Thông báo thường mang nhãn `[text-blocks]`, và vị trí chỉ thị có thể đặt tại **dấu mở text block**, thay vì trỏ trực tiếp vào dấu cách vô hình nằm cuối một dòng.

### 3.1. Cảnh báo indent không nhất quán

Giả sử một text block được trình bày như sau. Đây là **sơ đồ hiển thị khoảng trắng, không phải mã Java sao chép để biên dịch**:

~~~text
String x = """
················alpha··
⇥beta
················gamma
················""";
~~~

Trong sơ đồ, `·` tượng trưng cho **một space thật** và `⇥` tượng trưng cho **một tab thật**. `alpha` và `gamma` có 16 space thụt đầu dòng, nhưng `beta` có một tab. Sau khi compiler tính tab là một ký tự và cắt lề chung ngắn nhất, `alpha` và `gamma` còn **15 space** ở đầu, trong khi `beta` không còn space đầu. Đó là lỗi dữ liệu chứ không chỉ là lỗi trình bày.

Nếu cả ba dòng đều dùng 16 space giống nhau trước `alpha`, `beta` và `gamma`, chuỗi có thể trở thành `"alpha\nbeta\ngamma\n"` như mong đợi. Không cần giữ 16 space đầu dòng trong runtime `String` chỉ vì muốn Java source được căn đẹp.

### 3.2. Cảnh báo khoảng trắng cuối dòng sẽ bị bỏ

Trong sơ đồ trên, hai ký hiệu `··` ngay sau `alpha` đại diện cho **hai space ở cuối dòng nguồn**. Chúng bị compiler loại khỏi nội dung text block. Đây là chủ đích thiết kế để việc editor tự động dọn trailing whitespace không vô tình thay đổi giá trị chuỗi.

Hệ quả:

- Nếu hai space chỉ là do thao tác copy/paste hoặc editor, xóa chúng đi là cách sửa đúng.
- Nếu định dạng dữ liệu **thực sự cần** một space cuối dòng, viết `alpha\s` trong text block. Escape `\s` được xử lý sau bước loại khoảng trắng nguồn nên tạo **đúng một space trong `String`**.
- Nếu cần một tab có ý nghĩa trong dữ liệu, có thể dùng escape `\t` ở vị trí nội dung mong muốn. Không nên dùng tab để căn lề nguồn rồi trông chờ tab còn nguyên sau khử indent.
- Viết `\u0020` không phải giải pháp thay `\s`: Unicode escape được xử lý rất sớm trong quá trình đọc nguồn, nên space sinh ra vẫn có thể bị xem là trailing whitespace và bị loại.

## 4. Thí nghiệm có thể chạy: tái hiện đúng hai warning

Để bài thực hành có thể sao chép trên editor tự xóa trailing space, ta tạo tệp ví dụ bằng một chương trình Java nhỏ. Chương trình **chủ động ghép hai space** sau `alpha` và **ký tự tab** trước `beta`, nhờ vậy không cần cất dấu cách vô hình trong đoạn Markdown.

Tạo một thư mục thực hành mới rồi lưu tệp **`PrepareWarningSample.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class PrepareWarningSample {
    public static void main(String[] args) throws Exception {
        String source = String.join("\n",
                "public class WarningSample {",
                "    public static void main(String[] args) {",
                "        String x = \"\"\"",
                "                alpha" + "  ",
                "\t" + "beta",
                "                gamma",
                "                \"\"\";",
                "        System.out.println(x.replace(\" \", \".\").replace(\"\\n\", \"<LF>\"));",
                "    }",
                "}") + "\n";

        Files.writeString(
                Path.of("WarningSample.java"), source,
                StandardCharsets.UTF_8);
        System.out.println("Wrote WarningSample.java");
    }
}
~~~

Đây là chương trình Java độc lập: nó tạo `WarningSample.java` trong **thư mục làm việc hiện tại**. Thực hành trong thư mục mới để tên tệp không trùng dự án khác. Với JDK 17 trở lên (ví dụ bên dưới được kiểm tra bằng compiler mới hơn với `--release 17`), chạy tuần tự:

~~~bash
javac --release 17 PrepareWarningSample.java
java PrepareWarningSample
javac --release 17 -Xlint:text-blocks WarningSample.java
java WarningSample
~~~

Lệnh `java PrepareWarningSample` in:

~~~text
Wrote WarningSample.java
~~~

Lệnh `javac ... -Xlint:text-blocks` sẽ hiển thị **hai thông báo cốt lõi** sau (dòng nguồn, cột đánh dấu và đường dẫn có thể khác nhau theo máy/JDK):

~~~text
warning: [text-blocks] inconsistent white space indentation
warning: [text-blocks] trailing white space will be removed
2 warnings
~~~

Lệnh `java WarningSample` sau đó in:

~~~text
...............alpha<LF>beta<LF>...............gamma<LF>
~~~

Trong output này, dấu chấm thay cho các space thật, `<LF>` thay cho ký tự xuống dòng. Chính xác có **15 dấu chấm** trước `alpha` và **15 dấu chấm** trước `gamma`; trước `beta` không có dấu chấm. Hai dấu cách cuối `alpha` đã biến mất. Điều này chứng minh warning liên quan trực tiếp tới kết quả runtime.

**Thử thêm:** chạy `javac --release 17 WarningSample.java` khi không bật nhóm lint. Với cấu hình mặc định của `javac` hiện tại, hai warning này không xuất hiện, nhưng kết quả `String` vẫn như cũ. Bật lint chỉ giúp **phát hiện**, không chỉnh sửa dữ liệu và không thay đổi thuật toán xử lý text block.

## 5. Mã đúng: giữ indent nhất quán và giữ space khi thực sự cần

Tạo tệp độc lập **`TextBlockLintClean.java`**:

~~~java
public class TextBlockLintClean {
    public static void main(String[] args) {
        String text = """
            alpha\s
            beta
            """;

        System.out.println(text.equals("alpha \nbeta\n"));
        System.out.println(
                text.replace(" ", ".").replace("\n", "|"));

        String nested = """
            red
              green
            blue
            """;
        System.out.println(
                nested.replace(" ", ".").replace("\n", "|"));
    }
}
~~~

~~~bash
javac --release 17 -Xlint:text-blocks TextBlockLintClean.java
java TextBlockLintClean
~~~

Lần biên dịch này không phát sinh warning `[text-blocks]`. Kết quả chạy:

~~~text
true
alpha.|beta|
red|..green|blue|
~~~

Giải thích:

- `alpha\s` chứa đúng **một space cuối dòng** nhờ escape `\s`; chuỗi bằng `"alpha \nbeta\n"`.
- `alpha.|beta|` được in ra bằng cách biến space thành dấu chấm và `\n` thành ký hiệu `|`, giúp phát hiện những khoảng trắng mà cách in thông thường khó nhìn thấy.
- Dòng `green` thụt hơn hai space so với `red` và `blue`, nên chuỗi chứa `..green`; đây là **indent nội dung có chủ đích**, không phải cảnh báo.
- Dấu đóng `"""` nằm trên dòng riêng nên kết quả các text block có ký tự `\n` cuối. Nếu payload yêu cầu không có newline cuối, cần thiết kế vị trí dấu đóng hoặc xử lý chuỗi có chủ đích, rồi kiểm tra bằng `equals`.

**Cách sửa tình huống ở phần 4:** thay tab trước `beta` bằng số space thụt đầu dòng đúng như các dòng còn lại và xóa hai space cuối `alpha`. Nếu yêu cầu nghiệp vụ phải có hai space cuối `alpha`, thay bằng `\s\s` và kiểm tra output bằng assertion; đừng giữ chúng dưới dạng trailing whitespace vô hình.

## 6. Sử dụng lint trong quy trình biên dịch hiện đại

### 6.1. Những tùy chọn `javac` liên quan

| Lệnh/tùy chọn | Tác dụng |
| --- | --- |
| `javac -Xlint:text-blocks File.java` | Bật chính nhóm cảnh báo về khoảng trắng text block |
| `javac -Xlint:all File.java` | Bật tất cả nhóm cảnh báo lint, có thể có nhiều nhóm không liên quan |
| `javac -Xlint:all,-text-blocks File.java` | Bật các nhóm lint khác nhưng loại trừ `text-blocks`; chỉ dùng khi có lý do cụ thể |
| `javac -Xlint:text-blocks -Werror File.java` | Đưa warning thành lỗi build nếu có warning; hữu ích cho kiểm tra chất lượng đã thiết lập |
| `javac --release 17 -Xlint:text-blocks File.java` | Vừa kiểm tra tính tương thích API/ngôn ngữ Java 17 vừa bật cảnh báo text block trên JDK compiler hỗ trợ |

Cảnh báo `-Xlint:text-blocks` thuộc khâu **compile**, nên đừng nhập nó sau lệnh `java`. Với cú pháp `-Xlint:all,-text-blocks`, dấu trừ nằm **bên trong danh sách nhóm lint**, khác với việc bỏ toàn bộ kiểm tra.

### 6.2. Khi cần build thất bại vì warning

Nếu dự án đã thống nhất codebase phải sạch lint, có thể thử:

~~~bash
javac --release 17 -Xlint:text-blocks -Werror WarningSample.java
~~~

Với tệp sinh ở phần 4, `javac` in hai warning rồi đưa ra lỗi tương tự:

~~~text
error: warnings found and -Werror specified
1 error
2 warnings
~~~

Khi có `-Werror`, lệnh biên dịch trả về exit code khác 0. Nội dung đường dẫn và vị trí warning thay đổi theo môi trường; thông điệp và hành vi ở trên là phần đáng kiểm tra. Sau khi sửa indent/trailing space, build cần chạy lại với **cùng flags** để xác nhận không còn warning. Không nên tắt `-Xlint:text-blocks` chỉ để làm mất dấu hiệu rằng literal dữ liệu đang khác ý định.

### 6.3. Tích hợp vào Gradle hoặc Maven

Trong dự án Gradle dùng **Groovy DSL**, đoạn cấu hình sau thêm tham số cho các tác vụ biên dịch Java. Đây là **một đoạn cấu hình `build.gradle`**, không phải một dự án độc lập:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-Xlint:text-blocks")
}
~~~

Khi dùng Maven Compiler Plugin, có thể truyền cùng tùy chọn trong phần `configuration` của plugin (đoạn XML sau nằm **bên trong khai báo `maven-compiler-plugin`**):

~~~xml
<configuration>
    <compilerArgs>
        <arg>-Xlint:text-blocks</arg>
    </compilerArgs>
</configuration>
~~~

Hai cấu hình chỉ **bật chẩn đoán**, không tự sửa tệp. Trong CI, cân nhắc `-Werror` sau khi đã đánh giá các warning của toàn bộ dự án và xác định chính sách build. Khi dùng Gradle toolchains hoặc Maven toolchains, kiểm tra JDK **thực sự dùng để compile**, không chỉ JDK dùng để chạy ứng dụng; bộ cảnh báo phụ thuộc phiên bản compiler.

## 7. Phân biệt các tình huống thường gặp

**Tình huống A — source trông đều mà chuỗi bị lệch.** Bật chế độ hiển thị khoảng trắng trong IDE, kiểm tra tab/space đầu dòng và dấu đóng `"""`. Đừng chỉ tin vào số cột hiển thị; một tab có thể được editor mở rộng thành nhiều cột nhưng compiler đếm một ký tự.

**Tình huống B — payload phải có khoảng trắng cuối dòng.** Viết `\s` ở vị trí cần giữ và dùng test `equals(...)` với chuỗi kỳ vọng. `-Xlint:text-blocks` không phải bộ chuẩn hóa hoặc formatter, nên không thay thế việc kiểm tra nội dung dữ liệu.

**Tình huống C — các dòng cần độ thụt khác nhau.** Hoàn toàn hợp lệ khi dữ liệu như JSON, YAML hoặc đoạn code cần indent lồng nhau. Hãy giữ *phần indent chung* nhất quán; các khoảng trắng bổ sung cho cấu trúc nội dung vẫn có ý nghĩa. Cảnh báo không có nghĩa mọi dòng phải thụt ngang nhau.

**Tình huống D — không thấy warning nhưng có lỗi.** Nhóm lint này chỉ nhận diện các rủi ro khoảng trắng nhất định. Nó không phát hiện mọi sai lệch về newline, ký tự escape, JSON/SQL không hợp lệ, SQL injection hay vấn đề encoding. Việc quên xuống dòng bắt buộc sau dấu mở `"""` là **lỗi cú pháp compiler**, không cần `-Xlint:text-blocks` mới phát hiện.

**Tình huống E — người khác thay editor hoặc formatter.** Thống nhất quy ước indent bằng editor settings/formatter; thêm kiểm thử so sánh đúng giá trị `String` đối với payload nhạy cảm về khoảng trắng. Chạy lint trong build giúp phát hiện khi copy/paste làm lẫn tab và space hoặc thêm trailing whitespace.

**Tình huống F — hiểu nhầm quan hệ với `String.stripIndent()`.** `-Xlint:text-blocks` kiểm tra **cú pháp nguồn lúc biên dịch**. `String.stripIndent()` là một phương thức xử lý **chuỗi ở runtime**, không phải tùy chọn chữa warning của compiler. Sửa text block gốc khi bạn kiểm soát mã nguồn, thay vì tự động thay đổi payload ở runtime rồi che giấu lỗi định dạng.

## 8. Checklist khi review pull request có text block

1. **Cùng quy tắc indent:** phần khoảng trắng đầu dòng của block không bị trộn tab/space theo cách làm cắt lề sai.
2. **Không có trailing whitespace vô hình:** nếu khoảng trắng cuối dòng có ý nghĩa, đã dùng escape như `\s` và kiểm tra kết quả.
3. **Đúng chuỗi thực tế:** có test `equals` hoặc đối chiếu byte khi dữ liệu nhạy cảm về space/newline.
4. **Đã bật lint:** `javac -Xlint:text-blocks` hoặc cấu hình tương ứng của build tool có hiệu lực.
5. **Không đồng nhất warning với lỗi biên dịch:** warning bình thường vẫn cho phép compile; chỉ có `-Werror` hoặc chính sách build khác mới khiến build fail vì warning.
6. **Đúng phiên bản JDK:** flags được thử trên JDK compiler đang dùng trong CI/production; Text Blocks là tính năng chính thức, không dùng tùy chọn preview.

## 9. Tự kiểm tra

**1. Vì sao text block thụt một tab có thể làm kết quả khác 4 space dù editor hiển thị giống nhau?**  
Vì compiler đếm tab là **một ký tự whitespace** khi tính incidental indent, còn editor có thể hiển thị tab rộng bằng nhiều cột.

**2. `-Xlint:text-blocks` có tự sửa khoảng trắng của chuỗi không?**  
Không. Nó **báo warning** khi phát hiện rủi ro; chính các quy tắc text block mới quyết định nội dung `String`.

**3. Muốn giữ đúng một space cuối dòng mà không dùng trailing whitespace vô hình, viết gì?**  
Viết `\s` trước dòng mới, ví dụ `alpha\s`.

**4. Có thể dùng `\u0020` thay `\s` để bảo vệ trailing space không?**  
Không nên. Unicode escape được xử lý sớm, nên space tạo ra vẫn có thể bị loại trong bước xử lý khoảng trắng text block.

**5. Lệnh nào khiến hai warning trong thí nghiệm trở thành lỗi build?**  
`javac --release 17 -Xlint:text-blocks -Werror WarningSample.java`.

## 10. Tài liệu chính thức để tra cứu

- [Oracle Java SE 25 — Text Blocks](https://docs.oracle.com/en/java/javase/25/language/text-blocks.html): phần **Incidental White Space**, **Trailing White Space**, và **Detecting Potential Issues with White Space** giải thích cơ chế cùng hai cảnh báo `-Xlint:text-blocks`.
- [Oracle Java SE 25 — Programmer's Guide to Text Blocks](https://docs.oracle.com/en/java/javase/25/text-blocks/index.html): các ví dụ và hướng dẫn về indent, tab, line terminator, `\s`.
- [Oracle Java SE 26 — `javac` Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): khóa lint `text-blocks`, nhóm `-Xlint` và tùy chọn `-Werror`.
- [OpenJDK JEP 378 — Text Blocks](https://openjdk.org/jeps/378): đặc tả tính năng chính thức từ Java 15.
