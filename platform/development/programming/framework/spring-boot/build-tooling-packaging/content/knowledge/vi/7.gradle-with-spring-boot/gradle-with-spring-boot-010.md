# Phân biệt repositories cho plugin với repositories cho thư viện trong Gradle và Spring Boot

## 1. Mục tiêu và tình huống mở đầu

Trong một dự án Spring Boot sử dụng Gradle, thêm `mavenCentral()` vào `build.gradle` đôi khi **không giải quyết** lỗi `Plugin [id: 'org.springframework.boot'] was not found`. Ngược lại, cấu hình `gradlePluginPortal()` để tải được Spring Boot Gradle plugin **không có nghĩa** các thư viện `spring-boot-starter-web`, Jackson hay JDBC driver sẽ tự có repository.

Lý do: Gradle có các **phạm vi giải quyết artifact (resolution scopes)** khác nhau. Một số repository phục vụ **plugin dùng để chạy logic build**; những repository khác phục vụ **thư viện mà ứng dụng biên dịch, kiểm thử và chạy**.

Sau bài này, bạn có thể:

1. Phân biệt Gradle **plugin ID**, **plugin marker**, **plugin implementation** và **application library**.
2. Xác định `pluginManagement.repositories` trong settings dành cho `plugins { }`; `dependencyResolutionManagement.repositories` hoặc project `repositories` dành cho `dependencies { }`.
3. Nhận biết `buildscript.repositories` là cơ chế riêng của cách cấu hình plugin legacy.
4. Viết một cấu hình Spring Boot Gradle có thể chạy trên Linux/Windows và kiểm tra repository thực sự được sử dụng.
5. Sửa lỗi không tìm thấy plugin, không tìm thấy dependency, thiếu authentication, sai metadata hoặc không tương thích phiên bản mà không thêm tùy tiện repository ở mọi vị trí.

**Phiên bản trong ví dụ** là Spring Boot Gradle plugin `3.3.5`, Dependency Management plugin `1.1.6`, Java 17. Chúng được dùng để minh họa một cấu hình nhất quán, **không phải khuyến nghị phiên bản mới nhất**. Với dự án thật, theo Spring Boot, Gradle Wrapper và JDK mà dự án đã phê duyệt.

## 2. Hai loại artifact cốt lõi và một loại thường gây nhầm

| Đối tượng | Ví dụ | Dùng khi nào? |
| --- | --- | --- |
| **Gradle plugin** | `id 'org.springframework.boot' version '3.3.5'` | Khi Gradle cấu hình build, tạo task `bootJar`, `bootRun` và các integration cần thiết |
| **Plugin marker** | `org.springframework.boot:org.springframework.boot.gradle.plugin:3.3.5` | Giúp Gradle tìm implementation của plugin từ plugin ID và version |
| **Plugin implementation** | `org.springframework.boot:spring-boot-gradle-plugin:3.3.5` | JAR chứa mã plugin chạy trong môi trường build, có thể có dependency riêng |
| **Library dependency** | `org.springframework.boot:spring-boot-starter-web` | Được thêm vào classpath của mã ứng dụng/test và các dependency transitively kéo theo |

Một plugin và một library có thể cùng xuất bản dưới dạng artifact Maven, nhưng **không có cùng nhiệm vụ**. Cùng mang tiền tố `org.springframework.boot` không làm cho plugin trở thành Spring Boot starter.

**Plugin marker** thường dùng quy ước tọa độ `<plugin-id>:<plugin-id>.gradle.plugin:<version>`, rồi trỏ tới module implementation. Ví dụ marker cho `org.springframework.boot` trỏ tới JAR `spring-boot-gradle-plugin`. Một số plugin dùng cấu hình resolution khác nên không phải mọi plugin đều có marker có thể tìm thấy trong bất kỳ Maven repository nào.

Ngược lại, `implementation 'org.springframework.boot:spring-boot-starter-web'` chỉ yêu cầu thư viện của ứng dụng. Nó **không áp dụng** `org.springframework.boot` Gradle plugin. Nếu cần `bootJar` hoặc `bootRun`, bạn phải áp dụng plugin riêng.

## 3. Sơ đồ các repository scope

~~~text
Gradle Wrapper (gradlew / gradlew.bat)
    |
    v
settings.gradle hoặc settings.gradle.kts
    |
    +-- pluginManagement {
    |       repositories { ... }
    |   }                           -> Phân giải plugins { id(...) version ... }
    |                                -> Plugin marker + implementation + transitives
    |
    +-- dependencyResolutionManagement {
    |       repositories { ... }
    |   }                           -> implementation / runtimeOnly / testImplementation ...
    |                                -> Thư viện trực tiếp và transitive của project
    v
build.gradle hoặc build.gradle.kts
    |
    +-- plugins { ... }             -> Dùng plugin resolver từ settings
    +-- dependencies { ... }        -> Dùng dependency resolver của project/settings
    +-- repositories { ... }        -> Nguồn thư viện, nếu chính sách cho phép
    |
    +-- buildscript {
            repositories { ... }    -> Classpath của build script kiểu legacy
            dependencies { ... }
        }
~~~

Ba scope độc lập nhất cần nhớ:

- **Plugin DSL:** cấu hình ở `pluginManagement.repositories` của `settings.gradle[.kts]`. `plugins { }` trong project sử dụng cơ chế này.
- **Project dependencies:** cấu hình ở `dependencyResolutionManagement.repositories` trong settings hoặc `repositories` của project (theo chính sách `repositoriesMode`).
- **Legacy buildscript classpath:** cấu hình `buildscript.repositories` dành cho những artifact được khai báo bằng `buildscript.dependencies.classpath`.

Đừng nhầm các scope đó với `distributionUrl` của **Gradle Wrapper**, nguồn cấp **Java toolchain**, hoặc `publishing.repositories` là **đích xuất bản** artifact. Những cấu hình này có nhiệm vụ riêng.

## 4. Nơi tìm Gradle plugin: `pluginManagement.repositories`

Ví dụ build script Spring Boot dùng Plugins DSL:

~~~groovy
// build.gradle (trích đoạn)
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}
~~~

Gradle cần giải quyết hai plugin bên ngoài qua plugin ID/version. Nơi chỉ định repository cho yêu cầu này là **settings**:

~~~groovy
// settings.gradle - Groovy DSL
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
~~~

Kotlin DSL tương ứng:

~~~kotlin
// settings.gradle.kts
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
~~~

`gradlePluginPortal()` truy cập Gradle Plugin Portal, nơi xuất bản nhiều marker và plugin. `mavenCentral()` là kho Maven Central, có thể cần cho implementation hoặc phụ thuộc của plugin trong một số cách xuất bản. **Thêm Maven Central tại đây không tự cung cấp dependency repository cho ứng dụng.**

Nếu project **không khai báo** `pluginManagement.repositories`, Gradle Plugins DSL thường dùng Gradle Plugin Portal mặc định cho plugin bên ngoài. Nếu project **đã khai báo** danh sách repository custom, đừng giả định plugin portal vẫn được tự thêm vào sau danh sách ấy; cần ghi rõ những nguồn mà project/mirror thực sự yêu cầu.

Block `pluginManagement { }` phải nằm ở đầu file settings theo quy tắc Gradle (ngoại trừ `import` hợp lệ). Khi dùng Kotlin DSL, các `import` đặt trên đầu rồi tới block này. Những cấu hình khác đứng trước pluginManagement có thể khiến quá trình biên dịch/đọc settings thất bại.

**Lưu ý kiểm tra plugin:** `plugins { id 'java' }` hoạt động không chứng minh cấu hình repository plugin đúng: `java` là **Gradle core plugin**, không cần tải ngoài. Hãy thử plugin bên ngoài như `org.springframework.boot` để đánh giá kết nối thực tế.

## 5. Nơi tìm thư viện ứng dụng: repositories của project

Ví dụ phần thư viện trong `build.gradle`:

~~~groovy
// build.gradle (trích đoạn)
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    runtimeOnly 'com.h2database:h2'
}
~~~

Đây là **thư viện**, không phải plugin. Gradle dùng dependency repositories trong settings hoặc project để giải quyết phiên bản đã được yêu cầu/BOM quản lý cùng metadata và transitive artifacts.

### Cách A: khai báo tập trung trong settings

~~~groovy
// settings.gradle - sau pluginManagement
dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}
~~~

Cách này giúp một multi-project build dùng cùng danh sách nguồn tải thư viện. Maven Central có các Spring Boot starters phổ biến; hệ thống nội bộ có thể thay bằng mirror đáng tin cậy theo yêu cầu tổ chức.

Nếu cần **bắt buộc mọi project dùng repositories từ settings**, thêm:

~~~groovy
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}
~~~

Khi áp dụng `FAIL_ON_PROJECT_REPOS`, **không khai báo thêm** `repositories { mavenCentral() }` trong `build.gradle`: dù cùng URL, Gradle vẫn coi đó là project repository trái quy tắc. Một plugin tự thêm repository cũng có thể gây lỗi tương tự; cần tìm cấu hình gốc và xử lý đúng nơi.

Các chế độ `PREFER_SETTINGS` và `PREFER_PROJECT` có quy tắc ưu tiên khác; chọn theo chiến lược quản trị của dự án. Đừng xem `FAIL_ON_PROJECT_REPOS` là “lỗi Maven Central”: đó là lỗi **vi phạm chính sách repo**.

### Cách B: khai báo riêng ở `build.gradle`

~~~groovy
// build.gradle, nếu settings không cấm project repositories
repositories {
    mavenCentral()
}
~~~

Cách B hữu ích với Gradle build đơn giản hoặc cấu hình cũ. Không dùng đồng thời với `repositoriesMode.FAIL_ON_PROJECT_REPOS` ở settings.

**Kotlin DSL:** câu lệnh `repositories { mavenCentral() }` dùng được trong `build.gradle.kts`; trong `settings.gradle.kts`, `dependencyResolutionManagement { repositories { mavenCentral() } }` có cùng ý nghĩa. Nếu dùng `RepositoriesMode`, có thể import `org.gradle.api.initialization.resolve.RepositoriesMode` ở đầu Kotlin settings.

### BOM khác với repository

Trong Spring Boot, **BOM quản lý phiên bản** của nhiều starter/thư viện nhưng **không chỉ định nơi tải artifact**. Ví dụ `org.springframework.boot:spring-boot-dependencies` có thể cung cấp version của dependency, nhưng build vẫn phải có Maven Central/mirror để tải module thực.

Việc khai báo `spring-boot-starter-web` không có version riêng có thể đúng khi Spring Boot BOM được quản lý qua plugin phù hợp hoặc `platform()`. Tuy nhiên, BOM **không tự thêm** thư viện: phải có dependency trực tiếp hoặc transitive khiến module xuất hiện trên classpath.

## 6. Một ví dụ Spring Boot Gradle build được bằng Groovy DSL

Ví dụ này gồm các file đủ để kiểm tra plugin resolution và library resolution độc lập. Nó giả định đã có **Gradle Wrapper tương thích**, Internet hoặc mirror hợp lệ, cùng JDK 17 để chạy/biên dịch. Các số version được chọn nhất quán cho mục đích học. Nếu project của bạn đã có file build, chỉ ghép những phần cần thiết thay vì thay toàn bộ cấu hình.

### 6.1 `settings.gradle`

~~~groovy
import org.gradle.api.initialization.resolve.RepositoriesMode

pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'repository-scopes-demo'
~~~

Đây là nơi duy nhất định nghĩa plugin repositories và dependency repositories. `pluginManagement` có mặt trước các block cấu hình khác; `FAIL_ON_PROJECT_REPOS` giữ cho project modules không chèn thêm repositories ngoài chính sách.

### 6.2 `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot Gradle plugin tích hợp với `io.spring.dependency-management`: khi hai plugin cùng được áp dụng, BOM `spring-boot-dependencies` của phiên bản Spring Boot plugin được dùng để quản lý nhiều version thư viện. Vì vậy `spring-boot-starter` và `spring-boot-starter-test` không cần ghi version trong ví dụ.

**Không** thêm top-level `repositories { mavenCentral() }` trong file này, vì settings đã bật `FAIL_ON_PROJECT_REPOS`. Plugin Spring Boot **không thay** library starter, và library starter **không áp dụng** Gradle plugin.

### 6.3 `src/main/java/com/example/demo/DemoApplication.java`

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Đây là class Java hoàn chỉnh có tên file/package trùng khớp. Vì dependency chỉ là `spring-boot-starter`, ứng dụng có thể chạy xong rồi thoát thay vì mở HTTP port; điều đó **không phải lỗi tải dependency**.

### 6.4 Chạy bằng Gradle Wrapper

Linux/bash:

~~~bash
./gradlew --version
./gradlew help
./gradlew dependencies --configuration runtimeClasspath
./gradlew clean build
ls -lh build/libs/
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat help
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat clean build
Get-ChildItem .\build\libs\
~~~

- `--version`: ghi lại Gradle/JVM đang chạy, giúp phát hiện incompatibility.
- `help`: yêu cầu Gradle đọc settings/build script, giải quyết các plugin cần cấu hình. Lệnh này **chưa buộc** mọi library runtime phải được tải.
- `dependencies --configuration runtimeClasspath`: giải quyết/hiển thị đồ thị dependency ứng dụng. Cần plugin Java thích hợp tạo configuration `runtimeClasspath`.
- `clean build`: compile/test/package theo task graph; với Spring Boot plugin và main class hợp lệ có thể tạo executable JAR trong `build/libs/`.

Log và số task phụ thuộc môi trường; dấu hiệu kết thúc thành công thường là `BUILD SUCCESSFUL`, nhưng không có stdout cố định. Nếu chạy offline/có cache, một build thành công **không chứng minh** remote repo hiện đang truy cập được.

## 7. Ví dụ tương đương bằng Kotlin DSL

Chọn **một DSL** theo dự án, không đặt đồng thời cả `settings.gradle` và `settings.gradle.kts` trong cùng một root.

**File `settings.gradle.kts`:**

~~~kotlin
import org.gradle.api.initialization.resolve.RepositoriesMode

pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}

rootProject.name = "repository-scopes-demo"
~~~

**File `build.gradle.kts`:**

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.3.5"
    id("io.spring.dependency-management") version "1.1.6"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Dùng lại file Java ở mục 6. Dù viết Kotlin DSL, `plugins` và `dependencies` vẫn được giải quyết từ **hai loại repository** trong settings; DSL chỉ thay đổi cú pháp khai báo.

## 8. Plugin marker: vì sao có JAR rồi mà vẫn không tìm thấy plugin?

Khi gặp:

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.5'
}
~~~

Gradle Plugin DSL thường tìm:

~~~text
org.springframework.boot:org.springframework.boot.gradle.plugin:3.3.5
                    -> marker POM
                    -> org.springframework.boot:spring-boot-gradle-plugin:3.3.5
                    -> plugin implementation + transitive dependencies
~~~

Một Maven mirror nội bộ có thể đã lưu `spring-boot-gradle-plugin` nhưng **thiếu plugin marker**. Kết quả là lỗi `Plugin ... was not found` khi yêu cầu qua ID, dù implementation có thể tải được nếu biết chính xác tọa độ.

Cách xử lý đúng là:

1. Mirror/publish **đủ marker, implementation và các dependency liên quan** vào plugin repository.
2. Cấu hình `gradlePluginPortal()` hoặc repository khác chứa marker theo chính sách của tổ chức.
3. Trường hợp plugin implementation không có marker, dùng `pluginManagement.resolutionStrategy` để ánh xạ plugin ID sang module cụ thể; chỉ dùng khi biết rõ implementation/version.

Ví dụ **trích đoạn độc lập** minh họa phương án 3 cho Spring Boot plugin, khi Maven Central là nguồn implementation được cấp phép:

~~~groovy
// settings.gradle - thay cho pluginManagement thông thường khi thật sự cần
pluginManagement {
    resolutionStrategy {
        eachPlugin {
            if (requested.id.id == 'org.springframework.boot') {
                useModule(
                    'org.springframework.boot:spring-boot-gradle-plugin:' +
                    requested.version
                )
            }
        }
    }
    repositories {
        mavenCentral()
    }
}
~~~

Nó giả định yêu cầu plugin có khai báo version. `useModule` chuyển sang implementation module thay vì marker cho ID đã chọn; các plugin khác vẫn cần repository/marker thích hợp. Đây **không phải thiết lập bắt buộc** cho project Spring Boot bình thường có thể truy cập Plugin Portal.

## 9. Plugin DSL và `buildscript.repositories` kiểu legacy

Trước `plugins { }` hiện đại, nhiều dự án sử dụng:

~~~groovy
// build.gradle - trích đoạn minh họa cách legacy
buildscript {
    repositories {
        mavenCentral()
    }
    dependencies {
        classpath 'org.springframework.boot:spring-boot-gradle-plugin:3.3.5'
    }
}

apply plugin: 'java'
apply plugin: 'org.springframework.boot'
~~~

Đoạn này giải quyết trực tiếp implementation artifact trong `buildscript.classpath` bằng **`buildscript.repositories`**, rồi áp dụng plugin bằng `apply plugin`. **Nó không yêu cầu plugin marker theo cơ chế Plugins DSL.**

Ví dụ legacy trên chỉ minh họa resolution plugin; nếu muốn build ứng dụng đầy đủ, vẫn cần dependency repositories và dependency management/BOM như project thật yêu cầu. Không thêm đồng thời hai cách apply cùng một plugin chỉ để thử lỗi.

So sánh:

| Cơ chế | Khai báo plugin | Repository cấp artifact plugin |
| --- | --- | --- |
| Plugins DSL | `plugins { id("org.springframework.boot") version "..." }` | `pluginManagement.repositories` ở settings |
| Legacy `buildscript` | `buildscript.dependencies.classpath(...)` rồi `apply plugin` | `buildscript.repositories` ở build script |
| Library của ứng dụng | `dependencies { implementation(...) }` | `dependencyResolutionManagement.repositories` hoặc `repositories` của project |

Vì vậy, nếu lỗi nói tới configuration `classpath`, phải xem **ngữ cảnh classpath**: nó là legacy buildscript classpath hay một phần khác của build/plugin? Nếu lỗi nói `Plugin [id...]`, bắt đầu ở plugin resolver. Nếu lỗi ở `runtimeClasspath` hay `compileClasspath`, xem library repository và version.

## 10. Tại sao `repositoriesMode` khiến một cấu hình nhìn đúng lại fail?

Khi thiết kế multi-module build, nhiều nhóm đặt dependency repositories **tập trung ở settings**:

~~~groovy
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}
~~~

Trong khi module con vẫn có:

~~~groovy
// app/build.gradle - sai khi settings cấm project repository
repositories {
    mavenCentral()
}
~~~

Gradle có thể báo build **không cho phép thêm project repositories** dù cùng một tên `mavenCentral()`. Lỗi ở đây là vi phạm policy, không phải DNS hay artifact không tồn tại. Cách sửa là **đưa nguồn cần thiết vào settings**, loại khai báo ở project và giải quyết plugin nào tự chèn repository nếu có.

Các chế độ khác của Gradle cho phép quản lý khác nhau:

- `PREFER_SETTINGS`: ưu tiên repository khai báo ở settings; project repositories không điều khiển resolution theo cùng cách.
- `PREFER_PROJECT`: project repositories được ưu tiên khi chúng được khai báo.
- `FAIL_ON_PROJECT_REPOS`: bảo đảm chính sách tập trung bằng cách gây lỗi khi project thêm repository theo quy tắc này.

Chọn chế độ dựa trên nhu cầu build reproducibility và quản trị nguồn tải. **Không dùng `repositoriesMode` để thay thế `pluginManagement`**; plugin resolver là một luồng khác.

## 11. Repository cho Wrapper, Java toolchain, publishing và version catalog

### Gradle Wrapper

`gradle/wrapper/gradle-wrapper.properties` dùng `distributionUrl` để tải **bản phân phối Gradle**, ví dụ cấu hình bởi lệnh `wrapper`. Nếu Wrapper báo không thể tải Gradle distribution, sửa `dependencyResolutionManagement.repositories` không giải quyết được URL distribution; cần kiểm tra network, proxy, CA hoặc mirror của Gradle.

### Java toolchain

Khi `java.toolchain.languageVersion` yêu cầu JDK chưa cài, Gradle có cơ chế dò tìm hoặc **provisioning JDK** theo resolver được cấu hình. Maven Central dành cho thư viện ứng dụng **không tự cung cấp** JDK. Lỗi `No matching Java installation` thuộc lớp toolchain/JDK, không phải thiếu `spring-boot-starter`.

### Publishing repositories

`publishing.repositories` của plugin `maven-publish` chỉ **nơi đẩy artifact** khi thực hiện publish; không phải nơi tải plugin hay runtime library. Nếu cần đăng artifact, xác định xuất bản JAR nào và dùng cơ chế credentials phù hợp, không lấy cấu hình publish làm repository resolution.

### Version catalog

Trong `gradle/libs.versions.toml`, nhóm có thể đặt alias cho plugin và library:

~~~toml
[versions]
boot = "3.3.5"

[plugins]
boot = { id = "org.springframework.boot", version.ref = "boot" }

[libraries]
boot-starter = { module = "org.springframework.boot:spring-boot-starter" }
~~~

Khi `build.gradle.kts` gọi `alias(libs.plugins.boot)`, resolver vẫn dùng **`pluginManagement.repositories`**. Khi gọi `implementation(libs.boot.starter)`, resolver vẫn dùng **dependency repositories**. Catalog quản lý **tọa độ/version**, không tự chuyển repository scope. Ví dụ library không ghi version vì giả định project đã có Spring Boot BOM/dependency management.

## 12. Mirror doanh nghiệp, credentials và cách quản lý nguồn tải

Với công ty có Artifactory/Nexus hoặc mirror nội bộ, hai đường tải thường khác nhau:

- **Plugin mirror:** cần đủ plugin marker, implementation và transitive dependencies. Cấu hình ở `pluginManagement.repositories`.
- **Library mirror:** cần POM/Gradle module metadata/JAR và transitive dependencies của ứng dụng. Cấu hình ở `dependencyResolutionManagement.repositories` hoặc project repositories.
- **Credentials:** lấy từ Gradle properties được cấp an toàn, biến môi trường hoặc CI secret store. Không commit username/password/token vào URL, `settings.gradle` hoặc `build.gradle`.
- **Content filters:** khi lọc group/module, nhớ rằng marker và implementation có thể khác group hoặc tọa độ. Lọc quá hẹp có thể làm plugin thất bại ngay cả khi implementation JAR vẫn có trong kho.
- **Gradle init scripts:** máy và CI có thể được áp dụng cấu hình repository ngoài source; điều này giải thích vì sao cùng file Gradle đôi khi local chạy được, CI sạch lại fail.

Không mặc định repository **thứ hai** sẽ cứu được mọi lỗi repository thứ nhất. Khi Gradle đã nhận metadata của module từ một repository nhưng tải artifact thất bại, hoặc một exclusive content rule ràng buộc module vào nguồn cụ thể, resolution không đơn giản chỉ “thử mọi URL còn lại”. Kiểm tra cụ thể log và chính sách mirror.

Đối với CI, ưu tiên project có **cấu hình nguồn tải khai báo rõ**, kiểm tra được và không yêu cầu người dùng phải tự thêm một repository ngầm vào IDE. Tránh tải dependency/plugin từ kho không tin cậy chỉ vì một URL cho kết quả nhanh hơn.

## 13. Chẩn đoán theo loại lỗi, không đoán

Trên Linux/bash, từ thư mục gốc dự án:

~~~bash
./gradlew --version
./gradlew help --info
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency org.springframework.boot:spring-boot-starter --configuration runtimeClasspath
./gradlew clean build
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat help --info
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency org.springframework.boot:spring-boot-starter --configuration runtimeClasspath
.\gradlew.bat clean build
~~~

**Giải thích đúng phạm vi từng lệnh:**

- `--version` ghi lại Gradle version và JVM thực thi; quan trọng để nhận ra Gradle/Java/plugin incompatibility.
- `help --info` đọc và cấu hình project, thường buộc giải quyết plugin cần thiết trước khi chạy task; nó không bảo đảm runtime dependency đã tải.
- `dependencies --configuration runtimeClasspath` cho biết graph của ứng dụng và làm rõ dependency nào bị thiếu hoặc phiên bản được chọn.
- `dependencyInsight` truy tìm đường dẫn và nguyên nhân version của một module, giúp phân biệt lỗi repository với conflict/constraint.
- `clean build` kiểm tra toàn bộ luồng compilation, test, packaging theo cấu hình.

Nếu multi-project build, có thể cần gọi `:app:dependencies` hoặc `:app:dependencyInsight` để kiểm tra đúng module. Nếu dự án chưa áp dụng Java/JVM plugin tương ứng thì `runtimeClasspath` có thể không tồn tại; đó là vấn đề configuration, không phải lỗi repository.

### Bảng lỗi thường gặp

| Triệu chứng | Kiểm tra trước | Cách xử lý |
| --- | --- | --- |
| `Plugin [id: 'org.springframework.boot', version: '...'] was not found` | `pluginManagement.repositories`, plugin ID, version, marker | Cấp Plugin Portal/mirror đúng, xác nhận marker và implementation có thật |
| `Could not find org.springframework.boot:spring-boot-starter-...` | Dependency repository và BOM/phiên bản | Cấp Maven Central/mirror cho dependencies; xác minh module có phiên bản hợp lệ |
| `Could not resolve all files for configuration ':classpath'` | `buildscript.classpath` hoặc plugin classpath thực tế | Xem lỗi đầy đủ, xác định cơ chế plugin legacy hay Plugins DSL |
| `Build was configured to prefer settings repositories` hoặc lỗi cấm project repo | `repositoriesMode` | Đưa repo về settings/loại project repository trái policy |
| `401 Unauthorized` hoặc `403 Forbidden` | Xác thực, quyền repo và CI secrets | Kiểm tra credentials/permissions, tránh lộ secret vào log |
| Timeout / TLS / DNS với Plugin Portal | Network tới plugin repo, proxy, certificate | Sửa network/mirror tương ứng, không thêm thư viện tùy tiện |
| Plugin marker tìm được nhưng implementation/dependency vẫn fail | Mirror thiếu module hoặc content filter chặn | Bổ sung chain artifact của plugin trong plugin repositories |
| `No matching variant of ...` | Gradle/JVM/plugin version và metadata variant | Đọc Gradle API/JVM attributes trong lỗi; đây có thể là incompatibility |
| `No matching Java installation` | Java toolchain/JDK | Cài/cấp resolver JDK phù hợp; library repo không tự giải quyết |
| Wrapper không tải distribution | `distributionUrl` và network | Kiểm tra Gradle distribution URL/proxy, không chỉ Maven Central |

Một build có thể “pass local” nhờ cache nhưng “fail CI” khi CI phải tải artifact mới. Để kiểm tra hành vi online, có thể dùng `--refresh-dependencies` khi có lý do và mạng sẵn sàng; nó yêu cầu Gradle kiểm tra lại dependency metadata/cache. `--offline` chỉ dùng cache đã lưu, vì vậy **không chứng minh** repository remote đang truy cập được. Không xóa toàn bộ cache hoặc bật log chi tiết chứa credentials như bước đầu tiên.

## 14. Thí nghiệm tách biệt plugin repo và library repo

Dùng project mẫu ở mục 6 trên một branch thử nghiệm; ghi lại từng kết quả và khôi phục sau bài học. Nếu dữ liệu đã cache, kiểm tra trên CI sạch hoặc môi trường được kiểm soát để tránh kết luận sai.

**Trường hợp A — có plugin repository, thiếu library repository.** Giữ `pluginManagement.repositories { gradlePluginPortal() }` nhưng loại các dependency repositories khỏi bản thử nghiệm. Trong môi trường chưa có cache, Gradle có thể cấu hình plugin và `help` thành công, rồi fail khi `compileJava` hoặc task cần starter cố giải quyết runtime/compile dependencies. Bài học: tải được plugin **không có nghĩa** tải được library.

**Trường hợp B — có library repository, không giải quyết được plugin.** Giữ `dependencyResolutionManagement.repositories { mavenCentral() }` nhưng cấu hình plugin resolver thiếu nguồn marker thực sự; lúc này build có thể fail **trước khi** tới bước resolve starter. Chú ý: chỉ xóa `pluginManagement` thường **không tạo lỗi**, vì Gradle có Plugin Portal mặc định. Muốn thí nghiệm có ý nghĩa, phải biết nguồn plugin resolver thực sự truy cập trong môi trường thử nghiệm.

**Trường hợp C — có cả hai repository đúng scope.** Khôi phục `pluginManagement.repositories { gradlePluginPortal(); mavenCentral() }` và `dependencyResolutionManagement.repositories { mavenCentral() }`. Nếu bật `FAIL_ON_PROJECT_REPOS`, bảo đảm các build script không tự thêm project repos. Sau đó chạy `help`, `dependencies`, `clean build` để kiểm tra theo thứ tự **plugin → library → build/test**.

Với mọi thí nghiệm, đọc lỗi thực tế: artifact không tồn tại, network bị chặn, authentication, thiếu marker, sai Java/Gradle variant hoặc configuration typo đều có thể tạo hiện tượng tương tự.

## 15. Hiểu lầm phổ biến và cách ghi nhớ

| Nhận định sai | Cách hiểu chính xác |
| --- | --- |
| “Có `mavenCentral()` ở `build.gradle` là tìm được mọi Gradle plugin.” | Plugins DSL dùng `pluginManagement.repositories` trong settings. |
| “Chỉ cần `gradlePluginPortal()` là starter và driver đều resolve.” | Starter/driver cần dependency repositories, thường là Maven Central/mirror. |
| “`buildscript.repositories` và `pluginManagement.repositories` giống nhau.” | Legacy classpath và Plugins DSL có đường resolution khác nhau. |
| “Plugin `java` resolve được chứng minh Plugin Portal ổn.” | `java` là core plugin của Gradle, không tải ngoài. |
| “`FAIL_ON_PROJECT_REPOS` gây lỗi thì tắt nó là cách sửa.” | Tìm project/plugin nào thêm repo và chuẩn hóa theo chính sách settings trước. |
| “BOM cung cấp cả repository.” | BOM quản lý dependency **versions**; repository tìm **artifacts**. |
| “Version catalog tự chỉ định nơi tải plugin và library.” | Catalog chứa ID/module/version; repository scope vẫn độc lập. |
| “`gradlew help` thành công nghĩa `gradlew build` chắc chắn thành công.” | Task help chưa xác thực mọi compile/runtime/test dependency. |
| “Lỗi không tải JDK hoặc Gradle Wrapper do Maven Central thiếu starter.” | JDK provisioning và Gradle distribution là luồng tải riêng. |
| “Bất kỳ lỗi `No matching variant` nào cũng do repo.” | Nhiều trường hợp là tương thích JDK/Gradle/plugin API hoặc metadata variant. |

## 16. Checklist ứng dụng vào project thật

- [ ] Biết dự án dùng `settings.gradle` hay `settings.gradle.kts`, `build.gradle` hay `build.gradle.kts` và phiên bản Gradle Wrapper.
- [ ] Có `pluginManagement.repositories` phù hợp với các plugin ngoài như Spring Boot Gradle plugin và dependency management plugin.
- [ ] Có dependency repositories rõ ràng trong settings **hoặc** project; kiểm tra `repositoriesMode` trước khi thêm repository mới.
- [ ] Kiểm tra project có legacy `buildscript { }` hay không để không sửa nhầm scope.
- [ ] Nếu dùng mirror doanh nghiệp, xác minh plugin marker, implementation, transitive dependencies và thư viện ứng dụng được mirror đầy đủ.
- [ ] Phân biệt lỗi plugin resolution, library resolution, network/auth, Wrapper distribution và Java toolchain.
- [ ] Xác nhận Gradle có thể cấu hình plugin bằng `help`, phân giải library bằng `dependencies`/`dependencyInsight`, và build bằng `clean build`.
- [ ] So sánh trên CI với phiên bản Gradle/JDK tương thích, không xem cache của máy cá nhân là bằng chứng kho remote hoạt động.
- [ ] Không commit secret, không thêm repository không tin cậy và không bỏ chính sách quản trị để che một lỗi cụ thể.

Hoàn thành bài khi bạn có thể nhìn thấy `Plugin ... was not found` và `Could not find ...starter...`, **giải thích ngay vì sao chúng thuộc hai phạm vi repository khác nhau**, rồi xác định đúng file/cấu hình cần sửa trong một Spring Boot Gradle project.

## Tài liệu chính thức

- [Gradle – Working with Plugins](https://docs.gradle.org/current/userguide/plugins.html)
- [Gradle – Plugin Management](https://docs.gradle.org/current/userguide/plugins_intermediate.html#sec:plugin_management)
- [Gradle – Declaring Repositories](https://docs.gradle.org/current/userguide/declaring_repositories.html)
- [Gradle – Centralizing Repository Declarations](https://docs.gradle.org/current/userguide/centralizing_repositories.html)
- [Gradle – Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Gradle – Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [Spring Boot – Gradle Plugin: Getting Started](https://docs.spring.io/spring-boot/gradle-plugin/getting-started.html)
- [Spring Boot – Gradle Plugin: Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)
