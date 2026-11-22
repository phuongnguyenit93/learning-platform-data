# Chia sẻ phiên bản, cấu hình và quy ước một cách có kiểm soát

Khi một ứng dụng Java phát triển thành nhiều mô-đun, mỗi mô-đun thường có build script, dependency và nhiệm vụ riêng. Nếu mọi mô-đun tự chọn phiên bản thư viện, tự khai báo repository và tự cấu hình compiler, test hoặc đóng gói, build sẽ nhanh chóng trở nên khó quản lý. Ngược lại, nếu dồn mọi thứ vào một cấu hình toàn cục, các mô-đun có thể nhận những dependency hoặc quy tắc mà chúng không cần.

Mục tiêu của build nhiều mô-đun là **chia sẻ đúng những chính sách cần thống nhất, đồng thời giữ trách nhiệm của từng mô-đun rõ ràng**. Trong Gradle, có thể dùng Settings để quản lý cấu trúc build và repository, Version Catalog hoặc platform để quản lý version, convention plugin để đóng gói quy ước, và project dependency để thể hiện quan hệ giữa các mô-đun. Maven có parent POM, `dependencyManagement`, `pluginManagement`, properties và BOM để tổ chức cấu hình tương tự.

Không có một cơ chế duy nhất phù hợp cho mọi loại cấu hình. Cần xác định thông tin nào thuộc toàn build, thông tin nào thuộc một nhóm mô-đun và thông tin nào chỉ thuộc một mô-đun cụ thể. Bài học này trình bày cách xác định ranh giới đó và áp dụng nó trong dự án nhiều mô-đun.

## 1. Vì sao cần chia sẻ cấu hình có kiểm soát?

Giả sử một hệ thống có các mô-đun:

```text
order-platform/
├── settings.gradle.kts
├── build.gradle.kts
├── api/
├── application/
├── domain/
├── persistence/
└── reporting/
```

Các mô-đun có thể cần những quy ước chung:

- Cùng một phiên bản Java toolchain.
- Cùng nguồn repository dependency.
- Cùng phiên bản JUnit hoặc thư viện logging.
- Cùng cách chạy test và tạo báo cáo.
- Cùng quy tắc kiểm tra chất lượng và định dạng mã.
- Cùng quy ước đặt `group`, `version` và metadata artifact.

Nhưng không phải mô-đun nào cũng cần mọi thư viện. `domain` có thể chỉ cần Java Library plugin và một số thư viện nhỏ; `application` cần plugin chạy ứng dụng; `persistence` cần driver database; `reporting` có thể cần thư viện xuất báo cáo. Nếu root project thêm mọi dependency vào tất cả mô-đun, build sẽ tạo classpath thừa và làm ranh giới module mờ đi.

Chia sẻ có kiểm soát giải quyết hai vấn đề đồng thời:

1. **Tính nhất quán:** các mô-đun tuân theo cùng chính sách về version, toolchain, repository và chất lượng build.
2. **Tính độc lập:** mỗi mô-đun chỉ áp dụng plugin, dependency và task phù hợp với vai trò của nó.

## 2. Phân loại phạm vi cấu hình trước khi chia sẻ

Trước khi quyết định đặt cấu hình ở đâu, hãy phân loại nó theo phạm vi:

| Phạm vi | Ví dụ | Nơi thường phù hợp trong Gradle |
|---|---|---|
| Toàn build | Tên root project, danh sách project, plugin repository, dependency repository, quy tắc repository | `settings.gradle(.kts)` |
| Toàn tổ chức hoặc nhiều repository | Danh mục version chuẩn, convention plugin dùng chung, platform được phát hành | Version Catalog, plugin build logic hoặc artifact platform riêng |
| Nhóm mô-đun cùng vai trò | Toolchain, test framework, kiểm tra chất lượng cho các Java library | Convention plugin |
| Một mô-đun | Dependency riêng, task riêng, cấu hình database adapter | `build.gradle(.kts)` của mô-đun |
| Một task | File input/output, tùy chọn thực thi, cache và incremental behavior | Task type hoặc task configuration tương ứng |

Ví dụ, repository Maven Central thường là chính sách của toàn build. Phiên bản Jackson có thể được quản lý tập trung, nhưng chỉ mô-đun thực sự sử dụng Jackson mới khai báo nó. Java library convention có thể đặt toolchain và cấu hình test chung cho nhóm thư viện. Một task sinh mã chỉ thuộc mô-đun cần sinh mã đó.

Đặt cấu hình đúng phạm vi giúp người đọc hiểu vì sao một mô-đun nhận được một plugin hoặc dependency. Cấu hình toàn cục nên dành cho những điều thực sự áp dụng cho toàn build; cấu hình theo vai trò nên được đóng gói thành quy ước có tên.

## 3. Settings quản lý cấu trúc và chính sách toàn build

### 3.1. Khai báo các mô-đun một lần

Trong Gradle, `settings.gradle` hoặc `settings.gradle.kts` xác định build gồm những project nào:

```kotlin
// settings.gradle.kts
rootProject.name = "order-platform"

include(
    "api",
    "application",
    "domain",
    "persistence",
    "reporting"
)
```

Mỗi project có một path riêng như `:domain` hoặc `:persistence`. Gradle dùng path này để nhận diện project trong build. Việc include một project không tự động áp dụng Java plugin, thêm dependency hay làm cho project khác phụ thuộc vào nó. Các quan hệ đó được khai báo riêng.

Nếu thư mục vật lý khác path project, có thể ánh xạ rõ ràng:

```kotlin
include("application")
project(":application").projectDir = file("apps/order-service")
```

Project path vẫn là `:application`, dù nội dung nằm trong `apps/order-service`.

### 3.2. Quản lý repository dependency ở Settings

Nếu mọi mô-đun đều dùng cùng repository, có thể khai báo ở cấp build:

```kotlin
// settings.gradle.kts
dependencyResolutionManagement {
    repositories {
        mavenCentral()
        maven {
            url = uri("https://repo.example.com/releases")
        }
    }
}
```

Các project trong build có thể dùng repository đã được quản lý tại Settings. Để ngăn mô-đun tự thêm repository ngoài chính sách, có thể chọn chế độ:

```kotlin
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}
```

Với `FAIL_ON_PROJECT_REPOS`, build sẽ báo lỗi nếu một project tự khai báo repository. Đây là cách thực thi chính sách tập trung rõ ràng. Nếu tổ chức cần cho phép project bổ sung repository riêng, hãy chọn `repositoriesMode` phù hợp và quy định trường hợp nào được phép.

Không nên thêm repository nội bộ vào mọi mô-đun chỉ để tránh lỗi phân giải. Hãy xác định repository nào được tin cậy, repository nào chứa release/snapshot và chính sách xác thực tương ứng. Credentials nên được lấy từ môi trường hoặc secret store; không commit mật khẩu hoặc token vào build script.

### 3.3. Phân biệt repository plugin và repository dependency

Gradle có hai nhóm repository khác nhau:

```kotlin
// settings.gradle.kts
pluginManagement {
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
```

`pluginManagement.repositories` được dùng để phân giải plugin được yêu cầu trong khối `plugins`. `dependencyResolutionManagement.repositories` được dùng để phân giải thư viện của project. Cấu hình một nhóm không tự động thay thế nhóm còn lại.

### 3.4. Đặt quy tắc version plugin ở cấp build

Settings cũng có thể cung cấp version mặc định cho plugin:

```kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }

    plugins {
        id("org.springframework.boot") version "3.3.5"
        id("com.diffplug.spotless") version "6.25.0"
    }
}
```

Các mô-đun có thể yêu cầu plugin theo ID mà không lặp version:

```kotlin
plugins {
    id("org.springframework.boot")
}
```

Version mặc định trong `pluginManagement.plugins` được áp dụng cho plugin request không chỉ định version riêng. Cách này hữu ích khi nhiều mô-đun cần cùng phiên bản plugin. Với plugin chỉ dùng ở một mô-đun, vẫn có thể cân nhắc khai báo riêng nếu điều đó làm cấu hình dễ hiểu hơn.

## 4. Tập trung khai báo version bằng Version Catalog

### 4.1. Một nguồn tên và version chung

Gradle Version Catalog mặc định nằm ở `gradle/libs.versions.toml`. Các project trong cùng build có thể dùng catalog `libs` để tham chiếu dependency và plugin alias.

Ví dụ:

```toml
[versions]
jackson = "2.17.2"
slf4j = "2.0.13"
junit = "5.10.3"
spring-boot = "3.3.5"

[libraries]
jackson-databind = { module = "com.fasterxml.jackson.core:jackson-databind", version.ref = "jackson" }
slf4j-api = { module = "org.slf4j:slf4j-api", version.ref = "slf4j" }
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "spring-boot" }
```

Mô-đun sử dụng alias:

```kotlin
dependencies {
    implementation(libs.jackson.databind)
    implementation(libs.slf4j.api)
    testImplementation(libs.junit.jupiter)
}
```

Khi cần nâng Jackson, người bảo trì thay version trong catalog. Các mô-đun tham chiếu alias sẽ nhận định nghĩa mới mà không phải sửa tọa độ ở từng build script.

### 4.2. Catalog không tự thêm dependency cho mọi project

Catalog chỉ định nghĩa alias và version. Nó không tự thêm dependency vào classpath của mọi mô-đun. Mỗi mô-đun vẫn khai báo những thư viện nó thực sự cần:

```kotlin
// domain/build.gradle.kts
dependencies {
    implementation(libs.slf4j.api)
}
```

```kotlin
// reporting/build.gradle.kts
dependencies {
    implementation(libs.jackson.databind)
}
```

Nếu `domain` không dùng Jackson, không cần thêm `libs.jackson.databind` vào module đó chỉ vì alias đã tồn tại. Cách làm này giữ dependency graph nhỏ và thể hiện đúng trách nhiệm của từng mô-đun.

### 4.3. Tập trung plugin alias

Catalog có thể khai báo plugin:

```toml
[versions]
spring-boot = "3.3.5"

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "spring-boot" }
```

Ở root project, có thể khai báo plugin nhưng không áp dụng:

```kotlin
// build.gradle.kts ở root
plugins {
    alias(libs.plugins.spring.boot) apply false
}
```

Mô-đun cần plugin sẽ áp dụng alias:

```kotlin
// application/build.gradle.kts
plugins {
    alias(libs.plugins.spring.boot)
}
```

`apply false` giúp root quản lý yêu cầu plugin và version mà không áp dụng plugin đó lên root project. Các mô-đun con có thể dùng cùng alias. Cần chọn một cơ chế quản lý version plugin nhất quán giữa Version Catalog, `pluginManagement` và root `plugins` để tránh nhiều nguồn khai báo khó theo dõi.

### 4.4. Catalog và platform/BOM có vai trò khác nhau

Version Catalog giảm lặp tọa độ và version trong build script. Platform hoặc BOM căn chỉnh version của một nhóm thư viện có quan hệ tương thích.

Ví dụ:

```kotlin
dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:3.3.5"))
    implementation("org.springframework.boot:spring-boot-starter-web")
}
```

Platform cung cấp version constraints; project vẫn khai báo starter mà nó thực sự sử dụng. Có thể khai báo tọa độ BOM trong catalog rồi dùng `platform(libs.spring.boot.bom)` để tập trung version BOM. Catalog và platform phối hợp với nhau nhưng không thay thế nhau.

Khi nhiều mô-đun cần dùng cùng bộ thư viện Spring, một mô-đun platform riêng hoặc BOM do framework phát hành giúp giữ version đồng bộ. Không nên cố giải quyết mọi xung đột bằng cách ghi cùng một version vào nhiều alias độc lập mà không có chính sách căn chỉnh.

## 5. Convention plugin: chia sẻ cách cấu hình theo vai trò

### 5.1. Vì sao không chỉ dùng root build script?

Một số cấu hình lặp lại không chỉ là version. Nhiều Java library có thể cần cùng toolchain, test framework, compiler options và kiểm tra chất lượng. Nếu copy cùng một khối vào từng `build.gradle`, mỗi thay đổi sẽ phải sửa nhiều file.

Có thể viết cấu hình trong `subprojects { ... }`, nhưng cách đó dễ áp dụng nhầm cho những mô-đun không cùng vai trò. Ví dụ, một project chỉ dùng để quản lý version hoặc một project đóng gói ứng dụng có thể không cần toàn bộ cấu hình Java library.

Convention plugin đóng gói một bộ quy tắc có tên và chỉ được áp dụng ở mô-đun cần nó. Tên plugin thể hiện vai trò như `company.java-library` hoặc `company.spring-service`.

### 5.2. Cấu trúc build logic

Một cách tổ chức phổ biến là đặt convention plugin trong included build tên `build-logic`:

```text
order-platform/
├── settings.gradle.kts
├── build.gradle.kts
├── gradle/
│   └── libs.versions.toml
├── build-logic/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/main/kotlin/
│       └── company.java-library.gradle.kts
├── domain/
├── persistence/
└── application/
```

Trong Settings chính:

```kotlin
// settings.gradle.kts
pluginManagement {
    includeBuild("build-logic")
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

rootProject.name = "order-platform"
include("domain", "persistence", "application")
```

`includeBuild("build-logic")` đưa build chứa plugin vào quá trình phân giải plugin. Build logic được biên dịch như một build riêng và cung cấp plugin cho build chính.

### 5.3. Định nghĩa convention plugin

`build-logic/build.gradle.kts` có thể dùng Kotlin DSL plugin để biên dịch build logic:

```kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}

gradlePlugin {
    plugins {
        register("javaLibraryConventions") {
            id = "company.java-library"
            implementationClass = "com.example.build.JavaLibraryConventionPlugin"
        }
    }
}
```

Implementation plugin có thể cấu hình Java library:

```kotlin
package com.example.build

import org.gradle.api.Plugin
import org.gradle.api.Project
import org.gradle.api.plugins.JavaLibraryPlugin
import org.gradle.api.plugins.JavaPluginExtension
import org.gradle.api.tasks.testing.Test
import org.gradle.jvm.toolchain.JavaLanguageVersion

class JavaLibraryConventionPlugin : Plugin<Project> {
    override fun apply(project: Project) {
        project.pluginManager.apply(JavaLibraryPlugin::class.java)

        project.extensions.configure(JavaPluginExtension::class.java) {
            toolchain.languageVersion.set(JavaLanguageVersion.of(21))
        }

        project.tasks.withType(Test::class.java).configureEach {
            useJUnitPlatform()
        }
    }
}
```

Plugin này áp dụng `java-library`, chọn Java toolchain 21 và cấu hình các task `Test` dùng JUnit Platform. Các module áp dụng plugin sẽ nhận cùng quy ước.

Trong build logic thực tế, cần khai báo các plugin và thư viện mà implementation cần trong build của `build-logic`. Không nên giả định Version Catalog của build chính tự động xuất hiện trong included build; included build có cấu hình Settings và dependency resolution riêng. Nếu muốn chia sẻ catalog, phải import hoặc cấu hình nó một cách rõ ràng.

### 5.4. Áp dụng theo vai trò mô-đun

Mô-đun domain:

```kotlin
// domain/build.gradle.kts
plugins {
    id("company.java-library")
}

dependencies {
    // Chỉ dependency domain thực sự cần
}
```

Mô-đun persistence:

```kotlin
// persistence/build.gradle.kts
plugins {
    id("company.java-library")
}

dependencies {
    implementation(project(":domain"))
    // Thêm driver và thư viện persistence riêng tại đây
}
```

Mô-đun application có thể dùng plugin khác:

```kotlin
// application/build.gradle.kts
plugins {
    application
}

application {
    mainClass.set("com.example.order.OrderApplication")
}

dependencies {
    implementation(project(":domain"))
    implementation(project(":persistence"))
}
```

Hai module library dùng chung convention. Application có cấu hình riêng phù hợp vai trò chạy ứng dụng. Nếu application cũng cần một số quy tắc chung, có thể tạo convention plugin `company.application` riêng thay vì ép nó áp dụng Java library convention.

### 5.5. Convention plugin nên chứa điều gì?

Một convention plugin tốt thường chứa các quy tắc ổn định và có ý nghĩa cho một nhóm project:

- Áp dụng plugin nền tảng cần thiết.
- Cấu hình Java toolchain và compiler options.
- Cấu hình test framework và test logging.
- Đăng ký task kiểm tra chất lượng dùng chung.
- Đặt quy tắc đóng gói hoặc publishing phù hợp với vai trò module.
- Cấu hình dependency constraint hoặc dependency dùng chung thực sự bắt buộc.

Không nên đưa mọi dependency tùy chọn vào convention plugin. Ví dụ, driver PostgreSQL chỉ nên được khai báo ở module persistence nếu module khác không cần. Một convention plugin dành cho mọi Java library không nên âm thầm thêm thư viện HTTP client, JSON hoặc database vào tất cả mô-đun.

## 6. Chia sẻ cấu hình bằng `allprojects` và `subprojects`

Gradle cung cấp các block tiện dụng ở root project:

```groovy
allprojects {
    group = 'com.example.order'
    version = '1.0.0'
}

subprojects {
    repositories {
        mavenCentral()
    }
}
```

- `allprojects` cấu hình root project và các project con.
- `subprojects` chỉ cấu hình các project con.

Các block này có thể phù hợp cho thuộc tính đơn giản hoặc quy tắc thực sự áp dụng rộng. Tuy nhiên, nếu chứa nhiều logic plugin, dependency, task hoặc callback, root build script sẽ trở thành nơi có quá nhiều tác động ẩn.

Những rủi ro thường gặp:

- Một mô-đun không cần Java plugin nhưng bị áp dụng cấu hình Java chung.
- Mô-đun mới tự động nhận dependency hoặc task không liên quan.
- Khó hiểu cấu hình đến từ file root hay build script riêng của module.
- Logic cấu hình khó tái sử dụng ngoài build hiện tại.
- Cấu hình chéo project có thể làm tăng phụ thuộc giữa các project và gây khó khăn khi tối ưu configuration cache.

Với build lớn, convention plugin thường làm rõ ý định hơn: module nào cần Java library convention thì chủ động áp dụng plugin đó. `allprojects`/`subprojects` vẫn hữu ích khi phạm vi thật sự đồng nhất, nhưng nên giữ nội dung ngắn và dễ dự đoán.

## 7. Chia sẻ dependency mà vẫn giữ ranh giới mô-đun

### 7.1. Project dependency thể hiện quan hệ sử dụng

Nếu `persistence` sử dụng API của `domain`, hãy khai báo quan hệ đó:

```kotlin
// persistence/build.gradle.kts
dependencies {
    implementation(project(":domain"))
}
```

Không nên chỉ thêm output của `domain` bằng đường dẫn file hoặc copy class vào `persistence`. Project dependency giúp Gradle hiểu quan hệ giữa các project, phân giải variant và sắp xếp task cần thiết.

### 7.2. Chọn `api` hay `implementation`

Với `java-library`, `api` dùng cho dependency có kiểu hoặc API được lộ ra qua API công khai của thư viện; `implementation` dùng cho dependency nội bộ.

```kotlin
plugins {
    `java-library`
}

dependencies {
    api(project(":domain-api"))
    implementation("org.slf4j:slf4j-api:2.0.13")
}
```

Nếu public method của thư viện trả về kiểu thuộc `domain-api`, consumer cần nhìn thấy dependency đó trên compile classpath, nên `api` có thể phù hợp. Nếu SLF4J chỉ được dùng bên trong implementation, `implementation` thường là lựa chọn đúng.

Đừng dùng `api` cho mọi dependency chỉ để tránh lỗi compile. Làm vậy khiến dependency nội bộ bị lộ cho consumer và tăng phạm vi compile classpath. Ngược lại, dùng `implementation` cho kiểu xuất hiện trong public API có thể khiến consumer không biên dịch được.

### 7.3. Tránh vòng phụ thuộc giữa các project

Ví dụ không mong muốn:

```text
domain  ---> persistence
   ^             |
   |             v
   +----------- application
```

Nếu `domain` cần `persistence` trong khi `persistence` cũng cần `domain`, hai mô-đun tạo quan hệ vòng. Điều này thường là dấu hiệu ranh giới kiến trúc chưa rõ. Có thể tách interface/port vào một module trung gian hoặc đảo chiều dependency để implementation phụ thuộc vào abstraction.

Một cấu trúc thường dễ kiểm soát hơn:

```text
application ---> persistence ---> domain-api
      |                              ^
      +------------------------------+
```

Sơ đồ chỉ minh họa một lựa chọn. Kiến trúc thực tế có thể khác, nhưng dependency graph nên thể hiện hướng phụ thuộc có chủ đích và tránh chu trình không cần thiết.

## 8. Chia sẻ task và quy tắc thực thi theo cách lazy

Khi nhiều project cần cấu hình task cùng loại, dùng API cấu hình lazy:

```kotlin
tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    testLogging {
        events("failed", "skipped")
    }
}
```

Trong convention plugin, có thể dùng `configureEach` để cấu hình task khi nó được tạo/được yêu cầu. Với task mới, ưu tiên `tasks.register` thay vì tạo task eagerly:

```kotlin
tasks.register("printModuleName") {
    group = "help"
    description = "Prints the current project path."

    doLast {
        logger.lifecycle("Project: ${project.path}")
    }
}
```

Task registration lazy giúp Gradle không phải tạo và cấu hình mọi task ngay lập tức nếu chúng không được dùng. Trong build nhiều mô-đun, điều này có thể cải thiện thời gian cấu hình và hỗ trợ configuration cache.

Hạn chế truy cập task của project khác bằng cách dò container hoặc dùng `afterEvaluate` để chờ cấu hình. Khi một project cần output từ project khác, hãy mô hình hóa dependency qua project dependency hoặc task input/output phù hợp. Build tool có thể từ đó thiết lập thứ tự và truyền dữ liệu rõ ràng.

## 9. Không nhầm multi-project build với composite build

Gradle có hai cách tổ chức nhiều phần build thường bị nhầm lẫn:

| Khái niệm | Đặc điểm | Ví dụ sử dụng |
|---|---|---|
| Multi-project build | Nhiều project cùng thuộc một build, được khai báo trong Settings bằng `include` | Một ứng dụng gồm domain, persistence, API và application |
| Composite build | Nhiều build độc lập được kết hợp bằng `includeBuild` | Dùng build plugin nội bộ hoặc thay dependency repository bằng source build trong quá trình phát triển |

Multi-project build có một Settings chính và các project path như `:domain`, `:api`. Composite build có thể gồm nhiều build độc lập, mỗi build có Settings và lifecycle riêng.

Ví dụ included build cho build logic:

```kotlin
pluginManagement {
    includeBuild("build-logic")
}
```

Ở đây `build-logic` là một build riêng được đưa vào quá trình phân giải plugin. Nó không phải một subproject thông thường của root project. Điều này hữu ích để phát triển convention plugin, nhưng cũng có nghĩa nó có dependency resolution và cấu hình riêng.

Nếu một thư viện source được phát triển trong repository khác, composite build cũng có thể thay thế module dependency đã publish bằng project từ included build thông qua dependency substitution. Cần dùng cơ chế đó có chủ đích để local build phản ánh đúng dependency mà CI hoặc production sẽ dùng.

## 10. Maven: chia sẻ qua parent POM, dependencyManagement và pluginManagement

Maven tổ chức cấu hình nhiều mô-đun chủ yếu qua POM cha và cơ chế kế thừa.

### 10.1. Parent POM và aggregator

Một POM có thể vừa là parent cho các module con, vừa là aggregator liệt kê các module trong reactor build:

```xml
<project>
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example.order</groupId>
    <artifactId>order-platform</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>domain</module>
        <module>persistence</module>
        <module>application</module>
    </modules>
</project>
```

`<modules>` xác định những project tham gia reactor build. `<parent>` trong POM con xác định POM mà module kế thừa. Hai khái niệm thường được dùng cùng nhau nhưng có ý nghĩa riêng: aggregator tổ chức build nhiều module; parent cung cấp cấu hình kế thừa.

### 10.2. Quản lý dependency version

Parent POM có thể đặt properties và `dependencyManagement`:

```xml
<properties>
    <jackson.version>2.17.2</jackson.version>
    <slf4j.version>2.0.13</slf4j.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>${jackson.version}</version>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>${slf4j.version}</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Module con khai báo dependency cần dùng nhưng không lặp version:

```xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
</dependencies>
```

`dependencyManagement` quản lý version và một số thuộc tính dependency khi module khai báo nó. Nó không tự thêm mọi dependency được liệt kê vào classpath của tất cả module.

### 10.3. Import BOM

Parent POM có thể import BOM để quản lý một nhóm thư viện tương thích:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Module con có thể khai báo starter mà không lặp version. BOM tập trung version của framework; parent POM tập trung chính sách cho các module thuộc hệ thống. Không nên tự ghi version cho từng starter nếu BOM đã quản lý và dự án không có lý do ghi đè.

### 10.4. Quản lý plugin version bằng pluginManagement

Parent POM cũng có thể quản lý version và cấu hình plugin:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>21</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

`pluginManagement` quản lý version và cấu hình mặc định của plugin khi plugin được kích hoạt trong build phù hợp. Nó không có nghĩa mọi plugin liệt kê trong đó đều tự động được thực thi. Phần `<build><plugins>` được dùng để đưa plugin vào build của project.

### 10.5. Giới hạn của kế thừa Maven

Parent POM giúp giảm lặp, nhưng parent quá lớn có thể làm mọi module nhận nhiều cấu hình khó hiểu. Một số module có thể cần cấu hình riêng hoặc cần một parent khác. Hãy giữ parent tập trung vào những quy tắc thực sự dùng chung và dùng profile/plugin riêng khi có khác biệt theo môi trường hoặc vai trò.

## 11. Ví dụ tổng thể: tổ chức một Gradle multi-project build

Giả sử hệ thống gồm domain library, persistence library và application. Mục tiêu là thống nhất Java 21, JUnit Platform, repository và version dependency; mỗi module vẫn khai báo thư viện riêng.

### 11.1. Cấu trúc thư mục

```text
order-platform/
├── settings.gradle.kts
├── build.gradle.kts
├── gradle/
│   └── libs.versions.toml
├── build-logic/
│   ├── build.gradle.kts
│   └── src/main/kotlin/
│       └── company.java-library.gradle.kts
├── domain/
│   └── build.gradle.kts
├── persistence/
│   └── build.gradle.kts
└── application/
    └── build.gradle.kts
```

### 11.2. Settings

```kotlin
pluginManagement {
    includeBuild("build-logic")
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

rootProject.name = "order-platform"
include("domain", "persistence", "application")
```

### 11.3. Version Catalog

```toml
[versions]
slf4j = "2.0.13"
junit = "5.10.3"
jackson = "2.17.2"

[libraries]
slf4j-api = { module = "org.slf4j:slf4j-api", version.ref = "slf4j" }
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }
jackson-databind = { module = "com.fasterxml.jackson.core:jackson-databind", version.ref = "jackson" }
```

### 11.4. Convention plugin cho Java library

```kotlin
// build-logic/src/main/kotlin/company.java-library.gradle.kts
plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
```

Để convention plugin có ID `company.java-library`, build logic cần đăng ký plugin với ID và implementation tương ứng hoặc dùng cơ chế precompiled script plugin theo quy ước Gradle. File precompiled script plugin trên có tên tạo ra ID theo tên file, nếu build logic đã bật Kotlin DSL plugin.

### 11.5. Module domain

```kotlin
plugins {
    id("company.java-library")
}

dependencies {
    testImplementation(libs.junit.jupiter)
}
```

### 11.6. Module persistence

```kotlin
plugins {
    id("company.java-library")
}

dependencies {
    implementation(project(":domain"))
    implementation(libs.slf4j.api)
    testImplementation(libs.junit.jupiter)
}
```

### 11.7. Module application

```kotlin
plugins {
    application
}

application {
    mainClass.set("com.example.order.OrderApplication")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

dependencies {
    implementation(project(":domain"))
    implementation(project(":persistence"))
    implementation(libs.jackson.databind)
}
```

Trong ví dụ:

- Settings quản lý project, plugin repository và dependency repository.
- Version Catalog quản lý version alias.
- Convention plugin áp dụng Java library quy ước cho `domain` và `persistence`.
- Mỗi module khai báo dependency đúng vai trò.
- `application` dùng Application plugin để chạy và phân phối ứng dụng.
- Project dependency thể hiện quan hệ giữa các mô-đun.

Root build không phải nơi khai báo tất cả dependency cho tất cả module. Mỗi phần cấu hình có một phạm vi và trách nhiệm rõ ràng.

## 12. Chia sẻ cấu hình giữa nhiều repository

Một tổ chức có thể có nhiều repository độc lập nhưng muốn dùng cùng quy ước build. Trong trường hợp đó, chỉ đặt `build-logic` trong một multi-project build không đủ, vì included build chỉ thuộc build đang include nó.

Có thể chọn một trong các hướng:

1. **Phát hành convention plugin:** đóng gói build logic thành plugin và publish lên plugin repository nội bộ. Các repository khác khai báo plugin ID/version và áp dụng.
2. **Dùng included build từ repository riêng:** phù hợp khi đang phát triển plugin hoặc cần thay đổi đồng thời build logic và project tiêu thụ. Cần quản lý source checkout và version trong CI.
3. **Chia sẻ Version Catalog:** publish hoặc import catalog dùng chung để thống nhất alias/version; mỗi build vẫn quyết định dependency nào cần dùng.
4. **Phát hành platform/BOM:** cung cấp bộ dependency constraints để nhiều project căn chỉnh version thư viện.
5. **Dùng parent POM hoặc Maven BOM:** với hệ sinh thái Maven, phát hành parent POM hoặc BOM cho các repository kế thừa/import.

Khi chia sẻ qua repository, cần quản lý version của chính convention plugin và platform. Build logic là một sản phẩm cần được phát hành, kiểm thử và nâng cấp có chủ đích. Không nên để mọi repository tự tham chiếu một nhánh source đang thay đổi mà không có quy trình kiểm soát.

## 13. Chia sẻ theo môi trường mà không nhân đôi build script

Một số cấu hình thay đổi theo local, CI, staging hoặc production. Không nên tạo một bản build script riêng cho mỗi môi trường nếu khác biệt chỉ là giá trị cấu hình.

Có thể dùng Gradle project property hoặc environment variable:

```kotlin
val targetEnvironment = providers.gradleProperty("targetEnvironment")
    .orElse("dev")

tasks.register("printTargetEnvironment") {
    doLast {
        logger.lifecycle("Target environment: ${targetEnvironment.get()}")
    }
}
```

Chạy:

```bash
./gradlew printTargetEnvironment -PtargetEnvironment=staging
```

Hoặc dùng biến môi trường theo quy ước Gradle:

```text
ORG_GRADLE_PROJECT_targetEnvironment=production
```

Với cấu hình nhạy cảm như token hoặc password, dùng secret store của CI và chỉ truyền cho bước cần thiết. Không đặt bí mật vào Version Catalog, build script hoặc file cấu hình được commit.

Nếu property ảnh hưởng đến output của task, cần khai báo nó như task input để Gradle biết khi nào task phải chạy lại. Không nên đọc trực tiếp một biến môi trường ẩn trong task action rồi kỳ vọng incremental build hoặc build cache luôn nhận ra thay đổi.

## 14. Những cách chia sẻ dễ gây vấn đề

### 14.1. Đưa mọi dependency vào root và áp dụng cho tất cả mô-đun

Điều này khiến các mô-đun nhận dependency không cần thiết, làm compile/runtime classpath lớn và che giấu module nào thực sự sử dụng thư viện. Hãy tập trung version bằng catalog/platform, còn dependency declaration giữ tại mô-đun tiêu thụ.

### 14.2. Lặp cùng một khối cấu hình trong nhiều build script

Sao chép toolchain, test logging, compiler options và task registration tạo ra nhiều nguồn cần sửa. Nếu các mô-đun cùng vai trò, hãy tạo convention plugin có tên rõ ràng.

### 14.3. Dùng `subprojects` để áp dụng plugin không phân biệt vai trò

Không phải mọi project con đều là Java library. Một project platform, build logic, application hoặc documentation có thể cần cấu hình khác. Hãy áp dụng convention plugin theo vai trò thay vì áp dụng một cấu hình rộng cho mọi project.

### 14.4. Đặt quá nhiều logic trong root build script

Root script có thể trở thành nơi chứa task của module khác, `afterEvaluate`, truy cập project chéo và điều kiện phức tạp. Điều này làm build khó hiểu và có thể cản trở configuration cache. Tách logic ổn định vào convention plugin hoặc task type.

### 14.5. Chia sẻ version nhưng không kiểm tra compatibility

Một catalog có thể giúp mọi mô-đun dùng cùng version, nhưng không tự đảm bảo các thư viện tương thích. Dùng BOM/platform khi nhà phát hành cung cấp bộ version tương thích; đọc release notes và chạy kiểm thử sau khi nâng cấp.

### 14.6. Dùng một convention plugin cho những vai trò khác nhau

Nếu application, library và platform project có nhu cầu khác nhau, một plugin khổng lồ với nhiều điều kiện theo tên project sẽ khó bảo trì. Tách convention theo vai trò để mỗi plugin có một mục đích rõ ràng.

### 14.7. Dùng đường dẫn file thay cho project dependency

Thêm output của project khác bằng file path khiến Gradle không hiểu đầy đủ quan hệ project và variant. Hãy dùng `implementation(project(":domain"))` hoặc `api(project(...))` tùy cách API được công bố.

## 15. Kiểm tra cấu hình dùng chung có hiệu lực

Sau khi tổ chức cấu hình, hãy quan sát mô hình build thực tế.

### 15.1. Xem cấu trúc project và task

```bash
# Xem các project trong build
./gradlew projects

# Xem task có sẵn
./gradlew tasks --all

# Xem chi tiết một task
./gradlew help --task test
```

`projects` xác nhận Settings đã include đúng mô-đun. `tasks --all` cho biết plugin và convention đã tạo task nào. `help --task` hiển thị thông tin task cụ thể.

### 15.2. Xem dependency graph theo mô-đun

```bash
# Dependency của domain
./gradlew :domain:dependencies

# Runtime classpath của application
./gradlew :application:dependencies --configuration runtimeClasspath

# Tìm lý do version được chọn
./gradlew :application:dependencyInsight \
    --dependency jackson-databind \
    --configuration runtimeClasspath
```

Kiểm tra từng module giúp phát hiện dependency bị áp dụng nhầm hoặc version khác dự kiến. Nếu một thư viện chỉ cần trong test, xác nhận nó không xuất hiện trong runtime classpath chính của ứng dụng.

### 15.3. Chạy các task phù hợp

```bash
# Chạy test cho một module
./gradlew :domain:test

# Chạy build của một module
./gradlew :persistence:build

# Chạy toàn bộ build
./gradlew build
```

Gradle chỉ thực thi task được yêu cầu và các task tiền đề cần thiết. Khi chạy `:application:build`, Gradle có thể thực hiện task của project dependency như `domain` hoặc `persistence` theo task graph.

### 15.4. Maven tương ứng

```bash
# Xem reactor modules
./mvnw -pl :order-platform help:evaluate -Dexpression=project.artifactId -q -DforceStdout

# Xem dependency tree
./mvnw -pl application dependency:tree

# Chạy build reactor
./mvnw verify
```

Với Maven, có thể dùng `-pl` để chọn project trong reactor, `-am` để build thêm project mà project được chọn phụ thuộc vào. Ví dụ:

```bash
./mvnw -pl application -am verify
```

`-am` (also make) yêu cầu Maven xây dựng các project trong reactor mà project được chọn phụ thuộc vào. Điều này hữu ích khi kiểm tra một mô-đun trong build nhiều mô-đun.

## 16. Quy trình thiết kế chia sẻ cấu hình

Khi bắt đầu một build nhiều mô-đun hoặc tái cấu trúc build hiện tại, có thể thực hiện theo trình tự:

1. **Liệt kê vai trò mô-đun.** Xác định library, application, platform, adapter, test fixture và build logic.
2. **Xác định chính sách toàn build.** Chọn project nào tham gia build, repository nào được phép và plugin version được phân giải ở đâu.
3. **Tập trung version.** Dùng Version Catalog cho alias/version và BOM/platform cho nhóm thư viện cần căn chỉnh.
4. **Nhóm quy ước theo vai trò.** Tạo convention plugin cho Java library, application hoặc module có yêu cầu riêng.
5. **Giữ dependency tại nơi sử dụng.** Mỗi module khai báo dependency và project dependency phản ánh nhu cầu thực tế.
6. **Giữ task lazy và ranh giới rõ.** Dùng task registration/configuration phù hợp, tránh logic chéo project không cần thiết.
7. **Quản lý cấu hình môi trường.** Truyền giá trị qua property hoặc environment; giữ bí mật trong secret store.
8. **Kiểm tra mô hình thực tế.** Xem project, task và dependency graph theo từng module.
9. **Nâng cấp có kiểm soát.** Thay version tập trung, đọc compatibility notes và chạy test/build cho các mô-đun bị ảnh hưởng.
10. **Tài liệu hóa quy ước.** Giải thích convention plugin nào dành cho vai trò nào và cách module áp dụng nó.

## 17. Bài tập vận dụng

Một hệ thống có năm mô-đun: `domain`, `persistence`, `api`, `worker` và `application`. Tất cả mô-đun Java cần dùng Java 21. Tất cả dùng JUnit Platform để chạy test. Chỉ `api` và `application` dùng Jackson; chỉ `persistence` dùng JDBC driver; `application` phụ thuộc `api`, `worker` phụ thuộc `domain` và `persistence`.

Hãy thiết kế cách chia sẻ cấu hình:

1. Những thông tin nào nên đặt trong `settings.gradle.kts`?
2. Nên khai báo version Jackson, JUnit và JDBC driver ở đâu?
3. Có nên thêm Jackson vào dependency của tất cả project để thống nhất version không? Vì sao?
4. Convention plugin nào có thể được tạo cho các Java library? Mô-đun nào nên áp dụng?
5. Application plugin nên được áp dụng ở đâu?
6. Quan hệ project dependency giữa các module nên được khai báo như thế nào?
7. Nếu public API của `api` sử dụng kiểu từ `domain`, cần cân nhắc `api` hay `implementation`?
8. Nếu muốn dùng chung cấu hình cho một repository khác, nên publish convention plugin, catalog hay platform trong tình huống nào?
9. Dùng lệnh nào để xác nhận runtime classpath của `application` chỉ chứa dependency cần thiết?
10. Nếu CI dùng môi trường `staging`, truyền property như thế nào mà không tạo build script riêng?

Có thể thực hành bằng một Gradle multi-project nhỏ: khai báo Settings, tạo Version Catalog, thêm convention plugin trong included build và áp dụng plugin cho hai Java library. Sau đó chạy `./gradlew projects`, `./gradlew tasks --all`, `./gradlew :application:dependencies --configuration runtimeClasspath` và `./gradlew build` để quan sát tác động của từng lớp cấu hình.

## 18. Nguyên tắc duy trì lâu dài

- **Chia sẻ chính sách, không chia sẻ dependency một cách mù quáng.** Version có thể tập trung; dependency vẫn thuộc mô-đun sử dụng nó.
- **Dùng Settings cho quyết định toàn build.** Cấu trúc project và repository nên có một nguồn quản lý rõ ràng.
- **Dùng Version Catalog cho tên và version.** Dùng platform/BOM khi cần căn chỉnh một nhóm thư viện tương thích.
- **Dùng convention plugin cho quy tắc theo vai trò.** Tên plugin nên cho biết loại project và hành vi được áp dụng.
- **Giữ project dependency tường minh.** Quan hệ giữa mô-đun cần thể hiện bằng dependency declaration, không dựa vào file path hoặc thứ tự build thủ công.
- **Tránh cấu hình toàn cục quá rộng.** `allprojects` và `subprojects` nên giữ ngắn; logic theo vai trò nên nằm trong convention plugin.
- **Giữ task lazy và input/output rõ ràng.** Điều này giúp build dễ tối ưu và ít phụ thuộc chéo.
- **Quản lý build logic như mã nguồn sản phẩm.** Convention plugin cần version, kiểm thử và tài liệu.
- **Không để cấu hình môi trường và bí mật bị trộn lẫn.** Dùng project property, environment variable và secret store theo đúng mục đích.
- **Kiểm tra từng mô-đun sau thay đổi.** Xem dependency graph, task graph và chạy test/build phù hợp.

Khi dự án có nhiều mô-đun, một cấu hình tốt không phải là cấu hình gom được nhiều dòng nhất vào root project. Cấu hình tốt là cấu hình cho thấy chính sách nào được chia sẻ, mô-đun nào áp dụng quy ước nào và dependency nào thực sự thuộc về mô-đun đó. Ranh giới rõ ràng giúp nhóm nâng cấp, mở rộng và bảo trì build mà không làm các mô-đun phụ thuộc vào những quy tắc ngoài trách nhiệm của chúng.
