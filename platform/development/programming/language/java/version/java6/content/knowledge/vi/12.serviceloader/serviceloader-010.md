# Tích hợp Java SPI gốc với cấu trúc module của dự án hiện đại

## 1. Mục tiêu và phạm vi

**Java Service Provider Interface (SPI)** cho phép chương trình chọn các implementation theo một interface/abstract class mà không cần import hoặc khởi tạo trực tiếp từng implementation. Cơ chế chuẩn do JDK cung cấp gồm:

- **Service contract:** kiểu chung mà consumer biết, ví dụ `TextTransformer`.
- **Service provider:** class triển khai contract, ví dụ `UppercaseTransformer`.
- **Đăng ký provider:** file `META-INF/services/<tên đầy đủ của service>` trong JAR dùng classpath, hoặc `provides ... with ...` trong `module-info.java` của named module.
- **Khám phá:** `ServiceLoader.load(ServiceType.class)`, sau đó duyệt provider theo nhu cầu.

**SPI gốc vẫn còn được dùng trong Java hiện đại.** Điều thay đổi từ Java 9 là hệ module JPMS có cơ chế mô tả service bằng `uses` và `provides`, trong khi dự án thực tế còn có module build của Gradle/Maven. Bài học tập trung vào cách đặt contract, provider và consumer vào những module có trách nhiệm rõ, đóng gói đúng, chạy được trên Java 17+ và tránh làm lẫn classpath với module path.

Sau bài này, bạn có thể:
1. Phân biệt **Gradle/Maven module**, **JPMS named module** và **JAR trên classpath**.
2. Thiết kế ranh giới `service-api` → `service-provider` và `app`, không để app phụ thuộc trực tiếp vào implementation.
3. Tích hợp SPI bằng `META-INF/services` cho classpath và `uses`/`provides` cho JPMS.
4. Chạy một ví dụ Gradle multi-project có provider là dependency **runtime-only**.
5. Kiểm tra artifact/runtime, xử lý provider thiếu hoặc trùng, và xác định khi nào cần `ClassLoader` hay `ModuleLayer`.

## 2. Ba khái niệm "module" không đồng nghĩa

| Khái niệm | Ví dụ | Nó quyết định điều gì? |
| --- | --- | --- |
| **Gradle subproject / Maven module** | `:service-api`, `:service-provider`, `:app` | Cách chia source, build, dependency, test, JAR và phiên bản. |
| **JPMS named module** | `module demo.spi { ... }` trong `module-info.java` | Định danh module ở JVM; `requires`, `exports`, `uses`, `provides` và phạm vi truy cập. |
| **Classpath / unnamed module** | JAR trong `-cp` hoặc runtime classpath | Các class không được JPMS mô tả theo named module; đăng ký SPI thường đi qua resource `META-INF/services`. |

Một Gradle subproject **không tự biến thành JPMS named module**. Muốn là explicit named module, cần `module-info.java` biên dịch thành `module-info.class` và chạy/đóng gói qua module path thích hợp.

Ngược lại, một Gradle multi-project vẫn có thể chạy hoàn toàn trên classpath và dùng SPI bằng `META-INF/services`. Cơ chế này vẫn được JDK hỗ trợ; **không phải kiến thức lỗi thời**. Chỉ nên thêm JPMS khi dự án thực sự cần ranh giới module ở Java runtime, phân phối modular JAR hoặc runtime image.

## 3. Kiến trúc module đề xuất

Giả sử ứng dụng có nhiều phép biến đổi văn bản. Thiết kế ba module:

```text
                     (compile contract)
  +---------------------+         +---------------------+
  | app                 | ------> | service-api         |
  | module demo.app     |         | module demo.spi     |
  | uses TextTransformer|         | interface public    |
  +---------------------+         +---------------------+
           |                                 ^
           | runtimeOnly provider            | compile contract
           v                                 |
  +---------------------+                    |
  | service-provider    | -------------------+
  | module demo.provider|
  | provides ... with...|
  +---------------------+
```

**Ý nghĩa ranh giới:**
- `service-api` chứa interface ổn định, chỉ các kiểu được consumer/provider cùng dùng. Nó không phụ thuộc implementation.
- `service-provider` phụ thuộc `service-api`, triển khai nghiệp vụ và đăng ký provider. Không cần export package implementation khi chạy named module.
- `app` phụ thuộc `service-api` để biên dịch và công bố `uses`. Provider được đưa vào **runtime** mà không thêm `requires demo.provider` vào `module-info.java` của app.
- Có thể thêm nhiều provider module độc lập mà không sửa code nhận diện class implementation trong app; nếu có nhiều provider, consumer cần chính sách chọn lựa.

**Hai loại cạnh dependency khác nhau:** quan hệ `implementation project(':service-api')` trong Gradle nói về artifact khi build; `requires demo.spi` trong `module-info.java` nói về module được đọc khi biên dịch/chạy JPMS. Nên giữ hai khai báo nhất quán. `runtimeOnly project(':service-provider')` đưa JAR provider vào runtime mà không cần app import implementation.

## 4. Ví dụ Gradle multi-project + JPMS trên Java 17+

Ví dụ dùng **Gradle Groovy DSL**, Java 17+, API `ServiceLoader` của JDK, không yêu cầu thư viện application bên ngoài. Dự án thực tế có Gradle Wrapper thì dùng `./gradlew` hoặc `gradlew.bat`; nếu không có wrapper, dùng bản Gradle cài đặt phù hợp.

### 4.1. Cấu trúc thư mục

```text
spi-demo/
  settings.gradle
  build.gradle
  service-api/
    src/main/java/
      module-info.java
      demo/spi/TextTransformer.java
  service-provider/
    build.gradle
    src/main/java/
      module-info.java
      demo/provider/UppercaseTransformer.java
    src/main/resources/
      META-INF/services/demo.spi.TextTransformer
  app/
    build.gradle
    src/main/java/
      module-info.java
      demo/app/Main.java
```

File resource `META-INF/services/...` trong module provider là **tùy chọn đối với JPMS**, nhưng được thêm ở đây để cùng artifact có thể chạy với SPI kiểu classpath. Nó có vai trò riêng, không thay thế `module-info.java` trong ví dụ JPMS.

### 4.2. Khai báo các subproject và cấu hình Java

`settings.gradle`:

```groovy
rootProject.name = 'spi-demo'
include 'service-api', 'service-provider', 'app'
```

`build.gradle` ở root:

```groovy
subprojects {
    apply plugin: 'java'

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(17)
        }
        modularity.inferModulePath = true
    }
}
```

Cấu hình trên áp dụng Java plugin cho cả ba subproject nên `service-api` không cần file `build.gradle` riêng trong ví dụ tối giản này. `modularity.inferModulePath` yêu cầu Gradle phân loại dependencies có thông tin module để dùng module path cho source set có `module-info.java`. Java toolchain giúp chọn JDK biên dịch nhất quán. Các phiên bản Gradle hiện đại đã hỗ trợ xử lý Java modules; khi dùng build có convention plugin riêng, hãy đặt cấu hình tương đương trong convention thay vì lặp tùy ý.

### 4.3. service-api: chỉ định nghĩa hợp đồng công khai

`service-api/src/main/java/module-info.java`:

```java
module demo.spi {
    exports demo.spi;
}
```

`service-api/src/main/java/demo/spi/TextTransformer.java`:

```java
package demo.spi;

public interface TextTransformer {
    String id();
    String transform(String text);
}
```

`exports demo.spi` cho phép module consumer và provider truy cập kiểu `TextTransformer`. Nếu API chứa kiểu khác do module ngoài cung cấp, bạn có thể cần `requires`/`requires transitive` tương ứng; ví dụ này chỉ dùng kiểu trong `java.base` nên không cần thêm `requires java.base`.

### 4.4. service-provider: triển khai và công bố provider

`service-provider/build.gradle`:

```groovy
dependencies {
    implementation project(':service-api')
}
```

`service-provider/src/main/java/module-info.java`:

```java
module demo.provider {
    requires demo.spi;
    provides demo.spi.TextTransformer
        with demo.provider.UppercaseTransformer;
}
```

`service-provider/src/main/java/demo/provider/UppercaseTransformer.java`:

```java
package demo.provider;

import demo.spi.TextTransformer;
import java.util.Locale;

public final class UppercaseTransformer implements TextTransformer {
    public UppercaseTransformer() {
    }

    @Override
    public String id() {
        return "uppercase";
    }

    @Override
    public String transform(String text) {
        return text.toUpperCase(Locale.ROOT);
    }
}
```

Vì module khai báo `provides ... with ...`, `ServiceLoader` có thể định vị provider mà consumer không cần import `demo.provider.UppercaseTransformer`. Package `demo.provider` **không cần export**: hệ module cấp quyền cần thiết để tạo provider theo cơ chế service. Provider được khai báo ở đây là class public, có constructor public không tham số, tương thích cả cơ chế classpath.

### 4.5. app: chỉ biết interface, khai báo uses

`app/build.gradle`:

```groovy
apply plugin: 'application'

dependencies {
    implementation project(':service-api')
    runtimeOnly project(':service-provider')
}

application {
    mainModule = 'demo.app'
    mainClass = 'demo.app.Main'

    // Giải quyết rõ provider module ở thời điểm chạy ví dụ.
    applicationDefaultJvmArgs = ['--add-modules=demo.provider']
}
```

`runtimeOnly` là quyết định có chủ đích: app cần API khi compile, nhưng không cần compile trực tiếp đối với class provider. `--add-modules=demo.provider` bảo đảm demo resolve provider trong boot module layer từ module path; nó **không có nghĩa** app cần `requires demo.provider`. Trong một runtime đã bind provider module bằng cơ chế service/module resolution, có thể không cần ép `--add-modules`; hãy kiểm tra thực tế khi đóng gói image hoặc phân phối.

`app/src/main/java/module-info.java`:

```java
module demo.app {
    requires demo.spi;
    uses demo.spi.TextTransformer;
}
```

**Không bỏ `uses`:** một named module gọi `ServiceLoader.load(TextTransformer.class)` phải khai báo service mà nó sử dụng. Thiếu `uses` sẽ làm cơ chế load báo lỗi cấu hình. `requires demo.spi` là để đọc interface; `uses demo.spi.TextTransformer` là để khai báo ý định khám phá provider.

`app/src/main/java/demo/app/Main.java`:

```java
package demo.app;

import demo.spi.TextTransformer;
import java.util.List;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        List<TextTransformer> matches =
                ServiceLoader.load(TextTransformer.class)
                        .stream()
                        .map(ServiceLoader.Provider::get)
                        .filter(p -> "uppercase".equals(p.id()))
                        .toList();

        if (matches.size() != 1) {
            throw new IllegalStateException(
                    "Expected exactly one uppercase provider; found "
                            + matches.size());
        }

        TextTransformer selected = matches.get(0);
        System.out.println("provider=" + selected.id());
        System.out.println("result=" + selected.transform("Java SPI"));
    }
}
```

`toList()` có từ Java 16, hoạt động với Java 17+. Consumer sử dụng `ServiceLoader` để có các provider; ví dụ chọn theo `id()` và kiểm tra **đúng một** lựa chọn nhằm tránh phụ thuộc vào thứ tự provider khi ứng dụng tăng số plugin. `ServiceConfigurationError` vẫn có thể xuất hiện lúc duyệt nếu provider đăng ký không hợp lệ.

### 4.6. Đăng ký SPI classpath để artifact cũng chạy kiểu truyền thống

Tạo file **đúng đường dẫn** `service-provider/src/main/resources/META-INF/services/demo.spi.TextTransformer` với nội dung:

```text
demo.provider.UppercaseTransformer
```

Đây là **UTF-8 text resource**, tên file phải là tên đầy đủ của interface service. Gradle Java plugin mặc định đưa file dưới `src/main/resources` vào JAR, giữ nguyên vị trí `META-INF/services/...`.

- Khi provider nằm ở **classpath/unnamed module**, `ServiceLoader` đọc service-configuration resource này.
- Khi provider nằm trong **explicit named module** trên module path, `provides ... with ...` trong `module-info.class` là thông tin đăng ký chính; khai báo trùng trong service file cho cùng provider được bỏ qua, tránh nạp hai lần.
- Chỉ tạo `META-INF/services` cho một JAR nếu bạn thực sự hỗ trợ chạy classpath. Không thêm file chỉ để “kích hoạt” JPMS: `provides` mới là khai báo dành cho named module.

Với provider chạy kiểu classpath, class được đăng ký phải public, triển khai service và có constructor public không tham số; cơ chế provider factory `public static provider()` chỉ áp dụng cho provider của named module thích hợp, không phải một lối thay thế cho constructor khi đăng ký classpath.

### 4.7. Chạy và kết quả dự kiến

Từ thư mục `spi-demo`, khi có Gradle Wrapper:

```bash
./gradlew :app:run --console=plain
```

Trên Windows PowerShell/CMD, chạy tương đương:

```powershell
.\gradlew.bat :app:run --console=plain
```

Nếu project không có Wrapper và đã cài Gradle, dùng `gradle :app:run --console=plain`.

Hai dòng stdout do **chương trình Java** in ra (Gradle còn in thêm thông tin task/build):

```text
provider=uppercase
result=JAVA SPI
```

Luồng thực thi:
1. Gradle biên dịch `demo.spi`, `demo.provider` và `demo.app`, tách JAR/lớp theo subproject.
2. App chạy như named module `demo.app` và được resolve cùng `demo.provider` trong runtime module layer.
3. `ServiceLoader.load(TextTransformer.class)` khám phá thông tin provider từ JPMS `provides` (và có thể các provider khác nhìn thấy được), sau đó khởi tạo theo nhu cầu khi duyệt.
4. App kiểm tra provider có `id="uppercase"` đúng một bản; kết quả chuyển `"Java SPI"` thành `"JAVA SPI"`.

Nếu runtime thêm một provider khác có `id="uppercase"`, ví dụ chủ động báo lỗi thay vì tùy ý chọn một provider. Trong dự án lớn, có thể thiết kế registry với khóa duy nhất, ưu tiên rõ ràng, hoặc fail-fast theo ràng buộc nghiệp vụ.

## 5. Khi dự án chưa dùng JPMS: áp dụng SPI gốc trên classpath

Nhiều hệ thống Java hiện đại xây thành nhiều Gradle subproject/Maven module nhưng **không khai báo `module-info.java`**. Chúng vẫn dùng SPI chuẩn:

```text
api.jar            -> demo.spi.TextTransformer
provider.jar       -> demo.provider.UppercaseTransformer
                      META-INF/services/demo.spi.TextTransformer
app.jar            -> ServiceLoader.load(TextTransformer.class)
runtime classpath  -> api.jar + provider.jar + app.jar
```

Cách tích hợp:
1. Đặt service interface ở module API, implementation ở module provider.
2. Build app phụ thuộc API khi compile, chỉ thêm provider ở runtime. Trong Gradle có thể dùng `runtimeOnly project(':service-provider')`.
3. Đóng gói `META-INF/services/<FQCN>` trong JAR provider, nội dung là FQCN provider.
4. Bảo đảm runtime classpath có cả interface, provider và file resource; gọi `ServiceLoader.load(...)` từ consumer.
5. Chạy smoke test xác minh kết quả ít nhất một provider hoặc đúng số lượng/khóa mà nghiệp vụ yêu cầu.

Đối với Maven, tư duy tương tự: tách artifact API/provider/consumer và khai báo dependency provider có phạm vi runtime khi phù hợp. **Tên Maven module trong reactor không tự là tên JPMS module.**

Nếu quyết định chuyển sang JPMS, bổ sung `module-info.java` với `exports`/`requires`/`uses`/`provides`, rồi kiểm tra module path và quyền truy cập thật. Không nhất thiết đồng thời đổi mọi thư viện thứ ba nếu chúng chưa tương thích với named module; hãy đánh giá từng dependency và cơ chế packaging đang dùng.

## 6. ClassLoader, ModuleLayer và phạm vi khám phá

Trong môi trường classpath thông thường:

```java
ServiceLoader<TextTransformer> byContext =
        ServiceLoader.load(TextTransformer.class);
```

Overload một tham số sử dụng **Thread Context ClassLoader (TCCL)** làm điểm bắt đầu. Điều này hữu ích cho plugin/container nhưng có thể khác loader đã định nghĩa `TextTransformer`. Trong ứng dụng có plugin loader riêng, có thể truyền tường minh:

```java
ClassLoader pluginLoader = /* class loader được hệ thống plugin quản lý */;
ServiceLoader<TextTransformer> explicit =
        ServiceLoader.load(TextTransformer.class, pluginLoader);
```

Hai đoạn trên là **snippet API**, biến `pluginLoader` phải được cung cấp bởi hệ thống của bạn. Class loader phải nhìn thấy service contract và provider đúng runtime identity. Nếu host và plugin có hai bản riêng của cùng `demo.spi.TextTransformer` ở các loader khác nhau, Java có thể coi đó là hai kiểu khác nhau và provider bị báo `not a subtype`.

Nếu hệ plugin xây nhiều **named module trong ModuleLayer riêng**, nên khám phá theo layer:

```java
ServiceLoader<TextTransformer> inLayer =
        ServiceLoader.load(pluginLayer, TextTransformer.class);
```

Đây là snippet khi `pluginLayer` đã là `ModuleLayer` hợp lệ. Overload này tìm provider trong named modules của layer đó và các layer cha; **không quét classpath unnamed modules**. Đừng tưởng một subproject Gradle tương ứng với một `ModuleLayer`: layer là khái niệm runtime, được resolve/define riêng.

Khi cần tạm thay TCCL cho một đoạn code dùng SPI mặc định, phải khôi phục trong `finally`:

```java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    ServiceLoader<TextTransformer> loader =
            ServiceLoader.load(TextTransformer.class);
    // Sử dụng loader ngay trong phạm vi context đã xác định.
} finally {
    thread.setContextClassLoader(previous);
}
```

Đây cũng là snippet bên trong một phương thức đã có `pluginLoader`. Không giữ TCCL tùy tiện trong thread pool vì request sau có thể dùng sai provider hoặc giữ tham chiếu tới class loader đã gỡ.

## 7. Kiểm tra build artifact và runtime

Chỉ kiểm tra source đúng chưa đủ: lỗi SPI phần lớn lộ ra sau khi **đóng gói** và chạy trên runtime thực.

### 7.1. Kiểm tra named module

Chạy build JAR (khi dự án có Wrapper):

```bash
./gradlew :service-api:jar :service-provider:jar :app:jar
```

Kiểm tra module descriptor của JAR provider với `jar --describe-module --file <đường-dẫn-JAR>`; một lệnh minh họa khi không cấu hình `version`/`archiveBaseName` tùy chỉnh:

```bash
jar --describe-module --file service-provider/build/libs/service-provider.jar
```

Bạn cần thấy module `demo.provider` và khai báo `provides demo.spi.TextTransformer with demo.provider.UppercaseTransformer`. Tên JAR thực tế có thể kèm phiên bản; lấy chính xác tên file trong thư mục build trước khi chạy lệnh.

Kiểm tra resource classpath (nếu hỗ trợ chế độ classpath):

```bash
jar --list --file service-provider/build/libs/service-provider.jar
```

Trong danh sách cần có `META-INF/services/demo.spi.TextTransformer` và `demo/provider/UppercaseTransformer.class`. Đây là ví dụ đường dẫn mặc định; tùy build, tên artifact có thể khác.

### 7.2. Bảng kiểm tra tích hợp

| Lớp kiểm tra | Câu hỏi |
| --- | --- |
| Contract | Consumer/provider cùng dùng **một** kiểu service, cùng package và runtime class identity? |
| Gradle/Maven dependency | Consumer compile được với API; provider có trong **runtime** nhưng không bị hard-code làm compile dependency? |
| JPMS descriptor | `demo.spi` có `exports`; app có `requires` và `uses`; provider có `requires` và `provides`? |
| JPMS resolution | Provider JAR thực sự nằm trên module path và đã được resolve vào module layer khi chạy? |
| Classpath resource | File `META-INF/services/<FQCN>` nằm trong JAR cuối; tên class provider đúng; loader có thể đọc resource? |
| Provider construction | Class provider public, constructor public không tham số trong ví dụ; dependencies của provider có mặt ở runtime? |
| Runtime behavior | App phát hiện đúng provider, có xử lý 0/nhiều provider, không phụ thuộc thứ tự ngẫu nhiên? |
| Packaging | Khi tạo fat/shaded JAR, công cụ đóng gói có giữ và **gộp** các service files của nhiều dependency/provider? |

**Đặc biệt với fat JAR/shading:** nếu nhiều JAR cùng có `META-INF/services/demo.spi.TextTransformer`, thao tác copy mặc định có thể chỉ giữ một file. Hãy cấu hình công cụ đóng gói để merge nội dung service-configuration file. Với executable/nested JAR của framework, cần xác minh cách class loader và resource lookup chạy thực tế; tên “module” của framework hoặc Gradle không tự đồng nghĩa với JPMS. Đối với một project Spring Boot thông thường chạy theo executable JAR, có thể vẫn dùng classpath SPI, nhưng không nên giả định executable JAR đó chạy như một JPMS named module.

## 8. Cơ chế lazy loading, vòng đời và lựa chọn provider

`ServiceLoader.load(...)` tạo bộ khám phá, nhưng provider thường được tìm và khởi tạo **lười** khi duyệt. `ServiceLoader` lưu cache các provider đã load trong instance đó. Vì vậy:
- `iterator()`/`stream()` bắt đầu duyệt provider theo nhu cầu.
- `ServiceLoader.Provider.type()` cho phép xét kiểu provider trước khi gọi `get()` khởi tạo.
- `findFirst()` hợp lý khi bất kỳ provider nào cũng được, nhưng không nên dùng kết quả đầu tiên làm quy tắc ưu tiên nghiệp vụ nếu có nhiều provider.
- `reload()` xóa cache; nó **không tự thêm JAR vào classpath/module path** và không thay thế class đã được JVM nạp.
- `ServiceLoader` không thread-safe. Không vừa dùng chung loader ở nhiều thread vừa `reload()` mà thiếu phối hợp.

Ví dụ snippet để xem kiểu provider trước khi khởi tạo (đặt trong phương thức của consumer):

```java
ServiceLoader<TextTransformer> loader =
        ServiceLoader.load(TextTransformer.class);
loader.stream()
        .map(ServiceLoader.Provider::type)
        .map(Class::getName)
        .sorted()
        .forEach(System.out::println);
```

Output phụ thuộc các provider thực tế được resolve. `stream()` không thay thế kiểm tra lỗi: provider hỏng vẫn có thể phát sinh `ServiceConfigurationError` trong quá trình locate/load.

**Giữ vòng đời đúng:** khi thực sự hỗ trợ plugin thay nóng bằng `URLClassLoader` hoặc `ModuleLayer`, ứng dụng còn phải quản lý resource, thread, reference đến instance provider và loader cũ. SPI chỉ lo cơ chế discovery, không tự cách ly plugin, kiểm soát quyền, hoặc hot-reload bản triển khai đã nạp.

## 9. Những lỗi tích hợp phổ biến

| Triệu chứng | Nguyên nhân hay gặp | Hướng xử lý |
| --- | --- | --- |
| `findFirst()` rỗng hoặc danh sách trống | Quên `META-INF/services` trong classpath hoặc `provides`/module resolution trong JPMS | Xem artifact cuối và startup module path/classpath. |
| `ServiceConfigurationError: Provider ... not found` | Sai tên class, JAR provider/dependency vắng ở runtime | Kiểm tra FQCN, dependency runtimeOnly, nội dung JAR và class loader. |
| `... not a subtype` | Host và plugin nạp hai bản của service contract hoặc provider implement sai interface | Dùng chung một API artifact/type runtime; tránh nhúng trùng API vào plugin. |
| Named module consumer load lỗi | Thiếu `uses` trong `module-info.java` hoặc module không đọc được API | Bổ sung `uses`, `requires` và `exports` phù hợp. |
| Chạy được trong IDE, lỗi khi phát hành | Runtime classpath/module path khác, resource bị mất khi shade/bootJar | Test artifact phát hành trên launcher thực, kiểm tra merge service files. |
| Không thấy provider ngoài hệ thống | Sai TCCL, explicit loader chỉ thấy một phía, module layer chưa resolve provider | Chọn loader/layer chính xác; tránh dựa vào default không kiểm soát. |
| Hai provider cùng ID, hành vi khác nhau giữa máy | Dựa vào thứ tự `ServiceLoader` | Chọn bằng capability/ID và báo lỗi nếu có trùng, như ví dụ chính. |
| `reload()` không thấy JAR mới | Chỉ reset cache, classloader/module layer chưa được cập nhật | Thiết kế vòng đời plugin và loader/layer riêng. |
| Runtime image thiếu provider | Module provider không nằm trong image hoặc không được bind/resolve | Kiểm tra cấu hình `jlink`/module graph và kiểm thử image sau build. |

Nếu cần kiểm tra service file qua classloader (chỉ có giá trị cho provider classpath), snippet trong phương thức có xử lý `IOException`:

```java
ClassLoader cl = Thread.currentThread().getContextClassLoader();
var resources = cl.getResources(
        "META-INF/services/demo.spi.TextTransformer");
while (resources.hasMoreElements()) {
    System.out.println(resources.nextElement());
}
```

Đoạn này **không thể** dùng để liệt kê đầy đủ provider được đăng ký bằng `provides` trong named modules: metadata JPMS không nhất thiết là một file resource `META-INF/services`.

## 10. Nguyên tắc áp dụng vào dự án thật

1. **Bắt đầu từ contract ổn định.** Tách API module tối thiểu; chỉ public hóa những kiểu consumer cần. Duy trì khả năng mở rộng provider độc lập.
2. **Chọn deployment model trước.** Classpath, named modules, hay runtime plugin layer? Kiểu module của build không quyết định tự động kiểu runtime.
3. **Giữ dependency một chiều.** Provider → API; consumer → API; provider xuất hiện ở runtime. Không đưa class implementation vào module API hoặc hard-code import trong consumer.
4. **Dùng registration tương ứng:** `META-INF/services` khi chạy classpath; `uses` và `provides` khi chạy JPMS. Có thể hỗ trợ cả hai nếu phân phối dual-mode và kiểm tra thực tế.
5. **Chọn provider có chủ đích.** Phát hiện 0/1/nhiều provider, có quy tắc chọn bằng ID/capability/cấu hình; fail-fast khi thiếu hoặc trùng thay vì chọn theo thứ tự triển khai.
6. **Kiểm thử bản đóng gói.** Chạy smoke test với JAR/distribution/container/runtime image thật, không chỉ unit test ở IDE. Xác nhận provider file/descriptor và đường đi của dependency.
7. **Đảm bảo chất lượng và an toàn plugin.** Provider là code được thực thi trong process với quyền của ứng dụng; xác minh nguồn artifact, dependency và tương thích phiên bản. `ServiceLoader` không sandbox code không tin cậy.
8. **Hạn chế trạng thái loader giữ lâu.** Quản lý TCCL/thread, cache, `reload`, resource; không gọi `ServiceLoader.loadInstalled` để thay cơ chế plugin ứng dụng: overload đó dùng platform class loader và thường bỏ qua provider ở application classpath/module path.

## 11. Bài tập tự kiểm tra

**Câu 1.** Dự án có ba Gradle subproject nhưng không có `module-info.java`. Có thể dùng `ServiceLoader` không?

**Đáp án:** Có. Đó vẫn là kiến trúc module ở mức build; SPI classpath đăng ký bằng `META-INF/services/<FQCN>` vẫn hoạt động khi JAR provider xuất hiện đúng runtime classpath.

**Câu 2.** Trong JPMS, app cần `requires demo.provider` để gọi `ServiceLoader.load(TextTransformer.class)` không?

**Đáp án:** Không. App cần `requires demo.spi` và `uses demo.spi.TextTransformer`. Provider khai báo `provides`, được đưa vào runtime và được resolve trong module layer phù hợp.

**Câu 3.** File service và `provides` đều đăng ký cùng provider trong JAR dual-mode. Trên module path, liệu provider có bị nạp hai lần chỉ vì hai khai báo?

**Đáp án:** Không. Theo hợp đồng `ServiceLoader`, cấu hình service-file nhắc tới provider vốn đã được triển khai trong named module sẽ được bỏ qua để tránh duplicate.

**Câu 4.** Ứng dụng có provider JAR nhưng `findFirst()` rỗng. Hãy nêu hai việc nên kiểm tra.

**Đáp án:** Kiểm tra registration (`META-INF/services` hoặc `provides`) và liệu JAR/provider module có thực sự hiện diện, nhìn thấy và được resolve trong runtime tương ứng. Nếu classloader khác nhau, kiểm tra TCCL và service type identity.

**Câu 5.** `ServiceLoader.reload()` có tự thêm module provider mới vào module graph không?

**Đáp án:** Không. `reload()` chỉ xóa cache của ServiceLoader hiện có; thay đổi class loader/module layer là việc riêng của hệ plugin/runtime.

## 12. Tài liệu chuẩn đang được hỗ trợ

- [Java SE 17 API — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html) — contract và hai cách đăng ký provider, cách khám phá named/unnamed modules, API `stream`/`reload`, lỗi cấu hình.
- [Gradle — Building Modules for the Java Module System](https://docs.gradle.org/current/userguide/java_library_plugin.html#sec:java_library_modular) — `module-info.java`, `requires` và Gradle dependencies, suy luận module path.
- [Gradle Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html) — `mainModule`, `mainClass`, `applicationDefaultJvmArgs`, task `run`.
- [Java SE 17 API — ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html) — scope của named module layer khi xây plugin runtime.
