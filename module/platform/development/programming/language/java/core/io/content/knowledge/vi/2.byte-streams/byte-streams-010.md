# FileInputStream, FileOutputStream và chế độ append trong Java

`FileInputStream` và `FileOutputStream` là hai luồng byte dùng để làm việc trực tiếp với tệp trong gói `java.io`. Một bên đọc byte có sẵn trên đĩa, bên còn lại ghi byte vào tệp. Khi ghi, chọn **ghi từ đầu tệp** hay **ghi nối vào cuối tệp (append)** là quyết định rất quan trọng: mở `FileOutputStream` không bật append trên tệp đã tồn tại có thể làm mất toàn bộ dữ liệu cũ ngay lúc mở luồng.

Bài này tập trung vào cách mở, đọc, ghi, ghi nối, đóng và xử lý lỗi của hai lớp; các ví dụ áp dụng cho Java 17+.

## 1. Luồng byte làm việc với tệp như thế nào?

- **`FileInputStream`** kế thừa `InputStream`: mở tệp để lấy các byte theo thứ tự, với vị trí đọc tiến lên qua các lần gọi `read(...)`. Đọc đến hết tệp trả `-1`.
- **`FileOutputStream`** kế thừa `OutputStream`: mở tệp để ghi các byte bằng `write(...)`; không cung cấp thao tác đọc. Chế độ mở quyết định dữ liệu cũ được giữ để nối thêm hay bị thay thế.
- Hai lớp xử lý **byte thô**, không tự giải mã UTF-8, không tự hiểu dòng, số nguyên, ảnh hay JSON. Diễn giải dữ liệu là trách nhiệm của tầng phía trên.
- Cả hai là luồng I/O gắn với tài nguyên hệ điều hành. Mở có thể thất bại và thao tác có thể ném `IOException`; phải đóng tài nguyên khi dùng xong.

| Nhu cầu | Lựa chọn | Hành vi chính |
|---|---|---|
| Đọc tệp | `new FileInputStream(file)` | Mở để đọc; không tạo tệp còn thiếu |
| Tạo hoặc thay thế nội dung tệp | `new FileOutputStream(file)` | Nếu tệp hợp lệ chưa có thì tạo; nếu có thì **xóa nội dung cũ (truncate)** |
| Nối byte vào cuối tệp | `new FileOutputStream(file, true)` | Nếu tệp chưa có thì tạo; nếu đã có thì giữ dữ liệu cũ và ghi tiếp |
| Ghi từ đầu với tham số tường minh | `new FileOutputStream(file, false)` | Cùng ý nghĩa với không truyền cờ append |

Ở đây `file` có thể là một đối tượng `File`; các constructor tương tự cũng nhận đường dẫn `String`. Nên tạo đường dẫn một cách tường minh bằng `Path` và chuyển sang `File` khi sử dụng các API cổ điển:

~~~java
Path path = Path.of("data.bin");
File file = path.toFile();

// Các dòng sau là minh họa, không mở cùng lúc cả ba luồng ghi:
FileInputStream input = new FileInputStream(file);
FileOutputStream overwrite = new FileOutputStream(file);
FileOutputStream append = new FileOutputStream(file, true);
~~~

Đoạn mã trên chỉ minh họa các constructor, **không** phải chương trình chạy độc lập. Trong code thật hãy chọn đúng một chế độ theo mục đích, quản lý đóng luồng và tránh mở luồng ghi khi chưa định ghi dữ liệu. Chỉ riêng việc tạo `new FileOutputStream(file)` đã có thể truncate tệp.

## 2. Phân biệt overwrite và append

Giả sử tệp đang chứa ba byte theo thứ tự:

~~~text
A B C
~~~

Sau khi mở `new FileOutputStream(file)` và ghi hai byte `X Y`, nội dung cuối cùng là:

~~~text
X Y
~~~

Ngược lại, mở `new FileOutputStream(file, true)` rồi ghi `X Y` sẽ cho:

~~~text
A B C X Y
~~~

Lưu ý quan trọng:

1. `append = true` nghĩa là **ghi byte mới ở cuối tệp**. Nó không tự thêm ký tự xuống dòng, dấu cách, dấu phân cách hay header.
2. `append = false` là mặc định. Trên tệp thông thường đã tồn tại, constructor mở đầu ra ở chế độ này sẽ truncate tệp; việc đóng ngay sau đó cũng không khôi phục dữ liệu cũ.
3. Cả hai chế độ có thể tạo tệp mới nếu tệp không tồn tại và đường dẫn cùng quyền truy cập hợp lệ. Chúng **không tự tạo thư mục cha**.
4. Mở thất bại, chẳng hạn vì tệp không tồn tại khi đọc, đường dẫn là thư mục không phù hợp hoặc thiếu quyền, sẽ phát sinh lỗi (thường là `FileNotFoundException` khi tạo luồng), không phải trả về một luồng rỗng.
5. Append không mặc nhiên bảo đảm nhiều luồng hoặc nhiều tiến trình cùng ghi thành từng **bản ghi nguyên vẹn** theo ý nghĩa nghiệp vụ. Nếu cần đồng bộ truy cập hoặc khóa tệp, phải thiết kế riêng; cũng cần xác định rõ quy tắc phân cách dữ liệu.

Để thêm một dòng văn bản vào tệp, chính ứng dụng phải tự quyết định có ghi `"\n"` hay không. Append chỉ là hành vi đặt vị trí ghi, không phải API quản lý dòng.

## 3. Ví dụ Java 17+: ghi mới, nối thêm rồi ghi thay thế

Tạo tệp **`FileAppendDemo.java`** với mã hoàn chỉnh:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class FileAppendDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("append-demo-", ".bin");

        try {
            // Không append: bắt đầu nội dung tệp bằng 3 byte.
            try (FileOutputStream out = new FileOutputStream(path.toFile())) {
                out.write(new byte[] {10, 20, 30});
            }

            // Append: giữ 3 byte cũ và nối 2 byte tiếp theo.
            try (FileOutputStream out = new FileOutputStream(path.toFile(), true)) {
                out.write(new byte[] {40, 50});
            }
            System.out.println("Sau append: " + Arrays.toString(readAll(path)));

            // Không append: tệp trước đó bị truncate.
            try (FileOutputStream out = new FileOutputStream(path.toFile(), false)) {
                out.write(7);
            }
            System.out.println("Sau overwrite: " + Arrays.toString(readAll(path)));
        } finally {
            Files.deleteIfExists(path);
        }
    }

    private static byte[] readAll(Path path) throws IOException {
        try (FileInputStream in = new FileInputStream(path.toFile());
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[3];
            int n;
            while ((n = in.read(buffer)) != -1) {
                out.write(buffer, 0, n);
            }
            return out.toByteArray();
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac FileAppendDemo.java
java FileAppendDemo
~~~

Kết quả chuẩn:

~~~text
Sau append: [10, 20, 30, 40, 50]
Sau overwrite: [7]
~~~

Điều đáng quan sát:

- Chương trình tạo một tệp tạm mới bằng `Files.createTempFile(...)` để tránh ghi đè nhầm tài liệu sẵn có.
- Lần mở đầu tiên, `FileOutputStream(path.toFile())` ghi ba byte. Lần mở với `true` nối thêm hai byte; đọc lại cho thấy đầy đủ năm byte.
- Lần mở cuối cùng với `false` truncate dữ liệu cũ rồi ghi một byte có giá trị `7`; vì vậy toàn bộ tệp chỉ còn `[7]`.
- `readAll(...)` lặp đến EOF; mỗi lần chỉ chuyển `n` byte thực sự đọc được sang `ByteArrayOutputStream`. Nó không coi kích thước bộ đệm 3 là số byte luôn đọc được.
- Cả ba luồng ghi, luồng đọc và luồng bộ nhớ đều đóng bằng `try-with-resources`. Khối `finally` xóa tệp tạm sau khi các luồng đã đóng.

Trong ví dụ này, phương thức `readAll` gom dữ liệu vào RAM để tiện in ra màn hình; với tệp rất lớn nên xử lý hoặc sao chép từng khối thay vì giữ toàn bộ nội dung trong bộ nhớ.

## 4. Đọc đúng cách với FileInputStream

Các phương thức thông dụng kế thừa từ `InputStream`:

| Lời gọi | Điều nhận được |
|---|---|
| `int value = in.read()` | Một byte ở dạng `int` trong khoảng `0..255`, hoặc `-1` khi EOF |
| `int n = in.read(buffer)` | Đọc tối đa `buffer.length` byte, bắt đầu tại chỉ số 0 |
| `int n = in.read(buffer, offset, length)` | Đọc tối đa `length` byte vào mảng tại chỉ số `offset` |
| `byte[] data = in.readAllBytes()` | Đọc toàn bộ các byte còn lại vào mảng, phù hợp khi dữ liệu đủ nhỏ |
| `long n = in.transferTo(out)` | Truyền byte từ đầu vào sang một `OutputStream` cho tới EOF |

`read(buffer, off, len)` trả về **số byte thực đọc**, có thể nhỏ hơn `len`, hoặc `-1` nếu đã EOF (với `len > 0`). Nếu `len == 0`, lời gọi trả `0`. `off` chỉ là chỉ số trong **mảng đích**, không phải vị trí trên đĩa. Vùng hợp lệ phải thỏa `0 <= off <= buffer.length` và `0 <= len <= buffer.length - off`.

Vòng lặp đọc/sao chép thường viết:

~~~java
byte[] buffer = new byte[8192];
int n;
while ((n = input.read(buffer)) != -1) {
    output.write(buffer, 0, n);
}
~~~

Đây là **mảnh mã minh họa** yêu cầu hai biến `input`/`output` là các luồng đang mở. Không dùng `output.write(buffer)` thay cho `output.write(buffer, 0, n)`: lần đọc cuối có thể nhận ít hơn bộ đệm, khiến phần dư cũ bị ghi sai.

Nếu xử lý mỗi byte riêng lẻ, luôn so sánh kết quả `int` với `-1` **trước khi chuyển sang `byte`**. Byte `0xFF` hợp lệ có dạng `-1` khi hiển thị bằng kiểu `byte` có dấu, nhưng `in.read()` sẽ trả số nguyên `255` khi đọc nó thành công; chỉ `-1` kiểu `int` mới báo EOF.

Lệnh `available()` không cho biết chính xác tổng số byte còn trong tệp/luồng theo hợp đồng chung của `InputStream`; không dùng nó làm điều kiện đọc hết. Luôn dựa vào `read()` trả `-1`, độ dài đã biết của giao thức hoặc API đọc đủ chuyên dụng.

## 5. Ghi byte bằng FileOutputStream

Những phương thức kế thừa từ `OutputStream` thường dùng:

- `out.write(int b)` ghi **8 bit thấp** của số nguyên: `out.write(65)` ghi đúng một byte `0x41` (chữ A nếu diễn giải theo ASCII).
- `out.write(byte[] bytes)` ghi toàn bộ mảng.
- `out.write(byte[] bytes, int offset, int length)` ghi chính xác `length` byte bắt đầu tại chỉ số `offset` trong mảng nguồn.
- `out.close()` đóng luồng và giải phóng tài nguyên liên quan; ưu tiên `try-with-resources` để đóng cả khi có ngoại lệ.

Khác với `read(...)`, `write(byte[], off, len)` trả về `void`; nếu hoàn thành bình thường, lời gọi đã thực hiện yêu cầu ghi `len` byte vào luồng theo hợp đồng của API. Nếu có sự cố ghi, phương thức có thể ném `IOException`. Không dùng giá trị trả về của `read(...)` làm `length` trước khi đã kiểm tra nó là số dương.

Ví dụ với một mảng byte đã có:

~~~java
byte[] payload = {11, 22, 33, 44, 55};
out.write(payload, 1, 3); // Ghi ba byte 22, 33, 44
~~~

Đây là mảnh mã minh họa; `out` cần là một `FileOutputStream` đã mở hợp lệ. Tham số thứ ba là **số lượng byte**, không phải chỉ số cuối.

Khi cần nâng hiệu suất ghi nhiều khối nhỏ, có thể bọc bằng `BufferedOutputStream`. Trong trường hợp đó, `flush()` đẩy dữ liệu đang nằm trong bộ đệm của Java xuống luồng bên dưới; nó không đồng nghĩa với việc dữ liệu đã được lưu bền vững trên thiết bị lưu trữ. `close()` của luồng bọc sẽ đóng luôn luồng bên dưới, nên chỉ quản lý đóng lớp bao ngoài khi đã trao quyền sở hữu cho wrapper.

## 6. Ví dụ Java 17+: append văn bản có mã hóa rõ ràng

`FileOutputStream` là luồng byte. Khi cần lưu văn bản, phải tự chuyển `String` thành byte bằng charset rõ ràng; với dữ liệu UTF-8, dùng `StandardCharsets.UTF_8`. Ví dụ này cố ý ghi ký tự xuống dòng ở cuối từng bản ghi, bởi cờ append tự nó **không** thêm dấu xuống dòng.

Tệp **`AppendUtf8Demo.java`**:

~~~java
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class AppendUtf8Demo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("append-lines-", ".txt");

        try {
            try (FileOutputStream out = new FileOutputStream(path.toFile())) {
                out.write("Dong 1\n".getBytes(StandardCharsets.UTF_8));
            }

            try (FileOutputStream out = new FileOutputStream(path.toFile(), true)) {
                out.write("Dong 2\n".getBytes(StandardCharsets.UTF_8));
            }

            try (FileInputStream in = new FileInputStream(path.toFile())) {
                String text = new String(in.readAllBytes(), StandardCharsets.UTF_8);
                System.out.print(text);
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

~~~bash
javac AppendUtf8Demo.java
java AppendUtf8Demo
~~~

Kết quả:

~~~text
Dong 1
Dong 2
~~~

Ví dụ giữ ASCII trong nội dung để stdout giống nhau ở các terminal phổ biến; thao tác chuyển mã vẫn thực sự sử dụng UTF-8. Với tệp văn bản lớn hoặc cần xử lý từng dòng, nên chọn `BufferedReader`/`BufferedWriter`, `InputStreamReader`/`OutputStreamWriter` hoặc `Files.newBufferedReader`/`Files.newBufferedWriter`. Không nên chuyển từng mảng byte đọc được sang `String` một cách độc lập nếu một ký tự UTF-8 có thể bị tách giữa hai lần đọc.

## 7. Quản lý tài nguyên và lỗi tệp

Ưu tiên `try-with-resources` cho cả đọc và ghi:

~~~java
try (FileInputStream in = new FileInputStream(sourceFile);
     FileOutputStream out = new FileOutputStream(targetFile)) {
    in.transferTo(out);
}
~~~

Đây là mảnh mã minh họa: `sourceFile` và `targetFile` là những biến `File` hợp lệ đã được xác định. Cách viết tự đóng hai luồng khi khối kết thúc, kể cả khi đọc/ghi ném lỗi; không cần gọi `close()` thủ công trong `finally`. Lưu ý mở đích bằng constructor không append **sẽ truncate đích**, và sao chép tệp lên chính nó theo cách này có thể phá dữ liệu; nên xác minh nguồn và đích là hai tệp phù hợp trước khi mở.

Các tình huống cần chủ động xử lý:

| Tình huống | Hệ quả và hướng xử lý |
|---|---|
| Đọc tệp không tồn tại | `FileInputStream` có thể ném `FileNotFoundException`; kiểm tra đường dẫn hoặc xử lý lỗi |
| Ghi vào thư mục cha chưa tồn tại | Constructor không tự tạo thư mục; tạo thư mục trước nếu ứng dụng cho phép |
| Thiếu quyền đọc/ghi hoặc tệp bị khóa | Có thể ném ngoại lệ I/O; hiển thị lỗi đúng ngữ cảnh, không giả vờ thành công |
| Mở output không append trên tệp có dữ liệu | Truncate ngay khi mở; cân nhắc append, lưu bản sao hoặc cơ chế ghi an toàn |
| Đọc bằng mảng và bỏ qua `n` | Có thể xuất thêm dữ liệu cũ cuối bộ đệm; dùng đúng số byte thực nhận |
| Append nhiều bản ghi cùng lúc từ nhiều tiến trình | Bản ghi có thể bị xen kẽ tùy hệ thống và cách ghi; cần đồng bộ/khóa hoặc kiến trúc ghi tập trung khi tính toàn vẹn quan trọng |
| Lưu file lớn bằng `readAllBytes()` | Có thể tiêu tốn RAM lớn; đọc theo các khối kích thước cố định |
| Ghi văn bản mà không xác định charset | Dễ lệch mã hóa giữa máy; dùng UTF-8 hoặc API đọc/ghi văn bản phù hợp |

Một số phương thức viết có thể đưa dữ liệu qua bộ đệm của hệ điều hành. Đóng luồng sau khi ghi bảo đảm đóng tài nguyên theo hợp đồng API nhưng **không tự tạo bảo đảm bền vững trên ổ đĩa khi mất điện**. Nếu ứng dụng cần mức bảo đảm này, cần thiết kế cơ chế đồng bộ dữ liệu phù hợp như `FileDescriptor.sync()` và cân nhắc tính nguyên tử khi thay thế tệp; vấn đề này tách khỏi ý nghĩa của append.

## 8. FileInputStream/FileOutputStream so với Files API

Các lớp cổ điển rất hữu ích để hiểu luồng byte và tương thích mã cũ. Trong Java hiện đại, `java.nio.file.Files` cung cấp thêm các cách mở với ý định rõ ràng:

~~~java
Path path = Path.of("data.bin");

// Các biểu thức này chỉ minh họa cách chọn API.
InputStream in = Files.newInputStream(path);
OutputStream fresh = Files.newOutputStream(path);
OutputStream append = Files.newOutputStream(
        path, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
~~~

Đây là **mảnh mã minh họa**, cần import `java.io.InputStream`, `java.io.OutputStream`, `java.nio.file.Files`, `java.nio.file.Path` và `java.nio.file.StandardOpenOption`. Mỗi luồng phải được quản lý đóng riêng; không nên cùng lúc mở `fresh` và `append` vào cùng tệp trong một ví dụ sử dụng thực tế.

- Mặc định, `Files.newOutputStream(path)` có hiệu ứng `CREATE`, `TRUNCATE_EXISTING` và `WRITE`: tạo mới hoặc truncate tệp cũ rồi ghi.
- Để nối dữ liệu, chỉ rõ `StandardOpenOption.APPEND`; thêm `CREATE` khi muốn tạo nếu chưa tồn tại, như ví dụ.
- Nếu không cho phép ghi đè tệp đã có, xem xét `CREATE_NEW` thay vì mặc định tạo/truncate.
- `Files.copy(...)` và `Files.write(...)` có thể phù hợp cho thao tác tệp ngắn, nhưng vẫn cần hiểu open options và rủi ro ghi đè.

Đừng nhầm `APPEND` với `CREATE` hoặc `TRUNCATE_EXISTING`. Chúng mô tả những quyết định khác nhau: vị trí ghi, việc có tạo tệp hay không, và việc có xóa nội dung cũ hay không. Tránh kết hợp những open option có ý nghĩa xung đột.

## 9. Cách chọn chế độ trong tình huống thực tế

**Tạo kết quả nhị phân mới:** viết với `FileOutputStream` sau khi đã xác minh đường dẫn đích. Nếu ứng dụng không được ghi đè, dùng API có lựa chọn `CREATE_NEW`.

**Thêm bản ghi nhật ký:** dùng chế độ append, viết dấu phân cách và charset phù hợp. Với hệ thống ghi đồng thời hoặc yêu cầu log đáng tin cậy, cân nhắc logger chuyên dụng và cơ chế đồng bộ.

**Đọc và sao chép tệp:** dùng `FileInputStream` đọc theo khối, `FileOutputStream` ghi đúng số byte nhận được. Không cần giải mã dữ liệu nếu chỉ sao chép byte.

**Đọc một file văn bản:** có thể đọc byte qua `FileInputStream` rồi giải mã, nhưng `Files.newBufferedReader` hoặc `InputStreamReader` thường diễn đạt mục đích đúng hơn, đặc biệt khi nội dung lớn.

**Cập nhật một byte ở giữa tệp:** hai lớp stream này không cung cấp truy cập ngẫu nhiên theo vị trí. Xem `RandomAccessFile` hoặc `FileChannel` nếu thật sự cần đọc/ghi theo offset của tệp; offset trong `read(byte[], off, len)` chỉ là offset **trong mảng**.

## 10. Checklist kiến thức

1. `FileInputStream` chỉ đọc, trả `-1` ở EOF; `FileOutputStream` chỉ ghi.
2. `new FileOutputStream(file)` hoặc `(..., false)` **truncate** tệp đã có; `(..., true)` **nối vào cuối**.
3. Append không tự tạo newline, không tạo thư mục cha, không đảm bảo tính nguyên tử của bản ghi nghiệp vụ khi nhiều tác nhân cùng ghi.
4. Khi đọc vào `byte[]`, chỉ xử lý `n` byte mà `read(...)` thực sự trả về.
5. Đóng luồng với `try-with-resources` và xử lý `IOException`; mở luồng đầu ra cũng là thao tác có tác dụng phụ.
6. Byte thô khác văn bản: muốn ghi văn bản thì xác định charset, chẳng hạn UTF-8.
7. Với ứng dụng thật, lựa chọn rõ ràng giữa tạo mới, thay thế và append trước khi mở đích; dùng `Files` và `StandardOpenOption` khi cần diễn đạt các chính sách này.
