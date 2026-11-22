# `String.trim()` và tập ký tự không vượt `U+0020` trong Java

## 1. `trim()` dùng để làm gì?

Khi nhận chuỗi có khoảng trắng hoặc một số ký tự điều khiển ở **đầu và cuối**, ta thường cần loại bỏ chúng trước khi hiển thị, kiểm tra hoặc xử lý tiếp. Lớp `java.lang.String` có phương thức:

```java
public String trim()
```

`trim()` trả về một chuỗi có nội dung được cắt bỏ từ **đầu** và **cuối** theo quy tắc xác định bởi Java: loại bỏ liên tiếp những `char` có giá trị **không lớn hơn `U+0020`** (tức `0x0000` đến `0x0020`, bao gồm hai đầu). Phương thức không xóa các ký tự tương tự nếu chúng nằm **ở giữa** nội dung.

```java
String original = " \tJava Core\n ";
String cleaned = original.trim();

System.out.println("[" + cleaned + "]"); // [Java Core]
```

Giá trị trả về là `"Java Core"`; dấu cách đầu, tab `\t`, ký tự xuống dòng `\n` và dấu cách cuối bị loại. Dấu cách **giữa** hai từ vẫn còn.

**Điểm mấu chốt:** Tên `trim` dễ làm ta nghĩ nó xử lý toàn bộ “khoảng trắng Unicode”. Thực tế, tiêu chí của `String.trim()` chính là giá trị số của **UTF-16 `char`**, không phải một phép phân loại “whitespace” theo Unicode.

## 2. Quy tắc chính xác: mọi `char` có giá trị `<= U+0020`

`U+0020` là Unicode code point của dấu cách ASCII thông thường (`SPACE`), tương ứng giá trị thập phân `32`. Với `String.trim()`, những `char` có giá trị **từ `0` đến `32`** được xem là có thể cắt bỏ ở rìa chuỗi.

Nói cách khác:

```text
Khoảng giá trị char bị trim ở đầu/cuối:

U+0000  U+0001  ...  U+001F  U+0020
  0       1              31      32
|----------------------------------|
         Được loại bỏ ở rìa
```

Một số ví dụ:

| Ký tự / mã | Giá trị | `trim()` loại ở đầu/cuối? | Ý nghĩa |
|---|---:|---|---|
| `U+0000` (NUL) | 0 | Có | Ký tự điều khiển NUL, không phải dấu cách |
| `U+0009` (`\t`) | 9 | Có | Tab ngang |
| `U+000A` (`\n`) | 10 | Có | Line feed |
| `U+000D` (`\r`) | 13 | Có | Carriage return |
| `U+001F` | 31 | Có | Ký tự điều khiển |
| `U+0020` (`' '`) | 32 | Có | Dấu cách ASCII |
| `U+0021` (`'!'`) | 33 | Không | Dấu chấm than |
| `U+00A0` | 160 | Không | NO-BREAK SPACE (NBSP) |
| `U+2003` | 8195 | Không | EM SPACE |
| `U+3000` | 12288 | Không | IDEOGRAPHIC SPACE |

**Không chỉ có space, tab và newline:** Ký tự NUL (`U+0000`) cũng nằm trong khoảng bị `trim()` xóa, dù nó **không được coi là whitespace** theo `Character.isWhitespace(...)`. Đây là lý do định nghĩa “xóa whitespace” tuy thuận tiện nhưng chưa mô tả đúng toàn bộ hợp đồng của `trim()`.

Ngược lại, NBSP hoặc EM SPACE có thể nhìn giống dấu cách, nhưng giá trị `char` của chúng **lớn hơn** `U+0020`; `trim()` không xóa chúng.

### Vì sao nói về `char`, không chỉ “ký tự Unicode”?

Các API chỉ số và phép xử lý cơ bản của `String` trong Java được diễn đạt theo đơn vị mã **UTF-16** (`char`). Một `char` có giá trị không dấu từ `0` đến `65535`. `trim()` kiểm tra những đơn vị `char` ở rìa theo ngưỡng `U+0020`. Các ký tự Unicode bổ trợ như nhiều emoji được biểu diễn bằng hai `char` surrogate với giá trị lớn hơn ngưỡng này, vì vậy không bị cắt bỏ chỉ vì chúng là ký tự đặc biệt.

## 3. `trim()` kiểm tra từ hai đầu vào giữa

Có thể hình dung phương thức tiến hành theo các bước:

1. Bắt đầu từ ký tự đầu tiên. Khi ký tự đó có giá trị `<= U+0020`, bỏ qua và tiếp tục với ký tự sau.
2. Xét từ cuối chuỗi về phía trước, bỏ qua liên tiếp các ký tự có giá trị `<= U+0020`.
3. Giữ lại **đoạn liên tục nằm giữa hai ranh giới còn lại** và trả về dưới dạng `String`.

Đây là **mô hình diễn giải hành vi**, không phải yêu cầu rằng mọi bản JDK phải cài đặt thuật toán theo đúng số bước hoặc luôn sao chép dữ liệu.

```text
Giá trị đầu vào:

[TAB] [SPACE] [SPACE] J a v a [SPACE] C o r e [LF] [SPACE]
 \__________________/ |________________| \__________/
     trim ở đầu          Giữ nguyên       trim ở cuối

Giá trị trả về:

J a v a [SPACE] C o r e
```

Vì chỉ cắt **đầu và cuối**, một chuỗi có nhiều khoảng trắng giữa hai từ vẫn giữ nguyên phần ở giữa:

```java
String s = " \tA \t B\n";
String result = s.trim();

// result chứa: A, dấu cách, tab, dấu cách, B
```

`trim()` **không** chuẩn hóa nhiều dấu cách giữa các từ thành một, không xóa mọi khoảng trắng trong văn bản và không thực hiện “clean” toàn bộ chuỗi.

### Ba trường hợp ranh giới

```java
"Java".trim()     // "Java": không có ký tự đầu/cuối cần cắt
" \t ".trim()     // "": chỉ chứa các ký tự thuộc tập cần cắt
"".trim()         // "": chuỗi đầu vào vốn rỗng
```

Nếu toàn bộ chuỗi chỉ có các `char` không vượt `U+0020`, kết quả là chuỗi rỗng `""`. Đây là một chuỗi hợp lệ có `length() == 0`, **khác `null`**.

## 4. Ví dụ Java 17+ chạy được và nhìn thấy ký tự vô hình

Các dấu cách, tab, NUL và EM SPACE rất khó phân biệt trong stdout. Vì vậy ví dụ sau định nghĩa `visible(...)` để đổi những ký tự đang quan sát thành nhãn dễ đọc; việc đổi nhãn này **chỉ phục vụ in kết quả**.

Lưu thành **`TrimU0020Demo.java`**:

```java
public class TrimU0020Demo {

    static String visible(String text) {
        return text
                .replace(String.valueOf((char) 0x0000), "[NUL]")
                .replace("\t", "[TAB]")
                .replace("\n", "[LF]")
                .replace(" ", "[SPACE]")
                .replace(String.valueOf((char) 0x00A0), "[NBSP]")
                .replace(String.valueOf((char) 0x2003), "[EM_SPACE]");
    }

    static void show(String label, String input) {
        System.out.println(label + " original=" + visible(input));
        System.out.println(label + " trim=" + visible(input.trim()));
        System.out.println(label + " strip=" + visible(input.strip()));
    }

    public static void main(String[] args) {
        show("ASCII", "\t  Java  \n");

        String nul = String.valueOf((char) 0x0000);
        show("NUL", nul + "Java" + nul);

        String nbsp = String.valueOf((char) 0x00A0);
        show("NBSP", nbsp + "Java" + nbsp);

        String emSpace = String.valueOf((char) 0x2003);
        show("EM", emSpace + "Java" + emSpace);

        String middle = "A \t B";
        System.out.println("middle=" + visible(middle.trim()));

        String source = "  Java  ";
        source.trim(); // Bỏ qua giá trị trả về
        System.out.println("discard=" + visible(source));
        source = source.trim();
        System.out.println("saved=" + visible(source));
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 TrimU0020Demo.java
java TrimU0020Demo
```

**Stdout (nhãn trong ngoặc vuông là cách minh họa ký tự vô hình):**

```text
ASCII original=[TAB][SPACE][SPACE]Java[SPACE][SPACE][LF]
ASCII trim=Java
ASCII strip=Java
NUL original=[NUL]Java[NUL]
NUL trim=Java
NUL strip=[NUL]Java[NUL]
NBSP original=[NBSP]Java[NBSP]
NBSP trim=[NBSP]Java[NBSP]
NBSP strip=[NBSP]Java[NBSP]
EM original=[EM_SPACE]Java[EM_SPACE]
EM trim=[EM_SPACE]Java[EM_SPACE]
EM strip=Java
middle=A[SPACE][TAB][SPACE]B
discard=[SPACE][SPACE]Java[SPACE][SPACE]
saved=Java
```

**Đọc kết quả:**

- **ASCII:** tab, dấu cách và line feed ở rìa đều có mã `<= U+0020`, nên `trim()` và `strip()` cùng cho `"Java"`.
- **NUL:** `trim()` xóa ký tự `U+0000` ở hai đầu. `strip()` giữ lại vì NUL không thỏa `Character.isWhitespace(...)`.
- **NBSP:** cả hai phương thức trong ví dụ đều giữ NBSP (`U+00A0`), mặc dù trông giống khoảng trắng. Đây là giới hạn dễ bị bỏ sót khi xử lý văn bản sao chép từ trang web.
- **EM SPACE:** `trim()` giữ `U+2003` vì lớn hơn ngưỡng; `strip()` loại bỏ vì `Character.isWhitespace` nhận diện ký tự này là whitespace.
- **middle:** `trim()` không động đến khoảng trắng và tab ở giữa hai ký tự `A` và `B`.
- **discard / saved:** `trim()` trả về chuỗi kết quả; nếu không sử dụng giá trị trả về, biến `source` không đổi.

## 5. Phân biệt `trim()` với `strip()` trong Java 11+

Đây là hai phương thức khác nhau về **tiêu chí phân loại ký tự**:

| Phương thức | Tiêu chí xóa ở hai đầu | Hệ quả đáng nhớ |
|---|---|---|
| `trim()` | `char` có giá trị `<= U+0020` | Xóa dấu cách ASCII, một số control char kể cả NUL |
| `strip()` | Unicode code point thỏa `Character.isWhitespace(...)` | Xóa nhiều whitespace Unicode như EM SPACE |
| `stripLeading()` | Tiêu chí như `strip()`, chỉ xét **đầu** | Giữ nguyên phần cuối |
| `stripTrailing()` | Tiêu chí như `strip()`, chỉ xét **cuối** | Giữ nguyên phần đầu |

`strip()`, `stripLeading()` và `stripTrailing()` có từ Java 11. Cả ba cũng trả về giá trị `String`; chúng **không thay đổi** đối tượng ban đầu.

```java
String s = "  Java  ";

System.out.println("[" + s.stripLeading() + "]");  // [Java  ]
System.out.println("[" + s.stripTrailing() + "]"); // [  Java]
System.out.println("[" + s.strip() + "]");         // [Java]
```

### `strip()` không xóa mọi thứ nhìn giống khoảng trắng

Tên “Unicode-aware” có thể dẫn đến suy luận quá mức. `strip()` dựa vào **`Character.isWhitespace`**, và Java không coi mọi ký tự phân cách hoặc dấu cách không ngắt dòng là `isWhitespace == true`.

Ví dụ: `U+00A0` (NBSP), `U+2007` (FIGURE SPACE) và `U+202F` (NARROW NO-BREAK SPACE) không thỏa quy tắc `Character.isWhitespace` của Java. Bởi vậy **đổi `trim()` thành `strip()` không có nghĩa đã xử lý hết các loại khoảng trắng trong dữ liệu nhập**.

Phân biệt thêm `Character.isSpaceChar(...)`: nó có phạm vi nhận diện khác `Character.isWhitespace(...)`, bao gồm một số ký tự space separator mà `isWhitespace` loại trừ. Tuy nhiên, `String.strip()` **không dùng** `Character.isSpaceChar` làm điều kiện của nó.

### `isBlank()` cũng không tương đương `trim().isEmpty()`

Từ Java 11, `String.isBlank()` trả `true` khi chuỗi rỗng hoặc mọi code point thuộc tập `Character.isWhitespace(...)`. Điều này khác với việc kiểm tra xem có còn ký tự sau `trim()` hay không.

Ví dụ, các biểu thức dưới đây có kết quả khác nhau:

```java
String nul = String.valueOf((char) 0x0000);
String em = String.valueOf((char) 0x2003);

System.out.println(nul.trim().isEmpty()); // true
System.out.println(nul.isBlank());        // false

System.out.println(em.trim().isEmpty());  // false
System.out.println(em.isBlank());         // true
```

**Chọn API dựa trên định nghĩa “trắng” của nghiệp vụ**, thay vì nghĩ tất cả các phương thức này có cùng quy tắc.

## 6. Tính bất biến: `trim()` không cập nhật biến tự động

`String` là immutable. Phương thức `trim()` trả về giá trị cần được **sử dụng**, ví dụ bằng phép gán lại, tạo biến mới, `return` hoặc truyền trực tiếp cho một phương thức khác.

**Sai ý định nếu muốn cập nhật biến:**

```java
String username = "  Alice  ";
username.trim();
System.out.println("[" + username + "]"); // [  Alice  ]
```

Lời gọi thứ hai tính kết quả nhưng **bỏ qua** nó. Cách đúng:

```java
username = username.trim();
System.out.println("[" + username + "]"); // [Alice]
```

Hoặc giữ nguyên chuỗi gốc:

```java
String rawUsername = "  Alice  ";
String normalizedUsername = rawUsername.trim();
```

Khi muốn dùng trực tiếp:

```java
System.out.println("[" + rawUsername.trim() + "]");
```

Đây cũng là cách dùng hợp lệ: giá trị trả về được chuyển vào `println`, nên không bị bỏ phí.

Không nên suy đoán danh tính đối tượng chỉ từ lời gọi `trim()`. JDK có thể trả lại chính tham chiếu cũ nếu không có nội dung cần cắt; ở trường hợp khác có thể trả đối tượng `String` mới. **Điều cần dựa vào là nội dung kết quả, không phải `==`**.

## 7. Những tình huống áp dụng và giới hạn

### Tình huống 1: dữ liệu từ biểu mẫu có dấu cách ASCII thừa

```java
String entered = "   learner@example.com   ";
String email = entered.trim();

System.out.println(email); // learner@example.com
```

Phù hợp khi chỉ muốn bỏ dấu cách ASCII ở rìa. Tuy nhiên, xử lý input thật có thể cần xác thực cú pháp, giới hạn chiều dài, chuẩn hóa Unicode theo chính sách và kiểm soát các ký tự không mong muốn. `trim()` **không phải một bước kiểm tra tính hợp lệ tổng quát**.

### Tình huống 2: đọc dòng văn bản có ký tự xuống dòng

```java
String rawLine = "\tstatus=OK\r\n";
String status = rawLine.trim();

System.out.println(status); // status=OK
```

`trim()` có thể loại CR/LF và tab ở hai đầu. Nhưng nếu chương trình cần bảo toàn chính xác định dạng file hoặc khoảng trắng có ý nghĩa, việc tự ý `trim()` có thể làm **mất dữ liệu**.

Ví dụ, trong một giá trị bí mật, chuỗi đã được ký số, dữ liệu fixed-width hoặc văn bản cần giữ nguyên whitespace, không nên loại bỏ ký tự đầu/cuối nếu đặc tả dữ liệu không cho phép.

### Tình huống 3: văn bản sao chép từ trang web có NBSP

```java
String nbsp = String.valueOf((char) 0x00A0);
String copied = nbsp + "Java" + nbsp;

System.out.println(copied.trim().length()); // 6
```

NBSP ở hai đầu **không bị `trim()` loại**, vì vậy chuỗi kết quả vẫn dài `6` UTF-16 code unit: `NBSP` + `Java` (4) + `NBSP`.

Ngay cả `strip()` cũng không xóa NBSP theo `Character.isWhitespace`. Nếu yêu cầu là “loại thêm NBSP ở hai đầu”, cần xác định và triển khai một chính sách chuẩn hóa riêng, có kiểm thử; tránh âm thầm coi mọi ký tự Unicode là dấu cách thông thường.

### Tình huống 4: chuẩn hóa trong phương thức xử lý

```java
static String normalizeLabel(String label) {
    if (label == null) {
        return "";
    }
    return label.trim();
}
```

Trong ví dụ này, `null` được chuyển thành chuỗi rỗng theo **quyết định thiết kế của phương thức**, không phải hành vi có sẵn của `trim()`. Nếu `label` là `null`, gọi trực tiếp `label.trim()` sẽ ném `NullPointerException`.

## 8. Lỗi thường gặp

| Lỗi | Vì sao là lỗi | Cách xử lý |
|---|---|---|
| Nghĩ `trim()` chỉ xóa `' '` | Nó còn xóa những `char` có giá trị nhỏ hơn `U+0020` | Hiểu chính xác ngưỡng `U+0020` |
| Nghĩ `trim()` xóa mọi Unicode space | NBSP, EM SPACE, IDEOGRAPHIC SPACE có giá trị lớn hơn ngưỡng | Chọn `strip()` hoặc chính sách riêng tùy dữ liệu |
| Nghĩ `strip()` xóa mọi dấu cách đặc biệt | `Character.isWhitespace` vẫn không gồm một số non-breaking space | Kiểm tra đúng tập ký tự cần xử lý |
| Gọi `s.trim()` rồi vẫn in `s` | `String` bất biến; kết quả trả về không tự gán | Dùng `s = s.trim()` hoặc lưu biến mới |
| Tưởng `trim()` xóa khoảng trắng ở giữa | Nó chỉ xét hai rìa | Xử lý nội dung giữa theo yêu cầu riêng |
| Gọi `trim()` trên `null` | `null` không có phương thức | Kiểm tra `null` khi cần |
| Dùng `trim()` cho dữ liệu cần giữ nguyên byte/ký tự | Có thể xóa ký tự đầu/cuối mang ý nghĩa | Làm theo hợp đồng định dạng dữ liệu |
| Dùng `==` để so kết quả | So sánh danh tính đối tượng `String` | Dùng `.equals(...)` để so nội dung |

### Phân biệt khoảng trắng có ý nghĩa và ký tự thừa

Các trường hợp sau khác nhau về yêu cầu:

- Tên người dùng được cho phép có dấu cách ở đầu hoặc cuối hay không?
- Trong một biểu mẫu, hai ký tự `U+0020` ở đầu thường là dữ liệu thừa; trong một văn bản định dạng, chúng có thể là dấu thụt dòng.
- Dữ liệu đọc từ hệ thống ngoài có thể chứa NBSP hoặc whitespace Unicode; không nên giả định `trim()` sẽ làm nó giống với văn bản gõ bằng bàn phím.
- Một hệ thống đôi khi cần chỉ báo lỗi cho đầu vào có ký tự điều khiển thay vì đơn giản xóa đi. `trim()` loại cả một số control char, nên có thể che giấu đầu vào không hợp lệ nếu dùng tùy tiện.

Vì vậy cần biết rõ **định nghĩa khoảng trắng hợp lệ** trong nghiệp vụ trước khi chọn `trim`, `strip` hay cách xử lý riêng.

## 9. Kiểm tra chương trình bằng những ca biên

Để bảo đảm không nhầm tiêu chí của `trim()`, có thể viết các khẳng định đơn giản trong phương thức `main`:

```java
String nul = String.valueOf((char) 0x0000);
String nbsp = String.valueOf((char) 0x00A0);
String emSpace = String.valueOf((char) 0x2003);

if (!"Java".equals(("\t Java \n").trim())) {
    throw new AssertionError("Không trim đúng ASCII whitespace");
}

if (!"Java".equals((nul + "Java" + nul).trim())) {
    throw new AssertionError("Không trim đúng NUL");
}

if (!(nbsp + "Java" + nbsp).equals(
        (nbsp + "Java" + nbsp).trim())) {
    throw new AssertionError("NBSP không nên bị trim");
}

if (!(emSpace + "Java" + emSpace).equals(
        (emSpace + "Java" + emSpace).trim())) {
    throw new AssertionError("EM SPACE không nên bị trim");
}

if (!"Java".equals((emSpace + "Java" + emSpace).strip())) {
    throw new AssertionError("strip phải loại EM SPACE");
}
```

Các đoạn ở phần này là mã **nằm trong một phương thức** và có thể chèn vào `main` của lớp Java ở phần 4; riêng lẻ chúng không phải tệp Java hoàn chỉnh. Nếu mọi điều kiện đều đúng, chương trình đi qua khối kiểm tra mà không ném `AssertionError`. Khẳng định thủ công bằng `throw` ở ví dụ này không phụ thuộc tùy chọn JVM `-ea`.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** `"\t Java \n".trim()` trả về gì?

**Đáp án:** `"Java"`. Tab, dấu cách và newline đều thuộc khoảng `<= U+0020` ở hai đầu.

**Câu 2.** `("A " + " B").trim()` có tự xóa hai dấu cách ở giữa không?

**Đáp án:** Không. Kết quả vẫn là `"A  B"`, vì các dấu cách đó **không nằm ở rìa**.

**Câu 3.** Chuỗi chỉ chứa các ký tự `U+0000`, `U+0009` và `U+0020` có kết quả `trim()` như thế nào?

**Đáp án:** Chuỗi rỗng `""`, vì tất cả ký tự đều thuộc tập có thể cắt bỏ.

**Câu 4.** Vì sao `"\u00A0Java\u00A0".trim()` không trả `"Java"`?

**Đáp án:** `U+00A0` là NBSP có giá trị lớn hơn `U+0020`. `trim()` không loại bỏ nó. (Trong Java, Unicode escape `\u00A0` được chuyển sớm trong quá trình xử lý mã nguồn; ở ví dụ này nó đại diện cho NBSP hợp lệ trong literal chuỗi.)

**Câu 5.** Khi hai đầu chứa EM SPACE (`U+2003`), nên dùng `trim()` hay `strip()` để bỏ ký tự ấy?

**Đáp án:** Với ngữ nghĩa mặc định của Java, dùng `strip()` vì `Character.isWhitespace(U+2003)` là `true`; `trim()` giữ nguyên EM SPACE.

**Câu 6.** Vì sao `s.trim();` có thể chạy bình thường nhưng không làm biến `s` thay đổi?

**Đáp án:** `String` bất biến, `trim()` trả giá trị mới hoặc giá trị hiện tại phù hợp quy tắc; nếu kết quả bị bỏ qua, biến `s` vẫn tham chiếu đến chuỗi trước lời gọi.

**Câu 7.** `trim()` và `isBlank()` có nhận diện ký tự NUL (`U+0000`) giống nhau không?

**Đáp án:** Không. `trim()` xóa NUL ở rìa do mã `0 <= U+0020`, trong khi `isBlank()` dùng `Character.isWhitespace` và không xem NUL là whitespace.

## 11. Ghi nhớ

`String.trim()` loại bỏ từ **hai đầu chuỗi** những đơn vị UTF-16 `char` có giá trị **không vượt `U+0020`**; nó không sửa nội dung ở giữa và không thay đổi đối tượng `String` ban đầu. Ngưỡng này bao gồm cả ký tự điều khiển như NUL và bỏ qua nhiều khoảng trắng Unicode có mã lớn hơn `U+0020`.

`String.strip()` (Java 11+) dùng `Character.isWhitespace`, xử lý được nhiều Unicode whitespace hơn nhưng vẫn không bao gồm mọi dấu cách không ngắt dòng. Khi làm việc với dữ liệu đầu vào, hãy xác định tập ký tự cần loại bỏ, giữ kết quả trả về của phương thức và kiểm thử những ca biên như NUL, NBSP và EM SPACE.
