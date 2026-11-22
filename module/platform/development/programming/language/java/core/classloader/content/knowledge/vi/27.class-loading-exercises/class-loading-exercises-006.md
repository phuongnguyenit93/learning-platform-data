# Tạo ModuleLayer cho plugin mô đun hóa với Java 17+

## 1. Bài toán: nạp plugin dưới dạng named module khi host đang chạy

Trong Java Platform Module System (**JPMS**, Java 9+), một plugin không nhất thiết chỉ là một JAR đặt trên classpath rồi tìm implementation bằng `Class.forName`. Plugin có thể là **named module**, có file `module-info.java`, khai báo phụ thuộc `requires` và nhà cung cấp dịch vụ `provides ... with ...`.

Một ứng dụng chủ (**host**) có thể bắt đầu mà **không resolve plugin module**, sau đó:

1. Khám phá module artifact bằng `ModuleFinder`.
2. Resolve module graph mới dựa trên `Configuration` của parent layer.
3. Định nghĩa runtime modules và ánh xạ loader bằng `ModuleLayer.defineModulesWithManyLoaders` (hoặc `WithOneLoader`).
4. Tìm service providers trong **layer mới** bằng `ServiceLoader.load(layer, ServiceType.class)`.
5. Gọi plugin qua **shared API module** của host, không import implementation class.
6. Quản lý vòng đời layer, instances, class loaders, caches và các resources liên quan.

Bài thực hành này sẽ có ba phần:

~~~text
Boot ModuleLayer (ModuleLayer.boot())
  |
  +-- plugin.api named module
  |     exports plugin.api.Extension
  |
  +-- java.base và các system modules đã resolve
  |
  v
Child ModuleLayer (được tạo động)
  |
  +-- plugin.echo named module
        requires plugin.api
        provides plugin.api.Extension
          with plugin.echo.EchoExtension
~~~

**Điểm cốt lõi:** API `plugin.api.Extension` phải có **cùng runtime class identity** ở host và provider. Plugin implementation được định nghĩa ở **child layer**, còn shared API module đã tồn tại trong **boot parent layer**. Đây là cách giữ hợp đồng giao tiếp trong khi cho phép khám phá plugin mới lúc chạy.

### Kết quả cần đạt

Bạn sẽ xây được chương trình Java 17+ không cần Maven/Gradle, có một module API, một module provider và launcher host; tự biên dịch từng phần; tạo `Configuration` rồi `ModuleLayer`; dùng `ServiceLoader.load(layer, ...)`; xác minh defining loader, runtime module identity, parent visibility và việc tạo hai child layers độc lập.

Bài cũng giải thích khác nhau giữa module path với classpath, `ModuleFinder` với `Configuration`, parent `ModuleLayer` với parent `ClassLoader`, lựa chọn one/many/custom loaders, giới hạn visibility/exports/opens, sự khác nhau giữa `resolve` và `resolveAndBind` và các lỗi thường gặp trong hệ plugin thực tế.

## 2. Bốn đối tượng khác nhau của JPMS

### 2.1. Module artifact và module descriptor

Một modular JAR hoặc một directory module đã biên dịch chứa `module-info.class`. Tệp source descriptor:

~~~java
module plugin.echo {
    requires plugin.api;
    provides plugin.api.Extension
        with plugin.echo.EchoExtension;
}
~~~

Ở runtime, thông tin descriptor cho biết:

- **Module name**: `plugin.echo`.
- **Requires**: cần `plugin.api`.
- **Provides**: đăng ký provider `plugin.echo.EchoExtension` cho service `plugin.api.Extension`.
- Các directives khác có thể là `exports`, `opens`, `uses`.

Một artifact xuất hiện trên disk **chưa đồng nghĩa** module của nó đã được resolve hoặc có runtime `Module` object.

### 2.2. ModuleFinder: tìm artifacts/module references

~~~java
ModuleFinder finder =
        ModuleFinder.of(Path.of("build/plugins"));
~~~

`ModuleFinder` biết cách nhận diện module artifacts ở những roots được chỉ định; nó không tự define runtime classes hay khởi động provider.

Trong demo, `build/plugins` chứa exploded module directory `plugin.echo`. Có thể thay bằng modular JAR nếu đã đóng gói đúng và chỉ định path phù hợp.

### 2.3. Configuration: module graph đã resolve

~~~java
Configuration configuration =
        ModuleLayer.boot().configuration().resolve(
                finder,
                ModuleFinder.of(),
                Set.of("plugin.echo"));
~~~

Đây là graph của **các modules mới được resolve** dựa trên parent configuration. `resolve` xử lý `requires` và các ràng buộc resolution, không tự instantiate provider hay tạo ClassLoader.

Các tham số cần phân biệt:

- `finder` thứ nhất: module artifacts có thể dùng trong cuộc resolution hiện tại.
- `ModuleFinder.of()`: danh mục after finder trong API này, ở demo để trống.
- `Set.of("plugin.echo")`: **root module names** yêu cầu resolve.

API `plugin.api` đã ở parent boot configuration; resolver có thể thỏa `requires plugin.api` từ parent, nên **không cần tạo bản thứ hai của API trong child**.

### 2.4. ModuleLayer: định nghĩa runtime modules và loaders

~~~java
ModuleLayer layer = ModuleLayer.boot()
        .defineModulesWithManyLoaders(
                configuration,
                ClassLoader.getSystemClassLoader());
~~~

Đây là thời điểm tạo runtime `Module` objects và ánh xạ named modules mới vào loader(s). Method instance `defineModulesWithManyLoaders` trả `ModuleLayer`.

Trong thí nghiệm:

- Parent module layer: `ModuleLayer.boot()`.
- Parent `Configuration`: `boot.configuration()`.
- Child configuration chứa `plugin.echo`.
- Loader strategy: **mỗi module mới** có loader mới riêng.
- Tham số `ClassLoader.getSystemClassLoader()` là **parent ClassLoader cho loader mới**, **không** có nghĩa plugin được định nghĩa trực tiếp trong application/system loader.

**Tách bạch ba quan hệ:** JPMS module readability (có thể đọc module nào), parent layer relation (layer nào là cha), và ClassLoader delegation (loader nào nạp/ủy quyền những classes nào). Chúng liên quan nhưng **không đồng nhất**.

## 3. Thiết kế host, shared API và plugin module

### 3.1. Hợp đồng API dùng chung

API module tên `plugin.api`:

~~~java
module plugin.api {
    exports plugin.api;
}
~~~

Và interface:

~~~java
package plugin.api;

public interface Extension {
    String name();
    String execute(String input);
}
~~~

Lựa chọn này giữ public contract nhỏ. Host và implementation chỉ biết `Extension`, không cần chia sẻ implementation type hay thư viện riêng của plugin.

**Trách nhiệm của API module:** quản lý các service interfaces, DTOs và exceptions đi qua boundary. Với hệ nhiều plugin, không để provider định nghĩa thêm bản `plugin.api.Extension` riêng; nếu không runtime type identity có thể bị chia đôi và cast/service discovery thất bại.

### 3.2. Plugin implementation module

Descriptor:

~~~java
module plugin.echo {
    requires plugin.api;
    provides plugin.api.Extension with plugin.echo.EchoExtension;
}
~~~

Provider class:

~~~java
package plugin.echo;

import plugin.api.Extension;

public final class EchoExtension implements Extension {
    @Override
    public String name() {
        return "echo";
    }

    @Override
    public String execute(String input) {
        return "PLUGIN:" + input;
    }
}
~~~

**Không cần `exports plugin.echo;`** chỉ để `ServiceLoader` tạo provider đã khai báo qua `provides ... with ...`. Cơ chế provider factory được JPMS/`ServiceLoader` xử lý theo hợp đồng. Host không cần truy cập trực tiếp type implementation bằng Java source import.

Trong demo, provider có public no-arg constructor mặc định. Trong hệ thực tế, provider requirements, constructor và static `provider()` factory behavior còn tùy named module/service-provider contract, cần kiểm tra Javadoc tương ứng.

### 3.3. Host biết API và child ModuleLayer, không biết EchoExtension

Host sẽ viết:

~~~java
for (Extension extension :
        ServiceLoader.load(layer, Extension.class)) {
    System.out.println(extension.execute("hello"));
}
~~~

Không có:

~~~java
import plugin.echo.EchoExtension;
~~~

Điều đó cho phép plugin module **không xuất hiện lúc compile host** hoặc không có trong boot layer. Vòng đời plugin có thể được xử lý qua interface API và metadata/service registry.

### 3.4. Vì sao API nên nằm ở parent layer?

Nếu host dùng `plugin.api.Extension` thuộc boot layer nhưng plugin child tự resolve thêm một `plugin.api` khác cùng tên dưới một layer khác, có nguy cơ host và plugin không dùng cùng `Class<?>`.

Thiết kế khuyến nghị trong demo:

~~~text
Boot layer:
  plugin.api.Extension => Class<?> chung

Child layer:
  plugin.echo.EchoExtension
       implements Extension từ parent
~~~

Điều kiện quan trọng là **module resolution graph và module-classloader mapping** thực sự dẫn provider đến chính `Extension.class` của host; không đủ khi chỉ kiểm tra hai bytecode JAR “trông giống nhau”.

## 4. Cấu trúc dự án demo

~~~text
demo/
├── src/
│   ├── plugin.api/
│   │   ├── module-info.java
│   │   └── plugin/api/Extension.java
│   ├── plugin.echo/
│   │   ├── module-info.java
│   │   └── plugin/echo/EchoExtension.java
│   └── host/
│       └── HostMain.java
└── build/
    ├── mods/
    │   └── plugin.api/          # module API đã compile
    ├── plugins/
    │   └── plugin.echo/         # module provider đã compile
    └── host/                    # launcher trên classpath
~~~

**Tách hai directory có chủ đích:**

- `build/mods` là **module path khi chạy host** để `plugin.api` được resolve vào boot layer.
- `build/plugins` **không nằm trên `--module-path` của launcher**; host chỉ truyền path này cho `ModuleFinder.of` **khi đang chạy**.
- `build/host` là classpath chứa `HostMain.class` trong **unnamed module**.

Nhờ đó, bài kiểm thử `echoNotInBoot=true` có ý nghĩa thật sự: provider không bị launcher resolve trước khi code host tạo child layer.

Nếu để `plugin.echo` vào boot module path **và thêm nó làm root module** bằng `--add-modules`, demo không còn đo đúng quá trình dynamic layer creation.

## 5. File nguồn của shared API module

### 5.1. `src/plugin.api/module-info.java`

~~~java
module plugin.api {
    exports plugin.api;
}
~~~

`exports plugin.api;` cho phép code từ module khác (kể cả unnamed host module) dùng public types của package API khi có readability phù hợp.

### 5.2. `src/plugin.api/plugin/api/Extension.java`

~~~java
package plugin.api;

public interface Extension {
    String name();
    String execute(String input);
}
~~~

Trong chương trình, `Extension.class` được host truyền vào `ServiceLoader.load(layer, Extension.class)`. Nó là một type cụ thể được JVM định nghĩa, không phải một chuỗi service name.

## 6. File nguồn của plugin provider module

### 6.1. `src/plugin.echo/module-info.java`

~~~java
module plugin.echo {
    requires plugin.api;
    provides plugin.api.Extension with plugin.echo.EchoExtension;
}
~~~

Không cần `uses plugin.api.Extension;` trong chính plugin provider module để khai báo provider; `uses` là directive cho **module tiêu thụ service**.

Host demo là unnamed module. Nếu host được mô đun hóa thành named module `plugin.host`, descriptor nên có:

~~~java
module plugin.host {
    requires plugin.api;
    uses plugin.api.Extension;
}
~~~

Đây là **descriptor minh họa cho kiến trúc named host**, **không dùng trong source demo runnable** ở mục 8. Khi host là named module tiêu thụ service, `uses` là điểm cần khai báo để `ServiceLoader` hợp lệ. Mục đích demo dùng unnamed host là đơn giản hóa biên dịch và nhấn mạnh dynamic layer; nó vẫn có quyền gọi service API đã được resolve trong boot.

### 6.2. `src/plugin.echo/plugin/echo/EchoExtension.java`

~~~java
package plugin.echo;

import plugin.api.Extension;

public final class EchoExtension implements Extension {
    @Override
    public String name() {
        return "echo";
    }

    @Override
    public String execute(String input) {
        return "PLUGIN:" + input;
    }
}
~~~

Plugin này chỉ nhận và trả `String` thuộc Java platform để output không phụ thuộc serialization hay versioning của DTO. Production có thể thay bằng `Request`/`Response` thuộc API module, nhưng phải giữ API version/identity nhất quán.

## 7. Tạo child ModuleLayer đúng thứ tự

### 7.1. Xác nhận API đã được resolve trong boot

~~~java
ModuleLayer boot = ModuleLayer.boot();
boolean apiInBoot = boot.findModule("plugin.api").isPresent();
~~~

Nếu `plugin.api` không ở boot, `requires plugin.api` trong provider có thể không được resolver đáp ứng từ parent như ta dự định. Demo chủ động chạy với `--add-modules plugin.api` để tạo root cho API boot layer.

### 7.2. Xác nhận plugin chưa ở boot

~~~java
boolean pluginNotYetLoaded =
        boot.findModule("plugin.echo").isEmpty();
~~~

Đây là kiểm tra **module đã được định nghĩa trong layer**; nó không khẳng định artifact không tồn tại trên disk. Plugin có sẵn ở `build/plugins` nhưng chưa resolve trong boot configuration.

### 7.3. ModuleFinder đọc plugin artifact

~~~java
ModuleFinder finder =
        ModuleFinder.of(Path.of("build/plugins"));
~~~

Với cấu trúc thư mục đã chuẩn, finder nhận `plugin.echo`. Nếu `module-info.class` thiếu hoặc directory/JAR module không hợp lệ, bước discovery/resolution có thể thất bại. Phải dùng **module root**, không truyền nhầm source tree hoặc output directory chứa nhiều files vô tổ chức.

### 7.4. Resolve roots, giữ API ở parent

~~~java
Configuration configuration = boot.configuration()
        .resolve(finder, ModuleFinder.of(), Set.of("plugin.echo"));
~~~

Ý nghĩa:

~~~text
Parent Configuration:
  plugin.api (đã resolved)
     ^
     | requires
New Configuration:
  plugin.echo
~~~

`resolve` không tạo runtime classes; nó chỉ tạo graph có các module references và readability dependencies hợp lệ. Vì root set chứa `plugin.echo`, provider module được resolve **dù host không có compile-time dependency đến provider**.

`resolveAndBind` là một phương thức khác: ngoài roots/requires, nó còn có service binding resolution giúp kéo thêm provider modules phù hợp theo module graph. Trong demo, ta **đã đặt `plugin.echo` làm root tường minh**, nên không cần service binding để chọn plugin. Nếu muốn khám phá providers tự động theo `uses/provides`, phải thiết kế giải thuật `resolveAndBind` và module finder scope/parent config rõ.

### 7.5. Định nghĩa runtime layer và chọn ClassLoader policy

~~~java
ModuleLayer layer = boot.defineModulesWithManyLoaders(
        configuration,
        ClassLoader.getSystemClassLoader());
~~~

Dạng instance này trả `ModuleLayer`. `WithManyLoaders` tạo một loader mới cho **mỗi named module được định nghĩa trong configuration mới**, không yêu cầu mỗi module của **parent boot layer** cũng được tạo lại.

Sau đó:

~~~java
Module providerModule =
        layer.findModule("plugin.echo").orElseThrow();

ClassLoader providerLoader =
        layer.findLoader("plugin.echo");
~~~

`layer.findModule` có thể tìm ở current layer hoặc parents, còn `layer.modules()` chỉ là modules định nghĩa trực tiếp ở current layer. `layer.findLoader` tra loader của module tương ứng trong current/parent layers; nó có thể trả `null` cho bootstrap loader, không phải chỉ cho module thiếu.

### 7.6. Phân biệt module loader và parent loader

Trong demo:

~~~java
ClassLoader appLoader = ClassLoader.getSystemClassLoader();
ClassLoader pluginLoader = layer.findLoader("plugin.echo");
~~~

- `appLoader` là **parent loader parameter** được truyền khi tạo child layer.
- `pluginLoader` là **defining loader** do layer creation thiết lập cho plugin module.
- `Extension.class.getClassLoader()` thuộc loader định nghĩa shared API module ở boot layer.
- Plugin implementation class sẽ có loader `pluginLoader`, nhưng interface API có class identity từ shared parent.

Không khẳng định chỉ từ việc có một parent loader rằng plugin class đã được **định nghĩa bởi parent**. Đó là sai khác giữa **ủy quyền** và **định nghĩa**.

## 8. Chương trình Java 17+ đầy đủ, có thể chạy ngay

Lưu file `src/host/HostMain.java`:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.ServiceLoader;
import java.util.Set;
import plugin.api.Extension;

public final class HostMain {
    public static void main(String[] args) {
        ModuleLayer boot = ModuleLayer.boot();

        System.out.println("apiInBoot="
                + boot.findModule("plugin.api").isPresent());
        System.out.println("echoNotInBoot="
                + boot.findModule("plugin.echo").isEmpty());

        ModuleFinder finder = ModuleFinder.of(
                Path.of("build/plugins"));
        Configuration configuration = boot.configuration()
                .resolve(finder, ModuleFinder.of(),
                         Set.of("plugin.echo"));

        ModuleLayer layer = boot.defineModulesWithManyLoaders(
                configuration, ClassLoader.getSystemClassLoader());
        Module pluginModule =
                layer.findModule("plugin.echo").orElseThrow();
        ClassLoader pluginLoader = layer.findLoader("plugin.echo");

        System.out.println("pluginResolved="
                + configuration.findModule("plugin.echo").isPresent());
        System.out.println("newLayerModule="
                + layer.modules().contains(pluginModule));
        System.out.println("parentApiVisible="
                + layer.findModule("plugin.api").isPresent());
        System.out.println("loaderFindsParentApi="
                + (layer.findLoader("plugin.api")
                    == boot.findLoader("plugin.api")));

        int count = 0;
        for (Extension ext :
                ServiceLoader.load(layer, Extension.class)) {
            count++;
            System.out.println("providerName=" + ext.name());
            System.out.println("providerResult=" + ext.execute("hello"));
            System.out.println("providerInChildModule="
                    + (ext.getClass().getModule() == pluginModule));
            System.out.println("providerLoaderMatches="
                    + (ext.getClass().getClassLoader() == pluginLoader));
            System.out.println("sharedApiIdentity="
                    + Extension.class.isAssignableFrom(ext.getClass()));
        }
        System.out.println("providerCount=" + count);

        ModuleLayer second = boot.defineModulesWithManyLoaders(
                configuration, ClassLoader.getSystemClassLoader());
        System.out.println("separateLayerSeparateModule="
                + (second.findModule("plugin.echo").orElseThrow()
                    != pluginModule));
        System.out.println("separateLayerSeparateLoader="
                + (second.findLoader("plugin.echo") != pluginLoader));
    }
}
~~~

Các thao tác:

- `ModuleFinder.of(...)` tạo finder cho plugin directory.
- `Configuration.resolve(...)` tạo graph mới có provider root.
- `defineModulesWithManyLoaders(...)` tạo child ModuleLayer và loader của provider.
- `ServiceLoader.load(layer, Extension.class)` yêu cầu discovery trong layer đó.
- `provider.getClass().getModule()` đối chiếu **Module object identity**, không chỉ tên String.
- `provider.getClass().getClassLoader()` đối chiếu đúng defining loader do layer gán.
- `Extension.class.isAssignableFrom(provider.getClass())` chứng minh provider dùng được interface runtime của host.
- Tạo thêm child layer `second` từ cùng configuration cho phép so **hai runtime Module objects** và loaders riêng, không đổi layer thứ nhất.

**Chú ý:** ví dụ chỉ có một provider, nên vòng lặp in đúng một nhóm dòng. Một hệ plugin thật có thể có nhiều providers; thứ tự discovery không nên được coi là priority trừ khi ứng dụng tự quy định chính sách chọn provider.

## 9. Lệnh biên dịch và thực thi

### 9.1. Linux/macOS

Từ thư mục `demo`, tạo output directories rồi dùng JDK 17+:

~~~sh
mkdir -p build/mods/plugin.api build/plugins/plugin.echo build/host

javac --release 17 \
  -d build/mods/plugin.api \
  src/plugin.api/module-info.java \
  src/plugin.api/plugin/api/Extension.java

javac --release 17 \
  --module-path build/mods \
  -d build/plugins/plugin.echo \
  src/plugin.echo/module-info.java \
  src/plugin.echo/plugin/echo/EchoExtension.java

javac --release 17 \
  --module-path build/mods \
  --add-modules plugin.api \
  -d build/host \
  src/host/HostMain.java

java \
  --module-path build/mods \
  --add-modules plugin.api \
  -cp build/host \
  HostMain
~~~

**Không** đưa `build/plugins` vào `--module-path` lúc launch. Nếu dùng khác biệt directory root, sửa đúng `ModuleFinder.of(...)` trong host code trước khi chạy.

### 9.2. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force build/mods/plugin.api | Out-Null
New-Item -ItemType Directory -Force build/plugins/plugin.echo | Out-Null
New-Item -ItemType Directory -Force build/host | Out-Null

javac --release 17 -d build/mods/plugin.api src/plugin.api/module-info.java src/plugin.api/plugin/api/Extension.java

javac --release 17 --module-path build/mods -d build/plugins/plugin.echo src/plugin.echo/module-info.java src/plugin.echo/plugin/echo/EchoExtension.java

javac --release 17 --module-path build/mods --add-modules plugin.api -d build/host src/host/HostMain.java

java --module-path build/mods --add-modules plugin.api -cp build/host HostMain
~~~

Đây là các lệnh một dòng tương thích Windows PowerShell. Thư mục chứa sources phải được tạo trước, đúng đường đã nêu ở mục 4. Không cần Maven, Gradle, external libraries hoặc platform-specific Java code.

### 9.3. Vì sao phải có `--add-modules plugin.api`?

Host chạy trên **classpath/unnamed module** nhưng muốn gọi `Extension.class` của named module API. Đặt `plugin.api` trên module path **chưa đủ nếu module chưa được resolve làm root**. `--add-modules plugin.api` buộc JVM resolve nó vào boot layer khi launch.

Khi compile host, cũng cần `--module-path build/mods --add-modules plugin.api` để `javac` nhìn thấy exported type trong named module API. Không đưa implementation JAR/directory vào host compile dependencies.

### 9.4. Stdout chính xác đã kiểm chứng

~~~text
apiInBoot=true
echoNotInBoot=true
pluginResolved=true
newLayerModule=true
parentApiVisible=true
loaderFindsParentApi=true
providerName=echo
providerResult=PLUGIN:hello
providerInChildModule=true
providerLoaderMatches=true
sharedApiIdentity=true
providerCount=1
separateLayerSeparateModule=true
separateLayerSeparateLoader=true
~~~

Ví dụ đã được kiểm chứng bằng cách compile ba source groups với `javac --release 17` và chạy `java` trên JDK có hỗ trợ Java 17. Không phụ thuộc hash của ClassLoader, đường tuyệt đối hoặc thứ tự filesystem.

### 9.5. Giải thích 14 dòng

| Dòng | Ý nghĩa |
|---|---|
| `apiInBoot=true` | Shared API được resolve vào boot layer |
| `echoNotInBoot=true` | Implementation module chưa được define trong boot layer |
| `pluginResolved=true` | Child configuration đã resolve provider module root |
| `newLayerModule=true` | Plugin Module object được định nghĩa trực tiếp trong child layer |
| `parentApiVisible=true` | Child layer thấy shared API từ parent layer |
| `loaderFindsParentApi=true` | `findLoader` của child có thể tra module ở parent layers |
| `providerName=echo` | `ServiceLoader` đã tạo instance plugin |
| `providerResult=PLUGIN:hello` | Plugin xử lý input qua shared API contract |
| `providerInChildModule=true` | Implementation class thuộc đúng runtime Module object của child layer |
| `providerLoaderMatches=true` | Implementation class do loader mà `layer.findLoader` trả về định nghĩa |
| `sharedApiIdentity=true` | Provider implement chính runtime service API type của host |
| `providerCount=1` | Chính xác một provider được tìm trong cấu hình demo |
| `separateLayerSeparateModule=true` | Hai sibling child layers có runtime Module objects khác nhau |
| `separateLayerSeparateLoader=true` | Với `WithManyLoaders`, hai child layers có plugin loaders riêng |

**Đọc chính xác:** `ModuleLayer.findLoader(name)` **có thể tìm ở parent layers**. Không được khẳng định nó chỉ tra các modules của child layer. Với bootstrap-defined module như `java.base`, kết quả loader có thể là `null` mà module vẫn hợp lệ.

## 10. Một loader, nhiều loaders và mapping tùy chỉnh

### 10.1. `defineModulesWithOneLoader`

~~~java
ModuleLayer child = boot.defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader());
~~~

Tất cả **modules được định nghĩa trong configuration mới** dùng **một ClassLoader mới**. Nếu plugin gồm nhiều named modules có thể chia sẻ một loader, đây là lựa chọn đơn giản. Tuy nhiên có thể gặp package overlap/loader constraints khiến tạo layer thất bại.

**Đừng hiểu** mọi module trong **boot parent layer** cũng bị chuyển vào loader mới; chỉ modules trong configuration mới được định nghĩa tại child layer.

### 10.2. `defineModulesWithManyLoaders`

~~~java
ModuleLayer child = boot.defineModulesWithManyLoaders(
        configuration,
        ClassLoader.getSystemClassLoader());
~~~

Mỗi module mới được định nghĩa bằng loader mới riêng. Khi có nhiều module implementation, điều này có thể giảm một số xung đột package names. Nhưng vẫn cần module readability/exports/opens và sự nhất quán type API.

Một provider module có thể tham chiếu types do parent API module định nghĩa; không cần tạo thêm bản API trong child.

### 10.3. `defineModules` với mapping function

Nếu framework cần chọn custom loader cho từng module:

~~~java
ModuleLayer child = boot.defineModules(
        configuration,
        moduleName -> loaderRegistry.get(moduleName));
~~~

Đây là **snippet kiến trúc**, chưa runnable độc lập; cần chuẩn bị `loaderRegistry` và đáp ứng đầy đủ module/package/delegation constraints của API. Nó không tự biến bất kỳ ClassLoader nào thành JPMS-aware loader hoàn chỉnh. Custom loaders phải triển khai đúng class/resource loading và tránh deadlocks/delegation cycles.

### 10.4. Instance và static overloads

Dùng `boot.defineModulesWithManyLoaders(cf, parentLoader)` trả `ModuleLayer` trực tiếp. Còn nhóm **static** methods:

~~~java
ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithManyLoaders(
                configuration,
                List.of(boot),
                ClassLoader.getSystemClassLoader());
ModuleLayer child = controller.layer();
~~~

Đây là snippet cần `java.util.List`, `configuration` và `boot`. Static variant cho phép danh sách parent layers và trả `Controller`, có thể dùng một số thao tác điều chỉnh readability/exports/opens qua controller theo hợp đồng. Đừng nhầm return type với instance method.

### 10.5. Chọn chiến lược theo bài toán

| Chiến lược | Mapping modules mới | Dùng khi | Chú ý |
|---|---|---|---|
| `WithOneLoader` | Nhiều modules chung một loader mới | Các modules phối hợp chặt, không xung đột package | Không giả định luôn hợp lệ với split packages |
| `WithManyLoaders` | Một loader mới/module mới | Muốn namespace tách theo module | Shared API vẫn cần thống nhất |
| `defineModules(cf, fn)` | Custom mapping | Container/plugin engine có loader policy riêng | Implementation và debugging phức tạp |
| Static `ModuleLayer.defineModules...` | Kèm `Controller` | Nhiều parents hoặc cần controller APIs | Return type khác instance method |

## 11. `resolve` và `resolveAndBind` trong kiến trúc plugin

### 11.1. `resolve` theo root + requires

Trong demo:

~~~java
Configuration configuration = boot.configuration().resolve(
        finder, ModuleFinder.of(), Set.of("plugin.echo"));
~~~

Ta **biết đích danh tên plugin module** và resolve nó thành root. `requires plugin.api` của plugin được đáp ứng từ boot parent config.

### 11.2. `resolveAndBind` khi dùng service binding

Một mô hình khác là host module khai báo `uses plugin.api.Extension;` và muốn resolver tìm các provider modules từ finder. Khi đó `resolveAndBind` có thể thêm provider modules vào graph dựa trên `provides` theo service binding rules.

Tuy nhiên:

- Không phải mọi JAR chứa provider đều được chọn trong mọi resolution.
- Root graph/module finder scope và module descriptors ảnh hưởng binding.
- Service binding có thể kéo thêm module dependencies hoặc providers so với roots ban đầu.
- `ServiceLoader.load(layer, service)` vẫn cần một **layer đã định nghĩa các provider modules**. Nó không tự giải quyết graph hay tải bất kỳ JAR trên disk ngoài layer chỉ nhờ service name.

Cần phân biệt **discovery của provider module lúc resolution** và **discovery/instantiation provider object lúc ServiceLoader iteration**.

### 11.3. ModuleFinder trước, ServiceLoader sau

~~~text
Plugin artifacts
   |
   | ModuleFinder
   v
Resolved Configuration
   |
   | ModuleLayer.defineModules...
   v
Runtime ModuleLayer + loaders
   |
   | ServiceLoader.load(layer, Service.class)
   v
Provider instances
~~~

Nếu chưa tạo layer, `ServiceLoader.load(layer, ...)` không có nơi để tìm provider runtime modules mới. Nếu plugin chưa được resolve, thay đổi TCCL cũng không làm `ModuleLayer` tự xuất hiện.

## 12. Chẩn đoán: module có trong folder nhưng ServiceLoader không thấy provider

### 12.1. Kiểm tra packaging/module descriptors

Một plugin modular JAR phải có hợp đồng phù hợp:

~~~text
plugin.echo.jar
  module-info.class
  plugin/echo/EchoExtension.class
~~~

Descriptor khai báo `provides plugin.api.Extension with plugin.echo.EchoExtension;`. Nếu quên `provides`, `ServiceLoader.load(layer, Extension.class)` không có provider declaration của named module để tìm, dù class implementation tồn tại.

Với **explicit named module**, không dựa vào mỗi `META-INF/services/plugin.api.Extension` như ở mô hình classpath. Java SPI cho classpath có provider configuration file riêng; với JPMS explicit module, descriptor `provides` mới là cách chuẩn công bố providers.

### 12.2. Kiểm tra runtime paths

Các path khác vai trò:

~~~text
--module-path build/mods
    => plugin.api ở boot configuration

ModuleFinder.of("build/plugins")
    => plugin.echo được phát hiện khi host chạy

-cp build/host
    => HostMain ở unnamed module
~~~

Nếu vô tình thêm `plugin.echo` vào boot roots, `echoNotInBoot` không còn true; nếu để `plugin.api` không được resolve trong boot, provider dependency resolution có thể thất bại.

Đừng đánh đồng compile-time module path, launcher module path, dynamic ModuleFinder roots và classpath.

### 12.3. Các nguyên nhân phổ biến

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| `FindException` lúc finder/resolve | Module artifact không hợp lệ, missing module hoặc duplicate names | Kiểm tra path/module-info.class, roots |
| `ResolutionException` | Xung đột module graph, packages, readability constraints | Đọc exception; sửa descriptors/dependencies |
| `LayerInstantiationException` | Không thể tạo loader/module mapping theo policy | Kiểm tra package overlap và loader constraints |
| `NoClassDefFoundError` khi provider được dùng | Runtime dependency không nằm trong graph/loader thích hợp | Kiểm tra `requires`/modules/launcher path |
| `ServiceConfigurationError` | Provider declaration/constructor/module/class identity không phù hợp | Kiểm tra `provides ... with` và shared API type |
| Không có provider dù layer tạo thành công | Quên `provides` hoặc plugin module không resolved | Kiểm tra `configuration.modules()`, `layer.modules()` |
| Provider class không tìm được bằng host loader | Implementation thuộc child module/loader | Dùng `ServiceLoader.load(layer,service)`; không `Class.forName` host |
| `ClassCastException` khi ép kiểu provider | Host/plugin dùng khác runtime API type | API từ parent, kiểm tra `Extension.class` identity |
| Module ở file nhưng `findModule` trống | ModuleFinder chưa resolve module làm root/dependency | Sửa root set/module finder |
| Plugin thêm rồi host không thấy | Layer hiện có là immutable về modules | Tạo child layer mới hoặc plugin manager generations |
| TCCL đổi mà `ServiceLoader.load(layer,...)` không thay | Overload theo layer dùng explicit layer | Chọn đúng overload/kiểm tra thực sự dùng layer nào |
| Runtime JAR version khác source | Đóng gói/deploy sai artifact | So module descriptor, bytecode và source version |
| Module đồng tên ở sibling layers | Runtime module identity khác nhau dù name giống | Giữ đúng layer reference và API bridge |

### 12.4. Phân biệt ClassLoader lỗi với JPMS access lỗi

Một module đã resolve và class load thành công vẫn có thể gặp:

- `IllegalAccessError` nếu Java access/module exports không phù hợp.
- `InaccessibleObjectException` khi deep reflection vào package chưa `opens`.
- `NoSuchMethodException` hoặc provider constructor/factory errors.
- `ClassCastException` nếu service API/runtime types chia đôi.
- `ServiceConfigurationError` khi provider không hợp lệ.

Đừng chỉ đổi `ClassLoader.getParent()` hoặc thêm `--add-opens` bừa bãi. Hãy phân loại lỗi theo bước **resolution**, **definition**, **loading**, **access** hay **instantiation**.

## 13. Module layer không phải plugin hot reload tự động

### 13.1. ModuleLayer không cho “append module” vào cùng instance

Khi tạo `ModuleLayer` xong, không có thao tác `layer.addModule(newJar)` để định nghĩa thêm module tùy ý vào chính layer cũ. Muốn triển khai plugin mới hoặc version mới, thường cần **Configuration/layer mới**, chọn parent(s)/module graph theo thiết kế.

Hai sibling layers có thể có named module cùng tên và implementation binary class names giống nhau nhưng là **những runtime Module/Class objects khác nhau**, như hai dòng cuối của demo.

### 13.2. Lifecycle references khiến loader không được GC

Một plugin manager có thể giữ:

- `ServiceLoader` và provider instances.
- `ModuleLayer`, `Module`, `ClassLoader`, `Class<?>`.
- `MethodHandle`/reflection caches.
- Threads, thread context class loaders, executors và thread locals.
- Listeners, callbacks, scheduled tasks hoặc static maps.

Tạo layer mới không đồng nghĩa layer cũ tự unload. Khi thay plugin, cần stop code cũ, dọn references và tài nguyên trước khi garbage collector có thể thu hồi classes/loaders khi đủ điều kiện.

### 13.3. API compatibility trong nhiều generations

Shared API module ở boot layer giúp host và providers dùng cùng `Extension.class`, nhưng không đảm bảo mọi version plugin tương thích:

- Thay method descriptor có thể phá binary compatibility.
- Plugin mới cần API revision khác, host chưa có sẽ gây lỗi resolution/linkage.
- Shared DTO/type xuất hiện ở method signatures cũng phải có identity nhất quán.
- Một child module có thể chứa private dependencies của riêng nó, nhưng nếu type private tràn qua shared API boundary thì ClassCastException/linkage problems có thể xuất hiện.

Production nên có version metadata, semantic compatibility policy và health/startup validation trước khi đưa plugin vào phục vụ requests.

### 13.4. Parent layer khác parent ClassLoader

Nhắc lại theo logic demo:

~~~text
ModuleLayer parent:
    Boot Layer
         |
         v
    Dynamic Plugin Layer

ClassLoader relationships (không vẽ thành 1:1):
    Application/system loader (tham số parentLoader)
         |
         v
    Loader mới cho plugin.echo
~~~

Boot layer có thể chứa modules do bootstrap, platform, application loaders định nghĩa. **Không có quy tắc “một layer = một loader”**; API `WithOneLoader` và `WithManyLoaders` chủ động chọn mapping khác nhau.

### 13.5. Ranh giới bảo mật

`ModuleLayer` giúp kiểm soát module resolution/readability/exports/opens, nhưng **không phải OS sandbox** để chạy plugin không tin cậy. Một provider trong cùng JVM vẫn có thể dùng public Java APIs, tiêu thụ CPU/RAM và truy cập những tài nguyên mà process được OS cho phép.

Với plugin untrusted cần process/container/VM isolation, least-privilege credentials, resource limits, network policy và IPC authorization. Trên JDK 24+, `SecurityManager` đã bị vô hiệu hóa theo JEP 486; không thiết kế sandbox mới dựa vào policy SecurityManager legacy.

## 14. Các sai lầm thường gặp cần tránh

1. **“Có module JAR trong folder là runtime đã có module.”** Sai: finder/artifact khác resolve/define.
2. **“`ModuleFinder` tạo ClassLoader.”** Sai: module finder chỉ cung cấp references.
3. **“`Configuration.resolve` đã instantiate provider.”** Sai: mới resolve graph.
4. **“Host phải import provider implementation.”** Sai: shared API + service loader được thiết kế để không cần.
5. **“Cứ đặt modular JAR trên `--module-path` là chắc chắn được resolve.”** Sai: cần roots/depends/binding.
6. **“Plugin và shared API nên cùng có một bản API module riêng.”** Sai cho demo: làm mất shared type identity.
7. **“Không `exports plugin.echo` thì `ServiceLoader` không dùng được provider.”** Sai trong mô hình `provides` explicit module hợp lệ.
8. **“`ServiceLoader.load(layer, Service.class)` dùng TCCL như overload một tham số.”** Sai: overload này dùng layer được truyền.
9. **“`ServiceLoader` tự tìm JAR chưa được resolve và define layer.”** Sai: phải có runtime modules trong layer.
10. **“Parent ModuleLayer là parent ClassLoader.”** Sai: hai quan hệ riêng.
11. **“`WithManyLoaders` tạo mỗi module ở boot layer một loader mới.”** Sai: chỉ modules configuration mới.
12. **“`WithOneLoader` chắc chắn hợp lệ cho mọi module graph.”** Sai: có thể gặp split-package/loader constraints.
13. **“`layer.modules()` liệt kê cả ancestor modules.”** Sai: chỉ modules trực tiếp trong layer.
14. **“`findLoader` của child không tìm được parent module.”** Sai: có thể tìm parent layers.
15. **“`findLoader` trả null luôn có nghĩa module thiếu.”** Sai: bootstrap loader là null; thiếu module gây IllegalArgumentException.
16. **“Hai layers cùng module name chứa cùng Module object.”** Sai: sibling layers có thể có identities khác.
17. **“Tạo layer mới là unload layer cũ.”** Sai: references/threads có thể giữ layer cũ.
18. **“Một loader riêng bảo đảm plugin không đọc host files.”** Sai: ClassLoader không phải sandbox.
19. **“`ServiceLoader` không thấy provider chỉ vì thiếu `META-INF/services`.”** Với explicit named module, kiểm tra `provides` trong `module-info.java`.
20. **“Có thể đổi module/loader mapping của layer đã tồn tại.”** Sai: cần tạo cấu hình và layer phù hợp mới.

## 15. Bài tập và câu hỏi tự kiểm tra

1. `ModuleFinder`, `Configuration`, `ModuleLayer` và `ServiceLoader` lần lượt chịu trách nhiệm gì?
2. Vì sao không cho `plugin.echo` vào launcher `--module-path` của demo?
3. `--add-modules plugin.api` làm gì với boot layer?
4. Vì sao `Extension.class` của host và plugin cần cùng runtime identity?
5. `module-info.java` của plugin phải khai báo `requires` và `provides` như thế nào?
6. Tại sao `plugin.echo` không bắt buộc `exports plugin.echo;` để làm service provider?
7. Host unnamed module khác gì một named module host về `uses`?
8. Vì sao `Configuration.resolve` không tự chạy static initializer của provider?
9. `resolveAndBind` bổ sung bước gì so với `resolve`?
10. Điều gì xảy ra nếu module folder không chứa `module-info.class` hợp lệ?
11. `defineModulesWithOneLoader` và `defineModulesWithManyLoaders` chọn loaders như thế nào?
12. Tham số `parentLoader` có cùng ý nghĩa với parent `ModuleLayer` không?
13. Vì sao `layer.findLoader("plugin.api")` trong demo vẫn trả được loader từ boot layer?
14. `layer.modules()` và `layer.findModule("plugin.api")` có phạm vi tìm giống nhau không?
15. Vì sao trong demo `plugin.echo` là named module ở child layer dù host chạy trên classpath?
16. Overload nào của `ServiceLoader` dùng layer explicit? Nó khác overload dựa TCCL ra sao?
17. `provider.getClass().getModule() == pluginModule` kiểm chứng điều gì?
18. `Extension.class.isAssignableFrom(provider.getClass())` giúp kiểm tra điều gì?
19. Tại sao cùng một `Configuration` có thể tạo hai child `ModuleLayer` runtime độc lập?
20. Nếu thêm plugin JAR vào filesystem sau khi layer đã tạo, làm sao đưa plugin mới vào runtime?
21. Khi nào nên dùng static `ModuleLayer.defineModules...` và `Controller`?
22. Nếu provider runtime thấy `NoClassDefFoundError`, cần kiểm tra graph/loader phần nào?
23. Nếu provider dùng private dependency versions khác host, làm sao tránh API type leak?
24. Vì sao cần stop plugin threads, dọn TCCL/caches và provider references trước khi unload?
25. Nếu plugin đến từ nguồn không tin cậy, ModuleLayer có đủ làm sandbox không?

**Tiêu chí hoàn thành:** tạo đúng cây source, compile API/provider/host, chạy đủ **14 dòng stdout** như tài liệu; giải thích vì sao plugin được tạo trong child layer còn API ở parent; dùng `ServiceLoader.load(layer, Extension.class)` thành công; phân biệt finder/resolve/define/service discovery và lỗi thường gặp.

## 16. Tài liệu chính thức

- [Java SE 21 — ModuleLayer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html): tạo layers, `findModule`, `findLoader`, parents, controller.
- [Java SE 21 — Configuration](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html): `resolve`, `resolveAndBind`, resolution graph.
- [Java SE 21 — ModuleFinder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleFinder.html): cách tìm modular JAR/exploded modules.
- [Java SE 21 — ServiceLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): service provider modules, `load(ModuleLayer, Class)`, declaration.
- [Java SE 21 — Module](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): runtime module identity, loader và layer.
- [Java SE 21 — Java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `--module-path`, `--add-modules`, `-cp`.
- [Java Language Specification §7.7 — Module Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7): module descriptors, `requires`/`exports`/`uses`/`provides`.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): kiến trúc JPMS.
- [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): giới hạn security architecture mới đối với untrusted code.

**Kết luận:** tạo ModuleLayer động là một quy trình tường minh: **ModuleFinder tìm plugin artifact → Configuration resolve module graph → ModuleLayer định nghĩa runtime named modules và loaders → ServiceLoader dùng layer để tạo provider instances**. Khi giữ shared API trong parent layer, host có thể gọi plugin mô đun hóa mà không compile phụ thuộc implementation, đồng thời giữ đúng module/classloader identity và chủ động quản lý vòng đời plugin.