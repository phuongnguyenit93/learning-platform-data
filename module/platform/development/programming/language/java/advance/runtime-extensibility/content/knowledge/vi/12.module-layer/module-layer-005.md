# Khám phá dịch vụ qua ServiceLoader.load(layer, service)

## 1. Mục đích

Trong Java Platform Module System (JPMS), ứng dụng có thể tạo một **ModuleLayer** riêng cho các module plugin. Sau khi giải quyết dependency và định nghĩa layer, host cần tìm các implementation của một service interface mà plugin công bố.

Java cung cấp overload:

\`\`\`java
public static <S> ServiceLoader<S> load(ModuleLayer layer, Class<S> service)
\`\`\`

Phương thức này tạo một \`ServiceLoader<S>\` để khám phá các provider của service trong **layer chỉ định và các ancestor layer** theo quy tắc của JPMS. Khác với \`ServiceLoader.load(Service.class)\`, overload này sử dụng **layer làm phạm vi khám phá**, thay vì lấy thread context class loader làm điểm xuất phát.

Ví dụ, host định nghĩa service \`GreetingService\`, còn plugin module khai báo:

\`\`\`java
provides com.example.api.GreetingService
    with com.example.plugin.VietnameseGreeting;
\`\`\`

Sau khi host tạo layer chứa plugin, lệnh:

\`\`\`java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(pluginLayer, GreetingService.class);
\`\`\`

sẽ cho phép host tìm provider có thể sử dụng mà không cần gọi \`Class.forName\` theo tên implementation.

**Điểm cần nhớ:** \`ServiceLoader.load(layer, service)\` không tạo layer, không tự nạp JAR mới từ ổ đĩa và không bảo đảm tự cập nhật khi có plugin JAR mới. Việc tìm provider qua \`ServiceLoader\` cũng có thể dẫn đến khởi tạo provider khi duyệt; vì thế phải hoàn tất kiểm tra nguồn gốc và khả năng tin cậy của plugin trước khi sử dụng.

## 2. Vai trò của service, provider và layer

Một hệ thống thường có những thành phần sau:

| Thành phần | Vai trò |
|---|---|
| Service interface | Hợp đồng mà host và provider cùng tham chiếu |
| API module | Cung cấp service interface dùng chung |
| Provider module | Khai báo implementation bằng \`provides ... with ...\` |
| \`ModuleFinder\` | Tìm module trong JAR hoặc thư mục plugin |
| \`Configuration\` | Graph module đã được phân giải dependency |
| \`ModuleLayer\` | Tập module đang tồn tại trong một lớp runtime |
| \`ServiceLoader\` | Tìm và khởi tạo provider theo hợp đồng service |

Luồng tổng quát:

\`\`\`text
        Host application
             |
        API module
             |
    ModuleFinder.of(plugins/)
             |
    Configuration.resolve(...)
             |
       ModuleLayer
             |
    ServiceLoader.load(layer, GreetingService.class)
             |
       Provider instances
             |
       Registry / selection policy
             |
          Invocation
\`\`\`

Khái niệm *service* ở đây là giao diện Java công bố dưới dạng service provider mechanism, không nhất thiết là HTTP service hoặc microservice.

Với JPMS, lớp provider có thể nằm trong package không được \`exports\` cho host; cơ chế \`provides\` vẫn cho phép \`ServiceLoader\` khởi tạo và trả về đối tượng thông qua service interface được chia sẻ.

## 3. Chuẩn bị module-info.java

Giả sử hệ thống gồm ba module:

- \`com.example.greeting.api\`: khai báo interface \`GreetingService\`.
- \`com.example.greeting.plugin\`: triển khai service và công bố provider.
- \`com.example.greeting.host\`: tạo layer, khám phá và gọi provider.

### API module

\`src/com.example.greeting.api/module-info.java\`:

\`\`\`java
module com.example.greeting.api {
    exports com.example.greeting.api;
}
\`\`\`

\`src/com.example.greeting.api/com/example/greeting/api/GreetingService.java\`:

\`\`\`java
package com.example.greeting.api;

public interface GreetingService {
    String language();
    String greet(String name);
}
\`\`\`

\`exports\` cho phép host và plugin truy cập interface theo cơ chế JPMS.

### Provider module

\`src/com.example.greeting.plugin/module-info.java\`:

\`\`\`java
module com.example.greeting.plugin {
    requires com.example.greeting.api;

    provides com.example.greeting.api.GreetingService
        with com.example.greeting.plugin.VietnameseGreeting;
}
\`\`\`

\`src/com.example.greeting.plugin/com/example/greeting/plugin/VietnameseGreeting.java\`:

\`\`\`java
package com.example.greeting.plugin;

import com.example.greeting.api.GreetingService;

public final class VietnameseGreeting implements GreetingService {
    public VietnameseGreeting() {}

    @Override
    public String language() {
        return "vi";
    }

    @Override
    public String greet(String name) {
        return "Xin chào, " + name;
    }
}
\`\`\`

Provider có public no-argument constructor để service loader khởi tạo. Trong explicit module, provider cũng có thể sử dụng quy tắc provider method \`provider()\` được API hỗ trợ; ví dụ này chọn constructor để dễ theo dõi. Không cần \`exports com.example.greeting.plugin\` chỉ để cung cấp provider bằng \`provides\`.

### Host module

\`src/com.example.greeting.host/module-info.java\`:

\`\`\`java
module com.example.greeting.host {
    requires com.example.greeting.api;
    uses com.example.greeting.api.GreetingService;
}
\`\`\`

\`uses\` khai báo rằng module host sử dụng service. Việc thiếu \`uses\` trong named module có thể khiến \`ServiceLoader\` từ chối yêu cầu khi chạy. \`requires\` cung cấp khả năng truy cập interface, còn \`uses\` khai báo tiêu thụ service; hai chỉ thị có vai trò khác nhau.

## 4. Ví dụ Java 17+: tạo ModuleLayer và khám phá provider

\`src/com.example.greeting.host/com/example/greeting/host/Main.java\`:

\`\`\`java
package com.example.greeting.host;

import com.example.greeting.api.GreetingService;
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.ServiceLoader;
import java.util.Set;

public final class Main {
    public static void main(String[] args) {
        Path pluginDirectory = Path.of("plugins");

        ModuleFinder pluginFinder = ModuleFinder.of(pluginDirectory);
        ModuleLayer parent = ModuleLayer.boot();

        Configuration configuration = parent.configuration().resolve(
                pluginFinder,
                ModuleFinder.of(),
                Set.of("com.example.greeting.plugin")
        );

        ModuleLayer pluginLayer = parent.defineModulesWithOneLoader(
                configuration,
                ClassLoader.getSystemClassLoader()
        );

        List<GreetingService> providers =
                ServiceLoader.load(pluginLayer, GreetingService.class)
                        .stream()
                        .map(ServiceLoader.Provider::get)
                        .sorted(Comparator.comparing(GreetingService::language))
                        .toList();

        for (GreetingService provider : providers) {
            System.out.println(provider.language() + ": " +
                    provider.greet("Lan"));
        }
    }
}
\`\`\`

Giải thích từng bước:

1. \`ModuleFinder.of(pluginDirectory)\` phát hiện module từ thư mục \`plugins\`.
2. \`ModuleLayer.boot()\` cung cấp parent layer chứa host và API module trong ví dụ này.
3. \`resolve(..., Set.of("com.example.greeting.plugin"))\` tìm module root và giải quyết các dependency.
4. \`defineModulesWithOneLoader\` tạo layer chứa plugin theo configuration đã resolve.
5. \`ServiceLoader.load(pluginLayer, GreetingService.class)\` tìm provider của service trong phạm vi layer.
6. \`Provider::get\` tạo/lấy instance, sau đó host gọi method của interface chung.

Ở bước \`stream()\`, \`ServiceLoader.Provider\` cho phép xem \`type()\` trước khi gọi \`get()\`, hữu ích khi muốn lọc hoặc kiểm tra kiểu provider. Nhưng thao tác phát hiện và định nghĩa class vẫn có các quy tắc liên kết riêng; không được xem \`type()\` là một sandbox hoặc một bước xác thực mã không tin cậy.

### Cấu trúc thư mục

\`\`\`text
project/
├── src/
│   ├── com.example.greeting.api/
│   │   ├── module-info.java
│   │   └── com/example/greeting/api/GreetingService.java
│   ├── com.example.greeting.host/
│   │   ├── module-info.java
│   │   └── com/example/greeting/host/Main.java
│   └── com.example.greeting.plugin/
│       ├── module-info.java
│       └── com/example/greeting/plugin/VietnameseGreeting.java
└── plugins/
\`\`\`

Từ thư mục \`project\`, chạy trên JDK 17+:

\`\`\`bash
javac --module-source-path src -d mods \
  src/com.example.greeting.api/module-info.java \
  src/com.example.greeting.api/com/example/greeting/api/GreetingService.java \
  src/com.example.greeting.host/module-info.java \
  src/com.example.greeting.host/com/example/greeting/host/Main.java \
  src/com.example.greeting.plugin/module-info.java \
  src/com.example.greeting.plugin/com/example/greeting/plugin/VietnameseGreeting.java

mkdir -p plugins

jar --create --file plugins/com.example.greeting.plugin.jar \
  -C mods/com.example.greeting.plugin .

java --module-path mods/com.example.greeting.api:mods/com.example.greeting.host \
  --module com.example.greeting.host/com.example.greeting.host.Main
\`\`\`

Các lệnh trên trình bày theo shell POSIX (dấu \`\\\` nối dòng). Với Windows PowerShell, chạy mỗi lệnh trên một dòng và thay dấu phân tách module path \`:\` bằng \`;\`. Tránh đặt thư mục \`mods\` chứa module plugin trực tiếp trên \`--module-path\` khi host khởi chạy nếu muốn chứng minh plugin chỉ được đưa vào **child layer** do code tạo; lệnh trên chỉ đưa API và host lên module path.

Kết quả mong đợi:

\`\`\`text
vi: Xin chào, Lan
\`\`\`

Nếu không có JAR hoặc module name sai, bước resolve sẽ thất bại. Nếu provider có lỗi khi khởi tạo, lỗi có thể xuất hiện khi duyệt \`ServiceLoader\` hoặc gọi \`Provider.get()\`.

## 5. Vì sao ServiceLoader.load(layer, service) khác các overload khác?

Java cung cấp nhiều cách tạo service loader:

| API | Điểm xuất phát khám phá | Khi nào dùng |
|---|---|---|
| \`ServiceLoader.load(Service.class)\` | Thread context class loader | Ứng dụng dùng classpath/TCCL hoặc cơ chế mặc định |
| \`ServiceLoader.load(Service.class, loader)\` | Class loader chỉ định | Cần kiểm soát loader theo cơ chế classpath/module |
| \`ServiceLoader.loadInstalled(Service.class)\` | Platform class loader | Dịch vụ cài đặt nhìn thấy qua loader thích hợp |
| \`ServiceLoader.load(layer, Service.class)\` | Module layer được chỉ định và ancestor layers | Hệ plugin sử dụng JPMS \`ModuleLayer\` |

Sự khác biệt có ý nghĩa khi host sử dụng nhiều layer, có cùng tên implementation ở nhiều nơi hoặc muốn giới hạn nguồn khám phá. Tuy nhiên, khám phá theo layer **không tự đảm bảo chỉ có provider thuộc đúng plugin đang xét**: API cũng tìm trong các ancestor layer. Nếu cần chính xác provider nào thuộc layer/plugin hiện tại, kiểm tra \`provider.type().getModule().getLayer()\` và metadata/allowlist tương ứng.

Thứ tự các provider do ServiceLoader trả về không phải chính sách ưu tiên nghiệp vụ. Muốn single-provider selection, fan-out hoặc pipeline, hãy xây bước lựa chọn và thứ tự riêng sau discovery.

## 6. Phân biệt module name, service type và class identity

Các lỗi khi khám phá provider thường không nằm ở cú pháp \`ServiceLoader.load\` mà ở cách tổ chức module và class loader.

**Service type phải là một \`Class\` chung** giữa host và plugin. Nếu host và plugin tự định nghĩa hai bản sao của \`GreetingService\` bằng hai loader khác nhau, việc implementation có cùng tên interface chưa đảm bảo phép cast hợp lệ. Đặt API module trong parent layer dùng chung là mô hình thông dụng.

**Module root phải tồn tại trong finder**. \`Set.of("com.example.greeting.plugin")\` chọn tên JPMS module, không phải tên JAR hay class. \`ModuleFinder.of(Path.of("plugins"))\` phải thấy JAR hoặc exploded module có descriptor hợp lệ và không bị xung đột tên.

**Provider phải đúng hợp đồng**. Service implementation phải đáp ứng quy tắc \`provides\` và kiểu service. Trong explicit module, khai báo module descriptor quyết định việc công bố provider; chỉ có implementation class trong JAR chưa đủ.

**Layer đã tạo không tự cập nhật**. Chép JAR mới vào \`plugins\` không làm \`ServiceLoader\` của layer cũ phát hiện module mới. Muốn cập nhật động, host phải xây finder/configuration/layer mới theo lifecycle của plugin manager.

## 7. Xử lý provider lỗi và chính sách lựa chọn

Khi duyệt \`ServiceLoader\`, một provider lỗi có thể gây \`ServiceConfigurationError\`. Tùy nguyên nhân còn có thể xảy ra lỗi class loading/linkage hoặc exception do mã constructor/provider method. Không nên bắt một exception chung rồi lặng lẽ bỏ qua mọi provider.

Các chính sách có thể cân nhắc:

- **Fail-fast:** nếu tất cả provider bắt buộc hợp lệ, từ chối kích hoạt layer/plugin khi phát hiện lỗi.
- **Best-effort:** nếu service là optional observer, có thể ghi nhận provider lỗi và tiếp tục theo cơ chế có kiểm soát, không che khuất sự cố.
- **Single provider:** chọn đúng một provider theo \`pluginId\`, capability, phiên bản hoặc cấu hình; từ chối nếu không có ứng viên hoặc mơ hồ.
- **Pipeline:** áp dụng order/dependency metadata của host sau discovery; không dựa trên thứ tự iteration.
- **Hot reload:** tạo snapshot provider mới, kiểm tra health, rồi chuyển request mới qua snapshot đó; drain tác vụ cũ trước khi giải phóng tham chiếu.

Không thực hiện side effect nghiệp vụ trong constructor nếu có thể tránh; ưu tiên lifecycle rõ ràng như \`initialize\`, \`start\`, \`stop\`, \`close\` để host chủ động xác định lúc plugin được phép nhận công việc.

## 8. Khám phá service và bảo mật

Đây là điểm dễ bỏ sót trong plugin runtime: \`ModuleFinder\` và \`ModuleDescriptor\` cho phép đọc metadata mà chưa cần chạy logic plugin, còn \`ServiceLoader\` có thể khởi tạo object provider và chạy mã từ JAR.

Trước khi gọi \`Provider.get()\`, host nên kiểm tra:

1. Artifact đến từ nguồn được phép, metadata và chữ ký/hash đáp ứng chính sách.
2. Module name, version, API dependency và service declaration phù hợp.
3. Không có duplicate/xung đột module hoặc provider vượt quyền.
4. Loader/layer được tạo từ bản artifact đã kiểm tra, tránh thay JAR trong lúc dùng.
5. Có chính sách lifecycle, timeout, logging và rollback nếu init thất bại.

JPMS điều khiển module readability, exports và opens; \`ModuleLayer\` không phải sandbox cho mã không đáng tin trong cùng JVM. Đối với plugin thiếu tin cậy, dùng cô lập process/container và giao thức trao đổi với host.

## 9. Câu hỏi thường gặp

### Vì sao ServiceLoader trả về danh sách rỗng?

Kiểm tra module provider đã có mặt trong layer chưa, \`module-info.java\` có đúng \`provides\` hay không, service type có được chia sẻ đúng không, module host có \`uses\` hay không, và layer được truyền vào \`load\` có đúng layer chứa provider không. Nếu dùng automatic module hoặc classpath, quy tắc provider declaration có thể khác explicit module.

### Có cần export package implementation không?

Thông thường **không** cần chỉ để dùng \`provides ... with ...\`. Java service loader có thể tạo provider trong package implementation không export, trong khi host chỉ gọi qua interface của API module.

### Có thể gọi ServiceLoader.load(layer, service) nhiều lần không?

Có. Mỗi lời gọi tạo một service loader riêng, có cache provider/instance riêng theo quy tắc API. Không nên giả định chúng dùng chung singleton provider. Với cùng một \`ServiceLoader\`, \`reload()\` xóa cache provider để iteration kế tiếp tìm lại trong phạm vi layer đó, nhưng **không thêm module mới vào layer đã tồn tại**.

### ServiceLoader có sắp xếp theo priority không?

Không tự xử lý priority nghiệp vụ. Host cần đọc metadata của provider và áp dụng selector/sorter rõ ràng. Đừng gán ý nghĩa ưu tiên cho thứ tự tình cờ do discovery.

### Có được tạo layer cho mỗi plugin không?

Có thể, nếu graph dependency, class identity và lifecycle cho phép. Tuy vậy chi phí loader/module, quản lý shared API, service visibility và tài nguyên sẽ phức tạp hơn. Một layer chứa nhiều plugin hoặc nhiều layer độc lập đều là lựa chọn kiến trúc, cần kiểm thử xung đột dependency và hot reload.

## 10. Checklist áp dụng

- API module xuất service interface và được chia sẻ bởi host/plugin.
- Host named module khai báo \`uses\`.
- Provider module khai báo \`requires\` API và \`provides\` implementation.
- Finder trỏ đúng thư mục/JAR, module root chính xác.
- Configuration resolve được trên parent module graph.
- Layer được định nghĩa với class loader phù hợp.
- \`ServiceLoader.load(layer, Service.class)\` dùng đúng đối tượng layer và service type.
- Provider được lựa chọn theo chính sách riêng; xử lý trùng, thiếu và lỗi khởi tạo.
- Metadata/integrity được xác thực trước khi thực thi mã provider.
- Hot reload tạo layer/snapshot mới và dọn lifecycle cũ.

**Ghi nhớ:** \`ServiceLoader.load(layer, service)\` là cầu nối từ **JPMS ModuleLayer** đến **service provider**. Nó giúp host khám phá implementation theo module graph, nhưng quản lý plugin hoàn chỉnh vẫn cần kiểm tra nguồn gốc, giải quyết dependency, lựa chọn provider và kiểm soát vòng đời.
