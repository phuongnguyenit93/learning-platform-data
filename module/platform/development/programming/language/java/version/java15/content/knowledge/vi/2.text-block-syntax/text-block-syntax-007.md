# Giá trị `String`, tính bất biến và cơ chế `intern` (Java 15+)

> **Ngữ cảnh:** Bài học thuộc chủ đề **Cú pháp text block**. Text block làm cho chuỗi nhiều dòng dễ đọc hơn, nhưng giá trị tạo ra vẫn là `java.lang.String` thông thường. Nội dung dưới đây tập trung vào ngữ nghĩa giá trị, tính bất biến và string pool; các quy tắc này vẫn áp dụng trên Java hiện đại.

## Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích giá trị của một `String`, kể cả khoảng trắng và ký tự xuống dòng trong text block.
2. Phân biệt so sánh **nội dung** bằng `equals()` với so sánh **tham chiếu** bằng `==`.
3. Hiểu tại sao một `String` bất biến dù biến chứa nó có thể nhận giá trị mới.
4. Giải thích string pool, chuỗi hằng tại thời điểm biên dịch và kết quả của `intern()`.
5. Tránh các lỗi thường gặp khi xử lý text block, so sánh chuỗi hoặc cố gắng tối ưu bằng `intern()`.

## 1. Giá trị `String` là gì?

`String` biểu diễn một **chuỗi ký tự bất biến**. Về mặt API, độ dài và các phương thức như `charAt()` được xác định theo các *đơn vị mã UTF-16* (UTF-16 code units). Điều này mô tả cách API biểu diễn chuỗi, không buộc một JVM phải lưu đối tượng trong bộ nhớ theo một cấu trúc nội bộ cố định.

Giá trị chuỗi bao gồm **từng ký tự chính xác**: chữ cái, dấu cách, tab, dấu tiếng Việt và ký tự xuống dòng. Vì vậy, hai chuỗi trông giống nhau trong giao diện vẫn có thể khác giá trị nếu một chuỗi có khoảng trắng hoặc newline thừa.

Trong Java 15 trở lên, hai cú pháp dưới đây đều có kiểu `String`:

~~~java
String oneLine = "Xin chào";
String manyLines = """
    Xin chào
    Java
    """;
~~~

Text block **không phải** một kiểu dữ liệu hay đối tượng đặc biệt. Nó là một cách viết literal `String`, tiện cho SQL, JSON, HTML, thông báo nhiều dòng và các văn bản nhiều dòng khác. Các phương thức `equals()`, `length()`, `replace()`, `intern()` hoạt động trên text block như với chuỗi viết bằng dấu ngoặc kép thông thường.

### 1.1. Text block và giá trị ký tự chính xác

Ví dụ độc lập sau chạy trên **Java 17+** và vẫn đúng với Java hiện đại.

**Tệp `TextBlockValueDemo.java`**

~~~java
public class TextBlockValueDemo {
    public static void main(String[] args) {
        String block = """
            user=Lan
            level=15
            """;

        String escaped = "user=Lan\nlevel=15\n";

        String withoutFinalNewline = """
            user=Lan
            level=15""";

        System.out.println(block.equals(escaped));
        System.out.println(block == escaped);
        System.out.println(block.endsWith("\n"));
        System.out.println(
            withoutFinalNewline.equals("user=Lan\nlevel=15")
        );
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 TextBlockValueDemo.java
java TextBlockValueDemo
~~~

**Kết quả chính xác:**

~~~text
true
true
true
true
~~~

Giải thích:
- Dấu mở `"""` phải được theo sau bởi dấu xuống dòng trong mã nguồn. Dấu xuống dòng ngay sau dấu mở **không tự trở thành ký tự đầu tiên** của giá trị.
- Với dấu đóng nằm trên một dòng riêng như `block`, giá trị chứa newline cuối cùng, tương đương `"user=Lan\nlevel=15\n"`.
- Với dấu đóng ngay sau `level=15`, giá trị không có newline cuối cùng.
- Kết quả `block == escaped` là `true` vì **cả hai đều là literal `String`** có cùng nội dung và được intern. Đây là quy tắc dành cho literal, **không phải** lý do để dùng `==` so sánh chuỗi nói chung.

Khi xác định giá trị text block, Java xử lý theo thứ tự: **chuẩn hóa CR/CRLF thành LF (`\n`)**, **bỏ khoảng trắng thụt lề phụ và trailing whitespace không cần thiết**, sau đó **diễn giải escape sequence**. Vì thế không nên suy ra giá trị bằng cách nhìn các khoảng trắng trong editor mà bỏ qua quy tắc text block.

Nếu cần giữ **dấu cách cuối dòng** trong text block, có thể dùng `\s` (escape biểu diễn một space). Ví dụ dưới đây là một đoạn mã nằm trong phương thức Java:

~~~java
String withTrailingSpace = """
    A\s
    B
    """;

System.out.println(withTrailingSpace.equals("A \nB\n")); // true
~~~

Dấu `\s` được diễn giải sau bước loại bỏ trailing whitespace nên space đó được giữ lại. Nếu cần giữ chính xác khoảng trắng hoặc cách xuống dòng vì yêu cầu giao thức, hãy kiểm tra giá trị bằng `equals()` hay test thay vì chỉ đọc mã nguồn.

## 2. Tính bất biến (*immutability*) của `String`

Một khi đối tượng `String` đã được tạo, **nội dung của đối tượng không thể bị sửa tại chỗ** qua API công khai. Các thao tác thay đổi nội dung như `concat()`, `replace()`, `substring()`, `strip()` hay `toUpperCase()` trả về một giá trị `String`; đối tượng ban đầu vẫn giữ nguyên. Tùy đầu vào, một phương thức có thể trả về chính đối tượng cũ nếu giá trị không đổi; vì vậy cũng không nên khẳng định mọi lần gọi đều cấp phát đối tượng mới.

**Tệp `ImmutableStringDemo.java`**

~~~java
import java.util.Locale;

public class ImmutableStringDemo {
    public static void main(String[] args) {
        String original = "Java";
        String updated = original.concat(" 15").replace("15", "17");
        String upper = original.toUpperCase(Locale.ROOT);

        System.out.println(original);
        System.out.println(updated);
        System.out.println(upper);

        String template = """
            Chào %s!
            """;
        String message = template.formatted("Java");

        System.out.println(template.contains("%s"));
        System.out.println(message.equals("Chào Java!\n"));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ImmutableStringDemo.java
java ImmutableStringDemo
~~~

**Kết quả chính xác:**

~~~text
Java
Java 17
JAVA
true
true
~~~

`formatted()` thay thế tham số trong **chuỗi kết quả**, không sửa text block `template`. Đây là lý do có thể tái sử dụng một template an toàn cho nhiều dữ liệu.

**Phân biệt đối tượng và biến tham chiếu:**

~~~java
String name = "Lan";
name = name + " Anh"; // biến name trỏ sang giá trị mới
~~~

Biến `name` được gán lại, nhưng đối tượng `String` chứa `"Lan"` không bị chỉnh sửa. Từ khóa `final` chỉ hạn chế **gán lại biến** (nếu có); tính bất biến là đặc tính của **đối tượng `String`**, kể cả khi biến không có `final`.

Tính bất biến giúp chuỗi dễ chia sẻ giữa nhiều nơi dùng, thích hợp làm khóa `HashMap` hoặc `HashSet` (với `equals()`/`hashCode()` ổn định), đồng thời làm cho việc dùng literal chung trong string pool an toàn.

Khi xây dựng một chuỗi từ rất nhiều mảnh trong vòng lặp, `StringBuilder` là lựa chọn phù hợp để tích lũy nội dung có thể thay đổi, rồi gọi `toString()` để lấy `String` cuối cùng. Không cần thay mọi phép nối `+` đơn giản bằng `StringBuilder`; trình biên dịch/JVM hiện đại có các tối ưu cho nối chuỗi thông thường.

## 3. So sánh **giá trị** khác so sánh **tham chiếu**

| Cách so sánh | Câu hỏi được trả lời | Dùng khi nào |
| --- | --- | --- |
| `a.equals(b)` | Hai chuỗi có **cùng nội dung** không? | Mặc định khi kiểm tra dữ liệu chuỗi; `a` phải khác `null`. |
| `java.util.Objects.equals(a, b)` | Nội dung bằng nhau, và xử lý được `null`? | Khi một hoặc cả hai biến có thể `null`. |
| `a == b` | Hai tham chiếu có trỏ tới **đúng cùng đối tượng** không? | Khi thực sự cần biết danh tính đối tượng, hoặc đang minh họa cơ chế intern. |

Ví dụ `new String("Java")` tạo ra một đối tượng `String` mới có **cùng nội dung** với literal `"Java"`. Vì vậy `equals()` có thể là `true` trong khi `==` là `false`.

**Quy tắc thực hành:** So sánh tên, mã, câu lệnh SQL, nội dung JSON hay kết quả text block bằng `equals()` (hoặc `Objects.equals()` khi có thể `null`). Việc `==` ngẫu nhiên cho kết quả mong muốn trên hai literal không khiến nó trở thành phép so sánh nội dung.

### Lưu ý về Unicode

`length()` trả về số *UTF-16 code units*, không nhất thiết là số ký tự người dùng nhìn thấy. Ví dụ `"🙂".length()` bằng `2` trong khi `"🙂".codePointCount(0, "🙂".length())` bằng `1`. Ngoài ra, ký tự dựng sẵn và tổ hợp dấu có thể trông giống nhau nhưng khác chuỗi đơn vị mã; `equals()` không tự chuẩn hóa Unicode. Nếu ứng dụng cần so sánh các dạng Unicode tương đương, hãy xác định quy tắc chuẩn hóa phù hợp trước khi so sánh.

## 4. String pool và `intern()`

Java duy trì một **pool các chuỗi chuẩn hóa theo nội dung** (canonical strings). Các chuỗi literal và các biểu thức chuỗi hằng tại thời điểm biên dịch được intern tự động. Gọi `s.intern()` sẽ trả về tham chiếu đến đối tượng đại diện cho **giá trị** `s` trong pool:
- Nếu pool đã chứa một chuỗi bằng `s` theo `equals()`, trả về tham chiếu trong pool.
- Nếu chưa có, một chuỗi cùng giá trị được đưa vào pool theo hợp đồng API của `intern()`, rồi trả về tham chiếu chuẩn đó.
- Với hai chuỗi khác `null`, `s.intern() == t.intern()` đúng khi và chỉ khi `s.equals(t)` đúng.
- Gọi `intern()` **không thay đổi nội dung** chuỗi và không tự gán lại biến; muốn dùng tham chiếu chuẩn phải lưu giá trị trả về khi cần.

Phân biệt:
- **Literal:** `"Java"` hay text block `"""..."""`; được intern theo quy tắc ngôn ngữ.
- **Biểu thức hằng lúc biên dịch:** `"Ja" + "va"` được gộp thành giá trị hằng `"Java"` và intern.
- **Giá trị tạo lúc chạy:** Nối một biến thường, gọi `formatted()`, `substring()` hoặc đọc dữ liệu đầu vào; **không có bảo đảm** chúng tự dùng cùng tham chiếu với literal có cùng nội dung.
- **`new String("Java")`:** yêu cầu tạo đối tượng riêng, dù nội dung trùng literal trong pool.

### 4.1. Ví dụ kiểm tra danh tính và `intern()`

**Tệp `StringInternDemo.java`**

~~~java
public class StringInternDemo {
    public static void main(String[] args) {
        String literal = "Java";
        String sameLiteral = "Java";
        String compileTime = "Ja" + "va";

        String suffix = "va"; // không phải biến hằng final
        String runtime = "Ja" + suffix;
        String created = new String("Java");

        System.out.println(literal == sameLiteral);
        System.out.println(literal == compileTime);
        System.out.println(literal == runtime);
        System.out.println(literal.equals(runtime));
        System.out.println(literal == created);
        System.out.println(literal == created.intern());
        System.out.println(runtime.intern() == created.intern());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 StringInternDemo.java
java StringInternDemo
~~~

**Kết quả chính xác:**

~~~text
true
true
false
true
false
true
true
~~~

Giải thích từng nhóm:
1. `literal` và `sameLiteral` cùng tham chiếu vì đều là literal `"Java"` đã intern.
2. `compileTime` cũng dùng tham chiếu chuẩn vì `"Ja" + "va"` là biểu thức hằng tại thời điểm biên dịch.
3. `runtime` được tạo từ phép nối lúc chạy do `suffix` là biến thường: cùng giá trị nhưng khác tham chiếu với `literal`. `created` cũng là đối tượng riêng do có `new String(...)`.
4. `created.intern()` và `runtime.intern()` trả về chuỗi chuẩn của giá trị `"Java"`; vì vậy so sánh `==` giữa **các kết quả intern** có thể đúng. Tuy nhiên trong nghiệp vụ, chỉ cần `literal.equals(runtime)`.

**Chi tiết dễ nhầm:** Nếu viết `final String suffix = "va";` và dùng `"Ja" + suffix` thì `suffix` có thể là một *constant variable* theo quy tắc Java, khiến cả biểu thức được tính lúc biên dịch. Từ khóa `final` riêng lẻ chưa đủ cho mọi giá trị; điều kiện là kiểu nguyên thủy hoặc `String`, có khởi tạo bằng biểu thức hằng và đáp ứng định nghĩa constant variable.

### 4.2. Text block có được intern không?

**Có.** Text block là một `String` literal nên cùng tuân theo quy tắc interning như literal trong ngoặc kép. Sau khi Java chuẩn hóa xuống dòng, loại bỏ khoảng trắng phụ và diễn giải escape, **giá trị thực sự** mới quyết định hai literal có cùng nội dung hay không.

Ví dụ `block == escaped` trong `TextBlockValueDemo` là `true` vì giá trị chính xác của cả hai literal giống nhau. Nếu text block thiếu hoặc thêm một `\n`, một dấu cách, hoặc khác ký tự Unicode, giá trị không còn bằng nhau. Ngược lại, việc gọi `formatted()` trên text block là một **phép xử lý lúc chạy**; kết quả có thể bằng một literal về nội dung nhưng **không có bảo đảm** cùng tham chiếu nếu chưa gọi `intern()`.

Phân biệt thêm: **constant pool trong tệp `.class`** là cấu trúc mô tả hằng và tham chiếu của class; **string pool/interning** là cơ chế cung cấp các tham chiếu `String` chuẩn tại runtime. Chúng liên quan nhau nhưng không phải cùng một khái niệm, và cách JVM lưu trữ nội bộ có thể thay đổi giữa các bản triển khai.

## 5. Có nên tự gọi `intern()` để tiết kiệm bộ nhớ?

Không dùng `intern()` như một thói quen cho mọi chuỗi:
- Intern có chi phí tra cứu/quản lý pool và có thể ảnh hưởng đến thời gian chạy hoặc bộ nhớ.
- Nó chỉ đáng cân nhắc nếu chương trình xử lý số lượng lớn **giá trị lặp lại**, và đo đạc thực tế chứng minh chi phí tổng thể được cải thiện.
- Pool không thay thế cấu trúc dữ liệu chuyên dụng, cache có giới hạn, hay các chiến lược quản lý vòng đời dữ liệu.
- Không dựa vào địa chỉ bộ nhớ, chi tiết vùng heap, hay cách thu gom chuỗi của một JVM cụ thể để chứng minh tính đúng đắn của ứng dụng.

Trong hầu hết mã ứng dụng, hãy ưu tiên `equals()` và các collection có hợp đồng so sánh giá trị. `intern()` chủ yếu hữu ích khi hiểu/điều tra danh tính literal, hoặc trong một tối ưu đã được đo kiểm.

## 6. Những lỗi phổ biến và cách sửa

| Lỗi | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Dùng `input == "yes"` để kiểm tra giá trị | `input` có thể được tạo lúc chạy, khác đối tượng literal | `"yes".equals(input)` |
| Nghĩ `text.replace("a", "b")` sửa `text` | `String` bất biến; kết quả có thể bị bỏ qua | `text = text.replace("a", "b");` |
| Dùng text block và quên newline cuối | Dấu đóng nằm trên dòng riêng thường tạo `\n` cuối | Dự đoán/kiểm tra chính xác bằng `equals()` |
| Giả định thụt lề trong source được giữ nguyên | Text block loại bỏ thụt lề phụ | Viết test hoặc điều chỉnh text block theo giá trị cần lưu |
| Nghĩ `intern()` làm biến gốc tự trỏ vào pool | Nó trả về một tham chiếu, không tự gán lại biến | `String canonical = value.intern();` khi có lý do rõ ràng |
| Gọi `intern()` để thay thế `equals()` | Pool có chi phí và không cần cho kiểm tra nội dung | Dùng `equals()` cho logic ứng dụng |
| Cho rằng `length()` là số ký tự hiển thị | `length()` tính UTF-16 code units | Dùng API code point khi bài toán cần, lưu ý grapheme phức tạp hơn |

## 7. Tự kiểm tra hiểu bài

**Câu 1.** Hai giá trị dưới đây có bằng nhau không?

~~~java
String a = """
    A
    B
    """;
String b = "A\nB";
~~~

**Đáp án:** Không. `a` là `"A\nB\n"`; `b` là `"A\nB"`. Dùng `a.equals(b)` nhận `false`.

**Câu 2.** Vì sao `"ab" == "a" + "b"` là `true` trong ví dụ literal, nhưng không nên dùng `==` cho hai chuỗi người dùng nhập?

**Đáp án:** `"a" + "b"` là biểu thức hằng được gộp lúc biên dịch và intern; đầu vào tại runtime không có bảo đảm tham chiếu tới cùng đối tượng dù cùng giá trị. Dùng `equals()`.

**Câu 3.** Sau đoạn dưới, `s` có còn giá trị `"Java"` không?

~~~java
String s = "Java";
s.toUpperCase(java.util.Locale.ROOT);
~~~

**Đáp án:** Có. Giá trị trả về của `toUpperCase()` bị bỏ qua; `s` vẫn tham chiếu giá trị `"Java"`.

**Câu 4.** Với `String x = new String("ok");`, điều gì khác nhau giữa `x.equals("ok")` và `x.intern() == "ok"`?

**Đáp án:** Cả hai đều `true` trong trường hợp này, nhưng phép đầu kiểm tra giá trị trực tiếp, phép sau so sánh hai tham chiếu chuẩn sau khi interning. Ưu tiên phép đầu trong nghiệp vụ.

## 8. Ghi nhớ khi áp dụng

1. Text block và chuỗi trong ngoặc kép tạo ra cùng kiểu **`String`**; giá trị gồm chính xác các ký tự sau xử lý khoảng trắng, newline và escape.
2. **`String` bất biến**; các phép biến đổi tạo ra giá trị kết quả, không thay đổi nội dung đối tượng cũ.
3. **`equals()`** là lựa chọn mặc định để so sánh nội dung. **`==`** so sánh danh tính tham chiếu.
4. Literal và biểu thức hằng được **intern tự động**; `intern()` cung cấp tham chiếu chuẩn theo giá trị nhưng không nên lạm dụng cho ứng dụng.
5. Với text block, **newline cuối và thụt lề** có thể làm thay đổi kết quả `equals()` và cả sự trùng tham chiếu sau intern.

**Tài liệu chính thức để tra cứu:**
- [Java Language Specification – Text Blocks (`3.10.6)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6)
- [Oracle – Text Blocks](https://docs.oracle.com/en/java/javase/25/language/text-blocks.html)
- [Java API – String, equals và intern](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/String.html)
