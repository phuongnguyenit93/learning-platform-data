# Chạy ServiceLoader trên module path

## 1. Mục tiêu

Java ServiceLoader cho phép một module sử dụng service interface mà không cần phụ thuộc trực tiếp vào class triển khai. Khi chạy trên Java Platform Module System (JPMS), service API, module tiêu thụ và module provider có thể được đóng gói thành các named module riêng biệt.

Để ServiceLoader tìm được implementation trên module path, cần phối hợp ba phần:

1. Module API công khai service interface.
2. Module consumer khai báo service cần dùng bằng directive `uses`.
3. Module provider khai báo implementation bằng directive `provides ... with ...`.

Khi khởi chạy ứng dụng, module resolver phải nhìn thấy provider module và đưa nó vào module graph. Sau đó ServiceLoader mới có thể khám phá provider và cung cấp service instance.

Bài này dựng một ví dụ hoàn chỉnh gồm ba module, biên dịch thành modular JAR, chạy ứng dụng trên module path, rồi xử lý các lỗi thường gặp.

Sau bài này, bạn có thể:

- Phân biệt service API, consumer và provider module.
- Viết đúng `uses` và `provides ... with ...` trong `module-info.java`.
- Biên dịch nhiều module và đóng gói thành modular JAR.
- Chạy ứng dụng bằng `java --module-path` và `--module`.
- Dùng `ServiceLoader.load` để lấy provider.
- Kiểm tra module resolution và chẩn đoán khi ServiceLoader không tìm thấy provider.

## 2. Cấu trúc dự án

Ta xây dựng ứng dụng greeting với ba module:

| Module | Trách nhiệm |
| --- | --- |
| `com.example.greeting.api` | Khai báo service interface mà consumer và provider cùng sử dụng. |
| `com.example.greeting.provider` | Cung cấp implementation cho service. |
| `com.example.greeting.app` | Khởi chạy ứng dụng và yêu cầu ServiceLoader tìm provider. |

Cấu trúc source tree:

~~~text
service-loader-demo/
└── src/
    ├── com.example.greeting.api/
    │   ├── module-info.java
    │   └── com/example/greeting/api/GreetingService.java
    ├── com.example.greeting.provider/
    │   ├── module-info.java
    │   └── com/example/greeting/provider/FormalGreetingService.java
    └── com.example.greeting.app/
        ├── module-info.java
        └── com/example/greeting/app/Main.java
~~~

Mỗi module có một `module-info.java` ở gốc source tree của module. Tên thư mục module khớp với tên module được khai báo trong descriptor.

## 3. Khai báo service API

Module API chỉ định package chứa interface được export:

~~~java
// src/com.example.greeting.api/module-info.java
module com.example.greeting.api {
    exports com.example.greeting.api;
}
~~~

Service interface:

~~~java
// src/com.example.greeting.api/com/example/greeting/api/GreetingService.java
package com.example.greeting.api;

public interface GreetingService {
    String greet(String name);
}
~~~

Module API không cần biết implementation nào sẽ được sử dụng. Nó chỉ định nghĩa contract chung để consumer gọi và provider triển khai.

Package chứa interface phải được export vì consumer cần đọc kiểu `GreetingService`, còn provider cần implement interface đó.

## 4. Khai báo provider module bằng provides

Module provider phụ thuộc vào API và công bố implementation trong descriptor:

~~~java
// src/com.example.greeting.provider/module-info.java
module com.example.greeting.provider {
    requires com.example.greeting.api;

    provides com.example.greeting.api.GreetingService
        with com.example.greeting.provider.FormalGreetingService;
}
~~~

Implementation:

~~~java
// src/com.example.greeting.provider/com/example/greeting/provider/FormalGreetingService.java
package com.example.greeting.provider;

import com.example.greeting.api.GreetingService;

public final class FormalGreetingService implements GreetingService {

    public FormalGreetingService() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Directive `provides S with P` có nghĩa module này cung cấp implementation `P` cho service type `S`.

Trong ví dụ, provider module khai báo `requires com.example.greeting.api` để đọc service interface. Package triển khai `com.example.greeting.provider` không cần export chỉ để ServiceLoader phát hiện provider được đăng ký trong module descriptor. Module system có thể khám phá provider thông qua metadata `provides` mà vẫn giữ package implementation được encapsulate.

Với cách khởi tạo bằng constructor, provider class cần có constructor public không tham số. JPMS cũng hỗ trợ provider method tĩnh theo quy tắc của ServiceLoader, nhưng ví dụ này dùng constructor để dễ theo dõi.

## 5. Khai báo consumer module bằng uses

Module ứng dụng đọc API và khai báo service cần tìm:

~~~java
// src/com.example.greeting.app/module-info.java
module com.example.greeting.app {
    requires com.example.greeting.api;

    uses com.example.greeting.api.GreetingService;
}
~~~

Directive `uses` nói rằng module app sử dụng service type `GreetingService`. Nó không nêu tên provider module và không tạo dependency tường minh từ app tới `com.example.greeting.provider`.

Đây là điểm quan trọng của ServiceLoader: consumer phụ thuộc vào contract, còn implementation có thể được thay thế bằng provider khác mà không cần sửa code consumer.

## 6. Viết code gọi ServiceLoader

Main class:

~~~java
// src/com.example.greeting.app/com/example/greeting/app/Main.java
package com.example.greeting.app;

import com.example.greeting.api.GreetingService;
import java.util.ServiceLoader;

public class Main {

    public static void main(String[] args) {
        ServiceLoader<GreetingService> services =
            ServiceLoader.load(GreetingService.class);

        boolean found = false;

        for (GreetingService service : services) {
            found = true;
            System.out.println(service.greet("Java Module System"));
        }

        if (!found) {
            throw new IllegalStateException(
                "No GreetingService provider is available"
            );
        }
    }
}
~~~

Các bước thực hiện:

1. `ServiceLoader.load(GreetingService.class)` tạo loader cho service type.
2. Loader khám phá các provider khả dụng trong môi trường module/class loader hiện tại.
3. Vòng lặp lấy từng service instance.
4. Consumer gọi method trên interface `GreetingService`, không cần tham chiếu implementation class.

Vì app là named module và dùng service type, directive `uses` trong `module-info.java` là bắt buộc. Nếu thiếu, ServiceLoader có thể ném `ServiceConfigurationError` khi kiểm tra quyền sử dụng service.

Nếu chỉ cần một provider, có thể dùng:

~~~java
GreetingService service = ServiceLoader
    .load(GreetingService.class)
    .findFirst()
    .orElseThrow(() ->
        new IllegalStateException("No GreetingService provider found")
    );
~~~

Nếu ứng dụng có thể có nhiều implementation, hãy quyết định rõ có dùng tất cả provider hay chọn một provider theo metadata/cấu hình. Không nên dựa vào thứ tự khám phá như một cơ chế ưu tiên ổn định.

## 7. Biên dịch các module từ source tree

Từ thư mục gốc `service-loader-demo`, tạo output directory và biên dịch ba module:

~~~bash
javac --module-source-path src -d mods -m com.example.greeting.api,com.example.greeting.provider,com.example.greeting.app
~~~

Trong đó:

- `--module-source-path src` chỉ vị trí chứa source tree của các module.
- `-d mods` đặt output đã biên dịch vào thư mục `mods`.
- `-m` chỉ định các module cần biên dịch.

Sau khi biên dịch, cấu trúc output có dạng:

~~~text
mods/
├── com.example.greeting.api/
│   ├── module-info.class
│   └── com/example/greeting/api/GreetingService.class
├── com.example.greeting.provider/
│   ├── module-info.class
│   └── com/example/greeting/provider/FormalGreetingService.class
└── com.example.greeting.app/
    ├── module-info.class
    └── com/example/greeting/app/Main.class
~~~

Đây là exploded modules: mỗi module là một thư mục chứa `module-info.class` và các class đã biên dịch.

Nếu source tree không đúng cấu trúc, compiler có thể báo không tìm thấy module hoặc package. Hãy kiểm tra tên thư mục module, vị trí `module-info.java`, package declaration và các directive `requires`/ `exports`.

## 8. Chạy ứng dụng bằng module path

Dùng launcher Java với module path trỏ tới thư mục `mods`:

~~~bash
java --module-path mods --module com.example.greeting.app/com.example.greeting.app.Main
~~~

Dạng viết ngắn:

~~~bash
java -p mods -m com.example.greeting.app/com.example.greeting.app.Main
~~~

Trong lệnh:

- `--module-path mods` hoặc `-p mods` chỉ nơi chứa các module đã biên dịch.
- `--module` hoặc `-m` chọn module ứng dụng và main class.
- Phần trước dấu `/` là tên module.
- Phần sau dấu `/` là tên đầy đủ của main class.

Kết quả mong đợi:

~~~text
Hello, Java Module System!
~~~

Khi launcher resolve module graph, consumer khai báo `uses` và provider module có `provides` phù hợp. Cơ chế service binding của launcher có thể đưa provider module khả kiến vào configuration để ServiceLoader khám phá được.

Provider module phải nằm trong phạm vi module path mà launcher có thể quan sát. Chỉ có file JAR ở một thư mục không được chỉ định trong module path thì chưa đủ.

## 9. Đóng gói thành modular JAR

Thay vì chạy exploded modules, có thể đóng gói từng module thành modular JAR.

~~~bash
jar --create --file mods/com.example.greeting.api.jar -C mods/com.example.greeting.api .
jar --create --file mods/com.example.greeting.provider.jar -C mods/com.example.greeting.provider .
jar --create --file mods/com.example.greeting.app.jar -C mods/com.example.greeting.app .
~~~

Các file JAR vẫn chứa `module-info.class`, nên module name được xác định bởi descriptor chứ không phụ thuộc tên file.

Chạy ứng dụng từ các modular JAR:

~~~bash
java --module-path mods --module com.example.greeting.app/com.example.greeting.app.Main
~~~

Module path có thể chứa modular JAR hoặc exploded module. Cả hai đều có thể được dùng để resolve named modules nếu cấu trúc hợp lệ.

Có thể kiểm tra descriptor của provider:

~~~bash
jar --describe-module --file mods/com.example.greeting.provider.jar
~~~

Kết quả cần thể hiện module name và directive `provides com.example.greeting.api.GreetingService with ...`.

## 10. ServiceLoader.load và ModuleLayer

Ví dụ trước dùng:

~~~java
ServiceLoader.load(GreetingService.class)
~~~

Cách này dùng thread context class loader để tìm provider trong môi trường loader hiện tại. Với ứng dụng chạy trên module path chuẩn, đây thường là cách đơn giản nhất.

Nếu ứng dụng tạo module layer riêng bằng API `ModuleLayer`, hãy dùng overload nhận layer:

~~~java
ServiceLoader<GreetingService> services =
    ServiceLoader.load(customLayer, GreetingService.class);
~~~

Overload này tìm provider trong layer được chỉ định và các ancestor layer của nó. Điều này hữu ích khi plugin hoặc provider được nạp vào layer động, tách khỏi boot layer.

Ví dụ khái niệm:

~~~java
ModuleLayer customLayer = /* layer đã được resolve và define */;
ServiceLoader<GreetingService> services =
    ServiceLoader.load(customLayer, GreetingService.class);
~~~

Layer phải chứa hoặc nhìn thấy provider module phù hợp. Tạo layer không tự động bảo đảm có provider: module finder phải tìm thấy module, configuration phải resolve module đó và descriptor phải đăng ký đúng service.

Không dùng `ServiceLoader.load(service)` một cách mặc định nếu provider nằm trong một custom layer mà thread context class loader không đại diện cho layer đó. Chọn overload phù hợp với nơi provider được nạp.

## 11. Named module và classpath provider khác nhau thế nào?

ServiceLoader hỗ trợ cả named module và classpath truyền thống, nhưng cách đăng ký provider khác nhau.

| Môi trường | Cách đăng ký provider |
| --- | --- |
| Named module trên module path | Directive `provides Service with Provider` trong `module-info.java`. |
| Classpath/unnamed module | File `META-INF/services/<fully-qualified-service-name>` chứa tên đầy đủ của provider class. |

Ví dụ file service configuration trên classpath:

~~~text
META-INF/services/com.example.greeting.api.GreetingService
~~~

Nội dung:

~~~text
com.example.greeting.provider.FormalGreetingService
~~~

Với modular JAR được dùng như named module, hãy khai báo `provides` trong module descriptor. Không nên dựa vào file `META-INF/services` thay cho descriptor của named provider module.

Consumer trên classpath không có `module-info.java`, vì vậy không khai báo `uses`. Consumer là named module thì phải khai báo `uses` cho service type mà nó dùng.

## 12. Kiểm tra module resolution khi provider không xuất hiện

Nếu chương trình không tìm thấy provider, hãy kiểm tra theo từng lớp.

### Kiểm tra module descriptor

Xem descriptor của consumer:

~~~bash
java --module-path mods --describe-module com.example.greeting.app
~~~

Xác nhận module app có `uses com.example.greeting.api.GreetingService`.

Xem descriptor của provider:

~~~bash
java --module-path mods --describe-module com.example.greeting.provider
~~~

Xác nhận provider có `provides` đúng service type và implementation class đúng package/name.

### Kiểm tra module có observable không

~~~bash
java --module-path mods --list-modules
~~~

Tên `com.example.greeting.provider` cần xuất hiện trong tập module observable. Nếu không có, kiểm tra đường dẫn module path, cấu trúc modular JAR/exploded module và module name trong descriptor.

### Xem graph được resolve khi khởi chạy

~~~bash
java --show-module-resolution --module-path mods --module com.example.greeting.app/com.example.greeting.app.Main
~~~

Output giúp quan sát root module, dependency và thông tin bind provider trong quá trình launcher resolution. Nếu provider không được đưa vào graph, kiểm tra `uses`, `provides`, module finder và phạm vi module path.

### Phân biệt provider không được tìm thấy với lỗi khởi tạo

Nếu provider đã được khám phá nhưng constructor hoặc provider method lỗi, vấn đề không còn là module path đơn thuần. ServiceLoader có thể ném `ServiceConfigurationError` khi cấu hình provider sai, class không thể nạp hoặc instance không thể được tạo.

Kiểm tra exception và nguyên nhân gốc, bao gồm constructor, dependency runtime, quyền truy cập module và class loader. Đừng chỉ bắt mọi lỗi rồi trả về danh sách rỗng, vì như vậy sẽ che giấu lỗi cấu hình.

## 13. Những lỗi thường gặp

**Consumer thiếu uses**

Một named module gọi ServiceLoader nhưng không khai báo `uses` cho service type. Thêm directive vào `module-info.java` của consumer rồi biên dịch lại.

**Provider thiếu provides**

Provider class có implement interface nhưng module descriptor không đăng ký nó. Thêm `provides Service with Provider` vào descriptor của provider module.

**Provider không nằm trên module path**

Launcher không thể tìm module provider nếu module path không chứa artifact phù hợp. Bổ sung đúng thư mục hoặc modular JAR vào `--module-path`.

**Sai service type**

Consumer dùng một interface nhưng provider đăng ký một interface khác, dù tên class implementation có vẻ đúng. Kiểm tra fully qualified name của service type ở cả hai descriptor.

**Provider class không tạo được instance**

Kiểm tra constructor public không tham số hoặc provider method, dependency của implementation và exception gốc. Đây là lỗi khởi tạo provider chứ không nhất thiết là lỗi resolution.

**Dùng sai loader hoặc layer**

Provider được nạp trong custom ModuleLayer nhưng code lại tìm qua context class loader của layer khác. Dùng `ServiceLoader.load(layer, Service.class)` với đúng layer.

**Package implementation không export**

Thông thường không cần export package chứa provider class chỉ để ServiceLoader phát hiện provider được khai báo bằng `provides`. Chỉ export package nếu module khác cần truy cập API public trong package đó.

## 14. Ghi nhớ

- API module export service interface.
- Consumer module khai báo `uses ServiceType;`.
- Provider module khai báo `provides ServiceType with ProviderClass;` và đọc module API bằng `requires`.
- Biên dịch source tree modular bằng `javac --module-source-path`; chạy bằng `java --module-path` và `--module`.
- Provider phải observable và được resolve vào module graph để ServiceLoader tìm thấy.
- `ServiceLoader.load(Service.class)` phù hợp với môi trường loader hiện tại; `ServiceLoader.load(layer, Service.class)` dùng khi provider nằm trong module layer cụ thể.
- Named module đăng ký provider bằng descriptor; classpath provider dùng `META-INF/services`.
- `--list-modules`, `--describe-module` và `--show-module-resolution` giúp kiểm tra khả năng quan sát, descriptor và graph được resolve.

Hãy giữ consumer phụ thuộc vào service contract, để provider có thể được thay đổi hoặc bổ sung mà không làm ứng dụng gắn cứng với implementation cụ thể.
