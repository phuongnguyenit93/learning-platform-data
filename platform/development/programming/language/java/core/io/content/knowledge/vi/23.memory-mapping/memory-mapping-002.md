# MapMode READ_ONLY, READ_WRITE và PRIVATE trong Java NIO.2

## 1. Memory-mapped file là gì?

Với Java NIO.2, phương thức `FileChannel.map(...)` ánh xạ một **vùng byte của tệp** vào không gian bộ nhớ của tiến trình và trả về `MappedByteBuffer`. Thay vì liên tục gọi `read()` để sao chép byte từ channel vào buffer riêng, chương trình có thể truy cập vùng được ánh xạ bằng các phương thức `get(...)` và `put(...)` của `ByteBuffer`.

Ví dụ một tệp chứa 8 byte:

~~~text
Tệp example.bin (offset theo byte)
  0   1   2   3   4   5   6   7
+---+---+---+---+---+---+---+---+
| A | B | C | D | E | F | G | H |
+---+---+---+---+---+---+---+---+
        |<----- map(2, 4) ---->|
               ánh xạ C D E F

MappedByteBuffer mới:
  index  0   1   2   3
       +---+---+---+---+
       | C | D | E | F |
       +---+---+---+---+
~~~

Trong `channel.map(mode, position, size)`:

- `mode` chọn **quyền đọc/ghi và cách các thay đổi từ buffer ảnh hưởng tới tệp**.
- `position` là **vị trí bắt đầu trong tệp**, tính theo byte, kiểu `long`, không âm.
- `size` là **số byte** của vùng ánh xạ, kiểu `long` khi truyền vào API, nhưng đối tượng `MappedByteBuffer` trên Java 17 có dung lượng biểu diễn bởi `int`: vùng của một lần map không vượt `Integer.MAX_VALUE` byte.
- Buffer trả về có `position() == 0`, `limit() == capacity() == size`; chỉ số 0 trong buffer ứng với offset `position` của tệp.
- `FileChannel.map(...)` không làm thay đổi con trỏ vị trí I/O hiện tại của channel. Nó thiết lập một mapping riêng.

`MappedByteBuffer` là một `ByteBuffer` dạng direct. Vì vậy, nó hỗ trợ `get`/`put` tương đối hoặc tuyệt đối, byte order, view/slice và các thao tác điều khiển position/limit như buffer thông thường. Điểm khác biệt nằm ở nguồn dữ liệu và cách hệ điều hành quản lý trang bộ nhớ ánh xạ.

**Phạm vi bài này:** ba hằng `FileChannel.MapMode.READ_ONLY`, `READ_WRITE` và `PRIVATE`. Chúng có thể trông tương tự nhau khi chỉ đọc dữ liệu, nhưng có hành vi **rất khác nhau khi ứng dụng sửa buffer**.

## 2. So sánh ba MapMode

| Chế độ | Đọc dữ liệu? | Ghi `put` vào mapping? | Thay đổi từ mapping có được ghi trở lại tệp? | Cần mở FileChannel như thế nào? |
| --- | --- | --- | --- | --- |
| `READ_ONLY` | Có | Không; ném `ReadOnlyBufferException` | Không có thay đổi do buffer này thực hiện | Có quyền `READ` |
| `READ_WRITE` | Có | Có | Có; thay đổi được truyền về tệp theo cơ chế mapping, có thể gọi `force()` để yêu cầu ghi xuống lưu trữ | Có cả `READ` và `WRITE` |
| `PRIVATE` | Có | Có, trong vùng riêng của mapping | **Không**; các thay đổi của mapping không được truyền trở lại tệp | Có cả `READ` và `WRITE` |

Sự phân biệt quan trọng:

- `READ_ONLY` bảo vệ **view này khỏi việc ghi qua API buffer**. Nó không làm cho toàn bộ tệp bất biến: một tiến trình khác hoặc luồng khác có thể thay đổi tệp ở bên ngoài mapping.
- `READ_WRITE` dùng khi muốn cập nhật nội dung tệp thông qua bộ nhớ ánh xạ. Nội dung sửa có thể được hệ điều hành ghi về tệp ở thời điểm khác, nên khi cần kiểm soát việc đồng bộ cần gọi `MappedByteBuffer.force()` theo hợp đồng.
- `PRIVATE` là **copy-on-write**: ban đầu đọc từ vùng tệp được ánh xạ; khi ghi, hệ điều hành có thể tạo bản sao riêng của phần trang bị sửa. Chỉ chương trình nhìn thấy những thay đổi riêng của mapping đó; chúng không được propagate về tệp và không hiện ra ở tiến trình khác thông qua chính mapping riêng ấy.

Không coi `PRIVATE` là bản sao snapshot bất biến của toàn bộ tệp. Việc tệp nền thay đổi từ bên ngoài, và thời điểm thay đổi đó được phản ánh vào mapping, **phụ thuộc hệ điều hành và không được API bảo đảm**. Thứ được cam kết rõ ràng là **những thay đổi thực hiện qua private mapping không ghi ngược lại tệp**.

## 3. Mở FileChannel với quyền phù hợp

Cú pháp cơ bản:

~~~java
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path path = Path.of("example.bin");

try (FileChannel channel =
        FileChannel.open(path, StandardOpenOption.READ)) {

    long length = channel.size();
    MappedByteBuffer mapped =
            channel.map(FileChannel.MapMode.READ_ONLY, 0, length);
    // Đọc mapped tại đây.
}
~~~

Đây là **mảnh minh họa**, giả định `example.bin` đã tồn tại và không rỗng. `FileChannel.open(path, READ)` cho phép map `READ_ONLY`. Nếu muốn map `READ_WRITE` hoặc `PRIVATE`, mở channel có cả hai quyền:

~~~java
try (FileChannel channel = FileChannel.open(
        path, StandardOpenOption.READ, StandardOpenOption.WRITE)) {

    MappedByteBuffer writable =
            channel.map(FileChannel.MapMode.READ_WRITE, 0, channel.size());

    MappedByteBuffer privateView =
            channel.map(FileChannel.MapMode.PRIVATE, 0, channel.size());
}
~~~

**Chú ý về quyền:** dù `PRIVATE` không ghi các thay đổi trở lại tệp, overload `FileChannel.map` trên Java 17 vẫn yêu cầu channel mở cả `READ` lẫn `WRITE` cho chế độ này. Mở channel chỉ đọc rồi yêu cầu `READ_WRITE` hoặc `PRIVATE` có thể ném `NonWritableChannelException`; nếu thiếu quyền đọc cần thiết, có thể gặp `NonReadableChannelException`. Quyền mở tệp ở hệ điều hành cũng phải cho phép hoạt động tương ứng.

Không nên mở channel với `TRUNCATE_EXISTING` khi mục tiêu là ánh xạ dữ liệu hiện có để đọc hoặc sửa: tùy chọn này có thể xóa hết nội dung ngay khi mở. Nếu muốn tạo tệp mới và map, phải chuẩn bị kích thước/vùng nội dung một cách có chủ đích và xử lý trường hợp tệp rỗng.

## 4. READ_ONLY: đọc trực tiếp từ vùng tệp, không ghi được

~~~java
try (FileChannel channel = FileChannel.open(file, StandardOpenOption.READ)) {
    MappedByteBuffer readOnly = channel.map(
            FileChannel.MapMode.READ_ONLY, 0, channel.size());

    byte first = readOnly.get(0);
    System.out.println((char) first);

    // Ném ReadOnlyBufferException:
    // readOnly.put(0, (byte) 'X');
}
~~~

Đây là **mảnh minh họa** với biến `file` là `Path` trỏ đến tệp không rỗng. Gọi `isReadOnly()` trên buffer này trả `true`. Các thao tác thay đổi dữ liệu qua buffer như `put(...)` bị từ chối.

READ_ONLY thích hợp khi:

- Quét một tệp lớn để tìm một mẫu byte, chỉ số hay bảng tra cứu mà không có nhu cầu sửa.
- Đọc cấu trúc nhị phân có vị trí cố định trong tệp.
- Muốn API của một mapping từ chối thao tác ghi do lỗi lập trình.

READ_ONLY **không đồng nghĩa** an toàn trước thay đổi ngoài chương trình. Nếu một tiến trình khác sửa hoặc thu nhỏ tệp trong khi mapping đang tồn tại, nội dung quan sát được có thể thay đổi hoặc vùng mapping có thể trở nên không truy cập được. Java không bảo đảm snapshot của tệp tại thời điểm map.

Nếu ứng dụng cần dữ liệu không đổi để xử lý, hãy kiểm soát vòng đời tệp/đồng bộ, đọc bản sao độc lập hoặc dùng cơ chế nhất quán phù hợp hệ thống.

## 5. READ_WRITE: sửa buffer có tác động đến tệp

~~~java
try (FileChannel channel = FileChannel.open(
        file, StandardOpenOption.READ, StandardOpenOption.WRITE)) {

    MappedByteBuffer rw = channel.map(
            FileChannel.MapMode.READ_WRITE, 0, channel.size());

    rw.put(0, (byte) 'J'); // Sửa byte đầu của vùng ánh xạ.
    rw.force();            // Yêu cầu đồng bộ các thay đổi qua mapping.
}
~~~

Điều cần hiểu:

1. `put(0, ...)` ghi vào vùng mapping tại **buffer index 0**, tương ứng vị trí bắt đầu truyền cho `map`. Với ví dụ trên, đó là byte đầu tiên của tệp.
2. Ở `READ_WRITE`, thay đổi sẽ được truyền về tệp theo cơ chế của hệ điều hành. **Thời điểm** thay đổi trở nên quan sát được từ các tiến trình khác có thể khác nhau theo nền tảng.
3. `rw.force()` dùng để yêu cầu đẩy những thay đổi của mapping xuống thiết bị lưu trữ. Theo API Java 17, với tệp trên thiết bị lưu trữ **cục bộ**, lời gọi này có bảo đảm ghi các thay đổi từ buffer vào thiết bị khi trả về; với thiết bị không cục bộ thì không có bảo đảm tương đương.
4. `rw.force(int index, int length)` yêu cầu đồng bộ một phần vùng ánh xạ khi muốn quản lý phạm vi; đây là API hiện diện trên Java 17. Nó có thể thực hiện thêm I/O ngoài phạm vi yêu cầu vì đơn vị lưu trữ vật lý.
5. Cần xử lý lỗi I/O của `force()`. Với `MappedByteBuffer.force`, lỗi ghi có thể phát sinh dưới dạng `UncheckedIOException`.

`MappedByteBuffer.force()` và `FileChannel.force(boolean metaData)` không hoàn toàn thay thế nhau. Theo Java 17, `FileChannel.force` **không được bảo đảm** sẽ đồng bộ những thay đổi thực hiện thông qua `MappedByteBuffer`. Với byte sửa qua memory mapping, hãy gọi `mapped.force()` khi cần đồng bộ thay đổi đó.

Một điểm dễ nhầm: `force()` **không phải** lệnh “lưu file” bắt buộc sau mọi `put`. Chế độ `READ_WRITE` đã có ngữ nghĩa propagate; `force` là công cụ yêu cầu thời điểm đồng bộ theo hợp đồng, đặc biệt khi ứng dụng có yêu cầu độ bền dữ liệu.

## 6. PRIVATE: copy-on-write và sự tách biệt với tệp gốc

~~~java
try (FileChannel channel = FileChannel.open(
        file, StandardOpenOption.READ, StandardOpenOption.WRITE)) {

    MappedByteBuffer privateView = channel.map(
            FileChannel.MapMode.PRIVATE, 0, channel.size());

    privateView.put(0, (byte) 'P');

    // privateView.get(0) nhìn thấy 'P'.
    // Byte tại vị trí 0 trong tệp KHÔNG bị thay đổi bởi lệnh put trên.
}
~~~

Chế độ PRIVATE rất khác với một buffer read-only: chương trình **được phép ghi** và đọc lại những byte vừa sửa. Tuy nhiên, tác động đó bị giữ trong không gian riêng của mapping.

~~~text
Tệp ban đầu:
      H E L L O
          |
          +--------> PRIVATE mapping
                        |
                    put(0, 'P')
                        |
Mapping riêng nhìn thấy:
      P E L L O

Tệp gốc vẫn là:
      H E L L O
~~~

Private mapping không tự động tạo một “file phiên bản mới”. Những byte sửa riêng chỉ tồn tại trong mapping và có thể mất đi khi vùng mapping bị giải phóng. Nếu muốn lưu bản sửa vào tệp mới, chương trình phải chủ động sao chép dữ liệu kết quả sang tệp đích (ví dụ bằng `Files.newOutputStream(...)` hoặc channel ghi riêng) và có quy tắc đảm bảo nhất quán.

`force()` trên `PRIVATE` **không ghi các byte sửa riêng về tệp**; theo Java 17, `MappedByteBuffer.force()` không có tác dụng cho mapping `READ_ONLY` hoặc `PRIVATE`. Không dùng `force` như phương án “commit” thay đổi private mapping.

### 6.1. PRIVATE không có nghĩa “đóng vai trò transaction”

Một transaction thông thường có commit/rollback, cô lập theo cấp độ xác định và quy tắc nhất quán. `MapMode.PRIVATE` chỉ cung cấp semantics **copy-on-write cho những thay đổi từ mapping đó**; nó không tự cung cấp:

- Giao diện commit thay đổi về tệp.
- Bảo đảm snapshot độc lập hoàn toàn trước các sửa đổi bên ngoài.
- Khả năng hoàn tác thay đổi của một `READ_WRITE` mapping khác.
- Cơ chế khóa/đồng bộ giữa các tiến trình, hay khả năng giải quyết xung đột.

Nếu muốn chỉnh sửa thử một bản dữ liệu nhị phân rồi quyết định có giữ hay không, PRIVATE có thể hữu ích cho xử lý cục bộ; nếu cần transaction bền vững thì phải thiết kế cơ chế riêng ở cấp ứng dụng.

## 7. Ví dụ hoàn chỉnh Java 17+: so sánh ba chế độ trên cùng tệp

Chương trình sau dùng tệp tạm chứa chuỗi ASCII `HELLO`:

1. Mở READ_ONLY, đọc nội dung và chứng minh lệnh `put` bị chặn.
2. Mở PRIVATE, sửa `H` thành `P`. Buffer riêng thấy `PELLO` nhưng đọc lại tệp vẫn thấy `HELLO`.
3. Mở READ_WRITE, sửa `E` thành `A` và gọi `force()`. Đọc lại tệp thấy `HALLO`.

Lưu thành `MapModeDemo.java`:

~~~java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.ReadOnlyBufferException;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class MapModeDemo {

    static String readAscii(MappedByteBuffer mapped) {
        // Duplicate giữ nguyên position/limit của buffer gốc.
        MappedByteBuffer copy = mapped.duplicate();
        copy.position(0);
        byte[] bytes = new byte[copy.remaining()];
        copy.get(bytes);
        return new String(bytes, StandardCharsets.US_ASCII);
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("map-modes-", ".bin");

        // Đăng ký xóa lúc JVM kết thúc. Việc dọn mmap phụ thuộc HĐH;
        // đừng phụ thuộc xóa tức thì lúc buffer vẫn còn mapping.
        file.toFile().deleteOnExit();
        Files.writeString(file, "HELLO", StandardCharsets.US_ASCII);

        try (FileChannel channel = FileChannel.open(
                file, StandardOpenOption.READ)) {

            MappedByteBuffer ro = channel.map(
                    FileChannel.MapMode.READ_ONLY, 0, 5);

            System.out.println("readOnly=" + ro.isReadOnly());
            System.out.println("readOnlyText=" + readAscii(ro));

            boolean blocked = false;
            try {
                ro.put(0, (byte) 'X');
            } catch (ReadOnlyBufferException ex) {
                blocked = true;
            }
            System.out.println("readOnlyBlocked=" + blocked);
        }

        try (FileChannel channel = FileChannel.open(
                file, StandardOpenOption.READ, StandardOpenOption.WRITE)) {

            MappedByteBuffer privateView = channel.map(
                    FileChannel.MapMode.PRIVATE, 0, 5);
            privateView.put(0, (byte) 'P');

            System.out.println("privateView=" + readAscii(privateView));
            System.out.println("fileAfterPrivate=" +
                    Files.readString(file, StandardCharsets.US_ASCII));

            MappedByteBuffer rw = channel.map(
                    FileChannel.MapMode.READ_WRITE, 0, 5);
            rw.put(1, (byte) 'A');
            rw.force();

            System.out.println("readWriteView=" + readAscii(rw));
            System.out.println("fileAfterReadWrite=" +
                    Files.readString(file, StandardCharsets.US_ASCII));
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac MapModeDemo.java
java MapModeDemo
~~~

**Stdout dự kiến trong môi trường thông thường hỗ trợ memory-mapped files:**

~~~text
readOnly=true
readOnlyText=HELLO
readOnlyBlocked=true
privateView=PELLO
fileAfterPrivate=HELLO
readWriteView=HALLO
fileAfterReadWrite=HALLO
~~~

Giải thích:

- `readOnlyText=HELLO`: mapping READ_ONLY cho phép truy cập byte gốc.
- `readOnlyBlocked=true`: `put` ném `ReadOnlyBufferException` và không làm thay đổi tệp.
- `privateView=PELLO` cùng `fileAfterPrivate=HELLO`: lệnh sửa trên PRIVATE chỉ tác động lên mapping riêng.
- `readWriteView=HALLO` và `fileAfterReadWrite=HALLO`: mapping READ_WRITE sửa byte thứ hai trong tệp.
- `force()` được gọi cho READ_WRITE trước khi kiểm tra lại tệp. Ví dụ dùng dữ liệu ASCII một byte/ký tự để offset 0, 1 và kích thước 5 dễ kiểm chứng.

**Lưu ý môi trường:** memory mapping phụ thuộc hệ điều hành, filesystem và quyền truy cập. Tệp tạm được đăng ký xóa khi JVM thoát vì trên một số hệ điều hành (đặc biệt Windows), việc xóa tệp đang có mapping chưa được giải phóng có thể bị từ chối. Không có lệnh chuẩn Java 17 bảo đảm “unmap ngay lập tức” cho mọi `MappedByteBuffer`.

## 8. Những giới hạn và trạng thái của MappedByteBuffer

### 8.1. Chỉ số buffer không phải offset tuyệt đối của tệp

~~~java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_ONLY, 1_024, 128);

byte first = mapped.get(0); // Byte ở offset 1024 của tệp.
byte last = mapped.get(127); // Byte ở offset 1151 của tệp.
~~~

Đây là mảnh mã minh họa với `channel` đã mở quyền đọc và tệp có ít nhất 1152 byte. Với offset bất kỳ `start`, `mapped.get(i)` tương ứng byte ở offset `start + i`. Vì vậy `mapped.get(1_024)` trong đoạn trên là ngoài phạm vi, dù offset 1024 tồn tại trong tệp gốc.

### 8.2. Trạng thái ByteBuffer vẫn áp dụng

Mapping mới có `position=0`, `limit=capacity=size`. `get()` tương đối tăng position; `get(index)` tuyệt đối không làm thay đổi position. `flip()`, `rewind()`, `slice()` và `duplicate()` điều khiển view/position tương tự các ByteBuffer khác.

Đặc biệt, **`clear()` không xóa byte trong tệp hoặc vùng mapping**. Nó chỉ đặt lại position và limit; với READ_WRITE mapping, thao tác `put` mới mới là thay đổi nội dung.

### 8.3. load(), isLoaded() và force() không cùng vai trò

| API | Mục tiêu | Giới hạn cần nhớ |
| --- | --- | --- |
| `mapped.load()` | Cố gắng nạp các trang tương ứng vùng mapping vào bộ nhớ vật lý. | Best-effort; có thể phát sinh page fault và I/O; không bảo đảm trang luôn resident về sau. |
| `mapped.isLoaded()` | Hỏi xem vùng mapping có vẻ đang resident hay không. | Chỉ là gợi ý; `false` chưa chắc dữ liệu không có trong RAM. |
| `mapped.force()` | Đẩy thay đổi từ READ_WRITE mapping xuống lưu trữ theo hợp đồng. | Không có tác dụng với READ_ONLY/PRIVATE; bảo đảm phụ thuộc tệp trên thiết bị cục bộ. |

Đừng gọi `load()` và cho rằng dữ liệu đã được “đồng bộ xuống đĩa”: `load` giúp nạp dữ liệu **từ tệp lên RAM**; `force` xử lý hướng ghi thay đổi **từ mapping về lưu trữ**.

### 8.4. Đóng FileChannel không lập tức hủy mapping

Sau khi `FileChannel` đóng, vùng mapping vẫn có thể tồn tại và sử dụng được đến khi `MappedByteBuffer` được thu gom rác. Đây là điểm khác biệt với những đối tượng I/O mà việc đóng đồng nghĩa giải phóng toàn bộ tài nguyên bên dưới ngay lập tức.

Hệ quả thực tế:

- Tệp có thể khó xóa, đổi tên hoặc truncate trong khi mapping vẫn còn, tùy hệ điều hành.
- Không giữ số lượng lớn mapping không cần thiết trong thời gian dài.
- Đừng xây dựng logic dựa trên dự đoán thời điểm GC; `MappedByteBuffer` không triển khai `AutoCloseable`.
- Khi cần kiểm soát vòng đời vùng nhớ chính xác, đánh giá giải pháp khác phù hợp runtime, nhưng không giả định có API unmap công khai tương đương `close()` trên Java 17.

## 9. Nguy cơ khi tệp thay đổi đồng thời hoặc bị truncate

Một tệp đang được map có thể bị tiến trình khác sửa, thay kích thước hoặc cắt ngắn. Theo Javadoc Java 17, nhiều chi tiết ánh xạ phụ thuộc hệ điều hành:

- Khi tệp nền thay đổi, **nội dung** buffer có phản ánh thay đổi đó hay không, và phản ánh khi nào, không được bảo đảm thống nhất.
- Nếu tệp bị truncate khiến một phần mapping không còn được hỗ trợ bởi dữ liệu tệp, việc truy cập vùng đó có thể trở nên không khả dụng.
- `MappedByteBuffer` có thể ném ngoại lệ khi đụng vùng mất khả năng truy cập; không suy ra tất cả hệ điều hành sẽ có cách báo lỗi giống nhau.
- `READ_ONLY` không đồng nghĩa dữ liệu bất biến, và `PRIVATE` cũng không mặc nhiên là snapshot bền vững/nhất quán trước sửa đổi bên ngoài.

Nếu ứng dụng cần giao thức đọc/ghi nhất quán, hãy kiểm soát chủ sở hữu file, khóa/phiên bản dữ liệu, hoặc chọn cơ chế lưu trữ có transaction theo yêu cầu. `FileLock` có thể hỗ trợ phối hợp giữa các tiến trình khi filesystem và tiến trình liên quan tuân thủ khóa, nhưng không phải cam kết tuyệt đối trên mọi nền tảng và không loại bỏ mọi vấn đề đồng bộ.

**Không nên map một vùng vượt EOF rồi giả định luôn đọc được byte 0 hoặc file được mở rộng đúng cách.** Hành vi khi vùng map không nằm trọn trong file không được Javadoc Java 17 xác định nhất quán. Đối với READ_ONLY, hãy kiểm tra kích thước hiện có; với READ_WRITE, nếu muốn mở rộng file, hãy xác lập dung lượng tệp có chủ đích trước khi map.

## 10. Chọn chế độ nào cho từng nhu cầu?

| Nhu cầu | Chế độ phù hợp | Lý do |
| --- | --- | --- |
| Đọc tệp nhị phân lớn, tra cứu chỉ số hoặc quét dữ liệu mà không sửa | `READ_ONLY` | View không cho phép ghi, giảm rủi ro sửa nhầm. |
| Sửa bảng chỉ số hoặc vùng cố định và muốn lưu kết quả vào tệp | `READ_WRITE` | Các thay đổi từ mapping được propagate về tệp; có thể gọi `force()` khi yêu cầu độ bền. |
| Tạo biến thể tạm để chạy thử thuật toán trên dữ liệu hiện có | `PRIVATE` | Cho phép sửa view riêng mà không ghi những sửa đổi đó về tệp nền. |
| Muốn snapshot bất biến, chống mọi thay đổi bên ngoài | Không chế độ nào tự bảo đảm | Phải bổ sung bản sao và/hoặc cơ chế nhất quán riêng. |
| Muốn transaction commit/rollback thật sự | Không chế độ nào tự cung cấp | Cần tầng giao dịch hoặc giao thức lưu dữ liệu phù hợp. |
| Tệp nhỏ, chỉ đọc/ghi một lần | Thường dùng `Files.readAllBytes`/`write` hoặc `FileChannel.read/write` | Chi phí thiết lập mapping có thể không đem lại lợi ích. |

Không phải tệp lớn nào cũng nhất thiết nên memory-map. Truy cập tuần tự toàn bộ một tệp một lần có thể dùng stream/channel với buffer đủ lớn và dễ kiểm soát tài nguyên hơn. Memory mapping hữu ích với truy cập ngẫu nhiên hoặc thao tác lặp nhiều lần trên vùng tệp, nhưng cần đo đạc phù hợp workload.

## 11. Các lỗi thường gặp

### Lỗi 1: tưởng PRIVATE giống READ_ONLY

**Sai:** “PRIVATE không sửa file nên chắc chắn buffer này không ghi được.”

**Đúng:** PRIVATE buffer **ghi được**, nhưng các sửa đổi riêng không propagate về file. READ_ONLY mới ném `ReadOnlyBufferException` khi `put`.

### Lỗi 2: tưởng PRIVATE giống READ_WRITE với force bị tắt

**Sai:** “Nếu gọi `privateView.force()` hoặc đóng channel sẽ commit dữ liệu.”

**Đúng:** PRIVATE có semantics copy-on-write; `force()` không ghi các thay đổi của PRIVATE về tệp. Muốn lưu phiên bản riêng phải copy/serialize dữ liệu sang đích khác.

### Lỗi 3: mở FileChannel chỉ đọc rồi map PRIVATE

**Sai:** “PRIVATE không viết file thì mở READ là đủ.”

**Đúng:** Java 17 yêu cầu cả `READ` và `WRITE` để map `PRIVATE`, giống `READ_WRITE`. `READ_ONLY` chỉ yêu cầu `READ`.

### Lỗi 4: gọi FileChannel.force() để flush các byte vừa sửa qua mapping

**Rủi ro:** `FileChannel.force` không được bảo đảm ghi những thay đổi do `MappedByteBuffer.put`. Khi cần đồng bộ byte sửa qua READ_WRITE mapping, gọi `mapped.force()` và xử lý lỗi theo hợp đồng.

### Lỗi 5: giả định dữ liệu đọc từ mapping là snapshot

**Rủi ro:** Tiến trình khác có thể sửa hoặc truncate tệp. Dữ liệu được quan sát và vùng truy cập hợp lệ phụ thuộc nền tảng. Sử dụng ownership/versioning/locking phù hợp hoặc sao chép dữ liệu khi cần ảnh chụp nhất quán.

### Lỗi 6: xem `clear()` là xóa dữ liệu

**Sai:** `mapped.clear()` chỉ reset trạng thái `position/limit`. Nó không đổi tệp và không xóa byte đang ánh xạ. Ghi zero cần `put` rõ ràng và phải có quyền ghi.

### Lỗi 7: bỏ qua byte order và charset

Memory mapping cung cấp **byte**, không tự biết file lưu số theo big-endian/little-endian hay văn bản UTF-8/UTF-16. Khi đọc `getInt()` hoặc `getLong()`, đặt đúng `ByteOrder`. Khi đọc chữ, dùng `CharsetDecoder` hoặc chuyển đoạn byte với charset xác định; không coi một byte bất kỳ luôn là một ký tự.

### Lỗi 8: map cả tệp rất lớn trong một lần

Mỗi `MappedByteBuffer` Java 17 có capacity đo theo `int`. Nếu tệp lớn hơn `Integer.MAX_VALUE` byte, hãy map theo **các cửa sổ vùng byte** (window) có kích thước phù hợp. Mỗi cửa sổ có offset/length riêng, xử lý ranh giới bản ghi nếu dữ liệu trải qua hai cửa sổ. Cũng phải tính chi phí mapping và thời gian vùng map còn sống.

### Lỗi 9: xóa/đổi tên file ngay khi close channel

`close()` trên channel **không** bảo đảm vùng mmap mất hiệu lực ngay lập tức. Trên một số hệ điều hành thao tác xóa/đổi tên có thể gặp lỗi khi mapping còn tồn tại. Thiết kế vòng đời, dọn tệp và tái sử dụng mapping theo các ràng buộc thực tế.

## 12. Bài tập thực hành

1. Tạo file 8 byte chứa `ABCDEFGH`. Map `READ_ONLY` với offset 2, size 4. `get(0)` trả byte nào? **`C`**, vì buffer index 0 ứng với offset 2 trong file.
2. Gọi `put(0, 'X')` trên READ_ONLY. Điều gì xảy ra? **`ReadOnlyBufferException`**; không có thay đổi do lệnh ghi này thực hiện.
3. Trên file `HELLO`, map PRIVATE và đổi byte đầu thành `P`. Buffer thấy gì và file thấy gì? **Buffer thấy `PELLO`; file vẫn `HELLO`**, giả sử không có tác nhân khác sửa file.
4. Map READ_WRITE và sửa byte thứ hai `E` thành `A`. Kết quả file là gì? **`HALLO`** khi thay đổi đã được truyền tới tệp; gọi `force()` khi cần đồng bộ theo hợp đồng.
5. PRIVATE map có thể mở trên channel chỉ có `READ` không? **Không theo API Java 17**; cần cả `READ` lẫn `WRITE`.
6. `MappedByteBuffer.force()` trên PRIVATE có ghi file không? **Không**; các thay đổi private không được propagate.
7. `MappedByteBuffer.load()` có thay `force()` không? **Không**; load cố gắng nạp trang vào RAM, force đồng bộ thay đổi của READ_WRITE mapping về lưu trữ.
8. Tệp bị một tiến trình khác truncate khi ứng dụng đang dùng mapping. Có thể chắc chắn đọc mapping an toàn không? **Không**; vùng có thể trở nên không truy cập được, hành vi phụ thuộc hệ điều hành.
9. Đóng channel xong có bảo đảm xóa được file đã map ngay không? **Không**; mapping có vòng đời riêng tới khi buffer được GC thu hồi.
10. Cần chỉnh một bản dữ liệu có khả năng “commit” và “rollback” giữa nhiều tiến trình. MapMode nào đáp ứng trọn vẹn? **Không chế độ nào tự cung cấp transaction**; phải thiết kế tầng đồng bộ/lưu trữ riêng.

## 13. Tài liệu API Java 17 để tra cứu

- [FileChannel.map và MapMode — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): hợp đồng mapping, quyền mở channel, vùng ánh xạ và những hành vi phụ thuộc hệ điều hành.
- [FileChannel.MapMode — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.MapMode.html): ba chế độ chuẩn READ_ONLY, READ_WRITE, PRIVATE.
- [MappedByteBuffer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html): `force()`, `load()`, `isLoaded()` và vòng đời mapping.

**Ghi nhớ:** `READ_ONLY` = đọc, cấm ghi qua buffer; `READ_WRITE` = sửa buffer và propagate về tệp; `PRIVATE` = đọc/ghi trên **bản thay đổi riêng kiểu copy-on-write**, không propagate về tệp. Khi sử dụng mmap, cần hiểu thêm `force()`, quyền của `FileChannel`, giới hạn vùng map và vòng đời mapping vốn không kết thúc ngay khi đóng channel.
