# Kiểm tra đồ thị kết quả qua `Configuration` và `ResolvedModule`

Khi dùng Java Platform Module System (JPMS), viết `requires` trong `module-info.java` mới chỉ **khai báo phụ thuộc**. Java còn phải phân giải (resolution) các module khả dụng thành một **đồ thị module đã phân giải** trước khi xây dựng lớp module để chạy chương trình. Để hiểu vì sao một module được chọn, module nào đọc được module nào, hoặc vì sao không tìm thấy một dependency, ta có thể kiểm tra đồ thị qua hai API chuẩn của JDK:

- `java.lang.module.Configuration`: đại diện cho một **cấu hình module đã phân giải** và các cấu hình cha.
- `java.lang.module.ResolvedModule`: đại diện cho **một module cụ thể trong cấu hình**, bao gồm mô tả module và quan hệ *readability* (khả năng đọc module khác).

Điểm quan trọng nhất: **đồ thị `requires` khai báo trong descriptor và đồ thị `reads()` sau resolution có liên quan nhưng không nhất thiết giống nhau**. Bài này dựng một ví dụ Java 17 có quan hệ `requires transitive`, in đồ thị theo thứ tự ổn định, đọc đúng `Configuration.modules()`, `findModule()`, `ResolvedModule.reference()`, `reads()` và giải thích khác biệt giữa phân giải cấu hình với nạp module để thực thi.

## 1. Trước khi kiểm tra, cần phân biệt ba đối tượng

| Thành phần | Vai trò | Điều nó trả lời |
|---|---|---|
| `ModuleDescriptor` | Mô tả tĩnh của một named module: `requires`, `exports`, `opens`, `uses`, `provides`... | “Module *khai báo* điều gì?” |
| `Configuration` | Kết quả resolution của một tập module root, cùng quan hệ với cấu hình cha | “Trong lần phân giải này, có những module nào được chọn?” |
| `ResolvedModule` | Một module đã được chọn, có `ModuleReference`, `configuration()` và tập `reads()` | “Module này *thực sự đọc được* những module nào trong đồ thị?” |

Có hai API dễ nhầm thêm:

- `java.lang.Module` mô tả module **ở runtime** sau khi module được định nghĩa vào một `ModuleLayer`; nó có `canRead(...)`, `getLayer()` và các thao tác runtime khác.
- `java.lang.ModuleLayer` gắn một `Configuration` với cách định nghĩa lớp/class loader và các đối tượng `Module`. **Chỉ gọi `Configuration.resolve(...)` chưa tạo `ModuleLayer`, chưa nạp class để chạy, và chưa khởi tạo provider.**

Vì vậy `ResolvedModule` không phải đối tượng `Module` runtime; `ModuleDescriptor` cũng không phải danh sách toàn bộ các cạnh sau resolution.

## 2. Quá trình tạo đồ thị resolution

Một phép phân giải thường cần ba thứ:

1. **Root modules:** tập tên module cần có, ví dụ `demo.app`.
2. **Nguồn tìm module (`ModuleFinder`):** module path/JAR/thư mục chứa các module quan sát được.
3. **Cấu hình cha:** ví dụ `ModuleLayer.boot().configuration()` để tham chiếu các module nền tảng JDK đã có.

```text
Root: demo.app
       |
       v
ModuleFinder tìm demo.app và các dependency liên quan
       |
       v
Resolution kiểm tra yêu cầu, khả năng đọc và ràng buộc JPMS
       |
       v
Configuration (đồ thị kết quả)
       |
       +-- modules() -> các ResolvedModule thuộc chính cấu hình mới
       |
       +-- parents() -> cấu hình cha, có thể chứa java.base
       |
       +-- findModule(name) -> tìm theo tên trong cấu hình hoặc cha
```

Mã API điển hình:

```java
ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
Configuration parent = ModuleLayer.boot().configuration();

Configuration graph = parent.resolve(
        finder,
        ModuleFinder.of(),
        Set.of("demo.app"));
```

Đoạn này là minh họa API; chương trình hoàn chỉnh bên dưới có import, tệp nguồn và lệnh chạy.

Ý nghĩa tham số của `parent.resolve(before, after, roots)`:

- `before`: nơi ưu tiên tìm module so với module trong cấu hình cha.
- `after`: nguồn tìm sau khi đã xét cấu hình cha.
- `roots`: tập module bắt đầu quá trình phân giải.
- `parent`: cấu hình cha được kế thừa; các module ở cha có thể được dùng để thỏa phụ thuộc.

API resolution không lấy danh sách class trong classpath rồi tự biến chúng thành named module. Những tệp `module-info.class` hoặc modular JAR được `ModuleFinder` nhìn thấy mới là đầu vào của phép phân giải tương ứng. Thứ tự và tính quan sát được của các module có thể ảnh hưởng kết quả, nên cần kiểm tra đầu vào trước khi kết luận lỗi do `Configuration`.

## 3. Bài toán minh họa: ba module và một cạnh đọc gián tiếp

Ta tạo ba named module:

```text
demo.app --requires--> demo.feature --requires transitive--> demo.contract
```

`demo.app` chỉ khai báo `requires demo.feature`. `demo.feature` công bố `requires transitive demo.contract`, vì vậy `demo.app` cũng có khả năng đọc `demo.contract` theo quy tắc readability của JPMS.

Cấu trúc nguồn:

```text
module-graph-demo/
├── src/
│   ├── demo.contract/
│   │   ├── module-info.java
│   │   └── demo/contract/Greeter.java
│   ├── demo.feature/
│   │   ├── module-info.java
│   │   └── demo/feature/GreeterImpl.java
│   └── demo.app/
│       ├── module-info.java
│       └── demo/app/App.java
└── inspector/
    └── GraphInspector.java
```

Sau khi biên dịch, `mods/` chứa ba thư mục module đã biên dịch, còn `out/` chứa lớp inspector. Inspector chạy trên classpath để nó có thể xây dựng một cấu hình mới từ `mods/` mà không cần đưa ba module demo vào boot layer của chính tiến trình inspector.

### 3.1. Module hợp đồng: `demo.contract`

Tệp `src/demo.contract/module-info.java`:

```java
module demo.contract {
    exports demo.contract;
}
```

Tệp `src/demo.contract/demo/contract/Greeter.java`:

```java
package demo.contract;

public interface Greeter {
    String greet(String name);
}
```

Module này xuất gói `demo.contract` để các module đọc được nó có thể truy cập `Greeter`.

### 3.2. Module tính năng: `demo.feature`

Tệp `src/demo.feature/module-info.java`:

```java
module demo.feature {
    requires transitive demo.contract;
    exports demo.feature;
}
```

Tệp `src/demo.feature/demo/feature/GreeterImpl.java`:

```java
package demo.feature;

import demo.contract.Greeter;

public final class GreeterImpl implements Greeter {
    @Override
    public String greet(String name) {
        return "Hello " + name;
    }
}
```

`requires transitive demo.contract` có hai tác dụng liên quan: `demo.feature` đọc `demo.contract`; các module đọc `demo.feature` theo mối quan hệ phù hợp cũng được ngụ ý đọc `demo.contract`. Đừng nhầm `requires transitive` với việc mở gói: để mã ngoài module truy cập kiểu `Greeter`, `demo.contract` vẫn cần `exports demo.contract`.

### 3.3. Root module: `demo.app`

Tệp `src/demo.app/module-info.java`:

```java
module demo.app {
    requires demo.feature;
}
```

Tệp `src/demo.app/demo/app/App.java`:

```java
package demo.app;

import demo.contract.Greeter;
import demo.feature.GreeterImpl;

public final class App {
    public static void main(String[] args) {
        Greeter greeter = new GreeterImpl();
        System.out.println(greeter.greet("Java"));
    }
}
```

Điều đáng chú ý: `App` import `demo.contract.Greeter` mặc dù `demo.app` **không khai báo** `requires demo.contract`. Việc này hợp lệ vì `demo.feature` có `requires transitive demo.contract`. Chương trình sẽ in `Hello Java`.

## 4. Tạo `Configuration` và duyệt `ResolvedModule`

Tệp `inspector/GraphInspector.java` sau đây là một chương trình Java 17 độc lập, đầy đủ import và `main`:

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.lang.module.ResolvedModule;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Set;

public final class GraphInspector {
    public static void main(String[] args) {
        ModuleFinder finder = ModuleFinder.of(
                Path.of(args.length > 0 ? args[0] : "mods"));

        Configuration parent = ModuleLayer.boot().configuration();
        Configuration graph = parent.resolve(
                finder,
                ModuleFinder.of(),
                Set.of("demo.app"));

        System.out.println("Modules in new configuration:");
        graph.modules().stream()
                .map(ResolvedModule::name)
                .sorted()
                .forEach(name -> System.out.println("  " + name));

        graph.modules().stream()
                .sorted(Comparator.comparing(ResolvedModule::name))
                .forEach(module -> {
                    List<String> direct = module.reference()
                            .descriptor()
                            .requires()
                            .stream()
                            .map(require -> require.name())
                            .filter(name -> name.startsWith("demo."))
                            .sorted()
                            .toList();

                    List<String> reads = module.reads()
                            .stream()
                            .map(ResolvedModule::name)
                            .filter(name -> name.startsWith("demo."))
                            .sorted()
                            .toList();

                    System.out.println(module.name()
                            + " requires=" + direct
                            + " reads=" + reads);
                });

        System.out.println("find demo.feature: "
                + graph.findModule("demo.feature").isPresent());
        System.out.println("find demo.missing: "
                + graph.findModule("demo.missing").isPresent());
        System.out.println("same configuration: "
                + (graph.findModule("demo.app")
                        .orElseThrow().configuration() == graph));
        System.out.println("java.base in parent: "
                + parent.findModule("java.base").isPresent());
        System.out.println("java.base through graph.findModule: "
                + graph.findModule("java.base").isPresent());
        System.out.println("java.base in graph.modules: "
                + graph.modules().stream()
                        .anyMatch(m -> m.name().equals("java.base")));
    }
}
```

Chương trình cố ý sắp xếp danh sách bằng `.sorted()` và `Comparator.comparing(...)`; `Set<ResolvedModule>` trả từ `modules()` hoặc `reads()` **không phải một hợp đồng thứ tự hiển thị**. Nếu in trực tiếp tập hợp, thứ tự có thể khác giữa môi trường.

Để các dòng ví dụ ổn định, ta lọc những tên bắt đầu bằng `demo.` khi so sánh `requires`/`reads`. Module thực tế còn có thể đọc `java.base` hoặc các module khác do JPMS quy định; việc lọc chỉ dành cho mục đích quan sát phần đồ thị demo.

## 5. Biên dịch và chạy trên Java 17 trở lên

Ví dụ dùng `javac --release 17` để các class được biên dịch theo mức Java 17. Đứng tại thư mục `module-graph-demo`, nơi có các thư mục `src` và `inspector` như phần trên.

### Linux/macOS (Bash)

Tạo thư mục đầu ra:

```bash
mkdir -p mods out
```

Biên dịch ba named module. Mỗi module phải có tên thư mục trùng tên module dưới `--module-source-path src`:

```bash
javac --release 17 -d mods --module-source-path src src/demo.contract/module-info.java src/demo.contract/demo/contract/Greeter.java src/demo.feature/module-info.java src/demo.feature/demo/feature/GreeterImpl.java src/demo.app/module-info.java src/demo.app/demo/app/App.java
```

Biên dịch inspector vào classpath output riêng:

```bash
javac --release 17 -d out inspector/GraphInspector.java
```

Chạy ứng dụng named module, rồi chạy inspector:

```bash
java --module-path mods -m demo.app/demo.app.App
java -cp out GraphInspector mods
```

### Windows PowerShell

Các đường dẫn tương đối dùng dấu `/` dưới đây vẫn được Java CLI và PowerShell nhận trong vị trí tên tệp ở ví dụ. Dùng:

```powershell
New-Item -ItemType Directory -Force mods,out | Out-Null

javac --release 17 -d mods --module-source-path src src/demo.contract/module-info.java src/demo.contract/demo/contract/Greeter.java src/demo.feature/module-info.java src/demo.feature/demo/feature/GreeterImpl.java src/demo.app/module-info.java src/demo.app/demo/app/App.java

javac --release 17 -d out inspector/GraphInspector.java

java --module-path mods -m demo.app/demo.app.App
java -cp out GraphInspector mods
```

Không cần ghép nhiều JAR bằng dấu `:` hoặc `;` vì `mods` là **một** đường dẫn module output và `out` là **một** đường dẫn classpath. Nếu sau này dùng nhiều phần tử trong `--module-path`, Linux/macOS dùng `:`, còn Windows dùng `;`.

### Kết quả chính xác

Lệnh chạy `demo.app` in stdout:

```text
Hello Java
```

Lệnh `GraphInspector` in stdout:

```text
Modules in new configuration:
  demo.app
  demo.contract
  demo.feature
demo.app requires=[demo.feature] reads=[demo.contract, demo.feature]
demo.contract requires=[] reads=[]
demo.feature requires=[demo.contract] reads=[demo.contract]
find demo.feature: true
find demo.missing: false
same configuration: true
java.base in parent: true
java.base through graph.findModule: true
java.base in graph.modules: false
```

Các kết quả trên là đầu ra cho **bộ tệp nguồn và lệnh chạy vừa trình bày**, không phải đầu ra phổ quát của mọi đồ thị JPMS. Inspector chạy trên classpath, và khi nó tạo cấu hình con với `demo.app` là root thì ba module demo cùng được phân giải trong cấu hình đó.

## 6. Đọc từng kết quả: điều nào thực sự chứng minh điều gì?

### 6.1. `Configuration.modules()` cho biết tập module thuộc cấu hình mới

```java
Set<ResolvedModule> selected = graph.modules();
```

Trong ví dụ, `selected` có ba tên `demo.app`, `demo.feature`, `demo.contract`.

**Không được hiểu** `graph.modules()` là “mọi module mà `graph` có thể tra cứu”, vì các module nằm trong cấu hình cha **không thuộc tập này**. `java.base` thuộc cấu hình boot ở cha; vì vậy:

```text
java.base through graph.findModule: true
java.base in graph.modules: false
```

Đây không phải mâu thuẫn. `Configuration.findModule(name)` tra cứu cả cấu hình hiện tại và các cấu hình cha. Khi cần liệt kê **riêng các module mới**, dùng `modules()`; khi cần tra tên module có thể đến từ cha, dùng `findModule()`.

### 6.2. `ResolvedModule.name()` là tên module đã chọn

```java
String name = module.name();
```

`name()` phù hợp để ghi log, kiểm tra membership và so sánh với tên trong descriptor. Không nên tự xem tên hiển thị như một định danh duy nhất xuyên mọi configuration/layer: một tên module có thể xuất hiện trong những môi trường nạp khác nhau; khi cần hiểu một `ResolvedModule`, hãy giữ cả cấu hình sở hữu nó.

### 6.3. `ResolvedModule.reference()` dẫn tới descriptor của module

```java
var descriptor = module.reference().descriptor();
var declaredRequires = descriptor.requires();
```

`module.reference()` trả `ModuleReference`, chứa `ModuleDescriptor` và có thể cung cấp `location()` dạng `Optional<URI>`. Không được giả định `location()` luôn có URI file/JAR: module có thể đến từ module finder của hệ thống hoặc cơ chế khác.

`descriptor.requires()` là các khai báo **trực tiếp trong descriptor**, kèm modifier. Trong chương trình, ta chỉ lấy `.name()` để so sánh. Nếu muốn phân biệt `requires transitive`, có thể đọc:

```java
boolean transitive = module.reference()
        .descriptor()
        .requires()
        .stream()
        .anyMatch(r -> r.name().equals("demo.contract")
                && r.modifiers().contains(
                        java.lang.module.ModuleDescriptor.Requires.Modifier.TRANSITIVE));
```

Đoạn kiểm tra này là **minh họa biểu thức nằm trong ngữ cảnh có biến `module`**, không phải một chương trình độc lập. Giá trị `true` áp dụng khi `module` là `demo.feature`; với `demo.app` là `false` vì `demo.app` không trực tiếp khai báo `demo.contract`.

Các yêu cầu mặc định đến `java.base` thường được thêm vào descriptor theo quy tắc JPMS. Bộ lọc `demo.` trong inspector loại chúng khỏi bảng để không làm lẫn ví dụ.

### 6.4. `ResolvedModule.reads()` biểu thị các cạnh readability

```java
Set<ResolvedModule> readable = module.reads();
```

`reads()` trả tập những module mà module này đọc được theo đồ thị resolution. Đồ thị readability có thể bao gồm các quan hệ **suy ra từ `requires transitive`**, không chỉ những mục `requires` ghi trực tiếp trong descriptor.

Trong stdout:

```text
demo.app requires=[demo.feature] reads=[demo.contract, demo.feature]
```

Đây là điểm học quan trọng: `demo.app` **không trực tiếp khai báo** `demo.contract`, nhưng vẫn đọc được nó vì `demo.feature` yêu cầu `demo.contract` theo chế độ `transitive`.

Trong ví dụ, `demo.feature` trực tiếp đọc `demo.contract`. `demo.contract` không khai báo phụ thuộc demo nào nên tập readability sau khi lọc tên `demo.` là rỗng. Điều đó không nói rằng nó không đọc `java.base`; ta đã chủ động lọc các module không bắt đầu bằng `demo.`.

### 6.5. `ResolvedModule.configuration()` chỉ ra cấu hình sở hữu module

```java
Configuration owner = module.configuration();
```

Nếu lấy `demo.app` từ `graph.findModule("demo.app")`, biểu thức `module.configuration() == graph` là `true` trong chương trình này vì `demo.app` nằm trong chính cấu hình mới.

Nhưng với một module trả về từ cấu hình cha qua `findModule`, `module.configuration()` sẽ là cấu hình cha sở hữu nó, **không phải** `graph`. Vì vậy, khi kiểm tra graph phân cấp, phải phân biệt **được tra cứu qua cấu hình hiện tại** và **được sở hữu bởi cấu hình hiện tại**.

## 7. So sánh đồ thị `requires` và đồ thị `reads`

Đặt cạnh nhau để dễ hình dung:

```text
KHAI BÁO (ModuleDescriptor.requires)
  demo.app     -> demo.feature
  demo.feature -> demo.contract  [TRANSITIVE]
  demo.contract -> (không requires demo.*)

ĐỌC ĐƯỢC (ResolvedModule.reads, chỉ lọc demo.*)
  demo.app     -> demo.feature
  demo.app     -> demo.contract  [suy ra qua transitive]
  demo.feature -> demo.contract
  demo.contract -> (không đọc demo.*)
```

Bảng sau giải thích chọn API cho từng câu hỏi:

| Muốn biết | API phù hợp | Lưu ý |
|---|---|---|
| Module nào đã được đưa vào cấu hình mới? | `configuration.modules()` | Không bao gồm module chỉ thuộc parent |
| Module `X` có thể tìm qua cấu hình và cha không? | `configuration.findModule("X")` | Có thể trả module từ parent |
| Module A khai báo `requires` nào? | `resolved.reference().descriptor().requires()` | Có modifier `TRANSITIVE`, `STATIC`, `MANDATED`... |
| Module A thực sự đọc những module nào sau phân giải? | `resolved.reads()` | Có thể gồm cạnh gián tiếp |
| Module B thuộc cấu hình nào? | `resolved.configuration()` | Hữu ích với nhiều parent/layer |
| Module được chọn có mô tả/tài nguyên ở đâu? | `resolved.reference()` | `location()` là `Optional` |
| Module runtime A hiện có đọc B không? | `java.lang.Module.canRead(...)` | Chỉ dùng cho module runtime sau khi được định nghĩa |

Không nên dùng `descriptor.requires()` để kết luận toàn bộ **readability**, cũng không nên dùng `reads()` để đoán chắc một quan hệ là `requires` trực tiếp. Nếu cần vẽ sơ đồ đầy đủ, nên chú thích **cạnh khai báo** và **cạnh đọc có hiệu lực** thành hai loại.

## 8. Khi nào `Configuration.resolve(...)` chưa đủ?

`Configuration` là đồ thị metadata đã phân giải, không phải một ứng dụng được khởi chạy. Ví dụ inspector **không** định nghĩa class loader/module layer cho ba module demo.

Muốn thực thi các class trong module mới, cần một bước định nghĩa vào `ModuleLayer` với chiến lược class loader thích hợp, hoặc đơn giản khởi chạy chương trình modular bằng `java --module-path ... -m ...` như ví dụ. Hai lệnh:

```text
java --module-path mods -m demo.app/demo.app.App
java -cp out GraphInspector mods
```

là **hai cách chạy có mục đích khác nhau**. Lệnh đầu tạo môi trường module để chạy `demo.app`; lệnh sau tạo cấu hình để khảo sát từ một tiến trình inspector trên classpath. Hai đồ thị có thể phản ánh các dependency tương đương nhưng không phải cùng một đối tượng `Configuration` trong cùng một JVM.

Cũng cần phân biệt:

- `resolve(...)`: phân giải tập root và các phụ thuộc module cần thiết theo luật JPMS.
- `resolveAndBind(...)`: ngoài việc phân giải, còn có thể đưa vào các module provider khi thực hiện **service binding** dựa trên khai báo `uses` và `provides`.

Nếu module có `uses SomeService` mà provider chỉ được phát hiện qua service binding, kết quả `modules()` có thể khác giữa hai cách. Không nên suy luận “cứ có `provides` trên module path là provider tự vào graph” cho mọi trường hợp `resolve`. Sau khi có graph, ứng dụng còn cần `ModuleLayer` và cơ chế sử dụng dịch vụ thích hợp để thực sự gọi provider.

## 9. Kiểm tra graph trong hệ thống có cấu hình cha

Cấu hình không nhất thiết là một tập module phẳng. `Configuration.parents()` trả các cấu hình cha; API static còn có biến thể resolution nhận danh sách cha để phục vụ module layer phức tạp. Trong ứng dụng plugin, một plugin có thể được phân giải thành cấu hình con của boot configuration hoặc cấu hình đã chứa API chung.

Mô hình:

```text
          Boot configuration
          (java.base, ...)
                  |
                  v
          Child configuration
       (demo.app, demo.feature,
         demo.contract)
```

Quy tắc quan sát:

1. Dùng `graph.modules()` để thấy đúng module **thuộc graph** mới.
2. Dùng `graph.parents()` để biết các cấu hình trước đó mà graph có thể dựa vào.
3. Dùng `graph.findModule(name)` để tìm module theo tên xuyên quan hệ cấu hình.
4. Sau khi có `ResolvedModule`, dùng `configuration()` để biết nó thuộc về parent hay child.
5. Dùng `reads()` của từng module nếu cần xác minh đường readability. Đừng dùng riêng `findModule` để suy ra một module bất kỳ đọc được module đã tìm thấy.

`findModule("java.base").isPresent()` là câu hỏi “module đó có ở đâu trong cấu hình này hoặc cha không?”. Nó **không** có nghĩa mọi module trong graph có quyền truy cập mọi gói của `java.base` hoặc bất kỳ module parent nào; tính đọc được, `exports` và `opens` vẫn là các quan hệ/ràng buộc riêng.

## 10. Những giới hạn khi đọc đồ thị phân giải

**Readability khác package accessibility.** Module A có thể đọc B, nhưng A chỉ được truy cập công khai các package mà B **exports** cho A. `opens` phục vụ truy cập phản chiếu theo quy tắc tương ứng; `reads()` không phải danh sách package được phép import.

**Một cấu hình có thể được tạo mà chưa chạy code.** `ResolvedModule` không nói class đã được nạp, static initializer đã chạy, hay service provider đã được tạo. Các câu hỏi đó thuộc giai đoạn runtime.

**Descriptor là metadata tại thời điểm resolution.** Những thay đổi readability bằng các API runtime như `Module.addReads(...)` (trong phạm vi quyền và điều kiện thích hợp) có thể làm `Module.canRead(...)` ở runtime khác với dữ liệu ta khảo sát từ cấu hình ban đầu.

**`reads()` là tập cạnh, không phải thuật toán chỉ đường.** Nếu muốn tìm vì sao A đọc C qua những module trung gian nào, cần kết hợp descriptor (`requires`/modifier) và phân tích graph. Một cạnh xuất hiện trong `reads()` không tự ghi “nguồn gốc cạnh”.

**Module version không thay thế dependency management.** `ModuleDescriptor` có thể mang version metadata, nhưng JPMS resolution không phải bộ giải phiên bản semantic dependency giống Maven/Gradle. Module path cần được chuẩn bị với các artifact tương thích; việc có tên module đúng chưa đủ để kết luận API tương thích.

**Không phải mọi thứ trên classpath đều vào JPMS graph.** Mã của unnamed module và các dependency thuần classpath không tự xuất hiện trong `Configuration.modules()` với tư cách resolved named module. Các automatic module trên module path có quy tắc riêng; cần phân biệt chúng với plain classpath JAR.

## 11. Chẩn đoán kết quả bất thường

| Hiện tượng | Khả năng thường gặp | Cách kiểm tra |
|---|---|---|
| `findModule("demo.app")` rỗng | Không đưa `demo.app` vào root hoặc không có nó trong các cấu hình liên quan | In roots, kiểm tra ModuleFinder và tên module |
| Resolution thất bại vì thiếu module | Một dependency bắt buộc không được quan sát từ finder/parent | Kiểm tra `requires`, đường dẫn module path và module thực sự có mặt |
| Module có trong finder nhưng không có ở `modules()` | Nó có thể không thuộc dependency closure của roots, hoặc đã được thỏa từ parent | Kiểm tra root, parent và `findModule` |
| `findModule("java.base")` có nhưng `modules()` không liệt kê | `java.base` thuộc cấu hình cha | Đọc `parents()` và `ResolvedModule.configuration()` |
| `reads()` có nhiều tên hơn `requires()` | Cạnh đọc suy ra, ví dụ `requires transitive` | Đọc modifier trong `ModuleDescriptor.Requires` |
| Đọc được module B nhưng không import được package trong B | Package chưa được `exports` phù hợp hoặc API không public | Kiểm tra `ModuleDescriptor.exports()` và visibility của kiểu |
| Kết quả khác giữa `resolve` và `resolveAndBind` | Service binding có thể đưa thêm provider modules | Kiểm tra `uses`/`provides` và finder liên quan |
| In `Set` ra thứ tự thay đổi | Tập hợp không quy định thứ tự trình bày | Sắp xếp theo `ResolvedModule.name()` trước khi in |
| Cấu hình phân giải được nhưng app chạy lỗi liên kết | Module graph hợp lệ chưa bảo đảm API binary tương thích hay class đã nạp đúng | Kiểm tra phiên bản artifact, chữ ký phương thức và log runtime |
| `ResolvedModule` tìm được nhưng không có `Module` runtime | Mới thực hiện resolution, chưa tạo layer | Định nghĩa layer hoặc chạy ứng dụng modular để có runtime Module |

Nếu muốn quan sát resolution khi chính JVM chạy ứng dụng, có thể dùng:

```bash
java --show-module-resolution --module-path mods -m demo.app/demo.app.App
```

Tùy JDK, module path và cấu hình môi trường, lệnh này có thể in thêm các module hệ thống và thông tin resolution; không nên coi văn bản debug đó là định dạng ổn định để máy khác phụ thuộc. Đối với bài kiểm tra tự động có yêu cầu output nhất quán, cách duyệt `Configuration` và sắp xếp danh sách như `GraphInspector` thường thuận tiện hơn.

Khi `resolve` ném ngoại lệ, hãy đọc **nguyên nhân đầu tiên và module name trong thông báo**. Các vấn đề như thiếu module, finder quan sát trùng module, hoặc mô tả module không hợp lệ cần được xử lý ở nguồn tìm module/descriptor; không thể giải quyết bằng cách `catch` rồi giả vờ graph đủ module.

## 12. Một quy trình kiểm tra thực tế

Khi một module trong ứng dụng lớn không tìm được hoặc không đọc được module khác, đi theo trình tự:

1. **Xác định root thật:** ứng dụng khởi chạy bằng `-m` nào, hoặc framework gọi resolution với `roots` nào? Đừng lấy tất cả JAR có mặt làm root nếu không có lý do.
2. **Ghi lại module finders và parent:** phân biệt các module ứng dụng được phát hiện từ module path với module đã nằm trong boot/parent configuration.
3. **Phân giải và chặn lỗi sớm:** nếu có lỗi, xử lý nguyên nhân trong `requires`, module path hoặc descriptor.
4. **Kiểm tra membership:** dùng `modules()` và `findModule(name)`. Ghi rõ module thuộc cấu hình hiện tại hay parent.
5. **Đối chiếu khai báo và readability:** từ `ResolvedModule.reference().descriptor().requires()` xem cạnh trực tiếp và modifier; từ `ResolvedModule.reads()` xem kết quả thực tế.
6. **Kiểm tra quyền truy cập package:** readability không thay `exports`/`opens`; đọc descriptor của module đích khi có lỗi biên dịch hoặc phản chiếu.
7. **Nếu cần chạy plugin:** sau khi graph hợp lệ, kiểm tra tạo `ModuleLayer`, class loader, và cơ chế nạp dịch vụ. Đừng dừng ở “đồ thị đã phân giải” mà kết luận mọi provider đã chạy.
8. **Tự động hóa:** sắp xếp tên module, so sánh tập đỉnh/cạnh cần thiết và cho kiểm thử thất bại khi một dependency quan trọng hoặc một cạnh `reads` bất ngờ biến mất.

## 13. Bài tập củng cố

1. **Bỏ `transitive`:** đổi `demo.feature` thành `requires demo.contract;`. Dự đoán việc `demo.app` biên dịch khi vẫn import `demo.contract.Greeter`. Sau đó bỏ import `Greeter` khỏi `App` hoặc thêm `requires demo.contract` trực tiếp và giải thích thay đổi đồ thị.
2. **Đổi roots:** truyền root là `demo.feature` thay cho `demo.app`. So sánh tập `modules()` mới, các cạnh `reads()` và module `demo.app` có còn được phân giải không.
3. **Tìm trong parent:** dùng `graph.findModule("java.base")`, in `configuration()` của module nhận được và đối chiếu với `graph.modules()`. Vì sao `java.base` không phải module được chọn mới?
4. **Kiểm tra modifier:** bổ sung vòng lặp in các `ModuleDescriptor.Requires.Modifier` của từng dependency. Đảm bảo phân biệt `TRANSITIVE` của `demo.feature` với `requires` thường của `demo.app`.
5. **Thử sai module path:** bỏ thư mục module `demo.contract` khỏi finder (trên bản sao môi trường thử nghiệm), rồi xem resolution có thất bại hay được thỏa từ parent. Diễn giải lỗi thay vì bỏ qua.
6. **Phân biệt resolution và runtime:** giải thích vì sao `Configuration.resolve(...)` cho bạn một `ResolvedModule` nhưng chưa cung cấp đối tượng `java.lang.Module` runtime của module ấy. Viết thêm phép kiểm tra trên `ModuleLayer` nếu bài toán triển khai cần.

**Ghi nhớ:** `ModuleDescriptor` là bản khai báo, `Configuration` là tập module đã được phân giải theo một phạm vi và các parent, còn `ResolvedModule.reads()` cho biết cạnh đọc có hiệu lực trong đồ thị ấy. Sử dụng cả ba góc nhìn mới đủ cơ sở phân tích quan hệ phụ thuộc JPMS, đặc biệt khi `requires transitive` hoặc cấu hình cha làm đồ thị kết quả khác danh sách `requires` nhìn thấy trong từng `module-info.java`.