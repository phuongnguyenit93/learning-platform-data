# Tách repository snapshot, release và thông tin xác thực khi xuất bản artifact bằng Gradle

## 1. Bài toán: cùng một thư viện nhưng không được xuất bản bừa vào cùng một kho

Trong quá trình phát triển Java, nhóm có thể tạo nhiều bản build của một thư viện. Ví dụ:

- `com.example.training:greeting-api:1.4.0-SNAPSHOT`: bản đang phát triển, còn có thể được publish lại.
- `com.example.training:greeting-api:1.4.0`: bản release chính thức, nên có tính bất biến, có tag/phê duyệt và được tiêu thụ ổn định.
- `com.example.training:greeting-api:1.4.0-rc1`: bản release candidate; có phải snapshot hay release theo chính sách của tổ chức là một quyết định cần xác định rõ.

Nếu cùng dùng một Maven repository, cùng credentials và cùng lệnh `publish` mà không có chính sách, rất dễ xảy ra:

1. Một commit thử nghiệm ghi `-SNAPSHOT` vào kho release.
2. Một release chính thức bị publish lại/ghi đè do account quá nhiều quyền.
3. CI của nhánh feature có quyền ghi vào kho release production.
4. Username/token nằm trong `build.gradle.kts` hoặc được in ở logs.
5. Gradle task `publish` ghi vào **mọi repository được khai báo**, không chỉ repository mà developer tưởng là phù hợp.
6. Consumer đọc snapshot như release và gặp sự khác biệt bytes do snapshot là bản thay đổi.
7. Đội ngũ nhầm `repositories { }` để **tải dependencies** với `publishing.repositories { }` để **đẩy artifacts**.
8. Credentials bị thiếu hoặc sai nhưng bị xử lý bằng cách tắt HTTPS/authentication, làm giảm bảo mật chuỗi cung ứng.

Cách thiết kế tốt là **tách ba quyết định**:

- **Artifact identity:** `groupId:artifactId:version` và metadata nào được xuất bản?
- **Publish destination:** với version đang có, chỉ cho phép một snapshot/release endpoint nào nhận artifact?
- **Authentication/authorization:** tài khoản/token nào được dùng, có đúng quyền, thời hạn và bảo vệ bí mật không?

Bài này dùng Gradle **`maven-publish`** cho Java 17. Bạn sẽ có một demo **publish thật vào hai Maven repositories dạng thư mục trên máy** mà không cần tài khoản; sau đó cùng logic được chuyển sang remote Nexus/Artifactory/GitHub Packages hoặc repository tương thích bằng **Gradle properties/CI secrets**.

Sau bài học, bạn có thể:

- Hiểu semantics của `-SNAPSHOT` và release Maven.
- Tạo `MavenPublication` từ `components["java"]` và chọn repository theo version.
- Dùng **một Maven repository definition được định tuyến động** để lệnh `publish` không vô tình gửi cả hai kho.
- Tách credentials theo **repository name**, dùng `PasswordCredentials` với property lookup tự động.
- Ánh xạ CI secrets vào `ORG_GRADLE_PROJECT_*` thay vì commit mật khẩu.
- Kiểm chứng artifact, POM, Gradle Module Metadata, metadata checksums và tọa độ GAV.
- Phân biệt quyền publish, quyền resolve, credential type, HTTPS và release authorization.
- Xử lý lỗi 401/403/404, invalid version, snapshot policy, checksum mismatch, duplicate release, metadata không đầy đủ.
- Thiết lập pipeline có gate cho snapshot và release và cơ chế rollback/an toàn.

**Quy tắc quan trọng nhất:** chọn URL đúng **chưa đủ**. Repository manager phải có policy snapshots/releases và quyền ghi riêng; CI phải kiểm tra branch/tag, artifacts, tests và approval trước khi publish.

## 2. Các khái niệm trước khi viết Gradle script

### 2.1. Snapshot và release có ý nghĩa gì?

Trong Maven ecosystem, phiên bản `1.4.0-SNAPSHOT` diễn đạt **bản đang thay đổi**. Nhiều repository managers lưu mỗi deployment snapshot dưới timestamp/build number trong metadata, nhưng **cách đặt tên vật lý phụ thuộc server**. Developer thường request bằng logical version `1.4.0-SNAPSHOT`, còn Maven metadata giúp tìm nội dung hiện hành.

Phiên bản `1.4.0` thường là release: sau khi phát hành, bytes/POM/signature **không nên thay đổi**. Đó là chính sách về tính bất biến, chứ **Gradle không tự bảo đảm server không cho ghi đè**.

| Thuộc tính | Snapshot | Release |
| --- | --- | --- |
| Ví dụ | `1.4.0-SNAPSHOT` | `1.4.0` |
| Mục đích | Dev, tích hợp, thử nghiệm | Công bố ổn định |
| Có thể đổi bytes theo thời gian? | Thường có theo chính sách snapshot | Nên cấm |
| Lưu ở đâu? | Maven snapshots repository | Maven releases repository |
| Consumer cache | Cần xét changing metadata/cache policy | Có thể được xem như immutable |
| Quyền publish | CI/dev account phạm vi hạn chế | Release-only service account/approval |
| Nguồn version | Branch/build metadata có kiểm soát | Tag/version chính thức |
| Điều kiện trước publish | Tests + snapshot validation | Tests + tag + signing + approval + release checks |

**Không suy từ mọi hậu tố pre-release**: `1.4.0-rc1` hoặc `1.4.0-beta2` **không tự động được coi là Maven SNAPSHOT**. Trong bài này, quy tắc là **hậu tố chính xác `-SNAPSHOT`**; những version khác đi vào nhánh release. Tổ chức nào có kênh staging/RC riêng phải thêm chính sách phân loại đó thay vì dùng `endsWith("SNAPSHOT")` rồi hy vọng mọi bản pre-release đều đúng kho.

### 2.2. Ba loại repository trong Gradle

| Block / lệnh | Chức năng | Ghi chú |
| --- | --- | --- |
| `pluginManagement.repositories` trong settings | **Tải Gradle plugins** | Không phải kho nhận Maven publication |
| `repositories` hoặc `dependencyResolutionManagement.repositories` | **Tải project dependencies** | Ví dụ `mavenCentral()`, private Maven proxy |
| `publishing.repositories` | **Đẩy publications** | Chính nơi `publish` đưa JAR/POM/metadata lên |
| `publishToMavenLocal` | Xuất bản vào Maven local cache | Không chứng minh remote authentication/upload |
| `publish` | Aggregate publish tasks | Chạy các tasks cho **mọi publication × configured repository** |
| `publish...To...Repository` | Publish một publication tới một repository | Tên phụ thuộc publication/repository names |

Ví dụ cấu hình tiêu thụ:

```kotlin
repositories {
    mavenCentral()
}
```

Ví dụ cấu hình xuất bản:

```kotlin
publishing {
    repositories {
        maven {
            name = "releases"
            url = uri("https://repo.example.invalid/repository/maven-releases/")
        }
    }
}
```

URL `example.invalid` là **địa chỉ tài liệu, không phải server có thật**. Đây là ví dụ phân biệt blocks, **chưa có credentials và publication**, không thể dùng để upload thật.

**Đừng sửa lỗi publish 401 bằng cách thêm `mavenCentral()` vào `repositories`**: repository resolution và publishing là hai chiều độc lập. Chúng có thể dùng cùng endpoint tổ chức nhưng có cấu hình/quyền khác nhau.

### 2.3. Publication không phải chỉ một file JAR

Một `MavenPublication` từ Java component có thể công bố:

- Binary JAR.
- Sources JAR/Javadoc JAR nếu đã bật trong `java { }`.
- Maven POM, nêu GAV và dependency metadata.
- Gradle Module Metadata `.module`, mô tả variants/attributes phù hợp.
- Checksum sidecars nếu được repository/plugin hỗ trợ, và signatures nếu cấu hình `signing`.

Do đó nếu chỉ copy một `build/libs/*.jar` lên kho thủ công, consumer có thể **thiếu metadata hoặc transitive dependencies**. `maven-publish` hiểu các publications/artifacts/metadata và tạo tasks liên quan.

## 3. Chọn chiến lược tách kho

Có hai cách thường gặp.

### 3.1. Một repository trong `publishing`, URL thay theo version

```kotlin
publishing {
    repositories {
        maven {
            name = "deployment"
            val selectedUrl = if (
                project.version.toString().endsWith("-SNAPSHOT")
            ) {
                "https://repo.example.invalid/repository/snapshots/"
            } else {
                "https://repo.example.invalid/repository/releases/"
            }
            url = uri(selectedUrl)
        }
    }
}
```

Đây là **mẫu định tuyến URL** theo tài liệu Gradle, chưa đủ credentials/production release policy. Ưu điểm:

- Chỉ có **một** configured repository cho build hiện tại.
- Lệnh `publish` không vô tình gọi cả hai remote repositories.
- Task name ổn định nếu repository name cố định.
- Code dễ kiểm tra vì lựa chọn dựa vào `project.version`.

Nhược điểm: nếu cùng tên repository `deployment` và cùng credentials, một tài khoản có thể bị cấp quyền quá rộng. Chúng ta sẽ cải tiến bằng **tên repository được chọn cũng thay theo loại version**, nên Gradle nạp credentials snapshot/release tách biệt.

### 3.2. Hai repositories được khai báo đồng thời

```kotlin
publishing {
    repositories {
        maven {
            name = "snapshots"
            url = uri("https://repo.example.invalid/repository/snapshots/")
        }
        maven {
            name = "releases"
            url = uri("https://repo.example.invalid/repository/releases/")
        }
    }
}
```

**CẢNH BÁO:** nếu gọi `./gradlew publish` với hai repositories này, Gradle sẽ tạo tasks cho **cả hai** và aggregate `publish` có thể chạy chúng. Nó **không tự loại release task chỉ vì version có `-SNAPSHOT`**. Server có thể từ chối một đích, nhưng để task gửi dữ liệu sai endpoint không phải thiết kế tốt.

Nếu buộc phải khai báo cả hai, hãy dùng **task cụ thể** (ví dụ `publishMavenJavaPublicationToSnapshotsRepository`) hoặc `PublishToMavenRepository.onlyIf(...)` có policy rõ ràng, đồng thời áp server-side restrictions. Tuy nhiên với đa số library dùng một đích theo version, **khai báo một repository được chọn** đơn giản và an toàn hơn.

## 4. Thiết kế demo: một thư viện, hai kho Maven cục bộ, không mật khẩu

Demo dùng **Gradle Kotlin DSL + Java 17**, đặt tên project là `publishing-lab`. Public artifact ID cố ý khác project name để làm rõ **Maven coordinates không nhất thiết trùng tên JAR local**.

```text
publishing-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── .gitignore
├── src/main/java/demo/publish/Greeting.java
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── .demo-repo/                  (Gradle tạo khi publish)
│   ├── snapshots/
│   └── releases/
└── consumer/                    (một Gradle build độc lập để thử tiêu thụ)
    ├── settings.gradle.kts
    ├── build.gradle.kts
    └── src/main/java/demo/consumer/Client.java
```

**Không** commit `.demo-repo/` vào Git. Đây là Maven repository trên filesystem dành cho thí nghiệm; nó không có server-side quyền truy cập/immutability và không mô phỏng bảo mật Nexus/Artifactory. Ta chọn đặt ngoài `build/` để chạy `clean` không làm mất snapshot đã publish ở bước trước.

Yêu cầu: một Gradle Wrapper tương thích JDK 17, JDK 17 được Gradle nhận diện, môi trường cho phép ghi file, và không có yêu cầu tải third-party library. `java-library` và `maven-publish` là **Gradle core plugins** nên demo có thể vận hành offline sau khi Wrapper/Gradle distribution đã được chuẩn bị.

### 4.1. File `settings.gradle.kts`

```kotlin
rootProject.name = "publishing-lab"
```

`rootProject.name` xác định project name và default local JAR file name, nhưng `MavenPublication.artifactId` có thể được đặt khác. Đây là một build riêng, **không include `consumer`** vì ta muốn thử consumer giống người dùng bên ngoài thật sự.

### 4.2. File `.gitignore`

```gitignore
.gradle/
build/
.demo-repo/
consumer/.gradle/
consumer/build/
```

Không copy toàn bộ local repository, `.gradle` caches hoặc secrets vào Git. Các file Gradle Wrapper **nên được commit** theo policy, không bị `.gitignore` bỏ qua.

### 4.3. File `src/main/java/demo/publish/Greeting.java`

```java
package demo.publish;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "Hello from published library";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

`main` chỉ là entry point tự kiểm tra trong bài học; người tiêu thụ sẽ gọi `Greeting.message()` như API thư viện. Code không phụ thuộc ngoài JDK, nên việc publish/resolve Maven metadata dễ quan sát.

Biên dịch/chạy trực tiếp bằng Java 17 khi cần:

```bash
javac --release 17 -d build/manual-classes src/main/java/demo/publish/Greeting.java
java -cp build/manual-classes demo.publish.Greeting
```

**Stdout chính xác của chương trình**:

```text
Hello from published library
```

Các lệnh này có thể được dùng riêng để kiểm tra code Java; chúng **không tạo publication**, POM hoặc Maven repository. Trên Windows PowerShell, các đường dẫn cũng có thể dùng `\`, ví dụ `build\manual-classes`.

## 5. Toàn bộ `build.gradle.kts`: tự chọn snapshot/release và local/remote

Đây là cấu hình trung tâm của bài, **có thể chạy ngay ở chế độ local mặc định**. Khi muốn publish tới remote, chỉ thay bằng Gradle properties/CI secrets có thật, **không chỉnh logic snapshot/release**.

```kotlin
import org.gradle.api.credentials.PasswordCredentials
import org.gradle.api.publish.maven.MavenPublication

plugins {
    `java-library`
    `maven-publish`
}

group = "com.example.training"

// Version có thể được CI cấp bằng -PartifactVersion=...
val artifactVersion = providers.gradleProperty("artifactVersion")
    .orElse("1.0.0-SNAPSHOT")
    .get()
require(artifactVersion.isNotBlank() && artifactVersion != "unspecified") {
    "A meaningful artifactVersion is required"
}
version = artifactVersion

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
    withSourcesJar()
}

// Hậu tố -SNAPSHOT là quy tắc phân loại của demo.
val isSnapshot = artifactVersion.endsWith("-SNAPSHOT")

// local: file:// repositories trong thư mục .demo-repo
// remote: HTTPS repository từ Gradle properties
val publishTarget = providers.gradleProperty("publishTarget")
    .orElse("local")
    .get()
require(publishTarget == "local" || publishTarget == "remote") {
    "publishTarget must be local or remote"
}

// Repository name còn là prefix của Gradle credentials.
val destinationName = if (isSnapshot) "snapshots" else "releases"

// Ở mỗi invocation chỉ cấu hình MỘT destination URI.
val destinationUrl = if (publishTarget == "remote") {
    val urlProperty = if (isSnapshot) {
        "snapshotRepoUrl"
    } else {
        "releaseRepoUrl"
    }
    uri(providers.gradleProperty(urlProperty).get())
} else {
    val directory = if (isSnapshot) {
        ".demo-repo/snapshots"
    } else {
        ".demo-repo/releases"
    }
    layout.projectDirectory.dir(directory).asFile.toURI()
}

// Không cho gửi credentials qua HTTP plain text.
require(publishTarget != "remote" || destinationUrl.scheme == "https") {
    "Remote publication requires an HTTPS URL"
}

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            groupId = project.group.toString()
            artifactId = "greeting-api"
            version = artifactVersion

            // Gồm binary JAR + metadata Java variants.
            from(components["java"])

            pom {
                name.set("Greeting API")
                description.set("Library for snapshot/release publishing lab")
            }
        }
    }

    repositories {
        maven {
            name = destinationName
            url = destinationUrl

            // Không yêu cầu credentials khi publish vào file://.
            if (publishTarget == "remote") {
                credentials(PasswordCredentials::class)
            }
        }
    }
}

// Task xem kế hoạch: KHÔNG in URL hoặc credentials.
tasks.register("showPublishPlan") {
    group = "publishing"
    description = "Prints selected publication mode and repository name"
    doLast {
        println("ARTIFACT_VERSION=" + artifactVersion)
        println("VERSION_KIND=" + if (isSnapshot) "SNAPSHOT" else "RELEASE")
        println("PUBLISH_TARGET=" + publishTarget)
        println("REPOSITORY_NAME=" + destinationName)
        println("MAVEN_GAV=com.example.training:greeting-api:" + artifactVersion)
    }
}
```

### 5.1. Tại sao configuration này tránh publish nhầm?

- `artifactVersion` được đọc một lần rồi gán cho `project.version` và `MavenPublication.version`.
- `endsWith("-SNAPSHOT")` là **một quy tắc duy nhất** cho cả URL lẫn credential prefix.
- `publishTarget` chỉ nhận `local` hoặc `remote`. Nhập sai, build dừng thay vì tự đoán.
- Với `local`, Gradle chọn một thư mục `.demo-repo/snapshots` hoặc `.demo-repo/releases` và **không cấu hình authentication**.
- Với `remote`, Gradle yêu cầu đúng một property URL: `snapshotRepoUrl` hoặc `releaseRepoUrl`.
- Với `remote`, chỉ nhận URL có scheme `https`, ngăn vô tình gửi mật khẩu qua HTTP.
- `name` của repository là `snapshots` hoặc `releases`, nên Gradle tự tra các credentials **khác nhau**.
- **Chỉ một `maven { ... }` được tạo** tại invocation hiện tại. Vì vậy `publish` không có một second repository task phải tự skip.
- `showPublishPlan` không tiết lộ username/password hoặc full URL (URL đôi khi có query token).
- Sản phẩm chính được publish từ `components["java"]`, giúp POM/Gradle Module Metadata có semantics của Java component.
- `withSourcesJar()` thêm sources artifact; không cần tự zip `src/main/java` rồi upload bằng tay.

### 5.2. Vì sao file local repo nằm ngoài `build/`?

Nếu local demo dùng `layout.buildDirectory.dir("repos/snapshots")`, mỗi lần chạy `clean` có thể xóa toàn bộ artifact đã publish trong thư mục đó. Với `.demo-repo/`, bạn có thể publish snapshot, chạy `clean`, publish release rồi so sánh hai kho mà không bị mất kho trước.

**Đây chỉ là lựa chọn cho lab.** Với production, Maven repository manager quản lý lưu trữ, retention, access control, HTTPS, immutable releases và audit logs. Không biến thư mục `.demo-repo/` thành repository dùng chung trong tổ chức bằng cách commit Git hay mount trên shared file server thiếu bảo vệ.

### 5.3. ArtifactId khác tên project

Project name là `publishing-lab`, nhưng Maven publication đặt `artifactId="greeting-api"`. Do đó:

- JAR trước publish thường ở `build/libs/publishing-lab-1.0.0-SNAPSHOT.jar`.
- Maven coordinates là `com.example.training:greeting-api:1.0.0-SNAPSHOT`.
- Maven repository folder path dùng group path `com/example/training/greeting-api/...`.
- File binary được publish có thể được đổi tên theo Maven artifact ID, ví dụ `greeting-api-1.0.0.jar` cho release.

**Không suy GAV chỉ từ tên file trong `build/libs/`.** Hãy xem chính `MavenPublication`, POM và repository tree.

## 6. Chạy demo snapshot: bản phát triển đi vào kho snapshots

Linux/macOS:

```bash
./gradlew --version
./gradlew showPublishPlan
./gradlew clean publish
```

Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat showPublishPlan
.\gradlew.bat clean publish
```

Vì không truyền `artifactVersion`, cấu hình mặc định là `1.0.0-SNAPSHOT`, `publishTarget=local`.

Stdout **chỉ của task `showPublishPlan`** được thiết kế gồm:

```text
ARTIFACT_VERSION=1.0.0-SNAPSHOT
VERSION_KIND=SNAPSHOT
PUBLISH_TARGET=local
REPOSITORY_NAME=snapshots
MAVEN_GAV=com.example.training:greeting-api:1.0.0-SNAPSHOT
```

Đây **không phải toàn bộ Gradle console output**: Gradle còn có task headings, build result, warnings/caching messages.

Sau `publish`, kiểm tra:

```text
.demo-repo/snapshots/com/example/training/greeting-api/1.0.0-SNAPSHOT/
```

Thư mục này nên chứa các artifacts/metadata của snapshot publication theo Maven format. Tên file thực tế có thể là logical `-SNAPSHOT` hoặc timestamped snapshot tùy metadata/publishing implementation; **không cố định một tên file timestamp giả**. Dùng `find`/`Get-ChildItem` để xem entry thật.

Xem đường chính:

```bash
find .demo-repo/snapshots -type f
```

PowerShell:

```powershell
Get-ChildItem .demo-repo\snapshots -Recurse -File |
    Select-Object FullName
```

Lệnh `publish` tạo Maven artifact/POM/metadata, **không tự chạy unit tests như một gate bắt buộc**. Với ứng dụng thật, CI nên chạy `check` trước rồi mới cho publish.

### 6.1. Các task được sinh bởi `maven-publish`

Với publication name `mavenJava` và selected repository name `snapshots`, Gradle sinh task kiểu:

```text
generatePomFileForMavenJavaPublication
generateMetadataFileForMavenJavaPublication
publishMavenJavaPublicationToSnapshotsRepository
publish
publishToMavenLocal
```

Một vài task phụ thuộc và tên artifact-specific có thể thay đổi theo plugin/Gradle version. Dùng:

```bash
./gradlew tasks --all
./gradlew publish --dry-run
```

để xác nhận trong build hiện tại.

**`--dry-run` chỉ hiển thị task graph**, không upload được artifact hoặc xác minh username/password của remote. Nếu cần biết publication task đúng URL, xem `showPublishPlan` và cấu hình/properties đã được phê duyệt; không log secrets hoặc URL có token.

## 7. Chạy demo release: cùng publication nhưng đích khác

Với cùng build, không sửa file để đổi URL. Chỉ đưa version release:

```bash
./gradlew showPublishPlan -PartifactVersion=1.0.0
./gradlew clean publish -PartifactVersion=1.0.0
```

PowerShell:

```powershell
.\gradlew.bat showPublishPlan -PartifactVersion=1.0.0
.\gradlew.bat clean publish -PartifactVersion=1.0.0
```

Stdout thiết kế của `showPublishPlan`:

```text
ARTIFACT_VERSION=1.0.0
VERSION_KIND=RELEASE
PUBLISH_TARGET=local
REPOSITORY_NAME=releases
MAVEN_GAV=com.example.training:greeting-api:1.0.0
```

Artifact release sẽ được đưa về:

```text
.demo-repo/releases/com/example/training/greeting-api/1.0.0/
```

Snapshot ở `.demo-repo/snapshots` **vẫn tồn tại** dù chạy `clean`, vì hai kho thử nghiệm nằm ngoài `build/`.

**Đây là cơ chế chuyển routing, không phải “release promotion”.** Bản release đã được build lại theo version `1.0.0`; bytecode/artifact bytes có thể khác snapshot nếu manifest/version metadata hoặc build inputs đổi. Với pipeline đòi promotion của *exact same bytes*, phải sử dụng khả năng promote/stage/release của repository manager hoặc quy trình lưu artifact đã được chứng thực; không mặc định rebuild từ cùng commit luôn tạo bytes giống nhau nếu chưa kiểm chứng reproducibility.

### 7.1. Kiểm tra file đã publish, không chỉ task status

Trên Unix:

```bash
find .demo-repo -type f
jar tf build/libs/publishing-lab-1.0.0.jar
```

Trên PowerShell:

```powershell
Get-ChildItem .demo-repo -Recurse -File |
    Select-Object FullName
jar tf build\libs\publishing-lab-1.0.0.jar
```

Mong đợi:

- `.jar` chứa `demo/publish/Greeting.class`.
- `-sources.jar` chứa `demo/publish/Greeting.java`.
- Maven POM nêu `groupId=com.example.training`, `artifactId=greeting-api`, `version=1.0.0`.
- Gradle Module Metadata mô tả Java variants nếu được publish theo cấu hình hiện tại.
- File checksums nếu publisher/repository hỗ trợ hoặc được Gradle tạo theo Maven publishing.

**Không khẳng định mọi kho luôn dùng cùng tên sidecar files**. Repository manager có thể sinh metadata riêng, rewrite snapshot filenames hoặc có cấu hình signing/staging đặc thù.

## 8. Consumer độc lập: chứng minh snapshot/release đọc từ đúng kho

Một publisher chạy `publish` thành công chưa chứng minh consumer ngoài repo tìm thấy module đúng GAV. Ta tạo **một Gradle build khác** dưới thư mục `consumer/`, không đưa nó vào `include(...)` của root publisher.

### 8.1. `consumer/settings.gradle.kts`

```kotlin
rootProject.name = "publish-consumer"
```

### 8.2. `consumer/build.gradle.kts`

```kotlin
plugins {
    application
}

repositories {
    maven {
        url = uri("../.demo-repo/releases")
        mavenContent {
            releasesOnly()
        }
    }
    maven {
        url = uri("../.demo-repo/snapshots")
        mavenContent {
            snapshotsOnly()
        }
    }
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation("com.example.training:greeting-api:1.0.0-SNAPSHOT")
}

application {
    mainClass.set("demo.consumer.Client")
}
```

**Quan trọng:** `mavenContent { releasesOnly()/snapshotsOnly() }` là bộ lọc **trên consumer repository resolution**, không phải luật chặn publisher upload nhầm. Bộ lọc nói cho Gradle biết đích nào có loại version nào; nó **không cấp quyền**, **không kiểm tra server release immutability**, và không làm `publishing.repositories` tự chọn đích.

Các relative paths trong file trên tính từ **`consumer/` project directory**. Nó truy cập hai file repositories do lab publisher tạo trước đó. Với repository doanh nghiệp, phải thay bằng HTTPS URLs do tổ chức phê duyệt và cấu hình read credentials riêng (thường ít quyền hơn credentials publish).

### 8.3. `consumer/src/main/java/demo/consumer/Client.java`

```java
package demo.consumer;

import demo.publish.Greeting;

public final class Client {
    private Client() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
```

### 8.4. Chạy consumer trên snapshot

Từ root `publishing-lab/`, sau khi đã publish snapshot:

```bash
./gradlew -p consumer clean run
```

PowerShell:

```powershell
.\gradlew.bat -p consumer clean run
```

Stdout của `Client.main`:

```text
Hello from published library
```

Nếu bạn đã chạy chỉ phiên bản release mà chưa publish snapshot, consumer sẽ fail ở `1.0.0-SNAPSHOT` — đó là tình huống đúng vì dependency chưa tồn tại ở snapshots repository.

### 8.5. Chuyển sang release

Trong **consumer/build.gradle.kts**, thay dòng dependency bằng:

```kotlin
implementation("com.example.training:greeting-api:1.0.0")
```

Sau đó:

```bash
./gradlew -p consumer clean run
```

Consumer sẽ tìm `1.0.0` ở releases repo, dự kiến in cùng stdout nếu source API không đổi. Việc stdout giống nhau **không** có nghĩa two publications giống hệt bytes; muốn xác định dùng POM, selected dependency report và SHA-256.

Kiểm tra graph:

```bash
./gradlew -p consumer dependencies --configuration runtimeClasspath
./gradlew -p consumer dependencyInsight --dependency greeting-api \
    --configuration runtimeClasspath
```

PowerShell có thể viết lệnh cuối trên **một dòng**; dấu `\` nối dòng trong Bash không dùng nguyên xi trong PowerShell.

## 9. Chuyển từ local file repositories sang remote HTTP(S)

Code publisher phần 5 **đã hỗ trợ** `-PpublishTarget=remote`. Khi chọn remote, URL được đọc từ một trong hai Gradle properties:

| Loại version | Property URL phải có | Repository name | Credentials mà Gradle tra |
| --- | --- | --- | --- |
| `-SNAPSHOT` | `snapshotRepoUrl` | `snapshots` | `snapshotsUsername` / `snapshotsPassword` |
| Không có `-SNAPSHOT` | `releaseRepoUrl` | `releases` | `releasesUsername` / `releasesPassword` |

**Không khai báo cùng credentials cho cả hai kho.** Mỗi đích nên có service account/token riêng với quyền nhỏ nhất, đặc biệt release upload cần được hạn chế hơn snapshots.

Một ví dụ **chỉ về URL**, dùng domain tài liệu không tồn tại:

```properties
snapshotRepoUrl=https://repo.example.invalid/repository/maven-snapshots/
releaseRepoUrl=https://repo.example.invalid/repository/maven-releases/
```

Bạn có thể đặt **hai URL không bí mật** trong project `gradle.properties` nếu tổ chức cho phép, sau khi thay bằng URL thật. Không đặt username/password vào cùng file được commit. Domain `example.invalid` là nơi điền thông tin trong ví dụ, **không có máy chủ triển khai thực tế**.

### 9.1. Lệnh xuất bản remote chỉ khi đã có endpoint và credentials thật

Snapshot:

```bash
./gradlew showPublishPlan -PpublishTarget=remote \
    -PartifactVersion=1.4.0-SNAPSHOT

./gradlew check publish -PpublishTarget=remote \
    -PartifactVersion=1.4.0-SNAPSHOT
```

Release:

```bash
./gradlew showPublishPlan -PpublishTarget=remote \
    -PartifactVersion=1.4.0

./gradlew check publish -PpublishTarget=remote \
    -PartifactVersion=1.4.0
```

**Các lệnh trên là mẫu production chỉ sau khi đã cấp quyền và cấu hình môi trường.** Với `example.invalid`, chúng không thể upload thành công. `check publish` có ý nghĩa chạy cả hai lifecycle tasks **trong cùng invocation**, nhưng task ordering trong graph không nên được suy thành release gate nghiêm ngặt chỉ từ thứ tự tên lệnh. Pipeline nên tách **job/stage kiểm thử pass trước, stage publish sau**; hoặc định nghĩa explicit task dependency/gating có kiểm chứng.

Khi dùng PowerShell, chạy mỗi Gradle command trên một dòng không có Bash `\`; đặt Gradle flags sau task cũng được.

### 9.2. Chuyện gì xảy ra nếu thiếu URL?

Vì script dùng:

```kotlin
providers.gradleProperty(urlProperty).get()
```

nên khi `publishTarget=remote` mà thiếu `snapshotRepoUrl` hoặc `releaseRepoUrl`, build **fail sớm trong configuration**. Đó là cơ chế **fail closed** được chủ đích; đừng dùng fallback remote URL đoán bừa hoặc tự trỏ vào public repository nào khác.

Ở chế độ local, script không cần hai URL này, không cần username/password và vẫn publish được trong sandbox. Với release thật, có thể thêm policy kiểm tra hostname/allowed path để tránh bị hướng sang máy chủ ngoài tổ chức, ngoài việc kiểm scheme `https`.

## 10. Credentials: lấy từ đâu mà không ghi vào source?

Trong build script:

```kotlin
maven {
    name = "snapshots"
    credentials(PasswordCredentials::class)
}
```

Nếu repository name là `snapshots`, Gradle tự tìm **Gradle properties**:

- `snapshotsUsername`
- `snapshotsPassword`

Nếu repository name là `releases`:

- `releasesUsername`
- `releasesPassword`

Đó là cơ chế `credentials(PasswordCredentials::class)` và lookup tự động của Gradle. **Tên phải khớp chính xác về chữ hoa/chữ thường**; `snapshotUsername` (thiếu `s`) không giống `snapshotsUsername`. Với demo, credentials chỉ được cấu hình khi `publishTarget == "remote"`.

### 10.1. Các nguồn Gradle property thường dùng

Gradle có thể đọc project properties qua:

- User-home `~/.gradle/gradle.properties` (**không** commit vào project).
- Project `gradle.properties` (chỉ đặt giá trị không bí mật, trừ khi repository private/ignored có policy đặc biệt).
- CLI `-Pkey=value` (không khuyến nghị cho secrets vì có thể lộ trong process list, shell history, CI logs).
- Environment variables có prefix `ORG_GRADLE_PROJECT_`.
- Các cơ chế Gradle property được CI/IDE cấu hình theo phiên bản/platform.

Ví dụ tên environment variables tương ứng:

```text
ORG_GRADLE_PROJECT_snapshotsUsername
ORG_GRADLE_PROJECT_snapshotsPassword
ORG_GRADLE_PROJECT_releasesUsername
ORG_GRADLE_PROJECT_releasesPassword
```

Đây là **tên biến**, không phải secret values. Tổ chức cần dùng secret manager/CI secrets để tiêm giá trị vào environment khi **đúng publish job** chạy.

### 10.2. Shell pattern với secrets đã có sẵn trong CI

Ví dụ Bash trong một job mà secret manager **đã** đặt sẵn hai biến `CI_SNAPSHOT_USER` và `CI_SNAPSHOT_TOKEN`:

```bash
export ORG_GRADLE_PROJECT_snapshotsUsername="$CI_SNAPSHOT_USER"
export ORG_GRADLE_PROJECT_snapshotsPassword="$CI_SNAPSHOT_TOKEN"

./gradlew publish -PpublishTarget=remote \
  -PartifactVersion=1.4.0-SNAPSHOT
```

Không đưa giá trị token trực tiếp vào script, không bật `set -x` trên đoạn có secrets và không `echo` env variables. Job release nên dùng **hai secret variables khác** ánh xạ vào `ORG_GRADLE_PROJECT_releasesUsername` và `ORG_GRADLE_PROJECT_releasesPassword`, không reuse snapshot credentials.

**Không mặc định mỗi server dùng username/password người dùng thật.** Nhiều Nexus/Artifactory deployments hỗ trợ scoped tokens; có thể dùng username robot + token làm password. GitHub Packages có cơ chế token/permissions riêng. Chỉ dùng scheme server yêu cầu.

### 10.3. Tại sao không dùng `System.getenv("PASSWORD")!!` trực tiếp?

Mẫu anti-pattern:

```kotlin
credentials {
    username = "developer"
    password = "literal-secret-in-git"
}
```

Đây là **mẫu sai để nhận diện**, không chứa một secret thật. Cách này để lộ thông tin, không tái sử dụng được trên CI và khó rotate.

Cũng tránh ép:

```kotlin
val token = System.getenv("REPO_PASSWORD")!!
```

ở top-level cho **mọi invocation**: ngay cả `help`, `tasks` hay `test` đều có thể fail nếu developer không có token. Dùng `PasswordCredentials::class` để Gradle chỉ yêu cầu credentials khi repository thật sự được dùng bởi một task cần authentication; cơ chế này được tài liệu Gradle nêu rõ.

**Giới hạn:** nếu script vẫn gọi `providers.gradleProperty("releaseRepoUrl").get()` lúc configuration, nó có thể yêu cầu URL dù chưa publish. Đó là vấn đề riêng của endpoint config, không phải cơ chế trì hoãn credential requirement.

### 10.4. HTTP Basic và HTTP header token

`PasswordCredentials` phù hợp nhiều Maven repository servers, nhưng một số host yêu cầu header token hoặc scheme khác. Gradle có:

- `PasswordCredentials`: user/password.
- `HttpHeaderCredentials`: tên/value header, ví dụ bearer token theo server.
- `AwsCredentials`: access/secret/session token cho S3-compatible repository path theo API.

Ví dụ **mẫu cơ chế** để dùng header auth, **không dán thêm vào publisher demo đồng thời với PasswordCredentials**:

```kotlin
import org.gradle.api.credentials.HttpHeaderCredentials
import org.gradle.authentication.http.HttpHeaderAuthentication

publishing {
    repositories {
        maven {
            name = "privateHeaderRepo"
            url = uri("https://repo.example.invalid/repository/maven-private/")
            credentials(HttpHeaderCredentials::class)
            authentication {
                create<HttpHeaderAuthentication>("header")
            }
        }
    }
}
```

Nếu dùng `privateHeaderRepo`, Gradle có thể tra `privateHeaderRepoAuthHeaderName` và `privateHeaderRepoAuthHeaderValue`. Header name/value phải theo tài liệu host; **đừng giả định mọi server chấp nhận `Authorization: Bearer ...` hoặc cùng tên header**. Đây là **phương án thay thế** cần publication và URL thật, không phải toàn bộ runnable build.

### 10.5. HTTPS là nền tảng, nhưng chưa đủ

HTTPS bảo vệ transport khi certificate validation đúng; nó không chứng minh artifact được publish là an toàn. Ngoài HTTPS cần:

- Repository host allowlist và TLS certificate chain hợp lệ.
- Service accounts/tokens với scopes thích hợp và thời gian sống ngắn khi có thể.
- Rights read vs deploy riêng; snapshot account không được deploy release.
- Secret masking/log retention trong CI, không ghi token vào artifact metadata.
- Revocation/rotation và audit logs.
- Branch/tag protection và publish approvals.
- Checksum/signature/provenance của release artifacts.

Đừng dùng `allowInsecureProtocol=true` để bypass lỗi kết nối HTTPS hoặc chứng chỉ. Nếu internal CA chưa được trust, hãy cấu hình trust store/certificate chain hợp lệ theo policy.

## 11. Tách quyền snapshot/release trong CI

### 11.1. Snapshot pipeline

Một snapshot pipeline có thể chạy trên nhánh phát triển được cho phép:

```text
Feature/main commit
       |
 Checkout + Gradle Wrapper verification
       |
 Build/test/quality checks
       |
 Security/dependency checks theo policy
       |
 Tính version -SNAPSHOT được cho phép
       |
 Chọn snapshot URL và snapshot service account
       |
 publish (chỉ 1 selected repository)
       |
 Check artifact/POM/metadata + lưu build trace
```

Không nên cấp release credentials cho job feature branch vì credential theft có thể xảy ra qua script/plugin/dependency độc hại trong build.

### 11.2. Release pipeline

Release nên là một job/stage riêng:

```text
Protected tag v1.4.0 + approval
       |
 Checkout đúng commit/tag, clean workspace
       |
 Verify Wrapper/JDK/dependencies
       |
 Full tests, quality, security/license checks
       |
 Kiểm version không chứa -SNAPSHOT
       |
 Chọn releases endpoint + release-only credentials
       |
 Ký artifacts và xuất provenance theo policy
       |
 publish / stage / promote theo repository manager
       |
 Verify published GAV, POM, checksum, signature
       |
 Ghi release audit trail
```

**Không có tính năng nào trong `maven-publish` tự xác nhận Git tag là hợp lệ**. Đó là trách nhiệm của CI/release policy.

### 11.3. Một ví dụ khung CI (minh họa)

```yaml
# Stage snapshot: chỉ chạy ở branch được phép.
steps:
  - name: Verify and test
    run: ./gradlew clean check

  - name: Publish snapshot
    env:
      ORG_GRADLE_PROJECT_snapshotsUsername: ${{ secrets.SNAPSHOT_PUBLISH_USER }}
      ORG_GRADLE_PROJECT_snapshotsPassword: ${{ secrets.SNAPSHOT_PUBLISH_TOKEN }}
    run: |
      ./gradlew publish -PpublishTarget=remote \
        -PartifactVersion=1.4.0-SNAPSHOT
```

**Đây là snippet dùng cú pháp GitHub Actions secrets, chưa phải workflow hoàn chỉnh**: cần trigger, permissions, branch restriction, checkout, setup JDK, Wrapper integrity, caches, approved URLs và secret definitions của tổ chức. Không copy nguyên vào CI rồi cho rằng release đã được bảo vệ.

Ví dụ release stage tương tự nhưng dùng `releasesUsername`/`releasesPassword` và stable version từ protected tag. Chỉ job release mới có quyền đọc hai release secrets. Dùng account snapshot để deploy release là vi phạm nguyên tắc least privilege.

### 11.4. Vì sao release nên tách job chứ không chỉ đổi version?

Mặc dù script đã route bằng `-SNAPSHOT`, chính sách release có nhiều bước **khác snapshot**:

- Release artifacts phải immutable, cần ký/checksum và retention phù hợp.
- Build từ đúng protected tag; không nhận version tùy ý của untrusted pull request.
- Cần POM license/SCM/developer metadata nếu repository yêu cầu.
- Có quyền deploy/stage/release khác snapshot.
- Có thể cần xác minh artifacts chính là những bytes đã test.
- Có rollback hoặc deprecate release, không âm thầm overwrite version đã phát hành.

**Tách repository là một lớp kiểm soát kỹ thuật, không thay release governance.**

## 12. Tác vụ publish cụ thể và bẫy aggregate `publish`

### 12.1. Task name từ publication và repository name

Trong demo:

- Publication name: `mavenJava`.
- Repository name snapshot: `snapshots`.
- Repository name release: `releases`.

Với snapshot, Gradle tạo:

```text
publishMavenJavaPublicationToSnapshotsRepository
```

Với release:

```text
publishMavenJavaPublicationToReleasesRepository
```

Trong mỗi build invocation, chỉ một trong hai được tạo vì `destinationName` phụ thuộc version. Dùng `./gradlew tasks --all` để xác nhận chính xác. Lệnh `./gradlew publish` sẽ chạy những publication-to-repository tasks hiện có trong invocation đó.

### 12.2. Nếu một build buộc có hai repositories đồng thời

Gradle hỗ trợ `PublishToMavenRepository.onlyIf(...)`. Ví dụ **chỉ minh họa predicate**:

```kotlin
import org.gradle.api.publish.maven.tasks.PublishToMavenRepository

tasks.withType<PublishToMavenRepository>().configureEach {
    onlyIf("snapshot to snapshots, release to releases") {
        val snapshot = project.version.toString().endsWith("-SNAPSHOT")
        (repository.name == "snapshots" && snapshot) ||
        (repository.name == "releases" && !snapshot)
    }
}
```

**Đoạn này không thay thế cấu hình hai repository URLs**, và không chứng minh credentials sẽ chỉ được yêu cầu ở repository task được skip trong mọi Gradle/plugin version. Nếu bạn dùng aggregate `publish` và cả hai repos có credentials, Gradle có thể kiểm credential requirements từ task graph trước execution. Vì vậy **một selected repo per invocation** là cách đơn giản hơn khi mục tiêu là tránh sai đích và chỉ cần một bộ credentials.

Dù có `onlyIf`, repository manager vẫn cần reject snapshot ở releases repository và reject release ở snapshots repository. Đừng coi client-side task predicate là một security boundary.

### 12.3. `publishToMavenLocal` không phải bước deployment

`./gradlew publishToMavenLocal` xuất bản vào local Maven repository, thường `~/.m2/repository`. Nó:

- Không sử dụng `publishing.repositories` remote target để upload.
- Không đòi remote deployment credentials.
- Không kiểm tra network, TLS, HTTP authentication và quyền write.
- Không thay pipeline snapshot/release.
- Có thể ghi đè module local và gây khác biệt khi consumer ưu tiên `mavenLocal()`.

Trong bài demo, **nên dùng selected file-based repository qua `publish`** để xác minh routing snapshot/release, hơn là dùng `publishToMavenLocal` rồi nghĩ đã kiểm remote repository selection.

## 13. Consumer repository filter và supply chain

Một hệ thống khác tải dependency của bạn cần **cấu hình tiêu thụ**:

```kotlin
repositories {
    maven {
        url = uri("https://repo.example.invalid/repository/releases/")
        mavenContent {
            releasesOnly()
        }
    }

    maven {
        url = uri("https://repo.example.invalid/repository/snapshots/")
        mavenContent {
            snapshotsOnly()
        }
    }
}
```

Đây là **consumer-side model**, dùng URLs ví dụ không có thật. Chức năng:

- Khi cần release, Gradle ưu tiên repository được phép chứa release.
- Khi cần snapshot, Gradle xem repository khai báo `snapshotsOnly()`.
- Giảm truy vấn nhầm repository, tăng tính rõ ràng và có thể giảm rò rỉ thông tin dependency.
- Không tự định nghĩa credentials cho publish.
- Không bảo đảm một repository manager không lưu sai loại version nếu server policy sai.

Với các private group nội bộ, cân nhắc `content { includeGroup("com.example.training") }` hoặc `exclusiveContent` để tránh dependency confusion/repository shadowing. `exclusiveContent` có semantics toàn bộ repository handler và có giới hạn khi dùng trong `pluginManagement`; chỉ áp sau khi hiểu transitive dependencies và Gradle settings của tổ chức.

**Cẩn thận với repo order:** Gradle có thể chọn module từ repository đầu tiên có metadata phù hợp; không nên để Maven Central hoặc mavenLocal shadow private group một cách ngẫu nhiên. Dùng content filters và quản lý namespace theo policy.

### 13.1. Tại sao snapshot consumer có thể không thấy bytes mới ngay?

Snapshot logical version thay đổi theo thời gian; Gradle có cơ chế cache cho **changing modules**/metadata. Cùng `1.4.0-SNAPSHOT` có thể được publish lại nhưng consumer vẫn dùng cached resolution trong một khoảng thời gian tùy chính sách. Điều đó không có nghĩa publisher đã đẩy sai URL.

Khi điều tra:

```bash
./gradlew dependencyInsight --dependency greeting-api \
  --configuration runtimeClasspath
./gradlew --refresh-dependencies run
```

`--refresh-dependencies` yêu cầu Gradle kiểm tra lại resolution metadata/artifacts theo quy tắc; **không** chứng minh artifact nguồn an toàn và không buộc tải lại mọi file khi checksum/cache cho thấy không đổi. Với release reproducibility, tránh phụ thuộc snapshot mutable trong production.

## 14. Publishing metadata, checksum và chữ ký

### 14.1. POM và Gradle Module Metadata

Với `MavenPublication.from(components["java"])`:

- POM mang GAV, dependencies theo Java variant mapping, project information.
- Gradle Module Metadata có thể ghi variants/attributes, API/runtime distinctions.
- Sources/Javadoc artifacts bổ sung cần bật trong Java plugin.
- Publication version phải nhất quán với project/Git tag/repository policy.

Kiểm thử từ **external consumer** quan trọng vì project dependency `project(":module")` có thể resolve được trong cùng build ngay cả khi publication thiếu metadata hoặc artifact. Demo consumer ở phần 8 kiểm tra đúng repository Maven file layout.

Gradle tạo các tasks như `generatePomFileForMavenJavaPublication` và `generateMetadataFileForMavenJavaPublication`. Bạn có thể xem file dưới `build/publications/mavenJava/` sau khi task chạy. Đừng tự sửa generated POM bên trong `build/` rồi mong lần publish tiếp dùng nó.

### 14.2. Checksums và dependency verification

Maven publish có thể tạo checksums như SHA-256/SHA-512; remote repository cũng có thể kiểm/ghi sidecars. Nhưng một checksum do cùng nguồn không đáng tin phát hành chưa tự xác minh publisher identity.

Ở consumer, Gradle **Dependency Verification** dùng `gradle/verification-metadata.xml` và checksum/PGP fingerprints được review để kiểm soát bytes đã chấp thuận. Nó khác cơ chế publish URL routing và khác **dependency locking** (pin selected versions). Khi release cần provenance mạnh, thêm signing/attestation theo security policy.

### 14.3. Signing cho release

Gradle có core `signing` plugin; ví dụ một publishing build có thể sign `publishing.publications["mavenJava"]` với private key được cấp từ secret manager. **Không commit PGP private keys hoặc passphrase** và không sao chép khóa từ máy cá nhân vào CI logs.

Có thể có release policy:

- Snapshot: signing optional/hoặc mandatory tùy tổ chức.
- Release: signing mandatory, public key fingerprint được công bố/xác minh.
- Snapshot/release đều dùng HTTPS và controlled credentials.
- Artifact repository có immutable release policy và checksums validation.
- CI lưu source commit, build provenance, JDK/Wrapper/plugin versions.

Maven Central có release/deployment workflow riêng, và theo tài liệu Gradle hiện hành không dùng legacy Maven Deploy Plugin/OSSRH endpoint cũ. **Đừng giả định chỉ thêm `maven-publish` với URL Maven Central là có thể xuất bản trực tiếp vào Maven Central hiện đại.** Bài demo nhắm generic Maven-compatible repositories như Nexus/Artifactory, không thay thế quy trình portal chuyên dụng.

## 15. Lỗi thường gặp và cách phân biệt

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Snapshot xuất hiện ở releases repo | Version routing sai hoặc khai báo cả hai repository rồi gọi aggregate `publish` | Kiểm `-SNAPSHOT`, URL, task graph; cấu hình một selected repo và server policy |
| Release xuất hiện ở snapshots repo | Dùng default `artifactVersion=...-SNAPSHOT` khi định release | Truyền stable version từ protected tag, kiểm `showPublishPlan` |
| `1.4.0-rc1` vào releases | Quy tắc chỉ xét `-SNAPSHOT` | Xây chính sách staging/RC riêng nếu cần, không coi là lỗi Gradle |
| `401 Unauthorized` | Thiếu/sai username/token hoặc auth scheme | Kiểm repo name → property names, token validity, server challenge |
| `403 Forbidden` | Account đăng nhập được nhưng thiếu quyền deploy/overwrite | Kiểm role/scope, release immutability, project policy |
| `404 Not Found` khi upload | URL sai, repository path chưa tồn tại, reverse proxy hoặc server che quyền | Xác minh endpoint với admin; không disable TLS |
| `Could not get property snapshotRepoUrl` | Chưa cấp URL remote cho snapshot | Cấp Gradle property đúng tên, URL HTTPS |
| Gradle báo missing `snapshotsUsername` | Đặt nhầm `snapshotUsername` hoặc secret chưa injection | Dùng `ORG_GRADLE_PROJECT_snapshotsUsername`/`snapshotsPassword` |
| Có username/password nhưng request fail | Server cần bearer/header auth hoặc token chưa đủ scope | Đọc docs host, dùng `HttpHeaderCredentials` khi đúng |
| `publish` chạy hai remote tasks | Hai `maven { }` được cấu hình đồng thời | Dùng một selected repo hoặc explicit task/predicate |
| `publishToMavenLocal` pass nhưng remote fail | Local publishing không test HTTPS/auth | Chạy đúng remote task với credentials và approved URL |
| `generatePomFile...` pass nhưng upload fail | POM generation và remote network/deploy là các giai đoạn khác | Kiểm repository permissions, network, URL, server logs |
| `Publication ... not found` | Không tạo `MavenPublication` hoặc sai tên `mavenJava` | Xem `publishing.publications`, tasks --all |
| `Cannot publish multiple publications with same coordinates` | GAV trùng giữa publications hoặc modules | Gán group/artifactId/version duy nhất theo policy |
| Artifact upload nhưng POM sai | Không publish từ Java component đúng hoặc tùy chỉnh POM sai | `from(components["java"])` và consumer test |
| Thư viện resolve nội bộ nhưng external consumer fail | Project dependency che metadata publication thiếu | Publish vào sandbox Maven file repo rồi resolve từ build độc lập |
| New snapshot không thấy ở consumer | Cache changing modules hoặc snapshot metadata chưa cập nhật | Kiểm server metadata, `--refresh-dependencies` theo policy |
| Release GAV đã tồn tại bị từ chối | Server immutable release policy hoạt động đúng | Tạo version mới, không overwrite release cũ |
| Source JAR không có trong kho | Quên `withSourcesJar()` hoặc configuration publication không gồm variant | Bật Java sources JAR, kiểm metadata/artifact tree |
| `java.lang.UnsupportedClassVersionError` khi consumer chạy | Compiler target Java mới hơn consumer runtime | Dùng Java toolchain/`--release` phù hợp, test runtime tối thiểu |
| `Unsupported protocol HTTP` / TLS problem | URL insecure hoặc certificate trust lỗi | Sửa HTTPS/trust chain, không bật insecure fallback |
| Build fail ngay khi chạy `help` ở remote mode | URL property `.get()` tại configuration bị thiếu | Cấp URL trước hoặc dùng local mode để xem project; credentials vẫn yêu cầu theo task |
| CI logs lộ token | Debug logging, `-Psecret=...`, shell tracing hoặc in URL query token | Rotate token, tắt tracing, mask/review logs |
| CI fail nhưng laptop pass | Khác Wrapper/JDK/secrets/repository endpoint/certificate | Pin environment, dùng protected CI secret injection |
| `.demo-repo` bị xóa sau clean | Đặt file repository trong `build/` hoặc cleanup tùy chỉnh | Để lab repo ngoài `build/` và `.gitignore` |
| Maven Central upload fail | Không dùng workflow/plugin Portal phù hợp hiện hành | Dùng publishing flow được Maven Central/Gradle docs hiện thời hỗ trợ |
| Client `repositories { mavenContent ... }` không chặn publisher | MavenContent là resolution filter | Dùng publish routing và server-side staging/release policies |

### 15.1. 401 và 403 không phải cùng lỗi

**401** thường báo thiếu/không hợp lệ auth; **403** thường báo quyền không cho thao tác. Nhưng repository managers/proxies có thể trả mã khác hoặc cố tình che resources. Đừng suy nguyên nhân chỉ từ HTTP status: cần biết URI, method, user scope, repository type (hosted/proxy/group), server logs và token policy.

### 15.2. Không tự khắc phục lỗi bằng cách nới quyền release account

Nếu snapshot publish fail vào release repository, đó có thể là **dấu hiệu route sai**; cấp thêm quyền để “fix” sẽ làm xấu bảo mật. Hãy kiểm `showPublishPlan`, `project.version`, `publishing.repositories`, generated task names, CI secrets và server policy trước.

## 16. Quy trình điều tra có hệ thống

**Bước 1 — xác nhận version và lựa chọn kho, không in secrets:**

```bash
./gradlew showPublishPlan -PartifactVersion=1.4.0-SNAPSHOT
./gradlew showPublishPlan -PartifactVersion=1.4.0
```

Kiểm `VERSION_KIND` và `REPOSITORY_NAME`.

**Bước 2 — xác nhận task graph:**

```bash
./gradlew tasks --all
./gradlew publish --dry-run
```

Ở demo với một selected repository, chỉ nên có một publish-to-repository target cho mỗi publication trong invocation.

**Bước 3 — kiểm Java artifact, POM, metadata:**

```bash
./gradlew clean jar generatePomFileForMavenJavaPublication
jar tf build/libs/publishing-lab-1.0.0-SNAPSHOT.jar
```

Lệnh `jar tf` ở đây **giả định snapshot version mặc định**. Nếu đã truyền `-PartifactVersion=1.0.0`, tên file sẽ khác. Đọc `build/publications/mavenJava/pom-default.xml` nếu task đã tạo thành công.

**Bước 4 — publish vào file-based repository trước:**

```bash
./gradlew publish -PpublishTarget=local \
  -PartifactVersion=1.0.0-SNAPSHOT
```

Kiểm thư mục snapshots và POM thật. Nếu local publish fail, khắc phục build/publication trước khi đổ lỗi HTTP authentication.

**Bước 5 — chuyển đúng remote endpoint và quyền:**

- Kiểm URL thật là HTTPS và repository type **hosted** nhận deployments, không phải proxy-only.
- Xác nhận snapshot/release URL tương ứng với version suffix.
- Kiểm đúng tên credential properties và secrets injection.
- Xác định token nào có deployment permission, scope group/path/version nào.
- Không in token/full URL/query parameters; dùng repository manager logs hoặc redacted stacktrace.

**Bước 6 — xác minh server-side policy:** release immutable, snapshots retention, authentication, allowed groups, deploy paths, audit events, no overwrite release. Việc server chặn nhầm upload nên được xem là guardrail có ích.

**Bước 7 — thử external consumer:** resolve GAV từ repository thật (read-only creds), xem dependency graph và metadata, chạy smoke test trên JDK target, không chỉ kiểm task `publish` trả code 0.

**Bước 8 — đóng bằng chứng:** ghi commit SHA, tag, Gradle Wrapper, toolchain, GAV, repository name, artifact SHA-256, result/checksums và CI job ID — nhưng **không ghi secrets**.

## 17. Multi-project, convention plugin và centralized policy

Trong monorepo:

```text
root/
├── settings.gradle.kts
├── gradle/libs.versions.toml
├── api/build.gradle.kts
├── client/build.gradle.kts
└── build-logic/
    └── ...
```

Một số modules nên publish, một số không:

- `:api` và `:client` là public/internal Java libraries cần Maven publications.
- `:integration-tests` là test-only module, không nên có publication.
- `:docs` hoặc `:tools` có thể tạo ZIPs nhưng không phải Maven component.
- Root aggregator không nhất thiết có Java component để publish.

**Đừng áp dụng `maven-publish`/credentials khắp `subprojects { ... }` rồi để mọi module có đường upload production.** Tạo convention plugin theo `company.publish-java-library`, chỉ áp vào modules thực sự được publish. Nó có thể:

1. Áp Java library/Maven publish plugins.
2. Đặt groupId/artifactId conventions rõ ràng.
3. Cấp metadata POM (license, SCM, developers) theo yêu cầu.
4. Chọn snapshot/release destination từ version + policy.
5. Tạo sources/Javadoc artifacts đúng scope.
6. Nối signing/release verification tasks khi cần.
7. Enforce HTTPS, endpoint allowlist và restriction không publish version `unspecified`.
8. Không đọc secrets ở root build nếu task publish không được gọi.

Mỗi module phải có **unique Maven coordinates**. Khi version giống nhau nhưng artifactId trùng nhau, hai modules có thể đè hoặc bị repository manager từ chối; không phải lỗi Gradle có thể “fix” bằng tăng retry count.

### 17.1. Version catalog không bảo vệ release endpoints

`libs.versions.toml` giúp pin dependency/plugin versions, nhưng **không tự chọn publication destination hoặc cấp credentials**. `settings.pluginManagement.repositories` là nguồn tải build plugins, còn Maven publish destination vẫn nằm trong `publishing.repositories`. Phân tách hai chức năng này để secrets không vô tình bị đưa vào plugin repository resolution.

### 17.2. Phân biệt deploy modules và deploy Gradle plugins

Nếu xuất bản Gradle plugin lên **Gradle Plugin Portal**, cơ chế `com.gradle.plugin-publish` có policies/credentials khác generic Maven repository. Bài này dạy **Maven-compatible module publication**; không lấy snapshot routing của Nexus rồi copy sang Plugin Portal. Khi publish plugin vào internal Maven repository qua marker/implementation artifacts, cần bảo đảm đủ publications và metadata plugin theo `java-gradle-plugin`/Gradle docs.

## 18. Bảo vệ quy trình publish: từ demo tới production

### 18.1. Release phải bất biến

Một release version `1.4.0` nên được publish **một lần**. Nếu phát hiện bug sau release, tạo `1.4.1` hoặc deprecate/revoke qua quy trình chính thức. Không overwrite `1.4.0` bởi vì:

- Consumer caches có thể giữ phiên bản bytes cũ.
- Dependency verification đã pin checksum sẽ phát hiện thay đổi.
- Software bill of materials/attestations và chữ ký mất ý nghĩa nếu bytes đổi.
- Downstream builds dùng cùng version nhưng ra kết quả khác nhau.
- Audit trail không còn gắn chắc artifact với source commit.

**Server-side immutability** quan trọng hơn client-side `onlyIf` bởi credential bị lộ hoặc người dùng công cụ khác vẫn có thể gửi HTTP request.

### 18.2. Snapshots cũng cần accountability

Snapshot mutable không đồng nghĩa vô hạn và vô trách nhiệm:

- CI log commit/branch/build ID đã sinh artifact.
- Chỉ job được phép mới publish; không dùng deploy account của release.
- Có retention và cleanup rõ.
- Có version/tag đủ mô tả branch khi nhiều branches song song.
- Consumer snapshot có caching policy thích hợp; tránh pin mutable snapshot cho production.
- Các dependencies nội bộ không vô tình được shadow bởi external repository.

Khi cần build dev thật sự immutable, cân nhắc **unique prerelease version theo commit/build number** thay vì publish đè `-SNAPSHOT` mãi. Khi dùng kiểu version khác `-SNAPSHOT`, điều chỉnh routing policy trước; không suy Gradle tự biết đó là snapshot.

### 18.3. Secret hygiene

- **Không commit** tokens/passwords/private signing keys vào Git.
- **Không** truyền secrets thẳng trong `-P...=secret` nếu CI/shell history có thể ghi lại.
- **Không** bật `set -x`/verbose HTTP logging trong job có secrets.
- Dùng masking/retention policy cho logs.
- Tách read token và publish token; snapshot publish token và release publish token.
- Token càng ngắn hạn/càng ít scope càng tốt; rotation/revocation có playbook.
- Review mọi build plugins/scripts vì chúng chạy trong Gradle build process và có thể đọc environment.
- HTTPS + validated TLS/CA, không tắt certificate verification.
- Signing secrets chỉ được cấp ở release job, không tự gắn vào pull request từ fork.
- Đảm bảo protected branches/tags và CI workflows không bị untrusted contributor sửa để leak secret.

### 18.4. Build reproducibility

Pin Gradle Wrapper, Java toolchains, dependency versions và kiểm tra checksums/PGP khi phù hợp. Release build nên có thể tái lập hoặc ít nhất có provenance đủ điều tra. Cùng tag không bảo đảm cùng bytes nếu generated files hoặc tool versions thay đổi. Tốt nhất lưu checksums trước/sau upload và verify artifact lấy lại từ repository.

## 19. Các tình huống quyết định thường gặp

| Tình huống | Lựa chọn |
| --- | --- |
| Developer muốn thử Maven publication nhưng không có account | Demo file repositories `.demo-repo/snapshots`/`releases` |
| CI branch `main` muốn publish bản chưa phát hành | `x.y.z-SNAPSHOT` vào snapshot repo, snapshot-only account |
| Protected tag `v1.4.0` đã duyệt | `1.4.0` vào releases repo, release-only account, signing/checks |
| `1.4.0-rc1` cần không vào releases | Mở kênh staging/RC hoặc sửa routing policy; không dựa chỉ `-SNAPSHOT` |
| Nhiều repos được cấu hình và gọi `publish` | Cẩn thận: aggregate gửi tới mọi repo; chuyển một selected repo hoặc gate tasks |
| Server dùng username + token | `PasswordCredentials`, token như password theo docs server |
| Server dùng HTTP header bearer token | `HttpHeaderCredentials` với property prefix/HttpHeaderAuthentication |
| Secret chưa được cấp trong CI | Fail sớm khi publish, không fallback anonymous/insecure |
| Release GAV bị server từ chối vì đã tồn tại | Giữ immutability, tạo version mới hoặc làm release recovery có audit |
| Consumer cần cả snapshot và release | `mavenContent { snapshotsOnly() / releasesOnly() }` ở **consumer repositories** |
| User muốn xuất bản vào Maven local | `publishToMavenLocal`, không phải deploy remote |
| Internal repo là proxy/cache chỉ đọc | Không publish vào proxy/group URL không chấp nhận deploy; dùng hosted deployment endpoint |
| Test pass nhưng Maven consumer báo missing dependency | Kiểm published POM/`.module` và external consumer build, không chỉ JAR |

## 20. Câu hỏi tự kiểm tra

1. **`1.4.0-SNAPSHOT` thường đi vào kho nào?** Snapshot Maven repository, theo routing policy.
2. **`1.4.0` thường đi vào kho nào?** Releases repository, nơi artifact nên immutable.
3. **`1.4.0-rc1` có tự là SNAPSHOT?** Không. Hậu tố `-SNAPSHOT` mới là quy tắc demo, cần staging riêng nếu muốn.
4. **`repositories { mavenCentral() }` có quyết định nơi `publish` upload không?** Không; publish dùng `publishing.repositories`.
5. **Khai báo hai repos trong `publishing.repositories` rồi chạy `publish` có tự chọn đúng một không?** Không. Aggregate có tasks cho cả hai.
6. **Nếu repository name là `snapshots`, Gradle tra credentials nào?** `snapshotsUsername` và `snapshotsPassword`.
7. **Tên `snapshotUsername` có tự thay `snapshotsUsername` không?** Không, names/case phải khớp.
8. **Tại sao dùng `ORG_GRADLE_PROJECT_*` trong CI?** Để cấp Gradle properties từ environment/secret manager mà không commit giá trị.
9. **Một token có quyền cả snapshot và release có rủi ro gì?** Compromise job snapshot có thể deploy release; nguyên tắc least privilege bị phá.
10. **`publishToMavenLocal` có kiểm thử username/password remote không?** Không.
11. **Dùng `mavenContent { snapshotsOnly() }` ở consumer có chặn upload release không?** Không, nó lọc dependency resolution.
12. **Nếu build local pass nhưng remote báo 403, sửa bằng cách thêm Maven Central?** Không. Kiểm server permissions/role/hosted endpoint.
13. **Vì sao JAR đã build không đủ để Maven consumers resolve đúng?** Cần publication metadata POM/Gradle Module Metadata, deps và GAV.
14. **`version="1.4.0"` có bảo đảm release được xây từ protected Git tag không?** Không; CI/release policy phải kiểm tag/source.
15. **Snapshot mới publish mà consumer vẫn nhận bản cũ, điều gì có thể xảy ra?** Changing module cache/metadata TTL của consumer.
16. **Có nên chạy `--refresh-dependencies` để sửa checksum mismatch rồi chấp nhận artifact mới?** Không. Phải xác minh nguồn và bytes.
17. **Làm sao tránh xóa local test repository khi chạy `clean`?** Đặt demo repository ngoài `build/` hoặc không clean thư mục đó.
18. **Nếu release repository đã có `1.4.0` và từ chối overwrite, đây là lỗi hay bảo vệ?** Thường là guardrail đúng để giữ immutability.
19. **Tại sao HTTPS không đủ để chứng minh một artifact đúng publisher?** TLS chỉ bảo vệ transport/endpoint; cần provenance, checksum/signature, code review.
20. **Vì sao nên kiểm bằng external consumer?** Nó phát hiện publication thiếu metadata/GAV/dependency dù producer build/project dependency vẫn ổn.

## 21. Checklist trước khi bật publish thật

- [ ] Maven coordinates `groupId:artifactId:version` đã kiểm chứng, version không còn `unspecified`.
- [ ] Phân loại snapshot qua `-SNAPSHOT` hoặc policy khác được xác định rõ.
- [ ] Chỉ một selected repository theo version cho mỗi publish invocation, hoặc có gate hai repos được kiểm chứng.
- [ ] Snapshot và release có endpoint hosted phù hợp, URL **HTTPS** và allowlist.
- [ ] Account/token snapshots và releases tách biệt, permissions tối thiểu.
- [ ] Credentials được cấp qua CI secrets/Gradle user properties, không commit vào source.
- [ ] Tên repository và property prefix khớp chính xác; biết `ORG_GRADLE_PROJECT_*`.
- [ ] Không in token, basic auth header hoặc URL có secrets trong logs.
- [ ] Release chỉ chạy từ protected tag/branch với approval và tests thành công.
- [ ] Snapshot không có quyền overwrite release, server chặn sai version type.
- [ ] Release immutability được enforce ở repository manager, không chỉ Gradle script.
- [ ] Publication dùng `from(components["java"])` và đúng sources/Javadoc artifacts khi cần.
- [ ] POM/Gradle Module Metadata/dependencies được kiểm bằng external consumer.
- [ ] `publishToMavenLocal` không bị nhầm là production deployment.
- [ ] Consumer repositories dùng Maven snapshot/release filters theo chính sách.
- [ ] Build Wrapper/JDK/dependencies và generated outputs có provenance/checksum.
- [ ] Release signing/attestation nếu repository/organization yêu cầu.
- [ ] Có audit logs, release ID, Git commit, artifact checksums, rollback/revocation procedure.
- [ ] CI jobs không nhận secrets khi chạy untrusted PR/fork code.
- [ ] Có quy trình 401/403/repository permission/metadata resolution và key rotation.

## 22. Ghi nhớ

- **Snapshot** dùng version kết thúc `-SNAPSHOT`, thường được lưu ở snapshots repo và có semantics mutable.
- **Release** là version ổn định, nên publish đúng một lần vào releases repo với server-side immutability.
- **`publishing.repositories` chọn nơi upload**, khác `repositories` dùng để tải libraries và `pluginManagement.repositories` dùng để tải build plugins.
- **`publish` aggregate tất cả configured repository tasks**. Muốn chỉ một đích, cấu hình **một repository được chọn theo version**.
- **Repository name là credential identity** khi dùng `credentials(PasswordCredentials::class)`: `snapshotsUsername/Password` và `releasesUsername/Password` có thể được tiêm riêng.
- **`ORG_GRADLE_PROJECT_*` là cách truyền Gradle properties từ CI environment**, không phải lý do để in secret ra console.
- **`mavenContent { snapshotsOnly()/releasesOnly() }` chỉ lọc consumer resolution**, không kiểm soát việc publish.
- **`MavenPublication.from(components["java"])` xuất bản Java artifact kèm POM/variants**, khác chỉ copy JAR vào một thư mục.
- **`publishToMavenLocal` không xác minh remote auth hoặc quyền**, chỉ là local Maven repository.
- **CI và repository server cần bảo vệ cuối cùng**: protected tags, tests, HTTPS, least privilege, release immutability, checksums và audit trail.

## Tài liệu chính thức

- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): `MavenPublication`, `publishing.repositories`, snapshot/release URL routing, generated tasks và `publishToMavenLocal`.
- [Gradle — Publishing Setup](https://docs.gradle.org/current/userguide/publishing_setup.html): publications, metadata, repository, task mapping và checksums.
- [Gradle — Supported Repository Protocols](https://docs.gradle.org/current/userguide/supported_repository_protocols.html): `PasswordCredentials`, tự đọc Gradle properties theo repository name, conditional credentials, HTTP/header authentication.
- [Gradle — Securing Repositories](https://docs.gradle.org/current/userguide/securing_repositories.html): secrets, authentication, TLS và repository security.
- [Gradle — Customizing Publishing](https://docs.gradle.org/current/userguide/publishing_customization.html): `PublishToMavenRepository.onlyIf` cho publishing có điều kiện.
- [Gradle — Filtering Repository Content](https://docs.gradle.org/current/userguide/filtering_repository_content.html): `mavenContent { snapshotsOnly() / releasesOnly() }` trong consumer repositories.
- [Gradle — Declaring Dependency Versions](https://docs.gradle.org/current/userguide/dependency_versions.html): `-SNAPSHOT` là changing module và caching implications.
- [Gradle — Maven Publication DSL](https://docs.gradle.org/current/dsl/org.gradle.api.publish.maven.MavenPublication.html): groupId/artifactId/version và publication APIs.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): checksum và signature checks ở phía consumer.
- [Gradle — Publishing to Maven Central](https://docs.gradle.org/current/userguide/publishing_maven.html#publishing_maven:publishing_maven_central): giới hạn/flow xuất bản Maven Central hiện hành, không nhầm legacy OSSRH với generic Maven deployment.
