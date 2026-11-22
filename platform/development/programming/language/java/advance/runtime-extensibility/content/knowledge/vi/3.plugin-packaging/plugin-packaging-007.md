# Kiểm tra gói plugin thực tế thay vì chỉ chạy trên classpath của IDE

## 1. Vấn đề: chạy được trong IDE chưa chứng minh artifact sẽ hoạt động

Trong một ứng dụng Java có khả năng mở rộng tại runtime, plugin thường được phân phối dưới dạng JAR. Khi chạy thử trong IntelliJ IDEA, Eclipse hoặc bài unit test, IDE dựng classpath từ thư mục `build/classes`, `target/classes`, `resources` và các dependency đã được giải quyết. Môi trường này có thể **khác hẳn nội dung và cách nạp JAR cuối cùng**.

Ví dụ, IDE nhìn thấy:

```text
app/build/classes/java/main/
plugin/build/classes/java/main/
plugin/build/resources/main/META-INF/services/com.example.spi.Plugin
~/.gradle/caches/.../helper-library.jar
```

Nhưng ứng dụng thật được giao hai tệp:

```text
dist/app.jar
dist/plugins/my-plugin.jar
```

Một bài kiểm tra chạy trên classpath của IDE có thể thành công mặc dù artifact phát hành thiếu `META-INF/services`, thiếu thư viện runtime, chứa tên package cũ sau relocation, đặt dependency sai vị trí hoặc không thể đọc được từ classloader thực tế.

**Mục tiêu kiểm thử đúng:** chứng minh rằng các byte của artifact được giao, với cấu hình nạp và Java runtime dự kiến, đủ để tìm, khởi tạo và sử dụng plugin. Đây là kiểm tra đầu ra của quá trình build, không chỉ kiểm tra mã nguồn.

## 2. Phân biệt ba mức kiểm tra

| Mức | Đầu vào | Chứng minh được | Chưa chứng minh được |
| --- | --- | --- | --- |
| Unit test | Class compile và test dependencies | Logic độc lập, xử lý đầu vào/đầu ra | Plugin có nằm trong JAR và được host tìm thấy hay không |
| Integration test trên classpath phát triển | Classes và resources do IDE/Gradle/Maven dựng | Hợp đồng API và tích hợp trong môi trường build | Đúng nội dung archive, manifest, đường dẫn plugin và runtime dependencies |
| Artifact smoke/integration test | JAR sau `package`/`jar`/`shadowJar` cùng cách chạy lúc triển khai | Class/resource, SPI metadata, cách nạp và hành vi ở artifact thực | Mọi môi trường production, trừ khi mô phỏng đủ cấu hình liên quan |

Ba mức kiểm thử bổ trợ nhau. Không nên bỏ unit test; chỉ cần **thêm bước kiểm tra artifact cuối** cho các khả năng phụ thuộc vào đóng gói.

## 3. Định nghĩa hợp đồng phân phối trước khi test

Trước khi viết lệnh kiểm tra, xác định:

1. **Artifact nào được phát hành?** JAR thường, executable/fat JAR, shaded JAR, tập JAR trong `plugins/`, hay module JAR trên module path.
2. **Ai sở hữu SPI API?** Host cung cấp `com.example.spi.Plugin` hay plugin tự đóng gói? Nếu hai classloader nạp hai bản sao của một class cùng tên, có thể xuất hiện lỗi `not a subtype` hoặc `ClassCastException`.
3. **Cách khám phá plugin?** `ServiceLoader`, tên class trong file cấu hình, phản chiếu, hay framework-specific registry? Đừng tìm `META-INF/services` khi hệ thống không sử dụng SPI.
4. **Dependency được cấp thế nào?** Bundled bên trong fat JAR, đi kèm `lib/`, hay do host cung cấp? `compileOnly`/`provided` phải thực sự do môi trường runtime đáp ứng.
5. **Classloader và runtime nào?** `URLClassLoader`, thread context classloader, application classloader, module layer, Java 17/21, hệ điều hành, đường dẫn plugin ngoài ứng dụng.

Kết quả kiểm tra phải gắn với **một cách phân phối cụ thể**. Không được lấy việc `java -cp "build/classes:..."` thành công làm bằng chứng cho `java -jar dist/app.jar`.

## 4. Ví dụ đầy đủ: tạo và kiểm thử một plugin JAR thực sự

Ví dụ này dùng Java 17+, một host sở hữu interface `ToolPlugin` và plugin riêng được tải bằng `URLClassLoader`. Không cần Gradle/Maven để nhìn rõ quá trình đóng gói; khi dùng hệ build thực tế, thay lệnh tạo JAR bằng artifact mà pipeline tạo ra.

Cấu trúc tệp:

```text
sample/
  api/com/example/spi/ToolPlugin.java
  plugin/com/example/plugins/UppercasePlugin.java
  host/Host.java
  plugin-resources/META-INF/services/com.example.spi.ToolPlugin
```

`api/com/example/spi/ToolPlugin.java`:

```java
package com.example.spi;

public interface ToolPlugin {
    String id();
    String apply(String input);
}
```

`plugin/com/example/plugins/UppercasePlugin.java`:

```java
package com.example.plugins;

import com.example.spi.ToolPlugin;
import java.util.Locale;

public final class UppercasePlugin implements ToolPlugin {
    public UppercasePlugin() {}

    @Override
    public String id() {
        return "uppercase";
    }

    @Override
    public String apply(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
```

Nội dung `plugin-resources/META-INF/services/com.example.spi.ToolPlugin`:

```text
com.example.plugins.UppercasePlugin
```

`host/Host.java`:

```java
import com.example.spi.ToolPlugin;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.ServiceLoader;

public final class Host {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: Host <plugin-jar>");
        }

        Path pluginJar = Path.of(args[0]).toAbsolutePath();
        URL url = pluginJar.toUri().toURL();

        // Parent thấy ToolPlugin API; child chứa implementation và SPI resource.
        try (URLClassLoader loader = new URLClassLoader(
                new URL[] {url}, Host.class.getClassLoader())) {

            ServiceLoader<ToolPlugin> services =
                    ServiceLoader.load(ToolPlugin.class, loader);
            List<ToolPlugin> plugins = new ArrayList<>();
            for (ToolPlugin plugin : services) {
                plugins.add(plugin); // Thực sự khởi tạo provider, không chỉ đếm metadata.
            }

            if (plugins.size() != 1) {
                throw new AssertionError(
                        "Expected 1 plugin, found " + plugins.size());
            }

            ToolPlugin plugin = plugins.get(0);
            if (!"uppercase".equals(plugin.id())) {
                throw new AssertionError("Unexpected plugin: " + plugin.id());
            }
            String output = plugin.apply("artifact test");
            if (!"ARTIFACT TEST".equals(output)) {
                throw new AssertionError("Unexpected output: " + output);
            }
            System.out.println(plugin.id() + ": " + output);
        }
    }
}
```

Trong thư mục `sample`, build **hai JAR riêng**:

```bash
mkdir -p out/api out/plugin out/host dist
javac -d out/api api/com/example/spi/ToolPlugin.java
javac -cp out/api -d out/plugin plugin/com/example/plugins/UppercasePlugin.java
javac -cp out/api -d out/host host/Host.java
jar --create --file dist/plugin.jar -C out/plugin . -C plugin-resources .
jar --create --file dist/host.jar -C out/api . -C out/host .
java -cp dist/host.jar Host dist/plugin.jar
```

Kết quả:

```text
uppercase: ARTIFACT TEST
```

Với Windows PowerShell, `mkdir -p` là cú pháp shell Unix; có thể tạo các thư mục trước bằng `New-Item -ItemType Directory -Force`. Các lệnh `javac`, `jar` và `java` còn lại có cùng ý nghĩa.

Điểm quan trọng: host chạy bằng **`dist/host.jar`**, plugin được nạp từ **`dist/plugin.jar`**; không đưa `out/plugin` hoặc `plugin-resources` lên classpath của lệnh chạy. Nếu đóng gói thiếu tài nguyên:

```bash
jar --create --file dist/plugin-broken.jar -C out/plugin .
java -cp dist/host.jar Host dist/plugin-broken.jar
```

Host sẽ ném `AssertionError` với thông điệp `Expected 1 plugin, found 0`. Đây là lỗi mà bài test chỉ chạy `out/plugin` với `plugin-resources` riêng trên classpath có thể bỏ sót.

**Giới hạn của ví dụ:** `URLClassLoader` trong ví dụ nạp một plugin tin cậy và không tạo ranh giới bảo mật. Plugin code chạy với quyền của JVM host. Trong hệ thống có plugin không tin cậy, cần mô hình cách ly riêng như process/container; classloader không phải sandbox. Trong ứng dụng thực tế, hãy kiểm soát danh sách JAR và API được chia sẻ.

## 5. Kiểm tra cấu trúc JAR bằng công cụ JDK

### Kiểm tra các entry có thực sự tồn tại

```bash
jar --list --file dist/plugin.jar
```

Đầu ra phải có ít nhất:

```text
META-INF/
META-INF/MANIFEST.MF
META-INF/services/
META-INF/services/com.example.spi.ToolPlugin
com/
com/example/
com/example/plugins/
com/example/plugins/UppercasePlugin.class
```

Thứ tự các entry trong output có thể khác; **sự hiện diện và đường dẫn** mới là điều quan trọng. Chữ hoa, chữ thường và tên package trong đường dẫn là đáng kể.

Đối với artifact thực tế, kiểm tra:

- `META-INF/services/<fully.qualified.ServiceName>` và nội dung descriptor khi dùng classpath SPI.
- `.class` của provider, dependencies và API nếu chúng cần được đóng gói.
- `META-INF/MANIFEST.MF`: `Main-Class`, `Class-Path`, `Multi-Release` hoặc các thuộc tính liên quan nếu cách chạy sử dụng chúng.
- Các tài nguyên config/schema/template mà plugin đọc bằng `getResource`/`getResourceAsStream`.
- Đường dẫn và chữ ký native library nếu plugin dùng JNI; kiểm thử trên OS/architecture phù hợp.
- `module-info.class` và module descriptors nếu chạy trên module path.

Một JAR hợp lệ về định dạng ZIP không bảo đảm Java nạp được plugin. `jar --describe-module --file dist/plugin.jar` giúp kiểm tra thông tin module khi áp dụng; kết quả cần được diễn giải theo việc đây là named, automatic hay classpath JAR.

### Kiểm tra nội dung service descriptor

Với môi trường có `unzip`:

```bash
unzip -p dist/plugin.jar META-INF/services/com.example.spi.ToolPlugin
```

Kết quả kỳ vọng:

```text
com.example.plugins.UppercasePlugin
```

Dùng `jar --extract --file dist/plugin.jar META-INF/services/com.example.spi.ToolPlugin` khi cần trích xuất bằng JDK, nhưng chú ý lệnh extract ghi file vào working directory; nên chạy trong một thư mục tạm.

Đường dẫn descriptor dựa trên **tên nhị phân đầy đủ của service interface**, không phải tên artifact hay implementation. Nội dung phải trỏ đến provider sau quá trình relocation/shading, không trỏ tên class trước khi đổi package.

## 6. Dependency runtime: thử môi trường tối thiểu

Một plugin có thể compile được bởi vì IDE hoặc test runner chứa thư viện hỗ trợ mà JAR phát hành không mang theo. Ví dụ:

```text
plugin.jar
  com/example/plugins/ReportPlugin.class
  META-INF/services/com.example.spi.ToolPlugin

IDE runtime:
  plugin.jar + report-utils.jar

Production:
  plugin.jar             # thiếu report-utils.jar
```

Tùy nơi class cần được load, runtime có thể ném `NoClassDefFoundError`, `ClassNotFoundException`, `ServiceConfigurationError` hoặc lỗi khởi tạo provider. Không có một exception duy nhất cho mọi kiểu thiếu dependency.

Cách kiểm:

1. Đặt artifact đầu ra trong thư mục phát hành sạch (`dist/`), không thêm `build/classes`, `target/classes` hay các thư viện IDE vô tình cung cấp.
2. Chạy đúng command production: `java -cp`, `java -jar`, launcher script hoặc module path.
3. Chỉ đặt các dependency **được hợp đồng phân phối cho phép** vào classpath/module path.
4. Tập trung vào load, instantiate và lời gọi thật có thể chạm đến class phụ thuộc; việc chỉ thấy tên provider chưa chứng minh toàn bộ đường thực thi hoạt động.
5. Nếu hỗ trợ nhiều phiên bản Java/OS, chạy smoke test trên các môi trường hỗ trợ trong CI.

Với thin JAR, các dependency có thể phải đứng cạnh artifact ở `lib/`; với fat JAR, kiểm tra thư viện đã được gộp/nhúng theo launcher tương ứng. Không giả định rằng lệnh `java -jar` tự động đọc mọi JAR nằm cùng thư mục. Khi dùng `java -jar`, tùy cơ chế launcher/manifest mà classpath bên ngoài được xử lý khác; `-cp` đặt trên command line không thay thế cơ chế classpath của `-jar`.

## 7. Thử đúng classloader và ServiceLoader

`ServiceLoader.load(Service.class)` mặc định dùng **thread context classloader**; `ServiceLoader.load(Service.class, loader)` dùng loader truyền vào. Bài test chạy trên IDE có thể có context loader rộng hơn runtime thực tế. Vì vậy smoke test phải dùng cách gọi giống host.

Các tình huống cần test khi có liên quan:

| Tình huống | Kiểm tra |
| --- | --- |
| Plugin JAR được thêm động | Tạo loader trỏ chính xác JAR phân phối; load qua loader đó |
| API service do host sở hữu | Provider tương thích với **cùng một `Class<?> ` service type** mà host sử dụng |
| Nhiều plugin từ nhiều JAR | Mọi provider đều được tìm thấy, không bị ghi đè `META-INF/services` |
| Package relocation | Descriptor, provider name và bytecode cuối cùng đồng bộ |
| Thêm/bớt JAR lúc runtime | Lifecycle loader, `ServiceLoader.reload()` khi phù hợp; không kỳ vọng thay file là tự cập nhật |
| JPMS named modules | `uses`/`provides` hợp lệ và service được tìm trong module layer đúng |

Tránh khẳng định `Class.forName("...")` thành công là đủ: lệnh đó không xác minh `ServiceLoader` có tìm thấy provider hay không; cũng chưa chắc class có thể khởi tạo hoặc thực hiện hợp đồng plugin.

### Thất bại cần phát hiện sớm

Khi yêu cầu ít nhất một plugin, coi danh sách provider rỗng là **test fail**. `ServiceLoader` trả collection trống có thể là hành vi hợp lệ của API, nên phải có assertion theo yêu cầu sản phẩm.

Nếu plugin được chọn theo `id()`, nên kiểm tra **tập ID kỳ vọng** thay vì chỉ `count()`: số lượng đúng vẫn có thể chứa sai provider. Gọi một operation thực tế của mỗi plugin để phát hiện lỗi liên kết và lỗi resource chỉ xuất hiện khi thực thi.

## 8. Kiểm thử đúng build output với Gradle và Maven

### Gradle

Với Gradle, hãy chạy tác vụ build được dùng để phát hành rồi test chính file output của tác vụ đó:

```bash
./gradlew clean jar
jar --list --file build/libs/your-plugin.jar
```

Đây là ví dụ cho project dùng Gradle Wrapper trên Unix; trên Windows là `gradlew.bat`. Tên JAR cụ thể tùy `archiveBaseName`, version và classifier. Với Shadow, dùng `shadowJar` và kiểm tra **Shadow JAR**, không nhầm với JAR thường:

```bash
./gradlew shadowJar
jar --list --file build/libs/your-plugin-all.jar
```

Ví dụ lệnh `jar` dùng tên output phổ biến; cần thay bằng **đường dẫn artifact đã được task tạo thật**. Khi task đã tạo JAR, không lấy kết quả của `test` tự động thay cho smoke test sau đóng gói. Gradle task kiểm thử có thể dùng runtimeClasspath của dự án, vốn rộng hơn classpath phân phối.

### Maven

```bash
mvn clean package
jar --list --file target/your-plugin.jar
```

Tên output phụ thuộc `artifactId`, `version`, finalName và cấu hình Shade/Assembly. Nếu dùng Shade/Assembly, kiểm tra artifact được triển khai, tránh chọn nhầm original JAR. `mvn test` không tương đương kiểm thử `mvn package` bởi tài nguyên có thể được biến đổi tại package phase.

### Quy tắc CI

Sắp xếp pipeline:

```text
Compile → Unit tests → Package → Inspect artifact → Launch artifact → Assert plugin discovery/behavior → Publish
```

Smoke test cần chạy **trước khi xuất bản** và thất bại với exit code khác 0. Ví dụ `Host` ở trên ném `AssertionError` khi provider thiếu/sai, nên command `java` trả non-zero và CI có thể chặn publish.

Đặc biệt khi có bước `minimize`, shading, relocation, obfuscation, resource filtering hoặc post-processing, artifact cần test phải là **file sau bước biến đổi cuối cùng**.

## 9. Các lỗi điển hình và cách chẩn đoán

| Triệu chứng sau package | Bằng chứng cần tìm | Hướng xử lý |
| --- | --- | --- |
| 0 plugin, IDE vẫn tìm được | Descriptor bị thiếu hoặc sai vị trí trong JAR | Bổ sung resource theo cấu trúc `META-INF/services/`; kiểm tra resource processing |
| Thiếu một vài plugin sau merge JAR | Hai dependency có cùng tên descriptor, một bản bị ghi đè | Dùng transformer hợp nhất service files |
| `ServiceConfigurationError: Provider ... not found` | Descriptor ghi tên cũ hoặc class provider không có trong artifact | Đồng bộ relocation và metadata; kiểm tra minimizer |
| `not a subtype` / `ClassCastException` | API SPI bị đóng gói trùng hoặc nạp bởi loader khác | Chia sẻ cùng service API từ host; kiểm soát parent/child loader |
| `NoClassDefFoundError` khi chạy provider | Dependency có ở IDE nhưng thiếu trong distribution | Đóng gói dependency hoặc cung cấp trên runtime path đúng hợp đồng |
| Resource loading trả `null` | Resource không được copy vào JAR hoặc đường dẫn bị đổi | Kiểm tra entries và đường dẫn `getResource` |
| `java -jar` khác `java -cp` | Manifest/launcher/classpath packaging khác | Chạy đúng command phân phối, kiểm tra `Main-Class` và launcher |
| Plugin chạy ở máy phát triển nhưng lỗi tại Linux | Chữ hoa/thường, path, permission, JNI binary hoặc encoding | Kiểm tra trên môi trường tương thích production |
| JPMS module không được phát hiện | `module-info` hoặc module layer không khớp | Xác minh `uses`/`provides`, module path và layer |

Không nên chữa lỗi bằng cách đưa toàn bộ dependency của IDE vào production classpath: cách đó có thể che giấu thiếu sót của bản phân phối và gây xung đột phiên bản.

## 10. Kiểm soát tính tái lập và provenance của artifact

Một rủi ro khác là kiểm thử **file khác** file sẽ phát hành. Ví dụ pipeline build nhiều biến thể, test `plugin.jar` nhưng upload `plugin-all.jar`. Để bảo đảm tính liên kết:

- Ghi nhận đường dẫn và SHA-256 của artifact đã kiểm thử (`sha256sum dist/plugin.jar` hoặc PowerShell `Get-FileHash dist/plugin.jar -Algorithm SHA256`).
- Dùng chính artifact đó cho bước publish; nếu ký lại, tối ưu hoặc đóng gói lại sau test, cần xác minh và kiểm thử artifact sau biến đổi.
- Build trong môi trường CI kiểm soát được Java, dependency và phiên bản plugin build; tránh dùng file cũ còn sót từ lần build trước.
- Với plugin load từ thư mục `plugins/`, kiểm tra cả cấu trúc phân phối và file cấu hình/launcher tương ứng.

Hash giúp xác nhận **cùng nội dung byte** đã được test và phát hành; nó không tự chứng minh plugin đúng. Kết luận chỉ có giá trị khi đi cùng smoke test đúng môi trường.

## 11. Checklist trước phát hành

- [ ] Build đúng task/profile tạo artifact phát hành.
- [ ] Mở JAR cuối và xác minh có class, resources, SPI descriptors, manifest/module metadata cần thiết.
- [ ] Đối chiếu provider names trong service descriptors với class thực sự được đóng gói, kể cả sau relocate.
- [ ] Không để test runtime âm thầm dùng `build/classes`, `target/classes`, test dependencies hoặc IDE-managed classpath.
- [ ] Chạy host/launcher bằng command và Java version được hỗ trợ; nạp plugin từ đúng file JAR phân phối.
- [ ] Assert số lượng và danh tính provider, khởi tạo provider và gọi operation thật.
- [ ] Chạy trường hợp thiếu resource/dependency khi có thể, để xác nhận kiểm thử có khả năng phát hiện lỗi.
- [ ] Kiểm thử mọi biến thể đáng phát hành, gồm regular JAR, shaded JAR hoặc module JAR theo hợp đồng thực tế.
- [ ] Gắn artifact đã kiểm thử với artifact được publish bằng hash hoặc cùng đầu ra pipeline.

**Kết luận kỹ thuật:** kiểm thử plugin trên classpath IDE chứng minh code hoạt động trong môi trường phát triển. Chỉ việc **mở và chạy đúng artifact sau đóng gói**, dưới đúng classloader, dependency set và runtime command, mới chứng minh bản phân phối có thể khám phá, khởi tạo và thực thi plugin như kỳ vọng.
