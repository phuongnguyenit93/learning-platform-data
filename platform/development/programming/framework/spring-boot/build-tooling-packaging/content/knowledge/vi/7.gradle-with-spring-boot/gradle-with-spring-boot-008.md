# Quản lý cấu hình dùng chung qua convention plugin và version catalog trong Gradle

## 1. Mục tiêu: chia đúng trách nhiệm của cấu hình build

Trong một repository Spring Boot có nhiều module Gradle, việc lặp các khối `plugins`, `java.toolchain`, `repositories`, `tasks.test`, cấu hình `bootJar` và số phiên bản dependency ở mọi `build.gradle` khiến các module dễ lệch nhau. Bài này chỉ ra hai cơ chế bổ sung cho nhau:

- **Convention plugin** đóng gói **hành vi và quy ước build có thể tái sử dụng**: áp dụng plugin, cấu hình Java toolchain, JUnit Platform, compiler options, kiểm tra chất lượng và những task chung. Module áp dụng convention bằng một plugin ID rõ ràng.
- **Version catalog** tập trung **tọa độ thư viện, phiên bản và plugin aliases**: thường ở `gradle/libs.versions.toml`, được dùng qua accessor `libs` để tránh lặp tên và số phiên bản trong mỗi build script.

Hai cơ chế giải quyết hai vấn đề khác nhau. Version catalog **không tự áp dụng plugin, không thêm dependency vào classpath và không tạo quality gate**. Convention plugin có thể thiết lập điều đó, nhưng không nên tùy tiện chốt các version giống nhau ở nhiều file.

### Đầu ra cần đạt

Sau bài học, bạn có thể:

1. Phân loại phần nào thuộc version catalog, phần nào thuộc convention plugin và phần nào phải ở riêng module ứng dụng.
2. Tạo `build-logic` như một **included build** chứa precompiled Groovy convention plugins.
3. Cho `build-logic` đọc cùng một `libs.versions.toml` với main build mà không tưởng hai build tự chia sẻ mọi extension.
4. Đưa Spring Boot Gradle plugin lên classpath của convention plugin đúng cách.
5. Tạo một library module và một Spring Boot application module theo quy ước Java 17, JUnit, BOM và executable JAR.
6. Dùng task graph, dependency reports và test/artifact thực tế để chứng minh các quy ước có hiệu lực.
7. Giải thích giới hạn của catalog: **alias không phải dependency lockfile hay cơ chế cưỡng chế version**.

Tài liệu và ví dụ dùng **Gradle Groovy DSL**, Java 17, Gradle Wrapper 8.10.2 và Spring Boot 3.3.13 để có một bộ số phiên bản nhất quán. Đây là cấu hình minh họa, không phải khẳng định phiên bản hiện tại mới nhất. Dự án thực tế cần chốt phiên bản tương thích và được hỗ trợ theo chính sách riêng.

## 2. Mô hình tổ chức: ai chịu trách nhiệm điều gì?

| Thành phần | Vị trí điển hình | Chứa gì? | Không chịu trách nhiệm |
| --- | --- | --- | --- |
| `settings.gradle` | root build | Tên dự án, danh sách subproject, included build, plugin/dependency repositories. | Không nên chứa toàn bộ cấu hình compile/test của từng module. |
| `gradle/libs.versions.toml` | root build | Version key, library alias, plugin alias, bundle. | Không áp dụng plugin hoặc tạo dependency thực tế. |
| `build-logic` | một included build | Precompiled convention plugins, những phụ thuộc build-time để triển khai chúng. | Không phải module runtime của ứng dụng Spring Boot. |
| `acme.java-conventions` | plugin trong `build-logic` | Java plugin, toolchain Java 17, test task/JUnit, quy tắc Java chung. | Không ép mọi thư viện thành executable Boot JAR. |
| `acme.spring-boot-app` | plugin trong `build-logic` | Áp dụng Java convention + Spring Boot plugin cho module thực thi. | Không quyết định mọi dependency nghiệp vụ mà module cần. |
| `core/build.gradle` | module library | Chọn plugin Java library/convention, khai báo dependency riêng. | Không phải nơi khai báo global version của Spring Boot. |
| `app/build.gradle` | module app | Chọn app convention, import Spring Boot BOM, khai báo starter và dependency tới core. | Không cần lặp logic Java toolchain và cấu hình test đã nằm trong convention. |

**Nguyên tắc thiết kế:** một module nói rõ nó **thuộc loại gì** bằng plugin ID; convention định nghĩa **quy tắc dành cho loại đó**; catalog giữ **danh tính/phiên bản của dependency và plugin**. Giữ phần tùy biến thực sự thuộc module trong build script module thay vì chuyển hết vào một plugin khổng lồ.

### 2.1. Vì sao tránh cấu hình lặp qua `subprojects { ... }`?

Cách ngắn ban đầu là đặt trong root:

~~~groovy
// Chỉ là phản ví dụ về cấu hình áp cho mọi module:
subprojects {
    apply plugin: 'java'
    tasks.withType(Test).configureEach {
        useJUnitPlatform()
    }
}
~~~

Cách này tạo **cross-project configuration**: khi mở `app/build.gradle`, người đọc khó nhận ra nhiều rule đang được áp từ root. Cấu hình module trở nên phụ thuộc quá nhiều vào module khác và khó tối ưu configuration cache/parallelism. Một library, Boot app và platform/aggregator cũng không nên bắt buộc dùng cùng một plugin.

Trong phương án convention:

~~~groovy
// app/build.gradle
plugins {
    id 'acme.spring-boot-app'
}
~~~

Người đọc nhìn thấy rõ loại build mà module yêu cầu. Không cấm mọi trường hợp dùng `subprojects`, nhưng với quy ước plugin/test/Java chung, convention plugin giúp ranh giới rõ hơn.

## 3. Version catalog: cấu trúc, accessor và giới hạn

Gradle tự nhận catalog mặc định từ `gradle/libs.versions.toml` trong **main build**. File TOML có bốn nhóm phổ biến:

- `[versions]`: tên version và giá trị.
- `[libraries]`: alias trỏ đến `group:artifact`, có thể tham chiếu version key hoặc bỏ version.
- `[plugins]`: alias trỏ tới plugin ID + version, dùng trong `plugins { alias(...) }` ở build script thông thường.
- `[bundles]`: nhóm nhiều library aliases để khai báo gọn hơn, không tự thêm chúng nếu không được tham chiếu.

Ví dụ tối giản:

~~~toml
[versions]
spring-boot = "3.3.13"

[libraries]
spring-boot-bom = { module = "org.springframework.boot:spring-boot-dependencies", version.ref = "spring-boot" }
spring-boot-starter-web = { module = "org.springframework.boot:spring-boot-starter-web" }
spring-boot-starter-test = { module = "org.springframework.boot:spring-boot-starter-test" }

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "spring-boot" }
~~~

Phép ánh xạ accessor thường được sinh từ dấu gạch ngang: `spring-boot-bom` → `libs.spring.boot.bom`, `spring-boot-starter-web` → `libs.spring.boot.starter.web`, `spring-boot` trong mục plugin → `libs.plugins.spring.boot`.

Ví dụ dùng từ một `build.gradle` thông thường:

~~~groovy
plugins {
    alias(libs.plugins.spring.boot)
}

dependencies {
    implementation(platform(libs.spring.boot.bom))
    implementation(libs.spring.boot.starter.web)
}
~~~

Đây chỉ là **đoạn minh họa cách dùng accessor**. Đừng thêm alias Boot plugin vào cùng module nếu module đó đã áp dụng `acme.spring-boot-app` và convention ấy đã áp dụng Boot plugin. Trong ví dụ hoàn chỉnh bên dưới, app áp dụng convention để quản lý plugin tập trung.

### 3.1. Alias có thể không khai báo version

Hai starter trong TOML trên **không có version**. Điều này có chủ đích: module Spring Boot sẽ import BOM bằng `platform(...)`. BOM cung cấp các constraints/phiên bản liên quan; Gradle giải quyết dependency graph với BOM và các ràng buộc khác.

Lỗi thường gặp là bỏ cả BOM lẫn version trong catalog, rồi viết:

~~~groovy
dependencies {
    implementation(libs.spring.boot.starter.web)
}
~~~

Khi đó module không có nơi quản lý version cho starter, nên dependency resolution có thể báo thiếu version. Chỉ tạo alias không có nghĩa Gradle sẽ tự “đọc version từ Spring Boot Gradle plugin”.

### 3.2. Catalog không tự ép version được chọn

Nếu catalog khai báo phiên bản thư viện A là X, Gradle vẫn có thể chọn Y theo dependency graph, constraints/platform và conflict resolution. Alias chỉ đưa **dependency notation** và yêu cầu version vào khai báo nơi nó được dùng.

- `platform(BOM)` đưa version constraints vào graph, thường là recommendations, có thể bị nâng theo graph.
- `enforcedPlatform(BOM)` có quyền cưỡng chế phiên bản và có thể tác động xuống consumer; chỉ dùng khi chủ ý đánh đổi và hiểu ảnh hưởng.
- `version catalogs` không thay thế **dependency locking**, dependency verification, vulnerability scanning hoặc phân tích tương thích runtime.
- `bundles` chỉ gộp aliases để viết ngắn; không tạo ranh giới dependency scope, không kiểm tra tương thích giữa các member.

Dùng `dependencyInsight` để biết version **được chọn thật** và **lý do chọn**, thay vì chỉ đọc số version trong TOML.

## 4. Convention plugin: build logic hoạt động như một plugin thực sự

Gradle hỗ trợ hai cách chia sẻ build logic thường gặp:

- **`buildSrc/`:** một build đặc biệt được Gradle tự động nhận, phù hợp dự án nhỏ nhưng thay đổi build logic có thể ảnh hưởng phạm vi cấu hình rộng.
- **Included build `build-logic/`:** được đăng ký rõ trong settings, có thể quản lý, kiểm thử và phát hành plugin độc lập khi cần; phù hợp multi-project/đội lớn.

Bài này dùng **included build** với **precompiled Groovy script plugins**. Một file:

~~~text
build-logic/src/main/groovy/acme.java-conventions.gradle
~~~

trở thành plugin với ID:

~~~text
acme.java-conventions
~~~

Đuôi `.gradle` quyết định Groovy DSL; nếu đổi sang `.gradle.kts` cần viết lại bằng Kotlin DSL và dùng `kotlin-dsl` plugin trong build-logic. **Đừng trộn cú pháp `def`/Groovy closure vào file `.gradle.kts`.**

### 4.1. Precompiled plugin có classpath riêng

Một quy tắc quan trọng của Gradle:

- Plugin lõi như `java`, `java-library` có sẵn cho precompiled convention plugin.
- Đối với external plugin như `org.springframework.boot`, build tạo convention plugin phải có **dependency triển khai plugin** trên classpath (ví dụ `org.springframework.boot:spring-boot-gradle-plugin`).
- Trong khối `plugins` của chính precompiled script plugin, áp external plugin bằng `id 'org.springframework.boot'` **không kèm version**. Version được xác định bởi dependency của `build-logic`.
- `alias(libs.plugins.spring.boot)` **không dùng trực tiếp trong `plugins` block của precompiled script plugin** như cách dùng trong một build script bình thường.
- Main build và `build-logic` là hai **build riêng**. `libs` của main build không tự xuất hiện trong build-logic; muốn dùng cùng catalog, import TOML vào settings của build-logic.

Đây là chỗ hay sai nhất khi mới chuyển cấu hình từ một `app/build.gradle` sang convention plugin.

## 5. Ví dụ end-to-end: một Spring Boot app và một Java library dùng chung quy ước

### 5.1. Cây file

Dự án mô phỏng một HTTP service `app` gọi hàm Java từ thư viện `core`:

~~~text
shared-build-demo/
├── settings.gradle
├── gradle/
│   ├── libs.versions.toml
│   └── wrapper/...
├── gradlew
├── gradlew.bat
├── build-logic/
│   ├── settings.gradle
│   ├── build.gradle
│   └── src/main/groovy/
│       ├── acme.java-conventions.gradle
│       └── acme.spring-boot-app.gradle
├── core/
│   ├── build.gradle
│   └── src/main/java/com/example/core/Greeting.java
└── app/
    ├── build.gradle
    ├── src/main/java/com/example/app/Application.java
    └── src/test/java/com/example/app/ApplicationTest.java
~~~

Các file Wrapper (`gradle-wrapper.jar`, `gradle-wrapper.properties`, `gradlew`, `gradlew.bat`) phải có trong dự án để lệnh ở dưới sử dụng được. Ví dụ giả định đã tạo và lưu Wrapper version 8.10.2, một version Gradle 8.x phù hợp dòng Spring Boot 3.3. Không đưa nội dung JAR nhị phân vào bài README.

### 5.2. File catalog chung

`gradle/libs.versions.toml`:

~~~toml
[versions]
spring-boot = "3.3.13"

[libraries]
# Artifact plugin để build-logic có thể apply org.springframework.boot.
spring-boot-gradle-plugin = { module = "org.springframework.boot:spring-boot-gradle-plugin", version.ref = "spring-boot" }

# BOM là nguồn quản lý dependency versions cho ứng dụng.
spring-boot-bom = { module = "org.springframework.boot:spring-boot-dependencies", version.ref = "spring-boot" }

# Các starter và launcher không có version: nhận version từ BOM.
spring-boot-starter-web = { module = "org.springframework.boot:spring-boot-starter-web" }
spring-boot-starter-test = { module = "org.springframework.boot:spring-boot-starter-test" }
junit-platform-launcher = { module = "org.junit.platform:junit-platform-launcher" }

[plugins]
# Dùng khi module áp dụng Boot trực tiếp, không dùng song song với app convention.
spring-boot = { id = "org.springframework.boot", version.ref = "spring-boot" }
~~~

**Vì sao cần cả `spring-boot-gradle-plugin` và `spring-boot-bom`?** Một cái là **plugin chạy lúc Gradle cấu hình/build**, một cái là **BOM cung cấp version constraints cho dependency runtime/test**. Dùng chung key `spring-boot` giúp không vô tình dùng plugin 3.3.13 và BOM của một dòng Boot khác.

### 5.3. Main `settings.gradle`: khai báo module và tìm convention plugin

`settings.gradle` ở root:

~~~groovy
pluginManagement {
    // Included plugin build phải được đăng ký trước khi app dùng plugin ID của nó.
    includeBuild('build-logic')

    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'shared-build-demo'
include('core', 'app')
~~~

- `includeBuild('build-logic')` cho Gradle thấy các plugin do included build cung cấp khi phân giải `plugins` của subproject.
- `include('core', 'app')` tạo **hai subproject** cùng thuộc main build. `build-logic` là **included build**, không đồng nghĩa `include('build-logic')` như một runtime library subproject.
- `pluginManagement.repositories` dùng để tìm plugin; `dependencyResolutionManagement.repositories` dùng để giải quyết library/BOM. Đây là hai phạm vi khác nhau.
- Version catalog mặc định nằm tại `gradle/libs.versions.toml` nên Gradle nạp tự động cho main build; không cần gọi `from(...)` lần nữa trong main settings.

### 5.4. `build-logic/settings.gradle`: import lại catalog vì đây là build riêng

`build-logic/settings.gradle`:

~~~groovy
rootProject.name = 'build-logic'

dependencyResolutionManagement {
    versionCatalogs {
        libs {
            from(files('../gradle/libs.versions.toml'))
        }
    }
}
~~~

`../gradle/libs.versions.toml` là file của root build nhìn từ thư mục `build-logic`. Trong **build-logic** không có một file `gradle/libs.versions.toml` khác được tự nhận, nên catalog này được tạo từ **một file đã có**.

Chú ý:

1. `from(...)` chỉ nhận một file cho mỗi lần import catalog; không gọi `from(...)` nhiều lần cho cùng `libs`.
2. Khi tách build-logic ra repository riêng, đường dẫn tương đối này cần đổi sang catalog được publish hoặc cơ chế chia sẻ khác.
3. Đây là chia sẻ **định nghĩa version**; nó không làm mọi dependency/plugin của main build tự xuất hiện trên classpath của build-logic.

### 5.5. `build-logic/build.gradle`: đăng ký khả năng biên dịch convention

`build-logic/build.gradle`:

~~~groovy
plugins {
    id 'groovy-gradle-plugin'
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}

dependencies {
    // Alias này được import vào build-logic ở build-logic/settings.gradle.
    // Version của Boot plugin đến từ đúng một key trong TOML root.
    implementation(libs.spring.boot.gradle.plugin)
}
~~~

`groovy-gradle-plugin` là plugin chuẩn cho precompiled Groovy script plugin. `implementation(libs.spring.boot.gradle.plugin)` đưa **artifact Spring Boot Gradle plugin** vào compile/runtime classpath của convention plugin; không thêm artifact này vào runtime classpath của ứng dụng Web.

Nếu thiếu khai báo trên, file `acme.spring-boot-app.gradle` ở phần sau có thể lỗi resolve `org.springframework.boot` khi Gradle build build-logic. Đừng khắc phục bằng cách thêm `version '3.3.13'` ngay trong `plugins` của precompiled script plugin: cú pháp version trực tiếp không được hỗ trợ cho external plugin tại đó.

### 5.6. Convention thứ nhất: Java toolchain và JUnit

`build-logic/src/main/groovy/acme.java-conventions.gradle`:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

// Áp dụng cho mọi task kiểu Test được tạo trong module.
// Cấu hình theo kiểu lazy để task đăng ký sau cũng nhận quy ước.
tasks.withType(org.gradle.api.tasks.testing.Test).configureEach {
    useJUnitPlatform()
}
~~~

**Ý nghĩa từng dòng:**

- `id 'java'` cung cấp main/test source sets và tasks như `classes`, `test`, `check`, `jar`, `build`.
- `java.toolchain` khiến Gradle dùng compiler/runtime toolchain Java 17 thích hợp; bản thân nó không cài JDK nếu môi trường chưa có và toolchain provisioning chưa cấu hình.
- `tasks.withType(Test).configureEach` định nghĩa quy ước test dùng JUnit Platform cho tất cả Test tasks hiện có/được đăng ký sau.
- Plugin này **không tạo executable Boot JAR**, nên áp dụng được cho cả Java library.

Nếu tổ chức muốn bắt buộc thêm Checkstyle, JaCoCo, compile options hoặc test logging, đặt rule ở convention này hoặc một convention chuyên trách, nhưng chỉ nối vào `check` những gate mà dự án thực sự định dùng. Không nhét mọi library test dependency vào module nếu module đó không cần.

### 5.7. Convention thứ hai: áp dụng Spring Boot cho app

`build-logic/src/main/groovy/acme.spring-boot-app.gradle`:

~~~groovy
plugins {
    id 'acme.java-conventions'
    id 'org.springframework.boot'
}
~~~

Hai dòng trên đã mang nhiều ý nghĩa:

1. `acme.java-conventions` áp dụng Java plugin, Java 17 và JUnit Platform.
2. `org.springframework.boot` được resolve từ plugin artifact mà `build-logic/build.gradle` khai báo, nên không ghi version ngay tại đây.
3. Spring Boot plugin thấy Java plugin có mặt sẽ thêm các task và integration thích hợp, điển hình là `bootJar` và `bootRun`.
4. Plugin app sẽ được **chọn công khai bởi `app/build.gradle`**; không bị áp vào `core` ngoài ý muốn.

**Câu hỏi quan trọng:** vì sao không viết `dependencies { implementation spring-boot-starter-web }` trong convention này? Được phép nếu tổ chức chủ ý bắt mọi Boot app dùng Web, nhưng ví dụ này muốn giữ quyền lựa chọn giữa **Web, Batch, CLI hoặc app không có HTTP** cho từng module. Vì vậy convention chỉ định *cách build*, còn app chọn *chức năng runtime* và import BOM cùng các starter phù hợp.

## 6. Module Java library và module Spring Boot app

### 6.1. Thư viện `core`

`core/build.gradle`:

~~~groovy
plugins {
    id 'java-library'
    id 'acme.java-conventions'
}

group = 'com.example'
version = '0.1.0'
~~~

Cả `java-library` và Java convention đều có thể áp `java`; Gradle xử lý plugin application theo idempotent semantics, không biên dịch đôi chỉ vì hai plugin cùng cần Java. `java-library` mang cấu hình `api`/`implementation` dành cho thư viện; Java convention mang Java toolchain và JUnit.

`core/src/main/java/com/example/core/Greeting.java`:

~~~java
package com.example.core;

public final class Greeting {
    private Greeting() {
    }

    public static String reply() {
        return "pong";
    }
}
~~~

Đây là Java class độc lập, không dùng Spring. Khi chạy `./gradlew :core:build`, thư viện có JAR thông thường cho các module khác dùng; **không có lý do tạo Boot executable JAR** từ module này.

### 6.2. Ứng dụng `app`

`app/build.gradle`:

~~~groovy
plugins {
    id 'acme.spring-boot-app'
}

group = 'com.example'
version = '0.1.0'

dependencies {
    implementation(project(':core'))

    // Hai classpath cần BOM: runtime/main và test.
    implementation(platform(libs.spring.boot.bom))
    testImplementation(platform(libs.spring.boot.bom))

    implementation(libs.spring.boot.starter.web)
    testImplementation(libs.spring.boot.starter.test)
    testRuntimeOnly(libs.junit.platform.launcher)
}
~~~

**Giải thích:**

- Module áp đúng **một app convention ID**, không cần lặp `java`/`org.springframework.boot`/toolchain/JUnit configuration.
- `implementation(project(':core'))` tạo dependency thực tới Java library trong main build.
- `implementation(platform(libs.spring.boot.bom))` thêm version constraints Boot vào main dependency graph.
- `testImplementation(platform(libs.spring.boot.bom))` làm tương tự cho test dependency graph. Các configuration và kế thừa có thể khiến BOM xuất hiện gián tiếp, nhưng khai báo tường minh giúp lớp học quan sát rõ.
- Các starter/library aliases không có version vì đã được BOM quản lý.
- `testRuntimeOnly(libs.junit.platform.launcher)` bảo đảm launcher của JUnit Platform có mặt khi Gradle chạy test. Nó không đưa test engine vào artifact production.
- Spring Boot plugin từ convention tạo `bootJar` executable cho `app`; `core` vẫn dùng library JAR.

**Mối quan hệ giữa catalog và BOM:** Catalog cung cấp *đường dẫn tới BOM và starter*; chính `platform(...)` mới thêm BOM vào graph. Không phải chỉ vì có TOML là dependency alignment tự có.

### 6.3. Main class của `app`

`app/src/main/java/com/example/app/Application.java`:

~~~java
package com.example.app;

import com.example.core.Greeting;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return Greeting.reply();
    }
}
~~~

`@SpringBootApplication` là điểm vào của app; `@RestController` và `@GetMapping` công bố `GET /ping`. Handler gọi `Greeting.reply()` từ module `core`, vì vậy ví dụ chứng minh **dependency nội bộ đã được nối đúng** vào app. Source cần được đặt tại đúng path/package như trên; chỉ chạy `javac Application.java` trơ trọi sẽ thiếu dependency Spring nên không phải lệnh biên dịch phù hợp.

### 6.4. Test tích hợp nhẹ bằng MockMvc

`app/src/test/java/com/example/app/ApplicationTest.java`:

~~~java
package com.example.app;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApplicationTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void pingDelegatesToCore() throws Exception {
        mvc.perform(get("/ping"))
           .andExpect(status().isOk())
           .andExpect(content().string("pong"));
    }
}
~~~

Test này tải Spring test context và thử request mapping thông qua MockMvc; nó **không mở cổng HTTP thật** và **không kiểm thử binary JAR đã đóng gói**. Mục tiêu là minh chứng JUnit Platform trong convention hoạt động, BOM quản lý test dependency, module `core` được sử dụng và endpoint trả nội dung mong đợi.

Nếu test thành công, câu chuyện đầy đủ vẫn cần `bootJar` và smoke test `java -jar` để xác nhận artifact.

## 7. Bản đồ phụ thuộc giữa các lớp cấu hình

Sơ đồ sau là một mô hình nguyên nhân, **không phải thứ tự thực thi Gradle tasks**:

~~~mermaid
flowchart TD
    TOML["gradle/libs.versions.toml"]
    ROOT["main settings.gradle"]
    LOGIC["build-logic/settings.gradle + build.gradle"]
    JAVA["acme.java-conventions"]
    BOOT["acme.spring-boot-app"]
    CORE["core/build.gradle"]
    APP["app/build.gradle"]
    BOM["Spring Boot BOM / platform"]
    JAR["app:bootJar"]

    ROOT -->|"includeBuild"| LOGIC
    ROOT -->|"include subprojects"| CORE
    ROOT -->|"include subprojects"| APP
    TOML -->|"auto-import in main build"| APP
    TOML -->|"explicit import"| LOGIC
    LOGIC -->|"plugin artifact classpath"| BOOT
    LOGIC --> JAVA
    JAVA --> CORE
    JAVA --> BOOT
    BOOT --> APP
    APP -->|"platform(libs...)"| BOM
    CORE -->|"project dependency"| APP
    APP --> JAR
~~~

**Lưu ý thứ tự ý nghĩa:** library alias ≠ dependency thực; plugin alias ≠ plugin đã được áp dụng; plugin build classpath ≠ runtime application classpath; included build ≠ normal subproject.

Với ví dụ này, thay đổi `[versions] spring-boot` ở TOML có thể ảnh hưởng cả:
- Version artifact Spring Boot plugin mà `build-logic` dùng để áp dụng.
- Version Spring Boot BOM mà app dùng để chọn dependency.
- Version plugin alias `libs.plugins.spring.boot` cho các module áp dụng trực tiếp nếu có.

Nhưng thay version không làm mã ứng dụng tự tương thích; luôn build, test và kiểm tra artifact sau thay đổi.

## 8. Các bước kiểm chứng trên Gradle Wrapper

Chạy trong root `shared-build-demo`, sau khi đã có JDK 17, Wrapper Gradle 8.10.2 và có quyền tải các dependency. Với Linux/macOS dùng `./gradlew`; Windows dùng `gradlew.bat`.

### 8.1. Bước A: cấu hình và plugin có được resolve không?

~~~bash
./gradlew --version
./gradlew projects
./gradlew :app:tasks --all
./gradlew :core:tasks --all
~~~

Kỳ vọng có `:app` và `:core` là subproject. Trong app xuất hiện task `bootJar`/`bootRun` do Spring Boot plugin. Trong core xuất hiện `jar`/`test` theo Java plugins, không có `bootJar` nếu không ai thêm Boot plugin. Một task được liệt kê chỉ chứng minh **được đăng ký**, chưa chứng minh test hay package đã chạy.

Nếu `Plugin [id: 'acme.spring-boot-app'] was not found`, kiểm tra `pluginManagement.includeBuild('build-logic')`, tên file/id và compile output của build-logic trước khi tìm thư viện ở app.

### 8.2. Bước B: xem task graph mà không chạy

~~~bash
./gradlew :app:build --dry-run
./gradlew :core:build --dry-run
~~~

Kỳ vọng `:app:build` bao gồm các nhánh compile/test/check/assemble, có Boot packaging (vì app convention áp Boot plugin). `:core:build` chỉ có Java library packaging và những task test/verification được khai báo. `--dry-run` không thực thi tests; các dòng giả lập không được ghi thành kết quả PASS.

### 8.3. Bước C: chạy test và build thật

~~~bash
./gradlew clean :core:build :app:build
~~~

Kỳ vọng:

- Java source của core được biên dịch.
- App compile thành công với class `Greeting` từ dependency `project(':core')`.
- `:app:test` chạy test `pingDelegatesToCore` và report cho biết test pass.
- `:app:bootJar` tạo executable Spring Boot JAR.
- `:core:jar` tạo library JAR thường.

Chú ý `clean` không tự dọn toàn bộ subproject nếu task path/cấu hình của bạn chỉ tác động root; để dọn đúng hai module trong dự án có cấu hình root riêng, dùng tường minh:

~~~bash
./gradlew :core:clean :app:clean :core:build :app:build
~~~

Dòng sau là quy trình vệ sinh output theo module; không cần xóa cache hay `.gradle` trên toàn máy.

Report app thường ở:

~~~text
app/build/test-results/test/
app/build/reports/tests/test/
~~~

Nếu `NO-SOURCE` hoặc `0 tests` trong module đáng lẽ có test, hãy kiểm tra path `src/test/java`, class name, JUnit dependency/launcher và `useJUnitPlatform()`. `BUILD SUCCESSFUL` một mình không cho biết test được phát hiện bao nhiêu.

### 8.4. Bước D: kiểm tra dependency resolution thật

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath

# Ví dụ xác định phiên bản Spring Web được Gradle chọn
./gradlew :app:dependencyInsight --configuration runtimeClasspath --dependency spring-web
~~~

Kỳ vọng thấy Spring Boot BOM/platform constraints được áp dụng và các thư viện Spring phù hợp trong dependency graph. `dependencyInsight` giúp phân biệt **requested version**, **selected version**, constraint/BOM và conflict resolution.

Không dùng câu “catalog khóa mọi dependency” để mô tả trạng thái này. Nếu có phiên bản ngoài BOM được chọn, Gradle report/insight là nguồn phân tích. Nếu dự án yêu cầu bất biến version ở mức cao hơn, nghiên cứu dependency locking hoặc constraints phù hợp.

### 8.5. Bước E: kiểm tra executable artifact thực

~~~bash
./gradlew :app:bootJar
jar tf app/build/libs/app-0.1.0.jar
~~~

Với cấu hình mặc định của ví dụ, `app/build/libs/app-0.1.0.jar` là tên Boot JAR điển hình (nếu không tùy biến archive name/classifier). Trong archive Spring Boot executable JAR của dòng ví dụ, tìm `BOOT-INF/classes/`, `BOOT-INF/lib/` và manifest có launcher phù hợp.

Để kiểm chứng chạy thật:

~~~bash
java -jar app/build/libs/app-0.1.0.jar --server.port=18085
~~~

Ở terminal thứ hai, sau khi app đã khởi động:

~~~bash
curl -i http://localhost:18085/ping
~~~

Kỳ vọng: HTTP status **200** và response body chính xác **`pong`**. Tên file và thông điệp startup phải lấy từ output build thật; nếu tên JAR khác, thay đúng path thay vì sửa ngược module name theo ví dụ. Dừng server bằng Ctrl+C và kiểm tra process đã kết thúc.

**Tổng hợp bằng chứng:** catalog resolve đúng version; convention áp dụng Java/Test/Boot plugin đúng module; core tạo library JAR; app test pass; app tạo executable JAR; binary chạy và phục vụ HTTP. Các bằng chứng này mới đủ minh họa giá trị của cơ chế chia sẻ.

## 9. Khi nào nên đưa một rule vào convention thay vì module?

Tập trung **quy tắc mang tính lặp và ổn định theo loại dự án**:

| Quy tắc | Nơi phù hợp | Lý do |
| --- | --- | --- |
| JDK toolchain chung | `acme.java-conventions` | Cả core/app cần version Java tương thích. |
| JUnit Platform và test logging/timeout chung | Java/testing convention | Module không tự ghi lại cùng quy tắc, nhưng vẫn chọn test dependency riêng. |
| Apply Spring Boot plugin | `acme.spring-boot-app` | Chỉ áp cho module thực thi có main class. |
| Boot plugin artifact version | Catalog + `build-logic/build.gradle` | Một version key, đúng plugin build classpath. |
| Starter Web/Test dependency | Catalog định nghĩa alias; app chọn dùng | Không phải mọi module đều là HTTP app. |
| Internal project dependency `:core` | `app/build.gradle` | Đây là quan hệ nghiệp vụ của module app. |
| Publish, coverage, formatting, static analysis | Convention riêng theo capability | Chỉ áp dụng khi module lựa chọn/chính sách yêu cầu. |
| Secret, URL DB, Spring profile prod | Runtime configuration/secret store | Không phải build convention hay TOML catalog. |
| Spring Boot BOM | Catalog cung cấp tọa độ; dùng `platform`/plugin để import | Version alignment phải tham gia dependency resolution. |

**Không xây convention “tất cả trong một”** gắn Spring Boot vào module library, tự thêm Web starter cho batch app, hoặc đặt credential vào plugin source. Một convention dễ kiểm tra nên đại diện cho một capability rõ ràng: Java base, Java library, Boot app, publishing, quality gates...

### 9.1. Cho phép override có kiểm soát

Convention có thể đặt default, còn module tùy biến trong phạm vi cho phép. Ví dụ nếu nhóm cần module riêng dùng thêm compiler arguments hoặc một test task khác, nên thêm rule có scope rõ, tránh sửa Java target rải rác không được phê duyệt. Khi một yêu cầu liên tục lặp ở nhiều module, nâng nó thành convention; nếu chỉ đúng cho một app, giữ ở module.

Ưu tiên Gradle lazy APIs (`tasks.named`, `configureEach`, Providers) để không thực thi task/configure sớm một cách không cần thiết. Nếu convention cần option cấu hình từ consumer, tạo **extension typed** thay vì đọc environment variables ở configuration time mà không khai báo input.

## 10. Cách thay đổi phiên bản và quản trị catalog

### 10.1. Cập nhật Spring Boot an toàn

Ví dụ muốn nâng Boot sang một phiên bản đã được nhóm phê duyệt:

1. Sửa đúng `spring-boot` trong `gradle/libs.versions.toml`.
2. Với cấu hình mẫu, alias plugin artifact và BOM tự trỏ về cùng version mới.
3. Kiểm tra tương thích **JDK/Gradle Wrapper** với plugin mới; không giả định phiên bản plugin mọi dòng cùng hỗ trợ Gradle 8.10.2.
4. Dùng `dependencyInsight`, `test`, `build` và smoke test trên executable JAR để phát hiện thay đổi behavior.
5. Khi có dependency bị override riêng, kiểm tra lại lý do và tính tương thích; catalog thay version không tự sửa các constraints do module khác áp.

**Không sửa chỉ `org.springframework.boot` plugin version mà quên BOM**, vì dễ sinh build plugin của một dòng Boot và runtime dependency của dòng khác. Một key chung giảm rủi ro nhưng không thay thế QA.

### 10.2. Plugin alias và plugin artifact là hai cách dùng, không được lẫn

Một project app nhỏ **không có convention** có thể dùng:

~~~groovy
plugins {
    id 'java'
    alias(libs.plugins.spring.boot)
}
~~~

Còn khi **đã có convention**, app chỉ cần:

~~~groovy
plugins {
    id 'acme.spring-boot-app'
}
~~~

Trong convention, Spring Boot được áp qua `id 'org.springframework.boot'` (không version), và version đến từ dependency `implementation(libs.spring.boot.gradle.plugin)` của build-logic. Đây là **hai đường giải quyết plugin khác nhau**. Đừng cố viết `alias(libs.plugins.spring.boot)` trong precompiled convention plugin, hoặc thêm `version '...'` ở đó.

### 10.3. Version catalogs với multi-build/monorepo

Một repository có nhiều included build (ví dụ `build-logic`, test fixtures, custom Gradle plugins) cần quyết định chia sẻ catalog thế nào:

- Với một repo, import từ **cùng file TOML** vào từng included build khi cần.
- Với nhiều repo, có thể publish catalog artifact và import theo version để tách vòng đời phát hành.
- Mỗi included build có **settings** và dependency/plugin classpath riêng; đừng giả định root `libs` tự xuất hiện trong included build.
- Plugin/dependency repository scopes có thể khác nhau giữa các build. Trường hợp tải dependency trong app được nhưng build-logic không tải được Boot plugin, kiểm tra repositories của **build-logic**, không chỉ root.
- Test các convention plugin có behavior phức tạp bằng Gradle TestKit/functional tests khi cần; chỉ so tên file TOML chưa chứng minh các task wiring chính xác.

### 10.4. Tương quan với dependency-management plugin

Trong Spring Boot Gradle, có hai lựa chọn quản lý dependency phiên bản:

- **Gradle native BOM**: `implementation(platform(libs.spring.boot.bom))` và tương tự cho test, như ví dụ này. Dễ quan sát dependency constraints bằng Gradle reports.
- **`io.spring.dependency-management` plugin**: khi cùng áp với Spring Boot plugin, có thể import Boot BOM và hỗ trợ cơ chế property-based customization. Đây là một plugin ngoài khác; nếu áp trong precompiled convention, cần đảm bảo dependency/plugin classpath phù hợp.

Không cần **cả hai** chỉ để làm một việc. Chọn một cơ chế theo nhu cầu hệ thống, tránh khai báo chồng nhau khiến khó xác định nguồn chọn version. Library không áp Boot plugin không tự được quản lý bởi Boot BOM; nếu library khai báo starter/versionless Boot dependencies, nó cũng cần nền tảng version phù hợp.

## 11. Lỗi phổ biến: dấu hiệu, nguồn gốc và cách sửa

| Hiện tượng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| `Plugin [id: 'acme.spring-boot-app'] was not found`. | Quên `includeBuild('build-logic')` trong plugin management, sai file name/plugin ID, build-logic compile fail. | Kiểm tra root settings, đường dẫn `src/main/groovy` và log build-logic. |
| `Plugin [id: 'org.springframework.boot'] was not found` khi biên dịch convention. | External plugin không có trong build-logic implementation classpath. | Thêm artifact `spring-boot-gradle-plugin` vào `build-logic/build.gradle`. |
| Không tìm được `libs` trong build-logic. | Catalog main build không tự chia sẻ sang included build. | Import `../gradle/libs.versions.toml` trong `build-logic/settings.gradle`. |
| `alias(libs.plugins.spring.boot)` lỗi trong precompiled `plugins` block. | Alias catalog không sẵn ở đó như ordinary build script. | Áp `id 'org.springframework.boot'` và dùng dependency trên classpath build-logic. |
| `libs.spring.boot.bom` không có accessor. | Tên alias sai, TOML syntax lỗi, catalog chưa import, Gradle sync chưa cập nhật. | Kiểm tra TOML và path, chạy lại Gradle sync/configuration. |
| Dependency starter không có version. | Chỉ thêm alias versionless mà quên BOM/platform hoặc dependency management. | Thêm `platform(libs.spring.boot.bom)` ở configuration phù hợp. |
| Version catalog ghi X nhưng Gradle chọn Y. | Constraints/BOM/transitive dependency conflict. | Dùng `dependencyInsight` để xem requested vs selected và nguồn constraint. |
| `:core:bootJar` xuất hiện hoặc đòi main class. | Boot plugin bị áp vào library qua convention quá rộng. | Giới hạn Boot plugin cho app convention, library dùng Java library. |
| `:app:bootJar` không có. | App chưa áp Boot plugin/Java plugin hoặc plugin bị tắt. | Kiểm tra `:app:tasks --all` và convention plugin IDs. |
| `:app:test` báo `NO-SOURCE` hoặc không thấy JUnit test. | Sai file path, `useJUnitPlatform` chưa áp, thiếu starter-test/launcher. | Kiểm tra `src/test/java`, convention task config và test runtime classpath. |
| Build thành công nhưng JAR thiếu dependency runtime. | Chọn plain JAR, build script tùy chỉnh artifact/scope. | Kiểm tra `bootJar`, manifest, `BOOT-INF/lib` và chạy `java -jar`. |
| Một update version gây lỗi build-logic. | Plugin mới không hỗ trợ Gradle/JDK đang dùng hoặc phụ thuộc repository. | So release compatibility và nâng toolchain/Wrapper có kiểm chứng. |
| Root `allprojects/subprojects` ghi đè các giá trị module. | Cấu hình cross-project chồng với convention. | Chuyển rule theo capability vào convention, bỏ config trùng. |
| Catalog dùng nhưng dependency không đồng bộ hoàn toàn. | Catalog không phải lockfile/strict policy. | Sử dụng BOM, constraints, locking/verification khi yêu cầu. |

### Phương pháp chẩn đoán theo lớp

1. **Plugin resolution**: kiểm tra root `pluginManagement`, `includeBuild` và file plugin ID.
2. **Build-logic compilation**: kiểm tra `build-logic/settings.gradle` import catalog, repositories, plugin artifact dependency.
3. **Module plugin wiring**: nhìn `:core:tasks --all` và `:app:tasks --all` để xem Java/Boot task được tạo ở module nào.
4. **Dependency resolution**: đọc `runtimeClasspath`, `testRuntimeClasspath` và `dependencyInsight`; phát hiện thiếu BOM hoặc version conflict.
5. **Compilation/test**: xem Java toolchain được Gradle chọn, report Test/JUnit, các task `NO-SOURCE`/`FAILED`.
6. **Packaging/runtime**: xác nhận `bootJar` và file executable, sau đó dùng `java -jar` cùng smoke test.

Chẩn đoán đúng lớp tránh “sửa” bằng cách copy lại cùng plugin/version vào mọi module, bởi hành động đó chỉ làm mất lợi ích của convention + catalog.

## 12. Bài thực hành và tiêu chí hoàn tất

### Bài thực hành A — chứng minh cấu hình dùng chung

1. Tạo cây file và hai modules như ví dụ.
2. Chạy `./gradlew projects`, `:core:tasks --all`, `:app:tasks --all`.
3. Chứng minh **chỉ app** có `bootJar`, cả core/app đều có Java/Test tasks.
4. Chạy `./gradlew :core:clean :app:clean :core:build :app:build`.
5. Kiểm tra report `ApplicationTest` (status 200, body `pong`), nội dung executable archive và smoke test app `GET /ping`.

### Bài thực hành B — thử một thay đổi quy ước

Đổi Java toolchain trong `acme.java-conventions.gradle` sang một version **đã được dự án hỗ trợ** và có JDK sẵn trên máy, sau đó xem thay đổi tác động tới cả core/app ở bước compile. Khôi phục Java 17 sau thử nghiệm. Đừng chọn JDK mới bất kỳ nếu Spring Boot plugin hoặc Gradle Wrapper trong bài không hỗ trợ.

### Bài thực hành C — thử một thay đổi danh mục version

Thay key `spring-boot` trong TOML sang một version được xác nhận tương thích, chạy Gradle configuration/build và so lại plugin/BOM versions từ reports. Khôi phục version mẫu sau bài tập. Nếu không thể resolve dependency vì môi trường offline/không có repository, ghi đúng blocker đó, không coi là lỗi của Java code.

### Checklist tự đánh giá

- [ ] Giải thích được **convention plugin quản lý hành vi build**, version catalog quản lý tọa độ/version/alias.
- [ ] Phân biệt main build, subproject và included build `build-logic`.
- [ ] Tạo được precompiled Groovy convention với ID trùng tên file.
- [ ] Áp Java 17 + JUnit Platform bằng convention cho core/app.
- [ ] Áp Boot plugin chỉ vào app và có `bootJar` đúng module.
- [ ] Đưa Boot plugin artifact vào **classpath build-logic** mà không trộn vào runtime app.
- [ ] Import cùng TOML từ `build-logic/settings.gradle`, hiểu vì sao cần import.
- [ ] Dùng BOM qua `platform(...)` và starter alias không có version đúng cách.
- [ ] Không dùng plugin alias trong `plugins` block của precompiled convention.
- [ ] Kiểm chứng requested/selected dependency version bằng `dependencyInsight`.
- [ ] Phân biệt catalog với BOM, constraints và dependency locking.
- [ ] Phân biệt `jar` library và executable `bootJar`, chạy được chính artifact đã đóng gói.
- [ ] Có report test và smoke test `GET /ping` cho app.
- [ ] Nêu được trường hợp phù hợp với convention riêng thay vì root `subprojects` config.

**Tiêu chí đạt bài:** người học trình bày được một bộ file hoàn chỉnh, chỉ ra rule Java/test/Boot nằm trong convention nào, chứng minh plugin/BOM lấy chung Boot version từ catalog, giải thích lựa chọn dependency của app, và cung cấp log/report cho cả build, test, packaged runtime. Nếu thiếu một trong những bằng chứng đó, nêu rõ phần chưa được kiểm chứng thay vì mặc định `BUILD SUCCESSFUL` bao phủ mọi thứ.

## Tài liệu tham khảo chính thức

- [Gradle — Convention Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_convention.html)
- [Gradle — Precompiled Script Plugins và Applying External Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html)
- [Gradle — Sharing Build Logic](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html)
- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html)
- [Gradle — Platforms and Maven BOM](https://docs.gradle.org/current/userguide/platforms.html)
- [Gradle — Catalogs and Platforms](https://docs.gradle.org/current/userguide/centralizing_catalog_platform.html)
- [Spring Boot 3.3 Gradle Plugin — Getting Started](https://docs.spring.io/spring-boot/3.3/gradle-plugin/getting-started.html)
- [Spring Boot 3.3 Gradle Plugin — Managing Dependencies](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html)

Các file ví dụ là cấu hình hướng dẫn. Các lệnh kiểm chứng phải được chạy trong project có Wrapper/JDK/dependency repositories thích hợp; không coi output dự kiến là log đo được nếu chưa thực hiện chúng.