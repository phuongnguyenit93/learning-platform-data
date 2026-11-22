# Truy vấn `ModuleLayer` bằng `findModule` và `modules`

## Mục tiêu

Sau bài này, bạn có thể:

- Tra cứu một module đã được định nghĩa trong `ModuleLayer` theo tên bằng `findModule(String)`.
- Liệt kê các module thuộc **chính layer hiện tại** bằng `modules()`.
- Phân biệt việc tìm kiếm xuyên qua layer cha với việc liệt kê module của một layer.
- Xử lý kết quả `Optional<Module>` an toàn và nhận biết những giới hạn của hai API khi làm việc với Java Platform Module System (JPMS).

## 1. `ModuleLayer` là gì?

Trong JPMS (Java 9+), `ModuleLayer` biểu diễn một nhóm module đã được **định nghĩa ở thời điểm chạy** cùng quan hệ cha giữa các layer. Mỗi module có tên thuộc layer là một đối tượng `java.lang.Module`. Layer giúp ứng dụng tổ chức những nhóm module, chẳng hạn các plugin được nạp vào layer con, trong khi vẫn dựa trên các module hệ thống ở layer cha.

Layer khởi động của JVM có thể lấy bằng:

```java
ModuleLayer boot = ModuleLayer.boot();
```

Các module hiện diện trong `boot` phụ thuộc vào cấu hình runtime, module graph được giải quyết khi khởi động và bản phân phối JDK; `java.base` là ví dụ chắc chắn thuộc môi trường Java module thông thường. Không nên giả định mọi module của JDK đều xuất hiện trong một layer ở mọi cách chạy.

Hai API thường được dùng để quan sát layer là:

```java
Optional<Module> findModule(String name);
Set<Module> modules();
```

Cả hai đều truy vấn những module đã có trong layer; chúng **không tự tìm JAR trên ổ đĩa, không tự resolve cấu hình và không tạo layer mới**.

## 2. `findModule(String name)` — tra cứu module theo tên

`findModule` nhận **tên module** (`String`) và trả về `Optional<Module>`:

```java
ModuleLayer boot = ModuleLayer.boot();

Optional<Module> maybeBase = boot.findModule("java.base");
Module base = maybeBase.orElseThrow();
System.out.println(base.getName()); // java.base

Optional<Module> missing = boot.findModule("com.example.does.not.exist");
System.out.println(missing.isPresent()); // false
```

Cách sử dụng an toàn tùy mục tiêu:

- `ifPresent(...)` khi module là tùy chọn và chỉ cần xử lý nếu tồn tại.
- `orElseThrow(...)` khi việc thiếu module là lỗi nghiệp vụ.
- `map(...)` hoặc `flatMap(...)` khi cần biến đổi giá trị mà vẫn giữ ngữ nghĩa có/không.
- `isPresent()` hoặc `isEmpty()` để kiểm tra sự tồn tại; `isEmpty()` có từ Java 11.

Ví dụ không gọi `Optional.get()` khi chưa kiểm tra:

```java
String requestedName = "java.sql";
ModuleLayer boot = ModuleLayer.boot();

boot.findModule(requestedName).ifPresentOrElse(
    module -> System.out.println("Tìm thấy: " + module.getName()),
    () -> System.out.println("Module chưa có trong layer hoặc các layer cha")
);
```

`Optional.ifPresentOrElse` có từ Java 9. Đối số phải là **tên module** như `java.base`, `com.example.payment`, không phải tên package, class hoặc đường dẫn file.

### Phạm vi tìm kiếm: layer hiện tại và các layer cha

`layer.findModule(name)` trước hết tìm module trong `layer` đang xét. Khi không thấy ở đó, API tiếp tục tìm trong các **parent layers**. Vì vậy, kết quả có thể là module thuộc layer cha, không thuộc `layer.modules()`.

Hình dung cấu trúc:

```text
Boot layer
  ├── java.base
  └── ...các module đã được giải quyết lúc khởi động
        ↑
Plugin layer
  └── com.example.plugin
```

Khi tra từ plugin layer:

- `pluginLayer.findModule("com.example.plugin")` có thể trả về module của plugin layer.
- `pluginLayer.findModule("java.base")` có thể trả về `java.base` từ boot layer cha.
- `pluginLayer.modules()` chỉ chứa các module được định nghĩa trong plugin layer.

Với các layer có nhiều cha, không nên dựa vào việc trùng tên module ở các nhánh cha để suy ra một module duy nhất theo tên. Khi cần biết module thật sự thuộc layer nào, kiểm tra `module.getLayer()` hoặc thao tác trực tiếp với `modules()` của layer mong muốn.

## 3. `modules()` — liệt kê module thuộc chính layer

`modules()` trả về một `Set<Module>` **không thể sửa đổi** gồm những module được định nghĩa trong layer được gọi.

```java
ModuleLayer boot = ModuleLayer.boot();
Set<Module> bootModules = boot.modules();

System.out.println("Số module trong boot layer: " + bootModules.size());

bootModules.stream()
    .map(Module::getName)
    .sorted()
    .forEach(System.out::println);
```

Các điểm cần nhớ:

1. Danh sách không bao gồm module chỉ có trong layer cha.
2. Thứ tự duyệt `Set` không phải thứ tự tên module. Dùng `sorted()` nếu cần kết quả ổn định, dễ đọc hoặc kiểm thử.
3. Tập kết quả không cho phép `add`/`remove`. Muốn lọc hoặc tích lũy, tạo một collection khác.
4. Một layer hợp lệ có thể chứa **0 module**; khi đó `modules().isEmpty()` là `true`.
5. `Set<Module>` chứa các đối tượng module thật; khi in thông tin, lấy tên bằng `Module::getName` hoặc truy cập metadata bằng `getDescriptor()` nếu cần.

Ví dụ lọc module theo tiền tố tên:

```java
List<String> javaModules = ModuleLayer.boot().modules().stream()
    .map(Module::getName)
    .filter(name -> name.startsWith("java."))
    .sorted()
    .toList(); // Stream.toList() có từ Java 16

System.out.println(javaModules);
```

Với Java 9–15, thay `.toList()` bằng `.collect(Collectors.toList())` và import `java.util.stream.Collectors`.

## 4. So sánh nhanh hai phương thức

| Câu hỏi | `findModule(String)` | `modules()` |
|---|---|---|
| Dùng để làm gì? | Tìm **một** module theo tên | Lấy **tất cả** module được định nghĩa trong layer |
| Kiểu trả về | `Optional<Module>` | `Set<Module>` |
| Module ở layer hiện tại | Có thể tìm thấy | Có trong tập |
| Module chỉ có ở layer cha | Có thể tìm thấy | Không có trong tập |
| Không tìm thấy / layer rỗng | `Optional.empty()` | `Set` rỗng |
| Có thay đổi module graph? | Không | Không |
| Tình huống phù hợp | Kiểm tra module theo tên, lấy đối tượng module | Thống kê, lọc, liệt kê module của layer |

**Lỗi suy luận thường gặp:** thấy `layer.findModule("java.base").isPresent() == true` rồi kết luận `layer.modules()` chứa `java.base`. Điều đó chỉ đúng nếu `java.base` thực sự được định nghĩa trong chính layer này. Với layer con, module có thể đến từ cha.

## 5. Ví dụ chạy độc lập: layer khởi động và layer rỗng

Lưu thành `LayerQueryDemo.java`:

```java
import java.util.Optional;
import java.util.Set;

public class LayerQueryDemo {
    public static void main(String[] args) {
        ModuleLayer boot = ModuleLayer.boot();

        // Tìm module cụ thể.
        Optional<Module> javaBase = boot.findModule("java.base");
        System.out.println("java.base có trong boot? " + javaBase.isPresent());

        // Liệt kê module của boot, chỉ in tối đa 10 tên.
        Set<Module> bootModules = boot.modules();
        System.out.println("Số module trong boot: " + bootModules.size());
        bootModules.stream()
            .map(Module::getName)
            .sorted()
            .limit(10)
            .forEach(name -> System.out.println(" - " + name));

        // Layer rỗng đặc biệt không có module và không có cha.
        ModuleLayer empty = ModuleLayer.empty();
        System.out.println("empty.modules().isEmpty(): "
            + empty.modules().isEmpty());
        System.out.println("empty.findModule(\"java.base\").isPresent(): "
            + empty.findModule("java.base").isPresent());

        // Đối tượng Module biết layer sở hữu nó.
        javaBase.ifPresent(module ->
            System.out.println("java.base thuộc boot: "
                + (module.getLayer() == boot)));
    }
}
```

Chạy bằng JDK 9 trở lên:

```bash
javac LayerQueryDemo.java
java LayerQueryDemo
```

Các kết luận có thể xác nhận từ ví dụ:

- `boot.findModule("java.base")` tìm thấy `java.base`.
- `boot.modules()` đưa ra tập module đã định nghĩa trong boot, với số lượng phụ thuộc môi trường.
- `ModuleLayer.empty()` không chứa module, cũng không có cha để tìm tiếp: cả hai truy vấn đều cho kết quả rỗng.
- `module.getLayer() == boot` kiểm tra vị trí định nghĩa của module trả về.

## 6. Phân biệt tìm kiếm xuyên cha và liệt kê toàn bộ cây layer

Giả sử ứng dụng có `pluginLayer` được tạo từ một `Configuration` với `boot` làm layer cha. Khi đó:

```java
// pluginLayer là ModuleLayer con đã được tạo hợp lệ trước đó.
Optional<Module> baseFromParent = pluginLayer.findModule("java.base");
Set<Module> localOnly = pluginLayer.modules();

boolean javaBaseDefinedHere = localOnly.stream()
    .anyMatch(m -> "java.base".equals(m.getName()));
```

`baseFromParent` có thể chứa `java.base` mặc dù `javaBaseDefinedHere` là `false`. Điều này đặc biệt quan trọng khi viết hệ thống plugin, nơi bạn muốn phân biệt các module của plugin với module nền tảng.

Nếu yêu cầu là **liệt kê mọi module của layer và tất cả layer cha**, `modules()` một lần là chưa đủ. Duyệt `parents()` và hợp nhất các tập module:

```java
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.LinkedHashSet;
import java.util.Set;

public class ModuleLayerTree {
    public static Set<Module> collectModules(ModuleLayer start) {
        Set<ModuleLayer> visited =
            Collections.newSetFromMap(new IdentityHashMap<>());
        Set<Module> collected = new LinkedHashSet<>();
        Deque<ModuleLayer> queue = new ArrayDeque<>();
        queue.add(start);

        while (!queue.isEmpty()) {
            ModuleLayer layer = queue.removeFirst();
            if (!visited.add(layer)) {
                continue;
            }
            collected.addAll(layer.modules());
            queue.addAll(layer.parents());
        }

        return Collections.unmodifiableSet(collected);
    }
}
```

Lý do sử dụng `visited`: quan hệ cha có thể tạo thành một **đồ thị có hướng không chu trình** với nhiều nhánh cùng trỏ tới một ancestor, nên một layer cha có thể được gặp qua nhiều đường. `IdentityHashMap` ở đây giúp đánh dấu từng đối tượng `ModuleLayer` đã duyệt. Nếu chỉ muốn đếm module của **một layer**, hãy dùng trực tiếp `layer.modules().size()`, không cần hàm duyệt này.

## 7. Những điều API không làm thay bạn

### Không tự nạp module

`findModule("com.example.plugin")` trả về rỗng nếu module đó chưa được định nghĩa trong layer hoặc các layer cha, kể cả khi trên ổ đĩa có JAR mang tên tương ứng. Để tạo layer mới với module của ứng dụng, quy trình tổng quát là:

1. Xác định module artifacts bằng `ModuleFinder`.
2. Resolve một `Configuration` từ các module gốc và parent configuration.
3. Định nghĩa `ModuleLayer` mới với class loader phù hợp.
4. Sau đó mới dùng `findModule` và `modules` trên layer đã tạo.

### Không đồng nghĩa với quyền truy cập

Tìm được một `Module` không chứng minh module đang gọi **đọc được** module đó, hoặc truy cập được package bên trong. Khi cần kiểm tra ở mức module:

```java
Module caller = LayerQueryDemo.class.getModule();

boot.findModule("java.base").ifPresent(target -> {
    System.out.println("Caller đọc được java.base? "
        + caller.canRead(target));
    System.out.println("Package java.lang được export cho caller? "
        + target.isExported("java.lang", caller));
});
```

Trong đoạn ví dụ trên, `boot` là biến đã được khởi tạo (`ModuleLayer.boot()`). `canRead` kiểm tra quan hệ readability; `isExported` kiểm tra export của một package tới module gọi. Các kiểm tra về mở package cho reflection dùng `isOpen` tương ứng. Chúng là những khái niệm khác với việc **module có tồn tại trong layer hay không**.

### Không nhầm với `Configuration.findModule`

- `ModuleLayer.findModule(String)` trả về `Optional<Module>`, tức module ở runtime sau khi được định nghĩa.
- `Configuration.findModule(String)` trả về `Optional<ResolvedModule>` và thuộc giai đoạn giải quyết module graph.

Dùng `Configuration` khi bạn cần làm việc với cấu hình đã resolve; dùng `ModuleLayer` khi muốn quan sát các module runtime.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách làm |
|---|---|---|
| `findModule(...)` rỗng dù có file JAR | JAR chưa được resolve/define vào layer phù hợp | Kiểm tra bước tạo `Configuration` và `ModuleLayer` |
| `findModule(...)` có giá trị nhưng `modules()` không chứa module đó | Module nằm trong parent layer | So sánh `module.getLayer()` với layer đang xét |
| `modules().add(...)` báo `UnsupportedOperationException` | Tập trả về không thể sửa đổi | Sao chép sang `HashSet`/`LinkedHashSet` nếu cần |
| Kết quả liệt kê thay đổi thứ tự | `Set` không cam kết thứ tự trình bày | `map(Module::getName).sorted()` |
| Gọi `optional.get()` ném `NoSuchElementException` | Không có module được tìm thấy | Dùng `orElseThrow` với thông báo hoặc `ifPresent` |
| Tìm tên class/package mà không ra module | `findModule` chỉ nhận tên module | Xác định tên module trong `module-info.java` hay descriptor |

## 9. Thực hành

1. Dùng `ModuleLayer.boot()`, tìm `java.base` và một tên module không tồn tại; in thông báo riêng cho hai trường hợp.
2. In tên tất cả module bắt đầu bằng `java.` trong boot layer, theo thứ tự từ điển.
3. Viết hàm `boolean isLocalModule(ModuleLayer layer, String name)` để kiểm tra module có thuộc **chính layer** không, dựa trên `modules()`. So sánh với kết quả `layer.findModule(name).isPresent()` khi bạn có một layer con.
4. Với một layer có cha, thử `collectModules(layer)` và so sánh số module thu được với `layer.modules().size()`; giải thích vì sao hai số có thể khác.

Gợi ý cho bài 3:

```java
static boolean isLocalModule(ModuleLayer layer, String name) {
    return layer.modules().stream()
        .anyMatch(module -> name.equals(module.getName()));
}
```

## Ghi nhớ

- `findModule(name)` tìm một module theo tên trong layer hiện tại **và các layer cha**; kết quả là `Optional<Module>`.
- `modules()` trả về tập `Set<Module>` không thể sửa đổi của **chính layer hiện tại**.
- Muốn xác định module nằm ở layer nào, dùng `module.getLayer()`; muốn liệt kê xuyên parent layers, tự duyệt `parents()`.
- Hai API hỗ trợ **truy vấn trạng thái runtime** của JPMS, không tự resolve, nạp module hay cấp quyền đọc/truy cập module.

Tham khảo API của JDK: `java.lang.ModuleLayer`, `java.lang.Module`, `java.lang.module.Configuration` và `java.lang.module.ModuleFinder`.