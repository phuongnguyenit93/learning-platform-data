# Khi nào chọn RandomAccessFile thay FileChannel trong Java?

## 1. Câu trả lời thực dụng

Khi cần **truy cập ngẫu nhiên** tới một tệp (đọc/ghi tại một vị trí byte xác định), Java cung cấp cả `java.io.RandomAccessFile` và `java.nio.channels.FileChannel`. Cả hai đều có thể đọc/ghi ngoài thứ tự tuần tự. Khác biệt quan trọng nhất là **mức trừu tượng, cách thao tác dữ liệu, cách quản lý vị trí và các tính năng mở rộng**.

**Chọn `RandomAccessFile`** khi tác vụ tương đối đơn giản, thiên về đọc/ghi các giá trị nguyên thủy theo một con trỏ chung: `seek(offset)` rồi `readInt()`, `writeLong()`, `readFully(byte[])`. API gọn, dễ đọc, thường phù hợp cho tệp nhị phân nhỏ/vừa, cấu trúc bản ghi cố định, bài tập và công cụ bảo trì.

**Chọn `FileChannel`** khi cần `ByteBuffer`, đọc/ghi theo vị trí tuyệt đối mà **không đổi con trỏ kênh**, xử lý khối dữ liệu lớn, `transferTo/transferFrom`, `map` (memory mapping), `lock`, hoặc chia việc đọc/ghi cho nhiều thành phần sử dụng offset rõ ràng.

Không nên hiểu rằng “`RandomAccessFile` là API truy cập ngẫu nhiên, còn `FileChannel` chỉ đọc tuần tự”. **Cả hai đều hỗ trợ truy cập ngẫu nhiên.** `FileChannel` cũng có `position(long)` để di chuyển vị trí hiện tại.

| Nhu cầu | Thường chọn | Vì sao |
|---|---|---|
| Đọc/ghi một vài `int`, `long`, `double` ở offset cụ thể | `RandomAccessFile` | Có sẵn phương thức kiểu nguyên thủy, ít mã chuyển đổi |
| Thay trường dữ liệu trong bản ghi cố định | `RandomAccessFile` nếu thao tác đơn giản | `seek` + `writeInt` rất trực quan |
| Đọc/ghi nhiều vùng không liền nhau và muốn giữ nguyên vị trí hiện tại | `FileChannel` | `read(buffer, position)` / `write(buffer, position)` |
| Làm việc với buffer, batch I/O, gathering/scattering | `FileChannel` | API NIO làm việc trực tiếp với `ByteBuffer` |
| Sao chép khối byte giữa channel/file | `FileChannel` | `transferTo` / `transferFrom` |
| Memory-mapped file, khóa vùng tệp | `FileChannel` | `map`, `lock`, `tryLock` |
| Muốn dùng thư viện `DataInput` / `DataOutput` cũ | `RandomAccessFile` | Triển khai trực tiếp cả hai interface |
| Cần xử lý file rất lớn | Tùy thao tác, thường cân nhắc `FileChannel` | Cả hai dùng offset `long`; channel có thêm chiến lược I/O |
| Nhiều luồng đọc các vùng độc lập theo offset | Thường `FileChannel` với positional I/O, có phối hợp | Tránh việc nhiều tác vụ tự đổi một con trỏ chung |

“Thường chọn” là gợi ý thiết kế, **không phải bảo đảm hiệu năng**. Tốc độ còn tùy filesystem, độ lớn buffer, thiết bị lưu trữ, cách gọi API và mẫu truy cập; khi hiệu năng quan trọng, cần benchmark với dữ liệu thực tế.

## 2. Random access là gì?

Tệp có thể xem như dãy byte đánh chỉ số từ `0` đến `length - 1`. Truy cập ngẫu nhiên cho phép chuyển tới offset cụ thể để đọc hoặc sửa tại chỗ, không cần xử lý từ byte đầu tiên.

Giả sử tệp chứa ba số nguyên `int` liên tiếp, mỗi số dài 4 byte:

```text
Offset      0         4         8        12
            |---------|---------|---------|
Giá trị     |   10    |   20    |   30    |
            |---------|---------|---------|
                    ^
          Bản ghi số 2 bắt đầu ở byte 4
```

Muốn cập nhật số thứ hai thành `99`, ta cần ghi 4 byte từ offset `4`. Cả `RandomAccessFile` và `FileChannel` đều làm được. Nếu mỗi bản ghi có độ dài cố định `recordSize`, offset bản ghi thứ `index` (đếm từ 0) là:

```text
offset = headerSize + index * recordSize
```

Trong mã thực tế nên dùng `long` cho offset và tính toán cẩn thận, ví dụ `Math.multiplyExact((long) index, recordSize)` để tránh tràn số. Đảm bảo mỗi offset có nghĩa theo **định dạng tệp**, không được giả định một ký tự UTF-8 luôn có độ dài một byte.

## 3. Cách RandomAccessFile làm việc

`RandomAccessFile` nằm trong `java.io`, implements `DataInput`, `DataOutput` và `Closeable`. Nó có **con trỏ tệp (file pointer)** dùng chung cho các thao tác đọc/ghi có vị trí hiện tại:

- `getFilePointer()`: trả offset của thao tác kế tiếp.
- `seek(long pos)`: đặt file pointer về offset từ đầu tệp; offset không được âm.
- `readInt()`, `readLong()`, `readDouble()`, `readBoolean()`, `readFully(...)`: đọc dữ liệu và tiến file pointer theo số byte đã dùng.
- `writeInt(int)`, `writeLong(long)`, `write(byte[])`: ghi dữ liệu rồi tiến con trỏ.
- `length()`: trả kích thước tệp theo byte; `setLength(long)`: thay đổi độ dài tệp.
- `getChannel()`: lấy `FileChannel` liên kết với chính đối tượng này.

Ví dụ minh họa (đây là đoạn mã, giả định `file.bin` có định dạng ba số nguyên):

```java
try (RandomAccessFile raf = new RandomAccessFile("file.bin", "rw")) {
    raf.seek(4L);
    int second = raf.readInt();   // Đọc 4 byte ở offset 4; pointer thành 8

    raf.seek(4L);
    raf.writeInt(second + 1);     // Ghi lại 4 byte; pointer thành 8
}
```

Ưu điểm nằm ở chỗ `readInt/writeInt` lo sẵn việc kết hợp bốn byte thành `int` theo **big-endian**. Các phương thức của `DataInput/DataOutput` dùng biểu diễn nhị phân xác định, giúp mã cho bản ghi chứa giá trị nguyên thủy dễ đọc.

### Chế độ mở tệp

| Mode | Ý nghĩa |
|---|---|
| `"r"` | Chỉ đọc; tệp phải tồn tại |
| `"rw"` | Đọc và ghi; có thể tạo tệp nếu chưa tồn tại |
| `"rws"` | Như `rw`, yêu cầu cập nhật nội dung **và** metadata của tệp được đồng bộ xuống thiết bị lưu trữ theo ngữ nghĩa API |
| `"rwd"` | Như `rw`, yêu cầu đồng bộ **nội dung** tệp; không yêu cầu đồng bộ metadata theo cùng mức |

`"rws"` và `"rwd"` có thể gây chi phí I/O lớn nếu ghi rất thường xuyên. Chúng cũng không tạo ra bảo đảm giao dịch/atomic toàn cục, không thay thế cơ chế kiểm soát lỗi hay chiến lược lưu dữ liệu. Trên một số hệ thống, khả năng đảm bảo đồng bộ cuối cùng phụ thuộc thiết bị và filesystem.

### Các lưu ý riêng của RandomAccessFile

1. `readInt()` cần đủ **4 byte**, nếu tới EOF sớm sẽ ném `EOFException`. `read(byte[])` thì có thể đọc ít hơn yêu cầu; khi muốn lấy đúng N byte, dùng `readFully(byte[])` hoặc xử lý lặp.
2. `readUTF/writeUTF` dùng **modified UTF-8** với phần độ dài mã hóa giới hạn, **không phải** giao thức UTF-8 tùy ý dùng `StandardCharsets.UTF_8`. Hai đầu đọc/ghi phải thống nhất định dạng.
3. `readLine()` là API cũ không phù hợp để đọc văn bản UTF-8 tổng quát. Với văn bản nên cân nhắc `BufferedReader`/`Files.newBufferedReader` và charset rõ ràng.
4. `seek` đi tới vị trí ngoài EOF được phép, nhưng việc đọc tại đó sẽ gặp EOF; nếu ghi ở vị trí vượt EOF, tệp mở rộng và giá trị các byte khoảng trống trung gian không nên được giả định theo một mẫu cụ thể.
5. `setLength` khi thu nhỏ sẽ cắt bỏ phần cuối; nếu file pointer lớn hơn độ dài mới, file pointer được điều chỉnh về độ dài mới. Khi mở rộng, nội dung vùng mở rộng không được bảo đảm có giá trị tùy ý mà ứng dụng mong đợi.
6. `RandomAccessFile` có một **file pointer dùng chung**; nếu nhiều luồng `seek` rồi `read/write` trên cùng đối tượng mà không phối hợp, vị trí có thể thay đổi xen giữa hai lệnh, dẫn tới truy cập nhầm bản ghi.

## 4. Cách FileChannel làm việc

`FileChannel` nằm trong `java.nio.channels`. Thông thường, dùng `FileChannel.open(Path, OpenOption...)` để làm việc với tệp hoặc lấy channel từ `RandomAccessFile.getChannel()`.

`FileChannel` xử lý dữ liệu qua `ByteBuffer`. Chương trình tự chọn kích thước buffer, cách giải mã các giá trị và `ByteOrder`. Điều này nhiều mã hơn với một vài kiểu nguyên thủy, nhưng thuận tiện khi đọc/ghi theo khối hoặc tích hợp hệ sinh thái NIO.

```java
try (FileChannel channel = FileChannel.open(
        Path.of("file.bin"),
        StandardOpenOption.READ,
        StandardOpenOption.WRITE)) {

    ByteBuffer value = ByteBuffer.allocate(Integer.BYTES)
            .order(ByteOrder.BIG_ENDIAN);

    value.putInt(99);
    value.flip();                     // Chuyển từ ghi vào buffer sang đọc buffer

    while (value.hasRemaining()) {
        channel.write(value);         // Ghi từ vị trí hiện tại của channel
    }
}
```

Đoạn này là **minh họa**, cần import `Path`, `StandardOpenOption`, `ByteBuffer`, `ByteOrder`, `FileChannel`; đồng thời giả định tệp đã tồn tại. Trước khi muốn sửa **đúng offset 4**, phải gọi `channel.position(4L)` hoặc dùng lệnh ghi theo vị trí tuyệt đối. Không có `position(4L)` trong đoạn minh họa nên nó ghi tại **vị trí hiện tại khi mở**, thường là đầu tệp.

### Hai kiểu I/O của FileChannel

**I/O theo con trỏ hiện tại (sequential-position I/O):**

```java
channel.position(4L);
channel.read(buffer);
channel.write(buffer);
```

Đây là đoạn mô tả phương thức; các lệnh đọc/ghi tăng vị trí channel theo lượng byte thực tế được xử lý. Trước mỗi `write`, cần đặt `ByteBuffer.position/limit` đúng trạng thái.

**I/O theo vị trí tuyệt đối (positional I/O):**

```java
channel.read(buffer, 4L);
channel.write(buffer, 4L);
```

Hai thao tác trên sử dụng offset cung cấp và **không thay đổi channel.position()**. Đây là lợi thế khi nhiều logic thao tác các vùng tệp khác nhau. Tuy nhiên, một lời gọi `read/write` có thể xử lý **ít byte hơn** `buffer.remaining()`, nên đối với dữ liệu có độ dài cố định cần lặp, đồng thời tự tăng offset sau mỗi lần xử lý.

Các tính năng khác của `FileChannel`:

- `size()`, `truncate(size)`, `position(pos)`: kích thước, cắt bớt, thay con trỏ. **`truncate` không tự mở rộng** tệp nếu kích thước truyền vào lớn hơn hiện tại; điểm này khác `RandomAccessFile.setLength`.
- `force(boolean metaData)`: yêu cầu đồng bộ nội dung (và metadata nếu `true`) ra lưu trữ theo ngữ nghĩa API. Mức đảm bảo cuối cùng còn tùy loại tệp, filesystem và hệ thống.
- `transferTo` / `transferFrom`: truyền byte giữa channel, đôi khi có tối ưu từ OS, nhưng **không bảo đảm zero-copy** hoặc truyền hết trong một lời gọi.
- `map(FileChannel.MapMode, position, size)`: ánh xạ một vùng tệp thành `MappedByteBuffer` để truy cập bộ nhớ ánh xạ. Hữu ích cho kiểu truy cập nhất định nhưng cần cân nhắc page fault, kích thước ánh xạ, vòng đời mapping và tài nguyên.
- `lock` / `tryLock`: khóa file/vùng file. Việc khóa được tôn trọng tới mức nào phụ thuộc OS/filesystem; không xem đây là giải pháp duy nhất cho mọi tình huống đồng thời.
- `read(ByteBuffer[])` / `write(ByteBuffer[])`: thao tác scattering/gathering với nhiều buffer.

**Lưu ý quan trọng:** `FileChannel` có thể là API rất tốt mà không cần dùng `map` hay zero-copy; positional I/O thông thường đã là lý do hợp lệ để chọn nó.

## 5. Chương trình Java 17+ hoàn chỉnh: cùng thao tác, hai API

Ví dụ ghi ba số nguyên 4 byte theo thứ tự `10, 20, 30`, đọc số thứ hai, thay thành `99`, sau đó đọc lại. Hai cách có cùng kết quả dữ liệu; `FileChannel` cho thấy việc đọc/ghi theo offset tuyệt đối không làm thay đổi channel position.

Tạo tệp tên **`RandomAccessChoiceDemo.java`**:

```java
import java.io.EOFException;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class RandomAccessChoiceDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("random-access-demo-");
        Path rafPath = directory.resolve("raf.bin");
        Path channelPath = directory.resolve("channel.bin");

        try {
            usingRandomAccessFile(rafPath);
            usingFileChannel(channelPath);
        } finally {
            Files.deleteIfExists(rafPath);
            Files.deleteIfExists(channelPath);
            Files.deleteIfExists(directory);
        }
    }

    private static void usingRandomAccessFile(Path path) throws IOException {
        try (RandomAccessFile raf = new RandomAccessFile(path.toFile(), "rw")) {
            raf.setLength(0);
            raf.writeInt(10);
            raf.writeInt(20);
            raf.writeInt(30);

            raf.seek(Integer.BYTES);
            System.out.println("RAF before: " + raf.readInt());

            raf.seek(Integer.BYTES);
            raf.writeInt(99);

            raf.seek(Integer.BYTES);
            System.out.println("RAF after: " + raf.readInt());
        }
    }

    private static void usingFileChannel(Path path) throws IOException {
        try (FileChannel channel = FileChannel.open(
                path,
                StandardOpenOption.CREATE,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE,
                StandardOpenOption.TRUNCATE_EXISTING)) {

            ByteBuffer all = ByteBuffer.allocate(3 * Integer.BYTES)
                    .order(ByteOrder.BIG_ENDIAN);
            all.putInt(10).putInt(20).putInt(30);
            all.flip();

            while (all.hasRemaining()) {
                channel.write(all);
            }
            // Sau 12 byte ghi tuần tự, position() là 12.

            long secondOffset = Integer.BYTES;
            System.out.println("Channel before: "
                    + readIntAt(channel, secondOffset));

            ByteBuffer replacement = ByteBuffer.allocate(Integer.BYTES)
                    .order(ByteOrder.BIG_ENDIAN);
            replacement.putInt(99);
            replacement.flip();
            writeFullyAt(channel, replacement, secondOffset);

            System.out.println("Channel after: "
                    + readIntAt(channel, secondOffset));
            System.out.println("Channel position: " + channel.position());
        }
    }

    private static int readIntAt(FileChannel channel, long offset)
            throws IOException {
        ByteBuffer buffer = ByteBuffer.allocate(Integer.BYTES)
                .order(ByteOrder.BIG_ENDIAN);
        long position = offset;

        while (buffer.hasRemaining()) {
            int count = channel.read(buffer, position);
            if (count < 0) {
                throw new EOFException("Not enough bytes for int");
            }
            if (count == 0) {
                throw new IOException("No progress while reading");
            }
            position += count;
        }

        buffer.flip();
        return buffer.getInt();
    }

    private static void writeFullyAt(
            FileChannel channel, ByteBuffer buffer, long offset)
            throws IOException {
        long position = offset;

        while (buffer.hasRemaining()) {
            int count = channel.write(buffer, position);
            if (count == 0) {
                throw new IOException("No progress while writing");
            }
            position += count;
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa mã nguồn:

```bash
javac RandomAccessChoiceDemo.java
java RandomAccessChoiceDemo
```

Trên filesystem hỗ trợ các thao tác tạo/ghi/xóa tệp thông thường, stdout chính xác là:

```text
RAF before: 20
RAF after: 99
Channel before: 20
Channel after: 99
Channel position: 12
```

Giải thích từng điểm:

1. `Integer.BYTES` bằng `4`. Số thứ hai bắt đầu ở offset `4`.
2. `RandomAccessFile.readInt()` đọc đúng 4 byte từ con trỏ đã `seek`; để đọc lại cùng vị trí sau khi sửa phải `seek` lần nữa.
3. `ByteBuffer.putInt` và `getInt` xử lý cùng dữ liệu big-endian. `flip` đặt lại vị trí/giới hạn để buffer có thể được tiêu thụ đúng cách.
4. `FileChannel` đã ghi tuần tự 12 byte, nên vị trí hiện tại bằng `12`. Cả `readIntAt` và `writeFullyAt` gọi positional I/O với `offset=4`, vì vậy vị trí channel **vẫn bằng 12**.
5. Hai hàm helper dùng vòng lặp vì lời gọi `FileChannel.read/write` không bảo đảm xử lý toàn bộ buffer trong một lần. Kiểm tra EOF và tình trạng không tiến thêm byte giúp ví dụ tránh vòng lặp vô hạn.

Ví dụ chủ động dùng **hai tệp riêng**, vì mục tiêu là minh họa cùng định dạng bằng hai API, tránh việc hai lần chạy ảnh hưởng dữ liệu của nhau. Đường dẫn thư mục tạm là ngẫu nhiên nhưng không được in ra, nên stdout không phụ thuộc tên thư mục.

## 6. RandomAccessFile và FileChannel có thể dùng chung một tệp

`RandomAccessFile.getChannel()` trả về một `FileChannel` liên kết với cùng đối tượng tệp. **File pointer của RandomAccessFile và position của channel liên kết sẽ cùng phản ánh một vị trí**, khi một bên dùng API làm thay đổi vị trí hiện tại.

Ví dụ minh họa (giả định tệp tồn tại; chưa phải chương trình độc lập):

```java
try (RandomAccessFile raf = new RandomAccessFile("shared.bin", "rw")) {
    FileChannel channel = raf.getChannel();

    raf.seek(8L);
    System.out.println(channel.position());  // 8

    channel.position(12L);
    System.out.println(raf.getFilePointer()); // 12
}
```

Đừng dùng `raf.seek(...)` ở một nơi và `channel.read(...)` ở nơi khác trên cùng đối tượng mà tưởng rằng hai con trỏ độc lập. Một thao tác positional `channel.read(buffer, offset)` không thay position, nhưng các thao tác phụ thuộc position và `seek` có thể ảnh hưởng nhau.

Đặc biệt, tránh đóng riêng channel được `raf.getChannel()` rồi tiếp tục giả định có thể dùng RAF như cũ. Hãy thiết kế rõ **quyền sở hữu tài nguyên** và đóng đối tượng bao ngoài theo try-with-resources.

## 7. Các tình huống chọn API chi tiết

### Tình huống A — Tệp cấu hình nhị phân vài trăm bản ghi cố định

Ví dụ mỗi bản ghi chứa `long id`, `int status`, `double score` (tổng 20 byte nếu không có padding). Ứng dụng cần đọc bản ghi thứ `i` rồi cập nhật `status`.

`RandomAccessFile` phù hợp khi chỉ có một luồng hoặc đã bảo vệ phần `seek + read/write`, định dạng không phức tạp và không cần chức năng channel đặc biệt. Có thể viết `raf.seek(offset)`, `raf.readLong()`, `raf.readInt()`, `raf.readDouble()` một cách trực quan.

Cần ghi rõ endianness, byte offset của từng trường, version của định dạng, giới hạn kích thước file và hành vi khi dữ liệu bị cắt. Dùng `Math.addExact` và `Math.multiplyExact` nếu offset tính từ input không tin cậy.

### Tình huống B — Dịch vụ đọc nhiều vùng tệp theo offset độc lập

Giả sử dịch vụ nhận yêu cầu đọc 4 KiB ở các offset khác nhau. `FileChannel.read(buffer, offset)` thường phù hợp hơn: mỗi yêu cầu mang offset riêng, không cần tự gọi `position(offset)` rồi đọc từ con trỏ chung.

Tuy vậy, “offset riêng” **không** tự bảo đảm an toàn nếu nhiều tác vụ ghi đè cùng vùng, cắt/đổi kích thước tệp, hoặc quản lý vòng đời channel sai. Cần đồng bộ/thiết kế bất biến dữ liệu, và kiểm soát việc đóng channel khi yêu cầu đang chạy.

### Tình huống C — Sao chép vùng lớn, xử lý buffer hoặc ánh xạ bộ nhớ

Khi cần truyền dữ liệu sang một `WritableByteChannel`, đọc nhiều buffer, hoặc truy cập lặp nhiều vùng bằng mapping, `FileChannel` cung cấp các API chuyên biệt. `transferTo` có thể tận dụng tối ưu của hệ điều hành trên một số trường hợp, nhưng phải kiểm tra số byte thực sự truyền và lặp nếu cần.

Memory mapping không phải lựa chọn luôn nhanh hơn. Với file lớn và pattern ngẫu nhiên, nên xét page fault, bộ nhớ ảo, khả năng thay đổi kích thước tệp, thời điểm dữ liệu được flush và vòng đời mapping. Benchmark từng phương án trong điều kiện vận hành.

### Tình huống D — Chỉ cần sửa một trường nguyên thủy rồi đóng

Nếu thao tác một lần, định dạng là big-endian, điều kiện filesystem đơn giản, `RandomAccessFile` tiết kiệm mã và ít điểm sai hơn việc chuẩn bị `ByteBuffer`. Nhiều dòng mã hơn không làm `FileChannel` sai; nó chỉ có thể không cần thiết cho bài toán rất nhỏ.

### Tình huống E — Có sẵn hệ thống xử lý ByteBuffer/NIO

Nếu tầng I/O, serializer hoặc parser hiện có sử dụng `ByteBuffer`, chọn `FileChannel` thường giúp giảm chuyển đổi giữa `byte[]` và buffer, và thuận tiện để tích hợp với cơ chế NIO đang dùng.

### Tình huống F — Yêu cầu đọc/ghi bất đồng bộ

Không nên chọn API chỉ vì tên chứa “Channel”. **`FileChannel` và `RandomAccessFile` đều là API I/O đồng bộ** trong cách dùng thông thường. Nếu cần mô hình bất đồng bộ thực sự, hãy xem `AsynchronousFileChannel` và thiết kế xử lý completion/future phù hợp; hiệu quả và cách triển khai vẫn phụ thuộc nền tảng.

## 8. Hiệu năng, bộ nhớ và đồng thời

**Không có “nhanh hơn tuyệt đối”.** `RandomAccessFile` có thể hiệu quả cho các thao tác nguyên thủy đơn giản, trong khi `FileChannel` có lợi thế API cho khối lớn, direct buffers, mapping, transfer và positional I/O. Không thể khẳng định rằng chỉ cần đổi `RandomAccessFile` sang `FileChannel` sẽ tăng tốc.

Khi đánh giá hiệu năng:

- Đo với kích thước tệp, phân bố offset, tỉ lệ đọc/ghi, filesystem và phần cứng thực tế.
- Tránh so sánh một bên đọc từng byte với một bên đọc theo buffer lớn: khác biệt đó phần lớn đến từ kích thước I/O.
- Phân biệt **heap buffer** (`ByteBuffer.allocate`) và **direct buffer** (`ByteBuffer.allocateDirect`); direct buffer có chi phí cấp phát/quản lý riêng và không phải mặc định tốt hơn.
- Phân biệt latency đơn lẻ và throughput; các phương thức đồng bộ dữ liệu bền vững như `"rws"/"rwd"` hoặc `force` có thể thay đổi đáng kể hiệu năng.
- Không coi file lock là thay thế mọi đồng bộ trong cùng tiến trình. Cách khóa vùng và mức độ bắt buộc/tư vấn phụ thuộc OS/filesystem.

`RandomAccessFile` có `seek` + thao tác theo con trỏ; mỗi cặp lệnh đó **không tự biến thành một thao tác nguyên tử** đối với nhiều luồng. Với `FileChannel`, positional read/write giảm phụ thuộc con trỏ chung, nhưng ứng dụng vẫn phải quản lý truy cập trùng vùng, truncate, lock, xử lý partial I/O và close đúng lúc.

## 9. Sai lầm thường gặp

1. **Nghĩ FileChannel không random access:** thực tế có cả `position(long)` và `read/write(ByteBuffer, long)`.
2. **Quên `ByteBuffer.flip()`:** sau khi `putInt`, buffer đang ở chế độ ghi; nếu không `flip`/điều chỉnh giới hạn, lệnh ghi kênh có thể không ghi dữ liệu mong đợi.
3. **Nghĩ `read/write(ByteBuffer)` luôn xử lý hết:** phải kiểm tra return value, remaining, EOF và lặp khi định dạng yêu cầu đúng N byte.
4. **Nhầm thứ tự byte:** `RandomAccessFile.readInt/writeInt` dùng big-endian; `ByteBuffer` mặc định big-endian nhưng có thể bị đổi bằng `order(...)`. Hai bên phải thống nhất.
5. **Nhầm ký tự với byte:** offset random access là **byte offset**. Với UTF-8, một ký tự có thể chiếm nhiều byte, nên không thể tính offset ký tự bằng phép nhân cố định tùy tiện.
6. **Dùng `seek` khi nhiều luồng chia sẻ file pointer:** thao tác xen kẽ có thể đọc/ghi sai vị trí. Chọn cơ chế đồng bộ hoặc positional I/O thích hợp.
7. **Nhầm `truncate` với `setLength`:** `FileChannel.truncate` chỉ thu nhỏ nếu size nhỏ hơn hiện tại; `RandomAccessFile.setLength` có thể mở rộng.
8. **Mở `RandomAccessFile("rw")` rồi tưởng sẽ tự xóa nội dung cũ:** mode `"rw"` không tự truncate; muốn thay mới toàn bộ tệp phải chủ động `setLength(0)` hoặc dùng chính sách phù hợp.
9. **Chọn API dựa trên tuyên bố “zero-copy luôn nhanh”:** `transferTo/From` không bảo đảm luôn zero-copy, và có thể truyền ít hơn số byte yêu cầu.
10. **Quên giới hạn định dạng:** `writeUTF/readUTF` là modified UTF-8 với giới hạn riêng; không dùng thay thế vô điều kiện cho văn bản UTF-8 chuẩn.
11. **Dùng `force` hoặc `"rws"` như bảo đảm giao dịch:** đồng bộ dữ liệu không đồng nghĩa atomic nhiều bản ghi hay phục hồi hoàn chỉnh khi mất điện.
12. **Bỏ qua ngoại lệ/cleanup:** dùng try-with-resources, phân biệt EOF và lỗi I/O, và xác nhận dữ liệu khi đọc bản ghi bị thiếu/corrupt.

## 10. Checklist ra quyết định

Trả lời bốn câu hỏi này:

1. **Dữ liệu được đọc/ghi thế nào?** Một vài primitive tại offset cố định → nghiêng về `RandomAccessFile`; khối byte/`ByteBuffer` → nghiêng về `FileChannel`.
2. **Có cần vị trí đọc/ghi tuyệt đối độc lập con trỏ hiện tại?** Nếu có, `FileChannel.read/write(buffer, position)` thuận tiện hơn.
3. **Có cần transfer, mapping, locking, gathering/scattering hoặc hệ sinh thái NIO?** Nếu có, `FileChannel` là lựa chọn tự nhiên.
4. **Có yêu cầu đồng thời, crash consistency và hiệu năng đặc biệt không?** Thiết kế phối hợp luồng, đồng bộ lưu trữ và benchmark trước khi quyết định; tên API không giải quyết thay kiến trúc.

**Quy tắc dễ nhớ:** `RandomAccessFile` tối ưu cho **sự đơn giản khi thao tác primitive + seek**; `FileChannel` tối ưu cho **sự linh hoạt khi thao tác buffer và offset**. Ưu tiên API giải quyết đúng nhu cầu với ít độ phức tạp nhất.

## 11. Câu hỏi tự kiểm tra

**Câu 1:** Một tệp chứa 1.000 bản ghi, mỗi bản ghi đúng 24 byte, ứng dụng một luồng chỉ cập nhật một `int` ở bản ghi thứ `i`. Chọn gì?  
**Gợi ý:** `RandomAccessFile` thường đủ đơn giản; tính `offset = header + i * 24 + fieldOffset` bằng `long`, `seek` rồi `writeInt`; kiểm tra kích thước, chỉ số và định dạng.

**Câu 2:** Đọc luân phiên 100 vùng khác nhau, mỗi vùng 8 KiB, không muốn thay một con trỏ chung. Chọn gì?  
**Gợi ý:** `FileChannel` với `read(ByteBuffer, long position)` và vòng lặp đảm bảo đủ byte; quản lý buffer/offset cho từng yêu cầu.

**Câu 3:** Sau `channel.write(buffer, 128)`, `channel.position()` có tự đổi sang 128 + số byte đã ghi không?  
**Không.** Lời gọi ghi theo vị trí tuyệt đối không thay position của channel.

**Câu 4:** Dùng `RandomAccessFile("rw")` và gọi `seek(0)` để ghi 4 byte vào tệp dài 1 MiB. Tệp có tự giảm còn 4 byte không?  
**Không.** Ghi đè 4 byte đầu không tự cắt bỏ dữ liệu còn lại; có thể dùng `setLength(4)` nếu định dạng và mục tiêu yêu cầu.

**Câu 5:** Muốn mở rộng một tệp lên 4 KiB bằng API riêng cho từng loại, `raf.setLength(4096)` và `channel.truncate(4096)` có tương đương không?  
**Không.** `setLength` có thể mở rộng; `truncate` không mở rộng nếu size lớn hơn kích thước hiện tại.

## 12. Tóm tắt

- **`RandomAccessFile`:** file pointer + `seek` + API `DataInput/DataOutput` cho primitive; dễ hiểu với định dạng bản ghi nhị phân đơn giản.
- **`FileChannel`:** `ByteBuffer`, vị trí tuyệt đối, truyền dữ liệu, memory mapping, locking và các kỹ thuật NIO; phù hợp khi cần kiểm soát I/O chi tiết.
- **Cả hai đều random access, dùng offset `long`, có thể phát sinh lỗi I/O và cần đóng tài nguyên.** Chọn theo cấu trúc dữ liệu, đặc tính truy cập và yêu cầu triển khai, không theo giả định hiệu năng chung.
