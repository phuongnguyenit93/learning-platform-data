# Đọc tài nguyên trong JAR và đóng InputStream đúng cách

> **Phạm vi:** Java Core → ClassLoader → Tài nguyên. Mục tiêu là đọc văn bản, cấu hình và dữ liệu nhị phân đã đóng gói trong JAR bằng resource API, phân biệt tên tài nguyên tương đối/tuyệt đối, xử lý `null` và lỗi I/O, sử dụng `try-with-resources` để đóng `InputStream`, đồng thời tránh phụ thuộc vào đường dẫn file vật lý. Mã minh họa dùng Java 17+.

## 1. Vì sao đọc tài nguyên trong JAR khác đọc file trên ổ đĩa?

Trong giai đoạn phát triển, ta có thể đặt `config.properties` hoặc `message.txt` ở thư mục dự án và đọc được bằng `Files.readString(Path.of(...))`. Nhưng sau khi build thành một JAR:

```text
demo.jar
├── META-INF/
│   └── MANIFEST.MF
└── demo/
    ├── JarResourceDemo.class
    └── message.txt
```

`demo/message.txt` là **entry bên trong archive**, không phải file độc lập có đường dẫn OS kiểu `/home/app/demo/message.txt` hoặc `C:\app\demo\message.txt`. Khi chạy `java -cp demo.jar demo.JarResourceDemo`, JVM/ClassLoader có thể tìm entry này bằng tên resource và trả một `InputStream` để đọc bytes.

Phân biệt hai câu hỏi:

1. **Tìm resource ở đâu?** Đây là trách nhiệm của `Class.getResource...`, `ClassLoader.getResource...`, module resource API hoặc cơ chế loader chuyên biệt.
2. **Đọc resource và quản lý vòng đời thế nào?** Đây là trách nhiệm của mã sử dụng `InputStream`, charset/decoder, kiểm tra lỗi và **đóng stream**.

Hướng tiếp cận di động là **resource name → InputStream → đọc dữ liệu → close**. Đừng biến một JAR resource thành `File` chỉ để dùng API của hệ thống file nếu bài toán chỉ là đọc nội dung.

## 2. Chọn API phù hợp để đọc entry trong JAR

Khi mục tiêu là **đọc bytes và đóng stream**, bắt đầu từ API đưa thẳng tới `InputStream`:

| Trường hợp | API phù hợp | Điều cần kiểm tra |
| --- | --- | --- |
| Resource nằm cạnh class `MyClass` | `MyClass.class.getResourceAsStream("data.txt")` | Tên tính từ package của class |
| Resource được gọi bằng tên từ root | `MyClass.class.getResourceAsStream("/demo/data.txt")` | Dấu `/` đầu thuộc quy tắc `Class` |
| Đã chọn một loader cụ thể | `loader.getResourceAsStream("demo/data.txt")` | Không thêm `/` đầu; loader có thể không thấy resource |
| Cần mở dữ liệu từ URL đã tìm được | `url.openStream()` | Kiểm tra URL không `null`, xử lý `IOException` |

Cả `Class.getResourceAsStream` và `ClassLoader.getResourceAsStream` có thể trả `null`: resource thiếu, tên sai, loader khác hoặc giới hạn module đều cần được xét. Nếu cần **liệt kê** nhiều bản cùng tên, dùng `loader.getResources(name)` rồi mở và đóng stream từ từng URL. Với named module, `Module.getResourceAsStream(name)` có chính sách `opens` riêng; không suy ra khả năng truy cập của nó từ kết quả `ClassLoader`.

Tìm resource không đồng nghĩa nạp một class hay chạy static initializer. Trong JAR, entry không phải `File` độc lập trên đĩa; với bài toán chỉ đọc nội dung, ưu tiên dùng stream.

## 3. Đường dẫn: relative, absolute và dấu gạch chéo

Giả sử class gọi API là `demo.JarResourceDemo`, resource ở entry `demo/message.txt`.

**Với `Class` API:**

```java
// Tìm demo/message.txt: tên tương đối theo package "demo"
JarResourceDemo.class.getResourceAsStream("message.txt");

// Tìm demo/message.txt: dấu "/" đầu là tuyệt đối từ root
JarResourceDemo.class.getResourceAsStream("/demo/message.txt");

// Tìm message.txt ngay ở root archive/classpath, KHÔNG phải demo/message.txt
JarResourceDemo.class.getResourceAsStream("/message.txt");
```

**Với `ClassLoader` API:**

```java
ClassLoader loader = JarResourceDemo.class.getClassLoader();

// Đúng: tên từ resource root
loader.getResourceAsStream("demo/message.txt");

// Không dùng "/" đầu với ClassLoader API
loader.getResourceAsStream("/demo/message.txt");
```

Các snippet trên phải nằm trong code có class `demo.JarResourceDemo`, ví dụ một method của chính lớp đó; chúng minh họa **quy tắc lookup**, không phải chương trình Java độc lập.

Lý do: `Class.getResource...` khi tên không bắt đầu `/` sẽ thêm package prefix (thay dấu `.` thành `/`). Nếu tên bắt đầu `/`, nó bỏ dấu `/` trước khi tìm. Trong khi đó, `ClassLoader.getResource...` nhận tên đã tính từ root; **không có quy tắc tự loại bỏ dấu `/`** giống như `Class` API.

Bảng tóm tắt:

| Lời gọi từ `demo.JarResourceDemo` | Tên thực tìm |
| --- | --- |
| `getResourceAsStream("message.txt")` | `demo/message.txt` |
| `getResourceAsStream("/demo/message.txt")` | `demo/message.txt` |
| `getResourceAsStream("/message.txt")` | `message.txt` |
| `getClassLoader().getResourceAsStream("demo/message.txt")` | `demo/message.txt` |

Trong JAR, entry names dùng dấu `/`, thường **phân biệt hoa/thường**. Đừng dùng dấu `\` làm package separator hoặc tự biến một resource name thành đường dẫn Windows. Đừng đặt `src/main/resources` vào tên runtime nếu build tool đã copy nội dung thư mục đó làm classpath root.

## 4. Bài thực hành độc lập: đóng gói, đọc và đóng stream

Ví dụ được thiết kế để **chạy thật từ JAR**, không chỉ chạy từ IDE. Chỉ cần JDK 17+ và các lệnh `javac`, `jar`, `java`.

### Cấu trúc source

```text
src/
  demo/
    JarResourceDemo.java
resources/
  demo/
    message.txt
classes/           (được javac tạo)
demo.jar           (được jar tạo)
```

**File `src/demo/JarResourceDemo.java`:**

```java
package demo;

import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public class JarResourceDemo {
    private static String readText(InputStream input) throws IOException {
        if (input == null) {
            throw new FileNotFoundException("demo/message.txt");
        }

        try (input) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8)
                    .stripTrailing();
        }
    }

    public static void main(String[] args) throws IOException {
        System.out.println("relative: " + readText(
                JarResourceDemo.class.getResourceAsStream("message.txt")));

        System.out.println("absolute: " + readText(
                JarResourceDemo.class.getResourceAsStream("/demo/message.txt")));

        System.out.println("loader: " + readText(
                JarResourceDemo.class.getClassLoader()
                        .getResourceAsStream("demo/message.txt")));

        URL url = JarResourceDemo.class.getResource("message.txt");
        System.out.println("protocol: " + url.getProtocol());
        System.out.println("missing: "
                + (JarResourceDemo.class.getResourceAsStream("missing.txt")
                        == null));
    }
}
```

**File `resources/demo/message.txt` (UTF-8):**

```text
Hello from inside JAR
```

### Biên dịch và đóng gói

Tại thư mục gốc chứa `src` và `resources`:

```bash
javac -d classes src/demo/JarResourceDemo.java
jar --create --file demo.jar -C classes . -C resources .
jar --list --file demo.jar
java -cp demo.jar demo.JarResourceDemo
```

Đối với Windows PowerShell/CMD, ví dụ này cũng dùng được với dấu `/` trong đối số của các công cụ JDK. Nếu muốn kiểm tra nội dung, `jar --list --file demo.jar` sẽ có các entry `demo/JarResourceDemo.class` và `demo/message.txt`; danh sách đầy đủ còn có manifest/directory entries nên không hardcode toàn bộ output của `jar`.

**Stdout của lệnh `java -cp demo.jar demo.JarResourceDemo` đã được kiểm tra bằng OpenJDK 21:**

```text
relative: Hello from inside JAR
absolute: Hello from inside JAR
loader: Hello from inside JAR
protocol: jar
missing: true
```

Điểm đáng chú ý:

- `java -cp demo.jar`: ứng dụng lấy cả class và resource từ cùng archive.
- Ba API lookup đầu đều tìm đúng entry `demo/message.txt` theo ba cách khác nhau.
- `try (input)`, được Java 9+ hỗ trợ với biến tham số **effectively final**, đóng stream khi rời block, kể cả khi đọc phát sinh `IOException`.
- `input.readAllBytes()` đọc bytes; `new String(..., UTF_8)` giải mã văn bản bằng **charset xác định**. Không phụ thuộc system-default encoding.
- `stripTrailing()` chỉ dùng trong ví dụ để bỏ newline cuối file cho output ổn định; ứng dụng thật không nên tự strip/trim khi khoảng trắng cuối là dữ liệu có ý nghĩa.
- `protocol: jar` cho thấy URL nhận được thuộc dạng `jar:...!/demo/message.txt` khi chạy từ JAR. Phần đường dẫn thực tế không cố định giữa máy.
- `missing: true` minh họa resource không có thì API trả `null`, thay vì tự ném `FileNotFoundException` tại bước lookup. Hàm `readText` chủ động ném checked exception có nghĩa rõ ràng trong trường hợp resource bắt buộc bị thiếu.

**Tại sao không có `try-with-resources` trong `main`?** Vì helper `readText` **nhận quyền sở hữu** stream mà caller tạo, đóng stream bên trong rồi trả `String` (không trả một stream còn mở). Đây là một hợp đồng thiết kế có chủ đích; phương thức công khai phải nói rõ ai chịu trách nhiệm close, tránh đóng hai lần hoặc giữ stream rò rỉ. Phần 5 đưa mẫu thường gặp, nơi chính caller mở và đóng resource.

## 5. Mẫu ưu tiên: try-with-resources ngay tại nơi sử dụng

Nếu không cần helper nhận ownership, nên viết trực tiếp:

```java
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

// Bên trong method Java có throws IOException:
String name = "/demo/message.txt";

try (InputStream in = MyClass.class.getResourceAsStream(name)) {
    if (in == null) {
        throw new FileNotFoundException("Classpath resource: " + name);
    }

    String text = new String(in.readAllBytes(), StandardCharsets.UTF_8);
    System.out.println(text);
}
```

`MyClass` là class minh họa cần thay bằng class thật của bạn; đoạn code trên **không là một chương trình độc lập**. `try-with-resources` chấp nhận giá trị resource là `null`: nếu `null` thì không có đối tượng nào để đóng. Ta vẫn cần kiểm tra `null` **trước khi gọi `readAllBytes()`**, bởi vì nếu không, lỗi quan sát được sẽ là `NullPointerException` thiếu ngữ cảnh.

Với API truy cập bằng class loader:

```java
// Bên trong method có tham chiếu tới Class<?> owner
ClassLoader loader = owner.getClassLoader();
if (loader == null) {
    // owner có thể được định nghĩa bởi bootstrap loader;
    // cân nhắc ClassLoader.getSystemResourceAsStream(...) hoặc API Class.
}

try (InputStream in =
             owner.getResourceAsStream("/demo/message.txt")) {
    if (in == null) {
        throw new FileNotFoundException("demo/message.txt");
    }
    // Đọc dữ liệu rồi tự động đóng InputStream.
}
```

Ở đây `owner` được giả định là một biến `Class<?>` do caller truyền; snippet không độc lập. Không gọi `loader.getResourceAsStream(...)` nếu `loader == null`. **Dùng `owner.getResourceAsStream`** thường đơn giản hơn, đặc biệt khi muốn gắn lookup với class cụ thể và không muốn đoán loader toàn cục.

### Điều gì xảy ra khi có exception?

`try-with-resources`:

1. Lấy stream cần sử dụng.
2. Chạy phần thân `try`.
3. Gọi `close()` **khi thoát khỏi block**, dù code thành công hay ném exception.
4. Nếu phần thân và `close()` cùng ném exception, lỗi của close thường được lưu như **suppressed exception** của lỗi chính.

Không cần gọi `close()` thủ công trước mỗi `return` hay trong cả `catch` và `finally`. Nếu xây API trả `InputStream` cho caller, **caller** phải nhận trách nhiệm đóng; nếu đã đóng bên trong method thì không thể trả stream đã đóng rồi mong caller tiếp tục đọc.

`IOException` có thể phát sinh khi đọc **hoặc** đóng. Đừng viết `catch (IOException ignored) {}` để che lỗi khi file cấu hình quan trọng đã bị cắt/đọc không hoàn chỉnh.

## 6. Chọn cách đọc theo dữ liệu: text, binary, lớn hay nhỏ

### Văn bản nhỏ, UTF-8 rõ ràng

`InputStream.readAllBytes()` (Java 9+) thích hợp với **resource nhỏ có kích thước đã biết/được kiểm soát**.

```java
try (InputStream in =
        MyClass.class.getResourceAsStream("/demo/settings.json")) {
    if (in == null) {
        throw new FileNotFoundException("demo/settings.json");
    }
    String json = new String(in.readAllBytes(), StandardCharsets.UTF_8);
}
```

Đoạn này là snippet trong method có `throws IOException` và class `MyClass` phù hợp. Nó chỉ đọc chuỗi JSON, **không parse/validate JSON**.

### Đọc văn bản bằng Reader có chỉ định charset

Khi cần đọc theo dòng hoặc giảm bộ nhớ tạm so với `readAllBytes()`:

```java
try (InputStream in =
             MyClass.class.getResourceAsStream("/demo/words.txt")) {
    if (in == null) {
        throw new FileNotFoundException("demo/words.txt");
    }

    try (var reader = new java.io.BufferedReader(
            new java.io.InputStreamReader(in, StandardCharsets.UTF_8))) {
        for (String line; (line = reader.readLine()) != null; ) {
            System.out.println(line);
        }
    }
}
```

Đây là snippet không độc lập. `BufferedReader` giúp đọc từng dòng; đóng reader cũng đóng stream bên dưới. Hai lớp `try-with-resources` cùng quản lý stream có thể làm `close()` được gọi lặp lại; `InputStream` thông thường xử lý được, nhưng **thiết kế sạch hơn** là khai báo một reader trong try-with-resources sau khi đã kiểm tra stream mở, hoặc chỉ một owner có trách nhiệm đóng. Ví dụ dưới đây rõ ràng hơn khi cần reader:

```java
InputStream raw = MyClass.class.getResourceAsStream("/demo/words.txt");
if (raw == null) {
    throw new FileNotFoundException("demo/words.txt");
}

try (var reader = new java.io.BufferedReader(
        new java.io.InputStreamReader(raw, StandardCharsets.UTF_8))) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
```

`reader.close()` tự đóng `InputStreamReader` rồi `raw`. Mọi snippet ở đây cần ngữ cảnh import hoặc tên đầy đủ và xử lý `IOException`.

### Dữ liệu nhị phân: không ép thành String

Với ảnh hoặc dữ liệu nhị phân, giữ bytes nguyên vẹn:

```java
try (InputStream in =
             MyClass.class.getResourceAsStream("/demo/logo.png")) {
    if (in == null) {
        throw new FileNotFoundException("demo/logo.png");
    }
    byte[] image = in.readAllBytes();
    // Đưa bytes cho decoder/consumer nhị phân thích hợp.
}
```

Đừng dùng `new String(bytes, UTF_8)` để làm bước trung gian cho ảnh: quá trình decode/encode có thể thay đổi dữ liệu không phải text.

### Resource lớn: đọc từng phần

`readAllBytes()` có thể tiêu tốn rất nhiều bộ nhớ, nhất là khi input kích thước không tin cậy. Với dữ liệu lớn có thể dùng mảng đệm, giới hạn tổng bytes, hoặc `transferTo(OutputStream)` nếu phù hợp luồng xử lý:

```java
try (InputStream in =
             MyClass.class.getResourceAsStream("/demo/large.bin")) {
    if (in == null) {
        throw new FileNotFoundException("demo/large.bin");
    }

    byte[] buffer = new byte[8192];
    long total = 0;
    int count;
    while ((count = in.read(buffer)) != -1) {
        total += count;
        if (total > 50_000_000L) {
            throw new IOException("Resource exceeds permitted limit");
        }
        // Xử lý đúng buffer[0..count), không dùng toàn bộ 8192 byte.
    }
}
```

Đoạn này chỉ minh họa cơ chế giới hạn và stream consumption; với nguồn không tin cậy, quy trình còn cần giới hạn tổng dung lượng thực tế **trước khi thực hiện tác vụ tốn kém**, không chỉ đếm sau khi đọc. Chú ý `InputStream.available()` **không phải** kích thước file: API chỉ cho số byte ước lượng có thể đọc không chặn, không dùng để cấp phát mảng chính xác.

## 7. Vì sao không nên ép URL trong JAR thành java.io.File?

Thao tác có vẻ hợp lý:

```java
URL url = MyClass.class.getResource("/demo/message.txt");
java.io.File file = new java.io.File(url.toURI());
```

Đoạn trên là snippet minh họa, cần xử lý `URISyntaxException` và kiểm tra `url != null`. Nó có thể hoạt động khi resource là một file trực tiếp trong thư mục output (URL scheme `file:`) nhưng **thường không hoạt động khi nằm trong JAR** (URL scheme `jar:`). `File`/`Path.of(URI)` mặc định cần URI có filesystem provider phù hợp; `jar:file:/...!/demo/message.txt` không tự biến thành file thực trong filesystem mặc định.

Không nên làm:

- Ghép `System.getProperty("user.dir") + "/src/main/resources/..."` để đọc resource trong deployed JAR.
- Ép mọi `URL` resource thành `new File(...)` rồi dùng `Files.readString`.
- Bắt `FileSystemNotFoundException` và tự đổi thành path bằng cách cắt chuỗi `!`: dễ sai với encoding, nested JAR, tùy biến loader.

Đúng cho **bài toán chỉ đọc content**:

```java
try (InputStream in = MyClass.class.getResourceAsStream("/demo/message.txt")) {
    if (in == null) {
        throw new FileNotFoundException("demo/message.txt");
    }
    // Xử lý bytes hoặc chuyển sang Reader.
}
```

Nếu cần **duyệt toàn bộ entries**, xác minh chữ ký, truy cập metadata của JAR riêng biệt, lúc đó mới cân nhắc `java.util.jar.JarFile`, `java.util.zip.ZipFile` hoặc ZIP/JAR FileSystem Provider. Đó là API có yêu cầu/lifecycle khác và thường cần **đường dẫn tới archive thật**, không phải phương án thay thế cơ học cho resource stream.

## 8. Khi cần dùng JarFile trực tiếp: đóng cả JarFile lẫn InputStream

Nếu ứng dụng nhận đường dẫn tới một archive thật (không chỉ là classpath resource) và cần đọc chính xác một entry, `JarFile` là lựa chọn thích hợp.

```java
import java.io.FileNotFoundException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

// Bên trong method Java có throws IOException:
try (JarFile jar = new JarFile("demo.jar")) {
    JarEntry entry = jar.getJarEntry("demo/message.txt");
    if (entry == null) {
        throw new FileNotFoundException("demo/message.txt");
    }

    try (InputStream in = jar.getInputStream(entry)) {
        String text = new String(in.readAllBytes(), StandardCharsets.UTF_8);
        System.out.println(text);
    }
}
```

Đây là snippet trong method có xử lý `IOException`. Ý nghĩa:

- `JarFile` **mở archive và quản lý tài nguyên của archive**; đóng bằng outer try-with-resources.
- `jar.getInputStream(entry)` cấp stream đọc bytes của entry; đóng bằng inner try-with-resources.
- `JarEntry.getName()` là tên bên trong JAR với dấu `/`, không phải path tuyệt đối của OS.
- Đường `"demo.jar"` ở đây là **file JAR trên disk** relative với working directory; nếu bạn chỉ có classpath resource từ custom loader mà không có file vật lý thì không mặc nhiên dùng được `JarFile`.

Đừng dùng `JarFile` chỉ để lấy một file cấu hình nếu `Class.getResourceAsStream` đã đáp ứng. Càng không quên đóng `JarFile` khi duyệt nhiều entries vì có thể giữ file descriptors, archive handles và bộ đệm nén.

## 9. Nhiều tài nguyên cùng tên và ClassLoader khác nhau

Classpath có thể chứa hai JAR đều có entry `demo/config.properties`. Khi đó:

- `getResource("demo/config.properties")` thường trả một URL được tìm theo chính sách tìm kiếm của loader.
- `getResourceAsStream(...)` đọc từ một resource mà cơ chế lookup đã chọn.
- `getResources("demo/config.properties")` có thể cung cấp nhiều URL; dùng khi **cố ý muốn tổng hợp** nhiều resources (ví dụ metadata plugins), chứ không phải cách “lấy bản mới nhất”.

Ví dụ:

```java
import java.io.InputStream;
import java.net.URL;
import java.util.Enumeration;

// Đặt trong method có throws IOException:
ClassLoader loader = Thread.currentThread().getContextClassLoader();
if (loader == null) {
    loader = ClassLoader.getSystemClassLoader();
}

Enumeration<URL> all = loader.getResources("demo/config.properties");

while (all.hasMoreElements()) {
    URL url = all.nextElement();
    try (InputStream in = url.openStream()) {
        // Đọc từng bản cấu hình và gộp theo quy tắc ứng dụng.
    }
}
```

Không cố cast loader thành `URLClassLoader` để hỏi đường JAR; trên JDK 9+ application loader mặc định không buộc là `URLClassLoader`. Thứ tự giữa các resources phụ thuộc loader, classpath/module search và duplicate packages; **không dùng thứ tự ngẫu nhiên thay cho chính sách merge**.

**ClassLoader identity quan trọng:** `SomeClass.class.getClassLoader()` chỉ loader **định nghĩa** class. Trong container/plugin, cùng resource name có thể có kết quả khác khi hỏi system loader, thread context loader hoặc plugin loader. Nếu tài nguyên “đi cùng” một class, thường nên gọi `ThatClass.class.getResourceAsStream` để tránh phải đoán loader nào đang nhìn thấy nó.

### Resource trong named module

Kể từ Java 9, resource lookup có thể chịu **module encapsulation**. Theo API Java SE, tài nguyên không phải `.class` nằm trong package của named module có thể **không hiện ra** qua `ClassLoader.getResource...` nếu package không được mở một cách phù hợp; đặc biệt, ClassLoader API có yêu cầu **unconditionally opened package** đối với nhiều resource trong named modules.

`Class.getResourceAsStream` dùng semantics của module chứa class, và việc truy cập còn phụ thuộc caller/module và quy tắc `Module.getResourceAsStream`. Điều này nghĩa là `null` **không đủ để kết luận file bị thiếu**: file có thể tồn tại nhưng không được phép truy cập qua API/caller đó. Khi đóng gói named modules, hãy kiểm tra `module-info.java`, `opens` và phương thức tìm tài nguyên; đừng thử sửa bằng cách ghép path OS.

## 10. Resource không tìm thấy: thiết kế xử lý thất bại rõ ràng

`getResourceAsStream` có thể trả `null` do:

1. Entry không tồn tại trong JAR hoặc thư mục classpath.
2. Sai tên package, thiếu/thừa dấu `/`, sai chữ hoa/chữ thường.
3. Resource không được copy vào output JAR.
4. Khác class loader hoặc thread context loader.
5. Named module encapsulation hoặc giới hạn truy cập.
6. Lỗi/giới hạn mở stream từ URL, tùy implementation và hoàn cảnh.

**Resource bắt buộc:** báo lỗi ngay với tên resource rõ ràng, chẳng hạn:

```java
InputStream raw = MyClass.class.getResourceAsStream("/demo/settings.json");
if (raw == null) {
    throw new IllegalStateException(
            "Required resource missing: /demo/settings.json");
}
try (raw) {
    // parse dữ liệu bắt buộc
}
```

Snippet này không độc lập. `IllegalStateException` là quyết định thiết kế cho configuration bắt buộc; cũng có thể chọn `FileNotFoundException` trong API xử lý `IOException`. Tránh để `NullPointerException` ở dòng đọc stream vì thông tin chẩn đoán kém.

**Resource tùy chọn:** có thể trả cấu hình mặc định hoặc `Optional` sau khi kiểm tra `null`, nhưng phải phân biệt **thật sự thiếu** với **I/O error trong lúc đọc**. Không nên tự động biến mọi `IOException` thành “dùng giá trị mặc định” nếu dữ liệu sai/hỏng cần được phát hiện.

### Kiểm tra JAR đóng gói

Từ thư mục có archive:

```bash
jar --list --file demo.jar
```

Xác nhận đúng entry `demo/message.txt` (hoặc tên cấu hình thực tế). Nếu dùng Maven, thông lệ là `src/main/resources/demo/message.txt` sẽ được copy về output classpath/JAR tương ứng; với Gradle Java plugin, `src/main/resources` cũng là nguồn resource mặc định. Tuy nhiên cần kiểm tra cấu hình build vì filters/resource exclusions có thể thay đổi nội dung/đường dẫn.

Không cần sửa `-cp` chỉ để truy cập một entry mà archive đã có trong classpath đúng: tập trung xác minh tên resource và loader. Nếu JAR chứa tài nguyên nhưng không nằm trong nguồn tìm kiếm của loader dùng để lookup, mới cần điều chỉnh cấu hình runtime.

## 11. Những lỗi quản lý stream phổ biến

| Lỗi | Rủi ro | Cách sửa |
| --- | --- | --- |
| Gọi `getResourceAsStream(...).readAllBytes()` ngay | `NullPointerException` nếu không tìm thấy. | Lưu stream, kiểm tra `null`, xử lý tên resource cụ thể. |
| Không đóng stream từ `getResourceAsStream` hoặc `URL.openStream` | Rò tài nguyên, file handle hoặc network handle tùy nguồn. | Dùng `try-with-resources` quanh stream. |
| Trả `InputStream` đã bị đóng bên trong helper | Caller không thể đọc stream đúng. | Thiết lập ownership: caller đóng nếu API trả stream; helper đóng nếu trả bytes/text. |
| Dùng `File` cho URL `jar:` | Thất bại khi chuyển URI hoặc giả định sai filesystem. | Đọc bằng `InputStream`; dùng `JarFile` khi thật sự quản lý archive vật lý. |
| Giải mã văn bản bằng default charset | Nội dung tiếng Việt/UTF-8 bị sai tùy môi trường. | Dùng `StandardCharsets.UTF_8` hoặc charset được đặc tả trong định dạng. |
| Dùng `new String(imageBytes, UTF_8)` cho ảnh | Hỏng dữ liệu nhị phân. | Giữ bytes và dùng decoder nhị phân thích hợp. |
| Dùng `available()` làm size toàn file | Có thể đọc thiếu/cấp phát sai. | Đọc đến EOF hoặc theo format length có giới hạn. |
| Đọc resource cực lớn bằng `readAllBytes()` | OOM hoặc áp lực GC. | Streaming theo chunks, giới hạn bytes. |
| Dùng `reader.lines()` rồi quên đóng reader | Stream liên kết có thể giữ resource mở. | Đặt reader trong try-with-resources, đặc biệt khi trả stream lười. |
| Quên đóng `JarFile` hoặc `ZipFile` | Archive handle có thể giữ file không xóa/ghi lại được. | Bọc object archive bằng try-with-resources. |
| Một utility tự đóng stream do caller truyền mà không nêu | Caller bị bất ngờ khi muốn sử dụng tiếp. | Ghi rõ ownership hoặc API nhận `Supplier<InputStream>` với hợp đồng phù hợp. |
| Nuốt `IOException` lúc đọc/close | Mất dữ liệu hoặc che lỗi runtime. | Ghi nhận/cấp lỗi lên caller, xử lý suppressed exceptions. |

Về file handle: ngay cả sau khi **đã đóng một `InputStream`**, implementation URL/ClassLoader có thể cache và quản lý JAR ở cấp khác. Việc đóng stream là **nghĩa vụ của người dùng stream**, nhưng không khẳng định toàn bộ archive cache của JVM/custom loader bị giải phóng ngay. Nếu bạn tự tạo `URLClassLoader` phục vụ plugin, hãy quản lý cả vòng đời/`close()` của chính loader khi thích hợp.

## 12. Thực hành thiết kế API đọc config an toàn

Một helper dùng trong code sản xuất nên:

- Nhận **`Class<?> owner`** hoặc class loader/Module cụ thể để chủ động xác định không gian tìm kiếm.
- Dùng resource name **rõ ràng, có quy tắc** (ví dụ `"/demo/config.properties"` cho `Class` API).
- Kiểm tra `null` rồi tạo exception mô tả resource.
- Đọc bằng charset xác định hoặc decoder dữ liệu thích hợp.
- Đóng stream đúng một chỗ theo hợp đồng ownership.
- Không tiết lộ URL/path tuyệt đối trong logs nhạy cảm nếu có thông tin deployment không muốn công khai.
- Có giới hạn kích thước tối đa với resources đến từ nguồn không tin cậy.

Ví dụ helper độc lập có thể tái sử dụng (đặt trong file `ResourceText.java` ở default package nếu copy nguyên):

```java
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class ResourceText {
    private ResourceText() {}

    public static String requiredUtf8(Class<?> owner, String absoluteName)
            throws IOException {
        if (!absoluteName.startsWith("/")) {
            throw new IllegalArgumentException(
                    "Expected absolute resource name: " + absoluteName);
        }

        try (InputStream in = owner.getResourceAsStream(absoluteName)) {
            if (in == null) {
                throw new FileNotFoundException(absoluteName);
            }
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
```

Đây là **một class biên dịch được**; chưa có `main` để tự chạy và cần caller truyền `owner` + `absoluteName`. Helper giữ nguyên whitespace/newline của resource; không `trim` hoặc `strip` nội dung cấu hình. `owner` không được `null` theo contract bạn định nghĩa; có thể thêm `Objects.requireNonNull` nếu input là dữ liệu ngoại vi. Nếu resource lớn, nên dùng phiên bản streaming hoặc giới hạn bytes thay vì `readAllBytes()`.

Ví dụ cách gọi bên trong class của ứng dụng:

```java
String text = ResourceText.requiredUtf8(
        MyApplication.class, "/demo/config.properties");
```

`MyApplication` là class minh họa, không có sẵn trong file `ResourceText.java`; phải thay bằng class của ứng dụng và xử lý `IOException`. Khi chạy trong named module, vẫn cần quyền truy cập resource thích hợp như mục 9.

## 13. Câu hỏi tự kiểm tra

1. **Tài nguyên `demo/message.txt` trong JAR có bắt buộc tồn tại thành file `demo/message.txt` ngoài ổ đĩa không?** Không. Nó là entry của archive; đọc bằng resource stream.
2. **Từ class `demo.Example`, `getResourceAsStream("message.txt")` khác `getResourceAsStream("/message.txt")` thế nào?** Tên đầu tìm `demo/message.txt`, tên thứ hai tìm `message.txt` ở root.
3. **`ClassLoader.getResourceAsStream("/demo/message.txt")` là tên chuẩn không?** Không; ClassLoader API nhận resource name từ root **không có dấu `/` đầu**. Truyền `"demo/message.txt"`.
4. **API trả `null` có thể có nghĩa gì?** Thiếu resource, sai tên/loader, bị encapsulation/giới hạn truy cập hoặc không thể lấy stream theo hành vi implementation; không tự khẳng định file không có.
5. **Đọc trong JAR bằng `File` hay `getResourceAsStream` nên chọn gì?** Đọc content bằng resource stream; `File` chỉ phù hợp nếu thật sự có đường dẫn filesystem và API yêu cầu.
6. **Tại sao try-with-resources cần thiết?** Đóng stream tự động ở cả đường thành công và exception, hạn chế rò handle.
7. **Ai đóng stream do helper trả ra?** Tùy hợp đồng API. Nếu trả `InputStream` còn mở thì caller phải đóng; nếu helper đọc rồi trả `String`/`byte[]` thì helper nên đóng stream trước khi trả.
8. **`readAllBytes` luôn thích hợp với mọi resource?** Không, chỉ cho dữ liệu có kích thước hợp lý/được kiểm soát; resource lớn cần streaming và giới hạn.
9. **Resource có cùng tên trong hai JAR thì `getResourceAsStream` đọc cả hai?** Không; nó mở một resource tìm được. Dùng `getResources` khi thực sự muốn liệt kê nhiều bản.
10. **Tại sao `JarFile` có hai mức tài nguyên cần đóng?** Vì có handle của archive và stream của từng entry; try-with-resources quản lý cả hai.
11. **Đã đóng stream đồng nghĩa file JAR bị unload khỏi JVM?** Không. Class loader và URL caching có vòng đời riêng; stream close chỉ đảm bảo trách nhiệm đóng stream mà caller sở hữu.
12. **Trong named module, không thấy resource luôn nghĩa là build bỏ quên file?** Không. Còn có ràng buộc encapsulation/opens và API tra cứu.

## 14. Tài liệu chuẩn

- [Java SE 21 — `Class.getResourceAsStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getResourceAsStream(java.lang.String)): tên relative/absolute theo package, resource trong named modules.
- [Java SE 21 — `ClassLoader` resource APIs](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `getResource`, `getResourceAsStream`, `getResources` và search order.
- [Java SE 21 — `Module.getResourceAsStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html#getResourceAsStream(java.lang.String)): encapsulation và module resource lookup.
- [Java SE 21 — `InputStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html): `readAllBytes`, `transferTo`, `available` và `close`.
- [Java SE 21 — `AutoCloseable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/AutoCloseable.html): vòng đời của try-with-resources.
- [Java SE 21 — `JarFile`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/jar/JarFile.html): đọc entry và đóng archive.
- [Java SE 21 — `jar` tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html): đóng gói class và resources từ các thư mục.
- [The Java Language Specification, `14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3): semantics close và suppressed exceptions.
