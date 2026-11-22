# Class loader trong một module layer

## <a id="tong-quan">Class loader đóng vai trò gì trong ModuleLayer?</a>

Trong Java Platform Module System (JPMS), một **module** nhóm các package, khai báo phụ thuộc và quyết định phần API được công khai. Một **module layer** (`ModuleLayer`) là tập các module đã được giải quyết phụ thuộc để có thể hoạt động cùng nhau. Còn **class loader** là thành phần tìm và định nghĩa các lớp (`Class<?>`) trong JVM.

Ba khái niệm liên quan nhưng không đồng nhất:

- `Configuration` mô tả *module nào được giải quyết và chúng đọc module nào*.
- `ModuleLayer` đưa cấu hình đó vào môi trường chạy, gắn mỗi module với một class loader và có thể có một hay nhiều layer cha.
- `ClassLoader` chịu trách nhiệm nạp mã bytecode của các lớp, đồng thời tham gia xác định danh tính lớp trong JVM.

Hình dung một ứng dụng có các module nền tảng trong layer khởi động và hai plugin được tải sau:

```text
ModuleLayer.boot()                (layer cha)
  ├─ java.base                     → bootstrap loader
  └─ các module của ứng dụng       → loader tương ứng
            │
            │ cấu hình cha + class loader cha
            ▼
ModuleLayer pluginLayer           (layer con)
  ├─ demo.greeter                  → pluginLoader
  └─ demo.report                   → pluginLoader hoặc loader khác
```

Mũi tên giữa các layer thể hiện quan hệ cha của **layer**; mũi tên từ module đến loader thể hiện ánh xạ dùng để nạp lớp. Đây là hai mối quan hệ riêng. Một layer có thể chứa nhiều module, và nhiều module có thể dùng chung một loader.

**Lộ trình học:** hiểu sự khác nhau giữa module và loader → xem cách layer tạo ánh xạ → thực hành tạo layer con → quan sát danh tính lớp và quyền truy cập → chọn chiến lược loader phù hợp.

## <a id="vi-sao-can-class-loader">Vì sao layer cần ánh xạ module tới class loader?</a>

Trước JPMS, một class loader thường tìm lớp theo tên nhị phân như `com.example.Service` trên classpath. Với JPMS, JVM còn biết lớp thuộc **module có tên** nào; module đó có thể công khai package bằng `exports`, mở package cho phản chiếu bằng `opens` và khai báo phụ thuộc bằng `requires`.

Layer giúp ứng dụng triển khai những tình huống như:

- Nạp một bộ module plugin được phát hiện lúc chạy, ngoài tập module khởi động.
- Tạo hai layer với những phiên bản hoặc triển khai khác nhau của cùng một tên module, khi cấu trúc phụ thuộc cho phép.
- Chọn chính sách dùng chung loader hoặc dùng loader riêng cho từng module.
- Truy vấn lớp thuộc layer nào và dùng loader nào để nạp lớp.

Không phải mỗi module có một loader. Ngược lại, class loader không tự tạo ra quy tắc `requires`/`exports`. **Khả năng tìm thấy bytecode** và **quyền truy cập ở cấp module** là hai điều kiện khác nhau.

Danh tính một lớp tại thời điểm chạy gắn với **tên nhị phân + loader định nghĩa lớp**. Vì vậy, hai lớp cùng tên được định nghĩa bởi hai loader khác nhau là hai kiểu khác nhau trong JVM. Ép kiểu giữa chúng có thể gây `ClassCastException`, dù mã nguồn trông giống hệt nhau.

## <a id="anh-xa-module-loader">Từ Configuration đến ánh xạ module–loader</a>

Một tiến trình điển hình gồm bốn bước:

1. Dùng `ModuleFinder` tìm các modular JAR hoặc exploded module.
2. Dùng `Configuration.resolve(...)` giải quyết tập module gốc và các phụ thuộc, dựa trên cấu hình của layer cha.
3. Gọi một trong các phương thức `defineModules...` để tạo layer và gắn loader cho từng module trong cấu hình mới.
4. Dùng `layer.findLoader(moduleName)` để lấy loader của một module được định nghĩa **trực tiếp trong layer đó**, rồi dùng loader để tải lớp.

Ví dụ quan hệ dữ liệu:

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| `ModuleFinder` | Mã module nằm ở đâu? | Thư mục `plugin-mods/` |
| `Configuration` | Cần những module nào, chúng đọc ai? | `demo.greeter`, `java.base` |
| `ModuleLayer` | Các module đã được định nghĩa trong layer nào? | `pluginLayer` |
| `ClassLoader` | Lớp này do bộ nạp nào định nghĩa? | `pluginLayer.findLoader("demo.greeter")` |

Một module trong cấu hình mới có thể đọc các module của layer cha. Điều đó không có nghĩa mọi lớp đều được nạp bởi loader của layer cha: JPMS vẫn dùng các liên kết ủy quyền loader và kiểm tra khả năng truy cập theo cấu hình module.

**Hai loại “cha” cần phân biệt:**

- **Layer cha:** cung cấp các module/cấu hình đã tồn tại để giải quyết phụ thuộc cho layer con.
- **Loader cha:** tham số `parentLoader` khi Java tạo loader mới; dùng để ủy quyền tải những lớp phù hợp.

`parentLoader` là `ClassLoader`, không phải `ModuleLayer`; truyền hệ thống loader vào phương thức tạo layer không biến layer mới thành một phần của boot layer.

## <a id="ba-cach-gan-loader">Ba cách gắn class loader khi tạo layer</a>

### 1. Một loader cho toàn bộ module mới

```java
ModuleLayer child = ModuleLayer.boot()
    .defineModulesWithOneLoader(config, ClassLoader.getSystemClassLoader());
```

`defineModulesWithOneLoader` tạo **một loader mới** để định nghĩa các module trong `config`. Tham số truyền vào là **loader cha của loader mới**, không phải yêu cầu dùng trực tiếp hệ thống loader làm loader của plugin.

Ưu điểm: cách tổ chức đơn giản, các module mới chia sẻ cùng loader. Hạn chế: mức phân tách danh tính lớp thấp hơn; những package không tương thích không thể tùy ý được định nghĩa trong cùng một loader.

### 2. Mỗi module mới có loader riêng

```java
ModuleLayer child = ModuleLayer.boot()
    .defineModulesWithManyLoaders(config, ClassLoader.getSystemClassLoader());
```

`defineModulesWithManyLoaders` tạo một loader mới cho từng module được định nghĩa trong cấu hình. Các module vẫn dùng JPMS để đọc lẫn nhau theo quan hệ phụ thuộc; không nên suy diễn rằng loader riêng sẽ tự động ngăn mọi tương tác giữa các module.

Ưu điểm: phân tách không gian lớp theo module rõ hơn, thuận lợi khi thiết kế hệ thống plugin. Đổi lại: nhiều loader hơn, việc chia sẻ API và giữ tham chiếu phải được quản lý cẩn thận.

### 3. Tự chọn loader cho từng tên module

```java
Map<String, ClassLoader> mapping = Map.of(
    "demo.greeter", greeterLoader,
    "demo.report", reportLoader
);

ModuleLayer child = ModuleLayer.boot()
    .defineModules(config, mapping::get);
```

`defineModules` nhận hàm `Function<String, ClassLoader>`, trả về loader cho từng module trong cấu hình. Đây là lựa chọn nâng cao: ứng dụng chịu trách nhiệm về loader, cách tải lớp, ủy quyền và tính tương thích của các package. Đoạn mã giả định `greeterLoader` và `reportLoader` đã được khởi tạo đúng; việc tự viết class loader nằm ngoài ví dụ nhập môn này.

| Chiến lược | Loader cho các module mới | Phù hợp khi |
|---|---|---|
| `defineModulesWithOneLoader` | Một loader mới dùng chung | Bộ module nhỏ, muốn thiết lập đơn giản |
| `defineModulesWithManyLoaders` | Mỗi module một loader mới | Muốn ranh giới loader rõ theo module |
| `defineModules` | Do ứng dụng cung cấp | Cần chính sách nạp lớp tùy biến |

Với các overload tĩnh nhận `List<ModuleLayer>` cha, phương thức trả về `ModuleLayer.Controller`; gọi `controller.layer()` để lấy layer. Trong bài này, các ví dụ dùng overload trên một đối tượng `ModuleLayer` cha, trả về trực tiếp `ModuleLayer`.

## <a id="vi-du-tao-layer">Ví dụ hoàn chỉnh: nạp modular JAR ở layer con</a>

Giả sử ứng dụng chủ chạy trên classpath, còn plugin được đóng gói thành modular JAR `plugin-mods/demo.greeter.jar`.

**1. Module descriptor của plugin — `module-info.java`:**

```java
module demo.greeter {
    exports demo.greeter.api;
}
```

**2. Lớp API công khai bên trong plugin — `demo/greeter/api/Greeter.java`:**

```java
package demo.greeter.api;

public final class Greeter {
    public Greeter() {}

    public String hello(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

**3. Ứng dụng chủ — `Host.java`:**

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class Host {
    public static void main(String[] args) throws Exception {
        ModuleLayer boot = ModuleLayer.boot();

        // Chỉ rõ nơi chứa các modular JAR của plugin.
        ModuleFinder finder = ModuleFinder.of(Path.of("plugin-mods"));

        // Tạo cấu hình con dựa vào các module đã có trong boot layer.
        Configuration config = boot.configuration().resolve(
            finder,
            ModuleFinder.of(),
            Set.of("demo.greeter")
        );

        // Một loader mới được tạo cho các module trong config.
        ModuleLayer pluginLayer = boot.defineModulesWithOneLoader(
            config,
            ClassLoader.getSystemClassLoader()
        );

        Module pluginModule = pluginLayer.findModule("demo.greeter")
            .orElseThrow();
        ClassLoader pluginLoader = pluginLayer.findLoader("demo.greeter");

        Class<?> type = pluginLoader.loadClass("demo.greeter.api.Greeter");
        Object instance = type.getConstructor().newInstance();
        Object result = type.getMethod("hello", String.class)
            .invoke(instance, "JPMS");

        System.out.println(result);
        System.out.println(type.getModule() == pluginModule);
        System.out.println(type.getClassLoader() == pluginLoader);
    }
}
```

Để tự chạy ví dụ với JDK 17+ và cấu trúc tệp như trên, có thể biên dịch và đóng gói:

```bash
javac -d out/plugin src/demo.greeter/module-info.java src/demo.greeter/demo/greeter/api/Greeter.java
jar --create --file plugin-mods/demo.greeter.jar -C out/plugin .
javac -d out/host Host.java
java -cp out/host Host
```

Tạo thư mục `plugin-mods` trước khi chạy lệnh `jar`. Các lệnh trên minh họa đường dẫn tương đối; có thể thay đổi cho phù hợp với thư mục dự án.

Kết quả chính:

```text
Xin chào, JPMS!
true
true
```

Giá trị `true` thứ nhất xác nhận lớp thuộc module đã lấy từ layer. Giá trị thứ hai xác nhận loader mà layer ánh xạ tới module thực sự là loader định nghĩa `Greeter`. Ví dụ hoạt động nhờ package `demo.greeter.api` được `exports`; nếu chỉ tải được lớp nhưng package không được xuất phù hợp, thao tác gọi từ ứng dụng chủ có thể không được phép.

## <a id="truy-van-loader">Tìm loader và nhận biết module thuộc layer nào</a>

```java
ModuleLayer boot = ModuleLayer.boot();

ClassLoader javaBaseLoader = boot.findLoader("java.base");
System.out.println(javaBaseLoader == null); // true: bootstrap loader

// Với một pluginLayer đã tạo như ví dụ:
Module plugin = pluginLayer.findModule("demo.greeter").orElseThrow();
ClassLoader loader = pluginLayer.findLoader("demo.greeter");
System.out.println(plugin.getClassLoader() == loader);
```

Một số quy tắc thực hành:

- `ModuleLayer.findLoader(name)` chỉ chấp nhận tên module được định nghĩa **trong chính layer nhận lời gọi**; tên không có ở layer đó gây `IllegalArgumentException`.
- Giá trị `null` từ `findLoader` có thể là trường hợp hợp lệ: module do **bootstrap class loader** tải, chẳng hạn `java.base` trong boot layer.
- `ModuleLayer.findModule(name)` có thể tìm tiếp trong các layer cha. Do đó, việc `findModule` tìm thấy module không đảm bảo `findLoader` trên chính layer hiện tại chấp nhận tên đó. Nếu muốn loader của module đã tìm thấy, có thể dùng `module.getClassLoader()`.
- `Class.forName("demo.greeter.api.Greeter")` từ ứng dụng chủ không chắc thấy lớp nằm trong layer con: phương thức này dùng loader gắn với nơi gọi theo quy tắc tương ứng. Hãy lấy loader từ layer hoặc dùng `Class.forName(module, className)` khi có `Module` phù hợp.

Với `Class.forName(Module, String)`, kết quả là `null` nếu lớp không được tìm thấy trong module chỉ định. Đây là API khác với overload `Class.forName(String)` vốn ném `ClassNotFoundException` khi không tìm thấy lớp.

## <a id="loader-va-quyen-truy-cap">Tải được lớp chưa đồng nghĩa sử dụng được lớp</a>

Xét plugin có mô tả:

```java
module demo.greeter {
    requires demo.contract;
    exports demo.greeter.api;
    opens demo.greeter.internal to demo.host;
}
```

- `requires demo.contract`: khai báo plugin đọc module hợp đồng. Cấu hình module giải quyết được phụ thuộc; loader phải có đường đi phù hợp để nạp các lớp cần thiết.
- `exports demo.greeter.api`: cho phép module khác truy cập các kiểu `public` trong package API, nếu thỏa điều kiện đọc module.
- `opens demo.greeter.internal to demo.host`: cho phép phản chiếu sâu tới package nội bộ đối với module có tên `demo.host`; không biến package đó thành API công khai để biên dịch.
- `ClassLoader.loadClass(...)`: tìm hoặc nạp `Class<?>`; không tự cấp quyền truy cập vào constructor, field hay method vốn bị JPMS/Java visibility hạn chế.

Phân biệt lỗi theo tầng:

| Hiện tượng | Nơi cần kiểm tra |
|---|---|
| Không tìm thấy module khi `resolve` | `ModuleFinder`, đường dẫn JAR, tên module, `requires` |
| `LayerInstantiationException` khi tạo layer | Ánh xạ loader, package xung đột, ràng buộc khi định nghĩa module |
| `IllegalArgumentException` ở `findLoader` | Tên module không được định nghĩa trực tiếp trong layer đang hỏi |
| `ClassNotFoundException` | Tên nhị phân, nội dung JAR, loader đang dùng |
| `IllegalAccessException` hoặc `InaccessibleObjectException` | `public`, `exports`, `opens`, quan hệ đọc module |
| `ClassCastException` dù cùng tên lớp | Hai bản lớp đến từ hai loader định nghĩa khác nhau |

Trong các hệ thống plugin, một API chung nên nằm ở module thuộc layer cha và được các plugin cùng tham chiếu. Nếu từng plugin mang theo và nạp riêng bản API của mình, đối tượng cùng tên interface có thể không ép kiểu qua lại được.

## <a id="mot-hay-nhieu-loader">Quan sát khác nhau giữa một loader và nhiều loader</a>

Giả sử `config` giải quyết hai module mới: `demo.greeter` và `demo.report`. Có thể so sánh:

```java
ClassLoader parentLoader = ClassLoader.getSystemClassLoader();
ModuleLayer boot = ModuleLayer.boot();

ModuleLayer one = boot.defineModulesWithOneLoader(config, parentLoader);
boolean sameOne = one.findLoader("demo.greeter")
    == one.findLoader("demo.report");

ModuleLayer many = boot.defineModulesWithManyLoaders(config, parentLoader);
boolean sameMany = many.findLoader("demo.greeter")
    == many.findLoader("demo.report");

System.out.println(sameOne);  // true
System.out.println(sameMany); // false
```

Ví dụ giả định cả hai module đều thuộc `config` và có thể được định nghĩa thành công. Mỗi lời gọi tạo layer con mới, nên `one` và `many` là hai layer khác nhau.

Các loader riêng làm thay đổi **danh tính lớp**, cách ủy quyền và vòng đời tham chiếu. Chúng không tự thay thế kiểm tra phụ thuộc hoặc tính đóng gói của module. Quyết định dùng nhiều loader nên dựa vào nhu cầu cách ly, quản lý phiên bản và giao diện chia sẻ giữa plugin với ứng dụng chủ.

## <a id="ung-dung-dong">Class loader và hệ thống plugin</a>

Khi cần tìm các triển khai dịch vụ, `ServiceLoader` thường tiện hơn phản chiếu bằng tên lớp cố định:

```java
// ContractService là interface từ một module API chung ở layer cha.
// Module plugin phải khai báo provides ... with ... trong module-info.java.
ServiceLoader<ContractService> services =
    ServiceLoader.load(pluginLayer, ContractService.class);

for (ContractService service : services) {
    System.out.println(service.getClass().getModule().getName());
}
```

Ví dụ giả định `ContractService` đã được định nghĩa và nhìn thấy từ ứng dụng chủ. `ServiceLoader.load(layer, serviceType)` tra cứu provider trong layer được chỉ định và các layer cha theo quy tắc JPMS; các plugin có thể công bố provider bằng `provides ... with ...`. Cách này giảm nhu cầu biết trước tên lớp triển khai và dùng phản chiếu thủ công.

**Vòng đời:** JPMS không cung cấp nút `unloadModule` hay `unloadLayer`. Khi không còn tham chiếu giữ layer, class loader, `Class<?>`, đối tượng plugin và các thành phần liên quan, JVM *có thể* thu gom chúng. Chỉ bỏ biến `pluginLayer` không đảm bảo module hoặc lớp đã được giải phóng; cần chú ý cache tĩnh, thread, thread context class loader và service/provider còn sống.

**Class loader không phải ranh giới bảo mật tuyệt đối.** Dùng layer/plugin để tổ chức mã và quản lý phụ thuộc; đừng coi nó là sandbox đủ để chạy mã không đáng tin cậy.

## <a id="sai-lam-pho-bien">Những nhầm lẫn thường gặp</a>

1. **“Mỗi module có một class loader.”** Sai: `defineModulesWithOneLoader` gắn nhiều module vào cùng một loader.
2. **“Truyền system loader vào là plugin được tải bởi system loader.”** Sai với hai phương thức `defineModulesWith...`: Java tạo loader **mới** với system loader làm cha.
3. **“`findModule` thành công thì `findLoader` trên cùng layer chắc chắn thành công.”** Không hẳn: `findModule` có thể tìm ở layer cha, còn `findLoader` chỉ tra module định nghĩa trực tiếp trong layer.
4. **“Loader tìm được lớp thì gọi được mọi method.”** Sai: ranh giới `exports`/`opens` và quy tắc truy cập Java vẫn áp dụng.
5. **“Hai lớp cùng package và cùng tên thì là cùng kiểu.”** Chỉ đúng khi danh tính loader định nghĩa tương thích; khác loader có thể là hai kiểu khác nhau.
6. **“Bỏ layer là unload ngay.”** JVM chỉ có thể thu gom khi không còn các tham chiếu giữ lớp, loader hoặc đối tượng liên quan.

## <a id="thuc-hanh">Thực hành và tự kiểm tra</a>

**Bài 1 — Truy vết loader.** Chạy ví dụ `demo.greeter`, in tên module của `Greeter`, so sánh `type.getClassLoader()` với `pluginLayer.findLoader("demo.greeter")` và quan sát `ModuleLayer.boot().findLoader("java.base")`. Giải thích vì sao loader của `java.base` có thể là `null`.

**Bài 2 — So sánh chính sách.** Tạo thêm modular JAR `demo.report` (không cần phụ thuộc `demo.greeter`). Resolve cả hai tên module, lần lượt dùng `defineModulesWithOneLoader` và `defineModulesWithManyLoaders`. So sánh kết quả `==` giữa hai loader trong cùng layer, rồi giải thích lớp nào được chia sẻ và loader nào chỉ thuộc layer mới.

**Bài 3 — Tách nạp lớp và truy cập.** Thử bỏ `exports demo.greeter.api` khỏi `module-info.java`, đóng gói lại và chạy Host. Ghi lại bước nào vẫn tìm thấy `Class<?>` và bước nào không còn đủ quyền truy cập. Sau đó khôi phục `exports`. Phân tích bằng hai câu hỏi: *loader tìm được bytecode chưa?* và *module gọi có quyền truy cập kiểu/thành viên chưa?*

**Câu hỏi tự kiểm tra:**

- `ModuleLayer`, `Configuration` và `ClassLoader` khác nhau ở trách nhiệm nào?
- Tại sao ứng dụng có thể có nhiều layer con cùng tên module nhưng không nên trộn đối tượng từ các loader khác nhau một cách tùy tiện?
- Khi nào nên chọn một loader, nhiều loader, hoặc ánh xạ loader tùy biến?
- Vì sao một module có thể được `findModule` tìm thấy từ layer con nhưng `findLoader` tại layer con lại báo lỗi?

**Ghi nhớ:** cấu hình giải quyết quan hệ module; layer định nghĩa module vào môi trường chạy; class loader định nghĩa lớp. Muốn kiểm chứng một lớp đến từ đâu, hãy xem đồng thời `type.getModule()` và `type.getClassLoader()`, rồi đối chiếu với module và loader của layer tương ứng.
