# Vòng đời phần mở rộng Java: khám phá, nạp mã, khởi tạo, gọi và dừng

## 1. Bức tranh tổng thể

Một ứng dụng Java có khả năng mở rộng lúc chạy (*runtime extensibility*) cho phép bổ sung hành vi bằng các thành phần được triển khai riêng (*plugin*, *extension* hoặc *service provider*). Ví dụ, một công cụ xử lý tài liệu có thể tìm JAR chứa bộ chuyển đổi định dạng, kiểm tra tính tương thích, nạp bộ chuyển đổi, gọi xử lý và dừng khi không dùng nữa.

Phân biệt ba trách nhiệm:

- **Hợp đồng (API/contract):** các interface và kiểu dữ liệu mà host và plugin cùng hiểu, chẳng hạn `Extension`, `HostContext`, yêu cầu/kết quả và quy tắc xử lý lỗi.
- **Artifact:** JAR hoặc Java module chứa code, tài nguyên và cách khai báo provider.
- **Host/manager:** khám phá, lựa chọn, kiểm tra, nạp, tạo instance, khởi động, điều phối lời gọi, theo dõi, dừng và giải phóng tài nguyên.

**Phát hiện một JAR không có nghĩa code trong JAR đã được nạp. Nạp class không đồng nghĩa tạo instance; tạo instance không đồng nghĩa plugin đã sẵn sàng phục vụ. Gọi `stop()` không đồng nghĩa JVM đã unload class.** Đó là lý do phải mô hình hóa vòng đời riêng.

### Luồng trạng thái mẫu

```text
Artifact + metadata
   │
   ▼
DISCOVERED ──kiểm tra nguồn, version, dependencies──► VALIDATED
                                                      │
                                                      ▼
                                              LOADED (classes)
                                                      │
                                                      ▼
                                             CREATED (instance)
                                                      │
                                                      ▼
                                           INITIALIZING / start()
                                               │            │
                                          lỗi/rollback     thành công
                                               ▼            ▼
                                             FAILED       ACTIVE
                                                            │
                                                    execute()/invoke
                                                            │
                                                            ▼
                                              QUIESCING (ngừng nhận việc)
                                                            │
                                                            ▼
                                               STOPPED / close()
                                                            │
                                                bỏ mọi tham chiếu
                                                            ▼
                                             MAY BE UNLOADED (GC)
```

Đây là state machine do **ứng dụng thiết kế**, không phải tên trạng thái JVM cung cấp sẵn. Trạng thái `STOPPED` chỉ mô tả vòng đời logic. Class unloading là khả năng phụ thuộc vào tính khả dụng để thu gom rác của class loader và các class liên quan.

| Mốc | Host làm gì? | Điều kiện chuyển tiếp |
| --- | --- | --- |
| Discovery | Tìm artifact, manifest hoặc provider declaration | Có ứng viên để đánh giá |
| Validation | Kiểm tra nguồn, phiên bản API/JDK, phụ thuộc, định danh, chính sách | Chỉ nhận artifact đủ điều kiện |
| Loading | Chọn `ClassLoader`/`ModuleLayer`, nạp và liên kết class cần dùng | Không có lỗi thiếu lớp hoặc bất tương thích |
| Creation | Tạo instance qua SPI/factory | Provider đúng contract |
| Initialization | Truyền context, cấp tài nguyên, chạy readiness check | `start` hoàn tất |
| Invocation | Dispatch request theo ID/capability, quản lý lỗi và đồng thời | Plugin vẫn `ACTIVE` |
| Quiesce/stop | Chặn request mới, đợi request cũ, dọn tài nguyên | Plugin đã ngừng việc |
| Cleanup | Gỡ registry/callback, đóng loader nếu sở hữu | Không giữ tham chiếu khiến leak |

## 2. Thiết kế hợp đồng ổn định trước khi dùng runtime loading

Hợp đồng tối thiểu có thể là:

```java
public interface Extension {
    String id();
    void start(HostContext context);
    String execute(String request);
    void stop();
}
```

Đây là minh họa chưa độc lập; chương trình Java 17+ chạy được nằm ở mục 4. Khi xây contract thật cần quyết định:

1. **Danh tính và khả năng.** `id` phải duy nhất trong phạm vi host; nên có version, nhóm tác vụ/capabilities và chính sách khi hai plugin trùng ID. Đừng dựa vào thứ tự `ServiceLoader` để chọn plugin ưu tiên.
2. **Trạng thái và idempotence.** Chỉ gọi `execute` sau khi `start` thành công, không gọi mới sau khi bắt đầu dừng; `stop` nên an toàn nếu gọi lại.
3. **Sở hữu tài nguyên.** Plugin chịu trách nhiệm đóng thread, executor, socket, stream, watcher và listener do nó tạo. Host chịu trách nhiệm registry, điều phối và loader do chính host tạo.
4. **Context có giới hạn.** Truyền interface nhỏ cho các dịch vụ được phép dùng (logger, cấu hình, dữ liệu cần thiết); đừng truyền toàn bộ đối tượng nội bộ host.
5. **Tương thích binary/API.** Một bản cập nhật interface, method signature hay dependency có thể gây `LinkageError` hoặc `AbstractMethodError` dù tên class không đổi; định version và kiểm thử tương thích.
6. **Lỗi và rollback.** Định nghĩa lỗi nào khiến provider bị vô hiệu, điều kiện retry, giới hạn thời gian khởi động/dừng và cách thu hồi tài nguyên khi `start` mới hoàn tất một phần.

Host và plugin phải chia sẻ **cùng một định nghĩa** `Extension` và DTO dùng chung. Trong Java, danh tính kiểu phụ thuộc vào **fully qualified class name + defining class loader**. Hai class có cùng tên nhưng do hai loader khác nhau định nghĩa có thể không ép kiểu qua lại. API dùng chung thường được đặt trong artifact ổn định, do class loader của host hoặc parent sở hữu; không vô tình đóng thêm bản sao API vào từng JAR plugin.

## 3. Các giai đoạn và cơ chế thực tế

### 3.1. Khám phá (*discovery*) — nhận diện ứng viên

Các cách khám phá phổ biến:

- **Registry/cấu hình:** host đọc danh sách ID, đường dẫn artifact, version và quyền bật/tắt.
- **Thư mục JAR:** host liệt kê file trong thư mục được phép. Việc liệt kê và đọc manifest không cần chạy mã trong JAR.
- **Java SPI trên classpath/unnamed module:** đặt tệp `META-INF/services/<fully-qualified-service-type>` trong JAR, mỗi dòng là tên lớp provider.
- **JPMS named modules:** module cung cấp dùng `provides service.Type with impl.Provider;`; module tiêu thụ dùng `uses service.Type;`. `ServiceLoader.load(layer, ServiceType.class)` có thể tìm provider từ layer và các layer cha.

Ví dụ file `META-INF/services/app.api.Extension`:

```text
sample.HelloExtension
```

Đừng quét mọi class rồi dùng reflection chỉ để xác định provider nếu đã có descriptor hoặc module declaration. `ServiceLoader` có tính **lazy**: tạo loader không đồng nghĩa đã tạo tất cả provider; việc duyệt `iterator()` hoặc `stream()` có thể khởi phát tìm và nạp provider. `ServiceLoader.stream()` và `Provider.type()` giúp xem loại provider trước khi gọi `get()` trong những trường hợp phù hợp, nhưng đây không phải cách xác thực an toàn mã bên thứ ba.

Lỗi `ServiceConfigurationError` có thể xuất hiện khi duyệt do descriptor sai, provider thiếu/không hợp lệ, constructor lỗi hoặc provider không tạo được. Thứ tự mà provider được phát hiện không nên được coi là luật ưu tiên nghiệp vụ. `ServiceLoader.reload()` **chỉ xóa cache provider của đối tượng loader**, không tự dừng instance cũ và không định nghĩa lại class đã nạp.

### 3.2. Nạp mã (*class loading*) — đúng ranh giới class loader

| Cách | Phù hợp với | Điểm cần lưu ý |
| --- | --- | --- |
| Provider trên classpath khi khởi động | Plugin cố định, được đóng gói cùng ứng dụng | Chung không gian classpath, khó thay JAR đã nạp |
| `URLClassLoader` riêng | Nạp plugin JAR khi chương trình đang chạy | Quản lý parent delegation, phụ thuộc, cleanup và leak |
| `ModuleLayer` | Plugin theo JPMS với cấu hình module tường minh | Readability/export, dependency resolution và lớp module phức tạp hơn |

`ClassLoader.loadClass(...)` tìm và nạp class theo cơ chế loader; **nó không tự gọi constructor hay method `start` do ứng dụng định nghĩa**. JVM còn thực hiện liên kết (*verification, preparation, resolution*) và khởi tạo class khi điều kiện khởi tạo xảy ra. Static initializer hoặc constructor có thể lỗi **trước** khi host bước vào `start`; vì vậy tránh đặt logic khởi động khó rollback trong static initializer.

Với `URLClassLoader`, thông thường parent loader của host cung cấp contract `app.api.Extension`, còn child loader cung cấp `sample.HelloExtension` và các thư viện riêng. Quy tắc parent delegation không phải cách bảo mật plugin. Đặc biệt, một plugin chạy **trong cùng JVM** có thể sử dụng quyền của tiến trình; tách class loader chỉ chủ yếu giải quyết khả năng tìm class, cô lập dependency và quản lý vòng đời tương đối.

### 3.3. Tạo instance và khởi động (*instantiate/start*)

Provider có thể được tạo qua `ServiceLoader`, factory hoặc DI container. Khi dùng SPI classpath, lớp provider thông thường phải thỏa điều kiện của cơ chế ServiceLoader để khởi tạo (chẳng hạn constructor không tham số phù hợp). `start(context)` là **quy ước nghiệp vụ tự thiết kế**; Java hay `ServiceLoader` không tự gọi nó.

Trong `start`, plugin có thể xác thực cấu hình, mở kết nối, nạp tài nguyên, đăng ký listener và tự kiểm tra sẵn sàng. Host chỉ thêm instance vào registry phục vụ request khi `start` thành công. Nếu giữa chừng thất bại, plugin phải dọn các tài nguyên đã mở; host ghi `FAILED`, không dispatch và có thể vô hiệu hóa ứng viên mà vẫn giữ ứng dụng chính hoạt động.

Nếu có dependency giữa nhiều plugin, cần xác định thứ tự khởi động, phát hiện vòng phụ thuộc và dừng **theo thứ tự ngược** để plugin phụ thuộc được dừng trước plugin cung cấp dịch vụ.

### 3.4. Gọi nghiệp vụ (*invoke*)

Host chọn provider qua registry dựa trên `id`, capability hoặc chính sách. Trước khi gọi phải kiểm tra trạng thái `ACTIVE` và hợp đồng đầu vào. Với production, cần định rõ:

- **Concurrency:** một instance có thread-safe không? Host đồng bộ, tạo instance theo request hay cho phép nhiều thread gọi đồng thời? Đối tượng `ServiceLoader` không được thiết kế để dùng đồng thời tùy tiện trên nhiều luồng.
- **Timeout:** host đặt deadline, giới hạn số yêu cầu đồng thời và backpressure. `Future.cancel(true)` chủ yếu yêu cầu interrupt; không bảo đảm kết thúc mã plugin không hợp tác.
- **Failure isolation:** phân biệt lỗi nghiệp vụ có thể trả về với lỗi cấu hình/nạp class hoặc lỗi nghiêm trọng; ghi log plugin ID, version, stage, correlation ID; chỉ retry operation có tính an toàn phù hợp.
- **TCCL:** một số thư viện dùng `Thread.currentThread().getContextClassLoader()` để tìm resource/service. Nếu host tạm đổi TCCL khi gọi plugin, phải khôi phục loader ban đầu trong `finally`.
- **Observability:** đo thời gian `start`, thời gian gọi, request đang xử lý, lỗi, timeout, trạng thái và thời gian `stop` theo từng plugin.

### 3.5. Ngừng nhận việc, dừng và giải phóng (*quiesce/stop/close*)

Thứ tự nên thực hiện:

1. Chuyển sang `QUIESCING`, gỡ khỏi bộ định tuyến để chặn request mới.
2. Chờ các request đang chạy xong trong một deadline; giải quyết việc hủy/chuyển giao khi vượt hạn.
3. Gọi `stop()` hoặc `close()`, hủy đăng ký listener/callback và đóng tất cả executor, thread, socket, stream, watcher hay native resource do plugin sở hữu.
4. Xóa tham chiếu từ registry, cache, callback, `ThreadLocal`, thread context class loader, instance và các đối tượng reflection tới class của plugin.
5. Đóng `URLClassLoader` nếu host là chủ sở hữu, ghi nhận trạng thái và mọi lỗi cleanup; không để một lỗi dọn dẹp che khuất các công việc dọn dẹp độc lập khác.

`URLClassLoader.close()` giải phóng các file/JAR mà loader đã mở và khiến loader đó không còn nạp class/resource mới của chính nó; **class và object đã nạp vẫn có thể dùng được**. Việc đóng loader không tự dừng plugin, và **không bảo đảm unload class**. Class unloading chỉ có thể diễn ra sau khi không còn tham chiếu giữ class loader/các class của nó và GC quyết định thu gom. Nguồn leak thường là thread vẫn sống, `ThreadLocal`, TCCL, static cache, listener, scheduler hoặc lambda/callback mà host còn giữ.

**Hot reload** thường yêu cầu loader mới và instance mới: kiểm tra artifact → nạp/`start` mới → readiness → chuyển traffic sang mới → chờ request cũ → `stop` cũ → gỡ tham chiếu/đóng loader cũ. `ServiceLoader.reload()` không thay thế luồng này. Nếu cần chuyển state giữa hai version, nên dùng định dạng trung lập (JSON/record API ổn định) thay cho object triển khai thuộc loader cũ.

## 4. Ví dụ chạy được Java 17+: plugin JAR qua SPI

Ví dụ tách **host/API** khỏi **JAR provider**. Host nạp JAR động bằng `URLClassLoader`, tìm provider bằng `ServiceLoader`, gọi `start → execute → stop` và đóng loader. Dùng JDK 17+; không cần Maven hoặc Gradle.

Cấu trúc:

```text
demo/
├─ src/
│  ├─ app/api/HostContext.java
│  ├─ app/api/Extension.java
│  ├─ app/host/Main.java
│  └─ sample/HelloExtension.java
└─ providers/
   └─ META-INF/services/app.api.Extension
```

**`src/app/api/HostContext.java`**:

```java
package app.api;

public interface HostContext {
    void log(String message);
}
```

**`src/app/api/Extension.java`**:

```java
package app.api;

public interface Extension {
    String id();
    void start(HostContext context);
    String execute(String request);
    void stop();
}
```

**`src/sample/HelloExtension.java`**:

```java
package sample;

import app.api.Extension;
import app.api.HostContext;

public final class HelloExtension implements Extension {
    private HostContext context;
    private boolean active;

    @Override
    public String id() {
        return "hello";
    }

    @Override
    public void start(HostContext context) {
        if (active) {
            throw new IllegalStateException("Already started");
        }
        this.context = context;
        active = true;
        context.log("started " + id());
    }

    @Override
    public String execute(String request) {
        if (!active) {
            throw new IllegalStateException("Plugin is not active");
        }
        return "Xin chào, " + request + "!";
    }

    @Override
    public void stop() {
        if (!active) {
            return; // Gọi lặp an toàn
        }
        active = false;
        context.log("stopped " + id());
        context = null;
    }
}
```

**`providers/META-INF/services/app.api.Extension`** (đúng một dòng provider):

```text
sample.HelloExtension
```

**`src/app/host/Main.java`**:

```java
package app.host;

import app.api.Extension;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Usage: java -cp build/host app.host.Main <plugin.jar>");
        }

        URL jarUrl = Path.of(args[0]).toAbsolutePath().toUri().toURL();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] { jarUrl }, Extension.class.getClassLoader())) {

            ServiceLoader<Extension> providers =
                ServiceLoader.load(Extension.class, pluginLoader);
            List<Extension> running = new ArrayList<>();

            try {
                for (Extension extension : providers) {
                    if (!"hello".equals(extension.id())) {
                        continue;
                    }

                    extension.start(message ->
                        System.out.println("[host] " + message));
                    running.add(extension);
                    System.out.println(extension.execute("Java"));
                }

                if (running.isEmpty()) {
                    throw new IllegalStateException("No hello provider found");
                }
            } finally {
                // Dừng ngược thứ tự start kể cả khi execute ném lỗi.
                for (int i = running.size() - 1; i >= 0; i--) {
                    try {
                        running.get(i).stop();
                    } catch (RuntimeException ex) {
                        System.err.println("Stop failed: " + ex);
                    }
                }
            }
        } // URLClassLoader.close() sau stop.
    }
}
```

Từ thư mục `demo`, mở **PowerShell trên Windows**. Cần có `java`, `javac`, `jar` của JDK 17+ trong `PATH`:

```powershell
New-Item -ItemType Directory -Force build/host, build/plugin | Out-Null
javac -encoding UTF-8 -d build/host src/app/api/HostContext.java src/app/api/Extension.java src/app/host/Main.java
javac -encoding UTF-8 -cp build/host -d build/plugin src/sample/HelloExtension.java
New-Item -ItemType Directory -Force build/plugin/META-INF/services | Out-Null
Copy-Item providers/META-INF/services/app.api.Extension build/plugin/META-INF/services/app.api.Extension
jar --create --file build/hello-plugin.jar -C build/plugin .
java -cp build/host app.host.Main build/hello-plugin.jar
```

**Stdout dự kiến, chính xác:**

```text
[host] started hello
Xin chào, Java!
[host] stopped hello
```

Tại sao chạy được?

1. `build/host` có contract và host; `hello-plugin.jar` có `sample.HelloExtension` và descriptor `META-INF/services/...`, **không có bản sao** `app.api.Extension`.
2. Parent của `pluginLoader` chính là loader đã nạp API host. Vì vậy `HelloExtension` thật sự implement đúng `Extension` mà host biết.
3. `ServiceLoader.load(Extension.class, pluginLoader)` thiết lập cách tìm provider; vòng `for` thực hiện duyệt và tạo instance. `start` là lời gọi **tường minh của host**, không phải hành vi tự động của SPI.
4. Sau `execute`, khối `finally` dừng mọi plugin đã được khởi động và khối `try-with-resources` đóng loader. Output không chứa thông báo của việc đóng loader vì `close()` không in ra stdout.

Trên Linux/macOS thay `New-Item`/`Copy-Item` bằng `mkdir -p`/`cp`; các lệnh Java giữ nguyên. Mẫu này cố ý nhỏ: host production còn phải kiểm tra nguồn JAR, timeout, thread safety, readiness, rollback nếu `start` tạo tài nguyên rồi lỗi và quy tắc hot swap.

## 5. Lỗi theo giai đoạn: chẩn đoán nguyên nhân đúng chỗ

| Mốc | Triệu chứng | Kiểm tra |
| --- | --- | --- |
| Discovery | Không tìm thấy provider | File `META-INF/services/...` đúng tên API? descriptor nằm trong JAR? đúng `provides/uses` với module? |
| Loading/linking | `ClassNotFoundException`, `NoClassDefFoundError`, `UnsupportedClassVersionError`, `LinkageError` | Thiếu thư viện, classpath/loader sai, bytecode cho JDK mới hơn, trùng lớp/API hoặc dependency |
| Tạo instance | `ServiceConfigurationError`, lỗi constructor/static initialization | Provider triển khai đúng contract, có cách tạo instance hợp lệ, tránh tác dụng phụ trong static initializer |
| `start` | Mở được một phần tài nguyên rồi ném lỗi | Rollback từng tài nguyên, không đưa plugin vào registry, ghi stage và nguyên nhân |
| Gọi | Exception, kết quả sai, race hoặc treo | Input/output contract, thread safety, deadline, giới hạn đồng thời, log và retry policy |
| `stop`/cleanup | Thread/file còn sống, loader không được GC | Chặn gọi mới, đợi inflight, đóng hết executor/stream/callback, gỡ cache/TCCL/reference |

Các ngộ nhận cần tránh:

- **“Tìm JAR tức là đã chạy provider.”** Discovery có thể chỉ là đọc metadata, còn load/initialize/invoke là các bước riêng.
- **“`ServiceLoader` sẽ gọi `start()` và `stop()`.”** Không: host/framework tự định nghĩa và gọi lifecycle API.
- **“`reload()` sẽ thay code hiện tại.”** Không: nó xóa cache tìm provider; class definition/instance cũ không tự đổi.
- **“Đóng class loader sẽ kill thread và unload class.”** Không: thread/object vẫn có thể tồn tại; unload không bảo đảm.
- **“Cùng tên class tức cùng kiểu.”** Không nếu defining class loader khác nhau.
- **“Loader riêng là sandbox cho mã không tin cậy.”** Không: để chạy mã không tin cậy cần ranh giới tiến trình, quyền OS bị giới hạn và giới hạn tài nguyên.

## 6. Vận hành và nâng cấp an toàn

Để phát triển từ ví dụ thành plugin manager tin cậy, thường phải bổ sung:

- **Manifest/version compatibility:** plugin ID, version, API version, JDK tối thiểu, dependencies, checksum/chữ ký, nguồn cung cấp, capabilities; từ chối sớm trường hợp sai.
- **State machine có đồng bộ:** chuyển trạng thái nguyên tử, registry chỉ xuất hiện sau readiness, chặn lời gọi mới khi `QUIESCING`.
- **Dependency lifecycle:** thứ tự start theo dependency, thứ tự stop ngược; phát hiện chu trình và lỗi khởi động chuỗi.
- **Resource ownership:** host quản lý loader; plugin quản lý tài nguyên riêng; dọn đủ khi chạy thành công, lỗi giữa chừng hay hot reload.
- **Fault management:** timeout, quota, health check, circuit breaker/quarantine, xử lý request còn chạy và policy retry.
- **Security:** chỉ chấp nhận artifact từ nguồn đã kiểm tra. Class loader không giới hạn quyền của plugin trong JVM; mã không tin cậy cần tách process.
- **Observability và leak check:** đo init/stop latency, in-flight, error rate, số loader cũ còn sống sau nhiều lượt nâng cấp; tìm thread/TCCL/`ThreadLocal` giữ class loader.

Quy trình hot upgrade thường là **kiểm tra artifact mới → tạo loader/instance mới → start và readiness → chuyển traffic → đợi request cũ → stop cũ → gỡ tham chiếu, đóng loader cũ**. Nếu phiên bản mới không sẵn sàng, giữ phiên bản cũ phục vụ và dọn phiên bản mới đã khởi động một phần. Không trao trực tiếp object đặc thù class loader cũ sang phiên bản mới; nên trao state qua dữ liệu/contract ổn định.

### Checklist tự đánh giá

- [ ] API chung được định version và chỉ có một định nghĩa được host/plugin cùng dùng.
- [ ] Phân biệt rõ discovery, loading, class initialization, provider creation, business start, invocation và stop.
- [ ] Kiểm tra nguồn JAR, metadata, dependency và compatibility trước khi kích hoạt.
- [ ] Host chỉ dispatch đến plugin `ACTIVE`; định rõ concurrency, timeout, error policy.
- [ ] Plugin khởi động thất bại biết rollback; shutdown chặn request mới trước khi cleanup.
- [ ] Không còn callback/thread/cache/TCCL giữ loader cũ khi thay phiên bản.
- [ ] Kiểm thử thực tế: nạp, xử lý, thất bại lúc start/gọi, dừng, nạp phiên bản mới và theo dõi leak.

**Tài liệu API chính thức (Java 17):** [`ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html), [`URLClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html), [`ModuleLayer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html).
