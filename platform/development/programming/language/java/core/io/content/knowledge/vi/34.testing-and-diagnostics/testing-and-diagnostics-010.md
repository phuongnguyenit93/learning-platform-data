# Chẩn đoán dữ liệu chưa flush, file handle còn mở và buffer sai trạng thái trong Java IO/NIO.2

Một ứng dụng có thể gọi `write()` mà file vẫn rỗng; file không xóa hoặc đổi tên được vì tài nguyên còn mở; hoặc `FileChannel` ghi ra 0 byte dù `ByteBuffer` đã có dữ liệu. Ba triệu chứng này thường bị gộp chung thành “IO chưa ghi xong”, nhưng chúng đến từ **ba lớp trạng thái khác nhau**:

1. **Bộ đệm đầu ra chưa flush**: dữ liệu còn nằm trong `BufferedWriter`, `BufferedOutputStream` hoặc tầng mã hóa ký tự, chưa được chuyển hết xuống tầng IO bên dưới.
2. **Tài nguyên hệ điều hành chưa close**: `InputStream`, `OutputStream`, `Reader`, `Writer`, `FileChannel`, `DirectoryStream` hoặc `Stream` dựa trên tệp còn giữ tài nguyên; có thể tích lũy file descriptor/handle hoặc file lock.
3. **`Buffer` sai `position`/`limit`**: dữ liệu đã có trong vùng nhớ nhưng API NIO không còn byte “remaining” để đọc/ghi, hoặc dữ liệu cũ bị ghi lặp/lẫn với dữ liệu chưa hợp lệ.

Để sửa đúng, trước hết phải xác định dữ liệu đã đi qua những tầng nào, tài nguyên do ai sở hữu, và trạng thái của buffer tại thời điểm gọi API.

## 1. Chuỗi truyền dữ liệu: write, flush, close và độ bền trên đĩa

Một đường ghi phổ biến có các tầng:

```text
Dữ liệu ứng dụng
   └─ BufferedWriter (buffer ký tự)
        └─ OutputStreamWriter (mã hóa ký tự thành byte)
             └─ BufferedOutputStream (buffer byte, nếu có)
                  └─ FileOutputStream / FileChannel
                       └─ bộ đệm của hệ điều hành / filesystem
                            └─ thiết bị lưu trữ
```

Không phải chương trình nào cũng có đầy đủ mọi tầng. Ví dụ `Files.newBufferedWriter(path, UTF_8)` trả về một writer có buffering; `Files.writeString` là API ghi tiện ích, không để lại writer cho code gọi tự đóng.

| Hành động | Điều được bảo đảm trong phạm vi hợp đồng thông thường | Điều **không** được bảo đảm |
| --- | --- | --- |
| `writer.write(...)` | Đẩy dữ liệu vào trạng thái của writer; có thể vẫn chỉ nằm trong bộ đệm | File lập tức quan sát được toàn bộ dữ liệu |
| `writer.flush()` | Yêu cầu đẩy dữ liệu đang buffer xuống destination bên dưới, và flush các tầng writer/stream trong chuỗi theo hợp đồng | Byte đã được lưu bền vững trên thiết bị vật lý |
| `writer.close()` | Với writer chuẩn như `BufferedWriter`, flush trước khi close và giải phóng tài nguyên; có thể ném lỗi IO | Một giao dịch nghiệp vụ hoàn tất hay file được `fsync` tuyệt đối |
| `FileChannel.force(true)` | Yêu cầu buộc thay đổi nội dung và metadata qua channel xuống thiết bị theo bảo đảm cụ thể của provider | Biến mọi filesystem, NFS/remote mount, hardware cache thành giao dịch bền vững |
| `FileDescriptor.sync()` | Yêu cầu hệ điều hành đồng bộ dữ liệu liên quan tới descriptor | Thay thế cho việc flush bộ đệm ở tầng Java còn chưa chuyển byte xuống descriptor |

**Phân biệt ba câu hỏi:** “Đã `write`?” khác “Đã `flush` xuống hệ điều hành?” và khác “Đã `force/sync` để giảm nguy cơ mất dữ liệu do crash?”. Nếu writer còn giữ ký tự trong RAM, gọi `force` trên file channel bên dưới mà chưa flush writer **không thể đồng bộ các byte chưa đến channel**.

Với xử lý file thông thường, `try-with-resources` và việc kiểm tra exception từ close thường đủ để đảm bảo dữ liệu ở tầng Java được xả và tài nguyên được giải phóng. Với yêu cầu độ bền cao (nhật ký giao dịch, checkpoint), cần thêm hợp đồng đồng bộ cụ thể, file tạm, đổi tên đúng cách và kiểm tra hỗ trợ của filesystem.

## 2. Dấu hiệu của dữ liệu chưa được flush

Các tình huống quen thuộc:

- Gọi `write("hello")` vào `BufferedWriter`, sau đó một tiến trình khác đọc file và chưa thấy `"hello"`. Writer có thể vẫn giữ chuỗi đó trong buffer.
- Dùng `PrintWriter.print(...)` và chờ dữ liệu xuất hiện ngay. Cờ `autoFlush=true` của `PrintWriter` tự flush khi gọi `println`, `printf` hoặc `format`, **không** phải sau mọi `print`/`write`.
- Có nhiều tầng buffering nhưng chỉ xử lý một tầng thủ công không đúng chủ sở hữu. Trong thiết kế bình thường, flush ở **wrapper ngoài cùng** cho dữ liệu đi xuống các tầng bên dưới.
- Tiến trình kết thúc bất thường trước khi đóng writer. `try-with-resources` xử lý luồng điều khiển Java thông thường và exception, nhưng không chạy khi tiến trình bị kill ngay lập tức hoặc JVM/crash ở cấp hệ điều hành.
- Ghi dữ liệu sau khi đã log “saved” nhưng thực tế đoạn code ghi/flush/close có thể ném exception. Nên chỉ công bố thành công sau khi toàn bộ đường ghi trả về bình thường.

Mẫu đúng:

```java
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("report.txt");
try (BufferedWriter writer =
         Files.newBufferedWriter(file, StandardCharsets.UTF_8)) {
    writer.write("hello");
    writer.newLine();
    writer.flush(); // Chỉ cần nếu phải thấy dữ liệu trước khi đóng.
} // close sẽ flush và đóng trong đường thực thi bình thường.
```

Đoạn trên là **mã minh họa trong một phương thức**; thiếu lớp và `main`. Nếu không có nhu cầu quan sát file trước khi đóng, thường không cần gọi `flush()` thủ công ngay trước `close()`. Nhưng nếu output là một giao thức tương tác như socket, phải flush tại các điểm cần gửi phản hồi, không đợi đóng kết nối.

**Không dùng `Thread.sleep(...)` làm giải pháp flush.** Chờ đợi không cam kết `BufferedWriter` tự xả bộ đệm. Cũng không nên dùng `flush` sau *mỗi byte* khi ghi file lớn, vì nhiều syscall nhỏ làm giảm hiệu năng.

### PrintWriter che giấu lỗi IO

Khác nhiều writer, `PrintWriter` không ném `IOException` trực tiếp từ các lệnh ghi thường dùng; `checkError()` cung cấp trạng thái lỗi và có thể flush nếu stream chưa đóng. Vì vậy việc gọi `println` mà không có exception **không đủ** để kết luận file đã ghi thành công. Với code cần báo lỗi rõ ràng, ưu tiên `BufferedWriter` hoặc API có exception minh bạch; nếu dùng `PrintWriter`, kiểm tra lỗi tại điểm kết thúc thích hợp.

## 3. File handle còn mở: ai có trách nhiệm close?

“File handle” trên Windows và “file descriptor” trên Unix-like là tài nguyên hệ điều hành. Một đối tượng Java giữ stream/channel mở có thể tiếp tục giữ tài nguyên này, trực tiếp hoặc qua wrapper. Những biểu hiện phổ biến:

- `Too many open files` / `EMFILE` khi mở nhiều tài nguyên mà không đóng, đặc biệt trong server xử lý liên tục.
- Trên Windows, `AccessDeniedException`, lỗi move/delete hoặc ứng dụng khác không đổi tên được file khi một process còn giữ handle có chế độ chia sẻ không phù hợp. Trên Unix, thường có thể unlink tên file đang mở; dữ liệu/tài nguyên vẫn tồn tại cho tới khi handle cuối đóng. Hành vi cụ thể phụ thuộc filesystem và quyền OS.
- File lock giữ lâu hơn cần thiết, worker khác không lấy được lock hoặc thao tác cần quyền độc quyền bị chặn.
- Sau một số request, bộ đếm descriptor tăng theo thời gian; một restart tạm “chữa” triệu chứng rồi lỗi lặp lại.

**Nguyên tắc sở hữu:** nơi tạo stream/channel thường chịu trách nhiệm đóng nó. Trả một stream ra khỏi hàm mà không định nghĩa caller phải đóng là nguồn gây leak. Nếu API trả một `Stream<String>` đọc file lazily, cần dùng try-with-resources tại nơi thực sự tiêu thụ.

Ví dụ đọc file và tự đóng nguồn:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = Path.of("events.log");
try (Stream<String> lines =
         Files.lines(path, StandardCharsets.UTF_8)) {
    long errors = lines.filter(line -> line.contains("ERROR")).count();
    System.out.println(errors);
}
```

Đây là **đoạn trong phương thức `throws IOException` hoặc tự xử lý lỗi**, không phải chương trình Java độc lập. `Files.lines`, `Files.list`, `Files.walk` và `Files.find` có thể giữ nguồn filesystem mở; cần đóng `Stream` trả về. Lệnh terminal `cat` hay `grep` không kiểm soát vòng đời của Java stream.

Với channel hoặc khóa file, dùng đúng kiểu close:

```java
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

try (FileChannel channel = FileChannel.open(
         Path.of("state.bin"), StandardOpenOption.CREATE,
         StandardOpenOption.READ, StandardOpenOption.WRITE);
     FileLock lock = channel.lock()) {
    // Tác vụ cần khóa, thực hiện trong phạm vi try này.
} // Khóa được giải phóng, sau đó channel được đóng (đảo thứ tự tạo).
```

Đây là đoạn minh họa. `FileLock` còn phụ thuộc khả năng hỗ trợ/semantics của OS và filesystem. Việc đóng một wrapper có thể đóng luôn stream/channel bên dưới; đừng dùng tiếp tài nguyên ấy sau khi wrapper sở hữu nó đã close. Ngược lại, `ByteArrayOutputStream` là buffer trong RAM, không mở file descriptor; không nên đánh đồng mọi `close()` với thao tác giải phóng file.

### Cách tìm file descriptor bị leak

| Môi trường | Công cụ quan sát hữu ích | Lưu ý |
| --- | --- | --- |
| Linux | `lsof -p <PID>`; `ls -l /proc/<PID>/fd` | `lsof` có thể cần cài riêng/quyền phù hợp; đường dẫn `/proc` có thể bị hạn chế trong container |
| Windows | Resource Monitor → CPU → Associated Handles; Sysinternals Process Explorer/Handle | Tìm theo tên file/process, chú ý việc chia sẻ handle và quyền truy cập |
| JVM trên Unix | `com.sun.management.UnixOperatingSystemMXBean.getOpenFileDescriptorCount()` | API mở rộng phụ thuộc nền tảng; chỉ cho **tổng số**, không chỉ ra file nào leak |
| Trong ứng dụng | Metric số lượng descriptor/handle; log đường dẫn, vị trí tạo, sự kiện close; stress test lặp lại | Không log toàn bộ tên file nhạy cảm, thông tin user hay nội dung file vào hệ thống giám sát công khai |

Với leak, hãy quan sát **xu hướng dưới tải rồi sau khi workload hoàn tất**. Con số đang tăng trong lúc có nhiều kết nối hoạt động chưa chắc là leak; đáng nghi khi vẫn tăng sau mỗi vòng tải tương đương và không quay về baseline phù hợp.

Đừng suy từ một JVM thread dump rằng mọi file đang mở đã được phát hiện: thread dump cho biết stack/thread, không liệt kê đầy đủ descriptor. GC hay `System.gc()` cũng **không phải** cơ chế giải phóng file handle đáng tin cậy; hãy close rõ ràng.

## 4. ByteBuffer: capacity, position, limit và remaining

`ByteBuffer` là buffer có trạng thái. Bốn con số quan trọng:

- `capacity`: dung lượng cố định tính theo byte.
- `position`: chỉ số của phần tử kế tiếp sẽ đọc hoặc ghi theo thao tác tương đối.
- `limit`: ranh giới *exclusive* của phần còn được phép đọc/ghi.
- `remaining() = limit - position`: số byte các phương thức tương đối còn có thể xử lý.

Bất biến là `0 <= position <= limit <= capacity`.

Ví dụ `ByteBuffer.allocate(8)` sau khi ghi các byte `A B C` bằng `put`:

```text
Index:       0  1  2  3  4  5  6  7
Bytes:       A  B  C  ?  ?  ?  ?  ?
State:       position=3, limit=8, capacity=8
```

Dấu `?` tượng trưng phần không thuộc dữ liệu hợp lệ của ví dụ. Sau `flip()`:

```text
Index:       0  1  2  3  4  5  6  7
Bytes:       A  B  C  ?  ?  ?  ?  ?
State:       position=0, limit=3, capacity=8
Remaining:   A  B  C
```

Nếu gọi `FileChannel.write(buffer)` **trước `flip`**, channel sẽ đọc từ `position=3` đến `limit=8`, tức không phải 3 byte vừa đưa vào. Một trường hợp khác, nếu buffer đã `position==limit`, `write` có thể trả 0 vì `!hasRemaining()`, dù mảng bên trong vẫn giữ dữ liệu cũ.

### Bốn phép chuyển trạng thái cần nhớ

| API | Thay đổi trạng thái | Dùng lúc nào | Hiểu sai thường gặp |
| --- | --- | --- | --- |
| `flip()` | `limit = position; position = 0` | Kết thúc **ghi dữ liệu vào buffer**, chuẩn bị đọc từ buffer | Không gọi trước ghi channel; hoặc gọi hai lần khiến limit thành 0 |
| `clear()` | `position = 0; limit = capacity` | Chuẩn bị ghi đè buffer khi dữ liệu cũ đã được xử lý hết | **Không xóa byte vật lý**; làm mất dấu vùng dữ liệu còn chờ đọc |
| `rewind()` | `position = 0`, giữ `limit` | Đọc lại cùng vùng byte hợp lệ | Nhầm với `clear` và đọc cả byte không hợp lệ |
| `compact()` | Chuyển byte còn `remaining` về đầu; position đặt sau chúng; limit về capacity | Đã tiêu thụ **một phần**, giữ byte chưa xử lý để nhận thêm | Nhầm với clear làm mất dữ liệu chưa dùng |

`mark/reset` cũng là trạng thái; các thao tác `flip/clear/rewind/compact` thường hủy mark theo hợp đồng của `Buffer`. Khi debug, in `position`, `limit`, `capacity` và `remaining()` trước/sau mỗi lần channel read/write sẽ nhanh hơn việc chỉ in địa chỉ của buffer.

**`buffer.array()` không đồng nghĩa với “dữ liệu hợp lệ trong buffer”.** Với heap buffer, nó có thể bao gồm byte đã dùng, byte trống hoặc byte không nằm giữa `position`/`limit`; với direct/read-only buffer có thể không truy cập được backing array. Để đọc đúng phần còn lại, dùng `byte[] result = new byte[buffer.remaining()]; buffer.get(result);` hoặc dùng view `slice()` theo nhu cầu.

## 5. Ví dụ Java 17+ có stdout xác định

Ví dụ dùng một file text có `BufferedWriter` và một file nhị phân có `ByteBuffer/FileChannel`. Tệp được tạo trong thư mục tạm để không phụ thuộc tên file bên ngoài. Không có tác vụ cùng lúc thay đổi chúng.

Tạo `IoDiagnosticsDemo.java`:

```java
import java.io.BufferedWriter;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class IoDiagnosticsDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("io-diagnostics-");
        Path text = dir.resolve("notes.txt");

        // 1) Xả bộ đệm, đọc lại trong khi writer vẫn mở.
        try (BufferedWriter writer =
                Files.newBufferedWriter(text, StandardCharsets.UTF_8)) {
            writer.write("hello");
            writer.flush();
            System.out.println("after flush="
                    + Files.readString(text, StandardCharsets.UTF_8));
        }
        System.out.println("after close="
                + Files.readString(text, StandardCharsets.UTF_8));

        // 2) Chuyển ByteBuffer từ chế độ put sang channel.write.
        Path binary = dir.resolve("data.bin");
        try (FileChannel out = FileChannel.open(binary,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE)) {
            ByteBuffer buffer = ByteBuffer.allocate(8);
            buffer.put("ABC".getBytes(StandardCharsets.UTF_8));

            System.out.printf("before flip: pos=%d limit=%d%n",
                    buffer.position(), buffer.limit());
            buffer.flip();
            System.out.printf("after flip: pos=%d limit=%d%n",
                    buffer.position(), buffer.limit());

            while (buffer.hasRemaining()) {
                out.write(buffer);
            }
        }
        System.out.println("saved="
                + Files.readString(binary, StandardCharsets.UTF_8));

        // 3) Chiều ngược lại: channel.read rồi flip mới get.
        try (FileChannel in = FileChannel.open(binary,
                StandardOpenOption.READ)) {
            ByteBuffer buffer = ByteBuffer.allocate(8);
            int count = in.read(buffer);
            System.out.printf("after read: n=%d pos=%d limit=%d%n",
                    count, buffer.position(), buffer.limit());

            buffer.flip();
            byte[] result = new byte[buffer.remaining()];
            buffer.get(result);
            System.out.println("decoded="
                    + new String(result, StandardCharsets.UTF_8));
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 IoDiagnosticsDemo.java
java IoDiagnosticsDemo
```

Stdout trên JDK 17+ khi chạy với filesystem thông thường, không có tác vụ khác can thiệp:

```text
after flush=hello
after close=hello
before flip: pos=3 limit=8
after flip: pos=0 limit=3
saved=ABC
after read: n=3 pos=3 limit=8
decoded=ABC
```

Mỗi `try-with-resources` quản lý tài nguyên cụ thể, đồng thời làm lộ lỗi close thành exception nếu có. Lệnh `flush()` ở ví dụ cho phép kiểm tra `notes.txt` **trước khi writer đóng**; không phải yêu cầu phải flush hai lần ở mọi chương trình.

File `data.bin` có đúng ba byte `ABC` vì `flip` giới hạn vùng được write thành `[0,3)`; vòng `while (buffer.hasRemaining())` xử lý khả năng channel ghi ít hơn số byte remaining trong một lần gọi. Với nonblocking channel, nếu `write` trả 0 lặp lại, phải dùng `Selector` hoặc chiến lược chờ phù hợp, không spin vô hạn; ví dụ này dùng `FileChannel` mở để ghi file thông thường.

## 6. Quy trình debug khi file rỗng, thiếu byte hoặc dữ liệu xuất hiện muộn

Khi gặp một file “đã write nhưng chưa có dữ liệu”, nên kiểm tra theo thứ tự sau:

1. **Đúng file và đúng đường dẫn?** In/log đường dẫn đã chuẩn hóa và nơi chạy thực tế (working directory, file path, mount/container). Nhầm file tương đối là nguyên nhân rất thường gặp. Không đưa đường dẫn nhạy cảm vào log công khai.
2. **Mở file bằng option nào?** `TRUNCATE_EXISTING` xóa nội dung cũ; `APPEND` thêm vào cuối; `CREATE_NEW` từ chối ghi đè file tồn tại. Nếu thread khác mở file với truncate, có thể thấy file trống dù writer trước đã thành công.
3. **Có wrapper buffer không?** `BufferedWriter`, `BufferedOutputStream`, `OutputStreamWriter` có thể giữ dữ liệu; flush/close đúng lớp sở hữu. Dùng phép đọc lại chỉ *sau flush* để xác minh visibility, không kết luận từ kích thước đọc được khi buffer chưa xả.
4. **Exception có bị nuốt không?** Kiểm tra `IOException` ở write, flush, close; với `PrintWriter`, chú ý `checkError()`.
5. **ByteBuffer có còn remaining không?** Ghi log `position/limit/capacity`, `n=channel.write(buffer)` và cập nhật sau mỗi lần gọi. Phân biệt byte count trả về với số byte đã intended.
6. **Có gọi force/sync theo yêu cầu durability không?** Chỉ xét sau khi Java buffer đã flush; nhớ `force` và `flush` giải quyết hai tầng khác nhau.
7. **Ai còn ghi vào file?** Đồng bộ các worker, không cho phép đối tượng khác thay dữ liệu giữa kiểm tra và đọc lại. Tránh khẳng định “flush thất bại” khi nguyên nhân là race hoặc ứng dụng đang đọc file khác.

Thay vì ghi `System.out.println("saved")` ngay sau khi đưa dữ liệu vào buffer, hãy quan sát các mốc `write completed`, `flush completed`, `close completed`, `file published` theo nhu cầu. Không ghi log từng byte trong hot path production; dùng metric/các điểm trace khi tái hiện lỗi.

## 7. Quy trình debug khi file handle tăng liên tục

Một kịch bản rò rỉ:

```java
// Sai: mỗi lần gọi đều mở một Stream từ filesystem nhưng không close.
long countErrors(Path file) throws java.io.IOException {
    return java.nio.file.Files.lines(file)
            .filter(s -> s.contains("ERROR"))
            .count();
}
```

Vì `Files.lines` trả lazy Stream, việc `count()` kết thúc **không tự động gọi `close()` cho stream**. Sửa:

```java
long countErrors(Path file) throws java.io.IOException {
    try (java.util.stream.Stream<String> lines =
            java.nio.file.Files.lines(file)) {
        return lines.filter(s -> s.contains("ERROR")).count();
    }
}
```

Đây là hai **phương thức minh họa độc lập** đặt bên trong lớp, không biên dịch như một file chứa cả hai phương thức cùng chữ ký. Trong dự án thật, chỉ giữ phiên bản đã sửa.

Cách tái hiện/leak-test:

1. Đo số descriptor/handle trước khi chạy một vòng workload có đủ request tương đương.
2. Chạy lặp những nhánh **thành công, exception, cancellation, timeout**. Chính nhánh lỗi thường bỏ qua `close()` nếu code đóng thủ công cuối phương thức.
3. Sau khi workload dừng, so sánh baseline, liệt kê handle/path bằng công cụ OS rồi đối chiếu code tạo stream/channel/reader/writer.
4. Chuyển về `try-with-resources`; nếu nhiều resource, khai báo tài nguyên theo đúng thứ tự sở hữu. Đảm bảo các nhánh `return`, `throw` đều đóng đúng tài nguyên.
5. Chạy lại cùng workload; xác nhận số descriptor không tăng vô hạn và các thao tác file move/delete/lock cần thiết hoạt động bình thường.

Nếu tài nguyên được chuyển cho caller hoặc một async job, phải chuyển rõ ownership và bảo đảm close **sau khi** task hoàn thành. Đóng channel quá sớm trong khi worker còn IO có thể gây `ClosedChannelException` hoặc `AsynchronousCloseException`; đóng quá muộn lại giữ handle không cần thiết. Hủy `Future` không chứng minh IO đã dừng tức thời.

## 8. Các lỗi ByteBuffer thường gặp và phép thử

### Quên flip trước khi ghi ra channel

```java
ByteBuffer buffer = ByteBuffer.allocate(8);
buffer.put(new byte[] {65, 66, 67});
// Sai: chưa flip; remaining là 5, không phải 3 byte "ABC".
channel.write(buffer);
```

Đoạn minh họa nằm trong phương thức có `WritableByteChannel channel`. Sửa bằng `buffer.flip()` trước khi chuyển sang đọc dữ liệu từ buffer. Khi dùng `ByteBuffer.wrap(byte[])`, vị trí ban đầu là 0 và limit bằng độ dài mảng, nên **không gọi flip vô điều kiện** ngay sau `wrap` nếu chưa có thao tác `put`; nếu không có thể biến limit thành 0.

### Quên flip sau channel.read

```java
ByteBuffer dst = ByteBuffer.allocate(1024);
int n = channel.read(dst);
if (n > 0) {
    dst.flip();
    // Xử lý chính xác dst.remaining() byte, không phải capacity.
}
```

Nếu quên `flip`, lời gọi `get` có thể đọc phần chưa được điền hoặc không đọc được vùng vừa nhận, tùy `position/limit`. Nếu đọc tới cuối stream, `read()` thường trả `-1`; với channel không blocking, `0` có thể có nghĩa tạm chưa có dữ liệu, **không** phải EOF.

### Dùng clear dù vẫn còn frame chưa xử lý

Trong parser protocol, một lần `read` có thể chỉ nhận nửa thông điệp. Sau khi `flip` và tiêu thụ các frame hoàn chỉnh, dùng `compact()` để dồn byte của frame chưa đủ về đầu buffer rồi đọc thêm:

```java
// Mã minh họa trong vòng xử lý protocol, không phải main độc lập.
buffer.flip();
consumeCompleteFrames(buffer); // Nâng position qua những byte đã xử lý.
buffer.compact();              // Giữ byte còn lại để lần đọc tiếp tục.
```

Nếu dùng `clear()` ở đây, dữ liệu còn lại bị xem như không tồn tại dù byte vật lý có thể vẫn nằm trong mảng. Nếu dùng `rewind()` sau khi đã xử lý nửa buffer, phần đầu đã xử lý có thể bị tiêu thụ lại.

### Shared buffer giữa nhiều luồng

`ByteBuffer` không thread-safe cho việc cùng thay đổi `position/limit` trên một instance. Nếu nhiều worker cùng thao tác relative `get/put` vào một buffer, có thể mất byte/đảo thứ tự dù `FileChannel` có hỗ trợ dùng giữa nhiều luồng. Dùng buffer riêng theo task, hoặc đồng bộ và chia slice rõ ràng; đừng chia sẻ một `ByteBuffer` mutable mà không quy định ownership.

### Partial write và trạng thái sau ghi

`FileChannel.write(buffer)` trả số byte thực sự ghi. Chỉ đóng/công bố file khi buffer không còn remaining hoặc có xử lý lỗi thích hợp. `write` không làm buffer tự `clear` hay tự `flip`; nó tăng `position` theo số byte đã chuyển. Với thao tác ghi file có nhiều buffer, cần xem cả số byte ghi thực tế và vị trí ghi tệp, tránh dùng `buffer.array().length` như số byte đã xuất.

## 9. Kiểm thử và chẩn đoán tự động

Nên xây test riêng cho ba lớp vấn đề để biết lỗi thuộc về đâu.

| Tình huống test | Bằng chứng cần có | Lỗi được phát hiện |
| --- | --- | --- |
| Ghi vài ký tự vào `BufferedWriter`, gọi `flush`, đọc ngay khi writer còn mở | Nội dung đọc lại đúng | Thiếu flush ở điểm cần visibility |
| Kết thúc `try-with-resources` rồi đọc lại | Dữ liệu đầy đủ; exception close được xử lý | Quên close/nuốt lỗi cuối đường ghi |
| Thao tác nhiều lần lên `Files.lines`, `Files.walk`, `FileChannel` | Descriptor không tăng mất kiểm soát sau workload | Leak tài nguyên |
| Chạy nhánh exception, cancellation, early return | Tài nguyên vẫn được đóng, không còn file lock vô ý | Chỉ đóng ở happy path |
| `ByteBuffer.put` → `flip` → ghi channel | Số byte ghi bằng số byte hợp lệ | Sai position/limit |
| Đọc file bằng buffer nhỏ hơn file | Lặp đọc cho tới EOF, không mất byte | Giả định một lần read lấy hết dữ liệu |
| Parser nhận nửa frame ở một lần đọc | `compact` giữ byte chưa tiêu thụ | Mất frame ở biên buffer |
| Output có yêu cầu bền vững khi crash | Trình tự flush → force/sync → commit được định nghĩa và đo kiểm theo filesystem | Nhầm visibility với durability |

**Không dùng test “file size vẫn bằng 0 ngay sau write chưa flush” làm bảo đảm tuyệt đối**: tùy kích thước dữ liệu, buffer và implementation, writer có thể tự flush khi đầy. Test nên chứng minh kết quả sau explicit flush/close, không đòi hỏi dữ liệu trước flush luôn vô hình.

Với unit test parser, có thể dùng `ByteBuffer.allocate(4)` để ép chia frame qua nhiều lần đọc. Với integration test resource, dùng tệp tạm và đo descriptor ở nơi có thể; tránh dựa duy nhất vào việc xóa file thành công trên Unix vì file còn mở có thể vẫn unlink được.

## 10. Phân biệt ba loại triệu chứng trong thực tế

| Triệu chứng | Khả năng cần kiểm tra đầu tiên | Hướng xử lý |
| --- | --- | --- |
| File rỗng trong khi writer còn mở, nhưng đúng sau close | Buffered output chưa flush | Flush tại ranh giới cần visibility |
| File đúng sau flush nhưng không sống sót qua sự cố điện/OS | Thiếu yêu cầu durability hoặc giới hạn filesystem/storage | Xem `FileChannel.force`/`FileDescriptor.sync` và protocol lưu bền vững |
| `Too many open files` | Stream/channel không close; worker ownership không rõ | Try-with-resources, kiểm tra nhánh lỗi, đo descriptor |
| Trên Windows không rename/delete được file | Handle/lock còn mở hoặc quyền chia sẻ/OS | Tìm process giữ handle; đảm bảo close/giải phóng lock |
| NIO `write` ghi 0 byte | `!buffer.hasRemaining()` hoặc nonblocking output chưa writable | In `position/limit`, kiểm tra channel và readiness |
| File chứa byte rác hoặc số byte sai | Thiếu flip, dùng cả `array()` hoặc không xử lý partial write | Giữ state buffer và lặp ghi đúng |
| Parser thiếu dữ liệu ở cuối block | Dùng clear thay vì compact, xử lý từng khối như frame độc lập | Giữ byte pending, kiểm thử split input |
| File đúng một lần nhưng sai dưới tải | Đọc/ghi đồng thời không điều phối, shared mutable buffer, close sai thời điểm | Tách buffer theo task, khóa/sắp thứ tự, quy định ownership |

## 11. Checklist áp dụng khi review code IO

1. Tìm tất cả nơi mở tài nguyên: `Files.newBufferedWriter`, `Files.newInputStream`, `FileChannel.open`, `Files.lines/list/walk/find`, `ZipFile`, `RandomAccessFile`. Xác định ai close trên mọi đường đi.
2. Với output có buffer, xác định **khi nào bên ngoài được phép nhìn thấy dữ liệu**. Nếu trước close, đặt flush có chủ đích; nếu cần durability, thiết kế bước force/sync sau khi dữ liệu đã xuống tầng file.
3. Không tuyên bố success trước khi thao tác ghi và đóng/commit hoàn thành; thu thập lỗi write/flush/close. Với `PrintWriter`, kiểm tra `checkError()` hoặc dùng API báo exception.
4. Với NIO, ghi rõ trạng thái buffer trước/sau `put/read/flip/write/clear/compact`. Dùng `remaining` cho byte hợp lệ, lặp khi channel có partial read/write.
5. Đặt thử nghiệm chạy lặp và nhánh lỗi để bắt handle leak; test trên nền tảng sẽ triển khai, đặc biệt nếu kết quả phụ thuộc Windows file sharing, filesystem từ xa hoặc lưu trữ đám mây.
6. Giữ resource scope tối thiểu: không giữ channel/stream xuyên qua lời gọi mạng hay task bất đồng bộ không cần thiết. Với worker bất đồng bộ, không đóng nguồn khi công việc còn cần dùng.

Điều cần nhớ: **`flush` xử lý byte đang đệm ở lớp Java; `close` kết thúc quyền sở hữu tài nguyên; `ByteBuffer.flip/clear/compact` xử lý trạng thái vị trí đọc/ghi; `force/sync` giải quyết yêu cầu đồng bộ xuống storage.** Chúng không thay thế nhau.

### Tài liệu tham khảo chính thức

- Java SE 17 `BufferedWriter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html
- Java SE 17 `Writer` và `OutputStream` (flush/close): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Writer.html
- Java SE 17 `ByteBuffer` / `Buffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17 `FileChannel` (write/force/close): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html
- Java SE 17 `Files` (resource management): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html