# Xem ModuleReference, ModuleDescriptor và các phụ thuộc được khai báo

## 1. Mục tiêu: đọc được “module nói gì” trước khi JVM nối các module

Trong Java Platform Module System (JPMS, Java 9+), một module có **tên**, chứa các package/class/resource và khai báo quan hệ với module khác. Khi xây hệ thống plugin có module path hoặc `ModuleLayer` riêng, ta thường cần trả lời:

- Tệp JAR/module đang tìm được có **module name** nào? Là explicit module hay automatic module?
- Module **khai báo** `requires` tới những module nào, với `transitive` hay `static`?
- Module `exports`/`opens` package nào, `uses` service nào và `provides` implementation nào?
- JVM đã **resolve** những module nào và thiết lập quan hệ **readability** thực tế ra sao?
- Nếu thiếu dependency, cần nhìn vào metadata, vị trí module, lỗi resolution hay class loader?

Ba API chính của bài:

| API | Đại diện cho | Dùng khi |
| --- | --- | --- |
| `ModuleFinder` | Cơ chế tìm các module quan sát được theo system image hoặc đường dẫn | Xác định có thể tìm module nào ở đâu |
| `ModuleReference` | Tham chiếu đến **nội dung** một module và descriptor của nó | Lấy descriptor, location (nếu biết), đọc nội dung module |
| `ModuleDescriptor` | Metadata khai báo của module | Đọc tên, `requires`, `exports`, `opens`, `uses`, `provides` và thuộc tính module |

Để so sánh **khai báo** với **kết quả phân giải**, học thêm `Configuration` và `ResolvedModule`:

- `Configuration`: đồ thị các module đã được phân giải (resolution), gồm các cạnh readability.
- `ResolvedModule`: một đỉnh trong đồ thị ấy; `reads()` cho biết các module mà nó đọc được trong configuration.
- `java.lang.Module`: module **runtime** đã được JVM định nghĩa trong một layer; dùng `getDescriptor()`, `canRead(...)`, `isExported(...)`, v.v. để kiểm tra tình trạng lúc chạy.

**Phân biệt quan trọng:** `ModuleDescriptor.requires()` là các phụ thuộc **được khai báo trong descriptor** (kể cả một số dependency ngầm định); nó **không** tương đương danh sách tất cả module mà module có thể đọc sau resolution. `ResolvedModule.reads()` diễn tả đồ thị đã phân giải. Và `Module.canRead(...)` có thể phản ánh thay đổi động như `addReads` sau khi layer được định nghĩa.

## 2. Sơ đồ luồng quan sát và phân giải

~~~text
module-info.java
   │ javac
   ▼
module-info.class + classes + resources
   │  (exploded module / modular JAR / runtime image)
   ▼
ModuleFinder.of(path...) hoặc ModuleFinder.ofSystem()
   │ find("demo.app") / findAll()
   ▼
ModuleReference
   ├── descriptor() ──> ModuleDescriptor
   │                      ├── name()
   │                      ├── requires()  [phụ thuộc khai báo]
   │                      ├── exports() / opens()
   │                      └── uses() / provides()
   ├── location() ────> Optional<URI>
   └── open() ────────> ModuleReader
   │
   │  Khi thực sự thực hiện resolution từ roots + finder + parents
   ▼
Configuration
   └── ResolvedModule
         ├── reference() ──> ModuleReference
         └── reads() ─────> Set<ResolvedModule> [cạnh readability]
   │
   │  Khi định nghĩa module layer
   ▼
ModuleLayer / java.lang.Module (runtime)
~~~

**Không nhảy bước:** việc `finder.find(name)` trả về `ModuleReference` chứng minh module **được finder nhìn thấy**, chưa chứng minh nó là một phần của cấu hình đã resolve hay runtime layer hiện tại. Một module có thể được tìm thấy trên module path nhưng không được chọn là root hoặc transitive dependency để đưa vào cấu hình.

## 3. ModuleReference: “tay nắm” tới nội dung của module

`java.lang.module.ModuleReference` là abstract class mà hệ thống cung cấp concrete implementation. Những thao tác chủ yếu:

~~~java
// Đoạn minh họa: finder đã là ModuleFinder hợp lệ.
ModuleReference reference = finder.find("demo.app").orElseThrow();

ModuleDescriptor descriptor = reference.descriptor();
Optional<java.net.URI> uri = reference.location();
try (java.lang.module.ModuleReader reader = reference.open()) {
    // Đọc tài nguyên của module khi thực sự cần.
}
~~~

Đây là **đoạn mã minh họa, chưa phải chương trình độc lập**, dùng các type thuộc `java.lang.module` và `java.util.Optional`. Ý nghĩa:

1. `descriptor()`: luôn trả metadata của module mà reference mô tả.
2. `location()`: `Optional<URI>`; có thể là `file:` của exploded module/modular JAR, `jrt:` cho system module, hoặc rỗng nếu finder không cung cấp vị trí. **Không ép** nó thành `Path` bằng `Path.of(uri)` khi chưa kiểm tra URI scheme và file system provider.
3. `open()`: tạo `ModuleReader` để đọc nội dung, có thể ném `IOException`. Đóng reader bằng try-with-resources; không phải thao tác bắt buộc chỉ để xem dependency.

`ModuleReference` **không** có nghĩa class của module đã được initialize, không quản lý instance/plugin lifecycle và không tự thiết lập quan hệ `requires` cho ứng dụng. Nó là một đối tượng dùng cho lookup/inspection và resolution.

### 3.1. Tìm một module hệ thống

Ví dụ độc lập, lưu thành `InspectSystemModule.java`:

~~~java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;

public class InspectSystemModule {
    public static void main(String[] args) {
        ModuleReference ref = ModuleFinder.ofSystem()
                .find("java.base")
                .orElseThrow();

        System.out.println("name=" + ref.descriptor().name());
        System.out.println("automatic=" + ref.descriptor().isAutomatic());
        System.out.println("requires=" + ref.descriptor().requires().size());
        System.out.println("locationKnown=" + ref.location().isPresent());
    }
}
~~~

Biên dịch/chạy từ thư mục chứa tệp với JDK 17+:

~~~powershell
javac --release 17 InspectSystemModule.java
java InspectSystemModule
~~~

Các dòng **ổn định cho module `java.base`**:

~~~text
name=java.base
automatic=false
requires=0
~~~

Dòng `locationKnown=...` được in tiếp theo và **tùy runtime image/finder**; trên nhiều JDK là `true` với `jrt:/java.base`. Không coi URI cụ thể là public path của JAR trên đĩa. Chọn `java.base` vì nó là module nền tảng luôn có và không cần `requires java.base` lên chính nó.

### 3.2. ModuleFinder: tập module có thể tìm, không phải tập đã nạp

Các nguồn thường gặp:

~~~java
// Các đoạn minh họa, không phải chương trình độc lập.
ModuleFinder system = ModuleFinder.ofSystem();
ModuleFinder plugins = ModuleFinder.of(Path.of("plugins"));
ModuleFinder merged = ModuleFinder.compose(plugins, system);

Optional<ModuleReference> found = merged.find("com.example.plugin");
Set<ModuleReference> candidates = merged.findAll();
~~~

- `ofSystem()` tìm module trong **runtime image** của JDK.
- `of(Path...)` tìm module từ đường dẫn được truyền: thư mục chứa modular JAR/automatic JAR, hoặc exploded module; không tự duyệt tùy ý mọi thư mục con.
- `compose(...)` hợp nhiều finder theo **thứ tự ưu tiên**. Finder tạo từ một chuỗi directory cũng có quy tắc chọn module cùng tên; khi hai module cùng tên xuất hiện **trong một directory**, thao tác có thể ném `FindException`.
- `findAll()` trả một `Set` không có thứ tự giao diện bảo đảm để trình bày. **Sort theo `descriptor().name()`** nếu cần output/tệp báo cáo tái lập.
- Finder không bắt buộc thread-safe; đừng truy cập và thay nội dung module path đồng thời rồi kỳ vọng một snapshot cập nhật an toàn.

`ModuleFinder` tìm module theo **module name**, không theo Maven coordinates. Tên module, version JAR và artifact name là ba thứ khác nhau; đặc biệt automatic module có thể lấy tên từ manifest `Automatic-Module-Name` hoặc từ tên JAR theo quy tắc tự động.

## 4. ModuleDescriptor: đọc chính xác thông tin module khai báo

`java.lang.module.ModuleDescriptor` mô tả module, được biên dịch vào `module-info.class` với **explicit named module**, hoặc được dựng tương ứng cho **automatic module**. Đây là metadata, không phải một `Class<?>` đại diện cho class implementation.

Các API cần nhớ:

| API trên ModuleDescriptor | Ý nghĩa |
| --- | --- |
| `name()` | Tên module, ví dụ `demo.app` |
| `isAutomatic()` | Có phải automatic module không |
| `isOpen()` | Có phải `open module` không |
| `version()` / `rawVersion()` | Version module nếu được ghi nhận, không đồng nghĩa phiên bản runtime đang được enforce |
| `mainClass()` | Main class trong descriptor, nếu có |
| `requires()` | Tập `ModuleDescriptor.Requires`: các phụ thuộc khai báo và ngầm định |
| `exports()` | Các package xuất API, gồm unqualified/qualified exports |
| `opens()` | Các package mở cho deep reflection |
| `uses()` | Tên những service types mà module khai báo sử dụng |
| `provides()` | Service types và tên provider implementations |
| `packages()` | Các package thuộc module theo descriptor |
| `modifiers()` | Tập module modifiers (ví dụ `OPEN` hoặc `AUTOMATIC`) |

Lưu ý: `exports`, `opens` và `uses/provides` **không phải** “dependencies” trong `requires()`. Chúng chi phối các luật truy cập, reflection và service binding, có thể ảnh hưởng đến resolution hoặc cách dùng sau đó, nhưng cần đọc **các tập riêng** thay vì gộp lại như Maven dependencies.

### 4.1. ModuleDescriptor.Requires là nơi đọc dependency chính

Mỗi phần tử `ModuleDescriptor.Requires` chứa:

- `name()`: tên module đích.
- `modifiers()`: tập `ModuleDescriptor.Requires.Modifier`.
- `compiledVersion()`: `Optional<ModuleDescriptor.Version>` nếu có version được ghi nhận lúc biên dịch và parse được.
- `rawCompiledVersion()`: `Optional<String>` cho chuỗi version thô, nếu tồn tại.

Bốn modifier quan trọng:

| Modifier | Hình thức/tình huống | Ý nghĩa |
| --- | --- | --- |
| `TRANSITIVE` | `requires transitive demo.api;` | Module khác đọc module hiện tại sẽ có quan hệ đọc ngầm tới `demo.api` theo quy tắc JPMS |
| `STATIC` | `requires static java.logging;` | Dependency bắt buộc ở thời điểm biên dịch, **tùy chọn lúc chạy**; nếu không được resolve thì không có runtime readability edge tới nó |
| `MANDATED` | `requires java.base` được compiler/descriptor tự thêm | Dependency được khai báo **ngầm định** trong module declaration |
| `SYNTHETIC` | Metadata được tạo ngoài khai báo tường minh/ngầm định | Dependency được thêm ở dạng tổng hợp; không phải từ khóa viết trong `module-info.java` |

Một `requires foo;` thông thường có tập modifier rỗng `[]`. Một directive cũng có thể có nhiều modifier (chẳng hạn static + transitive theo ngữ cảnh cho phép); **không giả định tập chỉ chứa một**. Khi in ra cho máy so sánh, sort tên modifier.

**`java.base` là trường hợp đặc biệt:** với các named module khác `java.base`, descriptor thường có dependency ngầm định tới `java.base`, mang `MANDATED` khi không khai báo tường minh. Vì vậy bảng “số lượng requires” lấy từ API có thể lớn hơn số directive `requires` bạn nhìn thấy trong source.

### 4.2. Version không phải dependency resolver của Maven/Gradle

`ModuleDescriptor.version()` là version gắn với **module đang mô tả** nếu có. `Requires.compiledVersion()` có thể biểu thị version của module được ghi lúc biên dịch. Cả hai đều có thể trống. `module-info.java` của Java **không** có cú pháp trực tiếp kiểu `requires lib@1.2`, và JPMS không tự resolve Maven group/artifact/version ranges như Maven/Gradle.

Do đó khi kiểm tra mismatch giữa compile-time và runtime, không được kết luận “version được enforce” chỉ từ các `Optional` này. Phải kiểm tra JAR thực tế, module path, build dependency graph và binary compatibility.

## 5. Bài thực hành Java 17+: tự tạo ba module và soi ModuleReference/ModuleDescriptor

Lab tạo một quan hệ cụ thể:

~~~text
demo.app
    │ requires demo.util
    ▼
demo.util
    │ requires transitive demo.api
    ▼
demo.api

demo.app còn khai báo requires static java.logging
Mọi module trên ngầm định đọc java.base.
~~~

Điều cần quan sát: descriptor của `demo.app` **không có** `requires demo.api`, nhưng sau resolution `demo.app` **đọc được `demo.api`** nhờ `demo.util` khai báo `requires transitive demo.api`.

### 5.1. Cấu trúc project

Tạo cấu trúc:

~~~text
jpms-inspector/
├── src/
│   ├── demo.api/
│   │   ├── module-info.java
│   │   └── demo/api/Message.java
│   ├── demo.util/
│   │   ├── module-info.java
│   │   └── demo/util/Greeter.java
│   └── demo.app/
│       ├── module-info.java
│       └── demo/app/ModuleReport.java
└── mods/                # được javac tạo ra
~~~

Tên thư mục dưới `src` **trùng module name**; đây là convention của `javac --module-source-path`. Mỗi named module có riêng một `module-info.java`.

Tệp `src/demo.api/module-info.java`:

~~~java
module demo.api {
    exports demo.api;
}
~~~

Tệp `src/demo.api/demo/api/Message.java`:

~~~java
package demo.api;

public record Message(String text) {}
~~~

Tệp `src/demo.util/module-info.java`:

~~~java
module demo.util {
    requires transitive demo.api;
    exports demo.util;
}
~~~

Tệp `src/demo.util/demo/util/Greeter.java`:

~~~java
package demo.util;

import demo.api.Message;

public final class Greeter {
    private Greeter() {}

    public static Message greeting() {
        return new Message("hello-jpms");
    }
}
~~~

Tệp `src/demo.app/module-info.java`:

~~~java
module demo.app {
    requires demo.util;
    requires static java.logging;
}
~~~

`demo.app` có **hai directive tường minh**: `demo.util` và `java.logging`. Modifier `static` biểu thị `java.logging` cần thiết khi biên dịch nhưng dependency ấy **không bắt buộc có trong resolution lúc chạy**. Lab không dùng class của `java.logging`, nên chỉ trình bày nó trong descriptor.

### 5.2. Viết chương trình inspect chạy trong demo.app

Tệp `src/demo.app/demo/app/ModuleReport.java`:

~~~java
package demo.app;

import demo.util.Greeter;
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.lang.module.ResolvedModule;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

public final class ModuleReport {
    public static void main(String[] args) {
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

        for (String name : List.of("demo.api", "demo.util", "demo.app")) {
            ModuleReference reference = finder.find(name).orElseThrow();
            ModuleDescriptor descriptor = reference.descriptor();

            System.out.println("MODULE " + descriptor.name());
            System.out.println("  automatic=" + descriptor.isAutomatic());

            descriptor.requires().stream()
                    .sorted(Comparator.comparing(
                            ModuleDescriptor.Requires::name))
                    .forEach(required -> {
                        String flags = required.modifiers().stream()
                                .map(Enum::name)
                                .sorted()
                                .collect(Collectors.joining(","));
                        System.out.println("  requires " + required.name()
                                + " [" + flags + "]");
                    });
        }

        ResolvedModule app = ModuleLayer.boot()
                .configuration()
                .findModule("demo.app")
                .orElseThrow();

        System.out.println("READS demo.api="
                + app.reads().stream()
                     .anyMatch(module -> module.name().equals("demo.api")));
        System.out.println("READS demo.util="
                + app.reads().stream()
                     .anyMatch(module -> module.name().equals("demo.util")));
        System.out.println("MESSAGE " + Greeter.greeting().text());
    }
}
~~~

Giải thích từng phần:

1. `ModuleFinder.of(Path.of("mods"))` quan sát các exploded modules đã biên dịch.
2. `find(name).orElseThrow()` lấy `ModuleReference` của từng module. Nếu không tìm thấy, bài thực hành dừng rõ ràng thay vì bỏ qua.
3. `reference.descriptor().requires()` trả **direct declared requirements** cùng `java.base` ngầm định; sort theo tên để stdout không phụ thuộc thứ tự duyệt `Set`.
4. `required.modifiers()` được sort và join; chuỗi `[]` nghĩa là dependency bình thường, không có modifier.
5. `ModuleLayer.boot().configuration().findModule("demo.app")` lấy **resolved module của ứng dụng thực sự đang chạy**. `reads()` phản ánh readability sau resolution.
6. `Greeter.greeting()` trả một `Message` thuộc `demo.api`. Mã `demo.app` compile và chạy được dù không trực tiếp khai báo `requires demo.api` vì `demo.util` đã khai báo `requires transitive demo.api`. Đây là minh họa ngắn về hiệu ứng transitive.

### 5.3. Lệnh biên dịch và chạy

Mở PowerShell tại thư mục `jpms-inspector`, máy có **JDK 17+**:

~~~powershell
New-Item -ItemType Directory -Force mods | Out-Null
javac --release 17 -encoding UTF-8 --module-source-path src -d mods -m demo.api,demo.util,demo.app
java --module-path mods --module demo.app/demo.app.ModuleReport
~~~

Stdout của chương trình (với đúng các source file trên):

~~~text
MODULE demo.api
  automatic=false
  requires java.base [MANDATED]
MODULE demo.util
  automatic=false
  requires demo.api [TRANSITIVE]
  requires java.base [MANDATED]
MODULE demo.app
  automatic=false
  requires demo.util []
  requires java.base [MANDATED]
  requires java.logging [STATIC]
READS demo.api=true
READS demo.util=true
MESSAGE hello-jpms
~~~

Hai dòng `READS` cho thấy app đọc được cả `demo.util` (phụ thuộc trực tiếp) **và** `demo.api` (nhờ transitive). Nhưng khi đọc `requires()` của **chính app**, `demo.api` không xuất hiện. Không được viết code suy ra tất cả runtime readable modules chỉ từ `app.descriptor().requires()`.

Nếu báo lỗi `module demo.app not found` hoặc `module demo.util not found`, kiểm tra command đang chạy từ **đúng working directory** và `mods` có cấu trúc `mods/demo.app/module-info.class`, `mods/demo.util/module-info.class`, `mods/demo.api/module-info.class` sau khi biên dịch.

## 6. Dùng ModuleDescriptor để duyệt exports, opens, uses, provides

Ngoài `requires`, hãy đọc các thành phần khác để hiểu **tại sao một module được đọc nhưng class vẫn không truy cập được**, hoặc **tại sao một provider được đưa vào graph**.

Trong module descriptor:

~~~java
// Minh họa module-info.java của một module ứng dụng khác.
module example.host {
    requires example.api;
    uses example.api.Task;
    opens example.host.config to example.reflect;
}
~~~

Và một module provider:

~~~java
// Minh họa module-info.java của một provider module.
module example.provider {
    requires example.api;
    provides example.api.Task with example.provider.TaskImpl;
}
~~~

**Đây là hai descriptor minh họa thuộc hai module khác nhau, không phải chương trình độc lập.** Các package/module/type cần được tạo tương ứng mới biên dịch được.

Với `ModuleDescriptor d`:

~~~java
// Đoạn Java minh họa, cần biến d thuộc kiểu ModuleDescriptor.
d.exports().forEach(e -> {
    System.out.println(e.source() + " -> " + e.targets());
});
d.opens().forEach(o -> {
    System.out.println(o.source() + " -> " + o.targets());
});
d.uses().forEach(service -> System.out.println("uses " + service));
d.provides().forEach(p -> {
    System.out.println("provides " + p.service() + " with " + p.providers());
});
~~~

- `exports()`: trả các `ModuleDescriptor.Exports`. `source()` là package; `isQualified()` và `targets()` cho biết có giới hạn module nhận quyền hay không. **Unqualified export** không đồng nghĩa package được mở cho deep reflection.
- `opens()`: trả các `ModuleDescriptor.Opens`, hỗ trợ framework reflection theo phạm vi module. Với `open module`, kiểm tra thêm `descriptor.isOpen()` vì các package được mở theo tính chất của module, dù set `opens()` không liệt kê từng package.
- `uses()`: tập tên service interfaces module yêu cầu.
- `provides()`: tập mapping từ service type sang tên implementations. Đây là **service binding metadata**, không phải các phụ thuộc `requires` trực tiếp.

**Điểm kiểm tra:** một module có thể khai báo `uses` và được resolution có service binding đưa thêm provider modules vào graph, dù không viết `requires providerModule`. Vì vậy nếu bạn muốn dựng **dependency closure thực tế**, phải biết đã dùng `resolve(...)` hay `resolveAndBind(...)` và có các provider nào được quan sát.

## 7. Direct dependencies, transitive readability và resolved graph khác nhau thế nào?

Xét đúng ba module trong lab:

~~~text
Declared requires of demo.app:
  demo.util          []
  java.logging       [STATIC]
  java.base          [MANDATED]

Declared requires of demo.util:
  demo.api           [TRANSITIVE]
  java.base          [MANDATED]

Sau resolution của ứng dụng đang chạy:
  demo.app READS demo.util
  demo.app READS demo.api  (qua requires transitive)
  demo.app READS java.base
  java.logging có thể không nằm trong graph nếu chỉ được yêu cầu qua requires static.
~~~

### 7.1. requires thường: phụ thuộc trực tiếp

`requires demo.util;` cho phép app đọc `demo.util` khi nó được resolve. Điều này **không tự truyền** khả năng đọc tất cả dependencies của `demo.util` sang app. Để app đọc `demo.api` qua util, util phải khai báo `requires transitive demo.api;` (hoặc app khai báo dependency phù hợp theo cách khác).

**Readability khác accessibility:** đọc được module chưa đảm bảo truy cập được mọi class. Package của target phải được `exports` cho caller, public class/method phải đủ điều kiện Java access; reflective access sâu còn chịu `opens`.

### 7.2. requires transitive: quan hệ đọc được truyền qua

Ví dụ:

~~~java
// module-info.java của demo.util trong lab:
module demo.util {
    requires transitive demo.api;
    exports demo.util;
}
~~~

Khi app `requires demo.util`, nó đọc được `demo.api` nhờ directive transitive trong util. Nói “app trực tiếp declares `requires demo.api`” là **sai**: direct descriptor app vẫn chỉ có đúng các directive của app và các ngầm định như `java.base`.

`requires transitive` không có nghĩa “tự động xuất toàn bộ package”: `demo.api` vẫn phải export package mà app muốn dùng. Nếu library module có code public cần trả về type thuộc `demo.api`, dùng `requires transitive` thường giúp API consumer đọc được type đó.

### 7.3. requires static: có trong descriptor nhưng không bắt buộc resolve khi chạy

`requires static java.logging;` được lưu trong `ModuleDescriptor.Requires` với modifier `STATIC`, dù module `java.logging` **không nhất thiết được runtime resolution kéo vào** chỉ từ directive ấy. Nếu `java.logging` được resolve vì lý do khác, app có thể đọc nó theo quy tắc JPMS; nếu không, sự có mặt của directive static không tạo ra module runtime để dùng.

Đây là lý do `requires()` không phải câu trả lời cho “các module được load tại thời điểm này là gì?”. Khi code thực sự sử dụng class trong module optional, cần xử lý trường hợp module không có trên runtime graph. Các kiểu lỗi/runtime behavior cụ thể phụ thuộc việc class được tham chiếu và liên kết ở đâu; đừng mặc định `requires static` tự cung cấp fallback.

### 7.4. requires java.base: phụ thuộc được bổ sung ngầm

Các named module (trừ `java.base`) có dependency tới `java.base` ngay cả khi source `module-info.java` không ghi. API descriptor hiển thị `MANDATED` cho dependency ngầm này. Vì thế khi đếm “một module có bao nhiêu requires”, phải quyết định báo cáo có gồm `MANDATED` hay không:

- **Báo cáo cấu trúc classfile/descriptor:** nên giữ `MANDATED` để minh bạch.
- **Báo cáo directive do tác giả viết:** lọc phụ thuộc ngầm định và ghi rõ cách lọc, tránh diễn giải rằng source có thêm `requires java.base;`.
- **Báo cáo graph đã resolve:** không dùng count trực tiếp của `requires()`; đọc `ResolvedModule.reads()`.

## 8. Tạo Configuration mới để xem kết quả resolution trước khi chạy plugin

`ModuleLayer.boot().configuration()` cho biết graph của boot layer. Nếu đang xây plugin platform, bạn còn có thể **thử resolution trên một finder** trước khi định nghĩa module layer thực.

Ví dụ **minh họa không độc lập** (giả định `pluginModulePath` là `Path` chỉ tới những module plugin đã chuẩn bị và `rootName` là tên module gốc):

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleFinder finder = ModuleFinder.of(pluginModulePath);
Configuration parent = ModuleLayer.boot().configuration();

Configuration candidate = parent.resolve(
        finder,
        ModuleFinder.of(),       // after finder rỗng
        Set.of(rootName));

candidate.modules().stream()
        .sorted(java.util.Comparator.comparing(m -> m.name()))
        .forEach(m -> {
            System.out.println(m.name() + " reads "
                    + m.reads().stream()
                       .map(r -> r.name())
                       .sorted()
                       .toList());
        });
~~~

Đây là **bước giải resolution, chưa định nghĩa module layer mới**. Trong cấu hình có parent:

- Tìm roots và dependencies theo thứ tự `before finder`, các parent configurations, rồi `after finder` (theo quy tắc API).
- Module đã có trong parent configuration có thể được dùng lại và **không xuất hiện lại trong `candidate.modules()`**. Nếu muốn toàn bộ graph bao gồm parent, phải duyệt cả `parents()`/`findModule(name)` phù hợp.
- `candidate.modules()` chỉ là các module được thêm ở configuration mới, không nhất thiết là tất cả những module mà plugin có thể đọc.
- Nếu dependency thiếu, có thể ném `FindException`; nếu graph vi phạm consistency (cycle hoặc package conflict, v.v.), có thể ném `ResolutionException`.
- `resolveAndBind(...)` mở rộng resolution với service binding: nó có thể đưa thêm provider modules cho các `uses` được phát hiện. Điều đó làm graph thực tế khác tập `requires` trực tiếp.

**Không tự đoán loader:** việc tạo `Configuration` chưa tự nạp/định nghĩa class. Khi định nghĩa `ModuleLayer`, phải chọn đúng mapping từ module sang class loader, ví dụ `defineModulesWithOneLoader` hoặc `defineModulesWithManyLoaders` với ràng buộc package/class loading. Không được suy ra “một module = một loader” chỉ từ `ModuleReference`.

### 8.1. So sánh ba mức quan sát trong một ứng dụng modular

| Mức | API | Câu hỏi trả lời được |
| --- | --- | --- |
| Có thể tìm thấy | `ModuleFinder.find(name)` | Có module mang tên này ở nguồn mà finder quan sát không? |
| Được khai báo | `ModuleReference.descriptor().requires()` | Descriptor nói có những dependency nào và modifier ra sao? |
| Đã phân giải | `Configuration.findModule(name)`, `ResolvedModule.reads()` | Đồ thị readability sau resolution có những cạnh nào? |
| Đã định nghĩa runtime | `ModuleLayer.findModule(name)`, `Module.canRead(...)` | Module đang chạy thuộc layer nào, có đọc được module kia tại runtime không? |

Một hệ thống thực tế đôi khi có **nhiều layers** và module name trùng nhau ở các layer khác nhau. Khi kiểm tra, lưu cả **layer/configuration/loader context**, không tra module name như một khóa toàn JVM.

## 9. Kiểm tra module descriptor bằng công cụ dòng lệnh

Không phải lúc nào cũng cần viết Java inspector. Những lệnh hữu ích trên JDK 17+:

~~~powershell
# Xem module trong runtime image:
java --list-modules

# Xem thông tin một module có thể quan sát từ runtime:
java --describe-module java.sql

# Với project demo đã biên dịch:
java --module-path mods --describe-module demo.app

# Quan sát resolution trong một lần khởi chạy:
java --show-module-resolution --module-path mods --module demo.app/demo.app.ModuleReport

# Xem Module attribute trong class file (tùy đường dẫn):
javap -v mods/demo.app/module-info.class
~~~

- `java --describe-module` hiển thị module declaration theo cách trình bày của JDK, không đảm bảo cùng format với `ModuleDescriptor.toString()`.
- `java --show-module-resolution` giúp đối chiếu roots, resolved modules và các quan hệ graph lúc launch; output có thể nhiều dòng, khác theo runtime image và flags.
- `javap -v` xem cấu trúc classfile, gồm `Module` attribute. Đây là nguồn gần bytecode nhất khi nghi ngờ packaging sai.
- `jdeps` giúp phát hiện class/package dependencies từ bytecode, nhưng **đồ thị dependency theo bytecode** không luôn đồng nhất với `requires` được khai báo (đặc biệt với reflection, optional modules và service binding).

Một cách kiểm tra nhanh trong chương trình Java nếu **chỉ có object runtime module**:

~~~java
// Đoạn minh họa độc lập về cú pháp, cần chọn module runtime phù hợp.
Module module = String.class.getModule();
System.out.println(module.getName());
System.out.println(module.getDescriptor().name());
~~~

Stdout:

~~~text
java.base
java.base
~~~

`Class.getModule()` gắn với module **định nghĩa class** đó. Với class trên class path, bạn nhận unnamed module; `getDescriptor()` của unnamed module trả `null`, nên **không gọi `.requires()` trực tiếp mà không kiểm tra**.

## 10. Các sai lầm khi đọc descriptor và dependency

### 10.1. “Có ModuleReference là module đã được resolve”

Sai. `ModuleFinder.find` có thể trả module candidate không nằm trong `Configuration` hiện tại. Khi runtime báo module không thể truy cập, cần kiểm tra roots, visibility và graph thực tế. **Một finder thấy module** không đảm bảo host JVM đang chạy đã định nghĩa module ấy.

### 10.2. “requires() là tất cả module tôi đọc được”

Sai vì `requires transitive` tạo readability thêm; `requires static` có thể không dẫn tới runtime module; runtime có thể có service binding hoặc dynamic reads. Đọc `ResolvedModule.reads()` / `Module.canRead` theo đúng tầng muốn quan sát.

### 10.3. “requires transitive có nghĩa export mọi package”

Sai. `requires transitive` nói về **readability**; `exports` nói về quyền truy cập các public type; `opens` về deep reflection. Cả ba cần được kiểm tra khi module đã hiện diện mà caller vẫn không dùng được class/package.

### 10.4. “Module descriptor bắt buộc ghi version”

Sai. `version()` và `compiledVersion()` là các `Optional`, không nên gọi `get()` hoặc `orElseThrow()` nếu không có chính sách rõ. JPMS module names không phải Maven coordinates và không tự tải dependencies từ kho artifact.

### 10.5. “Thứ tự requires()/findAll() là thứ tự đồ thị”

Sai. Đây là các `Set` không có thứ tự trình bày đáng dựa vào. Nếu tạo báo cáo để diff hoặc kiểm thử, **sort theo module name rồi modifier**. Đừng suy luận thứ tự class loading từ thứ tự in metadata.

### 10.6. “Automatic module có requires() trống thì không đọc module khác”

Sai. Automatic module có quy tắc readability/exports đặc biệt. Descriptor của automatic module thường chỉ ghi dependency `java.base`; điều này **không** mô tả đầy đủ runtime readability. Kiểm tra `isAutomatic()` trước khi diễn giải kết quả và dùng resolved graph khi muốn biết các cạnh.

### 10.7. “Lỗi module-info.class là do thiếu JAR”

Có thể là `InvalidModuleDescriptorException`/`FindException` vì module descriptor lỗi, module names trùng, package metadata không hợp lệ, hoặc runtime không tương thích; cũng có thể là `ResolutionException` khi graph vi phạm constraint. Đọc exception cause và log của finder/resolver. Thay JAR ngẫu nhiên có thể che một lỗi version/package khác.

### 10.8. “Đọc metadata bằng ModuleReader luôn an toàn để giữ lâu”

`ModuleReader` là tài nguyên phải được đóng; giữ reader/stream mở lâu có thể giữ file handles hoặc resources từ runtime/module image. Với mục tiêu chỉ xem `requires`, hãy dùng `reference.descriptor()`, không mở reader trừ khi thực sự cần xem file bên trong module.

## 11. Quy trình chẩn đoán cho plugin/module resolution

Giả sử plugin `com.example.report` không chạy được. Một luồng điều tra có thứ tự:

1. **Quan sát:** ModuleFinder trên đúng module path/layer candidate có tìm thấy module name không? Nếu không, kiểm tra artifact, tên module, path, automatic module naming.
2. **Khai báo:** Lấy `ModuleReference.descriptor()`. Ghi `name`, `isAutomatic`, `requires` cùng modifiers, `exports/opens/uses/provides`.
3. **Đối chiếu dependency hiện hữu:** Với mỗi required module bắt buộc, kiểm tra nó ở finder/parent configuration nào. Riêng `STATIC` phải hiểu semantics optional lúc chạy.
4. **Resolution:** Dùng `Configuration.resolve(...)` hoặc cấu hình runtime đã có; ghi tập resolved modules và các cạnh `ResolvedModule.reads()`. Bắt `FindException`/`ResolutionException` với cause cụ thể.
5. **Layer/runtime:** Nếu đã define layer, kiểm tra `ModuleLayer.findModule`, `Module.canRead`, `isExported`/`isOpen`. Chú ý layer cha và dynamic additions.
6. **Class loading:** Nếu class vẫn không dùng được, đối chiếu class loader, class/package visibility và binary signature. JPMS resolution thành công **không** bảo đảm class implementation không bị `NoClassDefFoundError` khi được dùng.
7. **Kết quả:** Báo cáo rõ “thiếu module quan sát được”, “module không được resolve”, “readability/accessibility sai” hay “lỗi classloading/bytecode” để sửa đúng nguyên nhân.

### Dạng báo cáo gợi ý

~~~text
Root module: demo.app
Finder: module path ./mods
Module candidate: demo.app (explicit; location known)
Declared requirements:
  demo.util []                  present in finder
  java.logging [STATIC]         runtime optional
  java.base [MANDATED]          system module
Resolved readability:
  demo.util, demo.api, java.base ...
Conclusion:
  demo.api is readable via requires transitive in demo.util.
~~~

Đây là **bản minh họa định dạng báo cáo**, không phải stdout chính thức của API. Phần `...` biểu thị có thể còn các module đọc được tùy cấu hình đã resolve. Không chép nguyên danh sách từ ví dụ này như kết quả trên một JDK bất kỳ.

## 12. Bài tập và tiêu chí hoàn thành

### Bài tập A — Đổi requires transitive thành requires thường

Trong `demo.util/module-info.java`, đổi:

~~~java
requires transitive demo.api;
~~~

thành:

~~~java
requires demo.api;
~~~

Đây là **đoạn trích descriptor**, không phải chương trình độc lập. Giữ `demo.app` chỉ requires `demo.util`. Vì `ModuleReport` chỉ trực tiếp import `demo.util.Greeter` và dùng suy luận `var`/method chains trong bản hiện tại, ứng dụng có thể vẫn biên dịch tùy cách sử dụng type của API; để kiểm chứng rõ quan hệ readability, thêm một **dòng import trực tiếp** `demo.api.Message` cùng khai báo biến kiểu `Message` trong app. Khi đó app sẽ không được phép dùng public type từ `demo.api` qua quan hệ transitive đã bị bỏ; cần thêm `requires demo.api;` vào `demo.app/module-info.java` hoặc khôi phục `requires transitive demo.api;` ở util.

### Bài tập B — Nhìn thấy và sử dụng khác nhau

Tạo một module `demo.hidden` nằm trong module path nhưng không được root `demo.app` yêu cầu và không phải provider được bind. Kiểm tra `ModuleFinder.of(Path.of("mods")).find("demo.hidden")` có thể trả `ModuleReference`, trong khi `ModuleLayer.boot().configuration().findModule("demo.hidden")` có thể rỗng khi launch chỉ với `demo.app`. Đây là khác biệt giữa **observable** và **resolved**.

### Bài tập C — Thử requires static

Giữ `requires static java.logging` trong app. Quan sát descriptor còn phần tử `STATIC`. Đối chiếu `--show-module-resolution` và khả năng `java.logging` được resolve bởi runtime/root khác. Rút ra: **declared static dependency != bắt buộc tồn tại runtime**.

### Bài tập D — Thử service binding

Tạo service interface trong module API, khai báo `uses` ở host, `provides ... with ...` ở provider. So sánh kết quả của `resolve` và `resolveAndBind` trên cùng finders/roots (nhớ tính cả parent configurations). Hãy báo cáo provider nào được thêm do service binding, thay vì tự cho rằng có `requires provider`.

### Checklist kết quả

Bạn đã nắm vững chủ đề khi có thể giải thích và kiểm chứng:

- `ModuleFinder.find` trả gì và vì sao chưa chắc module được resolve.
- `ModuleReference.descriptor()` khác `ModuleReference.open()` ở vai trò nào.
- `ModuleDescriptor.requires()` chứa các dependency khai báo và cả `java.base [MANDATED]`.
- `Requires.Modifier.STATIC` và `TRANSITIVE` tác động khác nhau thế nào.
- Tại sao module app đọc được `demo.api` dù không trực tiếp `requires demo.api`.
- `ResolvedModule.reads()` cho thông tin nào mà `requires()` chưa cung cấp.
- Vì sao `exports`, `opens`, `uses`, `provides` phải đọc riêng.
- Tại sao version trên module descriptor không thay Maven/Gradle version resolution.
- Cách tránh sai do unnamed/automatic module, multiple layers và thứ tự Set.
- Cách tái hiện lỗi bằng `java --describe-module`, `--show-module-resolution` và chương trình Java 17+.

## 13. Tài liệu chuẩn để tra cứu

- Java SE 17 — ModuleFinder: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html
- Java SE 17 — ModuleReference: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleReference.html
- Java SE 17 — ModuleDescriptor: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.html
- Java SE 17 — ModuleDescriptor.Requires: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.Requires.html
- Java SE 17 — Configuration: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html
- Java SE 17 — ResolvedModule: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ResolvedModule.html
- Java SE 17 — Module runtime: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- JPMS resolution specification: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/package-summary.html
