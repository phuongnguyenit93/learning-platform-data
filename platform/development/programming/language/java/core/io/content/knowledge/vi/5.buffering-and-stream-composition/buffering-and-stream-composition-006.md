# `flush()` đẩy bộ đệm phần mềm nhưng không đồng nghĩa dữ liệu bền vững

## Mục tiêu bài học

Trong Java I/O, gọi `flush()` đúng lúc giúp dữ liệu còn nằm trong **bộ đệm của một lớp ghi** được chuyển tiếp xuống tầng bên dưới. Nhưng điều đó **không có nghĩa** byte đã đến đĩa vật lý, sẽ sống sót sau mất điện, đã được phía mạng bên kia nhận và xử lý, hay toàn bộ thao tác ghi có tính nguyên tử.

Sau bài này, bạn có thể:

- Phân biệt **ghi vào buffer**, **flush**, **close**, **đọc lại được**, **synchronization/durability** và **atomicity**.
- Giải thích hành vi `flush()` của `BufferedOutputStream`, `BufferedWriter`, `OutputStreamWriter`, `PrintWriter` và các lớp bao.
- Biết khi nào dùng `FileChannel.force(...)` hoặc `FileDescriptor.sync()` để yêu cầu đồng bộ file với thiết bị lưu trữ.
- Thiết kế thứ tự thao tác khi phải vừa flush buffer ở Java vừa yêu cầu đồng bộ file, đồng thời hiểu giới hạn của thao tác rename, network flush và ứng dụng phân tán.
- Tránh gọi `flush()` quá thường xuyên hoặc dùng nó làm bằng chứng dữ liệu bền vững.

## 1. Một lời gọi `write()` có thể mới chỉ ghi vào bộ nhớ Java

Hãy hình dung ứng dụng muốn ghi một dòng vào file:

```text
Ứng dụng Java
    │ write("order=42\n")
    ▼
BufferedWriter / BufferedOutputStream       ← bộ đệm do Java/library quản lý
    │ flush() — chuyển dữ liệu còn đọng xuống tầng kế tiếp
    ▼
OutputStreamWriter / FileOutputStream
    │ ghi byte tới hệ điều hành
    ▼
Bộ đệm hệ điều hành / page cache             ← có thể vẫn ở RAM
    │ thao tác đồng bộ thích hợp (ví dụ force / fsync)
    ▼
Filesystem, driver, thiết bị lưu trữ         ← cơ chế cache/journal riêng
    │
    ▼
Dữ liệu được hệ thống lưu trữ xác nhận
```

Sơ đồ đơn giản hóa đường đi của một file bình thường; những filesystem, thiết bị, môi trường ảo hoặc storage từ xa có thể có các tầng khác. Điểm quan trọng là **mỗi tầng có bộ đệm và cam kết riêng**. `flush()` ở một lớp Java **không tự động đi qua tất cả các tầng** và không được hiểu như `fsync`.

Ví dụ: `BufferedOutputStream` nhận ba byte, cất chúng trong mảng byte nội bộ. Chừng nào buffer chưa đầy hoặc chưa flush, `OutputStream` bên dưới có thể chưa thấy byte nào. Khi gọi `flush()`, ba byte được gửi xuống underlying stream. Nếu underlying stream là `FileOutputStream`, hệ điều hành đã nhận lệnh ghi nhưng có thể chỉ lưu dữ liệu trong page cache. Nếu underlying stream là socket, byte có thể đang ở hàng đợi gửi của hệ điều hành.

Không phải mọi output stream đều sở hữu buffer riêng. Với `OutputStream` cơ sở, `flush()` có triển khai mặc định **không làm gì**; lớp con có thể ghi đè. Vì vậy, việc phương thức tồn tại trên API không đủ để kết luận có hoạt động đồng bộ xuống phần cứng.

## 2. Năm trạng thái phải phân biệt

| Trạng thái | Điều có thể khẳng định | Điều **chưa** thể kết luận |
|---|---|---|
| **`write(...)` vào lớp có buffer** | Lớp ghi đã chấp nhận dữ liệu theo hợp đồng API | Dữ liệu đã tới stream/file/socket bên dưới |
| **`flush()` thành công** | Lớp được gọi đã chuyển dữ liệu đang đệm và yêu cầu các tầng dưới flush theo hợp đồng lớp đó | Dữ liệu chắc chắn nằm trên đĩa bền vững hoặc bên nhận đã xử lý |
| **`close()` thành công** | Tài nguyên đã được đóng; với nhiều wrapper ghi phổ biến, dữ liệu còn đệm được flush trong lúc đóng | Đĩa đã được sync, giao dịch nguyên tử, hay phía mạng đã lưu |
| **Đọc lại file thấy dữ liệu** | Dữ liệu hiện quan sát được qua API đọc trong điều kiện hiện tại | Sau mất điện/OS crash, dữ liệu vẫn tồn tại |
| **`force()`/`sync()` thành công** | Đã yêu cầu cơ chế đồng bộ xuống thiết bị theo hợp đồng API và khả năng hỗ trợ | Một giao dịch nhiều file chắc chắn nguyên tử, thiết bị/đường truyền bất kỳ luôn đáp ứng mọi bảo đảm, hoặc thư mục/rename đã được đồng bộ đầy đủ |

Phân biệt **visibility (khả năng quan sát)** và **durability (độ bền sau sự cố)**. Một tiến trình khác có thể đọc thấy byte trong cache mà dữ liệu đó vẫn chưa được bảo đảm tồn tại sau crash.

Phân biệt thêm **atomicity (nguyên tử)**. Atomicity nói về việc người quan sát thấy toàn bộ trạng thái cũ hoặc mới, không thấy trạng thái nửa chừng; durability nói về trạng thái đã cam kết có còn sau sự cố hay không. `flush()`, `force()` và `ATOMIC_MOVE` giải quyết những vấn đề khác nhau, không thể thay thế nhau.

## 3. `flush()` của các lớp Java hoạt động ra sao?

### 3.1. `OutputStream` và `BufferedOutputStream`

`OutputStream.flush()` là phương thức cho phép lớp con đẩy byte còn đọng; triển khai mặc định không làm gì. `BufferedOutputStream` giữ byte trong vùng đệm và khi flush thì ghi các byte đó tới underlying stream, sau đó gọi `flush()` của stream bên dưới.

Cần để ý thứ tự khi ghép các lớp:

```java
OutputStream raw = Files.newOutputStream(path);
BufferedOutputStream buffered = new BufferedOutputStream(raw);
```

Đây là **đoạn minh họa**, giả sử `path` là `Path` hợp lệ và xử lý `IOException`. Nên dùng try-with-resources trong chương trình thực tế. `buffered.write(...)` có thể chỉ thay đổi mảng byte trong `buffered`. `buffered.flush()` đẩy byte xuống `raw`; **`raw.flush()` không nhất thiết đẩy được dữ liệu vẫn nằm bên trên trong `buffered`**. Gọi flush ở lớp ngoài cùng chịu trách nhiệm ghi để đi qua đúng chuỗi lớp bao.

Một stream bên dưới có thể có buffer khác. `BufferedOutputStream` không tự hứa rằng toàn bộ đường đi sau đó đến tận thiết bị lưu trữ đã ổn định.

### 3.2. `Writer`, `BufferedWriter`, `OutputStreamWriter`

`Writer` là abstraction dành cho ký tự, trong khi `OutputStream` ghi byte. `OutputStreamWriter` encode ký tự thành byte theo charset đã chọn và có thể giữ byte nội bộ trước khi gửi xuống stream. `BufferedWriter` lại có thêm buffer ký tự.

```text
BufferedWriter                (buffer char)
    ↓ flush()
OutputStreamWriter            (encoder ký tự → byte, có thể có buffer byte)
    ↓ flush()
OutputStream                  (tầng đích; có thể là BufferedOutputStream)
    ↓
file / network / memory sink
```

Vì vậy, flush **wrapper ghi bên ngoài** có ý nghĩa khi phải khiến dữ liệu đi qua toàn bộ chuỗi chuyển đổi ký tự/byte. Nếu chỉ flush `OutputStream` ở đáy mà không flush `BufferedWriter` bên trên, các ký tự chưa được đẩy xuống vẫn có thể bị giữ lại.

`BufferedWriter.newLine()` chỉ viết ký tự xuống dòng theo hệ thống; **không tự động flush**. `writer.write("\n")` cũng không tự bảo đảm flush. Muốn người tiêu thụ thấy dữ liệu sớm, gọi `writer.flush()` đúng thời điểm theo giao thức.

### 3.3. `PrintWriter` và auto-flush

`PrintWriter` có tùy chọn `autoFlush` khi tạo đối tượng, nhưng `autoFlush=true` **không có nghĩa** mọi `print(...)`, `write(...)`, hay mọi ký tự `'\n'` đều tự flush. Với `PrintWriter`, hành vi auto-flush được kích hoạt bởi các phương thức `println`, `printf`, `format`, theo hợp đồng lớp. Nếu giao thức cần chắc chắn đẩy byte sau một lệnh `print`, hãy flush tường minh.

Một khác biệt quan trọng: `PrintWriter` không truyền các `IOException` theo cách `BufferedWriter` thường làm, mà lưu trạng thái lỗi; có thể kiểm tra bằng `checkError()` (phương thức này cũng flush nếu stream còn mở). Không bỏ qua lỗi ghi khi độ chính xác dữ liệu quan trọng. `PrintStream` cũng có cơ chế xử lý lỗi riêng; không mặc định việc in thành công tức đã lưu trữ thành công.

## 4. Ví dụ Java 17: nhìn thấy hiệu quả của `flush()` trên bộ đệm phần mềm

Chương trình sau không dùng filesystem, nhờ đó đo chính xác việc byte còn trong `BufferedOutputStream` và đã đi đến đích bên dưới hay chưa.

Lưu **`BufferedFlushDemo.java`**:

```java
import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class BufferedFlushDemo {
    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream sink = new ByteArrayOutputStream();

        try (BufferedOutputStream buffered =
                 new BufferedOutputStream(sink, 8)) {
            buffered.write("ABC".getBytes(StandardCharsets.UTF_8));
            System.out.println("before flush: " + sink.size());

            buffered.flush();
            System.out.println("after flush: " + sink.size());

            buffered.write('D');
            System.out.println("after another write: " + sink.size());
        }

        System.out.println("after close: " +
            sink.toString(StandardCharsets.UTF_8));
    }
}
```

Chạy:

```bash
javac BufferedFlushDemo.java
java BufferedFlushDemo
```

Kết quả:

```text
before flush: 0
after flush: 3
after another write: 3
after close: ABCD
```

Giải thích theo thứ tự:

1. `BufferedOutputStream` được cấp buffer 8 byte; ghi `ABC` (3 byte) chưa làm đầy buffer nên `sink` vẫn có độ dài 0.
2. `buffered.flush()` chuyển `ABC` vào `ByteArrayOutputStream`, làm `sink.size() == 3`.
3. Ghi thêm `D` không bắt buộc đẩy ngay byte mới, vì buffer còn chỗ; `sink` vẫn có 3 byte.
4. Khi kết thúc try-with-resources, `close()` của `BufferedOutputStream` flush byte `D` đang chờ rồi đóng wrapper. `ByteArrayOutputStream` vẫn cho phép đọc nội dung trong bộ nhớ.

**Giới hạn chứng minh:** ví dụ chỉ xác nhận `flush()` đẩy byte từ một buffer Java sang `ByteArrayOutputStream`; không có file, kernel page cache hay đĩa nào ở đây, vì vậy không thể dùng ví dụ này làm phép đo durability.

## 5. Ví dụ: buffer ký tự cũng cần `flush()`

Lưu **`WriterFlushDemo.java`**:

```java
import java.io.BufferedWriter;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;

public class WriterFlushDemo {
    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream sink = new ByteArrayOutputStream();

        try (Writer writer = new BufferedWriter(
                new OutputStreamWriter(sink, StandardCharsets.UTF_8),
                64)) {
            writer.write("café");
            System.out.println("bytes before: " + sink.size());

            writer.flush();
            System.out.println("bytes after: " + sink.size());
            System.out.println("decoded: " +
                sink.toString(StandardCharsets.UTF_8));
        }
    }
}
```

Chạy:

```bash
javac WriterFlushDemo.java
java WriterFlushDemo
```

Kết quả:

```text
bytes before: 0
bytes after: 5
decoded: café
```

`BufferedWriter` ban đầu giữ bốn ký tự UTF-16 trong buffer của nó, nên `sink` chưa thấy gì. Sau khi flush, chuỗi được encode thành **5 byte UTF-8** (ba chữ ASCII và `é` dài hai byte). Gọi flush ở `BufferedWriter` ngoài cùng giúp ký tự đi qua `OutputStreamWriter` xuống sink.

Đây cũng là minh họa rằng một `Writer` còn phải xử lý **charset**; thao tác `flush()` đẩy dữ liệu đang chờ, nhưng không thay thế việc xác định đúng charset.

## 6. File I/O: đã flush ở Java vẫn có thể chỉ nằm trong page cache

Giả sử một ứng dụng ghi file trên hệ thống tệp thông thường. Với `FileOutputStream` hoặc `Files.newOutputStream`, khi byte được chuyển tới lời gọi ghi của hệ điều hành, dữ liệu có thể được lưu vào **page cache** trước khi được đẩy đến thiết bị. `flush()` của wrapper ở Java giải quyết buffer của wrapper; nó không tự bảo đảm OS đã flush tất cả dữ liệu file đến thiết bị.

Ngay cả khi bạn đóng stream và mở lại file để đọc thấy dữ liệu đúng, kết quả đó vẫn có thể đến từ cache hiện tại. **Đọc lại thành công là kiểm tra khả năng quan sát, không phải bài kiểm tra mất điện**.

### 6.1. `FileChannel.force(boolean metaData)`

`java.nio.channels.FileChannel.force(metaData)` yêu cầu cập nhật nội dung file lên thiết bị lưu trữ theo hợp đồng của channel. Với file nằm trên **thiết bị lưu trữ cục bộ**, API Java quy định các thay đổi phù hợp được buộc ghi xuống thiết bị; với thiết bị không cục bộ, mức bảo đảm có thể phụ thuộc hệ thống/provider.

- `force(false)`: yêu cầu force các thay đổi **nội dung file**; có thể vẫn force metadata tùy triển khai.
- `force(true)`: yêu cầu force cả **nội dung** và **metadata** file liên quan.
- Thao tác có thể ném `IOException` nếu việc force thất bại.
- Việc `force` thành công không tự tạo atomic transaction giữa nhiều file, không đồng bộ mọi thư mục liên quan theo một hợp đồng phổ quát và không bảo đảm storage từ xa cư xử giống storage cục bộ.
- Nếu dữ liệu được thay đổi qua cơ chế **khác channel này**, không nên giả định `channel.force(...)` sẽ bao trùm tất cả những thay đổi đó. Dùng cùng một channel cho ví dụ ghi/force là cách biểu đạt trách nhiệm rõ ràng hơn.

Một vấn đề hay gặp là gọi `force` **trước khi** `BufferedOutputStream.flush()`. Khi đó byte vẫn có thể ở mảng Java, chưa từng đi qua `FileChannel`; force không thể buộc xuống đĩa dữ liệu mà channel chưa nhận được.

### 6.2. Ví dụ Java 17: flush wrapper trước rồi force channel

Lưu **`FlushAndForceDemo.java`**. Chương trình tạo tệp tạm, ghi qua buffer, flush đến `FileChannel`, yêu cầu force và đọc lại dữ liệu để kiểm tra byte:

```java
import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.channels.Channels;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FlushAndForceDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("io-flush-", ".txt");

        try {
            try (FileChannel channel =
                     FileChannel.open(file, StandardOpenOption.WRITE);
                 OutputStream buffered = new BufferedOutputStream(
                     Channels.newOutputStream(channel), 8192)) {

                buffered.write("DATA\n".getBytes(StandardCharsets.UTF_8));

                buffered.flush();  // 1. Đẩy byte còn ở buffer Java
                channel.force(true); // 2. Yêu cầu force nội dung/metadata
            }

            System.out.print(
                Files.readString(file, StandardCharsets.UTF_8)
            );
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Chạy:

```bash
javac FlushAndForceDemo.java
java FlushAndForceDemo
```

Kết quả trên môi trường I/O bình thường:

```text
DATA
```

Ở đây `Channels.newOutputStream(channel)` chuyển `FileChannel` sang API `OutputStream`, rồi `BufferedOutputStream` cung cấp lớp đệm. Gọi `buffered.flush()` **trước** `channel.force(true)` để đảm bảo byte đã được gửi tới channel. Việc `Files.readString` thành công chỉ xác minh nội dung quan sát được; ví dụ **không thể chứng minh** hành vi sau crash/power loss, không phải benchmark hay bài kiểm tra vật lý thiết bị. Chương trình xóa file tạm để dọn tài nguyên; trong ứng dụng lưu dữ liệu thật, việc xóa và đồng bộ thư mục phải tuân theo quy trình riêng.

Một thay thế trong API `java.io` là **`FileDescriptor.sync()`**, ví dụ với `FileOutputStream.getFD().sync()`, sau khi đã flush wrapper đang chứa dữ liệu. Nó yêu cầu hệ thống đồng bộ các buffer của descriptor với thiết bị lưu trữ. Thứ tự vẫn quan trọng: nếu byte chưa tới file descriptor, sync ở bên dưới không thể đồng bộ những byte còn đọng trong buffer Java.

### 6.3. Các giới hạn của `force` và `sync`

`force`/`sync` mạnh hơn flush ở wrapper, nhưng cần hiểu chính xác phạm vi:

- File nằm trên filesystem mạng có thể có ngữ nghĩa, buffering và bảo đảm khác file local.
- Filesystem, kernel, thiết bị, controller cache và phần cứng/ảo hóa phải phối hợp mới tạo ra độ bền thực tế. Không phát biểu “100% chắc chắn” cho mọi tổ hợp thiết bị.
- `force` một file không tự bảo đảm **mọi thay đổi tên file hoặc directory entry** đã được đồng bộ. Việc tạo file, đổi tên và thay thế file liên quan tới metadata thư mục; thao tác sync directory không được Java NIO.2 cung cấp theo một giao diện portable áp dụng mọi hệ điều hành.
- `MappedByteBuffer` khi sửa vùng memory-mapped có cơ chế `force()` riêng; đừng giả định flush wrapper hoặc force trên một channel bất kỳ thay thế được thao tác phù hợp cho mapping.
- Một chuỗi thao tác “ghi A, ghi B” vẫn có thể dở dang sau crash, kể cả khi mỗi bước yêu cầu force riêng. **Durability không tự bằng atomicity**.

Khi nghiệp vụ đòi hỏi cam kết giao dịch, phục hồi sau crash, ghi nhiều bản ghi nhất quán hoặc thứ tự commit chặt chẽ, hãy dùng định dạng log/transaction protocol được thiết kế đúng hoặc cơ sở dữ liệu có bảo đảm đã được kiểm chứng trên hạ tầng đích.

## 7. `close()` khác `flush()`

**`flush()`** nhằm đẩy dữ liệu đang nằm trong buffer của các lớp ghi nhưng **giữ stream/writer mở** để viết tiếp. **`close()`** kết thúc vòng đời, giải phóng tài nguyên; với `BufferedOutputStream`, `BufferedWriter` và nhiều wrapper ghi khác, đóng cũng flush dữ liệu còn chờ.

```java
try (var writer =
         Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("first line");
    writer.newLine();
    writer.flush(); // Chỉ cần nếu muốn đẩy trước khi thoát scope
    writer.write("second line");
}
// close được gọi tự động khi rời try-with-resources
```

Đây là **đoạn minh họa**, biến `path` là `Path`; có import `Files`, `StandardCharsets`; phương thức xử lý `IOException`. Nếu chỉ cần đóng sau một lần ghi, thường **không cần flush ngay trước close** ở các lớp buffered writer chuẩn. Ngược lại, nếu muốn dữ liệu đi tiếp trước khi kết thúc scope, flush tường minh là hợp lý.

Lưu ý:

- `close()` có thể ném `IOException` trong lúc flush/đóng; dùng try-with-resources để không quên đóng và để Java xử lý suppressed exceptions hợp lý.
- Việc wrapper đóng có đóng tài nguyên underlying hay không phải theo **hợp đồng của wrapper cụ thể**. Với các wrapper chuẩn như `BufferedOutputStream`, thường đóng cả underlying stream. Không chia sẻ bừa cùng underlying stream cho nhiều owner có quyền close.
- Không thể dùng một `Writer` đã đóng để ghi tiếp; `flush()` không thay thế `close()` để giải phóng file descriptor.
- `Files.writeString(...)` kết thúc thao tác ghi không đồng nghĩa file đã được force xuống đĩa.

## 8. Network: `flush()` không phải ACK của ứng dụng bên nhận

Sơ đồ cho socket có buffer:

```text
Ứng dụng gửi
    ↓ buffered.write(message)
Bộ đệm Java
    ↓ buffered.flush()
SocketOutputStream / kernel send buffer
    ↓ TCP/network
Kernel nhận ở máy bên kia
    ↓ ứng dụng bên kia read()
Xử lý nghiệp vụ, ghi database, commit
    ↓ ứng dụng bên kia gửi ACK nghiệp vụ
Ứng dụng gửi nhận ACK và xác minh
```

Ở phía gửi, `buffered.flush()` có thể giúp byte rời khỏi Java buffer để được chuyển cho hệ thống mạng. **Nó không chứng minh bên kia đã `read()`, decode đúng giao thức, xử lý thành công, hay commit dữ liệu bền vững.** Ngay cả TCP ACK (nếu quan sát được ở tầng giao thức) chủ yếu xác nhận byte đến TCP stack phía nhận, không phải xác nhận thao tác nghiệp vụ đã hoàn thành.

Nếu một client gửi “thanh toán thành công” hoặc “lưu lệnh giao dịch”, để biết server thực sự xử lý thành công cần **phản hồi ở tầng ứng dụng** với định danh yêu cầu, trạng thái commit, idempotency/khả năng retry. Trên TCP, ranh giới `write()` và `read()` không tương ứng một message; cần framing (độ dài, delimiter với escaping đúng, hoặc protocol có cấu trúc).

Một số wrapper có buffer, một số socket stream không giữ buffer Java riêng. Vì vậy, `flush()` không phải lệnh “gửi gấp” phổ quát tới mọi mạng; nó phụ thuộc lớp nào đang giữ dữ liệu. Với giao thức tương tác, cân bằng batch/flush, kích thước message, độ trễ, backpressure và các tùy chọn socket thay vì flush sau mỗi byte.

## 9. `flush()` không bảo đảm thay thế file nguyên tử

Hãy xét cách cập nhật file cấu hình:

```text
Mở file cũ và truncate
→ Ghi nửa nội dung mới
→ Mất điện / tiến trình bị kill
→ File có thể rỗng, dang dở hoặc thiếu nhất quán
```

Gọi `flush()` sau mỗi đoạn **không giải quyết** việc một độc giả có thể thấy file bị ghi dở hoặc crash xảy ra giữa các đoạn. Một quy trình cập nhật file có yêu cầu an toàn hơn thường cần các bước thiết kế riêng:

1. Tạo **file tạm trong cùng thư mục/filesystem đích** và ghi toàn bộ nội dung mới vào file tạm; tránh đè trực tiếp nội dung đang phục vụ người đọc.
2. Flush tất cả Java buffer liên quan rồi force file tạm theo yêu cầu durability; xử lý `IOException`.
3. Sau khi nội dung tạm sẵn sàng, dùng `Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE, ...)` **khi filesystem/provider hỗ trợ**; có thể nhận `AtomicMoveNotSupportedException`. Ngữ nghĩa thay thế target đã tồn tại khi yêu cầu atomic move là provider-specific, không nên suy diễn `REPLACE_EXISTING` luôn có cùng hành vi trên mọi nền tảng.
4. Nếu nghiệp vụ yêu cầu crash durability của tên/đường dẫn, cần xác minh cơ chế đồng bộ **directory entry** và recovery trên OS/filesystem cụ thể. Java không cung cấp một quy trình portable hoàn chỉnh có cam kết chung cho tất cả filesystem.
5. Xác định chính sách fallback khi atomic rename không hỗ trợ; không âm thầm fallback sang thao tác không nguyên tử nếu yêu cầu bắt buộc atomicity.

Đây là **quy trình khái niệm**, không phải đoạn mã độc lập hay lời hứa rằng mọi filesystem/thiết bị đều cung cấp transaction. Nếu cập nhật nhiều file phải đồng bộ trạng thái cùng nhau, một lần rename file đơn lẻ vẫn không đủ; cân nhắc journal, manifest có version/commit marker hoặc database.

## 10. Chi phí và thời điểm nên gọi `flush()`

Flush quá ít có thể làm dữ liệu bị trễ trong buffer; flush quá thường xuyên có thể mất lợi ích batching, tăng lời gọi hệ thống hoặc tăng tương tác mạng. `force()`/sync thường đắt hơn vì yêu cầu đồng bộ sâu hơn.

| Bài toán | Khi nên flush | Có cần sync/force hoặc giao thức khác? |
|---|---|---|
| Ghi một file nhỏ rồi đóng | Thường close của wrapper là đủ để đẩy buffer Java | Nếu cần tồn tại sau crash, xem xét file force và quy trình commit |
| Ghi file lớn dạng streaming | Flush tại ranh giới thực sự cần quan sát, hoặc để buffer đầy tự xử lý | Tùy yêu cầu durability; không force mỗi byte |
| CLI/REPL in prompt | Flush sau prompt nếu không có newline hoặc stdout đang buffer | Không liên quan file durability |
| Protocol yêu cầu client/server trao đổi lệnh và phản hồi tức thì | Flush ở ranh giới message sau khi đã encode/framing đầy đủ | Cần application ACK để biết bên nhận xử lý |
| Ghi audit/trading/payment log | Flush Java buffer trước khi đánh dấu bản ghi đã xử lý | Thường cần cơ chế commit/durability xác định; cân nhắc database/log chuyên dụng |
| Viết `ByteArrayOutputStream` trực tiếp | Không có buffer ngoài nên flush thường không mang thêm ý nghĩa | Không có đĩa để sync |
| Dùng `BufferedOutputStream` bọc `ByteArrayOutputStream` | Flush để sink có byte còn đọng tại lớp bao | Không liên quan durability |
| Cập nhật file cấu hình không được phép dang dở | Flush file tạm và force theo yêu cầu | Cần atomic replace/recovery phù hợp filesystem |

Không nên biến “gọi `flush()` ở cuối mỗi `write()`” thành quy tắc máy móc. Hãy xác định **thời điểm người khác cần nhìn thấy dữ liệu** và **điểm nào được coi là commit bền vững**; hai nhu cầu này khác nhau.

## 11. Câu hỏi thường gặp

### `flush()` có ghi dữ liệu từ RAM xuống ổ cứng không?

Nó giúp đẩy dữ liệu đang chờ ở tầng buffer cụ thể (ví dụ `BufferedOutputStream`, `BufferedWriter`) xuống tầng tiếp theo. Tầng tiếp theo có thể là bộ nhớ, socket, file stream hoặc buffer khác. Nếu muốn yêu cầu hệ điều hành đồng bộ file lên thiết bị, dùng API như `FileChannel.force()` hay `FileDescriptor.sync()` đúng cách, trong phạm vi bảo đảm của hệ thống tệp.

### Gọi `flush()` rồi `Files.readString` đọc đúng có chứng minh bền vững không?

Không. Dữ liệu có thể đã vào page cache nên lệnh đọc thấy phiên bản mới; sau mất điện vẫn có thể mất nếu chưa đồng bộ. Readback là phép kiểm thử logic dữ liệu **ở trạng thái hiện tại**, không phải crash/power-loss test.

### Nếu dùng try-with-resources rồi thì có cần `flush()` trước `close()` không?

Với `BufferedOutputStream` và `BufferedWriter` chuẩn, thường không cần nếu mục tiêu chỉ là đẩy dữ liệu khi kết thúc scope, vì `close()` sẽ xử lý buffer. Có thể cần flush **sớm hơn**, trong khi đối tượng còn mở, nếu bên tiêu thụ cần nhận dữ liệu ngay. Không đồng nhất đóng stream với `fsync`.

### `FileChannel.force(true)` có làm file update trở thành atomic transaction không?

Không. Nó yêu cầu đồng bộ dữ liệu và metadata file theo hợp đồng; không tự bảo đảm chuyển đổi từ trạng thái cũ sang mới một cách nguyên tử, hoặc đồng bộ thư mục/tập hợp file. Atomicity cần cơ chế riêng.

### Gọi `flush()` dưới `BufferedWriter` có đủ không?

Không nhất thiết. Nếu ký tự còn nằm trong `BufferedWriter`, flush trực tiếp một `OutputStream` bên dưới không đẩy được ký tự chưa được `BufferedWriter` chuyển xuống. Flush lớp ghi ngoài cùng mà ứng dụng đã viết vào.

### `flush()` trên socket có báo server đã nhận yêu cầu thành công không?

Không. Nó có thể đẩy byte tới tầng socket/hệ điều hành ở phía gửi; cần protocol và phản hồi ứng dụng để xác nhận server đã xử lý/commit.

### `PrintWriter(autoFlush=true)` có tự flush mỗi lần `print()` không?

Không. Với `PrintWriter`, auto-flush gắn với `println`, `printf` và `format` (không phải mọi `print`/`write`). Nếu cần đẩy sau `print`, gọi `flush()` tường minh; để phát hiện lỗi, dùng `checkError()` hoặc lựa chọn Writer có cơ chế exception rõ ràng.

## 12. Tự kiểm tra

1. **Một `BufferedOutputStream` chứa 20 byte chưa flush. Ứng dụng gọi `FileChannel.force(true)` lên channel bên dưới. 20 byte có chắc đã force không?**  
   **Không.** Nếu còn nằm trong buffer Java, chúng chưa đến channel. Cần flush wrapper trước, rồi force đúng channel.
2. **Một ứng dụng vừa flush file, mở lại đọc được nội dung. Điều gì đã được xác minh?**  
   Khả năng quan sát nội dung trong trạng thái hiện tại; chưa chứng minh dữ liệu sống sót sau crash.
3. **Khi nào `close()` khác `flush()`?**  
   Flush đẩy buffer để tiếp tục dùng stream; close kết thúc vòng đời và giải phóng tài nguyên. Với nhiều buffered writer/stream chuẩn, close cũng flush buffer.
4. **Đâu là khác biệt giữa `FileChannel.force(false)` và `force(true)`?**  
   `false` yêu cầu force nội dung; `true` yêu cầu force nội dung và metadata file. Hành vi chi tiết phụ thuộc provider và hạ tầng.
5. **Sau khi `socketOutputStream.flush()`, có thể trả “thanh toán thành công” chưa?**  
   Chưa. Phải chờ phản hồi nghiệp vụ xác nhận server xử lý và commit thành công.
6. **File cần cập nhật nguyên tử có đủ bằng `flush()` và `force()` không?**  
   Chưa. Cần cơ chế xuất bản trạng thái mới nguyên tử, chẳng hạn file tạm và atomic move khi được hỗ trợ, cùng thiết kế đồng bộ metadata/recovery theo môi trường.

**Ghi nhớ:** `flush()` xử lý **bộ đệm phần mềm trong đường ghi**; `force()`/`sync()` xử lý yêu cầu **đồng bộ file xuống lưu trữ** ở mức được hệ thống hỗ trợ; atomic rename/transaction giải quyết **tính nguyên tử**, còn application ACK xác nhận **xử lý phía nhận**. Bốn nhu cầu này phải được thiết kế và kiểm chứng riêng.
