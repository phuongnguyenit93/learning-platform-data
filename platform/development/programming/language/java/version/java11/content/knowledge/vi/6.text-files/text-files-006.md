# Giới hạn bộ nhớ khi đọc toàn bộ tệp văn bản trong Java 11

## 1. Vì sao phải quan tâm đến bộ nhớ?

Trong Java 11, `Files.readString(path)` giúp đọc một tệp văn bản thành một `String` chỉ bằng một lời gọi. Cách này rất thuận tiện cho tệp cấu hình hoặc nội dung nhỏ, nhưng toàn bộ dữ liệu phải được giữ trong bộ nhớ của tiến trình. Khi tệp lớn, số lượng tệp lớn hoặc nhiều yêu cầu đọc đồng thời, ứng dụng có thể tăng mức sử dụng heap, chịu áp lực garbage collector (GC), giảm tốc độ hoặc gặp `OutOfMemoryError`.

**Mục tiêu bài học:** biết khi nào đọc toàn bộ tệp là hợp lý, hiểu các khoản chi phí bộ nhớ có thể phát sinh, dùng các API Java 11 để xử lý theo luồng và thiết kế giới hạn kích thước đầu vào có kiểm chứng. Các nguyên tắc này vẫn áp dụng trên các bản JDK hiện đại.

Sau bài này, bạn có thể:

- Phân biệt kích thước tệp tính theo **byte**, độ dài `String` và bộ nhớ heap thực tế.
- Lựa chọn đúng giữa `Files.readString`, `Files.readAllBytes`, `Files.readAllLines`, `Files.lines` và `Files.newBufferedReader`.
- Xử lý tệp lớn bằng bộ đệm có kích thước cố định, tránh giữ toàn bộ nội dung.
- Phát hiện giới hạn của việc kiểm tra `Files.size` trước khi đọc và bổ sung bộ đếm byte **ngay trong vòng đọc** khi cần chặn đầu vào lớn.
- Đo đạc và kiểm thử bộ nhớ mà không giả định có một ngưỡng “an toàn” chung cho mọi ứng dụng.

## 2. Đọc toàn bộ tệp nghĩa là gì?

Ba API sau đều đưa **toàn bộ nội dung** vào cấu trúc dữ liệu ở bộ nhớ:

| API | Giá trị trả về | Đặc điểm | Khi nên dùng |
| --- | --- | --- | --- |
| `Files.readString(path, UTF_8)` | `String` | Đọc và giải mã toàn bộ tệp văn bản; giữ nguyên ký tự xuống dòng | Tệp văn bản nhỏ, đã biết kích thước và encoding |
| `Files.readAllBytes(path)` | `byte[]` | Đọc tất cả byte, chưa giải mã ký tự | Tệp nhị phân hoặc lúc thực sự cần toàn bộ byte của tệp nhỏ |
| `Files.readAllLines(path, UTF_8)` | `List<String>` | Đọc tất cả dòng và giữ lại dưới dạng danh sách; ký tự kết thúc dòng không nằm trong nội dung các phần tử | Tệp nhỏ cần thao tác trên danh sách dòng |

**Không nhầm:** `readString` là API được thêm trong Java 11, còn `readAllBytes` và `readAllLines` đã tồn tại từ trước nhưng vẫn được hỗ trợ. Chúng không bị “lỗi thời”; vấn đề là **phạm vi sử dụng**. Tài liệu JDK 11 nói rõ những API đọc tất cả nội dung không dành cho tệp rất lớn.

Ví dụ đọc toàn bộ một tệp nhỏ:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("config.txt");
String content = Files.readString(file, StandardCharsets.UTF_8);
System.out.println(content.length());
```

Đây là **trích đoạn trong một phương thức có khai báo `throws IOException` hoặc xử lý ngoại lệ**, không phải chương trình đầy đủ. `Path.of(...)` có từ Java 11. `Files.readString(path)` mặc định giải mã theo UTF-8; phiên bản có tham số `Charset` giúp thể hiện rõ hợp đồng encoding.

Nếu `config.txt` có dung lượng không giới hạn do người dùng tải lên, việc gọi `readString` mà không có giới hạn là một quyết định có rủi ro. Ngược lại, một tệp cấu hình vài kilobyte, được quản lý và được kiểm tra, thường không cần một hệ thống đọc theo luồng phức tạp.

## 3. Vì sao 100 MB trên ổ đĩa không đồng nghĩa chỉ cần 100 MB RAM?

### 3.1. Kích thước byte và ký tự là hai phép đo khác nhau

- `Files.size(path)` trả về kích thước tệp theo **byte** tại thời điểm đo.
- `String.length()` trả về số **đơn vị mã UTF-16** trong chuỗi; không phải số byte trên ổ đĩa và cũng không nhất thiết bằng số Unicode code point.
- Dữ liệu UTF-8 có thể cần từ một đến nhiều byte cho mỗi code point Unicode. Khi giải mã thành chuỗi, cách JVM lưu trữ và các bộ đệm tạm ảnh hưởng đến lượng heap tiêu thụ.
- Java 11 có cơ chế lưu `String` gọn hơn cho một số nội dung, nhưng **không được giả định** một `String` luôn dùng đúng một hoặc hai byte cho mỗi ký tự, cũng không được bỏ qua overhead đối tượng.

Ví dụ, tệp UTF-8 chứa nhiều ký tự tiếng Việt có số byte khác `String.length()`. Với ký tự nằm ngoài Basic Multilingual Plane, một code point thường chiếm hai đơn vị mã UTF-16.

### 3.2. Đỉnh bộ nhớ có thể cao hơn kích thước tệp

Để đọc toàn bộ một tệp, hệ thống có thể cần đồng thời một hoặc nhiều bộ phận sau:

1. Bộ đệm byte để lấy dữ liệu từ tệp.
2. Dữ liệu đã giải mã thành `String` hoặc các đối tượng `String` của từng dòng.
3. Mảng hoặc danh sách chứa tham chiếu tới các đối tượng.
4. Bộ đệm tạm, đối tượng đang chờ GC và dữ liệu phát sinh từ các bước parse, split, map.
5. Heap đang sử dụng bởi những công việc khác, đặc biệt khi nhiều request cùng đọc tệp.

Vì vậy, **không có công thức chính xác phổ quát kiểu “file 50 MB chắc chắn chiếm 50 MB heap”**. Một file 50 MB cũng không mặc nhiên an toàn khi `-Xmx` lớn hơn 50 MB. Ngoài heap, tiến trình JVM còn sử dụng bộ nhớ native, thread stacks, metaspace và bộ nhớ trực tiếp (nếu có); giới hạn RAM container không bằng `-Xmx`.

Ví dụ mang tính định hướng: nếu một worker giữ 60 MB dữ liệu đọc toàn bộ, 10 worker đồng thời có thể làm tăng nhu cầu lưu giữ dữ liệu lên hàng trăm MB **trước cả khi tính** overhead và việc parse. Không lấy các con số minh họa này làm phép đo chính xác cho một runtime cụ thể.

### 3.3. Giới hạn đối tượng và `OutOfMemoryError`

Một `byte[]` hoặc `String` đơn lẻ chịu những giới hạn biểu diễn và cấp phát của Java/JVM; không thể dùng một mảng để lưu số lượng phần tử tùy ý. Tài liệu `Files.readAllBytes` và `Files.readString` nêu `OutOfMemoryError` có thể xảy ra với file cực lớn (chẳng hạn cỡ vượt 2 GB), **nhưng OOME có thể xảy ra với file nhỏ hơn rất nhiều** khi bộ nhớ còn lại không đủ.

Đừng lấy “2 GB” làm ngưỡng an toàn. Giới hạn thực tế còn phụ thuộc JVM, heap, những đối tượng đang sống, số lần đọc song song, encoding và nền tảng chạy.

`OutOfMemoryError` thường là dấu hiệu tài nguyên nghiêm trọng; không thiết kế luồng bình thường theo kiểu “cứ đọc hết rồi bắt `OutOfMemoryError` để xử lý tệp lớn”. Chặn dữ liệu quá kích thước **trước và trong khi đọc** hoặc xử lý streaming để tránh phải giữ toàn bộ dữ liệu.

## 4. Chọn API theo kích thước và mục tiêu

| Tình huống | Giải pháp Java 11 | Chi phí bộ nhớ cần chú ý |
| --- | --- | --- |
| Tệp cấu hình nhỏ, có giới hạn rõ | `Files.readString` với `Charset` xác định | Giữ toàn bộ chuỗi; nên đặt ngưỡng đầu vào |
| Cần byte gốc của tệp nhỏ | `Files.readAllBytes` | Giữ toàn bộ `byte[]` |
| Cần danh sách dòng nhỏ | `Files.readAllLines` | Danh sách và toàn bộ đối tượng dòng cùng tồn tại |
| Đếm/kiểm tra/biến đổi từng dòng, không giữ kết quả | `Files.lines` với `try-with-resources` hoặc `BufferedReader.readLine` | Thông thường chỉ giữ dòng đang xử lý; một dòng quá dài vẫn có thể lớn |
| Đọc văn bản dài mà không tin kích thước từng dòng | `Files.newBufferedReader` + `Reader.read(char[])` | Giữ bộ đệm `char[]` có kích thước cố định |
| Xử lý dữ liệu thô có trần byte nghiêm ngặt | `Files.newInputStream` + buffer `byte[]` + bộ đếm byte | Bộ đệm cố định nếu xử lý từng khối; nếu vẫn muốn chuỗi thì cần chứa toàn bộ dữ liệu **đã bị chặn kích thước** |
| Chuyển dữ liệu lớn sang nơi lưu khác | Luồng `InputStream`/`OutputStream` hoặc `Files.copy` phù hợp | Không cần tạo toàn bộ `String` hoặc `byte[]` trung gian |

**Một sai lầm rất phổ biến:** đổi `Files.readAllLines(...)` thành `Files.lines(...).collect(Collectors.toList())` rồi cho rằng đã tiết kiệm bộ nhớ. Sau `collect`, toàn bộ các dòng vẫn được giữ lại trong một `List`, nên mục tiêu tránh lưu tất cả dữ liệu không đạt.

`Files.lines(...)` trả `Stream<String>` đọc lười khi có terminal operation; cần đóng stream. Một phép `count()` có thể không giữ mọi dòng, nhưng nếu dùng `sorted()`, `distinct()` hoặc gom dữ liệu vào collection, có thể tạo trạng thái trung gian lớn. Hãy nhìn vào **toàn bộ pipeline**, không chỉ API đầu tiên.

## 5. Đọc theo từng dòng bằng `BufferedReader`

Khi dữ liệu có dòng ngắn và mỗi dòng được xử lý độc lập, `Files.newBufferedReader` là lựa chọn dễ đọc:

```java
static long countNonEmptyLines(Path path) throws IOException {
    long count = 0;
    try (BufferedReader reader =
            Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        String line;
        while ((line = reader.readLine()) != null) {
            if (!line.isEmpty()) {
                count++;
            }
        }
    }
    return count;
}
```

Đây là **phương thức minh họa đặt trong một lớp**, cần import `java.io.BufferedReader`, `java.io.IOException`, `java.nio.file.Files`, `java.nio.file.Path` và `java.nio.charset.StandardCharsets`.

`try-with-resources` đóng reader ngay cả khi phát sinh lỗi; `readLine()` trả `null` khi hết dữ liệu (khác với một dòng rỗng `""`). Mẫu này chỉ giữ lại dòng hiện tại thay vì toàn bộ danh sách.

**Giới hạn quan trọng:** `readLine()` vẫn tạo `String` cho *một dòng*. Nếu đầu vào có một dòng dài hàng trăm MB không có newline, dòng đó có thể tiêu thụ lượng bộ nhớ rất lớn. Vì thế, “đọc theo dòng” **không tự động** bảo đảm bộ nhớ cố định trong mọi trường hợp.

`readLine()` cũng bỏ dấu kết thúc dòng; không dùng nguyên mẫu này nếu phải giữ byte hoặc ký tự xuống dòng gốc. Với CSV có dấu xuống dòng bên trong trường trích dẫn, một “dòng vật lý” không nhất thiết là một bản ghi hoàn chỉnh; hãy dùng parser phù hợp với định dạng.

## 6. Đọc bằng buffer ký tự cố định để tránh dòng quá dài

Nếu cần duyệt mọi ký tự mà không lưu toàn bộ chuỗi hoặc dòng, gọi `Reader.read(char[])` với một buffer cố định.

```java
static long countUtf16Units(Path path) throws IOException {
    long count = 0;
    try (Reader reader =
            Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        char[] buffer = new char[4096];
        int n;
        while ((n = reader.read(buffer)) != -1) {
            count += n;
        }
    }
    return count;
}
```

Đây là **phương thức minh họa**, cần `import java.io.Reader;`, `import java.io.IOException;` và các import `Files`, `Path`, `StandardCharsets`. `4096` chỉ là kích thước ví dụ, có thể chọn theo yêu cầu xử lý.

- Mỗi lần đọc sử dụng lại `char[4096]`. Bộ nhớ phụ thêm cho dữ liệu đang xử lý tương ứng với kích thước buffer, **không tăng theo tổng số dòng hoặc tổng độ dài tệp**.
- `n` là số **đơn vị mã UTF-16** vừa đọc, không phải số byte gốc; nếu cần đếm code point, phải xử lý surrogate pairs qua ranh giới các buffer.
- `Files.newBufferedReader` có thể dùng bộ đệm nội bộ ngoài `char[]` mà bạn cấp; “bộ nhớ giới hạn” không có nghĩa là chỉ cấp phát đúng `4096 * 2` byte.
- Cách đọc này không gom nội dung; nếu code đẩy mọi khối vào `StringBuilder` hay `List` thì bộ nhớ lại tăng theo toàn bộ tệp.
- Với parser dạng streaming, cần giữ một phần trạng thái giữa các khối để xử lý dữ liệu cắt ngang buffer. Đừng mặc định một khối bằng một dòng, một từ hoặc một ký tự Unicode hoàn chỉnh.

Đây là mẫu hữu ích để tính checksum ở tầng byte (với `InputStream`), đếm ký tự, thống kê tần suất hoặc thực hiện biến đổi có trạng thái giới hạn.

## 7. `Files.lines`: tiện cho thống kê, nhưng phải quản lý tài nguyên

`Files.lines(path, UTF_8)` trả một `Stream<String>` cung cấp từng dòng khi thực thi pipeline. Do stream giữ tham chiếu tới tệp đang mở, bắt buộc đóng bằng `try-with-resources`:

```java
static long countNonBlankLines(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.filter(line -> !line.isBlank()).count();
    }
}
```

Đây là **phương thức minh họa**, cần import `java.util.stream.Stream` và các loại `Files`, `Path`, `StandardCharsets`, `IOException`. `String.isBlank()` có từ Java 11; quy tắc blank dựa vào `Character.isWhitespace`, khác với `String.isEmpty()`.

Cần biết:

1. `Files.lines` là streaming theo dòng, không giữ tự động toàn bộ tệp trong `List`.
2. Nếu có dòng đơn lẻ cực dài, việc tạo `String` cho dòng đó vẫn có chi phí bộ nhớ; cần buffer ký tự cố định nếu đây là rủi ro.
3. Lỗi I/O xảy ra sau khi stream đã được mở có thể được bọc trong `UncheckedIOException` khi thực hiện terminal operation; không chỉ xử lý lỗi ở lúc gọi `Files.lines`.
4. Không chỉnh sửa tệp trong khi terminal operation đang đọc; tài liệu JDK nêu kết quả không được xác định nếu tệp thay đổi trong quá trình xử lý.
5. Đừng mặc định `parallel()` làm tệp lớn chạy nhanh hơn: hiệu quả phụ thuộc charset, I/O, kích thước dòng, chi phí xử lý, thiết bị lưu trữ và tải song song. Hãy đo trước.

## 8. Đặt giới hạn kích thước khi vẫn cần đọc toàn bộ

Có trường hợp hợp lệ phải lấy cả nội dung thành một `String`: ví dụ đọc mẫu văn bản nhỏ cho một tác vụ chỉ chấp nhận chuỗi hoàn chỉnh. Khi đó **định nghĩa ngưỡng byte tối đa** dựa trên ngân sách bộ nhớ và tính chất dữ liệu.

### 8.1. Vì sao `Files.size` một mình chưa đủ?

`Files.size(path)` giúp biết kích thước tại thời điểm gọi, nên có thể loại bỏ sớm tệp vượt ngưỡng:

```java
long maxBytes = 1024L * 1024L; // Giới hạn ví dụ: 1 MiB
if (Files.size(path) > maxBytes) {
    throw new IOException("File is too large");
}
String text = Files.readString(path, StandardCharsets.UTF_8);
```

Đây là **trích đoạn** cần khai báo `path` và import phù hợp. Mẫu trên hữu ích để kiểm tra **sơ bộ**, nhưng **không phải ràng buộc kích thước cứng**: nội dung hoặc kích thước có thể thay đổi sau lần kiểm tra và trước/đang khi `readString` đọc. Một số loại nguồn tệp cũng không mang đặc điểm giống tệp thường.

Nếu đầu vào không đáng tin cậy hoặc hệ thống yêu cầu trần kích thước nghiêm ngặt, hãy đếm số byte **trong vòng đọc** và từ chối ngay khi vượt ngưỡng.

### 8.2. Thực hiện giới hạn ngay khi đọc

Chiến lược:

1. Xác định `maxBytes` là số byte tối đa mà nghiệp vụ chấp nhận, cộng thêm ngân sách cho các đối tượng tạm và các request đồng thời. Đây **không phải** số heap tối đa được tiêu thụ.
2. Có thể dùng `Files.size` để loại sớm tệp chắc chắn quá lớn.
3. Mở `InputStream` và đọc qua `byte[]` có kích thước cố định.
4. Cộng dồn byte đã đọc; **trước khi ghi khối vào bộ nhớ**, kiểm tra xem tổng có vượt `maxBytes` không.
5. Chỉ sau khi đã đọc hoàn tất **trong giới hạn** mới giải mã thành `String`.
6. Đóng tài nguyên dù thành công hay thất bại.

Dù đã đặt trần byte, nếu cuối cùng trả `String` thì bạn vẫn phải giữ nội dung đó trong bộ nhớ. Trường hợp cần xử lý tệp lớn hơn ngân sách, hãy dùng streaming và không tích lũy toàn bộ.

## 9. Chương trình Java 11 hoàn chỉnh: đọc nhỏ có giới hạn và đọc lớn theo buffer

Tạo tệp **`FileMemoryLimitDemo.java`**. Chương trình chủ động tạo một tệp thử nghiệm UTF-8 nhỏ, đọc toàn bộ để minh họa, đếm ký tự bằng buffer cố định, đếm dòng bằng `Files.lines` và thực thi phép đọc với **giới hạn byte thực tế**. Tệp tạm được xóa trong `finally`.

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.Reader;
import java.nio.ByteBuffer;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class FileMemoryLimitDemo {

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("memory-demo-", ".txt");
        try {
            Files.writeString(
                    file, "alpha\nbeta\n\n", StandardCharsets.UTF_8);

            System.out.println("File bytes: " + Files.size(file));
            System.out.println("Full String length: "
                    + Files.readString(file, StandardCharsets.UTF_8)
                           .length());
            System.out.println("Streamed char units: "
                    + countUtf16Units(file));

            try (Stream<String> lines =
                    Files.lines(file, StandardCharsets.UTF_8)) {
                System.out.println("Line count: " + lines.count());
            }

            System.out.println("Small text: "
                    + readUtf8UpTo(file, 16).replace("\n", "|"));

            try {
                readUtf8UpTo(file, 8);
            } catch (IOException ex) {
                System.out.println("Cap: " + ex.getMessage());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }

    static long countUtf16Units(Path path) throws IOException {
        long count = 0;
        try (Reader reader =
                Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            char[] buffer = new char[4096];
            int n;
            while ((n = reader.read(buffer)) != -1) {
                count += n;
            }
        }
        return count;
    }

    static String readUtf8UpTo(Path path, int maxBytes)
            throws IOException {
        if (maxBytes < 0) {
            throw new IllegalArgumentException(
                    "maxBytes must not be negative");
        }

        // Kiểm tra sớm; tệp vẫn có thể thay đổi sau bước này.
        if (Files.size(path) > maxBytes) {
            throw new IOException(
                    "file exceeds " + maxBytes + " bytes");
        }

        try (InputStream input = Files.newInputStream(path);
             ByteArrayOutputStream output =
                     new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4096];
            int total = 0;
            int n;

            while ((n = input.read(buffer)) != -1) {
                // Kiểm tra khi đọc để bắt cả trường hợp tệp tăng kích thước.
                if (n > maxBytes - total) {
                    throw new IOException(
                            "file exceeds " + maxBytes + " bytes");
                }
                output.write(buffer, 0, n);
                total += n;
            }

            CharsetDecoder decoder = StandardCharsets.UTF_8
                    .newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT);

            return decoder.decode(
                    ByteBuffer.wrap(output.toByteArray())).toString();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 11 -encoding UTF-8 FileMemoryLimitDemo.java
java FileMemoryLimitDemo
```

Kết quả chính xác:

```text
File bytes: 12
Full String length: 12
Streamed char units: 12
Line count: 3
Small text: alpha|beta||
Cap: file exceeds 8 bytes
```

**Vì sao kết quả như vậy?**

- Chuỗi `"alpha\nbeta\n\n"` có 12 ký tự ASCII, cũng là 12 byte UTF-8: `alpha` (5), xuống dòng (1), `beta` (4), hai ký tự xuống dòng cuối (2).
- Đọc vào `String` và đếm bằng buffer đều cho **12 đơn vị mã UTF-16** vì dữ liệu minh họa chỉ chứa ASCII.
- `Files.lines` trả ba dòng logic: `alpha`, `beta` và một dòng trống. Newline cuối không tự tạo thêm một dòng thứ tư.
- Với giới hạn 16 byte, nội dung 12 byte được chấp nhận; thay newline bằng `|` tạo `alpha|beta||`.
- Với giới hạn 8 byte, phép kiểm tra `Files.size` phát hiện vượt ngưỡng và tạo lỗi `IOException` có thông điệp cố định. Nếu file tăng sau bước kiểm tra, điều kiện trong vòng đọc vẫn chặn dữ liệu vượt `maxBytes`.
- `CharsetDecoder` được cấu hình `REPORT` để **báo lỗi nếu UTF-8 không hợp lệ**; khác với việc tùy tiện thay thế byte lỗi bằng ký tự thay thế rồi tiếp tục coi dữ liệu là đúng.
- Bộ nhớ thêm của `countUtf16Units` phụ thuộc các buffer có kích thước cố định, trong khi `readUtf8UpTo` cố ý tích lũy byte để có thể trả về một `String` đầy đủ. Nó chỉ thích hợp cho **giới hạn nhỏ và được kiểm soát**.

**Giới hạn của ví dụ:** `ByteArrayOutputStream` và `toByteArray()` có thể làm tồn tại các bản sao byte tạm thời; tiếp đó còn có đối tượng kết quả đã giải mã. Vì vậy, `maxBytes` là **trần byte đầu vào**, không phải trần heap chính xác. Với các file phải xử lý theo luồng, hãy chuyển kết quả của mỗi buffer đến bộ xử lý tiếp theo thay vì dùng `ByteArrayOutputStream`.

## 10. Xây dựng giới hạn thực tế trong hệ thống

### 10.1. Tính theo ngân sách bộ nhớ và đồng thời

Một quy trình quyết định có thể dùng được:

1. Xác định **heap thực có sẵn** cho thao tác sau khi trừ dữ liệu ứng dụng đang giữ và dự phòng cho GC. Xem thêm giới hạn RAM ở mức container/VM.
2. Xác định **số lần đọc đồng thời tối đa**, không chỉ kích thước tệp lớn nhất.
3. Ước lượng các cấu trúc sống cùng lúc trong quá trình đọc và parse. Nếu thao tác cần cả `byte[]`, `String` và các DTO, phải tính tất cả.
4. Chọn ngưỡng đầu vào có **biên an toàn**, kiểm thử tải đồng thời và đo thực tế.
5. Khi dữ liệu không phù hợp với ngân sách, thiết kế lại đường xử lý thành **chunked/streaming**, hoặc chuyển tác vụ sang job có kiểm soát tài nguyên.

Ví dụ: một ứng dụng nhỏ chỉ cần đọc tệp cấu hình vài KB có thể cho phép `readString`. Dịch vụ nhận file upload lớn, nhiều request song song cần áp trần byte từ tầng nhận file, giới hạn concurrency và ưu tiên xử lý streaming. Trần ở tầng HTTP/upload **bổ sung**, chứ không thay thế giới hạn trong quá trình xử lý nếu nguồn dữ liệu có thể thay đổi hoặc không đáng tin cậy.

### 10.2. Tệp tăng kích thước hoặc bị thay thế giữa hai lần đọc

Kiểm tra `Files.size` rồi đọc là một khoảng thời gian có thể xảy ra thay đổi (TOCTOU). Đối với nguồn ngoài hệ thống:

- Đừng coi `size <= maxBytes` là bằng chứng chắc chắn rằng thao tác sau đó sẽ luôn đọc ≤ `maxBytes`.
- Dùng một cơ chế kiểm tra byte khi đọc; nếu là file đang được ghi, cân nhắc quy trình **nhận hoàn chỉnh rồi xử lý snapshot bất biến**.
- Với đường dẫn do người dùng nhập, áp dụng chính sách truy cập và ngăn đọc nhầm file ngoài phạm vi được phép; đây là vấn đề an toàn đường dẫn độc lập với bộ nhớ.
- Nếu dữ liệu được giải nén, **kích thước dữ liệu sau giải nén** mới quyết định lượng dữ liệu xử lý; một tệp nén nhỏ có thể mở rộng rất lớn. Đặt giới hạn cả số byte đầu vào lẫn số byte đầu ra đã giải nén khi phù hợp.

### 10.3. Ranh giới tệp khác với ranh giới bản ghi

Với log, CSV, NDJSON hoặc văn bản có định dạng, chọn cách phân tách bản ghi chính xác:

- Log/NDJSON thường xử lý từng dòng, nhưng vẫn cần giới hạn độ dài một dòng nếu nguồn không đáng tin.
- CSV có thể chứa newline bên trong trường được trích dẫn, nên `readLine` chưa đủ để phân tích cú pháp CSV chuẩn.
- Với văn bản UTF-8, không giải mã từng mảnh byte một cách độc lập rồi nối kết quả; một ký tự có thể trải qua **nhiều buffer byte**. Sử dụng `Reader` để decoder giữ trạng thái hoặc dùng `CharsetDecoder` streaming đúng quy trình nếu cần tự xử lý byte.
- Nếu ứng dụng cần giữ nguyên định dạng xuống dòng, hãy tránh thuật toán `readLine` rồi nối lại bằng `"\n"`, vì thao tác đó có thể thay đổi `\r\n` hoặc newline cuối.

## 11. Đo hiệu năng và bộ nhớ đúng cách

Các dấu hiệu đáng quan sát: lượng heap sử dụng trước/sau và tại đỉnh, số lần/tổng thời gian GC, độ trễ xử lý, throughput, số request đọc file đồng thời, kích thước đầu vào và tỷ lệ lỗi.

Các công cụ hiện còn hữu ích trên Java 11 và JDK mới hơn:

- **Java Flight Recorder (JFR)** để phân tích cấp phát, GC và hoạt động JVM trong tình huống thực tế.
- **`jcmd`** để chẩn đoán heap, thread và điều khiển JFR khi môi trường cho phép.
- **Metrics của ứng dụng** để ghi số byte đã đọc, thời gian xử lý, tỷ lệ từ chối do vượt trần và số tác vụ đọc đồng thời.
- **Thử nghiệm tải** với tập file có kích thước khác nhau, file có một dòng cực dài, UTF-8 nhiều byte, file hỏng encoding và nhiều tác vụ song song.

Không kết luận “ổn” chỉ từ `Runtime.getRuntime().freeMemory()` tại một thời điểm. Nó phản ánh tình trạng heap ở thời điểm đo, **không** đại diện chính xác cho đỉnh cấp phát, native memory hoặc toàn bộ tiến trình. So sánh bằng nhiều lần chạy và môi trường có tài nguyên tương đương production.

Nếu định chỉnh `-Xmx` hoặc GC, cần hiểu nguyên nhân thực. Tăng heap có thể giảm lỗi tạm thời nhưng không sửa được thiết kế nạp dữ liệu không giới hạn, và còn phải tôn trọng memory limit của container.

## 12. Các sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm? | Cách xử lý |
| --- | --- | --- |
| Đọc file upload bất kỳ bằng `Files.readString` | Dữ liệu không có trần, gây áp lực heap hoặc OOME | Đặt giới hạn và ưu tiên streaming |
| `Files.readAllLines` cho file log lớn | Mọi dòng và `List` phải nằm trong heap | `Files.lines`/`BufferedReader`, xử lý từng phần |
| `Files.lines(...).collect(toList())` rồi gọi là streaming tiết kiệm RAM | Vẫn giữ toàn bộ dữ liệu khi collect | Dùng terminal operation không tích lũy nếu có thể |
| Cho rằng mỗi dòng luôn nhỏ | File có thể là một dòng khổng lồ | Giới hạn độ dài dòng hoặc dùng buffer `char[]` |
| Chỉ kiểm tra `Files.size` một lần | File có thể thay đổi sau kiểm tra | Kiểm tra byte trong vòng đọc |
| Dựa vào kích thước file để suy ra heap | Còn byte buffer, String, List, DTO, GC và concurrency | Đo đỉnh bộ nhớ thật và dành biên an toàn |
| Cho rằng file 1 GB cần 1 GB RAM | Kích thước sau giải mã và bộ nhớ tạm khác | Thiết kế theo ngân sách thực tế |
| Cứ tăng `-Xmx` khi gặp OOME | Nguyên nhân giữ toàn bộ dữ liệu vẫn tồn tại | Sửa luồng xử lý, giới hạn request/concurrency |
| Đếm byte bằng `String.length()` | `length()` đếm UTF-16 units | Đo file byte hoặc byte thực đọc |
| Tự giải mã UTF-8 trên từng mảnh byte độc lập | Có thể cắt giữa ký tự nhiều byte | Dùng `Reader`/decoder giữ trạng thái |
| Quên đóng `Files.lines` | Tài nguyên file có thể bị giữ lâu | `try-with-resources` |
| Gộp log hoặc payload thành một `StringBuilder` không giới hạn | Bộ nhớ tăng theo tổng dữ liệu | Ghi/đẩy dữ liệu theo từng khối |
| Bắt `OutOfMemoryError` như lỗi nghiệp vụ bình thường | JVM có thể thiếu tài nguyên để tiếp tục ổn định | Phòng tránh bằng giới hạn và streaming |
| Không kiểm thử nhiều request đồng thời | Bộ nhớ đỉnh tăng theo số tác vụ | Đặt giới hạn concurrency và thử tải thực |

## 13. Checklist trước khi triển khai

1. **Nguồn dữ liệu:** do hệ thống kiểm soát hay người dùng tải lên? Tệp có thể lớn, tăng kích thước hoặc chứa dữ liệu sai encoding không?
2. **Mục tiêu:** có thực sự cần toàn bộ `String`/`byte[]`/`List` trong bộ nhớ, hay có thể xử lý từng dòng/khối?
3. **Giới hạn:** đã có trần byte và cơ chế kiểm tra ngay trong vòng đọc khi cần bảo vệ đầu vào chưa?
4. **Một dòng quá dài:** giải pháp `readLine` có nguy cơ tạo `String` quá lớn không?
5. **Encoding:** đã dùng charset đúng (thường UTF-8) và định nghĩa rõ cách xử lý byte không hợp lệ chưa?
6. **Tài nguyên:** đã dùng `try-with-resources` cho `Reader`, `InputStream` và `Stream<String>` chưa?
7. **Bộ nhớ:** đã đo heap peak, GC và memory container cùng số lượng thao tác đồng thời chưa?
8. **Định dạng:** việc tách dòng/chunk có làm sai CSV, Unicode hoặc ký tự xuống dòng gốc không?
9. **Tính đúng đắn:** đã test tệp rỗng, tệp nhỏ, tệp đúng ngưỡng, vượt ngưỡng, một dòng cực dài, encoding lỗi và file thay đổi không?
10. **Vận hành:** khi file bị từ chối hoặc không đọc được, ứng dụng có thông báo lỗi phù hợp, ghi log an toàn và giải phóng tài nguyên không?

## 14. Bài luyện tập và đáp án

**Bài 1.** Một job xử lý log dung lượng nhiều GB, chỉ cần đếm các dòng chứa một từ khóa. Có cần `Files.readAllLines` không?

**Đáp án:** Không. Dùng `Files.lines` hoặc `BufferedReader`, xử lý từng dòng và không thu thập tất cả dòng vào `List`. Nếu có rủi ro một dòng rất dài, cân nhắc xử lý buffer ký tự có trạng thái hoặc đặt giới hạn dòng.

**Bài 2.** Có phải `Files.size(file) = 100_000_000` nghĩa là `Files.readString(file)` chỉ cấp phát 100_000_000 byte không?

**Đáp án:** Không. Byte gốc, chuỗi giải mã, đối tượng phụ, bộ nhớ tạm và các thao tác khác có thể cùng chiếm bộ nhớ. Số byte không xác định trực tiếp đỉnh heap.

**Bài 3.** Tại sao `Files.lines(file).collect(Collectors.toList())` vẫn có thể OOME?

**Đáp án:** Kết quả `collect` giữ lại toàn bộ các `String` dòng và cấu trúc `List`. Dữ liệu không còn được xử lý “xong rồi bỏ” nữa.

**Bài 4.** Một file 5 MiB vượt ngưỡng 1 MiB. Nếu đã kiểm tra `Files.size` trước khi đọc, có cần kiểm tra trong vòng đọc không?

**Đáp án:** Nếu yêu cầu giới hạn cứng đối với file có thể thay đổi hoặc nguồn không đáng tin, có. `Files.size` chỉ là kiểm tra tại một thời điểm; vòng đọc kiểm tra số byte thực nhận.

**Bài 5.** `BufferedReader.readLine()` có luôn dùng lượng RAM cố định dù file lớn đến đâu không?

**Đáp án:** Không. Mỗi `readLine()` tạo một chuỗi chứa toàn bộ dòng hiện tại; một dòng bất thường dài có thể rất lớn. Dùng `Reader.read(char[])` nếu phải khống chế kích thước bộ nhớ của phần đang đọc.

## 15. Ghi nhớ

- `Files.readString`, `Files.readAllBytes` và `Files.readAllLines` vẫn hữu ích cho **tệp nhỏ, có giới hạn**. Không đọc toàn bộ dữ liệu lớn hoặc không kiểm soát được một cách vô điều kiện.
- **Kích thước file tính bằng byte ≠ độ dài `String` ≠ lượng heap tiêu thụ**.
- `Files.lines` và `BufferedReader` giúp xử lý tăng dần, nhưng **không** tự bảo đảm bộ nhớ cố định nếu một dòng cực dài hoặc pipeline tích lũy kết quả.
- `Reader.read(char[])` với buffer cố định giúp xử lý văn bản theo khối và tránh tạo `String` cho cả file hay cả dòng.
- `Files.size` là kiểm tra sơ bộ; muốn bảo đảm trần byte, phải **kiểm tra byte thực đọc** trong vòng lặp.
- Giới hạn kích thước đầu vào, số tác vụ đồng thời, định dạng dữ liệu và quan sát bộ nhớ là những phần của cùng một thiết kế an toàn.

### Tài liệu API chính thức vẫn áp dụng

- [`Files` trong Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html) — `readString`, `readAllBytes`, `readAllLines`, `newBufferedReader`, `lines`, `newInputStream`, `size`.
- [`BufferedReader` trong Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/BufferedReader.html) — cách đọc văn bản bằng buffer, `readLine` và quản lý tài nguyên.
- [`InputStream` trong Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/InputStream.html) — đọc byte theo khối.
- [`CharsetDecoder` trong Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/charset/CharsetDecoder.html) — giải mã và xử lý byte lỗi.
- [`Files` trong Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html) — tham chiếu khả năng tiếp tục hỗ trợ các API trên JDK hiện đại.
