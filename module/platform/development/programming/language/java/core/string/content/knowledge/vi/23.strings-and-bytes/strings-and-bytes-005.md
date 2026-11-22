# Charset mặc định và ảnh hưởng của môi trường, phiên bản JDK

## 1. Vì sao charset mặc định quan trọng?

Trong Java, `String` chứa các ký tự Unicode; còn file, socket, thông điệp và nhiều API I/O trao đổi **byte**. **Encoding** biến ký tự thành byte; **decoding** biến byte thành ký tự. Một dãy byte chỉ có thể được giải mã đúng khi phía đọc dùng đúng charset mà phía ghi đã dùng.

**Charset mặc định** (*default charset*) của một JVM được lấy bằng `Charset.defaultCharset()`. Một số API tự sử dụng charset này khi lập trình viên không truyền đối số `Charset` hay tên encoding. Vì vậy, cùng một mã nguồn có thể ghi ra những byte khác nhau, hoặc đọc cùng một file ra kết quả khác nhau, khi đổi máy chạy hay phiên bản JDK.

Ví dụ, chữ `é` trong UTF-8 có hai byte hex `C3 A9`; trong ISO-8859-1 chỉ có một byte `E9`. Đọc hai byte UTF-8 `C3 A9` dưới ISO-8859-1 sẽ tạo ra hai ký tự `Ã©` thay vì một ký tự `é` — một dạng **mojibake** (chữ bị lỗi mã hóa). Nếu charset không thể biểu diễn một ký tự khi ghi, tùy API/cấu hình bộ mã hóa, ký tự có thể bị thay thế hoặc thao tác có thể phát sinh lỗi; không nên mặc định rằng mọi chuyển đổi đều bảo toàn dữ liệu.

Phân biệt ba điều:

- `String.length()` đếm số *UTF-16 code unit*, không đếm byte UTF-8 và cũng không nhất thiết bằng số ký tự người dùng nhìn thấy.
- `s.getBytes(charset).length` là số byte thực tế sau khi mã hóa bằng charset được chỉ định.
- Charset mặc định chỉ có ý nghĩa với những API **thực sự sử dụng** nó. Một API đã quy định UTF-8 hoặc đã nhận charset tường minh thì không phụ thuộc vào default charset.

## 2. Quy tắc theo phiên bản JDK

| Phiên bản | Charset mặc định thông thường | Hệ quả |
| --- | --- | --- |
| JDK 17 trở xuống | Phụ thuộc hệ điều hành, locale, cấu hình môi trường tại lúc JVM khởi động; nhiều máy Linux/macOS thường dùng UTF-8, một số môi trường Windows dùng mã trang như `windows-1252` | Ứng dụng bỏ qua đối số charset có thể chạy khác nhau giữa các máy. |
| JDK 18 trở lên (JEP 400) | **UTF-8** là mặc định cho Java SE APIs có sử dụng default charset, ngoại trừ trường hợp cấu hình tương thích được hỗ trợ | Kết quả có tính nhất quán cao hơn giữa hệ điều hành; nhưng dữ liệu cũ ở charset khác có thể bị đọc sai. |

JEP 400 (**UTF-8 by Default**) có hiệu lực từ **JDK 18**. Sự thay đổi này liên quan đến **charset mặc định của JVM**, không có nghĩa là mọi file trên hệ thống tự đổi sang UTF-8, mọi thư viện đều mặc định UTF-8, hay mọi byte tùy ý đều là UTF-8 hợp lệ.

Trên JDK 18+, các lựa chọn được hỗ trợ khi khởi động JVM gồm:

- `-Dfile.encoding=UTF-8`: dùng UTF-8 làm default charset.
- `-Dfile.encoding=COMPAT`: chọn default charset theo cách tương thích với JDK 17 trở xuống, thường lấy encoding của môi trường hệ thống.

`COMPAT` được giới thiệu để hỗ trợ chuyển đổi sang JDK 18+, **không nên coi là tùy chọn tương đương trên JDK 17**. Những giá trị `file.encoding` khác `UTF-8` và `COMPAT` không được hỗ trợ theo đặc tả của JDK mới; tránh dựa vào hành vi riêng của một bản JDK.

JDK 17 đưa vào thuộc tính `native.encoding` để quan sát encoding của môi trường host. Trên JDK 18+, `Charset.defaultCharset()` có thể là UTF-8 dù `native.encoding` cho biết một charset khác. `file.encoding` là tùy chọn cấu hình lúc khởi động; **đừng gọi `System.setProperty("file.encoding", "...")` giữa chừng rồi kỳ vọng mọi bộ đọc/ghi và default charset đổi đồng bộ**.

## 3. API nào chịu ảnh hưởng, API nào không?

| Viết theo charset mặc định (phụ thuộc JDK/môi trường) | Phiên bản tường minh, ổn định |
| --- | --- |
| `text.getBytes()` | `text.getBytes(StandardCharsets.UTF_8)` |
| `new String(bytes)` | `new String(bytes, StandardCharsets.UTF_8)` |
| `new InputStreamReader(inputStream)` | `new InputStreamReader(inputStream, StandardCharsets.UTF_8)` |
| `new OutputStreamWriter(outputStream)` | `new OutputStreamWriter(outputStream, StandardCharsets.UTF_8)` |
| `new FileReader(file)` | `new FileReader(file, StandardCharsets.UTF_8)` |
| `new FileWriter(file)` | `new FileWriter(file, StandardCharsets.UTF_8)` |

`StandardCharsets.UTF_8` là hằng số trong `java.nio.charset` và luôn biểu diễn UTF-8. Khi tài liệu hoặc giao thức yêu cầu charset khác (ví dụ file lịch sử dùng `windows-1252`), hãy chỉ định **đúng charset đó** ở cả hai phía thay vì cố ép mọi dữ liệu thành UTF-8.

Một số phương thức `java.nio.file.Files` đã chọn UTF-8 **ngay cả trước JDK 18** khi không truyền charset, chẳng hạn:

- `Files.readString(path)`, `Files.writeString(path, text)`;
- `Files.newBufferedReader(path)`, `Files.newBufferedWriter(path)`;
- `Files.readAllLines(path)`.

Do đó, đừng suy luận rằng mọi overload thiếu đối số charset đều dùng `Charset.defaultCharset()`. Cần đọc hợp đồng của **chính overload đang gọi**. Với dữ liệu nhị phân, `Files.readAllBytes(path)` chỉ trả về byte, không giải mã và không sử dụng charset.

**Ngoại lệ quan trọng:** `System.out` và `System.err` có thể dùng encoding gắn với console/standard streams, khác với `Charset.defaultCharset()`. Trên JDK mới, `Console.charset()` và các thuộc tính liên quan đến stdout/stderr hỗ trợ quan sát cấu hình này. Việc chữ hiển thị sai trong terminal chưa đủ để kết luận byte trong file sai; hãy kiểm tra riêng encoding của file, luồng và terminal.

## 4. Ví dụ Java 17+: byte cố định, charset mặc định thay đổi theo JVM

Tạo file **`DefaultCharsetDemo.java`** (lưu mã nguồn bằng UTF-8):

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

public class DefaultCharsetDemo {
    public static void main(String[] args) {
        String text = "Aé";

        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
        String decodedCorrectly = new String(utf8, StandardCharsets.UTF_8);
        String decodedIncorrectly = new String(utf8, StandardCharsets.ISO_8859_1);

        System.out.println("String.length(): " + text.length());
        System.out.println("UTF-8 byte count: " + utf8.length);
        System.out.println("UTF-8 hex: " + HexFormat.of().withUpperCase().formatHex(utf8));
        System.out.println("UTF-8 round trip correct: " + text.equals(decodedCorrectly));
        System.out.println("ISO-8859-1 decode same text: " + text.equals(decodedIncorrectly));

        Charset actualDefault = Charset.defaultCharset();
        byte[] implicit = text.getBytes();
        System.out.println("Default charset: " + actualDefault.name());
        System.out.println("Default bytes match UTF-8: " + Arrays.equals(implicit, utf8));
        System.out.println("file.encoding: " + System.getProperty("file.encoding"));
        System.out.println("native.encoding: " + System.getProperty("native.encoding"));
    }
}
```

Biên dịch/chạy từ terminal tại thư mục chứa file:

```bash
javac -encoding UTF-8 DefaultCharsetDemo.java
java DefaultCharsetDemo
```

**Năm dòng đầu có kết quả xác định** trên Java 17+:

```text
String.length(): 2
UTF-8 byte count: 3
UTF-8 hex: 41C3A9
UTF-8 round trip correct: true
ISO-8859-1 decode same text: false
```

Các dòng phía sau **phụ thuộc phiên bản JDK, môi trường và tham số khởi động**. Chẳng hạn với JDK 18+ ở chế độ mặc định, `Default charset: UTF-8` và `Default bytes match UTF-8: true`; `native.encoding` có thể giống hoặc khác UTF-8 tùy máy. Không có một stdout chính xác chung cho `file.encoding` và `native.encoding` trên mọi hệ điều hành.

Với JDK 18+ có thể chạy thêm:

```bash
java -Dfile.encoding=UTF-8 DefaultCharsetDemo
java -Dfile.encoding=COMPAT DefaultCharsetDemo
```

Ở máy có native encoding khác UTF-8, lần chạy `COMPAT` giúp quan sát khác biệt. Nếu native encoding vốn đã là UTF-8 thì hai lần chạy có thể cho cùng kết quả `Default bytes match UTF-8: true`. Với JDK 17, có thể thử `java -Dfile.encoding=UTF-8 DefaultCharsetDemo` để kiểm tra ứng dụng trước khi nâng cấp, nhưng chỉ dùng `COMPAT` trên JDK 18+.

**Giải thích:** `"Aé"` có hai UTF-16 code unit nhưng thành ba byte UTF-8 (`41 C3 A9`). Giải mã cùng byte UTF-8 bằng ISO-8859-1 tạo ra chuỗi khác; ghi và đọc phải thống nhất charset. `text.getBytes()` ở cuối ví dụ cố ý dùng overload mặc định để thấy điểm rủi ro; trong mã ứng dụng nên ưu tiên overload truyền charset.

## 5. Ghi/đọc file với charset được chỉ định

Đoạn sau là **mã minh họa đặt bên trong một phương thức có `throws IOException`**, với các import `java.nio.file.Files`, `java.nio.file.Path` và `java.nio.charset.StandardCharsets`:

```java
Path path = Path.of("message.txt");
String message = "Xin chào Việt Nam";

Files.writeString(path, message, StandardCharsets.UTF_8);
String restored = Files.readString(path, StandardCharsets.UTF_8);
System.out.println(message.equals(restored)); // true
```

`Files.writeString` ghi ký tự thành byte UTF-8, còn `Files.readString` đọc chúng bằng UTF-8, không phụ thuộc vào default charset của JVM. Nếu thiếu đối số charset ở **hai phương thức cụ thể này**, mặc định của chúng vẫn là UTF-8. Khi file đến từ hệ thống ngoài, trước tiên phải biết charset thật của nguồn: chọn UTF-8 cho dữ liệu UTF-8; dùng charset khác nếu đặc tả nguồn quy định khác. Không tự động chuyển một file cũ sang UTF-8 chỉ bằng cách thay đổi tham số JVM.

Một luồng byte cũng có thể được khai báo encoding rõ ràng:

```java
// Hai dòng minh họa độc lập về ý tưởng, cần có in/out phù hợp.
var reader = new java.io.InputStreamReader(in, StandardCharsets.UTF_8);
var writer = new java.io.OutputStreamWriter(out, StandardCharsets.UTF_8);
```

Trong ứng dụng thực, `in` và `out` là các `InputStream`/`OutputStream` đang được quản lý vòng đời (thường dùng `try-with-resources`); charset phải tương ứng với giao thức và dữ liệu nguồn.

## 6. Khi nâng cấp JDK hoặc chuyển môi trường, lỗi nào dễ xuất hiện?

**Tình huống 1 — file cũ dùng charset của Windows.** Một ứng dụng chạy trên JDK 17 ghi file bằng `new FileWriter(file)` khi default charset là `windows-1252`. Sang JDK 21, `new FileReader(file)` thường giải mã với UTF-8. Nếu file chứa byte không phải UTF-8 hợp lệ, tùy API có thể gặp ký tự thay thế hoặc lỗi đọc; nếu dãy byte hợp lệ nhưng mang nghĩa khác, có thể thấy chữ sai. Cách xử lý đúng là xác định encoding gốc của file, đọc bằng charset đó rồi, nếu cần, **chuyển mã có kiểm tra** sang UTF-8.

**Tình huống 2 — trao đổi byte giữa dịch vụ.** Dịch vụ A dùng `getBytes()` để gửi bản tin, dịch vụ B dùng `new String(bytes)` để nhận. Nếu default charset khác nhau, bản tin có thể sai hoặc mất dữ liệu. Hãy định nghĩa charset trong hợp đồng giao tiếp (thường UTF-8) và dùng rõ ràng ở cả bên gửi lẫn nhận.

**Tình huống 3 — test chạy ổn trên máy lập trình nhưng lỗi tại CI/container.** Image hệ điều hành, locale hoặc bản JDK khác làm thay đổi default charset (đặc biệt với JDK 17 trở xuống). Test chỉ có ASCII có thể vẫn xanh vì nhiều charset mã hóa ASCII giống nhau. Bổ sung dữ liệu có dấu tiếng Việt, ký tự ngoài ASCII và kiểm tra **byte đầu ra** cùng kết quả giải mã.

**Tình huống 4 — nguồn Java và terminal.** File `.java` được lưu theo mã cũ có thể bị `javac` giải mã không đúng nếu encoding biên dịch đổi. Dùng `javac -encoding UTF-8` khi source ở UTF-8; kiểm tra encoding của IDE/build tool. Terminal có thể hiển thị sai dù bytes được mã hóa đúng, nên không lấy vẻ ngoài của console làm phép thử duy nhất.

## 7. Chẩn đoán và chuyển đổi an toàn

Có thể xem cấu hình của JVM bằng:

```bash
java -XshowSettings:properties -version
```

Trong kết quả, chú ý `file.encoding` và (khi có) `native.encoding`. Trong ứng dụng, in `Charset.defaultCharset().name()` như ví dụ trên để biết charset mặc định **thực tế**. Với JDK 18+, so sánh lần chạy mặc định với `-Dfile.encoding=COMPAT` để phát hiện chỗ phụ thuộc vào mã trang cũ. Với JDK 17, thử `-Dfile.encoding=UTF-8` để chuẩn bị nâng cấp.

Quy trình xử lý một lỗi mojibake:

1. Xác định byte **gốc** ở nguồn (đọc hex hoặc log byte); giữ lại bản gốc trước khi sửa.
2. Xác định charset do format, giao thức, header hoặc hệ thống tạo file quy định. Nếu không có hợp đồng, cần điều tra thay vì tin rằng mặc định của JVM có thể “đoán” đúng.
3. Giải mã bằng charset gốc **một lần**, kiểm tra các ký tự đặc trưng và trường hợp dữ liệu không hợp lệ.
4. Khi cần chuẩn hóa, mã hóa lại sang UTF-8, cập nhật metadata/giao thức và test luồng đọc–ghi xuyên môi trường.
5. Thay các điểm dùng `getBytes()`, `new String(bytes)`, `InputStreamReader`, `OutputStreamWriter`, `FileReader`, `FileWriter` không khai báo charset bằng phiên bản phù hợp với hợp đồng dữ liệu; rà cả thư viện ngoài và tùy chọn build.

**Không** “sửa” chữ lỗi bằng cách liên tục đổi giữa các charset hoặc thay `file.encoding` toàn hệ thống mà không hiểu byte nguồn. Đổi cấu hình có thể che lỗi ở một luồng nhưng làm hỏng luồng khác. Nếu dữ liệu đã bị thay thế mất thông tin trong bước giải mã trước đó, chỉ thay charset ở bước sau không khôi phục được byte gốc.

## 8. Checklist khi viết Java bền vững

- Có hợp đồng encoding rõ ràng cho file, HTTP body, CSV, log hoặc dữ liệu trao đổi; ưu tiên UTF-8 khi tự thiết kế format mới.
- Dùng `StandardCharsets.UTF_8` hoặc charset do định dạng quy định khi chuyển `String` ⇄ `byte[]` và khi khởi tạo reader/writer.
- Không đồng nhất default charset với `native.encoding`, encoding của nguồn `.java`, charset console, locale hoặc encoding thật của một file cũ.
- Test ký tự ngoài ASCII trên JDK/môi trường triển khai; xác thực cả bytes lẫn chuỗi đã giải mã.
- Coi `-Dfile.encoding=COMPAT` là công cụ kiểm thử/chuyển tiếp trên JDK 18+, còn việc truyền charset tường minh là hướng giải quyết lâu dài.

## Tài liệu chính thức

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400).
- [Oracle JDK 18 Release Notes — JEP 400](https://www.oracle.com/java/technologies/javase/18-relnote-issues.html).
- [Oracle Java SE 21 Internationalization Guide — Supported Encodings](https://docs.oracle.com/en/java/javase/21/intl/supported-encodings.html).
- [Java 17 API — `FileReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileReader.html).
