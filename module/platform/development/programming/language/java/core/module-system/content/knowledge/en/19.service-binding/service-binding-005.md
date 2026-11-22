# Service binding với nhiều provider

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vì sao một service có thể có nhiều provider trong hệ thống module.
- Phân biệt nhiều provider được khai báo trong cùng một module với provider nằm ở nhiều module khác nhau.
- Hiểu vai trò của directive `uses`, `provides` và bước service binding khi resolve module.
- Dùng `Configuration.resolveAndBind()` và `ServiceLoader` để tìm nhiều provider.
- Xử lý thứ tự provider một cách chủ động thay vì dựa vào thứ tự phát hiện.

## 1. Service có thể có nhiều provider

Trong Java Platform Module System (JPMS), service là một abstraction mà module tiêu thụ muốn sử dụng. Provider là implementation cung cấp khả năng cụ thể cho service đó.

Một service có thể có nhiều implementation cùng lúc. Ví dụ, ứng dụng cần một service định dạng dữ liệu và có thể sử dụng các provider khác nhau:

- JSON provider chuyển dữ liệu sang JSON.
- XML provider chuyển dữ liệu sang XML.
- YAML provider chuyển dữ liệu sang YAML.

Các provider cùng implement một service interface, vì vậy module tiêu thụ chỉ cần biết API của service. Nó không cần phụ thuộc trực tiếp vào từng module triển khai.

Có hai cách tổ chức phổ biến:

1. Một provider module khai báo nhiều provider class trong cùng một directive `provides`.
2. Nhiều provider module riêng biệt cùng khai báo `provides` cho một service.

Hai cách này có thể cùng tồn tại trong một module graph.

## 2. Khai báo một service API

Giả sử service API có module name là `com.example.format.api` và export package chứa interface:

~~~java
module com.example.format.api {
    exports com.example.format;
}
~~~

Service interface:

~~~java
package com.example.format;

public interface Formatter {
    String format(String input);
}
~~~

Module API chỉ định nghĩa contract. Nó không cần biết provider JSON hay XML được triển khai như thế nào.

Module tiêu thụ và các provider đều cần đọc được module API. Vì thế, mỗi module sử dụng service interface sẽ khai báo `requires com.example.format.api;`.

## 3. Nhiều provider trong các module khác nhau

### 3.1. JSON provider

Provider JSON được đặt trong module riêng:

~~~java
module com.example.format.provider.json {
    requires com.example.format.api;

    provides com.example.format.Formatter
            with com.example.format.json.JsonFormatter;
}
~~~

Implementation:

~~~java
package com.example.format.json;

import com.example.format.Formatter;

public final class JsonFormatter implements Formatter {

    public JsonFormatter() {
    }

    @Override
    public String format(String input) {
        return "{\"value\":\"" + input + "\"}";
    }
}
~~~

### 3.2. XML provider

Provider XML cũng có module riêng:

~~~java
module com.example.format.provider.xml {
    requires com.example.format.api;

    provides com.example.format.Formatter
            with com.example.format.xml.XmlFormatter;
}
~~~

Implementation:

~~~java
package com.example.format.xml;

import com.example.format.Formatter;

public final class XmlFormatter implements Formatter {

    public XmlFormatter() {
    }

    @Override
    public String format(String input) {
        return "<value>" + input + "</value>";
    }
}
~~~

Hai module provider đều khai báo service giống nhau trong directive `provides`, nhưng trỏ tới implementation khác nhau. Mỗi provider class ở ví dụ này là public và có public constructor không tham số.

### 3.3. Module tiêu thụ service

Module ứng dụng khai báo module API và service mà nó sử dụng:

~~~java
module com.example.format.app {
    requires com.example.format.api;

    uses com.example.format.Formatter;
}
~~~

Directive `uses` nói với hệ thống module rằng ứng dụng sử dụng service `Formatter`. Ứng dụng không cần khai báo `requires com.example.format.provider.json;` hoặc `requires com.example.format.provider.xml;` chỉ để tìm provider.

Đây là điểm quan trọng của service binding: module tiêu thụ phụ thuộc vào abstraction, còn các provider có thể được bổ sung qua module resolution.

## 4. Service binding trong quá trình resolve module

Service binding là bước mở rộng module graph dựa trên các service mà module đã resolve khai báo sử dụng.

Giả sử module graph ban đầu có ứng dụng và module API:

~~~text
com.example.format.app
        |
        | requires
        v
com.example.format.api
~~~

Ứng dụng khai báo:

~~~java
uses com.example.format.Formatter;
~~~

Nếu các provider module có thể quan sát được trong tập module đầu vào, quá trình service binding có thể bổ sung cả hai provider vào graph:

~~~text
                     +-------------------------------+
                     |                               |
                     v                               v
com.example.format.provider.json       com.example.format.provider.xml
                     |                               |
                     +---------------+---------------+
                                     |
                                     | provides Formatter
                                     v
                           com.example.format.Formatter
                                     ^
                                     |
                                     | uses
                                     |
                           com.example.format.app
~~~

Với nhiều provider, hệ thống không cần chọn một provider duy nhất ở bước binding. Tất cả provider module phù hợp và có thể quan sát được đều có thể được thêm vào module graph.

Khi provider module được thêm vào graph, các dependency mà provider khai báo bằng `requires` cũng được resolve. Quá trình service binding tiếp tục cho đến khi không còn provider module mới nào được thêm vào.

### 4.1. `resolve()` và `resolveAndBind()`

API `java.lang.module.Configuration` cung cấp hai phương thức có ý nghĩa khác nhau:

| Phương thức | Hành vi |
|---|---|
| `resolve(...)` | Resolve graph dựa trên các root module và dependency `requires`. |
| `resolveAndBind(...)` | Resolve graph và thực hiện thêm service binding dựa trên các directive `uses` / `provides`. |

Vì vậy, khi tự tạo một module configuration và muốn tự động đưa các provider module vào graph dựa trên service, hãy dùng `resolveAndBind()`.

Service binding chỉ có thể thêm provider mà module finder hoặc parent configuration có thể quan sát được. Nếu provider JAR không nằm trong module path/finder được cung cấp, hoặc module không khai báo provider phù hợp, nó sẽ không tự xuất hiện trong graph.

## 5. Tạo ModuleLayer có nhiều provider

Ví dụ sau tạo một layer mới từ thư mục module. Thư mục `mods` được giả định chứa các module API, app, JSON provider và XML provider dưới dạng modular JAR hoặc exploded modules.

~~~java
import com.example.format.Formatter;

import java.nio.file.Path;
import java.util.ServiceLoader;
import java.util.Set;
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;

public class LayerBootstrap {

    public static void main(String[] args) {
        Path modulesPath = Path.of("mods");

        ModuleFinder finder = ModuleFinder.of(modulesPath);

        Configuration configuration =
                ModuleLayer.boot()
                        .configuration()
                        .resolveAndBind(
                                ModuleFinder.of(),
                                finder,
                                Set.of("com.example.format.app"));

        ModuleLayer layer =
                ModuleLayer.boot()
                        .defineModulesWithOneLoader(
                                configuration,
                                ClassLoader.getSystemClassLoader());

        ServiceLoader<Formatter> loader =
                ServiceLoader.load(layer, Formatter.class);

        loader.forEach(formatter ->
                System.out.println(formatter.format("hello")));
    }
}
~~~

Các bước chính:

1. `ModuleFinder.of(modulesPath)` tạo module finder cho thư mục chứa các module.
2. `resolveAndBind(...)` bắt đầu từ root module `com.example.format.app`, resolve dependency và bổ sung provider module phù hợp.
3. `defineModulesWithOneLoader(...)` định nghĩa các module đã resolve trong một layer mới.
4. `ServiceLoader.load(layer, Formatter.class)` tìm service provider thuộc layer được chỉ định.
5. Duyệt loader để nhận instance từ các provider đã tìm thấy.

Trong ví dụ, `ModuleFinder.of()` đầu tiên là finder rỗng cho vị trí tìm kiếm ưu tiên trước parent configuration. Finder thứ hai chứa các module của ứng dụng. Nếu module API đã có trong boot layer thì dependency đó có thể được thỏa mãn từ parent configuration; nếu chưa có, hãy đặt module API trong thư mục module đầu vào.

Lưu ý rằng `resolveAndBind()` chỉ resolve module graph. Nó không tự tạo instance của provider. Việc tạo instance xảy ra khi ứng dụng tiêu thụ `ServiceLoader`, chẳng hạn bằng `forEach()`, iterator hoặc stream.

## 6. Nhiều provider trong cùng một module

JPMS cũng cho phép một module khai báo nhiều provider class cho cùng một service trong một directive `provides`.

Ví dụ:

~~~java
module com.example.format.provider.bundle {
    requires com.example.format.api;

    provides com.example.format.Formatter
            with com.example.format.json.JsonFormatter,
                 com.example.format.xml.XmlFormatter;
}
~~~

Trong trường hợp này, một provider module đóng gói cả hai implementation. Khi module này được resolve vào layer, `ServiceLoader` có thể tìm thấy cả hai provider class.

Có thể phân biệt hai cách tổ chức như sau:

| Cách tổ chức | Ví dụ | Đơn vị được thêm vào module graph |
|---|---|---|
| Nhiều module, mỗi module một provider | `provider.json`, `provider.xml` | Từng provider module |
| Một module, nhiều provider class | `provider.bundle` khai báo hai class | Một provider module; loader tìm các provider class được khai báo |

Chọn cách tổ chức theo nhu cầu đóng gói và triển khai. Tách module cho phép phân phối provider độc lập; gom nhiều provider vào một module giúp triển khai chúng như một đơn vị.

## 7. Nhận và xử lý nhiều provider bằng ServiceLoader

Khi các provider đã nằm trong layer mà loader tìm kiếm, ứng dụng có thể lấy tất cả provider:

~~~java
ServiceLoader<Formatter> loader =
        ServiceLoader.load(Formatter.class);

for (Formatter formatter : loader) {
    System.out.println(formatter.format("hello"));
}
~~~

Trong một ứng dụng dùng custom layer, hãy dùng overload nhận layer:

~~~java
ServiceLoader<Formatter> loader =
        ServiceLoader.load(layer, Formatter.class);
~~~

Nếu muốn kiểm tra kiểu provider trước khi tạo instance, sử dụng `stream()`:

~~~java
loader.stream()
        .filter(provider ->
                provider.type().getPackageName()
                        .startsWith("com.example.format"))
        .map(ServiceLoader.Provider::get)
        .forEach(formatter ->
                System.out.println(formatter.format("hello")));
~~~

`stream()` trả về các đối tượng `ServiceLoader.Provider<Formatter>`. Ứng dụng có thể dùng `type()` để kiểm tra kiểu provider rồi mới gọi `get()` cho những provider được chọn.

### 7.1. Không phụ thuộc thứ tự phát hiện

Không nên giả định provider luôn được trả về theo thứ tự JSON rồi XML, hoặc theo thứ tự khai báo trong module descriptor. Thứ tự phát hiện provider không phải là hợp đồng để ứng dụng dựa vào.

Nếu cần thứ tự ổn định, hãy sắp xếp rõ ràng trước khi lấy instance:

~~~java
loader.stream()
        .sorted((left, right) ->
                left.type().getName()
                        .compareTo(right.type().getName()))
        .map(ServiceLoader.Provider::get)
        .forEach(formatter ->
                System.out.println(formatter.format("hello")));
~~~

Nếu thứ tự nghiệp vụ cần dựa trên độ ưu tiên, hãy định nghĩa metadata/contract ưu tiên riêng trong service API hoặc provider, sau đó sắp xếp theo quy tắc đó. Tên lớp chỉ phù hợp khi thứ tự từ điển thực sự là điều ứng dụng mong muốn.

## 8. Những tình huống cần kiểm tra

Khi một provider không xuất hiện trong kết quả, hãy kiểm tra lần lượt:

- Consumer module đã khai báo `uses ServiceType;` chưa?
- Provider module đã khai báo đúng `provides ServiceType with ProviderClass;` chưa?
- Provider module có thể được quan sát qua module finder hoặc parent configuration không?
- Module provider có được thêm vào configuration/layer đang được sử dụng không?
- Ứng dụng có đang gọi đúng overload của `ServiceLoader.load(...)` cho boot layer hoặc custom layer không?
- Provider class có tuân thủ quy tắc provider của ServiceLoader và có thể được khởi tạo không?

Một lỗi thường gặp là chỉ đặt provider JAR trong thư mục trên ổ đĩa rồi kỳ vọng loader tự tìm thấy. Provider phải thuộc module configuration/layer mà loader đang tìm kiếm.

Khi duyệt hoặc tạo instance, cấu hình provider không hợp lệ có thể dẫn tới `ServiceConfigurationError`. Hãy xử lý lỗi ở ranh giới phù hợp của ứng dụng, đồng thời giữ thông tin nguyên nhân để chẩn đoán provider nào gặp sự cố.

## 9. Tóm tắt

Một service có thể được cung cấp bởi nhiều provider class trong cùng một module hoặc bởi nhiều provider module độc lập. Consumer khai báo `uses` để thể hiện nhu cầu sử dụng service; provider module khai báo `provides ... with ...` để đăng ký implementation.

Khi cần resolve module graph có service binding, `Configuration.resolveAndBind()` bổ sung các provider module phù hợp mà hệ thống có thể quan sát được. Sau khi các module được định nghĩa trong layer, `ServiceLoader` tìm và tạo instance của các provider. Ứng dụng nên xử lý thứ tự provider một cách tường minh nếu thứ tự đó ảnh hưởng tới nghiệp vụ.

Tài liệu tham khảo:

- [Configuration — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html)
- [ModuleLayer — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html)
- [ServiceLoader — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html)
