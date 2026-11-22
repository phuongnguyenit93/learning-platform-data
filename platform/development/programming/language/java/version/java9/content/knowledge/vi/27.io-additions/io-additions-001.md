# Đọc dữ liệu còn lại bằng InputStream.readAllBytes()

Từ Java 9, **InputStream.readAllBytes()** cho phép đọc toàn bộ byte còn lại của một luồng vào một mảng byte duy nhất. Phương thức này hữu ích khi dữ liệu có kích thước vừa phải và chương trình cần xử lý toàn bộ nội dung trong bộ nhớ, chẳng hạn giải mã một nội dung UTF-8 hoặc phân tích một tệp nhỏ.

Điểm quan trọng là phương thức đọc **từ vị trí hiện tại đến khi gặp EOF (end of stream)**. Nó không quay lại đầu luồng và cũng không tự đóng luồng sau khi đọc.

## 1. Chữ ký và kết quả của readAllBytes()

Chữ ký phương thức:

~~~java
public byte[] readAllBytes() throws IOException
~~~

- Kiểu trả về là **byte[]**, chứa tất cả byte còn lại mà phương thức đọc được cho đến EOF.
- Phương thức có thể ném **IOException** nếu xảy ra lỗi I/O trong khi đọc.
- Nếu luồng đã ở EOF khi gọi, phương thức trả về một mảng byte rỗng (**new byte[0]**), không trả về null.
- Phương thức chặn (blocking) cho đến khi đọc hết dữ liệu còn lại và xác định được EOF, hoặc một ngoại lệ xảy ra.
- Phương thức không gọi close() và không đóng InputStream. Vòng đời của luồng vẫn thuộc trách nhiệm của bên gọi.

Ví dụ ngắn:

~~~java
InputStream input = ...;
byte[] data = input.readAllBytes();
~~~

Sau khi đọc thành công đến EOF, data chứa phần dữ liệu còn lại của luồng tại thời điểm bắt đầu đọc. Những byte đã được đọc trước đó bằng read() không xuất hiện lại trong mảng kết quả.

## 2. Đọc từ vị trí hiện tại, không phải luôn từ đầu

InputStream duy trì vị trí đọc hiện tại. Mỗi lần gọi read() thành công sẽ tiêu thụ một hoặc nhiều byte. readAllBytes() tiếp tục từ vị trí đó.

Ví dụ:

~~~java
byte[] prefix = new byte[4];
int count = input.read(prefix);

byte[] remaining = input.readAllBytes();
~~~

Nếu lần read() đầu đã lấy được bốn byte, remaining chỉ chứa các byte sau bốn byte đó. Không nên giả định read(byte[]) luôn lấp đầy toàn bộ buffer; phương thức trả về số byte thực tế đã đọc. Khi chuyển buffer thành String hoặc xử lý dữ liệu, phải dùng count để bỏ qua phần buffer chưa được ghi.

Nếu cần đọc lại từ đầu, phải dùng một nguồn có khả năng mở hoặc reset lại luồng. readAllBytes() không tự reset stream.

## 3. Ví dụ hoàn chỉnh: đọc phần còn lại và kiểm tra trạng thái đóng

Lưu chương trình dưới tên **ReadAllBytesDemo.java**. Ví dụ dùng Java 9 trở lên, đọc một phần trước bằng read(), sau đó dùng readAllBytes() để lấy phần còn lại. Một lớp nhỏ theo dõi close() giúp quan sát rằng readAllBytes() không tự đóng luồng.

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class ReadAllBytesDemo {

    private static final class TrackingInputStream extends ByteArrayInputStream {
        private boolean closed;

        TrackingInputStream(byte[] data) {
            super(data);
        }

        @Override
        public void close() {
            closed = true;
        }

        boolean isClosed() {
            return closed;
        }
    }

    public static void main(String[] args) throws IOException {
        byte[] source = "Java9readAllBytes".getBytes(StandardCharsets.UTF_8);
        TrackingInputStream input = new TrackingInputStream(source);

        byte[] prefixBuffer = new byte[5];
        int prefixLength = input.read(prefixBuffer);
        byte[] remaining = input.readAllBytes();

        System.out.println("prefix: " +
                new String(prefixBuffer, 0, prefixLength, StandardCharsets.UTF_8));
        System.out.println("remaining: " +
                new String(remaining, StandardCharsets.UTF_8));
        System.out.println("remaining length: " + remaining.length);
        System.out.println("closed by readAllBytes: " + input.isClosed());
        System.out.println("at EOF length: " + input.readAllBytes().length);

        input.close();
        System.out.println("closed after explicit close: " + input.isClosed());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 9 ReadAllBytesDemo.java
java ReadAllBytesDemo
~~~

Kết quả stdout:

~~~text
prefix: Java9
remaining: readAllBytes
remaining length: 12
closed by readAllBytes: false
at EOF length: 0
closed after explicit close: true
~~~

Giải thích:

- read() lấy năm byte đầu tiên, tương ứng với chuỗi Java9.
- readAllBytes() đọc phần còn lại là readAllBytes, gồm 12 byte ASCII.
- Luồng chưa bị đóng sau readAllBytes(); cờ closed vẫn là false.
- Lần gọi readAllBytes() tiếp theo diễn ra khi stream đã ở EOF, vì vậy trả về mảng rỗng có độ dài 0.
- Chỉ khi gọi close() tường minh thì ví dụ mới đánh dấu luồng đã đóng.

TrackingInputStream chỉ là công cụ minh họa để quan sát vòng đời. Với luồng tệp thực tế, nên dùng try-with-resources để đảm bảo đóng tài nguyên.

## 4. Đọc toàn bộ nội dung từ một tệp

Có thể dùng Files.newInputStream() để mở tệp và readAllBytes() để đọc phần byte của tệp:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;

public class ReadFileDemo {
    public static void main(String[] args) throws IOException {
        try (InputStream input =
                     Files.newInputStream(Paths.get("message.txt"))) {
            byte[] bytes = input.readAllBytes();
            String content = new String(bytes, StandardCharsets.UTF_8);
            System.out.println(content);
        }
    }
}
~~~

Trong ví dụ:

1. Files.newInputStream() mở tệp và trả về InputStream.
2. readAllBytes() đọc các byte còn lại của tệp.
3. String được tạo với StandardCharsets.UTF_8 để giải mã theo đúng bảng mã đã chọn.
4. Khi thoát khỏi khối try, try-with-resources gọi close() để giải phóng luồng tệp.

**Nên chỉ rõ charset khi chuyển byte[] thành String.** new String(bytes) dùng charset mặc định của môi trường, vì vậy cùng một byte array có thể được diễn giải khác nhau giữa các máy. Với dữ liệu UTF-8, dùng StandardCharsets.UTF_8.

## 5. readAllBytes() có blocking và tiêu thụ bộ nhớ

readAllBytes() phải xác định EOF trước khi hoàn tất. Vì vậy, thời gian hoàn thành phụ thuộc vào nguồn dữ liệu:

- Với ByteArrayInputStream hoặc một tệp hữu hạn, phương thức thường kết thúc khi đã đọc hết dữ liệu.
- Với stream từ mạng hoặc nguồn có thể tiếp tục gửi dữ liệu, phương thức có thể tiếp tục chờ cho đến khi phía gửi kết thúc luồng hoặc EOF được báo.
- Nếu nguồn không bao giờ kết thúc, lời gọi có thể chờ rất lâu hoặc không hoàn tất.

Phương thức lưu toàn bộ dữ liệu còn lại trong một byte array. Bộ nhớ cần thiết tăng theo kích thước dữ liệu. Nếu luồng quá lớn, việc tạo mảng có thể gây áp lực bộ nhớ hoặc dẫn đến OutOfMemoryError.

Do đó, readAllBytes() phù hợp với dữ liệu có kích thước vừa phải và đã biết hoặc được kiểm soát. Không nên dùng nó để gom toàn bộ một luồng lớn hoặc một kết nối dài hạn vào RAM.

## 6. Khi nào nên dùng readNBytes() hoặc transferTo()?

Java 9 cũng bổ sung các phương thức khác cho InputStream để xử lý các nhu cầu đọc khác nhau.

| Phương thức | Phiên bản | Mục đích | Khi phù hợp |
|---|---|---|---|
| readAllBytes() | Java 9 | Đọc toàn bộ byte còn lại vào một byte[] | Dữ liệu vừa phải, cần toàn bộ nội dung trong bộ nhớ |
| readNBytes(byte[], int, int) | Java 9 | Đọc tối đa len byte vào buffer có sẵn và trả về số byte thực tế | Chỉ cần một lượng byte giới hạn, muốn tái sử dụng buffer |
| readNBytes(int) | Java 11 | Đọc tối đa len byte và trả về byte[] mới | Cần lượng byte giới hạn với cú pháp ngắn |
| transferTo(OutputStream) | Java 9 | Chuyển toàn bộ byte còn lại trực tiếp sang OutputStream | Muốn sao chép hoặc chuyển tiếp dữ liệu mà không gom toàn bộ vào một byte[] |

Ví dụ dùng overload readNBytes() có từ Java 9:

~~~java
byte[] header = new byte[16];
int count = input.readNBytes(header, 0, header.length);
~~~

count là số byte thực tế được ghi vào buffer và có thể nhỏ hơn 16 nếu nguồn đạt EOF trước khi đủ số lượng yêu cầu. Chỉ xử lý các byte trong phạm vi từ 0 đến count - 1.

Từ Java 11 có thêm overload trả về byte[]:

~~~java
byte[] header = input.readNBytes(16);
~~~

Cả hai overload đều đọc tối đa số byte được yêu cầu; chúng không cố đọc thêm dữ liệu ngoài giới hạn đó.

Ví dụ chuyển dữ liệu sang một OutputStream:

~~~java
try (InputStream input = Files.newInputStream(Paths.get("source.bin"));
     OutputStream output = Files.newOutputStream(Paths.get("copy.bin"))) {
    long copied = input.transferTo(output);
    System.out.println("copied bytes: " + copied);
}
~~~

transferTo() ghi dữ liệu theo luồng sang đích, phù hợp hơn khi không cần giữ toàn bộ nội dung trong một byte array. Phương thức này cũng đọc đến EOF; nó không tự đóng input hoặc output. Các tài nguyên trong ví dụ được try-with-resources quản lý.

Nếu cần xử lý luồng rất lớn theo từng phần, có thể dùng vòng lặp với buffer để xử lý hoặc ghi từng đoạn, thay vì tích lũy toàn bộ dữ liệu trong bộ nhớ.

## 7. Lỗi thường gặp và cách tránh

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ readAllBytes() đọc lại từ đầu stream | Bỏ sót việc các byte trước đó đã bị tiêu thụ | Nhớ rằng phương thức đọc từ vị trí hiện tại |
| Nghĩ phương thức tự đóng InputStream | Rò rỉ tài nguyên nếu không có nơi khác đóng stream | Dùng try-with-resources hoặc gọi close() theo quyền sở hữu tài nguyên |
| Dùng readAllBytes() cho dữ liệu rất lớn | Tốn nhiều bộ nhớ, có nguy cơ OutOfMemoryError | Dùng transferTo(), readNBytes() hoặc xử lý theo buffer |
| Gọi readAllBytes() trên stream không có điểm EOF rõ ràng | Lời gọi có thể block trong thời gian dài | Dùng giao thức có giới hạn, readNBytes() hoặc cơ chế timeout phù hợp |
| Giả định read(byte[]) luôn đọc đủ buffer | Có thể xử lý nhầm các byte chưa được ghi | Dùng số byte thực tế mà read() trả về |
| Dùng charset mặc định để giải mã dữ liệu văn bản | Nội dung có thể sai giữa các môi trường | Chỉ rõ StandardCharsets.UTF_8 hoặc charset của dữ liệu |
| Nhầm mảng rỗng với null khi đã EOF | Kiểm tra trạng thái sai | Mảng trả về có độ dài 0 khi không còn byte |
| Dùng readNBytes(int) khi biên dịch với Java 9 | Overload này chưa có ở Java 9 | Dùng readNBytes(byte[], int, int) trong Java 9; overload nhận int có từ Java 11 |

## 8. Ghi nhớ

- InputStream.readAllBytes() được bổ sung từ Java 9 và trả về byte[] chứa tất cả byte còn lại.
- Phương thức đọc từ vị trí hiện tại đến EOF; không reset stream.
- Phương thức chặn cho đến khi đọc hết dữ liệu và xác định EOF hoặc phát sinh IOException.
- Nếu đã ở EOF, kết quả là byte array rỗng; không phải null.
- readAllBytes() không tự gọi close(); bên gọi chịu trách nhiệm quản lý vòng đời InputStream.
- Vì giữ toàn bộ dữ liệu trong bộ nhớ, chỉ dùng cho lượng dữ liệu phù hợp; với dữ liệu lớn, ưu tiên chuyển tiếp hoặc xử lý theo buffer.
- Java 9 có readNBytes(byte[], int, int); overload readNBytes(int) được bổ sung từ Java 11.
- Khi giải mã byte[] thành văn bản, hãy chỉ rõ charset.
