# Java Module System và những điểm cần cấu hình trong Gradle build

**Java Platform Module System (JPMS)**, ra đời từ Java 9, bổ sung một lớp ranh giới lên trên package và classpath truyền thống: ứng dụng có thể chia thành **named modules**, mô tả module nào đọc module nào, package nào được công khai, package nào dành riêng cho nội bộ, và dịch vụ nào được cung cấp hoặc sử dụng. Trong Gradle, muốn sử dụng JPMS đúng cần phối hợp **`module-info.java`**, các **Gradle dependency configurations**, lựa chọn **module path thay vì classpath**, cách chạy ứng dụng, chiến lược kiểm thử và việc xử lý thư viện chưa modular hóa.

Ví dụ: một ứng dụng `:app` gọi public API của thư viện `:library`. Nếu `:library` có `module-info.java` nhưng quên `exports` package chứa API, project `:app` có thể vẫn resolve dependency thành công qua Gradle, song Java compiler sẽ **không cho phép truy cập package**. Ngược lại, nếu module descriptor viết `requires demo.greeter` nhưng Gradle không đưa module đó lên **module path**, việc biên dịch cũng có thể thất bại. **Gradle dependency và JPMS readability là hai tầng hợp đồng khác nhau, cần nhất quán.**

Bài học này trình bày tư duy mô hình, các directive của `module-info.java`, cơ chế Gradle tự suy luận module path, ví dụ **ba subproject Java 17 chạy được** (không cần dependency bên ngoài), cấu hình `application.mainModule`, thư viện automatic/unnamed module, unit/black-box test, module packaging, công cụ chẩn đoán và những lỗi phổ biến.

## 1. Trước khi có JPMS: classpath làm được gì, thiếu gì?

Ứng dụng Java truyền thống thường chạy với:

```bash
java --class-path "libs/*:build/classes/java/main" demo.Main
```

Dấu phân cách trong classpath là `:` trên Unix và `;` trên Windows; ví dụ trên dùng Unix. Ở chế độ truyền thống, các classes trên classpath thuộc **unnamed module**. Một JAR có public class thường có thể được class khác trên classpath tham chiếu (subject to Java access modifiers) và không có module descriptor để quy định package-level exports.

JPMS bổ sung cơ chế:

```bash
java --module-path path/to/modules --module demo.app/demo.app.Main
```

Trong đó:

- **`--module-path`** (`-p`): nơi chứa named modules; Java launcher đọc metadata để tìm module và quan hệ giữa chúng.
- **`--module`** (`-m`): tên module được chạy và tùy chọn fully qualified main class.
- **`module-info.java`**: khai báo module name, `requires`, `exports`, `opens`, `uses`, `provides`.
- **`java.base`**: module nền tảng được mọi module đọc ngầm, nên không phải tự viết `requires java.base;`.

Mục tiêu không chỉ là đổi syntax của lệnh `java`. JPMS giúp:

1. **Strong encapsulation**: chỉ những package được export/open theo quy tắc mới lộ ra ngoài module.
2. **Explicit readability**: một named module cần khai báo đọc những module mà code của nó dựa vào.
3. **Reliable configuration**: JVM có thêm khả năng báo lỗi thiếu module hoặc package conflict trước khi ứng dụng đi sâu vào runtime.
4. **Service binding**: module có thể công bố rõ nơi dùng và cung cấp service provider.
5. **Tùy chọn runtime image nhỏ hơn**: những công cụ như `jlink` có thể đóng gói runtime tùy biến từ các modules phù hợp, nếu dependency graph và loại modules đáp ứng yêu cầu.

**JPMS không bắt buộc đối với mọi Java project.** Một Java 17 application không có `module-info.java` vẫn có thể chạy bình thường bằng classpath; Gradle Java plugin không tự biến mọi project thành named module.

## 2. Named module, automatic module, unnamed module

| Loại | Cách hình thành | Có tên module ổn định? | `exports`/`requires` cụ thể? | Gradle module-path inference |
| --- | --- | --- | --- | --- |
| **Explicit named module** | Source có `module-info.java`, JAR có `module-info.class` | Có, do descriptor định nghĩa | Có | Nhận diện `module-info.class` |
| **Automatic module có manifest name** | JAR có `Automatic-Module-Name` nhưng không có descriptor | Có, do manifest chỉ định | Tự động export các packages và đọc modules phù hợp theo JPMS | Nhận diện manifest entry |
| **Plain JAR/legacy classpath library** | Không có `module-info.class` hoặc `Automatic-Module-Name` | Trên classpath: thuộc unnamed module; trên module path do JVM xử lý có thể được suy tên automatic nhưng không nên dựa vào đó | Không có descriptor tường minh | Gradle thường giữ ở **classpath** theo inference |
| **Unnamed module** | Các classes/JARs nằm trên classpath | Không có tên để `requires` | Package visibility theo classpath/access rules | Là kết quả đặt library trên classpath |

**Chi tiết thường bị hiểu sai:** JDK có thể suy ra tên automatic module từ **tên tệp JAR khi JAR được đặt thủ công trên module path**. Nhưng thuật toán **Gradle inferModulePath** dùng dấu hiệu đáng tin như `module-info.class` hoặc `Automatic-Module-Name`. Vì vậy một plain Maven JAR không có các dấu hiệu này **không tự được Gradle chuyển lên module path** chỉ vì nó có thể trở thành automatic module ở JVM nếu ép đặt lên đó.

**Named module không thể `requires` một unnamed module.** Nếu source của bạn nằm trong một named module nhưng dependency lại chỉ có trên classpath/unnamed module, bạn cần chiến lược migrate/adapt, không chỉ thêm `requires group.artifact;` rồi mong Gradle tự sửa.

## 3. `module-info.java` là hợp đồng của module

Một module descriptor nằm ở:

```text
src/main/java/module-info.java
```

Ví dụ:

```java
module demo.catalog {
    requires java.logging;
    exports demo.catalog.api;
    opens demo.catalog.model;
}
```

Ý nghĩa:

- `module demo.catalog`: **tên module** được Java module system nhận diện; không phải Maven group/name hay Gradle project path.
- `requires java.logging`: module này có quyền đọc public exported packages của `java.logging`, dùng cho Java logging API.
- `exports demo.catalog.api`: các **public types** trong package đó có thể truy cập ở compile/runtime từ module khác đọc `demo.catalog`.
- `opens demo.catalog.model`: cho phép reflective access sâu đến package đó theo các quy tắc của JPMS; không giống việc export cho compiler.
- Những packages không được export/open vẫn có thể được code **bên trong chính module** sử dụng, nhưng bị encapsulate đối với modules bên ngoài.

Đây là một **module-info.java minh họa**. Nếu muốn compiler chấp nhận `exports`/`opens` trong project hoàn chỉnh, phải có các packages/classes tương ứng. Bài thực hành đầy đủ ở phần 7 sử dụng descriptor thống nhất với source.

### Các directive phổ biến

| Directive | Cơ chế | Khi nào dùng |
| --- | --- | --- |
| `requires M;` | Module hiện tại đọc module M | Internal dependency hoặc dependency thường |
| `requires transitive M;` | Module đọc M, và modules đọc module hiện tại cũng đọc M một cách ngầm | Public API dựa vào types của M |
| `requires static M;` | Yêu cầu M lúc compile, không bắt buộc hiện diện lúc runtime | Compile-time-only types/annotations |
| `requires static transitive M;` | Compile-time-only dependency được công khai cho consumers phù hợp | Public compile-time contract |
| `exports pkg;` | Cho các modules khác truy cập public types của package | Public Java API |
| `exports pkg to M;` | Chỉ export package cho module M | API chọn lọc cho bạn bè/thành phần cụ thể |
| `opens pkg;` | Cho reflective access sâu vào package | Serialization/ORM/DI reflection có chủ đích |
| `opens pkg to M;` | Chỉ mở reflection cho module M | Framework cần reflective field/constructor access |
| `uses api.Service;` | Module dùng service interface qua `ServiceLoader` | Service consumer |
| `provides api.Service with impl.Provider;` | Module cung cấp provider implementation | Plugin/provider module |
| `open module M { ... }` | Mở reflective access cho mọi package trong module | Migration tạm thời; hạn chế trong thiết kế mới |

`exports` và `opens` giải quyết hai nhu cầu **khác nhau**: một cái cho phép **truy cập compile-time thông thường**, cái còn lại cho phép **reflection sâu**. Đừng mở toàn bộ module chỉ để compile được một public API.

## 4. Gradle cấu hình module path như thế nào?

Với Java plugin hoặc `java-library`, Gradle có thuộc tính:

```kotlin
java {
    modularity.inferModulePath.set(true)
}
```

**Giá trị này đã là mặc định `true` trên các phiên bản Gradle hiện đại** (từ Gradle 7.0). Ghi tường minh có thể hữu ích khi giải thích hoặc khi build từng bị tắt tính năng.

Gradle quyết định chuyển dependency entry từ traditional classpath sang **module path** trong một task Java phù hợp khi:

1. Inference **không bị tắt** (tại Java extension hoặc task).
2. **Source set được coi là modular** — thông thường `src/main/java/module-info.java` có mặt, hoặc trường hợp automatic-module project theo cơ chế Gradle hỗ trợ.
3. Dependency JAR/classes directory có **`module-info.class`** hoặc **manifest `Automatic-Module-Name`**.

Khi đó Gradle có thể đặt các dependencies modular lên `--module-path` cho `javac`, `java`, `javadoc` hoặc các task JVM phù hợp; phần còn lại có thể vẫn nằm trên classpath, nhưng named module không tự đọc unnamed module.

### Bạn cần cấu hình gì tối thiểu?

Đối với project Java thuần (không dependencies ngoài), thường chỉ cần:

```kotlin
plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

và `src/main/java/module-info.java`. Không cần tự tạo biến `--module-path` bằng cách ghép đường dẫn JAR thủ công. Gradle tự nhận diện modular source set khi project/plugin được cấu hình phù hợp.

Nếu bạn sử dụng `application` plugin để **chạy ứng dụng modular**, còn cần `application.mainModule` (phần 7). Nếu một project chỉ tạo library JAR, không cần `mainModule`.

### Khi nào tắt inference?

Nếu đang migrate legacy build, cần plugin bên thứ ba điều khiển module path riêng hoặc cần chẩn đoán manual JPMS arguments, có thể dùng:

```kotlin
java {
    modularity.inferModulePath.set(false)
}
```

Hoặc chỉ với một JavaCompile task:

```kotlin
tasks.named<JavaCompile>("compileJava") {
    modularity.inferModulePath.set(false)
}
```

Đoạn thứ hai cần project đã áp dụng Java plugin; `JavaCompile` là task type từ Gradle API. **Tắt inference không làm `module-info.java` biến mất**; compiler vẫn thấy module descriptor và có thể lỗi khi dependencies không được bố trí đúng. Đây là tùy chọn cho trường hợp kiểm soát module path thủ công, không phải cách chữa mặc định khi JPMS báo lỗi.

## 5. Gradle dependency configurations và JPMS `requires` phải đồng bộ

Đối với `java-library`, ánh xạ ý định thường là:

| `module-info.java` | `build.gradle.kts` | Vì sao |
| --- | --- | --- |
| `requires other.module;` | `implementation(...)` | Module hiện tại cần thư viện, không tự truyền quyền đọc module cho consumer |
| `requires transitive other.module;` | `api(...)` | Public API dựa vào other.module; consumer cũng cần thấy module khi compile |
| `requires static other.module;` | `compileOnly(...)` | Cần lúc compile, không bắt buộc có lúc runtime |
| `requires static transitive other.module;` | `compileOnlyApi(...)` | Public compile-time contract không tự mang dependency vào runtime |
| Runtime service/provider không dùng trong source compile | `runtimeOnly(...)` | Provider cần ở runtime, không nhất thiết ở compiler classpath |

**Không có một-to-one mapping bắt buộc cho mọi plugin/variant**, nhưng bảng là hướng dẫn chuẩn Gradle cho Java library. Đặc biệt, **Gradle hiện không tự kiểm tra rằng các `requires` và dependency declarations luôn khớp nhau**. Bạn phải bảo đảm cả hai tầng đúng.

Một tình huống hay gặp:

```kotlin
// library/build.gradle.kts
dependencies {
    implementation(project(":contracts"))
}
```

nhưng descriptor:

```java
module demo.greeter {
    requires transitive demo.contracts;
}
```

JPMS nói consumer phải đọc `demo.contracts`, nhưng Gradle implementation scope có thể không đưa dependency đó vào **compileClasspath của consumer**. Cách đồng bộ với public contract là `api(project(":contracts"))`.

Ngược lại, nếu đã dùng `api(project(":contracts"))` nhưng descriptor viết `requires demo.contracts;` không có `transitive`, consumer compiler ở module path có thể vẫn báo rằng module tiêu thụ **không đọc** `demo.contracts` khi source của consumer dùng kiểu của module đó. Đây là hai lỗi khác nhau:

- Thiếu Gradle API dependency exposure → thiếu artifact trên compile classpath/module path.
- Thiếu JPMS transitive readability → artifact có thể có trên module path nhưng module consumer không được đọc nó.

## 6. Phân biệt module name, Gradle project path và Maven coordinates

| Khái niệm | Ví dụ | Dùng ở đâu |
| --- | --- | --- |
| Gradle subproject path | `:library` | `project(":library")`, `./gradlew :library:jar` |
| JPMS module name | `demo.greeter` | `module demo.greeter { ... }`, `requires demo.greeter;`, `--module demo.greeter/...` |
| Maven coordinates | `org.example:greeter:1.0` | `implementation("org.example:greeter:1.0")` khi dùng external artifacts |
| Java package | `demo.greeter.api` | `exports demo.greeter.api;`, `import demo.greeter.api.GreeterFactory;` |
| Java main class | `demo.app.Main` | `mainClass.set("demo.app.Main")` |

**Các tên này có thể giống nhau nhưng không bắt buộc.** Gradle tìm artifacts theo project path hoặc coordinates, còn JPMS tìm modules theo tên được công bố bởi `module-info.class` hoặc `Automatic-Module-Name`. Đặt `requires library;` chỉ vì subproject tên là `:library` sẽ sai nếu descriptor của nó khai báo `module demo.greeter`.

Tên JPMS module thường theo reversed-domain convention, chẳng hạn `com.company.api`; tránh dấu gạch ngang của Maven artifactId trong module name.

## 7. Ví dụ hoàn chỉnh: ba Java modules với Gradle Kotlin DSL

Ví dụ gồm ba subprojects, **không cần download thư viện từ Maven Central**:

1. **`:contracts`**: cung cấp interface `Greeter` trong JPMS module `demo.contracts`.
2. **`:library`**: cung cấp factory `GreeterFactory`, có implementation nội bộ, JPMS module `demo.greeter`.
3. **`:app`**: chương trình Java chạy được, JPMS module `demo.app`.

`:library` công khai **kiểu của `:contracts` trong public method signature**, nên nó phải khai báo đồng thời:

- `api(project(":contracts"))` trong Gradle.
- `requires transitive demo.contracts;` trong JPMS module descriptor.

Ứng dụng `:app` chỉ `requires demo.greeter;` nhưng nhờ JPMS transitive readability và Gradle API variant, vẫn dùng được interface `Greeter`.

### 7.1. Cây thư mục đầy đủ

```text
jpms-gradle-demo/
├── settings.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/...
├── contracts/
│   ├── build.gradle.kts
│   └── src/main/java/
│       ├── module-info.java
│       └── demo/contracts/api/Greeter.java
├── library/
│   ├── build.gradle.kts
│   └── src/main/java/
│       ├── module-info.java
│       ├── demo/greeter/api/GreeterFactory.java
│       └── demo/greeter/internal/DefaultGreeter.java
└── app/
    ├── build.gradle.kts
    └── src/main/java/
        ├── module-info.java
        └── demo/app/Main.java
```

Yêu cầu: Gradle Wrapper phiên bản hỗ trợ Java toolchain 17 và JPMS inference (Gradle 7+ hoặc bản hiện hành phù hợp), JDK 17 hoặc toolchain provisioning được cấu hình, hệ điều hành có thể chạy `./gradlew`/`gradlew.bat`. Không bắt buộc tạo file `build.gradle.kts` ở root cho demo này.

### 7.2. File `settings.gradle.kts`

```kotlin
rootProject.name = "jpms-gradle-demo"

include("contracts", "library", "app")
```

Tên projects là `:contracts`, `:library`, `:app`; tên modules nằm trong từng `module-info.java` và **không phải các Gradle paths**.

### 7.3. `contracts/build.gradle.kts`

```kotlin
plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

### 7.4. `contracts/src/main/java/module-info.java`

```java
module demo.contracts {
    exports demo.contracts.api;
}
```

Module `demo.contracts` chỉ export package `demo.contracts.api` để modules khác dùng public types. Không cần `requires java.base` vì JPMS đọc `java.base` ngầm.

### 7.5. `contracts/src/main/java/demo/contracts/api/Greeter.java`

```java
package demo.contracts.api;

public interface Greeter {
    String greet(String name);
}
```

Đây là Java interface tối thiểu. Module khác có thể import nó nếu đọc module `demo.contracts` và package được export.

### 7.6. `library/build.gradle.kts`

```kotlin
plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    // Public API của :library trả về Greeter từ :contracts.
    api(project(":contracts"))
}
```

`java-library` cho phép `api`. Nếu dùng `implementation(project(":contracts"))`, `:library` vẫn có thể compile, nhưng consumer compiler sẽ không được công bố `:contracts` qua API variant như cần cho public signature.

### 7.7. `library/src/main/java/module-info.java`

```java
module demo.greeter {
    requires transitive demo.contracts;

    exports demo.greeter.api;
}
```

Đây là hai quyết định:

- `requires transitive demo.contracts`: code bên trong library đọc `demo.contracts`, và các modules đọc `demo.greeter` sẽ đọc `demo.contracts` theo cơ chế transitive readability.
- `exports demo.greeter.api`: public factory được phép truy cập từ modules khác.

**Không có `exports demo.greeter.internal;`**. Mã trong `demo.greeter.internal` vẫn được factory dùng vì chúng ở cùng một module; consumer không được import trực tiếp internal class dù class được khai báo `public`.

### 7.8. `library/src/main/java/demo/greeter/internal/DefaultGreeter.java`

```java
package demo.greeter.internal;

import demo.contracts.api.Greeter;

public final class DefaultGreeter implements Greeter {
    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

Class được khai báo `public` để factory trong package khác **cùng module** có thể instantiate. Nó vẫn không thuộc public API của module vì package `demo.greeter.internal` không được export.

### 7.9. `library/src/main/java/demo/greeter/api/GreeterFactory.java`

```java
package demo.greeter.api;

import demo.contracts.api.Greeter;
import demo.greeter.internal.DefaultGreeter;

public final class GreeterFactory {
    private GreeterFactory() {
    }

    public static Greeter create() {
        return new DefaultGreeter();
    }
}
```

Kiểu trả về `Greeter` là **public contract**. Đây là lý do `requires transitive demo.contracts` và `api(project(":contracts"))` phải đi cùng nhau.

### 7.10. `app/build.gradle.kts`

```kotlin
plugins {
    application
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(project(":library"))
}

application {
    // Đúng tên JPMS module trong app/src/main/java/module-info.java.
    mainModule.set("demo.app")

    // Fully qualified Java class chứa public static void main.
    mainClass.set("demo.app.Main")
}
```

`application` áp dụng Java plugin, tạo task `run` và các distribution tasks. Đối với ứng dụng modular, **cả `mainModule` và `mainClass` đều quan trọng**: Gradle dùng chúng để chạy main trong đúng module qua Java launcher.

### 7.11. `app/src/main/java/module-info.java`

```java
module demo.app {
    requires demo.greeter;
}
```

Bạn **không cần** thêm `requires demo.contracts;` trong ví dụ này vì `demo.greeter` đã khai báo `requires transitive demo.contracts;`. Tuy nhiên app vẫn cần contracts module được resolve trên module path; phần **Gradle `api(project(":contracts"))`** đảm bảo dependency đó được công bố cho consumer compile variant.

### 7.12. `app/src/main/java/demo/app/Main.java`

```java
package demo.app;

import demo.contracts.api.Greeter;
import demo.greeter.api.GreeterFactory;

public final class Main {
    public static void main(String[] args) {
        Greeter greeter = GreeterFactory.create();
        System.out.println(greeter.greet("Gradle"));
    }
}
```

Trong mã nguồn `:app`, `Greeter` là kiểu **đến từ module `demo.contracts`**, được đọc transitively thông qua `demo.greeter`. Code không import `DefaultGreeter`, nên tôn trọng ranh giới API do `:library` công bố.

### 7.13. Chạy và kiểm chứng

Trên Linux/macOS:

```bash
./gradlew :app:compileJava --console=plain
./gradlew :app:run --quiet
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat :app:compileJava --console=plain
.\gradlew.bat :app:run --quiet
```

Khi Gradle Wrapper/JDK phù hợp và các file đúng như trên, **stdout của Java Main** là:

```text
Hello, Gradle!
```

Đây là dòng duy nhất do `Main.main` in ra. Gradle console có thể có thông tin build riêng, cảnh báo hoặc tiến độ tùy môi trường. Không nên coi toàn bộ terminal output luôn chỉ có một dòng.

`:app:run` biên dịch các project prerequisites cần thiết rồi chạy ứng dụng qua Application plugin. **Không cần tự tạo lệnh `javac --module-path ...` trong build script** vì Gradle đã hiểu Java module descriptors và project dependencies.

### 7.14. Xác minh module descriptors trong artifacts

Chạy:

```bash
./gradlew :contracts:jar :library:jar :app:jar
```

Sau đó kiểm tra các JARs trong `contracts/build/libs`, `library/build/libs`, `app/build/libs`. Có thể dùng công cụ JDK:

```bash
jar --describe-module --file library/build/libs/library.jar
```

Đường dẫn `library.jar` **chỉ đúng nếu archive name mặc định chưa bị đổi và không có version suffix**. Nếu project gán `version`, filename có thể thành `library-<version>.jar`. Hãy xác định tên JAR thực tế trước khi chạy lệnh `jar --describe-module`.

Descriptor trong JAR phải có module `demo.greeter`, `requires transitive demo.contracts` và `exports demo.greeter.api`. Nếu JAR không có `module-info.class`, kiểm tra source path và task `compileJava`/packaging.

## 8. Thử nghiệm trước–sau: tại sao cần `requires transitive`?

Bắt đầu từ project chạy được ở phần 7.

**Thử nghiệm A:** trong `library/src/main/java/module-info.java`, đổi:

```java
requires transitive demo.contracts;
```

thành:

```java
requires demo.contracts;
```

Giữ `api(project(":contracts"))` ở Gradle. Khi `:app` import `Greeter` từ module `demo.contracts`, `javac` có thể báo rằng package `demo.contracts.api` **không visible** vì `demo.app` không đọc `demo.contracts` transitively. Dependency artifact có thể vẫn ở module path; vấn đề là **JPMS readability**.

Giải pháp phù hợp với public API trả về `Greeter` là **khôi phục `requires transitive demo.contracts;`**. Bạn cũng có thể thêm `requires demo.contracts;` vào `:app` nếu app có dependency trực tiếp và chủ ý dùng contracts, nhưng cách đó không thay thế nghĩa vụ công bố đúng public API của thư viện với các consumer khác.

**Thử nghiệm B:** khôi phục `requires transitive`, nhưng trong `library/build.gradle.kts` đổi:

```kotlin
api(project(":contracts"))
```

thành:

```kotlin
implementation(project(":contracts"))
```

Library vẫn có thể compile, nhưng `:app` có thể thiếu `:contracts` trên compile module path thông qua API variant. Đây là lỗi **Gradle dependency exposure**. Sửa bằng cách giữ `api` vì `Greeter` xuất hiện trong chữ ký public của `GreeterFactory.create()`.

**Bài học:** `requires transitive` là quy tắc **Java module readability**, còn `api` là quy tắc **Gradle consumer compile dependency exposure**. Không bên nào tự thay thế bên kia.

## 9. Thử nghiệm ranh giới: package `internal` không được export

Trong `:app/src/main/java/demo/app/Main.java`, thử thêm import:

```java
// Ví dụ sai có chủ đích, không thêm vào bản chạy chuẩn:
import demo.greeter.internal.DefaultGreeter;
```

Dù `DefaultGreeter` được khai báo `public`, package `demo.greeter.internal` không được `demo.greeter` export. Java compiler modular sẽ chặn import từ `:app`.

Thông báo có thể có dạng:

```text
package demo.greeter.internal is not visible
(package demo.greeter.internal is declared in module
 demo.greeter, which does not export it)
```

Đây là **dạng lỗi minh họa**, không cam kết đúng từng ký tự cho mọi phiên bản JDK. Sau thử nghiệm, xóa import và giữ `Main.java` của phần 7.

Không nên sửa bằng cách export cả `demo.greeter.internal` chỉ để consumer dùng được. Nếu cần expose behavior, hãy thêm public API ở `demo.greeter.api`. Đó là lợi ích quan trọng nhất của JPMS: **package visibility theo module**, không chỉ dựa vào `public` class modifier.

## 10. `exports` và `opens`: compiler access khác deep reflection

Java access modifiers, module exports và module opens không giải quyết cùng một vấn đề.

```java
module demo.customer {
    exports demo.customer.api;
    opens demo.customer.model;
}
```

- Với `exports demo.customer.api;`, consumer compiler được dùng **public classes** trong package này nếu consumer module đọc `demo.customer`.
- Với `opens demo.customer.model;`, thư viện framework dùng reflection (ORM, serializer, DI) có thể truy cập sâu vào fields/constructors trong package, theo quy tắc Java reflection.
- **`opens` không cho consumer biên dịch một import thông thường** như `exports`; nó phục vụ runtime reflective access.
- `exports ... to some.module` hoặc `opens ... to some.module` giới hạn việc cho phép vào một danh sách named modules cụ thể.

Ví dụ chỉ mở cho một framework:

```java
module demo.customer {
    requires framework.module;

    exports demo.customer.api;
    opens demo.customer.model to framework.module;
}
```

Đây là **descriptor khái niệm**: `framework.module` là tên minh họa, không phải module đã xác nhận tồn tại trong JDK hay Maven. Trước khi dùng thật, phải kiểm tra tên JPMS module của framework, cách framework xử lý reflection và module dependencies thực sự.

### Tạm xử lý reflection bằng JVM flags

Khi migrate code cũ, có thể phải thử:

```bash
java --add-opens demo.customer/demo.customer.model=ALL-UNNAMED ...
```

Hoặc nếu đã xác định chính xác đối tượng truy cập:

```kotlin
// Mảnh ghép vào build.gradle.kts đã có application plugin.
tasks.named<JavaExec>("run") {
    jvmArgs(
        "--add-opens",
        "demo.customer/demo.customer.model=ALL-UNNAMED"
    )
}
```

`JavaExec` là Gradle task type; ví dụ này **chỉ có ý nghĩa khi module/package thật sự tồn tại**. Flag `ALL-UNNAMED` áp dụng cho code trên classpath/unnamed modules. Với một framework named module, có thể cần đích là **đúng tên module** thay vì `ALL-UNNAMED`.

**Không dùng `--add-opens` hoặc `--add-exports` làm giải pháp mặc định lâu dài**. Chúng có thể làm yếu đóng gói strong encapsulation. Trước tiên sửa descriptor hoặc thay cách framework sử dụng reflection theo tài liệu chính thức.

## 11. `uses` và `provides`: ServiceLoader qua module descriptor

JPMS mô tả dịch vụ không chỉ bằng `META-INF/services` truyền thống mà còn bằng module directives:

```java
// Trong module consumer có gọi ServiceLoader.load(Formatter.class):
module demo.app {
    requires demo.spi;
    uses demo.spi.Formatter;
}
```

```java
// Trong module provider chứa implementation:
module demo.formatter.impl {
    requires demo.spi;
    provides demo.spi.Formatter
        with demo.formatter.impl.UpperFormatter;
}
```

Các đoạn này là **minh họa**, không phải phần của project chạy được ở phần 7. Cần có interface `Formatter`, provider class thích hợp và module `demo.spi` trong project thực tế.

Điểm chính:

1. Module **service consumer** khai báo `uses ServiceType` nếu sử dụng service loading theo mô hình module.
2. Module **provider** khai báo `provides ServiceType with ImplementationClass`; provider implementation có thể nằm trong package **không export**, vì Java module descriptor đã mô tả provider binding.
3. Gradle dependency phù hợp (thường `runtimeOnly` cho provider không dùng khi compile) phải giúp artifact/provider module xuất hiện trong runtime module graph.
4. **Phải kiểm thử service discovery thực tế**; có JAR trên classpath/module path không bảo đảm provider được tìm nếu metadata hoặc module graph sai.
5. `ServiceLoader` trong Java module world khác với việc tự gọi `Class.forName` hoặc import implementation class.

### `runtimeOnly` với service provider

Một consumer compile với API:

```kotlin
dependencies {
    implementation(project(":spi"))
    runtimeOnly(project(":provider"))
}
```

Đây là **mảnh ghép Gradle** cho kiến trúc SPI; muốn chạy cần đủ source files, module descriptors và ServiceLoader. Đừng đưa provider JAR vào `api` chỉ để service có sẵn nếu consumer source không tham chiếu implementation type.

## 12. External libraries: explicit, automatic và legacy JAR

Dự án thực tế hiếm khi chỉ dùng JDK và project modules. Khi thêm third-party libraries, phải kiểm tra **chúng cung cấp JPMS metadata ở phiên bản nào**.

Một ví dụ tham khảo theo tài liệu Gradle:

```kotlin
dependencies {
    implementation("com.google.code.gson:gson:2.13.1")
    implementation("org.apache.commons:commons-lang3:3.10")
    implementation("commons-cli:commons-cli:1.4")
}
```

Tùy chính xác các artifact versions:

- Gson có **explicit module descriptor**, tên ví dụ `com.google.gson`.
- Commons Lang 3.10 có **`Automatic-Module-Name`**, tên `org.apache.commons.lang3`; nó hoạt động như automatic module theo cơ chế Gradle.
- Commons CLI 1.4 không có module metadata theo ví dụ Gradle, nên được đặt trên classpath/unnamed module.

Với một module mô-đun hóa:

```java
module demo.my.library {
    requires com.google.gson;
    requires org.apache.commons.lang3;
    // Không thể requires unnamed module từ commons-cli 1.4.
}
```

Đây là **descriptor minh họa** và chỉ biên dịch trong project có packages/source/dependencies phù hợp. Ví dụ thư viện và version cụ thể ở trên dựa trên cách Gradle minh họa các loại JAR; **kiểm tra module descriptors/manifests của đúng artifact version bạn dùng** vì metadata có thể thay đổi ở bản mới.

### Vì sao một JAR legacy khó dùng từ named module?

Khi Gradle để JAR đó ở classpath, classes nằm trong **unnamed module**. Một explicit named module không thể đơn giản `requires` unnamed module vì nó không có tên để được yêu cầu. Có các hướng giải quyết, theo ưu tiên:

1. **Nâng cấp hoặc đổi thư viện** sang bản có explicit `module-info.class` hoặc manifest `Automatic-Module-Name`.
2. **Tạo adapter/wrapper module** có tên ổn định, dùng cơ chế build/publish phù hợp, bảo toàn license và không sửa nội dung artifact gốc tùy tiện.
3. **Dùng artifact transform** để bổ sung module descriptor nếu bạn sở hữu/kiểm soát build và hiểu hậu quả đối với dependencies/exports.
4. **Giữ thành phần legacy trên classpath** và thiết kế ranh giới giao tiếp riêng, nếu đó là quyết định kiến trúc; có thể phải chạy một phần app theo mô hình classpath thay vì cố ép mọi package thành named modules.
5. Chỉ dùng các JVM `--add-reads`/`--add-opens` workaround có phạm vi nhỏ, được kiểm thử đầy đủ, khi không thể thay thế ngay.

**Đừng tự đặt tên module bằng cách đoán từ tên JAR**. Một library có `Automatic-Module-Name` là chuẩn ổn định hơn suy tên tự động theo filename; khi đổi version hoặc classifier, filename có thể đổi và làm tên module không như bạn nghĩ.

## 13. Tạo automatic module cho chính library chưa sẵn sàng modular hóa

Nếu thư viện bạn xuất bản **chưa muốn thêm `module-info.java`**, nhưng muốn hỗ trợ Gradle/JDK consumers modular ổn định hơn, thêm manifest:

```kotlin
plugins {
    `java-library`
}

tasks.named<Jar>("jar") {
    manifest {
        attributes("Automatic-Module-Name" to "demo.legacy.adapter")
    }
}
```

Đây là một file build Kotlin DSL cơ bản hợp lệ cho module có Java source. Nó không biến library thành **explicit named module**: không có `module-info.class`; JVM xem JAR như **automatic module** khi đặt trên module path, với exports/reads rộng hơn.

**Ưu điểm**: chọn được module name ổn định để consumer `requires demo.legacy.adapter;`. **Giới hạn**: không có đóng gói chặt `exports`/`opens` như explicit module; các dependencies và compatibility phải được xem xét riêng.

Khi đã sẵn sàng thiết kế API boundary nghiêm ngặt, chuyển sang `module-info.java` đúng tên đã công bố trong manifest để tránh breaking module name change. Không nên giữ `Automatic-Module-Name` khác với tên explicit module descriptor trong cùng một JAR.

## 14. Kiểm thử modular projects: white-box và black-box

Đây là một phần **dễ hiểu nhầm nhất**. Theo tài liệu Gradle về Java testing, một source set **không có `module-info.java` của riêng nó** thường được xử lý như thư viện Java truyền thống ở compile/test execution: các dependencies có thể nằm trên **classpath**. Vì vậy với source set `test` mặc định, nếu chỉ có `src/main/java/module-info.java` nhưng **không** có `src/test/java/module-info.java`, Gradle có thể chạy test theo **classpath/white-box**.

### 14.1. Unit test white-box trên classpath

Ví dụ một library có JUnit 5 test:

```kotlin
// Đoạn bổ sung vào library/build.gradle.kts
repositories {
    mavenCentral()
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.11.4")
}

tasks.test {
    useJUnitPlatform()
}
```

Với một file **`library/src/test/java/demo/greeter/api/GreeterFactoryTest.java`**:

```java
package demo.greeter.api;

import demo.contracts.api.Greeter;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreeterFactoryTest {
    @Test
    void createsGreeter() {
        Greeter greeter = GreeterFactory.create();
        assertEquals("Hello, Gradle!", greeter.greet("Gradle"));
    }
}
```

Chạy:

```bash
./gradlew :library:test --console=plain
```

Đoạn mở rộng này cần Maven Central để lấy JUnit. Vì test source set **không có test module descriptor**, bạn đang kiểm tra hành vi library **mà không nhất thiết đang kiểm thử strong encapsulation tại JPMS runtime**. Unit test PASS không chứng minh rằng application là named module hợp lệ.

### 14.2. Black-box integration test

Để kiểm tra đúng ranh giới JPMS, tạo một **consumer named module độc lập** làm test harness. Trong ví dụ phần 7, chính `:app` là một consumer modular có thể dùng để kiểm tra integration; nó chỉ được import `demo.greeter.api` thay vì internal classes.

Một mô hình khác là tạo `:integration-tests` subproject hoặc custom source set có `module-info.java` riêng, `requires demo.greeter`, các test framework dependencies phù hợp, và chạy trên module path. Điều này xác minh exports/readability từ góc nhìn consumer.

**Không mặc định rằng các JUnit test frameworks sẽ hoạt động hoàn toàn trên module path chỉ cần thêm `module-info.java` vào tests.** JUnit engines/launchers, test discovery, reflective access và task test JVM arguments có thể cần cấu hình riêng.

### 14.3. White-box qua `--patch-module`

Khi muốn test truy cập internals nhưng vẫn chạy trong modular runtime, JPMS cho phép **patch test classes vào module đang test**. Các JVM/compiler flags có thể gồm `--patch-module`, `--add-reads`, `--add-opens` tùy cách test framework hoạt động.

Gradle **không cung cấp một cấu hình white-box module patching duy nhất, tự động phù hợp với mọi framework**, nên phải thiết kế cách compile/run tests theo nhu cầu thực tế và kiểm thử trên phiên bản JDK/Gradle được hỗ trợ. Đừng copy các flags từ tutorial sang production mà không hiểu module target và path.

### Khi nào chọn loại nào?

| Loại test | Ranh giới JPMS có được áp dụng nghiêm ngặt? | Phù hợp |
| --- | --- | --- |
| Unit test mặc định, test source không có module descriptor | Thường không, theo classpath white-box | Kiểm tra logic đơn vị, kể cả internals |
| Named module integration test/consumer subproject | Có, khi compile/run thật trên module path | Kiểm tra exports, requires, service loading |
| Module patching tests | Có nhưng được mở/patch có chủ đích | Kiểm tra internals trong module mà vẫn dùng JPMS rules |

**Kết luận kiểm thử:** cần ít nhất một bài integration/consumer test thực sự chạy modular khi xuất bản một Java module API. Test suite green trên classpath không đủ chứng minh consumers named modules biên dịch được.

## 15. `application.mainModule` khác `application.mainClass`

Trong project Java application thông thường:

```kotlin
application {
    mainClass.set("demo.app.Main")
}
```

Gradle có thể chạy ứng dụng trên classpath. Khi main source set là named module, cần khai báo rõ **JPMS module name**:

```kotlin
application {
    mainModule.set("demo.app")
    mainClass.set("demo.app.Main")
}
```

- `mainModule` **không phải** Gradle project name hoặc Maven artifactId; phải khớp `module demo.app { ... }` trong descriptor.
- `mainClass` là **fully qualified Java class** với entry point.
- Gradle Application plugin sẽ dùng các thông tin này để cấu hình task `run` và application distributions cho modular app theo khả năng plugin.
- `java -jar app.jar` không mặc định giống `./gradlew :app:run`. Plain JAR có thể thiếu runtime dependencies, launcher có thể sử dụng classpath khác, và JPMS metadata cần được xử lý phù hợp.
- Gradle Application plugin có các tasks `installDist`, `distZip`, `distTar`; khi phát hành, **kiểm thử launcher trong distribution thật**, không chỉ `run` ở development environment.

Ví dụ build phân phối:

```bash
./gradlew :app:installDist
./gradlew :app:distZip
```

Output thường nằm trong `app/build/install` và `app/build/distributions`, nhưng tên distribution phụ thuộc cấu hình Application plugin/project archive names.

### Module version trong `module-info.class`

Gradle cho phép đặt version của module qua JavaCompile options, không phải viết version trong cú pháp `module-info.java`:

```kotlin
// Trong build.gradle.kts đã áp dụng Java plugin:
version = "1.2.0"

tasks.named<JavaCompile>("compileJava") {
    options.javaModuleVersion.set(provider { project.version.toString() })
}
```

Đây là snippet bổ sung; không dùng cùng với ví dụ chưa đặt version nếu không cần. `javaModuleVersion` ảnh hưởng metadata module được compiler tạo, **không phải** cơ chế dependency locking/version conflict của Gradle. Với project lớn, nên đảm bảo version provider ổn định và không vô tình phụ thuộc Project từ task execution; task configuration ở đây thiết lập provider theo build version.

## 16. `jlink` và `jpackage`: không phải tự có chỉ vì đã áp dụng Java plugin

JPMS mở ra khả năng tạo runtime image tùy biến:

- `jlink`: liên kết một tập named modules vào runtime image.
- `jpackage`: tạo native installer/app image tùy platform.
- `jdeps`: phân tích module/package dependencies.
- `jar --describe-module`: xem module descriptor hoặc automatic module metadata của JAR.

Tuy nhiên:

- Gradle Java/Java Library/Application plugins **không tự động biến mọi `build` thành bước `jlink` hoặc `jpackage`**.
- Bạn phải tự thiết kế task hoặc sử dụng plugin có hỗ trợ phù hợp, kiểm soát toolchain, module path và output.
- `jlink` có giới hạn nhất định với automatic modules; không nên khẳng định bất cứ legacy JAR nào cũng có thể dùng tạo runtime image chỉ vì nó chạy trên module path.
- Image được tạo có thể phụ thuộc OS/CPU/JDK vendor; không nên coi nó là artifact Java thuần chạy mọi nơi.
- Nếu plugin bên thứ ba thêm `jlink` task, vẫn phải xác minh compatibility và runtime behavior.

Nội dung này liên quan **đóng gói và deployment**; phần quan trọng trước tiên vẫn là compile/run modular đúng bằng Gradle.

## 17. Các lệnh chẩn đoán thường dùng

Từ project phần 7:

```bash
./gradlew --version
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :library:dependencies --configuration compileClasspath
./gradlew :app:compileJava --info
./gradlew :app:run --info
./gradlew :library:jar
```

Từ JDK:

```bash
java --list-modules
jar --describe-module --file library/build/libs/library.jar
```

Nếu JAR có version trong tên, thay bằng đúng file thực tế. `java --list-modules` liệt kê **module trong runtime image**, không tự liệt kê mọi module trong thư mục build. `jar --describe-module` đọc module metadata trong JAR, còn `dependencies` là báo cáo Gradle resolved dependency graph; **không công cụ nào tự thay thế hoàn toàn cái khác**.

### Phân loại lỗi theo tầng

| Lệnh/công cụ | Tầng nó giúp kiểm tra |
| --- | --- |
| `dependencies --configuration compileClasspath` | Có đúng project/external dependency được resolve để compile không? |
| `dependencies --configuration runtimeClasspath` | Có đúng runtime dependency/provider không? |
| `compileJava --info` | Java compiler invocation/Gradle inputs và tác vụ compile |
| `run --info` | JavaExec runtime, JVM options và task graph |
| `jar --describe-module` | Artifact JAR có tên JPMS và exports/requires gì? |
| `jdeps` với module path phù hợp | Những modules/packages mà artifact thực tế dùng |
| `java --show-module-resolution ...` | Runtime đang resolve modules nào, đọc từ đâu? |
| IDE delegate run/test to Gradle | Xác định lỗi nằm ở IDE model hay Gradle build |

### Dùng `jdeps`

Ví dụ khái niệm sau khi tạo các JAR:

```bash
jdeps --module-path contracts/build/libs:library/build/libs \
      --list-deps library/build/libs/library.jar
```

Đây là **ví dụ Unix** khi library JAR không có version suffix và đường dẫn modules tương ứng tồn tại. Trên Windows, module-path entries thường được phân cách bằng `;` thay vì `:`; bạn phải xác định đường dẫn thực và đối chiếu đầy đủ transitive modules. `jdeps` có thể báo lỗi nếu thiếu modules được yêu cầu, nên hãy cấp đủ module path khi phân tích.

### Dùng `java --show-module-resolution`

Nếu chạy một application modular qua lệnh Java trực tiếp, có thể thêm:

```bash
java --show-module-resolution --module-path modules \
     --module demo.app/demo.app.Main
```

Lệnh này **minh họa cấu trúc**: thư mục `modules` là placeholder cho các modules đã được đóng gói thực tế, không phải thư mục được ví dụ Gradle tự tạo. Với Gradle project phần 7, `./gradlew :app:run --info` là cách dễ tái hiện hơn mà không phải tự ghép module path.

## 18. Bảng chẩn đoán lỗi JPMS trong Gradle

| Triệu chứng | Nguyên nhân hay gặp | Cách sửa |
| --- | --- | --- |
| `module not found: demo.greeter` | Module name sai, JAR không có metadata, Gradle dependency không tới module path | Kiểm tra `module-info.java`, project dependency và `inferModulePath` |
| `package ... is not visible` | Module không đọc dependency hoặc package chưa `exports` | Kiểm tra `requires` và `exports` theo đúng hướng |
| `module demo.app does not read demo.contracts` | Thiếu `requires` hoặc `requires transitive` ở dependency API | Đồng bộ descriptor với Gradle `api` |
| Public API trả `Greeter` nhưng consumer thiếu module `demo.contracts` | Gradle dùng `implementation` thay vì `api` cho public dependency | Chuyển library dependency sang `api` và giữ JPMS transitivity |
| Import class `public` trong `internal` không compile | Package chưa `exports` | Truy cập qua public API; chỉ export nếu thật sự là contract |
| `InaccessibleObjectException` khi reflection | Package chưa `opens` cho module/caller phù hợp | Thêm `opens` hẹp hoặc cấu hình framework, tránh mở toàn bộ |
| `Cannot access ... from unnamed module` | Named module đang phụ thuộc legacy library ở classpath | Nâng thư viện modular, wrap/transform hoặc thay kiến trúc |
| `java.lang.module.FindException` | Thiếu module, descriptor lỗi hoặc duplicate names | Kiểm tra module path, tên module và JAR metadata |
| `java.lang.module.ResolutionException` | Module graph không hợp lệ, packages conflict/split | Rà dependencies/module graph, loại split packages |
| `java.lang.LayerInstantiationException` | Có thể do split packages hoặc module layer config | Xem package trùng và module path entries |
| Gradle `run` chạy classpath dù main có descriptor | Thiếu `application.mainModule` hoặc cấu hình run khác | Đặt `mainModule` đúng, kiểm tra JavaExec invocation |
| `jar --describe-module` không có descriptor như mong muốn | `module-info.java` sai path, Jar đóng gói khác hoặc đang xem artifact cũ | `clean jar`, kiểm tra source set, đúng JAR |
| `java.modularity.inferModulePath` bị tắt | Legacy config hoặc plugin override | Bật inference khi phù hợp; bỏ manual module path xung đột |
| Unit tests PASS nhưng modular app FAIL | Tests chạy classpath/white-box, không enforce JPMS | Thêm integration/consumer named module tests |
| JUnit không tìm tests trên module path | Test launcher/engine, `opens`, patching hoặc module readability sai | Xem Java testing docs, test runtime classpath/module flags |
| IDE báo khác Gradle CLI | IDE module model và task delegation khác | Dùng Wrapper và delegate build/test cho Gradle; cấu hình IDE phù hợp |
| Hai libraries chứa cùng package | **Split package** trong các named modules | Tách package, tránh tự đóng gói duplicate classes vào nhiều modules |
| Plugin tạo plain JAR nhưng Gradle vẫn không thấy nó là module | Thiếu `module-info.class` hoặc manifest `Automatic-Module-Name` | Xuất bản metadata đúng, không đoán module name theo tên JAR |

Những lỗi như `ClassNotFoundException`, `NoClassDefFoundError` hoặc reflection access failure **không luôn do JPMS**; cũng có thể là thiếu runtime dependencies, version conflict hoặc packaging. Phải phân biệt module path/classpath, resolved dependencies và runtime distribution trước khi sửa code.

## 19. Quy trình migrate từ classpath project sang modular build

Một kế hoạch thực tế có thể đi theo các bước:

1. **Chọn boundary dựa trên kiến trúc**, không chỉ dựa trên số lượng Gradle subprojects. Một subproject có thể tương ứng một named module; tránh ép nhiều modules vào cùng một source set nếu chưa có chiến lược cụ thể.
2. **Rà external dependencies**: có `module-info.class`, `Automatic-Module-Name`, hay chỉ legacy JAR? Kiểm tra đúng phiên bản đang dùng.
3. **Thiết kế module names ổn định** và public packages; xác định internal packages không export.
4. **Thêm `src/main/java/module-info.java`** cho từng named module; thêm `requires`, `exports` tối thiểu cần thiết.
5. **Đồng bộ Gradle scopes** với JPMS: `requires` ↔ `implementation`, `requires transitive` ↔ `api`, `requires static` ↔ `compileOnly`, `requires static transitive` ↔ `compileOnlyApi` khi hợp lý.
6. **Sử dụng Java toolchain** phù hợp (Java 17+ theo dự án) và giữ `inferModulePath` mặc định nếu không có lý do tắt.
7. **Chạy compile/consumer tests** theo thứ tự dependency: modules nền tảng trước, ứng dụng sau; kiểm tra compile graph chứ không tự tạo module path thủ công.
8. **Đặt `application.mainModule` và `mainClass`** cho modular application.
9. **Chạy black-box modular integration tests** để kiểm tra exports/readability, bên cạnh white-box unit tests.
10. **Xử lý reflection có chủ đích**, chỉ `opens` package cần thiết và đúng framework modules.
11. **Kiểm tra packaging/distribution thực tế** với `jar --describe-module`, launcher và runtime dependencies.
12. **Giữ khả năng rollback** nếu một thư viện legacy/annotation processor/test framework chưa hỗ trợ mô hình module phù hợp.

### Những điều nên tránh

- Không thêm `module-info.java` vào mọi project chỉ để đạt mục tiêu “đều có module”.
- Không `exports` tất cả packages, vì như vậy mất phần lớn lợi ích encapsulation.
- Không dùng `open module` hoặc hàng loạt `--add-opens` như phương án mặc định lâu dài.
- Không đoán JPMS module name từ Maven artifactId.
- Không dùng `api` cho mọi Gradle dependencies; chỉ public contracts cần được expose.
- Không kết luận modular runtime đúng chỉ vì unit tests chạy trên classpath đều PASS.
- Không trộn nhiều module descriptors trong một main source set theo cách Java plugin không được thiết kế để xử lý nếu thiếu cấu hình tùy chỉnh.
- Không viết lại đường dẫn các JAR bằng strings thủ công khi Gradle module inference và project dependencies đã đủ.

## 20. Bài tập tự kiểm tra

**Câu 1.** Có `src/main/java/module-info.java` trong Java Library project, Gradle hiện đại đã bật `inferModulePath`. Có cần tự khai báo `options.compilerArgs += "--module-path"` không?

**Đáp:** Thông thường không. Gradle suy luận modular source set và phân loại các dependency entries có `module-info.class`/`Automatic-Module-Name` theo cơ chế module inference. Chỉ cấu hình thủ công khi có trường hợp đặc biệt được kiểm chứng.

**Câu 2.** Java project không có `module-info.java` nhưng dùng JDK 17. Nó đã là explicit named module chưa?

**Đáp:** Chưa. Java 17 hỗ trợ JPMS nhưng không tự biến source set thành explicit named module. Project vẫn có thể chạy bằng classpath.

**Câu 3.** `:library` export `demo.greeter.api` nhưng không export `demo.greeter.internal`. Một class `public` trong internal package có được `:app` import trên module path không?

**Đáp:** Không. Public Java access modifier không vượt qua module-level export restrictions.

**Câu 4.** `:library` public method trả `demo.contracts.api.Greeter`. Vì sao cần cả `requires transitive demo.contracts` và `api(project(":contracts"))`?

**Đáp:** `requires transitive` cho **JPMS readability** của consumer; `api` cho **Gradle compile dependency exposure**. Cả hai phải phản ánh public contract chứa kiểu từ `contracts`.

**Câu 5.** Khi nào dùng `opens` thay vì `exports`?

**Đáp:** Khi một framework cần **deep reflection** vào package và không cần consumer compiler được phép import public classes từ đó. `opens` không thay `exports` cho các API trực tiếp.

**Câu 6.** Một third-party JAR không có `module-info.class` hoặc `Automatic-Module-Name`. Gradle inferModulePath thường đặt nó ở đâu?

**Đáp:** Trên classpath, thuộc unnamed module. Named module không thể viết `requires` đến unnamed module; cần upgrade/wrapper/transform/migration strategy.

**Câu 7.** `mainModule.set("demo.app")` có phải Gradle project path `:app` không?

**Đáp:** Không. `demo.app` là JPMS module name từ `module-info.java`. `:app` là Gradle subproject path.

**Câu 8.** Vì sao một JUnit unit test chạy qua Gradle có thể PASS dù `exports` trong production module sai?

**Đáp:** Nếu test source set không có module descriptor, Gradle thường chạy tests trên classpath white-box; module encapsulation không được kiểm thử. Cần integration test thực sự modular/consumer build.

**Câu 9.** Có `Automatic-Module-Name` trong JAR nhưng không có `module-info.class`. Nó là explicit module hay automatic module?

**Đáp:** Automatic module có tên ổn định từ manifest; nó chưa có `exports`/`requires` descriptor tường minh như explicit module.

**Câu 10.** Có thể dùng `jar --describe-module` để xem tên JPMS module không?

**Đáp:** Có. Dùng với JAR thực tế sau build. Nếu JAR không có descriptor nhưng có manifest automatic name, output sẽ phản ánh automatic module info theo JDK.

**Câu 11.** `java --list-modules` có tự liệt kê mọi dependency JAR trong `build/libs` không?

**Đáp:** Không. Nó liệt kê modules có trong runtime image đang dùng. Muốn kiểm tra artifacts của build, xem `jar --describe-module`, module path và Gradle dependency reports.

**Câu 12.** Một framework nạp class bằng reflection bị `InaccessibleObjectException`. Đâu là giải pháp đầu tiên?

**Đáp:** Xác định package/module/caller thực tế, xem framework có hỗ trợ JPMS không; thêm `opens pkg to framework.module` hẹp khi phù hợp. Chỉ dùng `--add-opens` như workaround được kiểm chứng.

## 21. Tài liệu chính thức

- [Gradle — Java Library Plugin: Building Modules for the Java Module System](https://docs.gradle.org/current/userguide/java_library_plugin.html#sec:java_library_modular): `module-info.java`, `requires`, module path inference, automatic/unnamed modules, JPMS/Gradle scope mapping.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): `java.modularity.inferModulePath` và các source sets/tasks chuẩn.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html#sec:application_modular): cấu hình `mainModule` và `mainClass`, `run`, distributions.
- [Gradle — Testing in Java & JVM projects](https://docs.gradle.org/current/userguide/java_testing.html#sec:java_testing_modules): test trên classpath/white-box, named module black-box tests và module patching.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): cách Gradle chọn compiler/JDK cho các Java tasks.
- [Oracle — Java SE 17: Modules and module declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7): ngữ nghĩa các module directives.
- [Oracle — The java Command (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `--module-path`, `--module`, `--show-module-resolution`, `--add-opens`.
- [Oracle — The javac Command (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): compilation modes, JPMS options và module readability.
- [Oracle — jar Tool (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): `--describe-module` để xem metadata của module JAR.
