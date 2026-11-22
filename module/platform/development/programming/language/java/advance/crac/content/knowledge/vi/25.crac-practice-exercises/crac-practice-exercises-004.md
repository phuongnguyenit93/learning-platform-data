# Đóng và mở lại tệp với vị trí đọc ghi được kiểm chứng

Khi một ứng dụng Java dùng CRaC, tiến trình có thể được checkpoint rồi restore sau một khoảng thời gian. Nếu ứng dụng đang đọc hoặc ghi tệp, không nên chỉ giữ một `FileChannel` hay `RandomAccessFile` trong heap và giả định file descriptor cùng vị trí đọc/ghi vẫn dùng được sau restore. Một quy trình rõ ràng cần ghi nhận offset, hoàn tất I/O đang chạy, flush dữ liệu cần thiết, đóng tệp trước checkpoint, sau đó mở lại tệp và xác minh cả nội dung lẫn vị trí trước khi tiếp tục.

Bài thực hành này dùng `FileChannel` để ghi hai bản ghi UTF-8, đóng tệp, mở lại, đọc và kiểm tra offset, tiếp tục ghi tại vị trí đã lưu, rồi mở lần nữa để xác nhận dữ liệu. Phần sau tích hợp quy trình đó với CRaC `Resource` và giải thích các giới hạn khi tệp bị thay đổi trong lúc process tạm dừng.

## 1. Vị trí đọc/ghi là offset theo byte

`FileChannel.position()` trả về vị trí hiện tại tính bằng byte kể từ đầu tệp. `FileChannel.position(long)` đặt vị trí tiếp theo cho thao tác đọc/ghi tuần tự trên channel. `RandomAccessFile.getFilePointer()` và `seek(long)` cũng làm việc với offset byte.

Điều này đặc biệt quan trọng với UTF-8. Một ký tự tiếng Việt có thể chiếm nhiều byte. Số ký tự trong chuỗi Java không nhất thiết bằng số byte được ghi vào tệp.

Ví dụ:

```java
String text = "Xin chào CRaC";
int javaChars = text.length();
int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length;

System.out.println("String.length=" + javaChars);
System.out.println("UTF-8 bytes=" + utf8Bytes);
```

Không dùng `String.length()` làm offset để seek trong một tệp UTF-8. Hãy lưu đúng số byte đã đọc/ghi hoặc dùng một định dạng record có framing và offset được xác định rõ.

## 2. Phân biệt vị trí của channel và offset do ứng dụng quản lý

Một `FileChannel` có một vị trí hiện tại. Sau một lần `read(ByteBuffer)` hoặc `write(ByteBuffer)` tuần tự, vị trí này được cập nhật. Khi đóng channel, vị trí hiện tại không còn nằm trong một channel đang mở; khi mở lại, channel mới bắt đầu với vị trí mặc định theo API (thường là byte 0), vì vậy ứng dụng phải seek lại.

Có hai cách làm việc:

| Cách | API | Ảnh hưởng tới `channel.position()` |
| --- | --- | --- |
| I/O tuần tự | `read(buffer)`, `write(buffer)`, `position(offset)` | Đọc/ghi cập nhật vị trí hiện tại. |
| I/O tại offset tường minh | `read(buffer, offset)`, `write(buffer, offset)` | Không thay đổi vị trí hiện tại của channel. Ứng dụng tự quản lý offset. |

Nếu chỉ có một luồng đọc/ghi, dùng vị trí hiện tại có thể đơn giản. Nếu có nhiều luồng hoặc cần giữ cursor đọc và cursor ghi độc lập, positional I/O thường dễ kiểm soát hơn; vẫn cần đồng bộ nếu nhiều thao tác ghi có thể đè lên cùng vùng byte.

Không nên để nhiều thread cùng thay đổi `channel.position()` mà không có lock. Một thread có thể seek trong lúc thread khác đang đọc, khiến thao tác tiếp theo bắt đầu ở offset không mong muốn.

## 3. Chuẩn bị tệp thực hành

Ví dụ dưới đây dùng một tệp nhị phân có nội dung UTF-8. Ta ghi bản ghi đầu tiên, lưu offset cuối, đóng channel, mở lại và xác minh dữ liệu trước khi ghi bản ghi thứ hai.

Tạo project Java thông thường, rồi thêm class sau. Ví dụ dùng Java 11 trở lên và không cần thư viện ngoài:

```java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;

public final class FilePositionDemo {

    private static void writeFully(FileChannel channel, ByteBuffer source)
            throws IOException {
        while (source.hasRemaining()) {
            int written = channel.write(source);
            if (written == 0) {
                Thread.yield();
            }
        }
    }

    private static void readFully(FileChannel channel, ByteBuffer target)
            throws IOException {
        while (target.hasRemaining()) {
            int read = channel.read(target);
            if (read < 0) {
                throw new EOFException("File ended before the buffer was full");
            }
            if (read == 0) {
                Thread.yield();
            }
        }
    }

    private static void requirePosition(long actual, long expected, String label) {
        if (actual != expected) {
            throw new IllegalStateException(
                    label + ": expected=" + expected + ", actual=" + actual);
        }
    }

    public static void main(String[] args) throws IOException {
        Path file = Path.of("build", "file-position-demo.bin");
        Files.createDirectories(file.getParent());

        byte[] firstRecord = "id=1;message=Đã lưu trước checkpoint\n"
                .getBytes(StandardCharsets.UTF_8);
        byte[] secondRecord = "id=2;message=Tiếp tục sau khi mở lại\n"
                .getBytes(StandardCharsets.UTF_8);

        long savedWritePosition;

        // Lần mở thứ nhất: tạo tệp và ghi bản ghi đầu tiên.
        try (FileChannel channel = FileChannel.open(
                file,
                StandardOpenOption.CREATE,
                StandardOpenOption.TRUNCATE_EXISTING,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {

            channel.position(0);
            writeFully(channel, ByteBuffer.wrap(firstRecord));

            savedWritePosition = channel.position();
            requirePosition(savedWritePosition, firstRecord.length,
                    "write position after first record");

            // Đẩy nội dung và metadata tệp theo khả năng của hệ điều hành/storage.
            channel.force(true);
        }

        // Lần mở thứ hai: đọc lại dữ liệu cũ, xác minh cursor rồi ghi tiếp.
        try (FileChannel channel = FileChannel.open(
                file,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {

            channel.position(0);
            ByteBuffer firstRead = ByteBuffer.allocate(firstRecord.length);
            readFully(channel, firstRead);

            if (!Arrays.equals(firstRecord, firstRead.array())) {
                throw new IllegalStateException("First record content mismatch");
            }

            requirePosition(channel.position(), savedWritePosition,
                    "read position after first record");

            // Seek về offset đã lưu trước khi đóng channel.
            channel.position(savedWritePosition);
            requirePosition(channel.position(), savedWritePosition,
                    "reopened write position");

            writeFully(channel, ByteBuffer.wrap(secondRecord));
            channel.force(true);

            long expectedEnd = savedWritePosition + secondRecord.length;
            requirePosition(channel.position(), expectedEnd,
                    "write position after second record");
        }

        // Lần mở thứ ba: xác minh bản ghi thứ hai bắt đầu đúng offset đã lưu.
        try (FileChannel channel = FileChannel.open(
                file, StandardOpenOption.READ)) {

            channel.position(savedWritePosition);
            ByteBuffer secondRead = ByteBuffer.allocate(secondRecord.length);
            readFully(channel, secondRead);

            if (!Arrays.equals(secondRecord, secondRead.array())) {
                throw new IllegalStateException("Second record content mismatch");
            }

            long expectedEnd = savedWritePosition + secondRecord.length;
            requirePosition(channel.position(), expectedEnd,
                    "read position after second record");
        }

        System.out.println("File: " + file.toAbsolutePath());
        System.out.println("Saved write position: " + savedWritePosition + " bytes");
        System.out.println("Final file size: " + Files.size(file) + " bytes");
        System.out.println("Read/write positions and record contents verified.");
    }
}
```

Chương trình cố ý dùng `readFully` và `writeFully`. Một lần đọc/ghi trên channel không được đảm bảo luôn xử lý hết toàn bộ `ByteBuffer`; code phải lặp cho tới khi buffer hết dữ liệu. Khi đọc tới EOF trước khi buffer đầy, ví dụ ném `EOFException` thay vì âm thầm coi dữ liệu thiếu là hợp lệ.

`force(true)` yêu cầu channel ghi các thay đổi nội dung và metadata tệp tới storage theo khả năng của hệ điều hành và thiết bị. Nó không thay thế transaction database, không bảo đảm mọi filesystem/network storage có cùng semantics, và không tự làm cho một file rename ở thư mục cha trở nên bền vững trên mọi nền tảng.

## 4. Chạy và quan sát kết quả

Biên dịch và chạy class:

```bash
javac FilePositionDemo.java
java FilePositionDemo
```

Kết quả gồm đường dẫn tệp, offset sau bản ghi đầu tiên, kích thước cuối và thông báo xác minh thành công. Các con số offset được tính theo byte UTF-8; vì chuỗi có dấu tiếng Việt, chúng có thể lớn hơn số ký tự hiển thị.

Có thể kiểm tra file bằng lệnh hệ điều hành:

```bash
cat build/file-position-demo.bin
wc -c build/file-position-demo.bin
```

Lệnh `cat` chỉ phù hợp vì ví dụ ghi text UTF-8 vào file. Trong ứng dụng production, không dùng lệnh hiển thị toàn bộ file nếu nó có thể chứa dữ liệu nhạy cảm.

## 5. Tại sao phải kiểm chứng cả vị trí lẫn nội dung?

Chỉ gọi `channel.position(savedOffset)` rồi đọc lại giá trị `channel.position()` chứng minh channel đã nhận offset, nhưng chưa chứng minh offset đó trỏ tới đúng dữ liệu mong muốn.

Ví dụ, file có thể bị truncate, thay bằng file khác, chèn thêm byte hoặc thay đổi nội dung trong lúc ứng dụng đóng. Khi đó:

- Offset vẫn nằm trong phạm vi file nhưng trỏ tới record khác.
- Kích thước file vẫn bằng cũ nhưng nội dung đã bị thay thế.
- Offset ở giữa một record hoặc giữa một chuỗi UTF-8.
- File path trỏ tới một inode khác sau khi file được rotate/replace.

Vì vậy, khi mở lại cần kiểm tra ít nhất:

1. File tồn tại và có quyền đọc/ghi phù hợp.
2. Kích thước file phù hợp với policy.
3. Offset không âm và không vượt quá giới hạn hợp lệ.
4. Offset phù hợp ranh giới record nếu file có record framing.
5. Header, generation id, record id hoặc checksum tại vùng liên quan khớp với metadata đã lưu.
6. Sau khi seek, đọc thử một record/marker và xác minh trước khi tiếp tục ghi hoặc xử lý.

Đối với file do một tiến trình duy nhất quản lý, có thể yêu cầu kích thước không đổi giữa lúc đóng và mở lại. Nếu một writer bên ngoài được phép append, cần định nghĩa rõ high-water mark và xác minh prefix; không áp dụng điều kiện `size == expectedSize` một cách máy móc.

## 6. Dùng `RandomAccessFile` để kiểm tra file pointer

`RandomAccessFile` là API đơn giản khác để thao tác tại offset. `seek(long)` đặt file pointer và `getFilePointer()` trả vị trí hiện tại tính theo byte.

```java
import java.io.RandomAccessFile;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

byte[] payload = "record-10: dữ liệu mẫu\n".getBytes(StandardCharsets.UTF_8);
long savedPosition;

try (RandomAccessFile file = new RandomAccessFile("records.dat", "rw")) {
    file.seek(0);
    file.write(payload);
    savedPosition = file.getFilePointer();
    file.getFD().sync();
}

try (RandomAccessFile file = new RandomAccessFile("records.dat", "rw")) {
    file.seek(0);
    byte[] actual = new byte[payload.length];
    file.readFully(actual);

    if (!Arrays.equals(payload, actual)) {
        throw new IllegalStateException("Content mismatch");
    }

    file.seek(savedPosition);
    if (file.getFilePointer() != savedPosition) {
        throw new IllegalStateException("File pointer mismatch");
    }

    file.write("record-11: tiếp tục\n".getBytes(StandardCharsets.UTF_8));
    file.getFD().sync();
}
```

Chế độ `"rw"` mở file để đọc/ghi và không tự truncate nội dung cũ. Nếu muốn ghi lại từ đầu, cần chủ động truncate bằng `setLength(0)` hoặc dùng `FileChannel` với `TRUNCATE_EXISTING`. Không nhầm `seek(0)` với truncate: seek chỉ di chuyển con trỏ, không xóa dữ liệu.

`RandomAccessFile` tiện cho bài thực hành tuần tự. `FileChannel` linh hoạt hơn khi cần positional I/O, `ByteBuffer`, file locking hoặc tích hợp với NIO.

## 7. Tích hợp với CRaC: lưu offset, flush và đóng trước checkpoint

Khi checkpoint, object Java có thể được giữ trong heap, nhưng file descriptor/channel cần được quản lý theo lifecycle. Một cách đơn giản là lưu offset vào field của `Resource`, force dữ liệu nếu ứng dụng vừa ghi, rồi đóng channel trong `beforeCheckpoint`. Sau restore, mở lại file, kiểm tra kích thước/marker và seek về offset đã lưu.

Ví dụ dưới đây minh họa phần cốt lõi. Các thao tác `stopAcceptingFileWork()` và `awaitInFlightFileWork()` thuộc coordinator của ứng dụng; chúng phải ngăn thao tác mới và drain I/O đang chạy trước khi lưu cursor.

```java
import org.crac.Context;
import org.crac.Resource;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;

public final class ReopenableFileResource implements Resource {
    private static final int ANCHOR_BYTES = 16;

    private final Path path;
    private FileChannel channel;
    private long savedPosition;
    private long expectedSize;
    private byte[] anchor = new byte[0];
    private boolean accepting = true;

    public ReopenableFileResource(Path path) throws IOException {
        this.path = path;
        this.channel = FileChannel.open(
                path, StandardOpenOption.READ, StandardOpenOption.WRITE);
        this.expectedSize = channel.size();
        this.savedPosition = channel.position();
        this.anchor = captureAnchor(channel, savedPosition);
    }

    public synchronized void seek(long byteOffset) throws IOException {
        ensureOpen();
        if (byteOffset < 0 || byteOffset > channel.size()) {
            throw new IllegalArgumentException("Offset outside file bounds");
        }
        channel.position(byteOffset);
    }

    public synchronized long position() throws IOException {
        ensureOpen();
        return channel.position();
    }

    @Override
    public synchronized void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        accepting = false;
        try {
            stopAcceptingFileWork();
            awaitInFlightFileWork();

            if (channel == null || !channel.isOpen()) {
                throw new IOException("File channel is not open");
            }
            savedPosition = channel.position();
            expectedSize = channel.size();
            anchor = captureAnchor(channel, savedPosition);

            channel.force(true);
            channel.close();
            channel = null;
        } catch (Exception e) {
            if (channel != null && channel.isOpen()) {
                accepting = true;
            }
            throw e;
        }
    }

    @Override
    public synchronized void afterRestore(Context<? extends Resource> context)
            throws Exception {
        reopenAndVerify();
        accepting = true;
        resumeFileWork();
    }

    // Dùng nếu checkpoint attempt bị abort sau khi beforeCheckpoint đã đóng file.
    // Đây là đường rollback của ứng dụng, không phải CRaC afterRestore.
    public synchronized void resumeAfterAbortedCheckpoint() throws IOException {
        if (channel == null || !channel.isOpen()) {
            reopenAndVerify();
        }
        accepting = true;
        resumeFileWork();
    }

    private void reopenAndVerify() throws IOException {
        FileChannel reopened = FileChannel.open(
                path, StandardOpenOption.READ, StandardOpenOption.WRITE);
        try {
            long actualSize = reopened.size();
            if (actualSize != expectedSize) {
                throw new IOException("File size changed while channel was closed: expected="
                        + expectedSize + ", actual=" + actualSize);
            }

            if (savedPosition < 0 || savedPosition > actualSize) {
                throw new IOException("Saved position is outside the reopened file");
            }

            byte[] actualAnchor = captureAnchor(reopened, savedPosition);
            if (!Arrays.equals(anchor, actualAnchor)) {
                throw new IOException("File content near saved position changed");
            }

            reopened.position(savedPosition);
            if (reopened.position() != savedPosition) {
                throw new IOException("Could not restore the saved file position");
            }

            channel = reopened;
        } catch (IOException | RuntimeException e) {
            reopened.close();
            throw e;
        }
    }

    private static byte[] captureAnchor(FileChannel channel, long position)
            throws IOException {
        int length = (int) Math.min(ANCHOR_BYTES, position);
        ByteBuffer buffer = ByteBuffer.allocate(length);
        long start = position - length;
        while (buffer.hasRemaining()) {
            int count = channel.read(buffer, start);
            if (count < 0) {
                throw new IOException("Unexpected EOF while reading anchor");
            }
            if (count == 0) {
                Thread.yield();
            } else {
                start += count;
            }
        }
        return buffer.array();
    }

    private void ensureOpen() throws IOException {
        if (!accepting || channel == null || !channel.isOpen()) {
            throw new IOException("File operations are paused or the channel is closed");
        }
    }

    private void stopAcceptingFileWork() {
        // Notify the application coordinator to reject new file operations.
    }

    private void awaitInFlightFileWork() {
        // Wait with a bounded deadline using a coordinator that does not need
        // this object's monitor. All file I/O must pass through this ownership boundary.
    }

    private void resumeFileWork() {
        // Allow file operations only after reopen and verification succeed.
    }
}
```

Đây là skeleton lifecycle, trong đó ba method coordinator cần được nối với cơ chế quản lý worker thực tế của ứng dụng. `synchronized` ngăn các method của object chạy đồng thời trong lúc callback giữ monitor, nhưng không tự dừng các thread khác đang thao tác trực tiếp lên channel hoặc file; mọi I/O phải đi qua cùng ownership boundary.

Anchor chỉ kiểm tra 16 byte ngay trước cursor. Nó giúp phát hiện một số trường hợp file bị thay đổi nhưng không chứng minh toàn bộ file giống hệt. Trong production, nên dùng file generation id/header, record sequence, immutable file identity hoặc checksum của vùng dữ liệu cần bảo vệ. `BasicFileAttributes.fileKey()` có thể hữu ích như tín hiệu bổ sung nhưng không được mọi filesystem hỗ trợ và không phải định danh portable qua host/restore.

Ví dụ yêu cầu `actualSize == expectedSize` vì giả định file chỉ do resource này quản lý trong khoảng checkpoint. Nếu một process khác được phép append trong thời gian đó, hãy dùng high-water mark và xác minh prefix theo policy thay vì áp dụng điều kiện kích thước bằng tuyệt đối.

## 8. Đăng ký Resource và trigger checkpoint

Sau khi tạo resource, đăng ký nó với CRaC global context theo API của runtime:

```java
ReopenableFileResource resource =
        new ReopenableFileResource(Path.of("data", "records.bin"));

Core.getGlobalContext().register(resource);
```

Ứng dụng cần import `org.crac.Core` và dùng đúng dependency CRaC được JDK/runtime hỗ trợ. Việc đăng ký phải xảy ra một lần trong lifecycle phù hợp; tránh tạo nhiều Resource cùng quản lý một file/channel.

Khi checkpoint được yêu cầu, CRaC gọi `beforeCheckpoint`; sau khi process được restore, runtime gọi `afterRestore`. Có thể trigger bằng API hoặc command được JDK CRaC cung cấp. Cú pháp và semantics cụ thể phụ thuộc distribution/version. Không giả định việc gọi callback thủ công tương đương với một lần checkpoint/restore thực tế.

Sau `afterRestore`, chỉ resume worker đọc/ghi khi `reopenAndVerify()` thành công. Nếu file không còn đúng, báo lỗi và giữ component không sẵn sàng thay vì tiếp tục ghi ở offset không chắc chắn.

## 9. Vì sao phải drain I/O trước khi lưu vị trí?

Nếu callback đọc `channel.position()` trong lúc một thread khác đang ghi, offset được lưu có thể không phản ánh ranh giới record mà ứng dụng mong muốn. Nếu buffer ứng dụng còn dữ liệu chưa ghi, `channel.position()` có thể phản ánh số byte đã đưa vào channel nhưng chưa phản ánh dữ liệu logic còn trong buffer.

Trước khi checkpoint:

1. Ngừng nhận công việc file mới.
2. Chờ các thao tác đọc/ghi hiện tại hoàn tất.
3. Flush `BufferedOutputStream`, writer hoặc buffer ứng dụng nếu có.
4. Gọi `FileChannel.force(true)` nếu cần yêu cầu dữ liệu và metadata tệp được đẩy xuống storage.
5. Lưu offset sau khi mọi buffer đã được xử lý.
6. Đóng channel.

Không lấy offset từ `FileChannel` rồi bỏ qua buffer ở tầng cao hơn. Ví dụ `BufferedWriter` có thể đang giữ ký tự chưa được ghi xuống channel; cursor của channel sẽ thấp hơn vị trí logic của writer.

Nếu ứng dụng có nhiều writer, cần một coordinator/lock bao quanh toàn bộ thao tác drain, flush, capture cursor và close. Không chỉ khóa riêng dòng `channel.position()`.

## 10. BufferedReader và vị trí đọc trước (read-ahead)

Một lỗi thường gặp là dùng `BufferedReader` để đọc text rồi lấy vị trí `FileChannel.position()` làm offset của dòng vừa đọc. `BufferedReader` và các decoder có thể đọc trước nhiều byte vào buffer nội bộ. Vị trí channel lúc đó có thể vượt qua cuối dòng logic mà ứng dụng vừa nhận.

Ví dụ:

```text
File bytes:  [line 1][line 2][line 3][line 4]
Application: đọc xong line 1
BufferedReader: có thể đã nạp line 2 và một phần line 3
FileChannel position: có thể nằm sau line 1
```

Nếu checkpoint lưu channel position, sau restore ứng dụng có thể bỏ qua phần dữ liệu đã được read-ahead nhưng chưa được xử lý.

Các cách giải quyết:

- Dùng `FileChannel` và parser byte-level có quản lý offset rõ ràng.
- Dùng record framing có độ dài xác định hoặc delimiter được xử lý ở tầng byte.
- Tự lưu logical cursor do parser quản lý, không lấy vị trí channel khi có buffer read-ahead.
- Nếu dùng `BufferedReader`, cần một cơ chế wrapper theo dõi offset logic đã tiêu thụ; không suy ra offset từ channel bên dưới.

Với UTF-8, delimiter newline là byte `0x0A`, nhưng nội dung ký tự có thể gồm nhiều byte. Parser cần xử lý trường hợp buffer kết thúc giữa một chuỗi mã hóa nhiều byte. Dùng `CharsetDecoder` đúng cách hoặc framing byte rõ ràng; không cắt chuỗi tùy ý theo chỉ số ký tự.

## 11. Partial read/write và kiểm tra EOF

Không được giả định một lệnh `read` hay `write` xử lý hết buffer. API NIO cho phép đọc/ghi ít byte hơn số byte còn lại. Điều này đặc biệt quan trọng khi dùng channel không blocking, network channel hoặc thao tác file với môi trường đặc biệt.

Quy tắc:

- Dùng vòng lặp cho tới khi `ByteBuffer.hasRemaining()` trả false.
- Khi đọc trả `-1`, xử lý EOF; nếu đang chờ một record đầy đủ thì đây là dữ liệu bị truncate.
- Khi đọc trả `0`, không tăng offset; chờ hoặc retry theo policy phù hợp.
- Chỉ cập nhật logical cursor sau khi toàn bộ record đã được đọc/ghi thành công.
- Nếu write lỗi giữa record, không đánh dấu record hoàn tất; khi khởi động lại cần kiểm tra/truncate partial tail theo định dạng file.

Với regular file channel blocking, thao tác thường tiến triển, nhưng code tổng quát vẫn nên xử lý partial I/O. Không dùng `channel.size()` thay cho việc kiểm tra record đầy đủ.

## 12. Lưu cursor trong heap hay file metadata?

Nếu mục tiêu là restore đúng process image, field trong object `Resource` có thể được giữ trong heap và khôi phục cùng process. Ví dụ `savedPosition` trong skeleton là một field như vậy.

Nếu cần tiếp tục sau cold restart không dùng checkpoint, hoặc cần phục hồi khi checkpoint artifact bị mất, offset phải được lưu trong metadata bền vững riêng. Có thể lưu:

- File generation id hoặc file identity logic.
- Read offset và write offset.
- File size/high-water mark.
- Last processed record id/sequence.
- Checksum/anchor của vùng dữ liệu quanh cursor.
- Version của định dạng file.

Metadata nên được ghi theo cách tránh trạng thái nửa chừng: ghi file tạm, force nội dung, rồi atomic move trong cùng filesystem nếu provider hỗ trợ. Nếu atomic move không được hỗ trợ, cần thiết kế recovery marker hoặc storage transaction phù hợp.

Offset chỉ có ý nghĩa khi đi kèm file generation/version. Nếu file bị rotate hoặc thay bằng file mới, offset cũ không được tự động áp dụng lên file mới dù kích thước giống nhau.

## 13. Xử lý file bị thay đổi trong lúc checkpoint

Ứng dụng phải định nghĩa ai sở hữu file trong thời gian process bị checkpoint.

| Tình huống | Cách xử lý |
| --- | --- |
| Không có writer nào khác và file bất biến | Kiểm tra kích thước, generation/header và anchor; yêu cầu kích thước khớp. |
| File chỉ được append bởi một writer khác | Lưu high-water mark; xác minh prefix đến high-water mark; quyết định có đọc phần append mới hay không. |
| File bị rotate/replaced | Dùng generation id hoặc file identity; không dùng offset cũ trên file mới. |
| File bị truncate | Phát hiện `size < savedPosition` hoặc checksum/record validation thất bại; dừng xử lý. |
| Nội dung bị sửa nhưng kích thước không đổi | Kiểm tra record id/version hoặc checksum; size alone không đủ. |
| File nằm trên network filesystem | Xác nhận semantics cache/locking/rename/force của filesystem và kiểm thử trên đúng mount. |

Nếu file được quản lý bởi một dịch vụ khác, nên dùng protocol/lease để xác nhận file generation và high-water mark. Không dựa vào việc path vẫn tồn tại.

## 14. Ghi append và tránh ghi đè dữ liệu

Để tiếp tục ghi từ cuối file, có thể lấy `size()` rồi seek tới đó, nhưng chỉ an toàn khi quyền ghi được điều phối. Nếu writer khác append đồng thời giữa lúc đọc size và lúc write, hai writer có thể cùng chọn một offset và ghi đè nhau.

Với một writer duy nhất:

```java
long end = channel.size();
channel.position(end);
writeFully(channel, ByteBuffer.wrap(recordBytes));
```

Với nhiều writer, dùng một cơ chế serialization/locking phù hợp, hoặc dùng positional writes vào vùng đã cấp phát riêng. `FileLock` trong Java có thể hỗ trợ phối hợp giữa process trên một số filesystem, nhưng lock thường mang tính advisory và semantics phụ thuộc hệ điều hành/filesystem. Nó không thay thế distributed lock hay protocol của storage.

Không mặc định `StandardOpenOption.APPEND` kết hợp với `position()` cho mọi provider sẽ tạo hành vi seek-and-overwrite mong muốn. Nếu cần ghi ở offset cụ thể, mở channel `READ`/`WRITE` rồi dùng offset tường minh và quản lý concurrency rõ ràng.

## 15. Ghi file an toàn khi cập nhật metadata

Nếu offset được lưu trong sidecar, tránh ghi đè file metadata tại chỗ rồi để lại nội dung một phần khi process bị dừng. Một mẫu phổ biến:

1. Ghi toàn bộ metadata vào file tạm cùng filesystem.
2. Gọi `force(true)` trên file tạm.
3. Đóng file.
4. Dùng `Files.move(temp, target, ATOMIC_MOVE, REPLACE_EXISTING)` nếu filesystem hỗ trợ.
5. Nếu `AtomicMoveNotSupportedException` xảy ra, dùng một chiến lược recovery có version/marker thay vì giả định move vẫn atomic.

Atomic rename giúp người đọc không thấy file metadata nửa chừng trong điều kiện filesystem hỗ trợ. Nó không tự bảo đảm directory entry được flush bền vững qua mọi sự cố mất điện; durability cuối cùng phụ thuộc filesystem và storage.

## 16. Lỗi và rollback khi checkpoint thất bại

Một tình huống quan trọng: `beforeCheckpoint` đã đóng file nhưng thao tác dump thất bại. Process ban đầu có thể tiếp tục mà không chạy `afterRestore`.

Do đó cần một đường rollback/resume riêng:

- Coordinator biết Resource nào đã đóng.
- Nếu checkpoint abort, gọi phương thức resume dành cho process gốc.
- Reopen file, xác minh generation/size/anchor và seek lại cursor.
- Chỉ resume worker sau khi xác minh thành công.
- Nếu không thể reopen an toàn, giữ component `NOT_READY` và báo lỗi.

Không dùng `afterRestore` như callback rollback cho checkpoint thất bại. `afterRestore` thuộc luồng restore; nó không được bảo đảm chạy khi checkpoint attempt bị abort.

Nếu file bị thay đổi trong lúc checkpoint abort, không tự động ghi tiếp ở offset cũ. Cần reconcile với file owner hoặc phục hồi từ metadata/backup theo policy.

## 17. File locking và nhiều process

Nếu nhiều process cùng truy cập file, cần xác định semantics đồng bộ. `FileChannel.lock()` có thể khóa vùng hoặc toàn file tùy overload; `tryLock()` cho phép kiểm tra không block vô hạn. Nhưng:

- File lock có thể là advisory; process khác không tuân thủ lock vẫn có thể ghi.
- Hành vi phụ thuộc OS và filesystem.
- Lock object không nên được coi là hợp lệ xuyên qua checkpoint nếu channel đã đóng.
- Sau restore, cần mở channel mới và lấy lock mới.
- Không giữ lock trong lúc chờ checkpoint nếu điều đó làm các process khác deadlock hoặc timeout.

Một quy trình an toàn là dừng nhận work, drain thao tác, release lock, checkpoint; sau restore mở file, kiểm tra generation và reacquire lock trước khi tiếp tục. Nếu file được chia sẻ qua nhiều host, dùng locking/coordination được storage hỗ trợ thay vì giả định local `FileLock` cung cấp distributed mutual exclusion.

## 18. Quyền truy cập, symbolic link và đường dẫn

Sau restore, file path có thể trỏ tới vị trí khác nếu mount namespace hoặc volume mapping thay đổi. Kiểm tra:

- Đường dẫn được resolve trong đúng mount namespace/container.
- User/UID/GID của process có quyền đọc/ghi.
- File không bị thay bằng symbolic link trỏ ra ngoài thư mục dự kiến.
- Parent directory có quyền truy cập phù hợp.
- Volume đã mount và sẵn sàng trước khi `afterRestore` mở file.
- File không bị cleanup job xóa hoặc rotate ngoài ý muốn.

Nếu đường dẫn đến từ input bên ngoài, canonicalize và kiểm tra nó nằm trong vùng dữ liệu được phép. Đừng mở một path tùy ý từ metadata checkpoint mà không xác thực.

## 19. Kiểm thử các trường hợp biên

Ngoài luồng thành công, hãy thử:

- File rỗng, offset 0.
- Offset đúng EOF.
- Offset âm hoặc lớn hơn file size.
- File bị truncate trước khi reopen.
- File được thay bằng file khác cùng kích thước.
- Byte cuối của record bị thiếu.
- Ghi chỉ hoàn tất một phần record rồi lỗi.
- UTF-8 character bị chia giữa hai buffer.
- BufferedReader đọc trước qua nhiều dòng.
- Hai thread cùng seek/read/write.
- Hai process cùng append.
- Permission thay đổi sau restore.
- Mount/volume chưa sẵn sàng.
- Checkpoint abort sau khi channel đã đóng.
- Restore lặp lại từ cùng artifact.

Kiểm tra cả nội dung và vị trí. Một offset hợp lệ về số học nhưng trỏ sai record vẫn là lỗi.

## 20. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Hướng xử lý |
| --- | --- | --- |
| Sau khi mở lại, đọc từ đầu file | Channel mới chưa được seek | Khôi phục offset đã lưu rồi xác minh `position()`. |
| Bỏ qua một phần dữ liệu | Offset được tính theo ký tự thay vì byte, hoặc BufferedReader read-ahead | Lưu byte offset logic ở parser/framing layer. |
| Ghi đè bản ghi cũ | Offset write cũ hoặc hai writer cùng dùng một vị trí | Kiểm tra high-water mark và đồng bộ writer. |
| Đọc thiếu record | Giả định một lần `read()` lấp đầy buffer | Dùng vòng lặp `readFully` và phát hiện EOF. |
| File size đúng nhưng nội dung sai | File bị thay hoặc sửa cùng kích thước | Kiểm tra generation id, record sequence hoặc checksum. |
| File bị mất dữ liệu sau checkpoint | Chưa flush buffer ứng dụng hoặc chưa force theo policy | Drain, flush tầng cao, `force(true)` và xác nhận storage semantics. |
| Resource không mở lại sau restore | Volume chưa mount, permission đổi hoặc path sai | Validate mount/identity/permission trước khi resume. |
| Process gốc không hoạt động sau checkpoint abort | Channel đã đóng nhưng không có rollback path | Gọi resume coordinator riêng; không chờ `afterRestore`. |
| Lock không còn sau restore | Lock gắn với channel/descriptor cũ | Mở channel mới và reacquire lock. |

## 21. Checklist thực hành

- [ ] Dùng offset theo byte, không dùng `String.length()` cho file UTF-8.
- [ ] Ghi nhận offset sau khi thao tác hoàn tất, không giữa một record.
- [ ] Dùng `readFully`/`writeFully` để xử lý partial I/O.
- [ ] Phân biệt channel position với offset tường minh của ứng dụng.
- [ ] Drain worker và flush buffer trước khi capture cursor.
- [ ] Gọi `force(true)` khi durability của nội dung/metadata tệp yêu cầu.
- [ ] Đóng channel trước checkpoint theo resource lifecycle.
- [ ] Sau restore mở channel mới và kiểm tra quyền/path.
- [ ] Xác minh file size, generation/header, anchor hoặc record id.
- [ ] Seek về saved offset và kiểm tra `channel.position()`.
- [ ] Chỉ resume worker sau khi validation thành công.
- [ ] Có rollback/reopen path nếu checkpoint bị abort.
- [ ] Xác định chính sách nếu file bị append, rotate hoặc thay đổi bên ngoài.
- [ ] Không dựa vào `BufferedReader` read-ahead position làm logical cursor.
- [ ] Nếu nhiều writer/process, có lock/coordination rõ ràng.
- [ ] Đã kiểm thử truncate, partial record, UTF-8, permission và mount failure.

## 22. Kết luận

Để đóng và mở lại tệp an toàn, hãy lưu offset theo byte sau khi I/O đã hoàn tất, flush dữ liệu cần thiết, đóng channel, mở channel mới và seek về offset đã lưu. Kiểm tra `channel.position()` chứng minh cursor đã được đặt; đọc lại marker hoặc record tại vùng liên quan mới chứng minh cursor trỏ tới dữ liệu mong đợi.

Trong CRaC, đặt quy trình này vào Resource lifecycle: dừng nhận việc và drain I/O trước checkpoint, lưu cursor trong trạng thái được khôi phục, force/close file, rồi reopen/verify sau restore trước khi resume worker. Nếu checkpoint abort, cần đường rollback riêng để mở lại file trong process gốc. Với UTF-8, buffered reader, file rotation hoặc nhiều writer, phải quản lý logical offset và file identity rõ ràng; chỉ giữ một con số PID/offset hay một object channel trong heap là chưa đủ.
