# Tên package riêng và tránh chiếm nhầm lớp hoặc tài nguyên của ứng dụng

Khi viết Java agent, bytecode được chèn vào một lớp ứng dụng thường cần gọi **helper** để ghi trace, đo thời gian hoặc đếm sự kiện. Helper có thể nằm trong agent JAR, trong một JAR được thêm vào bootstrap class loader search, hoặc trong một class loader khác. Nếu agent dùng tên package quá chung, nhét các thư viện của mình vào đường tìm kiếm lớp của ứng dụng hoặc đặt resource trùng đường dẫn, JVM có thể **nạp đúng tên nhưng sai phiên bản/sai nguồn**, gây lỗi linkage, sai cấu hình và hành vi rất khó chẩn đoán.

**Nguyên tắc thiết kế:** đặt các class/helper của agent trong một **namespace riêng, ổn định, khó đụng tên**, cô lập dependency của agent, giữ JAR được đưa vào bootstrap thật nhỏ và kiểm tra cả **class names lẫn resource names**. Một package riêng giúp giảm collision nhưng **không tự tạo security boundary** và không tự giải quyết mọi vấn đề class loader/module.

Bài này thuộc nhóm **Class loader và helper** của Java Instrumentation. Bạn sẽ hiểu chính xác thế nào là “chiếm nhầm” class/resource, vì sao delegation làm xảy ra lỗi, cách tổ chức JAR/relocate dependency, cách chọn vị trí đặt helper và cách kiểm chứng bằng ví dụ Java 17+.

## 1. Phân biệt ba khái niệm: tên lớp, identity của lớp và resource

### 1.1. Binary class name không phải toàn bộ identity

Trong Java, một lớp thường có binary name như:

```text
com.example.payment.PaymentService
io.mycompany.telemetry.agent.internal.ProbeBridge
org.example.codec.JsonCodec
```

Trong class file, các tên đó thường xuất hiện dưới dạng internal name với dấu `/`, chẳng hạn `io/mycompany/telemetry/agent/internal/ProbeBridge`. Với các lớp thông thường, **identity trong JVM còn phụ thuộc defining class loader**, không chỉ chuỗi tên.

```text
(binary name = "com.example.Plugin")
      +
(defining class loader = Loader-A)
      = Class A

(binary name = "com.example.Plugin")
      +
(defining class loader = Loader-B)
      = Class B (khác Class A)
```

Hai `Class<?>` khác nhau dù có thể cùng tên ký tự. Việc ép kiểu hoặc truyền instance qua ranh giới loader có thể gây `ClassCastException`. Ngược lại, nếu loader **ủy quyền lên parent** và nhận class có cùng tên đã được parent định nghĩa, nó có thể không nạp class cùng tên trong JAR của chính mình. Đây là một cách xảy ra lỗi **nạp nhầm class**.

### 1.2. Resource chỉ được tìm bằng đường dẫn, không phải Java type identity

Resource có tên kiểu:

```text
application.properties
logback.xml
META-INF/services/com.example.spi.ParserProvider
com/example/payment/config.json
io/mycompany/telemetry/agent/internal/agent.properties
```

`ClassLoader.getResource(name)` hoặc `getResourceAsStream(name)` tra resource theo **đường dẫn `/`-separated**, với thứ tự/khả năng tìm kiếm theo loader/module. Resource không có kiểu Java hay kiểm tra rằng “file này thuộc đúng JAR của helper”.

Hai JAR có thể cùng chứa `application.properties`; API trả về **một resource phù hợp với đường tìm kiếm** chứ không biết file nào chứa cấu hình “đúng ý” của bạn. Với cơ chế parent-first phổ biến, resource từ parent có thể thắng resource của child. Trong môi trường named module, quy tắc encapsulation và thứ tự tìm có thể khác; không nên đoán tuyệt đối từ classpath.

### 1.3. “Trùng package” không đồng nhất với “đã chiếm nhầm”

| Hiện tượng | Ví dụ | Điều có thể xảy ra |
|---|---|---|
| Trùng **binary name** | App và agent đều có `com.example.util.Helper` | Loader dùng bản app hoặc bản agent ngoài dự kiến |
| Trùng **package**, class khác tên | App có `com.example.util.A`, agent có `com.example.util.B` | Split package, sealing, module và package-private access có thể gây vấn đề; không phải lúc nào cũng lỗi ngay |
| Trùng **resource path** | Cả hai có `config.properties` | Helper đọc nhầm config của app hoặc ngược lại |
| Trùng **service descriptor** | Cả hai có `META-INF/services/com.example.Plugin` | Service provider discovery có thể thấy provider ngoài dự định |
| Trùng **dependency binary name** | App và agent chứa hai phiên bản `org.some.library.Parser` | `NoSuchMethodError`/`LinkageError`, ABI khác nhau |
| Hai class cùng tên nhưng do hai loaders khác nhau định nghĩa | Hai plugin có `com.example.Model` | Hai class identities riêng; cast/linkage giữa hai bên có thể lỗi |
| Helper không được target loader nhìn thấy | Bytecode app gọi `io.agent.internal.ProbeBridge` nhưng loader không thấy | `NoClassDefFoundError`/`ClassNotFoundException` hoặc lỗi truy cập |
| Resource trùng tên đơn giản nhưng ở **namespace riêng khác nhau** | `app/config.properties` và `agent/internal/config.properties` | Thông thường tránh đụng path, dễ kiểm chứng nguồn |

**Không có quy tắc “package name càng dài thì JVM càng ưu tiên”.** Tên duy nhất giúp tránh collision; classloader delegation và module visibility quyết định class nào thực sự được resolve.

## 2. Parent-first delegation và lý do lấy nhầm class

`ClassLoader.loadClass` mặc định kiểm tra class đã load, sau đó thường hỏi **parent** trước, rồi mới gọi `findClass` ở loader hiện tại. Các class loader tùy chỉnh có thể thay đổi chính sách này, nhưng parent-first là mô hình quan trọng cần hiểu.

```text
          Child Loader
          /         \
      loadClass     getResource
         |              |
         v              v
   hỏi Parent trước   hỏi Parent trước
         |              |
   nếu không tìm       nếu không tìm
         v              v
   tìm trong child    tìm trong child
```

Giả sử:

```text
application.jar:
  com/acme/common/Codec.class         -> phiên bản APP
  com/acme/common/config.properties   -> source=APP

agent-helper.jar:
  com/acme/common/Codec.class         -> phiên bản AGENT
  com/acme/common/config.properties   -> source=AGENT
```

Nếu loader đang cố tìm `com.acme.common.Codec` có parent nhìn thấy bản APP, lookup thông thường có thể trả về **APP** ngay cả khi child mang file class AGENT. Cũng vậy, `getResource("com/acme/common/config.properties")` có thể trả resource APP.

**Hệ quả đối với agent:** Helper biên dịch với dependency phiên bản agent nhưng runtime lại resolve dependency của ứng dụng. Nếu method mong đợi không có, bạn có thể gặp `NoSuchMethodError`. Nếu kiểu khác nghĩa, lỗi có thể còn nguy hiểm hơn vì chạy được nhưng sai behavior.

### 2.1. Child-first không phải phương thuốc mặc định

Một số plugin framework, application server hoặc module system dùng chiến lược child-first hay chính sách khác. Khi đó trường hợp đảo ngược có thể xảy ra: mã ứng dụng vô tình nhận class/resource của agent nếu agent được đưa vào vùng tìm kiếm của nó.

Do đó, không xây giải pháp dựa vào “agent chắc chắn đi trước” hay “app chắc chắn đi trước”. Hãy thiết kế để **không có tên trùng** ngay từ đầu, rồi kiểm tra classloader thực tế khi triển khai.

### 2.2. Java package-private và runtime package

Cùng phần prefix package không bảo đảm hai class được xem là cùng **runtime package** nếu chúng được định nghĩa bởi các loaders khác nhau (và trong bối cảnh module hiện đại còn có các quy tắc runtime module). Vì thế một helper cố đặt trong package của ứng dụng để truy cập member package-private có thể gặp `IllegalAccessError`. Đổi tên package một cách tùy tiện cũng có thể phá quyền truy cập, package sealing hoặc module boundary.

**Không dùng trick “đặt helper cùng package với app” để vượt cơ chế truy cập.** Chọn API/bridge hợp lệ, điều chỉnh module reads/opens/exports khi được phép và kiểm tra class-loader identity.

## 3. Rủi ro đặc biệt khi append JAR vào bootstrap class loader search

Java Instrumentation cung cấp:

```java
void appendToBootstrapClassLoaderSearch(java.util.jar.JarFile jarfile);
void appendToSystemClassLoaderSearch(java.util.jar.JarFile jarfile);
```

Đây là **API được gọi trên đối tượng `Instrumentation` của agent**, không phải lệnh JVM tự động thực hiện với mọi agent JAR. Đoạn sử dụng bên dưới chỉ minh họa, chưa phải agent đầy đủ:

```java
// inst là Instrumentation đã nhận qua premain/agentmain:
try (java.util.jar.JarFile jar =
        new java.util.jar.JarFile("agent-bootstrap-helper.jar")) {
    inst.appendToBootstrapClassLoaderSearch(jar);
}
```

**Lưu ý về vòng đời:** Với runtime thật, đừng giả định đóng `JarFile` ngay sau append luôn phù hợp với mọi triển khai/cách giữ resource. Quản lý `JarFile` và vòng đời JAR theo tài liệu/kiểm thử JVM sử dụng; ở đây mã chỉ giới thiệu chữ ký API, **không khuyến nghị copy-paste đoạn `try-with-resources` như mẫu triển khai production**.

### 3.1. Vì sao append bootstrap dễ “chiếm nhầm”?

Bootstrap là parent cao trong nhiều chuỗi delegation. Nếu JAR được append chứa class/resource trùng tên với thứ mà loader phía dưới định tìm, một lookup bị miss ở lớp cha có thể tìm thấy class/resource từ JAR append. Javadoc `Instrumentation.appendToBootstrapClassLoaderSearch` cảnh báo **chính xác** không nên đưa vào JAR các class/resources ngoài những thứ chủ đích thuộc bootstrap instrumentation.

Tài liệu đưa tình huống lớp `C` tham chiếu một accessor không public như `C$1`, nhưng bootstrap append JAR cũng chứa tên `C$1`. Parent delegation có thể khiến `C$1` được định nghĩa bởi bootstrap thay vì loader của `C`, gây **`IllegalAccessError`**. Một cách tránh là dùng **tên package duy nhất** cho các class của instrumentation.

```text
App Loader L định nghĩa C
  C -> cần C$1 (accessor không public)
        |
        v
     delegate lên bootstrap
        |
    bootstrap append JAR cũng chứa C$1
        |
        v
     bootstrap định nghĩa nhầm C$1
        |
        v
     runtime-package/access rules không phù hợp
     -> có thể IllegalAccessError
```

Nếu helper được chuyển vào bootstrap search, hãy cố gắng tạo **JAR riêng tối thiểu**, chỉ chứa các class và resource thật sự cần ở bootstrap. Không đưa toàn bộ agent, dependency phổ biến, root resources, service descriptors và ứng dụng test vào đó chỉ để tiện build.

### 3.2. Append system khác với thêm JAR vào mọi loader

`appendToSystemClassLoaderSearch` thêm JAR vào **đường tìm kiếm của system class loader** khi loader này hỗ trợ cơ chế cần thiết. Nó **không** tự làm mọi custom loader nhìn thấy helper, không đảm bảo named module có quyền truy cập và không thay đổi `java.class.path` system property.

Một class đã bị JVM **ghi nhận lần symbolic reference resolution thất bại** cũng không nhất thiết được “sửa” bằng việc append JAR sau đó: Javadoc cảnh báo những lần resolve tiếp theo của reference đã thất bại phải tiếp tục thất bại theo quy tắc JVMS. Vì thế phải sắp xếp **helper visibility trước khi class được instrument cố gọi helper**, thay vì tin rằng có thể chữa mọi `NoClassDefFoundError` bằng việc append muộn.

### 3.3. Bootstrap không phải nơi chứa tất cả dependencies

Một bootstrap helper tốt thường:

- Có API nhỏ, ổn định, dùng kiểu primitive hoặc kiểu JDK cơ bản.
- Không phụ thuộc class ứng dụng, ORM, Jackson/JSON mapper, logger/HTTP client của app.
- Không kích hoạt class loading hay network I/O khi lần đầu được gọi.
- Không đưa package `java.*`, `jdk.internal.*` hoặc `sun.*` tự tạo vào JAR.
- Không mang tài nguyên chung như `logback.xml`, `application.properties`, `META-INF/services` không liên quan.
- Có cơ chế chẩn đoán và kiểm soát lỗi nhưng tránh đưa mọi dependency vào bootstrap.

**Đây là giảm rủi ro, không phải bảo đảm tuyệt đối.** Named modules, class access, loader delegation khác thường và dependency identity vẫn cần được kiểm tra.

## 4. Đặt package riêng cho helper và namespace tài nguyên

### 4.1. Một quy ước namespace thực tế

Dùng reverse-domain và tên sản phẩm/agent rõ ràng:

```text
Nên:
  io.acme.observability.agent.bootstrap.ProbeBridge
  io.acme.observability.agent.runtime.EventRecorder
  io.acme.observability.agent.internal.BytecodeSupport
  io.acme.observability.agent.shaded.somevendor.Parser

Nên tránh:
  com.common.Helper
  com.example.util.Logger
  org.objectweb.asm.Helper                 (nếu tự định nghĩa class ở namespace thư viện)
  com.myapp.service.AgentHelper            (trùng package của ứng dụng)
  java.lang.AgentBridge                     (package JDK)
```

Chúng là **ví dụ cách đặt tên**, không phải tên cần dùng nguyên văn. Một prefix riêng phải do tổ chức/sản phẩm sở hữu hoặc được quản lý nội bộ, không đoán tên package của app rồi copy.

Nên tách rõ:

1. **Bootstrap bridge**: API nhỏ mà bytecode có thể gọi từ nhiều loaders; đưa vào bootstrap JAR tối thiểu nếu thực sự cần.
2. **Agent runtime**: transformer, configuration, exporter, queue và các thành phần quản lý; giữ nơi classloader phù hợp, không tự đưa hết vào bootstrap.
3. **Shaded dependencies**: thư viện đóng gói với agent và đã relocate khi có nguy cơ trùng class name với ứng dụng.
4. **Agent resources**: cấu hình, service descriptors và resource nghiệp vụ của agent trong path độc nhất.

### 4.2. Resource path cũng phải riêng

Package class riêng chưa đủ nếu JAR chứa resource tên chung.

| Resource nguy hiểm nếu bỏ tại root / path chung | Hướng tổ chức giảm collision |
|---|---|
| `application.properties` | `io/acme/observability/agent/internal/agent.properties` |
| `logback.xml` | Không đóng gói mặc định nếu agent không chủ động dùng một logger config riêng |
| `config.json` | `io/acme/observability/agent/internal/config.json` |
| `schema.json` | `io/acme/observability/agent/internal/schema/v1.json` |
| `META-INF/services/com.some.SPI` | Kiểm soát service descriptors khi build/shade, tránh provider không chủ định |
| `META-INF/native-image/...` | Đảm bảo metadata thuộc đúng namespace/artifact và được cập nhật sau relocation |

Ví dụ truy cập resource private theo path rõ ràng:

```java
// Mã minh họa trong class helper có loader phù hợp:
String name = "io/acme/observability/agent/internal/agent.properties";
ClassLoader loader = ProbeBridge.class.getClassLoader();
java.io.InputStream input = (loader == null)
        ? ClassLoader.getSystemResourceAsStream(name)
        : loader.getResourceAsStream(name);
```

Đoạn này **không phải một chiến lược tổng quát cho bootstrap**: khi `getClassLoader() == null`, `getSystemResourceAsStream` có thể tìm nguồn khác với bootstrap helper và có collision. Đừng mang đoạn minh họa này vào code thật nếu chưa định nghĩa **nguồn resource có thẩm quyền**. Với bootstrap helper, tốt nhất **không cần đọc config riêng trong hot path**; cấu hình nên được chuyển theo hợp đồng API đã kiểm soát hoặc được nạp từ một nguồn tường minh ở tầng agent runtime.

### 4.3. Dấu `/` trong resource APIs thường gây sai

```java
// Resource path từ gốc theo ClassLoader:
loader.getResource("io/acme/agent/internal/agent.properties");

// Class.getResource: bắt đầu bằng "/" là absolute path:
ProbeBridge.class.getResource(
        "/io/acme/agent/internal/agent.properties");

// Nếu KHÔNG có "/", Class.getResource là đường dẫn
// tương đối với package chứa ProbeBridge.
ProbeBridge.class.getResource("agent.properties");
```

Đây là các snippet minh họa; `loader` và `ProbeBridge` phải là các biến/class có thật. Đừng gọi `ClassLoader.getResource("/...")` rồi trông chờ nó luôn tự bỏ dấu `/` như `Class.getResource`: hai API có quy tắc khác nhau.

**Chưa đủ nếu chỉ lấy URL:** cùng path có thể tồn tại trong nhiều JAR. Khi kiểm thử, liệt kê `loader.getResources(name)` và kiểm tra danh sách URLs; riêng khi chạy production, đừng log URL nhạy cảm bừa bãi.

## 5. Dependency relocation/shading và những gì không nên relocate mù quáng

Nếu agent dùng một thư viện cũng phổ biến trong ứng dụng, ví dụ bytecode parser hoặc JSON library, chỉ đổi package **của helper** vẫn có thể chưa đủ. Cả agent và app có thể cần `org.some.library.Parser` ở hai phiên bản khác nhau.

### 5.1. Ba chiến lược cơ bản

| Chiến lược | Ưu điểm | Giới hạn |
|---|---|---|
| **Không bundle** dependency, dựa vào thư viện ứng dụng | JAR nhỏ | Rủi ro ABI/version conflict, không đáng tin với nhiều ứng dụng đích |
| Bundle dependency nhưng **giữ nguyên package** | Đóng gói thuận tiện | Collision khi class loader ưu tiên phiên bản khác hoặc package sealing |
| Bundle và **relocate/shade** dependency vào namespace agent | Giảm binary-name collisions | Phải xử lý reflection, service descriptors, resources, module/manifest và kiểm thử packaging |

Ví dụ ý tưởng relocation:

```text
Trước:
  org/example/parser/Parser.class
  org/example/parser/Tokenizer.class

Sau:
  io/acme/observability/agent/shaded/parser/Parser.class
  io/acme/observability/agent/shaded/parser/Tokenizer.class
```

Đây là **mô tả chiến lược**, không phải lệnh build thực thi. Với Maven Shade, Gradle Shadow hoặc công cụ tương đương, phải cấu hình relocation ở **giai đoạn build artifact**, không sửa tên class trực tiếp trong source rồi mặc định mọi resource/reflection reference đã được cập nhật.

### 5.2. Những điểm relocation thường bỏ sót

- **`META-INF/services/...`**: cả tên descriptor file và tên provider classes bên trong có thể cần transform tương ứng. Nếu không, `ServiceLoader` không tìm provider hoặc tìm sai.
- **Reflection by string**: `Class.forName("org.example.parser.Parser")` có thể không tự sửa nếu tên nằm trong chuỗi không được công cụ relocation hiểu.
- **Config/resource paths**: class đã chuyển package nhưng code vẫn tìm resource ở path cũ, hoặc agent vẫn chứa resource tên chung.
- **JPMS descriptors**: `module-info.class`, `Automatic-Module-Name`, exports/opens/uses/provides phải tương thích với artifact sau build.
- **Serialized class names/JNI/native code**: string-based references và native symbols có thể phụ thuộc tên cũ.
- **Manifest `Premain-Class`/`Agent-Class`**: phải trỏ đúng agent entry point sau khi build; nếu relocation thay tên entry class mà manifest không cập nhật, JVM không thể chạy agent.
- **Signed JAR**: việc sửa nội dung JAR làm chữ ký/digest cũ không còn tương ứng; phải dùng quy trình ký/đóng gói phù hợp, không phát hành artifact có metadata chữ ký sai.
- **Licenses và notice**: bundle thư viện bên thứ ba vẫn có nghĩa vụ license/notice tùy giấy phép.

**Shading không phải biên giới bảo mật.** Nó giảm xung đột tên class, không ngăn code tùy ý truy cập dữ liệu và không tự cung cấp module read/export permission.

## 6. Ví dụ Java 17+ chạy được: một class và một resource bị parent “lấy trước”

Đây là **thí nghiệm class-loader thuần Java**, không cần `-javaagent`. Mục tiêu là quan sát chính xác parent-first lookup để thấy vì sao agent phải dùng package/resource riêng. Để học cơ chế này, ta có hai JAR:

- `app.jar`: định nghĩa `sample.shared.Marker` và một resource chung.
- `helper.jar`: cố ý có **class/resource trùng tên** `sample.shared.Marker`; đồng thời có helper trong namespace riêng `io.workshop.telemetry.agent.internal.Helper` và resource private riêng.

Chương trình `CollisionDemo` dùng hai `URLClassLoader` parent/child tường minh. Thí nghiệm chứng minh tính chất lookup, **không tuyên bố URLClassLoader mô phỏng mọi custom loader, module loader hay bootstrap append trong production**.

### 6.1. Tạo cấu trúc file

```text
loader-lab/
  src-app/
    sample/shared/Marker.java
  resources-app/
    sample/shared/config.properties
  src-helper/
    sample/shared/Marker.java
    io/workshop/telemetry/agent/internal/Helper.java
  resources-helper/
    sample/shared/config.properties
    io/workshop/telemetry/agent/internal/agent.properties
  src-demo/
    CollisionDemo.java
```

Hai file `sample/shared/Marker.java` có cùng tên class nhưng là **hai bản nguồn khác nhau**. Biên dịch riêng để tạo hai JAR, không đặt chúng cạnh nhau trên cùng classpath của `CollisionDemo`.

### 6.2. File `src-app/sample/shared/Marker.java`

```java
package sample.shared;

public final class Marker {
    public static String origin() {
        return "APP";
    }
}
```

### 6.3. File `src-helper/sample/shared/Marker.java`

```java
package sample.shared;

public final class Marker {
    public static String origin() {
        return "AGENT";
    }
}
```

Đây là **collision cố tình tạo ra cho thí nghiệm**. Trong sản phẩm thật, đừng đóng gói `sample.shared.Marker` của helper nếu ứng dụng đã có class cùng tên.

### 6.4. File `src-helper/io/workshop/telemetry/agent/internal/Helper.java`

```java
package io.workshop.telemetry.agent.internal;

public final class Helper {
    public static String origin() {
        return "AGENT_HELPER";
    }
}
```

Class này có namespace agent riêng và **không** nằm trong package `sample.shared` của ứng dụng. Trong loader setup thí nghiệm, child loader có thể định nghĩa nó mà không bị parent lấy nhầm.

### 6.5. Ba file resources

`resources-app/sample/shared/config.properties`:

```properties
origin=APP_RESOURCE
```

`resources-helper/sample/shared/config.properties`:

```properties
origin=AGENT_RESOURCE
```

`resources-helper/io/workshop/telemetry/agent/internal/agent.properties`:

```properties
origin=AGENT_PRIVATE_RESOURCE
```

Hai file đầu có **cùng resource path** trong hai JAR. File thứ ba dùng path dành riêng cho helper. Khi ghi file hãy giữ đúng ký tự `=` và path, tránh đặt nhầm resource trực tiếp ở thư mục root của JAR.

### 6.6. File `src-demo/CollisionDemo.java`

```java
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.Collections;
import java.util.Properties;

public final class CollisionDemo {
    private static String property(ClassLoader loader, String name)
            throws Exception {
        try (InputStream in = loader.getResourceAsStream(name)) {
            if (in == null) {
                return "MISSING";
            }
            Properties p = new Properties();
            p.load(in);
            return p.getProperty("origin", "MISSING");
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("Usage: CollisionDemo <app.jar> <helper.jar>");
            System.exit(2);
        }

        URL appUrl = Path.of(args[0]).toUri().toURL();
        URL helperUrl = Path.of(args[1]).toUri().toURL();

        try (URLClassLoader appLoader = new URLClassLoader(
                     new URL[] {appUrl},
                     ClassLoader.getPlatformClassLoader());
             URLClassLoader helperLoader = new URLClassLoader(
                     new URL[] {helperUrl},
                     appLoader)) {

            // Parent-first: helperLoader yêu cầu class trùng tên,
            // nhưng appLoader đã có thể tìm và định nghĩa class APP.
            Class<?> shared = Class.forName(
                    "sample.shared.Marker", true, helperLoader);
            String sharedOrigin =
                    (String) shared.getMethod("origin").invoke(null);
            System.out.println("SHARED_CLASS=" + sharedOrigin);
            System.out.println(
                    "SHARED_CLASS_FROM_PARENT="
                    + (shared.getClassLoader() == appLoader));

            String commonResource = property(
                    helperLoader, "sample/shared/config.properties");
            System.out.println(
                    "SHARED_RESOURCE=" + commonResource);

            int matches = Collections.list(helperLoader.getResources(
                    "sample/shared/config.properties")).size();
            System.out.println(
                    "SHARED_RESOURCE_MATCHES=" + matches);

            // Namespace riêng: chỉ helper.jar có class này.
            Class<?> helper = Class.forName(
                    "io.workshop.telemetry.agent.internal.Helper",
                    true, helperLoader);
            String helperOrigin =
                    (String) helper.getMethod("origin").invoke(null);
            System.out.println("PRIVATE_CLASS=" + helperOrigin);
            System.out.println(
                    "PRIVATE_CLASS_FROM_CHILD="
                    + (helper.getClassLoader() == helperLoader));

            String privateResource = property(helperLoader,
                    "io/workshop/telemetry/agent/internal/agent.properties");
            System.out.println(
                    "PRIVATE_RESOURCE=" + privateResource);
        }
    }
}
```

**Vì sao dùng platform class loader làm parent của `appLoader`?** Để không vô tình đưa `app.jar` hoặc `helper.jar` vào system classpath. `appLoader` có thể thấy class trong `app.jar`, còn `helperLoader` có `appLoader` làm parent. Đây là mô hình parent-first **được chủ động xây dựng cho kiểm thử**, không phải dự đoán class loader của mọi ứng dụng thật.

**Vì sao dùng reflection?** `CollisionDemo` không compile-time import `sample.shared.Marker` hoặc helper, nên nó có thể được biên dịch độc lập và hỏi chính loader đã cấu hình để xem nguồn class được resolve ở runtime. Cách kiểm tra bằng `getClassLoader() == appLoader/ helperLoader` giúp tránh đoán class source từ tên.

### 6.7. Biên dịch, đóng JAR và chạy trên JDK 17+

Trong shell Bash/macOS/Linux tại `loader-lab`:

```shell
mkdir -p build/app build/helper build/demo

javac -d build/app src-app/sample/shared/Marker.java
javac -d build/helper \
  src-helper/sample/shared/Marker.java \
  src-helper/io/workshop/telemetry/agent/internal/Helper.java
javac -d build/demo src-demo/CollisionDemo.java

cp -R resources-app/. build/app/
cp -R resources-helper/. build/helper/

jar --create --file app.jar -C build/app .
jar --create --file helper.jar -C build/helper .

java -cp build/demo CollisionDemo app.jar helper.jar
```

Nếu chạy PowerShell trên Windows, tạo thư mục và copy resources bằng các lệnh tương đương:

```powershell
New-Item -ItemType Directory -Force build/app, build/helper, build/demo | Out-Null
javac -d build/app src-app/sample/shared/Marker.java
javac -d build/helper src-helper/sample/shared/Marker.java src-helper/io/workshop/telemetry/agent/internal/Helper.java
javac -d build/demo src-demo/CollisionDemo.java
Copy-Item -Path "resources-app/*" -Destination "build/app" -Recurse -Force
Copy-Item -Path "resources-helper/*" -Destination "build/helper" -Recurse -Force
jar --create --file app.jar -C build/app .
jar --create --file helper.jar -C build/helper .
java -cp build/demo CollisionDemo app.jar helper.jar
```

Cách chạy trên Windows cần PowerShell với JDK tools có trong `PATH`. Các chuỗi class/resource ở đây không phụ thuộc dấu `\` của Windows vì tên trong JAR luôn dùng `/`.

**Stdout dự kiến với đúng hai JAR và class loader của demo:**

```text
SHARED_CLASS=APP
SHARED_CLASS_FROM_PARENT=true
SHARED_RESOURCE=APP_RESOURCE
SHARED_RESOURCE_MATCHES=2
PRIVATE_CLASS=AGENT_HELPER
PRIVATE_CLASS_FROM_CHILD=true
PRIVATE_RESOURCE=AGENT_PRIVATE_RESOURCE
```

Giải thích:

1. `SHARED_CLASS=APP`: `helperLoader` hỏi parent trước; parent `appLoader` tìm được bản `sample.shared.Marker` trong `app.jar`.
2. `SHARED_CLASS_FROM_PARENT=true`: loader thực sự **định nghĩa** class là `appLoader`, không phải `helperLoader`.
3. `SHARED_RESOURCE=APP_RESOURCE`: resource path trùng tên và `getResourceAsStream` lấy bản từ parent theo lookup mặc định của `URLClassLoader` trong bài test.
4. `SHARED_RESOURCE_MATCHES=2`: `getResources` liệt kê cả bản của app và helper trong mô hình hai JAR này; lấy **resource đầu tiên** không có nghĩa resource đó thuộc helper.
5. `PRIVATE_CLASS=AGENT_HELPER` và `PRIVATE_CLASS_FROM_CHILD=true`: class có package riêng được định nghĩa từ `helper.jar` bởi child.
6. `PRIVATE_RESOURCE=AGENT_PRIVATE_RESOURCE`: resource private của helper có path riêng nên được tìm đúng trong môi trường test.

**Tính giới hạn của output:** Kết quả trên là thí nghiệm kiểm soát với hai `URLClassLoader`, parent-first, không có JAR thứ ba và resources chưa bị module encapsulation. Trong một framework với child-first loader hoặc named modules, cách resolve có thể khác. Mục tiêu là chứng minh **đặt trùng tên khiến kết quả phụ thuộc loader**, không phải khẳng định JVM luôn ưu tiên app.

### 6.8. Kiểm chứng nội dung JAR và thứ tự resource

```shell
jar tf app.jar
jar tf helper.jar
```

Hai JAR phải cùng có `sample/shared/Marker.class` và `sample/shared/config.properties`. `helper.jar` có thêm `io/workshop/telemetry/agent/internal/Helper.class` và `io/workshop/telemetry/agent/internal/agent.properties`.

Để debug nâng cao trên HotSpot, có thể dùng `-Xlog:class+load=info` khi chạy Java 17+, rồi lọc các dòng class thuộc namespace mẫu để xem nguồn:

```shell
java -Xlog:class+load=info -cp build/demo \
  CollisionDemo app.jar helper.jar
```

Lệnh này in **nhiều log JVM hơn** stdout dự kiến, nên đừng so khớp output toàn bộ theo dòng; tập trung vào các dòng `SHARED_*`, `PRIVATE_*` và nguồn load class. `-Xlog:class+load` là chẩn đoán của HotSpot/JVM hỗ trợ unified logging, không bắt buộc mọi triển khai Java đều có cùng thông điệp.

## 7. Liên hệ trực tiếp với bytecode instrumentation

Giả sử transformer chèn instruction:

```text
invokestatic io/acme/observability/agent/bootstrap/ProbeBridge.onEnter (I)V
```

Đây là **ký pháp bytecode minh họa**, không phải source Java biên dịch độc lập. JVM cần resolve đúng `ProbeBridge` từ ngữ cảnh liên kết của class đã được instrument. Có ba câu hỏi không thể bỏ qua:

1. **Class nào sẽ resolve helper?** Nó được định nghĩa bởi loader nào? Class loader của nó có nhìn thấy bridge package không?
2. **Nếu helper có dependencies, loader tương ứng sẽ resolve chúng ở đâu?** Có thể vô tình lấy nhầm bản của ứng dụng không?
3. **Nếu helper đọc resource/config, resource ấy nằm ở đâu?** Có thể lấy nhầm file cùng tên từ parent, classpath hoặc module khác không?

### 7.1. Mẫu kiến trúc bridge tối thiểu

```text
Target class: com.app.OrderService
  |
  | bytecode call (method ID, timestamp, outcome)
  v
io.acme.observability.agent.bootstrap.ProbeBridge
  - ít method public static
  - không phụ thuộc class ứng dụng
  - chỉ kiểu primitive/JDK tối thiểu
  |
  | chuyển dữ liệu đã giới hạn qua giao diện ổn định
  v
io.acme.observability.agent.runtime.Recorder
  - queue/batching/exporter
  - agent-specific class loader/context
  - dependencies đã cô lập
```

Không phải bootstrap bridge tự nhiên có quyền gọi `Recorder` trong mọi loader: cần thiết kế visibility/registration rõ ràng và kiểm tra trước khi instrument target. Với named module, ngoài visibility của class loader còn có **module reads/exports/opens**; `Instrumentation.redefineModule` có thể bổ sung quan hệ khi được hỗ trợ, không phải giải pháp thay thế cho class binary-name correctness.

### 7.2. Nên exclude những class nào khỏi transformer?

- Package bootstrap/runtime helper của chính agent, để tránh helper tự bị instrument rồi lặp lại probe.
- Dependencies của exporter/logger mà helper gọi, nếu instrument sẽ gây vòng lặp/overhead.
- Các lớp JDK và class-loader internals không thuộc phạm vi quan sát, khi can thiệp có thể gây lỗi bootstrap/linkage.
- Class thuộc package đã được biết có nguy cơ xung đột với agent hoặc có chính sách riêng.

Filter class name không phải toàn bộ cơ chế bảo vệ. Khi nhiều loaders định nghĩa cùng binary name, transformer cần thêm **loader identity/module/code source và chính sách target**, không dùng `className` duy nhất để quyết định mọi thao tác.

## 8. Tài nguyên và ServiceLoader: collision không chỉ ở file .properties

### 8.1. `META-INF/services`

Java SPI/provider discovery có thể tra `META-INF/services/<service binary name>`. Khi agent bundle service providers và app cũng có providers tương tự, thứ tự và ngữ cảnh class loader có thể ảnh hưởng provider nào được phát hiện. Việc shading một class provider mà không cập nhật descriptor có thể dẫn tới `ServiceConfigurationError`.

Ví dụ:

```text
META-INF/services/com.example.spi.Parser
```

File bên trong chứa tên binary class provider, không phải path tới jar. Nếu provider được relocate, cả **tên class trong file** và có thể **tên service descriptor** phải tương ứng với cách dịch package/ABI. Không gộp bừa hai descriptor chỉ để “giữ hết providers”: có thể làm agent nhìn thấy provider không được phê duyệt hoặc app dùng nhầm SPI.

Một số cách gọi `ServiceLoader.load(service)` dùng **thread context class loader**; khi yêu cầu chọn nguồn cụ thể, hãy dùng overload có loader rõ ràng nếu phù hợp:

```java
// Snippet minh họa, ServiceType và desiredLoader chưa định nghĩa:
java.util.ServiceLoader<ServiceType> providers =
        java.util.ServiceLoader.load(ServiceType.class, desiredLoader);
```

Không kết luận rằng TCCL luôn là loader của agent: trong thread ứng dụng/framework nó có thể là loader của app. Cũng không tự thay TCCL toàn cục trong probe vì có thể ảnh hưởng thư viện khác.

### 8.2. Root logging resources và configuration discovery

Các tên như `log4j2.xml`, `logback.xml`, `application.yml` hay `META-INF/services/...` thường được thư viện dò tự động. Đóng gói một bản config vô tình trong agent JAR có thể tác động đến behavior của ứng dụng nếu jar xuất hiện trong đường tìm kiếm mà app dùng, ngay cả khi **không có class nào trùng tên**.

Cách giảm rủi ro: tránh bundle các config root-level không cần thiết; chỉ package resource private trong namespace agent; thiết kế đường đọc configuration tường minh, không cho logger của agent tự chọn file cấu hình application ngoài ý muốn.

### 8.3. Named modules và resource encapsulation

Trong hệ JPMS, resource trong named module có thể bị encapsulate; `ClassLoader.getResource`/`getResources` không nhất thiết thấy resource package-private trừ khi package được mở phù hợp. `Module.getResourceAsStream` và `Class.getResource` có quy tắc khác đôi chút về phạm vi truy cập. Vì vậy, nếu một resource “có trong JAR nhưng bị báo MISSING”, phải xem **module, package opens, loader và path**, không chỉ xem `jar tf`.

## 9. Kỹ thuật kiểm tra trên agent thật

### 9.1. Kiểm tra binary class thực sự được resolve

```java
// Snippet chẩn đoán; clazz là Class<?> có thật:
ClassLoader loader = clazz.getClassLoader();
String binaryName = clazz.getName();

java.security.ProtectionDomain pd = clazz.getProtectionDomain();
java.security.CodeSource cs = pd == null ? null : pd.getCodeSource();
java.net.URL location = cs == null ? null : cs.getLocation();
```

- `clazz.getClassLoader() == null` thường cho biết class do bootstrap loader định nghĩa.
- `clazz.getName()` cho **binary name**, nhưng không đủ để phân biệt hai class cùng tên.
- `CodeSource.getLocation()` có thể hỗ trợ tìm source JAR; với bootstrap/generated classes hoặc chính sách khác, **có thể null**. Không biến URL đó thành dấu xác thực nguồn duy nhất.
- Nếu logging trong transformer, tránh gọi reflection/lazy class loading sâu ngay trong callback.

Đối với transformer, tham số `loader` và `module` của callback Java 9+ giúp nhận diện ngữ cảnh target. Nhưng `loader == null` không nghĩa class “là của agent”; nó thường nói về bootstrap. Không đoán owner từ một tham số đơn lẻ.

### 9.2. Liệt kê resource collisions

```java
// Snippet minh họa trong đoạn method có loader xác định:
java.util.Enumeration<java.net.URL> found =
        loader.getResources("sample/shared/config.properties");

while (found.hasMoreElements()) {
    System.out.println(found.nextElement());
}
```

Trong test có thể in URL, nhưng log production cần redaction vì đường dẫn deployment có thể chứa chi tiết nội bộ. Với named modules, kết quả có thể bị giới hạn bởi quy tắc encapsulation, nên một resource không xuất hiện trong list không nhất thiết vắng mặt trong mọi cách truy cập khác.

### 9.3. Quét artifact trước khi publish

Trước phát hành agent:

```shell
jar tf agent.jar
jar tf bootstrap-helper.jar
```

Kiểm tra bằng build script/CI (không chỉ review bằng mắt):

- Không có class trong package của ứng dụng trừ trường hợp đã thiết kế rõ.
- Không có `com/common`, `org/example/util` hoặc namespace thư viện không được relocate ngoài ý muốn.
- Bootstrap JAR chỉ chứa **bootstrap bridge cần thiết**, không kèm cả exporter/JSON/logger dependencies.
- Resource root-level và `META-INF/services` đúng danh sách allowlist.
- Manifest `Premain-Class`/`Agent-Class` đúng binary name và đúng class entry.
- Nếu shade, verify names/relocated paths, service descriptors và license notices.
- Nếu bundle multi-release JAR, kiểm tra `META-INF/versions/*` và manifest `Multi-Release: true`, tránh bỏ sót class collision trong thư mục versioned.
- Kiểm tra runtime với **đúng JDK, app class loader, framework, module setup**; không chỉ thử bằng unit test trên system classpath.

## 10. Các lỗi thường gặp và thứ tự chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| `NoSuchMethodError` sau khi thêm agent | Runtime chọn class trùng tên nhưng API version khác | In binary name, defining loader, CodeSource, `javap -p -s` của hai artifact |
| `ClassCastException: X cannot be cast to X` | Hai định nghĩa cùng tên nhưng khác loader | So `clazz.getClassLoader()`/module, phân tích đường truyền object |
| `IllegalAccessError` khi gọi accessor/helper | Runtime package/loader không phù hợp; bootstrap có thể chiếm nhầm class | Kiểm tra bootstrap append jar, package-private class, loader identity |
| `NoClassDefFoundError` cho `ProbeBridge` | Loader của target không thấy helper, hoặc reference resolution đã fail trước đó | Kiểm tra jar đã append **trước khi sử dụng**, loader/module visibility, Javadoc cache thất bại |
| `SecurityException` khi load package | Có thể vi phạm sealed package hay quy tắc cấm tên package đặc biệt | Kiểm manifest `Sealed`, package definition, nơi class được load |
| Agent đọc config của app | Trùng resource path và loader parent-first | `getResources(name)`, URLs và artifact thực |
| App dùng sai logging config | Agent đóng gói root resource chung | Quét `jar tf` và classloader lookup; đưa config vào namespace riêng |
| `ServiceConfigurationError` sau shading | Service descriptor/provider name không tương ứng | Kiểm `META-INF/services`, relocated binary names và chosen loader |
| Bootstrap helper không gọi được app class | Bootstrap không nhìn thấy child classes | Tách bridge và runtime; không thêm dependency app vào bootstrap |
| System append rồi target vẫn không thấy helper | Target loader/module visibility khác; previously failed resolution | Kiểm đường delegation, Module reads/exports, thời điểm append |
| Class chạy nhưng behavior kỳ lạ | Cùng binary name khác implementation, không lỗi ABI | Log loader/source, xét checksum/class version; test semantics |
| Test pass trên Java 17 nhưng lỗi Java 21 | Module/runtime/JAR/loader configuration khác | Test matrix JDK+classloader; xác minh versioned entries của multi-release JAR |

**Thứ tự giải quyết nên theo:**

1. Xác định đúng **class name, resource path** cần tìm.
2. Kiểm **JAR nào thật sự chứa entry** (`jar tf`); đừng chỉ nhìn source.
3. Xác định **loader/module của class gọi** và đường delegation của nó.
4. Kiểm **loader/source thực sự chọn**, không giả định child/parent ưu tiên toàn cục.
5. So binary API descriptors và package/access rules.
6. Với resource, kiểm `getResources` và liệu file đã bị module encapsulation không.
7. Nếu do collision, **đổi namespace/relocate/build artifact**, không tùy tiện ép JVM ưu tiên JAR agent trong môi trường production.
8. Chạy lại tests với cache/loader đã khởi động mới; đừng dựa vào append muộn sau khi symbolic reference resolution đã thất bại.

## 11. Các hiểu nhầm quan trọng

1. **“Đã đặt tên package riêng là mọi vấn đề class loading biến mất.”** Không. Helper còn phải được loader/module của bytecode đã instrument nhìn thấy.
2. **“Cùng binary name thì chắc chắn cùng Class object.”** Không nếu defining loaders khác nhau.
3. **“JAR agent chứa class nghĩa là class ấy sẽ được dùng.”** Không; parent-first có thể chọn bản từ parent.
4. **“Resource thuộc package của Java class nên không thể trùng.”** Resource chỉ có path; root resources và service descriptors rất dễ xung đột.
5. **“Chỉ cần dùng child-first cho agent.”** Có thể khiến agent chiếm class của app theo hướng ngược lại; không phải giải pháp mặc định.
6. **“Bootstrap là nơi an toàn để đặt mọi helper và thư viện.”** Sai; Javadoc Instrumentation cảnh báo nghiêm ngặt về class/resource ngoài ý muốn.
7. **“Đặt helper trong package ứng dụng để gọi package-private method luôn được.”** Sai: runtime package/module/loader identity và access control có thể khác.
8. **“Relocate dependency chỉ cần sửa `.class` paths.”** Sai: reflection strings, resources, SPI, module metadata, manifest và chữ ký có thể cần xử lý.
9. **“`getResource` luôn trả đúng file trong JAR gọi method.”** Sai: lookup qua loader, thường có delegation và có thể trả file từ parent.
10. **“`getResources` luôn theo một thứ tự toàn cục ổn định.”** Không trong mọi loader/module; mô hình thí nghiệm có thứ tự cụ thể, không suy rộng.
11. **“`appendToSystemClassLoaderSearch` sửa luôn `java.class.path`.”** Không, Javadoc nêu rõ property đó không bị thay.
12. **“Thêm helper JAR sau lỗi `NoClassDefFoundError` chắc chắn sửa được.”** Không, JVM có quy tắc nhớ lần symbolic reference resolution thất bại.
13. **“Một package Java duy nhất cũng là security isolation.”** Không: namespace tránh trùng tên chứ không tạo sandbox.
14. **“Tên package càng ngắn càng tiện, sau này đổi cũng được.”** Agent bytecode đã chèn tham chiếu binary name; đổi package cần migration/versioning phù hợp.
15. **“Không có class collision thì không cần xem resource.”** Sai; `application.properties`, `logback.xml` và `META-INF/services` vẫn có thể làm thay hành vi.

## 12. Câu hỏi tự kiểm tra

1. **Class identity gồm gì?** Binary name và defining loader (với ngữ cảnh module/runtime access đi kèm).
2. **Vì sao child JAR có `sample.shared.Marker` nhưng `Class.forName` qua child lại trả APP?** Vì URLClassLoader mặc định ủy quyền tới parent; parent tìm được class trước.
3. **Resource có tên `sample/shared/config.properties` có được bảo vệ bởi Java package namespace không?** Không. Đó chỉ là path được loader tìm, có thể tồn tại ở nhiều JAR.
4. **`getResources(name)` khác `getResource(name)` thế nào?** Một API liệt kê nhiều kết quả nhìn thấy, API kia tìm một kết quả theo chính sách của loader/module.
5. **Tại sao bootstrap append JAR phải tối thiểu?** Vì entry trùng tên có thể bị bootstrap chọn trước và làm app linkage/access thất bại.
6. **Thêm JAR vào system search có tự làm mọi custom loader nhìn thấy không?** Không; phụ thuộc quan hệ delegation và module visibility.
7. **Vì sao `IllegalAccessError` có thể xuất hiện nếu class không public bị nạp từ sai loader?** Runtime package/access identity không còn phù hợp dù package name text giống.
8. **Nếu app và agent dùng hai phiên bản cùng một dependency, giải pháp xây dựng thường là gì?** Cô lập loader và/hoặc relocate/shade dependency vào namespace agent, kiểm thử ABI.
9. **Relocate `com.foo.Provider` cần xét file nào ngoài `Provider.class`?** `META-INF/services`, reflection config, module/manifest/resources và dependencies liên quan.
10. **Vì sao không nên bỏ `logback.xml` trong bootstrap helper JAR?** Nó có thể được framework dò theo classpath/resource search và ảnh hưởng app.
11. **Điều gì chứng minh một class thực sự từ JAR nào?** Defining loader, CodeSource nếu có, class loading diagnostics và metadata của artifact được kiểm chứng.
12. **Khi `ClassLoader.getResourceAsStream` trả null, chắc chắn resource không ở JAR không?** Không: còn loader, module encapsulation, path và quyền truy cập.
13. **`Class.getResource("x.properties")` tra ở đâu?** Tương đối với package của class; dùng `"/path/from/root"` cho absolute resource path.
14. **Package `io.acme.agent.internal` có là security boundary không?** Không; nó là quy ước namespace để tránh trùng tên.
15. **Tại sao helper bootstrap không nên trực tiếp phụ thuộc thư viện app?** Bootstrap loader thường không nhìn thấy classes do child/app loaders định nghĩa, dễ lỗi linkage.
16. **Test collision trong ví dụ yêu cầu thư mục build nào thuộc runtime classpath?** Chỉ `build/demo`; app.jar và helper.jar được nạp bằng hai URLClassLoader tường minh.
17. **Làm sao xác nhận hai bản resource được phát hiện trong demo?** `SHARED_RESOURCE_MATCHES=2` từ `getResources` và kiểm tra entries trong JAR.
18. **Khi nào nên dùng `-Xlog:class+load=info`?** Khi JVM hỗ trợ unified logging và cần quan sát nguồn load class; không coi output đầy đủ là API ổn định.

## 13. Tài liệu tham khảo chính thức

- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, parent-first delegation, `getResource`, `getResources`, package definition, loader identity.
- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): tìm class/resource từ các URL/JAR và cách thiết lập parent loader.
- [Java SE 21 — Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `getClassLoader`, `getResource`, `getResourceAsStream`.
- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `appendToBootstrapClassLoaderSearch`, `appendToSystemClassLoaderSearch` và cảnh báo class/resource collision, unresolved symbolic references.
- [Java SE 21 — java.lang.instrument](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): cấu trúc agent JAR, `Premain-Class` và `Agent-Class`.
- [Java SE 21 — ServiceLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): `META-INF/services`, provider discovery và loader selection.
- [Java SE 21 — Module](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): resource encapsulation và `Module.getResourceAsStream`.
- [Java SE 21 — JAR File Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html): manifest, package sealing, multi-release JAR, service descriptors.

**Ghi nhớ:** một Java agent tốt **không tranh tên** với ứng dụng. Đặt helper và resource trong namespace riêng, giữ bootstrap JAR tối thiểu, cô lập/relocate dependencies và luôn xác minh **class nào được loader nào định nghĩa, resource nào thật sự được đọc**. Không có namespace convention nào thay thế được kiểm thử class-loader/module visibility trên JVM đích.