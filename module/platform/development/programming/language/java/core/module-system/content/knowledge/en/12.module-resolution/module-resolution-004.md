# Configuration.resolve và resolveAndBind

Java Platform Module System (JPMS) không chỉ mô tả dependency trong `module-info.java`; nó còn cần tìm các module thực tế và giải quyết toàn bộ quan hệ phụ thuộc trước khi tạo một module layer. Hai phương thức `Configuration.resolve(...)` và `Configuration.resolveAndBind(...)` thực hiện bước phân giải đó.

Cả hai phương thức đều tạo ra một đối tượng `Configuration` mới từ các module gốc (roots), các module có thể tìm thấy qua `ModuleFinder` và những configuration cha đã tồn tại. Điểm khác biệt quan trọng là `resolveAndBind` thực hiện thêm **service binding**: nó tìm các provider của service mà module trong cấu hình sử dụng, rồi bổ sung provider module cùng dependency cần thiết vào kết quả.

Các phương thức này không tự nạp class hoặc khởi tạo plugin. Chúng tạo module configuration; sau đó ứng dụng dùng `ModuleLayer` để định nghĩa và nạp các module đó.

## 1. Configuration là gì?

`Configuration` biểu diễn kết quả phân giải một tập hợp module. Nó chứa module graph đã được giải quyết, cùng quan hệ với các configuration cha.

Trong một ứng dụng thông thường, configuration nền tảng có thể lấy từ boot layer:

~~~java
Configuration bootConfiguration =
    ModuleLayer.boot().configuration();
~~~

Boot layer chứa các module nền tảng và những module đã được khởi tạo cho runtime hiện tại. Khi cần nạp plugin hoặc một nhóm module bổ sung, ứng dụng có thể tạo configuration con dựa trên configuration của boot layer.

Cần phân biệt:

- **`ModuleFinder`**: tìm và cung cấp thông tin về các module có thể quan sát được từ một nguồn.
- **`Configuration`**: kết quả phân giải roots và dependency thành một module graph hợp lệ.
- **`ModuleLayer`**: môi trường runtime định nghĩa các module từ configuration và gắn chúng với class loader.

Luồng tổng quát:

~~~text
ModuleFinder + root module names + parent Configuration
                         |
                         v
            Configuration.resolve(...)
                         |
                         v
              Resolved Configuration
                         |
                         v
          ModuleLayer.defineModules...
                         |
                         v
             Runtime ModuleLayer
                         |
                         v
             Load classes / services
~~~

Vì vậy, tạo được một configuration chưa có nghĩa plugin đã được khởi chạy. Ứng dụng còn cần tạo layer và sử dụng class hoặc service từ layer đó.

## 2. ModuleFinder: nguồn tìm module

`ModuleFinder` là abstraction để tìm module theo tên và liệt kê các module mà nguồn đó cung cấp.

Một nguồn thường gặp là thư mục chứa modular JAR, automatic module hoặc exploded module:

~~~java
import java.lang.module.ModuleFinder;
import java.nio.file.Path;

ModuleFinder pluginFinder =
    ModuleFinder.of(Path.of("plugins"));
~~~

`ModuleFinder.of(Path...)` có thể tìm module trong các đường dẫn được chỉ định. Các đường dẫn thường là:

- Modular JAR có `module-info.class`.
- JAR không có descriptor, có thể được nhận diện như automatic module.
- Thư mục chứa cấu trúc module đã biên dịch (exploded module).

Có thể kiểm tra các module finder tìm thấy:

~~~java
pluginFinder.findAll().forEach(reference ->
    System.out.println(reference.descriptor().name())
);
~~~

Mỗi `ModuleReference` cung cấp descriptor và thông tin tham chiếu tới nội dung module. `ModuleFinder` không tự resolve dependency; nó chỉ giúp tìm module để bước phân giải sử dụng.

Một số factory method hữu ích:

- `ModuleFinder.of(paths...)`: tìm module từ các đường dẫn cụ thể.
- `ModuleFinder.ofSystem()`: tìm các module của runtime image.
- `ModuleFinder.of()`: tạo finder rỗng, không cung cấp module nào.

Có thể kết hợp nhiều finder bằng `ModuleFinder.compose(...)` nếu ứng dụng cần tìm module từ nhiều nguồn. Khi có tên module trùng lặp trong cùng tập nguồn quan sát, việc tìm module có thể thất bại; hãy tránh đặt các phiên bản hoặc bản sao cùng tên module vào các vị trí gây xung đột.

## 3. Ý nghĩa của before, after và roots

Hai phương thức `resolve` và `resolveAndBind` nhận các tham số quan trọng:

~~~java
Configuration.resolve(
    ModuleFinder before,
    ModuleFinder after,
    Collection<String> roots
);
~~~

- **`before`**: finder được dùng để tìm module trước khi xét các parent configuration.
- **`after`**: finder được dùng để tìm module sau khi xét các parent configuration.
- **`roots`**: tập tên module gốc mà ứng dụng muốn đưa vào configuration mới.

Thứ tự tìm kiếm này cho phép ứng dụng kết hợp nguồn module của layer mới với các module đã có ở parent layer. Trong trường hợp plugin đơn giản, thường dùng finder chứa plugin làm `before` và finder rỗng làm `after`.

Ví dụ:

~~~java
ModuleFinder pluginFinder =
    ModuleFinder.of(Path.of("plugins"));

Configuration parent =
    ModuleLayer.boot().configuration();

Configuration configuration = parent.resolve(
    pluginFinder,
    ModuleFinder.of(),
    Set.of("com.example.plugin")
);
~~~

Ở đây:

1. `com.example.plugin` là root module.
2. JPMS tìm module này từ `pluginFinder`.
3. Các directive `requires` trong descriptor của plugin được lần theo.
4. Những module dependency cần thiết được tìm trong các nguồn quan sát và parent configuration.
5. Nếu mọi module đều có thể tìm thấy và dependency graph hợp lệ, phương thức trả về configuration mới.

`roots` không phải danh sách tất cả dependency. Chỉ cần khai báo các module mà ứng dụng muốn khởi đầu; JPMS tự resolve các dependency được khai báo bằng `requires` theo quy tắc module system.

Nếu root module không tồn tại, dependency bị thiếu, có split package hoặc module graph không hợp lệ, quá trình resolve có thể thất bại.

## 4. Configuration.resolve(): resolve dependency tường minh

`resolve(...)` phân giải các root module và dependency mà chúng khai báo. Quá trình này đi theo các directive như `requires`, kể cả các dependency được kéo theo qua module khác.

Ví dụ module plugin:

~~~java
module com.example.plugin {
    requires com.example.plugin.api;
    requires java.logging;
}
~~~

Ứng dụng có thể resolve plugin:

~~~java
ModuleFinder finder =
    ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    ModuleLayer.boot().configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.example.plugin")
    );
~~~

Configuration mới chứa plugin root và các module cần thiết theo dependency graph. Nếu `com.example.plugin.api` đã có trong parent configuration, JPMS có thể dùng module từ parent; nếu chưa, nó cần được tìm thấy trong các finder được cung cấp.

Khi nào nên dùng `resolve`?

- Ứng dụng biết rõ các module cần nạp.
- Dependency giữa các module đã được khai báo bằng `requires`.
- Không cần tự động bổ sung provider module chỉ vì chúng cung cấp service mà root module sử dụng.
- Ứng dụng muốn kiểm soát roots và tập module được resolve một cách tường minh.

`resolve` không thực hiện service binding. Nếu plugin provider không được root module yêu cầu bằng `requires`, provider có thể không xuất hiện trong configuration chỉ vì nó có directive `provides`.

## 5. Configuration.resolveAndBind(): resolve kèm service binding

`resolveAndBind(...)` thực hiện việc resolve như `resolve(...)`, sau đó thực hiện service binding. JPMS xem các directive `uses` trong những module đã resolve, tìm các module provider quan sát được có directive `provides` tương ứng, rồi bổ sung provider module vào configuration.

Ví dụ service API:

~~~java
package com.example.plugin.api;

public interface Plugin {
    void start();
}
~~~

Module API:

~~~java
module com.example.plugin.api {
    exports com.example.plugin.api;
}
~~~

Module ứng dụng khai báo sử dụng service:

~~~java
module com.example.app {
    requires com.example.plugin.api;

    uses com.example.plugin.api.Plugin;
}
~~~

Một provider module:

~~~java
module com.example.plugin.audit {
    requires com.example.plugin.api;

    provides com.example.plugin.api.Plugin
        with com.example.plugin.audit.AuditPlugin;
}
~~~

Ứng dụng có thể resolve root module `com.example.app` và để JPMS tìm provider:

~~~java
ModuleFinder pluginFinder =
    ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    ModuleLayer.boot().configuration().resolveAndBind(
        pluginFinder,
        ModuleFinder.of(),
        Set.of("com.example.app")
    );
~~~

Nếu `com.example.app` khai báo `uses com.example.plugin.api.Plugin` và `com.example.plugin.audit` là provider quan sát được trong các nguồn tìm kiếm, service binding có thể bổ sung provider module vào configuration cùng các dependency của nó.

Service binding có thể tiếp tục tìm provider cho các service mà những module provider được thêm vào sử dụng. Vì vậy, configuration kết quả có thể chứa nhiều module hơn tập roots ban đầu và dependency `requires` trực tiếp.

Cần nhớ:

- `resolveAndBind` không khởi tạo provider object.
- Nó chỉ đưa các provider module phù hợp vào configuration.
- Việc tạo instance provider vẫn do `ServiceLoader` thực hiện khi ứng dụng yêu cầu.
- Provider phải có trong phạm vi module finder/layer được tìm kiếm.
- Consumer vẫn phải khai báo `uses`; provider phải khai báo `provides`.

## 6. So sánh resolve và resolveAndBind

| Tiêu chí | `resolve(...)` | `resolveAndBind(...)` |
|---|---|---|
| Resolve roots | Có | Có |
| Resolve dependency `requires` | Có | Có |
| Tìm provider theo service binding | Không | Có |
| Bổ sung module chỉ vì module đó cung cấp service được dùng | Không | Có |
| Khởi tạo provider instance | Không | Không |
| Phù hợp | Dependency tường minh | Plugin/service provider |

Ví dụ dễ nhớ:

- Ứng dụng khai báo `requires com.example.plugin.audit`: `resolve` sẽ đưa provider module vào vì nó là dependency tường minh.
- Ứng dụng chỉ khai báo `uses Plugin`, provider module được tìm thấy trong finder: `resolveAndBind` có thể tự bổ sung provider module theo service binding.
- Cả hai phương thức đều cần một bước tạo `ModuleLayer` trước khi class trong module mới có thể được nạp và sử dụng trong runtime.

Không nên dùng `resolveAndBind` với kỳ vọng nó tìm mọi plugin ở bất cứ đâu trên máy. Nó chỉ tìm trong các module có thể quan sát qua những finder và parent configuration đã cung cấp.

## 7. Tạo ModuleLayer từ Configuration

Sau khi có configuration hợp lệ, ứng dụng có thể tạo layer con:

~~~java
ModuleFinder pluginFinder =
    ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    ModuleLayer.boot().configuration().resolve(
        pluginFinder,
        ModuleFinder.of(),
        Set.of("com.example.plugin")
    );

ModuleLayer pluginLayer =
    ModuleLayer.boot().defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader()
    );
~~~

`defineModulesWithOneLoader` định nghĩa các module trong configuration bằng một class loader chung cho layer mới, với class loader được chỉ định làm parent.

Một lựa chọn khác là `defineModulesWithManyLoaders`, tạo loader riêng cho từng module. Việc chọn một loader hay nhiều loader phụ thuộc kiến trúc plugin, cách cô lập class và nhu cầu chia sẻ package/class giữa các module.

Một số lưu ý:

- Configuration phải được tạo từ parent configuration tương ứng với layer mà bạn gọi `defineModules...`.
- Module layer mới có thể đọc các module ở parent theo quy tắc JPMS; parent không tự động đọc ngược module ở child layer.
- Việc tạo layer không có nghĩa mọi class trong mọi module đều được khởi tạo.
- Có thể kiểm tra module đã được định nghĩa:

~~~java
pluginLayer.findModule("com.example.plugin")
    .ifPresent(module ->
        System.out.println(module.getName()));
~~~

## 8. Ví dụ plugin sử dụng resolveAndBind

Giả sử thư mục `plugins/` chứa các module:

~~~text
plugins/
├── com.example.app.jar
├── com.example.plugin.api.jar
├── com.example.plugin.audit.jar
└── com.example.plugin.metrics.jar
~~~

Ứng dụng khai báo:

~~~java
module com.example.app {
    requires com.example.plugin.api;

    uses com.example.plugin.api.Plugin;
}
~~~

Provider audit:

~~~java
module com.example.plugin.audit {
    requires com.example.plugin.api;

    provides com.example.plugin.api.Plugin
        with com.example.plugin.audit.AuditPlugin;
}
~~~

Provider metrics:

~~~java
module com.example.plugin.metrics {
    requires com.example.plugin.api;

    provides com.example.plugin.api.Plugin
        with com.example.plugin.metrics.MetricsPlugin;
}
~~~

Có thể resolve ứng dụng cùng provider bằng:

~~~java
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.ServiceLoader;
import java.util.Set;

ModuleFinder finder =
    ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    ModuleLayer.boot().configuration().resolveAndBind(
        finder,
        ModuleFinder.of(),
        Set.of("com.example.app")
    );

ModuleLayer layer =
    ModuleLayer.boot().defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader()
    );

ServiceLoader<Plugin> plugins =
    ServiceLoader.load(layer, Plugin.class);

for (Plugin plugin : plugins) {
    plugin.start();
}
~~~

Trong ví dụ, `com.example.app` là root. Module descriptor của nó khai báo `uses Plugin`; hai provider module đều quan sát được trong `finder`. Service binding có thể đưa cả hai provider vào configuration. Sau khi layer được tạo, `ServiceLoader.load(layer, Plugin.class)` tìm provider trong layer và các ancestor layer theo quy tắc của API.

Consumer không cần viết `requires com.example.plugin.audit` hoặc `requires com.example.plugin.metrics`. Việc thêm provider mới có thể được thực hiện bằng cách thêm module provider vào thư mục plugin và bảo đảm nó được finder/layer nhìn thấy.

## 9. Kiểm tra kết quả resolve

Sau khi tạo configuration, có thể xem các module đã resolve:

~~~java
configuration.modules().forEach(resolvedModule ->
    System.out.println(resolvedModule.name())
);
~~~

Danh sách này hữu ích để kiểm tra:

- Root module có được đưa vào không.
- Dependency `requires` có được resolve không.
- Provider module có được bổ sung khi dùng `resolveAndBind` không.
- Có module ngoài dự kiến được kéo vào qua dependency hoặc service binding không.

Có thể kiểm tra các provider service được khám phá trong layer:

~~~java
ServiceLoader<Plugin> plugins =
    ServiceLoader.load(layer, Plugin.class);

plugins.stream().forEach(provider ->
    System.out.println(provider.type().getName())
);
~~~

`Provider.type()` cho phép xem provider type trước khi gọi `Provider.get()`. Điều này hữu ích để xác nhận provider nào được tìm thấy mà chưa khởi tạo tất cả instance.

Nếu configuration không chứa provider mong đợi, hãy kiểm tra finder có tìm thấy module đó không, module provider có `provides` đúng service type không, consumer có `uses` đúng service type không và provider có nằm trong phạm vi quan sát của quá trình resolve không.

## 10. Các lỗi thường gặp

**Root module không tìm thấy.** Tên trong `roots` không tồn tại trong các nguồn tìm kiếm hoặc parent configuration. Kiểm tra tên module bằng `jar --describe-module` và đường dẫn finder.

**Thiếu dependency của plugin.** Provider module có `requires` một module không có trong finder hoặc parent configuration. Quá trình resolve sẽ thất bại.

**Dùng `resolve` nhưng mong provider tự xuất hiện.** `resolve` chỉ xử lý roots và dependency tường minh. Nếu cần service binding, cân nhắc `resolveAndBind`.

**Dùng `resolveAndBind` nhưng không có provider.** Kiểm tra consumer `uses`, provider `provides`, module finder, module layer và cấu hình triển khai.

**Nhầm Configuration với ModuleLayer.** Configuration chỉ là module graph đã resolve; phải định nghĩa layer mới có môi trường runtime để nạp module.

**Gọi ServiceLoader ở sai layer.** Nếu plugin nằm trong custom layer, hãy dùng `ServiceLoader.load(layer, Service.class)` với đúng layer thay vì chỉ tìm theo layer mặc định.

**Cho rằng resolveAndBind khởi tạo plugin.** Service binding chỉ bổ sung provider module vào configuration. Provider object được tạo khi ServiceLoader yêu cầu instance.

**Dùng thứ tự provider để quyết định plugin mặc định.** JPMS không cung cấp chính sách ưu tiên nghiệp vụ. Hãy dùng ID, priority hoặc cấu hình ứng dụng.

## 11. Khi nào chọn phương thức nào?

Chọn `resolve` khi ứng dụng đã biết rõ module nào phải được đưa vào layer và các dependency được mô tả bằng `requires`. Cách này phù hợp với module graph tường minh, ít phụ thuộc vào khám phá service.

Chọn `resolveAndBind` khi ứng dụng dùng SPI và muốn JPMS tự tìm provider module cho các service mà module đã resolve khai báo `uses`. Đây là lựa chọn phù hợp cho hệ thống plugin có thể bổ sung provider mà không sửa dependency trực tiếp của consumer.

Trong cả hai trường hợp, hãy giữ trách nhiệm rõ ràng:

- Module descriptor khai báo dependency và service contract.
- ModuleFinder xác định nguồn module có thể tìm.
- Configuration giải quyết module graph.
- ModuleLayer định nghĩa các module trong runtime.
- ServiceLoader khám phá và khởi tạo provider.
- Ứng dụng quyết định provider nào được dùng và theo thứ tự nào.

## 12. Tự kiểm tra

Khi xây dựng module layer động, hãy trả lời:

1. Root module nào cần được resolve?
2. ModuleFinder đang tìm module ở thư mục, JAR hoặc nguồn nào?
3. Các dependency `requires` của roots có đầy đủ không?
4. Consumer đã khai báo `uses` cho service cần tìm chưa?
5. Provider module đã khai báo `provides` đúng service type chưa?
6. Nên dùng `resolve` hay `resolveAndBind`?
7. Configuration mới có những module nào sau khi resolve?
8. Layer được tạo với một class loader hay nhiều class loader?
9. ServiceLoader đang tìm trong đúng layer chưa?
10. Nếu có nhiều provider, chính sách chọn hoặc chạy provider được định nghĩa ở đâu?

Hiểu rõ `resolve`, `resolveAndBind` và `ModuleLayer` giúp xây dựng cơ chế plugin có thể mở rộng mà vẫn kiểm soát được dependency. JPMS thực hiện việc tìm và phân giải module; ứng dụng vẫn phải chịu trách nhiệm về vòng đời, cấu hình và chính sách sử dụng provider.
