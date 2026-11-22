# Khai báo phía cung cấp bằng provides ... with

## Mục tiêu

Java Platform Module System (JPMS) hỗ trợ mô hình dịch vụ (service) để một module công bố phần triển khai của một hợp đồng, còn module khác sử dụng hợp đồng đó mà không cần phụ thuộc trực tiếp vào module triển khai.

Directive `provides ... with ...` được khai báo trong `module-info.java` của module cung cấp dịch vụ. Nó cho module system biết module đó cung cấp implementation nào cho một service type. Ở phía tiêu thụ, module khai báo `uses` và thường dùng `java.util.ServiceLoader` để tìm provider khi chạy.

Sau bài này, bạn có thể:

- Phân biệt service type, service consumer và service provider.
- Viết directive `provides Service with Provider` trong module descriptor.
- Xác định dependency cần có giữa provider module và module chứa service API.
- Hiểu vì sao provider package không nhất thiết phải export.
- Kết hợp `provides`, `uses` và `ServiceLoader` trong ứng dụng nhiều module.
- Kiểm tra provider được phân giải, đóng gói và phát hiện ở runtime.
- Chọn provider constructor hoặc provider method phù hợp và xử lý lỗi phổ biến.

Các ví dụ dùng cú pháp JPMS hiện hành, biên dịch được với `javac --release 17` trở lên.

## 1. Mô hình dịch vụ trong JPMS

Một hệ thống dịch vụ thường có ba vai trò:

1. **Service type**: hợp đồng công khai, thường là interface hoặc abstract class. Ví dụ `Greeter`.
2. **Service provider**: module cung cấp một hoặc nhiều implementation của service type.
3. **Service consumer**: module cần sử dụng service nhưng không muốn phụ thuộc trực tiếp vào implementation cụ thể.

Có thể hình dung:

~~~text
                 Service API module
                com.example.greeter.api
                          ▲
                 requires│
                          │
       ┌──────────────────┴──────────────────┐
       │                                     │
Provider module                       Consumer module
com.example.greeter.provider           com.example.greeter.app
       │                                     │
       │ provides Greeter                    │ uses Greeter
       │ with FriendlyGreeter                │
       └──────────────────┐       ┌──────────┘
                          ▼       ▼
                       ServiceLoader
~~~

Provider module phụ thuộc vào module chứa service API để triển khai interface. Consumer module cũng đọc module API, nhưng không cần khai báo `requires` đến provider module.

Cách thiết kế này tách hợp đồng khỏi phần triển khai. Có thể thay implementation hoặc bổ sung provider mới mà không phải sửa mã nguồn consumer, miễn là các provider vẫn tuân theo cùng service contract.

## 2. Cú pháp `provides ... with ...`

Directive được đặt trong `module-info.java` của module cung cấp:

~~~java
module com.example.greeter.provider {
    requires com.example.greeter.api;

    provides com.example.greeter.api.Greeter
        with com.example.greeter.provider.FriendlyGreeter;
}
~~~

Cấu trúc:

~~~java
provides <service-type> with <provider-class>;
~~~

Trong đó:

- `service-type` là kiểu dịch vụ mà module công bố.
- `provider-class` là lớp provider được module đăng ký.
- `requires` khai báo dependency đến module sở hữu service type để provider có thể triển khai hợp đồng.
- Directive này thuộc module descriptor và được biên dịch thành metadata trong `module-info.class`.

Một module có thể cung cấp nhiều service type bằng nhiều directive `provides`. Một service type cũng có thể có nhiều provider class trong cùng directive:

~~~java
module com.example.codec.provider {
    requires com.example.codec.api;

    provides com.example.codec.api.Codec
        with com.example.codec.provider.JsonCodec,
             com.example.codec.provider.XmlCodec;
}
~~~

Mỗi provider được liệt kê phải đáp ứng quy tắc provider của JPMS. Khi chạy, consumer có thể nhận nhiều provider cho cùng service type.

## 3. Điều kiện đối với provider class

Với cách thông dụng, provider class:

- Là lớp public.
- Triển khai service type.
- Có constructor public không tham số.
- Có thể được khởi tạo bởi cơ chế service loading.

Ví dụ:

~~~java
package com.example.greeter.provider;

import com.example.greeter.api.Greeter;

public final class FriendlyGreeter implements Greeter {
    public FriendlyGreeter() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Constructor public không tham số cho phép ServiceLoader tạo instance provider. Nếu constructor không tồn tại, không public hoặc yêu cầu tham số, provider theo dạng constructor thông thường sẽ không đáp ứng quy tắc discovery.

### 3.1. Dùng provider method

JPMS còn hỗ trợ provider method. Thay vì provider class trực tiếp triển khai service type, class được khai báo trong `provides` có thể cung cấp một method:

~~~java
package com.example.greeter.provider;

import com.example.greeter.api.Greeter;

public final class GreeterFactory {
    private GreeterFactory() {
    }

    public static Greeter provider() {
        return new FriendlyGreeter();
    }
}
~~~

Module descriptor:

~~~java
module com.example.greeter.provider {
    requires com.example.greeter.api;

    provides com.example.greeter.api.Greeter
        with com.example.greeter.provider.GreeterFactory;
}
~~~

Provider method phải là method `public static`, tên `provider`, không có tham số và có kiểu trả về tương thích với service type. Trong trường hợp này, class được liệt kê trong `provides` không cần trực tiếp triển khai interface service.

Provider method hữu ích khi cần kiểm soát cách tạo instance, trả về một implementation được cấu hình hoặc che giấu class triển khai thật. Nếu không cần logic tạo instance riêng, public no-argument constructor thường đơn giản hơn.

## 4. Service type phải được công bố cho consumer

Service type thường nằm trong một module API riêng:

File `com.example.greeter.api/module-info.java`:

~~~java
module com.example.greeter.api {
    exports com.example.greeter.api;
}
~~~

File `com.example.greeter.api/com/example/greeter/api/Greeter.java`:

~~~java
package com.example.greeter.api;

public interface Greeter {
    String greet(String name);
}
~~~

Module API export package chứa interface để provider và consumer có thể sử dụng kiểu này.

Provider module cần đọc API module:

~~~java
module com.example.greeter.provider {
    requires com.example.greeter.api;

    provides com.example.greeter.api.Greeter
        with com.example.greeter.provider.FriendlyGreeter;
}
~~~

Consumer module cũng cần đọc API module. Package của implementation provider không cần export cho consumer chỉ để ServiceLoader phát hiện provider. Module descriptor đã công bố mối quan hệ service qua `provides`; implementation có thể nằm trong package nội bộ của provider module.

Đây là điểm quan trọng của encapsulation: consumer phụ thuộc vào interface công khai, còn class triển khai có thể được giữ bên trong module provider.

## 5. Phía tiêu thụ: `uses` và `ServiceLoader`

Module sử dụng service khai báo directive `uses`:

~~~java
module com.example.greeter.app {
    requires com.example.greeter.api;

    uses com.example.greeter.api.Greeter;
}
~~~

`uses` ghi nhận service type mà module cần. Với named module, khai báo này là một phần của module descriptor và cần có khi module sử dụng ServiceLoader cho service đó.

Mã nguồn consumer:

~~~java
package com.example.greeter.app;

import com.example.greeter.api.Greeter;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        Greeter greeter = ServiceLoader.load(Greeter.class)
                .findFirst()
                .orElseThrow(() ->
                        new IllegalStateException("No Greeter provider found"));

        System.out.println(greeter.greet("JPMS"));
        System.out.println("provider module="
                + greeter.getClass().getModule().getName());
    }
}
~~~

`ServiceLoader.load(Greeter.class)` tạo service loader cho service type. Các provider được tìm khi duyệt kết quả; việc discovery và khởi tạo có tính lazy. `findFirst()` phù hợp trong ví dụ chỉ có một provider. Nếu ứng dụng hỗ trợ nhiều provider, hãy duyệt toàn bộ hoặc áp dụng quy tắc lựa chọn riêng.

Có thể duyệt các provider:

~~~java
ServiceLoader<Greeter> loader = ServiceLoader.load(Greeter.class);

for (Greeter greeter : loader) {
    System.out.println(greeter.greet("JPMS"));
}
~~~

Hoặc dùng stream để xem metadata provider trước khi yêu cầu instance:

~~~java
ServiceLoader.load(Greeter.class)
        .stream()
        .forEach(provider -> System.out.println(provider.type().getName()));
~~~

Không nên dựa vào thứ tự provider như một quy tắc ưu tiên của ứng dụng. Nếu thứ tự hoặc lựa chọn provider có ý nghĩa nghiệp vụ, hãy định nghĩa tiêu chí rõ ràng trong ứng dụng.

## 6. Ví dụ hoàn chỉnh với ba module

Ví dụ này tạo ba module độc lập:

- `com.example.greeter.api`: định nghĩa interface Greeter.
- `com.example.greeter.provider`: cung cấp FriendlyGreeter bằng `provides ... with ...`.
- `com.example.greeter.app`: khai báo `uses` và gọi ServiceLoader.

Cấu trúc thư mục:

~~~text
module-demo/
└── src/
    ├── com.example.greeter.api/
    │   ├── module-info.java
    │   └── com/example/greeter/api/Greeter.java
    ├── com.example.greeter.provider/
    │   ├── module-info.java
    │   └── com/example/greeter/provider/FriendlyGreeter.java
    └── com.example.greeter.app/
        ├── module-info.java
        └── com/example/greeter/app/Main.java
~~~

### 6.1. Module API

File `src/com.example.greeter.api/module-info.java`:

~~~java
module com.example.greeter.api {
    exports com.example.greeter.api;
}
~~~

File `src/com.example.greeter.api/com/example/greeter/api/Greeter.java`:

~~~java
package com.example.greeter.api;

public interface Greeter {
    String greet(String name);
}
~~~

### 6.2. Module provider

File `src/com.example.greeter.provider/module-info.java`:

~~~java
module com.example.greeter.provider {
    requires com.example.greeter.api;

    provides com.example.greeter.api.Greeter
        with com.example.greeter.provider.FriendlyGreeter;
}
~~~

File `src/com.example.greeter.provider/com/example/greeter/provider/FriendlyGreeter.java`:

~~~java
package com.example.greeter.provider;

import com.example.greeter.api.Greeter;

public final class FriendlyGreeter implements Greeter {
    public FriendlyGreeter() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Provider module không khai báo `exports com.example.greeter.provider`. Consumer không cần truy cập trực tiếp implementation class.

### 6.3. Module consumer

File `src/com.example.greeter.app/module-info.java`:

~~~java
module com.example.greeter.app {
    requires com.example.greeter.api;

    uses com.example.greeter.api.Greeter;
}
~~~

File `src/com.example.greeter.app/com/example/greeter/app/Main.java`:

~~~java
package com.example.greeter.app;

import com.example.greeter.api.Greeter;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        Greeter greeter = ServiceLoader.load(Greeter.class)
                .findFirst()
                .orElseThrow(() ->
                        new IllegalStateException("No Greeter provider found"));

        System.out.println(greeter.greet("JPMS"));
        System.out.println("provider module="
                + greeter.getClass().getModule().getName());
    }
}
~~~

Lưu ý module app chỉ `requires com.example.greeter.api`. Nó không cần `requires com.example.greeter.provider`; provider được tìm thông qua service binding.

### 6.4. Biên dịch

Chạy tại thư mục `module-demo`:

~~~bash
javac --release 17 -d out --module-source-path src -m com.example.greeter.api,com.example.greeter.provider,com.example.greeter.app
~~~

Lệnh biên dịch cả ba module. `--release 17` kiểm tra source và API nền tảng theo Java 17, ngay cả khi compiler đang chạy trên JDK mới hơn.

### 6.5. Chạy từ exploded modules

~~~bash
java --module-path out --module com.example.greeter.app/com.example.greeter.app.Main
~~~

Kết quả stdout:

~~~text
Hello, JPMS!
provider module=com.example.greeter.provider
~~~

Java launcher phân giải module app và các dependency. Vì app khai báo `uses Greeter`, module system có thể bind provider module cung cấp service này khi provider module có thể quan sát được trên module path.

Có thể xem quá trình phân giải:

~~~bash
java --show-module-resolution --module-path out --module com.example.greeter.app/com.example.greeter.app.Main
~~~

Trong output, một dòng có dạng:

~~~text
com.example.greeter.app binds com.example.greeter.provider ...
~~~

Đường dẫn thực tế trong output thay đổi theo máy và cách đóng gói. Dòng `binds` cho thấy provider module được liên kết do service được sử dụng.

## 7. Đóng gói thành modular JAR

Sau khi biên dịch, có thể đóng gói từng module:

~~~bash
mkdir mods
jar --create --file mods/com.example.greeter.api.jar -C out/com.example.greeter.api .
jar --create --file mods/com.example.greeter.provider.jar -C out/com.example.greeter.provider .
jar --create --file mods/com.example.greeter.app.jar -C out/com.example.greeter.app .
~~~

Chạy từ các modular JAR:

~~~bash
java --module-path mods --module com.example.greeter.app/com.example.greeter.app.Main
~~~

Kết quả stdout giống ví dụ trước:

~~~text
Hello, JPMS!
provider module=com.example.greeter.provider
~~~

Kiểm tra module descriptor đã đóng gói:

~~~bash
jar --describe-module --file mods/com.example.greeter.provider.jar
~~~

Output sẽ có thông tin module và directive cung cấp service, ví dụ:

~~~text
provides com.example.greeter.api.Greeter with com.example.greeter.provider.FriendlyGreeter
~~~

Đây là cách xác nhận `provides` đã nằm trong descriptor của modular JAR. Không chỉ dựa vào việc file JAR có chứa class implementation.

## 8. Service binding trong quá trình phân giải module

Service binding là bước module resolution tìm các module cung cấp service mà các module đã được phân giải khai báo qua `uses`.

Với ứng dụng named module chạy bằng Java launcher:

1. Module app là root được chỉ định bằng `--module`.
2. Module system phân giải dependency thông thường như `requires`.
3. Nó đọc các directive `uses` của module đã phân giải.
4. Provider module phù hợp và có thể quan sát được trên module path được bind vào cấu hình.
5. ServiceLoader tìm provider trong module layer đang sử dụng.

Do đó, trong ví dụ trên, provider có thể được bind dù app không khai báo `requires com.example.greeter.provider`.

Nếu provider module không nằm trong nguồn module có thể quan sát, service loader sẽ không tìm thấy provider đó. Nếu có nhiều provider module cho cùng service, nhiều implementation có thể được phát hiện.

### 8.1. Service binding với custom ModuleLayer

Ứng dụng plugin có thể tạo module layer riêng. Khi tự phân giải cấu hình, dùng API `Configuration.resolveAndBind(...)` nếu cần liên kết provider theo các service được sử dụng.

`Configuration.resolve(...)` giải quyết dependency theo các quan hệ module; `resolveAndBind(...)` bổ sung bước service binding. Sau khi có Configuration, ứng dụng có thể tạo layer bằng API `ModuleLayer`.

Ví dụ khung thao tác:

~~~java
Configuration configuration = parent.configuration()
        .resolveAndBind(
                beforeFinder,
                ModuleFinder.of(pluginPath),
                Set.of("com.example.plugin"));

ModuleLayer layer = parent.defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader());
~~~

Đây là khung minh họa cho plugin layer; các biến `parent`, `beforeFinder` và `pluginPath` cần được thiết lập theo ứng dụng thực tế.

Khi tải service trong layer mới, chỉ định layer đó:

~~~java
ServiceLoader<Greeter> loader =
        ServiceLoader.load(layer, Greeter.class);
~~~

Cách này giúp discovery diễn ra trong đúng layer thay vì mặc định dùng layer của ứng dụng chính.

### 8.2. Tạo runtime image bằng jlink

Khi tạo custom runtime image cho ứng dụng dùng service provider, tùy chọn `--bind-services` yêu cầu jlink liên kết provider module và dependency cần thiết:

~~~bash
jlink --module-path mods --add-modules com.example.greeter.app --bind-services --output runtime-image
~~~

Sau đó chạy bằng Java launcher trong image:

~~~bash
runtime-image/bin/java --module com.example.greeter.app/com.example.greeter.app.Main
~~~

Trên Windows:

~~~powershell
.\runtime-image\bin\java.exe --module com.example.greeter.app/com.example.greeter.app.Main
~~~

Chỉ dùng `--bind-services` khi runtime image cần các provider được phát hiện qua service binding. Module path phải chứa các module phù hợp để jlink tìm và liên kết.

## 9. Phân biệt `provides`, `uses`, `requires`, `exports` và `opens`

| Directive | Vai trò | Nơi thường khai báo |
|---|---|---|
| `provides S with P` | Công bố provider P cho service S | Module provider |
| `uses S` | Khai báo module cần sử dụng service S | Module consumer |
| `requires M` | Khai báo dependency và readability đến module M | Module cần M |
| `exports p` | Công bố package p cho truy cập API thông thường | Module sở hữu package |
| `opens p` | Cho phép reflective access đến package p ở runtime | Module sở hữu package |

Các directive giải quyết những câu hỏi khác nhau:

- `requires` cho biết module nào đọc module nào.
- `exports` quyết định package nào có thể được module khác sử dụng trực tiếp.
- `opens` kiểm soát reflective access.
- `uses` mô tả nhu cầu tiêu thụ một service.
- `provides` đăng ký implementation cho service đó.

Không thêm `exports` cho package provider chỉ để ServiceLoader phát hiện implementation. Cũng không thêm `requires` từ consumer đến provider chỉ vì consumer cần service; hãy để consumer phụ thuộc vào service API.

## 10. Nhiều provider và lựa chọn implementation

Một service có thể có nhiều provider:

~~~java
module com.example.provider.bundle {
    requires com.example.codec.api;

    provides com.example.codec.api.Codec
        with com.example.codec.json.JsonCodec,
             com.example.codec.xml.XmlCodec;
}
~~~

Consumer có thể duyệt toàn bộ:

~~~java
ServiceLoader<Codec> codecs = ServiceLoader.load(Codec.class);

for (Codec codec : codecs) {
    System.out.println(codec.getClass().getName());
}
~~~

ServiceLoader không định nghĩa thứ tự provider như một chính sách ưu tiên nghiệp vụ. Nếu cần chọn JSON hay XML, hãy để consumer đọc cấu hình hoặc metadata và chọn theo quy tắc của ứng dụng.

Nếu provider có cấu hình hoặc khởi tạo tốn tài nguyên, có thể dùng provider method hoặc một lớp factory để kiểm soát việc tạo đối tượng. Cần tránh tạo side effect không cần thiết khi provider được discovery hoặc khởi tạo.

## 11. Lỗi thường gặp và cách xử lý

### Consumer thiếu `uses`

Module gọi ServiceLoader cho service type nhưng descriptor không khai báo `uses`.

Cách sửa: thêm đúng service type vào `uses` trong module-info.java của consumer. Tên phải là tên đầy đủ của kiểu service.

### Provider module thiếu `requires` đến service API

Provider class không đọc được service type hoặc không thể triển khai interface.

Cách sửa: thêm `requires` đến module sở hữu service type trong provider module.

### Provider class không đáp ứng quy tắc khởi tạo

Provider class không có public no-argument constructor và cũng không có provider method hợp lệ.

Cách sửa: thêm constructor public không tham số hoặc dùng provider method public static tên `provider`, không có tham số và trả về service type tương thích.

### Service API không export package

Consumer hoặc provider không thể truy cập service type do package chứa interface không được export.

Cách sửa: export package API trong module sở hữu service interface. Không cần export package triển khai provider chỉ để ServiceLoader tìm implementation.

### Provider module không được tìm thấy

Module provider không nằm trên module path hoặc không thuộc tập module có thể quan sát.

Cách sửa: kiểm tra đường dẫn, tên module và descriptor của modular JAR. Nếu ứng dụng dùng custom ModuleLayer, kiểm tra module finder và cách gọi `resolveAndBind`.

### Không tìm thấy provider ở runtime

`ServiceLoader` không trả về provider và code báo không có implementation.

Kiểm tra:

- Consumer đã khai báo `uses` đúng service type chưa?
- Provider module đã khai báo `provides` đúng tên service và provider class chưa?
- Provider module có thể được tìm thấy trên module path/layer không?
- Provider class hoặc provider method có đáp ứng quy tắc không?
- Service API có cùng một module/type identity trong layer consumer và provider không?

### `ServiceConfigurationError`

ServiceLoader có thể ném `ServiceConfigurationError` nếu cấu hình provider sai, provider không hợp lệ hoặc quá trình tạo provider thất bại. Đọc nguyên nhân gốc và kiểm tra descriptor, constructor/provider method cùng dependency của provider.

### Nhiều provider nhưng dùng `findFirst()`

`findFirst()` chỉ lấy provider đầu tiên theo thứ tự discovery. Không dùng nó để ngầm biểu diễn ưu tiên nếu ứng dụng có nhiều implementation. Hãy duyệt tất cả hoặc áp dụng bộ chọn rõ ràng.

## 12. Kiểm tra nhanh trước khi phát hành

- [ ] Service API nằm trong module riêng và export package chứa service type.
- [ ] Provider module khai báo `requires` đến module service API.
- [ ] Provider module có `provides Service with Provider` đúng tên đầy đủ.
- [ ] Provider class có public no-arg constructor hoặc provider method hợp lệ.
- [ ] Consumer module khai báo `uses Service`.
- [ ] Consumer chỉ phụ thuộc vào service API nếu không cần truy cập implementation trực tiếp.
- [ ] Provider package không bị export rộng hơn mức cần thiết.
- [ ] Provider module nằm trên module path hoặc trong module layer phù hợp.
- [ ] Đã kiểm tra service binding bằng `--show-module-resolution`.
- [ ] Đã kiểm tra descriptor bằng `jar --describe-module`.
- [ ] Đã thử chạy ServiceLoader trên runtime image thực tế nếu ứng dụng dùng jlink.
- [ ] Nếu có nhiều provider, đã định nghĩa quy tắc lựa chọn thay vì dựa vào thứ tự discovery.

## Tóm tắt

`provides Service with Provider` được khai báo trong module provider để công bố implementation cho một service type. Module consumer khai báo `uses Service` và dùng `ServiceLoader` để tìm provider. Provider module đọc service API bằng `requires`; consumer cũng đọc API nhưng không cần phụ thuộc trực tiếp vào module triển khai. Package provider có thể giữ kín vì service binding dựa trên module descriptor. Khi chạy named module, service binding có thể tự động liên kết provider có thể quan sát được; với custom layer dùng `Configuration.resolveAndBind`, còn khi tạo runtime image có thể dùng `jlink --bind-services`.

## Tài liệu tham khảo chính thức

- [Java Language Specification 26 — §7.7.4 The provides Directive](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html#jls-7.7.4)
- [Java SE 26 API — ServiceLoader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html)
- [Java SE 26 API — Configuration.resolveAndBind](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/Configuration.html)
- [Java SE 26 API — ModuleLayer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ModuleLayer.html)
- [Java SE 26 API — ModuleDescriptor.Provides](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/ModuleDescriptor.Provides.html)
- [The java Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [The jar Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html)
- [The jlink Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
