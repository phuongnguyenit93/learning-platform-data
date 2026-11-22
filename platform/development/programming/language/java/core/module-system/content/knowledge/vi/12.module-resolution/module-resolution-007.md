# Service binding khi resolveAndBind

Trong JPMS, việc resolve module thường bắt đầu từ một tập root module rồi lần theo các directive **requires** để tìm dependency cần thiết. Tuy nhiên, một module có thể khai báo **uses** một service mà không khai báo **requires** trực tiếp tới module cung cấp implementation. Nếu chỉ resolve theo dependency thông thường, module provider có thể chưa được đưa vào cấu hình runtime.

**Service binding** giải quyết trường hợp này. Khi dùng **Configuration.resolveAndBind(...)**, module system resolve root modules và dependency của chúng, sau đó tìm các module provider cho service mà những module đã resolve khai báo sử dụng. Provider và dependency của provider được bổ sung vào configuration; quá trình tìm provider tiếp tục nếu provider mới lại sử dụng service khác.

Cần phân biệt ba việc: descriptor khai báo service contract, **resolveAndBind** đưa provider module vào cấu hình, và **ServiceLoader** tìm cũng như tạo instance provider khi ứng dụng cần dùng service.

## 1. Vì sao cần service binding?

Giả sử một ứng dụng báo cáo chỉ biết interface **ReportExporter**. Ứng dụng khai báo module cần service:

~~~java
module com.acme.application {
    requires com.acme.report.spi;
    uses com.acme.report.spi.ReportExporter;
}
~~~

Một module khác cung cấp implementation:

~~~java
module com.acme.csv.exporter {
    requires com.acme.report.spi;

    provides com.acme.report.spi.ReportExporter
        with com.acme.csv.CsvReportExporter;
}
~~~

Ứng dụng phụ thuộc vào module API **com.acme.report.spi**. Nó không khai báo **requires com.acme.csv.exporter**, bởi mục tiêu là có thể thay thế hoặc bổ sung provider mà không làm module ứng dụng phụ thuộc vào từng implementation.

Nếu configuration chỉ resolve root **com.acme.application** và các dependency bắt buộc của nó, module provider có thể không được đưa vào configuration. Khi đó, service contract đã có và ứng dụng đã khai báo **uses**, nhưng provider module chưa nằm trong layer được tìm kiếm.

Service binding giúp module system tìm các provider module có thể quan sát được cho service mà graph đã resolve cần dùng. Cơ chế này hữu ích với plugin, driver, serializer, exporter và các extension point khác.

## 2. Ba directive và API cần hiểu

### 2.1. uses

Directive **uses** được khai báo trong module cần tìm implementation của service:

~~~java
module com.acme.application {
    requires com.acme.report.spi;
    uses com.acme.report.spi.ReportExporter;
}
~~~

Nó cho module system biết service type nào được module tiêu thụ. Service type thường là interface hoặc abstract class nằm trong một module API ổn định.

Một named module gọi **ServiceLoader.load(...)** cho một service cần khai báo **uses** service đó trong descriptor. Nếu thiếu khai báo, việc sử dụng ServiceLoader từ module đó có thể thất bại với **ServiceConfigurationError**.

### 2.2. provides ... with ...

Module provider khai báo implementation:

~~~java
module com.acme.csv.exporter {
    requires com.acme.report.spi;

    provides com.acme.report.spi.ReportExporter
        with com.acme.csv.CsvReportExporter;
}
~~~

Directive này đăng ký provider cho service type. Module provider cần đọc module chứa service API để implementation có thể tham chiếu contract.

Package chứa provider không nhất thiết phải export cho module ứng dụng. Ứng dụng làm việc với interface service; module system và ServiceLoader xử lý provider theo metadata trong descriptor.

### 2.3. ServiceLoader

Sau khi provider module có mặt trong layer phù hợp, ứng dụng tìm provider bằng **ServiceLoader**:

~~~java
ServiceLoader<ReportExporter> exporters =
    ServiceLoader.load(ReportExporter.class);

for (ReportExporter exporter : exporters) {
    exporter.export(report);
}
~~~

Trong một ứng dụng dùng custom ModuleLayer, nên chỉ rõ layer muốn tìm provider:

~~~java
ServiceLoader<ReportExporter> exporters =
    ServiceLoader.load(pluginLayer, ReportExporter.class);
~~~

ServiceLoader cung cấp cơ chế duyệt và tạo provider instance theo cách provider được khai báo. Việc tạo instance xảy ra khi ứng dụng duyệt kết quả hoặc yêu cầu provider; **resolveAndBind** không khởi tạo provider và không gọi nghiệp vụ của nó.

## 3. resolve và resolveAndBind khác nhau thế nào?

**Configuration.resolve(...)** giải quyết các root module và dependency theo quan hệ module đã khai báo. Các module chỉ được thêm vì chúng là root hoặc dependency cần thiết trong đồ thị.

**Configuration.resolveAndBind(...)** thực hiện resolution cùng với service binding. Sau khi resolve graph ban đầu, module system tìm provider cho các service được sử dụng bởi những module trong graph. Provider module được bổ sung cùng dependency của nó. Nếu provider mới lại khai báo **uses** một service khác, service binding có thể tiếp tục tìm provider cho service đó.

| Tiêu chí | resolve(...) | resolveAndBind(...) |
|---|---|---|
| Resolve root modules | Có | Có |
| Resolve dependency qua requires | Có | Có |
| Tự bổ sung provider cho service được sử dụng | Không thực hiện bước service binding | Có |
| Bổ sung dependency của provider | Không có provider được bổ sung từ bước binding | Có, khi provider được đưa vào configuration |
| Khởi tạo provider object | Không | Không |
| Tạo ModuleLayer | Không | Không |

Service binding chỉ xét provider module có thể quan sát được từ các nguồn module finder dùng trong quá trình resolve. Một provider nằm ngoài các nguồn module được cung cấp sẽ không tự xuất hiện. Việc một JAR chỉ nằm ở classpath cũng không khiến nó trở thành provider module trong configuration named module.

Điều này giúp giữ rõ ranh giới giữa tìm module ở thời điểm resolution và nạp provider instance ở thời điểm ứng dụng sử dụng service.

## 4. Vòng lặp service binding diễn ra như thế nào?

Giả sử graph ban đầu có module ứng dụng A:

- A khai báo **uses ServiceX**.
- Provider module PX khai báo **provides ServiceX with ProviderX**.
- PX lại khai báo **uses ServiceY**.
- Provider module PY khai báo **provides ServiceY with ProviderY**.

Khi resolveAndBind chạy:

1. Resolve root A và dependency bắt buộc của A.
2. Đọc các service mà module trong graph đã resolve khai báo sử dụng.
3. Tìm provider module có thể quan sát được cho các service đó.
4. Bổ sung PX và resolve dependency của PX.
5. Vì PX sử dụng ServiceY, tiếp tục tìm provider cho ServiceY.
6. Bổ sung PY và dependency của PY.
7. Tiếp tục cho đến khi không tìm thấy provider mới cần bổ sung.

Quá trình này giúp configuration chứa cả provider gián tiếp cần thiết qua chuỗi service. Provider không được đưa vào chỉ vì nó tồn tại trên module path; nó phải cung cấp một service được module trong graph sử dụng.

Một provider có thể cung cấp nhiều service. Khi nhiều module cần cùng một service, một provider module được resolve vào configuration sẽ được dùng chung trong layer đó theo module identity của layer.

## 5. Dùng Configuration.resolveAndBind trong Java

API có thể được gọi từ configuration cha, thường là boot configuration:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

Configuration parent = ModuleLayer.boot().configuration();

ModuleFinder applicationFinder =
    ModuleFinder.of(Path.of("app-mods"));

ModuleFinder providerFinder =
    ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    parent.resolveAndBind(
        applicationFinder,
        providerFinder,
        Set.of("com.acme.application")
    );
~~~

Ý nghĩa các tham số:

- **parent** là configuration đã có, ở ví dụ này là configuration của boot layer.
- **applicationFinder** là nguồn module được tìm trước các configuration cha trong quá trình resolve.
- **providerFinder** là nguồn module được tìm sau các configuration cha.
- **Set.of("com.acme.application")** chỉ định root module cần khởi chạy.

Hai ModuleFinder cần trỏ tới đúng các module có thể quan sát trong môi trường triển khai. Tên root phải khớp với module name trong descriptor. Nếu dependency hoặc provider không tìm thấy, hoặc graph có lỗi như dependency không hợp lệ, resolution sẽ thất bại với lỗi tương ứng.

Với overload nhận danh sách parent configurations, có thể viết:

~~~java
Configuration configuration =
    Configuration.resolveAndBind(
        applicationFinder,
        java.util.List.of(ModuleLayer.boot().configuration()),
        providerFinder,
        Set.of("com.acme.application")
    );
~~~

Overload này hữu ích khi cấu hình module có nhiều parent configuration. Với trường hợp thông thường chỉ có một parent, gọi **parent.resolveAndBind(...)** dễ đọc hơn.

## 6. Tạo ModuleLayer từ configuration đã bind

**resolveAndBind** chỉ trả về **Configuration**. Muốn các module được định nghĩa tại runtime và có thể dùng ServiceLoader theo layer, ứng dụng cần tạo ModuleLayer:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.ServiceLoader;
import java.util.Set;

ModuleLayer parentLayer = ModuleLayer.boot();

ModuleFinder applicationFinder =
    ModuleFinder.of(Path.of("app-mods"));

ModuleFinder providerFinder =
    ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    parentLayer.configuration().resolveAndBind(
        applicationFinder,
        providerFinder,
        Set.of("com.acme.application")
    );

ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithOneLoader(
        configuration,
        List.of(parentLayer),
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer applicationLayer = controller.layer();

ServiceLoader<ReportExporter> exporters =
    ServiceLoader.load(applicationLayer, ReportExporter.class);

for (ReportExporter exporter : exporters) {
    exporter.export(report);
}
~~~

Đọc luồng này theo thứ tự:

1. Lấy boot layer làm layer cha.
2. Tạo finder cho module ứng dụng và finder cho module provider/plugin.
3. Resolve root module cùng dependency và service provider bằng **resolveAndBind**.
4. Định nghĩa configuration thành layer mới bằng **defineModulesWithOneLoader**.
5. Lấy layer từ controller.
6. Dùng **ServiceLoader.load(layer, serviceType)** để tìm provider trong layer đó và các layer cha liên quan.
7. Duyệt provider để tạo instance và gọi chức năng.

Trong ví dụ, service interface **ReportExporter** phải là cùng một kiểu API mà module ứng dụng và module provider cùng đọc. Thông thường module chứa service API nằm ở boot layer hoặc được chia sẻ qua layer cha. Nếu host và plugin vô tình nạp hai bản khác nhau của service API bằng các class loader khác nhau, chúng có thể có hai class identity khác nhau và không giao tiếp qua cùng một service type được.

## 7. Quan sát module đã được bind

Sau khi resolution hoàn tất, có thể xem các module trong configuration:

~~~java
configuration.modules().stream()
    .map(resolvedModule -> resolvedModule.name())
    .sorted()
    .forEach(System.out::println);
~~~

Nếu module provider có mặt trong configuration, tên của nó sẽ xuất hiện trong tập module đã resolve. Có thể xem descriptor của từng module để kiểm tra service provider:

~~~java
configuration.modules().forEach(resolvedModule -> {
    System.out.println("Module: " + resolvedModule.name());
    System.out.println("Provides: "
        + resolvedModule.reference().descriptor().provides());
});
~~~

Cũng có thể quan sát quá trình resolve của launcher bằng tùy chọn **--show-module-resolution**. Khi muốn launcher thực hiện service binding cho module path, tùy chọn **--bind-services** có thể được dùng cùng cấu hình module phù hợp:

~~~bash
java --show-module-resolution --bind-services --module-path "app-mods;plugins" -m com.acme.application/com.acme.application.Main
~~~

Dấu phân cách đường dẫn trong ví dụ trên là dấu chấm phẩy của Windows. Trên Linux/macOS, module path thường dùng dấu hai chấm. Khi chạy qua Gradle hoặc Maven, hãy bảo đảm cấu hình launcher thực tế truyền đúng module path và root module.

## 8. Những điều kiện cần để service binding hoạt động

**resolveAndBind** không tự tìm mọi class có tên giống service. Các thành phần cần có một cấu hình nhất quán:

- Module sử dụng service khai báo **uses** đúng service type.
- Provider module khai báo **provides ServiceType with ProviderType**.
- Module provider có thể được tìm thấy bởi ModuleFinder được truyền vào quá trình resolution.
- Provider module có dependency hợp lệ, bao gồm module chứa service API.
- Service type mà consumer và provider tham chiếu phải cùng module/type identity trong cấu hình runtime.
- Root module được chọn phải dẫn tới module sử dụng service; nếu không module nào trong graph sử dụng service đó, provider không được bổ sung chỉ vì nó đang nằm trong thư mục plugin.
- Khi gọi ServiceLoader với một layer cụ thể, provider phải nằm trong layer đó hoặc một layer cha mà cơ chế tìm kiếm xét tới.

Nếu provider không xuất hiện, hãy kiểm tra descriptor bằng **jar --describe-module**, kiểm tra finder có trỏ đúng thư mục, rồi kiểm tra **uses** và **provides**. Nếu provider đã nằm trong configuration nhưng ServiceLoader vẫn báo lỗi, hãy kiểm tra service type, provider constructor/provider method và class loader/layer.

## 9. Lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| resolveAndBind không thêm provider | Không có module trong finder cung cấp service mà graph sử dụng | Kiểm tra **uses**, **provides** và module path của provider |
| Module provider không tìm thấy | Finder trỏ sai thư mục, sai module name hoặc thiếu artifact | Kiểm tra ModuleFinder và **jar --describe-module** |
| ServiceLoader báo module không khai báo uses | Module gọi service chưa khai báo **uses** | Thêm service type vào module-info.java của consumer |
| ServiceLoader không tạo được provider | Provider class hoặc provider method không tuân thủ quy tắc, hoặc dependency thiếu | Kiểm tra descriptor, constructor/provider method và dependency |
| Provider có mặt trong cấu hình nhưng không được ứng dụng nhìn thấy | Đang dùng nhầm layer hoặc service API có class identity khác | Dùng **ServiceLoader.load(layer, ServiceType.class)** và chia sẻ API từ layer cha |
| Resolution thất bại sau khi bổ sung provider | Dependency của provider bị thiếu, trùng module name, split package hoặc graph không hợp lệ | Xử lý dependency graph của provider trước khi tạo layer |
| Provider không được khởi tạo ngay sau resolveAndBind | Resolution chỉ thêm module vào configuration | Duyệt ServiceLoader để yêu cầu provider instance |

Không nên giải quyết lỗi bằng cách thêm toàn bộ plugin vào root set mà chưa xác định service contract. Cách đó làm module graph phụ thuộc trực tiếp vào implementation và giảm lợi ích của service binding.

## 10. Khi nào nên dùng resolveAndBind?

Dùng **resolveAndBind** khi ứng dụng muốn xác định module provider dựa trên service contract ở thời điểm tạo configuration, đặc biệt khi provider được phân phối riêng hoặc nằm trong thư mục plugin.

Các trường hợp phù hợp:

- Ứng dụng có nhiều implementation cho một service và muốn phát hiện provider trên module path.
- Plugin có thể sử dụng service khác, tạo thành chuỗi provider cần được resolve đầy đủ.
- Ứng dụng muốn tạo một ModuleLayer chứa root modules và provider modules đã được bind.
- Công cụ đóng gói hoặc runtime cần xác định tập module provider cần thiết từ các service mà graph sử dụng.

Dùng **resolve** khi muốn kiểm soát rõ tập module thông qua root và dependency khai báo, đồng thời không muốn service binding tự bổ sung provider module. Dù chọn cách nào, việc tạo layer và khởi tạo service vẫn là các bước riêng.

## 11. Bài tập thực hành

1. Tạo module API **com.acme.report.spi** với interface **ReportExporter** và export package chứa interface.
2. Tạo module ứng dụng khai báo **requires com.acme.report.spi** và **uses com.acme.report.spi.ReportExporter**.
3. Tạo hai provider module CSV và JSON; mỗi module khai báo **provides** cho cùng service type.
4. Đặt provider JAR trong thư mục plugin riêng và tạo ModuleFinder cho thư mục đó.
5. Resolve ứng dụng bằng **resolve(...)** rồi xem configuration có những module nào.
6. Thay bằng **resolveAndBind(...)** và so sánh module provider được thêm vào configuration.
7. Tạo ModuleLayer từ configuration đã bind, sau đó tìm provider bằng **ServiceLoader.load(layer, ReportExporter.class)**.
8. Cho một provider sử dụng service thứ hai; tạo provider cho service thứ hai và quan sát việc binding bổ sung module theo chuỗi.
9. Thử bỏ **uses** khỏi module ứng dụng hoặc bỏ **provides** khỏi module provider để quan sát lỗi và giải thích nguyên nhân.
10. Dùng **--show-module-resolution** và in **configuration.modules()** để xác nhận module nào thực sự được resolve.

## 12. Những điểm cần ghi nhớ

- **uses** khai báo service mà module cần.
- **provides ... with ...** đăng ký implementation trong module provider.
- **resolve(...)** giải quyết root modules và dependency qua requires.
- **resolveAndBind(...)** thực hiện resolution cùng service binding, bổ sung provider module cho service được sử dụng trong graph.
- Service binding có thể tiếp tục qua provider sử dụng service khác cho đến khi không còn provider mới cần thêm.
- **resolveAndBind** trả về Configuration; nó không tự tạo ModuleLayer và không khởi tạo provider instance.
- **ServiceLoader** tìm và tạo provider khi ứng dụng yêu cầu, thường dùng overload nhận ModuleLayer trong kiến trúc nhiều layer.
- Provider phải nằm trong các module có thể quan sát qua finder và có dependency/service descriptor hợp lệ.
- Service API cần có cùng class identity giữa host và provider.

Khi nắm được sự khác nhau giữa module resolution, service binding, layer definition và provider instantiation, bạn có thể thiết kế cơ chế plugin theo service contract mà vẫn giữ module ứng dụng độc lập với từng implementation.
