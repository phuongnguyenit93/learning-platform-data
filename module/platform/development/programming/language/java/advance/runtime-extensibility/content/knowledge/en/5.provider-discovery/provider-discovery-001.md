# Chọn ServiceLoader.load theo class loader hoặc ngữ cảnh luồng (TCCL)

## 1. Vấn đề cần giải quyết khi khám phá provider

Một ứng dụng Java có thể công bố một **Service Provider Interface (SPI)**, ví dụ `Greeting`, rồi để các JAR/plugin khác cung cấp implementation. `java.util.ServiceLoader<S>` tìm provider theo metadata triển khai (trên class path hoặc trong module), thay vì buộc host gọi trực tiếp constructor của từng implementation.

Vấn đề quan trọng trong runtime extensibility là **provider nằm trong không gian nạp lớp nào**. Trong ứng dụng một class path, `ServiceLoader.load(Greeting.class)` thường tìm được provider và khiến ta tưởng cách chọn class loader không quan trọng. Trong ứng dụng dùng plugin JAR, application server, module layer, nhiều ứng dụng cùng JVM hoặc thread pool, cùng một SPI có thể cho kết quả khác nhau khi chọn loader khác nhau.

Bài này tập trung vào quyết định giữa hai overload:

```java
ServiceLoader<S> ServiceLoader.load(Class<S> service);
ServiceLoader<S> ServiceLoader.load(Class<S> service, ClassLoader loader);
```

Đây là **chữ ký dạng minh họa** để so sánh; chương trình đầy đủ và lệnh chạy nằm ở mục 5. Trong mã Java thật, kiểu `S` được suy ra từ `Class<S>`, ví dụ `ServiceLoader<Greeting> providers = ServiceLoader.load(Greeting.class);`.

**Tư tưởng cốt lõi:** Chọn loader theo *ranh giới triển khai provider mà ta chủ ý cho phép nhìn thấy*, rồi bảo đảm cả service type và provider đều thuộc mô hình class loading tương thích. TCCL là một cách truyền ngữ cảnh từ bên gọi tới thư viện chung; overload nhận `ClassLoader` là cách quyết định ngữ cảnh khám phá một cách tường minh.

## 2. Hai overload thực sự chọn loader như thế nào?

### 2.1. `load(Class<S> service)` lấy context class loader của thread

Java 17 định nghĩa:

```java
ServiceLoader.load(service)
```

tương đương với:

```java
ServiceLoader.load(service, Thread.currentThread().getContextClassLoader())
```

**Thread Context Class Loader (TCCL)** là giá trị gắn với thread, đọc bằng `getContextClassLoader()` và có thể tạm đổi bằng `setContextClassLoader(loader)`. Nó **không bắt buộc** phải bằng loader đã định nghĩa class đang gọi `ServiceLoader`, loader của SPI, hoặc system class loader.

Cần nhớ bốn điểm:

1. TCCL được lấy **ở thời điểm gọi `ServiceLoader.load(service)`**. Một `ServiceLoader` đã tạo không tự chuyển sang loader mới chỉ vì sau đó TCCL của thread đổi.
2. TCCL là ngữ cảnh của *thread hiện tại*, không phải thuộc tính của `Greeting.class` hay của plugin. Hai thread có thể khám phá các provider khác nhau nếu TCCL khác nhau.
3. Framework/container có thể chủ động đặt TCCL để thư viện ở tầng chung tìm được provider của ứng dụng/plugin. Thread pool tái sử dụng thread, nên không thể giả định TCCL đang có là ngữ cảnh phù hợp cho tác vụ mới.
4. Khi `getContextClassLoader()` trả `null`, overload hai tham số nhận `null` sử dụng **system class loader** (nếu không có thì dùng bootstrap loader) theo hợp đồng JDK. Đừng diễn giải `null` là “chỉ tìm lớp bootstrap”.

Overload một tham số ngắn gọn khi **runtime/container đã công bố rõ ai thiết lập TCCL, trong phạm vi nào, và khi nào khôi phục giá trị cũ**. Nếu không tồn tại hợp đồng đó, kết quả discovery có thể phụ thuộc thread đang chạy.

### 2.2. `load(Class<S> service, ClassLoader loader)` chọn tường minh

```java
ClassLoader pluginLoader = /* class loader mà runtime sở hữu */;
ServiceLoader<Greeting> providers =
        ServiceLoader.load(Greeting.class, pluginLoader);
```

Đây là đoạn minh họa dùng một loader do runtime tạo sẵn, chưa phải chương trình độc lập. Tham số `loader` là **điểm bắt đầu** để ServiceLoader tìm provider, cấu hình `META-INF/services` và class provider.

Khác biệt thực tế:

- Việc khám phá không phụ thuộc TCCL đang gắn trên thread đã gọi. Dùng được từ thread của scheduler, executor hay request handler khi runtime biết chính xác loader của plugin.
- Dễ thể hiện quyền sở hữu và vòng đời: registry của plugin A dùng loader A, registry plugin B dùng loader B.
- Không đồng nghĩa “chỉ nhìn thấy lớp do loader này tự định nghĩa”: parent delegation cho phép nhìn thấy lớp/tài nguyên từ parent; với **named modules** trong module layer, cơ chế tìm provider còn có quy tắc riêng của JDK.
- `load(service, null)` không có nghĩa tạo loader rỗng. JDK dùng system class loader, hoặc bootstrap khi không có system loader.

**Lưu ý về tên gọi:** `Greeting.class.getClassLoader()` trả loader *đã định nghĩa lớp SPI*, còn `Thread.currentThread().getContextClassLoader()` trả loader ngữ cảnh hiện tại. Hai giá trị có thể bằng nhau trong chương trình đơn giản nhưng có thể khác nhau trong kiến trúc plugin.

### 2.3. Bảng chọn nhanh

| Bối cảnh | Cách gọi nên cân nhắc | Lý do và điều kiện |
|---|---|---|
| Ứng dụng Java class path thông thường, TCCL đã được quản lý | `ServiceLoader.load(Spi.class)` | Gọn, nhưng vẫn phụ thuộc TCCL |
| Host biết chính xác class loader của plugin | `ServiceLoader.load(Spi.class, pluginLoader)` | Tường minh, tránh lệ thuộc thread nào gọi |
| Framework chung được gọi bên trong ứng dụng có TCCL do container thiết lập | `ServiceLoader.load(Spi.class)` | Cho phép thư viện chung khám phá provider của ứng dụng theo contract container |
| Công việc chạy trong thread pool mà TCCL có thể thuộc tác vụ trước | Overload nhận loader tường minh; hoặc quản lý TCCL trong `try/finally` | Tránh đọc sai provider và tránh giữ class loader cũ |
| Host chỉ muốn provider nằm trên class path của nó | `ServiceLoader.load(Spi.class, hostLoader)` | Chỉ đúng trong phạm vi class loader delegation và cấu hình thực tế |
| Provider nằm trong custom **named module layer** | `ServiceLoader.load(layer, Spi.class)` | Chọn layer và tổ tiên của nó; khác bài toán class path/TCCL |
| Chỉ tìm provider do platform loader nhìn thấy | `ServiceLoader.loadInstalled(Spi.class)` | Java 17 dùng platform class loader; không phải cách tìm plugin trên application class path |

Bảng là gợi ý thiết kế, không thay thế kiểm tra mô hình nạp lớp của runtime cụ thể.

## 3. Quan hệ giữa SPI, provider, loader và TCCL

Giả sử có ba phần:

- **Host/API:** interface `demo.spi.Greeting` và lớp ứng dụng `demo.app.LoaderDemo`, được application class loader tải.
- **Plugin:** class `demo.plugin.EnglishGreeting` cùng cấu hình `META-INF/services/demo.spi.Greeting`, nằm ngoài application class path.
- **Plugin class loader:** `URLClassLoader` của runtime trỏ tới thư mục/JAR plugin và nhận loader của SPI làm parent.

Khi đó:

```text
Application/host loader
   ├── demo.spi.Greeting         (SPI chung)
   └── demo.app.LoaderDemo
            ^
            | parent delegation
            |
Plugin URLClassLoader
   ├── demo.plugin.EnglishGreeting
   └── META-INF/services/demo.spi.Greeting
```

Trong kiểu bố trí này, `ServiceLoader.load(Greeting.class, pluginLoader)` có thể tìm provider, còn `ServiceLoader.load(Greeting.class)` phụ thuộc TCCL hiện tại. Nếu TCCL vẫn là host loader và host không thấy metadata của plugin, discovery sẽ trả rỗng.

**Class identity đặc biệt quan trọng.** Trong JVM, tên nhị phân giống nhau không đủ để hai class được xem là một loại: loader định nghĩa class cũng là một phần của danh tính runtime. Nếu plugin tự chứa một bản `demo.spi.Greeting` được định nghĩa bởi child loader thay vì sử dụng cùng `Greeting.class` của host, provider có thể không assignable với SPI của host, dẫn đến `ServiceConfigurationError`. Vì vậy hãy đặt API dùng chung ở parent được cả host và plugin nhìn thấy, rồi để plugin loader tải implementation và dependency riêng.

Một `ClassLoader` không phải cơ chế sandbox bảo mật đáng tin cậy. Parent delegation, visibility, module access, resource lookup và lifecycle là các quyết định cần kiểm chứng; việc dùng loader riêng tự nó không cô lập quyền truy cập CPU, bộ nhớ, file hay mạng.

## 4. Provider discovery hoạt động khi nào và từ đâu?

Với provider ở **unnamed module/class path**, JDK đọc file UTF-8:

```text
META-INF/services/<tên.nhị.phân.đầy.đủ.của.SPI>
```

Ví dụ service `demo.spi.Greeting` có file `META-INF/services/demo.spi.Greeting`, mỗi dòng khai báo tên class provider, chẳng hạn `demo.plugin.EnglishGreeting`. Class provider cần được loader liên quan nhìn thấy, implement SPI và có constructor `public` không tham số đối với provider class-path thông thường.

Với **named modules**, module của consumer khai báo `uses`, module provider khai báo `provides ... with ...`. `ServiceLoader.load(service, loader)` có quy tắc tìm các provider ở named modules, bao gồm một số provider ở cùng layer nhưng do loader khác định nghĩa; đây là lý do không nên coi tham số loader là bộ lọc “chỉ đúng một JAR”. Nếu mục tiêu chính là khoanh một module layer cụ thể, dùng overload `load(ModuleLayer layer, Class<S> service)`: overload này tìm provider trong layer đó và các layer tổ tiên, không quét unnamed modules.

Một `ServiceLoader` **không nhất thiết đọc và instantiate tất cả provider ngay khi gọi `load(...)`**. Iterator, `findFirst()` và terminal operation trên `stream()` mới kích hoạt việc khám phá và khởi tạo theo nhu cầu. Bởi vậy, thao tác tạo `ServiceLoader` thành công chưa chứng minh provider có thể dùng được; lỗi cấu hình có thể phát sinh lúc duyệt.

## 5. Ví dụ đầy đủ Java 17+: plugin được tìm bằng explicit loader và TCCL

Ví dụ này chạy trên **class path**, không sử dụng `module-info.java`. Quan trọng: **không đưa `build/plugin` lên application class path khi chạy host**; nếu thêm nó vào `java -cp`, thử nghiệm sẽ không còn kiểm tra được sự khác biệt về visibility.

### 5.1. Cây thư mục

Tạo các tệp sau từ thư mục làm việc `demo/`:

```text
demo/
├── src/
│   ├── api/demo/spi/Greeting.java
│   ├── host/demo/app/LoaderDemo.java
│   └── plugin/
│       ├── demo/plugin/EnglishGreeting.java
│       └── META-INF/services/demo.spi.Greeting
└── build/                         (tạo bằng lệnh ở bên dưới)
```

**Tệp `src/api/demo/spi/Greeting.java`:**

```java
package demo.spi;

public interface Greeting {
    String greet(String name);
}
```

**Tệp `src/plugin/demo/plugin/EnglishGreeting.java`:**

```java
package demo.plugin;

import demo.spi.Greeting;

public final class EnglishGreeting implements Greeting {
    public EnglishGreeting() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

**Tệp UTF-8 `src/plugin/META-INF/services/demo.spi.Greeting` chứa chính xác một dòng:**

```text
demo.plugin.EnglishGreeting
```

Tên file mô tả **SPI**, còn nội dung là tên class **provider**. File này là resource và phải được copy vào output của plugin bên cạnh class đã biên dịch; `javac` không tự copy resource.

**Tệp `src/host/demo/app/LoaderDemo.java`:**

```java
package demo.app;

import demo.spi.Greeting;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ServiceLoader;

public final class LoaderDemo {
    private static String describe(ServiceLoader<Greeting> loader) {
        return loader.findFirst()
                .map(provider -> provider.greet("Java"))
                .orElse("(none)");
    }

    public static void main(String[] args) throws Exception {
        Thread thread = Thread.currentThread();
        ClassLoader originalTccl = thread.getContextClassLoader();
        ClassLoader hostLoader = Greeting.class.getClassLoader();

        // Đặt TCCL về host để output không phụ thuộc launcher.
        thread.setContextClassLoader(hostLoader);
        try {
            System.out.println("host-default=" +
                    describe(ServiceLoader.load(Greeting.class)));

            URL pluginUrl = Path.of("build/plugin")
                    .toAbsolutePath().toUri().toURL();

            // Parent nạp SPI, child tìm provider và metadata riêng.
            try (URLClassLoader pluginLoader =
                    new URLClassLoader(new URL[] { pluginUrl }, hostLoader)) {
                System.out.println("explicit-plugin=" +
                        describe(ServiceLoader.load(
                                Greeting.class, pluginLoader)));

                thread.setContextClassLoader(pluginLoader);
                try {
                    System.out.println("tccl-plugin=" +
                            describe(ServiceLoader.load(Greeting.class)));
                } finally {
                    // Không để plugin loader rò vào công việc kế tiếp.
                    thread.setContextClassLoader(hostLoader);
                }

                System.out.println("after-restore=" +
                        describe(ServiceLoader.load(Greeting.class)));
            }
        } finally {
            thread.setContextClassLoader(originalTccl);
        }
    }
}
```

Không có class provider nào được import ở host. Host chỉ biết `Greeting`, còn tên provider nằm trong resource `META-INF/services`.

### 5.2. Biên dịch và chạy trên Windows PowerShell

Đứng ở thư mục `demo/`, với JDK 17+ trên `PATH`:

```powershell
New-Item -ItemType Directory -Force -Path build/api,build/host,build/plugin/META-INF/services | Out-Null
javac -d build/api src/api/demo/spi/Greeting.java
javac -cp build/api -d build/plugin src/plugin/demo/plugin/EnglishGreeting.java
Copy-Item src/plugin/META-INF/services/demo.spi.Greeting build/plugin/META-INF/services/demo.spi.Greeting
javac -cp build/api -d build/host src/host/demo/app/LoaderDemo.java
java -cp "build/api;build/host" demo.app.LoaderDemo
```

### 5.3. Lệnh tương đương trên Linux/macOS

```bash
mkdir -p build/api build/host build/plugin/META-INF/services
javac -d build/api src/api/demo/spi/Greeting.java
javac -cp build/api -d build/plugin src/plugin/demo/plugin/EnglishGreeting.java
cp src/plugin/META-INF/services/demo.spi.Greeting build/plugin/META-INF/services/demo.spi.Greeting
javac -cp build/api -d build/host src/host/demo/app/LoaderDemo.java
java -cp "build/api:build/host" demo.app.LoaderDemo
```

Lưu ý dấu phân cách class path: `;` trên Windows, `:` trên Linux/macOS. Chạy từ đúng thư mục `demo/` vì `Path.of("build/plugin")` được tính theo working directory.

### 5.4. Stdout dự kiến chính xác

```text
host-default=(none)
explicit-plugin=Hello, Java
tccl-plugin=Hello, Java
after-restore=(none)
```

**Giải thích từng dòng:**

1. `host-default=(none)`: host không đưa `build/plugin` vào application class path; TCCL tạm đặt về `hostLoader` nên không thấy resource/provider plugin.
2. `explicit-plugin=Hello, Java`: overload hai tham số dùng `pluginLoader`, có URL tới `build/plugin`. Loader này thấy cấu hình service và nạp `EnglishGreeting`; class `Greeting` được chia sẻ qua parent.
3. `tccl-plugin=Hello, Java`: tạm đặt TCCL thành `pluginLoader`; overload một tham số từ đó tương đương với overload hai tham số dùng chính loader này.
4. `after-restore=(none)`: đã trả TCCL về `hostLoader`, nên lần discovery mới lại không thấy plugin. Hai khối `finally` bảo đảm dọn ngữ cảnh thread kể cả khi có lỗi; `try-with-resources` đóng `URLClassLoader`.

Chương trình chỉ tạo **một provider** để stdout không phụ thuộc thứ tự nhiều provider. Nếu API cho phép nhiều provider, phải định nghĩa tiêu chí chọn theo metadata, tính năng hoặc priority; đừng mặc nhiên cho rằng provider đầu tiên ổn định trong mọi môi trường.

## 6. Vì sao không chọn loader theo “class hiện tại” một cách máy móc?

Trong framework, class của thư viện chung có thể được parent loader định nghĩa, còn service implementation thuộc một ứng dụng con. Ba lựa chọn dưới đây có thể khác nhau:

```java
// Loader định nghĩa API, thường phù hợp làm parent để chia sẻ SPI.
ClassLoader apiLoader = Greeting.class.getClassLoader();

// Loader định nghĩa class của thư viện đang gọi (có thể ở tầng khác).
ClassLoader libraryLoader = LoaderDemo.class.getClassLoader();

// Loader ngữ cảnh do phía gọi / container gắn vào thread.
ClassLoader contextLoader =
        Thread.currentThread().getContextClassLoader();
```

Đây là **đoạn minh họa** dùng tên class của ví dụ mục 5; không thay thế chương trình ở mục 5. Trong ví dụ class path đơn giản, `apiLoader` và `libraryLoader` cùng là application loader. Trong container nhiều tầng, `libraryLoader` có thể không tìm thấy JAR plugin; dùng nó một cách vô thức khiến thư viện thấy ít provider hơn runtime mong muốn.

**Phân biệt rõ hai câu hỏi:**

- *Class nào được coi là cùng SPI?* Phụ thuộc `Class<?>` được truyền vào và danh tính runtime của nó (tên lớp + loader định nghĩa).
- *Tìm resource và implementation ở đâu?* Phụ thuộc class loader được chọn để discovery, cộng quy tắc delegate/module của JVM.

Hai quyết định phải tương thích. Đặt một bản API trùng lặp bên trong plugin có thể làm `EnglishGreeting` không phải subtype của `Greeting` do host nhìn thấy dù tên class trong log giống nhau.

## 7. Quy tắc đặt và khôi phục TCCL an toàn

TCCL là trạng thái mutable của một thread. Nếu runtime thật sự cần tạm đặt nó (ví dụ API của bên thứ ba chỉ gọi `ServiceLoader.load(Spi.class)`), hãy bảo đảm **lưu giá trị cũ, đặt ngữ cảnh trong phạm vi ngắn nhất, và khôi phục bằng `finally`**.

Một helper minh họa (đặt bên trong class phù hợp và import `java.util.function.Supplier`):

```java
static <T> T withContextLoader(
        ClassLoader selected,
        java.util.function.Supplier<T> action) {
    Thread thread = Thread.currentThread();
    ClassLoader previous = thread.getContextClassLoader();
    thread.setContextClassLoader(selected);
    try {
        return action.get();
    } finally {
        thread.setContextClassLoader(previous);
    }
}
```

Dùng:

```java
String result = withContextLoader(pluginLoader, () ->
        ServiceLoader.load(Greeting.class)
                .findFirst()
                .map(g -> g.greet("Java"))
                .orElse("(none)"));
```

Hai khối code ở đây là **minh họa tích hợp** trong phạm vi có `Greeting` và `pluginLoader`; ví dụ đầy đủ ở mục 5 có thể biên dịch và chạy độc lập.

Không dùng `setContextClassLoader` như một cài đặt toàn JVM. Với executor dùng lại thread, một tác vụ quên restore sẽ làm tác vụ khác tìm nhầm provider hoặc giữ tham chiếu tới plugin loader đã hết vòng đời. Nếu code của bạn chủ động nắm `pluginLoader`, overload tường minh thường dễ kiểm soát hơn việc thay đổi TCCL để gọi một overload ngắn hơn.

**Chú ý:** Java `ThreadLocal` và TCCL là hai cơ chế khác nhau. Một `CompletableFuture`, executor hay scheduler không tự đảm bảo mang đúng TCCL từ request này sang task khác. Truyền loader tường minh hoặc bọc tác vụ trong scope restore khi cần.

### TCCL được chụp vào lúc tạo ServiceLoader

```java
// TCCL đang là hostLoader:
ServiceLoader<Greeting> captured =
        ServiceLoader.load(Greeting.class);

// Đổi TCCL sang pluginLoader sau đó không đổi loader đã chọn
// bên trong captured. Muốn khám phá theo pluginLoader, hãy gọi lại
// ServiceLoader.load(Greeting.class, pluginLoader).
```

Đừng suy luận rằng iterator đọc TCCL mới mỗi khi `hasNext()` hoặc `next()` được gọi. Đối tượng `ServiceLoader` đã lưu ngữ cảnh loader được chọn lúc tạo.

## 8. Named modules: class loader và module layer không phải cùng một trục

Ví dụ class path ở mục 5 không khai báo module. Khi chuyển sang Java Platform Module System (JPMS), consumer trong một **explicit named module** phải khai báo `uses` cho service, còn module provider khai báo `provides`.

Ví dụ định hướng (chỉ là các *module descriptor* minh họa, không phải bộ source độc lập để biên dịch):

```java
// module-info.java của module chứa host
module demo.host {
    requires demo.spi;
    uses demo.spi.Greeting;
}
```

```java
// module-info.java của module chứa provider
module demo.plugin {
    requires demo.spi;
    provides demo.spi.Greeting with demo.plugin.EnglishGreeting;
}
```

Module `demo.spi` trong bố trí này cần `exports demo.spi;` để host/provider truy cập service type. Trong named module, provider được chỉ định bằng `provides`; không nên giả định file `META-INF/services` của ví dụ class path thay thế đầy đủ cấu hình module.

Nếu ứng dụng tạo các plugin bằng `ModuleLayer` riêng, có thể chọn:

```java
ServiceLoader<Greeting> providers =
        ServiceLoader.load(pluginLayer, Greeting.class);
```

Đây là phác thảo khi đã có biến `pluginLayer` và module hợp lệ. Cách gọi này tìm provider ở **named modules của layer và tổ tiên**, không tìm provider trong unnamed modules. Ngược lại, overload nhận `ClassLoader` trong JDK 17 có thể tìm named-module provider thuộc các module layer có quan hệ qua loader/parent theo quy tắc JDK; không bảo đảm chỉ tìm provider do duy nhất loader đó định nghĩa.

**Khi nào dùng lớp nào?** Nếu ranh giới runtime là URL/JAR loader của plugin class path, overload nhận loader tường minh tự nhiên hơn. Nếu ranh giới là module layer do runtime tạo và quản lý, hãy cân nhắc overload nhận `ModuleLayer`. TCCL vẫn có thể hữu ích cho code dùng overload mặc định, nhưng không phải tên thay thế cho module layer.

## 9. Cache, reload và vòng đời plugin

`ServiceLoader` giữ cache những provider đã tìm/nạp trong **chính instance** của nó. `iterator()` có thể trả lại các provider đã được instantiate ở lần duyệt trước; `reload()` xóa cache và yêu cầu khám phá lại ở các lần duyệt tiếp theo.

Các điểm dễ nhầm:

- `reload()` **không biến class loader cũ thành loader có thể nạp lại một phiên bản khác của class đã định nghĩa**. Với plugin JAR thay thế, hot reload thật sự có thể cần loader mới/layer mới và chuyển toàn bộ registration, cache, tài nguyên, reference sang phiên mới.
- Sau `reload()`, iterator/stream cũ của cùng `ServiceLoader` có thể trở nên không hợp lệ; tạo iterator/stream mới. Javadoc cho phép `ConcurrentModificationException` nếu dùng iterator sau khi cache bị xóa.
- `ServiceLoader` instance **không thread-safe**. Đừng chia sẻ và duyệt cùng instance trên nhiều thread mà thiếu đồng bộ phù hợp; thường dễ hơn khi tạo instance theo phiên discovery.
- Không cache `ServiceLoader.load(Spi.class)` trong singleton dùng chung cho mọi ứng dụng trong JVM khi các ứng dụng có TCCL khác nhau. Điều đó có thể trả nhầm provider và giữ tham chiếu class loader lâu dài.
- `URLClassLoader.close()` đóng các tài nguyên mà loader sở hữu như JAR/file đã mở; nó **không tự hủy instance provider**, không tự đóng các tài nguyên nghiệp vụ của plugin và không xóa các class đã được JVM định nghĩa.
- Khi unload, runtime phải hủy callback/subscription của provider, giải phóng reference tới provider/`ServiceLoader`/loader, trả TCCL về ngữ cảnh cũ và đóng loader trong phạm vi phù hợp. Class loader chỉ có thể được thu gom sau khi không còn tham chiếu mạnh liên quan.

Vì discovery là lazy, thời điểm xuất hiện lỗi có thể nằm ở `findFirst()`, `iterator().hasNext()/next()`, xử lý `stream()` hoặc `Provider.get()`. Hãy ghi log đủ service type, loader identity, tên provider và đường dẫn metadata nếu có thể, thay vì biến mọi lỗi thành “không tìm thấy provider”.

## 10. Xử lý lỗi khám phá và phân biệt “rỗng” với “cấu hình hỏng”

Ba kết quả có ý nghĩa khác nhau:

1. **Không có provider hợp lệ nào được tìm**: iterator hết, `findFirst()` trả `Optional.empty()`; ứng dụng chọn fallback hoặc báo thiếu tính năng tùy hợp đồng.
2. **Có cấu hình provider nhưng nạp/khởi tạo thất bại**: có thể nhận `ServiceConfigurationError` (ví dụ sai tên class, constructor không dùng được, provider không implement đúng SPI, metadata hỏng).
3. **Provider nạp được nhưng logic nghiệp vụ lỗi**: callback/service method ném lỗi riêng; ServiceLoader không phải cơ chế xử lý lỗi nghiệp vụ tự động.

`ServiceConfigurationError` là subclass của `Error`, vì vậy một `catch (RuntimeException)` thông thường **không bắt** được nó. Khi runtime muốn báo lỗi cấu hình có ngữ cảnh, có thể bắt cụ thể tại ranh giới discovery:

```java
try {
    Greeting provider = ServiceLoader
            .load(Greeting.class, pluginLoader)
            .findFirst()
            .orElseThrow(() ->
                    new IllegalStateException("No Greeting provider"));
    System.out.println(provider.greet("Java"));
} catch (java.util.ServiceConfigurationError failure) {
    throw new IllegalStateException(
            "Invalid Greeting provider configuration", failure);
}
```

Đây là đoạn tích hợp dùng `pluginLoader` đã tồn tại, không phải chương trình chạy riêng. Đừng catch rộng `Throwable` để âm thầm bỏ qua provider lỗi; một cấu hình SPI sai thường cần sửa triển khai. Nếu muốn cô lập plugin hỏng để tiếp tục plugin khác, phải công bố chính sách rõ ràng và kiểm thử khả năng recover của iterator, vì JDK không bảo đảm luôn bỏ qua được provider hỏng sau mỗi lỗi.

### Đọc nguyên nhân lỗi theo biểu hiện

| Biểu hiện | Hướng kiểm tra |
|---|---|
| `findFirst()` rỗng dù JAR tồn tại | TCCL/loader có thấy đúng resource? `build/plugin` có thực sự nằm trên URL/class path của loader đang dùng? |
| `ServiceConfigurationError: Provider ... not found` | Sai tên provider, thiếu class file, sai package, thiếu dependency, visibility qua parent |
| `... not a subtype` | Có copy SPI khác loader không? Provider có implement đúng class `Greeting` của host không? |
| Constructor/provider method lỗi | Kiểm tra yêu cầu public no-args constructor khi dùng class-path provider, dependency khi init, exception gốc |
| Chạy từ CLI được, vào executor/container lại không thấy | In ra TCCL của từng luồng và loader đã chọn khi gọi `ServiceLoader.load` |
| Sau redeploy vẫn thấy provider cũ | Còn cache `ServiceLoader`/reference đến loader cũ? Có tạo loader mới và close lifecycle cũ chưa? |
| `ConcurrentModificationException` sau `reload()` | Iterator/stream đã tạo trước reload phải bỏ và tạo mới |
| Provider load được nhưng cast sai | Xác minh SPI Class object dùng chung và classloader delegation; đừng chỉ so tên class |

Phục vụ chẩn đoán, có thể in `Greeting.class.getClassLoader()`, `Thread.currentThread().getContextClassLoader()` và loader explicit đang dùng. Không dựa vào chuỗi `toString()` của loader để đánh giá identity duy nhất; có thể so reference hoặc dùng identity trong log có ngữ cảnh.

## 11. Kiểm thử contract lựa chọn class loader

Với một runtime hỗ trợ plugin, nên có các case tích hợp xác nhận đúng ranh giới:

| Tình huống | Kết quả mong muốn |
|---|---|
| Host class path chỉ chứa API/host, plugin ở loader riêng | Overload mặc định với host TCCL không thấy plugin |
| `load(Spi.class, pluginLoader)` với metadata chính xác | Provider plugin được nạp; cast theo SPI của host thành công |
| Đặt TCCL thành plugin loader rồi dùng overload mặc định | Provider tương đương với explicit loader trong bố trí đơn giản |
| Khôi phục TCCL rồi gọi lại overload mặc định | Không giữ nhầm loader của plugin |
| Tạo ServiceLoader trước khi đổi TCCL | Instance cũ vẫn khám phá theo loader đã chọn khi tạo |
| Resource service tồn tại nhưng class provider không thấy | Báo lỗi cấu hình, không coi như tập provider rỗng bình thường |
| Plugin mang bản API duplicate do loader khác định nghĩa | Phát hiện lỗi class identity / assignability |
| Nhiều plugin loader độc lập | Mỗi lượt discovery dùng đúng loader, không lẫn provider ngoài ranh giới chủ ý |
| Reload/hot swap | Tạo vòng đời và class loader mới khi cần; không giữ instance/tài nguyên cũ |
| Thread pool xử lý nhiều tác vụ | TCCL được restore kể cả khi provider ném lỗi; không rò ngữ cảnh qua task |

Đừng assert thứ tự tổng quát của provider ở nhiều module/JAR khi JDK không bảo đảm; với nhiều provider, sắp xếp hoặc chọn bằng quy tắc ứng dụng sau discovery.

## 12. Quy tắc triển khai thực tế

- **Chọn chủ sở hữu loader:** Runtime tạo/quản lý loader plugin; thư viện không tùy tiện sử dụng `ClassLoader.getSystemClassLoader()` nếu container cung cấp ranh giới khác.
- **Chọn overload theo hợp đồng:** Nắm loader thì truyền explicit; chỉ dựa TCCL khi đã biết ai thiết lập và khôi phục; dùng `ModuleLayer` cho discovery scoped theo named module layer.
- **Giữ một SPI chung:** Host và plugin phải nhìn thấy cùng class của hợp đồng; provider implementation có thể ở loader/layer riêng.
- **Kiểm chứng packaging:** Có đúng `META-INF/services/<SPI>` trong output class path hoặc `uses/provides` trong module descriptor, provider được nạp thực sự, constructor/provider method tương thích.
- **Quản lý vòng đời:** `ServiceLoader` có cache và không thread-safe; hot reload đòi hỏi xử lý reference, active subscription, tài nguyên và class loader, không chỉ gọi `reload()`.
- **Đo được kết quả:** Test cả trường hợp tìm thấy, không tìm thấy, cấu hình sai, thread pool đổi ngữ cảnh và unload/redeploy.

Tài liệu chuẩn để đối chiếu: [Java SE 17 `ServiceLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html) và [Java SE 17 `ClassLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html). Hai API này định nghĩa chính xác overload, module discovery, cache, lỗi và hợp đồng TCCL.
