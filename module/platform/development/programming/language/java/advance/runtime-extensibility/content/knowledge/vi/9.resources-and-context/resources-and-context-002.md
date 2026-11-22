# Quy tắc đường dẫn tài nguyên và nguy cơ chọn nhầm bản trong loader cha

Một ứng dụng Java có thể nạp thêm plugin, driver, codec hoặc bộ quy tắc cấu hình tại runtime. Mỗi thành phần thường đóng gói tài nguyên như `.properties`, `.yaml`, JSON, template, chứng chỉ hoặc file `META-INF/services`. Vấn đề dễ bị bỏ qua là **tên tài nguyên không bảo đảm nó đến từ đúng JAR hay đúng phiên bản plugin**.

Ví dụ, cả thư viện ứng dụng và plugin đều chứa `config/mode.txt`. Code gọi `pluginLoader.getResource("config/mode.txt")` có thể đọc **bản của loader cha**, dù lời gọi được thực hiện trên biến `pluginLoader`. Nguyên nhân nằm ở **quy tắc đặt tên đường dẫn và cơ chế ủy quyền tìm tài nguyên** của `ClassLoader`.

Bài này giải thích cách Java hiểu đường dẫn tài nguyên, sự khác biệt giữa `Class.getResource` và `ClassLoader.getResource`, thuật toán tìm ở parent/child loader, cách phát hiện bản trùng tên, tác động của thread context class loader và JPMS, cùng ví dụ Java 17 có thể chạy và đối chiếu kết quả.

## 1. Tài nguyên trên classpath được định danh như thế nào?

Một **resource name** trong Java là chuỗi đường dẫn logic, các thành phần phân cách bằng dấu `/`. Nó **không nhất thiết là đường dẫn file trên máy**:

- `config/app.properties`: tên tài nguyên bắt đầu từ **gốc classpath hoặc root được loader quản lý**.
- `META-INF/services/com.example.spi.Codec`: metadata SPI theo quy ước.
- `com/example/plugin/schema.json`: tài nguyên đặt cùng namespace/package của một plugin.
- `images/icon.png`: tài nguyên có thể nằm trong thư mục build, JAR hoặc nguồn khác mà loader hiểu.

Nếu project có file `src/main/resources/config/app.properties`, khi build theo cấu trúc classpath thông thường, tên lookup là `config/app.properties`. Đừng truyền `src/main/resources/config/app.properties` vào `getResource` ở runtime: `src/main/resources` là cấu trúc nguồn của quá trình build, không phải prefix chuẩn của resource khi đóng gói.

Các quy tắc quan trọng:

1. Sử dụng `/` trong resource name, kể cả khi chạy Windows; **không** xây resource name bằng `File.separator` hoặc ghép đường dẫn như file hệ điều hành.
2. Viết đúng chữ hoa/chữ thường và từng thành phần đường dẫn. Trong JAR, tên entry được phân biệt chính xác; khi chạy từ thư mục exploded, filesystem có thể có quy tắc case khác nhau. Mã portable không nên dựa vào việc filesystem tự bỏ qua khác biệt hoa/thường.
3. Dấu `/` ở **đầu chuỗi** có ý nghĩa riêng khi dùng `Class.getResource`, nhưng không phải cú pháp nên truyền cho `ClassLoader.getResource`. Phân biệt hai API ở phần tiếp theo.
4. Nếu resource không tìm thấy, `getResource` trả `null`, `getResourceAsStream` cũng có thể trả `null`; cần báo lỗi có tên resource và loader đang dùng.
5. URL trả về có thể dùng scheme `jar:`, `file:`, `jrt:` hoặc cơ chế loader khác. **Không mặc định biến URL tài nguyên thành `java.io.File`**; ưu tiên `URL.openStream()` hoặc `getResourceAsStream()`.

```text
Cấu trúc nguồn                         Tên tra cứu runtime
src/main/resources/
    config/app.properties          --> config/app.properties
    com/acme/plugin/rules.json     --> com/acme/plugin/rules.json
    META-INF/services/x.y.Codec    --> META-INF/services/x.y.Codec
```

Lưu ý: tài nguyên không đồng nhất với mã class. Việc class được tìm bởi một loader nào đó không có nghĩa resource trùng tên ở loader đó sẽ được ưu tiên nếu đường gọi tìm resource vẫn ủy quyền cho parent.

## 2. Phân biệt Class.getResource và ClassLoader.getResource

Đây là nguồn lỗi rất thường gặp khi chuyển code giữa package hoặc chuyển từ một helper trong plugin sang code của host.

### `ClassLoader.getResource(String name)`

Tên tài nguyên được hiểu theo gốc namespace mà loader tìm kiếm; thông thường **không bắt đầu bằng dấu `/`**:

```java
ClassLoader loader = MyPlugin.class.getClassLoader();
URL url = loader.getResource("com/acme/plugin/rules.json");
```

Đây là **đoạn minh họa**: `MyPlugin` phải là một class tồn tại, các import `ClassLoader`/`URL` và resource tương ứng phải có trong project. `getResource` trả về URL đầu tiên theo quy tắc của loader. `getResourceAsStream` chọn nguồn theo cùng quy tắc tra cứu resource đó.

### `Class.getResource(String name)`

`Class` hỗ trợ hai cách diễn giải:

- Nếu `name` **không có `/` ở đầu**, nó là tên **tương đối với package của class**.
- Nếu `name` **bắt đầu bằng `/`**, dấu đầu bị bỏ và phần còn lại được hiểu là tên **tuyệt đối từ root resource namespace**.

Giả sử class `com.acme.plugin.MyPlugin`:

| Lời gọi | Resource name tuyệt đối được hình thành |
| --- | --- |
| `MyPlugin.class.getResource("rules.json")` | `com/acme/plugin/rules.json` |
| `MyPlugin.class.getResource("config/rules.json")` | `com/acme/plugin/config/rules.json` |
| `MyPlugin.class.getResource("/config/rules.json")` | `config/rules.json` |
| `MyPlugin.class.getClassLoader().getResource("config/rules.json")` | `config/rules.json` |
| `MyPlugin.class.getClassLoader().getResource("/config/rules.json")` | Không phải dạng đường dẫn chuẩn của ClassLoader; với `URLClassLoader` thông thường có thể không tìm thấy |

**Cẩn thận với suy luận “dùng Class.getResource sẽ chắc chắn chọn tài nguyên của plugin”.** Đối với class ở unnamed module, API này tạo resource name tuyệt đối rồi giao cho **loader định nghĩa class**; loader đó có thể tiếp tục ủy quyền tìm resource cho parent. Đối với class trong named module, Java có đường tìm resource gắn với module riêng và quy tắc đóng gói module; xem phần 7.

Khi thay đổi vị trí package, `MyPlugin.class.getResource("rules.json")` sẽ đổi resource name tương ứng. Vì vậy, dùng đường dẫn tương đối là thuận tiện cho tài nguyên thực sự gắn với class/package; dùng đường dẫn root rõ ràng cho tài nguyên có hợp đồng độc lập với package.

### Lấy stream và đóng tài nguyên

Ví dụ dùng `ClassLoader` với URL:

```java
ClassLoader loader = MyPlugin.class.getClassLoader();
URL url = loader.getResource("com/acme/plugin/rules.json");
if (url == null) {
    throw new IllegalStateException("Resource not found: com/acme/plugin/rules.json");
}
try (InputStream in = url.openStream()) {
    byte[] bytes = in.readAllBytes();
    // Decode/parse bytes theo hợp đồng của resource.
}
```

Đây cũng là snippet, cần import `URL`, `InputStream` và class `MyPlugin`. Đọc thành byte rồi chọn đúng charset (thường UTF-8 nếu contract quy định), đóng `InputStream` bằng try-with-resources. Với `getResourceAsStream` cũng phải kiểm tra `null` và đóng stream; nó tiện khi không cần biết URL, nhưng **URL hữu ích để chẩn đoán nguồn gốc của bản được chọn**.

## 3. Tại sao loader con có thể chọn nhầm bản từ loader cha?

`ClassLoader` chuẩn dùng mô hình **delegation**. Đối với `getResource(name)`, implementation mặc định làm theo ý tưởng:

1. Hỏi **parent class loader** trước; nếu parent là `null` thì tìm trong nguồn của bootstrap loader.
2. Nếu parent trả URL, lấy URL đó và kết thúc.
3. Nếu parent không tìm thấy, gọi `findResource(name)` để tìm ở chính loader hiện tại.

Đối với `getResources(name)`, implementation mặc định liệt kê các kết quả từ **parent trước**, sau đó thêm các kết quả từ `findResources(name)` của loader con.

```text
ClassLoader parent
    resources/
        config/mode.txt      (PARENT)
            |
            | delegation
            v
ClassLoader child
    resources/
        config/mode.txt      (CHILD)

child.getResource("config/mode.txt")
    -> parent.getResource(...) -> PARENT được chọn
    -> không cần tìm CHILD

child.getResources("config/mode.txt")
    -> [URL của PARENT, URL của CHILD]  (với URLClassLoader mặc định)
```

Đây là quy tắc của **implementation mặc định của `ClassLoader` và `URLClassLoader` theo parent-first**, không phải bảo đảm tất cả class loader tùy biến hoạt động giống hệt. Một plugin host hoặc application server có thể override `getResource`/`getResources` hoặc dùng chính sách child-first cho một số namespace. Trong named modules, thứ tự tìm giữa các module cùng loader còn có những trường hợp không được đặc tả. **Không xây logic chọn phiên bản dựa trên giả định tùy tiện về thứ tự kết quả.**

### Một lỗi tích hợp có thật về mặt cơ chế

Host cung cấp `config/codec.properties` bản 1; plugin cũng có tên đó cho bản 2. Code plugin gọi `getClass().getClassLoader().getResourceAsStream("config/codec.properties")`. Nếu loader plugin đi qua parent-first, nội dung bản 1 của host có thể được chọn. Hệ thống vẫn chạy, nhưng cấu hình thuật toán, mapping, version hoặc feature flag có thể sai một cách âm thầm.

Điểm nguy hiểm là **resource được tìm thấy** nên kiểm tra `null` không bắt được lỗi. Cần xác minh **provenance** (resource thuộc provider/artifact/version nào), và tốt nhất tránh xung đột tên ngay từ thiết kế.

## 4. Ví dụ Java 17 độc lập: tái hiện parent-first và kiểm tra các bản trùng tên

Ví dụ dưới đây tự tạo hai thư mục tạm, mỗi thư mục có `config/mode.txt` nhưng nội dung khác nhau. Một `URLClassLoader` làm parent và một loader làm child; child nhận parent đó khi xây dựng. Cuối cùng thử loader biệt lập để thấy bản trong child. Chương trình không cần thư viện ngoài JDK.

Tạo file `ParentFirstResources.java`:

```java
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Enumeration;

public class ParentFirstResources {
    static String read(URL url) throws IOException {
        if (url == null) return "<missing>";
        try (InputStream in = url.openStream()) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8).trim();
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("resource-choice-");
        Path parentRoot = root.resolve("parent");
        Path childRoot = root.resolve("child");
        Path parentFile = parentRoot.resolve("config/mode.txt");
        Path childFile = childRoot.resolve("config/mode.txt");

        try {
            Files.createDirectories(parentFile.getParent());
            Files.createDirectories(childFile.getParent());
            Files.writeString(parentFile, "PARENT\n", StandardCharsets.UTF_8);
            Files.writeString(childFile, "CHILD\n", StandardCharsets.UTF_8);

            try (URLClassLoader parent = new URLClassLoader(
                         new URL[] {parentRoot.toUri().toURL()}, null);
                 URLClassLoader child = new URLClassLoader(
                         new URL[] {childRoot.toUri().toURL()}, parent);
                 URLClassLoader childOnly = new URLClassLoader(
                         new URL[] {childRoot.toUri().toURL()}, null)) {

                String name = "config/mode.txt";
                System.out.println("selected=" + read(child.getResource(name)));

                Enumeration<URL> all = child.getResources(name);
                int index = 0;
                while (all.hasMoreElements()) {
                    System.out.println("candidate" + (++index)
                            + "=" + read(all.nextElement()));
                }

                System.out.println("isolated=" + read(childOnly.getResource(name)));
                System.out.println("slashFound=" + (child.getResource("/" + name) != null));
            }
        } finally {
            Files.deleteIfExists(parentFile);
            Files.deleteIfExists(childFile);
            Files.deleteIfExists(parentFile.getParent());
            Files.deleteIfExists(childFile.getParent());
            Files.deleteIfExists(parentRoot);
            Files.deleteIfExists(childRoot);
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 ParentFirstResources.java
java ParentFirstResources
```

Stdout đã đối chiếu bằng `javac --release 17` và `java`:

```text
selected=PARENT
candidate1=PARENT
candidate2=CHILD
isolated=CHILD
slashFound=false
```

**Giải thích:**

1. `parentRoot` và `childRoot` cùng chứa đường dẫn logic `config/mode.txt`, khác nội dung để quan sát được nguồn được chọn.
2. `parent` là `URLClassLoader` có parent `null`; `child` ủy quyền cho `parent`. Bởi parent-first, `child.getResource(name)` nhận nội dung `PARENT`.
3. `child.getResources(name)` liệt kê cả hai bản và trong ví dụ này theo thứ tự `PARENT` rồi `CHILD`. Đây là hành vi của cặp loader mặc định được tạo trong ví dụ.
4. `childOnly` không có `parent` cùng chứa resource, nên truy vấn chọn `CHILD`. **Đây là thử nghiệm minh họa isolation, không phải hướng dẫn luôn đặt parent bằng `null` cho plugin production**: class/plugin thực tế có thể cần các API chung từ host và các module của nền tảng.
5. `slashFound=false` cho thấy với loader trong ví dụ, `ClassLoader.getResource("/config/mode.txt")` không tìm thấy. Đối với `Class.getResource("/config/mode.txt")`, dấu `/` đầu lại có ý nghĩa hợp lệ như phần 2.

Không được kết luận rằng thay parent loader bằng `null` là giải pháp phổ quát. Nó có thể làm provider không nhìn thấy service interface, thư viện phụ thuộc, hoặc gây trùng class identity. Giải pháp phù hợp thường là **đặt namespace resource riêng**, kiểm tra collision và xây một chính sách lookup rõ ràng.

## 5. Khi có nhiều bản: phát hiện, chọn đúng và fail fast

### Dùng getResources để tìm collision

Nếu chỉ gọi `getResource` hoặc `getResourceAsStream`, ứng dụng biết “có tài nguyên”, nhưng có thể không biết “có thêm bản thứ hai”. Khi một resource **được yêu cầu phải duy nhất**, kiểm tra bằng `getResources`:

```java
static URL requireUniqueResource(ClassLoader loader, String name)
        throws IOException {
    var locations = java.util.Collections.list(loader.getResources(name));
    if (locations.size() != 1) {
        throw new IllegalStateException(
            "Expected exactly one resource '" + name
            + "', found " + locations.size() + ": " + locations);
    }
    return locations.get(0);
}
```

Đây là helper snippet, cần import `URL`, `IOException` và được gọi từ một class đã khai báo. Nó kiểm tra **số lượng resource location nhìn thấy bởi loader tại thời điểm tra cứu**; không tự xác minh nội dung, chữ ký, quyền truy cập hoặc version. Đối với cấu hình bắt buộc duy nhất, báo lỗi sớm tốt hơn việc âm thầm lấy bản đầu tiên.

Còn những resource được thiết kế để có **nhiều bản** thì không nên fail fast chỉ vì `getResources` trả nhiều URL. Ví dụ `META-INF/services/<service-interface>` được `ServiceLoader` sử dụng để khám phá nhiều provider; `META-INF/services` cần được xử lý theo quy tắc SPI, không coi đó là một file config single-owner. Cũng có ứng dụng chủ động gộp nhiều phần metadata từ các JAR. Trong các trường hợp đó, phải xác định chính sách merge, trùng lặp và lỗi parse rõ ràng.

### Ba chính sách chọn nguồn hợp lệ

**A. Namespace riêng theo chủ sở hữu**

Dùng `META-INF/com.acme.plugin-x/config/rules.json` hoặc `com/acme/pluginx/rules.json` thay vì đặt mọi resource là `config.json`/`application.properties` ở root. Đây thường là biện pháp đơn giản và ít phụ thuộc vào thứ tự class loader nhất. Khi đổi version schema, khai báo version trong tên, metadata hoặc nội dung nếu hợp đồng cần phân biệt.

**B. Một điểm tra cứu có chủ sở hữu rõ**

Một plugin registry có thể nắm `ClassLoader`, `Module` hoặc handle tới artifact đã được xác thực và cung cấp `openResource(pluginId, resourceName)`. Phần nghiệp vụ không tự ý gọi system loader hay TCCL. Tại điểm này registry có thể kiểm tra: ID plugin, version, đường dẫn trong namespace cho phép, ứng viên trùng lặp và nguồn gốc URL. Với JAR cụ thể, có thể đọc entry qua `JarFile`/`JarEntry` theo hợp đồng riêng thay vì dựa vào thuật toán tài nguyên của parent-first loader; cần quản lý vòng đời JAR/stream.

**C. Ưu tiên có chủ đích, được kiểm thử**

Có những host thiết kế parent-first cho API chung và child-first cho tài nguyên riêng của plugin. Nếu hệ thống thật sự yêu cầu chính sách ấy, triển khai ở một loader/registry có mô tả rõ **namespace nào được ưu tiên**, fallback lúc nào, kết quả ra sao khi trùng tên, và có duy trì nhất quán với `getResources` không. Việc tùy tiện đảo mọi lookup thành child-first có thể gây lỗi class identity, ABI hoặc xung đột dependency.

**Không dùng “URL thứ hai trong enumeration” làm hợp đồng.** Thứ tự cụ thể của cặp `URLClassLoader` trong ví dụ là có thể quan sát, nhưng nhiều loại custom loader và module configuration khác có thứ tự không ổn định/không được đặc tả.

## 6. TCCL, loader hệ thống và class loader định nghĩa class

Ba lời gọi có thể dùng **ba loader khác nhau**:

```java
ClassLoader defining = MyPlugin.class.getClassLoader();
ClassLoader context = Thread.currentThread().getContextClassLoader();
ClassLoader system = ClassLoader.getSystemClassLoader();
```

Đây là snippet; `MyPlugin` phải tồn tại. `defining` là loader định nghĩa class (có thể `null` với bootstrap class). `context` là **thread context class loader (TCCL)**, một thiết lập có thể khác theo thread và được dùng bởi nhiều framework để khám phá implementation/resources. `system` là system/application loader của JVM.

Ví dụ: request thread của host có TCCL trỏ tới loader của host, worker thread lại có TCCL khác; cùng `context.getResource("config/mode.txt")` có thể nhận hai kết quả khác nhau. Thread pool có thể giữ TCCL từ lúc tạo hoặc bị framework thay đổi. Không nên suy đoán TCCL luôn là loader của plugin đang xử lý request.

Nếu một API chủ động dùng TCCL, cần xác định ai thiết lập, ai khôi phục và hoạt động đó có phù hợp với hợp đồng framework không. Khi tạm thay TCCL, phải phục hồi trong `finally` để tránh làm nhiễm bối cảnh của thread pool:

```java
Thread thread = Thread.currentThread();
ClassLoader old = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    // Gọi framework API vốn được thiết kế để dùng TCCL.
} finally {
    thread.setContextClassLoader(old);
}
```

Đoạn trên là minh họa cần biến `pluginLoader` đã được tạo và kiểm tra trước. **Đổi TCCL không thay đổi class loader đã định nghĩa class, cũng không tự loại bỏ parent-first delegation**. Nếu chỉ cần đọc một resource thuộc artifact xác định, ưu tiên API nhận explicit loader/module/artifact thay vì thay context toàn thread.

## 7. Resource trong Java Platform Module System (JPMS)

Với **named modules**, quy tắc tìm resource có thêm lớp **encapsulation**. Hai điểm cần phân biệt:

1. `ClassLoader.getResource(name)` và `getResources(name)` áp dụng hạn chế đối với resource **không kết thúc bằng `.class`** trong package thuộc named module: chỉ có thể trả về resource đó qua các API này khi package được `opens` **vô điều kiện**. `exports` cho Java API public không tương đương `opens` cho resource/reflective access.
2. `SomeClass.class.getResource(...)` (khi `SomeClass` thuộc named module) trước hết tìm trong module gắn với class và áp dụng điều kiện mở package cho module của caller. `Module.getResourceAsStream(name)` cũng nhắm vào module cụ thể, áp dụng quy tắc resource access của module đó.

Nếu muốn đọc một resource gắn với module đã biết:

```java
Module owner = SomeProvider.class.getModule();
try (InputStream in = owner.getResourceAsStream(
        "com/acme/provider/schema.json")) {
    if (in == null) {
        throw new IllegalStateException("Resource unavailable in module");
    }
    // Đọc theo charset/schema của plugin.
}
```

Đây là snippet có class `SomeProvider` và import `InputStream` phù hợp; API có thể ném `IOException`. **Không có nghĩa** chỉ cần biết module là có quyền đọc mọi package resource: với named module, package chứa resource có thể cần `opens` cho caller. Resource không thuộc package của module và file `.class` có quy tắc đóng gói riêng.

Trong một module layer có nhiều module chứa cùng resource name, `ClassLoader.getResource` không bảo đảm thứ tự tìm giữa chúng. Muốn ràng buộc resource với đúng module/version, dùng tham chiếu module đã được registry chọn rồi kiểm tra quyền truy cập, thay vì chỉ tra một tên chung trên class loader.

Tài liệu JDK 17 nêu rõ các quy tắc này trong `ClassLoader.getResource/getResources`, `Class.getResource` và `Module.getResourceAsStream`.

## 8. Chẩn đoán “đúng tên nhưng sai bản” theo thứ tự nào?

Khi plugin tải nhầm file cấu hình, mục tiêu là chứng minh **resource name, loader, URL và nội dung/version** nào thực sự được chọn, không chỉ xem tên file có tồn tại.

### Bước 1 — Xác định chính xác resource name

Ghi lại tên logic mà code truyền vào API, có dấu `/` đầu hay không, có phải đường dẫn tương đối với package hay không, có đúng chữ hoa/thường không. Đừng kiểm tra mỗi file trong thư mục `src/main/resources`; phải kiểm tra **artifact/runtime classpath** đang thực thi.

### Bước 2 — Ghi nguồn loader và context

Xác định API đã gọi: `SomeClass.class.getResource`, `someLoader.getResource` hay lấy loader từ TCCL. Quan sát class/identity của defining/context loader và parent chain nếu có thể. Tránh log ra nội dung cấu hình nhạy cảm; chỉ log metadata an toàn.

### Bước 3 — Liệt kê candidates thay vì chỉ đọc first match

Ở môi trường có thể chẩn đoán an toàn:

```java
String name = "com/acme/pluginx/rules.json";
ClassLoader loader = plugin.getClass().getClassLoader();
var urls = java.util.Collections.list(loader.getResources(name));

System.out.println("resource=" + name);
System.out.println("loader=" + loader);
System.out.println("candidates=" + urls.size());
urls.forEach(url -> System.out.println("candidateUrl=" + url));
```

Đây là snippet: cần đối tượng `plugin`, `getResources` có thể ném `IOException`, và cần cân nhắc logging URL có thể chứa đường dẫn nội bộ. Nếu có hai URL, so sánh tên JAR, version và checksum trong môi trường kiểm thử; đừng chỉ chọn theo index của enumeration.

### Bước 4 — Kiểm tra file thực sự được đóng gói

Xem danh sách entry trong JAR:

```bash
jar --list --file plugin.jar
```

Tìm tên như `com/acme/pluginx/rules.json` hoặc `META-INF/services/...`. Nếu thiếu entry thì phải sửa build/packaging, không thể chữa bằng thay class loader. Nếu có hai bản ở host/plugin, kiểm tra JAR được dùng thực tế và thứ tự loader. Với JAR đã shading/assembly, cần kiểm tra việc merge/ghi đè metadata, đặc biệt `META-INF/services`.

### Bước 5 — Đặt test bảo vệ quy tắc chọn resource

Nên có test tích hợp dựng cả parent và child resource **trùng tên, khác nội dung**, như ví dụ phần 4. Kiểm thử loader cụ thể của production (kể cả app server/framework), kiểm tra URL được chọn; thêm test fail fast khi resource cần duy nhất nhưng có >1 candidate, và test không tìm thấy resource.

Tại đường production, nếu tài nguyên quyết định hành vi quan trọng (mapping, policy, trust store, serialization schema), có thể kiểm tra thêm version/schema/checksum hay chữ ký nguồn theo hợp đồng. Việc chọn nhầm một bản “có vẻ hợp lệ” có thể nguy hiểm hơn lỗi `null`.

## 9. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân hay gặp | Cách xác minh và xử lý |
| --- | --- | --- |
| `getResource` trả `null` dù file có trong project | Truyền prefix `src/main/resources`, sai package, khác chữ hoa/thường, hoặc resource không được đóng gói | Kiểm tra resource name từ root, danh sách entry JAR và artifact thực tế |
| `Class.getResource("x.json")` tìm sai vị trí | Method này hiểu `x.json` tương đối với package của class | Dùng đường dẫn tuyệt đối `"/config/x.json"` khi cần root; xác minh module/package |
| `ClassLoader.getResource("/x.json")` không tìm thấy | Nhầm dấu `/` đầu theo quy tắc của `Class.getResource` | Truyền `"x.json"` cho `ClassLoader` |
| Plugin đọc cấu hình của host | Parent-first chọn cùng resource name ở loader cha | Dùng `getResources` để tìm collision; namespace plugin riêng, registry rõ ownership |
| Sau cập nhật JAR vẫn thấy nội dung cũ | Runtime vẫn dùng parent JAR/old loader, cache riêng của framework, hoặc chưa thay artifact trong process | Quan sát URL nguồn và deployment/version; refresh đúng lifecycle |
| Máy này chạy đúng, máy khác sai | Khác packaging, classpath order, class loader policy hoặc môi trường filesystem | Kiểm thử trên artifact/container thực; bỏ phụ thuộc vào thứ tự ngầm |
| `getResourceAsStream` có dữ liệu nhưng không đúng config | Không xác minh nguồn hoặc nhiều bản cùng tên | Tra URL bằng `getResources`, so version/schema, fail fast khi cần |
| Resource trong named module không tìm thấy | Package không được `opens` phù hợp hoặc dùng sai API tìm theo module | Kiểm tra `module-info.java`, dùng `Class`/`Module` API phù hợp và đúng quyền |
| `Paths.get(url.toURI())` lỗi với resource trong JAR | Không phải mọi resource URL đều tương ứng một file của default filesystem | Dùng `URL.openStream()`, hoặc API ZIP/JAR thích hợp khi cần |
| Thay TCCL làm lỗi plugin khác ở thread pool | Không khôi phục context hoặc kỳ vọng TCCL đổi delegation | Dùng `try/finally`; ưu tiên explicit loader/module và test tải lại |

## 10. Quy tắc thiết kế tài nguyên cho module mở rộng

**Đặt tên có chủ sở hữu.** Tránh các key chung như `config.json`, `settings.properties` ở root classpath nếu nhiều plugin có thể dùng. Định danh namespace theo tổ chức/plugin và giữ ổn định trong hợp đồng; đánh version schema khi cần.

**Tách tên logic khỏi nguồn vật lý.** API phía core có thể dùng `pluginId + resourceName`, còn plugin registry chịu trách nhiệm định tuyến tới loader/module/JAR được phép. Một đoạn code nghiệp vụ không cần biết đường dẫn JAR trên ổ đĩa hay thứ tự loader.

**Có quy tắc collision rõ ràng.** Một số resource hợp pháp phải duy nhất; số khác như metadata SPI có thể được tổng hợp. Xác định nhóm nào cần fail fast, nhóm nào được merge, và cách xử lý trùng provider/config.

**Không trộn đường dẫn resource với đường dẫn hệ điều hành.** Resource name dùng `/`, không phải đường dẫn tuyệt đối tới máy host. Không tin vào resource name do input chưa xác thực cung cấp; registry nên giới hạn namespace, loại path traversal và xác thực owner trước khi mở artifact.

**Quản lý lifecycle của loader và stream.** Đóng `InputStream` ngay sau khi đọc; nếu quản lý `URLClassLoader`, đóng nó khi kết thúc vòng đời plugin và không còn hoạt động cần tài nguyên. Việc đóng loader không lập tức unload class đã được định nghĩa; muốn dỡ phiên bản cũ phải giải phóng các tham chiếu liên quan.

**Kiểm thử đúng môi trường triển khai.** Unit test chỉ dùng một classpath đơn giản không tái hiện được trường hợp trùng resource giữa parent và child. Thêm integration test dựng hierarchy giống production, xác minh đúng source/version và module access.

### Checklist ngắn trước khi phát hành plugin

- [ ] Resource name dùng `/` và được tính đúng root/package theo API gọi.
- [ ] Không dựa vào `src/main/resources` hay đường dẫn file thật tại runtime.
- [ ] Biết **class loader/module nào** sở hữu plugin và đường lookup có parent-first không.
- [ ] Nếu tên có thể trùng, kiểm tra `getResources` và xử lý theo chính sách rõ ràng.
- [ ] Không cho loader cha âm thầm quyết định cấu hình riêng của plugin khi yêu cầu chọn bản plugin.
- [ ] TCCL được chỉ định/khôi phục đúng nếu framework cần; không dùng TCCL như lối tắt cho isolation.
- [ ] Xác minh các giới hạn `opens`/JPMS khi đọc tài nguyên trong named module.
- [ ] Stream được đóng, URL nguồn có thể kiểm tra, version/schema được validate.
- [ ] Có test trùng resource parent/child và test artifact/JAR thực tế.

Tài liệu tham khảo JDK 17:

- [`ClassLoader` và các phương thức `getResource`, `getResources`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [`Class.getResource`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getResource(java.lang.String))
- [`Module.getResourceAsStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html#getResourceAsStream(java.lang.String))

**Ghi nhớ:** đường dẫn đúng chỉ cho Java biết **tên cần tìm**; **loader, delegation order và module access** mới quyết định **bản nào thực sự được trả về**. Đối với plugin, phải thiết kế resource namespace, kiểm tra xung đột và buộc nguồn tài nguyên gắn với đúng chủ sở hữu/version thay vì tin rằng gọi trên loader con sẽ tự ưu tiên bản của nó.