# Tổ chức khám phá plugin qua dịch vụ trong lớp mô-đun

## Mục tiêu

JPMS cho phép ứng dụng nạp các mô-đun plugin ở runtime mà không cần đặt tất cả plugin trên module path của ứng dụng ngay từ lúc khởi động. Một cách tổ chức phù hợp là đặt hợp đồng plugin trong một mô-đun API ổn định, đặt các plugin trong thư mục riêng, tạo một **ModuleLayer** con từ những mô-đun tìm thấy ở thư mục đó, rồi dùng **ServiceLoader** để khám phá implementation.

Sau bài này, bạn có thể:

- Thiết kế service API để host và plugin cùng sử dụng.
- Khai báo phía tiêu thụ bằng uses và phía cung cấp bằng provides ... with ....
- Quét module descriptor để tìm các mô-đun có cung cấp service.
- Phân giải dependency và tạo ModuleLayer động ở runtime.
- Dùng ServiceLoader.load(layer, Service.class) để tìm provider trong layer.
- Xử lý trường hợp không có plugin, module resolution lỗi hoặc provider cấu hình sai.
- Chọn chiến lược class loader và quản lý vòng đời plugin phù hợp.

Ví dụ sử dụng API JPMS từ Java 9 và được biên dịch/chạy theo baseline Java 17 trở lên.

## 1. Kiến trúc plugin dựa trên service

Một kiến trúc plugin modular thường có ba phần:

1. **Service API:** mô-đun định nghĩa interface hoặc abstract service type mà host và plugin cùng hiểu.
2. **Host application:** mô-đun sử dụng service, tìm các plugin module và tạo layer để nạp chúng.
3. **Plugin modules:** các mô-đun độc lập triển khai service và khai báo provider trong module descriptor.

~~~text
Boot layer
├── com.acme.plugin.api
│   └── com.acme.plugin.api.Plugin
└── com.acme.host
    └── com.acme.host.Main

Plugin directory
└── com.acme.plugin.csv.jar
    ├── module-info.class
    └── com.acme.plugin.csv.CsvPlugin

Child ModuleLayer
└── com.acme.plugin.csv
    └── provider của com.acme.plugin.api.Plugin
~~~

Service API và host được khởi chạy trong boot layer. Các plugin được tìm từ thư mục riêng, phân giải thành một configuration mới và nạp trong child layer. Plugin vẫn đọc được service API ở parent layer thông qua quan hệ mô-đun.

Cách tổ chức này cho phép triển khai plugin riêng biệt, kiểm tra module descriptor trước khi khởi tạo và chọn thời điểm tạo layer.

## 2. Khai báo service contract

Service API là hợp đồng ổn định giữa host và plugin. Interface nên thể hiện những thao tác mà host thực sự cần, tránh phụ thuộc vào class cụ thể của từng plugin.

Ví dụ Plugin.java:

~~~java
package com.acme.plugin.api;

public interface Plugin {
    String name();
    String process(String input);
}
~~~

Mô-đun API xuất package chứa interface:

~~~java
module com.acme.plugin.api {
    exports com.acme.plugin.api;
}
~~~

Host và plugin đều khai báo requires com.acme.plugin.api. Nhờ vậy, cả hai cùng tham chiếu một định nghĩa service type được nạp từ parent layer.

Hợp đồng service nên được thiết kế cẩn thận:

- Giữ tên và ý nghĩa method ổn định qua các phiên bản.
- Quy định rõ kiểu dữ liệu đầu vào, đầu ra và cách biểu diễn lỗi.
- Không để API công khai phụ thuộc vào class implementation riêng của một plugin.
- Nếu cần thay đổi không tương thích, xác định rõ version hoặc một service contract mới.
- Tránh truyền object thuộc class loader riêng của plugin qua API nếu host không thể đọc kiểu đó.

Service API là điểm kết nối giữa các mô-đun. Nếu host và plugin nạp hai bản khác nhau của cùng interface, object provider có thể không tương thích về kiểu dù tên class giống nhau. Vì vậy, hãy để service API ở layer cha và dùng chính lớp service đó khi gọi ServiceLoader.

## 3. Khai báo phía tiêu thụ bằng uses

Mô-đun gọi ServiceLoader phải khai báo service mà nó sử dụng trong module-info.java.

Ví dụ module descriptor của com.acme.host:

~~~java
module com.acme.host {
    requires com.acme.plugin.api;
    uses com.acme.plugin.api.Plugin;
}
~~~

Hai chỉ thị có vai trò khác nhau:

- requires com.acme.plugin.api tạo quan hệ readability để host tham chiếu interface Plugin.
- uses com.acme.plugin.api.Plugin khai báo host là consumer của service đó.

Với named module, nếu code gọi ServiceLoader cho một service nhưng module descriptor thiếu uses tương ứng, quá trình tìm provider có thể thất bại với ServiceConfigurationError. Khai báo uses là một phần của hợp đồng mô-đun, không phải một dòng tùy chọn chỉ để ghi chú.

## 4. Khai báo phía cung cấp bằng provides

Mỗi plugin là một named module và khai báo service provider bằng provides ... with ....

Ví dụ module descriptor của plugin CSV:

~~~java
module com.acme.plugin.csv {
    requires com.acme.plugin.api;
    provides com.acme.plugin.api.Plugin
        with com.acme.plugin.csv.CsvPlugin;
}
~~~

Implementation CsvPlugin.java:

~~~java
package com.acme.plugin.csv;

import com.acme.plugin.api.Plugin;

public final class CsvPlugin implements Plugin {
    public String name() {
        return "CSV";
    }

    public String process(String input) {
        return "processed " + input;
    }
}
~~~

Các điểm cần nhớ:

- Plugin module phải đọc được service API, vì vậy nó khai báo requires com.acme.plugin.api.
- provides chỉ ra service type và implementation provider.
- Provider class theo dạng constructor phải là lớp public có public no-argument constructor.
- Package chứa provider không cần exports nếu host không gọi trực tiếp lớp implementation.
- ServiceLoader tạo provider khi cần; việc tìm module descriptor không đồng nghĩa mọi plugin đã được khởi tạo.

JPMS cũng hỗ trợ provider method tĩnh theo quy tắc của ServiceLoader. Với cách đó, lớp được nêu trong provides có public static provider() trả về service type phù hợp. Cách constructor đơn giản trong ví dụ trên thường dễ hiểu và dễ kiểm thử hơn.

## 5. Tìm plugin module bằng ModuleFinder

ModuleFinder cung cấp cách tìm mô-đun từ các vị trí module path. Có thể tạo finder từ thư mục chứa modular JAR hoặc exploded module:

~~~java
ModuleFinder finder = ModuleFinder.of(Path.of("plugins"));
~~~

ModuleFinder.of(directory) tìm các mô-đun ở thư mục được chỉ định. Cách bố trí thông dụng là một thư mục phẳng chứa các modular JAR:

~~~text
application/
├── mods/
│   ├── com.acme.plugin.api.jar
│   └── com.acme.host.jar
└── plugins/
    ├── com.acme.plugin.csv.jar
    └── com.acme.plugin.json.jar
~~~

Thư mục mods chứa host và service API được phân giải vào boot layer. Thư mục plugins chứa các plugin cần nạp động. Không đặt plugin vào module path khởi động của host nếu mục tiêu là tạo child layer riêng.

Có thể liệt kê các module reference tìm được:

~~~java
Set<ModuleReference> references = finder.findAll();
~~~

Mỗi ModuleReference có descriptor để đọc tên mô-đun, requires, exports, uses và provides mà không cần khởi tạo class của plugin.

Đây là điểm hữu ích khi xây dựng plugin registry: host có thể kiểm tra metadata trước khi tạo layer hoặc gọi constructor provider.

## 6. Khám phá provider từ module descriptor

Để tìm plugin module cung cấp một service cụ thể, duyệt ModuleDescriptor.provides() của các module reference:

~~~java
String serviceName = Plugin.class.getName();

Set<String> roots = finder.findAll().stream()
        .filter(reference -> reference.descriptor().provides().stream()
                .anyMatch(provides -> provides.service().equals(serviceName)))
        .map(reference -> reference.descriptor().name())
        .collect(Collectors.toSet());
~~~

Đoạn code này:

1. Lấy descriptor của từng mô-đun trong thư mục plugin.
2. Kiểm tra danh sách provides.
3. Chỉ giữ mô-đun khai báo service type đúng bằng tên lớp Plugin.
4. Thu thập tên mô-đun để dùng làm root khi resolve.

Việc kiểm tra descriptor không cần nạp implementation class. Nhờ đó, host có thể phân biệt plugin module với thư viện phụ trợ chỉ nằm cùng thư mục.

Nếu không tìm thấy root nào, ứng dụng nên xử lý rõ ràng:

~~~java
if (roots.isEmpty()) {
    System.out.println("No plugins found");
    return;
}
~~~

Không nên tạo một layer rỗng rồi giả định rằng plugin đã được nạp. Trạng thái không có plugin là một trường hợp bình thường của hệ thống có thể mở rộng.

## 7. Phân giải dependency và tạo ModuleLayer con

Sau khi xác định root module, cần phân giải chúng cùng các dependency. Lấy configuration của boot layer làm parent:

~~~java
ModuleLayer parent = ModuleLayer.boot();

Configuration configuration = parent.configuration()
        .resolve(finder, ModuleFinder.of(), roots);
~~~

Tham số của resolve:

- finder là nơi tìm các mô-đun plugin và dependency của chúng.
- ModuleFinder.of() là finder rỗng cho vị trí tìm kiếm thứ hai.
- roots là tên các mô-đun plugin cần đưa vào configuration mới.

Configuration resolver kiểm tra requires và tạo đồ thị mô-đun có thể phân giải. Các dependency đã tồn tại trong parent configuration có thể được dùng từ parent; các mô-đun mới được tìm từ finder của plugin.

Sau đó tạo layer:

~~~java
ModuleLayer pluginLayer =
        ModuleLayer.defineModulesWithOneLoader(
                configuration,
                List.of(parent),
                ClassLoader.getSystemClassLoader())
        .layer();
~~~

Layer mới có parent là boot layer. Các mô-đun plugin trong configuration được định nghĩa và nạp bởi class loader do API tạo ra.

### Chọn chiến lược class loader

JPMS cung cấp các cách định nghĩa layer phổ biến:

| API | Cách tổ chức class loader | Khi phù hợp |
|---|---|---|
| defineModulesWithOneLoader | Một class loader cho các mô-đun trong layer mới | Plugin có quan hệ chặt chẽ, chia sẻ dependency và không cần tách loader riêng |
| defineModulesWithManyLoaders | Một class loader cho mỗi mô-đun trong layer mới | Cần tách phạm vi nạp lớp giữa các mô-đun |
| defineModules | Ứng dụng cung cấp hàm ánh xạ tên mô-đun sang class loader | Hệ thống có chiến lược class loader riêng |

Một loader cho tất cả plugin thường đơn giản hơn. Nhiều loader giúp tách việc nạp lớp nhưng làm cấu hình, giao tiếp và chẩn đoán phức tạp hơn.

ModuleLayer và class loader không phải sandbox bảo mật. Plugin không đáng tin cậy không nên được chạy trực tiếp trong cùng tiến trình chỉ vì nó nằm trong một layer riêng. Nếu cần ranh giới tin cậy mạnh, hãy cân nhắc chạy plugin trong tiến trình hoặc môi trường hệ điều hành riêng.

## 8. Nạp provider từ đúng ModuleLayer

Khi plugin nằm trong child layer, dùng overload nhận ModuleLayer:

~~~java
ServiceLoader<Plugin> loader =
        ServiceLoader.load(pluginLayer, Plugin.class);
~~~

Đây là điểm quan trọng của mô hình plugin động. ServiceLoader.load(Plugin.class) thông thường dựa trên thread context class loader; nó không thay thế việc chỉ rõ layer khi provider nằm trong một ModuleLayer tùy chỉnh.

ServiceLoader.load(pluginLayer, Plugin.class) tìm provider trong layer được chỉ định và các parent layer của nó. Do đó, provider ở child layer có thể được khám phá, đồng thời service type vẫn là lớp Plugin đã được nạp ở parent layer.

Việc duyệt provider có tính lazy: provider thường được khởi tạo khi iterator yêu cầu phần tử tiếp theo. Vì vậy, lỗi cấu hình có thể chỉ xuất hiện khi duyệt ServiceLoader chứ không nhất thiết xuất hiện lúc tạo đối tượng ServiceLoader.

Ví dụ:

~~~java
for (Plugin plugin : ServiceLoader.load(pluginLayer, Plugin.class)) {
    System.out.println(plugin.name());
}
~~~

Nếu cần xem metadata provider trước khi khởi tạo instance, có thể dùng ServiceLoader.stream() và ServiceLoader.Provider.type(). Điều này hữu ích cho registry muốn kiểm tra annotation hoặc class name trước khi gọi Provider.get().

Thứ tự provider không nên được coi là thứ tự ưu tiên nghiệp vụ. Nếu ứng dụng cần thứ tự xác định, hãy lấy provider, đọc metadata như name hoặc priority, rồi sắp xếp theo quy tắc do ứng dụng định nghĩa.

## 9. Ví dụ hoàn chỉnh: host nạp plugin trong child layer

Ví dụ gồm ba mô-đun:

- com.acme.plugin.api: service interface.
- com.acme.host: ứng dụng tiêu thụ service.
- com.acme.plugin.csv: plugin triển khai service.

### Cấu trúc thư mục

~~~text
src/
├── com.acme.plugin.api/
│   ├── module-info.java
│   └── com/acme/plugin/api/Plugin.java
├── com.acme.host/
│   ├── module-info.java
│   └── com/acme/host/Main.java
└── com.acme.plugin.csv/
    ├── module-info.java
    └── com/acme/plugin/csv/CsvPlugin.java
~~~

### Service API

src/com.acme.plugin.api/module-info.java:

~~~java
module com.acme.plugin.api {
    exports com.acme.plugin.api;
}
~~~

src/com.acme.plugin.api/com/acme/plugin/api/Plugin.java:

~~~java
package com.acme.plugin.api;

public interface Plugin {
    String name();
    String process(String input);
}
~~~

### Host module

src/com.acme.host/module-info.java:

~~~java
module com.acme.host {
    requires com.acme.plugin.api;
    uses com.acme.plugin.api.Plugin;
}
~~~

src/com.acme.host/com/acme/host/Main.java:

~~~java
package com.acme.host;

import com.acme.plugin.api.Plugin;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;
import java.util.Set;
import java.util.stream.Collectors;

public class Main {
    public static void main(String[] args) {
        Path pluginDirectory =
                Path.of(args.length == 0 ? "plugins" : args[0]);

        try {
            ModuleFinder finder = ModuleFinder.of(pluginDirectory);
            String serviceName = Plugin.class.getName();

            Set<String> roots = finder.findAll().stream()
                    .filter(reference -> reference.descriptor().provides()
                            .stream()
                            .anyMatch(provides ->
                                    provides.service().equals(serviceName)))
                    .map(reference -> reference.descriptor().name())
                    .collect(Collectors.toSet());

            if (roots.isEmpty()) {
                System.out.println("No plugins found");
                return;
            }

            ModuleLayer parent = ModuleLayer.boot();
            var configuration = parent.configuration()
                    .resolve(finder, ModuleFinder.of(), roots);

            ModuleLayer pluginLayer =
                    ModuleLayer.defineModulesWithOneLoader(
                            configuration,
                            List.of(parent),
                            ClassLoader.getSystemClassLoader())
                    .layer();

            try {
                for (Plugin plugin :
                        ServiceLoader.load(pluginLayer, Plugin.class)) {
                    try {
                        System.out.println(
                                plugin.name() + ": "
                                + plugin.process("JPMS"));
                    } catch (RuntimeException pluginError) {
                        System.err.println(
                                "Plugin failed: " + plugin.name()
                                + " - " + pluginError.getMessage());
                    }
                }
            } catch (ServiceConfigurationError error) {
                System.err.println(
                        "Plugin configuration error: "
                        + error.getMessage());
                System.exit(2);
            }
        } catch (java.lang.module.FindException
                | java.lang.module.ResolutionException error) {
            System.err.println(
                    "Cannot resolve plugin modules: "
                    + error.getMessage());
            System.exit(1);
        }
    }
}
~~~

Host thực hiện các bước theo thứ tự: tìm module reference, chọn root có provides đúng service, resolve dependency, tạo layer, rồi nạp provider bằng ServiceLoader overload nhận layer.

### Plugin module

src/com.acme.plugin.csv/module-info.java:

~~~java
module com.acme.plugin.csv {
    requires com.acme.plugin.api;
    provides com.acme.plugin.api.Plugin
        with com.acme.plugin.csv.CsvPlugin;
}
~~~

src/com.acme.plugin.csv/com/acme/plugin/csv/CsvPlugin.java:

~~~java
package com.acme.plugin.csv;

import com.acme.plugin.api.Plugin;

public final class CsvPlugin implements Plugin {
    public String name() {
        return "CSV";
    }

    public String process(String input) {
        return "processed " + input;
    }
}
~~~

Package com.acme.plugin.csv không cần exports vì host chỉ tương tác qua interface Plugin. Provider được ServiceLoader tạo theo khai báo provides trong module descriptor.

### Biên dịch và đóng gói

Mở terminal tại thư mục chứa src/:

~~~bash
javac --release 17 -d out --module-source-path src -m com.acme.plugin.api,com.acme.host,com.acme.plugin.csv
~~~

Tạo thư mục chứa mô-đun khởi động và plugin:

~~~bash
mkdir mods
mkdir plugins
~~~

Đóng gói service API và host vào mods:

~~~bash
jar --create --file mods/com.acme.plugin.api.jar -C out/com.acme.plugin.api .
jar --create --file mods/com.acme.host.jar --main-class com.acme.host.Main -C out/com.acme.host .
~~~

Đóng gói plugin riêng vào plugins:

~~~bash
jar --create --file plugins/com.acme.plugin.csv.jar -C out/com.acme.plugin.csv .
~~~

Kiểm tra provider metadata:

~~~bash
jar --describe-module --file plugins/com.acme.plugin.csv.jar
~~~

Kết quả cần có các dòng tương tự:

~~~text
com.acme.plugin.csv
requires com.acme.plugin.api
requires java.base mandated
provides com.acme.plugin.api.Plugin with com.acme.plugin.csv.CsvPlugin
~~~

### Chạy host

Tại thư mục gốc của ví dụ:

~~~bash
java --module-path mods -m com.acme.host plugins
~~~

Host được nạp từ mods. Thư mục plugins được truyền như đối số ứng dụng, nên plugin JAR được tìm và nạp vào child layer lúc chạy.

Stdout chính xác với một plugin CSV:

~~~text
CSV: processed JPMS
~~~

Nếu thư mục plugin rỗng, stdout là:

~~~text
No plugins found
~~~

Ví dụ đã được biên dịch bằng javac --release 17 và chạy trên JDK 24. Plugin CSV được phát hiện từ provides trong descriptor, nạp qua child ModuleLayer và gọi thành công qua service API ở parent layer.

## 10. resolve và resolveAndBind

Hai phương thức thường gặp của Configuration là resolve và resolveAndBind.

- **resolve** phân giải các root module cùng dependency requires của chúng.
- **resolveAndBind** thực hiện resolution và thêm bước service binding cho các service được sử dụng trong đồ thị mô-đun đang được phân giải.

Trong ví dụ, host chủ động quét provides để chọn root plugin module. Vì vậy, resolve là đủ: mỗi plugin đã được chọn rõ ràng, và các dependency của plugin được phân giải cùng nó.

resolveAndBind hữu ích khi mô hình resolution cần tự động bổ sung provider cho service được dùng bởi các mô-đun trong đồ thị đang phân giải. Nó không thay thế việc thiết kế root module, kiểm tra plugin directory hoặc gọi ServiceLoader. Hãy chọn phương thức theo cách hệ thống xác định tập mô-đun cần nạp.

## 11. Xử lý lỗi và vận hành plugin

### Không có plugin

Không có provider là trạng thái hợp lệ. Host có thể tiếp tục chạy với chức năng cơ bản, hiển thị thông báo hoặc từ chối khởi động tùy yêu cầu sản phẩm.

### Không tìm thấy dependency

ModuleFinder hoặc configuration resolution có thể thất bại nếu plugin thiếu mô-đun được yêu cầu, có module descriptor không hợp lệ hoặc có dependency xung đột.

Hãy ghi rõ tên mô-đun và đường dẫn plugin để việc chẩn đoán có thể truy nguyên. Tránh bắt mọi RuntimeException rồi bỏ qua, vì điều đó có thể che mất lỗi cấu hình thật.

### ServiceConfigurationError

ServiceLoader có thể phát sinh ServiceConfigurationError khi provider không hợp lệ, không thể khởi tạo, không đáp ứng service type hoặc khai báo service không nhất quán.

Bắt lỗi quanh quá trình duyệt provider. Nếu một plugin bị lỗi, chính sách của host có thể là dừng toàn bộ quá trình nạp hoặc ghi nhận plugin lỗi và tiếp tục với các plugin khác. Chọn chính sách rõ ràng và nhất quán.

### Lỗi khi thực thi plugin

Một provider có thể khởi tạo thành công nhưng ném exception trong method nghiệp vụ. Xử lý lỗi này riêng cho từng plugin nếu các plugin độc lập và host cho phép tiếp tục.

Không nên để một plugin làm hỏng toàn bộ quá trình chỉ vì một lỗi đầu vào hoặc lỗi xử lý có thể cô lập.

### Vòng đời và nạp lại plugin

ModuleLayer không có phương thức close để dỡ một plugin ngay lập tức. Việc một layer và class loader có thể được thu hồi phụ thuộc vào việc chúng không còn được tham chiếu, cùng với các thread, context class loader, callback, cache và resource mà plugin đã tạo.

Nếu cần reload:

1. Ngừng gửi request mới đến plugin cũ.
2. Yêu cầu plugin dừng công việc và đóng resource do nó quản lý.
3. Dừng thread hoặc executor thuộc plugin theo hợp đồng lifecycle.
4. Gỡ listener, callback và reference từ host.
5. Tạo layer mới cho phiên bản plugin mới.
6. Chỉ giữ reference đến layer cũ khi còn công việc thực sự cần nó.

Nếu yêu cầu reload hoặc cách ly nghiêm ngặt, chạy mỗi plugin hoặc nhóm plugin trong tiến trình riêng có thể dễ quản lý hơn. Một ModuleLayer riêng tự nó không bảo đảm khả năng unload tức thời hay cô lập bảo mật.

## 12. Những nguyên tắc thiết kế nên giữ

- Đặt service interface trong mô-đun API ổn định ở parent layer.
- Host khai báo requires và uses cho service type.
- Plugin khai báo requires API và provides ... with ... trong module descriptor.
- Quét metadata trước khi khởi tạo provider.
- Chọn rõ root module và kiểm tra dependency khi resolve.
- Dùng ServiceLoader.load(layer, service) cho provider trong custom layer.
- Không dựa vào thứ tự provider để quyết định ưu tiên nghiệp vụ.
- Xác định chính sách lỗi riêng cho module resolution, provider creation và lời gọi plugin.
- Không coi ModuleLayer hoặc class loader là ranh giới bảo mật.
- Thiết kế lifecycle để host có thể dừng plugin và giải phóng reference khi cần.

## Kết luận

JPMS kết hợp module descriptor, ModuleFinder, Configuration, ModuleLayer và ServiceLoader để xây dựng cơ chế plugin động. Service API tạo hợp đồng chung; uses và provides khai báo phía tiêu thụ và cung cấp; ModuleFinder tìm plugin JAR; Configuration.resolve phân giải dependency; ModuleLayer tạo môi trường nạp mô-đun con; ServiceLoader.load(layer, service) tìm provider trong layer đó.

Cách tổ chức này cho phép host kiểm soát thời điểm và tập mô-đun được nạp, giữ plugin tách khỏi boot layer và vẫn giao tiếp qua một service API ổn định. Khi triển khai thực tế, hãy bổ sung xử lý lỗi, quản lý vòng đời và kiểm thử dependency để hệ thống plugin hoạt động có thể dự đoán trên các JDK hiện đại.
