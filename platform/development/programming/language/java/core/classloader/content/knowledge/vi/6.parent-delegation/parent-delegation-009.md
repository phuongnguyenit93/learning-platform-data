# Ủy quyền trong mô hình đồ thị và ngoại lệ với hệ module

Khi học `ClassLoader`, ta thường gặp sơ đồ **bootstrap ← platform ← application ← custom loader** và quy tắc *parent-first*: loader hỏi cha trước, rồi mới thử tự tìm class. Sơ đồ này hữu ích nhưng **không mô tả hết mọi đường ủy quyền trong Java 9+**, đặc biệt khi **Java Platform Module System (JPMS)** và các `ModuleLayer` mới được dùng.

Một loader vẫn có **một parent** theo `getParent()`, nhưng quá trình tìm class còn có thể có **cạnh ủy quyền trực tiếp sang loader khác**, kể cả loader ngang hàng (*peer*) hoặc loader không phải tổ tiên trong parent chain. Điều này tạo thành **đồ thị delegation**, thay vì chỉ một cây. JVM và module system dùng thông tin module/package/exports để xác định nơi nên tìm class; loader tích hợp còn có ngoại lệ phục vụ module được nâng cấp (*upgraded module*).

Bài học thuộc nhóm **Cơ chế ủy quyền** của Java core – classloader. Sau bài này, bạn cần phân biệt được **cây parent**, **đồ thị phụ thuộc module** và **đồ thị ủy quyền khi load class**; hiểu cơ chế đặc biệt của loader tích hợp; tự chạy được ví dụ hai module có loader ngang hàng; và biết các giới hạn về type identity, quyền truy cập, deadlock, module layers.

## 1. Mô hình thông thường: cây parent-first

Trong cơ chế mặc định của `ClassLoader.loadClass(String, boolean)`, quy trình tìm class gần như sau:

1. Kiểm tra tên class đã được loader này khởi đầu nạp chưa qua `findLoadedClass`.
2. Nếu chưa, thử gọi `parent.loadClass(...)`; nếu parent được biểu diễn bằng `null`, dùng cơ chế bootstrap.
3. Khi parent không tìm thấy, gọi `findClass(...)` của loader hiện tại.
4. Nếu tìm được class và tham số `resolve` yêu cầu, liên kết qua `resolveClass(...)`.
5. Nếu tất cả đều không tìm thấy, ném `ClassNotFoundException`.

Cây parent thường gặp trên JDK 17:

```text
[Bootstrap]                    (biểu diễn bằng null)
     ^
     | parent
[Platform]
     ^
     | parent
[Application/System]
     ^
     | parent
[PluginLoader]
```

**Cạnh parent** là một quan hệ được lưu/biểu diễn bằng `ClassLoader.getParent()`. Đó **không phải** thông tin class thực sự do ai định nghĩa.

Ví dụ, lời gọi `PluginLoader.loadClass("java.lang.String")` có thể ủy quyền lên bootstrap để nhận lại `java.lang.String`. `PluginLoader` là *requesting/initiating loader* nhưng **defining loader** của `String` vẫn được biểu diễn là `null`:

```java
ClassLoader child = ClassLoader.getSystemClassLoader();
Class<?> type = child.loadClass("java.lang.String");
System.out.println(type == String.class);
System.out.println(type.getClassLoader() == null);
```

Đây là **đoạn minh họa cần đặt trong method có `throws ClassNotFoundException`**; trên JDK Java SE thông thường, hai dòng in `true`. `loadClass` tự nó không bắt buộc chạy static initializer của class được tìm thấy.

**Giới hạn của cây parent:** một loader có thể biết thêm loader khác thông qua module, framework hoặc policy tùy biến. `getParent()` chỉ trả về **một cạnh parent**, không hứa liệt kê toàn bộ loader có thể được hỏi trong mọi lần load class.

## 2. Ba loại “đồ thị” cần tách riêng

Hãy hình dung ứng dụng có module `m.api` và `m.client`. `m.client` đọc `m.api`, còn mỗi module được gán cho một class loader khác nhau.

### 2.1 Đồ thị parent loader

```text
                  [System parent]
                   ^           ^
                   |           |
              [Loader A]   [Loader B]
                 m.api       m.client
```

Cả A và B đều có cùng parent. **A không phải parent của B** và ngược lại. Đây là đồ thị các cạnh parent (thường có dạng cây).

### 2.2 Đồ thị module readability

```text
[m.client] --requires/reads--> [m.api]
```

Cạnh này mô tả **module nào đọc module nào**. Source `module-info.java` có thể khai báo `requires m.api;`; sau khi module resolution, runtime có quan hệ `Module.canRead` tương ứng. Đọc được module chưa đủ để truy cập tùy ý mọi package: cần xét `exports` hoặc `opens` phù hợp.

### 2.3 Đồ thị class-loader delegation

```text
[Loader B] --tìm p.api.Service--> [Loader A]
                 |
                 +-- package p.api thuộc module m.api
                     và được xuất/hiển thị cho m.client
```

Trong cơ chế loader của `ModuleLayer.defineModulesWithManyLoaders`, loader B có thể **đi thẳng sang A** khi tên class nằm trong một package mà module đọc được và được export phù hợp. Cạnh này **không xuất hiện trong `getParent()` của B**, vì A là loader ngang hàng.

Như vậy:

| Quan hệ | Hỏi điều gì? | API hoặc dữ liệu quan sát |
| --- | --- | --- |
| Parent | Loader nào là parent của loader hiện tại? | `ClassLoader.getParent()` |
| Module readability | Module nào được module hiện tại đọc? | `module-info.java`, resolved configuration, `Module.canRead(...)` |
| Module export/open | Package nào được phép truy cập compile/runtime hoặc reflection? | `exports`, `opens`, `Module.isExported/isOpen` |
| Delegation thực tế | Khi nạp tên class này, loader sẽ hỏi ai? | Chính sách `loadClass` + ánh xạ package/module/loader |
| Defining loader | Class được trả về do ai định nghĩa? | `Class.getClassLoader()` |

**Không đồng nhất ba đồ thị.** Một cạnh `requires` là thông tin module, không tự động là một lệnh `getParent()`. Một cạnh delegation cho phép hỏi loader để tìm class, nhưng không tự cấp quyền Java access vượt qua ràng buộc module.

## 3. Vì sao JPMS cần cơ chế delegation theo đồ thị?

Trước Java 9, mô hình học tập classpath chủ yếu dựa trên thứ tự tra cứu trong parent chain và `findClass`. Từ Java 9, **named modules** cho phép gắn các package vào các module được resolve và gắn module vào các class loader. Với một loader quản lý nhiều module, việc tìm class có thể cần biết chính xác:

- Tên class có **package** nào?
- Package ấy thuộc module đã được resolve nào?
- Module đó gắn với **loader hiện tại hay một loader khác**?
- Package có được **export** cho module yêu cầu không?
- Nếu không có ánh xạ package/module thích hợp, có nên fallback sang parent/classpath không?

Một số loader do JPMS tạo dùng **direct delegation**: tìm module theo package và gửi yêu cầu trực tiếp tới loader phụ trách module, thay vì bắt buộc thử parent trước ở mọi trường hợp.

### Hai chiến lược tạo module layer

| API của `ModuleLayer` | Cách ánh xạ module → loader | Hệ quả chính |
| --- | --- | --- |
| `defineModulesWithOneLoader(cf, parentLoader)` | Các module trong layer mới dùng **một loader** | Module trong cùng layer chia sẻ loader; vẫn có thể direct-delegate tới loader của module ở parent layers |
| `defineModulesWithManyLoaders(cf, parentLoader)` | **Mỗi module** trong layer mới có loader riêng | Loader của module B có thể direct-delegate tới loader của module A ngay trong layer nếu có quan hệ phù hợp |
| `defineModules(cf, moduleNameToLoader)` | Caller cung cấp hàm ánh xạ module → loader | Dành cho chiến lược nâng cao; caller chịu trách nhiệm quản lý loader và điều kiện hợp lệ |

**Parent layer** và **parent class loader** là hai khái niệm khác nhau. `ModuleLayer.boot()` có thể là layer cha của layer mới; `ClassLoader.getSystemClassLoader()` có thể là parent của các loader mới. Điều này không khiến hai loader ngang hàng tự nhiên trở thành cha–con.

Khi chọn `defineModulesWithManyLoaders`, việc **mỗi module một loader** là một đặc điểm của API; không có nghĩa mọi named module ở JVM luôn có loader riêng. Boot layer có thể phân nhiều module cho cùng bootstrap/platform/application loader.

### Quy trình direct delegation theo package

```text
Loader B cần p.api.Service
        |
        v
Package = p.api
        |
        v
Tra module/package đã được giải quyết trong layer
        |
        +-- p.api thuộc m.api, được export tới m.client
        |            |
        |            v
        |       Đưa yêu cầu trực tiếp tới Loader A
        |            |
        |            v
        |       Trả cùng định nghĩa Class<?> của Loader A
        |
        +-- Không ánh xạ tới module phù hợp
                     |
                     v
            Thử parent loader theo contract của API
```

Sơ đồ mô tả cơ chế của loader JPMS được tạo bởi các phương thức trên. Đây **không phải** thuật toán bắt buộc cho mọi custom `ClassLoader`; custom loader có thể áp dụng policy khác và phải tự chịu trách nhiệm tương thích.

## 4. Ví dụ Java 17+ chạy được: hai loader ngang hàng, một cạnh delegation trực tiếp

Ta sẽ tạo hai named modules:

- **`m.alpha`** chứa `p.alpha.Greeter` và export package `p.alpha`.
- **`m.beta`** khai báo `requires m.alpha;`, chứa `p.beta.UseAlpha` sử dụng `Greeter`.
- Một chương trình `Launcher` trên classpath sẽ resolve hai module rồi dùng `defineModulesWithManyLoaders` để tạo mỗi module một loader. Hai loader có cùng parent là system loader.

### 4.1 Cấu trúc thư mục

```text
project/
├── src/
│   ├── m.alpha/
│   │   ├── module-info.java
│   │   └── p/alpha/Greeter.java
│   └── m.beta/
│       ├── module-info.java
│       └── p/beta/UseAlpha.java
└── Launcher.java
```

Tạo đủ các thư mục trên; chạy những lệnh `javac` phía dưới từ thư mục `project/`.

### 4.2 Nội dung module `m.alpha`

File `src/m.alpha/module-info.java`:

```java
module m.alpha {
    exports p.alpha;
}
```

File `src/m.alpha/p/alpha/Greeter.java`:

```java
package p.alpha;

public class Greeter {
    public static String message() {
        return "Hello from alpha";
    }
}
```

`exports p.alpha;` cho phép module khác đọc `m.alpha` và truy cập public API của package này theo điều kiện module system.

### 4.3 Nội dung module `m.beta`

File `src/m.beta/module-info.java`:

```java
module m.beta {
    requires m.alpha;
    exports p.beta;
}
```

File `src/m.beta/p/beta/UseAlpha.java`:

```java
package p.beta;

public class UseAlpha {
    public static String call() {
        return p.alpha.Greeter.message();
    }
}
```

`requires m.alpha;` làm module `m.beta` đọc `m.alpha`. `exports p.beta;` cho phép `Launcher` gọi public method qua reflection hợp lệ từ unnamed module, sau khi tìm được class.

### 4.4 Chương trình tạo module layer mới

File `Launcher.java`:

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class Launcher {
    public static void main(String[] args) throws Exception {
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

        Configuration cf = ModuleLayer.boot()
                .configuration()
                .resolve(finder, ModuleFinder.of(), Set.of("m.beta"));

        ModuleLayer layer = ModuleLayer.boot()
                .defineModulesWithManyLoaders(
                        cf, ClassLoader.getSystemClassLoader());

        ClassLoader a = layer.findLoader("m.alpha");
        ClassLoader b = layer.findLoader("m.beta");

        System.out.println("different loaders: " + (a != b));
        System.out.println("same parent: "
                + (a.getParent() == b.getParent()));
        System.out.println("peer is not parent: "
                + (b.getParent() != a));

        Class<?> viaB = b.loadClass("p.alpha.Greeter");
        System.out.println("B can load A: "
                + (viaB == a.loadClass("p.alpha.Greeter")));

        Class<?> use = b.loadClass("p.beta.UseAlpha");
        System.out.println("call: "
                + use.getMethod("call").invoke(null));

        try {
            a.loadClass("p.beta.UseAlpha");
            System.out.println("reverse: found");
        } catch (ClassNotFoundException expected) {
            System.out.println("reverse: not found");
        }
    }
}
```

Các điểm cần lưu ý:

- `ModuleFinder.of(Path.of("mods"))` lấy module đã biên dịch từ thư mục `mods`.
- `resolve(... Set.of("m.beta"))` cũng resolve `m.alpha` do `m.beta` yêu cầu module ấy.
- `defineModulesWithManyLoaders` tạo loader riêng cho mỗi module và đặt cùng parent system loader.
- `layer.findLoader(name)` lấy loader được gán cho module trong layer.
- `b.loadClass("p.alpha.Greeter")` tìm class do loader A định nghĩa dù A **không phải** parent của B.
- `a.loadClass("p.beta.UseAlpha")` không có cạnh ngược hợp lệ trong ví dụ. Parent system loader cũng không chứa hai module chỉ mới đưa vào layer này.

### 4.5 Biên dịch và chạy

Yêu cầu **JDK 17 trở lên**. Từ `project/`:

```bash
javac --release 17 -d mods --module-source-path src -m m.alpha,m.beta
javac --release 17 Launcher.java
java -cp . Launcher
```

Bản ví dụ này đã được đối chiếu bằng `javac --release 17` và chạy trên JDK 21 tương thích Java 17. Stdout chính xác:

```text
different loaders: true
same parent: true
peer is not parent: true
B can load A: true
call: Hello from alpha
reverse: not found
```

**Vì sao đây là bằng chứng của đồ thị delegation?**

`same parent: true` chứng minh A/B cùng parent. `peer is not parent: true` xác nhận A không phải parent của B. Nhưng `B can load A: true` vẫn xuất hiện: loader B tìm `p.alpha.Greeter` bằng **direct delegation** dựa trên package/module và export, nhận lại đúng `Class<?>` do A định nghĩa.

Cạnh này có hướng: `m.beta` đọc `m.alpha` và module API được export cho B; ngược lại `m.alpha` không có quan hệ đọc/export tương ứng để B trở thành nguồn class của A. Vì thế `reverse: not found` là kết quả hợp lý trong ví dụ.

**Chú ý khi tái hiện:** đừng đồng thời đưa `mods` vào `--module-path` của `java` và tự resolve cùng chúng trong `Launcher` nếu mục tiêu là quan sát các module do layer mới định nghĩa. Lệnh chạy chỉ đặt `Launcher` trên classpath, để tránh lẫn boot layer với custom layer.

## 5. Điểm đặc biệt của loader tích hợp: platform có thể delegate sang application

Java SE 17 công bố rõ một ngoại lệ quan trọng đối với cây parent:

> Khi module được nâng cấp hoặc ghi đè theo cơ chế module system, platform class loader có thể cần delegate sang loader khác, ví dụ application class loader, mặc dù application **không phải tổ tiên** của platform.

Điều này liên quan trường hợp **upgraded module** được xác định cho platform loader nhưng đọc các module được định nghĩa cho loader khác. Để thỏa mãn các tham chiếu package/module đó, platform loader có thể hỏi loader phụ trách module đích theo cách **trực tiếp**, không chỉ đi dọc parent chain.

Sơ đồ ý tưởng:

```text
        [Bootstrap]
             ^
             | parent
        [Platform] -----------------+
             ^                      |
             | parent               | có thể direct-delegate
        [Application] <-------------+
        
      Parent edge: Application → Platform → Bootstrap
      Extra lookup edge: Platform → Application (khi module yêu cầu)
```

Trong sơ đồ, mũi tên parent hướng lên và cạnh ngoại lệ được ghi rõ. Đường platform → application **không phải parent mới**, không biến hệ loader mặc định thành vòng parent, và cũng **không có nghĩa** platform luôn nhìn thấy mọi class trên application classpath.

**Điểm cần nhớ:**

1. `ClassLoader.getPlatformClassLoader().getParent()` không thay đổi chỉ vì có một cạnh delegation sang app.
2. Cạnh này xuất hiện **theo nhu cầu module/package cụ thể**, nổi bật trong trường hợp upgraded modules; nó không phải policy “platform fallback qua mọi class của application”.
3. Hành vi Java SE 17 ở mức API cho phép/giải thích cơ chế này. Chi tiết ánh xạ và kiểm tra package của runtime cụ thể có thể thay đổi theo phiên bản/triển khai.
4. Parent-first vẫn là mô hình mặc định được `ClassLoader` khuyến nghị cho loader tùy biến thông thường, nhưng **loader built-in phục vụ JPMS** có thể hoạt động theo quy tắc riêng.

Không nên dựng giả một kết quả “platform luôn load được class `com.myapp.X`” trên JDK bình thường. Để minh họa ngoại lệ thật sự cần cấu hình module nâng cấp/module read phù hợp. Ví dụ `ModuleLayer` ở mục 4 cung cấp bằng chứng **runnable** về cùng nguyên lý direct delegation giữa các loader ngang hàng mà không phụ thuộc cấu hình nâng cấp JDK đặc thù.

## 6. Parent, readability, exports và opens phối hợp ra sao?

Một câu hỏi hay gặp: **Nếu B load được `p.alpha.Greeter` từ A thì code trong B chắc chắn gọi được mọi thành viên của Greeter không?**

**Không.** Đồ thị delegation chỉ giải thích cách tìm class. Quy tắc module còn chi phối **quyền truy cập**.

| Khái niệm | Chức năng | Ví dụ |
| --- | --- | --- |
| `requires m.alpha;` | Module B có quan hệ đọc A | `m.beta` dùng API của `m.alpha` |
| `requires transitive m.alpha;` | Quan hệ đọc được truyền tiếp cho module đọc module khai báo theo quy tắc JPMS | Một API module re-export phụ thuộc |
| `exports p.alpha;` | Cho phép module khác truy cập public/protected API đủ điều kiện của package | `UseAlpha` gọi `Greeter.message()` |
| `exports p.alpha to m.beta;` | Chỉ export package cho module được nêu | Giới hạn compile/runtime access theo module |
| `opens p.alpha;` | Cho phép deep reflection tới package trong phạm vi được mở | Framework phản chiếu private members khi cần |
| `opens p.alpha to m.beta;` | Chỉ mở deep reflection cho module được chỉ định | Giới hạn quyền reflection |
| `Module.canRead(...)` | Xem quan hệ đọc runtime giữa module | Debug readability |
| `Module.isExported(...)` / `isOpen(...)` | Xem quyền export/open runtime | Debug access/encapsulation |

`requires` không có nghĩa package sẽ tự động được export. `exports` không có nghĩa mọi module tự động đọc module nguồn. `opens` chủ yếu dành cho reflection sâu, không biến private method thành một public method có thể gọi trực tiếp từ source Java.

Một lỗi `IllegalAccessError` hoặc `InaccessibleObjectException` có thể xuất hiện **sau khi class đã được tìm thấy**. Đừng sửa sai bằng cách đổi parent loader khi nguyên nhân nằm ở `exports`/`opens` hoặc quyền truy cập Java.

### Liên hệ từ graph module tới class-loader graph

Trong loader của module layer, **gói được export và quan hệ module** được dùng để xác định các tuyến direct-delegation. Tuy nhiên **không phải mọi cạnh `requires` sẽ trở thành một cạnh parent**, và **không phải mọi loại lookup class đều lặp lại thuật toán đọc module của Java compiler**.

Đặc biệt, khi một API loader nhận trực tiếp một tên binary class từ bên ngoài, cơ chế ánh xạ package/module của loader có thể là đầu mối để tìm class; kiểm tra có được **dùng** class đó từ code của một module cụ thể là câu hỏi khác với việc lấy một `Class<?>` qua API.

## 7. `ModuleLayer` có thể tạo ra các kiến trúc nào?

### 7.1 Một loader chứa nhiều module

`defineModulesWithOneLoader` gán mọi module trong layer mới cho **một loader**. Điều này giúp các module chia sẻ một namespace loader, nhưng **không gộp các module thành một module duy nhất**. Các quan hệ `requires`, `exports` và `opens` vẫn tồn tại.

Nếu hai module trong cùng layer khai báo **trùng package** khi dùng một loader, việc tạo layer có thể thất bại với `LayerInstantiationException`. Quy tắc này giúp tránh tình huống một package nằm trong nhiều named module cùng loader và không có owner rõ ràng.

### 7.2 Mỗi module một loader

`defineModulesWithManyLoaders` tạo một loader cho mỗi module, với parentLoader được chỉ định. Những loader ấy có thể là **siblings** nhưng sử dụng direct delegation theo package export để phục vụ module readability. Bài chạy ở mục 4 minh họa trường hợp này.

### 7.3 Hàm ánh xạ module → custom loader

`defineModules` cho phép truyền hàm xác định loader tương ứng. Đây là phạm vi nâng cao cho container/plugin engine cần điều khiển namespace. Cần bảo đảm mỗi module/package có loader hợp lệ, không xung đột package và không sinh tuyến delegation không được kiểm soát.

### 7.4 Nhiều parent layers

API tĩnh của `ModuleLayer` nhận danh sách parent layers và `Configuration` có quan hệ parent tương ứng. Một module ở layer con có thể đọc module ở một trong các parent layers phù hợp. **Quan hệ layer parent** là quan hệ resolution giữa các layer; không trùng với kết quả `ClassLoader.getParent()` trên từng loader.

`ModuleLayer.findLoader(name)` hỗ trợ lấy loader gắn với module trong layer. `ModuleLayer.findModule(name)` có thể tìm cả parent layers. Một loader không “trở thành con của mọi loader trong mọi parent layer”; direct-delegation đến đúng module phụ thuộc routing ở runtime.

## 8. Ranh giới của đồ thị delegation

### 8.1 Đường tìm class có hướng

Nếu B hỏi A, không suy ra A hỏi được B. Tính bất đối xứng giúp giới hạn phụ thuộc. Ví dụ `m.beta requires m.alpha` không tạo cạnh tự động ngược lại.

### 8.2 Tên class chưa bảo đảm danh tính kiểu

JVM xác định class/interface bằng cặp **binary name + defining loader**. Nếu A và B mỗi bên định nghĩa `p.api.Contract` của riêng mình, đó là hai kiểu khác nhau dù tên và bytecode giống. Mục tiêu của direct delegation đúng cách là cho bên sử dụng **nhận cùng Class object** do loader sở hữu module định nghĩa.

Nếu một object của plugin không cast được sang interface của host, cần kiểm tra:

```java
System.out.println(object.getClass().getName());
System.out.println(object.getClass().getClassLoader());
System.out.println(object.getClass().getModule());
```

Đây là **đoạn minh họa trong method**, với `object` là instance đang điều tra. In thêm class loader của interface dự kiến và so identity của `Class<?>`, không chỉ so tên.

### 8.3 Không phải đồ thị nào cũng an toàn

Custom loader có thể override `loadClass` và tạo cạnh sang loader bất kỳ. Nếu thiết kế A → B và B → A, thiếu bộ nhớ đệm/kiểm tra và thứ tự khóa an toàn có thể gây vòng truy vấn hoặc deadlock. Chỉ thêm cạnh khi có ràng buộc rõ ràng về package, owner và chặn vòng.

### 8.4 Không thay thế security boundary

JPMS giới hạn readability và package accessibility; class loader isolation giới hạn kiểu nào được định nghĩa/nhìn thấy. Cả hai **không phải môi trường sandbox hoàn chỉnh** để thực thi bytecode không đáng tin. Đừng dựa vào “parent = null” hoặc “plugin có loader riêng” như giải pháp bảo mật duy nhất.

### 8.5 Resource lookup có luật khác

`getResource` và `getResources` cũng có cơ chế delegation và chịu quy tắc đóng gói của named modules. Một số API của `ModuleLayer` quy định tìm resource trong các module của layer trước parent; resource nằm trong package không được `opens` công khai có thể bị ẩn. Vì thế “class B tìm được từ loader A” không suy ra mọi resource `p/alpha/config.properties` đều tra được qua B.

## 9. Nhiều luồng: lý do tài liệu ClassLoader nhắc parallel capable

JavaDoc `ClassLoader` cảnh báo rằng khi delegation **không phân cấp nghiêm ngặt**, class loader cần hỗ trợ **parallel-capable loading** để tránh deadlock do giữ lock trên loader trong khi yêu cầu loader khác.

Trong cơ chế cổ điển, `loadClass` có thể được đồng bộ hóa theo một khóa trên loader. Nếu:

```text
Thread 1: giữ lock Loader A → chờ Loader B
Thread 2: giữ lock Loader B → chờ Loader A
```

thì hai thread có thể đứng chờ nhau. Khi loader **parallel capable**, việc đồng bộ có thể dựa trên `getClassLoadingLock(name)` cho mỗi tên class, giúp giảm việc khóa cả loader trong một số tình huống. Tuy nhiên parallel capable **không chứng minh mọi đồ thị có vòng đều an toàn**: deadlock vẫn có thể xảy ra nếu thiết kế routing/khóa sai.

Một custom subclass dự định tham gia graph delegation phải hiểu `registerAsParallelCapable`. Đăng ký cần gọi từ quá trình khởi tạo class của subclass, và điều kiện về các superclass trong chuỗi class loader cũng phải phù hợp. Không gọi hàm ấy bừa trong mỗi `loadClass` hay coi nó như công tắc chữa mọi deadlock.

Đây là lý do loader của module system có cơ chế routing và đồng bộ chuyên biệt. Ở tầng ứng dụng, ưu tiên API `ModuleLayer` được chuẩn hóa thay vì tự tạo nhiều override `loadClass` có vòng tham chiếu giữa chúng.

## 10. Một cách kiểm tra graph qua dữ liệu runtime

Khi sự cố liên quan tới class loader, có thể kiểm tra ba lớp thông tin:

**A. Parent chain**

```java
static void printParents(ClassLoader loader) {
    while (loader != null) {
        System.out.println(loader);
        loader = loader.getParent();
    }
    System.out.println("bootstrap (null)");
}
```

Đây là **method minh họa**, thêm vào một class trước khi gọi. Chuỗi parent chỉ trả lời “cha của ai”, **không biểu diễn cạnh direct delegation** như B → A trong ví dụ.

**B. Module và defining loader của class thực tế**

```java
static void inspect(Class<?> type) {
    Module module = type.getModule();
    System.out.println("class=" + type.getName());
    System.out.println("module=" + module.getName());
    System.out.println("loader=" + type.getClassLoader());
}
```

`module.getName()` có thể là `null` với unnamed module; `getClassLoader()` là `null` với class bootstrap. Cần in loader cả **ở source của request và ở class kết quả** để phân biệt initiating và defining.

**C. Graph module đã resolve**

```java
Module client = layer.findModule("m.beta").orElseThrow();
Module api = layer.findModule("m.alpha").orElseThrow();

System.out.println("reads: " + client.canRead(api));
System.out.println("exports: " + api.isExported("p.alpha", client));
System.out.println("different loaders: "
        + (layer.findLoader("m.beta") != layer.findLoader("m.alpha")));
```

Đây là **đoạn minh họa thêm vào `Launcher.main` của mục 4**, sau khi biến `layer` đã được tạo. Trong ví dụ, ba dòng in `true`. `Module.canRead` và `isExported` chứng minh module-level visibility; kết quả hai loader khác nhau chứng minh class không bắt buộc nằm chung loader. Cạnh direct delegation được quan sát qua `b.loadClass(...)` rồi so `Class<?>` identity.

**D. Class loading logs**

Trên HotSpot hỗ trợ unified logging, thử:

```bash
java -Xlog:class+load=info -cp . Launcher
```

Log có thể cho biết class được nạp từ nguồn nào nhưng thường khá dài; định dạng không cố định giữa các JVM. Không sử dụng log ấy làm bằng chứng duy nhất cho toàn bộ graph. Nếu cần, tạm thêm log trong custom `loadClass`/`findClass` để quan sát tuyến request, đồng thời tránh logging gây recursion.

## 11. Lỗi và cách chẩn đoán

| Triệu chứng | Câu hỏi cần kiểm tra |
| --- | --- |
| `ClassNotFoundException` khi B tìm class A | Package có trong module nào? Module có được resolve vào layer? Có export/đường delegation phù hợp? |
| `NoClassDefFoundError` lúc liên kết/thực thi | Dependency runtime bị thiếu, lỗi linking khác, hoặc initialization trước đó thất bại? Xem `cause` |
| `IllegalAccessError` | Class được tìm thấy nhưng quyền Java access/module exports có cho phép gọi? |
| `InaccessibleObjectException` khi deep reflection | Package có `opens` phù hợp cho caller không? |
| `ClassCastException` giữa hai tên class giống nhau | Có hai defining loader định nghĩa trùng tên? Có cùng API class được chia sẻ đúng nơi không? |
| `LayerInstantiationException` khi tạo module layer | Có package trùng/split delegation/module mapping không hợp lệ không? |
| Lúc chạy bị treo khi hai loader nạp chéo | Có vòng delegation/khóa và custom loader không parallel capable không? |
| `ServiceLoader` không thấy provider | Module `uses`/`provides`, layer, loader, TCCL, package exports/visibility đã cấu hình đúng chưa? |

**Quy trình thực tế:**

1. Thu thập tên class cần load, caller và thao tác (bytecode, reflection, `Class.forName`, service discovery).
2. Xác định **định nghĩa class thực tế** bằng `getClassLoader()` và `getModule()`.
3. Lấy **parent chain** riêng, không nhầm nó với toàn bộ delegation.
4. Với named modules, kiểm tra module trong đúng `ModuleLayer`, `requires`/readability và `exports`/`opens`.
5. Nếu có nhiều loader ngang hàng, kiểm tra **package → module → loader mapping** và chiều cạnh direct-delegation.
6. Khi có trùng tên, so `Class<?>` identity và defining loader; khi có treo, kiểm tra các lock và vòng nạp chéo.
7. Khắc phục dependency/module mapping, kiến trúc API chia sẻ hoặc chính sách loader rồi chạy lại cùng đường gọi lỗi. Không dùng `--add-opens`/`--add-exports` như một bản vá tùy tiện khi nguyên nhân thật là class identity.

## 12. Các nhận định dễ sai

| Nhận định | Đính chính |
| --- | --- |
| “Mỗi loader chỉ có thể hỏi parent.” | Đúng với thuật toán parent-first mặc định; loader JPMS và custom loader có thể direct-delegate sang loader khác. |
| “Hai loader có cùng parent thì không nhìn thấy class của nhau.” | Module layer có thể tạo cạnh package/module từ B sang loader ngang hàng A. |
| “`getParent()` sẽ liệt kê mọi cạnh của graph.” | Nó chỉ cho biết parent; cạnh graph cần kiểm tra policy loader và module mapping. |
| “`requires` làm loader A thành parent của B.” | `requires` tạo module readability, không biến đổi cấu trúc parent. |
| “B load được class là B đã định nghĩa class đó.” | B có thể trả `Class<?>` do A hoặc bootstrap định nghĩa. |
| “Platform luôn delegate sang application.” | Chỉ có thể xuất hiện khi điều kiện module nâng cấp/đọc module phù hợp; không phải đường fallback vô điều kiện. |
| “Named module nào cũng có loader riêng.” | Boot layer có thể gán nhiều module cho cùng built-in loader; layer mới được tạo theo API one/many/custom. |
| “Có readability tức là reflection private được.” | Còn cần exports/opens, quyền truy cập Java và ràng buộc reflection. |
| “Graph loader an toàn nếu chỉ override `loadClass`.” | Có nguy cơ vòng delegation và deadlock; cần thiết kế khóa và parallel-capable phù hợp. |
| “Class loader isolation tự bảo vệ khỏi mọi bytecode độc hại.” | Loader/module là cơ chế namespace và access-control, không đủ làm sandbox toàn diện. |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Loader A và B đều có parent là system loader. Trong ví dụ, tại sao B vẫn load được `p.alpha.Greeter` do A định nghĩa?

**Đáp án:** `defineModulesWithManyLoaders` tạo direct delegation dựa vào package thuộc module `m.alpha` được export phù hợp và được module `m.beta` đọc. A là loader ngang hàng của B, không cần là parent.

**Câu 2.** `b.getParent() != a` nhưng `b.loadClass("p.alpha.Greeter") == a.loadClass("p.alpha.Greeter")` có mâu thuẫn không?

**Đáp án:** Không. `getParent()` chỉ trả quan hệ cha; `loadClass` có thể delegate trực tiếp sang loader khác theo module mapping và nhận cùng `Class<?>`.

**Câu 3.** Tại sao việc `m.beta requires m.alpha` không đồng nghĩa mọi private method trong `m.alpha` đều gọi được từ `m.beta`?

**Đáp án:** Module readability không tự xóa quyền Java access. Public API còn cần package export phù hợp; deep reflection có thể cần `opens` và các điều kiện khác.

**Câu 4.** Vì sao platform loader đôi khi có thể delegate sang application loader dù application là con trong parent chain?

**Đáp án:** Trong một số cấu hình upgraded modules, platform module có thể đọc module được loader khác, chẳng hạn app loader, định nghĩa. Direct delegation theo module/package giải quyết tham chiếu đó mà không đổi `getParent()`.

**Câu 5.** Chạy `defineModulesWithOneLoader` thay vì `defineModulesWithManyLoaders` có xóa các quan hệ `requires` không?

**Đáp án:** Không. Chỉ đổi cách ánh xạ module vào class loader; module readability và exports/opens vẫn có hiệu lực.

**Câu 6.** Nếu class có cùng tên được định nghĩa độc lập ở A và B, JVM có xem là cùng kiểu không?

**Đáp án:** Không. Danh tính kiểu cần cả binary name và defining loader. Chia sẻ một class qua delegation trả về cùng `Class<?>` là cách tránh lỗi này khi thiết kế API giữa module/plugin.

**Câu 7.** Vì sao tạo hai custom loader delegate chéo không cẩn thận có thể deadlock?

**Đáp án:** Mỗi thread có thể giữ lock ở một loader rồi chờ loader còn lại. Với graph không phân cấp nghiêm ngặt cần thiết kế routing và concurrency, bao gồm parallel-capable loader khi phù hợp.

**Câu 8.** Để biết “class do ai định nghĩa”, dùng `getParent()` hay `Class.getClassLoader()`?

**Đáp án:** Dùng `Class.getClassLoader()` trên class đã nhận. `getParent()` chỉ cho biết parent của một loader; nó không xác định defining loader cho từng kết quả load class.

## Kết luận học tập

Quan hệ **parent** là một nhánh cấu trúc của class loader; quan hệ **module reads/exports** quyết định phụ thuộc và khả năng truy cập giữa named modules; quan hệ **delegation khi load class** có thể là một **đồ thị có hướng** với cạnh sang loader ngang hàng hoặc loader không phải tổ tiên. Vì vậy, để giải thích một class được tìm thấy từ đâu, hãy xem **package, module, module layer, loader được gán, đường ủy quyền và defining loader** thay vì chỉ lần theo `getParent()`.

Tài liệu chuẩn nên đối chiếu:

- [ClassLoader – Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html) (delegation, parallel-capable và ngoại lệ platform/application với upgraded modules).
- [ModuleLayer – Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html) (`defineModulesWithOneLoader`, `defineModulesWithManyLoaders`, ánh xạ package/module và direct delegation).
- [Module – Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html) (readability, exports, opens).
- [JVM Specification 17 – Loading, Linking and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html) (defining loader, initiating loader, danh tính kiểu và loading constraints).
