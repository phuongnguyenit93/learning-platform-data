# Chỉ thị uses trong Java Module System

## 1. Vai trò của uses trong JPMS

Trong Java Platform Module System (JPMS), chỉ thị **uses** khai báo rằng một module cần sử dụng một service (dịch vụ) có kiểu được xác định trước. Service thường là một interface hoặc abstract class đóng vai trò hợp đồng; các module khác có thể cung cấp implementation mà module tiêu thụ không cần biết trước tên module triển khai.

Cơ chế này hỗ trợ kiến trúc **Service Provider Interface (SPI)**:

- Module API định nghĩa service type, ví dụ interface Greeter.
- Module consumer gọi service thông qua API và khai báo uses trong module descriptor.
- Một hoặc nhiều module provider đăng ký implementation bằng chỉ thị provides.
- ServiceLoader tìm và tạo provider phù hợp tại runtime.

Ví dụ, ứng dụng cần gửi thông báo nhưng không muốn phụ thuộc trực tiếp vào implementation SMTP, console hay một dịch vụ bên ngoài. Ứng dụng chỉ làm việc với interface NotificationSender. Các module provider có thể cung cấp ConsoleNotificationSender hoặc EmailNotificationSender theo cấu hình triển khai.

uses là một phần của module descriptor, file module-info.java. Nó mô tả nhu cầu service ở cấp module, giúp module resolver tham gia tìm provider khi xây dựng module graph.

## 2. Cú pháp của chỉ thị uses

Cú pháp:

~~~java
module com.example.app {
    requires com.example.greeter.api;
    uses com.example.greeter.Greeter;
}
~~~

Trong đó:

- uses là từ khóa của module declaration.
- Tên theo sau là service type đầy đủ package (fully qualified name).
- Service type thường là public interface hoặc abstract class được module API export.
- Một module có thể khai báo nhiều uses, mỗi chỉ thị cho một service type.
- Một service type có thể có nhiều provider.

Ví dụ module tiêu thụ nhiều service:

~~~java
module com.example.application {
    requires com.example.payment.api;
    requires com.example.notification.api;

    uses com.example.payment.PaymentGateway;
    uses com.example.notification.NotificationSender;
}
~~~

Chỉ thị uses không tạo object, không gọi method và không tự nạp file cấu hình. Nó khai báo service mà module muốn tìm ở runtime. Việc tìm kiếm và sử dụng instance thường được thực hiện bằng java.util.ServiceLoader.

Tên service type phải xác định được trong module đang khai báo uses. Nếu service interface nằm trong module khác, consumer cần quan hệ readability thích hợp, thường được khai báo bằng requires đối với module API.

## 3. Phân biệt uses, requires và provides

Ba chỉ thị thường xuất hiện cùng nhau nhưng có nhiệm vụ khác nhau:

| Chỉ thị | Vai trò | Thường xuất hiện ở |
|---|---|---|
| requires | Khai báo module dependency và khả năng đọc module khác. | Consumer và provider cần dùng service API. |
| uses | Khai báo module tiêu thụ một service type. | Module consumer. |
| provides ... with ... | Đăng ký implementation cho một service type. | Module provider. |

Ví dụ:

~~~java
// module-info.java của API
module com.example.greeter.api {
    exports com.example.greeter;
}
~~~

~~~java
// module-info.java của consumer
module com.example.app {
    requires com.example.greeter.api;
    uses com.example.greeter.Greeter;
}
~~~

~~~java
// module-info.java của provider
module com.example.greeter.english {
    requires com.example.greeter.api;

    provides com.example.greeter.Greeter
        with com.example.greeter.english.EnglishGreeter;
}
~~~

Consumer cần requires API để biên dịch và gọi Greeter. Consumer khai báo uses để yêu cầu service. Provider cũng cần đọc API để implementation có thể triển khai interface, rồi dùng provides để đăng ký implementation.

Consumer không cần requires module provider chỉ để dùng service. Đây là điểm tạo ra sự tách rời giữa ứng dụng và implementation. Module resolver có thể tìm provider thông qua cơ chế service binding trong quá trình giải quyết module graph.

## 4. Service type và ranh giới module

Service type là hợp đồng chung giữa consumer và provider. Nên đặt interface hoặc abstract class trong một module API nhỏ, ổn định và export đúng package cần thiết.

Ví dụ:

~~~java
package com.example.greeter;

public interface Greeter {
    String greet(String name);
}
~~~

Module API:

~~~java
module com.example.greeter.api {
    exports com.example.greeter;
}
~~~

Package chứa Greeter phải được export để các module consumer và provider có thể truy cập kiểu public này. Có thể dùng qualified exports nếu tổ chức muốn giới hạn module nào được đọc package API.

Implementation thường nằm trong package riêng của provider:

~~~java
package com.example.greeter.english;

import com.example.greeter.Greeter;

public final class EnglishGreeter implements Greeter {
    public EnglishGreeter() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Module provider:

~~~java
module com.example.greeter.english {
    requires com.example.greeter.api;

    provides com.example.greeter.Greeter
        with com.example.greeter.english.EnglishGreeter;
}
~~~

Package chứa EnglishGreeter không cần export chỉ để ServiceLoader tạo provider. Module descriptor đã đăng ký provider; việc giữ package implementation ở trạng thái encapsulated giúp consumer phụ thuộc vào service contract thay vì class triển khai cụ thể.

Không nên đặt implementation class trong module API. Nếu làm vậy, consumer sẽ phải mang theo implementation hoặc API module sẽ trở nên gắn chặt với một lựa chọn triển khai.

## 5. ServiceLoader tìm provider như thế nào?

java.util.ServiceLoader là API tiêu chuẩn để tải service provider. Với module có tên, lời gọi ServiceLoader.load(ServiceType.class) sử dụng module context của caller và module layer tương ứng. Consumer module phải khai báo uses cho service type đang tải.

Cách dùng cơ bản:

~~~java
ServiceLoader<Greeter> loader =
        ServiceLoader.load(Greeter.class);

for (Greeter greeter : loader) {
    System.out.println(greeter.greet("Java"));
}
~~~

ServiceLoader cung cấp các provider theo cơ chế lazy loading. Provider thường chỉ được nạp và khởi tạo khi iterator hoặc stream được duyệt. Vì vậy, tạo ServiceLoader không có nghĩa mọi provider đã được tạo ngay lập tức.

Với named modules trên module path, module descriptor của provider dùng provides để đăng ký implementation. Module resolver thực hiện service binding: khi một module đã được resolve khai báo uses, các module provider phù hợp có thể được thêm vào module graph nếu chúng quan sát được trên module path.

Nhờ đó, ứng dụng có thể chỉ chọn module ứng dụng làm root module khi khởi chạy. Provider được phát hiện thông qua service binding mà consumer không cần ghi tên provider trong requires.

## 6. Ví dụ hoàn chỉnh với ba module Java 17

Ví dụ gồm ba module:

- com.example.greeter.api: định nghĩa interface Greeter.
- com.example.greeter.english: cung cấp EnglishGreeter.
- com.example.app: tiêu thụ Greeter bằng uses và ServiceLoader.

Cấu trúc thư mục:

~~~text
service-demo/
└── src/
    ├── com.example.greeter.api/
    │   ├── module-info.java
    │   └── com/example/greeter/Greeter.java
    ├── com.example.greeter.english/
    │   ├── module-info.java
    │   └── com/example/greeter/english/EnglishGreeter.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
~~~

### Module API

File src/com.example.greeter.api/module-info.java:

~~~java
module com.example.greeter.api {
    exports com.example.greeter;
}
~~~

File src/com.example.greeter.api/com/example/greeter/Greeter.java:

~~~java
package com.example.greeter;

public interface Greeter {
    String greet(String name);
}
~~~

### Module provider

File src/com.example.greeter.english/module-info.java:

~~~java
module com.example.greeter.english {
    requires com.example.greeter.api;

    provides com.example.greeter.Greeter
        with com.example.greeter.english.EnglishGreeter;
}
~~~

File src/com.example.greeter.english/com/example/greeter/english/EnglishGreeter.java:

~~~java
package com.example.greeter.english;

import com.example.greeter.Greeter;

public final class EnglishGreeter implements Greeter {
    public EnglishGreeter() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

### Module consumer

File src/com.example.app/module-info.java:

~~~java
module com.example.app {
    requires com.example.greeter.api;
    uses com.example.greeter.Greeter;
}
~~~

File src/com.example.app/com/example/app/Main.java:

~~~java
package com.example.app;

import com.example.greeter.Greeter;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<Greeter> loader =
                ServiceLoader.load(Greeter.class);

        for (Greeter greeter : loader) {
            System.out.println(greeter.greet("Java"));
            return;
        }

        throw new IllegalStateException("No Greeter provider found");
    }
}
~~~

### Biên dịch và chạy

Đứng tại thư mục gốc service-demo, dùng JDK 17 trở lên:

~~~bash
javac --release 17 --module-source-path src -d mods -m com.example.greeter.api,com.example.greeter.english,com.example.app
~~~

Compiler tìm source của từng module theo tên thư mục dưới src và ghi các module đã biên dịch vào mods.

Chạy ứng dụng:

~~~bash
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Stdout:

~~~text
Hello, Java!
~~~

Ứng dụng chỉ khai báo requires com.example.greeter.api và uses Greeter. Nó không khai báo requires com.example.greeter.english. Provider được tìm thông qua service binding khi launcher resolve module graph. Nếu provider module không nằm trên module path hoặc không được resolve, ServiceLoader sẽ không tìm thấy provider tương ứng.

Để quan sát module resolution, có thể chạy:

~~~bash
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
~~~

Output chẩn đoán có thể khác nhau theo JDK và môi trường, nhưng có thể dùng để kiểm tra các module được resolve, gồm module provider được thêm nhờ service binding.

## 7. Một service có thể có nhiều provider

Một service type có thể được cung cấp bởi nhiều module:

~~~java
module com.example.greeter.french {
    requires com.example.greeter.api;

    provides com.example.greeter.Greeter
        with com.example.greeter.french.FrenchGreeter;
}
~~~

Nếu cả provider tiếng Anh và tiếng Pháp đều được quan sát và resolve, ServiceLoader có thể trả về nhiều implementation. Thứ tự provider không nên được xem là một quy tắc ưu tiên ổn định cho nghiệp vụ.

Nếu ứng dụng cần chọn một implementation cụ thể, hãy định nghĩa chính sách lựa chọn rõ ràng, chẳng hạn:

- Đọc tên provider mong muốn từ cấu hình.
- Duyệt provider và kiểm tra metadata hoặc thuộc tính do ứng dụng định nghĩa.
- Chọn theo capability mà provider công bố.
- Báo lỗi rõ ràng nếu không có provider phù hợp hoặc có nhiều provider không thể phân biệt.

Không nên dùng thứ tự trả về của ServiceLoader để ngầm quyết định provider chính. Nếu thứ tự có ý nghĩa, hãy mô hình hóa thứ tự đó trong cấu hình hoặc trong API của ứng dụng.

## 8. Provider constructor và provider method

Cách phổ biến nhất là provider class public, triển khai service type và có public no-argument constructor. Ví dụ EnglishGreeter ở trên dùng constructor không tham số.

JPMS cũng hỗ trợ provider method: module descriptor vẫn khai báo class provider trong provides, nhưng class đó có thể cung cấp một public static method tên provider không nhận tham số và trả về service type. Cách này hữu ích khi việc tạo implementation cần factory hoặc implementation class không muốn được công bố như kiểu provider trực tiếp.

Ví dụ:

~~~java
package com.example.greeter.factory;

import com.example.greeter.Greeter;
import com.example.greeter.english.EnglishGreeter;

public class GreeterProvider {
    public static Greeter provider() {
        return new EnglishGreeter();
    }
}
~~~

Khi dùng provider method, descriptor đăng ký provider class:

~~~java
provides com.example.greeter.Greeter
    with com.example.greeter.factory.GreeterProvider;
~~~

Provider method phải là public, static, không có tham số và trả về service type hoặc subtype tương thích. Hãy chọn một hình thức provider nhất quán và kiểm tra điều kiện của ServiceLoader theo JDK mục tiêu.

## 9. ServiceLoader API: iterator, stream và cache

ServiceLoader triển khai Iterable, do đó có thể dùng enhanced for hoặc iterator để lấy instance:

~~~java
for (Greeter provider : ServiceLoader.load(Greeter.class)) {
    System.out.println(provider.greet("Java"));
}
~~~

Từ Java 9, ServiceLoader có stream() trả về các Provider descriptor. Có thể xem kiểu provider trước khi yêu cầu instance:

~~~java
ServiceLoader<Greeter> loader =
        ServiceLoader.load(Greeter.class);

loader.stream()
        .map(ServiceLoader.Provider::type)
        .forEach(System.out::println);
~~~

Khi cần tạo instance từ một Provider, gọi Provider.get(). Cách stream hữu ích khi muốn lọc theo annotation, class name hoặc metadata của implementation trước khi khởi tạo.

ServiceLoader lưu cache các provider đã được nạp. Nếu môi trường có thay đổi provider và ứng dụng có lý do để nạp lại, có thể gọi reload() để xóa cache. reload() không tự cài module mới vào module layer; nó chỉ làm mới việc duyệt provider theo layer/class loader mà loader đang sử dụng.

ServiceLoader instance không được thiết kế để chia sẻ đồng thời giữa nhiều thread mà không có đồng bộ hóa phù hợp. Nếu nhiều thread cần truy cập, hãy quản lý vòng đời và việc duyệt provider rõ ràng.

Khi provider bị lỗi cấu hình, thiếu constructor phù hợp hoặc không thể khởi tạo, ServiceLoader có thể phát sinh ServiceConfigurationError trong lúc duyệt hoặc lấy provider. Hãy xử lý lỗi tại ranh giới khởi tạo ứng dụng để thông báo rõ service nào và provider nào gây vấn đề.

## 10. Service trong classpath và module path

ServiceLoader hỗ trợ cả ứng dụng classpath truyền thống và ứng dụng modular, nhưng cách đăng ký provider khác nhau.

| Môi trường | Cách đăng ký provider |
|---|---|
| Classpath / unnamed module | File META-INF/services/<tên đầy đủ của service type> trong JAR provider. |
| Named module trên module path | Chỉ thị provides trong module-info.java. |

Ví dụ file classpath provider:

~~~text
META-INF/services/com.example.greeter.Greeter
~~~

Nội dung file là tên đầy đủ của implementation class, mỗi provider một dòng:

~~~text
com.example.greeter.english.EnglishGreeter
~~~

Cơ chế file META-INF/services vẫn hữu ích cho thư viện tương thích classpath. Khi chuyển provider thành named module, nên khai báo provides trong module descriptor để JPMS hiểu service binding.

Đừng nhầm file META-INF/services với chỉ thị uses. uses nằm trong module descriptor của consumer; file META-INF/services hoặc provides nằm ở phía provider. Một bên mô tả nhu cầu, bên kia mô tả implementation được đăng ký.

Với named module consumer, phải khai báo uses cho service type mà module đó tải qua ServiceLoader. Việc có file META-INF/services trong một JAR không tự thay thế khai báo uses trong module descriptor.

## 11. Service trong custom ModuleLayer

Ứng dụng nâng cao có thể tạo module layer riêng để nạp plugin hoặc nhóm module động. Trong trường hợp đó, có thể chỉ định layer khi tải service:

~~~java
ServiceLoader<Greeter> loader =
        ServiceLoader.load(pluginLayer, Greeter.class);
~~~

pluginLayer là ModuleLayer đã được tạo từ Configuration và ClassLoader tương ứng. Module provider cần được resolve vào layer đó.

Khi tạo configuration cho plugin, cần quan tâm đến service binding. API Configuration.resolveAndBind có thể resolve thêm provider module dựa trên uses/provides trong module graph. Nếu chỉ resolve dependency thông thường mà không thực hiện service binding, provider module có thể không được thêm vào graph như mong đợi.

Việc tạo layer thường cần kiểm soát:

- Module finder và vị trí chứa plugin module.
- Parent configuration và parent layer.
- Class loader được dùng để định nghĩa module.
- Service type được chia sẻ giữa host và plugin.
- Quyền truy cập, vòng đời và cách gỡ bỏ plugin.
- Cách xử lý provider lỗi hoặc module không tương thích.

Không nên tạo một class loader/module layer mới cho mỗi lần gọi service. Hãy thiết kế vòng đời plugin rõ ràng, tránh nạp trùng module và giữ service API ổn định giữa host với provider.

## 12. Lỗi thường gặp khi dùng uses và ServiceLoader

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Module consumer không compile được service type | Thiếu requires module API hoặc package API chưa export. | Kiểm tra module dependency và exports. |
| ServiceLoader không tìm thấy provider | Provider module không có trên module path hoặc không được resolve. | Kiểm tra provides và service binding. |
| Báo module không khai báo uses | Named module gọi ServiceLoader cho service type chưa khai báo trong descriptor. | Thêm uses đúng service type vào module-info.java. |
| Provider class không hợp lệ | Thiếu public no-arg constructor hoặc provider method phù hợp. | Kiểm tra điều kiện provider class/provider method. |
| ServiceConfigurationError khi duyệt | Provider không thể nạp, khởi tạo hoặc không phù hợp service type. | Xem exception và module/provider cụ thể. |
| Consumer phải requires implementation module | Thiết kế phụ thuộc trực tiếp vào provider thay vì service. | Consumer chỉ requires API và uses service; provider dùng provides. |
| Provider package bị mở rộng không cần thiết | Nhầm rằng consumer phải truy cập implementation class. | Giữ package implementation encapsulated; chỉ export service API. |
| Không thấy provider mới sau reload | Provider module chưa được thêm vào layer hoặc module graph. | Cập nhật layer/configuration theo vòng đời plugin; reload chỉ xóa cache của ServiceLoader. |
| Classpath provider không được tìm thấy | Thiếu hoặc sai file META-INF/services. | Kiểm tra tên service file, nội dung và vị trí trong JAR. |
| Nhiều provider cho kết quả không ổn định | Ứng dụng dựa vào thứ tự duyệt provider. | Tự định nghĩa chính sách lựa chọn provider. |

Khi chẩn đoán, hãy xác định ứng dụng chạy trên classpath hay module path. Sau đó kiểm tra service type, uses, provides hoặc META-INF/services, vị trí module/JAR và module resolution. Đây là các điểm khác nhau và cần kiểm tra theo đúng môi trường chạy.

## 13. Công cụ kiểm tra module service

Có thể dùng các công cụ JDK để xem descriptor và quan hệ module.

Xem descriptor của modular JAR:

~~~bash
jar --describe-module --file mods/com.example.greeter.english.jar
~~~

Nếu đang dùng exploded module directory, có thể chỉ định module path khi kiểm tra module:

~~~bash
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
~~~

Dùng jdeps để kiểm tra phụ thuộc module và package:

~~~bash
jdeps --module-path mods --check com.example.app
~~~

Tùy cấu trúc dự án và loại artifact, cú pháp cụ thể có thể cần thêm classpath hoặc module path. Hãy đọc help của đúng JDK nếu cần điều chỉnh.

Các lệnh này hỗ trợ kiểm tra module dependency và resolution. Chúng không thay thế việc chạy test service discovery thực tế. Nên có test xác nhận provider mong đợi được tìm thấy, khởi tạo và trả kết quả đúng.

## 14. Thiết kế service API an toàn và ổn định

Service interface là hợp đồng mà consumer và provider cùng phụ thuộc. Khi thiết kế, nên chú ý:

- Giữ service API nhỏ và ổn định; chỉ công bố kiểu mà consumer thực sự cần.
- Tránh đưa class implementation vào API module.
- Quy định rõ behavior khi không có provider, có một provider hoặc nhiều provider.
- Định nghĩa cách chọn provider nếu có nhiều implementation.
- Xem xét khả năng provider được nạp lười và lỗi có thể xuất hiện khi tạo instance.
- Giữ package implementation không export nếu consumer không cần truy cập trực tiếp.
- Xác định compatibility giữa phiên bản API và provider.
- Kiểm soát nguồn module plugin; ServiceLoader không phải sandbox bảo mật.

Provider code chạy với quyền của tiến trình ứng dụng và có thể thực hiện bất kỳ hành động nào mà quyền tiến trình cho phép. Vì vậy, chỉ nạp provider từ nguồn tin cậy, kiểm soát module path và quyền truy cập file/plugin. JPMS encapsulation giúp quản lý khả năng truy cập kiểu và package; nó không tự cô lập code provider như một sandbox.

Nếu service xử lý dữ liệu nhạy cảm hoặc thao tác bên ngoài, API nên xác định rõ xác thực, timeout, xử lý lỗi, quản lý tài nguyên và quyền được cấp. Đừng coi việc provider được đăng ký trong module descriptor là bằng chứng provider an toàn.

## 15. Quy trình triển khai uses

1. Xác định service contract và đặt interface/abstract class trong module API.
2. Export package chứa service type từ module API.
3. Trong consumer, requires module API để đọc service type.
4. Khai báo uses với tên đầy đủ của service type trong module-info.java.
5. Trong từng provider, requires module API và đăng ký implementation bằng provides ... with ....
6. Đảm bảo provider có public no-argument constructor hoặc provider method đúng chuẩn.
7. Biên dịch và đặt các module vào module path.
8. Dùng ServiceLoader để tìm provider; định nghĩa chính sách khi không có hoặc có nhiều provider.
9. Kiểm tra module resolution và test hành vi trên môi trường triển khai.
10. Theo dõi tương thích API/provider và kiểm soát nguồn plugin.

## 16. Checklist khi sử dụng uses

- [ ] Service type được định nghĩa trong API module ổn định.
- [ ] Package chứa service type được export phù hợp.
- [ ] Consumer requires module API.
- [ ] Consumer khai báo uses đúng service type.
- [ ] Provider requires module API và khai báo provides đúng service type.
- [ ] Provider có public no-arg constructor hoặc public static provider method hợp lệ.
- [ ] Consumer không phụ thuộc trực tiếp vào module implementation nếu chỉ cần service contract.
- [ ] Provider module có thể được quan sát và resolve trên module path.
- [ ] Đã kiểm tra hành vi khi không có provider và khi có nhiều provider.
- [ ] Đã xử lý ServiceConfigurationError và lỗi khởi tạo provider.
- [ ] Đã kiểm tra classpath/META-INF/services nếu ứng dụng dùng cơ chế cũ.
- [ ] Đã xác định vòng đời ModuleLayer nếu dùng plugin động.
- [ ] Đã kiểm soát nguồn provider và quyền chạy của plugin.

Chỉ thị uses cho module biết service nào nó cần. Khi kết hợp requires cho API, provides cho implementation và ServiceLoader để tìm instance, ứng dụng có thể thay đổi provider mà không phải sửa dependency trực tiếp trong consumer.