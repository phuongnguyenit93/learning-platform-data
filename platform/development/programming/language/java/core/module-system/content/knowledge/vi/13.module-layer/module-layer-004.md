# defineModulesWithOneLoader

Trong Java Platform Module System (JPMS), Configuration mô tả tập module đã được giải quyết và các quan hệ dependency của chúng. Để các module đó tham gia runtime, Java cần định nghĩa chúng trong một ModuleLayer và gắn chúng với class loader.

Phương thức ModuleLayer.defineModulesWithOneLoader() tạo một layer mới và định nghĩa tất cả module trong configuration được cung cấp bằng một class loader chung. Cách tổ chức này phù hợp khi nạp một nhóm module có quan hệ chặt chẽ, chẳng hạn một plugin cùng các module phụ trợ của nó.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vai trò của defineModulesWithOneLoader() trong quy trình tạo module layer.
- Phân biệt configuration cha, module layer cha và class loader cha.
- Tạo configuration từ module finder rồi định nghĩa layer bằng một loader.
- Lấy module và class loader từ layer mới.
- Hiểu vai trò của ModuleLayer.Controller.
- So sánh one-loader với many-loaders và chọn cách phù hợp cho plugin.

## 1. ModuleLayer và class loader

Một module graph đã được resolve chưa đồng nghĩa các class của module đã được nạp vào runtime. Sau khi có Configuration, ứng dụng có thể định nghĩa các module trong một ModuleLayer.

~~~text
ModuleFinder
    |
    v
Configuration.resolve(...)
    |
    v
Resolved module graph
    |
    v
ModuleLayer.defineModulesWithOneLoader(...)
    |
    v
New ModuleLayer
    |
    v
Modules defined with one class loader
~~~

Ba khái niệm cần phân biệt:

- **Configuration:** tập module đã được giải quyết cùng dependency và configuration cha.
- **ModuleLayer:** tập các đối tượng Module được định nghĩa trong runtime, có quan hệ với các layer cha.
- **ClassLoader:** cơ chế nạp class. Một module được định nghĩa trong layer sẽ gắn với class loader được chọn khi tạo layer.

ModuleLayer sử dụng Configuration để định nghĩa module vào runtime. Configuration mô tả module graph; layer tổ chức các module đã resolve trong runtime.

## 2. API defineModulesWithOneLoader

API static có dạng:

~~~java
ModuleLayer.defineModulesWithOneLoader(
    Configuration cf,
    List<ModuleLayer> parents,
    ClassLoader parentLoader
);
~~~

| Tham số | Ý nghĩa |
|---|---|
| cf | Configuration chứa các module cần định nghĩa trong layer mới |
| parents | Danh sách module layer cha tương ứng với các configuration cha của cf |
| parentLoader | Class loader cha của class loader được tạo cho layer mới |

Kết quả trả về là ModuleLayer.Controller. Gọi controller.layer() để lấy layer vừa tạo.

Đặc điểm chính:

- Các module thuộc configuration mới được định nghĩa bằng cùng một class loader.
- Các module đã thuộc layer cha vẫn thuộc layer và class loader của cha.
- Mỗi module vẫn là một named module riêng với descriptor và quy tắc truy cập riêng.
- Dùng chung class loader không làm hợp nhất các module thành một module duy nhất.

Cần phân biệt hai loại parent:

- Danh sách parents xác định quan hệ giữa các module layer.
- parentLoader xác định class loader cha trong cơ chế delegation khi nạp class.

Đây là hai tham số phục vụ hai cơ chế khác nhau.

## 3. Resolve configuration trước khi tạo layer

Trước khi gọi defineModulesWithOneLoader(), cần resolve module graph. Ví dụ, các plugin được đóng gói trong thư mục:

~~~text
plugins/
├── com.acme.plugin.alpha.jar
├── com.acme.plugin.beta.jar
└── com.acme.plugin.common.jar
~~~

Giả sử module alpha phụ thuộc beta và common. Có thể tìm module và resolve từ boot layer:

~~~java
Path pluginPath = Path.of("plugins");
ModuleFinder finder = ModuleFinder.of(pluginPath);

ModuleLayer parentLayer = ModuleLayer.boot();

Configuration configuration =
    parentLayer.configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.acme.plugin.alpha")
    );
~~~

Trong ví dụ:

- ModuleFinder.of(pluginPath) tìm các module trong thư mục plugin.
- Boot layer là layer cha.
- resolve() bắt đầu từ root com.acme.plugin.alpha và tìm các dependency cần thiết.
- Configuration kết quả chứa các module mới được giải quyết cùng quan hệ tới configuration cha.

Nếu dependency không có trong module path hoặc không được cung cấp bởi configuration cha, resolution có thể thất bại trước khi tạo layer.

## 4. Tạo layer bằng một class loader

Sau khi resolve thành công, gọi API:

~~~java
ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithOneLoader(
        configuration,
        List.of(parentLayer),
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer pluginLayer = controller.layer();
~~~

ClassLoader.getSystemClassLoader() được dùng làm parent class loader cho loader mới. Loader của layer mới có thể ủy quyền việc nạp class mà nó không định nghĩa cho parent loader theo cơ chế delegation.

Cấu hình layer cha và class loader cha không giống nhau:

- List.of(parentLayer) cho biết layer mới có boot layer làm cha.
- ClassLoader.getSystemClassLoader() cho biết loader mới có system class loader làm parent.

Khi có nhiều layer cha, configuration phải được resolve từ các configuration cha tương ứng và danh sách layer truyền vào phải phù hợp với chúng.

### 4.1. Lấy module và kiểm tra class loader

Từ controller, lấy layer:

~~~java
ModuleLayer pluginLayer = controller.layer();
~~~

Tìm module:

~~~java
Module pluginModule = pluginLayer.findModule("com.acme.plugin.alpha")
    .orElseThrow();

System.out.println(pluginModule.getName());
ClassLoader pluginLoader = pluginModule.getClassLoader();
~~~

Các module trong configuration mới được tạo bằng one-loader sẽ trả về cùng một class loader:

~~~java
Module alpha = pluginLayer.findModule("com.acme.plugin.alpha")
    .orElseThrow();

Module beta = pluginLayer.findModule("com.acme.plugin.beta")
    .orElseThrow();

System.out.println(alpha.getClassLoader() == beta.getClassLoader());
~~~

Nếu cả hai module đều thuộc configuration được định nghĩa bởi lời gọi one-loader đó, kết quả là true.

ModuleLayer.findModule() có thể tìm module trong layer hiện tại và các layer cha. Khi kiểm tra module mới, hãy dùng tên module thuộc configuration mới để tránh nhầm với module đã tồn tại ở layer cha.

## 5. Ví dụ plugin hoàn chỉnh

Ví dụ dưới đây nạp một plugin module từ thư mục plugins. Plugin được resolve rồi định nghĩa trong layer mới với một loader chung.

Cấu trúc:

~~~text
application/
├── app/
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
└── plugins/
    └── com.acme.plugin/
        ├── module-info.java
        └── com/acme/plugin/PluginEntry.java
~~~

### 5.1. Module plugin

File module-info.java:

~~~java
module com.acme.plugin {
    exports com.acme.plugin;
}
~~~

File PluginEntry.java:

~~~java
package com.acme.plugin;

public class PluginEntry {
    public String name() {
        return "Sample plugin";
    }
}
~~~

Plugin export package chứa entry class để mã bên ngoài có thể truy cập class public này.

### 5.2. Module app

File module-info.java:

~~~java
module com.acme.app {
}
~~~

File Main.java:

~~~java
package com.acme.app;

import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.lang.reflect.Method;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

public class Main {
    public static void main(String[] args) throws Exception {
        Path pluginPath = Path.of("plugins");
        ModuleLayer parentLayer = ModuleLayer.boot();
        ModuleFinder finder = ModuleFinder.of(pluginPath);

        Configuration configuration =
            parentLayer.configuration().resolve(
                finder,
                ModuleFinder.of(),
                Set.of("com.acme.plugin")
            );

        ModuleLayer.Controller controller =
            ModuleLayer.defineModulesWithOneLoader(
                configuration,
                List.of(parentLayer),
                ClassLoader.getSystemClassLoader()
            );

        ModuleLayer pluginLayer = controller.layer();

        Module pluginModule = pluginLayer
            .findModule("com.acme.plugin")
            .orElseThrow();

        ClassLoader pluginLoader = pluginModule.getClassLoader();

        Class<?> entryClass = Class.forName(
            "com.acme.plugin.PluginEntry",
            true,
            pluginLoader
        );

        Object entry = entryClass.getConstructor().newInstance();
        Method nameMethod = entryClass.getMethod("name");

        System.out.println(nameMethod.invoke(entry));
    }
}
~~~

Ví dụ dùng reflection để minh họa class được nạp bằng loader của plugin. Package đã được export nên class public và constructor public có thể được truy cập theo cách thông thường.

### 5.3. Biên dịch và chạy

Biên dịch plugin thành module JAR, đặt JAR vào thư mục plugins. Sau đó biên dịch module app và chạy app với module path chứa app. Khi chạy, app dùng ModuleFinder để tìm plugin trong thư mục plugins.

Ví dụ tạo JAR:

~~~bash
jar --create --file plugins/com.acme.plugin.jar -C plugins-out/com.acme.plugin .
~~~

Chạy ứng dụng:

~~~bash
java --module-path app-out -m com.acme.app/com.acme.app.Main
~~~

Kết quả:

~~~text
Sample plugin
~~~

Plugin được tìm trong thư mục plugins mà app truyền vào ModuleFinder, không cần đưa plugin vào boot layer. Layer mới định nghĩa plugin và gắn module plugin với class loader được tạo cho layer đó.

## 6. ModuleLayer.Controller

defineModulesWithOneLoader() trả về ModuleLayer.Controller. Controller cung cấp quyền điều chỉnh một số quan hệ module sau khi layer được định nghĩa.

| Phương thức | Tác dụng |
|---|---|
| layer() | Lấy ModuleLayer vừa tạo |
| addReads(source, target) | Bổ sung quan hệ đọc từ module nguồn tới module đích |
| addExports(source, package, target) | Export một package của module nguồn cho module đích |
| addOpens(source, package, target) | Mở package của module nguồn cho deep reflection từ module đích |

Ví dụ:

~~~java
Module source = pluginLayer.findModule("com.acme.plugin")
    .orElseThrow();

Module target = ModuleLayer.boot()
    .findModule("com.acme.app")
    .orElseThrow();

controller.addReads(source, target);
~~~

Ví dụ này bổ sung quan hệ đọc từ plugin tới app. Chỉ dùng khi có yêu cầu runtime cụ thể và đã hiểu tác động tới ranh giới module.

Controller điều chỉnh các module do controller đó tạo ra. Thay đổi này chỉ có hiệu lực runtime, không sửa module-info.java trong JAR. Hãy ưu tiên khai báo dependency và export ổn định trong descriptor; dùng controller cho tích hợp động có chủ đích.

## 7. So sánh one-loader và many-loaders

| Cách tạo | Ánh xạ class loader |
|---|---|
| defineModulesWithOneLoader | Tất cả module trong configuration mới dùng chung một loader |
| defineModulesWithManyLoaders | Mỗi module trong configuration mới có loader riêng |
| defineModules | Ứng dụng cung cấp hàm ánh xạ module name sang class loader |

### 7.1. Khi nào one-loader phù hợp?

Dùng defineModulesWithOneLoader() khi:

- Một nhóm module thuộc cùng một ứng dụng hoặc plugin suite.
- Các module cần chia sẻ một cơ chế nạp class thống nhất.
- Không cần tách riêng class loader cho từng module.
- Muốn giảm số lượng class loader cần quản lý.

### 7.2. Khi nào many-loaders phù hợp?

Dùng defineModulesWithManyLoaders() khi cần mỗi module có class loader riêng, chẳng hạn để quản lý class loading hoặc vòng đời module độc lập hơn.

Nhiều class loader không tự tạo ra sandbox bảo mật. Không nên xem class loader là ranh giới an toàn để chạy mã không tin cậy.

### 7.3. Một loader không hợp nhất module

Dù các module dùng chung class loader:

- Mỗi module vẫn có tên và đối tượng Module riêng.
- requires, exports, opens và quy tắc truy cập vẫn được áp dụng.
- Package không export vẫn không trở thành API công khai.
- Các module vẫn có thể được tìm riêng trong layer theo tên.

Dùng chung loader không đồng nghĩa mọi class trong layer có thể truy cập lẫn nhau.

## 8. Điều kiện và giới hạn

### 8.1. Configuration phải phù hợp với parent layers

Configuration truyền vào phải được resolve với các configuration cha tương ứng. Danh sách parent layers khi định nghĩa layer phải phản ánh đúng các configuration cha đó.

Nếu configuration được resolve từ boot configuration, danh sách parent thường là:

~~~java
List.of(ModuleLayer.boot())
~~~

Không truyền một layer cha không tương ứng với configuration đã dùng để resolve.

### 8.2. Package trùng giữa các module

Các module trong cùng một configuration/layer cần tuân thủ ràng buộc package của JPMS. Nếu hai module trong cùng layer chứa cùng một package, việc định nghĩa layer có thể thất bại với LayerInstantiationException.

Khi gặp lỗi split package:

1. Xác định các module đang chứa package trùng.
2. Chọn một module sở hữu package đó.
3. Chuyển class liên quan về cùng module hoặc thiết kế lại package.
4. Resolve lại configuration và định nghĩa layer.

### 8.3. Phân biệt lỗi resolution và lỗi layer creation

- Configuration.resolve() có thể thất bại nếu module không tìm thấy, dependency không hợp lệ hoặc graph có chu trình.
- defineModulesWithOneLoader() có thể thất bại khi không thể định nghĩa các module vào layer với ràng buộc class loader/package tương ứng.

Hãy xác định lỗi xảy ra trước hay sau khi có Configuration. Không sửa requires nếu nguyên nhân thực tế là package conflict hoặc loader constraint.

## 9. Những nhầm lẫn thường gặp

**One-loader có nghĩa tất cả module trong JVM dùng chung loader?** Không. Chỉ các module thuộc configuration mới được định nghĩa bởi lời gọi đó dùng chung loader. Module ở parent layers tiếp tục dùng loader của layer cha.

**Parent layer và parent class loader có giống nhau?** Không. Parent layer xác định quan hệ module giữa các layer. Parent class loader xác định delegation của class loading.

**Layer mới có thay đổi boot layer?** Không. Layer mới là layer con; các module đã có trong boot layer vẫn thuộc boot layer.

**Dùng one-loader có bỏ qua exports không?** Không. Mỗi module vẫn giữ ranh giới truy cập của JPMS.

**Có thể dùng one-loader làm sandbox cho plugin không?** Không. Plugin không tin cậy cần được cô lập ở mức process hoặc cơ chế bảo mật thích hợp.

## 10. Quy trình triển khai plugin bằng one-loader

1. Định nghĩa API ổn định ở module cha hoặc module dùng chung.
2. Đóng gói plugin và dependency thành các named module.
3. Chọn root module plugin cần nạp.
4. Dùng ModuleFinder để tìm module trong thư mục plugin.
5. Resolve Configuration với boot layer hoặc layer cha phù hợp.
6. Dùng defineModulesWithOneLoader() để tạo layer.
7. Lấy module từ layer và xác định class loader.
8. Nạp entry point hoặc tìm service provider qua ServiceLoader.
9. Quản lý lỗi khởi tạo, trạng thái và vòng đời plugin.
10. Chỉ dùng Controller để điều chỉnh quan hệ runtime khi có nhu cầu rõ ràng.

Nếu plugin cung cấp service, nên thiết kế API bằng uses và provides để không phụ thuộc vào tên class implementation cụ thể.

## 11. Tự kiểm tra

**Tình huống 1:** Configuration chứa ba module plugin A, B, C. Gọi defineModulesWithOneLoader() thì mỗi module có class loader riêng không?

**Trả lời:** Không. Các module thuộc configuration mới được định nghĩa bằng cùng một class loader. Module trong parent layers vẫn dùng loader của layer cha.

**Tình huống 2:** Configuration được resolve từ boot layer. Khi tạo layer, vì sao truyền List.of(ModuleLayer.boot())?

**Trả lời:** Vì boot layer là layer cha tương ứng với configuration cha đã dùng trong quá trình resolve.

**Tình huống 3:** defineModulesWithOneLoader() trả về gì?

**Trả lời:** Một ModuleLayer.Controller. Gọi controller.layer() để lấy layer vừa tạo.

**Tình huống 4:** Hai module trong configuration có package trùng tên. One-loader có tự giải quyết xung đột không?

**Trả lời:** Không. Package conflict có thể khiến layer creation thất bại. Cần tổ chức lại package hoặc module sở hữu package.

**Tình huống 5:** One-loader có làm các module bỏ qua quy tắc exports không?

**Trả lời:** Không. Module identity và quy tắc truy cập vẫn được giữ nguyên dù các module dùng chung class loader.

**Tình huống 6:** Khi nào nên chọn many-loaders?

**Trả lời:** Khi cần mỗi module có class loader riêng để quản lý class loading hoặc vòng đời module độc lập hơn. Cách này vẫn không tự tạo sandbox bảo mật.

Khi thiết kế plugin bằng JPMS, hãy tách rõ ba bước: resolve module graph thành Configuration, định nghĩa Configuration trong ModuleLayer, rồi sử dụng class hoặc service từ layer mới. defineModulesWithOneLoader() đảm nhiệm bước định nghĩa layer với một loader chung, trong khi module descriptor tiếp tục quyết định dependency và quyền truy cập giữa các module.
