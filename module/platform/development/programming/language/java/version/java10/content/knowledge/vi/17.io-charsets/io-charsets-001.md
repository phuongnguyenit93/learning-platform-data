# Java 10 — Đối tượng `Charset` trong các API I/O bổ sung

## 1. Mục tiêu bài học

Khi ứng dụng Java ghi hoặc đọc **văn bản** thông qua file, luồng byte hay các công cụ định dạng, nó phải chuyển đổi giữa ký tự Unicode và dãy byte. Quy tắc chuyển đổi đó được biểu diễn bởi `java.nio.charset.Charset`. Nếu bên ghi và bên đọc không thống nhất encoding, văn bản có dấu tiếng Việt có thể bị lỗi dù các lệnh đọc/ghi đều chạy không báo ngoại lệ.

Java 10 đã mở rộng nhiều API I/O để người lập trình có thể **truyền trực tiếp đối tượng `Charset`**, thay vì chỉ truyền tên encoding dạng `String` hoặc dựa vào default charset. Các bổ sung đáng chú ý nằm ở `PrintStream`, `PrintWriter`, `Scanner`, `Formatter` và `ByteArrayOutputStream.toString(Charset)`. Tất cả vẫn là API chuẩn được dùng trong các phiên bản Java hiện đại.

Bài này giúp bạn:

1. Hiểu `Charset` là gì, vai trò ở ranh giới byte ↔ văn bản, và cách dùng `StandardCharsets.UTF_8`.
2. Nhận diện **đúng những overload được bổ sung trong Java 10**, không nhầm với API đã tồn tại từ trước hoặc chỉ xuất hiện ở phiên bản sau.
3. Chọn constructor dùng `Charset` cho `PrintWriter`, `PrintStream`, `Scanner`, `Formatter` và phương thức giải mã `ByteArrayOutputStream.toString(Charset)`.
4. Phân biệt charset cho **encoding/decoding** với `Locale` cho **formatting**, với charset của file nguồn Java, và với default charset của JVM.
5. Sử dụng `try-with-resources`, `flush` và cơ chế kiểm tra lỗi đúng cách.
6. Xử lý tình huống charset không khớp, dữ liệu UTF-8 hỏng, byte không thể giải mã và yêu cầu từ chối dữ liệu lỗi.
7. Chạy được các chương trình thực hành với `javac --release 10` hoặc trên JDK mới, rồi dự đoán stdout chính xác.

**Giới hạn kiến thức:** Chỉ trình bày những cơ chế vẫn áp dụng hiện nay. Những API ra đời sau Java 10 được ghi rõ phiên bản; không dùng overload deprecated hoặc mẹo phụ thuộc encoding của máy.

## 2. Charset là gì? Tại sao I/O văn bản cần nó?

`Charset` xác định cách ánh xạ giữa chuỗi ký tự Unicode và các byte theo một character encoding được hỗ trợ, ví dụ `UTF-8` hoặc `ISO-8859-1`.

```text
Java String / char
      |
      | mã hóa (encode) bằng Charset
      v
  byte[] / OutputStream
      |
      | lưu file, truyền mạng, ghi vào bộ đệm
      v
  byte[] / InputStream
      |
      | giải mã (decode) bằng Charset phù hợp
      v
Java String / char
```

- `OutputStream` ghi **byte**, không mang khái niệm ký tự cho tới khi có bộ mã hóa.
- `InputStream` đọc **byte**, không tự biết byte đó là UTF-8, ISO-8859-1 hay định dạng binary.
- `PrintWriter` và `PrintStream` có các constructor/logic chuyển ký tự thành byte; `Scanner` có thể đọc byte rồi tách thành token sau khi giải mã.
- `ByteArrayOutputStream` giữ byte trong bộ nhớ; `toString(Charset)` giải mã chúng thành `String`.
- Cùng một chuỗi ký tự có thể cho ra **các byte khác nhau** khi dùng những charset khác nhau.

Ví dụ văn bản `"Café"` có ký tự `é` không phải ASCII. Khi mã hóa UTF-8, `é` sử dụng nhiều hơn một byte. Nếu giải mã các byte UTF-8 bằng ISO-8859-1, chuỗi nhận được sẽ không giống chuỗi ban đầu; lỗi thường được gọi là *mojibake*. Việc chuyển byte thành `String` theo một encoding **không tự động nhận diện encoding thật của file**.

### 2.1. Charset là đối tượng cấu hình, không phải dữ liệu văn bản

Một `Charset` như `StandardCharsets.UTF_8` mô tả cách chuyển đổi. Nó **không** chứa văn bản, không mở file và không quyết định thứ tự dòng. Nó được truyền vào các API ở **ranh giới chuyển đổi**.

Cách dùng được khuyến nghị:

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

Charset utf8 = StandardCharsets.UTF_8;
Charset latin1 = StandardCharsets.ISO_8859_1;
```

Đây là các dòng ví dụ đặt trong một phương thức. `StandardCharsets` cung cấp các đối tượng charset tiêu chuẩn được Java bảo đảm hỗ trợ, như UTF-8, UTF-16, US-ASCII và ISO-8859-1. Không cần tra cứu một chuỗi tên mỗi lần đọc/ghi.

Có thể dùng `Charset.forName("UTF-8")` khi tên encoding đến từ cấu hình, nhưng lúc đó phải xử lý trường hợp tên sai hoặc charset không được hỗ trợ. Đối với giao thức cố định sử dụng UTF-8, `StandardCharsets.UTF_8` làm ý định rõ hơn và tránh lỗi gõ tên.

### 2.2. Cặp encode–decode phải thống nhất

```java
var bytes = "Café".getBytes(StandardCharsets.UTF_8);
var correct = new String(bytes, StandardCharsets.UTF_8);
var incorrect = new String(bytes, StandardCharsets.ISO_8859_1);
```

Đây là **mảnh code trong một phương thức**, cần import `StandardCharsets`. `correct.equals("Café")` là `true`; `incorrect.equals("Café")` là `false`. Hai phép giải mã vẫn là lời gọi Java hợp lệ nhưng chỉ một phép khớp với cách byte được tạo.

Không phải lúc nào charset phổ biến nhất cũng đúng: nếu một file thực sự được mã hóa bằng charset khác theo hợp đồng nguồn, cần đọc theo encoding thực tế hoặc chuyển đổi dữ liệu có kiểm soát. **Chọn UTF-8 cho dữ liệu mới** là quy ước hợp lý nhưng không thay thế việc hiểu định dạng đầu vào.

## 3. Chính xác Java 10 đã bổ sung những gì?

Những overload nhận trực tiếp **`Charset`** dưới đây được đánh dấu `Since: 10` trong Javadoc Java SE 10:

| API | Overload bổ sung Java 10 | Vai trò |
|---|---|---|
| `PrintStream` | `PrintStream(OutputStream, boolean, Charset)` | In/format ký tự ra output stream với charset được chỉ định |
| `PrintStream` | `PrintStream(File, Charset)` | Tạo luồng in văn bản đến file với charset |
| `PrintStream` | `PrintStream(String fileName, Charset)` | Tương tự nhưng nhận đường dẫn dạng String |
| `PrintWriter` | `PrintWriter(OutputStream, boolean, Charset)` | Viết ký tự lên byte stream, có cờ auto-flush |
| `PrintWriter` | `PrintWriter(File, Charset)` | Ghi ký tự vào file bằng charset chỉ định |
| `PrintWriter` | `PrintWriter(String fileName, Charset)` | Ghi ký tự vào file bằng tên file và charset |
| `Scanner` | `Scanner(InputStream, Charset)` | Giải mã byte từ input stream trước khi phân tích token |
| `Scanner` | `Scanner(File, Charset)` | Scan văn bản từ file bằng charset |
| `Scanner` | `Scanner(Path, Charset)` | Scan văn bản từ đường dẫn NIO bằng charset |
| `Scanner` | `Scanner(ReadableByteChannel, Charset)` | Giải mã byte từ channel theo charset |
| `Formatter` | `Formatter(OutputStream, Charset, Locale)` | Định dạng dữ liệu rồi ghi byte bằng charset |
| `Formatter` | `Formatter(File, Charset, Locale)` | Định dạng vào file với charset và locale |
| `Formatter` | `Formatter(String fileName, Charset, Locale)` | Định dạng vào file theo tên file, charset và locale |
| `ByteArrayOutputStream` | `toString(Charset)` | Giải mã byte đã tích lũy thành chuỗi |

**Không có nghĩa** Java 10 mới lần đầu cho phép truyền Charset tới mọi API I/O. Ví dụ:

- `InputStreamReader(InputStream, Charset)` đã có từ **Java 1.4**.
- `OutputStreamWriter(OutputStream, Charset)` cũng tồn tại từ lâu.
- `String.getBytes(Charset)` và `new String(byte[], Charset)` đã xuất hiện trước Java 10.
- `Files.newBufferedReader(Path, Charset)` và `Files.newBufferedWriter(Path, Charset, ...)` cũng là những API NIO có trước Java 10.
- `Files.readString(Path, Charset)` và `Files.writeString(Path, ..., Charset)` xuất hiện ở **Java 11**, không dùng chúng trong ví dụ tự nhận là target Java 10.

Giá trị của Java 10 ở đây là **thêm các overload tiện dụng** dùng đối tượng `Charset` trực tiếp cho nhiều luồng in, công cụ quét và định dạng vốn thường nhận tên encoding hoặc mặc định của môi trường.

## 4. Vì sao dùng `Charset` thay vì tên encoding kiểu `String`?

So sánh:

```java
// API nhận tên encoding:
new PrintStream(output, true, "UTF-8");

// API Java 10 nhận đối tượng Charset:
new PrintStream(output, true, StandardCharsets.UTF_8);
```

Đây là mảnh code giả định `output` là `OutputStream` và cần import `PrintStream`/`StandardCharsets`. Hai cách có thể đạt cùng mục tiêu, nhưng cách thứ hai có lợi điểm:

1. **Ý định rõ ở compile time:** tham số là `Charset`, không phải một String bất kỳ.
2. **Không gõ tên bằng tay** cho các charset chuẩn, giảm sai chính tả.
3. **API dễ phối hợp:** một đối tượng `Charset` dùng nhất quán cho write/read/decode trong cùng một luồng xử lý.
4. **Tránh xử lý ngoại lệ charset name không hợp lệ** khi sử dụng các hằng số của `StandardCharsets`; tất nhiên lỗi I/O thực sự vẫn có thể xảy ra.
5. **Không phụ thuộc default charset** của JVM khi dữ liệu bên ngoài được quy định rõ encoding.

Nếu tên encoding được cung cấp từ cấu hình runtime, `Charset.forName(configuredName)` vẫn hữu ích. Hãy kiểm tra cấu hình tại ranh giới hệ thống; sai tên có thể ném `IllegalCharsetNameException` hoặc `UnsupportedCharsetException`, không phải lúc nào cũng là một ngoại lệ I/O checked.

**Lưu ý về lỗi:** constructor nhận `File` hoặc `String fileName` vẫn có thể ném `IOException` do quyền truy cập, đường dẫn, thiết bị lưu trữ hoặc file không tạo được. Việc đổi từ String charset name sang đối tượng `Charset` không làm hoạt động file system hết lỗi.

## 5. `PrintWriter` với `Charset`

`PrintWriter` là công cụ ghi văn bản có các method `print`, `println`, `printf` và `format`. Khi nhận một `OutputStream` cùng `Charset`, nó cần mã hóa ký tự trước khi ghi byte.

Constructor Java 10:

```java
new PrintWriter(outputStream, autoFlush, charset)
```

Ví dụ:

```java
var bytes = new ByteArrayOutputStream();
try (var writer = new PrintWriter(bytes, true, StandardCharsets.UTF_8)) {
    writer.println("Xin chào Việt Nam");
}
String text = bytes.toString(StandardCharsets.UTF_8);
```

Đây là **mảnh code trong phương thức** và cần import `ByteArrayOutputStream`, `PrintWriter`, `StandardCharsets`. `text` chứa nội dung dòng đã ghi và ký tự xuống dòng phù hợp môi trường; đừng so sánh byte xuống dòng với `"\n"` nếu chưa quy định line separator.

### 5.1. Auto-flush và flush có khác nhau?

Với `PrintWriter`, `autoFlush=true` khiến việc flush tự động xảy ra khi gọi `println`, `printf` hoặc `format`, **không phải mọi lời gọi `print`**. Nếu ghi bằng `print` và cần dữ liệu được đẩy tới output stream trước khi kết thúc, gọi `flush()` hoặc đóng writer đúng cách.

```java
try (var writer = new PrintWriter(out, true, StandardCharsets.UTF_8)) {
    writer.print("Café");
    writer.flush();
}
```

Mảnh mã giả định `out` là `OutputStream`. `try-with-resources` sẽ đóng writer khi rời block; đóng wrapper có thể đóng luôn output stream bên dưới, nên phải rõ **ai sở hữu stream**.

### 5.2. Cách kiểm tra lỗi của PrintWriter

`PrintWriter` không ném trực tiếp `IOException` từ các method in trong hoạt động thông thường; có thể gọi `checkError()` để kiểm tra trạng thái lỗi. Hành vi này không phải mới ở Java 10, nhưng rất quan trọng khi dùng constructor mới.

```java
writer.flush();
if (writer.checkError()) {
    throw new IllegalStateException("Writing text failed");
}
```

Đây là mảnh code giả định `writer` đang mở. Không được kết luận thao tác ghi thành công chỉ vì `println` không ném ngoại lệ. Đối với ứng dụng cần báo cáo lỗi I/O chính xác hơn, xem xét `BufferedWriter`/`OutputStreamWriter` hoặc API `Files` phù hợp, có hợp đồng ném `IOException`.

**Không được nhầm encoding lỗi với write lỗi:** `PrintWriter` có thể thay thế ký tự không mã hóa được theo quy tắc encoder mặc định; `checkError()` không phải một phép kiểm tra tính toàn vẹn Unicode nghiêm ngặt. Nếu yêu cầu từ chối dữ liệu không thể mã hóa, dùng `CharsetEncoder` được cấu hình `CodingErrorAction.REPORT`.

## 6. `PrintStream` với `Charset`

`PrintStream` hỗ trợ các method `print`, `println`, `printf`, và có thể ghi byte trực tiếp do kế thừa `FilterOutputStream`. Java 10 bổ sung constructor:

```java
new PrintStream(outputStream, autoFlush, charset)
```

Ví dụ:

```java
var buffer = new ByteArrayOutputStream();
try (var stream = new PrintStream(buffer, true, StandardCharsets.UTF_8)) {
    stream.print("Café | €");
}
String result = buffer.toString(StandardCharsets.UTF_8);
```

Mảnh code trong một phương thức, cần import `PrintStream`, `ByteArrayOutputStream` và `StandardCharsets`. Đối tượng `Charset` chỉ định cách **các lời gọi ghi ký tự** được chuyển sang byte. Nếu dùng `stream.write(byte[])` để ghi raw bytes, đó là hoạt động byte, **không được tự động chuyển encoding** theo `Charset` như method `print(String)`.

### 6.1. PrintStream và PrintWriter khác gì trong ngữ cảnh này?

| Tiêu chí | `PrintStream` | `PrintWriter` |
|---|---|---|
| Trọng tâm API | In nội dung ra byte stream; có cả thao tác byte | In ký tự, kế thừa `Writer` |
| Java 10 nhận `Charset` | Có constructor với `OutputStream`, `File`, tên file | Có constructor tương ứng |
| `print/println/printf` | Có | Có |
| Cơ chế báo lỗi I/O | `checkError()` | `checkError()` |
| `autoFlush` | Theo quy tắc `PrintStream`, bao gồm những trường hợp liên quan newline/ghi byte | Tự động chủ yếu tại `println`, `printf`, `format` |
| Khi phù hợp | Console-like output hay byte stream cần in văn bản | Tập trung viết ký tự/định dạng văn bản |

Không nên chọn chỉ dựa trên tên giống nhau của hai class. Khi yêu cầu kiểm soát byte và encode nghiêm ngặt, thiết kế quanh `OutputStream` với encoder hoặc Writer thích hợp có thể rõ ràng hơn.

## 7. `Scanner` với `Charset`

`Scanner` phân tích **văn bản** thành token theo delimiter và hỗ trợ đọc các kiểu như `int`, `double`. Khi đầu vào là `InputStream`, `File`, `Path` hoặc `ReadableByteChannel`, charset cần thiết để giải mã byte thành ký tự **trước khi tokenizer hoạt động**.

Java 10 cho phép:

```java
new Scanner(inputStream, StandardCharsets.UTF_8)
new Scanner(file, StandardCharsets.UTF_8)
new Scanner(path, StandardCharsets.UTF_8)
new Scanner(channel, StandardCharsets.UTF_8)
```

Đây là các dạng constructor minh họa, không phải bốn lệnh hoàn chỉnh nếu chưa có biến và import phù hợp. Chọn đúng overload theo loại nguồn.

### 7.1. Ví dụ đọc token có dấu tiếng Việt

```java
byte[] data = "mã-01;hợp lệ".getBytes(StandardCharsets.UTF_8);

try (var scanner = new Scanner(
        new ByteArrayInputStream(data), StandardCharsets.UTF_8)) {
    scanner.useDelimiter(";");
    String code = scanner.next();
    String status = scanner.next();
}
```

Mảnh code cần import `ByteArrayInputStream`, `Scanner` và `StandardCharsets`. Kết quả lần lượt là `"mã-01"`, `"hợp lệ"`. Dấu `;` ở đây là delimiter regex do ứng dụng chỉ định; **charset không quyết định cách tách token**.

### 7.2. Đừng nhầm Charset với Locale trong Scanner

- **Charset**: byte nào đại diện cho chữ `é`, chữ `ế`, chữ `đ`?
- **Delimiter**: dấu cách, dấu `;`, hoặc biểu thức regex nào ngăn cách token?
- **Locale**: quy tắc diễn giải một số định dạng địa phương, ví dụ ký tự thập phân hoặc nhóm hàng nghìn, khi gọi `nextDouble()`.

Ví dụ: một file UTF-8 có token `"12,5"` có thể được diễn giải số theo một locale phù hợp, nhưng việc thiết lập `StandardCharsets.UTF_8` **không tự thiết lập locale**. Ngược lại, `scanner.useLocale(Locale.US)` không sửa lỗi giải mã khi các byte thực tế không phải charset scanner đang dùng.

`Scanner` đóng vai trò tokenizer/parser; nếu muốn đọc toàn bộ dòng với ít chi phí phân tích hơn, có thể dùng `BufferedReader` kết hợp charset. `InputStreamReader(InputStream, Charset)` là API **cũ hơn Java 10**, nhưng vẫn hoàn toàn phù hợp hiện nay.

### 7.3. Vòng đời và lỗi Scanner

Đặt `Scanner` trong `try-with-resources` để đóng tài nguyên do nó sở hữu. Nếu scanner được tạo từ một input stream và sau đó bị đóng, nó có thể đóng luôn nguồn bên dưới. Với `System.in` dùng chung, không nên đóng sớm scanner nếu các thành phần khác vẫn cần đọc từ stdin.

`Scanner` có phương thức `ioException()` để lấy `IOException` cuối cùng từ nguồn đọc nếu có; không phải mọi lỗi đọc đều luôn được ném trực tiếp tại `next()`. Khi xử lý file cần độ tin cậy cao, hãy kiểm tra thêm hợp đồng lỗi và đóng tài nguyên.

## 8. `Formatter` kết hợp `Charset` và `Locale`

`Formatter` kết hợp **định dạng** dữ liệu với **ghi văn bản** vào một `OutputStream` hoặc file. Java 10 bổ sung các constructor:

```java
new Formatter(outputStream, charset, locale)
new Formatter(file, charset, locale)
new Formatter(fileName, charset, locale)
```

Đây là những dạng lời gọi để nhận diện API; biến nguồn cần có kiểu và import phù hợp.

Điểm quan trọng là **Charset và Locale là hai trục độc lập**:

| Cấu hình | Trả lời câu hỏi |
|---|---|
| `Charset` | Văn bản cuối cùng được encode thành byte như thế nào? |
| `Locale` | Số, ngày hoặc chữ cái theo định dạng vùng/ngôn ngữ được biểu diễn ra sao? |
| Chuỗi format như `"%.2f"` | Có bao nhiêu chữ số thập phân, độ rộng, quy tắc trình bày nào? |

Ví dụ:

```java
var output = new ByteArrayOutputStream();
try (var formatter = new Formatter(
        output, StandardCharsets.UTF_8, Locale.US)) {
    formatter.format("Giá=%1$.2f", 12.5);
}
String formatted = output.toString(StandardCharsets.UTF_8);
```

Mảnh code cần import `Formatter`, `ByteArrayOutputStream`, `Locale` và `StandardCharsets`. `formatted` bằng `"Giá=12.50"`. `Locale.US` làm dấu thập phân dùng dấu chấm trong ví dụ; UTF-8 mã hóa ký tự `"á"` thành byte. **Không được hiểu rằng UTF-8 tự làm cho số có dấu chấm thập phân.**

### 8.1. Khi nào dùng Formatter thay cho PrintWriter?

`PrintWriter.printf(...)` cũng có khả năng định dạng. `Formatter` hữu ích khi bạn muốn đối tượng formatter riêng có charset và locale rõ ràng, hoặc khi đang dùng API `Formatter` trực tiếp. Chọn theo thiết kế ứng dụng; không có yêu cầu mọi file text phải dùng `Formatter` chỉ vì Java 10 có overload mới.

## 9. `ByteArrayOutputStream.toString(Charset)` — một API Java 10 đặc biệt hữu ích

`ByteArrayOutputStream` tích lũy các byte trong bộ nhớ. Khi muốn chuyển chúng thành văn bản, cần giải mã bằng charset tương ứng.

Java 10 bổ sung:

```java
String text = output.toString(StandardCharsets.UTF_8);
```

Đây là mảnh code, `output` là `ByteArrayOutputStream` và cần import `StandardCharsets`. `toString(Charset)` **không phải** phương thức `Object.toString()` in tên class; nó tạo một `String` bằng cách **decode byte** trong bộ đệm.

So sánh:

```java
var buffer = new ByteArrayOutputStream();
byte[] bytes = "Việt Nam".getBytes(StandardCharsets.UTF_8);
buffer.write(bytes, 0, bytes.length);

String text = buffer.toString(StandardCharsets.UTF_8);
```

Mảnh code trong method, cần `ByteArrayOutputStream` và `StandardCharsets`. `text.equals("Việt Nam")` là `true`.

Một lợi ích của overload nhận `Charset` là không cần dùng `buffer.toString("UTF-8")` với tên encoding dạng String, đồng thời không cần giải mã mặc định theo môi trường. API này đã có từ Java 10 và vẫn hữu ích để kiểm thử nội dung byte do `PrintWriter` hoặc `PrintStream` tạo ra.

### 9.1. Nếu bộ đệm chứa byte UTF-8 hỏng?

`ByteArrayOutputStream.toString(Charset)` theo Javadoc **thay thế các chuỗi byte malformed/unmappable** bằng replacement string mặc định khi decode, thay vì tự động ném một ngoại lệ kiểm soát chất lượng dữ liệu.

Do đó, **trả được `String` không chứng minh byte đầu vào hoàn toàn hợp lệ**. Khi bắt buộc phát hiện UTF-8 lỗi, dùng một `CharsetDecoder` có cấu hình `CodingErrorAction.REPORT`. Ví dụ chạy được trong mục 12.

## 10. Chương trình hoàn chỉnh 1 — I/O trong bộ nhớ với bốn API

Tạo file **`CharsetRoundTripDemo.java`**. Chương trình này dùng các overload Java 10 nhận `Charset` trong `PrintWriter`, `PrintStream`, `Scanner`, `Formatter`, và dùng `ByteArrayOutputStream.toString(Charset)`. Phần `InputStreamReader` là API đã tồn tại trước đó nhưng vẫn là cách chuẩn để minh họa chiều giải mã.

```java
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.Formatter;
import java.util.Locale;
import java.util.Scanner;

public class CharsetRoundTripDemo {
    public static void main(String[] args) throws Exception {
        var utf8 = StandardCharsets.UTF_8;
        String original = "Tiếng Việt: Hà Nội, Huế";

        var bytes = new ByteArrayOutputStream();
        try (var writer = new PrintWriter(bytes, true, utf8)) {
            writer.print(original);
            writer.flush();
            System.out.println("printWriterError=" + writer.checkError());
        }
        System.out.println("writerRoundTrip="
                + original.equals(bytes.toString(utf8)));

        var printed = new ByteArrayOutputStream();
        try (var printStream = new PrintStream(printed, true, utf8)) {
            printStream.print("Café | €");
        }
        System.out.println("printStreamRoundTrip="
                + "Café | €".equals(printed.toString(utf8)));

        var input = new ByteArrayInputStream(
                "mã-01;hợp lệ".getBytes(utf8));
        try (var scanner = new Scanner(input, utf8)) {
            scanner.useDelimiter(";");
            String code = scanner.next();
            String status = scanner.next();
            System.out.println("scannerTokens="
                    + ("mã-01".equals(code)
                            && "hợp lệ".equals(status)));
        }

        var formatted = new ByteArrayOutputStream();
        try (var formatter = new Formatter(
                formatted, utf8, Locale.US)) {
            formatter.format("Giá=%1$.2f", 12.5);
        }
        System.out.println("formatterRoundTrip="
                + "Giá=12.50".equals(formatted.toString(utf8)));

        var readerInput = new ByteArrayInputStream(
                original.getBytes(utf8));
        try (var reader = new BufferedReader(
                new InputStreamReader(readerInput, utf8))) {
            System.out.println("readerRoundTrip="
                    + original.equals(reader.readLine()));
        }
    }
}
```

**Biên dịch và chạy bằng JDK hỗ trợ target Java 10:**

```bash
javac --release 10 -encoding UTF-8 CharsetRoundTripDemo.java
java CharsetRoundTripDemo
```

**Stdout chính xác:**

```text
printWriterError=false
writerRoundTrip=true
printStreamRoundTrip=true
scannerTokens=true
formatterRoundTrip=true
readerRoundTrip=true
```

### 10.1. Giải thích từng bước

1. `utf8` là đối tượng `Charset` duy nhất được truyền nhất quán cho tất cả bước chuyển ký tự/byte.
2. `PrintWriter(bytes, true, utf8)` mã hóa `original`; `flush()` bảo đảm dữ liệu được đẩy vào `ByteArrayOutputStream` trước khi giải mã. `checkError()` trả `false` trong lần chạy bình thường.
3. `bytes.toString(utf8)` giải mã byte bằng **đúng charset** đã dùng khi ghi. Phép so sánh bằng `String.equals` xác nhận chuỗi có dấu được khôi phục.
4. `PrintStream(printed, true, utf8)` làm nhiệm vụ tương tự với chuỗi chứa dấu `é` và ký hiệu `€`.
5. `Scanner(input, utf8)` đọc dữ liệu UTF-8 rồi tách hai token theo dấu `;`; tính đúng đắn của delimiter là vấn đề riêng với charset.
6. `Formatter(formatted, utf8, Locale.US)` xử lý hai khía cạnh cùng lúc: định dạng số `12.5` thành `12.50` theo locale được chọn và mã hóa ký tự Việt ra UTF-8.
7. `InputStreamReader(..., utf8)` giải mã chiều ngược lại và `BufferedReader.readLine()` lấy dòng; đây là kỹ thuật đọc có trước Java 10, được giữ lại vì vẫn hợp lệ và dễ hiểu.

**Ý nghĩa của `-encoding UTF-8`:** cờ đó quy định encoding của **file mã nguồn .java** khi `javac` đọc ký tự có dấu. Nó **khác** với `StandardCharsets.UTF_8` quy định encoding của dữ liệu khi chương trình **chạy**. Trong dự án thực tế, nên cấu hình thống nhất cả hai nhưng không nhầm chúng làm một.

## 11. Chương trình hoàn chỉnh 2 — ghi và đọc file với Charset

Tạo file **`CharsetFileDemo.java`**. Ví dụ tạo một file tạm, lần lượt thử ba API Java 10 ghi văn bản: `PrintWriter(File, Charset)`, `PrintStream(File, Charset)` và `Formatter(File, Charset, Locale)`. Sau mỗi lần ghi, `Scanner(Path, Charset)` đọc lại file.

```java
import java.io.PrintStream;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Formatter;
import java.util.Locale;
import java.util.Scanner;

public class CharsetFileDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("j10-charset-", ".txt");
        try {
            try (var writer = new PrintWriter(
                    file.toFile(), StandardCharsets.UTF_8)) {
                writer.print("Café");
            }
            try (var scanner = new Scanner(
                    file, StandardCharsets.UTF_8)) {
                System.out.println("filePrintWriter="
                        + "Café".equals(scanner.next()));
            }

            try (var out = new PrintStream(
                    file.toFile(), StandardCharsets.UTF_8)) {
                out.print("Hà_Nội");
            }
            try (var scanner = new Scanner(
                    file, StandardCharsets.UTF_8)) {
                System.out.println("filePrintStream="
                        + "Hà_Nội".equals(scanner.next()));
            }

            try (var formatter = new Formatter(
                    file.toFile(), StandardCharsets.UTF_8, Locale.US)) {
                formatter.format("%.2f", 12.5);
            }
            try (var scanner = new Scanner(
                    file, StandardCharsets.UTF_8)) {
                System.out.println("fileFormatter="
                        + "12.50".equals(scanner.next()));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Lệnh:

```bash
javac --release 10 -encoding UTF-8 CharsetFileDemo.java
java CharsetFileDemo
```

**Stdout:**

```text
filePrintWriter=true
filePrintStream=true
fileFormatter=true
```

### 11.1. Điều cần chú ý

- File được tạo trong **thư mục tạm của hệ điều hành**, không dùng một đường dẫn tuyệt đối phụ thuộc máy.
- `try-with-resources` bảo đảm writer/print stream/formatter/scanner được đóng, tránh đọc khi dữ liệu còn nằm trong bộ đệm của writer.
- File được **ghi đè** theo từng lần tạo writer/print stream/formatter. Đây là ví dụ thử các constructor trên cùng file tạm; **không** phải demo append file. Nếu cần append, chọn API có chế độ mở tương ứng.
- `Scanner(Path, Charset)` là overload Java 10; trong ví dụ nó đọc token đơn giản, không cần giả định encoding mặc định.
- `finally` xóa file tạm kể cả khi quá trình kiểm thử phát sinh ngoại lệ; một lỗi xóa file vẫn là lỗi I/O thực tế có thể được báo lên caller.
- `PrintWriter(File, Charset)` và những overload file khác có thể ném `IOException` khi không mở/tạo được file. Vì vậy `main` trong demo cho phép `throws Exception` để giữ ngắn mã học tập, nhưng ứng dụng thật nên bắt/lan truyền ngoại lệ theo thiết kế API.

Nếu cần một file được cập nhật an toàn, có kiểm soát atomic replacement hoặc xử lý nhiều tiến trình, riêng việc chỉ định charset là **chưa đủ**. Hãy thiết kế vòng đời file, transaction và chế độ ghi riêng.

## 12. Chương trình hoàn chỉnh 3 — giải mã nghiêm ngặt thay vì âm thầm thay thế

Một bộ đệm có thể chứa byte không hợp lệ theo UTF-8. `ByteArrayOutputStream.toString(Charset)` dùng quy tắc thay thế ký tự lỗi. Nếu yêu cầu là **từ chối dữ liệu không hợp lệ**, bạn cần `CharsetDecoder` và `CodingErrorAction.REPORT`.

Tệp **`CharsetFailureDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class CharsetFailureDemo {
    public static void main(String[] args) {
        byte[] malformed = {(byte) 0xC3, (byte) 0x28};
        var buffer = new ByteArrayOutputStream();
        buffer.write(malformed, 0, malformed.length);

        String decoded = buffer.toString(StandardCharsets.UTF_8);
        System.out.println("replacementUsed="
                + decoded.contains("\uFFFD"));

        boolean strictRejected = false;
        try {
            StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(malformed));
        } catch (CharacterCodingException expected) {
            strictRejected = true;
        }
        System.out.println("strictRejected=" + strictRejected);

        byte[] correctBytes = "Café".getBytes(StandardCharsets.UTF_8);
        String wrong = new String(
                correctBytes, StandardCharsets.ISO_8859_1);
        System.out.println("wrongCharsetMatches="
                + "Café".equals(wrong));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 10 -encoding UTF-8 CharsetFailureDemo.java
java CharsetFailureDemo
```

**Stdout:**

```text
replacementUsed=true
strictRejected=true
wrongCharsetMatches=false
```

Giải thích:

1. Cặp byte `0xC3, 0x28` **không phải một chuỗi UTF-8 hợp lệ**. `ByteArrayOutputStream.toString(StandardCharsets.UTF_8)` thay phần lỗi bằng ký tự thay thế U+FFFD (`\uFFFD`), nên `replacementUsed=true`.
2. `StandardCharsets.UTF_8.newDecoder()` tạo decoder có thể được cấu hình. Hai lời gọi `onMalformedInput(REPORT)` và `onUnmappableCharacter(REPORT)` yêu cầu báo lỗi thay vì thay thế âm thầm. `decode(...)` vì thế ném ngoại lệ thuộc `CharacterCodingException`.
3. Byte của `"Café"` được tạo đúng bằng UTF-8, nhưng giải mã bằng ISO-8859-1 tạo một chuỗi khác, dẫn đến `wrongCharsetMatches=false`. Đây là **mismatch encoding**, không nhất thiết là malformed input theo charset sai.
4. `CharsetDecoder` là API đã có từ trước Java 10; dùng nó ở đây vì nó vẫn là công cụ chuẩn khi yêu cầu kiểm soát chất lượng dữ liệu chặt hơn overload tiện dụng `toString(Charset)`.

### 12.1. Đừng nhầm “decoder không ném” với “file có encoding đúng”

Một dãy byte có thể được chấp nhận trong một charset nhưng không mang đúng ý nghĩa ban đầu. Vì thế **kết quả không có ngoại lệ chưa đủ để xác định charset của nguồn**. Hãy lấy charset từ hợp đồng file/protocol (header, metadata, chuẩn định dạng) hoặc bước phát hiện đáng tin được thiết kế riêng.

Nếu dữ liệu JSON hoặc giao thức có encoding được chuẩn hóa, tuân theo **đặc tả của định dạng đó**. Không tự thay encoding dựa vào `Charset.defaultCharset()` của máy chạy.

## 13. Default charset trên các phiên bản JDK hiện đại

Từ **JDK 18**, JEP 400 quy định **UTF-8 là default charset theo mặc định** cho các Java SE API chuẩn, với những tùy chọn tương thích và ngoại lệ cụ thể của môi trường. Trên các JDK 17 trở xuống, default charset có thể phụ thuộc hệ điều hành hoặc thiết lập máy. Vì vậy:

- `new PrintWriter(output)` và `new Scanner(input)` có thể dựa vào default charset nếu không truyền charset.
- `new PrintWriter(output, true, StandardCharsets.UTF_8)` và `new Scanner(input, StandardCharsets.UTF_8)` nói rõ định dạng mong muốn, không phụ thuộc cách cấu hình default.
- Dù nhiều JDK hiện đại mặc định UTF-8, **khai báo charset tường minh vẫn là thói quen tốt** khi đọc/ghi dữ liệu phải được trao đổi giữa hệ thống, lưu trữ lâu dài hoặc có giao thức cụ thể.
- Charset sử dụng cho `System.out` và các stream console có thể liên quan tới cấu hình console/launch riêng; đừng suy rằng thay đổi default charset sẽ tự động sửa mọi lỗi hiển thị terminal.

Cũng không nên coi file cũ mặc nhiên được mã hóa UTF-8 chỉ vì JDK mới mặc định UTF-8. Chọn charset theo **nguồn dữ liệu** chứ không chỉ theo phiên bản JDK.

### 13.1. Cờ biên dịch nguồn khác với charset lúc chạy

`javac -encoding UTF-8` chỉ định **cách javac đọc file .java**. `StandardCharsets.UTF_8` chỉ định **cách chương trình chuyển byte và ký tự khi chạy**. Biến môi trường và cấu hình console là vấn đề khác nữa.

Ví dụ trong một dự án Maven/Gradle, mã nguồn được lưu UTF-8 nhưng API I/O lại dùng mặc định của môi trường sẽ vẫn có thể gặp vấn đề nếu dữ liệu ngoài có encoding khác. Ngược lại, I/O dùng UTF-8 nhưng mã nguồn được đọc bằng encoding sai có thể làm hỏng các string literal chứa dấu ngay từ lúc biên dịch.

## 14. Xử lý lỗi và vòng đời tài nguyên

Các constructor nhận đối tượng `Charset` làm code rõ hơn nhưng không loại bỏ rủi ro I/O.

| Tình huống | Nguyên nhân/ngoại lệ hoặc dấu hiệu | Cách xử lý |
|---|---|---|
| Charset object là `null` | Nhiều constructor hoặc method sẽ ném `NullPointerException` | Không truyền null; dùng `StandardCharsets` hoặc validate cấu hình |
| Tên charset do người dùng nhập sai | `Charset.forName(...)` có thể ném `IllegalCharsetNameException` hoặc `UnsupportedCharsetException` | Validate cấu hình, cung cấp thông báo rõ |
| File không tồn tại/không thể tạo | Constructor nhận `File`/`Path` có thể ném ngoại lệ I/O | Kiểm tra quyền, đường dẫn và lan truyền lỗi đúng cách |
| PrintWriter ghi gặp I/O error | Các method `print` có thể không ném lỗi trực tiếp | Gọi `checkError()` ở điểm cần xác nhận |
| PrintStream ghi gặp I/O error | Có cơ chế trạng thái lỗi `checkError()` | Xem xét và phản hồi lỗi ghi |
| Scanner đọc nguồn lỗi | `Scanner.ioException()` có thể cung cấp lỗi I/O cuối | Kiểm tra nếu độ tin cậy I/O quan trọng |
| Dữ liệu UTF-8 malformed | Overload tiện dụng có thể thay ký tự lỗi | Dùng `CharsetDecoder` với `REPORT` nếu phải từ chối |
| Reader/writer không được đóng | Dữ liệu còn trong buffer hoặc rò rỉ tài nguyên | `try-with-resources`/`flush` đúng thời điểm |
| Đóng wrapper khi stream bên dưới còn dùng | Nhiều wrapper đóng luôn nguồn dưới | Xác định rõ quyền sở hữu và vòng đời stream |
| Đọc file bằng charset khác lúc ghi | Mojibake hoặc nội dung sai | Truyền charset theo hợp đồng cả hai chiều |

### 14.1. Lựa chọn API tùy yêu cầu báo lỗi

`PrintWriter`/`PrintStream` thuận tiện cho xuất text/format, nhưng khi tính đúng đắn phụ thuộc vào việc **mọi lỗi ghi phải được phát hiện và xử lý rõ**, nhiều ứng dụng chọn `BufferedWriter`/`Files.newBufferedWriter` (kèm Charset), vì các phương thức ghi có thể báo `IOException` trực tiếp.

**Không coi đây là API lỗi thời:** `PrintWriter` và `PrintStream` vẫn còn dùng tốt. Điều cần quan tâm là **hợp đồng lỗi và ownership** của ứng dụng.

### 14.2. Unicode BOM và newline không phải chính Charset tự quyết định đầy đủ

- UTF-8 không đòi hỏi byte-order mark (BOM). Không tự giả định mọi bộ ghi UTF-8 phải xuất BOM.
- Một số file bên ngoài có thể có BOM; cách ứng dụng nhận diện/bỏ BOM cần được định nghĩa phù hợp định dạng.
- `println` có thể sinh line separator phụ thuộc môi trường. Nếu giao thức yêu cầu `\n` đúng theo byte, hãy viết newline đúng quy định của giao thức, thay vì dựa vào newline mặc định của thiết bị.
- Charset chỉ giải quyết **mã hóa ký tự**, không tự bảo đảm chuẩn hóa Unicode, CSV escaping, delimiter hay line ending của file.

## 15. Khi nào dùng API Java 10, khi nào dùng API hiện đại khác?

| Nhu cầu | Lựa chọn gợi ý | Mốc phiên bản |
|---|---|---|
| In text có charset vào một `OutputStream` | `PrintWriter(out, autoFlush, charset)` | Java 10 |
| In text và tương tác API PrintStream | `PrintStream(out, autoFlush, charset)` | Java 10 |
| Tokenize text từ file/stream theo charset | `Scanner(fileOrStream, charset)` | Java 10 |
| Vừa format theo Locale vừa encode text | `Formatter(out, charset, locale)` | Java 10 |
| Decode byte buffer sang String | `ByteArrayOutputStream.toString(charset)` | Java 10 |
| Đọc dòng text với decoder explicit | `InputStreamReader(in, charset)` + `BufferedReader` | Đã có trước Java 10 |
| Đọc/ghi text file bằng NIO reader/writer | `Files.newBufferedReader/path..., charset` | Đã có trước Java 10 |
| Đọc toàn bộ file text thành String | `Files.readString(path, charset)` | Java 11 |
| Ghi toàn bộ String vào file | `Files.writeString(path, text, charset, ...)` | Java 11 |
| Cần phát hiện byte UTF-8 hỏng, không cho phép replacement | `CharsetDecoder` cấu hình `CodingErrorAction.REPORT` | Đã có trước Java 10 |

Bài học là về **truyền Charset object** chứ không bắt buộc phải dùng class mới nhất. Chọn API theo cách đọc/ghi mà ứng dụng thật cần: dòng hay token, file nhỏ hay luồng lớn, có format hay không, cần kiểm soát lỗi hoặc vòng đời thế nào.

## 16. Kiểm thử đúng, tránh phụ thuộc máy

### 16.1. Kiểm thử round-trip

Một test round-trip tốt cần:

1. Văn bản có ít nhất một ký tự ngoài ASCII, ví dụ `"Hà Nội, Huế"`.
2. Mã hóa bằng `StandardCharsets.UTF_8`, không dùng default charset.
3. Giải mã bằng **cùng đối tượng Charset**.
4. So sánh bằng `String.equals` (hoặc test assertion tương đương).
5. Kiểm thử cả writer lẫn reader thực tế nếu đường đi sản phẩm đi qua nhiều lớp wrapper.

Chỉ dùng chữ `"ABC"` không phải test đủ tốt để phát hiện chọn sai UTF-8/ISO-8859-1 vì các byte ASCII giống nhau trong nhiều charset.

### 16.2. Kiểm thử mismatch

Cố ý dùng charset không khớp và chứng minh `equals` trả false, **không** in ra các ký tự lỗi rồi assert một chuỗi mojibake cụ thể nếu điều đó làm test phụ thuộc môi trường hiển thị.

Bài `CharsetFailureDemo` ở trên thể hiện pattern ổn định: test boolean `wrongCharsetMatches=false`, không phụ thuộc font/terminal.

### 16.3. Kiểm thử dữ liệu hỏng

Dùng một dãy byte UTF-8 malformed và kiểm tra:
- Overload decode tiện dụng có thể dùng replacement;
- `CharsetDecoder` với `REPORT` ném `CharacterCodingException`.

Nên kiểm tra **loại lỗi hoặc hành vi**, không dựa vào chuỗi message mặc định của exception.

### 16.4. Kiểm thử file tạm và cleanup

- Tạo file bằng `Files.createTempFile`, không hardcode một vị trí có thể không tồn tại.
- Đóng writer trước khi reader mở file để tránh vấn đề dữ liệu còn trong buffer.
- Xóa file trong `finally`.
- Không dùng một file chung giữa nhiều test chạy song song nếu không có cơ chế phối hợp.

### 16.5. Kiểm thử định dạng Locale độc lập charset

Đặt `Locale.US` trong ví dụ Formatter để output `12.50` ổn định. Dùng UTF-8 cho cả encode/decode. Nếu ứng dụng dùng `Locale` khác, test phải so sánh định dạng đúng theo locale đã chỉ định, không kết luận khác biệt dấu thập phân là lỗi charset.

## 17. Những hiểu nhầm thường gặp

| Hiểu nhầm | Điều đúng |
|---|---|
| “Charset là kiểu dữ liệu lưu văn bản.” | `Charset` định nghĩa cách mã hóa/giải mã giữa ký tự và byte. |
| “Đọc byte luôn tự biết encoding.” | Không. Phải chọn đúng charset theo hợp đồng dữ liệu. |
| “Java 10 mới có `InputStreamReader(in, Charset)`.” | Không. Constructor đó có từ Java 1.4. |
| “Java 10 mới có `Files.readString`.” | Không. `Files.readString` là Java 11. |
| “PrintWriter Java 10 có Charset, vậy không cần flush/close.” | Sai. Buffer và vòng đời tài nguyên vẫn cần quản lý. |
| “PrintWriter.print sẽ luôn tự flush nếu autoFlush=true.” | Không; `PrintWriter` auto-flush trên `println`, `printf` hoặc `format`. |
| “Charset và Locale đều có chức năng định dạng số.” | Sai. Charset encode/decode byte; Locale ảnh hưởng biểu diễn dữ liệu theo vùng/ngôn ngữ. |
| “`ByteArrayOutputStream.toString(Charset)` luôn từ chối byte lỗi.” | Không. Nó dùng replacement khi giải mã malformed/unmappable; dùng decoder `REPORT` nếu cần từ chối. |
| “Không có exception nghĩa là đúng encoding.” | Không. Giải mã sai charset vẫn có thể trả text nhưng sai nội dung. |
| “JDK mới mặc định UTF-8 nên bỏ được Charset trong mọi API.” | Không nên; dữ liệu trao đổi hoặc file cũ phải dùng encoding đúng và tường minh. |
| “`javac -encoding UTF-8` điều khiển luôn charset của file ứng dụng ghi ra.” | Sai. Cờ này chỉ điều khiển cách `javac` đọc **mã nguồn**. |
| “PrintStream.write(byte[]) sẽ tự encode lại UTF-8.” | Không. Đây là thao tác ghi raw bytes; charset được dùng cho các operation xuất ký tự. |
| “Đóng Scanner không ảnh hưởng InputStream bên dưới.” | Có thể đóng luôn nguồn; cần quản lý ownership. |
| “UTF-8 luôn dài đúng bằng `String.length()` byte.” | Sai. Ký tự ngoài ASCII có thể dùng nhiều byte; Java String sử dụng UTF-16 code units. |
| “Dùng `Charset.forName` được bất kỳ tên nào.” | Không. Tên sai hoặc không được hỗ trợ có thể gây ngoại lệ. |

## 18. Câu hỏi ôn tập có đáp án

**Câu 1.** Sự bổ sung chính về `Charset` trong I/O của Java 10 là gì?

**Đáp án:** Nhiều constructor và một số method mới nhận trực tiếp `Charset`, nổi bật tại `PrintWriter`, `PrintStream`, `Scanner`, `Formatter` và `ByteArrayOutputStream.toString(Charset)`. Điều đó không có nghĩa `Charset` hay toàn bộ hoạt động I/O với charset đều mới ở Java 10.

**Câu 2.** Nên dùng `"UTF-8"` hay `StandardCharsets.UTF_8` khi charset đã được quy định là UTF-8?

**Đáp án:** `StandardCharsets.UTF_8` thường rõ hơn vì là đối tượng charset chuẩn được Java bảo đảm hỗ trợ, không phụ thuộc vào cách gõ chuỗi tên encoding.

**Câu 3.** Vì sao `new PrintWriter(stream, true, StandardCharsets.UTF_8)` có thể cần `flush()` sau `print(...)`?

**Đáp án:** `autoFlush=true` trên `PrintWriter` không tự flush mọi lời gọi `print`. Có thể gọi `flush` hoặc đóng writer đúng cách khi cần dữ liệu đã được ghi ra underlying output.

**Câu 4.** `Scanner(input, utf8)` có tự dùng `Locale.US` không?

**Đáp án:** Không. Charset quyết định giải mã byte; locale ảnh hưởng xử lý định dạng một số token. Muốn locale cụ thể thì đặt `useLocale(...)`.

**Câu 5.** `Formatter(out, UTF8, Locale.US)` nhận charset để làm gì? Locale để làm gì?

**Đáp án:** Charset mã hóa văn bản thành byte; locale ảnh hưởng biểu diễn số, ngày và những quy tắc địa phương khi format.

**Câu 6.** `ByteArrayOutputStream.toString(StandardCharsets.UTF_8)` có ném `CharacterCodingException` khi dữ liệu UTF-8 sai không?

**Đáp án:** Không theo hợp đồng overload tiện dụng này: malformed/unmappable được thay bằng replacement string. Muốn từ chối, dùng `CharsetDecoder` với `CodingErrorAction.REPORT`.

**Câu 7.** Vì sao decode byte UTF-8 bằng ISO-8859-1 có thể không báo lỗi nhưng vẫn sai?

**Đáp án:** Byte được diễn giải theo bảng ký tự khác, tạo ra ký tự không tương ứng văn bản ban đầu. Không có exception không đồng nghĩa encoding khớp.

**Câu 8.** `Files.readString(Path, Charset)` có sẵn nếu target Java 10 không?

**Đáp án:** Không, nó có từ Java 11. Với target Java 10, có thể dùng `Scanner(Path,Charset)` hoặc một Reader phù hợp.

**Câu 9.** Khi nào cần `CharsetDecoder` thay vì chỉ `new String(bytes, utf8)`?

**Đáp án:** Khi dữ liệu hỏng phải bị phát hiện/từ chối, hoặc ứng dụng cần chính sách cụ thể cho malformed/unmappable input.

**Câu 10.** Tại sao demo sử dụng `-encoding UTF-8` khi biên dịch?

**Đáp án:** Để `javac` đọc chính xác các literal có dấu trong file nguồn .java. Đây là encoding nguồn, khác với encoding I/O của chương trình lúc chạy.

**Câu 11.** Trên JDK 18+, có nên mặc định suy rằng mọi file bên ngoài là UTF-8 không?

**Đáp án:** Không. Default charset của JDK có chính sách hiện đại hơn, nhưng file/giao thức bên ngoài phải được giải mã theo định dạng thực tế.

**Câu 12.** `PrintWriter.checkError()` nhằm xử lý điều gì?

**Đáp án:** Nó cho biết trạng thái lỗi I/O của PrintWriter vì các phương thức in thường không trực tiếp ném `IOException`. Nó không thay thế decoder/encoder nghiêm ngặt để kiểm tra tất cả vấn đề về ký tự.

## 19. Tài liệu chính thức

- [Oracle Java SE 10 — Uses of Charset](https://docs.oracle.com/javase/10/docs/api/java/nio/charset/class-use/Charset.html): liệt kê constructor và method nhận `Charset` trong `java.io` và `java.util`.
- [Oracle Java SE 10 — PrintWriter](https://docs.oracle.com/javase/10/docs/api/java/io/PrintWriter.html): constructor nhận `Charset`, `Since: 10` và `checkError()`.
- [Oracle Java SE 10 — PrintStream](https://docs.oracle.com/javase/10/docs/api/java/io/PrintStream.html): constructor mới nhận `Charset` và chính sách in ký tự.
- [Oracle Java SE 10 — Scanner](https://docs.oracle.com/javase/10/docs/api/java/util/Scanner.html): các overload nhận `Charset` khi đọc byte từ File, InputStream, Path, Channel.
- [Oracle Java SE 10 — Formatter](https://docs.oracle.com/javase/10/docs/api/java/util/Formatter.html): constructor nhận `Charset` cùng `Locale`.
- [Oracle Java SE 10 — ByteArrayOutputStream](https://docs.oracle.com/javase/10/docs/api/java/io/ByteArrayOutputStream.html): `toString(Charset)` (Since: 10) và replacement cho dữ liệu lỗi.
- [Oracle Java SE 21 — Charset](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/Charset.html): cơ chế encoding/decoding vẫn áp dụng trên Java hiện đại.
- [Oracle Java SE 21 — StandardCharsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset chuẩn luôn được hỗ trợ.
- [Oracle Java SE 21 — CharsetDecoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html): xử lý malformed/unmappable bằng `CodingErrorAction.REPORT`.
- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): mốc thay đổi default charset từ JDK 18; không thay thế việc chỉ định charset rõ khi dữ liệu bên ngoài có hợp đồng riêng.

**Ghi nhớ:** `Charset` là **quy tắc chuyển đổi ký tự ↔ byte**. Java 10 giúp truyền `Charset` trực tiếp vào nhiều constructor của `PrintWriter`, `PrintStream`, `Scanner`, `Formatter` và vào `ByteArrayOutputStream.toString(Charset)`. Dùng `StandardCharsets.UTF_8` khi đúng định dạng dữ liệu, ghi và đọc cùng charset, quản lý flush/close/lỗi I/O, và dùng `CharsetDecoder` có `REPORT` khi cần từ chối văn bản được mã hóa sai.