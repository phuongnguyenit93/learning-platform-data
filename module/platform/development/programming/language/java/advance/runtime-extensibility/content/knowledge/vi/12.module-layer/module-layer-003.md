# Tạo ModuleLayer với defineModulesWithManyLoaders hoặc ánh xạ ClassLoader tùy chỉnh

Khi một ứng dụng Java cần nạp thêm các **named module** sau khi JVM đã khởi động, Java Platform Module System (JPMS) cho phép ứng dụng tạo **ModuleLayer** mới từ cấu hình module đã được giải quyết. Lựa chọn quan trọng là **mỗi module sẽ được ClassLoader nào định nghĩa**. Java cung cấp cách tiện lợi là defineModulesWithManyLoaders để tạo loader riêng cho mỗi module, đồng thời cho phép tự ánh xạ tên module → loader bằng defineModules.

Bài này giải thích các API trên Java 17+, trình tự ModuleFinder → Configuration → ModuleLayer, sự khác nhau giữa ánh xạ tự động và tùy chỉnh, một lab chạy được với hai modular JAR, các giới hạn về readability, exports, resource, class identity và cách xử lý vòng đời của plugin.

## 1. Một layer là gì, và nó không phải là gì?

**ModuleLayer** là một tập các Module object được JVM định nghĩa từ đồ thị resolved module trong một Configuration, cùng quan hệ với một hoặc nhiều parent layer. Một layer có thể được tạo lúc runtime để host nhìn thấy plugin mới mà không đưa tất cả plugin lên module path của tiến trình khi khởi động.

Cần phân biệt các đối tượng:

| Đối tượng | Chức năng | Điều không tự làm |
| --- | --- | --- |
| ModuleFinder | Tìm mô tả module trong JAR/JMOD/thư mục module | Không nạp hay khởi tạo class |
| Configuration | Giải quyết đồ thị requires, xác định tập resolved module | Chưa tạo Module object hay loader tại runtime |
| ModuleLayer | Định nghĩa các runtime Module và gắn module vào loader | Không tự gọi main, constructor hay service provider |
| ClassLoader | Định nghĩa/tra cứu class; tham gia delegation | Không tự tạo cạnh requires/exports/opens |
| ModuleLayer.Controller | Cung cấp quyền điều chỉnh một số quan hệ reads/exports/opens khi dùng static factory | Không giải quyết lại dependency graph hay biến class loader thành sandbox |

Một Module thuộc **một layer** và được gắn với **một class loader**. Ngược lại, **một class loader có thể phục vụ nhiều module** nếu đáp ứng điều kiện package và mô hình nạp. Class identity vẫn dựa trên **tên binary + defining class loader**; module readability và exports là những kiểm tra truy cập **bổ sung**.

Mô hình cơ bản:

~~~text
ModuleFinder.of(pluginDirectory)
         |
         v
parent.configuration().resolve(finder, before, roots)
         |
         v
Configuration (đã xác định module nào đọc module nào)
         |
         +---- defineModulesWithManyLoaders(cf, parentLoader)
         |           mỗi module → loader do JDK tạo
         |
         +---- defineModules(cf, moduleName -> loader)
                     mỗi module → loader do host lựa chọn
         |
         v
ModuleLayer
         |
         +---- findModule("demo.alpha")
         +---- findLoader("demo.alpha")
~~~

**ModuleLayer không bảo đảm an toàn cho mã không tin cậy.** Các module/plugin trong cùng JVM vẫn thực thi trong tiến trình JVM đó; layer và class loader giúp tổ chức namespace/kiểm soát khả năng truy cập, không thay thế cô lập tiến trình, xác thực artifact hay kiểm soát quyền hệ điều hành.

## 2. Các API Java 17 quan trọng

Các phương thức đều thuộc java.lang.ModuleLayer:

| Cách tạo | Phương thức | Giá trị trả về | Ý nghĩa |
| --- | --- | --- | --- |
| Nhiều loader, một parent layer | parent.defineModulesWithManyLoaders(cf, parentLoader) | ModuleLayer | JDK tạo **một loader riêng cho mỗi module** trong cf |
| Nhiều loader, nhiều parent hoặc cần controller | ModuleLayer.defineModulesWithManyLoaders(cf, parentLayers, parentLoader) | ModuleLayer.Controller | Factory tĩnh; gọi controller.layer() để lấy layer |
| Tự ánh xạ, một parent layer | parent.defineModules(cf, nameToLoader) | ModuleLayer | Function<String, ClassLoader> chọn loader theo tên module |
| Tự ánh xạ, nhiều parent hoặc cần controller | ModuleLayer.defineModules(cf, parentLayers, nameToLoader) | ModuleLayer.Controller | Host sở hữu mapping và có Controller |
| Một loader chung do JDK tạo | parent.defineModulesWithOneLoader(cf, parentLoader) | ModuleLayer | Tất cả module trong cf dùng chung một loader mới |

**Dễ nhầm:** tham số parentLoader của defineModulesWithManyLoaders là **ClassLoader cha của các loader mới**, không phải loader dùng chung để **định nghĩa** tất cả module. Để lấy loader thực sự định nghĩa một module, gọi layer.findLoader(moduleName), không lấy parentLoader rồi suy đoán.

Factory dạng instance yêu cầu Configuration có đúng một parent configuration khớp với configuration của layer nhận lời gọi. Factory static nhận danh sách parentLayers theo đúng thứ tự các parent configuration của cf; sai thứ tự/không khớp có thể gây IllegalArgumentException. Trong lab ta chỉ dùng ModuleLayer.boot() làm parent nên chọn dạng instance để code dễ đọc.

**ModuleLayer.Controller** là handle quản lý layer từ các factory tĩnh, hữu ích khi framework cần addReads, addExports hoặc addOpens theo quyền của controller. Những hành động này có điều kiện và cần quản trị rõ ràng, không tự sửa nội dung module-info.java, không được coi là cách bỏ qua mọi kiểm tra module.

## 3. Chọn mô hình loader theo nhu cầu

### 3.1. defineModulesWithManyLoaders: một loader mỗi module

JDK tự tạo loader tương ứng với từng module trong Configuration. Các loader mới có parent là parentLoader đã truyền. Loader do JDK cung cấp biết **direct delegation** theo package/module: khi code cần type thuộc module khác mà quan hệ đọc/exports phù hợp, nó có thể chuyển yêu cầu đến loader chứa module ấy. Do đó một module không nhất thiết bị cô lập hoàn toàn khỏi các module mà nó được phép đọc.

Ưu điểm:

- Host không phải tự viết loader hiểu module path, resource lookup và delegation giữa những named module.
- Dễ quan sát layer.findLoader(name), xác định ranh giới tên package/class của từng module.
- Tránh buộc nhiều module dùng chung một defining loader, có ích khi các module muốn tách class identity và vòng đời.

Giới hạn:

- Tạo thêm loader có chi phí bộ nhớ, metadata và vận hành; số module lớn cần quản trị.
- Module readability/exports vẫn áp dụng. Có loader riêng **không cho phép** một module truy cập package chưa được exports.
- Các loader có parent chung, và loader do JDK tạo có thể delegate tới module readable; đây **không phải** cách ly bảo mật hoặc một cơ chế versioning dependency hoàn toàn tự động.
- Mỗi module có loader riêng **không có nghĩa** tự động unload/reload khi thay JAR; còn reference sống sẽ giữ loader/module tồn tại.

### 3.2. defineModules: ánh xạ tùy chỉnh

Khi gọi defineModules(cf, name -> loader), JVM **không tạo loader thay host**. Hàm phải trả một ClassLoader hợp lệ cho từng tên module trong Configuration. Ví dụ host muốn:

- Chọn loader riêng của từng plugin theo chính sách;
- Ánh xạ một nhóm module vào cùng loader khi package không xung đột;
- Kết hợp loader sẵn có với loader của hệ thống quản lý plugin;
- Kiểm soát riêng việc tra cứu resource, bytecode instrumentation, delegation hoặc thống kê.

Đổi lại, **trách nhiệm về class loading và module delegation chuyển sang host**. Tài liệu Java 17 yêu cầu loader do host triển khai tôn trọng module readability; các loader nên được đăng ký **parallel-capable** để tránh deadlock khi nạp class song song. Trước khi module bị sử dụng, loader phải sẵn sàng đọc class/resource của module được ánh xạ.

Hàm ánh xạ trả null hoặc platform class loader là không hợp lệ; ánh xạ nhiều module có **cùng package** vào cùng loader, dùng loader đã định nghĩa module cùng tên, hoặc dùng loader đã định nghĩa type trong package thuộc module mới có thể gây LayerInstantiationException. **Không tạo mapping bằng cách đoán loader theo thứ tự resolve**; tên module là khóa bắt buộc.

## 4. Quy trình từ modular JAR tới layer

Host cần một tập artifact chứa **module-info.class** hoặc module descriptors hợp lệ. Với explicit named module:

1. Đóng các module thành modular JAR trong thư mục plugin.
2. Dùng ModuleFinder.of(pathToDirectory) để host đọc các module descriptor.
3. Chọn parent layer (thường là ModuleLayer.boot()).
4. Giải quyết từ parent.configuration().resolve(finder, ModuleFinder.of(), roots), trong đó roots là tên module muốn đưa vào graph.
5. Chọn defineModulesWithManyLoaders hoặc defineModules với mapping đã chuẩn bị.
6. Lấy loader bằng layer.findLoader(moduleName), nạp class/khởi tạo provider qua hợp đồng của host.
7. Quản lý lifecycle, exception, task, resource và reference trong suốt thời gian plugin còn hoạt động.

**ModuleFinder không quét mọi JAR tùy ý trên classpath rồi biến chúng thành module trong layer.** Nó đọc các đường dẫn host truyền vào. Module path của process và runtime ClassLoader URL search là những cơ chế riêng; đừng trộn lẫn classpath-based SPI với explicit module declarations.

Phân biệt lỗi:

| Giai đoạn | Ví dụ lỗi | Hướng kiểm tra |
| --- | --- | --- |
| Finder | Không đọc được artifact, module descriptor không hợp lệ, tên trùng | File JAR, module-info.class, nội dung thư mục, ModuleFinder |
| Resolution | Thiếu requires hoặc đồ thị không giải quyết được | Tên module, requires, ModuleFinder parent/before |
| Define layer | Mapping không hợp lệ, loader chứa package đã định nghĩa, xung đột package | Ánh xạ tên → loader, package ownership và quan hệ với parent |
| Load class | Class không nằm trong module/loader hoặc sai tên | layer.findLoader, đường dẫn JAR, package |
| Link/access | NoClassDefFoundError, IllegalAccessError hoặc lỗi truy cập phản chiếu | requires, exports/opens, dependency/version và class identity |
| Invoke | Constructor hoặc phương thức của plugin ném exception | Plugin lifecycle, cấu hình, resource và business logic |

Điểm quan trọng là **Configuration thành công chưa đồng nghĩa code plugin đã nạp thành công**. Phần lớn việc nạp class vẫn có thể là lazy và chỉ xảy ra khi host lần đầu dùng implementation.

## 5. Lab Java 17+ với hai named module độc lập

Lab sẽ tạo hai modular JAR: demo.alpha.jar và demo.beta.jar. Chúng chỉ dùng java.base ngầm định, **không requires lẫn nhau**. Đây là lựa chọn có chủ đích để mô hình ánh xạ bằng URLClassLoader trong lab dễ hiểu; khi có phụ thuộc liên module phức tạp, host phải triển khai delegation phù hợp thay vì sao chép máy móc mẫu loader tối giản.

Cấu trúc:

~~~text
lab/
├── src/
│   ├── demo.alpha/
│   │   ├── module-info.java
│   │   └── demo/alpha/api/Alpha.java
│   ├── demo.beta/
│   │   ├── module-info.java
│   │   └── demo/beta/api/Beta.java
│   └── host/LayerDemo.java
├── build/               (tạo khi biên dịch)
└── modules/             (chứa hai modular JAR)
~~~

### 5.1. Module demo.alpha

File **src/demo.alpha/module-info.java**:

~~~java
module demo.alpha {
    exports demo.alpha.api;
}
~~~

File **src/demo.alpha/demo/alpha/api/Alpha.java**:

~~~java
package demo.alpha.api;

public final class Alpha {
    private Alpha() {}

    public static String message() {
        return "alpha";
    }
}
~~~

Khai báo exports demo.alpha.api để code ở unnamed module của host có quyền truy cập **public type và public method** trong package này. Nếu không exports, việc gọi reflection công khai như getMethod(...).invoke(...) từ host có thể gặp IllegalAccessException ngay cả khi class đã được loader tìm thấy.

### 5.2. Module demo.beta

File **src/demo.beta/module-info.java**:

~~~java
module demo.beta {
    exports demo.beta.api;
}
~~~

File **src/demo.beta/demo/beta/api/Beta.java**:

~~~java
package demo.beta.api;

public final class Beta {
    private Beta() {}

    public static String message() {
        return "beta";
    }
}
~~~

Hai module dùng hai package không trùng nhau, giúp lab minh họa rõ cách ánh xạ module sang loader. Chúng không phải module tự động suy ra từ tên file; module-info.java xác định tên demo.alpha và demo.beta.

### 5.3. Host tạo hai layer bằng hai cách

File **src/host/LayerDemo.java**:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.Map;
import java.util.Set;

public final class LayerDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: LayerDemo <modules-directory>");
        }

        Path dir = Path.of(args[0]).toAbsolutePath();
        ModuleLayer parent = ModuleLayer.boot();

        ModuleFinder finder = ModuleFinder.of(dir);
        Configuration configuration = parent.configuration()
                .resolve(finder, ModuleFinder.of(),
                        Set.of("demo.alpha", "demo.beta"));

        // Cách 1: để JDK tạo một ClassLoader riêng cho mỗi module.
        ModuleLayer many = parent.defineModulesWithManyLoaders(
                configuration, ClassLoader.getSystemClassLoader());
        show("many", many);

        // Cách 2: host tự chọn loader cho từng tên module.
        URL alphaUrl = dir.resolve("demo.alpha.jar").toUri().toURL();
        URL betaUrl = dir.resolve("demo.beta.jar").toUri().toURL();

        try (URLClassLoader alphaLoader = new URLClassLoader(
                     new URL[] {alphaUrl}, ClassLoader.getSystemClassLoader());
             URLClassLoader betaLoader = new URLClassLoader(
                     new URL[] {betaUrl}, ClassLoader.getSystemClassLoader())) {

            Map<String, ClassLoader> byName = Map.of(
                    "demo.alpha", alphaLoader,
                    "demo.beta", betaLoader);

            ModuleLayer custom = parent.defineModules(
                    configuration, name -> {
                        ClassLoader loader = byName.get(name);
                        if (loader == null) {
                            throw new IllegalArgumentException(
                                    "No loader mapped for " + name);
                        }
                        return loader;
                    });

            show("custom", custom);
        }
    }

    private static void show(String label, ModuleLayer layer)
            throws ReflectiveOperationException {
        ClassLoader alphaLoader = layer.findLoader("demo.alpha");
        ClassLoader betaLoader = layer.findLoader("demo.beta");

        Class<?> alpha = Class.forName(
                "demo.alpha.api.Alpha", true, alphaLoader);
        Class<?> beta = Class.forName(
                "demo.beta.api.Beta", true, betaLoader);

        System.out.println(label + " alpha="
                + alpha.getMethod("message").invoke(null));
        System.out.println(label + " beta="
                + beta.getMethod("message").invoke(null));
        System.out.println(label + " distinct="
                + (alphaLoader != betaLoader));
        System.out.println(label + " named="
                + (alpha.getModule().isNamed()
                   && beta.getModule().isNamed()));
    }
}
~~~

Giải thích:

- ModuleFinder.of(dir) tìm hai modular JAR đã đóng gói trong modules/.
- configuration() của boot layer là parent Configuration; resolve dùng cả hai tên module làm roots.
- many tạo hai loader mới; layer.findLoader("demo.alpha") và layer.findLoader("demo.beta") trả các loader thực sự gắn với module.
- custom map **đúng tên module** sang hai URLClassLoader độc lập, được tạo và cấu hình URL trước khi định nghĩa layer. Để minh họa mapping, mỗi loader chỉ chứa JAR của module tương ứng.
- Host không compile-time import Alpha/Beta: nó lấy class bằng tên binary và loader được trả từ layer rồi gọi public static method qua reflection.
- Các package demo.alpha.api và demo.beta.api đã được exports từ module-info; vì vậy host có thể gọi public member qua reflection thông thường.
- Hai layer được tạo từ **cùng Configuration**, nhưng với **những loader khác nhau**. Các Module object của hai layer khác nhau; không chia sẻ instance implementation qua hai loader khi không có hợp đồng chung.
- try-with-resources đóng các URLClassLoader của **ví dụ custom** sau khi gọi xong. Loader do JDK tạo bởi many không phải là URLClassLoader do ứng dụng trực tiếp sở hữu; không tự giả định có thể đóng nó bằng cách ép kiểu.

**Quan trọng về phạm vi ví dụ custom:** hai module chỉ cần java.base nên parent system loader đủ giải quyết những type JDK được dùng. Nếu demo.beta có requires demo.alpha và cần load trực tiếp class Alpha, hai URLClassLoader đơn giản với hai URL tách biệt **không tự bảo đảm delegation chéo theo module readability**; với bài toán thực, hãy sử dụng các loader do JDK tạo, hoặc viết loader/module routing thích hợp và kiểm thử đầy đủ.

### 5.4. Biên dịch modular JAR và host

Chạy từ thư mục lab/ trên bash/POSIX với JDK 17 trở lên:

~~~bash
mkdir -p build/alpha build/beta build/host modules

javac -encoding UTF-8 -d build/alpha src/demo.alpha/module-info.java src/demo.alpha/demo/alpha/api/Alpha.java
jar --create --file modules/demo.alpha.jar -C build/alpha .

javac -encoding UTF-8 -d build/beta src/demo.beta/module-info.java src/demo.beta/demo/beta/api/Beta.java
jar --create --file modules/demo.beta.jar -C build/beta .

javac -encoding UTF-8 -d build/host src/host/LayerDemo.java
java -cp build/host LayerDemo modules
~~~

Đây là **hai explicit named modules**; jar được đóng với module-info.class và class implementation. Host chạy trên classpath chỉ gồm build/host và nhận thư mục chứa modular JAR bằng đối số. Không đưa modules/*.jar vào host -cp; host sẽ tìm chúng thông qua ModuleFinder ở runtime.

Stdout kỳ vọng khi các file và lệnh đúng như trên:

~~~text
many alpha=alpha
many beta=beta
many distinct=true
many named=true
custom alpha=alpha
custom beta=beta
custom distinct=true
custom named=true
~~~

Các dòng distinct=true chứng minh **trong từng layer**, hai module sử dụng hai loader khác nhau. named=true cho thấy những class được nạp thuộc named module, thay vì chỉ tồn tại trong unnamed module của classpath.

Để kiểm tra artifact:

~~~bash
jar --describe-module --file modules/demo.alpha.jar
jar --describe-module --file modules/demo.beta.jar
~~~

Đầu ra của jar --describe-module có thể gồm tên module, packages, exports và requires java.base; không nên sao chép nguyên văn stdout của công cụ giữa những bản JDK khác nhau rồi coi định dạng là hợp đồng ổn định. Phần cần xác minh là tên demo.alpha/demo.beta, package exports và module-info.class thực sự được đóng trong JAR.

Trên Windows dùng dấu **;** nếu tham số -cp có nhiều phần; trong lệnh host ở trên chỉ có một entry nên không cần đổi. mkdir -p là cú pháp bash; với PowerShell có thể tạo thư mục bằng New-Item -ItemType Directory -Force.

## 6. Khi muốn gom module vào cùng loader bằng mapping tùy chỉnh

Một lý do thực tế để dùng defineModules là nhóm những module có package tách biệt vào loader chung do host quản lý. Ví dụ **mã minh họa, không phải chương trình hoàn chỉnh**:

~~~java
// Giả định parent, configuration, alphaJar, betaJar đã xác định.
// Host phải đóng sharedLoader sau khi tất cả module ngừng dùng.
URLClassLoader sharedLoader = new URLClassLoader(
        new URL[] {alphaJar.toUri().toURL(), betaJar.toUri().toURL()},
        ClassLoader.getSystemClassLoader());

ModuleLayer shared = parent.defineModules(configuration,
        name -> switch (name) {
            case "demo.alpha", "demo.beta" -> sharedLoader;
            default -> throw new IllegalArgumentException(name);
        });
~~~

Cách này dùng **một loader** cho hai module có package khác nhau. Nếu mục tiêu chỉ là "một loader mới cho mọi module" và không cần xử lý custom riêng, defineModulesWithOneLoader thường đơn giản hơn và thực thi direct delegation do JDK cung cấp. Đừng dùng mapping thủ công chỉ vì muốn mô phỏng API đã có sẵn.

**Ràng buộc package:** hai module có cùng một package mà được ánh xạ vào **cùng ClassLoader** sẽ không thể được định nghĩa hợp lệ. Đây là một lý do nên phân tách namespace của plugin rõ ràng. Mapping khác loader có thể thay đổi điều kiện về xung đột trong loader, nhưng không sửa được sai lệch của requires, exports, opens hay class identity.

**Dữ liệu sống của plugin:** dù định nghĩa layer thành công, khi host gọi close() trên URLClassLoader, việc nạp thêm class/resource từ URL có thể không hoạt động nữa. Vì vậy plugin manager cần giữ loader đến hết phiên hoạt động; chỉ đóng sau khi dừng task, provider, listener và resource có liên quan. Close không chứng minh class đã unload ngay.

## 7. Readability, exports, opens và delegation

Có loader khác nhau là một nửa bài toán. JPMS còn kiểm soát **module nào được đọc module nào** và **package nào được công khai**:

| Cơ chế | Ý nghĩa thực tế | Cách kiểm tra |
| --- | --- | --- |
| requires demo.alpha trong module-info của demo.beta | demo.beta đọc demo.alpha ở compile/runtime module graph | Configuration resolution và Module.canRead |
| exports demo.alpha.api | Cho các module khác truy cập public types trong package được export | Module.isExported và lỗi access |
| exports demo.alpha.api to demo.beta | Chỉ cấp exports có điều kiện cho module được nêu | Không mặc định public với host khác |
| opens demo.alpha.internal | Cho deep reflection phù hợp tới package; không đồng nghĩa exports type tại compile time | Module.isOpen và quyền phản chiếu |
| loader delegation | Nếu type thuộc module readable khác, loader phải biết chuyển tới loader thực sự định nghĩa type | Kiểm thử Class.forName và invokes ở nhiều module |
| layer.findLoader(name) | Tìm loader gắn với module được định nghĩa trong layer hoặc các parent layer | Không đồng nhất nó với TCCL hoặc system loader |

Ví dụ khi demo.beta cần public type từ demo.alpha, chỉnh module-info.java của beta thành:

~~~java
module demo.beta {
    requires demo.alpha;
    exports demo.beta.api;
}
~~~

Đây là **đoạn minh họa thay đổi descriptor**, chưa phải lab runnable hoàn chỉnh: còn cần cập nhật class của beta, biên dịch với module path chứa demo.alpha, và thực hiện kiểm thử delegation. Với defineModulesWithManyLoaders, loader do JDK tạo hỗ trợ direct delegation cho các package/module readable. Với loader custom, host phải thiết kế đường ủy quyền tương ứng và tránh vòng ủy quyền gây deadlock.

**Đừng nhầm TCCL với defining loader.** Thread.currentThread().setContextClassLoader(...) chỉ thay context class loader của thread cho những API có sử dụng nó; nó không thay ModuleLayer mapping hay class identity của class đã định nghĩa. Để lấy đúng loader của named module, hãy sử dụng layer.findLoader(moduleName).

**Đừng nhầm opens với exports.** Deep reflection vào non-public member cần quyền opens tương ứng, còn truy cập public API của module trong lab đã được hỗ trợ bằng exports. Việc host lấy được Class object không bảo đảm mọi phương thức đều có thể được invoke nếu module không mở/xuất package.

## 8. ServiceLoader trong layer plugin

Nếu ứng dụng dùng SPI thay vì reflection để chọn class theo tên, named module thường khai báo service bằng module-info.java:

~~~java
module demo.plugin {
    requires demo.api;
    provides demo.api.PluginService with demo.plugin.PluginServiceImpl;
}
~~~

Ở phía consumer named module, khai báo uses demo.api.PluginService khi cần dùng cơ chế service binding. Với một layer đã định nghĩa xong, host có thể dùng overload có layer tường minh:

~~~java
// Minh họa tích hợp: giả định layer và PluginService đã tồn tại.
ServiceLoader<PluginService> providers =
        ServiceLoader.load(layer, PluginService.class);
for (PluginService provider : providers) {
    provider.run();
}
~~~

Các đoạn code ở đây **không thuộc lab build đầy đủ** vì lab dùng reflection và không định nghĩa demo.api.PluginService. Chúng làm rõ đường mở rộng khi tích hợp plugin SPI thực tế.

ServiceLoader.load(layer, service) tìm provider theo cơ chế module layer, khác với ServiceLoader.load(service) dùng thread context class loader. Cần xem đúng phạm vi module graph, uses/provides, cùng danh tính class của SPI, và kiểm tra việc provider được mở rộng trong layer phụ thuộc. Không đưa JAR lên một module layer rồi cho rằng ServiceLoader sẽ quét mọi class triển khai interface mà không có cấu hình dịch vụ.

Với hệ thống chứa cả plugin trên classpath lẫn named module, phải phân biệt **META-INF/services trên classpath** với provides trong explicit named module; cách định danh và tìm provider phụ thuộc kiểu module/loader. Đừng trộn ngẫu nhiên hai cơ chế discovery.

## 9. Lỗi dễ mắc với custom loader mapping

**Lỗi 1 — nhầm parentLoader với loader của module.**

~~~java
// Không đúng khi cần kiểm tra loader định nghĩa module:
ClassLoader assumed = ClassLoader.getSystemClassLoader();

// Đúng:
ClassLoader actual = layer.findLoader("demo.alpha");
~~~

Trong many-loader mode, loader actual là loader mới do JDK tạo; system loader chỉ là parent được truyền vào.

**Lỗi 2 — chỉ trả một URLClassLoader có URL thiếu dependency.** Nếu module yêu cầu class từ module khác, Java phải vừa cho phép quan hệ requires/exports, vừa tìm được class qua delegation thích hợp. Một URLClassLoader chỉ chứa JAR của nó không tự điều phối mọi named module dependency. Đừng xem LayerInstantiationException hoặc NoClassDefFoundError là bằng chứng phải bỏ JPMS; hãy kiểm tra graph và mapping.

**Lỗi 3 — mapping không đủ mọi module của Configuration.** Function<String,ClassLoader> nhận tên module được JVM yêu cầu. Nếu thiếu mapping, trả null sẽ bị từ chối; nếu chủ động ném IllegalArgumentException, lỗi sẽ nổi lên ngay lúc defineModules. Nên xây map đầy đủ từ module names đã resolve, trước khi định nghĩa layer.

**Lỗi 4 — dùng lại loader đã định nghĩa class trong package sắp gán.** Runtime package identity theo defining loader/module có thể khiến việc định nghĩa module mới không hợp lệ. Chuẩn bị loader mới trước khi tải class plugin và không thêm cùng module vào một loader đã có module cùng tên.

**Lỗi 5 — đọc được module nhưng package không exports.** Reflection có thể thấy tên class nhưng gọi method fail. Kiểm tra exports/opens thay vì chỉ sửa URL của loader.

**Lỗi 6 — đóng loader quá sớm.** close() của URLClassLoader hạn chế khả năng tải class/resource mới từ URL, trong khi code đang dùng có thể vẫn chạy. Khi cập nhật plugin, dừng work, cleanup reference, tạo layer/loader thế hệ mới rồi mới đổi registry; không hứa "hot swap class" trong chính layer hiện hữu.

**Lỗi 7 — nghĩ class loader là sandbox.** Mã plugin vẫn có thể thực thi với quyền tiến trình. Đối với plugin không tin cậy cần chính sách nguồn artifact và cô lập tiến trình/container phù hợp.

**Lỗi 8 — bỏ qua rủi ro partial failure khi custom mapping.** Tài liệu Java 17 nói việc defineModules với mapping tùy chỉnh có thể **không atomic tùy implementation**: một số module có thể đã được định nghĩa vào JVM dù method thất bại ở module khác. Không retry với nguyên loader sau lỗi mà không đánh giá trạng thái; thiết kế tạo loader mới và rollback quyền sở hữu tài nguyên ở tầng plugin manager.

## 10. Chọn giải pháp, validate và vận hành

| Tiêu chí | withManyLoaders | defineModules với mapping |
| --- | --- | --- |
| Ai tạo loader? | JDK | Host |
| Mỗi module một loader? | Có | Tùy mapping |
| Delegation theo module graph | Loader do JDK cung cấp thực hiện direct delegation | Host chịu trách nhiệm triển khai phù hợp |
| Lựa chọn parent loader | Truyền parentLoader cho các loader mới | Chọn parent khi host tạo loader |
| Quyền kiểm soát findClass/resource | Theo hành vi loader do JDK tạo | Có thể tùy biến nếu host thực sự triển khai |
| Chi phí bảo trì | Thường thấp hơn | Cao hơn, cần kiểm thử concurrency và linkage |
| Use case điển hình | Nạp nhiều named module plugin có dependencies theo JPMS | Plugin manager có loader/route/policy riêng |
| Vòng đời | Vẫn phải quản lý reference/provider/task | Host còn quản lý close() của loader do mình tạo |

Khi lập hệ thống thật, nên bổ sung:

1. **Preflight artifact:** danh tính module, phiên bản, source/checksum, module-info, package trùng, danh sách requires và các dependency runtime.
2. **Resolution trước definition:** báo rõ FindException/ResolutionException và tên module gây lỗi; tránh dùng cùng tên module khác phiên bản trong graph không kiểm soát.
3. **Mapping kiểm chứng được:** bảng module → loader, classpath/resource của loader, parent chain, đường delegation cho required module và chính sách package ownership.
4. **Startup validation:** tạo layer, kiểm tra findModule/findLoader, nạp class/provide service thực tế, xác nhận exports/opens và phép gọi API quan trọng.
5. **Failure isolation:** phân biệt lỗi resolve, define, class loading, reflection và provider runtime. Nếu custom definition thất bại, không mặc định thao tác có thể rollback atomic.
6. **Lifecycle:** giữ loader sống khi plugin hoạt động; ngừng tiếp nhận task, dừng thread/callback, giải phóng reference rồi mới close loader do host sở hữu.
7. **Cô lập và bảo mật:** kiểm tra độ tin cậy của plugin và xem xét thực thi ngoài JVM khi cần sandbox thực sự; module layer không phải cơ chế cấp quyền OS.

**Bài tập mở rộng:** (a) thay mapping của beta sang cùng alphaLoader sau khi đảm bảo URLClassLoader có đủ hai JAR và hai package tách biệt; so sánh distinct; (b) thêm requires demo.alpha vào beta, rồi thiết kế loader custom có delegation chính xác và so sánh với withManyLoaders; (c) bỏ exports demo.alpha.api và quan sát lỗi reflection; (d) thử define hai module có cùng package vào một loader custom; (e) theo dõi vòng đời hai thế hệ plugin loader khi cập nhật artifact.

**Nguồn API:** [Java SE 17 — ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html), [Java SE 17 — ModuleFinder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html), [Java SE 17 — Configuration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html).

Nguyên tắc kỹ thuật: **dùng defineModulesWithManyLoaders khi cần một loader do JDK quản lý cho từng module; dùng defineModules khi thực sự cần chính sách ánh xạ riêng và sẵn sàng chịu trách nhiệm về loading/delegation, package ownership, concurrency và lifecycle**. Cả hai đều phải bắt đầu từ Configuration hợp lệ và được kiểm chứng bằng hành vi nạp class thực tế.