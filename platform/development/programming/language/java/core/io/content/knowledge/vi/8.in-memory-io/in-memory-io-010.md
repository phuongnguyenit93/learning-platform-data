# Giới hạn dung lượng khi tích lũy toàn bộ nội dung trong I/O bộ nhớ

Đọc toàn bộ dữ liệu vào RAM rất tiện khi làm việc với một tệp cấu hình nhỏ, phản hồi ngắn hoặc dữ liệu cần kiểm tra lại nhiều lần. Trong Java, các lớp như `ByteArrayOutputStream`, `CharArrayWriter`, `StringWriter` và `StringBuilder` cho phép **tích lũy dữ liệu ngày càng nhiều trong bộ nhớ**. Các phương thức `InputStream.readAllBytes()` hoặc `Files.readAllBytes(path)` cũng tạo kết quả chứa toàn bộ dữ liệu.

Nhưng kiểu xử lý này có **giới hạn thực tế**: dung lượng heap, giới hạn độ dài mảng, kích thước phần dữ liệu được giữ lại và bản sao tạm khi chuyển sang `byte[]`, `char[]` hoặc `String`. Khi nguồn lớn hoặc không đáng tin cậy, “đọc hết rồi mới xử lý” có thể gây `OutOfMemoryError` hoặc làm bộ gom rác hoạt động quá tải.

Bài này tập trung vào cơ chế tăng dung lượng, cách áp một **giới hạn có kiểm tra**, và khi nào chuyển sang xử lý từng khối thay vì gom toàn bộ nội dung.

## 1. “I/O trong bộ nhớ” gồm những gì?

Trong Java, luồng I/O thường có nguồn hoặc đích là tệp, socket hay tài nguyên ngoài. Với I/O trong bộ nhớ, nguồn/đích là đối tượng giữ dữ liệu trong RAM.

| API | Vai trò | Điểm cần biết về bộ nhớ |
|---|---|---|
| `ByteArrayOutputStream` | Gom các byte được ghi vào một vùng nhớ | Vùng đệm tự mở rộng; `toByteArray()` tạo bản sao dữ liệu |
| `ByteArrayInputStream` | Đọc từ mảng `byte[]` đã có | Thường dùng mảng có sẵn, không tự tải thêm dữ liệu |
| `CharArrayWriter` | Gom ký tự `char` vào bộ nhớ | Mảng ký tự tự mở rộng; `toCharArray()` tạo bản sao |
| `CharArrayReader` | Đọc từ `char[]` đã có | Phù hợp dữ liệu ký tự đã nằm trong RAM |
| `StringWriter` | Gom văn bản trong buffer ký tự | Buffer tăng dần theo lượng văn bản ghi |
| `StringReader` | Đọc từ `String` đã có | Không giải quyết vấn đề nếu `String` gốc quá lớn |
| `StringBuilder` | Ghép chuỗi ký tự trong RAM | `append(...)` có thể làm buffer tăng rất lớn |
| `InputStream.readAllBytes()` | Đọc toàn bộ byte còn lại của luồng thành mảng | Có thể tiêu thụ nhiều RAM; không phù hợp nguồn lớn |
| `Files.readString(path)` | Đọc nội dung văn bản của tệp thành `String` | Cần giữ toàn bộ kết quả dưới dạng chuỗi |
| `Files.readAllLines(path)` | Gom mọi dòng thành `List<String>` | Ngoài ký tự còn có đối tượng `List` và `String` của từng dòng |

**Lưu ý:** I/O “trong bộ nhớ” không có nghĩa là dung lượng **không giới hạn**. Khả năng mở rộng buffer chỉ có nghĩa API có thể cấp phát thêm cho đến khi chạm giới hạn của mảng hoặc môi trường thực thi.

## 2. Kích thước dữ liệu, dung lượng vùng đệm và heap là ba khái niệm khác nhau

Với bộ đệm có thể mở rộng, cần tách rõ:

- **Size / số dữ liệu hợp lệ**: số byte hoặc phần tử ký tự thực sự đã ghi, chẳng hạn `ByteArrayOutputStream.size()`.
- **Capacity / dung lượng cấp phát**: số phần tử buffer nội bộ có thể chứa trước khi cần cấp phát lớn hơn. Capacity có thể lớn hơn size vì thường được tăng theo từng đợt.
- **Heap / ngân sách RAM JVM**: nơi nhiều đối tượng Java sống. Heap cũng phải chứa mã ứng dụng, object khác, các bản sao trung gian và nhiều cấu trúc phụ trợ.

Giả sử một `ByteArrayOutputStream` có size là 1 MiB, nó có thể đã được cấp một buffer có capacity lớn hơn 1 MiB. Khi gọi `toByteArray()`, Java tạo **một mảng mới** chứa chính xác các byte hợp lệ. Trong thời gian đó, buffer nội bộ và mảng kết quả **cùng có thể còn sống**, nên không được tính rằng chỉ cần đúng 1 MiB RAM để tạo kết quả.

`new ByteArrayOutputStream(1024)` chỉ đặt **dung lượng ban đầu** là 1024 byte; nó **không đặt giới hạn tối đa**. Tương tự, `StringBuilder.ensureCapacity(...)` chỉ dự phòng dung lượng, không cấm append thêm sau đó. Ngược lại, `ByteArrayOutputStream.size()` báo tổng dữ liệu đã ghi, **không phải capacity đang cấp phát**.

### Giới hạn của mảng không đồng nhất với heap

Mảng Java dùng chỉ số kiểu `int`, vì vậy độ dài của một mảng không thể vượt quá phạm vi biểu diễn `int`, và giới hạn triển khai thực tế có thể thấp hơn `Integer.MAX_VALUE`. Trong khi đó, heap có thể cạn **từ trước** khi đến giới hạn một mảng.

Ví dụ, yêu cầu một mảng `byte[]` lớn có thể thất bại ngay cả trên máy có tổng RAM rất cao vì:
- JVM có giới hạn heap riêng, chẳng hạn được cấu hình bằng `-Xmx`.
- Heap đã được sử dụng bởi các đối tượng khác.
- Có thêm buffer tạm hoặc bản sao khiến **đỉnh bộ nhớ đồng thời** cao hơn dung lượng dữ liệu gốc.
- JVM không cấp phát được một mảng đủ lớn theo giới hạn/đặc điểm triển khai.

Không dùng `Integer.MAX_VALUE` làm giới hạn an toàn cho một phản hồi web, tệp nhập hoặc thông điệp socket. Hãy xác định giới hạn nghiệp vụ nhỏ hơn đáng kể, phù hợp với quy mô dữ liệu và tổng số yêu cầu đồng thời.

## 3. Vì sao buffer tự tăng có thể gây quá tải?

`ByteArrayOutputStream` giữ một mảng byte bên trong; nếu thao tác ghi tiếp vượt chỗ trống hiện tại, nó phải mở rộng vùng lưu trữ. `CharArrayWriter` và các bộ xây dựng văn bản cũng cần tăng vùng đệm khi dữ liệu lớn dần.

Trong quá trình tăng, triển khai có thể phải cấp mảng mới và sao chép dữ liệu cũ. Ngoài ra, đoạn code sử dụng kết quả có thể phát sinh **bản sao thứ hai**. Cơ chế này thường hợp lý cho dữ liệu nhỏ, nhưng có thể tốn CPU và RAM khi kích thước khó dự đoán.

Ví dụ tưởng như tiện:

~~~java
// Mảnh mã minh họa: input là một InputStream đã mở.
ByteArrayOutputStream memory = new ByteArrayOutputStream();
input.transferTo(memory);
byte[] all = memory.toByteArray();
~~~

Cả `memory` và `all` có thể cùng giữ byte của toàn bộ nguồn. `transferTo(...)` chỉ chuyển từ một luồng sang một luồng khác; khi **đích vẫn là `ByteArrayOutputStream`**, chương trình vẫn tích lũy toàn bộ dữ liệu vào RAM. Đừng coi `transferTo` là giải pháp streaming tiết kiệm bộ nhớ nếu nơi nhận vẫn là một buffer trong bộ nhớ.

Tương tự:

~~~java
// Mảnh mã minh họa: reader là Reader đã mở.
StringWriter writer = new StringWriter();
reader.transferTo(writer);
String allText = writer.toString();
~~~

Đầu ra vẫn được gom toàn bộ. Cách dùng API trông giống “stream” nhưng **đích quyết định mô hình lưu trữ**.

## 4. readAllBytes và readString: tiện nhưng không mặc nhiên an toàn

`InputStream.readAllBytes()` đọc tất cả các byte còn lại đến EOF rồi trả về `byte[]`. Tài liệu JDK 17 nhấn mạnh API này phục vụ **trường hợp đơn giản khi dữ liệu vừa bộ nhớ**, không dành cho luồng có dữ liệu lớn. Nó có thể phát sinh `OutOfMemoryError` nếu không thể cấp phát mảng cần thiết.

~~~java
// Mảnh mã minh họa: source là InputStream đã mở.
byte[] data = source.readAllBytes();
~~~

Các biến thể phổ biến có điểm khác nhau:

| Cách làm | Đặc điểm |
|---|---|
| `source.readAllBytes()` | Đọc đến EOF, kích thước không được giới hạn bằng tham số |
| `source.readNBytes(limit)` | Chỉ đọc **tối đa** `limit` byte và trả mảng tối đa kích thước đó |
| `source.readNBytes(buffer, off, len)` | Cố gắng điền mảng có sẵn, chỉ đọc tối đa `len` byte; trả số byte thực tế |
| `Files.readAllBytes(path)` | Đọc toàn tệp vào một mảng; phù hợp tệp nhỏ |
| `Files.readString(path, charset)` | Đọc thành một `String`; cần ngân sách bộ nhớ cho cả dữ liệu đọc và chuỗi |
| `Files.readAllLines(path, charset)` | Giữ tất cả dòng trong `List<String>` |
| `BufferedReader.readLine()` trong vòng lặp | Có thể xử lý từng dòng, không cần gom toàn bộ tệp; riêng dòng rất dài vẫn tạo `String` lớn |

**Phân biệt việc “đọc tối đa N” và “từ chối nếu nguồn có hơn N”:**

`readNBytes(N)` giúp giới hạn lượng dữ liệu trả về trong một lần gọi, nhưng **không tự xác nhận rằng nguồn chỉ dài N byte**. Nếu nguồn có N+1 byte, lời gọi đầu tiên vẫn trả đúng N byte mà không thông báo “quá giới hạn”. Muốn từ chối nguồn vượt N, phải kiểm tra thêm có byte tiếp theo hoặc dùng vòng lặp có bộ đếm và quy tắc vượt ngưỡng.

`available()` cũng **không** được dùng để suy ra tổng kích thước nguồn: hợp đồng của `InputStream.available()` chỉ mô tả ước lượng số byte có thể đọc mà không bị chặn, không phải độ dài toàn luồng.

## 5. Cách đặt giới hạn tích lũy theo số byte

Khi thật sự cần tạo kết quả `byte[]`, đặt giới hạn rõ ràng **trước khi đọc**, chẳng hạn 1 MiB hoặc 10 MiB tùy nghiệp vụ, và kiểm tra trong từng lần đọc. Không chờ đến sau khi `toByteArray()` mới so sánh độ dài: khi đó tài nguyên đã được sử dụng.

Giả sử ngân sách được đặt là `maxBytes`. Sau khi đọc được `n > 0` byte:

~~~java
// Mảnh mã minh họa: total, maxBytes và n là số không âm hợp lệ.
if (n > maxBytes - total) {
    throw new IOException("Nguồn vượt giới hạn");
}
total += n;
~~~

So sánh `n > maxBytes - total` tránh tính `total + n` trước khi kiểm tra; cách này hữu ích để giảm nguy cơ tràn số khi chương trình mở rộng sang kích thước lớn. Bất biến cần duy trì là `0 <= total <= maxBytes`. Khi theo dõi số byte rất lớn trong một pipeline truyền dữ liệu, có thể sử dụng `long` cho tổng, nhưng **một mảng `byte[]` đơn lẻ vẫn bị giới hạn độ dài kiểu `int`**.

### Ví dụ chạy được: trả về mảng chỉ khi nguồn không vượt giới hạn

Tạo file **`BoundedMemoryReadDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class BoundedMemoryReadDemo {
    public static void main(String[] args) throws IOException {
        byte[] source = "abcdefghi".getBytes(StandardCharsets.US_ASCII);

        try (InputStream in = new ByteArrayInputStream(source)) {
            byte[] result = readAtMost(in, 9);
            System.out.println("length=" + result.length);
            System.out.println("text=" +
                    new String(result, StandardCharsets.US_ASCII));
        }

        try (InputStream in = new ByteArrayInputStream(source)) {
            readAtMost(in, 8);
        } catch (IOException ex) {
            System.out.println(ex.getMessage());
        }
    }

    private static byte[] readAtMost(InputStream input, int maxBytes)
            throws IOException {
        if (maxBytes < 0) {
            throw new IllegalArgumentException("maxBytes < 0");
        }

        ByteArrayOutputStream output =
                new ByteArrayOutputStream(Math.min(maxBytes, 8192));
        byte[] buffer = new byte[4];
        int total = 0;
        int count;

        while ((count = input.read(buffer)) != -1) {
            if (count > maxBytes - total) {
                throw new IOException(
                        "Vượt giới hạn " + maxBytes + " byte");
            }
            output.write(buffer, 0, count);
            total += count;
        }
        return output.toByteArray();
    }
}
~~~

Biên dịch/chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 BoundedMemoryReadDemo.java
java BoundedMemoryReadDemo
~~~

Stdout:

~~~text
length=9
text=abcdefghi
Vượt giới hạn 8 byte
~~~

Giải thích:

1. Mẫu dữ liệu có 9 byte ASCII. Với `maxBytes=9`, cả ba lượt đọc qua buffer dài 4 byte (4 + 4 + 1) đều hợp lệ và phương thức trả mảng chính xác.
2. Với `maxBytes=8`, sau khi tích lũy 8 byte, vòng lặp nhận thêm 1 byte. Điều kiện `count > maxBytes - total` đúng và ném `IOException` trước khi ghi phần vượt giới hạn vào kết quả.
3. Bộ đệm khởi đầu của `ByteArrayOutputStream` được chọn nhỏ và hợp lý; tham số constructor không đặt hard limit. **Chính điều kiện trong vòng lặp mới thực thi giới hạn nghiệp vụ**.
4. Vì kết quả phải là `byte[]`, `toByteArray()` tạo bản sao. Giới hạn 9 byte bảo vệ khối dữ liệu trong ví dụ, nhưng khi áp dụng cho kích thước lớn còn phải tính thêm bộ nhớ đỉnh do bản sao.
5. Để tái sử dụng hàm với nguồn không đáng tin cậy, cân nhắc deadline, hủy thao tác hoặc kiểm soát đầu vào có thể chặn vô thời hạn. Giới hạn dung lượng **khác** giới hạn thời gian.

`readAtMost` ở trên giả định `maxBytes` phù hợp với ngân sách RAM và kiểu `int`. Với hệ thống thực tế, chỉ số giới hạn phải đến từ cấu hình/chính sách ứng dụng được kiểm soát; không lấy trực tiếp một giá trị cực lớn do bên gửi đề xuất.

## 6. Các cách giới hạn khác: chỉ đọc phần đầu, kiểm tra dư một byte, báo lỗi

Nếu chỉ cần **xem trước** tối đa N byte (preview), `input.readNBytes(N)` thích hợp, vì ứng dụng chủ ý bỏ qua phần còn lại. Nhưng phải gọi kết quả đó là **preview**, không phải “toàn bộ tài liệu”.

Nếu cần **đọc toàn bộ khi kích thước không quá N và báo lỗi nếu nhiều hơn**, có thể dùng:

1. Đọc tối đa N byte vào một mảng hoặc buffer.
2. Nếu đã đọc đủ N byte, thử đọc **thêm một byte** để phân biệt vừa đủ N với nguồn dài hơn N.
3. Nếu lần thử trả `-1`, nguồn kết thúc đúng ngưỡng; nếu trả byte từ `0` đến `255`, nguồn vượt giới hạn.

Lưu ý ở trường hợp N bằng 0: phải kiểm tra một byte trước khi kết luận nguồn rỗng. Cách này có thể tiêu thụ thêm một byte từ input khi nguồn vượt ngưỡng. Nếu cần giữ lại byte đó, ứng dụng phải dùng nguồn có khả năng đẩy lại/đánh dấu, hoặc chọn giao thức phù hợp. Cách lặp `readAtMost` ở trên chấp nhận việc đọc một phần buffer khiến số byte đã tiêu thụ từ nguồn có thể lớn hơn giới hạn, dù nó không tích lũy những byte vượt hạn mức.

Một số bài toán có yêu cầu bảo toàn stream khi không hợp lệ; khi đó thiết kế cơ chế giới hạn ở ranh giới đọc hoặc quản lý frame dữ liệu, thay vì chỉ nhận kết quả quá giới hạn sau khi đọc.

## 7. Xử lý từng khối: giải pháp thường tốt nhất khi không cần giữ toàn bộ

Nếu mục tiêu là **sao chép**, **tính checksum**, **nén**, **mã hóa theo dòng/khối** hoặc truyền dữ liệu tới nơi khác, có thể xử lý liên tục bằng một bộ đệm kích thước cố định mà không giữ tất cả nguồn trong RAM.

~~~java
// Mảnh mã minh họa: input/output là các stream đã mở.
byte[] buffer = new byte[8192];
int n;
while ((n = input.read(buffer)) != -1) {
    output.write(buffer, 0, n);
}
~~~

Ý nghĩa:

- `buffer` chỉ cấp phát cố định 8192 byte để dùng lại.
- `read(...)` trả **số byte thực tế**, có thể ít hơn buffer; chỉ ghi `n` byte vừa nhận.
- Nguồn có kích thước lớn không khiến bộ đệm này tự phình lên. Tổng byte đi qua có thể rất lớn, nhưng **bộ đệm của vòng lặp** vẫn giữ nguyên kích thước.
- Đích là yếu tố quyết định: ghi ra `FileOutputStream` hoặc một đích hỗ trợ streaming sẽ tránh tích lũy toàn bộ; nếu `output` chính là `ByteArrayOutputStream` thì dữ liệu vẫn gom hết trong RAM.
- Với nguồn tệp, đóng stream bằng `try-with-resources`; nếu dữ liệu nhạy cảm, còn phải cân nhắc thời gian sống của các mảng trung gian.

`InputStream.transferTo(OutputStream)` (Java 9+) cũng phục vụ việc truyền byte từ input sang output đến EOF, nhưng **không áp sẵn dung lượng tối đa**. Nếu cần giới hạn tổng byte sao chép, vẫn phải tự đếm hoặc bao một lớp giới hạn trước khi truyền.

### Ví dụ hoàn chỉnh: sao chép file mà không load toàn bộ

Tạo file **`StreamingFileCopyDemo.java`**:

~~~java
import java.io.InputStream;
import java.io.OutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class StreamingFileCopyDemo {
    public static void main(String[] args) throws IOException {
        Path source = Files.createTempFile("copy-source-", ".bin");
        Path target = Files.createTempFile("copy-target-", ".bin");

        try {
            Files.write(source,
                    "one\ntwo\n".getBytes(StandardCharsets.UTF_8));

            long total = 0;
            try (InputStream in = Files.newInputStream(source);
                 OutputStream out = Files.newOutputStream(target)) {
                byte[] buffer = new byte[3];
                int n;

                while ((n = in.read(buffer)) != -1) {
                    out.write(buffer, 0, n);
                    total += n;
                }
            }

            System.out.println("bytes=" + total);
            System.out.println("same="
                    + (Files.mismatch(source, target) == -1));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 StreamingFileCopyDemo.java
java StreamingFileCopyDemo
~~~

Stdout:

~~~text
bytes=8
same=true
~~~

Dữ liệu `"one\ntwo\n"` có 8 byte UTF-8. Mảng `buffer` trong ví dụ chỉ dài 3 byte, khiến chương trình bắt buộc lặp nhiều lần. `Files.mismatch(...)` (có từ Java 12) xác nhận hai tệp giống byte theo byte mà không cần tự gọi `readAllBytes()`.

Trong ứng dụng thật, file tạm chỉ dùng để minh họa cách sao chép và kiểm tra. Khi sao chép từ nguồn do người dùng cung cấp, phải kiểm tra nguồn/đích, quyền ghi, ngân sách thời gian và bảo đảm không vô tình ghi đè dữ liệu quan trọng.

## 8. Giới hạn khi tích lũy văn bản: byte khác ký tự

Khi dữ liệu là văn bản, cần phân biệt hai loại giới hạn:

- **Giới hạn theo byte** hữu ích cho kích thước file, lưu trữ, băng thông và bảo vệ dữ liệu đầu vào dạng byte.
- **Giới hạn theo ký tự** hữu ích cho chiều dài nội dung sau khi giải mã. Trong Java, `String.length()`, `StringBuilder.length()` và `CharArrayWriter.size()` đếm **đơn vị mã UTF-16** (thường tương ứng với `char`), không nhất thiết bằng số Unicode code point hay số “ký tự người dùng nhìn thấy”.

Ví dụ chuỗi `"A🙂B"` có ba Unicode code point nhưng `String.length()` là 4 vì emoji được biểu diễn bằng hai đơn vị UTF-16. Trong UTF-8, dữ liệu này có 6 byte: `A` (1) + emoji (4) + `B` (1).

Do đó, một giới hạn “10.000 ký tự” phải định nghĩa rõ đang tính theo code point, đơn vị UTF-16 hay độ dài hiển thị; nếu mục tiêu là giới hạn RAM khi tích lũy, còn phải tính encoding và cấu trúc chứa.

### Ví dụ giới hạn StringBuilder theo đơn vị UTF-16

~~~java
// Mảnh mã minh họa: chunk là phần văn bản nhận được từ reader.
int maxUnits = 1000;
StringBuilder builder = new StringBuilder();
if (chunk.length() > maxUnits - builder.length()) {
    throw new IllegalArgumentException("Vượt số đơn vị UTF-16");
}
builder.append(chunk);
~~~

Cách kiểm tra trên chỉ giới hạn lượng **nội dung** tích lũy. Nó không cho một mức cam kết chính xác về byte heap, bởi triển khai `String`/`StringBuilder` và overhead bộ nhớ có thể khác nhau. Nếu cần giới hạn ký tự hiển thị hoặc Unicode code point, thuật toán phải xét thêm quy tắc Unicode phù hợp.

Đối với dữ liệu streaming UTF-8, **không nên** chuyển từng mảng byte thành `String` độc lập khi một ký tự nhiều byte có thể nằm ở ranh giới hai lần đọc; dùng `InputStreamReader` hoặc `CharsetDecoder` để giải mã có trạng thái qua các khối.

## 9. reset và close: có giải phóng bộ nhớ đang giữ không?

`ByteArrayOutputStream.reset()` và `CharArrayWriter.reset()` đặt **số lượng dữ liệu hợp lệ về 0**, để có thể ghi một nội dung khác bằng buffer đã cấp phát. Chúng **không bắt buộc giảm capacity**; thực tế các lớp này giữ lại vùng đệm để tái sử dụng.

Với hai lớp bộ nhớ này, `close()` không giải phóng buffer nội bộ theo nghĩa “trả RAM ngay”; các phương thức vẫn có thể sử dụng sau khi đóng theo hợp đồng riêng của lớp. Khi object không còn được tham chiếu, bộ gom rác mới có cơ hội thu hồi vùng nhớ tương ứng.

Đừng dùng `reset()` như cơ chế chống tràn bộ nhớ khi một object buffer đã từng phình quá lớn và được giữ sống lâu. Với hệ thống phục vụ nhiều request, giữ lại một buffer từng nhận payload lớn có thể khiến heap bị chiếm không cần thiết; sau khi xử lý request nên bỏ tham chiếu đến buffer lớn nếu không muốn tái sử dụng với cùng capacity.

### Ví dụ chạy được: size, toByteArray và reset

Tạo file **`MemoryBufferReuseDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

public class MemoryBufferReuseDemo {
    public static void main(String[] args) {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream(2);

        buffer.writeBytes("abc".getBytes(StandardCharsets.UTF_8));
        byte[] snapshot = buffer.toByteArray();
        snapshot[0] = (byte) 'Z';

        System.out.println("size=" + buffer.size());
        System.out.println("stored="
                + buffer.toString(StandardCharsets.UTF_8));

        buffer.reset();
        System.out.println("afterReset=" + buffer.size());

        buffer.writeBytes("XY".getBytes(StandardCharsets.UTF_8));
        System.out.println("reused="
                + buffer.toString(StandardCharsets.UTF_8));
    }
}
~~~

~~~bash
javac -encoding UTF-8 MemoryBufferReuseDemo.java
java MemoryBufferReuseDemo
~~~

Stdout:

~~~text
size=3
stored=abc
afterReset=0
reused=XY
~~~

Dù constructor chỉ yêu cầu capacity ban đầu bằng 2, buffer vẫn chứa được ba byte `abc` vì nó **tự mở rộng**, chứng minh tham số đó không phải hard limit. Việc sửa `snapshot[0]` thành `Z` không đổi nội dung buffer vì `toByteArray()` đã trả **bản sao**. Sau `reset()`, số byte hợp lệ bằng 0; ghi `XY` tạo nội dung mới. Chương trình không kết luận capacity đã giảm, vì API không cung cấp getter công khai để truy xuất chính xác capacity của `ByteArrayOutputStream`.

## 10. Kiểm tra kích thước trước và trong khi đọc

Đối với một file có `Path`, `Files.size(path)` trả kích thước hiện tại theo byte, hữu ích để **từ chối sớm** file quá lớn:

~~~java
// Mảnh mã minh họa: path là Path hợp lệ, maxBytes là giới hạn đã xác định.
if (Files.size(path) > maxBytes) {
    throw new IOException("File quá lớn");
}
~~~

Nhưng kiểm tra ban đầu **không thay thế** kiểm tra lúc đọc. Tệp có thể thay đổi sau thời điểm đo, và một luồng mạng, luồng nén hoặc luồng sinh động không có kích thước đáng tin trước khi đọc.

Nếu dữ liệu đã **giải nén**, giới hạn kích thước tệp nén trên đĩa không đảm bảo nội dung giải nén nhỏ; phải theo dõi kích thước **sau giải nén** khi tích lũy nội dung. Tương tự, một HTTP header khai báo kích thước có thể không có, sai hoặc không đáng tin; phải giới hạn byte thực nhận.

Ngoài giới hạn cho **mỗi** nguồn, hệ thống cần xem xét tổng lượng bộ nhớ cho **nhiều** tác vụ đồng thời. Chẳng hạn 100 request cùng gom tối đa 10 MiB tạo ít nhất một khoảng cỡ 1.000 MiB dữ liệu logic và còn phát sinh các bản sao/overhead khác; việc từng request tuân thủ 10 MiB **không có nghĩa** cả hệ thống nằm trong ngân sách heap.

## 11. Cách chọn chiến lược theo mục tiêu

| Mục tiêu | Chiến lược phù hợp | Điều cần tránh |
|---|---|---|
| Giải mã một payload nhỏ, có giới hạn rõ | Đọc có kiểm tra max byte, rồi giải mã bằng charset tường minh | Gom vô hạn từ nguồn không đáng tin |
| Tải/đọc cả file cấu hình nhỏ | `Files.readString` hoặc `Files.readAllBytes` sau khi đảm bảo phù hợp bộ nhớ | Dùng API tiện lợi cho file hàng GB |
| Sao chép dữ liệu giữa hai file | `InputStream` → buffer cố định → `OutputStream` hoặc `Files.copy` | Sao chép qua `ByteArrayOutputStream` nếu không cần mảng kết quả |
| Xử lý log theo dòng | `BufferedReader.readLine()` trong vòng lặp | `Files.readAllLines` cho log có thể rất lớn |
| Tạo một chuỗi nhỏ từ nhiều phần | `StringBuilder`/`StringWriter` với giới hạn độ dài | Ghép vô hạn từ input streaming |
| Xử lý dữ liệu có thể dài không xác định | Streaming, chunking, pagination hoặc giới hạn đầu vào | Coi `readAllBytes()` là thao tác vô hại |
| Ghi ra network/file theo từng gói | Xử lý và ghi từng khối, theo dõi tổng và lỗi | Buffer toàn bộ dữ liệu trong RAM trước khi bắt đầu ghi |

Một vài quy tắc áp dụng:

1. **Biết giới hạn nghiệp vụ trước khi tích lũy**. Một giá trị mặc định rõ ràng như 1 MiB là ví dụ, không phải giới hạn phổ quát.
2. **Kiểm tra khi đọc/append**, không chỉ sau khi hoàn thành.
3. **Tính thêm bản sao** khi gọi `toByteArray()`, `toCharArray()`, `toString()`, giải mã text, gom List hoặc tạo những đối tượng trung gian.
4. **Đừng trộn byte với ký tự**. Dung lượng UTF-8 không thể suy ra đơn giản từ `String.length()`; số code point lại là khái niệm khác.
5. **Dùng streaming khi đầu ra không cần dữ liệu toàn phần**. Streaming chỉ thật sự tiết kiệm khi đích và pipeline không gom lại toàn bộ.
6. **Quản lý tài nguyên đúng loại**. `ByteArrayOutputStream.close()` không phải thao tác giải phóng heap; ngược lại, các luồng tệp/socket phải được đóng bằng `try-with-resources`.
7. **Tách lỗi quá giới hạn khỏi lỗi I/O** để báo đúng nguyên nhân, và từ chối dữ liệu lớn bằng thông báo rõ ràng thay vì trông chờ bắt `OutOfMemoryError`. `OutOfMemoryError` có thể khiến JVM ở trạng thái thiếu tài nguyên nghiêm trọng, không phải nhánh xử lý thông thường.

## 12. Tóm tắt

- Các buffer bộ nhớ như `ByteArrayOutputStream`, `CharArrayWriter` và `StringBuilder` **tự tăng dung lượng**, không tự đặt giới hạn số byte/ký tự phù hợp ứng dụng.
- `size()` là lượng dữ liệu hợp lệ; **capacity** có thể lớn hơn và **heap** còn phải chứa các đối tượng khác. `toByteArray()`/`toCharArray()` có thể làm tăng đỉnh bộ nhớ vì tạo bản sao.
- `readAllBytes()`, `readString()` và `readAllLines()` phù hợp với dữ liệu nhỏ hoặc đã được kiểm soát; không áp dụng tùy tiện cho nguồn không biết kích thước.
- Muốn giữ toàn bộ kết quả thì kiểm tra **giới hạn trong từng lần đọc** và cân nhắc bộ nhớ của bản sao; muốn chỉ preview thì dùng API có giới hạn và không giả định đó là toàn bộ nguồn.
- Nếu không cần tích lũy, xử lý **theo từng khối** để dung lượng buffer cố định, đồng thời kiểm soát đích ghi.
- `reset()` tái sử dụng buffer nhưng không nhất thiết giải phóng capacity; chỉ bỏ các tham chiếu không còn cần mới giúp bộ gom rác có thể thu hồi.
- Đặt giới hạn cả theo **byte**, **ký tự**, **số công việc đồng thời** và **thời gian** tương ứng mục tiêu hệ thống.

### Tài liệu chính thức

- [Java 17 — ByteArrayOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ByteArrayOutputStream.html)
- [Java 17 — CharArrayWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/CharArrayWriter.html)
- [Java 17 — InputStream.readAllBytes/readNBytes/transferTo](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html)
- [Java 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
