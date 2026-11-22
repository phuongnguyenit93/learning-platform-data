# getChannel và trạng thái vị trí được chia sẻ trong truy cập ngẫu nhiên Java

Khi đọc hoặc ghi tệp bằng `RandomAccessFile`, ta có thể di chuyển con trỏ bằng `seek(long)` rồi gọi `read()` hoặc `write()`. Java NIO cung cấp `FileChannel` để thao tác với `ByteBuffer` và đọc/ghi tại một vị trí xác định. Điểm dễ nhầm: **`RandomAccessFile.getChannel()` trả về kênh gắn với cùng tệp đang mở và hai API dùng chung một trạng thái vị trí**.

Nếu một đoạn code gọi `raf.seek(100)` rồi một đoạn khác gọi `channel.read(buffer)`, con trỏ tệp của `raf` cũng tiến lên theo số byte thực đọc. Nếu tiếp đó gọi `raf.read()`, lần đọc này tiếp tục từ vị trí *sau* thao tác của channel. Hiểu đúng mối liên hệ đó là điều cần thiết khi kết hợp Java I/O truyền thống với NIO hoặc khi nhiều phương thức sử dụng chung đối tượng mở tệp.

## 1. Ba khái niệm vị trí cần phân biệt

### 1.1. File pointer của `RandomAccessFile`

`RandomAccessFile` là một đối tượng vừa đọc vừa ghi tùy chế độ mở, hỗ trợ truy cập ngẫu nhiên trong tệp. Đơn vị của `seek()` và `getFilePointer()` là **byte**, không phải số ký tự hay số phần tử trong mảng.

- `raf.getFilePointer()` trả về độ lệch byte hiện tại tính từ đầu tệp; byte đầu tiên ở vị trí 0.
- `raf.seek(offset)` đặt vị trí cho lần đọc/ghi tiếp theo. `offset` âm không hợp lệ.
- Các lần `read` hoặc `write` tuần tự sẽ di chuyển vị trí theo số byte đã tiêu thụ/ghi.
- Di chuyển `seek()` tới vị trí lớn hơn kích thước tệp **không tự làm tệp dài ra**. Ghi sau đó có thể làm tệp dài ra; nội dung khoảng trống phụ thuộc hệ thống tệp và API, không nên giả định an toàn là toàn byte 0.
- Đọc khi con trỏ ở hoặc sau EOF trả về `-1` với `read()`, trong khi `readFully(...)` ném `EOFException` nếu không đủ dữ liệu.

Một tệp có nội dung ASCII `ABCDEFGH` dài 8 byte có các vị trí 0–7 chứa dữ liệu; vị trí 8 là ngay sau byte cuối cùng (EOF).

### 1.2. File position của `FileChannel`

`FileChannel` có vị trí riêng ở cấp API, truy cập qua `channel.position()` và di chuyển qua `channel.position(newPosition)`. Lời gọi `channel.read(dst)` hoặc `channel.write(src)` **dùng vị trí hiện tại** rồi cập nhật nó theo số byte đọc/ghi thành công.

Riêng kênh lấy từ **`raf.getChannel()`**, Java quy định:

```text
RandomAccessFile.getFilePointer() == FileChannel.position()
                   (cùng một tệp mở)
```

Hai giá trị được đồng bộ về mặt ngữ nghĩa: thay đổi file pointer bằng `raf.seek()` hoặc I/O của `raf` làm thay đổi vị trí channel; thay đổi vị trí bằng `channel.position(...)` hoặc I/O tuần tự của channel làm thay đổi file pointer của `raf`. `getChannel()` trả về **FileChannel duy nhất gắn với đối tượng RandomAccessFile đó**.

Điều này **không có nghĩa** mọi `FileChannel` mở cùng tên tệp sẽ dùng chung vị trí. Một `FileChannel.open(path, ...)` độc lập, hoặc một `RandomAccessFile` khác tự mở đường dẫn đó, có trạng thái vị trí cho lần mở riêng. Chúng cùng thấy dữ liệu trên tệp khi thay đổi được hệ thống tệp phản ánh, nhưng không dùng chung con trỏ chỉ vì đường dẫn giống nhau.

### 1.3. Vị trí của `ByteBuffer`

`buffer.position()` là chỉ số trong **bộ đệm bộ nhớ**, không phải độ lệch trong tệp. Ví dụ, trước khi đọc `ByteBuffer.allocate(4)` có `position=0`; nếu channel đọc được 3 byte, vị trí buffer tăng lên 3. Vị trí tệp cũng có thể tăng 3 khi dùng `channel.read(buffer)`, nhưng đó là **hai trạng thái khác nhau**.

`buffer.flip()` chuẩn bị đọc những byte đã được nạp vào buffer: nó đổi `limit` và `position` của buffer, **không tua lại con trỏ của tệp**. `buffer.clear()` cũng chỉ thay đổi trạng thái của buffer, không xóa nội dung tệp và không đưa `FileChannel.position()` về 0.

## 2. Lời gọi nào làm di chuyển vị trí dùng chung?

Giả sử `raf` mở ở chế độ `"rw"`, `channel = raf.getChannel()` và ban đầu con trỏ đang ở byte 2.

| Thao tác | Tác động lên vị trí dùng chung |
| --- | --- |
| `raf.seek(10)` | Đặt con trỏ của cả `raf` và `channel` thành 10 |
| `raf.read()` | Nếu đọc được một byte, vị trí tăng 1; tại EOF trả `-1`, không tiêu thụ byte |
| `raf.write(byteValue)` | Ghi một byte tại vị trí hiện tại rồi tăng vị trí |
| `channel.position(5)` | Đặt vị trí của cả hai thành 5 |
| `channel.read(dst)` | Đọc từ vị trí hiện tại; vị trí tăng bằng số byte thực đọc (không nhất thiết bằng `dst.remaining()` ban đầu) |
| `channel.write(src)` | Ghi từ vị trí hiện tại; vị trí tăng bằng số byte thực ghi |
| `channel.read(dst, absoluteOffset)` | Đọc ở vị trí tệp cho trước; **không đổi** vị trí dùng chung |
| `channel.write(src, absoluteOffset)` | Ghi ở vị trí tệp cho trước; **không đổi** vị trí dùng chung |
| `buffer.flip()`, `buffer.rewind()`, `buffer.clear()` | Chỉ đổi trạng thái của `ByteBuffer`, không đổi vị trí tệp |

Hai dạng có tham số `long position` ở cuối, `FileChannel.read(ByteBuffer,long)` và `FileChannel.write(ByteBuffer,long)`, được gọi là **positional I/O**. Chúng **vẫn thay đổi `ByteBuffer.position()`** theo số byte đã xử lý, nhưng giữ nguyên `FileChannel.position()` / `raf.getFilePointer()`.

Lưu ý: tham số `position` của positional I/O là vị trí bắt đầu *trong tệp*, khác `buffer.position()`. Một lần đọc/ghi channel có thể xử lý ít byte hơn mức yêu cầu, vì vậy phải dùng **giá trị trả về** để tính tiếp, không giả định chỉ cần gọi một lần là đầy buffer.

## 3. Ví dụ Java 17+ chạy được: lần theo con trỏ từng bước

Tạo tệp **`SharedPositionDemo.java`** với nội dung sau. Chương trình sử dụng tệp tạm riêng, ghi chuỗi ASCII có độ dài xác định, thực hiện các thao tác theo thứ tự rồi xóa tệp tạm khi kết thúc.

```java
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class SharedPositionDemo {
    private SharedPositionDemo() {}

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("shared-position-", ".bin");
        try {
            try (RandomAccessFile raf =
                    new RandomAccessFile(file.toFile(), "rw")) {
                FileChannel channel = raf.getChannel();

                raf.write("ABCDEFGH".getBytes(StandardCharsets.US_ASCII));
                show("write 8 bytes", raf, channel);

                raf.seek(2);
                show("raf.seek(2)", raf, channel);

                ByteBuffer relative = ByteBuffer.allocate(2);
                readFully(channel, relative);
                relative.flip();
                System.out.println("channel.read -> " +
                        StandardCharsets.US_ASCII.decode(relative));
                show("after channel.read", raf, channel);

                System.out.println("raf.read -> " + (char) raf.read());
                show("after raf.read", raf, channel);

                channel.position(1);
                show("channel.position(1)", raf, channel);
                System.out.println("raf.read -> " + (char) raf.read());
                show("after raf.read again", raf, channel);

                ByteBuffer absolute = ByteBuffer.allocate(2);
                readFullyAt(channel, absolute, 6);
                absolute.flip();
                System.out.println("read at 6 -> " +
                        StandardCharsets.US_ASCII.decode(absolute));
                show("after positional read", raf, channel);

                ByteBuffer replacement =
                        ByteBuffer.wrap(new byte[] { (byte) 'Z' });
                writeFullyAt(channel, replacement, 0);
                show("after positional write", raf, channel);
            }

            System.out.println("file content -> " +
                    Files.readString(file, StandardCharsets.US_ASCII));
        } finally {
            Files.deleteIfExists(file);
        }
    }

    private static void show(String label,
                             RandomAccessFile raf,
                             FileChannel channel) throws IOException {
        System.out.println(label + ": raf=" + raf.getFilePointer() +
                ", channel=" + channel.position());
    }

    private static void readFully(FileChannel channel,
                                  ByteBuffer dst) throws IOException {
        while (dst.hasRemaining()) {
            int n = channel.read(dst);
            if (n < 0) {
                throw new IOException("Unexpected EOF");
            }
            if (n == 0) {
                throw new IOException("Read made no progress");
            }
        }
    }

    private static void readFullyAt(FileChannel channel, ByteBuffer dst,
                                    long offset) throws IOException {
        while (dst.hasRemaining()) {
            int n = channel.read(dst, offset + dst.position());
            if (n < 0) {
                throw new IOException("Unexpected EOF");
            }
            if (n == 0) {
                throw new IOException("Read made no progress");
            }
        }
    }

    private static void writeFullyAt(FileChannel channel, ByteBuffer src,
                                     long offset) throws IOException {
        while (src.hasRemaining()) {
            int n = channel.write(src, offset + src.position());
            if (n == 0) {
                throw new IOException("Write made no progress");
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac SharedPositionDemo.java
java SharedPositionDemo
```

Kết quả chuẩn của chương trình:

```text
write 8 bytes: raf=8, channel=8
raf.seek(2): raf=2, channel=2
channel.read -> CD
after channel.read: raf=4, channel=4
raf.read -> E
after raf.read: raf=5, channel=5
channel.position(1): raf=1, channel=1
raf.read -> B
after raf.read again: raf=2, channel=2
read at 6 -> GH
after positional read: raf=2, channel=2
after positional write: raf=2, channel=2
file content -> ZBCDEFGH
```

**Giải thích từng chuyển động:**

1. `raf.write("ABCDEFGH"...)` ghi 8 byte vào tệp tạm ban đầu rỗng nên con trỏ chuyển tới 8; channel nhìn thấy cùng vị trí.
2. `raf.seek(2)` đưa cả hai về byte 2, trước chữ `C`.
3. `channel.read(relative)` đọc `C`, `D` từ vị trí dùng chung. Lúc này con trỏ ở 4 và `raf.read()` đọc chữ `E`.
4. `channel.position(1)` đưa `raf` về byte 1; `raf.read()` đọc chữ `B`, khiến con trỏ tới 2.
5. `channel.read(absolute, 6)` lấy `G`, `H` ở vị trí tuyệt đối 6; cả hai con trỏ tệp vẫn ở 2.
6. `channel.write(replacement, 0)` thay byte đầu tiên thành `Z` nhưng vẫn giữ vị trí tệp là 2. Sau khi đóng `raf`, nội dung là `ZBCDEFGH`.

Các hàm `readFully` và `readFullyAt` lặp theo lượng dữ liệu thực đọc vì API `FileChannel.read` không đảm bảo một lần gọi sẽ lấp đầy buffer. `writeFullyAt` cũng tăng offset theo `src.position()` để hỗ trợ một lần ghi chưa hoàn tất. Ví dụ dùng tệp cục bộ thông thường; nó báo lỗi nếu một thao tác với dung lượng còn lại không tiến triển, thay vì lặp vô hạn. Nội dung ASCII giúp số byte và vị trí dễ dự đoán.

## 4. `read(dst)` và `read(dst, position)` khác nhau trong thực tế

Xét một phương thức cần đọc tiêu đề 4 byte ở đầu tệp, trong khi phương thức gọi đang duyệt bản ghi ở vị trí 500. Nếu viết:

```java
// Minh họa: channel đã khai báo và đang ở vị trí 500.
channel.position(0);
ByteBuffer header = ByteBuffer.allocate(4);
channel.read(header);
```

Phương thức này vừa **đặt lại vị trí dùng chung về 0**, vừa **đẩy nó lên theo số byte đã đọc**. Khi trở về, `RandomAccessFile` của bên gọi không còn ở 500. Nếu cố khôi phục bằng cách lưu vị trí rồi đặt lại, mọi thao tác xen giữa (đặc biệt trong chương trình nhiều luồng) vẫn có thể bị ảnh hưởng.

Dùng positional I/O để đọc một vùng độc lập:

```java
// Minh họa: channel đã khai báo, readable và còn mở.
ByteBuffer header = ByteBuffer.allocate(4);
long start = 0;
while (header.hasRemaining()) {
    int n = channel.read(header, start + header.position());
    if (n < 0) {
        throw new IOException("Header too short");
    }
    if (n == 0) {
        throw new IOException("No read progress");
    }
}
header.flip();
```

Đoạn này cần nằm trong phương thức xử lý `IOException` và có import `FileChannel`, `ByteBuffer`. Với `read(dst, position)`, trạng thái `position` của channel **và file pointer của `raf` không đổi**, dù `header.position()` tăng. Nếu muốn đọc cấu trúc có kích thước biến thiên, cũng nên kiểm tra giới hạn, kích thước tệp và trường hợp EOF trước khi cấp phát bộ đệm lớn.

Tương tự, nếu cần vá một trường trong tệp mà không làm gián đoạn vòng lặp đọc tuần tự, `channel.write(src, absolutePosition)` giúp ghi tại offset chỉ định mà không di chuyển vị trí dùng chung. Tuy nhiên thay đổi **nội dung** tệp vẫn có thể ảnh hưởng dữ liệu mà thao tác đọc khác sẽ gặp; positional I/O giải quyết vấn đề con trỏ, không tự tạo snapshot hay transaction.

## 5. Kích thước tệp, EOF và ảnh hưởng tới vị trí

**Vị trí (position)** và **kích thước (size/length)** là hai thông số khác nhau:

- `raf.length()` và `channel.size()` cùng phản ánh độ dài của tệp được mở, tính bằng byte.
- `raf.seek(offset)` hoặc `channel.position(offset)` có thể đặt offset lớn hơn kích thước tệp mà không tăng kích thước ngay.
- Đọc từ vị trí ở hoặc vượt EOF không tạo ra byte mới. Đọc từ channel có thể trả `-1` khi không còn dữ liệu.
- Ghi ở vị trí sau EOF có thể mở rộng tệp. Đừng nhầm byte do chương trình ghi với nội dung khoảng trống được tạo ra giữa EOF cũ và vùng ghi.
- `raf.setLength(newLength)` có thể **rút ngắn hoặc kéo dài** tệp. Khi kéo dài, giá trị của byte mới không được bảo đảm theo hợp đồng API. Nếu con trỏ đang vượt `newLength` sau lần gọi, nó được đặt lại bằng `newLength`.
- `channel.truncate(newSize)` chỉ rút ngắn khi `newSize` nhỏ hơn kích thước hiện có; không kéo dài tệp nếu `newSize` lớn hơn. Nếu vị trí hiện tại lớn hơn kích thước mới, nó cũng bị đưa về kích thước mới. Vì vậy `raf.getFilePointer()` và `channel.position()` vẫn cùng phản ánh thay đổi này.

Ví dụ ngắn, giả sử `raf` đang mở tệp 8 byte, `channel = raf.getChannel()`:

```java
// Minh họa, không phải chương trình độc lập.
raf.seek(100);      // Position = 100, length vẫn 8.
channel.truncate(4);
// Position của cả raf và channel = 4; length = 4.
```

Nếu một API thay đổi độ dài tệp, API còn lại sẽ thấy độ dài mới. **Đừng cố lưu trữ một bản sao kích thước tệp lâu dài** trong khi các đoạn code khác vẫn có thể ghi hoặc truncate.

### EOF không phải một vị trí "bị khóa"

Không có quy tắc nào buộc position luôn nhỏ hơn hoặc bằng size. Vị trí có thể vượt EOF. Điều quan trọng là đọc và ghi xử lý khác nhau: đọc không có dữ liệu trả dấu hiệu EOF, còn ghi có thể mở rộng tệp. Nếu chương trình cần một bản ghi ở offset nhất định, cần xác thực vùng byte đó thực sự tồn tại, thay vì dựa riêng vào phép `seek()` đã thành công.

### Mode mở tệp ảnh hưởng thao tác được phép

`new RandomAccessFile(file, "r")` mở để đọc; channel tương ứng không cho ghi. `"rw"` cho đọc/ghi; `"rws"` và `"rwd"` bổ sung yêu cầu đồng bộ cập nhật với thiết bị lưu trữ theo hợp đồng của `RandomAccessFile`. Mode đọc/ghi không quyết định có chia sẻ vị trí hay không: **kênh từ `getChannel()` vẫn gắn với cùng file pointer**.

## 6. Khả năng xảy ra lỗi khi nhiều thành phần dùng cùng con trỏ

Giả sử phương thức A thực hiện `raf.seek(100)`, kỳ vọng lần `raf.readFully(record)` kế tiếp đọc bản ghi ở byte 100. Nhưng trước lần đọc, phương thức B sử dụng `raf.getChannel()` và gọi `channel.position(0)` hoặc `channel.read(someBuffer)`. Lần đọc của A có thể đến từ vị trí ngoài ý muốn.

Đây là **lỗi phối hợp trạng thái**: việc mỗi lời gọi riêng lẻ đều hợp lệ không bảo đảm chuỗi `seek + read` là một giao dịch nguyên tử. Kịch bản nguy hiểm hơn khi hai luồng cùng sử dụng một `RandomAccessFile` hoặc channel được lấy từ nó.

Ba cách thiết kế rõ ràng:

1. **Một chủ sở hữu điều khiển vị trí tuần tự:** Toàn bộ thao tác `seek/read/write` được điều phối trong một thành phần, các thành phần khác không tự di chuyển vị trí.
2. **Positional I/O cho những thao tác độc lập:** Các lời gọi `channel.read(dst, offset)` và `channel.write(src, offset)` không phụ thuộc position dùng chung. Thích hợp với xử lý bản ghi có offset biết trước.
3. **Khóa nhất quán toàn bộ chuỗi thao tác liên quan đến vị trí:** Khi bắt buộc dùng `seek + read`, dùng **cùng một khóa ở tất cả code path có khả năng di chuyển vị trí**, bao gồm cả lời gọi đi qua `FileChannel`. Chỉ `synchronized(raf)` ở một nơi không giúp gì nếu nơi khác gọi channel mà không tham gia khóa đó.

Cần phân biệt **an toàn của bản thân FileChannel** với **tính nguyên tử của nghiệp vụ**. Hợp đồng của `FileChannel` cho phép sử dụng từ nhiều luồng; các hoạt động liên quan vị trí hoặc thay đổi kích thước tệp được điều phối theo quy tắc của channel. Tuy nhiên, điều đó không tự gộp hai lời gọi `seek()` và `read()` của ứng dụng thành một thao tác không thể bị chen giữa. Positional I/O giúp tránh đụng con trỏ, nhưng nếu hai luồng cùng ghi chồng lên vùng byte hoặc một luồng truncate trong lúc luồng khác đọc thì vẫn cần một chính sách đồng bộ dữ liệu.

### Ví dụ về phép đọc bản ghi tại offset cố định

Đây là **đoạn minh họa**, cần đặt trong phương thức xử lý `IOException` với `FileChannel channel` đã mở:

```java
long recordOffset = 128;
ByteBuffer record = ByteBuffer.allocate(16);

while (record.hasRemaining()) {
    int n = channel.read(record,
            recordOffset + record.position());
    if (n < 0) {
        throw new IOException("Incomplete record");
    }
    if (n == 0) {
        throw new IOException("Read made no progress");
    }
}
record.flip(); // Chỉ reset buffer để giải mã bản ghi.
```

Đoạn này đọc đủ 16 byte bắt đầu tại offset 128 mà không cần `channel.position(128)`, đồng thời không làm hỏng vòng lặp tuần tự dùng chung `raf`. Nếu bản ghi có độ dài/offset do dữ liệu bên ngoài cung cấp, hãy kiểm tra tràn số khi cộng offset và length cũng như kích thước tệp trước khi cấp phát bộ đệm; kiểm tra kích thước vẫn không chống được việc tệp bị sửa đồng thời.

## 7. Đóng tài nguyên và sự liên hệ giữa hai API

Kênh lấy bằng `raf.getChannel()` thuộc tài nguyên mở của `raf`, không phải một kênh tách biệt sở hữu file descriptor mới. Theo hợp đồng `RandomAccessFile`, đóng `raf` cũng đóng channel gắn với nó. Vì vậy không lưu channel vượt quá vòng đời của `raf` rồi kỳ vọng nó vẫn hoạt động.

Trong chương trình chính, chỉ dùng:

```java
try (RandomAccessFile raf = new RandomAccessFile(file.toFile(), "rw")) {
    FileChannel channel = raf.getChannel();
    // Làm việc với raf và channel trong cùng phạm vi.
}
```

Đoạn này là mẫu minh họa cần có `file` kiểu `Path` và các import thích hợp. Đóng `RandomAccessFile` cuối khối `try` cũng giải phóng channel. Tránh trộn lẫn quyền sở hữu vòng đời, chẳng hạn đóng channel giữa chừng rồi tiếp tục sử dụng `raf` như thể hai đối tượng hoàn toàn độc lập. Nếu muốn một channel hoàn toàn độc lập, hãy mở nó trực tiếp theo chính sách tài nguyên rõ ràng.

## 8. Lỗi thường gặp và cách khắc phục

| Ngộ nhận hoặc lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| `getChannel()` tạo con trỏ độc lập với `RandomAccessFile` | `raf.read()` đọc sai vị trí sau khi channel thao tác | Ghi nhớ file pointer và channel position của cùng lần mở được chia sẻ |
| Dùng `channel.position(offset); channel.read(dst)` như phép đọc "không tác dụng phụ" | Thay đổi vị trí bên gọi | Dùng `channel.read(dst, offset)` nếu muốn giữ vị trí |
| Cho rằng `read(dst)` luôn đọc đủ `dst.remaining()` | Cắt thiếu bản ghi hoặc tính sai offset | Dùng vòng lặp dựa trên số byte thực đọc; xử lý EOF |
| Cho rằng `ByteBuffer.flip()` sẽ tua lại tệp | Vị trí file pointer không thay đổi | Chỉ dùng `raf.seek()` hoặc `channel.position()` khi thực sự cần đổi vị trí tệp |
| Dùng `seek(offset)` như bằng chứng rằng dữ liệu ở offset đó tồn tại | Đọc EOF hoặc dữ liệu không hoàn chỉnh | Kiểm tra độ dài và xử lý kết quả đọc |
| Dùng nhiều luồng gọi xen kẽ `seek()` và `read()` | Bản ghi lấy từ vùng khác kỳ vọng | Một chủ sở hữu vị trí, khóa chung hoặc positional I/O |
| Giả định mọi lần mở cùng path chia sẻ con trỏ | Suy luận sai khi dùng hai channel độc lập | Phân biệt trạng thái mỗi lần mở với nội dung của cùng tệp |
| Đóng `raf` trong khi thành phần khác vẫn giữ `getChannel()` | Thao tác về sau trên channel đã đóng thất bại | Quản lý cùng vòng đời tài nguyên |
| Dùng positional I/O nhưng nghĩ dữ liệu được bảo vệ khỏi ghi đè | Con trỏ ổn định nhưng dữ liệu vẫn có thể bị sửa đồng thời | Có chiến lược đồng bộ nội dung tệp nếu cần |

Để tự kiểm tra, hãy thay đổi lần lượt `raf.seek(2)` thành `channel.position(2)`, và thay `channel.read(relative)` thành dạng `channel.read(relative, 2)`. Quan sát rằng cách đặt vị trí dùng chung vẫn cho cùng trạng thái, còn cách đọc với offset tường minh giữ nguyên con trỏ hiện tại. Thử thêm `raf.length()` và `channel.size()` sau các thao tác chỉ dịch chuyển con trỏ: kích thước vẫn là 8 byte cho tới khi có ghi mở rộng hoặc truncate.

**Ghi nhớ:** `RandomAccessFile.getChannel()` cho phép truy cập cùng tệp qua hai lớp API nhưng cũng ràng buộc chúng vào **một vị trí tuần tự dùng chung**. Các thao tác `seek()`, `position()` và I/O tương đối làm thay đổi vị trí đó; các thao tác `read/write` với **offset tệp tường minh** cho phép truy cập ngẫu nhiên mà không xáo trộn con trỏ, dù vẫn cần quản lý kích thước, vòng đời và truy cập đồng thời.