# Charset mặc định, UTF-8 từ JDK 18 và các ngoại lệ theo API

Khi một chương trình Java chuyển giữa **byte** và **văn bản**, nó phải chọn một `Charset`: quy tắc mã hóa ký tự thành byte (encode) hoặc giải mã byte thành ký tự (decode). Nếu không chỉ rõ charset, *một số* API sử dụng **default charset của JVM**. Từ **JDK 18**, Java áp dụng **UTF-8 làm charset mặc định** theo JEP 400, giúp nhiều API có hành vi thống nhất hơn trên Windows, Linux và macOS. Tuy nhiên, không phải mọi API thiếu tham số charset đều lấy `Charset.defaultCharset()`: nhiều API đã quy định UTF-8, ISO-8859-1, charset thiết bị đầu cuối hoặc charset theo định dạng dữ liệu.

Điều quan trọng trong thực tế là **xác định đúng quy tắc của API đang dùng** và **chỉ định charset rõ ràng ở ranh giới dữ liệu** khi dữ liệu phải tương thích giữa các môi trường hoặc phiên bản Java.

## 1. Charset là gì và default charset dùng để làm gì?

Các đối tượng `String` trong Java biểu diễn chuỗi ký tự Unicode ở mức API; khi đọc/ghi tệp, gửi dữ liệu qua mạng hoặc trao đổi với hệ thống ngoài, chuỗi phải được biểu diễn bằng byte. Một ký tự có thể chiếm số byte khác nhau tùy charset.

Ví dụ ký tự `é`:

| Charset | Các byte theo hệ thập lục phân |
|---|---|
| UTF-8 | `C3 A9` |
| ISO-8859-1 | `E9` |
| US-ASCII | Không biểu diễn trực tiếp được; hành vi thay thế hoặc báo lỗi tùy API/bộ mã hóa |

Nếu ghi bằng UTF-8 nhưng đọc bằng ISO-8859-1, hai byte `C3 A9` có thể bị giải mã thành `Ã©`: đây là hiện tượng **mojibake** (văn bản bị biến dạng do sai mã hóa). Không phải lỗi dấu tiếng Việt trong `String`; đó là lỗi do hai phía diễn giải byte không cùng quy tắc.

`java.nio.charset.Charset.defaultCharset()` trả về đối tượng charset mặc định của JVM. Những API *được định nghĩa là dùng default charset* sẽ sử dụng charset này khi không nhận đối số charset. Vì vậy cần phân biệt:

- **Default charset**: mặc định chung của JVM, đọc bằng `Charset.defaultCharset()`.
- **Charset được truyền tường minh**: ví dụ `StandardCharsets.UTF_8`; không phụ thuộc default charset.
- **Charset cố định theo hợp đồng API**: ví dụ `Files.readString(path)` mặc định UTF-8, bất kể default charset là gì.
- **Charset của môi trường tương tác**: ví dụ đầu vào/đầu ra console, có thể khác `Charset.defaultCharset()`.
- **Charset theo định dạng hoặc giao thức**: ví dụ API nạp `Properties` từ `InputStream` theo ISO-8859-1.

Không được suy ra chỉ từ việc API **không có tham số charset** rằng nó chắc chắn sử dụng default charset.

## 2. Trước và sau JDK 18: thay đổi gì?

JEP 400, có hiệu lực từ **JDK 18**, làm cho UTF-8 trở thành default charset chuẩn của các API Java SE phụ thuộc default charset, trừ khi JVM được cấu hình đổi hành vi theo cơ chế hỗ trợ.

| Phiên bản | Default charset thông thường | Ảnh hưởng |
|---|---|---|
| JDK 17 trở xuống | Phụ thuộc hệ điều hành, locale và cấu hình môi trường tại thời điểm JVM khởi động | Cùng code không truyền charset có thể tạo/đọc các byte khác nhau giữa máy |
| JDK 18 trở lên | **UTF-8 theo mặc định** trên mọi nền tảng | Các API dùng default charset hoạt động nhất quán hơn |
| JDK 18+ với `-Dfile.encoding=COMPAT` | Quay về cách xác định charset gắn với môi trường kiểu JDK 17 | Dùng để thử nghiệm và xử lý tương thích khi nâng cấp |
| JDK 18+ với `-Dfile.encoding=UTF-8` | UTF-8 | Làm rõ ý định cấu hình bằng tham số khởi động |

Ví dụ trên một máy Windows dùng code page cũ, JDK 17 có thể dùng `windows-1252` hoặc `windows-31j` làm default charset, trong khi JDK 18+ theo mặc định dùng UTF-8. Tuy nhiên, **JDK 17 không có nghĩa là luôn không dùng UTF-8**: nhiều môi trường Linux và macOS đã có mặc định UTF-8 từ trước. Kết quả cụ thể phải kiểm tra trên JVM đang chạy.

Tác động của thay đổi nằm ở **các thao tác mã hóa/giải mã phụ thuộc default charset**. JEP 400 không tự chuyển mã những tệp cũ đã ghi, không tự phát hiện charset lịch sử của tệp và không làm thay đổi hợp đồng mã hóa đã quy định riêng của từng API.

### Hai thuộc tính cần phân biệt

- `file.encoding` liên quan đến lựa chọn default charset của JVM. Với JDK 18+, các giá trị được hỗ trợ theo đặc tả để lựa chọn cơ chế này là `UTF-8` và `COMPAT` khi truyền lúc khởi động.
- `native.encoding` mô tả charset có nguồn gốc từ cấu hình môi trường/hệ điều hành, hữu ích để nhận diện chế độ tương thích. Nó **có thể khác** `file.encoding` khi default charset là UTF-8.

Với JDK 18+, khi chạy `-Dfile.encoding=COMPAT`, default charset được suy ra từ `native.encoding` theo cơ chế tương thích; nó có thể vẫn là UTF-8 nếu môi trường dùng UTF-8. Đừng kỳ vọng `COMPAT` chắc chắn trả ra một charset khác UTF-8.

**Không coi `System.setProperty("file.encoding", "...")` sau khi chương trình đã chạy là cách chuyển charset an toàn.** JVM và các thành phần liên quan có thể đã khởi tạo/cached charset. Nếu cần điều chỉnh ở mức JVM, truyền tùy chọn lúc khởi động; nếu cần mã hóa ổn định ở mức dữ liệu, truyền `Charset` trực tiếp vào API.

## 3. Nhận diện charset trên JVM đang chạy

Tạo tệp **`CharsetProbe.java`** lưu ở UTF-8:

~~~java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class CharsetProbe {
    public static void main(String[] args) {
        System.out.println("default = " + Charset.defaultCharset().name());
        System.out.println("file.encoding = " + System.getProperty("file.encoding"));
        System.out.println("native.encoding = " + System.getProperty("native.encoding"));

        String text = "\u00E9"; // Ký tự é
        System.out.println("implicit = " + Arrays.toString(text.getBytes()));
        System.out.println("explicit UTF-8 = "
                + Arrays.toString(text.getBytes(StandardCharsets.UTF_8)));
    }
}
~~~

Biên dịch bằng JDK 17+; tham số `-encoding UTF-8` bảo đảm trình biên dịch diễn giải tệp nguồn UTF-8 theo ý định:

~~~bash
javac -encoding UTF-8 CharsetProbe.java
java CharsetProbe
~~~

Ba dòng đầu và dòng `implicit` **phụ thuộc JVM/môi trường hoặc cờ khởi động**, vì vậy không có một bản stdout duy nhất đúng cho mọi máy. Điều bất biến là:

~~~text
explicit UTF-8 = [-61, -87]
~~~

Dòng này in `byte[]` theo kiểu `byte` có dấu trong Java, nên các byte `C3 A9` được biểu diễn thành `-61, -87`. Đây vẫn là byte UTF-8 hợp lệ của `é`.

Trên JDK 18+, thử độc lập hai chế độ sau:

~~~bash
java -Dfile.encoding=UTF-8 CharsetProbe
java -Dfile.encoding=COMPAT CharsetProbe
~~~

Khi `UTF-8` được sử dụng làm default charset, dòng `implicit` cũng là `[-61, -87]`. Khi `COMPAT` chọn một charset khác, dòng này **có thể thay đổi**, ví dụ một ký tự được mã hóa bằng một byte theo ISO-8859-1 hoặc một encoding tương thích khác. Đừng hard-code kết quả `native.encoding` hay charset Windows trong bài kiểm tra chạy trên nhiều hệ điều hành.

Có thể xem thêm thuộc tính khởi động bằng `java -XshowSettings:properties -version`. Cách đáng tin nhất để biết default charset Java thực sự đang dùng trong code vẫn là `Charset.defaultCharset()`.

## 4. Các API thực sự phụ thuộc default charset

Trong những lời gọi sau, nếu **không truyền charset**, chuyển đổi ký tự ↔ byte sẽ dựa trên default charset của JVM theo hợp đồng API:

| API/ví dụ | Vùng ảnh hưởng |
|---|---|
| `"text".getBytes()` | Mã hóa `String` thành byte |
| `new String(byteArray)` | Giải mã byte thành `String` |
| `new InputStreamReader(inputStream)` | Giải mã byte từ một input stream thành ký tự |
| `new OutputStreamWriter(outputStream)` | Mã hóa ký tự khi ghi ra output stream |
| `new FileReader(file)`, `new FileWriter(file)` (constructor không chỉ charset) | Đọc/ghi ký tự trên tệp |
| Các constructor `Scanner` hoặc `Formatter` dùng default charset với nguồn/đích là byte | Chuyển đổi ký tự ở tầng vào/ra theo đúng overload |

Ví dụ cặp lời gọi phụ thuộc môi trường:

~~~java
// Mảnh mã minh họa: sử dụng charset mặc định, có thể khác giữa JDK 17 và 18+.
byte[] bytes = "Tiếng Việt".getBytes();
String decoded = new String(bytes);
~~~

Nếu cả hai thao tác xảy ra trong **cùng JVM** và không có biến đổi byte, chúng thường cho lại chuỗi ban đầu với charset hỗ trợ văn bản đó; nhưng **các byte đã tạo có thể khác giữa máy**. Việc ghi tệp trên máy A rồi đọc bằng máy B mới là ranh giới dễ xuất hiện lỗi mã hóa, đặc biệt với các charset không biểu diễn được tất cả ký tự.

Để khống chế hành vi, chọn overload có `Charset`:

~~~java
import java.nio.charset.StandardCharsets;

byte[] bytes = "Tiếng Việt".getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
~~~

Đoạn này là **mảnh mã minh họa** vì không có `main`; nó cho thấy cách chỉ định UTF-8 độc lập với default charset. `StandardCharsets.UTF_8` là hằng charset chuẩn có sẵn trên mọi triển khai Java SE.

Với luồng, cũng truyền vào constructor:

~~~java
Reader reader = new InputStreamReader(input, StandardCharsets.UTF_8);
Writer writer = new OutputStreamWriter(output, StandardCharsets.UTF_8);
~~~

Đây là mảnh mã minh họa; `input` và `output` là các stream đã được mở, phải được đóng đúng cách. Với tệp, có thể chọn constructor `FileReader`/`FileWriter` nhận `Charset` trên các JDK hiện đại, hoặc dùng `Files.newBufferedReader`/`Files.newBufferedWriter` nhận `Charset`.

## 5. Những ngoại lệ nổi bật: API không dùng default charset

Thay đổi từ JDK 18 **không có nghĩa mọi API Java đều đổi về UTF-8**. Có API đã cố định UTF-8 trước đó, có API cố định encoding khác và có API phụ thuộc đầu cuối/định dạng.

| API hoặc tình huống | Quy tắc thực tế |
|---|---|
| `Files.readString(path)`, `Files.writeString(path, text)` | Mặc định **UTF-8** theo hợp đồng API (từ khi các API này xuất hiện ở JDK 11) |
| `Files.newBufferedReader(path)`, `Files.newBufferedWriter(path)` | Mặc định **UTF-8** cả trên JDK 17 |
| `Files.readAllLines(path)`, `Files.lines(path)` khi không chỉ charset | Mặc định **UTF-8** |
| `Properties.load(InputStream)`, `Properties.store(OutputStream, ...)` | Định dạng properties dạng byte dùng **ISO-8859-1**, với các escape Unicode theo quy tắc riêng |
| `Properties.load(Reader)`, `Properties.store(Writer, ...)` | Ký tự đã/đang được xử lý bởi `Reader`/`Writer`; charset do phía tạo reader/writer quyết định |
| `PropertyResourceBundle` nạp file `.properties` | Từ JDK 9, mặc định thử UTF-8, có cơ chế fallback ISO-8859-1 khi byte không phải UTF-8 hợp lệ theo quy tắc ResourceBundle; **không đồng nhất với `Properties.load(InputStream)`** |
| `System.out`, `System.err` và việc đọc/ghi ở console | Charset của các stream/console có thể theo môi trường đầu cuối, không nhất thiết bằng `Charset.defaultCharset()`; có quy tắc hệ thống riêng |
| `FileInputStream`, `FileOutputStream`, `Files.readAllBytes` | Hoạt động trên **byte thô**, không tự encode/decode text |
| `InputStreamReader(input, someCharset)`, `new String(bytes, someCharset)` | Dùng **charset được truyền tường minh**, không dùng default |

Vì vậy, chuyển Java 17 → 18 có thể khiến `new FileReader("old.txt")` diễn giải khác trước, trong khi `Files.readString(path)` vốn luôn dùng UTF-8 nên **không thay đổi charset chỉ vì JEP 400**.

### 5.1. Các phương thức của `Files` vốn cố định UTF-8

Các API file dạng ký tự tiện lợi của `java.nio.file.Files` thường mặc định UTF-8. Điều này đã đúng từ trước JDK 18:

~~~java
String content = Files.readString(path); // UTF-8
Files.writeString(path, content);         // UTF-8

try (BufferedReader reader = Files.newBufferedReader(path)) {
    String line = reader.readLine();      // UTF-8
}
~~~

Đây là **mảnh mã minh họa** cần import `Files`, `Path`, `BufferedReader` và `IOException`, đồng thời khai báo `path`. Các phương thức cũng có overload nhận `Charset` để xử lý dữ liệu theo encoding khác. Không dùng kết quả của `Charset.defaultCharset()` để đoán encoding của các overload trên.

### 5.2. `Properties.load(InputStream)` là trường hợp dễ nhầm nhất

Định dạng properties đọc trực tiếp từ byte qua `Properties.load(InputStream)` **không chuyển sang UTF-8 ở JDK 18**. API này giả định **ISO-8859-1** đối với byte đầu vào và hỗ trợ Unicode escape cho ký tự khác. Trong khi đó, `Properties.load(Reader)` tiếp nhận sẵn các ký tự được reader giải mã theo charset do ứng dụng chọn.

Ví dụ một file byte UTF-8 chứa dòng `name=Café`: nếu dùng `load(InputStream)`, ký tự `é` có thể thành `Ã©`; muốn nạp đúng UTF-8 thì bọc `InputStreamReader` với `StandardCharsets.UTF_8` rồi dùng `load(Reader)`.

Đặc biệt, đừng áp dụng nhầm quy tắc này cho `ResourceBundle.getBundle(...)` tải `PropertyResourceBundle`, vì hành vi tải resource bundle dạng properties đã đổi theo JEP 226 từ **JDK 9**. Đây là hai API có quy tắc khác nhau dù tệp cùng phần mở rộng `.properties`.

### 5.3. Console, `System.in/out/err` có quy tắc riêng

Trong ứng dụng chạy từ terminal, bytes đầu vào và đầu ra phải phù hợp encoding mà terminal hoặc môi trường host đang sử dụng. JEP 400 cố ý không bắt buộc `System.out` và `System.err` phải luôn dùng UTF-8 như `Charset.defaultCharset()`; việc tự đổi đầu ra console có thể khiến chữ bị lỗi trên một số môi trường.

- `System.out`/`System.err` là các `PrintStream` có thiết lập encoding gắn với môi trường đầu cuối hoặc thuộc tính liên quan (chẳng hạn `stdout.encoding` và `stderr.encoding`). Không suy ra chúng bằng default charset.
- `System.in` là **luồng byte**. Khi bọc bằng `new InputStreamReader(System.in)` hoặc `new Scanner(System.in)` không chỉ charset, chính wrapper mặc định có thể dùng **default charset**, vốn không nhất thiết trùng với encoding của terminal.
- Với ứng dụng nhập liệu tương tác, xem xét `System.console()`/`Console` khi có console thích hợp; `System.console()` có thể trả `null` khi chạy trong IDE, pipeline hoặc khi chuyển hướng I/O.
- Ở những JDK có thuộc tính `stdin.encoding`, `stdout.encoding` và `stderr.encoding`, có thể tham khảo chúng theo tài liệu phiên bản triển khai để chọn charset tương ứng. Chúng **không phải bằng chứng** rằng `file.encoding` luôn giống encoding console.

Khi kết nối với một giao thức xác định UTF-8 hoặc ghi ra tệp, nên ghi rõ UTF-8 ở chỗ chuyển ký tự thành byte. Với tương tác trực tiếp terminal, phải xem đặc điểm của thiết bị đầu cuối.

## 6. Ví dụ Java 17+: kiểm chứng API cố định UTF-8 và ISO-8859-1

Tạo tệp **`CharsetApiRulesDemo.java`**, lưu bằng UTF-8:

~~~java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Properties;

public class CharsetApiRulesDemo {
    public static void main(String[] args) throws Exception {
        String text = "Caf\u00E9";
        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);

        System.out.println("UTF-8 bytes: " + Arrays.toString(utf8));
        System.out.println("Explicit decode: "
                + text.equals(new String(utf8, StandardCharsets.UTF_8)));

        Path file = Files.createTempFile("charset-rule-", ".txt");
        try {
            Files.write(file, utf8);
            System.out.println("Files.readString: "
                    + text.equals(Files.readString(file)));
        } finally {
            Files.deleteIfExists(file);
        }

        byte[] propertiesUtf8 = ("name=" + text + "\n")
                .getBytes(StandardCharsets.UTF_8);

        Properties byteProperties = new Properties();
        byteProperties.load(new ByteArrayInputStream(propertiesUtf8));
        System.out.println("Properties.load(InputStream): "
                + text.equals(byteProperties.getProperty("name")));

        Properties readerProperties = new Properties();
        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(propertiesUtf8), StandardCharsets.UTF_8)) {
            readerProperties.load(reader);
        }
        System.out.println("Properties.load(Reader UTF-8): "
                + text.equals(readerProperties.getProperty("name")));
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac -encoding UTF-8 CharsetApiRulesDemo.java
java CharsetApiRulesDemo
~~~

Stdout ổn định trên JDK 17+ (kể cả khi default charset khác UTF-8):

~~~text
UTF-8 bytes: [67, 97, 102, -61, -87]
Explicit decode: true
Files.readString: true
Properties.load(InputStream): false
Properties.load(Reader UTF-8): true
~~~

Tại sao kết quả như vậy?

1. `text.getBytes(StandardCharsets.UTF_8)` tạo byte UTF-8 không phụ thuộc môi trường. Ký tự `é` được mã hóa thành `C3 A9`.
2. `new String(utf8, UTF_8)` giải mã đúng cùng charset; phép so sánh chuỗi trả `true`.
3. `Files.readString(file)` không truyền charset vẫn mặc định UTF-8 theo hợp đồng riêng; trả lại đúng chuỗi, kể cả trên JDK 17.
4. `Properties.load(InputStream)` dùng ISO-8859-1 và diễn giải hai byte UTF-8 của `é` thành hai ký tự, nên chuỗi khác giá trị gốc.
5. `Properties.load(Reader)` nhận ký tự đã được giải mã bằng UTF-8 nên đọc đúng nội dung.

Chương trình sử dụng file tạm và xóa trong `finally` để không ghi đè một file có sẵn. Ví dụ là kiểm chứng **khác biệt giữa hợp đồng API**, không cần đổi `file.encoding` để tạo khác biệt này.

## 7. Ví dụ nhỏ về lỗi khi chuyển phiên bản JDK

Giả sử một hệ thống trước đây chạy JDK 17 trên máy dùng charset cũ, mã như sau:

~~~java
// Mảnh mã minh họa: thiếu chỉ định charset ở ranh giới dữ liệu.
try (FileWriter writer = new FileWriter("report.txt")) {
    writer.write("Café");
}
~~~

Nếu default charset trước đây là ISO-8859-1, `é` có thể được ghi thành byte `E9`. Khi chuyển sang JDK 18+, cùng code thiếu charset có thể ghi UTF-8, trong đó `é` thành `C3 A9`. Một ứng dụng cũ tiếp tục mong chờ ISO-8859-1 sẽ đọc sai file mới; ngược lại, ứng dụng nâng cấp cũng có thể đọc sai dữ liệu cũ.

Giải pháp bền vững là **biết charset thực tế của dữ liệu và chọn tường minh**. Chẳng hạn, khi hệ thống xác định file phải là UTF-8:

~~~java
// Mảnh mã minh họa: cần các import và xử lý IOException phù hợp.
try (Writer writer = new OutputStreamWriter(
        new FileOutputStream("report.txt"), StandardCharsets.UTF_8)) {
    writer.write("Café");
}
~~~

Hoặc trên Java hiện đại:

~~~java
Files.writeString(Path.of("report.txt"), "Café", StandardCharsets.UTF_8);
~~~

Các đoạn trên chỉ nhằm làm rõ lựa chọn charset; với tệp thực phải xem xét chính sách tạo/ghi đè, quyền truy cập và lỗi I/O. Nếu **dữ liệu cũ thật sự dùng encoding legacy**, cần đọc bằng charset legacy **chính xác** để chuyển mã sang UTF-8; chỉ đổi cờ JVM hoặc gắn nhãn “UTF-8” lên byte cũ không tự biến đổi byte thành UTF-8.

Khi di chuyển dữ liệu, xử lý lỗi giải mã có ý nghĩa quan trọng: một số decoder mặc định có thể thay byte không hợp lệ bằng ký tự thay thế, che giấu mất mát dữ liệu. Dữ liệu quan trọng nên được kiểm tra bằng charset đúng và cấu hình decoder phù hợp để phát hiện lỗi thay thế hoặc ký tự không ánh xạ được.

## 8. Kiểm thử migration JDK 17 → 18+

Một quy trình kiểm thử hữu ích:

1. **Liệt kê vị trí phụ thuộc default charset**: `new String(bytes)`, `String.getBytes()`, `FileReader/FileWriter`, `InputStreamReader/OutputStreamWriter`, và các overload tương ứng của `Scanner` hoặc `Formatter`. Đối chiếu hợp đồng từng overload.
2. **Xác định nguồn gốc byte**: dữ liệu tệp cũ, tệp mới, tài nguyên cấu hình, terminal, payload mạng và dữ liệu đối tác có thể thuộc các charset khác nhau.
3. **Thử với UTF-8 rõ ràng ngay trên môi trường cũ**: trên các JDK triển khai hỗ trợ, thử `java -Dfile.encoding=UTF-8 ...` để phát hiện ảnh hưởng khi nâng cấp. Với `javac`, dùng `-encoding UTF-8` khi file nguồn được lưu UTF-8.
4. **Thử chế độ tương thích trên JDK 18+**: `java -Dfile.encoding=COMPAT ...` để so sánh trong quá trình chẩn đoán; đừng coi đây là giải pháp lâu dài thay cho việc ghi rõ encoding ở ranh giới dữ liệu.
5. **Kiểm tra output bằng byte và nội dung đã giải mã**: dùng một tập mẫu gồm ASCII, dấu tiếng Việt, ký tự không thuộc Latin-1 và dữ liệu đã tồn tại. Một kiểm thử chỉ dùng ASCII thường không phân biệt được UTF-8 với nhiều charset cũ.
6. **Giữ nguyên các API có hợp đồng đặc thù**: `Properties.load(InputStream)` và `Files.readString` không cần đổi ý nghĩa chỉ vì JEP 400. Nếu thay API thì phải chủ động đánh giá chuyển đổi format.
7. **Kiểm tra stdout/console riêng**: việc file UTF-8 hợp lệ không chứng minh terminal cũng đang diễn giải stdout theo UTF-8; hãy phân biệt hiển thị trên terminal với byte thật trong file.

Trong dự án, đưa charset vào định nghĩa định dạng tệp hoặc giao thức và kiểm thử vòng đời ghi → đọc trên các môi trường mục tiêu. Không dựa vào charset máy lập trình viên làm hợp đồng dữ liệu.

## 9. Lỗi tư duy thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| “Java 17 mặc định luôn là ANSI; Java 18 luôn UTF-8 trong mọi API” | JDK 17 có thể đã dùng UTF-8; JDK 18+ mặc định UTF-8 **cho API dùng default charset**, vẫn có ngoại lệ |
| “Không truyền charset thì chắc chắn dùng `Charset.defaultCharset()`” | Các API `Files` văn bản, `Properties.load(InputStream)` và console có quy tắc khác |
| “`COMPAT` luôn có nghĩa ISO-8859-1” | `COMPAT` dùng charset tương thích theo môi trường; có thể là UTF-8 hoặc charset khác |
| “Chỉ cần gọi `System.setProperty("file.encoding", "UTF-8")` là mọi luồng đổi ngay” | Cấu hình lúc runtime không đáng tin để thay đổi bộ mã đang được sử dụng |
| “Đổi sang JDK 18 sẽ tự chuyển mọi file cũ sang UTF-8” | Byte đã lưu không thay đổi; cần đọc đúng charset nguồn rồi encode sang charset đích |
| “`System.out.println(...)` chắc chắn xuất UTF-8 từ JDK 18” | Charset console/stdout có quy tắc riêng; terminal còn phải giải mã byte đúng |
| “`.properties` thì luôn ISO-8859-1” | `Properties.load(InputStream)` dùng ISO-8859-1; `PropertyResourceBundle` từ JDK 9 thường đọc UTF-8, có fallback |
| “Dùng ASCII để test đã đủ” | Với ký tự ASCII đơn giản, rất nhiều charset tạo cùng byte; phải dùng ký tự ngoài ASCII để thấy khác biệt |

## 10. Ghi nhớ cốt lõi

- **JDK 17 trở xuống**: default charset phụ thuộc cấu hình nền tảng; **JDK 18 trở lên**: mặc định UTF-8 theo **JEP 400**.
- **`Charset.defaultCharset()`** cho biết charset mặc định của JVM thực tế; trên JDK 18+ có thể thử `-Dfile.encoding=UTF-8` hoặc `-Dfile.encoding=COMPAT` lúc khởi động.
- Chỉ những API **thật sự dựa vào default charset** mới nhận ảnh hưởng tương ứng; API mã hóa cố định và stream byte thô không tự đổi ý nghĩa.
- **`Files.readString/newBufferedReader` mặc định UTF-8**, còn **`Properties.load(InputStream)` dùng ISO-8859-1**; đây là hai ví dụ dễ đối chiếu nhất.
- **Console/stdin/stdout/stderr** có quy tắc encoding riêng; không đồng nhất với default charset mà không kiểm tra.
- Khi dữ liệu phải tồn tại lâu dài hoặc trao đổi qua nhiều máy, **luôn nêu rõ charset**, thường dùng `StandardCharsets.UTF_8`, và kiểm thử cả thao tác encode và decode.

### Tài liệu tham khảo chính thức

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400)
- [Java SE — Charset.defaultCharset()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/Charset.html#defaultCharset())
- [Java SE — Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html)
- [Java SE — Properties](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Properties.html)
- [Oracle — Supported Encodings](https://docs.oracle.com/en/java/javase/25/intl/supported-encodings.html)
