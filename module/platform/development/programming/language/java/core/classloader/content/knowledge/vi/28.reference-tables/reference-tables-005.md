# Thuật ngữ defining loader, initiating loader, runtime package và layer

## 1. Bốn thuật ngữ không được đánh đồng

Trong Java, một chuỗi tên lớp hoặc tên package không đủ xác định thực thể lúc JVM chạy. Các thuật ngữ được quy định rõ ở JVMS 17, mục 5.3 và 5.3.6:

| Thuật ngữ | Định nghĩa | Đặc điểm |
|---|---|---|
| **Defining loader** | Loader thực sự **định nghĩa** một runtime class/interface từ representation của lớp | Xác định identity của class cùng với binary name |
| **Initiating loader** | Loader **khởi xướng** quá trình nạp một class, trực tiếp hoặc thông qua delegation | Có thể khác defining loader; JVM dùng trong loading constraints |
| **Run-time package** | Cặp **(package name, defining loader)** | Không đồng nhất với tên package trong Java source |
| **Module layer** | Tập runtime modules được tạo từ `Configuration` và ánh xạ module name tới loader | Một loader có thể phục vụ nhiều named modules |

Ba đẳng thức ý niệm:

~~~text
Runtime class identity = (binary name, defining ClassLoader)
Run-time package      = (package name, defining ClassLoader)
Module layer          = (runtime modules, module-to-loader mapping)
~~~

Vì thế hai class đều có tên `demo.plugin.Worker` có thể khác nhau hoàn toàn về runtime identity; hai package tên `demo.plugin` cũng có thể khác run-time package; một ModuleLayer không nhất thiết chỉ chứa một ClassLoader.

## 2. Defining loader

Một loader L thực sự tạo runtime class C bằng cách nạp representation thích hợp và nhờ JVM định nghĩa C được gọi là **defining loader**. Với `Class<?> clazz`, method `clazz.getClassLoader()` trả về defining loader; kết quả `null` biểu diễn bootstrap loader khi thích hợp.

~~~text
PluginLoader L1 định nghĩa demo.plugin.Worker v1 → C1
PluginLoader L2 định nghĩa demo.plugin.Worker v2 → C2

C1.getName().equals(C2.getName()) == true
C1 == C2                              == false
C1.getClassLoader() != C2.getClassLoader()
~~~

Class identity không do tên JAR, đường URL hoặc tên file quyết định trực tiếp. Cùng một binary name nhưng khác defining loaders là hai runtime classes; một object thuộc implementation v1 không thể tự ép thành implementation v2. Ngược lại, hai plugin có thể trao đổi qua một interface được loader cha định nghĩa chung.

**Phân biệt với `ClassLoader.getParent()`:** parent của loader chỉ là tham chiếu dùng cho một số delegation paths. Defining loader là vai trò gắn với một runtime class cụ thể. Child có thể định nghĩa implementation class nhưng yêu cầu parent định nghĩa public API class.

## 3. Initiating loader và chuỗi delegation

Một loader có thể được JVM yêu cầu tải class tên N, sau đó delegate cho một loader khác. Loader được yêu cầu ban đầu là **initiating loader** theo khái niệm JVM; loader cuối cùng định nghĩa class là **defining loader**, và cũng là initiating loader.

~~~text
JVM cần demo.api.Api qua loader CHILD
             |
             v
CHILD.loadClass("demo.api.Api")
             |
        delegate parent
             |
             v
PARENT định nghĩa demo.api.Api
             |
             v
Trả Class<?> đã định nghĩa về CHILD

Defining loader: PARENT
Initiating loaders trong mô hình này: CHILD, PARENT
~~~

JVMS nêu rõ: nếu yêu cầu bắt đầu ở L1 và loader L2 định nghĩa class, cả L1 và L2 là initiating loaders. **Những loader chỉ là trung gian trong chuỗi delegation không mặc nhiên được ghi nhận là initiating loaders**; vì vậy không suy ra mọi parent trung gian đều có vai trò ấy.

### Vì sao JVM cần initiating loader?

Nó giúp JVM duy trì **loading constraints** để kiểm tra an toàn kiểu khi hai classes từ hai loaders tương tác qua method descriptors và field descriptors. Các ký hiệu của JVM:

- `<N, Ld>`: type có binary name N, được defining loader Ld định nghĩa.
- `N^Li`: type name N được xét qua initiating loader Li.
- Constraint như `N^L1 = N^L2` yêu cầu hai cách resolve tên có liên quan biểu diễn cùng runtime type. Vi phạm có thể gây `LinkageError`.

**Giới hạn quan sát:** Java SE 17 không có public API thông dụng `Class.getInitiatingLoaders()`. `Class.getClassLoader()` cho biết **defining loader**, không phải tập initiating loaders mà VM ghi nhận. Gọi `child.loadClass` rồi nhận Class object của parent chứng minh **delegation/defining loader**, nhưng không phải phép đọc trực tiếp VM initiating-loader records.

## 4. Run-time package là cặp package name và defining loader

Theo JVMS, runtime package không chỉ là chữ `package com.example;` trong source. Nó được xác định bằng:

~~~text
(package name, defining ClassLoader)
~~~

Ví dụ:

~~~text
L1 định nghĩa demo.same.A → run-time package (demo.same, L1)
L2 định nghĩa demo.same.B → run-time package (demo.same, L2)

Tên package giống?          Có
Run-time package giống?     Không
~~~

Package-private access yêu cầu runtime package phù hợp, không chỉ FQCN prefix giống nhau. Nếu bytecode từ L2 cố truy cập package-private member của class do L1 định nghĩa, JVM có thể ném `IllegalAccessError`, kể cả khi cả hai source files đều viết `package demo.same;`.

Kiểm tra thực tế:

~~~java
// Mã minh họa, khi đã có Class<?> a, b.
boolean sameRuntimePackage =
        a.getPackageName().equals(b.getPackageName())
        && a.getClassLoader() == b.getClassLoader();
~~~

`Class.getPackageName()` chỉ trả **tên**, còn `Class.getPackage()` trả metadata `Package`, không phải định danh run-time package của JVMS. Muốn kiểm chứng quyền package-private, cần xét **cả tên package lẫn defining loader**, và các quy tắc module/access control liên quan.

**Quan hệ với JPMS:** Một run-time package thuộc đúng một runtime module. Khi nhiều named modules cùng một ClassLoader, JVM không cho một run-time package bị “chia” qua nhiều modules; vì vậy mapping hai modules có cùng package vào một loader có thể khiến `LayerInstantiationException`. Nhưng cùng package name ở hai loaders khác nhau vẫn có thể tồn tại vì chúng là hai run-time packages khác nhau.

## 5. Ví dụ Java 17+ số 1: hai JAR, một binary name

Ví dụ so sánh hai class cùng `demo.plugin.Worker` được định nghĩa bởi hai `URLClassLoader` khác nhau, và cùng dùng shared API do parent định nghĩa.

### 5.1. Cấu trúc

~~~text
loader-glossary/
├── api-src/demo/api/Api.java
├── v1-src/demo/plugin/Worker.java
├── v2-src/demo/plugin/Worker.java
└── host-src/LoaderGlossaryDemo.java
~~~

**api-src/demo/api/Api.java**:

~~~java
package demo.api;

public interface Api {
    String message();
}
~~~

**v1-src/demo/plugin/Worker.java**:

~~~java
package demo.plugin;

import demo.api.Api;

public final class Worker implements Api {
    public Worker() {
    }

    @Override
    public String message() {
        return "v1";
    }
}
~~~

**v2-src/demo/plugin/Worker.java**:

~~~java
package demo.plugin;

import demo.api.Api;

public final class Worker implements Api {
    public Worker() {
    }

    @Override
    public String message() {
        return "v2";
    }
}
~~~

**host-src/LoaderGlossaryDemo.java**:

~~~java
import demo.api.Api;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class LoaderGlossaryDemo {
    private LoaderGlossaryDemo() {
    }

    private static boolean sameRuntimePackage(
            Class<?> left, Class<?> right) {
        return left.getPackageName().equals(right.getPackageName())
                && left.getClassLoader() == right.getClassLoader();
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: LoaderGlossaryDemo <v1.jar> <v2.jar>");
        }

        ClassLoader parent = Api.class.getClassLoader();

        URL url1 = Path.of(args[0]).toUri().toURL();
        URL url2 = Path.of(args[1]).toUri().toURL();

        try (URLClassLoader l1 =
                     new URLClassLoader(new URL[]{url1}, parent);
             URLClassLoader l2 =
                     new URLClassLoader(new URL[]{url2}, parent)) {

            Class<?> c1 = l1.loadClass("demo.plugin.Worker");
            Class<?> c2 = l2.loadClass("demo.plugin.Worker");

            Api p1 = (Api) c1.getConstructor().newInstance();
            Api p2 = (Api) c2.getConstructor().newInstance();

            Class<?> delegatedApi = l1.loadClass("demo.api.Api");

            System.out.println("Same binary name: "
                    + c1.getName().equals(c2.getName()));
            System.out.println("Same Class object: " + (c1 == c2));
            System.out.println("Different defining loaders: "
                    + (c1.getClassLoader() != c2.getClassLoader()));
            System.out.println("Same package name: "
                    + c1.getPackageName().equals(c2.getPackageName()));
            System.out.println("Same runtime package: "
                    + sameRuntimePackage(c1, c2));
            System.out.println("API delegated to parent: "
                    + (delegatedApi == Api.class));
            System.out.println("API defining loader is parent: "
                    + (delegatedApi.getClassLoader() == parent));
            System.out.println("Shared API cast works: "
                    + (p1 instanceof Api && p2 instanceof Api));
            System.out.println("Plugin values: "
                    + p1.message() + "," + p2.message());
            System.out.println("Distinct unnamed modules: "
                    + (c1.getModule() != c2.getModule()));
            System.out.println("Unnamed modules have no layer: "
                    + (c1.getModule().getLayer() == null
                    && c2.getModule().getLayer() == null));
        }
    }
}
~~~

**Tại sao hai plugin JAR không được đặt vào host classpath?** Vì `URLClassLoader` mặc định parent-first. Nếu parent đã có `demo.plugin.Worker`, cả hai child loaders có thể nhận bản của parent thay vì tự định nghĩa hai runtime classes. Hai JAR chỉ chứa implementation; **không** đóng gói `Api.class` bên trong chúng.

### 5.2. Bash: build và chạy

Từ thư mục `loader-glossary` với JDK 17+:

~~~bash
mkdir -p build/api build/host build/v1 build/v2 dist

javac -encoding UTF-8 -d build/api api-src/demo/api/Api.java

javac -encoding UTF-8 -cp build/api \
  -d build/v1 v1-src/demo/plugin/Worker.java

javac -encoding UTF-8 -cp build/api \
  -d build/v2 v2-src/demo/plugin/Worker.java

javac -encoding UTF-8 -cp build/api \
  -d build/host host-src/LoaderGlossaryDemo.java

jar --create --file dist/v1.jar -C build/v1 .
jar --create --file dist/v2.jar -C build/v2 .

java -cp "build/api:build/host" \
  LoaderGlossaryDemo dist/v1.jar dist/v2.jar
~~~

### 5.3. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force build/api,build/host,build/v1,build/v2,dist | Out-Null

javac -encoding UTF-8 -d build/api api-src/demo/api/Api.java

javac -encoding UTF-8 -cp build/api -d build/v1 v1-src/demo/plugin/Worker.java
javac -encoding UTF-8 -cp build/api -d build/v2 v2-src/demo/plugin/Worker.java
javac -encoding UTF-8 -cp build/api -d build/host host-src/LoaderGlossaryDemo.java

jar --create --file dist/v1.jar -C build/v1 .
jar --create --file dist/v2.jar -C build/v2 .

java -cp "build/api;build/host" LoaderGlossaryDemo dist/v1.jar dist/v2.jar
~~~

### 5.4. Stdout chính xác

~~~text
Same binary name: true
Same Class object: false
Different defining loaders: true
Same package name: true
Same runtime package: false
API delegated to parent: true
API defining loader is parent: true
Shared API cast works: true
Plugin values: v1,v2
Distinct unnamed modules: true
Unnamed modules have no layer: true
~~~

Các dòng này kiểm chứng **cùng binary name nhưng khác runtime classes**, **cùng package name nhưng khác run-time packages**, **parent định nghĩa shared API**, và **mỗi plugin loader có unnamed module riêng**.

Nó chỉ quan sát defining-loader/delegation qua public APIs; không tự đọc initiating-loader records bên trong JVM.

## 6. ModuleLayer và Module không phải ClassLoader

Java 9+ có JPMS, trong đó `ModuleLayer` là nhóm runtime named modules được tạo từ `Configuration` và phép ánh xạ **module name → ClassLoader**.

~~~text
LAYER ONE                            LAYER MANY

demo.alpha ──┐                       demo.alpha → Loader LA
             ├── Loader L
demo.beta ───┘                       demo.beta  → Loader LB
~~~

Các APIs tiêu biểu:

| API | Ý nghĩa |
|---|---|
| `ModuleLayer.boot()` | Boot layer của JVM |
| `layer.findModule("demo.alpha")` | Module object tương ứng |
| `layer.findLoader("demo.alpha")` | Loader được gắn với module |
| `module.getClassLoader()` | Loader của runtime module |
| `module.getLayer()` | Layer của named module |
| `layer.parents()` | Parent ModuleLayers |
| `layer.defineModulesWithOneLoader(cf, parentLoader)` | Một loader **mới** cho nhiều modules |
| `layer.defineModulesWithManyLoaders(cf, parentLoader)` | Một loader **mới** cho từng module |
| `layer.defineModules(cf, mapper)` | Mapping do framework cung cấp |

**Quan trọng:** `parentLoader` trong các convenience APIs nói về **parent của loader mới**, không phải loader trực tiếp định nghĩa modules. `layer.parents()` không tương đương `loader.getParent()`: đây là hai quan hệ khác nhau.

Các modules dùng chung loader vẫn có ranh giới `requires`, `exports` và `opens` riêng. Một loader có thể gắn nhiều named modules và vẫn có `ClassLoader.getUnnamedModule()` của chính nó. Một class thuộc đúng một runtime module thông qua runtime package tương ứng.

## 7. Ví dụ Java 17+ số 2: named modules và layers

Tạo hai named modules: `demo.alpha` xuất public API; `demo.beta` có `requires demo.alpha` và gọi alpha. Host tạo hai layers: một layer dùng chung loader, một layer dùng loader riêng.

### 7.1. Cấu trúc

~~~text
module-layer-glossary/
├── src/demo.alpha/module-info.java
├── src/demo.alpha/demo/alpha/Alpha.java
├── src/demo.beta/module-info.java
├── src/demo.beta/demo/beta/Beta.java
└── host-src/ModuleLayerGlossary.java
~~~

**src/demo.alpha/module-info.java**:

~~~java
module demo.alpha {
    exports demo.alpha;
}
~~~

**src/demo.alpha/demo/alpha/Alpha.java**:

~~~java
package demo.alpha;

public final class Alpha {
    private Alpha() {
    }

    public static String value() {
        return "ALPHA";
    }
}
~~~

**src/demo.beta/module-info.java**:

~~~java
module demo.beta {
    requires demo.alpha;
    exports demo.beta;
}
~~~

**src/demo.beta/demo/beta/Beta.java**:

~~~java
package demo.beta;

import demo.alpha.Alpha;

public final class Beta {
    private Beta() {
    }

    public static String call() {
        return Alpha.value() + ":BETA";
    }
}
~~~

**host-src/ModuleLayerGlossary.java**:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public final class ModuleLayerGlossary {
    private ModuleLayerGlossary() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: ModuleLayerGlossary <jar-dir>");
        }

        ModuleLayer boot = ModuleLayer.boot();
        ModuleFinder finder = ModuleFinder.of(Path.of(args[0]));
        Configuration cf = boot.configuration().resolve(
                finder, ModuleFinder.of(), Set.of("demo.beta"));

        ClassLoader parent = ClassLoader.getSystemClassLoader();

        ModuleLayer one =
                boot.defineModulesWithOneLoader(cf, parent);
        ClassLoader oneAlpha = one.findLoader("demo.alpha");
        ClassLoader oneBeta = one.findLoader("demo.beta");
        Class<?> alphaOne = oneAlpha.loadClass("demo.alpha.Alpha");
        Class<?> betaOne = oneBeta.loadClass("demo.beta.Beta");

        ModuleLayer many =
                boot.defineModulesWithManyLoaders(cf, parent);
        ClassLoader manyAlpha = many.findLoader("demo.alpha");
        ClassLoader manyBeta = many.findLoader("demo.beta");
        Class<?> alphaMany =
                manyAlpha.loadClass("demo.alpha.Alpha");
        Class<?> betaMany =
                manyBeta.loadClass("demo.beta.Beta");

        System.out.println("One loader shared: "
                + (oneAlpha == oneBeta));
        System.out.println("One modules distinct: "
                + (alphaOne.getModule() != betaOne.getModule()));
        System.out.println("Alpha module named: "
                + alphaOne.getModule().isNamed());
        System.out.println("Alpha belongs to one layer: "
                + (alphaOne.getModule().getLayer() == one));
        System.out.println("Boot parent layer: "
                + one.parents().contains(boot));
        System.out.println("Many loaders distinct: "
                + (manyAlpha != manyBeta));
        System.out.println("Many class loaders mapped: "
                + (alphaMany.getClassLoader() == manyAlpha
                && betaMany.getClassLoader() == manyBeta));

        String result = (String) betaMany.getMethod("call")
                .invoke(null);
        System.out.println("Beta calls alpha: " + result);

        System.out.println("Alpha Class same across layers: "
                + (alphaOne == alphaMany));
        System.out.println("Alpha Module same across layers: "
                + (alphaOne.getModule() == alphaMany.getModule()));
    }
}
~~~

### 7.2. Bash

Chạy từ thư mục `module-layer-glossary`:

~~~bash
mkdir -p mods host dist

javac -encoding UTF-8 --module-source-path src -d mods \
  src/demo.alpha/module-info.java \
  src/demo.alpha/demo/alpha/Alpha.java \
  src/demo.beta/module-info.java \
  src/demo.beta/demo/beta/Beta.java

javac -encoding UTF-8 -d host host-src/ModuleLayerGlossary.java

jar --create --file dist/demo.alpha.jar -C mods/demo.alpha .
jar --create --file dist/demo.beta.jar -C mods/demo.beta .

java -cp host ModuleLayerGlossary dist
~~~

### 7.3. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force mods,host,dist | Out-Null

javac -encoding UTF-8 --module-source-path src -d mods src/demo.alpha/module-info.java src/demo.alpha/demo/alpha/Alpha.java src/demo.beta/module-info.java src/demo.beta/demo/beta/Beta.java

javac -encoding UTF-8 -d host host-src/ModuleLayerGlossary.java

jar --create --file dist/demo.alpha.jar -C mods/demo.alpha .
jar --create --file dist/demo.beta.jar -C mods/demo.beta .

java -cp host ModuleLayerGlossary dist
~~~

Host không đặt modular JARs vào `-cp`, mà sử dụng `ModuleFinder.of(dist)` để resolve và tạo layer mới.

### 7.4. Stdout

~~~text
One loader shared: true
One modules distinct: true
Alpha module named: true
Alpha belongs to one layer: true
Boot parent layer: true
Many loaders distinct: true
Many class loaders mapped: true
Beta calls alpha: ALPHA:BETA
Alpha Class same across layers: false
Alpha Module same across layers: false
~~~

Đọc kết quả:

- Layer `one` đặt cả hai named modules vào **một loader**, nhưng modules vẫn là hai runtime objects khác nhau.
- Layer `many` đặt mỗi module vào một loader mới; beta vẫn gọi alpha nhờ `requires`/exports và direct delegation mà loader của layer hỗ trợ.
- Hai layers được tạo độc lập, class alpha và runtime module alpha ở mỗi layer khác identity.
- Layer creation không tự có nghĩa JVM eager-load toàn bộ classes; `loadClass` mới yêu cầu type cụ thể.

## 8. Tầng package, module và layer trong JPMS

Mối quan hệ nên đọc như sau:

~~~text
Runtime class
  |
  | binary name + defining loader
  v
Run-time package
  |
  | package name + defining loader
  v
Runtime Module (named/unnamed)
  |
  v
ModuleLayer (đối với named modules của layer)
~~~

Một run-time package thuộc **một runtime module**. Một runtime module được gắn với đúng một loader, nhưng một loader có thể phục vụ nhiều runtime modules. Một loader cũng có thể được gắn với modules từ nhiều layers trong một custom mapping hợp lệ.

Nếu gộp hai modules có overlapping packages vào cùng loader, `defineModulesWithOneLoader` có thể ném `LayerInstantiationException`. Split delegation (một loader phải tìm cùng package ở hơn một target loader) cũng là một giới hạn. Các constraints này không có nghĩa mọi JVM cấm hai loaders khác nhau định nghĩa cùng package name.

Cần phân biệt:

- **Package-private**: liên quan run-time package.
- **Module readability/exports/opens**: kiểm soát truy cập qua named-module boundary.
- **Loader visibility**: một loader có tìm được bytecode hoặc class qua delegation không.
- **Authorization** của người dùng cuối: chính sách ứng dụng; tìm thấy class/resource không có nghĩa người dùng được phép sử dụng.

## 9. Bảng chẩn đoán lỗi

| Lỗi hoặc dấu hiệu | Vấn đề có thể là |
|---|---|
| `ClassCastException` giữa hai tên class giống nhau | Hai defining loaders khác nhau tạo hai runtime types |
| `IllegalAccessError` khi gọi package-private member | Hai classes không cùng run-time package dù package names trùng |
| `LinkageError` liên quan loader constraint | Initiating-loader type resolutions không nhất quán |
| `NoClassDefFoundError` trong plugin | Loader đang resolve không nhìn thấy dependency đúng |
| `LayerInstantiationException` | Overlapping packages/split delegation/module mapping |
| `InaccessibleObjectException` | Thiếu module `opens` cho reflection |
| `IllegalAccessError` với public API named module | `requires` hoặc `exports` không phù hợp |
| `Class.getClassLoader() == null` | Lớp được bootstrap loader định nghĩa |
| Hai Module objects cùng name nhưng khác `==` | Hai runtime modules (có thể thuộc layers khác nhau) |

Không sửa bằng cách bắt `LinkageError` rồi tiếp tục vô điều kiện. Hãy kiểm tra classloader topology, runtime API identity, module graph và packaging.

## 10. Các ngộ nhận cần loại bỏ

| Nhận định sai | Giải thích đúng |
|---|---|
| Loader gọi `loadClass` chắc chắn define class | Nó có thể delegate cho parent |
| `Class.getClassLoader()` trả initiating loader | Trả defining loader |
| Mọi loader trung gian là initiating loader | JVMS không tự tính mọi trung gian |
| Cùng binary name tức cùng runtime type | Còn cần defining loader |
| Cùng package name tức cùng run-time package | Còn cần defining loader |
| Một loader chỉ phục vụ một module | Một loader có thể có nhiều named modules |
| Một ModuleLayer chính là một ClassLoader | Layer chứa modules, ánh xạ tới một/nhiều loaders |
| Parent layer bằng parent ClassLoader | Hai quan hệ khác nhau |
| Tạo layer là đã load mọi class trong đó | Module definition và class loading khác nhau |
| Named module khiến loader mất unnamed module | Loader vẫn có unnamed module riêng |
| TCCL quyết định identity của class | Defining loader mới quyết định runtime class identity |

## 11. Câu hỏi tự kiểm tra

**1.** Child yêu cầu Api, parent định nghĩa. Ai là defining loader?

**Đáp án:** Parent. Child có thể là initiating loader trong tiến trình nạp qua delegation.

**2.** Hai Classes `demo.plugin.Worker` cùng tên, khác defining loaders có cùng type?

**Đáp án:** Không. Class identity là binary name + defining loader.

**3.** Hai Classes có `package demo.same;` nhưng do hai loaders định nghĩa, cùng run-time package không?

**Đáp án:** Không. Tên package và defining loader phải cùng nhau trùng khớp.

**4.** `getClassLoader()` có cho biết mọi initiating loaders của một class không?

**Đáp án:** Không. Nó trả defining loader, còn initiating records thuộc ngữ nghĩa JVM.

**5.** Một layer có hai modules dùng một loader được không?

**Đáp án:** Có, nếu mapping hợp lệ, ví dụ `defineModulesWithOneLoader`.

**6.** Hai modules khác loader vẫn có thể giao tiếp?

**Đáp án:** Có, nếu readability/exports hợp lệ và loader delegation được tổ chức đúng.

**7.** Hai Module objects cùng tên ở hai layers có nhất thiết bằng nhau không?

**Đáp án:** Không. So sánh runtime identity bằng object tham chiếu.

**8.** Vì sao package-private access có thể thất bại dù source package giống nhau?

**Đáp án:** Vì defining loaders khác nhau tạo run-time packages khác nhau.

## 12. Tài liệu chính thức

- [JVMS 17 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3): defining và initiating loaders, runtime identities.
- [JVMS 17 — User-defined Loader](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.2): quy tắc loader khởi xướng.
- [JVMS 17 — Loading Constraints](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.4): an toàn kiểu qua loaders.
- [JVMS 17 — Modules and Layers](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.6): runtime module/package/layer.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): delegation và unnamed module.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): defining loader/package/module introspection.
- [Java SE 17 — ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html): module-to-loader mapping.
- [Java SE 17 — Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): runtime module identity.

**Tóm lại:** Defining loader tạo runtime class; initiating loader khởi xướng việc nạp và có thể khác defining loader. Run-time package gồm tên package **và** defining loader. ModuleLayer nhóm runtime modules với ánh xạ loaders; nó không phải ClassLoader và không bắt buộc một module trên một loader.