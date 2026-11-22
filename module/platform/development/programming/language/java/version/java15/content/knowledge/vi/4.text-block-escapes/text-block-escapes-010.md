# Kiểm thử xuống dòng cuối, khoảng trắng cuối và dấu nháy trong Java text block

## 1. Mục tiêu của bài

Khi dùng **text block** (chuỗi nhiều dòng viết bằng ba dấu nháy đôi `"""`) để lưu JSON, HTML, SQL, thông điệp hay dữ liệu kiểm thử, hai đoạn mã trông gần giống nhau vẫn có thể tạo ra hai giá trị `String` khác nhau. Sai khác thường nằm ở **ký tự xuống dòng cuối chuỗi**, **dấu cách cuối dòng** và **dấu nháy đôi**.

Sau bài này, bạn có thể:

- Xác định chính xác có bao nhiêu ký tự `\n` ở cuối text block, bao gồm trường hợp không có ký tự xuống dòng cuối.
- Giữ dấu cách cuối dòng bằng escape `\s`; hiểu vì sao dấu cách nguồn cuối dòng thường bị loại bỏ.
- Viết chuỗi chứa một, hai, ba dấu nháy đôi liên tiếp mà không vô tình đóng text block.
- Phân biệt ký tự dữ liệu với dấu nháy `"""` dùng làm delimiter, đồng thời kiểm tra trường hợp dữ liệu kết thúc ngay bằng `"`.
- Viết phép thử **so sánh giá trị `String` chính xác**, báo lỗi có thể đọc được và chạy được với mức ngôn ngữ Java 15.

Text blocks chính thức có mặt từ **Java 15**, tiếp tục là cú pháp Java thông dụng ngày nay. Các ví dụ dùng các quy tắc còn hiệu lực của Java và không dựa vào API đã bị bỏ hoặc tính năng preview.

## 2. Ba bước chuyển đổi ảnh hưởng trực tiếp đến kết quả

Theo *Java Language Specification, §3.10.6*, Java xử lý **nội dung nguồn** của text block theo đúng thứ tự:

1. Chuẩn hóa `CRLF` hoặc `CR` của tệp nguồn về **LF** (ký tự `\n`).
2. Loại bỏ **incidental whitespace**: mức căn lề chung, whitespace cuối dòng nguồn và whitespace trên các dòng chỉ gồm khoảng trắng, tương đương quy tắc `String.stripIndent()`.
3. Diễn giải escape cuối cùng: `\s` thành dấu cách, `\"` thành dấu `"`, `\t` thành tab, `\n` thành LF; một dấu gạch chéo ngược đứng **ngay trước line terminator** sẽ bỏ line terminator đó.

Do escape chỉ được dịch **sau** khi loại bỏ khoảng trắng nguồn, `\s` là cách rõ ràng để biểu thị dấu cách có ý nghĩa nằm ở cuối dòng. Tương tự, dấu `\"` giúp chứa dấu nháy đôi trong chuỗi mà không khiến ba dấu `"""` liên tiếp trong nguồn bị hiểu là ký hiệu đóng.

Điểm mấu chốt: **kiểm thử giá trị đã được tạo**, không chỉ đếm dấu cách và dấu xuống dòng bằng mắt trong editor. Mọi `String` thu được từ text block có thể được so sánh trực tiếp với một string literal thông thường bằng `equals`.

## 3. Kiểm thử ký tự xuống dòng cuối

### 3.1. Dấu đóng nằm ở dòng riêng: có newline cuối

```java
String withFinalLf = """
        apple
        """;
```

Giá trị tương đương: `"apple\n"`. Dấu mở `"""` bắt buộc theo sau bởi một line terminator; line terminator **ngay sau dấu mở** chỉ là phần của opening delimiter, không tạo thêm dòng trống ở đầu chuỗi. Ngược lại, newline sau `apple` nằm trong nội dung vì dấu đóng ở dòng tiếp theo.

### 3.2. Dấu đóng ngay sau nội dung: không có newline cuối

```java
String withoutFinalLf = """
        apple""";
```

Giá trị tương đương: `"apple"`. Vị trí dấu đóng quyết định ở đây **có** hay **không có** một newline cuối. Không kết luận chỉ từ việc dùng dấu `"""` rằng text block luôn luôn kết thúc bằng `\n`.

### 3.3. Dòng rỗng trước dấu đóng: thêm newline cuối nữa

```java
String withTwoLfs = """
        apple

        """;
```

Giá trị tương đương: `"apple\n\n"`. Dòng trống vẫn có ý nghĩa đối với số ký tự xuống dòng, dù các dấu cách/tab nằm trên chính dòng trống có thể bị loại bỏ.

### 3.4. Escape nối dòng: bỏ một line terminator cụ thể

```java
String joined = """
        ap\
        ple
        """;
```

Giá trị tương đương: `"apple\n"`. Dấu `\` đứng ngay trước line terminator làm *nối* `ap` và `ple`. Vì dấu đóng vẫn ở dòng riêng sau `ple`, chuỗi **vẫn** có newline ở cuối. Đừng nhầm việc bỏ newline **ở vị trí nối dòng** với việc xóa mọi newline của text block.

Nếu muốn giữ nội dung ở nhiều dòng mã Java nhưng giá trị cuối không có newline, hãy kiểm tra vị trí escape và dấu đóng trong đúng trường hợp đó, thay vì giả định trình biên dịch sẽ “tự trim”.

### 3.5. So sánh kỳ vọng

| Mẫu nguồn | `String` kỳ vọng | Số ký tự LF cuối |
| --- | --- | ---: |
| `apple` và dấu đóng ở dòng kế | `"apple\n"` | 1 |
| `apple"""` trên cùng dòng cuối | `"apple"` | 0 |
| `apple`, một dòng trống, rồi dấu đóng | `"apple\n\n"` | 2 |
| `ap\` rồi `ple` rồi dấu đóng ở dòng kế | `"apple\n"` | 1 |

Nếu giá trị được dùng để tạo tệp hoặc snapshot, một newline cuối có thể làm kết quả so khớp toàn bộ khác đi; khi ghi ra tệp còn cần xét **mã hóa ký tự** do lời gọi ghi tệp lựa chọn. `System.out.println(value)` tự thêm dấu kết thúc dòng để hiển thị, nên không thể nhìn console rồi kết luận newline ấy thuộc `value`.

## 4. Kiểm thử dấu cách cuối dòng

Trong text block, dấu cách/tab thật được gõ ở cuối dòng mã nguồn thường bị xóa ở bước loại bỏ incidental whitespace. Điều này tránh việc trình soạn thảo xóa trailing spaces làm thay đổi chuỗi thông thường. Tuy nhiên dữ liệu kiểm thử, dòng fixed-width, chữ ký bản tin hoặc nội dung phải khớp nguyên văn có thể **cần giữ** trailing spaces.

Dùng `\s` (mỗi `\s` tương ứng **một dấu cách U+0020**):

```java
String padded = """
        X\s\s
        """;
```

Giá trị chính xác là `"X  \n"`: sau chữ `X` là **hai dấu cách**, sau đó mới tới LF. Vì escape được dịch ở bước cuối, hai dấu cách này không bị bước loại bỏ whitespace nguồn xóa đi.

**Phân biệt ba trường hợp:**

| Trong text block | Kết quả | Ý nghĩa |
| --- | --- | --- |
| Dấu cách thực sự gõ cuối dòng nguồn | Thường bị loại bỏ | Incidental trailing whitespace |
| `\s` ở cuối dòng | Dấu cách được giữ | Có chủ ý đưa U+0020 vào dữ liệu |
| `\t` ở cuối dòng | Tab được giữ | Có chủ ý đưa U+0009 vào dữ liệu |

Khi phải ghi chính xác một dấu cách sau dấu nháy, dấu phẩy hoặc cuối trường, dùng escape giúp người review dễ nhận ra yêu cầu dữ liệu. Không dùng `String.strip()` hoặc `stripTrailing()` trên chuỗi vừa tạo nếu các ký tự cuối đó là dữ liệu cần giữ: hai phương thức này có thể xóa whitespace của **giá trị** thực sự.

Để kiểm tra giá trị, viết điều kiện có dấu cách trong expected literal:

```java
if (!padded.equals("X  \n")) {
    throw new AssertionError("Hai dau cach cuoi dong da thay doi");
}
```

Câu lệnh kiểm tra trên là đoạn bổ sung sau khi tạo `padded`, không phải chương trình Java đầy đủ đứng độc lập. Trên editor, bật chế độ hiển thị whitespace hoặc dùng hàm hiển thị ký tự ẩn trong phần mã chạy hoàn chỉnh bên dưới.

### Lưu ý về `\u0020`

Đừng dùng Unicode escape `\u0020` trong mã nguồn để thay `\s` nhằm giữ khoảng trắng cuối dòng: Java xử lý Unicode escapes từ rất sớm trước khi biên dịch nội dung text block. Với nhu cầu này, `\s` phù hợp và dễ hiểu hơn. Escape octal `\040` cũng biểu diễn space theo JLS, nhưng `\s` thể hiện mục đích trực tiếp hơn trong mã Java hiện nay.

## 5. Kiểm thử dấu nháy đôi

### 5.1. Một hoặc hai dấu `"` bên trong nội dung

Không cần escape dấu nháy đôi đơn lẻ hay cặp hai dấu khi chúng không tạo thành ba dấu liên tiếp:

```java
String message = """
        She said "ok".
        """;

String twoAtOnce = """
        ""quote""
        """;
```

Giá trị lần lượt là:

- `"She said \"ok\".\n"`.
- `"\"\"quote\"\"\n"`.

Trong hai biểu thức **kỳ vọng** viết ở trên, `\"` là cú pháp của *string literal Java thông thường* dùng để mô tả ký tự nháy đôi. Trong nội dung **text block**, dấu `"` đơn lẻ không cần escape.

### 5.2. Ba dấu `"""` liên tiếp là trường hợp đặc biệt

Trong mã nguồn text block, ba dấu nháy đôi liên tiếp có thể bị nhận diện là **closing delimiter**. Để chuỗi chứa đúng ba dấu nháy đôi, hãy escape ít nhất một dấu trong cụm đó:

```java
String threeQuotes = """
        \"""
        """;
```

Giá trị chính xác: `"\"\"\"\n"` (ba dấu nháy đôi rồi một LF).

Giải thích chuỗi ký tự trên dòng nội dung: `\"` biểu diễn dấu `"` đầu tiên, hai dấu `""` tiếp theo là nội dung bình thường. Vì vậy trình phân tích không gặp một closing delimiter `"""` tại vị trí đó.

Khi nhúng **mã Java có text block khác**, áp dụng nguyên tắc tương tự: escape ít nhất một dấu trong mỗi cụm ba dấu nháy liên tiếp cần xuất hiện như **dữ liệu**. Không cần escape tất cả các dấu nháy trong tài liệu nhiều dòng.

### 5.3. Dấu nháy là ký tự cuối cùng của dữ liệu và không có newline

Tình huống dễ nhầm: cần kết quả `answer"` nhưng lại muốn closing delimiter nằm **ngay sau ký tự `"` cuối cùng**. Dùng escape ở dấu nháy thuộc dữ liệu:

```java
String quoteAtEnd = """
        answer\"""";
```

Giá trị là `"answer\""`, độ dài **7** ký tự: 6 chữ cái trong `answer` và một dấu nháy đôi; **không** có `\n` cuối chuỗi.

Nếu đặt các dấu nháy liên tiếp mà không escape thích hợp, trình phân tích cú pháp có thể coi ba dấu đầu là dấu đóng rồi gặp dấu nháy thừa, dẫn đến lỗi biên dịch. Đây là lỗi cú pháp **khi viết nguồn**; nó khác việc phép thử `equals` phát hiện giá trị không đúng **sau khi biên dịch thành công**.

## 6. Chương trình kiểm thử chạy được trên Java 15

Lưu **nguyên vẹn** đoạn mã sau vào tệp `TextBlockBoundaryTest.java`. Chương trình chỉ dùng API chuẩn, không cần thư viện kiểm thử bên ngoài. Tất cả expected strings đều biểu diễn rõ newline, space và quote. Khi bất kỳ phép thử nào không khớp, chương trình ném `AssertionError` và in ra cả hai giá trị với ký tự ẩn được biểu thị bằng ký hiệu nhìn thấy.

```java
public final class TextBlockBoundaryTest {
    private static int checks;

    public static void main(String[] args) {
        String finalLf = """
                hello
                """;
        String noFinalLf = """
                hello""";
        String doubleFinalLf = """
                hello

                """;
        String continued = """
                he\
                llo
                """;
        String twoSpaces = """
                X\s\s
                """;
        String ordinaryQuotes = """
                She said "ok".
                """;
        String doubleQuotes = """
                ""quote""
                """;
        String tripleQuotes = """
                \"""
                """;
        String quoteAtEnd = """
                answer\"""";

        check("final-lf", finalLf, "hello\n");
        check("no-final-lf", noFinalLf, "hello");
        check("two-final-lf", doubleFinalLf, "hello\n\n");
        check("continued", continued, "hello\n");
        check("trailing-spaces", twoSpaces, "X  \n");
        check("ordinary-quotes", ordinaryQuotes, "She said \"ok\".\n");
        check("double-quotes", doubleQuotes, "\"\"quote\"\"\n");
        check("triple-quotes", tripleQuotes, "\"\"\"\n");
        check("quote-at-end", quoteAtEnd, "answer\"");
        System.out.println("ALL " + checks + " CHECKS PASSED");
    }

    private static void check(String name, String actual, String expected) {
        if (!expected.equals(actual)) {
            throw new AssertionError(name + " expected " + show(expected)
                    + " but got " + show(actual));
        }
        checks++;
        System.out.println("PASS " + name);
    }

    private static String show(String value) {
        return "[" + value.replace("\\", "\\\\")
                          .replace(" ", "<SP>")
                          .replace("\r", "\\r")
                          .replace("\n", "\\n")
                          .replace("\t", "\\t") + "]";
    }
}
```

Biên dịch với JDK có hỗ trợ mục tiêu Java 15 và chạy chương trình:

```bash
javac --release 15 TextBlockBoundaryTest.java
java TextBlockBoundaryTest
```

**Stdout chính xác:**

```text
PASS final-lf
PASS no-final-lf
PASS two-final-lf
PASS continued
PASS trailing-spaces
PASS ordinary-quotes
PASS double-quotes
PASS triple-quotes
PASS quote-at-end
ALL 9 CHECKS PASSED
```

Chương trình đã được biên dịch với `javac --release 15` và chạy để xác minh chín ca kiểm thử. Nếu dùng JDK khác, trước hết kiểm tra `javac --help` để biết bản compiler đó hỗ trợ những mức `--release` nào. Java 15 là mốc xuất hiện chính thức của text block; có thể dùng tính năng này ở các bản Java hiện đại mà không bật preview.

### Tại sao hàm `check` hữu ích?

- `expected.equals(actual)` kiểm tra **toàn bộ** dữ liệu, kể cả whitespace vô hình, thay vì kiểm tra `contains` hoặc dựa vào `println`.
- `show` biến space thành `<SP>`, newline thành `\n`, tab thành `\t`, CR thành `\r` và hiển thị backslash thành `\\`. Ký hiệu chỉ dùng trong thông báo lỗi, không sửa giá trị đang được kiểm thử.
- Dùng `AssertionError` trực tiếp khiến chương trình kết thúc không thành công khi sai, kể cả khi không chạy với tùy chọn `-ea`. Nếu thay bằng từ khóa `assert` của Java, phải biết rằng các `assert` statement thường bị vô hiệu hóa nếu không bật assertions lúc chạy.
- Tên file phải đúng `TextBlockBoundaryTest.java` vì có lớp `public final class TextBlockBoundaryTest`.

## 7. Cách kiểm thử chính xác khi tích hợp trong dự án

Nếu dự án đã dùng framework test, tái sử dụng ý tưởng **kiểm tra toàn chuỗi**, thay vì dựa vào tên framework hay phiên bản phụ thuộc:

```java
// Ví dụ trong một phương thức test đã được cấu hình sẵn:
String actual = """
        name: "Lan"\s
        """;
String expected = "name: \"Lan\" \n";
if (!actual.equals(expected)) {
    throw new AssertionError("Text block thay doi whitespace hoac quotes");
}
```

Đoạn này minh họa nội dung một phương thức test; nó không phải một chương trình Java độc lập vì cần được đặt trong lớp/phương thức phù hợp. Với JUnit 5, có thể dùng `assertEquals(expected, actual)` thay điều kiện trên nếu dự án đã có thư viện test; cú pháp và dữ liệu kỳ vọng vẫn như nhau.

**Thứ tự kiểm tra thực tế:**

1. Xác định hợp đồng cần giữ: newline cuối **có hay không**, chính xác **bao nhiêu** space cuối dòng, và chính xác **bao nhiêu** dấu `"`.
2. Viết `expected` bằng ordinary string literal có escape rõ ràng (ví dụ `"x  \n"`, `"\"\"\"\n"`).
3. Viết text block thuận mắt nhưng đặt closing delimiter và `\s`/`\"` theo hợp đồng dữ liệu.
4. So sánh bằng `equals` hoặc assertion **toàn chuỗi**. Khi sai, hiển thị chuỗi bằng cách thay ký tự ẩn bằng các marker để tìm vị trí sai.
5. Với dữ liệu có định dạng nhạy cảm, chạy test trên phiên bản JDK thực tế và kiểm tra kết quả sau khi serializing/ghi file nếu chức năng có bước chuyển đổi tiếp theo.

Một phép thử chỉ kiểm tra `actual.trim().equals(expected.trim())` có thể cho kết quả **dương tính giả**: chính thao tác `trim()` đã làm mất khác biệt newline hoặc dấu cách mà bài test cần phát hiện. Tương tự, `strip()` và `stripTrailing()` có thể che lấp lỗi ở biên chuỗi.

## 8. Những nhầm lẫn phổ biến

| Hiểu nhầm | Điều đúng và cách kiểm thử |
| --- | --- |
| “Dùng text block thì luôn tự có newline cuối.” | Không. So sánh `"x\n"` và `"x"` khi đổi vị trí dấu đóng. |
| “Nhìn `println` là biết chuỗi chứa newline cuối.” | Không. `println` thêm line terminator; cần `equals` hoặc đọc `length()`, `charAt()`. |
| “Space gõ trực tiếp cuối dòng text block luôn được giữ.” | Không. Dùng `\s` và xác nhận bằng `equals("x  \n")`. |
| “Một dấu `"` trong text block luôn phải viết `\"`.” | Không. Dấu nháy đôi đơn thường được viết trực tiếp. |
| “Ba dấu `"""` trong nội dung cũng được viết trực tiếp.” | Dễ thành closing delimiter; escape ít nhất một dấu khi cần lưu chúng như dữ liệu. |
| “Text block giữ nguyên CRLF của tệp nguồn.” | Không. Line terminators của nguồn được chuẩn hóa về LF trước bước escape. |
| “Escape `\r` chắc chắn cũng biến thành LF.” | Không. Escape được giải mã cuối cùng, nên có thể tạo ký tự CR trong giá trị. |
| “Một khoảng trắng đầu dòng còn lại chắc hẳn là lỗi compiler.” | Không. Lề tương đối nhiều hơn mức incidental chung có thể là dữ liệu có chủ ý. |
| “Nếu `trim()` xong bằng nhau là đủ.” | Không đủ cho bài kiểm thử giá trị nguyên bản; đã xóa dấu cách/newline ở rìa. |

### Tình huống cần điều tra thêm

- **Tệp snapshot khác nhau dù nội dung nhìn giống:** xem số LF cuối và khả năng môi trường đã chuyển đổi LF sang CRLF khi ghi file.
- **Bản ghi fixed-width bị thiếu cột:** kiểm tra `\s` ở cuối những dòng phải đủ độ dài, không dùng `stripTrailing()` trước khi ghi.
- **JSON có dấu nháy nằm trong giá trị:** phân biệt quy tắc Java text block với quy tắc escape của **JSON**. Text block tạo ra chuỗi ký tự; nếu cần ký tự escape trong JSON, phải viết sao cho sau khi Java xử lý escape, JSON nhận được dữ liệu đúng.
- **Nhúng mã Java có delimiter `"""`:** escape một dấu trong cụm để nguồn Java bên ngoài không bị đóng sớm; kiểm thử dữ liệu thu được chứa đúng ba dấu.
- **Editor tự căn lề:** xem editor đã đổi vị trí dấu đóng, lề tương đối hoặc xóa dấu cách nguồn chưa. Dùng phép thử `equals` để phát hiện thay đổi có tác động tới chuỗi.

## 9. Bài tập tự kiểm tra

**Bài 1.** So sánh hai đoạn:

```java
String a = """
        id
        """;
String b = """
        id""";
```

`a.equals(b)` trả gì? **`false`**, vì `a` là `"id\n"`, `b` là `"id"`. Đây là khác biệt dữ liệu thực, không chỉ cách hiển thị.

**Bài 2.** Bạn cần dữ liệu `"A \n"` (chữ `A`, một dấu cách, một LF). Viết thế nào để dấu cách cuối được giữ? **Đáp án:**

```java
String a = """
        A\s
        """;
```

**Bài 3.** Bạn cần chuỗi chứa đúng `"""` **và không có newline cuối**. Có thể dùng một dấu nháy có escape rồi closing delimiter đặt cùng dòng không? **Có**, nhưng phải kiểm thử giá trị chính xác và đếm dấu nháy trong nguồn thật cẩn thận. Cách dễ review hơn khi không yêu cầu cùng dòng là tách dòng delimiter rồi loại newline có chủ đích bằng cách bố trí nguồn phù hợp.

**Bài 4.** Sau khi `String value` được tạo, phép so sánh `value.stripTrailing().equals(expected.stripTrailing())` có phù hợp để phát hiện lỗi trailing spaces không? **Không**, vì nó bỏ chính dữ liệu cần so sánh.

**Bài 5.** Trong kết quả `"She said \"ok\".\n"`, có bao nhiêu dấu nháy đôi **thuộc dữ liệu**? **Hai**: một trước `ok` và một sau `ok`. Chúng không phải opening/closing delimiter.

**Tiêu chí đạt:** với từng text block, hãy viết được ordinary string literal tương đương, kiểm tra `equals` đúng với dữ liệu thực, mô tả rõ ký tự LF cuối, dấu cách cuối dòng và dấu nháy đôi là dữ liệu hay delimiter.

## 10. Tài liệu chính thức để tra cứu khi cần

- [Java Language Specification, Java SE 15, §3.10.6 — Text Blocks](https://docs.oracle.com/javase/specs/jls/se15/html/jls-3.html#jls-3.10.6): quy tắc opening/closing delimiter, chuỗi tạo thành và ba bước biến đổi; đặc biệt có ví dụ escape dấu nháy kép.
- [Java Language Specification, Java SE 15, §3.10.7 — Escape Sequences](https://docs.oracle.com/javase/specs/jls/se15/html/jls-3.html#jls-3.10.7): ý nghĩa chính xác của `\s`, `\"`, `\\`, `\n` và escape nối dòng.
- [Oracle Java Text Blocks Guide](https://docs.oracle.com/en/java/javase/25/language/text-blocks.html): ví dụ trực quan về final newline, incidental whitespace, trailing spaces và ba dấu nháy đôi.
- [Javadoc `String` của Java SE 15](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/String.html): đối chiếu `equals`, `stripIndent`, `strip` và các API liên quan khi nhắm tương thích Java 15.