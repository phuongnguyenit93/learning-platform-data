# Khám phá dịch vụ theo ModuleLayer

Trong JPMS, `ModuleLayer` cho phép tạo một lớp mô-đun ở thời điểm chạy dựa trên một đồ thị module đã được phân giải. Một ứng dụng có thể dùng cơ chế này để nạp các module mở rộng từ thư mục plugin, tìm provider của một service và giữ các phần mở rộng trong một lớp mô-đun con có quan hệ rõ với lớp cha.

Khi kết hợp `ModuleFinder`, `Configuration.resolveAndBind(...)`, `ModuleLayer.defineModulesWithOneLoader(...)` và `ServiceLoader.load(layer, Service.class)`, ứng dụng có thể phát hiện dịch vụ từ module được nạp động mà không cần biên dịch trực tiếp với class triển khai. Hợp đồng service vẫn được chia sẻ qua module API.

Bài học này dùng các API JPMS hiện hành và ví dụ chạy được bằng Java 17 trở lên. Các module trong ví dụ cùng chạy trong một JVM; ModuleLayer giúp tổ chức việc phân giải và nạp module, không tạo tiến trình hoặc sandbox riêng.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của `ModuleLayer`, `Configuration` và `ModuleFinder`.
- Phân biệt lớp mô-đun boot, lớp mô-đun ứng dụng và lớp mô-đun con được tạo động.
- Phân giải một module plugin cùng các dependency của nó.
- Dùng `resolveAndBind` để gắn provider theo các directive `uses` và `provides`.
- Tạo lớp mô-đun mới với class loader phù hợp.
- Dùng `ServiceLoader.load(layer, serviceType)` để tìm provider trong lớp mô-đun và các lớp cha.
- Giữ service API có cùng identity giữa module gọi và module provider.
- Xử lý lỗi phân giải, provider và vòng đời plugin.

## 1. ModuleLayer là gì?

### 1.1. Đồ thị module và lớp mô-đun lúc chạy

JPMS mô tả module bằng `module-info.java`. Descriptor khai báo tên module, dependency, package export, service usage và service provider. Khi chạy, JVM cần phân giải các module này thành một đồ thị hợp lệ.

Có ba khái niệm liên quan:

- **ModuleFinder:** tìm các module có thể được phân giải từ module path, thư mục module hoặc nguồn module khác.
- **Configuration:** biểu diễn đồ thị module đã được phân giải, gồm các module được chọn và quan hệ dependency của chúng.
- **ModuleLayer:** biểu diễn các module đã được định nghĩa trong JVM cùng class loader tương ứng và quan hệ với lớp mô-đun cha.

Có thể hình dung quy trình:

~~~text
Nguồn module / thư mục plugin
          |
          v
     ModuleFinder
          |
          v
 Configuration.resolve / resolveAndBind
          |
          v
       Configuration
          |
          v
 ModuleLayer.defineModules...
          |
          v
     ModuleLayer
          |
          v
 ServiceLoader.load(layer, Service.class)
~~~

`Configuration` giải quyết câu hỏi module nào có mặt và dependency nào được thỏa mãn. `ModuleLayer` biến cấu hình đó thành các module có thể được nạp và sử dụng tại runtime.

### 1.2. Quan hệ cha và con

Một ModuleLayer có thể có một hoặc nhiều lớp cha. Lớp con có thể đọc các module từ lớp cha theo module graph đã phân giải. Mô hình phổ biến cho plugin là:

~~~text
Parent layer
├── greeting.api
└── launcher.app
       |
       v
Child layer
├── plugin.feature
└── greeting.provider
~~~

Trong ví dụ, module API nằm ở lớp cha. Module feature và provider nằm ở lớp con. Provider phụ thuộc vào cùng module API mà ứng dụng sử dụng, vì vậy kiểu service được chia sẻ chính xác giữa hai lớp.

Lớp cha có thể là boot layer, application layer hoặc một lớp do ứng dụng tạo trước đó. Không mặc định rằng `ModuleLayer.boot()` luôn là lớp cha phù hợp. Hãy chọn lớp đang chứa service API mà provider cần triển khai. Có thể lấy lớp đó bằng:

~~~java
ModuleLayer parent = Greeter.class.getModule().getLayer();
~~~

Cách này giúp provider phân giải dependency tới đúng module chứa `Greeter`, kể cả khi ứng dụng được khởi chạy trong application layer nằm phía trên boot layer.

### 1.3. ModuleLayer không phải process hoặc sandbox

Các module trong cùng JVM vẫn chia sẻ tài nguyên tiến trình và có thể tương tác qua API mà chúng được phép truy cập. ModuleLayer tổ chức module graph, package encapsulation và class loading; nó không cách ly mã plugin không đáng tin cậy như một tiến trình riêng.

Nếu cần chạy plugin không đáng tin cậy, hãy dùng ranh giới tiến trình hoặc container cùng cơ chế kiểm soát tài nguyên phù hợp. Không xem ModuleLayer như một ranh giới bảo mật.

## 2. ModuleFinder: tìm module ở đâu?

### 2.1. Tìm module từ module path

`ModuleFinder` là abstraction để tìm module theo tên. Một số cách tạo finder phổ biến:

~~~java
ModuleFinder systemFinder = ModuleFinder.ofSystem();
ModuleFinder pathFinder = ModuleFinder.of(Path.of("mods"));
ModuleFinder pluginFinder = ModuleFinder.of(Path.of("plugins"));
~~~

- `ModuleFinder.ofSystem()` tìm các module hệ thống của JDK.
- `ModuleFinder.of(path...)` tìm module trong các vị trí được chỉ định. Đường dẫn có thể là modular JAR hoặc thư mục chứa các module đã biên dịch.
- `find(moduleName)` trả về một `Optional<ModuleReference>`.
- `findAll()` trả về các module mà finder có thể tìm thấy.

Thư mục plugin có thể chứa nhiều module đã biên dịch dạng exploded module hoặc modular JAR. Trong ví dụ, `plugins/` chứa thư mục `greeting.provider/` và `plugin.feature/`, mỗi thư mục có `module-info.class` ở gốc module.

### 2.2. Kiểm tra module trước khi phân giải

Có thể xác minh một module có tồn tại:

~~~java
ModuleReference reference = pluginFinder.find("greeting.provider")
        .orElseThrow(() ->
                new IllegalArgumentException("Plugin module not found"));
~~~

Việc tìm thấy `ModuleReference` chỉ xác nhận finder nhìn thấy module. Module vẫn có thể không phân giải được nếu thiếu dependency, có xung đột tên, yêu cầu phiên bản không phù hợp hoặc có cấu hình không hợp lệ.

### 2.3. Tránh để plugin path thay thế nhầm module API

Khi một module plugin khai báo `requires greeting.api;`, resolver cần dùng đúng module API mà ứng dụng đã nạp. Nếu plugin finder được ưu tiên trước parent configuration, một bản sao `greeting.api` có thể được chọn vào lớp con.

Điều đó tạo ra hai module API khác nhau và hai identity của kiểu `Greeter`. Provider triển khai bản sao ở lớp con sẽ không tương thích với service interface mà ứng dụng đang dùng ở lớp cha.

Khi muốn dependency của plugin được thỏa mãn từ parent trước, truyền finder plugin ở tham số `after` của phương thức resolve:

~~~java
parent.configuration().resolveAndBind(
        ModuleFinder.of(),
        pluginFinder,
        Set.of("plugin.feature")
);
~~~

Tham số `before` được tìm trước parent configurations; tham số `after` được tìm sau parent configurations. Đặt finder plugin ở `after` giúp module API đã có trong parent được ưu tiên. Đây là điểm quan trọng để giữ cùng một service type giữa các layer.

## 3. Configuration: phân giải module graph

### 3.1. resolve và resolveAndBind

Sau khi có ModuleFinder, ứng dụng cần tạo Configuration:

~~~java
Configuration configuration = parent.configuration().resolve(
        beforeFinder,
        afterFinder,
        roots
);
~~~

`resolve` phân giải các module gốc và dependency cần thiết để tạo đồ thị hợp lệ.

`resolveAndBind` thực hiện phân giải và thêm bước service binding. Bước này xem các directive `uses` trong đồ thị module được phân giải và tìm các module provider phù hợp theo directive `provides` có trong các finder. Các provider được tìm thấy có thể được thêm vào đồ thị cùng dependency của chúng.

Ví dụ:

~~~java
Configuration configuration = parent.configuration().resolveAndBind(
        ModuleFinder.of(),
        pluginFinder,
        Set.of("plugin.feature")
);
~~~

Nếu `plugin.feature` khai báo `uses com.acme.greeter.api.Greeter;` và finder có module khai báo `provides ... Greeter ...`, service binding có thể thêm provider vào cấu hình.

### 3.2. Root modules là gì?

Tham số `roots` là tập tên module mà ứng dụng muốn đưa vào cấu hình. Resolver bắt đầu từ các root này, rồi bổ sung dependency cần thiết.

Ví dụ:

- `plugin.feature` là root vì ứng dụng muốn nạp tính năng đó.
- `greeting.api` đã nằm trong parent layer nên được dùng làm dependency của plugin.
- `greeting.provider` được thêm nhờ service binding vì module feature sử dụng service mà provider cung cấp.

Nếu provider là mục tiêu nạp trực tiếp, có thể đặt tên provider trong roots. Nếu muốn để service binding chọn provider từ các module sử dụng service, đặt module sử dụng service làm root và dùng `resolveAndBind`.

### 3.3. Service binding không bỏ qua dependency

Một provider vẫn phải đáp ứng tất cả dependency của nó. Nếu provider yêu cầu một module không có trong parent hoặc plugin finder, việc phân giải thất bại. `resolveAndBind` không tự tải thư viện từ internet hay đoán dependency còn thiếu.

Nên xử lý rõ các lỗi:

- `FindException`: finder không thể tìm module hoặc module reference không hợp lệ.
- `ResolutionException`: module graph không thể phân giải do thiếu hoặc xung đột dependency.
- `LayerInstantiationException`: không thể tạo layer theo cấu hình hoặc class loader đã chọn.

## 4. Tạo ModuleLayer

### 4.1. defineModulesWithOneLoader

Sau khi có Configuration, tạo lớp mô-đun:

~~~java
ModuleLayer layer = parent.defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader()
);
~~~

Phương thức này tạo các module trong configuration và dùng một class loader cho các module mới trong layer. Class loader được truyền vào đóng vai trò parent loader của loader được tạo cho layer.

Lựa chọn một loader phù hợp khi các module plugin có thể dùng chung một class loader. Điều này thường đơn giản cho một nhóm plugin có quan hệ chặt chẽ.

### 4.2. Các cách tạo layer khác

JPMS cung cấp các lựa chọn khác:

- `defineModulesWithManyLoaders(...)`: tạo loader riêng cho từng module trong layer.
- `defineModules(...)`: cho phép ứng dụng cung cấp hàm ánh xạ module name sang class loader.
- Các overload tạo layer với nhiều parent layers khi kiến trúc cần ghép nhiều đồ thị module.

Chọn cách tạo loader theo yêu cầu về chia sẻ class, dependency và cách nạp plugin. Nhiều loader có thể tạo ranh giới class-loading rõ hơn, nhưng cũng làm phức tạp việc chia sẻ kiểu giữa các module.

### 4.3. ModuleLayer là bất biến sau khi tạo

Sau khi layer được tạo, module graph của layer đó không được thêm module mới bằng cách sửa trực tiếp layer. Để nạp một nhóm plugin khác, ứng dụng tạo Configuration và ModuleLayer mới với parent phù hợp.

Các layer có thể cùng dùng chung API ở lớp cha. Việc tạo layer mới không tự thay thế instance đang được sử dụng từ layer cũ.

### 4.4. Kiểm tra module trong layer

Có thể kiểm tra module đã được tạo:

~~~java
layer.findModule("greeting.provider");
layer.modules();
layer.findLoader("greeting.provider");
~~~

- `findModule` trả về `Optional<Module>`.
- `modules` trả về tập module trực tiếp thuộc layer đó.
- `findLoader` trả về class loader được dùng cho module được chỉ định.

`layer.modules()` chỉ liệt kê module thuộc layer hiện tại, không gộp các module ở lớp cha. Để xem module cha, truy cập layer cha tương ứng.

## 5. Khai báo service trong JPMS

### 5.1. Service API khai báo trong module riêng

Service là hợp đồng mà consumer cần sử dụng. Ví dụ:

~~~java
package com.acme.greeter.api;

public interface Greeter {
    String greet(String name);
}
~~~

Module API công bố package chứa service:

~~~java
module greeting.api {
    exports com.acme.greeter.api;
}
~~~

Provider và consumer cùng tham chiếu module API. Giữ API ổn định giúp thay provider mà không buộc consumer biết class triển khai cụ thể.

### 5.2. Provider khai báo provides

Module triển khai khai báo:

~~~java
module greeting.provider {
    requires greeting.api;

    provides com.acme.greeter.api.Greeter
            with com.acme.greeter.provider.FriendlyGreeter;
}
~~~

Class provider:

~~~java
package com.acme.greeter.provider;

import com.acme.greeter.api.Greeter;

public final class FriendlyGreeter implements Greeter {
    public FriendlyGreeter() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Với cách đăng ký provider class này, class provider phải public và có public no-argument constructor. Package triển khai không cần export chỉ để ServiceLoader tạo provider theo khai báo `provides`.

JPMS cũng hỗ trợ provider method: module có thể khai báo class provider có phương thức public static `provider()` trả về service type. Cách này hữu ích khi muốn tạo service bằng factory hoặc khi class triển khai không trực tiếp là provider class được khởi tạo theo constructor thông thường.

### 5.3. Consumer khai báo uses

Module sử dụng service khai báo:

~~~java
module launcher.app {
    requires greeting.api;
    uses com.acme.greeter.api.Greeter;
}
~~~

Directive `uses` nói rõ module này tiêu thụ service. Khi gọi ServiceLoader từ named module, module gọi cần khai báo `uses` cho service tương ứng.

## 6. ServiceLoader kết hợp với ModuleLayer

### 6.1. Tìm provider trong một layer cụ thể

Khi provider nằm trong child layer, dùng overload nhận ModuleLayer:

~~~java
ServiceLoader<Greeter> loader =
        ServiceLoader.load(layer, Greeter.class);
~~~

Overload này tìm provider trong layer được chỉ định và các layer cha của nó. Nó phù hợp khi ứng dụng muốn khám phá provider trong một layer plugin cụ thể.

Nếu dùng `ServiceLoader.load(Greeter.class)`, việc tìm provider dựa trên ngữ cảnh loader của API đó và không diễn đạt rõ layer plugin cần truy vấn. Với kiến trúc nhiều layer, hãy truyền layer rõ ràng.

### 6.2. Provider được nạp khi cần

ServiceLoader không nhất thiết tạo tất cả provider ngay khi tạo loader. Provider được tìm và khởi tạo khi ứng dụng duyệt loader hoặc gọi các thao tác như `findFirst()`, `iterator()` hoặc `stream()`.

Ví dụ:

~~~java
Greeter greeter = ServiceLoader.load(layer, Greeter.class)
        .findFirst()
        .orElseThrow(() ->
                new IllegalStateException("No Greeter provider"));
~~~

Nếu có nhiều provider, có thể duyệt tất cả:

~~~java
for (Greeter greeter : ServiceLoader.load(layer, Greeter.class)) {
    System.out.println(greeter.greet("Ada"));
}
~~~

Thứ tự provider không nên được dùng làm quy tắc ưu tiên nghiệp vụ nếu ứng dụng cần một lựa chọn xác định. Khi cần chọn provider, hãy thêm metadata hoặc cấu hình riêng để xác định lựa chọn.

### 6.3. Provider không cần export package triển khai

Module provider có thể giữ class triển khai trong package không export. Consumer chỉ cần biết service interface. Điều này giúp ứng dụng không import class như `FriendlyGreeter` và không bị phụ thuộc vào package triển khai.

Điểm cốt lõi là service type phải là cùng một class/module identity ở phía consumer và provider. Vì vậy, module provider cần đọc đúng API module ở parent layer, không nạp một bản sao API khác vào child layer.

## 7. Ví dụ hoàn chỉnh: khám phá Greeter trong child ModuleLayer

Ví dụ có bốn module:

- `greeting.api`: công bố interface Greeter trong parent layer.
- `launcher.app`: tạo layer plugin và tìm service.
- `plugin.feature`: module gốc được yêu cầu nạp; khai báo uses Greeter.
- `greeting.provider`: cung cấp implementation và được service binding thêm vào child layer.

Cấu trúc source:

~~~text
src/
├── greeting.api/
│   ├── module-info.java
│   └── com/acme/greeter/api/Greeter.java
├── launcher.app/
│   ├── module-info.java
│   └── com/acme/launcher/Main.java
├── plugin.feature/
│   ├── module-info.java
│   └── com/acme/feature/FeatureMarker.java
└── greeting.provider/
    ├── module-info.java
    └── com/acme/greeter/provider/FriendlyGreeter.java
~~~

### 7.1. Module greeting.api

File `src/greeting.api/module-info.java`:

~~~java
module greeting.api {
    exports com.acme.greeter.api;
}
~~~

File `src/greeting.api/com/acme/greeter/api/Greeter.java`:

~~~java
package com.acme.greeter.api;

public interface Greeter {
    String greet(String name);
}
~~~

### 7.2. Module greeting.provider

File `src/greeting.provider/module-info.java`:

~~~java
module greeting.provider {
    requires greeting.api;

    provides com.acme.greeter.api.Greeter
            with com.acme.greeter.provider.FriendlyGreeter;
}
~~~

File `src/greeting.provider/com/acme/greeter/provider/FriendlyGreeter.java`:

~~~java
package com.acme.greeter.provider;

import com.acme.greeter.api.Greeter;

public final class FriendlyGreeter implements Greeter {
    public FriendlyGreeter() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Package `com.acme.greeter.provider` không export. Ứng dụng chỉ nhận interface Greeter.

### 7.3. Module plugin.feature

File `src/plugin.feature/module-info.java`:

~~~java
module plugin.feature {
    requires greeting.api;
    uses com.acme.greeter.api.Greeter;
}
~~~

File `src/plugin.feature/com/acme/feature/FeatureMarker.java`:

~~~java
package com.acme.feature;

public final class FeatureMarker {
    private FeatureMarker() {
    }

    public static String id() {
        return "catalog-feature";
    }
}
~~~

Module feature là root được ứng dụng yêu cầu nạp. Directive `uses` cho biết module này cần service Greeter; service binding có thể tìm provider tương ứng trong plugin finder.

### 7.4. Module launcher.app

File `src/launcher.app/module-info.java`:

~~~java
module launcher.app {
    requires greeting.api;
    uses com.acme.greeter.api.Greeter;
}
~~~

File `src/launcher.app/com/acme/launcher/Main.java`:

~~~java
package com.acme.launcher;

import com.acme.greeter.api.Greeter;
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.ServiceLoader;
import java.util.Set;

public final class Main {
    public static void main(String[] args) {
        // Parent phải chứa đúng service API mà provider sẽ triển khai.
        ModuleLayer parent = Greeter.class.getModule().getLayer();

        // plugins/ là thư mục chứa các module plugin đã biên dịch.
        ModuleFinder pluginFinder = ModuleFinder.of(Path.of("plugins"));

        // Tìm plugin.feature sau parent configuration để dùng lại greeting.api
        // từ parent; service binding bổ sung greeting.provider.
        Configuration configuration = parent.configuration()
                .resolveAndBind(
                        ModuleFinder.of(),
                        pluginFinder,
                        Set.of("plugin.feature")
                );

        ModuleLayer layer = parent.defineModulesWithOneLoader(
                configuration,
                ClassLoader.getSystemClassLoader()
        );

        Greeter greeter = ServiceLoader.load(layer, Greeter.class)
                .findFirst()
                .orElseThrow(() ->
                        new IllegalStateException("No Greeter provider"));

        System.out.println(greeter.greet("Ada"));
        System.out.println(
                "provider module=" + greeter.getClass().getModule().getName()
        );
        System.out.println(
                "child layer modules=" + layer.modules().stream()
                        .map(module -> module.getName())
                        .sorted()
                        .toList()
        );
        System.out.println(
                "provider reads parent API="
                        + greeter.getClass().getModule()
                                .canRead(Greeter.class.getModule())
        );
    }
}
~~~

### 7.5. Biên dịch và chạy bằng Java 17+

Từ thư mục chứa `src`, biên dịch API và launcher vào module path chính:

~~~bash
javac --release 17 --module-source-path src -d mods -m greeting.api,launcher.app
~~~

Biên dịch provider và feature vào thư mục plugin, dùng API đã biên dịch làm module path:

~~~bash
javac --release 17 --module-path mods --module-source-path src -d plugins -m greeting.provider,plugin.feature
~~~

Chạy launcher. Thư mục `plugins` phải nằm trong working directory vì code dùng `Path.of("plugins")`:

~~~bash
java --module-path mods -m launcher.app/com.acme.launcher.Main
~~~

Kết quả stdout:

~~~text
Hello, Ada!
provider module=greeting.provider
child layer modules=[greeting.provider, plugin.feature]
provider reads parent API=true
~~~

Kết quả cho thấy:

1. `plugin.feature` được chọn làm root của child configuration.
2. `resolveAndBind` tìm module provider có `provides Greeter` vì feature khai báo `uses Greeter`.
3. Provider được tạo trong child layer và đọc đúng service API từ parent.
4. `ServiceLoader.load(layer, Greeter.class)` tìm được provider trong child layer.
5. Ứng dụng chỉ gọi interface Greeter, không phụ thuộc class triển khai FriendlyGreeter.

## 8. Chọn class loader và chia sẻ class

### 8.1. Một loader hay nhiều loader?

`defineModulesWithOneLoader` thường phù hợp khi các module plugin cần chia sẻ class trong cùng một nhóm. `defineModulesWithManyLoaders` có thể phù hợp khi cần tách class loader theo module.

Việc chọn loader ảnh hưởng đến identity của class. Hai class có cùng tên đầy đủ nhưng được định nghĩa bởi hai class loader khác nhau vẫn là hai kiểu khác nhau trong JVM.

### 8.2. Giữ service API ở lớp cha

Một lỗi phổ biến là đưa cả API module vào plugin finder trong khi API đã tồn tại ở parent. Nếu resolver tạo bản sao API trong child layer, provider có thể triển khai một kiểu Greeter khác với kiểu mà launcher đang sử dụng.

Để tránh lỗi:

- Giữ module API trong parent layer.
- Biên dịch provider dựa vào đúng API module.
- Đặt plugin finder ở tham số `after` khi cần ưu tiên parent configuration.
- Dùng `ServiceLoader.load(layer, Greeter.class)` với chính service class mà launcher import từ parent.
- Kiểm tra `providerModule.canRead(serviceType.getModule())` khi cần chẩn đoán.

Không đóng gói một bản sao service API trong mỗi plugin trừ khi kiến trúc cố ý dùng một API độc lập với identity riêng.

### 8.3. Class loader của plugin

Có thể lấy loader cho module trong layer:

~~~java
ClassLoader loader = layer.findLoader("greeting.provider");
~~~

Không giả định mọi module trong mọi layer dùng cùng loader. Nếu dùng nhiều loader, hãy dựa trên module cụ thể cần nạp thay vì giữ một loader chung tùy tiện.

## 9. Nhiều provider và lựa chọn dịch vụ

### 9.1. Một service có thể có nhiều provider

Một service có thể có nhiều module cùng khai báo `provides`. Khi các provider đều có mặt trong layer hoặc các layer cha, ServiceLoader có thể trả về nhiều implementation.

Duyệt provider:

~~~java
ServiceLoader<Greeter> loader =
        ServiceLoader.load(layer, Greeter.class);

for (Greeter greeter : loader) {
    System.out.println(greeter.greet("Ada"));
}
~~~

Nếu cần ưu tiên provider theo cấu hình, không dựa vào thứ tự tìm thấy. Hãy thiết kế metadata, tên provider hoặc cấu hình lựa chọn rõ ràng.

### 9.2. Lazy loading và lỗi provider

ServiceLoader có thể trì hoãn việc tạo provider cho đến khi ứng dụng duyệt. Lỗi có thể xuất hiện khi provider được khởi tạo hoặc khi đọc metadata, ví dụ:

- Provider thiếu public no-argument constructor theo dạng provider class.
- Provider không thể được nạp do dependency hoặc class loader.
- Constructor/provider method ném exception.
- Module descriptor khai báo sai service type hoặc implementation.

Các lỗi cấu hình provider thường được báo qua `ServiceConfigurationError`. Hãy bắt và ghi log ở ranh giới nạp plugin nếu ứng dụng cần tiếp tục hoạt động khi một plugin lỗi.

### 9.3. Không dùng tên class triển khai làm hợp đồng plugin

Consumer nên phụ thuộc vào service interface. Nếu consumer gọi trực tiếp `FriendlyGreeter`, lợi ích của service discovery bị mất và việc thay provider trở nên khó khăn.

Giữ API nhỏ, ổn định và tách khỏi package triển khai giúp thêm provider mà không sửa mã consumer.

## 10. Vòng đời và cập nhật plugin

### 10.1. Tạo layer mới cho phiên bản plugin mới

ModuleLayer không có thao tác thêm module vào layer hiện tại. Khi cần nạp phiên bản plugin khác, ứng dụng có thể tạo layer mới với module finder và configuration mới.

Ứng dụng cần quyết định thời điểm chuyển sang layer mới, cách quản lý service instance và cách ngừng sử dụng instance từ layer cũ.

### 10.2. Không có bảo đảm unload ngay lập tức

Java không cung cấp thao tác chung để cưỡng bức unload một ModuleLayer. Class loader và class của plugin chỉ có thể được thu hồi khi không còn tham chiếu giữ chúng và JVM có thể garbage-collect loader đó.

Để hỗ trợ thu hồi tài nguyên:

- Dừng sử dụng service instance thuộc layer cũ.
- Đóng tài nguyên mà plugin đã mở, ví dụ file, socket, executor hoặc thread.
- Xóa tham chiếu tới class, object, callback và class loader của layer cũ.
- Tránh để thread hoặc static registry ở parent giữ đối tượng của child layer.

Ngay cả khi không còn tham chiếu, thời điểm garbage collection không được bảo đảm.

### 10.3. ModuleLayer không tự quản lý lifecycle nghiệp vụ

Layer chỉ tổ chức module và class loading. Ứng dụng vẫn cần một hợp đồng lifecycle nếu plugin cần khởi động, dừng, giải phóng tài nguyên hoặc nhận cấu hình.

Có thể định nghĩa service riêng như `PluginLifecycle` với `start()` và `stop()`, hoặc một interface quản lý plugin có trách nhiệm rõ. Đừng giả định việc bỏ tham chiếu tới ModuleLayer sẽ tự gọi cleanup.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra hoặc xử lý |
| --- | --- | --- |
| `FindException` | Plugin finder không thấy module | Kiểm tra module path, thư mục exploded module và tên module |
| `ResolutionException` | Thiếu dependency hoặc module graph xung đột | Kiểm tra requires và các module có trong parent/plugin finder |
| Không tìm thấy provider | Thiếu `provides`, `uses`, provider chưa được bind hoặc đang tìm sai layer | Kiểm tra descriptor, roots, resolveAndBind và layer truyền vào ServiceLoader |
| Provider không tương thích với service type | API bị nạp thành hai module/class identity khác nhau | Đặt API ở parent, ưu tiên parent bằng finder `after` |
| `ServiceConfigurationError` | Provider class hoặc quá trình khởi tạo không hợp lệ | Kiểm tra constructor/provider method và dependency lúc runtime |
| `LayerInstantiationException` | Cấu hình không thể tạo thành layer theo class loader đã chọn | Kiểm tra package, module graph và cách ánh xạ loader |
| Plugin cũ vẫn còn được giữ | Object, thread hoặc loader còn tham chiếu | Thiết kế cleanup và bỏ tham chiếu rõ ràng |

Một số lỗi chỉ xuất hiện khi ServiceLoader thực sự duyệt provider. Vì vậy, kiểm thử cần chạy tới bước lấy và gọi service, không dừng ngay sau khi Configuration hoặc ModuleLayer được tạo.

## 12. Checklist thiết kế ModuleLayer

- [ ] Phân biệt được ModuleFinder, Configuration và ModuleLayer.
- [ ] Xác định đúng parent layer đang chứa service API.
- [ ] Đưa module plugin vào đúng finder và module path.
- [ ] Chọn roots phản ánh module feature cần nạp.
- [ ] Dùng resolveAndBind khi cần service binding.
- [ ] Hiểu thứ tự finder before, parent configuration và finder after.
- [ ] Khai báo `uses` trong module tiêu thụ service.
- [ ] Khai báo `provides ... with ...` trong module provider.
- [ ] Dùng `ServiceLoader.load(layer, Service.class)` để truy vấn đúng layer.
- [ ] Giữ service API identity thống nhất giữa parent và child.
- [ ] Chọn one-loader hoặc many-loaders theo nhu cầu chia sẻ class.
- [ ] Xử lý lỗi phân giải và lỗi khởi tạo provider.
- [ ] Có quy trình dừng plugin và giải phóng tài nguyên.
- [ ] Không xem ModuleLayer là sandbox hoặc cơ chế unload tức thì.
