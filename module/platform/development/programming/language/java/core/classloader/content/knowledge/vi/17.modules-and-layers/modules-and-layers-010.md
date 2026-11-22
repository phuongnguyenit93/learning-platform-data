# Giới hạn split package và các lỗi cấu hình ModuleLayer trong Java

## 1. Split package là gì, vì sao gây rắc rối trong JPMS?

**Split package** xảy ra khi các class thuộc **cùng một package name** được phân bố trong hai hay nhiều module hoặc artifact khác nhau. Ví dụ hai module đều chứa `com.example.shared`:

~~~text
module alpha                       module beta
├── module-info.class              ├── module-info.class
└── com/example/shared/            └── com/example/shared/
    └── Alpha.class                    └── Beta.class

Cùng package name: com.example.shared
Khác module name: alpha và beta
~~~

Trong Java classpath truyền thống, các class có cùng package trên nhiều JAR có thể được class loader tìm theo thứ tự. Điều này dễ che giấu xung đột và phụ thuộc vào cấu hình. **Java Platform Module System (JPMS, Java 9+)** cần cấu hình module rõ ràng, nên áp đặt các kiểm tra mạnh hơn liên quan package, readability, exports và **loader mapping**.

Không nên hiểu split package bằng một luật đơn giản “hai named modules cùng có package p là luôn bị cấm”. Các quy tắc quan trọng **phụ thuộc giai đoạn và cách sử dụng**:

1. **Khi module resolution:** một module **không được đọc hai module khác nhau cùng export một package tới nó**. Bản thân module đang chứa package p cũng có thể xung đột với package p được module nó đọc export tới nó.
2. **Khi tạo layer:** hai module có package trùng **không thể cùng được định nghĩa trong một class loader**. `ModuleLayer.defineModulesWithOneLoader` từ chối overlapping packages ngay cả trong một số cấu hình mà resolution đã thành công.
3. **Khi dùng nhiều loaders:** `defineModulesWithManyLoaders` cho phép mỗi module có loader riêng, nên có thể chứa package name trùng nếu module configuration đã hợp lệ và không có xung đột readability/exports khác.
4. **Khi chạy classpath:** các class thuộc unnamed module của loader tương ứng; việc nhiều JAR có cùng package không tự đồng nghĩa với cùng loại lỗi cấu hình layer của JPMS.

Bài này giúp phân biệt **lỗi resolve graph**, **lỗi định nghĩa layer**, **lỗi visibility khi truy cập class** và **lỗi định danh kiểu**, kèm thí nghiệm Java 17+ có thể biên dịch/chạy.

## 2. Bốn khái niệm phải phân biệt

### 2.1. Module path không phải module graph

`--module-path` chỉ cho JPMS các vị trí quan sát module. Một JAR nằm trên module path **chưa chắc được resolved** vào cấu hình đang chạy. Java bắt đầu từ **root modules**, theo các quan hệ `requires`, rồi tính readability.

Đặt hai JAR cùng chứa package vào module path chưa đủ để kết luận runtime phải thất bại: cần xác định **chúng có được chọn vào graph không, export tới ai và được gắn loader thế nào**.

### 2.2. Configuration là kết quả giải quyết dependency

`java.lang.module.Configuration` biểu diễn một tập **resolved modules** và readability graph tương ứng. Ví dụ `ModuleLayer.boot().configuration()` là configuration của boot layer. APIs `Configuration.resolve` và `resolveAndBind` có thể tạo configuration mới dựa trên module finders, parent configurations và tập root names.

Resolution có thể ném `FindException` nếu không tìm được module, hoặc `ResolutionException` nếu không xây được một graph hợp lệ vì những ràng buộc phụ thuộc/xuất package.

### 2.3. ModuleLayer là các runtime Module gắn với ClassLoader

`ModuleLayer` chứa runtime `Module` objects cho một configuration và mapping từ **module name tới ClassLoader**. Một layer có parent layer(s), và class loading phải tôn trọng module membership/delegation.

Hai factory methods quan trọng:

- `defineModulesWithOneLoader(cf, parentLoader)`: tạo **một loader mới** dùng cho tất cả modules trong configuration. Có thể thất bại nếu modules chứa package trùng.
- `defineModulesWithManyLoaders(cf, parentLoader)`: tạo **một loader riêng cho mỗi module**. Không có cùng điều kiện cấm overlapping packages *chỉ do dùng chung loader*.
- `defineModules(cf, classLoaderFunction)`: advanced mapping, cho phép điều khiển loader; có kiểm tra package conflicts và ownership chặt chẽ.

Cả hai phương thức `WithOneLoader` và `WithManyLoaders` trả về **layer mới**, không sửa nội dung của boot layer hay biến class loader đã có thành một loader khác.

### 2.4. Runtime package và Class identity

Runtime package liên quan **package name và defining loader**. Với named modules, class còn thuộc một runtime module (`Class.getModule()`). Hai class cùng package text nhưng thuộc loader khác nhau **không mặc nhiên là cùng runtime package** để dùng package-private access.

Hai class có **cùng binary name** mà được định nghĩa bởi hai loader khác nhau cũng có thể là **hai kiểu runtime khác nhau**; không thể cast lẫn nhau chỉ vì tên/bytes trùng.

## 3. Ràng buộc ở thời điểm module resolution

Một nguyên tắc đặc tả Java 17 là: **resolution thất bại nếu có hai hoặc nhiều modules export cùng package tới một module đọc cả hai**.

Giả sử:

~~~text
module consumer
    requires alpha
    requires beta

module alpha exports com.example.api
module beta  exports com.example.api
~~~

Nếu consumer đọc cả alpha và beta và cả hai export `com.example.api` tới consumer, Java không thể chọn một nghĩa duy nhất cho các public types của package đó. Module resolution sẽ từ chối configuration, thường dưới dạng `ResolutionException` hoặc lỗi phân giải module phù hợp ở launcher.

Không cần hai module có cùng **class name** để gặp vấn đề: cùng **package name** đã đủ cho xung đột readability/export.

### 3.1. Trường hợp xung đột với chính package của consumer

Cũng không hợp lệ khi module `consumer` chứa package `com.example.api` **và** đọc một module khác export chính package đó tới consumer theo quy tắc resolution. Đây là package conflict trong readability graph, không phải lỗi vì Java compiler không tìm thấy một file class.

### 3.2. Exports có thể qualified

`exports com.example.api to consumer;` chỉ export tới module consumer đã chỉ định. Vì vậy phải xét **đích export thực tế**, không chỉ việc descriptor có từ khóa `exports`.

Module `other` không đọc hoặc không được export package đó chưa chắc thấy conflict giống consumer. Một tool phân tích module graph cần xét cả qualified exports và `requires transitive`, không đơn thuần đếm trùng tên package trong mọi file trên disk.

### 3.3. Automatic modules có thêm hiệu ứng

Một JAR không có `module-info.class` có thể trở thành **automatic module** trên module path. Các packages của automatic module được export rộng và module có readability rules đặc biệt. Khi resolver đưa automatic module vào graph, các automatic modules observable có thể cùng được enumerated theo quy tắc JPMS, khiến split packages từ các thư viện cũ trở thành xung đột tưởng như bất ngờ.

Khi migration, kiểm tra tên automatic module (có thể suy từ tên file JAR hoặc từ `Automatic-Module-Name`) và package exports, chứ không chỉ sửa danh sách `requires` theo cảm tính.

## 4. Ràng buộc ở thời điểm tạo ModuleLayer

Resolution hợp lệ vẫn chưa chứng minh có thể tạo layer bằng **mọi cách mapping class loaders**.

### 4.1. defineModulesWithOneLoader

~~~java
ModuleLayer layer = ModuleLayer.boot()
        .defineModulesWithOneLoader(configuration, parentLoader);
~~~

Đây là **đoạn minh họa**, giả sử `configuration` là Configuration hợp lệ và `parentLoader` là ClassLoader phù hợp.

Phương thức tạo một loader mới cho tất cả modules trong configuration. Theo Javadoc Java 17, layer construction có thể thất bại khi:

- **Overlapping packages:** hai hay nhiều modules trong configuration có cùng package.
- **Split delegation:** loader tạo ra cần delegate tới **hơn một loader khác** để tải các classes của một package cụ thể.
- Module `java.base` không được tạo lại trong configuration mới.
- Module chứa package `java` hoặc bắt đầu bằng `java.` không được định nghĩa theo cách này.

Các tình huống phù hợp có thể ném `LayerInstantiationException`. Lưu ý một **configuration hợp lệ ở resolution** vẫn có thể có overlapping packages không export sang cùng consumer; với one-loader strategy, điều đó vẫn đủ khiến layer creation bị bác bỏ.

### 4.2. defineModulesWithManyLoaders

~~~java
ModuleLayer layer = ModuleLayer.boot()
        .defineModulesWithManyLoaders(configuration, parentLoader);
~~~

Ở cách này Java tạo một loader cho từng module. Nếu alpha và beta cùng chứa package `com.example.internal` nhưng chúng ở hai loader khác nhau, mô hình này **có thể** hợp lệ miễn configuration đã qua resolution và không vi phạm những ràng buộc khác.

Không suy rằng `ManyLoaders` là công cụ “bỏ qua mọi module conflict”: nó **không sửa một Configuration có readability/exports conflicts**. Chỉ sau khi `Configuration.resolve` thành công mới tới bước định nghĩa layer.

### 4.3. defineModules: ánh xạ thủ công

Với `ModuleLayer.defineModules`, caller cung cấp function quyết định loader cho từng module. Javadoc nêu các dạng lỗi quan trọng:

- Hai module cùng package được map vào **cùng ClassLoader**.
- Một module được map vào loader đã định nghĩa module **cùng tên**.
- Module được map vào loader đã định nghĩa classes thuộc một trong các packages của module mới.
- Những tên package `java.*` bị cấm trong module configuration mới.
- ClassLoader function có thể trả loader không phù hợp, và Java ném lỗi tương ứng.

Đây là vùng advanced; mapping phải nhất quán với **readability**, direct delegation, và lifecycle. Đừng “tắt kiểm tra split package” bằng cách tùy tiện trả về một existing loader.

## 5. Thí nghiệm runnable Java 17: split package hợp lệ khi nhiều loaders, lỗi với một loader

Thí nghiệm cho thấy chính xác sự khác nhau giữa **resolution** và **layer construction**. Ta biên dịch **hai named modules** không có `exports`, mỗi module đều chứa package `clash` nhưng class name khác.

### 5.1. Tạo cấu trúc dự án

~~~text
layer-split-demo/
├── src/
│   ├── alpha/
│   │   ├── module-info.java
│   │   └── clash/
│   │       └── Alpha.java
│   └── beta/
│       ├── module-info.java
│       └── clash/
│           └── Beta.java
└── LayerDemo.java
~~~

**Không có `requires alpha` hoặc `requires beta`** và không export `clash`. Do đó chỉ riêng việc cả hai module có package ấy **không gây lỗi export-readability trong resolution**.

### 5.2. Module alpha

File **src/alpha/module-info.java**:

~~~java
module alpha {
}
~~~

File **src/alpha/clash/Alpha.java**:

~~~java
package clash;

public final class Alpha {
}
~~~

### 5.3. Module beta

File **src/beta/module-info.java**:

~~~java
module beta {
}
~~~

File **src/beta/clash/Beta.java**:

~~~java
package clash;

public final class Beta {
}
~~~

Tên class Alpha và Beta khác nhau; ta đang thử **trùng package**, không phải trùng binary class name.

### 5.4. Chương trình host LayerDemo.java

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class LayerDemo {
    public static void main(String[] args) throws Exception {
        ModuleLayer boot = ModuleLayer.boot();
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

        Configuration cf = boot.configuration().resolve(
                finder, ModuleFinder.of(), Set.of("alpha", "beta"));

        System.out.println("alpha resolved: "
                + cf.findModule("alpha").isPresent());
        System.out.println("beta resolved: "
                + cf.findModule("beta").isPresent());

        ClassLoader parent = ClassLoader.getSystemClassLoader();
        try {
            boot.defineModulesWithOneLoader(cf, parent);
            System.out.println("one loader: success");
        } catch (LayerInstantiationException expected) {
            System.out.println(
                    "one loader: LayerInstantiationException");
        }

        ModuleLayer layer =
                boot.defineModulesWithManyLoaders(cf, parent);

        Class<?> alpha = layer.findLoader("alpha")
                .loadClass("clash.Alpha");
        Class<?> beta = layer.findLoader("beta")
                .loadClass("clash.Beta");

        System.out.println("separate loaders: "
                + (alpha.getClassLoader() != beta.getClassLoader()));
        System.out.println("alpha module: "
                + alpha.getModule().getName());
        System.out.println("beta module: "
                + beta.getModule().getName());
    }
}
~~~

Điểm kỹ thuật:

- `ModuleFinder.of(Path.of("mods"))` đọc các exploded modules được biên dịch dưới `mods`.
- `resolve` dùng configuration của boot layer làm parent và root set gồm `alpha`, `beta`.
- Vì không module nào export package trùng tới cùng consumer, **resolution thành công**.
- Khi `defineModulesWithOneLoader` cố map cả alpha/beta vào một loader, JPMS phát hiện **overlapping package `clash`** và ném `LayerInstantiationException`. Chương trình bắt lỗi theo **loại**, không phụ thuộc text của thông báo.
- `defineModulesWithManyLoaders` dùng loader riêng cho mỗi module, nên tạo layer được trong setup này.
- `loadClass` trực tiếp theo loader của module trả các Class mà không cần class từ package `clash` được export cho host unnamed module; ví dụ chỉ đọc metadata, **không gọi public method của class qua Java source cross-module**.
- `Class.getModule().getName()` cho thấy hai class thuộc đúng named modules.

### 5.5. Lệnh biên dịch và chạy

Đứng tại thư mục `layer-split-demo` với JDK 17 trở lên. **Biên dịch từng module riêng** để tránh áp đặt thêm kiểm tra compiler khi cùng lúc compile modules chứa package trùng:

~~~bash
javac --release 17 --module-source-path src -d mods -m alpha
javac --release 17 --module-source-path src -d mods -m beta
javac --release 17 -d host LayerDemo.java
java -cp host LayerDemo
~~~

Các lệnh dùng cho Windows PowerShell, Linux hoặc macOS khi đã tạo đúng file/thư mục theo cây trên; không có path list separator cần thay đổi.

**Stdout dự kiến chính xác:**

~~~text
alpha resolved: true
beta resolved: true
one loader: LayerInstantiationException
separate loaders: true
alpha module: alpha
beta module: beta
~~~

Nếu môi trường build đang tự động đưa alpha/beta lên classpath hoặc module path toàn cục, tránh đặt những artifacts trùng tên ở các vị trí ngoài `mods` để bài thực hành không thay đổi root graph ngoài ý định.

### 5.6. Tại sao không phải mẹo vượt mọi hạn chế JPMS?

Thí nghiệm cho thấy **hai module có package trùng nhưng không export vào cùng consumer** có thể tạo layer với nhiều class loaders. Nếu sửa descriptors để một module consumer đọc **hai module đều export `clash`**, resolution có thể thất bại **trước khi** chọn one-loader/many-loaders. Không thể dùng many-loaders để biến readability graph không hợp lệ thành hợp lệ.

## 6. Ví dụ conceptual về ResolutionException do export trùng

Giả sử có ba module descriptors:

~~~java
// alpha/module-info.java
module alpha {
    exports clash;
}
~~~

~~~java
// beta/module-info.java
module beta {
    exports clash;
}
~~~

~~~java
// consumer/module-info.java
module consumer {
    requires alpha;
    requires beta;
}
~~~

**Ba code blocks này minh họa module descriptors, không phải một ví dụ có thể compile/chạy độc lập ở cùng project.** Nếu consumer phải đọc cả hai modules cùng export package `clash`, tính hợp lệ của module graph vi phạm quy tắc `java.lang.module` về overlapping exported packages. Tùy việc kiểm tra được phát hiện ở javac, linker hay khi runtime resolve graph, có thể thấy lỗi compiler hoặc `ResolutionException`/launcher failure.

Người học không nên kỳ vọng một stdout cố định cho bộ mô tả *không hợp lệ* này. Hãy xác định lỗi thuộc **module resolution**, khác với `LayerInstantiationException` sau khi resolution thành công.

### Vì sao export khác với opens?

- `exports p` cho phép truy cập các public types trong package p theo module readability.
- `opens p` cho phép deep reflection vào package theo điều kiện module access, **không đồng nghĩa export p cho compile-time imports**.
- Một package có thể không export nhưng vẫn tồn tại trong module descriptor/class files; nó vẫn là package bị trùng khi cố gán hai modules vào cùng loader.
- `exports p to q` có hiệu lực có điều kiện cho consumer q; không nên đếm package conflict như một luật toàn cục không xét target.
- Các tùy chọn `--add-exports` hoặc `--add-opens` điều chỉnh truy cập nhưng **không phải biện pháp chung giải quyết overlapping packages trong một loader**.

## 7. Những nhóm exception và giai đoạn tương ứng

| Lỗi / exception | Giai đoạn thường gặp | Nguyên nhân điển hình |
| --- | --- | --- |
| `FindException` | Module discovery/resolution | Root module hoặc dependency không tìm được, module reference không phù hợp |
| `ResolutionException` | Module graph resolution | Readability graph không hợp lệ, xung đột exported package, module cycle |
| `LayerInstantiationException` | Tạo layer | Overlap package trong cùng loader, split delegation, loader/module ownership conflict |
| `IllegalArgumentException` | Gọi layer API sai | Parent configuration không tương ứng parent layer(s), đối số không hợp lệ |
| `ClassNotFoundException` | Nạp class | Loader của module không tìm được class được hỏi |
| `IllegalAccessException` / `InaccessibleObjectException` | Reflection/access | Chưa được export/open phù hợp hoặc bị hạn chế truy cập |
| `IllegalAccessError` | JVM linkage/access | Bytecode cố truy cập class/member không được phép |
| `LinkageError` | Linking/defining classes | Type/loader constraints hoặc định nghĩa bytecode không hợp lệ theo tình huống |
| `ServiceConfigurationError` | Service loading | Service/provider configuration thiếu hoặc subtype/type identity không khớp |

**Đừng bắt `Exception` chung rồi suy tất cả là split package.** Root cause có thể đơn giản là thiếu module, sai root set, sai parent layer hoặc package visibility. Trong test, bắt **đúng loại lỗi** để xác định giai đoạn.

`FindException` và `ResolutionException` thuộc `java.lang.module`, trong khi `LayerInstantiationException` thuộc `java.lang`. Chúng không thay thế nhau.

## 8. Tại sao parent layers làm tình hình phức tạp hơn?

Một `ModuleLayer` có thể được tạo từ configuration có **parent configuration(s)**; runtime layer phải có **parent layer(s) tương ứng, đúng thứ tự**.

Ví dụ pattern hợp lệ:

~~~java
ModuleLayer boot = ModuleLayer.boot();
Configuration cf = boot.configuration().resolve(
        finder, ModuleFinder.of(), roots);
ModuleLayer child =
        boot.defineModulesWithManyLoaders(
                cf, ClassLoader.getSystemClassLoader());
~~~

Đây là **đoạn minh họa** cần khai báo `finder`/`roots` và import các kiểu phù hợp.

Một lời gọi như `otherLayer.defineModulesWithManyLoaders(cf, parentLoader)` có thể ném `IllegalArgumentException` nếu **parent của cf** không tương ứng với `otherLayer.configuration()`. Điều này khác với xung đột package: ngay cả các modules không trùng package cũng có thể thất bại do nối sai parent.

### Module cùng tên ở hai layers

Một layer con có thể tồn tại cùng một tên module như ở layer khác trong các cấu hình nhất định, nhưng đây là **hai runtime Module objects**, không mặc nhiên là cùng identity. Cần phân biệt:

- `ModuleLayer.findModule(name)` có thể tìm trong layer hiện tại hoặc parent layers theo hợp đồng.
- `Class.getModule()` cho runtime module thực tế của class.
- `ClassLoader` định nghĩa type và cùng binary name có thể dẫn tới kiểu khác nhau.
- Mapping một module vào class loader đã có module cùng tên định nghĩa từ trước có thể bị từ chối.
- Thiết kế loader/layer cho plugin phải tính tới nơi đặt **shared API** để không định nghĩa lại interface/DTO/annotation/exception của host.

Thêm một layer không phải thao tác “thay đổi module graph của boot layer”; nó tạo vùng runtime mới với quan hệ parent.

## 9. Split delegation: khi một loader phải delegate cùng package tới nhiều loaders

Một lỗi khó hiểu khác của `defineModulesWithOneLoader` là **split delegation**. Ví dụ về ý tưởng:

~~~text
Parent layer:
    module baseA exports p.api to child modules; loader LA
    module baseB exports p.api to child modules; loader LB

Child layer:
    một class loader duy nhất C cho nhiều modules
    C cần tìm classes trong package p.api từ cả LA và LB
    -> mapping package -> target loader không đơn trị
~~~

Đây là **sơ đồ khái niệm**, không phải configuration hợp lệ/runnable được xác nhận. Nếu module readability/export gây xung đột sớm, lỗi đã xảy ra tại resolution. Khi một configuration hợp lệ nhưng loader tạo ra cần phân giải cùng package qua hơn một target loader, `defineModulesWithOneLoader` có thể từ chối với `LayerInstantiationException` do split delegation.

Do đó phải xem **toàn bộ module graph và loader mapping**, không chỉ scan xem class names trùng nhau trong hai JAR của layer con.

## 10. Cùng package trong hai loaders không trao quyền package-private

Trong JVM, **runtime package** liên quan tên package và defining loader; chỉ cùng chuỗi `package p;` là chưa đủ để các lớp có cùng runtime package.

Nếu Module A và Module B mỗi module có `p.Helper` hoặc `p.Worker`, được định nghĩa ở các loader khác nhau, mã ở A không thể mặc nhiên truy cập package-private members ở B chỉ nhờ cùng tên package.

JPMS còn có rules access trên module:

- Class trong module X muốn dùng public type của Y thường phải có quan hệ readability phù hợp và Y phải export package chứa type ấy tới X.
- Deep reflection thường cần `opens` phù hợp.
- Runtime package và module ownership không đồng nghĩa với package name trong source code.
- Hai classes ở hai loaders cùng binary name khác runtime identity, cast lẫn nhau có thể ném `ClassCastException`.

Vì vậy `defineModulesWithManyLoaders` giúp tránh **overlapping packages trong cùng một loader**, nhưng không biến chúng thành một package chung có quyền truy cập ngang nhau.

## 11. Mã runnable để quan sát lớp thuộc module nào

Trong `LayerDemo.java`, hai lệnh:

~~~java
Class<?> a = layer.findLoader("alpha")
        .loadClass("clash.Alpha");
Class<?> b = layer.findLoader("beta")
        .loadClass("clash.Beta");
~~~

chỉ tải Class metadata. In:

~~~java
System.out.println(a.getModule().getName());
System.out.println(b.getModule().getName());
~~~

cho biết module runtime. Nếu muốn tạo instance hoặc gọi một public method của class nằm trong non-exported package từ một host unnamed module bằng reflection, **module access checks có thể từ chối**. Để minh họa split packages không cần vượt qua quyền truy cập module: chỉ dùng `getName()`/`getModule()`/`getClassLoader()` như demo hoàn chỉnh.

Nếu thực sự muốn publish API xuyên module boundary, hãy bố trí package API một lần trong shared module và `exports` đúng nơi, thay vì giữ duplicate API packages trong nhiều modules.

## 12. Các sửa lỗi thường gặp theo nguyên nhân

### Tình huống A: hai JAR chia sẻ API package

Cấu trúc xấu:

~~~text
api-v1.jar: com.vendor.api.*
api-v2.jar: com.vendor.api.*
both on module path, both resolved/read
~~~

Hướng sửa: chọn một version API module chung; loại một bản duplicate, chuẩn hóa dependency tree. Nếu plugin cần bản private khác version, dùng package relocation/adapter/process boundary theo thiết kế, **không để cả hai module export cùng contract package tới consumer**.

### Tình huống B: một thư viện chứa cả API và implementation, muốn chia module

Một module có thể export `com.example.api`, module khác chứa `com.example.impl`. **Không đặt cả hai vào `com.example.api`** chỉ vì source code cũ từng dùng cùng package. Tách package names rõ ràng hoặc giữ trong một module nếu không cần module boundary.

### Tình huống C: one-loader layer thất bại, many-loaders thành công

Đây là bằng chứng **loader mapping** là nguyên nhân, không nhất thiết module graph sai. Xem các package overlap rồi quyết định:

- Nếu split package vô tình do dependency/version mismatch: sửa artifact/module packaging.
- Nếu cố ý có package name trùng nhưng không export, nhiều loaders có thể hợp lệ, song cần đánh giá rủi ro readability, reflection và type identity.
- Không tự động chuyển mọi plugin sang many-loaders nếu một shared API vẫn bị định nghĩa lại; shared contract phải do module/loader chung cung cấp.

### Tình huống D: FindException vì root module không có

Thêm đúng module vào module path hoặc sửa root name. Không chỉnh `opens` hoặc đổi class loader để chữa một module **chưa được finder tìm thấy**.

### Tình huống E: IllegalAccessError/InaccessibleObjectException

Xác định module có được **read** và package có được **export/open** đúng hướng không. Đừng xóa class files cùng tên ngẫu nhiên khi lỗi thực tế chỉ là quyền module.

### Tình huống F: Hot reload/module layers

Một layer mới với loaders mới có thể tạo runtime types riêng. Khi host muốn giữ một interface API chung, nó nên nằm ở parent layer/module được chia sẻ. Nếu mỗi plugin layer tự đưa API JAR vào, dù không có split package **trong từng layer**, host vẫn có thể gặp duplicated API Class identity giữa layers.

## 13. Kiểm tra artifact và module graph

Các công cụ JDK thường hữu ích:

~~~bash
jar --describe-module --file alpha.jar
jar --list --file alpha.jar
jdeps --module-path mods --check alpha
java --show-module-resolution --module-path mods -m alpha/your.Main
~~~

**Đây là các lệnh minh họa**, yêu cầu alpha.jar, mods và main class thực sự tồn tại. Không dùng dòng `-m alpha/your.Main` trong demo trước vì module alpha không khai báo `Main`. `jar --list` giúp xem package entries; `jar --describe-module` xem descriptor; `jdeps` hỗ trợ phân tích dependency theo artifact và Java version; `--show-module-resolution` hiển thị các modules được resolved bởi launcher.

Quan sát code runtime:

~~~java
System.out.println(someClass.getModule());
System.out.println(someClass.getClassLoader());
System.out.println(someClass.getModule().getLayer());
~~~

Đây là **đoạn minh họa**, cần có biến `someClass`. Nó trả lời module/loader/layer thực tế, thay vì đoán chỉ từ nơi đặt JAR.

Nếu dùng Java 17 trên module path, `java --validate-modules` có thể hỗ trợ kiểm tra các module observable và phát hiện một số vấn đề như tên module trùng hoặc xung đột; **không xem đây là thay thế cho việc resolve và chạy đúng root configuration của ứng dụng**.

## 14. Tại sao không giải quyết split package bằng child-first tùy tiện?

Child-first `ClassLoader` có thể nạp cùng binary name vào loader riêng và tạo hai runtime types, nhưng đó **không phải** biện pháp chung cho lỗi JPMS module layer:

1. Một `Configuration.resolve` thất bại vì module readability/export conflict không tự trở nên hợp lệ bằng cách override `loadClass`.
2. Một `defineModulesWithOneLoader` có package overlap vẫn không thể map hai modules chứa cùng package vào cùng một loader hợp lệ.
3. Nếu đổi sang loaders riêng, vấn đề type identity của API/shared classes có thể xuất hiện.
4. Một plugin chỉ nên cô lập **implementation/private dependencies**, còn shared API/annotation/exception/DTO nên thống nhất trong parent/common module nếu dùng chung ở boundary.
5. Module `java.base` và tên `java.*` có bảo vệ riêng; không nên cố định nghĩa lại core packages.
6. Namespace isolation không phải security sandbox: classloader không ngăn code plugin thực hiện I/O hoặc truy cập tài nguyên process theo quyền của nó.

Thiết kế đúng bắt đầu từ **module ownership cho từng package**, sau đó lựa chọn module graph và loader mapping; không bắt đầu bằng việc override delegation rồi hy vọng JPMS chấp nhận.

## 15. Checklist chẩn đoán lỗi cấu hình layer

1. **Xác định giai đoạn:** discovery, resolution, layer creation, class loading hay reflective access.
2. **In/ghi module roots:** có đang request đúng module names không?
3. **Liệt kê package của từng resolved module:** có package overlap không?
4. **Xem exports và qualified exports:** module nào đọc hai providers cho cùng package?
5. **Xem requires / requires transitive:** có cycle hoặc missing dependency không?
6. **Phân biệt one loader và many loaders:** one-loader cấm overlapping packages ngay tại layer construction; many-loaders không sửa invalid graph.
7. **Kiểm tra parent configurations:** có khớp parent layers tương ứng không?
8. **Kiểm tra loader ownership:** custom `defineModules` có map hai modules cùng package vào một loader hoặc reuse loader đã có module/class không?
9. **Kiểm tra runtime identity:** `Class.getModule()` và `getClassLoader()` của API/DTO/annotation/exception.
10. **Xem module path vs classpath:** modular JAR có bị đưa sai chỗ, root modules đã resolved chưa?
11. **Xem automatic modules:** JAR cũ có tên module suy ra và exports rộng gây xung đột không?
12. **Sửa từ nguồn:** loại duplicate package, tái cấu trúc module API/impl, sửa requires/exports/opens hoặc chọn loader mapping phù hợp — rồi chạy lại tests.
13. **Không ép compiler/runtime bỏ qua lỗi bằng flags ngẫu nhiên:** `--add-reads`/`--add-exports` không phải câu trả lời cho mọi overlap; có thể còn làm xung đột đọc/xuất rõ hơn.

## 16. Những ngộ nhận phổ biến

| Ngộ nhận | Điều chính xác |
| --- | --- |
| “Hai modules có cùng package luôn bị cấm ngay khi cùng nằm trên disk” | Còn tùy modules có được resolved, graph/exports và loader mapping |
| “Resolve thành công là tạo layer nào cũng được” | One-loader mapping còn có cấm overlapping packages và split delegation |
| “Đổi sang many-loaders là sửa được ResolutionException” | Không. Invalid graph phải được sửa ở bước resolution |
| “Split package phải trùng cả class name” | Không. Chỉ cần package name trùng, class names có thể khác |
| “Classpath đã cho phép split package nên module path cũng cho phép y hệt” | JPMS có thêm readability, exports và package ownership |
| “Dùng opens là hết xung đột exported package” | Opens và exports có ngữ nghĩa khác nhau, không chữa mọi overlap |
| “Cùng package source được truy cập package-private giữa modules” | Runtime package và module access không tự thống nhất khi khác loaders |
| “Named module có một loader riêng cho từng JAR” | Phụ thuộc layer mapping; one-loader có thể quản lý nhiều modules |
| “Exception nào từ module system cũng là FindException” | ResolutionException, LayerInstantiationException và access errors là các giai đoạn khác nhau |
| “Custom child-first loader luôn làm JPMS chấp nhận” | Module graph/layer constraints vẫn phải thỏa |
| “Hai layers cùng module name là một module” | Runtime Module objects và class identities vẫn phụ thuộc cấu hình/layers/loaders |
| “Module path chứa JAR là class tự dùng được” | Modules phải được selected/resolved và package accessible |

## 17. Bài tập tự kiểm tra

**1. Split package là gì?**  
Hai hay nhiều modules/artifacts có class cùng package name, không bắt buộc trùng class name.

**2. Hai module alpha/beta cùng có package p nhưng không export p. Configuration có nhất thiết fail không?**  
Không. Cần xét module graph; chúng có thể coexist trong configuration hợp lệ.

**3. Vì sao defineModulesWithOneLoader có thể fail dù Configuration.resolve đã thành công?**  
Vì one-loader yêu cầu không có overlapping packages trong các modules cùng được định nghĩa vào loader đó; còn có thể gặp split delegation.

**4. defineModulesWithManyLoaders có luôn giải quyết được split package conflict?**  
Không. Nó chỉ chọn loader mapping khác; resolution graph vẫn phải hợp lệ.

**5. Nếu consumer đọc hai modules cùng export package p tới nó thì sao?**  
Resolution thất bại do exported package conflict trong readability graph.

**6. Exports p và opens p có cùng ý nghĩa không?**  
Không. Exports cho khả năng truy cập public types theo module rules; opens phục vụ deep reflection theo điều kiện.

**7. Nếu một module root không được ModuleFinder tìm thấy thì thường gặp lỗi gì?**  
FindException ở bước discovery/resolution, không phải LayerInstantiationException.

**8. Hai class ở cùng tên package nhưng khác defining loaders có thể truy cập package-private của nhau chỉ nhờ tên giống nhau không?**  
Không, runtime package không tự trùng khi defining loaders khác.

**9. Nếu custom defineModules map hai modules có cùng package vào cùng loader thì sao?**  
Có thể bị LayerInstantiationException do package ownership conflict.

**10. Làm thế nào thấy lớp thật thuộc layer/module nào?**  
Dùng `clazz.getModule()`, `clazz.getClassLoader()`, và `clazz.getModule().getLayer()`.

**11. Khi layer mới định nghĩa lại interface shared API, host có chắc cast object plugin sang bản host được không?**  
Không. Cần một Class runtime dùng chung ở boundary.

**12. Vì sao kiểm tra mỗi tên JAR trên module path không đủ?**  
Cần biết root modules, configuration resolution, readability graph, package exports, loader mapping và parent layers.

## 18. Tài liệu chính thức

- Java SE 17, **ModuleLayer API** (overlapping packages, split delegation, one-loader/many-loaders và custom mapping): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- Java SE 17, **java.lang.module package specification** (module resolution và exported-package conflicts): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/package-summary.html
- Java SE 17, **Configuration API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html
- Java SE 17, **ModuleFinder API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html
- Java SE 17, **ModuleDescriptor API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.html
- Java SE 17, **Module API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- Java SE 17, **java launcher**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Java Language Specification 17, [§7.7 Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)
