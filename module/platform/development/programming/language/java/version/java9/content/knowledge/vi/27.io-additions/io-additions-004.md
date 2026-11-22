# Giới hạn bộ nhớ khi đọc toàn bộ luồng

Khi làm việc với luồng byte, việc đọc toàn bộ dữ liệu vào một mảng có thể thuận tiện, nhưng cũng tạo ra giới hạn về bộ nhớ. Từ Java 9, `InputStream.readAllBytes()` cung cấp cách đọc đến EOF và trả về một `byte[]`. API này phù hợp với dữ liệu nhỏ hoặc có kích thước đã được kiểm soát. Với luồng lớn, không xác định kích thước hoặc có thể không kết thúc, cần chọn cách đọc theo từng phần.

Nguyên tắc chính: **không đưa toàn bộ nội dung vào heap nếu ứng dụng chỉ cần xử lý tuần tự từng phần**. Dùng buffer cố định, giới hạn kích thước đầu vào hoặc chuyển dữ liệu trực tiếp đến đích phù hợp.

## 1. readAllBytes đọc toàn bộ đến EOF

Từ Java 9, `InputStream` có phương thức:

~~~java
byte[] readAllBytes() throws IOException
~~~

Phương thức đọc dữ liệu từ vị trí hiện tại của stream cho đến khi gặp EOF, rồi trả về một mảng chứa tất cả byte đã đọc. Nếu stream đã ở EOF, kết quả là mảng rỗng.

Ví dụ:

~~~java
byte[] data;
try (InputStream input = Files.newInputStream(path)) {
    data = input.readAllBytes();
}
~~~

Cách viết này ngắn gọn và phù hợp khi:

- Nội dung nhỏ và có giới hạn rõ ràng.
- Ứng dụng thật sự cần toàn bộ byte cùng lúc.
- Bộ nhớ có thể đáp ứng kích thước tối đa dự kiến.
- Nguồn dữ liệu có điểm kết thúc đáng tin cậy.

`readAllBytes()` không tự đóng stream. Nếu phương thức đang sở hữu stream, hãy dùng try-with-resources để đóng nó sau khi xử lý.

## 2. Vì sao đọc toàn bộ có thể vượt bộ nhớ?

Một mảng byte phải chứa toàn bộ nội dung đã đọc. Nếu kích thước đầu vào là N byte, riêng mảng kết quả cần xấp xỉ N byte heap, chưa tính các đối tượng và dữ liệu trung gian khác.

Ví dụ, sau khi đọc:

~~~java
byte[] bytes = input.readAllBytes();
String text = new String(bytes, StandardCharsets.UTF_8);
~~~

Ứng dụng có thể giữ đồng thời mảng byte và String đã giải mã. Tùy cách biểu diễn chuỗi và runtime, bộ nhớ thực tế có thể lớn hơn đáng kể so với kích thước file. Nếu tiếp tục tạo bản sao, giải nén hoặc phân tích thành cấu trúc đối tượng, mức sử dụng heap còn tăng.

Khi dữ liệu lớn hơn vùng heap còn trống hoặc vượt giới hạn kích thước mảng mà runtime có thể cấp phát, ứng dụng có thể gặp `OutOfMemoryError`. Không nên xem việc tăng `-Xmx` là giải pháp mặc định: nguồn dữ liệu vẫn có thể lớn hơn heap, nhiều request có thể đọc đồng thời và mỗi request đều giữ một bản sao.

## 3. Luồng không có kích thước cố định hoặc không kết thúc

`readAllBytes()` phải chờ đến khi phát hiện EOF. Điều này có thể không phù hợp với:

- Kết nối mạng còn mở để tiếp tục nhận dữ liệu.
- Luồng thiết bị hoặc nguồn dữ liệu liên tục.
- Stream vô hạn do ứng dụng tạo.
- Giao thức có nhiều thông điệp trên cùng một kết nối mà EOF chỉ xuất hiện khi đóng kết nối.

Với những nguồn này, lời gọi có thể tiếp tục chờ và tích lũy dữ liệu. Nếu giao thức có ranh giới thông điệp, hãy đọc đúng số byte đã khai báo hoặc phân tích theo delimiter/framing. Không dùng EOF của toàn bộ kết nối làm ranh giới thông điệp nếu giao thức không quy định như vậy.

## 4. readNBytes khi chỉ cần một lượng dữ liệu giới hạn

Java 9 bổ sung:

~~~java
byte[] readNBytes(int len) throws IOException
~~~

Phương thức đọc tối đa `len` byte và trả về mảng có số byte thực tế đã đọc. Kết quả có thể ngắn hơn `len` nếu stream đến EOF sớm. Nếu `len` âm, phương thức ném `IllegalArgumentException`.

Ví dụ đọc một header có độ dài tối đa 16 byte:

~~~java
byte[] header = input.readNBytes(16);
if (header.length < 16) {
    throw new EOFException("Incomplete header");
}
~~~

Cách này giới hạn lượng dữ liệu được giữ trong mảng kết quả. Nó phù hợp với header, prefix hoặc một trường có kích thước đã biết. Không gọi `readNBytes(Integer.MAX_VALUE)` như một cách thay thế cho `readAllBytes`; vẫn cần chọn giới hạn thực tế.

Java 9 cũng có overload ghi vào mảng do caller cung cấp:

~~~java
int readNBytes(byte[] buffer, int offset, int len) throws IOException
~~~

Overload này ghi tối đa `len` byte vào vùng được chỉ định và trả về số byte đã đọc. Caller có thể tái sử dụng buffer thay vì cấp phát một mảng mới cho mỗi phần.

## 5. Xử lý theo buffer cố định

Khi cần xử lý nội dung lớn theo từng phần, dùng vòng lặp đọc buffer:

~~~java
byte[] buffer = new byte[8192];
int count;

while ((count = input.read(buffer)) != -1) {
    process(buffer, 0, count);
}
~~~

Mỗi lần đọc chỉ giữ một buffer có kích thước cố định. Nếu `process` xử lý xong phần hiện tại trước khi đọc phần tiếp theo, lượng bộ nhớ phụ có thể giữ gần như không đổi khi kích thước đầu vào tăng.

Một số điểm cần chú ý:

- Chỉ xử lý các byte trong đoạn `[0, count)`; phần còn lại của buffer có thể chứa dữ liệu cũ.
- `read` trả về `-1` khi gặp EOF.
- Không giả định một lần đọc sẽ lấp đầy toàn bộ buffer.
- Nếu cần giải mã văn bản theo từng chunk, dùng `CharsetDecoder` hoặc một reader có quản lý trạng thái để xử lý ký tự nhiều byte bị chia giữa hai lần đọc.
- Không chuyển từng chunk độc lập thành String nếu có thể có ký tự UTF-8 bị tách giữa các chunk.

## 6. transferTo để chuyển dữ liệu trực tiếp đến đích

Java 9 bổ sung:

~~~java
long transferTo(OutputStream out) throws IOException
~~~

Phương thức đọc byte từ InputStream hiện tại và ghi chúng vào OutputStream đích cho đến EOF. Nó trả về tổng số byte đã chuyển.

Ví dụ sao chép một file mà không tạo mảng chứa toàn bộ nội dung:

~~~java
try (InputStream input = Files.newInputStream(source);
     OutputStream output = Files.newOutputStream(target)) {

    long copied = input.transferTo(output);
}
~~~

Cách này phù hợp khi mục tiêu là chuyển dữ liệu từ nguồn sang file, socket hoặc một OutputStream khác. Việc truyền sử dụng bộ đệm nội bộ thay vì yêu cầu ứng dụng giữ toàn bộ nội dung trong một mảng.

`transferTo` không đóng InputStream hoặc OutputStream. Hai stream vẫn cần được quản lý theo quyền sở hữu; try-with-resources là lựa chọn phù hợp khi phương thức tạo và sở hữu cả hai.

Nếu đích là một cấu trúc giữ mọi byte trong RAM, chẳng hạn `ByteArrayOutputStream`, tổng bộ nhớ vẫn tăng theo kích thước dữ liệu. Muốn giới hạn heap, hãy chọn đích ghi ra file hoặc xử lý từng phần thay vì một container tích lũy toàn bộ nội dung.

## 7. Giới hạn dung lượng đầu vào một cách tường minh

Với dữ liệu không đáng tin cậy, chỉ dùng buffer cố định vẫn chưa đủ nếu ứng dụng tiếp tục ghi mọi byte ra đĩa hoặc tạo đối tượng từ chúng. Nên đặt giới hạn dung lượng theo yêu cầu nghiệp vụ.

Ví dụ hàm sao chép tối đa một số byte:

~~~java
static long copyWithLimit(
        InputStream input,
        OutputStream output,
        long maxBytes) throws IOException {

    if (maxBytes < 0) {
        throw new IllegalArgumentException("maxBytes must be non-negative");
    }

    byte[] buffer = new byte[8192];
    long total = 0;
    int count;

    while ((count = input.read(buffer)) != -1) {
        if (count > maxBytes - total) {
            throw new IOException("Input exceeds configured limit");
        }

        output.write(buffer, 0, count);
        total += count;
    }

    return total;
}
~~~

Trước mỗi lần ghi, hàm kiểm tra phần dữ liệu mới có vượt giới hạn còn lại hay không. Việc dùng `maxBytes - total` sau khi bảo đảm `total <= maxBytes` tránh phép cộng `total + count` có thể overflow.

Nếu giới hạn bị vượt, hàm ném IOException và đích có thể đã chứa một phần dữ liệu trước đó. Với file đích, ứng dụng có thể ghi vào file tạm rồi chỉ đổi tên sau khi hoàn tất; nếu thất bại, xóa file tạm để tránh sử dụng nội dung chưa đầy đủ.

## 8. Không dùng available() làm kích thước toàn bộ stream

`InputStream.available()` trả về ước lượng số byte có thể đọc hoặc bỏ qua mà không bị chặn bởi lần đọc tiếp theo. Nó **không** trả về tổng kích thước của stream và không đảm bảo số byte còn lại.

Không nên viết:

~~~java
byte[] data = new byte[input.available()];
input.read(data);
~~~

Cách này có thể đọc thiếu dữ liệu, tạo mảng có kích thước 0 dù vẫn còn byte sẽ đến sau, hoặc không xử lý đúng các lần đọc ngắn. Đặc biệt với stream mạng, `available()` thường không cho biết tổng nội dung của thông điệp.

Hãy dùng EOF, độ dài được giao thức cung cấp hoặc một giới hạn do ứng dụng quy định để xác định lượng dữ liệu cần đọc.

## 9. Ví dụ hoàn chỉnh với Java 17+

Tạo file **StreamMemoryLimitDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class StreamMemoryLimitDemo {
    static long copyWithLimit(
            InputStream input,
            OutputStream output,
            long maxBytes) throws IOException {

        if (maxBytes < 0) {
            throw new IllegalArgumentException("maxBytes must be non-negative");
        }

        byte[] buffer = new byte[8192];
        long total = 0;
        int count;

        while ((count = input.read(buffer)) != -1) {
            if (count > maxBytes - total) {
                throw new IOException("Input exceeds configured limit");
            }

            output.write(buffer, 0, count);
            total += count;
        }

        return total;
    }

    public static void main(String[] args) throws IOException {
        byte[] source = "Java streams".getBytes(StandardCharsets.UTF_8);

        try (InputStream input = new ByteArrayInputStream(source)) {
            byte[] all = input.readAllBytes();
            System.out.println("readAllBytes: "
                    + new String(all, StandardCharsets.UTF_8));
        }

        try (InputStream input = new ByteArrayInputStream(source)) {
            byte[] prefix = input.readNBytes(4);
            System.out.println("prefix: "
                    + new String(prefix, StandardCharsets.UTF_8));
        }

        Path target = Files.createTempFile("stream-copy-", ".bin");
        try {
            long transferred;
            try (InputStream input = new ByteArrayInputStream(source);
                 OutputStream output = Files.newOutputStream(target)) {
                transferred = input.transferTo(output);
            }
            System.out.println("transferred: " + transferred);
            System.out.println("file size: " + Files.size(target));

            long limited;
            try (InputStream input = new ByteArrayInputStream(source);
                 OutputStream output = Files.newOutputStream(target)) {
                limited = copyWithLimit(input, output, source.length);
            }
            System.out.println("limited copy: " + limited);
        } finally {
            Files.deleteIfExists(target);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac StreamMemoryLimitDemo.java
java StreamMemoryLimitDemo
~~~

Kết quả stdout:

~~~text
readAllBytes: Java streams
prefix: Java
transferred: 12
file size: 12
limited copy: 12
~~~

Ví dụ dùng dữ liệu nhỏ để minh họa từng API. Khi làm việc với file hoặc mạng lớn, thay ByteArrayInputStream bằng nguồn thực tế và chọn đích có khả năng tiếp nhận dữ liệu theo luồng.

## 10. Quản lý tài nguyên và lỗi giữa chừng

Đọc toàn bộ hay đọc theo buffer đều có thể phát sinh IOException. Với stream do phương thức mở, hãy đóng nó bằng try-with-resources. Nếu stream được caller truyền vào, cần tuân theo hợp đồng sở hữu: không tự đóng stream nếu caller vẫn chịu trách nhiệm sử dụng tiếp.

Khi sao chép dữ liệu, lỗi có thể xảy ra sau khi một phần đã được đọc hoặc ghi. Đừng giả định file đích đã hoàn chỉnh chỉ vì nó tồn tại. Với thao tác cần tính toàn vẹn, ghi ra file tạm, xác thực đủ nội dung rồi mới công bố file cuối.

Nếu stream đến từ mạng, timeout, hủy tác vụ và giới hạn kích thước cũng cần được thiết kế riêng. Giới hạn bộ nhớ không tự giải quyết việc một nguồn có thể gửi dữ liệu quá chậm hoặc không bao giờ kết thúc.

## 11. Chọn cách đọc phù hợp

| Nhu cầu | API/cách làm | Đặc điểm bộ nhớ |
|---|---|---|
| Nội dung nhỏ, cần tất cả byte | `readAllBytes()` | Tăng theo toàn bộ nội dung |
| Cần một prefix có giới hạn | `readNBytes(len)` | Bị giới hạn bởi len |
| Đọc vào buffer tái sử dụng | `read(buffer)` hoặc `readNBytes(buffer, off, len)` | Giữ buffer cố định |
| Chuyển toàn bộ nguồn sang đích | `transferTo(out)` | Không cần mảng chứa toàn bộ nguồn; phụ thuộc cách đích lưu dữ liệu |
| Sao chép có giới hạn dung lượng | Vòng lặp buffer + bộ đếm | Bộ nhớ phụ cố định, có giới hạn byte |
| Đọc toàn bộ file đã biết nhỏ | `Files.readAllBytes(path)` | Tạo mảng chứa toàn bộ file |

## 12. Lỗi thường gặp

**Dùng readAllBytes cho file hoặc response không giới hạn**

Toàn bộ byte được giữ trong một mảng. Dùng buffer hoặc chuyển trực tiếp đến file khi dữ liệu có thể lớn.

**Cho rằng readAllBytes tự đóng stream**

Phương thức đọc đến EOF nhưng không đóng stream. Quản lý tài nguyên bằng try-with-resources khi bạn sở hữu stream.

**Cho rằng readNBytes luôn trả đủ len byte**

Nếu EOF đến sớm, mảng kết quả ngắn hơn. Kiểm tra độ dài khi giao thức yêu cầu đủ header hoặc payload.

**Cho rằng transferTo luôn tiết kiệm bộ nhớ bất kể đích**

Nếu đích là một container tích lũy trong RAM, bộ nhớ vẫn tăng theo dữ liệu. Chọn OutputStream đích phù hợp.

**Dùng available() để cấp phát mảng chứa toàn bộ nội dung**

available chỉ là ước lượng byte có thể đọc không chặn, không phải tổng kích thước stream.

**Quên giới hạn kích thước đầu vào không đáng tin cậy**

Buffer cố định giới hạn bộ nhớ tạm nhưng không giới hạn tổng byte được xử lý. Dùng bộ đếm và giới hạn nghiệp vụ nếu cần chặn dữ liệu quá lớn.

**Giải mã từng chunk độc lập**

Một ký tự nhiều byte có thể bị chia giữa hai lần đọc. Dùng decoder có trạng thái hoặc reader phù hợp để giữ đúng ranh giới ký tự.

## 13. Checklist

- Chỉ dùng `readAllBytes` khi dữ liệu nhỏ hoặc đã có giới hạn đáng tin cậy.
- Xác định stream có EOF rõ ràng hay có thể tiếp tục mở.
- Dùng `readNBytes` cho prefix hoặc trường có độ dài giới hạn.
- Dùng buffer cố định để xử lý dữ liệu tuần tự.
- Dùng `transferTo` khi cần chuyển nguồn sang một đích phù hợp.
- Đặt giới hạn tổng byte cho nguồn không đáng tin cậy.
- Không dùng `available()` làm kích thước toàn bộ.
- Đóng stream đúng quyền sở hữu và xử lý file đích một phần khi có lỗi.

`readAllBytes` là tiện ích hữu ích của Java 9, nhưng chỉ nên dùng khi việc giữ toàn bộ nội dung trong heap là hợp lý. Với dữ liệu lớn hoặc không xác định kích thước, đọc theo buffer, giới hạn đầu vào và chuyển trực tiếp đến đích giúp bộ nhớ ổn định hơn.
