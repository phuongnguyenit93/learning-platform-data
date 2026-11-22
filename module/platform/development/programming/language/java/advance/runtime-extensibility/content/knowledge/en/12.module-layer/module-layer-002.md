# Tạo layer con bằng defineModulesWithOneLoader trong Java

## 1. Mục tiêu: tạo một module layer con có class loader riêng

Khi ứng dụng Java sử dụng **Java Platform Module System (JPMS)**, một chương trình có thể nạp thêm các **named module** vào một `ModuleLayer` mới thay vì phải đặt tất cả module trong boot layer ngay lúc khởi động JVM. Cách này đặc biệt hữu ích khi host có hệ thống plugin và muốn tổ chức các module mở rộng theo từng lớp cấu hình và vòng đời.

`ModuleLayer` là một nhóm module đã được định nghĩa ở runtime dựa trên một `Configuration` được giải quyết trước đó. Một layer có thể tham chiếu **layer cha** để module của nó sử dụng những module phù hợp ở bên trên. `ModuleLayer.boot()` là layer được JVM tạo khi khởi động với các module của boot configuration.

Phương thức **`defineModulesWithOneLoader`** tạo **layer con** và sử dụng **một class loader mới cho mọi module được định nghĩa trong layer đó**. API này không có nghĩa là dùng trực tiếp class loader được truyền vào để định nghĩa tất cả module mới; tham số `parentLoader` là **loader cha** của loader mới do hệ thống tạo.

Một bức tranh tổng quát:

```text
ModuleLayer.boot()          (layer cha, đã tồn tại)
        |
        | configuration của cha + module path mới
        v
Configuration.resolve(...)  (xây dựng đồ thị module đã giải quyết)
        |
        | defineModulesWithOneLoader(configuration, parentLoader)
        v
child ModuleLayer
   +-- demo.api      --+
   +-- demo.plugin   --+--> cùng một loader mới của layer con
        |
        +-- sử dụng module ở layer cha nếu đồ thị cho phép
```

Ví dụ hai module `demo.api` và `demo.plugin` có thể cùng nằm trong child layer; `demo.plugin` yêu cầu `demo.api`. Hai module được nạp bởi cùng một loader mới, trong khi chương trình host có thể vẫn chạy ở classpath với system loader.

**Điều phải phân biệt:** `Configuration` mô tả những module nào được chọn và quan hệ `requires`; `ModuleLayer` định nghĩa module thật ở runtime và gắn chúng với class loader. Tạo configuration thành công **chưa** có nghĩa module đã được định nghĩa thành một layer.

## 2. Điều kiện và các thành phần tham gia

### 2.1. ModuleFinder: tìm các module có thể giải quyết

`java.lang.module.ModuleFinder` cung cấp danh sách module từ một hoặc nhiều đường dẫn:

```java
ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
```

Đây là đoạn Java minh họa, cần `import java.lang.module.ModuleFinder` và `import java.nio.file.Path`. Thư mục `mods` trong ví dụ sẽ chứa hai **exploded named modules** đã được biên dịch:

```text
mods/
  demo.api/
    module-info.class
    example/api/Message.class
  demo.plugin/
    module-info.class
    example/plugin/Greeter.class
```

`ModuleFinder` cũng có thể đọc các **modular JAR** hợp lệ trong đường dẫn được cung cấp. Không lẫn module path với classpath: một JAR được nạp bằng classpath thông thường không tự động trở thành named module của child layer. Một module được tìm thấy có thể là **explicit module** có `module-info.class` hoặc một **automatic module** trong trường hợp phù hợp; ví dụ bên dưới chủ động dùng explicit modules để giữ hành vi rõ ràng.

`ModuleFinder.of(...)` chỉ là bước xác định nguồn module. Những lỗi tìm kiếm, đọc descriptor hoặc phân giải dependency có thể chỉ xuất hiện khi gọi `find`, `findAll` hay `Configuration.resolve`, nên đừng xem việc tạo finder thành công là bằng chứng artifact hợp lệ.

### 2.2. Configuration: giải quyết đồ thị module

Từ layer cha, lấy configuration của cha rồi gọi `resolve`:

```java
ModuleLayer parent = ModuleLayer.boot();

Configuration config = parent.configuration().resolve(
        ModuleFinder.of(Path.of("mods")),
        ModuleFinder.of(),
        Set.of("demo.plugin"));
```

Đây là đoạn minh họa, cần import `java.lang.module.Configuration`, `java.lang.module.ModuleFinder`, `java.nio.file.Path` và `java.util.Set`.

Ba tham số cốt lõi của `Configuration.resolve(before, after, roots)`:

- **before:** finder ưu tiên để tìm module mới; ở đây tìm trong thư mục `mods`.
- **after:** finder dự phòng nếu module chưa được tìm ở các nơi có ưu tiên trước và trong cấu hình cha; ở đây là finder rỗng.
- **roots:** tên module gốc cần được giải quyết, ở đây chỉ có `demo.plugin`.

Nếu `demo.plugin` khai báo `requires demo.api;`, resolver đưa thêm `demo.api` vào configuration (giả sử chưa có ở configuration cha và nó được tìm thấy trong finder). Các module đã được giải quyết ở **parent configuration** có thể thỏa những dependency phù hợp và không cần định nghĩa lại trong layer con.

**Chọn root là tên module, không phải tên package hay tên JAR.** `Set.of("demo.plugin")` chỉ ra module gốc; resolver tự đi theo dependency. Nếu root không được tìm hoặc dependency bắt buộc không thỏa, việc giải quyết có thể thất bại với `java.lang.module.ResolutionException` hoặc `FindException` tùy nguyên nhân.

### 2.3. ModuleLayer: định nghĩa layer mới

Sau khi đã có `Configuration`:

```java
ModuleLayer child = parent.defineModulesWithOneLoader(
        config,
        ClassLoader.getSystemClassLoader());
```

Đây là **instance method** trên `ModuleLayer`. Nó tạo một layer con với **một parent layer**, là `parent`. Một điều kiện quan trọng là `config` phải được giải quyết với configuration của layer cha tương ứng; không được tạo configuration từ một graph cha khác rồi ghép tùy ý.

`ClassLoader.getSystemClassLoader()` được dùng ở ví dụ làm `parentLoader` của loader mới. Trong ứng dụng thật, chọn loader cha theo kiến trúc host, phiên bản API chia sẻ và những ràng buộc module layer. Module trong layer con vẫn có cơ chế liên kết/ủy quyền tới module của các layer cha phù hợp với đồ thị JPMS; không suy luận rằng cứ truyền system loader là mọi package của classpath hoặc layer cha đều tự động được module con đọc được.

Sau khi tạo, dùng:

```java
ClassLoader loader = child.findLoader("demo.plugin");
Module module = child.findModule("demo.plugin").orElseThrow();
```

`child.findLoader(...)` trả class loader được gắn với module đó. Với `defineModulesWithOneLoader`, các module **được định nghĩa mới trong cùng child layer** trả về cùng một loader. `child.findModule(...)` là phép tìm module theo layer và các layer cha; khi cần xác nhận module thực sự thuộc layer mới, xem `child.modules()`.

## 3. Ví dụ đầy đủ Java 17+: hai named module trong một child layer

Ví dụ gồm **hai named module được biên dịch riêng** và một chương trình launcher chạy trên classpath. Module `demo.plugin` dùng class `Message` của module `demo.api`. Launcher tự tạo child layer, lấy class loader của từng module và gọi mã plugin bằng reflection.

### 3.1. Cấu trúc source

Tạo cây thư mục dưới thư mục làm việc:

```text
src/
  demo.api/
    module-info.java
    example/
      api/
        Message.java
  demo.plugin/
    module-info.java
    example/
      plugin/
        Greeter.java
  LayerDemo.java
```

Tên thư mục ngay dưới `src` phải trùng tên module để `javac --module-source-path src` nhận đúng các nguồn modular.

**Tệp `src/demo.api/module-info.java`:**

```java
module demo.api {
    exports example.api;
}
```

Module này công bố package `example.api` cho các module khác; class bên trong package đó có thể được dùng ở runtime nếu quan hệ module cho phép.

**Tệp `src/demo.api/example/api/Message.java`:**

```java
package example.api;

public final class Message {
    private Message() {}

    public static String text() {
        return "hello";
    }
}
```

**Tệp `src/demo.plugin/module-info.java`:**

```java
module demo.plugin {
    requires demo.api;
    exports example.plugin;
}
```

`requires demo.api` tạo dependency có kiểm soát trên module API. `exports example.plugin` cho phép launcher bên ngoài module gọi public class/method trong package này bằng reflection thông thường.

**Tệp `src/demo.plugin/example/plugin/Greeter.java`:**

```java
package example.plugin;

import example.api.Message;

public final class Greeter {
    public Greeter() {}

    public String greet() {
        return Message.text() + " from child layer";
    }
}
```

`Greeter` là implementation thuộc `demo.plugin`. Khi được nạp trong child layer, nó gọi một class thuộc module `demo.api`, vốn được giải quyết cùng layer.

### 3.2. Chương trình tạo layer

**Tệp `src/LayerDemo.java`:**

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class LayerDemo {
    public static void main(String[] args) throws Exception {
        ModuleLayer parent = ModuleLayer.boot();
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
        Configuration config = parent.configuration().resolve(
                finder, ModuleFinder.of(), Set.of("demo.plugin"));

        ModuleLayer child = parent.defineModulesWithOneLoader(
                config, ClassLoader.getSystemClassLoader());

        ClassLoader apiLoader = child.findLoader("demo.api");
        ClassLoader pluginLoader = child.findLoader("demo.plugin");
        Class<?> greeterType = pluginLoader.loadClass("example.plugin.Greeter");
        Object greeter = greeterType.getDeclaredConstructor().newInstance();

        System.out.println("modules: " + child.modules().size());
        System.out.println("same loader: " + (apiLoader == pluginLoader));
        System.out.println("boot is parent: " + child.parents().contains(parent));
        System.out.println("provider module: " + greeterType.getModule().getName());
        System.out.println("result: " + greeterType.getMethod("greet").invoke(greeter));
    }
}
```

Đây là chương trình **chạy độc lập** khi đi kèm các module ở trên. Nó sử dụng reflection để truy cập class của child layer vì launcher trên classpath không khai báo `requires demo.plugin` tại thời điểm biên dịch. API `ModuleLayer` thuộc JDK, không cần thư viện ngoài.

### 3.3. Biên dịch và chạy

Chạy các lệnh sau ở **thư mục cha chứa `src`**, với JDK 17+:

```bash
javac --release 17 --module-source-path src -d mods --module demo.api,demo.plugin
javac --release 17 -d out src/LayerDemo.java
java -cp out LayerDemo
```

Lệnh đầu đặt các class/module descriptor vào `mods/demo.api` và `mods/demo.plugin`. Lệnh thứ hai biên dịch launcher vào `out`. Lệnh cuối chạy launcher trên classpath; nó chủ động đọc module từ `mods` rồi tạo layer mới.

**Đầu ra** đã được kiểm tra bằng `javac --release 17` và `java` trên JDK:

```text
modules: 2
same loader: true
boot is parent: true
provider module: demo.plugin
result: hello from child layer
```

Giải thích đầu ra:

1. `modules: 2`: khi root `demo.plugin` được giải quyết, `demo.api` cũng được đưa vào child configuration do quan hệ `requires`. Layer mới chứa đúng hai module mới.
2. `same loader: true`: `child.findLoader("demo.api")` và `child.findLoader("demo.plugin")` là **cùng một instance** class loader, đúng cam kết của `defineModulesWithOneLoader`.
3. `boot is parent: true`: `child.parents()` chứa `ModuleLayer.boot()`, tức layer mới có quan hệ cha với boot layer.
4. `provider module: demo.plugin`: `Greeter` thuộc named module đã được định nghĩa trong child layer, không phải một class vô danh tải từ classpath.
5. `result: hello from child layer`: constructor và method public chạy được; module `demo.plugin` đọc API mà nó khai báo `requires`.

**Vì sao không dùng `Class.forName("example.plugin.Greeter")` với overload mặc định?** Overload đó dùng loader gắn với code gọi (với launcher này là loader của classpath host), không tự biết class của layer con vừa tạo. Phải chủ động lấy `child.findLoader("demo.plugin")` và dùng `loadClass` hoặc `Class.forName(name, initialize, loader)` phù hợp.

## 4. Điều gì thật sự được chia sẻ khi dùng “one loader”?

`defineModulesWithOneLoader` nghĩa là **các module của layer mới cùng một defining class loader do JVM tạo**. Nó **không** có nghĩa mọi module trở thành một module duy nhất hoặc bỏ kiểm tra encapsulation.

| Thuộc tính | Khi dùng một loader trong child layer |
| --- | --- |
| Class loader cho `demo.api` và `demo.plugin` | Cùng một instance |
| Danh tính module | Vẫn là hai module khác nhau |
| `requires`, `exports`, `opens` | Vẫn được kiểm tra theo JPMS |
| Module layer cha | Vẫn là layer riêng biệt |
| Class loader truyền làm `parentLoader` | Là loader cha cho loader mới, không phải chính loader mới |
| Khả năng load qua classpath host mặc định | Không tự xảy ra nếu host không tham chiếu tới loader/layer mới |
| Cô lập giữa hai module có cùng loader | Ít hơn mô hình nhiều loader; vẫn có ranh giới module access |
| Vòng đời module/class loader | Chịu ảnh hưởng của tham chiếu tới layer, module, class, instance và thread |

Một quyết định quan trọng: **hai module được định nghĩa trong cùng một class loader không được cùng chứa một package**. Ví dụ nếu `demo.api` và `demo.plugin` đều định nghĩa package `example.shared` trong cùng layer, việc tạo layer một-loader có thể thất bại với `LayerInstantiationException` vì xung đột package. `Configuration.resolve` và layer instantiation không phải cùng một bước; kiểm tra thành công ở bước resolve không bảo đảm mọi ràng buộc class-loader/package đều thỏa.

Nếu cần nạp các plugin có dependency trùng package nhưng khác version, **một loader cho tất cả plugin** thường không phải phương án phù hợp. Có thể thiết kế **một child layer cho từng nhóm plugin** (mỗi nhóm có loader riêng) hoặc dùng `defineModulesWithManyLoaders` khi cấu hình cho phép. Tuy nhiên không chọn nhiều loader chỉ để “hết lỗi”: những kiểu Java dùng chung qua boundary vẫn phải có chiến lược API và class identity nhất quán.

## 5. So sánh các API định nghĩa module layer

| API | Đặc điểm | Khi nào xem xét |
| --- | --- | --- |
| `parent.defineModulesWithOneLoader(cf, parentLoader)` | Instance method; trả về `ModuleLayer`; các module mới dùng chung loader | Một layer con dưới một parent, muốn bộ module chia sẻ loader |
| `parent.defineModulesWithManyLoaders(cf, parentLoader)` | Instance method; mỗi module mới gắn với một loader riêng | Muốn tách loader của các module trong cùng configuration |
| `parent.defineModules(cf, nameToLoader)` | Tự chỉ định ánh xạ module name → loader | Kiến trúc loader tùy chỉnh; cần thiết kế và kiểm soát nhất quán |
| `ModuleLayer.defineModulesWithOneLoader(cf, parents, parentLoader)` | Static method; nhận danh sách parent layers và trả `ModuleLayer.Controller` | Có nhiều parent layer hoặc cần controller cho các điều chỉnh có kiểm soát |

Với trường hợp chỉ một parent và không cần controller, **instance method** như ví dụ là lựa chọn đơn giản và rõ ràng.

Nếu cần phiên bản static:

```java
ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithOneLoader(
                config,
                java.util.List.of(parent),
                ClassLoader.getSystemClassLoader());

ModuleLayer child = controller.layer();
```

Đây là **đoạn API minh họa**, giả định `config` đã được giải quyết theo đúng danh sách parent configuration, và `parent` là parent layer tương ứng. `Controller` có các khả năng điều chỉnh một số quan hệ reads/exports/opens cho module của layer mới trong phạm vi API; việc có controller không đồng nghĩa có thể vô hiệu hóa tùy ý mọi giới hạn của JPMS hoặc thay thế kiểm tra compatibility.

Trong hệ nhiều parent layers, không thể thay bừa `List.of(parent)` bằng một danh sách khác configuration được resolve. Quan hệ giữa `Configuration.parents()` và các parent layers thực tế cần khớp, đúng thứ tự theo contract.

## 6. Các vấn đề thiết kế thường gặp

### 6.1. Package exports/opens và reflection

Ví dụ `Greeter` ở trên có `public class`, `public constructor` và `public method`. Nếu module `demo.plugin` **không export** package `example.plugin`, launcher thuộc unnamed module có thể tải/nhìn thấy class nhưng không được gọi reflection thông thường vào member public từ bên ngoài module. Khi đó có thể gặp `IllegalAccessException`. Đối với deep reflection lên member không public, có thể cần `opens` phù hợp; `exports` không tự cấp quyền deep reflection.

**Không nhầm “cùng class loader” với “mọi package đều mở”.** `requires` quyết định khả năng đọc module, `exports` quyết định truy cập public type/member theo package, còn `opens` chủ yếu phục vụ reflective access. Quy tắc chi tiết phụ thuộc quan hệ caller và module đích.

### 6.2. API/SPI nên đặt ở đâu?

Nếu host và plugin cùng cần một interface như `com.acme.spi.Plugin`, nên xác định **một bản API/SPI có danh tính runtime chung**. Thường host cung cấp API trong parent layer, rồi child module khai báo `requires` tới module API đó. Khi ấy plugin và host cùng tham chiếu đúng `Class<?>` của interface, tránh việc hai bên tự định nghĩa các bản sao.

Ví dụ bài này đặt `demo.api` cùng layer con để minh họa dependency giữa hai module mới; trong hệ thống plugin thực, nếu host cần trực tiếp cast provider thành interface, API dùng chung thường phải được host nhìn thấy trước (ở parent layer hoặc một arrangement được thiết kế tương thích). Đưa API vào layer con không tự làm host trên classpath biết kiểu đó tại compile time.

Nếu dùng `ServiceLoader.load(layer, serviceType)`, cần đảm bảo service type mà consumer dùng có danh tính đúng, provider module khai báo `provides ... with ...` và consumer/module có khả năng dùng service theo quy tắc JPMS. `ServiceLoader` dựa vào layer và cấu hình provider thực tế, không tự tạo các `requires`/`exports` thiếu.

### 6.3. Không dùng classpath thay cho module resolution

Một lỗi phổ biến là build plugin JAR rồi chỉ thêm nó vào `-cp` và kỳ vọng `ModuleFinder.of(Path)` hoặc `Configuration.resolve` tự tìm được nó như một named module. Cần đưa artifact hợp lệ vào đường dẫn finder cung cấp; phiên bản JAR là modular hoặc automatic module theo quy tắc JPMS. Ngược lại, thêm JAR vào `--module-path` khi khởi động cũng không tự xác nhận rằng module đã được resolve vào child layer muốn tạo.

Không có “đường tắt” giúp `defineModulesWithOneLoader` biến một file tùy ý thành module hợp lệ. Module discovery, descriptor parsing và resolution phải được thực hiện đúng.

### 6.4. Missing dependencies, split packages, version

Những lỗi có thể xuất hiện ở các thời điểm khác nhau:

| Giai đoạn | Ví dụ vấn đề | Hướng xử lý |
| --- | --- | --- |
| Tìm module | Path sai, artifact không thể đọc, descriptor hỏng | Kiểm tra output build, tên module, `ModuleFinder` và `FindException` |
| Resolve configuration | Root không tìm được, `requires` không thỏa, graph mâu thuẫn | Kiểm tra `Configuration.resolve` và `ResolutionException` |
| Define layer | Ràng buộc package/class loader không hợp lệ cho một-loader | Xem `LayerInstantiationException` và bố cục package |
| Load class | Gọi bằng loader của host, tên class sai, class thiếu | Dùng `child.findLoader(moduleName)`, kiểm tra binary name |
| Reflective access | Module không `exports`/`opens` như mục đích gọi | Sửa module descriptor theo contract; không chỉ `setAccessible(true)` |
| Instantiate/invoke | Constructor hoặc method plugin ném exception | Xem cause và exception chain, kiểm tra environment |
| Service discovery | Sai `provides`/service type hoặc loader/layer | Kiểm tra module metadata, danh tính SPI và `ServiceLoader` |

JPMS **không tự giải quyết semantic versioning của plugin** chỉ bằng việc đặt version vào tên JAR. Nếu host có chính sách tương thích, hãy kiểm tra version API, Java baseline và dependency range riêng trước khi đưa artifact vào runtime. `Configuration.resolve` chủ yếu giải quyết đồ thị module, không phải bộ quản lý dependency version như Maven/Gradle.

### 6.5. Layer mới không tự được “cài” vào boot layer

`ModuleLayer.boot()` không thay đổi sau khi tạo layer con. Những module ở layer con không mặc định trở thành một phần của module graph lúc khởi động hoặc tự xuất hiện với mọi class loader đang có.

Host nên giữ rõ reference tới `ModuleLayer` và dùng `findModule`/`findLoader`/`ServiceLoader.load(layer, ...)` tại điểm tích hợp. Không nên sửa biến global hoặc classpath tùy tiện để “đánh lừa” lớp đang chạy rằng plugin đã nằm sẵn ở boot layer.

### 6.6. ModuleLayer không phải sandbox bảo mật

Layer và class loader cung cấp **ranh giới module, namespace và tổ chức vòng đời**. Chúng không mặc nhiên cấm plugin đọc file, kết nối mạng hoặc gọi API có quyền mà host cho phép. Khi thực thi code không tin cậy, cần ranh giới bảo mật riêng như tiến trình, quyền hệ điều hành, container, IPC và chính sách authorization. Không dùng `defineModulesWithOneLoader` như bằng chứng plugin được cô lập tuyệt đối.

## 7. Vòng đời, reload và lựa chọn cấu trúc

Khi module và class đã được định nghĩa trong layer, không thể chỉ đổi một `Configuration` rồi buộc class đang tồn tại chuyển sang loader khác. Một lần cập nhật plugin thường gồm:

1. Chuẩn bị và kiểm tra artifact mới.
2. Tạo `ModuleFinder` và configuration mới từ parent phù hợp.
3. Tạo **child layer mới** bằng phương thức đã chọn.
4. Khởi tạo/kiểm thử implementation mới, rồi chuyển registry hoặc routing của host sang bản đó theo chiến lược rõ ràng.
5. Gỡ listener, task, cache, thread context class loader, service instance và những tham chiếu tới layer/class/loader cũ khi không còn sử dụng.

`ModuleLayer` không phải một `AutoCloseable` chuẩn và không có phép “unload module ngay lập tức”. Việc bộ nạp/layer cũ có thể được GC phụ thuộc việc còn tham chiếu mạnh tới class, instance, loader, thread hoặc cache hay không. Tạo layer mới liên tục mà không hủy registration có thể gây tăng memory/metaspace.

Với nhiều plugin độc lập, một layer con **chứa tất cả module của mọi plugin** và một loader chung có thể tiết kiệm số lượng loader, nhưng không phù hợp nếu các plugin xung đột package hoặc cần lifecycle tách biệt. Lựa chọn layer-per-plugin, group-per-layer hay many-loaders tùy đồ thị `requires`, số phiên bản dependency cần đồng tồn tại và boundary API.

## 8. Checklist thiết kế và kiểm thử

- **Artifact:** mọi root/dependency cần resolve là named module hợp lệ, module path đúng và có `module-info.class` khi dùng explicit module?
- **Configuration:** `parent.configuration()` đúng parent layer, `resolve` chọn đúng roots và bao gồm dependency bắc cầu?
- **Layer:** `defineModulesWithOneLoader` thành công; `child.parents()` và `child.modules()` đúng kỳ vọng?
- **Class loaders:** `findLoader` trả cùng loader cho **các module mới** trong child layer; host dùng đúng loader khi load class?
- **Type identity:** các API/SPI dùng chung không bị định nghĩa lại sai ở layer/plugin?
- **Access control:** `requires`, `exports`, `opens` đủ cho import, reflection, callback và service provider?
- **Package constraints:** các module gắn cùng một loader không định nghĩa trùng package?
- **Service discovery:** `provides`/`uses` và `ServiceLoader` khớp service type/layer mong muốn?
- **Failure mode:** log rõ lỗi ở các bước find, resolve, define, load, reflect và initialize?
- **Lifecycle:** ứng dụng có chiến lược tạo layer mới khi upgrade và giải phóng reference tới layer cũ?

**Kết luận kỹ thuật:** muốn tạo child layer với `defineModulesWithOneLoader`, hãy **tìm module (`ModuleFinder`) → giải quyết configuration (`Configuration.resolve`) → định nghĩa layer (`parent.defineModulesWithOneLoader`) → lấy loader/module từ layer mới (`findLoader`/`findModule`)**. Một loader chung chỉ quy định chiến lược định nghĩa class cho các module mới; JPMS vẫn kiểm tra đồ thị phụ thuộc, exports/opens và các ranh giới cần thiết.