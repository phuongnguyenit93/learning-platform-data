# Chuỗi rỗng và ký tự xuống dòng ở cuối khi dùng String.lines() trong Java



## 1. Vì sao kết quả số dòng dễ gây nhầm lẫn?

Trong Java, `String.lines()` (có từ Java 11) tạo một `Stream<String>` chứa các **dòng văn bản** của chuỗi. Mỗi phần tử là nội dung một dòng **không bao gồm ký tự kết thúc dòng**. Tuy nhiên, **chuỗi rỗng**, **dòng rỗng**, và **chuỗi có ký tự xuống dòng ở cuối** không phải ba trường hợp giống nhau.

Xét ba đầu vào:

```text
""          chuỗi có 0 ký tự
"Java\n"    chữ Java, rồi một ký tự xuống dòng LF
"Java\n\n"  chữ Java, rồi hai ký tự LF liên tiếp
```

Trong đoạn trên, `\n` là cách biểu diễn ký tự xuống dòng trong Java string literal, không phải hai ký tự dấu gạch chéo ngược và chữ `n`.

Kết quả khác nhau:

- `"".lines()` tạo **0 phần tử**: không có dòng nào.
- `"Java\n".lines()` tạo **1 phần tử** `"Java"`: dấu kết thúc dòng cuối cùng không tự tạo thêm dòng rỗng.
- `"Java\n\n".lines()` tạo **2 phần tử**: `"Java"` và `""`; dấu LF thứ hai kết thúc một dòng rỗng sau `Java`.

Điều quan trọng nhất của bài: **`String.lines()` không tự thêm một chuỗi rỗng chỉ vì đầu vào kết thúc bằng dấu xuống dòng.** Nhưng khi có **nhiều dấu kết thúc dòng liên tiếp**, chúng vẫn biểu thị những dòng rỗng có thật.

## 2. Bảng trường hợp biên

Để nhìn rõ, mỗi giá trị dòng bên dưới được đặt trong dấu nháy đôi. Ký hiệu `[]` nghĩa là **không có phần tử**, còn `[""]` nghĩa là **có một phần tử là chuỗi rỗng**.

| Chuỗi đầu vào (Java literal) | Các phần tử từ `lines().toList()` | Số dòng |
| --- | --- | ---: |
| `""` | `[]` | 0 |
| `"Java"` | `["Java"]` | 1 |
| `"Java\n"` | `["Java"]` | 1 |
| `"Java\n\n"` | `["Java", ""]` | 2 |
| `"\n"` | `[""]` | 1 |
| `"\n\n"` | `["", ""]` | 2 |
| `"\r\n"` | `[""]` | 1 |
| `"one\n\ntwo"` | `["one", "", "two"]` | 3 |
| `"one\r\ntwo\r\n"` | `["one", "two"]` | 2 |
| `"first\nsecond"` | `["first", "second"]` | 2 |

Giải thích hai trường hợp đặc biệt:

- `"\n"` là một **dòng rỗng có dấu kết thúc**: stream chứa một phần tử `""`. Còn `""` không chứa dòng nào, nên stream rỗng.
- `"Java\n\n"` gồm dòng `Java` kết thúc bởi dấu LF thứ nhất, sau đó một **dòng rỗng** kết thúc bởi dấu LF thứ hai. Dấu LF thứ hai cũng là ký tự kết thúc cuối cùng nên không phát sinh dòng rỗng thứ ba.

**Số ký tự xuống dòng không luôn bằng số dòng.** Với `"Java\n"` có một LF và một dòng; với `"Java"` không có LF nhưng vẫn có một dòng. Với chuỗi rỗng thì có 0 dòng.

## 3. Chương trình Java 17+ hoàn chỉnh

Lưu đoạn mã sau thành tệp `StringLinesEdgeCases.java`:

```java
import java.util.Arrays;
import java.util.List;

public class StringLinesEdgeCases {
    private static void show(String label, String input) {
        List<String> visible = input.lines()
                .map(line -> "\"" + line + "\"")
                .toList();

        System.out.println(label + " => count=" +
                visible.size() + ", lines=" + visible);
    }

    public static void main(String[] args) {
        show("empty", "");
        show("no terminator", "Java");
        show("one trailing LF", "Java\n");
        show("two trailing LF", "Java\n\n");
        show("only LF", "\n");
        show("two LF", "\n\n");
        show("only CRLF", "\r\n");
        show("mixed blanks", "one\n\ntwo");
        show("CRLF final", "one\r\ntwo\r\n");

        String[] byDefault = "Java\n".split("\\R");
        String[] keepTrailing = "Java\n".split("\\R", -1);
        System.out.println("split default count: " + byDefault.length);
        System.out.println("split keep count: " + keepTrailing.length);
        System.out.println("split keep last empty: " +
                keepTrailing[1].isEmpty());
        System.out.println("empty split count: " +
                "".split("\\R", -1).length);

        String original = "one\r\ntwo\r\n";
        String reconstructed = String.join("\n",
                original.lines().toList());
        System.out.println("reconstructed equals original: " +
                reconstructed.equals(original));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac StringLinesEdgeCases.java
java StringLinesEdgeCases
```

Kết quả chuẩn:

```text
empty => count=0, lines=[]
no terminator => count=1, lines=["Java"]
one trailing LF => count=1, lines=["Java"]
two trailing LF => count=2, lines=["Java", ""]
only LF => count=1, lines=[""]
two LF => count=2, lines=["", ""]
only CRLF => count=1, lines=[""]
mixed blanks => count=3, lines=["one", "", "two"]
CRLF final => count=2, lines=["one", "two"]
split default count: 1
split keep count: 2
split keep last empty: true
empty split count: 1
reconstructed equals original: false
```

Hàm `show` bọc nội dung mỗi dòng trong dấu nháy đôi để ta phân biệt được `[]` với `[""]`. Đây chỉ là cách hiển thị dễ quan sát khi học; bản thân `String.lines()` trả về dòng gốc, không tự thêm dấu nháy.

`toList()` là phương thức `Stream.toList()` có trong Java 16+, vì vậy chương trình dùng Java 17 chạy được. Trước Java 16, có thể thu thập thành danh sách bằng `collect(Collectors.toList())`. Phần quan trọng của bài, `String.lines()`, đã có từ Java 11.

### Từ dòng sang trường tách

Ở đây chỉ cần biết `lines()` không tạo thêm dòng sau newline cuối, trong khi `split("\\R", -1)` có thể giữ trường rỗng phía sau dấu phân cách. `split("\\R")` mặc định bỏ các trường rỗng cuối; với chính chuỗi `""`, `split` vẫn trả một phần tử rỗng, còn `lines()` trả stream rỗng. Cách `limit` dương và tập ngắt dòng Unicode thuộc bài **Khác biệt giữa lines và split với limit**.

## 4. Phân biệt chuỗi rỗng, dòng rỗng và dòng chỉ có khoảng trắng

Ba khái niệm thường được kiểm tra bằng những API khác nhau:

- **Chuỗi đầu vào rỗng:** `input.isEmpty()` trả về `true` khi độ dài chuỗi bằng 0.
- **Dòng rỗng:** với từng `line` từ `input.lines()`, `line.isEmpty()` trả về `true` nếu dòng có 0 ký tự.
- **Dòng trắng:** `line.isBlank()` trả về `true` nếu dòng chỉ gồm khoảng trắng theo định nghĩa của Java, hoặc rỗng.

Ví dụ:

```java
String text = "first\n \n\nlast\n";

long allLines = text.lines().count();
long emptyLines = text.lines()
        .filter(String::isEmpty)
        .count();
long blankLines = text.lines()
        .filter(String::isBlank)
        .count();

System.out.println(allLines);   // 4
System.out.println(emptyLines); // 1
System.out.println(blankLines); // 2
```

Giải thích: các dòng lần lượt là `"first"`, `" "` (một dấu cách), `""` và `"last"`. Dòng `" "` là **blank** nhưng không **empty**. Dấu `\n` cuối cùng không tạo ra dòng rỗng thứ năm.

**Lưu ý:** mỗi lần gọi `text.lines()` ở ví dụ tạo một stream mới. Một `Stream` đã dùng terminal operation như `count()` sẽ bị tiêu thụ; không gọi tiếp `count()` trên cùng đối tượng stream.

## 5. Muốn giữ chính xác ký tự xuống dòng cuối phải làm gì?

`String.lines()` trả lại **nội dung dòng** và loại bỏ dấu kết thúc của từng dòng. Sau khi tách, ta không còn biết từ danh sách dòng rằng đầu vào ban đầu dùng `\n`, `\r`, hay `\r\n`, cũng không luôn biết có ký tự xuống dòng ở cuối hay không.

Ví dụ:

```java
String original = "one\r\ntwo\r\n";
String reconstructed = String.join("\n",
        original.lines().toList());

System.out.println(reconstructed.equals(original)); // false
```

`reconstructed` là `"one\ntwo"`; nó không còn CRLF và không còn terminator sau `two`. Vì vậy, **không dùng `String.join("\n", text.lines().toList())` để khẳng định khôi phục nguyên trạng văn bản**.

Nếu chỉ muốn biết chuỗi gốc có kết thúc bằng một trong ba loại terminator được `String.lines()` nhận biết, kiểm tra trực tiếp chuỗi gốc **trước khi duyệt dòng**:

```java
boolean endsWithLineTerminator =
        text.endsWith("\n") || text.endsWith("\r");
```

Biểu thức đó cũng trả về `true` cho CRLF, vì `"\r\n"` kết thúc bằng `"\n"`. Nếu muốn phân biệt chính xác ba kiểu để ghi lại:

```java
String terminal;
if (text.endsWith("\r\n")) {
    terminal = "\r\n";
} else if (text.endsWith("\n")) {
    terminal = "\n";
} else if (text.endsWith("\r")) {
    terminal = "\r";
} else {
    terminal = "";
}
```

Đây chỉ là phép kiểm tra **terminator cuối**, không lưu được toàn bộ dấu kết thúc khác nhau bên trong chuỗi. Nếu yêu cầu giữ nguyên byte, giữ nguyên định dạng xuống dòng hỗn hợp hoặc tái tạo văn bản không sai một ký tự, hãy giữ nguyên nguồn ban đầu hoặc dùng bộ phân tích có bảo toàn delimiter; không chỉ dựa vào `lines()`.

### 9.1. Trường hợp nhập liệu hoặc xử lý bản ghi

Với tài liệu văn bản thông thường, newline cuối thường chỉ khép lại dòng cuối. Với một giao thức hay định dạng mà **phần sau delimiter cuối** được coi là một bản ghi/trường rỗng, nghiệp vụ có thể cần giữ phần tử rỗng này; khi đó cách chia dùng `split("\\R", -1)` (sau khi xác nhận phạm vi terminator phù hợp) sẽ gần với mô hình “các trường được ngăn bằng delimiter” hơn.

Ví dụ, đầu vào `"A\nB\n"` có:
- Hai dòng theo `String.lines()`: `A` và `B`.
- Ba phần tử theo `split("\\R", -1)`: `A`, `B` và `""`.

Hai kết quả đều có lý do riêng. Hãy quyết định trước dấu kết thúc cuối đại diện cho **kết thúc dòng** hay **dấu phân cách tạo trường rỗng** trong định dạng dữ liệu cụ thể.

## 6. Bài tập tự kiểm tra

Trước khi chạy mã, đoán kết quả các biểu thức:

| Biểu thức | Kết quả |
| --- | ---: |
| `"".lines().count()` | `0` |
| `"\r".lines().count()` | `1` |
| `"\r\n".lines().count()` | `1` |
| `"x\r\n".lines().count()` | `1` |
| `"x\r\n\r\n".lines().count()` | `2` |
| `"x\n\n\ny".lines().count()` | `4` |
| `" x \n".lines().findFirst().orElse("?")` | `" x "` |
| `"x\n".split("\\R", -1).length` | `2` |

Thực hành thêm: viết một hàm nhận chuỗi đầu vào, báo số dòng tất cả, số dòng rỗng, số dòng chỉ có khoảng trắng và một boolean cho biết đầu vào có kết thúc bằng LF hoặc CR hay không. Hãy thử cả `""`, `"\n"`, `"a\n"`, `"a\n\n"`, `"a\r\nb\r\n"`.

## 7. Ghi nhớ

- **`String.lines()` với chuỗi rỗng cho 0 dòng**, còn chuỗi gồm duy nhất một LF cho 1 dòng rỗng.
- Một **terminator duy nhất ở cuối** không sinh thêm phần tử rỗng; **hai terminator liên tiếp** vẫn giữ dòng rỗng nằm giữa chúng.
- `String.lines()` nhận `\n`, `\r`, `\r\n`; regex `\R` nhận tập linebreak rộng hơn.
- **`split("\\R", -1)` giữ phần tử rỗng cuối**, khác với cách chia dòng của `String.lines()`; với chuỗi rỗng, `split` cho một phần tử rỗng.
- `isEmpty()` và `isBlank()` phục vụ hai cách hiểu khác nhau về dòng rỗng và dòng trắng.
- `String.lines()` loại các dấu kết thúc dòng; nếu cần biết hoặc bảo toàn newline cuối và kiểu CR/LF/CRLF, phải giữ thông tin từ đầu vào gốc.
