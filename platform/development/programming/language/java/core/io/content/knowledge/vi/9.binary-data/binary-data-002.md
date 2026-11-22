# DataInputStream và DataOutputStream: đọc, ghi dữ liệu nhị phân có kiểu trong Java

Khi một chương trình cần ghi nhiều giá trị như mã phiên bản, số lượng, cờ trạng thái hoặc số thực vào một tệp nhị phân, việc tự biến đổi từng giá trị thành byte rất dễ sai. Java cung cấp hai lớp **`DataOutputStream`** và **`DataInputStream`** để ghi/đọc các kiểu dữ liệu nguyên thủy theo một **định dạng nhị phân xác định**.

Hai lớp này hoạt động trên các **byte stream**, thường bọc một `OutputStream` hoặc `InputStream` có sẵn. Chúng hữu ích khi hai phía đã thống nhất **thứ tự trường, kiểu trường và cách biểu diễn byte**. Chúng **không tự biết cấu trúc bản ghi** và không tự tái tạo một đối tượng Java tùy ý.

## 1. Hai lớp làm nhiệm vụ gì?

- **`java.io.DataOutputStream`**: nhận giá trị Java như `int`, `long`, `boolean`, `double`, `char` và một số dạng chuỗi, sau đó ghi chúng xuống một `OutputStream` dưới dạng byte.
- **`java.io.DataInputStream`**: lấy byte từ `InputStream` và giải mã theo các phương thức `readInt()`, `readLong()`, `readBoolean()`, `readDouble()`, `readChar()`, `readUTF()`...
- **`DataOutput` và `DataInput`**: hai giao diện mà các lớp này triển khai, quy định hợp đồng cho việc ghi/đọc dữ liệu có kiểu.

Về quan hệ lớp:

~~~text
OutputStream
  └── FilterOutputStream
       └── DataOutputStream    (implements DataOutput)

InputStream
  └── FilterInputStream
       └── DataInputStream     (implements DataInput)
~~~

Một pipeline điển hình:

~~~text
                   GHI
giá trị Java --DataOutputStream--> BufferedOutputStream --> FileOutputStream --> file.bin
                   ĐỌC
giá trị Java <--DataInputStream--- BufferedInputStream <-- FileInputStream <-- file.bin
~~~

**Điểm quyết định:** `DataOutputStream` không thêm metadata tự mô tả kiểu dữ liệu. Nếu ghi lần lượt `int`, `boolean`, `long`, thì khi đọc phải biết để gọi `readInt()`, `readBoolean()`, `readLong()` **đúng thứ tự**. Đọc bằng kiểu hoặc thứ tự khác có thể sinh giá trị sai hoặc gặp hết dữ liệu.

## 2. Định dạng nhị phân của các kiểu nguyên thủy

Các phương thức `DataOutput` và `DataInput` có quy tắc biểu diễn cụ thể, không tùy tiện phụ thuộc vào charset hay byte order của CPU. Với các số có nhiều byte, dữ liệu được ghi theo thứ tự **big-endian** (byte có ý nghĩa lớn nhất trước).

| Ghi | Đọc đối ứng | Số byte | Ghi chú |
|---|---|---:|---|
| `writeBoolean(v)` | `readBoolean()` | 1 | `false` ghi byte 0; `true` ghi byte 1; đọc giá trị khác 0 là `true` |
| `writeByte(v)` | `readByte()` / `readUnsignedByte()` | 1 | Ghi 8 bit thấp; đọc có dấu hoặc không dấu |
| `writeShort(v)` | `readShort()` / `readUnsignedShort()` | 2 | Số nguyên 16 bit, big-endian |
| `writeChar(v)` | `readChar()` | 2 | Một **UTF-16 code unit** 16 bit, không phải chuỗi UTF-8 |
| `writeInt(v)` | `readInt()` | 4 | Số nguyên 32 bit, big-endian |
| `writeLong(v)` | `readLong()` | 8 | Số nguyên 64 bit, big-endian |
| `writeFloat(v)` | `readFloat()` | 4 | Theo các bit IEEE 754 được Java quy định |
| `writeDouble(v)` | `readDouble()` | 8 | Theo các bit IEEE 754 được Java quy định |
| `writeUTF(text)` | `readUTF()` | 2 + N | 2 byte độ dài không dấu, sau đó N byte **modified UTF-8** |

Ví dụ:

~~~text
writeInt(0x01020304)  -> 01 02 03 04
writeShort(300)       -> 01 2C
writeBoolean(true)    -> 01
~~~

Các byte hiển thị dưới dạng **hexadecimal (hệ 16)**. Ghi số `0x01020304` bằng `writeInt` không tạo bốn ký tự ASCII `"0102"`; nó tạo đúng **bốn byte** `01 02 03 04`. Nếu dùng `new String(bytes, UTF_8)` để cố xem dữ liệu nhị phân như văn bản, kết quả không phản ánh được cấu trúc của các trường.

Đối với một `int` âm, `writeInt` ghi biểu diễn 32 bit (two's complement) theo big-endian. `readInt` khôi phục lại cùng giá trị `int` nếu bốn byte gốc đầy đủ và chưa bị sửa.

### Đọc có dấu và không dấu

`writeByte(255)` ghi đúng byte `FF`, nhưng `readByte()` trả về `-1` vì diễn giải nó như số 8 bit có dấu. Nếu đặc tả bản ghi quy định đây là giá trị từ 0 đến 255, hãy dùng `readUnsignedByte()` để nhận `255`. Tương tự, `readUnsignedShort()` trả giá trị từ 0 đến 65535. Không được tự thay đổi phương thức đọc chỉ dựa trên “giá trị trông lạ”; cần tuân thủ **schema của dữ liệu**.

### `writeChar` không phải “ghi ký tự UTF-8”

`writeChar('A')` ghi hai byte `00 41`, trong khi mã hóa chuỗi `"A"` bằng UTF-8 cho một byte `41`. Một ký tự Unicode ngoài BMP được biểu diễn bằng **cặp surrogate** trong Java `String`, nên không thể giả định “một ký tự người dùng nhìn thấy = một lần `writeChar`”. Khi trao đổi văn bản nói chung, hãy xác định rõ encoding và quy tắc ghi độ dài thay vì dùng `writeChar` như một format chuỗi chung.

## 3. Quy tắc ghép stream và đóng tài nguyên

Thông thường code tự mở file bằng `Files.newOutputStream(path)`, rồi bọc `BufferedOutputStream` để giảm thao tác ghi xuống tầng dưới, và cuối cùng dùng `DataOutputStream` để viết giá trị có kiểu:

~~~java
try (DataOutputStream out = new DataOutputStream(
        new BufferedOutputStream(Files.newOutputStream(path)))) {
    out.writeInt(42);
    out.writeBoolean(true);
}
~~~

Đây là **đoạn minh họa**, cần import `java.io.*` và `java.nio.file.*`, có `Path path` và xử lý/khai báo `IOException`. Nếu code tự mở stream nguồn/đích, nó **sở hữu** tài nguyên và dùng `try-with-resources` cho lớp bọc ngoài cùng là thích hợp. `close()` ở decorator ngoài cùng đóng các tầng bên trong theo hợp đồng lớp JDK thông thường; `BufferedOutputStream` đẩy phần dữ liệu còn đệm xuống tầng sau khi đóng.

Đọc lại:

~~~java
try (DataInputStream in = new DataInputStream(
        new BufferedInputStream(Files.newInputStream(path)))) {
    int count = in.readInt();
    boolean enabled = in.readBoolean();
}
~~~

Cách đọc khớp **hai trường** đã ghi. Tuy nhiên, một helper chỉ **mượn** `InputStream` hoặc `OutputStream` từ caller không nên tùy ý đóng wrapper của nó, vì đóng wrapper có thể đóng luôn tài nguyên caller sở hữu. Hợp đồng API phải quy định rõ ai đóng và khi nào.

**Chú ý:** `DataOutputStream.flush()` chuyển yêu cầu flush xuống output bên trong; nhưng flush không có nghĩa dữ liệu đã được bảo đảm lưu bền vững trên ổ đĩa. Không gọi `close` chỉ để giải quyết nhu cầu flush trên stream được mượn.

## 4. Ví dụ Java 17 hoàn chỉnh: ghi và đọc cùng định dạng

Ví dụ sau dùng `ByteArrayOutputStream` và `ByteArrayInputStream` để dễ chạy độc lập, nhưng kiến trúc wrapper giống khi ghi/đọc tệp. Bản ghi gồm:

1. Một trường `int` **magic**: `0x01020304`, chiếm 4 byte.
2. Một trường `short` với giá trị `300`, chiếm 2 byte.
3. Một trường `boolean` là `true`, chiếm 1 byte.
4. Một trường `String` bằng `writeUTF`, có 2 byte tiền tố độ dài và phần văn bản theo **modified UTF-8**.

Lưu thành **`BinaryDataStreamsDemo.java`**:

~~~java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;

public class BinaryDataStreamsDemo {
    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream storage = new ByteArrayOutputStream();
        String message = "A" + '\0' + "é";

        try (DataOutputStream out = new DataOutputStream(
                new BufferedOutputStream(storage))) {
            out.writeInt(0x01020304);
            out.writeShort(300);
            out.writeBoolean(true);
            out.writeUTF(message);
        }

        byte[] encoded = storage.toByteArray();
        System.out.println("Total bytes: " + encoded.length);

        try (DataInputStream in = new DataInputStream(
                new BufferedInputStream(new ByteArrayInputStream(encoded)))) {
            int magic = in.readInt();
            int count = in.readUnsignedShort();
            boolean enabled = in.readBoolean();
            String decoded = in.readUTF();

            System.out.printf("Magic: 0x%08X%n", magic);
            System.out.println("Count: " + count);
            System.out.println("Enabled: " + enabled);
            System.out.println("Text equal: " + message.equals(decoded));
            System.out.println("Text length: " + decoded.length());
            System.out.println("Next byte: " + in.read());
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp mã nguồn:

~~~bash
javac --release 17 -encoding UTF-8 BinaryDataStreamsDemo.java
java BinaryDataStreamsDemo
~~~

Kết quả chuẩn:

~~~text
Total bytes: 14
Magic: 0x01020304
Count: 300
Enabled: true
Text equal: true
Text length: 3
Next byte: -1
~~~

Giải thích chính xác kích thước **14 byte**:

- `writeInt` ghi 4 byte `01 02 03 04`.
- `writeShort(300)` ghi 2 byte `01 2C`.
- `writeBoolean(true)` ghi 1 byte `01`.
- `writeUTF("A" + '\0' + "é")` ghi 2 byte độ dài **`00 05`**, theo sau là 5 byte `41 C0 80 C3 A9`.
- Tổng cộng **4 + 2 + 1 + 2 + 5 = 14 byte**.
- `DataInputStream.readUnsignedShort()` đọc lại trường 2 byte và trả `300`. `readUTF()` biết đọc đúng tiền tố độ dài và 5 byte của chính chuỗi đó.
- `decoded.length()` là `3`: ký tự `A`, ký tự NUL `\0` và ký tự `é`, mỗi ký tự là một UTF-16 code unit. Trong `System.out` không in trực tiếp chuỗi này vì ký tự NUL không thích hợp để quan sát trên terminal.
- Sau khi đọc đúng bốn trường, `in.read()` trả về `-1` vì không còn byte. Điều đó không có nghĩa `readInt()` tại EOF sẽ trả `-1`: `readInt()` **ném `EOFException`** khi không đủ bốn byte.

`ByteArrayOutputStream` giữ các byte đã ghi ngay cả khi wrapper `DataOutputStream` được đóng. Điều này là đặc tính của stream bộ nhớ; với file/socket, việc đóng wrapper vẫn có thể giải phóng hoặc kết thúc tài nguyên bên dưới.

## 5. `writeUTF` và `readUTF`: modified UTF-8 không phải UTF-8 thông thường

Tên `writeUTF` dễ dẫn đến kết luận sai. Phương thức này dùng **modified UTF-8**, có đặc điểm khác UTF-8 chuẩn:

- Ghi **hai byte big-endian** mô tả độ dài phần dữ liệu encoded phía sau, vì thế chiều dài encoded tối đa là **65535 byte** (không phải tối đa 65535 ký tự Java).
- Ký tự `U+0000` (NUL) được mã hóa thành **`C0 80`** thay vì byte `00` như UTF-8 chuẩn.
- Ký tự BMP khác trong các trường hợp thích hợp dùng một, hai hoặc ba byte. Các ký tự ngoài BMP được thể hiện bằng hai **UTF-16 surrogate code unit**, mỗi đơn vị được mã hóa riêng thành ba byte (tổng sáu byte), khác cơ chế bốn byte của UTF-8 chuẩn.
- `readUTF()` nhận định dạng đối ứng. Nếu đọc bằng decoder UTF-8 thông thường như `new String(payload, UTF_8)` thì không bảo đảm đúng, đặc biệt với NUL và ký tự ngoài BMP.
- `writeUTF` có thể ném `UTFDataFormatException` nếu độ dài modified UTF-8 cần ghi vượt giới hạn; `readUTF` có thể ném lỗi khi định dạng phần UTF không hợp lệ.

Vì thế, **`writeUTF`/`readUTF` phù hợp khi cả hai phía đều hiểu chính xác định dạng Java DataInput/DataOutput**. Chúng không phải lựa chọn mặc định khi cần sinh UTF-8 chuẩn để hệ thống khác đọc.

Bảng so sánh:

| Cách ghi | Cấu trúc byte | Phía đọc đúng |
|---|---|---|
| `out.writeUTF(text)` | 2 byte độ dài + modified UTF-8 | `in.readUTF()` |
| `out.write(text.getBytes(UTF_8))` | Chỉ có byte UTF-8, không có chiều dài | Cần biết ranh giới từ bên ngoài |
| `out.writeInt(bytes.length); out.write(bytes)` | 4 byte độ dài + byte UTF-8 chuẩn | `readInt()` rồi `readFully`, sau đó decode UTF-8 |
| `Files.writeString(path, text, UTF_8)` | Byte UTF-8 của văn bản | `Files.readString(path, UTF_8)` hoặc Reader phù hợp |

**Đừng thay `readUTF()` bằng `readLine()`.** `DataInputStream.readLine()` đã bị deprecated vì chuyển byte thành ký tự không đúng cho các charset phổ biến. Với dữ liệu văn bản theo dòng, hãy dùng `BufferedReader` với charset tường minh, ví dụ UTF-8.

## 6. Muốn lưu chuỗi UTF-8 chuẩn thì tự định nghĩa độ dài

Giả sử ứng dụng cần giao tiếp với một hệ thống ngoài Java và đặc tả của bạn yêu cầu **length-prefixed UTF-8**: bốn byte đầu là độ dài payload ở dạng `int` big-endian, tiếp theo là đúng N byte UTF-8.

Mã **minh họa phương thức**, dùng các import `java.io.*` và `java.nio.charset.StandardCharsets`:

~~~java
static void writeUtf8(DataOutputStream out, String text)
        throws IOException {
    byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
    out.writeInt(bytes.length);
    out.write(bytes);
}

static String readUtf8(DataInputStream in) throws IOException {
    int length = in.readInt();
    final int MAX_TEXT_BYTES = 1_048_576; // Giới hạn do ứng dụng đặt.
    if (length < 0 || length > MAX_TEXT_BYTES) {
        throw new IOException("Độ dài chuỗi không hợp lệ: " + length);
    }
    byte[] bytes = new byte[length];
    in.readFully(bytes);
    return new String(bytes, StandardCharsets.UTF_8);
}
~~~

Khác `writeUTF`, cách này chủ động quy định `UTF-8` chuẩn và tiền tố độ dài 4 byte. Khi đọc, **kiểm tra chiều dài trước khi cấp phát** để tránh nhận dữ liệu sai định dạng hoặc dữ liệu không đáng tin gây sử dụng bộ nhớ quá mức.

Trong ví dụ, `new String(bytes, UTF_8)` có thể **thay thế byte UTF-8 bị lỗi** theo chính sách decoder của constructor. Nếu giao thức yêu cầu từ chối dữ liệu không hợp lệ, dùng `CharsetDecoder` cùng `CodingErrorAction.REPORT` để báo lỗi rõ ràng. Ngoài ra, mã minh họa chưa phải hệ giao thức có đầy đủ versioning, checksum hoặc thông điệp xác nhận; những tính năng đó tùy yêu cầu ứng dụng.

### Vì sao phải dùng `readFully`?

Đoạn sau **không đủ an toàn** khi cần nhận đúng N byte:

~~~java
byte[] buffer = new byte[length];
in.read(buffer); // Sai nếu giả định lần đọc này luôn trả đủ length byte.
~~~

Một lời gọi `read(byte[])` có thể trả ít hơn số byte yêu cầu, nhất là khi đọc mạng. `DataInputStream.readFully(buffer)` lặp cho đến khi đọc đủ buffer hoặc ném `EOFException` nếu nguồn kết thúc trước. Với file, cũng nên dùng API đúng hợp đồng thay vì dựa trên may mắn.

Trong một bản ghi phức tạp, mọi trường có kích thước thay đổi (chuỗi, mảng, danh sách) cần có **quy tắc ranh giới**: tiền tố độ dài, dấu phân cách phù hợp hoặc số lượng phần tử biết trước. `DataInputStream` chỉ cung cấp công cụ đọc byte/kiểu; nó **không tự suy ra ranh giới bản ghi**.

## 7. Lỗi đọc sai thứ tự, sai kiểu và trường thiếu

Giả sử phía ghi:

~~~java
out.writeInt(1000);      // 4 byte
out.writeBoolean(true);  // 1 byte
out.writeLong(9000L);    // 8 byte
~~~

Phía đọc đúng:

~~~java
int number = in.readInt();
boolean flag = in.readBoolean();
long id = in.readLong();
~~~

Đây là **hai đoạn minh họa** với `out` là `DataOutputStream` và `in` là `DataInputStream`, không phải chương trình chạy riêng. Nếu phía đọc gọi `readBoolean()` đầu tiên, nó lấy byte có giá trị cao nhất của `int 1000`, không phải cờ đã ghi; vị trí các trường phía sau bị lệch. Kết quả có thể **trông hợp lệ nhưng sai**, hoặc phát sinh `EOFException`.

### Khi nào `EOFException` xảy ra?

- `readInt()` cần đủ 4 byte, `readLong()` cần đủ 8 byte, `readDouble()` cần đủ 8 byte. Khi không đủ byte, những phương thức này ném `EOFException` (một subtype của `IOException`).
- `readFully(byte[])` ném `EOFException` nếu nguồn kết thúc trước khi đầy mảng.
- `read()` được thừa kế theo hợp đồng byte stream trả `-1` khi hết luồng, vì nó chỉ yêu cầu **một byte** hoặc dấu EOF.
- `readUTF()` có thể ném `EOFException` nếu dữ liệu kết thúc giữa chừng hoặc `UTFDataFormatException` nếu encoded data không hợp lệ.

Dùng ngoại lệ một cách có ý nghĩa: **file bị cắt giữa một bản ghi** là dấu hiệu dữ liệu không đầy đủ. Đừng bắt `EOFException` rồi coi đó là “đọc bản ghi thành công” khi cấu trúc yêu cầu phải có đủ trường.

### `available()` không phải độ dài file hay số byte chắc chắn còn lại

`DataInputStream.available()` phản ánh số byte có thể đọc mà không chặn theo hợp đồng luồng bên dưới, không phải một cách đáng tin để dự đoán toàn bộ phần còn lại của mạng/file. Đừng dùng điều kiện `available() >= 4` như phương pháp chung để quyết định có đọc được một `int` hay không. Khi biết schema, hãy đọc bằng `readInt`/`readFully` và xử lý `EOFException` đúng cách.

## 8. Ghi file thật: vòng đời, ghi đè và buffer

Ví dụ code tự mở và sở hữu tệp nhị phân:

~~~java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class BinaryFileExample {
    static void write(Path file, int version, long timestamp)
            throws IOException {
        try (DataOutputStream out = new DataOutputStream(
                new BufferedOutputStream(Files.newOutputStream(file)))) {
            out.writeInt(version);
            out.writeLong(timestamp);
        }
    }

    static long readTimestamp(Path file) throws IOException {
        try (DataInputStream in = new DataInputStream(
                new BufferedInputStream(Files.newInputStream(file)))) {
            int version = in.readInt();
            if (version != 1) {
                throw new IOException("Unsupported version: " + version);
            }
            return in.readLong();
        }
    }
}
~~~

Đây là một **lớp tiện ích biên dịch được**, không có phương thức `main`. Caller có thể gọi `write(file, 1, someTimestamp)` rồi `readTimestamp(file)` để nhận lại `someTimestamp`.

Lưu ý:

1. `Files.newOutputStream(file)` theo tùy chọn mặc định có thể **tạo mới hoặc cắt ngắn tệp đã có**. Nếu muốn tránh ghi đè, chọn tùy chọn như `StandardOpenOption.CREATE_NEW` và xác định chiến lược xử lý lỗi.
2. `try-with-resources` giúp đóng stream do code **tự mở**, kể cả khi thao tác đọc/ghi ném lỗi. Không nhất thiết đóng từng wrapper bằng tay trong khối.
3. `BufferedOutputStream` có thể giữ byte trong buffer, nên cần flush/close đúng vòng đời. Đóng đúng lúc không tự bảo đảm dữ liệu đã được ghi bền vững trên thiết bị.
4. Kiểm tra trường **version** khi đọc giúp tránh áp dụng sai schema khi định dạng phát triển. Nếu file có nhiều bản ghi, phải thêm quy tắc đếm bản ghi/độ dài record hoặc xác định điểm kết thúc.
5. Với dữ liệu quan trọng, việc ghi bị gián đoạn có thể để lại tệp **chỉ có một phần byte**. Khi cần bảo toàn file cũ, có thể ghi ra tệp tạm và thay thế theo chiến lược cập nhật an toàn phù hợp hệ thống tệp.

## 9. Phân biệt với các API I/O khác

| Công cụ | Dùng khi nào? | Không tự làm được gì? |
|---|---|---|
| `DataInputStream/DataOutputStream` | Đọc/ghi primitive có kiểu theo nhị phân xác định | Không định nghĩa schema đối tượng, không tự tạo format tự mô tả |
| `InputStream/OutputStream` | Đọc/ghi byte nói chung | Không có `readInt`, `writeDouble` trực tiếp |
| `BufferedInputStream/BufferedOutputStream` | Thêm buffer để giảm tương tác với tầng nền | Không tự hiểu kiểu dữ liệu |
| `Reader/Writer` | Đọc/ghi ký tự và văn bản theo charset | Không phù hợp để tự ý diễn giải mọi byte nhị phân |
| `ObjectInputStream/ObjectOutputStream` | Java object serialization theo cơ chế riêng | Không cùng format với `DataInputStream`; không nên nhầm hai loại |
| `ByteBuffer` | Biểu diễn byte và đọc/ghi primitive trong buffer, cấu hình byte order | Không tự định nghĩa hoặc truyền một giao thức |
| `Files.copy` / `InputStream.transferTo` | Sao chép dữ liệu byte nguyên trạng | Không tự phân tích các trường primitive |

`DataInputStream` và `DataOutputStream` rất hữu ích cho format nhỏ, ổn định và được kiểm soát. Nhưng khi cần giao tiếp nhiều ngôn ngữ, thay đổi schema phức tạp hoặc tương thích lâu dài, nên cân nhắc định dạng/giao thức có đặc tả rõ ràng. Dù chọn công cụ nào, phải ghi chính xác **field order**, **field width**, **endianness**, **charset** và **version**.

## 10. Lỗi thường gặp

| Nhầm lẫn | Hậu quả | Cách đúng |
|---|---|---|
| Ghi `writeInt` rồi đọc `readShort` | Đọc thiếu byte, trường kế tiếp bị lệch | Đọc đúng thứ tự và đúng loại đã ghi |
| Tưởng số được ghi bằng chuỗi chữ số | Cố decode file nhị phân thành text, dữ liệu “khó đọc” | Hiểu primitive được ghi bằng byte nhị phân |
| Quên big-endian | Tự dựng parser phía khác đảo byte | Ghi vào đặc tả thứ tự byte lớn trước |
| Tưởng `writeUTF` là UTF-8 chuẩn | Bộ đọc bên ngoài nhận sai payload | Dùng `readUTF` đối ứng hoặc tự định nghĩa UTF-8 chuẩn |
| Đọc một lần `read(byte[])` rồi coi là đủ | Có thể mất phần byte còn lại | `readFully` hoặc vòng đọc đúng hợp đồng |
| Đọc length từ file rồi cấp phát không giới hạn | Có thể lỗi bộ nhớ hoặc bị dữ liệu giả mạo tác động | Xác thực length trước khi cấp phát |
| Dùng `available()` như tổng byte còn lại | Lỗi với các stream chỉ báo byte hiện đọc không chặn | Dùng schema và xử lý EOF rõ ràng |
| Không đóng wrapper do mình sở hữu | Mất byte trong buffer hoặc rò rỉ tài nguyên | `try-with-resources` tại tầng sở hữu |
| Đóng wrapper trên stream do caller cấp | Có thể đóng mất tài nguyên dùng chung | Quy định rõ ownership, helper chỉ mượn thì không đóng |
| Ghi vào file tồn tại mà không xét tùy chọn mở | File cũ có thể bị cắt ngắn | Chọn `StandardOpenOption` đúng nhu cầu |
| Nghĩ `DataInputStream` tự hiểu bất kỳ binary format | Giá trị đọc sai hoặc exception | Đọc theo schema do ứng dụng/giao thức định nghĩa |

## 11. Tự kiểm tra

**Câu 1.** Code ghi `writeInt(0x01020304)` thì tệp có bốn byte hex nào?

> **Đáp án:** `01 02 03 04` vì `DataOutputStream` dùng **big-endian** cho số nguyên nhiều byte.

**Câu 2.** Ghi `writeByte(255)`, đọc bằng `readByte()` được bao nhiêu? Nếu muốn 255 thì dùng gì?

> **Đáp án:** `readByte()` trả `-1` do diễn giải 8 bit có dấu. Dùng `readUnsignedByte()` để nhận `255`.

**Câu 3.** Tại sao `writeUTF("A" + '\0' + "é")` cần 7 byte, không phải 5 byte?

> **Đáp án:** Modified UTF-8 của chuỗi có **5 byte** (`41 C0 80 C3 A9`), cộng **2 byte tiền tố độ dài** thành **7 byte**.

**Câu 4.** `DataInputStream.readInt()` gặp EOF chỉ còn hai byte: trả `-1` hay ném ngoại lệ?

> **Đáp án:** Ném **`EOFException`** vì không đủ bốn byte để tạo `int`. `-1` là giá trị báo EOF của `InputStream.read()`.

**Câu 5.** Có nên đọc chuỗi dài N byte bằng một lần `in.read(bytes)` rồi mặc định đã đủ dữ liệu?

> **Đáp án:** Không. Một lần đọc có thể nhận ít hơn N byte. Dùng **`readFully(bytes)`** sau khi kiểm tra N hợp lệ hoặc vòng đọc bảo đảm đủ N byte.

**Câu 6.** Có thể dùng `readUTF()` để đọc file UTF-8 thông thường không?

> **Đáp án:** Không theo cách chung. `readUTF()` đòi **hai byte độ dài** và phần dữ liệu **modified UTF-8** theo `DataInput`. File text UTF-8 thông thường không mặc nhiên có cấu trúc đó.

**Câu 7.** Code mượn `OutputStream` của framework rồi tạo `DataOutputStream`. Có nên đóng `DataOutputStream` ở cuối helper?

> **Đáp án:** Chỉ khi hợp đồng giao quyền đóng stream cho helper. Nếu helper chỉ mượn, đóng wrapper có thể đóng luôn output framework. Caller/tầng sở hữu quyết định vòng đời.

## Ghi nhớ

**`DataOutputStream` mã hóa primitive thành byte; `DataInputStream` giải mã byte thành primitive.** Hai phía phải thống nhất thứ tự trường, chiều rộng trường, big-endian và định dạng chuỗi. Nhớ ba điểm đặc biệt: **`writeUTF/readUTF` dùng modified UTF-8 kèm 2 byte độ dài**, **`readFully` bảo đảm lấy đủ payload hoặc báo EOF**, và **việc đóng wrapper phải tuân theo quyền sở hữu stream**.

**Tài liệu tham khảo:** [Java SE 17 — `DataInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html), [`DataOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html), [`DataInput`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInput.html), [`DataOutput`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutput.html).