# ModuleLayer và tập module đã định nghĩa trong Java (JPMS)

`ModuleLayer` là đối tượng biểu diễn một **lớp module tại thời điểm chạy** trong Java Platform Module System (JPMS). Mỗi layer chứa một tập các module *đã được định nghĩa* (defined modules), liên kết với một `Configuration` và các class loader tương ứng. Hiểu đúng tập module này giúp bạn xác định module nào thực sự thuộc layer, module nào được tìm qua layer cha, và vì sao một module có trên đĩa chưa chắc đã có mặt lúc chạy.

> Ví dụ sử dụng JDK 17 trở lên. API `ModuleLayer` xuất hiện từ Java 9; một số đoạn dùng `Stream.toList()` nên chọn JDK 17+ để chạy nguyên mẫu.

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt module *được phát hiện*, *được resolve* và *được định nghĩa* trong một layer.
- Lấy `Set<Module>` trực tiếp của layer bằng `modules()`.
- Dùng `findModule()` để tìm module trong layer hiện tại hoặc layer tổ tiên, đồng thời biết khi nào kết quả khác với `modules()`.
- Kiểm tra `Module.getLayer()`, `ModuleLayer.parents()` và `ModuleLayer.configuration()`.
- Tạo layer con và quan sát tập module được định nghĩa bằng ví dụ JPMS chạy được.

## 2. “Module đã định nghĩa” nghĩa là gì?

Quá trình hình thành một module có thể nhìn qua ba mức:

1. **Phát hiện (discovery):** `ModuleFinder` tìm các module trên module path hoặc một nguồn module khác và cung cấp `ModuleReference`. Được tìm thấy chưa đồng nghĩa với đã tham gia ứng dụng.
2. **Resolve (resolution):** `Configuration` biểu diễn đồ thị module đã resolve, gồm các `ResolvedModule` và quan hệ phụ thuộc. Việc resolve xác định một cấu hình hợp lệ.
3. **Định nghĩa (definition):** khi tạo `ModuleLayer` từ `Configuration`, JVM tạo các đối tượng `java.lang.Module` và ánh xạ chúng với class loader. Các đối tượng `Module` đó là **module đã định nghĩa trong layer**.

Các kiểu dữ liệu cần phân biệt:

| Đối tượng | Vai trò | Cách lấy ví dụ |
| --- | --- | --- |
| `ModuleReference` | Thông tin module được finder phát hiện | `ModuleFinder.find("com.example.greeter")` |
| `ResolvedModule` | Module trong đồ thị resolution | `configuration.modules()` |
| `Module` | Module runtime, gắn với class loader và có thể thuộc một layer | `layer.modules()` |
| `ModuleLayer` | Nhóm các `Module` runtime cùng quan hệ layer cha | `ModuleLayer.boot()` |

Điểm mấu chốt: `ModuleLayer.modules()` trả về **các đối tượng `Module` được định nghĩa trực tiếp tại layer đó**. Nó không liệt kê tất cả JAR trong thư mục, không trả về mọi module của JDK, và không tự gộp các module trong layer cha.

Ví dụ mô hình:

```text
Layer con
└── com.example.greeter       ← thuộc child.modules()
         │
         │ parent layer
         ▼
Boot layer
├── java.base                 ← thuộc boot.modules()
├── java.logging              ← nếu được resolve trong boot layer
└── ...                       ← tùy cách khởi chạy ứng dụng
```

Khi gọi `child.modules()`, bạn chỉ nhận module được định nghĩa tại layer con. Khi gọi `child.findModule("java.base")`, bạn vẫn có thể tìm thấy `java.base` ở boot layer thông qua chuỗi layer cha.

## 3. Những API quan trọng

| API | Giá trị trả về và ý nghĩa |
| --- | --- |
| `ModuleLayer.boot()` | Boot layer được JVM thiết lập khi khởi chạy chương trình |
| `layer.modules()` | `Set<Module>` không thể sửa, chỉ gồm module định nghĩa **trong layer hiện tại** |
| `layer.findModule(name)` | `Optional<Module>`; tìm ở layer hiện tại, rồi các layer cha |
| `layer.parents()` | Danh sách các layer cha trực tiếp; một layer có thể có nhiều cha |
| `layer.configuration()` | `Configuration` dùng để định nghĩa các module của layer |
| `layer.findLoader(name)` | Class loader của module có tên được định nghĩa tại layer; tên không thuộc layer có thể gây `IllegalArgumentException` |
| `module.getLayer()` | Layer chứa `Module` đó; có thể là `null` nếu module không thuộc layer nào |
| `module.getName()` | Tên module; các module được định nghĩa trong layer là named module |
| `module.getDescriptor()` | Metadata của named module, gồm tên, packages, exports, requires... |
| `module.getClassLoader()` | Class loader gắn với module; có thể là `null` khi dùng bootstrap class loader |

Cần phân biệt: `layer.configuration().modules()` là tập `ResolvedModule` của cấu hình, còn `layer.modules()` là tập `Module` ở runtime. Hai tập thể hiện hai giai đoạn khác nhau dù có thể tương ứng theo tên module.

## 4. Quan sát module trong boot layer

Ví dụ sau chạy như một lớp Java thông thường, không cần tạo `module-info.java`:

```java
import java.lang.Module;
import java.lang.ModuleLayer;
import java.util.Comparator;
import java.util.Set;

public class InspectBootLayer {
    public static void main(String[] args) {
        ModuleLayer boot = ModuleLayer.boot();
        Set<Module> defined = boot.modules();

        System.out.println("Số module trong boot layer: " + defined.size());

        defined.stream()
               .sorted(Comparator.comparing(Module::getName))
               .forEach(module -> System.out.printf(
                   "%-35s | đúng boot layer: %s%n",
                   module.getName(),
                   module.getLayer() == boot
               ));

        Module javaBase = boot.findModule("java.base").orElseThrow();
        System.out.println("Tên: " + javaBase.getName());
        System.out.println("Layer: " + javaBase.getLayer());
        System.out.println("Descriptor: " + javaBase.getDescriptor().name());
    }
}
```

Chạy:

```bash
javac InspectBootLayer.java
java InspectBootLayer
```

Giải thích:

- `boot.modules()` cung cấp tập module runtime ở boot layer.
- `getLayer() == boot` xác nhận các module đang duyệt thực sự được định nghĩa trong boot layer.
- `findModule("java.base").orElseThrow()` hợp lý vì `java.base` là module nền tảng bắt buộc.
- Số module và danh sách in ra có thể khác giữa các phiên chạy: phụ thuộc JDK, runtime image, module path, root modules và cách JVM resolve module khi khởi động.

Đừng đồng nhất đầu ra `java --list-modules` với `ModuleLayer.boot().modules()`. Lệnh đầu cho biết module quan sát được trong runtime image/module path; lời gọi thứ hai cho biết module thực sự đã định nghĩa trong boot layer của **tiến trình đang chạy**.

## 5. `modules()` và `findModule()` khác nhau thế nào?

Giả sử `child` là layer con chỉ định nghĩa module `com.example.greeter`, còn `java.base` thuộc boot layer:

```java
Set<Module> local = child.modules();

boolean baseDefinedHere = local.stream()
        .anyMatch(module -> module.getName().equals("java.base"));
// false: java.base không được định nghĩa trong child

boolean baseFoundThroughParents =
        child.findModule("java.base").isPresent();
// true: tìm thấy trong layer tổ tiên

Module greeter = child.findModule("com.example.greeter").orElseThrow();
boolean greeterDefinedHere = greeter.getLayer() == child;
// true
```

Có hai câu hỏi khác nhau:

- **“Layer này tự định nghĩa module nào?”** Dùng `layer.modules()` hoặc lọc theo `module.getLayer() == layer`.
- **“Từ layer này có thể tra cứu module tên X trong hệ phân cấp layer không?”** Dùng `layer.findModule("X")`.

`findModule()` kiểm tra layer hiện tại rồi truy tìm qua các layer cha. Trong sơ đồ có nhiều cha, nên hiểu layer là **đồ thị có hướng không chu trình (DAG)**, không nhất thiết là một cây đơn giản. Nếu cần biết chính xác module thuộc đâu, hãy kiểm tra `module.getLayer()` sau khi tìm được.

Một module cùng tên có thể xuất hiện dưới dạng những đối tượng `Module` khác nhau khi được định nghĩa trong các layer độc lập. Vì vậy, khi đối chiếu module runtime, **tên module không thay thế được ngữ cảnh layer và class loader**.

## 6. Ví dụ hoàn chỉnh: tạo layer con và lấy tập module

Ví dụ xây một named module `com.example.greeter` thành modular JAR, resolve nó rồi định nghĩa trong layer con. Layer này dùng boot layer làm cha.

### 6.1. Cấu trúc thư mục

```text
module-layer-demo/
├── src/
│   └── com.example.greeter/
│       ├── module-info.java
│       └── com/
│           └── example/
│               └── greeter/
│                   └── Greeter.java
└── LayerDemo.java
```

File `src/com.example.greeter/module-info.java`:

```java
module com.example.greeter {
    exports com.example.greeter;
}
```

File `src/com.example.greeter/com/example/greeter/Greeter.java`:

```java
package com.example.greeter;

public final class Greeter {
    private Greeter() {}

    public static String hello() {
        return "Xin chào từ module trong layer con!";
    }
}
```

Dùng một chương trình riêng để định nghĩa layer con. File `LayerDemo.java`:

```java
import java.lang.Module;
import java.lang.ModuleLayer;
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class LayerDemo {
    public static void main(String[] args) throws Exception {
        // 1) Layer cha: các module đã khởi tạo ở thời điểm boot.
        ModuleLayer parent = ModuleLayer.boot();

        // 2) Phát hiện modular JAR trong thư mục mlib.
        ModuleFinder finder = ModuleFinder.of(Path.of("mlib"));

        // 3) Resolve module gốc và các phụ thuộc của nó.
        Configuration configuration = parent.configuration().resolve(
                finder,
                ModuleFinder.of(),
                Set.of("com.example.greeter")
        );

        // 4) Định nghĩa module của configuration trong một layer con.
        ModuleLayer child = parent.defineModulesWithOneLoader(
                configuration,
                ClassLoader.getSystemClassLoader()
        );

        // 5) modules() chỉ liệt kê module định nghĩa tại child.
        System.out.println("Module trong child:");
        child.modules().stream()
                .map(Module::getName)
                .sorted()
                .forEach(System.out::println);

        Module greeterModule = child.findModule("com.example.greeter")
                .orElseThrow();
        System.out.println("Greeter thuộc child: "
                + (greeterModule.getLayer() == child));

        // java.base nằm trong parent, nhưng child.findModule vẫn tìm được.
        boolean baseDefinedInChild = child.modules().stream()
                .anyMatch(m -> m.getName().equals("java.base"));
        boolean baseFound = child.findModule("java.base").isPresent();
        System.out.println("Child tự định nghĩa java.base: "
                + baseDefinedInChild);
        System.out.println("Child tìm thấy java.base: " + baseFound);
        System.out.println("Parent trực tiếp chứa boot layer: "
                + child.parents().contains(parent));

        // 6) Nạp class bằng class loader gắn với module của child.
        ClassLoader loader = child.findLoader("com.example.greeter");
        Class<?> type = loader.loadClass("com.example.greeter.Greeter");
        System.out.println(type.getMethod("hello").invoke(null));
    }
}
```

Các bước thực hiện ở thư mục `module-layer-demo` (tạo sẵn hai thư mục đầu ra):

```bash
mkdir out
mkdir mlib
javac -d out src/com.example.greeter/module-info.java src/com.example.greeter/com/example/greeter/Greeter.java
jar --create --file mlib/com.example.greeter.jar -C out .
javac LayerDemo.java
java LayerDemo
```

Đầu ra tiêu biểu:

```text
Module trong child:
com.example.greeter
Greeter thuộc child: true
Child tự định nghĩa java.base: false
Child tìm thấy java.base: true
Parent trực tiếp chứa boot layer: true
Xin chào từ module trong layer con!
```

Tại sao có khác biệt này?

1. `ModuleFinder` phát hiện `com.example.greeter` trong `mlib`.
2. `resolve(...)` tạo cấu hình dựa trên `parent.configuration()`. Phụ thuộc vào `java.base` được đáp ứng bởi cấu hình cha; vì thế `java.base` không cần được định nghĩa lần nữa trong `child`.
3. `defineModulesWithOneLoader(...)` định nghĩa các module thuộc cấu hình mới trong `child` và gắn chúng với class loader được tạo cho layer.
4. `child.modules()` chỉ có `com.example.greeter` trong ví dụ này, trong khi `child.findModule("java.base")` có thể tìm xuống hệ layer cha.

Lưu ý: chương trình được chạy bằng `java LayerDemo`, không thêm JAR trong `mlib` làm root module của boot layer. Cách này giúp quan sát rõ module được nạp qua layer con.

## 7. Lấy danh sách module trực tiếp và danh sách từ các layer cha

Để thu thập tên module **chỉ của layer hiện tại**, có thể viết:

```java
Set<String> localNames = child.modules().stream()
        .map(Module::getName)
        .collect(java.util.stream.Collectors.toUnmodifiableSet());
```

Nếu mục tiêu thực sự là thống kê module được định nghĩa trên layer hiện tại **và mọi tổ tiên**, hãy đi qua `parents()`. Ví dụ dưới đây tránh duyệt trùng khi nhiều nhánh cùng có một layer cha:

```java
import java.lang.Module;
import java.lang.ModuleLayer;
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.Deque;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.Set;

public class LayerModules {
    public static Set<Module> collectIncludingParents(ModuleLayer start) {
        Set<ModuleLayer> visitedLayers = new HashSet<>();
        Set<Module> result = new LinkedHashSet<>();
        Deque<ModuleLayer> queue = new ArrayDeque<>();
        queue.add(start);

        while (!queue.isEmpty()) {
            ModuleLayer layer = queue.removeFirst();
            if (!visitedLayers.add(layer)) {
                continue;
            }
            result.addAll(layer.modules());
            queue.addAll(layer.parents());
        }

        return Collections.unmodifiableSet(result);
    }
}
```

Sử dụng:

```java
Set<Module> local = child.modules();
Set<Module> acrossLayers = LayerModules.collectIncludingParents(child);

System.out.println("Số module trực tiếp: " + local.size());
System.out.println("Số module gồm tổ tiên: " + acrossLayers.size());
```

Lưu ý khi biểu diễn kết quả:

- Tập `Set<Module>` bảo toàn danh tính module runtime. Nếu chỉ lấy `Set<String>` theo `getName()`, bạn có thể vô tình gộp các module khác nhau nhưng trùng tên ở những layer khác nhau.
- `parents()` trả về layer cha trực tiếp; cần duyệt tiếp nếu muốn xem toàn bộ tổ tiên.
- Việc gom module ở nhiều layer chỉ nhằm **quan sát/thống kê**; không có nghĩa mọi module đều có cùng quan hệ đọc (readability), cùng class loader hoặc cùng khả năng truy cập package.

## 8. Liên hệ với configuration, class loader và khả năng truy cập

### `Configuration` quyết định điều gì được resolve

`configuration.modules()` chứa tập `ResolvedModule` của cấu hình tương ứng. Nó mô tả đồ thị phụ thuộc đã chọn, nhưng không phải đối tượng `Module` runtime.

```java
Configuration cf = child.configuration();

System.out.println("Resolved ở cấu hình của child:");
cf.modules().stream()
        .map(resolved -> resolved.name())
        .sorted()
        .forEach(System.out::println);

System.out.println("Defined ở child:");
child.modules().stream()
        .map(Module::getName)
        .sorted()
        .forEach(System.out::println);
```

Trong ví dụ đơn giản, hai danh sách tên có thể giống nhau, nhưng kiểu đối tượng và ý nghĩa khác nhau. Khi tìm trong cấu hình có parent, `Configuration.findModule(name)` cũng cho phép truy vấn qua cấu hình tổ tiên; điều đó không khiến module tổ tiên xuất hiện trong `configuration.modules()` của cấu hình hiện tại.

### Class loader gắn với module

Khi layer được định nghĩa, JPMS thiết lập ánh xạ module → class loader. Một số lựa chọn API:

- `defineModulesWithOneLoader(...)`: các module của layer mới được định nghĩa với một class loader.
- `defineModulesWithManyLoaders(...)`: mô hình class loader khác, thường một loader cho từng module.
- `defineModules(...)`: cho phép cung cấp hàm ánh xạ tên module tới class loader theo thiết kế cụ thể.

Muốn tải lớp của module trong layer con, hãy lấy loader đúng chỗ:

```java
ClassLoader loader = child.findLoader("com.example.greeter");
Class<?> greeter = loader.loadClass("com.example.greeter.Greeter");
```

Không nên mặc định rằng `Class.forName("com.example.greeter.Greeter")` dùng class loader của ứng dụng sẽ thấy mọi module ở layer tùy chỉnh. Ngoài việc lớp có thể được nạp hay không, truy cập thành viên còn phụ thuộc các quy tắc `exports`, `opens` và quan hệ module phù hợp.

### Có module trong layer chưa đồng nghĩa “có quyền dùng mọi lớp”

`modules()` và `findModule()` phục vụ quan sát cấu trúc runtime, không thay thế cơ chế kiểm soát truy cập của JPMS:

- `requires` biểu diễn phụ thuộc và ảnh hưởng đến module readability.
- `exports` cho phép truy cập các kiểu public trong package được export.
- `opens` liên quan đến deep reflection, theo phạm vi được mở.
- `Module.canRead(other)` kiểm tra quan hệ đọc ở runtime đối với module khác.

Vì thế, tìm được một `Module` không đảm bảo mã hiện tại có thể trực tiếp import mọi package hoặc phản chiếu vào private member của module đó.

## 9. Các nhầm lẫn hay gặp

**Nhầm 1: `ModuleLayer.boot().modules()` là tất cả module đã cài trong JDK.**

Thực tế nó chỉ phản ánh module được định nghĩa ở boot layer của phiên chạy hiện tại. Module có trong runtime image hay module path nhưng không được resolve/định nghĩa sẽ không tự xuất hiện.

**Nhầm 2: `child.modules()` bao gồm cả module của cha.**

Sai. Dùng `child.findModule(name)` để tra cứu qua tổ tiên, hoặc chủ động duyệt `parents()` nếu muốn kiểm kê nhiều layer.

**Nhầm 3: `ModuleFinder` thấy JAR là layer đã có module.**

Sai. Discovery, resolution và definition là các bước khác nhau. Phải có một `Configuration` phù hợp và bước định nghĩa layer thì mới nhận được các `Module` runtime của layer đó.

**Nhầm 4: Có module trong `modules()` thì sẽ dùng được `Class.forName()` mặc định.**

Không chắc. Module trong layer tùy chỉnh có thể thuộc loader khác. Hãy lấy đúng loader bằng `findLoader()` cho module trong layer, rồi xét thêm quyền truy cập theo JPMS.

**Nhầm 5: Có cùng `getName()` thì chắc chắn cùng một `Module`.**

Không đúng trong hệ nhiều layer. Luôn xét thêm layer, class loader và đối tượng `Module` khi cần xác định danh tính runtime.

**Nhầm 6: Có thể thêm module vào `layer.modules()`.**

Không. Giá trị trả về là tập không thể sửa. Layer đã định nghĩa không được cập nhật bằng cách thêm phần tử vào tập; muốn có tập module mới, hãy xây cấu hình và layer thích hợp.

## 10. Bài tập tự thực hành

**Bài 1.** Chạy `InspectBootLayer` hai lần: một lần bình thường và một lần với cách khởi chạy có root module khác. So sánh tên module trong `boot.modules()`, giải thích sự khác biệt theo những module đã được resolve khi boot.

**Bài 2.** Với `LayerDemo`, thêm các dòng:

```java
System.out.println(child.modules().contains(
        child.findModule("java.base").orElseThrow()));
System.out.println(child.findModule("java.base")
        .orElseThrow().getLayer() == ModuleLayer.boot());
```

Kết quả lần lượt là `false` và `true`: tìm được `java.base` qua cha không làm cho module đó thuộc tập định nghĩa trực tiếp của layer con.

**Bài 3.** Viết hàm `printLocalModules(ModuleLayer layer)` in tên và tên class loader của module trong layer theo thứ tự alphabet. Với module do bootstrap loader quản lý, cần xử lý `getClassLoader() == null`.

**Bài 4.** Tạo hai layer con riêng biệt từ cùng một modular JAR, cùng dùng boot layer làm cha. Lấy module `com.example.greeter` của từng layer, so sánh `getName()`, `getLayer()` và danh tính đối tượng. Qua đó thấy tên module và danh tính module runtime là hai khái niệm khác nhau.

## 11. Ghi nhớ

- `ModuleLayer` là cấu trúc **runtime** chứa các named module đã được định nghĩa và có quan hệ với những layer cha.
- `layer.modules()` trả về **chỉ** tập `Module` được định nghĩa trực tiếp trong layer, không tự gom tổ tiên.
- `layer.findModule(name)` tra cứu cả layer hiện tại lẫn các layer cha; dùng `module.getLayer()` để biết chính xác nơi định nghĩa.
- `Configuration.modules()` chứa `ResolvedModule`; `ModuleFinder` phát hiện module; `ModuleLayer.modules()` chứa `Module` runtime.
- Việc tìm được module không tự cấp quyền đọc, export, open hoặc khả năng tải class bằng loader bất kỳ.

**API tham khảo:** `java.lang.ModuleLayer`, `java.lang.Module`, `java.lang.module.Configuration`, `java.lang.module.ModuleFinder` và `java.lang.module.ResolvedModule` trong tài liệu JDK.
