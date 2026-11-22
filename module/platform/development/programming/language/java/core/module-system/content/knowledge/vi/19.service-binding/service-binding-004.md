# Provider module được kéo vào module graph thế nào?

## 1. Mục tiêu

Trong Java Platform Module System (JPMS), một module sử dụng service có thể không khai báo `requires` trực tiếp tới module triển khai service đó. Đây là chủ ý của cơ chế Service Binding: module tiêu thụ khai báo **service mà nó cần**, module provider khai báo **service mà nó cung cấp**, rồi bộ phân giải module có thể tự đưa provider module phù hợp vào module graph.

Cần phân biệt ba việc:

1. **Khai báo service contract:** consumer dùng `uses`, provider dùng `provides ... with ...`.
2. **Service binding:** bộ phân giải tìm các provider module phù hợp và bổ sung chúng vào cấu hình/module graph.
3. **Sử dụng service:** `ServiceLoader` tìm provider và tạo service instance khi ứng dụng yêu cầu.

Service binding giải quyết việc module nào có mặt trong graph. Nó không tự tạo instance của implementation.

Sau bài này, bạn có thể giải thích vì sao consumer không cần `requires` provider, phân biệt `resolve()` với `resolveAndBind()`, và kiểm tra provider module đã được đưa vào một configuration hay chưa.

## 2. Ví dụ gồm ba module

Giả sử có ba module:

- `com.example.greeting.api`: định nghĩa service interface.
- `com.example.greeting.app`: tiêu thụ service.
- `com.example.greeting.provider`: cung cấp implementation.

Quan hệ mong muốn:

```text
com.example.greeting.app
        |
        | uses GreetingService
        v
GreetingService (API contract)
        ^
        | provides GreetingService with ...
        |
com.example.greeting.provider
```

Consumer phụ thuộc vào API contract. Nó không cần biết tên implementation cụ thể. Provider module phụ thuộc vào API để triển khai interface.

## 3. Hai directive tạo nên service binding

### Module API

`module-info.java` của module API:

```java
module com.example.greeting.api {
    exports com.example.greeting.api;
}
```

Service interface:

```java
package com.example.greeting.api;

public interface GreetingService {
    String greet(String name);
}
```

### Module consumer

`module-info.java` của ứng dụng:

```java
module com.example.greeting.app {
    requires com.example.greeting.api;

    uses com.example.greeting.api.GreetingService;
}
```

Directive `uses` nói rằng module app cần tìm implementation của `GreetingService`. Nó không chỉ định implementation class hoặc provider module cụ thể.

### Module provider

`module-info.java` của provider:

```java
module com.example.greeting.provider {
    requires com.example.greeting.api;

    provides com.example.greeting.api.GreetingService
        with com.example.greeting.provider.FormalGreetingService;
}
```

Implementation:

```java
package com.example.greeting.provider;

import com.example.greeting.api.GreetingService;

public final class FormalGreetingService implements GreetingService {

    public FormalGreetingService() {
        System.out.println("FormalGreetingService initialized");
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

Directive `provides S with P` đăng ký class `P` làm provider cho service type `S`. Provider module cần đọc được module chứa service API, vì vậy nó khai báo `requires com.example.greeting.api`.

Package chứa implementation không cần được export chỉ để ServiceLoader phát hiện provider được khai báo bằng `provides`. Module descriptor đã công bố mối liên hệ giữa service và provider.

## 4. Vì sao requires thông thường chưa đủ?

Module resolver bắt đầu từ các root modules rồi giải quyết những module được chúng yêu cầu bằng directive `requires`, tiếp tục theo các dependency của chúng.

Nếu app chỉ khai báo:

```java
requires com.example.greeting.api;
uses com.example.greeting.api.GreetingService;
```

thì dependency graph thông thường có API module, nhưng không có cạnh `requires` nào dẫn tới `com.example.greeting.provider`.

Directive `uses` không tương đương `requires`. Nó khai báo nhu cầu về một service, để cơ chế service binding có thể tìm module cung cấp service đó. Nhờ vậy, app không bị gắn cứng vào một implementation và có thể thay provider mà không phải sửa module descriptor của app.

Điều này cũng có nghĩa là việc đặt provider JAR trên module path chưa tự động bảo đảm provider module sẽ nằm trong configuration. Provider phải được bộ phân giải nhìn thấy và service binding phải được thực hiện.

## 5. resolve() và resolveAndBind() khác nhau thế nào?

Hai phương thức đều giải quyết module roots và các dependency cần thiết. Khác biệt nằm ở bước service binding.

| Phương thức | Cách tạo module graph |
| --- | --- |
| `Configuration.resolve(...)` | Giải quyết roots cùng dependency closure theo các directive `requires`. |
| `Configuration.resolveAndBind(...)` | Thực hiện resolution thông thường, sau đó bổ sung các provider module cho service được dùng trong graph; tiếp tục cho đến khi không còn provider module mới. |

Nếu provider module đã được kéo vào graph bằng `requires` hoặc được chỉ định làm root, nó vẫn có mặt khi dùng `resolve()`. Service binding hữu ích khi provider không phải dependency tường minh của consumer.

### Thuật toán service binding

Có thể hình dung quá trình như sau:

1. Resolver giải quyết các root modules và toàn bộ dependency `requires` của chúng.
2. Resolver xem các module đã giải quyết để thu thập những service type được khai báo trong directive `uses`.
3. Resolver tìm các module có thể quan sát được và có directive `provides` cho những service type đó.
4. Các provider module phù hợp được thêm vào graph; dependency `requires` của chúng cũng được giải quyết.
5. Resolver tiếp tục kiểm tra các module mới được thêm. Nếu provider module cũng khai báo `uses` service khác, các provider tương ứng có thể tiếp tục được bổ sung.
6. Quá trình dừng khi không còn provider module mới nào được thêm.

Đây là một dạng closure: graph mở rộng từ roots, dependency thông thường và các provider được phát hiện qua service binding.

Nếu có nhiều provider module khả kiến cùng cung cấp một service được sử dụng, service binding có thể đưa tất cả các provider phù hợp vào graph. Việc lựa chọn hoặc sử dụng một hay nhiều implementation là quyết định ở tầng ứng dụng thông qua ServiceLoader và logic của ứng dụng.

## 6. Tự tạo module layer với resolveAndBind()

Giả sử các module đã được biên dịch thành JAR trong thư mục `mods/`. Ta muốn tạo một layer con có root là `com.example.greeting.app`.

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class LayerBootstrap {

    public static void main(String[] args) {
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

        Configuration parentConfiguration =
            ModuleLayer.boot().configuration();

        Configuration configuration =
            parentConfiguration.resolveAndBind(
                finder,
                ModuleFinder.of(),
                Set.of("com.example.greeting.app")
            );

        ModuleLayer layer =
            ModuleLayer.boot().defineModulesWithOneLoader(
                configuration,
                ClassLoader.getSystemClassLoader()
            );

        System.out.println(
            "Provider module resolved: "
                + configuration.findModule("com.example.greeting.provider").isPresent()
        );
    }
}
```

Giải thích các tham số:

- `finder`: nơi resolver tìm các module có thể quan sát, bao gồm app, API và provider trong ví dụ.
- `ModuleFinder.of()`: finder rỗng ở vị trí tìm kiếm sau các parent configuration.
- `Set.of("com.example.greeting.app")`: root module cần khởi chạy.
- `resolveAndBind`: giải quyết dependency và bổ sung provider module phù hợp.
- `defineModulesWithOneLoader`: tạo layer mới từ configuration đã giải quyết, dùng một class loader cho các module trong layer theo chính sách của API.

Dòng `configuration.findModule(...).isPresent()` kiểm tra provider module có trong configuration hay không. Đây là bằng chứng ở cấp module graph; nó chưa chứng minh constructor của provider đã chạy.

## 7. Dùng ServiceLoader sau khi layer đã được tạo

Khi module layer đã chứa provider module, ứng dụng có thể tìm service trong layer đó:

```java
import com.example.greeting.api.GreetingService;
import java.util.ServiceLoader;

ServiceLoader<GreetingService> services =
    ServiceLoader.load(layer, GreetingService.class);

services.stream()
    .map(ServiceLoader.Provider::get)
    .forEach(provider ->
        System.out.println(provider.greet("Java"))
    );
```

Trong module app, directive `uses com.example.greeting.api.GreetingService` vẫn cần được khai báo để module có quyền sử dụng service type đó qua ServiceLoader.

Có hai giai đoạn riêng:

- Khi gọi `resolveAndBind`, resolver tìm provider module và đưa module đó vào configuration.
- Khi gọi `ServiceLoader` và yêu cầu provider instance bằng `Provider.get()` hoặc duyệt instance qua iterator, implementation mới được yêu cầu khởi tạo.

Nếu chỉ muốn xem loại provider trước khi khởi tạo, có thể dùng `services.stream()` và `Provider.type()`. Bản thân service binding không gọi constructor của provider.

## 8. Điều kiện để provider module được kéo vào graph

Provider module chỉ có thể được thêm khi các điều kiện cần thiết được đáp ứng:

- **Consumer khai báo `uses`:** service type phải xuất hiện trong module descriptor của một module đã được giải quyết.
- **Provider khai báo `provides`:** provider module phải đăng ký đúng service type bằng directive `provides S with P`.
- **Provider có thể được tìm thấy:** module phải nằm trong phạm vi mà các `ModuleFinder` và cấu hình parent cho phép resolver quan sát. Có file JAR ở một vị trí mà finder không tìm kiếm thì chưa đủ.
- **Provider module hợp lệ:** các dependency của provider phải được giải quyết và descriptor/provider declaration phải hợp lệ.
- **Dùng cơ chế có service binding:** cần gọi `resolveAndBind` hoặc dùng công cụ khởi chạy/đóng gói có bật service binding phù hợp. `resolve()` đơn thuần không thực hiện bước bổ sung provider này.

Nếu không tìm thấy provider phù hợp, resolver không tự tạo implementation và service có thể không có provider nào. Ứng dụng nên xác định service đó là bắt buộc hay tùy chọn và xử lý trường hợp không có provider ở tầng sử dụng.

## 9. Module path, classpath và jlink

Với named modules, provider được công bố trong `module-info.java` bằng `provides ... with ...`; service consumer khai báo `uses`. Đây là metadata mà module resolver dùng cho service binding.

Với provider đặt trên classpath, cách đăng ký truyền thống là file:

```text
META-INF/services/com.example.greeting.api.GreetingService
```

File chứa tên đầy đủ của các provider class. ServiceLoader có thể đọc cấu hình này qua class loader, nhưng classpath provider không phải một named provider module để resolver bổ sung vào module graph theo cùng cơ chế `provides` của JPMS.

Ở bước tạo runtime image, công cụ `jlink` có tùy chọn `--bind-services` để đưa các module provider cần thiết và dependency của chúng vào image dựa trên service được các module đã chọn sử dụng. Đây là bước liên kết service khi đóng gói runtime image; nó không phải thao tác khởi tạo service instance lúc chạy ứng dụng.

## 10. Những nhầm lẫn thường gặp

- **`uses` không phải `requires`:** `uses` khai báo service dependency. Nó không tạo một dependency tường minh từ consumer tới provider module.
- **Có trên module path không có nghĩa là có trong graph:** resolver chỉ dùng các module quan sát được trong phạm vi finder và quy tắc resolution hiện hành.
- **`resolve()` không tự động bind provider:** nếu cần kéo provider module theo service usage, dùng `resolveAndBind()`.
- **Service binding không chọn duy nhất một provider:** nhiều provider phù hợp có thể cùng được thêm vào graph. Ứng dụng quyết định provider nào sẽ được sử dụng.
- **Có trong graph không có nghĩa là đã khởi tạo:** configuration và module layer mô tả module đã được giải quyết. Service instance chỉ được yêu cầu ở bước sử dụng service.
- **Không cần consumer đọc package implementation:** app phụ thuộc vào API contract; provider module công bố implementation bằng descriptor và có thể giữ package triển khai ở trạng thái encapsulated.

## 11. Ghi nhớ

- Consumer khai báo service cần dùng bằng `uses`.
- Provider module công bố implementation bằng `provides S with P`.
- Resolver thông thường theo `requires`; service binding mở rộng graph theo các service được sử dụng.
- `Configuration.resolveAndBind()` lặp việc tìm provider và giải quyết dependency cho đến khi không còn module mới.
- `ServiceLoader` sử dụng provider trong layer; `Provider.get()` mới yêu cầu service instance.

Khi cần chẩn đoán một provider không xuất hiện, hãy kiểm tra lần lượt: consumer có `uses` đúng service type không, provider có `provides` đúng type không, module finder có nhìn thấy provider không, và configuration được tạo bằng `resolveAndBind` hay chỉ `resolve`.
