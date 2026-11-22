# Tách kho dùng cho plugin khỏi kho dùng cho thư viện

Một Gradle build thường phải tải hai nhóm thành phần khác nhau: plugin dùng để mở rộng chính quá trình build và thư viện mà mã ứng dụng hoặc mã kiểm thử sử dụng. Hai nhóm này có thể được lưu trên cùng một máy chủ Maven, nhưng chúng thuộc hai phạm vi phân giải khác nhau. Gradle cung cấp cấu hình repository riêng cho plugin và cho dependency của project để nhóm kiểm soát nguồn tải, quyền truy cập và chính sách sử dụng rõ ràng.

Nếu khai báo nhầm repository, build có thể tìm thấy thư viện ứng dụng nhưng không tìm thấy plugin, hoặc ngược lại. Việc trộn mọi repository vào một block cũng khiến khó giới hạn nguồn plugin, khó áp dụng credential riêng và khó quản lý tập trung các dependency trong multi-project build.

## 1. Phân biệt plugin repository và dependency repository

Plugin là thành phần mở rộng Gradle. Ví dụ Java Plugin, Kotlin JVM Plugin, Spring Boot Plugin hoặc plugin nội bộ của tổ chức. Plugin có thể đăng ký task, cấu hình extension, thay đổi task graph và thêm dependency hoặc quy tắc build.

Thư viện là dependency mà project sử dụng trong compile/runtime/test. Ví dụ JUnit, Jackson, SLF4J hoặc thư viện nghiệp vụ nội bộ. Thư viện thường được khai báo trong khối `dependencies` với các configuration như `implementation`, `api`, `runtimeOnly` hoặc `testImplementation`.

| Phạm vi | Khai báo repository ở đâu? | Dùng để phân giải |
|---|---|---|
| Plugin DSL (`plugins {}`) | `pluginManagement.repositories` trong settings script | Plugin marker và implementation artifact của plugin. |
| Plugin classpath kiểu cũ (`buildscript {}`) | `buildscript.repositories` trong build script | Dependency được khai báo trong `buildscript.dependencies { classpath(...) }`. |
| Thư viện của project | `dependencyResolutionManagement.repositories` trong settings script hoặc `repositories` trong project build script | Dependency của các configuration như `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath`. |
| Dependency của build logic riêng | Repository của chính build logic đó | Thư viện mà convention plugin hoặc build logic cần để biên dịch/chạy. |

Hai phạm vi chính cần tách trong hầu hết dự án là `pluginManagement.repositories` và `dependencyResolutionManagement.repositories`. Khai báo `mavenCentral()` trong block này không tự động thêm nó vào block kia.

## 2. Repository dùng cho plugin DSL

Với cú pháp plugin hiện đại:

```kotlin
plugins {
    id("org.example.quality") version "1.2.0"
}
```

Gradle cần tìm plugin theo plugin ID và version. Các repository mà Gradle dùng cho quá trình này được khai báo trong `pluginManagement` của `settings.gradle` hoặc `settings.gradle.kts`.

Ví dụ Groovy DSL trong `settings.gradle`:

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        maven {
            name = 'companyPluginRepository'
            url = uri('https://repo.example.com/gradle-plugins')
        }
    }
}

rootProject.name = 'sample-app'
```

Ví dụ Kotlin DSL trong `settings.gradle.kts`:

```kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        maven {
            name = "companyPluginRepository"
            url = uri("https://repo.example.com/gradle-plugins")
        }
    }
}

rootProject.name = "sample-app"
```

`gradlePluginPortal()` thêm Gradle Plugin Portal vào danh sách repository cho plugin DSL. Repository Maven bổ sung có thể phục vụ plugin nội bộ hoặc plugin được phân phối qua repository riêng của tổ chức.

`pluginManagement {}` cần được đặt ở đầu settings script trước các cấu hình settings khác để Gradle có thể sử dụng chính sách này khi xử lý plugin. Các plugin được khai báo trong `plugins {}` của settings script và project build script đều được phân giải theo cấu hình plugin management thích hợp.

### 2.1. Plugin ID, marker artifact và implementation artifact

Plugin DSL không chỉ tìm một JAR theo tên plugin. Với cơ chế plugin marker, Gradle thường tìm một marker artifact theo tọa độ được tạo từ plugin ID và version. Marker này chỉ đến module chứa implementation của plugin.

Ví dụ với plugin ID `org.example.quality` và version `1.2.0`, marker module thường có tọa độ dạng:

```text
org.example.quality:org.example.quality.gradle.plugin:1.2.0
```

Sau khi tìm được marker, Gradle tiếp tục phân giải implementation artifact mà marker khai báo. Vì vậy, repository dành cho plugin cần chứa marker artifact và các artifact implementation/phụ thuộc cần thiết, hoặc được cấu hình để ánh xạ plugin ID sang module implementation.

Nếu repository nội bộ chỉ chứa JAR implementation mà không có marker, plugin DSL có thể báo không tìm thấy plugin dù JAR đã tồn tại. Có thể dùng `resolutionStrategy` để ánh xạ ID plugin sang module:

```groovy
pluginManagement {
    repositories {
        maven {
            url = uri('https://repo.example.com/gradle-plugins')
        }
        gradlePluginPortal()
    }

    resolutionStrategy {
        eachPlugin {
            if (requested.id.id == 'org.example.quality') {
                useModule("org.example.build:quality-gradle-plugin:${requested.version}")
            }
        }
    }
}
```

Ở ví dụ này, Gradle ánh xạ plugin ID sang module implementation `org.example.build:quality-gradle-plugin`. Repository phải chứa module đó và các dependency mà plugin cần. Nếu plugin ID có thể được phân phối bằng marker chuẩn, dùng marker thường dễ tương thích hơn với plugin DSL và công cụ quản lý plugin.

### 2.2. Quản lý version mặc định của plugin

`pluginManagement.plugins` có thể khai báo version mặc định cho plugin ID. Project sau đó có thể dùng plugin mà không lặp version:

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        maven {
            url = uri('https://repo.example.com/gradle-plugins')
        }
    }

    plugins {
        id 'org.example.quality' version '1.2.0'
        id 'org.jetbrains.kotlin.jvm' version '2.0.21'
    }
}
```

Trong project:

```groovy
plugins {
    id 'java'
    id 'org.example.quality'
    id 'org.jetbrains.kotlin.jvm'
}
```

Cách này giúp tập trung version plugin ở settings script, đặc biệt hữu ích khi nhiều subproject dùng cùng plugin. Nó chỉ quản lý version plugin; version thư viện ứng dụng vẫn thuộc dependency management.

## 3. Repository dùng cho thư viện và dependency của project

Thư viện mà project dùng được phân giải từ repository khai báo trong phạm vi dependency resolution. Cấu hình truyền thống là block `repositories` trong `build.gradle` hoặc `build.gradle.kts`:

```groovy
repositories {
    mavenCentral()
    maven {
        url = uri('https://repo.example.com/maven-releases')
    }
}

dependencies {
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.2'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.0'
}
```

Các repository này được dùng để phân giải dependency của project. Chúng không tự trở thành repository của plugin DSL.

### 3.1. Quản lý repository tập trung trong settings

Trong build nhiều project, có thể khai báo repository dependency tập trung bằng `dependencyResolutionManagement` trong `settings.gradle`:

```groovy
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)

    repositories {
        mavenCentral()
        maven {
            name = 'companyLibraries'
            url = uri('https://repo.example.com/maven-releases')
        }
    }
}
```

Khi dùng `FAIL_ON_PROJECT_REPOS`, Gradle báo lỗi nếu project khai báo repository riêng trong build script. Điều này giúp mọi subproject dùng cùng chính sách repository được quản lý từ settings.

Các mode phổ biến:

| Mode | Hành vi |
|---|---|
| `PREFER_PROJECT` | Ưu tiên repository khai báo ở project; repository từ settings không áp đặt thay thế. Đây là mode mặc định. |
| `PREFER_SETTINGS` | Ưu tiên repository khai báo trong settings; repository khai báo ở project bị bỏ qua. |
| `FAIL_ON_PROJECT_REPOS` | Build thất bại nếu project thêm repository riêng, giúp enforcing centralized repository policy. |

Ví dụ Kotlin DSL:

```kotlin
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
        maven {
            name = "companyLibraries"
            url = uri("https://repo.example.com/maven-releases")
        }
    }
}
```

`dependencyResolutionManagement` quản lý repository dùng để resolve dependency của project trong build. Nó không thay thế `pluginManagement.repositories`, vì plugin cần được phân giải sớm trong quá trình cấu hình build.

## 4. Repository của buildscript kiểu cũ

Một số build cũ dùng `buildscript` để đưa plugin hoặc thư viện hỗ trợ vào classpath của build script:

```groovy
buildscript {
    repositories {
        mavenCentral()
        maven {
            url = uri('https://repo.example.com/legacy-build-tools')
        }
    }

    dependencies {
        classpath 'org.example:legacy-gradle-plugin:1.2.0'
    }
}

apply plugin: 'org.example.legacy'
```

Trong trường hợp này, `buildscript.repositories` được dùng để phân giải dependency khai báo trong `buildscript.dependencies`. Nó cũng không phải repository của thư viện ứng dụng được khai báo trong block `dependencies` bên ngoài.

Khi đọc một build cũ, cần phân biệt:

- `buildscript.repositories`: nơi tìm plugin/build logic classpath được khai báo trong `buildscript`.
- `repositories`: nơi tìm dependency của project.
- `pluginManagement.repositories`: nơi tìm plugin dùng plugin DSL.

Với build mới, nên ưu tiên plugin DSL và cấu hình `pluginManagement` để quản lý plugin rõ ràng. `buildscript` vẫn có thể cần trong migration hoặc plugin cũ chưa hỗ trợ plugin DSL.

## 5. Tổ chức repository theo vai trò

Một chính sách phổ biến là dùng nguồn riêng cho plugin nội bộ và thư viện nội bộ, đồng thời dùng repository công khai phù hợp cho dependency bên ngoài.

Ví dụ cấu trúc:

```text
Gradle build
├── pluginManagement.repositories
│   ├── Internal Gradle Plugins
│   └── Gradle Plugin Portal
│
└── dependencyResolutionManagement.repositories
    ├── Internal Maven Releases
    └── Maven Central
```

Repository plugin có thể chứa:

- Plugin nội bộ dùng chung cho các project.
- Plugin third-party không được lấy từ Plugin Portal.
- Marker artifact và implementation artifact của plugin.
- Các dependency mà implementation plugin cần.

Repository thư viện có thể chứa:

- Thư viện Java/Kotlin của ứng dụng.
- Thư viện test và runtime.
- Artifact nội bộ được publish bởi các team.
- BOM/platform và dependency metadata liên quan.

Một máy chủ Artifactory, Nexus hoặc repository manager nội bộ có thể phục vụ cả hai nhóm. Điều quan trọng là Gradle vẫn cấu hình hai scope riêng, với nội dung được lọc và quyền truy cập phù hợp. Cùng một URL xuất hiện ở cả hai scope không làm hai scope trở thành một.

## 6. Giới hạn repository bằng content filters

Nếu một repository chỉ được phép cung cấp một nhóm module nhất định, hãy khai báo content filter. Việc này giúp tránh Gradle tìm cùng một module ở nhiều nguồn không mong muốn và làm rõ nguồn sở hữu artifact.

Ví dụ trong dependency repositories:

```groovy
dependencyResolutionManagement {
    repositories {
        maven {
            name = 'internalLibraries'
            url = uri('https://repo.example.com/maven-releases')
            content {
                includeGroupByRegex 'com\\.example(\\..*)?'
            }
        }

        mavenCentral()
    }
}
```

Trong ví dụ, repository nội bộ chỉ được dùng để tìm group `com.example` và các group con theo regex; dependency thuộc group khác sẽ được tìm ở repository còn lại.

Có thể lọc theo group hoặc module cụ thể:

```groovy
repositories {
    maven {
        url = uri('https://repo.example.com/maven-releases')
        content {
            includeGroup('com.example.platform')
            includeModule('com.example.tools', 'build-support')
        }
    }
}
```

### 6.1. `exclusiveContent` cho module chỉ được lấy từ một nguồn

Trong trường hợp một group phải được lấy độc quyền từ repository nội bộ, dùng `exclusiveContent`:

```groovy
dependencyResolutionManagement {
    repositories {
        exclusiveContent {
            forRepository {
                maven {
                    name = 'internalOnly'
                    url = uri('https://repo.example.com/maven-releases')
                }
            }
            filter {
                includeGroupByRegex 'com\\.example(\\..*)?'
            }
        }

        mavenCentral()
    }
}
```

`exclusiveContent` vừa giới hạn nội dung của repository được chọn, vừa loại các module khớp filter khỏi những repository khác trong cùng repository handler. Điều này hữu ích để tránh một module nội bộ vô tình được lấy từ public repository hoặc một dependency public giả mạo tên group nội bộ.

Có thể áp dụng cùng ý tưởng trong `pluginManagement.repositories` để bảo đảm plugin nội bộ chỉ được tìm ở nguồn đã phê duyệt:

```groovy
pluginManagement {
    repositories {
        exclusiveContent {
            forRepository {
                maven {
                    name = 'internalGradlePlugins'
                    url = uri('https://repo.example.com/gradle-plugins')
                }
            }
            filter {
                includeGroupByRegex 'com\\.example\\.gradle(\\..*)?'
            }
        }

        gradlePluginPortal()
    }
}
```

Khi dùng filter, cần chắc chắn group/module pattern khớp với tọa độ thực tế của marker và implementation artifact. Nếu filter chỉ bao gồm group implementation nhưng marker nằm ở group khác, plugin DSL vẫn có thể báo không tìm thấy plugin.

## 7. Thứ tự repository và tính nhất quán nguồn artifact

Gradle xét các repository theo danh sách được khai báo trong repository handler. Tuy nhiên, không nên dựa vào thứ tự đơn thuần để kiểm soát một module nội bộ thuộc nguồn nào. Khi module metadata được tìm thấy ở một repository, Gradle gắn kết quả đó với repository tương ứng và lấy artifact của module từ nguồn phù hợp; không nên kỳ vọng Gradle sẽ ghép metadata từ một repository với JAR cùng tọa độ từ repository khác.

Điều này có một số hệ quả:

- Nếu metadata tồn tại trong repository đầu tiên nhưng artifact bị thiếu, resolution có thể thất bại thay vì tìm artifact cùng tọa độ ở repository kế tiếp.
- Một module cùng tọa độ nhưng được publish khác nhau ở nhiều repository có thể gây khó tái lập và rủi ro supply chain.
- Repository content filter và `exclusiveContent` giúp xác định nguồn sở hữu module rõ ràng hơn việc chỉ đổi thứ tự repository.
- Tránh publish cùng tọa độ nhưng nội dung khác nhau ở nhiều repository.

Đối với thư viện nội bộ, nên có group namespace riêng và cấu hình chỉ lấy group đó từ repository nội bộ. Đối với plugin nội bộ, nên dùng namespace plugin ID/group rõ ràng và repository riêng trong plugin management.

## 8. Credential và bảo mật repository

Repository nội bộ có thể yêu cầu username/password, token hoặc cơ chế xác thực khác. Không ghi secret trực tiếp vào build script hoặc commit file chứa credential vào repository.

Ví dụ Groovy DSL dùng giá trị từ Gradle properties hoặc environment variables:

```groovy
dependencyResolutionManagement {
    repositories {
        maven {
            name = 'privateLibraries'
            url = uri('https://repo.example.com/maven-releases')
            credentials {
                username = providers.gradleProperty('repoUser')
                    .orElse(providers.environmentVariable('REPO_USER')).get()
                password = providers.gradleProperty('repoPassword')
                    .orElse(providers.environmentVariable('REPO_PASSWORD')).get()
            }
        }
    }
}
```

Có thể đặt giá trị cá nhân trong `~/.gradle/gradle.properties` hoặc cung cấp biến môi trường trong CI. File `gradle.properties` chứa secret không được commit; repository chỉ nên lưu tên property và hướng dẫn cấu hình.

Ví dụ file cấu hình cá nhân:

```properties
repoUser=build-reader
repoPassword=token-value-from-secret-store
```

Trong CI, nên lấy token từ secret manager của nền tảng CI và đưa vào environment variable. Dùng HTTPS cho repository có xác thực; hạn chế quyền chỉ đọc nếu build chỉ cần resolve dependency. Repository dùng để publish artifact cần credential và quyền ghi riêng, không nên dùng cùng token quyền rộng cho mọi tác vụ.

Nếu plugin repository và dependency repository dùng tài khoản khác nhau, hãy cấu hình credential trong đúng repository scope. Credential của repository thư viện không tự được sử dụng cho plugin repository chỉ vì URL giống nhau.

## 9. Centralize repository và kiểm soát repository ngoài ý muốn

Trong build nhiều module, repository khai báo rải rác trong từng `build.gradle` khiến mỗi project có thể resolve dependency từ nguồn khác nhau. Điều này làm khó kiểm soát nguồn artifact và khó tái hiện lỗi.

Một cấu hình tập trung có thể trông như sau:

```groovy
// settings.gradle
pluginManagement {
    repositories {
        gradlePluginPortal()
        maven {
            url = uri('https://repo.example.com/gradle-plugins')
        }
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
        maven {
            url = uri('https://repo.example.com/maven-releases')
        }
    }
}

rootProject.name = 'sample-app'
include 'app', 'service', 'shared'
```

Khi bật `FAIL_ON_PROJECT_REPOS`, các project con không được tự thêm repository. Nếu một module thực sự cần repository riêng, cần xem lại chính sách chung hoặc tách module/build phù hợp; tránh âm thầm thêm nguồn mới ở một subproject.

Repository centralization không có nghĩa mọi dependency phải ở cùng một server. Có thể khai báo nhiều repository trong settings, nhưng tập nguồn được phê duyệt được kiểm soát tại một điểm.

### 9.1. `mavenLocal()` và build tái lập

`mavenLocal()` cho phép Gradle lấy artifact từ Maven local repository của người dùng. Điều này hữu ích khi phát triển thư viện nội bộ trên máy cá nhân, nhưng có thể gây khác biệt giữa các máy vì nội dung local repository không được version control và có thể chứa artifact cũ.

Không nên thêm `mavenLocal()` vào repository list của build phát hành hoặc CI nếu không có nhu cầu rõ ràng. Nếu dùng trong quá trình phát triển, hãy giới hạn phạm vi, tránh để local artifact che khuất artifact đã publish và bảo đảm CI không phụ thuộc vào trạng thái local của một máy.

## 10. Repository của convention plugin và included build

Nhiều dự án đặt convention plugin trong một included build, thường có tên thư mục `build-logic`:

```groovy
// settings.gradle
pluginManagement {
    includeBuild('build-logic')
    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = 'sample-app'
```

Included build có settings và build script riêng. Dependency mà chính build logic cần để biên dịch plugin được resolve theo repository dependency của build logic đó. Plugin mà build logic sử dụng lại được resolve theo plugin management của build logic. Vì vậy, cần cấu hình repository cho cả build chính và included build nếu hai nơi có nhu cầu khác nhau.

Ví dụ cấu trúc:

```text
sample-app/
├── settings.gradle
├── build.gradle
├── app/
│   └── build.gradle
└── build-logic/
    ├── settings.gradle
    └── build.gradle
```

Trong `build-logic/settings.gradle`, có thể khai báo:

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        maven {
            url = uri('https://repo.example.com/gradle-plugins')
        }
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
        maven {
            url = uri('https://repo.example.com/maven-releases')
        }
    }
}
```

Nếu plugin nội bộ được phát triển trong included build, Gradle có thể dùng plugin đó trực tiếp từ source build thay vì tải plugin artifact đã publish. Tuy vậy, dependency bên thứ ba của build logic vẫn cần repository phù hợp.

## 11. Repository resolution khác với dependency verification

Chọn repository quyết định Gradle tìm component ở đâu. Dependency verification kiểm tra artifact tải về có khớp checksum hoặc chữ ký đã được cấu hình hay không. Hai cơ chế bổ sung cho nhau.

Một repository nội bộ được phê duyệt vẫn có thể chứa artifact bị thay đổi ngoài ý muốn. Ngược lại, checksum hợp lệ không tự chứng minh repository là nguồn phù hợp với chính sách của tổ chức. Với build cần kiểm soát supply chain, nên kết hợp:

- Repository allowlist và content filters để giới hạn nguồn.
- HTTPS và credential có quyền tối thiểu.
- Dependency verification để xác minh checksum/chữ ký.
- Dependency locking để giữ phiên bản đã resolve.
- Review thay đổi plugin và thư viện khi nâng cấp.

Gradle có thể tạo cấu hình verification metadata bằng lệnh:

```bash
./gradlew --write-verification-metadata sha256 help
```

Lệnh này tạo hoặc cập nhật metadata checksum cho dependency được resolve trong lần chạy. File verification metadata cần được review trước khi commit; không nên tự động chấp nhận checksum mới mà không xác minh nguồn gốc artifact.

## 12. Điều tra lỗi không tìm thấy plugin hoặc thư viện

Thông báo lỗi thường cho biết Gradle đang resolve trong scope nào. Hãy xác định scope trước khi thêm repository.

| Dấu hiệu | Phạm vi cần kiểm tra | Hướng xử lý |
|---|---|---|
| `Plugin [id: ..., version: ...] was not found` | Plugin DSL | Kiểm tra `pluginManagement.repositories`, plugin ID/version, marker artifact và resolution strategy. |
| Không resolve được `group:module:version` trong `dependencies` | Project dependency | Kiểm tra `dependencyResolutionManagement.repositories` hoặc `repositories` của project. |
| Lỗi resolve `classpath` trong buildscript | Legacy buildscript | Kiểm tra `buildscript.repositories` và dependency trong `buildscript.dependencies`. |
| Plugin marker có nhưng implementation module không tìm thấy | Plugin implementation | Kiểm tra repository chứa implementation và metadata của marker. |
| Chỉ một subproject không tìm thấy thư viện | Repository mode hoặc cấu hình project | Kiểm tra `repositoriesMode`, repository riêng và project path. |
| Máy cá nhân resolve được nhưng CI thất bại | Credential/network/proxy | Kiểm tra secret, quyền truy cập, TLS, DNS và mirror. |
| Artifact được tìm thấy nhưng tải file JAR thất bại | Repository artifact content | Kiểm tra artifact có thực sự tồn tại trong cùng repository và quyền đọc. |
| Plugin nội bộ không được tìm thấy dù đã thêm Maven repo | Plugin marker hoặc filter | Kiểm tra marker coordinates, implementation coordinates và content filter. |

### 12.1. Xem repository và dependency đang được dùng

Với thư viện của project:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Với buildscript classpath kiểu cũ:

```bash
./gradlew buildEnvironment
```

Với lỗi plugin DSL, tăng log khi cấu hình một task đơn giản:

```bash
./gradlew help --info
```

Log chi tiết có thể cho biết repository được truy cập và nguyên nhân request thất bại. Không phải lúc nào cũng có một lệnh `dependencies` thông thường để hiển thị đầy đủ plugin DSL graph; hãy dựa vào thông báo plugin resolution và log settings/plugin management.

### 12.2. Thứ tự điều tra

1. Xác định lỗi nhắc đến plugin ID, buildscript classpath hay module dependency.
2. Mở đúng settings/build script đang quản lý repository của scope đó.
3. Kiểm tra repository URL, tên, content filter và thứ tự khai báo.
4. Kiểm tra marker artifact và implementation artifact nếu lỗi nằm ở plugin DSL.
5. Kiểm tra credential, quyền đọc, proxy, TLS và kết nối mạng.
6. Kiểm tra repository có chứa metadata lẫn artifact tương ứng hay không.
7. Nếu dùng repository manager/mirror, kiểm tra cache và trạng thái đồng bộ của mirror.
8. Chạy lại với `--info` hoặc `--refresh-dependencies` khi cần kiểm tra metadata mới.

`--refresh-dependencies` làm mới thông tin dependency trong cache nhưng không sửa URL, credential hoặc content filter sai. Nếu repository không được khai báo trong đúng scope, refresh cache cũng không giúp Gradle tìm thấy artifact.

## 13. Một cấu hình tham khảo cho dự án nhiều module

Ví dụ sau thể hiện chính sách tách plugin repository và thư viện repository, đồng thời centralize dependency repositories:

```groovy
// settings.gradle
pluginManagement {
    repositories {
        exclusiveContent {
            forRepository {
                maven {
                    name = 'internalGradlePlugins'
                    url = uri('https://repo.example.com/gradle-plugins')
                }
            }
            filter {
                includeGroupByRegex 'com\\.example\\.gradle(\\..*)?'
            }
        }
        gradlePluginPortal()
    }

    plugins {
        id 'com.example.gradle.conventions' version '1.4.0'
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        exclusiveContent {
            forRepository {
                maven {
                    name = 'internalLibraries'
                    url = uri('https://repo.example.com/maven-releases')
                }
            }
            filter {
                includeGroupByRegex 'com\\.example(\\..*)?'
            }
        }
        mavenCentral()
    }
}

rootProject.name = 'sample-app'
include 'app', 'service', 'shared'
```

Trong project:

```groovy
// app/build.gradle
plugins {
    id 'java'
    id 'com.example.gradle.conventions'
}

dependencies {
    implementation 'com.example:domain-api:2.0.0'
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.2'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.0'
}
```

Ý nghĩa của cấu hình:

- Plugin nội bộ thuộc namespace `com.example.gradle` (bao gồm group marker `com.example.gradle.conventions` và group implementation) chỉ được tìm ở repository plugin nội bộ.
- Plugin công khai có thể được tìm ở Gradle Plugin Portal.
- Dependency nội bộ thuộc group `com.example` chỉ được tìm ở repository thư viện nội bộ.
- Dependency công khai được tìm ở Maven Central.
- `FAIL_ON_PROJECT_REPOS` ngăn subproject tự thêm repository ngoài chính sách tập trung.
- Plugin version mặc định được khai báo tập trung trong `pluginManagement.plugins`.

Các URL, group, plugin ID và version trong ví dụ là giá trị minh họa. Khi áp dụng, cần thay bằng tọa độ và endpoint thực tế của tổ chức, đồng thời bảo đảm marker và implementation artifact được publish đúng nơi.

## 14. Nguyên tắc quản lý repository

- **Tách scope:** khai báo repository plugin trong `pluginManagement`, thư viện trong `dependencyResolutionManagement` hoặc project `repositories`.
- **Quản lý tập trung:** với multi-project build, dùng settings repository management và chọn `repositoriesMode` theo chính sách.
- **Dùng plugin DSL:** ưu tiên `plugins {}` và plugin management cho plugin mới; giữ `buildscript.repositories` cho build logic kiểu cũ khi cần.
- **Hiểu marker artifact:** plugin DSL cần marker hoặc một mapping rõ ràng từ plugin ID đến implementation module.
- **Giới hạn nội dung:** dùng `content` filter và `exclusiveContent` để module nội bộ chỉ đến từ nguồn được phê duyệt.
- **Không dựa vào thứ tự để sửa nguồn:** xác định ownership bằng filter thay vì trông chờ repository đầu tiên luôn thắng.
- **Bảo vệ credential:** lấy secret từ Gradle properties cá nhân hoặc CI secret store; không commit token.
- **Hạn chế repository local:** chỉ dùng `mavenLocal()` khi thật sự cần cho phát triển và không để build phát hành phụ thuộc trạng thái máy cá nhân.
- **Kiểm soát supply chain:** kết hợp repository policy, dependency verification, locking và review nâng cấp.
- **Điều tra theo scope:** phân biệt plugin DSL, buildscript classpath và project dependency trước khi sửa cấu hình.

Tách repository cho plugin và thư viện giúp Gradle biết mỗi loại thành phần được phép lấy từ đâu. `pluginManagement.repositories` phục vụ plugin DSL; `dependencyResolutionManagement.repositories` hoặc project `repositories` phục vụ thư viện; `buildscript.repositories` phục vụ classpath build script kiểu cũ. Khi kết hợp repository centralization, content filters, credential an toàn và verification metadata, dự án có thể kiểm soát nguồn artifact tốt hơn, giảm lỗi resolve và giữ build nhất quán giữa máy phát triển, CI và môi trường phát hành.
