# Kiểm chứng đọc ghi khi file.encoding khác charset đã khai báo trong API

## 1. Mục tiêu: tách cấu hình JVM khỏi hợp đồng của dữ liệu

Trong module **JAVA_VERSION_JAVA18**, thay đổi của [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400) khiến UTF-8 trở thành charset mặc định của nhiều API Java từ JDK 18. Điều này giúp các chương trình mới có hành vi nhất quán hơn giữa các hệ điều hành. Tuy nhiên, một file hoặc giao thức vẫn có charset riêng do định dạng hay bên phát quy định.

Bài thuộc chương **Kiểm chứng mã hóa**. Mục tiêu là xác nhận điều gì xảy ra khi thuộc tính JVM `file.encoding` khác charset mà API được yêu cầu sử dụng:

- API **không nhận charset** thường dùng `Charset.defaultCharset()`. Trên JDK 18+, mặc định là UTF-8, trừ khi JVM được khởi chạy ở chế độ tương thích `-Dfile.encoding=COMPAT`.
- API **nhận charset tường minh** phải dùng đúng charset truyền vào, bất kể `file.encoding` đang là gì.
- Một số API có **quy tắc charset cố định trong hợp đồng**. Ví dụ `Files.readString(path)` và `Files.writeString(path, text)` dùng UTF-8, không lấy charset từ `file.encoding`.
- Một định dạng legacy như Windows-1252 vẫn phải được đọc bằng Windows-1252 nếu đó là hợp đồng của file. UTF-8 mặc định không tự chuyển đổi byte cũ.

Sau bài này, bạn có thể kiểm tra charset mặc định tại thời điểm JVM khởi chạy, phân biệt API mặc định với API có charset rõ ràng, và chứng minh rằng đổi `file.encoding` không thay đổi hành vi của một API đã được truyền charset tường minh.

## 2. `file.encoding` có ý nghĩa gì trên JDK 18+?

`file.encoding` là thuộc tính hệ thống liên quan đến charset mặc định mà các API Java dùng khi không có charset được chỉ định. Theo JEP 400:

- Giá trị mặc định trên JDK 18+ là `UTF-8`.
- Có thể khởi chạy JVM với `-Dfile.encoding=COMPAT` để yêu cầu hành vi charset mặc định tương thích với môi trường native của nền tảng. Khi đó `Charset.defaultCharset()` phản ánh charset native mà JVM chọn.
- `native.encoding` cung cấp thông tin về charset native của môi trường chạy; đây là thông tin môi trường, không phải khai báo charset cho từng file.
- Chỉ `UTF-8` và `COMPAT` là các giá trị được hỗ trợ cho mục đích này trên JDK 18+. Đặt một tên charset tùy ý như `-Dfile.encoding=windows-1252` là cách cấu hình không được hỗ trợ và có hành vi không xác định.

Ví dụ kiểm tra trong chương trình:

```java
import java.nio.charset.Charset;

System.out.println("file.encoding="
        + System.getProperty("file.encoding"));
System.out.println("native.encoding="
        + System.getProperty("native.encoding"));
System.out.println("defaultCharset="
        + Charset.defaultCharset().name());
```

Không dùng `System.setProperty("file.encoding", ...)` giữa lúc chương trình đang chạy để đổi charset mặc định. Charset mặc định được khởi tạo và lưu trong runtime; thay đổi một chuỗi system property sau đó không phải cơ chế được hỗ trợ để cấu hình lại các API đã dùng hoặc cache charset. Hãy chọn chế độ cần thiết **ngay khi khởi chạy JVM**.

### 2.1. `COMPAT` không đồng nghĩa với một charset cố định

`-Dfile.encoding=COMPAT` yêu cầu JDK dùng hành vi tương thích với charset native của môi trường. Kết quả cụ thể phụ thuộc hệ điều hành, locale và cấu hình chạy. Trên một hệ Linux hiện đại có locale UTF-8, charset native có thể vẫn là UTF-8; khi đó `COMPAT` và mặc định UTF-8 cho kết quả giống nhau.

Vì vậy, không thể dùng `COMPAT` để đảm bảo chương trình chạy bằng Windows-1252 hoặc ISO-8859-1 trên mọi máy. Nếu một file đã được đặc tả là Windows-1252, hãy truyền `Charset.forName("windows-1252")` trực tiếp cho API đọc/ghi file.

### 2.2. `file.encoding` không phải metadata của file

Một file văn bản thông thường chỉ chứa byte. Hệ thống tệp không tự lưu một charset bắt buộc cho nội dung file. Nếu file do hệ thống khác tạo, charset phải được biết từ hợp đồng, cấu hình, tài liệu, BOM hoặc metadata của định dạng.

Ví dụ: byte `E9` có thể là chữ `é` trong Windows-1252, nhưng không phải một chuỗi UTF-8 hợp lệ đứng độc lập. Đọc file đó bằng charset mặc định UTF-8 không thể biến nó thành văn bản đúng. Cần dùng charset của file:

```java
var legacy = java.nio.charset.Charset.forName("windows-1252");
String text = Files.readString(Path.of("legacy.txt"), legacy);
```

## 3. API dùng charset mặc định và API có charset tường minh

| API | Cách chọn charset | Có phụ thuộc `file.encoding`? |
| --- | --- | --- |
| `new String(bytes)` | `Charset.defaultCharset()` | Có |
| `text.getBytes()` | `Charset.defaultCharset()` | Có |
| `new InputStreamReader(input)` | Charset mặc định | Có |
| `new OutputStreamWriter(output)` | Charset mặc định | Có |
| `new FileReader(file)` / `new FileWriter(file)` | Charset mặc định trên JDK hiện đại | Có |
| `new String(bytes, charset)` | Charset truyền vào | Không |
| `text.getBytes(charset)` | Charset truyền vào | Không |
| `new InputStreamReader(input, charset)` | Charset truyền vào | Không |
| `new OutputStreamWriter(output, charset)` | Charset truyền vào | Không |
| `new FileReader(file, charset)` / `new FileWriter(file, charset)` | Charset truyền vào | Không |
| `Files.readString(path, charset)` / `Files.writeString(path, text, charset)` | Charset truyền vào | Không |
| `Files.readString(path)` / `Files.writeString(path, text)` | UTF-8 theo hợp đồng API | Không |

Với file text, các overload nhận `Charset` làm rõ định dạng dữ liệu tại nơi chuyển đổi. Điều này quan trọng khi một ứng dụng phải xử lý đồng thời file UTF-8 mới và file legacy có charset đã biết.

### 3.1. Những API không tham số charset

```java
byte[] bytes = Files.readAllBytes(Path.of("input.txt"));

// Phụ thuộc Charset.defaultCharset().
String implicitText = new String(bytes);

// Cũng phụ thuộc Charset.defaultCharset().
byte[] implicitBytes = implicitText.getBytes();
```

Trên JDK 18+ mặc định thông thường là UTF-8, nhưng nếu ứng dụng chạy với `-Dfile.encoding=COMPAT` trên máy có charset native khác UTF-8, kết quả có thể khác. Đây là lý do không nên dùng các overload này để định nghĩa định dạng file hay giao thức liên máy.

### 3.2. Những API nhận charset tường minh

```java
import java.nio.charset.StandardCharsets;

String explicitText = new String(bytes, StandardCharsets.UTF_8);
byte[] explicitBytes = explicitText.getBytes(StandardCharsets.UTF_8);
```

Charset truyền vào quyết định cách chuyển đổi. `file.encoding` không ghi đè `StandardCharsets.UTF_8`, cũng không biến byte Windows-1252 thành UTF-8.

### 3.3. API có UTF-8 cố định

```java
String text = Files.readString(Path.of("message.txt"));
Files.writeString(Path.of("message-out.txt"), text);
```

Hai overload không có tham số charset của `Files.readString` và `Files.writeString` dùng UTF-8 theo hợp đồng API. Chúng không lấy charset từ `Charset.defaultCharset()`. Nếu file nguồn không phải UTF-8, hãy dùng overload có charset:

```java
var cp1252 = java.nio.charset.Charset.forName("windows-1252");
String legacyText = Files.readString(Path.of("legacy.txt"), cp1252);
Files.writeString(Path.of("legacy-copy.txt"), legacyText, cp1252);
```

Đừng suy luận rằng mọi API trong `java.nio.file.Files` đều dùng cùng một quy tắc: kiểm tra overload cụ thể và tài liệu API.

## 4. Ví dụ kiểm chứng: file UTF-8 và file Windows-1252

Ví dụ sau dùng hai định dạng đã biết:

- `utf8-data.txt` có hợp đồng UTF-8.
- `legacy-windows-1252.txt` có hợp đồng Windows-1252 và chứa chuỗi `café €`. Trong Windows-1252, byte của chuỗi này là `63 61 66 E9 20 80`.

Chương trình ghi và đọc bằng charset tường minh, đồng thời so sánh với API dùng charset mặc định. Các kết quả chẩn đoán được in bằng nhãn ASCII và byte hex để không phụ thuộc cách terminal hiển thị tiếng Việt.

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.HexFormat;

public final class FileEncodingPropertyCheck {
    public static void main(String[] args) throws Exception {
        Charset defaultCharset = Charset.defaultCharset();
        Charset windows1252 = Charset.forName("windows-1252");

        String utf8Text = "Tiếng Việt 🚀";
        Path utf8File = Path.of("utf8-data.txt");

        // Ghi đúng theo hợp đồng UTF-8.
        Files.writeString(utf8File, utf8Text, StandardCharsets.UTF_8);
        byte[] utf8Bytes = Files.readAllBytes(utf8File);

        String utf8ExplicitRead =
                new String(utf8Bytes, StandardCharsets.UTF_8);
        String utf8DefaultRead = new String(utf8Bytes);

        byte[] explicitUtf8Output =
                utf8Text.getBytes(StandardCharsets.UTF_8);
        byte[] defaultOutput = utf8Text.getBytes();

        String legacyText = "café €";
        Path legacyFile = Path.of("legacy-windows-1252.txt");

        // File legacy phải dùng charset được định dạng quy định.
        byte[] legacyBytes = legacyText.getBytes(windows1252);
        Files.write(legacyFile, legacyBytes);

        String legacyExplicitRead =
                Files.readString(legacyFile, windows1252);
        String legacyDefaultRead = new String(legacyBytes);

        System.out.println("file.encoding="
                + System.getProperty("file.encoding"));
        System.out.println("native.encoding="
                + System.getProperty("native.encoding"));
        System.out.println("defaultCharset=" + defaultCharset.name());

        System.out.println("utf8FileHex=" + hex(utf8Bytes));
        System.out.println("utf8ExplicitReadMatches="
                + utf8Text.equals(utf8ExplicitRead));
        System.out.println("utf8DefaultReadMatches="
                + utf8Text.equals(utf8DefaultRead));
        System.out.println("explicitUtf8OutputHex=" + hex(explicitUtf8Output));
        System.out.println("defaultOutputHex=" + hex(defaultOutput));
        System.out.println("defaultIsUtf8="
                + defaultCharset.equals(StandardCharsets.UTF_8));

        System.out.println("legacyFileHex=" + hex(legacyBytes));
        System.out.println("legacyExplicitReadMatches="
                + legacyText.equals(legacyExplicitRead));
        System.out.println("legacyDefaultReadMatches="
                + legacyText.equals(legacyDefaultRead));

        // Files.readString(path) có hợp đồng UTF-8 cố định.
        try {
            String fixedUtf8Read = Files.readString(legacyFile);
            System.out.println("legacyReadWithFilesDefault="
                    + legacyText.equals(fixedUtf8Read));
        } catch (java.io.IOException malformedUtf8) {
            System.out.println("legacyReadWithFilesDefault=REJECTED_AS_UTF8");
        }

        // Vector byte của Windows-1252 phải được giữ chính xác.
        byte[] expectedLegacy = {
                0x63, 0x61, 0x66, (byte) 0xE9, 0x20, (byte) 0x80
        };
        if (!Arrays.equals(expectedLegacy, legacyBytes)) {
            throw new AssertionError("Vector Windows-1252 không khớp");
        }
    }

    private static String hex(byte[] bytes) {
        return HexFormat.ofDelimiter(" ").withUpperCase().formatHex(bytes);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 FileEncodingPropertyCheck.java
java FileEncodingPropertyCheck
```

Chương trình kiểm chứng ba điểm:

1. Đọc file UTF-8 bằng `new String(bytes, UTF_8)` luôn phải khớp chuỗi gốc; đọc bằng `new String(bytes)` chỉ khớp khi default charset cũng là UTF-8.
2. Đọc file Windows-1252 bằng `Files.readString(path, windows1252)` phải khớp chuỗi gốc; đọc bằng `new String(bytes)` phụ thuộc default charset và có thể thay ký tự nếu default là UTF-8.
3. `Files.readString(path)` dùng UTF-8 cố định. Khi file Windows-1252 có byte không hợp lệ theo UTF-8, API có thể từ chối bằng IOException thay vì tự đoán charset legacy.

Nếu môi trường native cũng dùng UTF-8, các kết quả dùng default có thể trùng với explicit UTF-8. Đây là kết quả bình thường, không làm mất ý nghĩa của phép thử: chương trình vẫn in charset thực tế và kiểm tra riêng định dạng Windows-1252.

## 5. Chạy cùng chương trình với hai chế độ file.encoding

Trên JDK 18+, so sánh mặc định UTF-8 với chế độ tương thích:

```bash
java FileEncodingPropertyCheck
java -Dfile.encoding=COMPAT FileEncodingPropertyCheck
```

Trên PowerShell, lệnh cũng có thể chạy trực tiếp:

```powershell
java FileEncodingPropertyCheck
java -Dfile.encoding=COMPAT FileEncodingPropertyCheck
```

Hãy so sánh các dòng `file.encoding`, `native.encoding` và `defaultCharset`. Trong lần chạy mặc định, `defaultCharset` là UTF-8. Khi dùng `COMPAT`, charset mặc định theo môi trường native; nếu môi trường native là UTF-8 thì hai lần chạy có thể cho cùng kết quả.

Không dùng `-Dfile.encoding=windows-1252` để ép JVM đổi default charset. Trên JDK 18+, giá trị charset tùy ý không phải cấu hình được hỗ trợ. Muốn xử lý file Windows-1252, khai báo charset đó trong API:

```java
Charset windows1252 = Charset.forName("windows-1252");
String text = Files.readString(path, windows1252);
```

Nếu ứng dụng cũ cần kiểm tra chế độ tương thích, chạy mỗi cấu hình trong **một JVM mới**. Đừng gọi `System.setProperty("file.encoding", "COMPAT")` sau khi JVM đã khởi động và mong đợi mọi API tự đổi charset.

## 6. Đọc kết quả: điều gì phải thay đổi và điều gì phải giữ nguyên?

| Quan sát | Diễn giải đúng |
| --- | --- |
| `Charset.defaultCharset()` đổi giữa hai lần chạy | JVM đang dùng chế độ default charset khác nhau; chỉ API phụ thuộc default mới chịu ảnh hưởng. |
| `new String(bytes)` đổi kết quả | Đây là API phụ thuộc default charset; cần kiểm tra hợp đồng byte nguồn. |
| `text.getBytes()` đổi byte | Đây là API phụ thuộc default charset; không phù hợp để tạo định dạng file/giao thức cố định. |
| `new String(bytes, UTF_8)` giữ nguyên kết quả | Charset tường minh quyết định việc giải mã, không bị `file.encoding` ghi đè. |
| `text.getBytes(UTF_8)` giữ nguyên byte | Charset tường minh quyết định việc mã hóa, không bị `file.encoding` ghi đè. |
| `Files.readString(path)` đọc UTF-8 bất kể default | Đây là hợp đồng cố định của API, không dùng default charset. |
| `Files.readString(path, windows1252)` đọc đúng file legacy | Charset của file được truyền tường minh. |

Một bài kiểm thử tốt phải xác nhận cả **giá trị String** và **byte đầu ra**. Chỉ in ký tự ra console có thể gây hiểu lầm nếu console có charset hoặc font khác. Dùng `HexFormat`, `Arrays.equals` và `String.equals` để kiểm tra.

## 7. Các ngoại lệ và điểm dễ nhầm

### 7.1. `file.encoding` không tự chuyển đổi file

Đổi default charset không viết lại file đang có, không gắn metadata charset vào file và không thay đổi byte trên đĩa. Nó chỉ ảnh hưởng những API lấy charset mặc định tại runtime. Byte file chỉ thay đổi khi ứng dụng thực sự ghi nội dung mới.

### 7.2. API nhận charset tường minh tuân theo charset được truyền

Nếu gọi `Files.readString(path, StandardCharsets.UTF_8)` thì dữ liệu được giải mã bằng UTF-8 dù `file.encoding` đang là `COMPAT`. Tương tự, `OutputStreamWriter(out, UTF_8)` luôn mã hóa theo UTF-8. Hợp đồng tại lời gọi API là căn cứ.

### 7.3. `Files.readString(path)` không giống `new String(bytes)`

Hai cách gọi có vẻ tương tự nhưng quy tắc khác nhau:

- `new String(bytes)` dùng charset mặc định của JVM.
- `Files.readString(path)` dùng UTF-8 theo đặc tả API.

Đây là khác biệt quan trọng khi di chuyển code từ API cũ sang NIO.2 hoặc khi kiểm thử trên nhiều hệ điều hành.

### 7.4. `Properties.load(InputStream)` có quy tắc riêng

`Properties.load(InputStream)` diễn giải byte theo ISO-8859-1 và hỗ trợ escape Unicode `\uXXXX`; nó không lấy charset từ `file.encoding`. Nếu file properties được lưu UTF-8, dùng `Properties.load(Reader)` với `InputStreamReader(input, UTF_8)` để quy định charset rõ ràng.

### 7.5. Console và standard streams có thể có charset riêng

Đừng suy luận charset của terminal chỉ từ `file.encoding`. Khi cần kiểm tra output, dùng `System.out.charset()` và `System.err.charset()` trên JDK 18+, và `System.console().charset()` nếu có console. Console có thể không tồn tại khi chạy trong IDE hoặc pipe. Charset hiển thị là một ranh giới riêng với charset của file.

## 8. Quy trình chọn và kiểm chứng charset

1. **Xác định định dạng nguồn/đích:** file, HTTP, classpath, database hay process stream? Tài liệu hoặc bên phát quy định charset nào?
2. **Kiểm tra default runtime:** in `file.encoding`, `native.encoding` và `Charset.defaultCharset()` ở đầu chương trình khi cần chẩn đoán.
3. **Đặt charset tại API:** truyền `StandardCharsets.UTF_8` hoặc charset cụ thể của định dạng vào constructor/overload phù hợp.
4. **So byte thực tế:** dùng `Files.readAllBytes`, `HexFormat` và vector byte mẫu để xác nhận.
5. **So chuỗi sau decode:** dùng `String.equals` và khi cần `codePoints()` để phát hiện thay ký tự.
6. **Chạy hai cấu hình JVM:** so sánh mặc định UTF-8 với `-Dfile.encoding=COMPAT`; kết quả của API tường minh phải giữ nguyên.
7. **Kiểm tra riêng console:** không dùng lỗi hiển thị terminal làm bằng chứng file đã sai; kiểm tra charset stream và byte capture.

Sơ đồ:

```text
Dữ liệu có charset trong hợp đồng?
   |-- Có --> Truyền charset đó vào API.
   |
   +-- Chưa rõ --> Xác minh metadata/bên phát; không đoán từ file.encoding.
                      |
                      v
             API có nhận Charset?
               |-- Có --> Dùng charset tường minh.
               |
               +-- Không --> Xác nhận API thật sự dùng default
                             hay có charset cố định trong đặc tả.
                      |
                      v
              Đối chiếu byte + String trên hai JVM config.
```

## 9. Bài thực hành và tiêu chí hoàn thành

1. Chạy `FileEncodingPropertyCheck` với cấu hình JVM mặc định và `-Dfile.encoding=COMPAT`. Ghi lại default charset thực tế của từng lần chạy.
2. Xác nhận file UTF-8 luôn đọc đúng bằng `new String(bytes, UTF_8)` và `Files.readString(path, UTF_8)`.
3. Tạo file Windows-1252 có byte `63 61 66 E9 20 80`. Xác nhận overload có Windows-1252 đọc đúng; overload UTF-8 cố định có thể từ chối dữ liệu.
4. So sánh `new String(bytes)` và `text.getBytes()` giữa hai lần chạy. Giải thích vì sao kết quả chỉ thay đổi khi default charset khác.
5. Kiểm tra `Files.readString(path)` và `Files.writeString(path, text)` không thay đổi quy tắc UTF-8 khi đổi `file.encoding`.
6. Thử đặt `-Dfile.encoding=windows-1252` trên JDK 18+ và giải thích vì sao không được dùng giá trị tùy ý này như một cấu hình portable.
7. Thử thay đổi `System.setProperty("file.encoding", ...)` trong chương trình đã chạy; xác nhận đây không phải cách cấu hình lại charset mặc định.

**Tiêu chí hoàn thành:** bạn phân biệt được API dùng default charset, API nhận charset tường minh và API có UTF-8 cố định; giải thích đúng vai trò của `file.encoding`, `native.encoding` và `COMPAT`; chứng minh được API tường minh không bị default charset ghi đè; và đọc/ghi file legacy theo charset đã khai báo thay vì suy đoán từ cấu hình JVM.

### Tài liệu tham khảo

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): UTF-8 mặc định, chế độ `COMPAT` và thuộc tính `native.encoding`.
- [Java SE Charset](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/Charset.html): `Charset.defaultCharset()` và charset của runtime.
- [Java SE Files](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): quy tắc UTF-8 của `readString`/`writeString` và overload nhận charset.
- [Java SE String](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): constructor nhận charset và `getBytes(Charset)`.
- [Java SE FileReader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/FileReader.html) và [FileWriter](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/FileWriter.html): overload dùng charset mặc định và overload nhận charset.
