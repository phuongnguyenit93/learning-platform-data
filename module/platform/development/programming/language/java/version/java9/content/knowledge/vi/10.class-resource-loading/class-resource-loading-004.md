# Định danh lớp trong môi trường nhiều loader và mô-đun

Trong Java, tên đầy đủ của một class chưa đủ để xác định một kiểu tại runtime. JVM còn xét class loader đã định nghĩa class đó. Vì vậy, hai class có cùng binary name nhưng được định nghĩa bởi hai class loader khác nhau là hai kiểu khác nhau: chúng không thể thay thế cho nhau trong phép gán, ép kiểu hoặc kiểm tra `instanceof`.

JPMS bổ sung một lớp tổ chức khác: module và ModuleLayer. Cùng một module name có thể xuất hiện trong hai ModuleLayer độc lập. Khi module được định nghĩa trong từng layer với class loader riêng, class bên trong cũng có identity riêng. Hiểu rõ mối quan hệ giữa binary name, defining class loader, Module và ModuleLayer giúp tránh lỗi `ClassCastException`, lỗi liên kết và việc nạp nhầm phiên bản API trong ứng dụng plugin.

Bài học này tập trung vào cơ chế class identity và module identity hiện hành, với ví dụ chạy được bằng Java 17 trở lên.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao class identity phụ thuộc vào binary name và defining class loader.
- Phân biệt class name, class loader, runtime package, Module và ModuleLayer.
- Mô tả cách parent delegation ảnh hưởng đến việc tìm và định nghĩa class.
- Hiểu vì sao cùng một class name có thể đại diện cho hai kiểu không tương thích.
- Nhận diện lỗi ép kiểu, `ClassCastException`, `ClassNotFoundException` và `LinkageError` trong môi trường nhiều loader.
- Dùng các API như `Class.getClassLoader()`, `Class.getModule()`, `Module.getLayer()` và `ModuleLayer.findLoader()` để chẩn đoán.
- Tạo hai ModuleLayer độc lập chứa cùng một module name và kiểm chứng class identity.
- Thiết kế ranh giới API để các plugin chia sẻ đúng kiểu dữ liệu và interface.

## 1. Class identity trong JVM

### 1.1. Binary name chưa đủ để xác định một class

Một class Java có binary name, ví dụ:

~~~text
com.acme.model.Token
~~~

Binary name là tên đầy đủ của kiểu theo quy tắc Java. Tuy nhiên, khi JVM nạp class, identity của kiểu còn gắn với class loader đã định nghĩa nó.

Có thể ghi nhớ quy tắc:

~~~text
Class identity = binary name + defining class loader
~~~

Hai class chỉ có cùng tên chưa chắc là cùng một kiểu. Nếu loader A định nghĩa `com.acme.model.Token` và loader B cũng định nghĩa class có binary name đó, JVM xem chúng là hai class khác nhau.

Điều này có hệ quả trực tiếp:

- `ClassA == ClassB` trả về `false`.
- `ClassA.isAssignableFrom(ClassB)` trả về `false` nếu không có quan hệ kế thừa tương thích.
- Một object của ClassB không thể ép kiểu sang ClassA.
- `instanceof ClassA` không nhận object được tạo từ ClassB.
- Hai class có thể có cùng tên, field và method nhưng vẫn không tương thích.

### 1.2. Ai là defining class loader?

Defining class loader là loader thực sự tạo định nghĩa class trong JVM, thường thông qua `defineClass(...)`. Một loader có thể yêu cầu parent hoặc loader khác tìm class. Loader tìm thấy và trả về class không nhất thiết là defining loader của class đó.

Ví dụ, loader con gọi `loadClass("java.lang.String")`. Parent delegation đưa yêu cầu lên bootstrap loader, và bootstrap loader định nghĩa String. Loader con chỉ nhận lại Class object đã có.

Vì thế, cần phân biệt:

- **Initiating loader:** loader khởi đầu yêu cầu nạp class.
- **Defining loader:** loader thực sự định nghĩa class.

Khi kiểm tra identity, API `Class.getClassLoader()` trả về defining loader của class. Với class do bootstrap loader định nghĩa, giá trị trả về là `null`.

### 1.3. Class object là đại diện runtime của kiểu

Mỗi kiểu đã được nạp có một đối tượng `java.lang.Class` đại diện. Có thể so sánh hai kiểu bằng:

~~~java
Class<?> first = objectA.getClass();
Class<?> second = objectB.getClass();

System.out.println(first == second);
System.out.println(first.getName());
System.out.println(first.getClassLoader());
~~~

Không nên chỉ so sánh `getName()` để quyết định hai object có cùng kiểu. Hãy so sánh Class object hoặc dùng các API kiểm tra assignability phù hợp.

## 2. ClassLoader và không gian tên kiểu

### 2.1. Mỗi loader tạo một namespace riêng

Một class loader quản lý việc tìm, nạp và định nghĩa class. Khi hai loader độc lập định nghĩa class cùng binary name, mỗi loader tạo một kiểu riêng trong namespace của nó.

~~~text
Loader A
└── com.acme.model.Token  -> Class A

Loader B
└── com.acme.model.Token  -> Class B
~~~

Mặc dù hai class có cùng binary name, Class A và Class B không đồng nhất. JVM không gộp chúng chỉ vì tên package và class giống nhau.

Trong cùng một defining loader, việc cố định nghĩa lại một class đã có cùng binary name thường dẫn đến `LinkageError` do duplicate class definition. Hai loader khác nhau có thể định nghĩa class cùng tên mà không gặp xung đột định nghĩa theo cách đó.

### 2.2. Parent delegation

ClassLoader tiêu chuẩn thường dùng mô hình parent-first:

1. Kiểm tra class đã được loader nạp chưa.
2. Yêu cầu parent loader nạp class.
3. Nếu parent không tìm thấy, loader hiện tại mới tìm và định nghĩa class.

Mô hình này giúp các kiểu nền tảng và API dùng chung được nạp nhất quán. Ví dụ, nhiều plugin có thể cùng nhìn thấy một interface API từ parent loader.

Một custom class loader có thể thay đổi thứ tự tìm kiếm, chẳng hạn child-first cho một số thư viện plugin. Điều này có ích khi plugin cần phiên bản thư viện riêng, nhưng cũng dễ tạo ra hai bản sao của cùng một API hoặc kiểu dữ liệu.

Không nên thay đổi delegation một cách tùy tiện. Hãy xác định package nào phải dùng chung và package nào cần được cô lập trước khi triển khai loader tùy chỉnh.

### 2.3. Các loader thường gặp

Trong một JVM hiện đại, thường gặp:

| Loader | Vai trò |
| --- | --- |
| Bootstrap loader | Nạp các class nền tảng cốt lõi của runtime |
| Platform class loader | Nạp các module và thư viện nền tảng thuộc Java platform |
| System/Application class loader | Nạp class từ application class path hoặc module path theo cấu hình chạy |
| Custom class loader | Nạp class từ nguồn do ứng dụng quản lý, ví dụ plugin, bytecode sinh động hoặc kho class riêng |

Có thể xem một số loader chuẩn:

~~~java
System.out.println(String.class.getClassLoader());
System.out.println(ClassLoader.getPlatformClassLoader());
System.out.println(ClassLoader.getSystemClassLoader());
~~~

`String.class.getClassLoader()` thường in `null` vì String được bootstrap loader định nghĩa. Platform và system loader là các đối tượng ClassLoader cụ thể.

### 2.4. Runtime package và package-private

Package-private không chỉ dựa trên chuỗi tên package trong source. Runtime package được xác định theo tên package và defining class loader. Vì vậy, hai class có cùng tên package nhưng do hai loader khác nhau định nghĩa không thuộc cùng runtime package.

Ví dụ, hai class cùng khai báo:

~~~java
package com.acme.internal;
~~~

nhưng được nạp bởi loader A và loader B thì không thể dùng quyền package-private của nhau. Một class package-private ở loader A không trở nên truy cập được chỉ vì class ở loader B cũng có cùng package name.

Đây là một lý do quan trọng khiến plugin có class loader riêng cần dùng API public rõ ràng để trao đổi dữ liệu.

## 3. Module identity và ModuleLayer

### 3.1. Module là đơn vị đóng gói và kiểm soát truy cập

Trong JPMS, module có tên và descriptor. Descriptor khai báo các dependency, package được export, package được opens và các service mà module sử dụng hoặc cung cấp.

Một class đã được định nghĩa trong named module có thể truy xuất module runtime của nó:

~~~java
Module module = SomeType.class.getModule();

System.out.println(module.getName());
System.out.println(module.isNamed());
System.out.println(module.getLayer());
~~~

`Class.getModule()` trả về Module object gắn với class. Module object cung cấp tên module, trạng thái named/unnamed và layer chứa module đó.

### 3.2. Module name không phải Module object identity

Tên module là tên được khai báo trong `module-info.java`, ví dụ `sample.model`. Tên này định danh module trong một configuration/layer graph, nhưng không phải một định danh toàn cục duy nhất cho mọi ModuleLayer trong JVM.

Hai ModuleLayer độc lập có thể chứa hai instance của module cùng tên `sample.model`. Khi đó:

- `firstModule.getName()` và `secondModule.getName()` có thể bằng nhau.
- `firstModule == secondModule` vẫn là `false`.
- Hai Module object thuộc hai ModuleLayer khác nhau.
- Các class được định nghĩa bởi loader riêng trong hai layer cũng có class identity khác nhau.

Vì vậy, log chỉ ghi module name có thể chưa đủ để phân biệt hai bản nạp. Khi chẩn đoán plugin, nên ghi cả module name, layer và class loader.

### 3.3. ModuleLayer tổ chức module graph lúc runtime

ModuleLayer là tập hợp module đã được định nghĩa trong JVM cùng quan hệ với các layer cha. Một layer có thể được tạo từ Configuration:

~~~java
Configuration configuration = ModuleLayer.boot()
        .configuration()
        .resolve(
                pluginFinder,
                ModuleFinder.of(),
                Set.of("sample.model")
        );

ModuleLayer layer = ModuleLayer.boot()
        .defineModulesWithOneLoader(
                configuration,
                ClassLoader.getSystemClassLoader()
        );
~~~

Trong ví dụ trên, `ModuleFinder` tìm module plugin, `resolve` tạo configuration hợp lệ và `defineModulesWithOneLoader` định nghĩa module trong layer mới bằng một loader do layer tạo ra.

Các API thường dùng:

- `ModuleLayer.boot()`: lấy boot layer.
- `ModuleLayer.findModule(name)`: tìm module trực tiếp trong layer.
- `ModuleLayer.findLoader(name)`: lấy loader dùng cho module trong layer.
- `ModuleLayer.modules()`: lấy các module trực tiếp thuộc layer hiện tại.
- `Module.getLayer()`: tìm layer chứa một named module.

`ModuleLayer.modules()` không tự gộp các module ở layer cha. Nếu cần xem module cha, hãy truy cập quan hệ parent layer.

### 3.4. One loader và many loaders

JPMS cung cấp nhiều cách định nghĩa module trong layer:

- `defineModulesWithOneLoader`: dùng một class loader cho các module mới trong layer.
- `defineModulesWithManyLoaders`: tạo loader riêng cho từng module mới.
- `defineModules`: cho phép ứng dụng cung cấp hàm ánh xạ module name sang loader.

Một loader dùng chung giúp các module trong layer chia sẻ class loading thuận tiện hơn. Nhiều loader tạo namespace riêng theo module, nhưng làm tăng yêu cầu thiết kế API và trao đổi kiểu.

Dù chọn cách nào, class identity vẫn phải được hiểu theo binary name và defining loader. ModuleLayer không tự hợp nhất hai class đã được định nghĩa bởi hai loader khác nhau.

## 4. Class identity trong named module

### 4.1. Cùng module name ở hai layer vẫn có thể là hai kiểu khác nhau

Giả sử một module `sample.model` chứa:

~~~java
package com.acme.model;

public final class Token {
    public String value() {
        return "shared-name";
    }
}
~~~

Ứng dụng có thể tìm module đó từ cùng một thư mục plugin và tạo hai ModuleLayer độc lập. Mỗi layer định nghĩa `sample.model` với loader riêng.

~~~text
Boot layer
   |
   +-------------------------+
   |                         |
   v                         v
Layer A                  Layer B
sample.model             sample.model
Loader A                 Loader B
   |                         |
   v                         v
com.acme.model.Token     com.acme.model.Token
Class A                  Class B
~~~

Hai class có cùng binary name và module name, nhưng defining loader khác nhau. Vì vậy, Class object khác nhau và object tạo từ Class B không ép kiểu sang Class A được.

### 4.2. Module encapsulation vẫn áp dụng

Class loader có thể tìm và nạp class, nhưng việc nạp thành công không tự cấp quyền truy cập API qua biên module.

Để module khác truy cập kiểu public theo cách thông thường, module sở hữu package cần export package đó và module gọi cần đọc module tương ứng. `requires` thiết lập readability; `exports` công bố package cho truy cập thông thường.

`opens` dành cho deep reflection vào package. Nó không export package, không làm class trở thành cùng một kiểu và không thay đổi class identity.

### 4.3. Classpath và unnamed module

Code chạy trên classpath thường thuộc unnamed module của class loader tương ứng. Mỗi class loader có unnamed module riêng. Vì vậy, cùng một class name được nạp bởi hai custom loader cũng có thể thuộc hai unnamed module khác nhau.

Có thể kiểm tra:

~~~java
Module module = SomeType.class.getModule();

System.out.println(module.isNamed());
System.out.println(module.getName());
~~~

Với unnamed module, `isNamed()` là `false` và `getName()` trả về `null`. Không nên dùng module name để phân biệt class trong unnamed module; cần kiểm tra defining loader và Class object.

## 5. Nạp class và chẩn đoán identity

### 5.1. ClassLoader.loadClass

Khi đã có loader phù hợp, có thể yêu cầu nạp class:

~~~java
ClassLoader loader = layer.findLoader("sample.model");
Class<?> type = loader.loadClass("com.acme.model.Token");
~~~

`loadClass` nhận binary name và trả về Class object. Nó có thể ném `ClassNotFoundException` nếu loader không tìm thấy class. Thao tác này không đồng nghĩa với việc module đã export package cho module gọi.

### 5.2. Class.forName

Các overload của `Class.forName` có hành vi khác nhau:

~~~java
Class<?> typeA = Class.forName("com.acme.model.Token");

Class<?> typeB = Class.forName(
        "com.acme.model.Token",
        false,
        loader
);

Class<?> typeC = Class.forName(
        module,
        "com.acme.model.Token"
);
~~~

- `Class.forName(String)` tìm class bằng loader của caller và khởi tạo class.
- `Class.forName(String, boolean, ClassLoader)` cho phép chỉ định loader và có chọn khởi tạo hay không.
- `Class.forName(Module, String)` tìm class trong một module cụ thể; trả về `null` nếu module không chứa class đó và không khởi tạo class.

Khi làm việc với nhiều layer, chỉ định module hoặc loader rõ ràng giúp tránh vô tình nạp class từ application loader thay vì plugin loader.

### 5.3. Các API kiểm tra

| API | Thông tin |
| --- | --- |
| `type.getName()` | Binary name của class |
| `type.getClassLoader()` | Defining class loader; có thể là `null` với bootstrap loader |
| `type.getModule()` | Module object chứa class |
| `type.getModule().getName()` | Tên module, hoặc `null` với unnamed module |
| `type.getModule().getLayer()` | ModuleLayer chứa named module |
| `type.isAssignableFrom(other)` | Kiểm tra khả năng gán kiểu theo quan hệ type |
| `type.isInstance(object)` | Kiểm tra object có là instance của type hay không |
| `layer.findLoader(moduleName)` | Loader được layer dùng cho module |

Khi log lỗi plugin, hãy ghi tối thiểu binary name, module name, ModuleLayer và defining loader. Nếu cần so sánh chính xác, so sánh Class object và Module object trực tiếp.

## 6. Ví dụ chạy được: cùng module name nhưng khác class identity

Ví dụ này biên dịch một module `sample.model` duy nhất vào thư mục plugin. Ứng dụng tạo hai ModuleLayer độc lập từ cùng module đó, rồi nạp cùng binary name qua loader của từng layer.

Cấu trúc source:

~~~text
src/
├── sample.model/
│   ├── module-info.java
│   └── com/acme/model/Token.java
└── launcher.app/
    ├── module-info.java
    └── com/acme/launcher/Main.java
~~~

### 6.1. Module sample.model

File `src/sample.model/module-info.java`:

~~~java
module sample.model {
    exports com.acme.model;
}
~~~

File `src/sample.model/com/acme/model/Token.java`:

~~~java
package com.acme.model;

public final class Token {
    public String value() {
        return "shared-name";
    }
}
~~~

Package được export để ví dụ có thể dùng kiểu public qua ranh giới module. Việc export không làm hai bản nạp ở hai layer trở thành cùng một Class object.

### 6.2. Module launcher.app

File `src/launcher.app/module-info.java`:

~~~java
module launcher.app {
}
~~~

File `src/launcher.app/com/acme/launcher/Main.java`:

~~~java
package com.acme.launcher;

import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public final class Main {
    private static ModuleLayer createLayer(ModuleFinder finder) {
        Configuration configuration = ModuleLayer.boot()
                .configuration()
                .resolve(
                        finder,
                        ModuleFinder.of(),
                        Set.of("sample.model")
                );

        return ModuleLayer.boot().defineModulesWithOneLoader(
                configuration,
                ClassLoader.getSystemClassLoader()
        );
    }

    public static void main(String[] args) throws Exception {
        ModuleFinder finder = ModuleFinder.of(Path.of("plugins"));

        ModuleLayer firstLayer = createLayer(finder);
        ModuleLayer secondLayer = createLayer(finder);

        Class<?> first = firstLayer.findLoader("sample.model")
                .loadClass("com.acme.model.Token");

        Class<?> second = secondLayer.findLoader("sample.model")
                .loadClass("com.acme.model.Token");

        Object secondInstance = second.getDeclaredConstructor()
                .newInstance();

        System.out.println("binary name=" + first.getName());
        System.out.println("same binary name="
                + first.getName().equals(second.getName()));
        System.out.println("same module name="
                + first.getModule().getName()
                        .equals(second.getModule().getName()));
        System.out.println("same Module object="
                + (first.getModule() == second.getModule()));
        System.out.println("same ModuleLayer="
                + (first.getModule().getLayer()
                        == second.getModule().getLayer()));
        System.out.println("same defining loader="
                + (first.getClassLoader() == second.getClassLoader()));
        System.out.println("same Class object=" + (first == second));
        System.out.println("assignable="
                + first.isAssignableFrom(second));

        try {
            first.cast(secondInstance);
            System.out.println("cross-layer cast=unexpected success");
        } catch (ClassCastException expected) {
            System.out.println("cross-layer cast=ClassCastException");
        }
    }
}
~~~

Hàm `createLayer` phân giải cùng module name từ cùng finder mỗi lần được gọi. Mỗi lần `defineModulesWithOneLoader` tạo một layer và loader mới. Vì vậy, hai class được nạp có cùng tên nhưng khác defining loader.

### 6.3. Biên dịch và chạy bằng Java 17+

Từ thư mục chứa `src`, biên dịch module plugin vào thư mục `plugins`:

~~~bash
javac --release 17 --module-source-path src -d plugins -m sample.model
~~~

Biên dịch ứng dụng launcher vào thư mục `mods`:

~~~bash
javac --release 17 --module-source-path src -d mods -m launcher.app
~~~

Chạy ứng dụng từ thư mục dự án để đường dẫn tương đối `plugins` được tìm thấy:

~~~bash
java --module-path mods -m launcher.app/com.acme.launcher.Main
~~~

Kết quả stdout:

~~~text
binary name=com.acme.model.Token
same binary name=true
same module name=true
same Module object=false
same ModuleLayer=false
same defining loader=false
same Class object=false
assignable=false
cross-layer cast=ClassCastException
~~~

Kết quả chứng minh:

1. Hai class có cùng binary name.
2. Hai Module object có cùng module name nhưng khác identity.
3. Hai ModuleLayer và defining class loader khác nhau.
4. Hai Class object khác nhau và không tương thích phép gán.
5. Ép kiểu object của layer thứ hai sang Class của layer thứ nhất gây `ClassCastException`.

## 7. Lỗi phổ biến trong môi trường nhiều loader

### 7.1. ClassCastException dù tên class giống nhau

Nguyên nhân thường là object được tạo từ bản class do loader khác định nghĩa. Kiểm tra:

~~~java
System.out.println(object.getClass().getName());
System.out.println(object.getClass().getClassLoader());
System.out.println(expectedType.getClassLoader());
System.out.println(expectedType.isInstance(object));
~~~

Giải pháp kiến trúc là dùng một API chung được nạp từ parent loader hoặc parent layer. Tránh để cả ứng dụng và plugin tự nạp bản sao của interface hoặc DTO mà chúng cần trao đổi.

### 7.2. LinkageError do định nghĩa trùng trong cùng loader

Nếu một loader cố định nghĩa cùng binary name nhiều lần, JVM có thể ném `LinkageError`. Hãy kiểm tra cache class, thứ tự tìm kiếm và logic `findClass` của custom loader.

Nếu cần nạp hai phiên bản độc lập, hãy dùng hai loader hoặc hai layer có ranh giới rõ, đồng thời thiết kế API trao đổi dữ liệu qua một kiểu chung.

### 7.3. ClassNotFoundException và NoClassDefFoundError

- `ClassNotFoundException` thường xuất hiện khi ứng dụng gọi API nạp class theo tên nhưng loader không tìm thấy class.
- `NoClassDefFoundError` xuất hiện khi JVM cần một class dependency nhưng định nghĩa không thể được cung cấp tại runtime.
- `LinkageError` là nhóm lỗi liên kết, có thể xuất hiện khi class đã được nạp nhưng các định nghĩa hoặc ràng buộc liên kết không tương thích.

Hãy phân biệt lỗi tìm class với lỗi identity và lỗi module resolution. Chúng có thể có nguyên nhân khác nhau dù cùng xuất hiện trong quá trình nạp plugin.

### 7.4. Nạp nhầm API từ child layer

Nếu plugin đóng gói một bản sao của API mà ứng dụng đã có ở parent layer, resolver hoặc custom loader có thể tạo ra hai bản API. Provider có thể triển khai interface ở child layer trong khi consumer đang chờ interface ở parent layer.

Cách thiết kế an toàn hơn:

- Đặt module API dùng chung ở parent layer.
- Để plugin khai báo `requires shared.api;`.
- Không đóng gói lại API chung bên trong từng plugin.
- Khi phân giải plugin, ưu tiên module API đã có ở parent configuration.
- Dùng service interface hoặc DTO do parent định nghĩa để truyền dữ liệu qua ranh giới plugin.

### 7.5. Lỗi truy cập module không phải lỗi class identity

Một class có thể đã được nạp nhưng module gọi vẫn không được phép truy cập package hoặc thành viên của nó. Kiểm tra các directive:

- `requires` tạo readability giữa các module.
- `exports` công bố package cho truy cập Java thông thường.
- `opens` cấp quyền deep reflection cho package theo phạm vi được chỉ định.

Thêm `opens` không sửa được ClassCastException do hai loader định nghĩa hai kiểu riêng. Tương tự, export package không hợp nhất hai ModuleLayer.

## 8. Thiết kế API cho ứng dụng plugin

### 8.1. Đặt kiểu dùng chung ở parent

Nếu ứng dụng và plugin cần trao đổi dữ liệu, hãy đặt interface và DTO trong module API mà cả hai cùng đọc từ parent. Ví dụ:

~~~java
package com.acme.plugin.api;

public interface Plugin {
    PluginResult execute(PluginRequest request);
}
~~~

`PluginRequest` và `PluginResult` cũng nên thuộc module API chung nếu chúng đi qua ranh giới loader. Provider trong child layer triển khai interface từ parent và nhận object do parent định nghĩa.

### 8.2. Giữ implementation ở child

Các class triển khai, thư viện riêng và chi tiết nội bộ của plugin có thể ở child layer. Không cần export package triển khai chỉ để ServiceLoader tạo provider theo khai báo `provides`.

Điều này giúp ứng dụng chỉ phụ thuộc vào hợp đồng API, còn plugin có thể thay implementation mà không làm thay đổi kiểu dữ liệu chung.

### 8.3. Tránh đưa kiểu nội bộ qua ranh giới

Nếu plugin trả về object có class được định nghĩa trong child loader, consumer không nên cố ép kiểu object đó sang một class cùng tên được nạp ở parent. Hãy chuyển dữ liệu sang DTO chung, trả về interface chung hoặc dùng kiểu nền tảng như String, primitive và collection chứa các kiểu API chung.

### 8.4. Quản lý nhiều phiên bản plugin

Hai layer độc lập có thể giữ hai phiên bản plugin cùng module name. Đây là cơ sở để triển khai phiên bản mới song song với phiên bản cũ trong cùng JVM, nhưng ứng dụng phải quản lý rõ instance, thread, callback và tài nguyên của từng layer.

Không có thao tác chung để cưỡng bức unload ModuleLayer. Class loader chỉ có thể được thu hồi khi không còn tham chiếu và JVM có thể garbage-collect nó. Hãy dừng service, đóng tài nguyên và bỏ tham chiếu trước khi mong đợi loader cũ được thu hồi.

## 9. Checklist chẩn đoán

- [ ] So sánh binary name của hai class.
- [ ] So sánh `Class.getClassLoader()` để tìm defining loader.
- [ ] So sánh Class object bằng `==`.
- [ ] Dùng `isAssignableFrom` hoặc `isInstance` để xác nhận tương thích.
- [ ] Kiểm tra `Class.getModule()` và module name.
- [ ] Kiểm tra Module object và ModuleLayer, không chỉ module name.
- [ ] Xác định module API có đang được chia sẻ từ parent layer không.
- [ ] Kiểm tra module path, ModuleFinder và class loader delegation.
- [ ] Phân biệt lỗi class not found, lỗi liên kết, lỗi ép kiểu và lỗi truy cập module.
- [ ] Dùng interface/DTO chung do parent định nghĩa để trao đổi giữa các plugin.
- [ ] Không coi ModuleLayer là sandbox bảo mật hoặc cơ chế unload tức thì.
