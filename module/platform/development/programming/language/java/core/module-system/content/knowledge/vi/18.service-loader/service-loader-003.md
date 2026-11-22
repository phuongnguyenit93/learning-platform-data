# ServiceLoader.load với ModuleLayer

## Mục tiêu

Sau bài này, bạn có thể giải thích cách Java tìm service provider trong một module layer, cấu hình ba vai trò API, consumer và provider bằng JPMS, rồi nạp provider từ một thư mục plugin lúc chạy bằng ServiceLoader.

## 1. Vì sao kết hợp ServiceLoader với ModuleLayer?

ServiceLoader là cơ chế Service Provider Interface (SPI) của Java. Ứng dụng phụ thuộc vào một interface dịch vụ, còn các module khác cung cấp những lớp triển khai interface đó. Consumer chỉ biết kiểu dịch vụ; nó không cần phụ thuộc trực tiếp vào từng provider.

Java Platform Module System (JPMS) mô tả quan hệ này trong module descriptor:

- Module định nghĩa API xuất package chứa interface bằng exports.
- Module sử dụng dịch vụ khai báo uses.
- Module cung cấp triển khai khai báo provides ... with ....

Khi tất cả module đã có mặt lúc khởi động, các provider có thể được phân giải vào boot layer. Nhưng với ứng dụng plugin, ta thường muốn phát hiện và nạp module provider từ một thư mục sau khi ứng dụng đã chạy. ModuleLayer cho phép tạo một lớp module mới dựa trên một Configuration và một hoặc nhiều layer cha.

Overload ServiceLoader.load(ModuleLayer, Class) kết nối hai cơ chế này: nó tìm provider của kiểu dịch vụ trong layer được chỉ định và các layer cha của layer đó. Vì vậy, ứng dụng có thể nạp plugin theo từng layer mà không cần thêm các module plugin vào module path của tiến trình ngay từ đầu.

## 2. Ba thành phần của ví dụ

Ta xây dựng một dịch vụ chào hỏi với ba module:

| Module | Vai trò | Trách nhiệm |
|---|---|---|
| com.acme.greeting.api | Service API | Khai báo và export GreetingService |
| com.acme.greeting.app | Consumer | Khai báo uses, tạo layer và gọi ServiceLoader |
| com.acme.greeting.vi | Provider | Cài đặt GreetingService và khai báo provides |

Khi chạy, API và ứng dụng nằm trong boot layer. Provider được đóng gói thành modular JAR trong thư mục plugins và được nạp vào một layer con.

Cấu trúc mã nguồn có thể tổ chức như sau:

~~~text
src/
  com.acme.greeting.api/
    module-info.java
    com/acme/greeting/api/GreetingService.java
  com.acme.greeting.app/
    module-info.java
    com/acme/greeting/app/Main.java
  com.acme.greeting.vi/
    module-info.java
    com/acme/greeting/vi/VietnameseGreetingService.java

mods/
  com.acme.greeting.api.jar
  com.acme.greeting.app.jar

plugins/
  com.acme.greeting.vi.jar
~~~

Điểm quan trọng là JAR provider nằm trong plugins, không nằm trong mods khi khởi động ứng dụng. Nhờ vậy, provider được phân giải vào layer mới thay vì boot layer.

## 3. Khai báo module API

File module-info.java của module API:

~~~java
module com.acme.greeting.api {
    exports com.acme.greeting.api;
}
~~~

Interface dịch vụ:

~~~java
package com.acme.greeting.api;

public interface GreetingService {
    String greet(String name);
}
~~~

Package chứa interface phải được export để consumer và provider có thể tham chiếu kiểu GreetingService. Đây là kiểu hợp đồng chung giữa các module; consumer không cần biết tên lớp triển khai cụ thể.

## 4. Khai báo module provider

File module-info.java của provider:

~~~java
module com.acme.greeting.vi {
    requires com.acme.greeting.api;

    provides com.acme.greeting.api.GreetingService
        with com.acme.greeting.vi.VietnameseGreetingService;
}
~~~

Lớp triển khai:

~~~java
package com.acme.greeting.vi;

import com.acme.greeting.api.GreetingService;

public final class VietnameseGreetingService implements GreetingService {

    public VietnameseGreetingService() {
    }

    @Override
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Provider yêu cầu module API vì nó triển khai interface được khai báo ở đó. Chỉ thị provides đăng ký lớp triển khai cho service type. Với cách đăng ký này, package chứa lớp provider không cần export cho consumer chỉ để ServiceLoader tìm và tạo provider.

Module provider phải được đóng gói thành một module mà ModuleFinder có thể tìm thấy, thường là một modular JAR có module-info.class. Thư mục plugin không nên chứa một bản sao khác của module API nếu API đã nằm trong layer cha.

## 5. Khai báo module consumer

File module-info.java của ứng dụng:

~~~java
module com.acme.greeting.app {
    requires com.acme.greeting.api;

    uses com.acme.greeting.api.GreetingService;
}
~~~

Chỉ thị uses là phần khai báo quan trọng ở phía consumer. Module chứa mã gọi ServiceLoader phải khai báo rằng nó sử dụng service type đó. Nếu thiếu uses trong một named module, lời gọi nạp dịch vụ có thể thất bại với IllegalCallerException.

Consumer chỉ phụ thuộc vào API. Nó không cần khai báo requires com.acme.greeting.vi, bởi provider sẽ được tìm thấy động khi tạo layer.

## 6. Tạo layer mới và nạp provider

Trong Main.java, ta tìm module plugin, phân giải cấu hình dựa trên boot layer, tạo layer con rồi truyền layer đó cho ServiceLoader:

~~~java
package com.acme.greeting.app;

import com.acme.greeting.api.GreetingService;

import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.ServiceLoader;
import java.util.Set;

public class Main {

    public static void main(String[] args) {
        Path pluginDirectory = Paths.get(
            args.length == 0 ? "plugins" : args[0]
        );

        // Tìm các module có trong thư mục plugin.
        ModuleFinder pluginFinder = ModuleFinder.of(pluginDirectory);

        // Nêu rõ module provider cần được đưa vào layer mới.
        Set<String> roots = Set.of("com.acme.greeting.vi");

        // Phân giải provider và các dependency của nó.
        // Dependency đã có trong boot layer sẽ được lấy từ layer cha.
        Configuration configuration = ModuleLayer.boot()
            .configuration()
            .resolve(pluginFinder, ModuleFinder.of(), roots);

        // Tạo layer con. Các module mới dùng chung một class loader.
        ModuleLayer pluginLayer = ModuleLayer.defineModulesWithOneLoader(
            configuration,
            List.of(ModuleLayer.boot()),
            ClassLoader.getSystemClassLoader()
        ).layer();

        // Tìm service provider trong pluginLayer và các layer cha.
        ServiceLoader<GreetingService> services =
            ServiceLoader.load(pluginLayer, GreetingService.class);

        // Provider được khởi tạo khi ta duyệt kết quả.
        services.forEach(service ->
            System.out.println(service.greet("Java"))
        );
    }
}
~~~

Các bước có ý nghĩa như sau:

1. ModuleFinder.of(pluginDirectory) tìm module trong thư mục plugin. Với ví dụ này, thư mục chứa JAR của com.acme.greeting.vi.
2. roots chỉ định module gốc cần phân giải. ModuleFinder tìm thấy một JAR chưa có nghĩa module đó tự động được đưa vào layer; module phải thuộc đồ thị được phân giải từ các root.
3. Configuration.resolve(...) giải quyết đồ thị module. Cấu hình boot layer là cấu hình cha; pluginFinder cung cấp các module mới, còn ModuleFinder.of() ở tham số thứ hai là nơi tìm module bổ sung sau finder thứ nhất.
4. ModuleLayer.defineModulesWithOneLoader(...) định nghĩa các module đã phân giải trong layer con. Layer mới có boot layer làm cha và dùng một class loader chung cho các module mới.
5. ServiceLoader.load(pluginLayer, GreetingService.class) tìm provider trong pluginLayer và các layer cha. Việc duyệt ServiceLoader sẽ kích hoạt quá trình tạo các provider được tìm thấy.

Nếu có nhiều module plugin độc lập, hãy thêm tên từng module vào roots. Nếu provider phụ thuộc vào module khác nằm trong thư mục plugin, các dependency đó sẽ được đưa vào đồ thị khi phân giải.

## 7. Chạy ví dụ

Đóng gói module API và module ứng dụng vào thư mục mods. Đóng gói module provider thành JAR riêng trong thư mục plugins. Khi biên dịch provider, module path phải chứa JAR của API để javac phân giải được chỉ thị requires.

Khởi chạy ứng dụng bằng lệnh:

~~~bash
java --module-path mods \
     --module com.acme.greeting.app/com.acme.greeting.app.Main \
     plugins
~~~

Tham số plugins được truyền vào Main và dùng làm đường dẫn tìm module provider. Kết quả dự kiến:

~~~text
Xin chào, Java!
~~~

Trong lần khởi chạy này, module API và consumer thuộc boot layer. Module provider được tìm từ thư mục plugins, phân giải và định nghĩa trong layer con. Không cần đưa JAR provider vào module path khởi động của ứng dụng.

## 8. Khác biệt giữa hai overload load thường gặp

ServiceLoader có hai cách nạp thường được dùng trong ứng dụng modular:

- ServiceLoader.load(GreetingService.class) sử dụng thread context class loader để tìm provider. Cách này phù hợp với nhiều ứng dụng classpath và các tình huống discovery dựa trên class loader.
- ServiceLoader.load(pluginLayer, GreetingService.class) chỉ rõ module layer làm phạm vi tìm kiếm. Provider được tìm trong layer đó và các layer cha, phù hợp khi ứng dụng tự tạo layer cho plugin.

Nếu ứng dụng quản lý plugin bằng ModuleLayer, truyền layer rõ ràng giúp phạm vi tìm provider dễ hiểu và ít phụ thuộc vào trạng thái thread context class loader hơn. Dù dùng overload nào, named module gọi ServiceLoader vẫn cần khai báo uses cho service type tương ứng.

## 9. Vòng đời và cách duyệt ServiceLoader

ServiceLoader có tính lazy: việc tạo đối tượng ServiceLoader chưa có nghĩa mọi provider đã được khởi tạo. Provider được tạo khi ứng dụng duyệt iterator, gọi forEach hoặc lấy provider từ stream.

Có thể duyệt trực tiếp:

~~~java
for (GreetingService service : services) {
    System.out.println(service.greet("Java"));
}
~~~

Hoặc dùng stream để xem thông tin provider trước khi lấy instance:

~~~java
services.stream()
    .map(ServiceLoader.Provider::get)
    .forEach(service ->
        System.out.println(service.greet("Java"))
    );
~~~

ServiceLoader lưu cache các provider đã được tìm và tạo trong vòng đời của loader đó. Gọi reload() sẽ xóa cache để lần duyệt tiếp theo tìm lại provider. reload() không tạo lại ModuleLayer và cũng không thay đổi đồ thị module đã phân giải.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| IllegalCallerException khi gọi load(layer, service) | Named module gọi API chưa khai báo uses cho service type | Kiểm tra module-info.java của đúng module chứa lời gọi |
| Không tìm thấy provider | JAR không nằm trong thư mục được ModuleFinder quét, module provider không nằm trong roots hoặc thiếu provides | Kiểm tra đường dẫn plugin, tên module và module descriptor |
| FindException hoặc ResolutionException | Không tìm thấy module gốc hoặc dependency không thể phân giải | Kiểm tra tên module, module path và các requires |
| ServiceConfigurationError khi duyệt | Provider khai báo sai hoặc không thể được khởi tạo | Kiểm tra lớp provider, constructor và chỉ thị provides |
| ClassCastException hoặc provider không được nhận diện như service type | API bị nạp thành hai kiểu Class khác nhau bởi các class loader/layer khác nhau | Đặt module API ở layer cha và tránh đóng gói bản sao API trong plugin |

Khi không có provider nào được tìm thấy, hãy kiểm tra cả hai phía: module provider có khai báo provides đúng service type hay chưa, và module đó đã thực sự được đưa vào layer hay chưa. Chỉ đặt JAR vào thư mục plugin chưa đủ nếu tên module của nó không nằm trong tập roots và cũng không phải dependency của một root khác.

## 11. Chọn cách tạo class loader

Ví dụ dùng defineModulesWithOneLoader vì cấu hình này tạo một class loader cho các module mới trong layer. Nó phù hợp với nhiều hệ thống plugin đơn giản, nơi các module plugin có thể dùng chung một loader.

defineModulesWithManyLoaders tạo class loader riêng cho từng module trong layer. Cách này có thể hữu ích khi cần ranh giới class loader rõ hơn giữa các module. Dù chọn cách nào, quyền đọc module vẫn do đồ thị JPMS quyết định; class loader riêng không biến ModuleLayer thành sandbox bảo mật.

Một ModuleLayer cũng không phải tiến trình riêng. Mã plugin vẫn chạy trong cùng JVM và có thể sử dụng các quyền mà tiến trình đang có. Nếu cần cô lập mã không đáng tin cậy, phải thiết kế biên an toàn ở cấp tiến trình hoặc môi trường thực thi khác.

## 12. Khi nào nên dùng ServiceLoader.load với ModuleLayer?

Cách này phù hợp khi ứng dụng cần:

- Nạp plugin sau khi ứng dụng đã khởi động.
- Giữ API dịch vụ ổn định trong layer cha, còn provider thay đổi theo thư mục plugin.
- Phân giải một nhóm module plugin và dependency của chúng thành một layer riêng.
- Tìm provider theo đồ thị module cụ thể thay vì dựa vào thread context class loader.

Nếu ứng dụng chỉ dùng classpath và không tạo module layer riêng, ServiceLoader.load(service) thường đơn giản hơn. Khi ứng dụng đã quản lý plugin bằng JPMS và ModuleLayer, ServiceLoader.load(layer, service) thể hiện rõ nơi cần tìm provider.

## Ghi nhớ

ServiceLoader định nghĩa cách consumer tìm và sử dụng provider; JPMS khai báo quan hệ uses/provides; ModuleLayer gom các module đã phân giải thành một lớp runtime có quan hệ cha-con. Luồng nạp plugin điển hình là tìm module bằng ModuleFinder, phân giải bằng Configuration, tạo ModuleLayer rồi gọi ServiceLoader.load(layer, service).