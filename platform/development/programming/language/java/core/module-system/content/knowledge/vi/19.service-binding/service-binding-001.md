# Bind service provider vào module graph

## Mục tiêu

Sau bài này, bạn có thể khai báo service consumer và provider bằng JPMS, giải thích cách service binding tìm provider module, dùng `Configuration.resolveAndBind(...)` để đưa provider vào module graph, rồi dùng `ServiceLoader` để tìm và tạo instance của provider ở runtime.

## 1. Service trong Java và vai trò của module graph

Service là một hợp đồng mà nhiều implementation có thể cung cấp. Consumer phụ thuộc vào service interface, còn provider module cung cấp một hoặc nhiều implementation. Cách tổ chức này giúp ứng dụng chọn implementation theo môi trường, cấu hình hoặc thành phần được cài đặt mà không cần consumer phụ thuộc trực tiếp vào từng provider.

Trong Java, `ServiceLoader<S>` là API tiêu chuẩn để tìm provider của service type `S`. Với JPMS, hai directive mô tả quan hệ này:

- `uses` khai báo module cần một service type.
- `provides ... with ...` khai báo module cung cấp service type bằng một hoặc nhiều provider class.

Service binding là bước trong quá trình phân giải module. Module system tìm các provider module phù hợp với những service được các module trong graph sử dụng, rồi thêm provider module và các dependency cần thiết của chúng vào configuration. Nhờ đó, provider có thể được đưa vào layer mà không cần consumer khai báo `requires` trực tiếp tới từng provider.

Cần phân biệt hai giai đoạn:

1. **Service binding** quyết định provider module nào thuộc configuration/module graph.
2. **Service loading** dùng `ServiceLoader` để tìm provider và tạo instance khi ứng dụng cần.

Việc một provider module đã được bind vào graph không có nghĩa là provider object đã được khởi tạo.

## 2. Khai báo service API, consumer và provider

Ví dụ dùng service `Formatter` để chuyển đổi chuỗi.

### Module chứa service API

Cấu trúc:

~~~text
com.acme.spi/
  module-info.java
  com/acme/spi/Formatter.java
~~~

`module-info.java`:

~~~java
module com.acme.spi {
    exports com.acme.spi;
}
~~~

Service interface:

~~~java
package com.acme.spi;

public interface Formatter {
    String format(String input);
}
~~~

Package chứa service interface được export để consumer và provider có thể tham chiếu kiểu `Formatter`.

### Module consumer

Cấu trúc:

~~~text
com.acme.app/
  module-info.java
  com/acme/app/Main.java
~~~

`module-info.java`:

~~~java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.Formatter;
}
~~~

Hai directive có ý nghĩa riêng:

- `requires com.acme.spi` tạo dependency để consumer đọc được service API.
- `uses com.acme.spi.Formatter` khai báo consumer sử dụng service này và cho phép service binding tìm các module cung cấp nó.

Consumer không cần khai báo `requires com.acme.provider.upper`. Đây là điểm quan trọng: consumer phụ thuộc vào abstraction là service API, không phụ thuộc vào danh sách implementation.

### Module provider

Cấu trúc:

~~~text
com.acme.provider.upper/
  module-info.java
  com/acme/provider/upper/UppercaseFormatter.java
~~~

`module-info.java`:

~~~java
module com.acme.provider.upper {
    requires com.acme.spi;

    provides com.acme.spi.Formatter
        with com.acme.provider.upper.UppercaseFormatter;
}
~~~

Provider module cần đọc module chứa service interface, vì implementation tham chiếu đến `Formatter`. Directive `provides` đăng ký implementation với service type.

Implementation:

~~~java
package com.acme.provider.upper;

import com.acme.spi.Formatter;
import java.util.Locale;

public final class UppercaseFormatter implements Formatter {
    public UppercaseFormatter() {
    }

    @Override
    public String format(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

Với cách khai báo phổ biến này, provider class là class public triển khai service interface và có public constructor không tham số để `ServiceLoader` tạo instance.

Một service có thể có nhiều provider class:

~~~java
provides com.acme.spi.Formatter with
    com.acme.provider.upper.UppercaseFormatter,
    com.acme.provider.lower.LowercaseFormatter;
~~~

Các provider có thể nằm trong cùng một module hoặc được cung cấp bởi nhiều module khác nhau. Package chứa implementation không cần export chỉ để `ServiceLoader` có thể sử dụng provider đã khai báo trong module descriptor.

## 3. Provider method trong module descriptor

Ngoài provider class trực tiếp triển khai service interface, JPMS còn hỗ trợ provider method. Provider class khi đó khai báo một phương thức public static tên `provider`, không có tham số và trả về một kiểu tương thích với service type.

Ví dụ:

~~~java
package com.acme.provider.json;

import com.acme.spi.Formatter;

public final class FormatterProvider {
    private FormatterProvider() {
    }

    public static Formatter provider() {
        return new JsonFormatter();
    }
}
~~~

Module descriptor:

~~~java
module com.acme.provider.json {
    requires com.acme.spi;

    provides com.acme.spi.Formatter
        with com.acme.provider.json.FormatterProvider;
}
~~~

Trong trường hợp này, `FormatterProvider` là provider class được khai báo trong directive; đối tượng mà service loader nhận được là giá trị trả về từ phương thức `provider()`. Cách này hữu ích khi việc tạo implementation cần factory, cấu hình hoặc lựa chọn implementation nội bộ.

Không được nhầm tên provider class trong directive với kiểu đối tượng service cuối cùng: khi dùng provider method, phương thức phải trả về service type hoặc một subtype tương thích.

## 4. `resolve` và `resolveAndBind`

`Configuration` biểu diễn kết quả phân giải module. Hai phương thức thường gặp là:

- `resolve(...)` phân giải các root module cùng dependency được khai báo bằng `requires`.
- `resolveAndBind(...)` thực hiện phân giải và thêm service provider module phù hợp cho các service được dùng trong graph.

Nếu chỉ dùng `resolve`, provider module không tự động được đưa vào graph chỉ vì một module có directive `uses`. Nếu muốn module system tìm và bind provider module trong quá trình phân giải, hãy dùng `resolveAndBind`.

Ví dụ tạo configuration cho ứng dụng:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

Configuration configuration =
        ModuleLayer.boot()
                .configuration()
                .resolveAndBind(
                        ModuleFinder.of(),
                        finder,
                        Set.of("com.acme.app"));
~~~

Trong ví dụ:

- `mods` là thư mục chứa các module JAR hoặc exploded module như `com.acme.app`, `com.acme.spi` và `com.acme.provider.upper`.
- `ModuleFinder.of(Path.of("mods"))` tạo finder để tìm module trong thư mục đó.
- `ModuleFinder.of()` đầu tiên là finder rỗng đặt trước các parent configuration.
- `Set.of("com.acme.app")` chỉ định root module cần khởi động.
- Configuration của boot layer là parent configuration; các module nền tảng đã có trong boot layer tiếp tục được dùng từ parent.

Khi phân giải root `com.acme.app`, module system xử lý các dependency như `com.acme.spi`, đọc directive `uses`, tìm module có directive `provides` tương ứng, rồi đưa provider module cùng dependency của nó vào configuration. Quá trình binding tiếp tục khi các module được thêm vào graph cũng sử dụng service khác.

Các module được tìm thấy phải có descriptor hợp lệ và dependency có thể phân giải. Nếu thiếu module, có dependency không giải quyết được hoặc graph vi phạm quy tắc JPMS, quá trình có thể thất bại với các lỗi như `FindException` hoặc `ResolutionException`.

## 5. Kiểm tra provider module đã được bind

Có thể xem những module nằm trong configuration bằng `Configuration.modules()`:

~~~java
configuration.modules().stream()
        .map(resolvedModule -> resolvedModule.name())
        .sorted()
        .forEach(System.out::println);
~~~

Với ví dụ trên, danh sách có thể bao gồm:

~~~text
com.acme.app
com.acme.spi
com.acme.provider.upper
~~~

Kết quả cụ thể còn phụ thuộc vào các module và dependency thực tế trong thư mục `mods`. Điểm cần kiểm tra là provider module đã xuất hiện trong configuration dù consumer không khai báo `requires com.acme.provider.upper`.

Có thể truy vấn một module cụ thể:

~~~java
boolean providerWasBound = configuration
        .findModule("com.acme.provider.upper")
        .isPresent();

System.out.println(providerWasBound);
~~~

`findModule` trả về `Optional<ResolvedModule>`. Kết quả cho biết module có nằm trong configuration này hay không; nó chưa cho biết provider object đã được tạo.

## 6. Tạo layer từ configuration

Sau khi có configuration, ứng dụng có thể tạo layer mới:

~~~java
ModuleLayer layer =
        ModuleLayer.boot().defineModulesWithOneLoader(
                configuration,
                ClassLoader.getSystemClassLoader());
~~~

Layer mới chứa các module được phân giải trong configuration và dùng một class loader cho các module được định nghĩa trong layer đó. Các module ở boot layer vẫn có thể được tham chiếu qua quan hệ parent layer.

Có thể kiểm tra provider module trong layer:

~~~java
Module providerModule = layer
        .findModule("com.acme.provider.upper")
        .orElseThrow();

System.out.println(providerModule.getName());
System.out.println(providerModule.getLayer() == layer);
~~~

Service binding thuộc giai đoạn tạo configuration; việc định nghĩa layer đưa configuration đó vào runtime. Nếu ứng dụng chỉ chạy các module trên boot layer, JVM đã tạo layer ban đầu trong quá trình khởi động và bạn không cần tự tạo layer mới.

## 7. Tìm và sử dụng provider bằng `ServiceLoader`

Trong code thuộc module consumer `com.acme.app`, dùng `ServiceLoader` để lấy provider:

~~~java
package com.acme.app;

import com.acme.spi.Formatter;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        ServiceLoader<Formatter> providers =
                ServiceLoader.load(Formatter.class);

        for (Formatter formatter : providers) {
            System.out.println(formatter.format("Java modules"));
        }
    }
}
~~~

Vì `Main` thuộc module `com.acme.app`, module này đã khai báo `uses com.acme.spi.Formatter`. Khi chạy trong module layer tương ứng, `ServiceLoader.load(Formatter.class)` tìm provider module trong layer của caller và các ancestor layer.

Nếu đang quản lý layer tường minh, có thể chỉ định layer:

~~~java
ServiceLoader<Formatter> providers =
        ServiceLoader.load(layer, Formatter.class);
~~~

Lời gọi này phải xuất phát từ module khai báo `uses` cho service type. Ví dụ, hãy gọi nó từ code thuộc `com.acme.app` nếu module đó có directive `uses com.acme.spi.Formatter`.

`ServiceLoader` thường khởi tạo provider một cách lazy: provider được tạo khi iterator duyệt đến provider tương ứng. Có thể dùng `stream()` để làm việc với các đối tượng `ServiceLoader.Provider<S>` trước khi gọi `get()` để lấy service instance:

~~~java
ServiceLoader.load(Formatter.class)
        .stream()
        .map(ServiceLoader.Provider::get)
        .forEach(formatter ->
                System.out.println(formatter.format("JPMS")));
~~~

Service binding không thay thế `ServiceLoader`. Binding bảo đảm provider module có trong graph; `ServiceLoader` thực hiện việc khám phá và tạo instance khi chương trình cần. Nếu module đã được bind nhưng provider không thể khởi tạo hoặc cấu hình sai, việc duyệt provider có thể phát sinh `ServiceConfigurationError`.

## 8. Service binding với nhiều provider và nhiều service

Một module có thể dùng nhiều service:

~~~java
module com.acme.app {
    requires com.acme.spi;
    requires com.acme.metrics;

    uses com.acme.spi.Formatter;
    uses com.acme.metrics.MetricsSink;
}
~~~

Một module provider cũng có thể cung cấp nhiều service:

~~~java
module com.acme.adapters {
    requires com.acme.spi;
    requires com.acme.metrics;

    provides com.acme.spi.Formatter
        with com.acme.adapters.JsonFormatter;

    provides com.acme.metrics.MetricsSink
        with com.acme.adapters.ConsoleMetricsSink;
}
~~~

Khi phân giải và bind `com.acme.app`, module system có thể thêm `com.acme.adapters` vì module này cung cấp các service mà graph đang sử dụng. Các dependency của provider cũng được phân giải như các dependency module thông thường.

Nếu có nhiều provider cho một service, `ServiceLoader` có thể trả về nhiều provider. Không nên xây dựng logic nghiệp vụ phụ thuộc vào thứ tự provider nếu ứng dụng chưa định nghĩa một quy tắc lựa chọn riêng. Nếu chỉ được phép có một implementation, hãy kiểm tra số lượng provider và xử lý trường hợp không có hoặc có nhiều hơn một provider một cách rõ ràng.

## 9. Module path, class path và giới hạn của service binding

Service provider trong named module được khai báo bằng directive `provides` trong `module-info.java`. Khi dùng module path và muốn provider module được tự động thêm vào configuration theo service binding, hãy đảm bảo provider module nằm trong các module finder được dùng khi phân giải.

Ứng dụng class path truyền thống có thể đăng ký provider bằng file:

~~~text
META-INF/services/com.acme.spi.Formatter
~~~

File này chứa tên đầy đủ của các provider class, mỗi dòng một tên. Cơ chế này vẫn có vai trò với provider trên class path/unnamed module và trong các tình huống tương thích. Nó khác với việc khai báo `provides` trong module descriptor và không tự đưa một named provider module vào configuration bằng service binding.

Automatic module cũng là named module, nhưng quy tắc tương thích và cách xử lý metadata dịch vụ có thể khác explicit module. Với ứng dụng JPMS được thiết kế mới, nên khai báo `uses` và `provides` rõ ràng trong module descriptor để graph và service contract dễ kiểm tra.

## 10. Debug khi provider không xuất hiện

Khi `ServiceLoader` không tìm thấy provider như mong đợi, hãy kiểm tra theo thứ tự:

1. **Service type**: consumer và provider có tham chiếu đúng cùng service API module/type không?
2. **Consumer descriptor**: module gọi `ServiceLoader` đã khai báo `uses` cho đúng service type chưa?
3. **Provider descriptor**: provider module đã khai báo đúng `provides Service with Provider` chưa?
4. **Dependency của provider**: provider module có `requires` module chứa service API không?
5. **Module finder**: finder dùng trong `resolveAndBind` có tìm thấy provider module không?
6. **Configuration**: `configuration.findModule("...")` có trả về module provider không?
7. **Layer**: provider module có nằm trong layer được truyền cho `ServiceLoader.load(layer, service)`, hoặc trong ancestor layer phù hợp không?
8. **Provider construction**: provider class có thỏa điều kiện khởi tạo hoặc provider method có hợp lệ không?

Một số lỗi thường gặp:

- Dùng `resolve` trong khi mong đợi provider module được tự động bind.
- Quên `uses` ở consumer module.
- Quên `provides` ở provider module hoặc ghi sai service type/provider class.
- Provider module không nằm trong module finder dùng để phân giải.
- Provider module có dependency không thể phân giải.
- Gọi `ServiceLoader` từ một named module không khai báo `uses`.
- Đã bind provider vào configuration nhưng lại tìm service trong một layer khác không chứa provider đó.

## Ghi nhớ

`uses` mô tả nhu cầu service của consumer; `provides ... with ...` mô tả implementation của provider. `Configuration.resolveAndBind(...)` phân giải dependency và tự động thêm provider module phù hợp vào module graph. Sau khi tạo layer, `ServiceLoader` mới khám phá và khởi tạo provider instance. Consumer chỉ cần phụ thuộc vào service API, còn provider được lựa chọn thông qua cơ chế binding và loading của module system.
