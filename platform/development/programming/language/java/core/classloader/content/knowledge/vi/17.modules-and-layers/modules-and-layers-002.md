# Named module, unnamed module và automatic module trong Java

Từ Java 9, Java Platform Module System (JPMS) thêm khái niệm **module** vào quá trình tìm, nạp, liên kết và kiểm soát quyền truy cập class. Cùng một JAR chứa `com.example.Tool` có thể được nhìn như **thành phần classpath thuộc unnamed module** hoặc **automatic module có tên** khi đặt trên module path; một JAR có `module-info.class` thích hợp lại thường là **explicit named module**. Vị trí, descriptor và module resolution quyết định những gì một class có thể đọc/truy cập — không phải chỉ tên file JAR.

Ba khái niệm cần phân biệt:

- **Named module:** module có tên xác định. Có thể là *explicit named module* (khai báo `module-info.java`) hoặc *automatic module* (JAR cũ được module system đặt tên khi ở module path).
- **Unnamed module:** module **không có tên**, gom các class không thuộc named module của **một defining class loader**; classpath điển hình nằm trong unnamed module của application loader.
- **Automatic module:** **một loại named module** dành cho JAR không có module descriptor khi xuất hiện trên **module path**, giúp quá trình chuyển từ classpath sang JPMS diễn ra từng phần.

Bài thuộc nhóm **Module và layer** của Java core – classloader. Mục tiêu: giải thích đúng từng loại, bảng so sánh, quy tắc **reads / exports / opens**, module path và classpath, module resolution, ánh xạ module với loader, ví dụ Java 17+ biên dịch/chạy được, lỗi chuyển đổi phổ biến và cách thiết kế quá trình modularization.

## 1. Module khác package, JAR và ClassLoader như thế nào?

Một **package** gom các Java types theo namespace (ví dụ `demo.api`). Một **JAR** là định dạng archive chứa `.class`, resources và manifest. Một **ClassLoader** định nghĩa các runtime types và có chính sách tìm class. Một **module** là đơn vị JPMS có **tên, tập package, các yêu cầu phụ thuộc (`requires`), exports, opens và khai báo service**.

Không nên đánh đồng:

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Package | Class này nằm trong namespace nào? | `demo.api` |
| JAR | Bytecode/resource được đóng gói vật lý ra sao? | `legacy-tools.jar` |
| ClassLoader | Ai định nghĩa class và nó tìm class bằng cách nào? | Application loader, plugin loader |
| Module | Class thuộc module nào; module này đọc module nào; package được export/open ra sao? | `m.library`, `legacy.tools`, unnamed module |
| ModuleLayer | Tập named modules được resolve cùng quan hệ cha layer | `ModuleLayer.boot()` hoặc layer ứng dụng |
| ModuleFinder/module path | Runtime khám phá module artifacts ở những nơi nào? | `--module-path mods` |

**Một JAR không bắt buộc tương ứng một module named.** Trên classpath, nhiều JAR thường cùng góp class vào unnamed module của application loader. Trên module path, mỗi JAR hợp lệ được nhận diện như một module riêng (explicit hoặc automatic). Một directory module artifact có thể chứa cả một named module đã biên dịch.

**Một module không đồng nghĩa một ClassLoader.** Nhiều named modules của boot layer có thể do cùng bootstrap, platform hoặc application loader định nghĩa; `ModuleLayer.defineModulesWithManyLoaders` mới là một API chủ động tạo một loader cho mỗi module trong layer mới.

## 2. Named module — module có tên

**Named module** có tên lấy từ descriptor hay cơ chế đặt tên module. Đối với explicit named module, lập trình viên viết `module-info.java`:

```java
module m.library {
    exports demo.api;
}
```

Đây là **file `module-info.java` hoàn chỉnh**, không phải một Java class thông thường. Nó khai báo:

- Module name là `m.library`.
- Package `demo.api` được **export**, nên module đọc `m.library` có thể truy cập các public types/member hợp lệ của package này.
- Những package khác trong module **không tự động được export** ra bên ngoài.
- JPMS ngầm bổ sung phụ thuộc tới `java.base` cho những module thông thường.

Một module khác dùng API có thể khai báo:

```java
module m.app {
    requires m.library;
}
```

`requires` tạo dependency/readability từ `m.app` tới `m.library` khi module được resolve. Muốn dùng public class trong `demo.api`, còn cần `m.library` đã **export package** tương ứng.

### Named module có thể là explicit hoặc automatic

Thuật ngữ *named* chỉ nói **có tên**; nó **không** tự khẳng định descriptor là do developer viết. Automatic module cũng là named module, nhưng được tạo từ JAR chưa modularize.

Khi cần nói chính xác, dùng:

- **Explicit named module:** có module descriptor `module-info.class` được compile từ khai báo module (hoặc artifact modular tương đương).
- **Automatic named module:** tên/descriptor được module system suy ra cho **non-modular JAR đặt trên module path**.

Một explicit module có thể có `requires`, `requires transitive`, `requires static`, `exports`, `opens`, `uses` và `provides` với các ràng buộc rõ ràng. Không giả định mọi named module đều exports toàn bộ package.

## 3. Unnamed module — classpath không có tên module

Một `ClassLoader` có **một unnamed module riêng**, được truy vấn bằng:

```java
Module unnamed =
        ClassLoader.getSystemClassLoader().getUnnamedModule();
System.out.println(unnamed.isNamed()); // false
System.out.println(unnamed.getName());  // null
```

Đây là **đoạn minh họa trong method Java**. Với application class loader, class được đặt trên classpath mà không tham gia named module thường có:

```java
Module m = MyClass.class.getModule();
System.out.println(m.isNamed());             // false
System.out.println(m.getDescriptor() == null); // true
```

Đây cũng là **đoạn minh họa**, giả định `MyClass` nằm trên classpath. Unnamed module **không có `module-info.java`/ModuleDescriptor**, và `Module.getLayer()` đối với unnamed module là `null`.

### Những quy tắc khả năng đọc và truy cập

Theo Java SE 17, unnamed module:

1. **Reads mọi module.** `Module.canRead(other)` từ unnamed module trả `true` cho các module khác, kể cả named/unnamed.
2. **Exports mọi package của nó.** Những package ấy được coi là exported ra ngoài khi xét API runtime.
3. **Opens mọi package của nó.** Nó không có strong encapsulation ở cấp module; quy tắc Java access và reflection vẫn tiếp tục áp dụng.
4. **Không thể là dependency `requires` tường minh** trong `module-info.java` vì nó **không có tên để viết vào `requires`**.
5. **Chỉ mỗi loader quản lý unnamed module của riêng nó.** Unnamed module của system loader khác unnamed module của plugin loader; không có “một unnamed module duy nhất cho cả JVM”.

Một hệ quả dễ nhầm: dù **unnamed module đọc named module**, module vẫn phải **được resolve** vào configuration/layer để có class liên quan trong runtime, và classpath code chỉ truy cập được package **được export thích hợp**. `canRead=true` không tự tạo file JAR trong classpath, không tự resolve mọi module tùy ý, và không vô hiệu exports/Java access checks.

### Tại sao code classpath rất dễ phụ thuộc mọi thứ?

Trong ứng dụng Java truyền thống:

```bash
java -cp "out:lib/*" com.example.Main
```

các class từ `out` và những JAR do application class loader định nghĩa thường thuộc **cùng unnamed module của loader ấy**. Vì unnamed module reads mọi module và exports/opens mọi package của mình, nó cung cấp hành vi gần mô hình classpath trước Java 9: ít khai báo dependency ở mức JPMS, đổi lại khó kiểm soát ranh giới kiến trúc.

Dòng lệnh ở trên dùng ký tự `:` cho Linux/macOS; trên Windows dùng `;`. Đừng nhầm rằng wildcard `lib/*` biến các JAR thành automatic modules: **vị trí trong classpath** quyết định chúng thuộc unnamed module, dù chúng là các JAR thông thường.

## 4. Automatic module — cầu nối cho JAR chưa modularize

Một **non-modular JAR** không có `module-info.class`, khi đặt trên **module path**, có thể được module system xem như **automatic module**:

```text
lib/
└── legacy-tools.jar
      └── legacy/LegacyMessage.class
            |
            +-- đặt bằng --class-path ---> unnamed module
            |
            +-- đặt bằng --module-path --> automatic named module
                                         "legacy.tools"
```

Các đặc điểm của automatic module trong Java 17:

- **Có tên module** suy ra từ `Automatic-Module-Name` trong manifest nếu attribute tồn tại, nếu không từ tên JAR theo thuật toán ModuleFinder.
- **Không cần `module-info.class`**. Nếu JAR có descriptor module explicit hợp lệ thì đó là **explicit named module**, không phải automatic.
- **Được đối xử như exports và opens toàn bộ package** trong runtime.
- **Reads tất cả những named modules đã được resolve trong configuration**, và khi được tạo trong JVM cũng **reads mọi unnamed modules**.
- **Có thể bị module explicit khác `requires` theo tên**, ví dụ `requires legacy.tools;`.
- Hỗ trợ discovery các service providers từ metadata `META-INF/services` theo cơ chế dành cho automatic modules.
- **Vẫn tuân thủ ràng buộc module resolution**, như trùng tên module hoặc split-package conflict; không phải “classpath cũ có quyền truy cập vô hạn ở mọi tầng”.

Một chi tiết đặc tả: `ModuleDescriptor` của automatic module không có các `exports`/`opens` directives tường minh như descriptor do developer viết. Việc exports/opens mọi package là **cách module được runtime đối xử**, nên đừng suy từ `descriptor.exports().isEmpty()` rằng các package bị đóng. Dùng `module.isExported(...)` / `module.isOpen(...)` hoặc hiểu đúng modifier automatic.

### Automatic module có đọc classpath không?

**Có theo quy tắc module readability:** automatic module reads các unnamed modules khi được instantiated. Điều này là khả năng đọc ở **cấp module graph**. Nhưng source/library vẫn cần được đặt ở path và loader thích hợp, bytecode phải resolve được và các ràng buộc class loading/module access vẫn áp dụng. Không nên viết “automatic module luôn nhìn thấy mọi file trên ổ đĩa” hay coi nó thay cho cấu hình `--class-path`.

## 5. So sánh trực diện ba loại

| Tiêu chí | Explicit named module | Automatic module | Unnamed module |
| --- | --- | --- | --- |
| Có module name? | Có | **Có** | **Không** (`getName()==null`) |
| Descriptor do ai cung cấp? | Tác giả viết `module-info.java` hoặc tương đương | JVM/module finder tạo descriptor từ non-modular JAR | Không có descriptor |
| Phân phối thường gặp | Modular JAR/directory trên module path; runtime image | Non-modular **JAR trên module path** | Class files/JARs trên classpath của loader |
| `isNamed()` | `true` | `true` | `false` |
| `getDescriptor().isAutomatic()` | `false` | **`true`** | Descriptor là `null` |
| Reads ai? | Các module được khai báo/được module system bổ sung | Tất cả named modules đã resolve và unnamed modules | Tất cả modules |
| Exports package? | Chỉ package khai báo `exports` hoặc được phép bởi cấu hình runtime | Tất cả package | Tất cả package |
| Opens cho deep reflection? | Chỉ theo `opens`/`open module`/cấu hình tương ứng | Tất cả package | Tất cả package |
| Có thể dùng ở `requires`? | Có, theo tên | **Có**, theo tên | **Không**, vì không có tên |
| Vùng class identity | Binary name + defining loader; thêm ràng buộc JPMS | Tương tự | Tương tự |
| Dùng khi nào? | Module hóa thật, kiểm soát dependency/API | Chuyển tiếp thư viện JAR cũ sang JPMS | Ứng dụng classpath/legacy framework |

**Tên “automatic” không có nghĩa JVM tự convert bytecode hay rewrite code thành modular JAR.** Nó cấp một descriptor/module name mang tính cầu nối, còn class files vẫn là class files cũ.

**Tên “unnamed” không có nghĩa package/class không có tên.** Class `org.example.Service` vẫn có đầy đủ binary name; **chỉ module chứa class đó không có module name**.

## 6. Các cạnh module readability quan trọng

Giả sử ba module:

```text
m.app (explicit named)
   |
   +-- requires m.library  ------> m.library (explicit named)
   |
   +-- requires legacy.tools ----> legacy.tools (automatic named)

Unnamed module của application loader
   |
   +-- reads các named modules đã resolve (và các module khác)
   |
   +-- không có tên để named module viết "requires <unnamed>"
```

Trong mô hình mặc định:

- `m.app` reads `m.library` và `legacy.tools` vì khai báo `requires`.
- `m.app` **không tự reads** unnamed module chỉ vì có một classpath trên command line.
- `legacy.tools`, do là automatic module, reads cả unnamed module.
- Unnamed module reads `m.app`, `m.library`, `legacy.tools` khi chúng tồn tại trong runtime, nhưng **không có quyền vượt qua package không export từ explicit module**.

Để kiểm tra ở runtime:

```java
Module app = /* module m.app */;
Module api = /* module m.library */;
Module legacy = /* automatic module legacy.tools */;
Module unnamed = ClassLoader.getSystemClassLoader()
        .getUnnamedModule();

System.out.println(app.canRead(api));
System.out.println(app.canRead(legacy));
System.out.println(app.canRead(unnamed));
System.out.println(legacy.canRead(unnamed));
System.out.println(unnamed.canRead(app));
```

Đây là **đoạn minh họa**, không phải file biên dịch độc lập vì biến module cần lấy từ một `ModuleLayer` thực tế. Ví dụ thực thi đầy đủ bên dưới kiểm chứng các cạnh đặc biệt `app → unnamed` và `automatic → unnamed`.

### Không nhầm `reads` với `exports`

Trong JPMS:

- **`requires`/reads:** module A có thể tham chiếu các public types trong các module mà nó đọc **nếu package được export phù hợp**.
- **`exports`:** package của module B cho phép các module đọc B dùng public API hợp lệ.
- **`opens`:** cho phép deep reflection theo phạm vi mở; không biến mọi private member thành public source-level API.
- **`module-info.java`:** xác định các quan hệ tường minh của explicit modules; không áp dụng cách ghi đó cho unnamed module.

Ví dụ `m.app requires m.library` không đủ để truy cập `demo.internal.Hidden` nếu `m.library` không export `demo.internal`. Ngược lại, B export một package không khiến A mặc nhiên có read edge tới B.

## 7. Ví dụ hoàn chỉnh Java 17+: ba dạng module trong cùng ứng dụng

Đây là ví dụ **đã được biên dịch bằng `javac --release 17` và chạy**. Nó chứng minh automatic module là named, một explicit module `requires` nó, unnamed client đọc được các named modules **đã resolve**, và sự khác biệt read edge tới unnamed module.

### 7.1 Cấu trúc dự án

Tạo thư mục `module-kinds-demo`:

```text
module-kinds-demo/
├── src/
│   ├── m.library/
│   │   ├── module-info.java
│   │   └── demo/api/Answer.java
│   └── m.app/
│       ├── module-info.java
│       └── demo/app/Main.java
├── legacy-src/
│   └── legacy/LegacyMessage.java
├── classpath/
│   └── UnnamedClient.java
├── mods/
│   ├── m.library/             (output)
│   └── m.app/                 (output)
├── legacy-classes/           (output)
├── lib/
│   └── legacy-tools.jar      (artifact sinh bởi jar)
└── out/                       (output)
```

Tạo `mods/m.library`, `mods/m.app`, `legacy-classes`, `lib` và `out` trước khi compile. Các lệnh chạy từ **thư mục `module-kinds-demo`**. Không thêm `legacy-tools.jar` vào classpath khi muốn nó được nhận diện là automatic module.

### 7.2 Explicit module `m.library`

File `src/m.library/module-info.java`:

```java
module m.library {
    exports demo.api;
}
```

File `src/m.library/demo/api/Answer.java`:

```java
package demo.api;

public final class Answer {
    public static String value() {
        return "Named";
    }
}
```

Descriptor export `demo.api` cho module khác đọc `m.library`. Class `Answer` là public với static method dễ gọi và không có side effects.

### 7.3 JAR cũ không có module descriptor

File `legacy-src/legacy/LegacyMessage.java`:

```java
package legacy;

public final class LegacyMessage {
    public static String value() {
        return "Automatic";
    }
}
```

Ta sẽ biên dịch class này **không kèm `module-info.java`** rồi đóng JAR tên `legacy-tools.jar`. Module system suy ra module name **`legacy.tools`** khi file JAR nằm trên module path.

### 7.4 Explicit module `m.app` phụ thuộc cả hai

File `src/m.app/module-info.java`:

```java
module m.app {
    requires m.library;
    requires legacy.tools;
}
```

File `src/m.app/demo/app/Main.java`:

```java
package demo.app;

import demo.api.Answer;
import legacy.LegacyMessage;

public class Main {
    public static void main(String[] args) {
        System.out.println("main named: "
                + Main.class.getModule().isNamed());

        System.out.println("library module: "
                + Answer.class.getModule().getName());

        System.out.println("legacy automatic: "
                + LegacyMessage.class.getModule()
                        .getDescriptor().isAutomatic());

        System.out.println("values: "
                + Answer.value() + " + " + LegacyMessage.value());

        Module unnamed = ClassLoader.getSystemClassLoader()
                .getUnnamedModule();

        System.out.println("named reads unnamed: "
                + Main.class.getModule().canRead(unnamed));

        System.out.println("automatic reads unnamed: "
                + LegacyMessage.class.getModule().canRead(unnamed));
    }
}
```

`m.app` **requires automatic module `legacy.tools` bằng tên**, chứng minh automatic module là named module đúng nghĩa chứ không phải unnamed.

### 7.5 Một client ở classpath/unnamed module

File `classpath/UnnamedClient.java`:

```java
import demo.api.Answer;
import legacy.LegacyMessage;

public class UnnamedClient {
    public static void main(String[] args) {
        System.out.println("client named: "
                + UnnamedClient.class.getModule().isNamed());

        System.out.println("named value: " + Answer.value());
        System.out.println("auto value: " + LegacyMessage.value());
    }
}
```

`UnnamedClient` không có `module-info.java`, được biên dịch/chạy bằng `-cp`. Nó không `requires` được module nào do không có descriptor, nhưng unnamed module đọc những named modules được resolve.

### 7.6 Biên dịch hai artifacts nền tảng

**Bước 1: compile explicit `m.library`.**

```bash
javac --release 17 -d mods/m.library src/m.library/module-info.java src/m.library/demo/api/Answer.java
```

**Bước 2: compile legacy JAR và xem module name suy ra.**

```bash
javac --release 17 -d legacy-classes legacy-src/legacy/LegacyMessage.java
jar --create --file lib/legacy-tools.jar -C legacy-classes .
jar --describe-module --file lib/legacy-tools.jar
```

Phần quan trọng của kết quả `jar --describe-module`:

```text
No module descriptor found. Derived automatic module.

legacy.tools automatic
requires java.base mandated
contains legacy
```

Thứ tự/dòng phụ trong output có thể phụ thuộc phiên bản `jar`; điều cần kiểm tra là **`legacy.tools automatic`** và không có module descriptor tự viết.

### 7.7 Compile và chạy named application

**Windows** (`;` phân cách module-path entries):

```bash
javac --release 17 --module-path "mods;lib/legacy-tools.jar" -d mods/m.app src/m.app/module-info.java src/m.app/demo/app/Main.java
java --module-path "mods;lib/legacy-tools.jar" --module m.app/demo.app.Main
```

**Linux/macOS** (`:` phân cách module-path entries):

```bash
javac --release 17 --module-path "mods:lib/legacy-tools.jar" -d mods/m.app src/m.app/module-info.java src/m.app/demo/app/Main.java
java --module-path "mods:lib/legacy-tools.jar" --module m.app/demo.app.Main
```

Stdout đã kiểm tra:

```text
main named: true
library module: m.library
legacy automatic: true
values: Named + Automatic
named reads unnamed: false
automatic reads unnamed: true
```

Giải thích:

1. `Main` thuộc explicit named module `m.app`.
2. `Answer` thuộc named module `m.library`.
3. `LegacyMessage` thuộc automatic named module `legacy.tools`; descriptor của nó có `isAutomatic()==true`.
4. `m.app` dùng được cả hai API do có `requires` và các package thích hợp được export.
5. `m.app` **không** có read edge tới unnamed module chỉ do Java launcher tồn tại.
6. Automatic module **đọc được unnamed module** theo đặc tả Java 17.

Đây là bằng chứng trực tiếp rằng **named module thường và automatic module không có cùng default readability**, dù cả hai đều có module name.

### 7.8 Compile và chạy unnamed client

Khi ứng dụng classpath dùng classes trong named modules, các module đích phải được **resolve**. Ở ví dụ này, truyền `--add-modules m.library,legacy.tools` để bảo đảm module graph có chúng.

**Windows:**

```bash
javac --release 17 --module-path "mods;lib/legacy-tools.jar" --add-modules m.library,legacy.tools -d out classpath/UnnamedClient.java
java --module-path "mods;lib/legacy-tools.jar" --add-modules m.library,legacy.tools -cp out UnnamedClient
```

**Linux/macOS:**

```bash
javac --release 17 --module-path "mods:lib/legacy-tools.jar" --add-modules m.library,legacy.tools -d out classpath/UnnamedClient.java
java --module-path "mods:lib/legacy-tools.jar" --add-modules m.library,legacy.tools -cp out UnnamedClient
```

Stdout đã xác minh:

```text
client named: false
named value: Named
auto value: Automatic
```

Dù unnamed module không có `requires`, nó có thể sử dụng các exported public APIs của named modules **sau khi các module ấy được resolve**.

**Lưu ý:** `--module-path` chỉ làm artifacts trở nên **observable**; nó không có nghĩa module nào cũng mặc định **resolved** trong mọi kiểu launch. `--add-modules` là một cách chủ động thêm root modules. Với `java --module m.app/...`, `m.app` là root và module resolution kéo vào `m.library`/`legacy.tools` từ khai báo `requires`.

## 8. Lựa chọn classpath hay module path thay đổi bản chất của JAR

Một JAR truyền thống có thể nằm:

**A. Trên classpath:**

```bash
java -cp "out:lib/legacy-tools.jar" UnnamedClient
```

Lệnh này chỉ là **minh họa vị trí** trên Linux/macOS; nếu `UnnamedClient` còn cần `m.library`, phải cung cấp dependency ấy riêng (classpath hoặc named module đã resolve phù hợp). Điểm cốt lõi: `legacy-tools.jar` ở **classpath** ⇒ class của JAR thuộc **unnamed module** của defining loader tương ứng, không trở thành automatic module.

**B. Trên module path:**

```bash
java --module-path "mods:lib/legacy-tools.jar" --add-modules m.library,legacy.tools -cp out UnnamedClient
```

Ở đây, `legacy-tools.jar` có mặt trên module path và được resolve; `LegacyMessage.class.getModule().getName()` có thể trả `"legacy.tools"`, còn `getDescriptor().isAutomatic()` trả `true`.

**C. Sau khi JAR được modularize:** nếu tác giả thêm `module-info.class` hợp lệ và đóng JAR như modular artifact, nó trở thành **explicit named module** khi module system đọc descriptor ấy trên module path.

**Một vị trí không tự biến Java 8 bytecode thành Java 17 source:** automatic module là cách **JPMS bao gói module identity**, không thay đổi nội dung `LegacyMessage.class`.

## 9. Tên của automatic module được suy ra ra sao?

JPMS cần **module name** để explicit module có thể khai báo `requires`. Có hai nguồn ưu tiên:

1. Manifest của JAR có attribute **`Automatic-Module-Name`** → sử dụng giá trị khai báo nếu hợp lệ.
2. Nếu không có, module system **suy ra tên từ tên file JAR** theo quy tắc chuẩn: loại phần extension/phiên bản theo thuật toán, chuyển ký tự phân cách thích hợp và tạo tên module hợp lệ.

Ví dụ với artifact `legacy-tools.jar`, tên suy ra là `legacy.tools`. Tên JAR khác có thể tạo tên khác, và đổi tên artifact có thể làm **hỏng tất cả `requires old.name`**. Vì vậy, nhà phát hành thư viện định dần sang JPMS thường nên đặt attribute manifest ổn định:

```text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.legacy
```

Đây là **một phần manifest minh họa**, không phải tệp cần viết cho ví dụ `legacy.tools` đã chạy. Nếu sử dụng attribute trên, tên module sẽ là `com.acme.legacy` thay vì tên suy ra từ file.

Có thể kiểm tra artifact trước khi viết `requires`:

```bash
jar --describe-module --file lib/legacy-tools.jar
```

Đừng suy tên module bằng cách đoán mọi dấu gạch nối/tên phiên bản của JAR, nhất là artifact được đóng gói lại, shadow hoặc đổi tên qua repository. Dùng module descriptor/manifest thực tế.

### Automatic-Module-Name không đồng nghĩa explicit module

Attribute manifest chỉ cung cấp **tên**, không khai báo `requires`, `exports`, `opens` theo cách tường minh. Khi JAR đó là automatic module, runtime vẫn đối xử như exports/opens mọi package và reads rộng theo quy tắc automatic. Muốn chuyển thành explicit module thật, tác giả phải cung cấp module descriptor, kiểm soát package/API và xác minh dependency/service metadata.

## 10. Khi nào automatic module sẽ được resolve?

Một nguyên nhân gây khó hiểu: đặt JAR vào `--module-path` **không bảo đảm** mọi class trong JAR đã xuất hiện trong graph của chương trình.

Thông thường module được resolve khi:

- Nó là root module được chỉ định bằng `--module` hoặc `--add-modules`.
- Một module đã được resolve khai báo `requires` module ấy, khiến resolution xét tiếp dependency.
- Cấu hình launcher/build tool/module layer chủ động thêm module root hoặc cơ chế discovery phù hợp.

Trong ví dụ, `m.app requires legacy.tools;` làm module tự động được kéo vào graph khi khởi chạy `m.app`.

Với chương trình classpath `UnnamedClient` không có `module-info` để kê khai dependency, ta dùng:

```bash
--add-modules m.library,legacy.tools
```

Đây là **mảnh tham số command line**, không phải lệnh độc lập. Ngoài ra Java launcher có những token đặc biệt như `ALL-MODULE-PATH`, nhưng **không dùng `--add-modules ALL-MODULE-PATH` vô điều kiện trong production** vì có thể resolve các module không cần thiết, làm lộ xung đột tên/package hoặc tạo dependency graph phức tạp.

**Đừng nhầm ba trạng thái:** artifact có trên module path → **observable**; artifact được chọn/kéo vào graph → **resolved**; class cụ thể được yêu cầu → JVM/class loader **load/define** class đó. Ba bước không xảy ra cùng thời điểm và không đồng nghĩa.

## 11. Một unnamed module cho mỗi ClassLoader

Nếu dùng custom plugin class loaders:

```text
Application loader
   └── unnamed module của application loader

PluginLoader A
   └── unnamed module của A

PluginLoader B
   └── unnamed module của B
```

Mỗi loader có thể định nghĩa các class **không thuộc một named module nào**, và các class ấy được xếp vào **unnamed module của chính loader**.

Đoạn code minh họa:

```java
ClassLoader a = new ClassLoader(
        ClassLoader.getSystemClassLoader()) { };
ClassLoader b = new ClassLoader(
        ClassLoader.getSystemClassLoader()) { };

System.out.println(a.getUnnamedModule().isNamed());
System.out.println(a.getUnnamedModule() == b.getUnnamedModule());
System.out.println(a.getUnnamedModule().canRead(b.getUnnamedModule()));
```

Có thể đặt đoạn trên trong `main` của một class Java 17. Stdout dự kiến:

```text
false
false
true
```

Giải thích:

- Cả A và B đều có unnamed module nên `isNamed()` trả `false`.
- Hai loader khác nhau có **hai unnamed modules khác nhau**.
- Unnamed module reads mọi module nên `canRead` giữa chúng trả `true`.

**Readability không phải một cơ chế tự tìm class của loader kia**. Nếu A tự định nghĩa `plugin.Type`, `B.getUnnamedModule().canRead(A.getUnnamedModule())` trả true **không làm B.loadClass("plugin.Type") tự động tìm xuống A**. Đồ thị class loader delegation/defining loader và module readability là hai quan hệ khác nhau.

### Class identity vẫn phụ thuộc defining loader

Java runtime type identity gồm **binary name + defining class loader**, bất kể named hay unnamed. Hai plugin loaders cùng định nghĩa `plugin.Config` trong hai unnamed modules riêng là hai types khác nhau, dù package/class name trùng.

Ngược lại, hai named modules có thể dùng chung cùng loader nhưng vẫn có **module names và exports/readability riêng**. JPMS bổ sung lớp kiểm soát access, không thay thế quy tắc JVM về type identity.

## 12. Named module không thể thông thường `requires` unnamed module

Đây là một hạn chế kiến trúc quan trọng khi migration:

```java
module m.app {
    requires com.example.legacy;
}
```

Đoạn này hợp lệ **chỉ khi module có tên `com.example.legacy` có thể được module system tìm thấy và resolve**. Một JAR chỉ ở classpath sẽ thuộc unnamed module, không có module name để khai báo trong `requires`.

Hệ quả:

- **Classpath application** có thể dùng exported API của named module đã resolve.
- **Explicit named module** không thể viết `requires unnamed;` để phụ thuộc chính thức vào mã legacy chỉ còn trên classpath.
- Một đường chuyển tiếp là đưa legacy JAR lên **module path** thành automatic module có tên ổn định, sau đó `requires` nó.
- Đường lâu dài là modularize dependency thành explicit named module có descriptor/exports/opens có chủ đích.

Có thể dùng tùy chọn launcher `--add-reads m.app=ALL-UNNAMED` cho trường hợp migration/debug đặc biệt; nhưng đây là **read edge được thêm từ ngoài**, không làm unnamed module trở thành một module có tên, không tự sửa class loading hoặc biến mã legacy thành dependency JPMS được khai báo đầy đủ. Cần cấu hình cả compiler/runtime thích hợp nếu source lẫn execution đều cần edge này. Ưu tiên cấu trúc module dependency rõ ràng hơn với hệ thống dài hạn.

## 13. Exports, opens và runtime reflection

Một class có thể **load được** mà vẫn **không được phép truy cập** từ module khác. Ba dạng access dễ nhầm:

| Cơ chế | Ý nghĩa |
| --- | --- |
| `requires x;` | Module được đọc module `x` |
| `exports p;` | Export public API trong package `p` để module đọc có thể sử dụng |
| `exports p to y;` | Chỉ export package `p` cho module `y` |
| `opens p;` | Mở package cho deep reflection ở runtime theo các điều kiện tương ứng |
| `opens p to y;` | Mở package cho reflection của module `y` |
| `open module x { ... }` | Explicit named module mở các package theo quy tắc open module |
| Automatic module | Được runtime đối xử là **export và open mọi package** |
| Unnamed module | Được runtime đối xử là **export và open mọi package** |

Một ví dụ với named module:

```java
module m.library {
    exports demo.api;
    opens demo.internal to m.framework;
}
```

Đây là **descriptor minh họa**, giả định các package và target modules tồn tại. `m.framework` có thể cần `opens` để reflection sâu vào `demo.internal`; còn source-level access vào public types vẫn dựa trên `exports`.

**Không gọi automatic module là cơ chế security sandbox:** vì nó exports/opens mọi package nên module encapsulation rất lỏng. Unnamed module cũng có hành vi rộng tương tự. Và ngay cả với explicit module, exports/opens không bảo vệ toàn diện khỏi code độc hại trong cùng JVM.

### Khi gặp `InaccessibleObjectException`

Nếu code reflection từ classpath cố `setAccessible(true)` với private member trong package thuộc **explicit module không open**, có thể gặp `InaccessibleObjectException`. Việc unnamed module reads module đó không tự bỏ qua `opens`. Dùng public API, cấu hình `opens` đúng module, hoặc tạm dùng `--add-opens module/package=ALL-UNNAMED` khi thật sự cần và hiểu rủi ro.

## 14. Automatic module khi migration: có lợi nhưng không phải điểm kết thúc

**Lợi ích của automatic module:**

1. Cho phép explicit module viết `requires` tới thư viện chưa có descriptor.
2. Không buộc sửa source của thư viện legacy ngay trong một lượt migration.
3. Có module identity để quan sát qua `Class.getModule()` và module resolution.
4. Giữ tương thích ở mức class files/JAR packaging khi thư viện chuyển từ classpath sang module path.
5. Cho thời gian chuẩn hóa API exports/opens và service declarations trước khi chuyển hẳn sang explicit descriptor.

**Những rủi ro:**

- **Automatic module name thiếu ổn định** nếu chỉ suy từ artifact filename/version/renaming.
- **Tất cả package export/open**, làm lỏng encapsulation, kể cả implementation package không định public API.
- **Split packages** hoặc cùng module name giữa nhiều JAR có thể làm module resolution thất bại.
- **Đọc quá rộng**: automatic module có thể phụ thuộc vào named/unnamed modules mà chưa có dependency được khai báo tường minh.
- **Service discovery** có thể phụ thuộc metadata `META-INF/services`; khi chuyển sang explicit module, cần thiết kế `uses`/`provides` phù hợp.
- **Classpath fallback không vô hạn**: package/module mappings và loader policies có thể khiến class không được tìm theo kiểu classpath cũ.
- **Dependency chưa modularize transitive** có thể cần xử lý từng lớp hoặc gom thành các automatic modules mà module graph resolve được.

**Quy trình migration gợi ý:**

1. Kiểm kê JARs, packages, thư viện native/services/reflection.
2. Chạy `jar --describe-module` để biết explicit hay automatic và module names.
3. Ổn định module name qua manifest `Automatic-Module-Name` nếu thư viện chưa thể modularize.
4. Di chuyển một số dependency phù hợp sang module path, không quăng tất cả JAR vào cùng lúc.
5. Khai báo `requires` rõ ràng ở explicit modules và chạy integration tests.
6. Dò lỗi split-package, duplicate module names, deep reflection và service loader.
7. Tạo `module-info.java` thực sự cho thư viện khi đã xác định dependency và API surface.
8. Giữ `--add-reads`/`--add-opens`/`--add-exports` ở mức tối thiểu cần thiết và lên kế hoạch loại bỏ nếu có thể.

### Split package là gì?

Hai named modules cùng chứa một package, ví dụ cả `m.alpha` và `m.beta` có `com.acme.util`, có thể làm resolution hoặc tạo layer không hợp lệ tùy cấu hình/readability. Automatic modules cũng chịu checks này; không phải vì JAR “legacy” nên được miễn.

Classpath truyền thống từng cho phép nhiều JAR chứa class trong cùng package của một unnamed module, nhưng module system muốn package ownership rõ hơn. Khi gặp split package, thường cần tách package, gộp artifacts, shading có kiểm soát hoặc chuyển cấu trúc dependency — không thể chỉ thêm `requires` để sửa.

## 15. Module name, loader và layer cần quan sát cùng nhau

Một helper runtime:

```java
static void inspect(Class<?> type) {
    Module module = type.getModule();
    System.out.println("class=" + type.getName());
    System.out.println("loader=" + type.getClassLoader());
    System.out.println("module=" + module.getName());
    System.out.println("named=" + module.isNamed());
    System.out.println("layer=" + module.getLayer());

    if (module.isNamed()) {
        System.out.println("automatic="
                + module.getDescriptor().isAutomatic());
    }
}
```

Đây là **method minh họa**, cần đặt trong class để compile. Không gọi `module.getDescriptor().isAutomatic()` **khi module unnamed**, vì `getDescriptor()` có thể trả `null` và gây `NullPointerException`.

**Diễn giải:**

- `module.getName()==null` → unnamed module.
- `module.isNamed()==true` và `getDescriptor().isAutomatic()==true` → automatic named module.
- `module.isNamed()==true`, descriptor không automatic → named module loại khác (thường explicit).
- `module.getLayer()` chỉ liên quan layer của named module; với unnamed là `null`.
- `type.getClassLoader()` cho biết defining loader của class, **không phải module name**.

Mỗi lần debug, cần tách ít nhất ba câu hỏi: **Class do loader nào định nghĩa? Thuộc module nào? Module graph có read/export/open cạnh nào?**

### Các lệnh chẩn đoán hữu ích

```bash
jar --describe-module --file lib/legacy-tools.jar
java --module-path "mods:lib/legacy-tools.jar" --describe-module legacy.tools
java --module-path "mods:lib/legacy-tools.jar" --show-module-resolution --module m.app/demo.app.Main
```

Các lệnh trên viết với separator Linux/macOS; trên Windows đổi `:` thành `;`. Lệnh `--show-module-resolution` in thêm nhiều dòng resolution trên stderr/stdout trước output ứng dụng tùy launcher; dùng để xác định **module nào đã được resolve**, không phải chứng minh mọi class trong module đã được load.

Có thể dùng `jdeps` để khảo sát dependency của JAR/module khi chuẩn bị migration. Tuy nhiên output của `jdeps` cần đối chiếu reflective/service/native dependencies vì static analysis không thấy mọi đường nạp động.

## 16. Phân biệt các lỗi hay gặp

| Lỗi/triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `module not found: legacy.tools` khi `javac` | JAR chưa nằm trên module path hoặc module name khác dự đoán | `jar --describe-module`, kiểm tra manifest/JAR filename và `--module-path` |
| `package ... is not visible` | Thiếu `requires`, package chưa export hoặc module chưa resolved | Module descriptor/readability/exports và compiler options |
| `ClassNotFoundException` trong chương trình classpath dùng named module | Module artifact chỉ observable nhưng chưa resolved, hoặc loader/path sai | `--add-modules`, module graph, defining loader |
| `IllegalAccessError` / `InaccessibleObjectException` | Có module access restriction, thường reflection sâu vào explicit module | `exports`/`opens` hoặc chỉnh API |
| `FindException` / `ResolutionException` | Duplicate module name, split package, module không hợp lệ hoặc graph conflict | Rà module path/JAR packages |
| `NoClassDefFoundError` | Runtime thiếu dependency/linking/init thất bại | So compile vs runtime module/class paths và cause |
| `ServiceConfigurationError` | Module `uses`/`provides` hoặc `META-INF/services` sai | ServiceLoader API và metadata tương ứng |
| Tên module thay đổi sau đổi filename JAR | Automatic module name suy từ filename | Thêm `Automatic-Module-Name` ổn định hoặc chuyển explicit |
| Module explicit không dùng được classpath library | Không có `requires` tới unnamed module | Chuyển dependency thành automatic/explicit, hoặc read edge có chủ đích |
| Class trùng tên nhưng cast lỗi | Defining loaders khác nhau tạo runtime types khác nhau | In `Class.getClassLoader()`/`getModule()`, thống nhất API loader |

**Đừng sửa lỗi module bằng cách thêm bừa `--add-opens ALL-UNNAMED`.** Lệnh đó không chữa lỗi không tìm thấy module, không làm classpath JAR tự trở thành automatic module và không giải quyết class identity conflict.

## 17. Những nhầm lẫn rất dễ xuất hiện

| Nhầm lẫn | Đính chính |
| --- | --- |
| “Automatic module là unnamed module.” | **Sai.** Automatic module là **named module**; `isNamed()==true`. |
| “Một JAR có tên module là nó luôn automatic.” | Có descriptor `module-info.class` thì thường là **explicit named module**. |
| “JAR ở classpath vẫn dùng Automatic-Module-Name như named module.” | Không; ở classpath nó thuộc unnamed module của loader thích hợp. |
| “Unnamed module nghĩa là class không có package.” | Không; class thuộc `com.acme` vẫn có thể nằm trong unnamed module. |
| “Chỉ có một unnamed module trong JVM.” | Mỗi defining class loader có unnamed module riêng. |
| “Mọi named module có `requires` như nhau.” | Automatic module có readability rộng đặc biệt; explicit module dựa descriptor và graph. |
| “Automatic module có mọi package xuất hiện trong `descriptor.exports()`.” | Nó được **runtime đối xử** là exports/opens mọi package, không nhất thiết lưu từng directive trong descriptor. |
| “Module path chứa JAR là mọi class/JAR lập tức được nạp.” | Phải phân biệt **observable → resolved → class loading**. |
| “Unnamed module đọc tất cả thì đọc được private fields của explicit module.” | Không; `opens` và Java reflection access vẫn áp dụng. |
| “`requires m.library` biến loader của `m.library` thành parent.” | Không; module readability khác parent classloader delegation. |
| “Automatic module là kiến trúc module hóa đầy đủ.” | Nó là **cầu nối migration**, chưa đóng ranh giới package/dependency chặt. |
| “Có thể viết `requires unnamed;`.” | Không; unnamed module không có module name. |

## 18. Câu hỏi tự kiểm tra có đáp án

**1.** `legacy-tools.jar` không chứa `module-info.class`. Nếu dùng `-cp lib/legacy-tools.jar`, class trong JAR thuộc module gì?

**Đáp án:** Unnamed module của loader định nghĩa class tương ứng. Nó **không** tự trở thành automatic module chỉ vì tên JAR hợp lệ.

**2.** Nếu đặt JAR trên module path và được resolve, dạng module nào?

**Đáp án:** Automatic named module nếu JAR thật sự không có module descriptor. `getModule().isNamed()==true` và `getDescriptor().isAutomatic()==true`.

**3.** `Module.getName()==null` nghĩa là class không có tên binary?

**Đáp án:** Không. Chỉ có module là unnamed; class có thể có binary name bình thường như `com.demo.Tool`.

**4.** Vì sao `m.app requires legacy.tools` hợp lệ dù `legacy-tools.jar` không có `module-info.java`?

**Đáp án:** Khi JAR là automatic module ở module path, runtime tạo một named module `legacy.tools`. Explicit module có thể viết `requires` tới tên ấy.

**5.** `m.app` có thể tham chiếu thẳng `com.legacy.Helper` chỉ nằm trên classpath bằng `requires com.legacy;` không?

**Đáp án:** Không có named module tên `com.legacy` để resolve. Có thể chuyển JAR thành automatic module trên module path hoặc thiết kế migration khác; `--add-reads ...=ALL-UNNAMED` là lối tạm thời có giới hạn.

**6.** Module nào mặc định reads unnamed module: automatic hay explicit named?

**Đáp án:** Automatic module reads mọi unnamed module theo đặc tả. Explicit named module **không tự** reads unnamed, trừ khi read edge được thêm bằng cấu hình/API thích hợp.

**7.** Unnamed module có exports và opens mọi package không?

**Đáp án:** Có theo semantics JPMS. Điều đó **không xóa** Java visibility rules cho private/protected members hoặc cho phép vô điều kiện xuyên qua explicit named module khác.

**8.** Vì sao `--module-path lib` không tự bảo đảm `legacy.tools` có trong module graph?

**Đáp án:** Module chỉ *observable* từ path; cần module resolution chọn nó làm root, kéo vào qua `requires` hoặc quy tắc root khác. Có thể dùng `--add-modules legacy.tools` nếu ứng dụng classpath thực sự cần.

**9.** Làm sao xem tên automatic module đáng tin thay vì đoán tên JAR?

**Đáp án:** Dùng `jar --describe-module --file artifact.jar` và kiểm tra manifest `Automatic-Module-Name`. Nếu JAR chưa có descriptor, tên có thể suy từ filename theo quy tắc ModuleFinder.

**10.** Một `PluginLoader A` và `PluginLoader B` tạo hai unnamed modules. Vì sao hai class cùng tên vẫn có thể là hai types khác nhau?

**Đáp án:** JVM type identity gồm binary name + defining loader. Unnamed module readability không hợp nhất định nghĩa class giữa các loaders.

**11.** Trong output ví dụ, tại sao `main named: true` và `legacy automatic: true` đồng thời đều đúng?

**Đáp án:** `m.app` là explicit named module; `legacy.tools` là automatic named module. Cả hai đều có tên, nhưng descriptor/readability khác nhau.

**12.** Nếu package nội bộ trong automatic module đang bị reflection sâu truy cập, điều gì có thể đổi khi thư viện được chuyển thành explicit module?

**Đáp án:** Automatic module được mở toàn bộ packages. Explicit module mặc định chỉ opens những package được khai báo/mở phù hợp; code reflection có thể gặp access error nếu thiếu `opens`/cấu hình tương ứng. Cần kiểm thử migration.

## 19. Checklist dùng trong dự án thực

1. **Xác định artifact:** class nằm trong source output, plain JAR hay modular JAR?
2. **Xác định placement:** `--class-path` hay `--module-path`? Đừng lấy vị trí trên filesystem làm bằng chứng module type.
3. **Kiểm tra descriptor:** có `module-info.class` không? Có `Automatic-Module-Name`? `jar --describe-module` báo gì?
4. **Xác định module runtime:** `clazz.getModule().getName()` và `isNamed()` có đúng kỳ vọng?
5. **Kiểm tra automatic:** chỉ gọi `getDescriptor().isAutomatic()` khi module named.
6. **Kiểm tra resolution:** module chỉ observable hay thực sự resolved? Có `--add-modules` hoặc `requires` không?
7. **Kiểm tra graph:** module nào reads module nào? Package cần dùng có export không?
8. **Kiểm tra reflection:** code cần deep reflection có opens phù hợp không?
9. **Kiểm tra loader:** class do loader nào định nghĩa? Unnamed module của loader nào?
10. **Kiểm tra migration:** module names có ổn định? Có split packages, duplicate modules, JNI/SPI dependencies không?
11. **Kiểm tra test:** chạy cả compile và runtime command tương ứng JDK 17+, đừng chỉ biên dịch rồi coi module graph đúng.
12. **Giữ kiến trúc:** dùng automatic modules để chuyển tiếp, nhưng hướng tới explicit descriptors và dependency boundaries rõ ràng khi dự án sẵn sàng.

## Kết luận

**Named** nghĩa là module có tên; **unnamed** nghĩa là module không có tên (mỗi ClassLoader có một unnamed module riêng); **automatic** là một **named module đặc biệt** được suy ra từ non-modular JAR trên module path. Việc **đặt artifact ở classpath hay module path**, chọn module roots, resolve graph và áp dụng `reads/exports/opens` quyết định cách các class tương tác trong Java 17+.

Khi cần chẩn đoán, luôn phân biệt ba tầng độc lập nhưng liên hệ nhau: **(1) nơi lưu JAR/class trên classpath/module path, (2) module type và module graph/readability, (3) defining class loader và JVM type identity.** Đây là nền tảng để modularize các dự án classpath cũ mà không vô tình phá dependency hoặc reflection.

**Tài liệu chính thức:**

- [Java SE 17 — `java.lang.Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html) (named/unnamed, `getName`, `canRead`, `isExported`, `isOpen`).
- [Java SE 17 — `java.lang.module.ModuleDescriptor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.html) (automatic module modifier và cách runtime xử lý).
- [Java SE 17 — `java.lang.module` package specification](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/package-summary.html) (module resolution, readability graph).
- [Java SE 17 — `java` launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html) (`--module-path`, `--module`, `--add-modules`, `--add-reads`).
- [Java SE 17 — JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html) (`Automatic-Module-Name`).
- [dev.java — Incremental Modularization with Automatic Modules](https://dev.java/learn/organizing/modules/automatic-module/) (hướng dẫn chuyển đổi thư viện legacy).
