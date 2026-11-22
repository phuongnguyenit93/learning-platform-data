# Xác thực kho riêng bằng thông tin bí mật bên ngoài source trong Gradle

## 1. Bối cảnh và mục tiêu

Trong nhóm **Kho thư viện** của Gradle, một dự án Java có thể phải tải JAR nội bộ từ Nexus/Artifactory/Maven-compatible repository, giải quyết Gradle plugin riêng hoặc xuất bản artifact vào kho của công ty. Các kho đó yêu cầu xác thực bằng username/password, personal access token, service account hoặc HTTP header. Nếu credential được viết thẳng trong `build.gradle.kts`, `settings.gradle.kts`, `gradle.properties` đã commit hoặc một URL có user/password, secret có nguy cơ xuất hiện trong Git, bản fork, CI log, backup và hệ thống phân tích build.

Cách thiết kế đúng là **giữ tên kho, địa chỉ HTTPS và phương thức xác thực trong mã nguồn; cung cấp giá trị bí mật từ một nguồn bên ngoài repository**. Gradle hỗ trợ cơ chế nhận credential từ Gradle project properties và environment theo tên repository, nên không cần đọc mật khẩu bằng code thủ công.

Sau bài học này, bạn sẽ biết:

1. Định vị đúng repository cần xác thực: project dependencies, plugin resolution hay publishing.
2. Khai báo Maven repository an toàn với `PasswordCredentials` trong Kotlin DSL và Groovy DSL.
3. Giải thích cách `name = "corpMaven"` tạo quy ước `corpMavenUsername` / `corpMavenPassword`.
4. Lấy secret từ file riêng trong Gradle User Home, biến môi trường `ORG_GRADLE_PROJECT_*` hoặc secret manager trong CI.
5. Dùng token ở HTTP header bằng `HttpHeaderCredentials` và `HttpHeaderAuthentication` khi server không dùng Basic.
6. Lọc group được phép resolve, hạn chế nguy cơ rò rỉ tên dependency nội bộ và dependency confusion.
7. Phân biệt credential đọc thư viện với credential publish, plugin repository, Gradle Wrapper và proxy.
8. Xử lý 401/403/404/407, lỗi TLS và thiếu property mà không in credential.
9. Thiết kế giới hạn quyền, xoay vòng token và bảo vệ workflow CI.

**Quan trọng:** `https://repo.example.invalid/...` và `org.example.internal:shared-utils:1.2.3` trong ví dụ là **địa chỉ và artifact giả dành cho tài liệu**, không phải một repository có thể đăng nhập. Những mẫu Gradle script hợp lệ về cấu trúc, nhưng chỉ resolve được khi bạn thay bằng endpoint, group, artifact, version thật do quản trị hệ thống cấp và cung cấp credential hợp lệ theo cách an toàn.

## 2. Phân biệt các repository trước khi cấu hình

| Nhu cầu | Khối cấu hình | Tác dụng |
| --- | --- | --- |
| Tải dependency cho source/test | `repositories {}` trong `build.gradle.kts` hoặc `dependencyResolutionManagement.repositories` trong Settings | Resolve Maven/Ivy modules, JAR, POM, metadata |
| Tải plugin dùng trong `plugins {}` | `pluginManagement.repositories` trong `settings.gradle.kts` | Resolve Gradle plugin marker và implementation |
| Đẩy artifact lên server | `publishing.repositories` khi dùng `maven-publish` | Upload JAR/POM/Gradle metadata |
| Legacy buildscript classpath | `buildscript.repositories` | Resolve thư viện của buildscript cũ |
| Tải Gradle distribution của Wrapper | `gradle/wrapper/gradle-wrapper.properties` và cơ chế Wrapper | Tải chính Gradle, trước khi xử lý project script |

Một sự cố `plugins { id("org.example.internal.plugin") }` không nhất thiết được sửa bằng cách thêm repository trong `build.gradle.kts`. Plugin resolution có **scope riêng**. Tương tự, build đọc dependency thành công nhưng publish thất bại có thể do repository publish dùng một token khác, thường cần quyền ghi.

Quy trình hợp lý là **xác định thao tác Gradle đang làm**, sau đó mới chọn đúng repository và tên credential.

### 2.1. Sơ đồ luồng

~~~text
Gradle Wrapper
   +--> distributionUrl (xác thực Wrapper nếu cần)

settings.gradle.kts
   +--> pluginManagement.repositories (plugin)
   +--> dependencyResolutionManagement.repositories (library)

build.gradle.kts
   +--> repositories (project dependency, nếu không tập trung ở Settings)
   +--> publishing.repositories (upload artifact)
~~~

Đây là **bốn vị trí khác nhau**. Secret quản lý qua môi trường hoặc Gradle user properties có thể cùng nguồn cấp nhưng nên có **identity và quyền tách biệt**.

## 3. Nguyên tắc cơ bản: giữ bí mật ngoài source

Đối với private repository, một cấu hình tốt phải đáp ứng đồng thời:

- Source chỉ chứa URL HTTPS, repository name, kiểu authentication và quy tắc lọc nội dung.
- Secret không được commit, không nhúng vào URL, không in qua `println`/logging, không đưa vào task output.
- Credential được đưa vào Gradle qua cơ chế được hỗ trợ, như Gradle User Home `gradle.properties` hoặc các env vars `ORG_GRADLE_PROJECT_*`.
- Token **chỉ có quyền cần thiết**, theo mô hình read-only cho build và read/write riêng cho release.
- CI không cung cấp secret cho job chạy mã chưa được tin cậy, ví dụ PR từ fork chưa được review.
- Repository phải dùng HTTPS với chứng chỉ TLS đáng tin; không bật cấu hình bỏ an toàn truyền tải để tránh lỗi.
- Chỉ hỏi kho phù hợp về group artifact phù hợp; tránh để public repository thấy tọa độ package nội bộ.
- Có quy trình thu hồi và xoay vòng credential khi lộ.

**Ngoài source không đồng nghĩa đã mã hóa.** File ở `~/.gradle/gradle.properties` là văn bản thuần nếu người dùng tự điền credential. Nó tránh lộ vào Git, nhưng phải được bảo vệ bằng quyền hệ điều hành và chính sách quản lý thiết bị. Trên CI nên dùng secret store của nền tảng.

## 4. Cơ chế khuyến nghị: named PasswordCredentials

Gradle hỗ trợ `credentials(PasswordCredentials::class)` để tự tìm hai project property dựa trên **tên repository**.

Ví dụ:

~~~kotlin
maven {
    name = "corpMaven"
    url = uri("https://repo.example.invalid/maven/releases")
    credentials(PasswordCredentials::class)
}
~~~

Khi repo có `name = "corpMaven"`, Gradle tìm:

~~~text
corpMavenUsername
corpMavenPassword
~~~

Các giá trị có thể được cung cấp qua:

- `~/.gradle/gradle.properties`, chính xác hơn là `$GRADLE_USER_HOME/gradle.properties`.
- `ORG_GRADLE_PROJECT_corpMavenUsername` và `ORG_GRADLE_PROJECT_corpMavenPassword` trong environment của Gradle.
- Các nguồn Gradle project property khác được hỗ trợ, nhưng không dùng command-line `-P`/`-D` để đưa secret vào process arguments.

Cơ chế này khác với việc đặt hẳn:

~~~kotlin
// PHẢN VÍ DỤ: không đưa credential vào source.
credentials {
    username = "real-user"
    password = "real-password-or-token"
}
~~~

Trong cách khuyến nghị, **không có username hoặc password trong build script**. Gradle dùng tên property cụ thể để yêu cầu giá trị khi kho cần được sử dụng.

### 4.1. Tên property phân biệt hoa/thường

Nếu bạn đổi repository từ `corpMaven` thành `corp-maven`, quy tắc tự tìm credential cũng đổi theo tên mới. Vì vậy nên chọn tên ổn định, dễ đặt thành property hoặc biến môi trường. Với một dự án, thống nhất `corpMaven`, `corpPlugins`, `corpPublish` thay vì thay đổi tên vô tình giữa các file.

### 4.2. Chỉ yêu cầu credential khi cần

Typed named credentials không nhất thiết đòi đủ username/password khi bạn chạy một task **không dùng kho đó**. Chẳng hạn `./gradlew help` có thể thành công dù chưa cung cấp thông tin private Maven repository, nếu không có plugin hoặc dependency nào cần truy cập. Khi một task yêu cầu truy cập repo, Gradle có thể phát hiện property thiếu **trước khi chạy các task actions** và báo tên cần cung cấp.

Do vậy, `BUILD SUCCESSFUL` ở task `help` **không chứng minh** server đã xác thực thành công; kiểm tra bằng thao tác resolve thật khi cấu hình đã có endpoint và artifact chính xác.

## 5. Ví dụ Kotlin DSL hoàn chỉnh cho dependency riêng

**settings.gradle.kts**

~~~kotlin
rootProject.name = "private-repository-demo"
~~~

**build.gradle.kts**

~~~kotlin
import org.gradle.api.credentials.PasswordCredentials
import org.gradle.authentication.http.BasicAuthentication

plugins {
    `java-library`
}

repositories {
    mavenCentral {
        content {
            // Không hỏi kho public về group nội bộ.
            excludeGroup("org.example.internal")
        }
    }

    maven {
        name = "corpMaven"
        // Địa chỉ minh họa. Thay bằng HTTPS URL thật.
        url = uri("https://repo.example.invalid/maven/releases")

        // Gradle tự đọc corpMavenUsername / corpMavenPassword
        // từ Gradle project properties bên ngoài source.
        credentials(PasswordCredentials::class)

        // Chỉ kho này được hỏi về group nội bộ.
        content {
            includeGroup("org.example.internal")
        }

        // Dùng HTTP Basic khi server hỗ trợ và cần gửi
        // credential preemptively (không chờ challenge).
        authentication {
            create<BasicAuthentication>("basic")
        }
    }
}

dependencies {
    // Tọa độ minh họa, không có thật.
    implementation("org.example.internal:shared-utils:1.2.3")
}
~~~

**Những ý quan trọng:**

1. `java-library` tạo dependency configuration `implementation`.
2. `mavenCentral` được lọc để không resolve `org.example.internal` từ nguồn công khai.
3. Repository riêng được giới hạn chỉ nhận group nội bộ, tránh phải gửi các tọa độ public sang server không cần thiết.
4. `PasswordCredentials` dùng tên `corpMaven` để tìm hai property, không cần code đọc env riêng.
5. `BasicAuthentication` làm Gradle gửi credentials **preemptively**. Một số server trả HTTP 404 thay cho 401 nếu chưa có Basic header; cấu hình tường minh có thể cần khi server như vậy. Nếu server không sử dụng Basic, chọn cơ chế khác thay vì gửi sai scheme.
6. Tất cả URL, group, artifact là **placeholder**, thay theo hướng dẫn tổ chức; không đưa secret vào script.

### 5.1. Thư mục và lệnh kiểm tra

~~~text
private-repository-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
~~~

Giả định có Gradle Wrapper hợp lệ. Trên Linux/macOS:

~~~bash
./gradlew help --console=plain
~~~

Trên PowerShell:

~~~powershell
.\gradlew.bat help --console=plain
~~~

Nếu script tương thích với Wrapper, lệnh `help` có thể cấu hình build thành công **mà không cần tải private library**. Sau khi thay URL và dependency thật, kiểm tra:

~~~bash
./gradlew dependencies --configuration compileClasspath --console=plain
~~~

Gradle khi đó mới cần truy cập metadata của `shared-utils`. Nếu mô-đun, endpoint hoặc credential không hợp lệ, thao tác resolve thất bại; không có stdout xác thực “chuẩn” nào cho placeholder ở ví dụ.

**Không chạy `./gradlew build` trên mẫu chưa thay URL** rồi kỳ vọng Java compile từ dependency giả. Bài học hướng dẫn **cấu hình an toàn**; kiểm tra HTTP authentication thật cần repository và tài khoản hợp lệ.

## 6. Cấp credential trên máy cá nhân

### 6.1. Đặt ở Gradle User Home

Với cấu hình mặc định:

- macOS/Linux: `~/.gradle/gradle.properties`.
- Windows: `%USERPROFILE%\.gradle\gradle.properties`.
- Nếu đặt biến `GRADLE_USER_HOME`, file tương ứng là **`$GRADLE_USER_HOME/gradle.properties`**.

Ví dụ **nội dung minh họa** của file nằm **ngoài Git working tree**:

~~~properties
# Chỉ lưu trên máy được phép; không đưa file này vào Git.
corpMavenUsername=private-user-from-secret-manager
corpMavenPassword=private-read-token-or-password
~~~

Hai giá trị sau dấu bằng là *placeholder*, không phải credential được cấp. Trong thực tế hãy lấy credential từ cổng nội bộ/secret manager được tổ chức phê duyệt. Không paste secret vào chat hoặc tài liệu hướng dẫn.

Trên Unix-like OS, sau khi tạo file:

~~~bash
chmod 600 "$HOME/.gradle/gradle.properties"
~~~

Giúp giới hạn quyền đọc file với owner. Trên Windows dùng ACL, tài khoản máy riêng, thiết bị bảo mật và không đặt trong thư mục chia sẻ; không giả định chmod có tác dụng trên NTFS.

### 6.2. Vì sao không commit project gradle.properties?

Gradle cũng đọc `gradle.properties` tại root dự án, nhưng nếu bạn đưa:

~~~properties
corpMavenPassword=some-secret
~~~

vào file đang được Git track thì secret có thể nằm trong commit hiện tại và lịch sử Git. **Thêm `.gitignore` sau khi commit không xóa secret khỏi lịch sử.** Nếu lộ, cần thu hồi/rotate token, đánh giá những nơi đã truy cập, và xử lý lịch sử repository theo quy trình của tổ chức.

Có thể giữ **cấu hình không nhạy cảm** như repository URL, environment name hoặc feature flag trong source; credential phải tách riêng.

## 7. Cấp credential qua biến môi trường

Gradle ánh xạ biến có tiền tố `ORG_GRADLE_PROJECT_` thành project property.

Đối với repo tên `corpMaven`:

~~~text
ORG_GRADLE_PROJECT_corpMavenUsername -> corpMavenUsername
ORG_GRADLE_PROJECT_corpMavenPassword -> corpMavenPassword
~~~

### 7.1. Linux/macOS

Giả định `REPO_USER` và `REPO_PASSWORD` **đã được** secret manager hoặc môi trường tin cậy cấp:

~~~bash
export ORG_GRADLE_PROJECT_corpMavenUsername="$REPO_USER"
export ORG_GRADLE_PROJECT_corpMavenPassword="$REPO_PASSWORD"

./gradlew dependencies --configuration compileClasspath
~~~

Cách chỉ cấp cho một process:

~~~bash
ORG_GRADLE_PROJECT_corpMavenUsername="$REPO_USER" \
ORG_GRADLE_PROJECT_corpMavenPassword="$REPO_PASSWORD" \
./gradlew dependencies --configuration compileClasspath
~~~

Các lệnh này **không tạo credential**; nếu biến nguồn chưa có, biến đích có thể rỗng. Không echo nội dung nguồn hoặc dùng `set -x` trong job chứa secret.

### 7.2. Windows PowerShell

Giả định `$env:REPO_USER`, `$env:REPO_PASSWORD` đã được cấp an toàn:

~~~powershell
$env:ORG_GRADLE_PROJECT_corpMavenUsername = $env:REPO_USER
$env:ORG_GRADLE_PROJECT_corpMavenPassword = $env:REPO_PASSWORD

.\gradlew.bat dependencies --configuration compileClasspath
~~~

Sau khi dùng xong phiên terminal dành cho kiểm tra:

~~~powershell
Remove-Item Env:ORG_GRADLE_PROJECT_corpMavenUsername
Remove-Item Env:ORG_GRADLE_PROJECT_corpMavenPassword
~~~

Nếu biến đã mất thì `Remove-Item` có thể báo không tìm thấy; không phải lỗi Gradle. Không dùng `Write-Host` để kiểm tra password.

### 7.3. Ưu tiên project properties

Các nguồn Gradle project properties cấp build có thứ tự ưu tiên điển hình **cao → thấp**:

1. `-PpropertyName=value` trên CLI.
2. System property `-Dorg.gradle.project.propertyName=value`.
3. `ORG_GRADLE_PROJECT_propertyName`.
4. Gradle User Home `gradle.properties`, rồi build root, rồi Gradle installation theo quy tắc tương ứng.

Vì thế environment của CI có thể ghi đè một cấu hình local khi chạy trên runner. **Không dùng `-P`/`-D` cho secret** dù là nguồn ưu tiên cao: command line có thể bị lưu trong lịch sử, process listing, log CI hoặc công cụ quan sát.

Environment variables cũng có rủi ro trên máy/runner không đáng tin, nên phải kiểm soát những process có thể đọc môi trường. Tuy vậy chúng là kênh phù hợp để CI truyền bí mật từ secret manager mà **không sửa source**.

## 8. HTTP header token thay cho username/password

Một số server yêu cầu header như:

~~~text
Private-Token: <token>
~~~

hoặc:

~~~text
Authorization: Bearer <token>
~~~

Khi server quy định kiểu này, dùng **`HttpHeaderCredentials`** cộng **`HttpHeaderAuthentication`**, không giả định HTTP Basic luôn đúng.

**build.gradle.kts — mẫu repository thay thế cho Basic**:

~~~kotlin
import org.gradle.api.credentials.HttpHeaderCredentials
import org.gradle.authentication.http.HttpHeaderAuthentication

repositories {
    maven {
        name = "corpHeader"
        url = uri("https://repo.example.invalid/maven/token")

        // Gradle tự tìm hai property:
        // corpHeaderAuthHeaderName
        // corpHeaderAuthHeaderValue
        credentials(HttpHeaderCredentials::class)

        authentication {
            create<HttpHeaderAuthentication>("header")
        }

        content {
            includeGroup("org.example.internal")
        }
    }
}
~~~

Mẫu này phải được đặt đúng trong build script hoặc Settings, và cần repository thật trước khi sử dụng; không giữ đồng thời hai repository trùng group mà không có lý do.

Property names:

~~~text
corpHeaderAuthHeaderName
corpHeaderAuthHeaderValue
~~~

File Gradle User Home **minh họa**:

~~~properties
corpHeaderAuthHeaderName=Authorization
corpHeaderAuthHeaderValue=Bearer <private-access-token>
~~~

Trong CI, các biến môi trường là:

~~~text
ORG_GRADLE_PROJECT_corpHeaderAuthHeaderName
ORG_GRADLE_PROJECT_corpHeaderAuthHeaderValue
~~~

Ví dụ Linux khi secret đã nằm trong `REPO_TOKEN`:

~~~bash
export ORG_GRADLE_PROJECT_corpHeaderAuthHeaderName="Authorization"
export ORG_GRADLE_PROJECT_corpHeaderAuthHeaderValue="Bearer ${REPO_TOKEN}"

./gradlew dependencies --configuration compileClasspath
~~~

**Điểm quan trọng:** Header `Name` và `Value` phụ thuộc hợp đồng API của server. Nếu server yêu cầu `Private-Token` thì dùng `Private-Token` cùng giá trị token, không tự thêm `Bearer`. Nếu server yêu cầu `Authorization: Bearer ...`, cần giá trị gồm tiền tố `Bearer `. Không in biến `AuthHeaderValue`.

**Phân biệt:**

- `PasswordCredentials` là username/password. Một số server chấp nhận **username + token làm password**.
- `HttpHeaderCredentials` là name/value của header, thường dành cho token hoặc OAuth bearer.
- `HttpHeaderAuthentication` khai báo scheme tương ứng để client thực sự gửi header.
- Một biến Gradle property tên `token` tự nó **không khiến Gradle biết cách auth**.

## 9. Có thể lấy credential bằng Provider API trực tiếp không?

Có, đặc biệt khi tên biến môi trường của tổ chức không theo `ORG_GRADLE_PROJECT_`. Ví dụ:

~~~kotlin
import org.gradle.api.credentials.PasswordCredentials

repositories {
    maven {
        name = "customNamingRepo"
        url = uri("https://repo.example.invalid/maven/another")

        credentials(PasswordCredentials::class) {
            username = providers.environmentVariable(
                "INTERNAL_REPO_USERNAME"
            ).orNull

            password = providers.environmentVariable(
                "INTERNAL_REPO_PASSWORD"
            ).orNull
        }
    }
}
~~~

Đây là đoạn cấu hình repository **hợp lệ về cú pháp**, cần endpoint/biến thật. `.orNull` có thể trả null nếu property chưa được cấp; lỗi khi truy cập có thể kém rõ ràng hơn cơ chế tự tìm credential. Nếu không có yêu cầu tích hợp đặc biệt, ưu tiên:

~~~kotlin
name = "corpMaven"
credentials(PasswordCredentials::class)
~~~

để Gradle tự kiểm tra và báo tên property thiếu khi repository được sử dụng.

**Không tự `println(providers.environmentVariable(...).get())`** hoặc ghi giá trị vào Gradle log để xem có nhận đúng không. Xác nhận bằng một thao tác resolve thật khi endpoint và permission đã sẵn sàng.

## 10. Plugin repository cần cấu hình ở Settings

Khi code viết:

~~~kotlin
plugins {
    id("org.example.internal.convention") version "1.2.3"
}
~~~

Gradle có thể cần tải plugin marker và implementation **trước khi project script được đánh giá**. Repository trong `build.gradle.kts.repositories` không phải nơi giải quyết plugin này.

**settings.gradle.kts**:

~~~kotlin
pluginManagement {
    repositories {
        maven {
            name = "corpPlugins"
            url = uri("https://repo.example.invalid/gradle-plugins")
            credentials(PasswordCredentials::class)

            authentication {
                create<BasicAuthentication>("basic")
            }
        }

        gradlePluginPortal()
    }
}

rootProject.name = "plugin-repository-demo"
~~~

Property names:

~~~text
corpPluginsUsername
corpPluginsPassword
~~~

CI env:

~~~text
ORG_GRADLE_PROJECT_corpPluginsUsername
ORG_GRADLE_PROJECT_corpPluginsPassword
~~~

Khi plugin thật được apply trong build, ngay cả `./gradlew help` cũng có thể phải truy cập plugin repository, nên thiếu credential có thể làm build thất bại **trước các task actions**.

Nếu lỗi `Plugin ... was not found` xảy ra dù username/password đúng, kiểm tra plugin ID, version, plugin marker module, Gradle plugin implementation dependency, URL và repository order. Không tự kết luận mọi 404 là do mật khẩu sai.

### 10.1. Legacy buildscript

Dự án cũ có thể dùng:

~~~kotlin
buildscript {
    repositories {
        maven {
            name = "legacyBuildRepo"
            url = uri("https://repo.example.invalid/gradle-buildscript")
            credentials(PasswordCredentials::class)
        }
    }
}
~~~

`buildscript.repositories` dùng cho classpath của buildscript, khác cả pluginManagement lẫn dependencies của ứng dụng. Nếu project đã chuyển sang `plugins {}` hiện đại, nên ưu tiên cơ chế tương ứng thay vì trộn cả hai mà không cần.

## 11. Tập trung repository declarations trong settings.gradle.kts

Với nhiều subproject, việc mỗi module tự thêm URL/credential khó audit và dễ sai. Gradle hỗ trợ `dependencyResolutionManagement` trong Settings.

**settings.gradle.kts — một cấu hình mẫu độc lập**:

~~~kotlin
import org.gradle.api.initialization.resolve.RepositoriesMode

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)

    repositories {
        mavenCentral {
            content {
                excludeGroup("org.example.internal")
            }
        }

        maven {
            name = "corpMaven"
            url = uri("https://repo.example.invalid/maven/releases")
            credentials(PasswordCredentials::class)

            authentication {
                create<BasicAuthentication>("basic")
            }

            content {
                includeGroup("org.example.internal")
            }
        }
    }
}

rootProject.name = "multi-project-demo"
include(":app")
~~~

**app/build.gradle.kts**:

~~~kotlin
plugins {
    java
}

dependencies {
    implementation("org.example.internal:shared-utils:1.2.3")
}
~~~

Với `FAIL_ON_PROJECT_REPOS`, Gradle từ chối project repository do subproject (hoặc plugin) cố thêm vào ngoài Settings. Đây là một cơ chế kiểm soát hữu ích cho build có chính sách repository chặt chẽ; nếu một plugin hiện có khai báo project repository, cần điều chỉnh chiến lược thay vì tắt bảo vệ tùy tiện.

### 11.1. Vì sao cần group filter?

Một build có Maven Central và kho private **không lọc** có thể hỏi kho công khai về module nội bộ. Điều này làm lộ tên package và tăng khả năng dependency confusion. Hai bộ lọc có ý nghĩa:

~~~kotlin
// Public repository:
content {
    excludeGroup("org.example.internal")
}

// Private repository:
content {
    includeGroup("org.example.internal")
}
~~~

Nếu tổ chức có các subgroup như `org.example.internal.tools`, `includeGroup` chỉ khớp chính xác, không tự bao gồm mọi subgroup. Trên Gradle từ 8.1, cân nhắc `includeGroupAndSubgroups("org.example.internal")` và bộ lọc exclude tương ứng. Nếu artifact nội bộ **phải chỉ đi đến một repository**, tìm hiểu `exclusiveContent` theo tài liệu Gradle.

### 11.2. HTTPS là bắt buộc về mặt thiết kế

Gradle phiên bản hiện đại từ chối repository HTTP không bảo mật theo mặc định. Không bật `isAllowInsecureProtocol = true` để “giải quyết nhanh” lỗi nếu đang truyền credential: một bên trên mạng có thể đánh cắp token hoặc thay JAR/POM đang tải. Nếu mạng nội bộ chỉ có HTTP, đề nghị cấu hình TLS endpoint/reverse proxy với chứng chỉ được hệ thống tin cậy.

## 12. Publishing cần một repository và token ghi riêng

Đọc dependency nội bộ thường dùng token read-only; publish JAR/POM cần quyền write.

**build.gradle.kts — ví dụ dự án Java library được phép phát hành:**

~~~kotlin
import org.gradle.api.credentials.PasswordCredentials
import org.gradle.authentication.http.BasicAuthentication
import org.gradle.api.publish.maven.MavenPublication

plugins {
    `java-library`
    `maven-publish`
}

group = "org.example.internal"
version = "1.0.0"

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }

    repositories {
        maven {
            name = "corpPublish"
            url = uri("https://repo.example.invalid/maven/releases")
            credentials(PasswordCredentials::class)

            authentication {
                create<BasicAuthentication>("basic")
            }
        }
    }
}
~~~

Property names:

~~~text
corpPublishUsername
corpPublishPassword
~~~

CI env:

~~~text
ORG_GRADLE_PROJECT_corpPublishUsername
ORG_GRADLE_PROJECT_corpPublishPassword
~~~

Đây **không phải lệnh yêu cầu bạn publish artifact ngay**. Chỉ chạy job phát hành sau khi có repo URL thật, namespace/version hợp lệ, policy release, approval và token ghi được cấp đúng phạm vi. Có thể xem task để xác nhận cấu trúc:

~~~bash
./gradlew tasks --all --console=plain
~~~

Với ví dụ này, Gradle thường tạo task theo tên kiểu `publishMavenJavaPublicationToCorpPublishRepository`; tên thực tế phụ thuộc publication/repository. `publishToMavenLocal` chỉ ghi kho Maven cục bộ và không chứng minh remote publishing đã được xác thực.

**Khuyến nghị:** tên repo đọc và ghi khác nhau (`corpMaven` vs `corpPublish`) và token scope khác nhau. Token publish đừng cấp cho build kiểm tra PR thường ngày.

## 13. CI/CD: truyền secrets vào Gradle mà không đưa vào source

Mô hình:

~~~text
CI secret manager
        |
        v
Job đáng tin, quyền tối thiểu
        |
        | ORG_GRADLE_PROJECT_corpMavenUsername
        | ORG_GRADLE_PROJECT_corpMavenPassword
        v
Gradle named PasswordCredentials
        |
        v
HTTPS private Maven repository
~~~

Ví dụ một workflow **GitHub Actions** chỉ chạy khi chủ động yêu cầu, không tự cấp secret cho PR từ fork.

**.github/workflows/gradle.yml**:

~~~yaml
name: Build with private dependencies

on:
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    env:
      ORG_GRADLE_PROJECT_corpMavenUsername: ${{ secrets.PRIVATE_REPO_USER }}
      ORG_GRADLE_PROJECT_corpMavenPassword: ${{ secrets.PRIVATE_REPO_READ_TOKEN }}

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - name: Build
        run: ./gradlew build --console=plain
~~~

**Lưu ý:** `PRIVATE_REPO_USER`/`PRIVATE_REPO_READ_TOKEN` phải tồn tại trong secret store của GitHub Actions và được cấp đúng quyền. Các action versions ở ví dụ chỉ minh họa; tổ chức có thể yêu cầu pin action theo commit SHA, restrict network egress hoặc policy runner riêng. Đừng cho mã chưa review chạy trên runner chứa secret.

### 13.1. Tại sao không dùng -P cho password?

Không nên chạy:

~~~bash
# PHẢN VÍ DỤ: tuyệt đối không làm với secret thật.
./gradlew build -PcorpMavenPassword=SECRET_HERE
~~~

Giá trị có thể bị lộ qua shell history, process list, log pipeline hoặc tools ghi lại command line. Tương tự, không dùng URL chứa `user:password@host`.

Cấp env vars từ secret manager vẫn cần cách ly runner, tránh debug log, tránh scripts `env`, `printenv`, `set -x` hoặc xuất nguyên process environment.

### 13.2. Chỉ cấp secret cho những job cần

Một job chạy formatter hoặc kiểm tra file Markdown có thể không cần credential repo. Một job đọc dependency chỉ cần token read-only. Job publish cần token ghi riêng và có thể cần approval. Nếu pipeline chạy mã từ PR không đáng tin, tuyệt đối không tự cấp token publish để “test cho tiện”.

Dù nền tảng CI có tính năng mask secret, một script độc hại có thể truyền token ra endpoint ngoài. Bảo vệ **quyền thực thi mã trên runner** quan trọng không kém việc che log.

## 14. HTTP authentication và lý do server trả 401/403/404

| HTTP status / dấu hiệu | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| 401 Unauthorized | Token sai/hết hạn, chưa gửi credential, scheme auth không phù hợp | Kiểm tra loại credential, tên property, token và endpoint |
| 403 Forbidden | Token có thể đã xác thực nhưng không có quyền đọc/ghi nhóm artifact | Kiểm tra ACL, scope, namespace và policy server |
| 404 Not Found | Tọa độ/URL sai hoặc server che tài nguyên private bằng 404 | Kiểm tra repository path, Maven layout, group/artifact/version và cơ chế auth |
| 407 Proxy Authentication Required | Proxy yêu cầu auth riêng | Kiểm tra cấu hình proxy của CI/JVM, không nhầm với repository username |
| TLS handshake / PKIX | JDK không trust CA hoặc proxy làm TLS inspection | Cài CA đúng theo policy, kiểm tra truststore, không tắt HTTPS |
| Missing <repo>Username/Password | Gradle không tìm được project properties | Kiểm tra tên repo, chữ hoa/thường, biến có vào process và Gradle User Home |
| Không resolve plugin nội bộ | Kho private chỉ được khai báo trong dependency repositories | Bổ sung `pluginManagement.repositories` và xác minh plugin marker |
| Resolve dependency được, publish 403 | Credential publish khác hoặc thiếu quyền write | Kiểm tra `publishing.repositories`, tên corpPublish, quyền token |
| Máy cá nhân chạy được, CI lỗi | Local có user gradle.properties, CI thiếu secrets/mạng/JDK | So sánh cấu hình không nhạy cảm, không in credentials |

Không dùng HTTP status như bằng chứng duy nhất. Một số server cố tình trả 404 để che sự tồn tại của artifact mà tài khoản không được phép xem. Một số server dùng reverse proxy hoặc SSO khiến lỗi nằm ngoài Gradle script.

### 14.1. Preemptive HTTP Basic

Gradle mặc định có thể chờ server trả authentication challenge (401) trước khi gửi credential cho một số scheme. Nếu server không trả challenge chuẩn và tài liệu server xác nhận dùng Basic, khai báo:

~~~kotlin
authentication {
    create<BasicAuthentication>("basic")
}
~~~

giúp Gradle gửi Basic credential từ đầu. Chỉ áp dụng với HTTPS endpoint tin cậy. Nếu server đòi header `Authorization: Bearer ...` hoặc `Private-Token`, Basic không phải giải pháp; chọn HttpHeaderAuthentication.

### 14.2. Sai tên repo hoặc tên biến

Một biến `ORG_GRADLE_PROJECT_corpMavenPASSWORD` **không tương đương** với `ORG_GRADLE_PROJECT_corpMavenPassword`. Prefix bắt buộc đúng, phần tên property phải khớp chính xác với repo name và hậu tố `Username`/`Password` hoặc `AuthHeaderName`/`AuthHeaderValue`.

Nếu file ở một Gradle User Home khác với process đang dùng, Gradle cũng sẽ không thấy giá trị. Kiểm tra `GRADLE_USER_HOME` và quyền file mà **không hiển thị nội dung file**.

### 14.3. Sai scope và lifecycle

Lỗi xuất hiện lúc áp dụng plugin? → kiểm tra Settings `pluginManagement`.
Lỗi khi chạy `compileJava`, `test` hoặc `dependencies`? → kiểm tra project/dependency repositories.
Lỗi khi chạy `publish`? → kiểm tra publishing repositories và token write.
Lỗi khi chạy `./gradlew` ngay trước khi Gradle khởi động? → có thể là Wrapper distribution/proxy/TLS.

Không chỉnh tất cả khối repository cùng một lúc; xử lý nơi phát sinh lỗi trước.

## 15. Gradle Wrapper authentication là một cơ chế khác

Gradle Wrapper tải distribution từ `distributionUrl` trong `gradle/wrapper/gradle-wrapper.properties` **trước khi Gradle đánh giá project build script**. Do đó, khai báo:

~~~kotlin
repositories {
    maven {
        credentials(PasswordCredentials::class)
    }
}
~~~

không tự cấp credential để Wrapper tải Gradle distribution.

Nếu tổ chức tự host Wrapper distribution cần HTTP Basic, tài liệu Gradle mô tả các system properties chuyên dụng như `gradle.wrapperUser` và `gradle.wrapperPassword`. Cần cấp qua kênh bí mật được phê duyệt, tránh chứa user/password trong `distributionUrl`. Với Wrapper download qua proxy hoặc kho nội bộ, cũng phải bảo vệ TLS và verify distribution.

Phân biệt:

~~~text
Wrapper credential != Maven dependency credential
Plugin credential  != project dependency credential
Publish credential != read-only credential
Proxy credential   != repository credential
~~~

Chúng có thể do cùng tổ chức quản lý nhưng không nên tùy tiện dùng chung secret lâu dài.

## 16. Kiểm tra mà không hiển thị credential

### 16.1. Kiểm tra script và plugin configuration

~~~bash
./gradlew help --console=plain
~~~

Với build có plugin nội bộ trong `plugins {}`, lệnh này có thể đã cần plugin repository. Với dependency repository chưa được dùng, `help` có thể **không kiểm tra** xác thực.

### 16.2. Resolve một configuration thực sự

Khi đã cấu hình private URL và module thật:

~~~bash
./gradlew dependencies --configuration compileClasspath --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat dependencies --configuration compileClasspath --console=plain
~~~

Chỉ kiểm tra được nếu project có configuration `compileClasspath` phù hợp và một module được phép truy cập. Output hiển thị dependency graph hoặc lỗi resolve, không phải xác nhận rằng mọi quyền publish đều đúng.

### 16.3. Xem lý do dependency được chọn

~~~bash
./gradlew dependencyInsight \
  --dependency shared-utils \
  --configuration compileClasspath \
  --console=plain
~~~

Tên dependency là ví dụ; cần thay bằng module thực. Lệnh `dependencyInsight` giúp hiểu version selection, không thay thế kiểm thử quyền truy cập khi artifact chưa được dùng.

### 16.4. Không dùng debug log thiếu kiểm soát

`--info`, `--debug`, `--scan`, network traces hoặc log của plugin bên thứ ba có thể lộ thông tin nội bộ, path, URL và trong một số trường hợp giá trị nhạy cảm. Đừng in:

~~~kotlin
// PHẢN VÍ DỤ: tuyệt đối không đưa vào build script.
println(providers.gradleProperty("corpMavenPassword").get())
~~~

Nếu cần gửi log cho hỗ trợ kỹ thuật, kiểm tra và redact theo quy trình tổ chức. Đừng tin rằng một plugin luôn tự mask mọi secret.

## 17. Ví dụ Groovy DSL tương đương

Trong `build.gradle` dùng Groovy, cùng cơ chế named credentials:

~~~groovy
import org.gradle.api.credentials.PasswordCredentials
import org.gradle.authentication.http.BasicAuthentication

plugins {
    id 'java-library'
}

repositories {
    mavenCentral {
        content {
            excludeGroup 'org.example.internal'
        }
    }

    maven {
        name = 'corpMaven'
        url = uri('https://repo.example.invalid/maven/releases')
        credentials(PasswordCredentials)
        authentication {
            basic(BasicAuthentication)
        }
        content {
            includeGroup 'org.example.internal'
        }
    }
}

dependencies {
    implementation 'org.example.internal:shared-utils:1.2.3'
}
~~~

Tương ứng project properties `corpMavenUsername`, `corpMavenPassword`; dùng đúng Gradle User Home hoặc `ORG_GRADLE_PROJECT_*`. Groovy DSL không làm việc hard-code secret trở nên an toàn hơn.

Nếu server dùng header token, cơ chế tương đương trong Groovy là `credentials(HttpHeaderCredentials)` và `authentication { header(HttpHeaderAuthentication) }`, với các import tương ứng. Không trộn Basic và header auth trừ khi server thực sự hỗ trợ cả hai và bạn hiểu lựa chọn scheme.

## 18. Phân loại lỗi thường gặp

| Lỗi cấu hình | Hậu quả | Cách sửa |
| --- | --- | --- |
| Password/token trong source | Secret vào Git và có thể bị nhân bản | Di chuyển sang user properties/CI secrets và rotate token bị lộ |
| Chỉ thêm `.gitignore` sau khi đã commit secret | Secret vẫn còn trong history | Thu hồi secret, đánh giá phạm vi lộ, xử lý Git history theo policy |
| Dùng `-Ppassword=value` | Secret có thể nằm trên process command line | Dùng `ORG_GRADLE_PROJECT_*` hoặc user gradle.properties |
| Repo private đặt `http://` | Nguy cơ nghe lén và thay thế artifact | Chuyển HTTPS/truststore đáng tin |
| Dùng Basic cho endpoint Bearer-only | HTTP 401/404 | Dùng HttpHeaderCredentials/Authentication đúng tài liệu |
| Biến env sai chữ hoa/thường | Gradle báo missing property | Khớp đúng `name` và hậu tố property |
| Repo cho project deps không có trong pluginManagement | Plugin resolve fail | Khai báo plugin repository ở Settings |
| Credential read dùng để publish | Thường thiếu write permission | Token publish riêng, least privilege |
| Không lọc internal group | Tên artifact nội bộ có thể bị hỏi ở public Maven | Lọc group hoặc dùng exclusiveContent |
| Lạm dụng `--debug`/env dump | Có thể lộ credentials trong log | Chẩn đoán an toàn, redact, hạn chế truy cập log |
| `help` thành công nên nghĩ auth đã đúng | Private repository có thể chưa được dùng | Thử resolve module thật |
| Token hết hạn | Build CI fail đột ngột | Quy trình rotate và giám sát thời hạn |
| Token quyền quá rộng | Tăng hậu quả khi lộ | Token read/write tách biệt theo job |
| Dùng cache công cộng chứa file cấu hình bí mật | Nguy cơ secret lộ qua cache | Không cache file secret; rà soát paths/permissions |
| Dùng token production trên PR từ fork | Code không tin cậy có thể lấy token | Protected job/environment và không cấp secret |
| Hạ TLS verification để sửa PKIX | Mất bảo vệ kênh truyền | Sửa CA, truststore và proxy đúng cách |

## 19. Bài tập tự kiểm tra

**Câu 1:** Repo khai báo `name = "corpArtifacts"` và `credentials(PasswordCredentials::class)`. Gradle tìm properties nào?

**Đáp án:** `corpArtifactsUsername` và `corpArtifactsPassword`. Với CI, dùng `ORG_GRADLE_PROJECT_corpArtifactsUsername` và `ORG_GRADLE_PROJECT_corpArtifactsPassword`.

**Câu 2:** Có một token, nhất thiết dùng HttpHeaderCredentials không?

**Đáp án:** Không. Nếu server chấp nhận token như password trong HTTP Basic, dùng PasswordCredentials. Nếu server yêu cầu `Authorization: Bearer ...` hoặc `Private-Token`, dùng HttpHeaderCredentials đúng format.

**Câu 3:** Tải dependency bằng project `repositories` thành công nhưng plugin nội bộ báo không thấy. Vì sao?

**Đáp án:** Plugin resolution dùng Settings `pluginManagement.repositories`, không dùng project dependency repositories.

**Câu 4:** Có nên đặt password trong repo root `gradle.properties` rồi thêm file vào `.gitignore`?

**Đáp án:** Không nên. Nếu file đã track hoặc từng commit, `.gitignore` không gỡ secret khỏi history. Dùng Gradle User Home hoặc CI secret store.

**Câu 5:** Lệnh `./gradlew help` thành công có chứng minh private Maven auth không?

**Đáp án:** Chưa chắc. `help` có thể không resolve private library. Thử configuration/module thật khi đã có endpoint và quyền phù hợp.

**Câu 6:** Gradle báo 403 khi publish nhưng download vẫn được. Có nên đổi thành token quản trị toàn quyền?

**Đáp án:** Không. Xác định policy/ACL, cấp token ghi tối thiểu cho publishing job, tách khỏi token đọc.

**Câu 7:** Vì sao chỉ dùng `mavenCentral()` trước private Maven có thể gây vấn đề?

**Đáp án:** Một số request artifact nội bộ có thể gửi tên dependency đến public repo, tăng dependency confusion và rò rỉ thông tin. Cần content filters hoặc exclusiveContent.

**Câu 8:** `ORG_GRADLE_PROJECT_corpMavenPASSWORD` đúng chưa?

**Đáp án:** Chưa. Với repo `corpMaven`, hậu tố phải là `Password`: `ORG_GRADLE_PROJECT_corpMavenPassword`.

**Câu 9:** Kho chỉ có HTTP và yêu cầu token. Có nên bật `isAllowInsecureProtocol`?

**Đáp án:** Không. Cần HTTPS/TLS endpoint tin cậy, thay vì gửi token qua HTTP thuần.

**Câu 10:** Gradle Wrapper tải distribution riêng bị 401. Thêm PasswordCredentials vào project repositories có giúp không?

**Đáp án:** Không. Wrapper download xảy ra trước khi project build script được đánh giá; nó có cơ chế xác thực riêng.

## 20. Checklist áp dụng trong dự án

1. Xác định đang resolve project dependency, plugin, publish hay Wrapper.
2. Dùng HTTPS URL và tên repo ổn định trong source, ví dụ `corpMaven`.
3. Chọn PasswordCredentials hoặc HttpHeaderCredentials theo scheme server.
4. Đặt giá trị bí mật ngoài source: user gradle.properties có quyền file phù hợp hoặc CI secret store.
5. Với named credentials, kiểm tra chính xác property names theo repo name.
6. Không log secret và không truyền trực tiếp qua `-P`, `-D`, URL hoặc command line.
7. Dùng group filter/exclusiveContent khi cần để ngăn hỏi sai repository.
8. Cấp riêng token read và write, hạn chế CI job/branch/environment sử dụng.
9. Chạy Gradle Wrapper, kiểm tra cấu hình rồi resolve dependency có thật.
10. Nếu lỗi, phân loại HTTP status, repo scope, group/version, cert/proxy và token rights.
11. Rà soát cache/log/artifact tránh chứa credential; rotate token khi nghi lộ.
12. Đối chiếu tài liệu đúng phiên bản Gradle Wrapper trước khi thay đổi API hoặc security settings.

**Quy tắc nhớ nhanh:**

~~~text
Source:      URL HTTPS + repository name + credentials(TYPE) + filters
Secret:      GRADLE_USER_HOME/gradle.properties hoặc CI secret store
Basic:       <repoName>Username + <repoName>Password
HTTP Header: <repoName>AuthHeaderName + <repoName>AuthHeaderValue
CI:          ORG_GRADLE_PROJECT_<propertyName>
Không làm:   hard-code secret / echo token / truyền token qua -P
~~~

## 21. Tài liệu chính thức

- Gradle — Securing Repositories: https://docs.gradle.org/current/userguide/securing_repositories.html
- Gradle — Supported Repository Protocols / HTTP(S) Authentication: https://docs.gradle.org/current/userguide/supported_repository_protocols.html
- Gradle — Build Environment Configuration / Project Properties: https://docs.gradle.org/current/userguide/build_environment.html
- Gradle — Declaring Repositories: https://docs.gradle.org/current/userguide/declaring_repositories_basics.html
- Gradle — Centralizing Repository Declarations: https://docs.gradle.org/current/userguide/centralizing_repositories.html
- Gradle — Maven Publish Plugin: https://docs.gradle.org/current/userguide/publishing_maven.html
- Gradle — Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
- Gradle — PasswordCredentials API: https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.api.credentials/-password-credentials/
- Gradle — HttpHeaderCredentials API: https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.api.credentials/-http-header-credentials/
- Gradle — Configuration Cache Requirements: https://docs.gradle.org/current/userguide/configuration_cache_requirements.html

Những liên kết `current` theo phiên bản Gradle mới nhất tại thời điểm truy cập. Đối với repository thực tế, luôn kiểm tra **phiên bản Gradle Wrapper** và yêu cầu của repository manager/CI đang sử dụng.