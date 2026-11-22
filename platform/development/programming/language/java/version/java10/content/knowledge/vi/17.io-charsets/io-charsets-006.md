# PrintStream nhận Charset khi ghi ra luồng hoặc tệp

## 1. Vì sao PrintStream cần một Charset tường minh?

`java.io.PrintStream` là lớp xuất dữ liệu thuận tiện: hỗ trợ `print`, `println`, `printf`, `format` và nhiều kiểu dữ liệu Java. Nó bọc một `OutputStream` để gửi dữ liệu xuống **luồng byte**, nhưng trước khi ghi văn bản, cần chuyển các ký tự Unicode của Java thành byte theo một **bảng mã (charset)**.

Từ **Java 10**, `PrintStream` có thêm các constructor nhận trực tiếp `java.nio.charset.Charset`. Ba dạng quan trọng:

~~~java
// Các chữ ký constructor của java.io.PrintStream, Java 10+:
new PrintStream(outputStream, autoFlush, charset);
new PrintStream(file, charset);
new PrintStream(fileName, charset);
~~~

Ở đây `outputStream` có kiểu `OutputStream`, `autoFlush` là `boolean`, `file` là `java.io.File`, `fileName` là `String` và `charset` là `java.nio.charset.Charset`.

Các constructor mới vẫn tồn tại và được hỗ trợ trên những JDK hiện đại. Chúng cho phép chọn bảng mã bằng một đối tượng đã được kiểm tra, chẳng hạn `StandardCharsets.UTF_8`, thay vì dựa vào mã mặc định của JVM hoặc một tên bảng mã kiểu `String`.

**Ví dụ nhanh:**

~~~java
// Đoạn minh họa bên trong phương thức, có import thích hợp.
var bytes = new ByteArrayOutputStream();

try (var printer = new PrintStream(
        bytes, false, StandardCharsets.UTF_8)) {
    printer.print("Tiếng Việt: Hà Nội");
}

String restored = bytes.toString(StandardCharsets.UTF_8);
System.out.println(restored.equals("Tiếng Việt: Hà Nội")); // true
~~~

Dữ liệu được mã hóa sang byte theo UTF-8, rồi đọc lại đúng bảng mã UTF-8. Ví dụ dùng bộ đệm bộ nhớ để không phụ thuộc font hoặc charset của terminal khi kiểm tra kết quả.

**Nguyên tắc:** đầu ghi và đầu đọc phải thống nhất bảng mã. Một chuỗi ký tự có thể trông đúng trong chương trình Java nhưng trở thành văn bản lỗi nếu byte UTF-8 bị giải mã theo charset khác.

## 2. Ba constructor nhận Charset được bổ sung ở Java 10

### 2.1. Ghi vào một OutputStream

~~~java
PrintStream(OutputStream out, boolean autoFlush, Charset charset)
~~~

- `out`: luồng byte nhận dữ liệu, ví dụ `ByteArrayOutputStream`, `FileOutputStream`, luồng mạng do ứng dụng sở hữu.
- `autoFlush`: bật/tắt chế độ flush tự động theo các sự kiện được định nghĩa cho `PrintStream`.
- `charset`: bảng mã dùng để chuyển **ký tự được in** thành byte.

~~~java
// Đoạn trong một method.
OutputStream out = new ByteArrayOutputStream();

try (PrintStream ps = new PrintStream(
        out, true, StandardCharsets.UTF_8)) {
    ps.println("Xin chào");
}
~~~

Constructor trên nhận đủ **ba đối số**. Trên Java 17, **không có** constructor `new PrintStream(out, StandardCharsets.UTF_8)` chỉ gồm `OutputStream` và `Charset`. Nếu muốn ghi vào luồng có Charset, cung cấp cờ `autoFlush`.

Dùng `PrintStream` bọc một OutputStream phù hợp khi bạn muốn có lệnh `println`, định dạng dữ liệu và toàn quyền cấu hình nơi byte được gửi. Đừng nhầm PrintStream với một API trả về `Writer` thuần ký tự: nó là lớp con của `FilterOutputStream`.

### 2.2. Ghi trực tiếp theo tên tệp

~~~java
PrintStream(String fileName, Charset charset) throws IOException
~~~

~~~java
// Đoạn minh họa trong một phương thức có throws IOException.
try (PrintStream ps = new PrintStream(
        "report.txt", StandardCharsets.UTF_8)) {
    ps.println("Báo cáo");
}
~~~

Constructor có `fileName` tạo một PrintStream ghi vào tệp và dùng charset đã chọn. Nếu tệp đã tồn tại, nội dung cũ sẽ bị **cắt về độ dài 0 (truncate)**; nếu chưa tồn tại, tệp được tạo khi điều kiện hệ thống cho phép. Nó **không phải** chế độ append mặc định.

**Cẩn thận:** với dữ liệu thực, không tự ý dùng tên tệp trong ví dụ để ghi đè file quan trọng. Chương trình hoàn chỉnh ở mục 9 tạo tệp tạm và dọn dẹp an toàn.

### 2.3. Ghi trực tiếp bằng File

~~~java
PrintStream(File file, Charset charset) throws IOException
~~~

~~~java
// Đoạn minh họa, java.io.File và java.nio.charset.StandardCharsets.
File file = new File("notes.txt");

try (PrintStream ps = new PrintStream(
        file, StandardCharsets.UTF_8)) {
    ps.print("Một dòng UTF-8");
}
~~~

So với biến thể tên tệp, constructor này nhận đối tượng `File` có sẵn. Quy tắc quan trọng vẫn như nhau: charset được xác định và file đích bị truncate nếu đã tồn tại.

### Bảng so sánh nhanh

| Constructor | Từ Java | Nơi ghi | Charset chỉ định | autoFlush |
| --- | --- | --- | --- | --- |
| `PrintStream(OutputStream)` | Trước 10 | Luồng byte | Mặc định/phụ thuộc constructor | Không |
| `PrintStream(OutputStream, boolean)` | Trước 10 | Luồng byte | Mặc định/phụ thuộc constructor | Do đối số |
| `PrintStream(OutputStream, boolean, String encoding)` | Trước 10 | Luồng byte | Tên bảng mã dạng String | Do đối số |
| `PrintStream(OutputStream, boolean, Charset)` | **10** | Luồng byte | Đối tượng Charset | Do đối số |
| `PrintStream(String, Charset)` | **10** | Tệp theo tên | Đối tượng Charset | Không bật tự động |
| `PrintStream(File, Charset)` | **10** | Tệp File | Đối tượng Charset | Không bật tự động |

Những constructor cũ dạng tên `String` **vẫn tồn tại**, không nên nói chúng đã bị xóa. Dạng `Charset` giúp code diễn đạt bảng mã rõ hơn và tránh lỗi đánh máy khi dùng hằng số `StandardCharsets`.

## 3. Charset, Unicode và byte: cơ chế chuyển đổi

Java `String` lưu dữ liệu văn bản Unicode. Khi `PrintStream` in văn bản, nó phải chuyển từng chuỗi ký tự sang byte qua một bộ mã hóa (*encoder*) của Charset đã chọn.

Ví dụ chữ `"é"`:

- Trong UTF-8, ký tự này chiếm **2 byte**.
- Trong ISO-8859-1, ký tự đó chiếm **1 byte**.
- Trong US-ASCII, ký tự đó **không biểu diễn được** theo bảng mã.

~~~java
// Đoạn minh họa trong phương thức.
String word = "café";

byte[] utf8 = word.getBytes(StandardCharsets.UTF_8);
byte[] latin1 = word.getBytes(StandardCharsets.ISO_8859_1);

System.out.println(utf8.length);   // 5: c a f (1 byte mỗi chữ) + é (2).
System.out.println(latin1.length); // 4: c a f é (1 byte mỗi chữ).
~~~

**Không nhầm Charset với font:** Charset quyết định **byte** tạo ra. Font/terminal quyết định khả năng hiển thị glyph trên màn hình. Ngay cả byte đúng UTF-8, một terminal giải mã theo bảng mã khác hoặc không hỗ trợ ký tự cũng có thể hiển thị sai.

### 3.1. Ghi text đúng UTF-8 rồi giải mã đúng

~~~java
// Trong method, cần import java.util.Arrays.
String original = "Tiếng Việt";
var target = new ByteArrayOutputStream();

try (PrintStream ps = new PrintStream(
        target, false, StandardCharsets.UTF_8)) {
    ps.print(original);
}

byte[] actual = target.toByteArray();

System.out.println(Arrays.equals(
        actual, original.getBytes(StandardCharsets.UTF_8)
)); // true

System.out.println(original.equals(
        new String(actual, StandardCharsets.UTF_8)
)); // true
~~~

Bản thân `ByteArrayOutputStream` không mang charset; nó chỉ giữ byte. Chính `PrintStream` chọn cách mã hóa byte; phía đọc chọn cách giải mã. Nếu hai phía không thống nhất, văn bản có thể không giống ban đầu.

### 3.2. Ghi bằng charset khác vẫn hợp lệ nếu cả hai phía thống nhất

~~~java
String original = "café";
var bytes = new ByteArrayOutputStream();

try (PrintStream ps = new PrintStream(
        bytes, false, StandardCharsets.ISO_8859_1)) {
    ps.print(original);
}

String restored = new String(
        bytes.toByteArray(), StandardCharsets.ISO_8859_1);

System.out.println(original.equals(restored)); // true
~~~

Vì `"café"` được ISO-8859-1 biểu diễn đầy đủ, ghi và đọc bằng cùng charset cho kết quả đúng. Việc “luôn dùng UTF-8” là lựa chọn tốt cho nhiều định dạng văn bản hiện đại, nhưng nếu giao thức/bên nhận đã yêu cầu một bảng mã khác, phải tuân thủ giao thức đó.

### 3.3. Các Charset tiêu chuẩn nên biết

`java.nio.charset.StandardCharsets` cung cấp hằng số có sẵn, được Java hỗ trợ chuẩn, ví dụ:

- `StandardCharsets.UTF_8`: Unicode UTF-8, lựa chọn phổ biến cho tệp text và giao thức hiện đại.
- `StandardCharsets.UTF_16`: Unicode UTF-16 với quy tắc byte order của charset.
- `StandardCharsets.UTF_16LE` và `UTF_16BE`: chỉ rõ byte order.
- `StandardCharsets.US_ASCII`: tập ký tự ASCII 7-bit.
- `StandardCharsets.ISO_8859_1`: bảng mã Latin-1, không chứa toàn bộ tiếng Việt.

Khi cần charset từ cấu hình động, có thể dùng `Charset.forName(name)` sau khi validate tên và chính sách được phép. Với UTF-8 cố định, `StandardCharsets.UTF_8` dễ đọc hơn và không cần lookup.

## 4. Khác biệt quan trọng: print/println xử lý ký tự, write gửi byte

### 4.1. print(String) mã hóa bằng Charset của PrintStream

~~~java
var bytes = new ByteArrayOutputStream();

try (PrintStream ps = new PrintStream(
        bytes, false, StandardCharsets.UTF_8)) {
    ps.print("é");
}

System.out.println(bytes.size()); // 2: chữ é trong UTF-8.
~~~

Các overload `print` và `println` dùng encoding/charset của PrintStream để chuyển biểu diễn văn bản thành byte. `printf`/`format` cũng dùng cách tạo văn bản rồi mã hóa bằng charset của PrintStream.

### 4.2. write(byte[]) không mã hóa lại các byte đã có

~~~java
var bytes = new ByteArrayOutputStream();

try (PrintStream ps = new PrintStream(
        bytes, false, StandardCharsets.UTF_8)) {
    ps.write(new byte[] {65, 66, 67});
}

System.out.println(bytes.toString(StandardCharsets.UTF_8)); // ABC
~~~

Ở đây các byte `65,66,67` được ghi trực tiếp. Chúng trùng với các byte ASCII của `A,B,C`, nhưng không phải do PrintStream chuyển mã từ ký tự.

**Bẫy phổ biến:**

~~~java
// Phản mẫu: byte đã mã hóa theo ISO-8859-1,
// PrintStream có UTF-8 KHÔNG tự chuyển từ Latin-1 sang UTF-8.
var latin1Bytes = "café".getBytes(StandardCharsets.ISO_8859_1);

try (PrintStream ps = new PrintStream(
        outputStream, false, StandardCharsets.UTF_8)) {
    ps.write(latin1Bytes);
}
~~~

`outputStream` là OutputStream do ứng dụng cung cấp. Luồng đích nhận **byte Latin-1**, không phải byte UTF-8, dù wrapper được tạo với `StandardCharsets.UTF_8`. Nếu mục tiêu là UTF-8 text, hãy in **String** qua `ps.print(...)` hoặc giải mã byte đầu vào bằng charset đúng rồi mã hóa sang UTF-8.

### 4.3. print(Object) không tự tạo JSON

`PrintStream.print(Object)` sử dụng biểu diễn chuỗi (thường qua `String.valueOf` / `toString`), không tự serialize object theo JSON, XML hoặc định dạng protocol. Charset chỉ thay đổi **cách chuỗi được ghi thành byte**, không thay đổi cấu trúc nội dung.

Nếu hệ thống cần JSON/CSV có escaping, thứ tự, locale hay schema cụ thể, hãy tạo nội dung đúng định dạng **trước**, rồi dùng PrintStream hoặc Writer ghi với charset đã công bố.

## 5. Ghi ra File: UTF-8, truncate, append và giải phóng tài nguyên

### 5.1. Mở file bằng constructor Charset

~~~java
// Đoạn minh họa trong method có throws IOException.
Path path = Path.of("report.txt");

try (PrintStream ps = new PrintStream(
        path.toFile(), StandardCharsets.UTF_8)) {
    ps.println("Báo cáo UTF-8");
}
~~~

Với constructor `(File, Charset)`, PrintStream tạo/ghi tệp và **ghi đè nội dung tệp đã tồn tại**. `try-with-resources` đóng stream trong mọi đường đi bình thường và khi ngoại lệ được ném trong body, tránh rò rỉ tài nguyên.

`PrintStream(String fileName, Charset charset)` có hành vi tương tự đối với tên tệp.

### 5.2. Chế độ append phải cấu hình OutputStream riêng

Nếu muốn **ghi tiếp vào cuối file** thay vì truncate:

~~~java
// Đoạn trong method có throws IOException.
Path path = Path.of("report.txt");

try (PrintStream ps = new PrintStream(
        Files.newOutputStream(
                path,
                StandardOpenOption.CREATE,
                StandardOpenOption.APPEND
        ),
        false,
        StandardCharsets.UTF_8
)) {
    ps.println("Dòng được thêm");
}
~~~

Ở đây `Files.newOutputStream` mới là nơi quyết định `CREATE`/`APPEND`. Constructor `PrintStream(OutputStream, boolean, Charset)` chỉ bọc luồng byte đã được mở. Không thêm các tùy chọn append bằng cách đặt `autoFlush=true`: **autoFlush không phải append**.

Nếu cần ghi đè một file qua API `Files`, sử dụng đúng các `StandardOpenOption` như `CREATE`, `TRUNCATE_EXISTING` và `WRITE` theo hợp đồng. Với file quan trọng, cân nhắc quy trình ghi file tạm và thay thế có kiểm soát để tránh lưu lại bản nội dung dở dang khi xảy ra lỗi.

### 5.3. Ghi và đọc phải dùng charset phù hợp

~~~java
// Đoạn minh họa trong method, Java 17+.
Path path = Path.of("example.txt");
String content = "Tiếng Việt";

try (PrintStream ps = new PrintStream(
        path.toFile(), StandardCharsets.UTF_8)) {
    ps.print(content);
}

String restored = Files.readString(path, StandardCharsets.UTF_8);
System.out.println(content.equals(restored)); // true
~~~

Ví dụ minh họa dùng tên `example.txt`; khi chạy chương trình ứng dụng thực tế phải cân nhắc đường dẫn và nội dung cũ. Chương trình hoàn chỉnh mục 9 dùng `Files.createTempFile` để không đụng đến file của người học.

### 5.4. Không đóng System.out hoặc System.err do hệ thống cung cấp

~~~java
// Không nên dùng try-with-resources để đóng System.out:
// try (PrintStream ps = System.out) {
//     ps.println("Hello");
// }
~~~

`System.out` và `System.err` là luồng tiêu chuẩn do môi trường chạy quản lý. Đóng chúng có thể khiến những lệnh in tiếp theo trong ứng dụng không còn hoạt động bình thường.

Nếu tạo **một PrintStream mới bọc System.out**, đóng wrapper cũng có thể đóng luồng nền do wrapper sở hữu. Nếu chỉ muốn in Unicode ra terminal, hãy cân nhắc charset thực tế của console/redirected stdout và phương án cấu hình thích hợp; đừng giả định ép UTF-8 trên wrapper sẽ luôn làm mọi terminal hiển thị đúng.

## 6. autoFlush có tác dụng gì?

Constructor luồng byte nhận `boolean autoFlush`:

~~~java
new PrintStream(out, true, StandardCharsets.UTF_8);
new PrintStream(out, false, StandardCharsets.UTF_8);
~~~

Khi `autoFlush=true`, PrintStream có thể flush luồng nền tự động sau những sự kiện được Javadoc quy định: ghi một mảng byte, gọi một trong các phương thức `println`, hoặc ghi ký tự/byte xuống dòng `'\n'` theo cách API xử lý.

**Không nhầm lẫn:**

- `autoFlush=true` **không** có nghĩa “mỗi ký tự lập tức được ghi bền vững xuống ổ đĩa”.
- `flush()` đẩy dữ liệu qua bộ đệm API xuống OutputStream nền, **không bảo đảm fsync hay durability** trên thiết bị lưu trữ.
- `autoFlush=false` không có nghĩa dữ liệu chắc chắn chưa ghi; tùy luồng/bộ đệm, byte có thể đã được chuyển xuống bên dưới. Khi cần hoàn tất ghi, hãy `flush()`/`close()` theo vòng đời phù hợp.
- `autoFlush` chỉ điều khiển flushing, **không đổi charset**, không tự mở file append, không sửa định dạng văn bản.

~~~java
// Ví dụ cấu hình thường dùng cho một OutputStream do ứng dụng sở hữu:
try (PrintStream ps = new PrintStream(
        outputStream, true, StandardCharsets.UTF_8)) {
    ps.println("READY");
}
~~~

Nếu `outputStream` là một mạng socket hoặc luồng ghi đặc biệt, flush có thể tác động độ trễ và hiệu suất. Khi viết nhiều dòng tệp lớn, lựa chọn `autoFlush` nên dựa vào nhu cầu latency/buffering, không dùng true vô điều kiện.

### println và ký tự xuống dòng

`println()` dùng dấu kết thúc dòng theo môi trường chạy Java. Đừng coi byte cuối của mọi `println` luôn là một byte `0A` trên tất cả nền tảng. Nếu một protocol yêu cầu **chính xác `\r\n` (CRLF)** hay **`\n` (LF)**, hãy ghi chuỗi dấu kết thúc dòng do protocol yêu cầu bằng cách rõ ràng, thay vì phụ thuộc line separator của môi trường.

Để kiểm thử nội dung văn bản độc lập nền tảng, có thể so sánh với `System.lineSeparator()` khi dùng `println`, hoặc dùng `print(...)` không kèm xuống dòng nếu mục tiêu là xác minh byte UTF-8.

## 7. Lỗi I/O: PrintStream dùng checkError, không báo IOException khi print

Một khác biệt đáng chú ý so với nhiều API stream/writer khác là **các thao tác ghi của PrintStream không ném checked `IOException` khi gặp lỗi I/O**. Thay vào đó, `PrintStream` đặt **cờ lỗi nội bộ**; có thể kiểm bằng `checkError()`.

~~~java
// Đoạn minh họa với OutputStream được cung cấp:
try (PrintStream ps = new PrintStream(
        outputStream, true, StandardCharsets.UTF_8)) {
    ps.println("data");

    if (ps.checkError()) {
        throw new IllegalStateException("PrintStream output failed");
    }
}
~~~

`checkError()` cũng flush stream còn mở trước khi kiểm tra trạng thái. Nếu có lỗi ghi xuống đích, cờ lỗi có thể trở thành true và giữ tình trạng lỗi cho tới khi được xóa bằng cơ chế bảo vệ của lớp. Không được đánh giá “lệnh `println` không ném exception” là bằng chứng file đã ghi thành công.

### Lưu ý về constructor File

Các constructor `PrintStream(File, Charset)` và `PrintStream(String, Charset)` khai báo `throws IOException` **khi mở hoặc tạo file**. Điều này **khác** với việc các phương thức `print`/`println` xử lý lỗi I/O qua cờ lỗi sau khi stream đã tạo thành công.

Vì vậy, xử lý I/O thường cần cả:

- `try/catch` hoặc `throws IOException` cho việc **mở/tạo file**.
- Kiểm tra `checkError()` khi ứng dụng cần biết có lỗi **ghi ra** hay không.

Mã production nhạy với mất dữ liệu cũng cần cân nhắc flush/đồng bộ thiết bị/ghi file tạm, tùy khả năng của OutputStream bên dưới. `checkError()==false` chỉ nói PrintStream chưa ghi nhận lỗi, không chứng minh dữ liệu đã được ghi bền vững trên đĩa.

### So sánh với Files.newBufferedWriter

~~~java
// Khi muốn I/O text có checked IOException:
try (BufferedWriter writer = Files.newBufferedWriter(
        path, StandardCharsets.UTF_8)) {
    writer.write("Tiếng Việt");
    writer.newLine();
}
~~~

`BufferedWriter` và nhiều phương thức `Writer` báo `IOException` trực tiếp cho các thao tác ghi, nên phù hợp nếu chính sách xử lý lỗi ghi cần rõ ràng bằng checked exception. `PrintStream` tiện ở các hàm `print`/`printf` nhưng cần nhớ mô hình báo lỗi của nó.

## 8. Ký tự không mã hóa được: PrintStream thay thế, không báo lỗi encoding

`PrintStream` được Javadoc mô tả là **thay những chuỗi ký tự malformed hoặc unmappable bằng ký tự/chuỗi thay thế mặc định của charset**. Nó không có một tùy chọn ở constructor `Charset` để bắt buộc mọi ký tự không thể mã hóa thành exception.

Ví dụ:

~~~java
// Chữ é không có trong US-ASCII.
var bytes = new ByteArrayOutputStream();

try (PrintStream ps = new PrintStream(
        bytes, false, StandardCharsets.US_ASCII)) {
    ps.print("café");
}

String restored = new String(
        bytes.toByteArray(), StandardCharsets.US_ASCII);

System.out.println(restored.equals("café")); // false
~~~

Dữ liệu không được bảo toàn: `US_ASCII` không thể mã hóa chữ `é`. Đừng nhầm với `checkError()`; thay thế ký tự do encoding policy **không nhất thiết** là lỗi I/O được phản ánh bởi cờ của PrintStream.

**Nếu yêu cầu phải báo lỗi thay vì thay thế**, hãy dùng một `CharsetEncoder` có `CodingErrorAction.REPORT` với API phù hợp, ví dụ `OutputStreamWriter`:

~~~java
// Đoạn minh họa trong method có throws IOException.
var encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Writer writer = new OutputStreamWriter(
        outputStream, encoder)) {
    writer.write("café"); // Có thể ném UnmappableCharacterException.
}
~~~

Đây là **mã minh họa** cho cơ chế báo lỗi encoding; `outputStream` phải được khai báo/được cấp bởi ứng dụng. Khi chữ `é` không thuộc US-ASCII, encoder ở chế độ REPORT làm thao tác ghi thất bại thay vì âm thầm thay bằng ký tự khác.

Chính sách cụ thể là yêu cầu nghiệp vụ: với dữ liệu quan trọng cần round-trip chính xác, không nên dựa vào replacement. Với text log thông thường, UTF-8 thường phù hợp và có khả năng biểu diễn phần lớn văn bản Unicode hợp lệ; vẫn cần quan tâm đầu vào malformed nếu cần độ chính xác tuyệt đối.

## 9. Chương trình Java 17+ hoàn chỉnh có thể biên dịch và chạy

Chương trình dưới đây kiểm thử:

1. Ghi văn bản tiếng Việt ra **ByteArrayOutputStream** qua `PrintStream(OutputStream, boolean, Charset)`.
2. So sánh chính xác **byte UTF-8** và giải mã round-trip.
3. Ghi ra **file tạm** bằng `PrintStream(File, Charset)`, sau đó kiểm tra byte và nội dung.
4. Dùng `PrintStream(String, Charset)` để chứng minh mở lại file theo tên sẽ **truncate** nội dung trước đó.
5. So sánh mã hóa ISO-8859-1 và trường hợp mất dữ liệu khi chọn US-ASCII.
6. Kiểm tra `autoFlush` bằng một OutputStream đếm số lần flush.
7. Mô phỏng OutputStream ném IOException để kiểm `checkError()`.

File **`PrintStreamCharsetDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class PrintStreamCharsetDemo {

    static final class CountingOutputStream extends ByteArrayOutputStream {
        int flushCalls;

        @Override
        public void flush() throws IOException {
            super.flush();
            flushCalls++;
        }
    }

    public static void main(String[] args) throws IOException {
        String text = "Tiếng Việt: Hà Nội ☕";

        // 1) Ghi vào bộ đệm byte bằng UTF-8 tường minh.
        var memory = new ByteArrayOutputStream();

        try (PrintStream ps = new PrintStream(
                memory, false, StandardCharsets.UTF_8)) {
            ps.print(text);
        }

        byte[] written = memory.toByteArray();

        System.out.println("memoryTextMatch="
                + text.equals(new String(
                        written, StandardCharsets.UTF_8)));
        System.out.println("memoryBytesMatch="
                + Arrays.equals(
                        written, text.getBytes(StandardCharsets.UTF_8)));

        // 2) Ghi vào file tạm bằng File + Charset.
        Path temp = Files.createTempFile(
                "printstream-charset-", ".txt");

        try {
            try (PrintStream ps = new PrintStream(
                    temp.toFile(), StandardCharsets.UTF_8)) {
                ps.print(text);
                if (ps.checkError()) {
                    throw new IOException("file output failed");
                }
            }

            System.out.println("fileTextMatch="
                    + text.equals(Files.readString(
                            temp, StandardCharsets.UTF_8)));
            System.out.println("fileBytesMatch="
                    + Arrays.equals(
                            Files.readAllBytes(temp),
                            text.getBytes(StandardCharsets.UTF_8)));

            // 3) Mở lại theo String fileName sẽ ghi đè, không append.
            try (PrintStream ps = new PrintStream(
                    temp.toString(), StandardCharsets.UTF_8)) {
                ps.print("NEW");
            }
            System.out.println("fileTruncated="
                    + "NEW".equals(Files.readString(
                            temp, StandardCharsets.UTF_8)));
        } finally {
            Files.deleteIfExists(temp);
        }

        // 4) Cùng text, nhưng byte theo các Charset khác nhau.
        String cafe = "café";
        var latin1 = new ByteArrayOutputStream();

        try (PrintStream ps = new PrintStream(
                latin1, false, StandardCharsets.ISO_8859_1)) {
            ps.print(cafe);
        }

        System.out.println("latin1RoundTrip="
                + cafe.equals(new String(
                        latin1.toByteArray(),
                        StandardCharsets.ISO_8859_1)));
        System.out.println("latin1Bytes=" + latin1.size());

        var ascii = new ByteArrayOutputStream();
        try (PrintStream ps = new PrintStream(
                ascii, false, StandardCharsets.US_ASCII)) {
            ps.print(cafe);
        }

        System.out.println("asciiRoundTrip="
                + cafe.equals(new String(
                        ascii.toByteArray(),
                        StandardCharsets.US_ASCII)));

        // 5) autoFlush gọi flush trên luồng nền khi println.
        var counting = new CountingOutputStream();

        try (PrintStream ps = new PrintStream(
                counting, true, StandardCharsets.UTF_8)) {
            ps.println("line");
            System.out.println("autoFlushTriggered="
                    + (counting.flushCalls > 0));
        }

        // 6) Lỗi ghi được phản ánh qua checkError.
        OutputStream failing = new OutputStream() {
            @Override
            public void write(int value) throws IOException {
                throw new IOException("simulated write failure");
            }
        };

        try (PrintStream ps = new PrintStream(
                failing, true, StandardCharsets.UTF_8)) {
            ps.print("X");
            System.out.println("writeErrorDetected=" + ps.checkError());
        }
    }
}
~~~

**Biên dịch:** lưu file nguồn bằng UTF-8, rồi chạy trên JDK 17 hoặc mới hơn có hỗ trợ `--release 17`:

~~~bash
javac -encoding UTF-8 --release 17 PrintStreamCharsetDemo.java
java PrintStreamCharsetDemo
~~~

**Stdout chính xác**, chỉ sử dụng ký tự ASCII để không phụ thuộc khả năng hiển thị Unicode của terminal:

~~~text
memoryTextMatch=true
memoryBytesMatch=true
fileTextMatch=true
fileBytesMatch=true
fileTruncated=true
latin1RoundTrip=true
latin1Bytes=4
asciiRoundTrip=false
autoFlushTriggered=true
writeErrorDetected=true
~~~

### Giải thích từng nhóm output

**(1) memoryTextMatch / memoryBytesMatch:** `PrintStream` nhận `StandardCharsets.UTF_8`, tạo đúng byte UTF-8 của chuỗi. Giải mã bằng cùng charset ra chuỗi giống ban đầu, và so sánh mảng byte bằng `Arrays.equals` cũng trả `true`.

**(2) fileTextMatch / fileBytesMatch:** constructor `(File, Charset)` đã ghi dữ liệu vào tệp tạm. `Files.readString(..., UTF_8)` đọc đúng nội dung; mảng byte bằng kết quả `text.getBytes(UTF_8)`. Tệp được tạo qua `Files.createTempFile` và xóa trong `finally`, không ghi đè dữ liệu người dùng ở một đường dẫn cố định.

**(3) fileTruncated:** constructor `(String, Charset)` mở lại cùng file, ghi `NEW` và truncate phần văn bản trước. Đọc file thấy đúng `NEW`, không phải phần cũ nối thêm.

**(4) latin1RoundTrip / latin1Bytes:** chuỗi `"café"` có bốn ký tự đều biểu diễn được trong ISO-8859-1, mỗi ký tự 1 byte. Vì ghi và đọc cùng charset, kết quả đúng và `latin1.size() == 4`.

**(5) asciiRoundTrip:** `US_ASCII` không mã hóa được ký tự `é`, `PrintStream` dùng biểu diễn thay thế. Đọc lại không thể có chuỗi `"café"` ban đầu, nên `false`. Chương trình không cố định ký tự thay thế bằng một giả định phụ thuộc charset.

**(6) autoFlushTriggered:** `CountingOutputStream` đếm các lần `flush`. Sau `println` với `autoFlush=true`, ít nhất một lần flush đã được gọi trên luồng nền, nên điều kiện dương. Không dùng số lần flush tuyệt đối vì đó không phải hợp đồng cần phụ thuộc.

**(7) writeErrorDetected:** OutputStream giả lập luôn ném `IOException` khi ghi. `PrintStream` ghi nhận lỗi thay vì ném checked IOException từ `print`, rồi `checkError()` trả `true`.

Chương trình không cần framework, không dùng một đường dẫn cố định và tránh những dòng output tiếng Việt phụ thuộc charset của console. Nó kiểm tra **byte** và **nội dung giải mã**, giúp phát hiện lỗi encoding rõ ràng hơn quan sát chữ trên terminal.

## 10. Đừng phụ thuộc nhầm vào Charset mặc định của JVM hoặc System.out

### 10.1. Charset mặc định đã có thay đổi trong Java hiện đại

Trước Java 18, `Charset.defaultCharset()` thường phụ thuộc hệ điều hành và locale. Từ **Java 18**, **JEP 400 — UTF-8 by Default** đưa UTF-8 thành charset mặc định cho những API Java tương ứng (với cơ chế cấu hình tương thích được JDK hỗ trợ).

Điều này **không làm constructor nhận Charset trở nên thừa**:

- Khi giao thức trao đổi file yêu cầu UTF-8, viết `StandardCharsets.UTF_8` thể hiện hợp đồng rõ ràng và giữ tính tương thích khi code chạy trên JDK 17.
- Một ứng dụng có thể cần ISO-8859-1 hoặc một bảng mã đã được quy định từ bên thứ ba; mặc định UTF-8 không tự đáp ứng yêu cầu đó.
- Trong kiểm thử và triển khai đa môi trường, chọn charset tường minh giảm khả năng đọc/ghi lệch cấu hình.

Không tuyên bố rằng **mọi** luồng in mặc định đều “chắc chắn dùng UTF-8” chỉ vì JDK 18+ có mặc định UTF-8.

### 10.2. System.out và System.err có đặc điểm riêng

`System.out` và `System.err` gắn với đầu ra tiêu chuẩn/console. Charset chúng sử dụng có thể theo cấu hình stdout/stderr và môi trường console, **không nhất thiết bằng `Charset.defaultCharset()`** trong các JDK hiện đại. Nếu redirect ra file hoặc chạy trên terminal có cách giải mã khác, hiển thị ký tự Unicode có thể phụ thuộc môi trường.

Vì vậy, đừng viết test encoding bằng cách chỉ xem `System.out.println("Tiếng Việt")` rồi kết luận file sẽ có byte UTF-8. Với tệp hoặc luồng do chương trình sở hữu, hãy chọn Charset trực tiếp và kiểm byte đầu ra như trong mục 9.

Muốn in Unicode ra console đúng, phải bảo đảm nơi xuất, nơi nhận và khả năng hiển thị của terminal tương thích. Việc tạo wrapper UTF-8 trên `System.out` không tự làm mọi console trở thành UTF-8 và có thể ảnh hưởng vòng đời stdout.

## 11. PrintStream khác gì PrintWriter và Files.newBufferedWriter?

| Nhu cầu | API thường phù hợp | Đặc điểm |
| --- | --- | --- |
| Tiện in nhiều kiểu dữ liệu vào OutputStream | `PrintStream(out, autoFlush, charset)` | Hỗ trợ `print/println/printf`, charset tường minh; kiểm `checkError` cho lỗi I/O |
| In vào file theo tên hoặc `File` với Charset | `PrintStream(fileName, charset)` / `PrintStream(file, charset)` | API từ Java 10; truncate file đã có |
| Ghi chuỗi/text và cần checked IOException trong thao tác ghi | `Files.newBufferedWriter(path, charset)` | Trả `BufferedWriter`, báo `IOException` khi lỗi I/O |
| Ghi text vào OutputStream với charset và xử lý encoding nâng cao | `OutputStreamWriter(out, encoder)` | Có thể cấu hình `CharsetEncoder` với `CodingErrorAction.REPORT` |
| Ghi chuỗi vào file không cần print/printf | `Files.writeString(path, content, charset)` | API Java 11+, thường gọn cho nội dung có sẵn |
| Ghi vào file ở chế độ append | `Files.newOutputStream(path, CREATE, APPEND)` rồi bọc PrintStream | Chính OutputStream quyết định chế độ file |

`PrintWriter` cũng có các hàm `print`/`println` và nhiều constructor nhận Charset trên JDK hiện đại, nhưng nó là Writer cho văn bản chứ không phải OutputStream để xuất byte. Chọn dựa trên giao diện muốn cung cấp và cách xử lý lỗi, không phải chỉ dựa vào việc cả hai đều có tên `print`.

### Một ví dụ thay thế bằng BufferedWriter

~~~java
// Đoạn trong method có throws IOException.
Path path = Path.of("notes.txt");

try (var writer = Files.newBufferedWriter(
        path, StandardCharsets.UTF_8)) {
    writer.write("Tiếng Việt");
    writer.newLine();
}
~~~

`BufferedWriter` phù hợp khi muốn ghi văn bản và nhận lỗi `IOException` theo contract; `PrintStream` tiện khi muốn in dữ liệu đã định dạng qua `print`, `println`, `printf` vào một luồng byte.

## 12. Các lỗi thực tế thường gặp

| Lỗi / nhận định sai | Vì sao sai? | Cách xử lý |
| --- | --- | --- |
| `new PrintStream(out, StandardCharsets.UTF_8)` trên Java 17 | Không có constructor hai tham số `OutputStream, Charset` | Dùng `new PrintStream(out, false, UTF_8)` hoặc `true` |
| Chỉ định Charset ở PrintStream nhưng vẫn `write(byte[])` chứa byte bảng mã khác | `write` gửi raw bytes, không tự chuyển mã lại | Gửi `String` qua `print`, hoặc chủ động decode/encode |
| Ghi UTF-8 nhưng đọc bằng ISO-8859-1 | Byte bị giải mã sai nên dễ xuất hiện ký tự lỗi | Chỉ rõ charset ở cả hai phía theo cùng hợp đồng |
| Giả định file constructor là append | Nó truncate file đã tồn tại | Dùng `Files.newOutputStream(..., APPEND)` |
| Bật `autoFlush` để mong file không bao giờ mất dữ liệu | Flush không phải fsync/durability | Quản lý vòng đời và cơ chế lưu trữ phù hợp |
| Không kiểm tra `checkError` vì `println` không ném IOException | PrintStream có cờ lỗi nội bộ cho lỗi ghi | Kiểm `checkError` khi cần xác nhận không có lỗi ghi |
| Dùng US-ASCII để ghi tiếng Việt rồi kỳ vọng đọc lại nguyên vẹn | Nhiều ký tự không mã hóa được, bị thay thế | Dùng charset đủ bao phủ hoặc encoder REPORT |
| Giả định JDK 18+ mọi stdout luôn UTF-8 | System.out/err có cấu hình console riêng | Kiểm tra môi trường stdout và giao thức đầu nhận |
| Đóng `System.out` sau khi in xong | Các phần sau của ứng dụng có thể không in được | Không tự đóng luồng chuẩn do môi trường quản lý |
| Chuyển tên charset `"UTF8"` bằng String khắp dự án | Dễ lỗi cấu hình, ít rõ hợp đồng hơn hằng số chuẩn | Ưu tiên `StandardCharsets.UTF_8` khi cố định |
| Dùng `println` để tạo file giao thức bắt buộc byte LF | Line separator có thể phụ thuộc nền tảng | Ghi đúng ký tự xuống dòng theo giao thức |
| Tưởng Charset tự kiểm soát JSON/CSV/locale | Charset chỉ quy định byte encoding của ký tự | Tạo đúng nội dung/format rồi encode |
| Không đóng stream ghi file do ứng dụng sở hữu | Có thể rò rỉ tài nguyên hoặc thiếu flush lúc kết thúc | Dùng `try-with-resources` |
| Tưởng việc ghi không ném exception chứng minh dữ liệu đã bền vững | PrintStream có thể báo lỗi bằng cờ, flush không đồng nghĩa fsync | Kiểm error + chiến lược durability thích hợp |

## 13. Checklist thiết kế và kiểm thử

1. **Xác định nơi đích:** OutputStream do ứng dụng sở hữu, file theo `File`/`String`, mạng hay console?
2. **Chọn Charset rõ ràng:** nếu bên nhận yêu cầu UTF-8, dùng `StandardCharsets.UTF_8`; không dựa vào mặc định một cách vô thức.
3. **Chọn đúng constructor:** OutputStream cần đủ `(out, autoFlush, charset)`; File/String dùng `(file, charset)` hoặc `(fileName, charset)`.
4. **Chọn chế độ file:** tạo/ghi đè hay append? Nếu append, cấu hình OutputStream bằng `StandardOpenOption.APPEND`, không nhầm với autoFlush.
5. **Quản lý vòng đời:** dùng `try-with-resources` cho stream/file bạn sở hữu; tránh đóng System.out và System.err.
6. **Chọn cách ghi:** `print/println/printf` cho văn bản cần encode; `write(byte[])` cho byte đã có, không kỳ vọng tự transcode.
7. **Chọn chính sách lỗi:** constructor file có thể ném `IOException`, còn lỗi ghi của PrintStream cần kiểm `checkError`.
8. **Xử lý ký tự không biểu diễn được:** PrintStream mặc định thay thế; nếu nghiệp vụ đòi không mất ký tự, dùng encoder ở chế độ REPORT với Writer/API tương ứng.
9. **Kiểm byte, không chỉ kiểm màn hình:** với dữ liệu Unicode, so sánh `actualBytes` với `expectedString.getBytes(charset)` và round-trip bằng cùng charset.
10. **Kiểm newline:** đừng phụ thuộc byte xuống dòng của `println` khi giao thức quy định separator cụ thể.
11. **Cân nhắc JDK mục tiêu:** constructors nhận Charset có từ Java 10; `Files.readString/writeString` có từ Java 11; chương trình minh họa dùng Java 17.
12. **Không dựa vào default charset của stdout:** JDK 18+ có JEP 400 nhưng `System.out` và `System.err` có cấu hình console riêng.

### Tự đánh giá

**Câu 1.** Muốn ghi vào một `ByteArrayOutputStream` dưới dạng UTF-8 bằng constructor Java 10, cú pháp nào đúng?

**Đáp án:** `new PrintStream(out, false, StandardCharsets.UTF_8)` hoặc thay `false` bằng `true` nếu cần autoFlush.

**Câu 2.** `new PrintStream("data.txt", StandardCharsets.UTF_8)` sẽ append nếu file có sẵn?

**Đáp án:** Không. Constructor dạng fileName truncate nội dung file cũ; muốn append phải dùng OutputStream được mở bằng tùy chọn thích hợp.

**Câu 3.** Sau `new PrintStream(out, false, UTF_8)`, gọi `ps.write(latin1Bytes)` có tự đổi byte Latin-1 thành UTF-8 không?

**Đáp án:** Không. `write(byte[])` gửi raw byte; cần decode/encode có chủ đích.

**Câu 4.** Nếu in `"café"` qua `PrintStream` dùng `US_ASCII`, dữ liệu có luôn khôi phục được không?

**Đáp án:** Không. `é` không thuộc US-ASCII, PrintStream có thể thay ký tự không biểu diễn được bằng representation thay thế của charset.

**Câu 5.** Bật `autoFlush=true` có đảm bảo byte đã được ghi bền vững lên ổ đĩa không?

**Đáp án:** Không. Flush không đồng nghĩa fsync; đồng thời chính sách flush phụ thuộc hành vi API.

**Câu 6.** Tại sao cần kiểm `ps.checkError()` sau khi ghi?

**Đáp án:** PrintStream thường không ném checked IOException trong `print/println` khi xảy ra lỗi I/O; nó ghi trạng thái lỗi nội bộ để kiểm bằng `checkError()`.

**Câu 7.** Constructor `(File, Charset)` và `(String, Charset)` có thể ném checked exception khi mở file không?

**Đáp án:** Có, chúng khai báo `throws IOException`, khác với đường đi báo lỗi qua `checkError` khi ghi.

**Câu 8.** Từ Java 18, default charset UTF-8 có nghĩa mọi System.out trên mọi console chắc chắn dùng UTF-8?

**Đáp án:** Không. Các luồng chuẩn có cấu hình liên quan console/stdout/stderr riêng; nên kiểm tra môi trường và chọn encoding rõ khi tạo luồng/tệp do ứng dụng sở hữu.

**Câu 9.** Có thể dùng `PrintStream` thay cho JSON serializer chỉ bằng cách chọn Charset UTF-8?

**Đáp án:** Không. Charset quyết định mã hóa ký tự thành byte, không tự chuyển object thành JSON hợp lệ.

**Câu 10.** Khi nào nên chọn `Files.newBufferedWriter(path, UTF_8)` thay cho PrintStream?

**Đáp án:** Khi API cần ghi text với checked IOException được báo trực tiếp, hoặc cần Writer hơn là các phương thức print/printf tiện lợi.

## 14. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — PrintStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/PrintStream.html): constructors với `Charset`, `autoFlush`, `checkError`, quy tắc encoding và thay thế ký tự không biểu diễn được.
- [Oracle Java SE 17 — PrintStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintStream.html): kiểm chứng signatures tương thích với Java 17, cùng mốc `Since: 10` của ba constructor nhận Charset.
- [Oracle Java SE 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): tập charset chuẩn có sẵn, gồm UTF-8, UTF-16, ISO-8859-1 và US-ASCII.
- [Oracle Java SE 17 — CharsetEncoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html): cơ chế mã hóa và cấu hình lỗi malformed/unmappable.
- [Oracle Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): mở OutputStream với options, đọc file text bằng charset và ghi thông qua Writer.
- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi default charset kể từ JDK 18, phạm vi và ngoại lệ đối với chuẩn đầu ra console.
- [Oracle JDK 24 — Supported Encodings](https://docs.oracle.com/en/java/javase/24/intl/supported-encodings.html): ghi chú charset của `System.out`/`System.err` có thể khác `Charset.defaultCharset()`.
- [Dev.java — Reading and Writing Files](https://dev.java/learn/api/io/files/): thực hành I/O hiện đại dùng `Files`, `Path` và charset tường minh khi đọc/ghi văn bản.

**Ghi nhớ:** ba constructor nhận `Charset` của `PrintStream` từ **Java 10** giúp định nghĩa chính xác cách **văn bản được mã hóa thành byte** khi ghi ra `OutputStream` hoặc tệp. Hãy dùng `StandardCharsets.UTF_8` khi giao thức cần UTF-8; nhớ rằng `write(byte[])` không tự transcode, mở file trực tiếp có thể ghi đè nội dung cũ, `autoFlush` không phải bảo đảm lưu bền vững và lỗi I/O khi in cần được kiểm bằng `checkError()`.