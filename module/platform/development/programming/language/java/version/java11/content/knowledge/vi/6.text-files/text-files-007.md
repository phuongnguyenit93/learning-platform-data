# Chọn đọc toàn bộ hoặc xử lý từng phần theo kích thước dữ liệu (Java 11+)

## Mục tiêu

Khi xử lý **tệp văn bản**, chọn sai cách đọc có thể làm chương trình dùng bộ nhớ quá lớn, chậm khi gặp tệp dài hoặc không giải phóng tài nguyên đúng lúc. Java 11 đã cung cấp các API vẫn được hỗ trợ trong Java hiện đại: `Files.readString`, `Files.readAllLines`, `Files.lines`, `Files.newBufferedReader` và các phương thức `Reader.read(...)`.

Sau bài này, bạn sẽ biết **khi nào nên đọc toàn bộ**, **khi nào đọc từng dòng**, **khi nào cần đọc từng khối ký tự**; hiểu độ phức tạp bộ nhớ, ý nghĩa charset/line ending, và chạy được một chương trình minh họa cả ba chiến lược.

**Phạm vi:** tệp **văn bản** được mã hóa bằng UTF-8, đọc tuần tự bằng Java 11 trở lên. Một số API dành cho Java mới sẽ được ghi rõ phiên bản. Không sử dụng cách đọc đã lỗi thời hoặc phụ thuộc charset mặc định của máy.

## 1. Phân biệt kích thước tệp, bộ nhớ và đơn vị dữ liệu

Trước khi chọn API, cần phân biệt ba đại lượng:

- **Byte trên đĩa:** `Files.size(path)` cho kích thước tệp theo byte tại thời điểm kiểm tra.
- **Ký tự Java:** `String.length()` và `Reader.read(char[])` tính **đơn vị mã UTF-16** (`char`). Một ký tự Unicode nằm ngoài BMP có thể chiếm hai `char`.
- **Bộ nhớ trong JVM:** phụ thuộc cách lưu chuỗi, số object, collection, bộ đệm, phần mềm đang chạy và bộ nhớ heap cho phép. Không suy ra chính xác RAM chỉ từ `Files.size(path)`.

Ví dụ tệp UTF-8 chứa chữ ASCII `A`, emoji `🙂` và dấu xuống dòng LF: phần nội dung đó có **6 byte UTF-8**, nhưng khi đọc thành `String` có **4 đơn vị UTF-16** (`A` = 1, emoji = 2, LF = 1). Vì vậy không dùng `text.length()` làm “kích thước tệp theo byte”.

Việc đọc **toàn bộ tệp** thành một `String` hoặc `List<String>` giữ dữ liệu trong bộ nhớ và có thể phát sinh cấp phát tạm khi giải mã. Ngược lại, xử lý **từng dòng hoặc từng khối** cho phép chỉ giữ phần dữ liệu đang cần cùng kết quả tổng hợp, nếu thuật toán không tự tích lũy lại toàn bộ nội dung.

## 2. Bốn cách đọc phổ biến và chi phí của chúng

| API | Đầu ra | Cách xử lý | Bộ nhớ cần lưu ý | Khi dùng |
| --- | --- | --- | --- | --- |
| `Files.readString(path, UTF_8)` | Một `String` chứa toàn bộ nội dung, **giữ ký tự xuống dòng** | Đọc hết trước khi trả kết quả | Tăng theo toàn bộ kích thước văn bản | Tệp nhỏ, cần xử lý xuyên nhiều dòng hoặc giữ nguyên định dạng |
| `Files.readAllLines(path, UTF_8)` | `List<String>` chứa mọi dòng, **bỏ ký tự kết thúc dòng** | Đọc hết trước khi trả kết quả | Tăng theo nội dung và số dòng/list element | Tệp nhỏ, cần truy cập/sửa/so sánh các dòng nhiều lần |
| `Files.lines(path, UTF_8)` | `Stream<String>`, lấy dòng **theo nhu cầu** | Pipeline Stream được tiêu thụ bởi terminal operation | Có thể thấp nếu chỉ filter/map/count; tăng nếu collect/sort/group | File lớn, lọc và tổng hợp theo dòng với Stream |
| `Files.newBufferedReader(path, UTF_8)` | `BufferedReader` | Đọc lần lượt bằng `readLine()` hoặc `read(char[])` | Bộ đệm và dữ liệu đang xử lý; phụ thuộc độ dài dòng hoặc cỡ khối | File lớn, cần vòng lặp, kiểm soát lỗi/tiến độ và bộ nhớ |

Cả bốn API còn hữu ích ở Java hiện đại. Tên `readAllLines` và `readString` diễn tả **đọc toàn bộ**, còn `lines` có dạng Stream nhưng không có nghĩa mọi phép toán trên Stream đều tiết kiệm bộ nhớ.

### Quy tắc chọn nhanh

1. **Tệp chắc chắn nhỏ, cần nguyên văn kể cả xuống dòng:** chọn `Files.readString`.
2. **Tệp chắc chắn nhỏ, cần danh sách dòng để truy cập theo vị trí hoặc duyệt lại nhiều lần:** chọn `Files.readAllLines`.
3. **Tệp có thể rất lớn hoặc kích thước chưa biết, xử lý độc lập từng dòng:** chọn `Files.lines` với pipeline không tích lũy, hoặc `BufferedReader.readLine()`.
4. **Tệp có dòng cực dài, không có xuống dòng, hoặc cần xử lý theo luồng ký tự mà không tạo cả một dòng String:** đọc thành các khối bằng `Reader.read(char[])` và giữ trạng thái xử lý giữa các khối.
5. **Dữ liệu thực ra là nhị phân:** không giải mã bừa thành `String`; dùng API byte như `Files.newInputStream`/`InputStream.read(byte[])` cùng quy tắc định dạng thích hợp.

**Không có ngưỡng MB cố định áp dụng cho mọi ứng dụng.** Một tệp 20 MB có thể nhỏ với tiến trình có heap lớn nhưng quá sức với ứng dụng nhiều tác vụ đồng thời; một tệp hàng GB không nên được xử lý bằng cách giữ toàn bộ trong RAM khi chỉ cần đếm/lọc. Đánh giá kích thước tối đa thực tế, heap còn trống, số yêu cầu đồng thời, độ dài dòng và bộ nhớ cho kết quả.

## 3. Chương trình chạy được: chọn chế độ đọc theo mục đích

Chương trình sau thực hiện cùng một tệp văn bản ở ba chế độ:

- `all`: gọi `readString` và `readAllLines` để **so sánh** toàn văn với danh sách dòng; chỉ phù hợp cho **tệp nhỏ**.
- `lines`: duyệt tuần tự bằng `BufferedReader.readLine()`, đếm tổng số dòng, dòng không trắng, độ dài dòng lớn nhất mà không giữ danh sách mọi dòng.
- `chunks`: đọc từng khối `char[4096]` và đếm tổng số đơn vị UTF-16, kể cả các ký tự xuống dòng, không tạo một chuỗi lớn.

**Tệp: `TextReadDemo.java`** (Java 11+).

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class TextReadDemo {
    public static void main(String[] args) {
        if (args.length != 2 ||
                !("all".equals(args[0]) ||
                  "lines".equals(args[0]) ||
                  "chunks".equals(args[0]))) {
            System.err.println(
                    "Usage: java TextReadDemo.java <all|lines|chunks> <file>");
            System.exit(2);
            return;
        }

        Path path = Path.of(args[1]);
        try {
            switch (args[0]) {
                case "all":
                    String content =
                            Files.readString(path, StandardCharsets.UTF_8);
                    List<String> lines =
                            Files.readAllLines(path, StandardCharsets.UTF_8);
                    System.out.println("characters=" + content.length() +
                            ", lines=" + lines.size());
                    break;

                case "lines":
                    long lineCount = 0;
                    long nonblankCount = 0;
                    int maxLineChars = 0;

                    try (BufferedReader reader =
                            Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
                        String line;
                        while ((line = reader.readLine()) != null) {
                            lineCount++;
                            if (!line.isBlank()) {
                                nonblankCount++;
                            }
                            maxLineChars = Math.max(
                                    maxLineChars, line.length());
                        }
                    }

                    System.out.println("lines=" + lineCount +
                            ", nonblank=" + nonblankCount +
                            ", maxLineChars=" + maxLineChars);
                    break;

                case "chunks":
                    long characters = 0;
                    char[] block = new char[4096];

                    try (Reader reader =
                            Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
                        int count;
                        while ((count = reader.read(block)) != -1) {
                            characters += count;
                        }
                    }

                    System.out.println("characters=" + characters);
                    break;

                default:
                    throw new AssertionError("Unreachable mode");
            }
        } catch (IOException e) {
            System.err.println("Read failed: " + e.getMessage());
            System.exit(1);
        }
    }
}
```

**Chuẩn bị tệp `sample.txt` (UTF-8):** nhập ba dòng dưới đây, với dòng giữa trống, rồi lưu bằng kiểu xuống dòng **LF**, có LF sau `beta`:

```text
alpha

beta
```

Với nội dung chính xác dưới dạng ký hiệu `"alpha\n\nbeta\n"`, tệp chứa **12 byte ASCII/UTF-8**. Nếu trình soạn thảo tự chuyển sang `CRLF` (Windows), kết quả đếm *dòng* không đổi, nhưng số ký tự bao gồm xuống dòng sẽ thành **15** thay vì 12.

Chạy trực tiếp từ tệp nguồn, JDK 11+:

```bash
java TextReadDemo.java all sample.txt
java TextReadDemo.java lines sample.txt
java TextReadDemo.java chunks sample.txt
```

Hoặc biên dịch rồi chạy thông thường:

```bash
javac TextReadDemo.java
java TextReadDemo all sample.txt
java TextReadDemo lines sample.txt
java TextReadDemo chunks sample.txt
```

**Kết quả chính xác với tệp mẫu dùng LF:**

| Lệnh / chế độ | Stdout |
| --- | --- |
| `all` | `characters=12, lines=3` |
| `lines` | `lines=3, nonblank=2, maxLineChars=5` |
| `chunks` | `characters=12` |

Chương trình đã được kiểm tra bằng cách **biên dịch với `javac --release 11`** và chạy ba chế độ trên JDK hiện đại. Những giá trị ở bảng chỉ đúng với nội dung mẫu, không phải đầu ra cố định của mọi tệp.

### Giải thích kết quả và chi phí

**Chế độ `all`:**

```java
String content = Files.readString(path, StandardCharsets.UTF_8);
List<String> lines = Files.readAllLines(path, StandardCharsets.UTF_8);
```

- `content` giữ **mọi ký tự**, gồm ba LF, nên `content.length() == 12`.
- `lines` gồm `["alpha", "", "beta"]`, vì đọc theo dòng **loại bỏ dấu kết thúc dòng**; LF cuối tệp không tạo một dòng thứ tư.
- Ví dụ chủ ý gọi **cả hai API** trên cùng một tệp nhỏ để thấy khác biệt; trong chương trình thật, nếu chỉ cần một cách biểu diễn, hãy **chọn một** để tránh đọc tệp và giữ dữ liệu hai lần.
- `Files.readString` được giới thiệu từ Java 11, giữ nguyên dấu ngắt dòng, tự đóng tài nguyên đọc khi hàm hoàn thành. `readAllLines` cũng tự đóng file khi hoàn thành; cả hai có thể thất bại nếu file quá lớn hoặc nội dung giải mã không hợp lệ.

**Chế độ `lines`:**

```java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý từng dòng, không lưu toàn bộ.
    }
}
```

Đoạn rút gọn này **chỉ minh họa mô hình đọc**, không phải chương trình độc lập; chương trình hoàn chỉnh ở trên có đủ biến đếm. `readLine()` trả về nội dung của một dòng **không có CR/LF**. Với mẫu, các dòng có độ dài 5, 0, 4; dòng dài nhất là 5, có hai dòng không trắng.

`try-with-resources` đóng reader khi kết thúc hoặc gặp lỗi. Bộ đọc có bộ đệm nên giảm số thao tác I/O nhỏ lẻ, đồng thời vòng lặp chỉ giữ dòng hiện tại và vài biến thống kê.

**Chế độ `chunks`:**

```java
char[] block = new char[4096];
try (Reader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    int count;
    while ((count = reader.read(block)) != -1) {
        // Chỉ xử lý block[0] ... block[count - 1].
    }
}
```

Mẫu rút gọn cần import `Reader`, `Files`, `StandardCharsets` và một biến `path` đã khai báo. Mỗi lần `read(block)` chỉ trả về số đơn vị `char` **thực sự đọc được** (có thể ít hơn 4096), và `-1` là kết thúc luồng. Không được mặc định toàn bộ buffer luôn có dữ liệu mới.

Lợi thế: bạn không cần tạo cả một `String` dài tương đương với **dòng dài nhất**. Đổi lại, nếu muốn nhận biết các ký tự xuống dòng, dấu phân cách hoặc Unicode code point, bạn phải xử lý trường hợp chúng nằm **giữa hai khối liên tiếp**. Trong UTF-16, cặp surrogate cũng có thể nằm ở ranh giới khối; đếm `char` như ví dụ vẫn đúng, nhưng phân tích Unicode code point cần giữ trạng thái phù hợp.

## 4. Khi tệp lớn: `Files.lines` hay `BufferedReader`?

Cả hai đều được hỗ trợ và hữu ích trong Java hiện đại.

### `Files.lines` cho pipeline lọc/tổng hợp

Nếu muốn đếm các dòng có nội dung, thay vì lưu một `List`:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class CountNonblankLines {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java CountNonblankLines.java <file>");
            return;
        }

        Path path = Path.of(args[0]);
        try (Stream<String> lines =
                Files.lines(path, StandardCharsets.UTF_8)) {
            long count = lines.filter(line -> !line.isBlank()).count();
            System.out.println("nonblank=" + count);
        }
    }
}
```

Lưu thành `CountNonblankLines.java`, biên dịch và chạy:

```bash
javac CountNonblankLines.java
java CountNonblankLines sample.txt
```

Stdout với tệp mẫu có LF:

```text
nonblank=2
```

`Files.lines(path, charset)` trả về Stream đọc lười (*lazy*) khi có terminal operation, chẳng hạn `count()`. Tuy nhiên Stream này **giữ file mở**; phải sử dụng `try-with-resources`. Ngoài `IOException` lúc mở file, lỗi I/O phát sinh **trong quá trình duyệt Stream** có thể được ném dưới dạng `UncheckedIOException`. Khi viết công cụ CLI cần báo lỗi có kiểm soát, xử lý cả hai loại lỗi tại ranh giới phù hợp.

Có thể thay lambda bằng `Predicate.not(String::isBlank)` (Java 11+) khi đã import `java.util.function.Predicate`:

```java
long count = lines
        .filter(Predicate.not(String::isBlank))
        .count();
```

Đây là **đoạn thay thế** cho câu lệnh tính `count` trong `try` ở ví dụ trên; không phải khối độc lập.

Một Stream chỉ dùng được một lần. Nếu muốn vừa đếm, vừa liệt kê dòng theo điều kiện khác, hãy thiết kế một lần duyệt kết hợp hoặc **mở stream mới** nếu cần nhiều lần duyệt file.

### `BufferedReader.readLine()` cho điều khiển rõ ràng

Chọn vòng lặp khi cần:
- Đếm chính xác số dòng gốc để thông báo lỗi vị trí.
- Ghi ra kết quả ngay khi xử lý được từng dòng.
- Dừng sớm theo quy tắc ứng dụng, quản lý tiến độ hoặc tích lũy một vài bộ đếm/trạng thái.
- Xử lý ngoại lệ `IOException` trực tiếp tại thời điểm đọc.

Với tệp rất lớn, một vòng lặp qua reader thường dễ theo dõi mức sử dụng bộ nhớ: mỗi lần chỉ giữ một dòng cộng dữ liệu nhỏ đang xử lý. Tuy nhiên nếu một dòng dài hàng trăm MB, chính việc tạo `String` cho dòng đó vẫn gây áp lực bộ nhớ; đó là lý do có chiến lược đọc theo khối.

## 5. Lợi ích bộ nhớ của Stream có thể bị mất ở bước cuối

Cú pháp Stream **không tự bảo đảm** bộ nhớ thấp. So sánh:

```java
// Đếm: chỉ giữ kết quả là một số, không tích trữ mọi dòng.
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.filter(line -> !line.isBlank()).count();
}

// Tạo List: giữ tất cả dòng được chọn trong bộ nhớ.
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> result = lines
            .filter(line -> !line.isBlank())
            .collect(java.util.stream.Collectors.toList());
}
```

Các đoạn trên là **minh họa trong phương thức có xử lý `IOException`**, cần import cho `Stream`, `List`, `Files`, `Path` và `StandardCharsets`. Ví dụ thứ hai có `List` chứa các dòng được chọn, nên khi tỷ lệ lọc cao, chi phí có thể tiến gần đọc toàn bộ.

Các thao tác `sorted()`, `distinct()`, `groupingBy(...)` hoặc thu gom mọi dòng cũng có thể giữ trạng thái/bộ đệm tăng theo dữ liệu. Muốn bộ nhớ giới hạn, hãy chọn thuật toán streaming thật sự: đếm, tổng hợp một ít thống kê, lọc rồi ghi dần, hoặc tổng hợp theo cửa sổ có giới hạn.

Không mặc định `parallel()` giúp đọc file nhanh hơn: hiệu quả phụ thuộc charset, cách chia nguồn, tốc độ đĩa, thuật toán và chi phí đồng bộ. Thử đo hiệu năng với dữ liệu thực tế trước khi thay đổi.

## 6. Đọc “theo khối” đúng nghĩa và ranh giới dữ liệu

Khi một record có thể dài hơn cả bộ nhớ mong muốn hoặc tệp là một khối văn bản rất dài không có newline, `BufferedReader.readLine()` vẫn phải tạo `String` cho **trọn một dòng**. Khi đó `Reader.read(char[])` giới hạn kích thước dữ liệu đầu vào **mỗi lần đọc**.

Ví dụ thống kê đơn giản trong chương trình chính chỉ cộng số lượng `char`, vì vậy không cần ghép khối. Nhưng nếu muốn tìm chuỗi `ERROR`, cắt token hoặc parse định dạng:

1. Giữ phần ký tự cuối khối trước có thể là tiền tố token.
2. Đọc khối tiếp theo, ghép hoặc xử lý trạng thái tiếp diễn.
3. Tính đúng khi ký tự Unicode nằm ở ranh giới `char`, đặc biệt surrogate pair.
4. Không giả định một lần `read(...)` luôn trả đầy buffer.
5. Đóng reader trong `try-with-resources`.

Nếu phải xử lý byte thô hoặc giao thức nhị phân, dùng `InputStream.read(byte[])`; **đừng** chuyển từng khối byte UTF-8 độc lập thành `String` bằng cách giải mã thiếu trạng thái, vì một ký tự UTF-8 có thể bị chia giữa hai khối. Với văn bản, `InputStreamReader`/`BufferedReader` đảm nhiệm việc giải mã charset xuyên các lần đọc.

## 7. Khi nào nên quyết định bằng kích thước file?

Có thể lấy kích thước làm tín hiệu:

```java
long bytes = Files.size(path);
```

Đây là **đoạn minh họa** trong ngữ cảnh có `Path path` và xử lý `IOException`. Nhưng kích thước tệp chỉ là một dữ kiện, không phải công thức RAM chính xác; hơn nữa file có thể thay đổi giữa lần kiểm tra kích thước và lúc đọc.

Một quy trình chọn thực tế:

- **Biết chắc file nhỏ, có giới hạn kích thước rõ trong hợp đồng** và cần nguyên văn: `readString` giúp code ngắn.
- **Biết chắc file nhỏ, cần truy cập từng dòng nhiều lần:** `readAllLines`.
- **Không kiểm soát được kích thước do người dùng/tổ chức khác cung cấp** hoặc file có thể tăng liên tục: ưu tiên `lines`/`BufferedReader`, đồng thời đặt giới hạn đầu vào hợp lý nếu cần.
- **Đường truyền tệp dữ liệu rất dài, không có newline hoặc một record có thể khổng lồ:** xử lý `Reader.read(char[])` và kiểm soát thuật toán ghép dữ liệu.
- **Cần thay đổi một vài dòng trong file lớn:** đọc/ghi streaming sang **tệp đầu ra riêng** rồi thay thế có kiểm soát nếu cần; tránh đọc toàn bộ và ghi đè ngay file nguồn.

Ví dụ định hướng: file vài KB để đọc mẫu cấu hình thường phù hợp `readString`. File log nhiều GB để đếm lỗi thường phù hợp đọc tuần tự. Không suy ra kết quả chỉ từ hai ví dụ; bộ nhớ heap, số tác vụ chạy đồng thời, dòng lớn nhất và cách tính toán kết quả mới quyết định giới hạn thực.

## 8. Charset, xuống dòng, ngoại lệ và tính toàn vẹn

### Charset

Nên chỉ rõ `StandardCharsets.UTF_8` khi hợp đồng dữ liệu là UTF-8. Từ Java 11, `Files.readString(path)` mặc định dùng UTF-8, nhưng viết charset tường minh giúp người học nhận biết việc giải mã. Không chọn `Charset.defaultCharset()` một cách vô thức khi đọc file từ hệ thống khác.

Nếu file dùng charset khác, hãy dùng đúng `Charset` đã được xác định; không coi lỗi ký tự là lý do để “đoán thử” nhiều charset mà không có hợp đồng rõ ràng.

### Line ending và dòng cuối

- `readString` giữ các dấu xuống dòng của văn bản.
- `readAllLines`, `Files.lines` và `BufferedReader.readLine` trả về nội dung dòng không có dấu kết thúc `LF`, `CR` hoặc `CRLF`.
- Với `"alpha\n\nbeta\n"`, các thao tác theo dòng tạo đúng **ba** dòng: `"alpha"`, `""`, `"beta"`.
- Với `CRLF`, `readString`/đọc khối giữ cả `\r` và `\n`, còn thao tác theo dòng loại dấu kết thúc đó.

Đọc theo dòng không thích hợp nếu cần bảo toàn **nguyên xi** kiểu xuống dòng để tạo byte-for-byte copy; khi đó phải chọn chiến lược giữ nguyên nội dung/binary phù hợp.

### Ngoại lệ và đóng tài nguyên

- `Files.readString` và `readAllLines` có thể ném `IOException` hoặc `OutOfMemoryError` nếu file cực lớn; tránh dùng chúng cho dữ liệu không kiểm soát.
- `Files.lines` và `Files.newBufferedReader` cần được đóng sau khi dùng; `try-with-resources` là cơ chế hiện đại.
- Sai đường dẫn, file không tồn tại, không đủ quyền đọc, lỗi I/O hoặc UTF-8 không hợp lệ có thể làm thao tác thất bại.
- `Path.of(...)` còn có thể ném `InvalidPathException` (unchecked) với chuỗi đường dẫn không hợp lệ. Ví dụ chính tập trung vào đọc file, vì vậy công cụ sản xuất nên bổ sung xử lý đầu vào này và báo lỗi phù hợp.
- `Files.lines` có thể bọc lỗi đọc phát sinh sau khi mở file trong `UncheckedIOException`; hãy phân biệt với `IOException` xảy ra khi mở file.
- Tệp có thể bị thay đổi đồng thời trong quá trình duyệt, nên không giả định streaming là một bản snapshot nhất quán. Nếu tính nhất quán là yêu cầu nghiệp vụ, hãy có quy trình quản lý nguồn dữ liệu tương ứng.

**Lưu ý:** `OutOfMemoryError` là dấu hiệu dữ liệu/chiến lược vượt ngân sách bộ nhớ; bắt lỗi này để tiếp tục xử lý bình thường không thay thế thiết kế đọc theo luồng.

## 9. Sai lầm thường gặp

| Sai lầm | Hệ quả | Hướng khắc phục |
| --- | --- | --- |
| Dùng `readString` với file tùy ý, rất lớn | Có thể tăng heap đột biến, lỗi bộ nhớ | Ưu tiên đọc từng dòng/khối và giới hạn dữ liệu |
| Dùng `Files.lines(...).toList()` và nghĩ là streaming tiết kiệm RAM | Danh sách được thu gom trong RAM | Dùng terminal operation tổng hợp hoặc ghi dần, không giữ toàn bộ |
| Gọi `Files.lines` nhưng không đóng Stream | File descriptor/tài nguyên có thể còn mở | `try-with-resources` |
| Đọc dòng khi cần giữ đúng dấu `CRLF`/`LF` | Mất thông tin kết thúc dòng | `readString` cho file nhỏ hoặc xử lý theo khối có giữ dấu |
| Đọc file lớn có một dòng cực dài qua `readLine` | Bộ nhớ vẫn tăng theo độ dài dòng | `Reader.read(char[])` và parser có trạng thái |
| Dùng `Files.size` làm số `char`/RAM chính xác | Sai với UTF-8, Unicode và overhead | Phân biệt byte, UTF-16 và object allocation |
| Xử lý toàn bộ buffer dù `read(char[])` trả về ít ký tự | Dùng lại dữ liệu cũ trong phần buffer chưa được cập nhật | Chỉ xử lý từ chỉ số `0` đến `count - 1` |
| Giải mã riêng từng block byte của tệp UTF-8 | Có thể làm hỏng ký tự khi bị cắt giữa block | Dùng `Reader`/bộ giải mã có trạng thái |
| Dùng chung một Stream cho nhiều terminal operation | Lỗi do Stream đã được tiêu thụ | Thiết kế một lần duyệt hoặc mở Stream mới |
| Thử với file bé rồi kết luận chương trình chạy an toàn với file GB | Bỏ qua line length, overhead, concurrency, heap | Đo trên dữ liệu đại diện và theo dõi RAM/GC |

## 10. Thực hành áp dụng

**Bài 1 — Dự đoán.** File có nội dung `"A\n\nB\n"` và dùng LF. Hãy dự đoán `readString(...).length()` và số phần tử `readAllLines(...)`. Đáp án: **5** đơn vị UTF-16 và **3** dòng.

**Bài 2 — Chọn API.** Với file ghi chú 8 KB cần hiển thị nguyên văn, chọn `readString`. Với file log 5 GB chỉ cần đếm dòng có chứa `"ERROR"`, ưu tiên `Files.lines`/`BufferedReader` để không tạo danh sách toàn bộ.

**Bài 3 — Quan sát line ending.** Chạy ví dụ chính với `sample.txt` lưu LF rồi CRLF. So sánh kết quả `all`, `lines` và `chunks`. Giải thích tại sao đếm dòng vẫn là 3 trong cả hai trường hợp nhưng kết quả ký tự khác nhau.

**Bài 4 — Kiểm tra dòng dài.** Tạo một file chỉ có một dòng rất dài; giải thích vì sao `readLine()` cần bộ nhớ theo độ dài dòng, còn cách đọc `char[]` có thể xử lý mỗi khối với buffer cố định nếu thuật toán không tích lũy lại toàn bộ nội dung.

**Bài 5 — Củng cố.** Chỉnh chế độ `lines` để đếm các dòng chứa từ khóa được truyền từ command line, giữ nguyên cấu trúc `try-with-resources`. Thử tệp rỗng, dòng trắng, Unicode, đường dẫn có dấu cách và file không tồn tại.

### Câu hỏi tự kiểm tra

1. `Files.readAllLines` có phải “đọc từng phần” vì trả `List<String>` không? **Không**, nó đọc hết và lưu danh sách.
2. `Files.lines` có luôn giữ bộ nhớ cố định không? **Không**, các thao tác như thu gom/sắp xếp vẫn có thể tích lũy dữ liệu.
3. Tại sao `Reader.read(char[])` hữu ích khi một dòng cực dài? Vì không bắt buộc tạo một `String` cho cả dòng trước khi xử lý.
4. Tại sao phải đóng `Files.lines`? Vì Stream nắm tài nguyên file cho tới khi được đóng.
5. Có ngưỡng “nhỏ hơn 100 MB thì luôn dùng `readString`” không? **Không**, phải cân nhắc ngân sách heap, concurrency, dữ liệu và thuật toán thực tế.

## Tài liệu chính thức (các API vẫn hiện hành)

- [Oracle Java SE 11 — `Files`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html): `readString` (từ Java 11), `readAllLines`, `lines` và `newBufferedReader`.
- [Oracle Java SE 25 — `Files`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): tài liệu hiện đại về lựa chọn đọc toàn bộ, Stream theo dòng, charset và yêu cầu đóng tài nguyên.
- [Oracle Java SE 25 — `Reader`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Reader.html): `read(char[])`, giá trị trả về và vòng đời reader.
- [Oracle Java SE 25 — `BufferedReader`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/BufferedReader.html): `readLine()`, cách duyệt dòng và bộ đệm.
- [Oracle Java SE 25 — `StandardCharsets`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8 và các charset chuẩn.

**Nguyên tắc thực hành:** chọn dữ liệu giữ trong RAM dựa trên **bộ nhớ thực tế cần dùng**, không đơn thuần tên API. Đọc toàn bộ khi vừa nhỏ vừa cần toàn bộ; đọc từng dòng khi xử lý theo dòng; đọc từng khối khi một dòng hoặc record có thể quá lớn.