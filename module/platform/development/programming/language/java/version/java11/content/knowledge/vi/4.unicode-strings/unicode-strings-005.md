# String.lines() và phân tích dòng theo cơ chế lười trong Java 11

## 1. Khi nào dùng String.lines()?

Từ **Java 11**, `java.lang.String` cung cấp phương thức:

```java
public Stream<String> lines()
```

Phương thức này trả về một `Stream<String>` chứa các dòng văn bản theo đúng thứ tự xuất hiện trong chuỗi. Mỗi phần tử là **nội dung của một dòng, không bao gồm ký tự kết thúc dòng**. Dữ liệu nguồn là một đối tượng `String` đã tồn tại trong bộ nhớ.

Ví dụ:

```java
import java.util.stream.Stream;

String text = "Java 11\nString.lines()\nStream API";
Stream<String> lines = text.lines();
lines.forEach(System.out::println);
```

Kết quả:

```text
Java 11
String.lines()
Stream API
```

Lợi ích chính là khả năng kết hợp với Stream API để **duyệt, lọc, biến đổi và phân tích từng dòng khi cần**. Đối với thao tác chỉ cần vài dòng đầu hoặc tìm một dòng thỏa điều kiện, pipeline tuần tự thường có thể dừng sớm mà không phải tạo trước một mảng chứa tất cả các dòng.

Điểm cần phân biệt ngay từ đầu:

- **Lười khi tách và cung cấp phần tử dòng**: `lines()` không cần tạo toàn bộ danh sách dòng trước khi pipeline tiêu thụ.
- **Không lười khi tải chuỗi gốc**: đối tượng `String` đã nằm trong bộ nhớ trước khi gọi `lines()`. Nếu vừa gọi `Files.readString(...)` để đọc toàn bộ tệp, `String.lines()` không làm thao tác đọc tệp đó trở thành streaming.
- `lines()` không xóa khoảng trắng đầu/cuối dòng, không bỏ dòng trống và không tự chuyển nội dung thành số hoặc đối tượng. Đó là công việc của các bước `map`, `filter` hoặc parser riêng.

## 2. Quy tắc nhận diện một dòng

Theo hợp đồng của `String.lines()`, có đúng ba dạng **ký tự kết thúc dòng** được nhận diện:

| Ký hiệu Java | Ký tự Unicode | Ý nghĩa |
| --- | --- | --- |
| `\n` | U+000A | LF (line feed) |
| `\r` | U+000D | CR (carriage return) |
| `\r\n` | U+000D rồi U+000A | CRLF, được coi là **một** dấu kết thúc dòng |

Định nghĩa dòng là: (1) không hoặc nhiều ký tự đứng trước một dấu kết thúc dòng; hoặc (2) một hoặc nhiều ký tự kết thúc ở cuối chuỗi mà không cần dấu kết thúc dòng. Các dấu kết thúc dòng **không thuộc về giá trị `String` của dòng**.

### Các trường hợp biên cần nhớ

Bảng sau thể hiện **chuỗi đầu vào dưới dạng Java string literal** và dãy dòng thu được (dấu ngoặc kép trong bảng chỉ để nhìn rõ dòng rỗng, không thuộc dữ liệu):

| Đầu vào | Các dòng trả về | Số dòng |
| --- | --- | ---: |
| `""` | không có phần tử | 0 |
| `"abc"` | `["abc"]` | 1 |
| `"abc\n"` | `["abc"]` | 1 |
| `"\n"` | `[""]` | 1 |
| `"abc\n\n"` | `["abc", ""]` | 2 |
| `"a\n\nb"` | `["a", "", "b"]` | 3 |
| `"a\r\nb\rc\nd"` | `["a", "b", "c", "d"]` | 4 |
| `"   "` | `["   "]` | 1 |

Có hai quy tắc dễ nhầm:

1. **Chuỗi rỗng có 0 dòng**. Nhưng một dấu `\n` đứng riêng tạo ra **1 dòng rỗng** vì nó kết thúc một dòng có 0 ký tự.
2. **Không tạo thêm dòng rỗng ngay sau dấu kết thúc dòng ở cuối chuỗi**. Vì vậy `"abc\n"` có 1 dòng và `"abc\n\n"` có 2 dòng; dòng rỗng ở ví dụ thứ hai là dòng đứng *giữa hai dấu kết thúc*.

Một chuỗi có nhiều ký tự xuống dòng liên tiếp có thể chứa nhiều dòng rỗng có ý nghĩa. Nếu cần phân biệt chính xác danh sách rỗng với danh sách chứa phần tử `""`, kiểm tra cả `count()` hoặc bao mỗi dòng bằng dấu phân cách khi hiển thị; `List.toString()` của danh sách chứa chuỗi rỗng dễ gây nhầm.

### Không đồng nghĩa với mọi dấu phân cách dòng của Unicode

`String.lines()` chỉ coi **LF, CR và CRLF** là line terminator. Các ký tự khác đôi khi có chức năng ngắt dòng khi hiển thị, chẳng hạn **U+0085 (NEL), U+2028 (LINE SEPARATOR), U+2029 (PARAGRAPH SEPARATOR)**, không làm `lines()` tách dòng.

```java
String text = "A\u2028B";
System.out.println(text.lines().count()); // 1
```

Dù chuỗi chứa ký tự phân cách dòng Unicode U+2028, `lines()` vẫn coi toàn bộ là một dòng. Điều này **không có nghĩa `String` mất hỗ trợ Unicode**: ký tự Unicode trong nội dung được giữ lại; chỉ có quy tắc xác định ranh giới dòng là giới hạn như trên.

Nếu định dạng dữ liệu thực sự sử dụng nhiều kiểu ngắt dòng Unicode, cần chọn bộ phân tách thích hợp (ví dụ regex `\R` của `java.util.regex.Pattern`) và kiểm thử riêng quy tắc dòng rỗng ở cuối. `String.lines()` và `split("\\R")` **không hoàn toàn tương đương** về ranh giới nhận diện hoặc cách biểu diễn dòng rỗng.

## 3. “Lười” hoạt động như thế nào?

Stream API phân biệt **intermediate operations** (thao tác trung gian) và **terminal operations** (thao tác kết thúc).

- `map`, `filter`, `skip`, `limit` tạo pipeline, thường chưa tiêu thụ các dòng ngay.
- `findFirst`, `anyMatch`, `count`, `collect`, `forEach` kích hoạt việc tiêu thụ khi cần tạo kết quả.
- Với một pipeline **tuần tự**, các thao tác kết thúc ngắn mạch như `findFirst`, `anyMatch` và `limit(n)` kết hợp với terminal operation có thể ngừng duyệt sau khi đủ thông tin. Một `filter` có thể phải duyệt nhiều hơn `n` dòng đầu vào mới tìm được `n` dòng thỏa điều kiện.

Ví dụ quan sát thứ tự thực hiện:

```java
import java.util.stream.Stream;

Stream<String> pipeline = "one\ntwo\nthree"
        .lines()
        .map(line -> {
            System.out.println("processing=" + line);
            return line.toUpperCase();
        });

System.out.println("pipelineReady");
System.out.println("result=" + pipeline.findFirst().orElse("none"));
```

Kết quả khi chạy tuần tự:

```text
pipelineReady
processing=one
result=ONE
```

Không có dòng `processing=...` lúc xây dựng pipeline. `findFirst()` cần phần tử đầu tiên nên trong ví dụ này chỉ chuyển đổi `"one"`; phần `"two"` và `"three"` không cần được chuyển đổi. Đây là **cách quan sát hiện tượng**, không phải khuyến nghị đặt side effect trong `map` của code sản xuất. Trong code thực tế, nên giữ lambda thuần túy, không phụ thuộc vào việc mọi callback được chạy.

### Không nhầm giữa lười và luôn thực hiện mọi bước

Một số terminal operation có thể dùng thông tin kích thước nguồn và bỏ qua thao tác trung gian khi luật Stream API cho phép mà vẫn giữ nguyên kết quả cuối. Không nên dựa vào `peek` hoặc side effect trong `map` để đếm chính xác số lần pipeline xử lý khi đổi sang `count()`; nếu muốn kiểm soát side effect theo thứ tự, dùng `forEachOrdered` hoặc vòng lặp thông thường.

Cũng không nên mặc định song song hóa với `parallel()`: đầu vào String thường không cần parallel processing; thêm song song làm phức tạp chi phí và thứ tự side effect. Với bài toán phân tích dòng có tính tuần tự, dùng pipeline tuần tự giúp ý nghĩa của `findFirst`, `limit` và thứ tự dòng rõ ràng.

## 4. Pipeline xử lý dòng trong thực tế

Giả sử có cấu hình hoặc nội dung nhập theo dòng:

```text
# options
  host = localhost

port = 8080
timeout = 30
```

Để bỏ dòng trống, bỏ comment, cắt khoảng trắng, rồi chỉ lấy hai cấu hình đầu tiên:

```java
import java.util.List;
import java.util.stream.Collectors;

String config = "# options\r\n  host = localhost\n\nport = 8080\rtimeout = 30";

List<String> firstTwoSettings = config.lines()
        .map(String::strip)
        .filter(line -> !line.isBlank())
        .filter(line -> !line.startsWith("#"))
        .limit(2)
        .collect(Collectors.toList());

System.out.println(firstTwoSettings);
// [host = localhost, port = 8080]
```

Ý nghĩa từng bước:

1. `lines()` lần lượt cung cấp nội dung từng dòng theo quy tắc CR/LF/CRLF.
2. `map(String::strip)` bỏ khoảng trắng Unicode được Java xem là whitespace ở **đầu/cuối mỗi dòng**. `lines()` tự nó không làm bước này.
3. `filter(line -> !line.isBlank())` loại dòng rỗng hoặc chỉ gồm whitespace.
4. `filter(line -> !line.startsWith("#"))` bỏ comment sau khi đã `strip()`, do đó xử lý được comment có dấu cách đầu dòng.
5. `limit(2)` chỉ nhận tối đa hai dòng **sau khi lọc**. Với terminal `collect` của pipeline tuần tự này, việc duyệt có thể dừng ngay khi lấy đủ hai dòng hợp lệ.
6. `collect(Collectors.toList())` mới materialize danh sách kết quả. Java 11 có `Collectors.toList()`; cách viết `stream.toList()` chỉ có từ Java 16, vì vậy không dùng khi yêu cầu biên dịch với `--release 11`.

Nếu chỉ cần kiểm tra có dòng nào trùng điều kiện, thường không cần tạo danh sách:

```java
boolean hasPort = config.lines()
        .map(String::strip)
        .anyMatch(line -> line.startsWith("port ="));
```

Khi tìm thấy điều kiện, `anyMatch` có thể dừng sớm. Còn nếu cần dòng hợp lệ đầu tiên:

```java
String firstSetting = config.lines()
        .map(String::strip)
        .filter(line -> !line.isBlank() && !line.startsWith("#"))
        .findFirst()
        .orElse("not found");
```

`findFirst()` trả về `Optional<String>`; `orElse` là cách chỉ định giá trị mặc định khi không tìm được phần tử. Với pipeline giữ thứ tự, phần tử tìm được là phần tử đầu tiên theo thứ tự dòng trong chuỗi.

### Chuyển đổi mỗi dòng thành dữ liệu có cấu trúc

`lines()` chỉ xác định ranh giới; việc phân tích trường là trách nhiệm của ứng dụng. Ví dụ nhập **đơn giản** theo dạng `key=value` (không hỗ trợ escape, dấu bằng nằm trong khóa, comment đa dòng hoặc cú pháp cấu hình phức tạp):

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, String> properties = config.lines()
        .map(String::strip)
        .filter(line -> !line.isBlank() && !line.startsWith("#"))
        .map(line -> {
            int separator = line.indexOf('=');
            if (separator <= 0) {
                throw new IllegalArgumentException("Invalid line: " + line);
            }
            return Map.entry(
                    line.substring(0, separator).strip(),
                    line.substring(separator + 1).strip());
        })
        .collect(Collectors.toMap(Map.Entry::getKey, Map.Entry::getValue));
```

Ví dụ này hợp lệ trên Java 11; `Map.entry` có từ Java 9. `Collectors.toMap` **ném exception nếu có khóa trùng** mà không cung cấp merge function; với dữ liệu có thể trùng khóa, cần định nghĩa quy tắc xử lý rõ ràng. Không nên dùng parser ngắn trên cho CSV chuẩn, YAML hoặc định dạng có quoting/escaping phức tạp.

## 5. Chương trình hoàn chỉnh: kiểm chứng ranh giới và cơ chế lười

Lưu đoạn sau vào tệp **`StringLinesDemo.java`**:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class StringLinesDemo {
    public static void main(String[] args) {
        String input =
                "  # ghi chu\r\n  Alice,10\rBob,20\n  \nCarol,30\r\n";

        System.out.println("total=" + input.lines().count());

        List<String> firstTwo = input.lines()
                .map(String::strip)
                .filter(line ->
                        !line.isBlank() && !line.startsWith("#"))
                .limit(2)
                .collect(Collectors.toList());

        System.out.println("firstTwo=" + firstTwo);

        System.out.println("first=" + input.lines()
                .map(String::strip)
                .filter(line ->
                        !line.isBlank() && !line.startsWith("#"))
                .findFirst()
                .orElse("none"));

        System.out.println("empty=" + "".lines().count());
        System.out.println("terminal=" + "x\n".lines().count());
        System.out.println("blankBetween=" + "x\n\ny"
                .lines().collect(Collectors.toList()));
        System.out.println("onlyTerminator=" + "\n".lines().count());
        System.out.println("mixed=" + "a\r\nb\rc\nd"
                .lines().collect(Collectors.toList()));
        System.out.println("unicodeSeparator=" + "a\u2028b"
                .lines().count());

        Stream<String> deferred = "one\ntwo\nthree"
                .lines()
                .map(line -> {
                    System.out.println("processing=" + line);
                    return line.toUpperCase();
                });

        System.out.println("pipelineReady");
        System.out.println("result=" +
                deferred.findFirst().orElse("none"));
    }
}
```

Biên dịch và chạy với JDK 11 trở lên:

```bash
javac --release 11 StringLinesDemo.java
java StringLinesDemo
```

Kết quả:

```text
total=5
firstTwo=[Alice,10, Bob,20]
first=Alice,10
empty=0
terminal=1
blankBetween=[x, , y]
onlyTerminator=1
mixed=[a, b, c, d]
unicodeSeparator=1
pipelineReady
processing=one
result=ONE
```

Giải thích những dòng dễ nhầm:

- `total=5`: chuỗi đầu vào có dòng comment, hai dòng dữ liệu `Alice`/`Bob`, một dòng chỉ chứa hai khoảng trắng và dòng `Carol`. Dấu CRLF cuối không tạo thêm dòng thứ sáu.
- `firstTwo=[Alice,10, Bob,20]`: bỏ comment và dòng trống rồi lấy hai dòng dữ liệu đầu tiên; dòng `Carol` không xuất hiện trong danh sách do `limit(2)`.
- `blankBetween=[x, , y]`: dòng rỗng nằm giữa `x` và `y` được giữ nguyên; đây là ba phần tử.
- `onlyTerminator=1` nhưng `empty=0`: một dấu xuống dòng đơn lẻ đại diện cho một dòng rỗng; chuỗi rỗng không có dòng.
- `unicodeSeparator=1`: U+2028 không thuộc ba loại ký tự phân cách của `String.lines()`.
- `pipelineReady` in trước `processing=one`: `map` chưa chạy khi khai báo pipeline. Lời gọi `findFirst()` kích hoạt xử lý phần tử đầu tiên.

## 6. So sánh với các cách tách dòng khác

| Cách tiếp cận | Đầu vào | Cơ chế chính | Điểm cần chú ý |
| --- | --- | --- | --- |
| `text.lines()` | `String` đã ở bộ nhớ | Stream cung cấp dòng lười, nhận diện CR/LF/CRLF | Không giữ ký tự kết thúc dòng; không tự hỗ trợ mọi separator Unicode |
| `text.split("\\R")` | `String` đã ở bộ nhớ | Regex tách rồi tạo mảng `String[]` | `\R` nhận diện nhiều kiểu linebreak Unicode hơn; quy tắc dòng rỗng ở cuối của `split` có thể khác |
| `Pattern.compile("\\R").splitAsStream(text)` | `String` đã ở bộ nhớ | Stream tách bằng regex | Hỗ trợ regex nhưng không mặc nhiên có cùng quy tắc dòng trống như `String.lines()` |
| `Files.readString(path, UTF_8).lines()` | Tệp | Đọc **toàn bộ tệp** vào `String` rồi tách dòng lười | Không phù hợp nếu tệp quá lớn để giữ toàn bộ trong bộ nhớ |
| `Files.lines(path, UTF_8)` | Tệp | Đọc tệp dần thành `Stream<String>` | Cần đóng stream/tài nguyên; lỗi I/O có thể xuất hiện khi tiêu thụ |

Tài liệu API của JDK nêu rằng `String.lines()` có ưu điểm triển khai so với `split("\\R")` nhờ cung cấp phần tử lười và tìm nhanh dấu kết thúc dòng. Tuy nhiên, **hai API không tương đương ngữ nghĩa** nên cần chọn theo định dạng đầu vào; lợi ích hiệu năng thực tế phụ thuộc kích thước chuỗi và pipeline.

Nếu cần đọc một tệp lớn mà không nạp tất cả nội dung thành một `String`:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

// Trong một phương thức có khai báo throws IOException:
Path path = Path.of("data.txt");
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    long nonBlankCount = lines.filter(line -> !line.isBlank()).count();
    System.out.println(nonBlankCount);
}
```

`try-with-resources` là cần thiết vì stream từ `Files.lines` gắn với tài nguyên tệp. Trong khi đó, stream từ `String.lines()` chỉ duyệt chuỗi trong bộ nhớ, không sở hữu file handle. Dù `Files.lines` có tính lười, mỗi dòng rất dài vẫn cần đủ bộ nhớ cho riêng dòng đó. Khi đọc tệp, một số lỗi có thể phát sinh ở bước tiêu thụ stream dưới dạng `UncheckedIOException`; cần xử lý theo yêu cầu hệ thống.

## 7. Giới hạn và lựa chọn thiết kế quan trọng

### Không bảo toàn nguyên dạng ký tự xuống dòng

`lines()` bỏ CR/LF/CRLF khỏi các phần tử. Vì vậy, sau khi ghép kết quả bằng `Collectors.joining("\n")`, ta có thể **thay đổi CRLF thành LF** và **mất dấu xuống dòng cuối**:

```java
import java.util.stream.Collectors;

String original = "A\r\nB\n";
String rebuilt = original.lines()
        .collect(Collectors.joining("\n"));

System.out.println(original.equals(rebuilt)); // false
```

Nếu cần giữ nguyên byte, dấu CRLF, dòng trống ở cuối hoặc mã hóa của tài liệu, `lines()` không phải bộ tách có thể khôi phục chính xác đầu vào. Cần parser giữ lại delimiters hoặc làm việc trên cấu trúc nguồn phù hợp.

### Mỗi Stream chỉ tiêu thụ một lần

```java
import java.util.stream.Stream;

Stream<String> stream = "A\nB".lines();
long count = stream.count();  // 2
// stream.findFirst();        // Không hợp lệ: stream đã tiêu thụ
```

Nếu cần thực hiện nhiều phép duyệt độc lập, gọi `text.lines()` mỗi lần để tạo stream mới, hoặc materialize vào `List` khi đầu vào đủ nhỏ và cần truy cập lặp lại. Một đối tượng `Stream` không được tái sử dụng sau terminal operation.

### Phân tích cú pháp nhiều dòng không tự động được xử lý

Một dòng logic có thể kéo dài qua nhiều dòng vật lý: CSV có dấu xuống dòng bên trong trường được quote, JSON nhiều dòng, log stack trace, hoặc đoạn văn có quy tắc gộp khối. `String.lines()` chỉ cung cấp các **dòng vật lý** theo CR/LF/CRLF. Những tình huống này cần parser hiểu ngữ pháp định dạng; không thể chỉ `filter`/`map` độc lập từng dòng rồi giả định đã xử lý chính xác tài liệu.

### Dữ liệu nhập bất thường và lỗi phân tích

`lines()` không xác thực định dạng. Với các dòng dữ liệu số, `Integer.parseInt(...)` vẫn có thể ném `NumberFormatException`. Nên xác định rõ có bỏ qua dòng không hợp lệ, báo lỗi kèm số dòng, hay dừng toàn bộ quá trình. Nếu cần số dòng, có thể dùng vòng lặp/iterator có bộ đếm cục bộ hoặc thiết kế stage đánh số rõ ràng thay vì nhét trạng thái thay đổi vào `map` chạy song song.

### Kích thước dữ liệu và hành vi terminal operation

- `limit`/`findFirst`/`anyMatch` có thể giúp tránh xử lý phần đuôi chuỗi ở pipeline tuần tự.
- `collect(Collectors.toList())`, `toArray()` và các phép tổng hợp cần duyệt hết sẽ phải xử lý mọi dòng thích hợp; `collect` còn giữ kết quả trong bộ nhớ.
- `String.lines()` không giúp giảm bộ nhớ đã dùng để lưu `String` ban đầu. Nếu nguồn chưa ở bộ nhớ, hãy cân nhắc `Files.lines`/`BufferedReader` thay vì đọc toàn bộ tệp trước.
- Không lạm dụng side effect trong `peek`/`map` để ghi trạng thái nghiệp vụ; việc tối ưu pipeline hoặc thực thi song song có thể thay đổi số lần/thứ tự gọi callback.

## 8. Lỗi phổ biến và cách sửa

| Hiện tượng | Nguyên nhân thực tế | Cách xử lý |
| --- | --- | --- |
| Tưởng `"abc\n"` có hai dòng | Không có dòng rỗng mới sau dấu kết thúc ở cuối | Đối chiếu định nghĩa `lines()`; dùng định dạng giữ dấu kết thúc nếu cần |
| Không tách tại U+2028 hoặc U+0085 | `lines()` chỉ tách CR/LF/CRLF | Dùng cách phân tách Unicode phù hợp và kiểm tra quy tắc dòng trống |
| Dòng chỉ gồm dấu cách vẫn tồn tại | `lines()` không `trim`/`strip` hoặc bỏ dòng trắng | Thêm `map(String::strip)` và `filter(s -> !s.isBlank())` khi nghiệp vụ yêu cầu |
| Thấy pipeline `map` chưa in gì | Stream là lazy; chưa gọi terminal operation | Gọi `collect`, `forEach`, `findFirst`... và tránh dựa vào side effect |
| Gặp `IllegalStateException` khi sử dụng lại stream | Đã chạy terminal operation trên cùng stream | Tạo stream mới bằng `text.lines()` |
| Ứng dụng vẫn dùng nhiều bộ nhớ dù dùng `lines()` | `String` gốc đã chứa toàn bộ nội dung; hoặc `collect` chứa toàn bộ kết quả | Đọc tệp bằng `Files.lines`, xử lý ngay khi có thể và giữ ít kết quả |
| Gộp lại chuỗi nhưng mất CRLF/dấu newline cuối | Delimiters không được đưa vào phần tử | Giữ riêng delimiter nếu yêu cầu tái tạo chính xác |
| Parse dữ liệu nhiều dòng sai | Dòng vật lý không bằng bản ghi logic | Sử dụng parser theo định dạng thay vì xử lý từng dòng độc lập |

## 9. Kiểm tra nhanh

1. `"a\r\nb".lines().count()` bằng bao nhiêu? **2**, vì CRLF là một dấu kết thúc dòng.
2. `"\n\n".lines().count()` bằng bao nhiêu? **2**, mỗi `\n` kết thúc một dòng rỗng; không có dòng thứ ba sau dấu cuối.
3. Vì sao `String text = Files.readString(path); text.lines().limit(1)` không được gọi là đọc tệp lười? Vì **`Files.readString` đã đọc toàn bộ tệp** trước khi stream được tạo; chỉ việc tạo ra các phần tử dòng là lazy.
4. `text.lines().map(String::strip).filter(String::isBlank).count()` đếm gì? Đếm số dòng trở thành trống/whitespace sau `strip()`, kể cả dòng rỗng nằm giữa hai dấu kết thúc; không đếm “dòng trống tưởng tượng” ngay sau dấu kết thúc cuối.
5. Nếu cần giữ nguyên mọi ký tự xuống dòng để ký số hay so sánh nguyên bản, có nên chuyển thành `List<String>` bằng `lines()` rồi ghép lại? **Không**, vì `lines()` loại bỏ delimiters.
6. Muốn lấy dòng hợp lệ đầu tiên mà không duyệt toàn bộ pipeline, chọn operation nào? Dùng `filter(...).findFirst()` trên pipeline tuần tự; chỉ cần xử lý đủ phần đầu để tìm kết quả.

## Tài liệu chuẩn hiện hành

- [Oracle JDK 26: String.lines()](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html#lines()) — hợp đồng của `lines()`, định nghĩa CR/LF/CRLF, các trường hợp rỗng và ghi chú về tính lười.
- [Oracle JDK 11: String.lines()](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html#lines()) — xác nhận API đã có từ Java 11 và giữ cùng ngữ nghĩa cốt lõi.
- [Oracle JDK 26: Stream API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html) — intermediate/terminal operations, short-circuiting và các ràng buộc của Stream.
- [Oracle JDK 26: Files.lines()](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path,java.nio.charset.Charset)) — khi nguồn là tệp cần đọc theo dòng với quản lý tài nguyên.

**Ghi nhớ:** `String.lines()` là công cụ xử lý **dòng văn bản trong một chuỗi có sẵn**, với các phần tử được cung cấp lười theo CR/LF/CRLF. Kết hợp với Stream API để lọc và phân tích có kiểm soát; chọn bộ đọc tệp streaming hoặc parser định dạng chuyên dụng khi bài toán đòi hỏi tính chất khác.