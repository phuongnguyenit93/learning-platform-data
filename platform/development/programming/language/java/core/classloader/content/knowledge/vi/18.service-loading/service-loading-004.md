# `ServiceLoader.load` với loader tường minh hoặc loader ngữ cảnh

> **Java Core → ClassLoader → Nạp dịch vụ.** Bài học giải thích sự khác nhau giữa `ServiceLoader.load(Service.class)` (dùng **thread context class loader – TCCL**) và `ServiceLoader.load(Service.class, chosenLoader)` (dùng **loader tường minh**), cách đóng gói providers trong JAR, tác động của class-loader delegation, cơ chế tìm providers trong unnamed/named modules, và quản lý cache/vòng đời an toàn. Thực hành chủ đạo dùng **Java 17+**; các API module/stream xuất hiện từ Java 9.

## 1. Câu trả lời trọng tâm

`java.util.ServiceLoader<S>` là API chuẩn để tìm **implementations (service providers)** của một interface/abstract service type `S`, mà consumer không cần hard-code tên từng class triển khai.

Có hai cách gọi thường gặp:

~~~java
// (1) Dựa vào TCCL của thread hiện tại.
ServiceLoader<MyService> viaContext =
        ServiceLoader.load(MyService.class);

// (2) Nêu rõ class loader dùng làm điểm bắt đầu tìm provider.
ClassLoader chosenLoader = obtainPluginLoader();
ServiceLoader<MyService> viaExplicit =
        ServiceLoader.load(MyService.class, chosenLoader);
~~~

Đây là **snippet minh họa**, chưa phải file Java độc lập; `MyService` và `obtainPluginLoader` do ứng dụng cung cấp.

**Quy tắc chính thức của Java SE:**

~~~java
ServiceLoader.load(service)
~~~

**tương đương với:**

~~~java
ServiceLoader.load(
        service,
        Thread.currentThread().getContextClassLoader())
~~~

Nghĩa là overload một tham số phụ thuộc **TCCL tại thời điểm tạo `ServiceLoader`**, trong khi overload hai tham số sử dụng **loader bạn truyền vào**. Đây không phải lựa chọn ngẫu nhiên theo package của service interface.

### Bảng phân biệt nhanh

| Cách gọi | Loader làm điểm bắt đầu khám phá providers | Thường dùng khi |
| --- | --- | --- |
| `ServiceLoader.load(S.class)` | TCCL của thread **đang gọi `load`** | Framework cần lựa chọn provider theo caller/application context |
| `ServiceLoader.load(S.class, pluginLoader)` | `pluginLoader` đã chọn | Plugin host/container muốn cách tìm có kiểm soát, không lệ thuộc thread hiện tại |
| `ServiceLoader.load(S.class, null)` | **System class loader**, hoặc bootstrap nếu không có system loader | Cần fallback công khai theo Java SE API; `null` không mang nghĩa “không tìm gì” |
| `ServiceLoader.loadInstalled(S.class)` | **Platform class loader** trên Java 9+ | Chỉ cần installed/platform providers; thường **không** thấy application classpath/module-path providers |
| `ServiceLoader.load(layer, S.class)` | **ModuleLayer** chỉ định cùng các parent layers | Plugin vận hành qua JPMS module layers; chỉ tìm named-module providers |

**TCCL khác defining loader.** Loader định nghĩa `S.class`, loader định nghĩa provider implementation và TCCL có thể là những đối tượng khác nhau. Kết quả chỉ hợp lệ khi provider **assignable** tới đúng runtime `S.class` mà consumer đưa vào.

## 2. Vì sao ServiceLoader cần context class loader?

Giả sử một thư viện nền tảng được classloader cha nạp, còn một ứng dụng/plugin có classloader con:

~~~text
               Platform / parent / host loader
                   |
                   +-- api.PaymentService
                   +-- framework.Discovery
                   |
                   v
                Plugin loader
                   |
                   +-- impl.CardPayment
                   +-- META-INF/services/api.PaymentService

Framework ở parent muốn tìm implementation ở child:
  Chỉ dùng defining loader của Framework => có thể không thấy plugin
  Chọn TCCL = plugin loader => có thể tìm provider
  Truyền plugin loader rõ ràng => không cần thay TCCL
~~~

Parent-first delegation thông thường chỉ cho **child hỏi parent**, chứ không làm parent tự động tìm mọi class/resource của child. ServiceLoader dùng TCCL trong convenience overload để framework do parent nạp vẫn có một **điểm nhìn** vào providers được triển khai trong child/application loader.

Điều đó **không** làm TCCL trở thành parent của mọi class hay thay JVM class resolution của bytecode:

- `Framework.class.getClassLoader()` vẫn là loader **định nghĩa** Framework.
- `PaymentService.class` phải là shared contract đúng runtime identity.
- TCCL là một **tham chiếu trên đối tượng Thread**, có thể thay qua `getContextClassLoader`/`setContextClassLoader`.
- Chỉ những API **chủ động dùng TCCL** (như overload `ServiceLoader.load(S.class)`) mới bị ảnh hưởng trực tiếp.
- Với explicit loader, người gọi có thể chọn plugin loader mà **không cần thay** TCCL của worker thread.

### 2.1. `ServiceLoader.load(S.class)` lấy TCCL vào lúc nào?

**Lúc bạn gọi `ServiceLoader.load(S.class)` để tạo đối tượng loader**, không phải liên tục hỏi lại TCCL trước mỗi `iterator().next()`. Provider discovery/instantiation lại diễn ra **lazily**, nên thời điểm **chọn loader** và thời điểm **tạo provider object** không nhất thiết trùng nhau.

Ví dụ ý niệm:

~~~java
Thread thread = Thread.currentThread();
ClassLoader saved = thread.getContextClassLoader();

ServiceLoader<MyService> serviceLoader;
try {
    thread.setContextClassLoader(pluginLoader);
    serviceLoader = ServiceLoader.load(MyService.class);
} finally {
    thread.setContextClassLoader(saved);
}

// Sau khi restore TCCL, serviceLoader vẫn dùng loader đã chọn
// ở lúc ServiceLoader.load(...) được gọi.
for (MyService provider : serviceLoader) {
    use(provider);
}
~~~

Đây là snippet trong ứng dụng có `MyService`, `pluginLoader` và `use` hợp lệ. Việc đổi TCCL của thread **sau** khi tạo đối tượng `ServiceLoader` không chuyển đối tượng đó sang loader khác.

**Không suy luận rằng loader đã chọn chắc nhìn thấy provider.** Classpath, parent delegation, `META-INF/services`, module graph và class identity vẫn phải phù hợp.

## 3. Nạp provider như thế nào? Classpath và module path

Một service có thể có **0, 1 hoặc nhiều providers**. Provider không nhất thiết được tạo ngay khi bạn gọi factory `load`; người gọi duyệt qua `iterator()`, `stream()` hoặc `findFirst()` để thực sự khám phá/khởi tạo theo API.

### 3.1. Provider ở classpath/unnamed module

Với interface:

~~~java
package demo.spi;

public interface GreetingService {
    String greet();
}
~~~

JAR cung cấp provider cần:

1. Có class triển khai, ví dụ `demo.plugin.EnglishGreeter implements demo.spi.GreetingService`.
2. Có file cấu hình đúng tên resource:

~~~text
META-INF/services/demo.spi.GreetingService
~~~

3. Nội dung file mã hóa UTF-8 có **binary name** của implementation:

~~~text
demo.plugin.EnglishGreeter
~~~

4. Resource và implementation đều **visible** qua loader mà `ServiceLoader` dùng để tìm. Provider class trong unnamed module thường cần **public class** có **public no-argument constructor** để ServiceLoader tạo instance.

File cấu hình có thể chứa nhiều tên provider, mỗi dòng một tên. Dòng rỗng và comment `#` có cách xử lý theo đặc tả; các tên phải đúng binary names. Một tên sai, một provider không implement interface đúng runtime identity, hoặc constructor sai có thể gây `ServiceConfigurationError`.

**Đừng nhầm** `META-INF/services` với một API kiểm tra folder hệ điều hành. ServiceLoader tìm **resources thông qua classloader** (thường là `getResources("META-INF/services/"+serviceName)` với providers trong unnamed modules), nên việc resource được đóng gói vào JAR đúng đường quan trọng hơn vị trí thư mục làm việc.

### 3.2. Provider ở named modules (JPMS)

Từ Java 9, provider có thể khai báo bằng `module-info.java`:

~~~java
module demo.provider {
    requires demo.api;
    provides demo.spi.GreetingService
        with demo.provider.EnglishGreeter;
}
~~~

Consumer module (ví dụ `demo.consumer`) phải khai báo:

~~~java
module demo.consumer {
    requires demo.api;
    uses demo.spi.GreetingService;
}
~~~

API `demo.api` export package `demo.spi`:

~~~java
module demo.api {
    exports demo.spi;
}
~~~

Đây là **ba module descriptors minh họa**, không phải một file Java duy nhất. Với caller nằm trong **explicit named module**, `uses` có ý nghĩa bắt buộc theo ServiceLoader contract; thiếu `uses` có thể gây `ServiceConfigurationError` khi gọi `load`. `requires` bảo đảm đọc module sở hữu service type nếu service nằm ở module khác.

**Không nhầm:**

- `requires`: module dependency/readability.
- `uses`: khai báo caller tiêu thụ service.
- `provides ... with ...`: provider module công bố implementation.
- `exports`: cho public package API được truy cập; provider implementation class không nhất thiết phải được export như một API công khai thông thường.
- Module phải nằm trong **resolved graph/layer** phù hợp; chỉ đặt JAR trên module path không đồng nghĩa module đó đang hiện diện trong graph.

Khi dùng overload `load(S.class, loader)` trên JDK 9+, ServiceLoader có thể tìm providers trong **named modules** liên quan đến loader/module layer trước khi đọc provider-configuration files trong **unnamed modules**. Vì thế explicit loader **không có nghĩa “chỉ quét JAR URLs của loader này”**.

## 4. Thực hành hoàn chỉnh: explicit loader và TCCL cho plugin JAR

Bài lab này cố ý tách **host API/application** khỏi **provider JAR**. Chúng ta sẽ chứng minh rằng:

- Host loader không nhìn thấy provider vì provider không nằm trên host classpath.
- Truyền `pluginLoader` tường minh thì thấy provider.
- Gọi `load(S.class)` khi TCCL là host thì không thấy.
- Tạo `ServiceLoader` khi TCCL là plugin, **sau đó khôi phục TCCL trước khi duyệt** thì vẫn thấy provider.

### 4.1. Cây thư mục

~~~text
service-loader-lab/
├── src/
│   ├── api/demo/spi/GreetingService.java
│   ├── plugin/demo/plugin/EnglishGreeter.java
│   └── host/demo/host/ServiceLookupDemo.java
├── config/
│   └── META-INF/services/demo.spi.GreetingService
└── build/                     (các lệnh bên dưới tạo)
    ├── api/
    ├── plugin/
    ├── host/
    └── provider.jar
~~~

Tệp **`src/api/demo/spi/GreetingService.java`**:

~~~java
package demo.spi;

public interface GreetingService {
    String greet();
}
~~~

Tệp **`src/plugin/demo/plugin/EnglishGreeter.java`**:

~~~java
package demo.plugin;

import demo.spi.GreetingService;

public final class EnglishGreeter implements GreetingService {
    public EnglishGreeter() { }

    @Override
    public String greet() {
        return "hello from plugin";
    }
}
~~~

Tệp cấu hình **`config/META-INF/services/demo.spi.GreetingService`** có **chính xác một dòng**:

~~~text
demo.plugin.EnglishGreeter
~~~

Tệp **`src/host/demo/host/ServiceLookupDemo.java`**:

~~~java
package demo.host;

import demo.spi.GreetingService;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.ServiceLoader;

public final class ServiceLookupDemo {
    private static String values(
            ServiceLoader<GreetingService> services) {
        List<String> result = new ArrayList<>();
        for (GreetingService service : services) {
            result.add(service.greet());
        }
        return result.toString();
    }

    public static void main(String[] args) throws Exception {
        ClassLoader hostLoader = GreetingService.class.getClassLoader();
        Thread caller = Thread.currentThread();
        ClassLoader originalTccl = caller.getContextClassLoader();
        URL jar = Path.of("build", "provider.jar")
                .toAbsolutePath().toUri().toURL();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] {jar}, hostLoader)) {

            // Kiểm soát TCCL của chương trình: không giả định môi trường.
            caller.setContextClassLoader(hostLoader);
            System.out.println("context-host="
                    + values(ServiceLoader.load(GreetingService.class)));
            System.out.println("explicit-host="
                    + values(ServiceLoader.load(
                            GreetingService.class, hostLoader)));

            System.out.println("explicit-plugin="
                    + values(ServiceLoader.load(
                            GreetingService.class, pluginLoader)));

            caller.setContextClassLoader(pluginLoader);
            ServiceLoader<GreetingService> captured =
                    ServiceLoader.load(GreetingService.class);

            // Restore TRƯỚC khi lặp qua ServiceLoader.
            caller.setContextClassLoader(hostLoader);
            System.out.println("captured-after-change="
                    + values(captured));
        } finally {
            caller.setContextClassLoader(originalTccl);
        }
    }
}
~~~

**Điểm an toàn của thiết kế:** `URLClassLoader` có parent là loader định nghĩa shared service interface, vì thế `EnglishGreeter` implement **chính cùng `demo.spi.GreetingService`** mà host truyền vào `ServiceLoader.load`. Plugin JAR **không được** chứa một bản `demo/spi/GreetingService.class` được child loader tự define lại.

### 4.2. Biên dịch và đóng JAR (Linux/macOS, POSIX shell)

Từ thư mục `service-loader-lab`:

~~~bash
mkdir -p build/api build/plugin build/host \
    build/plugin/META-INF/services

# 1. Service interface được biên dịch vào host/shared API.
javac --release 17 -d build/api \
    src/api/demo/spi/GreetingService.java

# 2. Plugin biên dịch với API của host.
javac --release 17 -cp build/api -d build/plugin \
    src/plugin/demo/plugin/EnglishGreeter.java

# 3. Copy provider configuration vào đúng vị trí trong JAR.
cp config/META-INF/services/demo.spi.GreetingService \
    build/plugin/META-INF/services/demo.spi.GreetingService

# 4. Gói CHỈ plugin implementation và metadata, không gói API.
jar --create --file build/provider.jar -C build/plugin .

# 5. Host main class dùng API, không có plugin JAR ở classpath.
javac --release 17 -cp build/api -d build/host \
    src/host/demo/host/ServiceLookupDemo.java

java -cp "build/api:build/host" demo.host.ServiceLookupDemo
~~~

Trên Windows, dùng lệnh tạo thư mục/copy phù hợp PowerShell và đổi dấu phân tách classpath thành **`;`**:

~~~powershell
java -cp "build/api;build/host" demo.host.ServiceLookupDemo
~~~

Khi tự lập thư mục/file bằng IDE, đảm bảo đường `META-INF/services/demo.spi.GreetingService` trong JAR đúng cả chữ hoa/thường; `jar --list --file build/provider.jar` có thể xác minh.

### 4.3. Stdout kỳ vọng (Java 17+ trong cấu hình lab)

~~~text
context-host=[]
explicit-host=[]
explicit-plugin=[hello from plugin]
captured-after-change=[hello from plugin]
~~~

**Giải thích chính xác:**

1. `context-host=[]`: TCCL bị đặt thành host loader, nên `ServiceLoader.load(S.class)` chỉ thấy nguồn provider host có thể tìm. Bài lab không triển khai một provider nào trên host classpath.
2. `explicit-host=[]`: dù TCCL có là gì, overload hai tham số chọn **hostLoader** một cách tường minh.
3. `explicit-plugin=[hello from plugin]`: loader con có URL tới `provider.jar`, tìm được `META-INF/services` và định nghĩa `EnglishGreeter`; interface được parent định nghĩa.
4. `captured-after-change=[hello from plugin]`: `ServiceLoader` được **tạo khi TCCL là plugin loader**, rồi caller khôi phục TCCL về host **trước khi iterator bắt đầu**. ServiceLoader vẫn giữ loader đã chọn ban đầu.
5. `try-with-resources` đóng `pluginLoader` sau khi đã duyệt xong providers; `finally` khôi phục TCCL bất kể việc khám phá providers thành công hay ném lỗi.

Đây là output của **thí nghiệm được cấu hình**, không phải một lời hứa cho mọi ứng dụng vốn có providers bổ sung trong host runtime. Nếu host có provider khác cùng service, kết quả sẽ khác theo deployment thực tế.

### 4.4. Thử các thay đổi để hiểu cơ chế

- **Bỏ file `META-INF/services/...` khỏi JAR:** ServiceLoader dạng classpath sẽ không tự dò toàn bộ classes để tìm implementation; hai dòng sử dụng plugin thường trả `[]`.
- **Ghi nhầm FQCN trong file cấu hình:** khi duyệt provider có thể ném `ServiceConfigurationError` với nguyên nhân “provider ... not found”.
- **Đưa provider JAR lên host classpath:** host loader có thể tìm provider, khiến ranh giới kiểm thử “host trống, plugin có provider” không còn đúng.
- **Đổi parent plugin loader thành platform loader mà không cung cấp shared API:** provider có thể không tìm thấy `demo.spi.GreetingService`, hoặc type identity không khớp nếu plugin tự mang bản API khác.
- **Đổi TCCL sau khi gọi `ServiceLoader.load(S.class)`:** không làm đối tượng `ServiceLoader` đang giữ chuyển sang loader mới.

## 5. Explicit loader: chủ động chọn context thay vì phụ thuộc thread

Trong plugin manager, lựa chọn tường minh thường an toàn và rõ ràng:

~~~java
ServiceLoader<PluginService> providers =
        ServiceLoader.load(PluginService.class, pluginLoader);

for (PluginService provider : providers) {
    register(provider);
}
~~~

Snippet này cần `PluginService`, `pluginLoader`, `register` trong project. Ưu điểm là API thể hiện **ý định lựa chọn loader** ngay tại call site; executor worker có TCCL host hay plugin khác không làm thay đổi loader được truyền vào.

Tuy nhiên explicit loader vẫn **không phải “bỏ qua delegation”**:

- Với `URLClassLoader` mặc định, tìm resources/classes thường phụ thuộc **parent-first behavior**.
- `ServiceLoader.load(S.class, pluginLoader)` trên JDK 9+ có thể khám phá **named-module providers** liên quan đến module layer, không chỉ đọc cấu hình trong `pluginLoader.getURLs()`.
- Service contract phải accessible và có đúng class identity; `S.class` do host đưa vào không được tự thay bởi bản `S` plugin định nghĩa.
- ServiceLoader mới cũng có **provider cache riêng**. Việc đổi một biến `ClassLoader` ở bên ngoài không biến đổi các ServiceLoader đã tạo trước đó.

Khi host có các plugins thuộc nhiều tenants, hãy gắn service discovery với **plugin context/loader cụ thể**, không dựa vào TCCL tình cờ của thread gọi.

### 5.1. Khi đối số `loader` là null

Theo Javadoc của `load(Class<S>, ClassLoader)`:

~~~java
ServiceLoader<MyService> viaSystem =
        ServiceLoader.load(MyService.class, null);
~~~

Nếu loader là null, API dùng **system class loader** (hoặc bootstrap nếu system loader không có). Nó **không** có nghĩa “dùng bootstrap ngay lập tức”, “không tìm providers” hoặc “dùng TCCL lúc đó”.

Phân biệt hai tình huống:

~~~java
ServiceLoader.load(MyService.class, null);
ServiceLoader.load(MyService.class);
~~~

Lệnh đầu chọn system/bootstrap fallback. Lệnh thứ hai đọc TCCL; nếu TCCL cũng null, fallback của overload hai tham số dẫn đến system/bootstrap như trên. Nếu TCCL là plugin loader, hai lệnh **có thể cho kết quả khác nhau**.

### 5.2. `loadInstalled` không thay cho plugin discovery

~~~java
ServiceLoader<MyService> installed =
        ServiceLoader.loadInstalled(MyService.class);
~~~

Trên Java 9+, API này dùng **platform class loader**, thường không thấy provider deployment trên application classpath/module path. Nó không phải lựa chọn chung để tìm plugin JAR do ứng dụng phát hành. Đừng lấy tên “installed” để suy ra Java vẫn có `lib/ext` extension mechanism như Java 8.

## 6. Khi nào nên chủ động thay TCCL?

Có frameworks hoặc libraries chỉ gọi overload một tham số mà **không cho bạn truyền loader**. Khi đó có thể đặt TCCL xung quanh một operation:

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    framework.discoverAndRun();
} finally {
    thread.setContextClassLoader(previous);
}
~~~

Đây là **snippet**, cần `framework` và `pluginLoader` trong scope. `try/finally` quan trọng vì:

- Phương thức framework có thể ném exception.
- Worker của một `ExecutorService` thường được **tái sử dụng**. Nếu không restore, task tiếp theo có thể tìm nhầm providers của plugin trước.
- TCCL là một **strong reference** tới loader. Một thread tồn tại lâu (pool worker, scheduler) giữ plugin loader đã stop có thể ngăn class unloading và khiến hot reload giữ JARs/Metaspace lâu hơn.
- Việc set TCCL không tự truyền sang một worker đã tồn tại; lúc `framework.discoverAndRun()` chạy trên thread khác, thread ấy phải có TCCL đúng **tại lúc thực tế gọi `ServiceLoader.load`**.

Nếu đã có overload hai tham số và có thể gọi trực tiếp, **ưu tiên explicit loader** để giảm thay đổi thread context ngoài ý muốn.

### 6.1. TCCL, `new Thread` và thread pool

Trong cấu hình Thread tạo thông thường, child thread **kế thừa TCCL tại thời điểm thread object được tạo**, không phải khi `start()`. Thread pool thường có workers sinh ra trước và tái sử dụng; `executor.submit(runnable)` **không bảo đảm** worker tự lấy TCCL của submitter.

Ví dụ:

~~~java
ExecutorService executor = Executors.newSingleThreadExecutor();

// Đây chỉ là ví dụ ý tưởng:
Thread.currentThread().setContextClassLoader(pluginLoader);
executor.submit(() -> ServiceLoader.load(PluginService.class));
// Không có bảo đảm worker nhìn pluginLoader nếu worker đã tồn tại.
~~~

Đây là snippet minh họa, **không** phải phương án propagation chuẩn. Ngoài imports và variables, nó thiếu restore TCCL của caller và chưa duyệt providers. Một thiết kế đúng phải capture loader từ plugin context và **đặt vào worker ngay trong task**, hoặc truyền tường minh vào `ServiceLoader.load`.

### 6.2. Wrapper propagation cho executor task (Java 17+)

Tệp **`ServiceContextTasks.java`**:

~~~java
import java.util.concurrent.Callable;

public final class ServiceContextTasks {
    private ServiceContextTasks() { }

    public static <T> Callable<T> withTccl(
            ClassLoader desired,
            Callable<T> operation) {
        return () -> {
            Thread current = Thread.currentThread();
            ClassLoader previous = current.getContextClassLoader();
            try {
                current.setContextClassLoader(desired);
                return operation.call();
            } finally {
                current.setContextClassLoader(previous);
            }
        };
    }
}
~~~

~~~bash
javac --release 17 ServiceContextTasks.java
~~~

Class helper hợp lệ nhưng không có `main`. Cách gọi từ code có `ExecutorService executor` và `pluginLoader`:

~~~java
var future = executor.submit(
    ServiceContextTasks.withTccl(pluginLoader, () -> {
        var services = ServiceLoader.load(PluginService.class);
        return services.findFirst().orElse(null);
    })
);
PluginService service = future.get();
~~~

Snippet yêu cầu imports/biến/context ngoại vi, đồng thời cần quản lý lifecycle provider trả về. Khi method `ServiceLoader.load` được gọi trong worker, TCCL đã là `pluginLoader`. `finally` restore khi operation thành công hay thất bại. Trong multi-tenant app, truyền `pluginLoader` từ context do host quản lý, không copy một giá trị TCCL có thể đã bị task khác làm bẩn.

**Lưu ý:** `withTccl` chỉ áp dụng cho **operation đồng bộ bên trong callback**. Nếu callback spawn async tasks khác mà không truyền loader tiếp, chúng không được đảm bảo cùng context.

## 7. Lazy discovery, caching và `reload()`

Nhiều hiểu nhầm phát sinh vì `ServiceLoader.load` chỉ **tạo đối tượng loader**. Providers được tìm/khởi tạo khi bạn thực sự duyệt:

~~~java
ServiceLoader<MyService> services =
        ServiceLoader.load(MyService.class, chosenLoader);

// Tại đây chưa thể kết luận mọi provider đã được instantiate.
for (MyService provider : services) {
    System.out.println(provider);
}
~~~

- `iterator()` tìm và **instantiate** providers lazily; `hasNext`/`next` có thể ném `ServiceConfigurationError`.
- Providers đã được load vào **cache của chính `ServiceLoader`**; lần duyệt sau thường nhận các providers đã cache trước rồi tiếp tục tìm các provider chưa dùng.
- `findFirst()` (Java 9+) trả `Optional<S>` với provider đầu tiên, nếu có; không bảo đảm provider đầu tiên trong toàn hệ thống là ưu tiên ổn định trừ khi deployment/module rules cụ thể cho biết.
- `stream()` (Java 9+) trả `Stream<ServiceLoader.Provider<S>>`; `provider.type()` cho biết provider type và `provider.get()` tạo/lấy instance theo contract. Nó cho phép inspect/filter types mà chưa bắt buộc instantiate tất cả providers.
- `reload()` **xóa provider cache** để những lần duyệt sau tìm từ đầu; nó **không** biến `ServiceLoader` sang một classloader khác và **không** unload các runtime classes đã nạp.

### 7.1. Đừng hiểu `reload` là nạp lại JAR/class

~~~java
ServiceLoader<MyService> services =
        ServiceLoader.load(MyService.class, pluginLoader);
services.reload();
~~~

Kết quả không bảo đảm plugin bytecode trên disk sẽ được VM định nghĩa lại. Cùng một defining classloader không thể define cùng binary name nhiều lần; muốn hot reload implementation mới thường phải tạo **plugin loader thế hệ mới**, chuyển service routing, dừng và close generation cũ, đồng thời bỏ references.

Sau `reload()`, các iterators/streams đã tạo trước đó **không nên sử dụng tiếp**; API có cơ chế fail-fast (`ConcurrentModificationException`) nếu cache bị xóa trong khi đang duyệt.

### 7.2. `ServiceLoader` không thread-safe

Javadoc nêu rõ **instances of `ServiceLoader` are not safe for use by multiple concurrent threads**. Đừng đưa một instance ServiceLoader dùng chung cho nhiều worker vừa `iterator()` vừa `reload()` mà không có orchestration phù hợp.

Cách quản lý thường tốt hơn:

- Tạo ServiceLoader **theo plugin/request/context** khi cần discovery.
- Duyệt và chọn provider **ở một thread/giai đoạn quản lý**, sau đó publication các service instances theo đồng bộ phù hợp.
- Tách provider instance thread-safety khỏi thread-safety của `ServiceLoader`; provider có thể không thread-safe ngay cả khi discovery đã xong.
- Không cache `ServiceLoader.load(S.class)` trong **static singleton toàn JVM** cho nhiều ứng dụng/TCCL khác nhau; Javadoc cảnh báo sai context và memory leak. Nếu cần cache, khóa theo đúng **service type + loader/layer + lifecycle** và có cleanup khi plugin stop.

## 8. Xử lý lỗi `ServiceConfigurationError` chính xác

`ServiceConfigurationError` **extends `Error`**, không phải `Exception`. Lỗi có thể xảy ra khi gọi `load` (ví dụ named caller thiếu `uses`) hoặc muộn hơn khi `iterator`/`stream` thực sự khám phá provider. Những nguyên nhân thường gặp:

| Biểu hiện | Lý do có thể | Cách kiểm tra |
| --- | --- | --- |
| Không tìm thấy provider, danh sách `[]` | Config file/provider module không visible qua loader | Kiểm tra `META-INF/services` trong JAR, loader, graph |
| “Provider ... not found” | Tên provider trong config sai, thiếu JAR, class unavailable | Kiểm tra exact binary name + classpath/loader |
| “Provider ... not a subtype” | Provider implement một bản `S` khác defining loader | So sánh `S.class` identity từ host và plugin |
| Không khởi tạo được provider | Không có public no-arg constructor hợp lệ với classpath deployment hoặc constructor ném lỗi | Xem cause, visibility, constructor |
| Error khi named caller gọi `load` | Module thiếu `uses` hoặc service không accessible | Thêm `uses S`/`requires`/`exports` phù hợp |
| Provider discovery sai tenant/plugin | TCCL là loader của worker cũ | Dùng explicit loader hoặc wrapper `try/finally` |
| Provider được giữ lâu sau shutdown | Cache, host registry, TCCL, threads giữ strong reference | Close instance nếu cần, clear references, shutdown workers |
| Bị lặp provider kỳ lạ | Duplicated descriptors/classpath/module paths | Kiểm tra JAR entries, module provides, parent resources |
| `ConcurrentModificationException` khi duyệt | `reload()` xảy ra sau khi có iterator/stream | Dùng iterator mới, không truy cập ServiceLoader concurrent |

Mẫu handling ở boundary tin cậy:

~~~java
try {
    for (MyService provider : ServiceLoader.load(
            MyService.class, pluginLoader)) {
        register(provider);
    }
} catch (java.util.ServiceConfigurationError problem) {
    // Log đầy đủ provider metadata/cause và đưa plugin vào FAILED.
    throw problem;
}
~~~

Đây là snippet. Không bắt toàn bộ `Error`/`Throwable` rồi bỏ qua “provider hỏng” vô điều kiện; `ServiceConfigurationError` thường chỉ ra cấu hình deployment sai nghiêm trọng. API có thể thử tiếp sau một số lỗi, nhưng Java SE không bảo đảm recovery hoàn toàn. Phần vận hành cần quyết định policy fail-fast, quarantine hoặc degrade một cách rõ ràng.

### 8.1. Gỡ lỗi bằng chính loader đã chọn

Khi chỉ có classpath SPI:

~~~java
String resourceName =
        "META-INF/services/" + MyService.class.getName();

java.util.Enumeration<java.net.URL> urls =
        pluginLoader.getResources(resourceName);

while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());
}
~~~

Đây là snippet yêu cầu `MyService`/`pluginLoader` và method xử lý `IOException`. Nó giúp kiểm tra provider configuration visible qua loader, nhưng **không chứng minh provider class sẽ được load, constructor sẽ thành công hay module access hợp lệ**. Với named modules, module descriptors cung cấp providers nên chỉ tìm `META-INF/services` **không đầy đủ**.

Nếu định vị resource đúng nhưng provider vẫn không hoạt động, kiểm tra lớp do loader nào định nghĩa:

~~~java
System.out.println(MyService.class.getClassLoader());
System.out.println(provider.getClass().getClassLoader());
System.out.println(MyService.class.isInstance(provider));
~~~

Đây cũng là snippet (đã có biến `provider`), mục tiêu là phân biệt **visibility**, **type identity** và **instantiation failure**.

## 9. JPMS và `ModuleLayer`: khác với TCCL

Với module plugin được resolve trong layer riêng, API:

~~~java
ServiceLoader<MyService> fromLayer =
        ServiceLoader.load(pluginLayer, MyService.class);
~~~

tìm named-module providers trong **`pluginLayer` và các parent layers**, **không tìm unnamed-module providers** qua `META-INF/services`. Đây là lựa chọn thường phù hợp khi plugin architecture dùng JPMS ModuleLayer thay vì `URLClassLoader` với JARs trên classpath.

Ngược lại:

~~~java
ServiceLoader<MyService> fromLoader =
        ServiceLoader.load(MyService.class, someLoader);
~~~

có thể tìm **cả named và unnamed-module providers** theo ServiceLoader algorithm. Kể cả một classloader thuộc một layer, việc lookup named modules có thể liên quan **các module khác trong cùng layer**, không giới hạn module do chính loader đó define. Cần hiểu đây là **service discovery**, không chỉ `someLoader.loadClass("...")`.

### 9.1. Service provider triển khai bằng named module

Ví dụ module declarations:

~~~java
module demo.api {
    exports demo.spi;
}
~~~

~~~java
module demo.provider {
    requires demo.api;
    provides demo.spi.GreetingService
        with demo.provider.EnglishGreeter;
}
~~~

~~~java
module demo.consumer {
    requires demo.api;
    uses demo.spi.GreetingService;
}
~~~

Nếu compiler/launcher yêu cầu:

~~~bash
java --module-path mods --add-modules demo.provider \
     --module demo.consumer/demo.consumer.Main
~~~

`mods` phải chứa các modules đã biên dịch và `Main` cần có code chạy phù hợp; lệnh này là **mẫu launch**, không phải script độc lập tạo ba modules. `--add-modules` trong ví dụ giúp đưa provider module vào graph; còn việc ServiceLoader khám phá chính xác còn phụ thuộc layer/module graph và service declarations. Với classpath demo ở phần 4, **không được tự viết `module-info.java` vào provider JAR** mà vẫn kỳ vọng kết quả/packaging không đổi.

### 9.2. `uses` không thay thế `exports`

Consumer module phải đọc module của service type và khai báo dùng service; service provider module phải công bố providers. Đừng giải quyết `ServiceConfigurationError` bằng `--add-opens` khi vấn đề thật là thiếu `uses` hoặc chưa resolve module. `opens` chủ yếu liên quan deep reflection, không phải “bật” SPI provider discovery.

## 10. Vòng đời provider, cache và hot reload

Khi provider là một plugin có state/resources, ServiceLoader **không quản lý shutdown** cho provider. API discovery/instantiation không tự gọi `close()` khi host không còn dùng provider.

Với plugin quản lý rõ ràng:

~~~text
1. Create plugin ClassLoader / ModuleLayer
2. Discover providers bằng explicit loader hoặc layer
3. Validate shared interface identity và constructor/module access
4. Start service và publish vào registry
5. Quiesce: ngừng request mới
6. Drain/cancel async tasks; unregister callbacks/listeners
7. Close providers/resources thuộc plugin (nếu có)
8. Drop ServiceLoader/provider caches và strong references
9. Close URLClassLoader sau khi không còn concurrent loads
10. JVM có thể unload classes khi đủ điều kiện; không bảo đảm ngay
~~~

Nếu bạn dùng `ServiceLoader.load(S.class)` trong một worker thread sống lâu, việc để worker giữ TCCL plugin loader **có thể giữ plugin cũ reachable**, ngay cả sau khi `URLClassLoader.close()`. Vì vậy cần restore TCCL và bỏ cache/registries.

**Không nhầm:** `ServiceLoader.reload()` chỉ reset cache của **một ServiceLoader instance**, không đóng providers cũ, không đổi TCCL đã capture, không close JAR, không tạo loader mới và không ép GC unload classes.

Với `ServiceLoader.Provider<S>` (Java 9+), `Provider.get()` có thể tạo instance trong quá trình sử dụng; lifecycle cũng thuộc trách nhiệm application framework sau khi nhận provider.

## 11. Quy tắc chọn overload trong ứng dụng thực

| Bài toán | API nên cân nhắc | Lý do |
| --- | --- | --- |
| Framework/library không biết plugin loader, chọn context theo request | `ServiceLoader.load(S.class)` | Dùng TCCL để parent-side code tìm child-side provider |
| Host biết loader nào sở hữu plugin | `ServiceLoader.load(S.class, pluginLoader)` | Tường minh, không phụ thuộc executor/TCCL |
| Code cần default system loader, không dựa TCCL | `ServiceLoader.load(S.class, ClassLoader.getSystemClassLoader())` hoặc `load(S.class, null)` | Fallback rõ ràng theo API |
| Chỉ muốn providers từ platform | `ServiceLoader.loadInstalled(S.class)` | Sử dụng platform loader, thường không dùng plugin application providers |
| Plugin modules ở một ModuleLayer riêng | `ServiceLoader.load(layer, S.class)` | Tìm named modules ở layer và ancestors |
| Cần lấy provider đầu tiên nếu có | `ServiceLoader.load(...).findFirst()` | Trả `Optional`; vẫn có thể ném `ServiceConfigurationError` |
| Cần inspect provider types trước khi instantiate | `ServiceLoader.load(...).stream()` | `Provider.type()` và `Provider.get()` tách biệt |
| Cần refresh danh sách providers của loader đang dùng | `serviceLoader.reload()` | Reset cache, **không hot-reload bytecode** |

**Khuyến nghị ứng dụng plugin:** Khi control plane đã biết loader/layer sở hữu provider, dùng **explicit loader/layer**. Chỉ dùng TCCL để tích hợp thư viện/framework yêu cầu ambient context, và khi đổi TCCL phải restore trong `finally`.

## 12. Những ngộ nhận thường gặp

1. “`ServiceLoader.load(S.class)` luôn dùng loader của `S.class`.” — **Sai**; nó dùng TCCL.
2. “`load(S.class, pluginLoader)` chỉ tìm classes từ đúng URL của pluginLoader, không bao giờ qua parent.” — **Sai**; phải tính delegation, `getResources`, named modules/layers.
3. “Sau khi tạo ServiceLoader, đổi TCCL sẽ thay loader nó sử dụng.” — **Sai**; loader được chọn tại factory call.
4. “Đưa JAR vào thư mục `plugins` là ServiceLoader tự quét.” — **Sai** nếu không có loader/module resolution cấu hình tìm đúng artifact.
5. “Provider class ở classpath nhưng không cần `META-INF/services`.” — **Sai** cho provider deployment dạng classpath truyền thống; cần cấu hình chuẩn.
6. “Trong named module vẫn phải có `META-INF/services` như classpath.” — **Không bắt buộc**; dùng `provides ... with`.
7. “`ServiceLoader.loadInstalled` là cách load plugin JAR.” — **Thường sai** trên Java 9+ vì dùng platform loader.
8. “`load(S.class, null)` luôn sử dụng bootstrap.” — **Sai**; ưu tiên system loader.
9. “`ServiceLoader.load` đã instantiate tất cả providers trước khi trả về.” — **Sai**; discovery/instantiation lazy.
10. “`reload()` tạo `Class<?>` mới cho plugin.” — **Sai**; chỉ xóa provider cache.
11. “ServiceLoader tự thread-safe vì nằm trong java.util.” — **Sai**; Javadoc cảnh báo không an toàn với truy cập đa luồng.
12. “Provider cùng tên interface nghĩa là compatible qua hai loaders.” — **Sai**; phải cùng runtime type identity.
13. “Set TCCL trên submitter là đủ cho thread pool worker đã tồn tại.” — **Không có bảo đảm**.
14. “Provider sau khi nhận từ ServiceLoader tự được close khi loader close.” — **Sai**; application quản lý lifecycle provider.
15. “Classloader nhìn thấy provider thì module caller chắc có `uses`/readability phù hợp.” — **Sai**; JPMS kiểm tra thêm module declarations.

## 13. Bài tập tự kiểm tra

Giả sử application API `demo.spi.GreetingService` được host loader định nghĩa, `pluginLoader` nhìn thấy `EnglishGreeter` và SPI file, host loader không thấy provider:

1. `ServiceLoader.load(GreetingService.class, hostLoader)` trả gì khi duyệt? **Không có provider trong lab**, thường danh sách trống.
2. `ServiceLoader.load(GreetingService.class, pluginLoader)` trả gì? **Provider `EnglishGreeter`**.
3. Nếu TCCL hiện tại là `pluginLoader`, `ServiceLoader.load(GreetingService.class)` giống lựa chọn nào? **Explicit plugin loader**.
4. Nếu đổi TCCL về host sau khi tạo ServiceLoader nhưng trước khi `iterator` chạy, loader có đổi không? **Không**.
5. Nếu dùng `load(S.class, null)` khi TCCL đang plugin? **System/bootstrap fallback, không lấy plugin TCCL**.
6. Nếu provider JAR không có file `META-INF/services/demo.spi.GreetingService` và không có named-module declaration, ServiceLoader có quét mọi `*.class` không? **Không**.
7. Provider có class cùng tên `demo.spi.GreetingService` nhưng tự định nghĩa lại interface thì kết quả gì? **Không subtype của host service type**, có thể `ServiceConfigurationError`.
8. Khi nào provider constructor chạy? **Khi provider được instantiated lazily trong iteration/Provider.get**, không nhất thiết khi gọi `load`.
9. `reload()` có bỏ provider objects đã được host lưu nơi khác không? **Không**.
10. Named caller quên `uses` thì xử lý ở đâu? **Sửa module descriptor/caller module, không phải đổi TCCL đơn thuần**.
11. Pool worker giữ TCCL plugin cũ là rủi ro gì? **Sai provider và có thể giữ classloader không unload**.
12. `ServiceLoader.load(layer,S.class)` có tìm provider trong unnamed module chỉ nhờ `META-INF/services` không? **Không**.

## 14. Tài liệu gốc nên tham khảo

1. [`ServiceLoader` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): overload `load`, TCCL, explicit loader, null behavior, named/unnamed modules, cache, `reload`, concurrency và errors.
2. [`ServiceLoader.Provider` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.Provider.html): `type()`, `get()` và lazy provider creation.
3. [`ClassLoader` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `loadClass`, `getResources`, runtime loader behavior.
4. [`Thread` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html): `getContextClassLoader`/`setContextClassLoader` và inheritance.
5. [JPMS `java.lang.Module` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Module.html): module identity/readability.
6. [`ModuleLayer` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ModuleLayer.html): xây và dùng module layers.
7. [JEP 261 — Module System](https://openjdk.org/jeps/261): ServiceLoader với named modules.
8. [Java SPI Tutorial — Oracle (historical Java 8)](https://docs.oracle.com/javase/tutorial/ext/basics/spi.html): khái niệm service interface/provider/ServiceLoader; với Java 9+ ưu tiên đối chiếu Javadoc hiện tại về JPMS.

**Kết luận:** `ServiceLoader.load(S.class)` chọn **TCCL tại lúc tạo ServiceLoader**; `ServiceLoader.load(S.class, chosenLoader)` chọn **loader bạn nêu rõ**. Provider discovery diễn ra lazily và còn phụ thuộc `META-INF/services` hoặc JPMS `provides/uses`, class identity và module graph. Trong host/plugin systems, explicit loader thường dễ kiểm soát hơn; nếu buộc dùng TCCL, phải truyền đúng context tại execution boundary và **luôn khôi phục trong `finally`**.
