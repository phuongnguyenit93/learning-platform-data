# Dependency declaration và requires tương ứng

Trong ứng dụng Java dùng Java Platform Module System (JPMS), cùng một thư viện thường xuất hiện ở hai nơi: **khai báo dependency trong công cụ build** (Maven hoặc Gradle) và **khai báo `requires` trong `module-info.java`**. Hai khai báo này liên quan chặt chẽ nhưng không đồng nghĩa.

- Build tool quyết định **artifact nào, phiên bản nào, từ repository nào** được đưa vào compile classpath, module path, runtime hoặc test.
- Module descriptor quyết định **named module nào đọc named module nào**, package nào được export hoặc mở cho reflection, và module nào tiêu thụ/cung cấp service.
- Lệnh biên dịch hoặc chạy phải cung cấp các artifact đúng module name, đúng version và đúng đường dẫn để hệ thống phân giải module có thể kiểm tra hợp đồng đó.

Khi di chuyển dự án từ classpath sang module path, chỉ thêm dependency vào `pom.xml` hoặc `build.gradle` thường chưa đủ. Ngược lại, chỉ thêm `requires` mà không có artifact tương ứng trên module path sẽ gây lỗi `module not found`.

## 1. Hai tầng khai báo giải quyết những câu hỏi khác nhau

Giả sử ứng dụng dùng một thư viện tên `acme-json`. Trong Maven, một dependency có thể được khai báo bằng:

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>acme-json</artifactId>
    <version>2.4.0</version>
</dependency>
```

Ở đây, `com.acme:acme-json:2.4.0` là **tọa độ artifact**. Nó giúp Maven tải đúng file JAR và các dependency liên quan.

Trong `module-info.java` của ứng dụng:

```java
module com.acme.app {
    requires com.acme.json;
}
```

`com.acme.json` là **tên JPMS module**, không phải Maven `groupId`, `artifactId` hay tên file JAR. Nếu artifact có descriptor `module-info.class`, tên module được lấy từ descriptor đó. Với automatic module, tên có thể đến từ manifest hoặc được suy ra từ tên JAR.

Một bản build hoạt động khi cả hai lớp cấu hình tương ứng: build tool cung cấp JAR chứa module `com.acme.json`, còn descriptor ứng dụng khai báo quan hệ đọc module đó.

| Câu hỏi | Cấu hình chịu trách nhiệm |
|---|---|
| Dùng phiên bản thư viện nào? | Maven/Gradle dependency declaration |
| Tìm thư viện ở repository nào? | Maven/Gradle repositories và dependency resolution |
| Artifact nằm trên compile/module path nào? | Compiler plugin hoặc cấu hình build |
| Named module của ứng dụng đọc module nào? | `requires` trong `module-info.java` |
| Module consumer có thể import package nào? | `exports` của module cung cấp |
| Framework được deep reflection vào package nào? | `opens` của module chứa package |
| Service provider nào có thể được khám phá? | `uses`, `provides` và module graph |

**Quy tắc cốt lõi:** dependency declaration chọn **artifact**; `requires` khai báo **readability** trong module graph.

## 2. Ví dụ tối thiểu với module ứng dụng và thư viện

Giả sử có module thư viện:

```java
// module-info.java của thư viện
module com.acme.greeting {
    exports com.acme.greeting.api;
}
```

Class công khai:

```java
package com.acme.greeting.api;

public final class Greeter {
    private Greeter() {
    }

    public static String hello(String name) {
        return "Xin chào, " + name;
    }
}
```

Ứng dụng dùng thư viện:

```java
package com.acme.app;

import com.acme.greeting.api.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.hello("JPMS"));
    }
}
```

Descriptor của ứng dụng:

```java
module com.acme.app {
    requires com.acme.greeting;
}
```

Maven hoặc Gradle vẫn cần lấy đúng JAR của `com.acme.greeting`. Khi biên dịch module `com.acme.app`, `javac` nhìn thấy descriptor và xác nhận:

1. Module `com.acme.greeting` có tồn tại trong tập module có thể quan sát không?
2. Module `com.acme.app` có quyền đọc nó thông qua `requires` không?
3. Package `com.acme.greeting.api` đã được export cho consumer chưa?
4. Class và method được tham chiếu có visibility hợp lệ không?

Một dependency build tồn tại nhưng thiếu `requires` vẫn có thể gây lỗi package không visible. Ngược lại, `requires` đúng nhưng thiếu JAR dẫn tới lỗi không tìm thấy module.

## 3. Khai báo dependency trong Maven

Với cấu trúc Maven thông thường:

```text
app/
├── pom.xml
└── src/main/java/
    ├── module-info.java
    └── com/acme/app/Main.java
```

Ví dụ `pom.xml` tối giản:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme</groupId>
    <artifactId>app</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>greeting</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Maven quản lý việc lấy `com.acme:greeting:1.0.0`; `module-info.java` trong ứng dụng vẫn cần `requires com.acme.greeting;` nếu mã nguồn truy cập API của named module này.

Phiên bản Java release và phiên bản plugin trong ví dụ chỉ là cấu hình minh họa. Dự án thực tế nên dùng phiên bản plugin tương thích với JDK/toolchain và chính sách build của tổ chức.

Các Maven scope phổ biến:

| Maven scope | Ý nghĩa build thông thường | Lưu ý khi thiết kế JPMS |
|---|---|---|
| `compile` (mặc định) | Dependency cần khi compile; thường cũng nằm trong runtime dependency set | Nếu source named module tham chiếu module đó, thường khai báo `requires` |
| `provided` | Có ở compile/test, môi trường chạy được kỳ vọng cung cấp | Có thể tương ứng với `requires static` trong một số thiết kế tùy chọn; không tự động tương ứng |
| `runtime` | Cần khi chạy, không nhất thiết cần compile source trực tiếp | Không nên thêm `requires` chỉ vì JAR là runtime dependency; xem cách sử dụng |
| `test` | Phục vụ test | Thường không cần đưa vào descriptor sản phẩm |
| `system` | Phụ thuộc file local cụ thể, thường không khuyến khích | Không thay đổi quy tắc JPMS |

Maven scope không phải chỉ thị JPMS. Một dependency `runtime` có thể là driver được `ServiceLoader` phát hiện; ứng dụng không nhất thiết có `requires` tới module implementation.

## 4. Khai báo dependency trong Gradle

Với Gradle Java plugin hoặc Java Library plugin, một ví dụ Groovy DSL:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
    modularity.inferModulePath = true
}

dependencies {
    implementation 'com.acme:greeting:1.0.0'
}
```

Nếu source có `module-info.java`, build cần dùng module path đúng cho các dependency modular. Gradle có thể suy luận module path trong các cấu hình được hỗ trợ khi bật `inferModulePath`; hãy kiểm tra lệnh biên dịch thực tế khi có JAR không modular hoặc cấu hình tùy chỉnh.

Descriptor vẫn là:

```java
module com.acme.app {
    requires com.acme.greeting;
}
```

Các cấu hình Gradle thường gặp:

| Configuration | Vai trò | Quan hệ thường gặp với descriptor |
|---|---|---|
| `implementation` | API/implementation được dự án dùng để compile và chạy | `requires` khi mã module trực tiếp cần named module |
| `api` (Java Library plugin) | Dependency là một phần API được consumer biên dịch dựa vào | Có thể đi cùng `requires transitive` nếu public API thực sự phơi bày kiểu từ module đó |
| `compileOnly` | Dependency chỉ cần khi compile | Có thể dùng `requires static` nếu runtime cho phép thiếu module đó |
| `runtimeOnly` | Dependency chỉ cần khi chạy | Thường gặp ở service provider hoặc implementation được nạp động |
| `annotationProcessor` | Thư viện chứa annotation processor chạy tại compile time | Cấu hình riêng; không tự động phải `requires` trong application module |
| `testImplementation` | Thư viện phục vụ test | Không đồng nghĩa dependency của module ứng dụng ở production |

**Không đồng nhất** `api` với `requires transitive` hoặc `compileOnly` với `requires static` theo kiểu máy móc. Hai hệ thống phân loại dependency theo mục đích khác nhau; sự phù hợp còn tùy public API và hành vi runtime.

## 5. requires khác requires transitive như thế nào?

Giả sử `com.acme.service` cung cấp public API dùng kiểu `Customer` từ `com.acme.model`:

```java
// Trong com.acme.model
package com.acme.model;

public record Customer(String id) {
}
```

```java
// Trong com.acme.service
package com.acme.service.api;

import com.acme.model.Customer;

public interface CustomerService {
    Customer findById(String id);
}
```

Descriptor module model:

```java
module com.acme.model {
    exports com.acme.model;
}
```

Descriptor module service:

```java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
```

Ứng dụng:

```java
module com.acme.app {
    requires com.acme.service;
}
```

`requires transitive com.acme.model` làm cho các module đọc `com.acme.service` cũng đọc được `com.acme.model`. Điều này hữu ích vì chữ ký public của `CustomerService` chứa kiểu `Customer` thuộc module model.

Khi publish thư viện, Gradle Java Library plugin thường khai báo dependency model ở `api` thay vì `implementation` để consumer có dependency đó trong compile graph:

```groovy
dependencies {
    api 'com.acme:model:1.0.0'
}
```

Nhưng cần viết `requires transitive` trong descriptor nếu muốn JPMS truyền readability như trên. Gradle `api` không tự thay thế directive trong `module-info.java`.

Khi public API **không** phơi bày kiểu từ module khác, ưu tiên `requires` thường đủ. Lạm dụng `requires transitive` làm consumer nhìn thấy các dependency không cần thiết như một phần hợp đồng API.

## 6. requires static và dependency compile-only

`requires static` biểu thị dependency bắt buộc lúc biên dịch nhưng không bắt buộc phải có ở runtime để module hiện tại được phân giải.

Ví dụ ứng dụng chỉ dùng annotation ở compile time:

```java
module com.acme.app {
    requires static com.acme.annotations;
}
```

Gradle:

```groovy
dependencies {
    compileOnly 'com.acme:annotations:1.0.0'
}
```

Maven có thể dùng `provided` khi dependency được cung cấp ngoài môi trường ứng dụng, nhưng ngữ nghĩa Maven `provided` và `requires static` không hoàn toàn giống nhau. Maven `provided` có thể vẫn cần thư viện ở runtime do container cung cấp, còn `requires static` cho phép JPMS phân giải module ngay cả khi module phụ thuộc vắng mặt.

**Điều quan trọng:** `requires static` không làm class của thư viện tự xuất hiện khi ứng dụng chạy. Nếu code path runtime cố nạp một class của module tùy chọn không có mặt, ứng dụng vẫn có thể gặp lỗi nạp class. Chỉ dùng dạng này khi kiến trúc thật sự chấp nhận dependency không tồn tại khi chạy.

Cũng không nên dùng `requires static` chỉ vì muốn làm graph nhỏ hơn nếu thư viện luôn cần cho logic runtime.

## 7. Runtime-only dependency và ServiceLoader

Một số implementation chỉ được sử dụng thông qua Java Service Provider Interface (SPI). Consumer biết service interface, nhưng không import implementation class.

Module SPI:

```java
module com.acme.spi {
    exports com.acme.spi;
}
```

Consumer:

```java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.ReportExporter;
}
```

Provider:

```java
module com.acme.export.csv {
    requires com.acme.spi;
    provides com.acme.spi.ReportExporter
        with com.acme.export.csv.CsvReportExporter;
}
```

Trong Gradle, implementation provider có thể là dependency `runtimeOnly` ở build layer:

```groovy
dependencies {
    implementation 'com.acme:spi:1.0.0'
    runtimeOnly 'com.acme:export-csv:1.0.0'
}
```

Nhưng riêng `runtimeOnly` **không bảo đảm** provider module đã được JPMS resolve. Provider cần có trên module path và được đưa vào graph theo cách phù hợp, ví dụ chọn làm root với `--add-modules`, chọn root khi tạo `ModuleLayer` hoặc thực hiện service binding.

Ví dụ khởi chạy để yêu cầu provider module:

```shell
java --module-path mods \
  --add-modules com.acme.export.csv \
  -m com.acme.app/com.acme.app.Main
```

Không thêm `requires com.acme.export.csv;` vào consumer chỉ để ServiceLoader biết provider; consumer nên dựa vào service interface, không buộc phụ thuộc trực tiếp vào implementation.

## 8. Annotation processor không phải dependency runtime của ứng dụng

Một application module có thể dùng annotation và annotation processor trong build. Hai thành phần này nên được phân biệt:

- Annotation API: source có thể import annotation type; đây là compile dependency.
- Annotation processor: công cụ được `javac` nạp để sinh source/code; đây là dependency **của giai đoạn biên dịch**.

Gradle:

```groovy
dependencies {
    compileOnly 'com.acme:annotations:1.0.0'
    annotationProcessor 'com.acme:codegen-processor:1.0.0'
}
```

Nếu annotation API là một named module và source cần import nó, descriptor có thể có `requires static com.acme.annotations;`. Tuy nhiên, application module **không cần `requires` tới module processor chỉ vì processor chạy lúc build**.

Đối với Maven Compiler Plugin, cấu hình processor path có thể được khai báo tường minh (tùy version plugin) trong `annotationProcessorPaths`. Với modular processor, có thêm cơ chế `--processor-module-path`.

Không đưa processor cùng những dependency như template engine hoặc JavaPoet vào production runtime nếu application không thực sự cần gọi chúng.

## 9. Tên Maven/Gradle artifact không nhất thiết là tên module

Đây là một trong các nguồn gây lỗi phổ biến khi tạo `module-info.java`.

Ví dụ Maven:

```text
groupId    = org.example
artifactId = useful-utils
version    = 3.2
```

Tên JPMS module thực tế có thể là:

```text
org.example.utilities
```

chứ không nhất thiết là `useful.utils`, `org.example.useful.utils` hay chuỗi từ `artifactId`.

Nguồn xác định tên module theo mức độ ưu tiên thực tế:

1. `module-info.class` của explicit module.
2. `Automatic-Module-Name` trong manifest với automatic module.
3. Tên suy ra từ tên file JAR nếu không có hai nguồn trên và JAR được dùng như automatic module.

Có thể kiểm tra bằng:

```shell
jar --describe-module --file libs/useful-utils-3.2.jar
```

Ví dụ kết quả có thể nêu module automatic hoặc descriptor module explicit. Dùng đúng tên hiển thị trong `requires`.

Để xem module thực sự có mặt trong môi trường hiện tại:

```shell
java --module-path libs --list-modules
```

Tuy nhiên, danh sách module **có thể quan sát** không đồng nghĩa toàn bộ đã được resolve trong lần chạy ứng dụng. Dùng `--show-module-resolution` khi cần chẩn đoán graph của lần chạy.

## 10. Automatic module hỗ trợ migration nhưng có giới hạn

Một JAR không có descriptor khi đặt trên module path thường được xử lý như automatic module. Named module ứng dụng có thể khai báo `requires` tới automatic module, nếu tên module xác định được và package không xung đột.

Ví dụ:

```java
module com.acme.app {
    requires legacy.utilities;
}
```

Trong giai đoạn chuyển đổi, automatic module có thể giúp sử dụng thư viện cũ mà chưa phải tự tạo descriptor cho nó. Nhưng có một số giới hạn:

- Tên module có thể không ổn định nếu được suy ra từ tên JAR.
- Mọi package của automatic module được export rộng, nên mức đóng gói yếu.
- Nhiều JAR từ thời classpath có thể chứa split package và gây xung đột khi cùng chuyển lên module path.
- `jlink` không hỗ trợ liên kết automatic modules theo cách dùng explicit modules thông thường.

Vì vậy, không nên coi một dependency khai báo trong Maven/Gradle là luôn có module name ổn định. Khi chọn dependency cho ứng dụng modular dài hạn, ưu tiên artifact có explicit descriptor hoặc metadata module name rõ ràng.

## 11. Khi dependency có mặt nhưng javac vẫn báo package không visible

Một tình huống điển hình:

```java
module com.acme.app {
    requires com.acme.library;
}
```

Compiler báo:

```text
package com.acme.library.internal is not visible
(package ... is declared in module com.acme.library,
 which does not export it)
```

Đây không phải lỗi Maven/Gradle chưa tải được artifact. Module đã được tìm thấy, nhưng package trong thư viện chưa export cho ứng dụng.

Một descriptor như sau:

```java
module com.acme.library {
    exports com.acme.library.api;
}
```

chỉ công bố package `com.acme.library.api`. Thêm dependency ở build file hoặc thêm `requires` nữa không mở được `com.acme.library.internal`.

Cần dùng public API trong package được export hoặc yêu cầu thư viện công bố API hợp lệ. `--add-exports` có thể giúp migration tạm thời nhưng làm phụ thuộc vào cấu trúc nội bộ của thư viện.

Tương tự, `opens` dành cho deep reflection ở runtime, không thay thế `exports` cho việc import và gọi API trực tiếp.

## 12. Khi requires hợp lệ nhưng build báo module not found

Ví dụ:

```text
error: module not found: com.acme.greeting
```

Những nguyên nhân thường gặp:

1. Build tool chưa tải hoặc chưa đưa đúng JAR vào compiler input.
2. JAR nằm trên `--class-path` thay vì `--module-path`.
3. Tên module trong `requires` không khớp descriptor/automatic module name.
4. Version dependency đã bị thay thế, exclude hoặc resolve sang artifact khác.
5. Dependency là module tùy chọn nhưng cấu hình compile không cung cấp nó.
6. Package/module path bị cấu hình khác giữa IDE và CI.

Chẩn đoán:

```shell
jar --describe-module --file libs/com.acme.greeting.jar
```

```shell
javac --module-path mods:libs -d out \
  src/module-info.java \
  src/com/acme/app/Main.java
```

Ví dụ trên dùng dấu hai chấm cho Linux/macOS; Windows dùng dấu chấm phẩy. Trong IDE hoặc build tool, hãy kiểm tra tham số `javac` thật được sinh ra thay vì chỉ nhìn dependency declaration.

## 13. Test dependencies và module descriptor

Các thư viện test như JUnit, mock framework hoặc test utilities thường được khai báo với Maven `test` scope hoặc Gradle `testImplementation`.

Điều đó **không có nghĩa** nên thêm `requires` chúng vào descriptor production của `com.acme.app`. Nếu test code được biên dịch trong module riêng, hãy dùng test module descriptor phù hợp. Nếu test code được patch vào module production, cấu hình test runner có thể cần `--patch-module`, `--add-reads` hoặc `--add-opens` để chạy test.

Ví dụ Gradle:

```groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.0'
}
```

Dependency trên phục vụ test; module descriptor của ứng dụng không tự cần `requires org.junit.jupiter.api;` chỉ vì test source import JUnit.

Mục tiêu là giữ module production phản ánh dependency production, không chứa toàn bộ công cụ hỗ trợ phát triển.

## 14. Dependency resolution, module resolution và runtime image

Ba loại “resolution” dễ bị nhầm:

**Build dependency resolution** của Maven/Gradle: chọn artifact và version cụ thể từ dependency graph.

**JPMS module resolution**: bắt đầu từ root modules, phân giải `requires`, kiểm tra các ràng buộc của module graph và có thể bổ sung provider qua service binding khi được yêu cầu.

**Runtime image linking** của `jlink`: tạo image chứa tập module đã chọn cùng dependency cần thiết.

Một dependency đã được Maven/Gradle tải về không bảo đảm module đó được resolve ở runtime. Một module khai báo `requires` cũng không bảo đảm JAR tương ứng có sẵn nếu deployment bỏ quên artifact.

Khi đóng gói bằng `jlink`, cần kiểm tra ứng dụng và dependency đã có module descriptor phù hợp. Automatic modules hoặc các dependency chỉ nằm trên classpath có thể yêu cầu một chiến lược packaging khác.

Có thể kiểm tra runtime graph:

```shell
java --show-module-resolution \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
```

Nếu dùng custom runtime image, chạy lệnh bằng executable nằm trong image và đối chiếu `--list-modules` để xem module nào thực sự được đóng gói.

## 15. Quy trình đối chiếu dependency với requires

Một quy trình thực hành cho mỗi module ứng dụng hoặc thư viện:

1. **Liệt kê import và public API** của module: xác định kiểu thuộc module nào.
2. **Kiểm tra dependency build**: artifact và version cụ thể đã khai báo trong Maven/Gradle.
3. **Đọc module name từ artifact** bằng `jar --describe-module`.
4. **Chọn requires phù hợp**: `requires` cho dependency thông thường; `requires transitive` khi muốn truyền readability do API công bố; `requires static` nếu compile-time dependency thực sự tùy chọn ở runtime.
5. **Xem trường hợp đặc biệt**: service provider, annotation processor, test library và dependency chỉ dùng reflection.
6. **Kiểm tra module path thực tế** của `javac` và lệnh `java`.
7. **Biên dịch và chạy thử** bằng đúng artifact/dependency version sẽ triển khai.
8. **Dùng `jdeps` và resolution output** để phát hiện sai khác giữa mã, descriptor và graph.

Không cần ép mọi dependency của build tool thành một directive `requires`. Một số thư viện chỉ dùng để test, sinh mã, làm provider hoặc cung cấp resource. Điều quan trọng là xác định **mục đích sử dụng** của từng dependency.

## 16. Bảng tổng hợp các trường hợp điển hình

| Trường hợp | Build dependency thường gặp | JPMS tương ứng |
|---|---|---|
| Source dùng API public từ module X | Maven compile / Gradle implementation | `requires X;` |
| Thư viện công bố API có kiểu từ module X | Maven compile hoặc Gradle api | `requires transitive X;` khi cần truyền readability |
| Source dùng annotation chỉ cần khi compile | Maven provided / Gradle compileOnly | `requires static X;` nếu X là named module cần cho compile |
| Implementation nạp qua ServiceLoader | Maven runtime / Gradle runtimeOnly | Consumer `uses` service type; provider `provides` và phải được resolve |
| Annotation processor chạy khi build | Maven compiler processor config / Gradle annotationProcessor | Không tự động cần `requires` processor trong application module |
| Thư viện chỉ dùng ở test | Maven test / Gradle testImplementation | Không đưa vào descriptor production chỉ vì test cần |
| Framework đọc field private bằng reflection | Thường là runtime/implementation dependency | `opens package to framework.module;` khi cần deep reflection |
| Java SE API thuộc `java.sql` hoặc `java.logging` | Do JDK cung cấp, không có Maven artifact riêng | `requires java.sql;` hoặc `requires java.logging;` |

Nhớ rằng ví dụ trong bảng mô tả quan hệ **thường gặp** chứ không phải phép chuyển tự động 1–1. Khai báo JPMS cần dựa trên module thực tế chứa API và cách code sử dụng nó.

## 17. Các lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `module not found` | Artifact không được đưa vào module path hoặc module name sai | Xác định tên module thật, kiểm tra compiler/runtime path |
| `package ... is not visible` | Thiếu `requires` hoặc package chưa export | Kiểm tra descriptor consumer và provider |
| `reads package ... from both ...` | Split package / conflict giữa module | Loại dependency trùng, relocate package hoặc hợp nhất module |
| Code compile nhưng runtime thiếu class | Build và runtime dependency set khác nhau | Đồng bộ artifact/runtime graph, kiểm tra `requires static` |
| ServiceLoader không có provider | Provider không được resolve hoặc thiếu `provides` | Kiểm tra `uses`, `provides`, root modules và service binding |
| Reflection thất bại | Package chưa mở cho framework | Dùng `opens` thích hợp, không lạm dụng export |
| IDE chạy được nhưng CI lỗi | IDE và build tool phân loại classpath/module path khác | Kiểm tra toolchain, compiler args và dependency resolution |
| Jlink không chấp nhận một dependency | Dependency là automatic module hoặc không phù hợp với linking | Dùng explicit modular artifact hoặc đổi chiến lược packaging |

## 18. Những nguyên tắc cần nhớ

- Maven/Gradle quản lý **artifact và version**; JPMS quản lý **module readability và encapsulation**.
- Không suy ra module name trực tiếp từ Maven `groupId`, `artifactId` hoặc tên file.
- Chỉ dùng `requires transitive` khi cần truyền readability cho các module consumer.
- `requires static` cho phép vắng dependency khi runtime resolution, nhưng code runtime vẫn phải tránh dùng class không có mặt.
- Dependency kiểu `runtimeOnly` không tự bảo đảm provider được resolve trong JPMS.
- Annotation processor và thư viện test thường không phải dependency production của application module.
- `requires` không thay thế `exports`; `opens` giải quyết nhu cầu deep reflection.
- Kiểm tra module path thực tế, descriptor của JAR, `jdeps` và `--show-module-resolution` khi build và runtime không nhất quán.

**Kết luận:** Muốn khai báo dependency chính xác trong ứng dụng modular, cần kết hợp hai góc nhìn. Build tool trả lời “file JAR nào được đưa vào lúc build/chạy”, còn `module-info.java` trả lời “module nào được đọc và công bố API theo hợp đồng JPMS”. Khi hai lớp thông tin được đối chiếu bằng module name thật và chức năng sử dụng thực tế, dự án sẽ biên dịch dễ dự đoán hơn, giảm dependency thừa và tránh nhiều lỗi migration từ classpath sang module path.