# Giới hạn của sơ đồ ba loader khi làm việc với named module

## 1. Vấn đề: sơ đồ ba ClassLoader giải thích được gì?

Trong các bài nhập môn Java, ClassLoader thường được vẽ như một chuỗi:

~~~text
Bootstrap ClassLoader
          ^
          |
Platform ClassLoader
          ^
          |
Application / System ClassLoader
~~~

Sơ đồ này **hữu ích để nhận diện ba loader tích hợp** trong Java 9+ và hình dung quan hệ *parent* phổ biến. Tuy nhiên, khi một chương trình dùng **named module** (module có tên, thuộc Java Platform Module System — JPMS), sơ đồ trên **không đủ** để giải thích lớp nào nằm trong module nào, module nào đọc được module nào, package nào được phép truy cập, hoặc ClassLoader nào thực sự định nghĩa một lớp.

Các giới hạn quan trọng:

1. **Module không đồng nghĩa ClassLoader.** Một ClassLoader có thể định nghĩa lớp của nhiều named module; một named module có ClassLoader tương ứng, nhưng không bắt buộc có một loader riêng.
2. **Không chỉ có ba ClassLoader trong toàn bộ JVM.** Ba tên trong sơ đồ là những loader **tích hợp**. Các `ModuleLayer` do ứng dụng tạo thêm có thể dùng những loader mới; ứng dụng cũng có thể dùng custom ClassLoader ngoài cơ chế này.
3. **Đồ thị module khác cây quan hệ parent của loader.** `requires`/readability, `exports`, `opens` và cấu hình `ModuleLayer` không được mô tả bằng ba mũi tên trên.
4. **Named module trong boot layer không có nghĩa mọi lớp đều do cùng một loader định nghĩa.** Các module được gán vào những built-in loader tùy vai trò và cấu hình runtime; không nên suy ra loader của mọi module chỉ từ tên module.
5. **“Tìm được class” và “được phép truy cập class” là hai câu hỏi khác nhau.** Loader xử lý tra cứu/định nghĩa; JPMS còn có quy tắc readability và package accessibility.

Mục tiêu của bài là biết lúc nào sơ đồ ba loader còn hữu ích, lúc nào phải mở rộng cách quan sát sang **module + layer + loader + access rules**, và đọc được bằng chứng runtime qua Java 17+.

## 2. Nhắc lại các khái niệm trước khi xem giới hạn

### 2.1. Ba loader tích hợp nói về cơ chế định nghĩa lớp

| Built-in loader | Vai trò thường gặp | Quan sát API |
|---|---|---|
| **Bootstrap** | Loader do JVM tích hợp; định nghĩa các lớp rất cơ bản, ví dụ `java.lang.String` từ `java.base` | `String.class.getClassLoader() == null` thường trả về `true`; `null` là cách API biểu diễn bootstrap |
| **Platform** | Định nghĩa nhiều lớp thuộc các module nền tảng; đôi khi cần ủy quyền không thuần một chiều để hỗ trợ module nâng cấp | `ClassLoader.getPlatformClassLoader()` |
| **Application/System** | Thường định nghĩa lớp trên application classpath, application module path và lớp công cụ JDK liên quan | `ClassLoader.getSystemClassLoader()` |

Trong môi trường khởi chạy Java thông thường, application loader có platform loader là parent hoặc ancestor; platform loader liên quan bootstrap. Nhưng **parent delegation** chỉ là một chiều giải thích việc tìm class, không phải bản đồ module.

Đặc biệt, [Java 21 `ClassLoader` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html) nêu rằng platform loader có thể cần ủy quyền sang loader khác, kể cả application loader, trong một số trường hợp module được nâng cấp. Do đó, phát biểu “mọi lần tìm class đều đi đúng ba tầng từ dưới lên rồi xuống” là giản lược quá mức đối với JPMS.

### 2.2. Named module, unnamed module và automatic module

- **Named module** là module có tên trong JPMS, chẳng hạn `java.base` hay `lab.app`. Nó có descriptor (mô tả module); descriptor có thể là khai báo tường minh bằng `module-info.java` hoặc được tạo cho **automatic module** từ một JAR trên module path.
- **Unnamed module** gắn với một ClassLoader và chứa các lớp mà loader định nghĩa từ classpath, ngoài named modules. Mỗi ClassLoader có unnamed module của chính nó; `Class.getModule().isNamed()` giúp xác định một lớp đang thuộc named hay unnamed module.
- **Automatic module** vẫn là **named module**. Nó không phải “module vô danh”, và không được hiểu là một loader mới. Những cơ chế đọc/xuất của automatic module có quy tắc riêng trong JPMS.

Hai đường truyền lớp thường gặp:

~~~text
Classpath
  -> các lớp ứng dụng thông thường
  -> unnamed module của defining loader

Module path + module resolution
  -> named modules được resolve
  -> mỗi module ánh xạ tới ClassLoader trong layer
  -> readability / exports / opens quyết định quyền truy cập
~~~

`--module-path` không tự bảo đảm **mọi** module trong đường dẫn đã được resolve. Runtime phải tạo một cấu hình module từ root modules và quan hệ phụ thuộc. Một module JAR có mặt trên ổ đĩa nhưng không được resolve không mặc nhiên trở thành module trong graph đang chạy.

### 2.3. Hai loại “cây” cần tách biệt

**Loader delegation** mô tả đường tìm kiếm/ủy quyền khi load class. **Module readability** mô tả việc một module có quyền đọc module khác hay không; thêm `exports`, `opens` để điều khiển phạm vi package có thể sử dụng.

Ví dụ module A khai báo `requires module.b;`: điều đó thể hiện quan hệ phụ thuộc/readability. Nó **không có nghĩa** loader của A bắt buộc là con trực tiếp của loader của B, cũng không tạo một ClassLoader mới cho module B.

## 3. Mô hình đúng hơn: ModuleLayer + Module + ClassLoader

### 3.1. ModuleLayer ánh xạ module tới loader

`ModuleLayer` là lớp biểu diễn một **layer các module**. Mỗi layer được tạo từ một `Configuration` (đồ thị module đã resolve) và cách ánh xạ mỗi module vào một ClassLoader.

Một JVM Java 9+ có **boot layer** (lấy bằng `ModuleLayer.boot()`). Boot layer chứa `java.base` và những module được resolve lúc JVM khởi động. Các module trong boot layer được ánh xạ đến bootstrap hoặc các built-in loaders.

Ứng dụng có thể tạo layer bổ sung. Trong Java 17+, những API quan trọng gồm:

| API | Ý nghĩa thực tế |
|---|---|
| `ModuleLayer.boot()` | Layer được tạo khi JVM khởi động |
| `ModuleLayer.findModule("name")` | Tìm module trong layer hoặc các parent layers; trả về `Optional<Module>` |
| `ModuleLayer.findLoader("name")` | Tìm ClassLoader của named module tương ứng trong layer/parent layers |
| `ModuleLayer.defineModulesWithOneLoader(...)` | Tạo layer với **một loader mới** cho các module trong configuration |
| `ModuleLayer.defineModulesWithManyLoaders(...)` | Tạo layer với **mỗi module một loader mới** |
| `ModuleLayer.defineModules(...)` | Tạo layer với ánh xạ module→ClassLoader do ứng dụng cung cấp, cho tình huống nâng cao |
| `Module.getLayer()` | Cho biết layer chứa named module; với module không thuộc layer có thể là `null` |
| `Class.getModule()` | Trả về runtime `Module` của lớp; áp dụng cả named/unnamed module |

Chính API `defineModulesWithOneLoader` chứng minh **nhiều named module có thể chia sẻ một loader**; `defineModulesWithManyLoaders` chứng minh **có thể có thêm nhiều loader bên ngoài ba loader tích hợp**.

### 3.2. Minh họa hai cách tạo layer

~~~text
Boot layer
  java.base --> bootstrap loader
  ...       --> built-in loaders (theo mapping của runtime)

                    |
                    v
          Layer ứng dụng tạo thêm

Cách A: defineModulesWithOneLoader
  plugin.alpha ---------+
                        +--> loader L (loader mới)
  plugin.beta ----------+

Cách B: defineModulesWithManyLoaders
  plugin.alpha ------------> loader L1 (loader mới)
  plugin.beta -------------> loader L2 (loader mới)
~~~

Hình minh họa thể hiện **quy tắc mapping của hai API**, không dự đoán cấu hình cụ thể của mọi JDK. `L`, `L1`, `L2` là tên đại diện; Java không hứa lớp loader sẽ có tên hoặc `toString()` cố định như vậy.

### 3.3. Layer parent không đồng nghĩa ClassLoader parent

Một layer có **parent layer** theo ngữ nghĩa cấu hình/module lookup. Loader có `getParent()` theo ngữ nghĩa ủy quyền. Hai quan hệ này có thể được thiết kế tương thích nhưng **không phải cùng một quan hệ**.

Đặc biệt, API `defineModulesWithOneLoader(cf, parentLoader)` nhận rõ một `parentLoader` để gắn cho loader **mới tạo**, còn layer parent được xác định từ ngữ cảnh tạo layer. Đừng suy ra “module layer là con thì mọi loader trong đó chắc chắn là con của loader gán cho module trong parent layer”.

## 4. Những giới hạn thực tế của sơ đồ ba loader

### Giới hạn 1 — Không xác định được module nào chứa class

`Class#getClassLoader()` cho biết defining loader; nó **không tự trả lời** lớp đó thuộc named module nào.

Ví dụ, nếu `lab.app.Main` và `lab.app.Helper` cùng do application loader định nghĩa, điều đó chưa đủ kết luận chúng thuộc cùng một named module. Ngược lại, hai module khác nhau trong boot layer hoặc một custom layer có thể được map vào cùng loader.

Hãy đọc **cả**:

~~~java
Class<?> type = java.lang.String.class;
Module module = type.getModule();
ClassLoader loader = type.getClassLoader();
System.out.println(module.getName());
System.out.println(module.isNamed());
System.out.println(loader == null);
~~~

Đoạn trên là **minh họa đặt trong một phương thức Java**, không phải chương trình độc lập. Đối với `String` trên JDK phổ biến: module là `java.base`, module có tên, và loader bootstrap được biểu diễn bằng `null`.

### Giới hạn 2 — Không diễn đạt readability, exports và opens

Ba loader không cho biết một module có quyền dùng public API trong module khác hay không. Ví dụ:

~~~java
module lab.service {
    exports lab.service.api;
}
~~~

Module khác muốn dùng API trên phải có readability phù hợp, ví dụ `requires lab.service;` trong descriptor và dependency được resolve. Package `lab.service.internal` nếu không exported sẽ không trở thành public API khả dụng chỉ vì lớp có thể được một loader tìm thấy.

Tóm tắt:

- `requires` tạo quan hệ đọc ở mức module (với các biến thể như `transitive`/`static`).
- `exports` cho phép truy cập public/protected API tương ứng trong package theo quy tắc JPMS; có thể export có điều kiện tới module cụ thể.
- `opens` cho phép dạng **deep reflection** thích hợp tới package; không tương đương với việc mở rộng static compile-time access như `exports`.
- **ClassLoader** giải quyết việc tìm/định nghĩa class; **JPMS** thêm quy tắc kiểm soát truy cập.

Một `IllegalAccessError` hoặc `InaccessibleObjectException` liên quan module/package không được mặc định xử lý bằng việc đổi parent loader. Cần kiểm tra `requires`, `exports`, `opens` và cách ứng dụng được khởi chạy.

### Giới hạn 3 — Không thấy module layer do framework/plugin tạo

JVM có thể có **nhiều layer**; các layer mới tạo thường dành cho plugin, ứng dụng chia phần hoặc hệ thống cần quản lý tập module động. Sơ đồ ba built-in loaders không có chỗ cho loader của các layer này.

Có thể có:

- Các module trong **cùng một layer** chia sẻ một loader.
- Các module trong **cùng một layer** được gán mỗi module một loader.
- Các layer khác nhau chứa module có cùng tên theo cấu hình riêng, nhưng đó là các runtime module object khác nhau; không nên kết luận hai class là cùng kiểu chỉ nhờ tên module hoặc tên binary class.

Tại runtime, định danh class gắn với **binary name + defining class loader**. Module membership/layer là thông tin bổ sung cần kiểm tra khi debug, đặc biệt khi hai plugin cùng chứa lớp có tên giống nhau.

### Giới hạn 4 — Không ánh xạ cố định “module A → platform, module B → system”

Trong boot layer, các module platform/JDK/application được định nghĩa bởi các loader tương ứng với cấu hình thực tế. **Không có quy tắc đáng tin cậy rằng mọi named module đều thuộc system loader, hoặc mọi module mang tiền tố `java.` đều thuộc bootstrap loader.** Chi tiết chọn loader còn phụ thuộc nền tảng, phiên bản JDK, module resolution và cơ chế nâng cấp module.

Đừng gán loader dựa trên tên module. Thay vào đó, hỏi runtime:

~~~java
Class<?> clazz = java.sql.Driver.class;
System.out.println(clazz.getModule().getName());
System.out.println(clazz.getClassLoader());
~~~

Đoạn trên là **mã minh họa**. Chuỗi xuất ra bởi `getClassLoader()` là implementation detail; không yêu cầu nó giống nhau giữa JDK/vendor. Ngoài ra, module `java.sql` phải có mặt trong cấu hình runtime sử dụng lớp này.

### Giới hạn 5 — Parent-first là nguyên tắc mặc định, không phải toàn bộ JPMS

Mô hình `ClassLoader.loadClass` mặc định thường kiểm tra lớp đã nạp, ủy quyền cho parent, rồi dùng `findClass`. Tuy vậy, việc ánh xạ module đến loader và các trường hợp đặc biệt của built-in loaders tạo thêm chi tiết so với “cứ tìm từng tầng theo ba ô”.

Chẳng hạn, tài liệu `ClassLoader` của Java 21 ghi rõ **platform loader có thể cần ủy quyền tới một loader khác, kể cả application loader**, khi module nâng cấp đọc module được định nghĩa bởi các loader nằm ngoài chuỗi tổ tiên thông thường. Custom loader còn có thể được thiết kế với chiến lược không giống mặc định.

Vì thế, đừng dùng sơ đồ ba loader để chứng minh thứ tự nạp của mọi class trong một modular application.

## 5. Thực hành A — Một named module trong boot layer

Thực hành này chứng minh **named module + boot layer + loader mapping** là ba thông tin khác nhau có thể quan sát trực tiếp.

Tạo cấu trúc:

~~~text
project/
  src/
    lab.app/
      module-info.java
      lab/
        app/
          Main.java
~~~

Tệp **`src/lab.app/module-info.java`**:

~~~java
module lab.app {
}
~~~

Tệp **`src/lab.app/lab/app/Main.java`**:

~~~java
package lab.app;

public class Main {
    public static void main(String[] args) {
        Module module = Main.class.getModule();

        System.out.println("module=" + module.getName());
        System.out.println("named=" + module.isNamed());
        System.out.println("bootLayer="
                + (module.getLayer() == ModuleLayer.boot()));
        System.out.println("loaderMatches="
                + (Main.class.getClassLoader()
                == ModuleLayer.boot().findLoader("lab.app")));
        System.out.println("javaBase="
                + String.class.getModule().getName());
    }
}
~~~

Từ thư mục **`project`**, biên dịch và chạy bằng JDK 17+:

~~~sh
javac --release 17 -d mods/lab.app src/lab.app/module-info.java src/lab.app/lab/app/Main.java
java --module-path mods --module lab.app/lab.app.Main
~~~

Lưu ý: `javac -d` tạo cây thư mục output khi cần; ở đây `mods/lab.app` là thư mục chứa lớp của module `lab.app` theo *exploded module* layout.

**Stdout đã kiểm chứng với chương trình trên:**

~~~text
module=lab.app
named=true
bootLayer=true
loaderMatches=true
javaBase=java.base
~~~

**Giải thích:**

1. `module=lab.app` đến từ **`Main.class.getModule().getName()`**, không phải tên class loader.
2. `named=true` cho thấy `Main` thuộc named module được khai báo bởi `module-info.java`.
3. Khi launcher khởi động bằng `--module lab.app/...`, module main này thuộc **boot layer**.
4. `findLoader("lab.app")` cho loader ánh xạ từ module `lab.app`; so sánh với defining loader của `Main` là `true`.
5. `java.base` cũng là named module, nhưng điều đó **không đòi** nó dùng loader riêng chỉ vì có tên module; trong môi trường này `String` được định nghĩa bởi bootstrap.

Không cần khẳng định loader của `lab.app` có chuỗi tên in ra nhất định. Ví dụ dựa trên **quan hệ identity** có thể kiểm chứng được.

## 6. Thực hành B — Tạo loader ngoài sơ đồ ba built-in loader

Thực hành thứ hai chứng minh việc tạo **named module trong child layer** có thể sinh ClassLoader **khác system loader**. Nó cũng minh họa rằng một module được resolve nhưng chưa chắc nằm trong boot layer.

Tạo cấu trúc:

~~~text
project/
  src/
    plugin.one/
      module-info.java
      plugin/
        one/
          Feature.java
    launcher/
      LayerDemo.java
~~~

Tệp **`src/plugin.one/module-info.java`**:

~~~java
module plugin.one {
    exports plugin.one;
}
~~~

Tệp **`src/plugin.one/plugin/one/Feature.java`**:

~~~java
package plugin.one;

public class Feature {
    public static String label() {
        return "feature";
    }
}
~~~

Tệp **`src/launcher/LayerDemo.java`** (launcher chạy từ classpath, tức trong unnamed module của loader tương ứng):

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class LayerDemo {
    public static void main(String[] args) throws Exception {
        ModuleLayer boot = ModuleLayer.boot();

        ModuleFinder finder = ModuleFinder.of(Path.of("build/mods"));
        Configuration cf = boot.configuration().resolve(
                finder, ModuleFinder.of(), Set.of("plugin.one"));

        ModuleLayer child = boot.defineModulesWithOneLoader(
                cf, ClassLoader.getSystemClassLoader());
        ClassLoader loader = child.findLoader("plugin.one");
        Class<?> feature = loader.loadClass("plugin.one.Feature");

        System.out.println("name=" + feature.getModule().getName());
        System.out.println("inChild="
                + (feature.getModule().getLayer() == child));
        System.out.println("loaderMatches="
                + (feature.getClassLoader() == loader));
        System.out.println("differentFromSystem="
                + (loader != ClassLoader.getSystemClassLoader()));
    }
}
~~~

Từ thư mục **`project`**, chạy đúng các lệnh:

~~~sh
javac --release 17 -d build/mods/plugin.one src/plugin.one/module-info.java src/plugin.one/plugin/one/Feature.java
javac --release 17 -d build/launcher src/launcher/LayerDemo.java
java -cp build/launcher LayerDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
name=plugin.one
inChild=true
loaderMatches=true
differentFromSystem=true
~~~

### Cơ chế của ví dụ

1. `ModuleFinder.of(Path.of("build/mods"))` quan sát được exploded module `plugin.one` tại đường dẫn build; finder **chưa tự tải lớp**.
2. `boot.configuration().resolve(...)` tạo configuration cho named module `plugin.one` dựa trên boot configuration làm parent; `Set.of("plugin.one")` chọn root module cần resolve.
3. `boot.defineModulesWithOneLoader(cf, systemLoader)` tạo **child module layer** cùng **loader mới** cho module được resolve trong configuration. Argument `systemLoader` là **parent** của loader mới, không phải bản thân loader chứa `plugin.one`.
4. `child.findLoader("plugin.one")` lấy đúng loader được gán cho module. `loader.loadClass("plugin.one.Feature")` tìm lớp; ta chưa cần tạo instance hoặc kích hoạt initialize `Feature`.
5. `feature.getModule().getLayer() == child` chứng minh module nằm trong layer mới; `loader != systemLoader` chứng minh đã có loader nằm **ngoài ba tên trong sơ đồ built-in**.

Khi dùng `defineModulesWithManyLoaders(cf, systemLoader)` với configuration chứa **nhiều** named module, API sẽ tạo **một loader mới cho mỗi module**. Ngược lại, `defineModulesWithOneLoader` tạo **một loader** dùng cho các module trong configuration. Không cần tự viết subclass ClassLoader để quan sát hiệu ứng này.

> **Lưu ý về tính chạy được:** `LayerDemo` dùng đường dẫn tương đối `build/mods`; hãy chạy lệnh từ đúng thư mục `project`. Nếu chạy ở thư mục khác, sửa đường dẫn cho đúng. Thử nghiệm là ví dụ độc lập Java 17+, không cần Maven, Gradle hoặc IDE.

## 7. Khi nào dùng thông tin nào để phân tích vấn đề?

| Câu hỏi thực tế | Quan sát phù hợp | Vì sao sơ đồ ba loader chưa đủ |
|---|---|---|
| Lớp do loader nào định nghĩa? | `clazz.getClassLoader()` | Biết loader nhưng chưa biết JPMS module |
| Lớp thuộc module nào, named không? | `clazz.getModule()`, `isNamed()`, `getName()` | Một loader có thể gắn với nhiều module |
| Module thuộc layer nào? | `clazz.getModule().getLayer()` | Boot layer chỉ là một trong các layer có thể có |
| Một module trong layer dùng loader nào? | `layer.findLoader(moduleName)` | Module-to-loader mapping không suy ra từ quan hệ `requires` |
| Vì sao module A không dùng được public class của B? | Module readability (`requires`), package `exports` và resolution | Class loading và package access là hai cơ chế khác nhau |
| Vì sao framework reflection bị chặn? | Kiểm tra package `opens` và quyền reflective access | Có class trong loader chưa đủ để deep reflection |
| Vì sao hai plugin có cùng binary name nhưng không ép kiểu được? | So sánh `getName()` **và** `getClassLoader()`, thêm module/layer | Có thể là hai lớp khác defining loader |
| Vì sao một module JAR hiện diện nhưng không tải được? | Module path, root modules, `Configuration`, resolution và mapping | Có file không đồng nghĩa module đã được resolve |
| Vì sao thêm `--module-path` chưa đủ? | Kiểm tra module được resolve từ roots/`requires` | Module path cung cấp vị trí, không thay việc resolve graph |

### Các API quan sát dùng chung

~~~java
static void inspect(Class<?> clazz) {
    Module module = clazz.getModule();
    ClassLoader loader = clazz.getClassLoader();

    System.out.println("class=" + clazz.getName());
    System.out.println("module=" + module.getName());
    System.out.println("named=" + module.isNamed());
    System.out.println("layer=" + module.getLayer());
    System.out.println("loader=" + loader);
}
~~~

Đây là **phương thức minh họa**, không phải tệp Java độc lập. Với unnamed module, `module.getName()` trả về `null`; với bootstrap-defined classes, `loader` có thể là `null`. Đừng xem các giá trị `null` ấy là ngoại lệ. In `ModuleLayer` hoặc `ClassLoader` có thể cho chuỗi phụ thuộc JVM/JDK nên không sử dụng chuỗi đó làm assert cố định.

### Lệnh công cụ nên biết

- `java --list-modules`: liệt kê các module hệ thống khả dụng; **không** chứng minh tất cả đã được resolve cho ứng dụng đang chạy.
- `java --show-module-resolution --module-path mods --module lab.app/lab.app.Main`: quan sát quá trình resolve module khi khởi chạy (thứ tự/số dòng phụ thuộc JDK, không dùng làm stdout cố định).
- `jar --describe-module --file mylib.jar`: xem mô tả module của một JAR phù hợp.
- `jdeps --module-path mods --module lab.app`: phân tích dependency trong ngữ cảnh có module; điều chỉnh path tùy cấu trúc build thực tế.

Các công cụ trên bổ sung bằng chứng về **module graph**; `Class.getClassLoader()` và `ModuleLayer.findLoader()` bổ sung bằng chứng về **loader mapping**.

## 8. Lỗi suy luận phổ biến và cách sửa

1. **“Java chỉ có đúng ba class loaders.”** Sai. Ba loader trong sơ đồ là các **built-in loaders**; custom loaders và loaders cho module layers có thể tồn tại.
2. **“Named module nào cũng có classloader riêng.”** Sai. `defineModulesWithOneLoader` cho phép nhiều modules dùng chung một loader.
3. **“Mọi named module chạy bằng system loader.”** Sai. Cách ánh xạ phụ thuộc layer và cấu hình; có bootstrap, platform, application và loader khác.
4. **“`requires` nghĩa là loader của module A là con loader của B.”** Sai. Đây là quan hệ **module readability**, không phải classloader parent.
5. **“Nếu loader tìm thấy lớp thì code ở module khác đương nhiên dùng được.”** Sai. JPMS áp dụng điều kiện readability và package accessibility.
6. **“`exports` và `opens` tương đương.”** Sai. Export phục vụ truy cập thông thường theo quy tắc; opens cấp quyền reflective access phù hợp, nhất là deep reflection.
7. **“Module JAR nằm trên module path thì đã load ngay.”** Sai. Module cần được resolve; từng lớp lại được load khi JVM cần. Resolution không có nghĩa mọi lớp trong module đã initialized.
8. **“Cùng tên module hoặc cùng tên class tức là cùng class object.”** Sai. Module có thể tồn tại ở nhiều layers; identity của class xét binary name cùng defining loader.
9. **“`getClassLoader() == null` là bug.”** Sai với bootstrap-defined classes như `String`.
10. **“Parent-first luôn đủ giải thích thứ tự tìm lớp trong ứng dụng modular.”** Sai. Các built-in loader có trường hợp ủy quyền bổ sung; module mapping và custom strategies cần được kiểm tra thực tế.

## 9. Tự kiểm tra

1. Vì sao sơ đồ bootstrap → platform → application vẫn có ích nhưng không phải bản đồ đầy đủ của JPMS?
2. Một loader có thể định nghĩa nhiều named module không? API nào trong `ModuleLayer` minh họa điều đó?
3. Tạo child layer bằng `defineModulesWithManyLoaders` với ba module thì có bao nhiêu loader mới theo hợp đồng của API?
4. Quan hệ `requires` và quan hệ `ClassLoader.getParent()` khác nhau ở bản chất nào?
5. Nếu một lớp được loader tìm thấy nhưng module hiện tại không truy cập được package chứa nó, nên kiểm tra những quy tắc JPMS nào?
6. Dùng API nào để biết lớp thuộc named/unnamed module và layer nào?
7. `ClassLoader.getSystemClassLoader()` có nhất thiết là loader của mọi class trên module path không?
8. Vì sao `loader.loadClass("plugin.one.Feature")` trong ví dụ B không chứng minh module thuộc boot layer?
9. Trong ví dụ B, `differentFromSystem=true` chứng minh điều gì? Có nhất thiết phải viết subclass custom ClassLoader không?
10. Vì sao cần xác định module resolution trước khi kết luận một named module “có mặt” trong ứng dụng?
11. Nếu hai plugin đưa hai lớp tên `plugin.api.Service` vào các loader khác nhau, tên class giống nhau có bảo đảm cast được không?
12. `Module.getLayer() == null` hoặc `Class.getClassLoader() == null` có luôn là lỗi không? Nêu trường hợp hợp lệ cho từng kết quả.

**Tiêu chí hoàn thành:** bạn giải thích đúng sự khác nhau giữa **module graph**, **module layer** và **loader delegation**; tự chạy hai thí nghiệm, dự đoán đúng stdout và dùng kết hợp `Class#getModule`, `ModuleLayer.findLoader`, `Class#getClassLoader` để chẩn đoán thực tế.

## 10. Tham khảo chính thức

- [Java SE 21 — `ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): ba built-in loaders, parent delegation, ngoại lệ ủy quyền trong ứng dụng module.
- [Java SE 21 — `ModuleLayer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html): boot layer, cấu hình module, mapping module→ClassLoader và các API một/nhiều loaders.
- [Java SE 21 — `Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): module identity, named/unnamed, layer, readability, exports/opens.
- [Java SE 21 — `Configuration`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html): module resolution và quan hệ phụ thuộc.
- [Java SE 21 — `ModuleFinder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleFinder.html): khám phá module definitions trên đường dẫn.

Các liên kết API là nguồn tra cứu Java 21; hai ví dụ biên dịch ở mức tương thích Java 17 và không dựa vào thứ tự chuỗi `toString()` của loader.