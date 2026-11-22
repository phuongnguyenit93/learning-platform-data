
# Nền tảng ứng dụng, plugin và dependency do máy chủ cung cấp

Khi nâng cấp Java, một ứng dụng có thể biên dịch thành công trên JDK mới nhưng lại không khởi động được trong application server, không phát hiện plugin, không tìm thấy dịch vụ do container cung cấp hoặc gặp lỗi ép kiểu giữa hai class có **cùng tên**. Đây không nhất thiết là lỗi của ngôn ngữ Java hay một phương thức vừa bị xóa. Nhiều hệ thống phụ thuộc vào **hợp đồng giữa ứng dụng, nền tảng chạy, class loader và các thư viện runtime nằm ngoài artifact**.

Ví dụ: một WAR biên dịch với Jakarta Servlet API nhưng được triển khai trên servlet container thuộc thế hệ `javax.servlet`; một plugin tự đóng gói host SDK khiến host nhìn thấy hai bản định nghĩa interface; một ứng dụng trông như không dùng JDBC driver trong POM vì driver nằm ở server module; hoặc một executable JAR mới không còn nhận các service mà external application server cũ từng cung cấp. Trong mỗi tình huống, **compile classpath không phản ánh đầy đủ runtime thực tế**.

Bài học nằm trong *Java Advance Compatibility Migration*, chương *Framework và nền tảng*. Trọng tâm là cách phân biệt API và implementation, các mô hình server-managed dependency, plugin host, class-loader isolation, ServiceLoader, JPMS và phương pháp migration có thể kiểm chứng.

## 1. Mô hình tổng thể: ứng dụng chạy trên nhiều lớp

Một ứng dụng Java doanh nghiệp thường có ít nhất ba lớp:

1. **Mã ứng dụng và artifact được đóng gói:** classes, resources, dependencies thuộc sở hữu ứng dụng, cấu hình.
2. **Nền tảng ứng dụng:** application server, servlet container, framework runtime, plugin host, service registry và những dependency được cấp từ môi trường bên ngoài.
3. **Nền tảng Java và hệ điều hành:** JVM/JDK runtime image, Java SE modules, native libraries, module access, security properties.

Ví dụ một triển khai WAR:

~~~text
Java runtime / JDK
└── Application server
    ├── Server modules + shared libraries
    ├── Servlet engine, transaction, naming, logging
    ├── Provider/Service discovery
    └── Deployed application.war
        ├── WEB-INF/classes
        ├── WEB-INF/lib/*.jar
        └── Configuration / resources
~~~

Trên một executable JAR có embedded server, ranh giới thay đổi:

~~~text
Java runtime / JDK
└── application.jar / launcher
    ├── Application classes
    ├── Framework and embedded server
    ├── Runtime dependencies
    └── Configuration / resources
~~~

Với plugin host, còn có lớp SDK do host sở hữu và class loader riêng của plugin. Vì vậy, quy tắc đóng gói thư viện không thể áp dụng đồng loạt cho WAR, standalone JAR và plugin archive.

~~~mermaid
flowchart TD
    A["Mã ứng dụng hoặc plugin"] --> B["Compile API"]
    A --> C["Runtime riêng của ứng dụng"]
    A --> D["API/runtime do host cung cấp"]
    D --> E["Server/container/plugin host"]
    C --> F["JVM và Java SE modules"]
    E --> F
    B -. "API generation phải phù hợp" .-> D
~~~

## 2. Nền tảng ứng dụng là gì?

“Nền tảng ứng dụng” là môi trường hỗ trợ thực thi và quản lý một tập ứng dụng hoặc extension. Những hình thức thường gặp:

- **Servlet container:** HTTP connector, servlet/filter/listener, lifecycle web application.
- **Application server:** có thể cung cấp thêm các enterprise services như CDI, persistence integration, transactions, naming, messaging, validation tùy profile và version.
- **Framework runtime:** dependency injection, web/data integrations và starter dependencies đi cùng ứng dụng.
- **Embedded server:** servlet/web engine được đóng trong executable app.
- **Plugin host:** SDK, extension points, plugin discovery, lifecycle và class-loading rules.
- **Custom runtime image:** các Java/JDK modules được chọn qua `jlink`, có thể không chứa mọi module của JDK đầy đủ.

Các sản phẩm này có trách nhiệm khác nhau. Không nên suy luận “có JDK là có Java EE server”, hoặc “có dependency API là tự có runtime engine”.

### 2.1. API khác implementation

Một API định nghĩa contract dưới dạng class/interface/annotation/enum. Implementation thực thi hành vi.

| API/contract | Implementation/runtime cần thiết |
|---|---|
| `jakarta.servlet.*` | Servlet container |
| `jakarta.persistence.*` | ORM/persistence provider hoặc integration của server |
| `jakarta.validation.*` | Bean Validation provider |
| `jakarta.enterprise.inject.*` | CDI runtime |
| `jakarta.ws.rs.*` | JAX-RS server/client implementation |
| `java.sql.*` và `javax.sql.*` | JDBC driver, datasource/pool |
| SLF4J | Logging provider/backend |
| API plugin host | Plugin runtime và extension registration |

Bộ API có thể đủ để **biên dịch**, nhưng thường không tự tạo HTTP server, truy cập database hoặc khởi động validation engine.

### 2.2. Dependency do máy chủ cung cấp là gì?

Server-managed dependency là library hoặc API mà runtime host chịu trách nhiệm cung cấp cho ứng dụng. Ví dụ:

- Servlet API có sẵn trong external web container.
- Shared JPA/validation service do application server quản lý.
- JDBC driver khai báo trong server module.
- API của plugin SDK do host loader cung cấp.
- Logging bridge hoặc service provider thuộc host.
- Java SE modules đến từ runtime image.

Các component này **không nằm trong artifact ứng dụng** không có nghĩa là chúng không tồn tại ở runtime. Điều ngược lại cũng đúng: một dependency có trong local build nhưng có thể không được đóng gói vì scope.

### 2.3. Cần trả lời năm câu hỏi

Với mỗi dependency quan trọng:

1. **Ai định nghĩa API?** Java SE, Jakarta EE, framework, plugin SDK hay thư viện riêng?
2. **Ai triển khai hành vi?** App, provider, server, embedded runtime hay HSM/native bridge?
3. **Ai sở hữu version?** Application team, platform team, vendor server, plugin host?
4. **Ai nạp class?** Application class loader, server module loader, plugin loader, JPMS layer?
5. **Ai cấu hình provider/lifecycle?** DI container, ServiceLoader, server descriptor hay code khởi tạo?

Một câu trả lời thiếu ở bất kỳ mục nào có thể tạo rủi ro khi nâng JDK hoặc platform.

## 3. Ba classpath khác nhau và một artifact cuối

Cần phân biệt:

- **Compile classpath:** API/classes mà javac cần để biên dịch source.
- **Runtime classpath:** các class/libraries ứng dụng dùng khi chạy.
- **Host/server/plugin classpath:** dependencies do runtime bên ngoài cung cấp hoặc nạp qua loader riêng.
- **Test classpath:** thường rộng hơn production, có mock, embedded database và test engines.

Một dự án có thể compile được vì dependency nằm ở compile classpath, nhưng runtime vẫn thiếu nó nếu host không cung cấp đúng type.

| Thời điểm | Kiểm tra | Điều chưa chứng minh |
|---|---|---|
| Compile thành công | Mã source khớp API trên compile path | Server có API đó |
| Package thành công | Build tạo WAR/JAR | Server load và bootstrap được |
| Startup thành công | Các thành phần khởi tạo cơ bản | Mọi plugin/job/path chạy đúng |
| Provider được phát hiện | Registry có implementation | Phép gọi thật và quyền truy cập đúng |
| Unit test thành công | Logic trong test environment | Integration với server production |

**Artifact cuối** (WAR, fat JAR hoặc plugin ZIP) và môi trường thực thi là hai nguồn sự thật cần kiểm tra cùng nhau.

## 4. Maven provided: compile có, runtime do bên khác cấp

Một WAR triển khai lên external servlet container có thể khai báo:

~~~xml
<dependency>
  <groupId>jakarta.servlet</groupId>
  <artifactId>jakarta.servlet-api</artifactId>
  <version>SERVLET_API_VERSION</version>
  <scope>provided</scope>
</dependency>
~~~

`SERVLET_API_VERSION` chỉ là placeholder. Version phải tương thích server thật.

Ý nghĩa của `provided` là Maven cho phép compile và test với API, nhưng kỳ vọng môi trường ngoài cung cấp dependency khi chạy theo deployment model.

Nó **không có nghĩa rằng Servlet API không cần tồn tại ở runtime**.

### 4.1. Khi dùng provided sai

Giả sử app compile với Servlet API thế hệ mới nhưng deploy lên server cung cấp thế hệ cũ. Có thể xảy ra:

- `NoClassDefFoundError` vì server thiếu một kiểu.
- `NoSuchMethodError` vì server API version không có method.
- `AbstractMethodError` do binary implementation mismatch.
- Không thể load servlet/filter/listener.
- Lỗi namespace `javax.*` và `jakarta.*` không tương thích.
- Không tìm thấy service/provider hoặc server không chấp nhận descriptor.

Không sửa bằng cách ngẫu nhiên thêm nhiều API JAR vào WAR; cần căn đúng server và API generation.

### 4.2. API nào nên provided?

Phụ thuộc runtime:

| Deployment | Ai cung cấp runtime? | Hướng dependency |
|---|---|---|
| WAR trên external Servlet container | Server cung cấp engine/API | Servlet API thường provided |
| Executable JAR với embedded server | App/framework đóng embedded server | Server implementation cần ở runtime |
| Jakarta EE server với profile phù hợp | Server cung cấp các enterprise services đã công bố | Có thể dùng provided cho API đó |
| Standalone main class | Không tự có enterprise container | App cần runtime provider thực |
| Plugin trong host | Host cung cấp SDK/extension API | API host thường không bundle vào plugin |
| Unit test | Test runner cung cấp mock/embedded components | Test dependencies khác production |

Cần đọc tài liệu của nền tảng đang deploy, không sao chép quy tắc của dự án khác.

## 5. Gradle: các configuration không đồng nghĩa

Ví dụ:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    compileOnly("com.example.host:plugin-api:HOST_VERSION")
    implementation("com.example:commons:UTILS_VERSION")
    runtimeOnly("com.example:jdbc-driver:DRIVER_VERSION")
}
~~~

Đây là cú pháp minh họa với tọa độ placeholder.

| Configuration | Compile module | Runtime module | Mục đích |
|---|---|---|---|
| `api` (java-library) | Có | Thường có | Public dependency cho consumer |
| `implementation` | Có | Có | Implementation detail |
| `compileOnly` | Có | Không tự đưa vào runtime | API được runtime ngoài cấp |
| `runtimeOnly` | Không | Có | Provider/driver chỉ dùng khi chạy |
| `testImplementation` | Test compile | Test runtime | Test-only dependencies |
| `testRuntimeOnly` | Không cho test compile | Test runtime | Test provider/engine |

### 5.1. compileOnly là một cam kết với host

Nếu plugin dùng `com.example.host.PluginContext` ở source, nó có thể compile bằng dependency `compileOnly`. Nhưng host phải export chính type đó tới plugin loader. Một bản host khác có API không tương thích vẫn có thể gây linkage error.

### 5.2. api và public contract

Nếu một thư viện public có method:

~~~java
public com.example.host.PluginContext createContext();
~~~

type bên ngoài đã nằm trong public API của thư viện. Khi publish một library, cần đảm bảo consumer compile được với contract đó. Trong Gradle Java Library, `api(...)` có thể phù hợp khi public type cần được export, nhưng với SDK của host còn phải cân nhắc cơ chế provided và metadata publishing. Không có một configuration duy nhất đúng cho mọi platform.

### 5.3. RuntimeOnly không dành cho code import implementation trực tiếp

Nếu source gọi `new VendorDriver()` hoặc sử dụng class riêng của provider, dependency đó cần nằm ở compile path nữa. Khi có thể, thiết kế code dựa vào API và chọn provider ở runtime, nhưng dependency declaration phải phản ánh source thực tế.

## 6. WAR, executable JAR và plugin artifact

### 6.1. WAR

Cấu trúc thường gặp:

~~~text
application.war
├── WEB-INF/classes/
├── WEB-INF/lib/
└── WEB-INF/web.xml (nếu cần)
~~~

Không phải mọi server đều dùng cùng class-loader policy, nhưng thường có phân biệt thư viện của server với thư viện đóng gói trong ứng dụng.

### 6.2. Executable JAR

Ứng dụng standalone cần đưa runtime mà nó sở hữu vào artifact hoặc external runtime classpath. Một framework có thể đóng JAR lồng nhau với launcher riêng. Vì vậy, việc thiếu dependency trong root của JAR không tự chứng minh dependency không tồn tại; phải hiểu layout của packager.

### 6.3. Plugin archive

Một plugin host có thể yêu cầu:

~~~text
plugin-package/
├── plugin.jar
├── lib/plugin-helper.jar
├── lib/third-party.jar
└── plugin-descriptor.properties
~~~

Tên và cách đóng gói thay đổi theo host. Một số platform dùng chỉ một JAR, số khác dùng ZIP/bundle, `META-INF/services` hoặc JPMS module descriptor.

**Plugin API thường thuộc host, implementation thường thuộc plugin.** Đưa bản sao API của host vào plugin có thể phá class identity.

## 7. Class loader: lý do hai class cùng tên không giống nhau

Trong JVM, class identity phụ thuộc vào **binary name và defining class loader**. Hai loader độc lập có thể định nghĩa:

~~~text
com.example.host.Plugin
~~~

ở hai không gian khác nhau. JVM coi đó là hai kiểu riêng biệt.

Ví dụ lỗi:

~~~text
java.lang.ClassCastException:
class com.example.host.Plugin cannot be cast to
class com.example.host.Plugin
~~~

Thông báo thật có thể kèm tên module/loader để phân biệt hai bản. Không nên coi đây là lỗi vô lý hoặc lỗi của phép cast; phải kiểm tra nguồn JAR và loader.

### 7.1. Loader hierarchy thường gặp

~~~mermaid
flowchart TD
    A["Plugin class loader"] --> B["Host / parent class loader"]
    B --> C["Platform class loader"]
    C --> D["Bootstrap classes"]
    A --> E["Plugin implementation + private libs"]
    B --> F["Host SDK + shared APIs"]
~~~

Nhiều loader dùng parent-first delegation; plugin host có thể dùng child-first hoặc rule theo package. Mỗi nền tảng có chính sách riêng và có thể thay đổi giữa các phiên bản.

### 7.2. Duplicate API gây vấn đề như thế nào?

Host định nghĩa:

~~~java
package com.example.sdk;

public interface Plugin {
    void start(HostContext context);
}
~~~

Nếu plugin đóng một JAR khác định nghĩa `com.example.sdk.Plugin`, rồi loader của plugin ưu tiên bản riêng, instance có thể không được host nhận diện là implement interface do host load.

Hậu quả có thể là:

- `ClassCastException`.
- `LinkageError`.
- Host không đăng ký plugin.
- Không nhận ra annotation/interface khi scanning.
- Provider không thỏa SPI contract.
- Reflection lookup với `Class<?>` khác identity dù tên giống nhau.

Thường cần **chia sẻ một API từ host** và cô lập implementation details. Nhưng phải theo cơ chế chính thức của host vì một số framework module có cách liên kết riêng.

### 7.3. Xem class loader và code source

~~~java
import java.net.URL;
import java.security.CodeSource;

public final class ClassOrigin {
    public static void inspect(Class<?> type) {
        ClassLoader loader = type.getClassLoader();
        CodeSource source = type.getProtectionDomain()
                .getCodeSource();
        URL url = source == null ? null : source.getLocation();

        System.out.println(type.getName());
        System.out.println("loader=" + loader);
        System.out.println("source=" + url);
        System.out.println("module=" + type.getModule().getName());
    }
}
~~~

Loader có thể là `null` với class thuộc bootstrap; module name có thể là `null` cho unnamed module; code source cũng có thể `null`. Đây là tình huống bình thường. Không log đường dẫn nhạy cảm trong môi trường công khai.

Khi gặp duplicate types, so sánh origin của **class do host load** và **class do plugin load**, không chỉ tìm file cùng tên trong repository.

## 8. Class-loading policy: parent-first, child-first và server modules

**Parent-first** ưu tiên hỏi loader cha trước. Điều này giúp chia sẻ một số APIs nhưng có thể làm plugin vô tình dùng thư viện cũ của host.

**Child-first** cho plugin cô lập một số thư viện, nhưng dễ tạo hai bản của shared API nếu không có exception rule.

Một số server dùng package-level delegation hoặc module dependency declarations thay vì một thứ tự đơn giản.

Ví dụ hai plugin:

~~~text
Host SDK
├── Plugin A
│   └── private JSON library v1
└── Plugin B
    └── private JSON library v2
~~~

Cô lập hai JSON libraries có thể hợp lệ nếu các type của chúng không vượt qua ranh giới host–plugin. Nếu method thuộc API host trực tiếp nhận một class JSON từ phiên bản A nhưng host dùng phiên bản B, binary contract sẽ rối.

### 8.1. Phân biệt plugin-local và shared types

Một quy tắc thiết kế:

- Đưa **host SDK/shared API** vào vùng loader thống nhất.
- Đưa **implementation-specific dependencies** vào plugin-local classpath khi host cho phép.
- Không expose class plugin-local qua public host contract trừ khi có bridge/version policy.
- Truyền DTO/Java SE types hoặc serialized data qua ranh giới khi cần tránh version coupling.
- Ghi rõ thư viện nào có thể shade/relocate.

### 8.2. Khi nâng server-shared library

Thư viện ở server module có thể được dùng bởi nhiều WAR/plugin. Thay đổi version ở server-level ảnh hưởng nhiều ứng dụng cùng lúc.

Trước khi nâng:

1. Liệt kê toàn bộ consumer.
2. Xác định public APIs và binary signatures họ sử dụng.
3. Đọc compatibility notes.
4. Test các consumer đại diện.
5. Đặt phương án rollback cùng server module.
6. Không chỉ thử app mới nhất rồi cho rằng các app cũ đều an toàn.

## 9. Jakarta EE API generation và server compatibility

Một rủi ro lớn khi đổi framework/application server là chuyển enterprise API từ `javax.*` sang `jakarta.*`.

~~~java
// Thế hệ cũ:
import javax.servlet.Filter;

// Thế hệ mới:
import jakarta.servlet.Filter;
~~~

Hai class có binary names khác nhau. Một WAR compile với `javax.servlet.Filter` không tự trở thành Jakarta-compatible khi server chỉ cung cấp `jakarta.servlet.Filter`.

Những điểm cần đồng bộ:

- Servlet/filter/listener.
- JPA annotations và provider.
- Validation API/implementation.
- CDI extension points.
- REST APIs.
- JAXB/Mail/messaging nếu liên quan.
- Framework major version.
- Application server hoặc embedded runtime.
- XML/service metadata.
- Binary dependencies đã compile trước đó.

**Không thay tất cả `javax.` thành `jakarta.`**: nhiều Java SE APIs như `javax.sql.DataSource`, `javax.crypto.Cipher` và `javax.annotation.processing.Processor` vẫn thuộc Java SE.

### 9.1. Server profile quyết định runtime được cung cấp

Một servlet container không tự cung cấp toàn bộ các dịch vụ Jakarta EE Full Platform. Ngược lại, một full application server có thể cung cấp nhiều provider nhưng vẫn phải xét version/profile và cấu hình.

Đừng dựa vào tên thương mại hoặc chữ “Jakarta” trên website để kết luận server có tất cả APIs; kiểm tra **profile, version và extension modules được bật**.

### 9.2. Chuyển JDK khác chuyển enterprise platform

JDK 11 loại các module Java EE/CORBA từng bundled trong JDK cũ theo JEP 320. Đây là vấn đề riêng với việc enterprise APIs sau này chuyển namespace ở Jakarta EE 9.

Có thể nâng JDK mà vẫn giữ framework `javax.*` cũ nếu được hỗ trợ và có dependency phù hợp; cũng có thể nâng đồng bộ toàn bộ stack sang Jakarta. Cần quyết định riêng hai chiều để tránh sửa quá rộng.

## 10. Plugin contract và extension points

Một plugin được host nạp để mở rộng hệ thống. Host có thể công bố:

~~~java
package com.example.host.api;

public interface Plugin {
    String id();
    void start(PluginContext context);
    void stop();
}
~~~

Plugin:

~~~java
package com.example.plugin.audit;

import com.example.host.api.Plugin;
import com.example.host.api.PluginContext;

public final class AuditPlugin implements Plugin {
    @Override
    public String id() {
        return "audit";
    }

    @Override
    public void start(PluginContext context) {
        context.log("Audit started");
    }

    @Override
    public void stop() {
        // Dọn tài nguyên do plugin sở hữu.
    }
}
~~~

Plugin cần contract ổn định với host:

- Interface và method descriptors.
- Lifecycle sequence.
- Threading model.
- Permission model.
- Registration/discovery mechanism.
- Supported SDK versions.
- Access tới dữ liệu và services của host.
- Error handling và hot reload nếu có.

Một interface binary-compatible vẫn có thể đổi **hành vi** như thứ tự callback, transaction context hoặc thread mà callback chạy. Do đó, kiểm thử plugin cần nhiều hơn compile.

## 11. ServiceLoader và SPI

`java.util.ServiceLoader` là một cơ chế chuẩn để tìm implementation của service interface.

API:

~~~java
package com.example.spi;

public interface Exporter {
    String id();
    byte[] export(String content);
}
~~~

Implementation:

~~~java
package com.example.plugins.csv;

import com.example.spi.Exporter;
import java.nio.charset.StandardCharsets;

public final class CsvExporter implements Exporter {
    @Override
    public String id() {
        return "csv";
    }

    @Override
    public byte[] export(String content) {
        return content.getBytes(StandardCharsets.UTF_8);
    }
}
~~~

Với classpath-based SPI, JAR implementation có file:

~~~text
META-INF/services/com.example.spi.Exporter
~~~

và nội dung:

~~~text
com.example.plugins.csv.CsvExporter
~~~

Host:

~~~java
import com.example.spi.Exporter;
import java.util.ServiceLoader;

for (Exporter exporter : ServiceLoader.load(Exporter.class)) {
    System.out.println(exporter.id());
}
~~~

### 11.1. Implementation có mặt chưa chắc được tìm thấy

Có thể thiếu file `META-INF/services`, tên provider sai, class bị remove khi minimization, descriptor bị ghi đè khi shading hoặc loader không nhìn thấy JAR implementation.

Nếu plugin dùng class loader riêng, code host có thể cần truyền đúng loader:

~~~java
ServiceLoader<Exporter> exporters =
        ServiceLoader.load(Exporter.class, pluginClassLoader);
~~~

Nhưng interface `Exporter` vẫn phải có **cùng class identity** ở host và provider.

### 11.2. Nhiều providers không nhất thiết là tốt

Khi có nhiều implementation cùng service:

- Host cần policy chọn đúng provider.
- Không dựa vào thứ tự classpath một cách ngầm định.
- Kiểm tra duplicate provider IDs.
- Xử lý provider vắng mặt với lỗi rõ.
- Không fallback sang provider sai chính sách bảo mật/dữ liệu.
- Log tên và version provider thực sự đang hoạt động khi có thể.

### 11.3. Named modules có uses/provides

~~~java
module com.example.spi.api {
    exports com.example.spi;
}
~~~

~~~java
module com.example.csv.provider {
    requires com.example.spi.api;
    provides com.example.spi.Exporter
        with com.example.plugins.csv.CsvExporter;
}
~~~

~~~java
module com.example.app {
    requires com.example.spi.api;
    uses com.example.spi.Exporter;
}
~~~

Cần phân biệt khai báo provider trong module với việc provider module được **resolve** trong runtime layer. Custom `ModuleLayer` và launcher có thể yêu cầu service binding/configuration phù hợp.

## 12. JPMS module và server module không giống nhau

JDK 9 đưa Java Platform Module System. Nhưng server/plugin host có thể có hệ thống module riêng.

- **JPMS module:** `module-info.java`, `requires`, `exports`, `opens`, `uses`, `provides`.
- **Server-specific module:** dependency/export/isolation theo cấu hình máy chủ.
- **Plugin class loader:** phân chia không gian class theo plugin hoặc extension.

Ba mô hình có thể cùng tồn tại. Một `requires` trong `module-info.java` không tự khiến server module export class đó cho mọi plugin.

### 12.1. Đọc đúng requires, exports và opens

~~~java
module com.example.application {
    requires com.example.api;
    exports com.example.publicapi;
    opens com.example.model to com.example.orm.runtime;
}
~~~

- `requires` xác lập readability.
- `exports` cho phép truy cập công khai các public types trong package.
- `opens` cho phép deep reflection trong phạm vi chỉ định.

Không thêm `opens` để chữa `ClassNotFoundException` vì sai dependency scope. Không thêm `--add-exports` để chữa provider registration sai. Phân loại lỗi trước.

### 12.2. Custom runtime image có thể thiếu module

Một server chạy trên image tạo bằng `jlink` chỉ có các module được chọn. Nếu một extension cần `java.sql` hoặc một JDK provider module không có, lỗi runtime có thể phát sinh dù developer có JDK đầy đủ.

Kiểm tra trên đúng runtime:

~~~bash
java --list-modules
~~~

Không giả định `java` trên shell developer là cùng binary với Java của container/server.

## 13. Thread context class loader và plugin discovery

Một số framework và `ServiceLoader` dùng **thread context class loader (TCCL)**. Khi plugin được nạp riêng, TCCL ảnh hưởng provider/resource lookup.

Kiểm tra:

~~~java
ClassLoader loader =
        Thread.currentThread().getContextClassLoader();

System.out.println(loader);
~~~

Nếu một callback chạy trong thread khác với thread của host, TCCL có thể khác, dẫn đến lỗi chỉ xuất hiện ở background job.

### 13.1. Khi host thay TCCL cần hoàn nguyên

Ví dụ host chủ động gọi bootstrap:

~~~java
Thread current = Thread.currentThread();
ClassLoader previous =
        current.getContextClassLoader();

try {
    current.setContextClassLoader(pluginLoader);
    invokePluginBootstrap();
} finally {
    current.setContextClassLoader(previous);
}
~~~

Đây là mẫu cho code sở hữu lifecycle; không phải lời khuyên để mọi plugin tùy tiện thay TCCL. Khi debug phải ghi loader của thread, service interface, implementation và module layer.

## 14. Hot reload, unload và class loader leaks

Một plugin có thể nạp thành công lần đầu nhưng leak mỗi lần reload, đặc biệt sau khi host/JDK nâng cấp.

Các nguyên nhân thường gặp:

- Host static registry giữ plugin object.
- Thread do plugin tạo chưa dừng.
- Scheduled task và executor vẫn chạy.
- `ThreadLocal` giữ instance từ plugin loader.
- Context class loader của thread chưa hoàn nguyên.
- Event listener chưa unsubscribe.
- JDBC driver hoặc MBean còn đăng ký.
- Logging appender/callback giữ reference.
- Timer hoặc cache giữ class/object của plugin.

Kiểm thử nên gồm:

~~~text
Load plugin
→ Start
→ Execute representative operations
→ Stop and release owned resources
→ Unload
→ Load again
→ Check behavior and resource usage
~~~

Không giải quyết bằng cách tùy tiện tắt global service của host. Plugin chỉ nên cleanup những tài nguyên nó sở hữu theo hợp đồng platform.

### 14.1. Threading là một phần của plugin API

Nếu host đổi callback từ thread đồng bộ sang async worker, code plugin phụ thuộc thread-local transaction/security context có thể lỗi mà không có compile error.

Cần kiểm tra:

- Callback threading contract.
- Security/transaction context propagation.
- Concurrency giới hạn.
- Shutdown/lifecycle ordering.
- Error propagation.
- Plugin resource ownership.

## 15. Shading và relocation: giảm xung đột có giới hạn

Khi plugin cần phiên bản thư viện khác host, có thể dùng relocation cho **implementation-private** dependency.

Ví dụ khái niệm:

~~~text
com.vendor.json.*  →  com.example.plugin.shadow.json.*
~~~

Nhưng relocation không tự xử lý:

- Public API type dùng thư viện gốc.
- Reflection names nằm trong chuỗi.
- `META-INF/services` chưa được sửa.
- Serialization type identifiers.
- Resource paths.
- Native libraries.
- Signed JAR metadata.
- Annotation scanning.
- ClassLoader-based service registration.

Cần thử packaged artifact và host runtime. Không relocate host SDK nếu host cần nhận các type đó với đúng class identity.

### 15.1. Fat JAR có thể làm mất provider descriptors

Hai thư viện đều có:

~~~text
META-INF/services/com.example.spi.Exporter
~~~

Nếu assembly chỉ giữ một file, provider còn lại biến mất. Cần cấu hình service descriptor merging phù hợp với build plugin, rồi đọc nội dung JAR cuối và chạy service discovery test.

## 16. JDK upgrade tác động server/plugin theo những trục nào?

| Trục | Rủi ro |
|---|---|
| Class-file version | Plugin/dependency được build cho JVM mới hơn |
| Reflection/JPMS | Framework truy cập package không còn được mở |
| JDK internal APIs | Plugin/agent cũ dùng implementation detail không ổn định |
| Bytecode tooling | ASM/Byte Buddy/instrumentation không hiểu class file mới |
| Java EE-related modules | API từng bundled trong JDK cũ không còn ở JDK 11+ |
| Security/TLS | Algorithm policy, truststore, provider thay đổi |
| Default charset/locale/timezone | Dữ liệu/log/file behavior thay đổi |
| Native libraries | JNI, driver, CPU/OS ABI và vendor support |
| Runtime image | Custom jlink image thiếu module |
| Server framework | Server version chưa được công bố hỗ trợ JDK mục tiêu |

Nâng JDK **không thay thế** việc nâng framework/server/plugin SDK. Một hệ thống có thể cần sửa cả ba, nhưng nên tách rủi ro để biết nguồn thay đổi.

### 16.1. Compile JDK khác runtime JDK

Ví dụ Gradle dùng toolchain Java 21 để compile nhưng target Java 17:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

`--release 17` giới hạn API và bytecode cho source do compiler này biên dịch; nó không tự chuyển bytecode của third-party dependencies hay native host components về Java 17.

Phải chạy artifact trên **runtime version thấp nhất được công bố hỗ trợ**.

## 17. Security: class loader isolation không phải sandbox

Một plugin cùng JVM có thể chia sẻ nhiều quyền hệ điều hành với host. Phân chia class loader giúp quản lý namespace và một số boundary, nhưng **không phải sandbox bảo mật đầy đủ**.

Plugin không đáng tin có thể gây:

- Truy cập dữ liệu hoặc file mà process được phép.
- Network traffic ngoài dự kiến.
- Tạo thread hoặc tiêu thụ memory vô hạn.
- Ghi system properties/global registries.
- Thao tác reflection nếu access cho phép.
- Tải native library hoặc agent trong môi trường cho phép.

Không nên dựa vào Security Manager truyền thống như chiến lược sandbox mới cho JDK hiện đại; chính sách hỗ trợ đã thay đổi đáng kể. Với code không đáng tin, cân nhắc **cách ly tiến trình/container**, policy OS/network và host permission model được thiết kế rõ ràng.

### 17.1. Không mở module toàn cục chỉ để plugin chạy

Một workaround như:

~~~text
--add-opens java.base/java.lang=ALL-UNNAMED
~~~

mở deep reflection vào package tương ứng cho nhiều unnamed modules theo phạm vi. Nó không chữa lỗi thiếu API hoặc class loader conflict.

Cần xác định chính xác caller và nguyên nhân; ưu tiên nâng dependency/host, dùng public API hoặc cấu hình `opens` tối thiểu cho package do ứng dụng sở hữu.

## 18. Ma trận lỗi và cách khoanh vùng

| Triệu chứng | Tầng có thể lỗi | Hướng kiểm tra |
|---|---|---|
| `package ... does not exist` lúc compile | Compile dependency/API | Source import, API generation, compileClasspath |
| `ClassNotFoundException` | Runtime class visibility | JAR, host module, class loader |
| `NoClassDefFoundError` | Runtime linkage hoặc initialization | Cause chain, missing class/module |
| `NoSuchMethodError` | Binary mismatch | Version + method descriptor |
| `AbstractMethodError` | Interface và implementation lệch | Provider/host SDK generation |
| `ClassCastException` cùng class name | Duplicate defining loaders | Host API vs plugin-local API |
| `ServiceConfigurationError` | SPI/descriptor/provider | `META-INF/services`, loader, module resolution |
| Plugin không được đăng ký | Host lifecycle/metadata | Plugin descriptor, extension point, version |
| HTTP 404 dù servlet compile | Server routing/container | Deployment logs, annotations/descriptors |
| ORM entity not managed | Provider/annotation mismatch | JPA generation, entity scanning |
| `InaccessibleObjectException` | JPMS reflection | Module openness, framework internals |
| `UnsupportedClassVersionError` | JVM baseline | Class file version, runtime JDK |
| Lỗi chỉ sau reload | Resource/loader leak | Threads, listeners, registries, TCCL |
| Lỗi chỉ trong background thread | Context classloader | TCCL, executor lifecycle |

Cùng một exception có thể có nhiều nguyên nhân. Không kết luận chỉ từ thông báo ngoài cùng; cần đọc `Caused by` và đối chiếu artifact/runtime.

## 19. Công cụ chẩn đoán dependency và bytecode

### 19.1. Maven dependency tree

~~~bash
mvn dependency:tree
~~~

Tree giúp xem transitive dependencies và version mediation của ứng dụng, **không nhất thiết thấy thư viện có sẵn trong server**.

### 19.2. Gradle dependency report

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency example-lib \
  --configuration runtimeClasspath
~~~

Đọc thêm cấu hình dành riêng cho plugin/test nếu build sử dụng. Một bản provider chỉ có ở test runtime không được coi là dependency production.

### 19.3. Kiểm tra nội dung artifact

~~~bash
jar tf path/to/application.jar
jar tf path/to/application.war
~~~

Quan tâm đến:

- `WEB-INF/lib` và `WEB-INF/classes` trong WAR.
- Third-party JAR đã được đóng gói.
- `META-INF/services`.
- Plugin descriptors.
- `module-info.class`.
- Manifest and Multi-Release JAR metadata.
- Class bị loại bởi minimization.

### 19.4. Xem method descriptors

~~~bash
javap -classpath path/to/host-api.jar \
  -p -s com.example.host.api.Plugin
~~~

So sánh API mà plugin được compile với API host đang cấp, chú ý method descriptor, class/package names, visibility và class file version.

### 19.5. Class loading log

Với JDK hỗ trợ unified logging:

~~~bash
java -Xlog:class+load=info -jar application.jar
~~~

Ở application server, có thể cần dùng logging/management tooling riêng vì nhiều class loader cùng tham gia. Không bật log quá chi tiết trên production lâu dài nếu chưa đánh giá chi phí và bảo mật.

### 19.6. jdeps

~~~bash
jdeps --recursive --class-path "lib/*" app.jar
~~~

`jdeps` phân tích tham chiếu tĩnh, không thấy mọi SPI/reflection/dynamic plugin load. Cần kết hợp với runtime probes và kiểm tra artifact.

## 20. Dependency ownership inventory

Một bảng quản lý migration:

| Thành phần | API được dùng | Runtime provider | Version owner | Nơi nạp |
|---|---|---|---|---|
| Servlet | Jakarta Servlet API | External container | Server team | Server/app loader |
| ORM | Persistence API | ORM/provider | Framework/platform | Server/app |
| JDBC | `java.sql` | Vendor driver | Platform/app | Server/app module |
| Logging | SLF4J API | Logging backend | Host/app | Shared/app |
| Plugin SDK | Extension API | Host services | Plugin host vendor | Parent/shared |
| Plugin helper | Third-party API | Plugin-local JAR | Plugin owner | Plugin loader |
| Java modules | Java SE/JDK | Runtime image | JDK/platform owner | JVM modules |

Với mỗi hàng, bổ sung:

- Current và target versions.
- JDK baseline.
- Cấu hình build scope.
- Có đóng trong WAR/JAR/plugin archive không.
- Đường dẫn JAR và class loader tại runtime.
- Provider bootstrap mechanism.
- Consumer và phụ thuộc bắc cầu.
- Test liên quan.
- Chủ sở hữu, ticket và rollback.

### 20.1. Vì sao ownership quan trọng?

Thay một shared library của server có thể ảnh hưởng nhiều ứng dụng; nâng plugin-local library chỉ ảnh hưởng plugin nếu isolation đúng. Nếu owner không rõ, mỗi team có thể thêm một bản JAR “để sửa lỗi”, tạo duplicate types và version skew.

## 21. Quy trình migration an toàn

~~~mermaid
flowchart TD
    A["Inventory JDK, server, plugin host"] --> B["Tách API, provider và owner"]
    B --> C["Đối chiếu version/namespace/JDK baseline"]
    C --> D["Chỉnh scopes và packaging"]
    D --> E["Build artifact sạch"]
    E --> F["Kiểm tra class origins/SPI metadata"]
    F --> G["Chạy integration trên host mục tiêu"]
    G --> H{"Đạt tất cả kịch bản?"}
    H -->|Có| I["Canary, monitoring, rollback plan"]
    H -->|Không| J["Điều tra loader, linkage, provider, behavior"]
    J --> C
~~~

### Bước 1 — Chụp baseline

Ghi JDK vendor/version, server/plugin host version, module list, provider list, JVM flags và artifact checksum. Thu thập lỗi/metrics, đặc biệt từ chức năng plugin ít dùng.

### Bước 2 — Liệt kê API và runtime

Phân loại mỗi dependency thành app-owned, server-owned, plugin-owned, shared API, Java SE/JDK, build/test-only. Xác định ai có quyền nâng version.

### Bước 3 — Chọn tổ hợp được hỗ trợ

Đối chiếu compatibility matrix của:

- JDK và server.
- Framework và Servlet/Jakarta generation.
- Plugin host và SDK.
- ORM, validation, logging, driver/providers.
- Java agents và native libraries.
- Bytecode target của ứng dụng/plugin.

### Bước 4 — Điều chỉnh scopes

Đảm bảo provided/compileOnly chỉ dùng khi host thực sự cấp đúng API. Đưa runtime implementation vào artifact standalone khi cần. Không để duplicate API JAR trong plugin nếu host quản lý shared SDK.

### Bước 5 — Build và inspect

Build từ workspace sạch, kiểm tra JAR/WAR/plugin package, service descriptors và generated classes. Kiểm tra binary names bằng `javap`, dependency conflicts bằng Maven/Gradle reports.

### Bước 6 — Test trên host mục tiêu

Chạy **artifact đã đóng gói** trong server/container/plugin host thực. Kích hoạt HTTP/DB/transaction/logger/provider/plugin callback. Nếu plugin hỗ trợ reload, test cả stop/unload/load.

### Bước 7 — Test consumer cũ

Nếu sản phẩm công bố binary compatibility, thử plugin hoặc application đã compile với API cũ mà không compile lại. Không chỉ thử source đã nâng cùng host mới.

### Bước 8 — Canary và rollback

Theo dõi:

- Deploy/startup errors.
- Linkage và class loading exceptions.
- Provider discovery failures.
- HTTP error rate.
- Database/transaction failures.
- Plugin callback latency/errors.
- Memory/thread/resource leaks sau reload.

Rollback có thể phải hoàn nguyên cả app artifact **và** server modules/plugin SDK; chỉ quay lại WAR cũ có thể không đủ nếu host đã nâng không tương thích.

## 22. Tình huống tổng hợp: từ WAR trên server cũ sang host mới

Giả sử một hệ thống ban đầu:

- Chạy JDK 8.
- Deploy WAR lên container dùng `javax.servlet`.
- Dùng ORM/validation providers do server cấp.
- Có plugin tự đóng gói host SDK.
- Có JDBC driver trong server module.
- Định kỳ reload plugin bằng giao diện quản trị.

Nhóm muốn chuyển sang JDK mới và server thuộc thế hệ Jakarta.

**Các vấn đề có thể xuất hiện:**

1. WAR cũ còn binary reference tới `javax.servlet`.
2. Framework mới dùng `jakarta.servlet` nhưng vài filter cũ chưa chuyển.
3. `provided` khiến local build đạt nhưng server cung cấp API generation khác.
4. Plugin đóng hai phiên bản host SDK, phát sinh class identity conflict.
5. JDBC driver bị chuyển khỏi server module mà không thêm vào runtime.
6. Plugin service descriptor biến mất khi shading.
7. Plugin không dọn worker thread khi reload dẫn đến classloader leak.
8. Custom runtime image thiếu module mà extension cần.

**Giải pháp theo tầng:**

- Xác định generation Servlet API/server và cập nhật cả WAR, framework, filters.
- Căn JPA/validation providers với server hoặc chuyển chúng sang app-owned nếu deployment mới yêu cầu.
- Kiểm tra JDBC datasource/driver ownership.
- Loại duplicate host SDK khỏi plugin theo hợp đồng host.
- Xem `META-INF/services` trong plugin artifact cuối cùng.
- Chạy plugin lifecycle test, đặc biệt reload.
- Kiểm tra JPMS/module list, class origins và bytecode target.
- Rollout canary với rollback cả host và ứng dụng khi cần.

Ở đây, **một lỗi thiếu class** và **một lỗi class trùng** cần hai hướng sửa ngược nhau. Không thể dùng chiến lược “thêm nhiều JAR” cho mọi trường hợp.

## 23. Những sai lầm thường gặp

### 23.1. “Compile được tức là server có dependency”

Sai. Compile dependency có thể không nằm ở host runtime.

### 23.2. “provided và compileOnly nghĩa là không cần library”

Sai. Chúng biểu thị library được kỳ vọng do bên khác cung cấp hoặc chỉ cần để compile.

### 23.3. “Đưa SDK host vào plugin sẽ chắc ăn”

Có thể tạo duplicate defining loaders và phá binary type identity.

### 23.4. “Một plugin dùng child-first hay parent-first đều như nhau”

Sai. Delegation policy quyết định thư viện nào thắng và class nào được chia sẻ.

### 23.5. “Có provider class nghĩa là ServiceLoader thấy nó”

Sai. Service metadata, classloader/module resolution và descriptor phải đúng.

### 23.6. “Mọi javax đều chuyển thành jakarta”

Sai. Java SE vẫn có nhiều `javax.*`. Enterprise namespace migration phải theo từng API/specification.

### 23.7. “Một smoke test chứng minh plugin tương thích”

Sai. Callback, async threads, resource cleanup và plugin reload có thể lỗi ở runtime.

### 23.8. “Thêm --add-opens giải quyết mọi lỗi server”

Sai. Module openness khác API availability, linkage và provider discovery.

### 23.9. “Shading luôn tách dependency an toàn”

Không đúng nếu public API types, service descriptors, reflection strings hoặc resources vẫn dùng tên cũ.

### 23.10. “JDK nâng được thì application server chắc chắn hỗ trợ”

Sai. Server/host có compatibility matrix và dependency/tooling riêng.

### 23.11. “BOM chứa mọi implementation”

Sai. BOM/platform thường điều phối version, không tự động thêm mọi runtime dependency.

### 23.12. “Chỉ cần rollback ứng dụng, không cần host”

Không chắc. Nếu host API/provider đã thay đổi, app cũ có thể vẫn không chạy; rollback phải căn theo topology thực.

## 24. Mẫu hồ sơ server-managed dependency

~~~yaml
component: servlet-api
api_generation: "Jakarta Servlet generation used by application"
runtime_provider: "External container"
version_owner: "Platform team"
compile_scope: "provided"
artifact_bundled: false
server_version: "Recorded production version"
jdk_runtime: "Approved JDK"
verification:
  - "Inspect WAR contents"
  - "Inspect server module/API generation"
  - "Deploy and call servlet/filter endpoints"
migration_state: "PENDING_REVIEW"
~~~

Các chuỗi version trong mẫu là placeholder; ở dự án thật cần thay bằng giá trị và bằng chứng cụ thể. Không ghi credential, token hoặc cấu hình nhạy cảm vào tài liệu có phạm vi đọc rộng.

## 25. Checklist hoàn tất

### Ownership và nền tảng

- [ ] Đã ghi JDK, server, plugin host và framework versions.
- [ ] Đã phân biệt Java SE API với enterprise/platform API.
- [ ] Đã xác định ai sở hữu version mỗi dependency.
- [ ] Đã đối chiếu compatibility matrix với JDK đích.
- [ ] Đã xác định deployment là WAR, embedded JAR hay plugin archive.

### Dependency, class loader và packaging

- [ ] Đã kiểm tra Maven/Gradle scopes đúng mô hình.
- [ ] Đã so sánh compile, runtime, test và server dependency inventories.
- [ ] Đã tránh duplicate host API trong plugin nếu host không cho phép.
- [ ] Đã kiểm tra binary class names và method descriptors.
- [ ] Đã xác minh class loader origin của các type quan trọng.
- [ ] Đã kiểm tra SPI, service descriptor và module metadata.
- [ ] Đã kiểm tra shading/minimization không loại provider resources.
- [ ] Đã kiểm tra JPMS và custom runtime image khi liên quan.
- [ ] Đã xác minh javax/jakarta generation với server.

### Runtime và vận hành

- [ ] Đã deploy đúng artifact trên host/JDK mục tiêu.
- [ ] Đã test HTTP, persistence, datasource, transaction, logging nếu dùng.
- [ ] Đã kích hoạt plugin extension points và callbacks thật.
- [ ] Đã test reload/unload và resource cleanup nếu được hỗ trợ.
- [ ] Đã kiểm tra TCCL ở background threads khi có SPI.
- [ ] Đã chạy binary plugin cũ nếu host cam kết compatibility.
- [ ] Đã ghi classloading/linkage errors, metrics và checksum.
- [ ] Đã chuẩn bị rollout/rollback cho cả app và host.

## Kết luận

Nền tảng ứng dụng, plugin và dependency do máy chủ cung cấp tạo ra một lớp tương thích vượt ra ngoài source Java. **Compile được không có nghĩa deploy được**; một JAR không nằm trong artifact vẫn có thể có mặt do server cấp; và một class name giống nhau không đảm bảo cùng kiểu khi được định nghĩa bởi các class loader khác nhau.

Khi nâng JDK, framework hoặc host, cần xác định **API nào được dùng, implementation nào thực thi, ai quản lý version, class loader nào nạp class và provider được bootstrap ra sao**. Kiểm chứng phải thực hiện trên WAR/JAR/plugin archive cuối cùng, với server/plugin host và JDK đích, bao gồm cả lifecycle và các đường chạy tích hợp. Chỉ khi những ranh giới này rõ ràng, việc nâng cấp mới tránh được lỗi thiếu provider, trùng dependency, sai namespace và thay đổi hành vi khó phát hiện.

