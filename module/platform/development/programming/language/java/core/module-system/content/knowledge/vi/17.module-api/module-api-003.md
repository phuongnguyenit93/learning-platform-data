# ModuleLayer và configuration API

Java Platform Module System (JPMS) không chỉ mô tả dependency trong module-info.java. Ở runtime, Java còn cần xác định tập module nào tham gia vào ứng dụng, phân giải dependency giữa chúng và định nghĩa các module đó trong JVM. Hai API trung tâm cho công việc này là **Configuration** và **ModuleLayer**.

Configuration biểu diễn kết quả phân giải module: module nào được chọn, dependency nào được đáp ứng và quan hệ đọc giữa chúng. ModuleLayer đưa cấu hình đó vào runtime, gắn module với class loader và tạo quan hệ cha-con giữa các nhóm module. Các API này là nền tảng để xây dựng ứng dụng modular, nạp plugin động và tổ chức nhiều nhóm module trong cùng một tiến trình.

## 1. Phân biệt Configuration và ModuleLayer

Hai khái niệm thường xuất hiện cùng nhau nhưng giải quyết hai việc khác nhau:

- **Configuration** mô tả module graph đã được phân giải. Nó chứa các ResolvedModule và quan hệ đọc giữa các module trong cấu hình.
- **ModuleLayer** là một tập module đã được định nghĩa trong runtime. Mỗi module runtime được gắn với class loader theo chiến lược định nghĩa layer.
- **ClassLoader** tìm bytecode và định nghĩa class khi ứng dụng yêu cầu. ModuleLayer không đồng nghĩa với việc mọi class trong các module của layer đã được nạp.

Luồng xử lý khái quát:

~~~text
Module path / vị trí plugin
          |
          v
ModuleFinder tìm module
          |
          v
Configuration.resolve(...)
          |
          v
Module graph đã phân giải
          |
          v
ModuleLayer.defineModules(...)
          |
          v
Module runtime + ClassLoader
          |
          v
Class được nạp khi có yêu cầu
~~~

Một module có thể xuất hiện trong Configuration mà chưa được định nghĩa vào một ModuleLayer mới. Sau khi layer được tạo, module đã có đối tượng Module trong runtime, nhưng các class bên trong vẫn thường được nạp theo nhu cầu.

Do đó, khi debug, cần xác định đang quan sát cấu hình đã phân giải, module runtime hay class đã được nạp. Ba trạng thái này không thể thay thế cho nhau.

## 2. ModuleFinder cung cấp đầu vào cho quá trình phân giải

**ModuleFinder** tìm module descriptor từ các vị trí được chỉ định. Nó thường được dùng để tìm modular JAR, exploded module hoặc automatic module trên module path.

Ví dụ:

~~~java
import java.lang.module.ModuleFinder;
import java.nio.file.Path;

ModuleFinder pluginFinder =
    ModuleFinder.of(Path.of("plugins"));
~~~

Lệnh trên tạo finder tìm module trong thư mục plugins. Nếu thư mục chứa các JAR modular, finder đọc descriptor của chúng để xác định tên module và các directive. JAR không có module-info.class đặt trên module path có thể được nhận diện như automatic module theo quy tắc JPMS.

Một số factory method thường dùng:

| API | Mục đích |
| --- | --- |
| ModuleFinder.of(Path...) | Tìm module trong các thư mục hoặc JAR được chỉ định |
| ModuleFinder.ofSystem() | Tìm các module thuộc runtime image của JDK |
| ModuleFinder.of() | Tạo finder rỗng, thường dùng làm một trong các đầu vào của resolve |
| ModuleFinder.compose(...) | Kết hợp nhiều finder thành một finder |

Có thể tìm một module theo tên và đọc descriptor:

~~~java
var reference =
    pluginFinder.find("com.example.plugin");

if (reference.isPresent()) {
    System.out.println(reference.get().descriptor().name());
    System.out.println(reference.get().location());
}
~~~

ModuleFinder chỉ giúp tìm module và metadata. Nó chưa tạo module runtime, chưa nạp class implementation và chưa chạy code trong module.

## 3. Configuration biểu diễn kết quả module resolution

**Configuration** là kết quả của quá trình phân giải các module gốc cùng dependency cần thiết. Nó chứa tập ResolvedModule, mỗi phần tử đại diện cho một module đã được phân giải trong cấu hình.

Khi khởi chạy ứng dụng modular thông thường, Java launcher thực hiện resolution dựa trên module path, các module gốc được chọn và các module nền tảng. Khi ứng dụng cần nạp plugin ở runtime, có thể gọi API Configuration trực tiếp.

Ví dụ:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleLayer parent = ModuleLayer.boot();

ModuleFinder finder =
    ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    parent.configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.example.plugin")
    );
~~~

Các tham số của resolve có ý nghĩa:

- **finder** là nơi tìm các module mới cần phân giải trước khi xét các module đã có trong parent configuration.
- **ModuleFinder.of()** là finder rỗng cho vị trí tìm kiếm bổ sung sau parent configuration trong overload này.
- **Set.of("com.example.plugin")** chỉ định module gốc mà ứng dụng muốn đưa vào cấu hình.
- **parent.configuration()** cung cấp cấu hình cha, thường là cấu hình của boot layer.

Resolution bắt đầu từ module gốc. JPMS tiếp tục tìm các module mà chúng yêu cầu trực tiếp hoặc gián tiếp, kiểm tra dependency và xây dựng quan hệ đọc. Các module không nằm trong tập gốc và cũng không phải dependency cần thiết sẽ không tự động được đưa vào cấu hình chỉ vì chúng có mặt trong thư mục plugins.

Có thể xem các module trong kết quả:

~~~java
configuration.modules().forEach(resolved -> {
    System.out.println(resolved.name());
});
~~~

Danh sách này thể hiện module thuộc chính Configuration hiện tại. Các module đã có ở cấu hình cha được tham chiếu thông qua quan hệ parent, không nhất thiết xuất hiện như module mới của configuration con.

## 4. ResolvedModule và thông tin dependency

**ResolvedModule** đại diện cho một module đã được chọn trong Configuration. Nó cho phép truy cập tên, descriptor, ModuleReference và các dependency đã phân giải.

Ví dụ:

~~~java
configuration.modules().forEach(resolved -> {
    System.out.println("Name: " + resolved.name());
    System.out.println("Descriptor: " + resolved.reference().descriptor());
    System.out.println("Dependencies: " + resolved.reads());
});
~~~

Các thông tin quan trọng:

- **name()** trả về tên module.
- **reference()** trả về ModuleReference của module được tìm thấy.
- **configuration()** cho biết Configuration mà ResolvedModule thuộc về.
- **reads()** cho biết các module mà module này đọc trong cấu hình đã phân giải.

ResolvedModule vẫn là thông tin của quá trình resolution. Nó không phải đối tượng Module runtime và không cung cấp class loader để nạp class.

Có thể kiểm tra dependency theo tên bằng cách duyệt các phần tử trong reads(). Khi một dependency không được tìm thấy hoặc có ràng buộc module không thể thỏa mãn, resolution thất bại trước khi layer được định nghĩa.

## 5. resolve và resolveAndBind

Configuration cung cấp hai cách phân giải thường gặp:

- **resolve(...)** tìm các module gốc cùng dependency được khai báo bằng requires.
- **resolveAndBind(...)** thực hiện resolution kết hợp service binding để tìm thêm module provider phù hợp với các service được sử dụng trong module graph.

Ví dụ dùng service binding:

~~~java
Configuration configuration =
    parent.configuration().resolveAndBind(
        pluginFinder,
        ModuleFinder.of(),
        Set.of("com.example.app")
    );
~~~

Giả sử module ứng dụng khai báo:

~~~java
module com.example.app {
    requires com.example.plugin.api;
    uses com.example.plugin.api.PluginService;
}
~~~

Và module plugin khai báo:

~~~java
module com.example.plugin.csv {
    requires com.example.plugin.api;

    provides com.example.plugin.api.PluginService
        with com.example.plugin.csv.CsvPlugin;
}
~~~

Khi dùng resolveAndBind, module system có thể tìm provider module cho service mà module graph sử dụng, dựa trên các module có thể tìm thấy trong finder và các cấu hình cha. Các dependency của provider cũng được đưa vào quá trình phân giải.

Service binding chỉ quyết định module provider nào tham gia vào cấu hình. Nó không có nghĩa constructor của provider đã chạy hoặc tất cả implementation class đã được nạp. Việc lấy và sử dụng provider vẫn thường được thực hiện qua ServiceLoader ở runtime.

Chọn resolve khi chỉ cần các module gốc và dependency requires. Chọn resolveAndBind khi muốn module system tự mở rộng cấu hình bằng các module cung cấp service phù hợp.

## 6. Nhiều parent Configuration

Một Configuration có thể được phân giải dựa trên nhiều cấu hình cha. Trường hợp này hữu ích khi ứng dụng có các nhóm module độc lập đã được phân giải ở những layer cha khác nhau.

API static của Configuration nhận danh sách parent configuration:

~~~java
Configuration configuration =
    Configuration.resolve(
        finderBefore,
        List.of(parentA.configuration(),
                parentB.configuration()),
        finderAfter,
        Set.of("com.example.plugin")
    );
~~~

Trong đó:

- **finderBefore** được dùng để tìm module mới trước khi xét các parent configuration.
- Danh sách parent cung cấp các module đã có và quan hệ đọc của chúng.
- **finderAfter** là nguồn tìm kiếm bổ sung sau parent configurations.
- Tập roots xác định module gốc cần phân giải.

Khi định nghĩa ModuleLayer tương ứng, cần truyền các parent layer phù hợp với danh sách parent configuration. Cấu trúc cha của layer phải nhất quán với cấu hình đã dùng để resolution; không thể tùy tiện ghép một Configuration với các layer không tương ứng.

Với ứng dụng thông thường, một parent là boot layer thường đủ. Chỉ dùng nhiều parent khi kiến trúc thực sự có nhiều nhóm module cha cần chia sẻ.

## 7. ModuleLayer là gì?

**ModuleLayer** biểu diễn một tập module đã được định nghĩa trong JVM. Nó kết hợp Configuration đã phân giải với chiến lược class loader và các layer cha.

Các layer tạo thành một cấu trúc phân cấp:

~~~text
Boot ModuleLayer
       |
       v
Application / Plugin Layer
       |
       v
Child Plugin Layer
~~~

Một layer có thể chứa module ứng dụng, module plugin hoặc các module được nạp động. Layer con có thể đọc các module ở layer cha theo module graph đã phân giải.

Các API thường dùng:

| API | Vai trò |
| --- | --- |
| ModuleLayer.boot() | Lấy boot layer của ứng dụng |
| ModuleLayer.empty() | Lấy layer rỗng, thường dùng làm điểm bắt đầu cho cấu hình độc lập |
| parents() | Trả về các parent layer trực tiếp |
| modules() | Trả về các module được định nghĩa trực tiếp trong layer |
| configuration() | Lấy Configuration đã dùng để tạo layer |
| findModule(name) | Tìm module theo tên trong layer hierarchy |
| findLoader(name) | Tìm class loader gắn với module trong layer hierarchy |

Ví dụ quan sát boot layer:

~~~java
ModuleLayer boot = ModuleLayer.boot();

System.out.println("Module count: " + boot.modules().size());
System.out.println("Parents: " + boot.parents());

boot.modules().forEach(module -> {
    System.out.println(module.getName());
});
~~~

modules() cho biết module thuộc trực tiếp layer đang xét. Nếu muốn tìm module có thể nhìn thấy qua cấu trúc cha, dùng findModule(name) theo tên module.

## 8. Định nghĩa layer bằng một ClassLoader chung

Sau khi Configuration đã phân giải thành công, ứng dụng có thể định nghĩa các module vào một layer mới.

Cách đơn giản nhất cho nhóm plugin là **defineModulesWithOneLoader**:

~~~java
ModuleLayer.Controller controller =
    parent.defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer pluginLayer = controller.layer();
~~~

API này tạo một class loader mới để định nghĩa các module trong configuration. Các module mới trong layer dùng chung loader đó; loader được truyền vào làm parent để hỗ trợ delegation.

Phù hợp khi:

- Các module plugin cần chia sẻ class trong cùng nhóm.
- Các module có quan hệ dependency tương đối chặt.
- Không cần cô lập loader riêng cho từng module.
- Muốn đơn giản hóa việc chia sẻ API và kiểu dữ liệu giữa các plugin.

Lưu ý, tham số **parentLoader** là parent của loader mới được tạo. Nó không có nghĩa các module plugin được định nghĩa trực tiếp bởi system class loader.

Sau khi tạo layer, có thể kiểm tra:

~~~java
System.out.println(
    pluginLayer.findModule("com.example.plugin").isPresent()
);

ClassLoader pluginLoader =
    pluginLayer.findLoader("com.example.plugin");

System.out.println(pluginLoader);
~~~

Module đã được định nghĩa trong layer khi findModule tìm thấy nó. findLoader trả về loader được gắn với module; thao tác này không nạp toàn bộ class trong module.

## 9. Định nghĩa layer bằng nhiều ClassLoader

Nếu muốn mỗi module mới có một loader riêng, dùng **defineModulesWithManyLoaders**:

~~~java
ModuleLayer.Controller controller =
    parent.defineModulesWithManyLoaders(
        configuration,
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer pluginLayer = controller.layer();
~~~

API tạo một class loader cho mỗi module trong configuration. Các loader được thiết lập quan hệ parent phù hợp để hỗ trợ delegation và module readability.

Cách này hữu ích khi các module cần phạm vi nạp class riêng, ví dụ các plugin có dependency nội bộ khác nhau. Tuy nhiên, cần thiết kế rõ API chia sẻ giữa chúng. Nếu mỗi plugin đóng gói một bản sao của cùng interface, các class cùng tên nhưng do loader khác nhau định nghĩa vẫn là các kiểu khác nhau trong JVM.

So sánh hai cách:

| Tiêu chí | One loader | Many loaders |
| --- | --- | --- |
| Số loader mới | Một loader dùng chung cho module trong configuration | Một loader cho mỗi module |
| Chia sẻ class trong layer | Thuận tiện hơn khi dùng chung loader | Phải dựa vào quan hệ module và delegation |
| Cô lập nạp class | Ít tách biệt hơn | Tách theo module rõ hơn |
| Độ phức tạp | Thường đơn giản hơn | Cần quản lý class identity và API chia sẻ kỹ hơn |
| Phù hợp | Nhóm module phối hợp chặt | Các module cần phạm vi loader riêng |

Không có lựa chọn nào tự động an toàn hơn. Chọn chiến lược dựa trên dependency, cách chia sẻ API và vòng đời plugin của ứng dụng.

## 10. Tự ánh xạ module tới ClassLoader

Khi one-loader hoặc many-loaders không đáp ứng được kiến trúc, có thể dùng **defineModules** với hàm ánh xạ tên module sang class loader.

~~~java
ModuleLayer.Controller controller =
    parent.defineModules(
        configuration,
        moduleName -> loaderFor(moduleName)
    );

ModuleLayer pluginLayer = controller.layer();
~~~

Hàm loaderFor là logic của ứng dụng, phải trả về ClassLoader phù hợp cho từng tên module được định nghĩa. Cách này cho phép nhóm module vào các loader theo chính sách riêng.

Có thể dùng overload static để cung cấp nhiều parent layer:

~~~java
ModuleLayer.Controller controller =
    ModuleLayer.defineModules(
        configuration,
        List.of(parent),
        moduleName -> loaderFor(moduleName)
    );
~~~

Khi tự ánh xạ loader, cần bảo đảm:

- Mỗi module trong configuration được gắn với loader phù hợp.
- Các module cần chia sẻ API dùng chung một định nghĩa class API.
- Parent loader hỗ trợ tìm các dependency đã có ở layer cha.
- Không tạo hai định nghĩa class API không tương thích giữa các plugin.
- Vòng đời loader được quản lý cùng vòng đời plugin.

API này cung cấp quyền kiểm soát cao hơn nhưng cũng đòi hỏi hiểu rõ delegation và class identity. Chỉ nên dùng khi có yêu cầu cụ thể mà các chiến lược loader dựng sẵn không đáp ứng.

## 11. ModuleLayer.Controller và quyền điều chỉnh module runtime

Các API defineModules trả về **ModuleLayer.Controller**. Controller cung cấp tham chiếu tới layer vừa tạo và một số thao tác điều chỉnh quan hệ truy cập ở runtime.

Các thao tác chính gồm:

- **layer()** trả về ModuleLayer vừa được định nghĩa.
- **addReads(source, target)** thêm quan hệ đọc từ module nguồn tới module đích.
- **addExports(source, packageName, target)** export package của module nguồn tới module đích.
- **addOpens(source, packageName, target)** mở package của module nguồn cho deep reflection từ module đích.

Ví dụ:

~~~java
ModuleLayer.Controller controller =
    parent.defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer pluginLayer = controller.layer();

Module source =
    pluginLayer.findModule("com.example.plugin").orElseThrow();

Module target =
    parent.findModule("com.example.plugin.api").orElseThrow();

controller.addReads(source, target);
~~~

Trong thiết kế đúng, dependency requires nên được khai báo trong module-info.java. Controller phù hợp cho các tình huống runtime cần bổ sung quan hệ đọc, export hoặc open sau khi layer đã được định nghĩa.

Controller là đối tượng có quyền điều chỉnh các module thuộc layer được tạo. Chỉ truyền nó cho thành phần thực sự cần quyền này; không nên phát tán quyền thay đổi module graph một cách tùy tiện.

## 12. Ví dụ hoàn chỉnh: nạp plugin bằng ModuleLayer

Giả sử ứng dụng có module API nằm trong boot layer:

~~~java
module com.example.plugin.api {
    exports com.example.plugin.api;
}
~~~

Interface service:

~~~java
package com.example.plugin.api;

public interface PluginService {
    String name();
    void execute();
}
~~~

Module plugin được đóng gói thành JAR trong thư mục plugins:

~~~java
module com.example.plugin.csv {
    requires com.example.plugin.api;

    provides com.example.plugin.api.PluginService
        with com.example.plugin.csv.CsvPlugin;
}
~~~

Ứng dụng đã khởi chạy và muốn nạp plugin:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.ServiceLoader;
import java.util.Set;

ModuleLayer parent = ModuleLayer.boot();

ModuleFinder finder =
    ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    parent.configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.example.plugin.csv")
    );

ModuleLayer.Controller controller =
    parent.defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer pluginLayer = controller.layer();

ServiceLoader<PluginService> services =
    ServiceLoader.load(pluginLayer, PluginService.class);

for (PluginService service : services) {
    System.out.println(service.name());
    service.execute();
}
~~~

Quy trình hoạt động:

1. Module API đã có trong parent layer để ứng dụng và plugin cùng sử dụng một định nghĩa interface.
2. ModuleFinder tìm JAR plugin trong thư mục plugins.
3. Configuration.resolve phân giải module plugin và dependency của nó.
4. defineModulesWithOneLoader tạo layer con và loader cho module mới.
5. ServiceLoader.load(pluginLayer, PluginService.class) tìm provider trong layer được chỉ định và các layer cha.
6. Khi duyệt và sử dụng provider, implementation class được nạp và khởi tạo theo nhu cầu.

Ví dụ giả định plugin có descriptor hợp lệ, dependency API đã có ở parent layer và module gốc đúng tên. Trong ứng dụng thực tế, cần xử lý trường hợp thư mục plugin thiếu, module không tìm thấy, dependency không tương thích hoặc provider khởi tạo thất bại.

## 13. Vòng đời và khả năng quản lý plugin

ModuleLayer không cung cấp API unload một module riêng lẻ. Việc bỏ tham chiếu tới layer và các class loader liên quan có thể cho phép garbage collector thu hồi chúng khi không còn tham chiếu sống, nhưng điều đó chỉ xảy ra khi mọi tham chiếu tới class, instance, thread, callback, static state và loader đã được giải phóng.

Một plugin có thể giữ tham chiếu từ:

- Thread hoặc executor còn chạy.
- Thread context class loader.
- Listener hoặc callback đã đăng ký vào đối tượng sống lâu hơn.
- Static collection hoặc cache ở parent layer.
- Instance plugin được giữ trong registry của ứng dụng.

Nếu các tham chiếu này còn tồn tại, class loader và class của plugin có thể không được thu hồi.

Vì vậy, khi thiết kế vòng đời plugin, cần có bước đóng tài nguyên, dừng thread, hủy đăng ký listener, xóa registry và giải phóng tham chiếu. Không nên xem việc tạo ModuleLayer mới là cơ chế tự động unload plugin cũ.

ModuleLayer cũng không phải sandbox bảo mật. Module encapsulation và class loader hỗ trợ quản lý dependency, khả năng đọc và phạm vi nạp class, nhưng không cô lập mã không tin cậy khỏi tiến trình hoặc tài nguyên hệ điều hành.

## 14. Lỗi thường gặp khi dùng Configuration và ModuleLayer

**FindException**

ModuleFinder không tìm được module, descriptor không hợp lệ hoặc vị trí module path không đúng. Kiểm tra thư mục, tên module và nội dung JAR bằng jar --describe-module.

**ResolutionException**

Một dependency requires không tìm thấy, module graph có xung đột hoặc các ràng buộc resolution không thể thỏa mãn. Kiểm tra module gốc, dependency và các parent Configuration.

**LayerInstantiationException**

Configuration đã phân giải nhưng không thể định nghĩa layer theo chiến lược loader được chọn. Kiểm tra quan hệ package, module trùng hoặc vấn đề ánh xạ class loader.

**Module đã có trong Configuration nhưng không tìm thấy class**

Configuration chỉ mô tả module graph. Kiểm tra ModuleLayer đã được tạo chưa, loader gắn với module và JAR có chứa class cần dùng không.

**ServiceLoader không tìm thấy provider**

Kiểm tra module provider có provides đúng service, module consumer có uses, provider có tham gia cấu hình và ServiceLoader có dùng đúng layer hay không. Nếu cần tìm provider tự động trong resolution, xem xét resolveAndBind.

**ClassCastException giữa các plugin**

Có thể cùng một API bị định nghĩa bởi nhiều loader. Đặt API dùng chung trong parent layer và để plugin requires module API đó.

**Plugin không được thu hồi sau khi bỏ layer**

Tìm các tham chiếu còn sống tới instance, class, thread, context class loader, listener hoặc static cache. Chỉ bỏ biến tham chiếu tới ModuleLayer chưa đủ để bảo đảm loader có thể được thu hồi.

## 15. Công cụ quan sát module và layer

Dùng jar để kiểm tra descriptor của plugin:

~~~bash
jar --describe-module --file plugins/com.example.plugin.jar
~~~

Dùng Java launcher để xem module resolution của ứng dụng:

~~~bash
java --show-module-resolution \
     --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

Trong code, có thể in thông tin layer:

~~~java
System.out.println("Layer: " + pluginLayer);
System.out.println("Configuration: " + pluginLayer.configuration());
System.out.println("Parents: " + pluginLayer.parents());

pluginLayer.modules().forEach(module -> {
    System.out.println("Module: " + module.getName());
    System.out.println("Loader: " + module.getClassLoader());
});
~~~

Các nguồn quan sát có vai trò riêng:

- **jar --describe-module** cho biết descriptor của artifact.
- **Configuration.modules()** cho biết module đã tham gia cấu hình phân giải.
- **ModuleLayer.modules()** cho biết module được định nghĩa trực tiếp trong layer.
- **ModuleLayer.findModule()** giúp tìm module theo tên trong layer hierarchy.
- **ModuleLayer.findLoader()** cho biết class loader gắn với module.
- **-Xlog:class+load=info** cho biết class nào thực sự được nạp.

Khi cần xác định module không được tìm thấy, lỗi resolution hay lỗi class loading, hãy đối chiếu kết quả ở đúng giai đoạn.

## 16. Nguyên tắc thiết kế

- Dùng ModuleFinder để xác định nguồn module và Configuration để phân giải module graph.
- Chọn module gốc rõ ràng; module có mặt trong finder không tự động được đưa vào cấu hình.
- Dùng resolve cho dependency requires và resolveAndBind khi cần tìm provider theo service binding.
- Dùng boot layer làm parent khi plugin cần chia sẻ module API đã có trong ứng dụng.
- Dùng defineModulesWithOneLoader cho nhóm module cần chia sẻ loader.
- Dùng defineModulesWithManyLoaders khi cần loader riêng theo module.
- Chỉ dùng hàm ánh xạ loader tùy chỉnh khi có yêu cầu kiến trúc cụ thể.
- Giữ API dùng chung ở parent layer để tránh class identity xung đột.
- Dùng Controller có chủ đích để điều chỉnh reads, exports hoặc opens tại runtime.
- Quản lý thread, listener, cache và tham chiếu để plugin có thể kết thúc vòng đời.
- Không coi ModuleLayer là sandbox hoặc cơ chế unload tự động.

Khi hiểu Configuration, ResolvedModule, ModuleLayer và Controller, bạn có thể kiểm soát quá trình phân giải dependency, tạo layer runtime và nạp plugin theo cách có cấu trúc. Đây là nhóm API cốt lõi để xây dựng ứng dụng modular có khả năng mở rộng trong khi vẫn giữ module graph, class loader và quyền truy cập ở trạng thái có thể quan sát và quản lý.
