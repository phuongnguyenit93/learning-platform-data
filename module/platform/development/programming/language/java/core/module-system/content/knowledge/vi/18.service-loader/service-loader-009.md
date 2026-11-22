# Kiểm thử service khi provider nằm ở layer khác

Java Module System cho phép một ứng dụng tạo nhiều ModuleLayer độc lập. Một service interface có thể nằm trong layer cha, trong khi implementation được nạp vào một layer con hoặc một layer khác. Vì vậy, khi kiểm thử ServiceLoader, cần xác định rõ layer chứa provider và dùng đúng overload để tìm provider.

Trường hợp điển hình là ứng dụng có API service ổn định trong boot layer, còn plugin/provider được nạp động từ một thư mục module riêng. Bài kiểm thử cần chứng minh rằng ứng dụng tìm được provider trong layer được chỉ định, provider thực sự thuộc layer đó, và các layer không có quan hệ cha-con không bị trộn lẫn.

## 1. Hai cách tải service và khác biệt quan trọng

ServiceLoader có các overload thường gặp:

| API | Cách tìm provider |
|---|---|
| ServiceLoader.load(Service.class) | Dùng thread context class loader |
| ServiceLoader.load(Service.class, loader) | Dùng class loader được chỉ định |
| ServiceLoader.load(layer, Service.class) | Tìm provider trong layer được chỉ định và các layer cha của nó |

Khi provider được triển khai trong một ModuleLayer tùy chỉnh, nên dùng overload nhận ModuleLayer. Cách này thể hiện chính xác phạm vi tìm kiếm và tránh phụ thuộc vào thread context class loader.

Giả sử cấu trúc runtime như sau:

~~~text
ModuleLayer.boot()
    |
    |-- com.example.spi
    |      exports com.example.spi
    |
    |-- com.example.app
           requires com.example.spi
           uses com.example.spi.GreetingService

ModuleLayer child
    |
    |-- com.example.provider
           requires com.example.spi
           provides GreetingService with FormalGreeting
~~~

Service interface được chia sẻ từ layer cha. Provider được nạp vào layer con. Khi gọi ServiceLoader.load(childLayer, GreetingService.class), ServiceLoader tìm provider trong childLayer và các layer cha của nó.

Một layer anh em (sibling) không nằm trong phạm vi tìm kiếm. Ví dụ, nếu childA và childB đều được tạo trực tiếp từ boot layer, loader gắn với childA không tự tìm provider chỉ có trong childB.

## 2. Khai báo service và provider trong các module

Ví dụ sử dụng một service đơn giản để kiểm tra.

Module chứa service API:

~~~java
module com.example.spi {
    exports com.example.spi;
}
~~~

Service interface:

~~~java
package com.example.spi;

public interface GreetingService {
    String greet();
}
~~~

Module provider:

~~~java
module com.example.provider {
    requires com.example.spi;

    provides com.example.spi.GreetingService
        with com.example.provider.FormalGreeting;
}
~~~

Provider implementation:

~~~java
package com.example.provider;

import com.example.spi.GreetingService;

public final class FormalGreeting implements GreetingService {
    public FormalGreeting() {
    }

    @Override
    public String greet() {
        return "Hello from child layer";
    }
}
~~~

Với cách khai báo provider bằng provides ... with ..., provider class trong ví dụ là public và có public constructor không tham số. Module provider phải đọc được module chứa service interface.

Module ứng dụng hoặc module kiểm thử gọi ServiceLoader:

~~~java
module com.example.app {
    requires com.example.spi;

    uses com.example.spi.GreetingService;
}
~~~

Chỉ thị uses rất quan trọng. Module thực hiện lời gọi ServiceLoader phải khai báo service mà nó sử dụng. Nếu caller là một named module nhưng thiếu uses, thao tác tải service có thể ném ServiceConfigurationError.

## 3. Tạo layer con chứa provider

Để kiểm thử đúng tình huống provider ở layer khác, không đưa provider vào boot layer. Giả sử module SPI và module ứng dụng đã được nạp trong boot layer, còn module provider được đóng gói trong thư mục riêng, ví dụ plugins/.

Có thể tạo layer con bằng ModuleFinder, Configuration và ModuleLayer:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

public final class PluginLayers {

    private PluginLayers() {
    }

    public static ModuleLayer createProviderLayer(Path pluginsDirectory) {
        ModuleFinder finder = ModuleFinder.of(pluginsDirectory);

        Configuration configuration =
                ModuleLayer.boot()
                        .configuration()
                        .resolve(
                                finder,
                                ModuleFinder.of(),
                                Set.of("com.example.provider"));

        return ModuleLayer.defineModulesWithOneLoader(
                configuration,
                List.of(ModuleLayer.boot()),
                ClassLoader.getSystemClassLoader())
                .layer();
    }
}
~~~

Ý nghĩa các bước:

1. ModuleFinder.of(pluginsDirectory) tìm các module provider trong thư mục plugin.
2. configuration().resolve(...) giải quyết module graph bắt đầu từ module gốc com.example.provider. Các dependency có thể được tìm trong layer cha.
3. ModuleLayer.defineModulesWithOneLoader(...) định nghĩa các module đã resolve thành layer mới. Các module trong layer mới dùng một class loader có parent là class loader được truyền vào.
4. layer() lấy ModuleLayer vừa được tạo từ Controller.

Ở ví dụ này, provider được khai báo trực tiếp làm root nên resolve() là đủ để đưa nó vào configuration. Nếu mục tiêu là kiểm tra service binding tự động, có thể dùng resolveAndBind() với root module tiêu thụ service để thuật toán service binding tìm thêm provider phù hợp trong module finder.

Việc một JAR có mặt trong thư mục plugin không tự động có nghĩa module đó đã thuộc layer. Module phải được tìm thấy và resolve vào configuration trước khi được định nghĩa trong layer.

## 4. Kiểm thử provider thực sự nằm trong layer con

Test nên kiểm tra cả hai điều:

- ServiceLoader tìm thấy provider.
- Class của provider được định nghĩa trong đúng ModuleLayer con.

Có thể dùng ServiceLoader.stream() để lấy Provider trước khi khởi tạo implementation. Provider.type() cho phép kiểm tra class và module của provider.

Ví dụ JUnit:

~~~java
package com.example.app;

import com.example.spi.GreetingService;
import java.nio.file.Path;
import java.util.List;
import java.util.ServiceLoader;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ServiceLayerTest {

    @Test
    void discoversProviderFromChildLayer() {
        ModuleLayer childLayer =
                PluginLayers.createProviderLayer(Path.of("plugins"));

        List<ServiceLoader.Provider<GreetingService>> providers =
                ServiceLoader.load(childLayer, GreetingService.class)
                        .stream()
                        .collect(Collectors.toList());

        assertTrue(
                providers.stream().anyMatch(provider ->
                        provider.type().getModule().getLayer() == childLayer),
                "Phải tìm thấy provider thuộc child layer");

        List<String> messages = providers.stream()
                .map(ServiceLoader.Provider::get)
                .map(GreetingService::greet)
                .collect(Collectors.toList());

        assertTrue(messages.contains("Hello from child layer"));
    }
}
~~~

Test đầu tiên xác minh provider type thuộc đúng layer con. Test thứ hai gọi provider và kiểm tra hành vi thực tế. Hai assertion này bắt được hai loại lỗi khác nhau: không tìm được provider và tìm được provider nhưng provider không hoạt động như mong đợi.

Không nên chỉ kiểm tra số lượng provider. Một provider từ parent layer cũng có thể được ServiceLoader.load(childLayer, service) tìm thấy. Kiểm tra getModule().getLayer() giúp xác định chính xác provider đến từ đâu.

Cũng không nên giả định provider đầu tiên trong danh sách là provider của child layer. Thứ tự provider không phải hợp đồng mà test nên phụ thuộc vào. Hãy lọc theo module layer, tên module hoặc kết quả nghiệp vụ.

## 5. Kiểm tra phạm vi layer cha và layer anh em

ServiceLoader.load(layer, service) tìm provider trong layer được chỉ định và các layer cha. Hành vi này có hai hệ quả cần đưa vào test.

**Provider ở layer cha có thể được tìm thấy.** Nếu boot layer đã có provider cho cùng service, loader tạo từ child layer có thể nhìn thấy provider đó. Vì vậy, test chỉ kiểm tra providers.isEmpty() hoặc providers.size() có thể cho kết quả sai với mục tiêu kiểm tra child layer.

**Provider ở layer anh em không tự động được tìm thấy.** Nếu childA và childB cùng có boot layer làm parent, provider chỉ nằm trong childB không thuộc phạm vi của loader tạo từ childA.

Có thể biểu diễn phạm vi tìm kiếm:

~~~text
                 boot layer
                 /        \
             childA      childB
               |            |
           provider A    provider B

ServiceLoader.load(childA, Service.class)
    tìm trong childA và boot layer
    không tìm provider chỉ nằm trong childB
~~~

Khi kiểm thử sibling isolation, tạo hai layer độc lập từ cùng parent, đặt provider riêng vào mỗi layer, rồi xác minh loader của layer A không trả về provider có module thuộc layer B. Mỗi layer phải được tạo từ configuration phù hợp và service type phải là cùng một Class được chia sẻ từ parent layer.

Không so sánh tên module đơn thuần để xác định layer. Cùng một tên module có thể xuất hiện trong các cấu hình runtime độc lập. So sánh đối tượng ModuleLayer từ Class.getModule().getLayer() sẽ thể hiện đúng nguồn của provider.

## 6. Vì sao load(service) có thể bỏ sót provider?

ServiceLoader.load(GreetingService.class) sử dụng thread context class loader. Cách này phổ biến khi provider nằm trên classpath hoặc trong phạm vi class loader mà ứng dụng đang dùng.

Một custom ModuleLayer có thể được định nghĩa bằng class loader riêng. Nếu thread context class loader không nhìn thấy provider trong layer đó, overload class loader mặc định không đáp ứng mục tiêu kiểm thử.

Vì vậy:

~~~java
// Tìm provider theo thread context class loader
ServiceLoader<GreetingService> defaultLoader =
        ServiceLoader.load(GreetingService.class);

// Tìm provider theo ModuleLayer cụ thể
ServiceLoader<GreetingService> layerLoader =
        ServiceLoader.load(childLayer, GreetingService.class);
~~~

Hai loader trên có phạm vi tìm kiếm khác nhau. Đừng dùng kết quả của defaultLoader để kết luận provider có tồn tại trong childLayer hay không. Khi test plugin theo ModuleLayer, hãy truyền layer tường minh.

Nếu hệ thống chủ ý dùng class loader để quản lý plugin, có thể kiểm thử overload load(service, loader), nhưng test đó trả lời câu hỏi về khả năng nhìn thấy provider qua class loader. Nó không thay thế kiểm thử phạm vi của ModuleLayer.

## 7. Kiểm tra module descriptor và lỗi cấu hình

Khi provider không được tìm thấy, kiểm tra cấu hình module theo thứ tự:

1. Module provider có thực sự được đưa vào configuration của layer không?
2. Module provider có khai báo requires tới module chứa service interface không?
3. Provider module có provides Service with ProviderClass trong module-info.java không?
4. Module gọi ServiceLoader có khai báo uses Service không?
5. Provider class có thể được khởi tạo theo quy tắc của ServiceLoader không?
6. Service interface có cùng Class identity giữa caller và provider không?

Có thể kiểm tra descriptor trước khi tạo layer:

~~~java
ModuleFinder finder = ModuleFinder.of(Path.of("plugins"));

finder.find("com.example.provider")
        .ifPresent(reference -> {
            var descriptor = reference.descriptor();

            System.out.println("Module: " + descriptor.name());
            descriptor.requires().forEach(System.out::println);
            descriptor.provides().forEach(System.out::println);
        });
~~~

ModuleDescriptor.provides() cho biết các service mà module cung cấp. ModuleDescriptor.uses() cho biết các service mà module tiêu thụ. Đây là cách hữu ích để phát hiện lỗi khai báo trước khi chạy test tích hợp.

ServiceConfigurationError thường biểu thị lỗi cấu hình hoặc lỗi khi tìm/khởi tạo provider. Khi gặp lỗi, giữ nguyên cause và thông tin module trong log để xác định provider class, constructor, module descriptor hoặc class loader có vấn đề.

Không nên bắt ServiceConfigurationError rồi trả về danh sách rỗng. Cách đó làm test biến lỗi cấu hình thành kết quả “không có provider”, khiến nguyên nhân thực sự khó tìm.

## 8. Test matrix nên có

| Tình huống | Kết quả mong đợi |
|---|---|
| Provider được resolve vào child layer | load(childLayer, service) tìm thấy provider |
| Provider ở parent layer | Loader của child layer có thể tìm thấy provider parent |
| Provider chỉ ở sibling layer | Loader của child layer không tìm thấy provider sibling |
| Provider JAR chỉ nằm trên đĩa, chưa resolve vào layer | Không được xem là provider của layer |
| Provider module thiếu provides | ServiceLoader không tìm thấy provider theo khai báo module |
| Caller module thiếu uses | Có thể nhận ServiceConfigurationError |
| Provider không khởi tạo được | Nhận ServiceConfigurationError, test phải báo lỗi |
| Dùng load(service) với context loader không nhìn thấy plugin | Không thể dùng kết quả này để kết luận về child layer |

Với test tích hợp, nên có ít nhất một provider chỉ nằm trong child layer và một test xác nhận layer identity. Nếu hệ thống hỗ trợ nhiều plugin layer, thêm test sibling isolation để tránh vô tình chia sẻ provider giữa các plugin.

## 9. Quy tắc thực hành

- Dùng ServiceLoader.load(layer, service) khi muốn kiểm tra provider trong một ModuleLayer cụ thể.
- Đảm bảo module gọi ServiceLoader có uses directive cho service.
- Đảm bảo provider module đã được resolve và định nghĩa trong layer.
- Dùng provides ... with ... trong module descriptor của provider module.
- Xác minh provider thuộc đúng layer bằng provider.type().getModule().getLayer().
- Không phụ thuộc vào thứ tự provider.
- Phân biệt provider ở layer cha với provider ở layer con.
- Không kỳ vọng loader của một layer tìm thấy provider chỉ nằm trong layer anh em.
- Giữ ServiceConfigurationError hiển thị trong test để lỗi module descriptor hoặc khởi tạo provider không bị che giấu.

Khi kiểm thử service theo nhiều ModuleLayer, điều cần xác nhận không chỉ là service trả về kết quả đúng. Test còn phải xác nhận provider được tìm thấy từ đúng layer, đúng quan hệ cha-con và đúng cấu hình module. Đây là cách phát hiện sớm lỗi thường gặp trong hệ thống plugin hoặc ứng dụng nạp module động.
