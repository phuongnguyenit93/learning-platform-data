# Thứ tự ghép stream, buffer, charset và định dạng trong Java I/O

## 1. Tư duy theo luồng dữ liệu: byte → ký tự → cấu trúc

Trong Java I/O, nhiều lớp có thể bọc (**wrap**) cùng một nguồn/đích để mỗi lớp đảm nhận một chức năng. Với dữ liệu văn bản, bốn mối quan tâm cần phân biệt:

1. **Stream byte:** kết nối nguồn/đích vật lý hoặc logic, chẳng hạn `FileInputStream`, `FileOutputStream`, `Files.newInputStream`, `ByteArrayInputStream`.
2. **Buffer:** giảm số lần gọi tầng bên dưới bằng cách đọc/ghi theo khối, chẳng hạn `BufferedInputStream`, `BufferedOutputStream`, `BufferedReader`, `BufferedWriter`.
3. **Charset:** chuyển giữa **byte** và **ký tự**, chẳng hạn `InputStreamReader` và `OutputStreamWriter` với `StandardCharsets.UTF_8`.
4. **Định dạng (format):** quy ước biến các giá trị và bản ghi thành văn bản hoặc dữ liệu nhị phân: một dòng ứng với một bản ghi, CSV, JSON, hoặc `DataOutputStream` với một giao thức nhị phân cụ thể.

**Quy tắc chính:** Ghép lớp theo **kiểu dữ liệu mà mỗi lớp nhận và trả về**, rồi kiểm tra quy ước định dạng của tệp/giao thức. Không hoán đổi tùy ý các lớp chỉ vì chúng đều có chữ “stream” hoặc “buffer” trong tên.

Sơ đồ đọc văn bản đơn giản:

```text
Nguồn byte (file/network)
    ↓  byte
[BufferedInputStream]       (tùy chọn: buffer byte)
    ↓  byte
InputStreamReader(UTF-8)     (giải mã byte → char)
    ↓  char
BufferedReader              (tùy chọn: buffer char, readLine)
    ↓  String
Bộ phân tích định dạng       (parse từng dòng, CSV, JSON...)
    ↓
Giá trị nghiệp vụ
```

Sơ đồ ghi văn bản là chiều ngược lại về **ngữ nghĩa xử lý dữ liệu**:

```text
Giá trị nghiệp vụ
    ↓
Bộ tạo định dạng             (CSV, JSON, các dòng văn bản...)
    ↓  String / char
BufferedWriter               (tùy chọn: buffer char)
    ↓  char
OutputStreamWriter(UTF-8)     (mã hóa char → byte)
    ↓  byte
[BufferedOutputStream]       (tùy chọn: buffer byte)
    ↓  byte
Đích byte (file/network)
```

Dấu ngoặc vuông nghĩa là lớp tùy chọn. Sơ đồ diễn tả **chiều dữ liệu chảy**; mã Java thực tế thường được tạo từ **lớp bên trong (nguồn/đích) ra lớp bên ngoài (API ứng dụng dùng)**.

## 2. Ghép lớp theo kiểu Java

| Nhóm | Đầu vào/đầu ra của lớp | Vai trò |
| --- | --- | --- |
| `InputStream` / `OutputStream` | `byte`, `byte[]` | Nền tảng I/O byte |
| `BufferedInputStream` / `BufferedOutputStream` | `InputStream` / `OutputStream` | Bọc luồng byte và thêm buffer byte |
| `Reader` / `Writer` | `char`, `char[]`, `String` | Nền tảng I/O ký tự |
| `InputStreamReader` | Bọc một `InputStream` | Giải mã byte thành ký tự bằng charset |
| `OutputStreamWriter` | Bọc một `OutputStream` | Mã hóa ký tự thành byte bằng charset |
| `BufferedReader` / `BufferedWriter` | Bọc `Reader` / `Writer` | Thêm buffer ký tự, `readLine()` / `newLine()` |
| `PrintWriter` | Bọc `Writer` hoặc `OutputStream` | `print`, `println`, `printf` để tạo văn bản trình bày |
| `DataInputStream` / `DataOutputStream` | Bọc luồng byte | Đọc/ghi kiểu nguyên thủy theo **định dạng nhị phân** đã quy định |

Ví dụ đúng về mặt kiểu:

```java
// input là InputStream đã mở:
Reader decoder = new InputStreamReader(input, StandardCharsets.UTF_8);
BufferedReader lines = new BufferedReader(decoder);

// output là OutputStream đã mở:
Writer encoder = new OutputStreamWriter(output, StandardCharsets.UTF_8);
BufferedWriter text = new BufferedWriter(encoder);
```

Đoạn trên **chỉ minh họa cách ghép lớp**; `input`/`output` phải được khai báo và mở ở ngữ cảnh bao quanh. Khi dùng thực tế nên quản lý đóng luồng bằng `try-with-resources`, như ví dụ đầy đủ bên dưới.

Ví dụ sai về kiểu hoặc ý nghĩa:

- `new BufferedReader(input)` **không biên dịch**, vì `BufferedReader` yêu cầu `Reader` chứ không nhận trực tiếp `InputStream`. Cần một `InputStreamReader` làm cầu nối.
- `new BufferedInputStream(reader)` cũng không biên dịch, vì buffer byte không nhận `Reader`.
- Gọi `readLine()` trên `InputStream` không có nghĩa; đây là API xử lý ký tự ở `BufferedReader`.
- Lấy byte UTF-8 rồi tự ép từng byte thành `char` không phải giải mã UTF-8; ký tự Unicode có thể cần nhiều byte.

## 3. Ghép lớp đọc đúng thứ tự

Từ một nguồn byte:

```java
BufferedReader reader = new BufferedReader(
        new InputStreamReader(
                new BufferedInputStream(input),
                StandardCharsets.UTF_8));
```

Luồng xử lý thực tế:

1. `BufferedInputStream` nhận byte từ `input` theo khối.
2. `InputStreamReader` **giải mã UTF-8**, xử lý đúng cả ký tự được mã hóa thành nhiều byte nằm qua ranh giới giữa các lần đọc.
3. `BufferedReader` giữ ký tự trong buffer và cho phép `readLine()`.
4. Ứng dụng nhận `String` để xử lý theo định dạng đã thống nhất.

**Không phải lúc nào cũng cần cả hai buffer.** `InputStreamReader`/decoder và các lớp I/O có cơ chế quản lý dữ liệu riêng; `BufferedReader` thường đã đáp ứng nhu cầu đọc theo dòng. Bổ sung `BufferedInputStream` chỉ vì “càng nhiều buffer càng nhanh” có thể tăng bộ nhớ, độ phức tạp và không cải thiện tốc độ. Cần chọn buffer dựa trên cách truy cập, nguồn I/O, đo đạc thực tế.

Nếu tệp không chứa văn bản mà chứa dữ liệu nhị phân, không dùng `Reader` chỉ để tận dụng `readLine()`. Chọn API byte hoặc parser nhị phân tương ứng.

## 4. Ghép lớp ghi đúng thứ tự

Từ một đích byte:

```java
BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(
                new BufferedOutputStream(output),
                StandardCharsets.UTF_8));
```

Khi ứng dụng gọi `writer.write(...)`:

1. `BufferedWriter` có thể giữ các ký tự trong bộ đệm.
2. `OutputStreamWriter` chuyển ký tự thành byte theo UTF-8.
3. `BufferedOutputStream` có thể giữ các byte trong bộ đệm.
4. `output` ghi byte vào đích khi dữ liệu được đẩy xuống.

Lớp nằm ngoài cùng quyết định giao diện ứng dụng sử dụng: `write(String)`, `newLine()` ở `BufferedWriter`. Ứng dụng không cần tự tính từng byte UTF-8. Với protocol cần UTF-8, charset phải được chọn **cả phía ghi lẫn phía đọc**; buffer không có khả năng sửa lỗi dùng sai charset.

Để ghi một tài liệu nhỏ hoặc một tệp thông thường, biến thể **đơn giản hơn** cũng hợp lý:

```java
BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(output, StandardCharsets.UTF_8));
```

Hoặc khi thao tác với file bằng `Path`:

```java
BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8);
BufferedWriter writer = Files.newBufferedWriter(path, StandardCharsets.UTF_8);
```

Các dòng này là **đoạn mã minh họa**, cần khai báo `path`, import `java.nio.file.Files`, `java.nio.file.Path` và xử lý `IOException`. `Files.newBufferedWriter` mặc định có thể **tạo hoặc ghi đè nội dung tệp**; không chạy tùy tiện trên tệp cần giữ nguyên. Các API `Files` ở đây giúp tránh phải ghép thủ công khi không cần kiểm soát lớp stream byte ở tầng dưới.

## 5. Ví dụ Java 17+ chạy được: buffer byte, charset và định dạng dòng

Chương trình dùng mảng byte trong bộ nhớ để tránh đụng vào dữ liệu thật. Tạo file **`LayeredTextDemo.java`**:

```java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public class LayeredTextDemo {
    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream sink = new ByteArrayOutputStream();

        try (BufferedWriter writer = new BufferedWriter(
                new OutputStreamWriter(
                        new BufferedOutputStream(sink),
                        StandardCharsets.UTF_8))) {
            writer.write("Tên,điểm");
            writer.newLine();
            writer.write(String.format(Locale.ROOT, "%s,%.2f", "An", 7.5));
            writer.newLine();
            writer.write(String.format(Locale.ROOT, "%s,%.2f", "Bình", 8.0));
            writer.newLine();
        }

        byte[] bytes = sink.toByteArray();

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        new BufferedInputStream(new ByteArrayInputStream(bytes)),
                        StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                System.out.println("Dòng: " + line);
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 LayeredTextDemo.java
java LayeredTextDemo
```

Đầu ra:

```text
Dòng: Tên,điểm
Dòng: An,7.50
Dòng: Bình,8.00
```

Điểm cần quan sát:

- Giá trị `7.5`/`8.0` thành `7.50`/`8.00` ở **bước định dạng** `String.format(Locale.ROOT, "%.2f", ...)`. `Locale.ROOT` giúp dấu thập phân là dấu chấm; charset không tự chọn dấu thập phân.
- `StandardCharsets.UTF_8` quyết định **byte của chữ có dấu** như `Tên`, `điểm` và `Bình`, nhưng không quyết định tên cột hay quy ước dấu phẩy.
- `writer.newLine()` tạo dấu hết dòng theo nền tảng. `reader.readLine()` nhận diện các dạng kết thúc dòng quen thuộc và trả nội dung không kèm ký tự kết thúc dòng, vì vậy đầu ra console ổn định.
- `try-with-resources` đóng `BufferedWriter` ngoài cùng, đồng thời đẩy dữ liệu qua `OutputStreamWriter` và `BufferedOutputStream` xuống `sink` trước khi gọi `toByteArray()`. Nếu lấy bytes quá sớm, phần còn chờ trong buffer có thể chưa xuất hiện.
- `ByteArrayOutputStream` hỗ trợ lấy bản sao nội dung đã ghi ngay cả sau khi wrapper phía trên đóng nó.

Mã dùng cú pháp đơn giản giống CSV để minh họa **thứ tự lớp**. Đây chưa phải serializer/parser CSV hoàn chỉnh: nếu giá trị chứa dấu phẩy, dấu ngoặc kép hoặc xuống dòng, phải tuân theo quy tắc escaping/quoting của định dạng CSV, thường nên dùng thư viện xử lý CSV tương ứng. `line.split(",")` đơn giản không đủ cho các trường hợp đó.

## 6. “Định dạng” nằm ở đâu trong chuỗi?

Chọn **định dạng** trước khi quyết định gọi API nào để encode hoặc decode.

### Văn bản có cấu trúc

Định dạng quyết định **cú pháp bản ghi và giá trị**:

- CSV: cách phân tách trường, quoting dấu phẩy, escaping dấu ngoặc kép, dòng và header.
- JSON: đối tượng, mảng, chuỗi, escape và giá trị boolean/number theo đặc tả JSON.
- Dữ liệu ghi từng dòng: mỗi dòng là một record nếu ứng dụng xác định như vậy; không tự suy diễn mọi file văn bản đều có cấu trúc này.
- Log: timestamp, level, thông điệp, quy ước xuống dòng; cần chọn cách định dạng ngày giờ và số độc lập với charset.

Trong các trường hợp này, **serializer/parser** chạy ở tầng ký tự hoặc byte theo thư viện định dạng, còn **charset** đảm nhận phần biến đổi giữa ký tự và byte. Chẳng hạn JSON trên một giao thức có charset UTF-8: serializer tạo byte UTF-8 (hoặc ghi ký tự qua `Writer` phù hợp); không thể đổi parser JSON thành `BufferedReader` bằng cách thêm buffer.

### `PrintWriter` và `printf`

`PrintWriter` tiện cho định dạng trình bày với `print`, `println` và `printf`. Ví dụ cấu trúc kiểu thường thấy:

```java
PrintWriter out = new PrintWriter(
        new BufferedWriter(
                new OutputStreamWriter(output, StandardCharsets.UTF_8)));

out.printf(Locale.ROOT, "total=%.2f%n", 12.5);
out.flush();
```

Đây là **mã minh họa**, với `output` là một `OutputStream` đã mở và do nơi gọi chịu trách nhiệm quản lý vòng đời. `printf` xử lý **cách biểu diễn số và chuỗi**, `OutputStreamWriter` xử lý **charset**, `BufferedWriter` xử lý **buffer**. `PrintWriter` thường **không ném `IOException` từ các thao tác print/write/printf** mà ghi nhận trạng thái lỗi; khi độ tin cậy đầu ra quan trọng phải dùng `checkError()` hoặc chọn `Writer`/API có truyền lỗi trực tiếp. Nếu dùng `try-with-resources` với `PrintWriter` sở hữu luồng, đóng lớp ngoài cùng một lần.

`%n` là dấu xuống dòng theo nền tảng, khác với `\n` cố định. Với định dạng file có quy định chuẩn cụ thể về CRLF/LF, hãy ghi rõ dấu xuống dòng tương ứng và không phụ thuộc hệ điều hành.

### Dữ liệu nhị phân có định dạng riêng

Một định dạng nhị phân có thể quy định `int` 4 byte, `long` 8 byte, độ dài rồi đến byte dữ liệu, checksum, v.v. `DataOutputStream`/`DataInputStream` làm việc trực tiếp trên byte:

```java
DataOutputStream out = new DataOutputStream(
        new BufferedOutputStream(output));
out.writeInt(42);
out.writeUTF("Xin chào");
out.flush();
```

Đây là **mã minh họa** cần `output` đã mở, import `java.io.DataOutputStream`/`java.io.BufferedOutputStream` và quản lý đóng/ngoại lệ. Phía đọc tương ứng phải dùng `DataInputStream.readInt()` trước `readUTF()`, đúng **thứ tự trường dữ liệu** đã ghi. `writeUTF` sử dụng **modified UTF-8 của `DataOutputStream`**, khác UTF-8 chuẩn ở một số trường hợp (ví dụ ký tự NUL và surrogate); không thay nó bằng `new String(bytes, UTF_8)` hoặc `InputStreamReader(UTF_8)` nếu không tái hiện chính xác định dạng byte.

Ở đây **không có bước chuyển một tài liệu văn bản qua `OutputStreamWriter`**. Cố áp charset/`Reader` lên toàn bộ dãy byte của định dạng nhị phân có thể làm hỏng dữ liệu. Chọn nhánh text hoặc binary dựa trên đặc tả định dạng thực tế.

## 7. Nếu có nén, mã hóa hay biến đổi byte khác

Lớp biến đổi byte (chẳng hạn `GZIPInputStream`/`GZIPOutputStream`) xử lý **byte đã nén**, không thể nhận ký tự trực tiếp. Vì thế với văn bản UTF-8 được nén GZIP:

```text
GHI:  String → Writer tạo ký tự → UTF-8 bytes → GZIP bytes → đích
ĐỌC: nguồn GZIP bytes → giải nén → UTF-8 bytes → Reader → String
```

Ví dụ Java 17+ độc lập **`GzipTextPipelineDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

public class GzipTextPipelineDemo {
    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream destination = new ByteArrayOutputStream();

        try (BufferedWriter writer = new BufferedWriter(
                new OutputStreamWriter(
                        new GZIPOutputStream(destination),
                        StandardCharsets.UTF_8))) {
            writer.write("Café");
            writer.newLine();
        }

        byte[] compressed = destination.toByteArray();

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        new GZIPInputStream(
                                new ByteArrayInputStream(compressed)),
                        StandardCharsets.UTF_8))) {
            System.out.println(reader.readLine());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 GzipTextPipelineDemo.java
java GzipTextPipelineDemo
```

Đầu ra:

```text
Café
```

**Điểm quan trọng:** `GZIPOutputStream` cần `finish()` hoặc `close()` để ghi đầy đủ trailer/checksum của định dạng GZIP. Đóng `BufferedWriter` ngoài cùng làm đóng dây chuyền xuống GZIP, rồi mới lấy `destination.toByteArray()`. Nếu đảo thứ tự và cố đưa byte GZIP thẳng vào `InputStreamReader`, decoder UTF-8 sẽ đọc byte nén như văn bản và kết quả không còn đúng.

Với nén và mã hóa bảo mật cùng tồn tại, thứ tự lớp phải tuân **đặc tả giao thức**: ví dụ một giao thức có thể yêu cầu nén trước rồi mới mã hóa ở chiều ghi, và giải mã rồi mới giải nén ở chiều đọc. Không tự hoán đổi vì các phép biến đổi không nhất thiết giao hoán. Lớp buffer cũng cần bố trí ở vị trí phù hợp để không làm hỏng ranh giới thông điệp hay cơ chế flush của protocol.

## 8. Tốc độ, kích thước buffer và hành vi đọc trước

**Buffer byte** gom các lệnh đọc/ghi byte; **buffer ký tự** gom các thao tác đọc/ghi ký tự và cung cấp API tiện lợi như `readLine()`. Hai buffer có thể cùng tồn tại vì chúng xử lý dữ liệu ở hai phía của bộ chuyển charset, nhưng **không tự động có lợi** khi thêm cả hai.

Các tình huống thường gặp:

| Nhu cầu | Chuỗi lớp thường phù hợp |
| --- | --- |
| Đọc dòng UTF-8 từ file | `Files.newBufferedReader(path, UTF_8)` |
| Ghi dòng UTF-8 vào file | `Files.newBufferedWriter(path, UTF_8)` |
| Đọc block byte từ file | `BufferedInputStream(Files.newInputStream(path))` hoặc đọc block trực tiếp từ `InputStream` |
| Xử lý bản ghi văn bản từ socket | `BufferedReader(InputStreamReader(socket.getInputStream(), UTF_8))`, kèm framing giao thức |
| Xuất dữ liệu nhị phân nhiều trường | `DataOutputStream(BufferedOutputStream(output))` |
| Đọc văn bản đã nén GZIP | `BufferedReader(InputStreamReader(GZIPInputStream(input), UTF_8))` |

Hầu hết ví dụ Java ở trên dùng UTF-8 làm bộ mã tường minh. Khi giao thức/định dạng yêu cầu charset khác, phải áp dụng charset đúng theo đặc tả cả hai chiều.

**Đọc trước (read-ahead) có hậu quả:** `BufferedReader` và `InputStreamReader` có thể lấy từ luồng byte nhiều dữ liệu hơn lượng ký tự ứng dụng vừa yêu cầu. Nếu đọc vài dòng bằng wrapper rồi quay lại đọc trực tiếp `InputStream` gốc, vị trí đọc thực tế có thể đã vượt quá điểm tưởng tượng. Không trộn tùy ý các API truy cập chung một luồng; hãy để **một lớp ngoài cùng** quản lý quá trình đọc hoặc dùng framing/tầng parser được thiết kế cho việc chuyển giữa các loại dữ liệu.

Kích thước buffer lớn hơn không luôn nhanh hơn: còn phụ thuộc tốc độ mạng/đĩa, mẫu truy cập, số luồng chạy, áp lực bộ nhớ, chính sách flush và throughput/latency cần đạt. Chỉ tăng buffer khi có số liệu đo cụ thể.

## 9. `flush()`, `close()` và chủ sở hữu luồng

`BufferedWriter` có thể chưa đẩy dữ liệu xuống ngay khi gọi `write`. Ngay cả khi các byte đã qua `OutputStreamWriter`, `BufferedOutputStream` cũng có thể đang giữ lại. Vì thế:

- **`flush()` trên lớp ngoài cùng** yêu cầu đẩy dữ liệu trong chuỗi các wrapper xuống các tầng dưới theo hợp đồng của từng lớp.
- **`close()` lớp ngoài cùng** thường flush phần còn chờ rồi đóng các lớp bọc bên dưới; `try-with-resources` là cách thông thường để bảo đảm bước này.
- `flush()` **không đồng nghĩa dữ liệu đã được ghi bền vững lên thiết bị** (fsync) hay đầu nhận đã xử lý xong. Nếu cần durability phải dùng API và giao thức thích hợp, ví dụ `FileChannel.force(...)` trong tình huống tương ứng.
- Với stream biến đổi có định dạng kết thúc, như GZIP, **flush có thể chưa đủ để hoàn chỉnh output**; cần `finish()` hoặc `close()` theo hợp đồng của codec.

Ví dụ:

```java
try (BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(output, StandardCharsets.UTF_8))) {
    writer.write("OK");
    writer.flush(); // đẩy dữ liệu đang đệm; ví dụ có thể cần để phản hồi ngay
}
```

Đây là **mã minh họa**: `output` là luồng đã mở và được wrapper sở hữu. Không đóng một wrapper nếu bạn cần giữ luồng gốc tiếp tục mở trừ khi có thiết kế quản lý vòng đời riêng. Tránh đóng nhiều lần từng lớp mà không hiểu quan hệ sở hữu. Với `System.out`, không dùng `try-with-resources` tùy tiện vì đóng nó có thể ảnh hưởng toàn bộ ứng dụng.

Trong giao thức tương tác, writer được buffer cần `flush()` ở **ranh giới hoàn tất một thông điệp** nếu phía nhận đang chờ; ngược lại flush sau từng ký tự làm mất lợi ích bộ đệm. `BufferedReader.readLine()` cần ký tự kết thúc dòng hoặc EOF để hoàn tất dòng; nếu phía ghi chưa gửi newline/chưa flush, phía đọc có thể chờ mãi dù ứng dụng tưởng đã gọi `write`.

## 10. Những lỗi ghép lớp phổ biến

| Lỗi | Vì sao xảy ra | Cách làm đúng |
| --- | --- | --- |
| `BufferedReader(InputStream)` | Sai kiểu: reader cần `Reader` | Thêm `InputStreamReader(input, charset)` |
| Tạo `InputStreamReader` sau khi đã dùng `DataInputStream` đọc nhị phân tùy ý | Byte giao thức có thể không phải text | Dùng đúng parser/định dạng được quy định |
| Mã hóa String theo UTF-8, đọc theo charset mặc định | Charset hai phía không thống nhất | Truyền cùng charset tường minh |
| Tách byte UTF-8 bằng các lệnh ép `(char)byte` | Một ký tự có thể chứa nhiều byte | Để decoder xử lý ranh giới byte |
| Trộn đọc trực tiếp nguồn với `BufferedReader` đã bọc nguồn | Read-ahead làm vị trí nguồn khó đoán | Dùng một parser/chuỗi wrapper nhất quán |
| Đọc GZIP bytes trực tiếp bằng `InputStreamReader` | Chưa giải nén | `GZIPInputStream` phải giải nén trước khi decode |
| Gọi `toByteArray()` khi writer còn mở | Nội dung còn nằm trong buffer | Flush/close đúng thời điểm; với GZIP phải hoàn tất trailer |
| Mở cả buffer byte và buffer char không có lý do | Tăng overhead/bộ nhớ, đôi khi thêm latency | Chọn buffer theo nhu cầu và đo lường |
| `println` trong giao thức cần đúng LF | Xuống dòng phụ thuộc nền tảng | Ghi delimiter được giao thức quy định |
| Gọi `String.split(",")` để parse CSV bất kỳ | Không xử lý quoting/escape | Sử dụng parser đúng chuẩn CSV |
| Tin `PrintWriter` luôn báo `IOException` trực tiếp | PrintWriter có thể lưu cờ lỗi nội bộ | Kiểm tra `checkError()` hoặc chọn API báo lỗi |
| Gọi `flush` và tưởng đã lưu an toàn trên đĩa | Flush buffer ≠ durability của filesystem | Dùng cơ chế force/sync khi có yêu cầu bền vững |

## 11. Phương pháp thiết kế một pipeline I/O

Đối với một đường đọc hoặc ghi bất kỳ, lần lượt trả lời:

1. **Dữ liệu gốc là gì?** File, socket, byte mảng, bộ nhớ, hay luồng đã được API khác mở?
2. **Dữ liệu logic là text hay binary?** Với binary, chọn định dạng/protocol nhị phân; với text, xác định encoding thực.
3. **Có biến đổi byte không?** Nén, giải nén, mã hóa bảo mật, checksum... Sắp xếp đúng thứ tự được định dạng quy định.
4. **Ứng dụng cần thao tác ở mức nào?** Từng byte, dòng văn bản, record CSV, object JSON, số nguyên nhị phân?
5. **Buffer đặt ở đâu có giá trị?** Đọc dòng thì thường `BufferedReader`; byte block thì buffer byte hoặc đọc theo mảng. Tránh đệm lặp không cần thiết.
6. **Ai sở hữu nguồn/đích và khi nào hoàn tất?** Chọn nơi gọi `flush`, `finish` hoặc `close`; lưu ý writer có thể chưa đẩy dữ liệu.
7. **Đã kiểm thử hai chiều chưa?** Encode → decode, định dạng → parse, EOF, dữ liệu Unicode, ký tự không hợp lệ, thiếu dòng cuối, và trường hợp buffer nhỏ.

**Bài tự luyện:** Thiết kế pipeline ghi một file GZIP chứa CSV UTF-8, sau đó đọc lại từng dòng. Với phía ghi, đặt bộ tạo CSV ở lớp logic ngoài cùng, rồi writer UTF-8, sau đó `GZIPOutputStream` và file byte. Với phía đọc, đảo đường biến đổi: file byte → `GZIPInputStream` → `InputStreamReader(UTF_8)` → `BufferedReader` → parser CSV. Giải thích vì sao không đọc byte GZIP bằng `BufferedReader` ngay lập tức, và vì sao phải đóng gzip writer trước khi lấy bản nén hoàn chỉnh.

**Ghi nhớ:** Thứ tự đúng xuất phát từ **hợp đồng kiểu dữ liệu** và **đặc tả định dạng**: byte stream ở lõi I/O; buffer byte ở tầng byte khi cần; charset bridge chỉ ở ranh giới byte–char; buffer char và format/parser ở tầng văn bản; phép nén/mã hóa byte phải nằm ở đúng vị trí giao thức quy định.