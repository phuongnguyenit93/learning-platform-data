# Kết thúc luồng và trường hợp đọc ít hơn yêu cầu

## 1. EOF là gì?

EOF (End Of File hoặc End Of Stream) là trạng thái luồng không còn dữ liệu để đọc. Trong Java, với `InputStream`, một lần gọi `read()` trả về:

- Giá trị từ `0` đến `255` nếu đọc được một byte. Kết quả là số nguyên để có thể dành riêng `-1` làm dấu hiệu kết thúc.
- `-1` nếu đã đến cuối luồng và không còn byte nào để trả về.

Với `read(byte[] buffer, int offset, int length)`, kết quả là số byte thực tế đã đọc. Nếu không đọc được byte nào vì đã đến EOF, phương thức trả về `-1`. Nếu `length == 0`, phương thức trả về `0` theo hợp đồng, kể cả khi luồng đã ở EOF.

EOF không phải là byte có giá trị `-1`. Byte có giá trị nhị phân `11111111` được trả về dưới dạng số nguyên `255`; `-1` là tín hiệu riêng để báo hết dữ liệu.

## 2. Một lần read có thể đọc ít hơn số byte yêu cầu

Lời gọi:

```java
int count = input.read(buffer, 0, buffer.length);
```

yêu cầu đọc tối đa `buffer.length` byte, không bảo đảm luôn lấp đầy toàn bộ buffer. Phương thức có thể trả về một số dương nhỏ hơn độ dài yêu cầu. Điều này bình thường với luồng file, luồng mạng, pipe và các nguồn dữ liệu có thể cung cấp dữ liệu theo từng phần.

Ví dụ, khi yêu cầu 5 byte, các lần đọc có thể trả về 2, 2 và 1. Chỉ lần đọc tiếp theo mới trả về `-1` khi nguồn đã hết dữ liệu.

Vì vậy, không được giả định một lần `read(byte[])` sẽ lấp đầy buffer. Nếu xử lý giao thức có độ dài cố định, dữ liệu nhị phân hoặc cấu trúc cần đủ số byte, phải tiếp tục đọc cho đến khi đủ hoặc xác nhận EOF.

## 3. Vòng lặp đọc đúng cách

Một cách phổ biến là giữ biến đếm số byte đã nhận và tiếp tục đọc vào phần còn trống của buffer:

```java
byte[] buffer = new byte[expectedLength];
int offset = 0;

while (offset < buffer.length) {
    int count = input.read(buffer, offset, buffer.length - offset);

    if (count == -1) {
        throw new EOFException("Not enough bytes");
    }

    offset += count;
}
```

Với hợp đồng chuẩn của `InputStream`, khi `length > 0`, một lần đọc sẽ cố gắng đọc ít nhất một byte, chờ dữ liệu, EOF hoặc ngoại lệ. Trường hợp `length == 0` mới trả về 0 ngay. Nếu làm việc với API non-blocking như `ReadableByteChannel`, quy tắc khác: thao tác đọc có thể trả về 0 khi hiện chưa có dữ liệu; khi đó cần xử lý trạng thái chờ theo mô hình channel/selector, không áp dụng vòng lặp InputStream một cách máy móc.

Nếu dùng Java 9 trở lên, `InputStream.readNBytes` có thể thay thế vòng lặp thông thường cho trường hợp muốn đọc tối đa một số byte xác định.

## 4. readNBytes: đọc cho đến đủ hoặc EOF

Java 9 bổ sung hai overload `InputStream.readNBytes`.

### readNBytes(byte[] b, int off, int len)

Phương thức đọc tối đa `len` byte vào vùng của mảng bắt đầu tại `off`. Nó tiếp tục đọc cho đến khi đã đọc đủ `len` byte, gặp EOF hoặc xảy ra lỗi I/O. Giá trị trả về là số byte thực tế đã đọc.

```java
byte[] buffer = new byte[8];
int count = input.readNBytes(buffer, 0, buffer.length);

if (count < buffer.length) {
    System.out.println("EOF before the buffer was filled");
}
```

Nếu nguồn chỉ còn 5 byte, phương thức trả về 5 và 3 vị trí còn lại của buffer không được xem là dữ liệu mới đọc. Luôn dùng giá trị `count` để xác định phần hợp lệ trong buffer.

### readNBytes(int len)

Overload này tạo và trả về một mảng chứa tối đa `len` byte:

```java
byte[] data = input.readNBytes(8);
System.out.println(data.length);
```

Nếu luồng còn ít hơn 8 byte trước EOF, mảng trả về ngắn hơn 8 byte. Nếu luồng đã ở EOF, kết quả là mảng rỗng. Nếu `len` âm, phương thức ném `IllegalArgumentException`.

Điểm quan trọng: `readNBytes` cố gắng đọc đủ số lượng yêu cầu, nhưng không thể tạo thêm dữ liệu khi nguồn kết thúc. Vì vậy, nó không tự ném `EOFException` chỉ vì đọc được ít hơn yêu cầu.

### Khi cần đúng chính xác số byte

Nếu định dạng dữ liệu yêu cầu đúng `expectedLength` byte, hãy kiểm tra số lượng trả về:

```java
byte[] data = input.readNBytes(expectedLength);

if (data.length != expectedLength) {
    throw new EOFException("Expected " + expectedLength
            + " bytes but received " + data.length);
}
```

Hoặc dùng `DataInputStream.readFully`, phương thức được thiết kế để lấp đầy buffer hoặc ném `EOFException` nếu không đủ dữ liệu:

```java
DataInputStream dataInput = new DataInputStream(input);
byte[] data = new byte[expectedLength];
dataInput.readFully(data);
```

Chọn cách thể hiện rõ hợp đồng: đọc tối đa và chấp nhận dữ liệu ngắn, hay yêu cầu đủ chính xác một kích thước.

## 5. readAllBytes và transferTo

Java 9 cũng bổ sung hai phương thức tiện ích để xử lý phần dữ liệu còn lại của luồng.

### readAllBytes

`readAllBytes()` đọc tất cả byte còn lại cho đến EOF và trả về một mảng:

```java
byte[] all = input.readAllBytes();
```

Phương thức thuận tiện khi nguồn nhỏ và kích thước có giới hạn. Nó không phù hợp với luồng rất lớn hoặc không có điểm kết thúc rõ ràng vì toàn bộ dữ liệu phải nằm trong bộ nhớ; việc cấp phát mảng quá lớn có thể gây `OutOfMemoryError`.

### transferTo

`transferTo(OutputStream out)` đọc các byte còn lại từ input và ghi trực tiếp sang output cho đến EOF. Phương thức trả về tổng số byte đã truyền:

```java
long transferred = input.transferTo(output);
```

Cách này tránh phải tự tạo một buffer và viết vòng lặp sao chép thông thường. Nó vẫn đọc cho đến EOF, nên có thể chờ vô hạn nếu nguồn không bao giờ kết thúc. Phương thức không đóng input hoặc output; quyền sở hữu và đóng stream vẫn thuộc về mã gọi.

### So sánh nhanh

| Phương thức | Kết quả | Khi nguồn kết thúc sớm |
|---|---|---|
| `read(byte[], off, len)` | Số byte của một lần đọc | Có thể trả số dương nhỏ hơn `len`; lần đọc sau mới trả `-1` |
| `readNBytes(b, off, len)` | Số byte đã đọc sau khi cố gắng lấp đầy vùng đích | Trả số byte nhỏ hơn `len` |
| `readNBytes(len)` | Mảng tối đa `len` byte | Trả mảng ngắn hơn `len` |
| `readAllBytes()` | Mảng chứa mọi byte còn lại | Trả mảng chứa phần còn lại, có thể rỗng |
| `transferTo(out)` | Tổng số byte đã truyền | Dừng khi EOF và trả tổng số byte |

Các phương thức trên không tự đóng stream. Nếu phương thức gọi sở hữu tài nguyên, hãy dùng try-with-resources hoặc cơ chế quản lý vòng đời phù hợp.

## 6. available() không phải cách kiểm tra EOF

`InputStream.available()` trả về ước lượng số byte có thể đọc (hoặc bỏ qua) mà không phải chờ. Nó không cho biết tổng số byte còn lại trong luồng và không phải cách đáng tin cậy để kiểm tra EOF.

Không nên viết:

```java
if (input.available() == 0) {
    // Không thể kết luận rằng đã đến EOF.
}
```

Với socket hoặc nguồn dữ liệu đang chờ, `available() == 0` thường chỉ có nghĩa hiện tại chưa có byte nào sẵn sàng để đọc mà không chặn. Dữ liệu có thể đến sau đó.

Cách xác định EOF đúng là thực hiện thao tác đọc và kiểm tra giá trị trả về `-1` (hoặc kiểm tra số byte trả về của `readNBytes` khi đang chờ một lượng dữ liệu cụ thể).

## 7. Ví dụ chạy được: partial reads, EOF và các API Java 9

Chương trình dưới đây dùng một wrapper chỉ cho phép tối đa 2 byte đi qua mỗi lần gọi `read`. Điều này giúp quan sát rõ một lần đọc có thể trả ít hơn yêu cầu. Các phương thức `readNBytes`, `readAllBytes` và `transferTo` sau đó được kiểm tra trên cùng dữ liệu.

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Arrays;

public class StreamEofDemo {
    private static final class ChunkedInputStream extends FilterInputStream {
        private final int maxChunk;

        ChunkedInputStream(InputStream input, int maxChunk) {
            super(input);
            this.maxChunk = maxChunk;
        }

        @Override
        public int read(byte[] buffer, int offset, int length)
                throws IOException {
            return super.read(buffer, offset, Math.min(length, maxChunk));
        }
    }

    public static void main(String[] args) throws IOException {
        byte[] source = {10, 20, 30, 40, 50};

        try (InputStream input = new ChunkedInputStream(
                new ByteArrayInputStream(source), 2)) {
            byte[] buffer = new byte[5];
            int first = input.read(buffer, 0, buffer.length);
            int second = input.read(buffer, 0, buffer.length);
            int third = input.read(buffer, 0, buffer.length);
            int eof = input.read(buffer, 0, buffer.length);
            System.out.println("read counts = "
                    + first + ", " + second + ", " + third);
            System.out.println("EOF result = " + eof);
        }

        try (InputStream input = new ChunkedInputStream(
                new ByteArrayInputStream(source), 2)) {
            byte[] buffer = new byte[7];
            int count = input.readNBytes(buffer, 0, buffer.length);
            System.out.println("readNBytes count = " + count);
            System.out.println("readNBytes data = "
                    + Arrays.toString(Arrays.copyOf(buffer, count)));
        }

        try (InputStream input = new ByteArrayInputStream(source)) {
            byte[] result = input.readNBytes(7);
            System.out.println("short readNBytes length = " + result.length);
            System.out.println("short readNBytes data = "
                    + Arrays.toString(result));
        }

        try (InputStream input = new ByteArrayInputStream(source)) {
            System.out.println("readAllBytes = "
                    + Arrays.toString(input.readAllBytes()));
        }

        try (InputStream input = new ByteArrayInputStream(source);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            long transferred = input.transferTo(output);
            System.out.println("transferred = " + transferred);
            System.out.println("transferTo data = "
                    + Arrays.toString(output.toByteArray()));
        }
    }
}
```

Lưu mã nguồn trong `StreamEofDemo.java`, biên dịch và chạy bằng Java 17 trở lên:

```bash
javac --release 17 -Xlint:all StreamEofDemo.java
java StreamEofDemo
```

Kết quả:

```text
read counts = 2, 2, 1
EOF result = -1
readNBytes count = 5
readNBytes data = [10, 20, 30, 40, 50]
short readNBytes length = 5
short readNBytes data = [10, 20, 30, 40, 50]
readAllBytes = [10, 20, 30, 40, 50]
transferred = 5
transferTo data = [10, 20, 30, 40, 50]
```

Ba lần đọc đầu trả về 2, 2 và 1 byte. Lần tiếp theo trả `-1`, xác nhận EOF. `readNBytes` tự lặp các lần đọc bên dưới để thu thập dữ liệu cho đến khi đủ 7 byte hoặc EOF; vì nguồn chỉ có 5 byte, nó trả về 5. `readAllBytes` và `transferTo` đều xử lý phần còn lại cho đến EOF.

## 8. Đọc text: phân biệt byte và ký tự

`InputStream` đọc byte. Khi nội dung là văn bản, một ký tự có thể chiếm nhiều byte trong charset như UTF-8. Không được coi số byte đã đọc là số ký tự đã nhận.

Dùng `InputStreamReader` với charset xác định để giải mã byte thành ký tự, sau đó dùng `Reader` hoặc `BufferedReader` để xử lý text:

```java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line);
    }
}
```

Với `Reader`, giá trị `-1` cũng báo EOF khi đọc ký tự hoặc mảng ký tự. Tuy nhiên, số lượng trả về được tính theo đơn vị ký tự UTF-16 (`char`), không phải số byte UTF-8 trên nguồn ban đầu.

## 9. Những lỗi thường gặp

- **Coi một lần read là đọc đủ buffer:** xử lý sai dữ liệu khi nguồn chỉ cung cấp một phần.
- **Coi 0 là EOF:** với `InputStream`, EOF được báo bằng `-1` khi yêu cầu độ dài lớn hơn 0; `0` có nghĩa yêu cầu độ dài bằng 0 theo hợp đồng chuẩn.
- **Dùng available() để suy ra kích thước hoặc EOF:** giá trị này chỉ là ước lượng số byte có thể đọc mà không chờ.
- **Dùng readAllBytes cho luồng lớn hoặc vô hạn:** toàn bộ dữ liệu phải được giữ trong một mảng.
- **Quên kiểm tra số byte thực tế từ readNBytes:** nếu cần đúng độ dài, phải so sánh số lượng nhận được với độ dài mong muốn.
- **Nhầm readNBytes với readFully:** `readNBytes` chấp nhận trả kết quả ngắn ở EOF; `DataInputStream.readFully` ném `EOFException` nếu không đủ.
- **Đóng stream quá sớm:** chỉ đóng sau khi đã hoàn tất mọi thao tác đọc; các phương thức tiện ích Java 9 không tự đóng stream.
- **Nhầm byte với ký tự:** dùng charset rõ ràng và Reader cho dữ liệu văn bản.

## 10. Checklist khi xử lý luồng

1. Nguồn có thể kết thúc trước khi đủ dữ liệu không?
2. Mã đã xử lý giá trị `-1` và kiểm tra số byte thực tế chưa?
3. Nếu cần một kích thước cố định, đã dùng vòng lặp, `readNBytes` kèm kiểm tra độ dài hoặc `readFully` chưa?
4. Có đang dùng `available()` sai mục đích không?
5. Nguồn có thể rất lớn hoặc không bao giờ kết thúc không? Nếu có, tránh `readAllBytes` và cân nhắc xử lý theo buffer.
6. Stream được đóng đúng nơi sở hữu tài nguyên chưa?
7. Nếu đọc văn bản, charset và ranh giới byte/ký tự đã được xử lý đúng chưa?

EOF là tín hiệu kết thúc luồng, còn một lần đọc ngắn hơn yêu cầu là hành vi bình thường. Hãy dựa vào giá trị trả về và hợp đồng của từng API để quyết định tiếp tục đọc, chấp nhận dữ liệu ngắn hay báo lỗi vì dữ liệu không đủ.