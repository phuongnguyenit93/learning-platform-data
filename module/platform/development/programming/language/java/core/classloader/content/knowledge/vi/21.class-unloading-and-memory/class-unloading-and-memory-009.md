# Giải phóng JAR handle và tránh giữ file sau reload

## 1. Vì sao reload plugin rồi vẫn không thay hoặc xóa được JAR?

Trong ứng dụng Java nạp plugin từ `plugin.jar`, các thành phần như `URLClassLoader`, `JarFile` hoặc luồng đọc resource có thể giữ **file handle** tới JAR. Khi triển khai lại (reload), ứng dụng thường muốn thay JAR v1 bằng JAR v2; nếu chưa đóng các handles, thao tác ghi đè, rename hoặc xóa có thể gặp lỗi — đặc biệt trên Windows.

Đôi khi JAR thay được nhưng chương trình vẫn chạy code cũ. Đó lại là vấn đề khác: JVM đã định nghĩa class theo **binary name và defining class loader**, không tự cập nhật bytecode của một class đã nạp chỉ vì file JAR ngoài đĩa thay đổi.

Phải phân biệt ba mục tiêu:

1. **Giải phóng file handle:** đóng loader/stream/archive/connection sở hữu handle để hệ điều hành có thể giải phóng tài nguyên I/O.
2. **Nạp phiên bản mới:** tạo **loader mới** cho JAR phiên bản mới thay vì tái sử dụng loader đã định nghĩa class v1.
3. **Dỡ class khỏi bộ nhớ:** không còn strong references tới class, class loader, instances và những cấu trúc liên quan; khi đó JVM mới *có thể* thu gom/unload nếu phù hợp.

Ba mục tiêu liên quan, nhưng **không tương đương**. `URLClassLoader.close()` không tự unload class, còn `System.gc()` không phải API để đóng JAR handle.

Các triệu chứng:

| Triệu chứng | Nhóm vấn đề có thể xảy ra |
| --- | --- |
| Windows báo file đang được process sử dụng | Handle từ loader, JarFile, cache, stream, process khác |
| Linux xóa được file nhưng bộ nhớ/FD tăng | Unlink không bảo đảm descriptor đã đóng |
| Reload nhưng gọi method vẫn trả giá trị v1 | Class v1 vẫn được dùng; không tạo/định tuyến sang loader v2 |
| Sau nhiều lần reload, metaspace tăng | Loader/classes cũ còn được tham chiếu; cần phân tích heap/GC |
| Reload chỉ lỗi khi có request chạy đồng thời | Đóng loader trong lúc thread khác vẫn load class/resource |
| Đóng loader xong mà plugin vẫn có thread chạy | `close()` không tự gọi stop/shutdown plugin |

## 2. Hợp đồng chính xác của URLClassLoader.close()

`java.net.URLClassLoader` triển khai `java.io.Closeable` và có thể dùng trong *try-with-resources*. Theo Javadoc Java SE 21:

- `close()` đóng loader để loader không tiếp tục nạp **class và resource mới do loader ấy tự định nghĩa**.
- Các **class đã được nạp** vẫn có thể truy cập; các class/resource do parent định nghĩa vẫn có thể tiếp cận qua delegation.
- Với `file:` và `jar:` URL, nó cố gắng **đóng các file đã được chính loader ấy mở**.
- Nếu một thread còn thực hiện class loading khi `close()` được gọi, **kết quả của thao tác đang chạy không xác định** theo hợp đồng API.
- `close()` nỗ lực đóng mọi file, giữ lỗi `IOException` và các ngoại lệ suppressed khi có nhiều lỗi.
- Gọi close lại trên loader đã đóng là no-op.

Những điều `close()` **không hứa hẹn**:

- Không hủy các instances đã tạo từ class của loader.
- Không bảo đảm Class objects hoặc metaspace được thu gom ngay.
- Không tự dừng threads, executors, scheduled tasks hoặc callbacks của plugin.
- Không tự đóng mọi `new JarFile(...)` hay mọi `URL.openStream()` của thư viện ngoài.
- Không đóng parent system/application loader hoặc sibling loader.
- Không làm định nghĩa class cũ trở thành bytecode mới.
- Không bảo đảm file JAR đã được giải phóng nếu **owner khác** còn giữ handle.

Do đó, sau khi `close()` thành công bạn chỉ có thể khẳng định **đã thực hiện thao tác đóng của URLClassLoader ấy**, không thể suy ra toàn bộ tiến trình đã thôi giữ JAR.

## 3. Quản lý vòng đời loader bằng try-with-resources

Ví dụ cơ bản:

~~~java
Path jar = Path.of("plugins", "plugin-v1.jar")
        .toAbsolutePath().normalize();
URL url = jar.toUri().toURL();

try (URLClassLoader loader = new URLClassLoader(
        new URL[]{url}, Host.class.getClassLoader())) {

    Class<?> impl = loader.loadClass("demo.Greeter");
    // Làm việc với impl trong vòng đời loader còn mở.
}
// loader.close() được gọi ở đây.
~~~

Đây là đoạn minh họa **không độc lập**, giả định `Host` và imports có sẵn. `try-with-resources` giúp đóng loader khi block kết thúc kể cả khi có exception. Nếu `close()` ném `IOException`, caller phải xử lý/log; nếu block cũng ném ngoại lệ thì lỗi close có thể nằm trong `getSuppressed()` của lỗi chính.

**Quan trọng với server/plugin lâu dài:** không đặt try-with-resources quanh **riêng lệnh loadClass** rồi trả plugin instance cho nhiều request phía sau. Sau khi block kết thúc, loader đã đóng, nên nếu instance về sau cần load thêm dependency hoặc resource, việc nạp mới có thể không thực hiện được.

Hãy để đối tượng quản lý plugin (plugin manager) sở hữu loader trong **suốt một phiên phục vụ**, rồi đóng nó **sau khi** plugin dừng hoạt động.

### Parent không thuộc quyền sở hữu của child

Không đóng nhầm application/system loader hoặc một loader cha được chia sẻ giữa nhiều plugin. `URLClassLoader.close()` trên loader con **không** đóng parent; đó là hành vi đúng. Nếu parent classpath cũng đã chứa cùng plugin JAR, việc chỉ đóng child loader không đủ để giải phóng handle do parent sở hữu — và có thể khiến parent-first trả class phiên bản cũ.

## 4. Luồng resource và handle độc lập

Plugin thường đọc cấu hình/resource ngay trong JAR:

~~~java
try (URLClassLoader loader = new URLClassLoader(
        new URL[]{jarUrl}, parentLoader)) {

    try (InputStream in =
                 loader.getResourceAsStream("demo/config.txt")) {
        if (in == null) {
            throw new IllegalStateException("Missing demo/config.txt");
        }
        String config = new String(in.readAllBytes(),
                StandardCharsets.UTF_8);
        // Sử dụng config.
    }
}
~~~

Đây là code minh họa với `jarUrl`, `parentLoader` và imports giả định. Thứ tự đúng: **stream đóng trước, loader đóng sau**.

`URLClassLoader.getResourceAsStream` có hợp đồng: nếu loader đã đóng, các resource mà phương thức này mở sẽ được đóng. Tuy vậy, luôn nên đóng chính stream ngay khi dùng xong bằng *try-with-resources*, thay vì để nó sống suốt vòng đời loader.

Một stream lấy từ **API khác** có thể có owner khác:

| Cách mở | Đối tượng chủ quản | Cách quản lý phù hợp |
| --- | --- | --- |
| `loader.getResourceAsStream(name)` | Loader và stream do nó mở | Đóng stream khi dùng xong, đóng loader khi plugin stop |
| `url.openStream()` | URLConnection/stream; có thể dùng `jar:` handler cache | Đóng stream, chú ý connection/cache |
| `new JarFile(path)` | JarFile riêng | Đóng JarFile tường minh |
| `new ZipFile(path)` | ZipFile riêng | Đóng ZipFile tường minh |
| Framework-specific nested JAR reader | Framework/resource subsystem riêng | Tuân theo lifecycle của framework |

Không tin rằng `loader.close()` sẽ quét mọi object `JarFile` trên heap và đóng tất cả.

### Khi trực tiếp đọc JarFile

~~~java
try (JarFile jar = new JarFile(jarPath.toFile())) {
    JarEntry entry = jar.getJarEntry("demo/config.txt");
    if (entry == null) {
        throw new IllegalStateException("JAR entry missing");
    }

    try (InputStream in = jar.getInputStream(entry)) {
        String content = new String(in.readAllBytes(),
                StandardCharsets.UTF_8);
        // Xử lý content.
    }
}
~~~

Đoạn này cần `JarFile`, `JarEntry`, `InputStream`, `StandardCharsets` và biến `jarPath` hợp lệ. Stream được đóng trước JarFile. Nếu một dependency tự mở JAR bằng cách này, đóng URLClassLoader của host không thay trách nhiệm đóng JarFile đó.

## 5. Close không phải class unloading

Giả sử loader L1 định nghĩa class `demo.Greeter` từ v1:

~~~text
URLClassLoader L1
    |
    +--- mở file plugin-v1.jar
    |
    +--- định nghĩa Class<demo.Greeter>
             |
             +--- instance v1, static state, references
~~~

Sau `L1.close()`:

- File mà L1 sở hữu đã được đưa vào quy trình đóng theo hợp đồng.
- `Class<demo.Greeter>` v1 **vẫn là class runtime hiện hữu** nếu còn được tham chiếu.
- Những method đã liên kết và object đã tạo có thể vẫn dùng được trong các giới hạn tương ứng; nhưng không bảo đảm lazy class loading từ L1 hoạt động sau close.
- `Class<?>`, instance, method/constructor reflection, callback, thread hoặc registry của host có thể giữ L1 sống.

Để dùng class v2 cùng binary name, tạo **L2**, vì JVM phân biệt class bằng **binary name + defining loader**:

~~~text
demo.Greeter @ L1 = định nghĩa v1
demo.Greeter @ L2 = định nghĩa v2

cùng tên nhưng hai runtime Class khác nhau
~~~

Không thể bắt L1 định nghĩa lại `demo.Greeter` một lần nữa bằng cách sửa JAR tại chỗ rồi gọi `L1.loadClass(...)`. JVM không thay bytecode đã định nghĩa chỉ vì filesystem thay đổi.

`System.gc()` không phải câu lệnh unload class tức thời. Class unloading phụ thuộc điều kiện GC và việc loader/class có còn bị giữ hay không; không dùng vòng lặp gọi GC vô hạn để chờ xóa file.

## 6. Quy trình hot reload an toàn

Khi reload plugin được phục vụ liên tục, nên có một **lifecycle coordinator**:

~~~text
RUNNING (plugin v1)
    |
    | Bắt đầu reload
    v
QUIESCING: chặn request/task mới vào v1
    |
    | Đợi request in-flight hoàn thành
    v
STOPPING: plugin.stop(), cancel tasks, unregister handlers
    |
    | Đóng streams, connections, JarFile/ZipFile khác
    v
CLOSING: URLClassLoader.close(), xử lý IOException
    |
    | Không thread nào còn loading từ loader v1
    v
RETIRED: bỏ references tới v1, dọn JAR cũ khi không còn handle
    |
    v
START v2: loader mới, instance mới, health check, nhận request
~~~

Nếu muốn không downtime, nên **nạp v2 trước trong file tên riêng**, health-check rồi chuyển routing; sau đó mới đợi v1 ngừng hẳn và đóng loader cũ:

~~~text
plugins/
    greeter-1.0.0.jar  <-- L1; request cũ
    greeter-2.0.0.jar  <-- L2; request mới
~~~

Đây là **blue/green deployment ở mức plugin**, tránh thay thế một file đang được loader cũ mở:

1. Triển khai JAR v2 dưới tên versioned bất biến.
2. Tạo L2 độc lập, khởi tạo plugin mới và kiểm tra sức khỏe.
3. Chuyển request mới sang L2 bằng pointer/registry có đồng bộ.
4. Đợi v1 kết thúc các tác vụ đang chạy, dừng tất cả resources v1.
5. Đóng L1, dọn references, rồi mới xóa file JAR v1 khi không còn handles.

Với thiết kế overwrite cùng một file `live.jar`, việc replace nên xảy ra **sau khi đã đóng** toàn bộ owners của JAR cũ. Trên các hệ thống production, đặt bản mới theo tên version thường dễ rollback và ít phụ thuộc hành vi locking của OS hơn.

## 7. Bài thực hành Java 17+: đóng loader v1 rồi thay live.jar

Bài có **hai class source cùng binary name** nhưng nội dung khác nhau, được compile thành **hai JAR riêng**. Host chạy với classpath chỉ chứa code host, nạp JAR v1 rồi JAR v2 qua hai instances URLClassLoader, đóng stream và loader giữa hai lượt.

### Cấu trúc source

~~~text
example/
├── src/
│   ├── v1/demo/Greeter.java
│   ├── v2/demo/Greeter.java
│   └── host/ReloadDemo.java
├── out/
│   ├── v1/demo/...
│   ├── v2/demo/...
│   └── host/...
└── dist/
    ├── v1.jar
    ├── v2.jar
    └── live.jar
~~~

Hai file `Greeter.java` cố ý trùng tên class, nên **không compile chúng cùng một output root**.

### File src/v1/demo/Greeter.java

~~~java
package demo;

public final class Greeter {
    public static String version() {
        return "v1";
    }
}
~~~

### File src/v2/demo/Greeter.java

~~~java
package demo;

public final class Greeter {
    public static String version() {
        return "v2";
    }
}
~~~

### File src/host/ReloadDemo.java

~~~java
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public final class ReloadDemo {
    private static Class<?> usePlugin(Path jar, String label)
            throws Exception {
        URL url = jar.toUri().toURL();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{url},
                ReloadDemo.class.getClassLoader())) {

            Class<?> type = loader.loadClass("demo.Greeter");

            System.out.println(label + " defined by child: "
                    + (type.getClassLoader() == loader));

            System.out.println(label + " version: "
                    + type.getMethod("version").invoke(null));

            try (InputStream in =
                         loader.getResourceAsStream("demo/config.txt")) {
                if (in == null) {
                    throw new IllegalStateException("Missing config");
                }
                String value = new String(in.readAllBytes(),
                        StandardCharsets.UTF_8).trim();
                System.out.println(label + " config: " + value);
            }

            return type;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("live.jar next.jar");
        }

        Path live = Path.of(args[0])
                .toAbsolutePath().normalize();
        Path next = Path.of(args[1])
                .toAbsolutePath().normalize();

        Class<?> first = usePlugin(live, "before");

        Files.copy(next, live, StandardCopyOption.REPLACE_EXISTING);
        System.out.println("jar replaced");

        Class<?> second = usePlugin(live, "after");

        System.out.println("different runtime classes: "
                + (first != second));
    }
}
~~~

Chú ý:

- Mỗi lượt `usePlugin` tạo loader riêng và đóng bằng try-with-resources.
- Stream tài nguyên được đóng **trước** khi đóng loader.
- Bước copy/replace xảy ra **giữa** hai lượt, lúc loader v1 đã đóng.
- Cả hai `Class<?>` được giữ để so sánh identity: bài này **không thử chứng minh class unloading**.
- Host classpath **không** được chứa `demo.Greeter`; nếu parent nhìn thấy class đó, parent-first có thể trả class parent.

### Compile và chạy Linux/macOS

Từ thư mục `example`:

~~~bash
mkdir -p out/v1/demo out/v2/demo out/host dist

javac --release 17 -d out/v1 src/v1/demo/Greeter.java
javac --release 17 -d out/v2 src/v2/demo/Greeter.java
javac --release 17 -d out/host src/host/ReloadDemo.java

printf 'config one\n' > out/v1/demo/config.txt
printf 'config two\n' > out/v2/demo/config.txt

jar --create --file dist/v1.jar -C out/v1 .
jar --create --file dist/v2.jar -C out/v2 .

cp dist/v1.jar dist/live.jar

java -cp out/host ReloadDemo dist/live.jar dist/v2.jar
~~~

### Compile và chạy Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out\v1\demo, out\v2\demo, out\host, dist | Out-Null

javac --release 17 -d out\v1 src\v1\demo\Greeter.java
javac --release 17 -d out\v2 src\v2\demo\Greeter.java
javac --release 17 -d out\host src\host\ReloadDemo.java

Set-Content -Path out\v1\demo\config.txt -Value 'config one' -Encoding Ascii
Set-Content -Path out\v2\demo\config.txt -Value 'config two' -Encoding Ascii

jar --create --file dist\v1.jar -C out\v1 .
jar --create --file dist\v2.jar -C out\v2 .

Copy-Item dist\v1.jar dist\live.jar
java -cp out\host ReloadDemo dist\live.jar dist\v2.jar
~~~

Chạy trong thư mục `example` với JDK 17 trở lên. Các resource config chứa text ASCII nên việc đọc UTF-8 trả nội dung giống nhau trên hai hệ điều hành.

### Stdout chính xác đã kiểm chứng

~~~text
before defined by child: true
before version: v1
before config: config one
jar replaced
after defined by child: true
after version: v2
after config: config two
different runtime classes: true
~~~

Bài đã được biên dịch bằng `javac --release 17` và chạy thực tế trên OpenJDK 21 (Linux) với cùng cấu trúc file. Điều này chứng minh loader mới thấy JAR v2 và JAR resource v2. **Nó không chứng minh trên mọi Windows install mọi file lock đều được giải phóng**, vì file có thể còn do process, scanner hoặc thư viện khác sử dụng.

### Giải thích đầu ra

- `before defined by child: true`: L1 thực sự định nghĩa class v1.
- `before version: v1` và `before config: config one`: class/resource đầu tiên đến từ file live chứa v1.
- `jar replaced`: thao tác `Files.copy` hoàn thành trong môi trường test sau khi loader đầu tiên đóng.
- `after defined by child: true`: L2 định nghĩa class mới, không nhận class từ parent.
- `after version: v2` và `after config: config two`: class/resource đã chuyển sang JAR mới.
- `different runtime classes: true`: L1 và L2 là hai defining loaders khác nhau nên `Class<?>` không trùng.

Ví dụ cố ý trả `Class<?>` v1 từ `usePlugin` để so sánh. Trong hệ thống thật muốn unload, **không giữ reference v1 vô thời hạn**.

## 8. JarURLConnection và cache: một nguồn giữ JAR khác

Nếu code lấy URL rồi trực tiếp mở stream:

~~~java
URL resourceUrl = loader.getResource("demo/config.txt");
if (resourceUrl == null) {
    throw new IllegalStateException("Missing resource");
}
try (InputStream in = resourceUrl.openStream()) {
    // Đọc resource.
}
~~~

Đây là đoạn code minh họa với loader sẵn có. URL entry từ JAR có thể dạng:

~~~text
jar:file:/path/to/plugin.jar!/demo/config.txt
~~~

Giao thức `jar:` có `JarURLConnection`, một subclass của `URLConnection`. Thuộc tính `useCaches` của URLConnection cho phép cache khi `true`, và default thường bật. Một kết nối/caching độc lập có thể giữ tài nguyên ngay cả khi bạn đã gọi `close()` trên loader riêng.

Nếu **tự quản lý một JarURLConnection** và không muốn dùng cache của kết nối đó:

~~~java
URL jarEntry = new URL(
        "jar:file:/path/to/plugin.jar!/demo/config.txt");
JarURLConnection connection =
        (JarURLConnection) jarEntry.openConnection();
connection.setUseCaches(false);

try (InputStream in = connection.getInputStream()) {
    // Đọc bytes.
}
~~~

Đây là **minh họa**, URL string phải được tạo hợp lệ theo đường dẫn hệ thống thực. Gọi `setUseCaches(false)` **trước** khi bắt đầu sử dụng connection. Nó ảnh hưởng tới chính connection đó, **không** hứa đóng mọi cache/handle khác trên toàn JVM. Không lạm dụng thay đổi default cache toàn hệ thống để “sửa” một JAR lock nếu không hiểu tác động.

Nếu code mở `JarFile` bằng constructor, quản lý owner rõ ràng bằng try-with-resources; nếu connection hoặc thư viện dùng cache chung, cần tuân đúng contract của API và tránh đóng bừa một JarFile đang được chia sẻ.

## 9. Những gì giữ loader và class v1 trong bộ nhớ

Ngay cả khi đã giải phóng JAR handle, loader cũ vẫn có thể sống vì các **strong references**. Những nguồn phổ biến:

| Nguồn tham chiếu | Dấu hiệu | Cách xử lý |
| --- | --- | --- |
| Host static map / registry | `Map<String,Object>` còn giữ plugin instance | Unregister/remove theo version |
| `Class<?>` hoặc reflection Method/Constructor cache | Host giữ metadata class plugin lâu dài | Xóa cache theo lifecycle |
| Runnable/executor | Tác vụ của plugin vẫn nằm trong queue hoặc đang chạy | Cancel/shutdown và chờ kết thúc |
| Thread do plugin tạo | Thread sống giữ Runnable/context loader | Shutdown/join theo contract |
| TCCL trên thread pool | Context loader vẫn là child đã retire | Khôi phục TCCL trong `finally` |
| ThreadLocal | Thread lâu sống giữ plugin object/class | Remove ThreadLocal từ đúng thread |
| Listener/event bus | Plugin đã đăng ký callback vào singleton host | Unregister khi stop |
| MBean/JMX registry | MBean trỏ tới implementation class | Unregister có chủ đích |
| Service/driver registry | Provider/driver/handler được giữ trong registry | Dọn qua API đăng ký tương ứng |
| Resource/stream/archive | InputStream/JarFile/ZipFile còn mở | Đóng đúng owner |
| Shutdown hook | Hook giữ object plugin hoặc loader | Remove khi được phép và hợp lệ |

### TCCL nên được phục hồi

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    // Gọi code/framework cần tìm resources hoặc SPI qua TCCL.
} finally {
    thread.setContextClassLoader(previous);
}
~~~

Đây là đoạn minh họa. Với thread pool, một thread có thể tồn tại lâu hơn plugin rất nhiều; quên khôi phục context loader sẽ giữ tham chiếu tới phiên plugin cũ. Tuy vậy, phục hồi TCCL thôi chưa giải quyết mọi reference từ thread/task/registry.

Class unloading phụ thuộc JVM/GC và ranh giới các tham chiếu. `WeakReference<ClassLoader>` có thể giúp trong test quan sát loader có thể được thu gom không, nhưng **không đặt assertion thời gian cứng** rằng GC phải unload trong vài mili-giây. Heap dump và class unloading logs giúp phân tích khi có leak.

## 10. Khi nào dùng versioned JAR thay vì ghi đè live.jar?

Nếu có quyền thiết kế lại hệ thống, tên file versioned thường là lựa chọn tốt:

~~~text
plugins/
    service-1.0.0.jar
    service-1.1.0.jar
    service-1.2.0.jar
~~~

Lợi ích:

- Không cần ghi đè file mà loader cũ đang sử dụng.
- Có thể chạy song song loader version cũ và mới trong thời gian chuyển traffic.
- Rollback dễ vì file v1 chưa bị sửa.
- Dễ ghi log chính xác version nào đang phục vụ.
- Cleanup có thể thực hiện sau khi những loader liên quan đóng và không còn handle.

Nếu cần **atomic deployment**, tải/copy bản mới vào file tạm cùng filesystem, xác minh checksum/version, rồi rename tới tên **versioned final** trước khi tạo loader mới. Không coi một thao tác `Files.copy(..., REPLACE_EXISTING)` trực tiếp lên live file là một quy trình rollout đầy đủ có rollback/atomicity. Cơ chế rename/atomic move và quyền file phụ thuộc OS/filesystem.

Khi ứng dụng có nhiều request, cần dùng routing/registry có đồng bộ để chuyển sang loader v2. Không tự đóng L1 ngay khi cập nhật registry nếu request v1 còn hoạt động.

## 11. Chẩn đoán khi file vẫn bị giữ sau close

Một checklist thực hành:

1. **Lệnh chạy host có đặt plugin JAR trên application classpath không?** Nếu có, parent có thể đã mở JAR; đóng child không đóng parent.
2. **Có hai URLClassLoader trỏ cùng JAR không?** Đóng một loader chưa giải phóng handle của loader khác.
3. **Có reader độc lập nào không?** Tìm `new JarFile`, `ZipFile`, `getResourceAsStream`, `openStream`, framework scanner.
4. **Có JarURLConnection caching không?** Kiểm tra ownership và `useCaches`; không coi mọi URL stream là do URLClassLoader quản lý.
5. **Có IOException bị bỏ qua khi close?** Log cause và suppressed exceptions.
6. **Có request/thread đang load class/resource lúc close?** Tổ chức quiescing trước, không dựa vào hành vi concurrent close không xác định.
7. **Có file watcher, antivirus, IDE, scanner hoặc process khác chạm file không?** Kiểm tra bằng công cụ quản lý handles OS.
8. **OS hiện tại là Windows hay Linux?** Khác nhau về cách rename/unlink khi file mở; “xóa được” chưa chắc FD đã đóng.
9. **JAR thuộc custom/framework class loader?** URLClassLoader API không đại diện cho mọi nested-JAR loader.
10. **Tăng memory mà file handle không tăng?** Tìm strong references giữ ClassLoader; không coi đó là cùng loại leak.

Các công cụ như Resource Monitor/Process Explorer trên Windows hoặc `lsof` trên Linux hỗ trợ xác định process đang giữ handles thật. Chúng không thay cho Java API, nhưng giúp phân biệt lỗi của loader và lỗi của một process khác. Ở chiều ngược lại, việc class unload logs không báo class v1 được thu gom **không** tự chứng minh JAR handle vẫn mở.

### Những hiểu lầm điển hình

**“Đóng URLClassLoader đồng nghĩa plugin đã bị unload.”** Không: loader close không hủy objects/classes; JVM chỉ unload khi điều kiện reachability/GC thỏa.

**“Chỉ cần gọi System.gc() rồi file sẽ không bị lock.”** Không: GC không phải API giải phóng handle; đóng đúng owner.

**“Sửa JAR tại chỗ sẽ sửa bytecode của class đã load.”** Không: tạo class loader mới để có định nghĩa class runtime mới.

**“Stream do loader mở có thể để đó vì close loader sẽ đóng.”** Dù URLClassLoader có contract về getResourceAsStream, thiết kế tốt vẫn đóng stream ngay sau khi đọc xong.

**“Linux xóa file thành công chứng minh không còn leak.”** Không: descriptor tới nội dung cũ có thể còn sống sau khi unlink.

**“Cứ đóng loader rồi thay JAR là chắc chắn chạy được trên mọi Windows.”** Không: file có thể còn được process/connection khác giữ, hoặc thiếu quyền.

**“Cứ tạo loader mới cho mỗi request là reload đơn giản.”** Không: mở thêm handles, nhân class namespaces và tăng memory/cpu. Nên dùng một loader cho mỗi **plugin version/lifecycle** đã được điều phối.

## 12. Checklist production và câu hỏi ôn tập

Checklist trước khi triển khai:

- Plugin JAR cần reload không thuộc application classpath sống lâu.
- Loader per version có owner và lifecycle rõ ràng.
- Có stop hook ngừng request, executor, threads, callbacks và registrations.
- Không concurrent class loading khi gọi `close()`.
- Mọi stream/JarFile/ZipFile độc lập có try-with-resources hoặc cleanup tương đương.
- `URLClassLoader.close()` được gọi, IOException không bị bỏ qua.
- File version cũ được dọn sau khi không còn owner giữ handle.
- Phiên bản mới dùng **loader mới**, không reuse loader đã đóng.
- Shared API/interface được định nghĩa bởi loader cha nhất quán.
- Các caches, TCCL, ThreadLocals và registries được dọn khi plugin retire.
- Có logging/monitoring file handles, class loaders và class unloading khi cần.
- Có chiến lược versioned JAR, health check và rollback.
- Quy trình được thử trên đúng OS/filesystem triển khai.

**Câu 1.** `URLClassLoader.close()` bảo đảm unload mọi class đã định nghĩa không?

**Đáp:** Không. Nó đóng loader phục vụ việc nạp class/resource mới và đóng các file do nó mở theo hợp đồng; class unloading phụ thuộc JVM/GC và tham chiếu.

**Câu 2.** Vì sao JAR vẫn bị Windows giữ sau khi đóng một URLClassLoader?

**Đáp:** Có thể parent/sibling loader, JarFile/ZipFile, JarURLConnection cache hoặc process khác vẫn giữ file handle; cần tìm đúng owner.

**Câu 3.** Vì sao sau khi thay JAR, phải tạo URLClassLoader mới?

**Đáp:** Class đã định nghĩa bởi loader cũ không tự thay bytecode; loader mới cho phép định nghĩa cùng binary name trong namespace khác.

**Câu 4.** Có nên dùng `System.gc()` để bảo đảm xóa file không?

**Đáp:** Không. Đóng stream/JAR/loader bằng API quản lý tài nguyên; GC không cung cấp timing bảo đảm và không thay thế close.

**Câu 5.** Tại sao nên triển khai JAR theo tên version riêng?

**Đáp:** Tránh ghi đè file đang được phiên cũ sử dụng, dễ chuyển traffic và rollback, chỉ xóa bản cũ khi lifecycle kết thúc.

**Câu 6.** Nếu URLClassLoader đã đóng nhưng host vẫn giữ `Class<?>` của plugin v1 thì sao?

**Đáp:** JAR handle có thể đã được đóng, nhưng class v1 vẫn được tham chiếu, vì vậy không thể kết luận nó đã được unload. Hai trạng thái phải được kiểm tra riêng.

## Tài liệu tham khảo chính thức

- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): `close()`, `getResourceAsStream` và concurrency behavior.
- [Java SE 21 — JarURLConnection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/JarURLConnection.html): giao thức `jar:` và archive connection.
- [Java SE 21 — URLConnection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLConnection.html): `setUseCaches(false)` và cache policy.
- [Java SE 21 — JarFile](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/jar/JarFile.html): đọc và đóng JAR tường minh.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): class loading lifecycle.
- [JVMS Java SE 21 §5.3](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): định nghĩa class, binary name và defining loader.
