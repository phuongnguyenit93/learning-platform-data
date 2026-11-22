# Layer parent và khả năng đọc module

Trong Java Platform Module System (JPMS), `ModuleLayer` cho phép một ứng dụng định nghĩa thêm các named module sau khi JVM đã khởi động. Một layer mới có thể có một hoặc nhiều parent layers. Cách tổ chức này rất hữu ích cho hệ thống plugin, công cụ phát triển, ứng dụng mở rộng chức năng theo yêu cầu và hệ thống cần tách module thành các nhóm runtime.

Một điểm quan trọng thường bị hiểu nhầm là: **Có parent layer không đồng nghĩa mọi module ở child layer đều tự động đọc mọi module của parent.**

Hãy phân biệt ba loại quan hệ:

- **Layer parent:** child layer được xây dựng dựa trên configuration của những layer cha nào?
- **Module readability:** module A có quan hệ đọc với module B hay không?
- **Class loader và accessibility:** class được nạp từ đâu, package đã được export hoặc opens đúng cách chưa?

Quan hệ parent giúp module ở child layer tham chiếu các module đã được định nghĩa trong ancestor layers khi graph cho phép. Nhưng quyền đọc không được quyết định chỉ bằng việc hai module thuộc layer cha và con.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích `ModuleLayer.boot()` và sự khác nhau giữa parent/child layer.
- Phân biệt `layer.parents()`, `layer.modules()` và `layer.findModule()`.
- Hiểu `Configuration.resolve()` và readability graph có cạnh đọc đến module ở parent configuration.
- Phân biệt lookup thành công với quyền đọc thực tế qua `Module.canRead()`.
- Tạo plugin layer với `defineModulesWithOneLoader()`.
- Sử dụng `ModuleLayer.Controller.addReads()` đúng phạm vi.
- Tách biệt vai trò của `requires`, `requires transitive`, `exports`, `opens` và class loader.
- Chẩn đoán lỗi xảy ra khi nạp module từ một layer khác.

## 1. ModuleLayer là gì?

Một `ModuleLayer` chứa các đối tượng `Module` được định nghĩa từ một `Configuration` đã được resolve. Mỗi named module thuộc một layer cụ thể tại runtime.

JVM có boot layer được tạo lúc khởi động:

~~~java
ModuleLayer boot = ModuleLayer.boot();
~~~

Boot layer chứa `java.base` và các module khác được resolve cho lần khởi chạy. Khi ứng dụng cần nạp một plugin, nó có thể tạo layer mới dùng boot layer làm cha:

~~~text
              BOOT LAYER (parent)
          +-------------------------+
          | java.base               |
          | java.logging            |
          | java.sql                |
          | ...                     |
          +-------------------------+
                      ^
                      | parent layer
                      |
          +-------------------------+
          | CHILD PLUGIN LAYER      |
          | com.acme.plugin         |
          +-------------------------+
~~~

Sơ đồ trên chỉ mô tả **vị trí** các module. Nó chưa nói `com.acme.plugin` có thể đọc những module nào.

### 1.1. Vì sao cần parent layer?

Một plugin có thể phụ thuộc API đã tồn tại trong boot layer, chẳng hạn `java.logging` hoặc một module SPI do ứng dụng chính cung cấp. Khi resolve plugin, Java có thể sử dụng các module đã có ở parent configuration, thay vì định nghĩa lại chúng trong child.

Parent layer cũng cung cấp quan hệ tìm kiếm ancestor để ứng dụng có thể tra cứu module theo tên.

### 1.2. Layer là tập module, không phải class loader

Một layer có thể định nghĩa tất cả module bằng một loader hoặc ánh xạ mỗi module sang loader riêng. Ngược lại, class loader không phải một module layer.

Ba factory phổ biến là:

~~~java
parent.defineModulesWithOneLoader(configuration, parentLoader);

parent.defineModulesWithManyLoaders(configuration, parentLoader);

parent.defineModules(configuration, moduleNameToLoader);
~~~

Dùng chung loader không gộp các module thành một module duy nhất. Mỗi module vẫn có descriptor, tên và quyền truy cập riêng.

## 2. Từ Configuration đến ModuleLayer

`Configuration` là kết quả module resolution và mô tả readability graph giữa các resolved modules. Graph này có các node là `ResolvedModule` và các cạnh chỉ quan hệ đọc.

Một cách resolve plugin dựa trên boot configuration:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleLayer boot = ModuleLayer.boot();

ModuleFinder pluginFinder =
    ModuleFinder.of(Path.of("plugins"));

Configuration childConfig =
    boot.configuration().resolve(
        pluginFinder,
        ModuleFinder.of(),
        Set.of("com.acme.plugin")
    );
~~~

Các thành phần:

- `boot.configuration()` là parent configuration.
- `pluginFinder` tìm module mới từ thư mục JAR.
- `ModuleFinder.of()` trong ví dụ là finder rỗng ở vị trí `after`.
- `Set.of("com.acme.plugin")` chứa root module mới cần resolve.

Nếu plugin khai báo `requires java.logging;` và logging đã có trong parent configuration, resolver tạo quan hệ đọc từ plugin đến logging ở parent. Java không cần tạo bản sao của module logging trong child configuration.

### 2.1. Đọc graph ở mức configuration

Trước khi tạo layer, có thể liệt kê module mới và các cạnh đọc:

~~~java
childConfig.modules().forEach(module -> {
    System.out.println("Module: " + module.name());

    module.reads().forEach(target ->
        System.out.println("  reads: " + target.name())
    );
});
~~~

Những module được đọc có thể nằm trong child configuration **hoặc** parent configuration.

### 2.2. Parent configuration phải tương ứng với parent layer

Khi định nghĩa layer bằng static API:

~~~java
ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithOneLoader(
        childConfig,
        List.of(boot),
        ClassLoader.getSystemClassLoader()
    );
~~~

`List.of(boot)` phải tương ứng với parent configuration đã dùng trong lần resolve. Nếu configuration có nhiều parent, thứ tự các parent layers phải khớp thứ tự parent configurations.

Nếu parent layers không khớp, API có thể ném `IllegalArgumentException`.

## 3. Layer parent và read edge là hai thứ khác nhau

Giả sử:

~~~text
Parent configuration:
  java.base
  java.logging
  java.sql

Child configuration:
  com.acme.plugin
~~~

Plugin descriptor là:

~~~java
module com.acme.plugin {
    requires java.logging;
}
~~~

Graph đọc ở runtime về cơ bản là:

~~~text
com.acme.plugin  --->  java.logging
         |
         +------->     java.base
~~~

Còn `java.sql` có thể thuộc boot layer nhưng plugin **không** có cạnh đọc tới SQL.

Điều này không mâu thuẫn. Parent nói về **cấu trúc layer**; readability nói về **module graph**.

### 3.1. ModuleLayer.findModule()

~~~java
Module sql = childLayer.findModule("java.sql")
    .orElseThrow();
~~~

`findModule` tìm trong layer hiện tại rồi tới các parent layers. Nếu SQL nằm ở boot layer và boot là parent của child, lời gọi trên có thể thành công.

Nhưng việc tìm ra module không có nghĩa module plugin được phép tham chiếu các kiểu của SQL trong bytecode Java thông thường.

### 3.2. Module.canRead()

~~~java
boolean readable = pluginModule.canRead(sqlModule);
~~~

`canRead()` kiểm tra readability từ module gọi tới module đích tại runtime.

Ví dụ:

~~~text
child.findModule("java.sql").isPresent()  -> true

plugin.canRead(javaSqlModule)             -> false
~~~

Đây là ví dụ cốt lõi: **module được tìm thấy từ parent nhưng không được child module đọc**.

### 3.3. Readability có hướng

`A.canRead(B)` là quan hệ có hướng; không kéo theo `B.canRead(A)`.

~~~text
com.acme.plugin ---> java.logging

plugin.canRead(logging)  = true
logging.canRead(plugin)  = false (nếu không có quan hệ ngược)
~~~

Một parent module không tự động đọc module mới được định nghĩa ở child layer.

## 4. Ví dụ chạy được: plugin layer đọc một phần boot layer

Ví dụ sử dụng:

- Host chạy trên classpath, không import trực tiếp class plugin.
- Một explicit named module `com.acme.plugin` được đóng gói thành JAR.
- Boot layer chứa `java.logging` và `java.sql`.
- Plugin yêu cầu logging nhưng không yêu cầu SQL.

Cấu trúc thư mục:

~~~text
layer-demo/
├── Host.java
├── src/
│   └── com.acme.plugin/
│       ├── module-info.java
│       └── com/acme/plugin/api/PluginEntry.java
├── plugins/
└── out/
~~~

### 4.1. Module descriptor của plugin

File `src/com.acme.plugin/module-info.java`:

~~~java
module com.acme.plugin {
    requires java.logging;
    exports com.acme.plugin.api;
}
~~~

Plugin được phép đọc module `java.logging`, và package API của nó được export. Không có dòng `requires java.sql;`.

### 4.2. Mã PluginEntry

File `src/com.acme.plugin/com/acme/plugin/api/PluginEntry.java`:

~~~java
package com.acme.plugin.api;

import java.util.logging.Logger;

public final class PluginEntry {
    private PluginEntry() {
    }

    public static void start() {
        Logger.getLogger(PluginEntry.class.getName())
              .info("Plugin started");
    }
}
~~~

Class này cho thấy plugin thật sự phụ thuộc public API của logging.

### 4.3. Host.java

Tạo file `Host.java` ở thư mục `layer-demo`:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

public class Host {
    public static void main(String[] args) {
        ModuleLayer boot = ModuleLayer.boot();

        ModuleFinder finder =
            ModuleFinder.of(Path.of("plugins"));

        Configuration config =
            boot.configuration().resolve(
                finder,
                ModuleFinder.of(),
                Set.of("com.acme.plugin")
            );

        ModuleLayer.Controller controller =
            ModuleLayer.defineModulesWithOneLoader(
                config,
                List.of(boot),
                ClassLoader.getSystemClassLoader()
            );

        ModuleLayer child = controller.layer();

        Module plugin = child.findModule("com.acme.plugin")
            .orElseThrow();

        Module logging = boot.findModule("java.logging")
            .orElseThrow();

        Module sql = boot.findModule("java.sql")
            .orElseThrow();

        System.out.println("Parent is boot: "
            + (child.parents().get(0) == boot));

        System.out.println("Child finds SQL: "
            + child.findModule("java.sql").isPresent());

        System.out.println("Boot finds plugin: "
            + boot.findModule("com.acme.plugin").isPresent());

        System.out.println("Plugin reads logging: "
            + plugin.canRead(logging));

        System.out.println("Plugin reads SQL before: "
            + plugin.canRead(sql));

        System.out.println("Logging reads plugin: "
            + logging.canRead(plugin));

        controller.addReads(plugin, sql);

        System.out.println("Plugin reads SQL after: "
            + plugin.canRead(sql));
    }
}
~~~

Ứng dụng sử dụng `child.findModule()` và `Module.canRead()` để tách biệt hai loại kiểm tra. Cuối ví dụ, controller bổ sung một cạnh đọc từ plugin tới SQL.

### 4.4. Biên dịch và đóng gói

Đứng tại thư mục `layer-demo`:

~~~bash
javac --module-source-path src -d out -m com.acme.plugin
~~~

Tạo thư mục plugin nếu chưa có:

~~~bash
mkdir plugins
~~~

Đóng gói module JAR:

~~~bash
jar --create --file plugins/com.acme.plugin.jar \
    -C out/com.acme.plugin .
~~~

Nếu dùng Windows PowerShell, có thể viết một dòng:

~~~powershell
jar --create --file plugins/com.acme.plugin.jar -C out/com.acme.plugin .
~~~

Biên dịch Host:

~~~bash
javac -d host-out Host.java
~~~

### 4.5. Chạy ví dụ

~~~bash
java --add-modules java.logging,java.sql \
     -cp host-out Host
~~~

Trên Windows PowerShell:

~~~powershell
java --add-modules java.logging,java.sql -cp host-out Host
~~~

`--add-modules java.logging,java.sql` đảm bảo hai module JDK được resolve vào boot layer, để `boot.findModule()` tìm thấy chúng.

Plugin JAR **không** được đưa lên module path của lệnh khởi chạy này. Host sẽ tìm plugin trong thư mục `plugins` bằng `ModuleFinder.of()` rồi định nghĩa layer mới trong runtime.

### 4.6. Kết quả minh họa

~~~text
Parent is boot: true
Child finds SQL: true
Boot finds plugin: false
Plugin reads logging: true
Plugin reads SQL before: false
Logging reads plugin: false
Plugin reads SQL after: true
~~~

Diễn giải:

1. Child có boot làm parent.
2. Child tìm được SQL do `findModule()` tìm trong parent.
3. Boot không tự tìm ngược xuống child.
4. Plugin đọc được logging nhờ `requires java.logging;`.
5. Plugin không tự đọc SQL dù SQL nằm trong parent.
6. Logging không tự đọc ngược plugin.
7. `addReads(plugin, sql)` thêm một cạnh đọc ở runtime.

Kết quả này cho thấy chính xác tại sao phải phân biệt **tìm thấy module** với **module readability**.

## 5. ModuleLayer.Controller.addReads() hoạt động ra sao?

Khi tạo layer bằng static factory, kết quả trả về là `ModuleLayer.Controller`:

~~~java
ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithOneLoader(
        config,
        List.of(boot),
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer layer = controller.layer();
~~~

Controller có thể điều chỉnh một số quan hệ runtime của các module được định nghĩa trong layer mà nó điều khiển.

Các API quan trọng:

| API | Ý nghĩa |
|---|---|
| `controller.layer()` | Lấy layer mới |
| `controller.addReads(source, target)` | Bổ sung cạnh đọc từ source tới target |
| `controller.addExports(source, packageName, target)` | Export package của source cho target |
| `controller.addOpens(source, packageName, target)` | Mở package của source cho deep reflection từ target |

`source` phải là module thuộc layer được controller quản lý khi thực hiện các thay đổi tương ứng. Controller của child layer không tự có quyền chỉnh sửa tất cả module nằm trong boot layer.

### 5.1. addReads không thay đổi module-info.java

Ví dụ:

~~~java
controller.addReads(plugin, sql);
~~~

Có thể làm `plugin.canRead(sql)` chuyển từ `false` sang `true`.

Tuy nhiên:

- File `module-info.class` trong JAR không thay đổi.
- Compiler không được chạy lại.
- Dependency mới không được tự động thêm vào bản build.
- Code import API của SQL lúc compile vẫn cần readability hợp lệ ở compile-time.

Nếu SQL là dependency cố định mà plugin dùng trực tiếp, cách thiết kế bền vững là khai báo:

~~~java
module com.acme.plugin {
    requires java.sql;
}
~~~

thay vì dựa vào runtime patch cho một dependency đáng lẽ nên nằm trong descriptor.

### 5.2. addReads không giải quyết mọi lỗi

Một cạnh đọc mới không tự động:

- Tìm và resolve module không tồn tại trong configuration.
- Export package nội bộ của module đích.
- Mở private field cho deep reflection.
- Sửa lỗi class loader hoặc thiếu class/JAR.
- Thay thế cơ chế bảo mật để chạy plugin không tin cậy.

Đó là lý do `addReads` nên dùng cho các tình huống tích hợp động có chủ đích.

## 6. Requires và requires transitive qua ranh giới layer

Giả sử parent layer chứa:

~~~text
com.acme.spi
com.acme.model
~~~

Module SPI có descriptor:

~~~java
module com.acme.spi {
    requires transitive com.acme.model;
    exports com.acme.spi;
}
~~~

Plugin ở child layer có:

~~~java
module com.acme.plugin {
    requires com.acme.spi;
}
~~~

Readability có thể lan từ plugin tới model nhờ `requires transitive` trong descriptor SPI.

~~~text
com.acme.plugin
       |
       | requires
       v
com.acme.spi
       |
       | requires transitive
       v
com.acme.model
~~~

Sự lan truyền có thể đi qua parent configuration; nó không đòi hỏi mọi module phải ở cùng một layer.

### 6.1. Điều kiện bổ sung: exports

Nếu plugin dùng một public type của `com.acme.model`, package chứa kiểu đó vẫn cần được export phù hợp. `requires transitive` cho phép đọc module, **không tự export mọi package** của module được đọc.

### 6.2. requires static

Với:

~~~java
module com.acme.plugin {
    requires static com.acme.optional;
}
~~~

module optional cần cho compile-time, nhưng có thể không được resolve ở runtime nếu không thực sự cần đến. Parent layer không bắt buộc chứa module optional. Kiểm tra graph thực tế thay vì suy rằng parent luôn cung cấp mọi dependency đã thấy trong môi trường build.

## 7. Quan hệ đọc khác exports và opens

Hai module có thể có cạnh đọc nhưng việc truy cập class vẫn thất bại.

Giả sử contract module ở parent:

~~~java
module com.acme.contract {
    exports com.acme.contract.api;
}
~~~

Plugin:

~~~java
module com.acme.plugin {
    requires com.acme.contract;
}
~~~

Plugin có thể sử dụng public type đủ điều kiện trong `com.acme.contract.api`. Nhưng nếu nó import class từ `com.acme.contract.internal` mà contract không export package đó, compiler có thể từ chối.

### 7.1. Qualified export

Parent module có thể export một package chỉ cho plugin:

~~~java
module com.acme.contract {
    exports com.acme.contract.spi to com.acme.plugin;
}
~~~

Danh sách sau `to` là **module name**, không phải tên layer hay class loader. Qualified export không tự tạo readability, nên plugin vẫn cần một quan hệ đọc hợp lệ.

### 7.2. Opens cho deep reflection

Nếu một framework cần truy cập member không public:

~~~java
module com.acme.contract {
    opens com.acme.contract.model to com.acme.framework;
}
~~~

`opens` phục vụ reflective access; `exports` phục vụ public API access. Cả hai độc lập với cấu trúc parent/child layer.

### 7.3. Bảng phân biệt

| Câu hỏi | Cơ chế trả lời |
|---|---|
| Layer A có cha nào? | `ModuleLayer.parents()` |
| Module tên X ở layer này/ancestor không? | `ModuleLayer.findModule(name)` |
| Module A đọc B được không? | `Module.canRead(B)` |
| Package được công bố cho module dùng không? | `exports` và access modifiers |
| Deep reflection vào package có được phép không? | `opens` hoặc mở package phù hợp |
| Class được tải bởi loader nào? | `Module.getClassLoader()` / `ModuleLayer.findLoader()` |

Không nên thay thế một phép kiểm tra bằng phép kiểm tra khác.

## 8. Parent layer khác parent class loader

Trong factory:

~~~java
ModuleLayer.defineModulesWithOneLoader(
    config,
    List.of(boot),
    ClassLoader.getSystemClassLoader()
);
~~~

Hai tham số cuối có mục đích khác nhau:

- `List.of(boot)` xác định parent layer.
- `ClassLoader.getSystemClassLoader()` xác định class loader cha của loader mới được tạo.

Layer hierarchy thuộc mô hình JPMS. Class-loader delegation thuộc cơ chế nạp class. Hai cơ chế có liên hệ trong runtime nhưng không phải cùng một graph.

Ví dụ, một class loader có thể tìm đến class thuộc parent loader, song điều này không có nghĩa module đang chạy luôn có quyền truy cập class đó theo JPMS.

### 8.1. One-loader và many-loaders

| Phương thức | Cách ánh xạ module |
|---|---|
| `defineModulesWithOneLoader` | Các module mới dùng chung một class loader |
| `defineModulesWithManyLoaders` | Mỗi module mới có class loader riêng |
| `defineModules` | Ứng dụng cung cấp ánh xạ module name → loader |

Dù dùng một loader hay nhiều loader, các module vẫn giữ ranh giới readability và package access của riêng mình.

### 8.2. Lỗi class loading không đồng nhất với thiếu read edge

`ClassNotFoundException` có thể đến từ loader không tìm thấy class. `NoClassDefFoundError` có thể xuất hiện khi runtime không thể nạp/link class phụ thuộc. `IllegalAccessError` lại có thể liên quan tới quyền truy cập module hoặc Java access.

Khi debug, hãy tách thứ tự:

1. Module có được resolve chưa?
2. Class có tồn tại trong đúng artifact chưa?
3. Loader nào được dùng?
4. Module có readability phù hợp không?
5. Package có export/open phù hợp không?

## 9. Instance method và static method tạo layer

Có hai cách phổ biến khi chỉ dùng một parent.

### 9.1. Instance method

~~~java
ModuleLayer child =
    boot.defineModulesWithOneLoader(
        config,
        ClassLoader.getSystemClassLoader()
    );
~~~

Phương thức này trả về trực tiếp một `ModuleLayer`, và receiver `boot` là parent layer.

### 9.2. Static method

~~~java
ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithOneLoader(
        config,
        List.of(boot),
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer child = controller.layer();
~~~

Static method cho phép truyền danh sách parent layers và trả về controller để quản lý quan hệ module runtime.

Nếu không cần chỉnh read/export/open, instance method thường ngắn gọn hơn trong trường hợp một parent.

## 10. Layer nhiều cấp và nhiều parent

Layer graph có thể có nhiều cấp:

~~~text
        Boot
          ^
          |
    Shared API layer
          ^
          |
      Plugin layer
~~~

Trong trường hợp này plugin có thể tìm module từ cả shared API layer và boot layer bằng `findModule()` vì phép tìm đi qua chuỗi ancestor layers.

Nhưng việc plugin có đọc một module ancestor cụ thể hay không vẫn dựa vào readability graph hoặc một thay đổi runtime hợp lệ.

### 10.1. Parent nhiều hơn một

Các static factory chấp nhận:

~~~java
List<ModuleLayer> parents =
    List.of(firstParent, secondParent);
~~~

Khi có nhiều parent, phải tạo configuration bằng những parent configurations tương ứng, theo đúng thứ tự. Không thể tự thêm một parent layer ở thời điểm define nếu configuration không được resolve từ parent đó.

Một layer có nhiều parent không khiến tất cả module của các parent được hợp nhất thành một module.

### 10.2. Search đi từ con lên cha

~~~java
child.findModule("com.acme.plugin");
child.findModule("java.logging");
~~~

Có thể tìm module plugin và logging nếu chúng nằm trong child/ancestor phù hợp.

Ngược lại:

~~~java
boot.findModule("com.acme.plugin");
~~~

không tự tìm tất cả descendant layers. Một ứng dụng quản lý plugin nên giữ tham chiếu tới layer mà nó tạo.

## 11. ServiceLoader trong child layer

Một mô hình thực tế là module SPI nằm ở parent layer, còn implementation nằm ở child layer:

~~~text
Parent layer:
  com.acme.spi (interface Greeter)

Child layer:
  com.acme.greeter.impl (provider implementation)
~~~

Provider descriptor:

~~~java
module com.acme.greeter.impl {
    requires com.acme.spi;

    provides com.acme.spi.Greeter
        with com.acme.greeter.impl.DefaultGreeter;
}
~~~

Host có thể dùng:

~~~java
ServiceLoader<Greeter> providers =
    ServiceLoader.load(childLayer, Greeter.class);
~~~

Với thiết kế phù hợp, ServiceLoader có thể tìm provider được định nghĩa trong child layer mà host không cần import trực tiếp implementation class.

Các điều kiện cần chú ý:

- SPI API được export từ module sở hữu nó.
- Provider module có quan hệ đọc tới SPI.
- Provider được định nghĩa trong layer phù hợp.
- Module của caller khai báo `uses` nếu là named module và sử dụng service qua API tương ứng.
- Tránh nhầm việc “parent không đọc child” với việc không thể khám phá provider thông qua ServiceLoader.

## 12. Lỗi thường gặp khi tạo parent/child layer

### 12.1. Configuration không khớp parent

Triệu chứng: `IllegalArgumentException` khi gọi factory.

Nguyên nhân: configuration được resolve với parent configuration A nhưng khi define lại truyền layer có configuration khác.

Cách xử lý: theo dõi chính xác parent configuration lúc resolve và truyền parent layer tương ứng, giữ đúng thứ tự nếu có nhiều parent.

### 12.2. Module không tìm thấy lúc resolve

Ví dụ:

~~~text
java.lang.module.FindException:
Module com.acme.contract not found,
required by com.acme.plugin
~~~

Kiểm tra:

- Module contract có ở parent configuration không?
- Finder có tìm contract trong module path/thư mục được cung cấp không?
- Tên module có chính xác không?
- Artifact có chứa `module-info.class` đúng không?

Không thể dùng `addReads()` để sửa lỗi khi configuration chưa resolve thành công.

### 12.3. findModule có kết quả nhưng canRead false

Đây không nhất thiết là lỗi. Nó chỉ cho thấy module có thể được tìm thấy qua cấu trúc layer nhưng chưa có quan hệ đọc theo graph hiện hành.

Kiểm tra `requires`, `requires transitive` và nhu cầu bổ sung runtime read edge.

### 12.4. Đọc module nhưng không truy cập được package

Nếu module đích không export package cho plugin, `canRead() == true` chưa đủ.

Kiểm tra descriptor và access modifiers. Nếu cần deep reflection, xác định package/module được mở bằng `opens` hoặc cơ chế tương ứng.

### 12.5. Module loader không thấy class

Nếu factory tạo layer thành công nhưng không nạp được entry point:

- Kiểm tra file JAR có chứa class theo đường dẫn package không.
- Kiểm tra loader trả về bởi `child.findLoader("com.acme.plugin")`.
- Kiểm tra sử dụng đúng layer/loader thay vì nhầm system class loader.
- Phân biệt lỗi class loading với lỗi readability và package accessibility.

## 13. Công cụ và API chẩn đoán

### 13.1. Xem descriptor của plugin JAR

~~~bash
jar --describe-module --file plugins/com.acme.plugin.jar
~~~

Công cụ giúp xác nhận tên module, các `requires` và `exports` mà artifact thực sự chứa.

### 13.2. Xem module resolution ở boot layer

~~~bash
java --show-module-resolution \
     --add-modules java.logging,java.sql \
     -cp host-out Host
~~~

Tùy chọn này hiển thị graph trong quá trình khởi chạy. Graph được tạo thêm bên trong `Host.main()` không tự động xuất hiện đầy đủ trong output khởi động ban đầu.

### 13.3. Xem các module thuộc child trực tiếp

~~~java
child.modules().forEach(module ->
    System.out.println(module.getName())
);
~~~

`child.modules()` chỉ trả module được định nghĩa trực tiếp trong child, không phải toàn bộ module ở parent.

### 13.4. Xem các module mà child configuration đọc

~~~java
child.configuration().modules().forEach(module -> {
    System.out.println(module.name());

    module.reads().forEach(target ->
        System.out.println("  -> " + target.name())
    );
});
~~~

Đây là graph từ quá trình resolution, hữu ích để đối chiếu với `Module.canRead()` ở runtime.

### 13.5. Xem class loader và layer

~~~java
System.out.println(plugin.getLayer());
System.out.println(plugin.getClassLoader());
System.out.println(child.parents());
~~~

Các API giúp xác định module thuộc layer nào và dùng class loader nào. Chúng không thay thế phép kiểm tra readability.

## 14. Quy trình thiết kế plugin layer

Để thiết kế một hệ thống module layer dễ kiểm soát:

1. Xác định các API/SPI dùng chung và đặt chúng trong module được quản lý ổn định ở parent layer.
2. Viết descriptor cho plugin với `requires` tới đúng API module.
3. Chỉ export package plugin API thật sự cần công bố.
4. Đóng gói plugin thành modular JAR có tên module rõ ràng.
5. Tạo `ModuleFinder` từ thư mục chứa plugin.
6. Resolve child configuration dựa trên configuration của parent layer dự kiến.
7. Define layer bằng factory phù hợp và parent layers tương ứng.
8. Kiểm tra `layer.modules()`, `layer.parents()` và `Module.canRead()`.
9. Kiểm tra exports/opens và cách host tìm entry point hoặc service provider.
10. Chỉ dùng Controller để chỉnh quan hệ runtime khi có lý do kiến trúc rõ ràng.

Không nên tạo layer chỉ với mục đích né module encapsulation. Layer giúp tổ chức và nạp module động; nó không phải sandbox bảo mật.

## 15. Các hiểu lầm cần tránh

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| Child layer đọc mọi module trong parent | Không. Readability theo graph hoặc runtime change |
| `findModule()` thành công nghĩa `canRead()` true | Không. Lookup khác readability |
| Class loader tìm thấy class nghĩa có quyền sử dụng | Không. Accessibility vẫn có thể bị JPMS từ chối |
| Một class loader cho nhiều module nghĩa module graph mất ý nghĩa | Không. Named modules vẫn có descriptor riêng |
| `addReads()` sửa được mọi lỗi module path | Không. Nó không tìm module còn thiếu |
| `addReads()` tự export toàn bộ package | Không. Exports/opens là cơ chế riêng |
| Parent module tự động đọc child module | Không. Readability có hướng |
| ModuleLayer tự cô lập plugin không tin cậy | Không. Cần kiến trúc bảo mật phù hợp |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Child layer có boot làm parent, `child.findModule("java.sql")` trả về một module. Plugin có chắc đọc được SQL không?

**Trả lời:** Không. `findModule()` tìm module; `plugin.canRead(sql)` kiểm tra readability.

**Câu 2.** Plugin khai báo `requires java.logging;` và logging nằm ở parent configuration. Plugin có thể đọc logging không?

**Trả lời:** Có. Graph resolution tạo quan hệ đọc tới module logging ở parent.

**Câu 3.** Plugin đọc được logging có nghĩa logging đọc ngược plugin?

**Trả lời:** Không. Readability là quan hệ có hướng.

**Câu 4.** Muốn lấy tập module thuộc trực tiếp child layer, nên dùng gì?

**Trả lời:** `child.modules()`, thay vì `child.findModule()` vì findModule có thể tìm cả ancestor.

**Câu 5.** Static factory `ModuleLayer.defineModulesWithOneLoader` trả về gì?

**Trả lời:** `ModuleLayer.Controller`; gọi `controller.layer()` để lấy layer được tạo.

**Câu 6.** `controller.addReads(plugin, sql)` có thay đổi `module-info.java` của plugin không?

**Trả lời:** Không. Nó tạo read edge ở runtime, không sửa descriptor và không giúp source vốn thiếu `requires` tự compile trước đó.

**Câu 7.** Plugin đọc được contract nhưng compiler/runtime từ chối package internal. Vì sao?

**Trả lời:** Contract có thể chưa export package đó cho plugin hoặc class/member chưa đủ quyền truy cập. Readability không thay thế exports.

**Câu 8.** Parent class loader và parent layer có giống nhau không?

**Trả lời:** Không. Parent layer liên quan structure của module configurations; parent class loader liên quan tới delegation khi nạp class.

**Câu 9.** Vì sao cần giữ đúng thứ tự parent layers khi tạo layer có nhiều parent?

**Trả lời:** Vì danh sách phải tương ứng với parent configurations đã dùng khi resolve.

**Câu 10.** Module provider ở child có thể cung cấp service cho host dùng SPI ở parent mà host import trực tiếp provider class không?

**Trả lời:** Có thể thiết kế thông qua `ServiceLoader.load(childLayer, ServiceType.class)` với đúng module/SPI/provider configuration.

## Tổng kết

Khi làm việc với nhiều `ModuleLayer` trong JPMS, hãy phân biệt rõ:

- **Parent layer:** tổ chức các nhóm module và cho phép tìm kiếm qua ancestor.
- **Readability graph:** quyết định module nào có cạnh đọc tới module nào, kể cả các cạnh đi từ child tới parent.
- **Package accessibility:** `exports`, `opens` và các quy tắc Java quyết định sử dụng API và reflection.
- **Class loading:** xác định nơi nạp class, nhưng không tự thay thế các quy tắc module access.

Quy trình chẩn đoán hữu ích là: **xác định layer chứa module → kiểm tra parent configurations → xem module có được resolve → kiểm tra `findModule()` → kiểm tra `canRead()` → kiểm tra exports/opens → kiểm tra class loader**. Hiểu đúng các tầng này giúp xây dựng plugin layer hoạt động ổn định mà không dựa vào các giả định sai về quan hệ layer cha–con.