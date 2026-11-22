# Charset, StandardCharsets và lựa chọn UTF-8 tường minh trong Java

Một `String` Java có thể chứa tiếng Việt, chữ Nhật và emoji; nhưng khi **ghi ra file, gửi qua mạng hoặc nhận byte từ hệ thống khác**, chương trình phải chuyển giữa **ký tự** và **byte**. Nếu hai phía không dùng cùng bảng mã, dữ liệu có thể bị biến dạng thành các chuỗi như `"ChÃ o"`, dấu hỏi `?` hoặc ký tự thay thế `�`. Tính năng localization không chỉ là chọn `Locale` cho số/ngày: nội dung Unicode phải đi qua **ranh giới charset** đúng cách.

Trong Java 17+, `java.nio.charset.Charset` biểu diễn một bộ mã hóa/giải mã ký tự; `java.nio.charset.StandardCharsets` cung cấp các đối tượng charset chuẩn có sẵn, quan trọng nhất là **`StandardCharsets.UTF_8`**. Việc truyền UTF-8 **tường minh** ở các API nhận charset giúp hợp đồng file và API không phụ thuộc máy chạy, locale hay phiên bản JDK.

**Nguyên tắc trung tâm:** xác định chính xác nơi dữ liệu chuyển từ `String` sang `byte[]` và ngược lại. Mỗi ranh giới ấy phải dùng charset theo **hợp đồng dữ liệu**, không suy đoán từ vẻ ngoài của văn bản hoặc `Locale.getDefault()`.

Bài này đi từ khái niệm `Charset` và sáu `StandardCharsets` bắt buộc, đến các ví dụ Java 17+ với `String`, `Files`, `Reader/Writer`, `InputStream/OutputStream`, xử lý lỗi encode/decode, UTF-8 BOM, legacy `Properties`, khác biệt JDK 17 so với JDK 18+ và kiểm thử round-trip.

## 1. Ký tự Unicode, UTF-16 của String và byte UTF-8 là ba tầng

Giả sử nguồn văn bản chứa:

```text
Aé😀
```

Đây là **ba Unicode code point**:

| Ký tự | Code point | Số UTF-16 code unit trong Java String | Byte UTF-8 |
| --- | --- | --- | --- |
| `A` | `U+0041` | 1 | `41` |
| `é` | `U+00E9` | 1 | `C3 A9` |
| `😀` | `U+1F600` | 2 (surrogate pair) | `F0 9F 98 80` |

Vậy chuỗi này có `String.length() == 4`, `codePointCount(0, length()) == 3`, nhưng số byte sau khi encode UTF-8 là **7**. Không thể sử dụng `String.length()` để dự đoán độ dài file UTF-8 hoặc kích thước HTTP payload.

`String` là **chuỗi ký tự**; trên API Java, các vị trí của `charAt` và `substring` dựa trên **UTF-16 code units**, không phải byte UTF-8. Charset chỉ xuất hiện khi **encode/decode** giữa ký tự và byte. Đổi `Locale` không tự đổi byte encoding; đổi charset cũng không tự dịch từ ngữ hoặc định dạng lại ngày/giờ.

### Sơ đồ hai chiều

```text
String Java                  byte[] / file / HTTP body
    |                                ^
    | encode bằng UTF-8             |
    +------------------------------->|
    |   String.getBytes(UTF_8)       |
    |                                |
    |<-------------------------------+
    | decode bằng UTF-8
    |   new String(bytes, UTF_8)
```

Khi bên ghi encode UTF-8 mà bên đọc **decode như ISO-8859-1 hoặc Windows-1252**, các byte vẫn tồn tại nhưng được ánh xạ sang ký tự khác: đó là **mojibake**. Khi bộ mã không biểu diễn được một ký tự (ví dụ emoji với ISO-8859-1), encoder có thể thay bằng `?` hoặc báo lỗi tùy API và chính sách.

## 2. Charset và StandardCharsets khác nhau ở đâu?

`Charset` là **kiểu đối tượng** mô tả phép ánh xạ giữa các dãy byte và ký tự. Ta có thể lấy charset theo tên:

```java
Charset utf8 = Charset.forName("UTF-8");
Charset latin1 = Charset.forName("ISO-8859-1");
```

Đây là **fragment Java**, cần `import java.nio.charset.Charset;`. Tên charset có alias, có thể khác chữ hoa/chữ thường trong tên; `charset.name()` trả tên canonical. Khi tên lấy từ cấu hình, hãy kiểm tra có hỗ trợ và xử lý `IllegalCharsetNameException` hoặc `UnsupportedCharsetException` thay vì cứ tin input hợp lệ.

`StandardCharsets` là lớp tiện ích chứa **đối tượng Charset tĩnh** cho sáu charset tiêu chuẩn Java bắt buộc hỗ trợ. Không cần tra cứu bằng chuỗi ở runtime:

| Hằng số | Đặc điểm, tình huống |
| --- | --- |
| `StandardCharsets.US_ASCII` | ASCII 7 bit; không biểu diễn trực tiếp tiếng Việt có dấu |
| `StandardCharsets.ISO_8859_1` | Latin-1; mỗi byte 0x00–0xFF ánh xạ tới một ký tự thuộc vùng tương ứng |
| `StandardCharsets.UTF_8` | Unicode dạng byte độ dài biến thiên; lựa chọn thực tế phổ biến cho file/API |
| `StandardCharsets.UTF_16` | UTF-16, xử lý byte-order mark và thứ tự byte theo định nghĩa charset |
| `StandardCharsets.UTF_16BE` | UTF-16 big endian |
| `StandardCharsets.UTF_16LE` | UTF-16 little endian |

**Khi hợp đồng yêu cầu UTF-8**, ưu tiên `StandardCharsets.UTF_8` thay vì `Charset.forName("UTF-8")`: đây là hằng số rõ nghĩa, không cần gõ đúng tên chuỗi ở nhiều nơi và là charset được Java bảo đảm có sẵn.

**Nhưng** `Charset.forName(...)` vẫn hữu ích khi bắt buộc hỗ trợ input legacy có tên encoding được khai báo trong metadata, ví dụ một file do bên khác gửi ở Windows-1258 hoặc một charset chuyên biệt. Không hard-code tự đoán charset nếu file không có hợp đồng.

### Demo đầu tiên — CharsetBasicsDemo.java

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class CharsetBasicsDemo {
    public static void main(String[] args) {
        String text = "A\u00E9\uD83D\uDE00";
        Charset utf8 = StandardCharsets.UTF_8;
        byte[] bytes = text.getBytes(utf8);

        System.out.println("Charset: " + utf8.name());
        System.out.println("Same charset: "
                + utf8.equals(Charset.forName("utf-8")));
        System.out.println("UTF-16 units: " + text.length());
        System.out.println("Code points: "
                + text.codePointCount(0, text.length()));
        System.out.println("UTF-8 bytes: " + bytes.length);
        System.out.println("Hex: "
                + HexFormat.ofDelimiter(" ")
                        .withUpperCase().formatHex(bytes));
        System.out.println("Round trip: "
                + text.equals(new String(bytes, utf8)));
    }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac -encoding UTF-8 CharsetBasicsDemo.java
java CharsetBasicsDemo
```

Stdout:

```text
Charset: UTF-8
Same charset: true
UTF-16 units: 4
Code points: 3
UTF-8 bytes: 7
Hex: 41 C3 A9 F0 9F 98 80
Round trip: true
```

Ở đây `HexFormat` là API sẵn có từ **Java 17**. Chuỗi `\uD83D\uDE00` trong mã nguồn là cặp surrogate hợp lệ để tạo emoji `U+1F600`. Đầu ra hex chứng minh số byte: **1 + 2 + 4 = 7**, độc lập locale.

Lệnh `javac -encoding UTF-8` chỉ xác định **charset của file nguồn `.java`** mà compiler đọc; nó **không tự động thay đổi** charset của mọi file mà ứng dụng sẽ đọc/ghi khi chạy. Đây là hai ranh giới encoding khác nhau.

## 3. UTF-8 là một encoding, không phải một Locale

`Locale` như `vi-VN`, `en-US` hoặc `ja-JP` mô tả ngữ cảnh ngôn ngữ/khu vực để định dạng số, ngày, quy tắc tên hiển thị hay chọn bundle dịch. **UTF-8** mô tả cách mã hóa Unicode code point thành byte.

Có thể:

- Dùng `Locale.FRANCE` nhưng **ghi file bằng UTF-8**.
- Dùng `Locale.forLanguageTag("vi-VN")` nhưng **đọc JSON bằng UTF-8**.
- Hiển thị ngày theo `Locale.GERMANY` rồi gửi một trường ngày ISO `2026-10-28` dưới dạng **UTF-8**.
- Đọc file legacy bằng ISO-8859-1 nếu **hợp đồng file nói vậy**, dù nội dung cần hiển thị tại Việt Nam.

**Không có ánh xạ “người Việt thì dùng một encoding riêng, người Nhật thì encoding khác”** cho ứng dụng Unicode hiện đại. UTF-8 hỗ trợ tất cả các ngôn ngữ Unicode được mã hóa; lựa chọn locale cho UI là quyết định khác.

Ngoài ra, **UTF-8 không tự chuẩn hóa Unicode**. Hai chuỗi canonically equivalent, ví dụ `U+00E9` và `U+0065 U+0301`, khi encode đều hợp lệ nhưng có byte khác nhau. Nếu nghiệp vụ cần canonical equivalence, dùng thêm `java.text.Normalizer` theo chính sách, không mong encoder tự làm NFC.

## 4. Đừng phụ thuộc default charset ở những API có hợp đồng bên ngoài

Java có `Charset.defaultCharset()`, phản ánh default charset tại runtime. Tuy nhiên, khi viết:

```java
byte[] bytes = text.getBytes();
String restored = new String(bytes);
```

hai lời gọi **không truyền charset** sử dụng **default charset** của JVM cho các overload này. Nếu file hoặc byte được tạo ở môi trường khác, không có bảo đảm bên kia giải mã cùng encoding.

Đối với byte theo hợp đồng UTF-8, hãy viết:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);
```

Các đoạn trên là **fragment**, cần `text` và imports tương ứng. Với môi trường và chuỗi hợp lệ, cặp UTF-8 này có thể round-trip các ký tự Unicode mà không phụ thuộc default locale.

### JDK 17 khác JDK 18+ ở điểm nào?

- **Java 17 trở về trước:** default charset thường phụ thuộc hệ điều hành, locale và cấu hình runtime; không được mặc định rằng nó luôn là UTF-8.
- **Java 18 trở lên:** [JEP 400](https://openjdk.org/jeps/400) quy định UTF-8 là default charset cho các API Java SE thuộc phạm vi thay đổi, với các cơ chế cấu hình/ngoại lệ đã được tài liệu hóa. Vì vậy nhiều lời gọi không truyền charset hoạt động ổn định hơn trên JDK mới.
- **Dù vậy, nên dùng UTF-8 tường minh cho giao thức/file có contract**: code có thể được chạy lại trên Java 17, các API cũ có ngoại lệ, hệ thống legacy có encoding khác, và bên nhận vẫn cần biết hợp đồng.

**Không suy ra encoding của terminal/stdout chỉ từ `Charset.defaultCharset()`.** Console, shell, IDE và môi trường chạy có thể có cách mã hóa/hiển thị khác. Nếu chuỗi trong chương trình là Unicode đúng nhưng terminal hiện dấu hỏi hoặc ký tự lạ, hãy kiểm tra cả console encoding, font, terminal renderer và đường ống output, không chỉ sửa file input.

### Ví dụ quan sát default charset mà không giả định output

**`DefaultCharsetInfo.java`**:

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

public class DefaultCharsetInfo {
    public static void main(String[] args) {
        System.out.println("Default: "
                + Charset.defaultCharset().name());
        System.out.println("Explicit: "
                + StandardCharsets.UTF_8.name());
    }
}
```

```bash
javac -encoding UTF-8 DefaultCharsetInfo.java
java DefaultCharsetInfo
```

Dòng thứ hai luôn là `Explicit: UTF-8`; dòng đầu thay đổi tùy JDK/môi trường cấu hình, nên không đưa một giá trị mặc định duy nhất làm stdout cho mọi máy. Chương trình này dùng để **chẩn đoán**, không phải để chọn encoding cho file mới bằng cách lấy default.

## 5. Files.writeString và Files.readString: chọn UTF-8 rõ ràng

Java NIO cung cấp các API tiện cho file text:

```java
Files.writeString(path, content, StandardCharsets.UTF_8);
String text = Files.readString(path, StandardCharsets.UTF_8);
```

Đây là **fragment** với `path` là `Path` và `content` là `String`; cần imports `java.nio.file.Files`, `Path` và `java.nio.charset.StandardCharsets`.

**Điều quan trọng về overload:** `Files.writeString(path, content)` và `Files.readString(path)` trong Java 17 **đã dùng UTF-8 theo tài liệu**, không phải default charset của hệ điều hành. Truyền `StandardCharsets.UTF_8` vẫn hữu ích để thấy rõ hợp đồng và thuận tiện khi chuyển sang API khác. Đừng nói rằng **mọi overload không có Charset** trong Java đều dùng default: một số API NIO mới mặc định UTF-8, còn nhiều constructor Reader/Writer/`String.getBytes()` cũ lại lấy default charset.

### Chương trình chạy độc lập — Utf8FilesDemo.java

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class Utf8FilesDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("utf8-demo-", ".txt");
        String original = "Tiếng Việt: Chào bạn!";

        try {
            Files.writeString(file, original, StandardCharsets.UTF_8);
            String restored =
                    Files.readString(file, StandardCharsets.UTF_8);

            System.out.println("Equal: "
                    + original.equals(restored));
            System.out.println("UTF-8 bytes: "
                    + Files.size(file));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac -encoding UTF-8 Utf8FilesDemo.java
java Utf8FilesDemo
```

Đầu ra của dòng `Equal` luôn là `true` nếu ghi/đọc thành công. Dòng `UTF-8 bytes` là độ dài byte thực tế của chuỗi, **không** bằng số UTF-16 units khi có ký tự tiếng Việt có dấu. Có thể tính trực tiếp trong IDE để so sánh với `original.getBytes(StandardCharsets.UTF_8).length`; ví dụ trên không hard-code stdout của dòng số byte vì mục tiêu là minh họa đúng nguyên tắc đếm byte.

**Lưu ý lỗi I/O:** ở production, cần xử lý quyền ghi, đường dẫn, dung lượng, atomic file update và cleanup; ví dụ chỉ dùng file tạm và xóa ở `finally`. Nếu dữ liệu từ nguồn không tin cậy, kiểm tra giới hạn kích thước trước khi đọc toàn file vào memory.

### BufferedReader và BufferedWriter

Khi file lớn hoặc cần xử lý theo từng dòng, dùng:

```java
try (BufferedReader in =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = in.readLine()) != null) {
        // Xử lý một dòng.
    }
}

try (BufferedWriter out =
        Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    out.write("Chào");
    out.newLine();
}
```

Đây là **fragment**; cần `BufferedReader`, `BufferedWriter`, `Files`, `Path`, `StandardCharsets`. `newLine()` dùng line separator của nền tảng nên nếu một format máy đọc yêu cầu **LF cố định**, thay bằng `out.write('\n')` và quy định newline trong contract.

**Overload của `Files.newBufferedReader(path)` cũng dùng UTF-8**, nhưng overload có charset giúp code tự mô tả rõ. Một số API như `Files.lines(path, UTF_8)` trả stream cần đóng bằng try-with-resources khi đọc file.

## 6. Byte stream và Character stream: biết chính xác chỗ chuyển đổi

Java chia I/O thành hai nhóm chính:

| Nhóm | API | Dữ liệu mà nó trực tiếp xử lý |
| --- | --- | --- |
| Byte stream | `InputStream`, `OutputStream`, `Files.readAllBytes` | Byte thô; **không** tự biết văn bản UTF-8 |
| Character stream | `Reader`, `Writer`, `BufferedReader`, `BufferedWriter` | Ký tự; phải **decode/encode** khi nối với byte stream |
| Cầu nối | `InputStreamReader`, `OutputStreamWriter` | Dùng một `Charset` để chuyển byte ↔ char |

Hãy dùng:

```java
Reader reader = new InputStreamReader(
        inputStream, StandardCharsets.UTF_8);
Writer writer = new OutputStreamWriter(
        outputStream, StandardCharsets.UTF_8);
```

Đây là fragment với `inputStream`/`outputStream` đã khai báo. Không bỏ tham số `StandardCharsets.UTF_8` nếu hợp đồng yêu cầu UTF-8: constructor `new InputStreamReader(inputStream)` hoặc `new OutputStreamWriter(outputStream)` có thể chọn **default charset** thay vì UTF-8 tường minh.

### Ví dụ byte stream ↔ character stream

Lưu **`Utf8StreamBridgeDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;

public class Utf8StreamBridgeDemo {
    public static void main(String[] args) throws Exception {
        String expected = "Chào Việt Nam";
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();

        try (OutputStreamWriter writer = new OutputStreamWriter(
                buffer, StandardCharsets.UTF_8)) {
            writer.write(expected);
        }

        byte[] wire = buffer.toByteArray();
        StringBuilder result = new StringBuilder();

        try (InputStreamReader reader = new InputStreamReader(
                new ByteArrayInputStream(wire),
                StandardCharsets.UTF_8)) {
            char[] chars = new char[64];
            int n;
            while ((n = reader.read(chars)) != -1) {
                result.append(chars, 0, n);
            }
        }

        System.out.println("Round trip: "
                + expected.contentEquals(result));
        System.out.println("Bytes match UTF-8: "
                + java.util.Arrays.equals(
                        wire,
                        expected.getBytes(StandardCharsets.UTF_8)));
    }
}
```

```bash
javac -encoding UTF-8 Utf8StreamBridgeDemo.java
java Utf8StreamBridgeDemo
```

Stdout:

```text
Round trip: true
Bytes match UTF-8: true
```

Cần `flush()` hoặc `close()` writer trước khi lấy toàn bộ byte, vì encoder có thể giữ dữ liệu tạm. Trong ví dụ, khối try-with-resources đã đóng writer xong trước `toByteArray()`. `ByteArrayOutputStream.toByteArray()` vẫn hoạt động sau khi writer đóng stream vì `ByteArrayOutputStream.close()` không làm các lời gọi sau bị lỗi.

Nếu input từ mạng, đảm bảo giới hạn độ dài/timeout và protocol framing; `Reader` không xác định boundary của JSON message hay bản ghi TCP thay cho parser giao thức.

## 7. Những API không có charset: phân biệt đúng trường hợp

Không áp một quy tắc chung “bỏ Charset là sai” mà không nhìn **hợp đồng API**. Một bảng kiểm tra quan trọng trên Java 17:

| API/overload | Quy tắc encoding cần biết | Lựa chọn khi contract UTF-8 |
| --- | --- | --- |
| `String.getBytes()` | Dùng default charset | `getBytes(StandardCharsets.UTF_8)` |
| `new String(byte[])` | Dùng default charset | `new String(bytes, StandardCharsets.UTF_8)` |
| `new InputStreamReader(stream)` | Dùng default charset | `new InputStreamReader(stream, UTF_8)` |
| `new OutputStreamWriter(stream)` | Dùng default charset | `new OutputStreamWriter(stream, UTF_8)` |
| `new FileReader(file)` (Java 17) | Dùng default charset | Constructor nhận Charset hoặc `Files.newBufferedReader(path, UTF_8)` |
| `new FileWriter(file)` (Java 17) | Dùng default charset | Constructor nhận Charset hoặc `Files.newBufferedWriter(path, UTF_8)` |
| `Files.readString(path)` | **UTF-8**, đã định nghĩa | `Files.readString(path, UTF_8)` để rõ hợp đồng |
| `Files.writeString(path, text)` | **UTF-8**, đã định nghĩa | `Files.writeString(path, text, UTF_8)` |
| `Files.newBufferedReader(path)` | **UTF-8**, đã định nghĩa | Overload có charset khi muốn rõ |
| `Files.newBufferedWriter(path)` | **UTF-8**, đã định nghĩa | Overload có charset khi muốn rõ |
| `Files.readAllBytes(path)` | **Không decode**, trả bytes | Decode sau bằng Charset hợp đồng |
| `Files.write(path, byte[])` | **Không encode**, ghi bytes | Encode trước nếu nguồn là String |

Mục tiêu của việc **chọn UTF-8 tường minh** là làm rõ ranh giới byte/char và giữ tính tái lập của file/API, không phải khẳng định mọi method thiếu đối số charset đều giống nhau.

**Đừng nhầm** `Locale.getDefault(Locale.Category.FORMAT)` với `Charset.defaultCharset()`. Locale định dạng và charset mặc định là hai thông tin khác nhau; bạn không nên định nghĩa charset chỉ qua locale của người dùng.

## 8. Decode sai charset tạo mojibake, không phải lỗi font đơn thuần

Cùng một mảng byte có thể được diễn giải thành các code point khác nhau theo charset. Ví dụ chữ `é` trong UTF-8 có hai byte `C3 A9`. Nếu decode hai byte này theo `ISO-8859-1`, kết quả là hai ký tự `Ã©` thay vì `é`.

**File `MojibakeDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class MojibakeDemo {
    public static void main(String[] args) {
        String expected = "\u00E9";
        byte[] utf8 = expected.getBytes(StandardCharsets.UTF_8);

        String correct = new String(utf8, StandardCharsets.UTF_8);
        String wrong = new String(
                utf8, StandardCharsets.ISO_8859_1);

        System.out.println("UTF-8 hex: "
                + HexFormat.ofDelimiter(" ")
                        .withUpperCase().formatHex(utf8));
        System.out.println("Correct: " + correct.equals(expected));
        System.out.println("Wrong: " + wrong.equals(expected));
        System.out.println("Wrong UTF-16 length: " + wrong.length());
        System.out.println("Wrong code points: "
                + wrong.codePointCount(0, wrong.length()));
    }
}
```

```bash
javac -encoding UTF-8 MojibakeDemo.java
java MojibakeDemo
```

Stdout:

```text
UTF-8 hex: C3 A9
Correct: true
Wrong: false
Wrong UTF-16 length: 2
Wrong code points: 2
```

Giải thích: giải mã sai không làm byte đầu vào tự biến mất; nó **tạo chuỗi khác**. Nếu chuỗi sai đó lại được encode và lưu nhiều lần, quá trình mojibake có thể trở nên phức tạp hơn. Tìm đúng charset thực tế của nguồn và decode **một lần đúng cách**; không sửa mọi văn bản bằng thay chuỗi `"Ã"` hay `"Â"` theo regex.

**Lưu ý:** ISO-8859-1 có ánh xạ cho mọi byte 0x00–0xFF, nên nó có thể tạo ra văn bản “trông lỗi” nhưng không ném lỗi. UTF-8 có quy tắc byte hợp lệ rõ hơn và có thể báo lỗi nếu input vi phạm encoding. Tuy nhiên, một byte stream hợp lệ UTF-8 vẫn có thể chứa nội dung nghiệp vụ sai; hợp lệ về encoding ≠ hợp lệ về dữ liệu.

## 9. Malformed input và unmappable characters: REPLACE khác REPORT

Có hai nhóm lỗi khác nhau:

- **Malformed input khi decode:** byte không tuân thủ quy tắc của charset được khai báo, chẳng hạn byte đầu UTF-8 `C3` không theo sau bằng continuation byte hợp lệ.
- **Unmappable character khi encode:** ký tự Unicode không biểu diễn được trong charset đích, chẳng hạn emoji khi encode ISO-8859-1.

Một số API tiện lợi như `new String(bytes, StandardCharsets.UTF_8)` có thể **thay dãy byte sai** bằng ký tự thay thế Unicode `U+FFFD` thay vì ném exception. `String.getBytes(charset)` có thể thay ký tự không biểu diễn được bằng byte thay thế. Với dữ liệu cần bảo toàn chính xác, lựa chọn thay thế âm thầm có thể là rủi ro.

`CharsetDecoder` và `CharsetEncoder` cho phép thiết lập chính sách:

| Chính sách | Hành vi |
| --- | --- |
| `CodingErrorAction.REPORT` | Báo lỗi qua `CharacterCodingException` và subtype |
| `CodingErrorAction.REPLACE` | Thay lỗi bằng ký tự/byte thay thế |
| `CodingErrorAction.IGNORE` | Bỏ qua lỗi; nguy cơ mất dữ liệu |

`Charset.newDecoder()`/`newEncoder()` tạo các đối tượng **có trạng thái**, không thread-safe; mặc định xử lý lỗi bằng `REPORT`, và có thể cấu hình `onMalformedInput` và `onUnmappableCharacter`.

### Decode UTF-8 nghiêm ngặt

**File `StrictUtf8DecoderDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.StandardCharsets;
import java.nio.charset.CodingErrorAction;

public class StrictUtf8DecoderDemo {
    public static void main(String[] args) {
        byte[] invalid = {(byte) 0xC3, (byte) 0x28};
        String replaced = new String(
                invalid, StandardCharsets.UTF_8);

        System.out.println("Has replacement: "
                + replaced.contains("\uFFFD"));

        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(invalid));
            System.out.println("Unexpected acceptance");
        } catch (CharacterCodingException ex) {
            System.out.println("Strict decoder rejected bytes");
        }
    }
}
```

```bash
javac -encoding UTF-8 StrictUtf8DecoderDemo.java
java StrictUtf8DecoderDemo
```

Stdout:

```text
Has replacement: true
Strict decoder rejected bytes
```

Khi cần **cấm dữ liệu UTF-8 sai** trong import/API, dùng decoder `REPORT` hoặc API I/O có hợp đồng báo lỗi phù hợp thay vì kiểm tra thủ công chuỗi xem có ký tự `�` hay không. Chính ký tự `U+FFFD` cũng có thể xuất hiện hợp lệ trong văn bản nguồn, nên kiểm tra chuỗi sau decode không đủ để phân biệt nó đến từ byte lỗi hay người dùng cố ý nhập.

### Encode sang charset không hỗ trợ Unicode đầy đủ

**File `StrictEncoderDemo.java`**:

```java
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.StandardCharsets;
import java.nio.charset.CodingErrorAction;

public class StrictEncoderDemo {
    public static void main(String[] args) {
        String value = "A\uD83D\uDE00"; // A😀

        byte[] lossy = value.getBytes(
                StandardCharsets.ISO_8859_1);
        System.out.println("Lossy bytes: " + lossy.length);
        System.out.println("Lossy is A?: "
                + new String(lossy,
                        StandardCharsets.ISO_8859_1)
                        .equals("A?"));

        try {
            StandardCharsets.ISO_8859_1.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(value));
            System.out.println("Unexpected acceptance");
        } catch (CharacterCodingException ex) {
            System.out.println("Strict encoder rejected character");
        }
    }
}
```

```bash
javac -encoding UTF-8 StrictEncoderDemo.java
java StrictEncoderDemo
```

Stdout với encoder chuẩn của Java:

```text
Lossy bytes: 2
Lossy is A?: true
Strict encoder rejected character
```

Emoji không được biểu diễn trong ISO-8859-1, nên cách mã hóa tiện lợi có thể tạo dấu `?`; strict encoder ném lỗi. **UTF-8** có khả năng mã hóa mọi Unicode scalar value hợp lệ, nhưng `String` Java cũng có thể chứa surrogate đơn lẻ không hợp lệ; strict encoder vẫn có thể báo malformed input khi gặp chúng.

**Thiết kế import an toàn:** xác định xem file sai byte có phải bị từ chối, cách ly, cho phép sửa hoặc hiển thị ký tự thay thế. Đừng dùng `IGNORE` cho các trường định danh/mã giao dịch cần bảo toàn chính xác.

## 10. Byte Order Mark (BOM) trong UTF-8

UTF-8 không cần thứ tự byte lớn/bé như UTF-16, nên **BOM không cần thiết để xác định endianness**. Một số file UTF-8 vẫn bắt đầu bằng ba byte:

```text
EF BB BF
```

Khi decode như UTF-8, dãy này tương ứng ký tự **`U+FEFF`** ở đầu chuỗi. Nhiều parser hoặc editor có chính sách phát hiện/bỏ BOM, nhưng **không nên mặc định mọi Java API sẽ tự bỏ nó**. Nếu hợp đồng file không cho phép BOM, từ chối hoặc xử lý tường minh.

### Demo nhận diện BOM

**`Utf8BomDemo.java`**:

```java
import java.nio.charset.StandardCharsets;

public class Utf8BomDemo {
    public static void main(String[] args) {
        byte[] bytes = {
                (byte) 0xEF, (byte) 0xBB, (byte) 0xBF,
                (byte) 'A'
        };

        String decoded = new String(
                bytes, StandardCharsets.UTF_8);

        System.out.println("Length: " + decoded.length());
        System.out.println("Starts with BOM char: "
                + decoded.startsWith("\uFEFF"));
        System.out.println("After explicit removal: "
                + decoded.substring(1).equals("A"));
    }
}
```

```bash
javac -encoding UTF-8 Utf8BomDemo.java
java Utf8BomDemo
```

Stdout:

```text
Length: 2
Starts with BOM char: true
After explicit removal: true
```

Chỉ bỏ ký tự `U+FEFF` **nếu nó nằm ở vị trí đầu và contract của định dạng cho phép xử lý BOM**. Không dùng `replace("\uFEFF", "")` trên toàn văn bản như một chính sách phổ quát. Đối với JSON và các protocol khác, tuân thủ quy định của định dạng/parser thay vì tự sửa payload mà không có hợp đồng.

**UTF-16 có câu chuyện BOM và thứ tự byte khác:** `UTF_16`, `UTF_16BE`, `UTF_16LE` không thể hoán đổi tùy ý. Nếu bên ngoài yêu cầu UTF-16LE không BOM, hãy dùng đúng constant và xác nhận cách decoder tương ứng xử lý; đừng nghĩ UTF-8 BOM là bắt buộc như một số định dạng UTF-16.

## 11. Khi legacy API không dùng UTF-8 theo mặc định

Một bẫy phổ biến là **`java.util.Properties.load(InputStream)`**. Theo hợp đồng Java, cách đọc này dùng ISO-8859-1 cho file `.properties` dạng byte, hỗ trợ Unicode qua escape `\uXXXX` trong format properties truyền thống. Nếu bạn đưa vào byte UTF-8 trực tiếp, có thể nhận **mojibake** mà không ném lỗi.

Trái lại, `Properties.load(Reader)` nhận **ký tự đã được Reader decode**, nên có thể dùng `InputStreamReader(..., StandardCharsets.UTF_8)` để đọc nội dung UTF-8 đúng theo cấu hình file.

### Chương trình chạy được — PropertiesEncodingDemo.java

```java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public class PropertiesEncodingDemo {
    public static void main(String[] args) throws Exception {
        byte[] input = "title=caf\u00E9\n"
                .getBytes(StandardCharsets.UTF_8);

        Properties latin1 = new Properties();
        latin1.load(new ByteArrayInputStream(input));

        Properties utf8 = new Properties();
        try (InputStreamReader reader = new InputStreamReader(
                new ByteArrayInputStream(input),
                StandardCharsets.UTF_8)) {
            utf8.load(reader);
        }

        System.out.println("InputStream correct: "
                + "caf\u00E9".equals(
                        latin1.getProperty("title")));
        System.out.println("Reader UTF-8 correct: "
                + "caf\u00E9".equals(
                        utf8.getProperty("title")));
    }
}
```

```bash
javac -encoding UTF-8 PropertiesEncodingDemo.java
java PropertiesEncodingDemo
```

Stdout:

```text
InputStream correct: false
Reader UTF-8 correct: true
```

**Quan trọng:** không áp câu “Java 18+ mặc định UTF-8” để thay đổi hợp đồng cố định của `Properties.load(InputStream)`. Đây là API có charset được quy định riêng, không phụ thuộc default charset của JVM.

`ResourceBundle`/`PropertyResourceBundle` lại có những quy tắc đặc thù khác: trên Java 9+, `PropertyResourceBundle(InputStream)` dùng UTF-8 trước rồi có cơ chế fallback ISO-8859-1 nếu decode UTF-8 gặp byte malformed/unmappable (trừ khi cấu hình encoding được chỉ định). Vì thế **không đồng nhất `Properties.load(InputStream)` với `PropertyResourceBundle(InputStream)`** dù cả hai đều có thể đọc file `.properties`. Luôn đọc đúng tài liệu API và version đang triển khai.

## 12. Chọn charset đúng khi nhận nội dung từ bên ngoài

Không phải dữ liệu nào cũng là UTF-8. Ví dụ một đối tác gửi file legacy khai báo charset ISO-8859-1, hoặc một hệ thống cũ xuất theo một code page của Windows. Quy tắc đúng là:

1. **Xác định contract của nguồn**: charset, format, schema, liệu có BOM và xử lý lỗi.
2. **Validate/chấp nhận charset**: nếu tên charset nằm trong metadata, có thể dùng `Charset.forName(...)` sau khi kiểm tra whitelist cho các encoding được hỗ trợ.
3. **Decode một lần từ byte thô** bằng charset đã chọn, với hành vi lỗi `REPORT`/`REPLACE` theo chính sách.
4. **Chuyển về mô hình Unicode trong bộ nhớ**: `String`/đối tượng có kiểu; xác thực nghiệp vụ.
5. **Encode khi xuất** theo charset đích của giao thức, thường UTF-8 trong hệ thống mới.
6. **Ghi rõ quá trình chuyển đổi** nếu cần audit; không âm thầm thay ký tự không biểu diễn được.

**Không chọn encoding bằng cách thử lần lượt cho đến khi không ném lỗi rồi kết luận đúng.** ISO-8859-1 có thể decode mọi byte, nhưng kết quả vẫn sai nghĩa. UTF-8 decode thành công cũng không bảo đảm đây là dữ liệu đúng nội dung. Charset detection mang tính heuristic nếu không có metadata; cần nguồn đáng tin hoặc quy tắc riêng.

Đối với các nội dung theo giao thức có quy tắc charset bắt buộc (JSON, HTTP payload theo content-type và specification, các file encoding cố định), **tuân thủ giao thức** chứ không yêu cầu người dùng chọn charset tùy tiện.

### Ví dụ khi cần charset theo cấu hình

```java
Charset sourceCharset = Charset.forName(
        configuredCharsetName);
String text = Files.readString(path, sourceCharset);
```

Đây là **fragment**, giả định nguồn `configuredCharsetName` đã qua policy kiểm soát và import `java.nio.charset.Charset`, `java.nio.file.Files`. Không đưa tên charset từ user input trực tiếp vào một pipeline không có giới hạn loại file/kích thước; cũng cần xử lý lỗi unsupported charset và malformed input.

## 13. UTF-8 với JSON, CSV, HTTP và database

### JSON và HTTP

Khi ứng dụng serializes JSON, dùng **thư viện JSON** thay vì nối chuỗi thủ công. Trong hệ thống HTTP hiện đại, JSON được trao đổi ở **UTF-8** theo quy tắc format và giao thức; `application/json` là media type phù hợp. Đừng dùng `NumberFormat` phụ thuộc locale để ghi JSON number: JSON có grammar số của chính nó, không dùng dấu phân nhóm kiểu `1.234,50`.

`Charset` xử lý **byte của JSON**, còn serializer xử lý **escape, kiểu dữ liệu và cấu trúc JSON**. UTF-8 không thay thế JSON escaping và không quyết định xem một trường là number, string, boolean hay ngày ISO.

### CSV và văn bản bảng

CSV cần hợp đồng đủ phần: **UTF-8**, delimiter, quoting, newline, header và schema. Ví dụ một field tên người chứa dấu phẩy phải được quote theo quy tắc CSV; chỉ dùng UTF-8 là chưa đủ để parser nhận đúng các cột. Khi bên nhận là phần mềm bảng tính có default locale khác, đừng đổi định dạng decimal ở cột máy đọc theo dấu thập phân của máy chủ.

### Database

Trong JDBC, hãy truyền dữ liệu **có kiểu** qua `PreparedStatement`, ví dụ `setString` cho văn bản Unicode, `setBigDecimal` cho decimal, `setObject` cho `LocalDate` khi driver hỗ trợ, thay vì tự format chuỗi rồi nối SQL. Charset/collation của connection/database/driver có thể ảnh hưởng việc lưu và so Unicode, nhưng đó là **hợp đồng hạ tầng riêng**; `StandardCharsets.UTF_8` khi ghi file không tự quyết định encoding của một cột database.

### Network streams

`Socket.getInputStream()` và `getOutputStream()` trả **byte streams**. Đưa chúng qua `InputStreamReader`/`OutputStreamWriter` UTF-8 chỉ phù hợp với **giao thức văn bản** và khi protocol framing đã rõ. Nếu gửi message theo length-prefix byte, độ dài prefix phải là **số byte đã encode**, không phải `String.length()`.

## 14. Charset và hiệu năng khi xử lý nhiều dữ liệu

`StandardCharsets.UTF_8` là một `Charset` có thể tái sử dụng. Nhưng **`CharsetEncoder` và `CharsetDecoder` là các đối tượng có trạng thái**, không chia sẻ cùng một instance giữa nhiều thread mà không có cơ chế quản lý đồng bộ. Khi xử lý nhiều file, tạo decoder/encoder riêng mỗi lần sử dụng hoặc theo lifecycle một task.

Các API toàn bộ file như `Files.readString` rất tiện nhưng không phù hợp với file cực lớn hoặc input không tin cậy không có giới hạn. `BufferedReader`/`BufferedWriter` hoặc NIO channels với buffers giúp xử lý streaming; cần tính đến boundary byte nhiều phần của UTF-8:

```text
Code point 😀 = F0 9F 98 80

Chunk 1: F0 9F
Chunk 2: 98 80

Không thể decode từng chunk độc lập rồi nối String
nếu không duy trì trạng thái decoder phù hợp.
```

Nếu dùng `InputStreamReader`, Java duy trì trạng thái decoder để xử lý ký tự có byte bị chia qua các lần đọc stream. Nếu tự dùng `CharsetDecoder` trên `ByteBuffer` theo từng chunk, phải xử lý `CoderResult.UNDERFLOW`, byte còn dư, end-of-input và `flush` đúng cách. Không áp công thức `new String(chunkBytes, UTF_8)` độc lập cho mỗi chunk khi chunk có thể cắt giữa multibyte sequence.

**Khi cần tốc độ:** đo bằng workload thật và đặc biệt kiểm tra số byte/chuỗi lỗi, không sửa sang charset cũ chỉ vì nhầm rằng một byte/char luôn nhanh hơn; an toàn dữ liệu và interoperability quan trọng hơn việc tối ưu vi mô chưa chứng minh.

## 15. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `getBytes()` và `new String(bytes)` không chỉ định charset cho dữ liệu trao đổi | Phụ thuộc default JVM | Dùng `StandardCharsets.UTF_8` |
| Coi `Locale.forLanguageTag("vi-VN")` làm UTF-8 | Locale không là encoding | Chọn Locale và Charset độc lập |
| Dùng `String.length()` làm Content-Length HTTP UTF-8 | Sai với chữ có dấu/emoji | Tính số byte thực tế |
| Đọc UTF-8 bằng ISO-8859-1 | Mojibake `Ã©` | Decode đúng charset của nguồn |
| Encode tiếng Việt sang ASCII/Latin-1 rồi bỏ qua replacement | Mất ký tự | UTF-8 hoặc strict encoder `REPORT` |
| Tin mọi API không nhận charset đều giống nhau | `Files.readString` khác `FileReader` trên Java 17 | Xem hợp đồng overload |
| Tin Java 18+ khiến mọi thư viện luôn UTF-8 | Có API legacy quy định encoding riêng | Phân tích đúng từng API |
| Dùng `Properties.load(InputStream)` cho file UTF-8 trực tiếp | ISO-8859-1 decoding làm sai chuỗi | `load(Reader)` với UTF-8 hoặc API bundle đúng |
| Dùng `InputStreamReader(stream)` ở HTTP file có UTF-8 contract | Default charset không chắc là UTF-8 | Truyền UTF-8 |
| Trộn `UTF_16LE` và `UTF_16BE` | Sai thứ tự byte | Dùng đúng charset và BOM policy |
| Xóa `U+FEFF` ở mọi vị trí | Tự sửa dữ liệu không đúng | Chỉ xử lý BOM đầu nếu contract cho phép |
| Dựa vào `Charset.isSupported(...)` để phát hiện encoding file | Chỉ biết JVM hỗ trợ charset, không biết file thuộc encoding đó | Dùng metadata/contract nguồn |
| Cho rằng UTF-8 tự sửa Unicode NFC/NFD | Normalization khác encoding | `Normalizer` riêng khi cần |
| Dùng `CodingErrorAction.IGNORE` với mã ID | Bỏ byte/ký tự âm thầm | Dùng `REPORT` và validation |
| Decode mỗi network chunk độc lập | Có thể cắt đôi multibyte character | Dùng streaming Reader/decoder có trạng thái |
| Chia sẻ một `CharsetDecoder` giữa nhiều thread | Decoder mutable | Tạo riêng hoặc đồng bộ rõ |
| Thấy ký tự lỗi trên console rồi lập tức sửa dữ liệu nguồn | Có thể lỗi ở terminal/font/output encoding | Kiểm tra từng ranh giới byte/char |
| Trộn format số theo locale vào JSON số | JSON sai syntax | Serialize JSON typed data |
| Không định nghĩa newline/quoting của CSV | File UTF-8 vẫn parse sai | Định nghĩa format toàn diện |
| Không giới hạn file/user input | Dễ tốn bộ nhớ/tài nguyên | Giới hạn byte, stream, kiểm tra error |

## 16. Bài tập thực hành

**Bài 1 — Hex và độ dài.** Với `"Aé😀"`, dùng `String.length`, `codePointCount`, `getBytes(StandardCharsets.UTF_8).length` và `HexFormat`. Dự đoán `4`, `3`, `7` và các byte `41 C3 A9 F0 9F 98 80`. Thay chữ `é` bằng `e\u0301` và giải thích vì sao cùng hình ảnh hiển thị thường gặp lại cho nhiều byte hơn: Unicode normalization là vấn đề khác charset.

**Bài 2 — File UTF-8 qua hai overload.** Tạo file tạm với `Files.writeString(path, "Chào", UTF_8)`, đọc bằng `Files.readString(path, UTF_8)`. So sánh với overload `Files.readString(path)` trong Java 17. Vì sao cả hai cách đều đúng cho UTF-8, nhưng constructor `new FileReader(file)` không cho phép suy luận tương tự trong Java 17?

**Bài 3 — Stream.** Chạy `Utf8StreamBridgeDemo` rồi thay `UTF_8` ở Reader bằng `ISO_8859_1`, quan sát chuỗi không còn bằng nguồn. Quay lại cùng charset ở hai đầu và tính byte size theo `getBytes`.

**Bài 4 — Byte sai.** Dùng mảng byte `C3 28`. So `new String(bytes, UTF_8)` với decoder `REPORT`. Trong hệ thống import giao dịch, chọn từ chối file hay thay ký tự? Viết policy có mã lỗi và vị trí byte lỗi khi cần.

**Bài 5 — Legacy properties.** Chạy `PropertiesEncodingDemo`. Giải thích chính xác vì sao `load(InputStream)` đọc sai byte UTF-8 còn `load(Reader UTF-8)` đúng. Thử file legacy ISO-8859-1 hợp lệ và so hành vi; không kết luận JDK nào cũng tự nhận biết encoding từ `.properties`.

**Bài 6 — BOM.** Lấy mảng byte `EF BB BF 41`, decode UTF-8 và so `length`/code point đầu. Thiết kế policy một file CSV: chấp nhận BOM đầu hay từ chối? Đừng xóa mọi `U+FEFF` ở bất kỳ vị trí.

**Bài 7 — Streaming.** Giả lập chia bốn byte UTF-8 của emoji thành hai chunk `F0 9F` và `98 80`. Giải thích vì sao `new String` trên mỗi chunk sai; viết phiên bản dùng `InputStreamReader` trên một luồng chứa cả hai chunk hoặc một `CharsetDecoder` duy trì trạng thái.

## 17. Checklist chọn UTF-8 tường minh cho ứng dụng

1. **Xác định ranh giới:** mỗi file, payload, socket, queue, archive chứa text phải có charset theo contract.
2. **Chọn API:** bytes dùng `InputStream/OutputStream`; text dùng `Reader/Writer` hoặc `Files`; đặt UTF-8 ở điểm nối.
3. **Đối chiếu overload:** đọc docs trước khi suy luận default. `Files.readString` khác `String.getBytes()`.
4. **Xử lý sai encoding:** quyết định reject, replace hay migrate; tránh mất ký tự im lặng.
5. **Kiểm soát byte count:** không nhầm UTF-16 length với UTF-8 bytes.
6. **Phân biệt Locale:** định dạng số/ngày/UI theo locale; encode file/API theo UTF-8.
7. **Kiểm tra BOM/newline:** giao thức có chấp nhận BOM, dùng LF/CRLF hay encoding cụ thể không?
8. **Kiểm thử round-trip:** mã hóa, giải mã và so nội dung Unicode với tiếng Việt, dấu kết hợp, emoji và byte lỗi.
9. **Thử JDK/runtime khác:** nhất là nơi code cũ phụ thuộc default charset của Java 17.
10. **Giữ config rõ:** dùng `StandardCharsets.UTF_8` trong code hoặc mapping charset có whitelist khi cần hỗ trợ legacy.

## 18. Tài liệu chính thức

- [Java SE 21 — Charset](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/Charset.html): `defaultCharset`, `forName`, encode/decode, charset support.
- [Java SE 21 — StandardCharsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html): sáu hằng số chuẩn.
- [Java SE 21 — CharsetDecoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html): malformed input, REPORT/REPLACE/IGNORE.
- [Java SE 21 — CharsetEncoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetEncoder.html): unmappable characters và trạng thái encoder.
- [Java SE 21 — Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): `readString`, `writeString`, `newBufferedReader` và các overload charset.
- [Java SE 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): `getBytes(Charset)` và constructor từ bytes.
- [Java SE 21 — Properties](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Properties.html): khác biệt `load(InputStream)` và `load(Reader)`.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi default charset bắt đầu Java 18.

## 19. Ghi nhớ

**`Charset` định nghĩa cách encode/decode giữa Unicode và byte; `StandardCharsets.UTF_8` là hằng số Java được bảo đảm có sẵn và nên được dùng tường minh khi contract yêu cầu UTF-8.** Dữ liệu trong Java `String` dùng hệ chỉ số UTF-16, vì thế **độ dài String không phải độ dài byte UTF-8**.

Không phải overload thiếu Charset nào cũng có cùng mặc định: `String.getBytes()`/`InputStreamReader(stream)` và một số I/O legacy phụ thuộc default charset, còn `Files.readString(path)`/`writeString(path,text)` đã quy định UTF-8. Java 18+ dùng UTF-8 mặc định theo JEP 400 cho nhiều API, nhưng không thay đổi những hợp đồng legacy đặc thù như `Properties.load(InputStream)`. Hãy chọn charset theo **hợp đồng dữ liệu**, dùng decoder strict khi không được phép mất ký tự, kiểm soát BOM, newline và streaming, đồng thời phân biệt rõ **charset với locale, Unicode normalization và định dạng JSON/CSV**.