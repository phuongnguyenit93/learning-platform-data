# Chẩn đoán sai working directory, charset và đường dẫn resource trong Java IO

## 1. Ba nguyên nhân gây lỗi dễ bị đánh đồng

Một chương trình Java đọc được dữ liệu trong IDE nhưng thất bại khi chạy từ terminal, JAR, container hoặc server thường gặp một trong ba nhóm vấn đề:

1. **Sai working directory (CWD)**: đường dẫn tệp tương đối được giải quyết tại thư mục làm việc của tiến trình, không phải nơi chứa file source `.java`, file `.class` hay JAR.
2. **Sai charset**: đã mở đúng file/resource nhưng biến các byte thành ký tự theo encoding khác, gây mất dấu tiếng Việt, ký tự lạ hoặc ngoại lệ giải mã.
3. **Sai đường dẫn resource**: nhầm file system path với resource trong classpath/module hoặc nhầm đường dẫn tính từ package của class với đường dẫn tính từ classpath root.

Chẩn đoán đúng phải tách **vị trí tìm tệp**, **cơ chế tra cứu** và **cách diễn giải bytes**. Sửa một nhóm vấn đề không tự giải quyết nhóm còn lại.

Bài hướng dẫn kiến thức Java 17+ trong module IO: nhận biết CWD và `user.dir`, dùng `Path`/`Files` với base directory tường minh, tra classpath resources trong IDE/JAR, chọn charset chính xác, tái hiện lỗi bằng chương trình độc lập và xây kiểm thử chịu được thay đổi môi trường.

## 2. Working directory không phải thư mục source hay thư mục JAR

Một ví dụ:

~~~java
Path path = Path.of("data/customers.csv");
String csv = Files.readString(path, StandardCharsets.UTF_8);
~~~

Đây là đoạn minh họa cần được đặt trong method với imports và xử lý `IOException`. Chuỗi `data/customers.csv` là **relative filesystem path**. Trên default filesystem, nó được diễn giải theo working directory mà runtime đang sử dụng. Java không tự động dò tìm:

- Thư mục hiện đang chứa file `.java`.
- Thư mục build có file `.class`.
- Thư mục cài đặt JAR.
- `src/main/resources` trong source tree.
- Những JAR/dependency nằm trên classpath.

Ví dụ cấu trúc:

~~~text
/work/app/
  data/customers.csv
  build/classes/example/Main.class
  app.jar
~~~

Nếu command chạy từ `/work/app`, path tương đối có thể chỉ tới `/work/app/data/customers.csv`. Nếu chạy cùng JAR khi CWD là `/srv/service`, Java có thể tìm `/srv/service/data/customers.csv`, nơi file không tồn tại.

Việc dùng `java -jar /work/app/app.jar` **không làm CWD tự chuyển sang thư mục chứa JAR**. Launcher, shell, IDE, service manager hoặc container xác định CWD.

### Cách kiểm tra CWD trong Java

~~~java
System.out.println(System.getProperty("user.dir"));
System.out.println(Path.of("").toAbsolutePath().normalize());
System.out.println(Path.of("data/customers.csv").toAbsolutePath().normalize());
~~~

Đoạn trên là minh họa, chưa phải chương trình độc lập. In các giá trị đó tại thời điểm gặp lỗi giúp xác nhận Java **đang tra file ở đâu**.

`System.getProperty("user.dir")` thường phản ánh working directory được runtime thiết lập lúc khởi chạy. Không dùng `System.setProperty("user.dir", "...")` như một giải pháp portable để đổi OS CWD giữa chương trình: thay đổi một Java property không có nghĩa mọi API/file system provider sẽ lập tức coi process đã đổi directory. Nếu muốn đổi nơi đọc dữ liệu, **truyền một base `Path` tường minh** hoặc khởi động tiến trình con với working directory mong muốn.

### Absolute path, normalize và toRealPath

| Phương thức | Chức năng | Lưu ý |
| --- | --- | --- |
| `Path.of("x/y")` | Tạo path theo provider mặc định | Thường relative nếu không có root |
| `path.isAbsolute()` | Kiểm tra path tuyệt đối theo provider | Cú pháp Unix và Windows khác nhau |
| `path.toAbsolutePath()` | Tạo absolute representation từ ngữ cảnh hiện tại | Không chứng minh file tồn tại |
| `path.normalize()` | Xử lý thành phần `.` và `..` theo cú pháp | Không tự resolve symbolic links |
| `path.toRealPath()` | Resolve sang real path và kiểm tra tồn tại theo options | Có thể ném `IOException`; symlink semantics tùy options |
| `base.resolve(relative)` | Ghép path theo rules của `Path` | Nếu `relative` là absolute, behavior cần được xác thực |

Nếu path đến từ user input, chỉ `normalize()` và `startsWith(base)` không đủ cho mọi yêu cầu bảo mật: symbolic links có thể dẫn ra ngoài base; còn race giữa lúc kiểm tra và mở file.

## 3. Chỉ định base directory để tránh phụ thuộc ngữ cảnh chạy

Nếu tài nguyên là **dữ liệu bên ngoài ứng dụng** như file khách hàng, logs, output directory hoặc config thay đổi theo deployment, hãy nhận location qua args/config/env và tạo path từ base đó.

~~~java
static Path resolveUnderBase(Path baseDirectory, String relativeName)
        throws IOException {
    Path base = baseDirectory.toAbsolutePath().normalize();
    Path resolved = base.resolve(relativeName).normalize();
    if (!resolved.startsWith(base)) {
        throw new IOException("Path outside configured base");
    }
    return resolved;
}
~~~

Đây là method minh họa; phải import `Path` và `IOException`. Với untrusted paths, ví dụ chỉ kiểm tra lexical traversal, không xử lý đầy đủ symlink và TOCTOU race. Cần chính sách quyền và filesystem isolation cụ thể.

Ưu tiên những lựa chọn có hợp đồng rõ:

- `--data-dir=/var/lib/example` được truyền khi khởi động.
- Environment variable/config chứa đường dẫn tuyệt đối đã được validate.
- `Files.createTempDirectory(...)` cho dữ liệu dùng trong test/job tạm.
- User home khi dữ liệu thật sự thuộc một tài khoản người dùng.
- Data volume được mount vào một vị trí có tài liệu hóa trong container.

Không liên tục thử `../data`, `../../data` rồi chọn cái chạy được ở IDE: cách đó trở nên mong manh khi cấu trúc build hoặc service CWD thay đổi.

## 4. Classpath resource là cơ chế khác filesystem

Tài nguyên đóng gói như template, ảnh tĩnh, schema hoặc file mặc định có thể nằm ở:

~~~text
src/main/java/example/App.java
src/main/resources/config/defaults.properties
src/main/resources/templates/message.txt
~~~

Build tool thường sao chép chúng vào classpath root hoặc JAR:

~~~text
classes/
  example/App.class
  config/defaults.properties
  templates/message.txt
~~~

**Không mặc định dùng path `src/main/resources/config/defaults.properties` khi chạy production.** Source tree không nhất thiết tồn tại trong container hay sau khi đóng gói JAR.

Đọc resource đúng:

~~~java
try (InputStream in = App.class
        .getResourceAsStream("/config/defaults.properties")) {
    if (in == null) throw new FileNotFoundException("Resource missing");
    String content = new String(in.readAllBytes(), StandardCharsets.UTF_8);
}
~~~

Đây là mảnh mã cần import `InputStream`, `FileNotFoundException` và `StandardCharsets`, có `App` trong classpath và được đặt trong method. `getResourceAsStream` trả `null` nếu không tìm được resource theo cơ chế lookup; phải kiểm tra null trước khi đọc.

Resource thường nên được coi là **read-only asset**. Đừng cố ghi state vào `src/main/resources` hoặc vào JAR runtime. Muốn cho user chỉnh template mặc định, hãy copy resource vào thư mục dữ liệu do user/application sở hữu rồi sửa bản copy.

## 5. Quy tắc dấu slash và package khi tra resource

Giả sử class `com.example.io.Demo` và resource `config/defaults.properties` ở classpath root:

| Biểu thức | Vị trí được tìm |
| --- | --- |
| `Demo.class.getResourceAsStream("/config/defaults.properties")` | Từ resource root |
| `Demo.class.getResourceAsStream("defaults.properties")` | Tương đối package `com/example/io/` |
| `Demo.class.getResourceAsStream("config/defaults.properties")` | `com/example/io/config/defaults.properties` |
| `Demo.class.getClassLoader().getResourceAsStream("config/defaults.properties")` | Root của classloader |
| `Demo.class.getClassLoader().getResourceAsStream("/config/defaults.properties")` | Thường sai do leading slash |

`Class.getResourceAsStream` hỗ trợ cú pháp có leading slash để nói rõ root. `ClassLoader.getResourceAsStream` nhận resource name theo quy tắc classloader, thường không dùng slash đầu.

Không phải mọi class loader là cùng một instance: app server, plugin, module hoặc test runner có thể sử dụng classloader riêng. Bootstrap-loaded classes có thể có `getClassLoader()==null`. Nếu resource còn tồn tại nhưng lookup sai, hãy xác định class nào/classloader nào thực hiện truy cập.

### Khi nhiều JAR có resource cùng tên

Hai dependency cùng chứa `config/defaults.properties` có thể khiến một resource “đúng tên nhưng sai nội dung” được chọn. Nếu cần chẩn đoán:

~~~java
Enumeration<URL> found =
        Demo.class.getClassLoader().getResources("config/defaults.properties");
while (found.hasMoreElements()) {
    System.out.println(found.nextElement());
}
~~~

Đây là mảnh mã với imports `Enumeration`, `URL` và xử lý `IOException`; không phải chương trình hoàn chỉnh. Thứ tự classloader lookup có thể khác theo môi trường. Cân nhắc namespace resource path theo module/library, hoặc định nghĩa cơ chế override config rõ.

## 6. Resource bên trong JAR không phải một file path thông thường

Sau khi đóng gói, resource có thể có URL:

~~~text
jar:file:/opt/app/app.jar!/config/defaults.properties
~~~

Đừng coi nó là local file ở path `/opt/app/app.jar!/config/defaults.properties`. Code có thể chạy được trong IDE khi URL là `file:/.../classes/config/defaults.properties` nhưng thất bại khi URL là `jar:...`.

Ví dụ **không nên dùng như giải pháp tổng quát**:

~~~java
URL url = Demo.class.getResource("/config/defaults.properties");
Path path = Path.of(url.toURI());
~~~

Đây là mã minh họa thiếu imports và exception handling; trên JAR URI, chuyển sang `Path` có thể thất bại nếu filesystem provider tương ứng chưa được tạo hoặc không hỗ trợ. Để chỉ **đọc** resource, dùng `getResourceAsStream` và `try-with-resources`.

Nếu thư viện thật sự bắt buộc nhận `Path`, có thể copy resource ra temp file với giới hạn kích thước rồi quản lý cleanup, hoặc dùng ZIP FileSystem được mở/đóng có chủ đích trong trường hợp phù hợp. Không tự ép mọi URL thành file local.

Với named modules (JPMS), còn có phạm vi truy cập resource theo module và các quy tắc encapsulation. Nếu ứng dụng chạy module path thay vì classpath truyền thống, phải kiểm tra `Module.getResourceAsStream` và quyền `opens` nơi áp dụng.

## 7. Sai charset: đọc đúng byte nhưng tạo sai String

`Charset` là quy tắc mã hóa ký tự sang bytes và giải mã bytes thành ký tự. Nếu file được ghi bằng UTF-8 nhưng application đọc theo charset khác, dấu tiếng Việt có thể biến thành mojibake.

Ví dụ chữ `Café` được mã hóa UTF-8 thành:

~~~text
43 61 66 C3 A9
~~~

Trong đó `C3 A9` là hai byte biểu diễn `é`. Đọc cùng bytes theo ISO-8859-1 tạo hai ký tự khác với `é`.

~~~java
String text = "Caf\u00e9";
byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
String good = new String(utf8, StandardCharsets.UTF_8);
String wrong = new String(utf8, StandardCharsets.ISO_8859_1);
System.out.println(text.equals(good));  // true
System.out.println(text.equals(wrong)); // false
~~~

Đây là mảnh minh họa trong method có import `StandardCharsets`. Unicode escape trong source giúp một test cụ thể không phụ thuộc khả năng terminal/source editor hiển thị chữ `é`.

### Mặc định không thống nhất giữa mọi API

Một số API nhận charset rõ, một số overload sử dụng default charset của JVM:

- `Files.readString(path, StandardCharsets.UTF_8)`: explicit UTF-8.
- `Files.readString(path)` từ Java 11: overload không đối số charset **được đặc tả dùng UTF-8**.
- `Files.newBufferedReader(path)`: overload không charset dùng UTF-8.
- `new InputStreamReader(input)`: dùng default charset của JVM.
- `new FileReader(file)` không có charset: dùng default charset.
- `new OutputStreamWriter(output)` không có charset: dùng default charset.
- `text.getBytes()` không có charset: dùng default charset.
- `text.getBytes(StandardCharsets.UTF_8)`: không phụ thuộc default.

Với Java 17, default charset có thể tùy môi trường/locale/cấu hình hệ thống. JEP 400 đưa UTF-8 thành default từ JDK 18 theo cấu hình chuẩn, nhưng không biến mọi byte encoding/console behavior thành giống nhau.

**Không khắc phục bằng cách chỉ gọi `System.setProperty("file.encoding", "UTF-8")` giữa chương trình.** Việc đổi property runtime không được bảo đảm làm mọi decoder đã khởi tạo hoặc I/O API đổi encoding. Hãy chỉ định charset tại boundary dữ liệu.

## 8. File charset khác console charset

Luồng hiển thị trên terminal gồm ít nhất ba tầng:

~~~text
File bytes
    └── file decoder (UTF-8, ISO-8859-1, ...)
              └── Java String (Unicode text)
                          └── stdout/console encoder
                                    └── terminal decoder / font
                                               └── ký tự hiển thị
~~~

Nếu Java String đã đúng nhưng terminal hiện sai, sửa charset của file reader có thể làm dữ liệu thành sai. Ngược lại, nếu String đã sai ngay khi decode, thay font terminal không sửa được dữ liệu.

Cách kiểm tra:

1. So sánh String đã decode với expected literal bằng `equals`.
2. In hex bytes nguồn của một đoạn nhỏ, nếu dữ liệu được phép log.
3. In code points của String khi cần, không chỉ nhìn giao diện terminal.
4. Kiểm tra charset của writer phía trước; có thể file đã được encode sai từ nguồn.
5. Phân biệt default charset JVM, encoding do API quy định, encoding của console và hệ điều hành.
6. Với dữ liệu nhạy cảm, log kích thước/hash hoặc mẫu giả lập, không ghi toàn bộ nội dung.

Một lỗi giải mã có thể ném `MalformedInputException` hoặc hiển thị ký tự thay thế, tùy API/decoder policy. `NoSuchFileException` lại là vấn đề tra path; không thể chữa bằng đổi UTF-8.

### UTF-8 BOM và newline

Một số file UTF-8 bắt đầu bằng BOM `EF BB BF`, có thể xuất hiện trong Java String thành `U+FEFF` ở đầu nội dung. Không mặc định mọi parser đều loại bỏ BOM; ứng dụng nên có hợp đồng chấp nhận/bỏ BOM rõ ràng.

CRLF/LF khác nhau giữa môi trường hoặc công cụ tạo file. Nếu parser yêu cầu byte-for-byte reproduction, thao tác `BufferedReader.readLine()` sẽ bỏ newline, nên cần lựa chọn API lưu/đọc bytes phù hợp.

Nếu cần từ chối bytes UTF-8 sai thay vì tự thay bằng ký tự replacement, dùng `CharsetDecoder` với `CodingErrorAction.REPORT` và bắt `CharacterCodingException`.

## 9. Ví dụ Java 17+ độc lập: chạy từ CWD khác

Chương trình sau kiểm tra ba đường tìm dữ liệu và một tình huống sai charset:

1. File tương đối `input.txt` **không có trong CWD runtime**.
2. File input được truyền bằng **đường dẫn tuyệt đối** nên đọc được.
3. Resource `/sample/message.txt` nằm trong classpath root nên đọc được.
4. Dữ liệu `Café` được encode/decode UTF-8 đúng, nhưng decode ISO-8859-1 cho String khác.

Cấu trúc test:

~~~text
demo/
  ResourcePathsDemo.java
  classes/
    ResourcePathsDemo.class
    sample/message.txt           (RESOURCE_OK)
  input/input.txt                (FILE_OK)
  runtime/                       (thư mục chạy chương trình, không có input.txt)
~~~

Lưu thành **`ResourcePathsDemo.java`**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;

public class ResourcePathsDemo {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException("Provide absolute path to input.txt");
        }
        Path relative = Path.of("input.txt");
        System.out.println("Relative input found: " + Files.exists(relative));

        Path explicit = Path.of(args[0]);
        System.out.println("Explicit file: " +
                Files.readString(explicit, StandardCharsets.UTF_8).trim());

        try (InputStream in = ResourcePathsDemo.class
                .getResourceAsStream("/sample/message.txt")) {
            if (in == null) throw new IOException("Classpath resource missing");
            String resourceText = new String(in.readAllBytes(), StandardCharsets.UTF_8);
            System.out.println("Classpath resource: " + resourceText.trim());
        }

        String text = "Caf\u00e9";
        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
        System.out.println("UTF-8 bytes: " +
                HexFormat.of().withUpperCase().formatHex(utf8));
        System.out.println("UTF-8 roundtrip: " +
                text.equals(new String(utf8, StandardCharsets.UTF_8)));
        System.out.println("Wrong decoding changes value: " +
                !text.equals(new String(utf8, StandardCharsets.ISO_8859_1)));
        Charset systemDefault = Charset.defaultCharset();
        System.out.println("Default charset inspected: " + (systemDefault != null));
    }
}
~~~

### Chuẩn bị và chạy từ terminal Linux/macOS

Từ thư mục `demo/`:

~~~bash
mkdir -p classes/sample input runtime
printf 'RESOURCE_OK\n' > classes/sample/message.txt
printf 'FILE_OK\n' > input/input.txt
javac -d classes ResourcePathsDemo.java

CLASSES="$(pwd)/classes"
INPUT="$(pwd)/input/input.txt"
cd runtime
java -cp "$CLASSES" ResourcePathsDemo "$INPUT"
~~~

### Chuẩn bị trên Windows PowerShell

Từ thư mục `demo/`:

~~~powershell
New-Item -ItemType Directory -Force classes/sample, input, runtime | Out-Null
Set-Content classes/sample/message.txt 'RESOURCE_OK' -Encoding ASCII
Set-Content input/input.txt 'FILE_OK' -Encoding ASCII
javac -d classes ResourcePathsDemo.java

$classes = (Resolve-Path classes).Path
$inputFile = (Resolve-Path input/input.txt).Path
Push-Location runtime
try {
    java -cp $classes ResourcePathsDemo $inputFile
} finally {
    Pop-Location
}
~~~

File mẫu chỉ có ASCII để script tạo dữ liệu không phụ thuộc cách PowerShell mặc định encode. Các file thực có tiếng Việt nên được lưu/đọc bằng UTF-8 theo contract; chương trình test ký tự `é` bằng Unicode escape của Java.

**Stdout đã kiểm chứng bằng biên dịch/chạy JDK 17 từ một runtime directory tách biệt:**

~~~text
Relative input found: false
Explicit file: FILE_OK
Classpath resource: RESOURCE_OK
UTF-8 bytes: 436166C3A9
UTF-8 roundtrip: true
Wrong decoding changes value: true
Default charset inspected: true
~~~

**Diễn giải kết quả:**

- `Path.of("input.txt")` được kiểm tra theo CWD là `runtime/`, nơi không có file, nên false trong test này.
- `args[0]` trỏ tới `input/input.txt` bằng absolute path và `Files.readString(..., UTF_8)` trả `FILE_OK`.
- `ResourcePathsDemo.class.getResourceAsStream("/sample/message.txt")` tìm tại root của classpath chứa `classes/`, không cần file tồn tại ở CWD.
- `String.getBytes(UTF_8)` của `Café` tạo bytes `43 61 66 C3 A9`; giải mã đúng UTF-8 khôi phục String, giải mã sai ISO-8859-1 tạo giá trị khác.
- Dòng kiểm tra default charset không phụ thuộc việc runtime default là Windows-1252 hay UTF-8. Code có thể quan sát tên bằng `Charset.defaultCharset().name()` khi chẩn đoán thật.
- Resource stream được đóng qua `try-with-resources`; data input đọc được vì location và charset đều tường minh.

**Lưu ý:** `Files.exists` có thể trả false trong những trường hợp không xác định được tồn tại do lỗi I/O/quyền, nên không dùng nó làm bằng chứng tuyệt đối rằng path chưa từng tồn tại. Trong test dựng riêng, `runtime/input.txt` cố tình không được tạo.

## 10. Kiểm thử sau khi package JAR

Nếu đã compile và copy `classes/sample/message.txt` như trên, có thể đóng JAR:

~~~bash
jar --create --file demo.jar --main-class ResourcePathsDemo -C classes .
jar --list --file demo.jar
~~~

Danh sách entries phải có `ResourcePathsDemo.class` và `sample/message.txt`. Đường dẫn resource trong archive không được vô tình thêm tiền tố `classes/` hoặc `src/main/resources/`.

Sau đó chạy JAR từ một working directory khác:

~~~bash
java -jar /absolute/path/to/demo.jar /absolute/path/to/input/input.txt
~~~

Hai đường dẫn trong ví dụ phải được thay bằng absolute paths thật. Nếu JAR resource đúng, `getResourceAsStream("/sample/message.txt")` vẫn đọc được dù CWD là thư mục khác.

Nếu code đã chạy được bằng `java -cp classes ...` nhưng không chạy khi `java -jar ...`, kiểm tra:

- File resource có được package vào JAR không?
- Tên entry có phân biệt hoa/thường khác so với code không?
- Có package/resource filtering làm đổi đường dẫn hoặc bytes không?
- Có phụ thuộc `src/test/resources` chỉ hiện trong test classpath không?
- Có dùng `new File(getResource(...).toURI())` khiến resource trong JAR không còn là file thông thường không?
- Classloader/module của bản chạy đã thay đổi không?

## 11. Maven/Gradle: resources có vòng đời riêng

Trong dự án Maven/Gradle tiêu chuẩn:

~~~text
src/main/java/...
src/main/resources/templates/email.txt
src/test/java/...
src/test/resources/fixtures/data.txt
~~~

`src/main/resources` được copy vào output dành cho runtime/JAR theo build configuration thông thường. `src/test/resources` thuộc test runtime; nó **không mặc định được package vào production JAR**.

Nếu một feature chỉ dùng test fixture và sau đó gọi classpath lookup trong production, có thể trả `null` vì resource không hiện diện.

Resource filtering có thể thay đổi contents (ví dụ biểu thức placeholder, charset và line endings). Với binary assets như ảnh, JKS/PKCS12, ZIP, chứng chỉ, không tùy tiện bật text filtering. Nếu cần content chính xác, kiểm tra checksums trước/sau package.

Trong Gradle/Maven IDE, working directory của Run Configuration thường là project root, nhưng **không nên lấy điều đó làm hợp đồng production**. Dùng path tuyệt đối được truyền vào hoặc resource lookup độc lập CWD.

## 12. Làm test không phụ thuộc một CWD cố định

Với dữ liệu file, dùng thư mục tạm và explicit UTF-8:

~~~java
Path temp = Files.createTempDirectory("io-test-");
Path file = temp.resolve("unicode.txt");
try {
    String expected = "Caf\u00e9";
    Files.writeString(file, expected, StandardCharsets.UTF_8);
    String actual = Files.readString(file, StandardCharsets.UTF_8);
    if (!expected.equals(actual)) throw new AssertionError("Wrong charset");
} finally {
    Files.deleteIfExists(file);
    Files.deleteIfExists(temp);
}
~~~

Đây là đoạn minh họa trong method có imports và throws/exception handling. Test thực tế có thể dùng JUnit `@TempDir` và kiểm tra cleanup tự động.

Với resource, đặt fixture trong test resources và đọc bằng `TestClass.class.getResourceAsStream("/fixtures/data.txt")`. Để bắt lỗi packaging, cần integration test chạy JAR thật, không chỉ chạy tests trên class directory.

### Tái hiện CWD khác trong một test harness

Java không cung cấp một API portable để đổi OS working directory của JVM đang chạy theo thread. Thay vì sửa `user.dir`, có thể khởi chạy **tiến trình Java con** qua `ProcessBuilder.directory(...)`:

~~~java
ProcessBuilder pb = new ProcessBuilder(
        "java", "-cp", absoluteClasspath, "ResourcePathsDemo", absoluteInput);
pb.directory(otherWorkingDir.toFile());
Process child = pb.start();
int exitCode = child.waitFor();
~~~

Đây là snippet minh họa chưa độc lập: `absoluteClasspath`, `absoluteInput`, `otherWorkingDir` cần được khai báo và xử lý `IOException`/`InterruptedException`. Với integration test thực tế, cần đọc stdout/stderr (tránh pipe bị tắc), timeout, và kiểm tra exit code/expected output. Có thể dùng Java executable từ toolchain thay vì giả định luôn có `java` trên PATH.

**Mục tiêu của test:** buộc các path sai dựa vào project root bị lộ rõ và xác nhận resource lookup/explicit input hoạt động khi CWD khác.

## 13. Lỗi thường gặp và cách phân loại

| Hiện tượng | Nhóm lỗi | Kiểm tra / xử lý |
| --- | --- | --- |
| `NoSuchFileException` | Path không tồn tại ở vị trí được mở | Log absolute target và CWD |
| `FileNotFoundException` | File stream không mở được path | Kiểm tra path, file type, quyền |
| `AccessDeniedException` | Thiếu quyền truy cập | Kiểm tra account, ACL, mount mode |
| `InvalidPathException` | Syntax path không hợp lệ | Kiểm tra input path theo OS/provider |
| `getResourceAsStream()==null` | Resource lookup thất bại | Kiểm tra leading slash, package, JAR/classloader |
| `FileSystemNotFoundException` khi đổi resource URI thành Path | Sai cơ chế filesystem provider | Đọc qua `InputStream` hoặc mở filesystem provider đúng |
| `MalformedInputException` | Bytes không hợp lệ với decoder | Kiểm tra original bytes và charset |
| `UnmappableCharacterException` | Encoding/decoding không biểu diễn được theo policy | Chọn charset và error strategy rõ |
| Có text lỗi dấu nhưng không exception | Mojibake hoặc decoder replacement | So sánh Unicode/code points và hex |
| Resource đúng tên nhưng nội dung sai | Trùng resource trong dependencies | Enumerate resource URLs và kiểm soát classloader |

Không bắt rộng `IOException` rồi báo tất cả trường hợp là “Không tìm thấy file”. Làm vậy che lỗi quyền, ổ đĩa, encoding, provider hoặc kết nối mạng.

## 14. Tệp lớn, resource stream và những giới hạn khác

`Files.readString` và `InputStream.readAllBytes()` đọc toàn bộ dữ liệu vào bộ nhớ; phù hợp với cấu hình hoặc resource nhỏ, nhưng không phải mặc định tốt cho log nhiều GB.

Với file văn bản lớn, đọc theo streaming:

~~~java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        handle(line);
    }
}
~~~

Đây là snippet minh họa; `handle` do ứng dụng cung cấp, imports/exception handling cần đầy đủ. `readLine()` không giữ newline terminators, nên nếu cần bảo toàn byte-exact file để xác thực checksum/chữ ký, hãy thao tác bytes thay vì khôi phục text.

Với binary file như ZIP, hình ảnh, key store hoặc compressed resource, tránh decode thành String rồi encode lại; điều đó có thể phá bytes. Dùng `InputStream` và đúng binary parser.

Khi xử lý cấu hình đầu vào không tin cậy, giới hạn kích thước, đường dẫn được phép, độ sâu cấu trúc và thời gian I/O. Resource path được normalize không đồng nghĩa an toàn trước symlink/race; phải chọn chiến lược bảo vệ theo threat model.

## 15. Checklist chẩn đoán theo nhóm lỗi

### A. Relative file path không hoạt động

1. In/log `Path.of("").toAbsolutePath()`, `user.dir` và `path.toAbsolutePath().normalize()`.
2. Kiểm tra file tồn tại ở vị trí thực, quyền và loại file.
3. So sánh CWD của IDE, terminal, service manager, Docker `WORKDIR` hoặc container process.
4. Truyền một base directory qua args/config thay vì giả định project root.
5. Thử chạy từ CWD khác bằng process con.

### B. Classpath resource trả null

1. Kiểm tra path của resource **trong build output/JAR**, không chỉ trong source tree.
2. Kiểm tra leading slash của `Class.getResourceAsStream` và không dùng slash đầu trong `ClassLoader.getResourceAsStream`.
3. Kiểm tra package-relative path, case sensitivity và classloader/module boundary.
4. Xác nhận main resources thay vì test-only resources.
5. Nếu có nhiều resources trùng tên, enumerate URL matches.
6. Với resource trong JAR, dùng `InputStream`, không tự biến nó thành filesystem `File`.

### C. Chữ Việt bị lỗi

1. Xác nhận đã mở đúng file/resource.
2. Xem bytes gốc, charset do producer dùng và charset decoder hiện tại.
3. Dùng explicit `StandardCharsets.UTF_8` khi hợp đồng là UTF-8.
4. Kiểm tra BOM, malformed sequences, decoder replacement policy.
5. Phân biệt Java String sai với console hiển thị sai.
6. Tạo regression test kiểm tra String equality/code points/expected bytes.

### D. IDE chạy tốt nhưng production sai

1. So sánh CWD, JVM version, default charset, locale, classpath, module path.
2. Kiểm tra JAR contents và tài nguyên đã đóng gói.
3. Kiểm tra environment variables, system properties, quyền service account.
4. Xác minh case-sensitive filenames trên OS đích.
5. Chạy integration test từ CWD khác và với build artifact thật.
6. Log đầy đủ các thông số đường dẫn/charset cần thiết nhưng không lộ bí mật.

## 16. Các anti-pattern đặc trưng

| Cách làm sai | Vì sao lỗi | Thay bằng |
| --- | --- | --- |
| `Path.of("src/main/resources/template.txt")` trong production | Source tree có thể không tồn tại | `getResourceAsStream("/template.txt")` |
| Giả định `java -jar` thay CWD | JAR location khác process CWD | Base dir tường minh |
| Gọi `getResourceAsStream("config/x.txt")` từ class ở package khác | Tên relative tính từ package | Dùng slash root nếu cần |
| Dùng `ClassLoader.getResourceAsStream("/config/x.txt")` | Sai quy tắc tên resource classloader | Bỏ leading slash |
| Ép `jar:` URL thành file địa phương | Resource JAR không phải file local độc lập | Đọc bằng stream |
| Lưu dữ liệu runtime vào JAR/classpath | Thường read-only/không writable | Data directory tách biệt |
| `InputStreamReader(in)` không charset với file UTF-8 | Default charset có thể khác | `InputStreamReader(in, UTF_8)` |
| `String.getBytes()` cho format cố định | Phụ thuộc default charset | `getBytes(UTF_8)` |
| Đổi `user.dir` để “sửa” CWD | Không portable cho OS/process | Truyền base Path hoặc ProcessBuilder.directory |
| Chỉ kiểm tra `Files.exists` rồi giả định chắc chắn | Race/permission errors | Mở/đọc thật và xử lý exception |
| Mọi `IOException` đều báo file missing | Che mất nguyên nhân cụ thể | Phân loại theo exception và operation |
| Đổi file decoder vì terminal in sai dấu | Console có thể sai, String đã đúng | So sánh String và terminal riêng |
| Đọc binary bytes như text | Có thể phá dữ liệu không phục hồi | Dùng byte streams |
| Dùng `readAllBytes` cho file rất lớn | Có thể tăng heap/OOME | Streaming và bounded memory |

## 17. Câu hỏi tự kiểm tra

1. `Path.of("data.txt")` tìm cạnh class file hay ở CWD? **Ở CWD của tiến trình**, không phải thư mục class.
2. `java -jar /opt/app/app.jar` có tự đổi CWD sang `/opt/app` không? **Không**.
3. Cách kiểm tra absolute path mà ứng dụng đang tìm? `path.toAbsolutePath().normalize()`.
4. Có nên dùng `System.setProperty("user.dir", ...)` để đổi OS working directory ở runtime không? **Không**, không portable.
5. `src/main/resources` có luôn tồn tại trên server sau build không? **Không**.
6. Với `Class.getResourceAsStream("/config/x.txt")`, leading slash nghĩa gì? **Tìm từ resource root**.
7. `Class.getResourceAsStream("x.txt")` không slash tìm ở đâu? **Relative với package của class**.
8. Với `ClassLoader.getResourceAsStream` có nên bắt đầu bằng slash không? **Thông thường không**.
9. Resource trong JAR có luôn chuyển thẳng thành `File` được không? **Không**; ưu tiên stream.
10. `Files.readString(path)` trong JDK 17 có dùng default charset không? **Không**, overload đó dùng UTF-8.
11. `new InputStreamReader(in)` không đối số charset thì sao? **Dùng default charset JVM**.
12. UTF-8 bytes của `Café` là gì? **43 61 66 C3 A9**.
13. Decode bytes UTF-8 bằng ISO-8859-1 có thể sai chữ dù không exception? **Có**.
14. Java String đúng nhưng terminal sai dấu có chứng minh file bị lỗi không? **Không**; có thể là console encoding/font.
15. BOM UTF-8 có bytes nào? **EF BB BF**.
16. `Files.exists(path)==false` chứng minh chắc file không tồn tại không? **Không tuyệt đối**, có race và lỗi quyền/I/O.
17. Làm sao phát hiện app phụ thuộc ngầm vào IDE working directory? **Khởi chạy từ một CWD khác trong integration test**.
18. File chỉ có trong `src/test/resources` có tự vào production JAR không? **Thông thường không**.
19. Nếu classpath có hai resources cùng tên, có nguy cơ đọc nhầm không? **Có**, cần namespace/kiểm soát classloader.
20. Dữ liệu runtime có nên ghi vào `src/main/resources`/JAR không? **Không**, hãy dùng data directory writable rõ ràng.

## Tài liệu API tham khảo

- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): relative/absolute path, normalize, toRealPath.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): readString, newBufferedReader, newInputStream và I/O errors.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): getResource/getResourceAsStream và package-relative lookup.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): tra cứu và enumerate resources.
- [Java SE 17 — Charset](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html) và [StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): charset mặc định, UTF-8 và các charset chuẩn.
- [Java SE 17 — CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html): malformed bytes và decoder policy.
- [Java SE 17 — ProcessBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html): chạy process con với working directory đã chỉ định.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): sự thay đổi từ JDK 18 và vấn đề tương thích.
