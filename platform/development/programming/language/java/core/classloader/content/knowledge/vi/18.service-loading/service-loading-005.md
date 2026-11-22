# ServiceLoader.load với ModuleLayer trong Java

## 1. Vì sao cần overload nhận ModuleLayer?

Trong kiến trúc Java có host và plugin, host muốn làm việc với một **service interface** chung, nhưng implementation có thể nằm trong **named module** được nạp vào một `ModuleLayer` mới khi ứng dụng đã chạy. Java 9+ cung cấp overload:

~~~java
public static <S> ServiceLoader<S> load(
        ModuleLayer layer, Class<S> service)
~~~

Đây là chữ ký API, không phải chương trình Java hoàn chỉnh. Nó tạo `ServiceLoader<S>` để khám phá những provider đã đăng ký trong **named modules của layer được truyền vào và các ancestor layers**.

Khác với việc lấy một class bất kỳ qua `ClassLoader.loadClass("pkg.Type")`, ServiceLoader tìm những implementation đã đăng ký cho **một service contract**; consumer không phải import trực tiếp tên implementation.

~~~text
           ModuleLayer.boot()
      +-----------------------------+
      | com.acme.host               |
      | com.acme.spi                |
      | Greeter (service interface) |
      +-----------------------------+
                    ^
                    | parent layer
                    |
        Child ModuleLayer
      +-----------------------------+
      | com.acme.greeter            |
      | HelloGreeter (provider)     |
      +-----------------------------+

ServiceLoader.load(childLayer, Greeter.class)
          -> tìm child layer
          -> sau đó ancestor layers
          -> không tìm provider thuộc unnamed module
             chỉ vì có trên classpath
~~~

Phân biệt bốn khái niệm:

- **`ClassLoader`**: chịu trách nhiệm tìm và định nghĩa classes.
- **`ModuleLayer`**: tập resolved modules với configuration và ánh xạ tới class loaders.
- **`ServiceLoader`**: API khám phá/khởi tạo những provider của một service.
- **`ModuleFinder`**: phát hiện các module trên các đường dẫn chỉ định; bản thân nó **không** tạo layer hoặc tự nạp provider.

Đối với plugin chạy như **explicit named module**, có thể chủ động resolve một module mới vào child layer, rồi gọi `ServiceLoader.load(childLayer, Greeter.class)` mà không cần đặt module plugin lên boot module path từ đầu.

## 2. Hợp đồng giữa ba module

Ví dụ có:

| Module | Vai trò | Chỉ thị thiết yếu |
| --- | --- | --- |
| `com.acme.spi` | Chứa interface `Greeter` | `exports com.acme.spi;` |
| `com.acme.host` | Consumer tìm provider | `requires com.acme.spi;`, **`uses com.acme.spi.Greeter;`** |
| `com.acme.greeter` | Provider module | `requires com.acme.spi;`, **`provides com.acme.spi.Greeter with com.acme.greeter.HelloGreeter;`** |

Interface chung:

~~~java
package com.acme.spi;

public interface Greeter {
    String greet();
}
~~~

Một caller là explicit named module phải **khai báo `uses`** cho service mà nó yêu cầu qua ServiceLoader. Chỉ có `requires com.acme.spi;` là chưa đủ: requires cấp readability, còn uses là tuyên bố nhu cầu sử dụng service. Nếu không có uses phù hợp, API có thể ném `ServiceConfigurationError`.

Trong module provider:

~~~java
module com.acme.greeter {
    requires com.acme.spi;
    provides com.acme.spi.Greeter
            with com.acme.greeter.HelloGreeter;
}
~~~

Từ khóa `provides ... with ...` đăng ký provider theo descriptor. **Không cần `exports com.acme.greeter;` chỉ để ServiceLoader tạo provider**. Host chỉ cần type `Greeter` của SPI module, trong khi class implementation có thể tiếp tục được đóng gói nội bộ.

Một kiểu service/interface phải có **danh tính runtime nhất quán**. Nếu host có `com.acme.spi.Greeter` do loader A định nghĩa, còn plugin lại dùng bản copy Greeter do loader B định nghĩa, chúng có thể không phải cùng interface dù tên giống nhau, dẫn đến lỗi cast/linkage. Đặt SPI module ở parent layer và dùng cùng module là lựa chọn phổ biến.

## 3. Phạm vi của load(layer, service)

Theo Java SE API:

1. Tìm providers trong **layer được truyền vào**.
2. Tìm tiếp providers trong **ancestor layers** của layer đó.
3. **Không tìm providers thuộc unnamed modules** qua overload này.
4. Khi có nhiều parent layers, traversal là **depth-first**; mỗi ancestor layer được xét tối đa một lần.
5. **Không có thứ tự xác định giữa các modules trong cùng layer**. Nếu kết quả cần ưu tiên, ứng dụng phải chọn/sắp xếp rõ ràng.
6. Trong một module khai báo nhiều providers, thứ tự trong module descriptor có vai trò theo quy tắc API; providers thêm động do instrumentation có quy định riêng.
7. Chỉ có những modules thực sự **đã resolve vào layer graph** mới thuộc phạm vi. Có một JAR trên ổ đĩa không đồng nghĩa layer đang chứa module ấy.

Giả sử `L0` là boot, `L1` và `L2` có parent là `L0`, còn `L3` được tạo với hai parents `L1` và `L2`:

~~~text
         L0
       /    \
      L1     L2
        \   /
         L3
~~~

Lời gọi `load(L3, Service.class)` dò L3 trước, rồi ancestors với quy tắc depth-first và tránh xử lý một layer nhiều lần. Một **sibling layer** khác trong JVM không tự được dò nếu không phải ancestor của layer được truyền.

**Đặc biệt:** `ServiceLoader.load(ModuleLayer.boot(), Greeter.class)` không tự đi xuống mọi descendant layer. Nếu provider mới chỉ nằm trong child layer, hãy truyền child layer đó.

## 4. Quy trình tạo child layer cho plugin

Một ví dụ đơn giản chọn boot layer làm parent:

~~~java
ModuleLayer parent = ModuleLayer.boot();

ModuleFinder finder = ModuleFinder.of(
        Path.of("build/plugins"));

Configuration config = parent.configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.acme.greeter"));

ModuleLayer pluginLayer = parent.defineModulesWithOneLoader(
        config, ClassLoader.getSystemClassLoader());

ServiceLoader<Greeter> services =
        ServiceLoader.load(pluginLayer, Greeter.class);
~~~

Đoạn trên chỉ minh họa API cốt lõi; import và project chạy đầy đủ ở phần 5.

**Giải thích:**

1. `ModuleLayer.boot()` lấy boot layer chứa những named modules đã được launcher/JVM resolve.
2. `ModuleFinder.of(Path.of(...))` phát hiện exploded modules hoặc modular JAR được đặt đúng vị trí.
3. `Configuration.resolve` tạo configuration mới dựa vào parent configuration. Tập `Set.of("com.acme.greeter")` chỉ định module root; resolver xử lý thêm các required modules phù hợp.
4. `parent.defineModulesWithOneLoader(config, parentLoader)` định nghĩa child layer. Phương thức tạo **một class loader mới** cho modules thuộc configuration của layer con. Đối số `ClassLoader.getSystemClassLoader()` là **parent của loader mới**, không phải chính defining loader của các class plugin.
5. `ServiceLoader.load(pluginLayer, Greeter.class)` khám phá provider theo metadata của các named modules trong plugin layer và ancestors.

Nếu một plugin JAR nằm trong finder path nhưng **không nằm trong graph được resolve**, `ServiceLoader` không tự thêm module đó vào layer. Đối với bài toán auto-discovery có service-binding resolution, API `Configuration.resolveAndBind` là lựa chọn khác cần nghiên cứu; ví dụ này cố ý đặt provider làm root rõ ràng để hành vi có thể tái lập.

### One loader và many loaders khác nhau ra sao?

- `defineModulesWithOneLoader` tạo một class loader cho tất cả modules trong child configuration.
- `defineModulesWithManyLoaders` tạo class loader riêng cho từng module theo hợp đồng API.
- Cả hai đều tạo **named modules trong layer**; không phải đơn giản thêm JAR vào classpath.
- Quyết định cần xét số modules, split packages, mối quan hệ module/loader và quy tắc delegation. Với một module plugin, `oneLoader` đủ để học rõ ServiceLoader.

## 5. Ví dụ Java 17+ chạy được: 3 modules, 1 provider

Bài tập biên dịch ba modules, nhưng khi **chạy** sẽ tách:
- `com.acme.host` và `com.acme.spi` nằm trên module path của launcher, thuộc boot layer.
- `com.acme.greeter` nằm ở đường dẫn plugin riêng và chỉ được đưa vào **child layer** qua `ModuleFinder`/`Configuration`.

### Cấu trúc nguồn

~~~text
example/
└── src/
    ├── com.acme.spi/
    │   ├── module-info.java
    │   └── com/acme/spi/Greeter.java
    ├── com.acme.host/
    │   ├── module-info.java
    │   └── com/acme/host/Main.java
    └── com.acme.greeter/
        ├── module-info.java
        └── com/acme/greeter/HelloGreeter.java
~~~

### File src/com.acme.spi/module-info.java

~~~java
module com.acme.spi {
    exports com.acme.spi;
}
~~~

### File src/com.acme.spi/com/acme/spi/Greeter.java

~~~java
package com.acme.spi;

public interface Greeter {
    String greet();
}
~~~

### File src/com.acme.greeter/module-info.java

~~~java
module com.acme.greeter {
    requires com.acme.spi;
    provides com.acme.spi.Greeter
            with com.acme.greeter.HelloGreeter;
}
~~~

### File src/com.acme.greeter/com/acme/greeter/HelloGreeter.java

~~~java
package com.acme.greeter;

import com.acme.spi.Greeter;

public final class HelloGreeter implements Greeter {
    @Override
    public String greet() {
        return "Hello from child layer";
    }
}
~~~

Lớp provider public không có constructor tường minh, nên có implicit public default constructor phù hợp mô hình provider dùng constructor trong trường hợp này. Package implementation không cần exports cho host.

### File src/com.acme.host/module-info.java

~~~java
module com.acme.host {
    requires com.acme.spi;
    uses com.acme.spi.Greeter;
}
~~~

### File src/com.acme.host/com/acme/host/Main.java

~~~java
package com.acme.host;

import com.acme.spi.Greeter;
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.ServiceLoader;
import java.util.Set;

public class Main {
    public static void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "plugin module directory required");
        }

        ModuleLayer parent = ModuleLayer.boot();
        ModuleFinder plugins = ModuleFinder.of(Path.of(args[0]));

        Configuration config = parent.configuration().resolve(
                plugins,
                ModuleFinder.of(),
                Set.of("com.acme.greeter"));

        ModuleLayer child = parent.defineModulesWithOneLoader(
                config, ClassLoader.getSystemClassLoader());

        System.out.println("child has provider: "
                + child.findModule("com.acme.greeter").isPresent());
        System.out.println("host in boot: "
                + (Main.class.getModule().getLayer() == parent));

        List<Greeter> services =
                ServiceLoader.load(child, Greeter.class)
                    .stream()
                    .map(ServiceLoader.Provider::get)
                    .toList();

        System.out.println("provider count: " + services.size());

        for (Greeter greeter : services) {
            Module module = greeter.getClass().getModule();

            System.out.println("provider module: "
                    + module.getName());
            System.out.println("provider in child: "
                    + (module.getLayer() == child));
            System.out.println("message: "
                    + greeter.greet());
        }
    }
}
~~~

Ý nghĩa các bước:
- Host khai báo `uses` trong module descriptor, không gọi implementation trực tiếp.
- Module `com.acme.spi` ở parent tạo contract chung.
- Finder tìm module plugin, config resolve root, layer mới được định nghĩa.
- `ServiceLoader.load(child, Greeter.class)` tìm provider trong child/ancestors.
- `stream().map(ServiceLoader.Provider::get)` yêu cầu instance provider; việc khởi tạo provider là lazy khi duyệt.
- Một provider duy nhất giúp stdout ổn định; nếu có nhiều modules, không dựa vào thứ tự iteration không được đảm bảo.

### Biên dịch và chạy: Linux/macOS

Đứng trong thư mục example đã có sáu tệp Java:

~~~bash
mkdir -p build/all build/base build/plugins

javac --release 17 --module-source-path src \
    -d build/all $(find src -name '*.java')

cp -R build/all/com.acme.spi build/base/
cp -R build/all/com.acme.host build/base/
cp -R build/all/com.acme.greeter build/plugins/

java --module-path build/base \
    --module com.acme.host/com.acme.host.Main build/plugins
~~~

Đảm bảo `build/base` **chỉ** chứa host và SPI, `build/plugins` **chỉ** chứa provider. Khi chạy, không đưa provider vào `--module-path build/base`. Plugin được phát hiện và resolve sau khi app đã vào phương thức `main`.

### Biên dịch và chạy: Windows PowerShell

Dùng lệnh một dòng để tránh nhầm ký tự nối dòng:

~~~powershell
New-Item -ItemType Directory -Force build\all, build\base, build\plugins | Out-Null
$sources = @(Get-ChildItem -Path src -Recurse -Filter *.java | ForEach-Object { $_.FullName })
javac --release 17 --module-source-path src -d build\all $sources
Copy-Item build\all\com.acme.spi build\base\com.acme.spi -Recurse
Copy-Item build\all\com.acme.host build\base\com.acme.host -Recurse
Copy-Item build\all\com.acme.greeter build\plugins\com.acme.greeter -Recurse
java --module-path build\base --module com.acme.host/com.acme.host.Main build\plugins
~~~

Cần biên dịch thành công trước khi copy module output. Nếu chạy lại, hãy xóa output cũ thích hợp hoặc build trong thư mục mới để tránh module cũ gây nhiễu.

### Stdout thực tế đã kiểm chứng

~~~text
child has provider: true
host in boot: true
provider count: 1
provider module: com.acme.greeter
provider in child: true
message: Hello from child layer
~~~

Mã nguồn ở trên đã được biên dịch với `javac --release 17` và chạy thành công trên OpenJDK 21.

**Phân tích output:**
1. Child layer thực sự có module `com.acme.greeter`.
2. Host giữ nguyên trong boot layer.
3. Chỉ một provider được nạp do có một khai báo `provides` phù hợp.
4. Instance `HelloGreeter` thuộc module `com.acme.greeter`.
5. Module chứa class provider thuộc child layer chứ không phải boot.
6. Host gọi `greeter.greet()` qua interface chung, nhận chuỗi mong đợi.

## 6. Thay exploded module bằng modular JAR

`ModuleFinder` có thể đọc một **modular JAR** có `module-info.class`. Khi đã compile phần 5, đóng gói provider:

~~~bash
mkdir -p build/plugin-jars
jar --create --file build/plugin-jars/com.acme.greeter.jar \
    -C build/all/com.acme.greeter .
java --module-path build/base \
    --module com.acme.host/com.acme.host.Main build/plugin-jars
~~~

Trên PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build\plugin-jars | Out-Null
jar --create --file build\plugin-jars\com.acme.greeter.jar -C build\all\com.acme.greeter .
java --module-path build\base --module com.acme.host/com.acme.host.Main build\plugin-jars
~~~

Lớp `Main` không cần sửa vì nó nhận plugin path qua `args[0]`. ModuleFinder phát hiện file JAR, resolver tạo child configuration, ServiceLoader tìm provider từ named module trong child layer.

Có thể kiểm tra JAR qua:

~~~bash
jar --describe-module --file build/plugin-jars/com.acme.greeter.jar
~~~

Biến thể modular JAR cũng đã được chạy thử trong một bài kiểm thử riêng trên OpenJDK, trả đúng provider. Lưu ý: thêm file JAR sau khi layer đã được tạo **không cập nhật layer đã tồn tại**; phải resolve/tạo layer mới nếu muốn module set mới.

## 7. So sánh các overload ServiceLoader

| API | Nguồn tìm provider | Khi nào phù hợp |
| --- | --- | --- |
| `ServiceLoader.load(ModuleLayer layer, Class<S> service)` | Named modules trong **layer và ancestors**, không unnamed modules. | Plugin/module layers JPMS. |
| `ServiceLoader.load(Class<S> service)` | Dùng **thread context class loader** của thread hiện tại. | Ứng dụng hoặc framework quản lý services theo TCCL. |
| `ServiceLoader.load(Class<S> service, ClassLoader loader)` | Sử dụng class loader được chỉ định theo quy tắc ServiceLoader. | Chủ động chọn loader để tìm services theo môi trường. |
| `ServiceLoader.loadInstalled(Class<S> service)` | Sử dụng platform class loader. | Phạm vi platform/installed providers theo API. |

**Điểm quan trọng:** Overload `load(layer, service)` không phải cú pháp viết khác của `load(service, classLoader)`. Layer xác định graph named modules, còn ClassLoader xác định cơ chế nạp và tìm resource/provider theo API tương ứng. Việc đổi TCCL không biến một ServiceLoader theo layer thành bộ dò mọi unnamed provider.

### META-INF/services khác provides

Với classpath truyền thống, nhà cung cấp thường đăng ký qua:

~~~text
META-INF/services/com.acme.spi.Greeter
~~~

Nội dung là binary name provider, ví dụ `com.acme.greeter.HelloGreeter`. Đó là cấu hình service cho classpath/unnamed module. Với explicit named module, khai báo `provides ... with ...` trong module descriptor mới là mô hình JPMS.

Đừng đặt một provider chỉ trong `META-INF/services` trên classpath rồi trông chờ `load(childLayer, Greeter.class)` tự khám phá nó: overload theo layer **không tìm provider trong unnamed modules**.

## 8. Quy tắc provider, constructor và factory method

Với named module:

- Provider được liệt kê trong chỉ thị `provides service with provider;` của **module chứa provider**.
- Provider class/declared provider hợp lệ theo quy tắc JLS.
- Nếu dùng **provider constructor**, class provider là subtype của service và có public no-arg constructor (tường minh hoặc ngầm định).
- Named-module provider có thể dùng một public static no-arg method tên chính xác **`provider()`** với return type phù hợp. Với cách này, provider class không bắt buộc trực tiếp implements service nếu method trả service instance thích hợp.
- Consumer module cần `uses` nếu thuộc explicit named module.
- Service API phải accessible và có danh tính class nhất quán giữa các module.

Ví dụ minh họa cho provider factory method:

~~~java
package com.acme.greeter;

import com.acme.spi.Greeter;

public final class GreeterFactory {
    public static Greeter provider() {
        return new HelloGreeter();
    }
}
~~~

Với code minh họa này, descriptor có thể viết:

~~~java
provides com.acme.spi.Greeter
        with com.acme.greeter.GreeterFactory;
~~~

Đây là **phương án thay thế**, không áp dụng đồng thời trong bài chạy phần 5. Factory method phải đáp ứng đúng đặc tả, không đổi tên tự do thành `create()` mà kỳ vọng ServiceLoader tự nhận diện.

## 9. Lazy discovery, cache, reload và ordering

Một `ServiceLoader` chỉ khởi tạo provider **khi cần** trong quá trình duyệt iterator hoặc truy cập `Provider.get()` trên stream:

~~~java
ServiceLoader<Greeter> services =
        ServiceLoader.load(layer, Greeter.class);

for (Greeter service : services) {
    System.out.println(service.greet());
}
~~~

Đoạn này giả định biến `layer` đã có và mã ở trong consumer hợp lệ. Nó giúp tránh khởi tạo mọi provider ngay khi gọi `ServiceLoader.load`.

Khi chỉ muốn xem provider type trước khi tạo instance, dùng `ServiceLoader.stream()` và `ServiceLoader.Provider::type`. Khi cần instance, dùng `Provider::get`. Đừng đánh đồng việc truy vấn type metadata với việc cố ý chạy constructor của provider.

**Cache:** ServiceLoader giữ cache của các provider đã được khám phá/khởi tạo theo hợp đồng. `reload()` xóa cache để lần duyệt sau bắt đầu lại. Tuy nhiên, `reload()` **không**:

- Biên dịch lại module.
- Resolve thêm JAR vừa copy.
- Tạo child `ModuleLayer` mới.
- Thay bytecode của class đã định nghĩa.
- Unload mọi object/class/provider đang được ứng dụng giữ.

Muốn bổ sung một plugin module mới vào graph, thường phải **tạo Configuration/ModuleLayer mới** với root/plugin paths thích hợp, rồi tạo ServiceLoader mới cho layer đó.

**Ordering:** API không đảm bảo thứ tự các module trong cùng layer. Không dùng provider đầu tiên làm “mặc định” nếu kết quả phải ổn định giữa nhiều plugin, trừ khi chính bạn thiết kế quy tắc chọn/sắp xếp sau khi duyệt.

## 10. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không thấy provider | Plugin module chưa có trong layer hoặc thiếu `provides`. | Xem `child.modules()`, descriptor, root modules. |
| `ServiceConfigurationError` | Caller named module thiếu `uses`; provider sai hợp đồng/không tạo được; service không accessible. | Kiểm tra `uses`/`provides`, cause và module boundaries. |
| Resolver không tìm được module | Sai tên root/module path hoặc thiếu requires dependency. | Xem `ModuleFinder`, `Configuration.resolve`, exception. |
| `LayerInstantiationException` | Split packages hoặc mapping loader/module không hợp lệ. | Kiểm tra package ownership, lựa chọn loader strategy. |
| `ClassCastException` | SPI bị định nghĩa thành hai class runtime khác nhau. | So sánh `Greeter.class.getClassLoader()` và lớp service provider dùng. |
| Provider từ classpath không xuất hiện | Layer overload không quét unnamed module. | Dùng API classloader/TCCL hoặc chuyển provider sang named module. |
| `reload()` không thấy plugin JAR vừa thêm | Graph/layer cũ không được cập nhật. | Resolve và tạo layer mới. |
| Iteration order đổi | Có nhiều module cùng layer, không được đảm bảo thứ tự. | Chọn provider theo cấu hình/priority rõ ràng. |
| Load module thành công nhưng reflection vào implementation lỗi | Package provider không export/open cho caller. | Dùng SPI contract thay vì reflect trực tiếp vào implementation nội bộ. |

### Checklist

1. Consumer có `uses service;` trong descriptor chưa?
2. SPI module có `exports` package interface cho consumer và provider không?
3. Provider module có `provides service with impl;` và implementation hợp lệ chưa?
4. Module provider thực sự đã **resolved vào layer** chứ không chỉ tồn tại trên ổ đĩa chưa?
5. `ServiceLoader.load` được truyền **layer chứa provider hoặc descendant** chưa?
6. Có nhầm với unnamed modules hoặc file `META-INF/services` trên classpath không?
7. Có nhiều providers khiến thứ tự kết quả không xác định không?
8. `ServiceLoader.reload()` có bị hiểu lầm thành reload ModuleLayer không?
9. Exception xuất hiện tại resolution, layer creation hay khi iterator tạo provider?
10. Có giữ đúng một service interface class identity giữa host/plugin không?

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Provider nằm riêng trong child layer. Host gọi `ServiceLoader.load(ModuleLayer.boot(), Greeter.class)` có tìm được provider đó không?

**Đáp:** Không. API duyệt layer được đưa vào và ancestors, không tự duyệt descendants.

**Câu 2.** Consumer đã `requires com.acme.spi;` có còn cần `uses com.acme.spi.Greeter;`?

**Đáp:** Có đối với explicit named module gọi ServiceLoader. `requires` cung cấp readability, `uses` khai báo dịch vụ cần dùng.

**Câu 3.** Provider package phải `exports` cho host để ServiceLoader tạo object không?

**Đáp:** Không. `provides ... with ...` cho phép ServiceLoader tạo provider được khai báo hợp lệ; host giao tiếp qua SPI đã export.

**Câu 4.** Đặt một JAR chỉ có `META-INF/services` trên classpath. Overload nhận ModuleLayer có tìm nó không?

**Đáp:** Không, nó không tìm provider từ unnamed modules.

**Câu 5.** Sao chép JAR mới vào plugin folder sau khi tạo layer, gọi `reload()` là đủ?

**Đáp:** Không. Layer/configuration đã được định nghĩa. Tạo layer mới nếu muốn graph modules khác.

**Câu 6.** Khi nhiều named modules trong cùng layer cung cấp provider, thứ tự có luôn theo tên module không?

**Đáp:** Không. Thứ tự các module trong một layer không được bảo đảm.

## Tài liệu chính thức

- [ServiceLoader, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): overload `load(ModuleLayer, Class)`, lazy providers, cache, uses/provides.
- [ModuleLayer, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html): tạo layer và loader mapping.
- [Configuration, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html): resolve/resolveAndBind.
- [ModuleFinder, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleFinder.html): tìm modular JAR/exploded modules.
- [JLS Java SE 21 §7.7.4](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7.4): rules của service provision.
