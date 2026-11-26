# Ánh xạ tệp vào bộ nhớ với FileChannel và Arena

## Mục tiêu

Khi cần xử lý một tệp lớn, chương trình có thể đọc dữ liệu theo từng khối bằng `FileChannel`, hoặc ánh xạ một vùng của tệp vào bộ nhớ rồi truy cập vùng đó như một `MemorySegment`. Cách thứ hai được gọi là *memory-mapped file*.

Từ JDK 22, `FileChannel` có overload `map` nhận thêm `Arena` và trả về `MemorySegment`. Đây là cách tích hợp ánh xạ tệp với Foreign Function & Memory API (FFM) đã trở thành chính thức trong Java 22 qua JEP 454. API này vẫn có trong các JDK hiện đại; ví dụ trong bài dùng cú pháp ổn định từ JDK 22 trở lên, không cần bật preview.

Khi kết hợp `FileChannel`, `MemorySegment` và `Arena`, ta có thể:

- Ánh xạ một vùng tệp thành một vùng nhớ native để đọc hoặc ghi.
- Truy cập dữ liệu theo offset và kiểu dữ liệu bằng `ValueLayout`.
- Làm việc với kích thước vùng ánh xạ biểu diễn bằng `long`.
- Quy định rõ thời điểm vùng ánh xạ được giải phóng bằng vòng đời của `Arena`.

## Memory mapping là gì?

Memory mapping cho phép hệ điều hành ánh xạ một vùng của tệp vào không gian địa chỉ của tiến trình. Chương trình đọc và ghi vùng đó thông qua bộ nhớ; hệ điều hành quản lý việc nạp các trang dữ liệu và đồng bộ chúng với tệp theo cơ chế của nền tảng.

```text
Tệp trên thiết bị lưu trữ
        |
        | FileChannel.map(mode, offset, size, arena)
        v
Vùng nhớ được ánh xạ (mapped region)
        |
        v
MemorySegment
        |
        | get / set / getAtIndex / setAtIndex
        v
Giá trị được đọc hoặc ghi theo ValueLayout
        |
        | MemorySegment.force() khi cần yêu cầu ghi bền vững
        v
Tệp trên thiết bị lưu trữ
```

`MemorySegment` không phải một bản sao Java heap của toàn bộ tệp. Nó đại diện cho một vùng nhớ liên tục gắn với nội dung của vùng tệp đã ánh xạ. Vì vậy, chương trình có thể truy cập dữ liệu theo offset mà không cần tự đọc toàn bộ vùng dữ liệu vào một `byte[]`.

Memory mapping thường hữu ích với tệp lớn hoặc dữ liệu có cấu trúc được truy cập lặp lại. Việc ánh xạ có chi phí thiết lập và phụ thuộc hệ điều hành; với dữ liệu nhỏ, đọc/ghi thông thường qua `Files` hoặc `FileChannel` có thể đơn giản và hiệu quả hơn.

## API hiện hành trong Java

Các kiểu chính nằm trong hai package:

| Kiểu | Package | Vai trò |
|---|---|---|
| `FileChannel` | `java.nio.channels` | Mở tệp và tạo ánh xạ cho một vùng của tệp. |
| `FileChannel.MapMode` | `java.nio.channels` | Chọn chế độ ánh xạ: chỉ đọc, đọc/ghi hoặc copy-on-write. |
| `MemorySegment` | `java.lang.foreign` | Đại diện cho vùng nhớ được ánh xạ và cung cấp các thao tác truy cập có kiểm tra biên. |
| `Arena` | `java.lang.foreign` | Quản lý vòng đời và quy tắc truy cập theo thread của segment. |
| `ValueLayout` | `java.lang.foreign` | Mô tả kiểu, kích thước, alignment và byte order của giá trị được đọc/ghi. |
| `MemoryLayout` | `java.lang.foreign` | Mô tả cấu trúc dữ liệu phức hợp như struct hoặc sequence. |

Phương thức cần nhớ:

```java
MemorySegment FileChannel.map(
        FileChannel.MapMode mode,
        long offset,
        long size,
        Arena arena) throws IOException;
```

- `mode`: cách ánh xạ tệp.
- `offset`: vị trí bắt đầu trong tệp, tính bằng byte.
- `size`: số byte cần ánh xạ.
- `arena`: quản lý vòng đời của `MemorySegment` được trả về.

Overload này có từ JDK 22. `offset` và `size` là `long`; vì vậy API không áp dụng giới hạn `Integer.MAX_VALUE` của một `ByteBuffer`. Kích thước thực tế vẫn phụ thuộc hệ điều hành, hệ thống tệp và tài nguyên của máy.

## Chọn chế độ ánh xạ

`FileChannel.MapMode` xác định chương trình có thể làm gì với vùng dữ liệu:

| Chế độ | Quyền truy cập | Ảnh hưởng tới tệp |
|---|---|---|
| `READ_ONLY` | Chỉ đọc. Segment trả về là read-only; thao tác ghi sẽ thất bại. | Không ghi thay đổi qua ánh xạ này. |
| `READ_WRITE` | Đọc và ghi. | Thay đổi được truyền tới tệp theo cơ chế của hệ điều hành; gọi `MemorySegment.force()` để yêu cầu đẩy thay đổi xuống thiết bị lưu trữ. |
| `PRIVATE` | Đọc và ghi trên vùng ánh xạ riêng. | Thay đổi hoạt động theo copy-on-write và không được ghi trở lại tệp gốc. |

Quyền mở `FileChannel` phải tương thích với chế độ ánh xạ:

- `READ_ONLY` yêu cầu channel được mở với `StandardOpenOption.READ`.
- `READ_WRITE` và `PRIVATE` yêu cầu channel được mở với cả `READ` và `WRITE`.

Ví dụ mở channel chỉ đọc:

```java
FileChannel channel = FileChannel.open(path, StandardOpenOption.READ);
```

Ví dụ mở channel để đọc và ghi:

```java
FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.READ,
        StandardOpenOption.WRITE);
```

## Arena quản lý vòng đời của vùng ánh xạ

`Arena` xác định khi nào segment còn hợp lệ và thread nào có thể truy cập segment đó. Khi đóng một arena có thể đóng tường minh, tất cả segment gắn với arena bị vô hiệu hóa và vùng nhớ native tương ứng được giải phóng. Do `FileChannel.map(..., arena)` gắn vòng đời của mapped segment với arena, hãy giữ arena mở trong toàn bộ thời gian cần sử dụng segment.

Các loại arena thường gặp:

| Loại | Tạo bằng | Vòng đời và phạm vi thread |
|---|---|---|
| Confined | `Arena.ofConfined()` | Có thể đóng tường minh; chỉ thread tạo arena được truy cập và đóng. |
| Shared | `Arena.ofShared()` | Có thể đóng tường minh; nhiều thread có thể truy cập segment. |
| Automatic | `Arena.ofAuto()` | Thu hồi tự động khi arena và các segment liên quan không còn reachable; không chủ động đóng. |
| Global | `Arena.global()` | Không có thời điểm đóng; segment tồn tại trong suốt vòng đời tiến trình. |

Với một thao tác ánh xạ chỉ diễn ra trong một thread, `Arena.ofConfined()` kết hợp `try-with-resources` thường là lựa chọn rõ ràng nhất:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment mapped = channel.map(
            FileChannel.MapMode.READ_ONLY,
            0L,
            channel.size(),
            arena);

    // Chỉ truy cập mapped trong phạm vi arena còn mở.
}
// mapped không còn được truy cập sau khi arena đóng.
```

Nếu segment cần được truy cập từ nhiều thread, dùng `Arena.ofShared()` và thiết kế đồng bộ dữ liệu phù hợp. Shared arena cho phép nhiều thread truy cập; điều đó không tự làm cho các thao tác đọc/ghi cùng một vị trí trở nên an toàn hoặc nguyên tử.

Tránh dùng `Arena.global()` cho một ánh xạ chỉ cần sống trong thời gian ngắn: arena toàn cục không đóng được nên không có thời điểm giải phóng tường minh. `Arena.ofAuto()` cũng không phù hợp khi ứng dụng cần kiểm soát chính xác thời điểm unmap.

## Truy cập dữ liệu bằng MemorySegment và ValueLayout

Một segment có kích thước tính bằng byte. Các thao tác `get` và `set` nhận `ValueLayout` cùng offset tính bằng byte:

```java
int value = segment.get(ValueLayout.JAVA_INT, 0L);
segment.set(ValueLayout.JAVA_INT, 0L, 42);
```

Nếu dữ liệu là một dãy phần tử cùng kiểu, có thể dùng `getAtIndex` và `setAtIndex`. Tham số index là chỉ số logic; API tự nhân chỉ số với kích thước của layout:

```java
segment.setAtIndex(ValueLayout.JAVA_INT, 2L, 99);
int value = segment.getAtIndex(ValueLayout.JAVA_INT, 2L);
```

`ValueLayout.JAVA_INT` dùng byte order native của máy chạy chương trình. Khi định dạng tệp cần có byte order thống nhất giữa nhiều nền tảng, hãy chỉ định rõ:

```java
ValueLayout.OfInt INT_BIG_ENDIAN =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);
```

Khi đó cả thao tác đọc và ghi đều phải dùng layout `INT_BIG_ENDIAN` để diễn giải byte giống nhau trên các máy có byte order khác nhau.

Các access operation kiểm tra phạm vi của segment, vòng đời arena, quy tắc thread và alignment của layout. Truy cập vượt quá `byteSize()` có thể ném `IndexOutOfBoundsException`; truy cập sau khi arena đóng sẽ ném `IllegalStateException`; truy cập segment confined từ thread khác có thể ném `WrongThreadException`.

## Ví dụ hoàn chỉnh: ghi và đọc một dãy số nguyên

Ví dụ tạo file `numbers.bin`, ánh xạ file để ghi bốn số nguyên, yêu cầu ghi thay đổi xuống thiết bị lưu trữ rồi mở lại file ở chế độ chỉ đọc.

```java
import java.io.IOException;
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FileMappingExample {
    private static final ValueLayout.OfInt INT_BE =
            ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);

    private static final int[] VALUES = {10, 20, 30, 40};

    public static void main(String[] args) throws IOException {
        Path path = Path.of("numbers.bin");

        writeNumbers(path);
        readNumbers(path);
    }

    private static void writeNumbers(Path path) throws IOException {
        long byteSize = (long) VALUES.length * INT_BE.byteSize();

        try (FileChannel channel = FileChannel.open(
                     path,
                     StandardOpenOption.CREATE,
                     StandardOpenOption.TRUNCATE_EXISTING,
                     StandardOpenOption.READ,
                     StandardOpenOption.WRITE);
             Arena arena = Arena.ofConfined()) {

            // Đảm bảo file có đủ byte trước khi ánh xạ vùng dữ liệu.
            channel.position(byteSize - 1);
            ByteBuffer lastByte = ByteBuffer.wrap(new byte[] {0});
            while (lastByte.hasRemaining()) {
                channel.write(lastByte);
            }

            MemorySegment mapped = channel.map(
                    FileChannel.MapMode.READ_WRITE,
                    0L,
                    byteSize,
                    arena);

            for (int i = 0; i < VALUES.length; i++) {
                mapped.setAtIndex(INT_BE, i, VALUES[i]);
            }

            // Yêu cầu ghi các thay đổi của mapped segment xuống thiết bị lưu trữ.
            mapped.force();
        }
    }

    private static void readNumbers(Path path) throws IOException {
        try (FileChannel channel = FileChannel.open(
                     path,
                     StandardOpenOption.READ);
             Arena arena = Arena.ofConfined()) {

            long byteSize = channel.size();
            if (byteSize % INT_BE.byteSize() != 0) {
                throw new IOException("Kích thước file không phải bội số của 4 byte");
            }

            MemorySegment mapped = channel.map(
                    FileChannel.MapMode.READ_ONLY,
                    0L,
                    byteSize,
                    arena);

            long count = mapped.byteSize() / INT_BE.byteSize();
            for (long i = 0; i < count; i++) {
                System.out.println(mapped.getAtIndex(INT_BE, i));
            }
        }
    }
}
```

Chạy với JDK 22 trở lên:

```shell
javac FileMappingExample.java
java FileMappingExample
```

Kết quả:

```text
10
20
30
40
```

Các điểm cần quan sát trong ví dụ:

1. `FileChannel.open` mở file với quyền đọc và ghi vì chế độ `READ_WRITE` cần cả hai quyền.
2. Đoạn ghi byte cuối mở rộng file đến đúng kích thước cần thiết. Không nên giả định dữ liệu của một vùng ánh xạ trên file mới được khởi tạo theo một giá trị cụ thể.
3. `map` nhận offset `0L`, kích thước byte và arena; vị trí hiện tại của channel không quyết định offset ánh xạ.
4. `setAtIndex` ghi số nguyên theo layout Big Endian đã chọn.
5. `force()` yêu cầu đẩy các thay đổi của mapped segment xuống thiết bị lưu trữ. Arena đóng sau khi thao tác ghi kết thúc.
6. Khi đọc lại, channel chỉ cần quyền `READ`; mapped segment được tạo ở chế độ `READ_ONLY`.

## Ánh xạ một phần tệp và chia segment

Không bắt buộc phải ánh xạ toàn bộ tệp. Hai tham số `offset` và `size` xác định vùng cần làm việc:

```java
long offset = 4096L;
long length = 8192L;

MemorySegment region = channel.map(
        FileChannel.MapMode.READ_ONLY,
        offset,
        length,
        arena);
```

`region` đại diện cho các byte từ vị trí `offset` đến hết vùng có kích thước `length`. Offset và kích thước đều tính bằng byte. Cần bảo đảm vùng được yêu cầu hợp lệ với tệp và hệ điều hành; kiểm tra `channel.size()` trước khi ánh xạ là cách tốt để phát hiện vùng vượt quá kích thước hiện tại của tệp.

Có thể tạo một segment con bằng `asSlice` để giới hạn phạm vi mà một phần code được phép truy cập:

```java
MemorySegment header = region.asSlice(0L, 64L);
MemorySegment payload = region.asSlice(64L);
```

Các segment con dùng chung vùng nhớ và vòng đời với segment gốc, nhưng có giới hạn không gian nhỏ hơn. Vì vậy, một thao tác vượt khỏi phạm vi `payload` vẫn bị kiểm tra ngay cả khi vùng nhớ gốc lớn hơn.

## Đồng bộ thay đổi và tính bền vững

Mapped segment `READ_WRITE` cho phép ghi trực tiếp vào vùng nhớ được ánh xạ. Việc thay đổi được truyền về file theo cơ chế của hệ điều hành; thời điểm các thay đổi được nhìn thấy ở tiến trình khác phụ thuộc nền tảng và hệ thống tệp.

`MemorySegment.force()` yêu cầu ghi các thay đổi của mapped segment xuống thiết bị lưu trữ. Với file descriptor nằm trên thiết bị lưu trữ cục bộ, khi phương thức trả về, các thay đổi kể từ lúc tạo segment hoặc lần gọi `force()` gần nhất được bảo đảm đã ghi xuống thiết bị. Với thiết bị không cục bộ, không có bảo đảm tương tự. `force()` không có tác dụng với ánh xạ `READ_ONLY` hoặc `PRIVATE`.

Không nên hiểu `force()` là một giao dịch cơ sở dữ liệu hoặc cơ chế đồng bộ giữa nhiều writer. Nếu nhiều thread hoặc nhiều tiến trình cùng đọc/ghi một file, ứng dụng vẫn cần giao thức phối hợp, phân vùng vùng ghi và cơ chế khóa phù hợp. `FileLock` có thể hỗ trợ phối hợp giữa các tiến trình trong một số tình huống, nhưng không thay thế đồng bộ thread trong cùng JVM.

## Các giới hạn và lưu ý khi vận hành

- **Không thay đổi kích thước file khi đang dùng mapping.** Nếu file backing bị truncate, một phần hoặc toàn bộ mapped segment có thể trở nên không truy cập được; hành vi và exception cụ thể phụ thuộc hệ điều hành.
- **Giữ arena mở đúng thời gian cần thiết.** Đóng arena làm segment mất hiệu lực; không trả segment ra ngoài phạm vi sở hữu của arena nếu bên nhận có thể truy cập sau khi arena đóng.
- **Chọn đúng loại arena.** Confined phù hợp với truy cập trong một thread; shared dùng khi nhiều thread thực sự cần truy cập segment. Shared không tự cung cấp đồng bộ cho dữ liệu.
- **Mở channel đúng quyền.** Ánh xạ `READ_WRITE` và `PRIVATE` cần channel mở cả đọc lẫn ghi; `READ_ONLY` cần quyền đọc.
- **Xử lý byte order và alignment.** Định dạng tệp trao đổi giữa nhiều hệ thống nên quy định byte order rõ ràng. Offset truy cập cũng phải tương thích alignment của layout.
- **Không mặc định mapping luôn nhanh hơn.** Với file nhỏ hoặc thao tác tuần tự đơn giản, `FileChannel.read/write` hoặc `Files` có thể phù hợp hơn.
- **Không xem mapping là bản sao độc lập.** Thay đổi ở file bởi chương trình khác có thể ảnh hưởng nội dung mapped segment. Tránh để bên ngoài truncate hoặc thay đổi cấu trúc file trong lúc đang truy cập.
- **Kiểm soát tài nguyên hệ điều hành.** Mapping nhiều vùng hoặc giữ arena sống quá lâu có thể làm tăng áp lực lên virtual address space, bộ nhớ và tài nguyên file.

## Khi nào nên dùng FileChannel và Arena?

Sử dụng `FileChannel.map(..., arena)` khi ứng dụng cần truy cập một vùng tệp lớn như vùng nhớ, muốn thao tác trực tiếp theo cấu trúc nhị phân, hoặc cần kiểm soát vòng đời ánh xạ một cách tường minh.

Đối với file nhỏ, đọc tuần tự một lần hoặc dữ liệu cần chuyển thành đối tượng Java thông thường, API `Files` và `FileChannel.read/write` thường dễ hiểu hơn. Memory mapping phát huy tác dụng khi cách truy cập dữ liệu phù hợp với mô hình ánh xạ; hiệu năng cần được đo trên workload và hệ thống tệp thực tế.

## Tài liệu tham khảo

- [JEP 454 — Foreign Function & Memory API (JDK 22)](https://openjdk.org/jeps/454)
- [Java SE 27 API — `FileChannel.map(MapMode, long, long, Arena)`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/channels/FileChannel.html)
- [Java SE 27 API — `MemorySegment`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Java SE 27 API — `Arena`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/Arena.html)
- [Java SE 27 API — `ValueLayout`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [Oracle Java 27 Core Libraries Guide — Backing a Memory Segment with a Memory Region Inside a File](https://docs.oracle.com/en/java/javase/27/core/backing-memory-segment-memory-region-inside-file.html)
