# Java 10 – Reader.transferTo: Lựa chọn truyền trực tiếp hoặc xử lý biến đổi từng phần

> **Phạm vi:** Java 10 → **Reader.transferTo** → **Lựa chọn truyền trực tiếp hoặc xử lý biến đổi từng phần**. Nội dung chỉ sử dụng các quy tắc và API vẫn còn phù hợp trên Java 17+ và các JDK hiện đại. `Reader.transferTo(Writer)` được đưa vào **Java 10**; `InputStream.transferTo(OutputStream)` xuất hiện từ Java 9. Các ví dụ chạy được với `javac --release 17`.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích chính xác hợp đồng của `Reader.transferTo(Writer)`: đọc **phần ký tự còn lại** từ `Reader`, ghi theo thứ tự vào `Writer`, trả về `long` là số ký tự đã chuyển và đưa Reader tới EOF nếu thành công.
2. Chọn **chuyển trực tiếp** khi chỉ muốn sao chép dòng ký tự, không cần hiểu hoặc đổi nội dung.
3. Chọn **xử lý từng dòng**, **từng khối `char[]`** hoặc parser có trạng thái khi cần lọc, chuẩn hóa, giới hạn, ẩn dữ liệu hoặc thay đổi biểu diễn.
4. Phân biệt `Reader`/`Writer` (dữ liệu ký tự) với `InputStream`/`OutputStream` (dữ liệu byte) để không sử dụng sai khi cần bản sao nhị phân.
5. Hiểu vì sao `transferTo` trả số **đơn vị `char` UTF-16**, không nhất thiết bằng số Unicode code point hoặc số byte trên đĩa.
6. Quản lý charset, xuống dòng, bộ nhớ, flush/close, EOF, IOException, timeout và output dở dang một cách có trách nhiệm.
7. Nhận diện lỗi biến đổi theo chunk: token nằm qua ranh giới buffer, surrogate pair, ký tự kết hợp, xử lý case-insensitive và newline.
8. Chạy chương trình Java 17+ so sánh chuyển trực tiếp, xử lý từng dòng và ROT13 ASCII theo chunk, với stdout có thể kiểm chứng.

**Nguyên tắc:** `transferTo` phù hợp khi **giữ nguyên các `char` và thứ tự đọc**. Khi kết quả cần **chính sách biến đổi**, hãy chọn đơn vị xử lý đủ ý nghĩa (dòng, bản ghi, ký tự Unicode hoặc chunk có trạng thái) và tự điều khiển vòng đọc/ghi. Có thể kết hợp `transferTo` với **Writer trang trí có logic chuyển đổi**, nhưng khi đó **transformation nằm trong Writer**, không phải trong bản thân `transferTo`.

## 2. Hợp đồng của `Reader.transferTo(Writer)` từ Java 10

Phương thức thuộc `java.io.Reader`:

~~~java
public long transferTo(Writer out) throws IOException
~~~

Những cam kết cần nhớ:

- **Đọc tất cả các ký tự còn lại** của Reader và ghi chúng vào Writer **theo thứ tự đọc**.
- Nếu kết thúc thành công, Reader ở **cuối luồng** (EOF); các lần `read()` tiếp theo thông thường trả `-1`.
- Trả về một giá trị kiểu `long` biểu thị **số ký tự đã chuyển**. Đừng giả định đó là số byte UTF-8.
- **Không tự đóng** Reader hoặc Writer. Caller vẫn phải quản lý tài nguyên.
- Writer bắt buộc khác `null`; nếu `out == null` thì ném `NullPointerException`.
- Có thể ném `IOException` khi đọc hoặc ghi.
- Quá trình có thể **chờ vô thời hạn** ở bước đọc/ghi nếu nguồn hoặc đích không sẵn sàng; đây không phải cơ chế timeout hay giao thức hủy/cắt tải.
- Nếu I/O lỗi giữa chừng, một số ký tự có thể đã được đọc hoặc ghi; không có cam kết Reader đã tới EOF hoặc output còn nhất quán. Tài liệu khuyến nghị đóng cả hai luồng sớm sau lỗi.

### 2.1. Bản chất của `transferTo`: truyền nội dung ký tự

~~~java
import java.io.StringReader;
import java.io.StringWriter;

class DirectExample {
    static void run() throws java.io.IOException {
        var source = new StringReader("Java 10\nReader.transferTo");
        var target = new StringWriter();

        long count = source.transferTo(target);

        System.out.println(count);             // 25
        System.out.println(target.toString()); // hai dòng nội dung nguyên văn
    }
}
~~~

Đây là **đoạn minh họa bên trong class**, không phải file có `main` độc lập. Trong bài hoàn chỉnh phía dưới có chương trình được biên dịch và kiểm chứng stdout đầy đủ.

`transferTo` không yêu cầu dữ liệu phải nằm sẵn trong bộ nhớ. Reader có thể đọc file, socket, bộ giải mã hoặc nguồn dữ liệu khác; Writer có thể ghi file, bộ đệm, log sink hoặc luồng ký tự khác. Tuy nhiên **đặc điểm chờ và lỗi I/O** phụ thuộc vào hai đối tượng thực tế.

### 2.2. `transferTo` không bắt đầu lại từ đầu Reader

~~~java
var reader = new java.io.StringReader("ABCDE");
reader.read();  // tiêu thụ 'A'
var writer = new java.io.StringWriter();

long transferred = reader.transferTo(writer);
System.out.println(transferred);        // 4
System.out.println(writer.toString());  // BCDE
~~~

Chỉ **phần còn lại** được chuyển. Nếu Reader đã ở EOF, `transferTo` thành công với số ký tự chuyển `0`; nếu Reader đã bị đóng, hành vi đọc sẽ theo hợp đồng của class Reader cụ thể và có thể ném `IOException`.

Không tái sử dụng Reader đã được chuyển tới cuối luồng rồi kỳ vọng có lại toàn bộ nội dung. Một số Reader hỗ trợ `mark/reset`, nhưng không phải tất cả; muốn đọc lại thường phải mở nguồn mới.

## 3. Bảng quyết định: chuyển nguyên văn hay xử lý từng phần?

| Mục tiêu | Nên dùng | Vì sao |
| --- | --- | --- |
| Copy toàn bộ **text** từ Reader sang Writer, giữ thứ tự `char` | `reader.transferTo(writer)` | Ngắn gọn, không cần vòng lặp thủ công |
| Chuyển text giữa hai file với UTF-8 cụ thể | `Files.newBufferedReader` + `Files.newBufferedWriter` + `transferTo` | Định rõ decoding/encoding và quản lý resource |
| Copy file **nhị phân hoặc byte-exact** | `Files.copy` hoặc byte streams | Reader/Writer có bước giải mã/mã hóa text |
| Xóa dòng rỗng, trim, đổi hoa/thường theo **dòng** | `BufferedReader.readLine()` + `Writer` | Cần xem và quyết định theo từng dòng |
| Mỗi N ký tự cần thay/đếm, lọc ký tự ASCII | `Reader.read(char[])` + `Writer.write(...)` | Điều khiển từng khối, tránh giữ cả file trong bộ nhớ |
| Cần dừng sau N ký tự hoặc N bản ghi | Vòng đọc có **giới hạn** | `transferTo` mặc định đọc tới EOF |
| Chỉ cần xử lý các record hợp lệ, bỏ record lỗi | Parser/reader từng record, validation riêng | Không thể làm bằng copy nguyên văn |
| Muốn chuyển và biến đổi mà vẫn gọi `transferTo` | Writer decorator/FilterWriter có transformation | Chọn Writer chịu trách nhiệm chuyển đổi |
| Chuyển mạng liên tục/nguồn chưa có EOF | Protocol có framing, cancellation/timeout | `transferTo` có thể chờ mãi |
| Biến đổi Unicode phức tạp, token qua nhiều chunk | Parser/stateful processor hoặc thư viện chuyên biệt | Transform từng `char` tách rời dễ sai |
| Cần sửa nhiều ký tự trên toàn file với dữ liệu nhỏ | `readAll`/`readString` khi thật sự phù hợp giới hạn bộ nhớ | Dễ viết, nhưng không nên áp dụng với input vô hạn/lớn |

**Không có lựa chọn “nhanh nhất trong mọi trường hợp”.** Mỗi cách tối ưu cho một **hợp đồng đầu ra** khác nhau. Luôn xác định trước: kết quả cần giống input đến cấp `char`, giống đến cấp **byte**, hay được phép thay nội dung?

## 4. Trường hợp nên dùng truyền trực tiếp

### 4.1. Chỉ chuyển các ký tự từ nguồn sang đích

~~~java
try (var reader = new java.io.StringReader("hello\nworld");
     var writer = new java.io.StringWriter()) {
    long chars = reader.transferTo(writer);
    System.out.println(chars);              // 11
    System.out.println(writer.toString());  // hello và world trên hai dòng
}
~~~

Chuyển trực tiếp là lựa chọn tốt nếu:

- Không lọc hoặc chuẩn hóa nội dung.
- Không cần kiểm tra/giới hạn số record trong lúc đọc.
- Chỉ cần một số đếm ký tự đã chuyển.
- Dữ liệu đã được xác định là **text**, không phải file nhị phân.
- Caller đã kiểm soát vòng đời Reader/Writer và cách xử lý lỗi.

### 4.2. Đọc và ghi file văn bản theo charset cụ thể

~~~java
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

class TextFileTransfer {
    static long copyText(Path source, Path target)
            throws java.io.IOException {
        try (Reader in = Files.newBufferedReader(
                     source, StandardCharsets.UTF_8);
             Writer out = Files.newBufferedWriter(
                     target, StandardCharsets.UTF_8)) {
            return in.transferTo(out);
        }
    }
}
~~~

Đây là **một phương thức mẫu**, không phải ứng dụng `main` độc lập. Nó tạo/ghi đè text file đích theo mặc định của `newBufferedWriter`, nên cần bảo đảm source/target là **hai path phù hợp**, không vô tình đọc và truncate cùng một file.

**Vì sao cần nêu charset?** Reader đọc **ký tự đã được giải mã** từ byte; Writer ghi **ký tự và mã hóa lại thành byte**. Dù `transferTo` không cố ý sửa ký tự, output **không được hứa byte-for-byte giống input** khi charset, BOM, encoding error policy hoặc loại Writer khác nhau. Với file nhị phân, dùng `Files.copy(source, target, ...)` hoặc `InputStream`/`OutputStream` thay vì Reader/Writer.

### 4.3. Truyền trực tiếp không nhất thiết load toàn bộ nội dung vào String

Dùng `Reader.transferTo` với file streams thường tránh việc tự tạo một String lớn chứa toàn file. Điều này hữu ích khi nội dung lớn. Tuy nhiên cách triển khai thực tế vẫn có **buffer**; không gọi nó là “zero-copy” hoặc hứa không có allocation. Performance tùy Reader/Writer, charset, hệ thống file và môi trường.

Nếu đích là `StringWriter` như ví dụ học tập, bản thân nó **cần giữ toàn bộ output trong bộ nhớ**. Không được suy luận rằng chỉ cần thay vòng lặp bằng `transferTo` sẽ khiến memory của `StringWriter` trở thành hằng số.

## 5. `char` được đếm như thế nào? UTF-16, code point và byte

Java `Reader` và `Writer` xử lý **đơn vị `char`**. Một `char` biểu diễn một đơn vị mã UTF-16; ký tự Unicode ngoài BMP (ví dụ emoji) thường cần **hai `char`**, gọi là surrogate pair.

~~~java
String sample = "A\uD83D\uDE00Z"; // A + emoji + Z
System.out.println(sample.length());                 // 4
System.out.println(sample.codePointCount(0, 4));     // 3
~~~

Với `StringReader(sample).transferTo(writer)`, giá trị đếm là **4 ký tự Java `char`**, không phải 3 Unicode code points. Nếu mã hóa UTF-8, số byte có thể khác nữa.

Trong ví dụ chính, input có:

~~~java
String content = "  Java 10\r\ncaf\u00E9\nA\uD83D\uDE00Z  ";
~~~

- Có `\r\n`, `\n` và một surrogate pair.
- Tổng `String.length()` là **22** đơn vị `char`.
- Tổng `String.codePointCount(...)` là **21** code points.
- `Reader.transferTo` từ đầu StringReader trả **22**.
- Writer trực tiếp ghi cùng các `char` giữ cả `\r\n` lẫn `\n` nếu Writer không chuyển đổi.

**Cảnh báo:** “Số ký tự” trong API Reader không tự có nghĩa số grapheme clusters hiển thị trên màn hình; một chữ người đọc nhìn thấy có thể gồm nhiều Unicode code points, ví dụ base letter + combining mark.

## 6. Khi cần biến đổi **từng dòng**: BufferedReader.readLine()

Các nghiệp vụ như import CSV đơn giản theo dòng (không có quoted multi-line fields), loại dòng trống, chuẩn hóa phần đầu/cuối mỗi dòng hoặc chuyển chữ hoa/thường có thể cần nhìn vào **nội dung từng dòng**.

~~~java
static int normalizeLines(Reader source, Writer target)
        throws IOException {
    var lines = new BufferedReader(source);
    int written = 0;

    for (String line; (line = lines.readLine()) != null; ) {
        var cleaned = line.strip();
        if (cleaned.isEmpty()) {
            continue;
        }
        if (written > 0) {
            target.write("\n");
        }
        target.write(cleaned.toUpperCase(Locale.ROOT));
        written++;
    }
    return written;
}
~~~

Đây là phương thức mẫu nằm trong class có các import `java.io.*` và `java.util.Locale`. Nó không tự đóng Reader/Writer vì **caller là chủ sở hữu tài nguyên**; dùng try-with-resources tại caller khi nguồn là file/socket.

### 6.1. Các biến đổi được thực hiện có chủ đích

- `readLine()` lấy chuỗi **không gồm** ký tự kết thúc dòng. Nó nhận biết `\n`, `\r`, `\r\n` và EOF.
- `strip()` xóa khoảng trắng ở đầu/cuối theo quy tắc Unicode của Java 11+, không giữ nguyên căn lề.
- Dòng trống sau khi strip bị loại.
- `toUpperCase(Locale.ROOT)` chuyển chữ hoa với locale cố định; dùng `Locale.ROOT` khi dữ liệu xử lý cần quy tắc không phụ thuộc ngôn ngữ giao diện/người dùng.
- Writer chèn `\n` giữa các dòng được giữ lại; **không giữ nguyên CRLF**, **không bảo toàn trailing newline**. Đây là kết quả đúng vì chính sách đã chọn thay đổi định dạng.

Không gọi phương thức này là “copy nguyên văn”. Nó là một phép **biến đổi dữ liệu**; nếu input là tài liệu cần bảo toàn chính xác xuống dòng hoặc signature/hash, đây là lựa chọn không phù hợp.

### 6.2. `readLine()` không tự biết newline gốc sau khi trả String

Sau `readLine()`, bạn không còn thông tin dòng ấy kết thúc bởi `\r`, `\n` hay `\r\n`. Nếu cần giữ nguyên byte/char terminators và đồng thời sửa nội dung dòng, phải xây parser theo ký tự hoặc thiết kế bộ đọc vẫn giữ delimiter. Dùng `writer.newLine()` của `BufferedWriter` sẽ chọn dấu xuống dòng theo nền tảng, **không** khôi phục newline gốc.

### 6.3. Dùng `BufferedReader.lines()` khi nào?

~~~java
try (var in = new BufferedReader(new StringReader(" A \n B "))) {
    var lines = in.lines()
            .map(String::strip)
            .filter(line -> !line.isEmpty())
            .toList(); // Java 16+
    System.out.println(lines); // [A, B]
}
~~~

`lines()` là một **Stream<String> lười đọc**. Stream không tự đóng BufferedReader nguồn; try-with-resources vẫn cần quản lý Reader. `IOException` khi đọc trong stream pipeline được bọc vào `UncheckedIOException` theo API. Cũng không được trộn thao tác đọc trực tiếp trên cùng BufferedReader trong lúc terminal operation của `lines()` đang chạy.

Với pipeline ghi sang Writer và cần xử lý `IOException` rõ ràng, vòng `readLine` có `throws IOException` thường dễ kiểm soát hơn `lines().forEach(...)`, vì lambda trong `forEach` không trực tiếp khai báo checked IOException. Không lạm dụng `PrintWriter` để “né” IOException: PrintWriter có cách xử lý lỗi riêng và cần kiểm tra `checkError()` nếu sử dụng.

### 6.4. Không coi mỗi “dòng” là một record với mọi định dạng

CSV có dấu nháy và newline bên trong field; JSON có thể trải qua nhiều dòng; một giao thức mạng có framing riêng. Với những định dạng đó, `readLine()` đơn giản không đủ để phân tích bản ghi đúng. Dùng parser/decoder của định dạng hoặc state machine có hợp đồng phù hợp.

## 7. Khi cần biến đổi **từng khối char[]**

Với dữ liệu lớn, không nhất thiết phải tạo String chứa toàn bộ nội dung. Ta có thể dùng `Reader.read(char[])` và ghi các khối sang Writer:

~~~java
static long rot13Ascii(Reader source, Writer target)
        throws IOException {
    var buffer = new char[3]; // kích thước nhỏ chỉ để minh họa chia chunk
    long total = 0;

    for (int count; (count = source.read(buffer)) != -1; ) {
        for (int i = 0; i < count; i++) {
            char ch = buffer[i];
            if (ch >= 'a' && ch <= 'z') {
                buffer[i] = (char) ('a' + (ch - 'a' + 13) % 26);
            } else if (ch >= 'A' && ch <= 'Z') {
                buffer[i] = (char) ('A' + (ch - 'A' + 13) % 26);
            }
        }
        target.write(buffer, 0, count);
        total += count;
    }
    return total;
}
~~~

ROT13 chỉ thay chữ cái ASCII A–Z và a–z; những `char` khác (dấu tiếng Việt, emoji surrogate units, ký tự xuống dòng) được giữ nguyên. Với `StringWriter` trong ví dụ đầy đủ, kết quả sẽ giữ nguyên chuỗi Unicode ngoài ASCII; đây là lựa chọn **cố ý giới hạn phạm vi biến đổi** để an toàn khi chia chunk nhỏ.

**Lưu ý:** Kích thước buffer `3` chỉ phục vụ minh họa ranh giới chunk. Với I/O thật, hãy chọn buffer kích thước thực tế dựa trên workload/profiling; không có một con số tối ưu cho mọi hệ thống.

### 7.1. Chỉ dùng `count` phần tử hợp lệ

`Reader.read(buffer)` trả số `char` thực sự đọc được hoặc `-1` tại EOF. Buffer có thể vẫn chứa dữ liệu của lần đọc trước ở các vị trí **sau `count`**; vì vậy chỉ xử lý/ghi:

~~~java
target.write(buffer, 0, count);
~~~

Không ghi toàn bộ `buffer.length` mỗi vòng nếu lần đọc chỉ nhận `count` ký tự. Không coi `read` chắc chắn lấp đầy buffer, nhất là ở EOF hoặc nguồn streaming.

### 7.2. Tại sao không được sửa từng `char` tùy ý trong mọi phép biến đổi?

ROT13 ASCII an toàn với input ngoài ASCII **chỉ vì code không đụng tới các `char` đó**. Nhưng các phép xử lý tổng quát như Unicode case folding, chuẩn hóa văn bản, phân tích từ hoặc thay nhiều ký tự có thể phụ thuộc vào:

- Cặp surrogate nằm **qua hai khối**.
- Một base character và combining marks nằm ở hai khối.
- Từ khóa nằm qua ranh giới chunk, ví dụ `"pass"` ở cuối khối và `"word"` ở đầu khối sau.
- Phép chuyển đổi chữ hoa/thường có thể làm **một ký tự thành nhiều ký tự**; xử lý từng `char` bằng `Character.toUpperCase(char)` không luôn tương đương `String.toUpperCase(Locale)`.
- Quy tắc ngôn ngữ/bản địa hóa như tiếng Thổ Nhĩ Kỳ hoặc chữ cái Unicode đặc biệt.

Nếu biến đổi phụ thuộc ngữ cảnh, hãy giữ **state vượt qua chunk boundary** hoặc dùng thư viện/parser Unicode phù hợp. Không giả định gọi `toUpperCase` trên từng `char` rồi ghi lại cùng chiều dài là đúng cho mọi văn bản Unicode.

## 8. Có thể dùng `transferTo` với Writer tự biến đổi không?

**Có**, nếu Writer được thiết kế để biến đổi các ký tự khi nhận `write(...)`. Lúc đó `Reader.transferTo` vẫn chịu trách nhiệm đọc và gửi các `char` theo thứ tự; **Writer chịu trách nhiệm thay đổi output**.

Ví dụ một Writer trang trí chỉ thay ký tự ASCII:

~~~java
import java.io.FilterWriter;
import java.io.IOException;
import java.io.Writer;

final class AsciiUpperWriter extends FilterWriter {
    AsciiUpperWriter(Writer target) {
        super(target);
    }

    @Override
    public void write(char[] chars, int off, int len) throws IOException {
        var converted = java.util.Arrays.copyOfRange(chars, off, off + len);
        for (int i = 0; i < converted.length; i++) {
            if (converted[i] >= 'a' && converted[i] <= 'z') {
                converted[i] = (char) (converted[i] - 'a' + 'A');
            }
        }
        out.write(converted, 0, converted.length);
    }
}
~~~

Đây là **class minh họa riêng**; khi dùng phải tạo Writer đích và bọc bằng `new AsciiUpperWriter(target)`. Chỉ `write(char[],off,len)` được override để minh họa đường gọi phù hợp với transferTo mặc định; nếu muốn một **Writer chuyển đổi tổng quát** dùng bởi nhiều caller, cần xem xét và bao phủ các overload `write(int)`, `write(String,...)`, chính sách flush/close và stateful transformation để tránh đường ghi bỏ qua phép biến đổi.

~~~java
// Trong phương thức có throws IOException:
var target = new java.io.StringWriter();
var convertingWriter = new AsciiUpperWriter(target);
new java.io.StringReader("Java").transferTo(convertingWriter);
System.out.println(target); // JAVA
~~~

**Ưu điểm:** Caller vẫn có thể sử dụng `transferTo` trong pipeline. **Đổi lại:** logic transformation chuyển sang Writer, phức tạp hơn khi có token qua nhiều chunk hoặc khi cần stop sớm sau N record. Với bài toán đơn giản, vòng đọc/ghi minh bạch thường dễ bảo trì hơn. Nếu đã có thư viện Writer decorator/codec với hợp đồng rõ ràng, cách kết hợp này rất hữu ích.

## 9. Chỉ muốn chuyển **một phần** của Reader thì làm gì?

`transferTo` có nghĩa “chuyển đến EOF”; nó không có đối số maxChars hoặc maxLines. Một phương thức read có quota cần tự dừng:

~~~java
static long copyAtMost(Reader in, Writer out, long maxChars)
        throws IOException {
    if (maxChars < 0) {
        throw new IllegalArgumentException("maxChars < 0");
    }
    var buffer = new char[4096];
    long remaining = maxChars;
    long copied = 0;

    while (remaining > 0) {
        int chunk = (int) Math.min(remaining, buffer.length);
        int n = in.read(buffer, 0, chunk);
        if (n == -1) break;
        out.write(buffer, 0, n);
        copied += n;
        remaining -= n;
    }
    return copied;
}
~~~

Đây là **phương thức mẫu** đặt trong class có `import java.io.Reader; import java.io.Writer; import java.io.IOException;`. Nó dừng khi chạm EOF hoặc quota char; đây không phải quota byte UTF-8 hay Unicode codepoint. Nếu cắt đúng giữa một surrogate pair, một output text encoder có thể không biểu diễn cặp Unicode hợp lệ — với yêu cầu cắt ký tự hiển thị, hãy dùng parser theo code point/segment, không quota raw `char` đơn giản.

Khi chỉ cần N **dòng**, sử dụng `readLine` với bộ đếm dòng; khi cần N **bản ghi**, dùng parser/framing theo định dạng nguồn. Không trông đợi `transferTo` tự dừng chỉ vì Writer đã nhận đủ nội dung, trừ khi Writer cố ý ném exception để hủy (lúc đó I/O có thể dở dang và cần xử lý lỗi).

## 10. Reader/Writer khác InputStream/OutputStream như thế nào?

| Khía cạnh | `Reader.transferTo(Writer)` | `InputStream.transferTo(OutputStream)` |
| --- | --- | --- |
| Có từ | **Java 10** | Java 9 |
| Đơn vị xử lý | `char` UTF-16 (ký tự Java) | byte |
| Kết quả đếm | `long` số `char` chuyển | `long` số byte chuyển |
| Dùng cho | Luồng **text đã được giải mã** | Dữ liệu byte/binary |
| Encoding | Thực hiện qua Reader/Writer tương ứng | Không tự giải mã text |
| Thay đổi nội dung | Bản thân method không lập chính sách biến đổi | Bản thân method không giải mã/chuyển đổi |
| Giữ byte-exact | Không phải hợp đồng tổng quát | Phù hợp hơn cho copy bytes với luồng tương ứng |

Khi chỉ cần sao chép một file bất kỳ không thay byte:

~~~java
java.nio.file.Files.copy(
        sourcePath,
        targetPath,
        java.nio.file.StandardCopyOption.REPLACE_EXISTING);
~~~

Đây là **đoạn minh họa** với `sourcePath`/`targetPath` kiểu `Path` và chính sách overwrite có chủ đích. Không dùng Reader cho file ZIP, hình ảnh, PDF, các file mã hóa hoặc byte protocol.

**Với text:** Charset phải được xác định khi tạo Reader/Writer như ví dụ `Files.newBufferedReader(..., UTF_8)` và `Files.newBufferedWriter(..., UTF_8)`. `Reader.transferTo` không tự quyết định UTF-8/UTF-16/Windows-1258; lớp chuyển giữa byte và char mới quyết định.

### 10.1. Đổi charset có thể vẫn giữ ký tự nhưng đổi byte

Chuyển từ Reader đã giải mã UTF-8 sang Writer mã hóa UTF-16 là một dạng **transcoding**. `transferTo` chuyển char, không chủ động chỉnh nội dung text, nhưng bytes đích sẽ khác bytes nguồn theo charset.

Cũng có các tình huống dữ liệu không biểu diễn được trong charset đích, malformed input, BOM hoặc encoding replacement. Chọn charset và error policy phù hợp, đừng quảng bá `transferTo` là cách sao chép **nguyên byte** chỉ vì output text nhìn tương tự.

## 11. Quản lý resource và flush/close

### 11.1. Dùng try-with-resources khi sở hữu luồng

~~~java
try (var in = java.nio.file.Files.newBufferedReader(
             sourcePath, java.nio.charset.StandardCharsets.UTF_8);
     var out = java.nio.file.Files.newBufferedWriter(
             targetPath, java.nio.charset.StandardCharsets.UTF_8)) {
    long copiedChars = in.transferTo(out);
    // Đặt metrics/log phù hợp nếu cần.
}
~~~

Đây là **đoạn minh họa** trong phương thức có `throws IOException` và biến `sourcePath`/`targetPath` kiểu `Path`. Try-with-resources sẽ gọi `close` ngay cả khi đang gặp exception, theo thứ tự đảo ngược việc khai báo.

`Reader.transferTo` **không đóng** hai luồng. Nó cũng **không phải một lời hứa flush mọi bộ đệm của Writer trước khi trả**. Tùy chính sách sở hữu:

- Khi caller sở hữu file Writer, `close` của Writer trong try-with-resources thường xử lý việc flush/finalize dữ liệu trước khi giải phóng tài nguyên.
- Với Writer dùng chung còn tiếp tục được dùng, caller có thể chủ động `flush()` khi cần đẩy nội dung ra đích theo hợp đồng của Writer.
- Không tự `close()` Writer do caller khác sở hữu nếu API của bạn chỉ nhận Writer để ghi bổ sung.
- Nếu dùng `StringWriter` để demo, không có đích file/network thật; quy tắc tài nguyên I/O có thể đơn giản hơn.

**Trong ví dụ `ProbeWriter`**, Reader mặc định không gọi flush/close và bộ đếm vẫn bằng 0, nhưng hãy dùng đây để minh họa **hành vi thử nghiệm của cặp class**, không suy rộng thành bảo đảm “mọi subclass transferTo không bao giờ flush”. Hợp đồng quan trọng là **không tự đóng Reader và Writer**.

### 11.2. IOException có thể xảy ra khi output đã bị ghi một phần

Khi đọc hoặc ghi lỗi, `transferTo` có thể đã tiêu thụ một phần input và ghi một phần output. Không có rollback. JavaDoc khuyến nghị đóng cả hai luồng sớm nếu lỗi I/O; try-with-resources là một cách phù hợp.

Nếu đang tạo **file kết quả quan trọng** và không muốn để lại file đích dở dang, cân nhắc:

1. Ghi sang file tạm mới cùng file system/đích thích hợp.
2. Chỉ sau khi transfer, flush/close và validation thành công mới đổi file tạm sang path đích.
3. Nếu môi trường hỗ trợ, dùng `Files.move` với `ATOMIC_MOVE` phù hợp; **không** giả định mọi file system hỗ trợ atomic rename.
4. Xử lý cleanup của file tạm khi thất bại, cùng chính sách overwrite/quyền truy cập/backup.
5. Nếu tính toàn vẹn byte là tiêu chí, chọn byte-copy và checksum byte-level thay vì chỉ dựa số `char`.

**Quan trọng:** `transferTo` không phải một phép ghi file nguyên tử hay giao dịch data store.

### 11.3. Chờ EOF và giới hạn của nguồn lâu dài

Một `Reader` đọc từ socket, pipe hoặc nguồn đang tiếp tục phát dữ liệu có thể **chưa có EOF**. `transferTo` có thể chờ mãi; nó không có tham số timeout và việc interrupt/đóng bất đồng bộ có behavior tùy Reader/Writer theo tài liệu. Với giao thức mạng, cần framing và timeout/cancellation ở layer phù hợp; không dùng `transferTo` với kỳ vọng “nó tự nhận đủ một request rồi dừng”.

## 12. Hiệu năng, buffering và bộ nhớ

**Hướng dẫn thực dụng:**

- Khi **không cần biến đổi**, `transferTo` thường giúp code ngắn hơn vòng đọc/ghi thủ công và cho implementation cơ hội dùng cách truyền hiệu quả.
- `BufferedReader`/`BufferedWriter` hữu ích khi thao tác nhiều lần với số ký tự nhỏ; không cần tự bọc nhiều lớp buffer vô nghĩa mà không đo lường.
- Vòng `read(char[])` phù hợp để xử lý theo block, cho phép theo dõi tiến độ/quota và kiểm soát memory footprint; chọn buffer size theo workload và profiling.
- Xử lý từng dòng có thể tạo String cho từng line; nó không đồng nghĩa với việc giữ **cả file** trong RAM. Nhưng một **dòng duy nhất cực dài** vẫn có thể làm tăng memory, nên cần giới hạn input khi không tin cậy.
- `StringWriter` tích lũy output trong memory; muốn streaming ra file, chọn Writer file/đích phù hợp.
- `Reader.transferTo` không phải kỹ thuật **zero-copy byte-level**; khi nguồn là file text, decoding/encoding vẫn có chi phí.
- Không tự tin khẳng định `transferTo` luôn nhanh hơn manual loop trên mọi Reader/Writer. Có subclass tối ưu khác nhau, dữ liệu lớn/nhỏ khác nhau và bộ đệm có ảnh hưởng lớn.

### 12.1. Tối ưu hóa dựa trên yêu cầu kết quả

Trước khi chọn một buffer size, xác định:

1. Output cần **giữ nguyên `char`** hay phải biến đổi?
2. Cần thống kê từng record hoặc validation trong khi đọc không?
3. Input có thể không có EOF không?
4. Output có giới hạn kích thước và chính sách dừng sớm không?
5. Cần bảo toàn CRLF, whitespace, charset và content hash không?
6. Tần suất gọi, kích thước dữ liệu, heap/GC, độ chậm mạng và disk là bao nhiêu?

Đừng giảm bớt tính đúng đắn Unicode hoặc bỏ validation chỉ vì thấy một vòng copy ngắn hơn. Hợp đồng output phải được ưu tiên trước micro-optimization.

## 13. Chương trình Java 17+ độc lập đã kiểm thử

Đoạn code sau minh họa **ba lựa chọn** trên cùng nội dung, đồng thời kiểm tra EOF, chỉ chuyển phần còn lại, null Writer, Unicode và quyền sở hữu luồng.

Lưu file **`ReaderTransferStrategyDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.io.Writer;
import java.util.Locale;

public class ReaderTransferStrategyDemo {
    static final class ProbeWriter extends Writer {
        private final StringBuilder content = new StringBuilder();
        int flushCount;
        int closeCount;

        @Override
        public void write(char[] chars, int offset, int length) {
            content.append(chars, offset, length);
        }

        @Override
        public void flush() {
            flushCount++;
        }

        @Override
        public void close() {
            closeCount++;
        }

        String text() {
            return content.toString();
        }
    }

    static long rot13Ascii(Reader source, Writer target) throws IOException {
        var buffer = new char[3];
        long total = 0;

        for (int count; (count = source.read(buffer)) != -1; ) {
            for (int i = 0; i < count; i++) {
                char ch = buffer[i];
                if (ch >= 'a' && ch <= 'z') {
                    buffer[i] = (char) ('a' + (ch - 'a' + 13) % 26);
                } else if (ch >= 'A' && ch <= 'Z') {
                    buffer[i] = (char) ('A' + (ch - 'A' + 13) % 26);
                }
            }
            target.write(buffer, 0, count);
            total += count;
        }
        return total;
    }

    static int normalizeLines(Reader source, Writer target)
            throws IOException {
        var lines = new BufferedReader(source);
        int written = 0;
        for (String line; (line = lines.readLine()) != null; ) {
            var cleaned = line.strip();
            if (cleaned.isEmpty()) {
                continue;
            }
            if (written > 0) {
                target.write("\n");
            }
            target.write(cleaned.toUpperCase(Locale.ROOT));
            written++;
        }
        return written;
    }

    public static void main(String[] args) throws IOException {
        String content = "  Java 10\r\ncaf\u00E9\nA\uD83D\uDE00Z  ";

        try (var in = new StringReader(content);
             var out = new StringWriter()) {
            long transferred = in.transferTo(out);
            System.out.println("direct-count=" + transferred);
            System.out.println("direct-equal=" + content.equals(out.toString()));
            System.out.println("direct-crlf=" + out.toString().contains("\r\n"));
            System.out.println("code-points=" +
                    content.codePointCount(0, content.length()));
            System.out.println("reader-after-eof=" + in.read());
        }

        var partlyRead = new StringReader(content);
        partlyRead.read();
        var remainder = new StringWriter();
        System.out.println("remaining-count=" + partlyRead.transferTo(remainder));
        System.out.println("remaining-is-suffix=" +
                remainder.toString().equals(content.substring(1)));

        var probe = new ProbeWriter();
        long probeCount = new StringReader("abc").transferTo(probe);
        System.out.println("probe-count=" + probeCount);
        System.out.println("probe-text=" + probe.text());
        System.out.println("probe-flush=" + probe.flushCount);
        System.out.println("probe-close=" + probe.closeCount);

        var transformedLines = new StringWriter();
        int keptLines = normalizeLines(new StringReader(content), transformedLines);
        System.out.println("line-count=" + keptLines);
        System.out.println("line-normalizes-crlf=" +
                !transformedLines.toString().contains("\r"));
        System.out.println("line-uppercase=" +
                transformedLines.toString().startsWith("JAVA 10\n"));
        System.out.println("line-no-final-newline=" +
                !transformedLines.toString().endsWith("\n"));

        var transformedChunks = new StringWriter();
        long transformedCount = rot13Ascii(
                new StringReader(content), transformedChunks);
        System.out.println("chunk-count=" + transformedCount);
        System.out.println("chunk-preserves-crlf=" +
                transformedChunks.toString().contains("\r\n"));
        System.out.println("chunk-rot13=" +
                transformedChunks.toString().startsWith("  Wnin 10\r\n"));
        System.out.println("chunk-emoji=" +
                transformedChunks.toString().contains("\uD83D\uDE00"));

        try {
            new StringReader("x").transferTo(null);
        } catch (NullPointerException expected) {
            System.out.println("null-writer=rejected");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 ReaderTransferStrategyDemo.java
java ReaderTransferStrategyDemo
~~~

**Stdout chính xác** (đã biên dịch và chạy):

~~~text
direct-count=22
direct-equal=true
direct-crlf=true
code-points=21
reader-after-eof=-1
remaining-count=21
remaining-is-suffix=true
probe-count=3
probe-text=abc
probe-flush=0
probe-close=0
line-count=3
line-normalizes-crlf=true
line-uppercase=true
line-no-final-newline=true
chunk-count=22
chunk-preserves-crlf=true
chunk-rot13=true
chunk-emoji=true
null-writer=rejected
~~~

### 13.1. Phân tích output theo phương pháp

**Truyền trực tiếp:**

- `direct-count=22` là số đơn vị `char`. `code-points=21` vì emoji cần hai `char`.
- `direct-equal=true` chứng minh các `char` nhận trong StringWriter giống nội dung đầu vào.
- `direct-crlf=true` cho thấy `\r\n` được giữ khi copy thẳng tới StringWriter.
- `reader-after-eof=-1` minh họa Reader đã tới cuối sau khi chuyển thành công.

**Reader đã đọc trước một phần:**

- `remaining-count=21` vì một dấu cách đầu tiên đã bị `read()` tiêu thụ.
- `remaining-is-suffix=true` chứng minh `transferTo` chỉ lấy phần còn lại từ vị trí hiện tại.

**Flush/close:**

- `probe-count=3`, `probe-text=abc`: Reader chuyển toàn bộ ba ký tự.
- `probe-flush=0`, `probe-close=0`: với cặp `StringReader` và `ProbeWriter` của chương trình này, việc chuyển không gọi flush/close. Đây không phải lý do để bỏ quản lý resource của Writer trong ứng dụng thật.

**Biến đổi theo dòng:**

- `line-count=3`: có ba dòng không rỗng sau làm sạch.
- `line-normalizes-crlf=true`: các dấu `\r` gốc không được giữ, vì readLine bỏ terminator và code chủ động chèn `\n`.
- `line-uppercase=true`: dữ liệu được chuyển hoa và xóa khoảng trắng đầu dòng.
- `line-no-final-newline=true`: chương trình không thêm newline sau dòng cuối.

**Biến đổi theo chunk:**

- `chunk-count=22`: số `char` đầu vào vẫn là 22; phép ROT13 giữ chiều dài.
- `chunk-preserves-crlf=true`: đoạn code không động tới các ký tự xuống dòng.
- `chunk-rot13=true`: `Java` được biến thành `Wnin` theo ROT13 ASCII.
- `chunk-emoji=true`: surrogate pair của emoji được giữ, dù buffer chỉ dài 3 `char`.

**Lỗi đầu vào:**

- `null-writer=rejected`: `transferTo(null)` ném `NullPointerException` theo API.

### 13.2. Giới hạn của ví dụ

Chương trình dùng `StringReader`/`StringWriter` để có output xác định và không gây tác động file system. Nó không đo performance hoặc giới hạn blocking của nguồn mạng; cũng không chứng minh mọi biến đổi Unicode có thể xử lý theo từng `char`. Với file thật, cần charset/try-with-resources và chính sách file đích riêng.

## 14. Lỗi phổ biến và cách xử lý

| Lỗi | Tại sao sai | Cách xử lý |
| --- | --- | --- |
| Dùng `Reader.transferTo` cho ZIP/PDF/ảnh | Text decoding/encoding không phải copy byte-exact | `Files.copy` hoặc byte streams |
| Cho rằng `transferTo` chỉnh sửa/normalize nội dung | Nó chuyển `char` theo thứ tự, transformation không có sẵn | Dùng readLine/read(char[])/decorator |
| Dùng `transferTo` rồi mong còn nội dung để đọc | Reader đã tới EOF nếu thành công | Mở Reader mới hoặc dùng mark/reset có điều kiện |
| Coi count là số byte UTF-8 | `char` UTF-16 khác byte/code point | Chọn byte API khi đếm byte |
| Quên quản lý Writer/Reader | Method không tự close | try-with-resources/ownership contract |
| Coi method tự flush đúng lúc | Không có bảo đảm flush mọi buffer theo nhu cầu caller | flush/close theo lifecycle |
| Dùng `readLine` rồi đòi giữ CRLF | Terminator bị readLine loại bỏ | Parser giữ delimiter hoặc chuyển nguyên văn |
| Gọi `write(buffer)` thay vì `write(buffer,0,n)` | Ghi lại ký tự rác/tồn từ lần read trước | Luôn dùng số `n` nhận từ read |
| Biến đổi Unicode bằng từng `char` độc lập | Surrogate/combining/token có thể vượt ranh giới chunk | Xử lý có trạng thái/codepoint-aware |
| Dùng `transferTo` cho nguồn không có EOF | Có thể block vô thời hạn | Framing/timeout/cancellation |
| Xem `transferTo` là transaction | IOException có thể để output dở dang | Ghi temp + validate + move khi phù hợp |
| Cho rằng buffer tự động vô hạn memory | StringWriter vẫn giữ cả output | Dùng Writer tới sink streaming |
| Dùng `BufferedReader.lines()` mà quên close Reader | Stream lười không sở hữu nguồn để tự đóng | try-with-resources Reader |
| Biến đổi text mà không quy định charset | Output có thể khác byte hoặc không encode được | Định rõ UTF-8/encoding policy |
| Bọc mọi Reader/Writer trong nhiều buffer | Tăng phức tạp, không bảo đảm nhanh hơn | Benchmark theo workload |
| Xử lý dòng cực dài không giới hạn từ input lạ | readLine có thể giữ một line lớn | Áp dụng quota/line length policy |
| Nghĩ flush/close do transferTo thực hiện | Không nên dựa trên suy đoán | Đóng và xử lý lỗi ở caller |
| Coi Writer decorator tự bao phủ mọi overload | Có overload write khác có thể đi đường khác | Thiết kế wrapper đầy đủ, test mọi đường ghi |

## 15. Bài tập có đáp án

**Bài 1.** Với `StringReader("ABCDE")`, sau khi gọi `read()` một lần rồi `transferTo(writer)`, số `char` chuyển là bao nhiêu?

**Đáp án:** `4`; Writer nhận `"BCDE"` vì Reader đã tiêu thụ A.

**Bài 2.** Vì sao `Reader.transferTo` trả `long` chứ không nên hiểu là số byte?

**Đáp án:** API chuyển các đơn vị `char` Java/UTF-16. Số byte phụ thuộc charset và cách Writer mã hóa; có thể khác số `char`.

**Bài 3.** `StringReader("A\uD83D\uDE00Z")` có bao nhiêu đơn vị `char` và Unicode codepoints?

**Đáp án:** `4` `char` và `3` codepoints. Emoji ngoài BMP được biểu diễn bằng surrogate pair.

**Bài 4.** Khi copy nội dung text sang `StringWriter` mà không cần thay đổi gì, nên chọn gì?

**Đáp án:** `reader.transferTo(writer)` vì chuyển theo thứ tự tới EOF, dễ đọc và trực tiếp.

**Bài 5.** Nếu cần bỏ dòng trống và đổi tất cả dòng còn lại thành chữ hoa, `transferTo` trực tiếp có đủ không?

**Đáp án:** Không. Cần pipeline xử lý dòng/chunk hoặc Writer decorator có logic chuyển đổi; `BufferedReader.readLine` là lựa chọn phù hợp khi chính sách theo dòng.

**Bài 6.** Tại sao `BufferedReader.readLine` có thể làm mất CRLF?

**Đáp án:** Nó trả String **không kèm terminator**. Khi Writer chèn `\n`, CRLF bị chuẩn hóa theo chính sách.

**Bài 7.** Dữ liệu là ảnh PNG, user cần copy giống byte gốc. Dùng Reader hay byte streams?

**Đáp án:** Byte streams hoặc `Files.copy`. Reader/Writer là API text, không hứa giữ byte-exact.

**Bài 8.** `transferTo` tự đóng nguồn và đích không?

**Đáp án:** Không. Caller chịu trách nhiệm vòng đời, thường dùng try-with-resources.

**Bài 9.** Nếu một Writer buffer chưa được flush mà `transferTo` trả, có thể coi nội dung đã được đồng bộ ra disk/mạng chưa?

**Đáp án:** Không. Cần flush/close theo hợp đồng Writer và yêu cầu durability; ngay cả flush cũng không đồng nghĩa fsync hay transaction.

**Bài 10.** `read(buffer)` trả `n = 2` với buffer dài 4096. Nên `write` bao nhiêu?

**Đáp án:** `writer.write(buffer,0,2)`; chỉ hai phần tử đầu là dữ liệu vừa đọc hợp lệ.

**Bài 11.** Vì sao phép tìm `"password"` có thể sai nếu chỉ kiểm tra từng chunk String riêng?

**Đáp án:** Token có thể nằm ở ranh giới chunk; cần giữ phần cuối chunk trước, parser/state machine hoặc cách lọc có ngữ cảnh.

**Bài 12.** Nếu cần dừng ngay sau 1000 `char` và để phần còn lại của Reader chưa đọc, nên dùng `transferTo` không?

**Đáp án:** Không. Dùng vòng đọc có quota. Nếu quota phải tính Unicode codepoint, cần thêm xử lý surrogate pair/Unicode, không chỉ đếm `char`.

**Bài 13.** Tại sao không nên nói `transferTo` chắc chắn nhanh hơn mọi vòng copy?

**Đáp án:** Hiệu năng tùy loại Reader/Writer, buffering, charset, kích thước dữ liệu và môi trường. Chọn theo yêu cầu đầu ra và đo thực tế.

**Bài 14.** `BufferedReader.lines()` có tự đóng BufferedReader không?

**Đáp án:** Không. Reader vẫn cần được quản lý bởi caller, ví dụ try-with-resources. I/O errors trong Stream có thể bị bọc thành `UncheckedIOException`.

**Bài 15.** Khi có `IOException` giữa quá trình transfer, có chắc Writer chưa ghi gì không?

**Đáp án:** Không. Một phần dữ liệu có thể đã được ghi/đọc. Đóng luồng, xử lý file tạm/rollback ở tầng ứng dụng nếu yêu cầu output nguyên vẹn.

**Bài 16.** Có thể dùng `Reader.transferTo(customWriter)` để vừa truyền vừa biến đổi không?

**Đáp án:** Có. Khi đó transformation nằm ở **custom Writer**. Phải bảo đảm Writer xử lý mọi overload write được caller sử dụng, trạng thái qua chunk và lỗi/lifecycle.

**Bài 17.** Nếu Reader đọc nguồn socket không bao giờ có EOF, `transferTo` có tự trở về sau một request không?

**Đáp án:** Không có bảo đảm; method có thể chờ vô thời hạn. Cần framing, giới hạn và timeout/cancellation theo giao thức.

**Bài 18.** Đổi từ UTF-8 sang UTF-16 qua Reader/Writer có thể giữ nội dung Unicode nhưng không giữ byte giống nhau không?

**Đáp án:** Có. `transferTo` chuyển `char`; Writer dùng charset của mình để mã hóa thành bytes.

## 16. Checklist để chọn API trong dự án

Trước khi triển khai luồng xử lý text, hãy trả lời:

1. **Nguồn là text hay binary?** Nếu binary/byte-exact, dùng byte API.
2. **Output phải nguyên văn theo `char` hay được phép biến đổi?** Nếu nguyên văn, `transferTo` là ứng viên tốt.
3. **Nếu biến đổi, đơn vị ngữ nghĩa là gì?** Dòng, record, token, codepoint hay char độc lập?
4. **Có cần giữ nguyên `\r\n`/`\n`, whitespace và trailing newline không?**
5. **Có cần dừng sớm, giới hạn ký tự/record, lọc input hoặc phát progress không?**
6. **Reader/Writer có thể block vô hạn không?** Timeout, cancellation và giao thức framing ở đâu?
7. **Caller sở hữu Reader/Writer nào?** Ai phải flush và close, xử lý exception?
8. **Nếu lỗi giữa chừng, output dở dang có được chấp nhận không?** Có cần temp file + atomic move?
9. **Charset có được định rõ ở nơi mở Reader/Writer không?** Có xử lý malformed input không?
10. **Có surrogate pairs, combining marks hoặc token qua chunk boundary không?**
11. **Có tránh buffer cả file không?** `StringWriter`/`readAllLines` có phù hợp dung lượng dữ liệu không?
12. **Test đã kiểm tra số char, EOF, content equality, CRLF và transformation đúng chưa?**
13. **Có kiểm thử dữ liệu rỗng, Writer null, IOException và source bị đọc trước một phần không?**
14. **Đã đo performance theo Reader/Writer thật thay vì kết luận từ demo StringReader chưa?**

## 17. Tài liệu chính thức còn áp dụng

1. [Java SE 17 – `Reader.transferTo(Writer)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Reader.html#transferTo(java.io.Writer)): hợp đồng since Java 10, trả số ký tự, EOF, không tự close, IOException/NullPointerException và có thể block.
2. [Java SE 17 – `BufferedReader.readLine()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html#readLine()): xử lý ký tự kết thúc dòng và việc không trả terminator trong String.
3. [Java SE 17 – `BufferedReader.lines()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html#lines()): stream lười, quyền sở hữu Reader và UncheckedIOException.
4. [Java SE 17 – `Writer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Writer.html): các overload write, flush, close, behavior của character output.
5. [Java SE 17 – `Files.newBufferedReader` và `newBufferedWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): tạo Reader/Writer theo Charset cụ thể.
6. [Java SE 17 – `InputStream.transferTo(OutputStream)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html#transferTo(java.io.OutputStream)): chuyển byte, khác Reader.transferTo.
7. [Java SE 17 – `String.codePointCount`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#codePointCount(int,int)): phân biệt `char` UTF-16 và Unicode codepoints.
8. [Java SE 17 – `StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8/UTF-16 và các charset chuẩn.
9. [OpenJDK – JEP 286](https://openjdk.org/jeps/286): `var` từ Java 10, dùng để khai báo biến cục bộ trong các ví dụ.
10. [Java SE 17 – `Files.copy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#copy(java.nio.file.Path,java.nio.file.Path,java.nio.file.CopyOption...)): sao chép theo byte/file thay vì diễn giải text.

**Tóm tắt:** `Reader.transferTo(Writer)` là cách gọn để **truyền trực tiếp những ký tự còn lại tới EOF** khi không cần biến đổi, nhưng **không đóng luồng và không bảo đảm ghi nguyên tử hoặc byte-exact**. Khi nghiệp vụ yêu cầu lọc dòng, chuẩn hóa, xử lý từng record/token, giới hạn lưu lượng hoặc kiểm soát Unicode, hãy chọn `BufferedReader.readLine()`, vòng `read(char[])` có trạng thái hoặc Writer decorator phù hợp. Quan trọng nhất là **định rõ hợp đồng kết quả và lifecycle I/O**, không chọn API chỉ vì cú pháp ngắn.
