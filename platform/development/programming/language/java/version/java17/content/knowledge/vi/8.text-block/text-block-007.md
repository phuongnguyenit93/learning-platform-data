# Chuỗi tạo ra sau xử lý và cách kiểm tra ký tự trong text block — Java 17

## 1. Text block tạo ra đối tượng gì?

Trong Java 17, **text block** là cách viết chuỗi nhiều dòng bằng cặp dấu phân định `"""`. Sau khi trình biên dịch xử lý nội dung bên trong, kết quả vẫn là một **`String` thông thường**. Chương trình không có một kiểu dữ liệu riêng tên là `TextBlock`, và đối tượng chuỗi không ghi nhớ nó được viết bằng text block hay bằng dấu nháy kép thông thường.

```java
String normal = "Hello\nJava\n";

String multiline = """
        Hello
        Java
        """;

System.out.println(normal.equals(multiline)); // true
```

Hai biểu thức trên tạo ra **cùng nội dung ký tự**:

```text
Hello⏎
Java⏎
```

Trong bản hiển thị này, `⏎` chỉ để minh họa ký tự xuống dòng `\\n` (LF), không phải ký tự thực được thêm vào String.

Điều cần học là **giá trị chuỗi sau xử lý**, thay vì đoán kết quả dựa trên vị trí chữ trong trình soạn thảo. Nội dung nhìn thấy trong file Java không luôn khớp từng ký tự với giá trị `String` khi chạy, vì Java xử lý xuống dòng, khoảng trắng thụt lề và các escape sequence.

Text block là tính năng ổn định từ Java 15 (JEP 378) và có sẵn trong Java 17 **không cần bật preview**. Những quy tắc của bài vẫn hữu ích khi viết Java hiện đại.

## 2. Cú pháp cơ bản và ký tự xuống dòng mở đầu

Một text block mở bằng ba dấu nháy kép, theo sau là các khoảng trắng được phép và **một line terminator bắt buộc**. Nội dung bắt đầu ở dòng tiếp theo:

```java
String greeting = """
        Xin chào
        Java 17
        """;
```

Ví dụ trên tạo chuỗi có hai dòng nội dung. Ký tự đầu tiên của chuỗi là `'X'`, **không phải** ký tự xuống dòng sau dấu `"""` mở. Ký tự xuống dòng ngay sau dấu mở là một phần cú pháp mở text block; nó không được tự động chèn vào đầu chuỗi.

Không thể viết text block trên cùng một dòng theo dạng sau:

```java
// Không hợp lệ: cần line terminator ngay sau dấu mở.
// String invalid = """Xin chào""";
```

Tương tự như string literal, text block có thể được gán cho biến, trả về từ phương thức, truyền vào API và thực hiện `equals`, `length`, `substring`, `replace`, `lines`, `codePoints`...

### Đặt dấu đóng ở đâu quyết định ký tự kết thúc

Hai đoạn sau khác nhau ở **vị trí dấu `"""` đóng**:

```java
String withFinalNewline = """
        Alpha
        Beta
        """;

String withoutFinalNewline = """
        Alpha
        Beta""";
```

Sau khi được xử lý:

```java
withFinalNewline.equals("Alpha\nBeta\n");    // true
withoutFinalNewline.equals("Alpha\nBeta");   // true
```

Trong ví dụ thứ nhất, sau `Beta` có một LF vì nội dung dòng `Beta` được kết thúc trước khi đến dòng chứa dấu đóng. Trong ví dụ thứ hai, dấu đóng đứng ngay sau `Beta`, nên không có LF cuối.

**Quy tắc thực hành:** Khi nội dung chuỗi cần chính xác tới ký tự cuối cùng (payload, thông báo, câu lệnh, kiểm thử snapshot), phải quyết định rõ có cần `\\n` ở cuối hay không.

## 3. Ba bước chính tạo nên giá trị chuỗi

Để hiểu chính xác một text block trên Java 17, có thể theo dõi ba bước mà Java dùng để diễn giải nội dung:

1. **Chuẩn hóa các line terminator** trong nội dung text block: `CR` (U+000D) và `CRLF` được chuẩn hóa thành `LF` (U+000A).
2. **Loại bỏ phần thụt lề ngẫu nhiên** (*incidental indentation*) và khoảng trắng cuối dòng theo các quy tắc text block. Phần thụt lề mang ý nghĩa tương đối có thể vẫn được giữ.
3. **Diễn giải escape sequence**: chẳng hạn `\\n`, `\\t`, `\\s` và dấu gạch chéo ngược ở cuối dòng cho line continuation.

Thứ tự này rất quan trọng: Java loại bỏ khoảng trắng nguồn theo quy tắc text block **trước khi** diễn giải escape. Vì thế `\\s` có thể cố ý tạo một khoảng trắng cuối dòng mà bước xử lý khoảng trắng thông thường không xóa đi.

| Bước | Dữ liệu nguồn | Điều có thể khác đi trong String |
|---|---|---|
| Chuẩn hóa newline | File dùng CRLF hoặc CR | Newline trong chuỗi text block là LF `\\n` |
| Loại thụt lề | Mã được thụt vào để nằm trong class/method | Phần thụt lề chung được loại bỏ |
| Xử lý khoảng trắng cuối dòng | Có space/tab ở cuối dòng nguồn | Khoảng trắng cuối dòng thông thường không được giữ |
| Diễn giải escape | Nguồn chứa `\\s`, `\\t`, `\\n`, `\\` cuối dòng | Chuỗi nhận space, tab, newline hoặc nối dòng tương ứng |

Lưu ý rằng trong hệ thống Java còn có các bước dịch ký tự Unicode escape của mã nguồn trước khi phân tích token. Với bài tập text block, nên mô tả ký tự mong muốn qua những escape thích hợp và kiểm tra trực tiếp chuỗi cuối cùng, thay vì suy luận từ mọi lớp xử lý của compiler.

## 4. Chuẩn hóa line terminator: CR, LF, CRLF

Text block có thể được viết trong một file nguồn sử dụng kiểu xuống dòng khác nhau theo hệ điều hành hoặc cấu hình Git:

| Ký hiệu | Code point | Mô tả |
|---|---|---|
| LF | U+000A | Line feed, biểu diễn trong Java là `'\\n'` |
| CR | U+000D | Carriage return, biểu diễn trong Java là `'\\r'` |
| CRLF | U+000D rồi U+000A | Cặp ký tự thường được dùng làm xuống dòng trong file nguồn trên Windows |

Đối với **line terminator thuộc nội dung text block**, Java chuẩn hóa CR và CRLF thành LF. Do đó cùng một text block thường tạo ra cùng giá trị chuỗi dù file nguồn dùng CRLF hay LF.

```java
String text = """
        first
        second
        """;

System.out.println(text.equals("first\nsecond\n")); // true
System.out.println(text.indexOf('\r'));              // -1
```

Ví dụ này mô tả ký tự xuống dòng do **dòng nội dung nguồn** tạo ra. Nếu bạn chủ động viết escape `\\r` bên trong text block, bước xử lý escape ở cuối vẫn có thể tạo ra CR trong chuỗi kết quả:

```java
String explicitCr = """
        A\rB""";

System.out.println(explicitCr.indexOf('\r')); // 1
```

Như vậy, **chuẩn hóa dòng trong nguồn không có nghĩa mọi String được tạo từ text block đều không thể chứa CR**. Chúng ta cần phân biệt line terminator có sẵn trong văn bản nguồn với ký tự được tạo ra bởi escape.

Khi ứng dụng giao tiếp với hệ thống cần `CRLF`, hãy chủ động xây dựng nội dung theo định dạng đó và kiểm tra; không nên giả định text block sẽ tự theo xuống dòng của hệ điều hành.

## 5. Loại bỏ thụt lề ngẫu nhiên

Text block thường nằm sâu bên trong class hoặc method, nên mã nguồn được thụt vào để dễ đọc. Java không đưa toàn bộ khoảng trắng thụt lề này vào chuỗi.

```java
String note = """
        first
        second
        """;

System.out.println(note.equals("first\nsecond\n")); // true
```

Trong ví dụ, khoảng trắng chung trước `first`, `second` và dấu đóng được xem là **incidental indentation**. Sau xử lý, chuỗi bắt đầu ngay bằng `f`.

### 5.1. Thụt lề tương đối vẫn được giữ

```java
String tree = """
        root
          child
            leaf
        """;
```

Kết quả là:

```text
root
  child
    leaf
```

Tương đương:

```java
"root\n  child\n    leaf\n"
```

Phần thụt lề chung đã bị bỏ; **hai dấu cách trước `child` và bốn dấu cách trước `leaf`** còn lại để thể hiện cấu trúc tương đối.

### 5.2. Vị trí dấu đóng cũng tham gia quy tắc thụt lề

Dấu đóng ở một mức thụt lề khác có thể khiến kết quả giữ lại nhiều khoảng trắng hơn:

```java
String indented = """
        one
          two
      """;
```

Với ví dụ trên, phần thụt lề ngẫu nhiên được quyết định theo mức nhỏ nhất có liên quan, gồm cả vị trí dấu đóng khi nó nằm trên dòng riêng. Vì dấu đóng lùi trái so với `one`, kết quả còn một phần khoảng trắng đầu dòng:

```java
indented.equals("  one\n    two\n"); // true
```

Đây là kỹ thuật có thể dùng khi thực sự cần một số khoảng trắng đầu mỗi dòng, nhưng nó dễ bị ảnh hưởng khi ai đó căn chỉnh lại dấu đóng. Đối với dữ liệu nhạy với whitespace, nên ghi rõ kỳ vọng bằng kiểm thử thay vì chỉ quan sát cách canh lề trong editor.

### 5.3. Khoảng trắng cuối dòng nguồn thường bị loại

Giả sử một dòng trông như có vài dấu cách sau chữ `A`:

```java
String noTrailingSpaces = """
        A
        B
        """;
```

Java loại bỏ khoảng trắng cuối dòng nguồn theo quy tắc text block. Nếu muốn **cố ý giữ dấu cách cuối dòng**, hãy viết rõ escape `\\s`:

```java
String keepOneSpace = """
        A\s
        B
        """;

System.out.println(keepOneSpace.equals("A \nB\n")); // true
```

Một khoảng trắng có ý nghĩa đã được thêm vào sau `A`. Người đọc mã có thể nhận ra đây là khoảng trắng được cố ý giữ, thay vì một lỗi định dạng do editor.

### 5.4. Tab và space không đồng nhất

Trong String, tab `\\t` là **một ký tự U+0009**, còn dấu cách `' '` là **U+0020**. Hai chuỗi có thể nhìn gần giống nhau trong terminal nhưng khác hẳn:

```java
String tabbed = "A\tB";
String spaced = "A B";

System.out.println(tabbed.equals(spaced)); // false
```

Để kiểm soát chính xác, hạn chế phối hợp tab và space ở phần đầu dòng văn bản nguồn, ưu tiên dùng `\\t` khi thực sự cần tab ở chuỗi kết quả và kiểm tra giá trị ký tự sau biên dịch.

## 6. Escape sequence trong text block

Text block hỗ trợ các escape của chuỗi Java, cùng những escape hữu ích cho văn bản nhiều dòng.

| Escape viết trong Java source | Ký tự hoặc tác dụng sau xử lý | Khi nào cần |
|---|---|---|
| `\\n` | LF, U+000A | Chủ động tạo newline tại một vị trí |
| `\\r` | CR, U+000D | Giao thức cần carriage return |
| `\\t` | Tab, U+0009 | Dữ liệu phân tách bằng tab |
| `\\s` | Space, U+0020 | Giữ đúng một dấu cách, nhất là cuối dòng |
| `\\\\` | Một ký tự gạch chéo ngược | Văn bản thực sự cần `\\` |
| `\\"` | Dấu nháy kép `"` | Khi cần escape nháy kép hoặc tránh kết thúc chuỗi |
| `\\` ngay trước line terminator | **Line continuation**: bỏ line terminator đó | Trải mã nguồn trên nhiều dòng mà ghép nội dung thành một dòng |

Trong text block, phần lớn dấu nháy kép đơn lẻ không cần escape:

```java
String json = """
        {
          "name": "Java",
          "version": 17
        }
        """;
```

Ký tự `"` trong `"name"` và `"Java"` là ký tự bình thường bên trong text block. Nếu cần ba dấu nháy liên tiếp trong phần nội dung, phải tránh để chúng bị nhận diện là dấu kết thúc text block, chẳng hạn bằng escape phù hợp.

### 6.1. Line continuation: gạch chéo ngược ở cuối dòng

Giả sử cần một String **liền mạch** nhưng muốn nguồn Java xuống nhiều dòng:

```java
String combined = """
        Java\
        Seventeen\
        Rocks
        """;
```

Sau xử lý:

```java
combined.equals("JavaSeventeenRocks\n"); // true
```

Gạch chéo ngược cuối dòng không phải ký tự được giữ trong chuỗi; nó chỉ báo **nối dòng nguồn**. Vì thế không có LF giữa `Java` và `Seventeen`, cũng không có LF giữa `Seventeen` và `Rocks`.

Nếu muốn có dấu cách tại vị trí ghép, cần chỉ định nó rõ:

```java
String words = """
        Java\s\
        Seventeen
        """;

System.out.println(words.equals("Java Seventeen\n")); // true
```

Ở dòng đầu, `\\s` tạo một dấu cách và escape nối dòng loại bỏ LF. Sau xử lý, hai từ được nối trên một dòng với **một** space ở giữa.

Đừng nhầm việc dùng `\\n` trong nguồn với việc có một dòng mới trong text block:

- Viết `\\n` nghĩa là yêu cầu tạo một LF tại vị trí escape.
- Đặt một dòng mới thật trong nội dung text block thường cũng tạo LF.
- Viết `\\` ở cuối dòng nghĩa là loại bỏ LF tại vị trí nối dòng.

## 7. Quan sát kết quả: không chỉ nhìn bằng `println`

Khi in ra console, một số ký tự **khó phân biệt bằng mắt**:

- Space ở cuối dòng thường không nhìn thấy.
- Tab được terminal giãn thành số cột hiển thị khác nhau.
- `\\r` có thể làm con trỏ quay về đầu dòng khi terminal xử lý.
- Một LF nằm cuối String và một LF do `println` thêm vào có thể khiến số dòng nhìn thấy khác nhau.

Vì vậy, khi cần biết chuỗi **chính xác sau xử lý**, hãy kiểm tra bằng `equals`, `length`, vị trí ký tự và biểu diễn code point.

### 7.1. `print` và `println` cho kết quả hiển thị khác nhau

```java
String text = """
        Hello
        """;

System.out.print(text);   // In đúng nội dung String.
System.out.println(text); // In String rồi thêm line separator của println.
```

Trong cả hai trường hợp, bản thân `text` **không đổi**. Nhưng `println` thêm dấu xuống dòng do API in ấn, nên không nên lấy tổng số dòng quan sát trên màn hình làm bằng chứng duy nhất về nội dung String.

### 7.2. Hiển thị whitespace bằng ký hiệu riêng

Tạo một bản **chỉ dùng để quan sát**, trong đó space được biểu diễn bằng `·`, tab bằng `⇥`, LF bằng `↵`:

```java
static String visible(String text) {
    return text
            .replace(" ", "·")
            .replace("\t", "⇥")
            .replace("\r", "␍")
            .replace("\n", "↵\n");
}
```

Ví dụ:

```java
String sample = """
        name:\sJava
        end\s
        """;

System.out.print(visible(sample));
```

Khi hiển thị, phần cuối dòng thứ hai sẽ có ký hiệu `·` đứng ngay trước `↵`. Đây là **bản trình bày để kiểm tra**; bản thân `sample` vẫn chứa các ký tự thực là space và LF, không chứa `·` hoặc `↵`.

### 7.3. So sánh với chuỗi kỳ vọng

Cách rõ ràng để chứng minh kết quả:

```java
String actual = """
        header
          item
        """;

String expected = "header\n  item\n";

if (!expected.equals(actual)) {
    throw new AssertionError("Text content differs");
}
```

Thao tác này kiểm tra chính xác **mọi ký tự**, gồm cả khoảng trắng thụt lề và LF cuối.

Khi dự án dùng JUnit, có thể thay bằng `assertEquals(expected, actual)`; JUnit là thư viện kiểm thử riêng, **không tích hợp sẵn trong JDK 17**.

### 7.4. Kiểm tra vị trí và mã UTF-16

`String.length()` đếm **UTF-16 code units**, không nhất thiết đếm số ký tự mà người đọc nhìn thấy. Với ASCII và các ký tự thường gặp nằm trong BMP, mỗi ký tự có một UTF-16 code unit.

```java
String value = """
        A\s
        """;

System.out.println(value.length());     // 3: 'A', ' ', '\n'
System.out.println(value.charAt(0));   // A
System.out.println((int) value.charAt(1)); // 32: U+0020
System.out.println((int) value.charAt(2)); // 10: U+000A
```

Kết quả này cho biết không có dấu cách lạ ở đầu chuỗi và khoảng trắng được cố ý giữ lại cuối dòng vẫn hiện diện trước newline.

## 8. Code point, ký tự Unicode và điều người dùng nhìn thấy

Một chuỗi có thể chứa ký tự ngoài Basic Multilingual Plane (BMP), chẳng hạn nhiều emoji. Các ký tự này dùng **hai UTF-16 code units** (surrogate pair). Vì thế `length()` và `charAt()` không phải lúc nào cũng tương ứng một-một với Unicode code points.

```java
String emoji = """
        😀""";

System.out.println(emoji.length());                         // 2
System.out.println(emoji.codePointCount(0, emoji.length())); // 1
System.out.printf("U+%X%n", emoji.codePointAt(0));           // U+1F600
```

Để duyệt các **Unicode code points**:

```java
String text = """
        A😀
        """;

text.codePoints().forEach(cp ->
        System.out.printf("U+%04X%n", cp));
```

Kết quả:

```text
U+0041
U+1F600
U+000A
```

Trong Java 17:

- `chars()` phát ra mã của từng UTF-16 code unit.
- `codePoints()` phát ra các Unicode code points.
- `charAt(i)` truy cập một UTF-16 code unit tại vị trí `i`.
- `codePointCount(0, s.length())` đếm code points của toàn bộ String.

Một **ký tự người dùng cảm nhận** (*grapheme cluster*) còn có thể gồm nhiều code points, chẳng hạn chữ cái kết hợp dấu hoặc tổ hợp emoji. Vì thế ngay cả số code points cũng không nhất thiết bằng số ký tự hiển thị.

Điểm liên quan trực tiếp tới text block: **text block chỉ thay cách biểu diễn chuỗi trong mã nguồn**. Sau khi tạo ra `String`, mọi quy tắc Unicode và API xử lý chuỗi của Java vẫn áp dụng y như đối với string literal thông thường.

## 9. Chương trình tổng hợp chạy trên Java 17

Tệp `Main.java` dưới đây cho thấy:

1. Sự khác nhau giữa LF cuối và không có LF cuối.
2. Phần thụt lề tương đối được giữ.
3. Space được tạo bằng `\\s`.
4. Cách xem **từng code point** của String.

```java
public class Main {
    static String visible(String text) {
        return text
                .replace(" ", "·")
                .replace("\t", "⇥")
                .replace("\r", "␍")
                .replace("\n", "↵\n");
    }

    static void inspect(String name, String text) {
        System.out.println("[" + name + "]");
        System.out.println("UTF-16 units: " + text.length());
        System.out.println("Content: " + visible(text));
        System.out.print("Code points:");
        text.codePoints().forEach(cp ->
                System.out.printf(" U+%04X", cp));
        System.out.println();
    }

    public static void main(String[] args) {
        String withLf = """
                Hi
                """;

        String noLf = """
                Hi""";

        String nested = """
                root
                  child
                """;

        String keptSpace = """
                A\s
                """;

        inspect("withLf", withLf);
        inspect("noLf", noLf);
        inspect("nested", nested);
        inspect("keptSpace", keptSpace);

        System.out.println(withLf.equals("Hi\n"));            // true
        System.out.println(noLf.equals("Hi"));                 // true
        System.out.println(nested.equals("root\n  child\n")); // true
        System.out.println(keptSpace.equals("A \n"));          // true
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

Phần cần quan sát trong các kết quả:

| Biến | Giá trị chính xác của String | `length()` |
|---|---|---:|
| `withLf` | `"Hi\\n"` | 3 |
| `noLf` | `"Hi"` | 2 |
| `nested` | `"root\\n  child\\n"` | 13 |
| `keptSpace` | `"A \\n"` | 3 |

Với `keptSpace`, dãy mã code point là `U+0041 U+0020 U+000A`. Dấu cách `U+0020` được tạo có chủ đích ngay trước newline.

Với `nested`, hai dấu cách trước `child` nằm trong String kết quả; không phải khoảng trắng chỉ phục vụ định dạng file Java.

## 10. Dùng String API để kiểm tra thêm

### 10.1. `String.lines()` và giới hạn khi kiểm tra newline cuối

`lines()` hữu ích để xử lý nội dung theo dòng:

```java
String text = """
        red
        blue
        """;

text.lines().forEach(System.out::println);
```

Nhưng `lines()` **không giữ các ký tự kết thúc dòng trong từng phần tử**. Bởi vậy chỉ duyệt `lines()` chưa đủ để xác nhận có LF cuối hay không.

```java
String a = "red\nblue\n";
String b = "red\nblue";

System.out.println(a.lines().count()); // 2
System.out.println(b.lines().count()); // 2
System.out.println(a.equals(b));       // false
```

Khi cần kiểm tra newline cuối, dùng `endsWith("\\n")`, `equals`, hoặc duyệt mã ký tự thay vì dựa vào số dòng.

### 10.2. `strip`, `stripTrailing` và `trim`

Các phương thức xóa khoảng trắng **lúc runtime** là thao tác khác với **quy tắc xử lý text block khi biên dịch**.

```java
String text = """
        Hello
        """;

System.out.println(text.equals("Hello\n"));  // true
System.out.println(text.strip().equals("Hello")); // true
```

`strip()` không sửa String gốc; nó trả về một String mới với whitespace đầu/cuối bị loại theo quy tắc của phương thức. Đừng tùy tiện gọi `strip()` lên dữ liệu cần giữ newline cuối hoặc thụt lề có ý nghĩa.

`stripIndent()` và `translateEscapes()` là các String API hữu ích khi xử lý văn bản ở runtime, nhưng chúng **không phải bằng chứng** rằng một String có nguồn gốc text block: khi compile, kết quả text block đã trải qua các bước xử lý cần thiết rồi. Gọi lại chúng có thể tiếp tục thay đổi dữ liệu đang có.

### 10.3. So sánh chuỗi thay vì so sánh tham chiếu

```java
String first = """
        one
        two
        """;

String second = "one\ntwo\n";

System.out.println(first.equals(second)); // true
```

Không dùng `==` làm cách kiểm chứng nội dung chuỗi. Toán tử `==` so sánh tham chiếu đối tượng; dù Java có cơ chế intern các literal và một số biểu thức hằng, kết quả so sánh tham chiếu không phải hợp đồng kiểm chứng nội dung mà bài học đang cần.

## 11. Những lỗi thường gặp khi quan sát text block

### 11.1. Nhầm dấu đóng trên dòng riêng với dấu đóng cùng dòng

```java
String a = """
        done
        """;
String b = """
        done""";
```

`a` bằng `"done\\n"`; `b` bằng `"done"`. Nếu truyền văn bản sang API kiểm thử snapshot hoặc so chữ ký nội dung, một LF dư hoặc thiếu cũng có thể làm kết quả khác.

### 11.2. Cố giữ dấu cách bằng cách gõ space ở cuối dòng

Editor hoặc formatter có thể xóa space cuối dòng. Quan trọng hơn, bản thân text block còn có quy tắc xóa trailing whitespace. Hãy dùng `\\s` để biểu diễn rõ khoảng trắng cần giữ.

### 11.3. Nhầm mức thụt của file nguồn với thụt lề kết quả

Java loại bỏ incidental indentation; đừng đoán có bao nhiêu space trong String chỉ bằng cách đếm cột từ lề trái editor. Dấu đóng và các dòng có thụt lề tương đối đều ảnh hưởng đến kết quả. Dùng `visible` và `equals` để kiểm tra.

### 11.4. Kết luận từ kết quả `println`

`println` thêm line separator khi in. Khoảng trắng cuối dòng thường không nhìn thấy. Để xác nhận chính xác, hãy kiểm tra `length()`, `charAt`, `codePoints()` hoặc so sánh với literal kỳ vọng.

### 11.5. Cho rằng text block giải mã định dạng dữ liệu

```java
String json = """
        {"name":"Java","major":17}
        """;
```

`json` vẫn chỉ là **String**. Text block không kiểm tra JSON hợp lệ, không tự biến JSON thành object, không tự escape dữ liệu động và không tự bảo vệ khỏi SQL injection hoặc lỗi định dạng khi ghép chuỗi. Nếu cần thao tác JSON thực sự, dùng parser phù hợp; với SQL động nên dùng prepared statement và tham số hóa.

### 11.6. Dùng text block để thay đổi cách mã hóa lúc ghi file

Giá trị String trong JVM được biểu diễn theo mô hình UTF-16 của Java. Khi ghi ra file hoặc gửi qua mạng, bạn vẫn phải chọn encoding phù hợp (thường là UTF-8). Text block **không tự chỉ định encoding cho file đầu ra**:

```java
java.nio.file.Files.writeString(
        java.nio.file.Path.of("message.txt"),
        """
        Xin chào Java 17
        """,
        java.nio.charset.StandardCharsets.UTF_8);
```

`Files.writeString` ở đây nhận String đã tạo và mã hóa nó thành bytes theo UTF-8 khi ghi tệp.

## 12. Bài tập đọc chính xác chuỗi kết quả

### Bài 1: Nhận diện LF cuối

```java
String a = """
        A
        B
        """;

String b = """
        A
        B""";
```

Hãy viết hai string literal thông thường có nội dung bằng `a` và `b`.

**Đáp án:** `a.equals("A\\nB\\n")` và `b.equals("A\\nB")` đều là `true`. Khác biệt là ký tự LF cuối cùng.

### Bài 2: Phân biệt thụt lề tương đối

```java
String layout = """
        parent
            child
        """;
```

Hãy cho biết có bao nhiêu dấu cách trước `child` sau khi xử lý và viết biểu thức kiểm chứng.

**Đáp án:** bốn space. Kiểm tra bằng:

```java
System.out.println(layout.equals("parent\n    child\n")); // true
```

### Bài 3: Giữ một dấu cách cuối dòng

```java
String line = """
        END\s
        """;
```

Hãy viết ba code point cuối theo thứ tự và dự đoán `line.length()`.

**Đáp án:** ba code point cuối là `U+0044` (D), `U+0020` (space), `U+000A` (LF). Chuỗi toàn bộ là `"END \\n"` và `length() == 5`.

### Bài 4: Nối dòng bằng escape

```java
String text = """
        first\
        second
        """;
```

Hãy cho biết chuỗi chứa một hay hai dòng, và liệu nó có dấu cách giữa hai từ hay không.

**Đáp án:** `text.equals("firstsecond\\n")` là `true`. Không có space giữa hai từ; chỉ có LF ở cuối do dòng `second` kết thúc trước dấu đóng.

### Bài 5: Đếm `length` và code points

```java
String value = """
        😀""";
```

Hãy dự đoán `value.length()` và `value.codePointCount(0, value.length())`.

**Đáp án:** lần lượt là `2` và `1`, bởi emoji ngoài BMP chiếm một code point nhưng hai UTF-16 code units.

### Bài 6: Viết hàm kiểm chứng

Viết một hàm nhận `String actual`, kiểm tra nó đúng bằng hai dòng `key=value` và `done`, có đúng một LF sau mỗi dòng. Hàm trả `boolean`.

```java
static boolean hasExpectedContent(String actual) {
    return "key=value\ndone\n".equals(actual);
}
```

Sau đó tự tạo một text block thỏa điều kiện và một text block chỉ khác **LF cuối** để thấy `equals` có thể phân biệt dữ liệu mà console không thể hiện rõ.

## 13. Tiêu chí hoàn thành

Người học nắm vững bài này khi có thể:

1. Giải thích text block trong Java 17 tạo ra **`String`**, không phải một kiểu dữ liệu mới.
2. Nêu được ba bước xử lý: chuẩn hóa newline, loại incidental whitespace, diễn giải escape.
3. Phân biệt dấu đóng trên dòng riêng với dấu đóng ngay sau ký tự cuối; dự đoán chính xác có hoặc không có LF cuối.
4. Giải thích thụt lề chung bị loại và thụt lề tương đối còn lại.
5. Sử dụng `\\s` để giữ space cuối dòng và `\\` cuối dòng để nối nội dung; phân biệt chúng với `\\n` và `\\t`.
6. Xác minh được String qua `equals`, `length`, `charAt`, `codePoints`, tránh suy luận chỉ từ `println`.
7. Phân biệt UTF-16 code units, Unicode code points và ký tự hiển thị khi chuỗi chứa emoji hoặc ký tự nhiều mã.
8. Biên dịch ví dụ bằng JDK 17 với `javac --release 17`, không dùng cú pháp preview.

## 14. Tài liệu tham khảo chính thức

- [OpenJDK JEP 378 — Text Blocks](https://openjdk.org/jeps/378): mô tả quy tắc xử lý text block, incidental whitespace và escape sequence.
- [Java Language Specification SE 17 — Text Blocks (§3.10.6)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6): ngữ pháp và cách xác định giá trị ký tự của text block.
- [Java SE 17 API — `String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `length`, `charAt`, `codePoints`, `lines`, `stripIndent`, `translateEscapes` và các phương thức làm việc với chuỗi.
- [Java SE 17 API — `Character`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): mô hình code point và UTF-16 của Java.

**Điểm cốt lõi:** vẻ ngoài nhiều dòng của mã nguồn text block chỉ là một phần câu chuyện. Giá trị cần quan tâm là **chuỗi ký tự sau ba bước xử lý**. Muốn xác nhận dữ liệu đúng tới từng space, tab và newline, hãy kiểm tra chính `String` bằng so sánh và API ký tự, thay vì chỉ nhìn mã nguồn hoặc kết quả in ra màn hình.
