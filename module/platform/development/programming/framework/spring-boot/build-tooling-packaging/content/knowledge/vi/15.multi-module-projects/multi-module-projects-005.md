# Áp dụng plugin Boot cho mô-đun ứng dụng và BOM cho mô-đun thư viện

## 1. Vấn đề cần giải quyết trong dự án đa mô-đun

Một dự án Spring Boot đủ lớn thường được chia thành nhiều mô-đun: `shared-lib`/`domain`/`common` chứa logic hoặc API dùng chung, còn `service-app` chứa entrypoint Spring Boot và tạo artifact chạy được. Nếu áp dụng **Spring Boot build plugin** lên **tất cả** mô-đun mà không phân biệt mục đích, module thư viện có thể bị ép tạo executable JAR dù **không có `main()`**. Ngược lại, nếu bỏ plugin Boot ở module thư viện nhưng không quản lý phiên bản dependency, việc khai báo thư viện Spring hoặc Apache Commons thiếu `version` lại có thể gây lỗi resolution.

Cách tách đúng:

> **Plugin Spring Boot để đóng gói và chạy ứng dụng; Spring Boot BOM để thống nhất phiên bản dependency.** Module thư viện có thể dùng BOM mà **không áp dụng plugin Boot**.

Bài này hướng dẫn hai build tool là **Gradle** và **Maven**, có ví dụ Java 17+, cách xem task/output, phân biệt JAR thường với executable JAR và những lỗi thường gặp.

### Mục tiêu sau bài

- Hiểu `org.springframework.boot` (Gradle plugin) hoặc `spring-boot-maven-plugin` (Maven plugin) phục vụ việc gì.
- Hiểu `spring-boot-dependencies` BOM **quản lý phiên bản**, không tự thêm dependency hay tạo task đóng gói.
- Chỉ áp dụng plugin Boot tại **module ứng dụng**; module thư viện giữ cấu trúc JAR Java thông thường.
- Dùng `project(':shared-lib')` (Gradle) hoặc reactor dependency (Maven) để ứng dụng sử dụng thư viện.
- Đọc `runtimeClasspath`, `dependencyInsight`, `dependency:tree` và kiểm tra `BOOT-INF/lib` để xác minh artifact cuối.
- Giữ cùng một bộ dependency version giữa app và library, không để BOM hoặc plugin version lệch nhau ngoài ý muốn.

## 2. Ba vai trò khác nhau: plugin, BOM và module dependency

| Thành phần | Vai trò chính | Không tự làm việc gì? |
|---|---|---|
| **Gradle `org.springframework.boot` plugin** | Khi có Java plugin, thêm `bootJar`, `bootRun`, `bootBuildImage` và các cấu hình Boot | Không tự thêm `spring-boot-starter`; không tự quản lý version nếu chưa dùng BOM hoặc dependency management |
| **Maven `spring-boot-maven-plugin`** | `repackage` JAR/WAR thành executable archive; hỗ trợ `spring-boot:run` và các goal khác | Không phải `dependencyManagement`; chỉ khai báo plugin mà không có execution phù hợp chưa chắc `package` đã repackage |
| **`spring-boot-dependencies` BOM** | Cung cấp phiên bản được quản lý cho Spring Boot, Spring Framework và nhiều thư viện tương thích | Không tạo executable JAR; không thêm các thư viện vào dependencies nếu chưa khai báo chúng |
| **Gradle `java-library`** | Tạo JAR thư viện và các `apiElements`/`runtimeElements`; hỗ trợ `api`/`implementation` | Không cần application main class |
| **Gradle `java`** | Compile/test/JAR Java chuẩn | Không tự tạo Boot executable archive nếu không có Boot plugin |
| **Maven `<packaging>jar</packaging>`** | Đóng gói JAR Java bình thường qua lifecycle | Không biến JAR thành Boot executable khi không chạy `repackage` |
| **Project/module dependency** | Nối app tới module library trong cùng build | Không tự điều khiển BOM, plugin hoặc main class |

Ví dụ:

```text
multi-boot/
├── shared-lib   (mô-đun thư viện, không có main())
│   ├── Java library plugin
│   ├── Spring Boot BOM quản lý dependency versions
│   └── build -> shared-lib-1.0.0.jar (JAR thường)
│
└── service-app  (mô-đun ứng dụng, có main())
    ├── Spring Boot plugin + Java plugin
    ├── Spring Boot BOM quản lý dependency versions
    ├── depends on shared-lib
    └── build -> service-app-1.0.0.jar (executable Boot JAR)
                         └── BOOT-INF/lib/shared-lib-1.0.0.jar
```

**BOM và Boot plugin là hai trục độc lập**. Có thể cần BOM trong cả library lẫn app; nhưng chỉ app cần khả năng `bootJar`/`repackage`.

### Lưu ý về thuật ngữ

- **Module/app project**: tập source code, dependency và build configuration riêng.
- **Root/aggregator**: điểm điều phối các module, không nhất thiết tạo artifact chạy được.
- **BOM** (*Bill of Materials*): bảng dependency versions đã được bộ framework kiểm tra tương thích.
- **JAR thường**: class ở root package của JAR; Java tooling có thể đặt lên classpath như thư viện.
- **Executable Boot JAR**: application classes ở `BOOT-INF/classes` và dependencies bên trong `BOOT-INF/lib`; chạy thông qua Spring Boot Loader bằng `java -jar`.
- **Task/goal**: Gradle chạy **task** (`bootJar`), Maven chạy **goal** (`spring-boot:repackage`); không dùng lẫn hai cú pháp.

## 3. Gradle: phân công plugin theo từng project

Dưới đây là mô hình **Groovy DSL** (`settings.gradle` và `build.gradle`). Ví dụ pin **Spring Boot 3.5.16**, **Java 17**. Đây là phiên bản dùng để minh họa một build tái lập; trong dự án thực, chọn phiên bản còn được hỗ trợ và đồng nhất với các module khác. Cần bản Gradle tương thích với Spring Boot 3.5 và Gradle Wrapper được tạo/duy trì đúng quy trình (ví dụ bản Gradle 8.14.x phù hợp nhánh này).

### 3.1. Cấu trúc dự án

```text
multi-boot-gradle/
├── settings.gradle
├── build.gradle
├── gradlew                  (nếu đã tạo Wrapper)
├── gradlew.bat              (nếu đã tạo Wrapper)
├── gradle/wrapper/...       (nếu đã tạo Wrapper)
│
├── shared-lib/
│   ├── build.gradle
│   ├── src/main/java/com/example/shared/GreetingService.java
│   └── src/test/java/com/example/shared/GreetingServiceTest.java
│
└── service-app/
    ├── build.gradle
    └── src/main/java/com/example/app/ServiceApplication.java
```

Có **một Gradle multi-project build** gồm hai subproject. Không thêm plugin Boot vào `shared-lib` chỉ vì nó dùng một thư viện trong Spring Boot BOM. `shared-lib` có thể là Java thuần không phụ thuộc Spring runtime.

### 3.2. settings.gradle: đăng ký các module

```groovy
rootProject.name = 'multi-boot-gradle'

include 'shared-lib', 'service-app'
```

Tên ở `include` phải đúng thư mục con thực tế. Dấu `:` trong task/dependency selector đại diện cho project path Gradle, ví dụ `:service-app:bootJar`.

### 3.3. build.gradle tại root: quản lý phiên bản plugin, chưa áp dụng

```groovy
plugins {
    id 'org.springframework.boot' version '3.5.16' apply false
}

allprojects {
    group = 'com.example'
    version = '1.0.0'

    repositories {
        mavenCentral()
    }
}
```

Ý nghĩa:

1. `id 'org.springframework.boot' version '3.5.16' apply false` khai báo phiên bản plugin có thể dùng trong **subproject**, nhưng **không áp dụng plugin vào root**; vì thế root không tự có `bootJar`.
2. `group` và `version` dùng nhất quán cho tất cả project để các artifact có tọa độ rõ ràng.
3. `mavenCentral()` cung cấp repository để resolve dependency; Gradle Plugin Portal được Gradle dùng theo cơ chế plugin resolution riêng.
4. Root **không** áp dụng `java` hay `org.springframework.boot` hàng loạt. Nếu thêm `subprojects { apply plugin: 'org.springframework.boot' }`, module thư viện cũng bị đưa vào luồng executable JAR — đó là điều ta muốn tránh.

**Phân biệt “đã có plugin trên classpath” và “đã áp dụng plugin”:** `apply false` không tạo task Boot. Chỉ `id 'org.springframework.boot'` trong `service-app/build.gradle` ở mục tiếp theo mới làm điều đó.

### 3.4. shared-lib/build.gradle: java-library + BOM, không có Boot plugin

```groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    // Import Spring Boot BOM dưới dạng Gradle platform cho thư viện.
    // api(platform(...)) cũng xuất các version constraints tới consumer
    // qua cơ chế metadata tương ứng của Gradle.
    api platform('org.springframework.boot:spring-boot-dependencies:3.5.16')

    // Không ghi phiên bản vì BOM đã quản lý.
    implementation 'org.apache.commons:commons-lang3'

    // Unit tests không cần Spring ApplicationContext.
    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.16'
    )
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Tại sao dùng `java-library`?**

- Nó áp dụng Java plugin và tạo task `compileJava`, `jar`, `test` cho thư viện.
- Nó có `api` và `implementation` để phân biệt dependency lộ ra trong public API với chi tiết nội bộ.
- Không có `bootJar`, không cần tìm `public static void main`.
- `jar` tạo JAR bình thường: class của `GreetingService` sẽ ở `com/example/shared/GreetingService.class` tại root của archive, phù hợp để module khác dùng như thư viện.

**Tại sao `api platform(...)`?** Trong Gradle `java-library`, việc khai báo BOM bằng `api platform(...)` cho phép constraints do BOM cung cấp tham gia cả API variant và được Gradle thể hiện cho consumer theo cơ chế publish metadata. Đây là **lựa chọn có chủ đích** trong ví dụ: thư viện được phát hành cho các consumer thuộc cùng hệ Spring Boot 3.5.x. Nếu thư viện hoàn toàn trung lập, không muốn đẩy các khuyến nghị phiên bản Spring Boot sang consumer, cân nhắc `implementation platform(...)` cho cấu hình nội bộ và để application quản lý BOM riêng.

**Không nhầm:**

- `api platform('...')` quản lý phiên bản dependency, **không thêm toàn bộ JAR trong BOM** vào thư viện.
- `implementation 'org.apache.commons:commons-lang3'` **mới khai báo dependency**; phiên bản được giải quyết theo BOM/constraints của graph.
- Không bắt buộc phải có `spring-boot-starter` trong shared library nếu nó chỉ dùng một tiện ích Java thuần.
- Nếu dùng kiểu từ thư viện ngoài trong **public method signature**, dependency đó có thể cần chuyển từ `implementation` sang `api` để consumer compile được.

### 3.5. service-app/build.gradle: chỉ app mới áp dụng Boot plugin

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    // Đây là dependency thật giữa hai project của build.
    implementation project(':shared-lib')

    // Ứng dụng cũng phải có version management rõ ràng.
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.16'
    )

    // BOM quản lý phiên bản; dependency này thêm Boot runtime thật.
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

`org.springframework.boot` được áp dụng vào `service-app`; vì project cũng có `java` nên Boot plugin tạo `bootJar` và `bootRun`, đồng thời `assemble` thường phụ thuộc `bootJar`. `jar` (JAR thường) vẫn tồn tại, với classifier `plain` theo quy ước.

`implementation project(':shared-lib')` khiến Gradle hiểu app phải dùng **đầu ra thích hợp của thư viện**; không cần tự chép `shared-lib.jar` sang thư mục `libs`. Khi `bootJar` đóng app, dependency thư viện được đưa vào runtime archive theo cơ chế của task, thường dưới `BOOT-INF/lib`.

**Lưu ý:** ví dụ **không áp dụng `io.spring.dependency-management`**. Đây là phương án **Gradle native BOM** (`platform`), không trộn hai cách quản lý version trong cùng ví dụ để tránh hiểu sai quy tắc ưu tiên.

### 3.6. Mã nguồn thư viện Java 17: không có main()

`shared-lib/src/main/java/com/example/shared/GreetingService.java`:

```java
package com.example.shared;

import org.apache.commons.lang3.StringUtils;

public final class GreetingService {
    private GreetingService() {
        // Utility class, không cần khởi tạo đối tượng.
    }

    public static String greet(String name) {
        return StringUtils.capitalize("hello, " + name) + "!";
    }
}
```

Class này dùng `commons-lang3` bên trong implementation. Chữ ký public chỉ nhận/trả `String` của JDK nên **không cần expose** Commons Lang3 như một `api` dependency. Không có `main()` và cũng không có `@SpringBootApplication` trong module thư viện.

### 3.7. Unit test thư viện, không khởi tạo Spring Boot

`shared-lib/src/test/java/com/example/shared/GreetingServiceTest.java`:

```java
package com.example.shared;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingServiceTest {

    @Test
    void greetsByCapitalizingFirstLetter() {
        assertEquals("Hello, Java!", GreetingService.greet("Java"));
    }
}
```

Bài test dùng JUnit 5/Jupiter đã được BOM quản lý. `:shared-lib:test` là task Java thường, không cần `bootTestRun` hay Spring context.

### 3.8. Mã nguồn ứng dụng Spring Boot

`service-app/src/main/java/com/example/app/ServiceApplication.java`:

```java
package com.example.app;

import com.example.shared.GreetingService;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ServiceApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServiceApplication.class, args);
    }

    @Bean
    CommandLineRunner greetingRunner() {
        return args -> System.out.println(GreetingService.greet("Java"));
    }
}
```

Ứng dụng chỉ dùng `spring-boot-starter`, không có web starter: nó chạy console, thực thi `CommandLineRunner` và kết thúc. Sau khởi động thành công, output **có chứa đúng dòng**:

```text
Hello, Java!
```

Spring Boot/Gradle còn có thể in banner, log hoặc thông báo khác; không khẳng định toàn bộ stdout chỉ có một dòng.

**Chú ý component scanning:** `GreetingService` ở `com.example.shared` là class Java thuần, app gọi trực tiếp, nên không cần Spring component scan tới package ấy. Nếu library cung cấp `@Service`, `@Configuration`, `@Entity` hoặc repository thực sự, phải quản lý package scan/import/auto-configuration tương ứng. Không nhầm “module nằm trên classpath” với “Spring tự đăng ký mọi bean trong module đó”.

## 4. Chạy và kiểm tra kết quả Gradle

Trên Linux/macOS, tại root có Gradle Wrapper:

```bash
# Xem các project trong build:
./gradlew projects

# Chạy unit tests của thư viện:
./gradlew :shared-lib:test

# Build JAR thư viện Java và executable JAR của ứng dụng:
./gradlew :shared-lib:jar :service-app:bootJar

# Chạy ứng dụng theo chế độ phát triển:
./gradlew :service-app:bootRun

# Chạy đúng executable JAR vừa build:
java -jar service-app/build/libs/service-app-1.0.0.jar
```

Windows PowerShell thay `./gradlew` bằng `.\gradlew.bat`. Nếu chưa có Wrapper, cần tạo bằng một bản Gradle đã cài tương thích (ví dụ chạy `gradle wrapper --gradle-version 8.14.3` từ build root phù hợp). Các file `gradlew`/`gradlew.bat` **không tự xuất hiện** chỉ vì viết `build.gradle`. Không cần chạy `bootRun` và `java -jar` đồng thời; đó là **hai cách chạy độc lập** để so sánh.

### Artifact dự kiến

| Module/task | File hoặc trạng thái | Mục đích |
|---|---|---|
| `:shared-lib:jar` | `shared-lib/build/libs/shared-lib-1.0.0.jar` | JAR thường, có `com/example/shared/GreetingService.class` |
| `:service-app:jar` | `service-app/build/libs/service-app-1.0.0-plain.jar` | JAR thường của app theo quy ước Boot/Gradle |
| `:service-app:bootJar` | `service-app/build/libs/service-app-1.0.0.jar` | Executable Boot JAR |
| `:service-app:bootRun` | Task chạy app từ runtime classpath | Chạy khi phát triển, không cần `java -jar` |
| `:shared-lib:bootJar` | **Không tồn tại** trong cấu hình này | Thư viện không áp dụng Boot plugin |

Tên file là **quy ước** với `group/version` và classifiers ở ví dụ. Nếu project sửa `archiveBaseName`, `archiveVersion` hoặc `archiveClassifier`, file thật có thể khác; xem output của task.

Liệt kê archive:

```bash
jar tf shared-lib/build/libs/shared-lib-1.0.0.jar
jar tf service-app/build/libs/service-app-1.0.0.jar
```

Trong thư viện, tìm `com/example/shared/GreetingService.class`. Trong executable app, tìm:

```text
BOOT-INF/classes/com/example/app/ServiceApplication.class
BOOT-INF/lib/shared-lib-1.0.0.jar
BOOT-INF/lib/commons-lang3-....jar
```

Dấu `....` chỉ **phiên bản thực do BOM/Gradle resolution chọn**, không phải tên file literal. Nếu executable JAR thiếu `shared-lib`, kiểm tra `implementation project(':shared-lib')` và `runtimeClasspath` thay vì tự copy JAR thủ công.

### Xem task và dependency graph

```bash
# Thư viện chỉ có nhiệm vụ Java thường, không có BootJar:
./gradlew :shared-lib:tasks --all

# App có các Boot tasks:
./gradlew :service-app:tasks --all

# Xem dependency trong từng module:
./gradlew :shared-lib:dependencies --configuration compileClasspath
./gradlew :shared-lib:dependencies --configuration runtimeClasspath
./gradlew :service-app:dependencies --configuration runtimeClasspath

# Vì sao phiên bản Commons Lang3 được chọn?
./gradlew :shared-lib:dependencyInsight --configuration runtimeClasspath --dependency commons-lang3

# Xem các variants để module khác tiêu thụ:
./gradlew :shared-lib:outgoingVariants
```

**Đọc đúng kết quả:**

- `runtimeClasspath` là cấu hình resolution, **không phải** danh sách file `BOOT-INF/lib` đã được xác nhận. Cần so với archive.
- `dependencyInsight` cho biết nguồn constraint/conflict resolution, giúp phát hiện BOM và override.
- `outgoingVariants` của `java-library` mô tả API/runtime variants; không có nghĩa một Boot fat JAR sẽ được dùng như Java library.
- `tasks --all` ở **đúng project** cho thấy `bootJar` có tồn tại không; task ở app không chứng tỏ library cũng có.
- Khi chạy `./gradlew build` ở root, Gradle có thể build/test cả hai project theo task graph. Chọn `:service-app:bootJar` khi chỉ muốn đóng app và các dependency cần thiết; chọn `build` cho kiểm thử tổng thể.

## 5. Vì sao plugin Boot không nên được áp dụng toàn bộ subprojects?

Một cấu hình **không nên dùng** khi root có các module Java thuần:

```groovy
subprojects {
    apply plugin: 'java'
    apply plugin: 'org.springframework.boot'
}
```

Nếu `org.springframework.boot` được áp dụng vào `shared-lib` và Java plugin đã có, Boot tạo `bootJar`, `bootRun`; `assemble` có thể phụ thuộc `bootJar`. Nhưng `GreetingService` không có `main()`, nên build executable archive có thể thất bại kiểu **không tìm thấy main class**. Ngay cả khi ép main hoặc vô hiệu hóa `bootJar`, module library còn phải bảo đảm các biến thể publication không bị nhầm sang executable layout.

### Cách đúng

Giữ phiên bản plugin tại root với `apply false`, sau đó áp dụng **chỉ trong `service-app/build.gradle`**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
}
```

Ở `shared-lib/build.gradle`:

```groovy
plugins {
    id 'java-library'
}
dependencies {
    api platform('org.springframework.boot:spring-boot-dependencies:3.5.16')
}
```

Các block trên **trích lại phần cốt lõi**, không phải cấu hình đầy đủ thay cho mục 3. Nếu thư viện cần thêm dependency thật, vẫn phải khai báo nó như trong ví dụ `commons-lang3`.

### Nếu phải tạm dùng Boot plugin trong một library?

Có thể vô hiệu hóa task `bootJar` trong một project theo thiết kế đặc biệt, nhưng điều đó dễ tạo cấu hình khó hiểu và không sửa nguyên nhân kiến trúc: **library thường không cần tính năng đóng gói ứng dụng**. Giải pháp ưu tiên vẫn là **không áp dụng plugin Boot** vào module này. Nếu dự án có custom shared build logic bắt buộc, kiểm tra cả task `jar`, outgoing variants, Maven/Gradle publication metadata và test tiêu thụ như một library.

## 6. Gradle BOM: api platform, implementation platform và enforcedPlatform

### 6.1. BOM là tập version constraints, không phải ứng dụng

Đặt:

```groovy
dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.16'
    )
    implementation 'org.apache.commons:commons-lang3'
}
```

`platform(...)` nhập các version constraints từ Maven BOM vào **cấu hình Gradle**. `implementation 'org.apache.commons:commons-lang3'` là dependency thực. Nếu **không có dòng implementation**, BOM không tự thêm Apache Commons Lang3 vào runtime JAR.

Trong module Java library:

- `implementation platform(...)` áp dụng constraints cho dependency cần trong nội bộ module. Đó thường là lựa chọn an toàn nếu thư viện không muốn ảnh hưởng version policy của consumer.
- `api platform(...)` cũng có thể đưa constraints ra API variant, nên consumer Gradle có thể nhận các ràng buộc version khi sử dụng project/library. Hữu ích nếu thư viện **chủ động cam kết** cùng hệ sinh thái phiên bản, nhưng cần thận trọng với thư viện công cộng đa hệ sinh thái.
- `enforcedPlatform(...)` dùng constraints mạnh hơn, có thể ép version trong graph và lan đến consumer qua các variant. Không chọn mặc định chỉ vì muốn “khóa thật chặt”; dễ tạo xung đột khi consumer có BOM khác.

**BOM không phải “một JAR chứa các thư viện”.** File `spring-boot-dependencies` chủ yếu là POM metadata với `dependencyManagement`. Nó điều hướng version selection, không tự chứa bytecode của Commons Lang3 hay các Spring starter.

### 6.2. Platform recommendations không phải khóa tuyệt đối

Gradle native `platform(...)` thường sử dụng **version recommendations**. Nếu dependency graph chứa ràng buộc/phiên bản khác, Gradle có thể chọn phiên bản không trùng bản trong BOM theo cơ chế conflict resolution. Vì vậy không nên nói “BOM luôn buộc mọi dependency đúng 100% phiên bản đó”.

Lệnh điều tra:

```bash
./gradlew :service-app:dependencyInsight --configuration runtimeClasspath --dependency commons-lang3
```

Khi thấy phiên bản ngoài dự kiến, tìm:

- Direct dependency khai báo phiên bản khác.
- Transitive dependency yêu cầu phiên bản cao hơn.
- Constraints/platform khác trên cùng classpath.
- Force, resolution strategy, dependency substitution hoặc version catalog.
- Gradle Module Metadata của dependency được publish.

**Tránh ghi override tùy tiện**: mỗi Spring Boot release được kiểm thử với một tổ hợp dependency nhất định. Chỉ override khi có lý do (security, bug fix, compatibility) và có test xác nhận.

### 6.3. Version plugin Boot và BOM cần được đồng bộ

Trong ví dụ:

```text
org.springframework.boot Gradle plugin: 3.5.16
spring-boot-dependencies BOM:        3.5.16
spring-boot-starter runtime:         được BOM 3.5.16 quản lý
```

Không nên vô tình dùng plugin `3.5.16` nhưng library BOM `3.4.x` và app BOM `3.5.x`; các ràng buộc có thể conflict và tạo ra version không đúng giả định. Với build lớn, quản lý version bằng một property/version catalog/convention plugin chung thay vì copy số phiên bản độc lập.

Ví dụ **đoạn thiết kế biến chung** cho Groovy DSL, khi tự kiểm soát cấu hình:

```groovy
// gradle.properties của build root:
springBootVersion=3.5.16

// Trong các build.gradle dùng dependency coordinates:
dependencies {
    implementation platform(
        "org.springframework.boot:spring-boot-dependencies:${springBootVersion}"
    )
}
```

Đây là **hai đoạn từ hai file khác nhau** để minh họa quản lý phiên bản, không đặt nguyên dòng `springBootVersion=...` vào `build.gradle`. Với `plugins {}`, việc đưa plugin version vào `settings.gradle` `pluginManagement`/version catalog có quy tắc riêng; không tự giả định có thể đặt Groovy property interpolation trong mọi `plugins` block.

## 7. Thay thế: io.spring.dependency-management plugin, không nhầm với Boot plugin

Spring Boot Gradle Plugin hỗ trợ hai đường quản lý dependency chính:

1. **Gradle native BOM** qua `platform(...)` — dùng ở toàn bộ ví dụ chính.
2. **Plugin `io.spring.dependency-management`** — cung cấp DSL `dependencyManagement`, import Maven BOM, hỗ trợ tùy chỉnh managed versions dựa trên properties.

Khi **Boot plugin và `io.spring.dependency-management` cùng được áp dụng trong một project**, Spring Boot plugin tự động import `spring-boot-dependencies` BOM tương ứng version Boot plugin. Nhưng **nếu chỉ áp dụng `io.spring.dependency-management` trong thư viện**, bạn phải **chủ động import BOM** — không có Boot plugin ở library để thực hiện tích hợp tự động ấy.

Một **phương án thay thế**, không trộn vào build native BOM ở mục 3, là khai báo tại root:

```groovy
plugins {
    id 'org.springframework.boot' version '3.5.16' apply false
    id 'io.spring.dependency-management' version '1.1.7' apply false
}
```

Ở `shared-lib/build.gradle`:

```groovy
plugins {
    id 'java-library'
    id 'io.spring.dependency-management'
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.boot:spring-boot-dependencies:3.5.16'
    }
}

dependencies {
    implementation 'org.apache.commons:commons-lang3'
}
```

Ở `service-app/build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
}

dependencies {
    implementation project(':shared-lib')
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Ở app, Boot plugin kết hợp dependency-management plugin để import BOM; ở library, import tường minh vì không áp dụng Boot plugin. Các block này **thay thế** những block plugin/dependency management tương ứng của cấu hình chính, không phải yêu cầu tạo hai hệ version-management chồng lên nhau.

### Ghi chú cho module thư viện được publish

`io.spring.dependency-management` và Gradle native `platform` không hoàn toàn giống nhau về cách triển khai version constraints, thuộc tính override và metadata khi publish. Khi export library ra Maven repository:

- Dùng `maven-publish` và `from components.java` nếu muốn publish Java component.
- Xem `gradle.module`, generated `pom.xml` và test với một **consumer project riêng**.
- Không suy rằng mọi version constraint trong Gradle Module Metadata sẽ được Maven consumer diễn đạt y hệt.
- Kiểm tra dependency transitive và compatibility ở consumer cuối, không chỉ build của module library.

## 8. Maven multi-module: BOM ở parent, Boot repackage chỉ ở app

Cùng ý tưởng được hiện thực khác trong Maven. Maven không có `apply false` như Gradle; ta đặt **BOM ở aggregator/parent** để các module kế thừa `dependencyManagement`, nhưng **chỉ module app** khai báo `spring-boot-maven-plugin` cùng goal `repackage`.

Ví dụ cấu trúc:

```text
multi-boot-maven/
├── pom.xml                        (aggregator/parent)
├── shared-lib/
│   ├── pom.xml
│   ├── src/main/java/com/example/shared/GreetingService.java
│   └── src/test/java/com/example/shared/GreetingServiceTest.java
└── service-app/
    ├── pom.xml
    └── src/main/java/com/example/app/ServiceApplication.java
```

Có thể **dùng lại nguyên các file Java 17** ở mục 3.6, 3.7, 3.8. Chúng không phụ thuộc trực tiếp vào build tool, chỉ phụ thuộc Java libraries được Maven quản lý chính xác.

### 8.1. Root pom.xml: aggregator + BOM + plugin management

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>multi-boot-maven</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>shared-lib</module>
        <module>service-app</module>
    </modules>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-boot.version>3.5.16</spring-boot.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>${spring-boot.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.13.0</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.2</version>
                </plugin>
                <plugin>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-maven-plugin</artifactId>
                    <version>${spring-boot.version}</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
```

**Điểm cốt lõi:**

- `<packaging>pom</packaging>` là aggregator/parent, không có Java app được chạy ở root.
- `<modules>` cho Maven Reactor biết có hai module.
- `<dependencyManagement>` import BOM giúp **module con kế thừa phiên bản phụ thuộc**, nhưng chưa thêm dependency cụ thể.
- `<pluginManagement>` quản lý phiên bản compiler, Surefire và Spring Boot Maven Plugin; **không tự kích hoạt repackage ở mọi module**.
- Root ví dụ **không dùng `spring-boot-starter-parent`**. Vì vậy repackage **không tự được bind** như trong setup dùng Starter Parent; phải khai báo execution tại app (mục 8.3).
- Compiler plugin version và `maven.compiler.release=17` giúp build Java 17 ổn định, thay vì lệ thuộc vào default của Maven quá cũ.
- Surefire 3.5.2 hỗ trợ chạy các JUnit Jupiter tests theo cấu hình của ví dụ.

### 8.2. shared-lib/pom.xml: JAR bình thường, không có Boot plugin

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>multi-boot-maven</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>shared-lib</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Cả `commons-lang3` lẫn `junit-jupiter` đều bỏ `<version>` vì root đã import Spring Boot BOM. JUnit nằm ở `test` scope, không đi vào JAR runtime của library. `<packaging>jar</packaging>` dùng lifecycle Maven JAR thông thường. **Không khai báo `spring-boot-maven-plugin` trong `shared-lib`**, vì thư viện không có entrypoint chạy ứng dụng.

### 8.3. service-app/pom.xml: chỉ app mới có repackage

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>multi-boot-maven</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>service-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>shared-lib</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <executions>
                    <execution>
                        <goals>
                            <goal>repackage</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-maven-plugin` nhận version từ `pluginManagement` ở root. Execution `repackage` **chỉ được khai báo trong app**, nên khi build reactor, app đóng executable JAR còn shared-lib vẫn là plain library JAR. Việc plugin version xuất hiện ở `pluginManagement` của root **không** có nghĩa thư viện cũng chạy goal `repackage`.

**Lưu ý cú pháp phiên bản:** `${project.version}` trong app trỏ đến project version của app (cùng `1.0.0` với library ở ví dụ). Nếu library có phiên bản độc lập, nên dùng property/coordinates tương ứng chứ không tự giả định đồng phiên bản.

### 8.4. Build và chạy Maven reactor

Từ root có `pom.xml`, dùng Maven đã cài:

```bash
mvn clean verify

# Chỉ build phần app và các project bắt buộc theo dependency:
mvn -pl :service-app -am clean package

# Chạy executable JAR:
java -jar service-app/target/service-app-1.0.0.jar
```

Nếu dự án đã có Maven Wrapper, thay `mvn` bằng `./mvnw` (Windows PowerShell: `.\mvnw.cmd`). Hai lệnh build ở trên là **các lựa chọn** cho hai nhu cầu; không cần chạy cả hai để một JAR mới tồn tại. `-pl :service-app` chọn module theo artifactId; `-am` thêm các project mà module đó phụ thuộc trong reactor, ví dụ `shared-lib`.

Khi ứng dụng chạy thành công, log sẽ chứa dòng `Hello, Java!` từ `CommandLineRunner`; các log Spring Boot khác vẫn có thể xuất hiện.

Kết quả dự kiến:

```text
shared-lib/target/shared-lib-1.0.0.jar        (JAR thư viện)
service-app/target/service-app-1.0.0.jar     (Boot executable JAR)
```

Kiểm tra:

```bash
jar tf shared-lib/target/shared-lib-1.0.0.jar
jar tf service-app/target/service-app-1.0.0.jar

mvn -pl :shared-lib dependency:tree
mvn -pl :service-app dependency:tree
mvn -pl :service-app help:effective-pom
```

JAR thư viện có `com/example/shared/GreetingService.class` ở root. Executable JAR app có `BOOT-INF/classes/com/example/app/ServiceApplication.class` và nested JAR `BOOT-INF/lib/shared-lib-1.0.0.jar`. Tên file phụ thuộc cấu hình `finalName`/classifiers nếu project thay đổi quy ước.

### 8.5. Vì sao Maven BOM không thay thế Starter Parent?

Nếu dự án dùng `spring-boot-starter-parent` làm Maven parent, ngoài dependency management nó còn có plugin management, compiler defaults và execution `repackage` thích hợp khi app khai báo plugin. Nhưng khi chỉ **import BOM** vào POM parent riêng như ví dụ:

- Có **dependency version management**.
- **Không** được tự thừa hưởng toàn bộ plugin management/executions từ Starter Parent.
- **Không** có bảo đảm Boot repackage được bind vào app nếu không khai báo plugin/execution.
- Phải cấu hình compiler/testing/encoding/plugin versions độc lập phù hợp với dự án.

Đây là lý do root POM ở mục 8.1 quản lý Maven Compiler/Surefire/Boot Plugin và app POM ở mục 8.3 **tường minh khai báo `repackage`**.

## 9. Scope, dependency exposure và publication: không chỉ build xanh

### 9.1. Thư viện nên khai báo ít dependency nhất cần thiết

Nếu `shared-lib` chỉ chứa utility như `GreetingService`, không cần thêm `spring-boot-starter` để “đồng bộ với Spring Boot”. Thêm starter trong library có thể kéo logging/autoconfiguration và các dependency không thiết yếu vào ứng dụng consumer.

Nếu library cần tính năng Spring như `@ConfigurationProperties`, Spring Core, validation hoặc một Spring Data API, khai báo **dependency hẹp nhất** đúng tính năng. BOM vẫn quản lý phiên bản mà không buộc bạn dùng starter hoặc Boot packaging plugin.

### 9.2. Gradle api vs implementation

`java-library` phân biệt:

- `api 'group:artifact'`: khi loại từ dependency xuất hiện trong **chữ ký public**, consumer cần thấy thư viện ở compile classpath.
- `implementation 'group:artifact'`: dependency là chi tiết bên trong. Consumer thường không cần thấy ở compile classpath nhưng vẫn cần lúc runtime.
- `compileOnly`: chỉ compile, không tự xuất hiện lúc runtime; dùng sai có thể gây `NoClassDefFoundError`.
- `runtimeOnly`: chỉ có khi chạy, thường thích hợp cho driver/provider không cần compile trực tiếp.
- `api platform(...)` và `implementation platform(...)`: đưa version constraints theo phạm vi; không phải loại dependency class binary giống `api '...'`.

Với Maven, `compile` là default scope, `provided`/`test` có quy tắc khác. Maven không có cặp `api`/`implementation` hoàn toàn tương đương Gradle, vì vậy nếu xuất bản library hỗ trợ cả hai build tool, phải kiểm tra các dependency trong POM và Gradle Module Metadata, không suy rằng metadata hai bên giống hệt nhau.

### 9.3. Publish library khác publish application

Nếu module `shared-lib` cần được nhiều dự án sử dụng qua Maven repository, trong Gradle có thể áp dụng `maven-publish` rồi publication:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

publishing {
    publications {
        library(MavenPublication) {
            from components.java
        }
    }
}
```

Đây là **đoạn thay thế/mở rộng cấu hình plugin của library**, không dán thêm một `plugins {}` block thứ hai vào giữa file mà không tổ chức lại. `from components.java` chọn Java component, không chọn Boot executable JAR. Nó là cách phù hợp để đưa public API, JAR thường và dependency metadata cho consumer.

Trong app, nếu muốn phát hành executable JAR, hãy publish artifact của `bootJar` riêng và định nghĩa publication thích hợp. **Không** coi `BOOT-INF/classes` là cấu trúc JAR library chuẩn cho ứng dụng khác compile. Nếu một module cần vừa là thư viện vừa là app, hãy thiết kế module/artifact/classifier rõ ràng, hoặc tốt hơn là tách hai module như bài này.

### 9.4. BOM của thư viện có thể ảnh hưởng consumer

Nếu shared-lib được publish cho nhiều hệ sinh thái hoặc nhiều major Spring Boot versions, cân nhắc:

- Không export BOM quá đặc thù qua API nếu library muốn trung lập framework.
- Không dùng `enforcedPlatform` mặc định, vì có thể ép phiên bản của consumer.
- Test bằng một consumer dự án độc lập, không chỉ project dependency trong reactor.
- Xác nhận POM/module metadata tạo ra khi publish có đúng dependency và constraints.
- Công bố ma trận tương thích Spring Framework/Boot, Java và Jakarta API nếu thư viện có public signatures gắn với framework.

## 10. Lỗi thường gặp khi áp dụng plugin sai module

| Hiện tượng | Nguyên nhân thường gặp | Kiểm tra/cách xử lý |
|---|---|---|
| `:shared-lib:bootJar` đòi main class | Áp dụng Boot plugin cho library có Java plugin | Bỏ Boot plugin khỏi library; chỉ dùng `java-library` + BOM |
| Root `build` cố tạo executable JAR cho mọi module | `subprojects { apply plugin: 'org.springframework.boot' }` | Tách plugin application theo project; root dùng `apply false` |
| Gradle `implementation '...:commons-lang3'` thiếu version và fail resolution | Có dependency thật nhưng chưa import BOM vào cấu hình phù hợp | Thêm `platform('...spring-boot-dependencies:...')` hoặc dependency-management plugin đúng project |
| Library có BOM nhưng app `bootJar` thiếu Spring runtime | BOM không tự thêm starter | App phải khai báo `implementation 'org.springframework.boot:spring-boot-starter'` hoặc starter phù hợp |
| `bootJar` chỉ có class app mà không có library | App chưa `implementation project(':shared-lib')` hoặc runtime variant bị đổi | Kiểm tra `runtimeClasspath` và `jar tf` của executable archive |
| App báo `NoClassDefFoundError` khi java -jar | Library JAR/dependency runtime thiếu hoặc bị exclude sai | So `BOOT-INF/lib`, Gradle runtimeClasspath, Maven dependency tree |
| Maven lib trở thành executable JAR, consumer không tìm được class | Boot `repackage` đang bị gắn lên module library | Giữ goal repackage **chỉ app**, library là plain JAR |
| Maven import BOM mà `spring-boot:repackage` không chạy | BOM không tự cấu hình plugin execution | Khai báo Boot plugin và execution `repackage` tại app |
| Maven `The requested profile ...` hoặc module không tìm được | Nhầm `-pl`/module path hay build từ sai root | Xem `<modules>` và reactor summary; dùng `-pl :service-app -am` |
| Java compiler level sai hoặc `UnsupportedClassVersionError` | Maven/Gradle/JDK/toolchain lệch giữa module | Pin Java 17 toolchain/release, kiểm tra `java -version` và build logs |
| `@Service` ở library không được Spring tìm | App component scan không bao phủ package library | `@Import`, `scanBasePackageClasses` hoặc auto-configuration thích hợp |
| Dependencies khác phiên bản giữa module | BOM lệch version/override trực tiếp | Dùng dependencyInsight/dependency:tree, thống nhất BOM policy |
| Gradle `No matching variant` | Consumer yêu cầu variant/Java version không tương thích | Xem `outgoingVariants`, Gradle metadata, toolchain |
| `-plain.jar` bị đưa lên repository làm app executable | Nhầm `components.java` với `bootJar` | Xác định rõ artifact loại nào được publish |
| Maven build app riêng nhưng chưa resolve được shared-lib | Shared-lib chưa có trong local repository và chưa dùng reactor | Build từ root với `-am` hoặc `mvn install` phù hợp |
| Library dùng starter không cần thiết | Copy cấu hình app sang library | Giảm về dependency hẹp nhất mà library thật sự dùng |

### Kịch bản kiểm thử kiến trúc

1. Từ root Gradle, chạy `:shared-lib:tasks --all`: **không** có `bootJar` trong library.
2. Chạy `:service-app:tasks --all`: có `bootJar`/`bootRun` ở app.
3. Chạy `:shared-lib:jar` và xem JAR: class ở root package.
4. Chạy `:service-app:bootJar` và xem app JAR: library ở `BOOT-INF/lib`.
5. Chạy `:service-app:bootRun` rồi `java -jar service-app/build/libs/...`: cùng một dòng `Hello, Java!` từ app.
6. Chạy `:shared-lib:dependencyInsight` để xem Commons Lang3 được chọn do constraints của BOM hay do override.
7. Với Maven, xem effective POM library/app: BOM được kế thừa, `repackage` chỉ được khai báo/chạy ở app.
8. Chạy reactor `mvn clean verify`, xem report tests; chỉ sau đó đánh giá build toàn dự án.

## 11. Trường hợp nhiều module ứng dụng, nhiều thư viện

Mô hình trên mở rộng theo vai trò, không theo một quy tắc “mọi subproject giống nhau”:

```text
root
├── domain-core          -> java-library + BOM
├── shared-integration   -> java-library + BOM + dependency thật cần dùng
├── account-service      -> Boot plugin + Java + BOM
├── billing-service      -> Boot plugin + Java + BOM
└── build-conventions    -> quản lý version/toolchain/quality rules
```

Mỗi **application** có main class riêng, executable JAR riêng. Các **library** giữ JAR thường và có thể được nhiều app dùng chung. Đối với thư viện đa framework, chỉ dùng một BOM trung lập hoặc phụ thuộc phiên bản rõ ràng khi cần, tránh tự ép mọi consumer dùng cùng bộ Spring Boot.

Nếu có nhiều project cùng import BOM, nên quản lý **một nơi duy nhất**:

- Gradle: `gradle.properties`, version catalog `libs.versions.toml` hoặc convention plugins để pin Boot/BOM version.
- Maven: root parent properties + `dependencyManagement` + `pluginManagement`.
- CI: một wrapper/toolchain và lệnh reactor/multi-project nhất quán; kiểm tra dependency graph của **artifact release**.
- Khi upgrade Spring Boot: nâng plugin/BOM cùng chính sách, chạy lại unit/integration tests và smoke test executable archives.

### Không nhầm BOM với version catalog

Gradle **version catalog** tập trung tọa độ/phiên bản do dự án khai báo, trong khi `platform(BOM)` nhập **dependency constraints được phát hành dưới dạng Maven BOM**. Có thể dùng cả hai (catalog cho tọa độ của BOM và plugins; platform để resolution), nhưng catalog không tự hoạt động như BOM trừ khi project thật sự khai báo platform dependency.

## 12. Checklist áp dụng trong dự án thật

- [ ] Liệt kê module nào là **library** và module nào là **application** trước khi viết plugin declarations.
- [ ] Root Gradle khai báo version Boot plugin bằng `apply false`, không áp dụng Boot hàng loạt.
- [ ] Library dùng `java-library`, **không áp dụng `org.springframework.boot`** nếu không cần executable archive.
- [ ] Library vẫn có version management từ Spring Boot BOM hoặc chính sách riêng; không áp dụng Boot plugin chỉ để lấy BOM.
- [ ] App dùng Boot plugin + Java plugin, có main class và dependency `project(':shared-lib')` thực.
- [ ] App nhập BOM phù hợp hoặc dùng `io.spring.dependency-management` có cấu hình đúng; không tự coi Boot plugin đơn độc là BOM.
- [ ] Không nhầm `platform(...)` với dependency thực; BOM không tự thêm starter/commons JAR.
- [ ] Dùng `api`/`implementation` đúng mức public API, tránh transitive dependency thừa.
- [ ] Maven root quản lý BOM ở `dependencyManagement`, không khai báo `repackage` trên thư viện.
- [ ] Với Maven không dùng Starter Parent, app khai báo plugin/execution `repackage` tường minh.
- [ ] Kiểm tra JAR library có class ở root package, Boot app có `BOOT-INF/classes` và `BOOT-INF/lib`.
- [ ] Dùng `dependencyInsight`/`dependency:tree` để kiểm tra nguồn phiên bản, đặc biệt sau upgrade.
- [ ] Chạy unit tests thư viện, app tests, và chạy **đúng executable artifact** sau khi build.
- [ ] Nếu publish library, kiểm tra Java component/Maven POM/Gradle Module Metadata với consumer độc lập.
- [ ] Đồng bộ plugin/BOM/Java toolchain ở nhiều module và trong CI; không ép version ngoài BOM nếu chưa kiểm thử.

**Kết luận:** Trong build đa mô-đun, Spring Boot **build plugin là công cụ tạo/chạy ứng dụng** còn Spring Boot **BOM là nguồn thống nhất dependency versions**. Vì vậy **library có thể cần BOM nhưng không cần Boot plugin**; **application cần plugin Boot và các dependency cụ thể**. Tách vai trò này giúp thư viện dễ tái sử dụng, app đóng gói chuẩn, giảm lỗi tìm `main()`, tránh xung đột version và làm cho task graph lẫn artifact release dễ kiểm soát.

### Tài liệu chính thức

- [Spring — Creating a Multi Module Project](https://spring.io/guides/gs/multi-module/)
- [Spring Boot 3.5 — Gradle Getting Started](https://docs.spring.io/spring-boot/3.5/gradle-plugin/getting-started.html)
- [Spring Boot 3.5 — Gradle Managing Dependencies](https://docs.spring.io/spring-boot/3.5/gradle-plugin/managing-dependencies.html)
- [Spring Boot 3.5 — Reacting to Other Gradle Plugins](https://docs.spring.io/spring-boot/3.5/gradle-plugin/reacting.html)
- [Spring Boot 3.5 — Maven Using the Plugin](https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html)
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle — Platforms and BOMs](https://docs.gradle.org/current/userguide/platforms.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
