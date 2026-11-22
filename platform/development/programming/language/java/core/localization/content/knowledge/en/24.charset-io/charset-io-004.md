# Charset mặc định và thay đổi từ JDK 18 trong Java

## 1. Một chương trình Java, hai máy, hai kết quả đọc tiếng Việt?

Giả sử một tệp văn bản chứa `Tiếng Việt` và được lưu bằng **UTF-8**. Một chương trình Java đọc tệp bằng:

```java
try (Reader reader = new FileReader("message.txt")) {
    // Đọc dữ liệu văn bản...
}
```

Nếu chương trình chạy trên JDK 17 hoặc cũ hơn, kết quả **có thể** phụ thuộc vào hệ điều hành, thiết lập người dùng và charset mặc định của JVM. Chẳng hạn một máy dùng UTF-8 đọc đúng, nhưng một hệ thống có mã trang `windows-1252` hoặc `windows-1258` có thể giải mã các byte UTF-8 thành ký tự sai, tạo hiện tượng thường gọi là **mojibake** (chữ bị lỗi mã hóa).

**Từ JDK 18**, JEP 400 *UTF-8 by Default* thay đổi giá trị mặc định của `Charset.defaultCharset()` thành **UTF-8** trên các nền tảng, trừ khi được yêu cầu chế độ tương thích. Nhờ vậy, nhiều constructor/phương thức I/O vốn dựa vào charset mặc định hoạt động đồng nhất hơn.

Tuy nhiên, kết luận “Java 18+ dùng UTF-8 cho **mọi** hoạt động I/O” là **sai**. Vẫn có những API có charset cố định, có tham số charset rõ ràng, xử lý theo console/terminal, hoặc theo quy định riêng của giao thức.

Bài học này trình bày:

1. Charset là gì, khác `String` và byte ra sao.
2. Trước JDK 18, charset mặc định được xác định như thế nào.
3. JEP 400 thay đổi điều gì và những ngoại lệ.
4. Các API cần truyền `StandardCharsets.UTF_8`.
5. Cách kiểm tra `file.encoding`, `native.encoding` và chế độ `COMPAT`.
6. Ví dụ Java 17+ kiểm chứng lỗi giải mã, cùng checklist nâng cấp.

## 2. Charset làm nhiệm vụ gì?

Java `String` biểu diễn văn bản Unicode. Khi đọc/ghi tệp, socket hoặc luồng byte, chương trình cần chuyển đổi **giữa byte và ký tự**:

- **Encoding:** `String`/ký tự → byte theo một `Charset`.
- **Decoding:** byte → ký tự/`String` theo một `Charset`.

Ví dụ, chữ `é` (`U+00E9`) có thể được mã hóa trong UTF-8 bằng hai byte `C3 A9`, còn trong ISO-8859-1 chỉ bằng một byte `E9`. Nếu các byte UTF-8 `C3 A9` bị giải mã theo ISO-8859-1, ta nhận hai code point `U+00C3` và `U+00A9`, thường nhìn như `Ã©`.

Đó không phải sự khác biệt về `Locale`, mà là **sự không khớp encoding/decoding**. `Locale.forLanguageTag("vi-VN")` không tự cho biết luồng byte dùng UTF-8 hay một charset khác.

| Thành phần | Công dụng | Ví dụ |
| --- | --- | --- |
| `String` | Văn bản Unicode trong Java | `"Tiếng Việt"` |
| `Charset` | Quy tắc chuyển byte ↔ ký tự | `UTF-8`, `ISO-8859-1`, `windows-1258` |
| `Charset.defaultCharset()` | Charset mặc định của JVM cho những API có sử dụng mặc định | Thường UTF-8 trên JDK 18+ |
| `StandardCharsets.UTF_8` | Hằng charset UTF-8 tường minh, luôn có trong Java SE | `text.getBytes(StandardCharsets.UTF_8)` |
| `Locale` | Quy ước ngôn ngữ/vùng trong trình bày và xử lý ngôn ngữ | `Locale.US`, `vi-VN` |

Một `String` có thể đúng trong bộ nhớ nhưng **sai ngay khi ghi ra byte bằng charset không phù hợp**. Ngược lại, tệp UTF-8 có byte chính xác nhưng có thể được **đọc sai** nếu decoder dùng charset khác. Hai đầu đọc/ghi cần cùng một hợp đồng charset, trừ khi có một bước chuyển mã rõ ràng.

## 3. Trước JDK 18: default charset phụ thuộc môi trường

Ở JDK 17 và các phiên bản cũ hơn, `Charset.defaultCharset()` được xác định khi JVM khởi động, thường từ hệ điều hành và cấu hình ngôn ngữ/encoding của máy.

| Hệ thống/thiết lập trước JDK 18 | Charset mặc định có thể gặp |
| --- | --- |
| Linux/macOS có locale UTF-8 | `UTF-8` |
| Một số cấu hình Windows Tây Âu | `windows-1252` hoặc tên alias tương ứng |
| Một số cấu hình Windows tiếng Nhật | `windows-31j` hoặc charset liên quan |
| Windows với cài đặt ngôn ngữ khác | Mã trang tương ứng; không được đoán chỉ từ tên quốc gia |
| POSIX/C locale trên một số môi trường | Có thể khác UTF-8 |

Đây là những **ví dụ**, không phải bảng cố định để suy ra encoding từ hệ điều hành. Cùng một OS có thể dùng charset mặc định khác nhau do thiết lập của người dùng và môi trường chạy.

Cách kiểm tra trong Java:

```java
import java.nio.charset.Charset;

System.out.println(Charset.defaultCharset().name());
```

Đây là snippet. Nếu JVM đã có charset mặc định khác UTF-8, `new InputStreamReader(stream)` có thể dùng charset ấy để giải mã. Khi một app chuyển từ laptop Linux sang Windows hoặc từ Windows cũ sang image container mới, cùng bộ byte có thể dẫn đến chuỗi khác nhau.

**Điều đáng chú ý:** nhiều tệp mã hóa theo một hệ thống cũ không chứa metadata chỉ rõ charset. Nếu một file lịch sử thực sự lưu trong `windows-1258`, việc đọc nó như UTF-8 sẽ không tự biến nó thành văn bản đúng. Việc chuyển default charset chỉ thay **quy tắc giả định khi thiếu charset**, không tự chuyển mã hàng loạt tệp sẵn có.

## 4. JEP 400: UTF-8 by Default kể từ JDK 18

JEP 400 được đưa vào **JDK 18**. Thay đổi chính là: những Java SE API **dựa trên default charset** sẽ mặc định dùng UTF-8, độc lập hơn với OS, locale và thiết lập tài khoản.

```java
Charset current = Charset.defaultCharset();
```

Trên một JVM JDK 18+ khởi động ở chế độ mặc định bình thường, `current` là `StandardCharsets.UTF_8`. Không cần yêu cầu `-Dfile.encoding=UTF-8` để có hành vi mặc định mới.

### Bảng khác nhau theo thế hệ JDK

| Hạng mục | JDK 17 trở về trước | JDK 18 trở lên, mặc định |
| --- | --- | --- |
| `Charset.defaultCharset()` | Thường theo môi trường/mã trang hệ thống | `UTF-8` |
| `new FileReader(file)` không truyền charset | Theo default charset | UTF-8 |
| `new FileWriter(file)` không truyền charset | Theo default charset | UTF-8 |
| `new InputStreamReader(stream)` | Theo default charset | UTF-8 |
| `new OutputStreamWriter(stream)` | Theo default charset | UTF-8 |
| `new String(bytes)` | Theo default charset | UTF-8 |
| `String.getBytes()` | Theo default charset | UTF-8 |
| `Files.newBufferedReader(path)` không truyền charset | Đã dùng UTF-8 | Vẫn dùng UTF-8 |
| `Files.readString(path)` không truyền charset (Java 11+) | Đã dùng UTF-8 | Vẫn dùng UTF-8 |

Các dòng này mô tả hành vi **không chỉ định charset** của API có liên quan. Chúng không làm thay đổi lời gọi đã truyền `StandardCharsets.ISO_8859_1` hoặc `Charset.forName("windows-1258")`: charset **tường minh luôn mang ý nghĩa riêng**.

Thay đổi ở JDK 18 giải quyết sự thiếu nhất quán lịch sử, nhưng cũng có nguy cơ **tương thích ngược**: code cũ viết/đọc các file dữ liệu theo mã trang nền tảng mà không chỉ định charset có thể đọc sai khi chạy trên JDK mới.

### Thay đổi “mặc định” không phải tự chuyển dữ liệu

Ví dụ:

1. Trên máy cũ, `new FileWriter(...)` ghi nội dung bằng Windows codepage.
2. Một tệp `legacy.txt` được tạo ra, chứa byte theo codepage đó.
3. Chuyển chương trình sang JDK 18+, `new FileReader(...)` mặc định giải mã các byte theo UTF-8.
4. Các byte cũ không nhất thiết hợp lệ theo UTF-8, dẫn đến ký tự thay thế, lỗi giải mã hoặc văn bản sai tùy API.

Lúc này sửa cấu hình `Locale` không giải quyết nguyên nhân. Cần xác định charset nguồn **thực tế**, đọc bằng charset ấy, rồi nếu muốn thì ghi lại tệp theo UTF-8 có chủ đích.

## 5. Các API chịu ảnh hưởng và API không chịu ảnh hưởng

### 5.1. API sử dụng default charset khi bỏ qua tham số

Những lời gọi sau có **phụ thuộc default charset**:

```java
byte[] bytes = text.getBytes();
String decoded = new String(bytes);

Reader reader = new InputStreamReader(input);
Writer writer = new OutputStreamWriter(output);
```

Các biến `text`, `input`, `output` là dữ liệu đã được khai báo; đoạn này chỉ là **snippet**, không phải một class độc lập. Ngoài ra, các constructor `FileReader`, `FileWriter` không có tham số charset, nhiều constructor `Scanner` hoặc `Formatter` có thể phụ thuộc default charset.

Nếu đưa **charset tường minh**, hành vi trở nên dễ hiểu:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);

Reader reader =
        new InputStreamReader(input, StandardCharsets.UTF_8);
Writer writer =
        new OutputStreamWriter(output, StandardCharsets.UTF_8);
```

Snippet trên cần `import java.nio.charset.StandardCharsets;`, `java.io.Reader;`, `java.io.Writer;`, `java.io.InputStreamReader;` và `java.io.OutputStreamWriter;`. Kể cả khi JDK 18+ mặc định UTF-8, việc **ghi rõ charset** tại điểm giao với file/giao thức giúp code tự mô tả hợp đồng và chạy được trên các phiên bản JDK cũ.

### 5.2. Files.readString và Files.newBufferedReader đã mặc định UTF-8

Không phải mọi API đọc/ghi text đều từng phụ thuộc OS. Từ trước JDK 18:

```java
String text = Files.readString(path);
```

`Files.readString(Path)` (Java 11+) mặc định giải mã theo UTF-8. `Files.newBufferedReader(Path)` (Java 8+) cũng mặc định dùng UTF-8. `Files.writeString(Path, text)` (Java 11+) mặc định dùng UTF-8; `Files.newBufferedWriter(Path)` cũng dùng UTF-8 nếu không truyền charset.

Do đó phát biểu “từ JDK 18, mọi thao tác Files mới bắt đầu dùng UTF-8” là sai. JEP 400 chủ yếu xử lý các API dựa trên **default charset có tính môi trường**. Một số phương thức `Files` đã chọn UTF-8 trước đó.

### 5.3. System.out và System.err là trường hợp đặc biệt

`System.out` và `System.err` là các luồng có liên hệ với console/terminal, và **không nhất thiết** dùng cùng charset với `Charset.defaultCharset()`. Java giữ hành vi phù hợp với môi trường stdout/stderr, tránh biến chữ in ra terminal thành mojibake chỉ vì `file.encoding` đổi sang UTF-8.

Ở JDK hiện đại, charset dùng cho console có thể được xác định qua `Console.charset()` khi có console, hoặc những cấu hình như `stdout.encoding`/`stderr.encoding` tùy runtime và platform. Vì thế:

```java
System.out.println(Charset.defaultCharset());
```

chỉ cho biết **default charset**, không chứng minh terminal, IDE console hoặc một process đang nhận stdout giải mã theo UTF-8.

Nếu ứng dụng ghi vào **một luồng byte do mình sở hữu**, hãy dùng `OutputStreamWriter(stream, charset)` hoặc `PrintStream(..., charset)` khi cần đảm bảo encoding. Khi ghi ra terminal, nên xác định charset thực tế của terminal/console và hạn chế thay đổi global output streams chỉ để sửa một lỗi hiển thị.

### 5.4. Những API có charset cố định hoặc đặc thù

Một số API không đi theo `Charset.defaultCharset()`:

| API/hành vi | Quy tắc |
| --- | --- |
| `Properties.load(InputStream)` | Theo đặc tả `.properties` truyền thống, byte được hiểu theo ISO-8859-1, có `\\uXXXX` escapes |
| `Properties.load(Reader)` | Dùng các **ký tự đã được Reader giải mã**, không tự chọn UTF-8 |
| `PropertyResourceBundle(InputStream)` | Từ Java 9: UTF-8-first với cơ chế fallback ISO-8859-1 trừ cấu hình riêng |
| `DataInputStream.readUTF()` / `DataOutputStream.writeUTF()` | Dùng **modified UTF-8** theo hợp đồng Java, không phải default charset hay UTF-8 chuẩn trong mọi trường hợp |
| `Files.readString(Path)` | UTF-8 mặc định từ khi API có mặt |
| `Files.newBufferedReader(Path)` | UTF-8 mặc định |
| `StandardCharsets.UTF_8` được truyền tường minh | Luôn là UTF-8 |
| API của bên thứ ba hoặc giao thức | Theo hợp đồng riêng, không suy đoán từ JEP 400 |

**Không dùng `-Dfile.encoding=UTF-8` để sửa một `Properties.load(InputStream)` đang đọc sai tiếng Việt.** API này có quy tắc ISO-8859-1 riêng. Nếu file properties thật sự ở UTF-8, tạo một `InputStreamReader(..., StandardCharsets.UTF_8)` rồi gọi `Properties.load(Reader)`, hoặc xử lý theo chuẩn resource bundle phù hợp.

Không nhầm **source file encoding** của `javac` với **I/O runtime**. Dùng `javac -encoding UTF-8` khi nguồn `.java` được lưu UTF-8, nhất là trên các JDK/CI khác nhau.

## 6. Kiểm chứng Java 17+: byte UTF-8 không tự nói lên charset

Tạo tệp **`DefaultCharsetDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.stream.Collectors;

public class DefaultCharsetDemo {
    private static String codePoints(String value) {
        return value.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) throws Exception {
        String source = "Ti\u1EBFng Vi\u1EC7t";
        byte[] data = source.getBytes(StandardCharsets.UTF_8);

        String correct = new String(data, StandardCharsets.UTF_8);
        String wrong = new String(data, StandardCharsets.ISO_8859_1);
        String implicit = new String(data);

        System.out.println("UTF-8 byte count: " + data.length);
        System.out.println("Explicit UTF-8 equals: "
                + source.equals(correct));
        System.out.println("Explicit Latin-1 equals: "
                + source.equals(wrong));
        System.out.println("Latin-1 decoded code points: "
                + codePoints(wrong));

        System.out.println("Default charset: "
                + Charset.defaultCharset().name());
        System.out.println("Default decode equals: "
                + source.equals(implicit));

        try (InputStreamReader reader = new InputStreamReader(
                new ByteArrayInputStream(data),
                StandardCharsets.UTF_8)) {
            char[] chars = new char[32];
            int count = reader.read(chars);
            System.out.println("Explicit reader equals: "
                    + source.equals(new String(chars, 0, count)));
        }
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 DefaultCharsetDemo.java
java DefaultCharsetDemo
```

**Phần stdout bất biến theo API** (các dòng được nêu dưới đây luôn giống nhau trong ví dụ):

```text
UTF-8 byte count: 14
Explicit UTF-8 equals: true
Explicit Latin-1 equals: false
Latin-1 decoded code points: U+0054 U+0069 U+00E1 U+00BA U+00BF U+006E U+0067 U+0020 U+0056 U+0069 U+00E1 U+00BB U+0087 U+0074
Explicit reader equals: true
```

Ba dòng khác trong output có thể khác theo JDK/môi trường. Trên **JDK 18+ khởi động mặc định**, chúng thường là:

```text
Default charset: UTF-8
Default decode equals: true
```

Trong thực tế hai dòng này xuất hiện **trước** dòng `Explicit reader equals`; phần “bất biến” và “phụ thuộc môi trường” được tách riêng để không đưa ra kỳ vọng sai trên JDK 17 hoặc khi bật `COMPAT`.

Cần phân biệt:

- `source.getBytes(UTF_8)` **mã hóa** chính xác theo UTF-8.
- `new String(data, UTF_8)` **giải mã** chính xác cùng charset.
- `new String(data, ISO_8859_1)` tạo chuỗi **khác**, dù cùng một mảng byte. Nó không tự phát hiện charset nguồn.
- `new String(data)` dùng default charset, nên khả năng đúng hay sai phụ thuộc cấu hình JVM.
- `InputStreamReader(..., UTF_8)` cho hành vi rõ ràng độc lập default.

Mẫu đầu ra sử dụng mã `U+XXXX` để tránh dựa vào font và charset của console khi hiển thị dấu tiếng Việt.

## 7. Demo 2: API phụ thuộc default và API đã cố định UTF-8

Tạo file **`FilesCharsetDemo.java`** (Java 17+). Chương trình này tự tạo file tạm UTF-8 và dọn dẹp:

```java
import java.io.FileReader;
import java.io.Reader;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FilesCharsetDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile(
                "charset-demo-", ".txt");
        String source = "Ti\u1EBFng Vi\u1EC7t";

        try {
            Files.writeString(file, source, StandardCharsets.UTF_8);

            String nioRead = Files.readString(file);
            System.out.println("Files.readString equals: "
                    + source.equals(nioRead));

            StringBuilder fromDefaultReader = new StringBuilder();
            try (Reader reader = new FileReader(file.toFile())) {
                char[] buffer = new char[64];
                int n;
                while ((n = reader.read(buffer)) != -1) {
                    fromDefaultReader.append(buffer, 0, n);
                }
            }

            System.out.println("Default reader equals: "
                    + source.contentEquals(fromDefaultReader));
            System.out.println("Default is UTF-8: "
                    + StandardCharsets.UTF_8
                            .equals(Charset.defaultCharset()));

            StringBuilder fromExplicitReader = new StringBuilder();
            try (Reader reader = new FileReader(
                    file.toFile(), StandardCharsets.UTF_8)) {
                char[] buffer = new char[64];
                int n;
                while ((n = reader.read(buffer)) != -1) {
                    fromExplicitReader.append(buffer, 0, n);
                }
            }
            System.out.println("Explicit reader equals: "
                    + source.contentEquals(fromExplicitReader));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 FilesCharsetDemo.java
java FilesCharsetDemo
```

**Stdout trên JDK 18+ với cấu hình mặc định UTF-8:**

```text
Files.readString equals: true
Default reader equals: true
Default is UTF-8: true
Explicit reader equals: true
```

Nếu chạy JDK 17 với charset mặc định **khác UTF-8**, các dòng `Files.readString` và `Explicit reader` vẫn `true`, nhưng dòng `Default reader equals` **có thể** là `false`, và `Default is UTF-8` là `false`. Tương tự, JDK 18+ với `-Dfile.encoding=COMPAT` có thể nhận cùng tình huống nếu native encoding khác UTF-8.

Bài học: **`Files.readString(Path)` không có charset argument không giống `new FileReader(File)`** về lịch sử default charset. Khi muốn code rõ ràng và ổn định qua môi trường, truyền charset tường minh cho `FileReader` hoặc sử dụng API `Files` với hợp đồng UTF-8.

Lưu ý quan trọng: `Files.createTempFile` chỉ tạo đường dẫn tạm và `Files.deleteIfExists` trong `finally` giúp dọn dẹp. Ví dụ không cần file tĩnh trong repo. Nếu có nhiều process chạy test, tên file tạm duy nhất tránh xung đột. Trong hệ thống thực tế, cần xử lý đầy đủ ngoại lệ I/O thay vì chỉ khai báo `throws Exception` như ví dụ học tập.

## 8. Tham số file.encoding và chế độ COMPAT

Trong **JDK 18 trở lên**, `file.encoding` được đưa vào mô tả implementation để cấu hình default charset từ lúc JVM khởi động. Hai giá trị được hỗ trợ theo tài liệu Oracle:

```text
-Dfile.encoding=UTF-8
-Dfile.encoding=COMPAT
```

- **`UTF-8`:** mặc định dùng UTF-8.
- **`COMPAT`:** yêu cầu cách chọn default charset tương thích trước JDK 18, tức theo môi trường/platform; thường phản ánh charset từ `native.encoding`.

Các giá trị khác cho `file.encoding` **không được hỗ trợ theo hợp đồng JDK hiện đại**. Không dựa vào `-Dfile.encoding=windows-1252` hoặc tự chọn arbitrary charset để thiết kế giải pháp lâu dài.

Ví dụ khởi chạy:

```bash
java -Dfile.encoding=UTF-8 DefaultCharsetDemo
java -Dfile.encoding=COMPAT DefaultCharsetDemo
```

Nếu máy có native encoding UTF-8, **hai lệnh có thể cho cùng kết quả**. Để kiểm thử thật sự tình huống khác UTF-8, cần một môi trường mà legacy/native charset khác UTF-8, chẳng hạn một máy Windows có mã trang cũ. Không nên tự suy rằng `COMPAT` chắc chắn làm output khác.

### Các thuộc tính cần biết

| Thuộc tính / API | Ý nghĩa và lưu ý |
| --- | --- |
| `Charset.defaultCharset()` | API chính để hỏi charset mặc định hiện tại |
| `System.getProperty("file.encoding")` | Thông tin/cấu hình gắn với default charset; xem khi chẩn đoán |
| `System.getProperty("native.encoding")` | Encoding nền tảng được JVM phát hiện (JDK 17+); có thể khác UTF-8 mặc định của JDK 18+ |
| `stdout.encoding` / `stderr.encoding` | Có thể điều khiển charset riêng của standard output/error ở các JDK hỗ trợ |
| `java -XshowSettings:properties -version` | Cho biết các thuộc tính ở startup, hữu ích khi kiểm tra deployment |

**Không sửa `System.setProperty("file.encoding", "...")` giữa lúc chương trình chạy rồi kỳ vọng toàn bộ các reader/writer đã tạo đổi charset.** Default charset được xác lập từ lúc khởi động JVM; các đối tượng I/O đã được tạo có charset riêng. Cách sửa property runtime không phải API đáng tin để đổi default charset đang sử dụng.

`native.encoding` cũng không nên dùng như “mã trang cần áp dụng cho toàn bộ file cũ”; file thực tế có thể do một ứng dụng trên máy khác tạo. Dùng charset của **dữ liệu nguồn**, không chỉ charset hiện tại của máy đọc.

## 9. Phân biệt đường nhập/xuất console

Một lỗi thường gặp sau khi đổi Java version:

- Ghi file UTF-8 đúng nhưng in ra terminal lại thấy ký tự lỗi.
- `Charset.defaultCharset()` trả `UTF-8`, nhưng `System.out` dùng charset console khác.
- JVM đọc file tường minh UTF-8 đúng, nhưng một công cụ tiếp nhận stdout hoặc log shipper giải mã theo charset không khớp.

Không nên vội sửa file encoding nếu nội dung **trong file** đã đúng. Kiểm tra từng ranh giới byte:

```text
String Java
  -> encoder của Writer/PrintStream
  -> byte trong file/pipe/terminal
  -> decoder của chương trình/terminal nhận
  -> ký tự được hiển thị
```

Nếu chương trình đọc `System.in` bằng `new InputStreamReader(System.in)`, decoder đó dùng default charset, nhưng **input từ terminal** có thể đến trong mã hóa khác, tạo rủi ro mismatch. Khi nguồn input là console, nên tham khảo API `System.console()` và khả năng `Console.charset()` (khi có console); khi nguồn input là file/pipe có hợp đồng, chỉ định charset rõ.

`System.console()` có thể trả `null` trong IDE, CI, pipe hoặc môi trường không gắn console tương tác. Không được coi nó luôn tồn tại.

### Không nhầm encoding với font

Ngay cả khi byte và decoder đều đúng UTF-8, terminal có thể thiếu glyph Unicode hoặc font phù hợp để hiện ký tự. Đây là lỗi **hiển thị**, khác với lỗi **giải mã**. Hãy kiểm tra code point/byte hoặc ghi ra file UTF-8 để phân biệt.

## 10. Properties, resource bundles và thay đổi default charset

Tệp `.properties` thường xuất hiện trong ứng dụng bản địa hóa. Nhưng nó có **hợp đồng charset đặc thù**:

```java
Properties properties = new Properties();

try (InputStream input = Files.newInputStream(path)) {
    properties.load(input);
}
```

Đây là snippet; `Properties.load(InputStream)` đọc các byte theo **ISO-8859-1** và xử lý Unicode escape `\\uXXXX`. Nó **không đổi sang UTF-8 chỉ vì đang dùng JDK 18+**.

Để đọc một file properties UTF-8 bằng `Properties`:

```java
Properties properties = new Properties();

try (Reader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    properties.load(reader);
}
```

Đây cũng là snippet, sử dụng `java.util.Properties`, `java.io.Reader`, `java.nio.file.Files` và `java.nio.charset.StandardCharsets`. `Reader` đã giải mã UTF-8 nên `Properties` nhận các ký tự Unicode tương ứng.

**`PropertyResourceBundle(InputStream)` là trường hợp khác:** từ Java 9, nó thử đọc UTF-8 và có cơ chế fallback về ISO-8859-1 theo đặc tả (có thuộc tính `java.util.PropertyResourceBundle.encoding`). Đừng gộp hành vi `PropertyResourceBundle` với `Properties.load(InputStream)` hoặc với JEP 400.

Nếu ứng dụng đang lỗi localization sau nâng cấp, kiểm tra API nào thực sự đọc tệp, tệp được lưu bằng charset nào và Java version thay đổi quy tắc nào. Không đặt tất cả nguyên nhân vào default charset.

## 11. Chuyển đổi một file legacy sang UTF-8 một cách có kiểm soát

Một chiến lược an toàn là:

1. Xác định encoding gốc **bằng tài liệu, metadata đáng tin hoặc kiểm tra nguồn dữ liệu thực tế**; không tự đoán qua tên file.
2. Đọc bằng charset gốc được xác nhận.
3. Xác nhận nội dung đã giải mã đúng (kiểm thử từ khóa có dấu, Unicode code point, sample records).
4. Ghi tệp mới bằng `UTF-8`.
5. Kiểm tra lại bằng UTF-8 reader, đối chiếu số bản ghi và nội dung.
6. Chỉ thay thế dữ liệu production sau khi có bản sao lưu và kế hoạch rollback.

Snippet minh họa khi **biết chắc tệp gốc là windows-1252**:

```java
Charset legacy = Charset.forName("windows-1252");

String content = Files.readString(oldFile, legacy);
Files.writeString(newFile, content, StandardCharsets.UTF_8);
```

Đây không phải chương trình độc lập; `oldFile` và `newFile` là `Path` đã xác định. Nếu tệp là tiếng Việt sử dụng `windows-1258` hoặc một charset khác, phải dùng đúng charset **đã được xác nhận**. Không lấy `windows-1252` làm mặc định cho mọi tệp legacy.

### Cẩn thận với decoder thay thế ký tự lỗi

Một số đường giải mã thay byte không hợp lệ bằng ký tự thay thế `U+FFFD` thay vì ném lỗi. Nếu cần kiểm tra toàn vẹn dữ liệu, dùng `CharsetDecoder` với `CodingErrorAction.REPORT` và xử lý `MalformedInputException` hoặc `UnmappableCharacterException` phù hợp.

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
```

Đây là snippet. Với tệp lớn, có thể truyền decoder vào `InputStreamReader` hoặc dùng cách đọc streaming để tránh nạp toàn bộ file vào bộ nhớ. **Không coi giải mã không báo lỗi là chứng minh charset chính xác**, vì nhiều dãy byte có thể hợp lệ ở nhiều charset nhưng tạo nội dung khác nhau.

## 12. Checklist nâng cấp từ JDK 17 hoặc cũ hơn lên JDK 18+

### Kiểm kê

Tìm trong code những chỗ I/O text **không truyền charset**:

- `new FileReader(...)`, `new FileWriter(...)`.
- `new InputStreamReader(...)`, `new OutputStreamWriter(...)`.
- `new String(byte[])`, `String.getBytes()`.
- `new Scanner(file/inputStream)` và một số constructor `Formatter`.
- Quy trình chạy `javac` mà không cố định `-encoding`.
- Giao tiếp giữa các process và pipeline stdout/stderr khi mã hóa không được thống nhất.

Đồng thời **phân loại** các API đã có charset tường minh, API mặc định UTF-8 độc lập môi trường như nhiều API `Files` và API giao thức đặc thù như `Properties.load(InputStream)`. Không thay đổi những chỗ đang có hợp đồng đúng chỉ vì muốn “thống nhất mọi thứ UTF-8”.

### Kiểm thử tương thích

1. Ghim phiên bản JDK, ghi lại `Charset.defaultCharset()` và `native.encoding` ở môi trường thử.
2. Với **JDK 17** đang chạy ở charset khác UTF-8, thử `-Dfile.encoding=UTF-8` ở startup để phát hiện phụ thuộc ngầm.
3. Với **JDK 18+**, thử startup thông thường và `-Dfile.encoding=COMPAT` để tái hiện hành vi legacy khi có native charset khác.
4. Kiểm tra file xuất/nhập, CSV, log, config, dữ liệu tiếng Việt, emoji và chữ nhiều byte.
5. Kiểm thử chạy qua IDE, terminal, CI, container và tiến trình con để phát hiện mismatch ở stdout/stdin.
6. Đối chiếu **byte thực** của file hoặc response giao thức, thay vì chỉ nhìn màn hình.
7. Với file legacy, định nghĩa charset nguồn và kế hoạch chuyển mã có kiểm soát.

### Cách sửa bền vững

Nếu file/giao thức **được định nghĩa là UTF-8**, ghi rõ:

```java
String data = Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(path, data, StandardCharsets.UTF_8);
```

Nếu format giao thức bắt buộc một charset **khác UTF-8**, hãy truyền chính charset đó. Ví dụ các chuẩn cũ, đối tác legacy hoặc tệp archive có encoding riêng cần được giữ đúng hợp đồng; đổi mặc định JVM không thay thế việc đọc/ghi đúng charset.

### Bộ test hữu ích

| Loại dữ liệu | Ví dụ | Điều kiểm tra |
| --- | --- | --- |
| ASCII | `hello` | Hầu hết charset tương thích ASCII vẫn cho kết quả giống nhau; chưa đủ kiểm thử |
| Tiếng Việt có dấu | `Tiếng Việt` | Không bị mojibake hoặc ký tự thay thế |
| Chữ Latin ngoài ASCII | `é`, `ñ` | Mã byte đúng, reader giải mã đúng |
| CJK | Chữ Nhật/Trung/Hàn | Không phụ thuộc codepage cũ |
| Emoji ngoài BMP | `U+1F600` | UTF-8 4 byte, surrogate pair khi thành String |
| Tệp legacy | Byte theo charset nguồn được xác nhận | Không đọc sai bằng UTF-8 |
| Stdout/stderr | Qua IDE, terminal, redirect, CI | Charset của encoder/decoder tương thích |
| Chương trình chuyển mã | Tệp nguồn → UTF-8 | Readback đúng và không mất dữ liệu |

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “Java 18+ mọi I/O đều UTF-8” | Chỉ các API phụ thuộc default bị ảnh hưởng; nhiều ngoại lệ | Xem hợp đồng charset của từng API |
| “Locale vi-VN nghĩa là UTF-8” | Locale và charset là hai khái niệm khác nhau | Truyền Charset tường minh |
| “Đổi file.encoding runtime là đủ” | Default được chọn lúc startup; reader/writer có cấu hình riêng | Khởi động với cấu hình thích hợp, sửa code |
| “-Dfile.encoding=windows-1258 luôn được hỗ trợ” | JDK 18+ chỉ hỗ trợ UTF-8/COMPAT theo đặc tả | Dùng Charset tường minh tại I/O |
| “COMPAT luôn trả charset khác UTF-8” | Máy có native encoding UTF-8 thì giống mặc định mới | Kiểm tra `native.encoding` và `defaultCharset()` |
| “Files.readString chỉ từ JDK 18 mới là UTF-8” | Phương thức này dùng UTF-8 từ Java 11 | Phân biệt API và lịch sử của chúng |
| “System.out chắc chắn in UTF-8” | Console/stdout có charset riêng | Kiểm tra môi trường console và bên nhận |
| “Properties.load(InputStream) dùng JDK default” | Nó có hợp đồng ISO-8859-1 | Dùng `load(Reader UTF-8)` nếu file UTF-8 |
| “UTF-8 byte tự động được Java nhận ra” | Các API String/Reader không tự auto-detect charset chung | Biết hoặc quy định charset nguồn |
| “Tệp đã lỗi chỉ cần encode UTF-8 lần nữa” | Nếu đã giải mã sai, có thể chỉ encode lại mojibake | Quay về byte nguồn và giải mã đúng |
| “Chỉ test ASCII đủ để xác nhận chuyển mã” | ASCII thường không thể hiện khác biệt | Test tiếng Việt và các ký tự ngoài ASCII |
| “file.encoding và native.encoding giống nhau” | JDK 18+ có thể mặc định UTF-8 dù native khác | Đọc từng thông tin đúng mục đích |
| “Charset.defaultCharset quyết định cách trình bày dấu tiếng Việt” | Còn font/terminal, Unicode và thuật toán format | Phân biệt encoding, decoding và rendering |

## 14. Câu hỏi ôn tập

**Câu 1.** Từ phiên bản nào Java sử dụng UTF-8 làm default charset cho các API Java SE dựa trên default charset?

**Đáp án:** Từ **JDK 18** theo JEP 400; trước đó mặc định có thể phụ thuộc hệ điều hành/người dùng. Chế độ `COMPAT` cho phép tái hiện lựa chọn kiểu cũ trong JDK 18+.

**Câu 2.** `Charset.defaultCharset()` trả UTF-8 có chứng minh `System.out` cũng đang encode UTF-8?

**Đáp án:** Không. Standard streams có cơ chế charset riêng, phù hợp với console và môi trường chạy.

**Câu 3.** Tại sao `new String(utf8Bytes)` có thể trả chuỗi sai trên JDK 17?

**Đáp án:** Constructor không có tham số dùng default charset; nếu default khác UTF-8, byte UTF-8 bị giải mã sai. Dùng `new String(utf8Bytes, StandardCharsets.UTF_8)`.

**Câu 4.** `Files.readString(path)` dùng charset gì nếu không truyền charset trên Java 17?

**Đáp án:** UTF-8, vì đây là hợp đồng của `Files.readString(Path)` ngay từ Java 11; không phải hành vi mới của JEP 400.

**Câu 5.** Tại sao `Properties.load(InputStream)` vẫn đọc khác với UTF-8 dù chạy JDK 21?

**Đáp án:** API đó quy định ISO-8859-1 khi đọc byte và hỗ trợ escape Unicode, độc lập default charset. Có thể dùng `Properties.load(Reader)` với reader UTF-8 được cung cấp rõ ràng.

**Câu 6.** Nếu tệp cũ là `windows-1258`, đưa lên JDK 21 rồi đọc bằng `FileReader(path)` có luôn đúng không?

**Đáp án:** Không. JDK 21 mặc định UTF-8, trong khi tệp cũ vẫn ở charset khác. Cần đọc bằng charset nguồn được xác nhận; nếu phù hợp, chuyển đổi sang UTF-8 có kiểm thử.

**Câu 7.** `-Dfile.encoding=COMPAT` có phải chiến lược bền vững cho mọi giao thức?

**Đáp án:** Không. Nó hỗ trợ chuyển tiếp/chẩn đoán cho ứng dụng legacy. Giải pháp lâu dài là quy định charset của dữ liệu và truyền charset tường minh tại ranh giới I/O.

**Câu 8.** Vì sao viết `System.setProperty("file.encoding","UTF-8")` sau khi app đã khởi động không đủ?

**Đáp án:** Default charset được xác định trong giai đoạn startup và các reader/writer đã khởi tạo có cấu hình riêng. Đổi property runtime không phải cách đáng tin để thay đổi hành vi đã được thiết lập.

## 15. Tổng kết

- **JDK 17 trở về trước:** default charset thường phụ thuộc máy, locale và native codepage.
- **JDK 18 trở lên:** JEP 400 đưa **UTF-8** thành default charset cho các Java SE API phụ thuộc `Charset.defaultCharset()`.
- **Không phải mọi API đổi theo JEP 400:** `System.out`/`System.err`, `Properties.load(InputStream)`, API `Files` vốn đã mặc định UTF-8, các giao thức và charset tường minh có hợp đồng riêng.
- **`-Dfile.encoding=UTF-8` hoặc `COMPAT`** được hỗ trợ tại startup JDK 18+; các giá trị khác không thuộc hợp đồng hỗ trợ.
- **Luôn xác định charset thực tế của byte nguồn**. Với dữ liệu mới/giao thức quy định UTF-8, nên truyền `StandardCharsets.UTF_8` tường minh để code tự mô tả và an toàn qua các phiên bản Java.
- Nâng cấp JVM không tự chuyển mã dữ liệu cũ. Kiểm thử tệp, network, console, log và cả ký tự ngoài ASCII trước khi triển khai.

**Tài liệu tham khảo chính thức:**

- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400)
- [Java SE 21 — Supported Encodings and Default Charset](https://docs.oracle.com/en/java/javase/21/intl/supported-encodings.html)
- [Java SE 21 — InputStreamReader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStreamReader.html)
- [Java SE 21 — Charset](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/Charset.html)
- [Java SE 21 — Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html)
- [Java Team — JEP 400 and the Default Charset](https://inside.java/2021/10/04/the-default-charset-jep400/)
