# Phạm vi tìm kiếm của ModuleFinder trước và sau cấu hình cha trong Java JPMS

## 1. Bài toán và các thuật ngữ cần phân biệt

Khi một runtime Java tạo module layer mới để nạp phần mở rộng, nó cần xác định **module nào sẽ được chọn cho mỗi tên module** và module đó nằm ở cấu hình mới hay đã được phân giải trong cấu hình cha. Trong Java Platform Module System (JPMS), công việc đó thuộc về `java.lang.module.Configuration.resolve(...)`. Hai tham số kiểu `ModuleFinder` có tên `before` và `after` quyết định thứ tự tìm kiếm so với **các cấu hình cha**.

Ba khái niệm quan trọng:

- **`ModuleFinder`:** một nguồn tra cứu `ModuleReference` theo *tên module*, ví dụ module trong JAR, exploded module hoặc runtime image. Nó mô tả module nào có thể tìm thấy, chưa tạo module layer và chưa nạp class.
- **`Configuration`:** kết quả phân giải các root module cùng những phụ thuộc cần thiết, chứa đồ thị khả năng đọc (*readability graph*) và quan hệ với các cấu hình cha. Một `ResolvedModule` trỏ tới `ModuleReference` đã chọn.
- **`ModuleLayer`:** bước hiện thực hóa cấu hình trong JVM bằng các runtime `Module` và class loader. Phân giải thành công chưa đồng nghĩa lớp của plugin đã được nạp hay plugin đã chạy.

Ví dụ: host có `demo.lib@1.0` trong cấu hình cha, plugin muốn dùng `demo.lib@2.0`, còn một kho dự phòng cung cấp `demo.lib@3.0`. Finder nào đưa ra module cùng tên và nó nằm ở đâu sẽ quyết định kết quả; JPMS **không tự chọn phiên bản cao nhất**.

Đề bài ở đây là hiểu chính xác **phạm vi và thứ tự tra cứu của `before` / `after` so với cấu hình cha**, cả với root và dependency, rồi biết cách quan sát kết quả và tránh nhầm với thứ tự nạp class.

## 2. Hợp đồng API: các overload cần đọc đúng

Java 17 cung cấp hai cách giải quyết cùng một bài toán (instance và static):

```java
// Instance: cấu hình nhận lời gọi là parent duy nhất.
Configuration child = parent.resolve(before, after, roots);

// Static: danh sách parent configurations được chỉ định rõ thứ tự.
Configuration child = Configuration.resolve(
        before, List.of(parentA, parentB), after, roots);
```

Đây là các đoạn **minh họa chữ ký/lời gọi**, giả sử các biến đã được khởi tạo; chương trình Java 17 chạy độc lập ở mục 6.

- `before`: finder có quyền được hỏi **trước** các cấu hình cha.
- `parents`: một hoặc nhiều `Configuration` cha được duyệt **theo thứ tự trong danh sách**. Với instance method, danh sách tương đương `List.of(parent)`.
- `after`: finder dự phòng, chỉ được dùng khi tên module không có ở `before` **và** không tìm thấy trong các cấu hình cha.
- `roots`: tập/tập hợp tên module bắt đầu quá trình phân giải. Root module cũng dùng chính thứ tự trên; tên trong `roots` không nhất thiết thuộc `before`.

Hai hàm tương ứng có service binding:

```java
Configuration child = parent.resolveAndBind(before, after, roots);

Configuration child = Configuration.resolveAndBind(
        before, List.of(parentA, parentB), after, roots);
```

`resolveAndBind` vẫn áp dụng tìm kiếm và các kiểm tra nhất quán của resolution, nhưng còn có bước khám phá provider cho service dependency; không nên giả định tập module được chọn sẽ giống `resolve` thường.

## 3. Thứ tự tìm kiếm chính xác cho mỗi tên module

Theo hợp đồng `Configuration.resolve(before, parents, after, roots)` của Java 17, khi cần định vị tên module `M`:

```text
Tìm M
  |
  v
before.find("M") ?
  | có --> chọn ModuleReference từ before
  |
  không
  v
parents[0].findModule("M") ?    // gồm tổ tiên của parent này
  | có --> dùng ResolvedModule đã có ở parent
  |
  không
  v
parents[1].findModule("M") ?    // nếu có nhiều parent
  | có --> dùng ResolvedModule đã có ở parent
  |
  không
  v
... các parent còn lại ...
  |
  v
after.find("M") ?
  | có --> chọn ModuleReference từ after
  |
  không --> không quan sát được module, resolution thất bại
```

**Thứ tự ưu tiên: `before → parents theo thứ tự tìm kiếm → after`.** Đối với một parent, lời gọi `parent.findModule("M")` tự tìm ở cấu hình đó trước, rồi tìm tiếp các tổ tiên theo thứ tự mà `parents()` công bố. Với nhiều parent, Javadoc mô tả việc gọi `findModule` lần lượt trên từng parent trong danh sách; đường đi trong mỗi cây cấu hình tương đương duyệt sâu trước.

Quy tắc này áp dụng cho:

1. **Root module**, ví dụ `demo.app` trong `roots`.
2. **Phụ thuộc trực tiếp**, ví dụ `demo.app requires demo.lib;`.
3. **Các phụ thuộc bắc cầu cần phân giải**, kể cả các cạnh đọc bổ sung được tính trong đồ thị sau đó.

Nếu một tên được tìm ở **parent configuration**, module ấy **không bị phân giải lại** và **không xuất hiện trong `child.modules()`**. Đây là khác biệt quan trọng giữa “được tìm thấy trong cây cấu hình” và “mới được thêm vào cấu hình con”.

Mốc “trước/sau” ở tên tham số nói về **ưu tiên tra cứu cho từng tên**, không phải thời điểm thực thi toàn bộ pipeline: không có quy tắc “load tất cả from before, chạy tất cả parent, sau đó mới load after”. Việc resolution duyệt các dependency có thể diễn ra theo thứ tự khác, nhưng quyết định lựa chọn nguồn cho mỗi tên tuân theo hợp đồng trên.

## 4. Phạm vi thực tế của từng nguồn

| Nguồn | Dữ liệu được tra cứu | Khi nào chọn | Hệ quả |
|---|---|---|---|
| `before` | Tên module mà finder này quan sát được | Có module tên yêu cầu | Ưu tiên hơn module cùng tên đã có trong parent và module trong after |
| Cấu hình cha thứ nhất | Các `ResolvedModule` trong chính cha và tổ tiên của nó | Before không có tên đó | Dùng lại module đã phân giải; không thêm lại vào child |
| Các cấu hình cha tiếp theo | Tương tự, theo danh sách `parents` | Tên không có trong before và các parent trước | Ưu tiên cha xuất hiện trước, không gộp ngẫu nhiên |
| `after` | Các module finder dự phòng biết đến | Before và mọi parent không có tên | Module được phân giải mới trong child nếu cần |
| Không nguồn nào thấy | Không tìm được tên | Resolution phải dùng tên đó | `FindException`, không tự suy ra module từ class path |

### Trường hợp cùng một tên xuất hiện nhiều nơi

Giả sử cả ba nơi có tên `demo.lib`:

```text
before : demo.lib@2.0
parent : demo.lib@1.0
after  : demo.lib@3.0

Khi cần demo.lib --> chọn before: demo.lib@2.0
```

Khi bỏ `demo.lib` khỏi before, parent thắng after. Khi không có `demo.lib` ở cả before lẫn parent, after mới được chọn. Dấu `@1.0` chỉ giúp quan sát trong ví dụ; ***không có thuật toán tự động chọn phiên bản cao nhất*** trong `Configuration.resolve`.

Cấu hình con có thể chọn module tên `demo.lib` mới từ before ngay cả khi cấu hình cha đã chứa một module cùng tên; bản module trong cha không bị “thay thế” hay sửa. Đừng hiểu kết quả là nâng cấp xuyên toàn bộ runtime. Những module trong cha vẫn thuộc cha và đồ thị module của các thành phần khác vẫn tồn tại. Các kiểm tra nhất quán có thể khiến một cách tổ hợp phụ thuộc trở thành `ResolutionException`; chiến lược shadow theo tên không phải lời bảo đảm mọi đồ thị đều hợp lệ.

### “After” không có nghĩa chỉ tìm module không tồn tại trên đĩa

`after` là một **finder độc lập**, không phải lệnh tự quét mọi thư mục còn lại. Nếu runtime truyền `ModuleFinder.of()` thì after rỗng; nếu truyền `ModuleFinder.of(path)` nó chỉ tìm trong các path đó; nếu truyền `ModuleFinder.ofSystem()` nó tìm system modules từ runtime image. Một module tồn tại trong một JAR khác ngoài các finder không tự nhiên trở nên “observable”.

## 5. Các cách tạo ModuleFinder và quy tắc bên trong một finder

Các cách thường gặp:

```java
ModuleFinder none = ModuleFinder.of();                 // không có entries
ModuleFinder plugins = ModuleFinder.of(pluginDir);    // thư mục chứa JAR/modules
ModuleFinder oneJar = ModuleFinder.of(pluginJar);     // một modular/automatic JAR
ModuleFinder system = ModuleFinder.ofSystem();        // module từ runtime image
ModuleFinder combined = ModuleFinder.compose(plugins, system);
```

Đây là đoạn minh họa: `pluginDir` và `pluginJar` là các biến `Path` đã có.

- `ModuleFinder.of(Path...)` tìm theo **thứ tự các path được đưa vào**. Khi nhiều path khác nhau có cùng tên module, finder chọn lần xuất hiện đầu tiên, không so sánh phiên bản để tìm bản mới nhất. Nếu **trong cùng một directory of modules** có nhiều module cùng tên thì đó là lỗi `FindException`.
- `ModuleFinder.compose(first, second, ...)` giữ ưu tiên theo thứ tự finder thành phần: tên thấy ở finder trước sẽ che tên ở finder sau. Đây là một thứ tự **bên trong một finder ghép**, khác với ba mức ưu tiên `before/parents/after` của `Configuration.resolve`.
- `find(String name)` trả `Optional<ModuleReference>`; `findAll()` trả tập tất cả module references finder thấy. Finder phải đưa ra góc nhìn nhất quán của các module mà nó công bố.
- Một `ModuleFinder` không bắt buộc thread-safe. Đối tượng tạo từ file path có thể quét/lỗi khi `find` hoặc `findAll` được gọi; không giả định phương thức `of(...)` đã kiểm tra toàn bộ JAR.
- Tệp JAR có `module-info.class` mô tả explicit named module. JAR không có descriptor có thể được nhận dạng là automatic module theo manifest/tên file; automatic modules có quy tắc resolution và readability rộng hơn, nên đặt chúng trên finder có thể làm phạm vi đồ thị lớn lên.

**Thứ tự hai tầng không được nhầm:**

```text
ModuleFinder.compose(A, B) trong BEFORE:
    A được hỏi trước B cho tên trùng nhau
Sau đó Configuration.resolve:
    BEFORE đã ghép -> PARENTS -> AFTER
```

Các module đang có trong `ModuleLayer.boot().configuration()` là **module đã được phân giải trong parent**, không phải tự động là tập mọi module mà `ModuleFinder.ofSystem()` có thể tìm. System finder có thể tìm cả module của runtime image không nằm trong graph boot ở một invocation cụ thể. Phân biệt “available in system image” và “already resolved in parent configuration”.

## 6. Chương trình Java 17 chạy được: quan sát before, parent và after

Ví dụ này tạo hai named modules chỉ có `module-info.class`: `demo.app` cần `demo.lib`. Ta đóng gói cùng descriptor của `demo.lib` thành ba modular JAR với phiên bản `1.0`, `2.0`, `3.0` để dễ nhìn nguồn được chọn. Không có plugin class hay service binding ở ví dụ này, vì mục tiêu là **resolution/ModuleFinder**, không phải class loading.

### 6.1. Cấu trúc nguồn

Tạo thư mục làm việc `module-order-demo/`:

```text
module-order-demo/
  src/
    lib/module-info.java
    app/module-info.java
    host/ModuleOrderDemo.java
  build/                         (được tạo bằng lệnh bên dưới)
    classes/lib/
    classes/app/
    parent/
    before/
    after/
    app/
    host/
```

**Tệp `src/lib/module-info.java`:**

```java
module demo.lib {
}
```

**Tệp `src/app/module-info.java`:**

```java
module demo.app {
    requires demo.lib;
}
```

**Tệp `src/host/ModuleOrderDemo.java`:**

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public final class ModuleOrderDemo {
    private static String describe(Configuration child) {
        var found = child.findModule("demo.lib").orElseThrow();
        String version = found.reference().descriptor().version()
                .orElseThrow().toString();
        boolean local = child.modules().contains(found);
        return "version=" + version + ",local=" + local;
    }

    public static void main(String[] args) {
        Configuration boot = ModuleLayer.boot().configuration();
        ModuleFinder empty = ModuleFinder.of();

        Path parentJar = Path.of("build/parent/demo.lib.jar");
        Path beforeJar = Path.of("build/before/demo.lib.jar");
        Path afterJar = Path.of("build/after/demo.lib.jar");
        Path appJar = Path.of("build/app/demo.app.jar");

        // Tạo cấu hình cha riêng: demo.lib@1.0 đã được resolve.
        Configuration parent = boot.resolve(
                ModuleFinder.of(parentJar), empty, Set.of("demo.lib"));

        // Before cung cấp demo.lib@2.0 dù parent có 1.0.
        Configuration beforeWins = parent.resolve(
                ModuleFinder.of(appJar, beforeJar),
                ModuleFinder.of(afterJar), Set.of("demo.app"));

        // Before chỉ có demo.app; parent cung cấp demo.lib@1.0.
        Configuration parentWins = parent.resolve(
                ModuleFinder.of(appJar),
                ModuleFinder.of(afterJar), Set.of("demo.app"));

        // Boot không có demo.lib; before không có demo.lib:
        // after được dùng để tìm demo.lib@3.0.
        Configuration afterFallback = boot.resolve(
                ModuleFinder.of(appJar),
                ModuleFinder.of(afterJar), Set.of("demo.app"));

        System.out.println("beforeWins: " + describe(beforeWins));
        System.out.println("parentWins: " + describe(parentWins));
        System.out.println("afterFallback: " + describe(afterFallback));
    }
}
```

**Giải thích thiết kế ví dụ:**

- `ModuleLayer.boot().configuration()` là cấu hình của boot layer, đã có `java.base`. Nhờ vậy `requires java.base` mặc định của những module mới có thể được đáp ứng từ parent.
- Gọi `boot.resolve(ModuleFinder.of(parentJar), empty, Set.of("demo.lib"))` tạo cấu hình `parent` chứa `demo.lib@1.0`. Đây là **cấu hình**, chưa tạo runtime `ModuleLayer` mới.
- Ở `beforeWins`, before finder biết cả root `demo.app` và `demo.lib@2.0`; phiên bản đó thắng parent 1.0 và after 3.0.
- Ở `parentWins`, trước chỉ biết `demo.app`; khi cần `demo.lib` thì dùng từ `parent`, nên `demo.lib` không phải module local của child.
- Ở `afterFallback`, parent là `boot` không có tên `demo.lib`, nên after bổ sung phiên bản 3.0.
- `child.findModule("demo.lib")` có thể tìm ở child hoặc parent; `child.modules().contains(found)` kiểm tra nó có thực sự thuộc chính child không.

### 6.2. Lệnh cho Windows PowerShell

Đứng ở thư mục `module-order-demo/` với JDK 17 hoặc mới hơn trên `PATH`:

```powershell
New-Item -ItemType Directory -Force -Path build/classes/lib,build/classes/app,build/parent,build/before,build/after,build/app,build/host | Out-Null

javac --release 17 -d build/classes/lib src/lib/module-info.java
jar --create --file build/parent/demo.lib.jar --module-version 1.0 -C build/classes/lib .
jar --create --file build/before/demo.lib.jar --module-version 2.0 -C build/classes/lib .
jar --create --file build/after/demo.lib.jar --module-version 3.0 -C build/classes/lib .

javac --release 17 --module-path build/parent/demo.lib.jar -d build/classes/app src/app/module-info.java
jar --create --file build/app/demo.app.jar -C build/classes/app .

javac --release 17 -d build/host src/host/ModuleOrderDemo.java
java -cp build/host ModuleOrderDemo
```

`jar --module-version` ghi version vào module descriptor của từng JAR; **không làm JPMS thực hiện semantic-version resolution**. Ta chỉ dùng version này để in ra nguồn đã thắng. `demo.app` được biên dịch với đường dẫn tới `demo.lib@1.0`, nhưng `requires demo.lib` trong descriptor ràng buộc **theo tên module**; nó không khóa phiên bản 1.0 trong lần resolution ở runtime.

### 6.3. Lệnh tương đương cho Linux/macOS

```bash
mkdir -p build/classes/lib build/classes/app build/parent build/before build/after build/app build/host

javac --release 17 -d build/classes/lib src/lib/module-info.java
jar --create --file build/parent/demo.lib.jar --module-version 1.0 -C build/classes/lib .
jar --create --file build/before/demo.lib.jar --module-version 2.0 -C build/classes/lib .
jar --create --file build/after/demo.lib.jar --module-version 3.0 -C build/classes/lib .

javac --release 17 --module-path build/parent/demo.lib.jar -d build/classes/app src/app/module-info.java
jar --create --file build/app/demo.app.jar -C build/classes/app .

javac --release 17 -d build/host src/host/ModuleOrderDemo.java
java -cp build/host ModuleOrderDemo
```

Chương trình host chạy ở class path và dùng API `java.lang.module` để **khảo sát cấu hình**, nên không cần tự đưa `demo.app` lên runtime module path. `Path.of("build/...")` dùng đường dẫn tương đối; phải đứng tại `module-order-demo/` khi chạy.

### 6.4. Stdout chính xác

```text
beforeWins: version=2.0,local=true
parentWins: version=1.0,local=false
afterFallback: version=3.0,local=true
```

Đầu ra này đã được kiểm tra bằng cách biên dịch mã với `javac --release 17` và chạy các modular JAR được tạo bởi `jar`.

- Dòng 1: `before` chọn 2.0 bất chấp 1.0 ở parent và 3.0 ở after; `local=true` vì mô-đun được phân giải trong child.
- Dòng 2: Parent đã chứa 1.0, nên after 3.0 **không thay thế**; `local=false` vì `demo.lib` thuộc parent config.
- Dòng 3: Không tìm được `demo.lib` từ before/boot, nên fallback 3.0 đi vào child.
- Ba cấu hình là **ba kết quả phân giải riêng biệt** trong chương trình; chúng không tự ghi đè lẫn nhau, và ví dụ không tạo layer runtime nào.

## 7. Root và dependency cùng đi qua một chuỗi tra cứu

Nhiều người cho rằng root luôn phải nằm trong before, còn after chỉ dành cho dependency. Quy tắc JDK nói rõ **root và transitive dependencies dùng cùng thứ tự tra cứu**.

| Tình huống cần tìm tên `M` | `before` | Parent | `after` | Kết quả |
|---|---|---|---|---|
| Root M ở before | M | M | M | M từ before |
| Root M vắng trong before, ở parent | không | M | M | M từ parent; không thêm vào child |
| Root M chỉ có ở after | không | không | M | M từ after |
| Dependency M của một root có ở cả before và parent | M | M | bất kỳ | Dependency từ before |
| Dependency M chỉ có ở parent/after | không | M | M | Dependency từ parent |
| Dependency M không ở đâu | không | không | không | `FindException` |

Khi tính dependency, resolver đọc descriptor (như `requires demo.lib;`), rồi chọn `demo.lib` theo bảng. Nếu bản trước và bản sau có descriptor khác nhau (dependency hoặc exported package khác), **đồ thị kết quả cũng khác**. Vì vậy khi thiết kế host plugin, thứ tự chọn finder ảnh hưởng cả khả năng tương thích và việc resolution có thành công hay không.

**Điểm quan trọng:** Nếu một root được tìm thấy trong parent, nó đã được phân giải ở đó và không được duyệt lại các dependency như một root mới trong child. Muốn có một module cùng tên được phân giải mới, phải cung cấp nó ở finder trước và bảo đảm đồ thị hợp lệ. Dùng after không thể ép một module đã tồn tại trong parent bị chọn lại.

## 8. Phân biệt Configuration.modules, findModule, parents và ModuleFinder.find

Những lời gọi sau trả lời bốn câu hỏi khác nhau:

```java
child.modules();                  // chỉ module được resolve trong child
child.findModule("demo.lib");      // child, rồi tới các cấu hình cha
child.parents();                  // danh sách direct parent configs
before.find("demo.lib");          // module *observable* qua finder before
```

Đây là đoạn minh họa trên biến của ví dụ; `before` ở đây biểu thị một `ModuleFinder`, không phải biến khai báo trong toàn bộ chương trình mục 6.

- `ModuleFinder.find(name)` trả `ModuleReference`, có thể đọc descriptor và location, nhưng module chưa chắc đã được chọn vào một `Configuration`.
- `Configuration.modules()` trả tập `ResolvedModule` **của cấu hình đó**; không bao gồm các module nằm ở parents.
- `Configuration.findModule(name)` tìm trong cấu hình hiện tại, sau đó ở các parent theo thứ tự tìm kiếm. Vì vậy phương thức này có thể tìm được module mà `modules()` của child không chứa.
- `ResolvedModule.reference().descriptor().version()` là metadata để quan sát, không chứng minh module nào đang chạy.
- `Configuration.parents()` ghi lại thứ tự parent. Với static method có nhiều parents, thứ tự này ảnh hưởng lookup; một cây cha có thể tự có cha của nó. Java mô tả tìm kiếm theo thứ tự gần với **depth-first search** trên các parent configurations.

Ví dụ muốn log chính xác lúc debugging:

```java
var resolved = child.findModule("demo.lib").orElseThrow();
System.out.println(resolved.name());
System.out.println(resolved.reference().location().orElse(null));
System.out.println(resolved.reference().descriptor().version().orElse(null));
System.out.println(child.modules().contains(resolved));
```

Đây là đoạn minh họa trong context đã có `child`. `location()` có thể rỗng và không nhất thiết là file path vật lý; đừng viết code sản phẩm phụ thuộc vào `toString()` của location như một module identity bảo đảm.

## 9. Có nhiều parent configurations thì tìm như thế nào?

Overload static cho phép:

```java
Configuration combined = Configuration.resolve(
        before,
        List.of(parentA, parentB),
        after,
        Set.of("demo.app"));
```

Trình tự tra cứu cho một tên `M`:

1. Hỏi `before`.
2. Nếu chưa có, hỏi `parentA.findModule(M)`: tự nó xét parentA rồi tổ tiên của A.
3. Nếu vẫn chưa có, hỏi `parentB.findModule(M)`: gồm parentB và tổ tiên của B.
4. Cuối cùng mới hỏi `after`.

**Parent được duyệt theo thứ tự danh sách**, không phải hợp nhất tập module rồi tìm “version tốt nhất”. Nếu hai parent có module tên giống nhau, việc chọn theo thứ tự là một quy tắc tìm kiếm; tính hợp lệ của đồ thị vẫn chịu những kiểm tra khác. Không nên dựa vào thiết kế nhiều parent chồng chéo để né quy định consistency.

Overload static yêu cầu danh sách `parents` không rỗng; Javadoc cũng nêu ràng buộc khi nhiều parent có target operating system, architecture hoặc version không nhất quán. Một đồ thị đã giải được bằng `Configuration.resolve` không bảo đảm runtime có thể tạo layer tùy tiện nếu các parent layers không khớp với parent configurations hoặc có xung đột package/loader.

Khi chỉ có một parent, dùng `parent.resolve(before, after, roots)` thường dễ đọc và ít sai hơn, vì API nêu rõ cha được kế thừa.

## 10. resolve và resolveAndBind khác nhau ở phạm vi quan sát

`resolve` theo các root và phụ thuộc `requires` tạo readability graph. `resolveAndBind` còn xét **service-use dependencies**:

- Sau khi giải root/dependency như `resolve`, các module có `uses` trong cấu hình mới **và các cấu hình cha** được xem xét.
- Resolver quét các module provider tìm được qua các `ModuleFinder` truyền vào (liên quan tới `findAll()`). Provider có `provides ... with ...` phù hợp có thể được bổ sung vào cấu hình mới, kéo theo các dependency của provider.
- Việc bổ sung service-provider có thể tạo thêm `uses`, nên quá trình này có thể lặp đến khi không còn module mới.
- `resolveAndBind` vẫn chịu các quy tắc tra cứu tên/kiểm tra đồ thị của resolution. Nó có thể đưa thêm module vào `child.modules()` mà chỉ nhìn `roots` và `requires` không dự đoán đủ.

Ví dụ descriptor định hướng, **không phải chương trình độc lập**:

```java
// module-info.java của module consumer
module demo.consumer {
    uses demo.api.Codec;
}

// module-info.java của provider
module demo.provider {
    requires demo.api;
    provides demo.api.Codec with demo.provider.JsonCodec;
}
```

Provider chỉ có thể được resolve/bind nếu descriptor, exports/readability, dependency và các finder được cấu hình hợp lệ. Thứ tự ưu tiên của finder không nên được diễn giải thành thứ tự thực thi provider hoặc chất lượng của provider.

**Tránh nhầm:** `ServiceLoader.load(...)` hoạt động ở bước khám phá service runtime; `Configuration.resolveAndBind(...)` mở rộng đồ thị module khi phân giải. Hai API có liên hệ về service provider nhưng giải quyết các giai đoạn khác nhau.

## 11. Khi resolution thất bại: tìm sai nguồn hay đồ thị không hợp lệ?

### FindException: vấn đề observability

`java.lang.module.FindException` thường xảy ra khi:

- Root hoặc dependency cần thiết không được tìm thấy trong `before`, các parent và `after`.
- Finder không đọc được JAR, sai descriptor `module-info.class`, hai module cùng tên nằm trong cùng một directory of modules, hoặc có lỗi khi tìm.
- Một module được tìm thấy nhưng descriptor không thể được parse hoặc metadata của module không hợp lệ.

Nếu before có một module lỗi, không nên mong resolver sẽ âm thầm “bỏ qua before để thử after” như một hệ thống tải lại dự phòng. Hành vi chính xác phụ thuộc lỗi finder; phải sửa hoặc lọc input, thay vì dùng after như cơ chế cứu mọi cấu hình hỏng.

### ResolutionException: vấn đề nhất quán đồ thị

`java.lang.module.ResolutionException` có thể xuất hiện khi:

- Module A `requires` B rồi tạo một chu trình requires không hợp lệ.
- Một module đọc hai module khác nhau có **cùng tên**; kể cả trường hợp module đọc một bản khác trùng tên với chính nó.
- Một module đọc đồng thời hai module export cùng package đến nó (split-package conflicts), hoặc package của chính module xung đột với package được đọc.
- Module khai báo `uses` / `provides` đối với kiểu service ở package không hiện diện hoặc không được export đúng theo readability.

Thứ tự before/parents/after chỉ chọn **ứng viên cho tên module**; nó không bỏ qua kiểm tra consistency. Việc tìm được đủ mọi module là điều kiện cần, chưa đủ để tạo đồ thị hợp lệ.

### Các lỗi khác

- `IllegalArgumentException` khi gọi static overload với danh sách parent rỗng hoặc cấu hình nhiều parent có target OS/architecture/version mâu thuẫn theo Javadoc.
- `SecurityException` trong môi trường có security policy/manager ngăn phép tìm module.
- Module image/descriptor có version mang tính metadata: không tự giải quyết khả năng tương thích binary/source hoặc xác thực nguồn JAR. Runtime phải kiểm tra phiên bản và quy tắc plugin của riêng mình trước khi xây module graph nếu đó là yêu cầu sản phẩm.

## 12. Từ Configuration tới ModuleLayer: ranh giới phải giữ rõ

Chương trình mục 6 **chỉ** tạo các `Configuration`. Để thực sự chạy code trong module, JVM cần một `ModuleLayer` phù hợp:

```java
// Minh họa khi parent là boot layer:
ModuleLayer bootLayer = ModuleLayer.boot();
Configuration child = bootLayer.configuration().resolve(
        before, ModuleFinder.of(), Set.of("demo.app"));
ModuleLayer layer = bootLayer.defineModulesWithOneLoader(
        child, ClassLoader.getSystemClassLoader());
```

Đây là đoạn **minh họa**: phải chuẩn bị finder và JAR có code hợp lệ, và parent configuration của child phải khớp với layer cha được dùng. Đừng áp dụng nguyên đoạn này vào `beforeWins` của ví dụ mục 6 vì parent configuration của nó **không trực tiếp là boot configuration**; muốn materialize nó cần tạo layer tương ứng cho parent trước, rồi mới tạo child layer với đúng quan hệ cha.

- `Configuration` quyết định mô-đun nào và cạnh readability nào tồn tại về mặt logic.
- `ModuleLayer` tạo runtime `Module` và ánh xạ module tới class loader. Nó còn kiểm tra những ràng buộc liên quan đến package và loader.
- `before` và `after` **không phải class loader**, cũng không định nghĩa “parent-first/child-first class loading” như ở `ClassLoader.loadClass`. Hai loại thứ tự này thuộc hai cơ chế riêng.
- Định nghĩa một layer mới không sửa parent layer; module trong parent tiếp tục hiện hữu ở layer đó.
- Nếu cần đưa plugin ra khỏi JVM hoặc hot reload, phải quản lý vòng đời các lớp, object, service registration, thread, cache và class loader; một `Configuration` không cung cấp thao tác “thay thế module đang chạy” tự động.

## 13. Automatic modules và các nguồn finder quá rộng

Một hệ thống dùng module path có thể gặp **automatic modules** tạo từ JAR chưa có `module-info.class`. Theo quy tắc module resolution, nếu có automatic module được enumerate, các automatic modules quan sát được khác cũng có thể phải được enumerate, nên kết quả có thể rộng hơn tập dependency nhìn thấy trong descriptor `requires`.

Tác động tới thiết kế `before` và `after`:

- Đặt cả thư mục plugin lớn vào `before` có thể làm nhiều automatic modules trở nên observable. Không nên giả định chỉ đúng một JAR được xem xét vì root ban đầu chỉ là một module.
- Khi dùng `resolveAndBind`, các service providers trong phạm vi finder có thể kéo thêm module vào graph. Có thể thay đổi phạm vi module được resolve khi thêm một JAR provider.
- `ModuleFinder.ofSystem()` có phạm vi hệ thống rộng. Nếu parent configuration đã có đủ system modules cần dùng, sử dụng `ModuleFinder.of()` làm `after` thường dễ kiểm soát hơn một finder bổ sung không chủ ý.
- Nếu cần chính sách chặt theo module name/version, hãy xác minh `find(name)` và `findAll()`, hạn chế đầu vào finder, kiểm tra metadata nguồn và consistency trước khi cho phép plugin được materialize.

JPMS không phải một dependency manager với khả năng tự xử lý Maven/Gradle-style version conflicts, cũng không thay thế isolation ở cấp process cho plugin không tin cậy.

## 14. Checklist điều tra và các lỗi hiểu sai phổ biến

| Biểu hiện | Cách kiểm tra |
|---|---|
| Module ở after không được chọn | Có module cùng tên trong before hoặc parent config không? |
| Parent chứa bản 1.0 nhưng child dùng 2.0 | Before có bản cùng tên; kiểm tra `child.modules()`, `ResolvedModule.reference().location()` |
| `findModule()` tìm được tên nhưng `modules()` không chứa | Module nằm trong parent configuration; kết quả này hợp lệ |
| Root “không nằm ở before” mà vẫn resolve | Root có thể được tìm trong parent hoặc after |
| Finder thấy JAR nhưng resolve báo thiếu dependency | Finder của root chưa chắc nhìn thấy mọi dependency; xác minh từng tên ở cả ba mức |
| Tên module đúng nhưng chọn sai JAR | Kiểm tra thứ tự `ModuleFinder.of(paths...)` và `ModuleFinder.compose(...)` trước khi xem thứ tự before/parent/after |
| Chọn bản version cao nhất? | Không có cơ chế đó: `before/parents/after` là chính sách precedence, không phải version solver |
| Split package/duplicate readability | Kiểm tra `requires`, `requires transitive`, `exports`, parent graph và lỗi `ResolutionException` |
| `resolveAndBind` đưa thêm module | Các module dùng `uses` và provider trong finder làm mở rộng graph |
| Cấu hình đã resolve nhưng class không tải được | Chưa chắc đã định nghĩa ModuleLayer; còn giới hạn loader, package, access và code |
| Plugin hot reload thấy bản cũ | Không thể sửa class/Module object của parent bằng cách đổi after finder; cần lifecycle/layer/loader mới |
| Chỉ thấy lỗi khi tìm nhiều module | `findAll()` có thể gặp JAR/descriptor lỗi, còn single-name `find()` chưa đi qua nguồn đó |

Khi thiết kế hợp đồng phân giải module cho runtime extensibility:

1. **Xác định parent configuration đã có những module nào**, không chỉ quan sát folder module path. Khi dùng nhiều parents, ghi rõ thứ tự và cây tổ tiên.
2. **Chọn nội dung `before` có chủ đích.** Đây là chỗ dùng khi thật sự muốn module mới có quyền được xét trước module cùng tên trong parent. Xác minh compatibility chứ không mặc định được override runtime.
3. **Chọn `after` làm nguồn fallback có giới hạn.** Nó không được quyền lấn át parent nếu before không tìm thấy.
4. **Phân biệt module observable và resolved.** In ra `finder.find(name)`, `Configuration.modules()` và `Configuration.findModule(name)` để lý giải nguồn được chọn.
5. **Kiểm thử các case trùng tên/thiếu tên và cả service binding.** Dùng module descriptor/version rõ ràng, assert đúng `ResolvedModule.configuration()` hoặc `modules().contains(...)`; kiểm tra cả `FindException` và `ResolutionException`.
6. **Materialize layer có chủ đích.** Cấu hình cha, parent layers, class loader và lifecycle phải khớp nhau; resolution chỉ là bước đầu.

**Ghi nhớ:** Trong `Configuration.resolve`, mỗi tên module được tìm theo **before → parent(s) → after**. Module đã có ở parent được dùng lại, không thêm vào cấu hình con; before có thể cung cấp một module cùng tên mới; after chỉ là nơi tìm sau cùng. Đây là quy tắc về **module resolution**, không phải thứ tự nạp class hay thuật toán chọn phiên bản.

**Nguồn chuẩn:** [Java SE 17 — Configuration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html), [ModuleFinder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html), [ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html) và [Module resolution](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/package-summary.html).
