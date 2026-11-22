# Ánh xạ từng vùng và giới hạn kích thước buffer trong Java NIO.2

## 1. Vấn đề: file rất lớn nhưng `MappedByteBuffer` có kích thước `int`

Trong Java NIO.2, `FileChannel.map(MapMode mode, long position, long size)` ánh xạ **một vùng liên tiếp của file** vào không gian địa chỉ của tiến trình và trả về `MappedByteBuffer`. Ứng dụng đọc/ghi byte qua API `ByteBuffer` mà không cần gọi `channel.read`/`write` cho từng đoạn dữ liệu.

Tuy nhiên, có hai kích thước rất khác nhau:

- **Vị trí trên file** dùng `long`, cho phép xác định một offset lớn hơn 2 GiB nếu file và hệ thống tệp hỗ trợ.
- **Kích thước của một vùng ánh xạ** truyền vào `map(..., size)` không âm và **không lớn hơn `Integer.MAX_VALUE`** (2.147.483.647 byte), bởi `MappedByteBuffer.capacity()`, `position()`, `limit()`, `get(int)` đều dùng chỉ số `int`.

Vì vậy, **không thể dùng một `MappedByteBuffer` duy nhất để ánh xạ toàn bộ file lớn hơn giới hạn này**. Giải pháp thông dụng là **ánh xạ lần lượt từng vùng nhỏ (window/chunk)**, mỗi lần có một offset `long` và độ dài phù hợp với `int`.

Mục tiêu sau bài học:

1. Hiểu giới hạn của `MappedByteBuffer` và không nhầm với giới hạn kích thước file.
2. Thiết kế vòng lặp `FileChannel.map` theo từng cửa sổ, không bỏ sót hoặc đọc trùng byte.
3. Chuyển đổi đúng giữa **offset tuyệt đối của file (`long`)** và **index cục bộ của vùng ánh xạ (`int`)**.
4. Xử lý phần cuối file nhỏ hơn cửa sổ, bản ghi nằm vắt qua ranh giới, giới hạn tài nguyên và vòng đời mapping.
5. Biết lúc nào nên dùng mapping và lúc nào chọn `FileChannel.read`/`transferTo`.

## 2. Cơ chế ánh xạ file vào bộ nhớ

Hệ điều hành quản lý một ánh xạ từ vùng địa chỉ ảo của tiến trình tới nội dung file. Tùy hệ điều hành và thời điểm truy cập, trang nhớ có thể được nạp từ file qua page fault, được giữ trong cache hoặc được đẩy ra bộ nhớ phụ.

```text
File lớn trên ổ đĩa (offset kiểu long):
0                                                                fileSize
|--------------------|--------------------|--------------------|--------|
     cửa sổ 0             cửa sổ 1             cửa sổ 2          cuối

FileChannel.map(READ_ONLY, offset, length)
                       |
                       v
MappedByteBuffer (index kiểu int):
0                                     length
|------------------------------------------|
      get(0), get(1), ... get(length - 1)
```

Một `MappedByteBuffer` mới từ `FileChannel.map` có `position=0`, `limit=capacity=size`, mark chưa xác định. Từ góc nhìn của buffer, chỉ số `0` ứng với **byte đầu tiên của vùng được ánh xạ**, tức file offset bằng `position` truyền cho `map`.

**Ánh xạ 256 MiB không đồng nghĩa JVM phải ngay lập tức tạo một `byte[]` 256 MiB trên heap.** `MappedByteBuffer` là direct byte buffer, sử dụng cơ chế bộ nhớ ánh xạ của hệ điều hành; tài nguyên địa chỉ ảo và trang vật lý vẫn có giới hạn, và truy cập có thể phát sinh I/O hoặc lỗi. Không suy luận rằng mapping “miễn phí RAM” hoặc luôn nhanh hơn đọc truyền thống.

## 3. Giới hạn `Integer.MAX_VALUE` có nghĩa gì?

```java
FileChannel channel = /* một FileChannel đã mở */;
long fileSize = channel.size();    // long, có thể > 2 GiB
long offset = 3_000_000_000L;     // Có thể là vị trí hợp lệ trong file lớn
long length = 64L * 1024 * 1024; // Một cửa sổ 64 MiB

MappedByteBuffer mapped =
        channel.map(FileChannel.MapMode.READ_ONLY, offset, length);
```

Đây là **đoạn minh họa trong phương thức**, chỉ thành công nếu channel đọc được, file chứa toàn bộ vùng cần ánh xạ và hệ điều hành còn đủ tài nguyên. Không dùng nguyên văn `/* ... */` như một chương trình độc lập.

`FileChannel.map` nhận `position`/`size` kiểu `long`, nhưng **hợp đồng vẫn yêu cầu `size <= Integer.MAX_VALUE`**. Số `offset` lớn không phải vấn đề tự thân; vấn đề là kích thước **một lần ánh xạ**.

| Đại lượng | Kiểu số | Phạm vi/ý nghĩa |
| --- | --- | --- |
| `channel.size()` | `long` | Kích thước file hiện tại; file có thể lớn hơn 2 GiB |
| `map(..., position, size)` | `long` cho cả hai đối số | `position >= 0`, `0 <= size <= Integer.MAX_VALUE` |
| `mapped.capacity()` | `int` | Số byte thuộc **một** mapping |
| `mapped.position()`, `limit()`, `remaining()` | `int` | Trạng thái/giới hạn cục bộ của mapping |
| `mapped.get(index)` | `int` | Index tương đối với đầu mapping, không phải vị trí toàn file |
| `offset + mappedIndex` | `long` sau khi mở rộng kiểu | Vị trí logic trên file |

**Không ép `fileSize` từ `long` sang `int`** để gọi `map`. Với file lớn hơn 2 GiB, ép kiểu có thể làm số bị tràn hoặc âm. Cũng không cấp một mảng Java dài bằng toàn bộ file: mảng Java dùng chỉ số `int`, và cả bộ nhớ heap lẫn GC đều có giới hạn riêng.

## 4. Thuật toán ánh xạ từng cửa sổ

Giả sử `fileSize=10` byte, chọn `windowSize=4`:

```text
File offsets:  0 1 2 3 | 4 5 6 7 | 8 9
              A B C D | E F G H | I J
Cửa sổ 1:     [0, 4)  length 4
Cửa sổ 2:     [4, 8)  length 4
Cửa sổ 3:     [8,10)  length 2
```

Công thức mỗi vòng:

```text
offset = 0
while offset < fileSize:
    remainingInFile = fileSize - offset
    length = min(windowSize, remainingInFile)
    map(file, offset, length)
    xử lý chính xác length byte
    offset = offset + length
```

Ba yêu cầu quan trọng:

- **Không mất byte:** bắt đầu cửa sổ sau đúng tại `offset + length`, không cộng một số cố định khi cửa sổ cuối ngắn hơn.
- **Không ánh xạ vượt EOF:** chỉ chọn `length <= fileSize - offset`. Đọc vị trí ngoài file không có ngữ nghĩa giống tự động đọc byte bằng 0; Java không bảo đảm hành vi khi mapping vượt phạm vi file.
- **Không gây tràn số:** nếu bảo đảm `0 <= offset <= fileSize` và `length <= fileSize-offset`, thì cập nhật `offset += length` không vượt `fileSize`. Tránh viết `offset + windowSize` để kiểm tra khi hai số có thể lớn gần `Long.MAX_VALUE`.

Với file rỗng (`fileSize==0`), vòng lặp không thực hiện mapping nào. Nếu cửa sổ được cấu hình `0` hoặc âm, phải từ chối trước khi lặp để tránh vòng lặp không tiến triển.

## 5. Ví dụ Java 17+ chạy được: ba cửa sổ trên file 10 byte

Ví dụ sau tạo file tạm chứa `ABCDEFGHIJ`, đọc bằng các ánh xạ dài tối đa 4 byte, sau đó chỉnh byte `F` thành `f` qua ánh xạ ghi và gọi `force()`.

Tạo file `MappedWindowsDemo.java`:

```java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class MappedWindowsDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("mapped-windows-", ".dat");

        // Bản demo dùng temp file. Yêu cầu xóa khi JVM kết thúc;
        // việc xóa có thể còn phụ thuộc OS nếu vùng map đang được giữ.
        file.toFile().deleteOnExit();
        Files.write(file, "ABCDEFGHIJ".getBytes(StandardCharsets.US_ASCII));

        try (FileChannel channel = FileChannel.open(
                file, StandardOpenOption.READ, StandardOpenOption.WRITE)) {

            long fileSize = channel.size();
            long windowSize = 4L;

            for (long offset = 0; offset < fileSize;) {
                long length = Math.min(windowSize, fileSize - offset);
                MappedByteBuffer window = channel.map(
                        FileChannel.MapMode.READ_ONLY, offset, length);

                byte[] bytes = new byte[window.remaining()];
                window.get(bytes);

                System.out.printf("range=[%d,%d), data=%s%n",
                        offset, offset + length,
                        new String(bytes, StandardCharsets.US_ASCII));

                offset += length;
            }

            // File offset 4..7 gồm E F G H.
            MappedByteBuffer writable = channel.map(
                    FileChannel.MapMode.READ_WRITE, 4L, 4L);
            writable.put(1, (byte) 'f'); // index 1 trong window = file offset 5
            writable.force();

            System.out.println("after edit: "
                    + Files.readString(file, StandardCharsets.US_ASCII));
        }
    }
}
```

Biên dịch và chạy trong JDK 17+:

```bash
javac MappedWindowsDemo.java
java MappedWindowsDemo
```

Stdout dự kiến trên hệ thống tệp bình thường, không có tác nhân ngoài thay đổi file:

```text
range=[0,4), data=ABCD
range=[4,8), data=EFGH
range=[8,10), data=IJ
after edit: ABCDEfGHIJ
```

**Giải thích kỹ:**

1. Cửa sổ đầu có `offset=0,length=4`, vì vậy `window.get(0)` (trước khi `get(bytes)`) tương ứng byte `A` ở file offset 0.
2. Cửa sổ hai có `offset=4,length=4`: index cục bộ 0..3 tương ứng vị trí file 4..7, tức `EFGH`.
3. Cửa sổ cuối còn hai byte: `Math.min(4,10-8)=2`. Không cố map 4 byte từ offset 8, vì như vậy vượt cuối file.
4. Mapping ghi tại offset 4, độ dài 4: `put(1, 'f')` chỉnh **byte tại file offset `4+1=5`**, không phải byte có file offset 1.
5. `writable.force()` yêu cầu đẩy thay đổi mapping ghi xuống thiết bị lưu trữ theo hợp đồng API (đảm bảo phụ thuộc loại thiết bị). File được đọc lại thành `ABCDEfGHIJ`.

Ví dụ tạo file tạm và đăng ký `deleteOnExit()`; không in đường dẫn ngẫu nhiên để giữ stdout ổn định. Cần biết rằng trên một số hệ điều hành, nhất là Windows, mapping có thể còn giữ tài nguyên/file lock cho tới khi bộ đệm được thu gom, khiến thao tác xóa file gặp giới hạn; `deleteOnExit` cũng không phải cơ chế bảo đảm xóa an toàn hay xóa ngay tức thì.

## 6. Mẫu xử lý file lớn hơn 2 GiB, không cần cấp phát mảng lớn

Một phương thức xử lý file từng byte bằng cửa sổ cố định:

```java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class WindowedScan {
    // Chọn cửa sổ nhỏ hơn giới hạn Integer.MAX_VALUE.
    private static final long WINDOW_BYTES = 256L * 1024 * 1024;

    public static long checksum(Path path) throws IOException {
        long sum = 0;

        try (FileChannel channel = FileChannel.open(
                path, StandardOpenOption.READ)) {

            long fileSize = channel.size();
            for (long offset = 0; offset < fileSize;) {
                long mappedSize = Math.min(
                        WINDOW_BYTES, fileSize - offset);

                MappedByteBuffer chunk = channel.map(
                        FileChannel.MapMode.READ_ONLY, offset, mappedSize);

                while (chunk.hasRemaining()) {
                    sum += Byte.toUnsignedInt(chunk.get());
                }
                offset += mappedSize;
            }
        }

        return sum;
    }
}
```

Đây là **lớp Java hợp lệ và có thể biên dịch** (không có `main`; gọi `WindowedScan.checksum(path)` từ ứng dụng hay test). Tổng `sum` là tổng giá trị byte 0..255 theo modulo tràn `long` nếu dữ liệu cực lớn; nó chỉ là phép thống kê minh họa, **không phải checksum mật mã** hay công cụ xác minh tính toàn vẹn file an toàn. Cửa sổ 256 MiB chỉ là lựa chọn mẫu; dung lượng phù hợp phụ thuộc hệ điều hành, 32/64-bit, số mapping còn tồn tại, đặc tính file và phép tính.

Điểm quan trọng là chỉ **độ dài của từng `chunk`** phải vừa `int`; biến `offset` và `fileSize` vẫn là `long`. Không chuyển toàn bộ dữ liệu vào `byte[]`.

`FileChannel.map` không bắt buộc mọi cửa sổ đều phải cùng kích thước. Phần cuối file có thể ngắn hơn nhiều. Nếu file tiếp tục được ghi hoặc bị truncate bởi tiến trình khác trong lúc quét, kích thước chụp ban đầu có thể không còn đúng; mẫu này giả định file không thay đổi trong quá trình đọc.

## 7. Cách tính offset tuyệt đối và index trong từng cửa sổ

Giả sử muốn truy cập byte ở vị trí tuyệt đối `absoluteOffset` của một file:

```text
windowStart = floor(absoluteOffset / windowSize) * windowSize
indexInWindow = absoluteOffset - windowStart
byte = mappedWindow.get((int) indexInWindow)
```

Nếu `windowSize=4` và cần đọc file offset 9:

```text
windowStart = (9 / 4) * 4 = 8
indexInWindow = 9 - 8 = 1
mapping cho [8,10) -> get(1) lấy 'J'
```

Hãy dùng các phép tính `long` trước khi ép index về `int`. Chỉ ép sau khi đã xác minh `0 <= indexInWindow < mappedWindow.limit()`. Không truyền `absoluteOffset` trực tiếp cho `mapped.get(int)`: nó là chỉ số của file chứ không phải của mapping.

Khi một cửa sổ được tạo theo yêu cầu thực tế (không cố định kích thước), tính đơn giản hơn:

```java
long localOffset = absoluteOffset - windowStart;

if (localOffset < 0 || localOffset >= window.limit()) {
    throw new IndexOutOfBoundsException("Outside current window");
}
byte value = window.get(Math.toIntExact(localOffset));
```

Đoạn trên minh họa, giả định `window` và `windowStart` là mapping/offset hiện tại. `Math.toIntExact` giúp phát hiện chuyển đổi ngoài giới hạn thay vì âm thầm tràn số. Nên lưu `windowStart` cùng `MappedByteBuffer` trong logic ứng dụng nếu cần truy cập ngẫu nhiên.

## 8. Ranh giới cửa sổ: bản ghi có thể vắt qua hai mapping

Một lỗi tinh vi xảy ra khi đọc dữ liệu có cấu trúc: **biên giới mapping không nhất thiết trùng biên giới bản ghi**.

Ví dụ file gồm các bản ghi 6 byte, nhưng cửa sổ chỉ 4 byte:

```text
File offsets:     0 1 2 3 | 4 5 6 7 | 8 9 10 11
Bản ghi 1:        [----------- 6 byte --------]
Bản ghi 2:                    [----------- 6 byte --------]
Cửa sổ:          [4 byte]   [4 byte]    [4 byte]
```

Nếu mỗi mapping chỉ gọi `getInt()` hoặc giải mã một cấu trúc mà không kiểm tra `remaining()`, phần dữ liệu ở cuối cửa sổ có thể gây `BufferUnderflowException` dù file **vẫn còn byte ở cửa sổ kế tiếp**.

Có ba chiến lược thông dụng:

1. **Cửa sổ căn theo kích thước bản ghi cố định.** Nếu mỗi record đúng 16 byte, chọn `windowSize` chia hết cho 16 và chỉ ánh xạ các phần có đủ record; xử lý phần cuối riêng. Cần lưu ý offset bắt đầu của cấu trúc cũng phải căn phù hợp.
2. **Giữ đoạn chưa đủ (carry-over).** Sao chép một vài byte cuối cửa sổ sang buffer phụ nhỏ, rồi ghép với những byte đầu cửa sổ kế tiếp trước khi parse. Cách này phù hợp format có header hoặc record biến độ dài.
3. **Ánh xạ vùng chồng lấn (overlapping windows).** Mỗi cửa sổ có thể chồng thêm vài byte từ vùng trước/sau để bảo đảm đọc trọn record, nhưng phải xác định chính xác vùng nào thuộc trách nhiệm xử lý của mỗi lượt để **không đếm hoặc ghi trùng byte**.

Ví dụ nếu một số nguyên 4 byte bắt đầu ở file offset 3, trong cửa sổ `[0,4)` chỉ còn một byte; `getInt(3)` không hợp lệ. Cần lấy ba byte còn lại từ cửa sổ `[4,8)` hoặc chọn chiến lược thiết kế khác. Đừng tăng `limit` vượt `capacity` để “mở rộng” một mapping; không thể như vậy.

### 8.1. UTF-8, ký tự và ranh giới window

Nếu file là văn bản UTF-8, một ký tự Unicode có thể mã hóa thành 2–4 byte, nằm vắt qua hai cửa sổ. Chuyển trực tiếp `new String(bytesOfOneWindow, UTF_8)` cho mỗi cửa sổ **có thể làm hỏng ký tự ở ranh giới**. Hãy giữ các byte UTF-8 chưa đủ sang cửa sổ sau, hoặc dùng `CharsetDecoder` ở chế độ streaming với trạng thái giải mã và xử lý `CoderResult.UNDERFLOW` đúng quy tắc.

Điều tương tự xảy ra với delimiter nhiều byte, header độ dài, checksum và cấu trúc nhị phân: **mapping chia theo kích thước vật lý; parser chia theo ranh giới ngữ nghĩa**. Hai việc phải được phối hợp.

## 9. Chọn kích thước cửa sổ bao nhiêu?

Không có một kích thước áp dụng tốt cho mọi hệ thống. Chọn `64 MiB`, `128 MiB` hoặc `256 MiB` có thể hợp lý để thử nghiệm, nhưng phải đo với dữ liệu và môi trường thực tế.

Yếu tố ảnh hưởng:

| Yếu tố | Ảnh hưởng |
| --- | --- |
| Giới hạn API | Mỗi mapping có kích thước tối đa `Integer.MAX_VALUE`; chọn nhỏ hơn để có dư địa |
| Không gian địa chỉ | Tiến trình 32-bit dễ cạn địa chỉ ảo hơn 64-bit |
| Số mapping còn tồn tại | Nhiều cửa sổ cùng sống có thể tăng áp lực địa chỉ và tài nguyên OS |
| Pattern truy cập | Đọc tuần tự, random access, cập nhật theo record có đặc tính khác nhau |
| Kích thước bản ghi | Nếu có thể căn biên, giảm thao tác carry-over và số lần mapping |
| Đặc tính thiết bị | SSD/HDD, network file system, page cache, latency, throughput |
| Khả năng thay đổi file | Mapping file bị truncate bên ngoài có rủi ro hơn đọc file tĩnh |
| Độ bền dữ liệu | Map `READ_WRITE` cần chiến lược force/persist phù hợp |

**Quá nhỏ:** tạo nhiều mapping, tăng overhead và số lần quản lý cửa sổ. **Quá lớn:** tăng áp lực không gian địa chỉ, chi phí map, page fault và tồn tại của mapping. Memory-mapped I/O không luôn nhanh hơn `FileChannel.read`, đặc biệt với file nhỏ hoặc đường đi đọc tuyến tính đơn giản.

Với `WINDOW_BYTES`, thực thi nên xác minh `1 <= WINDOW_BYTES <= Integer.MAX_VALUE` trước khi bắt đầu. Tránh dùng đúng mức tối đa như một mặc định bất biến, nhất là khi triển khai trên đa nền tảng.

## 10. Ba chế độ ánh xạ và khả năng sửa dữ liệu

`FileChannel.MapMode` cung cấp các lựa chọn chính:

| Chế độ | Điều kiện mở channel | Có được gọi `put`? | Có ghi thay đổi vào file gốc? |
| --- | --- | --- | --- |
| `READ_ONLY` | Mở để đọc | Không; sẽ ném `ReadOnlyBufferException` | Không |
| `READ_WRITE` | Mở để đọc **và** ghi | Có | Thay đổi được truyền tới file, thời điểm cụ thể phụ thuộc hệ điều hành; có thể dùng `force()` |
| `PRIVATE` | Mở để đọc **và** ghi | Có, qua copy-on-write | Thay đổi trong vùng riêng **không** lan về file gốc |

`PRIVATE` chỉ tạo bản sao khi cần (copy-on-write theo trang) và **không thay thế** chế độ `READ_WRITE` nếu mục tiêu là chỉnh sửa file. Gọi `force()` trên mapping không phải `READ_WRITE` có thể không có tác dụng.

Để thao tác nhiều cửa sổ ghi, phải chú ý các cửa sổ trùng nhau cùng ánh xạ một file và cách cập nhật đồng thời. Không tự suy luận rằng mọi thread/process thấy thay đổi theo một thứ tự nhất định; phải thiết kế đồng bộ hóa và nhất quán file riêng.

## 11. `force()`, `load()` và `isLoaded()` không phải cùng một chức năng

Ba phương thức thường gặp của `MappedByteBuffer`:

- **`force()`**: với mapping `READ_WRITE`, yêu cầu đẩy các thay đổi đã thực hiện tới thiết bị lưu trữ. Với file trên thiết bị local, API có cam kết về việc ghi thay đổi khi hoàn thành; với thiết bị không local, cam kết này yếu hơn. Phương thức có thể ném `UncheckedIOException` khi đẩy dữ liệu gặp I/O lỗi.
- **`force(index, length)`**: chỉ định một phần vùng của buffer cần đẩy; `index` và `length` là **chỉ số cục bộ**, không phải file offset tuyệt đối. Hệ thống có thể ghi thêm dữ liệu ngoài phạm vi chỉ định do kích thước khối thiết bị.
- **`load()`**: nỗ lực nạp nội dung mapping vào bộ nhớ vật lý; đây là **best effort**, có thể gây page fault/I/O, không có nghĩa dữ liệu sẽ luôn nằm trong RAM.
- **`isLoaded()`**: trả một gợi ý liệu các trang có nhiều khả năng đã ở RAM hay không; kết quả **không phải bảo đảm** cho lần đọc tiếp theo.

Với các cửa sổ ghi, có thể `force()` mỗi cửa sổ sau khi hoàn tất chỉnh sửa, hoặc áp dụng một chính sách đồng bộ theo batch tùy mức độ bền yêu cầu. `channel.force(true)` là thao tác riêng của `FileChannel`; không được đồng nhất vô điều kiện với `mapped.force()` về phạm vi/thời điểm.

## 12. Vòng đời của mapping khác vòng đời của `FileChannel`

Một điểm rất quan trọng: **đóng `FileChannel` không tự động hủy mọi `MappedByteBuffer` đã lấy từ channel đó**. Theo hợp đồng API, mapping vẫn hợp lệ cho đến khi chính buffer của nó được garbage-collected. Java 17 không cung cấp public `MappedByteBuffer.unmap()` tiêu chuẩn.

```java
MappedByteBuffer mapped;
try (FileChannel ch = FileChannel.open(file, StandardOpenOption.READ)) {
    mapped = ch.map(FileChannel.MapMode.READ_ONLY, 0L, 1024L);
}
// Channel đã đóng; mapping vẫn có thể còn hiệu lực.
byte first = mapped.get(0);
```

Đây là đoạn minh họa, giả sử `file` đã khai báo và file chứa tối thiểu 1024 byte; đặt code trong phương thức xử lý `IOException`. Không nên cố điều khiển việc unmap bằng `System.gc()`: JVM không bảo đảm GC chạy đúng lúc.

**Hệ quả đối với ánh xạ từng vùng:**

- Đừng giữ tất cả cửa sổ trong một `List<MappedByteBuffer>` khi không thực sự cần. Với file lớn, cách đó có thể giữ hàng trăm mapping và nhiều tài nguyên OS.
- Sau khi xử lý xong một vùng, bỏ reference khi không cần dùng lại. Việc giải phóng mapping vẫn do JVM/GC quản lý; không thể khẳng định nó được unmap ngay khi biến ra khỏi scope.
- Khi thao tác xóa, thay thế hoặc rename file đã map, Windows và một số provider có thể báo lỗi do mapping còn giữ tài nguyên. Hãy thiết kế lifecycle, kiểm tra hành vi trên hệ điều hành mục tiêu và xử lý lỗi.
- Khi cần vòng đời ánh xạ được quản lý tường minh, có thể nghiên cứu các API mới hơn ở JDK tương ứng; ví dụ Java 22+ có Foreign Function & Memory API với `MemorySegment`, nhưng chữ ký và khả năng hỗ trợ phụ thuộc JDK. Bài này dùng API Java 17+ ổn định là `MappedByteBuffer`.

## 13. File bị thay đổi hoặc truncate trong lúc đang được map

Memory mapping chỉ ổn định khi những điều kiện của file cũng ổn định. Java API nêu rằng hành vi khi một mapping yêu cầu vùng vượt ngoài file, hoặc khi kích thước/nội dung file bị thay đổi sau khi map, **có phần phụ thuộc hệ điều hành và không được đặc tả đầy đủ**.

Cần chú ý:

1. Nếu một tiến trình khác **truncate file** xuống ngắn hơn vùng đã ánh xạ, một phần mapping có thể trở nên không truy cập được. Hậu quả có thể gồm exception hoặc lỗi hệ điều hành; không giả định sẽ tự trả các byte 0.
2. Nếu file **tăng kích thước**, `MappedByteBuffer` cũ không tự tăng `capacity`. Phải tạo mapping mới cho vùng bổ sung nếu logic ứng dụng hỗ trợ.
3. `channel.size()` tại đầu vòng quét chỉ là ảnh chụp của thời điểm đó. Nếu file thay đổi đồng thời, dữ liệu quan sát có thể không nhất quán.
4. Dùng file lock hay phối hợp cấp ứng dụng khi quy trình yêu cầu snapshot ổn định; không giả định file lock sẽ bảo vệ dữ liệu trong mọi provider hoặc mọi hệ điều hành theo cùng cách.
5. Đừng map một vùng rất lớn ngoài EOF rồi mong `READ_WRITE` sẽ luôn cấp phát nội dung có thể truy cập. Có trường hợp API cho phép mapping vùng vượt file nhưng **nội dung/phạm vi bên ngoài hiện có có hành vi không được bảo đảm**; với nhu cầu tăng file, hãy thiết kế chiến lược resize và xác nhận sau đó.

Ở hệ thống sản xuất, đặc biệt với dữ liệu nhạy cảm hoặc tính nhất quán cao, file immutable hoặc phiên bản hóa giúp giảm rất nhiều rủi ro trong quá trình quét từng vùng.

## 14. Các lỗi API và lỗi thiết kế dễ gặp

| Sai lầm | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| `channel.map(READ_ONLY, 0, channel.size())` với file >2 GiB | Một mapping vượt `Integer.MAX_VALUE` | Chia thành windows nhỏ hơn giới hạn |
| Ép `long fileSize` xuống `int` | Dễ overflow/truncate | Giữ `long` cho offset, fileSize, tính window |
| Cửa sổ cuối vẫn map bằng `windowSize` | Vượt EOF | `min(windowSize, fileSize-offset)` |
| `offset += windowSize` bất kể vùng cuối | Dễ tính sai offset hoặc bỏ sót vùng khi logic thay đổi | Tăng đúng `mappedSize` thực tế |
| Gọi `mapped.get((int) absoluteOffset)` | Buffer index cục bộ, không phải file offset | `(int)(absoluteOffset-windowStart)` sau kiểm tra biên |
| Chọn `windowSize=0` | Vòng lặp không tiến triển | Validate giá trị cấu hình từ đầu |
| Đọc `getInt()` khi còn ít hơn 4 byte trong mapping | `BufferUnderflowException` dù file còn byte | Căn window theo record hoặc giữ carry-over |
| Giải mã từng vùng UTF-8 bằng `new String` | Có thể cắt ngang ký tự nhiều byte | Streaming decoder/carry-over |
| Map hàng nghìn cửa sổ và giữ mọi reference | Tài nguyên mapping/địa chỉ ảo tăng | Xử lý tuần tự, quản lý lifetime, đo tải |
| Gọi `force()` rồi coi mọi thay đổi đã bền trên mọi network FS | Cam kết khác nhau theo thiết bị/provider | Thiết kế durability theo môi trường thực |
| `channel.close()` rồi tin mapping đã unmap | Mapping có vòng đời riêng | Không giả định unmap tức thời |
| Truncate file khi còn mapping hoạt động | Mapping có thể mất tính hợp lệ | Điều phối resize với readers/writers |
| Nghĩ mapping luôn nhanh hơn `read()` | Page fault/chi phí ánh xạ có thể cao | Benchmark theo kích thước và kiểu truy cập |

### Ngoại lệ thường gặp

- `IllegalArgumentException`: offset âm, size âm hoặc size vượt giới hạn, hoặc tiền điều kiện khác của `map` bị vi phạm.
- `NonReadableChannelException`: muốn map `READ_ONLY` nhưng channel không được mở để đọc.
- `NonWritableChannelException`: muốn map `READ_WRITE`/`PRIVATE` nhưng thiếu quyền ghi (và đọc).
- `ReadOnlyBufferException`: cố `put` trên mapped buffer `READ_ONLY`.
- `IOException`: lỗi I/O trong khi tạo mapping hay thao tác channel.
- `IndexOutOfBoundsException`/`BufferUnderflowException`: truy cập index hoặc đọc nhiều hơn `limit` của một cửa sổ.

Không gộp tất cả thành “file quá lớn”. Cần log loại thao tác, file size, offset, mapped size, mode và trạng thái channel để phân tích nguyên nhân thực.

## 15. Mapping theo vùng so với `FileChannel.read()`

Memory mapping hữu ích khi thường xuyên đọc ngẫu nhiên trên file lớn hoặc cần thao tác nhiều byte mà không muốn thực hiện nhiều system call riêng lẻ. Nhưng dùng `FileChannel.read(buffer, offset)` vẫn là lựa chọn rất tốt cho tuần tự hoặc khi muốn quản lý trực tiếp kích thước buffer và vòng đời tài nguyên:

| Tiêu chí | `MappedByteBuffer` từng vùng | `FileChannel.read(ByteBuffer, long)` |
| --- | --- | --- |
| Truy cập nội dung | `get/put` trên vùng nhớ ánh xạ | Đọc dữ liệu vào buffer |
| Giới hạn thao tác | Một mapping tối đa `Integer.MAX_VALUE` byte | Một `ByteBuffer` cũng dùng capacity `int`; lặp read nhiều lần |
| Vị trí trên file | `long` offset khi `map` | `long` offset khi `read` |
| Chi phí | Tạo mapping, page fault, địa chỉ ảo | Chi phí read/syscall, copy dữ liệu vào buffer |
| Vòng đời | Mapping có thể tồn tại sau `channel.close()` | Buffer đọc có thể tái sử dụng, không tạo file mapping |
| File bị thay đổi/truncate | Có rủi ro truy cập mapped region phụ thuộc OS | Read tiếp có thể trả số byte mới, EOF hoặc IOException |
| Tính phù hợp | Random access/scan khối lớn tùy workload | Stream/scan tuần tự, parser theo block, lifetime dễ kiểm soát |

Không có quy tắc “file trên 2 GiB thì bắt buộc memory map”. File lớn vẫn có thể xử lý bằng `FileChannel.read` qua nhiều vòng buffer nhỏ. Nếu chỉ sao chép file sang channel khác, xem thêm `transferTo`/`transferFrom` và xử lý số byte thực chuyển, thay vì map rồi chép thủ công.

## 16. Bài tập và lời giải

**Bài 1.** File dài 10 byte, window size 4. Các khoảng cần map là gì?

**Đáp án:** `[0,4)`, `[4,8)`, `[8,10)`; lần lượt 4, 4 và 2 byte. Không map vùng `[8,12)`.

**Bài 2.** File 5 GiB có thể được xử lý bằng `MappedByteBuffer` Java 17 không?

**Đáp án:** Có. Không tạo một mapping 5 GiB; chia thành nhiều mapping, ví dụ 256 MiB/cửa sổ. File offset và fileSize dùng `long`.

**Bài 3.** Mapping `map(READ_ONLY, 1_000L, 100L)`. Byte ở file offset 1.037 ứng với index bao nhiêu?

**Đáp án:** `1037 - 1000 = 37`. Gọi `mapped.get(37)`.

**Bài 4.** Vì sao `mapped.getInt(98)` không được dùng trên vùng 100 byte để đọc 4 byte?

**Đáp án:** Chỉ còn hai byte có chỉ số 98 và 99. Phải đọc thêm ở mapping sau hoặc chọn vùng có đủ 4 byte; absolute `getInt(98)` không thể vượt `limit=100`.

**Bài 5.** Có thể viết `mapped.put(0, (byte)42)` vào mapping `READ_ONLY` không?

**Đáp án:** Không; ném `ReadOnlyBufferException`. Muốn sửa dữ liệu file thì phải mở channel có quyền đọc/ghi và map `READ_WRITE`.

**Bài 6.** Đóng `FileChannel` có giải phóng ngay mapped memory không?

**Đáp án:** Không bảo đảm. `MappedByteBuffer` và mapping của nó có thể vẫn tồn tại tới khi buffer được garbage-collected.

**Bài 7.** Chia UTF-8 theo từng mapping 64 MiB rồi `new String` độc lập trên từng vùng có luôn đúng không?

**Đáp án:** Không. Các byte của cùng một ký tự có thể nằm ở hai vùng; dùng streaming `CharsetDecoder` hoặc cơ chế giữ byte dư.

**Bài 8.** Khi kích thước file lớn hơn `Integer.MAX_VALUE`, có nên viết `int length = (int) channel.size()`?

**Đáp án:** Không. Phép ép có thể tràn và sinh giá trị sai; `channel.size()` phải giữ `long`, chỉ độ dài của cửa sổ đã giới hạn mới được chuyển an toàn thành `int`.

## 17. Checklist triển khai an toàn

1. Mở `FileChannel` với quyền phù hợp `MapMode`.
2. Đọc `fileSize` vào biến `long`; xác định liệu file có thể thay đổi đồng thời không.
3. Chọn `windowSize` dương, không vượt `Integer.MAX_VALUE`, kiểm tra cấu hình.
4. Duyệt `offset` từ 0 khi `offset < fileSize`.
5. Tính `length=Math.min(windowSize, fileSize-offset)` với số `long`.
6. `map(mode, offset, length)`, xử lý đúng `limit/capacity` của mapping và chuyển `absoluteOffset - offset` sang index cục bộ.
7. Nếu parser có record dài hoặc UTF-8, xử lý phần vắt ngang boundary.
8. Với ghi dữ liệu, xác định chế độ `READ_WRITE`, chính sách `force()`, lock và crash consistency.
9. Không giữ quá nhiều mapping, không giả định `close()` unmap ngay; kiểm tra Windows/Linux ở môi trường chạy thực.
10. Benchmark với `FileChannel.read`/I/O khác trước khi khẳng định mapping tốt hơn.

## Tài liệu API

- Java SE 21 — `FileChannel.map(MapMode,long,long)`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html
- Java SE 21 — `MappedByteBuffer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/MappedByteBuffer.html
- Java SE 21 — `ByteBuffer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 21 — `FileChannel.MapMode`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.MapMode.html
