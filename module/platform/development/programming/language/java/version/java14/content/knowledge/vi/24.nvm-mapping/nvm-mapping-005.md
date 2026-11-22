# Tạo `MappedByteBuffer` qua `FileChannel.map` — ánh xạ tệp và NVM trong Java hiện đại

> **Mục tiêu:** biết cách dùng `java.nio.channels.FileChannel.map(MapMode,long,long)` tạo `MappedByteBuffer`, hiểu cách offset file tương ứng index trong buffer, lựa chọn `READ_ONLY`/`READ_WRITE`/`PRIVATE`, đồng bộ bằng `force()`, quản lý vòng đời an toàn và áp dụng đúng các chế độ `ExtendedMapMode.READ_ONLY_SYNC`/`READ_WRITE_SYNC` khi **thực sự có NVM được hỗ trợ**. API ánh xạ file vẫn được hỗ trợ trong Java SE 17/25/26; mở rộng NVM của **JEP 352** có từ Java 14. Các ví dụ chính dùng **JDK 17+** mà không phụ thuộc tính năng preview hay thao tác native nội bộ lỗi thời.

## 1. Ánh xạ tệp là gì? Phân biệt mmap, heap và NVM

**Memory mapping** là cơ chế ánh xạ một vùng byte từ file vào không gian địa chỉ ảo của tiến trình. Thay vì gọi `read(...)` rồi chép dữ liệu sang một `byte[]` trên heap, ứng dụng có thể dùng các thao tác `get`/`put` của buffer để truy cập nội dung tệp thông qua cơ chế quản lý trang bộ nhớ của hệ điều hành.

```text
Tệp dữ liệu trên storage
    byte 0 .......... 15 | 16 .......... 31 | 32 .....
                           ^               ^
                           | vùng map 16 B |
                           v               v
                       MappedByteBuffer
                       index 0 .......... 15
                           ^
                           |
                        Java get/put
```

Các thành phần chính:

- **`FileChannel`**: kênh truy cập file với thao tác đọc, ghi và `map`. Mở từ `Path` với `FileChannel.open(...)`.
- **`MappedByteBuffer`**: một `ByteBuffer` dạng **direct buffer** đại diện vùng tệp đã map. Có `capacity()`, `position()`, `limit()`, `get()`, `put()`, `getInt()`, `putInt()` và thêm `load()`, `isLoaded()`, `force()`.
- **Virtual memory / page cache**: OS phụ trách ánh xạ địa chỉ ảo sang các trang nhớ và I/O khi cần. Mapping **không có nghĩa** dữ liệu file được đọc hết vào RAM ngay lúc tạo.
- **NVM (non-volatile memory, ví dụ persistent RAM được cấu hình phù hợp)**: một loại phần cứng lưu dữ liệu ngay cả khi tắt nguồn, có thể cho phép mapping đồng bộ tối ưu thông qua các map modes mở rộng. **Một ổ SSD thông thường không đồng nghĩa mapping NVM/DAX được hỗ trợ.**

**Phạm vi bài:** tập trung `FileChannel.map` tạo `MappedByteBuffer`. `MemorySegment` với `Arena` từ Java 22+ là lựa chọn hiện đại khác cho file mapping khi cần lifetime xác định; được so sánh ở mục 10 chứ không thay thế nội dung chính.

## 2. Chữ ký API và ý nghĩa ba tham số

```java
MappedByteBuffer map(FileChannel.MapMode mode,
                     long position,
                     long size) throws IOException
```

- **`mode`** là chế độ ánh xạ: `READ_ONLY`, `READ_WRITE`, `PRIVATE` hoặc một mode riêng được implementation hỗ trợ như `ExtendedMapMode.READ_WRITE_SYNC`.
- **`position`** là offset **theo byte trong tệp**, đếm từ byte 0, **không phải** `FileChannel.position()` hiện tại.
- **`size`** là **số byte cần map**, không phải offset cuối hoặc kích thước file tổng thể. `size` phải từ 0 đến `Integer.MAX_VALUE`; `position` phải không âm.
- Giá trị trả về là `MappedByteBuffer` có **`position() == 0`**, **`limit() == capacity() == size`**, mark chưa xác định.
- Mapping được tạo **không thay đổi current position của `FileChannel`**. Dùng `channel.position()` để kiểm tra vị trí kênh và `mapped.position()` để kiểm tra vị trí buffer, chúng là hai trạng thái khác nhau.

**Ví dụ ánh xạ vùng byte 16–31:**

```java
MappedByteBuffer mapped = channel.map(
    FileChannel.MapMode.READ_WRITE, 16L, 16L);

mapped.putInt(0, 123); // Ghi vào các byte 16,17,18,19 của FILE.
mapped.putInt(4, 456); // Ghi vào các byte 20,21,22,23 của FILE.
```

Đây là snippet trong phương thức có một `FileChannel channel` đã mở bằng **READ và WRITE**, tệp dài ít nhất 32 byte. `mapped.putInt(0,...)` dùng **index 0 tương đối so với vùng mapping**, không phải offset 0 trong file. `putInt(index,...)` là thao tác **absolute**, không đổi `mapped.position()`; còn `putInt(value)` là **relative** và tăng position của buffer.

**Điều kiện an toàn:** trước khi map, bảo đảm vùng `[position, position + size)` **đã nằm trong phạm vi file**. Theo JavaDoc, hành vi khi một phần vùng yêu cầu nằm ngoài file là **không được quy định nhất quán** giữa các OS. Đừng dựa vào việc một JVM đôi khi tự mở rộng file khi map để xây portable code.

## 3. Ba chế độ chuẩn `FileChannel.MapMode`

| Map mode | Mở `FileChannel` với quyền | Có thể ghi vào buffer? | Ghi có tác động file gốc? |
|---|---|---|---|
| `READ_ONLY` | `READ` | **Không**, ghi ném `ReadOnlyBufferException` | Không sửa file |
| `READ_WRITE` | **`READ` và `WRITE`** | **Có** | Có: thay đổi cuối cùng được truyền tới file, dùng `force` để yêu cầu ghi bền vững theo hợp đồng |
| `PRIVATE` | **`READ` và `WRITE`** | **Có** (copy-on-write) | **Không**: phần đã sửa là bản sao riêng, không ghi ngược vào file |

Chú ý `PRIVATE` **vẫn yêu cầu file channel được mở với cả quyền đọc và ghi** theo đặc tả `FileChannel.map`, mặc dù thay đổi trong private mapping không được đưa vào file. Nếu thiếu quyền, có thể gặp `NonWritableChannelException`.

### Khi dùng `READ_ONLY`

```java
try (FileChannel channel =
         FileChannel.open(path, java.nio.file.StandardOpenOption.READ)) {
    MappedByteBuffer view = channel.map(
        FileChannel.MapMode.READ_ONLY, 0, channel.size());
    byte first = view.get(0); // Chỉ hợp lệ khi file không rỗng.
    System.out.println(first);
}
```

Đây là snippet có `Path path` đã tồn tại và file không rỗng. Mọi `put` trên read-only view đều không hợp lệ. Mode này phù hợp index dữ liệu, tra cứu bảng/format nhị phân không muốn sửa.

### Khi dùng `READ_WRITE`

```java
MappedByteBuffer view = channel.map(
    FileChannel.MapMode.READ_WRITE, 0, 4096);

view.putInt(0, 42);
view.force(0, Integer.BYTES);
```

Đây là snippet chỉ hợp lệ khi file dài **ít nhất 4096 byte** và kênh có quyền đọc/ghi. `force(index,length)` là cách yêu cầu đồng bộ vùng vừa sửa lên storage. Đừng hiểu `putInt` tự bảo đảm dữ liệu đã bền vững trong trường hợp mất điện.

### Khi dùng `PRIVATE`

```java
MappedByteBuffer privateView = channel.map(
    FileChannel.MapMode.PRIVATE, 16, 8);
privateView.putInt(0, 777);
```

Nếu trước đó file có một số nguyên khác ở vị trí 16, `privateView.getInt(0)` thấy `777` nhưng byte tại vị trí 16 của **file gốc** không bị thay đổi bởi thao tác này. `PRIVATE` là cơ chế *copy-on-write*, **không phải một transaction** có thể commit sang file bằng `force()`. Muốn lưu dữ liệu mới, phải thực hiện quy trình ghi file riêng.

## 4. Mở file, bảo đảm kích thước và tạo buffer đúng cách

Một bước thực hành an toàn cho các ví dụ portable:

1. Tạo hoặc chọn một tệp **mà chương trình sở hữu**, trong thư mục có quyền hợp lệ.
2. Mở `FileChannel` với `StandardOpenOption.READ` và `WRITE` (thêm `CREATE` khi muốn tạo).
3. **Ghi dữ liệu/đệm đã định nghĩa** để file thật sự đủ dài; không nghĩ `channel.truncate(newLength)` sẽ làm file **tăng** độ dài — `truncate` chỉ có hiệu lực thu nhỏ khi độ dài hiện tại lớn hơn tham số.
4. Tính offset + length một cách có kiểm tra tràn số và bảo đảm cả vùng nằm trong file.
5. Gọi `map` với mode phù hợp. Sau đó đọc/ghi bằng index tương đối và đồng bộ nếu cần.
6. Đóng channel bằng `try-with-resources`, đồng thời quản lý **vòng đời mapping** theo mục 8.

Ví dụ khởi tạo tệp 64 byte:

```java
Path file = Files.createTempFile("mapped-", ".bin");
try (FileChannel channel = FileChannel.open(
        file, StandardOpenOption.READ, StandardOpenOption.WRITE)) {
    channel.write(ByteBuffer.wrap(new byte[64]));
    MappedByteBuffer mapped =
        channel.map(FileChannel.MapMode.READ_WRITE, 16, 16);
    mapped.putInt(0, 42);
    mapped.force();
}
```

Đây là snippet trong class/method đã import `Path`, `Files`, `FileChannel`, `ByteBuffer`, `MappedByteBuffer` và `StandardOpenOption`, **không phải một chương trình độc lập hoàn chỉnh**. Đừng map với `size=4096` khi tệp mới chỉ chứa 64 byte và trông chờ hành vi chung giữa các OS.

**Đọc/ghi dạng nhị phân:** `MappedByteBuffer` kế thừa `ByteBuffer.order(ByteOrder)`. Mặc định byte order là `BIG_ENDIAN`; nếu giao thức lưu dữ liệu bằng little-endian, phải gọi `order(ByteOrder.LITTLE_ENDIAN)` nhất quán ở cả ghi và đọc. Khi thao tác byte, `get(index)` trả giá trị `byte` có dấu; muốn biểu diễn số 0–255 dùng `Byte.toUnsignedInt(...)`.

## 5. Đồng bộ `force()` và ý nghĩa độ bền dữ liệu

`MappedByteBuffer` có hai dạng:

```java
mapped.force();                 // Yêu cầu ghi toàn bộ vùng mapping.
mapped.force(0, Integer.BYTES); // Yêu cầu ghi vùng 4 byte đầu buffer.
```

Trong `READ_WRITE`, `force()` yêu cầu đẩy thay đổi của mapping tới thiết bị lưu trữ. Theo Oracle JavaDoc, nếu file ở **thiết bị lưu trữ local**, khi phương thức trả về, các thay đổi của vùng được force từ buffer được bảo đảm đã được ghi xuống thiết bị theo hợp đồng API; với file trên **thiết bị không local**, không có cùng bảo đảm ấy. `force(index,length)` có thể khiến hệ thống flush thêm byte ngoài vùng yêu cầu do granularity thiết bị.

**So sánh hai API dễ nhầm:**

- `mapped.force()`: dùng để buộc **những thay đổi thực hiện thông qua mapped buffer** được ghi tới storage.
- `channel.force(true)`: được bảo đảm đối với những thay đổi thực hiện qua **các phương thức của `FileChannel`**; tài liệu nói rõ nó **có thể có hoặc không có tác dụng** với thay đổi thực hiện qua `MappedByteBuffer`.

Do đó **không thay `mapped.force()` bằng `channel.force(true)`** khi mục đích là đồng bộ dữ liệu bạn đã ghi bằng `mapped.put(...)`.

**Giới hạn độ bền và tính nhất quán:**

- `force()` không tự biến chuỗi nhiều lệnh `put` thành một giao dịch **atomic**. Một ứng dụng có thể bị dừng ở giữa thao tác cập nhật record, khiến chỉ một phần trường được ghi.
- `force()` không tự thực hiện WAL (write-ahead logging), checksum, versioning, replication, backup hoặc phục hồi lỗi dữ liệu.
- Nếu đòi hỏi crash-consistency, hãy thiết kế **format và protocol ghi** rõ: ghi payload trước, force, cập nhật metadata/commit marker có kiểm tra, force tiếp, kiểm tra version/checksum lúc khôi phục. Chi tiết thứ tự flush còn phụ thuộc storage và hợp đồng ứng dụng.
- Nếu dùng network filesystem, container overlay hoặc thiết bị đặc biệt, phải hiểu semantics của tầng storage. Đừng diễn giải dòng `force()` thành lời hứa tuyệt đối trên mọi hạ tầng.

**Mode khác:** `force()` có thể **không có tác dụng** với `READ_ONLY` hoặc `PRIVATE`. Với những implementation-specific modes, hành vi force được quy định bởi mode đó; xem `READ_WRITE_SYNC` ở mục 9.

## 6. Chương trình JDK 17+ độc lập: `MappedFileDemo.java`

Ví dụ này tạo một file có độ dài **64 byte**, map đúng **16 byte** bắt đầu ở offset 16, ghi hai số nguyên, force vùng 8 byte đầu, đọc lại từ file, kiểm chứng `PRIVATE`, `READ_ONLY` và vòng đời buffer sau khi đóng channel.

Tạo tệp **`MappedFileDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.MappedByteBuffer;
import java.nio.ReadOnlyBufferException;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class MappedFileDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("mapped-demo-", ".bin");
        file.toFile().deleteOnExit();

        MappedByteBuffer mapped;
        try (FileChannel channel = FileChannel.open(file,
                StandardOpenOption.READ, StandardOpenOption.WRITE)) {
            channel.write(ByteBuffer.wrap(new byte[64]));

            long beforePosition = channel.position();
            mapped = channel.map(FileChannel.MapMode.READ_WRITE, 16, 16);
            mapped.order(ByteOrder.BIG_ENDIAN);
            mapped.putInt(0, 0x12345678);
            mapped.putInt(4, 2026);
            mapped.force(0, 8);

            System.out.println("size=" + channel.size());
            System.out.println("mappingCapacity=" + mapped.capacity());
            System.out.println("mappingPosition=" + mapped.position());
            System.out.println("channelPositionUnchanged=" +
                (beforePosition == channel.position()));
            System.out.println("mappedFirst=" + mapped.getInt(0));

            ByteBuffer data = ByteBuffer.wrap(Files.readAllBytes(file))
                .order(ByteOrder.BIG_ENDIAN);
            System.out.println("fileFirst=" + data.getInt(16));
            System.out.println("fileSecond=" + data.getInt(20));

            MappedByteBuffer privateView =
                channel.map(FileChannel.MapMode.PRIVATE, 16, 8);
            privateView.order(ByteOrder.BIG_ENDIAN);
            privateView.putInt(0, 777);
            System.out.println("privateFirst=" + privateView.getInt(0));
            System.out.println("fileAfterPrivate=" +
                ByteBuffer.wrap(Files.readAllBytes(file))
                    .order(ByteOrder.BIG_ENDIAN).getInt(16));

            MappedByteBuffer readOnly =
                channel.map(FileChannel.MapMode.READ_ONLY, 16, 8);
            System.out.println("readOnly=" + readOnly.isReadOnly());
            try {
                readOnly.put(0, (byte) 1);
            } catch (ReadOnlyBufferException expected) {
                System.out.println("readOnlyWriteRejected=true");
            }
        }

        System.out.println("mappedAfterClose=" + mapped.getInt(0));
    }
}
```

Biên dịch và chạy từ thư mục chứa file bằng JDK 17+:

```bash
javac -encoding UTF-8 MappedFileDemo.java
java MappedFileDemo
```

**Stdout chính xác đã kiểm tra bằng OpenJDK 24 trên Windows:**

```text
size=64
mappingCapacity=16
mappingPosition=0
channelPositionUnchanged=true
mappedFirst=305419896
fileFirst=305419896
fileSecond=2026
privateFirst=777
fileAfterPrivate=305419896
readOnly=true
readOnlyWriteRejected=true
mappedAfterClose=305419896
```

### Phân tích từng kết quả

1. `size=64`: file được mở và ghi trước khi mapping; vùng map `[16,32)` **nằm hoàn toàn** trong file.
2. `mappingCapacity=16` và `mappingPosition=0`: buffer có view dài 16 byte, index bắt đầu ở 0 mặc dù offset file bắt đầu ở 16.
3. `channelPositionUnchanged=true`: `map` không đổi current position của `FileChannel`, trong khi `putInt(index,...)` absolute cũng không tăng position buffer.
4. `mappedFirst=305419896`: là giá trị decimal của số `0x12345678` được ghi vào vị trí relative 0. Câu lệnh tiếp theo ghi `2026` tại relative index 4.
5. `fileFirst=305419896` và `fileSecond=2026`: sau `force`, đọc bytes trong file tại **offset 16** và **offset 20** có cùng số nguyên.
6. `privateFirst=777` nhưng `fileAfterPrivate=305419896`: `PRIVATE` là copy-on-write, không thay đổi bytes gốc.
7. `readOnly=true` và `readOnlyWriteRejected=true`: ghi vào `READ_ONLY` ném `ReadOnlyBufferException` được bắt riêng trong demo.
8. `mappedAfterClose=305419896`: sau khi `FileChannel.close()`, buffer mapping vẫn có thể truy cập vì mapping **độc lập với channel đã tạo ra nó**.

**Lưu ý về tệp tạm:** demo gọi `file.toFile().deleteOnExit()` để yêu cầu dọn khi JVM kết thúc. Điều này **không phải cam kết xóa tức thời hoặc cleanup được quản lý rõ vòng đời của mapping**, nhất là khi process kết thúc bất thường. Với ứng dụng thật, xây chiến lược quản lý file/mapping riêng; không để tệp chứa dữ liệu nhạy cảm trong thư mục tạm không được bảo vệ.

## 7. Ánh xạ vùng, con trỏ buffer, dữ liệu lớn và hiệu năng

### 7.1. Offset tính theo file, index tính theo buffer

```text
File:   [bytes 0..15][bytes 16..31][bytes 32..63]
                      [ MAPPED 16 BYTES ]
Buffer:                0 .. 15
                            ^
mapped.get(0)  -> File byte 16
mapped.get(5)  -> File byte 21
mapped.get(15) -> File byte 31
```

Đừng cộng offset file vào `mapped.get(index)` một lần nữa. Nếu map từ file offset 16 rồi gọi `mapped.get(16)`, với capacity 16 sẽ vượt giới hạn của view (index 16 đã ở **ngoài** phạm vi `[0,16)`).

`ByteBuffer.get()/put()` có hai biến thể:

- **Relative:** `buffer.get()`, `buffer.put(byte)`, `putInt(int)` dùng current position và tăng position tương ứng.
- **Absolute:** `buffer.get(index)`, `put(index, byte)`, `getInt(index)`, `putInt(index, value)` không làm thay đổi position.

Có thể dùng `slice()` hoặc `slice(index,length)` để tạo view trên một phần của mapping; nội dung chia sẻ cùng storage nhưng position/limit/mark độc lập. Nếu dùng nhiều thread, đừng chia sẻ tùy tiện position trạng thái của một buffer.

### 7.2. Giới hạn `Integer.MAX_VALUE`

`FileChannel.map(MapMode,long,long)` trả `MappedByteBuffer` và yêu cầu `size <= Integer.MAX_VALUE`. Dù file lớn hơn 2 GiB, **một mapped buffer đơn lẻ** từ overload này vẫn bị giới hạn bởi kiểu `int` của capacity/index.

Để thao tác file lớn với JDK 17+, có thể **chia thành nhiều vùng map** nhỏ, sử dụng offset `long` và cẩn thận ở biên trang/chunk. Ví dụ mỗi chunk nhỏ hơn 1 GiB hoặc theo định dạng dữ liệu. Không giả định có thể map cả một file hàng chục GiB vào một `MappedByteBuffer`.

Từ **Java 22+**, overload `FileChannel.map(mode,offset,size,Arena)` trả `MemorySegment` với `long` size và lifetime do Arena quản lý; nó là lựa chọn thay thế chính thức cho những bài toán cần mapping lớn hoặc unmap có thời điểm xác định. Xem mục 10.

### 7.3. `load()` và `isLoaded()` không phải các bảo đảm hiệu năng

- `mapped.load()` cố gắng nạp pages của vùng ánh xạ vào bộ nhớ vật lý; **best effort**, có thể phát sinh page faults và I/O.
- `mapped.isLoaded()` trả dấu hiệu “có khả năng dữ liệu resident trong RAM”. `true` không đảm bảo pages luôn ở RAM về sau; `false` cũng không chứng minh toàn bộ dữ liệu không resident.
- Mapping không luôn nhanh hơn `FileChannel.read()/write()`, nhất là với file nhỏ vì tạo mapping có chi phí riêng. Cần benchmark cùng workload, access pattern, page cache state, kích thước file và hardware.

**Đừng gọi `load()` với giả định nó “pin” pages vĩnh viễn trong RAM**. Nếu ứng dụng đòi page residency hoặc low-latency nghiêm ngặt, cần công cụ OS/cấu hình bổ sung cùng phép đo thực tế.

## 8. Vòng đời, thread safety và rủi ro từ thay đổi file

### 8.1. Đóng `FileChannel` không hủy mapping

Theo JavaDoc:

- `MappedByteBuffer` và mapping của nó vẫn tồn tại cho đến khi buffer được GC giải phóng; **không có `MappedByteBuffer.close()` công khai**.
- `FileChannel.close()` đóng kênh nhưng **không làm mapping mất hiệu lực**.
- Không dựa vào một phương thức nội bộ không công khai hoặc hack `sun.misc.Unsafe` để “unmap ngay”; đó không phải cách quản lý tài nguyên portable, an toàn và hiện đại.

**Hệ quả:** trên một số OS, file vẫn được giữ map và có thể khó xóa/đổi tên dù channel đã đóng. Với hệ thống cần dọn file, xoay vòng log hoặc tái dùng file ngay lập tức, hãy thiết kế lifecycle và cân nhắc API `MemorySegment` với `Arena` (Java 22+) ở mục 10.

### 8.2. Không truncate / rewrite file đang được map

Nếu một process (hoặc process khác) rút ngắn hoặc thay đổi file đã map, một phần vùng ánh xạ có thể **không còn truy cập được**. JavaDoc cảnh báo thao tác đọc/ghi trên vùng ấy có thể tạo exception hoặc hành vi phụ thuộc OS/JVM, nên **không cho phép thao tác file tùy tiện trong lúc mapping còn sống**.

Thực hành an toàn:

1. Cố định kích thước file hoặc có protocol thay đổi kích thước rõ ràng.
2. Không để producer truncate hoặc replace file khi consumer vẫn đang đọc từ mapping cũ.
3. Nếu nhiều process cùng truy cập, định nghĩa locking, versioning và sequence/consistency protocol riêng.
4. Không dùng `force` để “chữa” mapping đã không hợp lệ do file bị sửa kích thước.

### 8.3. Nhiều thread và nhiều process

Ánh xạ nội dung file **không tự biến mọi thao tác Java thành atomic hoặc thread-safe**. Những phương thức `position()`/`limit()` thay đổi trạng thái buffer; write nhiều byte hay update nhiều field không được `MappedByteBuffer` bảo đảm như một transaction.

Có thể tạo `duplicate()` hoặc `slice()` cho mỗi thread để có position/limit riêng, nhưng các view vẫn chia sẻ **nội dung**. Nếu chúng cùng ghi, cần đồng bộ phù hợp; khi khác process, phải thiết kế cơ chế IPC hoặc file locking đúng mục đích. `FileLock` có thể phối hợp giữa process trên OS hỗ trợ, nhưng không tự tạo protocol commit hay bảo đảm file mapped nhất quán nếu process khác không tuân thủ.

## 9. Chế độ NVM đồng bộ của Java 14+: `ExtendedMapMode`

Java 14 bổ sung **JEP 352 — Non-Volatile Mapped Byte Buffers**. Trong module **`jdk.nio.mapmode`** có class:

```java
import jdk.nio.mapmode.ExtendedMapMode;
```

Các mode còn tồn tại trong **Oracle Java SE 25/26**:

| Mode mở rộng | Mục tiêu | Đặc điểm |
|---|---|---|
| `ExtendedMapMode.READ_ONLY_SYNC` | Read-only mapping được backing bởi NVM | Không cho ghi; cần OS/storage hỗ trợ sync mapping |
| `ExtendedMapMode.READ_WRITE_SYNC` | Read/write mapping được backing bởi NVM | `MappedByteBuffer.force()` có thể dùng **cache-line writeback** thay vì file-device flush trên nền tảng hỗ trợ |

Trên Linux, tài liệu implementation note nhắc tới các flag `MAP_SYNC` và `MAP_SHARED_VALIDATE` của `mmap`. Điều này liên quan đến file và filesystem hỗ trợ **direct access (DAX)/persistent memory**, chứ không đơn giản là “đang chạy Linux thì mọi file đều hỗ trợ”. Khi runtime không hỗ trợ mode, `FileChannel.map` có thể ném **`UnsupportedOperationException`**; các lỗi I/O hoặc storage cũng cần được xử lý.

**Không dùng `READ_WRITE_SYNC` một cách vô điều kiện trên HDD/SSD/NVMe hoặc mọi thư mục temp.** Đây là một *NVM-specialized mode*, không phải một cách tăng tốc mọi file mapping. Bản thân `FileChannel.MapMode.READ_WRITE` đã là đường sử dụng portable phù hợp cho phần lớn ứng dụng cần mmap file thông thường.

### 9.1. Ví dụ kiểm tra mode đồng bộ — có nhánh unsupported

Tạo tệp **`NvmSyncProbe.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import jdk.nio.mapmode.ExtendedMapMode;

public class NvmSyncProbe {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("nvm-sync-check-", ".bin");
        file.toFile().deleteOnExit();
        try (FileChannel channel = FileChannel.open(file,
                StandardOpenOption.READ, StandardOpenOption.WRITE)) {
            channel.write(ByteBuffer.wrap(new byte[4096]));
            try {
                var mapped = channel.map(
                    ExtendedMapMode.READ_WRITE_SYNC, 0, 4096);
                mapped.put(0, (byte) 7);
                mapped.force(0, 1);
                System.out.println("syncMappingAvailable=true");
            } catch (UnsupportedOperationException | java.io.IOException ex) {
                System.out.println("syncMappingAvailable=false");
                System.out.println("reasonType=" +
                    ex.getClass().getSimpleName());
            }
        }
    }
}
```

Module `jdk.nio.mapmode` là JDK-specific; biên dịch và chạy rõ ràng với module:

```bash
javac --add-modules jdk.nio.mapmode -encoding UTF-8 NvmSyncProbe.java
java --add-modules jdk.nio.mapmode NvmSyncProbe
```

**Kết quả đã kiểm tra trên OpenJDK 24 Windows với file tạm thông thường:**

```text
syncMappingAvailable=false
reasonType=UnsupportedOperationException
```

Trên một hệ thống Linux được cấu hình **NVM/DAX hỗ trợ** và JDK có hỗ trợ mode, chương trình có thể chạy vào nhánh `syncMappingAvailable=true`, nhưng **không có cam kết** vì file test mặc định được tạo ở thư mục temp có thể không nằm trên NVM. Để kiểm tra môi trường NVM thực, đặt file trong một **volume NVM/DAX đã được quản trị viên cấu hình**, hiểu rõ quyền và mount options; không giả định `Files.createTempFile(...)` tự dùng vùng đó.

**Không tự động catch exception rồi âm thầm fallback sang `READ_WRITE`** nếu yêu cầu nghiệp vụ phụ thuộc semantics durability của sync mode. Hãy quyết định rõ: báo thiếu khả năng NVM, chuyển sang storage khác hoặc thực hiện fallback theo một hợp đồng độ bền đã được kiểm chứng. Vì vậy mã probe chỉ **in trạng thái**, không cố thay đổi mode mà không thông báo.

## 10. Lựa chọn hiện đại khác từ Java 22+: `MemorySegment` và `Arena`

`FileChannel.map(MapMode,long,long)` tạo `MappedByteBuffer` vẫn được hỗ trợ và **không bị deprecate vì có API mới**. Nhưng từ Java **22**, Foreign Function & Memory API (JEP 454) trở thành chính thức, cung cấp overload mới:

```java
MemorySegment FileChannel.map(
    FileChannel.MapMode mode, long offset, long size, Arena arena)
```

Một `Arena` có thể đóng sẽ kiểm soát **lifetime của file mapping**. Khi `Arena.ofConfined()` bị đóng, mapped `MemorySegment` tương ứng không còn hợp lệ và vùng nhớ có thể được unmap có kiểm soát. `MemorySegment.byteSize()` dùng `long`, nên phù hợp với vùng lớn hơn giới hạn `int` của `MappedByteBuffer`.

Chương trình Java 22+ độc lập, cũng đã kiểm tra trên OpenJDK 24:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.ValueLayout;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class MappedSegmentDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("segment-demo-", ".bin");
        path.toFile().deleteOnExit();
        try (FileChannel channel = FileChannel.open(
                     path, StandardOpenOption.READ, StandardOpenOption.WRITE);
             Arena arena = Arena.ofConfined()) {
            channel.write(ByteBuffer.wrap(new byte[16]));
            var segment = channel.map(
                FileChannel.MapMode.READ_WRITE, 0, 16, arena);
            segment.set(ValueLayout.JAVA_INT, 0, 42);
            segment.force();
            System.out.println("mapped=" + segment.isMapped());
            System.out.println("value=" + segment.get(ValueLayout.JAVA_INT, 0));
            System.out.println("size=" + segment.byteSize());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MappedSegmentDemo.java
java MappedSegmentDemo
```

**Stdout đã xác minh:**

```text
mapped=true
value=42
size=16
```

**Nên dùng cái nào?**

- **JDK 17/21 hoặc API hiện có trả `ByteBuffer`:** `FileChannel.map(MapMode,long,long)` → `MappedByteBuffer` vẫn là cách phù hợp, ổn định và portable.
- **JDK 22+ và cần unmap rõ thời điểm / vùng mapping lớn:** cân nhắc `FileChannel.map(..., Arena)` → `MemorySegment`.
- **NVM chuyên biệt:** `ExtendedMapMode` vẫn là một lựa chọn riêng có điều kiện; chọn nó khi phần cứng, filesystem, JDK thực sự hỗ trợ. Dùng API Java hiện đại không tự chuyển một file thường thành persistent-memory device.

Không viết code tự gọi `Cleaner`, `Unsafe.invokeCleaner`, `finalize` hoặc chạm trực tiếp native address để giả lập unmap; những cách này không phải thay thế được bảo đảm cho quản lý vòng đời từ `Arena` trên JDK hiện đại.

## 11. Các lỗi thường gặp khi tạo và dùng `MappedByteBuffer`

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
|---|---|---|
| `NonReadableChannelException` | Channel không có quyền `READ` nhưng mode cần đọc | Mở `FileChannel` với quyền phù hợp |
| `NonWritableChannelException` | `READ_WRITE` hoặc `PRIVATE` nhưng thiếu `WRITE` | Mở kênh với **READ + WRITE** |
| `ReadOnlyBufferException` | Ghi vào `READ_ONLY` mapping | Dùng mode phù hợp và xem xét quyền ghi |
| `IllegalArgumentException` ở `map` | `position < 0`, `size < 0` hoặc `size > Integer.MAX_VALUE` | Kiểm tra offset/size trước gọi |
| `IndexOutOfBoundsException` | Dùng offset file trực tiếp làm index trong buffer | Tính index tương đối từ đầu vùng mapped |
| Map vượt EOF rồi behavior bất ngờ | Vùng mapping chưa nằm trong kích thước file | Khởi tạo/ghi đủ kích thước trước khi map |
| Dữ liệu sai endian | `ByteBuffer` mặc định big-endian, format yêu cầu little-endian | Thiết lập `order(ByteOrder.LITTLE_ENDIAN)` rõ ràng |
| Ghi xong nhưng không có bảo đảm lưu bền | Chỉ gọi `put` mà không `mapped.force` | Force đúng buffer/region, kiểm tra storage semantics |
| `channel.force(true)` không đảm bảo flush mapping | Channel force không hứa flush các thay đổi qua mapped buffer | Gọi `mapped.force()` |
| `PRIVATE` không lưu các `put` vào file | Là copy-on-write, không phải mode writeback | Dùng `READ_WRITE` hoặc ghi tệp tường minh |
| `UnsupportedOperationException` với `READ_WRITE_SYNC` | Runtime/OS/file không hỗ trợ mapping NVM sync | Kiểm tra NVM/DAX và chọn chính sách lỗi/fallback rõ ràng |
| `isLoaded() == false` tưởng không thể dùng buffer | Nó chỉ là hint về residency, không phải trạng thái hợp lệ | Vẫn có thể đọc nếu mapping hợp lệ |
| Không xóa/rename được file trên một OS | Mapping còn sống dù FileChannel đã đóng | Thiết kế lifecycle hoặc dùng `MemorySegment` + `Arena` ở Java 22+ |
| Lỗi khi file bị truncate trong lúc đang map | Vùng virtual memory trở nên không truy cập được | Không thay đổi size/file trái protocol |
| Map file >2 GiB vào một buffer | `MappedByteBuffer` có capacity kiểu `int` | Chia mapping thành chunks hoặc dùng `MemorySegment` từ Java 22+ |
| Race condition / dữ liệu không nhất quán | Chia sẻ buffer, thiếu locking/versioning | Thiết kế ownership, đồng bộ và protocol crash-consistency |

## 12. Checklist cho ứng dụng ánh xạ NVM và mmap production

1. Kiểm tra JDK, OS, filesystem, storage; xác định **file thường hay NVM thực sự**, không suy đoán từ tên ổ.
2. Chọn `FileChannel.MapMode` theo quyền đọc/ghi và semantics dữ liệu; nếu dùng NVM sync, kiểm tra module và hỗ trợ triển khai.
3. Bảo đảm vùng `[position,position+size)` nằm trong file, tránh overflow `long` khi tính toán.
4. Nếu dùng `MappedByteBuffer`, map từng vùng kích thước `<= Integer.MAX_VALUE` và tính index tương đối.
5. Dùng `ByteOrder` đúng với format nhị phân, kiểm thử byte-level readback.
6. Với `READ_WRITE`, gọi `mapped.force()` tại các điểm cần độ bền; không thay bằng `channel.force(true)` cho mapped changes.
7. Phân biệt **persisted bytes** với **transaction atomicity**; xây giao thức commit/version/checksum khi cần crash recovery.
8. Không để file bị truncate/replace trong lúc có mapping sống; quản lý locking/permissions và sự hợp tác giữa nhiều process.
9. Không giả định `FileChannel.close()` giải phóng mapping; chọn `MemorySegment` + `Arena` trên Java 22+ nếu cần lifecycle rõ ràng.
10. Kiểm chứng performance bằng workload thực (page faults, memory pressure, cache state, kích thước file, latency) trước khi tối ưu.
11. Với NVM sync, coi `UnsupportedOperationException` và `IOException` là nhánh xử lý bình thường khi thiếu hỗ trợ; không fallback âm thầm.
12. Bảo vệ file chứa dữ liệu nhạy cảm: permissions, mã hóa theo yêu cầu, đường dẫn đáng tin, dọn file và tránh ghi lộ dữ liệu trong log.
13. Chỉ tuyên bố “NVM sync đã hoạt động” sau khi **thử thành công trên chính volume NVM** và xác minh yêu cầu durability; demo RAM/file thường không thay thế bài test hạ tầng.

## Tài liệu chính thức

- Oracle Java SE 26 API, `FileChannel.map(MapMode,long,long)`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/FileChannel.html
- Oracle Java SE 26 API, `MappedByteBuffer` (`force`, `load`, `isLoaded`, lifetime): https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/MappedByteBuffer.html
- Oracle Java SE 25 API, `FileChannel.MapMode`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/FileChannel.MapMode.html
- Oracle Java SE 26 API, `jdk.nio.mapmode.ExtendedMapMode` (`READ_ONLY_SYNC`/`READ_WRITE_SYNC`): https://docs.oracle.com/en/java/javase/26/docs/api/jdk.nio.mapmode/jdk/nio/mapmode/ExtendedMapMode.html
- OpenJDK JEP 352 — *Non-Volatile Mapped Byte Buffers* (Java 14): https://openjdk.org/jeps/352
- OpenJDK JEP 454 — *Foreign Function & Memory API* (tính năng chính thức Java 22): https://openjdk.org/jeps/454
- Oracle Java SE 25 API, `java.lang.foreign.Arena` và `MemorySegment`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/package-summary.html
