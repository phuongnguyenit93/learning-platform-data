# Chọn module gốc và cấu hình cha từ ModuleLayer.boot()

Trong **Java Platform Module System (JPMS)**, một ứng dụng có thể giải quyết các module mới từ một tập JAR hoặc thư mục module và tạo **module layer** con mà không cần đặt trước toàn bộ plugin vào boot layer khi JVM khởi động. Hai quyết định đầu tiên của quá trình này là:

1. **Module gốc (root modules)**: những module có tên được chỉ định làm điểm bắt đầu của việc phân giải.
2. **Cấu hình cha (parent configuration)**: đồ thị module đã phân giải mà layer mới được phép tham chiếu, thường lấy từ `ModuleLayer.boot().configuration()`.

Một lựa chọn sai ở bước này có thể khiến module không được tìm thấy, phụ thuộc không được phân giải, phiên bản được chọn không đúng hoặc layer mới không tạo được. Bài này tập trung vào **cách chọn roots và cấu hình cha, cách Java phân giải phụ thuộc, và quan hệ giữa `Configuration` với `ModuleLayer`**.

## 1. Tách bốn khái niệm quan trọng

| Khái niệm | Java API | Vai trò |
|---|---|---|
| **Module gốc** | `Set<String> roots` | Tập tên module mà ta muốn bắt đầu phân giải, ví dụ `Set.of("plugin.greeting")` |
| **Module finder** | `java.lang.module.ModuleFinder` | Tìm định nghĩa module có thể quan sát được, thường từ các thư mục/JAR |
| **Configuration** | `java.lang.module.Configuration` | Kết quả phân giải: tập `ResolvedModule` cùng các quan hệ đọc module (`reads`) và tham chiếu cấu hình cha |
| **Module layer** | `java.lang.ModuleLayer` | Hiện thực hóa cấu hình thành các đối tượng `Module` ở runtime và gắn module với class loader |

**Điểm mấu chốt:** `Configuration.resolve(...)` chỉ xây dựng và kiểm tra **đồ thị module**. Nó **chưa định nghĩa các module mới vào JVM và chưa nạp class**. Sau đó mới dùng `ModuleLayer.defineModulesWithOneLoader(...)`, `defineModulesWithManyLoaders(...)` hoặc cơ chế tạo layer khác.

Một quy trình điển hình:

```text
JAR / exploded modules
        |
        v
ModuleFinder.of(paths...) ----- Set<String> roots
        |                              |
        +------------+-----------------+
                     |
                     v
ModuleLayer.boot() -> parent Configuration
                     |
                     v
Configuration.resolve(before, after, roots)
                     |
                     v
Configuration con + graph đọc module (readability)
                     |
                     v
bootLayer.defineModulesWithOneLoader(childConfig, parentLoader)
                     |
                     v
ModuleLayer con -> ClassLoader -> class/provider của plugin
```

Cần phân biệt hai kiểu “cha”:

- **Parent `Configuration`**: nơi resolver tìm các module đã phân giải, mang các quan hệ `reads` của đồ thị module.
- **Parent `ClassLoader`**: loader được truyền khi tạo layer để thiết lập quan hệ delegation cho loader mới.

Hai đối tượng này **không phải một**. Đúng loader vẫn không sửa được một đồ thị `requires` thiếu phụ thuộc; ngược lại, cấu hình phân giải thành công chưa bảo đảm class loader phù hợp với mọi package/module.

## 2. ModuleLayer.boot() cung cấp những gì?

`ModuleLayer.boot()` trả về **boot layer** của JVM, được tạo trong lúc JVM khởi động. Boot layer chứa `java.base` và các **named modules thực sự đã được giải quyết khi khởi động**, với các class loader tương ứng. Nó thường là layer cha thuận tiện khi tạo layer bổ sung.

```java
ModuleLayer bootLayer = ModuleLayer.boot();
Configuration parentConfig = bootLayer.configuration();
```

Đoạn trên là mã minh họa trong phương thức Java; cần `import java.lang.module.Configuration;` khi đặt vào một file độc lập.

Có thể quan sát hai cấp khác nhau:

```java
// Module thực sự được định nghĩa trong boot layer:
boolean hasBase = bootLayer.findModule("java.base").isPresent();

// Đồ thị phân giải và các module đã biết trong cấu hình boot:
boolean baseResolved =
        parentConfig.findModule("java.base").isPresent();
```

Ở đây `java.base` luôn hiện diện trong boot layer JVM tiêu chuẩn. Tuy nhiên, **boot layer không đồng nghĩa mọi module có trong JDK hoặc trên ổ đĩa**. Một module có sẵn trong JDK image nhưng chưa được giải quyết lúc khởi động không tự động xuất hiện trong `bootLayer.configuration()`. Tương tự, JAR plugin đặt trong thư mục `plugins` không tự gia nhập boot layer chỉ vì thư mục đó tồn tại.

**Vì sao lấy cấu hình boot làm cha?** Một plugin được phân giải sau khi JVM chạy thường cần `requires java.base` và có thể cần những module thư viện đã có trong boot layer. Đặt `bootLayer.configuration()` làm parent cho phép resolver tái sử dụng các module phù hợp trong đồ thị cha thay vì giải quyết lại chúng vào cấu hình con.

## 3. Chọn root modules đúng với yêu cầu

Root là **tên module** trong descriptor `module-info.java` hoặc tên automatic module (nếu dùng JAR tự động), **không phải tên package, tên class, hay đường dẫn đến JAR**.

Ví dụ:

```java
Set<String> roots = Set.of("plugin.greeting");
```

Nếu trong `module-info.java` có:

```java
module plugin.greeting {
    requires java.logging;
    exports plugin.greeting;
}
```

thì root là `plugin.greeting`. Module `java.logging` được đưa vào đồ thị khi resolver xử lý `requires` nếu nó được tìm thấy theo đúng quy tắc tìm kiếm; **không cần tự thêm mọi phụ thuộc vào `roots`**.

### 3.1. Nguyên tắc chọn roots

- Chọn **module chứa extension/entry point cần sử dụng**, dựa trên metadata và danh sách module được phép.
- Dùng **tên tường minh** theo use case. Ví dụ `Set.of("plugin.csv", "plugin.json")` khi chủ động cần hai module.
- Không lấy toàn bộ tên module trên đĩa làm roots chỉ vì chúng có thể được phát hiện: điều đó có thể nạp thêm extension không mong muốn và làm tăng xung đột.
- Không lấy tên JAR suy đoán tên module. Với explicit module, tin tên từ descriptor; với automatic module, tên suy ra có thể thay đổi theo manifest/tên file và không nên là hợp đồng lâu dài cho plugin.
- Kiểm soát source/version của từng module và các yêu cầu `requires` trước khi công bố cấu hình.
- Với plugin bắt buộc, không để `roots` rỗng như một cách “thành công” giả; với tính năng tùy chọn, danh sách rỗng có thể là trạng thái được xử lý riêng theo chính sách ứng dụng.

Nếu root thiếu, resolver thường báo `FindException`. Nếu root đã có trong parent configuration, cách chọn giữa module ở finder và module cha tùy vào **thứ tự tìm** được nêu ở phần tiếp theo; đừng dùng `findModule()` trên kết quả mà không phân biệt module mới với module được kế thừa.

### 3.2. Roots và phụ thuộc không phải một tập

Giả sử:

```text
plugin.report      (root)
  requires plugin.api
  requires java.logging
plugin.api         (module dependency)
java.logging       (có thể nằm trong boot configuration)
```

Đầu vào thích hợp thường là `Set.of("plugin.report")`. Resolver sẽ theo `requires` để tìm `plugin.api` và `java.logging`. Nếu `plugin.api` không có trong finder hoặc parent, resolution thất bại. Nếu `java.logging` đã nằm trong cấu hình boot, module đó được dùng từ cha và **không được định nghĩa lại trong cấu hình con**.

`requires transitive` tác động đến khả năng đọc module theo chuỗi; `requires static` có ý nghĩa riêng khi compile/runtime. Chúng không làm thay đổi nguyên tắc: **root xác định điểm bắt đầu, resolver xử lý module graph theo descriptor**.

## 4. Chọn cấu hình cha và thứ tự tìm module

Mẫu Java 17 thông dụng:

```java
ModuleLayer parentLayer = ModuleLayer.boot();

ModuleFinder before = ModuleFinder.of(Path.of("mods"));
ModuleFinder after = ModuleFinder.of(); // Finder rỗng
Set<String> roots = Set.of("plugin.greeting");

Configuration childConfig = parentLayer.configuration()
        .resolve(before, after, roots);
```

Đây là đoạn minh họa trong một phương thức, cần import `java.lang.module.Configuration`, `java.lang.module.ModuleFinder`, `java.nio.file.Path` và `java.util.Set`.

Đối với mỗi root hoặc dependency, resolver của `Configuration.resolve(...)` dùng thứ tự tìm kiếm:

1. **`before` finder**: tìm module trong nguồn ưu tiên (ví dụ thư mục `mods` hoặc tập JAR được chọn).
2. **Parent configurations**: tìm theo thứ tự parent được cung cấp; với instance method ở trên chỉ có parent là `parentLayer.configuration()`.
3. **`after` finder**: tìm khi hai nguồn trước không có module tương ứng.

Chính vì `before` được xét trước, nó có thể đưa ra module trùng tên với một module đã nằm ở parent. Vì thế cần tránh tùy tiện cho plugin thay thế tên/phiên bản thư viện của host; quyết định rõ nguồn nào là authoritative, kiểm tra module trùng tên và thử nghiệm với đúng cấu hình runtime.

`ModuleFinder.of()` **không có đối số** tạo finder rỗng, không phải tìm ở working directory. Khi cần tra cứu module trên hệ thống, Java còn có `ModuleFinder.ofSystem()`, nhưng đừng tự thêm nó vào mọi pipeline: cần xem module nào đã được boot giải quyết và cách tạo loader/layer cho module mới. Không phải mọi module JDK chưa có trong boot đều có thể tùy tiện được định nghĩa qua loader plugin.

### 4.1. Instance method và static method tương đương về parent

Nếu `parent` là một `Configuration`:

```java
Configuration child = parent.resolve(before, after, roots);
```

thì tương đương về cách cấu hình parent với:

```java
Configuration child = Configuration.resolve(
        before, List.of(parent), after, roots);
```

Cú pháp static nhận **danh sách parent configurations** và có ích khi tạo đồ thị có nhiều parent. Hai đoạn là minh họa riêng trong một phương thức với biến đã khai báo; đoạn thứ hai cần `import java.util.List;`.

**Không tự thay `Configuration.empty()` cho cấu hình boot** để “bắt đầu sạch” nếu plugin phải đọc các module của host. Parent rỗng làm thay đổi toàn bộ tập module sẵn có, có thể thiếu cả những module cần thiết trong quá trình giải quyết và khiến việc tạo layer không thỏa các điều kiện module runtime.

## 5. Ví dụ chạy được với JDK 17: một root và một parent boot

Ví dụ đầy đủ sau có:

- Module plugin tên `plugin.greeting` được biên dịch thành **exploded module** trong thư mục `mods`.
- Chương trình host `LayerRootsDemo` chạy trên classpath; host tự chọn root `plugin.greeting` từ thư mục `mods`.
- Host lấy cấu hình cha bằng `ModuleLayer.boot().configuration()`, phân giải module mới rồi định nghĩa layer con.
- Cuối cùng host lấy class loader của module và gọi một phương thức public trong package được `exports`.

**Không đưa thư mục `mods` vào `--module-path` khi chạy host trong ví dụ này**: host sẽ tự định vị nó qua `ModuleFinder.of(Path.of("mods"))`.

### 5.1. Cấu trúc thư mục

```text
project/
  LayerRootsDemo.java
  src/
    plugin.greeting/
      module-info.java
      plugin/
        greeting/
          Greeting.java
```

Tệp `src/plugin.greeting/module-info.java`:

```java
module plugin.greeting {
    exports plugin.greeting;
}
```

Tệp `src/plugin.greeting/plugin/greeting/Greeting.java`:

```java
package plugin.greeting;

public final class Greeting {
    private Greeting() {}

    public static String message() {
        return "Hello from plugin.greeting";
    }
}
```

Tệp `LayerRootsDemo.java`:

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.lang.module.ResolvedModule;
import java.nio.file.Path;
import java.util.Set;

public class LayerRootsDemo {
    public static void main(String[] args) throws Exception {
        String rootName = "plugin.greeting";

        // 1. Boot layer là layer cha; không tự nạp plugin của bài.
        ModuleLayer boot = ModuleLayer.boot();
        Configuration parentConfig = boot.configuration();

        // 2. Chỉ nhận module từ thư mục mods như một nguồn mới.
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
        if (finder.find(rootName).isEmpty()) {
            throw new IllegalStateException("Root missing: " + rootName);
        }

        // 3. Tên module, không phải path hoặc tên class.
        Set<String> roots = Set.of(rootName);

        // 4. Phân giải đồ thị module, dùng boot config làm cha.
        Configuration childConfig = parentConfig.resolve(
                finder,
                ModuleFinder.of(),
                roots);

        // 5. Kiểm tra điều thực sự được phân giải trong cấu hình mới.
        var newModules = childConfig.modules().stream()
                .map(ResolvedModule::name)
                .sorted()
                .toList();

        // 6. Định nghĩa module ở runtime bằng một loader mới.
        ModuleLayer childLayer = boot.defineModulesWithOneLoader(
                childConfig,
                ClassLoader.getSystemClassLoader());

        // 7. Dùng loader thuộc child layer để lấy class plugin.
        ClassLoader pluginLoader = childLayer.findLoader(rootName);
        Class<?> greeting = pluginLoader.loadClass(
                "plugin.greeting.Greeting");
        String message = (String) greeting
                .getMethod("message")
                .invoke(null);

        System.out.println("Boot has java.base: "
                + boot.findModule("java.base").isPresent());
        System.out.println("Boot has plugin.greeting: "
                + boot.findModule(rootName).isPresent());
        System.out.println("New modules: " + newModules);
        System.out.println("Child config sees java.base: "
                + childConfig.findModule("java.base").isPresent());
        System.out.println("Child layer owns plugin: "
                + childLayer.modules().stream()
                    .anyMatch(m -> m.getName().equals(rootName)));
        System.out.println("Message: " + message);
    }
}
```

### 5.2. Biên dịch và chạy

Từ thư mục `project`, với JDK 17 trở lên:

```bash
javac --module-source-path src -d mods -m plugin.greeting
javac -d out LayerRootsDemo.java
java -cp out LayerRootsDemo
```

Lệnh đầu tạo `mods/plugin.greeting/module-info.class` và `mods/plugin.greeting/plugin/greeting/Greeting.class`. `ModuleFinder.of(Path.of("mods"))` có thể tìm module dạng thư mục đã biên dịch. Host được biên dịch riêng và chỉ đưa `out` vào classpath khi chạy.

Stdout **chính xác** với cấu trúc trên, khi ứng dụng khởi động mà chưa nạp sẵn `plugin.greeting` vào boot layer:

```text
Boot has java.base: true
Boot has plugin.greeting: false
New modules: [plugin.greeting]
Child config sees java.base: true
Child layer owns plugin: true
Message: Hello from plugin.greeting
```

### 5.3. Đọc kết quả và hiểu module nào thuộc layer nào

- `Boot has java.base: true`: `java.base` được JVM đưa vào boot layer.
- `Boot has plugin.greeting: false`: host chạy chỉ từ classpath `out`; module plugin chưa được resolve khi JVM bắt đầu.
- `New modules: [plugin.greeting]`: `childConfig.modules()` trả **các module thuộc chính configuration mới**, không bao gồm `java.base` kế thừa từ cha.
- `Child config sees java.base: true`: `childConfig.findModule("java.base")` tìm được trong **cấu hình cha**. Điều này không có nghĩa `java.base` đã được định nghĩa lần nữa trong child layer.
- `Child layer owns plugin: true`: layer mới thật sự có `Module` cho `plugin.greeting`.
- `Message: ...`: loader của child layer nạp được class và package `plugin.greeting` đã được module `exports` để phương thức public có thể được gọi từ host thông qua reflection.

Một kiểm tra rất quan trọng: **`Configuration.findModule(name)` có thể tìm thấy module ở parent configuration**, còn `Configuration.modules()` chỉ liệt kê những module của cấu hình hiện tại. Tương tự, `ModuleLayer.findModule(name)` có thể tìm ở parent layers, trong khi `ModuleLayer.modules()` chỉ liệt kê module trong layer đó. Khi cần biết module có **thực sự mới** hay không, không dựa duy nhất vào `findModule(...).isPresent()`.

### 5.4. Nếu root không tồn tại thì sao?

Giả sử đổi `rootName` thành `plugin.unknown` mà thư mục `mods` không chứa module ấy:

- Trong ví dụ, câu lệnh `finder.find(rootName)` sẽ trả `Optional.empty()` và ứng dụng báo `Root missing: plugin.unknown`.
- Nếu bỏ preflight riêng và gọi `resolve(...)` với một root không tìm thấy qua `before`, parent và `after`, API sẽ ném `FindException`.
- Nếu module có nhưng thiếu phụ thuộc `requires`, `resolve(...)` cũng có thể thất bại với `FindException` hoặc báo lỗi khác theo tính nhất quán của graph.

Đây là lỗi **phân giải module**, xảy ra **trước khi** code gọi `pluginLoader.loadClass(...)`. Vì vậy cần phân biệt với lỗi `ClassNotFoundException`, lỗi truy cập do `exports`/`opens` và lỗi khởi tạo class ở giai đoạn sau.

## 6. Chọn nhiều roots và xác định phụ thuộc có được thừa hưởng

### 6.1. Hai module cần được kích hoạt

Nếu host cần độc lập hai extension:

```java
Set<String> roots = Set.of("plugin.greeting", "plugin.reporting");
Configuration childConfig = boot.configuration()
        .resolve(finder, ModuleFinder.of(), roots);
```

Đây là đoạn minh họa sử dụng biến `boot` và `finder` đã khai báo; hai module phải quan sát được trong finder hoặc parent configuration theo quy tắc resolution. Nếu `plugin.reporting` có `requires plugin.greeting`, chỉ đặt `plugin.reporting` làm root cũng có thể đủ để hai module được giải quyết; không cần nhân đôi root nếu `plugin.greeting` chỉ là phụ thuộc kỹ thuật. Ngược lại, nếu hai module cung cấp hai tính năng độc lập và không có `requires` lẫn nhau, chỉ root `plugin.reporting` sẽ không tự kéo `plugin.greeting` vào.

### 6.2. Cha có sẵn module mà plugin cần

Giả sử `plugin.reporting` khai báo `requires java.logging;`. Nếu `java.logging` có trong boot configuration, module mới có thể dùng bản đã phân giải ở đó. Nếu nó không có trong boot configuration, resolver vẫn phải tìm được module này từ `before` hoặc `after`. **Không giả định `ModuleLayer.boot()` chứa toàn bộ module Java SE.**

Trong môi trường triển khai thực, cần kiểm tra:

- Runtime image có bao gồm module cần dùng không (`jlink` có thể tạo image tối giản)?
- Khi khởi động, module nào thật sự được đưa vào boot layer?
- Extension có yêu cầu một API module của host được định nghĩa ở boot hoặc parent layer khác không?
- Module nào phải nằm trong child configuration để không tạo nhiều bản không tương thích của API chung?
- Module path và version có được pin/kiểm soát không?

Khi cần module JDK không có trong boot, cân nhắc cấu hình khởi động (`--add-modules`) hoặc thiết kế finder/layer phù hợp thay vì mặc nhiên cho tất cả module hệ thống vào lớp plugin.

### 6.3. Root module và provider service là hai khái niệm khác

`resolve(...)` dựa vào **roots và `requires`**. Nó không tự coi mọi provider được khai báo bằng `provides ... with ...` là root.

Nếu module host khai báo `uses some.api.Service` và muốn resolver tự bổ sung các module cung cấp implementation từ finder, có thể dùng:

```java
Configuration childConfig = boot.configuration()
        .resolveAndBind(finder, ModuleFinder.of(), roots);
```

`resolveAndBind` thực hiện thêm bước **service binding**, có thể kéo vào graph những module cung cấp dịch vụ thông qua `provides` mà không được chỉ định tường minh làm root. Điều này có thể mở rộng tập module được phân giải, nên phải kiểm soát nguồn finder và phạm vi trust. Để biết provider nào thực sự được chọn sử dụng khi chạy, còn cần hợp đồng service loading/selection riêng; `resolveAndBind` không thay cho chính sách chọn provider nghiệp vụ.

## 7. Trường hợp có nhiều parent layers

Dạng phổ biến nhất là một parent: `ModuleLayer.boot()`. Nhưng JPMS cũng hỗ trợ một cấu hình con có **nhiều parent configurations**:

```java
Configuration newConfig = Configuration.resolve(
        finder,
        List.of(parentA.configuration(), parentB.configuration()),
        ModuleFinder.of(),
        roots);
```

Và khi tạo layer với nhiều parent, phải dùng biến thể static tương ứng:

```java
ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithOneLoader(
                newConfig,
                List.of(parentA, parentB),
                ClassLoader.getSystemClassLoader());
ModuleLayer newLayer = controller.layer();
```

Hai đoạn **chỉ là minh họa** trong một phương thức có biến `finder`, `roots`, `parentA` và `parentB` đã định nghĩa; cần import `java.util.List` và `java.lang.module.Configuration`.

Danh sách parent của `Configuration` phải khớp **đúng thứ tự và đúng đối tượng cấu hình** của các parent layers khi tạo layer; nếu không, thao tác tạo layer có thể ném `IllegalArgumentException`. Cần kiểm soát xung đột tên module, target operating system và class loader delegation. Đây là lý do nên dùng **một parent boot** trừ khi thực sự cần một đồ thị layer phức tạp.

## 8. Xác thực roots, kiểm tra graph và phân biệt các loại lỗi

Một hệ thống plugin nghiêm túc nên có một giai đoạn **preflight** trước khi `resolve(...)`:

1. **Đọc metadata đáng tin cậy:** tên module, version/build identity, yêu cầu API, danh sách plugin được phép.
2. **Xác định roots:** module nào thật sự cần được kích hoạt; tránh lấy mọi module trong thư mục một cách mặc định.
3. **Kiểm tra finder:** root/module có xuất hiện tại đường dẫn dự kiến; file JAR có descriptor hợp lệ; artifact không bị thay đổi trong lúc dùng.
4. **Chọn parent:** boot layer hoặc layer chứa API chung mà plugin cần; ghi rõ lý do sử dụng parent đó.
5. **Giải quyết graph:** dùng `resolve` hoặc `resolveAndBind` tùy có cần service binding.
6. **Kiểm tra kết quả:** in/log `childConfig.modules()`; xác nhận module cần tạo thực sự thuộc graph mới; đánh giá duplicate package/module và compatibility.
7. **Định nghĩa layer:** chọn loader phù hợp và phân biệt lỗi ở thời điểm tạo layer.
8. **Khởi tạo extension:** nạp class, tìm service, thực thi health check, đăng ký/rollback ở ranh giới rõ ràng.

### 8.1. Các nhóm lỗi khác nhau

| Giai đoạn | Lỗi/triệu chứng thường gặp | Cần kiểm tra |
|---|---|---|
| `ModuleFinder` | `FindException` hoặc không tìm thấy module | Path, descriptor, JAR, tên module/automatic module |
| `Configuration.resolve` | `FindException` | Root/dependency không quan sát được, module descriptor không hợp lệ, lỗi đọc artifact |
| `Configuration.resolve` | `ResolutionException` | Cycle trong `requires`, xung đột tên module hoặc package/readability graph |
| `defineModulesWithOneLoader` | `LayerInstantiationException` | Package trùng giữa module cùng loader, split delegation, tên/package không được phép |
| `defineModules...` | `IllegalArgumentException` | `Configuration` có parent không khớp layer cha, hoặc cấu hình dùng sai biến thể API |
| Nạp class | `ClassNotFoundException` | Class không có trong module, sai loader hoặc sai tên binary class |
| Reflection/access | `IllegalAccessException` hoặc `InaccessibleObjectException` | `exports`/`opens`, quyền truy cập tại runtime |
| Chạy plugin | Lỗi nghiệp vụ hoặc linkage khác | API compatibility, version, dependency và trạng thái lifecycle |

`Configuration` là kết quả kiểm tra tính nhất quán ở mức **module graph**; không thay thế kiểm thử class loading, constructor, service provider, thao tác I/O hay xử lý nghiệp vụ.

### 8.2. Đọc những gì thực sự được giải quyết

Để kiểm tra root và dependencies, có thể liệt kê module trong **cấu hình con**:

```java
childConfig.modules().stream()
        .map(ResolvedModule::name)
        .sorted()
        .forEach(System.out::println);
```

Đây là đoạn minh họa cần `import java.lang.module.ResolvedModule;` và biến `childConfig` có sẵn. Sắp xếp để log dễ so sánh, vì thứ tự duyệt của tập module không phải hợp đồng nghiệp vụ.

Nếu cần xem module hiện tại đọc module nào, `ResolvedModule.reads()` cho tập các `ResolvedModule` có quan hệ readability. Các đỉnh đó có thể thuộc **cấu hình hiện tại hoặc cấu hình cha**. Ví dụ một plugin `requires java.base` sẽ có quan hệ đọc `java.base` dù `java.base` không nằm trong `childConfig.modules()`.

## 9. Các lỗi thiết kế thường gặp

1. **Dùng tên JAR thay tên module làm root.** Resolver nhận tên module; hãy kiểm tra `module-info.java` hoặc `ModuleReference.descriptor().name()`.
2. **Cho rằng mọi module trong `mods` sẽ tự được resolve.** `ModuleFinder` chỉ cho biết **có thể tìm thấy**; tập roots và dependencies mới quyết định graph.
3. **Nhầm boot layer với toàn bộ module có trong JDK.** Boot chỉ chứa module được resolve khi JVM khởi động.
4. **Lấy `Configuration.empty()` để “tự do hơn”.** Điều đó làm mất graph cha mà extension dự định dùng; không phải cách giải quyết thiếu dependency.
5. **Đặt mọi dependency vào roots.** `requires` đã thể hiện quan hệ phụ thuộc; roots nên phản ánh entry points/tính năng được chủ ý kích hoạt.
6. **Tưởng `resolve` đã load JAR/class.** Nó xây graph; cần tạo `ModuleLayer` và gọi class/service tương ứng sau đó.
7. **Cho rằng `findModule` trên cấu hình con nghĩa là module mới.** Phương thức có thể tìm trong parent; hãy đối chiếu `modules()`.
8. **Không hiểu thứ tự `before -> parents -> after`.** Có thể phân giải phiên bản khác kỳ vọng khi finder ưu tiên module trùng tên của host.
9. **Định nghĩa child layer với parent layers không khớp parent configurations.** Đây là lỗi API/lifecycle; cần dùng đúng cặp cấu hình–layer.
10. **Tin rằng `resolve` tự kéo mọi service provider.** Chỉ `resolveAndBind` mới bổ sung service binding theo mô tả JPMS.
11. **Cho rằng thêm JAR vào thư mục làm module xuất hiện tức thì.** Finder/Configuration/layer hiện hữu không tự trở thành hệ thống giám sát và hot swap.
12. **Xem module layer là sandbox.** JPMS giúp tổ chức và kiểm soát module readability/access, không tạo ranh giới bảo mật cấp tiến trình cho mã plugin không đáng tin.

## 10. Checklist áp dụng thực tế

| Câu hỏi | Bằng chứng nên có |
|---|---|
| Root là module nào? | Tên module tường minh từ descriptor, ID/version của extension |
| Root có nằm trong nguồn plugin được phép? | `finder.find(root)` trả module reference hợp lệ; artifact đã xác thực |
| Các module host nào cần chia sẻ? | Có trong parent configuration/layer đã chọn |
| Module phụ thuộc được tìm bằng cách nào? | Finder `before`, parent hoặc `after` theo thứ tự được công bố |
| Module nào thuộc chính configuration mới? | `childConfig.modules()` |
| Module nào chỉ được kế thừa từ cha? | `childConfig.findModule(name)` nhưng không có trong `childConfig.modules()` |
| Khi nào mới tạo class loader và Module runtime? | Khi gọi phương thức `defineModules...` |
| Dùng một hay nhiều loader? | Đánh giá split package/delegation, isolation và vòng đời |
| Service providers cần tự thêm vào graph? | Quyết định `resolve` hay `resolveAndBind` |
| Lỗi nào cần báo rõ? | Không thấy root/dependency, resolution conflict, layer instantiation, class loading, access |
| Khi cập nhật plugin sẽ làm gì? | Tạo configuration/layer mới, chuyển tham chiếu, quản lý tài nguyên/rollback |

### Tham khảo API Java 17

- [ModuleLayer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html)
- [Configuration — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html)
- [ModuleFinder — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html)

**Ghi nhớ:** chọn **root** bằng tên của module thực sự muốn kích hoạt; chọn **parent configuration** để kế thừa đồ thị đã phân giải của host, thường qua `ModuleLayer.boot().configuration()`; gọi `resolve(...)` để xây graph, sau đó **mới** định nghĩa layer con và nạp class. Phân biệt module **mới trong child** với module **có thể tìm trong parent** giúp hệ thống mở rộng Java vận hành có thể dự đoán và chẩn đoán được.