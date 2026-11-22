# findResource, findResources và điểm mở rộng cho ClassLoader tùy chỉnh

## 1. Khi class nạp được nhưng tài nguyên vẫn “không tìm thấy”

Ứng dụng Java thường đóng gói cùng bytecode các tài nguyên như tệp `.properties`, mẫu HTML, JSON, ảnh, chứng chỉ công khai, metadata `META-INF/services/...` hoặc cấu hình plugin. Nạp được `com.example.Plugin` **không bảo đảm** tìm được `config/settings.properties`: cơ chế tìm **class** và cơ chế tìm **resource** có các API, đường tìm và quyền truy cập riêng.

Giả sử đoạn mã chạy:

```java
ClassLoader loader = Plugin.class.getClassLoader();
java.net.URL url = loader.getResource("plugin/settings.properties");
```

Đây là snippet minh họa, giả định `Plugin` đã được định nghĩa. Khi `url == null`, trước khi kết luận “quên đóng gói file”, cần kiểm tra **tên resource**, **loader được dùng**, **delegation**, liệu loader tùy chỉnh có cung cấp `findResource`/`findResources` hay không, và ranh giới của **named module**.

Bài này tập trung vào **hai điểm mở rộng**:

- `protected URL findResource(String name)`: tìm **một URL** tới resource tại nguồn mà class loader tùy chỉnh quản lý.
- `protected Enumeration<URL> findResources(String name) throws IOException`: tìm **toàn bộ URL** tương ứng trong nguồn cục bộ của loader, thường phục vụ việc gom nhiều file cấu hình hoặc provider descriptor.

Chúng kết hợp với các phương thức **public** `getResource`, `getResources`, `resources` và `getResourceAsStream`. Hiểu rõ sự khác nhau này là điều kiện để thiết kế loader plugin nhất quán.

## 2. Bản đồ API: người dùng gọi gì, loader override gì?

| API | Phạm vi/chức năng | Kết quả khi không tìm thấy | Có thể override ở custom loader? |
| --- | --- | --- | --- |
| `ClassLoader.getResource(name)` | Tra một resource bằng thuật toán delegation mặc định: parent trước, local sau | `null` | Có, nhưng thường **không cần** nếu chỉ muốn đổi nguồn local |
| `ClassLoader.getResources(name)` | Gom resource từ parent, sau đó từ `findResources` local | `Enumeration` rỗng | Có; phải bảo đảm thứ tự nhất quán với `getResource` |
| `ClassLoader.resources(name)` (Java 9+) | `Stream<URL>` từ cơ chế nhiều resource; thường lazy | Stream rỗng | Có nhưng không cần nếu `getResources` đã đúng |
| `ClassLoader.getResourceAsStream(name)` | Lấy `InputStream` để đọc resource đầu tiên | `null` | Có; thường không cần nếu `getResource` đúng |
| `protected findResource(name)` | Điểm mở rộng local để tìm **một URL** | `null` | **Có — nơi custom loader thường implement** |
| `protected findResources(name)` | Điểm mở rộng local để tìm **nhiều URL** | Enumeration rỗng | **Có — phải implement nếu cần nhiều resource local** |
| `ClassLoader.getSystemResource(name)` | Tìm resource thông qua system class loader | `null` | Phương thức static; không thay thế resource lookup của plugin |
| `Class.getResource(name)` | Tìm theo ngữ cảnh package của chính class (khác quy tắc tên dưới đây) | `null` | Đây là API của `Class`, không phải extension point của `ClassLoader` |
| `Module.getResourceAsStream(name)` | Tìm resource trong một module cụ thể, có kiểm tra đóng gói module | `null` | Không thay thế trách nhiệm của loader hỗ trợ module |

**Mặc định trong JDK 17:**

- `ClassLoader.findResource(String)` trả `null`.
- `ClassLoader.findResources(String)` trả enumeration **không có phần tử**.
- `ClassLoader.getResource(String)` tìm parent trước; chỉ khi parent không tìm thấy mới gọi `findResource(String)`.
- `ClassLoader.getResources(String)` gom danh sách từ parent trước rồi thêm các URL do `findResources(String)` local cung cấp.
- `ClassLoader.resources(String)` mặc định gọi `getResources` và biến enumeration thành stream; `IOException` xảy ra khi xử lý stream có thể được bọc trong `UncheckedIOException`.

**Hệ quả dễ bỏ sót:** override **chỉ** `findResource` có thể làm `getResource` tìm được file cục bộ, trong khi `getResources` vẫn **không nhìn thấy** file đó nếu `findResources` của lớp con chưa được override. Hai điểm mở rộng độc lập; không nên mặc định `findResources` của `ClassLoader` sẽ gọi `findResource` giúp bạn.

## 3. Luồng delegation: getResource và getResources không tương đương

Giả sử parent và child cùng chứa file `demo/config.properties`:

```text
Root / ParentLoader
    └── demo/config.properties   (version: parent)

Plugin / ChildLoader
    └── demo/config.properties   (version: child)
```

Với việc giữ nguyên public API mặc định:

```text
child.getResource("demo/config.properties")
    ├── parent.getResource(...)          -> tìm thấy ở parent
    └── child.findResource(...)          -> KHÔNG cần gọi
Kết quả: URL của parent
```

Ngược lại:

```text
child.getResources("demo/config.properties")
    ├── parent.getResources(...)         -> URL của parent
    └── child.findResources(...)         -> URL của child
Kết quả: Enumeration [parent URL, child URL]
```

Điều này có hai mục đích:

1. **`getResource` chọn một nguồn phù hợp** với chiến lược parent-first.
2. **`getResources` cho phép khám phá nhiều nguồn** cùng tên, chẳng hạn nhiều JAR mỗi JAR cung cấp file `META-INF/services/com.example.spi.Plugin`.

Thứ tự parent trước local là hợp đồng của implementation mặc định. Một framework có thể **override** `getResource`/`getResources` để áp dụng child-first theo namespace, nhưng khi làm thế phải duy trì **tính nhất quán**: resource đầu tiên từ `getResources(name)` nên giống resource mà `getResource(name)` chọn cho cùng tên khi cùng điều kiện truy cập.

**Lưu ý:** `getResources` là enumeration, không phải `List` đã gộp và khử trùng; cùng một nội dung có thể xuất hiện từ nhiều vị trí. Cần tự định nghĩa cách xử lý nhiều cấu hình trùng nhau, không mặc định “JVM chỉ trả bản mới nhất”.

## 4. Tên resource: dấu /, package, classpath root

Java xác định tên resource của `ClassLoader` bằng **đường dẫn có dấu `/`**, không phải binary name của class:

| Muốn tìm | Tên truyền cho `ClassLoader.getResource` |
| --- | --- |
| Config tại root classpath `application.properties` | `"application.properties"` |
| Config thuộc package `com.acme` | `"com/acme/settings.properties"` |
| Service descriptor | `"META-INF/services/com.acme.spi.Plugin"` |
| Class file trong nguồn classpath | `"com/acme/Plugin.class"` (nhưng tra file class không đồng nghĩa dùng API nạp class) |

Với **`ClassLoader.getResource`**, không thêm dấu `/` đầu tên: dùng `"com/acme/config.properties"`. Với **`Class.getResource`**, quy tắc khác:

- `SomeClass.class.getResource("config.properties")`: tìm tương đối **theo package của SomeClass**.
- `SomeClass.class.getResource("/com/acme/config.properties")`: tên tuyệt đối từ root; dấu `/` đầu bị loại trước khi chuyển sang tra cứu.
- `SomeClass.class.getResourceAsStream(...)` giữ quy tắc tên tương ứng.

Ví dụ minh họa trong class `com.acme.SomeClass`:

```java
java.net.URL viaClassRelative =
        SomeClass.class.getResource("config.properties");

java.net.URL viaClassAbsolute =
        SomeClass.class.getResource("/com/acme/config.properties");

java.net.URL viaLoader =
        SomeClass.class.getClassLoader()
                .getResource("com/acme/config.properties");
```

Đây là snippet minh họa, giả định class và file resource thật sự tồn tại. Với một **unnamed module**, ba cách này thường tra tới cùng tài nguyên ở cùng package nếu cấu hình classpath phù hợp; với **named module**, đường tra và quy tắc encapsulation có thể khác, cần xem phần JPMS.

**Không truyền** `"com.acme.config.properties"` nếu file thực tế có tên `com/acme/config.properties`. Không dùng `File.separator` thay `/` để đặt tên resource trong JAR.

### Trong JAR, resource không nhất thiết là file thường trên đĩa

Nếu resource nằm trong JAR, URL có thể có dạng `jar:file:/.../plugin.jar!/demo/config.properties`. Nếu nằm trên module image hoặc do loader tùy chỉnh cấp, nó có thể không phải `file:` hay `jar:file:`.

Vì vậy dùng `url.openStream()` hoặc `getResourceAsStream()` để đọc, và đóng stream bằng try-with-resources. Đừng tự ép `new File(url.toURI())` cho mọi loại URL vì đường `jar:` không phải đường file thường và URL có thể sử dụng giao thức đặc biệt.

## 5. Chương trình Java 17 hoàn chỉnh: hai loader, hai nguồn tài nguyên

Ví dụ này thực sự xây dựng **hai loader có quan hệ parent-child**, trong đó cả hai có tài nguyên trùng tên. Ta override **cả** `findResource` và `findResources` để kết quả đơn/nhiều cùng nhất quán. Không cần Maven, Gradle, JAR ngoài hay kết nối mạng.

Tạo file `ResourceLookupDemo.java`:

```java
import java.io.IOException;
import java.io.InputStream;
import java.net.MalformedURLException;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Enumeration;
import java.util.List;

public class ResourceLookupDemo {

    private static final String CONFIG =
            "lesson_resource_demo_2026/config.txt";

    static final class DirectoryResources extends ClassLoader {
        private final Path root;

        DirectoryResources(Path directory, ClassLoader parent) {
            super(parent);
            this.root = directory.toAbsolutePath().normalize();
        }

        private Path localPath(String name) {
            // Bài thực hành chỉ dùng các tên resource kiểm soát được.
            if (name.startsWith("/")
                    || name.indexOf('\\') >= 0
                    || name.contains("..")) {
                return null;
            }
            Path candidate = root.resolve(name).normalize();
            return candidate.startsWith(root) ? candidate : null;
        }

        @Override
        protected URL findResource(String name) {
            Path file = localPath(name);
            if (file == null || !Files.isRegularFile(file)) {
                return null;
            }
            try {
                return file.toUri().toURL();
            } catch (MalformedURLException e) {
                return null;
            }
        }

        @Override
        protected Enumeration<URL> findResources(String name)
                throws IOException {
            URL local = findResource(name);
            if (local == null) {
                return Collections.emptyEnumeration();
            }
            return Collections.enumeration(List.of(local));
        }
    }

    private static String read(URL url) throws IOException {
        try (InputStream in = url.openStream()) {
            return new String(in.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
        }
    }

    public static void main(String[] args) throws Exception {
        Path temp = Files.createTempDirectory("resource-lookup-");
        Path parentRoot = temp.resolve("parent");
        Path childRoot = temp.resolve("child");
        Path parentFile = parentRoot.resolve(CONFIG);
        Path childFile = childRoot.resolve(CONFIG);

        try {
            Files.createDirectories(parentFile.getParent());
            Files.createDirectories(childFile.getParent());
            Files.writeString(parentFile, "PARENT\n");
            Files.writeString(childFile, "CHILD\n");

            DirectoryResources parent = new DirectoryResources(
                    parentRoot,
                    ClassLoader.getPlatformClassLoader());
            DirectoryResources child = new DirectoryResources(
                    childRoot, parent);

            URL first = child.getResource(CONFIG);
            System.out.println("getResource=" + read(first));

            Enumeration<URL> urls = child.getResources(CONFIG);
            List<String> values = new ArrayList<>();
            while (urls.hasMoreElements()) {
                values.add(read(urls.nextElement()));
            }
            System.out.println("getResources=" + values);

            System.out.println("missing="
                    + (child.getResource(
                            "lesson_resource_demo_2026/missing.txt")
                            == null));
            System.out.println("leadingSlash="
                    + (child.getResource("/" + CONFIG) == null));
        } finally {
            Files.deleteIfExists(parentFile);
            Files.deleteIfExists(childFile);
            Files.deleteIfExists(parentFile.getParent());
            Files.deleteIfExists(childFile.getParent());
            Files.deleteIfExists(parentRoot);
            Files.deleteIfExists(childRoot);
            Files.deleteIfExists(temp);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ResourceLookupDemo.java
java ResourceLookupDemo
```

**Stdout chính xác trong điều kiện chạy chuẩn**, khi platform loader không có resource trùng tên của bài thực nghiệm:

```text
getResource=PARENT
getResources=[PARENT, CHILD]
missing=true
leadingSlash=true
```

**Cách đọc kết quả:**

1. `child.getResource(CONFIG)` hỏi parent trước. Parent có `CONFIG`, nên trả URL của parent: dòng `getResource=PARENT`.
2. `child.getResources(CONFIG)` gom enumeration từ parent và từ `findResources` của child; mỗi loader cung cấp một URL, nên thứ tự hiển thị là `[PARENT, CHILD]`.
3. Tên `missing.txt` không tồn tại ở platform/parent/child trong thí nghiệm, nên `getResource` trả `null`.
4. Tên resource bắt đầu bằng `/` không thuộc cách đặt tên mà `ClassLoader.getResource` mong đợi; `DirectoryResources.localPath` từ chối tên này, nên kết quả là `true`.
5. Mọi tài nguyên được đọc bằng `URL.openStream` và đóng bởi try-with-resources. Thư mục tạm cùng hai file đều được dọn ở `finally` sau khi không còn stream mở.

### Vì sao ví dụ dùng một method hỗ trợ localPath?

Resource có thể được đặt tên từ cấu hình, đường dẫn do người dùng nhập hoặc dữ liệu bên ngoài. Khi chuyển tên resource thành `Path`, cần tránh các tên dạng `../secret.txt` thoát khỏi root. Ví dụ áp dụng kiểm tra **lexical**: từ chối dấu `/` đầu, dấu `\\` và chuỗi `..`, sau đó chuẩn hóa và so sánh root.

**Giới hạn bảo mật cần hiểu đúng:** các kiểm tra lexical không đủ chống việc thư mục con trong root là **symbolic link** trỏ ra ngoài. Trong hệ thống thực sự xử lý tên resource không tin cậy, cần kiểm tra path thực tế, quyền truy cập, symlink policy, giới hạn file size và nguồn được phép trước khi đọc. Ví dụ hướng dẫn chỉ sử dụng file tự tạo và tên cố định.

### Nếu chỉ override findResource trong DirectoryResources?

`child.getResource(CONFIG)` vẫn có thể tìm parent, và một resource **chỉ ở child** có thể được tìm thấy bởi `findResource`. Nhưng `child.getResources(CONFIG)` **không tự gọi findResource để thu thập local URL**; nếu không override `findResources`, phiên bản mặc định cho phần local trả enumeration rỗng. Vì vậy mọi hệ thống cần liệt kê nhiều resource phải có triển khai `findResources` tương ứng.

## 6. Một hay nhiều tài nguyên: vì sao không nên “lấy đại URL đầu tiên”?

Có các trường hợp sử dụng khác nhau:

| Nhu cầu | Cách dùng gợi ý | Quy tắc xử lý |
| --- | --- | --- |
| Chỉ đọc một cấu hình với parent-first priority | `getResource` / `getResourceAsStream` | Xác định rõ nguồn nào có quyền ưu tiên |
| Liệt kê các descriptor cùng tên trong nhiều JAR | `getResources` | Duyệt toàn bộ URL, parse từng nguồn và xử lý lỗi riêng |
| Dùng API stream để lọc URL | `resources` | Có thể gặp `UncheckedIOException` khi đánh giá stream |
| Muốn ghi log mọi nơi cung cấp cấu hình | `getResources` | Không tự kết luận các URL trả về là duy nhất |
| Chỉ tìm nguồn local của loader tùy chỉnh | `findResource` / `findResources` trong subclass | Đây là protected extension point, không phải API public gọi từ khắp ứng dụng |

Ví dụ snippet hợp lệ khi đã có đối tượng `loader`:

```java
String name = "META-INF/services/com.acme.spi.Plugin";
Enumeration<URL> entries = loader.getResources(name);
while (entries.hasMoreElements()) {
    URL descriptor = entries.nextElement();
    try (InputStream in = descriptor.openStream()) {
        // Đọc đúng charset/định dạng của descriptor cần xử lý.
    }
}
```

Đây là snippet (chưa có `main`, giả định loader và các import), dùng để minh họa duyệt resource. Khi làm ServiceLoader thật, nên dùng `ServiceLoader` để framework xử lý giao thức provider descriptor hoặc khai báo `provides ... with ...` trong module, thay vì viết parser thủ công mà bỏ qua các quy tắc.

**Thứ tự không phải “độ mới phiên bản”.** Nếu nhiều JAR có `config.properties`, parent-first có thể trả file của parent trước dù child chứa bản mới hơn; nếu code chỉ lấy URL đầu tiên, bản của child sẽ không được sử dụng. Đây là chính sách của loader; cần thiết kế explicit nếu muốn ưu tiên plugin.

## 7. Khi cần child-first resource lookup

Một số hệ plugin cho phép thư viện của plugin dùng tài nguyên riêng dù parent có file trùng tên. Có thể chọn chính sách **child-first** cho một namespace resource cụ thể:

```text
getResource("plugin-private/config.yaml")
    -> tìm resource trong plugin trước
    -> nếu không có mới delegate lên parent
```

Tuy nhiên, override `getResource` mà **không** xử lý `getResources` cho nhất quán có thể tạo lỗi khó phát hiện:

- `getResource(name)` trả URL của child.
- `getResources(name)` tiếp tục trả parent trước.
- Một thư viện đọc resource đơn và một thư viện enumerate cùng tên nhận kết quả khác về ưu tiên.

Nếu có lý do thật sự cần child-first, thiết kế cả **hai API** để kết quả đầu của enumeration phản ánh cùng chính sách, kiểm tra cách tránh lặp URL và đảm bảo quyền truy cập vào parent khi phù hợp.

Ở nhiều ứng dụng, một biện pháp đơn giản hơn là đặt resource riêng vào namespace không xung đột, ví dụ `plugin-a/config.yaml` thay vì dùng chung `config.yaml` ở root. Điều này giảm sự phụ thuộc vào thứ tự JAR và delegation.

**Đừng thay đổi toàn bộ class loading sang child-first chỉ để sửa một resource.** Class loading ảnh hưởng danh tính kiểu, API/SPI và những package cần chia sẻ; hãy điều chỉnh resource lookup ở mức cần thiết.

## 8. Class resource và resource loader có thể khác nhau

Để lấy tài nguyên đi cùng một class, người ta thường chọn:

```java
InputStream stream =
        Plugin.class.getResourceAsStream("settings.properties");
```

Với class `Plugin` ở package `com.acme.plugin`, đây là cách tìm tương đối trong package ấy. Nếu code dùng:

```java
Plugin.class.getClassLoader()
        .getResourceAsStream("settings.properties");
```

nó lại tra resource ở **classpath root**. Sự khác biệt dấu `/` / package là nguyên nhân phổ biến dẫn đến `null`.

Hai yếu tố nữa:

1. `Class.getResource` lấy ngữ cảnh từ **class cụ thể** (và module của class đó, nếu là named module). Một thư viện ở loader cha không tự nhìn xuống mọi resource của plugin con.
2. `Thread.currentThread().getContextClassLoader()` (TCCL) là một loader được gắn trên thread, do code/framework quản lý. Một số API khám phá provider (như cách sử dụng `ServiceLoader` thông thường) có thể dựa vào TCCL, nhưng đổi TCCL **không làm thay đổi** defining loader của class đã nạp.

Khi giao tiếp host–plugin, ghi rõ nơi phải đặt descriptor `META-INF/services/...` và loader nào dùng để tìm. Nếu host chỉ dùng system loader mà resource nằm ở loader plugin, việc đóng gói đúng file vẫn chưa đủ.

Đặc biệt nếu code chạy trong thread pool, khi tạm đổi TCCL phải khôi phục trong `finally` để tránh để ngữ cảnh plugin tồn tại ngoài vòng đời tác vụ:

```java
ClassLoader old = Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    // Gọi API discovery dùng context class loader nếu cần.
} finally {
    Thread.currentThread().setContextClassLoader(old);
}
```

Đây là đoạn minh họa, giả định `pluginLoader` đã được tạo; không phải chương trình độc lập.

## 9. JPMS: named modules có thêm quy tắc nhìn thấy tài nguyên

Từ Java 9, cùng một class loader có thể định nghĩa class từ **nhiều module**. Việc đọc resource trong named module chịu **module encapsulation** ngoài delegation thông thường.

### 9.1. ClassLoader.getResource(s) và yêu cầu opens

Theo Java SE 17 API, `ClassLoader.getResource`, `getResources` và `resources` bị giới hạn khi tài nguyên nằm trong package của **named module**:

- Ngoại lệ cho resource có tên kết thúc bằng `.class` theo quy tắc API.
- Với resource **không phải `.class`** trong package của named module, các API này thông thường chỉ trả resource khi package ấy được **opened unconditionally**.
- `exports` phục vụ việc truy cập API/type của module; không đồng nghĩa với việc `opens` tất cả tài nguyên để truy cập qua class loader.
- Một resource không nằm trong package của named module có cách áp dụng quy tắc khác; không nên áp đặt máy móc rằng mọi resource của mọi named module đều phải mở package.

Vì vậy, file rõ ràng có trong module JAR nhưng `loader.getResource("com/acme/internal/settings.json")` vẫn có thể trả `null` do package không được mở vô điều kiện.

### 9.2. Class.getResource và Module.getResourceAsStream

Khi code có class thuộc named module:

- `SomeClass.class.getResource(...)` sử dụng ngữ cảnh module của class và delegation module-aware tương ứng.
- `Module.getResourceAsStream(name)` dùng module đích và thực hiện kiểm tra quyền truy cập theo caller module; một package có thể được mở **có điều kiện** tới module gọi.
- Không suy ra rằng `ClassLoader.getResource` sẽ cho kết quả tương tự với `Module.getResourceAsStream` trong tất cả cấu hình JPMS.

Class loader hỗ trợ định nghĩa module có protected overload:

```java
protected URL findResource(String moduleName, String name)
        throws IOException
```

Đây là chữ ký API (không phải chương trình độc lập). Overload này hỗ trợ tra resource thuộc module có tên, và là nền tảng cho những API của `Class`/`Module`. Implementation mặc định:

- Nếu `moduleName == null`, thử delegate về `findResource(String name)`.
- Nếu `moduleName != null`, trả `null`; loader tùy chỉnh thực sự hỗ trợ nhiều named modules nên override để tra đúng module.

Bản thân protected overload này không tự thi hành toàn bộ quy tắc encapsulation dành cho API của caller; người triển khai phải hiểu hợp đồng của từng điểm gọi.

**Không nên dùng `--add-opens` như một bản vá chung cho mọi lỗi resource lookup**: nhiều API `ClassLoader.getResource` yêu cầu **unconditional opens** theo hợp đồng, và nguyên nhân thực tế cũng có thể là đường dẫn resource, launcher, module path hoặc loader lựa chọn sai.

## 10. findResource so với findClass, và đóng gói resource

`findClass("com.acme.Plugin")` tìm hoặc định nghĩa bytecode của **class**. `findResource("com/acme/plugin.yaml")` tìm một **resource URL**. Không có hợp đồng nào bảo đảm override một phương thức làm phương thức còn lại tự hỗ trợ cùng nguồn dữ liệu.

Ví dụ, custom loader có thể đọc `plugin/Greeter.class` từ một database để gọi `defineClass`, nhưng nếu không triển khai resource lookup, `getResource("plugin/defaults.yaml")` vẫn có thể trả `null`.

Tương tự, `javac` **không tự động copy mọi file `.properties` hoặc `.json`** từ thư mục source sang output classes. Nhiều công cụ build có bước xử lý resources riêng:

- Maven thông thường copy `src/main/resources` vào output theo lifecycle resources, rồi đóng gói vào JAR.
- Gradle Java plugin thông thường xử lý `src/main/resources` qua `processResources` vào output resources phù hợp.
- Nếu dùng `javac` đơn lẻ, cần tự đưa resource vào đúng classpath root/JAR và xác minh cấu trúc bằng công cụ như `jar tf app.jar`.

Để resource `com/acme/config.properties` tra bằng `getResource("com/acme/config.properties")`, JAR phải có entry với đúng đường dẫn đó; đặt file ngoài JAR rồi dùng đường classpath sai root sẽ khiến lookup thất bại.

**Một số nguồn chỉ đọc được qua loader/framework riêng**, ví dụ nested JAR của một executable application framework; đừng suy luận mọi cấu trúc JAR đều tra được bằng `new File(url.getPath())`.

## 11. Những lỗi và ngoại lệ thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `getResource(name) == null` | Sai tên, thiếu resource, khác loader, JPMS chặn hoặc không có custom `findResource` | In tên resource, loader được dùng, kiểm tra JAR, module và path |
| `getResourceAsStream(name) == null` | Resource không tìm thấy/không thể mở theo hợp đồng | Kiểm tra cùng nguyên nhân như `getResource`, đừng dereference `null` |
| `getResource` tìm thấy nhưng `getResources` không thấy bản child | Override `findResource` nhưng chưa override `findResources` | Kiểm tra implementation của hai điểm mở rộng |
| `getResources` trả nhiều kết quả khác kỳ vọng | Có file trùng tên ở parent, nhiều JAR hoặc nhiều loader source | Duyệt URL, xem thứ tự delegation và quy tắc merge |
| `getResource` lấy cấu hình cũ | Parent-first đã chọn file parent | Tách namespace hoặc thiết kế priority phù hợp |
| `IOException` khi duyệt/đọc resource | Lỗi I/O từ `getResources` hoặc `URL.openStream` | Đọc cause, đóng stream, kiểm tra permission/nguồn |
| `UncheckedIOException` khi xử lý `resources(name)` stream | Lỗi I/O phát sinh ở quá trình đánh giá stream | Xử lý riêng hoặc dùng `getResources` phù hợp |
| `SecurityException` / không thấy URL | Quyền truy cập bị giới hạn bởi môi trường hoặc module | Đối chiếu SecurityManager cũ, permissions và module opening |
| ServiceLoader báo thiếu provider | Descriptor thiếu, sai tên SPI hoặc provider không load/không cast được | Kiểm tra `META-INF/services`, SPI defining loader, classpath/module path |
| Resource URL có `jar:` nên File API báo lỗi | Tài nguyên nằm trong JAR, không là file thường | Dùng `openStream` thay vì giả định file system path |
| Sau redeploy resource cũ vẫn xuất hiện | Loader cũ/cache hoặc classpath runtime chưa đổi | Kiểm tra loader sống, URL cache, vòng đời và tài nguyên đã deploy |

**Đọc nguyên nhân trước khi “sửa”.** Một resource có thể tồn tại đúng đường nhưng được lấy từ loader khác; thêm bản trùng tên vào classpath không tự giải quyết ưu tiên parent-first.

## 12. Thiết kế custom loader: tính nhất quán, hiệu năng và tài nguyên

### 12.1. Thứ tự và tính đầy đủ

Khi override `findResource` và `findResources`, cần quyết định:

1. **Nguồn local nào hợp lệ?** Thư mục, JAR, bộ nhớ, database hay endpoint được kiểm soát.
2. **Tên resource ánh xạ ra nguồn thế nào?** Chuẩn hóa `/`, package path và ngăn path traversal.
3. **Một resource có nhiều bản local không?** Nếu có, `findResources` phải có khả năng trả nhiều URL, không chỉ gọi `findResource` một lần như loader thư mục mẫu chỉ chứa tối đa một file cho mỗi tên.
4. **URL có mở được stream ổn định không?** Một URL chỉ “trông đúng” nhưng `openStream()` không hoạt động là một implementation thiếu hoàn chỉnh.
5. **Parent vs local ưu tiên ra sao?** Nếu override cả public API, bảo đảm `getResource` và phần tử đầu của `getResources` tương thích.
6. **Thời điểm enumerate và lifecycle:** nếu resources bị sửa/xóa ngay giữa quá trình tra và mở stream, `URL.openStream` có thể thất bại sau khi URL đã được trả về.

### 12.2. Xử lý dữ liệu không tin cậy

Không tin tưởng resource name được cấu hình bên ngoài: tránh đọc ngoài root, symlink escape, nguồn URL bất ngờ, file cực lớn và mô hình tải từ mạng thiếu timeout/giới hạn. Chỉ cấp quyền đọc tới những nguồn đã được thiết kế.

Trong bài ví dụ, override `findResource` trả `null` nếu không thể tạo URL, theo hợp đồng API. Với loader thực tế, hãy ghi log chẩn đoán phù hợp ở tầng ứng dụng (không lộ thông tin nhạy cảm) và xác định cách xử lý lỗi I/O, thay vì nuốt mọi exception làm việc tìm file bỗng nhiên “thành công rỗng”.

### 12.3. Tính đồng thời và cache

Nhiều thread cùng gọi `getResource` / `getResources` không tạo ra một khóa initialization lớp như `<clinit>`. Nếu loader có state mutable, cache, connection tới backend hoặc bộ đếm, cần cơ chế đồng bộ riêng thích hợp.

Với file/JAR có khả năng thay đổi sau khi khởi chạy, cache resource URL hoặc nội dung cần có chính sách invalidation rõ ràng. Không giả định JVM tự reload resource chỉ vì file đã được thay; một số framework snapshot hoặc cache ở tầng riêng.

### 12.4. Đóng loader và stream

Nếu dùng `URLClassLoader`, `close()` giải phóng tài nguyên loader quản lý (ví dụ các JAR handle), nhưng không bảo đảm class đã định nghĩa unload lập tức. Cần đóng `InputStream` riêng cho mỗi lần đọc. Nếu muốn reload plugin, thường phải kiểm soát vòng đời class loader, reference tới class/instance và cache/descriptor; không chỉ thay thế file trong JAR đang được dùng.

### 12.5. Không tự viết URL handler nếu không cần

Nếu resource đã nằm trong thư mục/JAR bình thường, `URLClassLoader` có triển khai tìm class/resource từ URL, do đó đa số trường hợp không cần tự override các method trên. Chỉ viết custom loader khi nguồn bytecode/resource khác biệt hoặc có yêu cầu policy đặc biệt; thêm một lớp tùy biến không cần thiết dễ làm mất các tính năng JAR/module mà runtime đã hỗ trợ.

## 13. Quy trình chẩn đoán resource không tìm thấy

1. **Ghi chính xác tên resource** được truyền, bao gồm dấu `/` đầu nếu có, chữ hoa/thường và vị trí package.
2. **Xác định API cụ thể**: `Class.getResource`, `ClassLoader.getResource` hay `getResources`? Chúng có quy tắc tên/tra khác.
3. **Xác định loader**: class đang chạy do loader nào định nghĩa; API dùng TCCL, system loader hay plugin loader?
4. **Xác minh resource thật trong artifact deploy**: với JAR dùng `jar tf file.jar`, đối chiếu entry name; với thư mục classes xem classpath root.
5. **Đọc tất cả kết quả** của `getResources` nếu có xung đột: URL nào xuất hiện trước, liệu parent có tài nguyên cùng tên không?
6. **Với custom loader, kiểm tra riêng từng điểm mở rộng** `findResource` / `findResources`. Lưu ý mặc định cả hai không tự đọc thư mục tùy biến.
7. **Với named modules, kiểm tra package đã opens hay chưa** và API cụ thể cần unconditional opens hay opening theo caller module.
8. **Đọc qua URL.openStream()**; nếu không đọc được dù URL tồn tại, phân biệt lỗi lookup với lỗi I/O khi mở.
9. **Kiểm tra vòng đời**: loader đóng chưa, thread context loader đang trỏ vào đâu, resource có bị xóa/cập nhật giữa chừng không?
10. **Làm smoke test bằng artifact chạy thật**, tránh chỉ kiểm tra resource tồn tại trong source tree mà không được copy vào output/JAR.

Snippet chẩn đoán dùng được trong ứng dụng nếu đã có `ClassLoader loader`:

```java
String name = "com/acme/config.properties";
System.out.println("first=" + loader.getResource(name));
Enumeration<URL> matches = loader.getResources(name);
int count = 0;
while (matches.hasMoreElements()) {
    System.out.println("match[" + count++ + "]="
            + matches.nextElement());
}
System.out.println("count=" + count);
```

Đây là **snippet**, cần import `java.net.URL`, `java.util.Enumeration` và xử lý `IOException` ở caller. URL in ra phục vụ chẩn đoán nguồn, tránh để URL chứa token hoặc đường dẫn nhạy cảm xuất hiện trong log sản xuất.

## 14. Những ngộ nhận thường gặp

**“Nạp được class tức các file .properties đi kèm chắc chắn cũng tìm được.”** Sai: class loading và resource lookup tách biệt. Class có thể được tạo từ bytecode mà loader không biết tìm file resource khác.

**“Override findResource là đủ cho cả getResource và getResources.”** Sai: `findResources` mặc định là enumeration rỗng, cần override khi muốn tìm nhiều resource local.

**“getResource và getResources luôn trả cùng một URL.”** Một API trả một URL, API kia trả có thể nhiều; với triển khai mặc định, URL đầu tiên của enumeration nên thống nhất với getResource trong điều kiện truy cập tương ứng.

**“Tên resource luôn phải có dấu / đầu.”** Với `ClassLoader.getResource`, tên theo đường dẫn resource không bắt đầu bằng slash; dấu `/` đầu là quy tắc đặc biệt của `Class.getResource` khi muốn absolute path.

**“findResource có thể trả về Path hoặc File.”** Chữ ký trả `URL`; có thể trỏ tới jar, file hoặc giao thức khác có thể mở stream, không nhất thiết là file.

**“Tên resource trong Java dùng File.separator của Windows.”** Tên tài nguyên theo API dùng `/`, không dùng `\\` giữa các segment.

**“Thấy đúng file trong module JAR thì loader.getResource chắc chắn trả URL.”** Named module có encapsulation; `ClassLoader.getResource` có thể yêu cầu package opened unconditionally cho resource không phải .class.

**“Không thấy provider thì chỉ cần thêm findClass.”** ServiceLoader discovery còn cần provider metadata đúng, resource lookup đúng và nhất quán SPI type identity.

**“Close URLClassLoader thì mọi stream đã mở tự đóng.”** Stream cần được đóng độc lập; lifecycle URL/JAR và class unloading là vấn đề khác.

## 15. Bài tập tự kiểm tra

**Câu 1.** Parent và child đều có `demo/config.properties`. Với delegation mặc định, `child.getResource` thường trả bản nào?

**Đáp án:** Bản parent, vì `getResource` hỏi parent trước và chỉ gọi `findResource` local khi parent không tìm thấy.

**Câu 2.** `child.getResources("demo/config.properties")` trả những gì nếu parent và child đều cung cấp và loader hỗ trợ findResources local?

**Đáp án:** Enumeration với các URL do parent trả trước, tiếp theo URL của child. Nội dung có thể trùng nhau nhưng API không tự quy tắc hóa theo phiên bản.

**Câu 3.** Custom loader chỉ override `findResource` và có resource riêng ở child. Tại sao `getResources` không thấy resource ấy?

**Đáp án:** Vì `getResources` gọi extension point `findResources` để thu thập URL local; `findResources` mặc định trả rỗng và không tự dùng `findResource`.

**Câu 4.** Với class trong `com.acme`, `SomeClass.class.getResource("config.properties")` khác gì `SomeClass.class.getClassLoader().getResource("config.properties")`?

**Đáp án:** Phương thức trên `Class` tra tương đối từ package `com/acme/`; phương thức trên `ClassLoader` tra từ root theo đúng tên không có tiền tố package.

**Câu 5.** `getResource` trả một URL bắt đầu bằng `jar:file:`. Có nên `new File(url.toURI())` để đọc?

**Đáp án:** Không giả định URL là file local. Dùng `url.openStream()` và đóng bằng try-with-resources; xử lý lỗi I/O.

**Câu 6.** Một resource JSON nằm trong package của named module nhưng `ClassLoader.getResource` trả null. Bước kiểm tra thêm?

**Đáp án:** Kiểm tra package ấy có được mở **unconditionally** theo điều kiện của ClassLoader resource lookup hay không; đồng thời xác minh tên resource, module/loader và phương thức tra.

**Câu 7.** Khi nào nên dùng `Module.getResourceAsStream` thay cho `ClassLoader.getResource`?

**Đáp án:** Khi muốn truy cập resource trong một module cụ thể và cần tuân theo module/caller access rules, thay vì phụ thuộc vào tìm kiếm tổng quát của class loader.

## 16. Kết luận và tài liệu chính thức

`findResource` và `findResources` là **hai điểm mở rộng resource lookup** của `ClassLoader`. Phương thức thứ nhất hỗ trợ tìm một URL local, phương thức thứ hai hỗ trợ enumerate nhiều URL local; chúng độc lập và cần triển khai nhất quán. Với public API mặc định, `getResource` ưu tiên parent khi tìm một resource, còn `getResources` kết hợp parent rồi local. Thiết kế đúng cơ chế này giúp plugin và framework quản lý cấu hình, metadata và service providers đáng tin cậy, đồng thời tránh lỗi thứ tự tìm kiếm và ranh giới module.

Tài liệu đối chiếu:

- Java SE 17 `ClassLoader` API (`getResource`, `getResources`, `findResource`, `findResources`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 `Class` API (`getResource`, `getResourceAsStream`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 `Module` API (`getResourceAsStream`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- Java SE 17 `URLClassLoader` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
