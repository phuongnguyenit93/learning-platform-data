# Đăng ký service provider bằng uses và provides

## 1. Mục tiêu

Java Platform Module System (JPMS) có cơ chế service để một module sử dụng một contract mà không cần phụ thuộc trực tiếp vào từng implementation. Consumer khai báo nhu cầu bằng **uses**; module cung cấp implementation đăng ký bằng **provides ... with ...**. API module định nghĩa service type dùng chung.

Mẫu thiết kế này thường được dùng khi một ứng dụng có thể thay đổi implementation theo môi trường hoặc cần nhiều provider cùng triển khai một service, ví dụ:

- Gửi thông báo qua SMTP, SMS hoặc dịch vụ bên ngoài.
- Đọc file JSON, XML hoặc CSV.
- Lưu dữ liệu bằng nhiều loại storage.
- Tích hợp các payment gateway khác nhau.
- Mở rộng ứng dụng bằng plugin đáng tin cậy.

Sau bài này, bạn có thể tạo ba module API, consumer và provider; viết module descriptor cho từng vai trò; chạy ServiceLoader để tìm provider; đưa provider vào module graph; và xử lý trường hợp không có hoặc có nhiều provider.

## 2. Mô hình ba module

Ví dụ sử dụng service gửi lời chào:

~~~text
com.acme.greeting.api
    com.acme.greeting
        GreetingService
        GreetingRequest

com.acme.greeting.app
    com.acme.greeting.app
        Main

com.acme.greeting.provider
    com.acme.greeting.provider.internal
        DefaultGreetingService
~~~

Ba module có trách nhiệm riêng:

| Module | Trách nhiệm | Dependency |
|---|---|---|
| com.acme.greeting.api | Định nghĩa service contract | Không phụ thuộc consumer/provider |
| com.acme.greeting.app | Sử dụng service qua ServiceLoader | requires API, uses service |
| com.acme.greeting.provider | Cung cấp implementation | requires API, provides service |

Quan hệ dependency:

~~~text
             com.acme.greeting.api
                /             \
               /               \
       consumer app        provider module
          uses               provides
~~~

Consumer và provider cùng phụ thuộc vào API module. Consumer không cần biết class implementation cụ thể. Provider không cần phụ thuộc ngược vào consumer.

## 3. Tạo service API module

Tạo cấu trúc:

~~~text
src/
  com.acme.greeting.api/
    module-info.java
    com/
      acme/
        greeting/
          GreetingService.java
          GreetingRequest.java
~~~

Module descriptor:

~~~java
module com.acme.greeting.api {
    exports com.acme.greeting;
}
~~~

Service interface:

~~~java
package com.acme.greeting;

public interface GreetingService {
    String providerId();

    String greet(GreetingRequest request);
}
~~~

Request type:

~~~java
package com.acme.greeting;

public record GreetingRequest(String name) {
}
~~~

Package chứa service interface và request type phải được export để consumer và provider có thể tham chiếu các type này. Chỉ export package contract cần công khai; không đưa implementation class vào API module.

### Thiết kế service contract

Contract cần thể hiện nghiệp vụ mà consumer muốn thực hiện, không để lộ cách provider thực hiện:

- Dùng tên trung lập như GreetingService, PaymentGateway hoặc DocumentReader.
- Định nghĩa request/response type thuộc API module.
- Không trả về class riêng của thư viện SMTP, database driver hoặc SDK provider.
- Nêu rõ lỗi nghiệp vụ, timeout và semantics đồng bộ/bất đồng bộ khi cần.
- Giữ interface nhỏ để provider có thể triển khai mà không phải phụ thuộc vào framework của consumer.

Ví dụ, nếu service interface trả về SmtpMessage thì consumer đã phụ thuộc vào chi tiết SMTP. Hãy chuyển dữ liệu chung cần trao đổi vào API module.

## 4. Consumer đăng ký nhu cầu bằng uses

Tạo source:

~~~text
src/
  com.acme.greeting.app/
    module-info.java
    com/
      acme/
        greeting/
          app/
            Main.java
~~~

Module descriptor:

~~~java
module com.acme.greeting.app {
    requires com.acme.greeting.api;

    uses com.acme.greeting.GreetingService;
}
~~~

Hai directive có mục đích khác nhau:

- **requires** tạo readability tới API module để consumer có thể tham chiếu GreetingService và GreetingRequest.
- **uses** khai báo consumer sử dụng service type. Đây là service-use declaration mà module system dùng khi phân giải provider và ServiceLoader tìm implementation.

Một named module gọi ServiceLoader cho service type phải khai báo uses tương ứng trong module descriptor của module gọi. Thiếu directive này có thể dẫn đến ServiceConfigurationError khi ServiceLoader thực hiện việc tìm provider.

Code consumer:

~~~java
package com.acme.greeting.app;

import com.acme.greeting.GreetingRequest;
import com.acme.greeting.GreetingService;

import java.util.ServiceLoader;

public final class Main {

    public static void main(String[] args) {
        ServiceLoader<GreetingService> loader =
                ServiceLoader.load(GreetingService.class);

        GreetingService service = loader.findFirst()
                .orElseThrow(() -> new IllegalStateException(
                        "No GreetingService provider is available"));

        System.out.println(
                service.greet(new GreetingRequest("Lan")));
    }
}
~~~

**ServiceLoader.load(GreetingService.class)** tạo ServiceLoader cho service type. **findFirst()** trả về Optional chứa provider đầu tiên tìm thấy; nếu không có provider thì Optional rỗng. Ví dụ trên chuyển trường hợp không có provider thành lỗi khởi chạy có thông báo rõ.

Có thể duyệt tất cả provider:

~~~java
for (GreetingService service :
        ServiceLoader.load(GreetingService.class)) {
    System.out.println(service.providerId());
}
~~~

Consumer chỉ biết GreetingService. Nó không import DefaultGreetingService và không cần biết package nội bộ của provider.

### uses phải nằm ở module thực sự gọi ServiceLoader

Nếu một helper module chứa đoạn code gọi ServiceLoader, chính module đó cần khai báo uses cho service type. Việc module ứng dụng khác khai báo uses không tự động thay thế khai báo của module đang thực hiện lời gọi.

Với code chạy trên classpath trong unnamed module, không có module-info.java để khai báo uses. Quy tắc uses ở đây áp dụng cho named module.

## 5. Provider đăng ký implementation bằng provides

Tạo source:

~~~text
src/
  com.acme.greeting.provider/
    module-info.java
    com/
      acme/
        greeting/
          provider/
            internal/
              DefaultGreetingService.java
~~~

Module descriptor:

~~~java
module com.acme.greeting.provider {
    requires com.acme.greeting.api;

    provides com.acme.greeting.GreetingService
        with com.acme.greeting.provider.internal.DefaultGreetingService;
}
~~~

Implementation:

~~~java
package com.acme.greeting.provider.internal;

import com.acme.greeting.GreetingRequest;
import com.acme.greeting.GreetingService;

public final class DefaultGreetingService
        implements GreetingService {

    public DefaultGreetingService() {
    }

    @Override
    public String providerId() {
        return "default";
    }

    @Override
    public String greet(GreetingRequest request) {
        return "Hello, " + request.name() + "!";
    }
}
~~~

Với kiểu provider class dùng constructor, provider phải là public và có public no-argument constructor để ServiceLoader tạo instance. Class phải triển khai service type được nêu trong provides.

### Không cần export package implementation

Package com.acme.greeting.provider.internal không cần export chỉ để ServiceLoader tìm và khởi tạo provider:

~~~java
module com.acme.greeting.provider {
    requires com.acme.greeting.api;

    provides com.acme.greeting.GreetingService
        with com.acme.greeting.provider.internal.DefaultGreetingService;
}
~~~

Không cần thêm:

~~~java
exports com.acme.greeting.provider.internal;
~~~

Việc đăng ký provider trong module descriptor cho phép service mechanism truy cập provider theo quy tắc riêng của JPMS. Giữ package implementation không export giúp tránh biến class nội bộ thành API mà module khác có thể phụ thuộc trực tiếp.

## 6. Provider method thay cho constructor

Một named module có thể đăng ký provider class có public static method tên **provider** trả về service type. Cách này phù hợp khi cần factory hoặc khởi tạo implementation qua cấu hình.

Ví dụ provider class:

~~~java
package com.acme.greeting.provider.internal;

import com.acme.greeting.GreetingService;

public final class GreetingServiceFactory {

    private GreetingServiceFactory() {
    }

    public static GreetingService provider() {
        return new DefaultGreetingService(loadPrefix());
    }

    private static String loadPrefix() {
        return "Hello";
    }
}
~~~

Module descriptor:

~~~java
module com.acme.greeting.provider {
    requires com.acme.greeting.api;

    provides com.acme.greeting.GreetingService
        with com.acme.greeting.provider.internal.GreetingServiceFactory;
}
~~~

Trong trường hợp provider method, class được nêu trong provides không nhất thiết phải trực tiếp implement service interface. Nó phải là provider class hợp lệ và có public static no-argument method tên provider với kiểu trả về assignable to service type.

Phân biệt hai hình thức:

| Hình thức | Provider class | Cách tạo service |
|---|---|---|
| Constructor | Public class triển khai service, có public no-arg constructor | ServiceLoader tạo instance provider |
| Provider method | Public class có public static provider() trả về service type | ServiceLoader gọi factory method |

Chọn một hình thức phù hợp với cách khởi tạo. Không khai báo đồng thời các cơ chế mâu thuẫn cho cùng provider.

## 7. Biên dịch ba module

Với cấu trúc source ở trên, có thể biên dịch nhiều module trong một javac invocation:

~~~text
javac
  --module-source-path src
  -d mods
  -m com.acme.greeting.api,com.acme.greeting.app,com.acme.greeting.provider
~~~

Sau khi biên dịch, thư mục output có cấu trúc tương tự:

~~~text
mods/
  com.acme.greeting.api/
    module-info.class
    com/acme/greeting/
      GreetingService.class
      GreetingRequest.class
  com.acme.greeting.app/
    module-info.class
    com/acme/greeting/app/
      Main.class
  com.acme.greeting.provider/
    module-info.class
    com/acme/greeting/provider/internal/
      DefaultGreetingService.class
~~~

Ý nghĩa các tùy chọn:

- **--module-source-path src**: xác định nơi chứa source hierarchy của các module.
- **-d mods**: đặt class output.
- **-m**: liệt kê các module cần biên dịch trong invocation.

Nếu dùng build tool, cấu hình tương ứng cần bảo đảm ba module có dependency đúng và provider được đưa vào runtime graph. Không đặt provider implementation vào source tree của consumer chỉ để ServiceLoader tìm thấy nó.

## 8. Đưa provider vào module graph khi chạy

Đặt provider JAR hoặc module đã compile trên module path là chưa đủ trong mọi cấu hình. Provider phải được resolve vào module layer mà ServiceLoader tìm kiếm.

Có thể thêm provider module làm root module tường minh khi khởi chạy:

~~~text
java
  --module-path mods
  --add-modules com.acme.greeting.provider
  --module com.acme.greeting.app/com.acme.greeting.app.Main
~~~

Ở đây:

- Module chính là com.acme.greeting.app.
- Provider module được thêm vào graph qua --add-modules.
- API module được resolve do cả consumer và provider đều requires nó.
- ServiceLoader trong consumer có thể tìm provider đã được resolve trong cùng layer.

Nếu provider không có trong module layer đang tìm kiếm, ServiceLoader không thể phát hiện nó chỉ vì file JAR nằm ở một thư mục nào đó trên máy.

### Service binding và resolveAndBind

Module system còn có cơ chế service binding khi giải quyết module configuration. API **Configuration.resolveAndBind(...)** thực hiện resolution kết hợp việc tìm provider cho service mà các module đã resolve sử dụng.

Trong quá trình binding, provider module có thể được thêm vào graph; dependencies của provider cũng được resolve. Provider mới có thể sử dụng service khác, khiến quá trình tiếp tục bổ sung provider phù hợp.

Khi ứng dụng tự tạo ModuleLayer, hãy cân nhắc resolveAndBind nếu mục tiêu là tự động đưa provider của các service được sử dụng vào configuration. Nếu muốn kiểm soát chặt danh sách implementation, có thể thêm provider module làm root tường minh qua configuration.

Với custom runtime image, jlink có tùy chọn **--bind-services** để yêu cầu service binding khi tạo image. Nếu không bật tùy chọn này, hãy thêm provider cần thiết bằng --add-modules hoặc bảo đảm chúng được yêu cầu theo dependency graph.

## 9. Nhiều provider cho cùng service

Một module khác có thể cung cấp cùng GreetingService:

~~~java
module com.acme.greeting.formal {
    requires com.acme.greeting.api;

    provides com.acme.greeting.GreetingService
        with com.acme.greeting.formal.internal.FormalGreetingService;
}
~~~

Nếu cả hai provider đều được resolve trong module layer, ServiceLoader có thể phát hiện cả hai:

~~~java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

for (GreetingService service : loader) {
    System.out.println(service.providerId());
}
~~~

Không dùng thứ tự tìm thấy provider như một quy tắc ưu tiên nghiệp vụ. Thứ tự provider không phải contract lựa chọn ổn định cho ứng dụng.

Nếu cần chọn provider theo cấu hình:

~~~java
String configuredId = "formal";

GreetingService selected = ServiceLoader
        .load(GreetingService.class)
        .stream()
        .map(ServiceLoader.Provider::get)
        .filter(service -> service.providerId().equals(configuredId))
        .findFirst()
        .orElseThrow(() -> new IllegalStateException(
                "Configured provider is unavailable: " + configuredId));
~~~

Trong hệ thống thực tế, configuredId nên đến từ cấu hình đã được kiểm soát. Nếu provider không tồn tại, báo lỗi rõ ràng hoặc áp dụng fallback đã được thiết kế. Không âm thầm chọn implementation bất kỳ.

Nếu ứng dụng yêu cầu đúng một provider, hãy đếm và xác thực số provider tìm được. Nếu nhiều provider là hợp lệ, định nghĩa tiêu chí chọn rõ ràng theo capability, loại request hoặc cấu hình triển khai.

## 10. ServiceLoader với ModuleLayer riêng

Ứng dụng plugin có thể tạo module layer riêng để nạp provider độc lập với layer khởi động:

~~~java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(pluginLayer, GreetingService.class);
~~~

Overload nhận ModuleLayer giới hạn việc tìm kiếm theo layer được chọn và parent layers của nó theo hợp đồng ServiceLoader.

Khi tạo layer riêng, cần chú ý:

- Service API phải được chia sẻ đúng giữa consumer và provider.
- Provider module phải có mặt trong Configuration dùng để tạo layer.
- Module consumer phải khai báo uses nếu code trong named module đó gọi ServiceLoader.
- Không vô tình tạo hai bản service API độc lập trong hai layer nếu cần trao đổi cùng một service type.
- Quản lý lifecycle của layer và tài nguyên provider khi plugin được dỡ hoặc thay thế.

Không phải ứng dụng nào cũng cần ModuleLayer riêng. Với một ứng dụng modular đơn giản, module layer mặc định thường đủ.

## 11. Provider trên classpath và named module

Có hai cách đăng ký provider phổ biến:

### Named module

Dùng module-info.java:

~~~java
provides com.acme.greeting.GreetingService
    with com.acme.greeting.provider.internal.DefaultGreetingService;
~~~

Đây là cách đăng ký phù hợp với provider nằm trong named module.

### Classpath

Provider trên classpath thường dùng file service configuration:

~~~text
META-INF/services/com.acme.greeting.GreetingService
~~~

Nội dung file là tên đầy đủ của provider class:

~~~text
com.acme.greeting.provider.internal.DefaultGreetingService
~~~

ServiceLoader hỗ trợ cả hai hình thức, nhưng cách đăng ký và quy tắc module access khác nhau. Đừng tạo file META-INF/services để thay thế module descriptor cho named module khi mục tiêu là khai báo provider theo JPMS.

## 12. Xử lý lỗi và lifecycle

### Không tìm thấy provider

ServiceLoader không bắt buộc phải có provider. Khi service là tùy chọn, consumer có thể kiểm tra Optional và dùng fallback:

~~~java
Optional<GreetingService> provider =
        ServiceLoader.load(GreetingService.class).findFirst();

if (provider.isEmpty()) {
    // Chọn hành vi fallback đã được thiết kế.
}
~~~

Nếu service là bắt buộc, dừng khởi động hoặc trả lỗi có ý nghĩa. Không để lỗi chỉ xuất hiện muộn ở một request quan trọng.

### Provider không hợp lệ hoặc khởi tạo thất bại

ServiceLoader có thể ném **ServiceConfigurationError** nếu provider configuration sai, provider không hợp lệ hoặc quá trình khởi tạo thất bại.

Hãy ghi log đủ thông tin để xác định service type và provider gây lỗi, nhưng không ghi secrets hoặc dữ liệu nhạy cảm từ cấu hình.

### Provider mở tài nguyên

Provider có thể mở connection, thread hoặc client. ServiceLoader không phải dependency injection container đầy đủ và không tự quản lý vòng đời tài nguyên của provider.

Nếu service cần shutdown hoặc lifecycle phức tạp, thiết kế API quản lý lifecycle rõ ràng hoặc để application container quản lý provider. Xác định ai khởi tạo, ai đóng và provider có thread-safe hay không.

### ServiceLoader và concurrency

Không giả định một ServiceLoader instance có thể được nhiều thread sử dụng đồng thời mà không đồng bộ. Tài liệu API không cam kết ServiceLoader thread-safe. Có thể tạo instance riêng theo phạm vi sử dụng hoặc đồng bộ truy cập nếu cần chia sẻ.

## 13. Lỗi thường gặp

### Quên requires API module

Consumer hoặc provider không đọc được service interface. Thêm requires tới API module trong descriptor tương ứng.

### Quên exports package API

Package chứa service type không được export nên module khác không thể tham chiếu contract. Export đúng package API.

### Quên uses

Named module gọi ServiceLoader nhưng không khai báo uses cho service type. Thêm uses vào module chứa lời gọi.

### Quên provides

Provider class có mặt nhưng provider module không đăng ký service trong descriptor. Thêm provides ... with ....

### Provider class không hợp lệ

Với constructor-based provider, class phải public, triển khai service type và có public no-argument constructor. Nếu cần factory, dùng provider method hợp lệ.

### Package implementation bị export thừa

ServiceLoader không yêu cầu export package implementation chỉ để phát hiện provider. Giữ package nội bộ không export nếu không có API khác cần truy cập.

### Provider module không được resolve

Module path có provider JAR nhưng module layer không chứa provider. Thêm provider vào root modules hoặc dùng resolveAndBind khi muốn service binding.

### Consumer phụ thuộc implementation

Consumer khai báo requires tới provider cụ thể và gọi class trực tiếp. Chuyển dependency về API module và dùng uses/ServiceLoader.

### Chọn provider theo thứ tự

Không coi provider đầu tiên là provider mặc định có ý nghĩa nghiệp vụ. Chọn theo cấu hình hoặc capability đã định nghĩa.

## 14. Quy trình triển khai

1. Tạo API module chứa service interface và các request/response type.
2. Export package chứa contract.
3. Tạo consumer module, khai báo requires API và uses service type.
4. Viết consumer gọi ServiceLoader và xử lý trường hợp không có provider.
5. Tạo provider module, khai báo requires API và provides service type with implementation.
6. Đặt implementation trong package nội bộ; chỉ export nếu có nhu cầu API độc lập.
7. Kiểm tra provider class có constructor hợp lệ hoặc provider method đúng contract.
8. Compile các module và kiểm tra module descriptor trong output.
9. Đưa provider vào module graph hoặc module layer runtime.
10. Chạy thử ServiceLoader và xác nhận provider được phát hiện.
11. Thử trường hợp không provider, nhiều provider và provider khởi tạo lỗi.
12. Chạy integration test trên cấu hình module path hoặc runtime image gần với production.

## 15. Checklist đăng ký service provider

- API module có service interface được export chưa?
- Consumer có requires API module và uses đúng service type chưa?
- Provider có requires API module và provides đúng service type chưa?
- Provider class có public no-arg constructor hoặc provider method hợp lệ chưa?
- Implementation package có thể giữ không export không?
- Consumer có tránh requires trực tiếp provider implementation không?
- Provider module đã được resolve vào layer mà ServiceLoader tìm kiếm chưa?
- Nhiều provider có được chọn theo policy tường minh không?
- Trường hợp không provider hoặc provider lỗi đã có hành vi rõ ràng chưa?
- Resource và lifecycle của provider đã được quản lý chưa?
- Integration test có chạy trên module path hoặc runtime image thực tế không?

**Ghi nhớ:** API module định nghĩa service contract; consumer khai báo **requires + uses**; provider khai báo **requires + provides**. Đưa provider vào đúng module layer để ServiceLoader phát hiện nó. Giữ consumer phụ thuộc vào contract và giữ implementation trong package nội bộ để có thể thay provider mà không làm consumer phụ thuộc vào chi tiết triển khai.

## Tài liệu tham khảo

- Oracle Java SE 21 API — ServiceLoader: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html
- Java Language Specification, Java SE 21 — Service Providers and Module Declarations: https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html
- Oracle Java SE 21 — The java Command, module selection and module path: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle Java SE 21 API — Configuration.resolveAndBind: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html
- OpenJDK JEP 261 — Module System: https://openjdk.org/jeps/261
