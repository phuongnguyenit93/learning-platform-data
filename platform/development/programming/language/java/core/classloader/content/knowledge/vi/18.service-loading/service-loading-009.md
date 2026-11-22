# ServiceConfigurationError và provider không tương thích kiểu dịch vụ trong Java

## 1. Vấn đề: tên interface đúng nhưng ServiceLoader vẫn từ chối provider

`java.util.ServiceLoader` là cơ chế Java Service Provider Interface (**SPI**) dùng để tìm và tạo các implementation của một service contract. Bên sử dụng chọn một **`Class<S>` cụ thể** làm service type, ví dụ `Greeter.class`. Bên cung cấp khai báo implementation `PluginGreeter` và đăng ký nó bằng file trong `META-INF/services/` đối với ứng dụng chạy qua classpath, hoặc bằng `provides ... with ...` trong named module.

Một lỗi đáng chú ý là **`java.util.ServiceConfigurationError`**, thường kèm mô tả như *provider not a subtype*. Điều này xảy ra khi ServiceLoader tìm được provider nhưng provider không thỏa **quan hệ kiểu runtime** mà service type yêu cầu.

~~~text
ServiceLoader.load(api.Greeter.class, pluginLoader)
                        |
                        v
Đọc META-INF/services/api.Greeter
                        |
                        v
Tìm plugin.PluginGreeter bằng pluginLoader
                        |
                        v
Kiểm tra provider có tương thích api.Greeter?
          /                              \
         có                              không
          |                                |
     khởi tạo provider            ServiceConfigurationError
          |
   trả instance api.Greeter
~~~

Nguyên nhân có thể đơn giản: provider class **thật sự không implements service interface**. Nhưng trong hệ thống nhiều `ClassLoader`, nó có thể tinh vi hơn: provider **có khai báo implements đúng tên interface**, song interface của provider được loader plugin tự định nghĩa **khác Class runtime** so với interface của host.

**Quy tắc quyết định:** JVM xác định danh tính của class/interface bằng **(binary name, defining class loader)**. Vì thế hai interface có cùng `getName()` chưa chắc là một kiểu. ServiceLoader không chấp nhận provider chỉ vì văn bản `implements api.Greeter` hay `providerClass.getName()` trông hợp lý.

Bài này tập trung vào các lỗi cấu hình SPI, type identity, parent delegation, API dùng chung, lazy discovery, cách phân biệt provider sai với loader sai và một thí nghiệm Java 17+ có thể chạy độc lập để tái hiện lỗi rồi sửa đúng.

## 2. Các thành phần của Service Provider Interface

Một SPI thường có bốn thành phần:

1. **Service contract**: interface hoặc abstract class công khai mà ứng dụng muốn gọi.
2. **Provider implementation**: class cung cấp hành vi cho service ấy.
3. **Provider configuration/registration**: metadata giúp Java biết tên implementation.
4. **Consumer**: ứng dụng dùng `ServiceLoader<S>` để khám phá, khởi tạo và gọi provider.

Với classpath, ví dụ:

~~~text
api.Greeter                           <- interface chung
plugin.EnglishGreeter                 <- implementation
META-INF/services/api.Greeter        <- descriptor chứa:
   plugin.EnglishGreeter
~~~

**Tên file descriptor là binary name của service type**, không phải tên tùy ý: `META-INF/services/api.Greeter`. Nội dung tệp là **binary name của provider class**, mỗi provider một dòng. Tên có dấu chấm, không đổi dấu chấm thành `/` trong phần tên file service.

Một ứng dụng consumer điển hình:

~~~java
ServiceLoader<Greeter> loader = ServiceLoader.load(Greeter.class);
for (Greeter provider : loader) {
    System.out.println(provider.greet());
}
~~~

**Đoạn trên chỉ minh họa**; giả sử `Greeter` tồn tại và khai báo `greet()`. ServiceLoader là một **iterable lazy discovery mechanism**: việc gọi `load` không chứng minh mọi provider đều đã nạp hoặc tạo instance thành công. Những lỗi cấu hình có thể chỉ xuất hiện khi bắt đầu duyệt `iterator()` / `stream()` hoặc lấy provider.

## 3. Khi nào ném ServiceConfigurationError?

`ServiceConfigurationError` là một **`Error`**, không phải subclass của `Exception`. Nó biểu thị vấn đề khi tìm, xác thực hoặc tạo service providers.

Các nhóm nguyên nhân thường gặp:

| Nhóm | Ví dụ | Giai đoạn có thể lỗi |
| --- | --- | --- |
| Không đọc được descriptor | `META-INF/services/api.Greeter` bị lỗi I/O | Đọc cấu hình |
| Nội dung descriptor sai | Tên provider không hợp lệ, cấu hình sai cú pháp | Parse descriptor |
| Provider không tồn tại | File liệt kê `plugin.MissingGreeter` nhưng class không có | Load provider class |
| Provider không phải subtype | Class không implement đúng service type runtime | Kiểm tra type |
| Constructor không phù hợp | Classpath provider không có public no-arg constructor | Chọn cách tạo instance |
| Khởi tạo provider thất bại | Constructor/factory ném exception | Tạo provider |
| Cấu hình named module sai | Service type, `uses`/`provides` hoặc provider factory không hợp lệ | Resolution/discovery/instantiation |
| Loader/version conflict | Service API bị định nghĩa trùng, dependency không tương thích | Load/link/type check |

**Không nên coi mọi lỗi `ServiceConfigurationError` đều do cấu hình tệp descriptor.** Khi dịch vụ đã tìm thấy provider class nhưng không tương thích với chính service Class mà consumer truyền vào, nguyên nhân là **type identity** hoặc implementation sai.

Một số vấn đề sâu hơn như `LinkageError`, `ExceptionInInitializerError` hoặc lỗi quyền module có thể xuất hiện riêng hoặc được ServiceLoader báo thông qua `ServiceConfigurationError` tùy code path và Java version. Muốn chẩn đoán đúng phải xem **cause, message, service Class, provider Class và defining loaders**.

## 4. Provider “not a subtype” thực sự có nghĩa gì?

Giả sử consumer có:

~~~java
Class<?> service = api.Greeter.class;
Class<?> provider = plugin.PluginGreeter.class;

boolean compatible = service.isAssignableFrom(provider);
~~~

Đây là **đoạn minh họa**, với các class có thật trong dự án. Đối với **classpath provider dùng public no-arg constructor thông thường**, ServiceLoader yêu cầu provider class tương thích với service type; nếu không, nó từ chối cấu hình.

Hai trường hợp:

### Trường hợp A: Provider thực sự không implements API

~~~java
package plugin;

public class WrongGreeter {
    public String greet() {
        return "hello";
    }
}
~~~

`WrongGreeter` có một method tên `greet` nhưng **không khai báo implements `api.Greeter`**. Java không áp dụng structural typing cho service provider kiểu classpath này. Chỉ trùng method signature chưa đủ.

Nếu descriptor đăng ký `plugin.WrongGreeter` cho `api.Greeter`, việc provider không phải subtype là đúng.

### Trường hợp B: Provider implements cùng tên API nhưng từ loader khác

~~~text
Host ClassLoader             Plugin ClassLoader
        |                            |
        v                            v
api.Greeter [H]              api.Greeter [P]
        ^                            ^
        |                            |
Consumer uses H            plugin.PluginGreeter implements P

H.getName() = P.getName() = "api.Greeter"
H == P => false
H.isAssignableFrom(plugin.PluginGreeter) => false
~~~

Provider source có thể viết đúng `implements api.Greeter`, nhưng JVM giải quyết `api.Greeter` trong provider thành **P**, còn consumer yêu cầu **H**. Không có quan hệ subtype với H, ServiceLoader vẫn từ chối.

Hai `ClassLoader` khác nhau **không mặc nhiên** có lỗi: chỉ khi API Class bị **định nghĩa riêng**, không cùng được ủy quyền cho parent, mới phát sinh sự khác biệt identity này.

## 5. Tại sao ClassLoader và ServiceLoader liên quan trực tiếp?

Overload:

~~~java
ServiceLoader<Greeter> services =
        ServiceLoader.load(Greeter.class, pluginLoader);
~~~

Nó có hai đối tượng với vai trò khác nhau:

- **`Greeter.class`** là **service Class mà consumer nhận làm hợp đồng**. Class ấy có defining loader riêng, thường là host/common parent loader.
- **`pluginLoader`** là **loader sử dụng để khám phá và tải providers** theo hợp đồng API. Nó có thể load class provider, nhưng việc cung cấp loader khác **không biến service Class của host thành service Class của plugin**.

Dù provider loader tìm được tệp `META-INF/services/api.Greeter` và class `plugin.PluginGreeter`, nếu implementation resolve interface `api.Greeter` từ một classloader khác với host, type check vẫn thất bại.

**Thread Context ClassLoader** thường được dùng bởi overload `ServiceLoader.load(Greeter.class)`. Trong container/plugin, TCCL giúp provider discovery nhìn thấy đúng nơi, nhưng **đổi TCCL không tự nhập hai Class runtime đã bị định nghĩa riêng thành một**. Cần có chính sách chia sẻ service API đúng.

Cách tổ chức thường tốt:

~~~text
            Common / Host ClassLoader
                     |
                 api.Greeter
                 api.Request
                 api.Result
                     ^
             parent delegation
                     |
             Plugin ClassLoader
                     |
             plugin.PluginGreeter
             plugin.privateLib.*
             META-INF/services/api.Greeter
~~~

Implementation/private dependencies có thể thuộc loader riêng; **service interface và các kiểu contract dùng qua boundary** phải thống nhất.

## 6. Ví dụ Java 17+ hoàn chỉnh: tạo lỗi rồi sửa đúng

Thí nghiệm dùng **cùng một plugin bytecode** nhưng hai chế độ loader:

- `isolated`: plugin loader cố tình **child-first cho `api.*`**, tự định nghĩa bản interface trùng host. ServiceLoader báo `ServiceConfigurationError`.
- `shared`: plugin loader vẫn tự định nghĩa `plugin.*` nhưng **delegate `api.*` về parent**. Provider tương thích và service hoạt động.

Ví dụ không cần thư viện ngoài JDK 17+.

### 6.1. Cấu trúc source

Tạo một thư mục `spi-loader-demo` với các file:

~~~text
spi-loader-demo/
├── src-api/
│   └── api/
│       └── Greeter.java
├── src-plugin/
│   └── plugin/
│       └── PluginGreeter.java
└── src-host/
    └── HostMain.java
~~~

Sau biên dịch sẽ có:

~~~text
host-classes/
├── HostMain.class
├── HostMain$PluginLoader.class
└── api/
    └── Greeter.class

plugin-classes/
├── api/
│   └── Greeter.class
├── plugin/
│   └── PluginGreeter.class
└── META-INF/
    └── services/
        └── api.Greeter
~~~

Việc `api/Greeter.class` xuất hiện trong **hai thư mục** là có chủ ý. Thí nghiệm chỉ đưa `host-classes` lên **application classpath**; plugin-classes được giao cho custom loader qua URL. Descriptor chỉ đặt dưới plugin-classes.

### 6.2. File src-api/api/Greeter.java

~~~java
package api;

public interface Greeter {
    String greet();
}
~~~

### 6.3. File src-plugin/plugin/PluginGreeter.java

~~~java
package plugin;

import api.Greeter;

public final class PluginGreeter implements Greeter {
    @Override
    public String greet() {
        return "hello from plugin";
    }
}
~~~

Class public có constructor mặc định public; đủ cho **classpath-based ServiceLoader provider** bình thường.

### 6.4. File src-host/HostMain.java

~~~java
import api.Greeter;

import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;

public class HostMain {
    static final class PluginLoader extends URLClassLoader {
        private final boolean duplicateApi;

        PluginLoader(Path pluginClasses, boolean duplicateApi)
                throws IOException {
            super(
                    new URL[] { pluginClasses.toUri().toURL() },
                    HostMain.class.getClassLoader()
            );
            this.duplicateApi = duplicateApi;
        }

        private boolean localFirst(String name) {
            return name.startsWith("plugin.")
                    || (duplicateApi && name.startsWith("api."));
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!localFirst(name)) {
                return super.loadClass(name, resolve);
            }
            synchronized (getClassLoadingLock(name)) {
                Class<?> result = findLoadedClass(name);
                if (result == null) {
                    result = findClass(name);
                }
                if (resolve) {
                    resolveClass(result);
                }
                return result;
            }
        }
    }

    private static void runCase(
            String label, Path pluginDir, boolean duplicateApi)
            throws IOException, ClassNotFoundException {

        try (PluginLoader loader = new PluginLoader(
                pluginDir, duplicateApi)) {

            Class<?> pluginApi = loader.loadClass("api.Greeter");
            System.out.println(label + " same API Class: "
                    + (pluginApi == Greeter.class));

            ServiceLoader<Greeter> services =
                    ServiceLoader.load(Greeter.class, loader);

            try {
                Greeter provider = services.iterator().next();
                System.out.println(label + " provider: "
                        + provider.greet());
            } catch (ServiceConfigurationError failure) {
                System.out.println(label + " error: "
                        + failure.getClass().getSimpleName());
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: HostMain <plugin-classes-directory>");
        }

        Path pluginDir = Path.of(args[0]).toAbsolutePath();
        runCase("isolated", pluginDir, true);
        runCase("shared", pluginDir, false);
    }
}
~~~

### 6.5. Descriptor META-INF/services/api.Greeter

File này **không có phần mở rộng** `.txt`. Tên tệp là `api.Greeter`, nằm trong `META-INF/services` tính từ **gốc classpath của plugin loader**.

Nội dung file, một dòng:

~~~text
plugin.PluginGreeter
~~~

Đặt đúng tại:

~~~text
plugin-classes/META-INF/services/api.Greeter
~~~

Đừng tạo `plugin-classes/META-INF/services/api/Greeter`. Descriptor name giữ **dấu chấm** trong binary service name.

### 6.6. Biên dịch bằng JDK 17+

Tại thư mục `spi-loader-demo`:

~~~bash
javac --release 17 -d host-classes src-api/api/Greeter.java src-host/HostMain.java
javac --release 17 -d plugin-classes src-api/api/Greeter.java src-plugin/plugin/PluginGreeter.java
~~~

Sau khi compile, **tạo descriptor theo mục 6.5**. Nếu dùng Linux/macOS/bash, có thể thực hiện:

~~~bash
mkdir -p plugin-classes/META-INF/services
printf 'plugin.PluginGreeter\n' > plugin-classes/META-INF/services/api.Greeter
java -cp host-classes HostMain plugin-classes
~~~

Nếu dùng Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force plugin-classes/META-INF/services | Out-Null
[System.IO.File]::WriteAllText(
    (Join-Path (Get-Location) 'plugin-classes/META-INF/services/api.Greeter'),
    "plugin.PluginGreeter" + [Environment]::NewLine,
    [System.Text.UTF8Encoding]::new($false)
)
java -cp host-classes HostMain plugin-classes
~~~

Lưu ý Java 17, UTF-8 là encoding của các provider-configuration files. PowerShell 5.1 không hỗ trợ cú pháp `::new(...)` trên mọi cấu hình? Nếu PowerShell cụ thể không hỗ trợ, có thể tạo file này thủ công bằng editor và lưu UTF-8; đây chỉ là bước chuẩn bị resource, không thay đổi Java code.

### 6.7. Stdout chính xác

Với các tệp như trên và application classpath chỉ có `host-classes`, kết quả:

~~~text
isolated same API Class: false
isolated error: ServiceConfigurationError
shared same API Class: true
shared provider: hello from plugin
~~~

### 6.8. Phân tích kết quả

**Ở chế độ isolated:**

1. `PluginLoader.loadClass("api.Greeter")` chọn bản `api.Greeter` dưới `plugin-classes` vì `duplicateApi=true`.
2. `HostMain` biên dịch với bản `api.Greeter` nằm dưới `host-classes`, thuộc host application loader.
3. Cả hai tên đều là `api.Greeter` nhưng `Class<?>` khác, vì defining loader khác.
4. `plugin.PluginGreeter` được plugin loader định nghĩa và resolve `implements api.Greeter` về bản API của plugin.
5. `ServiceLoader.load(Greeter.class, loader)` giữ **service Class của host**, không đổi sang service Class của plugin. Nó tìm descriptor và provider rồi phát hiện implementation **không phải subtype của host service Class**, nên báo `ServiceConfigurationError`.
6. Code in **tên Error type**, không in message vì nội dung thông báo có thể khác theo JDK.

**Ở chế độ shared:**

1. `PluginLoader` vẫn load `plugin.PluginGreeter` local-first.
2. Nhưng `api.Greeter` không bị chọn local-first; loader ủy quyền cho parent và nhận **đúng một Class của host**.
3. Provider implement host API, nên subtype check thành công.
4. ServiceLoader tạo provider qua public no-arg constructor và gọi `greet()`, in `hello from plugin`.

Sự thay đổi nằm ở **loader policy cho package `api.*`**, không phải sửa tên interface, constructor, descriptor hay plugin method. Đây là phương án sửa có hệ thống cho lỗi duplicated service API.

## 7. Tại sao phải kiểm tra “cùng Class” thay vì “cùng tên”?

Một chẩn đoán thường thấy:

~~~java
Class<?> expected = Greeter.class;
Class<?> actual = pluginLoader.loadClass("api.Greeter");

System.out.println(expected.getName());
System.out.println(actual.getName());
~~~

**Mã minh họa**: hai dòng có thể in `api.Greeter` như nhau và khiến người đọc tưởng loader không lỗi.

Cần kiểm tra thêm:

~~~java
System.out.println(expected == actual);
System.out.println(expected.getClassLoader());
System.out.println(actual.getClassLoader());
~~~

Nếu `expected == actual` là false, cần xem **parent chain, child-first rules, API JAR duplicates**. Một provider implements đúng interface **của nó** nhưng chưa chắc implement đúng interface **của consumer**.

Với provider class đã tải được:

~~~java
boolean assignable = Greeter.class.isAssignableFrom(providerClass);
~~~

Nếu false, thử hỏi `providerClass.getInterfaces()` và defining loaders của những interfaces ấy. Đừng chỉ so tên chuỗi của interfaces.

## 8. “Not a subtype” không phải lúc nào cũng do nạp trùng API

Hai nhóm nguyên nhân phổ biến:

### Provider code khai báo sai

Descriptor ghi `plugin.WrongGreeter`, nhưng class đó không implement `api.Greeter`, hoặc compile nhầm version interface, hoặc class là adapter chưa được khai báo implements. Cần sửa provider class đúng contract.

### API bị định nghĩa lại

`PluginGreeter implements api.Greeter` trong source, nhưng `api.Greeter` trong bytecode được plugin class loader giải quyết tới một runtime Class khác. Cần sửa **loader ownership** hoặc cách đóng gói, không phải thêm `implements` lần nữa.

Một quy trình phân loại:

| Quan sát | Kết luận gợi ý | Bước sửa |
| --- | --- | --- |
| Provider không khai báo implements service | Sai class/descriptor | Sửa class hoặc descriptor |
| Provider khai báo implements, service/interface Class khác | Duplicate API via loaders | Share API ở parent |
| `isAssignableFrom` đúng, tạo instance lỗi | Constructor/factory/access/init | Xem constructor và cause |
| Class không tìm thấy | Lookup/packaging | Xem classpath/JAR và loader |
| Descriptor không tìm được | Provider discovery path | Kiểm tra `META-INF/services` |
| Lỗi xảy ra khi module configuration tạo | JPMS descriptor/graph | Xem `uses`, `provides` và module readability |
| ServiceLoader liệt kê provider nhưng cast fail nơi khác | Boundary/API identity | Kiểm tra tất cả DTO/exception/annotation contract |

## 9. Provider-configuration file: những yêu cầu dễ sai

Trong classpath-based SPI, tệp `META-INF/services/<binary service name>` có các quy tắc:

- Tên tệp khớp **binary service name**, ví dụ `META-INF/services/api.Greeter`.
- Tên provider bên trong là **fully qualified binary class name**, không phải filesystem path.
- Mỗi dòng khai báo một provider; dấu `#` mở đầu comment, khoảng trắng được xử lý theo quy tắc định dạng.
- Cấu hình nên được lưu UTF-8.
- Provider class thông thường phải là public concrete class có **public zero-argument constructor** khi classpath registration được dùng.
- Một provider xuất hiện trùng tên trong các cấu hình thường không tạo ra hai provider riêng của cùng implementation theo quy tắc deduplication, nhưng **đừng dựa vào trật tự khai báo** để chọn provider quan trọng.
- Resource không đọc được, encoding/syntax sai, class không tìm thấy, constructor không hợp lệ hoặc provider không đúng subtype đều có thể gây `ServiceConfigurationError` khi duyệt.

Lệnh hữu ích:

~~~bash
jar --list --file plugin.jar
~~~

Khi `plugin.jar` tồn tại, kiểm tra có `META-INF/services/api.Greeter` và `plugin/PluginGreeter.class` hay không. Đây mới chỉ là **xác minh packaging**, chưa bảo đảm provider Class có cùng service type với host.

Một JAR có cả `api/Greeter.class` và implementation có thể hoạt động bình thường nếu loader luôn **parent-first cho API package**. Chính sách load mới quyết định bản API đó có thực sự bị define lần hai hay không.

## 10. Lazy discovery: tại sao gọi load() chưa báo lỗi?

Ví dụ:

~~~java
ServiceLoader<Greeter> services =
        ServiceLoader.load(Greeter.class, loader);

System.out.println("created ServiceLoader");

for (Greeter provider : services) {
    System.out.println(provider.greet());
}
~~~

Đây là **mã minh họa** (có service type và loader phù hợp). Câu lệnh khởi tạo `ServiceLoader` thường chưa tạo tất cả providers. Khi chương trình bắt đầu iterate, Java mới đọc cấu hình, xác thực provider class, khởi tạo instance theo yêu cầu.

Vì vậy:

- Test chỉ gọi `ServiceLoader.load(...)` rồi kết luận SPI hợp lệ là chưa đủ.
- Có thể provider thứ nhất hoạt động, provider thứ hai bị lỗi khi tiếp tục iterate.
- `ServiceLoader.stream()` cung cấp stream của `ServiceLoader.Provider<S>`; **lấy danh sách provider types** và **gọi `Provider.get()`** không hoàn toàn cùng điểm tạo instance.
- Đừng dựa vào thứ tự provider khám phá trong mọi classloader/module environment để báo “provider nào sẽ được load trước” nếu API không cam kết thứ tự cố định.
- `ServiceLoader.reload()` xóa cache nội bộ và khiến discovery lại trên những lần duyệt sau; nó **không đổi runtime Class đã được loader định nghĩa** hay tự sửa lỗi API duplication.

### Lưu ý khi catch ServiceConfigurationError

Vì `ServiceConfigurationError extends Error`, đoạn:

~~~java
try {
    for (Greeter g : services) {
        g.greet();
    }
} catch (Exception e) {
    System.out.println("caught");
}
~~~

**Không phải mẫu bắt lỗi cấu hình đúng**: `catch (Exception)` không bắt `ServiceConfigurationError`.

Nếu muốn chẩn đoán/disable một provider không hợp lệ tại boundary:

~~~java
try {
    Greeter provider = services.iterator().next();
} catch (java.util.ServiceConfigurationError error) {
    System.err.println("SPI discovery failed: "
            + error.getMessage());
}
~~~

Đây là snippet minh họa. Có thể bắt đúng loại Error này ở **ranh giới vận hành plugin** để ghi log/chuyển trạng thái, nhưng không nên bắt mọi `Error` hoặc mọi `Throwable` rồi tiếp tục như không có lỗi: những lỗi VM/linkage nghiêm trọng cần xử lý khác.

## 11. Named modules: khác biệt với classpath descriptor

Từ Java 9, provider đăng ký trong **named module** thường dùng `module-info.java` thay cho descriptor classpath.

Ví dụ module API:

~~~java
module greeter.api {
    exports api;
}
~~~

Module consumer:

~~~java
module greeter.app {
    requires greeter.api;
    uses api.Greeter;
}
~~~

Module implementation:

~~~java
module greeter.impl {
    requires greeter.api;
    provides api.Greeter with plugin.PluginGreeter;
}
~~~

**Ba descriptors này chỉ minh họa sơ đồ module**, chưa phải dự án runnable hoàn chỉnh; để chạy còn cần Java sources, module paths và module resolution hợp lệ.

Các điểm quan trọng:

- `uses api.Greeter` khai báo service dependency trong named consumer module.
- `provides api.Greeter with plugin.PluginGreeter` khai báo provider của service.
- Provider module phải dùng **cùng service contract** theo module resolution, không tự ship một class `api.Greeter` khác trong module implementation.
- Trong named modules, một provider có thể sử dụng **public static provider method** có tên `provider` (theo quy tắc `ServiceLoader`) trả service implementation; vì thế không được áp dụng máy móc điều kiện “provider class phải implements service” cho **mọi kiểu provider factory trong named module**.
- Khi dùng direct provider class thay vì provider method, provider phải phù hợp service type và hình thức construction được JDK chấp nhận.
- `ServiceLoader.load(ModuleLayer layer, Class<S> service)` tìm providers trong layer và các parent layers theo hợp đồng API, có semantics khác với chỉ quét các tệp descriptor từ một URLClassLoader.
- Module readability, module roots, package exports/opens và service binding có thể gây những lỗi **trước khi ServiceLoader tạo provider**, không nên gộp mọi lỗi thành “not a subtype”.

**Sự khác nhau quan trọng:** lớp provider chứa trong named module có thể hợp lệ nhờ một `provider()` factory trả service type, ngay cả nếu chính provider class không subtype trực tiếp. Ở ví dụ classpath bên trên, provider implementation thông thường phải subtype và có public no-arg constructor.

## 12. ModuleLayer, service Class identity và plugin architecture

Một hệ thống plugin có thể tự tạo `ModuleLayer` cho từng plugin. Khi làm vậy, cần đảm bảo module chứa shared service API thuộc **parent/common layer** và được các plugin implementations tham chiếu nhất quán.

Sơ đồ đề xuất:

~~~text
Boot / Parent ModuleLayer
  greeter.api
    api.Greeter
       ^
       |
Plugin ModuleLayer A
  greeter.impl.a
    provides api.Greeter

Plugin ModuleLayer B
  greeter.impl.b
    provides api.Greeter
~~~

Nếu mỗi layer tự định nghĩa `api.Greeter` từ bản copy API module bằng class loader khác, host không thể coi hai Class ấy là cùng contract chỉ vì module/binary names giống nhau.

Một số lỗi JPMS khác cần tách riêng:

| Lỗi | Nhóm điều tra |
| --- | --- |
| `FindException` | Không tìm thấy named module cần thiết |
| `ResolutionException` | Module graph/readability/export conflict |
| `LayerInstantiationException` | Mapping module tới loader, overlapping packages hoặc layer conditions |
| `IllegalAccessError` / `InaccessibleObjectException` | Module access/exports/opens |
| `ServiceConfigurationError` | Provider discovery/configuration/subtype/construction |
| `ClassCastException` | Typed cast qua runtime Class không tương thích |

Chuyển sang named modules **không tự sửa** một API class bị duplication giữa loaders. Cần thiết kế ownership của service Class tại boundary.

## 13. Thread Context ClassLoader (TCCL): cần nhưng không đủ

Nhiều thư viện gọi:

~~~java
ServiceLoader<Greeter> services =
        ServiceLoader.load(Greeter.class);
~~~

Overload này thường sử dụng `Thread.currentThread().getContextClassLoader()` để chọn phạm vi tìm providers. Khi host và plugin có nhiều loader, TCCL có thể đang trỏ về một loader không nhìn thấy descriptor/provider.

Một pattern ở host:

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    ServiceLoader<Greeter> services =
            ServiceLoader.load(Greeter.class);
    // Duyệt service providers trong phạm vi tác vụ plugin.
} finally {
    thread.setContextClassLoader(previous);
}
~~~

Đây là **đoạn minh họa**, `pluginLoader` và `Greeter` cần có thật. Phải restore TCCL để tránh ảnh hưởng công việc khác trên cùng thread.

TCCL giúp API tìm provider metadata/classes ở phạm vi loader muốn chọn, nhưng **không thay đổi defining loader của `Greeter.class` mà caller đang giữ**. Nếu plugin class implement bản `api.Greeter` khác runtime Class, ServiceLoader vẫn từ chối.

Với ứng dụng đa luồng, async tasks hoặc executors, TCCL có thể không được truyền qua thread boundary theo ý muốn; ưu tiên overload nhận loader tường minh khi bạn quản lý rõ service discovery context.

## 14. Những lỗi cấu hình/packaging phổ biến

### Descriptor bị đặt sai thư mục

Sai:

~~~text
src/META-INF/services/api.Greeter
app/META-INF/services/api/Greeter
META-INF/services/plugin.PluginGreeter
~~~

Đúng cho service `api.Greeter`:

~~~text
META-INF/services/api.Greeter
~~~

Resource phải nằm ở **classpath/JAR root** mà loader dùng khi tìm `META-INF/services/...`.

### Nội dung ghi class không tồn tại

~~~text
plugin.GreeterProviderV2
~~~

Nếu artifact chỉ chứa `plugin.PluginGreeter`, ServiceLoader có thể báo provider không được tìm thấy. Đây là lỗi lookup, không phải type identity.

### Provider không có constructor/factory phù hợp

Một class chỉ có constructor yêu cầu tham số mà không có no-arg constructor có thể không được ServiceLoader classpath tạo như một provider class bình thường. Với named modules có khả năng dùng provider factory theo hợp đồng riêng.

### API dependency bị đóng hai lần

Plugin fat JAR copy `api.Greeter`, child-first loader define bản plugin. Đây là nguồn của lỗi “not a subtype” dù code Java nhìn đúng.

### Sai version API

Provider được biên dịch với phiên bản `Greeter` có method signature khác, có thể gây `NoSuchMethodError`, `AbstractMethodError` hoặc những lỗi linkage khác, không nhất thiết chỉ `ServiceConfigurationError`. Kiểm tra dependency tree, module graph, classpath/JAR thực tế.

### Nhiều providers cùng service

Nếu có nhiều tệp descriptor trùng tên, ServiceLoader có thể phát hiện nhiều providers. Một provider sai làm iteration bị gián đoạn; không nên chỉ test provider đầu tiên. Khi cần thứ tự ưu tiên, hãy chọn theo metadata hoặc logic ứng dụng rõ ràng chứ không dựa mù quáng vào thứ tự JAR của môi trường.

## 15. Chẩn đoán ServiceConfigurationError có hệ thống

Khi thấy lỗi SPI:

1. **Đọc nguyên stack trace và cause**: ghi lại service name, provider name, class loaders và message; không chỉ giữ dòng `ServiceConfigurationError`.
2. **Xác nhận service Class của host**: `Greeter.class.getName()`, `getClassLoader()`, `getModule()`.
3. **Xác nhận provider descriptor**: đường `META-INF/services/api.Greeter` đúng? Nội dung có đúng binary name?
4. **Xác nhận provider class có được tìm không** bằng đúng loader mà ServiceLoader dùng.
5. **So service identity**: `hostService == pluginLoader.loadClass("api.Greeter")` trong tình huống API package tương ứng.
6. **Kiểm tra assignability**: `hostService.isAssignableFrom(providerClass)` với đúng Class của provider.
7. **Quan sát provider interfaces**: `providerClass.getInterfaces()` và defining loader của từng interface.
8. **Kiểm tra construction**: public concrete class/no-arg constructor đối với classpath provider thông thường, hoặc đúng provider factory trong named module.
9. **Kiểm tra dependency scope**: plugin có đóng kèm API copy trong fat JAR? Maven/Gradle đã cấu hình provided/compileOnly khi host cung cấp API chưa?
10. **Kiểm tra loader policy**: shared `api.*` có parent-first? Private `plugin.*` có đúng loader riêng?
11. **Kiểm tra TCCL và module layer**: API được gọi với loader nào, service đã được resolved trong module graph chưa?
12. **Sau sửa, duyệt toàn bộ providers** trong môi trường deploy thật, không chỉ gọi `ServiceLoader.load`.

Một helper:

~~~java
static void describe(String label, Class<?> type) {
    System.out.println(label + " name=" + type.getName());
    System.out.println(label + " loader=" + type.getClassLoader());
    System.out.println(label + " module=" + type.getModule());
}
~~~

Đây là **đoạn minh họa trong một Java class**, không phải file chạy độc lập.

Trong HotSpot/OpenJDK, có thể bật class loading logs:

~~~bash
java -Xlog:class+load=info -cp host-classes HostMain plugin-classes
~~~

Stdout/stderr logging của JVM khác nhau theo môi trường, nên không công bố một transcript cố định. Quan sát log chỉ hỗ trợ xác định classfile origin; **so trực tiếp Class runtime/defining loader** vẫn là bằng chứng tốt nhất về type identity.

## 16. Kiến trúc tránh duplication và bảo vệ boundary

Một thiết kế plugin đáng tin nên tách rõ:

| Thành phần | Nơi định nghĩa nên chọn |
| --- | --- |
| Service interface `api.Greeter` | Shared parent loader/module |
| Service DTO và callback types | Shared parent loader/module |
| Annotation host cần scan | Shared parent loader/module |
| Typed exception contract | Shared parent loader/module |
| Provider implementation | Plugin loader/module |
| Private third-party library | Plugin loader nếu cần cô lập |
| Java core types | Bootstrap/platform delegation |

Một số nguyên tắc:

- Không child-first bừa bãi cho mọi package có trong fat JAR.
- Không relocate/shade service API cần chia sẻ mà không có adapter contract rõ.
- Dùng Maven scope `provided` hoặc Gradle `compileOnly` khi host **thực sự cung cấp** shared API lúc chạy; cấu hình build cần phù hợp deployment, không phải quy tắc áp dụng cho mọi project.
- Kiểm tra chính artifact build: descriptor có được copy vào JAR? Provider class có được giữ sau shading/minification? Tên resource có bị đổi sai không?
- Tách lỗi discovery thành **missing provider**, **invalid descriptor**, **type mismatch**, **constructor/factory failure**, **module access/linkage** để log/hỗ trợ vận hành.
- Nếu provider do bên không tin cậy cung cấp, `ServiceLoader`/`ClassLoader` không phải sandbox quyền file/network. Cần bảo vệ ở process/OS/container boundary theo threat model.
- Một provider có thể có static initializer gây side effects hoặc lỗi khi khởi tạo; cần cân nhắc lifecycle, caching, cleanup và isolation khi plugin có thể reload.

## 17. Các tình huống biên cần hiểu rõ

### Không có provider nào được tìm

Một ServiceLoader hợp lệ có thể trả iterator rỗng khi không có provider. Gọi `iterator().next()` trên iterator rỗng dẫn tới `NoSuchElementException`, **không phải** `ServiceConfigurationError` chỉ vì không có provider.

Trong ví dụ runnable ở mục 6, file descriptor có sẵn provider nên tình huống này không xảy ra; code production nên kiểm tra `hasNext()` hoặc duyệt `for-each`.

### Descriptor liệt kê class hợp lệ nhưng không subtype

Đây là lỗi cấu hình provider đúng nghĩa. Đừng “sửa” bằng cách cast qua `Object` hoặc so tên interfaces. Cần sửa implementation hoặc loader ownership.

### Provider factory trong named module

Một public static `provider()` method theo quy tắc ServiceLoader có thể trả service type, nên class chứa factory **không nhất thiết** implement trực tiếp service interface. Đừng áp bảng subtype dành cho classpath constructor providers lên mọi named-module factory.

### Hot reload không tự thay service Class

`ServiceLoader.reload()` bỏ cache khám phá/instance của chính ServiceLoader, nhưng các Class đã được định nghĩa bởi loader cũ không bị viết lại. Để dùng plugin bytes mới với cùng tên, thường cần loader mới và thiết kế chuyển giao lifecycle; giữ API chung ở parent để tránh cast errors giữa phiên bản plugin.

### Exception từ provider implementation

Exception được ném từ `provider.greet()` là lỗi lúc **gọi nghiệp vụ sau khi provider được tạo**, không tự động trở thành `ServiceConfigurationError`. Ngược lại lỗi xảy ra trong constructor/provider factory có thể bị ServiceLoader wrap/báo là configuration error.

### ServiceLoader instance không thread-safe

Theo Javadoc, `ServiceLoader` không được bảo đảm an toàn cho các thao tác concurrent tùy ý. Nếu hệ thống muốn dùng chung instance trong nhiều threads, cần kiểm soát synchronization/caching theo thiết kế. Đừng đồng thời `reload()` và iterate trên cùng instance rồi kỳ vọng behavior ổn định.

## 18. Tự kiểm tra kiến thức

**Câu 1. `ServiceConfigurationError` có phải subtype của `Exception` không?**  
Không; nó kế thừa `Error`.

**Câu 2. Vì sao một class có method `greet()` không tự là provider của `Greeter`?**  
Java cần subtype compatibility đối với provider classpath thông thường, không dựa vào structural method matching.

**Câu 3. Plugin source viết `implements api.Greeter`. Host vẫn báo not a subtype. Cần kiểm tra gì?**  
So `Greeter.class` ở host với `api.Greeter` do plugin loader resolve; kiểm tra defining loaders và child-first policy.

**Câu 4. Hai ClassLoader khác nhau có nhất thiết tạo hai Class service khác nhau không?**  
Không. Parent delegation có thể dùng một Class do common parent định nghĩa.

**Câu 5. File provider descriptor cho service `api.Greeter` tên gì?**  
`META-INF/services/api.Greeter`.

**Câu 6. Nội dung descriptor ghi đường dẫn `plugin/PluginGreeter.class` có đúng không?**  
Không. Nó phải ghi **binary provider name**, ví dụ `plugin.PluginGreeter`.

**Câu 7. `ServiceLoader.load(...)` trả về mà không lỗi đã chứng minh provider hợp lệ chưa?**  
Chưa. Discovery và instantiation diễn ra lazy khi duyệt.

**Câu 8. `Class.isAssignableFrom` trả false khi service name giống nhau vì sao?**  
Provider có thể implement một runtime service Class khác loader hoặc thật sự không implement hợp đồng.

**Câu 9. `ServiceLoader.reload()` có tự làm hai Class cùng tên trở thành một không?**  
Không. Nó chỉ làm mới cache nội bộ của ServiceLoader.

**Câu 10. Named-module provider factory có luôn đòi class chứa factory implements service interface không?**  
Không. Provider method hợp lệ có thể trả service type; quy tắc khác classpath provider-constructor thông thường.

**Câu 11. Thay TCCL sang plugin loader có chữa API duplication không?**  
Không. TCCL giúp lookup, không đổi type identity đã được define.

**Câu 12. Nên đặt interface, DTO, annotation, exception dùng chung ở đâu?**  
Ở common parent loader/module mà cả host và plugin tham chiếu thống nhất.

## 19. Tài liệu chính thức

- **Java SE 17 — ServiceLoader API:** classpath providers, `META-INF/services`, provider factories, lazy discovery, `reload`, `ServiceConfigurationError` và module semantics: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- **Java SE 17 — ServiceConfigurationError:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceConfigurationError.html
- **Java SE 17 — ClassLoader:** delegation, `loadClass`, `findClass` và loader identity: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17 — Class:** `isAssignableFrom`, `getClassLoader`, `getModule`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java SE 17 — ModuleLayer:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- **JVMS Java 17 §5.3 — Creation and Loading:** runtime identity và defining loader: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- **JLS Java 17 §12.2 — Loading of Classes and Interfaces:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2
