# Đọc `file.encoding` và `native.encoding` để phân biệt lựa chọn của JVM với mã hóa môi trường

## 1. Hai thuộc tính nói về hai điều khác nhau

Từ Java 18, **UTF-8 là charset mặc định** cho các Java SE API phụ thuộc default charset theo **JEP 400**. Khi chạy JVM theo cấu hình thông thường, `Charset.defaultCharset()` trả về UTF-8 trên các hệ điều hành.

Khi kiểm tra một ứng dụng, bạn thường thấy hai system property:

- `file.encoding`: cho biết lựa chọn default charset mà JDK đang sử dụng cho các API phụ thuộc charset mặc định.
- `native.encoding`: cho biết tên encoding của môi trường máy chủ gốc, hữu ích khi cần biết charset mà môi trường trước JDK 18 có thể đã dùng.

Hai giá trị này **có thể giống nhau hoặc khác nhau**. Ví dụ, một máy Windows có thể có native encoding là `windows-1258`, nhưng JVM JDK 18+ vẫn chọn UTF-8 làm default charset. Trong trường hợp đó, `file.encoding` phản ánh UTF-8 còn `native.encoding` phản ánh encoding của môi trường gốc.

Bài học thuộc chương **UTF-8 mặc định** của `JAVA_VERSION_JAVA18`. Mục tiêu là đọc đúng hai thuộc tính, hiểu mối liên hệ với `Charset.defaultCharset()`, nhận diện chế độ tương thích và kiểm tra ảnh hưởng khi nâng cấp ứng dụng lên JDK hiện đại.

## 2. Vai trò của từng thuộc tính

### 2.1. `file.encoding` — lựa chọn default charset của JDK

`file.encoding` là system property liên quan đến **default charset** của JDK. Trong cấu hình thông thường từ JDK 18 trở lên, giá trị runtime của nó là `UTF-8`.

Các API sử dụng default charset, chẳng hạn `String.getBytes()`, `new String(byte[])` hoặc một số constructor của `FileReader` và `InputStreamReader`, dựa trên lựa chọn này. Có thể kiểm tra default charset qua API chuẩn:

```java
import java.nio.charset.Charset;

System.out.println(Charset.defaultCharset().name());
System.out.println(System.getProperty("file.encoding"));
```

`Charset.defaultCharset()` là API để lấy charset mặc định mà ứng dụng Java nên dựa vào khi thật sự muốn sử dụng default charset. `file.encoding` hữu ích để chẩn đoán cấu hình khởi động và hiểu hành vi JDK.

### 2.2. `native.encoding` — encoding của môi trường máy chủ

`native.encoding` được giới thiệu từ JDK 17 để cung cấp thông tin về encoding của môi trường gốc. Nó đặc biệt hữu ích khi ứng dụng cần điều tra hành vi default charset trước Java 18 hoặc chạy ở chế độ tương thích.

Ví dụ, trong một môi trường:

```text
file.encoding   = UTF-8
native.encoding = windows-1258
```

Điều này có nghĩa JVM đã chọn UTF-8 làm default charset, trong khi encoding gốc mà JDK phát hiện từ môi trường là `windows-1258`. Các API phụ thuộc default charset sẽ theo lựa chọn UTF-8; không nên tự suy luận rằng mọi file, terminal hoặc chương trình bên ngoài cũng đang dùng UTF-8.

`native.encoding` là thông tin để đọc, **không phải cấu hình để ứng dụng đặt lại encoding của hệ điều hành**. Việc truyền `-Dnative.encoding=...` khi khởi chạy hoặc gọi `System.setProperty("native.encoding", "...")` không có tác dụng thay đổi encoding gốc được JDK phát hiện.

### 2.3. Bảng so sánh

| Thuộc tính/API | Ý nghĩa | Dùng để làm gì |
| --- | --- | --- |
| `Charset.defaultCharset()` | Charset mặc định thực tế của JVM | API chuẩn để kiểm tra default charset |
| `file.encoding` | Lựa chọn default charset của JDK ở thời điểm khởi động | Chẩn đoán chế độ UTF-8 hoặc tương thích |
| `native.encoding` | Encoding của môi trường máy chủ gốc mà JDK phát hiện | Điều tra môi trường cũ và chế độ COMPAT |
| `stdin.encoding` | Charset dùng cho đầu vào chuẩn | Giải mã byte nhận từ terminal/standard input |
| `stdout.encoding` | Charset dùng cho đầu ra chuẩn | Mã hóa văn bản gửi ra standard output |
| `stderr.encoding` | Charset dùng cho luồng lỗi chuẩn | Mã hóa văn bản gửi ra standard error |

**Không đồng nhất `native.encoding` với charset của mọi nguồn dữ liệu.** Một file có thể được tạo bởi ứng dụng dùng encoding khác; socket và HTTP có giao thức riêng; console có thể dùng charset riêng.

## 3. Mối quan hệ giữa `file.encoding` và `native.encoding` từ JDK 18

JEP 400 quy định UTF-8 là default charset từ JDK 18, đồng thời cung cấp chế độ `COMPAT` để kiểm tra hoặc duy trì hành vi tương thích với các bản JDK trước đó.

Hai giá trị `file.encoding` được hỗ trợ khi khởi động trên JDK 18+ là:

- `UTF-8`: chọn UTF-8 làm default charset.
- `COMPAT`: chọn default charset theo cách JDK 17 và các bản trước đó đã xác định từ môi trường.

Các giá trị khác **không được hỗ trợ theo đặc tả**; không dùng một tên charset tùy ý để cấu hình default charset của JVM.

### 3.1. Ma trận giá trị

| Cấu hình khởi động | `Charset.defaultCharset()` | `file.encoding` sau khởi động | `native.encoding` |
| --- | --- | --- | --- |
| Không đặt `file.encoding` trên JDK 18+ | UTF-8 | Thông thường là `UTF-8` | Encoding môi trường gốc |
| `-Dfile.encoding=UTF-8` | UTF-8 | `UTF-8` | Vẫn là encoding môi trường gốc |
| `-Dfile.encoding=COMPAT` | Charset được xác định theo môi trường như JDK 17 trở về trước | Bằng giá trị runtime của `native.encoding` | Encoding môi trường gốc |
| `-Dfile.encoding=windows-1258` trên JDK 18+ | Không được đặc tả | Hành vi không được hỗ trợ | Không thay đổi |

Ở dòng `UTF-8`, `file.encoding` và `native.encoding` có thể khác nhau. Ở dòng `COMPAT`, giá trị runtime của `file.encoding` sẽ bằng giá trị runtime của `native.encoding`.

Bảng này mô tả JDK 18 trở lên. Không áp dụng `-Dfile.encoding=COMPAT` cho JDK 17 trở về trước như một chế độ tương thích đã được hỗ trợ: giá trị `COMPAT` là cơ chế của JEP 400 từ JDK 18.

### 3.2. Ví dụ khi native encoding không phải UTF-8

Giả sử máy có native encoding `windows-1258`:

- Chạy JDK 18+ bình thường: `Charset.defaultCharset()` là UTF-8.
- Chạy `-Dfile.encoding=UTF-8`: default charset vẫn là UTF-8; `native.encoding` vẫn cho biết `windows-1258`.
- Chạy `-Dfile.encoding=COMPAT`: default charset quay về cách xác định theo môi trường cũ; giá trị runtime của `file.encoding` sẽ tương ứng với `native.encoding`.

Vì vậy, hai thuộc tính cho phép phân biệt **lựa chọn của JVM** và **đặc điểm encoding mà JDK phát hiện từ máy chủ**.

## 4. Đọc các giá trị trong chương trình Java

Ví dụ sau đọc cả hai system property, đồng thời hiển thị kết quả của API chuẩn:

```java
import java.nio.charset.Charset;

public class CharsetEnvironmentInfo {
    public static void main(String[] args) {
        String fileEncoding = System.getProperty("file.encoding");
        String nativeEncoding = System.getProperty("native.encoding");

        System.out.println("Charset.defaultCharset() = "
                + Charset.defaultCharset().name());
        System.out.println("file.encoding = " + fileEncoding);
        System.out.println("native.encoding = " + nativeEncoding);
    }
}
```

Ví dụ kết quả minh họa trên một máy có native encoding không phải UTF-8:

```text
Charset.defaultCharset() = UTF-8
file.encoding = UTF-8
native.encoding = windows-1258
```

Kết quả thực tế phụ thuộc môi trường. Không ghi cứng `windows-1258` trong logic ứng dụng; ví dụ chỉ minh họa trường hợp hai thuộc tính khác nhau.

### 4.1. `native.encoding` có thể không tồn tại trên runtime cũ

`native.encoding` được giới thiệu từ JDK 17. Khi chương trình cần chạy trên nhiều đời JDK hoặc JDK vendor khác nhau, hãy kiểm tra giá trị `null` trước khi sử dụng:

```java
import java.nio.charset.Charset;

String nativeEncoding = System.getProperty("native.encoding");

Charset hostEncoding = nativeEncoding != null
        ? Charset.forName(nativeEncoding)
        : Charset.defaultCharset();

System.out.println("Host encoding candidate = "
        + hostEncoding.name());
```

Cách fallback này phù hợp để hiển thị hoặc điều tra. Nó **không biến `hostEncoding` thành charset chuẩn cho mọi file hoặc giao thức**. Nếu đọc file, hãy dùng charset được định nghĩa trong hợp đồng của file đó.

### 4.2. Không dùng `Charset.forName("default")`

Không có charset chuẩn tên `default` để lấy default charset. Trên các JDK hiện đại, lời gọi:

```java
Charset.forName("default");
```

sẽ ném `UnsupportedCharsetException`. Dùng `Charset.defaultCharset()` để lấy default charset, hoặc `Charset.forName(nativeEncoding)` khi cần chuyển tên encoding hợp lệ từ `native.encoding` thành đối tượng `Charset`.

## 5. Kiểm tra cấu hình JVM từ dòng lệnh

### 5.1. Hiển thị các system property

JDK cung cấp tùy chọn `-XshowSettings:properties` để in các system property khi khởi động:

```bash
java -XshowSettings:properties -version
```

Trên Linux/macOS, có thể lọc hai thuộc tính cần xem:

```bash
java -XshowSettings:properties -version 2>&1 | grep -E 'file.encoding|native.encoding'
```

Trên Windows PowerShell:

```powershell
java -XshowSettings:properties -version 2>&1 |
    Select-String 'file.encoding|native.encoding'
```

Tùy JDK vendor và phiên bản, thứ tự và cách căn lề của output có thể khác. Mục đích là đọc giá trị runtime, không phụ thuộc vào định dạng hiển thị.

### 5.2. Chạy chương trình với hai chế độ để so sánh

Biên dịch ví dụ bằng UTF-8:

```bash
javac -encoding UTF-8 CharsetEnvironmentInfo.java
```

Chạy cấu hình UTF-8:

```bash
java -Dfile.encoding=UTF-8 CharsetEnvironmentInfo
```

Chạy chế độ tương thích trên JDK 18+:

```bash
java -Dfile.encoding=COMPAT CharsetEnvironmentInfo
```

So sánh ba giá trị:

1. `Charset.defaultCharset()` có thay đổi hay không?
2. `file.encoding` runtime có bằng `native.encoding` khi chạy COMPAT hay không?
3. `native.encoding` có giữ nguyên giữa hai lần chạy hay không?

Nếu native encoding khác UTF-8, lần chạy COMPAT thường cho thấy default charset quay lại encoding môi trường cũ. Nếu native encoding vốn là UTF-8, hai lần chạy có thể cho kết quả giống nhau; điều đó không chứng minh ứng dụng không có phụ thuộc encoding.

**Lưu ý:** `-Dfile.encoding=COMPAT` phải đứng trước tên lớp chính hoặc `-jar` trong lệnh `java` vì đây là tùy chọn khởi động JVM.

## 6. Vì sao không nên thay đổi system property sau khi JVM chạy?

Không nên cố thay đổi default charset bằng đoạn code:

```java
System.setProperty("file.encoding", "windows-1258");
```

Việc thay đổi giá trị property trong `System.getProperty()` không phải cơ chế được hỗ trợ để cấu hình lại default charset. JDK xác định charset mặc định trong quá trình khởi động; các API phụ thuộc default charset không được thiết kế để ứng dụng đổi charset tùy ý giữa vòng đời JVM.

Tương tự, `native.encoding` phản ánh encoding môi trường gốc do JDK phát hiện. Gán giá trị cho property này không thay đổi locale, code page, terminal hoặc cấu hình của hệ điều hành.

Nếu ứng dụng cần đọc dữ liệu bằng một charset cụ thể, hãy truyền charset trực tiếp vào API:

```java
import java.io.FileReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

try (var reader = new FileReader(
        Path.of("legacy.txt").toFile(),
        StandardCharsets.UTF_8)) {
    // File này được đọc rõ ràng bằng UTF-8.
}
```

Nếu file legacy thực sự là Windows-1258, hãy thay UTF-8 bằng charset nguồn đã được xác nhận. Cách này kiểm soát từng ranh giới dữ liệu mà không thay đổi cấu hình toàn JVM.

## 7. `native.encoding` không phải charset của console

Một điểm quan trọng khi điều tra tiếng Việt bị lỗi là không lấy `native.encoding` làm kết luận về encoding của `System.in`, `System.out` và `System.err`.

Các luồng chuẩn có thể dùng charset riêng:

| Luồng | Thuộc tính |
| --- | --- |
| `System.in` | `stdin.encoding` |
| `System.out` | `stdout.encoding` |
| `System.err` | `stderr.encoding` |

Từ Java 18, `PrintStream.charset()` cho phép kiểm tra charset mà một `PrintStream` đang sử dụng:

```java
import java.nio.charset.Charset;

System.out.println("default = "
        + Charset.defaultCharset().name());
System.out.println("stdout = "
        + System.out.charset().name());
System.err.println("stderr = "
        + System.err.charset().name());
```

`System.out` có thể dùng charset khác `Charset.defaultCharset()`. Vì thế, nếu chữ tiếng Việt hiển thị sai trong terminal, cần kiểm tra charset của luồng chuẩn và terminal, không chỉ xem `file.encoding` hoặc `native.encoding`.

Tương tự, `System.in` là luồng byte. Khi tạo `InputStreamReader` hoặc `Scanner` để đọc dữ liệu terminal, cần dùng charset của nguồn nhập. Charset của file, socket hoặc HTTP vẫn phải theo hợp đồng riêng.

## 8. `javac` và encoding của mã nguồn

`file.encoding` và `native.encoding` còn hữu ích khi điều tra lỗi biên dịch mã nguồn có ký tự ngoài ASCII. Theo tài liệu Oracle, `javac` mặc định đọc file `.java` theo default charset nếu không truyền tùy chọn `-encoding`.

Nếu mã nguồn được lưu bằng UTF-8, hãy khai báo rõ:

```bash
javac -encoding UTF-8 MyApplication.java
```

Nếu mã nguồn legacy được lưu bằng một encoding khác, cần chỉ định đúng encoding của file nguồn trong cấu hình build. Không nên dùng encoding máy chủ làm quy ước ngầm cho toàn bộ repository.

Phân biệt ba giai đoạn:

- **Source encoding:** cách `javac` giải mã file `.java` thành ký tự khi biên dịch.
- **Runtime default charset:** cách các API phụ thuộc default charset chuyển đổi byte và văn bản khi ứng dụng chạy.
- **External protocol/file encoding:** cách hệ thống bên ngoài quy định byte dữ liệu được gửi hoặc lưu.

Ba giai đoạn này có thể dùng cùng UTF-8, nhưng phải được cấu hình hoặc xác định theo hợp đồng tương ứng.

## 9. Tình huống thực tế khi nâng cấp lên JDK 18+

Giả sử một ứng dụng Java 17 chạy trên máy có native encoding `windows-1258`. Code có một đoạn:

```java
String text = new String(Files.readAllBytes(Path.of("legacy.txt")));
```

File `legacy.txt` được ghi bằng Windows-1258. Trên JDK 17, default charset của JVM có thể khớp với encoding môi trường nên ứng dụng đọc đúng. Khi nâng lên JDK 18, default charset chuyển sang UTF-8; byte Windows-1258 có thể bị giải mã sai.

Trong trường hợp này:

1. `native.encoding` giúp nhận diện encoding môi trường trước đây mà JDK phát hiện.
2. `file.encoding` và `Charset.defaultCharset()` cho biết default charset hiện tại của JVM.
3. Chạy `-Dfile.encoding=COMPAT` giúp tái hiện hành vi tương thích để xác nhận giả thuyết.
4. Sau khi xác định file thực sự là Windows-1258, thay lời gọi bằng API chỉ định charset nguồn.

Ví dụ sửa theo hợp đồng file:

```java
import java.nio.charset.Charset;
import java.nio.file.Files;
import java.nio.file.Path;

Path legacyFile = Path.of("legacy.txt");
Charset sourceCharset = Charset.forName("windows-1258");

String text = Files.readString(legacyFile, sourceCharset);
```

Không nên thay mọi file trong ứng dụng bằng `native.encoding`. Chỉ file nào có hợp đồng thực sự quy định encoding đó mới nên dùng. Nếu một file khác là UTF-8, nó phải tiếp tục được đọc bằng UTF-8 ngay cả khi native encoding của máy là Windows-1258.

### 9.1. Ví dụ kiểm tra khác biệt bằng hai API

Đoạn code sau ghi file bằng UTF-8 rồi đọc lại bằng `FileReader` không chỉ định charset và `Files.readString`:

```java
import java.io.FileReader;
import java.io.StringWriter;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("sample.txt");
String original = "Tiếng Việt: cà phê";

Files.writeString(file, original, StandardCharsets.UTF_8);

String byFiles = Files.readString(file, StandardCharsets.UTF_8);

String byDefault;
try (var reader = new FileReader(file.toFile())) {
    var buffer = new StringWriter();
    reader.transferTo(buffer);
    byDefault = buffer.toString();
}

System.out.println("default = " + Charset.defaultCharset().name());
System.out.println("Files matches = " + original.equals(byFiles));
System.out.println("FileReader matches = " + original.equals(byDefault));
```

Khi default charset là UTF-8, cả hai phép đọc đều có thể cho kết quả đúng. Khi chạy `-Dfile.encoding=COMPAT` trên môi trường native encoding khác UTF-8, `Files.readString` vẫn đọc UTF-8 theo hợp đồng API, trong khi `FileReader` có thể đọc sai vì dùng default charset.

Ví dụ này cho thấy `native.encoding` là manh mối điều tra, còn charset được truyền tường minh mới là cách xác định hợp đồng của file.

## 10. Checklist khi chẩn đoán lỗi encoding

Khi ứng dụng hiển thị sai tiếng Việt sau khi nâng cấp JDK, hãy kiểm tra theo thứ tự:

1. Gọi `Charset.defaultCharset()` để biết default charset thực tế của JVM.
2. Đọc `file.encoding` để hiểu cấu hình default charset khi khởi động.
3. Đọc `native.encoding` để biết encoding môi trường gốc mà JDK phát hiện.
4. Nếu cần, chạy lại trên JDK 18+ với `-Dfile.encoding=COMPAT` để so sánh hành vi trước đây.
5. Xác nhận charset thực sự của file, socket, HTTP body hoặc nguồn dữ liệu.
6. Tìm các API bỏ qua tham số charset như `new String(bytes)`, `getBytes()`, `FileReader(file)` và `InputStreamReader(stream)`.
7. Kiểm tra riêng `stdin.encoding`, `stdout.encoding`, `stderr.encoding` nếu lỗi chỉ xảy ra trong console.
8. Sửa tại ranh giới I/O bằng charset được quy định; không đổi system property sau khi JVM đã khởi động.
9. Thêm test có tiếng Việt, ký tự ngoài BMP và byte mẫu để xác nhận nội dung.

### Những suy luận sai cần tránh

| Suy luận | Vì sao sai |
| --- | --- |
| `native.encoding` khác UTF-8 thì ứng dụng đang dùng native encoding | JDK 18+ mặc định UTF-8; native chỉ mô tả môi trường gốc |
| `file.encoding` bằng UTF-8 thì mọi file đều là UTF-8 | File có thể được tạo theo encoding khác |
| Đổi `System.setProperty("file.encoding", ...)` sẽ đổi default charset | Đây không phải cơ chế cấu hình được hỗ trợ sau khởi động |
| `native.encoding` có thể đặt bằng `-Dnative.encoding` | Giá trị này do JDK phát hiện; đặt property không đổi encoding môi trường |
| `native.encoding` là charset của terminal | Standard streams có encoding riêng |
| Chạy COMPAT cho kết quả đúng nghĩa là ứng dụng đã portable | Nó chỉ cho thấy hành vi tương thích trong môi trường thử nghiệm |

## 11. Bài tập tự kiểm tra

**Bài 1.** Trên JDK 18+, chương trình in `file.encoding=UTF-8` và `native.encoding=windows-1258`. Điều đó có mâu thuẫn không?

*Đáp án:* Không. JVM chọn UTF-8 làm default charset theo JEP 400; native encoding phản ánh encoding của môi trường gốc.

**Bài 2.** Nếu chạy `-Dfile.encoding=COMPAT` trên JDK 18+, giá trị runtime của `file.encoding` sẽ như thế nào?

*Đáp án:* Giá trị runtime của `file.encoding` bằng giá trị runtime của `native.encoding`; default charset được xác định theo cách JDK 17 và trước đó đã dùng.

**Bài 3.** Có thể gọi `System.setProperty("native.encoding", "UTF-8")` để ép JVM xem môi trường là UTF-8 không?

*Đáp án:* Không. `native.encoding` là thuộc tính thông tin do JDK phát hiện. Gán giá trị bằng dòng lệnh hoặc API `System.setProperty` không thay đổi encoding gốc.

**Bài 4.** `Charset.defaultCharset()` và `System.out.charset()` có nhất thiết giống nhau không?

*Đáp án:* Không. Luồng chuẩn có thể dùng charset riêng được xác định bởi môi trường console và các property `stdout.encoding`, `stderr.encoding`.

**Bài 5.** Một file Windows-1258 được ứng dụng Java 17 đọc đúng nhưng sau nâng cấp Java 18 bị lỗi. `native.encoding` giúp gì?

*Đáp án:* Nó cung cấp manh mối về encoding môi trường mà JDK trước đây có thể dùng làm default. Cần xác nhận hợp đồng file; sau đó đọc bằng charset Windows-1258 tường minh thay vì phụ thuộc default charset.

## 12. Ghi nhớ

`file.encoding` phản ánh lựa chọn default charset của JDK; `native.encoding` phản ánh encoding của môi trường máy chủ mà JDK phát hiện. Từ JDK 18, UTF-8 là mặc định thông thường. Hai giá trị có thể khác nhau khi JVM chọn UTF-8 nhưng máy chủ có encoding gốc khác.

`-Dfile.encoding=UTF-8` và `-Dfile.encoding=COMPAT` là hai lựa chọn được hỗ trợ khi khởi động JDK 18+. `COMPAT` hữu ích để điều tra tương thích; `native.encoding` chỉ cung cấp thông tin và không thể được dùng để cấu hình lại môi trường.

Khi xây dựng ứng dụng Java hiện đại, hãy dùng `Charset.defaultCharset()` để kiểm tra default charset, dùng hai property để chẩn đoán môi trường, và chỉ định charset rõ ràng theo hợp đồng tại từng ranh giới nhập xuất. Đây là cách giữ dữ liệu tiếng Việt chính xác và giúp ứng dụng hoạt động nhất quán khi nâng cấp JDK.

### Tài liệu tham khảo chính thức

- [OpenJDK — JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400).
- [Oracle Java SE 27 — Supported Encodings: Default Charset, file.encoding và native.encoding](https://docs.oracle.com/en/java/javase/27/intl/supported-encodings.html).
- [Oracle Java SE 27 — Migration Guide: Be Aware of the Default Charset](https://docs.oracle.com/en/java/javase/27/migrate/migrating-from-jdk-8-later-jdk-releases.html).
- [Oracle Java SE 26 — System: Standard System Properties](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.html).
- [Oracle Java SE 27 — Charset.defaultCharset()](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/Charset.html).
