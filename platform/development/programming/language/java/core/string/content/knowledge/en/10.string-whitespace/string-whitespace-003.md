# String.strip(), stripLeading() và stripTrailing() trong Java

Trong Java, khi nhận tên người dùng, tiêu đề, nội dung biểu mẫu hay các giá trị văn bản, ta thường cần loại bỏ **ký tự khoảng trắng ở rìa chuỗi**. Từ Java 11, lớp `java.lang.String` có ba phương thức: `strip()`, `stripLeading()` và `stripTrailing()`. Chúng đều trả về một `String` và sử dụng khái niệm **whitespace của Java** thông qua `Character.isWhitespace(...)`.

Điểm cần nắm: **ba phương thức khác nhau ở phía của chuỗi được xử lý**; không phương thức nào có nhiệm vụ xóa khoảng trắng ở giữa nội dung. Chúng cũng khác `trim()` về tiêu chí nhận diện ký tự khoảng trắng, đặc biệt đối với Unicode.

## 1. So sánh ba phương thức

| Phương thức | Tác động | Ví dụ đầu vào | Kết quả |
|---|---|---|---|
| `s.strip()` | Bỏ whitespace ở **cả đầu lẫn cuối** | `"  Hello  "` | `"Hello"` |
| `s.stripLeading()` | Bỏ whitespace **chỉ ở đầu** | `"  Hello  "` | `"Hello  "` |
| `s.stripTrailing()` | Bỏ whitespace **chỉ ở cuối** | `"  Hello  "` | `"  Hello"` |

Chữ *leading* nghĩa là phần đầu; *trailing* nghĩa là phần đuôi. Trong ví dụ bảng, các ký tự khoảng trắng đều là dấu cách ASCII `U+0020` nên có thể quan sát trực tiếp. Với tab, xuống dòng và các ký tự trắng Unicode, đầu ra trên terminal không phải lúc nào cũng có dấu hiệu trực quan rõ ràng.

Cú pháp API:

```java
String both = source.strip();
String left = source.stripLeading();
String right = source.stripTrailing();
```

Đoạn trên là mã minh họa, giả sử `source` đã được khai báo. Cả ba phương thức **không nhận tham số**, có từ **Java 11**, và không ném lỗi khi `source` là chuỗi rỗng hay chỉ có whitespace. Tuy nhiên, nếu biến tham chiếu là `null`, gọi `source.strip()` sẽ gây `NullPointerException`.

## 2. Chuỗi được xử lý từ đâu đến đâu?

Giả sử một chuỗi có ba vùng:

```text
[ whitespace đầu ][ NỘI DUNG ][ whitespace cuối ]
  stripLeading()      giữ lại        stripTrailing()
             \         |         /
              \----- strip() ---/
```

Các phương thức chỉ quét các ký tự **liên tiếp** thuộc nhóm whitespace từ rìa được xét, và dừng khi gặp nội dung **không phải whitespace**. Chúng không “tìm và xóa mọi whitespace” trong cả chuỗi.

Ví dụ:

```java
String input = " \tJava  Core\n";
System.out.println(input.strip().equals("Java  Core")); // true
```

`strip()` bỏ dấu cách và tab ở đầu, bỏ newline ở cuối, nhưng **giữ nguyên hai dấu cách ở giữa** `Java` và `Core`. Nếu mục tiêu là chuẩn hóa khoảng trắng giữa các từ, đó là tác vụ khác với việc cắt khoảng trắng ở hai mép.

Một số ca biên:

- `"".strip()` trả `""`.
- `"   ".strip()` trả `""` vì toàn bộ nội dung là whitespace.
- `"   ".stripLeading()` và `"   ".stripTrailing()` cũng trả chuỗi rỗng.
- `"abc".strip()` có cùng nội dung `"abc"`.
- `" a  b ".strip()` là `"a  b"`: vẫn còn **hai** dấu cách giữa `a` và `b`.
- `"a\nb".strip()` vẫn có newline **bên trong** vì nó không nằm ở rìa chuỗi.

Có thể kết hợp `stripLeading()` và `stripTrailing()` theo thứ tự nào cũng được để đạt **giá trị chuỗi** tương đương `strip()`. Dùng trực tiếp `strip()` khi cần xử lý hai phía là cách rõ ý hơn.

## 3. “Whitespace” theo Java là gì?

Theo API `String`, các phương thức `strip...` nhận diện whitespace dựa trên `Character.isWhitespace(int codePoint)`. Đây là một quy tắc Unicode cụ thể do Java cung cấp, **không phải tất cả những ký tự trông giống khoảng trống trên màn hình**.

Những ví dụ thường gặp:

| Ký tự | Mã Unicode | `Character.isWhitespace` | `strip()` ở rìa |
|---|---|---|---|
| Dấu cách thông thường | `U+0020` (SPACE) | `true` | Bỏ |
| Tab ngang | `U+0009` (TAB) | `true` | Bỏ |
| Line feed | `U+000A` (LF) | `true` | Bỏ |
| Carriage return | `U+000D` (CR) | `true` | Bỏ |
| Em Space | `U+2003` | `true` | Bỏ |
| Ideographic Space | `U+3000` | `true` | Bỏ |
| Non-Breaking Space | `U+00A0` (NBSP) | `false` | **Giữ lại** |
| Figure Space | `U+2007` | `false` | **Giữ lại** |
| Narrow No-Break Space | `U+202F` | `false` | **Giữ lại** |
| Zero Width Space | `U+200B` | `false` | Giữ lại |
| Byte Order Mark (khi là ký tự trong văn bản) | `U+FEFF` | `false` | Giữ lại |

Bảng đưa ra những ca thực tế để **minh họa**, không phải toàn bộ bảng Unicode. Cách phân loại dựa trên quy tắc `Character.isWhitespace` của phiên bản Java bạn dùng; khi nâng cấp JDK, dữ liệu Unicode có thể được cập nhật.

Đặc biệt, tên **Non-Breaking Space** có chữ *Space* nhưng Java cố ý **không coi đây là whitespace theo `isWhitespace`**. Do đó, đoạn sau **không** loại bỏ NBSP:

```java
String data = "\u00A0Hello\u00A0";
System.out.println(data.strip().length()); // 7: NBSP + 5 chữ + NBSP
```

Nếu nghiệp vụ cần coi NBSP như một dấu cách có thể xóa, phải chỉ định chính sách chuyển đổi hoặc chuẩn hóa riêng; không nên giả định rằng `strip()` tự làm điều này.

### Vì sao NBSP có thể gây lỗi tưởng như “không strip được”?

Một chuỗi hiển thị giống `" Hello "` có thể thực ra bắt đầu hoặc kết thúc bằng `U+00A0`. Vì `Character.isWhitespace(0x00A0)` là `false`, `strip()` sẽ dừng tại ký tự đó ở rìa.

Ví dụ: `"\u00A0  Hello  "` bắt đầu bằng NBSP, nên `stripLeading()` **không** vượt qua NBSP để xóa hai dấu cách đứng sau nó. Ở phía phải, `stripTrailing()` vẫn có thể xóa các dấu cách thông thường liên tiếp ở cuối. Nguyên tắc quét từ mép giải thích chính xác hành vi này.

Khi debug, hãy in **code point** hoặc biểu diễn từng ký tự bằng ký hiệu rõ ràng thay vì chỉ nhìn khoảng trống trong output.

## 4. `strip()` khác `trim()` như thế nào?

`String.trim()` là phương thức có từ các phiên bản Java cũ. Nó dùng tiêu chí dựa trên **giá trị đơn vị mã không vượt quá `U+0020`** ở hai rìa (các ký tự có giá trị `<= '\u0020'`). Tiêu chí này không đồng nhất với Unicode whitespace của `Character.isWhitespace`.

| Vấn đề | `trim()` | `strip()` |
|---|---|---|
| Xuất hiện từ | Java rất lâu trước Java 11 | Java 11 |
| Tiêu chí chính | Giá trị đầu/cuối `<= U+0020` | `Character.isWhitespace` |
| SPACE `U+0020`, TAB `U+0009`, LF `U+000A` | Loại bỏ | Loại bỏ |
| EM SPACE `U+2003` | **Giữ lại** | **Loại bỏ** |
| IDEOGRAPHIC SPACE `U+3000` | **Giữ lại** | **Loại bỏ** |
| NBSP `U+00A0` | Giữ lại | Giữ lại |
| NULL `U+0000` ở rìa | Có thể loại bỏ vì `U+0000 <= U+0020` | Không thuộc whitespace nên giữ lại |

Điều đó có nghĩa **`strip()` không đơn giản là một “`trim()` mạnh hơn” trên mọi dữ liệu**. Với những đơn vị mã điều khiển có giá trị nhỏ mà Java không coi là whitespace, `trim()` có thể loại bỏ trong khi `strip()` giữ nguyên. Khi mục tiêu thực sự là loại bỏ **Unicode whitespace ở rìa**, nên ưu tiên `strip()` trong Java 11+.

Một ví dụ dễ thấy bằng mã nguồn:

```java
String text = "\u2003 Java \u2003";
System.out.println(text.strip().equals("Java")); // true
System.out.println(text.trim().equals(text));     // true
```

`trim()` nhìn thấy Em Space ở mép là ký tự `> U+0020` nên dừng ngay; `strip()` nhận ra Em Space là whitespace và loại bỏ nó cùng các dấu cách kề bên.

## 5. Ví dụ Java 17+: nhìn rõ kết quả khi có TAB, Em Space, NBSP

Vì tab và khoảng trắng Unicode khó phân biệt trong console, ví dụ dùng hàm `visible` để **chỉ phục vụ in log**. Nó hiển thị TAB thành `<TAB>`, Em Space thành `<EM>`, NBSP thành `<NBSP>` và dấu cách ASCII thành ký hiệu `_`. Hàm này không tham gia vào việc cắt chuỗi; nó chỉ giúp người học quan sát kết quả.

Lưu toàn bộ vào **`StripWhitespaceDemo.java`**:

```java
public class StripWhitespaceDemo {
    private static String visible(String text) {
        return text
                .replace("\t", "<TAB>")
                .replace("\u2003", "<EM>")
                .replace("\u00A0", "<NBSP>")
                .replace(" ", "_");
    }

    public static void main(String[] args) {
        String input = "\t\u2003 Hello \t";
        String nbsp = "\u00A0Hello\u00A0";
        String allWhitespace = " \t\u2003 ";

        System.out.println("source: [" + visible(input) + "]");
        System.out.println("strip: [" + visible(input.strip()) + "]");
        System.out.println("leading: ["
                + visible(input.stripLeading()) + "]");
        System.out.println("trailing: ["
                + visible(input.stripTrailing()) + "]");
        System.out.println("trim: [" + visible(input.trim()) + "]");

        System.out.println("NBSP strip: [" + visible(nbsp.strip()) + "]");
        System.out.println("EM isWhitespace: "
                + Character.isWhitespace('\u2003'));
        System.out.println("NBSP isWhitespace: "
                + Character.isWhitespace('\u00A0'));
        System.out.println("all blank: " + allWhitespace.isBlank());
        System.out.println("all strip empty: "
                + allWhitespace.strip().isEmpty());
        System.out.println("middle unchanged: "
                + " a  b ".strip().equals("a  b"));
    }
}
```

Biên dịch và chạy với **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 StripWhitespaceDemo.java
java StripWhitespaceDemo
```

Kết quả:

```text
source: [<TAB><EM>_Hello_<TAB>]
strip: [Hello]
leading: [Hello_<TAB>]
trailing: [<TAB><EM>_Hello]
trim: [<EM>_Hello]
NBSP strip: [<NBSP>Hello<NBSP>]
EM isWhitespace: true
NBSP isWhitespace: false
all blank: true
all strip empty: true
middle unchanged: true
```

Diễn giải:

1. Đầu vào có TAB, Em Space và một dấu cách ở phía đầu; phía cuối có dấu cách và TAB.
2. `strip()` bỏ hết các ký tự được xem là whitespace ở **cả hai** mép: `"Hello"`.
3. `stripLeading()` chỉ bỏ phần đầu: `"Hello \t"`.
4. `stripTrailing()` chỉ bỏ phần cuối: `"\t\u2003 Hello"`.
5. `trim()` chỉ bỏ TAB ngoài cùng ở đầu, rồi gặp Em Space nên dừng. Ở cuối, nó vẫn bỏ TAB và dấu cách vì các ký tự đó `<= U+0020`; kết quả còn Em Space và dấu cách ở đầu: `"\u2003 Hello"`.
6. `NBSP` đứng ở hai đầu vẫn tồn tại sau `strip()` vì `isWhitespace` trả `false` cho NBSP.
7. `allWhitespace.isBlank()` là `true`, và `strip()` biến chuỗi chỉ chứa whitespace thành `""`. Đây là hai cách kiểm tra nội dung trắng có liên quan, nhưng mục đích sử dụng khác nhau.

Hãy chú ý `<TAB>`, `<EM>`, `<NBSP>` và `_` chỉ là ký hiệu để **hiển thị kết quả trong chương trình demo**. Chúng không phải các ký tự mà `strip()` chèn vào chuỗi.

## 6. `strip` có thay đổi chuỗi gốc không?

Không. `String` trong Java là **immutable**: các phương thức `strip()`, `stripLeading()` và `stripTrailing()` trả về giá trị `String`; chúng không thay đổi nội dung của đối tượng `String` đang được tham chiếu bởi biến ban đầu.

```java
String name = "  Mai  ";
name.strip();
System.out.println("[" + name + "]"); // [  Mai  ]

name = name.strip();
System.out.println("[" + name + "]"); // [Mai]
```

Lời gọi `name.strip()` đầu tiên chỉ tính và trả kết quả rồi bị bỏ qua. Muốn dùng nội dung đã được cắt, cần **gán lại** cho biến hoặc lưu vào một biến mới:

```java
String raw = "  Mai  ";
String normalized = raw.strip();
```

Ở đây `raw` vẫn là `"  Mai  "`; `normalized` là `"Mai"`. Đừng dựa vào `==` để kiểm tra “đã strip chưa”: đặc tả quan tâm đến **giá trị văn bản**, không bảo đảm một quy tắc identity có ích cho nghiệp vụ. Dùng `equals()` khi so sánh nội dung.

## 7. `strip()` liên quan thế nào tới `isBlank()`?

`String.isBlank()`, cũng được thêm từ Java 11, trả `true` nếu chuỗi **rỗng hoặc chỉ gồm các code point được `Character.isWhitespace` nhận diện**.

```java
System.out.println(" \t\u2003 ".isBlank()); // true
System.out.println(" \t\u2003 ".strip().isEmpty()); // true
System.out.println("".isBlank());          // true
System.out.println("\u00A0".isBlank());    // false
```

Với các chuỗi Java thông thường, nhận xét sau rất hữu ích về mặt giá trị: nếu `s` chỉ gồm Unicode whitespace theo đúng tiêu chí `isBlank()` thì `s.strip()` là chuỗi rỗng. Tuy vậy, nên chọn API phù hợp với **ý định**:

- **`isBlank()`:** câu hỏi “chuỗi chỉ có whitespace hay không?”; trả `boolean`.
- **`strip()`:** yêu cầu tạo **giá trị văn bản mới** không còn whitespace ở hai đầu; trả `String`.
- **`isEmpty()`:** hỏi chiều dài chuỗi bằng 0 hay không, **không** đồng nghĩa chỉ chứa whitespace. `" ".isEmpty()` là `false`.

Một cách kiểm tra đầu vào phổ biến:

```java
static boolean hasMeaningfulText(String input) {
    return input != null && !input.isBlank();
}
```

Đoạn mã là phương thức minh họa, không phải chương trình độc lập. Nếu yêu cầu lưu một giá trị đã cắt rìa, dùng `input.strip()` khi đã kiểm tra `input != null`.

## 8. Dùng đúng phương thức trong từng tình huống

### Chuẩn hóa dữ liệu biểu mẫu

```java
String username = rawUsername.strip();
```

Nếu yêu cầu là xóa whitespace Unicode ở hai mép tên người dùng, `strip()` diễn đạt ý định tốt. Tuy nhiên, phải quy định rõ chính sách với NBSP và các ký tự định dạng vô hình: **strip không tự xóa mọi thứ trông như khoảng trắng**. Nếu hệ thống coi NBSP là khoảng trắng cần loại bỏ, quyết định đó thuộc quy tắc kiểm tra dữ liệu, không phải bảo đảm mặc định của API.

### Giữ indentation bên trái, bỏ trailing whitespace

```java
String cleanedLine = sourceLine.stripTrailing();
```

Hữu ích khi cần giữ thụt lề có ý nghĩa (ví dụ mã nguồn hoặc văn bản căn lề) nhưng bỏ khoảng trắng không mong muốn ở cuối. Với file có nhiều dòng, muốn xử lý từng dòng thì phải tách/duyệt từng dòng và áp dụng đúng chính sách, vì `stripTrailing()` trên toàn chuỗi chỉ xử lý **mép cuối của toàn chuỗi**, không tự làm sạch cuối **mọi dòng**.

### Bỏ phần thụt lề đầu nhưng giữ ký tự cuối

```java
String lineWithoutIndent = line.stripLeading();
```

Dùng khi indentation đầu là thứ cần bỏ nhưng whitespace cuối phải được giữ. Lưu ý text block của Java có thêm các phương thức khác liên quan indentation; không đồng nhất `stripLeading()` với `stripIndent()` hoặc `indent()`, vì chúng có những quy tắc riêng và mục tiêu khác.

### Phân biệt làm sạch rìa với sửa nội dung trong chuỗi

```java
String data = " a   b ";
System.out.println(data.strip()); // a   b
```

Bài toán biến nhiều khoảng trắng giữa `a` và `b` thành một khoảng trắng cần bước xử lý riêng. Nếu phải giữ nguyên định dạng bên trong (tên nhiều thành phần, mã định danh, văn bản có cấu trúc), đừng tự động thay đổi whitespace nội bộ.

## 9. Các lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Hậu quả | Cách xử lý |
|---|---|---|
| Cho rằng `strip()` xóa mọi whitespace trong chuỗi | Các dấu cách/tab ở giữa vẫn còn | `strip()` chỉ áp dụng ở **rìa** |
| Cho rằng `stripLeading()` cũng bỏ phần đuôi | Kết quả vẫn có trailing whitespace | Dùng `strip()` hoặc kết hợp thêm `stripTrailing()` |
| Gọi `s.strip()` rồi vẫn dùng `s` mà không gán | Dữ liệu gốc không thay đổi | Gán lại hoặc lưu kết quả |
| Dùng `trim()` thay `strip()` khi đầu vào có Em Space | Không loại bỏ `U+2003` ở mép | Dùng `strip()` trong Java 11+ |
| Tưởng NBSP chắc chắn bị `strip()` xóa | Chuỗi vẫn có `U+00A0` | Kiểm tra code point và quy tắc chuẩn hóa |
| Cho rằng `Character.isSpaceChar` và `Character.isWhitespace` giống nhau | Nhận diện sai tập ký tự trắng | Áp dụng đúng `Character.isWhitespace` theo API `String.strip` |
| Dùng `strip()` để làm sạch trailing whitespace từng dòng trong văn bản nhiều dòng | Chỉ phần cuối **toàn chuỗi** bị xử lý | Duyệt dòng theo quy tắc mong muốn |
| Gọi `strip()` trên `null` | `NullPointerException` | Kiểm tra null hoặc xác định trước hợp đồng đầu vào |
| Dùng `strip()` để đo chuỗi có rỗng hay không mà không quan tâm kết quả | Cấp phát/xử lý không cần thiết trong một số ca | Dùng `isBlank()` khi chỉ cần `boolean` |
| Giả định mọi phiên bản Java đều có ba API | Không biên dịch trên Java 8 | Nâng JDK lên 11+ hoặc viết cách xử lý phù hợp với phiên bản cũ |

## 10. Bài tập tự kiểm tra

Cho dữ liệu:

```java
String a = "\t abc \t";
String b = "\u2003abc\u2003";
String c = "\u00A0abc\u00A0";
String d = "   ";
String e = " a  b ";
```

Hãy dự đoán:

1. `a.strip()`, `a.stripLeading()` và `a.stripTrailing()` giữ lại phía nào?
2. Vì sao `b.strip().equals("abc")` là `true` trong khi `b.trim().equals("abc")` là `false`?
3. `c.strip().equals("abc")` có trả về `true` không?
4. `d.strip().isEmpty()` và `d.isBlank()` có cùng kết quả không?
5. `e.strip()` còn mấy dấu cách ở giữa `a` và `b`?

**Đáp án:**

1. `a.strip()` là `"abc"`; `stripLeading()` là `"abc \t"`, `stripTrailing()` là `"\t abc"`.
2. `U+2003` được Java nhận diện là whitespace; `trim()` chỉ loại đơn vị mã `<= U+0020`.
3. **Không**. NBSP `U+00A0` không thuộc nhóm được `Character.isWhitespace` chấp nhận, nên vẫn ở đầu và cuối.
4. Cả hai biểu thức đều là `true`; `strip()` trả chuỗi rỗng, `isBlank()` trực tiếp kiểm tra chỉ chứa whitespace.
5. Vẫn còn **hai** dấu cách ở giữa vì `strip()` không sửa nội dung bên trong.

## 11. Tài liệu chính thức

- [Java SE 17 — `String.strip()`, `stripLeading()`, `stripTrailing()`, `trim()` và `isBlank()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java SE 17 — `Character.isWhitespace(int)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html#isWhitespace(int))

**Ghi nhớ:** Dùng `strip()` để bỏ Java whitespace ở **hai mép**, `stripLeading()` chỉ ở **đầu**, `stripTrailing()` chỉ ở **cuối**. Chúng dùng quy tắc Unicode `Character.isWhitespace`, không đồng nghĩa “mọi ký tự trông trắng”, và không sửa khoảng trắng ở giữa. So với `trim()`, sự khác nhau nằm ở **tập ký tự được coi là có thể loại bỏ**, không chỉ ở tên phương thức.
