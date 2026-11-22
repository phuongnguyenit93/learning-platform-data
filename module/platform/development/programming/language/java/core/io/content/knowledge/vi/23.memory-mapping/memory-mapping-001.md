# Memory-mapped file và MappedByteBuffer trong Java NIO

## 1. Tổng quan: ánh xạ tệp vào bộ nhớ

**Memory-mapped file** (tệp được ánh xạ bộ nhớ) là kỹ thuật yêu cầu hệ điều hành ánh xạ một vùng byte của tệp vào không gian địa chỉ bộ nhớ của tiến trình. Ứng dụng có thể đọc hoặc sửa dữ liệu trong vùng đó qua các thao tác truy cập bộ nhớ, thay vì liên tục gọi `read`/`write` để chuyển từng khối byte giữa tệp và buffer.

Trong Java NIO, API cơ bản là:

- `FileChannel.map(FileChannel.MapMode mode, long position, long size)`: ánh xạ một **vùng** của tệp.
- `MappedByteBuffer`: một loại `ByteBuffer` trực tiếp (direct buffer) đại diện cho vùng tệp đã ánh xạ; dùng `get`, `put`, `getInt`, `slice`, `duplicate`... như `ByteBuffer` bình thường.
- `MappedByteBuffer.force()`: yêu cầu ghi các thay đổi của mapping đọc/ghi xuống thiết bị lưu trữ.
- `load()` và `isLoaded()`: API gợi ý/kiểm tra gần đúng về việc dữ liệu mapping đã ở bộ nhớ vật lý hay chưa.

Memory mapping thường hữu ích khi cần truy cập lặp lại những đoạn của tệp nhị phân tương đối lớn hoặc cần random access thuận tiện bằng chỉ số. **Không có quy tắc rằng memory mapping luôn nhanh hơn `FileChannel.read/write`**: việc tạo mapping, page fault, áp lực bộ nhớ và cơ chế ghi dữ liệu có chi phí riêng.

### Hình dung sự khác biệt

```text
I/O thông thường:
Tệp trên đĩa -- FileChannel.read(buffer) --> ByteBuffer --> chương trình
Chương trình -- FileChannel.write(buffer) --> tệp trên đĩa

Memory mapping:
Tệp trên đĩa <-- quản lý trang/cache bởi hệ điều hành -->
Vùng địa chỉ bộ nhớ được ánh xạ <-- MappedByteBuffer.get/put --> chương trình
```

Sơ đồ chỉ diễn tả **mô hình lập trình**. Dữ liệu không mặc nhiên được nạp toàn bộ vào RAM khi gọi `map`; hệ điều hành thường thực hiện tải trang theo nhu cầu, và cách truyền dữ liệu thực tế phụ thuộc hệ thống.

## 2. Tạo mapping bằng FileChannel.map

Cú pháp:

```java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_ONLY,
        startOffset,
        regionLength);
```

Đoạn trên là minh họa, giả định `channel` đã mở với quyền phù hợp. Tham số:

| Tham số | Ý nghĩa |
|---|---|
| `mode` | Quy định quyền và cách phản ánh thay đổi: `READ_ONLY`, `READ_WRITE` hoặc `PRIVATE` |
| `position` / `startOffset` | Byte offset **trong tệp** nơi vùng ánh xạ bắt đầu; kiểu `long`, không âm |
| `size` / `regionLength` | Số byte ánh xạ; kiểu `long` nhưng không lớn hơn `Integer.MAX_VALUE` |
| Giá trị trả về | `MappedByteBuffer` với `position() == 0`, `limit() == capacity() == size` và mark chưa được đặt |

Ví dụ tệp có mười byte `ABCDEFGHIJ`, ánh xạ từ offset 3 với chiều dài 4:

```text
Tệp:            A B C D E F G H I J
Offset tệp:     0 1 2 3 4 5 6 7 8 9
                      |-------|
Ánh xạ:               D E F G
Index của mapping:    0 1 2 3

mapped.get(0) tương ứng byte tệp ở offset 3.
mapped.get(3) tương ứng byte tệp ở offset 6.
```

Công thức tổng quát cho một ánh xạ không bị thay đổi cách nhìn:

```text
fileOffset = mappingStartOffset + mappedBufferIndex
```

Với `map(mode, 3L, 4L)`, capacity của mapped buffer là **4**, không phải kích thước toàn tệp. Chỉ số hợp lệ để đọc bằng `get(index)` là từ 0 đến 3, miễn `limit` vẫn là 4.

Điểm dễ nhầm: `FileChannel.map` **không thay đổi current position của FileChannel**. Đây là cơ chế khác với `channel.read(buffer)` hay `channel.write(buffer)` theo vị trí hiện tại.

## 3. Ba chế độ ánh xạ: READ_ONLY, READ_WRITE, PRIVATE

| Chế độ | Được đọc? | Được `put` qua mapping? | Thay đổi mapping có ghi về tệp? | Quyền của FileChannel |
|---|---|---|---|---|
| `FileChannel.MapMode.READ_ONLY` | Có | Không; ném `ReadOnlyBufferException` | Không có thay đổi qua mapping để ghi | Mở cho `READ` |
| `FileChannel.MapMode.READ_WRITE` | Có | Có | Thay đổi được phản ánh tới tệp; thời điểm không xác định nếu chưa đồng bộ | Mở cho **cả `READ` và `WRITE`** |
| `FileChannel.MapMode.PRIVATE` | Có | Có | **Không** ghi thay đổi riêng về tệp; copy-on-write | Mở cho **cả `READ` và `WRITE`** |

### READ_ONLY

`READ_ONLY` là lựa chọn rõ ràng khi chương trình chỉ tra cứu hoặc parse nội dung tệp. Nếu gọi phương thức sửa nội dung như `put` hay `compact` trên mapping chỉ đọc, sẽ gặp `ReadOnlyBufferException`. Vẫn có thể thay `position`, `limit`, `mark` để duyệt dữ liệu.

Không nên diễn giải “read-only” thành snapshot bất biến: nếu một chương trình khác thay đổi tệp đã ánh xạ, nội dung đọc qua view có thể thay đổi, còn cách thức và thời điểm thay đổi được nhìn thấy phụ thuộc hệ điều hành.

### READ_WRITE

`READ_WRITE` cho phép sửa byte qua `put` và các thao tác tương ứng. Hệ thống sẽ đồng bộ thay đổi giữa mapping và tệp theo semantics của OS; thay đổi có thể tồn tại ở bộ nhớ/cache trước khi được ghi xuống thiết bị lưu trữ. Gọi `mapped.force()` nếu yêu cầu phải **đẩy dữ liệu mapping xuống storage** theo hợp đồng API, nhất là trước checkpoint hoặc bàn giao dữ liệu.

Không được đánh đồng “một byte đọc lại thấy giá trị mới” với “đã an toàn trước mất điện”. Độ bền dữ liệu là câu hỏi về `force`, filesystem và hệ lưu trữ.

### PRIVATE (copy-on-write)

`PRIVATE` cho phép sửa nội dung **trong view riêng**, nhưng các thay đổi đó không truyền về tệp gốc; hệ thống có thể tạo bản sao các trang bị sửa (copy-on-write). Thích hợp khi cần biến đổi nội dung được ánh xạ để tính toán thử mà không chủ ý cập nhật tệp.

Không nên dùng `PRIVATE` để thay thế mọi bản snapshot nhất quán: khả năng thấy các sửa đổi từ bên ngoài, nhất là khi có đồng thời, là vấn đề phụ thuộc OS/provider và không nên dựa vào hành vi ngầm. `force()` trên mapping `PRIVATE` không phải thao tác “commit” nội dung private về tệp.

## 4. Cơ chế dưới hệ điều hành: page fault và page cache

Bộ nhớ ảo thường được quản lý theo **trang (page)**. Khi một byte của mapping lần đầu được truy cập, dữ liệu tương ứng có thể chưa ở RAM; hệ điều hành giải quyết page fault để đưa trang tệp vào bộ nhớ. Trang có thể bị đẩy ra hoặc tải lại theo chính sách quản lý bộ nhớ.

Một số hệ quả:

1. **`map` không đồng nghĩa nạp toàn bộ vùng tệp vào RAM.** Nó thiết lập ánh xạ; dữ liệu có thể đến lúc sử dụng mới được tải.
2. Đọc lặp lại vùng nóng có thể hưởng lợi từ page cache của OS.
3. Truy cập ngẫu nhiên dày đặc tới file lớn hơn bộ nhớ vật lý có thể sinh nhiều page fault và giảm hiệu suất.
4. Ghi bằng `READ_WRITE` làm thay đổi trang memory-mapped; thời điểm flush thông thường do OS quyết định nếu không gọi API đồng bộ.
5. Java không cung cấp bảo đảm rằng truy cập vào một mapped byte luôn không phải I/O vật lý. Truy cập như bộ nhớ vẫn có thể gây page fault.
6. Memory mapping có chi phí hệ điều hành và quản lý vùng địa chỉ, nên không mặc định có lợi với thao tác rất nhỏ hoặc tệp ngắn.

Memory mapping **không loại bỏ disk I/O**: nó chuyển phần lớn quyết định nạp/ghi trang cho OS. Phương pháp phù hợp phụ thuộc kích thước file, pattern đọc/ghi, số lần truy cập và hệ điều hành.

## 5. Ví dụ Java 17+ hoàn chỉnh và kết quả chính xác

Chương trình dưới đây:

- Tạo tệp `mapped-demo.bin` chứa sáu byte ASCII `ABCDEF`.
- Mở `FileChannel` với quyền `READ` và `WRITE`.
- Ánh xạ vùng từ offset 1, dài bốn byte, tức `BCDE`.
- Truy cập byte theo **chỉ số tương đối của mapping** và sửa hai vị trí.
- Kiểm chứng rằng thay `MappedByteBuffer.position()` không làm thay đổi `FileChannel.position()`.
- Gọi `force()` để đồng bộ thay đổi mapping rồi đóng channel.
- Đọc lại tệp từ filesystem để kiểm chứng nội dung.

Lưu thành **`MemoryMappedDemo.java`**:

```java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class MemoryMappedDemo {
    public static void main(String[] args) throws IOException {
        Path file = Path.of("mapped-demo.bin");
        Files.writeString(file, "ABCDEF", StandardCharsets.US_ASCII);

        try (FileChannel channel = FileChannel.open(
                file,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {

            MappedByteBuffer mapped = channel.map(
                    FileChannel.MapMode.READ_WRITE, 1L, 4L);

            System.out.println("capacity=" + mapped.capacity());
            System.out.println("first=" + (char) mapped.get(0));
            System.out.println("channelPosition=" + channel.position());

            // mapped index 0 tương ứng file offset 1: B -> x
            mapped.put(0, (byte) 'x');

            // mapped index 2 tương ứng file offset 3: D -> y
            mapped.position(2);
            mapped.put((byte) 'y');

            System.out.println("mappedPosition=" + mapped.position());
            System.out.println("channelPosition=" + channel.position());

            mapped.force();
        }

        System.out.println("result=" +
                Files.readString(file, StandardCharsets.US_ASCII));
    }
}
```

Biên dịch/chạy tại thư mục chứa `MemoryMappedDemo.java`:

```bash
javac MemoryMappedDemo.java
java MemoryMappedDemo
```

**Stdout khi các thao tác I/O được hệ điều hành cho phép:**

```text
capacity=4
first=B
channelPosition=0
mappedPosition=3
channelPosition=0
result=AxCyEF
```

Giải thích từng kết quả:

- Mapping `(offset=1, size=4)` đại diện `BCDE` và có capacity=4, vị trí riêng ban đầu là 0.
- `mapped.get(0)` đọc chữ `B` tại file offset 1. Đây là **absolute get**, không tăng `mapped.position()`.
- `channel.position()` vẫn là 0 dù đã gọi `map` và `mapped.get/put`.
- `mapped.put(0,'x')` sửa byte `B` thành `x`. Sau đó `mapped.position(2)` và `mapped.put('y')` ghi ở mapping index 2, tương ứng file offset 3, sửa `D` thành `y`. Relative put tăng position thành 3.
- Đọc lại toàn bộ tệp có kết quả `AxCyEF`, vì chỉ byte ở file offset 1 và 3 bị thay.
- `force()` yêu cầu đồng bộ thay đổi của mapping `READ_WRITE` xuống thiết bị lưu trữ theo quy tắc API.

Chương trình cố ý để lại tệp `mapped-demo.bin` để bạn có thể mở bằng hex editor hoặc đọc lại sau khi JVM kết thúc. Có thể xóa tệp đó sau khi chương trình thoát. Cách này tránh phụ thuộc vào thời điểm hệ điều hành giải phóng memory mapping, nhất là khi xóa tệp còn đang được ánh xạ trên Windows.

## 6. Đọc/ghi primitive, byte order và chỉ số

`MappedByteBuffer` kế thừa phần lớn API của `ByteBuffer`. Các thao tác cơ bản:

| Phép gọi | Hành vi |
|---|---|
| `get()` | Đọc 1 byte từ mapped position, tăng position 1 |
| `get(int index)` | Đọc 1 byte theo chỉ số mapping, không đổi position |
| `put(byte value)` | Ghi 1 byte tại mapped position, tăng position 1 |
| `put(int index, byte value)` | Ghi tại chỉ số mapping, không đổi position |
| `getInt()` / `putInt(int)` | Đọc/ghi 4 byte, dùng byte order hiện tại |
| `getLong()` / `putLong(long)` | Đọc/ghi 8 byte, dùng byte order hiện tại |
| `position()`, `limit()`, `capacity()` | Quản lý trạng thái của chính mapped buffer |
| `slice()` / `duplicate()` | View dùng chung byte trong vùng mapping, có position/limit/mark riêng |

Các offset trong `MappedByteBuffer` là **offset tính từ đầu vùng mapping**, không phải tự động là offset toàn tệp.

```java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_WRITE, 1024L, 16L);

mapped.putInt(4, 2026); // Ghi ở file offset 1024 + 4 = 1028.
```

Đây là đoạn **minh họa**, giả định file đủ dài và channel có quyền phù hợp.

`ByteBuffer` mặc định dùng **BIG_ENDIAN**. Nếu định dạng tệp của bạn là little-endian:

```java
mapped.order(java.nio.ByteOrder.LITTLE_ENDIAN);
mapped.putInt(4, 2026);
int same = mapped.getInt(4);
```

Cần thống nhất byte order ở mọi code đọc/ghi cùng định dạng. Khi tạo `slice/duplicate` mới từ `ByteBuffer/MappedByteBuffer`, Java 17 khởi tạo byte order của view mới là `BIG_ENDIAN`; nếu dùng multi-byte primitive, nên đặt `order(...)` tường minh ở view.

**Không nhầm file offset với byte của ký tự UTF-8.** Một ký tự UTF-8 có thể dài nhiều byte, nên `mapped.get(10)` là byte thứ 11 của mapping, không phải ký tự thứ 11 của văn bản.

## 7. force(), load() và isLoaded(): ba mục đích khác nhau

### `force()`: đẩy thay đổi tới thiết bị lưu trữ

```java
mapped.force();
mapped.force(100, 200); // Yêu cầu đồng bộ vùng [100, 300) của mapping.
```

Đây là đoạn minh họa; mapping cần đủ capacity cho vùng chỉ định.

- `force()` áp dụng cho toàn vùng mapping; overload `force(int index, int length)` nhắm vào một vùng byte.
- Đối với mapping `READ_WRITE` trên thiết bị lưu trữ cục bộ, tài liệu API Java quy định khi `force` trả về thành công, các thay đổi thuộc phạm vi được yêu cầu đã được ghi xuống thiết bị theo hợp đồng API.
- Với filesystem/thiết bị không phải lưu trữ cục bộ, không có cùng bảo đảm.
- OS có thể ghi thêm dữ liệu ngoài đúng vùng yêu cầu theo đơn vị trang/khối.
- Với `READ_ONLY` hoặc `PRIVATE`, `force` không có tác dụng ghi những sửa đổi riêng về tệp.
- `force` có thể ném `UncheckedIOException` khi gặp lỗi đồng bộ.

`force` **không biến nhiều thay đổi thành giao dịch nguyên tử**. Nếu yêu cầu dữ liệu chống hỏng giữa chừng, cần một định dạng và giao thức update phù hợp (ví dụ journal, checksum, double-write hoặc cơ chế giao dịch), chứ không chỉ thêm một lần `force`.

### `load()`: chủ động đề nghị nạp trang

```java
mapped.load();
```

`load()` cố gắng đưa các trang của mapping vào bộ nhớ vật lý. Đây là best effort, có thể phát sinh page fault/I/O và tiêu tốn tài nguyên. Không mặc định gọi `load()` cho mọi tệp lớn vì có thể làm tăng áp lực bộ nhớ và không tạo cam kết lưu trú vô hạn.

### `isLoaded()`: tín hiệu gần đúng

```java
boolean likelyResident = mapped.isLoaded();
```

`true` chỉ cho biết **rất có khả năng** toàn vùng đang nằm trong bộ nhớ vật lý tại thời điểm kiểm tra. `false` không chứng minh rằng dữ liệu chắc chắn chưa được nạp. Trạng thái có thể thay đổi ngay sau phép kiểm tra. Vì thế `isLoaded()` là hint quan sát, không phải điều kiện bắt buộc để `get()` được dùng an toàn.

| Phương thức | Trọng tâm | Không nên hiểu là |
|---|---|---|
| `load()` | Thử nạp dữ liệu vào bộ nhớ vật lý | Bảo đảm mọi trang luôn nằm trong RAM |
| `isLoaded()` | Gợi ý tình trạng resident | Bằng chứng chắc chắn không có page fault |
| `force()` | Đồng bộ các thay đổi read/write mapping ra storage | Tạo snapshot, khóa hay giao dịch nguyên tử |

## 8. Vòng đời mapping và đóng FileChannel

Một sự khác biệt quan trọng với I/O dùng buffer thông thường:

**Mapping không mất hiệu lực chỉ vì `FileChannel` tạo ra nó đã đóng.** Theo API, mapping và `MappedByteBuffer` vẫn hợp lệ cho tới khi bản thân buffer được garbage collected, với điều kiện vùng file backing vẫn có thể truy cập.

Ví dụ mô tả ý tưởng:

```java
MappedByteBuffer mapped;
try (FileChannel channel = FileChannel.open(
        Path.of("data.bin"), StandardOpenOption.READ)) {
    mapped = channel.map(FileChannel.MapMode.READ_ONLY, 0, channel.size());
}
// Channel đã đóng, mapped có thể vẫn đọc được nếu vùng file còn hợp lệ.
```

Đây chỉ là đoạn minh họa, vì `data.bin` cần tồn tại và phải có kích thước thích hợp. Việc JVM giữ mapping **không** ngăn được mọi rủi ro nếu file bị xóa/truncate/thay đổi từ bên ngoài.

Các hệ quả:

1. **Đóng channel không đồng nghĩa unmap ngay**; vùng mapping có thể còn giữ tài nguyên OS.
2. Không nên dựa vào `System.gc()` như cơ chế unmap deterministic.
3. Trên một số hệ điều hành, đặc biệt Windows, file đang được ánh xạ có thể khó xóa/đổi tên ngay.
4. Java 17 `MappedByteBuffer` không cung cấp phương thức public `close()` để chủ động giải phóng mapping như đóng stream/channel.
5. Nếu chương trình tạo nhiều mapping liên tiếp, phải cân nhắc vòng đời reference, mức sử dụng virtual address space và giới hạn tài nguyên.
6. Nếu phía khác truncate file sau khi map, việc truy cập vùng không còn backing có thể phát sinh lỗi không xác định cụ thể theo API; không nên để tình huống ấy xảy ra.

Với yêu cầu quản lý vòng đời cực chặt, cần cân nhắc giải pháp khác hoặc API mới phù hợp với JDK mục tiêu; không dựa vào các thủ thuật gọi API nội bộ/JDK không công khai để ép unmap trong mã portable Java 17.

## 9. Giới hạn mỗi mapping và cách xử lý tệp rất lớn

Tuy `FileChannel.map` nhận `position` và `size` kiểu `long`, kết quả là một `ByteBuffer` dùng chỉ số/capacity kiểu `int`. Vì vậy mỗi lời gọi `map` hỗ trợ `size` tối đa **`Integer.MAX_VALUE` byte** (xấp xỉ 2 GiB trừ 1 byte), và không có nghĩa là không thể xử lý **toàn bộ tệp lớn hơn 2 GiB**.

Chiến lược cho tệp lớn là **ánh xạ theo cửa sổ (window/chunk)**:

```java
long fileSize = channel.size();
long offset = 0L;
int windowSize = 64 * 1024 * 1024; // 64 MiB, ví dụ.

while (offset < fileSize) {
    long size = Math.min((long) windowSize, fileSize - offset);
    MappedByteBuffer window = channel.map(
            FileChannel.MapMode.READ_ONLY, offset, size);

    // Phân tích window trong phạm vi [0, window.limit()).
    // Ví dụ đọc: while (window.hasRemaining()) { byte b = window.get(); }

    offset += size;
}
```

Đoạn trên là minh họa, cần channel đã mở READ và import `MappedByteBuffer`, `FileChannel`. Trong hệ thống thực:

- Không giữ tất cả windows vô thời hạn nếu không cần; việc giải phóng mapping phụ thuộc vòng đời của buffer/GC.
- Cẩn thận với **bản ghi trải qua ranh giới cửa sổ**; phải giữ phần dư hoặc chọn ranh giới chunk trùng ranh giới bản ghi.
- Không giả định fileSize bất biến nếu tệp bị bên khác thay đổi; chọn cơ chế phối hợp/snapshot phù hợp.
- `offset` dùng `long`, còn index trong window là `int`. Không ép một offset file rất lớn xuống `int`.
- Mapping có giới hạn tài nguyên hệ điều hành, không chỉ giới hạn Java heap.
- Chọn window size bằng đo đạc thực tế; kích thước 64 MiB chỉ là ví dụ thiết kế.

Ví dụ map liên tiếp nhiều chunk cho phép xử lý file hàng chục GiB, nhưng không bảo đảm một chiến lược cụ thể phù hợp trên mọi hệ điều hành.

## 10. Vùng ánh xạ, kích thước file và an toàn truy cập

`map(mode, offset, length)` đòi hỏi `offset >= 0`, `length >= 0` và `length <= Integer.MAX_VALUE`. Java có thể ném `IllegalArgumentException` nếu vi phạm các điều kiện. Việc một vùng map không nằm trọn trong kích thước tệp tại thời điểm gọi có hành vi phụ thuộc hệ thống/đặc tả; **nên chuẩn bị file và bảo đảm dải mapping hợp lệ trước khi map**.

Ví dụ kiểm tra phạm vi đối với tệp có kích thước ổn định:

```java
long fileSize = channel.size();
long offset = 1024L;
long length = 256L;

if (offset < 0 || length < 0 ||
        length > Integer.MAX_VALUE ||
        offset > fileSize ||
        length > fileSize - offset) {
    throw new IllegalArgumentException("Mapping range outside the file");
}

MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_ONLY, offset, length);
```

Đoạn này chưa phải chương trình độc lập; nó dùng cách kiểm tra `length > fileSize - offset` để tránh lỗi tràn số khi tính `offset + length`. Với tệp được tiến trình khác sửa đồng thời, kiểm tra trước không bảo đảm file không đổi ngay trước/sau lệnh map: cần quản lý đồng thời bằng cơ chế khác.

**Không truncate file trong lúc còn có mapping đang được truy cập.** Theo hợp đồng Java, mapped buffer có thể trở nên không truy cập được nếu backing file bị thu nhỏ; việc truy cập có thể ném ngoại lệ không được chỉ rõ, tại thời điểm truy cập hoặc sau đó. Không dựa vào một ngoại lệ cụ thể để phục hồi an toàn.

## 11. MappedByteBuffer, các view và trạng thái riêng

`MappedByteBuffer` kế thừa semantics `ByteBuffer`: `position`, `limit` và `mark` là trạng thái của đối tượng; chúng độc lập với `FileChannel.position()`.

- `mapped.get()`: đọc byte ở mapped position rồi tăng mapped position.
- `mapped.get(index)`: đọc tuyệt đối, không đổi mapped position.
- `mapped.put(index, value)`: sửa byte tại index trong mapping, không thay mapped position.
- `mapped.slice()`: view con trên vùng remaining; index của slice bắt đầu ở 0.
- `mapped.duplicate()`: view cùng backing storage, sao position/limit/mark ban đầu, các con trỏ độc lập về sau.
- `mapped.asReadOnlyBuffer()`: view chỉ đọc của cùng dữ liệu; không phải snapshot bất biến.

Ở Java 17, các override `MappedByteBuffer.slice()` và `duplicate()` trả về `MappedByteBuffer` nên một số tính năng mapping như `force`/`load` cũng khả dụng trên các view tương ứng. Mỗi view giới hạn vùng byte và có con trỏ riêng, nhưng vẫn cùng ánh xạ/backing dữ liệu.

Ví dụ:

```java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_WRITE, 0L, 16L);
mapped.position(4);
mapped.limit(8);

MappedByteBuffer part = mapped.slice();
// part.capacity() == 4, part.position() == 0.
// part.get(0) nhìn thấy file offset 4.
```

Đoạn là minh họa, cần file đủ 16 byte. `part` không tạo bản sao độc lập. Khi phân phối các view cho nhiều luồng, cần chính sách chia vùng và đồng bộ dữ liệu; **position riêng không đảm bảo thread-safe khi các view ghi/đọc chung vùng**.

## 12. Khi nào nên dùng memory mapping?

### Nên cân nhắc

- Đọc nhiều lần các vùng khác nhau của tệp nhị phân lớn (ví dụ chỉ mục nhị phân, dữ liệu cố định có offset).
- Truy cập theo offset rải rác trong một vùng tệp và muốn xử lý qua `get(index)`.
- Cấu trúc dữ liệu trên đĩa gần với cách biểu diễn nhị phân trong bộ nhớ; cần thiết kế byte order/offset tường minh.
- Khối dữ liệu đủ lớn hoặc số lượt truy cập đủ cao để chi phí tạo mapping đáng được bù bằng lợi ích.
- Ứng dụng chấp nhận quản lý vòng đời mapping và tính phụ thuộc hệ điều hành.

### Thường nên dùng FileChannel.read/write hoặc Files

- Tệp nhỏ, chỉ đọc một lần hoặc thao tác ngắn; `Files.readAllBytes`, `Files.newBufferedReader` hay `FileChannel.read` có thể đơn giản hơn.
- Cần stream/parse bản ghi tuần tự mà không phải giữ mapping lâu dài.
- Cần kiểm soát chặt thời điểm đóng/xóa/đổi tên file trên nhiều nền tảng.
- File có thể bị sửa kích thước thường xuyên bởi tiến trình khác; mapping dễ gặp rủi ro tính hợp lệ khi truncate.
- Cần semantics rõ ràng của vòng lặp I/O, giới hạn bộ nhớ/tài nguyên và thứ tự ghi.

**Chọn theo benchmark và mô hình dữ liệu thực tế**, không mặc định “memory mapping là zero-copy nên luôn nhanh”. Mapping vẫn phát sinh page fault và disk I/O, cũng như overhead nếu liên tục tạo/huỷ mapping cho tác vụ nhỏ.

## 13. Đồng bộ, tính nhất quán và giới hạn an toàn

1. **Thay đổi đồng thời:** Nếu tác vụ khác ghi/truncate cùng tệp, Java không đảm bảo chính xác khi nào mapped view nhìn thấy thay đổi. Không dựa vào mapping như cơ chế đồng bộ giữa các tiến trình.
2. **Đọc/ghi nhiều byte không tự động nguyên tử:** Các phương thức `getInt/putInt` trên mapping không thay thế atomics/locks hay một giao thức đồng bộ an toàn.
3. **force không phải transaction:** Đồng bộ các trang không bảo đảm nhóm nhiều bản ghi cùng thành công hoặc tự rollback.
4. **Khoá file:** `FileChannel.lock/tryLock` có thể phối hợp giữa các bên tôn trọng khóa, nhưng cách thực thi/khả năng bắt buộc phụ thuộc OS/filesystem. Kiểm soát các writer theo thiết kế ứng dụng.
5. **PRIVATE không phải immutable snapshot toàn cục:** copy-on-write bảo vệ sửa đổi qua mapping khỏi tác động về file, nhưng không thiết lập snapshot isolation cho các thay đổi đồng thời từ bên ngoài.
6. **Xử lý file từ input không tin cậy:** Xác minh kích thước, offset, length, cấu trúc bản ghi, byte order và không cho số học offset bị overflow. Có thể dùng `Math.addExact` hoặc dạng kiểm tra hiệu an toàn.
7. **Tài nguyên không nằm toàn bộ trong heap:** Mapping tiêu thụ vùng địa chỉ và tài nguyên OS; heap memory thấp không đồng nghĩa mapping là miễn phí.
8. **Độ bền dữ liệu:** Khi cần durability, quyết định thời điểm `force`, xử lý ngoại lệ và kế hoạch khôi phục thay vì giả định mọi `put` lập tức an toàn.
9. **Khả năng xóa tệp:** Đừng yêu cầu xóa/đổi tên tức thời trong khi mapping vẫn còn được giữ tham chiếu, đặc biệt khi ứng dụng phải chạy trên Windows.

## 14. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách tránh |
|---|---|---|
| Hiểu `map` là đọc toàn bộ file vào heap | Ước lượng tài nguyên và performance sai | Hiểu cơ chế mapping/page fault của OS |
| Dùng chỉ số toàn tệp trong `mapped.get(index)` | Đọc sai dữ liệu hoặc `IndexOutOfBoundsException` | Quy đổi `fileOffset - mapStartOffset` |
| Tưởng `channel.position()` thay theo `mapped.get/put` | Luồng xử lý dựa trên sai con trỏ | Quản lý riêng file position và mapped position |
| Bỏ `force` khi cần dữ liệu bền vững | Có nguy cơ thay đổi chưa xuống thiết bị | Gọi `force` ở checkpoint phù hợp, xử lý lỗi |
| Dùng `PRIVATE` rồi chờ ghi về file | Thay đổi không được commit vào file | Dùng `READ_WRITE` nếu muốn ghi về file |
| Cố `put` trên `READ_ONLY` | `ReadOnlyBufferException` | Chọn mode đúng theo quyền |
| Ánh xạ > `Integer.MAX_VALUE` trong một buffer | Tham số không hợp lệ | Chia thành mapping windows |
| Giả định `close(channel)` unmap tức thời | File vẫn bị giữ tài nguyên/khó xóa | Thiết kế lifecycle mapping rõ ràng |
| Truncate file khi có mapping còn được dùng | Lỗi truy cập không xác định cụ thể | Phối hợp bảo vệ kích thước/backing file |
| Cho rằng `isLoaded() == true` bảo đảm không page fault | Logic runtime không chính xác | Xem `isLoaded` là hint |
| Ánh xạ từng thao tác nhỏ trong vòng lặp | Overhead và nhiều mapping tồn tại | Tái sử dụng mapping hợp lý, hoặc I/O thường |
| Nhầm Java byte order của view | Đọc/ghi số nhiều byte sai | Đặt `order(...)` rõ ràng |
| Xem read-only mapping là snapshot | Có thể thấy nội dung thay đổi từ ngoài | Muốn snapshot cần thiết kế lưu trữ phù hợp |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** File có mười byte `ABCDEFGHIJ`. Gọi `channel.map(READ_ONLY, 3, 4)`. `mapped.get(0)` trả byte nào và capacity là bao nhiêu?  
**Đáp án:** Byte `D`, capacity=4. Index 0 trong mapping ứng với offset 3 trong file.

**Câu 2.** Sau khi tạo mapping rồi `mapped.position(2); mapped.get();`, `channel.position()` có tự đổi không?  
**Đáp án:** Không. Mapped buffer và FileChannel duy trì vị trí riêng; mapping access không phải relative `FileChannel.read/write`.

**Câu 3.** Mapped view `READ_ONLY` có thể gọi `position(10)` trong giới hạn hợp lệ không? Và `put(...)` thì sao?  
**Đáp án:** Có thể thay position/limit hợp lệ; các thao tác sửa byte như `put` ném `ReadOnlyBufferException`.

**Câu 4.** Sửa một byte qua mapping `READ_WRITE` rồi đọc lại thấy byte mới. Điều đó có tự chứng minh đã ghi xuống ổ đĩa an toàn trước mất điện không?  
**Đáp án:** Không. Cần xét `force()` và độ bền được cung cấp bởi OS/filesystem/thiết bị.

**Câu 5.** Mapping `PRIVATE` bị thay byte qua `put`. Thay đổi đó có được ghi vào tệp gốc khi gọi `force()` không?  
**Đáp án:** Không. Mapping private dùng copy-on-write; `force` không phải lệnh commit nội dung private về file.

**Câu 6.** Tệp 5 GiB có thể xử lý bằng Java 17 `MappedByteBuffer` không?  
**Đáp án:** Có thể ánh xạ từng phần bằng nhiều windows, mỗi phần có size không vượt `Integer.MAX_VALUE` và dùng offset file kiểu `long`. Không thể map nguyên 5 GiB vào **một** `MappedByteBuffer`.

**Câu 7.** Đóng `FileChannel` có giải phóng mapping ngay không?  
**Đáp án:** Không. Mapping độc lập với vòng đời channel sau khi đã tạo; theo API Java 17 nó tồn tại tới khi buffer được GC, với điều kiện backing region vẫn hợp lệ.

**Câu 8.** Vì sao việc truncate file trong lúc một luồng đang truy cập mapping nguy hiểm?  
**Đáp án:** Vùng đã ánh xạ có thể mất backing hợp lệ; Java không bảo đảm loại ngoại lệ hay thời điểm lỗi cụ thể. Phải phối hợp việc thay kích thước và truy cập.

## 16. Ghi nhớ

- **`FileChannel.map` biến một vùng file thành `MappedByteBuffer`**, truy cập byte như direct `ByteBuffer` với index tương đối tính từ điểm bắt đầu mapping.
- Ba mode: **`READ_ONLY` để đọc**, **`READ_WRITE` để cập nhật file**, **`PRIVATE` để thay đổi riêng bằng copy-on-write**.
- `MappedByteBuffer.position/limit` độc lập với `FileChannel.position`; map/get/put không làm FileChannel.position tự tiến.
- **`force()` xử lý yêu cầu đồng bộ sửa đổi**, còn `load/isLoaded` liên quan residency bộ nhớ và chỉ cung cấp best effort/hint.
- Mỗi mapping trong Java 17 có size tối đa **`Integer.MAX_VALUE`**, muốn xử lý file lớn hơn thì map theo cửa sổ.
- **Đóng channel không giải phóng mapping ngay**; chú ý GC, file truncation, đồng thời, tính portable và tài nguyên hệ điều hành.
- Chọn memory mapping khi pattern truy cập và benchmark chứng minh hữu ích; I/O thông thường vẫn là lựa chọn tốt cho nhiều tác vụ đơn giản.

### Tài liệu tham khảo

- Oracle Java SE 17 — `FileChannel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html
- Oracle Java SE 17 — `MappedByteBuffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html
- Oracle Java SE 17 — `ByteBuffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
