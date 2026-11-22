# Phân biệt `flush()`, `FileDescriptor.sync()` và `FileChannel.force()` trong Java

## 1. Vấn đề: “đã ghi” có nghĩa là đã bền vững chưa?

Ứng dụng ghi một bản ghi giao dịch, một tệp cấu hình hoặc nhật ký phục hồi. Lệnh `write()` đã trả về, chương trình đọc lại được dữ liệu, nhưng máy bị mất điện ngay sau đó. Có chắc những byte này còn nguyên khi khởi động lại không?

Trong Java I/O, cần phân biệt **dữ liệu đã ra khỏi bộ đệm do ứng dụng quản lý** với **yêu cầu đồng bộ dữ liệu xuống thiết bị lưu trữ**. Ba API thường bị nhầm là:

- `flush()` của `OutputStream`/`Writer`: đẩy dữ liệu đang được các lớp stream/writer đệm đến đích phía dưới, theo hợp đồng implementation; **không tự bảo đảm lưu xuống đĩa vật lý**.
- `FileDescriptor.sync()`: yêu cầu hệ thống đồng bộ các bộ đệm liên quan đến **descriptor** xuống thiết bị; chỉ có thể tác động lên dữ liệu đã đi xuống phía dưới descriptor.
- `FileChannel.force(boolean metaData)`: yêu cầu đồng bộ các cập nhật của **tệp gắn với channel** xuống thiết bị. Tham số `metaData` quyết định có yêu cầu đồng bộ metadata cùng nội dung hay không.

Mục tiêu của bài là hiểu chính xác **đường đi của dữ liệu**, thứ tự thao tác, mức bảo đảm và giới hạn của từng API, sau đó áp dụng vào những lần ghi có yêu cầu durability.

## 2. Các tầng bộ đệm từ ứng dụng đến storage

Một đường ghi byte đơn giản có thể đi qua nhiều tầng:

```text
Ứng dụng: write("ABC")
        |
        v
BufferedWriter / OutputStreamWriter / BufferedOutputStream
(đệm ký tự, trạng thái bộ mã hóa hoặc đệm byte trong JVM)
        |                 ^
        | flush()         | dữ liệu chưa flush có thể còn ở đây
        v
FileOutputStream / file descriptor / FileChannel
        |
        v
Hệ điều hành, filesystem và page cache
        |
        | sync() hoặc force(...)
        v
Thiết bị lưu trữ / dịch vụ lưu trữ thực tế
        |
        v
Khả năng tồn tại qua lỗi hệ thống
(phụ thuộc hợp đồng Java, OS, driver, thiết bị và môi trường)
```

Đây là sơ đồ khái niệm, không có nghĩa mọi chương trình đều có tất cả các tầng. Ví dụ ghi thẳng qua `FileChannel` không cần `BufferedOutputStream`; ghi qua `BufferedWriter` có thể trải qua cả bộ đệm ký tự và bước mã hóa.

Hai câu hỏi khác nhau:

1. **Visibility (nhìn thấy):** một người đọc khác hoặc một file handle mới có thể quan sát byte đã được đưa đến filesystem chưa?
2. **Durability (bền vững):** hệ thống đã hoàn tất lời gọi đồng bộ theo hợp đồng, nhằm giảm nguy cơ mất cập nhật khi lỗi/crash chưa?

Thấy dữ liệu bằng `Files.readString(path)` ngay sau `write()` **không chứng minh** dữ liệu đã được đồng bộ xuống thiết bị. Dữ liệu có thể được phục vụ từ page cache của hệ điều hành.

## 3. Bảng so sánh nhanh

| API | Tầng tác động trực tiếp | Khi nên dùng | Điều không nên suy ra |
| --- | --- | --- | --- |
| `BufferedOutputStream.flush()` | Đệm byte của stream và gọi `flush()` tầng dưới | Muốn đẩy dữ liệu đang ở bộ đệm JVM xuống sink bên dưới | Không phải cam kết `fsync` hoặc không mất dữ liệu khi mất điện |
| `BufferedWriter.flush()` / `OutputStreamWriter.flush()` | Đệm ký tự/encoder và luồng bên dưới theo hợp đồng | Muốn hoàn tất việc chuyển text đang đệm xuống luồng byte | Không xác nhận độ bền của file trên storage |
| `OutputStream.flush()` mặc định | Implementation mặc định không làm gì | Điểm mở rộng cho subclass | Không mặc định có đệm để xả |
| `FileOutputStream.flush()` | Kế thừa hành vi từ `OutputStream` | Không phải API đồng bộ thiết bị | Gọi riêng nó không tương đương `FileDescriptor.sync()` |
| `FileDescriptor.sync()` | Các system buffers liên quan descriptor | Muốn đồng bộ ghi qua descriptor tới thiết bị | Không xả hộ `BufferedOutputStream` chưa flush |
| `FileChannel.force(false)` | Dữ liệu file do channel cập nhật theo phạm vi bảo đảm | Cần force nội dung | Không yêu cầu đầy đủ metadata theo hợp đồng |
| `FileChannel.force(true)` | Nội dung và metadata theo phạm vi bảo đảm | Cần cả metadata | Không phải commit transaction nhiều file hay đồng bộ tên trong thư mục |
| `StandardOpenOption.DSYNC` / `SYNC` | Chính sách đồng bộ khi mở file | Muốn các cập nhật nội dung / nội dung và metadata được ghi đồng bộ | Không xả đệm byte riêng ở tầng ứng dụng chưa chuyển xuống channel |

**Mấu chốt:** `flush()` xử lý “byte đã đi qua lớp bọc chưa?”, còn `sync()/force()` xử lý “cập nhật đã được yêu cầu đẩy ra storage chưa?”. Với pipeline nhiều lớp, thường phải **flush trước, sync/force sau**.

## 4. `flush()`: đẩy bộ đệm ứng dụng xuống tầng dưới

### 4.1. Hợp đồng chung của `OutputStream.flush()`

`OutputStream` triển khai `Flushable`. Theo Java SE 17, `flush()` thể hiện yêu cầu rằng những byte được stream implementation giữ lại trong bộ đệm cần được chuyển ngay đến đích mà stream đó quản lý. Nếu đích là abstraction của hệ điều hành như file, **flush chỉ bảo đảm byte đã được chuyển cho hệ điều hành theo hợp đồng, không bảo đảm đã được ghi xuống thiết bị vật lý**.

Implementation mặc định của `OutputStream.flush()` không làm gì. Vì vậy câu “mọi `flush()` đều đẩy page cache xuống đĩa” là sai.

### 4.2. `BufferedOutputStream` có bộ đệm byte thật

`BufferedOutputStream` chứa một mảng byte nội bộ. Khi gọi `write(int)`, byte có thể chỉ ở trong mảng đó. `flush()` sẽ ghi các byte đang đệm ra `OutputStream` phía dưới và tiếp tục gọi `flush()` bên dưới.

```java
FileOutputStream raw = new FileOutputStream(file);
BufferedOutputStream buffered = new BufferedOutputStream(raw);

buffered.write('A');
// 'A' có thể còn trong bộ đệm của buffered, raw chưa nhận byte.

buffered.flush();
// Buffer đã đẩy 'A' xuống raw/FileOutputStream,
// nhưng chưa có cam kết tương đương fsync.

// Quản lý close bằng try-with-resources trong chương trình thật.
```

*Đoạn mã trên chỉ minh họa*: `file` cần là `File` hợp lệ, cần import và xử lý `IOException`. `flush()` có thể ném `IOException` nếu tầng dưới không nhận được dữ liệu.

Khi ghi một mảng rất lớn, một số stream có thể chuyển byte thẳng xuống tầng dưới mà không giữ toàn bộ trong buffer; điều này **không đổi ý nghĩa** của `flush()`.

### 4.3. Flush của writer còn liên quan mã hóa ký tự

`BufferedWriter` chứa ký tự; `OutputStreamWriter` chuyển ký tự thành byte theo charset. Nếu dữ liệu được gửi qua nhiều lớp:

```text
BufferedWriter
     |
     v
OutputStreamWriter (UTF-8)
     |
     v
BufferedOutputStream
     |
     v
FileOutputStream
```

Lời gọi `writer.flush()` ở tầng ngoài có nhiệm vụ đẩy dữ liệu đang đệm theo chuỗi wrapper xuống tầng dưới. Khi cần hoàn tất một file text độc lập, `close()` sau khi hoàn tất ghi sẽ xử lý vòng đời của writer; sau đó vẫn phải tách riêng yêu cầu durability của storage nếu nghiệp vụ cần.

Đừng gọi `flush()` trên một stream khác không phải tầng ngoài đang giữ dữ liệu và tin rằng mọi byte đều đã đi xuống descriptor. Ví dụ `fileOutputStream.getFD().sync()` **không** tự đọc và làm rỗng mảng trong `BufferedOutputStream` đang bọc `fileOutputStream`.

### 4.4. `flush()` không đồng nghĩa `close()`

- `flush()` giúp đẩy dữ liệu đang đệm mà **stream vẫn mở**.
- `close()` đóng tài nguyên; nhiều lớp buffered/writer xả dữ liệu khi đóng.
- `close()` không phải API portable hứa hẹn mọi file đã được sync xuống thiết bị.
- Với stream còn được dùng tiếp, `flush()` hợp lý khi giao thức yêu cầu phía nhận sớm thấy byte, nhưng không thay thế sync.
- Với resource phải kết thúc, dùng `try-with-resources` để đóng có kỷ luật và xử lý `IOException` có thể phát sinh trong `write`, `flush` hoặc `close`.

## 5. `FileDescriptor.sync()`: đồng bộ các bộ đệm của descriptor

`java.io.FileDescriptor` đại diện cho kết nối mức thấp tới file, socket hoặc resource do hệ điều hành quản lý. `FileOutputStream.getFD()` trả descriptor của stream file đó.

Phương thức:

```java
public void sync() throws SyncFailedException
```

Theo hợp đồng Java SE 17, `sync()` yêu cầu **các system buffers liên quan FileDescriptor** được đồng bộ với thiết bị cơ sở. Khi thành công với một file lưu trên physical storage, mục đích là đưa những bản sửa đổi đang ở bộ nhớ do hệ thống quản lý tới media liên quan, theo bảo đảm mà môi trường có thể thực hiện.

**Giới hạn rất quan trọng:** `sync()` chỉ tác động đến các bộ đệm **ở phía dưới FileDescriptor**. Các byte còn ở `BufferedOutputStream`, `BufferedWriter` hay bộ đệm do ứng dụng tự quản lý phải được **flush** hoặc ghi xuống descriptor trước.

Do đó, với `BufferedOutputStream`:

```java
buffered.write(recordBytes);
buffered.flush();       // 1. JVM buffer -> FileOutputStream/OS
file.getFD().sync();    // 2. Yêu cầu OS đồng bộ descriptor
```

Đoạn này minh họa logic thứ tự, cần khai báo đối tượng, import và xử lý các checked exceptions. Nó cũng giả định `file` chính là `FileOutputStream` nằm dưới `buffered`.

### `SyncFailedException` có ý nghĩa gì?

`FileDescriptor.sync()` có thể ném `SyncFailedException` khi không thể xả buffers hoặc hệ thống không bảo đảm được các buffer đã đồng bộ với thiết bị. Không nên bắt rồi lặng lẽ coi một giao dịch quan trọng là thành công; application phải chuyển lỗi đến tầng phù hợp (retry có kiểm soát, báo lỗi, không xác nhận commit).

`FileDescriptor.valid()` chỉ kiểm tra descriptor có đại diện kết nối đang mở/hợp lệ hay không; nó **không chứng minh** yêu cầu sync đã thành công.

## 6. Ví dụ Java 17+ chạy được: flush trước, sync sau

Ví dụ thực nghiệm sau thiết kế để chứng minh **khả năng nhìn thấy byte qua một file handle khác** khi byte còn trong buffer của Java. Nó **không** kiểm thử mất điện hoặc bảo đảm durability; các kết quả đọc tệp chỉ xác nhận byte đã xuống tầng thấp hơn.

Tạo **`FlushAndSyncDemo.java`**:

```java
import java.io.BufferedOutputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FlushAndSyncDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("flush-sync-", ".dat");

        try {
            try (FileOutputStream raw = new FileOutputStream(path.toFile());
                 BufferedOutputStream buffered =
                         new BufferedOutputStream(raw, 8192)) {

                buffered.write('A');
                System.out.println("before flush="
                        + Files.size(path));

                buffered.flush();
                System.out.println("after flush="
                        + Files.readString(path, StandardCharsets.US_ASCII));

                // 'B' mới chỉ nằm trong BufferedOutputStream.
                buffered.write('B');

                // sync() không xả byte vẫn còn trong buffered.
                raw.getFD().sync();
                System.out.println("sync before second flush="
                        + Files.readString(path, StandardCharsets.US_ASCII));

                buffered.flush();
                raw.getFD().sync();

                System.out.println("flush then sync="
                        + Files.readString(path, StandardCharsets.US_ASCII));
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Biên dịch/chạy trong thư mục chứa file:

```bash
javac FlushAndSyncDemo.java
java FlushAndSyncDemo
```

Stdout khi các thao tác I/O và `sync()` đều thành công:

```text
before flush=0
after flush=A
sync before second flush=A
flush then sync=AB
```

Giải thích thứ tự:

1. `Files.createTempFile` tạo tệp rỗng. `FileOutputStream` mở tệp để ghi; buffer 8192 byte của `BufferedOutputStream` giữ lại ký tự ASCII `A`, nên file vẫn dài 0 khi chưa flush.
2. `buffered.flush()` đẩy `A` xuống `FileOutputStream`. Một lần đọc khác có thể thấy `A`, nhưng điều đó **chưa chứng minh** byte đã bền vững khi thiết bị mất nguồn.
3. `buffered.write('B')` giữ thêm `B` trong memory của JVM. `raw.getFD().sync()` đồng bộ những gì đã đến descriptor, **không** chuyển `B` khỏi buffer ứng dụng; vì vậy lần đọc vẫn là `A`.
4. `buffered.flush()` tiếp tục gửi `B` xuống descriptor; `raw.getFD().sync()` sau đó yêu cầu đồng bộ. Lúc này file chứa `AB` theo đường đọc thông thường.
5. `try-with-resources` đóng stream và `finally` xóa tệp tạm.

Nếu `sync()` bị hệ thống từ chối, chương trình ném lỗi và stdout có thể dừng trước dòng cuối. Đừng suy luận từ output rằng bạn đã mô phỏng được power loss; Java không có API chuẩn tái tạo mất nguồn để chứng minh độ bền bằng một lần test thông thường.

## 7. `FileChannel.force(boolean metaData)`: đồng bộ theo file channel

`java.nio.channels.FileChannel` cung cấp:

```java
public abstract void force(boolean metaData) throws IOException
```

Mục đích là yêu cầu các cập nhật của **tệp gắn với FileChannel** được ghi xuống thiết bị chứa tệp. Theo Java SE 17:

- Nếu tệp trên **thiết bị lưu trữ cục bộ**, khi `force` hoàn tất thành công, Java công bố bảo đảm các thay đổi có liên quan từ lúc channel được tạo hoặc từ lần force trước đã được ghi tới thiết bị đó, trong **phạm vi các thao tác API được bảo đảm**.
- Nếu tệp không nằm trên thiết bị cục bộ (chẳng hạn một số kiểu filesystem mạng), Java **không** đưa ra cùng bảo đảm này.
- `force(false)` yêu cầu đồng bộ **nội dung** file; nó **không bắt buộc** đồng bộ đầy đủ metadata.
- `force(true)` yêu cầu đồng bộ **nội dung cùng metadata** của file. Việc chọn `true` có thể cần thêm I/O; ảnh hưởng chính xác của cờ phụ thuộc OS.
- `force` có thể thực hiện I/O cả khi channel mở chỉ để đọc do OS có thể cập nhật metadata như last-access time.
- `force` có thể ném `ClosedChannelException` nếu channel đã đóng hoặc `IOException` nếu lỗi I/O.

### 7.1. `metaData = false` và `metaData = true`

Metadata có thể bao gồm kích thước, mốc thời gian và các thuộc tính mà filesystem quản lý. Không nên dựa vào việc từng OS coi thuộc tính nào “cần thiết” hoặc “không cần thiết” khi force với `false`; hợp đồng Java chỉ chỉ định loại cập nhật cần force.

```java
try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.WRITE)) {

    // Giả sử write(...) đã đưa toàn bộ nội dung cần ghi vào channel.
    channel.force(false); // Yêu cầu force nội dung
    channel.force(true);  // Yêu cầu force nội dung + metadata
}
```

Đây là snippet (cần khai báo `path` và `write` tương ứng). Gọi cả hai liên tiếp **thường không cần thiết**: chọn đúng mức độ cho lần đồng bộ của nghiệp vụ. Nếu công việc đã gọi `force(true)` ở điểm cam kết, không cần gọi thêm `force(false)` chỉ để “an toàn gấp đôi”.

### 7.2. Những cập nhật được `FileChannel.force()` bao phủ

Java SE 17 bảo đảm `FileChannel.force()` đối với thay đổi tạo ra bằng **các phương thức do `FileChannel` định nghĩa**. Nếu channel lấy qua `getChannel()` của `FileOutputStream` hoặc `RandomAccessFile`, đừng tự suy rộng phạm vi bảo đảm ngoài tài liệu API; với code quan trọng, hãy dùng cùng pipeline ghi/force rõ ràng và kiểm tra hợp đồng triển khai.

Đặc biệt, việc sửa **`MappedByteBuffer`** tạo từ `FileChannel.map` có quy tắc riêng: `FileChannel.force()` **có thể hoặc không** force các cập nhật được tạo qua mapped buffer. Hãy dùng **`MappedByteBuffer.force()`** để yêu cầu đồng bộ thay đổi của vùng map theo hợp đồng API của mapped buffer.

`force()` không đọc hay làm rỗng một buffer do ứng dụng tự quản lý. Nếu ứng dụng có `BufferedOutputStream` ở phía trên, luôn chuyển byte xuống filesystem trước khi gọi force trên channel liên quan.

## 8. Ví dụ Java 17+ chạy được: force nội dung và metadata

Tạo **`FileChannelForceDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FileChannelForceDemo {
    private static void writeAll(FileChannel channel, String text)
            throws IOException {
        ByteBuffer buffer = ByteBuffer.wrap(
                text.getBytes(StandardCharsets.US_ASCII));

        while (buffer.hasRemaining()) {
            int written = channel.write(buffer);
            if (written == 0) {
                throw new IOException("FileChannel made no progress");
            }
        }
    }

    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("file-force-", ".txt");

        try {
            try (FileChannel channel = FileChannel.open(
                    path,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {

                writeAll(channel, "DATA");
                channel.force(false); // force nội dung

                writeAll(channel, "!");
                channel.force(true);  // force nội dung + metadata

                System.out.println("size=" + channel.size());
            }

            System.out.println("text="
                    + Files.readString(path, StandardCharsets.US_ASCII));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

```bash
javac FileChannelForceDemo.java
java FileChannelForceDemo
```

Stdout khi cả hai lần force thành công:

```text
size=5
text=DATA!
```

Điểm chính:

1. `FileChannel.open` mở file đã tồn tại với quyền ghi, chế độ `TRUNCATE_EXISTING` đặt length về 0. Tùy môi trường, mở/ghi/force có thể ném `IOException`.
2. `writeAll` ghi đến khi hết byte trong `ByteBuffer`; nó không mặc định một `channel.write` đã ghi đủ dữ liệu.
3. `force(false)` ở lần đầu yêu cầu đồng bộ nội dung `DATA`.
4. Sau khi ghi dấu `!`, `force(true)` yêu cầu đồng bộ nội dung mới và metadata theo hợp đồng.
5. `size()` và lần đọc sau khi đóng xác nhận logical content của file là `DATA!`. **Chúng không kiểm thử khả năng sống sót qua mất điện.**

Không bao giờ coi `System.out.println("text=DATA!")` là bằng chứng thiết bị đã thực thi thành công mọi cơ chế chống mất điện. Bằng chứng ở đây là **`force` trả về mà không ném lỗi**, dưới đúng phạm vi bảo đảm của API và môi trường lưu trữ.

## 9. Ba API là ba mức khác nhau, không thay thế trực tiếp

Ví dụ cùng payload `"ORDER=42"`, có ba cách xử lý:

**Chỉ ghi rồi flush:**

```java
buffered.write(bytes);
buffered.flush();
```

Ý nghĩa: đẩy những byte đang ở bộ đệm ứng dụng xuống stream bên dưới, để phía nhận/OS sớm tiếp nhận. Thích hợp khi yêu cầu là đưa dữ liệu ra tầng kế tiếp, **không đủ** để hứa dữ liệu sống sót qua hệ thống crash.

**Ghi rồi flush và sync descriptor:**

```java
buffered.write(bytes);
buffered.flush();
rawFileOutputStream.getFD().sync();
```

Ý nghĩa: sau khi byte đã đi tới file descriptor, yêu cầu đồng bộ các system buffers liên quan descriptor.

**Ghi thẳng qua FileChannel rồi force:**

```java
ByteBuffer buffer = ByteBuffer.wrap(bytes);
while (buffer.hasRemaining()) {
    channel.write(buffer);
}
channel.force(true);
```

Ý nghĩa: với file channel, yêu cầu đồng bộ các cập nhật của file bao gồm metadata theo hợp đồng Java. Đoạn này giả định file channel mở `WRITE`, `bytes` đã có và không có đường ghi song song chưa được phối hợp.

Ba snippet này **không phải chương trình độc lập**; chúng mô tả các mô hình ứng dụng lựa chọn tùy API gốc. Không ghép ngẫu nhiên descriptor của file A với channel của file B rồi tưởng toàn bộ dữ liệu đã được đồng bộ.

## 10. Chọn `StandardOpenOption.SYNC` hoặc `DSYNC` khi nào?

Ngoài việc gọi `force()` sau một nhóm thao tác, Java NIO có option mở tệp yêu cầu ghi đồng bộ:

- `StandardOpenOption.DSYNC`: yêu cầu mỗi cập nhật **nội dung** file được ghi đồng bộ tới thiết bị.
- `StandardOpenOption.SYNC`: yêu cầu mỗi cập nhật **nội dung hoặc metadata** file được ghi đồng bộ tới thiết bị.

Ví dụ:

```java
try (FileChannel ch = FileChannel.open(
        path,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.DSYNC)) {

    // Các lần ch.write(...) thực hiện theo chế độ DSYNC.
}
```

Đây là snippet; cần `Path path`, import, và xử lý `IOException`. Không có ý nghĩa chọn `DSYNC` trên `BufferedOutputStream` nếu byte vẫn chưa được chuyển xuống `FileChannel`: option trên file channel không ép một buffer tầng ứng dụng khác phải flush.

**Khác biệt về hiệu năng:** gọi `force` theo batch thường ít lần đồng bộ hơn so với yêu cầu sync ở **mỗi lần cập nhật**. Đổi lại, nếu crash trước checkpoint force, các thay đổi từ checkpoint trước có thể chưa bền vững. Mô hình `SYNC/DSYNC` có thể tăng độ trễ cho từng lần ghi. Quyết định dựa trên yêu cầu mất dữ liệu tối đa được chấp nhận, kích thước batch, latency và đặc điểm filesystem.

Nếu chạy trên provider đặc biệt hoặc hệ thống tệp không hỗ trợ option yêu cầu, `FileChannel.open` có thể ném ngoại lệ. Không giả định độ bền và hiệu suất giống nhau trên volume mạng, bộ nhớ tạm, thiết bị ảo hoặc container.

## 11. Trường hợp `MappedByteBuffer`: phải hiểu đúng `force()` của map

Một vùng file mapping được lấy từ `FileChannel.map` có thể cho phép đọc/ghi trực tiếp qua `MappedByteBuffer`:

```java
try (FileChannel ch = FileChannel.open(
        path,
        StandardOpenOption.READ,
        StandardOpenOption.WRITE)) {

    MappedByteBuffer map = ch.map(
            FileChannel.MapMode.READ_WRITE, 0, 4096);

    map.put(0, (byte) 42);
    map.force();
}
```

**Đoạn mã minh họa, không độc lập**; nó giả định file/OS hỗ trợ vùng map tương ứng (mapping có thể làm dài file theo ngữ nghĩa API khi cần), cần import và xử lý exception. Quan trọng là:

- `FileChannel.force()` được Java 17 mô tả là **có thể hoặc không** bao phủ cập nhật qua mapped buffer.
- `MappedByteBuffer.force()` được thiết kế để yêu cầu các thay đổi của buffer mapping được ghi xuống thiết bị chứa mapped file (có giới hạn tương tự tùy loại thiết bị/OS/provider).
- Với chương trình thực tế, cần kiểm tra cách xử lý vòng đời map, giới hạn mapping, đồng bộ các luồng và lỗi khi thiết bị/region không còn truy cập được.

Không dùng một lệnh `channel.force(true)` như bảo đảm tổng quát cho mọi thay đổi từng được thực hiện qua `MappedByteBuffer`.

## 12. Durability chưa đồng nghĩa transaction hay atomicity

`sync()` hoặc `force()` giải quyết **đồng bộ dữ liệu**, không thay thế:

1. **Tính nguyên tử của nhiều lệnh ghi:** một ghi lớn hoặc nhiều record có thể chỉ ghi được một phần nếu ứng dụng/hệ thống thất bại giữa chừng. `force()` không biến chuỗi ghi thành “all-or-nothing”.
2. **Tính nhất quán của định dạng:** header và payload có thể không tương thích sau crash nếu không thiết kế thứ tự ghi, version, checksum hoặc log phục hồi.
3. **Tính nguyên tử thay thế file:** muốn publish một cấu hình mới, chiến lược thường là ghi file tạm cùng directory, force nội dung, sau đó đổi tên/move phù hợp. `Files.move` với `ATOMIC_MOVE` chỉ bảo đảm thao tác đổi tên/move mang tính atomic **nếu filesystem hỗ trợ**, không mặc nhiên đồng bộ bền vững cả directory entry.
4. **Tính bền vững của metadata thư mục:** force file không tự là một lời hứa portable rằng tên mới, thao tác tạo hoặc rename ở parent directory cũng đã được đồng bộ. Java SE không cung cấp một API cross-platform đơn giản bảo đảm `fsync(parent-directory)` trên mọi provider.
5. **Giao dịch nhiều file:** sync từng file không cung cấp commit nguyên tử của cả tập file. Cần transaction protocol hoặc hệ thống lưu trữ thiết kế cho yêu cầu ấy.

Một crash-safe protocol có thể cần record header, checksums, write-ahead log, commit marker và recovery logic. `flush/sync/force` chỉ là **một phần của thiết kế** đó.

### Ví dụ quy trình lưu cấu hình an toàn hơn

Với tệp cấu hình dùng để thay thế bản cũ:

```text
1. Tạo file tạm trong cùng thư mục với file chính.
2. Ghi toàn bộ nội dung mới và kiểm tra lỗi.
3. FileChannel.force(true) trên file tạm (sau khi dữ liệu đã tới channel).
4. Đóng channel/file tạm.
5. Files.move(temp, target, ATOMIC_MOVE, ...), nếu provider hỗ trợ.
6. Giải quyết durability của thao tác đổi tên/directory theo OS,
   filesystem và yêu cầu ứng dụng.
```

Đây là **luồng thiết kế**, không phải bảo đảm portable crash-safety chỉ bằng năm bước đầu. Nếu `ATOMIC_MOVE` không hỗ trợ, có thể nhận `AtomicMoveNotSupportedException`. Việc thay thế file đích và cách hoạt động của option bổ sung phải được xác định theo hợp đồng và filesystem; không tự giả định rollback hoặc không mất dữ liệu khi crash ở mọi thời điểm.

## 13. Đường ghi và trách nhiệm khi dùng nhiều lớp

Có ba kiểu kiến trúc thường gặp:

### A. Text log được đệm trong JVM

```text
BufferedWriter --> OutputStreamWriter --> BufferedOutputStream
                  --> FileOutputStream --> file descriptor --> filesystem
```

Nếu nghiệp vụ yêu cầu mỗi nhóm log phải sync, hãy flush **lớp writer ở ngoài cùng**, sau đó gọi `FileDescriptor.sync()` của đúng `FileOutputStream` bên dưới. Gọi `sync` trước `flush` không bao phủ byte còn trong writer hoặc buffered output stream.

### B. NIO file batch writer

```text
domain records --> encode thành ByteBuffer --> FileChannel.write(...)
                                      --> FileChannel.force(true/false)
```

Không có `BufferedOutputStream`, nên không có `flush()` ở kiểu API đó. `ByteBuffer.flip()` / `clear()` là thao tác **quản lý trạng thái bộ đệm dữ liệu**, không phải yêu cầu file sync. Đảm bảo mọi byte đã được `write` hết trước khi force.

### C. Kết hợp FileOutputStream và channel liên kết

`FileOutputStream.getChannel()` trả channel gắn với stream. Việc ghi qua stream và channel liên quan đến cùng file position/file connection nên phải được phối hợp. Nếu dùng `BufferedOutputStream` bọc stream, **flush lớp buffered** trước khi gọi bất cứ yêu cầu đồng bộ nào trên descriptor/channel.

Không nên đồng thời ghi byte qua nhiều thread ở hai kiểu API khác nhau mà thiếu kiểm soát thứ tự; flush và sync chỉ có ý nghĩa nếu ứng dụng xác định rõ tập byte nào thuộc checkpoint cần commit.

## 14. Hiệu năng, nhóm checkpoint và các giới hạn môi trường

Force có chi phí I/O; tần suất gọi có thể ảnh hưởng đáng kể độ trễ và throughput. Khi thiết kế một batch writer, có thể chọn:

- **Durability cao, mỗi record quan trọng:** ghi đủ record, sync/force trước khi báo “đã cam kết” cho bên gọi.
- **Group commit:** gom một nhóm record hợp lệ, sau đó force một lần; chỉ xác nhận những record tương ứng khi checkpoint hoàn tất.
- **Best effort output/log:** flush theo batch để dữ liệu sớm nhìn thấy; nếu chấp nhận mất đoạn log cuối khi crash, có thể không cần sync mỗi lần.

Lựa chọn không chỉ phụ thuộc mức nhanh/chậm mà phụ thuộc yêu cầu dữ liệu: bản ghi thanh toán, file checkpoint, cache có thể tái tạo hay log chẩn đoán có mức ưu tiên khác nhau.

Giới hạn cần nói rõ:

- Với filesystem **không cục bộ**, hợp đồng `FileChannel.force` không đưa cùng lời hứa như thiết bị local; storage server, cache, replication và network có chính sách riêng.
- Với thiết bị/driver có cache volatile hoặc thông báo đồng bộ không đáng tin, API Java không thay thế quy trình đánh giá durability của toàn bộ storage stack.
- Không kiểm chứng durability bằng cách chạy `Files.readAllBytes` ngay sau ghi rồi kết luận “đã an toàn khi mất điện”; OS page cache có thể trả byte mới.
- `IOException` hoặc `SyncFailedException` nghĩa là không thể xác nhận yêu cầu đồng bộ thành công; đừng trả về “committed” nếu cần bảo đảm dữ liệu.
- `force(true)` không tự sửa lỗi mất tính nguyên tử của update nhiều file hoặc nhiều bước nghiệp vụ.

## 15. Những lỗi phổ biến cần tránh

1. **“`flush` tương đương `fsync`.”** Sai. `flush` của stream thường đẩy bộ đệm ứng dụng xuống sink bên dưới; nó không hứa storage vật lý đã ghi xong.
2. **“Gọi `FileDescriptor.sync` trước flush vẫn giữ mọi record mới.”** Sai với byte còn nằm trong `BufferedOutputStream` hoặc các writer. Cần flush đúng lớp ngoài trước.
3. **“`FileOutputStream.flush` là chức năng đặc biệt để sync đĩa.”** Sai; `FileOutputStream` kế thừa `OutputStream.flush` mặc định, không phải lựa chọn thay `getFD().sync()`.
4. **“Cứ `force(false)` là metadata luôn bền vững.”** Không có bảo đảm yêu cầu force đầy đủ metadata từ cờ `false`.
5. **“`force(true)` là transaction commit toàn hệ thống.”** Không. Nó xử lý phạm vi cập nhật của một file theo hợp đồng, không commit nguyên tử nhiều file/directory.
6. **“`FileChannel.force` luôn bao phủ mapped buffer.”** Không chắc. Sửa file qua `MappedByteBuffer` nên dùng API force của vùng map.
7. **“Có thể thấy nội dung từ JVM khác nghĩa là file đã sync.”** Sai. Visibility có thể đến từ page cache.
8. **“`close` đồng nghĩa force.”** Không nên suy diễn; gọi yêu cầu đồng bộ rõ ràng nếu durability là tiêu chí.
9. **“Một lệnh `FileChannel.write(ByteBuffer)` luôn ghi hết buffer.”** Không bảo đảm. Kiểm tra `hasRemaining()` và số byte thực ghi, xử lý lỗi trước khi force.
10. **“Thêm `force(true)` khắp mọi nơi chỉ làm an toàn hơn.”** Có thể làm giảm throughput, tăng latency nhưng vẫn không giải quyết atomicity hoặc recovery protocol.
11. **“`SYNC` và `DSYNC` ép buffered writer tự flush.”** Sai. Option đặt trên open file, byte ở bộ đệm ứng dụng phải được chuyển xuống channel trước.
12. **“Nếu `sync` thành công thì không cần kiểm tra tính nhất quán dữ liệu.”** Không đủ. Trường hợp crash giữa nhiều record vẫn cần định dạng phục hồi phù hợp.

## 16. Bài tập vận dụng

### Bài tập A — dự đoán dữ liệu nhìn thấy

Một file ban đầu rỗng được bọc bởi `BufferedOutputStream` có capacity lớn hơn 100 byte. Sau:

```java
buffered.write('X');
raw.getFD().sync();
```

Tại thời điểm này, bạn **không được khẳng định** `X` đã đến descriptor. Vì sao? Hãy thêm thao tác đúng vị trí và giải thích sự khác nhau giữa visibility và durability.

### Bài tập B — ghi nhóm record

Một chương trình ghi 100 record vào `FileChannel`, sau đó gọi `force(true)` và mới xác nhận với người dùng. Nếu lỗi xảy ra sau record 90, trước khi force, các record nào có thể được xem là đã cam kết theo chính sách này? Thiết kế metadata nào giúp phân biệt record hoàn chỉnh và record dở?

### Bài tập C — cờ metadata

Nếu hệ thống chỉ quan tâm byte nội dung, `force(false)` có đủ ý nghĩa gì? Nếu cần bảo đảm cả metadata theo hợp đồng, nên chọn cờ nào? `force(true)` có bảo đảm directory entry của thao tác đổi tên file khác không?

### Bài tập D — log trong bộ nhớ map

Một file được sửa bằng `MappedByteBuffer.put`. Có thể chỉ gọi `FileChannel.force(true)` để khẳng định các thay đổi ở map đã được force không? API nào trực tiếp đảm nhận đồng bộ cập nhật từ mapped buffer?

### Bài tập E — mở file với `DSYNC`

Nếu ghi một triệu byte qua `BufferedOutputStream` trên một file open với `DSYNC` mà chưa flush buffer, bạn có thể kết luận từng byte đã xuống thiết bị chưa? Hãy phân tích ranh giới giữa buffer ứng dụng và option của file.

## 17. Tự kiểm tra kiến thức

1. `OutputStream.flush()` mặc định có làm thao tác gì không? Khi nào implementation cụ thể như `BufferedOutputStream` cần override?
2. `FileDescriptor.sync()` dùng từ `FileOutputStream` qua phương thức nào, và có ngoại lệ chuyên biệt gì?
3. Giải thích vì sao cần `buffered.flush()` **trước** `raw.getFD().sync()`.
4. `FileChannel.force(false)` và `FileChannel.force(true)` khác nhau thế nào? Tại sao chọn `false` không đồng nghĩa mọi metadata được force?
5. `FileChannel.force` có bảo đảm gì nếu file ở thiết bị local? Với remote filesystem thì sao?
6. Tại sao `MappedByteBuffer.force()` xuất hiện khi bài toán sửa vùng memory-mapped file?
7. `Files.readString(path)` đọc đúng ngay sau ghi có chứng minh dữ liệu bền vững sau mất điện không?
8. Tại sao đồng bộ file tạm rồi atomic rename vẫn cần suy nghĩ thêm về durability của thư mục cha?
9. Khi nào group commit giúp giảm I/O sync, và nó đổi thời điểm xác nhận “committed” như thế nào?
10. Phân biệt `SYNC/DSYNC` lúc mở file với `force` theo checkpoint sau nhiều lần ghi.

## 18. Tài liệu chính thống

- [Java SE 17 — `OutputStream.flush()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html#flush()).
- [Java SE 17 — `BufferedOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedOutputStream.html).
- [Java SE 17 — `FileDescriptor.sync()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileDescriptor.html#sync()).
- [Java SE 17 — `FileChannel.force(boolean)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html#force(boolean)).
- [Java SE 17 — `StandardOpenOption.SYNC` và `DSYNC`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html).
- [Java SE 17 — `MappedByteBuffer.force()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html#force()).

## 19. Ghi nhớ

`flush()` trả lời câu hỏi **“byte đang đệm ở tầng ứng dụng đã được chuyển xuống sink bên dưới chưa?”**. `FileDescriptor.sync()` và `FileChannel.force()` là yêu cầu **đồng bộ cập nhật đã đến tầng file/descriptor với thiết bị lưu trữ** theo những hợp đồng và giới hạn cụ thể.

Khi có bộ đệm ứng dụng, thứ tự cơ bản là **ghi đủ → flush đúng lớp ngoài → sync/force đúng tài nguyên → chỉ xác nhận khi đồng bộ thành công**. `force(false)` tập trung vào nội dung, `force(true)` yêu cầu cả metadata; với memory-mapped file, dùng `MappedByteBuffer.force()` cho những cập nhật qua map. Đối với giao dịch phải sống sót qua crash, còn cần xem xét atomicity, định dạng record, recovery, directory durability và giới hạn của storage stack.
