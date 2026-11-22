# Tạo thế hệ loader hoặc layer mới cho phiên bản plugin mới

## 1. Vì sao phải tạo “thế hệ” mới?

Một hệ Java mở rộng tại runtime có thể đang phục vụ request bằng plugin `report:v1` trong lúc có bản phát hành `report:v2`. Mục tiêu là nạp và kiểm thử v2 mà không làm đứt các request v1, sau đó chuyển request mới sang v2, cho v1 hoàn thành công việc rồi giải phóng tài nguyên.

**Không thể chỉ copy đè JAR rồi gọi lại `Class.forName`.** JVM định danh runtime class bằng **binary name và defining ClassLoader**. Nếu loader L1 đã định nghĩa `com.example.report.ReportPlugin` từ v1, class đó không biến thành bytecode v2 khi file JAR trên đĩa đổi. Cơ chế triển khai thông thường là tạo **defining loader mới L2**, hoặc tạo **ModuleLayer mới với các loader mới**, để cùng binary name có thể tồn tại song song dưới hai runtime identities.

~~~text
Host API / parent loader H
       |
       +-- Generation g101 → Loader L1 → Plugin v1 → request cũ R1
       |
       +-- Generation g102 → Loader L2 → Plugin v2 → request mới R2

Tên implementation có thể giống nhau;
(typeName, definingLoader L1) != (typeName, definingLoader L2).
Host API được H định nghĩa, nên cả v1 và v2 cùng implement hợp đồng H.
~~~

**Thế hệ (generation)** không chỉ là số version. Một generation phải mô tả một tập nhất quán: plugin artifact, dependency versions, classloader hoặc module layer, class/provider instances, cấu hình, state, các resource và lifecycle. Hai lần deploy lại **cùng** `2.0.0` có thể có generation ID khác nhau.

### Bốn thao tác dễ nhầm

| Thao tác | Tạo runtime class identity mới? | Thay thế request routing? | Dừng plugin cũ? |
| --- | --- | --- | --- |
| Thay JAR trên đĩa | Không đối với class đã define | Không | Không |
| `ServiceLoader.reload()` trên service loader cũ | Không: chỉ xóa provider cache | Không | Không |
| `new URLClassLoader(...)` rồi nạp bản mới | Có nếu class được loader mới định nghĩa | Không, phải tự publish | Không |
| `ModuleLayer.defineModulesWithOneLoader(...)` / `ManyLoaders(...)` trên cấu hình mới | Có với modules/classes được define bởi loaders mới | Không, phải tự publish | Không |

Muốn **hot replacement an toàn**, cần cả class identity, API boundary, candidate validation, atomic publication, request draining, rollback và cleanup.

## 2. Những điều kiện đầu vào phải chốt trước khi nâng cấp

Trước khi nạp v2, host nên biết rõ:

- **Plugin ID và artifact:** tên, version, digest/signature, đường dẫn JAR/module path **bất biến**. Không thay bytes ngay trong JAR mà loader cũ đang đọc.
- **Host contract:** `Plugin` API, các DTO, exception và event types phải được định nghĩa ở parent loader hoặc API module chung; không trộn các bản sao contract trong plugin-private loaders.
- **Dependency graph:** những library nào dùng chung, những library nào thuộc riêng từng generation. Tránh để parent có thư viện v1 nếu v2 cần một bản khác mà parent-first sẽ chọn v1.
- **Config/state:** v2 cần config schema mới không, dữ liệu cũ có backward compatibility không, ai thực hiện migration?
- **Health/capability:** phải kiểm tra điều kiện nào trước khi publish? Ví dụ API version, provider ID, dependency presence, constructor, database migration dry-run, warmup.
- **Lifecycle:** generation là stateless hay giữ connection, thread pool, timer, listener, thread-local, cache và native resources?
- **Traffic:** có thể chờ các request v1 kết thúc không; nếu timeout thì cancel, giữ v1 tạm thời hay rollback?
- **Trust:** plugin có được tin cậy không; classloader/module layer **không** phải sandbox để thực thi mã ác ý.

Một record generation gợi ý:

~~~text
Generation
  pluginId: report
  pluginVersion: 2.0.0
  generationId: report-2.0.0-iteration-4
  artifactDigest: SHA-256 của JAR thực
  dependencyManifest: danh sách version/digest đã khóa
  loaderOrLayer: đối tượng định nghĩa class cho generation
  providerInstances: các service được chọn
  state: CREATED / READY / ACTIVE / RETIRING / STOPPED
  inFlight: số request đang giữ lease
  resources: executors, connections, listeners thuộc generation
~~~

**Tách plugin version khỏi generation ID:** cùng version có thể nạp lại nhiều lần sau rollback hoặc đổi cấu hình. Khi log và troubleshoot, cần cả artifact digest, generation, loader/layer identity.

## 3. Căn bản: class identity, parent-first và shared API

`ClassLoader` mặc định ủy quyền lên parent trước khi tự định nghĩa class. `URLClassLoader` dùng mô hình này đối với classpath loading thông thường.

~~~text
HostApiLoader H:   com.example.spi.Plugin, Request, Result
    |
    +-- PluginLoader L1:
    |     report-v1.jar, json-lib-v1.jar
    |
    +-- PluginLoader L2:
          report-v2.jar, json-lib-v2.jar
~~~

Khi cả hai plugin code implement đúng interface do H định nghĩa, host có thể gọi v1/v2 qua `Plugin`. Ngược lại, nếu plugin đóng gói và tự định nghĩa bản sao `com.example.spi.Plugin` bằng child-first không kiểm soát, object có thể không cast được sang `Plugin` ở host dù `getName()` giống hệt. **Type identity là tên class + defining loader, không chỉ tên class.**

Không nên đặt `report-v1.jar` hoặc dependency private v1 trong host parent classpath. Nếu parent đã định nghĩa cùng tên class, L2 sẽ nhìn thấy class cũ qua delegation, vô hiệu hóa mục đích cô lập. Dùng các plugin-private JAR theo generation; chỉ giữ API/DTO đủ ổn định ở parent.

### 3.1. Không truyền đối tượng private trực tiếp giữa hai version

Dù v1 và v2 cùng có class `com.vendor.JsonNode`, nếu hai loaders định nghĩa chúng độc lập, runtime types khác nhau. Một object `JsonNode` v1 không tự cast được sang v2. Khi chuyển state hoặc dữ liệu, dùng stable DTO do host sở hữu, serialized payload có schema, hoặc gateway API tường minh. Không xem Java serialization của object private giữa hai generation là migration an toàn mặc định.

### 3.2. Những gì bị tách và không bị tách

Hai loaders có thể có class metadata/static fields/cache riêng cho class tự định nghĩa; v1 và v2 có thể cùng sống trong JVM. Nhưng heap, CPU, native process resources, security permissions và JVM crash vẫn chung. Muốn giới hạn lỗi/tài nguyên ở cấp process, dùng plugin worker process/container riêng.

## 4. Quy trình tạo generation mới với URLClassLoader

Dành cho plugin JAR trên class path hoặc JAR không dùng named module layer:

1. **Stage artifact:** ghi v2 ra path riêng `plugins/report-v2.jar`, xác thực checksum/signature và khóa dependency files. Tránh ghi đè artifact đang được loader v1 sử dụng.
2. **Create loader:** `new URLClassLoader(urlsOfV2, hostApiLoader)`. URL list phải chứa v2 và các dependency private đúng version.
3. **Discover entrypoint:** `Class.forName(entryBinaryName, true, loader)` hoặc `ServiceLoader.load(Plugin.class, loader)` nếu JAR khai báo SPI.
4. **Instantiate:** khởi tạo provider v2, chỉ cast qua shared API parent.
5. **Validate/warm up:** kiểm tra ABI/API version, config, health, functionality và các resources. Nếu fail, stop/close candidate rồi giữ active generation v1.
6. **Publish:** host thay active registry/snapshot sang v2 bằng cơ chế đồng bộ hóa chọn generation và cấp lease.
7. **Drain v1:** request cũ vẫn dùng v1 đến khi kết thúc hoặc theo timeout/cancellation policy.
8. **Release v1:** stop provider, unregister listeners, dừng executor/thread, restore TCCL, close URLClassLoader và bỏ mọi strong reference.

Ví dụ **đoạn minh họa, không độc lập**:

~~~java
URLClassLoader candidateLoader = new URLClassLoader(
        new URL[] {Path.of("plugins/report-v2.jar").toUri().toURL()},
        Plugin.class.getClassLoader());

Class<?> impl = Class.forName(
        "com.example.report.ReportPlugin", true, candidateLoader);
Plugin instance = (Plugin) impl.getConstructor().newInstance();

// Validate instance trước khi publish.
// Ở nhánh thất bại hoặc khi generation dừng: cleanup instance + loader.
~~~

Tạo loader không nhất thiết load tất cả class ngay; phần lớn hoạt động loading là **lazy**. Vì thế validation không chỉ kiểm tra constructor: phải gọi một số đường thực thi đại diện để phát hiện `NoClassDefFoundError`/`NoSuchMethodError` sớm thay vì đợi đến request đầu tiên.

### 4.1. close() không phải lệnh unload class

`URLClassLoader.close()` đóng các file/resource handles mà loader đã mở theo API. Những class đã được định nghĩa và còn reference vẫn tồn tại. `close()` không tự ngắt thread, gọi `Plugin.stop()` hoặc ép GC/class unloading. Nếu thread khác đang load class đồng thời khi `close()` diễn ra, kết quả load đó không được bảo đảm. **Chỉ close sau khi không còn công việc cần class/resource từ generation cũ.**

## 5. Lab Java 17+ chạy được: cùng binary name, hai generation độc lập

Lab này có hai JAR riêng nhưng **cùng class name `demo.impl.Greeter`**, một bản trả `v1` và bản kia `v2`. Host dùng một interface `demo.api.Plugin` duy nhất, tạo hai URLClassLoader và đổi active pointer.

**Phạm vi lab:** chạy tuần tự để minh họa class identity và publish; `AtomicReference.getAndSet` trong lab **không** là giải pháp đóng generation an toàn cho server có request concurrent (xem mục 7).

### 5.1. Cấu trúc thư mục

~~~text
hot-swap-demo/
├── src/
│   ├── api/demo/api/Plugin.java
│   ├── host/HotSwapDemo.java
│   ├── v1/demo/impl/Greeter.java
│   └── v2/demo/impl/Greeter.java
├── out/                   # sinh khi compile
└── jars/                  # sinh khi tạo JAR
~~~

Tệp `src/api/demo/api/Plugin.java`:

~~~java
package demo.api;

public interface Plugin extends AutoCloseable {
    String version();
    String greet(String name);

    @Override
    default void close() throws Exception {
        // Hook cho generation thực tế; demo không giữ resources.
    }
}
~~~

Tệp `src/v1/demo/impl/Greeter.java`:

~~~java
package demo.impl;

import demo.api.Plugin;

public final class Greeter implements Plugin {
    @Override
    public String version() {
        return "v1";
    }

    @Override
    public String greet(String name) {
        return "Xin chao " + name + " tu v1";
    }
}
~~~

Tệp `src/v2/demo/impl/Greeter.java` có **cùng binary name**:

~~~java
package demo.impl;

import demo.api.Plugin;

public final class Greeter implements Plugin {
    @Override
    public String version() {
        return "v2";
    }

    @Override
    public String greet(String name) {
        return "Xin chao " + name + " tu v2";
    }
}
~~~

Tệp `src/host/HotSwapDemo.java`:

~~~java
import demo.api.Plugin;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicReference;

public final class HotSwapDemo {
    record Generation(String id, URLClassLoader loader, Plugin plugin)
            implements AutoCloseable {
        @Override
        public void close() throws Exception {
            try {
                plugin.close();
            } finally {
                loader.close();
            }
        }
    }

    static Generation prepare(String id, Path jar) throws Exception {
        URLClassLoader loader = new URLClassLoader(
                new URL[] {jar.toUri().toURL()},
                Plugin.class.getClassLoader());
        try {
            Class<?> type = Class.forName(
                    "demo.impl.Greeter", true, loader);
            Plugin plugin = (Plugin) type.getConstructor().newInstance();

            if (!id.equals(plugin.version())) {
                throw new IllegalStateException("Wrong plugin version");
            }
            return new Generation(id, loader, plugin);
        } catch (Exception | LinkageError failure) {
            loader.close();
            throw failure;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Pass plugin-v1.jar plugin-v2.jar");
        }

        try (Generation g1 = prepare("v1", Path.of(args[0]))) {
            AtomicReference<Generation> active =
                    new AtomicReference<>(g1);
            System.out.println("active-before="
                    + active.get().plugin().greet("Lan"));

            try (Generation g2 = prepare("v2", Path.of(args[1]))) {
                // Kiểm tra candidate trước khi đổi active pointer.
                System.out.println("candidate="
                        + g2.plugin().greet("Lan"));

                Generation old = active.getAndSet(g2);
                System.out.println("active-after="
                        + active.get().plugin().greet("Lan"));
                System.out.println("old-reference="
                        + old.plugin().greet("Lan"));
                System.out.println("same-impl-class="
                        + (old.plugin().getClass()
                                == g2.plugin().getClass()));
                System.out.println("shared-contract="
                        + (old.plugin() instanceof Plugin
                                && g2.plugin() instanceof Plugin));

                // Lab không có request đồng thời; bỏ active pointer
                // trước khi g2 đóng ở cuối try.
                active.compareAndSet(g2, null);
            }
            // g1 được giữ tới hết outer try rồi mới đóng.
        }
    }
}
~~~

Giải thích những chi tiết then chốt:

- Host classpath `out\host` chứa API và `HotSwapDemo`, **không** chứa class `demo.impl.Greeter`. Vì vậy L1 và L2 có thể định nghĩa implementation riêng.
- `Plugin.class.getClassLoader()` là parent chung: cả v1 lẫn v2 dùng cùng runtime `Plugin` type, nên cast hợp lệ.
- `prepare` tạo loader, load class, instantiate và validate `version()` **trước** khi trả `Generation`. Nếu load/validation lỗi, cleanup loader candidate.
- `AtomicReference.getAndSet` làm active pointer đổi từ g1 sang g2. Vẫn có `old.plugin()` do object cũ chưa bị giải phóng, minh họa hai generation cùng tồn tại.
- `old.plugin().getClass() == g2.plugin().getClass()` là `false` dù cùng binary name: defining loaders khác nhau. Nhưng cả hai đều là `Plugin` của parent.
- Đóng g1/g2 chỉ diễn ra sau các lời gọi minh họa; lab không có thread background. Production phải dùng lease/drain.

### 5.2. Lệnh biên dịch và chạy

Chạy các lệnh trong **PowerShell** tại thư mục `hot-swap-demo` với **JDK 17+**:

~~~powershell
New-Item -ItemType Directory -Force out\host,out\v1,out\v2,jars | Out-Null

javac --release 17 -encoding UTF-8 -d out\host src\api\demo\api\Plugin.java src\host\HotSwapDemo.java
javac --release 17 -encoding UTF-8 -cp out\host -d out\v1 src\v1\demo\impl\Greeter.java
javac --release 17 -encoding UTF-8 -cp out\host -d out\v2 src\v2\demo\impl\Greeter.java

jar --create --file jars\plugin-v1.jar -C out\v1 .
jar --create --file jars\plugin-v2.jar -C out\v2 .

java -cp out\host HotSwapDemo jars\plugin-v1.jar jars\plugin-v2.jar
~~~

Kết quả stdout dự kiến:

~~~text
active-before=Xin chao Lan tu v1
candidate=Xin chao Lan tu v2
active-after=Xin chao Lan tu v2
old-reference=Xin chao Lan tu v1
same-impl-class=false
shared-contract=true
~~~

Những kết quả này phụ thuộc việc chỉ đưa `out\host` vào host classpath, hai JAR thực sự được tạo từ đúng source và parent không chứa implementation. Nếu cả hai implementation identity bị trùng, hãy kiểm tra classpath của process và parent delegation trước khi kết luận JVM đã “dùng chung” class giữa các plugin.

### 5.3. Vì sao không hot-replace bằng classloader cũ?

Nếu gọi `Class.forName("demo.impl.Greeter", true, g1.loader())` lần nữa sau khi đã load v1, loader cũ vẫn dùng class identity v1. Thay nội dung `plugin-v1.jar` trên đĩa trong lúc JVM đang chạy không phải cách update đáng tin: class đã load không đổi và resource lookup có thể bị ảnh hưởng. **Dùng artifact path mới, loader mới và một generation lifecycle mới.**

## 6. JPMS: tạo ModuleLayer mới cho phiên bản modular plugin

Plugin dùng **named modules** có metadata `module-info.java`, `requires`, `exports`, `opens`, `uses`, `provides`. Để đưa phiên bản mới vào JVM, host có thể tạo một `Configuration` mới từ `ModuleFinder` rồi define **ModuleLayer mới** với loader mapping tương ứng.

### 6.1. Dòng chảy JPMS

~~~text
plugin-v2 modular JAR(s), module path riêng
               |
        ModuleFinder.of(path)
               |
 stable parent layer (chứa host API module)
               |
 parent.configuration().resolve(finder, afterFinder, roots)
               |
        Configuration v2 (module graph)
               |
 parent.defineModulesWithOneLoader(cf, parentLoader)
                HOẶC
 parent.defineModulesWithManyLoaders(cf, parentLoader)
               |
         ModuleLayer v2 + loader(s)
               |
 provider discovery/instantiate/validate
               |
     registry publish + drain old layer
~~~

Hàm Java minh họa **không phải chương trình độc lập**; cần imports và module path thực:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

static ModuleLayer createPluginLayer(
        Path moduleDirectory, String rootModule) {

    ModuleLayer parent = ModuleLayer.boot();
    ModuleFinder finder = ModuleFinder.of(moduleDirectory);

    Configuration cf = parent.configuration().resolve(
            finder,
            ModuleFinder.of(),
            Set.of(rootModule));

    return parent.defineModulesWithOneLoader(
            cf, ClassLoader.getSystemClassLoader());
}
~~~

**Điều kiện:** host API module mà plugin `requires` phải có trong parent configuration hoặc được resolve đúng. Nếu host dùng parent layer tùy biến, thay `ModuleLayer.boot()` bằng parent ổn định thực tế. `ModuleFinder.of` chỉ thấy những module được chỉ trong path; nó không tự làm động tác deploy.

`defineModulesWithOneLoader` tạo một loader cho các modules trong configuration mới; `defineModulesWithManyLoaders` tạo một loader mỗi module. Cả hai giúp tạo mapping **mới**; phương thức `defineModules` với custom mapping thích hợp cho trường hợp advanced và đòi hỏi kiểm soát delegation/readability chặt chẽ.

### 6.2. Sibling layers thay vì coi v1 là parent của v2

Khi v1 và v2 dùng **cùng module name** `com.example.greeter`, nên đặt hai phiên bản ở **hai module paths riêng** rồi tạo **hai sibling layers** từ parent API ổn định:

~~~text
           Stable parent layer (API)
             /                \
       Layer g101          Layer g102
       greeter v1          greeter v2
       Loader(s) L1        Loader(s) L2
~~~

Nếu tạo v2 như child layer có **v1 layer là parent**, resolution có thể nhìn thấy module đã tồn tại trong parent và không đưa version v2 vào configuration như mong muốn. Parent phải đại diện phần dùng chung **không bao gồm version mà ta muốn thay**. Đừng nhét hai module cùng tên vào một configuration rồi kỳ vọng JPMS chọn version theo request: module resolution không phải Maven dependency resolver.

### 6.3. Provider trong modular plugin

Ví dụ module descriptor của provider:

~~~java
// module-info.java — ví dụ mô tả, chưa độc lập.
module com.example.greeter {
    requires com.example.api;
    provides com.example.api.Plugin
        with com.example.greeter.Greeter;
}
~~~

Nếu shared API là named module trong parent, host có thể khám phá providers qua candidate layer:

~~~java
// Đoạn minh họa, chưa độc lập; Plugin là host API,
// candidateLayer đã được define và validate.
ServiceLoader<Plugin> loader =
        ServiceLoader.load(candidateLayer, Plugin.class);
Plugin candidate = loader.findFirst().orElseThrow();
~~~

Một caller module sử dụng `ServiceLoader` cần khai báo `uses <service>` theo JPMS. `ServiceLoader.load(layer, service)` có thể quan sát providers ở layer và ancestor layers; **không dùng `findFirst()` làm chính sách bảo đảm chọn v2** nếu có nhiều providers. Hãy kiểm tra provider module, ID/version và ownership của candidate sau khi tìm.

Một `ModuleLayer` **không có phương thức `close()` chung**. Muốn generation JPMS cũ đủ điều kiện GC/unload, phải dừng provider, giải phóng thread/resources, bỏ references tới `ModuleLayer`, `Module`, loader và classes/instances. Không suy ra class unload tức thì chỉ vì đã bỏ layer khỏi active registry.

### 6.4. Khi nào chọn OneLoader vs ManyLoaders?

| Tiêu chí | `defineModulesWithOneLoader` | `defineModulesWithManyLoaders` |
| --- | --- | --- |
| Loader cho mỗi layer | Một loader mới cho tất cả module của configuration | Một loader mới cho mỗi module |
| Quản lý type/shared state | Các module chia sẻ loader nhưng vẫn có JPMS boundaries | Các module có runtime loader identities khác |
| Module package constraints | Có thể lỗi nếu overlapping packages/split delegation không hợp lệ | Phân tách loader hơn, nhưng vẫn phải thỏa module graph |
| Cấu hình/lifecycle | Đơn giản nếu nhiều module được release chung | Linh hoạt hơn theo module, nhưng thêm complexity |
| Plugin version isolation | Tạo **layer generation mới** | Tạo **layer generation mới** |

**Một layer không đồng nghĩa một plugin:** layer có thể gồm nhiều module plugin và dependency. Khi muốn chỉ thay một plugin trong nhóm, phải biết configuration/loader group nào cần được tạo lại. JPMS module readability không thay thế state migration hay request routing.

## 7. Chuyển traffic bằng lease để tránh đóng generation đang được dùng

### 7.1. AtomicReference chưa đủ khi có request đồng thời

Mẫu code tưởng đúng:

~~~java
// Minh họa race, KHÔNG dùng nguyên mẫu trong production.
Generation g = active.get();
g.plugin().handle(request);

// Thread triển khai chạy trong lúc request còn xử lý:
Generation old = active.getAndSet(candidate);
old.close(); // Có thể đóng resources ngay dưới request của thread khác!
~~~

Dù `getAndSet` đổi pointer nguyên tử, có khoảng thời gian giữa request đọc `g` và đăng ký sử dụng. Vì thế nếu deploy đóng old ngay, request có thể thấy connection/executor đã đóng.

### 7.2. Thiết kế cấp lease nhất quán với swap

Phải đồng bộ **việc chọn active generation và tăng bộ đếm active-use** với việc swap active pointer. Một thiết kế dễ suy luận là read/write gate:

~~~text
Request thread                        Deploy coordinator
-----------------------------         ------------------------------
acquire read gate
  g = active
  g.inFlight++ (đăng ký lease)
release read gate
run g.plugin()                        build/validate candidate v2
                                      acquire write gate
                                        old = active
                                        active = v2
                                        old.state = RETIRING
                                      release write gate
request hoàn tất
  g.inFlight--
                                      await old.inFlight == 0
                                      stop old background tasks/resources
                                      close old loader nếu thích hợp
                                      bỏ strong references tới old
~~~

Đây là **thuật toán, không phải chương trình Java độc lập**. Có thể dùng `ReentrantReadWriteLock` bảo vệ pointer và lease acquisition, còn invocation chạy **ngoài** read lock để deploy không bị chặn suốt thời gian request. Counter/state cần synchronization hoặc atomic state machine đủ chặt chẽ. Khi một generation đã đánh dấu `RETIRING`, không cấp **lease mới** cho nó.

Mỗi lease nên được close trong `finally` hoặc try-with-resources; nếu request ném exception/cancel cũng phải release. Không chỉ đếm request HTTP: plugin có thể giữ timer, queue consumer, scheduler, subscription, JMX registration hoặc callback dài hạn. Những resource ấy có lifecycle và ownership riêng.

### 7.3. State machine

~~~text
CREATED
   |
   v
VALIDATING ---> FAILED ----> RELEASED
   |
   v
READY --------> ABORTED ---> RELEASED
   |
   v
ACTIVE
   |
   v
RETIRING
   |
   +---- inFlight > 0 → WAIT/DRAIN (có timeout policy)
   |
   v
STOPPED
   |
   v
RELEASED
~~~

Các invariants:

- Chỉ `READY` candidate mới được publish.
- Swap cho request mới phải có một điểm tuyến tính hóa rõ ràng; không publish nửa v1/nửa v2 trong cùng registry snapshot.
- Old generation vẫn tồn tại cho work đã nhận trước swap.
- Đóng old chỉ sau khi bảo đảm không còn workload cần dùng nó; timeout phải có cách xử lý an toàn, không mặc định `close()` cưỡng bức.
- Nếu các plugin dùng chung dependency group resources, phải quản lý reference counts/lifecycle ở **cấp group**, không đóng parent dependency loader khi child khác còn dùng.

## 8. Rollback: trước publish dễ hơn sau publish

| Giai đoạn | Nếu lỗi | Hành động |
| --- | --- | --- |
| Check artifact/config | JAR thiếu, signature hoặc API version sai | Reject ngay, không tạo candidate |
| Create loader/layer | Dependency/package resolution lỗi | Cleanup candidate, v1 vẫn active |
| Instantiate/warm-up | Provider health hoặc constructor lỗi | Abort candidate, v1 vẫn active |
| Publish | Registry update không nhất quán | Không chấp nhận partial state; áp dụng atomic transaction/snapshot |
| Sau publish | v2 tăng error rate hoặc latency | Có thể chuyển về v1 **nếu v1 còn hợp lệ và dữ liệu tương thích** |
| V1 đã đóng | Cần quay lại version v1 | Tạo **generation v1 mới**, không “hồi sinh” closed loader |
| V2 đã ghi dữ liệu mới | V1 không đọc được schema mới | State/data migration hoặc rollback policy chuyên biệt, không chỉ đổi pointer |

**Rollback không hoàn nguyên side effects.** Plugin v2 có thể đã ghi database, gửi event, thay schema, tạo file hoặc gọi external APIs. Trước khi deploy cần nêu rõ backward compatibility, idempotency, transactional boundaries và data migration strategy. Nếu phải duy trì rollback window, có thể giữ old generation trong trạng thái chờ sau khi đã drain, nhưng không nên giữ vô hạn vì memory/resource pressure.

### 8.1. State migration giữa hai thế hệ

~~~text
Plugin v1 state
   │ export qua DTO/schema do host sở hữu
   ▼
Stable serialized snapshot
   │ validate/transform versioned schema
   ▼
Plugin v2 import
   │ health checks + warmup
   ▼
Publish v2 → drain v1 → retire v1
~~~

Không truyền trực tiếp object thuộc class private L1 sang L2 rồi cast: có thể `ClassCastException`. Tùy nghiệp vụ, migration cần snapshot version, replay event, dual-read/dual-write hoặc external state storage. Nếu không thể đưa hai version hoạt động trên cùng dữ liệu, không nên hứa “zero-downtime”.

## 9. ServiceLoader, TCCL và dependency visibility

### 9.1. ServiceLoader của generation mới

Với plugin classpath đăng ký `META-INF/services/<serviceFQCN>`:

~~~java
// Đoạn minh họa, chưa độc lập.
ServiceLoader<Plugin> discovered =
        ServiceLoader.load(Plugin.class, candidateLoader);

List<Plugin> candidates = discovered.stream()
        .map(ServiceLoader.Provider::get)
        .toList();
~~~

Với JPMS, dùng `ServiceLoader.load(candidateLayer, Plugin.class)` nếu service và provider modules được khai báo phù hợp. Cần xác thực provider **thuộc generation nào**; parent classloader/layer có thể lộ thêm providers từ vùng chia sẻ. Nếu có nhiều provider, `findFirst()` không phải cơ chế xếp ưu tiên ổn định theo business policy.

**`ServiceLoader.reload()` chỉ clear provider cache** của service loader đó; nó không thay JAR URLs, không định nghĩa class v2 thay v1, không dừng provider instance cũ. Muốn v2 thật sự, dùng **ServiceLoader gắn với loader/layer mới** và tạo provider instance mới theo lifecycle.

### 9.2. Thread Context ClassLoader

Một số frameworks/SPI sử dụng `Thread.currentThread().getContextClassLoader()`. Khi gọi plugin, host có thể cần TCCL của generation đó:

~~~java
// Minh họa, chưa độc lập: candidateLoader và task đã tồn tại.
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(candidateLoader);
    task.run();
} finally {
    thread.setContextClassLoader(previous);
}
~~~

**Nhất thiết restore trong finally** khi thread quay về pool. Nếu plugin tự tạo thread hoặc `ExecutorService`, thread có thể giữ TCCL của loader cũ, pin nó trong memory. Stop generation phải dừng tasks và xử lý những resource đã đăng ký trong host/global registries.

### 9.3. Dependency private

Nếu v1 cần `json-lib:1.x` còn v2 cần `json-lib:2.x`, hai generation loaders chỉ nên chứa đúng dependency riêng. Nếu `json-lib` v1 đã nằm trong host parent, parent-first có thể làm v2 vẫn dùng v1. Giữ API parent **không chứa các type private version-specific**; nếu public API dùng type đó, nó trở thành ranh giới version chung và cần versioning/adapter.

Với JPMS, build configurations cho từng generation từ module path riêng và parent ổn định. Không giả định module version field trong `ModuleDescriptor` có khả năng tự giải xung đột kiểu Maven; giải dependency graph trước khi define layer.

## 10. Giải phóng thế hệ cũ và lỗi rò class loader

Một URLClassLoader hoặc JPMS layer đã bị loại khỏi active pointer **vẫn có thể tồn tại** khi còn strong references tới bất kỳ object/class/loader tương ứng.

Những nguồn leak thường gặp:

- request/snapshot/registry còn giữ provider v1;
- `Thread.contextClassLoader`, `ThreadLocal`, daemon thread, executor, timer, scheduled jobs;
- event listener/observer/callback đăng ký trong singleton của host;
- JDBC drivers/JMX/logging providers/native libraries không unregister;
- `Class<?>`, `Method`, proxy, `MethodHandle`, reflection cache hoặc static global map;
- dependency group loader còn được dùng bởi plugin khác;
- open resources và in-flight class loading lúc gọi `URLClassLoader.close()`.

### Thứ tự cleanup gợi ý

1. Đánh dấu `RETIRING`, ngăn cấp lease mới.
2. Chờ requests/background activities đã xác định; xử lý timeout theo policy.
3. Gọi `Plugin.stop()/close()` và shutdown executors, cancel timers, unregister listeners.
4. Giải phóng connections/files/sessions, restore TCCL ở thread pools.
5. Clear registry/snapshots/caches của host đang giữ reference tới instance hoặc `Class<?>`.
6. Với classpath URLClassLoader: gọi `close()` khi không còn thread load class/resources qua nó.
7. Bỏ mọi reference tới loader/layer/module/provider và các class private từ thế hệ cũ.
8. Quan sát heap, Metaspace, loaded/unloaded classes và reference graph. **Không** khẳng định GC/unload tức thì.

`ModuleLayer` không có `close()` tương đương URLClassLoader; việc lifecycle shutdown do host/plugin thực hiện, còn việc reclaim classes phụ thuộc JVM/GC và references.

### Quan sát bằng JDK tools

~~~powershell
jar tf jars\plugin-v2.jar
jar --describe-module --file jars\plugin-v2.jar

java -Xlog:class+load=info -cp out\host HotSwapDemo jars\plugin-v1.jar jars\plugin-v2.jar

# Với tiến trình Java đang chạy; thay PID thật trước khi gọi:
jcmd 12345 help
jcmd 12345 VM.classloaders
~~~

Đây là các lệnh **chẩn đoán minh họa**. `jar --describe-module` có thể báo automatic module cho non-modular JAR hoặc hiển thị thông tin phụ thuộc JDK; các option của `jcmd` khác tùy JVM. Heap dump và thread dump giúp tìm strong references/TCCL đang giữ generation cũ.

## 11. Bảng so sánh và lỗi thường gặp

| Tình huống | Cách hiểu sai | Cách làm đúng |
| --- | --- | --- |
| v2 có cùng class name với v1 | Gọi `Class.forName` trên L1 lần nữa | Loader/layer generation mới L2 |
| Copy đè JAR cũ | Sẽ hot swap class đã load | Lưu artifact v2 bất biến, trỏ loader/layer mới vào v2 |
| Parent chứa implementation v1 | Plugin L2 tự ưu tiên class trong JAR v2 | Parent-first có thể lấy class v1; sửa loader boundary |
| Provider ở v2 không được tìm thấy | Gọi `ServiceLoader.reload()` trên v1 liên tục | Tạo service loader với L2/layer v2 và kiểm SPI/module metadata |
| Một thread đang dùng v1, deploy đóng ngay | Atomic swap đủ bảo đảm an toàn | Lease/refcount + drain/stop |
| Class cast lỗi dù cùng tên type | Chắc JVM lỗi | So sánh defining loader, thống nhất API ở parent |
| v2 dùng dependency ABI khác | JVM tự resolve đúng version | Kiểm classpath/module graph, API compatibility trước publish |
| JPMS v2 trùng module name v1 | Define v2 child của layer v1 là ổn | Sibling layers từ parent API ổn định |
| V2 startup lỗi | Chuyển routing trước rồi thử | Validate/warm up candidate trước publish |
| Rollback sau DB migration | Đổi pointer về v1 là đủ | Kiểm dữ liệu/side effects; có migration/compat plan |
| `URLClassLoader.close()` được gọi | Class phải unload ngay | Bỏ references, theo dõi GC/Metaspace, stop threads |
| Plugin của người dùng không tin cậy | Classloader đủ cách ly bảo mật | Process/container isolation và quyền OS |

## 12. Test matrix và quy trình triển khai

Một kiến trúc generation-based nên vượt qua các kiểm thử sau:

| Test | Thiết lập | Điều kiện PASS |
| --- | --- | --- |
| Load song song | Nạp v1 và v2 cùng binary name | Hai implementation classes khác loader; API parent chung |
| Candidate fail | V2 thiếu class, dependency hoặc config | V1 vẫn active; candidate được cleanup |
| Health/warm-up | Kiểm API version, gọi representative methods | Chỉ publish khi candidate READY |
| Atomic routing | Deploy khi nhiều request đồng thời | Mỗi request gắn một generation nhất quán |
| Drain | Giữ request v1 chưa kết thúc lúc swap | Không đóng v1 trước khi lease release |
| Background task | V1 có scheduler hoặc listener | Stop/unregister theo generation ownership |
| Rollback sớm | V2 lỗi ngay sau publish | Quay lại v1 còn hợp lệ, không rơi request |
| Rollback muộn | V1 đã stop/close | Tạo lại generation v1; dữ liệu vẫn tương thích |
| Dependency versions | V1 và v2 dùng thư viện khác version | Không nhầm API/private classes |
| TCCL/SPI | Provider discovery dưới thread pool | Provider đúng generation, restore TCCL |
| JPMS sibling layers | Cùng module name, v1/v2 ở hai layer riêng | Graph/layer/loader context chính xác |
| Repeated updates | V1 → V2 → V3 → V4 | Không leak threads, resource handles hoặc retained loaders |
| Cluster rollout | Nhiều JVM instances | Routing/version labels rõ trên từng instance |

### Quy trình triển khai thực tế

~~~text
1. Artifact verified (v2 + dependencies)
2. Candidate loader/layer created
3. Instantiate + validate + warm up
4. READY → publish active generation atomically
5. New requests → v2, existing leases → v1
6. Observe metrics and rollback if policy requires
7. Drain v1 → stop providers/background tasks
8. Close resources / URLClassLoader, drop references
9. Mark old generation RETIRED; monitor leaks
~~~

**Canary/rollback:** nếu yêu cầu an toàn cao, có thể route một phần traffic tới v2 rồi nâng tỷ lệ; khi đó registry phải hỗ trợ nhiều active generation theo rule và lease cho mỗi generation, không chỉ một con trỏ duy nhất. Khi v2 ảnh hưởng schema dữ liệu, rollback còn cần tương thích ở storage/protocol level.

### Những chỉ số hữu ích

Nên gắn `pluginId`, `version`, `generationId`, artifact digest và loader/layer identity vào log của request. Theo dõi in-flight leases, startup/validation duration, error rate, p95/p99 latency, active background tasks, thread count, open file handles, heap, Metaspace và class unloading. Nếu có nhiều JVM, việc swap trong một process không tự làm các process còn lại đồng bộ; phải có rollout coordinator ngoài process.

## 13. Checklist trước khi đánh dấu hoàn tất bản nâng cấp

1. **Artifact:** version và dependency manifests đã được khóa, JAR bất biến/checksum hợp lệ.
2. **Boundary:** API/DTO được định nghĩa ở parent; private classes không rò sang parent classpath.
3. **Generation:** loader/layer mới thật sự định nghĩa classes mới; không vô tình lấy implementation cũ từ ancestor.
4. **Validation:** constructor, SPI/service discovery, API compatibility, health, config và representative methods đạt.
5. **State:** import/export data qua stable schema; rollback có điều kiện rõ, không bỏ qua side effects.
6. **Publication:** routing nhất quán, cấp request lease atomically với việc chọn generation.
7. **Drain:** request cũ/background work được theo dõi, timeout policy không làm hỏng dữ liệu.
8. **Cleanup:** dừng plugin, unregister resources, restore TCCL; đóng URLClassLoader nếu có; bỏ references.
9. **JPMS:** module configuration/layer parent và loader mapping đúng; hiểu giới hạn `ModuleLayer.close()` không tồn tại.
10. **Monitoring:** log và metrics theo generation đủ để phát hiện leak hoặc mismatch.
11. **Security:** chỉ chạy mã đáng tin trong JVM; không dùng classloader như sandbox.
12. **Evidence:** kiểm thử repeated deploy, rollback và concurrency trước khi tuyên bố thay thế plugin an toàn.

**Kết luận:** để một phiên bản plugin mới thực sự xuất hiện trong JVM, cần tạo **ClassLoader hoặc ModuleLayer generation mới**, chuẩn bị và kiểm thử trước khi publish, điều phối request theo generation, rồi drain/stop phiên bản cũ. `ServiceLoader.reload()` không thay bytecode đã được define; `URLClassLoader.close()` không ép unload class; ModuleLayer cũng không tự quản lý lifecycle. Cơ chế hot replacement an toàn là tổng hợp của **class identity, dependency isolation, routing, rollback và resource ownership**.

## 14. Tài liệu tham khảo Java SE 17

- ClassLoader — delegation/class identity: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- URLClassLoader — parent loader và close semantics: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- ModuleLayer — layer definition, OneLoader/ManyLoaders: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- ModuleFinder — khám phá modular JAR: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html
- Configuration — module resolution: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html
- ServiceLoader — lookup theo ClassLoader/ModuleLayer, reload: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Module — runtime JPMS readability: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- JVM Specification 17, chapter 5 — Loading/Linking/Initializing: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
