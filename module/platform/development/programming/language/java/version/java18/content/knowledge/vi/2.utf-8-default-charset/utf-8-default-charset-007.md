# Giá trị UTF-8 và COMPAT của `file.encoding`: cấu hình khởi động được hỗ trợ và giới hạn sử dụng

## 1. Vì sao JDK có hai lựa chọn này?

Từ **JDK 18**, **UTF-8 là charset mặc định** cho các Java SE API phụ thuộc default charset trên mọi hệ điều hành theo **JEP 400**. Nhờ đó, ứng dụng thường có hành vi giống nhau khi chạy trên Windows, Linux, macOS hoặc trong container.

Tuy nhiên, một số ứng dụng cũ được viết khi default charset phụ thuộc vào hệ điều hành và locale. Ví dụ, một ứng dụng chạy trên Windows có thể đã đọc file theo Windows-1258 thông qua `new FileReader(file)` mà không chỉ định charset. Khi nâng cấp lên JDK 18+, constructor đó mặc định dùng UTF-8; dữ liệu file cũ có thể bị đọc sai.

Để hỗ trợ kiểm tra và chuyển đổi, JDK 18+ cho phép đặt thuộc tính khởi động `file.encoding` theo **hai giá trị được hỗ trợ**:

- `UTF-8`: chọn UTF-8 làm default charset.
- `COMPAT`: chọn default charset theo cách JDK 17 và các bản trước đó xác định từ môi trường.

Đây là hai chế độ **cấu hình khi khởi động JVM**. `COMPAT` chủ yếu hữu ích để điều tra sự phụ thuộc encoding trong quá trình nâng cấp. Với ứng dụng mới hoặc dữ liệu có hợp đồng rõ ràng, nên chỉ định charset ngay tại điểm đọc/ghi.

## 2. `file.encoding=UTF-8` có nghĩa gì?

`file.encoding` là system property liên quan đến default charset của JDK. Trên JDK 18 trở lên, nếu không đặt chế độ tương thích, UTF-8 là mặc định thông thường.

Có thể yêu cầu UTF-8 rõ ràng ngay khi khởi động:

```bash
java -Dfile.encoding=UTF-8 -jar app.jar
```

Hoặc với ứng dụng chạy từ classpath:

```bash
java -Dfile.encoding=UTF-8 -cp "classes;lib/*" com.example.Main
```

Trên Linux/macOS, dấu phân cách classpath thường là `:` thay vì `;`.

Khi JVM khởi động với giá trị này:

- `Charset.defaultCharset()` trả về UTF-8.
- `file.encoding` có giá trị runtime là `UTF-8`.
- `native.encoding` vẫn phản ánh encoding của môi trường máy chủ; nó có thể khác UTF-8.
- Các API thật sự dùng default charset sẽ dùng UTF-8, trừ những API có quy tắc encoding riêng hoặc những luồng chuẩn có charset riêng.

Ví dụ kiểm tra trong chương trình:

```java
import java.nio.charset.Charset;

public class EncodingMode {
    public static void main(String[] args) {
        System.out.println("default = "
                + Charset.defaultCharset().name());
        System.out.println("file.encoding = "
                + System.getProperty("file.encoding"));
        System.out.println("native.encoding = "
                + System.getProperty("native.encoding"));
    }
}
```

Kết quả minh họa trên máy có native encoding là Windows-1258:

```text
default = UTF-8
file.encoding = UTF-8
native.encoding = windows-1258
```

Hai giá trị `file.encoding` và `native.encoding` khác nhau là hoàn toàn hợp lệ: JVM đã chọn UTF-8, còn môi trường máy chủ có encoding gốc khác.

## 3. `file.encoding=COMPAT` có nghĩa gì?

`COMPAT` là lựa chọn của JEP 400 để khôi phục cách xác định default charset như JDK 17 và các phiên bản trước. Default charset khi đó được xác định theo môi trường máy chủ, chẳng hạn locale hoặc encoding hệ điều hành.

Chạy chương trình với:

```bash
java -Dfile.encoding=COMPAT -jar app.jar
```

Trong chế độ này:

- Default charset được xác định theo cách JDK 17 và trước đó đã dùng.
- `Charset.defaultCharset()` phản ánh charset tương thích đó.
- Giá trị runtime của `file.encoding` được thay bằng giá trị runtime của `native.encoding`.
- `native.encoding` vẫn là thông tin về encoding môi trường được JDK phát hiện.

Ví dụ minh họa nếu môi trường máy chủ có native encoding là Windows-1258:

```text
default = windows-1258
file.encoding = windows-1258
native.encoding = windows-1258
```

Nếu môi trường máy chủ vốn dùng UTF-8, chế độ `COMPAT` có thể vẫn cho kết quả UTF-8. Vì thế, không phải cứ thấy `COMPAT` là chắc chắn default charset khác UTF-8.

### 3.1. Bảng so sánh

Giả sử `native.encoding` của môi trường là `windows-1258`:

| Cách khởi động | `Charset.defaultCharset()` | Runtime `file.encoding` | `native.encoding` |
| --- | --- | --- | --- |
| Không đặt thuộc tính trên JDK 18+ | UTF-8 | UTF-8 | windows-1258 |
| `-Dfile.encoding=UTF-8` | UTF-8 | UTF-8 | windows-1258 |
| `-Dfile.encoding=COMPAT` | windows-1258 | windows-1258 | windows-1258 |

Bảng này minh họa quy tắc JDK 18+ khi native encoding khác UTF-8. Kết quả thực tế của `COMPAT` phụ thuộc môi trường đang chạy.

## 4. Vì sao chỉ UTF-8 và COMPAT được hỗ trợ?

Trên JDK 18+, tài liệu Java SE quy định `file.encoding` có thể được đặt khi khởi động với một trong hai giá trị `UTF-8` hoặc `COMPAT`. **Các giá trị khác không được hỗ trợ** và có hành vi không được đặc tả.

Ví dụ sau không phải cách cấu hình hợp lệ được Java SE bảo đảm:

```bash
java -Dfile.encoding=windows-1258 -jar app.jar
```

Không nên dựa vào hành vi quan sát được trên một JDK cụ thể để xem đây là cách ép default charset sang Windows-1258. Một bản JDK có thể xử lý khác bản khác hoặc thay đổi trong tương lai.

Nếu file thực sự dùng Windows-1258, hãy chỉ định charset tại API đọc file:

```java
import java.nio.charset.Charset;
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("legacy.txt");
Charset sourceCharset = Charset.forName("windows-1258");

String content = Files.readString(file, sourceCharset);
```

Nếu cần ghi ra một định dạng legacy cụ thể, cũng truyền charset đích vào API ghi. Cách này giữ cho phần còn lại của ứng dụng vẫn dùng UTF-8 mặc định mà không ép toàn JVM phụ thuộc một code page cũ.

## 5. Phải đặt `file.encoding` ở thời điểm nào?

`file.encoding` là cấu hình được JDK đọc trong quá trình khởi động. Hãy truyền thuộc tính trước tên lớp chính hoặc trước tùy chọn `-jar`:

```bash
java -Dfile.encoding=UTF-8 -jar app.jar
```

Không đặt thuộc tính sau tên lớp chính:

```bash
# Sai vị trí: đối số này được truyền cho main(), không phải JVM option.
java -jar app.jar -Dfile.encoding=COMPAT
```

Nếu chạy từ classpath, nguyên tắc tương tự:

```bash
java -Dfile.encoding=COMPAT -cp app.jar com.example.Main
```

`-Dname=value` là tùy chọn JVM. Nó phải xuất hiện trong phần đối số JVM, trước lớp chính hoặc `-jar`.

### 5.1. Không thay đổi default charset giữa lúc chạy

Không dùng đoạn code sau với kỳ vọng đổi default charset:

```java
System.setProperty("file.encoding", "COMPAT");
```

Thay đổi giá trị property sau khi JVM đã khởi tạo không phải cơ chế được hỗ trợ để cấu hình lại default charset. Charset có thể đã được xác định và cache trong quá trình khởi động hoặc lần sử dụng đầu tiên.

Tương tự, không dùng `System.setProperty("file.encoding", "windows-1258")` để ép các API đang chạy chuyển sang charset đó. Nếu một thao tác cần encoding khác, truyền `Charset` trực tiếp:

```java
Files.readString(path, Charset.forName("windows-1258"));
```

Cách này điều khiển đúng một điểm nhập xuất mà không làm thay đổi hành vi của các thành phần khác.

## 6. Quan hệ với `native.encoding`

`native.encoding` được giới thiệu từ JDK 17 để cung cấp tên encoding của môi trường máy chủ. Nó giúp xác định charset mà JDK 17 và các bản trước có thể đã dùng làm default charset.

JEP 400 mô tả quan hệ như sau:

- Khi `file.encoding` được đặt là `COMPAT` lúc khởi động, giá trị runtime của `file.encoding` sẽ bằng giá trị runtime của `native.encoding`.
- Khi `file.encoding` được đặt là `UTF-8`, giá trị runtime của `file.encoding` có thể khác `native.encoding`.

Không nên xem `native.encoding` là tùy chọn cấu hình. Đây là thông tin được JDK phát hiện từ môi trường. Đặt `-Dnative.encoding=UTF-8` hoặc gọi `System.setProperty("native.encoding", "UTF-8")` không thay đổi encoding gốc của hệ điều hành.

Có thể kiểm tra bằng:

```bash
java -XshowSettings:properties -version
```

Trên Linux/macOS có thể lọc:

```bash
java -XshowSettings:properties -version 2>&1 \
  | grep -E 'file.encoding|native.encoding'
```

Trên Windows PowerShell:

```powershell
java -XshowSettings:properties -version 2>&1 |
    Select-String 'file.encoding|native.encoding'
```

Các lệnh này hiển thị cấu hình runtime của chính tiến trình Java được khởi chạy. Khi kiểm tra ứng dụng đang chạy trong container hoặc service, hãy chạy lệnh với cùng JDK và môi trường triển khai tương ứng.

## 7. Thử nghiệm để hiểu khác biệt giữa hai chế độ

Ví dụ sau tạo file UTF-8 bằng API có charset tường minh, sau đó đọc file bằng một API phụ thuộc default charset và một API luôn dùng UTF-8:

```java
import java.io.FileReader;
import java.io.StringWriter;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileEncodingModeDemo {
    public static void main(String[] args) throws Exception {
        Path file = Path.of("message.txt");
        String original = "Tiếng Việt: cà phê";

        // Ghi file theo UTF-8 một cách tường minh.
        Files.writeString(file, original, StandardCharsets.UTF_8);

        // Files.readString không truyền charset vẫn dùng UTF-8 cố định.
        String byFiles = Files.readString(file);

        // FileReader không truyền charset dùng default charset.
        String byDefault;
        try (var reader = new FileReader(file.toFile())) {
            var buffer = new StringWriter();
            reader.transferTo(buffer);
            byDefault = buffer.toString();
        }

        System.out.println("default = " + Charset.defaultCharset().name());
        System.out.println("Files matches = " + original.equals(byFiles));
        System.out.println("FileReader matches = "
                + original.equals(byDefault));
    }
}
```

Biên dịch với source encoding UTF-8:

```bash
javac -encoding UTF-8 FileEncodingModeDemo.java
```

Chạy với UTF-8:

```bash
java -Dfile.encoding=UTF-8 FileEncodingModeDemo
```

Chạy với chế độ tương thích:

```bash
java -Dfile.encoding=COMPAT FileEncodingModeDemo
```

Nếu `native.encoding` của máy khác UTF-8, kết quả có thể như sau:

```text
# Chế độ UTF-8
default = UTF-8
Files matches = true
FileReader matches = true

# Chế độ COMPAT trên máy native encoding Windows-1258
default = windows-1258
Files matches = true
FileReader matches = false
```

Kết quả cho thấy:

- `Files.readString(file)` không truyền charset vẫn dùng UTF-8 theo hợp đồng API.
- `FileReader(file)` không truyền charset dùng default charset, vì vậy kết quả thay đổi theo chế độ khởi động.
- Khi `COMPAT` chọn charset khác UTF-8, `FileReader` có thể đọc sai file UTF-8.

Nếu native encoding của máy là UTF-8, hai lần chạy có thể cho kết quả giống nhau. Hãy kiểm thử trên môi trường có encoding gốc khác UTF-8 hoặc tạo test kiểm soát dữ liệu và charset để xác nhận hành vi.

## 8. `COMPAT` nên dùng khi nào?

`COMPAT` là công cụ chuyển đổi hữu ích khi một ứng dụng có lịch sử phụ thuộc default charset của hệ điều hành. Nó giúp nhóm phát triển so sánh hành vi trước và sau khi nâng cấp JDK.

Các trường hợp nên dùng trong giai đoạn điều tra:

- Tái hiện hành vi default charset như JDK 17 trở về trước.
- Xác định các API không chỉ định charset đang đọc hoặc ghi dữ liệu theo môi trường cũ.
- So sánh kết quả giữa `UTF-8` và `COMPAT` trong CI hoặc môi trường thử nghiệm.
- Tìm các file, log hoặc tích hợp bên ngoài có thể đang dựa vào code page cũ.

Không nên mặc định giữ `COMPAT` làm cấu hình lâu dài cho mọi môi trường. Nếu ứng dụng cần một file Windows-1258, hãy khai báo Windows-1258 cho đúng file đó. Nếu giao thức yêu cầu UTF-8, hãy dùng UTF-8 tường minh.

Cách tiếp cận này giúp ứng dụng có hợp đồng rõ ràng và không phụ thuộc encoding máy chủ.

## 9. Những giới hạn khác cần nhớ

### 9.1. Không phải mọi API đều dùng `file.encoding`

JEP 400 chuẩn hóa default charset của các API phụ thuộc default charset. Một số API đã có quy tắc UTF-8 cố định, ví dụ `Files.readString(path)` và `Files.writeString(path, text)`; một số API có charset riêng, ví dụ `Properties.load(InputStream)` dùng ISO-8859-1 theo hợp đồng của nó.

Các luồng chuẩn `System.in`, `System.out`, `System.err` cũng có thể sử dụng charset riêng thông qua `stdin.encoding`, `stdout.encoding`, `stderr.encoding` và cấu hình console. Do đó, thay đổi `file.encoding` không có nghĩa mọi dữ liệu văn bản của ứng dụng đều tự chuyển sang UTF-8.

### 9.2. `file.encoding` không chuyển đổi dữ liệu đã lưu

Đặt `-Dfile.encoding=UTF-8` không chuyển file Windows-1258 cũ thành UTF-8. Nó chỉ ảnh hưởng đến default charset mà các API liên quan sử dụng khi chạy JVM.

Muốn chuyển đổi file cũ, phải:

1. Xác định charset nguồn thật sự.
2. Giải mã byte bằng charset nguồn.
3. Mã hóa nội dung thành UTF-8.
4. Kiểm tra byte và văn bản sau khi ghi.

### 9.3. Không dùng default charset làm hợp đồng mạng

Một giao thức mạng cần quy định charset của payload. Hai ứng dụng có thể chạy trên cùng JDK nhưng cấu hình khởi động khác nhau. Nếu một bên dựa vào default charset và bên kia dựa vào UTF-8 tường minh, dữ liệu có thể không nhất quán.

Hãy dùng `StandardCharsets.UTF_8` tại ranh giới HTTP, message queue hoặc file trao đổi khi hợp đồng yêu cầu UTF-8.

### 9.4. Source encoding là một cấu hình riêng

`javac` mặc định đọc file `.java` theo default charset nếu không chỉ định `-encoding`. Để mã nguồn có tiếng Việt được biên dịch nhất quán, nên cấu hình:

```bash
javac -encoding UTF-8 MyApplication.java
```

Đây là cấu hình của quá trình biên dịch, khác với `file.encoding` của JVM lúc chạy.

## 10. Quy trình kiểm tra khi nâng cấp lên JDK 18+

1. Ghi nhận `native.encoding` trên môi trường cũ hoặc môi trường chạy ứng dụng.
2. Chạy ứng dụng trên JDK 18+ với `-Dfile.encoding=UTF-8`.
3. Chạy lại với `-Dfile.encoding=COMPAT` để so sánh hành vi cũ.
4. Tìm các lời gọi phụ thuộc default charset như `new String(bytes)`, `getBytes()`, `FileReader(file)` và `InputStreamReader(stream)`.
5. Xác nhận charset thật sự của file, HTTP payload và các hệ thống tích hợp.
6. Thay các điểm nhập xuất bằng overload nhận `Charset` theo hợp đồng dữ liệu.
7. Chạy test với tiếng Việt, emoji, byte không hợp lệ và file legacy.
8. Đưa cấu hình encoding của source code và dữ liệu trao đổi vào quy trình build/deploy.

### Những lỗi suy luận thường gặp

| Suy luận | Thực tế |
| --- | --- |
| Có thể đặt `-Dfile.encoding=windows-1258` để ép default charset | Giá trị này không được hỗ trợ theo đặc tả JDK 18+. |
| `COMPAT` luôn có nghĩa là Windows-1252 hoặc Windows-1258 | Nó phụ thuộc encoding môi trường thực tế. |
| `COMPAT` thay đổi charset của toàn bộ hệ điều hành | Nó chỉ chọn default charset của JVM theo cơ chế tương thích. |
| Gọi `System.setProperty` sau khởi động có thể đổi charset | Không phải cơ chế cấu hình default charset được hỗ trợ. |
| `file.encoding=UTF-8` chuyển các file cũ sang UTF-8 | Không có chuyển đổi dữ liệu trên đĩa. |
| `native.encoding` có thể đặt để điều khiển `COMPAT` | Đây là thông tin môi trường do JDK phát hiện. |
| Mọi luồng console đều theo `file.encoding` | Standard streams có charset riêng. |

## 11. Bài tập tự kiểm tra

**Bài 1.** JDK 18+ hỗ trợ những giá trị nào của `file.encoding` khi đặt trên dòng lệnh?

*Đáp án:* `UTF-8` và `COMPAT`. Các giá trị khác không được hỗ trợ theo đặc tả.

**Bài 2.** Trên máy có `native.encoding=windows-1258`, nếu chạy `-Dfile.encoding=UTF-8`, hai thuộc tính runtime có bắt buộc giống nhau không?

*Đáp án:* Không. `file.encoding` là UTF-8, còn `native.encoding` có thể vẫn là Windows-1258.

**Bài 3.** Nếu chạy `-Dfile.encoding=COMPAT`, runtime `file.encoding` có giá trị gì?

*Đáp án:* Nó được thay bằng giá trị runtime của `native.encoding`; default charset được xác định theo cách JDK 17 và trước đó đã dùng.

**Bài 4.** Có thể gọi `System.setProperty("file.encoding", "COMPAT")` trong `main()` để chuyển ứng dụng sang chế độ tương thích không?

*Đáp án:* Không. Phải đặt tùy chọn JVM trước khi khởi chạy lớp chính hoặc `-jar`; thay đổi property sau khởi động không cấu hình lại default charset.

**Bài 5.** Một file UTF-8 được đọc bằng `FileReader(file)` trên JDK 18+ chạy với `COMPAT` và native encoding Windows-1258. Vì sao có thể bị lỗi?

*Đáp án:* Constructor `FileReader(file)` dùng default charset. Trong chế độ `COMPAT`, default charset được xác định theo môi trường cũ, có thể là Windows-1258, trong khi file thực tế là UTF-8.

## 12. Ghi nhớ

`-Dfile.encoding=UTF-8` chọn UTF-8 làm default charset cho JVM khi khởi động. `-Dfile.encoding=COMPAT` chọn default charset theo cách JDK 17 và các bản trước đó đã dùng. Đây là hai giá trị được hỗ trợ từ JDK 18; các giá trị khác không được đặc tả.

`COMPAT` có ích để điều tra và hỗ trợ chuyển đổi ứng dụng cũ. Nó không phải giải pháp thay thế cho hợp đồng dữ liệu rõ ràng. Khi biết file hoặc giao thức yêu cầu charset nào, hãy truyền charset đó trực tiếp vào API. Cách làm này giữ cho dữ liệu tiếng Việt chính xác và ứng dụng ổn định trên các JDK hiện đại.

### Tài liệu tham khảo chính thức

- [OpenJDK — JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400).
- [Oracle Java SE 27 — Migration Guide: Be Aware of the Default Charset](https://docs.oracle.com/en/java/javase/27/migrate/migrating-from-jdk-8-later-jdk-releases.html).
- [Oracle Java SE 27 — System: Standard System Properties](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/System.html).
- [Oracle Java SE 27 — Supported Encodings and Default Charset](https://docs.oracle.com/en/java/javase/27/intl/supported-encodings.html).
- [Oracle Java SE 27 — Charset.defaultCharset()](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/Charset.html).
