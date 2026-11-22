# Thực hành: Tạo plugin dùng API chung và phát hiện bằng ServiceLoader

> **Java Core → ClassLoader → Thực hành.** Xây một ứng dụng Java 17 gồm **host**, **shared SPI interface** và **hai plugin JAR riêng**; dùng `URLClassLoader` và `java.util.ServiceLoader` để host phát hiện provider implementations mà không cần import lớp triển khai. Bài lab có đủ source code, cấu trúc thư mục, file `META-INF/services`, lệnh `javac`/`jar`/`java`, stdout, kiểm chứng ClassLoader identity, ví dụ TCCL và xử lý sự cố. Không cần Maven, Gradle hay thư viện ngoài JDK.

## 1. Kết quả cần đạt

Sau bài học, bạn sẽ biết:

1. Viết **API contract chung** để host và plugins có thể trao đổi qua cùng runtime interface.
2. Tạo hai plugin implement contract nhưng ở **hai JAR độc lập**.
3. Khai báo mỗi provider theo giao thức Java SPI với `META-INF/services/<service-binary-name>`.
4. Tạo `URLClassLoader` trỏ tới JAR và dùng `ServiceLoader.load(Service.class, chosenLoader)` để tìm provider.
5. Chứng minh plugin implementation do plugin loader định nghĩa, còn service interface được chia sẻ từ parent loader.
6. Giải thích khác biệt giữa explicit ClassLoader và thread context class loader (TCCL).
7. Hiểu lazy discovery, `ServiceConfigurationError`, `reload()` và vòng đời của plugin/loader.
8. Mở rộng hệ thống mà không sửa host API mỗi lần thêm plugin.

**Bài lab chính đã được biên dịch bằng `javac --release 17` và chạy thành công trên OpenJDK 21.** Chỉ cần JDK 17 trở lên có lệnh `java`, `javac` và `jar`.

## 2. Kiến trúc: host chỉ biết API, không biết implementation

~~~text
                       Application/Host Loader
                       defines demo.spi.Processor
                                  |
                    +-------------+---------------+
                    |                             |
                    v                             v
            URLClassLoader upper            URLClassLoader reverse
            build/upper.jar                 build/reverse.jar
                    |                             |
            demo.upper.UpperProcessor      demo.reverse.ReverseProcessor
            META-INF/services/...          META-INF/services/...
                    |                             |
                    +-------------+---------------+
                                  |
                       ServiceLoader<Processor>
~~~

**Bất biến quan trọng:** JVM nhận diện runtime type bằng **binary name + defining ClassLoader**. Plugin có thể được nạp bởi loader riêng nhưng phải implement **chính runtime `Processor.class` mà host biết**. Nếu mỗi plugin tự định nghĩa bản `demo.spi.Processor` riêng với child-first loader, host có thể nhận `ServiceConfigurationError: not a subtype` hoặc `ClassCastException` dù tên class/interface trùng nhau.

Cách đơn giản nhất:

- Compile API ra thư mục riêng `build/api`.
- Host có API trên application classpath.
- Compile providers với API trên **compile classpath**.
- Đóng provider JAR **không kèm** `demo/spi/Processor.class`.
- Đặt parent của mỗi `URLClassLoader` bằng `Processor.class.getClassLoader()`.
- Khi chạy host **không** đưa implementation JARs lên application classpath; chúng chỉ được thêm qua `URLClassLoader`.

Parent-first delegation đảm bảo child có thể dùng `Processor` đã được parent định nghĩa, trong khi plugin-private implementations vẫn do child định nghĩa. Đừng dùng tên interface giống nhau làm phép thử tương thích; so sánh `Class<?>` identity hoặc `isAssignableFrom`.

## 3. Cây thư mục hoàn chỉnh

Tạo source/config files như sau; thư mục `build` được lệnh build tạo:

~~~text
service-plugin-lab/
├── src/
│   ├── api/demo/spi/Processor.java
│   ├── upper/demo/upper/UpperProcessor.java
│   ├── reverse/demo/reverse/ReverseProcessor.java
│   └── host/demo/host/PluginHost.java
├── config/
│   ├── upper/META-INF/services/demo.spi.Processor
│   └── reverse/META-INF/services/demo.spi.Processor
└── build/
    ├── api/
    ├── upper/
    ├── reverse/
    ├── host/
    ├── upper.jar
    └── reverse.jar
~~~

Tất cả lệnh bên dưới chạy từ **`service-plugin-lab` làm working directory**. Nếu chạy host từ folder khác, `Path.of("build/upper.jar")` có thể trỏ sai file vì đây là đường dẫn tương đối.

### 3.1. Source API chung

**Tệp `src/api/demo/spi/Processor.java`:**

~~~java
package demo.spi;

public interface Processor {
    String id();
    String process(String text);
}
~~~

Interface cố ý chỉ dùng `String` thuộc JDK trong signature. `id()` giúp host phân biệt các providers. `process()` minh họa capability của plugin. Trong ứng dụng thực, API có thể có shared DTO, error types hoặc lifecycle methods; tất cả types đi qua boundary phải có ownership/ABI rõ ràng.

**Không nên** để method signature trả về `demo.upper.InternalData` hay một library class private mà host không truy cập được. Phân tách API chung khỏi class riêng làm giảm xung đột phiên bản và bảo vệ type identity.

## 4. Plugin A — UpperProcessor

**Tệp `src/upper/demo/upper/UpperProcessor.java`:**

~~~java
package demo.upper;

import demo.spi.Processor;
import java.util.Locale;

public final class UpperProcessor implements Processor {
    public UpperProcessor() {}

    @Override
    public String id() {
        return "upper";
    }

    @Override
    public String process(String text) {
        return text.toUpperCase(Locale.ROOT);
    }
}
~~~

Provider là **public concrete class** và có **public no-argument constructor**. Đây là contract thích hợp cho provider triển khai trong **unnamed module/classpath**. `Locale.ROOT` tránh output phụ thuộc default locale; nhập `java 17` cho kết quả `JAVA 17`.

## 5. Plugin B — ReverseProcessor

**Tệp `src/reverse/demo/reverse/ReverseProcessor.java`:**

~~~java
package demo.reverse;

import demo.spi.Processor;

public final class ReverseProcessor implements Processor {
    public ReverseProcessor() {}

    @Override
    public String id() {
        return "reverse";
    }

    @Override
    public String process(String text) {
        return new StringBuilder(text).reverse().toString();
    }
}
~~~

Nhập `java 17` cho kết quả `71 avaj`. `StringBuilder.reverse()` đủ dùng cho ví dụ ASCII này; không nên coi nó là thuật toán đảo các Unicode grapheme clusters phức tạp trong mọi ngôn ngữ.

Hai plugins không import lẫn nhau. Host cũng không import `UpperProcessor` hay `ReverseProcessor`. Đây là điểm cốt lõi để thêm implementation mới mà không sửa host source.

## 6. Khai báo SPI bằng `META-INF/services`

Với classpath provider, file cần mang tên **binary name đầy đủ của service type**:

~~~text
META-INF/services/demo.spi.Processor
~~~

**Tệp `config/upper/META-INF/services/demo.spi.Processor` có một dòng:**

~~~text
demo.upper.UpperProcessor
~~~

**Tệp `config/reverse/META-INF/services/demo.spi.Processor` có một dòng:**

~~~text
demo.reverse.ReverseProcessor
~~~

Quy tắc:

- Dùng plain UTF-8 text, không viết `.class`, `.java`, dấu slash hay biểu thức `new`.
- Mỗi dòng chứa một fully qualified **provider binary name**; có thể có nhiều providers với các dòng riêng.
- Path chính xác là `META-INF/services` (services số nhiều), phân biệt chữ hoa/thường trên nhiều môi trường.
- Descriptor phải được **copy vào chính JAR output**; chỉ đặt file ở source tree không đủ.
- Provider phải visible với loader, implement đúng shared `Processor`, constructor hợp lệ và không fail khi tạo instance.

ServiceLoader **không tự quét mọi `.class`** trong plugin JAR để tìm lớp implement một interface. Nếu không có descriptor (và không có provider declaration của named module), kết quả discovery có thể **trống** dù class implementation vẫn có trong JAR.

**Lưu ý:** Khi dùng named JPMS modules, bạn có thể khai báo `provides ... with ...` trong `module-info.java` thay vì cơ chế classpath descriptor. Bài lab này cố ý dùng **unnamed modules và SPI descriptor** để xem rõ ClassLoader.

## 7. Host Java code — chỉ biết interface `Processor`

**Tệp `src/host/demo/host/PluginHost.java`:**

~~~java
package demo.host;

import demo.spi.Processor;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ServiceLoader;

public final class PluginHost {
    static void run(String label, ClassLoader loader) {
        ServiceLoader<Processor> discovered =
                ServiceLoader.load(Processor.class, loader);

        int count = 0;
        for (Processor provider : discovered) {
            count++;
            System.out.println(label + ":" + provider.id()
                    + "=" + provider.process("java 17"));
            System.out.println(label + ":owned="
                    + (provider.getClass().getClassLoader() == loader));
        }
        System.out.println(label + ":count=" + count);
    }

    public static void main(String[] args) throws Exception {
        ClassLoader shared = Processor.class.getClassLoader();

        URL upper = Path.of("build/upper.jar")
                .toAbsolutePath().toUri().toURL();
        URL reverse = Path.of("build/reverse.jar")
                .toAbsolutePath().toUri().toURL();

        try (URLClassLoader upperLoader =
                     new URLClassLoader(new URL[] {upper}, shared);
             URLClassLoader reverseLoader =
                     new URLClassLoader(new URL[] {reverse}, shared)) {

            run("host", shared);
            run("upper", upperLoader);
            run("reverse", reverseLoader);

            System.out.println("same api="
                    + (upperLoader.loadClass(Processor.class.getName())
                        == Processor.class
                    && reverseLoader.loadClass(Processor.class.getName())
                        == Processor.class));

            Thread t = Thread.currentThread();
            ClassLoader before = t.getContextClassLoader();
            ServiceLoader<Processor> tcclServices;

            try {
                t.setContextClassLoader(upperLoader);
                tcclServices = ServiceLoader.load(Processor.class);
            } finally {
                t.setContextClassLoader(before);
            }

            System.out.println("tccl first="
                    + tcclServices.findFirst().orElseThrow().id());
        }
    }
}
~~~

Phân tích:

- `ClassLoader shared = Processor.class.getClassLoader()` chọn loader đang thực sự định nghĩa shared API. Không đoán dựa vào loader tên “system” nếu chạy trong container/custom runtime.
- `new URLClassLoader(new URL[]{upper}, shared)` tạo loader trỏ tới provider JAR, với parent là shared API loader.
- `ServiceLoader.load(Processor.class, loader)` dùng loader truyền vào để tìm provider-configuration resources và provider classes (trong lab classpath này).
- `for (Processor provider : discovered)` là bước **lazily tìm và tạo instance**. `ServiceLoader.load` tự nó chưa nhất thiết instantiate providers.
- `provider.getClass().getClassLoader() == loader` xác nhận **defining loader** của implementation trong cấu hình lab.
- `loadClass(Processor.class.getName()) == Processor.class` xác nhận **shared runtime contract identity**.
- `try-with-resources` đóng hai `URLClassLoader` khi toàn bộ ví dụ dùng xong; không gọi `close()` cho các provider objects (API demo chưa khai báo lifecycle này).

**Không áp dụng bừa `owned==true` cho mọi ServiceLoader ngoài lab**: với parent-first delegation hoặc named module providers, implementation có thể do loader khác định nghĩa. Đó không có nghĩa ServiceLoader sai; cần hiểu defining loader thực.

### 7.1. Phân biệt explicit loader với TCCL

Overload:

~~~java
ServiceLoader.load(Processor.class, upperLoader)
~~~

lấy **upperLoader** do host đưa vào, không phụ thuộc TCCL tình cờ của thread.

Overload:

~~~java
ServiceLoader.load(Processor.class)
~~~

tương đương với:

~~~java
ServiceLoader.load(
    Processor.class,
    Thread.currentThread().getContextClassLoader())
~~~

Trong `main`, TCCL được tạm đặt thành upper loader đúng lúc tạo `tcclServices`, rồi khôi phục **trước** `findFirst()`. ServiceLoader vẫn dùng loader đã chọn ban đầu, cho kết quả `upper`.

Khi sử dụng pool worker, **đừng cho rằng** TCCL của thread submitter được truyền sang worker đã tồn tại. Nếu framework chỉ dùng convenience overload, set/restore TCCL ở **chính thread thực thi discovery**, trong `try/finally`. Nếu có thể, plugin host nên ưu tiên overload hai tham số vì owner rõ ràng hơn.

## 8. Build hai plugin JAR và chạy host

Sử dụng POSIX shell (Linux/macOS/Git Bash). Từ root `service-plugin-lab`:

~~~bash
# 1. Output folders + đúng đường cho SPI descriptors.
mkdir -p build/api build/upper/META-INF/services \
         build/reverse/META-INF/services build/host

# 2. Shared API được biên dịch riêng.
javac --release 17 -d build/api \
    src/api/demo/spi/Processor.java

# 3. Providers dùng shared API ở compile classpath.
javac --release 17 -cp build/api -d build/upper \
    src/upper/demo/upper/UpperProcessor.java

javac --release 17 -cp build/api -d build/reverse \
    src/reverse/demo/reverse/ReverseProcessor.java

# 4. Copy SPI descriptor vào root output mỗi provider.
cp config/upper/META-INF/services/demo.spi.Processor \
   build/upper/META-INF/services/demo.spi.Processor

cp config/reverse/META-INF/services/demo.spi.Processor \
   build/reverse/META-INF/services/demo.spi.Processor

# 5. Đóng đúng hai JAR, không chứa shared Processor.class.
jar --create --file build/upper.jar -C build/upper .
jar --create --file build/reverse.jar -C build/reverse .

# 6. Host biên dịch chỉ với API.
javac --release 17 -cp build/api -d build/host \
    src/host/demo/host/PluginHost.java

# 7. Runtime host KHÔNG có upper.jar/reverse.jar trong classpath.
java -cp "build/api:build/host" demo.host.PluginHost
~~~

Trên Windows, `javac`/`jar` tương tự, nhưng tạo/copy thư mục bằng PowerShell/CMD và **classpath separator là `;`**:

~~~powershell
java -cp "build/api;build/host" demo.host.PluginHost
~~~

Không chạy `java -jar build/upper.jar`: đó là provider JAR không có `Main-Class`. Class có `main` nằm trong host.

### 8.1. Kiểm tra đúng artifacts trong JAR

~~~bash
jar --list --file build/upper.jar
jar --list --file build/reverse.jar
~~~

`upper.jar` phải chứa ít nhất:

~~~text
demo/upper/UpperProcessor.class
META-INF/services/demo.spi.Processor
~~~

`reverse.jar` phải chứa ít nhất:

~~~text
demo/reverse/ReverseProcessor.class
META-INF/services/demo.spi.Processor
~~~

`jar --list` có thể in thêm `META-INF/`, `MANIFEST.MF` và directory entries; không assert danh sách chỉ có hai dòng hay thứ tự in. **Không** có `demo/spi/Processor.class` trong các JAR plugin.

## 9. Stdout của lab đã kiểm chứng trên OpenJDK 21

~~~text
host:count=0
upper:upper=JAVA 17
upper:owned=true
upper:count=1
reverse:reverse=71 avaj
reverse:owned=true
reverse:count=1
same api=true
tccl first=upper
~~~

Giải thích từng nhóm:

- `host:count=0`: application/host loader biết interface, **không có** plugin descriptor JARs trên host classpath.
- `upper:upper=JAVA 17`: `upperLoader` đọc descriptor của `upper.jar` và instantiate `UpperProcessor`.
- `upper:owned=true`: implementation class do `upperLoader` định nghĩa.
- `upper:count=1`: chỉ một provider visible qua scope này.
- `reverse:reverse=71 avaj`: `reverseLoader` thấy provider riêng của `reverse.jar`.
- `reverse:owned=true` và `reverse:count=1`: một implementation do đúng reverse loader định nghĩa.
- `same api=true`: hai loaders delegate `demo.spi.Processor` về shared parent, tránh duplicate type identity.
- `tccl first=upper`: `ServiceLoader.load(Processor.class)` đã dùng TCCL upper loader lúc factory call.

Kết quả này đáng tin trong **đúng cấu hình của lab**; nếu bạn đặt plugin JARs vào host classpath, host có thêm providers, dùng parent khác hoặc custom child-first loader thì không nên kỳ vọng mọi dòng giống hệt.

## 10. ServiceLoader discovery phía sau hậu trường

Với classpath providers:

1. Caller chỉ ra `Processor.class` (một runtime class/interface cụ thể) và một ClassLoader.
2. Khi bắt đầu iteration, ServiceLoader tìm `META-INF/services/demo.spi.Processor` qua cơ chế `getResources` của loader.
3. Nó đọc các dòng binary names; có thể có comments bắt đầu `#` và dòng trống theo specification.
4. Nó nạp provider class bằng loader/module visibility rules, kiểm tra khả năng cung cấp đúng service.
5. Với classpath deployment, nó gọi **public no-argument constructor** và trả `Processor` instance.
6. Provider đã instantiate được giữ trong **provider cache của ServiceLoader instance**; iteration sau có thể thấy cached objects trước.

**Không** dùng `Class.forName("demo.upper.UpperProcessor")` từ default system loader như một replacement cho ServiceLoader. Host sẽ hard-code class name và có thể nhìn sai loader. SPI cho phép provider thêm/bớt với metadata thay vì sửa host.

### 10.1. Một descriptor nhiều providers

Một `META-INF/services/demo.spi.Processor` có thể có:

~~~text
demo.upper.UpperProcessor
demo.reverse.ReverseProcessor
~~~

Điều kiện là loader tìm được **cả hai class**. Nếu tạo một `URLClassLoader` có URLs của cả `upper.jar` và `reverse.jar`, ServiceLoader có thể tìm cả hai provider descriptors. Đây là cách triển khai nhóm plugins trong **cùng loader namespace**, khác mô hình hai loader riêng của lab.

**Bài tập snippet** bên trong `main` với `upper`, `reverse` và `shared`:

~~~java
try (URLClassLoader combined = new URLClassLoader(
        new URL[] {upper, reverse}, shared)) {

    ServiceLoader<Processor> services =
            ServiceLoader.load(Processor.class, combined);

    java.util.List<String> names = new java.util.ArrayList<>();
    for (Processor provider : services) {
        names.add(provider.id());
    }
    names.sort(String::compareTo);
    System.out.println(names);
}
~~~

Nếu cả hai JARs đúng, dòng cuối dự kiến:

~~~text
[reverse, upper]
~~~

Sắp xếp trước khi in để kết quả không dựa vào provider discovery order. Code này là **snippet mở rộng**, không nằm trong stdout của `PluginHost.java` ở mục 9.

### 10.2. Lazy loading, `findFirst`, `stream` và `reload`

~~~java
ServiceLoader<Processor> services =
        ServiceLoader.load(Processor.class, upperLoader);

// Java 9+: provider instance đầu tiên nếu có.
Processor first = services.findFirst().orElseThrow();

// Stream descriptor trước khi khởi tạo object:
services.stream().forEach(p -> {
    System.out.println(p.type().getName());
    // p.get() tạo/nhận provider instance theo contract.
});

// Xóa cache provider của ServiceLoader instance này:
services.reload();
~~~

Đây là **snippet** trong scope có `upperLoader`. `stream()` trả `ServiceLoader.Provider<S>`; `type()` và `get()` giúp inspect type, instantiate có chủ đích. `reload()` chỉ làm mới discovery/provider cache **trên ServiceLoader instance hiện tại**; nó **không** đổi loader đã chọn, không close objects và không redefine classfile của JAR trong cùng defining loader.

ServiceLoader **không thread-safe**; không dùng một instance chung cho nhiều threads vừa iterate vừa reload mà không kiểm soát đồng bộ/lifecycle.

## 11. Biến thể và lỗi cố ý để tự kiểm chứng

### 11.1. Xóa SPI descriptor khỏi JAR

Nếu `upper.jar` không có `META-INF/services/demo.spi.Processor`, khi gọi `run("upper", upperLoader)` không có provider ở plugin-scope này, có thể in `upper:count=0`. **Nhưng** phần cuối `tcclServices.findFirst().orElseThrow()` trong host main sẽ ném `NoSuchElementException` nếu không có provider nào; không nói cả ứng dụng chạy hết như trước.

### 11.2. Viết sai class name trong descriptor

Nếu viết `demo.upper.MissingProcessor`, Java sẽ không tìm provider class và có thể ném `ServiceConfigurationError` **lúc iterator/findFirst tìm provider**, không nhất thiết khi `ServiceLoader.load` được gọi. Sửa binary name theo JAR entry path; kiểm tra package trong source và `jar --list`.

### 11.3. Provider không phải subtype của shared API

Nếu plugin implement một **bản `Processor` được child-first loader tự define lại**, host đang dùng `Processor.class` từ parent; hai types không tương thích dù `Class.getName()` bằng nhau. ServiceLoader có thể ném `ServiceConfigurationError: ... not a subtype`. Nếu plugin JAR có copy API nhưng loader **vẫn parent-first**, riêng việc copy đó chưa chắc gây lỗi vì class cha có thể thắng. Phải quan sát defining loaders thực tế.

### 11.4. Constructor không public hoặc ném lỗi

Classpath provider cần public concrete class và public no-arg constructor. Sai contract hoặc constructor throw dẫn tới `ServiceConfigurationError`/cause liên quan khi instantiate. Không nên catch mọi `Throwable` rồi giả vờ provider vắng mặt.

### 11.5. Đưa plugin JAR lên host classpath

Nếu command `java -cp` bao gồm `build/upper.jar`, application loader có thể nhìn thấy provider descriptor và UpperProcessor; `host:count=0` không còn đúng. Vì parent-first, `upperLoader` cũng có thể delegate implementation về host, làm `upper:owned=false`. Đây là lỗi cấu hình ClassLoader rất phổ biến.

### 11.6. Tìm được resource nhưng không tạo được instance

Có thể kiểm tra đúng loader:

~~~java
String path = "META-INF/services/" + Processor.class.getName();
var urls = upperLoader.getResources(path);
while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());
}
~~~

Snippet cần đặt trong `main`; method có thể ném `IOException`. Có resource **không chứng minh** implementation class tồn tại, subtype đúng, constructor public hoặc dependency đã đủ. Nếu một lỗi xảy ra, xem full `ServiceConfigurationError` stack/cause.

## 12. So sánh explicit loader với TCCL

| API | Loader dùng làm điểm bắt đầu | Khi phù hợp |
| --- | --- | --- |
| `ServiceLoader.load(S.class, pluginLoader)` | Loader tường minh của plugin | Host biết owner, tránh phụ thuộc thread |
| `ServiceLoader.load(S.class)` | TCCL tại lúc factory call | Framework dùng ambient application context |
| `ServiceLoader.load(S.class, null)` | System classloader (hoặc bootstrap nếu không có system) | Không có nghĩa “không load” |
| `ServiceLoader.loadInstalled(S.class)` | Platform classloader (Java 9+) | Không phải cách chung tìm app plugin JAR |
| `ServiceLoader.load(layer, S.class)` | Named modules trong layer và các parent layers | JPMS plugin ModuleLayer |

`ServiceLoader.load(S.class)` bắt TCCL **lúc tạo** ServiceLoader, dù provider instantiation có thể diễn ra lazy **sau**. Nếu worker pool tái sử dụng thread mà còn TCCL của plugin cũ, một request mới có thể thấy nhầm providers và giữ loader cũ alive. Dùng explicit loader hoặc **set/restore TCCL trong `try/finally`** khi framework API không cho truyền loader.

Không coi TCCL là defining loader của service type. `Processor.class.getClassLoader()` vẫn là loader đã định nghĩa API theo JVM type identity.

## 13. JPMS (Java 9+) là biến thể khác, không phải bắt buộc của lab

Khi dùng named modules, provider có thể được khai báo ở `module-info.java`:

**API module:**

~~~java
module demo.api {
    exports demo.spi;
}
~~~

**Provider module:**

~~~java
module demo.upper {
    requires demo.api;
    provides demo.spi.Processor
        with demo.upper.UpperProcessor;
}
~~~

**Consumer module:**

~~~java
module demo.host {
    requires demo.api;
    uses demo.spi.Processor;
}
~~~

Đây là **ba descriptors thuộc ba named modules khác nhau**, không gộp vào một tệp. `uses` là khai báo consumer sử dụng service; `provides ... with` là khai báo provider; `requires` cho phép đọc module API; `exports` cho phép package API được truy cập.

Với named modules:

- Không bắt buộc có classpath `META-INF/services` cho provider khai báo bằng `provides`.
- Provider implementation package không cần export công khai chỉ để ServiceLoader tạo provider theo module contract.
- Provider modules phải có mặt trong **resolved module graph/layer**, không chỉ nằm tùy ý trong folder.
- `ServiceLoader.load(layer, S.class)` tìm providers trong named modules ở layer đó và parent layers, **không** tự tìm providers trong unnamed modules qua SPI files.
- Named-module provider có constructor/provider-method rules riêng; đừng lấy static `provider()` method làm giải pháp thiếu public constructor trong **classpath demo**.

Nếu chuyển sang ModuleLayer, phải viết lại build/launch module-path và module-resolution logic phù hợp; **không** chỉ thêm `module-info.java` vào JAR demo và giữ nguyên mọi kỳ vọng classpath.

## 14. Lifecycle, hot reload và độ an toàn

Trong lab, `try-with-resources` đóng `URLClassLoader` và file/JAR handles mà nó sở hữu. Tuy nhiên `URLClassLoader.close()`:

- Không hủy class đã nạp, không làm static fields reset.
- Không tự đóng HTTP/DB connections, streams hoặc threads do provider tự tạo.
- Không tự unregister listeners, `ServiceLoader` provider caches, DI/reflection maps ở host.
- Không bảo đảm class unloading/Metaspace giảm ngay.
- Không có giao thức an toàn để gọi đồng thời với thread khác đang load class; Javadoc nói kết quả load khi `close()` cạnh tranh là undefined.

Muốn cập nhật `upper.jar` từ V1 sang V2:

1. Xác minh artifact/version và tạo **loader thế hệ mới**.
2. Discover/instantiate/health-check provider V2 trước khi publish.
3. Cutover routing có synchronization/leases đúng để request mới dùng V2.
4. Drain công việc V1 đang chạy và ngừng callbacks.
5. Đóng provider-owned resources, clear caches, restore TCCL, remove ThreadLocal values.
6. Đóng old `URLClassLoader` và bỏ strong references; JVM có thể unload classes cũ khi đủ điều kiện.

`ServiceLoader.reload()` không phải hot-reload bytecode. Nếu plugin code là **untrusted**, classloader không tạo security sandbox; cần process/container/OS boundary, xác thực source/signatures và quản lý quyền thực sự.

## 15. Checklist nghiệm thu

- [ ] `Processor.java` tồn tại một bản ở `build/api`.
- [ ] Host không import concrete provider classes.
- [ ] Mỗi provider có public no-arg constructor và implements `demo.spi.Processor`.
- [ ] Hai JARs chứa implementation và `META-INF/services/demo.spi.Processor` đúng path.
- [ ] Không chứa bản duplicate `demo/spi/Processor.class` trong plugin JARs.
- [ ] `javac --release 17` biên dịch đủ bốn files.
- [ ] Host runtime classpath chỉ chứa `build/api` và `build/host`.
- [ ] `host:count=0` và mỗi plugin `count=1`.
- [ ] Output đúng `JAVA 17` và `71 avaj`.
- [ ] `upper:owned=true`, `reverse:owned=true` và `same api=true`.
- [ ] TCCL được restore trong `finally`, dòng `tccl first=upper` đúng.
- [ ] ServiceLoader không được cache VM-wide qua nhiều tenants/generations.
- [ ] Khi plugin retire, đã drain requests, clear caches và đóng resources đúng owner.
- [ ] Khi `ServiceConfigurationError`, đã kiểm tra original cause và SPI descriptor/JAR contents.

## 16. Câu hỏi tự kiểm tra

1. Shared API được nạp bởi loader nào? **Host/parent**, do `Processor.class.getClassLoader()` nhận diện.
2. Host có cần compile against `UpperProcessor` không? **Không**, chỉ cần `Processor`.
3. File nào dùng để khai báo provider trên classpath? **`META-INF/services/demo.spi.Processor`**.
4. Descriptor chứa Java source path hay provider binary name? **Binary name `demo.upper.UpperProcessor`**.
5. Plugin JAR chỉ có implementation class nhưng không có descriptor có được tự phát hiện không? **Không**, trừ cơ chế named-module provider riêng.
6. Vì sao loader của plugin nhận shared loader làm parent? **Để dùng cùng runtime `Processor.class`**.
7. `ServiceLoader.load(S.class, loader)` và một tham số khác nhau thế nào? **Explicit loader so với current thread context loader**.
8. Khi host đổi TCCL sau `ServiceLoader.load(S.class)`, ServiceLoader cũ tự đổi provider scope không? **Không**.
9. Provider class có thể do parent define khi explicit loader là child không? **Có**, tùy delegation/JPMS.
10. `ServiceLoader` tìm thấy providers ngay khi tạo đối tượng à? **Discovery/instantiation phần lớn lazy khi iterate/stream**.
11. Nếu descriptor sai class name, lỗi nào thường gặp? **ServiceConfigurationError**.
12. Nếu API bị duplicate trong child-first loader, điều gì xảy ra? **Runtime type identity mismatch, provider not subtype/cast failure**.
13. `URLClassLoader.close()` có unload classes ngay không? **Không**.
14. `reload()` có nạp class implementation V2 trong same defining loader không? **Không**.
15. `ServiceLoader.load(layer, S.class)` tìm classpath `META-INF/services` ở unnamed modules không? **Không**, dùng named-module declarations.
16. Có thể dùng hai JARs trong một loader không? **Có**, khi cùng binary namespace/dependencies tương thích.
17. Khi nào nên tạo loader riêng cho từng plugin? **Khi cần dependency isolation hoặc lifecycle/version ownership độc lập**.
18. Có nên dùng ClassLoader làm sandbox cho plugin chưa tin cậy không? **Không**, cần OS/process isolation khi có trust boundary.

## 17. Tài liệu chuẩn

1. [ServiceLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): contract của provider, classpath `META-INF/services`, named modules, explicit loader/TCCL, lazy instantiation, `reload`, errors.
2. [URLClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLClassLoader.html): tìm classes/resources từ URLs, parent delegation, `close`.
3. [ClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): defining/initiating loaders và resource lookup.
4. [ServiceConfigurationError — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceConfigurationError.html): lỗi khi SPI provider loading/creation không hợp lệ.
5. [Thread — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html): thread context ClassLoader.
6. [JVMS §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3): runtime class identity.
7. [ModuleLayer — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ModuleLayer.html): provider modules theo layer.
8. [JEP 261 — Module System](https://openjdk.org/jeps/261): `uses` và `provides ... with ...` trong module descriptors.

**Kết luận:** Một plugin classpath theo Java SPI là **implementation class + đúng `META-INF/services` file**. Host giữ shared `Processor` interface, tạo ClassLoader trỏ tới provider JAR rồi gọi `ServiceLoader.load(Processor.class, pluginLoader)`. Đừng đánh đổi shared API type identity lấy child-first tùy tiện; khi triển khai production, quản lý provider discovery, TCCL, errors, caches và lifecycle của loader theo từng plugin generation.
