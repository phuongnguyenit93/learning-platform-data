# Ánh xạ mô-đun tới một hoặc nhiều class loader

Trong JPMS, **ModuleLayer** mô hình hóa một tập hợp mô-đun đã được phân giải và gắn với một class loader hoặc nhóm class loader. Một mô-đun không chỉ có tên và descriptor; khi được định nghĩa trong một layer, nó còn có quan hệ với class loader chịu trách nhiệm nạp các lớp thuộc mô-đun đó.

Điểm cần nắm là quan hệ giữa **Module**, **ModuleLayer** và **ClassLoader**:

- Một mô-đun được định nghĩa trong một ModuleLayer.
- Một ModuleLayer có thể ánh xạ các mô-đun của nó tới một hoặc nhiều class loader.
- Nhiều mô-đun trong cùng layer có thể dùng chung một loader.
- Một layer có thể được xây dựng trên layer cha, cho phép ứng dụng tạo cấu trúc mô-đun động theo từng plugin hoặc nhóm chức năng.
- Việc một mô-đun đọc được mô-đun khác và việc một class loader nạp được lớp là hai vấn đề liên quan nhưng khác nhau.

Bài học này tập trung vào cách JPMS ánh xạ mô-đun tới loader, cách đọc ánh xạ bằng API hiện hành và cách tạo một layer mới với loader riêng khi cần nạp mô-đun động.

## 1. ModuleLayer và class loader

**ModuleLayer** là một tập hợp các mô-đun đã được tạo từ một cấu hình phân giải. Layer giữ các đối tượng **Module** và quan hệ với layer cha. Nó cũng lưu cách các mô-đun trong layer được định nghĩa và gắn với class loader.

Trong ứng dụng Java thông thường, các mô-đun hệ thống được tổ chức trong layer nền tảng. Có thể lấy layer này bằng:

~~~java
ModuleLayer.boot()
~~~

Layer boot chứa các mô-đun được khởi động cùng runtime và các mô-đun đã được đưa vào cấu hình ban đầu.

Một layer mới có thể được tạo phía trên layer boot hoặc một layer khác. Các mô-đun trong layer mới có thể được ánh xạ vào loader riêng, loader dùng chung hoặc loader cha tùy cách định nghĩa layer.

### 1.1. Một mô-đun được gắn với loader nào?

Với một đối tượng **Module**, gọi:

~~~java
ClassLoader loader = module.getClassLoader();
~~~

Phương thức **Module.getClassLoader()** trả về class loader chịu trách nhiệm nạp các lớp của mô-đun đó. Với một số mô-đun nền tảng được nạp bởi bootstrap loader, kết quả có thể là **null**. Vì vậy, không nên giả định mọi mô-đun đều có một đối tượng ClassLoader khác null.

Có thể kiểm tra loader của một lớp cụ thể bằng:

~~~java
ClassLoader loader = SomeType.class.getClassLoader();
Module module = SomeType.class.getModule();
~~~

Kết quả cho biết lớp thực tế được định nghĩa trong mô-đun nào và loader nào đã định nghĩa lớp đó. Đây là cách hữu ích khi chẩn đoán plugin, class identity hoặc lỗi nạp lớp.

### 1.2. Một layer có thể dùng nhiều loader

Một layer không đồng nghĩa với một class loader duy nhất. Khi định nghĩa layer, ứng dụng chọn chính sách ánh xạ loader. Ví dụ:

- **defineModulesWithOneLoader**: các mô-đun mới trong layer dùng chung một loader được tạo cho layer.
- **defineModulesWithManyLoaders**: mỗi mô-đun mới được ánh xạ tới loader riêng.
- **defineModules**: cho phép ứng dụng cung cấp hàm ánh xạ mô-đun tới loader.

Các lựa chọn này ảnh hưởng đến việc nạp lớp, khả năng chia sẻ package và cách cô lập plugin. Chúng không tự thay thế các quy tắc readability, exports hoặc opens của JPMS.

## 2. Phân biệt readability và class loading

Để hiểu ánh xạ mô-đun tới loader, cần tách ba khái niệm.

### 2.1. Readability

Readability trả lời câu hỏi: **mô-đun A có đọc được mô-đun B hay không?**

Một mô-đun thường khai báo quan hệ này qua **requires** trong module descriptor. Quan hệ có thể được truyền tiếp qua **requires transitive** hoặc được bổ sung bằng các API/tùy chọn phù hợp.

Readability ảnh hưởng tới việc biên dịch và truy cập các kiểu công khai từ mô-đun khác. Nó không nói loader nào sẽ định nghĩa lớp.

### 2.2. Export và access

Export xác định package nào của mô-đun được phép truy cập thông thường từ mô-đun khác. Open xác định package nào được mở cho deep reflection.

Một package được export vẫn phải tuân theo các modifier truy cập của Java. Một package được mở cho reflection không tự làm cho các kiểu của package đó có thể import khi biên dịch.

### 2.3. Class loading và class identity

Class loader chịu trách nhiệm tìm và định nghĩa lớp. Trong JVM, danh tính của một lớp được xác định bởi **tên lớp đầy đủ và defining class loader**.

Vì vậy, hai lớp có cùng tên đầy đủ nhưng được định nghĩa bởi hai loader khác nhau là hai kiểu khác nhau. Chúng không thể thay thế nhau trong phép gán hoặc ép kiểu chỉ vì tên lớp giống nhau.

Ví dụ, nếu hai plugin cùng nạp một bản sao của **com.example.api.Task** bằng hai loader riêng, JVM có thể xem chúng là hai kiểu không tương thích. Nếu hai plugin cần trao đổi đối tượng qua cùng một interface, cần bảo đảm interface đó được định nghĩa bởi một loader chung có thể đọc được từ cả hai phía.

## 3. Xem ánh xạ mô-đun và loader bằng API

Các API hiện hành cho phép quan sát layer và module loader trực tiếp.

### 3.1. Lấy layer của một mô-đun

~~~java
Module module = SomeType.class.getModule();
ModuleLayer layer = module.getLayer();
~~~

**Module.getLayer()** trả về layer chứa mô-đun đã được định nghĩa. Một số mô-đun đặc biệt có thể không gắn với một layer thông thường; khi đó cần xử lý kết quả null.

### 3.2. Lấy class loader của mô-đun

~~~java
ClassLoader loader = module.getClassLoader();
~~~

Kết quả có thể null đối với mô-đun được nạp bởi bootstrap loader. Nếu cần in thông tin:

~~~java
String loaderName = loader == null
    ? "bootstrap"
    : loader.getName();
~~~

**ClassLoader.getName()** có từ Java 9. Tên loader có thể null nếu loader không được đặt tên; tên chỉ phục vụ nhận diện/logging, không phải định danh duy nhất.

### 3.3. Duyệt các mô-đun trong layer

~~~java
ModuleLayer layer = ModuleLayer.boot();

layer.modules().stream()
    .sorted(java.util.Comparator.comparing(Module::getName))
    .forEach(module -> {
        ClassLoader loader = module.getClassLoader();
        String loaderName = loader == null
            ? "bootstrap"
            : String.valueOf(loader.getName());

        System.out.println(
            module.getName() + " -> " + loaderName);
    });
~~~

Đoạn code minh họa cách liệt kê mô-đun và tên loader. Các mô-đun hệ thống có thể được phân phối giữa những loader khác nhau; không nên suy ra rằng tất cả mô-đun trong boot layer đều dùng cùng một loader.

### 3.4. Xem loader của một lớp cụ thể

~~~java
Class<?> type = SomeType.class;

System.out.println("class=" + type.getName());
System.out.println("module=" + type.getModule().getName());
System.out.println("loader=" + type.getClassLoader());
~~~

Đây là phép kiểm tra phù hợp khi một lớp không được tìm thấy, bị nạp trùng hoặc bị từ chối ép kiểu. Hãy kiểm tra cả tên lớp, module và defining loader.

## 4. Tạo ModuleLayer mới và chọn cách ánh xạ loader

Quy trình tạo layer động thường gồm các bước:

1. Xác định các mô-đun cần nạp bằng **ModuleFinder**.
2. Lấy configuration của layer cha, thường là **ModuleLayer.boot().configuration()**.
3. Phân giải các mô-đun gốc bằng **Configuration.resolve(...)**.
4. Định nghĩa layer mới bằng một trong các phương thức của **ModuleLayer.defineModules...**.
5. Lấy layer mới và tìm mô-đun/loader cần sử dụng.
6. Tạo hoặc gọi lớp entry point theo cách phù hợp với kiến trúc plugin.

### 4.1. Tìm mô-đun bằng ModuleFinder

**ModuleFinder.of(path...)** tạo finder từ một hoặc nhiều thư mục/JAR chứa mô-đun.

~~~java
ModuleFinder finder = ModuleFinder.of(pluginPath);
~~~

Finder có thể tìm mô-đun theo descriptor trong thư mục mô-đun hoặc modular JAR. Đường dẫn phải trỏ tới vị trí chứa artifact hợp lệ. Với mô-đun phụ thuộc, cần bảo đảm các dependency cũng có thể được tìm thấy qua finder tương ứng hoặc trong configuration cha.

### 4.2. Phân giải cấu hình

~~~java
Configuration parentConfiguration =
    ModuleLayer.boot().configuration();

Configuration configuration =
    parentConfiguration.resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.example.plugin"));
~~~

Trong đó:

- **parentConfiguration** là configuration của layer cha.
- **finder** tìm các mô-đun plugin.
- **ModuleFinder.of()** rỗng được dùng làm finder cho các mô-đun trước khi tìm trong parent configuration theo thứ tự phân giải.
- **Set.of(...)** chỉ định tên mô-đun gốc cần phân giải.

Kết quả là một Configuration đã phân giải dependency graph. Phân giải thành công chưa đồng nghĩa các lớp đã được nạp; bước định nghĩa layer mới thiết lập các mô-đun và loader.

### 4.3. Định nghĩa layer với một loader dùng chung

~~~java
ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithOneLoader(
        configuration,
        List.of(ModuleLayer.boot()),
        ClassLoader.getSystemClassLoader());

ModuleLayer pluginLayer = controller.layer();
~~~

Các mô-đun mới trong layer được ánh xạ tới cùng một loader do API tạo ra với loader cha được cung cấp. Cách này thuận tiện khi các mô-đun plugin cần dùng chung class identity cho các package/type được chia sẻ theo thiết kế.

### 4.4. Định nghĩa layer với nhiều loader

~~~java
ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithManyLoaders(
        configuration,
        List.of(ModuleLayer.boot()),
        ClassLoader.getSystemClassLoader());

ModuleLayer pluginLayer = controller.layer();
~~~

Cách này tạo loader riêng cho từng mô-đun mới. Nó hữu ích khi muốn cô lập việc nạp lớp giữa các mô-đun plugin. Tuy nhiên, các lớp có cùng tên nhưng thuộc hai mô-đun/loader khác nhau có thể không tương thích về kiểu.

### 4.5. Định nghĩa layer bằng hàm ánh xạ loader

Khi cần kiểm soát ánh xạ chi tiết, có thể dùng overload **ModuleLayer.defineModules(...)** nhận hàm ánh xạ:

~~~java
Function<String, ClassLoader> loaderFunction =
    moduleName -> chooseLoaderFor(moduleName);

ModuleLayer.Controller controller =
    ModuleLayer.defineModules(
        configuration,
        List.of(ModuleLayer.boot()),
        loaderFunction);
~~~

Hàm nhận tên mô-đun và trả về loader dùng để định nghĩa mô-đun đó. Các loader được trả về phải đáp ứng yêu cầu về quan hệ delegation và khả năng nạp các lớp mà mô-đun cần. Không nên dùng một hàm ánh xạ tùy ý mà không hiểu rõ class identity và dependency graph.

**Controller** là đối tượng kiểm soát layer vừa định nghĩa. Trong ví dụ cơ bản, chỉ cần lấy **controller.layer()**. Controller còn cung cấp các thao tác điều chỉnh một số quan hệ module graph tại runtime; chỉ sử dụng khi có yêu cầu thiết kế rõ ràng.

## 5. Ví dụ hoàn chỉnh: nạp plugin trong layer riêng

Ví dụ dưới đây có hai mô-đun:

- **com.example.api** định nghĩa interface dùng chung.
- **com.example.plugin** cung cấp implementation.

Ứng dụng host nằm ngoài phần mã plugin và tạo một layer mới để tìm provider. Ví dụ dùng ServiceLoader theo layer để phát hiện implementation.

Cấu trúc thư mục:

~~~text
workspace/
├── api/
│   ├── module-info.java
│   └── com/example/api/Task.java
└── plugin/
    ├── module-info.java
    └── com/example/plugin/UppercaseTask.java
~~~

### 5.1. Mô-đun API

Tệp **api/module-info.java**:

~~~java
module com.example.api {
    exports com.example.api;
}
~~~

Tệp **api/com/example/api/Task.java**:

~~~java
package com.example.api;

public interface Task {
    String execute(String input);
}
~~~

### 5.2. Mô-đun plugin

Tệp **plugin/module-info.java**:

~~~java
module com.example.plugin {
    requires com.example.api;

    provides com.example.api.Task
        with com.example.plugin.UppercaseTask;
}
~~~

Tệp **plugin/com/example/plugin/UppercaseTask.java**:

~~~java
package com.example.plugin;

import com.example.api.Task;

public final class UppercaseTask implements Task {
    public UppercaseTask() {
        System.out.println("plugin-created");
    }

    @Override
    public String execute(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

### 5.3. Host named module tạo layer và nạp provider

Host cũng là một named module và dùng chung đúng một bản API với plugin. Tệp **src/com.example.host/module-info.java**:

~~~java
module com.example.host {
    requires com.example.api;
    uses com.example.api.Task;
}
~~~

Tệp **src/com.example.host/com/example/host/Main.java**:

~~~java
package com.example.host;

import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.ServiceLoader;
import java.util.Set;

import com.example.api.Task;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException("Pass the plugin module path");
        }

        Path pluginPath = Path.of(args[0]);
        ModuleFinder finder = ModuleFinder.of(pluginPath);
        Configuration configuration =
            ModuleLayer.boot().configuration().resolve(
                finder, ModuleFinder.of(), Set.of("com.example.plugin"));

        ModuleLayer.Controller controller =
            ModuleLayer.defineModulesWithOneLoader(
                configuration,
                List.of(ModuleLayer.boot()),
                ClassLoader.getSystemClassLoader());
        ModuleLayer pluginLayer = controller.layer();

        Module pluginModule = pluginLayer.findModule("com.example.plugin")
            .orElseThrow();
        ClassLoader pluginLoader = pluginModule.getClassLoader();

        System.out.println("plugin-module=" + pluginModule.getName());
        System.out.println("plugin-loader=" + String.valueOf(pluginLoader.getName()));

        Task task = ServiceLoader.load(pluginLayer, Task.class)
            .findFirst()
            .orElseThrow(() -> new IllegalStateException("No plugin provider"));
        System.out.println(task.execute("module layer"));
    }
}
~~~

Host cần khai báo **requires com.example.api** để tham chiếu kiểu Task và **uses com.example.api.Task** để ServiceLoader được phép tìm service. Plugin khai báo **requires com.example.api** và **provides ... with ...** như phần 5.2. Cả host lẫn plugin vì vậy dùng cùng một định nghĩa Task; không trộn một Task trên classpath với một Task trong named module vì hai class có thể có cùng tên nhưng không cùng identity.

### 5.4. Biên dịch và chạy với API ở boot layer

Cấu trúc đầy đủ:

~~~text
src/
├── com.example.api/
│   ├── module-info.java
│   └── com/example/api/Task.java
└── com.example.host/
    ├── module-info.java
    └── com/example/host/Main.java

plugin-src/
└── com.example.plugin/
    ├── module-info.java
    └── com/example/plugin/UppercaseTask.java
~~~

Các tệp API và plugin descriptor/implementation được khai báo ở phần 5.1 và 5.2. Biên dịch API cùng host vào output của boot layer:

~~~bash
javac -d out --module-source-path src -m com.example.api,com.example.host
~~~

Biên dịch plugin riêng, dùng API đã có trong module path:

~~~bash
javac --module-path out --module-source-path plugin-src -d plugin-out -m com.example.plugin
~~~

Chạy host trong boot layer và truyền đường dẫn chứa plugin module:

~~~bash
java --module-path out -m com.example.host/com.example.host.Main plugin-out
~~~

Khi resolve cấu hình con, cấu hình boot layer là parent; do đó dependency com.example.api của plugin được tìm thấy từ parent thay vì định nghĩa lại API trong layer con. ModuleFinder.of(pluginPath) chỉ tìm plugin trong đường dẫn được truyền vào. ServiceLoader.load(pluginLayer, Task.class) tìm provider thuộc layer con theo service type của API ở boot layer.

Kết quả trên JDK 24.0.2:

~~~text
plugin-module=com.example.plugin
plugin-loader=null
plugin-created
MODULE LAYER
~~~

ClassLoader.getName() có thể trả về null; vì vậy ví dụ dùng String.valueOf và không giả định mọi loader đều có tên. Dòng plugin-created xuất hiện khi ServiceLoader khởi tạo provider, không phải khi ModuleLayer được tạo.

## 6. Một số chiến lược ánh xạ loader

| Chiến lược | Ánh xạ | Khi phù hợp |
|---|---|---|
| One loader | Nhiều mô-đun dùng chung một loader | Các mô-đun plugin cần chia sẻ class identity và package/API theo thiết kế |
| Many loaders | Mỗi mô-đun có loader riêng | Muốn tách biệt quá trình nạp lớp giữa các mô-đun |
| Custom mapping | Hàm ánh xạ chọn loader cho từng mô-đun | Cần tích hợp với loader có sẵn hoặc chính sách nạp lớp riêng |

### 6.1. One loader

Các mô-đun trong layer có thể nhìn thấy các lớp do cùng loader định nghĩa theo quy tắc module access. Việc dùng chung loader không làm tất cả package tự động export. Module descriptor vẫn quyết định package nào được truy cập.

### 6.2. Many loaders

Mỗi mô-đun có defining loader riêng. Điều này giúp phân tách class space, nhưng có thể làm phát sinh lỗi ép kiểu nếu hai mô-đun định nghĩa hai bản sao của một API mà lẽ ra phải được chia sẻ.

Một nguyên tắc hữu ích là đặt các interface/DTO dùng chung trong mô-đun API ở layer cha. Plugin chỉ phụ thuộc vào API đó; layer con có thể tạo implementation riêng mà vẫn trao đổi đối tượng qua kiểu API chung.

### 6.3. Custom mapping

Custom mapping phù hợp khi ứng dụng đã có loader quản lý plugin hoặc cần dùng loader riêng theo nhóm. Hàm ánh xạ phải nhất quán với module graph và delegation. Một loader tùy chỉnh không thể tự bỏ qua quy tắc readability/export của JPMS.

## 7. Lỗi thường gặp khi ánh xạ mô-đun tới loader

### 7.1. ClassCastException dù tên lớp giống nhau

Nguyên nhân thường là cùng tên lớp được định nghĩa bởi hai loader khác nhau. Kiểm tra:

~~~java
System.out.println(typeA.getName());
System.out.println(typeA.getClassLoader());
System.out.println(typeB.getClassLoader());
System.out.println(typeA == typeB);
~~~

Nếu hai defining loader khác nhau, hai Class object không phải cùng một kiểu. Chia sẻ API qua layer cha hoặc một loader chung.

### 7.2. NoClassDefFoundError hoặc ClassNotFoundException

Kiểm tra các khả năng:

- Mô-đun chứa dependency chưa được tìm thấy trong finder hoặc parent configuration.
- Mô-đun chưa được phân giải vào layer.
- Loader được ánh xạ không thể nạp lớp phụ thuộc theo delegation.
- Tên mô-đun hoặc package bị ghi sai.
- Lớp không nằm trong package/module artifact dự kiến.

Dùng **ModuleFinder**, **Configuration.modules()**, **ModuleLayer.modules()** và **Module.getClassLoader()** để kiểm tra từng bước.

### 7.3. Layer tạo thành công nhưng không tìm thấy service

Layer được định nghĩa không tự bảo đảm provider sẽ được tìm thấy. Kiểm tra:

- Mô-đun consumer khai báo **uses** cho service type.
- Mô-đun provider khai báo **provides ... with ...** đúng service type.
- Provider module thực sự được phân giải và nằm trong layer.
- Dùng đúng overload **ServiceLoader.load(layer, service)** khi tìm provider trong layer tùy chỉnh.
- Service type được chia sẻ qua đúng module/class loader để provider và consumer cùng tham chiếu một kiểu.

### 7.4. Lẫn lộn module path và classpath

Mô-đun trên module path có descriptor và tham gia module graph. Mã trên classpath thuộc unnamed module. Một thư viện được đặt nhầm vào classpath có thể không được phân giải như một named module và không thể được tìm bằng tên module dự kiến.

Hãy kiểm tra cách đóng gói artifact, vị trí module path và lệnh khởi chạy thực tế.

### 7.5. Nghĩ rằng mỗi ModuleLayer luôn tạo loader mới

Layer có thể được định nghĩa với loader do ứng dụng cung cấp hoặc loader cha theo chính sách ánh xạ. Vì vậy, không nên suy ra số lượng loader chỉ từ số lượng layer. Hãy truy vấn **Module.getClassLoader()** của từng mô-đun để xác định ánh xạ thực tế.

## 8. Lưu ý về vòng đời và tài nguyên

ModuleLayer không phải cơ chế tự động dỡ bỏ plugin. JVM không cung cấp một thao tác đơn giản để unload một layer theo tên. Việc lớp và loader có thể được thu hồi phụ thuộc vào khả năng không còn tham chiếu mạnh tới loader, layer, lớp, instance, thread, thread context class loader, callback hoặc tài nguyên liên quan.

Nếu xây dựng hệ thống plugin có thể thay thế phiên bản, cần thiết kế vòng đời rõ ràng:

- Dừng tiếp nhận công việc mới.
- Đóng service/connection/thread do plugin tạo.
- Gỡ listener, callback và thread context class loader tham chiếu tới plugin.
- Xóa các tham chiếu tới instance, Class, Module, ModuleLayer và ClassLoader khi không còn cần.
- Chỉ kỳ vọng garbage collector thu hồi loader khi không còn đường tham chiếu mạnh giữ nó.

Việc tạo layer riêng có thể hỗ trợ cô lập nạp lớp, nhưng không tự tạo sandbox bảo mật. Mã plugin vẫn chạy trong cùng tiến trình và có thể dùng các quyền mà tiến trình được cấp. Với plugin không đáng tin cậy, cần ranh giới tiến trình hoặc cơ chế cô lập ở cấp hệ điều hành.

## 9. Checklist thiết kế ánh xạ mô-đun tới loader

- Xác định mô-đun API nào phải được chia sẻ giữa host và plugin.
- Đặt API dùng chung ở layer cha hoặc bảo đảm cùng defining loader.
- Phân giải dependency trước khi định nghĩa layer.
- Chọn one loader, many loaders hoặc custom mapping theo yêu cầu class identity.
- Kiểm tra loader thực tế bằng **Module.getClassLoader()**.
- Kiểm tra layer bằng **Module.getLayer()** và **ModuleLayer.modules()**.
- Phân biệt readability, exports/opens và class loading.
- Dùng **ServiceLoader.load(layer, service)** khi tìm provider trong layer động.
- Kiểm tra lỗi trùng tên lớp bằng defining class loader.
- Quản lý lifecycle plugin và loại bỏ tham chiếu khi muốn giải phóng loader.
- Không coi ModuleLayer là sandbox bảo mật.

**Nguyên tắc thiết kế:** ánh xạ mô-đun tới class loader là quyết định về class identity và cách tổ chức không gian lớp. Dùng loader chung khi các mô-đun cần chia sẻ cùng kiểu API; dùng loader riêng khi cần phân tách class space; dùng custom mapping khi có chính sách nạp lớp cụ thể. Sau khi định nghĩa layer, hãy kiểm tra loader thực tế và module graph bằng API thay vì suy đoán từ số lượng mô-đun hoặc layer.