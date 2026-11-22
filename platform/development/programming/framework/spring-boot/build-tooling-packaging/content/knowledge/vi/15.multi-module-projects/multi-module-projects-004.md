# Tổ chức Gradle multi-project qua `settings` và `project dependency`

Khi hệ thống Spring Boot phát triển lớn, một project Gradle duy nhất dễ trở nên khó quản lý: mọi class ở chung một source set, không rõ ranh giới giữa thư viện nghiệp vụ và ứng dụng có thể chạy, test lâu và dependency bị kéo vào những nơi không cần. **Gradle multi-project build** giải quyết bằng cách đặt nhiều **subproject** trong **một build**, được khai báo tập trung trong `settings.gradle` hoặc `settings.gradle.kts`, mỗi subproject có build script và dependency riêng.

Có hai thao tác khác nhau cần phân biệt:

- **`include('core', 'app')` trong settings:** nói với Gradle **những project nào thuộc build** và tên/path của chúng.
- **`implementation project(':core')` trong build script của `app`:** nói rằng **app dùng output/thư viện của core**. Chính project dependency giúp Gradle chọn artifact/variant, tạo classpath phù hợp và sắp xếp các task producer trước consumer.

**Chỉ include chưa tạo dependency.** Và **chỉ viết project dependency đến một path chưa include** không khiến Gradle tự tạo project đó. Phải thiết lập cả cấu trúc lẫn quan hệ sử dụng.

Trong Spring Boot, một thiết kế phổ biến là thư viện `:core` dùng `java-library` và ứng dụng `:app` dùng `org.springframework.boot` + `java`. Thông thường chỉ các module thực sự tạo executable archive mới cần `bootJar` hoặc `bootWar`; module thư viện nên tạo JAR thường.

Ví dụ xuyên suốt dùng **Java 17**, **Spring Boot 3.3.5**, **Gradle 8.7** và **Groovy DSL** để trình bày một build xác định, không khẳng định đó là các phiên bản mới nhất. Các nguyên tắc multi-project cũng áp dụng với các phiên bản khác, nhưng cần kiểm tra tương thích plugin/JDK.

## 1. Hiểu build, project, subproject và task

Một **Gradle build** có thể gồm:

~~~text
multi-demo/                    <- build root
├── settings.gradle            <- danh sách project và cấu hình cấp build
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...         <- Gradle Wrapper (nếu đã tạo)
├── core/                      <- project path :core
│   ├── build.gradle
│   └── src/main/java/...
└── app/                       <- project path :app
    ├── build.gradle
    └── src/main/java/...
~~~

Build trên có **root project** và hai **subproject**. Root project có thể có `build.gradle` riêng để định nghĩa build logic cấp root, nhưng **không bắt buộc** đối với ví dụ này. `settings.gradle` xác định build hierarchy; các build script con xác định plugins, dependencies và tasks cho từng project.

Trong Gradle, tên **project path** dùng dấu hai chấm:

| Project | Đường dẫn project | Một task ví dụ |
| --- | --- | --- |
| Root | `:` | `:help` |
| Thư viện core | `:core` | `:core:jar` |
| Ứng dụng app | `:app` | `:app:bootJar` |
| Module lồng (nếu include) | `:services:billing` | `:services:billing:test` |

**Project path không phải package Java.** `:core` có thể chứa package `com.example.core`; cấu trúc thư mục source Java phải tuân theo package, còn project path do Gradle settings quản lý.

**Project khác task:** `:app` là một project; `:app:bootJar` là task trong project đó. Dấu `:` ở đầu biểu thị path tuyệt đối tính từ build root, giúp không nhầm với project cùng tên ở vị trí khác.

### Lợi ích có thể đo được

- **Ranh giới dependency rõ:** app phụ thuộc core, core không cần biết về app.
- **Build order theo graph:** Gradle tự xây những output của core mà app cần trước khi app compile/package.
- **Plugin phù hợp từng module:** `java-library` ở core, Spring Boot plugin ở app.
- **Variant-aware resolution:** consumer nhận compile/runtime variant phù hợp từ library project.
- **Test và build có mục tiêu:** có thể chạy `:core:test` hoặc `:app:bootJar` thay vì thao tác mọi thứ.
- **Đóng gói đúng:** Boot archive của app có thể chứa JAR của core như dependency runtime; core không bị ép thành một executable Boot application.

Multi-project không tự đảm bảo build luôn nhanh hoặc kiến trúc luôn tốt. Nếu các module phụ thuộc vòng tròn, dùng quá nhiều cross-project configuration eager hoặc không có ranh giới API, build vẫn có thể phức tạp. Cần thiết kế cả project graph và dependency graph.

## 2. Vai trò của `settings.gradle`: khai báo các project tồn tại

File **`settings.gradle`** (Groovy DSL) ở build root:

~~~groovy
rootProject.name = 'multi-demo'
include 'core', 'app'
~~~

Tương đương cú pháp gọi method:

~~~groovy
rootProject.name = 'multi-demo'
include('core', 'app')
~~~

Hai đoạn trên là **hai cách viết cùng một cấu hình**, không cần copy cả hai. Gradle đọc settings ở giai đoạn initialization để xác định build root và các project tham gia. Với đường dẫn mặc định, `include 'core'` ánh xạ project `:core` đến thư mục `./core`, và `include 'app'` ánh xạ `:app` đến `./app`.

**Điều cần nhớ:**

1. `rootProject.name` đặt tên root project, không phải tên Java package.
2. `include` thêm **project descriptor** vào build; không đồng nghĩa module đó là dependency của module khác.
3. Mỗi subproject nên có build script phù hợp, chẳng hạn `core/build.gradle` và `app/build.gradle`.
4. Có thể include project nằm sâu bằng path dấu hai chấm.
5. Thư mục project phải tồn tại và có thể truy cập. Các phiên bản Gradle mới kiểm tra chặt hơn các directory được include bị thiếu hoặc không thể ghi.
6. Một settings file ở root là điểm xác định hierarchy; không cần tạo settings riêng cho mỗi child trong một multi-project build thông thường.

### `include` khác `includeBuild`

- **`include('core')`:** thêm `:core` thành **subproject cùng build**. Có thể dùng `implementation project(':core')`.
- **`includeBuild('build-logic')`:** đưa **một build khác** vào dạng **composite build/included build**, thường để chia sẻ build logic hoặc substitution giữa builds. Nó không tạo `:build-logic` thành subproject theo nghĩa của `include`.

Một cấu hình có `includeBuild` thuộc kiến trúc khác, không nên đổi `include 'core'` thành `includeBuild 'core'` chỉ vì muốn tách thư viện. Bài này tập trung vào **một settings hierarchy duy nhất** với `project(...)` dependencies.

## 3. Project dependency: tạo quan hệ tiêu thụ output của project khác

Trong `app/build.gradle`, lệnh:

~~~groovy
dependencies {
    implementation project(':core')
}
~~~

tạo dependency của **app** tới **core**. Dấu `:core` chỉ đúng project Gradle đã được include trong settings, không phải tên Maven artifact, không phải đường dẫn file và không phải tên package.

Gradle dùng **variant-aware dependency management**: tùy consumer cần compile classpath hay runtime classpath, nó chọn outgoing variant phù hợp mà project `:core` công bố (thường qua Java/Java Library plugin). Bởi vậy một project dependency không chỉ là “nối một file JAR bất kỳ”.

Đồ thị:

~~~text
settings.gradle
    rootProject = multi-demo
    include :core
    include :app
          |
          v
:app build.gradle
    implementation project(':core')
          |
          v
  Dependency graph: :app ----> :core
          |
          v
  Gradle nối compile/runtime classpath và task producer tương ứng
          |
          v
  :app:bootJar dùng output ứng dụng + runtime dependencies
~~~

**Hệ quả thực tế:**

- Khi compile source ở `:app` dùng một class public từ `:core`, Gradle cung cấp API artifact/variant của core cho compile classpath.
- Khi app chạy/đóng gói, Gradle cung cấp runtime variant của core với các runtime dependencies thích hợp.
- Gradle tạo quan hệ task cần thiết với output producer của core. Không cần chạy `./gradlew :core:jar` thủ công trước mỗi lần `:app:bootJar`.
- Khi core thay đổi, Gradle xác định task nào thực sự cần chạy lại dựa trên inputs/outputs/variant; không có quy tắc “luôn rebuild mọi module”.
- Những dependencies nội bộ của core không được tùy tiện đưa vào compile classpath của app; quy tắc `api`/`implementation` của Java Library plugin rất quan trọng.

### Không nhầm project dependency với external module dependency

~~~groovy
dependencies {
    implementation project(':core') // Project cùng Gradle build
    implementation 'org.springframework.boot:spring-boot-starter' // Module bên ngoài
}
~~~

Dòng đầu **không đòi publish core lên Maven Central** rồi mới dùng; Gradle biết project và output của nó trong cùng build. Dòng thứ hai resolve external artifact qua repository/dependency management. Nếu project `:core` không được include, Gradle không biết cách resolve `project(':core')`.

Viết `implementation files('../core/build/libs/core.jar')` thay cho project dependency là một kiểu phụ thuộc path/file dễ sai: nó làm mất phần thông tin variant/dependency transitively và có thể phải tự xử lý build order. Khi nguồn là một subproject Gradle, dùng `project(...)` đúng ngữ nghĩa.

## 4. Bài thực hành hoàn chỉnh: `:core` là thư viện, `:app` là ứng dụng Spring Boot

Mục tiêu:

1. Tạo multi-project build có hai module với một settings file.
2. Module `:core` cung cấp `GreetingService` bằng Java 17.
3. Module `:app` phụ thuộc `:core`, đăng ký bean và gọi thư viện trong một `CommandLineRunner`.
4. Chạy ứng dụng từ `bootRun` rồi tạo executable `bootJar`.
5. Chứng minh class của core được tìm thấy trong runtime của app, không cần publish core hoặc copy JAR thủ công.

Cấu trúc thư mục:

~~~text
multi-demo/
├── settings.gradle
├── core/
│   ├── build.gradle
│   └── src/
│       └── main/
│           └── java/
│               └── com/example/core/GreetingService.java
└── app/
    ├── build.gradle
    └── src/
        └── main/
            └── java/
                └── com/example/app/MultiDemoApplication.java
~~~

Nếu dùng Gradle Wrapper, root còn có `gradlew`, `gradlew.bat` và `gradle/wrapper/`. Đó là các file điều khiển Gradle version, không phải subprojects.

### 4.1. Root `settings.gradle`

~~~groovy
rootProject.name = 'multi-demo'
include 'core', 'app'
~~~

**Chưa** có dependency giữa app và core ở đây: settings chỉ làm hai project có mặt.

### 4.2. `core/build.gradle` — library project

~~~groovy
plugins {
    id 'java-library'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Vì `:core` không dùng thư viện bên ngoài ở bài này, nó không cần `repositories`. Nếu thêm external dependency sau này, phải cấu hình repositories ở core hoặc thống nhất repositories ở settings.

Tại sao `java-library` thay vì Spring Boot plugin?

- Đây là thư viện Java thuần, không có `@SpringBootApplication` hay điểm khởi động.
- `java-library` cung cấp `api`/`implementation` separation cùng các Java tasks.
- `:core:jar` tạo **plain library JAR**; core không cần Boot launcher/nested dependencies.
- Nếu sau này core thực sự muốn xuất bản artifact cho một ứng dụng khác, Java Library plugin là nền tảng tự nhiên hơn.

Không áp `id 'org.springframework.boot'` vào mọi module chỉ vì ứng dụng cuối cùng dùng Spring Boot. Làm vậy có thể tạo task `bootJar` không phù hợp với các module thư viện và gây nhầm sản phẩm phân phối.

### 4.3. `core/src/main/java/com/example/core/GreetingService.java`

~~~java
package com.example.core;

public final class GreetingService {

    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Code Java 17 hợp lệ. Method public `greet` là API mà app tiêu thụ; class không có annotation Spring. Việc quản lý bean được thực hiện ở module app để minh họa ranh giới: **một thư viện Java thông thường vẫn có thể được Spring Boot application dùng qua project dependency**.

### 4.4. `app/build.gradle` — executable Spring Boot application

~~~groovy
import org.springframework.boot.gradle.tasks.bundling.BootJar

plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation project(':core')
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.app.MultiDemoApplication'
}

tasks.named('bootJar', BootJar) {
    archiveFileName.set('multi-demo-app.jar')
}
~~~

**Phân tích cấu hình:**

- `java` tạo Java source sets và tasks như `compileJava`, `test`, `jar`.
- Spring Boot plugin tạo `bootJar` và `bootRun` khi kết hợp Java plugin phù hợp.
- `io.spring.dependency-management` hỗ trợ phiên bản thư viện theo Spring Boot BOM trong bài mẫu. Một project khác có thể dùng Gradle native BOM qua `platform(...)` thay thế.
- `implementation project(':core')` là **dòng quyết định** giúp `app` tiêu thụ API và runtime artifact của `core`.
- `spring-boot-starter` cung cấp Spring Boot runtime cơ bản mà **không khởi động web server**. Ví dụ này là ứng dụng command-line.
- `springBoot.mainClass` cấu hình điểm vào của ứng dụng để build plugin không cần phỏng đoán khi project có nhiều main classes.
- `bootJar.archiveFileName` cố định tên executable JAR để dễ kiểm tra, tránh lẫn với plain JAR và classifier mặc định.
- `repositories { mavenCentral() }` giải quyết external dependencies của app; project dependency `:core` không lấy thư viện core từ Maven Central.

Một lưu ý: version `3.3.5` và `1.1.6` được cố định cho ví dụ. Hãy kiểm tra compatibility và chính sách hỗ trợ trước khi áp dụng cho dự án mới.

### 4.5. `app/src/main/java/com/example/app/MultiDemoApplication.java`

~~~java
package com.example.app;

import com.example.core.GreetingService;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class MultiDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MultiDemoApplication.class, args);
    }

    @Bean
    GreetingService greetingService() {
        return new GreetingService();
    }

    @Bean
    CommandLineRunner showMessage(GreetingService greetingService) {
        return args -> System.out.println(
                "GREETING=" + greetingService.greet("Gradle")
        );
    }
}
~~~

**Chú ý ranh giới module:**

- `GreetingService` ở package `com.example.core`, module `:core`. Java compiler của `:app` biết class nhờ `implementation project(':core')`.
- `@SpringBootApplication` ở `com.example.app` thường scan package đó và các package con; nó **không tự scan sibling package `com.example.core`**. Vì vậy ví dụ tạo bean `GreetingService` bằng method `@Bean` ở app thay vì trông chờ component scan tìm class ngoài package gốc.
- `CommandLineRunner` nhận bean bằng dependency injection và gọi method public của core.
- `spring-boot-starter` không có server web; sau khi runner hoàn thành và context không có tiến trình lâu dài khác, ứng dụng kết thúc.
- Tên file public class khớp `MultiDemoApplication.java`, và package khớp cấu trúc thư mục.

### 4.6. Kiểm tra project hierarchy

Từ root `multi-demo/` có Gradle Wrapper:

~~~bash
./gradlew projects
~~~

Lệnh cho thấy root project và các subprojects `:core`, `:app`. Nội dung log, cách vẽ tree và version trong output phụ thuộc Gradle, không nên ghi một mẫu stdout cố định. Một hierarchy hợp lệ thường hiển thị các project tương ứng với settings.

Nếu chưa có Gradle Wrapper nhưng máy có Gradle tương thích, tại root có thể chạy một lần:

~~~bash
gradle wrapper --gradle-version 8.7
~~~

Lệnh tạo wrapper files; từ đó dùng `./gradlew` trên Linux/macOS và `.\gradlew.bat` trên Windows PowerShell. Việc tải distribution/dependencies lần đầu cần repository network phù hợp.

### 4.7. Chạy ứng dụng bằng `bootRun`

~~~bash
./gradlew :app:bootRun --args='--spring.main.banner-mode=off --logging.level.root=OFF'
~~~

Dòng **do chính chương trình** in khi khởi động thành công:

~~~text
GREETING=Hello, Gradle!
~~~

Đây không phải cam kết toàn bộ terminal chỉ có một dòng: Gradle/Spring Boot có thể in thêm startup/task log. Điều cần xác nhận là class `GreetingService` của core được chạy từ app.

Gradle xử lý compile/output của `:core` theo task dependency tương ứng rồi cung cấp cho `:app`. Không cần chạy `:core:jar` thủ công trước `:app:bootRun`.

### 4.8. Tạo executable JAR cho app

~~~bash
./gradlew :app:bootJar
~~~

Với `archiveFileName` tường minh, output:

~~~text
app/build/libs/multi-demo-app.jar
~~~

Chạy đúng artifact:

~~~bash
java -jar app/build/libs/multi-demo-app.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Dòng ứng dụng in:

~~~text
GREETING=Hello, Gradle!
~~~

`bootJar` đóng gói các runtime dependencies vào Spring Boot executable archive, bao gồm artifact thư viện `:core` được cung cấp qua project dependency. Với layout executable JAR thông dụng, class của app ở `BOOT-INF/classes` và JAR core có thể hiện dưới `BOOT-INF/lib`.

Kiểm tra bằng JDK:

~~~bash
jar tf app/build/libs/multi-demo-app.jar
~~~

Trong output dài, tìm:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/com/example/app/MultiDemoApplication.class
BOOT-INF/lib/core-1.0.0.jar
~~~

Đây là những **entry dự kiến** từ cấu hình version `:core` ở trên; archive còn có nhiều Spring Boot libraries. Nếu tên core JAR khác do thay `archiveBaseName`, `archiveVersion` hoặc plugin configuration, hãy xem tên thật trong `BOOT-INF/lib` thay vì áp cứng mẫu.

Lệnh `jar tf` chỉ liệt kê **outer archive entries**; không tự duyệt mọi class bên trong nested `core-1.0.0.jar`. Muốn xác nhận Java class thực sự có ở đó, có thể build `:core:jar` riêng rồi liệt kê file trong `core/build/libs/` hoặc dùng công cụ unpack nested JAR phù hợp.

### 4.9. Test và build từng phần

~~~bash
./gradlew :core:jar
./gradlew :core:test
./gradlew :app:test
./gradlew :app:build
~~~

Bài mẫu chưa có test source, vì thế `test` có thể báo `NO-SOURCE` hoặc tương đương. `:app:build` sẽ thực hiện lifecycle task của app và các dependencies cần thiết; không có nghĩa mọi task trong mọi subproject đều chạy. Khi muốn build toàn bộ multi-project theo convention, gọi task từ root có semantics phù hợp như `./gradlew build` và xem task graph thực tế.

## 5. Vì sao project dependency không cần viết task dependency thủ công?

Sai lầm thường gặp là cố dùng:

~~~groovy
// Không cần cho quan hệ Java library thông thường:
tasks.named('compileJava') {
    dependsOn(':core:jar')
}
~~~

Đoạn này là **phản ví dụ**, không phải phần của bài thực hành. Nó ghép cứng consumer task với một task cụ thể của module khác. Trong khi đó:

~~~groovy
dependencies {
    implementation project(':core')
}
~~~

đã diễn tả **mối quan hệ dữ liệu**: app cần thư viện của core. Gradle có thể tự chọn compile artifact hoặc runtime artifact, cùng những producer tasks đúng với variant. Task graph được suy ra từ dependency metadata chứ không yêu cầu viết thủ công từng quan hệ `dependsOn`.

Cơ chế này hữu ích khi sau này bạn thay phương pháp build core, thêm classes/resources hoặc đổi cách đóng gói. Project dependency vẫn nêu đúng ý nghĩa business/build: **app tiêu thụ core**.

### Variant-aware dependency management

Với Java Library plugin, project `:core` thường công bố các variants như:

- **`apiElements`:** phục vụ consumer ở compile classpath, ưu tiên API và những dependency cần cho public API.
- **`runtimeElements`:** phục vụ consumer ở runtime classpath, gồm runtime artifact và các dependency runtime thích hợp.

Gradle dựa trên attributes/capabilities/variant selection để ghép nhu cầu consumer với dữ liệu mà producer công bố. Không nên tự lấy file từ `core/build/libs` trong build script chỉ vì bạn biết artifact sẽ được tạo ở đó; cách đó làm bypass mô hình dependency giàu ngữ nghĩa.

**Không cần chạy core trước bằng tay.** Khi app cần output core, Gradle tự tạo task edges cần thiết. Thứ tự cụ thể của những task trung gian có thể khác theo Gradle version/caching/variants, nên hãy xem `--dry-run` hoặc `--info` thay vì khẳng định một chuỗi log cố định.

## 6. `api` và `implementation` trong một `java-library` module

`java-library` bổ sung phân tách API và implementation:

| Cấu hình trong core | Có thể xuất hiện ở compile classpath của app? | Có thể xuất hiện ở runtime của app? | Khi dùng |
| --- | --- | --- | --- |
| `api` | Có (được expose cho consumer) | Có theo runtime dependencies | Kiểu của thư viện khác xuất hiện trong public API/ABI |
| `implementation` | Không tự lộ ra consumer compile classpath | Có khi là runtime dependency | Logic nội bộ không lộ trong public API |
| `compileOnly` | Chỉ core compile, không tự xuất sang app | Không tự thành runtime dependency | Annotation hoặc API chỉ cần compile |
| `runtimeOnly` | Không phải compile API | Có khi runtime variant được tiêu thụ | JDBC driver, runtime integration |
| `testImplementation` | Không | Không trong app runtime | Testing của chính core |

Đây là semantics **mặc định của Java Library plugin**; một build tùy chỉnh variants/attributes có thể khác. Với bài thực hành đơn giản, core không có external dependencies nên `api` chưa được dùng.

### Ví dụ phân loại

Giả sử public method của core trả về một interface thuộc SLF4J:

~~~java
// Đoạn minh họa Java API; không phải file hoàn chỉnh.
public org.slf4j.Logger logger() {
    // Implementation có thể trả về Logger của thư viện logging.
    return org.slf4j.LoggerFactory.getLogger(getClass());
}
~~~

Vì `org.slf4j.Logger` xuất hiện trong public signature, library có thể cần đưa `slf4j-api` vào `api` để consumer compile được public API:

~~~groovy
// Đoạn minh họa thêm vào core/build.gradle, không dùng trong
// build.gradle của bài thực hành trước đó.
repositories {
    mavenCentral()
}

dependencies {
    api 'org.slf4j:slf4j-api:2.0.16'
}
~~~

Ngược lại, nếu một thư viện như `commons-lang3` chỉ được dùng trong private method body của core, nó thường thuộc `implementation`:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
~~~

Các version này chỉ làm ví dụ rõ tọa độ artifact; không khẳng định là latest. Không cần thêm chúng vào bài thực hành có `GreetingService` vì mã đó không sử dụng những thư viện này.

**Quy tắc:** ưu tiên `implementation` và chỉ dùng `api` khi public ABI cần type của dependency được xuất ra consumer. Nếu để mọi dependency ở `api`, consumer compile classpath phình to, tăng coupling và giảm lợi ích incremental compilation.

### API của core và component scan của Spring là hai điều khác nhau

Một class public được app compile/instantiate không nhất thiết trở thành Spring bean. Trong ví dụ, core dùng Java class thường, app dùng `@Bean` để đưa nó vào Spring container. Nếu core có `@Component` ở package ngoài vùng scan của app, phải cấu hình scan/import thích hợp hoặc dùng auto-configuration theo module; **project dependency chỉ đưa bytecode vào classpath, không tự đăng ký bean**.

## 7. `settings.gradle` với thư mục lồng và project path

Khi thư mục mặc định khớp project path:

~~~text
multi-demo/
├── settings.gradle
├── services/
│   └── billing/
│       └── build.gradle
└── libraries/
    └── pricing/
        └── build.gradle
~~~

Settings có thể dùng:

~~~groovy
rootProject.name = 'multi-demo'
include 'services:billing'
include 'libraries:pricing'
~~~

Các project path tương ứng là `:services:billing` và `:libraries:pricing`. Một build script của billing có thể khai báo:

~~~groovy
dependencies {
    implementation project(':libraries:pricing')
}
~~~

Đây là **cấu hình riêng để minh họa nested project paths**, không phải sửa tiếp bài thực hành `:core`/`:app`. Project `:libraries:pricing` phải thực sự tồn tại và công bố artifact/variant phù hợp nếu billing cần Java library. Gradle có thể tạo intermediate project descriptors cho các path chứa nhiều mức; bạn nên bảo đảm thư mục và project structure nhất quán.

### Khi project path khác physical directory

Không phải lúc nào project `:core` cũng ở `./core`. Ví dụ layout:

~~~text
multi-demo/
├── settings.gradle
└── modules/
    └── shared-core/
        └── build.gradle
~~~

Có thể ánh xạ bằng project descriptor trong settings:

~~~groovy
rootProject.name = 'multi-demo'
include 'core'

project(':core').projectDir = file('modules/shared-core')
~~~

Sau đó dependency vẫn là:

~~~groovy
dependencies {
    implementation project(':core')
}
~~~

Gradle dùng **logical project path** `:core` đã include, còn directory thực lấy từ `projectDir`. Không chuyển thành `project('modules/shared-core')` theo ý nghĩ “path là file path”, vì `project(...)` tìm **Gradle project path**, không phải đường dẫn filesystem tùy ý.

**Đừng tự tạo directory rỗng để che lỗi settings.** Nếu project path sai directory, build có thể không thấy build script và sources cần thiết; sửa mapping đúng. Ở Gradle 9+, việc include project có directory thiếu hoặc read-only được kiểm tra nghiêm ngặt hơn.

## 8. Root build script, versions và repositories: đặt cấu hình ở đâu?

Một multi-project build có thể có root `build.gradle` để cấu hình chung. Tuy nhiên ví dụ hai module chạy được ở mục 4 **không cần root build script**, vì:

- `settings.gradle` quản lý project hierarchy.
- `core/build.gradle` quản lý thư viện.
- `app/build.gradle` quản lý ứng dụng.
- Chỉ app cần Maven Central và Spring Boot plugin.

Khi nhiều module cùng dùng external dependencies, có thể tập trung repositories trong `settings.gradle` bằng Gradle `dependencyResolutionManagement`. Đây là **lựa chọn thay thế cấu hình repositories từng module**, không trộn với phần có `repositories { ... }` trong app khi bật chế độ cấm project repos.

### Ví dụ quản lý repositories ở settings (phương án riêng)

~~~groovy
import org.gradle.api.initialization.resolve.RepositoriesMode

rootProject.name = 'multi-demo'
include 'core', 'app'

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}
~~~

**Để sử dụng phương án này**, bỏ `repositories { mavenCentral() }` khỏi `app/build.gradle` và khỏi mọi project build script khác. Nếu không bỏ, `FAIL_ON_PROJECT_REPOS` sẽ báo lỗi khi một project/plugin thêm project-level repository. Code trên là một **biến thể settings hoàn chỉnh thay thế** file ở mục 4, không phải đoạn bổ sung không điều kiện.

`dependencyResolutionManagement.repositories` điều khiển **repositories dùng cho project dependencies/artifacts**; nó **khác** repositories dùng để resolve Gradle plugins. Muốn cấu hình plugin sources, xem `pluginManagement.repositories`.

### `pluginManagement` và cách quản lý version plugins

Trong multi-project, nhiều module Java/Boot có thể cần plugin versions nhất quán. Settings hỗ trợ:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
    plugins {
        id 'org.springframework.boot' version '3.3.5'
        id 'io.spring.dependency-management' version '1.1.6'
    }
}

rootProject.name = 'multi-demo'
include 'core', 'app'
~~~

Đây là **một lựa chọn settings khác** (không phải yêu cầu bắt buộc). Khi version được quản lý bằng `pluginManagement.plugins`, module có thể khai báo plugin IDs trong `plugins` mà không lặp version:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
}
~~~

`pluginManagement` quản lý **plugin resolution/default versions**; nó không tự áp dụng Spring Boot plugin cho mọi subproject. Phải có `plugins { id '...' }` ở module cần dùng. Đừng nhầm `pluginManagement` của Gradle với `dependencyResolutionManagement`; chúng giải quyết hai loại artifact khác nhau.

### Có nên viết `subprojects { apply plugin: ... }`?

Có thể cấu hình mọi subproject từ root, nhưng cách này dễ làm:

- module library bị apply Boot plugin không cần thiết;
- cấu hình project bị phụ thuộc thứ tự và khó tách biệt;
- build logic không rõ nơi sở hữu;
- gây khó với các hướng tối ưu configuration cache/isolated projects.

Trong dự án lớn, nên cân nhắc **convention plugins** hoặc build logic riêng để chia sẻ quy tắc về Java toolchain, tests, repositories và publishing; mỗi module chỉ áp dụng convention phù hợp. Không lặp cấu hình tùy tiện, nhưng cũng **không ép tất cả subprojects vào một root closure** nếu semantics khác nhau.

## 9. Kotlin DSL: cùng cấu trúc nhưng cú pháp khác

Nếu project dùng `settings.gradle.kts` và `build.gradle.kts` thì ý tưởng không đổi. Chọn **một DSL thống nhất** cho ví dụ; đừng chép Groovy syntax vào Kotlin script.

### Root `settings.gradle.kts`

~~~kotlin
rootProject.name = "multi-demo"
include("core", "app")
~~~

### `core/build.gradle.kts`

~~~kotlin
plugins {
    `java-library`
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Trong ví dụ Kotlin code block, cách viết ``java-library`` đang dùng dấu bao ngoài cho **Kotlin backtick identifier**; dòng cần gõ vào file thật là:

~~~kotlin
plugins {
    `java-library`
}
~~~

Khi sử dụng Kotlin DSL, `java-library` là Kotlin DSL plugin accessor được đặt trong dấu backtick, không phải chuỗi trần. Nó khác Groovy DSL `id 'java-library'`. Dấu backtick ở đây là cú pháp **thật** của Kotlin; tất cả dấu backtick khác trong văn xuôi chỉ để định dạng Markdown.

### `app/build.gradle.kts`

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

plugins {
    java
    id("org.springframework.boot") version "3.3.5"
    id("io.spring.dependency-management") version "1.1.6"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(project(":core"))
    implementation("org.springframework.boot:spring-boot-starter")
}

springBoot {
    mainClass.set("com.example.app.MultiDemoApplication")
}

tasks.named<BootJar>("bootJar") {
    archiveFileName.set("multi-demo-app.jar")
}
~~~

Các file Java trong `src/main/java` không phải đổi khi đổi Gradle DSL. Chú ý:

- Groovy: `implementation project(':core')`.
- Kotlin: `implementation(project(":core"))`.
- Groovy: `archiveFileName.set('...')`.
- Kotlin: `archiveFileName.set("...")`.
- Kotlin dùng generic `tasks.named<BootJar>(...)`; Groovy dùng `tasks.named('bootJar', BootJar)`.
- Không để hai file `build.gradle` và `build.gradle.kts` cùng giải thích mâu thuẫn cho một project; chọn cấu hình rõ ràng.

## 10. Task paths và build order trong multi-project

Các lệnh thường dùng từ root:

| Lệnh | Mục đích |
| --- | --- |
| `./gradlew projects` | Xem hierarchy của các project được settings include |
| `./gradlew tasks --all` | Liệt kê tasks mà Gradle nhận diện, gồm tasks theo project |
| `./gradlew :core:jar` | Tạo JAR library của core |
| `./gradlew :app:compileJava` | Compile app cùng các producer tasks mà dependency graph đòi hỏi |
| `./gradlew :app:bootRun` | Chạy ứng dụng Spring Boot ở app |
| `./gradlew :app:bootJar` | Đóng gói executable archive của app |
| `./gradlew :app:build` | Chạy lifecycle build app với các dependencies liên quan |
| `./gradlew build` | Yêu cầu build task theo task-selection semantics của Gradle trên hierarchy |
| `./gradlew :app:dependencies --configuration runtimeClasspath` | Xem resolved runtime dependency graph của app |

Một lệnh có path tuyệt đối `:app:bootJar` chỉ rõ task trong app. Điều đó giúp tránh gọi nhầm task cùng tên ở nhiều modules. Khi chạy từ subproject directory, Gradle cũng có quy tắc relative task path và build discovery; dùng full project task path từ root thường dễ đọc và dễ tái lập trong CI.

### `build` không giống `bootJar`

- `:core:build` của Java Library project thường bao gồm compile, test, jar/assemble theo lifecycle phù hợp.
- `:app:build` của Spring Boot project thường bao gồm kiểm thử và archive tasks được tích hợp, nhưng cấu hình cụ thể có thể được project tùy chỉnh.
- `:app:bootJar` chỉ yêu cầu executable archive và các task phụ thuộc; nó không mặc nhiên có cùng nghĩa với chạy toàn bộ bộ test/quality checks.
- `:app:bootRun` chạy application từ development runtime classpath, không phải kiểm chứng artifact đã được đóng gói.

Trong pipeline sản xuất, lựa chọn các task theo nhu cầu QA và output: ví dụ chạy test trước, sau đó package executable archive, rồi thực thi integration smoke test trên artifact thật.

### Xem task graph mà không thực thi actions

~~~bash
./gradlew :app:bootJar --dry-run
~~~

`--dry-run` hiển thị kế hoạch chạy tasks trong nhiều trường hợp nhưng **không tạo JAR mới**. Đừng nhầm việc thấy `:core:jar` trong dry-run với bảo đảm artifact hiện tại chứa đúng version của core. Để kiểm chứng thực tế phải chạy build và mở archive.

### Có cần gọi `dependsOn(':core:jar')` không?

Không, nếu app dùng dependency chuẩn `implementation project(':core')`. Gradle có metadata project dependency để tự xây task graph cần thiết. Chỉ cấu hình task dependency cross-project thủ công khi có một công việc riêng không thể biểu diễn bằng dependency artifact/variant thông thường, và cần cân nhắc coupling/maintenance.

## 11. Build graph khác dependency graph và package graph

Ba khái niệm thường bị gộp:

1. **Project hierarchy:** settings khai báo root và subprojects, ví dụ `:core`, `:app`.
2. **Dependency graph:** app dùng core; core có thể dùng external libraries; Gradle chọn variants và transitive dependencies.
3. **Task graph:** khi chạy `:app:bootJar`, Gradle chọn các tasks cần để tạo output của app và những producer outputs phụ thuộc.
4. **Artifact composition:** `bootJar` thu thập application classes và runtime dependencies để đóng gói executable archive.

Chỉ nhờ `include('core')`, Gradle biết core thuộc hierarchy nhưng **chưa biết app dùng core**. Chỉ nhờ `implementation project(':core')`, Gradle biết app dùng core nhưng phải có **project descriptor** của `:core` trong settings mới giải quyết được.

### Ranh giới giữa app và core ảnh hưởng packaging

Với ví dụ:

~~~groovy
// app/build.gradle
dependencies {
    implementation project(':core')
}
~~~

Gradle đưa project dependency vào runtime của app. Khi `bootJar` tạo executable Boot JAR, thư viện core là một dependency runtime điển hình và thường được đưa vào dưới `BOOT-INF/lib`. Core không cần tạo một executable Boot JAR riêng. Điều này khác việc copy source `core/src/main/java` vào `app/src/main/java`, vốn phá ranh giới module.

Nếu core có resources `src/main/resources`, Java Library JAR chứa những resources đó theo quy tắc build; classloader của Boot application có thể đọc qua nested library JAR. Không dựa vào đường dẫn `new File("../core/src/main/resources/...")` khi deploy, vì source tree không có trong artifact production.

## 12. Unit test, integration test và đóng gói theo module

Một lợi ích của multi-project là kiểm thử theo ranh giới:

- **Core unit tests:** kiểm tra business logic không cần khởi động Spring context.
- **App tests:** kiểm tra wiring Bean, Spring configuration, starter integration và startup.
- **Artifact smoke tests:** chạy đúng executable `app/build/libs/multi-demo-app.jar` để phát hiện packaging/classpath khác với IDE.

Nếu muốn bổ sung JUnit 5 test vào core, có thể thêm vào `core/build.gradle`:

~~~groovy
repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.3'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.3'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Đây là **mở rộng tùy chọn** cho project core; phiên bản cố định minh họa, không phải version mới nhất. Test Java của core có thể:

~~~java
package com.example.core;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingServiceTest {

    @Test
    void greetsByName() {
        String actual = new GreetingService().greet("Gradle");
        assertEquals("Hello, Gradle!", actual);
    }
}
~~~

Đặt file ở `core/src/test/java/com/example/core/GreetingServiceTest.java`. Sau đó chạy:

~~~bash
./gradlew :core:test
~~~

Khi assertions đúng, task test thành công (output Gradle có thể không in test result chi tiết). Đây không phải phần bắt buộc của project ở mục 4; nếu không thêm test dependencies/file, đừng mong có JUnit tests tự xuất hiện.

Đối với app, có thể thêm Spring Boot test starter và các test annotations phù hợp **trong chính app**, không để test dependency của core tự lan sang app. `testImplementation` của core không trở thành runtime dependency của app chỉ nhờ `implementation project(':core')`.

## 13. Plugin versions và dependency versions ở multi-project

Có ba tầng quản lý khác nhau:

| Đối tượng | Nơi có thể quản lý | Ví dụ |
| --- | --- | --- |
| Danh sách project | `settings.gradle(.kts)` | `include 'core', 'app'` |
| Gradle plugin versions/resolution | `plugins` hoặc `pluginManagement` trong settings | `org.springframework.boot` version |
| External dependency resolution | `repositories`, `dependencies`, BOM/platform, `dependencyResolutionManagement` | `spring-boot-starter`, JUnit |
| Inter-project dependency | `dependencies { implementation project(...) }` | App phụ thuộc core |

**Spring Boot BOM không tạo project dependency.** BOM quản lý versions của các external modules trong một configuration; nếu app cần code của `:core`, vẫn phải khai báo `project(':core')` và đưa `:core` vào settings.

**Đặt plugin Boot đúng nơi:** ứng dụng app mới cần `bootJar`. Chia sẻ Java toolchain hoặc test conventions ở root/settings có thể có giá trị, nhưng không nên áp plugin Boot vào core chỉ vì mọi project nằm trong một multi-project build.

### Project dependency có version không?

Trong cùng build, bạn viết `project(':core')` thay vì tọa độ kiểu `com.example:core:1.0.0`. Version của core có thể phục vụ artifact naming/publishing hoặc resolution metadata, nhưng không phải bạn đang yêu cầu download một core release từ repository. Nếu các module được phát hành độc lập và tiêu thụ qua Maven repo, lúc đó external dependency coordinates và versioning trở thành mô hình khác.

### Tránh vòng phụ thuộc

Không khai báo:

~~~groovy
// core/build.gradle (nếu làm thế này là sai kiến trúc cho ví dụ)
dependencies {
    implementation project(':app')
}
~~~

khi `app` đã `implementation project(':core')`. Đồ thị `:app → :core → :app` tạo chu trình dependency, có thể dẫn tới lỗi task dependency cycle hoặc resolution/compilation không hợp lệ. Thiết kế các module theo chiều có hướng: domain/core độc lập, application phụ thuộc core. Nếu hai module cần dùng types của nhau, trích một hợp đồng chung thành module thứ ba thay vì tạo vòng.

## 14. Chẩn đoán: Gradle không thấy project, class hay artifact

### Lệnh cần biết

~~~bash
./gradlew projects
./gradlew :app:tasks --all
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:bootJar --dry-run
./gradlew :app:bootJar --info
jar tf app/build/libs/multi-demo-app.jar
~~~

- `projects`: kiểm tra settings đã include đúng module/path.
- `:app:tasks --all`: xác định app có `bootJar` không.
- `compileClasspath`: kiểm tra app compile được API từ core và external dependencies cần thiết.
- `runtimeClasspath`: xem runtime graph, gồm project dependency và transitives phù hợp.
- `--dry-run`: xem task graph mà không thực thi task actions.
- `--info`: phân tích lý do task chạy, bị skip/up-to-date; log phụ thuộc phiên bản.
- `jar tf`: kiểm tra nội dung **artifact đã tạo**, không chỉ graph Gradle.

### Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Kiểm tra/cách sửa |
| --- | --- | --- |
| `Project with path ':core' could not be found in project ':app'` | Quên `include 'core'`, sai path hoặc settings root | Xem `settings.gradle` và `./gradlew projects` |
| `:core` có tên đúng nhưng không có sources/tasks | Mapping `projectDir` sai, directory rỗng hoặc plugin chưa áp dụng | Kiểm tra directory/build.gradle của core và project descriptor |
| `Could not find method implementation()` | Chưa áp dụng Java/Java Library plugin trong module | Áp plugin phù hợp để tạo dependency configuration |
| `ClassNotFoundException` với class core lúc runtime | App không có project dependency ở runtime hoặc package output sai | Xem `:app:runtimeClasspath`, `BOOT-INF/lib` và runtime logs |
| Java compiler app không thấy class public của core | Thiếu `implementation project(':core')` hoặc class không public/sai package | Kiểm tra dependencies, import và `core/src/main/java` |
| App compile không thấy type thuộc external API của core | Core dùng `implementation` cho type lộ trong public signature | Xem `java-library` `api` vs `implementation` |
| Cả core và app có `bootJar` khiến build không chọn đúng JAR | Áp Spring Boot plugin cho library không cần thiết | Chỉ app dùng Boot plugin; core dùng `java-library` |
| `bootJar` không tồn tại ở root | Root không phải module app | Gọi `:app:bootJar`, không giả định root có Boot task |
| Core build lặp lại quá nhiều | Build logic eager, khai báo input/output chưa chuẩn hoặc config chung không tối ưu | Dùng task graph/`--info`, tránh hard-coded task dependencies |
| `:app:bootJar` chạy nhưng artifact thiếu module core | Sai configuration/variant, packaging exclusion hoặc đã mở nhầm plain JAR | Xem project runtime dependency và đúng Boot artifact |
| Build chạy sai task trong multi-project | Gọi task name không có path hoặc từ sai directory | Dùng full task path `:app:bootJar` |
| Duplicate class hoặc resource ở nhiều module | Dùng copy source, shadow/merge sai hoặc phụ thuộc chồng lắp | Kiểm tra JAR contents, dependency graph, module responsibility |
| Module A phụ thuộc B và B phụ thuộc A | Vòng project dependency | Refactor dependency direction hoặc trích module API chung |
| Plugin resolution lỗi nhưng dependency project vẫn đúng | Plugin repositories/settings không phù hợp hoặc thiếu mạng | Phân biệt `pluginManagement` với `repositories` cho external libraries |
| IDE thấy module nhưng Gradle CLI không thấy | IDE import settings cũ, mở sai root hoặc chưa refresh Gradle | Chạy `./gradlew projects` từ root, reload Gradle trong IDE |

### Không tự sửa bằng `implementation files(...)`

Nếu lỗi “không tìm thấy `:core`”, nguyên nhân thường ở `settings.include` hoặc project path. Tránh sửa tạm thành:

~~~groovy
implementation files('../core/build/libs/core-1.0.0.jar')
~~~

vì điều này né project graph, làm build phụ thuộc file đầu ra tồn tại sẵn, không mô hình hóa producer tasks và transitive dependencies đúng cách. Dùng project dependency thì Gradle thực hiện linkage giữa modules một cách nhất quán.

### Vì sao IDE có thể chạy nhưng CI lỗi?

IDE có thể vẫn giữ classpath từ import cũ hoặc module dependency do người dùng cấu hình riêng, trong khi CI dùng Gradle settings và build scripts trên repository. **Gradle CLI là chuẩn để kiểm chứng build có thể tái lập.** Khi xảy ra bất đồng, chạy từ root với Wrapper, xem `projects`, `dependencies` và task graph trước khi sửa code Java.

## 15. Thiết kế module Spring Boot trong thực tế

Một ứng dụng có thể mở rộng thành:

~~~text
enterprise-app/
├── settings.gradle
├── domain/           (java-library)
├── application/      (java-library)
├── persistence/      (java-library hoặc plugin phù hợp)
├── web-api/          (Spring Boot executable application)
└── batch-job/        (Spring Boot executable application)
~~~

Quan hệ ví dụ:

~~~text
:web-api  ----> :application ----> :domain
                  ^
                  |
:persistence ------+
:batch-job ------> :application
~~~

Đây là sơ đồ ý tưởng, **không phải một project graph duy nhất phải áp cho mọi hệ thống**. Tránh để `:domain` phụ thuộc ngược vào `:web-api`. Những module tạo executable service (`:web-api`, `:batch-job`) có thể áp Boot plugin; các module library nên có plugin/build target riêng.

### Cách tách từ một project Spring Boot lớn

1. **Xác định public boundary:** service/domain types nào phải được app dùng?
2. **Tạo thư mục module** và `build.gradle` phù hợp, ví dụ `core` áp `java-library`.
3. **Thêm `include 'core'`** trong root settings.
4. **Chuyển code** với package giữ đúng hoặc đổi có kiểm soát, điều chỉnh imports/tests.
5. **Thêm `implementation project(':core')`** vào module app.
6. **Loại bỏ dependency đảo chiều** từ core về app; nếu cần, trích interface/contract sang module chia sẻ.
7. **Kiểm tra Spring component scan/auto-configuration**: app có nhìn thấy bean từ module tách ra không? Project dependency chỉ cung cấp classpath, không bảo đảm bean registration.
8. **Chạy tests của cả hai modules**, build Boot archive của app, đọc JAR và smoke test `java -jar`.
9. **Dọn cấu hình trùng** dần bằng convention plugins/BOM/repositories management nếu có nhiều subprojects.
10. **Ghi rõ đường CI/CD**: task `:web-api:bootJar` khác `:domain:jar`, không publish nhầm library như ứng dụng thực thi.

### Ranh giới giữa source module và deployment unit

Multi-project không có nghĩa phải triển khai từng module. Trong ví dụ, `:core` là **code module**, không phải service tự chạy. `:app` là **deployment unit**. Executable archive của app gom code ứng dụng và các dependency cần thiết, bao gồm core. Khi deploy app, bạn không cần đưa một tiến trình Java riêng cho core.

Ngược lại, nếu một project thực sự là microservice độc lập, nó có main class và deploy artifact riêng; không nên coi nó là `java-library` chỉ vì cùng repository.

## 16. Checklist thực hành cho developer và CI

Trước khi báo build đa module đã đúng, xác nhận:

- **Settings:** root name có chủ đích, `include` liệt kê đúng mọi module cần thiết.
- **Project paths:** `:app`, `:core` và các path lồng khớp directory hoặc `projectDir` đã đặt.
- **Plugins:** library dùng `java-library`, Boot executable module áp Spring Boot plugin; không áp plugin không cần thiết.
- **Dependencies:** app dùng `implementation project(':core')`, không copy file JAR bằng path hard-code.
- **API boundary:** core chỉ dùng `api` cho dependencies thật sự lộ trong public ABI, còn logic nội bộ dùng `implementation`.
- **Build order:** Gradle tự resolve producer tasks, không thêm `dependsOn` cross-project vô cớ.
- **Tests:** core và app có phạm vi test riêng, không kéo test-only libraries vào runtime production.
- **Artifact:** `:app:bootJar` tạo executable JAR và chứa đúng module core/runtime dependencies.
- **Runtime:** chạy thật `java -jar` để xác nhận classpath, bean wiring và môi trường triển khai.
- **Tái lập:** dùng Gradle Wrapper, project repositories và plugin versions nhất quán; không dựa vào IDE hoặc JAR từ lượt build cũ.

## 17. Câu hỏi tự kiểm tra

**Câu 1:** Thêm `include 'core'` trong `settings.gradle` có tự làm app phụ thuộc core không?

**Trả lời:** Không. `include` chỉ khai báo project tham gia build; phải thêm `implementation project(':core')` trong app hoặc một dependency quan hệ tương ứng.

**Câu 2:** `implementation project(':core')` khác `implementation 'com.example:core:1.0.0'` như thế nào?

**Trả lời:** Cách đầu tiêu thụ project `:core` trong cùng Gradle build, Gradle tự chọn output/variant và task dependencies. Cách sau resolve một external module theo tọa độ và version từ repository/cơ chế resolution.

**Câu 3:** Vì sao `:core` không nhất thiết phải áp Spring Boot plugin?

**Trả lời:** Vì `:core` là library Java, không có deployment entry point. `java-library` là plugin phù hợp để tạo plain JAR và phân tách API/implementation; app mới cần `bootJar`/launcher.

**Câu 4:** Khi app chạy `:app:bootJar`, có phải chạy `:core:jar` bằng tay trước không?

**Trả lời:** Không với project dependency chuẩn. Gradle nối producer/consumer tasks theo dependency graph/variants và build những output cần thiết.

**Câu 5:** Khác gì giữa `:core` và `core/src/main/java`?

**Trả lời:** `:core` là Gradle logical project path. `core/src/main/java` là directory vật lý của Java source thuộc module đó theo mapping mặc định.

**Câu 6:** Khi code của core có một public method trả type thuộc dependency ngoài, nên khai báo dependency đó ở `api` hay `implementation`?

**Trả lời:** Thường dùng `api` vì consumer cần type đó để compile public ABI. Nếu type chỉ dùng nội bộ trong method body, ưu tiên `implementation`.

**Câu 7:** Vì sao bean ở package `com.example.core` không tự xuất hiện chỉ vì app có project dependency đến core?

**Trả lời:** Project dependency chỉ đặt class/resources vào classpath. Spring bean registration còn tùy component scan, annotation, configuration hoặc explicit `@Bean`; ví dụ đăng ký bean ở app.

**Câu 8:** Có thể dùng `includeBuild('core')` thay `include 'core'` rồi vẫn gọi `project(':core')` như bình thường không?

**Trả lời:** Không mặc định. `includeBuild` dùng composite build/included build với semantics khác; project dependency theo `:core` yêu cầu core là subproject trong cùng settings hierarchy.

**Câu 9:** Muốn tạo executable JAR đúng module khi root không có Boot plugin thì chạy gì?

**Trả lời:** `./gradlew :app:bootJar`, không phải mặc định `./gradlew bootJar` ở root mà không biết task-selection behavior.

## 18. Tài liệu chính thức

- Gradle — [Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): `settings.gradle`, `include`, project descriptors và project dependencies.
- Gradle — [Structuring Multi-Project Builds](https://docs.gradle.org/current/userguide/intro_multi_project_builds.html): cấu trúc subprojects và task paths.
- Gradle — [The Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): `api`, `implementation` và outgoing variants.
- Gradle — [Declaring Dependencies Between Subprojects](https://docs.gradle.org/current/userguide/declaring_dependencies_between_subprojects.html): project dependencies và quan hệ build.
- Gradle — [Centralizing Repository Declarations](https://docs.gradle.org/current/userguide/centralizing_repositories.html): `dependencyResolutionManagement` và `RepositoriesMode`.
- Gradle — [Sharing Build Logic Between Subprojects](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html): convention plugins cho các build lớn.
- Spring Boot — [Gradle Packaging Executable Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html): `bootJar`, Java plugin và runtime dependencies.
- Spring Boot — [Gradle Running Your Application](https://docs.spring.io/spring-boot/gradle-plugin/running.html): `bootRun` và development classpath.

**Ghi nhớ:** `settings.gradle` quyết định **module nào tồn tại trong build**; `implementation project(':core')` quyết định **app phụ thuộc module nào**; Java Library plugin xác định **API và runtime variants**; Spring Boot plugin đóng gói **module ứng dụng** thành executable artifact. Để biết mọi thứ thực sự vận hành đúng, hãy kiểm chứng **project hierarchy → dependency graph → task graph → executable JAR**.
