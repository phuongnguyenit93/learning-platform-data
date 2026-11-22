# Quản lý đóng, flush và báo lỗi của từng lớp I/O khi xử lý Charset trong Java

> **Bối cảnh Java 10 — Charset trong I/O.** Tài liệu này trình bày cách quản lý vòng đời và lỗi của các lớp `InputStream`, `OutputStream`, `InputStreamReader`, `OutputStreamWriter`, `BufferedReader`, `BufferedWriter`, `PrintWriter` và các API `Files` khi chuyển **byte ↔ ký tự**. Các quy tắc còn áp dụng trên các JDK hiện đại được bảo trì; không yêu cầu sử dụng runtime Java 10 đã cũ. Bài phân biệt rõ trách nhiệm của từng lớp để tránh mất dữ liệu khi chưa flush/close, lỗi bị che giấu hoặc dùng sai charset.

## 1. Sau bài này, cần trả lời được điều gì?

1. Khi có các lớp I/O bọc nhau, **lớp nào sở hữu tài nguyên, lớp nào giải mã/mã hóa, lớp nào giữ bộ đệm và lớp nào nhận báo lỗi**?
2. `flush()` có ý nghĩa gì ở **Writer/BufferedWriter/OutputStreamWriter** và tại sao flush thành công chưa tự bảo đảm dữ liệu đã được lưu bền vững?
3. `close()` có tác dụng gì đối với lớp ngoài và các lớp bọc bên trong? Vì sao `try-with-resources` nên quản lý resource theo quyền sở hữu?
4. Vì sao lỗi **charset** có thể bị thay thế bằng ký tự/byte thay thế nếu dùng các constructor thông thường, và làm sao bật chế độ **REPORT** để phát hiện đầu vào sai?
5. Vì sao `PrintWriter` có thể báo lỗi qua `checkError()` thay vì ném `IOException`?
6. Tại sao một exception xảy ra trong `write`, `flush` hoặc `close` có thể khiến output đã được thay đổi một phần? Khi nào cần staging rồi publish?
7. Làm sao test các tình huống này không phụ thuộc OS, encoding console, thứ tự log hoặc thông điệp lỗi từ hệ thống?

## 2. Bản đồ một pipeline charset thường gặp

Trong chương trình Java, byte stream và character stream là các lớp trừu tượng khác nhau:

```text
ĐỌC (bytes → chars)

File / Socket / ByteArrayInputStream
          │  byte[]
          ▼
InputStream                    [tạo/đọc byte; close tài nguyên nguồn]
          │
          ▼
InputStreamReader              [CharsetDecoder: byte → char]
          │
          ▼
BufferedReader                 [đệm char, readLine/read/lines]
          │
          ▼
Ứng dụng                       [xử lý các ký tự Unicode]


GHI (chars → bytes)

Ứng dụng                       [String / char[]]
          │
          ▼
BufferedWriter                 [đệm char; flush/close]
          │
          ▼
OutputStreamWriter             [CharsetEncoder: char → byte]
          │
          ▼
OutputStream                   [nhận byte; có thể có buffer bên dưới]
          │
          ▼
File / Socket / ByteArrayOutputStream
```

**Không được lẫn tầng:** `BufferedWriter` làm việc với ký tự, `OutputStreamWriter` biến ký tự thành byte theo `Charset`, còn `OutputStream` đẩy byte tới một sink. Một `IOException` ở bất cứ tầng nào có thể được truyền lên tầng gọi, nhưng có một số wrapper (đáng chú ý `PrintWriter`) dùng cơ chế báo lỗi khác.

Trong ứng dụng thực tế, có thể chỉ dùng `Files.newBufferedReader(path, StandardCharsets.UTF_8)` và `Files.newBufferedWriter(path, StandardCharsets.UTF_8)`, không cần tự lắp từng lớp. Hiểu pipeline vẫn quan trọng khi xử lý lỗi, đóng tài nguyên hoặc yêu cầu kiểm soát decoder/encoder.

## 3. Phân vai từng lớp I/O

| Lớp / API | Đơn vị dữ liệu | Trách nhiệm chính | `flush`? | `close`? | Cách báo lỗi thông thường |
| --- | --- | --- | --- | --- | --- |
| `InputStream` | byte | Đọc byte từ nguồn | Không có `flush` | Có, để giải phóng tài nguyên theo implementation | `IOException` từ `read/close` |
| `OutputStream` | byte | Ghi byte ra đích | Có `flush`; tác dụng cụ thể tùy implementation và các wrapper | Có | `IOException` từ `write/flush/close` |
| `InputStreamReader` | char | Giải mã byte sang char theo Charset | Không có `flush` | Có; đóng reader và nguồn byte bên dưới theo hợp đồng | `IOException` và lỗi decoding được báo dưới dạng IOException khi cấu hình strict |
| `OutputStreamWriter` | char → byte | Mã hóa char thành byte theo Charset | Có; đẩy dữ liệu encoder/buffer tới stream | Có; kết thúc Writer và đóng stream liên quan | `IOException`, trong đó có lỗi encoding nếu dùng encoder `REPORT` |
| `BufferedReader` | char | Đệm dữ liệu đọc, `readLine`, `read` | Không có `flush` | Có; đóng Reader bên dưới | `IOException` từ hoạt động đọc hoặc đóng |
| `BufferedWriter` | char | Giữ dữ liệu ghi trong char buffer, giảm số lần gọi xuống lớp dưới | Có; đẩy ký tự đang đệm xuống Writer | Có; đóng, flush theo hợp đồng Writer | `IOException` ở `write/flush/close` |
| `PrintWriter` | char / định dạng | `print/println/printf`, tùy chọn auto-flush | Có; thêm hành vi auto-flush có điều kiện | Có | Chủ yếu kiểm tra cờ bằng `checkError()`; các phương thức ghi không ném IOException thông thường |
| `Files.newBufferedReader/Writer` | path + Charset | Factory dựng pipeline I/O với charset rõ | Writer có, Reader không | Có qua đối tượng tạo ra | `IOException` khi mở, đọc, ghi hoặc đóng |

Đây là bảng về **hợp đồng API**, không khẳng định mọi implementation tự động fsync dữ liệu hay hỗ trợ retry. Một `OutputStream` tuỳ biến có thể chỉ giữ byte trong RAM, không hề ghi ra thiết bị.

### 3.1. Lớp ngoài không quyết định charset nếu chưa có bridge phù hợp

`BufferedWriter` tự nó không biết UTF-8 hay UTF-16. Charset được chọn khi có `OutputStreamWriter` hoặc một factory writer nhận `Charset`:

```java
var writer = new java.io.BufferedWriter(
        new java.io.OutputStreamWriter(
                outputStream, java.nio.charset.StandardCharsets.UTF_8));
```

Đây là **đoạn nằm trong phương thức đã khai báo `outputStream`**. Nếu `BufferedWriter` nhận một Writer khác, chính Writer bên dưới có thể áp dụng một cơ chế chuyển đổi khác. Đừng đặt tên biến là `utf8Writer` rồi nghĩ điều đó chọn charset.

### 3.2. Reader cũng có thể đọc trước

`InputStreamReader` có thể đọc **nhiều byte hơn mức cần để trả ngay ký tự mà bạn vừa yêu cầu**, để giải mã hiệu quả. `BufferedReader` lại có thể đọc trước thêm ký tự. Vì vậy không được tự ý đọc trực tiếp từ cùng một `InputStream` song song với một `BufferedReader` đang bọc nó rồi kỳ vọng hai luồng cùng chia sẻ vị trí đơn giản, nhất quán.

Một API nhận Reader không nên âm thầm truy cập InputStream bên dưới thông qua tham chiếu còn lại. Ownership và đối tượng thực sự được dùng để đọc phải được quyết định rõ.

## 4. `write`, `flush` và `close` là ba thời điểm khác nhau

### 4.1. `write` có thể chỉ ghi vào buffer

Khi gọi:

```java
var buffer = new java.io.ByteArrayOutputStream();
var writer = new java.io.BufferedWriter(
        new java.io.OutputStreamWriter(
                buffer, java.nio.charset.StandardCharsets.UTF_8), 32);

writer.write("Hello");
```

`BufferedWriter` có thể vẫn giữ toàn bộ 5 ký tự, nên `buffer.size()` tại thời điểm này **không buộc phải là 5 byte**. Một tầng mã hóa khác cũng có thể giữ trạng thái chưa được hoàn tất. Không suy ra “đã tới file/socket” chỉ vì `write` trở về bình thường.

Trong chương trình lab, buffer ký tự được chọn đủ lớn và output có thể đo trực tiếp để minh họa rõ `0 byte trước flush`.

### 4.2. `flush` đẩy dữ liệu xuống lớp tiếp theo

```java
writer.flush();
```

`BufferedWriter.flush()` đẩy những ký tự đang đệm xuống Writer bên dưới rồi flush Writer ấy. `OutputStreamWriter.flush()` cố gắng chuyển các byte đã mã hóa ra OutputStream bên dưới theo hợp đồng. Nếu bên dưới còn `BufferedOutputStream`, thao tác flush cũng phải được truyền qua hệ lớp nếu muốn đẩy bộ đệm byte xuống sink.

**Giới hạn:** flush thành công giúp đẩy dữ liệu qua các buffer được triển khai đúng, **không mặc nhiên chứng minh dữ liệu đã được ghi bền vững lên đĩa sau mất điện** hoặc backend từ xa đã commit giao dịch. Các bảo đảm về durability đòi hỏi cơ chế cụ thể như `FileChannel.force(...)`, chính sách của filesystem và giao thức phía nhận.

### 4.3. `close` kết thúc vòng đời và có thể thất bại

Đối với các Writer thông dụng, `close()` flush dữ liệu còn lại trước khi đóng. `BufferedWriter.close()` đóng Writer bên dưới; `OutputStreamWriter.close()` đóng OutputStream bên dưới. Với reader, đóng lớp ngoài giải phóng tài nguyên thuộc các lớp đọc bên dưới theo hợp đồng.

**Đừng báo hoàn tất khi chưa đóng thành công** nếu đích cần file hoàn chỉnh. Ví dụ `transferTo` hoặc các lệnh `write` đã xong, nhưng `close` phát hiện lỗi ghi byte cuối cùng; toàn bộ tác vụ vẫn có thể là **thất bại**.

Sau khi đóng, thông thường không thể gọi `write/flush` tiếp trên Writer; nên xem đối tượng đó đã hết vòng đời. Một số đối tượng đặc biệt như `ByteArrayOutputStream` có hành vi riêng sau `close`, nhưng đó không phải hợp đồng chung của mọi stream.

### 4.4. Khi nào cần gọi `flush` thủ công trước `close`?

Nếu output cần được phía dưới nhận **trước khi bạn đóng** (ví dụ giao thức tương tác, yêu cầu ghi tiến độ, truyền một thông điệp rồi chờ phản hồi), hãy gọi `flush` tại thời điểm giao thức yêu cầu. Với output chỉ ghi một lần rồi đóng, `try-with-resources` thường cho phép Writer flush qua `close` mà không cần gọi `flush` sau mỗi dòng.

Gọi `flush` liên tục sau từng ký tự có thể làm giảm hiệu quả buffering. Ngược lại, giữ dữ liệu trong bộ đệm quá lâu khi ứng dụng cần phản hồi tức thời có thể gây sự cố giao thức. Lựa chọn theo **đơn vị thông điệp và hợp đồng truyền dữ liệu**, không phải “cứ ghi là flush”.

## 5. Charset phải được chỉ định và kiểm tra tại tầng chuyển đổi

### 5.1. Dùng `StandardCharsets` để tránh phụ thuộc cấu hình môi trường

Đọc:

```java
try (var in = java.nio.file.Files.newBufferedReader(
        path, java.nio.charset.StandardCharsets.UTF_8)) {
    String first = in.readLine();
}
```

Ghi:

```java
try (var out = java.nio.file.Files.newBufferedWriter(
        path, java.nio.charset.StandardCharsets.UTF_8)) {
    out.write("Xin chào");
}
```

Đây là **hai đoạn minh họa trong phương thức** có biến `path` kiểu `Path`. Trên JDK hiện đại, charset mặc định đã được chuẩn hóa phần lớn theo UTF-8, nhưng **nêu rõ charset vẫn là cách thể hiện hợp đồng file/giao thức rõ ràng**. Với nguồn/đích yêu cầu charset khác, phải dùng đúng charset đó, không gán nhãn UTF-8 chỉ vì văn bản là Unicode.

Một tệp UTF-8 đọc nhầm bằng ISO-8859-1 có thể **không ném lỗi** mà tạo văn bản méo dấu. Việc `readLine` trả dữ liệu không chứng minh charset đã chính xác. Dùng test round-trip và dữ liệu ký tự ngoài ASCII.

### 5.2. Khi dữ liệu malformed/unmappable, các constructor thông thường có thể thay thế ký tự

Một bridge tạo bằng `new InputStreamReader(input, StandardCharsets.UTF_8)` sử dụng cơ chế xử lý chuỗi byte không hợp lệ theo quy tắc decoder mà JDK cung cấp; constructor với `Charset` thường thay thế lỗi giải mã bằng ký tự thay thế. Tương tự, `new OutputStreamWriter(out, StandardCharsets.US_ASCII)` thông thường có thể thay ký tự không mã hóa được bằng byte thay thế thay vì ném exception.

Đây là lý do phải phân biệt:
- **Lỗi truy cập thiết bị I/O:** ví dụ file không đọc được, socket bị ngắt.
- **Dữ liệu không hợp lệ theo Charset:** ví dụ UTF-8 có byte sequence sai hoặc một ký tự Unicode không thể mã hóa dưới US-ASCII.
- **Chế độ xử lý lỗi encoding:** `REPLACE` / `REPORT` / `IGNORE` là các lựa chọn được điều khiển ở `CharsetDecoder` / `CharsetEncoder`. Không phải mọi cấu hình đều báo lỗi.

Với dữ liệu cần nguyên vẹn, nên sử dụng decoder/encoder có chính sách **`CodingErrorAction.REPORT`** để phát hiện sự cố. Không đổi sang `IGNORE` chỉ nhằm làm test xanh vì nó có thể làm mất dữ liệu mà không báo rõ.

### 5.3. Decoder nghiêm ngặt — báo lỗi malformed UTF-8

```java
byte[] invalid = {(byte) 0xC3, (byte) 0x28};

var decoder = java.nio.charset.StandardCharsets.UTF_8
        .newDecoder()
        .onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
        .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT);

try (var reader = new java.io.InputStreamReader(
        new java.io.ByteArrayInputStream(invalid), decoder)) {
    reader.read(new char[8]);
}
```

Đây là một đoạn **cố ý gây lỗi**: `0xC3` cần byte tiếp theo hợp lệ trong UTF-8, nhưng `0x28` không phải continuation byte. Reader báo lỗi dạng `MalformedInputException` (một subtype của `CharacterCodingException` và `IOException`) khi quá trình đọc gặp dữ liệu sai.

Với giao thức có dữ liệu tùy ý, phải xác định policy: từ chối dữ liệu, báo lỗi có offset, hay thay thế; không để mặc định không được tài liệu hóa quyết định tính toàn vẹn của chuỗi.

### 5.4. Encoder nghiêm ngặt — báo lỗi khi ký tự không mã hóa được

```java
var encoder = java.nio.charset.StandardCharsets.US_ASCII
        .newEncoder()
        .onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
        .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT);

try (var writer = new java.io.OutputStreamWriter(
        new java.io.ByteArrayOutputStream(), encoder)) {
    writer.write("\u00E9"); // é không có mã trực tiếp trong US-ASCII.
}
```

Đoạn này **cố ý gây lỗi** `UnmappableCharacterException`. Lưu ý lỗi có thể xuất hiện tại `write`, `flush` hoặc `close` tùy buffer/encoder; hãy kiểm soát toàn bộ vòng đời bằng `try-with-resources` và kiểm tra exception thực tế. Chương trình lab có `catch` xác định để in một dòng thống nhất.

**Không nhầm** `MalformedInputException` (dữ liệu sai cấu trúc encoding) với `UnmappableCharacterException` (ký tự hợp lệ nhưng không biểu diễn được trong charset đích). Đây là hai loại lỗi khác nhau, dù đều thuộc nhóm `CharacterCodingException`.

## 6. `PrintWriter`: các lời gọi in có thể không ném `IOException`

`PrintWriter` tiện để xuất văn bản định dạng:

```java
var printer = new java.io.PrintWriter(writer, true);
printer.println("hello");
```

Nhưng cần biết:
- Các phương thức ghi/in của `PrintWriter` **không truyền `IOException` như các Writer thông thường**. Nó lưu trạng thái lỗi để có thể kiểm tra.
- `checkError()` trả boolean cho biết đã có lỗi; việc kiểm tra cũng flush nếu writer chưa đóng, theo hợp đồng `PrintWriter`.
- Tùy chọn **autoFlush** trên `PrintWriter` áp dụng với `println`, `printf` hoặc `format` chứ **không phải mọi lần `write`** hay chỉ vì có ký tự xuống dòng nằm trong một chuỗi.
- `close` của `PrintWriter` cũng không tự biến nó thành một công cụ giao dịch nguyên tử.

Nếu chương trình cần biết việc ghi text có lỗi hay không:

```java
try (var printer = new java.io.PrintWriter(
        new java.io.OutputStreamWriter(
                outputStream, java.nio.charset.StandardCharsets.UTF_8),
        true)) {
    printer.println("ready");

    if (printer.checkError()) {
        throw new java.io.IOException(
                "PrintWriter reported an output error");
    }
}
```

Đoạn là **mã minh họa trong một phương thức đã có `outputStream`**. Nó không thay thế policy lỗi của bước đóng/publish. Đặc biệt, nếu application chỉ bắt `IOException` bên ngoài `printer.println` mà không kiểm tra `checkError`, có thể báo thành công sai.

Khi muốn đường đi lỗi dựa trên `IOException` trực tiếp, `BufferedWriter` hoặc `OutputStreamWriter` thường giúp luồng điều khiển rõ hơn. Không phải vì `PrintWriter` đã lỗi thời; nó vẫn dùng được, nhưng **cơ chế báo lỗi khác** cần được hiểu.

## 7. `try-with-resources`, ownership và suppressed exceptions

### 7.1. Chỉ đóng các tài nguyên mà scope thực sự sở hữu

Một cách đọc/ghi file UTF-8:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class TextFileCopy {
    public static void copy(Path source, Path target)
            throws IOException {
        try (var in = Files.newBufferedReader(
                     source, StandardCharsets.UTF_8);
             var out = Files.newBufferedWriter(
                     target, StandardCharsets.UTF_8)) {
            in.transferTo(out);
        }
    }
}
```

Đây là **class độc lập** nếu lưu tên tệp `TextFileCopy.java`. Nó biểu diễn quản lý resource, nhưng **không bảo đảm thay thế file đích an toàn**: với option mặc định của `Files.newBufferedWriter`, tệp đích có thể được tạo mới hoặc truncate khi mở. `Reader.transferTo` có thể chuyển một phần rồi ném `IOException`; writer còn có thể lỗi trong `close`.

Nếu API **nhận** một `Reader` hoặc `Writer` do caller cung cấp và caller tiếp tục dùng nó, đừng tự đóng chúng trừ khi hợp đồng chỉ định helper nhận ownership. Lỗi lúc close thuộc trách nhiệm scope sở hữu; việc quản lý phải được tài liệu hóa.

### 7.2. Thứ tự đóng của nhiều resource là **ngược với thứ tự khai báo**

```java
try (var input = openReader();
     var output = openWriter()) {
    // ...
}
```

Ví dụ trên là **pseudocode minh họa** với hai hàm factory chưa định nghĩa. Khi ra khỏi `try`, Java cố gắng đóng **`output` trước `input`**. Đây là thuộc tính của `try-with-resources`, không phụ thuộc vào tên biến.

Với wrapper theo chuỗi như `BufferedWriter(OutputStreamWriter(OutputStream))`, thường chỉ cần quản lý **wrapper ngoài cùng** theo owner; đóng nó sẽ truyền trách nhiệm xuống lớp dưới. Không cần luôn khai báo đồng thời các lớp con là resource độc lập rồi tự đóng lặp. Việc đóng hai lần có thể vô hại với một số implementation nhưng không phải lý do để thiết kế ownership mơ hồ.

### 7.3. Lỗi chính và lỗi khi đóng tài nguyên

Nếu body của `try` ném lỗi ở `write` và `close` cũng ném, Java giữ **exception từ body là lỗi chính**, còn lỗi đóng là một **suppressed exception** có thể xem qua `getSuppressed()`.

Ví dụ đơn giản:

```java
try (var writer = new FailOnWriteAndCloseWriter()) {
    writer.write("X"); // IOException "write-failed"
} catch (IOException ex) {
    System.out.println(ex.getMessage());             // write-failed
    System.out.println(ex.getSuppressed().length);    // 1
    System.out.println(ex.getSuppressed()[0].getMessage()); // close-failed
}
```

Đây là **mã minh họa** tham chiếu custom Writer được định nghĩa đầy đủ trong lab, không phải đoạn chạy riêng. Trong dự án thật, khi log nên ghi exception chính và những suppressed exceptions có ý nghĩa. Nếu chỉ log `ex.getMessage()`, lỗi flush/close thứ hai có thể bị mất dấu.

Khi **không có lỗi body** nhưng `close` ném, exception khi đóng trở thành lỗi chính; không được bỏ qua chỉ vì mọi `write` trước đó trở về bình thường.

### 7.4. Có nên luôn gọi `flush` rồi mới đóng?

Có thể gọi `flush` trước để phát hiện lỗi ở mốc cụ thể (ví dụ cần gửi một message hoàn chỉnh), nhưng **vẫn phải xử lý lỗi trong `close`**. Không nên xem `flush` thành công là lý do bỏ qua `close`; nó cũng không thay thế cơ chế fsync/durability.

Thứ tự kiểm soát thường là: **write → flush khi hợp đồng yêu cầu → close → validate/publish/commit nếu có → báo thành công**. Việc publish phải đặt sau khi close và mọi bước xác thực cần thiết thành công.

## 8. Lab Java hoàn chỉnh: 15 dòng output, không cần tệp thật

Chương trình dưới đây dùng `ByteArrayOutputStream` để quan sát byte thực sự tới tầng stream, triển khai Writer/OutputStream giả lập lỗi, và kiểm tra cả chính sách charset nghiêm ngặt. Nó **không ghi dữ liệu lên đĩa**, nên tái hiện kết quả trên nhiều môi trường.

### 8.1. Chuẩn bị

Dùng một JDK đang được hỗ trợ/bảo trì, chẳng hạn bản phân phối **JDK 21 hoặc 25 LTS** còn cập nhật bảo mật:

```bash
java -version
javac -version
```

Lưu chương trình sau vào tệp **`CharsetLayerLifecycleLab.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.io.PrintWriter;
import java.io.Writer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.charset.UnmappableCharacterException;

public class CharsetLayerLifecycleLab {
    static final class TrackedBytes extends ByteArrayOutputStream {
        boolean closed;

        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }
    }

    static final class BrokenWire extends OutputStream {
        @Override
        public void write(int b) throws IOException {
            throw new IOException("wire-failed");
        }
    }

    static final class WriteAndCloseFailWriter extends Writer {
        @Override
        public void write(char[] data, int off, int len)
                throws IOException {
            throw new IOException("write-failed");
        }

        @Override
        public void flush() { }

        @Override
        public void close() throws IOException {
            throw new IOException("close-failed");
        }
    }

    static final class CloseTrace implements AutoCloseable {
        private final String name;
        private final StringBuilder trace;

        CloseTrace(String name, StringBuilder trace) {
            this.name = name;
            this.trace = trace;
        }

        @Override
        public void close() {
            if (trace.length() > 0) {
                trace.append(">");
            }
            trace.append(name);
        }
    }

    public static void main(String[] args) throws Exception {
        // Một Unicode code point ngoài BMP gồm hai char UTF-16.
        String payload = "A\uD83D\uDCA1B";
        var sink = new TrackedBytes();

        // BufferedWriter -> OutputStreamWriter -> OutputStream.
        try (var writer = new BufferedWriter(
                new OutputStreamWriter(
                        sink, StandardCharsets.UTF_8), 32)) {
            writer.write(payload);
            System.out.println(
                    "buffered bytes before flush: " + sink.size());

            writer.flush();
            System.out.println(
                    "UTF-8 bytes after flush: " + sink.size());

            writer.write("!");
        }

        System.out.println("bytes after close: " + sink.size());
        System.out.println("underlying output closed: " + sink.closed);
        System.out.println("UTF-16 char units: " + payload.length());
        System.out.println("Unicode code points: "
                + payload.codePointCount(0, payload.length()));

        // Giải mã ngược từ byte bằng đúng charset.
        try (var input = new BufferedReader(
                new InputStreamReader(
                        new ByteArrayInputStream(sink.toByteArray()),
                        StandardCharsets.UTF_8))) {
            var decoded = input.readLine();
            System.out.println(
                    "roundtrip equal: " + decoded.equals(payload + "!"));
        }

        // Đọc nhầm charset có thể tạo chữ sai mà không ném lỗi.
        byte[] utf8 = "caf\u00E9".getBytes(StandardCharsets.UTF_8);
        System.out.println("wrong charset equal: "
                + new String(
                        utf8, StandardCharsets.ISO_8859_1)
                        .equals("caf\u00E9"));

        // Strict decoder: UTF-8 malformed sequence.
        byte[] invalid = {(byte) 0xC3, (byte) 0x28};
        try (var reader = new InputStreamReader(
                new ByteArrayInputStream(invalid),
                StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT))) {
            reader.read(new char[4]);
        } catch (MalformedInputException ex) {
            System.out.println(
                    "strict decoder: MalformedInputException");
        }

        // Strict encoder: é không thể mã hóa bằng US-ASCII.
        try (var writer = new OutputStreamWriter(
                new ByteArrayOutputStream(),
                StandardCharsets.US_ASCII.newEncoder()
                        .onUnmappableCharacter(CodingErrorAction.REPORT))) {
            writer.write("\u00E9");
        } catch (UnmappableCharacterException ex) {
            System.out.println(
                    "strict encoder: UnmappableCharacterException");
        }

        // PrintWriter lưu cờ lỗi thay vì truyền IOException.
        try (var printWriter = new PrintWriter(
                new OutputStreamWriter(
                        new BrokenWire(), StandardCharsets.UTF_8), true)) {
            printWriter.print("X");
            System.out.println(
                    "PrintWriter error flag: "
                            + printWriter.checkError());
        }

        // Lỗi body và close: close error trở thành suppressed.
        try (var writer = new WriteAndCloseFailWriter()) {
            writer.write("X");
        } catch (IOException ex) {
            System.out.println(
                    "primary error: " + ex.getMessage());
            System.out.println(
                    "suppressed count: " + ex.getSuppressed().length);
            System.out.println("suppressed error: "
                    + ex.getSuppressed()[0].getMessage());
        }

        // try-with-resources đóng theo thứ tự ngược khai báo.
        var trace = new StringBuilder();
        try (var source = new CloseTrace("source", trace);
             var target = new CloseTrace("target", trace)) {
            // Không cần thao tác trong body.
        }
        System.out.println("resource close order: " + trace);
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac CharsetLayerLifecycleLab.java
java CharsetLayerLifecycleLab
```

### 8.2. Stdout chính xác

```text
buffered bytes before flush: 0
UTF-8 bytes after flush: 6
bytes after close: 7
underlying output closed: true
UTF-16 char units: 4
Unicode code points: 3
roundtrip equal: true
wrong charset equal: false
strict decoder: MalformedInputException
strict encoder: UnmappableCharacterException
PrintWriter error flag: true
primary error: write-failed
suppressed count: 1
suppressed error: close-failed
resource close order: target>source
```

Không có output phụ thuộc số byte mà console dùng để hiển thị biểu tượng, tên file hay hệ điều hành. Lab so sánh nội dung Unicode bằng boolean. Các message `write-failed` và `close-failed` do chính lớp giả lập tạo, không phải giả định về thông điệp của I/O hệ thống.

### 8.3. Giải thích kết quả theo tầng

**Tầng 1 — ký tự trong buffer.** `writer.write(payload)` đưa 4 đơn vị `char` vào `BufferedWriter` có buffer 32 ký tự. Trong lab, chưa có byte nào tới `sink` nên in `0`.

**Tầng 2 — mã hóa và flush.** `writer.flush()` đẩy ký tự xuống `OutputStreamWriter` rồi xuống `TrackedBytes`; `"A💡B"` mã hóa UTF-8 thành `1+4+1=6` byte. Đây là số byte trong sink **RAM**, không phải xác nhận file đã fsync.

**Tầng 3 — close.** Ghi thêm `"!"` sau flush rồi để `try-with-resources` đóng `BufferedWriter`. Phần ký tự còn lại được flush/encode thành 1 byte, tổng 7; `TrackedBytes.closed==true` cho thấy đóng wrapper ngoài đã đóng stream bên dưới.

**Tầng 4 — đếm mã Unicode.** `String.length()==4` vì `💡` gồm hai UTF-16 `char`; `codePointCount(...)=3` vì về mặt Unicode có ba code point. Tính số byte phải dựa trên charset, không dựa vào `length()`.

**Tầng 5 — đọc đúng charset.** `InputStreamReader` giải mã cùng UTF-8 và `BufferedReader.readLine()` trả chuỗi bằng dữ liệu gốc cộng `!`. Không có ký tự xuống dòng trong dữ liệu nên `readLine()` trả toàn bộ chuỗi trước EOF.

**Tầng 6 — đọc sai charset.** Byte UTF-8 của `café` được đọc như ISO-8859-1, tạo chuỗi không bằng `café`; giá trị `false` không nhất thiết đi kèm exception. Đây là lỗi chất lượng dữ liệu dễ bị bỏ sót nếu chỉ kiểm tra mở/đọc file thành công.

**Tầng 7 — strict decoder/encoder.** Dãy byte UTF-8 sai cấu trúc gây `MalformedInputException`. Ký tự `é` không mã hóa được trong US-ASCII gây `UnmappableCharacterException` khi dùng encoder `REPORT`. Hai loại lỗi đều liên quan charset, nhưng phân biệt đúng nguyên nhân.

**Tầng 8 — cờ lỗi PrintWriter.** `BrokenWire.write` luôn ném `IOException`; `PrintWriter` không truyền exception ra khỏi `print` mà `checkError()` trả `true`. Đây là cơ chế báo lỗi đặc thù quan trọng.

**Tầng 9 — try-with-resources.** `write` ném `IOException("write-failed")`, rồi `close` cũng ném `IOException("close-failed")`. Java giữ lỗi đầu làm primary và một suppressed exception cho lần đóng. Kết quả `target>source` cho thấy resources được đóng theo thứ tự ngược với khai báo.

## 9. Báo lỗi ở đúng tầng và không làm mất thông tin nguyên nhân

Một pipeline có nhiều nguồn lỗi nhưng không phải tất cả đều nên được gộp thành thông báo “encoding lỗi”.

| Điểm lỗi | Ví dụ | Exception/biểu hiện thường gặp | Bước xử lý hợp lý |
| --- | --- | --- | --- |
| Mở file | Không có quyền / sai đường dẫn | `IOException`, có subtype chuyên biệt | Kiểm tra path, quyền, thông báo có ngữ cảnh |
| Đọc byte | Đĩa/kết nối hỏng | `IOException` | Không giả định đầu vào còn có thể đọc tiếp |
| Giải mã byte | UTF-8 sai cấu trúc | `MalformedInputException` nếu decoder `REPORT`, hoặc ký tự thay thế nếu policy `REPLACE` | Báo lỗi dữ liệu, nguồn encoding và vị trí nếu đo được |
| Đọc dòng | BufferedReader giữ dữ liệu nhưng stream lỗi | `IOException` | Đóng, cleanup theo ownership, không công bố dữ liệu chưa hoàn thành |
| Mã hóa char | Unicode không ánh xạ được sang charset đích | `UnmappableCharacterException` nếu encoder `REPORT` | Chọn đúng charset hoặc từ chối dữ liệu |
| Ghi byte | Đích hết dung lượng / kết nối ngắt | `IOException` | Đánh dấu output có thể đã được ghi một phần |
| Flush | Writer/stream bên dưới báo lỗi | `IOException` | Chưa báo thành công; đóng/cleanup và quyết định retry |
| Close | Ghi byte cuối cùng hoặc đóng thiết bị thất bại | `IOException` hoặc suppressed | Báo lỗi hoàn tất; log primary + suppressed |
| PrintWriter | Lỗi I/O bị ghi nhận thành trạng thái | `checkError()==true` | Kiểm tra cờ trước khi báo success |
| Publish | Move/commit cuối cùng thất bại | Exception từ file system/backend | Giữ trạng thái cũ hoặc xử lý staging theo policy |

### 9.1. Không bắt một `Exception` rồi vứt nguyên nhân

Mẫu không nên dùng:

```java
try {
    writer.write(text);
} catch (Exception ignored) {
    System.out.println("OK");
}
```

Đây là **đoạn cố ý sai**, giả sử có `writer` và `text`. Nó che lỗi ghi, khiến output hỏng có thể được công bố.

Một handler hợp lý phải truyền nguyên nhân tới lớp có trách nhiệm quyết định retry/publish, đồng thời xử lý cleanup trong `finally` hoặc `try-with-resources`. Nếu catch rồi ném exception mới, giữ nguyên nhân qua `new IOException("...", cause)` và ghi cả suppressed exceptions có liên quan.

### 9.2. Đóng thành công mới là một bước, chưa phải cam kết lưu bền vững

Ngay cả khi toàn bộ `write/flush/close` thành công, ứng dụng vẫn có thể cần:
- Xác minh số byte/checksum hoặc schema nếu đích quan trọng.
- Đặt tên/đổi tệp tạm thành tệp chính thức.
- Đồng bộ ra thiết bị nếu contract durability đòi hỏi.
- Nhận ACK/commit từ dịch vụ, queue hoặc database.

Chỉ sau khi đạt mức thành công mà **hợp đồng nghiệp vụ** yêu cầu mới ghi log `SUCCESS`. Không nâng một thành công ở tầng `BufferedWriter` thành tuyên bố transaction hoàn tất ở tầng hệ thống.

## 10. Ghi file an toàn hơn: staging trước khi publish

Một ví dụ hay gặp là ghi đè tệp cấu hình UTF-8. Nếu mở `Files.newBufferedWriter(target, UTF_8)` trực tiếp, target có thể bị tạo/truncate trước khi ghi xong. Lỗi mã hóa, lỗi thiết bị, lỗi flush hoặc close có thể để lại một tệp chỉ có **một phần** nội dung.

Mô hình staging:

```text
Dữ liệu text
     │
     ▼
Writer UTF-8 mở vào tệp tạm riêng
     │
     ▼
write / flush / close hoàn tất
     │
     ▼
validate nội dung/checksum nếu cần
     │
     ▼
Files.move(temp, target, ATOMIC_MOVE) khi provider hỗ trợ
     │
     ▼
Công bố target chính thức
```

### Ví dụ hàm minh họa

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public final class StagedUtf8Writer {
    public static void publish(Path destination, String content)
            throws IOException {
        Path target = destination.toAbsolutePath();
        Path temp = Files.createTempFile(
                target.getParent(), ".writing-", ".tmp");
        boolean published = false;

        try {
            try (var out = Files.newBufferedWriter(
                    temp, StandardCharsets.UTF_8)) {
                out.write(content);
            }

            // Chỉ thực hiện sau khi close thành công.
            Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE);
            published = true;
        } finally {
            if (!published) {
                Files.deleteIfExists(temp);
            }
        }
    }
}
```

Class `StagedUtf8Writer` là đoạn minh họa tách khỏi lab, có thể biên dịch với JDK hiện đại, nhưng việc **chạy thành công phụ thuộc vào file system**, path và quyền truy cập. `ATOMIC_MOVE` không được hỗ trợ ở mọi provider; nếu không hỗ trợ, Java ném `AtomicMoveNotSupportedException`. **Không tự fallback sang move thường** nếu nghiệp vụ bắt buộc atomicity.

Nếu tệp đích đã tồn tại, cách provider xử lý `ATOMIC_MOVE` và thay thế đích có thể phụ thuộc implementation; phải quyết định rõ chính sách overwrite/đua tranh giữa nhiều writer trước khi dùng trong production. Atomic move cũng không tự bảo đảm fsync, chống mất điện, backup, phân quyền, symlink safety hoặc tính nguyên tử đa tệp.

Nếu `Files.deleteIfExists(temp)` trong cleanup cũng lỗi, cần giữ/ghi nhận lỗi gốc; trong hệ thống quan trọng nên thiết kế luồng cleanup để không vô tình làm mất nguyên nhân chính.

## 11. Các tình huống thiết kế thường gặp

### 11.1. Đọc tệp văn bản UTF-8 theo dòng

Dùng `Files.newBufferedReader(path, UTF_8)`, quản lý bằng `try-with-resources`. `readLine()` **loại bỏ ký tự kết thúc dòng**, vì vậy nếu cần sao chép nguyên văn line endings thì không đọc/xuất lại bằng `readLine/println` theo cách mặc định. Dùng `Reader.transferTo` (từ Java 10) khi muốn chuyển chính xác các ký tự còn lại theo stream và không cần xử lý từng dòng.

### 11.2. Ghi log dạng văn bản

Nếu cần format và chấp nhận cách báo lỗi của `PrintWriter`, phải kiểm tra `checkError` khi ứng dụng yêu cầu phát hiện lỗi. Với pipeline bắt buộc ném `IOException` để thông báo thất bại, `BufferedWriter` hoặc thư viện logging có chính sách lỗi và flushing rõ ràng thường thích hợp hơn. Không tự đóng `System.out` / `System.err` nếu ứng dụng còn các thành phần khác dùng chung.

### 11.3. Ghi văn bản nhiều byte sang socket

Writer ở tầng ứng dụng có thể flush thành công nhưng phía nhận chưa commit thông điệp. Thiết kế giao thức framing, charset, end-of-message, ACK và timeout riêng. Sau `IOException`, tránh retry mù trên cùng stream; bên nhận có thể đã đọc một phần. Đóng và tạo phiên mới theo chính sách, dùng idempotency key nếu tác vụ có side effects.

### 11.4. File chứa dữ liệu không tin cậy

Với CSV/JSON hay giao thức text phải giữ nguyên dữ liệu, dùng decoder/encoder `REPORT`, không lặng lẽ thay byte hỏng thành `�` hoặc `?`. Sau khi giải mã, vẫn cần validate syntax/schema; “UTF-8 hợp lệ” không tự đồng nghĩa “JSON/CSV hợp lệ” hoặc an toàn.

### 11.5. Lưu tệp quan trọng chỉ một lần

Tạo Writer vào tệp tạm trong cùng vùng lưu trữ thích hợp, đóng thành công, xác minh và publish theo policy. Đừng mở target chính thức bằng chế độ truncate khi yêu cầu là “giữ phiên bản cũ nếu ghi mới thất bại”.

### 11.6. Nhiều tầng buffer

`BufferedWriter(OutputStreamWriter(BufferedOutputStream(...)))` có thể có char buffer, encoder internal buffer và byte buffer. Chọn flush ở **wrapper ngoài** để dòng yêu cầu flush đi xuyên qua các lớp được triển khai đúng. Đừng chỉ gọi `flush` trên `OutputStream` bên dưới trong khi `BufferedWriter` còn giữ ký tự chưa đẩy xuống.

## 12. Lỗi thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Nghĩ `BufferedWriter.write` luôn gửi byte ra đích ngay | Lệnh ghi có thể mới chỉ cập nhật char buffer | Flush khi giao thức cần, close khi kết thúc |
| Nghĩ `flush` bằng `fsync` | Flush không mặc nhiên bảo đảm dữ liệu bền vững trên thiết bị | Dùng cơ chế durability riêng khi cần |
| Chỉ bắt lỗi ở `write`, không xử lý lỗi ở `close` | Byte cuối/buffer có thể lỗi khi đóng | `try-with-resources` và kiểm tra exception |
| Không khai báo Charset | Dễ lệch hợp đồng/định dạng dữ liệu | `StandardCharsets.UTF_8` hoặc charset được giao thức chỉ định |
| Nghĩ đọc sai charset luôn ném lỗi | Có thể decode ra ký tự khác hợp lệ | Round-trip test, decoder `REPORT` khi cần |
| Dùng `CharsetDecoder` mặc định và cho rằng nó luôn REPLACE | `newDecoder` mặc định có chính sách REPORT | Cấu hình `CodingErrorAction` tường minh |
| Nghĩ `OutputStreamWriter` nhận `Charset` sẽ luôn ném lỗi nếu không encode được | Constructor thông thường có thể thay ký tự | Cấp `CharsetEncoder` cấu hình `REPORT` |
| Nghĩ `PrintWriter.print` ném `IOException` như `BufferedWriter.write` | `PrintWriter` ghi trạng thái lỗi | Kiểm tra `checkError()` |
| Bật `autoFlush=true` rồi nghĩ mọi `write` đều flush | Auto-flush chỉ tại một số phương thức in/format | Dùng `flush()` tường minh khi cần |
| Đóng stream bên dưới trước wrapper | Wrapper có thể còn buffer chưa flush | Đóng lớp ngoài có ownership; dùng try-with-resources |
| Đóng tài nguyên caller cung cấp không có thỏa thuận | Caller có thể cần dùng tiếp, dễ gây lỗi chéo | Tài liệu hóa ownership |
| Chỉ log lỗi chính, bỏ suppressed | Mất lỗi cleanup/close | Đọc `getSuppressed()` |
| Sau `IOException` vẫn công bố kết quả như hoàn chỉnh | Output có thể đã được ghi một phần | Staging/transaction và báo thất bại |
| Dùng `BufferedReader.readLine` để copy nguyên văn newline | `readLine` loại bỏ line separator | Dùng API chuyển ký tự giữ nguyên hoặc xử lý line ending đúng |
| So sánh số `char` với byte UTF-8 | Một code point có thể gồm 2 UTF-16 char và nhiều byte | Đếm theo đơn vị đúng của nghiệp vụ |

## 13. Bài tập tự luyện có hướng giải

### Bài 1 — Sắp thứ tự các lớp I/O

Hãy mô tả thứ tự xử lý khi ghi `String` ra tệp UTF-8 bằng `BufferedWriter(OutputStreamWriter(FileOutputStream))`.

**Đáp án:** Ứng dụng tạo ký tự → `BufferedWriter` có thể đệm ký tự → `OutputStreamWriter` mã hóa ký tự sang byte UTF-8 → `FileOutputStream` ghi byte. Khi đóng writer ngoài, dữ liệu đang đệm phải được đẩy xuống theo hợp đồng. Việc chuyển byte thành dữ liệu bền vững tùy filesystem/durability policy.

### Bài 2 — Dữ liệu đã đến đích chưa?

```java
var buffer = new java.io.ByteArrayOutputStream();
var out = new java.io.BufferedWriter(
        new java.io.OutputStreamWriter(
                buffer, java.nio.charset.StandardCharsets.UTF_8), 32);
out.write("A");
```

**Hỏi:** Có thể khẳng định `buffer.size()==1` chưa?

**Đáp án:** Không chỉ từ lệnh `write`, vì ký tự có thể đang trong buffer. Trong lab với buffer đủ lớn, size bằng `0` trước flush và tăng sau flush. Phải đóng `out` đúng cách khi kết thúc.

### Bài 3 — UTF-16 và UTF-8

Chuỗi `"A💡B"` có bao nhiêu Java `char`, code points và byte UTF-8?

**Đáp án:** `4` đơn vị `char`, `3` code points và `6` byte UTF-8. `String.length()` không trả byte length.

### Bài 4 — Phát hiện malformed UTF-8

Dãy byte gồm `0xC3 0x28` được đọc bằng `InputStreamReader` với decoder UTF-8 `REPORT`. Chuyện gì xảy ra?

**Đáp án:** Gặp `MalformedInputException` lúc đọc. Nếu dùng bridge có policy `REPLACE`, có thể nhận ký tự thay thế và không ném exception, nên cần chọn policy theo hợp đồng dữ liệu.

### Bài 5 — Encoder không biểu diễn được ký tự

Ghi `"é"` bằng US-ASCII với `CharsetEncoder.onUnmappableCharacter(REPORT)`. Lỗi nào phù hợp?

**Đáp án:** `UnmappableCharacterException`, một dạng `CharacterCodingException`/`IOException`. Nếu ứng dụng cho phép thay thế bằng `?`, phải ghi rõ policy, không mặc định giữ nguyên được dữ liệu.

### Bài 6 — `PrintWriter` không báo lỗi qua catch

Một `OutputStream` luôn ném `IOException` ở `write(int)`. `PrintWriter` bọc nó, gọi `print("X")` nhưng không thấy `IOException` trực tiếp. Có nghĩa là ghi thành công?

**Đáp án:** Không. `PrintWriter` có thể giữ cờ lỗi, cần `checkError()`. Nếu yêu cầu exception làm cơ chế báo lỗi, dùng Writer truyền lỗi hoặc gói kết quả lỗi rõ ràng.

### Bài 7 — Lỗi trong `close`

Bạn gọi `BufferedWriter.write` mà không thấy exception, nhưng `close` ném `IOException`. Có được báo “file lưu thành công” không?

**Đáp án:** Chưa. Nội dung có thể chưa được flush hoàn tất. `try-with-resources` lan lỗi đóng; chỉ publish sau khi toàn bộ bước cần thiết hoàn thành.

### Bài 8 — Suppressed exception

`write` ném `IOException("write-failed")`, `close` ném `IOException("close-failed")` trong cùng một `try-with-resources`. Exception nào là chính?

**Đáp án:** `write-failed` là primary; `close-failed` nằm trong `getSuppressed()`. Test nên xác nhận **loại và quan hệ lỗi**, không phụ thuộc message của các lớp I/O hệ thống.

### Bài 9 — Thứ tự đóng resource

```java
try (var a = openA(); var b = openB()) {
    // ...
}
```

**Đáp án:** Java đóng `b` rồi `a` khi rời `try`. Đoạn chỉ minh họa vì hai factory chưa được định nghĩa; lab runnable dùng `CloseTrace` và in `target>source`.

### Bài 10 — Nhiều buffer và flush

Với `BufferedWriter(OutputStreamWriter(BufferedOutputStream(...)))`, chỉ gọi `flush` trên `BufferedOutputStream` bên trong thì có chắc các ký tự mới ghi ở BufferedWriter đã ra đích không?

**Đáp án:** Không. Char buffer ở ngoài có thể chưa đẩy dữ liệu xuống. Gọi `flush` trên **wrapper ngoài** khi giao thức cần gửi hết dữ liệu đang đệm, đồng thời hiểu flush không tự là fsync hay ACK từ xa.

### Bài 11 — Chuyển Reader sang Writer và đóng

`reader.transferTo(writer)` trả `long` mà bạn không nhận lỗi. Nó có tự `flush` hoặc `close` Writer không? Có nghĩa backend đã commit chưa?

**Đáp án:** Không. `Reader.transferTo` chuyển ký tự và báo số ký tự khi kết thúc bình thường, không tự flush/close. Chủ sở hữu vẫn cần đóng và thực hiện các bước commit/publish theo hợp đồng.

### Bài 12 — Bản sao output an toàn

Ứng dụng phải giữ tệp cấu hình cũ nếu ghi phiên bản mới thất bại. Dùng `Files.newBufferedWriter(target, UTF_8)` ghi trực tiếp có phù hợp không?

**Đáp án:** Không nếu yêu cầu bắt buộc bảo toàn tệp cũ. Writer mặc định có thể truncate tệp đích từ lúc mở. Hãy ghi tệp tạm, đóng thành công, validate rồi publish bằng cơ chế atomic/transaction phù hợp; xử lý rõ trường hợp file system không hỗ trợ.

## 14. Checklist trước khi hoàn thành một pipeline I/O

- [ ] Biết chính xác stream nào là byte, stream nào là ký tự và lớp nào mã hóa/giải mã.
- [ ] Có `Charset` rõ ràng cho dữ liệu trao đổi; kiểm tra round-trip có ký tự ngoài ASCII.
- [ ] Chọn chính sách `REPLACE`/`REPORT`/`IGNORE` cho malformed/unmappable data, không để xảy ra mất dữ liệu không mong muốn.
- [ ] Hiểu `BufferedWriter.write` có thể chưa đẩy byte xuống sink.
- [ ] Dùng `flush` khi giao thức cần, không giả định flush bằng fsync/commit.
- [ ] Đảm bảo việc `close` được thực hiện và lỗi khi đóng được quan sát.
- [ ] Dùng `try-with-resources`; phân định resource nào do scope sở hữu.
- [ ] Không đóng tầng trong trước tầng ngoài khi lớp ngoài còn buffer.
- [ ] Kiểm tra `PrintWriter.checkError` khi `PrintWriter` được dùng ở đường ghi quan trọng.
- [ ] Không báo thành công nếu exception I/O xuất hiện ở read/write/flush/close/publish.
- [ ] Giữ exception chính và suppressed exceptions trong logging/diagnostics.
- [ ] Không giả định dữ liệu đã đến đích hoặc còn nguyên vẹn khi lỗi I/O giữa chừng.
- [ ] Nếu ghi tệp quan trọng, có staging hoặc chính sách khôi phục phù hợp.
- [ ] Không dùng `String.length()` làm số byte UTF-8.
- [ ] Chạy `CharsetLayerLifecycleLab.java` và đối chiếu **15 dòng stdout**.
- [ ] Unit tests không phụ thuộc console encoding hoặc thông điệp exception của OS.

## 15. Kết luận

Khi quản lý I/O có charset, hãy nhìn theo **tầng**: byte stream làm việc với byte; `InputStreamReader/OutputStreamWriter` chuyển đổi theo charset; `BufferedReader/BufferedWriter` tối ưu bằng bộ đệm; `PrintWriter` hỗ trợ định dạng nhưng báo lỗi theo cờ; `try-with-resources` quản lý đóng và suppressed exceptions. **`write`, `flush`, `close` và `commit/publish` không phải một sự kiện duy nhất**.

Nêu rõ ownership, charset, chính sách xử lý malformed/unmappable data và điều kiện được phép báo thành công. Khi hiểu đúng trách nhiệm mỗi tầng, bạn có thể viết mã Java 10+ rõ ràng, dễ kiểm thử và vẫn phù hợp các JDK được hỗ trợ hiện nay.

## Tài liệu tham khảo chính thức

- [Java SE 25 API — InputStreamReader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/InputStreamReader.html): bridge byte → char, charset và khả năng đọc trước.
- [Java SE 25 API — OutputStreamWriter](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/OutputStreamWriter.html): bridge char → byte, charset encoder, buffer, flush và close.
- [Java SE 25 API — BufferedReader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/BufferedReader.html): đọc có buffer và `readLine`.
- [Java SE 25 API — BufferedWriter](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/BufferedWriter.html): bộ đệm ký tự, flush/close.
- [Java SE 25 API — Writer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Writer.html) và [OutputStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/OutputStream.html): `write`, `flush`, `close`.
- [Java SE 25 API — PrintWriter](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/PrintWriter.html): auto-flush, `checkError` và cách lưu trạng thái lỗi.
- [Java SE 25 API — CharsetDecoder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetDecoder.html), [CharsetEncoder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetEncoder.html) và [CodingErrorAction](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CodingErrorAction.html): `REPORT/REPLACE/IGNORE`.
- [Java SE 25 API — Files](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): factory tạo buffered Reader/Writer, move tệp.
- [Java SE 25 API — Reader.transferTo](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Reader.html#transferTo(java.io.Writer)): phương thức bổ sung trong Java 10, không tự close.
- [Java Language Specification `14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.20.3): thứ tự đóng và suppressed exceptions.