# Rủi ro khi tệp bị thay đổi kích thước trong lúc đang ánh xạ bằng Java NIO

## 1. Bối cảnh: ánh xạ tệp và kích thước tệp là hai trạng thái khác nhau

Trong Java NIO, `FileChannel.map(...)` cho phép ánh xạ một vùng của tệp vào không gian địa chỉ bộ nhớ và trả về `MappedByteBuffer`. Sau đó chương trình đọc hoặc ghi bằng các phương thức của `ByteBuffer` thay vì liên tục chuyển dữ liệu qua `FileChannel.read(...)` hoặc `write(...)`.

Ví dụ:

~~~java
try (FileChannel channel = FileChannel.open(path, StandardOpenOption.READ)) {
    MappedByteBuffer mapped = channel.map(
            FileChannel.MapMode.READ_ONLY, 0, 8);
    byte firstByte = mapped.get(0);
}
~~~

Đây là **mảnh mã minh họa**: biến `path` và các import cần được định nghĩa, tệp phải có ít nhất 8 byte khi lập mapping và môi trường phải hỗ trợ thao tác này.

Có ít nhất ba đại lượng cần phân biệt:

- **Kích thước tệp hiện tại** (`channel.size()` hoặc `Files.size(path)`): có thể thay đổi do ghi nối, truncate hoặc tác nhân khác.
- **Phạm vi mapping**: được xác định tại lúc gọi `map(mode, position, size)`, ví dụ offset tệp từ 0 đến trước byte số 8. Nó không tự tăng/giảm đồng bộ với kích thước tệp.
- **Trạng thái của `MappedByteBuffer`**: `position`, `limit` và `capacity` là trạng thái của buffer; `capacity` cố định theo kích thước mapping, không phải một biến luôn phản ánh kích thước tệp.

Sơ đồ khi ban đầu tệp có 8 byte:

~~~text
Tệp ban đầu, size = 8:
offset:     0   1   2   3   4   5   6   7
         +---+---+---+---+---+---+---+---+
         | A | B | C | D | E | F | G | H |
         +---+---+---+---+---+---+---+---+
                    |  map(0, 8)  |
                    v             v
Mapping: +---+---+---+---+---+---+---+---+
         | A | B | C | D | E | F | G | H |
         +---+---+---+---+---+---+---+---+
         capacity = 8

Một tác nhân khác truncate tệp xuống size = 3:
         +---+---+---+
Tệp:     | A | B | C |
         +---+---+---+

Mapping cũ: vẫn biểu diễn vùng có capacity = 8,
             nhưng phần tương ứng byte 3..7 có thể
             không còn truy cập được. KHÔNG tự kiểm chứng
             điều này bằng cách đọc những byte đó.
~~~

**Điểm mấu chốt:** một mapping có thể còn tồn tại trong khi vùng tệp làm cơ sở cho nó đã biến đổi. Việc một thao tác Java vẫn cho phép chỉ số `get(7)` theo `limit` không chứng minh vị trí đó còn được hệ điều hành hỗ trợ bởi tệp hiện tại.

## 2. Hợp đồng Java 17: hành vi nào được bảo đảm?

Theo Javadoc của `FileChannel.map` và `MappedByteBuffer` trên Java 17:

1. Một vùng ánh xạ có thể trở nên **không truy cập được toàn bộ hoặc một phần vào bất kỳ thời điểm nào**, ví dụ khi tệp nền bị truncate.
2. Khi truy cập vùng không còn truy cập được, API **không bảo đảm một loại ngoại lệ xác định**; lỗi có thể được phát hiện ngay khi truy cập hoặc về sau. Vì vậy không thể viết một đoạn `catch` cụ thể rồi cho rằng đã an toàn trên mọi hệ điều hành.
3. Khi nội dung **hoặc kích thước** tệp thay đổi, việc những thay đổi đó có được phản ánh trong buffer đã map hay không và phản ánh vào lúc nào là **không được xác định thống nhất**.
4. Hành vi của `map` nếu vùng yêu cầu **không nằm trọn trong tệp** cũng không được bảo đảm đồng nhất theo Java 17.
5. Mapped buffer và channel có **vòng đời khác nhau**: đóng channel không nhất thiết hủy ngay mapping; mapping có thể tiếp tục tồn tại đến khi buffer được garbage collector thu hồi.

Do vậy, không được xem việc đọc thành công trên một hệ điều hành hoặc một JDK cụ thể là bằng chứng một thao tác cũng an toàn trên môi trường khác.

Tham khảo hợp đồng API:

- [FileChannel.map — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html#map(java.nio.channels.FileChannel.MapMode,long,long))
- [MappedByteBuffer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html)

## 3. Trường hợp nguy hiểm nhất: truncate nhỏ hơn vùng đã ánh xạ

Giả sử ứng dụng đã map vùng `[0, 4096)` của một tệp. Một luồng hoặc tiến trình khác gọi `FileChannel.truncate(1024)` làm tệp chỉ còn 1024 byte.

Về phía buffer, `capacity()` có thể vẫn là 4096 vì capacity được xác định tại thời điểm tạo. Nhưng khi ứng dụng tiếp tục đọc các index 1024 đến 4095, một phần của mapping có thể đã mất sự hỗ trợ từ tệp.

~~~text
Thời điểm T0:       file = 4096 byte; map(0, 4096)
Thời điểm T1:       ứng dụng đang xử lý index 0..1023
Thời điểm T2:       tiến trình khác truncate file còn 1024
Thời điểm T3:       ứng dụng cố đọc index 3000 -> nguy cơ
                    truy cập vùng mapping không khả dụng
~~~

Các hậu quả thực tế có thể là:

- Truy cập buffer gặp lỗi mà chương trình không thể dự đoán theo một exception type cố định.
- Tiến trình nhận lỗi từ cơ chế bảo vệ bộ nhớ/mapping của hệ điều hành; chi tiết phụ thuộc runtime và OS.
- Một quy trình đọc tuần tự đang chạy dở không thể chứng minh tính đúng đắn hoặc tính nhất quán của dữ liệu nữa.
- Tệp có thể bị thay thế hoặc các metadata đã dùng để xác nhận nội dung không còn tương ứng với đối tượng tệp đang được ứng dụng sử dụng.

**Không thử truy cập “byte đã mất” để chẩn đoán bằng mã production.** Mục đích của thiết kế an toàn là tránh tạo điều kiện truy cập vùng không hợp lệ, không phải phụ thuộc vào một loại lỗi sẽ được ném ra.

### 3.1. Ví dụ mã có rủi ro — không chạy như bài thực hành

~~~java
// MẢNH MINH HỌA RỦI RO: KHÔNG CHẠY để kiểm nghiệm lỗi.
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_ONLY, 0, 4096);

// Có thể xảy ra từ luồng hoặc tiến trình KHÁC:
otherChannel.truncate(1024);

// Không được suy ra get(3000) là an toàn từ capacity() == 4096.
byte value = mapped.get(3000);
~~~

Biến `channel`, `otherChannel` và đối tượng tệp không được khởi tạo trong đoạn này: đây là **mã minh họa tình huống nguy hiểm**, không phải ví dụ độc lập. Nó cho thấy lỗi thiết kế cần tránh, tuyệt đối không bảo đảm bất kỳ stdout/exception cụ thể nào.

## 4. Khi tệp tăng kích thước: mapping cũ không tự mở rộng

Trường hợp ngược lại: tệp ban đầu có 8 byte và chương trình map 8 byte. Sau đó tác nhân khác nối thêm 4 byte, tệp dài 12 byte.

~~~text
T0: file.size() = 8
    mapped.capacity() = 8

T1: append 4 byte -> file.size() = 12

T2: mapped.capacity() vẫn = 8
    index 8..11 không nằm trong không gian chỉ số của buffer cũ.
~~~

`MappedByteBuffer` không biến thành buffer có capacity 12 chỉ vì file đã dài hơn. Nếu ứng dụng muốn xử lý byte mới nằm ngoài khoảng đã map, cần **tạo một mapping phù hợp** (ví dụ mapping vùng mới hoặc ánh xạ lại trên instance/vùng khác) sau khi đã xác định bản dữ liệu hợp lệ.

Điều này khác với trường hợp truncate:

- **Tăng tệp**: phần byte thêm vào nằm ngoài ranh giới cũ; cố `mapped.get(8)` khi `limit=8` sẽ vi phạm chỉ số buffer thông thường.
- **Giảm tệp**: một chỉ số **vẫn có thể hợp lệ theo buffer** nhưng vùng tệp phía dưới không còn tồn tại, khiến rủi ro phức tạp hơn.

Không được giả định phép append sẽ an toàn khi đồng thời còn một writer có thể ghi đè/truncate phần cũ. Cần chính sách ownership và đồng bộ khi nhiều tác nhân cùng thay đổi một tệp.

## 5. Thay đổi nội dung và thay đổi kích thước đều tác động tới tính nhất quán

Một file giữ nguyên kích thước nhưng bị ghi đè nội dung vẫn có thể làm kết quả đọc bị trộn giữa nhiều phiên bản.

Giả sử bộ phân tích đọc header và payload:

~~~text
Phiên bản A:
[ header length=8 ][ payload của A ]

Writer cập nhật thành phiên bản B cùng kích thước:
[ header length=8 ][ payload của B ]

Reader đọc header từ A, rồi payload từ B
=> Kết quả có thể không tương ứng phiên bản hoàn chỉnh nào.
~~~

`READ_ONLY` chỉ từ chối ghi **qua mapped buffer đó**, không khóa tệp đối với các writer khác. `PRIVATE` cũng không phải snapshot cố định tuyệt đối trước các thay đổi từ bên ngoài. Trong cả ba mode, tính nhất quán của dữ liệu khi file bị sửa từ nguồn khác cần được giải quyết bằng thiết kế bổ sung.

Các thuộc tính như `FileChannel.size()`, `Files.getLastModifiedTime(...)` hay `BasicFileAttributes.fileKey()` có thể giúp phát hiện những thay đổi **quan sát được**, nhưng không chứng minh rằng dữ liệu chưa bị sửa giữa hai phép kiểm tra. Timestamp có độ phân giải khác nhau; fileKey có thể không được provider cung cấp; kích thước giữ nguyên không loại trừ ghi đè nội dung.

## 6. Ba MapMode có giúp bảo vệ khi tệp đổi kích thước không?

| MapMode | Hành vi ghi qua mapping | Có tự bảo vệ khỏi tệp bị truncate/resize bên ngoài không? |
| --- | --- | --- |
| `READ_ONLY` | `put` bị cấm, ném `ReadOnlyBufferException`. | **Không.** Bản thân vùng đã map vẫn có thể bị ảnh hưởng khi tệp nền thay đổi. |
| `READ_WRITE` | `put` có thể cập nhật tệp, `force()` hỗ trợ yêu cầu đồng bộ. | **Không.** Writer bên ngoài vẫn có thể truncate hoặc thay đổi phạm vi ánh xạ. |
| `PRIVATE` | Ghi bằng copy-on-write, không propagate thay đổi riêng về tệp. | **Không.** Nó không bảo đảm tạo snapshot bất biến trước mọi thay đổi kích thước ở tệp nền. |

Không cố “khắc phục truncate” bằng `mapped.force()`, `mapped.load()` hoặc `mapped.isLoaded()`:

- `force()` làm việc với yêu cầu đồng bộ thay đổi của READ_WRITE mapping; không sửa lại phạm vi tệp bị mất. Nó không có tác dụng commit với PRIVATE.
- `load()` cố nạp trang của mapping vào RAM. Nó không làm mapping độc lập khỏi tệp nền và không cấp quyền đọc một vùng đã trở nên không khả dụng.
- `isLoaded()` chỉ là một gợi ý về resident pages, không bảo đảm truy cập an toàn khi file bị resize.

Nguyên tắc: **MapMode quy định kiểu truy cập và truyền thay đổi**, chứ không phải hợp đồng khóa kích thước tệp.

## 7. Vì sao kiểm tra size trước mỗi get() vẫn chưa đủ?

Một cách sửa dễ nghĩ tới:

~~~java
long currentSize = channel.size();
if (targetOffset < currentSize) {
    return mapped.get(index);
}
~~~

Đây là **mảnh minh họa thiếu an toàn**, với `targetOffset`, `index` và `mapped` được khai báo ở nơi khác. Kể cả khi phép kiểm tra đúng tại thời điểm đầu, một writer khác vẫn có thể rút ngắn tệp **sau khi kiểm tra nhưng trước khi `get()`**.

Đó là lỗi **TOCTOU** (*time-of-check to time-of-use*):

~~~text
Reader                         Writer
  |                              |
  +-- size() => 4096             |
  |                              +-- truncate(1024)
  +-- mapped.get(3000)           |
         có thể không an toàn    |
~~~

Vì thế:

- Kiểm tra `size` và ranh giới `offset + length` là **cần thiết** khi lập mapping, nhưng không đủ trong môi trường nhiều writer không có phối hợp.
- Kiểm tra metadata lặp lại sau từng record có thể giúp phát hiện sự thay đổi, nhưng không loại bỏ khoảng chạy đua ở giữa các thao tác.
- Một `synchronized` hoặc `ReentrantReadWriteLock` trong **một JVM** chỉ bảo vệ các luồng thực sự tham gia cùng cơ chế khóa; tiến trình khác vẫn có thể sửa tệp.
- `FileLock` có thể hữu ích khi mọi tác nhân tuân thủ chính sách khóa, nhưng tính hiệu lực trên các hệ điều hành và filesystem khác nhau; không coi nó là lời giải phổ quát chống resize khi mmap.

## 8. Giải pháp 1: sở hữu độc quyền vòng đời và kích thước tệp

Khi chương trình tự tạo và kiểm soát file, cách đơn giản nhất là **không cho thay đổi kích thước trong suốt thời gian còn mapping đang được sử dụng**.

Một quy trình có trách nhiệm:

1. Ghi xong dữ liệu và xác lập kích thước file.
2. Công bố file cho reader khi dữ liệu đã hoàn chỉnh.
3. Mỗi reader mở mapping trên file ổn định, xử lý và ngừng tham chiếu đến mapping sau khi hoàn tất.
4. Nếu cần phát hành phiên bản mới, ghi ra file **mới** với tên/version riêng; không truncate bản đang được reader sử dụng.
5. Thu hồi file cũ khi không còn reader và khi OS cho phép giải phóng tài nguyên liên quan.

Nếu có thể kiểm soát mọi writer, đây là nền tảng giảm rủi ro tốt hơn việc cố bắt ngoại lệ phát sinh từ truy cập vùng đã mất.

### 8.1. Không thay thế trực tiếp file reader đang map

Một lựa chọn triển khai là file phiên bản hóa:

~~~text
data-v001.bin     <- reader A đã map, giữ nguyên
data-v002.bin     <- writer tạo bản mới hoàn chỉnh
current.version   <- metadata chỉ tới phiên bản mới

Reader B mở data-v002.bin.
Reader A hoàn tất trên data-v001.bin.
Sau khi tất cả reader cũ ngừng dùng, mới dọn data-v001.bin.
~~~

Cần bảo đảm cập nhật metadata/version theo phương thức atomic phù hợp để reader chỉ thấy file đã hoàn chỉnh, và có giải pháp quản lý tham chiếu (reference count, lease, epoch, hoặc giới hạn vòng đời reader).

`Files.move(..., ATOMIC_MOVE)` có thể hỗ trợ thao tác publish **khi filesystem hỗ trợ**, nhưng có thể ném `AtomicMoveNotSupportedException`; nó không tự bảo đảm một chiến lược consistent snapshot hoặc quyền xóa/đổi tên của file đang map trên mọi nền tảng.

## 9. Giải pháp 2: ánh xạ một bản sao ổn định

Nếu nguồn có thể bị writer khác thay đổi và ứng dụng cần bản dữ liệu độc lập, có thể **tạo bản sao rồi ánh xạ bản sao đó**. Khi bản sao thuộc sở hữu riêng và không bị tiến trình khác sửa, việc resize tệp nguồn không ảnh hưởng tới kích thước bản sao.

~~~text
Tệp nguồn (có thể đổi):
source.bin (8 byte) ----- COPY ----- snapshot.bin (8 byte)
       |                                   |
       |                                   +-- READ_ONLY mapping
       |
       +-- writer truncate về 2 byte

snapshot.bin vẫn có 8 byte và mapping của nó
không bị việc truncate SOURCE tác động.
~~~

**Điều kiện quan trọng:** `Files.copy` không tự bảo đảm một snapshot nhất quán nếu writer đang sửa nguồn **trong lúc copy**. Cần phối hợp ownership/locking, đọc bản nguồn đã publish bất biến, hoặc dùng cơ chế snapshot thực sự của storage/filesystem nếu yêu cầu consistency mạnh. Ngoài ra, không được để một actor khác truncate chính **tệp bản sao** khi reader đang map nó.

### 9.1. Chương trình Java 17+ chạy được, tránh truncate vùng đang map

Ví dụ này chỉ thay đổi kích thước **tệp nguồn**. Mapping được tạo trên **một tệp snapshot khác**, nên có kết quả xác định trong chương trình đơn luồng. Không có bước thử truy cập mapping bất hợp lệ.

Lưu vào `SafeMappedSnapshotDemo.java`:

~~~java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class SafeMappedSnapshotDemo {

    private static String ascii(MappedByteBuffer mapped) {
        MappedByteBuffer view = mapped.duplicate();
        view.position(0);
        byte[] bytes = new byte[view.remaining()];
        view.get(bytes);
        return new String(bytes, StandardCharsets.US_ASCII);
    }

    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("mmap-resize-demo-");
        Path source = dir.resolve("source.bin");
        Path snapshot = dir.resolve("snapshot.bin");

        // Đăng ký dọn lúc JVM kết thúc, thay vì cố xóa file đang map.
        // Các entry được đăng ký theo thứ tự ngược với thứ tự dọn.
        dir.toFile().deleteOnExit();
        source.toFile().deleteOnExit();
        snapshot.toFile().deleteOnExit();

        Files.writeString(source, "ABCDEFGH", StandardCharsets.US_ASCII);
        Files.copy(source, snapshot);

        try (FileChannel channel = FileChannel.open(
                snapshot, StandardOpenOption.READ)) {

            long size = channel.size();
            long offset = 2;
            int length = 4;

            // Kiểm tra phép trừ để tránh overflow khi kiểm tra offset+length.
            if (offset < 0 || length <= 0 ||
                    offset > size || length > size - offset) {
                throw new IOException("Mapping vượt phạm vi snapshot");
            }

            MappedByteBuffer mapped = channel.map(
                    FileChannel.MapMode.READ_ONLY, offset, length);

            System.out.println("snapshotSize=" + size);
            System.out.println("mappedCapacity=" + mapped.capacity());
            System.out.println("mappedBefore=" + ascii(mapped));

            // Chỉ rút ngắn SOURCE, không động đến SNAPSHOT đang được map.
            Files.writeString(
                    source,
                    "XY",
                    StandardCharsets.US_ASCII,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING);

            System.out.println("sourceAfterResize=" +
                    Files.readString(source, StandardCharsets.US_ASCII));
            System.out.println("mappedAfter=" + ascii(mapped));
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SafeMappedSnapshotDemo.java
java SafeMappedSnapshotDemo
~~~

Stdout xác định trong môi trường hỗ trợ đọc và ánh xạ tệp cục bộ:

~~~text
snapshotSize=8
mappedCapacity=4
mappedBefore=CDEF
sourceAfterResize=XY
mappedAfter=CDEF
~~~

Giải thích:

- Tệp `source.bin` có 8 byte `ABCDEFGH`; `Files.copy` tạo `snapshot.bin` độc lập cũng có 8 byte.
- Mapping dùng `offset=2`, `length=4` nên vùng đọc ban đầu là `CDEF`; `capacity=4`, không phải toàn bộ 8 byte của snapshot.
- Ghi `"XY"` với `TRUNCATE_EXISTING` thay thế nội dung nguồn, đưa kích thước **source** về 2 byte.
- Snapshot không bị ghi đè/truncate, nên mapping vẫn xem được `CDEF`.
- Ví dụ dọn file bằng `deleteOnExit()` vì thời điểm mapping thực sự được giải phóng sau khi đóng channel là không xác định. Với ứng dụng thực tế, cần chiến lược vòng đời riêng; không coi `deleteOnExit` là hệ thống quản lý file lâu dài.

Ví dụ chỉ minh họa **cách cô lập một nguồn có thể thay đổi**. Nếu muốn snapshot nhất quán khi nguồn có writer song song, cần phối hợp xuất bản bản hoàn chỉnh hoặc tính năng snapshot đáng tin cậy trước khi `Files.copy`.

## 10. Giải pháp 3: cửa sổ mapping và tái lập vùng truy cập theo version

Với tệp lớn hoặc luồng dữ liệu append, có thể chia xử lý thành các **cửa sổ ánh xạ** có kích thước giới hạn:

~~~text
Tệp 20 MiB:
  [0..4 MiB) [4..8 MiB) [8..12 MiB) [12..16 MiB) [16..20 MiB)
      window 1    window 2    window 3    window 4     window 5

Mỗi lần:
  - chỉ map vùng hợp lệ đã được công bố;
  - đọc hết vùng và hoàn tất công việc;
  - chuyển sang vùng/phiên bản mới theo quy tắc ownership.
~~~

Lợi ích của mapping theo cửa sổ:

- Mỗi `MappedByteBuffer` có `capacity` đo bằng `int`, nên tránh yêu cầu map một vùng lớn hơn `Integer.MAX_VALUE` byte trên Java 17.
- Có thể giới hạn lượng dữ liệu mỗi lần xử lý.
- Nếu tệp **chỉ được append** và các byte đã công bố không bị sửa, reader có thể map thêm vùng mới theo mốc chiều dài đã commit.

Nhưng **chia cửa sổ không tự loại bỏ rủi ro truncate**. Nếu writer được phép thu nhỏ hoặc ghi đè vùng đang dùng, bất kỳ cửa sổ nào cũng có thể mất hiệu lực. Tạo cửa sổ mới sau khi đọc `channel.size()` cũng có thể gặp TOCTOU nếu có writer không phối hợp.

Một phiên bản hệ thống tốt hơn phải có metadata cho **committed length** và **file version**, cùng nguyên tắc writer không được truncate dữ liệu đã công bố khi reader còn sử dụng.

## 11. Đồng bộ giữa các luồng và các tiến trình

### 11.1. Cùng một JVM

Nếu ứng dụng có thread đọc và thread ghi:

- Một `ReadWriteLock` có thể cho phép nhiều reader cùng đọc trong khi writer phải chờ để resize.
- Writer giữ write lock từ lúc bắt đầu thao tác thay kích thước tới khi hoàn tất việc publish phiên bản mới.
- Reader giữ read lock trong thời gian mapping và đọc dữ liệu cần bảo vệ.

Tuy nhiên, một lock Java chỉ có tác dụng với những luồng **thực sự dùng cùng lock**. Nếu một tiến trình khác có quyền truncate file thì cơ chế khóa trong JVM không giải quyết được rủi ro bên ngoài.

### 11.2. Khác tiến trình

Có thể xem xét `FileChannel.lock(...)` hoặc `tryLock(...)` như cơ chế phối hợp khi các actor cùng tuân theo quy tắc. Nhưng cần hiểu:

- Khả năng shared/exclusive lock phụ thuộc OS và filesystem.
- Một số file lock có tính **advisory**: các tiến trình không tuân thủ vẫn có thể thay đổi file.
- Mapping và locking có thể tương tác khác nhau trên từng nền tảng, kể cả trường hợp không tạo được lock hoặc việc map gặp lỗi.

Vì vậy, với dữ liệu quan trọng, **độc quyền sở hữu phiên bản tệp, snapshot bất biến hoặc giao thức publish mới** thường dễ kiểm chứng hơn kỳ vọng một lệnh lock có thể ngăn mọi thay đổi bên ngoài.

## 12. Những API cần dùng đúng mục đích

| API | Hỗ trợ điều gì? | Không giải quyết được điều gì? |
| --- | --- | --- |
| `FileChannel.map(mode, offset, length)` | Tạo mapping cố định trên vùng được yêu cầu. | Không tự theo dõi tăng/giảm size để điều chỉnh capacity. |
| `channel.size()` / `Files.size(path)` | Đọc kích thước tệp tại thời điểm gọi. | Không bảo vệ khỏi resize ngay sau khi đọc. |
| `channel.truncate(newSize)` | Nếu nhỏ hơn kích thước hiện có thì cắt ngắn file (khi channel được phép ghi). | Không tự sửa mọi mapping còn đang tồn tại ở reader. |
| `mapped.force()` | Đồng bộ sửa đổi của READ_WRITE mapping theo hợp đồng. | Không khôi phục phần tệp bị truncate, không bảo đảm snapshot. |
| `mapped.load()` | Thử nạp các trang mapping vào bộ nhớ. | Không giữ file ở kích thước cũ hoặc giữ trang truy cập được khi nền thay đổi. |
| `mapped.isLoaded()` | Đưa ra gợi ý trạng thái resident. | Không phải phép xác nhận an toàn để tránh truncate. |
| `FileLock` | Phối hợp truy cập giữa actor tuân thủ cơ chế khóa trên nền tảng hỗ trợ. | Không tự chống mọi writer không hợp tác trên mọi OS/filesystem. |
| `Files.copy(...)` | Tạo file đích độc lập khi copy thành công. | Không bảo đảm bản sao nhất quán nếu nguồn bị sửa cùng lúc. |
| `Files.move(..., ATOMIC_MOVE)` | Yêu cầu move nguyên tử nếu provider hỗ trợ. | Không bảo đảm reader dùng path sẽ tự đổi mapping; không giải phóng mapping cũ. |

Với `FileChannel.truncate(n)`, nếu `n` lớn hơn hoặc bằng kích thước tệp đang có, API **không nhất thiết mở rộng tệp**. Để tạo tệp có kích thước mới lớn hơn, cần một thao tác ghi hoặc cơ chế được provider hỗ trợ; không gọi `truncate(largerSize)` và giả định đã cấp vùng byte mới.

## 13. Quy tắc thiết kế một mmap reader chịu được việc thay đổi phiên bản tệp

Một reader production an toàn nên xác định rõ hợp đồng với writer trước khi tối ưu bằng mmap:

1. **Tệp nào được phép thay đổi?** Nếu tệp đang có reader, tối thiểu phải cấm truncate/ghi đè vùng đã công bố hoặc chuyển sang mô hình immutable versions.
2. **Version nhận diện thế nào?** Có thể dùng ID phiên bản, manifest, nội dung checksum hoặc file generation; chỉ size và mtime không đủ cho yêu cầu consistency mạnh.
3. **Reader mở đúng phiên bản nào?** Reader lấy đường dẫn phiên bản đã hoàn chỉnh, giữ ổn định trong toàn bộ lượt xử lý.
4. **Khi nào file cũ được dọn?** Cần xác nhận không còn reader hoặc lease sử dụng, ngoài việc cân nhắc OS giữ mapping sau khi đóng channel.
5. **Có bao giờ map vượt EOF không?** Ranh giới phải dựa trên kích thước đã được công bố và được giữ ổn định qua cơ chế sở hữu.
6. **Điều kiện thất bại nào có thể làm dừng xử lý?** Phân biệt file không tồn tại, lỗi quyền, dữ liệu sai định dạng, phiên bản bị thu hồi và IOException.
7. **Mục tiêu chỉ đọc hay sửa?** Nếu chỉ đọc, chọn `READ_ONLY` trên immutable file. Nếu cần sửa, xác định giao thức commit và độ bền dữ liệu; `READ_WRITE.force()` không giải quyết việc thay kích thước đồng thời.
8. **Có thực sự cần mmap?** Nếu dữ liệu được writer khác sửa kích thước liên tục và không thể phối hợp, đọc thành các buffer độc lập qua `FileChannel.read(...)` có thể dễ kiểm soát lỗi và vòng đời hơn, dù vẫn cần thiết kế cách bảo đảm tính nhất quán nội dung.

Không thể “catch mọi lỗi mmap” rồi tiếp tục như chưa có vấn đề. Một reader gặp dấu hiệu dữ liệu không còn tương ứng với phiên bản đã được xác nhận cần dừng và tải lại theo quy trình được thiết kế.

## 14. Lỗi phổ biến cần tránh

### Sai lầm 1: thấy capacity chưa đổi nên tin nội dung còn tồn tại

Sau khi file bị truncate, `mapped.capacity()` vẫn mô tả kích thước mapping ban đầu. Nó **không** chứng minh mọi byte tương ứng còn khả dụng.

### Sai lầm 2: gọi force() để phục hồi dữ liệu đã mất

`force()` không mở rộng file hoặc tái cấp lại vùng mapping bị truncate. Với `READ_WRITE` nó chỉ liên quan đến đồng bộ các sửa đổi từ mapping về thiết bị lưu trữ.

### Sai lầm 3: nghĩ PRIVATE là snapshot bất biến của file

PRIVATE có semantics copy-on-write đối với sửa đổi thông qua mapping đó. Nó không bảo đảm cô lập khỏi mọi thay đổi nội dung hoặc kích thước từ bên ngoài.

### Sai lầm 4: tin check size trước get loại bỏ rủi ro

Kiểm tra kích thước không khóa file. Writer có thể truncate ngay sau đó. Đây là TOCTOU; cần kiểm soát sự thay đổi bằng giao thức hay ownership.

### Sai lầm 5: bỏ qua lifetime của mapping

Đóng `FileChannel` không bảo đảm vùng mapping bị thu hồi ngay. Trên một số hệ điều hành, delete/rename/truncate có thể bị hạn chế do file vẫn đang được map.

### Sai lầm 6: map tệp có thể bị thay bằng phiên bản khác mà không lưu version

Path là một tên có thể được gắn với đối tượng tệp khác sau thao tác replace. Một mapping đã tồn tại không được bảo đảm sẽ tự thay đổi sang bản mới chỉ vì cùng path đang trỏ tới bản khác. Reader phải quản lý object/version tương ứng.

### Sai lầm 7: cho rằng file mới được append tự xuất hiện trong buffer cũ

`MappedByteBuffer` có capacity cố định. Byte mới nằm ngoài vùng ánh xạ cũ cần được đọc qua mapping hoặc API mới có phạm vi phù hợp.

### Sai lầm 8: kiểm thử bằng cố tình gây lỗi OS trên file đang map

Truncate một file đang map rồi cố đọc phần bị cắt là một thử nghiệm có thể gây hậu quả ngoài khả năng xử lý theo một exception chuẩn trên các nền tảng. Hãy kiểm tra chính sách ownership, vùng map hợp lệ và đường chuyển phiên bản bằng các bài test không truy cập mapping đã mất hiệu lực.

## 15. Câu hỏi tự kiểm tra

1. **Tệp dài 4 KiB đã được map toàn bộ, sau đó truncate còn 1 KiB. `mapped.capacity()` có tự giảm thành 1 KiB?** Không. Capacity của buffer cố định; phần mapping ngoài độ dài mới có nguy cơ không khả dụng.
2. **Có thể dựa vào `catch (IndexOutOfBoundsException)` để xử lý mọi lần truy cập phần bị truncate?** Không. Index có thể vẫn hợp lệ trong buffer trong khi mapping nền không còn hợp lệ; API không quy định một loại exception cố định cho trường hợp này.
3. **Nếu file được append từ 8 lên 12 byte, buffer đã map 8 byte có tự nhìn thấy index 8..11 không?** Không; capacity vẫn 8.
4. **`READ_ONLY` có ngăn tiến trình khác truncate file không?** Không. Nó chỉ cấm ghi qua buffer này.
5. **`PRIVATE` có bảo đảm snapshot nhất quán khi file nền bị thay đổi kích thước không?** Không.
6. **Vì sao kiểm tra `channel.size()` trước `mapped.get(i)` chưa đủ?** Có thể xảy ra resize giữa check và get.
7. **`FileChannel.force()` hoặc `MappedByteBuffer.force()` có “fix” được mapping sau truncate không?** Không. Đây là các API đồng bộ dữ liệu theo hợp đồng, không phải công cụ tái lập kích thước.
8. **Cách tránh rủi ro phổ biến nhất khi có nhiều reader?** Công bố các bản file bất biến/versioned và không thay đổi kích thước bản reader đang dùng; dọn bản cũ theo vòng đời reader.
9. **`Files.copy(source, snapshot)` đã đủ là snapshot nhất quán dưới concurrent writer chưa?** Chưa. Cần phối hợp để không copy giữa lúc dữ liệu đang thay đổi, hoặc dùng cơ chế snapshot của storage.
10. **Vì sao cần quản lý file cũ ngay cả sau khi đóng channel?** Mapping có vòng đời riêng và không được bảo đảm giải phóng ngay khi channel đóng.
11. **Có thể dùng một `MappedByteBuffer` Java 17 để map tệp lớn hơn 2 GiB vào một buffer duy nhất không?** Không theo giới hạn kích thước mapping của API này; cần chia vùng, hoặc chọn API phù hợp.
12. **Nếu yêu cầu dữ liệu nhất quán, có nên dựa riêng vào mtime và file size?** Không. Chúng chỉ là các dấu hiệu, không bảo đảm file không bị sửa giữa hai lần kiểm tra.

**Ghi nhớ:** memory mapping gắn buffer với một **vùng tệp ở thời điểm tạo mapping**, nhưng không đóng băng tệp nền. Nếu tệp bị thu nhỏ, vùng mapping có thể mất khả năng truy cập; nếu tệp được mở rộng, buffer cũ không tự tăng capacity. Hãy quản lý **ownership, version và vòng đời tệp**, giữ dữ liệu đang map ổn định, hoặc ánh xạ một bản sao bất biến khi cần cô lập reader khỏi resize.
