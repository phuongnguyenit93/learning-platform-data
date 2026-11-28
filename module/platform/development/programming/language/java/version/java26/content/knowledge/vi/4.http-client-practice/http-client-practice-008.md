# Offset, length và quyền sở hữu FileChannel

Khi làm việc với file lớn, file tải xuống hoặc dữ liệu nhị phân, ứng dụng thường chỉ cần đọc hay ghi một vùng byte thay vì nạp toàn bộ file vào bộ nhớ. FileChannel cung cấp thao tác I/O theo vị trí tuyệt đối, cho phép chỉ định offset bắt đầu và xử lý số byte cần đọc hoặc ghi. Để dùng đúng API, cần phân biệt vị trí trong file với trạng thái của ByteBuffer, xử lý trường hợp I/O chưa hoàn tất trong một lần gọi và xác định rõ thành phần nào chịu trách nhiệm đóng channel.

FileChannel là API NIO ổn định, có từ Java 1.4 và vẫn được hỗ trợ trong JDK 26. Đây không phải tính năng mới của Java 26, cũng không phải preview hay incubator. Có thể sử dụng trực tiếp trong project Java 26 mà không cần cờ preview.

## 1. Mô hình vị trí và độ dài

FileChannel làm việc với một file được xem như dãy byte. Trong các thao tác positional read/write và transfer, vị trí và số lượng dữ liệu được tính theo byte, không phải số ký tự, số dòng hay số phần tử Java. Có một ngoại lệ dễ nhầm: overload read(ByteBuffer[] dsts, int offset, int length) và write(ByteBuffer[] srcs, int offset, int length) dùng offset làm chỉ số bắt đầu trong mảng buffer và length làm số buffer tối đa cần xử lý; hai tham số đó không phải byte offset và byte length của file.

- **Offset** là vị trí byte bắt đầu tính từ đầu file.
- **Length** là số byte muốn xử lý kể từ offset.
- **End offset** là vị trí ngay sau vùng dữ liệu, thường tính bằng offset + length.
- **Channel position** là con trỏ hiện tại của FileChannel, được dùng bởi các thao tác read/write không truyền vị trí tường minh.
- **ByteBuffer position/limit** xác định vùng dữ liệu hiện đang được phép đọc hoặc ghi trong buffer.

Một vùng file thường được biểu diễn theo khoảng nửa mở:

~~~text
[offset, offset + length)
~~~

Ví dụ, offset 100 và length 20 có nghĩa là xử lý các byte từ vị trí 100 đến 119. Byte ở vị trí 120 nằm ngoài vùng đó.

| Khái niệm | Đơn vị | Vai trò |
|---|---|---|
| File offset | Byte, kiểu long | Vị trí bắt đầu trong file |
| Length/count | Byte, thường là long hoặc int tùy API | Số byte tối đa cần xử lý |
| FileChannel.position() | Byte | Vị trí hiện tại của channel |
| ByteBuffer.position() | Phần tử byte trong buffer | Vị trí đọc/ghi tiếp theo trong buffer |
| ByteBuffer.limit() | Phần tử byte trong buffer | Ranh giới cuối của vùng có thể đọc/ghi |
| ByteBuffer.remaining() | Byte | Số byte còn lại giữa position và limit |

Không đồng nhất offset của file với position của ByteBuffer. Chẳng hạn, file offset có thể là 4.000.000 trong khi ByteBuffer.position() mới là 0. Hai giá trị thuộc hai không gian vị trí khác nhau.

## 2. Hai nhóm thao tác đọc và ghi

FileChannel cung cấp hai kiểu thao tác chính.

### 2.1. Relative I/O: dùng channel position hiện tại

~~~java
int bytesRead = channel.read(buffer);
int bytesWritten = channel.write(buffer);
~~~

Các thao tác này bắt đầu tại channel.position(). Sau khi đọc hoặc ghi, vị trí channel tiến lên số byte thực tế đã xử lý.

Có thể đặt vị trí bằng:

~~~java
channel.position(1024);
~~~

Sau đó, read hoặc write tiếp theo bắt đầu từ byte 1024. Đây là cách làm việc tuần tự hoặc truy cập ngẫu nhiên khi chỉ có một luồng điều khiển vị trí channel.

### 2.2. Positional I/O: truyền offset trực tiếp

~~~java
int bytesRead = channel.read(buffer, fileOffset);
int bytesWritten = channel.write(buffer, fileOffset);
~~~

Hai phương thức này bắt đầu tại fileOffset và không thay đổi channel.position(). Đây là lựa chọn phù hợp khi cần đọc hoặc ghi một vùng file xác định mà không ảnh hưởng vị trí tuần tự hiện tại.

Ví dụ:

~~~java
long originalPosition = channel.position();

ByteBuffer header = ByteBuffer.allocate(16);
int count = channel.read(header, 0);

System.out.println("Bytes read: " + count);
System.out.println("Channel position: " + channel.position());
System.out.println("Unchanged: " + (channel.position() == originalPosition));
~~~

Nếu channel đang ở vị trí 500, đọc tại offset 0 vẫn không chuyển channel về vị trí 16. Các thao tác positional không dùng hoặc cập nhật channel position.

### 2.3. Đừng nhầm offset/length của scattering và gathering I/O

FileChannel còn có các overload nhận mảng ByteBuffer:

~~~java
long count = channel.read(buffers, 1, 2);
long written = channel.write(buffers, 1, 2);
~~~

Ở đây offset = 1 là chỉ số buffer bắt đầu trong mảng, còn length = 2 là số buffer tối đa được xử lý. Các thao tác này dùng channel.position() hiện tại và cập nhật vị trí đó theo tổng số byte thực tế đã đọc/ghi. Chúng không chỉ định vị trí byte trong file. Cách truyền offset/length này khác với read(buffer, fileOffset) và write(buffer, fileOffset).

### 2.4. Chọn kiểu thao tác nào?

| Tình huống | Cách phù hợp |
|---|---|
| Đọc file từ đầu đến cuối | Relative read/write |
| Đọc header tại một offset cố định | Positional read |
| Cập nhật một vùng byte mà không thay đổi vị trí tuần tự | Positional write |
| Nhiều tác vụ đọc các vùng khác nhau của cùng file | Positional I/O |
| Sao chép một đoạn file sang channel khác | transferTo hoặc transferFrom |
| Cần xử lý file theo thứ tự, một luồng | Relative I/O hoặc positional I/O với offset tự quản lý |

FileChannel an toàn khi được nhiều thread sử dụng, nhưng các thao tác phụ thuộc channel position hoặc làm thay đổi kích thước file được điều phối để không chạy đồng thời theo cách gây xung đột. Các thao tác có offset tường minh có thể tiến hành đồng thời tùy implementation. Dù vậy, nếu nhiều tác vụ ghi chồng lên cùng vùng byte, ứng dụng vẫn phải tự thiết kế quy tắc phối hợp.

## 3. ByteBuffer position, limit và flip

Một lỗi phổ biến là nhầm vị trí trong buffer với vị trí trong file. ByteBuffer có trạng thái riêng:

- capacity: sức chứa tối đa của buffer.
- position: vị trí mà thao tác get/put tiếp theo sử dụng.
- limit: ranh giới mà thao tác get/put không được vượt qua.
- remaining: limit trừ position.

Khi ghi dữ liệu vào buffer để gửi xuống file, buffer thường ở chế độ ghi dữ liệu. Sau khi put xong, gọi flip() để chuyển sang chế độ đọc dữ liệu từ buffer:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(8);
buffer.put(new byte[] { 10, 20, 30, 40 });

System.out.println(buffer.position()); // 4
System.out.println(buffer.limit());    // 8

buffer.flip();

System.out.println(buffer.position()); // 0
System.out.println(buffer.limit());    // 4
System.out.println(buffer.remaining()); // 4
~~~

Khi FileChannel ghi buffer, nó đọc các byte từ buffer.position() đến buffer.limit(). Sau mỗi lần ghi, buffer.position() tăng theo số byte thực tế đã ghi.

Khi FileChannel đọc vào buffer, nó ghi byte tại buffer.position() rồi tăng position. Sau khi đọc xong, gọi flip() để đọc dữ liệu vừa nhận:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(32);

int count = channel.read(buffer, 0);

buffer.flip();
while (buffer.hasRemaining()) {
    System.out.print(buffer.get() + " ");
}
~~~

Nếu cần tái sử dụng buffer để đọc lần tiếp theo, clear() đặt position về 0 và limit về capacity. clear() không xóa dữ liệu trong bộ nhớ; nó chỉ đặt lại trạng thái buffer.

## 4. Thực hành ghi và đọc một vùng byte theo offset

Tạo file FileChannelRangeDemo.java. Ví dụ sau ghi một prefix và nội dung UTF-8 vào file, sau đó đọc lại đúng vùng byte của nội dung.

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FileChannelRangeDemo {

    static void writeFully(
            FileChannel channel,
            long offset,
            ByteBuffer source
    ) throws IOException {
        if (offset < 0) {
            throw new IllegalArgumentException("offset must be non-negative");
        }

        Math.addExact(offset, (long) source.remaining());

        long filePosition = offset;

        while (source.hasRemaining()) {
            int written = channel.write(source, filePosition);

            if (written == 0) {
                Thread.onSpinWait();
                continue;
            }

            filePosition += written;
        }
    }

    static ByteBuffer readExactly(
            FileChannel channel,
            long offset,
            int length
    ) throws IOException {
        if (offset < 0 || length < 0) {
            throw new IllegalArgumentException("offset and length must be non-negative");
        }

        if (length == 0) {
            return ByteBuffer.allocate(0);
        }

        long end = Math.addExact(offset, (long) length);
        if (end > channel.size()) {
            throw new EOFException("Requested range exceeds current file size");
        }

        ByteBuffer destination = ByteBuffer.allocate(length);
        long filePosition = offset;

        while (destination.hasRemaining()) {
            int read = channel.read(destination, filePosition);

            if (read < 0) {
                throw new EOFException("File ended before the requested range was read");
            }

            if (read == 0) {
                Thread.onSpinWait();
                continue;
            }

            filePosition += read;
        }

        destination.flip();
        return destination;
    }

    public static void main(String[] args) throws IOException {
        Path path = Path.of("range-demo.bin");

        byte[] prefix = "HEADER|".getBytes(StandardCharsets.UTF_8);
        byte[] message = "Xin chào Java 26".getBytes(StandardCharsets.UTF_8);

        long messageOffset = prefix.length;
        int messageLength = message.length;

        try (FileChannel channel = FileChannel.open(
                path,
                StandardOpenOption.CREATE,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE,
                StandardOpenOption.TRUNCATE_EXISTING
        )) {
            writeFully(channel, 0, ByteBuffer.wrap(prefix));
            writeFully(
                channel,
                messageOffset,
                ByteBuffer.wrap(message)
            );

            System.out.println("File size: " + channel.size());
            System.out.println("Channel position: " + channel.position());

            ByteBuffer result = readExactly(
                channel,
                messageOffset,
                messageLength
            );

            byte[] bytes = new byte[result.remaining()];
            result.get(bytes);

            System.out.println(
                new String(bytes, StandardCharsets.UTF_8)
            );
        }
    }
}
~~~

Biên dịch và chạy:

~~~sh
javac FileChannelRangeDemo.java
java FileChannelRangeDemo
~~~

Kết quả mong đợi:

~~~text
File size: 24
Channel position: 0
Xin chào Java 26
~~~

Độ dài file ở ví dụ được tính theo byte UTF-8. Chuỗi tiếng Việt có ký tự có thể chiếm nhiều byte, do đó không dùng String.length() để tính offset hoặc length của file. Hãy chuyển chuỗi thành byte[] bằng charset cụ thể rồi lấy độ dài mảng byte.

Các helper trong ví dụ có hai trách nhiệm:

- writeFully tiếp tục ghi cho đến khi ByteBuffer hết dữ liệu. Offset file tăng theo số byte thực tế đã ghi.
- readExactly tiếp tục đọc đến khi nhận đủ số byte yêu cầu. Nếu file ngắn hơn vùng được yêu cầu, helper báo EOFException thay vì âm thầm trả về dữ liệu thiếu.

FileChannel là channel dạng blocking. Với buffer còn dữ liệu, một lần gọi vẫn có thể xử lý ít hơn số byte yêu cầu; vì vậy vòng lặp kiểm tra hasRemaining là cần thiết. Nhánh xử lý kết quả 0 tránh giả định rằng mọi lời gọi đều tiến triển ngay trong một lần gọi.

## 5. Offset và length với dữ liệu UTF-8

Offset và length của FileChannel luôn là byte offset. Chúng không đại diện cho vị trí ký tự trong String.

Ví dụ:

~~~java
String text = "AéViệt";
byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);

System.out.println(text.length());
System.out.println(utf8.length);
~~~

Hai giá trị có thể khác nhau vì ký tự ngoài ASCII thường được mã hóa thành nhiều byte trong UTF-8. Một ứng dụng cần đọc một đoạn văn bản từ file phải biết encoding và ranh giới mã hóa. Không nên tùy tiện cắt byte ở giữa một chuỗi mã hóa nhiều byte rồi giải mã như một chuỗi độc lập.

Với file văn bản có cấu trúc, offset byte nên được xác định từ định dạng file hoặc từ quá trình mã hóa. Nếu chỉ muốn đọc theo dòng hoặc ký tự, API cấp cao như Files.newBufferedReader phù hợp hơn; FileChannel hữu ích khi định dạng hoặc yêu cầu hiệu năng đòi hỏi truy cập theo byte.

## 6. Đọc đúng length và xử lý EOF

Một lời gọi read không có nghĩa là buffer sẽ được lấp đầy. Giá trị trả về phải được kiểm tra:

| Kết quả | Ý nghĩa |
|---|---|
| Số dương | Số byte thực tế đã đọc |
| 0 | Không có byte được đọc trong lần gọi đó |
| -1 | Đã đến cuối file đối với vị trí đọc |

Với positional read, nếu offset lớn hơn hoặc bằng kích thước file thì phương thức trả về -1. Nếu chỉ còn ít byte hơn length mong muốn, lời gọi có thể chỉ trả về số byte còn lại.

Có hai chính sách đọc phổ biến:

- **Read at most length bytes**: đọc tối đa length byte, chấp nhận kết quả ngắn khi gặp EOF.
- **Read exactly length bytes**: yêu cầu đủ số byte; nếu EOF xuất hiện trước khi đủ dữ liệu thì báo lỗi.

Ví dụ helper readExactly ở trên triển khai chính sách thứ hai. Khi đọc file có thể bị tiến trình khác thay đổi đồng thời, việc kiểm tra size trước chỉ là kiểm tra sớm; vòng lặp vẫn phải xử lý EOF vì kích thước file có thể thay đổi sau đó.

Đối với buffer lớn hơn giới hạn int hoặc file có kích thước hàng GB, không cấp phát một ByteBuffer khổng lồ chỉ để đọc một vùng. Hãy chia dữ liệu thành chunk có kích thước phù hợp, giữ offset hiện tại và lặp cho đến khi xử lý đủ length hoặc gặp EOF.

## 7. Ghi theo offset và cập nhật file

Positional write ghi từ offset được chỉ định và không thay đổi channel.position(). Kích thước file tăng nếu ghi vượt qua EOF.

~~~java
ByteBuffer update = ByteBuffer.wrap(
    "READY".getBytes(StandardCharsets.UTF_8)
);

writeFully(channel, 128, update);
~~~

Nếu file hiện tại ngắn hơn 128 byte, thao tác ghi có thể mở rộng file. Các byte nằm giữa EOF cũ và vị trí ghi mới có giá trị không xác định theo đặc tả; không dựa vào chúng để lưu dữ liệu có ý nghĩa. Nếu cần vùng đệm có nội dung xác định, hãy ghi rõ các byte đó.

Một số quy tắc quan trọng:

- Không dùng offset âm.
- Kiểm tra phép cộng offset + length để tránh tràn số.
- Kiểm tra quyền mở file: READ để đọc, WRITE để ghi.
- Ghi đủ buffer bằng vòng lặp khi yêu cầu toàn bộ dữ liệu.
- Tránh APPEND nếu cần ghi theo offset. Khi channel ở append mode, hành vi của positional write được đặc tả là không xác định.
- Chỉ dùng TRUNCATE_EXISTING khi thực sự muốn xóa nội dung cũ lúc mở file.

truncate(newSize) chỉ rút ngắn file khi newSize nhỏ hơn kích thước hiện tại. Nếu newSize lớn hơn hoặc bằng kích thước file, file không được mở rộng. Nếu channel position lớn hơn newSize sau khi truncate, position được đưa về newSize.

~~~java
try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.WRITE
)) {
    long oldSize = channel.size();
    channel.truncate(1024);
    System.out.println("Old size: " + oldSize);
    System.out.println("New size: " + channel.size());
}
~~~

truncate là thao tác làm mất dữ liệu ở phần cuối file. Không gọi nó trong luồng cập nhật nếu chưa xác định rõ kích thước mới và hậu quả.

## 8. Sao chép một vùng file với transferTo

Khi cần chuyển một vùng byte từ FileChannel sang WritableByteChannel khác, transferTo có thể tận dụng tối ưu của hệ điều hành và filesystem.

~~~java
long transferred = source.transferTo(
    sourceOffset,
    requestedLength,
    target
);
~~~

Các tham số:

- sourceOffset: offset bắt đầu trong file nguồn.
- requestedLength: số byte tối đa muốn chuyển.
- target: channel đích đang mở để ghi.

transferTo không thay đổi channel position của nguồn. Phương thức có thể chuyển ít byte hơn requestedLength hoặc trả về 0, tùy trạng thái channel và nền tảng. Vì vậy, khi cần chuyển đủ một vùng, phải lặp và cập nhật offset cũng như số byte còn lại:

~~~java
static long transferFully(
        FileChannel source,
        long offset,
        long length,
        java.nio.channels.WritableByteChannel target
) throws IOException {
    if (offset < 0 || length < 0) {
        throw new IllegalArgumentException("offset and length must be non-negative");
    }

    Math.addExact(offset, length);

    long position = offset;
    long remaining = length;
    long total = 0;

    while (remaining > 0) {
        long count = source.transferTo(position, remaining, target);

        if (count == 0) {
            break;
        }

        position += count;
        remaining -= count;
        total += count;
    }

    return total;
}
~~~

Hàm trả về số byte thực tế đã chuyển. Nếu kết quả nhỏ hơn length, caller phải xác định nguyên nhân: EOF ở nguồn, target không nhận thêm dữ liệu hoặc điều kiện I/O của nền tảng. Không được giả định transferTo luôn chuyển hết dữ liệu trong một lần gọi.

## 9. Quyền sở hữu và đóng FileChannel

FileChannel là tài nguyên hệ thống, nên phải có một nơi chịu trách nhiệm đóng nó. Mẫu thông dụng là thành phần mở channel sở hữu vòng đời channel và dùng try-with-resources:

~~~java
Path path = Path.of("data.bin");

try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.READ
)) {
    ByteBuffer buffer = ByteBuffer.allocate(4096);
    int count = channel.read(buffer, 0);
    System.out.println("Read: " + count);
}
~~~

Khi rời khỏi khối try, channel được đóng kể cả khi có exception. Không dựa vào garbage collection để giải phóng file descriptor; thời điểm GC chạy không xác định và không phải cơ chế quản lý tài nguyên.

### 9.1. Quy ước owner và borrower

Một quy ước dễ duy trì trong codebase:

- **Owner** là thành phần gọi FileChannel.open và chịu trách nhiệm đóng channel.
- **Borrower** là hàm nhận FileChannel từ bên ngoài để thực hiện công việc; hàm đó không tự đóng channel nếu hợp đồng API không nói rõ quyền sở hữu được chuyển giao.
- Khi owner truyền channel vào nhiều hàm, các hàm đó chỉ thao tác trong thời gian channel còn mở.
- Không giữ tham chiếu channel để dùng sau khi owner đã thoát khỏi try-with-resources.

Ví dụ hàm chỉ mượn channel:

~~~java
static long readHeader(
        FileChannel channel,
        ByteBuffer header
) throws IOException {
    return channel.read(header, 0);
}
~~~

Hàm này không đóng channel. Caller vẫn sở hữu và quản lý vòng đời:

~~~java
try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.READ
)) {
    ByteBuffer header = ByteBuffer.allocate(16);
    readHeader(channel, header);
}
~~~

Java không có hệ thống kiểu ownership để compiler tự ngăn mọi trường hợp đóng nhầm tài nguyên. Vì vậy, quy ước API và phạm vi try-with-resources cần được thiết kế rõ ràng.

### 9.2. Wrapper stream cũng có thể đóng channel

Channels.newInputStream(channel) và Channels.newOutputStream(channel) tạo stream dựa trên channel. Khi đóng stream wrapper, channel nền cũng bị đóng.

~~~java
FileChannel channel = FileChannel.open(
    path,
    StandardOpenOption.READ
);

try (var input = java.nio.channels.Channels.newInputStream(channel)) {
    input.transferTo(System.out);
}

// Channel đã bị đóng cùng với input stream.
System.out.println(channel.isOpen()); // false
~~~

Không nên đặt cả wrapper và channel vào hai phạm vi try-with-resources độc lập nếu không thiết kế rõ quan hệ sở hữu. Đóng wrapper sẽ đóng channel; việc đóng channel thêm lần nữa không gây hại trong trường hợp thông thường, nhưng hai owner độc lập dễ làm code khó hiểu và dễ đóng tài nguyên quá sớm.

Nếu muốn chuyển đổi giữa byte channel và stream, hãy xác định rõ wrapper nào chịu trách nhiệm đóng channel. Đọc Javadoc của phương thức Channels tương ứng vì hành vi đóng của từng adapter được mô tả cụ thể.

### 9.3. Channel lấy từ stream hoặc RandomAccessFile

FileChannel có thể được lấy từ FileInputStream, FileOutputStream hoặc RandomAccessFile thông qua getChannel(). Khi đó channel và đối tượng nguồn cùng chia sẻ trạng thái file. Thay đổi vị trí hoặc nội dung qua một bên được phản ánh ở bên kia; đóng channel cũng đóng đối tượng nguồn.

Đối với code mới, thường nên mở trực tiếp bằng FileChannel.open(Path, OpenOption...) để quyền mở file và vòng đời tài nguyên rõ ràng. Chỉ dùng getChannel() khi cần tích hợp với một stream hoặc RandomAccessFile đang được quản lý theo hợp đồng có sẵn.

## 10. Dùng FileChannel sau khi tải file bằng HttpClient

Trong ứng dụng HTTP Client, BodyHandlers.ofFile(Path) có thể ghi response body trực tiếp ra file. Sau khi request hoàn tất thành công, có thể mở FileChannel để đọc header hoặc một vùng byte cụ thể mà không nạp toàn bộ file vào heap.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Duration;

public class DownloadAndInspect {
    public static void main(String[] args) throws Exception {
        URI uri = URI.create("https://example.com/archive.bin");
        Path destination = Path.of("archive.bin");

        HttpRequest request = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofMinutes(2))
            .GET()
            .build();

        HttpResponse<Path> response;

        try (HttpClient client = HttpClient.newHttpClient()) {
            response = client.send(
                request,
                HttpResponse.BodyHandlers.ofFile(destination)
            );
        }

        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new IllegalStateException(
                "Unexpected HTTP status: " + response.statusCode()
            );
        }

        try (FileChannel channel = FileChannel.open(
                response.body(),
                StandardOpenOption.READ
        )) {
            ByteBuffer header = ByteBuffer.allocate(32);
            int count = channel.read(header, 0);

            System.out.println("Downloaded bytes: " + channel.size());
            System.out.println("Header bytes read: " + count);
        }
    }
}
~~~

BodyHandlers.ofFile quản lý việc ghi response body theo cơ chế của HTTP Client. Chỉ mở FileChannel sau khi response hoàn tất để đọc file đã tải. Nếu cần tải xuống an toàn trong môi trường production, hãy bổ sung xác thực status, giới hạn dung lượng, xử lý file tạm và thay thế file đích theo chính sách của ứng dụng.

Ví dụ này không giả định HTTP/3. HTTP Client có thể dùng phiên bản HTTP được thương lượng hoặc chọn theo cấu hình. Việc dùng FileChannel để đọc file sau download độc lập với giao thức HTTP đã vận chuyển response.

## 11. Đồng thời và tính nhất quán

FileChannel an toàn cho việc sử dụng từ nhiều thread, nhưng cần phân biệt an toàn ở mức đối tượng với tính đúng đắn của thao tác dữ liệu.

- Relative read/write dùng chung channel position. Nếu nhiều thread cùng di chuyển vị trí hoặc đọc ghi tương đối, thứ tự thao tác có thể không phù hợp với logic ứng dụng.
- Positional read/write không thay đổi channel position, phù hợp hơn khi các tác vụ thao tác trên các vùng byte độc lập.
- Hai positional write vào cùng vùng vẫn có thể ghi đè dữ liệu của nhau; cần phân vùng công việc hoặc cơ chế đồng bộ ở tầng ứng dụng.
- FileChannel có thể được đóng từ thread khác. I/O đang chờ có thể kết thúc bằng exception liên quan đến đóng channel hoặc interrupt.
- FileChannel lock là khóa vùng file phục vụ phối hợp với process khác; không nên dùng nó như cơ chế khóa giữa các thread trong cùng JVM.

Nếu nhiều thread ghi vào các offset không giao nhau, positional I/O giúp tránh tranh chấp channel position. Tuy nhiên, nếu chúng cùng cập nhật metadata hoặc kích thước file, ứng dụng vẫn cần kiểm soát thứ tự và tính nguyên tử theo yêu cầu dữ liệu.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Đọc nhầm vùng dữ liệu | Dùng ByteBuffer.position như file offset | Truyền file offset riêng vào read/write positional |
| Buffer ghi ra file rỗng | Quên put dữ liệu hoặc buffer đã ở position cuối | Kiểm tra remaining và trạng thái buffer trước write |
| Đọc buffer thấy không có dữ liệu | Quên flip sau khi đọc từ channel | Gọi flip trước khi get dữ liệu |
| Chỉ ghi được một phần buffer | Một lần write không bảo đảm ghi hết | Lặp đến khi source.hasRemaining() là false |
| Kết quả đọc ngắn hơn length | EOF trước khi đủ byte hoặc file thay đổi | Chọn chính sách read-at-most hoặc read-exactly và kiểm tra kết quả |
| Dữ liệu tiếng Việt bị lỗi | Tính offset bằng số ký tự thay vì byte UTF-8 | Tính offset/length từ byte[] được mã hóa cùng charset |
| Channel position thay đổi ngoài dự kiến | Dùng relative I/O ở nơi cần positional I/O | Dùng read(buffer, offset) hoặc write(buffer, offset) |
| ClosedChannelException | Dùng channel sau khi owner hoặc wrapper đã đóng | Xem lại phạm vi try-with-resources và quy ước ownership |
| Ghi nhầm cuối file thay vì offset | Mở channel ở append mode | Không kết hợp APPEND với positional write |
| File bị mất phần cuối | Dùng TRUNCATE_EXISTING hoặc truncate sai kích thước | Kiểm tra open options và kích thước trước khi ghi |
| Chuyển file không đủ byte | transferTo có thể chuyển ít hơn count | Lặp, cập nhật position/remaining và kiểm tra EOF |
| Nhiều thread ghi đè nhau | Các vùng ghi giao nhau hoặc chia sẻ trạng thái không được điều phối | Phân vùng offset hoặc đồng bộ hóa ở tầng ứng dụng |

## 13. Checklist trước khi đưa FileChannel vào sử dụng

- [ ] Offset và length đều được hiểu là số byte.
- [ ] Đã xác định dùng relative I/O hay positional I/O.
- [ ] Không nhầm file offset với ByteBuffer.position().
- [ ] Buffer được flip trước khi đọc dữ liệu đã nhận.
- [ ] Vòng lặp xử lý partial read/write và EOF.
- [ ] Phép cộng offset + length được kiểm tra tràn số khi dữ liệu đến từ bên ngoài.
- [ ] Charset được xác định rõ khi xử lý văn bản.
- [ ] Open options chỉ cấp quyền cần thiết và không vô tình truncate hoặc append.
- [ ] Một owner rõ ràng chịu trách nhiệm đóng FileChannel.
- [ ] Wrapper stream được coi là có khả năng đóng channel nền.
- [ ] Các thao tác đồng thời không ghi chồng lên vùng dữ liệu ngoài ý muốn.
- [ ] Với transferTo/transferFrom, đã xử lý trường hợp chỉ chuyển một phần dữ liệu.
- [ ] Project dùng API FileChannel ổn định, không cần bật preview hoặc incubator.

## Tài liệu tham khảo

- [Java SE 26 FileChannel API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/FileChannel.html): vị trí file, positional I/O, kích thước, truncate, transfer, đồng thời và quan hệ với stream.
- [Java SE 26 ByteBuffer API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/ByteBuffer.html): capacity, position, limit, remaining, flip và trạng thái buffer.
- [Java SE 26 Channels API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/Channels.html): chuyển đổi giữa channel và stream, bao gồm quy tắc đóng tài nguyên.
- [Java SE 26 StandardOpenOption API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/StandardOpenOption.html): các tùy chọn mở file.
- [Java SE 26 HttpResponse.BodyHandlers API](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): ghi response body ra file bằng HTTP Client.

