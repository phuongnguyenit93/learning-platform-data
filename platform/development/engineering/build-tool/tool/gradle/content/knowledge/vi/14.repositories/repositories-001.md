# Repository plugin và repository dependency giải quyết hai nhu cầu khác nhau trong Gradle

## 1. Vấn đề cốt lõi: cùng tên repositories, khác đối tượng được tải

Trong một build Gradle, **plugin** bổ sung khả năng cấu hình/build (tạo task, extension và quy tắc), còn **dependency** là thư viện hoặc module mà mã ứng dụng và task của dự án cần để biên dịch/chạy/kiểm thử. Hai loại artifact có thể cùng nằm trong một kho Maven, nhưng **Gradle sử dụng những tập repository được cấu hình ở các ngữ cảnh khác nhau**.

Một câu cần nhớ:

> `pluginManagement.repositories` dùng để tìm **Gradle plugin được yêu cầu bằng plugins DSL**; `Project.repositories` hoặc `dependencyResolutionManagement.repositories` dùng để tìm **dependency của project** như `implementation("group:module:version")`.

Không thể chỉ khai báo `mavenCentral()` trong `pluginManagement` rồi cho rằng dependency của `implementation(...)` cũng sẽ được tìm tại Maven Central. Ngược lại, khai báo `gradlePluginPortal()` trong `repositories` của project không tự cấu hình kho cho `plugins { id("...") version "..." }`.

Bài học giúp bạn phân biệt các tập repository; hiểu đường đi của plugin marker và artifact thư viện; cấu hình Gradle Groovy DSL/Kotlin DSL ở đúng file; xử lý lỗi repository không tìm thấy; và thử một ví dụ Java 17 với plugin tích hợp và dependency ngoài.

## 2. Bản đồ các repository trong Gradle

| Khối Gradle | Nơi thường cấu hình | Được sử dụng cho | Không tự giải quyết |
| --- | --- | --- | --- |
| `pluginManagement { repositories { ... } }` | `settings.gradle` / `settings.gradle.kts` | Các plugin được yêu cầu qua `plugins { id(...) version ... }`; plugin marker và implementation của plugin. | `implementation`, `testImplementation` của ứng dụng. |
| `repositories { ... }` của Project | `build.gradle` / `build.gradle.kts` | Module/artifact dependency của project, theo configuration như `compileClasspath`, `runtimeClasspath`. | Plugin DSL của build script. |
| `dependencyResolutionManagement { repositories { ... } }` | `settings.gradle` / `settings.gradle.kts` | Khai báo và quản trị repository dependency tập trung cho các project. | Plugin DSL (`pluginManagement` là khối khác). |
| `buildscript { repositories { ... } }` | Build script Groovy/Kotlin | Dependency **classpath của chính build script**, hay gặp với cách apply plugin cũ. | Dependency của mã ứng dụng; không thay thế `pluginManagement`. |
| `publishing { repositories { ... } }` | Project áp dụng plugin publish thích hợp | **Đích xuất bản** artifact khi chạy publish. | Nơi tải dependency/plugin cho build. |

Ví dụ mục đích:

- `plugins { id("java") }` áp dụng **plugin Java tích hợp sẵn của Gradle**; không cần tải Java plugin từ Internet.
- `plugins { id("some.external.plugin") version "1.2.3" }` là yêu cầu một **plugin bên ngoài**; Gradle cần nguồn plugin phù hợp, thường là Plugin Portal hoặc private plugin repository.
- `dependencies { implementation("org.apache.commons:commons-lang3:3.17.0") }` là một **module dependency của project**; muốn tải phải có repository dependency như `mavenCentral()`.
- `buildscript.dependencies { classpath("...") }` là dependency của **build logic/classpath**, không làm JAR đó tự xuất hiện trong classpath chương trình Java của project.

Ba ngữ cảnh đầu là trọng tâm của bài. Hai ngữ cảnh sau giúp chẩn đoán build cũ và tránh nhầm “repository tải” với “repository phát hành”.

## 3. Luồng giải quyết plugin qua plugins DSL

Khi Gradle đọc một yêu cầu plugin bên ngoài:

```kotlin
plugins {
    id("org.example.my-plugin") version "1.2.3"
}
```

Gradle phải xác định plugin ID/phiên bản, tìm thành phần để tải mã plugin, rồi đặt plugin lên classpath build logic và áp dụng nó. Cách phổ biến với **plugin repository dạng Maven** là dùng một *plugin marker artifact* để ánh xạ plugin ID sang module chứa implementation.

Với ID `org.example.my-plugin` và version `1.2.3`, marker thông thường có dạng:

```text
group:   org.example.my-plugin
name:    org.example.my-plugin.gradle.plugin
version: 1.2.3
```

Marker có metadata chỉ tới module chứa implementation của plugin, có thể là tọa độ khác. Gradle sau đó cần tải implementation và các dependency cần cho plugin. Cấu trúc marker do cơ chế publish plugin tạo ra; một plugin nội bộ không có marker hợp lệ có thể khiến `plugins { id(...) }` báo không tìm thấy dù implementation JAR thật sự đang ở một kho Maven.

Đường đi (đơn giản hóa):

```text
plugins { id("x.y") version "1.2.3" }
                  |
                  v
      pluginManagement.repositories
                  |
         plugin marker / metadata
                  |
                  v
       plugin implementation module
                  |
                  v
        Gradle plugin classpath
                  |
                  v
          Plugin được áp dụng
      (tạo task / extension / config)
```

**Đây không phải đường đi của `implementation("group:artifact:version")`.** Module dependency không đi qua plugin marker; Gradle giải quyết tọa độ module theo repository dependency của configuration tương ứng.

### 3.1. Kho plugin mặc định

Nếu không tự khai báo các plugin repositories khác, Gradle mặc định dùng **Gradle Plugin Portal** để giải quyết plugin qua plugins DSL, bên cạnh cơ chế cho core plugin và plugin đã được cấp từ build logic khác. Khi đã cấu hình `pluginManagement.repositories` tùy chỉnh, **đừng giả định Plugin Portal vẫn tự động nằm trong danh sách**. Nếu cần Plugin Portal, hãy thêm `gradlePluginPortal()` tường minh.

**Kotlin DSL — settings.gradle.kts:**

```kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
```

**Groovy DSL — settings.gradle:**

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
```

`mavenCentral()` nằm trong `pluginManagement.repositories` ở ví dụ này chỉ là **ứng viên kho plugin**. Nó **không** biến Maven Central thành repository cho `implementation(...)`. Một plugin chỉ có implementation ở Maven Central nhưng **không có plugin marker** cũng không chắc dùng được ngay với `plugins`; cần cơ chế mapping plugin resolution phù hợp.

### 3.2. Plugin tích hợp không chứng minh repository plugin hoạt động

`plugins { id("java") }`, `plugins { id("application") }` hoặc `plugins { id("java-library") }` dùng các **core plugins** đi kèm Gradle distribution. Một build chỉ dùng core plugin có thể áp dụng plugin thành công dù sai hoặc thiếu plugin repository cho **plugin ngoài**.

Vì vậy, không dùng việc `./gradlew help` chạy được với mỗi core plugin để kết luận `pluginManagement.repositories` đã đúng cho mọi plugin của tổ chức.

## 4. Luồng giải quyết dependency của project

Trong project Java, ví dụ:

```kotlin
plugins {
    id("java")
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
```

`implementation(...)` đưa module vào một **dependency configuration** do Java plugin cung cấp. Khi Gradle cần giải quyết classpath (chẳng hạn `compileClasspath` hoặc `runtimeClasspath`), nó tìm metadata và artifact của dependency theo repository được cấu hình cho project, ví dụ Maven Central.

Đường đi:

```text
dependencies { implementation("g:a:1.2.3") }
                          |
                          v
       Configuration / classpath của Project
                          |
                          v
  Project.repositories / dependencyResolutionManagement
                          |
                          v
              Metadata + artifact
                          |
                          v
       Compile / Runtime / Test / Task inputs
```

Nếu một Gradle project **không có** repository dependency thích hợp, dù đã có `pluginManagement { repositories { gradlePluginPortal() } }`, việc resolve một module bên ngoài vẫn có thể lỗi.

### 4.1. Có nhiều loại dependency, không phải loại nào cũng cần Maven

- **External module dependency:** `implementation("org.apache.commons:commons-lang3:3.17.0")` cần repository chứa module.
- **Project dependency:** `implementation(project(":core"))` tham chiếu project cùng build; Gradle dùng project model và variant/artifact của `:core`, **không tải project `:core` từ Maven Central**.
- **File dependency:** `implementation(files("libs/manual.jar"))` dùng file local; không có metadata/transitive dependency như module published. Không cần repository mạng để tìm đúng file đó.

Do đó câu “mọi dependency đều phải tải từ Maven Central” cũng không đúng; phải phân biệt nguồn dependency.

### 4.2. Repository order và tính nhất quán

Khi khai báo nhiều repository, Gradle xét thứ tự các repository theo logic resolution. Nếu tìm được **metadata của một module** tại repository nhất định, Gradle thường dùng chính repository đó để lấy artifacts của module, thay vì lắp ghép tùy tiện giữa các nguồn khác nhau.

Điều này quan trọng với repository nội bộ:

- Nếu cùng `group:name:version` tồn tại ở nhiều kho, thứ tự và metadata có thể quyết định nguồn được chọn.
- Có thể dùng **content filters** hoặc `exclusiveContent` khi phù hợp để ràng buộc group/module nào được phép lấy ở kho nào.
- Tránh thêm mọi URL repository vào mọi khối một cách bừa bãi; build chậm, khó kiểm soát provenance và tăng nguy cơ lấy artifact không mong muốn.

## 5. Cấu hình nơi tìm plugin và dependency trong settings

Đây là cách tập trung hai nhu cầu, nhưng giữ **hai danh sách repository riêng**. Ví dụ với Kotlin DSL:

**`settings.gradle.kts`:**

```kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(
        org.gradle.api.initialization.resolve.RepositoriesMode.FAIL_ON_PROJECT_REPOS
    )
    repositories {
        mavenCentral()
    }
}

rootProject.name = "repo-separation-lab"
include(":app")
```

Groovy DSL tương đương:

**`settings.gradle`:**

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(
        org.gradle.api.initialization.resolve.RepositoriesMode.FAIL_ON_PROJECT_REPOS
    )
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'repo-separation-lab'
include 'app'
```

**Diễn giải chính xác:**

1. Gradle sẽ dùng `gradlePluginPortal()` để giải quyết những **external plugin requests qua plugins DSL**, nếu có.
2. Gradle sẽ dùng `mavenCentral()` để giải quyết **external module dependencies của các project** theo policy trong `dependencyResolutionManagement`.
3. `FAIL_ON_PROJECT_REPOS` là chế độ nghiêm ngặt: nếu một project hay plugin cố thêm dependency repository trực tiếp vào project, Gradle báo lỗi. Nó **không bắt** plugin resolution dùng Maven Central.
4. Không cần lặp lại `repositories { mavenCentral() }` trong từng module khi đã đặt policy này.
5. Trong build này `:app` có thể dùng core plugin `application`; plugin đó có sẵn trong Gradle, nên test không tạo traffic tới Plugin Portal trừ khi có một external plugin request khác.

Đây là mẫu phù hợp cho nhiều project cần quản lý nguồn thư viện tập trung. Đối với build nhỏ, bạn cũng có thể dùng `repositories { mavenCentral() }` ở mỗi project, nhưng không được vừa bật `FAIL_ON_PROJECT_REPOS` vừa đặt repository ở module.

## 6. RepositoriesMode: policy dùng settings hay project

`dependencyResolutionManagement.repositories` không luôn thắng `Project.repositories` theo cùng một cách. Gradle có ba chế độ quan trọng:

| Chế độ | Hành vi |
| --- | --- |
| `RepositoriesMode.PREFER_PROJECT` | **Mặc định:** nếu một project khai báo repository riêng thì repository của project đó được ưu tiên thay danh sách settings cho project ấy. |
| `RepositoriesMode.PREFER_SETTINGS` | Dùng repository ở settings; repository khai báo thêm ở project bị bỏ qua và Gradle cảnh báo. |
| `RepositoriesMode.FAIL_ON_PROJECT_REPOS` | Bất kỳ repository dependency khai báo trực tiếp ở project (kể cả do plugin bổ sung) có thể khiến build lỗi; mục tiêu là enforce nguồn từ settings. |

Ví dụ dùng chế độ ưu tiên settings trong Kotlin:

```kotlin
dependencyResolutionManagement {
    repositoriesMode.set(
        org.gradle.api.initialization.resolve.RepositoriesMode.PREFER_SETTINGS
    )
    repositories {
        mavenCentral()
    }
}
```

**Không nhầm policy này với pluginManagement:** `repositoriesMode` là chính sách dành cho **dependency repositories của project**. Plugin repositories được cấu hình qua `pluginManagement` ở ngữ cảnh settings, không có một `repositoriesMode` tương đương để module “override” như dependency repository.

Nếu bật `FAIL_ON_PROJECT_REPOS` rồi copy một đoạn từ bài hướng dẫn khác:

```kotlin
// app/build.gradle.kts — ví dụ KHÔNG được dùng với FAIL_ON_PROJECT_REPOS:
repositories {
    mavenCentral()
}
```

Gradle có thể báo lỗi policy dù `mavenCentral()` cũng đã khai báo trong settings. Đó là **lỗi khai báo repository sai nơi**, không phải chứng cứ rằng Maven Central không tồn tại.

## 7. Ví dụ hoàn chỉnh chạy được: Java 17 + plugin tích hợp + thư viện ngoài

Ví dụ này cho thấy rõ: **plugin Java đến từ Gradle**, còn **Commons Lang3 được resolve từ Maven Central** theo settings. Chạy khi máy có Gradle Wrapper/JDK phù hợp và có quyền truy cập Maven Central (hoặc artifact đã có trong cache).

### 7.1. Cấu trúc thư mục

```text
repo-separation-lab/
├── settings.gradle.kts
├── app/
│   ├── build.gradle.kts
│   └── src/main/java/demo/App.java
└── gradle/ ...                    (nếu đã có Gradle Wrapper)
```

`gradlew`/`gradlew.bat` và `gradle/wrapper` là thành phần Wrapper, sinh sẵn trong repository hoặc tạo bằng lệnh `gradle wrapper` nếu máy đã cài Gradle. Chọn một bản Wrapper hỗ trợ JDK 17 và Kotlin DSL hiện dùng; không giả định mọi phiên bản Gradle cũ đều chạy được với JDK 17.

### 7.2. settings.gradle.kts

```kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(
        org.gradle.api.initialization.resolve.RepositoriesMode.FAIL_ON_PROJECT_REPOS
    )
    repositories {
        mavenCentral()
    }
}

rootProject.name = "repo-separation-lab"
include(":app")
```

### 7.3. app/build.gradle.kts

```kotlin
plugins {
    id("application")
}

application {
    mainClass.set("demo.App")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
```

**Không có `repositories { ... }` trong `app/build.gradle.kts`**, vì policy ở settings là `FAIL_ON_PROJECT_REPOS`. Plugin `application` có sẵn trong Gradle và cung cấp Java support, configuration `implementation` cùng task `run`.

### 7.4. app/src/main/java/demo/App.java

```java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        String name = StringUtils.capitalize("gradle");
        System.out.println("Library says: " + name);
    }
}
```

Ví dụ sử dụng API thật của Commons Lang3. Để **biên dịch độc lập với Gradle bằng javac**, phải đưa JAR `commons-lang3-3.17.0.jar` hợp lệ vào classpath, ví dụ trên macOS/Linux khi bạn đã có file JAR ở thư mục `lib`:

```bash
mkdir -p out
javac -cp lib/commons-lang3-3.17.0.jar -d out app/src/main/java/demo/App.java
java -cp "out:lib/commons-lang3-3.17.0.jar" demo.App
```

Ở Windows, dùng classpath separator `;` thay dấu `:`. Không có JAR ở `lib` thì **không thể chạy các lệnh javac trên nguyên trạng**; phần chính của bài là Gradle tự tải dependency theo repository, còn đoạn javac giúp bạn thấy rằng Java compiler cũng cần cùng classpath.

### 7.5. Chạy Gradle

Từ root:

```bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:compileJava
./gradlew -q :app:run
./gradlew :app:build
```

Trên Windows dùng `gradlew.bat`. `:app:dependencies` hiển thị cây dependency và giúp thấy Commons Lang3 trong classpath. Gradle sẽ resolve/download module từ Maven Central khi cần (hoặc dùng artifact đã có trong cache).

**Stdout của chương trình từ `:app:run`:**

```text
Library says: Gradle
```

`-q` làm gọn log Gradle; phần output ở trên là do `System.out.println` trong Java in ra, không phải log cứng của Gradle. Nếu mạng bị chặn hoặc artifact không có trong cache, build cần repository proxy/mirror phù hợp; **không** sửa lỗi bằng cách đưa `mavenCentral()` vào `pluginManagement`.

### 7.6. Bản Groovy tương đương

Tạo `settings.gradle` thay cho `settings.gradle.kts`:

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(
        org.gradle.api.initialization.resolve.RepositoriesMode.FAIL_ON_PROJECT_REPOS
    )
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'repo-separation-lab'
include 'app'
```

Tạo `app/build.gradle` thay cho `app/build.gradle.kts`:

```groovy
plugins {
    id 'application'
}

application {
    mainClass = 'demo.App'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
```

File Java giữ nguyên, và output `Library says: Gradle` vẫn giống nhau. Không giữ hai bản settings hoặc hai bản build script active trong cùng vị trí rồi phụ thuộc vào thứ tự Gradle tự chọn; hãy chỉ dùng một DSL cho mỗi script trong bài tập.

## 8. Ví dụ plugin bên ngoài: muốn tải được phải đặt repository đúng chỗ

Phần trước dùng core plugin `application`, nên nó chưa buộc Gradle tải plugin ngoài. Để thực sự quan sát plugin repository, hãy xem hai cấu hình **độc lập** sau.

### Trường hợp A: có dependency repository nhưng không có plugin repository cần thiết

**settings.gradle.kts — tình huống sai khi yêu cầu plugin nội bộ:**

```kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        // Thiếu repository nội bộ chứa plugin com.acme.gradle-quality.
    }
}

dependencyResolutionManagement {
    repositories { mavenCentral() }
}
```

**build.gradle.kts — plugin giả định chỉ có ở repository nội bộ:**

```kotlin
plugins {
    id("com.acme.gradle-quality") version "2.1.0"
}
```

Plugin `com.acme.gradle-quality` là **ID minh họa**, không phải plugin được xác nhận đã xuất bản. Nếu plugin ấy chỉ có trong một kho riêng, cấu hình Maven Central cho dependency **không thể tự sửa lỗi plugin not found**. Hãy bổ sung repository plugin phù hợp vào `pluginManagement.repositories` và bảo đảm plugin marker/metadata hoặc cơ chế ánh xạ đúng.

### Trường hợp B: có plugin repository nhưng không có dependency repository

**settings.gradle.kts:**

```kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = "dependency-repo-missing"
```

**build.gradle.kts:**

```kotlin
plugins {
    id("java")
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
```

Khi Gradle cần resolve `compileClasspath`, **không có** `Project.repositories` hay `dependencyResolutionManagement.repositories` nào được khai báo cho module Commons Lang3. Do đó một yêu cầu compile sử dụng thư viện ngoài sẽ không tìm được module. `gradlePluginPortal()` ở pluginManagement không cung cấp nguồn dependency cho `implementation`.

Cách sửa là thêm repository **cho dependency**:

```kotlin
repositories {
    mavenCentral()
}
```

Hoặc khai báo tập trung ở `dependencyResolutionManagement.repositories` trong settings; với mode `FAIL_ON_PROJECT_REPOS` thì **phải chọn cách tập trung ở settings**.

### Trường hợp C: plugin có thật trong Gradle Plugin Portal

Ví dụ một plugin được xuất bản trên Plugin Portal là `io.github.ben-manes.versions`, dùng để xem cập nhật dependency. Một phiên bản có thể kiểm tra tại [Gradle Plugin Portal](https://plugins.gradle.org/plugin/io.github.ben-manes.versions/0.65.0) là `0.65.0`:

```kotlin
plugins {
    id("io.github.ben-manes.versions") version "0.65.0"
}
```

Đoạn này là **minh họa riêng**; không cần thêm vào ví dụ Java ở mục 7. Để chạy cần mạng/cache và Gradle version tương thích với plugin version đã chọn. Gradle sẽ tìm plugin qua `pluginManagement.repositories`; việc app có `repositories { mavenCentral() }` không quyết định nơi resolve plugin này.

## 9. Plugin marker không giống một module dependency thông thường

Giả sử repository Maven nội bộ đã có JAR implementation:

```text
com.acme.build:quality-plugin:2.1.0
```

Điều đó **không có nghĩa** đoạn sau sẽ tự hoạt động:

```kotlin
plugins {
    id("com.acme.quality") version "2.1.0"
}
```

Với plugin DSL, Gradle cần cách ánh xạ **plugin ID + version** tới module implementation. Các phương án thông dụng:

1. **Publish plugin marker** tương ứng khi xuất bản plugin bằng cơ chế Gradle Plugin Development Plugin / cơ chế xuất bản chính thức.
2. **Ánh xạ plugin request sang module** bằng `pluginManagement.resolutionStrategy` nếu repository chỉ có implementation module.
3. **Dùng plugin trong included build** qua `pluginManagement.includeBuild(...)` (khi build logic được tổ chức như plugin build nội bộ).
4. Với build cũ dùng `buildscript.dependencies.classpath(...)` + `apply(plugin = "...")`, phải xử lý repository của classpath đúng ngữ cảnh (`buildscript.repositories`), không gộp tùy ý với plugins DSL.

Ví dụ ánh xạ (chỉ là sơ đồ minh họa, cần artifact nội bộ thật):

**Kotlin — settings.gradle.kts:**

```kotlin
pluginManagement {
    repositories {
        maven {
            url = uri("https://repo.example.org/gradle-plugins")
        }
    }

    resolutionStrategy {
        eachPlugin {
            if (requested.id.id == "com.acme.quality") {
                useModule("com.acme.build:quality-plugin:${requested.version}")
            }
        }
    }
}
```

URL `repo.example.org` và plugin `com.acme.quality` là **giá trị giả định**, không phải địa chỉ có thể dùng ngay. Cần plugin implementation có metadata và lớp plugin đúng; `requested.version` cần được cung cấp bằng plugin request hoặc policy version tương ứng. Lời gọi `useModule` cho Gradle biết dùng tọa độ nào khi resolve plugin request. Đây là giải pháp cho **plugin resolution**, không làm thay đổi nơi Gradle tải `implementation` của ứng dụng.

## 10. buildscript.repositories: ngữ cảnh thứ ba của build logic cũ

Trước plugins DSL hiện đại, build script thường đặt plugin implementation lên **buildscript classpath** thủ công:

**Groovy DSL:**

```groovy
buildscript {
    repositories {
        mavenCentral()
    }

    dependencies {
        classpath 'com.acme.build:quality-plugin:2.1.0'
    }
}

apply plugin: 'com.acme.quality'
```

**Kotlin DSL:**

```kotlin
buildscript {
    repositories {
        mavenCentral()
    }

    dependencies {
        classpath("com.acme.build:quality-plugin:2.1.0")
    }
}

apply(plugin = "com.acme.quality")
```

Các tọa độ `com.acme...` đều là **minh họa**. Ví dụ chỉ chạy nếu JAR plugin thực sự được publish vào repository phù hợp và plugin ID chính xác.

Ở đây, `buildscript.repositories` giải quyết **module dependency cho classpath của script**. Nó khác cả `pluginManagement.repositories` (phục vụ plugins DSL) lẫn `repositories` của Project (phục vụ `implementation`/`testImplementation`). Việc dùng legacy classpath không tạo thêm repository cho module dependencies của chương trình Java.

**Khuyến nghị:** với plugin hỗ trợ plugins DSL và model hiện đại, ưu tiên khai báo `plugins { ... }` kết hợp `pluginManagement.repositories`. Đừng chuyển một build cũ sang plugins DSL bằng cách chỉ đổi `apply(plugin=...)` thành `plugins { id(...) }` mà quên plugin marker và nơi tìm plugin.

### buildSrc và included builds cũng có phạm vi repository riêng

`buildSrc` hoặc included build chứa build logic được đánh giá như **một build riêng**, có settings/build scripts riêng và có thể cần repositories riêng để resolve dependencies của chính nó. Danh sách repository của main build **không phải một danh sách toàn cục đảm bảo tự áp cho mọi included build**.

Để tạo plugin nội bộ trong composite build, Gradle có thể dùng `pluginManagement { includeBuild("build-logic") }` khi build logic được cấu hình thích hợp. Cách này khác việc khai báo `maven { url = ... }`: plugin có thể được cung cấp bởi **một build tham gia composite**, không nhất thiết download từ Maven.

## 11. Ví dụ multi-project: vì sao mỗi module có thể bị lỗi khác nhau?

Giả sử build có root, `:app` và `:core`. Nếu mỗi project tự khai báo repository:

```kotlin
// app/build.gradle.kts
plugins { id("application") }

repositories { mavenCentral() }

dependencies {
    implementation(project(":core"))
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
```

mà `:core` có dependency ngoài nhưng không khai báo repository tương ứng, build của `:core` có thể lỗi dù `:app` đã có Maven Central. Repository của một project không mặc nhiên trở thành repository của mọi project con.

Một cách quản trị tốt hơn cho team là tập trung dependency repositories ở settings:

```kotlin
// settings.gradle.kts
pluginManagement {
    repositories { gradlePluginPortal() }
}
dependencyResolutionManagement {
    repositoriesMode.set(
        org.gradle.api.initialization.resolve.RepositoriesMode.FAIL_ON_PROJECT_REPOS
    )
    repositories { mavenCentral() }
}
rootProject.name = "multi-module"
include(":app", ":core")
```

Đây là một **đoạn cấu hình thay thế**, không ghép đồng thời với `repositories { mavenCentral() }` của `:app` ở trên nếu bật `FAIL_ON_PROJECT_REPOS`. Các project vẫn chọn dependency của mình trong `dependencies`, nhưng danh sách repository phục vụ external module resolution do settings quản trị.

**Phân biệt thêm:** project dependency `implementation(project(":core"))` không cần một Maven repository để tìm project `:core`, nhưng `:core` có thể cần repository để resolve các **external dependencies của chính nó**.

## 12. Repositories cho publish không phải nơi để download

Khi áp dụng `maven-publish`, một project có thể khai báo đích xuất bản:

```kotlin
plugins {
    id("maven-publish")
}

publishing {
    repositories {
        maven {
            url = uri("https://repo.example.org/releases")
        }
    }
}
```

`https://repo.example.org/releases` là URL giả định. Khối `publishing.repositories` cung cấp **đích upload** (khi chạy task publish thích hợp và có quyền truy cập), không tự bổ sung repository cho `dependencies` hay `plugins`.

Đừng “chữa” lỗi dependency not found bằng cách đặt repository vào `publishing`; nó phục vụ chiều ngược lại. Nếu cùng một kho nội bộ vừa chứa dependency vừa nhận publish, cần khai báo tại **đúng ngữ cảnh** cho từng vai trò.

## 13. Lỗi phổ biến và chẩn đoán theo triệu chứng

| Thông báo/hiện tượng | Nguyên nhân có thể | Cách xử lý đúng |
| --- | --- | --- |
| `Plugin [id: '...', version: '...'] was not found` | Plugin repositories thiếu kho, plugin marker không có, sai ID/version hoặc mạng/quyền. | Kiểm tra `pluginManagement.repositories` trong settings; xác nhận plugin ID/version và marker/mapping. |
| `Could not find group:module:version` khi compile | Repository dependency chưa được khai báo hoặc không có artifact/version. | Kiểm tra `Project.repositories` / `dependencyResolutionManagement.repositories` và tọa độ dependency. |
| `plugins { id("java") }` chạy được, plugin ngoài thất bại | Java là core plugin, không cần tải; external plugin mới cần repository. | Kiểm tra nơi resolve plugin ngoài, đừng dựa vào kết quả core plugin. |
| Có `gradlePluginPortal()` nhưng `implementation` vẫn not found | Plugin repository không dùng cho project module dependencies. | Thêm repository dependency phù hợp như `mavenCentral()` ở đúng ngữ cảnh. |
| Có `mavenCentral()` ở project nhưng plugin not found | Repository project không dùng cho plugins DSL. | Cấu hình `pluginManagement.repositories` đúng nơi. |
| `Build was configured to prefer settings repositories ...` | Một project/plugin cố thêm repository khi policy ở settings không cho phép/ưu tiên. | Xác định `repositoriesMode` và bỏ/chuyển khai báo repository project theo policy. |
| Cùng artifact có ở hai repository nhưng build lấy bản bất ngờ | Thứ tự repository, metadata hoặc filter chưa rõ. | Rà thứ tự, nội dung, metadata, `content`/`exclusiveContent`. |
| Plugin JAR tồn tại ở Maven nội bộ nhưng plugins DSL không thấy | Thiếu plugin marker hoặc mapping plugin ID → implementation. | Publish marker hoặc dùng `pluginManagement.resolutionStrategy` phù hợp. |
| Dùng `buildscript.repositories` nhưng Java compile không thấy dependency | Classpath của build logic khác classpath của mã Java. | Khai báo `dependencies { implementation(...) }` và repository project. |
| CI lỗi, máy cá nhân chạy được | Caches, credentials, proxy, offline mode hoặc repository local khác nhau. | Thử trên clean checkout, kiểm tra URL/TLS/quyền và dependency graph. |
| Plugin tải thành công nhưng task Java tải library thất bại | Plugin phase và module resolution là hai đường độc lập. | Chẩn đoán từng kho, không thay sai repository. |
| Đăng nhập repository bị 401/403 | Credentials thiếu hoặc không đủ quyền. | Dùng credential mechanism an toàn; không hard-code secret trong script/Git. |

### Đọc đúng loại lỗi thay vì sửa ngẫu nhiên

1. **Lỗi xảy ra lúc đọc/apply `plugins { }`?** Kiểm tra Plugin Portal, pluginManagement, ID/version, marker, mapping, included build.
2. **Lỗi khi Gradle resolve `compileClasspath`, `runtimeClasspath` hoặc `testRuntimeClasspath`?** Kiểm tra `dependencies`, project repositories, settings repositories, transitive dependencies và policy.
3. **Lỗi khi cấu hình `buildscript classpath`?** Kiểm tra `buildscript.dependencies.classpath` cùng `buildscript.repositories`.
4. **Lỗi khi publish?** Kiểm tra `publishing.repositories`, credentials, repository endpoint và task publish; không pha với resolver của project.

## 14. Lệnh kiểm tra thực tế và giới hạn của chúng

Với ví dụ ở mục 7:

```bash
./gradlew --version
./gradlew projects
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
./gradlew :app:compileJava --info
./gradlew -q :app:run
```

- `--version` giúp xác định Gradle và JVM của Wrapper.
- `projects` xác nhận root, `:app` và tên project.
- `dependencies --configuration runtimeClasspath` hiển thị module dependency đang được giải quyết, không hiển thị toàn bộ **plugin resolution repositories**.
- `dependencyInsight` giúp giải thích phiên bản module được chọn và đường dependency, nhưng không trực tiếp khẳng định URL repository đã sử dụng cho mọi artifact.
- `--info` có thể cung cấp thông tin bổ sung về resolution/compile; dùng `--debug` khi cần điều tra sâu và **tránh chia sẻ log chứa URL nội bộ, token hoặc credentials**.
- `--offline` buộc dùng dữ liệu đã có trong cache; nếu clean checkout/offline build lỗi, đó không đủ để kết luận repository config sai. Cần thử trong môi trường có mạng được phép truy cập.

Với plugin resolution, dùng `./gradlew help --info` hoặc lệnh có plugin cần dùng để quan sát lỗi ở giai đoạn cấu hình. Plugin đã cache từ trước có thể che khuất việc repository đang cấu hình sai; muốn tái hiện “first use” hãy kiểm tra trong môi trường/cache kiểm thử riêng có kiểm soát, **không xóa tùy tiện cache dùng chung**.

### Bài tập tự kiểm tra

Đánh giá những câu sau:

1. “Đã đặt `mavenCentral()` trong `pluginManagement.repositories` nên `implementation("g:a:v")` sẽ resolve từ Maven Central.” — **Sai**; đây là repository phục vụ plugin resolution, không phải module dependency của project.
2. “Đã đặt `mavenCentral()` trong `dependencyResolutionManagement.repositories` nên plugin ngoài từ Plugin Portal chắc chắn tìm thấy.” — **Sai**; cần nguồn plugin thích hợp hoặc nguồn plugin đã có trong build.
3. “`id("java")` không cần tải plugin ngoài, nên build có thể áp dụng Java plugin dù plugin repository không có Internet.” — **Đúng**; Java là core plugin.
4. “`FAIL_ON_PROJECT_REPOS` có thể gây lỗi nếu project thêm `repositories { mavenCentral() }`.” — **Đúng**; policy yêu cầu repository dependency tập trung ở settings.
5. “Một plugin marker trong plugin repository có thể ánh xạ plugin ID sang module implementation.” — **Đúng**; với plugin DSL, marker/mapping là phần thiết yếu của nhiều plugin bên ngoài.
6. “`buildscript.repositories` và `publishing.repositories` là cùng một thứ.” — **Sai**; một bên tải dependency cho buildscript classpath, một bên là đích upload.

## 15. An toàn, hiệu năng và khả năng tái lập

Quản lý repository đúng ngữ cảnh không chỉ giúp hết lỗi “not found”, mà còn có lợi cho build an toàn:

- **Giới hạn và kiểm soát nguồn:** chỉ đưa vào repository đã được phê duyệt; tùy môi trường dùng nội bộ mirror/Artifactory/Nexus, content filters và chính sách ở settings.
- **Không hard-code credentials:** dùng Gradle credentials API, Gradle properties hoặc cơ chế secret của CI; không commit token/mật khẩu vào source.
- **Giữ HTTPS/TLS khi phù hợp:** tránh transport không được bảo vệ; nếu môi trường yêu cầu HTTP nội bộ, cần phê duyệt rõ thay vì bật insecure protocol đại trà.
- **Giữ phiên bản cố định:** với plugin DSL và các dependency quan trọng, quản lý version theo chính sách và catalog; dynamic versions có thể làm build không tái lập.
- **Đừng lạm dụng `mavenLocal()`:** local Maven repository có thể chứa artifact khác nhau giữa máy người phát triển và CI; chỉ bật nếu có lý do xác định.
- **Tránh trộn build migration và repository migration:** chuyển nguồn plugin, đổi kho dependency và nâng plugin version đồng thời sẽ khó phân biệt lỗi.
- **Kiểm tra included builds/buildSrc:** các build con có scope riêng; phải xử lý repository của chính chúng khi chúng cần resolve dependencies.
- **Dùng Wrapper:** cùng Gradle/JDK giúp giảm biến thiên không liên quan khi chẩn đoán.

## 16. Tóm tắt để áp dụng

**Muốn tải plugin qua `plugins { }`?** Xem `pluginManagement.repositories` tại settings, plugin ID/version, marker và nơi host implementation.

**Muốn tải JAR ứng dụng qua `implementation` hoặc `testImplementation`?** Xem `Project.repositories` hoặc `dependencyResolutionManagement.repositories` và `RepositoriesMode`.

**Muốn tải plugin theo `buildscript.classpath` kiểu cũ?** Xem `buildscript.repositories`, không nhầm với hai loại trên.

**Muốn upload artifact?** Xem `publishing.repositories`, đó là chiều phát hành.

Đặc biệt, việc cấu hình cùng một URL (ví dụ Maven Central) ở hai khối **không làm hai khối trở thành một**: Gradle vẫn áp dụng danh sách repository theo đúng ngữ cảnh. Khi hiểu ranh giới này, bạn sửa lỗi plugin not found và dependency not found nhanh hơn, đồng thời kiểm soát nguồn artifact của cả tổ chức.

### Tài liệu tham khảo chính thức

- [Gradle — Working with Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html): plugin DSL, pluginManagement, kho plugin riêng, marker và cách áp dụng plugin.
- [Gradle — Declaring Repositories](https://docs.gradle.org/current/userguide/declaring_repositories_basics.html): phân biệt plugin repository và project dependency repository, thứ tự repository.
- [Gradle — Centralizing Repository Declarations](https://docs.gradle.org/current/userguide/centralizing_repositories.html): `dependencyResolutionManagement` và `RepositoriesMode`.
- [Gradle — Securing Repositories](https://docs.gradle.org/current/userguide/securing_repositories.html): cấu hình repository an toàn và policy.
- [Gradle — Declaring Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies.html): external/project/file dependencies và configurations.
- [Gradle — Plugin Publishing](https://docs.gradle.org/current/userguide/publishing_gradle_plugins.html): xuất bản Gradle plugin và marker artifacts.
