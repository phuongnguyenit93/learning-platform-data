# FileChannel: Append và các hành vi phụ thuộc hệ điều hành

Khi viết vào cuối file bằng Java NIO, lựa chọn `StandardOpenOption.APPEND` ảnh hưởng trực tiếp đến **vị trí ghi**, **khả năng nhiều tiến trình cùng ghi** và **tính nhất quán dữ liệu**. Một chương trình chạy đúng trên máy phát triển chưa chắc đã có cùng đặc tính nguyên tử, khóa file, độ bền dữ liệu hay quyền truy cập khi chạy trên hệ điều hành và filesystem khác.

Bài này tập trung vào `java.nio.channels.FileChannel`: append khác gì `position(size())`, cách mở channel an toàn, vòng lặp ghi đủ byte, giới hạn atomicity, file locking, `force`/`SYNC`/`DSYNC` và các khác biệt thường gặp giữa filesystem cục bộ, mạng và các nền tảng triển khai.

## 1. Append thực sự có nghĩa gì?

`FileChannel` làm việc với hai vị trí khác nhau:

- **File position**: offset byte kế tiếp của channel, truy cập qua `channel.position()` và điều chỉnh bằng `position(long)`.
- **Buffer position**: byte kế tiếp trong `ByteBuffer` được đưa vào `write(buffer)`; tăng theo số byte thực sự đã ghi.

Trong chế độ thông thường (không có `APPEND`), một phép `write(buffer)` bắt đầu ở **vị trí hiện tại của FileChannel**. Ở chế độ `APPEND`, mỗi lần gọi **relative write** sẽ chuyển vị trí file tới **cuối file hiện tại** rồi ghi dữ liệu.

```text
File ban đầu:       [A][B][C]
                    0  1  2   EOF=3

WRITE thông thường, position(1), ghi "X":
                    [A][X][C]
                    Không tự động thêm ở cuối.

APPEND, ghi "X":
                    [A][B][C][X]
                    Phép ghi đi tới cuối file trước khi ghi.
```

Điều quan trọng: chuẩn API **không cam kết** việc “đặt vị trí tới EOF + ghi dữ liệu” diễn ra như **một thao tác nguyên tử** trên mọi hệ điều hành. Vì vậy không thể suy ra hai writer đồng thời sẽ tự động ghi thành những bản ghi độc lập, đầy đủ, không bị xen kẽ.

## 2. Mở FileChannel: APPEND và các OpenOption liên quan

Dạng thông dụng:

```java
try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.APPEND)) {
    // Ghi vào cuối file bằng channel.write(buffer).
}
```

Đây là snippet: `path` là `Path` hợp lệ và cần import `java.nio.channels.FileChannel` cùng `java.nio.file.StandardOpenOption`. Tham số `APPEND` đã ngụ ý mở để ghi; thêm `WRITE` khiến ý định rõ ràng hơn.

| Tùy chọn | Hành vi | Lưu ý |
| --- | --- | --- |
| `WRITE` | Cho phép ghi file; thường bắt đầu ở offset 0 khi không APPEND. | Ghi từ đầu **ghi đè byte tương ứng**, không xóa tất cả nội dung cũ. |
| `APPEND` | Mỗi relative `write` ghi từ cuối file đang có. | Độ nguyên tử của thao tác đi tới EOF rồi ghi phụ thuộc hệ thống. |
| `CREATE` | Mở file có sẵn hoặc tạo nếu chưa có khi mở ghi. | **Không** có nghĩa truncate file đã tồn tại. |
| `CREATE_NEW` | Tạo file mới và thất bại nếu đã tồn tại. | Kiểm tra tồn tại và tạo mới là nguyên tử theo giao ước API/provider. |
| `TRUNCATE_EXISTING` | Xóa nội dung file đang có về độ dài 0 khi mở ghi. | **Không dùng cùng APPEND**. |
| `READ` | Cho phép đọc file. | **Không dùng cùng APPEND** theo hợp đồng `FileChannel.open`. |
| `SYNC` | Yêu cầu đồng bộ cả cập nhật nội dung và metadata xuống thiết bị lưu trữ. | Có thể chậm; tác dụng thực tế phụ thuộc môi trường I/O. |
| `DSYNC` | Yêu cầu đồng bộ cập nhật nội dung xuống thiết bị lưu trữ. | Không nên suy ra mọi metadata đã bền vững. |
| `DELETE_ON_CLOSE` | Cố gắng xóa file khi đóng channel. | Hành vi *best effort*, không phải cam kết xóa được trên mọi OS. |
| `SPARSE` | Gợi ý sử dụng sparse file khi tạo mới. | Chỉ là hint; provider/filesystem có thể bỏ qua. |

Các tổ hợp **không hợp lệ**:

```java
// Không hợp lệ: APPEND không đi kèm READ.
FileChannel.open(path, StandardOpenOption.APPEND,
        StandardOpenOption.READ);

// Không hợp lệ: APPEND không đi kèm TRUNCATE_EXISTING.
FileChannel.open(path, StandardOpenOption.APPEND,
        StandardOpenOption.TRUNCATE_EXISTING);
```

Đây là **ví dụ phản diện** để chỉ ra cấu hình sai, không được chạy trong chương trình sản xuất. Các tổ hợp không hợp lệ thường gây `IllegalArgumentException` khi mở channel. Nếu muốn đọc rồi append, hãy đọc qua một channel riêng, sau đó đóng/mở channel append; hoặc thiết kế luồng xử lý phù hợp mà không đưa `READ` vào cùng bộ tùy chọn APPEND.

**Lưu ý:** `CREATE_NEW` có ý nghĩa tránh ghi đè khi tạo **lần đầu**. Nó không giúp nhiều writer đồng thời serialize các lần append **sau khi file đã tồn tại**.

## 3. Ví dụ Java 17+: append hai dòng, rồi ghi đè đầu file

Chương trình dưới đây tạo file tạm riêng, đi qua hai cơ chế để thấy rõ chúng khác nhau:

1. Ghi nội dung ban đầu `seed\n`.
2. Dùng `APPEND` để thêm `one\n` và `two\n`.
3. Đóng channel, mở lại chỉ với `WRITE`, đặt file position về 0 và ghi `HEAD\n`; do có cùng số byte với `seed\n`, phần append phía sau được giữ nguyên.
4. Đọc lại nội dung, kiểm tra kích thước byte và xóa file sau khi các handle đã đóng.

Lưu thành **`FileChannelAppendDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FileChannelAppendDemo {

    private static ByteBuffer utf8(String value) {
        return ByteBuffer.wrap(
                value.getBytes(StandardCharsets.UTF_8));
    }

    private static void writeFully(FileChannel channel, ByteBuffer data)
            throws IOException {
        while (data.hasRemaining()) {
            int written = channel.write(data);
            if (written == 0) {
                throw new IOException("Ghi file không có tiến triển");
            }
        }
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("filechannel-append-", ".txt");
        try {
            Files.writeString(file, "seed\n", StandardCharsets.UTF_8);

            try (FileChannel append = FileChannel.open(
                    file,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.APPEND)) {
                writeFully(append, utf8("one\n"));
                writeFully(append, utf8("two\n"));
                append.force(true);
            }

            // WRITE không có APPEND: có thể chọn offset để ghi đè.
            try (FileChannel overwrite = FileChannel.open(
                    file, StandardOpenOption.WRITE)) {
                overwrite.position(0);
                writeFully(overwrite, utf8("HEAD\n"));
            }

            String result = Files.readString(
                    file, StandardCharsets.UTF_8);
            System.out.println("content=" + result.replace('\n', '|'));
            System.out.println("bytes=" + Files.size(file));
            System.out.println("correct="
                    + "HEAD\none\ntwo\n".equals(result));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac FileChannelAppendDemo.java
java FileChannelAppendDemo
```

Stdout với một chương trình chạy đơn lẻ và filesystem hỗ trợ các tùy chọn đã dùng:

```text
content=HEAD|one|two|
bytes=13
correct=true
```

**Giải thích chi tiết:**

- `Files.createTempFile` cấp một tệp riêng; không có tiến trình thứ hai cùng ghi nên thứ tự các lần ghi trong demo là xác định.
- `Files.writeString` mặc định ghi/truncate dữ liệu cũ của tệp hiện có, tạo đúng 5 byte ASCII ban đầu.
- `FileChannel.open(..., APPEND)` khiến các relative `write` tiếp theo đi tới EOF, bất kể file position trước đó. `writeFully` xử lý trường hợp một lần `write` chỉ chuyển được một phần buffer; sau mỗi lần channel tự tăng `ByteBuffer.position()`.
- Hai phần append lần lượt thêm 4 + 4 byte, tổng 13 byte. Các chuỗi ở đây là ASCII nên số byte UTF-8 trùng số ký tự đơn vị code; với tiếng Việt, phải tính byte qua `getBytes(UTF_8)`.
- `force(true)` yêu cầu đẩy cập nhật do append channel thực hiện tới thiết bị trên file cục bộ, với ràng buộc từ hợp đồng API; nó **không** biến append thành giao dịch đa tiến trình.
- Channel `overwrite` không bật append, nên `position(0)` và ghi `HEAD\n` sẽ thay đúng 5 byte đầu. File vẫn dài 13 byte vì không dùng `TRUNCATE_EXISTING`.

**Điểm giới hạn của ví dụ:** ngoại lệ “không có tiến triển” của `writeFully` là chính sách *fail fast* để không vô tình lặp vô hạn; FileChannel ghi file thông thường không dùng cơ chế non-blocking của `SocketChannel`. Với các channel khác, giá trị 0 có thể đòi chờ readiness. Đừng sao chép chính sách này cho mọi loại channel.

## 4. APPEND không tương đương với position(size())

Một cách khác để ghi cuối file là:

```java
// Snippet: channel đã mở với WRITE, không có APPEND.
channel.position(channel.size());
while (buffer.hasRemaining()) {
    channel.write(buffer);
}
```

Cách này **có thể đúng khi chỉ một writer sở hữu file**, nhưng trong nhiều writer, việc đọc `size()`, đặt `position()` rồi ghi là **nhiều bước riêng**. Writer khác có thể mở rộng hoặc thay đổi file ở giữa, nên chương trình có thể ghi đè vùng vừa được thêm hoặc đặt sai offset.

Trong chế độ `APPEND`, provider cố gắng bảo đảm mỗi relative `write` đi tới EOF ngay trước khi ghi, nhưng hợp đồng Java vẫn để tính nguyên tử phụ thuộc hệ điều hành. Trên một số hệ thống, một lần gọi kernel append được thực thi nguyên tử đối với cập nhật offset; trên hệ thống khác, đặc biệt khi có filesystem mạng, ngữ nghĩa có thể khác. **Không nên suy ra hành vi đa writer từ một lần chạy trên laptop.**

Ngoài ra:

- `FileChannel.write(ByteBuffer src, long position)` là **positional write**. Khi channel bật `APPEND`, **tác dụng của positional write là không được định nghĩa thống nhất theo Javadoc**. Không dùng cặp này để “vá” một byte ở vị trí cố định trong append channel.
- `position(0)` trên append channel không phải chiến lược cập nhật header: các relative write vẫn theo append mode.
- Nếu muốn sửa một header tại offset 0, hãy dùng channel **không** bật `APPEND` và có quyền ghi, tách khỏi luồng append nếu cần.

Bảng đối chiếu:

| Cách ghi | Vị trí bắt đầu | Có nên xem là append an toàn nhiều writer? |
| --- | --- | --- |
| `WRITE` rồi `position(size())` | Offset EOF đọc ở thời điểm gọi `size` | Không; có thể race giữa các bước. |
| `WRITE + APPEND`, `write(buffer)` | EOF tại mỗi relative write | Không có cam kết atomicity mọi OS/provider. |
| `WRITE` rồi `write(buffer, offset)` | Offset cụ thể do ứng dụng quản lý | Chỉ an toàn nếu quản lý vùng ghi và writer đúng cách. |
| `APPEND` rồi `write(buffer, offset)` | **Không có ngữ nghĩa portable** | Tránh dùng. |

## 5. “Một bản ghi” có thể gồm nhiều write

Giả sử một bản ghi có header độ dài và payload:

```java
// Snippet: channel APPEND, buffer đã chuẩn bị đầy đủ.
writeFully(channel, header);
writeFully(channel, payload);
```

Ngay cả nếu từng `write` riêng lẻ là nguyên tử trên một filesystem cụ thể, **không có giao ước hai lời gọi liên tiếp sẽ được ghép thành một transaction**. Writer khác có thể chèn dữ liệu giữa header và payload. Hơn nữa, `writeFully` có thể phải gọi `write` nhiều lần nếu xảy ra partial write.

Khi yêu cầu mỗi record xuất hiện như một khối thống nhất:

1. Mã hóa record thành một `ByteBuffer` trước khi ghi khi kích thước cho phép; điều này giảm số lần gọi write nhưng **không tạo ra atomicity portable**.
2. Chỉ định **một writer** hoặc một hàng đợi ghi được điều phối trong một JVM; bảo đảm một record được xử lý trọn vẹn trước record kế tiếp.
3. Nếu có nhiều JVM/tiến trình, dùng một cơ chế phối hợp được kiểm thử trên **filesystem mục tiêu**, chẳng hạn một writer service hoặc protocol lock đã thỏa thuận; không giả định Java tự serialize mọi chương trình.
4. Đặt record framing rõ ràng (magic, length, checksum/CRC, version), kiểm tra khi đọc và có chiến lược phát hiện/cắt bỏ phần đuôi chưa hoàn tất.
5. Nếu cần giao dịch nhiều record, rollback hoặc concurrency mạnh, cân nhắc cơ sở dữ liệu hay append-only log có cơ chế commit riêng.

Một lời gọi `write(ByteBuffer[])` (gathering write) cũng có thể chuyển ít byte hơn tổng `remaining()` và không phải giao ước mọi OS sẽ ghi nguyên tử toàn bộ record. Vẫn phải kiểm tra giá trị trả về và vị trí mỗi buffer.

## 6. Đồng thời trong cùng một JVM: điều gì được tuần tự hóa?

`FileChannel` an toàn để các thread gọi phương thức đồng thời về mặt thread safety của đối tượng channel. Tuy nhiên, nó **không cung cấp transaction hoặc ranh giới record** cho ứng dụng. Theo hợp đồng JDK:

- Trên **một FileChannel**, tại một thời điểm chỉ có một thao tác liên quan đến file position hoặc có thể thay đổi kích thước file được thực hiện; thao tác thứ hai loại này phải đợi. Điều này **không** đồng nghĩa chuỗi nhiều lời gọi `write` của một record trở thành nguyên tử.
- Những thao tác positional theo offset cụ thể có thể tiến hành đồng thời; mức độ thực sự thực thi song song tùy implementation.
- Nhiều FileChannel khác nhau, và đặc biệt nhiều process khác nhau, cần cơ chế phối hợp riêng khi cùng ghi một file.

Ví dụ, nếu nhiều thread cùng gọi một hàm `appendRecord` gồm 3 lần write, các lời gọi từ các thread vẫn có thể xen kẽ theo ranh giới write. Hãy khóa **toàn bộ thao tác ghi record** hoặc chuyển record qua một hàng đợi cho một writer duy nhất. Không nên dùng một biến `long localOffset = channel.size()` để tự phân phối offset khi có writer khác mở file.

Khi phối hợp nhiều process, thử nghiệm concurrency phải bao gồm **nhiều tiến trình thật**, không chỉ nhiều thread cùng chia sẻ một đối tượng channel.

## 7. FileLock: hữu ích nhưng không thay thế transaction

`FileChannel.lock()` yêu cầu khóa độc quyền, thường bao phủ vùng `[0, Long.MAX_VALUE)`. Có thể dùng `tryLock()` để thử lấy lock mà không đợi; hàm có thể trả `null` nếu process khác đang giữ khóa vùng xung đột.

Ví dụ minh họa (không phải chương trình độc lập):

```java
// channel: FileChannel đã mở với WRITE.
// Chính sách là mọi writer hợp tác đều phải dùng cùng quy ước khóa.
try (FileLock ignored = channel.lock()) {
    writeFully(channel, recordBuffer);
}
```

Cần import `java.nio.channels.FileLock`; `writeFully` là hàm helper như ở ví dụ chương trình. Lưu ý:

- Lock trên một số hệ điều hành là **advisory**, còn ở nơi khác có thể được thực thi bắt buộc; đừng giả định các process không hợp tác đều sẽ tuân thủ.
- Một số filesystem có thể không hỗ trợ shared lock hoặc chuyển yêu cầu shared thành exclusive. Kiểm tra `FileLock.isShared()` khi điều đó quan trọng.
- Lock được giữ thay mặt **toàn JVM**, nên không thích hợp để làm mutex giữa các thread trong cùng JVM; dùng đồng bộ hóa cấp ứng dụng.
- `OverlappingFileLockException` có thể xuất hiện nếu JVM đã giữ hoặc đang chờ một lock trùng vùng. `lock()` có thể chờ; `tryLock()` không nhất thiết thay thế chiến lược timeout và retry an toàn.
- Với file sẽ tiếp tục dài ra, cần bảo đảm phạm vi lock đã chọn bao phủ phần có thể phát triển; lock vào một vài byte đầu không tự khóa các byte nằm ngoài phạm vi.
- Hành vi khóa trên filesystem mạng phụ thuộc protocol/mount/server và điều kiện mạng. Kiểm thử trên môi trường triển khai thực tế.

Một lock phối hợp tốt có thể bảo đảm writer hợp tác không xen kẽ khi ghi record; nó **không** tự rollback record nếu process chết giữa chừng.

## 8. force(true), force(false), SYNC và DSYNC

`FileChannel.force(boolean metaData)` yêu cầu các cập nhật được ghi ra thiết bị lưu trữ; trên **thiết bị cục bộ**, Javadoc đưa ra bảo đảm cho các cập nhật phù hợp do chính channel thực hiện. Với **thiết bị không cục bộ**, không có cùng mức cam kết đó.

| Cơ chế | Phạm vi theo hợp đồng API | Thời điểm gọi | Hạn chế |
| --- | --- | --- | --- |
| `force(false)` | Yêu cầu đẩy thay đổi **nội dung**. | Sau khi ghi những dữ liệu quan trọng. | Metadata có thể chưa được đồng bộ; hiệu lực chi tiết phụ thuộc nền tảng. |
| `force(true)` | Yêu cầu đẩy cả **nội dung và metadata**. | Khi cần thêm thông tin kích thước/timestamp liên quan được đồng bộ. | Không tạo atomicity cho nhiều lần ghi. |
| `SYNC` | Yêu cầu đồng bộ nội dung và metadata theo mỗi cập nhật. | Chọn khi mở file. | Chi phí I/O có thể lớn. |
| `DSYNC` | Yêu cầu đồng bộ nội dung theo mỗi cập nhật. | Chọn khi mở file. | Không nên hiểu là mọi metadata đều được đảm bảo bền vững. |

`force` chỉ cam kết các loại thay đổi được API quy định. Với một `MappedByteBuffer` được sửa trực tiếp, nên xem xét `MappedByteBuffer.force()`; không mặc định `FileChannel.force()` sẽ bảo đảm mọi thay đổi qua memory mapping.

**Độ bền khác với atomicity:** có thể đẩy một bản ghi **chưa hoàn chỉnh** xuống đĩa. `force(true)` không cứu được format thiếu framing/CRC và không phối hợp được nhiều writer. Trong một quy trình tạo **file mới rồi thay file cũ**, khả năng atomic move và độ bền metadata của thư mục là những vấn đề riêng, cần thiết kế phù hợp provider/OS.

Cả việc flush Java buffer, đóng `FileChannel`, gọi `force` và sử dụng `SYNC` đều không nên bị nhầm với giao dịch dữ liệu nhiều bước có khả năng rollback.

## 9. Hành vi phụ thuộc hệ điều hành và filesystem

Các khác biệt quan trọng khi đưa code vào production:

### 9.1 Append atomicity và hệ thống file mạng

Trên hệ thống hỗ trợ append nguyên tử ở một system call, mỗi lần ghi có thể được bảo vệ khỏi một số race giữa tiến trình. JDK vẫn không hứa điều đó trên **mọi** hệ thống. Hệ thống file mạng (ví dụ NFS/SMB tùy cấu hình) có thêm cache, đồng bộ giữa client và protocol; không suy rằng behavior ở ext4 trên một máy sẽ giống trên volume mạng.

### 9.2 Nhìn thấy dữ liệu mới ở process khác

Các FileChannel trong **cùng chương trình Java** có bảo đảm về tính nhất quán view theo mô tả JDK. Với process khác, dữ liệu nhìn thấy có thể chịu ảnh hưởng cache của OS hoặc trễ protocol filesystem mạng. Một reader đọc giữa lúc writer đang cập nhật vẫn có thể thấy **bản ghi chưa hoàn chỉnh** theo schema ứng dụng.

### 9.3 File đang mở và xóa, đổi tên, thay thế

Trên các nền tảng POSIX, việc unlink một file đang mở có thể hợp lệ: handle cũ vẫn truy cập object cho tới khi đóng. Trên Windows, việc xóa/đổi tên file đang mở có thể thất bại tùy sharing mode và các handle liên quan. Không thiết kế cơ chế rotate log/replace dựa trên giả định một platform. Hãy đóng handle không cần thiết, bắt `IOException` và kiểm thử thay thế/di chuyển đúng volume, filesystem, OS.

### 9.4 Quyền truy cập, dấu thời gian và symbolic link

Quyền POSIX, ACL của Windows, metadata timestamp, hành vi symbolic link và case sensitivity khác nhau theo provider và filesystem. `CREATE` không bỏ qua permission. `FileChannel.open` có thể thất bại vì thiếu quyền, đường dẫn tới thư mục, file đang bị process khác giữ theo chế độ chia sẻ, quota hoặc file system read-only.

Nếu đường dẫn được nhận từ người dùng, kiểm soát quyền truy cập, thư mục được phép và symbolic link theo chính sách bảo mật. Không dùng dữ liệu ngoài để tự tạo tên file log mà không normalize/kiểm tra đường dẫn.

### 9.5 File dài hơn, lỗ hổng dữ liệu và sparse file

`channel.position(channel.size() + gap)` **không tự mở rộng** file. Khi sau đó ghi vào vị trí mới, file được mở rộng và các byte ở khoảng trống giữa EOF cũ và vùng mới có giá trị **không được bảo đảm** theo hợp đồng FileChannel. Nếu cần định dạng nhị phân có vùng trống, hãy khởi tạo rõ dữ liệu và định nghĩa chính sách. `SPARSE` chỉ là hint khi tạo file, không phải cam kết sử dụng ít dung lượng.

### 9.6 DELETE_ON_CLOSE và dọn tài nguyên

`DELETE_ON_CLOSE` chỉ là nỗ lực tốt nhất. Tính khả dụng và thời điểm xóa có thể phụ thuộc platform, handle hoặc quyền truy cập. Đối với dữ liệu quan trọng cần dọn, dùng thư mục temp riêng, đóng mọi stream/channel, xử lý lỗi xóa và có quy trình cleanup bổ sung.

## 10. Tránh nhầm các khái niệm “nguyên tử”

Trong một hệ thống ghi log hoặc journal, có nhiều cấp độ độc lập:

| Khái niệm | Có thể đạt được bằng | Điều **chưa** được bảo đảm |
| --- | --- | --- |
| Tạo file mới nếu chưa tồn tại | `CREATE_NEW` | Một record append sẽ tự an toàn giữa nhiều writer. |
| Append mỗi lệnh write | `APPEND` | Việc seek EOF + write nguyên tử trên mọi OS. |
| Ngăn writer hợp tác ghi cùng lúc | Cùng protocol lock hoặc single writer | Process không hợp tác không thể sửa file; không có rollback. |
| Đẩy byte ra thiết bị | `force` hoặc `SYNC/DSYNC` | Record mang schema đúng, không rách, multi-record transaction. |
| Thay một đường dẫn bằng file khác | `Files.move(..., ATOMIC_MOVE)` nếu provider hỗ trợ | Mọi metadata/data đã bền vững hoặc atomic xuyên filesystem. |
| Xác nhận record hoàn chỉnh | Header/length/checksum/trailer, kiểm tra khi đọc | File không bị sửa bởi người không có quyền; checksum không thay xác thực. |

`Files.move(..., StandardCopyOption.ATOMIC_MOVE)` có thể ném `AtomicMoveNotSupportedException` và hành vi thay đích đang tồn tại còn phụ thuộc provider/OS. Nếu cần bảo đảm thật sự, không bỏ qua exception rồi tự tuyên bố thay file là nguyên tử.

## 11. Các chiến lược triển khai theo nhu cầu

**Ứng dụng đơn giản, chỉ một writer:** mở `APPEND + CREATE + WRITE`, dùng một buffer chứa record hoàn chỉnh, `while (hasRemaining())` để ghi hết, đóng channel. Chọn tần suất `force` theo yêu cầu durability, không dùng `force` sau từng record khi chi phí không chấp nhận được.

**Nhiều thread cùng JVM:** cho mọi record qua một hàng đợi có một thread ghi, hoặc khóa toàn bộ khối ghi record trong ứng dụng. Không dựa vào việc `FileChannel` thread-safe để biến 2–3 lời gọi write thành transaction.

**Nhiều process trên cùng máy:** phối hợp qua single-writer process hoặc lock được tất cả process tuân thủ, kèm framing và recovery. Kiểm tra chính xác filesystem; nếu gặp lỗi, phải xác định record nào đã commit theo format chứ không đoán dựa trên một lần `write` thành công.

**Nhiều host / network filesystem:** tránh dựa vào atomic append khi không có hợp đồng kiểm chứng rõ. Xem xét dịch vụ ghi tập trung, message broker hoặc database có transaction phù hợp, quan sát retry, network partition và phục hồi.

**Ghi file cấu hình hoặc snapshot để thay thế:** thông thường tạo file mới ở thư mục đích, ghi hết, flush/force tùy yêu cầu, sau đó di chuyển/thay thế có kiểm tra hỗ trợ atomicity và error handling. Đây là workflow **khác** với append log.

**Có nhiều lần ghi ngắn:** cân nhắc buffer ở tầng ứng dụng nhưng phải flush đúng lúc và quản lý crash recovery. Việc gom nhiều record vào một buffer có thể cải thiện throughput; không tự bảo đảm tất cả record cùng commit nguyên tử.

## 12. Các lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Mở channel báo `IllegalArgumentException` | Ghép `APPEND + READ` hoặc `APPEND + TRUNCATE_EXISTING`. | Dùng đúng bộ open options, tách read và append. |
| Nội dung cũ bị thay đổi | Mở `WRITE` rồi ghi từ offset 0 nhưng nghĩ là append. | Chọn `APPEND` khi cần thêm cuối file. |
| File không được làm rỗng | Có `CREATE` nhưng không có `TRUNCATE_EXISTING`. | Dùng truncate khi thực sự muốn ghi lại toàn bộ file, không kết hợp APPEND. |
| Ghi đè dữ liệu mới từ process khác | Tính `size()` rồi `position(size)` có race. | Single writer/lock; không xem seek EOF là append nguyên tử. |
| Log hỏng hoặc record lẫn nhau | Nhiều write/record hoặc nhiều writer xen kẽ. | Framing, điều phối writer, recovery khi khởi động lại. |
| Dữ liệu ghi bị thiếu | Chỉ gọi `write(buffer)` một lần. | Lặp đến `!buffer.hasRemaining()`. |
| Vừa bật APPEND vừa muốn ghi header ở offset cố định | Positional write khi APPEND có semantics không portable. | Dùng channel không APPEND cho positional update và có coordination. |
| File lock hoạt động khác máy phát triển | Advisory/mandatory khác nhau, mạng không hỗ trợ như mong đợi. | Thống nhất giao thức lock, thử nhiều process trên hệ thật. |
| Gọi `force(true)` nhưng reader thấy record dở dang | force không cung cấp transaction. | Thiết kế commit framing/checksum và đồng bộ hóa reader. |
| Xóa/rename file đang mở bị lỗi | OS/file-sharing mode/provider khác nhau. | Đóng handle, xử lý IOException, kiểm thử quy trình rotate. |
| Số byte file không bằng số ký tự | Dữ liệu UTF-8 chứa Unicode đa byte. | Đo `ByteBuffer.remaining()` hoặc `getBytes(UTF_8).length`. |

## 13. Thực hành và câu hỏi đánh giá

**Bài 1 — Quan sát overwrite so với append.** Chạy chương trình mẫu rồi bỏ `APPEND` ở lần mở channel đầu, giữ nguyên các lệnh `writeFully`. Dự đoán file ra sao: các lần ghi bắt đầu từ position 0 và tiếp tục theo position sau write; nội dung cũ có thể bị thay thế và kích thước file tùy số byte đã ghi. Giải thích vì sao `CREATE` không làm thay đổi hành vi vị trí.

**Bài 2 — Tách header khỏi log.** File có header version/count cố định ở 16 byte đầu và phần log ở sau. Thiết kế hai giai đoạn: cập nhật header bằng channel bình thường có `WRITE` (không APPEND), đóng channel; ghi record mới qua channel `APPEND`. Nêu rủi ro khi hai việc này diễn ra song song và tại sao cần protocol commit thay vì dựa vào 2 thao tác độc lập.

**Bài 3 — Kiểm thử concurrent writer.** Tạo hai chương trình độc lập, mỗi chương trình append 1.000 record với format `length + payload + CRC`. Chạy trên filesystem địa phương và sau đó trên filesystem mạng (nếu có). So sánh số record hợp lệ, các đoạn giao nhau, lần write không đủ và tính chất append; tuyệt đối không coi một lần thử thành bằng chứng atomicity portable.

**Bài 4 — Mô phỏng crash.** Viết header và payload bằng hai lần write, chủ động dừng chương trình giữa chừng trong môi trường thử nghiệm. Xây reader quét file đến record cuối cùng được xác nhận đầy đủ, phát hiện phần đuôi không hoàn chỉnh và đưa ra chính sách truncate/recover có kiểm soát.

**Bài 5 — So sánh `force`.** Dùng ba cấu hình: không force, `force(false)`, `force(true)`. Đo độ trễ ghi với file trên môi trường kiểm thử riêng; diễn giải vì sao hiệu năng, caching, metadata và thiết bị lưu trữ ảnh hưởng số liệu. Không thử crash/sập nguồn trên hệ thống chứa dữ liệu thật.

**Tự kiểm tra:**

1. Vì sao `APPEND` khác `channel.position(channel.size())` trong môi trường đa writer?
2. Vì sao `FileChannel.write(buffer, offset)` không nên dùng khi APPEND bật?
3. Gọi `force(true)` có bảo đảm 3 lần write trở thành transaction không?
4. `FileLock` có giải quyết được cạnh tranh giữa các thread trong cùng JVM không?
5. Tại sao một record lớn chia thành nhiều write vẫn cần framing và recovery?
6. Những khác biệt OS/filesystem nào có thể ảnh hưởng rotate log, shared locks và visibility?

## 14. Tham khảo

- [Java SE 21 — FileChannel API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html): mô tả chính thức về APPEND, vị trí file, `force`, lock, concurrency và hành vi phụ thuộc hệ thống.
- [Java SE 21 — StandardOpenOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardOpenOption.html): định nghĩa các tùy chọn `APPEND`, `CREATE_NEW`, `SYNC`, `DSYNC` và các lựa chọn mở file.

**Ghi nhớ:** `APPEND` quy định **đi tới EOF trước mỗi relative write**, nhưng không cung cấp bảo đảm nguyên tử đa writer độc lập với OS. Kết hợp `writeFully`, protocol sở hữu file/lock phù hợp, định dạng bản ghi có thể phục hồi, chiến lược durability và kiểm thử trên filesystem triển khai thực tế mới tạo được một cơ chế ghi cuối file đáng tin cậy.
