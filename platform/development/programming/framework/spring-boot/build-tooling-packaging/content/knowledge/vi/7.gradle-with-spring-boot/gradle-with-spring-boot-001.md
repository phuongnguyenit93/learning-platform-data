# Cấu trúc settings.gradle và build.gradle trong dự án Spring Boot

## 1. Bức tranh tổng thể

Một dự án Spring Boot dùng Gradle thường có hai file cấu hình quan trọng:

- **`settings.gradle`**: mô tả *toàn bộ build* gồm tên root project, những subproject tham gia, cách tìm plugin, kho dependency dùng chung và các cấu hình quản lý dependency ở cấp build.
- **`build.gradle`**: mô tả *một project cụ thể* phải áp dụng plugin nào, dùng dependency nào, phiên bản/group ra sao, biên dịch bằng Java nào và tạo/chạy task gì.

Hai file trên dùng **Groovy DSL**. Nếu chọn **Kotlin DSL**, tên tương ứng là `settings.gradle.kts` và `build.gradle.kts`, cú pháp khác đôi chút nhưng trách nhiệm về cơ bản giống nhau. **Đừng dùng cú pháp Groovy rồi lưu trong file `.kts`, hoặc ngược lại.**

Bảng phân biệt nhanh:

| Vấn đề cần cấu hình | Vị trí thường dùng | Ví dụ |
|---|---|---|
| Tên build/root project | `settings.gradle` | `rootProject.name = 'orders-api'` |
| Thêm module vào build | `settings.gradle` | `include 'orders-api', 'shared-domain'` |
| Nơi tải plugin Gradle | `settings.gradle` → `pluginManagement.repositories` | `gradlePluginPortal()` |
| Kho thư viện dùng chung cho các module | `settings.gradle` → `dependencyResolutionManagement.repositories` | `mavenCentral()` |
| Plugin của một module | `build.gradle` → `plugins` | `id 'java'`, `id 'org.springframework.boot'` |
| Nhóm và phiên bản artifact | `build.gradle` | `group = 'com.example'`, `version = '0.1.0-SNAPSHOT'` |
| Java toolchain | `build.gradle` → `java` | `JavaLanguageVersion.of(17)` |
| Dependency source/test/runtime | `build.gradle` → `dependencies` | `implementation '...starter-web'` |
| Kiểm thử, đóng gói, chạy app | `build.gradle` và task do plugin cung cấp | `test`, `bootJar`, `bootRun` |
| Phiên bản Gradle mà wrapper tải | `gradle/wrapper/gradle-wrapper.properties` | `distributionUrl=...gradle-8.14.3-bin.zip` |
| Thuộc tính build và daemon | `gradle.properties` | `org.gradle.parallel=true` |

**Mô hình dễ nhớ:** `settings.gradle` trả lời “build này gồm những project nào và tìm các thành phần ở đâu?”; `build.gradle` trả lời “project này được tạo thành ứng dụng/thư viện bằng những plugin, dependency và task gì?”.

## 2. Cấu trúc thư mục single-module từ Spring Initializr

Giả sử tạo ứng dụng tên `orders-api`, Java 17, Gradle Groovy, Spring Boot 3.5.x. Thư mục thường có cấu trúc:

```text
orders-api/
├── settings.gradle                         # Danh tính và cấu trúc build
├── build.gradle                            # Logic build cho root project
├── gradle.properties                       # Có thể có, không bắt buộc
├── .gitignore
├── gradlew                                 # Wrapper script cho Unix/macOS
├── gradlew.bat                             # Wrapper script cho Windows
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar              # Mã bootstrap wrapper
│       └── gradle-wrapper.properties        # Version/distribution Gradle
├── src/
│   ├── main/
│   │   ├── java/com/example/orders/
│   │   │   ├── OrdersApplication.java
│   │   │   └── HelloController.java
│   │   └── resources/
│   │       └── application.properties
│   └── test/
│       └── java/com/example/orders/
│           └── OrdersApplicationTests.java
└── build/                                  # Sinh sau khi chạy Gradle
    ├── classes/
    ├── resources/
    ├── reports/
    ├── test-results/
    └── libs/
```

Đây là cấu trúc **minh họa đã bổ sung controller và test**; Spring Initializr có thể sinh cấu trúc hoặc file khác tùy dependency. Thư mục `build/` xuất hiện sau khi chạy task, thông thường được loại khỏi Git. Hai file `settings.gradle` và `build.gradle` cùng nằm ở root trong project một module; không cần một file `build.gradle` riêng cho `src/main`.

`gradlew` / `gradlew.bat` là các script gọi đúng phiên bản Gradle qua wrapper. Nên dùng wrapper thay vì `gradle` cài toàn cục khi làm việc nhóm và CI, đồng thời commit các file wrapper cần thiết.

## 3. settings.gradle: nội dung và ý nghĩa

### 3.1. Trường hợp tối giản

Một project Spring Boot **single-module** đơn giản có thể chỉ cần:

```groovy
// settings.gradle (Groovy DSL)
rootProject.name = 'orders-api'
```

`rootProject.name` đặt tên root project. Giá trị này được Gradle dùng trong báo cáo, cấu trúc task và thường ảnh hưởng tên file archive mặc định nếu không tùy chỉnh. Nó **không tự đổi** Java package (`package com.example.orders;`), `group` hay Spring property `spring.application.name`.

Nếu không ghi rõ root name, Gradle có thể dựa vào tên thư mục; khi checkout dự án vào đường dẫn khác, tên ngầm định dễ thay đổi. Đặt tên ổn định trong `settings.gradle` giúp CI và developer có kết quả nhất quán.

### 3.2. Khai báo repository và chính sách dùng repository tập trung

Một `settings.gradle` phù hợp khi muốn kiểm soát cả plugin và dependency repositories:

```groovy
// settings.gradle: ví dụ hoàn chỉnh cho ứng dụng single-module

pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'orders-api'
```

Giải thích chính xác từng phần:

1. `pluginManagement.repositories` cho Gradle biết **nơi tìm plugin** được khai báo qua `plugins { ... }`. `gradlePluginPortal()` là một repository cho plugin, khác với repository chứa thư viện chạy ứng dụng.
2. `dependencyResolutionManagement.repositories` cho Gradle biết **nơi tìm thư viện** như `spring-boot-starter-web`, Jackson, JUnit…
3. `repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS` yêu cầu các project không tự khai báo repository khác trong `build.gradle`; nếu có, Gradle báo lỗi. Quy tắc này hữu ích khi tổ chức muốn quản lý nguồn thư viện tập trung. Nó là lựa chọn có chủ đích, **không bắt buộc**.
4. `rootProject.name` là tên root project.

**Rất quan trọng:** `pluginManagement { ... }` nếu có phải xuất hiện ở đầu `settings.gradle`, trước các statement cấu hình thông thường. Đừng để `rootProject.name` hoặc `include` đứng trước `pluginManagement` rồi mới cấu hình plugin repository.

Trong ví dụ trên, **không thêm** `repositories { mavenCentral() }` trong `build.gradle`, vì `FAIL_ON_PROJECT_REPOS` cố ý cấm repository cấp project. Nếu không muốn centralize, có thể bỏ `dependencyResolutionManagement` và khai báo `repositories { mavenCentral() }` tại `build.gradle` như trong nhiều project đơn giản do Initializr tạo. Hai mẫu này là **hai cách tổ chức thay thế**, không ghép tùy tiện.

Ba chế độ repository chính của Gradle:

| Chế độ | Ý nghĩa |
|---|---|
| `PREFER_PROJECT` | Mặc định; repository ở project có thể được ưu tiên hơn repository khai báo trong settings |
| `PREFER_SETTINGS` | Ưu tiên repository trong settings và cảnh báo khi project khai báo repository khác |
| `FAIL_ON_PROJECT_REPOS` | Lỗi nếu project khai báo repository, buộc quản lý tại settings |

Khi hệ thống dùng artifact registry nội bộ, hãy khai báo repository tin cậy tại nơi phù hợp; **không hardcode password/token** vào Git. Có thể dùng credentials lấy từ biến môi trường, Gradle properties bảo mật hoặc secret của CI.

### 3.3. Đặt version plugin ở đâu?

Bạn có thể khai báo version plugin ngay trong `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}
```

Hoặc tập trung version plugin ở `pluginManagement.plugins` của `settings.gradle`:

```groovy
// Đoạn cấu hình thay thế ở đầu settings.gradle
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
    plugins {
        id 'org.springframework.boot' version '3.5.16'
        id 'io.spring.dependency-management' version '1.1.7'
    }
}
```

Khi dùng cách thứ hai, `build.gradle` có thể áp dụng plugin bằng ID **không lặp version**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
}
```

**Chọn một nguồn version rõ ràng** cho cùng plugin, đặc biệt ở multi-module. `pluginManagement` quản lý cách resolve plugin và default version; khai báo plugin tại đây **không đồng nghĩa tự áp dụng plugin** cho mọi project. Một project chỉ nhận task Spring Boot khi plugin `org.springframework.boot` thật sự được áp dụng ở project đó.

## 4. build.gradle: các khối quan trọng trong Spring Boot

Trong project Java, `build.gradle` là script cấu hình project và task. Những khối thường gặp:

| Khối / thuộc tính | Vai trò |
|---|---|
| `plugins { ... }` | Áp dụng Java plugin, Spring Boot Gradle plugin, dependency management, plugin test/quality khác |
| `group` và `version` | Tọa độ của artifact: tổ chức và version phát hành |
| `java { toolchain { ... } }` | Chọn JDK biên dịch/kiểm thử theo cấu hình toolchain |
| `repositories { ... }` | Nơi tải dependency **nếu không quản lý tập trung trong settings** |
| `dependencies { ... }` | Dependency theo configuration: `implementation`, `runtimeOnly`, `testImplementation`… |
| `tasks.named('test') { ... }` | Tùy chỉnh task test, ví dụ bật JUnit Platform |
| `tasks.named('bootJar') { ... }` | Tùy chỉnh artifact thực thi Boot nếu thật sự cần |
| `configurations { ... }` | Tùy chỉnh các nhóm dependency/configuration ở mức nâng cao |

### 4.1. Khối plugins

`id 'java'` áp dụng Java plugin: quy ước `src/main/java`, `src/test/java` và các task như `compileJava`, `test`, `jar`.

`id 'org.springframework.boot'` áp dụng Spring Boot Gradle plugin: khi dùng cùng Java plugin, nó hỗ trợ `bootRun`, `bootJar` và các tác vụ đóng gói/chạy phù hợp.

`id 'io.spring.dependency-management'` thêm cơ chế quản lý version dependency kiểu Maven. Khi cả plugin Spring Boot và plugin dependency management được áp dụng, Spring Boot **tự import** BOM `spring-boot-dependencies` tương ứng với version Spring Boot plugin, cho phép khai báo nhiều starter **không ghi version**.

Không bắt buộc dùng `io.spring.dependency-management`: Gradle native `platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)` cũng là một lựa chọn. Nếu không dùng cả plugin dependency management lẫn native BOM/constraints, những dependency không ghi version có thể không resolve được. Plugin Spring Boot **một mình** không tự bảo đảm mọi dependency đều đã có version.

### 4.2. Tọa độ project, JDK và dependency configurations

`group = 'com.example'` không phải package Java. `version = '0.1.0-SNAPSHOT'` là version ứng dụng/artifact của bạn, **không phải version Spring Boot**.

Java toolchain:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Toolchain giúp Gradle chọn JDK cho compile/test theo chính sách của Gradle; bản Gradle runtime/daemon vẫn cần JDK tương thích với version Gradle đang dùng. Nếu máy chưa có JDK 17 và chưa cấu hình toolchain download repository, Gradle có thể báo không tìm thấy toolchain; không coi đó là lỗi Spring Boot.

Các configuration phổ biến:

- `implementation`: dependency cần trong main code, không công bố API compile dependency cho consumer như `api` của `java-library`.
- `compileOnly`: chỉ cần để biên dịch, không tự có ở runtime.
- `runtimeOnly`: cần lúc chạy, không cần trực tiếp để compile main source.
- `testImplementation`: dùng để biên dịch/chạy test, không đưa thành main dependency chỉ vì xuất hiện ở test.
- `testRuntimeOnly`: chỉ cần ở runtime của test.
- `annotationProcessor` và `testAnnotationProcessor`: processor sinh mã (ví dụ Lombok) trong thời gian compile; không nên thêm bừa vào `implementation`.

Cơ chế configuration là lý do dependency `spring-boot-starter-test` thường nằm ở `testImplementation`, còn `spring-boot-starter-web` ở `implementation`.

## 5. Ví dụ hoàn chỉnh single-module với Groovy DSL

Dưới đây là **một project Spring Boot Java 17 có thể build/chạy** khi dùng Gradle Wrapper hợp lệ và có JDK 17, với plugin/version đã chọn để minh họa. Ví dụ dùng **cách tập trung repositories ở settings** và `io.spring.dependency-management` để tránh phải khai báo version cho starter.

### 5.1. File settings.gradle

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'orders-api'
```

### 5.2. File build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Ở ví dụ này:

- Không khai báo `repositories` trong `build.gradle` vì settings đã bật `FAIL_ON_PROJECT_REPOS`.
- `3.5.16` là version Spring Boot plugin được dùng cho ví dụ, `1.1.7` là version dependency management plugin. Kiểm tra compatibility với wrapper/JDK và chính sách phiên bản của hệ thống khi áp dụng thực tế.
- Các starter không ghi version vì BOM Spring Boot được import khi hai plugin tương ứng cùng được áp dụng.
- `useJUnitPlatform()` hướng task `test` chạy bộ test JUnit Jupiter/JUnit Platform, phù hợp với các bản `spring-boot-starter-test` hiện đại.

### 5.3. Mã nguồn Java chạy được

**`src/main/java/com/example/orders/OrdersApplication.java`**

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

**`src/main/java/com/example/orders/HelloController.java`**

```java
package com.example.orders;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    @GetMapping("/hello")
    public String hello() {
        return "Hello Spring Boot";
    }
}
```

**`src/test/java/com/example/orders/OrdersApplicationTests.java`**

```java
package com.example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrdersApplicationTests {
    @Test
    void contextLoads() {
    }
}
```

Đây là các file Java độc lập về tên/lớp, nhưng cần **dependency Spring Boot/JUnit do Gradle tải**; chỉ chạy `javac OrdersApplication.java` với JDK trần sẽ không tìm thấy các class của Spring Boot.

Lớp `OrdersApplication` nằm trong package `com.example.orders` nên Spring Boot mặc định quét cả `HelloController` cùng package. Chạy ứng dụng bằng wrapper:

```bash
# Unix/macOS, từ thư mục root project
./gradlew test
./gradlew bootRun
```

Trong một terminal khác, khi server đã khởi động trên cổng mặc định 8080:

```bash
curl --silent http://localhost:8080/hello
```

**HTTP response body mong đợi:** `Hello Spring Boot`. Lệnh `curl --silent` không nhất thiết tự in ký tự xuống dòng. Nếu cổng 8080 đã được dùng hoặc có cấu hình `server.port` khác, điều chỉnh URL tương ứng. Trên Windows PowerShell, có thể dùng `curl.exe http://localhost:8080/hello` hoặc `Invoke-WebRequest`; wrapper là `gradlew.bat`.

Đóng gói ứng dụng:

```bash
./gradlew bootJar
```

Thông thường file xuất hiện dưới `build/libs/orders-api-0.1.0-SNAPSHOT.jar` nếu chưa tùy chỉnh archive naming. Có thể chạy bằng:

```bash
java -jar build/libs/orders-api-0.1.0-SNAPSHOT.jar
```

Tên JAR thực tế nên xem trong `build/libs/`. Với project Boot áp dụng Java plugin, `bootJar` tạo executable JAR; `jar` thông thường tạo JAR khác. `build` chạy tập task assemble/check do plugin cấu hình, còn `bootRun` trực tiếp khởi chạy ứng dụng từ classpath phát triển.

### 5.4. Gradle Wrapper đi kèm

Ví dụ file `gradle/wrapper/gradle-wrapper.properties` (chỉ minh họa trường liên quan):

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.3-bin.zip
```

Đây là phiên bản Gradle 8.x được công bố và phù hợp với yêu cầu nền tảng của ví dụ Spring Boot 3.5.x. Các file wrapper thật có thể có thêm tham số timeout, verify SHA-256, base path…; dùng file do Initializr hoặc lệnh Gradle Wrapper tạo và commit kèm script/JAR cần thiết.

Không sửa `distributionUrl` để chuyển sang bản Gradle bất kỳ trước khi kiểm tra yêu cầu của **Spring Boot plugin** và các plugin build khác. Lệnh `./gradlew --version` giúp xác định phiên bản Gradle thực sự đang chạy.

## 6. Kotlin DSL: đổi đuôi file đi kèm đổi cú pháp

Nếu chọn **Gradle Kotlin** khi dùng Spring Initializr, hai file là `settings.gradle.kts` và `build.gradle.kts`. Chúng vẫn mô tả cùng cấu trúc và behavior, nhưng dùng cú pháp Kotlin.

**`settings.gradle.kts` tương đương:**

```kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}

rootProject.name = "orders-api"
```

**`build.gradle.kts` tương đương:**

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.1.0-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}
```

Ví dụ này dùng cùng các file Java ở mục 5. Cần hiểu sự khác nhau giữa `id 'java'` (Groovy) và `java` (Kotlin DSL), `implementation 'group:artifact'` so với `implementation("group:artifact")`, cũng như property setter `repositoriesMode = ...` và `repositoriesMode.set(...)`.

**Không cần tạo đồng thời hai file `build.gradle` và `build.gradle.kts` cho cùng một project.** Chọn một DSL nhất quán để tránh sự mơ hồ về script được dùng. Đừng copy một snippet Kotlin vào Groovy file chỉ vì cả hai đều được gọi là “Gradle configuration”.

## 7. settings.gradle trong multi-module build

Khi dự án lớn lên, bạn có thể tách code dùng chung (`shared-domain`) khỏi ứng dụng chạy độc lập (`orders-api`). Lúc đó `settings.gradle` là nơi định nghĩa **đồ thị project**.

Ví dụ:

```text
store-platform/
├── settings.gradle
├── build.gradle                 # Chung: version plugin, không áp dụng Boot tại root
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── orders-api/
│   ├── build.gradle             # Module ứng dụng Boot
│   └── src/main/java/...
└── shared-domain/
    ├── build.gradle             # Module thư viện Java
    └── src/main/java/...
```

**`settings.gradle` ở root:**

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'store-platform'
include 'orders-api', 'shared-domain'
```

Sau `include`, Gradle biết hai đường dẫn project là `:orders-api` và `:shared-domain`; tên chúng không phải package Java. Mặc định mỗi tên map đến thư mục cùng tên dưới root. Nếu tạo project lồng nhau, `include 'services:orders-api'` thường map tới `services/orders-api/`. Với Gradle hiện đại, đảm bảo thư mục subproject tồn tại, đặc biệt khi dùng Gradle 9+, để tránh lỗi khi khởi tạo.

**`build.gradle` ở root:** dùng `apply false` để version plugin có sẵn cho các module nhưng chưa áp dụng plugin Boot vào root.

```groovy
plugins {
    id 'org.springframework.boot' version '3.5.16' apply false
    id 'io.spring.dependency-management' version '1.1.7' apply false
}
```

**`orders-api/build.gradle`:** áp dụng plugin Boot vào đúng module chạy ứng dụng.

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation project(':shared-domain')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`shared-domain/build.gradle`:** khai báo module thư viện Java thuần, không tạo executable Boot JAR.

```groovy
plugins {
    id 'java-library'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Ở ví dụ này, `shared-domain` không khai báo dependency bên ngoài; nếu về sau thêm dependency không ghi version, cần quản lý version riêng qua BOM/platform hoặc quy tắc chung. Không suy ra rằng BOM áp dụng ở `orders-api` sẽ tự áp dụng cho mọi dependency declaration **của project `shared-domain`**.

Chạy riêng task một module:

```bash
./gradlew projects
./gradlew :orders-api:bootJar
./gradlew :shared-domain:jar
```

`:orders-api:bootJar` chỉ gọi task Boot ở module ứng dụng và các task phụ thuộc của nó; `shared-domain:jar` tạo JAR thư viện thường. Khi `orders-api` khai báo `implementation project(':shared-domain')`, Gradle xác định thứ tự và classpath phù hợp để sử dụng output của module thư viện.

Đừng áp dụng `org.springframework.boot` cho mọi module nếu một số module chỉ là library. Plugin Boot thường chỉ cần ở module tạo Boot executable application. Nếu nhiều module có chung build rules, dùng convention plugin hoặc cơ chế chia sẻ build logic có chủ đích thay vì copy cấu hình tràn lan.

## 8. Luồng đọc cấu hình của Gradle

Gradle xử lý build theo ba pha chính:

```text
Lệnh: ./gradlew bootJar
            |
            v
  INITIALIZATION
  Đọc settings.gradle
  -> Xác định rootProject và subprojects
  -> Thiết lập plugin/dependency resolution rules
            |
            v
  CONFIGURATION
  Đọc build.gradle của các project cần cấu hình
  -> Apply plugin
  -> Tạo/cấu hình task graph
  -> Xác định dependencies của task
            |
            v
  EXECUTION
  Chạy task được yêu cầu + task phụ thuộc
  -> compileJava, processResources,...
  -> bootJar
            |
            v
  build/libs/*.jar
```

Sơ đồ là mô hình khái niệm; configuration cache và các tối ưu của Gradle có thể thay đổi lượng công việc cần thực hiện, không thay đổi mục đích của từng file. Đừng gọi `bootJar` là phase trong `settings.gradle`: `bootJar` là **task** do Spring Boot Gradle plugin cung cấp trong project phù hợp.

Một file `settings.gradle` có thể có `includeBuild` để gắn build logic hoặc composite build; đó là khái niệm khác với `include` subproject. Với người mới, chỉ cần hiểu `include` tạo module trong cùng multi-project build; `includeBuild` kết nối một build riêng.

## 9. Nhìn đúng plugin repository, dependency repository và BOM

Ba thành phần có thể cùng xuất hiện nhưng giải quyết vấn đề riêng:

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Plugin repository | `pluginManagement { repositories { gradlePluginPortal() } }` | Tìm và tải Gradle plugins |
| Dependency repository | `dependencyResolutionManagement { repositories { mavenCentral() } }` | Tìm thư viện Java dùng bởi project |
| BOM / dependency management | `io.spring.dependency-management` hoặc `platform(...)` | Chọn version cho dependency đã được yêu cầu |

**Lỗi phổ biến:** chỉ khai báo `pluginManagement.repositories { gradlePluginPortal() }` rồi tự hỏi tại sao `spring-boot-starter-web` không tải được. Plugin Portal và Maven Central phục vụ hai nhu cầu khác nhau; nếu dependency repository thiếu hoặc có mạng/auth lỗi thì dependency resolution vẫn thất bại.

Nếu chọn native BOM thay vì plugin `io.spring.dependency-management`, phần cấu hình build có thể như sau (đây là **phương án thay thế**, không ghép thêm vào mẫu `build.gradle` mục 5):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    testImplementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Với cách này, hoàn thiện thêm `group`, `version`, `java { ... }`, `tasks.named('test') { ... }` cùng `settings.gradle` phù hợp như ví dụ single-module. `platform` đưa version BOM vào các dependency constraints của Gradle; các yêu cầu version khác trong graph có thể làm version được chọn khác BOM. `enforcedPlatform` là biến thể ép mạnh hơn và có thể gây xung đột hoặc ảnh hưởng consumer; không nên dùng khi chưa hiểu tác động.

Nếu plugin Spring Boot được áp dụng cùng `io.spring.dependency-management`, Boot tự import BOM; không cần thêm `platform` chỉ để “bảo đảm dependency”. Dùng một cách quản lý rõ ràng giúp phân tích version dễ hơn.

## 10. Các file liên quan nhưng có trách nhiệm khác

### 10.1. gradle.properties

`gradle.properties` lưu Gradle properties, ví dụ:

```properties
org.gradle.parallel=true
org.gradle.caching=true
```

Trong multi-module build có thể có properties ở cấp root và cơ chế properties ở mức user. Đừng lưu API token hoặc password thật trong `gradle.properties` được commit; đưa secret vào nơi an toàn và chỉ tham chiếu khi cần. `gradle.properties` không thay thế `settings.gradle` hay `build.gradle`.

### 10.2. gradle/libs.versions.toml

Một version catalog có thể tập trung alias và version:

```toml
[versions]
spring-boot = "3.5.16"

[libraries]
spring-boot-web = { module = "org.springframework.boot:spring-boot-starter-web" }

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "spring-boot" }
```

Khi đặt dưới `gradle/libs.versions.toml`, Gradle thường tự cung cấp catalog mặc định tên `libs`. Build script có thể tham chiếu alias plugin và library theo cú pháp DSL tương ứng, nhưng **version catalog không tự nhập BOM, không tự áp dụng plugin và không giải quyết tất cả xung đột dependency**. Đây là bước tổ chức thêm sau khi bạn hiểu `settings.gradle` và `build.gradle`.

### 10.3. application.properties / application.yml

`src/main/resources/application.properties` là **cấu hình của ứng dụng lúc runtime**, ví dụ:

```properties
spring.application.name=orders-api
server.port=8080
```

Nó khác hoàn toàn build script: `server.port` được Spring Boot đọc khi chạy ứng dụng, còn `rootProject.name` thuộc Gradle. Không viết `server.port=8080` trong `settings.gradle` rồi chờ Spring tự nhận. Cũng không lưu password thật trong `application.properties` được đưa vào Git/JAR.

### 10.4. .gitignore và thư mục build/

`build/`, `.gradle/` và file log là kết quả/cache cục bộ, thường bỏ qua trong Git. Ngược lại, `settings.gradle`, `build.gradle`, `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.properties` và `gradle/wrapper/gradle-wrapper.jar` là đầu vào quan trọng để người khác tái tạo build, thường cần commit.

## 11. Cách đọc và kiểm tra một dự án Spring Boot Gradle lạ

Khi mở repository chưa quen, nên đọc và kiểm tra theo thứ tự:

1. **`settings.gradle[.kts]`**: root name là gì? Có `include` module nào? Có `pluginManagement`, `dependencyResolutionManagement` hoặc repository nội bộ không?
2. **`gradle/wrapper/gradle-wrapper.properties`**: dùng Gradle version nào? Có tương thích với Spring Boot/Java/plugin?
3. **`build.gradle[.kts]` của module cần chạy**: áp dụng `java` và `org.springframework.boot` chưa? Plugin dependency management hoặc `platform` có được khai báo chưa?
4. **`group` / `version` / `java.toolchain`**: đã đặt theo release và JDK của dự án chưa?
5. **`dependencies`**: dependency vào main, test hay runtime? Version đến từ BOM/constraint nào?
6. **`src/main/java`**: main class `@SpringBootApplication` ở package gốc hợp lý không?
7. **Task graph**: có `bootRun` và `bootJar` ở đúng module không? Build và test chạy được không?

Những lệnh chẩn đoán hữu ích, chạy từ root project:

```bash
./gradlew --version
./gradlew projects
./gradlew tasks
./gradlew dependencies --configuration runtimeClasspath
./gradlew test
./gradlew bootJar
```

Với multi-module, nên chỉ định rõ module thay vì giả định task nằm tại root:

```bash
./gradlew :orders-api:tasks
./gradlew :orders-api:dependencies --configuration runtimeClasspath
./gradlew :orders-api:bootRun
```

Các lệnh trên in thông tin khác nhau tùy project/Gradle version; không có một stdout cố định cho mọi dự án. Lệnh `bootRun` tiếp tục giữ tiến trình ứng dụng cho đến khi bạn dừng, không phải lỗi treo build. Kiểm tra Java/Gradle version nếu command lỗi trước khi sửa ngẫu nhiên plugin.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/sửa |
|---|---|---|
| `Plugin [id: 'org.springframework.boot'] was not found` | Thiếu plugin repository, sai ID/version, mạng hoặc proxy | Xem `pluginManagement.repositories`, plugin version và quyền truy cập Plugin Portal |
| `Could not find ... spring-boot-starter-web` | Thiếu dependency repository hoặc chưa quản lý version cho dependency khai báo không có version | Xem `dependencyResolutionManagement.repositories`/`repositories` và BOM |
| `Build was configured to prefer settings repositories...` hoặc báo repository bị cấm | `FAIL_ON_PROJECT_REPOS` nhưng `build.gradle` vẫn có `repositories` | Xóa khai báo repository ở project hoặc đổi có chủ đích chính sách settings |
| `Task 'bootRun' not found` | Boot plugin chưa được áp dụng vào project đang gọi, hoặc gọi sai module | Xem `plugins` và `./gradlew :module:tasks` |
| `Task 'bootJar' not found` | Thiếu Java/Boot plugin hoặc gọi task ở root thay vì ứng dụng con | Xem cấu hình module và gọi `:orders-api:bootJar` |
| `Project with path ':shared-domain' could not be found` | Quên `include 'shared-domain'` hoặc tên module không trùng | Sửa `settings.gradle` và cấu trúc thư mục |
| `Could not find method implementation()` | Chưa áp dụng Java plugin hoặc khai báo dependency sai cấp | Kiểm tra `plugins { id 'java' }` và vị trí `dependencies` |
| Kotlin DSL báo lỗi với `id 'java'` hoặc `implementation '...'` | Sao chép cú pháp Groovy vào `.kts` | Đổi sang `id("java")` / `implementation("...")` hoặc dùng đúng file `.gradle` |
| `No matching toolchains found` | Máy thiếu JDK được yêu cầu hoặc chưa cấu hình resolver | Kiểm tra JDK 17, Java toolchain, `./gradlew --version` |
| Test không chạy theo JUnit Jupiter | Thiếu `useJUnitPlatform()`, thiếu test dependency hoặc không có test | Xem `tasks.named('test')`, `testImplementation` và báo cáo test |
| Module thư viện sinh Boot executable không mong muốn | Áp dụng Boot plugin cho mọi project | Chỉ áp dụng Boot plugin vào module application; module library dùng `java-library` |
| File JAR tên khác dự kiến | Root/project name, version hoặc `bootJar.archiveFileName` khác | Kiểm tra `rootProject.name`, `version` và `build/libs/` |

Có hai nguyên tắc xử lý lỗi quan trọng:

**Không đổi version bừa bãi.** Nếu build lỗi, hãy phân loại lỗi: plugin resolution, dependency resolution, Java toolchain, compile source, test hay packaging. Mỗi lớp có log và cách kiểm tra riêng.

**Không gọi `clean` để sửa mọi lỗi cấu hình.** `clean` xóa output, không sửa thiếu `include`, sai repository, không có plugin, nhầm DSL hay sai Java version. Đọc cấu hình tại đúng file trước.

## 13. Checklist thiết kế cấu trúc Gradle rõ ràng

- **Settings**: khai báo root name ổn định; tất cả module cần thiết được `include`; plugin repository và dependency repository đúng chính sách nhóm.
- **Project build**: mỗi module áp dụng đúng plugin; ứng dụng Boot có Java plugin + Spring Boot plugin; library thường không cần Boot executable plugin.
- **Dependency**: các starter/third-party library nằm đúng configuration; version được quản lý theo BOM/platform/constraint có chủ đích.
- **Java**: toolchain phù hợp với bản Spring Boot, Gradle Wrapper và môi trường triển khai.
- **Tests**: project có test dependency và task test được cấu hình đúng test framework.
- **Build output**: biết chạy `bootRun`, `bootJar`, `test`, `build`; biết nơi xem `build/libs` và report.
- **Multi-module**: root settings nêu rõ các module; từng build file tự quản lý vai trò của nó; dependency giữa module dùng `project(':...')`.
- **Reproducibility**: commit wrapper, settings, build script và source; tránh commit output/cache/secret; CI sử dụng wrapper.

### Tài liệu chính thức

- [Gradle User Manual — Structuring and Organizing Projects](https://docs.gradle.org/current/userguide/organizing_gradle_projects.html)
- [Gradle User Manual — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html)
- [Gradle User Manual — Centralizing Repository Declarations](https://docs.gradle.org/current/userguide/centralizing_repositories.html)
- [Gradle User Manual — Working with Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html)
- [Spring Boot 3.5 Gradle Plugin — Getting Started](https://docs.spring.io/spring-boot/3.5/gradle-plugin/getting-started.html)
- [Spring Boot Gradle Plugin — Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)

**Ghi nhớ:** `settings.gradle` **định nghĩa build và các project**; `build.gradle` **định nghĩa cách build một project**. Khi đi từ single-module sang multi-module, giữ rõ vai trò từng file, cấu hình repository/plugin một cách nhất quán, áp dụng Spring Boot plugin đúng module và xác minh qua Gradle Wrapper.
