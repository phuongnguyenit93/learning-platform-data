# String.lines() và các kiểu kết thúc dòng CR, LF, CRLF



## 1. Mục tiêu bài học

Một chuỗi Java có thể chứa nhiều dòng văn bản: nội dung tệp cấu hình, thông điệp HTTP đã tải về, kết quả lệnh hoặc dữ liệu sao chép từ hệ điều hành khác. “Xuống dòng” trong dữ liệu này không nhất thiết là một ký tự duy nhất. Ba dạng thường gặp là **LF**, **CR** và **CRLF**. Khi xử lý nhiều dòng, ta cần biết chuỗi chứa ký tự gì, phương thức nào xem chúng là ranh giới dòng và liệu dòng trống có bị giữ lại không.

Từ **Java 11**, `String.lines()` cho phép duyệt các dòng trong một `String` thông qua `Stream<String>`. Bài này tập trung vào:
- Hiểu chính xác `\n` (LF), `\r` (CR), `\r\n` (CRLF).
- Biết `String.lines()` trả về những chuỗi nào và loại bỏ ký tự kết thúc dòng ra sao.
- Dự đoán các trường hợp **dòng trống giữa văn bản**, **chuỗi rỗng** và **ký tự kết thúc dòng ở cuối**.
- Xử lý dòng bằng Stream, so sánh với `split("\\R")`, và chọn cách xử lý phù hợp cho dữ liệu đa nền tảng.

## 2. CR, LF và CRLF là gì?

| Tên | Tên đầy đủ | Escape trong chuỗi Java | Mã Unicode | Ký tự |
| --- | --- | --- | --- | --- |
| LF | Line Feed | `\n` | `U+000A` | Một ký tự điều khiển xuống dòng |
| CR | Carriage Return | `\r` | `U+000D` | Một ký tự điều khiển đưa đầu in về đầu dòng theo lịch sử |
| CRLF | Carriage Return + Line Feed | `\r\n` | `U+000D U+000A` | **Hai ký tự liên tiếp**, thường được xem như **một lần** kết thúc dòng |

Trong thực tế, văn bản kiểu Unix/Linux thường sử dụng LF, văn bản Windows thường sử dụng CRLF, còn CR đơn từng được dùng phổ biến trên hệ Macintosh cũ. Đây là quy ước hay gặp, không phải quy tắc bất biến: tệp có thể được tạo, đồng bộ hoặc truyền qua hệ thống khác và chứa bất kỳ dạng nào.

Chú ý `"\r\n"` có độ dài **2** trong `String` Java, nhưng nhiều API xử lý văn bản coi cặp này là **một ranh giới dòng**. Không nên hiểu CR và LF trong cặp CRLF như hai dòng độc lập.

```java
String lf = "A\nB";
String cr = "A\rB";
String crlf = "A\r\nB";

System.out.println(lf.length());   // 3
System.out.println(cr.length());   // 3
System.out.println(crlf.length()); // 4
```

Ba chuỗi đều thể hiện hai dòng theo `String.lines()`, nhưng số ký tự bên trong khác nhau. Escape `\n` và `\r` được viết trong **mã nguồn Java**; giá trị runtime chứa ký tự điều khiển thực, không chứa hai ký tự `\` và `n`/`r`.

## 3. String.lines() hoạt động như thế nào?

Chữ ký API:

```java
public Stream<String> lines()
```

Đây là **phương thức instance** của `java.lang.String`, có từ Java 11. Nó trả về một `Stream<String>` chứa các dòng của chuỗi nguồn theo đúng thứ tự xuất hiện. Mỗi phần tử là nội dung dòng, **không bao gồm ký tự kết thúc dòng**.

Trong định nghĩa của `String.lines()`, một *line terminator* là **một trong ba dạng**: LF (`\n`), CR (`\r`) hoặc CRLF (`\r\n`). Cặp CRLF được tiêu thụ cùng nhau như một dấu kết thúc dòng, dù gồm hai ký tự.

Về trực giác, một dòng là:
1. Không hoặc nhiều ký tự nằm trước một line terminator, **hoặc**
2. Không hoặc nhiều ký tự ở cuối chuỗi, sau line terminator cuối cùng nếu còn ký tự.

Tuy nhiên, **ký tự kết thúc dòng ở cuối chuỗi không tự sinh thêm một dòng trống cuối cùng**. Đây là điểm dễ nhầm khi so sánh với `String.split(..., -1)`.

```java
import java.util.List;

String text = "đầu\ncuối";
List<String> lines = text.lines().toList();

System.out.println(lines);       // [đầu, cuối]
System.out.println(lines.size()); // 2
```

`Stream.toList()` có từ Java 16, nên ví dụ này phù hợp với Java 17+. Trên Java 11, có thể thay `.toList()` bằng `.collect(Collectors.toList())`.

## 4. Ví dụ thực hành: trộn CR, LF và CRLF

Tạo tệp `LinesDemo.java` (lưu UTF-8) với mã đầy đủ sau:

```java
import java.util.List;

public class LinesDemo {
    private static void show(String label, String input) {
        List<String> lines = input.lines().toList();
        System.out.println(label + " = " + lines.size() + " dòng");

        for (int i = 0; i < lines.size(); i++) {
            System.out.println("  " + i + ": [" + lines.get(i) + "]");
        }
    }

    public static void main(String[] args) {
        show("LF", "A\nB");
        show("CR", "A\rB");
        show("CRLF", "A\r\nB");
        show("mixed", "một\nhai\r\nba\rbốn");
        show("blank middle", "A\n\nB");
        show("trailing LF", "A\n");
        show("empty", "");
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 LinesDemo.java
java LinesDemo
```

Stdout:

```text
LF = 2 dòng
  0: [A]
  1: [B]
CR = 2 dòng
  0: [A]
  1: [B]
CRLF = 2 dòng
  0: [A]
  1: [B]
mixed = 4 dòng
  0: [một]
  1: [hai]
  2: [ba]
  3: [bốn]
blank middle = 3 dòng
  0: [A]
  1: []
  2: [B]
trailing LF = 1 dòng
  0: [A]
empty = 0 dòng
```

Chương trình in `[ ]` xung quanh mỗi dòng để dễ thấy nội dung rỗng; trong kết quả, `[]` chính là một chuỗi dòng có độ dài 0. Thứ tự dòng được giữ nguyên khi đi qua Stream.

Quan sát sự khác biệt:
- `"A\nB"`, `"A\rB"` và `"A\r\nB"` đều tạo hai dòng `"A"` và `"B"`.
- `"A\n\nB"` chứa **hai dấu kết thúc dòng liên tiếp**; khoảng giữa chúng là một dòng rỗng hợp lệ.
- `"A\n"` kết thúc ngay sau một dấu LF; `lines()` chỉ trả `"A"`.
- `""` không có ký tự nào và không có dòng nào; Stream rỗng.

### Ranh giới với các bài chuyên sâu

Bảng dòng trống và ký tự xuống dòng cuối được kiểm chứng chi tiết ở bài **Chuỗi rỗng và ký tự xuống dòng ở cuối**. Nếu cần phân biệt `split(regex, 0)`, `split(regex, -1)` và `lines().limit(n)`, xem bài **Khác biệt giữa lines và split với limit**. Ở bài hiện tại, điểm trọng tâm là cách LF, CR và CRLF được nhận diện như ranh giới dòng và tác động của việc chuẩn hóa chúng.

## 5. Xử lý các dòng bằng Stream

Vì `lines()` trả `Stream<String>`, có thể kết hợp trực tiếp `map`, `filter`, `count`, `forEach`, `limit`, `collect`... để thực hiện các thao tác theo dòng.

### Đếm số dòng

```java
String text = "alpha\nbeta\r\ngamma";
long count = text.lines().count(); // 3
```

Giá trị ở đây là **số phần tử dòng** do `lines()` sinh ra, không phải số lần xuất hiện của ký tự `\n`. Trong chuỗi trên, CRLF là một lần kết thúc dòng; tổng có ba dòng.

### Lọc các dòng trống hoặc chỉ chứa khoảng trắng

```java
import java.util.List;

String text = "  Java  \n\n  \r\nStream\n";
List<String> nonBlank = text.lines()
        .map(String::strip)
        .filter(line -> !line.isEmpty())
        .toList();

System.out.println(nonBlank); // [Java, Stream]
```

Trong ví dụ này:
- `strip()` loại khoảng trắng Unicode theo quy tắc `Character.isWhitespace` ở hai đầu chuỗi (Java 11+).
- `filter(...)` bỏ những dòng trở thành rỗng sau khi strip.
- `toList()` gom kết quả thành danh sách (Java 16+).

Nếu cần **giữ lại** các dòng trống để bảo toàn bố cục gốc, đừng áp dụng `filter`. Nếu chỉ cần bỏ dòng trống theo định nghĩa `String.isBlank()` mà vẫn giữ khoảng trắng ở những dòng khác, có thể dùng `.filter(line -> !line.isBlank())`.

### Thêm số thứ tự dòng

```java
import java.util.List;
import java.util.stream.IntStream;

List<String> lines = "first\nsecond\nthird".lines().toList();
List<String> numbered = IntStream.range(0, lines.size())
        .mapToObj(i -> (i + 1) + ". " + lines.get(i))
        .toList();

System.out.println(numbered);
// [1. first, 2. second, 3. third]
```

Đây là đoạn mã minh họa đặt trong một phương thức hoặc `main`; ví dụ hoàn chỉnh chạy độc lập đã có tại mục 4.

### Nối lại các dòng

```java
import java.util.stream.Collectors;

String original = "A\r\nB\nC";
String normalized = original.lines()
        .collect(Collectors.joining("\n"));

System.out.println(normalized.equals("A\nB\nC")); // true
```

Sau khi tách, các dấu CR, LF hoặc CRLF **không còn nằm trong phần tử dòng**. Để nối lại, bạn phải chủ động chọn dấu phân cách mới. Kết quả này không giữ nguyên chính xác các dấu kết thúc dòng gốc. Nếu văn bản ban đầu kết thúc bằng newline, việc nối các dòng thường sẽ **không** tái tạo newline cuối cùng. Nếu cần bảo toàn từng byte của văn bản nguồn, đừng dùng `lines()` rồi tự join mà không ghi lại thông tin dấu kết thúc dòng.

## 6. Tránh nhầm với System.lineSeparator()

`System.lineSeparator()` trả về chuỗi kết thúc dòng **mặc định của nền tảng đang chạy**. Thường trên Windows là `"\r\n"`, còn trên Linux/macOS hiện đại là `"\n"`. Giá trị này phục vụ **việc tạo đầu ra theo nền tảng**, không quyết định loại terminator mà `String.lines()` có thể đọc.

```java
String output = String.join(
        System.lineSeparator(), "first", "second");
```

Đoạn trên tạo văn bản theo dấu xuống dòng hệ thống. Nhưng nếu một `String` đã chứa CRLF hoặc CR từ nguồn khác, `lines()` vẫn nhận diện chúng, bất kể máy đang chạy thuộc hệ điều hành nào.

Tương tự, `%n` trong `String.format(...)`/`Formatter` in ký tự xuống dòng theo nền tảng, và `println(...)` cũng phát sinh dấu xuống dòng của môi trường. Các cách **tạo xuống dòng** này khác với quy tắc **đọc/tách xuống dòng** của `String.lines()`.

## 7. Lines, stream và tài nguyên

`String.lines()` hoạt động trên một **chuỗi đã có trong bộ nhớ**. Nó không tự đọc tệp, không mở kết nối và không đóng luồng hệ điều hành. Stream trả về hỗ trợ thao tác theo chuỗi bước (pipeline), có thứ tự theo văn bản nguồn và việc tìm ranh giới dòng diễn ra khi Stream được sử dụng.

Ví dụ chỉ lấy hai dòng đầu:

```java
import java.util.List;

String text = "one\ntwo\nthree\nfour";
List<String> firstTwo = text.lines().limit(2).toList();

System.out.println(firstTwo); // [one, two]
```

Stream được sử dụng bởi một terminal operation như `toList()` hoặc `count()`; **không được tái sử dụng cùng một đối tượng Stream** sau khi terminal operation đã chạy:

```java
import java.util.stream.Stream;

String text = "A\nB";
Stream<String> stream = text.lines();

long count = stream.count(); // 2
// stream.toList(); // Sai: Stream đã được sử dụng
```

Muốn xử lý lần hai, hãy gọi `text.lines()` lần nữa. `String.lines()` tạo Stream từ một `String`; bản thân `String` là immutable nên không thay đổi vì hoạt động đọc dòng.

**Đối với tệp rất lớn:** đọc toàn bộ tệp vào một `String` có thể tốn bộ nhớ. Khi cần xử lý tăng dần, chọn `Files.lines(path, charset)` hoặc `BufferedReader.lines()` rồi quản lý vòng đời tệp/reader bằng `try-with-resources`. `Files.lines` cần đóng Stream vì nó nắm tài nguyên I/O; `String.lines` không có tài nguyên tệp cần đóng. Những API đọc dòng từ tệp và `String.lines` có cùng mục tiêu khai thác dòng văn bản, nhưng chi phí và vòng đời tài nguyên khác nhau.

## 8. Quy tắc thực hành khi chuẩn hóa xuống dòng

Khi nhận văn bản từ nhiều nguồn, hãy xác định **yêu cầu đầu ra** trước khi chuyển đổi:
1. **Chỉ cần tính toán theo dòng** (đếm, lọc, tìm kiếm): `String.lines()` thường phù hợp.
2. **Cần chuẩn hóa nội dung để hiển thị hoặc so sánh:** dùng `lines()` rồi join với `"\n"` hoặc quy tắc đầu ra đã chọn, chấp nhận việc thay đổi dấu xuống dòng gốc và khả năng mất newline cuối.
3. **Cần giữ nguyên định dạng gốc, kể cả CRLF/CR/LF hỗn hợp hoặc newline cuối:** lưu nguyên chuỗi; nếu phải phân tích, dùng thuật toán giữ kèm delimiter hoặc cơ chế đọc bảo toàn dấu kết thúc dòng.
4. **Cần xử lý nhiều loại Unicode linebreak:** cân nhắc regex `\R` và kiểm tra yêu cầu về các phần tử rỗng ở cuối.
5. **Cần phân tích theo chuẩn cụ thể** (CSV nhiều dòng trong trường có quote, HTTP headers, log có nhiều dòng): không mặc định mỗi dấu xuống dòng là ranh giới record; hãy dùng parser tuân thủ chuẩn.

Một ví dụ điển hình: nếu cần kiểm tra xem cấu hình có bao nhiêu **dòng không rỗng**, có thể viết:

```java
String config = "# sample\r\nhost=localhost\n\r\nport=8080\n";
long nonBlankLines = config.lines()
        .filter(line -> !line.isBlank())
        .count();

System.out.println(nonBlankLines); // 3
```

Đây là bài toán **đếm dòng hiển thị không rỗng**, không phải parse ngữ nghĩa của tệp cấu hình. Nếu cần đọc key/value, bình luận hay escape đúng chuẩn định dạng, phải dùng parser tương ứng.

## 9. Bài tự luyện có đáp án

**Bài 1.** Dự đoán số phần tử của ba Stream:

```java
"A\r\nB".lines().count();
"A\n\nB".lines().count();
"A\n".lines().count();
```

Đáp án lần lượt: **2**, **3**, **1**. CRLF là một dấu kết thúc dòng; hai LF liên tiếp tạo một dòng rỗng ở giữa; LF cuối không thêm dòng mới.

**Bài 2.** `"\r\n\n".lines()` có bao nhiêu dòng và nội dung của từng dòng là gì?

Đáp án: **2 dòng**, cả hai đều là `""`. CRLF tạo dòng rỗng thứ nhất; LF tiếp theo tạo dòng rỗng thứ hai.

**Bài 3.** Với `String text = "x\r\ny\n";`, hãy lấy danh sách dòng không chứa terminator.

```java
import java.util.List;

String text = "x\r\ny\n";
List<String> values = text.lines().toList();
// ["x", "y"]
```

**Bài 4.** Muốn giữ lại cả phần tử trống **sau LF cuối** để phân biệt `"A"` và `"A\n"`, nên dùng cách nào?

Một cách đơn giản khi dữ liệu phù hợp với các linebreak regex nhận diện:

```java
String[] values = "A\n".split("\\R", -1);
// ["A", ""]
```

Với yêu cầu bảo toàn chính xác CR/LF/CRLF gốc để tái xuất, `split("\\R", -1)` vẫn **không giữ loại delimiter**: phải dùng giải pháp lưu cả delimiter.

**Bài 5.** Cần xác định một chuỗi có bao nhiêu dòng không rỗng sau khi loại khoảng trắng đầu/cuối.

```java
String text = "A\n   \r\n B \n";
long count = text.lines()
        .map(String::strip)
        .filter(s -> !s.isEmpty())
        .count();
// 2
```

**Bài 6.** So sánh trên chuỗi `"A\u2028B"`: `lines()` và `split("\\R")` có cùng số phần tử không?

Đáp án: **không**. `lines()` tạo một dòng; `split("\\R")` tạo hai phần tử, vì regex `\R` nhận diện Unicode LINE SEPARATOR (`U+2028`).

## 10. Ghi nhớ

- **LF = `\n`**, **CR = `\r`**, **CRLF = `\r\n`**; CRLF gồm hai ký tự nhưng được coi là một line terminator.
- **`String.lines()` từ Java 11** tạo `Stream<String>` theo thứ tự dòng, tự bỏ LF/CR/CRLF khỏi từng phần tử.
- **Chuỗi rỗng → 0 dòng; một terminator đơn → 1 dòng rỗng; terminator ở cuối sau nội dung → không phát sinh thêm dòng cuối**.
- **Dòng trống ở đầu/giữa vẫn được giữ**, trừ khi bạn chủ động lọc bằng Stream.
- **`split("\\R")` nhận nhiều Unicode linebreak hơn; `split("\\R", -1)` giữ phần tử trống sau terminator cuối**, nhưng không bảo toàn chính loại dấu kết thúc dòng.
- **`System.lineSeparator()` là lựa chọn dấu xuống dòng khi tạo văn bản** theo nền tảng, không giới hạn những terminator mà `String.lines()` nhận diện.
- Nếu phải tái tạo văn bản **chính xác**, bao gồm newline cuối và CR/LF/CRLF hỗn hợp, hãy giữ nguyên nguồn hoặc lưu cả delimiter.

Tham khảo chính thức: [Java SE 17 — String.lines()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#lines()), [Java SE 17 — Pattern (\\R)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html), [Java SE 17 — Files.lines()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path)).
