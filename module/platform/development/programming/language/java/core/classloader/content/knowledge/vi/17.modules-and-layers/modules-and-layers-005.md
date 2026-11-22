# Quan hệ một loader với một hoặc nhiều module

## 1. Tổng quan

Trong Java 9+ (JPMS), **ClassLoader không có quan hệ một-một bắt buộc với Module**. Một loader có thể định nghĩa class thuộc **nhiều named modules**; tuy vậy từng runtime class thuộc **một module cụ thể**. Điều này có nghĩa:

- Cùng `ClassLoader` **không có nghĩa** hai class nằm trong cùng `Module`.
- Hai module có **ClassLoader khác nhau** vẫn có thể gọi public API của nhau nếu module graph/`exports` hợp lệ và loaders thực hiện delegation tương ứng.
- Quan hệ **parent ModuleLayer** không đồng nghĩa quan hệ **parent ClassLoader**.
- `ClassLoader.getUnnamedModule()` vẫn tồn tại ngay cả khi loader cũng định nghĩa các named modules.

Một `ModuleLayer` gắn các runtime `Module` objects với các loaders thông qua phép ánh xạ module → loader. Java 17 cung cấp `ModuleLayer.defineModulesWithOneLoader` (một loader cho nhiều module), `defineModulesWithManyLoaders` (mỗi module một loader), và `defineModules` (mapping tùy chỉnh).

## 2. Các khái niệm cần phân biệt

| Khái niệm | Vai trò | API quan sát |
|---|---|---|
| Class | Runtime type được định nghĩa bởi loader, thuộc module | `clazz.getClassLoader()`, `clazz.getModule()` |
| ClassLoader | Nạp/định nghĩa class và resource, có thể gắn nhiều module | `ClassLoader`, `getUnnamedModule()` |
| Module | Tập các package, module descriptor và quyền truy cập | `Module.getName()`, `getClassLoader()`, `getLayer()` |
| ModuleLayer | Các modules runtime được định nghĩa từ configuration cùng mapping loader | `findModule(name)`, `findLoader(name)` |
| Configuration | Modules đã resolve, quan hệ `requires` | `Configuration.resolve(...)` |
| ModuleFinder | Tìm modules từ modular JARs hoặc exploded modules | `ModuleFinder.of(...)` |

Một class `example.alpha.Alpha` có thể có defining loader L và thuộc module `demo.alpha`. Một class `example.beta.Beta` có thể **cũng do L định nghĩa** nhưng thuộc module `demo.beta`. Cả hai vẫn có module identity khác nhau và chịu `requires`, `exports`, `opens`.

## 3. Hai cách ánh xạ module–loader

~~~text
ONE LOADER
ModuleLayer ONE
  demo.alpha ────┐
                 ├────> ClassLoader L
  demo.beta  ────┘

Module alpha != Module beta
Defining loader alpha == defining loader beta


MANY LOADERS
ModuleLayer MANY
  demo.alpha ─────────> ClassLoader LA
  demo.beta  ─────────> ClassLoader LB

LA != LB
Beta có thể đọc/call Alpha nhờ requires + direct delegation.
~~~

Với `defineModulesWithOneLoader(cf,parentLoader)`, Java tạo **một loader mới** gắn mọi module trong configuration. Với `defineModulesWithManyLoaders(cf,parentLoader)`, Java tạo **một loader mới cho từng module**.

Tham số `parentLoader` trong hai API này **chỉ là parent của loader được tạo** — không phải loader trực tiếp nhận trách nhiệm định nghĩa modules. Muốn biết loader thực tế hãy gọi `layer.findLoader(moduleName)`.

## 4. Boot layer cũng minh họa quan hệ nhiều module–một loader

`ModuleLayer.boot()` tồn tại khi JVM khởi động, chứa `java.base` và những modules hệ thống được resolve. Các named modules của boot layer được phân bố trên **bootstrap, platform và system loaders** theo cấu hình runtime. Nhiều module có thể cùng một loader; bootstrap được biểu diễn bằng `null` trong `Class.getClassLoader()` hoặc `Module.getClassLoader()`.

Vì vậy quy tắc “một loader chỉ định nghĩa một named module” không đúng ngay cả với môi trường tiêu chuẩn.

`ModuleLayer.boot().configuration()` là một điểm khởi đầu thường dùng để resolve các modules mới. Layer mới có parent **layer** là boot, nhưng loader mới có parent **ClassLoader** tùy tham số caller chọn; hai quan hệ này không phải một.

## 5. Tạo layer gồm những bước nào?

~~~text
Modular JARs trong thư mục dist/
              |
              v
ModuleFinder.of(dist)
              |
              v
boot.configuration().resolve(...)
              |
              v
Configuration với requires dependencies
              |
              v
boot.defineModulesWithOneLoader(...)
           hoặc
boot.defineModulesWithManyLoaders(...)
              |
              v
ModuleLayer mới, modules mới, loaders mới
              |
              v
layer.findLoader(name).loadClass(binaryName)
~~~

`ModuleFinder` đọc module descriptors; `Configuration.resolve` xác định module graph; `ModuleLayer` định nghĩa các runtime modules và mapping. Một module đã được resolve/defined **không có nghĩa** mọi class của nó đã được nạp: loading có thể diễn ra khi cần.

Các phương thức tạo layer còn có biến thể static cho nhiều parent layers và `ModuleLayer.Controller`; ví dụ bài này sử dụng biến thể instance đơn giản với một parent layer.

## 6. Ví dụ Java 17+ hoàn chỉnh: hai named modules

Tạo cấu trúc:

~~~text
module-loader-demo/
├── src/
│   ├── demo.alpha/
│   │   ├── module-info.java
│   │   └── example/alpha/Alpha.java
│   └── demo.beta/
│       ├── module-info.java
│       └── example/beta/Beta.java
└── host-src/
    └── LayerMappingDemo.java
~~~

### 6.1. Module alpha

File **`src/demo.alpha/module-info.java`**:

~~~java
module demo.alpha {
    exports example.alpha;
}
~~~

File **`src/demo.alpha/example/alpha/Alpha.java`**:

~~~java
package example.alpha;

public final class Alpha {
    private Alpha() {
    }

    public static String value() {
        return "ALPHA";
    }
}
~~~

### 6.2. Module beta

File **`src/demo.beta/module-info.java`**:

~~~java
module demo.beta {
    requires demo.alpha;
    exports example.beta;
}
~~~

File **`src/demo.beta/example/beta/Beta.java`**:

~~~java
package example.beta;

import example.alpha.Alpha;

public final class Beta {
    private Beta() {
    }

    public static String call() {
        return "BETA->" + Alpha.value();
    }
}
~~~

Hai modules có **các package không trùng nhau**, phù hợp để dùng một loader trong thử nghiệm. `demo.beta` khai báo `requires demo.alpha`, nên module beta đọc module alpha. `demo.alpha` export package chứa public `Alpha` để beta có thể gọi nó.

### 6.3. Host tạo hai layers khác nhau

File **`host-src/LayerMappingDemo.java`**:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;

public final class LayerMappingDemo {
    private LayerMappingDemo() {
    }

    private static String invokeBeta(Class<?> beta)
            throws ReflectiveOperationException {
        Method method = beta.getMethod("call");
        return (String) method.invoke(null);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: LayerMappingDemo <module-directory>");
        }

        Path dir = Path.of(args[0]).toAbsolutePath().normalize();
        if (!Files.isDirectory(dir)) {
            throw new IllegalArgumentException("Missing module directory");
        }

        ModuleLayer boot = ModuleLayer.boot();
        ModuleFinder finder = ModuleFinder.of(dir);
        Configuration cf = boot.configuration().resolve(
                finder, ModuleFinder.of(), Set.of("demo.beta"));

        ClassLoader parentLoader = ClassLoader.getSystemClassLoader();
        ModuleLayer one =
                boot.defineModulesWithOneLoader(cf, parentLoader);

        ClassLoader oneALoader = one.findLoader("demo.alpha");
        ClassLoader oneBLoader = one.findLoader("demo.beta");
        Class<?> oneA =
                oneALoader.loadClass("example.alpha.Alpha");
        Class<?> oneB =
                oneBLoader.loadClass("example.beta.Beta");

        System.out.println("Boot has java.base: "
                + boot.findModule("java.base").isPresent());
        System.out.println("Host unnamed: "
                + !LayerMappingDemo.class.getModule().isNamed());
        System.out.println("One loader shared: "
                + (oneALoader == oneBLoader));
        System.out.println("One modules distinct: "
                + (oneA.getModule() != oneB.getModule()));
        System.out.println("One Alpha module mapped: "
                + (oneA.getModule()
                == one.findModule("demo.alpha").orElseThrow()));
        System.out.println("One Beta module mapped: "
                + (oneB.getModule()
                == one.findModule("demo.beta").orElseThrow()));
        System.out.println("One Beta calls Alpha: "
                + invokeBeta(oneB));
        System.out.println("One loader has unnamed module: "
                + !oneALoader.getUnnamedModule().isNamed());

        ModuleLayer many =
                boot.defineModulesWithManyLoaders(cf, parentLoader);
        ClassLoader manyALoader = many.findLoader("demo.alpha");
        ClassLoader manyBLoader = many.findLoader("demo.beta");
        Class<?> manyA =
                manyALoader.loadClass("example.alpha.Alpha");
        Class<?> manyB =
                manyBLoader.loadClass("example.beta.Beta");

        System.out.println("Many loaders distinct: "
                + (manyALoader != manyBLoader));
        System.out.println("Many Alpha mapped: "
                + (manyA.getClassLoader() == manyALoader));
        System.out.println("Many Beta mapped: "
                + (manyB.getClassLoader() == manyBLoader));
        System.out.println("Many Beta calls Alpha: "
                + invokeBeta(manyB));
        System.out.println("Alpha Class same across layers: "
                + (oneA == manyA));
        System.out.println("Alpha Module same across layers: "
                + (oneA.getModule() == manyA.getModule()));
        System.out.println("Both Alpha modules named: "
                + (oneA.getModule().isNamed()
                && manyA.getModule().isNamed()));
    }
}
~~~

Host không import `Alpha`/`Beta` và không cần đưa hai modular JARs lên application classpath lúc khởi chạy. Chính `ModuleFinder`, `Configuration` và `ModuleLayer` quản lý chúng.

### 6.4. Biên dịch, đóng JAR và chạy

**Bash (Linux/macOS/Git Bash):**

~~~bash
mkdir -p mods host dist

javac -encoding UTF-8 --module-source-path src -d mods \
  src/demo.alpha/module-info.java \
  src/demo.alpha/example/alpha/Alpha.java \
  src/demo.beta/module-info.java \
  src/demo.beta/example/beta/Beta.java

javac -encoding UTF-8 -d host host-src/LayerMappingDemo.java

jar --create --file dist/demo.alpha.jar -C mods/demo.alpha .
jar --create --file dist/demo.beta.jar -C mods/demo.beta .

java -cp host LayerMappingDemo dist
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force mods,host,dist | Out-Null

javac -encoding UTF-8 --module-source-path src -d mods src/demo.alpha/module-info.java src/demo.alpha/example/alpha/Alpha.java src/demo.beta/module-info.java src/demo.beta/example/beta/Beta.java

javac -encoding UTF-8 -d host host-src/LayerMappingDemo.java

jar --create --file dist/demo.alpha.jar -C mods/demo.alpha .
jar --create --file dist/demo.beta.jar -C mods/demo.beta .

java -cp host LayerMappingDemo dist
~~~

Yêu cầu JDK **17 trở lên** với `javac`, `jar`, `java` trên `PATH`. Mỗi module JAR chứa `module-info.class` và class tương ứng. Có thể xác minh bằng:

~~~bash
jar --describe-module --file dist/demo.alpha.jar
jar --describe-module --file dist/demo.beta.jar
~~~

**Stdout với đúng cấu hình:**

~~~text
Boot has java.base: true
Host unnamed: true
One loader shared: true
One modules distinct: true
One Alpha module mapped: true
One Beta module mapped: true
One Beta calls Alpha: BETA->ALPHA
One loader has unnamed module: true
Many loaders distinct: true
Many Alpha mapped: true
Many Beta mapped: true
Many Beta calls Alpha: BETA->ALPHA
Alpha Class same across layers: false
Alpha Module same across layers: false
Both Alpha modules named: true
~~~

Đây là kết quả xác định bởi phép so sánh object và logic `Alpha/Beta`, không dựa trên tên nội bộ của loader hoặc filesystem path.

## 7. Giải thích one-loader layer

~~~java
ModuleLayer one =
        boot.defineModulesWithOneLoader(cf, parentLoader);
~~~

Method tạo **một ClassLoader mới** cho các modules trong configuration. Vì vậy `one.findLoader("demo.alpha") == one.findLoader("demo.beta")` là `true`. Tuy nhiên `oneA.getModule() != oneB.getModule()` vẫn đúng: cùng loader không hợp nhất modules.

Java vẫn thực thi quy tắc `requires`, `exports` và `opens` theo module identity. Ví dụ, package-private member trong module alpha không được beta truy cập chỉ vì cùng loader. Quyền truy cập module và Java access control cần được thỏa.

Một loader có thể chứa nhiều modules; điều đó không có nghĩa các modules được xem như JARs hợp nhất trên classpath.

## 8. Giải thích many-loaders layer

~~~java
ModuleLayer many =
        boot.defineModulesWithManyLoaders(cf, parentLoader);
~~~

Method tạo **mỗi module một loader**. Loader cho `demo.beta` có thể thực hiện **direct delegation** tới loader của `demo.alpha` theo mapping module/package. Vì vậy `Beta.call()` vẫn gọi `Alpha.value()` mặc dù loaders khác nhau.

Hai loader của module beta/alpha không cần có quan hệ parent–child trực tiếp. Cả hai loader mới có `parentLoader` do caller truyền vào làm parent, ngoài ra còn cơ chế direct delegation theo module graph.

**Đừng suy luận rằng ClassLoader bình thường tự hiểu `requires`.** Nếu bạn tự tạo custom loaders và dùng `defineModules(cf, mapping)`, phải xây dựng delegation tương thích module readability và resource loading theo yêu cầu.

## 9. Hai layers cùng tên module có thể khác runtime identity

Ví dụ tạo hai layers từ cùng modular JARs:

~~~text
Layer one:
  Module demo.alpha → oneALoader → Class Alpha#one

Layer many:
  Module demo.alpha → manyALoader → Class Alpha#many
~~~

Hai `Class<?>` không bằng `==` vì defining loaders khác nhau. Hai `Module` objects cũng khác vì chúng được định nghĩa cho hai layers riêng.

Đừng dùng một mình chuỗi `Class.getName()` hay `Module.getName()` để nhận định runtime identity. So sánh class/module/loader object khi cần debug.

## 10. Unnamed module vẫn tồn tại

Mỗi loader có một `getUnnamedModule()`; ngay cả loader dùng để định nghĩa named modules vẫn có unnamed module của mình.

~~~java
// Minh họa khi đã có oneALoader:
Module unnamed = oneALoader.getUnnamedModule();
System.out.println(unnamed.isNamed()); // false
~~~

Một class được loader nạp vào named module **không bị chuyển sang unnamed module** vì phương thức trên tồn tại. `Class.getModule()` của `Alpha` vẫn là `demo.alpha`.

Host chạy bằng `java -cp host` thuộc unnamed module của **host loader**, khác các named modules mới trong layer. Đó là lý do `LayerMappingDemo.class.getModule().isNamed()` trả `false` trong chương trình.

## 11. Giới hạn khi gộp nhiều modules vào một loader

`defineModulesWithOneLoader` không thể sử dụng cho mọi configuration. Theo Java SE 17, các trường hợp có thể làm tạo layer thất bại gồm:

- **Overlapping packages:** hai modules của configuration khai báo cùng package nhưng đều được gắn một loader.
- **Split delegation:** loader chung phải delegate việc tìm class thuộc một package sang **hơn một loader** khác nhau trong module graph.
- Các hạn chế chung về `java.base` hoặc package `java` và `java.*`.

Ví dụ nếu cả `demo.alpha` và `demo.beta` đều chứa `example.shared`, một one-loader layer sẽ không có package owner duy nhất và có thể ném `LayerInstantiationException`.

Giải pháp thường là tách package rõ ràng hoặc đưa shared types sang một module API riêng mà hai modules cùng `requires`. Không áp dụng kiểu chọn “JAR nào đứng trước thì thắng” của classpath cho JPMS một cách máy móc.

## 12. Tìm resource trong named modules

Javadoc của các loader do `ModuleLayer` tạo lưu ý resource lookup có thể **khác parent-first URLClassLoader**:

- One-loader layer tìm resource trong **các modules của layer** trước parent loader.
- Many-loaders layer tìm resource trong **module gắn với loader đó** trước parent loader.
- Resource thuộc named module còn chịu quy tắc encapsulation và package `opens`; không phải mọi file trong JAR đều được mở cho mọi caller.

API `Module.getResourceAsStream(name)` giúp làm việc với resource của module cụ thể khi có quyền truy cập phù hợp. Không đoán thứ tự ưu tiên resource của module layer chỉ dựa trên classpath/URLClassLoader thường.

## 13. Readability, exports, opens khác với class loader visibility

| Quan hệ | Ví dụ | Ý nghĩa |
|---|---|---|
| Module readability | `requires demo.alpha` | `demo.beta` đọc module alpha |
| Export public API | `exports example.alpha` | Cho phép truy cập public types trong package |
| Deep reflection | `opens example.internal` | Cho phép reflective access phù hợp |
| Defining loader | `clazz.getClassLoader()` | Loader định nghĩa runtime class |
| Runtime module | `clazz.getModule()` | Module chứa runtime class |
| Parent ClassLoader | `loader.getParent()` | Quan hệ loader fallback/delegation |
| Parent ModuleLayer | `layer.parents()` | Quan hệ layer configuration |

Một loader **tìm được `Class<?>`** không bảo đảm code từ module khác có quyền gọi mọi member của class. Cùng ClassLoader vẫn chịu `exports`/`opens` và Java access control. Khác loader không tự động chặn quyền truy cập public API được export.

## 14. Khi dùng custom module loaders

`ModuleLayer.defineModules(cf, name -> loader)` cho phép ứng dụng tự ánh xạ modules. Trong hệ plugin, cần bảo đảm:

1. Mỗi module name được ánh xạ tới loader hợp lệ.
2. Không đặt các modules có overlapping packages vào cùng loader.
3. Không định nghĩa lại module cùng tên trong loader đã có module đó.
4. Mỗi loader tìm được bytecode/resources tương ứng với modules mà nó sở hữu.
5. Delegation tuân module readability và không gây vòng chờ giữa loaders.
6. Loader xử lý concurrent class loading an toàn; cân nhắc parallel-capable loader.
7. Vòng đời loader, resources, task/thread và reload được điều phối.

`registerAsParallelCapable()` không tự làm mutable state của loader thread-safe. Nếu loader tự viết `findClass`, vẫn phải xử lý cache và I/O đồng thời đúng.

## 15. Lỗi thường gặp

| Hiện tượng | Cách hiểu đúng |
|---|---|
| Hai class cùng loader nhưng thuộc module khác nhau | Một loader có thể phục vụ nhiều named modules |
| Two-module layer tạo lỗi package overlap | Không thể gộp hai modules có package chồng chéo vào cùng loader |
| Beta gọi được Alpha dù hai loader khác nhau | JPMS direct delegation theo module graph |
| Lấy `findLoader` khác tham số `parentLoader` | Method tạo loader **mới**; tham số chỉ là parent |
| Cùng module name ở hai layer không bằng object | Runtime Module identity khác nhau |
| `IllegalAccessError` dù đã load class | Kiểm tra `requires`/`exports` và access control |
| Reflection thất bại | Kiểm tra `opens` và caller context |
| Host `getModule().getName()` trả null | Classpath host nằm trong unnamed module |
| Resource trong module không thấy | Kiểm tra module resource encapsulation và lookup |
| Custom loader không tìm dependency readable | Mapping và direct delegation chưa tương thích |
| Nghĩ parent layer có một parent loader | Layer và loader là hai cấu trúc khác nhau |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Một ClassLoader có thể định nghĩa class thuộc hai named modules không?

**Đáp án:** Có. `defineModulesWithOneLoader` tạo một loader cho nhiều modules, miễn configuration hợp lệ.

**Câu 2.** Hai classes cùng ClassLoader có chắc cùng `Class.getModule()` không?

**Đáp án:** Không. Class của `demo.alpha` và `demo.beta` thuộc hai modules khác nhau.

**Câu 3.** `defineModulesWithManyLoaders` dùng một loader mới cho mỗi module hay nhận loader trực tiếp từ `parentLoader`?

**Đáp án:** Nó tạo mỗi module một loader mới, với `parentLoader` làm parent của chúng.

**Câu 4.** Vì sao beta có thể gọi alpha dù loader khác nhau?

**Đáp án:** `requires`, `exports` và direct delegation của layer-created loaders phù hợp.

**Câu 5.** Cùng tên module ở hai layer có đảm bảo cùng Module object?

**Đáp án:** Không. Trong ví dụ mỗi layer tạo Module objects khác nhau.

**Câu 6.** Tại sao overlapping packages làm one-loader layer thất bại?

**Đáp án:** Một loader không thể gắn hai modules cùng package theo quy tắc tạo layer đó.

**Câu 7.** `getUnnamedModule()` có nghĩa loader không thể phục vụ named modules?

**Đáp án:** Không. Loader vẫn có unnamed module của riêng mình dù phục vụ named modules.

## 17. Tài liệu chính thức

- [Java SE 17 — ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html) — ánh xạ one/many/custom loader và điều kiện tạo layer.
- [Java SE 17 — Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html) — loader, layer và module identity.
- [Java SE 17 — Class.getModule](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getModule()) — runtime module của class.
- [Java SE 17 — ModuleFinder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html) — tìm modules.
- [Java SE 17 — Configuration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html) — module graph resolution.
- [JVMS 17 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html) — class identity và module membership.

**Kết luận:** **Một loader có thể phục vụ một hoặc nhiều modules**; classloader mapping không xóa module boundaries. Khi thiết kế Java module layers, luôn xem đồng thời module graph, package ownership, exports/opens, loader identity và direct delegation.