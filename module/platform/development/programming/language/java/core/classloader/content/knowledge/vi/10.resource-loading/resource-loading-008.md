# file:, jar:, jrt: và giới hạn chuyển URL tài nguyên thành File trong Java

Một tài nguyên (*resource*) trong ứng dụng Java không nhất thiết nằm trong một tệp thông thường của hệ điều hành. Khi dùng `Class.getResource(...)` hoặc `ClassLoader.getResource(...)`, bạn nhận một `java.net.URL` mô tả **cách truy cập tài nguyên**, chứ không nhận cam kết rằng có thể gọi `new File(...)` để thao tác trên nó.

Ba dạng URL hay gặp khi học class loader và tài nguyên trên Java 17+ là:

| Scheme | Ví dụ minh họa | Tài nguyên ở đâu? |
|---|---|---|
| **`file:`** | `file:/opt/app/classes/demo/config.txt` | Tệp/thư mục trên một filesystem, thường gặp khi chạy từ thư mục `classes` |
| **`jar:`** | `jar:file:/opt/app/lib/app.jar!/demo/config.txt` | Một entry nằm bên trong archive JAR |
| **`jrt:`** | `jrt:/java.base/java/lang/String.class` | Nội dung runtime image theo mô hình module của JDK 9+ |

**Nguyên tắc quan trọng:** Khi mục tiêu chỉ là **đọc dữ liệu resource**, ưu tiên `getResourceAsStream(...)` hoặc `URL.openStream()`. Chỉ chuyển sang `Path`/`File` khi thực sự cần API tệp và đã xác minh URL có scheme và filesystem phù hợp.

## 1. Resource name khác URL, Path và File

Với lớp:

```java
package demo;

public final class App {
}
```

và cấu trúc triển khai:

```text
classes/
└── demo/
    ├── App.class
    └── config.txt
```

Bạn có thể tra resource theo hai cách:

```java
URL a = App.class.getResource("config.txt");
URL b = App.class.getClassLoader()
        .getResource("demo/config.txt");
```

Cả hai tìm cùng resource trong ví dụ, nhưng quy tắc tên khác nhau:

- **`Class.getResource("config.txt")`:** tên không bắt đầu bằng `/` được giải quyết **tương đối với package của class** (`demo/config.txt`).
- **`Class.getResource("/demo/config.txt")`:** dấu `/` đầu chỉ resource tuyệt đối tính từ gốc phạm vi lookup của class, và được bỏ trước khi tra bằng tên resource.
- **`ClassLoader.getResource("demo/config.txt")`:** tên resource luôn dùng dạng đường dẫn tuyệt đối trong namespace của loader **không có `/` đầu**. Dùng `"/demo/config.txt"` với API này thường không tìm thấy resource trong mô hình classpath thông thường.

Đối số `"demo/config.txt"` là **resource name**, không phải URL hay một đường dẫn filesystem tuyệt đối. Nó sử dụng `/` theo quy ước của Java ngay cả trên Windows.

Các đối tượng khác nhau phục vụ nhu cầu khác nhau:

| Đối tượng | Biểu diễn | Dùng khi |
|---|---|---|
| `String` resource name | `demo/config.txt` | Yêu cầu class loader tìm tài nguyên |
| `URL` | `jar:file:/.../app.jar!/demo/config.txt` | Xác định vị trí/cách mở tài nguyên |
| `URI` | `jar:file:/.../app.jar!/demo/config.txt` | Biểu diễn định danh theo cú pháp URI, không tự bảo đảm có filesystem |
| `Path` | Đường dẫn trong **một `FileSystem` cụ thể** | Dùng các API `Files.readString`, `Files.list`, v.v. |
| `File` | Đối tượng đại diện cho tên đường dẫn filesystem mặc định | Dùng legacy APIs yêu cầu `java.io.File` |
| `InputStream` | Luồng byte từ một nguồn đã mở | Đọc nội dung mà **không cần** tệp vật lý |

Một `URL` hợp lệ có thể trỏ tới JAR entry, JDK module image hoặc nguồn khác. Việc gọi `getResource(...)` thành công chỉ cho thấy resource có thể được định vị; nó **không chứng minh** resource có một tệp độc lập trên disk.

## 2. Dạng file: — khi có thể chuyển thành Path

Nếu chương trình chạy với `java -cp classes ...`, resource trong thư mục output thường có URL dạng:

```text
file:/home/user/project/classes/demo/config.txt
```

Khi scheme là `file` và URI phù hợp provider của filesystem hiện tại, cách chuyển nên dùng là:

```java
URL url = App.class.getResource("config.txt");
if (url == null) {
    throw new IllegalStateException("Missing config.txt");
}
if (!"file".equalsIgnoreCase(url.getProtocol())) {
    throw new IllegalStateException("Not a filesystem URL");
}

Path path = Path.of(url.toURI());
String content = Files.readString(path, StandardCharsets.UTF_8);
```

Đây là **đoạn minh họa** đặt trong một phương thức có khai báo/nhập `App`, `URL`, `Path`, `Files`, `StandardCharsets` và xử lý các checked exceptions. Với Java 17, `Path.of(URI)` là API phù hợp khi muốn chuyển URI sang `Path` qua filesystem provider hỗ trợ.

**Vì sao không dùng `new File(url.getFile())`?**

Một URL file có thể chứa mã hóa percent-encoding:

```text
file:/home/user/My%20Project/classes/demo/config.txt
```

- `url.getPath()` và `url.getFile()` cung cấp thành phần URL; chuỗi có thể còn `%20` đại diện cho khoảng trắng.
- `new File(url.getFile())` có thể diễn giải `%20` thành ba ký tự `%`, `2`, `0` trong tên file thật, dẫn tới “file not found”.
- `url.toURI()` và `Path.of(uri)` dùng quy tắc URI/filesystem provider để xử lý biểu diễn đường dẫn.
- Không tự thay `"%20"` bằng dấu cách hoặc dùng `URLDecoder.decode(...)` trên **toàn bộ đường dẫn URL**: `URLDecoder` dành cho dữ liệu form/query theo quy tắc riêng (ví dụ dấu `+`), không phải một hàm chuyển mọi URL thành filesystem path.

Trên Windows, URL file có thể mang dạng đại diện cho ổ đĩa hoặc đường UNC; đừng tự bỏ `file:`, tự nối dấu `\` hay suy diễn ký tự ổ đĩa từ chuỗi. Để filesystem provider xử lý qua `URI` và bắt exception nếu URL không được hỗ trợ.

### Những giới hạn ngay cả với file:

- `Path.of(url.toURI())` có thể không dùng được nếu `file:` URI chứa authority/host không được provider hỗ trợ trong môi trường đang chạy.
- Tệp có thể bị xóa/đổi quyền **sau** lúc lấy URL; việc URL hợp lệ không đảm bảo `Files.readString` luôn thành công.
- Một URL file có thể là đường dẫn tới **directory**; `Files.readString` áp dụng cho file nội dung, không có nghĩa mọi path đều có thể đọc như text.
- Với tài nguyên cần ghi, đừng mặc định thư mục `classes`/classpath có thể ghi hoặc thích hợp lưu dữ liệu ứng dụng. Một bản triển khai khác có thể chuyển resource vào JAR.

## 3. Dạng jar: — entry trong archive, không phải file độc lập

Khi đóng gói resource bên trong `app.jar`, cùng resource có thể được tìm thấy dưới URL:

```text
jar:file:/opt/app/app.jar!/demo/config.txt
```

Cú pháp chung của URL JAR theo `JarURLConnection`:

```text
jar:<url-của-JAR>!/<entry-name>
```

Tách các phần:

- `jar:`: giao thức URL chỉ resource thuộc JAR.
- `file:/opt/app/app.jar`: URL của **JAR chứa** tài nguyên; trong một số trường hợp URL JAR bên trong có thể là nguồn không phải local file.
- `!/`: dấu phân cách giữa container JAR và entry.
- `demo/config.txt`: tên entry trong archive.

**Không có một filesystem file thông thường mang tên `demo/config.txt` ngay bên cạnh JAR**. Các byte của entry nằm bên trong archive.

Ví dụ truy cập đúng:

```java
URL url = App.class.getResource("config.txt");
try (InputStream input = url.openStream()) {
    String text = new String(input.readAllBytes(),
            StandardCharsets.UTF_8);
    System.out.println(text);
}
```

Đây là đoạn minh họa yêu cầu xử lý `url == null` và `IOException` trong phương thức gọi; với nội dung nhỏ và đã biết encoding, nó hoạt động cho cả `file:` và `jar:`. `readAllBytes()` tải toàn bộ nội dung vào RAM; với resource lớn, nên đọc theo luồng và đặt giới hạn kích thước phù hợp.

### Vì sao new File(jarURL.toURI()) thất bại?

`java.io.File` chỉ biểu diễn tên đường dẫn trên filesystem mặc định; nó không diễn giải `!/entry` là đường dẫn tệp trong ZIP. Ví dụ:

```java
URL url = App.class.getResource("config.txt");
File file = new File(url.toURI()); // Không đúng cho jar: URL
```

Khi `url` có scheme `jar`, `new File(URI)` ném `IllegalArgumentException` vì constructor này yêu cầu URI theo scheme `file` phù hợp. Việc chuyển đổi chuỗi `url.getFile()` thành `File` cũng không giải quyết được: nó chứa thông tin archive và entry, không phải đường dẫn file bình thường.

**Cẩn thận thêm:** `Path.of(url.toURI())` không phải phép màu tự động biến mọi `jar:` URL thành `Path`. Với `jar` scheme, bạn cần ZIP/JAR filesystem provider và filesystem tương ứng phải được mở. Nếu chưa có filesystem cho JAR hoặc provider không hiện diện, có thể nhận `FileSystemNotFoundException` hay `ProviderNotFoundException`. Vì vậy lời khuyên “dùng `Path.of(url.toURI())` cho tất cả resource URLs” là sai.

### Nếu thật sự cần metadata của JAR

Có thể dùng `JarURLConnection` khi biết URL là `jar:`:

```java
URL url = App.class.getResource("config.txt");
if (url != null && "jar".equals(url.getProtocol())) {
    URLConnection raw = url.openConnection();
    if (raw instanceof JarURLConnection jar) {
        System.out.println(jar.getEntryName());
        System.out.println(jar.getJarFileURL());
    }
}
```

Đây là snippet minh họa với imports `java.net.URL`, `java.net.URLConnection`, `java.net.JarURLConnection` và khả năng ném `IOException`. `getEntryName()` trả tên entry; `getJarFileURL()` trả URL của archive, **không phải** entry. `getJarFileURL()` có thể không dùng scheme file trong mọi môi trường.

`JarURLConnection` cho phép truy cập metadata/manifest/`JarEntry`, nhưng nên chú ý quản lý connection, caching, tài nguyên và lỗi I/O. Nếu chỉ cần nội dung, `openStream()` hoặc `getResourceAsStream` đơn giản hơn.

## 4. Dạng jrt: — tài nguyên trong Java runtime image

Kể từ Java 9, JDK dùng runtime image theo hệ thống module (JEP 220) thay vì một tệp `rt.jar` kiểu JDK 8 cho các lớp nền tảng. Trên các JDK 17+ thông thường, resource của `java.lang.String` có thể có URL như:

```text
jrt:/java.base/java/lang/String.class
```

Nó có nghĩa:

- `jrt:`: giao thức/namespace resource của Java runtime image.
- `java.base`: module chứa class.
- `java/lang/String.class`: đường resource trong module.

Ví dụ:

```java
URL url = String.class.getResource("String.class");
System.out.println(url.getProtocol()); // jrt trên JDK 17 thông thường
```

Đây là snippet đặt trong method có import `java.net.URL` và xử lý `url == null` khi cần. **Đừng viết code yêu cầu mọi Java runtime và custom image luôn trả đúng cùng một chuỗi URL**: cách tài nguyên được tìm thấy phụ thuộc loader, module và runtime implementation. Trong bài thực hành với JDK tiêu chuẩn, `jrt:` là dạng mong đợi.

### jrt: không có nghĩa file vật lý

Dù URL chứa `java/lang/String.class`, đó không phải file thường nằm dưới thư mục `java.base` trên đĩa. Vì vậy:

```java
new File(jrtUrl.toURI()); // Không hợp lệ: scheme không phải file:
```

là sai về mô hình. Giống `jar:`, URL `jrt:` chỉ một nguồn tài nguyên đặc biệt; `java.io.File` không có khả năng đại diện tùy ý cho entry trong runtime image.

Khi chỉ cần đọc, vẫn dùng stream:

```java
URL url = String.class.getResource("String.class");
if (url == null) {
    throw new IllegalStateException("Runtime resource unavailable");
}
try (InputStream input = url.openStream()) {
    byte[] firstBytes = input.readNBytes(4);
    // Đọc bytecode class từ runtime resource khi được cung cấp.
}
```

Đây là snippet minh họa, không tự biên dịch nếu thiếu các imports/phương thức xử lý exception. Với bytecode chuẩn, 4 byte đầu thường là magic `CA FE BA BE`, nhưng đọc stream resource chỉ nên dùng để minh họa, không thay cho API reflection khi cần metadata của class.

### JRT FileSystem khác File

JDK có thể cung cấp provider **JRT FileSystem** của NIO. Khi provider này khả dụng, bạn có thể thao tác với `Path` thuộc filesystem `jrt:`:

```java
URI uri = URI.create(
        "jrt:/java.base/java/lang/String.class");

Path path = Path.of(uri);
byte[] bytes = Files.readAllBytes(path);
```

Đây là đoạn minh họa cho JDK hỗ trợ `jrt:` provider. `path` là đường dẫn **trên filesystem ảo của runtime image**, không phải đường dẫn `File` trên filesystem mặc định. Đừng chuyển nó thành `path.toFile()` và kỳ vọng thành công; NIO `Path.toFile()` có thể ném `UnsupportedOperationException` với filesystem không phải default provider.

Với custom runtime tối giản hoặc môi trường không có provider phù hợp, `Path.of(jrtUri)` có thể thất bại. Khi chỉ đọc resource của class hiện có, cách ít phụ thuộc hơn vẫn là `getResourceAsStream` hoặc `URL.openStream`.

## 5. Thí nghiệm Java 17+: cùng một resource tạo ra file: hoặc jar:

Ví dụ dưới đây tạo **một chương trình Java duy nhất** và một tệp resource. Chạy lần thứ nhất với thư mục `classes`; chạy lần thứ hai bằng `app.jar`. Nội dung resource không đổi, nhưng protocol URL khác vì cấu trúc triển khai khác.

Tạo cây:

```text
resource-demo/
├── src/
│   └── demo/
│       └── ResourceSchemesDemo.java
└── classes/
    └── demo/
        └── data/
            └── message.txt
```

Nội dung **`src/demo/ResourceSchemesDemo.java`**:

```java
package demo;

import java.io.InputStream;
import java.net.JarURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ResourceSchemesDemo {
    public static void main(String[] args) throws Exception {
        URL resource = ResourceSchemesDemo.class
                .getResource("data/message.txt");
        if (resource == null) {
            throw new IllegalStateException("Missing demo resource");
        }

        URL runtime = String.class.getResource("String.class");
        if (runtime == null) {
            throw new IllegalStateException("Missing runtime class resource");
        }

        System.out.println("Application protocol: "
                + resource.getProtocol());
        System.out.println("Runtime protocol: "
                + runtime.getProtocol());

        try (InputStream stream = resource.openStream()) {
            String message = new String(
                    stream.readAllBytes(), StandardCharsets.UTF_8);
            System.out.println("Message: " + message.trim());
        }

        if ("file".equals(resource.getProtocol())) {
            Path file = Path.of(resource.toURI());
            System.out.println("File exists: "
                    + Files.exists(file));
        } else if ("jar".equals(resource.getProtocol())) {
            JarURLConnection connection =
                    (JarURLConnection) resource.openConnection();
            System.out.println("JAR entry: "
                    + connection.getEntryName());
        }
    }
}
```

Trên **Bash** (Linux/macOS/Git Bash), trong thư mục `resource-demo`, tạo tệp, biên dịch và chạy:

```bash
mkdir -p classes/demo/data
printf 'Hello resource!\n' > classes/demo/data/message.txt

javac --release 17 -d classes src/demo/ResourceSchemesDemo.java
java -cp classes demo.ResourceSchemesDemo
```

Đầu ra trên JDK 17+ tiêu chuẩn khi chạy từ thư mục:

```text
Application protocol: file
Runtime protocol: jrt
Message: Hello resource!
File exists: true
```

Đóng gói rồi chạy chương trình từ JAR:

```bash
jar --create --file app.jar -C classes .
java -cp app.jar demo.ResourceSchemesDemo
```

Đầu ra:

```text
Application protocol: jar
Runtime protocol: jrt
Message: Hello resource!
JAR entry: demo/data/message.txt
```

Đây là **ví dụ đã kiểm chứng bằng cách biên dịch với `javac --release 17` và chạy hai chế độ** trên JDK có JRT. Lệnh `jar --create` đưa cả `demo/ResourceSchemesDemo.class` và `demo/data/message.txt` vào archive.

Vì không khai báo `Main-Class` trong manifest, bài thử **dùng `java -cp app.jar demo.ResourceSchemesDemo`**, không dùng `java -jar app.jar`. `java -jar` là chế độ khác và cần entry point trong manifest.

Nếu chạy trong môi trường đã có một resource cùng tên ở vị trí ưu tiên khác trên classpath, một custom class loader hoặc packaging đặc biệt, URL có thể khác. Hãy quan sát `getProtocol()` thay vì gắn cứng xử lý dựa trên tên file.

### Chạy trên PowerShell

Đối với Windows PowerShell, thay hai dòng tạo thư mục và tệp bằng:

```powershell
New-Item -ItemType Directory -Force -Path classes/demo/data | Out-Null
[System.IO.File]::WriteAllText(
    "classes/demo/data/message.txt",
    "Hello resource!" + [Environment]::NewLine,
    [System.Text.UTF8Encoding]::new($false)
)
```

Sau đó chạy cùng lệnh `javac`, `java`, `jar` như phần Bash. Đường dẫn `classes/demo/data` được Java và công cụ JDK hiểu trên Windows; phần code Java luôn dùng `/` trong resource name.

## 6. Quy tắc an toàn: đọc resource từ stream, không giả định File

Một method tái sử dụng được cho classpath resource nhỏ:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class ResourceText {
    private ResourceText() {
    }

    public static String read(String name) throws IOException {
        try (InputStream input =
                ResourceText.class.getResourceAsStream(name)) {
            if (input == null) {
                throw new IOException("Resource not found: " + name);
            }
            return new String(input.readAllBytes(),
                    StandardCharsets.UTF_8);
        }
    }
}
```

Tệp **`ResourceText.java`** này có thể biên dịch bằng:

```bash
javac --release 17 ResourceText.java
```

Nó là utility class **không chứa `main`**, nên không phải chương trình độc lập có stdout. Caller có thể dùng `ResourceText.read("/demo/data/message.txt")` nếu resource đó nằm trong classpath/module và có thể truy cập theo các quy tắc tương ứng.

Ưu điểm:

- Không cần hỏi nguồn là `file:` hay `jar:`.
- Không cần trích xuất resource ra thư mục tạm.
- Khi đổi cách packaging từ `classes` sang JAR, code đọc resource giữ nguyên.
- `try-with-resources` đảm bảo đóng stream khi đọc xong.

Hạn chế:

- `readAllBytes()` không phù hợp với resource rất lớn hoặc không tin cậy; dùng đọc theo buffer/stream và giới hạn dung lượng.
- `getResourceAsStream` trả `null` nếu không tìm được/không được phép truy cập; phải kiểm tra.
- Nếu cần chỉnh sửa dữ liệu, resource nhúng trong JAR không nên được dùng làm nơi lưu. Hãy chọn một external `Path` (file cấu hình, thư mục dữ liệu, database...) rồi đọc/ghi qua `Files`.
- Với tài nguyên remote hoặc loader riêng, việc mở stream có thể có lỗi I/O/network; cần chính sách timeout, logging và bảo vệ nguồn đầu vào phù hợp.

Một quy tắc thực tế: **classpath resource chủ yếu là tài sản đọc-only của ứng dụng** (template, schema, ảnh, cấu hình mặc định). Dữ liệu người dùng hoặc state ứng dụng nên được quản lý riêng khỏi JAR.

## 7. Nếu buộc phải có Path bên trong JAR: ZIP FileSystem

Java NIO hỗ trợ filesystem provider cho ZIP/JAR thông qua module `jdk.zipfs` trong các JDK có cung cấp nó. Khi cần dùng các API `Files` với entry bên trong JAR, có thể chủ động **mở ZIP filesystem** thay vì ép resource URL thành `File`.

Ví dụ minh họa (archive là local file):

```java
import java.net.URI;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class ZipFsExample {
    public static void main(String[] args) throws Exception {
        Path archive = Path.of("app.jar").toAbsolutePath();
        URI zipUri = URI.create("jar:" + archive.toUri());

        try (FileSystem fs =
                     FileSystems.newFileSystem(zipUri, Map.of())) {
            Path entry = fs.getPath("/demo/data/message.txt");
            System.out.println(Files.readString(entry).trim());
        }
    }
}
```

Đây là ví dụ bổ sung **có `main`**, yêu cầu có `app.jar` từ thí nghiệm trước, `jdk.zipfs` có sẵn và entry tương ứng tồn tại. Biên dịch bằng `javac --release 17 ZipFsExample.java`, chạy `java ZipFsExample` từ thư mục có `app.jar` sẽ in:

```text
Hello resource!
```

Đặc điểm:

- `FileSystems.newFileSystem` tạo/mở **filesystem ảo** gắn với archive. `entry` là `Path` **bên trong ZIP filesystem**, không phải `File` của hệ điều hành.
- Cần đóng `FileSystem` khi xong, và lưu ý lifecycle/caching khi nhiều thành phần dùng cùng một archive. Đóng filesystem trong khi code khác còn dùng `Path` có thể dẫn tới lỗi.
- Không tự động hỗ trợ mọi scheme `jar:` (ví dụ URL của JAR remote, nested JAR theo framework riêng). Với các trường hợp đó, các giao thức/loader chuyên dụng cần xử lý riêng.
- Trích xuất entry ra file tạm cũng là phương án nếu thư viện bắt buộc nhận `File`, nhưng phải quản lý vòng đời và quyền truy cập file tạm, không nhầm vị trí đó là nguồn resource gốc.

Với nhu cầu chỉ đọc vài byte hoặc parse text/JSON, **stream vẫn đơn giản hơn ZipFileSystem**.

## 8. Khi thư viện bắt buộc nhận File thì làm gì?

Một số API cũ yêu cầu tham số `java.io.File` thay vì `InputStream`. Có ba phương án:

| Nhu cầu | Cách triển khai |
|---|---|
| Có thể sửa API hoặc chọn overload khác | Ưu tiên API nhận `InputStream`, `Reader`, `URL` hoặc `ByteBuffer` |
| URL thực sự là local `file:` | Kiểm tra scheme, chuyển `url.toURI()` → `Path.of(uri)` → `path.toFile()` trên filesystem mặc định |
| Resource nằm trong JAR/JRT nhưng API chỉ nhận `File` | Tạo bản sao ra file tạm có quản lý, hoặc chuyển sang thư viện nhận stream; không ép URL đặc biệt thành `File` |

Ví dụ copy ra file tạm:

```java
URL resource = MyApp.class.getResource("/assets/report-template.bin");
if (resource == null) {
    throw new IllegalStateException("Missing template");
}

Path temp = Files.createTempFile("report-template-", ".bin");
try {
    try (InputStream in = resource.openStream()) {
        Files.copy(in, temp,
                java.nio.file.StandardCopyOption.REPLACE_EXISTING);
    }

    legacyApiThatRequiresFile(temp.toFile());
} finally {
    Files.deleteIfExists(temp);
}
```

Đây là **đoạn minh họa**, không độc lập vì cần `MyApp`, `legacyApiThatRequiresFile(...)` và các imports phù hợp. Trong production:

- Nếu legacy API giữ file sau khi method trả về, **không xóa quá sớm**.
- Chú ý quyền đọc file tạm, dữ liệu bí mật và cleanup kể cả khi có exception.
- Không để tên file tạm có thể bị dự đoán/ghi đè bởi nguồn không tin cậy.
- Với tài nguyên rất lớn, cân nhắc streaming và giới hạn dung lượng.
- Việc dùng `deleteOnExit()` không thay thế quản lý file temp dài hạn ở server process.

## 9. Ngoại lệ và lỗi hay gặp

| Hiện tượng | Nguyên nhân điển hình | Cách khắc phục |
|---|---|---|
| `getResource(...) == null` | Tên resource sai, sai prefix `/`, resource không đóng gói, module access | Kiểm tra name, loader và entry thực tế |
| `new File(url.toURI())` ném `IllegalArgumentException` | URL là `jar:` hoặc `jrt:`, không phải `file:` | Dùng stream hoặc provider phù hợp |
| `Path.of(jarUri)` ném `FileSystemNotFoundException` | Chưa mở JAR filesystem cho URI | Mở ZIP filesystem có quản lý hoặc đọc qua stream |
| File tồn tại nhưng `Files.readString` báo không tìm thấy | Dùng `new File(url.getFile())` với `%20`/URL-encoding, path sai | Dùng `Path.of(url.toURI())` cho `file:` URI |
| `FileSystemProviderNotFoundException` / `ProviderNotFoundException` | Provider cho scheme cần dùng không hiện diện | Kiểm tra runtime image/module/provider; fallback stream |
| `UnsupportedOperationException` từ `Path.toFile()` | Path thuộc filesystem ảo không phải filesystem mặc định | Dùng `Files` trên Path, không buộc thành File |
| `IOException` khi `openStream()` | Tài nguyên không đọc được, archive lỗi, remote I/O, permission | Xử lý I/O và đóng stream, không tự giả định thiếu class |
| Trên IDE chạy được, đóng JAR lại lỗi | Resource không được copy vào JAR, code giả định file trên disk | Kiểm tra archive, thay đọc File bằng stream |
| `jrt:` không truy cập được trên môi trường tối giản | Provider/resource/runtime image khác biệt | Dùng APIs cho module/resource phù hợp, tránh hardcode filesystem |

*Ghi chú tên lỗi:* Với Java 17, lớp exception về filesystem provider tên là `java.nio.file.ProviderNotFoundException`. Hãy dùng đúng tên này trong code; cụm `FileSystemProviderNotFoundException` đôi khi chỉ là cách diễn giải không chính thức, **không phải tên một exception class chuẩn**.

## 10. Một số trường hợp đặc biệt trong hệ sinh thái Java

### Named modules và resource encapsulation

Trên Java 9+, class loader resource lookup còn bị chi phối bởi **module encapsulation**. Với `ClassLoader.getResource`, tài nguyên **không kết thúc bằng `.class`** trong package của một named module thường chỉ có thể được trả về khi package được `opens` vô điều kiện, theo quy tắc API. Do đó `null` không luôn có nghĩa file không tồn tại.

`Class.getResource` và `Module.getResourceAsStream` cũng có những quy tắc tương ứng về resource trong module. Khi cần tài nguyên nội bộ của module, hãy cân nhắc API phù hợp và các quyền truy cập được quy định; không cố sửa bằng cách coi `jrt:` URL là đường dẫn file vật lý.

### Nested JAR và framework packaging

Một ứng dụng đóng gói theo framework có thể chứa JAR lồng bên trong, ví dụ `BOOT-INF/lib/dependency.jar`. URL do custom class loader trả về có thể là dạng đặc biệt hoặc cấu trúc phức tạp hơn `jar:file:...!/entry` thông thường.

Đừng viết parser URL thủ công kiểu:

```java
String path = url.toString().split("!/")[0];
```

Cách này bỏ qua URL encoding, multiple layers, nguồn remote và khác biệt giữa loader implementations. Nếu chỉ đọc tài nguyên, dùng `openStream()`. Nếu cần xác định archive thật, sử dụng API chính thức của framework/loader hoặc `JarURLConnection` khi URL đúng giao thức JAR chuẩn.

### HTTP, dữ liệu sinh động và resource không phải file

Không phải mọi loader chỉ đọc từ filesystem. Loader tùy biến có thể trả `http:`, `https:` hoặc protocol khác. Trong trường hợp đó, tạo `File` là vô nghĩa. URL protocol cũng không có cam kết nhất quán giữa các class loader plugins; resource có thể được sinh trong bộ nhớ hoặc cung cấp qua API riêng.

### Phân biệt class resource và đường đến JAR đang chạy

`MyApp.class.getResource("MyApp.class")` thường trả URL chỉ tới **entry .class** hoặc file .class cụ thể, không phải đường filesystem chứa ứng dụng. Nếu bạn muốn nơi lưu dữ liệu bên cạnh chương trình đang chạy, đừng bắt đầu bằng cách cắt chuỗi resource URL: cách đóng gói và class loader có thể thay đổi. Hãy dùng cấu hình ngoài, working directory có kiểm soát hoặc API deployment chính thức.

`ProtectionDomain.getCodeSource().getLocation()` đôi khi cho URL của JAR hoặc thư mục nguồn nạp code, nhưng có thể `null` hoặc không phản ánh ý nghĩa deployment bạn cần, đặc biệt với module system/custom loaders. Nó không thay thế một cấu hình rõ ràng cho đường dẫn dữ liệu.

## 11. Checklist chọn API đúng

Khi xử lý một resource, tự hỏi:

1. **Mình muốn đọc nội dung hay cần đường dẫn filesystem?** Nếu đọc, dùng `getResourceAsStream`/`openStream`.
2. **Tên tài nguyên đúng kiểu chưa?** `Class.getResource` có tương đối package; `ClassLoader.getResource` yêu cầu tên không có `/` đầu.
3. **Resource có thể là null không?** Luôn kiểm tra và báo lỗi dễ hiểu.
4. **Scheme thực tế là gì?** Quan sát `url.getProtocol()`, không suy đoán từ IDE hoặc tên file.
5. **Nếu là `file:`**, đã chuyển `url.toURI()` sang `Path` qua provider tương ứng, thay vì tự decode chuỗi?
6. **Nếu là `jar:`**, có thật cần `Path` không? Stream có thể đủ; ZIP filesystem chỉ dùng khi API cần thao tác với entries.
7. **Nếu là `jrt:`**, có hiểu đó là runtime image ảo, không phải `rt.jar` hoặc file vật lý?
8. **Nếu dùng JPMS**, package/resource có được phép truy cập qua API đang gọi không?
9. **Nếu cần File cho thư viện cũ**, đã quản lý file tạm, bảo mật và cleanup phù hợp?
10. **Đã kiểm tra cả chạy từ thư mục và chạy từ JAR chưa?** Hai cấu hình thường phơi bày các giả định sai về đường dẫn.

## 12. Tự kiểm tra kiến thức

**1. `getResource("config.txt")` trả `URL` có nghĩa resource là một file thật trên disk?** Không. URL có thể là `file:`, `jar:`, `jrt:` hoặc scheme khác.

**2. Vì sao `new File(url.getFile())` không nên dùng ngay với file URL có khoảng trắng?** Vì thành phần URL có thể chứa `%20`, không tương đương tên filesystem đã được giải mã đúng.

**3. URL `jar:file:/app/app.jar!/demo/config.txt` trỏ tới đâu?** Entry `demo/config.txt` **bên trong** archive `app.jar`. Không có file thông thường độc lập ở đường dẫn đó.

**4. `new File(jarUrl.toURI())` có hợp lệ không?** Không cho JAR URI: constructor `File(URI)` yêu cầu file URI phù hợp.

**5. `Path.of(jrtUri)` có thể sử dụng trong JDK hỗ trợ `jrt:` provider không?** Có, nhưng đó là `Path` thuộc JRT filesystem ảo; không mặc nhiên đổi được sang `java.io.File`.

**6. Tại sao đọc một resource bằng stream tốt hơn việc ép thành File?** Stream dùng được với nhiều protocol, đóng gói JAR hoặc thư mục, giảm coupling với filesystem layout.

**7. `ClassLoader.getResource("/demo/config.txt")` có giống `Class.getResource("/demo/config.txt")` không?** Không. `ClassLoader.getResource` dùng tên resource không bắt đầu `/`; `Class.getResource` có quy tắc xử lý `/` đầu riêng.

**8. Khi resource nằm trong named module, `getResource` trả null có chắc resource bị thiếu?** Không. Có thể do quy tắc module encapsulation hoặc quyền truy cập resource.

**9. Tại sao IDE chạy được nhưng executable JAR báo lỗi FileNotFoundException?** Code có thể đang dùng `new File(...)` giả định resource được triển khai dưới dạng filesystem file, trong khi sau packaging nó thành JAR entry.

**10. Nếu thư viện bắt buộc nhận File với resource nhúng JAR, cách tiếp cận hợp lý là gì?** Ưu tiên overload nhận stream nếu có; nếu không có, copy resource vào file tạm với quản lý vòng đời và bảo mật phù hợp.

## 13. Tài liệu chuẩn

- Java SE 17 API, `ClassLoader.getResource/getResourceAsStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 API, `Class.getResource/getResourceAsStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 API, `JarURLConnection` (cú pháp URL `jar:` và metadata): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/JarURLConnection.html
- Java SE 17 API, `File(URI)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/File.html
- Java SE 17 API, `Path.of(URI)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html
- Java SE 17 API, `FileSystems` và ZIP filesystem provider: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystems.html
- JEP 220, *Modular Run-Time Images* (thay đổi từ `rt.jar` sang runtime image): https://openjdk.org/jeps/220

**Ghi nhớ:** `file:` thường có thể chuyển thành `Path` trên filesystem tương ứng; `jar:` chỉ một entry trong archive; `jrt:` chỉ nội dung runtime image theo module. **URL resource không đồng nghĩa với `File`.** Khi chỉ cần đọc nội dung, hãy dùng stream để code tiếp tục hoạt động khi ứng dụng đổi từ thư mục classes sang JAR hoặc Java runtime module.
