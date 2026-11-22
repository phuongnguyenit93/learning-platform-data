# Java 7 — Kênh tệp bất đồng bộ: ByteBuffer và trường hợp chưa đọc ghi đủ dữ liệu

## 1. Mục tiêu, phạm vi và nguyên tắc quan trọng nhất

`AsynchronousFileChannel` thuộc Java NIO.2, xuất hiện từ Java 7 và **vẫn được hỗ trợ trên Java 17+**. API này khởi tạo các thao tác đọc/ghi tệp bất đồng bộ; kết quả được nhận qua `Future<Integer>` hoặc `CompletionHandler<Integer, A>`.

**Một lần `read` hoặc `write` hoàn tất không nhất thiết chuyển hết số byte mà caller muốn.** Số nguyên `n` sau completion phản ánh tiến độ *thực tế của đúng một lần I/O*. Nếu cần đủ dữ liệu, ứng dụng phải lặp đúng cách.

Bài học giúp bạn:

- Phân biệt vị trí trong `ByteBuffer` với vị trí trong file.
- Sử dụng `position`, `limit`, `capacity`, `remaining`, `flip`, `clear`, `compact` đúng thời điểm.
- Hiểu `AsynchronousFileChannel` **không có current file position**: mỗi thao tác truyền explicit `long filePosition`.
- Xử lý `n>0`, `n==0` và `n==-1`; EOF của read khác trạng thái không tiến triển.
- Viết vòng `writeFully` và vòng `readUntilEof` hoặc `readExactly`.
- Giữ bytes chưa ghi hết, không ghi đè buffer khi I/O còn pending.
- Dùng cả `Future` và `CompletionHandler` để tiếp tục một chuỗi partial operations.
- Copy file theo khối nhỏ, quản lý hai offsets riêng.
- Đọc UTF-8 khi byte của ký tự bị chia qua nhiều lượt.
- Xử lý exception, timeout, cancellation, concurrent I/O và file thay đổi.
- Phân biệt nội dung chuẩn NIO.2 Java 7 với những tiện ích Java 9+/11+ dùng trong ví dụ.

Các chương trình standalone được biên dịch bằng `javac --release 17` trên JDK hiện đại. Mỗi chương trình dùng directory tạm riêng và tự dọn tài nguyên. Không có nội dung API đã bị thay thế hoặc legacy theo lưu ý của module.

## 2. Hai hệ tọa độ cần phân biệt

```text
FILE (byte offsets):
    0 1 2 3 4 5 6 7 8 9 ...
          ^
          filePosition (long) — do caller truyền

ByteBuffer (indexes):
    0 1 2 3 4 5 6 7
    |   |       |   |
    0   position limit capacity

vùng còn khả dụng = [position,limit)
remaining = limit - position
```

| Thuộc tính | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `ByteBuffer.capacity()` | `int` | Dung lượng tối đa được cấp cho buffer |
| `ByteBuffer.position()` | `int` | Chỉ số byte tương đối kế tiếp |
| `ByteBuffer.limit()` | `int` | Giới hạn vùng buffer hợp lệ |
| `ByteBuffer.remaining()` | `int` | `limit-position` |
| `ByteBuffer.hasRemaining()` | `boolean` | Còn byte trong vùng hiệu lực? |
| `filePosition` của `read`/`write` | `long` | Vị trí byte bắt đầu trên file, không nằm trong ByteBuffer |
| `n` của một I/O hoàn tất | `int` | Số byte đã thực sự đọc/ghi; read có thể trả -1 |

Bất biến của Buffer: `0 ≤ position ≤ limit ≤ capacity`.

**Quan trọng:** Khi `read`/`write` chuyển `n>0` byte, chính operation cập nhật `ByteBuffer.position()`. Caller phải tăng **file position** của lần sau bằng `n`, **không tự tăng buffer.position thêm n lần nữa**.

### 2.1. Không có current position trên AsynchronousFileChannel

`FileChannel` có khái niệm current position và các positional overloads. Ngược lại, `AsynchronousFileChannel` **không có current file position**. Mỗi `read(dst, position)`/`write(src, position)` yêu cầu byte offset cụ thể.

Hai lời gọi:

```java
channel.write(first, 0L).get();
channel.write(second, 0L).get();
```

đều bắt đầu từ offset 0, có thể **ghi đè** nhau; không có tự động append. Đây là đoạn minh họa, cần các biến, imports và handling exceptions tương ứng.

### 2.2. Dung lượng buffer không chứng minh số byte đã chuyển

Giả sử buffer capacity=8, position=0, limit=8. `remaining()==8` chỉ nói I/O có thể chuyển **tối đa** 8 byte. Một lần read/write có thể hoàn tất với `n=3`:

```text
Trước: position=0,limit=8,remaining=8
Sau:   position=3,limit=8,remaining=5
File offset lần kế tiếp: offset cũ + 3
```

Năm byte còn lại **chưa được tự động xử lý**. Muốn đọc/ghi đủ 8 byte, tiếp tục operations sau khi lần trước đã hoàn tất.

## 3. Vòng đời ByteBuffer: flip, clear, compact

### 3.1. Allocate và put

`ByteBuffer.allocate(5)` tạo heap buffer với `position=0`, `limit=5`, `capacity=5`. Sau khi `put` 3 byte, position=3, limit vẫn là 5.

### 3.2. Flip: chuyển từ nạp sang tiêu thụ

`flip()` đặt `limit = oldPosition` và `position = 0`. Vì vậy, sau khi đọc **từ file vào buffer**, gọi `flip` để giới hạn vùng byte vừa nhận trước khi giải mã, chuyển tiếp hoặc ghi ra kênh khác.

### 3.3. Clear: chuẩn bị nạp lại

`clear()` đặt `position=0` và `limit=capacity`, **không xóa/zero-fill nội dung vật lý**. Chỉ clear khi dữ liệu trước đó đã được tiêu thụ/ghi hết hoặc không còn cần.

### 3.4. Compact: giữ phần chưa tiêu thụ

`compact()` dồn các byte trong khoảng `[position,limit)` về đầu buffer rồi đặt position sau các byte còn lại, limit=capacity.

Ví dụ đang có `ABCDE`, đã đọc `AB`, còn `CDE`; `compact` giữ `CDE` để nạp thêm `FG` thành `CDEFG`. Không dùng `clear` nếu phần `CDE` còn cần.

### 3.5. Wrap khác allocate+put

`ByteBuffer.wrap(byte[])` thường đã sẵn ở `position=0`, `limit=length`. **Không flip ngay** trên buffer vừa wrap chưa hề put; flip có thể biến limit thành 0. Trái lại, buffer `allocate` rồi `put` cần flip trước khi dùng làm source để ghi ra channel.

## 4. Chương trình A — BufferStatesDemo.java

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

public final class BufferStatesDemo {
    public static void main(String[] args) {
        ByteBuffer b = ByteBuffer.allocate(5);
        System.out.println("initial=" +
                b.position() + "/" + b.limit() + "/" + b.capacity());

        b.put("ABCDE".getBytes(StandardCharsets.US_ASCII));
        System.out.println("afterPut=" + b.position() + "/" + b.limit());

        b.flip();
        System.out.println("afterFlip=" + b.position() + "/" + b.limit());
        System.out.println("first=" + (char) b.get() +
                ",second=" + (char) b.get());

        b.compact();
        System.out.println("afterCompact=" +
                b.position() + "/" + b.limit());

        b.put("FG".getBytes(StandardCharsets.US_ASCII));
        b.flip();
        byte[] remaining = new byte[b.remaining()];
        b.get(remaining);
        System.out.println("remainingText=" +
                new String(remaining, StandardCharsets.US_ASCII));

        b.clear();
        System.out.println("afterClear=" +
                b.position() + "/" + b.limit());
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 BufferStatesDemo.java
java BufferStatesDemo
```

**Stdout đã kiểm chứng:**

```text
initial=0/5/5
afterPut=5/5
afterFlip=0/5
first=A,second=B
afterCompact=3/5
remainingText=CDEFG
afterClear=0/5
```

Phân tích: sau `get` hai byte, còn `CDE`; `compact` bảo toàn ba byte này, tiếp `put FG` rồi `flip` tạo vùng `CDEFG`. `clear` cuối chỉ reset vị trí và giới hạn, không xóa dữ liệu nhạy cảm khỏi memory.

## 5. Hợp đồng AsynchronousFileChannel.read

Hai overload chính:

```java
Future<Integer> pending = channel.read(dst, filePosition);

channel.read(dst, filePosition, attachment,
        new CompletionHandler<Integer, AttachmentType>() {
            public void completed(Integer n, AttachmentType a) {
                // Thành công: n byte đã đọc hoặc -1 ở EOF.
            }
            public void failed(Throwable error, AttachmentType a) {
                // Thao tác bất đồng bộ thất bại.
            }
        });
```

Đây là **mảnh minh họa**, `AttachmentType` là kiểu do ứng dụng tự định nghĩa, không phải class Java có sẵn.

`dst` phải là buffer **có thể ghi**, `filePosition >= 0`, channel phải được mở để đọc. Với Future, `get()` nhận số byte hoặc -1 khi tại EOF; `get` có thể chặn caller.

### 5.1. Ba kết quả của read

| Kết quả `n` | Ý nghĩa | Xử lý |
| --- | --- | --- |
| `n > 0` | Đã đọc `n` byte vào buffer | Tăng file offset `+=n`; xử lý byte sau khi I/O hoàn tất |
| `n == 0` | Không có byte tiến triển; ví dụ destination không còn remaining | Không tính là EOF; có guard/deadline |
| `n == -1` | End-of-file tại thời điểm attempt, ví dụ file position ≥ size | Kết thúc đọc hoặc báo thiếu dữ liệu nếu yêu cầu đúng N byte |
| Exception | Lỗi precondition/I/O/close/quyền | Xử lý tường minh |

Một lần read được phép đọc **ít hơn `dst.remaining()`** trước operation. Do đó code yêu cầu một record 100 byte **không được** gọi một read rồi giả định buffer đầy.

### 5.2. EOF là trạng thái quan sát, không phải cam kết bất biến

Nếu process khác đang append file, một read ở offset=size có thể trả -1 **lúc này**, nhưng file có thể có dữ liệu mới sau đó. Với bài toán tail log hoặc phát hành file, cần protocol riêng để biết khi nào nguồn đã hoàn tất.

## 6. Hợp đồng AsynchronousFileChannel.write

Tương tự:

```java
Future<Integer> pending = channel.write(src, filePosition);

channel.write(src, filePosition, attachment, handler);
```

`src` là buffer source; channel phải mở `WRITE`. `Future.get()` hoặc `CompletionHandler.completed(n,...)` nhận số byte **đã được ghi bởi đúng operation đó**.

- `n > 0`: tiến độ; tăng file offset `+=n`.
- `n == 0`: chưa tiến triển; retry có giới hạn/backoff phù hợp.
- `n < 0`: không phải kết quả bình thường của write theo API; xem là logic error.
- Exception: xử lý theo `getCause()` hoặc handler `failed`.

**Không nhầm** `src.capacity()` với số byte vừa được ghi. Nếu buffer có 10 byte và write trả 3, chính buffer còn 7 byte cần viết tiếp.

## 7. Mẫu readExactly và writeFully

### 7.1. Đọc đúng N byte hoặc báo thiếu

```java
static int readExactly(
        AsynchronousFileChannel channel,
        ByteBuffer dst,
        long offset) throws Exception {
    int readBytes = 0;
    int zeros = 0;

    while (dst.hasRemaining()) {
        int n = channel.read(dst, offset)
                .get(5, TimeUnit.SECONDS);

        if (n == -1) {
            throw new EOFException(
                    "Truncated record: got " + readBytes + " bytes");
        }
        if (n == 0) {
            if (++zeros > 16)
                throw new IOException("Read stalled");
            continue;
        }

        zeros = 0;
        readBytes += n;
        offset += n;
    }
    return readBytes;
}
```

Đây là **helper minh họa** (không phải standalone class). Cần `AsynchronousFileChannel`, `ByteBuffer`, `EOFException`, `IOException`, `TimeUnit` và xử lý `Exception` ở caller. Nó đòi **đúng số byte `dst.remaining()` tại khi gọi**, nhưng không tự đóng channel, và không tự biết một file đang được writer khác hoàn tất lúc nào.

Khi đọc vào **cùng buffer** để lấp đầy, **không clear buffer giữa các partial reads**. Channel cập nhật buffer position; caller chỉ cần cập nhật file offset.

### 7.2. Ghi hết buffer và trả offset mới

```java
static long writeFully(
        AsynchronousFileChannel channel,
        ByteBuffer src,
        long offset) throws Exception {
    int zeros = 0;

    while (src.hasRemaining()) {
        int n = channel.write(src, offset)
                .get(5, TimeUnit.SECONDS);

        if (n < 0)
            throw new IOException("Unexpected negative write");

        if (n == 0) {
            if (++zeros > 16)
                throw new IOException("Write stalled");
            continue;
        }

        zeros = 0;
        offset += n;
    }
    return offset;
}
```

Đây là helper minh họa. Chỉ sau khi `!src.hasRemaining()` mới được xem là **đã ghi hết bytes của buffer**. Không có thao tác mặc định tự tăng một current file position của channel.

### 7.3. Hai lưu ý về timeout

`future.get(5, TimeUnit.SECONDS)` giới hạn **thời gian chờ của caller cho một operation**, không giới hạn toàn bộ workflow. Nếu get timeout, operation **có thể vẫn pending**. Tuyệt đối không mutate hoặc trả buffer về pool ngay vì tưởng timeout là cancellation. Cần policy cancel/close/completion riêng.

Guard `zeros > 16` trong code là **chính sách minh họa để tránh lặp vô tận**, không phải chuẩn NIO.2. Khi triển khai thật, đo provider, deadline tổng, backoff và khả năng retry an toàn.

## 8. Chương trình B — PartialWriteDemo.java

Để minh họa chắc chắn nhiều pha, ví dụ **chủ động đặt `limit=3`** rồi mở rộng `limit=10`. Đây không phải một lời khẳng định OS đã tự partial-write 3 byte khi nhận buffer 10 byte.

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.concurrent.*;

public final class PartialWriteDemo {
    static long writeFully(
            AsynchronousFileChannel ch, ByteBuffer src, long offset)
            throws Exception {
        int zeros = 0;
        long position = offset;

        while (src.hasRemaining()) {
            Future<Integer> pending = ch.write(src, position);
            int n = pending.get(5, TimeUnit.SECONDS);

            if (n < 0)
                throw new IOException("unexpected negative write");

            if (n == 0) {
                if (++zeros > 16)
                    throw new IOException("write stalled");
                continue;
            }

            zeros = 0;
            position += n;
        }
        return position;
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("partial-write-");
        Path file = root.resolve("data.bin");

        try {
            ByteBuffer src = ByteBuffer.wrap(
                    "ABCDEFGHIJ".getBytes(StandardCharsets.US_ASCII));

            try (AsynchronousFileChannel ch =
                         AsynchronousFileChannel.open(
                                 file,
                                 StandardOpenOption.WRITE,
                                 StandardOpenOption.CREATE_NEW)) {
                src.limit(3);
                long afterFirst = writeFully(ch, src, 0);

                src.limit(10);
                long afterSecond = writeFully(ch, src, afterFirst);

                System.out.println("firstPhaseBytes=" + afterFirst);
                System.out.println("secondPhaseBytes=" +
                        (afterSecond - afterFirst));
                System.out.println("bufferRemaining=" + src.remaining());
                System.out.println("fileSize=" + ch.size());
            }

            System.out.println("fileContent=" + Files.readString(file));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 PartialWriteDemo.java
java PartialWriteDemo
```

**Stdout đã kiểm chứng:**

```text
firstPhaseBytes=3
secondPhaseBytes=7
bufferRemaining=0
fileSize=10
fileContent=ABCDEFGHIJ
```

Vì `ByteBuffer.wrap` đã có `limit=10` ban đầu, sau pha đầu position=3. Mở lại limit 10 để thấy đúng 7 byte còn lại; không cần `clear` hay `flip`. Hai pha dùng offsets 0 và 3, tạo file đủ 10 byte. Helper vẫn xử lý **partial result thật** của từng operation nếu provider trả ngắn hơn vùng còn lại.

### 8.1. Những cách viết gây lỗi

- Chỉ `channel.write(src, 0).get()` một lần rồi đóng channel.
- Ở pha hai truyền lại offset=0 nên bytes sau ghi đè bytes đầu.
- Gọi `clear` sau pha một, reset position về 0 và ghi lại bytes cũ.
- Chỉ kiểm `future.isDone()` rồi báo đủ dữ liệu mà không lấy `n` và kiểm `hasRemaining`.

## 9. Đọc theo khối nhỏ: vòng lặp đúng

Khi muốn đọc đến EOF và tiêu thụ dữ liệu ngay:

```text
while true:
    buffer.clear()
    n = await read(buffer, fileOffset)
    if n == -1: break
    if n == 0: xử lý zero-progress
    else:
        fileOffset += n
        buffer.flip()
        consume đúng buffer.remaining() bytes
```

Nếu buffer capacity=4, file dài 9 byte, không nhất thiết mỗi read trả lần lượt 4,4,1. Thuật toán phải đúng ngay cả khi provider trả 2,2,3,1,1. Sau `flip`, chỉ những bytes trong vùng hiệu lực mới được tiêu thụ.

**Không copy toàn bộ `buffer.array()` mỗi lượt** mà bỏ qua số byte thực tế; đoạn cuối có thể chứa bytes cũ từ lượt trước.

## 10. Chương trình C — ChunkedReadDemo.java

```java
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.concurrent.*;

public final class ChunkedReadDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("chunked-read-");
        Path file = root.resolve("data.txt");

        try {
            Files.writeString(
                    file, "ABCD12345", StandardCharsets.US_ASCII);

            try (AsynchronousFileChannel ch =
                         AsynchronousFileChannel.open(
                                 file, StandardOpenOption.READ)) {
                ByteBuffer dst = ByteBuffer.allocate(4);
                ByteArrayOutputStream all =
                        new ByteArrayOutputStream();
                long offset = 0;
                int zeros = 0;
                boolean eof = false;

                while (true) {
                    dst.clear();
                    int n = ch.read(dst, offset)
                            .get(5, TimeUnit.SECONDS);

                    if (n == -1) {
                        eof = true;
                        break;
                    }
                    if (n == 0) {
                        if (++zeros > 16)
                            throw new IllegalStateException("read stalled");
                        continue;
                    }

                    zeros = 0;
                    offset += n;
                    dst.flip();

                    byte[] part = new byte[dst.remaining()];
                    dst.get(part);
                    all.write(part);
                }

                System.out.println("data=" +
                        new String(all.toByteArray(),
                                StandardCharsets.US_ASCII));
                System.out.println("total=" + offset);
                System.out.println("eof=" + eof);
                System.out.println("bufferCapacity=" + dst.capacity());
                System.out.println("fileSize=" + ch.size());
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ChunkedReadDemo.java
java ChunkedReadDemo
```

**Stdout đã kiểm chứng:**

```text
data=ABCD12345
total=9
eof=true
bufferCapacity=4
fileSize=9
```

Chương trình sử dụng `ByteArrayOutputStream` để gom 9 byte, nên output không phụ thuộc số lượt read của OS. Với file lớn, xử lý block ngay hoặc stream sang output; đừng gom vô hạn tất cả bytes vào RAM.

### 10.1. Vì sao `flip` là bước bắt buộc?

Sau read `n>0`, buffer position đã tiến. Nếu không flip rồi gọi `get`, có thể chỉ đọc vùng còn lại **chưa chứa dữ liệu mới**. `flip` đặt limit chính xác theo bytes mới nhận và position về 0. Sau tiêu thụ xong, mới clear để tái dùng buffer cho read tiếp.

## 11. EOF và đọc không đủ một bản ghi

Có hai hợp đồng khác nhau:

- **Read until EOF:** file hiện chứa 3 byte thì nhận 3 byte rồi EOF là hoàn thành.
- **Read exactly 5 bytes:** file chỉ có 3 byte thì nhận 3 rồi EOF là **thiếu dữ liệu**, không thể báo “đủ 5”.

Với `AsynchronousFileChannel.read`, `-1` diễn tả EOF khi file position ≥ file size tại thời điểm attempt. **Đừng dùng `n<=0` làm điều kiện EOF**, vì `0` có nghĩa khác.

Một `ByteBuffer` với `remaining()==0` không có chỗ chứa; trên JDK test, `read(emptyBuffer,0)` trả 0. Điều này không chứng minh file rỗng.

## 12. Chương trình D — ShortReadEofDemo.java

```java
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.concurrent.*;

public final class ShortReadEofDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("short-read-");
        Path file = root.resolve("cat.txt");

        try {
            Files.writeString(
                    file, "cat", StandardCharsets.US_ASCII);

            try (AsynchronousFileChannel ch =
                         AsynchronousFileChannel.open(
                                 file, StandardOpenOption.READ)) {
                ByteBuffer dst = ByteBuffer.allocate(5);
                long offset = 0;
                int zeros = 0;
                boolean eof = false;

                while (dst.hasRemaining()) {
                    int n = ch.read(dst, offset)
                            .get(5, TimeUnit.SECONDS);

                    if (n == -1) {
                        eof = true;
                        break;
                    }
                    if (n == 0) {
                        if (++zeros > 16)
                            throw new IllegalStateException("read stalled");
                        continue;
                    }

                    zeros = 0;
                    offset += n;
                }

                dst.flip();
                byte[] part = new byte[dst.remaining()];
                dst.get(part);

                System.out.println("requested=5");
                System.out.println("read=" + offset);
                System.out.println("eofBeforeFull=" + eof);
                System.out.println("fullyRead=" + (offset == 5));
                System.out.println("data=" +
                        new String(part, StandardCharsets.US_ASCII));

                ByteBuffer zero = ByteBuffer.allocate(0);
                System.out.println("emptyBufferRead=" +
                        ch.read(zero, 0)
                                .get(5, TimeUnit.SECONDS));

                ByteBuffer one = ByteBuffer.allocate(1);
                System.out.println("readFromEof=" +
                        ch.read(one, 3)
                                .get(5, TimeUnit.SECONDS));
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ShortReadEofDemo.java
java ShortReadEofDemo
```

**Stdout đã kiểm chứng:**

```text
requested=5
read=3
eofBeforeFull=true
fullyRead=false
data=cat
emptyBufferRead=0
readFromEof=-1
```

Ba byte `cat` đã đọc đúng nhưng **chưa thỏa yêu cầu 5 byte**. `emptyBufferRead=0` khác `readFromEof=-1`. Nếu parse một file format với header cố định, phải báo truncated record/EOF thay vì pad hai byte zero hoặc dùng bytes cũ trong buffer.

## 13. Future và CompletionHandler: hai cách nhận cùng tiến độ

| Khía cạnh | `Future<Integer>` | `CompletionHandler<Integer,A>` |
| --- | --- | --- |
| Cách khởi tạo | `read(buf,pos)` / `write(buf,pos)` | `read(buf,pos,a,handler)` |
| Thành công | `future.get()` trả n | `completed(n,a)` |
| Thất bại | `ExecutionException.getCause()` | `failed(Throwable,a)` |
| Caller có thể block? | `get` có thể block | Không buộc caller chờ callback |
| State loop | Lưu trong caller | Lưu trong attachment/state |
| Việc cần làm với partial | Caller gọi tiếp khi cần | Handler initiate operation kế khi cần |

**Dù dùng cách nào, một operation không tự đảm bảo full read/full write**. Chính ứng dụng phải kiểm tra `n` và `hasRemaining()`.

### 13.1. Future.get ngay sau read vẫn là chờ có chặn

`Future.get` cho cách viết tuần tự dễ kiểm chứng, không phải tuyên bố toàn bộ workflow không bao giờ block. Dùng handler khi muốn event-driven orchestration, nhưng vẫn phải kiểm soát số pending operations, thread pool, buffer ownership và backpressure.

### 13.2. Handler phải xử lý cả failed

Nếu một callback chỉ triển khai `completed` và bỏ qua `failed`, workflow có thể chờ vô hạn hoặc báo trạng thái sai khi I/O thất bại. Lỗi không được biến thành success chỉ vì code đã initiate một operation.

## 14. Chương trình E — HandlerWriteDemo.java

Ví dụ ghi `handler-data` bằng chuỗi callbacks. Attachment `State` chứa chính buffer, file offset và kết quả tổng. Sau mỗi `completed(n,s)`, nếu buffer còn byte thì gọi tiếp `write` ở offset cập nhật.

```java
import java.nio.ByteBuffer;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.concurrent.*;

public final class HandlerWriteDemo {
    static final class State {
        final AsynchronousFileChannel channel;
        final ByteBuffer buffer;
        final CompletableFuture<Long> done;
        long offset;
        int empty;

        State(AsynchronousFileChannel ch,
              ByteBuffer b, CompletableFuture<Long> d) {
            channel = ch;
            buffer = b;
            done = d;
        }
    }

    static final CompletionHandler<Integer, State> HANDLER =
            new CompletionHandler<>() {
        public void completed(Integer n, State s) {
            if (n == null || n < 0) {
                s.done.completeExceptionally(
                    new IllegalStateException(
                        "unexpected write result"));
                return;
            }
            if (n == 0 && ++s.empty > 16) {
                s.done.completeExceptionally(
                    new IllegalStateException("write stalled"));
                return;
            }
            if (n > 0) {
                s.empty = 0;
                s.offset += n;
            }
            if (s.buffer.hasRemaining()) {
                s.channel.write(s.buffer, s.offset, s, this);
            } else {
                s.done.complete(s.offset);
            }
        }

        public void failed(Throwable failure, State s) {
            s.done.completeExceptionally(failure);
        }
    };

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("handler-write-");
        Path file = root.resolve("data.txt");

        try {
            ByteBuffer src = ByteBuffer.wrap(
                    "handler-data".getBytes(StandardCharsets.US_ASCII));
            CompletableFuture<Long> done = new CompletableFuture<>();

            try (AsynchronousFileChannel ch =
                         AsynchronousFileChannel.open(
                                 file,
                                 StandardOpenOption.WRITE,
                                 StandardOpenOption.CREATE_NEW)) {
                State state = new State(ch, src, done);
                ch.write(src, 0L, state, HANDLER);

                long count = done.get(5, TimeUnit.SECONDS);
                System.out.println("bytesWritten=" + count);
                System.out.println("bufferDrained=" +
                        (!src.hasRemaining()));
            }
            System.out.println("content=" + Files.readString(file));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 HandlerWriteDemo.java
java HandlerWriteDemo
```

**Stdout đã kiểm chứng:**

```text
bytesWritten=12
bufferDrained=true
content=handler-data
```

Giải thích: mỗi callback nhận tiến độ **một write**, rồi khởi tạo tiếp nếu cần. `done` chỉ hoàn tất khi source buffer đã drained. `failed` báo lỗi qua future. Dữ liệu là ASCII 12 byte, không dựa vào số lần callbacks cụ thể.

**Lưu ý production:** Đây là demo nhỏ. Cần bao phủ lỗi đồng bộ lúc initiate `write`, tránh callbacks quá nặng trên thread dispatcher, có chính sách zero-progress/backoff, timeout/cancellation, giữ channel mở đủ lâu và không tái dùng buffer khi pending.

## 15. Độc lập giữa file offset và buffer position: ghi đè có chủ ý

Nếu ghi `ABCDE` vào offset0 rồi ghi `xy` vào offset2, kết quả là `ABxyE`; offset thứ hai **không tự trở thành 5**.

```text
Trước:  offset 0 1 2 3 4
        bytes  A B C D E
Write:  start at fileOffset=2, source="xy"
Sau:             A B x y E
```

Đây là công dụng của positional I/O, nhưng cũng là lỗi nghiêm trọng nếu ứng dụng quên tính offset. Khi nhiều writers cùng cập nhật file, `channel.size()` không phải một phép reserve append offset atomic cho tất cả threads.

## 16. Chương trình F — PositionalWriteDemo.java

```java
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.concurrent.*;

public final class PositionalWriteDemo {
    static long writeFully(
            AsynchronousFileChannel ch, ByteBuffer b, long offset)
            throws Exception {
        long p = offset;
        int zeros = 0;

        while (b.hasRemaining()) {
            int n = ch.write(b, p).get(5, TimeUnit.SECONDS);
            if (n <= 0) {
                if (++zeros > 16)
                    throw new IllegalStateException("write stalled");
                continue;
            }
            zeros = 0;
            p += n;
        }
        return p;
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("positional-write-");
        Path file = root.resolve("data.bin");

        try {
            try (AsynchronousFileChannel ch =
                         AsynchronousFileChannel.open(
                                 file,
                                 StandardOpenOption.WRITE,
                                 StandardOpenOption.CREATE_NEW)) {

                long firstEnd = writeFully(
                        ch, ByteBuffer.wrap(
                                "ABCDE".getBytes(
                                        StandardCharsets.US_ASCII)),
                        0L);

                long secondEnd = writeFully(
                        ch, ByteBuffer.wrap(
                                "xy".getBytes(
                                        StandardCharsets.US_ASCII)),
                        2L);

                System.out.println("firstEnd=" + firstEnd);
                System.out.println("secondEnd=" + secondEnd);
                System.out.println("fileSize=" + ch.size());
            }
            System.out.println("fileText=" + Files.readString(file));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 PositionalWriteDemo.java
java PositionalWriteDemo
```

**Stdout đã kiểm chứng:**

```text
firstEnd=5
secondEnd=4
fileSize=5
fileText=ABxyE
```

`firstEnd=5` vì ghi 5 byte từ offset0; `secondEnd=4` vì ghi 2 byte từ offset2. Return value của helper là **offset kế tiếp sau vùng vừa ghi**, không phải tổng bytes của mọi pha.

## 17. Copy file theo khối: partial read và partial write

Một thuật toán copy không mất dữ liệu phải có **hai vòng lặp**:

1. Vòng ngoài đọc một block từ source. Nếu `-1` thì EOF; nếu `n>0` thì cập nhật `readOffset+=n`.
2. `buffer.flip()`.
3. Vòng trong ghi **hết chính block đó**: gọi `write(buffer,writeOffset)` lặp đến khi `!buffer.hasRemaining()`, tăng `writeOffset` theo `w` thực tế.
4. Chỉ sau khi block đã ghi hết mới `clear` buffer để đọc block tiếp theo.

```text
AsynchronousFileChannel source
          |
          | read(buffer,readOffset)
          |  → n bytes, readOffset += n
          v
      ByteBuffer
          |
          | flip()
          | write(buffer,writeOffset) ... until drained
          | writeOffset += written bytes
          v
AsynchronousFileChannel destination
```

Nếu đọc block mới trước khi write hoàn tất, buffer có thể bị ghi đè trong lúc destination còn lấy bytes; dữ liệu đích hỏng. Nếu quên tăng writeOffset sau partial write, một phần bytes có thể ghi đè nhau.

## 18. Chương trình G — AsyncCopyDemo.java

```java
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.concurrent.*;

public final class AsyncCopyDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("async-copy-");
        Path src = root.resolve("source.txt");
        Path dst = root.resolve("copy.txt");

        try {
            Files.writeString(
                    src, "0123456789abcdefghij",
                    StandardCharsets.US_ASCII);

            long readOffset = 0;
            long writeOffset = 0;
            ByteBuffer buffer = ByteBuffer.allocate(4);

            try (AsynchronousFileChannel in =
                         AsynchronousFileChannel.open(
                                 src, StandardOpenOption.READ);
                 AsynchronousFileChannel out =
                         AsynchronousFileChannel.open(
                                 dst,
                                 StandardOpenOption.WRITE,
                                 StandardOpenOption.CREATE_NEW)) {

                int zeros = 0;
                while (true) {
                    buffer.clear();
                    int n = in.read(buffer, readOffset)
                            .get(5, TimeUnit.SECONDS);

                    if (n == -1) break;

                    if (n == 0) {
                        if (++zeros > 16)
                            throw new IllegalStateException("read stalled");
                        continue;
                    }

                    zeros = 0;
                    readOffset += n;
                    buffer.flip();

                    int writeZeros = 0;
                    while (buffer.hasRemaining()) {
                        int w = out.write(buffer, writeOffset)
                                .get(5, TimeUnit.SECONDS);
                        if (w <= 0) {
                            if (++writeZeros > 16)
                                throw new IllegalStateException("write stalled");
                            continue;
                        }

                        writeZeros = 0;
                        writeOffset += w;
                    }
                }
            }

            System.out.println("bytesRead=" + readOffset);
            System.out.println("bytesWritten=" + writeOffset);
            System.out.println("contentsMatch=" +
                    Files.readString(src)
                            .equals(Files.readString(dst)));
            System.out.println("destSize=" + Files.size(dst));
        } finally {
            Files.deleteIfExists(dst);
            Files.deleteIfExists(src);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 AsyncCopyDemo.java
java AsyncCopyDemo
```

**Stdout đã kiểm chứng:**

```text
bytesRead=20
bytesWritten=20
contentsMatch=true
destSize=20
```

Với buffer capacity4, nội dung 20 byte được chuyển qua nhiều operations. Kết quả đúng **không phụ thuộc một read luôn trả 4 byte**: mọi lần read tăng offset theo `n` thực tế, mọi lần write tăng offset theo `w` thực tế.

Ví dụ so sánh chuỗi vì dữ liệu là ASCII nhỏ. Với file nhị phân/lớn, dùng so sánh byte/hash/manifest theo yêu cầu, và không giữ toàn bộ dữ liệu trong RAM.

### 18.1. Copy thất bại giữa chừng thì sao?

File destination có thể đã được ghi **một phần**. Đừng báo thành công nếu một read/write lỗi hoặc timeout. Với nghiệp vụ cần bản copy chỉ xuất hiện khi đủ, có thể ghi file tạm, xác minh, rồi publish theo quy trình phù hợp, xét khả năng `ATOMIC_MOVE` của filesystem và việc concurrent writers thay source.

## 19. Lỗi precondition: offset âm, read-only buffer, channel READ

`AsynchronousFileChannel` yêu cầu:

- `filePosition >= 0`.
- Buffer đích của `read` có thể ghi (không phải read-only buffer).
- Channel được mở cho `READ` nếu read và `WRITE` nếu write.
- Pending operations phải xử lý riêng với synchronous precondition exceptions.

Một `ByteBuffer.asReadOnlyBuffer()` **không dùng được làm đích của read**, nhưng có thể là **nguồn của write** (write chỉ lấy bytes từ buffer). Đừng đánh đồng “read-only buffer” với “cấm mọi I/O”.

## 20. Chương trình H — InvalidBuffersDemo.java

```java
import java.nio.ByteBuffer;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public final class InvalidBuffersDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("invalid-buffers-");
        Path file = root.resolve("source.txt");

        try {
            Files.writeString(
                    file, "abc", StandardCharsets.US_ASCII);

            try (AsynchronousFileChannel ch =
                         AsynchronousFileChannel.open(
                                 file, StandardOpenOption.READ)) {

                try {
                    ch.read(ByteBuffer.allocate(2), -1L);
                    System.out.println("negativeReadRejected=false");
                } catch (IllegalArgumentException expected) {
                    System.out.println("negativeReadRejected=true");
                }

                try {
                    ch.read(
                            ByteBuffer.allocate(2).asReadOnlyBuffer(),
                            0L);
                    System.out.println("readonlyDestRejected=false");
                } catch (IllegalArgumentException expected) {
                    System.out.println("readonlyDestRejected=true");
                }

                try {
                    ch.write(
                            ByteBuffer.wrap(new byte[] {1, 2}), 0L);
                    System.out.println(
                            "writeOnReadonlyChannelRejected=false");
                } catch (NonWritableChannelException expected) {
                    System.out.println(
                            "writeOnReadonlyChannelRejected=true");
                }
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 InvalidBuffersDemo.java
java InvalidBuffersDemo
```

**Stdout đã kiểm chứng:**

```text
negativeReadRejected=true
readonlyDestRejected=true
writeOnReadonlyChannelRejected=true
```

Cả ba là trường hợp input/mode không hợp lệ, không nên khắc phục bằng cách âm thầm bỏ lỗi rồi báo thành công. Chú ý vì exceptions có thể xảy ra ngay khi initiate operation, không chỉ tại `future.get()`.

## 21. UTF-8: ranh giới byte không trùng ranh giới ký tự

Chuỗi `A🙂éB` khi mã hóa UTF-8 có **8 byte**, nhưng `String.length()==5` (UTF-16 code units). Một buffer capacity3 có thể cắt một emoji 4-byte ở giữa hai lần read.

Nếu bạn làm:

```java
String text = new String(part, StandardCharsets.UTF_8);
```

riêng cho mỗi chunk mà chunk kết thúc giữa multi-byte sequence, có thể xuất hiện ký tự thay thế. Sau đó nối các String đã decode sai **không khôi phục được bytes**.

Hai cách đúng:

- **File nhỏ:** Gom bytes nguyên vẹn rồi decode một lần.
- **File lớn:** Dùng `CharsetDecoder` stateful, xử lý `CoderResult.UNDERFLOW`, giữ bytes chưa decode hoàn chỉnh (có thể `compact`) trước khi nạp thêm.

**Offset file luôn tính bằng số byte I/O trả về**, không theo String.length(), code points hoặc số glyph hiển thị.

## 22. Chương trình I — Utf8BoundaryDemo.java

```java
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.concurrent.*;

public final class Utf8BoundaryDemo {
    public static void main(String[] args) throws Exception {
        String original = "A\uD83D\uDE42\u00E9B";
        byte[] bytes =
                original.getBytes(StandardCharsets.UTF_8);

        Path root = Files.createTempDirectory("utf8-boundary-");
        Path file = root.resolve("text.txt");

        try {
            Files.write(file, bytes);
            ByteArrayOutputStream received =
                    new ByteArrayOutputStream();

            try (AsynchronousFileChannel ch =
                         AsynchronousFileChannel.open(
                                 file, StandardOpenOption.READ)) {
                ByteBuffer b = ByteBuffer.allocate(3);
                long offset = 0;
                int zeros = 0;

                while (true) {
                    b.clear();
                    int n = ch.read(b, offset)
                            .get(5, TimeUnit.SECONDS);

                    if (n == -1) break;

                    if (n == 0) {
                        if (++zeros > 16)
                            throw new IllegalStateException("read stalled");
                        continue;
                    }

                    zeros = 0;
                    offset += n;
                    b.flip();

                    byte[] part = new byte[b.remaining()];
                    b.get(part);
                    received.write(part);
                }

                System.out.println("byteCount=" + offset);
            }

            String decoded = new String(
                    received.toByteArray(), StandardCharsets.UTF_8);

            System.out.println("utf16Length=" +
                    original.length());
            System.out.println("utf8RoundTrip=" +
                    original.equals(decoded));
            System.out.println("fileSizeMatches=" +
                    (Files.size(file) == bytes.length));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 Utf8BoundaryDemo.java
java Utf8BoundaryDemo
```

**Stdout đã kiểm chứng:**

```text
byteCount=8
utf16Length=5
utf8RoundTrip=true
fileSizeMatches=true
```

Chương trình in boolean để kết quả không phụ thuộc font/terminal encoding khi hiển thị emoji. Escapes Java `\uD83D\uDE42\u00E9` tạo đúng chuỗi Unicode trong source. Buffer chỉ có 3 byte nhưng **không làm mất dữ liệu** vì bytes được ghép lại trước khi decode.

## 23. Buffer ownership khi có nhiều operations concurrent

Java `AsynchronousFileChannel` hỗ trợ nhiều operations outstanding và channel có thể được chia sẻ giữa threads. Tuy nhiên theo tài liệu Java:

- Thứ tự đọc/ghi và thứ tự completion handlers **không được bảo đảm** theo thứ tự gọi.
- Các `ByteBuffer` dùng cho I/O không an toàn khi **cùng một buffer** tham gia nhiều operations concurrent.
- Sau khi initiate một operation, đừng truy cập/mutate buffer cho tới khi operation hoàn tất.

**Anti-pattern:**

```java
ByteBuffer same = ByteBuffer.allocate(4096);
channel.read(same, 0L);
channel.read(same, 4096L);
```

Hai read outstanding vào cùng buffer có thể làm sai position và dữ liệu. Nếu muốn song song, dùng buffer riêng và offset không chồng lấn.

### 23.1. Hai buffers riêng chưa chắc đã đủ an toàn

Nếu hai writes dùng buffers riêng nhưng cùng ghi vùng offset=0, kết quả file phụ thuộc ordering/concurrency. Muốn correctness, phải có kế hoạch phân vùng offset, serialize khi cần, và chỉ publish sau các completions quan trọng.

### 23.2. Timeout/cancellation không giải phóng buffer tức thời

`Future.get(timeout)` ném `TimeoutException` **không đồng nghĩa I/O đã dừng**. `Future.cancel` hoặc close có semantics riêng; còn khả năng công việc đang xử lý ở provider. Trong mọi trường hợp, không trả buffer về pool trước khi biết có thể tái sử dụng an toàn.

### 23.3. CompletionHandler có thể chạy trên executor thread

Completion handlers được dispatch qua thread pool gắn với channel; code cần tránh block nặng và làm chậm các completions khác. Có thể dùng executor/bounded worker queue riêng cho xử lý nghiệp vụ, đồng thời giới hạn số tasks outstanding.

## 24. Các lỗi và lifecycle phải xử lý

| Tình huống | Exception/hiện tượng | Cách làm đúng |
| --- | --- | --- |
| File offset âm | `IllegalArgumentException` | Validate `>=0` |
| Buffer đích read-only | `IllegalArgumentException` | Dùng buffer writable cho read |
| Channel chỉ `READ` nhưng gọi write | `NonWritableChannelException` | Open đúng mode và quyền |
| Channel chỉ `WRITE` nhưng gọi read | `NonReadableChannelException` | Open đúng mode |
| Channel đã đóng | `ClosedChannelException` hoặc failure tùy giai đoạn | Quản lý lifecycle |
| Close khi còn pending I/O | `AsynchronousCloseException` khi pending operation fail | Không giả định full success |
| I/O error trong Future | `ExecutionException` với cause | Phân loại cause |
| Interrupted while waiting | `InterruptedException` | Khôi phục interrupt flag khi thoát theo policy |
| Timed get hết thời gian | `TimeoutException` | Pending I/O có thể vẫn chạy; không reuse buffer |
| Handler failure | `CompletionHandler.failed` | Complete workflow exceptionally |
| `n==0` liên tiếp | Không có byte tiến triển | Bounded retry/backoff/deadline |
| Read `-1` trước N | EOF/truncated record | Báo thiếu dữ liệu |
| Filesystem không hỗ trợ async channel | `UnsupportedOperationException` khi open | Kiểm tra provider hoặc fallback |
| File bị sửa/truncate đồng thời | Kết quả size/EOF thay đổi | Xác định snapshot/consistency policy |
| Nhiều writers cùng vùng | Ghi đè, dữ liệu không xác định về ordering | Serialize/partition offsets |
| Write beyond EOF | File lớn lên; bytes trong khoảng gap không được chỉ định | Khởi tạo các vùng cần thiết |

### 24.1. Error handling với Future

```java
try {
    int n = future.get();
    // Chỉ quyết định thành công sau khi xét n.
} catch (ExecutionException e) {
    Throwable cause = e.getCause();
    // Báo nguyên nhân I/O, không giả lập n=0.
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Thoát theo cancellation policy.
}
```

Đây là mảnh minh họa, cần `future` là `Future<Integer>` và imports tương ứng. Nếu dùng timed get, thêm `TimeoutException` với chính sách rõ.

### 24.2. CompletionHandler.failed là đường lỗi bắt buộc

Không chỉ log lỗi rồi vẫn hoàn tất `CompletableFuture` với success. Caller cần biết workflow chưa ghi đủ dữ liệu và liệu destination có chứa một phần bytes hay không.

### 24.3. Mốc thời gian kết quả không chứng minh durability

`Future.get` thành công chứng minh operation hoàn tất theo tầng API, **không tự bảo đảm dữ liệu đã trở thành transaction atomic/durable ở mọi thiết bị**. `AsynchronousFileChannel.force(metaData)` có semantics đẩy thay đổi ra storage theo khả năng provider, nhưng không biến nhiều writes thành một transaction duy nhất. Nếu cần integrity và publish an toàn, thiết kế temp file, verify, fsync/force và move theo contract của filesystem.

## 25. Những lỗi sai phổ biến

1. **Gọi `write` một lần rồi báo full success.** Phải lặp đến `!hasRemaining`.
2. **Gọi `read` một lần rồi parse buffer như đã đầy.** Phải dùng `n`/limit hoặc đọc đúng N.
3. **Cộng fileOffset theo buffer.capacity().** Phải cộng `n` thực tế.
4. **Tự cập nhật buffer.position thêm n.** Channel đã cập nhật sau completion.
5. **Flip một buffer vừa wrap chưa put.** Có thể khiến remaining=0.
6. **Clear trong khi còn bytes chưa gửi.** Mất dữ liệu.
7. **Dùng `buffer.array()` để lấy toàn bộ capacity.** Có thể chứa bytes cũ; direct buffer có thể không có array.
8. **Coi `n==0` là EOF.** EOF của read là `-1`.
9. **Coi `-1` là kết quả ghi hợp lệ.** Write không dùng EOF sentinel.
10. **Reuse buffer trước khi Future/handler hoàn tất.** Race/hỏng dữ liệu.
11. **Coi timeout là cancellation thành công.** Pending I/O có thể vẫn chạy.
12. **Dùng một ByteBuffer cho hai pending I/Os.** Buffer không an toàn cho trường hợp này.
13. **Ghi hai buffers khác nhau vào cùng offset khi không muốn overwrite.** Completion order không được bảo đảm.
14. **Dùng `String.length` để cập nhật file offset.** Offset tính theo bytes.
15. **Decode từng chunk UTF-8 độc lập.** Có thể cắt giữa multi-byte character.
16. **Coi một read EOF là file sẽ không bao giờ có bytes mới.** Writer có thể append.
17. **Ghi qua EOF rồi mong gap tự bằng zero.** Nội dung gap không được chỉ định theo API.
18. **Chỉ xử lý callback completed, bỏ failed.** Workflow có thể treo/báo sai.
19. **Đóng channel ngay sau initiate handler.** Pending I/O có thể thất bại.
20. **Cho rằng async luôn nhanh hơn sync.** Benchmark workload và provider thực.
21. **Không giới hạn buffers/operations pending.** Nguy cơ áp lực memory, file descriptors và executor queue.
22. **Không kiểm soát file được mở/ghi.** Dùng temp files và options phù hợp; tránh truncate dữ liệu người dùng.

## 26. Ma trận kiểm thử

| Tình huống | Mong đợi đúng | Không nên hardcode |
| --- | --- | --- |
| ByteBuffer allocate5 | pos0 limit5 capacity5 | Nội dung array đã là dữ liệu file |
| Put/flip/get/compact | Giữ phần chưa tiêu thụ | Compact tự ghi ra file |
| Forced two-phase write 3+7 | File `ABCDEFGHIJ` 10 byte | Provider tự sinh partial write đúng 3+7 |
| Read file9 bằng buffer4 | Tổng byte9, EOF, nội dung khớp | Số bytes từng read luôn 4 |
| Read file3 vào buffer5 | Got3, EOF before full | Tự padding thêm 2 byte |
| Empty-buffer read | Có thể 0, không phải EOF | 0 tương đương -1 |
| Read at offset=size | -1 với destination còn chỗ | File không có thể append thêm |
| Handler write | Tổng 12 byte, buffer drained | Chỉ một callback luôn đủ |
| Positional write offset2 | `ABxyE`, size5 | FileOffset tự nối sau lần đầu |
| Copy file20 | bytesRead=20,bytesWritten=20 | File nguồn không đổi trong production |
| Negative read position | Bị từ chối | Offset âm được sửa thành 0 |
| Read into read-only buffer | Bị từ chối | Read-only buffer không thể làm write source |
| Write into READ-only channel | Bị từ chối | Channel tự nâng quyền WRITE |
| UTF-8 buffer3 | Byte count8, round-trip true | String.length==byte count |
| Concurrent writes | Buffers và regions độc lập khi cần | Completion theo thứ tự submit |
| Timeout | Caller chưa nhận kết quả đúng hạn | Pending operation chắc chắn bị hủy |
| I/O error | Failure propagate | Tự nhận n=0 rồi bỏ qua |
| Partial destination | Cần cleanup/publish policy | Write failure tự rollback |
| Provider support | API behavior theo hợp đồng | OS nào cũng trả cùng progress count |

Các chương trình dùng byte ASCII hoặc Unicode cố định, không in tên temp file và đợi completion trước khi quan sát. Do đó stdout ghi trong bài đã được kiểm thử trên JDK/Windows; **không đưa ra bảo đảm về thời gian, số lần partial operations hoặc throughput trên mọi provider**.

## 27. Bài tập và hướng giải

**Bài 1.** Buffer capacity10, put6, flip, get2, compact: pos/limit sau từng bước? **Đáp án:** sau put (6,10), flip (0,6), get2 (2,6), compact (4,10).

**Bài 2.** Buffer wrap `"hello"` có cần flip ngay trước write? **Không:** wrap đã sẵn để lấy bytes. Allocate+put thì phải flip.

**Bài 3.** File offset=100, một write chuyển 3 byte. Offset kế tiếp? **103**, không cộng capacity.

**Bài 4.** Một write buffer 6 byte trả lần lượt 2,1,3: cần mấy lần? **3**, cộng đúng n và dừng khi remaining0.

**Bài 5.** Muốn đọc chính xác 7 byte, reads trả 3,2,2: có clear buffer giữa ba reads không? **Không**, đang lấp đầy cùng destination.

**Bài 6.** File chỉ còn3 byte nhưng record cần5, kết quả tiếp theo -1: trả gì? **Truncated record/EOF**, không báo full success.

**Bài 7.** Buffer remaining0, read trả0: có phải EOF? **Không**, read EOF sentinel là -1.

**Bài 8.** Vì sao hai writes cùng offset0 có thể overwrite? **Không có current file position tự tiến**.

**Bài 9.** Timeout trong `Future.get`: có được clear buffer ngay? **Không**, operation có thể vẫn pending.

**Bài 10.** Handler phải làm gì khi kết quả n=3 nhưng buffer còn5 byte? **Tăng offset +3 và khởi tạo write tiếp** sau completion trước; xử lý failed rõ.

**Bài 11.** Hai concurrent reads cùng dùng một ByteBuffer có an toàn không? **Không**, dù channel thread-safe.

**Bài 12.** Hai buffers riêng nhưng cùng file region có an toàn không? **Không bảo đảm nội dung cuối** nếu ordering không được điều phối.

**Bài 13.** Trong copy, khi một write chỉ chuyển 2 byte từ block4, được clear để read block kế chưa? **Không**, phải ghi hai byte còn lại trước.

**Bài 14.** Buffer chứa `ABCDE` đã tiêu thụ `AB`, muốn thêm `FG` mà giữ `CDE`: dùng gì? **compact**.

**Bài 15.** Tại sao không decode từng chunk UTF-8 độc lập? **Ký tự đa byte có thể bị chia qua hai chunks**.

**Bài 16.** String.length có phải file offset byte count? **Không**.

**Bài 17.** `read(dst,-1L)`? **IllegalArgumentException**.

**Bài 18.** `asReadOnlyBuffer` có dùng làm đích read? **Không**. Có thể làm nguồn write? **Có** vì operation lấy bytes từ buffer.

**Bài 19.** Ghi vào offset lớn hơn EOF, gap được bảo đảm toàn zero? **Không**.

**Bài 20.** EOF của file log có writer append có phải kết thúc vĩnh viễn? **Không**, cần tail/publish policy.

**Bài 21.** Future write success có phải atomic durable transaction? **Không**.

**Bài 22.** Tại sao không dùng luôn direct buffer cho mọi file? **Chi phí/lifecycle/performance phụ thuộc workload**, cần benchmark.

**Bài 23.** Timeout5 giây cho mỗi operation có giới hạn cả 100-operation copy trong5 giây không? **Không**.

**Bài 24.** Hai operations outstanding ghi cùng vùng, chỉ một buffer? Cần gì? **Độc lập buffers và offset region, điều phối order**, không tự tin vào thread safety của channel.

**Bài 25.** Lập test mô phỏng provider trả n=2,1,3 cho buffer6. **Đáp án định hướng:** tách logic cập nhật offset/remaining, dùng fake adapter và assert tổng6, không phụ thuộc OS phát sinh partial write thật.

## 28. Checklist sử dụng trong dự án

- [ ] Xác định rõ số bytes cần đọc: tới EOF hay đúng N.
- [ ] File offset là `long`, luôn không âm.
- [ ] Buffer position/limit là `int`, không lấy capacity thay n.
- [ ] `read` nhận riêng `n>0`, `n==0`, `n==-1`.
- [ ] `write` kết thúc chỉ khi `!src.hasRemaining()`.
- [ ] File offset tăng đúng số byte thực tế từng operation.
- [ ] Không tự tăng buffer.position sau khi operation hoàn tất.
- [ ] Không clear/flip buffer sai thời điểm.
- [ ] Buffer được flip trước khi tiêu thụ bytes đã read.
- [ ] Khi còn bytes chưa tiêu thụ, cân nhắc compact.
- [ ] Không dùng buffer đang pending I/O cho operation khác.
- [ ] Không reuse buffer ngay khi timed get timeout.
- [ ] Không block nặng trong completion handler.
- [ ] Thực hiện cả completed và failed.
- [ ] Xử lý ExecutionException/InterruptedException/TimeoutException.
- [ ] Ghi/đọc đồng thời phải có buffer và offset ownership riêng.
- [ ] Không coi completion order theo thứ tự initiate.
- [ ] Không coi EOF hiện tại là không thể append thêm.
- [ ] Không decode UTF-8 mỗi block nếu ký tự có thể bị chia.
- [ ] Không dùng String.length làm byte count.
- [ ] Giới hạn memory, retries, concurrency và queue.
- [ ] Xử lý file đích partial nếu write thất bại.
- [ ] Cân nhắc snapshot, integrity, force và publish khi cần.
- [ ] Không ghi đè file thật để chạy ví dụ.
- [ ] Kiểm chứng trên provider/hệ điều hành sẽ triển khai thực tế.
- [ ] Giữ kiến thức API hiện hành; tiện ích `Files.writeString`/`readString` có từ Java 11, `CompletableFuture` từ Java 8, anonymous diamond từ Java 9, còn `AsynchronousFileChannel`/`ByteBuffer` APIs cốt lõi từ Java 7.

## 29. Tài liệu chính thức

- [Java SE 17 — `AsynchronousFileChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): explicit position, partial reads/writes, Future/handler, buffer concurrency, close, force.
- [Java SE 17 — `AsynchronousByteChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousByteChannel.html): read/write buffer remaining, zero-progress, EOF semantics.
- [Java SE 17 — `ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): buffer byte storage, allocate/wrap/direct, get/put.
- [Java SE 17 — `Buffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html): position, limit, capacity, flip/clear/compact.
- [Java SE 17 — `CompletionHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html): completed/failed.
- [Java SE 17 — `Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): waiting, cancellation, timeout.
- [Java SE 17 — `CharsetDecoder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html): xử lý ký tự đa byte qua boundaries.
- [Java SE 17 — `StandardOpenOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): các chế độ mở tệp.
- [Java SE 17 — `FileChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): đối chiếu position của channel đồng bộ.

**Kết luận:** Với `AsynchronousFileChannel`, **một I/O hoàn tất không đảm bảo buffer đã được đọc/ghi hết**. Hãy xử lý `n` thực tế, tăng explicit file offset theo n, để chính buffer quản lý position, dùng `flip/clear/compact` đúng chỗ, đọc đến EOF hoặc đúng N theo yêu cầu và ghi lặp tới khi `!hasRemaining`. Khi I/O còn pending, không sửa/recycle buffer; khi xử lý song song, phải điều phối offsets/ownership và errors. Đó là nền tảng tránh mất dữ liệu và ghi đè trong các luồng file I/O bất đồng bộ trên Java hiện đại.