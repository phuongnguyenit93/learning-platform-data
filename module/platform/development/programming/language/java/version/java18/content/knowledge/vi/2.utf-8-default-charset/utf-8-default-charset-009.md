# `native.encoding` là thông tin môi trường và không phải công tắc đổi mã hóa của ứng dụng

## 1. Vai trò của `native.encoding`

`native.encoding` là system property được JDK giới thiệu từ **JDK 17** để cung cấp tên charset mà JDK phát hiện từ môi trường máy chủ gốc. Thuộc tính này hữu ích khi cần hiểu encoding mà các ứng dụng chạy trên JDK 17 và những phiên bản trước có thể đã dùng làm default charset.

Từ **JDK 18**, theo **JEP 400**, default charset thông thường của Java SE là UTF-8 trên mọi hệ điều hành. Vì vậy, giá trị `native.encoding` có thể khác với default charset hiện tại:

```text
Charset.defaultCharset() = UTF-8
file.encoding           = UTF-8
native.encoding         = windows-1258
```

Ví dụ trên minh họa một JVM đã chọn UTF-8 làm default charset, trong khi JDK phát hiện môi trường máy chủ có encoding `windows-1258`. Đây không phải trạng thái lỗi: hai giá trị trả lời hai câu hỏi khác nhau.

**Điểm cốt lõi:** `native.encoding` là thông tin để chẩn đoán và có thể dùng làm đầu vào khi một ứng dụng thật sự cần xử lý dữ liệu theo encoding môi trường cũ. Nó **không phải công tắc để đổi charset của JVM, hệ điều hành, file, terminal hay giao thức**.

Bài học thuộc chương **UTF-8 mặc định** của mô-đun `JAVA_VERSION_JAVA18`. Nội dung chỉ tập trung vào cách dùng thuộc tính này còn phù hợp trên JDK hiện đại, đặc biệt trong quá trình nâng cấp ứng dụng từ JDK 17 trở về trước.

## 2. Phân biệt `native.encoding` với các giá trị liên quan

Các thuộc tính dưới đây thường xuất hiện cùng nhau khi kiểm tra lỗi encoding, nhưng chúng không thể thay thế lẫn nhau.

| Giá trị | Ý nghĩa | Câu hỏi được trả lời |
| --- | --- | --- |
| `native.encoding` | Tên encoding môi trường gốc mà JDK phát hiện | Môi trường máy chủ cung cấp encoding nào để tham chiếu? |
| `file.encoding` | Giá trị cấu hình default charset của JDK tại runtime | JDK đang chọn default charset nào? |
| `Charset.defaultCharset()` | Charset mặc định thực tế mà Java API cung cấp | Các API phụ thuộc default charset đang dùng charset nào? |
| `stdin.encoding` | Charset của standard input | Byte nhận từ đầu vào chuẩn cần được giải mã thế nào? |
| `stdout.encoding` | Charset của standard output | Văn bản gửi ra đầu ra chuẩn được mã hóa thế nào? |
| `stderr.encoding` | Charset của standard error | Văn bản gửi ra luồng lỗi chuẩn được mã hóa thế nào? |

Từ JDK 18, default charset thông thường là UTF-8, nhưng các luồng chuẩn có thể dùng encoding riêng. Một file do phần mềm cũ tạo cũng có thể dùng Windows-1258, ISO-8859-1 hoặc một charset khác theo đặc tả của nó.

Do đó, không suy luận rằng:

- File nào trên máy cũng dùng `native.encoding`.
- `System.in`, `System.out` và `System.err` luôn dùng `native.encoding`.
- Default charset của JVM luôn bằng `native.encoding`.
- Thay đổi `native.encoding` sẽ thay đổi encoding của môi trường.

### 2.1. Xem các giá trị trong chương trình

```java
import java.nio.charset.Charset;

public class EncodingProperties {
    public static void main(String[] args) {
        System.out.println("defaultCharset = "
                + Charset.defaultCharset().name());
        System.out.println("file.encoding = "
                + System.getProperty("file.encoding"));
        System.out.println("native.encoding = "
                + System.getProperty("native.encoding"));
        System.out.println("stdout.encoding = "
                + System.getProperty("stdout.encoding"));
    }
}
```

Kết quả phụ thuộc JDK, hệ điều hành và môi trường chạy. Nếu `native.encoding` không tồn tại, `System.getProperty("native.encoding")` trả về `null`. Điều này có thể xảy ra khi chạy trên JDK cũ hơn JDK 17 hoặc trên runtime không cung cấp property này.

## 3. `native.encoding` được giới thiệu để làm gì?

Trước JDK 18, default charset của Java thường được xác định khi JVM khởi động dựa trên môi trường. Trên một số hệ thống Windows, giá trị có thể là charset theo code page; trên macOS hoặc Linux, kết quả có thể phụ thuộc locale và cấu hình môi trường.

Khi JEP 400 chuẩn hóa default charset thành UTF-8 từ JDK 18, ứng dụng cũ cần một cách để:

1. Nhận diện encoding môi trường mà JDK phát hiện.
2. Điều tra những điểm nhập xuất từng phụ thuộc default charset cũ.
3. Tái hiện hành vi tương thích khi cần so sánh.
4. Truyền charset phù hợp vào một API cụ thể nếu hợp đồng dữ liệu thật sự cần encoding môi trường đó.

`native.encoding` phục vụ mục đích cung cấp thông tin. Nó không yêu cầu ứng dụng chuyển toàn bộ dữ liệu sang charset môi trường và không thay đổi quy tắc mặc định UTF-8 của JEP 400.

### 3.1. Quan hệ với `file.encoding`

Từ JDK 18, `file.encoding` được hỗ trợ với hai giá trị cấu hình lúc khởi động:

- `UTF-8`: chọn UTF-8 làm default charset.
- `COMPAT`: xác định default charset theo cách JDK 17 và các bản trước đó đã làm.

Mối quan hệ với `native.encoding`:

| Cấu hình JVM | `Charset.defaultCharset()` | Runtime `file.encoding` | `native.encoding` |
| --- | --- | --- | --- |
| JDK 18+ mặc định, native là Windows-1258 | UTF-8 | UTF-8 | windows-1258 |
| `-Dfile.encoding=UTF-8` | UTF-8 | UTF-8 | windows-1258 |
| `-Dfile.encoding=COMPAT` | Theo encoding môi trường | Bằng runtime `native.encoding` | windows-1258 |

Khi dùng `COMPAT`, JDK chọn default charset theo môi trường như JDK 17 và runtime `file.encoding` được thay bằng runtime `native.encoding`. Khi dùng UTF-8, hai giá trị có thể khác nhau.

**Không nhầm hai cơ chế:** `-Dfile.encoding=COMPAT` là lựa chọn cấu hình default charset được JEP 400 hỗ trợ; `native.encoding` chỉ cho biết tên encoding môi trường mà JDK phát hiện.

## 4. `native.encoding` không thể được dùng làm công tắc cấu hình

Tài liệu Java SE quy định việc đặt `native.encoding` qua dòng lệnh hoặc bằng `System.setProperty()` **không có tác dụng** để thay đổi encoding môi trường.

Ví dụ sau không ép JDK hoặc hệ điều hành chuyển sang UTF-8:

```bash
java -Dnative.encoding=UTF-8 -jar app.jar
```

Tương tự, đoạn code sau không thay đổi encoding gốc:

```java
System.setProperty("native.encoding", "UTF-8");
```

Đặt một giá trị trong system property không thể thay đổi locale, code page của tiến trình, cấu hình terminal hoặc encoding mà JDK đã phát hiện từ môi trường. Không sử dụng cách này để sửa lỗi tiếng Việt.

### 4.1. Nếu muốn chọn default charset của JVM

Trên JDK 18+, cấu hình default charset bằng `file.encoding` lúc khởi động:

```bash
java -Dfile.encoding=UTF-8 -jar app.jar
`java -Dfile.encoding=COMPAT -jar app.jar
```

Chỉ `UTF-8` và `COMPAT` là hai giá trị được hỗ trợ theo đặc tả JEP 400. Các giá trị khác của `file.encoding` không được hỗ trợ.

### 4.2. Nếu muốn đọc file theo encoding môi trường

Đọc `native.encoding` rồi truyền charset đó vào API đọc file, nếu và chỉ nếu hợp đồng của file quy định encoding tương ứng:

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

String nativeName = System.getProperty("native.encoding");
Charset hostCharset = nativeName != null
        ? Charset.forName(nativeName)
        : Charset.defaultCharset();

Path file = Path.of("legacy-host-text.txt");
String content = Files.readString(file, hostCharset);
```

Đây là cách dùng thông tin môi trường tại **một ranh giới nhập xuất cụ thể**. Nó không thay đổi default charset của JVM.

Nếu biết chắc file là UTF-8, hãy dùng `StandardCharsets.UTF_8` thay vì `native.encoding`, kể cả khi hai giá trị hiện tại giống nhau.

## 5. Mẫu đọc `native.encoding` an toàn

Oracle hướng dẫn đọc thuộc tính này và dùng `Charset.defaultCharset()` làm phương án dự phòng nếu property không tồn tại:

```java
import java.nio.charset.Charset;

String nativeEncoding = System.getProperty("native.encoding");

Charset hostCharset = nativeEncoding != null
        ? Charset.forName(nativeEncoding)
        : Charset.defaultCharset();

System.out.println("Host charset candidate = "
        + hostCharset.name());
```

Cách làm này có các ý nghĩa:

- Trên JDK cung cấp `native.encoding`, ứng dụng lấy charset mà JDK phát hiện từ môi trường.
- Trên runtime không cung cấp property, ứng dụng dùng default charset hiện tại làm phương án dự phòng.
- Kết quả `hostCharset` chỉ là một charset ứng viên cho tình huống cần tương thích với môi trường, không phải charset mặc định của mọi file hoặc giao thức.

### 5.1. Vì sao cần kiểm tra `null`?

Không phải runtime Java nào cũng có `native.encoding`. Property này được giới thiệu từ JDK 17, vì vậy thư viện có thể cần chạy trên JDK cũ hơn hoặc runtime có hành vi khác.

Nếu gọi trực tiếp:

```java
Charset.forName(System.getProperty("native.encoding"));
```

mà property trả về `null`, ứng dụng sẽ gặp lỗi khi chuyển đổi tên charset. Hãy kiểm tra giá trị trước khi gọi `Charset.forName`.

### 5.2. Xử lý tên charset không hợp lệ

Trên JDK chính thức, `native.encoding` do JDK cung cấp nên giá trị bình thường phải là tên charset được hỗ trợ. Nếu ứng dụng nhận giá trị từ một runtime không chuẩn hoặc nguồn cấu hình khác, `Charset.forName(name)` có thể ném `IllegalCharsetNameException` hoặc `UnsupportedCharsetException`.

Có thể đóng gói việc đọc property thành hàm:

```java
import java.nio.charset.Charset;
import java.nio.charset.IllegalCharsetNameException;
import java.nio.charset.UnsupportedCharsetException;

static Charset hostCharsetOrDefault() {
    String name = System.getProperty("native.encoding");
    if (name == null || name.isBlank()) {
        return Charset.defaultCharset();
    }

    try {
        return Charset.forName(name);
    } catch (IllegalCharsetNameException
             | UnsupportedCharsetException ex) {
        return Charset.defaultCharset();
    }
}
```

Fallback này là lựa chọn phòng vệ cho ứng dụng cần hỗ trợ nhiều runtime. Nếu charset môi trường là một phần bắt buộc của hợp đồng dữ liệu, không nên âm thầm fallback: hãy báo lỗi cấu hình để tránh đọc sai dữ liệu.

## 6. Dùng charset lấy từ môi trường ở đúng nơi

Một trường hợp Oracle nêu là ứng dụng muốn tạo reader có hành vi tương thích với default charset kiểu JDK 17 và cũ hơn. Có thể truyền charset lấy từ `native.encoding` vào constructor:

```java
import java.io.FileReader;
import java.nio.charset.Charset;
import java.nio.file.Path;

String nativeName = System.getProperty("native.encoding");
Charset hostCharset = nativeName != null
        ? Charset.forName(nativeName)
        : Charset.defaultCharset();

try (var reader = new FileReader(
        Path.of("file.txt").toFile(), hostCharset)) {
    // Đọc file theo charset được chọn.
}
```

Cách này phù hợp nếu file thực sự được tạo theo encoding môi trường cũ. Constructor nhận `Charset` giúp hành vi được chỉ định rõ, thay vì phụ thuộc default charset hiện tại của JVM.

### 6.1. Không dùng native charset cho mọi file

Giả sử cùng một ứng dụng phải đọc ba nguồn:

| Nguồn | Hợp đồng encoding | Charset nên chọn |
| --- | --- | --- |
| File mới do dịch vụ tạo | UTF-8 | `StandardCharsets.UTF_8` |
| File legacy do ứng dụng desktop cũ tạo | Windows-1258 | `Charset.forName("windows-1258")` |
| Một file lịch sử đã được xác nhận dùng encoding môi trường máy cũ | Encoding tương ứng với môi trường đó | Có thể dùng charset lấy từ `native.encoding` |

Chỉ nguồn thứ ba có lý do dùng `native.encoding`. Nếu áp dụng nó cho hai nguồn còn lại, ứng dụng có thể giải mã sai dữ liệu.

### 6.2. Không dùng nó cho HTTP hoặc message queue nếu giao thức quy định UTF-8

HTTP payload, JSON, message queue hoặc giao thức nội bộ phải tuân theo đặc tả của từng giao thức. Nếu payload được quy định UTF-8, hãy dùng UTF-8 rõ ràng:

```java
byte[] payload = message.getBytes(StandardCharsets.UTF_8);
String received = new String(payload, StandardCharsets.UTF_8);
```

Không dùng charset của máy chủ gửi hoặc nhận để thay đổi hợp đồng giao tiếp. Hai máy chủ có thể có `native.encoding` khác nhau nhưng vẫn cần trao đổi cùng một dãy byte UTF-8.

## 7. Phân biệt encoding môi trường với encoding của console

Một nhầm lẫn phổ biến là nghĩ `native.encoding` quyết định cách terminal hiển thị tiếng Việt. Trên JDK hiện đại, các luồng chuẩn có charset riêng:

- `stdin.encoding` cho `System.in`.
- `stdout.encoding` cho `System.out`.
- `stderr.encoding` cho `System.err`.

Có thể quan sát:

```java
System.out.println("native = "
        + System.getProperty("native.encoding"));
System.out.println("default = "
        + java.nio.charset.Charset.defaultCharset().name());
System.out.println("stdout = "
        + System.out.charset().name());
System.err.println("stderr = "
        + System.err.charset().name());
```

`System.out.charset()` và `System.err.charset()` có từ Java 18. Chúng cho biết charset của các `PrintStream` tương ứng; không dùng `native.encoding` để suy ra các giá trị này.

Nếu ứng dụng đọc dữ liệu từ bàn phím, hãy kiểm tra `stdin.encoding` hoặc dùng API console phù hợp. Nếu ứng dụng đọc file, hãy dùng charset được quy định bởi file. Nếu ứng dụng trao đổi qua mạng, hãy dùng charset được quy định bởi giao thức.

## 8. Kiểm tra `native.encoding` từ dòng lệnh

Dùng `-XshowSettings:properties` để xem system properties của một tiến trình Java:

```bash
java -XshowSettings:properties -version
```

Trên Linux/macOS, lọc riêng thuộc tính cần xem:

```bash
java -XshowSettings:properties -version 2>&1 \
  | grep -E 'native.encoding|file.encoding'
```

Trên Windows PowerShell:

```powershell
java -XshowSettings:properties -version 2>&1 |
    Select-String 'native.encoding|file.encoding'
```

Nếu cần kiểm tra ứng dụng thật, chạy lệnh với cùng JDK, user, locale, container và cấu hình môi trường của ứng dụng. Kết quả từ một terminal khác có thể không phản ánh chính xác tiến trình production.

### 8.1. So sánh UTF-8 và COMPAT

Trên JDK 18+, có thể so sánh hai chế độ default charset:

```bash
java -Dfile.encoding=UTF-8 -jar app.jar
java -Dfile.encoding=COMPAT -jar app.jar
```

- Ở chế độ UTF-8, default charset là UTF-8; `native.encoding` vẫn cung cấp thông tin encoding môi trường.
- Ở chế độ COMPAT, default charset được xác định như JDK 17 và trước đó; runtime `file.encoding` bằng runtime `native.encoding`.

Đây là phép thử tương thích khi nâng cấp. Nó không làm thay đổi `native.encoding` và không thay thế việc khai báo charset trong hợp đồng dữ liệu.

## 9. `native.encoding` và encoding của mã nguồn Java

Khi biên dịch, `javac` mặc định đọc file nguồn theo default charset nếu không chỉ định `-encoding`. Nếu mã nguồn được lưu bằng UTF-8, nên khai báo:

```bash
javac -encoding UTF-8 MyApplication.java
```

Oracle cũng nêu rằng nếu nhóm phát triển chủ động lưu source file bằng encoding khác UTF-8, có thể truyền giá trị `native.encoding` vào tùy chọn `-encoding` để phù hợp với môi trường. Tuy nhiên, với dự án mới và repository dùng chung, chuẩn hóa source file UTF-8 thường dễ bảo trì và portable hơn.

Không nhầm encoding source code với encoding file dữ liệu lúc runtime. `native.encoding` không tự chuyển đổi file `.java`; tùy chọn `-encoding` của compiler mới xác định cách `javac` giải mã source file.

## 10. Tình huống thực tế: ứng dụng nâng cấp từ JDK 17

Một ứng dụng chạy trên máy Windows có native encoding là `windows-1258`. Ứng dụng cũ đọc file lịch sử bằng:

```java
new FileReader("archive.txt");
```

Trên JDK 17, default charset có thể theo encoding môi trường và file được đọc đúng. Khi nâng cấp lên JDK 18+, default charset chuyển thành UTF-8. Nếu file vẫn là Windows-1258, dữ liệu có thể bị giải mã sai.

Có thể điều tra:

1. Đọc `native.encoding` để biết encoding môi trường mà JDK phát hiện.
2. So sánh `Charset.defaultCharset()` trên JDK 18+.
3. Chạy thử `-Dfile.encoding=COMPAT` trên JDK 18+ để tái hiện default charset kiểu JDK 17.
4. Xác nhận file lịch sử thực sự dùng Windows-1258.
5. Sửa code để chỉ định charset ở reader.

Ví dụ sửa theo hợp đồng file:

```java
import java.io.FileReader;
import java.nio.charset.Charset;
import java.nio.file.Path;

String name = System.getProperty("native.encoding");
Charset source = name != null
        ? Charset.forName(name)
        : Charset.defaultCharset();

try (var reader = new FileReader(
        Path.of("archive.txt").toFile(), source)) {
    // Đọc nội dung theo encoding đã xác nhận.
}
```

Nếu file thực tế được tạo bằng Windows-1258, hãy xác nhận charset đó bằng tài liệu định dạng hoặc dữ liệu nguồn trước khi dùng. `native.encoding` chỉ là manh mối từ môi trường; nó không chứng minh mọi file cũ trên máy đều dùng cùng encoding.

## 11. Những suy luận sai cần tránh

| Suy luận | Thực tế |
| --- | --- |
| `native.encoding` là default charset của JDK 18+ | Default charset thông thường là UTF-8; native có thể khác |
| Đặt `-Dnative.encoding=UTF-8` sẽ đổi encoding môi trường | Tài liệu Java quy định việc đặt property này không có tác dụng |
| Gọi `System.setProperty("native.encoding", ...)` sẽ đổi code page hệ điều hành | Nó không thay đổi môi trường gốc |
| Mọi file trên máy đều dùng native encoding | Charset file do định dạng hoặc ứng dụng tạo file quy định |
| Console luôn dùng native encoding | Standard streams có charset riêng |
| `native.encoding` là charset bắt buộc cho HTTP/JSON | Giao thức quy định charset của payload |
| Dùng `COMPAT` sẽ thay đổi `native.encoding` | COMPAT chỉ ảnh hưởng lựa chọn default charset; native vẫn là thông tin môi trường |
| Có thể bỏ kiểm tra charset vì JDK 18+ đã dùng UTF-8 | File legacy và hệ thống bên ngoài vẫn có thể dùng encoding khác |

## 12. Bài tập tự kiểm tra

**Bài 1.** Trên JDK 18+, `Charset.defaultCharset()` trả về UTF-8 còn `native.encoding` là Windows-1258. Có phải JVM đang cấu hình sai không?

*Đáp án:* Không. JEP 400 chọn UTF-8 làm default charset; `native.encoding` phản ánh encoding môi trường gốc mà JDK phát hiện.

**Bài 2.** Có thể truyền `-Dnative.encoding=UTF-8` để yêu cầu JVM đổi encoding môi trường không?

*Đáp án:* Không. Tài liệu Java quy định đặt `native.encoding` qua command line hoặc `System.setProperty()` không có tác dụng đổi encoding môi trường.

**Bài 3.** Khi `native.encoding` không tồn tại, nên xử lý thế nào nếu cần lấy charset ứng viên tương thích?

*Đáp án:* Kiểm tra `null`; Oracle hướng dẫn fallback về `Charset.defaultCharset()`. Nếu hợp đồng yêu cầu một charset cụ thể, không nên fallback âm thầm mà cần báo lỗi hoặc lấy charset từ cấu hình đáng tin cậy.

**Bài 4.** Một API nhận JSON quy định UTF-8. Máy chủ có `native.encoding=windows-1258`. Nên mã hóa JSON theo charset nào?

*Đáp án:* UTF-8 theo hợp đồng JSON, ví dụ `StandardCharsets.UTF_8`. Không dùng native encoding của máy chủ để mã hóa payload.

**Bài 5.** Một file legacy được tạo theo encoding môi trường cũ. `native.encoding` có thể giúp ích như thế nào?

*Đáp án:* Nó cung cấp tên encoding mà JDK phát hiện từ môi trường, có thể dùng làm charset khi đọc nếu đã xác nhận file thực sự được tạo theo encoding đó. Sau khi xác định, nên ghi rõ charset trong code hoặc metadata của file.

## 13. Ghi nhớ

`native.encoding` là thông tin về encoding môi trường gốc do JDK phát hiện, được giới thiệu từ JDK 17. Từ JDK 18, UTF-8 là default charset thông thường theo JEP 400, vì vậy hai giá trị có thể khác nhau.

Không thể dùng `native.encoding` làm công tắc đổi mã hóa bằng tùy chọn dòng lệnh hoặc `System.setProperty()`. Khi ứng dụng cần tương thích với dữ liệu theo encoding môi trường cũ, có thể đọc property và truyền charset thu được vào một reader/writer cụ thể, sau khi xác nhận hợp đồng dữ liệu. Với file mới và giao thức hiện đại, hãy dùng charset được quy định rõ, thường là `StandardCharsets.UTF_8`.

### Tài liệu tham khảo chính thức

- [OpenJDK — JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400).
- [Oracle Java SE 27 — Supported Encodings: native.encoding, default charset và standard streams](https://docs.oracle.com/en/java/javase/27/intl/supported-encodings.html).
- [Oracle Java SE 27 — Migration Guide: Be Aware of the Default Charset](https://docs.oracle.com/en/java/javase/27/migrate/migrating-from-jdk-8-later-jdk-releases.html).
- [Oracle Java SE 27 — Charset.defaultCharset()](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/Charset.html).
- [Oracle Java SE 27 — System: Standard System Properties](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/System.html).
