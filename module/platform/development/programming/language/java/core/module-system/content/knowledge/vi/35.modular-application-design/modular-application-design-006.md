# Chọn layer khi cần plugin hoặc isolation

Java Module System cho phép một ứng dụng tạo nhiều ModuleLayer trong cùng một JVM. Mỗi layer chứa một cấu hình module đã được resolve và có quan hệ cha với một hoặc nhiều layer khác. Đây là nền tảng hữu ích khi ứng dụng cần nạp plugin động, quản lý nhiều nhóm module hoặc giới hạn phạm vi nhìn thấy provider.

Không phải ứng dụng nào cũng cần tạo layer riêng. Nếu tất cả module được xác định cố định khi khởi động, một module graph trong boot layer hoặc một module layer duy nhất thường đơn giản hơn. Hãy tạo layer mới khi có nhu cầu thực tế về vòng đời plugin, tập module có thể thay đổi, nhiều phiên bản plugin hoặc phạm vi service riêng.

## 1. ModuleLayer đại diện cho điều gì?

ModuleLayer là một tập hợp các module đã được định nghĩa trong runtime, cùng với quan hệ tới các layer cha. Một layer được tạo từ Configuration đã resolve và một hoặc nhiều parent layer.

Các thành phần liên quan:

| Thành phần | Vai trò |
|---|---|
| ModuleFinder | Tìm module từ module path, runtime image hoặc nguồn module khác |
| ModuleDescriptor | Mô tả tên module, requires, exports, opens, uses và provides |
| Configuration | Kết quả resolve module graph, xác định các module cần có mặt và dependency |
| ModuleLayer | Chứa các module đã được định nghĩa và quan hệ cha-con giữa các layer |
| ModuleLayer.Controller | Đối tượng điều khiển layer mới, có thể dùng để điều chỉnh một số quan hệ module trong runtime |
| ClassLoader | Nạp class của các module theo cách định nghĩa layer |

Luồng tạo layer thường gặp:

~~~text
Plugin directory
      |
      v
ModuleFinder
      |
      v
Configuration.resolve(...)
      |
      v
ModuleLayer.defineModulesWithOneLoader(...)
      |
      v
ModuleLayer child
      |
      v
ServiceLoader.load(childLayer, Service.class)
~~~

Configuration là kết quả resolve, còn ModuleLayer là môi trường runtime nơi các module trong configuration được định nghĩa. Chỉ tìm thấy một JAR bằng ModuleFinder chưa có nghĩa module đó đã được nạp vào một layer.

## 2. Khi nào nên tạo layer riêng?

Các tình huống thường phù hợp:

- **Plugin được cài thêm khi ứng dụng đã chạy:** ứng dụng có thể tìm module trong thư mục plugin và tạo layer mới cho plugin.
- **Nhiều nhóm plugin độc lập:** mỗi nhóm có thể được đặt trong một layer con riêng để kiểm soát module nào được nhìn thấy.
- **Cần phiên bản dependency riêng:** hai plugin có thể dùng các module dependency khác nhau nếu module graph và class loader được thiết kế phù hợp.
- **Cần phạm vi ServiceLoader cụ thể:** ứng dụng có thể tìm provider trong một layer và các layer cha của nó.
- **Cần ranh giới triển khai:** module plugin được resolve và khởi tạo theo thời điểm hoặc cấu hình riêng.

Không nên tạo layer chỉ để chia package cho đẹp. Nếu các module luôn được nạp cùng nhau, có cùng vòng đời và không cần phạm vi discovery riêng, một layer duy nhất thường dễ vận hành hơn.

## 3. Kiến trúc host và plugin

Một thiết kế plugin điển hình đặt service API trong layer cha. Host và plugin cùng tham chiếu tới đúng một định nghĩa service interface. Plugin implementation nằm trong layer con.

~~~text
Boot layer
|-- com.example.plugin.api
|      exports com.example.plugin.api
|
|-- com.example.host
       requires com.example.plugin.api
       uses com.example.plugin.api.Plugin

Child layer A
|-- com.example.audit.plugin
       requires com.example.plugin.api
       provides Plugin with AuditPlugin

Child layer B
|-- com.example.export.plugin
       requires com.example.plugin.api
       provides Plugin with ExportPlugin
~~~

Host chỉ biết contract Plugin. Nó không cần import AuditPlugin hoặc ExportPlugin. Mỗi plugin được tìm và nạp vào layer phù hợp.

Service API:

~~~java
package com.example.plugin.api;

public interface Plugin {
    String name();

    void start();
}
~~~

Module API:

~~~java
module com.example.plugin.api {
    exports com.example.plugin.api;
}
~~~

Module host:

~~~java
module com.example.host {
    requires com.example.plugin.api;

    uses com.example.plugin.api.Plugin;
}
~~~

Module plugin:

~~~java
module com.example.audit.plugin {
    requires com.example.plugin.api;

    provides com.example.plugin.api.Plugin
        with com.example.audit.plugin.AuditPlugin;
}
~~~

Implementation:

~~~java
package com.example.audit.plugin;

import com.example.plugin.api.Plugin;

public final class AuditPlugin implements Plugin {
    public AuditPlugin() {
    }

    @Override
    public String name() {
        return "audit";
    }

    @Override
    public void start() {
        System.out.println("Audit plugin started");
    }
}
~~~

Service API nên được định nghĩa và nạp từ layer cha. Không đóng gói một bản sao của API vào mỗi plugin. Nếu host và plugin nhìn thấy hai class Plugin khác nhau do hai class loader định nghĩa, chúng không có cùng class identity và việc ép kiểu hoặc gọi service có thể thất bại.

## 4. Tìm và resolve plugin module

Giả sử host nhận đường dẫn thư mục plugin. Có thể dùng ModuleFinder để tìm module gốc, sau đó resolve dependency dựa trên configuration của boot layer.

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

Path pluginPath = Path.of("plugins", "audit");
ModuleFinder finder = ModuleFinder.of(pluginPath);

Configuration configuration =
        ModuleLayer.boot()
                .configuration()
                .resolve(
                        finder,
                        ModuleFinder.of(),
                        Set.of("com.example.audit.plugin"));
~~~

Ý nghĩa:

1. ModuleFinder.of(pluginPath) tìm module trong thư mục plugin.
2. Configuration của boot layer làm cấu hình cha để resolve dependency.
3. finder cung cấp module plugin và các dependency nằm trong thư mục đó.
4. ModuleFinder.of() ở vị trí after-finder không bổ sung module từ một nguồn khác.
5. Set.of(...) chỉ định root module cần resolve.

Các dependency có thể được thỏa mãn bởi module trong parent configuration hoặc module finder theo quy tắc resolution. Nếu plugin cần thư viện riêng, đặt thư viện đó trên module path phù hợp và kiểm soát xung đột tên module.

Có thể dùng resolveAndBind() thay cho resolve() khi muốn service binding tự động tìm thêm provider module phù hợp từ các finder trong quá trình resolution. Không dùng nó một cách máy móc: hãy xác định service nào được khai báo uses và provider nào cần được đưa vào configuration.

## 5. Định nghĩa layer bằng một class loader

Sau khi có Configuration, tạo layer:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

public final class PluginLayerFactory {

    private PluginLayerFactory() {
    }

    public static ModuleLayer create(Path pluginPath) {
        ModuleFinder finder = ModuleFinder.of(pluginPath);

        Configuration configuration =
                ModuleLayer.boot()
                        .configuration()
                        .resolve(
                                finder,
                                ModuleFinder.of(),
                                Set.of("com.example.audit.plugin"));

        ModuleLayer.Controller controller =
                ModuleLayer.defineModulesWithOneLoader(
                        configuration,
                        List.of(ModuleLayer.boot()),
                        Plugin.class.getClassLoader());

        return controller.layer();
    }
}
~~~

defineModulesWithOneLoader định nghĩa tất cả module trong configuration mới bằng một class loader mới. Class loader này có parent là class loader được truyền vào. Trong ví dụ, parent loader có thể nhìn thấy service API đã được định nghĩa ở layer cha.

Cách này phù hợp khi các module trong cùng plugin layer có thể chia sẻ một class loader. Nó cũng giúp quản lý nhóm plugin như một đơn vị.

Không nên truyền một parent loader không nhìn thấy service API hoặc các kiểu public mà plugin cần dùng. Nếu API class được nạp lần nữa trong child layer, class identity sẽ khác với API class mà host đang dùng.

## 6. Dùng ServiceLoader để tìm provider trong layer

Sau khi tạo layer, host có thể tìm provider bằng overload nhận ModuleLayer:

~~~java
import java.util.ServiceLoader;

ModuleLayer pluginLayer =
        PluginLayerFactory.create(Path.of("plugins", "audit"));

ServiceLoader<Plugin> loader =
        ServiceLoader.load(pluginLayer, Plugin.class);

for (Plugin plugin : loader) {
    System.out.println(plugin.name());
    plugin.start();
}
~~~

ServiceLoader.load(pluginLayer, Plugin.class) tìm provider trong layer được chỉ định và các layer cha của nó. Nó không tìm provider chỉ nằm trong một layer anh em.

Nếu cần kiểm tra provider thuộc layer nào trước khi khởi tạo, dùng stream():

~~~java
ServiceLoader.load(pluginLayer, Plugin.class)
        .stream()
        .forEach(provider -> {
            Class<?> providerType = provider.type();

            System.out.println(providerType.getName());
            System.out.println(providerType.getModule().getLayer());
        });
~~~

Lưu ý rằng layer cha cũng có thể chứa provider. Nếu yêu cầu là chỉ chạy provider đến từ layer plugin cụ thể, hãy lọc theo provider.type().getModule().getLayer() trước khi gọi get().

ServiceLoader không tự quản lý toàn bộ vòng đời plugin. Host vẫn cần định nghĩa cách start, stop, xử lý lỗi, lưu trạng thái và giải phóng tài nguyên của plugin.

## 7. Một layer hay nhiều layer?

Có thể tạo một layer chứa nhiều plugin hoặc tạo layer riêng cho từng plugin.

### Một layer cho một nhóm plugin

~~~text
Boot layer
    |
    v
Plugin layer
    |-- audit plugin
    |-- export plugin
    |-- reporting plugin
~~~

Phù hợp khi các plugin được triển khai, nâng cấp và khởi động cùng nhau; có dependency chung; hoặc cần chia sẻ class giữa các module plugin.

### Một layer cho mỗi plugin

~~~text
                 Boot layer
                /     |     \
               v      v      v
           Audit    Export  Report
           layer    layer   layer
~~~

Phù hợp khi plugin có dependency riêng, cần nạp hoặc gỡ độc lập, hoặc cần giới hạn phạm vi ServiceLoader. Mỗi layer con có thể có configuration và class loader riêng.

Tuy nhiên, layer riêng không tự động cách ly mọi thứ. Plugin vẫn chạy trong cùng process, có thể dùng chung tài nguyên hệ điều hành, thread, filesystem và các API mà quyền của process cho phép. Nếu cần chạy code không tin cậy, dùng process/container boundary và cơ chế kiểm soát ở cấp hệ điều hành.

## 8. Chọn class loader strategy

ModuleLayer cung cấp nhiều cách định nghĩa module và gắn class loader.

| API | Cách tổ chức loader | Khi phù hợp |
|---|---|---|
| defineModulesWithOneLoader | Một loader cho tất cả module trong layer mới | Các module trong một plugin group cần chia sẻ loader |
| defineModulesWithManyLoaders | Một loader cho mỗi module mới | Cần tách loader giữa các module |
| defineModules | Ứng dụng cung cấp hàm ánh xạ tên module sang class loader | Cần kiểm soát loader strategy chi tiết |

Với defineModulesWithManyLoaders, các module vẫn thuộc cùng một ModuleLayer nhưng có loader riêng. Với defineModules, hàm ánh xạ phải trả về class loader phù hợp cho từng module.

Chọn loader strategy dựa trên dependency và yêu cầu runtime. Nhiều loader có thể làm class visibility phức tạp hơn. Nếu một module cần chia sẻ kiểu với module khác, phải bảo đảm quan hệ readability và khả năng nạp class phù hợp.

Một class trong Java được nhận diện không chỉ bằng tên đầy đủ mà còn bởi class loader đã định nghĩa nó. Hai class cùng tên nhưng do hai loader khác nhau định nghĩa là hai kiểu khác nhau. Đây là nguyên nhân phổ biến của ClassCastException khi plugin đóng gói bản sao service API.

## 9. Quan hệ cha-con và sibling layer

Một layer con có thể đọc module từ layer cha theo cấu hình và quan hệ readability. Nhưng sibling layer không tự động đọc module của nhau.

~~~text
                 Boot layer
                 /        \
             childA      childB
               |            |
          Plugin A      Plugin B
~~~

Nếu childA và childB đều có boot layer làm parent:

- Plugin trong childA có thể đọc các module phù hợp từ boot layer.
- Plugin trong childB có thể đọc các module phù hợp từ boot layer.
- childA không tự động đọc module chỉ có trong childB.
- childB không tự động đọc module chỉ có trong childA.

Đây là cơ sở để giới hạn phạm vi provider hoặc dependency giữa các plugin. Nếu hai plugin cần giao tiếp, thiết kế contract ở layer cha hoặc truyền dữ liệu qua API host quản lý thay vì truy cập trực tiếp implementation của layer kia.

Cũng cần phân biệt visibility với quyền truy cập package. Một module có thể đọc module khác nhưng vẫn không truy cập được package chưa export. Readability và exports là hai điều kiện riêng.

## 10. Controller và điều chỉnh module ở runtime

Các phương thức defineModules... trả về ModuleLayer.Controller. Controller cho phép thực hiện một số thay đổi có kiểm soát đối với module trong layer được tạo, ví dụ:

- addReads: bổ sung quan hệ readability.
- addExports: export một package tới module đích.
- addOpens: mở package cho deep reflection.

Ví dụ minh họa:

~~~java
ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithOneLoader(
                configuration,
                List.of(ModuleLayer.boot()),
                Plugin.class.getClassLoader());

ModuleLayer layer = controller.layer();
~~~

Chỉ giữ Controller nếu ứng dụng thực sự cần điều chỉnh quan hệ module sau khi tạo layer. Đừng dùng addReads, addExports hoặc addOpens để che giấu một module descriptor được thiết kế sai. Hãy khai báo requires, exports và opens ngay trong module-info.java nếu đó là contract ổn định.

Runtime adjustment có thể tạo coupling khó nhìn thấy trong descriptor và làm việc chẩn đoán phức tạp hơn. Ghi lại rõ lý do, module nguồn, module đích và package được mở nếu phải dùng Controller.

## 11. Vòng đời plugin và khả năng thu hồi layer

ModuleLayer không có phương thức close() như URLClassLoader. Tạo layer không đồng nghĩa với việc ứng dụng có thể gỡ plugin ngay lập tức.

Class và resource được nạp bởi class loader của plugin có thể được thu hồi khi class loader trở nên không còn được tham chiếu và garbage collector có thể thu hồi các class tương ứng. Vì vậy, ứng dụng phải giải phóng mọi tham chiếu có thể giữ plugin sống:

- Dừng thread do plugin tạo.
- Hủy executor, scheduler và timer.
- Gỡ listener hoặc callback đăng ký vào host.
- Xóa plugin object khỏi registry và cache.
- Xóa ThreadLocal do plugin tạo nếu còn được giữ bởi thread sống lâu.
- Khôi phục thread context class loader nếu plugin đã thay đổi.
- Đóng file, socket, database connection và resource mà plugin sở hữu.
- Không giữ ServiceLoader, Provider hoặc Class object của plugin trong cache toàn cục.

Ngay cả khi bỏ tham chiếu ModuleLayer, một thread đang chạy code của plugin hoặc một static cache của host vẫn có thể giữ class loader sống. Việc thu hồi không xảy ra tức thời và không nên dựa vào System.gc().

Thiết kế plugin cần có lifecycle contract, ví dụ start() và stop(), để host yêu cầu plugin giải phóng tài nguyên trước khi loại bỏ registry và tham chiếu tới layer.

## 12. ModuleLayer không phải security sandbox

ModuleLayer giúp tổ chức module graph, readability, exports, opens và phạm vi class loading. Nó không phải một sandbox bảo mật cho code không tin cậy.

Plugin chạy trong cùng JVM có thể sử dụng những quyền mà process đang có nếu có thể truy cập API tương ứng. Module encapsulation giúp kiểm soát truy cập giữa module, nhưng không thay thế phân quyền hệ điều hành.

Nếu plugin đến từ nguồn không tin cậy hoặc cần giới hạn quyền đọc file, truy cập mạng, native code hay tài nguyên máy chủ, cân nhắc chạy plugin trong process riêng, container hoặc môi trường được hệ điều hành kiểm soát. Giao tiếp qua IPC hoặc network contract có thể tạo ranh giới mạnh hơn layer trong cùng JVM.

## 13. Kiểm thử plugin layer

Nên kiểm thử ít nhất các trường hợp:

| Tình huống | Kết quả mong đợi |
|---|---|
| Plugin module hợp lệ trong thư mục plugin | ModuleFinder tìm thấy và Configuration resolve thành công |
| Plugin thiếu dependency | Resolve thất bại với thông tin module thiếu |
| Plugin khai báo provides đúng service | ServiceLoader của layer tìm thấy provider |
| Provider nằm trong parent layer | Loader của child layer có thể nhìn thấy provider parent |
| Provider chỉ nằm trong sibling layer | Loader của layer khác không tìm thấy provider đó |
| Plugin đóng gói bản sao service API | Phát hiện lỗi class identity hoặc cấu hình module |
| Hai plugin dùng cùng tên module trong cùng cấu hình | Phát hiện xung đột module name |
| Plugin stop không giải phóng thread/listener | Class loader có thể vẫn được giữ sống |

Ví dụ kiểm tra layer identity:

~~~java
ServiceLoader.load(pluginLayer, Plugin.class)
        .stream()
        .filter(provider ->
                provider.type().getModule().getLayer() == pluginLayer)
        .forEach(provider -> {
            Plugin plugin = provider.get();
            plugin.start();
        });
~~~

Nếu một layer có nhiều provider hoặc provider từ parent, đừng giả định thứ tự duyệt. Hãy xác định provider theo module name, metadata hoặc contract nghiệp vụ.

Ngoài test đơn vị, chạy integration test với đúng thư mục module plugin và JDK mục tiêu. Test trên classpath không chứng minh module path và layer resolution hoạt động như mong đợi.

## 14. Quy trình chọn layer

Khi quyết định có nên tạo layer riêng, trả lời theo thứ tự:

1. Module/plugin có cần được phát hiện hoặc nạp sau khi host đã khởi động không?
2. Plugin có dependency graph hoặc phiên bản dependency riêng không?
3. Host có cần kiểm soát phạm vi ServiceLoader cho từng plugin không?
4. Các plugin có cần được nạp và quản lý vòng đời riêng không?
5. Có thể dùng chung service API từ layer cha mà không sao chép class không?
6. Cần một loader cho cả nhóm module hay loader riêng cho từng module?
7. Có yêu cầu security isolation không? Nếu có, ModuleLayer một mình không đáp ứng.
8. Có kế hoạch dừng thread, listener và resource trước khi bỏ layer không?

Nếu không có nhu cầu discovery, dependency isolation hoặc lifecycle riêng, dùng một module layer đơn giản sẽ giảm độ phức tạp. Nếu có plugin động, nhiều layer con với service API ở parent thường là một cấu trúc phù hợp.

## 15. Ghi nhớ

ModuleLayer là đơn vị runtime để định nghĩa một tập module đã resolve và quan hệ cha-con của chúng. Dùng layer riêng khi cần nạp plugin động, kiểm soát phạm vi provider hoặc quản lý các nhóm module có dependency và vòng đời riêng. Đặt service API ổn định ở layer cha, resolve plugin bằng ModuleFinder và Configuration, sau đó định nghĩa layer với class loader phù hợp.

Một layer con có thể nhìn thấy module ở parent theo quy tắc module system; sibling layer không tự động nhìn thấy nhau. Chọn một loader cho cả nhóm plugin khi chúng cần chia sẻ loader, hoặc nhiều loader khi cần phân tách class loading. Cuối cùng, nhớ rằng ModuleLayer không phải security sandbox và việc thu hồi plugin đòi hỏi giải phóng class loader, thread, listener và tài nguyên do plugin giữ.

## Tài liệu tham khảo

- Java API — ModuleLayer: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ModuleLayer.html
- Java API — Configuration: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/Configuration.html
- Java API — ServiceLoader: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html
- Java Platform Module System — Module API: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/package-summary.html
