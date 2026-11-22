# Đọc ghi dữ liệu qua vùng nhớ đã ánh xạ (Java NIO.2)

## 1. Vấn đề và mục tiêu

Khi xử lý tệp nhị phân lớn, Java cung cấp hai cách tiếp cận phổ biến:

1. Đọc/ghi byte qua `FileChannel.read(ByteBuffer)` và `FileChannel.write(ByteBuffer)`. Chương trình tự chuẩn bị bộ đệm, gọi I/O rồi xử lý số byte thực tế đã truyền.
2. **Memory-mapped file**: dùng `FileChannel.map(...)` để ánh xạ một **vùng byte trong tệp** thành `MappedByteBuffer`. Chương trình truy cập vùng này bằng `get`, `put` và các phương thức của `ByteBuffer`, còn hệ điều hành quản lý cơ chế ánh xạ giữa bộ nhớ ảo và các trang dữ liệu tệp.

Vùng nhớ đã ánh xạ vẫn liên kết với một tệp thực tế, nhưng ứng dụng thao tác qua chỉ số của buffer. Việc ánh xạ **không có nghĩa toàn bộ tệp được nạp ngay lên heap Java**, cũng không đồng nghĩa mọi thay đổi byte được ghi bền vững xuống thiết bị ngay sau mỗi `put`.

```text
FileChannel ── map(mode, fileOffset, length) ──▶ MappedByteBuffer
    │                                             │
    │                                       get / put / getInt / putLong ...
    │                                             │
    └── tệp trên hệ thống tệp ◀── page cache / ánh xạ bộ nhớ của OS
```

**Mục tiêu:** tạo mapping đúng cách; đọc/ghi dữ liệu thông qua `MappedByteBuffer`; phân biệt `READ_ONLY`, `READ_WRITE`, `PRIVATE`; nắm `position`, `limit`, chỉ số byte so với offset trong tệp; hiểu `force()`, hạn chế về kích thước, hiệu năng, đồng bộ và vòng đời tài nguyên.

## 2. Từ `FileChannel` tới `MappedByteBuffer`

API cốt lõi:

```java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_WRITE,
        fileOffset,
        length
);
```

Đây là đoạn minh họa trong method có `channel` là `FileChannel` đang mở thích hợp và có xử lý `IOException`.

Ba tham số có ý nghĩa:

- `mode`: quyền và cơ chế ghi của vùng ánh xạ.
- `fileOffset`: vị trí bắt đầu **tính bằng byte trong tệp**; có kiểu `long`, phải không âm.
- `length`: độ dài **vùng ánh xạ tính bằng byte**; có kiểu `long` ở lời gọi, nhưng với overload trả `MappedByteBuffer`, kích thước map không được vượt `Integer.MAX_VALUE`. Nó phải không âm.

Nếu ánh xạ từ offset 100 với length 50:

```text
Tệp:            byte 0 ... byte 99 | byte 100 ........ byte 149 | byte 150 ...
                                            ↑                   ↑
Mapped buffer:                            index 0 ...       index 49
buffer.position() ban đầu: 0
buffer.limit() ban đầu:    50
buffer.capacity():         50
```

**Công thức:** `fileOffset + bufferIndex` là vị trí byte tương ứng trong tệp, trong điều kiện vùng tệp không bị thay đổi bởi tác nhân khác. `buffer.get(0)` đọc byte tại `fileOffset`, không phải byte số 0 của cả tệp nếu `fileOffset != 0`.

Khi trả về thành công, buffer có `position=0`, `limit=capacity=length` và `mark` chưa được đặt. `MappedByteBuffer` là một **direct byte buffer**; dữ liệu gắn với mapping, không có một `byte[]` Java truy cập được theo kiểu heap `ByteBuffer.allocate(...)`.

Lưu ý rằng lời gọi `map` tạo một vùng địa chỉ ánh xạ. Nó không tương đương `Files.readAllBytes`, vốn cấp phát một mảng Java chứa toàn bộ byte đọc được.

## 3. Ba chế độ ánh xạ: quyền ghi và quan hệ với tệp

`FileChannel.MapMode` định nghĩa ba mode chuẩn:

| Chế độ | Mở channel | Có thể sửa qua buffer? | Thay đổi được ghi về tệp? |
|---|---|---|---|
| `READ_ONLY` | Cần quyền `READ` | **Không**; `put` ném `ReadOnlyBufferException` | Không có sửa đổi qua view này |
| `READ_WRITE` | Cần đồng thời `READ` và `WRITE` | **Có** | Thay đổi sẽ được truyền về tệp theo cơ chế OS; thời điểm không mặc định xác định |
| `PRIVATE` | Cần đồng thời `READ` và `WRITE` | **Có** | **Không**; copy-on-write tạo bản sao riêng cho phần sửa, không ghi thay đổi đó về tệp |

Ví dụ mở channel rõ quyền:

```java
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path file = Path.of("records.bin");

try (FileChannel channel = FileChannel.open(
        file,
        StandardOpenOption.READ,
        StandardOpenOption.WRITE)) {

    // Chọn mode phù hợp rồi map một đoạn nằm trong file.
    // File chưa tồn tại sẽ gây lỗi mở; ví dụ này giả định nó đã có.
}
```

`READ_ONLY` có thể map bằng channel chỉ mở `READ`. `READ_WRITE` và `PRIVATE` cần channel mở cho **cả đọc lẫn ghi** theo hợp đồng `FileChannel.map`, dù `PRIVATE` không ghi byte đã chỉnh về tệp. Nếu quyền bị thiếu, có thể gặp `NonReadableChannelException` hoặc `NonWritableChannelException`.

### 3.1. `READ_ONLY`: đọc dữ liệu và chặn ghi qua mapping

```java
try (FileChannel channel = FileChannel.open(file,
        StandardOpenOption.READ)) {
    MappedByteBuffer mapped = channel.map(
            FileChannel.MapMode.READ_ONLY, 0, channel.size());

    byte first = mapped.get(0); // Nếu vùng có ít nhất một byte.
    // mapped.put(0, (byte) 7): ReadOnlyBufferException.
}
```

Đây là đoạn mã minh họa với các import đầy đủ và `file` trỏ tới tệp đọc được, không rỗng. Chỉ riêng `mapped.isReadOnly()` biểu thị quyền trên **view**, không biến dữ liệu tệp thành bất biến: tiến trình khác vẫn có thể thay tệp. Sự thay đổi bên ngoài có hiện ngay lên vùng đang map hay không phụ thuộc hệ điều hành và được API để ngỏ.

### 3.2. `READ_WRITE`: sửa byte ngay trên vùng map

```java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_WRITE, 0, 4);

mapped.put(0, (byte) 'J');  // Ghi vị trí đầu của vùng.
mapped.put(1, (byte) 'a');
mapped.put(2, (byte) 'v');
mapped.put(3, (byte) 'a');
mapped.force();              // Yêu cầu ghi các trang thay đổi về thiết bị.
```

Đoạn minh họa giả định `channel` có cả quyền đọc/ghi và tệp đã chứa ít nhất 4 byte. `put(index,value)` là truy cập **absolute**, không tăng `position`. `MappedByteBuffer.force()` được thiết kế để yêu cầu đẩy thay đổi của mapping `READ_WRITE` về thiết bị lưu trữ; chi tiết về độ bền dữ liệu được giải thích ở phần sau.

### 3.3. `PRIVATE`: copy-on-write chứ không phải `READ_ONLY`

```java
MappedByteBuffer privateView = channel.map(
        FileChannel.MapMode.PRIVATE, 0, 4);

privateView.put(0, (byte) 'X'); // Hợp lệ với view writable.
```

Phần dữ liệu bị sửa qua `privateView` được lưu trong bản riêng theo cơ chế copy-on-write, **không truyền ngược về tệp** và không hiển thị cho những chương trình khác đã map tệp đó qua mapping của chúng. Đây không phải cách tạo một **bản sao độc lập toàn bộ tệp ngay khi gọi map**; OS có thể chỉ tạo bản riêng cho những trang được sửa. Không dùng mode này nếu mục tiêu là lưu kết quả chỉnh sửa xuống tệp.

Với các mode khác nhau hoặc các ánh xạ do chương trình khác tạo, đừng tự đoán chính xác thời điểm byte thay đổi trở nên nhìn thấy: hợp đồng Java dành nhiều chi tiết cho OS.

## 4. Chuẩn bị kích thước tệp trước khi map

Khi map để đọc, phải biết vùng nào đang tồn tại. `channel.size()` trả kích thước hiện tại, nhưng một tiến trình khác có thể thay file giữa lúc đo và lúc truy cập.

**Quan trọng:** hợp đồng `FileChannel.map` không xác định rõ hành vi nếu vùng được yêu cầu **không nằm hoàn toàn trong kích thước tệp hiện có**; đừng dựa vào việc map tự mở rộng file mà không có bước chuẩn bị.

Để demo có hành vi rõ, hãy tạo nội dung trước:

```java
byte[] bytes = "HELLO".getBytes(StandardCharsets.US_ASCII);

try (FileChannel channel = FileChannel.open(
        file,
        StandardOpenOption.CREATE,
        StandardOpenOption.TRUNCATE_EXISTING,
        StandardOpenOption.READ,
        StandardOpenOption.WRITE)) {

    ByteBuffer source = ByteBuffer.wrap(bytes);
    while (source.hasRemaining()) {
        channel.write(source);
    }

    MappedByteBuffer mapped = channel.map(
            FileChannel.MapMode.READ_WRITE, 0, bytes.length);
}
```

Đoạn minh họa cần import `java.nio.ByteBuffer`, `java.nio.MappedByteBuffer`, `java.nio.charset.StandardCharsets` cùng lớp/channel ở trên, và method xử lý `IOException`. Dùng vòng lặp `while (source.hasRemaining())` bởi `FileChannel.write` **không đảm bảo** một lời gọi ghi hết byte còn lại trong buffer.

Nếu nghiệp vụ cần tệp nhị phân có kích thước cố định trước khi map, có thể dùng `FileChannel.position(...)` và ghi một byte ở cuối, hoặc phương pháp tạo tệp có kích thước mong muốn bằng các API file-system phù hợp. `FileChannel.truncate(newSize)` **chỉ cắt ngắn khi kích thước hiện tại lớn hơn**; nếu `newSize` lớn hơn kích thước tệp, `truncate` **không mở rộng tệp**.

### 4.1. Một mapping có thể dài bao nhiêu?

Với overload `FileChannel.map(MapMode,long,long)` trả `MappedByteBuffer` trong Java 17/21, `length <= Integer.MAX_VALUE`. Tệp có thể lớn hơn giới hạn này, nhưng **một buffer mapping đơn** vẫn dùng chỉ số `int`.

Để xử lý tệp rất lớn, thiết kế **mapping theo từng cửa sổ**:

```java
long fileSize = channel.size();
long windowSize = 64L * 1024 * 1024; // 64 MiB, minh họa.

for (long offset = 0; offset < fileSize; offset += windowSize) {
    long length = Math.min(windowSize, fileSize - offset);
    MappedByteBuffer window = channel.map(
            FileChannel.MapMode.READ_ONLY, offset, length);

    while (window.hasRemaining()) {
        byte value = window.get();
        // Xử lý từng byte theo yêu cầu cụ thể.
    }
}
```

Đây là đoạn **minh họa thuật toán**, giả định `channel` được mở đọc, file không bị thay đồng thời, và thay `// Xử lý` bằng xử lý nghiệp vụ. Không giữ vô hạn số mapping đã tạo: view có thể còn được giữ sống qua tham chiếu trong hệ thống. Tham số windowSize không phải kích thước trang OS, chỉ là một ví dụ chọn cửa sổ nhỏ hơn giới hạn API. Nếu dữ liệu gồm các bản ghi có thể nằm qua ranh giới cửa sổ, phải giữ lại phần byte dở dang và xử lý ở cửa sổ tiếp theo; không mặc định mỗi cửa sổ chứa một số bản ghi nguyên vẹn.

## 5. Đọc/ghi như một `ByteBuffer`

`MappedByteBuffer` kế thừa `ByteBuffer`, nên nhiều quy tắc quen thuộc áp dụng:

- `capacity`: tổng số byte của mapping, cố định với buffer đó.
- `limit`: giới hạn truy cập hiện tại, ban đầu bằng capacity.
- `position`: nơi `get()` hoặc `put(byte)` kế tiếp đọc/ghi; ban đầu 0.
- `remaining() = limit - position`.
- `get(index)` và `put(index,value)`: **absolute**, không thay position.
- `get()` và `put(value)`: **relative**, tăng position.
- `duplicate()` và `slice()`: tạo view dùng chung dữ liệu nhưng có cursor riêng.
- `clear()`, `flip()`, `rewind()`: chủ yếu quản lý cursor/limit, **không xóa byte khỏi mapping**.

Ví dụ vùng map 6 byte:

```java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_WRITE, 0, 6);

mapped.put(0, (byte) 'A'); // position vẫn 0.
mapped.position(1);
mapped.put((byte) 'B');    // Ghi index 1; position thành 2.
byte first = mapped.get(0); // Đọc index 0; position vẫn 2.
```

Các dòng là minh họa trong method đã mở channel có quyền đọc/ghi, và tệp đủ 6 byte. Nếu bạn gọi `mapped.flip()` sau một đợt sửa byte qua absolute `put(index, value)` mà position vẫn bằng 0, `flip()` sẽ đặt limit bằng 0 và khiến các thao tác đọc tương đối không còn phần tử. Với thao tác truy cập vị trí cố định, không bắt buộc dùng `flip()` như khi ghi nội dung vào `ByteBuffer` để truyền cho channel.

### 5.1. `slice()` giữ dữ liệu chung

```java
MappedByteBuffer base = channel.map(
        FileChannel.MapMode.READ_WRITE, 0, 8);
base.position(2);
base.limit(6);
ByteBuffer slice = base.slice();

slice.put(0, (byte) 99); // Sửa byte index 2 trong base.
```

Đoạn minh họa cần import `ByteBuffer` và `MappedByteBuffer`; base hợp lệ khi tệp ít nhất 8 byte. `slice` có position=0, limit=capacity=4; ánh xạ index 0 của slice sang index 2 của base. Từ Java 17, các thao tác `slice(index,length)` có thể chọn một vùng trực tiếp theo chỉ số.

**Không coi `slice` hoặc `duplicate` là bản sao nội dung.** Việc chúng có cursor riêng không có nghĩa chúng giữ byte riêng. Khi cần snapshot độc lập, copy bytes ra array hoặc `ByteBuffer` mới và cân nhắc tính nhất quán nếu file bị sửa đồng thời.

### 5.2. Đọc số nguyên phụ thuộc `ByteOrder`

Các method `getInt`, `putInt`, `getLong`, `putLong` thao tác trên nhiều byte và yêu cầu thống nhất thứ tự byte trong định dạng file.

```java
mapped.order(ByteOrder.LITTLE_ENDIAN);
mapped.putInt(0, 0x01020304);
System.out.printf("%02X %02X %02X %02X%n",
        mapped.get(0) & 0xFF,
        mapped.get(1) & 0xFF,
        mapped.get(2) & 0xFF,
        mapped.get(3) & 0xFF);
```

Đoạn minh họa giả định mapping READ_WRITE dài ít nhất 4 byte và import `java.nio.ByteOrder`. Output byte trong LITTLE_ENDIAN:

```text
04 03 02 01
```

Nếu đọc một file lưu little-endian mà không đặt thứ tự byte, giá trị `getInt()` sẽ có thể sai. `ByteBuffer` mới dùng thứ tự mặc định **BIG_ENDIAN**. Không đồng nhất việc ánh xạ tệp với việc tự nhận diện endian từ định dạng dữ liệu.

## 6. Ví dụ hoàn chỉnh Java 17+: ghi và đọc lại một file mapped

Ví dụ sau dùng nội dung ASCII cố định để phân biệt rõ **vị trí byte** với ký tự. Nó tạo file tạm, ghi `HELLO`, map `READ_WRITE`, sửa bằng truy cập absolute lẫn relative, kiểm tra `READ_ONLY` và `PRIVATE`, rồi đọc lại byte lưu trong file.

**Tệp:** `MappedIoDemo.java`

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.MappedByteBuffer;
import java.nio.ReadOnlyBufferException;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class MappedIoDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("mapped-io-", ".bin");

        // Mapping có thể giữ handle tài nguyên sau khi FileChannel đóng.
        // Dọn file tạm khi JVM kết thúc ở mức best effort.
        file.toFile().deleteOnExit();

        byte[] initial = "HELLO".getBytes(StandardCharsets.US_ASCII);

        try (FileChannel channel = FileChannel.open(
                file,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {

            ByteBuffer source = ByteBuffer.wrap(initial);
            while (source.hasRemaining()) {
                channel.write(source);
            }

            MappedByteBuffer mapped = channel.map(
                    FileChannel.MapMode.READ_WRITE, 0, initial.length);

            System.out.println("map size: " + mapped.capacity());
            System.out.println("first byte: " + (char) mapped.get(0));

            mapped.put(0, (byte) 'h'); // H -> h, position không đổi.

            ByteBuffer alias = mapped.duplicate();
            alias.put(1, (byte) 'I');  // E -> I trong storage chung.

            mapped.position(2);
            mapped.put((byte) 'y');   // L -> y, position tăng thành 3.

            System.out.println("position: " + mapped.position());
            System.out.println("alias change: "
                    + (char) mapped.get(1));

            // READ_WRITE: yêu cầu đẩy các byte sửa sang thiết bị.
            mapped.force();

            MappedByteBuffer readOnly = channel.map(
                    FileChannel.MapMode.READ_ONLY, 0, initial.length);
            System.out.println("read only: " + readOnly.isReadOnly());

            try {
                readOnly.put(0, (byte) 'X');
            } catch (ReadOnlyBufferException ex) {
                System.out.println("read-only write blocked");
            }

            MappedByteBuffer privateMap = channel.map(
                    FileChannel.MapMode.PRIVATE, 0, initial.length);
            privateMap.put(0, (byte) 'P');
            System.out.println("private first: "
                    + (char) privateMap.get(0));
        }

        // Đọc qua API file thông thường sau khi đã force mapping.
        // Việc PRIVATE ghi 'P' không thay byte tương ứng của file.
        System.out.println("file content: "
                + Files.readString(file, StandardCharsets.US_ASCII));
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac MappedIoDemo.java
java MappedIoDemo
```

**Stdout mong đợi trên hệ thống tệp thông thường hỗ trợ memory mapping:**

```text
map size: 5
first byte: H
position: 3
alias change: I
read only: true
read-only write blocked
private first: P
file content: hIyLO
```

Giải thích:

1. File được ghi đủ 5 byte trước khi map nên vùng `0..4` hoàn toàn nằm trong file hiện có.
2. `MappedByteBuffer` mới có `capacity=5`; `get(0)` thấy chữ `H`.
3. `put(0,'h')` là absolute; `alias.put(1,'I')` thay byte index 1 trong **cùng vùng nhớ**, cho dù alias có position riêng.
4. `mapped.position(2); mapped.put('y')` sửa byte index 2 rồi tăng position lên 3. Ba thay đổi tạo byte `hIyLO`.
5. `mapped.force()` yêu cầu ghi các thay đổi của mapping `READ_WRITE`.
6. Mapping `READ_ONLY` cho phép đọc nhưng từ chối `put`.
7. Mapping `PRIVATE` cho phép sửa view thành `P...`, nhưng **không ghi** chữ `P` vào file. Vì vậy dòng đọc file cuối giữ `hIyLO`.

Ví dụ cố ý dùng byte ASCII một byte mỗi ký tự. Trong thực tế, khi file dùng UTF-8, một code point Unicode có thể chiếm nhiều byte; không đặt `mapped.put(index, (byte) someChar)` rồi kỳ vọng luôn ghi đúng tiếng Việt hoặc emoji. Hãy encode cả chuỗi bằng `CharsetEncoder` hoặc `getBytes(StandardCharsets.UTF_8)` rồi ghi đúng số byte và kích thước vùng.

Lệnh `deleteOnExit()` chỉ là dọn dẹp tạm **best effort**: một số hệ điều hành giữ file/mapping trong lúc JVM còn sống hoặc có hạn chế xóa file; không biến nó thành lời hứa đã giải phóng OS mapping ngay sau `channel.close()`.

## 7. Đọc văn bản UTF-8 qua mapping

Mapped buffer mang byte; muốn đọc văn bản phải **giải mã theo charset**, không ép từng byte thành `char`.

Ví dụ file UTF-8 đã tồn tại, đọc toàn bộ trong trường hợp kích thước **không vượt giới hạn một mapping**:

```java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class MappedUtf8Reader {
    public static String read(Path file) throws IOException {
        try (FileChannel ch = FileChannel.open(
                file, StandardOpenOption.READ)) {

            long size = ch.size();
            if (size > Integer.MAX_VALUE) {
                throw new IOException("File too large for one mapping");
            }

            MappedByteBuffer data = ch.map(
                    FileChannel.MapMode.READ_ONLY, 0, size);

            return StandardCharsets.UTF_8.decode(data).toString();
        }
    }
}
```

Đây là helper có thể biên dịch (`MappedUtf8Reader.java`), không có `main` và không in stdout. `StandardCharsets.UTF_8.decode(data)` ở dạng convenience giải mã thành `CharBuffer`; với đầu vào không hợp lệ, cách xử lý lỗi của convenience method có thể dùng thay thế ký tự theo contract của `Charset`. Nếu nghiệp vụ yêu cầu **từ chối UTF-8 không hợp lệ**, dùng `CharsetDecoder` và `onMalformedInput(CodingErrorAction.REPORT)` cùng thao tác decode có kiểm soát. Vì output trả một `String`, helper này vẫn cần đủ RAM cho kết quả, dù quá trình đọc byte được map và không sao chép toàn file thành `byte[]` trung gian.

**Không** chia UTF-8 thành các window tùy tiện rồi decode từng window độc lập: một chuỗi byte nhiều phần có thể bị tách giữa hai cửa sổ. Nếu cần xử lý văn bản lớn theo đoạn, giữ state của decoder giữa những window, truyền phần byte chưa đủ ở ranh giới sang window kế tiếp, và xử lý end-of-input/flush đúng quy tắc `CharsetDecoder`. Nếu chỉ cần xử lý văn bản tuần tự, `BufferedReader` hoặc `Channels.newReader` thường đơn giản hơn.

## 8. `force()`, `load()` và `isLoaded()` làm việc gì?

### 8.1. `MappedByteBuffer.force()`: yêu cầu ghi vùng thay đổi

`mapped.force()` tác động lên vùng byte của mapping `READ_WRITE`. Với Java 17+, có overload:

```java
mapped.force();           // Toàn bộ vùng ánh xạ.
mapped.force(0, 1024);    // Vùng bắt đầu ở index 0, dài 1024 byte.
```

Dòng thứ hai chỉ hợp lệ khi `mapped.capacity() >= 1024`; cả hai là mã minh họa. Chỉ số của `force(index,length)` nằm trong **buffer mapped**, không phải offset tuyệt đối toàn tệp. Implementation có thể ghi cả các byte bên ngoài đoạn yêu cầu do đơn vị block/trang của OS.

Theo contract: nếu file ở **thiết bị lưu trữ cục bộ**, sau khi `force()` trả thành công, các thay đổi của vùng ánh xạ READ_WRITE đã được ghi tới thiết bị; với thiết bị không cục bộ, không có bảo đảm tương tự. `force()` trên mapping `READ_ONLY` hoặc `PRIVATE` **không** giúp lưu thay đổi về file. `force()` có thể ném `UncheckedIOException` nếu có lỗi ghi.

Không nên nhầm `mapped.force()` với `channel.force(metaData)`:

| API | Áp dụng cho | Ý nghĩa chính |
|---|---|---|
| `MappedByteBuffer.force()` | Những byte trong mapping | Yêu cầu đẩy thay đổi mapping về thiết bị theo điều kiện API |
| `MappedByteBuffer.force(index,length)` | Một đoạn của mapping | Force đoạn byte tương đối trong mapping |
| `FileChannel.force(boolean metaData)` | Nội dung cập nhật qua channel; tùy `metaData` có thể gồm metadata | Bảo đảm theo contract của FileChannel về các thay đổi file được thực hiện qua channel |

Nếu có cả thao tác ghi qua `FileChannel.write` và qua mapping, hãy đọc hợp đồng của cả hai, rồi xác định điều kiện độ bền đúng cho hệ thống tệp và môi trường. Không đánh đồng flush một buffer với transaction nhiều file hoặc bảo đảm crash consistency cho cấu trúc dữ liệu nhiều bước.

### 8.2. `load()` là nỗ lực nạp trang dữ liệu, không phải `force()`

`mapped.load()` yêu cầu JVM/OS cố gắng đưa các trang dữ liệu đã ánh xạ vào bộ nhớ vật lý trước để giảm page faults khi truy cập sau đó.

`mapped.isLoaded()` trả **gợi ý** liệu các trang đang cư trú hay không:

- `true` có nghĩa có khả năng cao dữ liệu đang resident, **không bảo đảm mãi mãi**.
- `false` **không khẳng định** mọi trang đều bị đẩy ra khỏi RAM.
- OS có thể thay đổi tình trạng resident ngay sau lời gọi.

Ví dụ:

```java
mapped.load();
boolean probablyResident = mapped.isLoaded();
```

Đây là đoạn minh họa với mapped đã hợp lệ. Không dùng `isLoaded()` làm điều kiện correctness hay khẳng định chắc chắn “đã có đủ byte trong RAM”. `load()` có thể phát sinh I/O và page faults; chỉ gọi trước khi truy cập nếu đo đạc cho thấy có lợi.

## 9. Map một vùng của file và xử lý bản ghi nhị phân

Giả sử định dạng một bản ghi cố định 12 byte gồm:

```text
Offset tương đối   Kích thước   Trường
0                  4 byte       id (int, LITTLE_ENDIAN)
4                  8 byte       timestamp (long, LITTLE_ENDIAN)
```

Đọc một record bằng mapped buffer:

```java
static long readTimestamp(MappedByteBuffer mapped, int recordIndex) {
    final int recordSize = Integer.BYTES + Long.BYTES;
    int base = Math.multiplyExact(recordIndex, recordSize);
    return mapped.getLong(base + Integer.BYTES);
}
```

Đây là đoạn minh họa trong class đã import `MappedByteBuffer`; caller phải đặt `mapped.order(ByteOrder.LITTLE_ENDIAN)` và kiểm tra recordIndex cũng như phạm vi vùng trước khi gọi. `Math.multiplyExact` giúp phát hiện tràn số nguyên khi tính offset, nhưng nếu giá trị vượt `limit`, thao tác vẫn có thể ném `IndexOutOfBoundsException`. Việc đọc một `long` có thể không đủ tính nguyên tử nếu file được tác nhân khác sửa đồng thời.

Cần phân biệt:

- **Offset trong tệp**: kiểu `long`, áp dụng khi gọi `map`.
- **Index trong buffer**: kiểu `int`, bắt đầu từ 0 của mapping.
- **Record offset**: tính theo số byte, không phải số trường.
- **Thứ tự byte**: dữ liệu trên đĩa phải có định dạng xác định và trùng với cấu hình `ByteOrder` lúc đọc/ghi.

Nếu file là log có cấu trúc, ngoài id và timestamp còn có thể cần header magic, version, length, checksum, trạng thái commit và xử lý bản ghi dở dang. Memory mapping chỉ cung cấp cách truy cập byte; nó **không tự cung cấp** định dạng bản ghi hoặc cơ chế giao dịch.

## 10. Khác nhau giữa map và read/write thông thường

| Tiêu chí | `FileChannel.read/write` | `FileChannel.map` |
|---|---|---|
| Mô hình truy cập | Truyền byte qua `ByteBuffer` khi gọi I/O | Ánh xạ file rồi truy cập byte qua `MappedByteBuffer` |
| Chi phí khởi tạo | Thường nhỏ cho I/O tuần tự ngắn | Thiết lập mapping có chi phí; không nhất thiết tốt cho file nhỏ |
| Truy cập ngẫu nhiên | Có thể dùng positional `read/write` | Thuận tiện dùng `get(index)` và `put(index,value)` |
| Bộ nhớ | Chủ động quản lý buffer | Dùng vùng địa chỉ ảo và trang OS; không phải tự động đưa toàn file lên Java heap |
| File rất lớn | Dễ xử lý từng lần đọc/ghi | Mapping đơn giới hạn `Integer.MAX_VALUE` byte; thường cần nhiều window |
| Đồng bộ và lưu bền | Quản lý write và `FileChannel.force` | Quản lý mapping và `MappedByteBuffer.force` |
| Vòng đời | Đóng channel kết thúc I/O của channel | Đóng channel **không** tự hủy mapping ngay |
| Thay đổi đồng thời | Vẫn phải thiết kế tính nhất quán | Mapping dễ chịu ảnh hưởng của thay đổi ngoài ý muốn; nhiều hành vi OS-dependent |

Chọn mmap thường có ích khi dữ liệu lớn, truy cập ngẫu nhiên nhiều lần hoặc muốn xem file như cấu trúc byte có index. Với tệp văn bản nhỏ, thao tác một lần hoặc I/O tuần tự, `Files.readString`, `BufferedInputStream`, `FileChannel.read` có thể đơn giản hơn và hiệu quả không kém. Hãy đo hiệu năng trong workload thật thay vì coi mmap luôn “zero-copy” theo nghĩa không có bất kỳ sao chép hay page fault nào.

## 11. Đồng thời, thay đổi file và những rủi ro khó thấy

### 11.1. Một vùng mapped không phải ảnh chụp bất biến

Nếu tiến trình khác sửa nội dung file, ánh xạ có thể quan sát thay đổi vào thời điểm phụ thuộc hệ điều hành. Không có bảo đảm chung rằng mỗi lần đọc nhiều trường tạo nên một snapshot logic nhất quán. Một thread khác sửa cùng mapped buffer cũng có thể tạo data race.

Muốn chia sẻ dữ liệu với nhiều thread hoặc nhiều process:

- Thiết kế giao thức cập nhật: ví dụ version, trạng thái commit, lock hoặc cơ chế memory visibility tương ứng.
- Dùng đồng bộ phù hợp; chỉ dùng `getInt`/`putInt` trên buffer không tự biến cấu trúc nhiều trường thành giao dịch atomic.
- Nếu cần phối hợp giữa tiến trình, tìm hiểu `FileLock` và bảo đảm của OS/file system; lock cũng có giới hạn và không thay thế kiểm tra consistency của định dạng.
- Đừng trộn `READ_WRITE` và `PRIVATE` rồi kỳ vọng những view này có cùng cách nhìn mọi thay đổi.

### 11.2. Không thay đổi kích thước file bên dưới một mapping đang dùng

Tài liệu Java cảnh báo rằng nội dung mapped buffer có thể trở nên **không truy cập được** nếu file bị cắt ngắn (truncate). Truy cập vùng không còn hợp lệ có thể gây ngoại lệ không được chỉ rõ. Hành vi khi thay đổi độ dài hoặc nội dung file sau khi đã map cũng phụ thuộc OS.

Nguyên tắc: khi dùng mmap cho file đang thay đổi, bảo vệ vòng đời và độ dài file bằng chính sách ownership/locking hoặc thiết kế format xử lý phiên bản; tránh `truncate` file đang còn vùng mapped truy cập. Không sử dụng `catch (RuntimeException)` rồi âm thầm coi byte lỗi như giá trị hợp lệ.

### 11.3. Mapping không tự quản lý transaction

Giả sử một bản ghi gồm `balance`, `version` và `checksum`. Việc ghi tuần tự từng trường vào mapping có thể bị người đọc khác quan sát **giữa chừng**. `force()` giúp đẩy byte thay đổi về thiết bị trong điều kiện hợp đồng, nhưng **không** biến chuỗi thay đổi thành một transaction nguyên tử và không cung cấp rollback.

Nếu cần crash consistency, phải thiết kế thứ tự cập nhật, journal/WAL, checksum, marker commit, double buffering hoặc các cơ chế bền vững phù hợp. Mmap là **cách truy cập** byte trong file, không phải hệ quản trị giao dịch.

### 11.4. Read-only buffer có còn thấy file thay đổi không?

`READ_ONLY` chỉ cấm ghi **qua buffer ấy**. Nếu tác nhân khác thay file trên đĩa, một số OS có thể phản ánh thay đổi vào mapping; Java không bảo đảm thời điểm hoặc sự hiện diện của việc phản ánh. Do đó, `READ_ONLY` không phải snapshot về mặt dữ liệu và không thay thế copy riêng khi cần tính bất biến.

## 12. Vòng đời và giải phóng ánh xạ

Một điểm khác `FileChannel` thông thường: vùng mapping do `MappedByteBuffer` đại diện vẫn có thể hợp lệ **sau khi channel dùng để tạo nó đã đóng**. Theo Java API, mapping và buffer tồn tại cho đến khi buffer được garbage collector thu hồi.

```java
MappedByteBuffer mapped;
try (FileChannel ch = FileChannel.open(
        file, StandardOpenOption.READ)) {
    mapped = ch.map(FileChannel.MapMode.READ_ONLY, 0, ch.size());
}
// FileChannel đã đóng, mapped vẫn có thể dùng theo contract mapping.
// Nhưng map phụ thuộc tính hợp lệ của vùng tệp bên dưới.
```

Đây là đoạn minh họa giả định `file` hợp lệ, method xử lý `IOException` và file không bị tác nhân khác thay đổi bất lợi. **Không** suy ra rằng đóng channel sẽ unmap, giải phóng địa chỉ ảo, hoặc lập tức cho phép xóa file trên mọi OS.

Đặc biệt trên Windows, file đã map có thể khó bị xóa/đổi tên khi OS còn giữ mapping. `MappedByteBuffer` trong Java 17/21 **không có một phương thức `close()` công khai** để chủ động unmap tương tự `FileChannel.close()`. Việc cố gọi API nội bộ JDK để ép unmap rất phụ thuộc phiên bản/module access, không nên làm mặc định.

Đối với tệp tạm, cân nhắc thiết kế không giữ tham chiếu mapping quá lâu, sử dụng dọn dẹp best-effort và chấp nhận có thể cần chờ tài nguyên mapping được giải phóng. Với ứng dụng cần kiểm soát vòng đời unmap chính xác, hãy đánh giá các API memory-segment chính thức phù hợp phiên bản Java đang dùng thay vì dựa vào hàm dọn dẹp nội bộ; riêng bài này dùng API `MappedByteBuffer` phổ biến của Java 17+.

### 12.1. Vì sao không cần hoặc không thể kiểm soát page cache theo ý muốn?

Hệ điều hành quyết định lúc nào dữ liệu mapped được đưa vào trang RAM và lúc nào được thay thế. `load()` chỉ là nỗ lực, `isLoaded()` là hint. Java `System.gc()` không phải giải pháp đúng để điều khiển cache hoặc bảo đảm hủy mapping ngay; chương trình không được đòi hỏi GC thực thi theo thời điểm xác định.

## 13. Lỗi và ngoại lệ cần biết

| Tình huống | Biểu hiện thường gặp | Hướng xử lý |
|---|---|---|
| `map` với offset/size âm hoặc size quá lớn | `IllegalArgumentException` | Kiểm tra chỉ số/kích thước, dùng mapping theo cửa sổ |
| Chọn `READ_ONLY` nhưng channel không mở đọc | `NonReadableChannelException` | Mở channel đúng quyền |
| Chọn `READ_WRITE` hoặc `PRIVATE` mà thiếu quyền đọc/ghi | `NonReadableChannelException` / `NonWritableChannelException` | Mở channel với cả `READ` và `WRITE` |
| Ghi vào view `READ_ONLY` | `ReadOnlyBufferException` | Dùng `READ_WRITE` nếu thực sự cần lưu; kiểm tra chính sách |
| `get`/`put` vượt giới hạn buffer | `IndexOutOfBoundsException`, `BufferUnderflowException` hoặc `BufferOverflowException` tùy thao tác | Kiểm tra `position`/`limit`/`remaining` và dữ liệu đầu vào |
| I/O khi mở hoặc tạo mapping lỗi | `IOException` | Xem quyền, trạng thái file, dung lượng và provider |
| `force()` gặp lỗi ghi | `UncheckedIOException` | Xử lý lỗi persistence, không giả định byte đã lưu |
| Tệp bị truncate trong lúc mapping còn sử dụng | Hành vi truy cập không được chỉ rõ, có thể ném ngoại lệ | Thiết kế ownership và không đổi kích thước file đang dùng |
| Xóa/đổi tên file đang mapped không thành công | Phụ thuộc OS và handle mapping | Kiểm soát vòng đời, tránh giả định close(channel) = unmap |
| Kiểm tra `isLoaded() == false` | Không đủ bằng chứng byte không ở RAM | Đừng dùng hint này làm điều kiện correctness |

Các exception như `NonReadableChannelException` / `NonWritableChannelException` là unchecked; `IOException` là checked, còn lỗi truy cập mapped memory khi file bị thay đổi ngoài ý muốn có thể không khớp một subtype cố định. Đừng biến mọi failure thành “file không tồn tại”.

## 14. Lỗi phổ biến khi đọc/ghi qua mapped buffer

1. **Cho rằng `map` đọc ngay toàn bộ file vào heap.** Nó thiết lập ánh xạ; OS quyết định nạp trang.
2. **Tưởng `READ_WRITE` đồng nghĩa ghi bền vững ngay sau `put`.** Thời điểm truyền về file có thể không xác định; khi cần persistence, dùng `force` với điều kiện hợp đồng.
3. **Dùng `PRIVATE` để sửa file.** Mode này giữ copy-on-write, không phản ánh chỉnh sửa về file.
4. **Gọi `put` lên `READ_ONLY`.** Kết quả `ReadOnlyBufferException`.
5. **Map vượt kích thước file hiện tại** rồi dựa vào việc OS sẽ tự mở rộng. Hành vi ngoài vùng file không được contract bảo đảm.
6. **Dùng `truncate(larger)` để mở rộng file.** `truncate` không tăng size khi kích thước mới lớn hơn kích thước hiện tại.
7. **Map toàn bộ file lớn hơn 2 GiB bằng một `MappedByteBuffer`.** Overload này giới hạn size ≤ `Integer.MAX_VALUE`; cần chia cửa sổ.
8. **Nhầm offset file với index mapped.** Index 0 của mapping ứng với offset được truyền khi `map`, không nhất thiết là byte 0 của file.
9. **Nhầm `get(index)` với `get()`.** Absolute access không tăng position, relative access có tăng.
10. **Gọi `flip` sau toàn bộ absolute `put`** làm limit thành 0 nếu position chưa di chuyển; gây lỗi đọc tiếp.
11. **Bỏ qua `ByteOrder` khi ghi struct nhị phân.** `getInt`/`putLong` theo byte order của buffer; phải khớp format file.
12. **Ép từng UTF-8 byte thành `char`.** Mã Unicode có thể chiếm nhiều byte; dùng charset decoder.
13. **Cho rằng `READ_ONLY` là snapshot bất biến.** Nội dung file có thể bị thay đồng thời.
14. **Cho rằng `force()` tạo transaction** hoặc bảo đảm nhiều cập nhật atomic. Không có cơ chế transaction tự động.
15. **Dựa vào `isLoaded()` để quyết định tính đúng sai.** Nó chỉ là hint, không phải phép chứng minh.
16. **Nghĩ đóng `FileChannel` sẽ giải phóng mapping ngay.** Mapping có vòng đời độc lập và gắn với GC.
17. **Giữ nhiều mapping nhỏ mà không quản lý tham chiếu.** Tốn vùng địa chỉ, tài nguyên OS, có thể cản xóa file.
18. **Đổi kích thước file đang mapped** mà không điều phối các tiến trình/luồng. Có thể làm vùng truy cập không còn hợp lệ.
19. **Gắn memory mapping với “luôn nhanh hơn”.** Mapping có chi phí thiết lập và page faults; hiệu năng phụ thuộc kích thước và kiểu truy cập.
20. **Trộn nhiều writer trên cùng file mà không có giao thức.** Có thể làm mất nhất quán dữ liệu dù từng `put` hợp lệ.

## 15. Câu hỏi tự kiểm tra

**1.** `FileChannel.map(READ_ONLY, 100, 20)` trả buffer có `capacity` và `position` ban đầu là bao nhiêu?  
**Đáp án:** capacity = 20, position = 0; `mapped.get(0)` tương ứng byte file offset 100.

**2.** Vì sao chọn `PRIVATE` vẫn cần quyền ghi channel?  
**Đáp án:** Contract của `FileChannel.map` yêu cầu channel đọc và ghi cho cả `READ_WRITE` lẫn `PRIVATE`, dù byte sửa trong PRIVATE không được đưa về file.

**3.** Map 3 GiB qua overload trả `MappedByteBuffer` của Java 17 được không?  
**Đáp án:** Không; `length` bị giới hạn ≤ `Integer.MAX_VALUE`. Cần map từng cửa sổ và xử lý biên.

**4.** `mapped.put(0, (byte) 7)` có đưa `position` từ 0 lên 1?  
**Không.** Đây là absolute put. `mapped.put((byte)7)` mới tăng position tương đối.

**5.** Khi dùng `READ_WRITE`, gọi `mapped.force()` nhằm mục đích gì?  
**Đáp án:** Yêu cầu ghi thay đổi của mapping về thiết bị; bảo đảm cụ thể áp dụng khi file nằm trên thiết bị cục bộ, còn hệ thống khác có thể không có cam kết tương đương.

**6.** Nếu `mapped.isLoaded()` trả `false`, có chắc dữ liệu không ở RAM?  
**Không.** API chỉ trả hint; false không chứng minh điều ngược lại.

**7.** Đóng `FileChannel` có làm mọi `MappedByteBuffer` tạo từ nó mất hiệu lực ngay không?  
**Không.** Mapping có vòng đời riêng; ngược lại, việc file bị truncate có thể gây hỏng khả năng truy cập mapping.

**8.** Tại sao không thể dùng `mapped.force()` thay cho cơ chế transaction nhiều trường?  
**Vì** `force` liên quan ghi bytes về thiết bị, không bảo đảm nhóm cập nhật thành một hành động atomic hoặc tự rollback.

**9.** Nếu ghi `putInt(0, 0x01020304)` theo little-endian, byte tại các chỉ số 0..3 là gì?  
**Đáp án:** `04 03 02 01`.

**10.** Một file chứa tiếng Việt UTF-8, có thể in `(char)mapped.get(i)` cho mỗi byte để nhận văn bản đúng không?  
**Không.** Cần decoder UTF-8 và giữ trạng thái chuyển đổi tại ranh giới byte, đặc biệt với ký tự nhiều byte.

## 16. Ghi nhớ và tài liệu tham khảo

**Nguyên tắc:** `FileChannel.map` cho phép xem một vùng byte của tệp như một `MappedByteBuffer` có chỉ số. `READ_ONLY` để đọc; `READ_WRITE` để chỉnh dữ liệu sẽ truyền về file; `PRIVATE` để chỉnh copy-on-write không truyền về file. Kiểm soát offset, kích thước map, byte order, quyền truy cập, `force()` và vòng đời mapping. Memory mapping cải thiện sự thuận tiện cho một số kiểu truy cập ngẫu nhiên nhưng không thay thế cơ chế đồng bộ, giao dịch hoặc kiểm tra dữ liệu.

Nguồn tài liệu Java SE 21 chính thức:

- `FileChannel.map` và các chế độ `FileChannel.MapMode`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html
- `MappedByteBuffer` (`force`, `load`, `isLoaded`, vòng đời): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/MappedByteBuffer.html
- `ByteBuffer` (đọc/ghi số, view, `ByteOrder`): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html
- `StandardCharsets` và `CharsetDecoder`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html và https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html
