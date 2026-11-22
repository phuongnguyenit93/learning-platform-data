# Rủi ro của `flatDir`, kho cục bộ và dependency không có metadata trong Gradle

## 1. Mục tiêu và bối cảnh

Gradle hỗ trợ nhiều cách nhận thư viện: module từ Maven/Ivy repository, project dependency, local file, flat directory repository và Maven local cache. Những cách này **không tương đương** về metadata, dependency bắc cầu, tính tái lập và an toàn chuỗi cung ứng.

Trong một dự án legacy, ai đó có thể chép `legacy-1.0.jar` vào `libs/`, dùng `flatDir` để Gradle tìm JAR, hoặc chạy `mvn install`/`publishToMavenLocal` để thư viện xuất hiện ở `~/.m2/repository`. Điều đó có thể giúp compile trên máy cá nhân nhưng làm CI thiếu JAR, runtime thiếu class, hoặc hai người có cùng `group:name:version` nhưng khác binary.

Sau bài học, bạn sẽ:

- Phân biệt `flatDir`, `files(...)`/`fileTree(...)`, `mavenLocal()`, local Maven/Ivy repository và repository HTTPS được quản lý.
- Hiểu **module metadata** và vai trò của POM, Ivy XML, Gradle Module Metadata.
- Giải thích vì sao `flatDir` không thể thay thế module có metadata thật và không tự biết dependency bắc cầu.
- Hiểu vì sao `mavenLocal()` **có thể chứa metadata** nhưng vẫn thiếu độ tin cậy và tính tái lập cần cho CI/release.
- Nhận biết rủi ro `metadataSources { artifact() }` và notation `@jar` khi bỏ metadata.
- Chạy demo Gradle + Java 17 chứng minh **compile thành công chưa bảo đảm runtime classpath đủ**.
- Chọn migration hợp lý: project/composite dependency, Maven/Ivy publishing, internal repository, content filtering, dependency locking và verification.

**Nguyên tắc:** hãy quản lý **module có tọa độ, metadata và nguồn repository được kiểm soát**, thay vì coi một JAR trần là mô hình dependency đầy đủ.

## 2. Module khác artifact; metadata khác tên file

Ví dụ module dependency:

```text
group:name:version
com.example:api:1.0
```

Trong Java project:

```kotlin
repositories { mavenCentral() }

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
```

Gradle cần thông tin rộng hơn file `commons-lang3-3.14.0.jar`:

| Dữ liệu | Ý nghĩa đối với dependency resolution |
| --- | --- |
| Maven POM (`.pom`) | Group/name/version, các Maven dependency scopes và dependencies được publish |
| Ivy descriptor (`ivy.xml`) | Configurations, artifacts, dependencies của Ivy |
| Gradle Module Metadata (`.module`) | Variants, attributes, capabilities, dependencies, constraints và artifacts |
| Artifact (`.jar`, `.aar`, `.zip`) | Bytecode/tài nguyên được tải; không tự mô tả mọi dependency bên ngoài |
| Repository | Nguồn lấy artifact, policy tin cậy, cách truy cập, khả năng bất biến và auditing |

Giả sử `com.example:api:1.0` gọi class từ `com.example:helper:1.0`. Với POM/Gradle metadata khai báo đúng dependency, consumer của `api` có thể tự nhận `helper` ở runtime. Nếu chỉ có file `api-1.0.jar`, Gradle **không thể tự suy ra** helper từ tên file.

**Dependency trực tiếp** là thứ app khai báo. **Dependency bắc cầu (transitive)** là thứ metadata của dependency đó khai báo. Một JAR có thể đóng gói `META-INF/MANIFEST.MF` hoặc POM trong archive, nhưng `flatDir` **không dùng các nội dung ấy thay cho metadata repository** theo mô hình Maven/Ivy/Gradle.

## 3. Bảng so sánh các loại dependency/repository

| Phương án | Cách khai báo | Metadata thật? | Rủi ro chính |
| --- | --- | --- | --- |
| Maven/Ivy repository HTTPS | `mavenCentral()` hoặc `maven { url = uri("https://...") }` | Có nếu publisher cung cấp | Cần policy nguồn, credentials, version, verification |
| Maven local | `mavenLocal()` | **Có thể có** POM/`.module` | Mutable cache cá nhân, missing modules, khác CI |
| Local Maven/Ivy repository | `maven { url = uri("fixture-repo") }` | Có nếu đúng layout và POM/Ivy metadata | Cùng file path có thể bị sửa, không tái lập trên runner khác |
| Flat directory repo | `flatDir { dirs("libs") }` | Không đọc POM/Ivy; Gradle sinh metadata tạm | Không có transitive graph/variants đúng nghĩa |
| File dependency | `files("libs/a.jar")`, `fileTree(...)` | Không | Thiếu GAV, transitives, publication metadata; path dễ biến động |

**Cần phân biệt:** `mavenLocal()` không giống `flatDir`. Một artifact Maven local **có thể** có POM và dependencies, nhưng nó vẫn là **kho local dễ ghi đè**, không có hợp đồng release bất biến như repository được quản lý. Gradle dependency cache dưới `GRADLE_USER_HOME` cũng không đồng nghĩa Maven local dưới `~/.m2/repository`.

## 4. `flatDir` là gì và tại sao Gradle khuyến nghị tránh?

Ví dụ Kotlin DSL trong `build.gradle.kts`:

```kotlin
plugins {
    java
}

repositories {
    flatDir {
        dirs("libs")
    }
}

dependencies {
    implementation("com.example:legacy-util:1.2")
}
```

Nếu `libs/legacy-util-1.2.jar` có mặt, Gradle có thể chọn file đó. Tuy nhiên:

1. `group=com.example` là danh tính mà consumer khai báo, **không được xác minh từ cây Maven có POM**.
2. `flatDir` tìm file theo quy tắc tên artifact, tạo metadata **ad hoc** từ sự tồn tại của file.
3. Không đọc Maven POM/Ivy XML để tìm dependency bắc cầu.
4. Không có publication variants/attributes/capabilities đầy đủ như từ Gradle Module Metadata.
5. Không có nguồn gốc publisher hoặc release checksum đáng tin chỉ từ tên file.
6. Các SDK lớn có thể cần nhiều JAR nhưng file JAR chính không liệt kê thông tin đó cho Gradle.

Groovy DSL tương đương, **là lựa chọn file khác**:

```groovy
plugins {
    id 'java'
}
repositories {
    flatDir { dirs 'libs' }
}
dependencies {
    implementation 'com.example:legacy-util:1.2'
}
```

### 4.1. FlatDir không thể override metadata thật

Đây là quy tắc đặc biệt quan trọng trong Gradle: **module có metadata thật** trong Maven/Ivy repository được ưu tiên so với metadata tạm từ `flatDir`. Ví dụ:

```text
flatDir:   libs/legacy-util-1.2.jar
Maven:     com/example/legacy-util/1.2/legacy-util-1.2.pom
           com/example/legacy-util/1.2/legacy-util-1.2.jar
```

Gradle ưu tiên module có metadata thật, kể cả nếu flatDir được khai báo trước. Đừng dùng flatDir để thay thế hoặc vá một module cùng GAV đã có trên Maven repository; hãy publish artifact/metadata có chủ đích hoặc dùng resolution/substitution mechanism đúng mục đích.

### 4.2. Khi nào vẫn tạm dùng?

Có thể chấp nhận rất hạn chế khi vendor chỉ cung cấp một JAR offline hoặc giữ legacy binary trong giai đoạn chuyển đổi. Cần ghi nguồn gốc, checksum, license, owner, artifact bytes, danh sách dependency cần thêm, runtime tests và kế hoạch thay thế. Đây là **ngoại lệ được quản trị**, không phải cách mặc định cho project mới.

## 5. `files(...)` và `fileTree(...)` không có metadata module

```kotlin
plugins { java }

dependencies {
    implementation(files("libs/legacy-util-1.2.jar"))
    runtimeOnly(fileTree("vendor-libs") {
        include("*.jar")
    })
}
```

Không cần `repositories` để nhận những file trực tiếp này. Đổi lại:

- Không có module GAV hoặc POM để tự resolve transitives.
- Thư mục `vendor-libs` có thể bị thêm/bớt JAR mà không sửa build script.
- Gradle **không bảo đảm thứ tự duyệt `FileTree` ổn định**, ngay cả trên cùng máy; cache/task nhạy thứ tự có thể gặp sai lệch.
- File deps **không được đưa vào published dependency descriptor** như các external modules. Consumer ngoài build không tự tải JAR được copy trong `libs` của producer.
- Nếu file được một task khác sinh ra, phải nối producer/consumer bằng output Provider hoặc `builtBy`; chỉ khai báo file path không nhất thiết chạy task sinh file.

Ví dụ path không portable:

```groovy
dependencies {
    implementation files('/Users/alice/Downloads/vendor.jar')
}
```

Trên Windows/CI path đó không tồn tại. Đưa JAR vào thư mục project và trỏ relative path có thể giải quyết vị trí file, **nhưng không tạo metadata hoặc bảo đảm license, integrity, transitives**.

Nếu bắt buộc dùng file dependencies, danh sách cố định `files("libs/a.jar", "libs/b.jar")` minh bạch hơn wildcard. Tuy nhiên giải pháp dài hạn vẫn là module dependency có metadata.

## 6. `mavenLocal()` có metadata nhưng kém tin cậy cho CI

`mavenLocal()` thường trỏ `~/.m2/repository` (vị trí thực tế có thể bị Maven settings thay đổi). Đây **khác** Gradle cache trong `GRADLE_USER_HOME`.

```groovy
// Chỉ để nhận diện nguy cơ, không phải mẫu production.
repositories {
    mavenLocal()
    mavenCentral()
}
```

Ba nhóm rủi ro theo tài liệu Gradle:

1. **Kho Maven local chủ yếu là cache**, không phải release repository có hợp đồng đầy đủ; module có thể thiếu artifacts phụ, POM hoặc metadata hoàn chỉnh.
2. **An ninh và tính đúng:** file có thể được ghi đè bởi `mvn install`/`publishToMavenLocal` hay process local khác. Hai người dùng cùng GAV có thể nhận JAR khác bytes.
3. **Hiệu năng:** Gradle không có cơ sở giả định local artifacts bất biến, nên hạn chế/bỏ qua caching dependency bình thường cho local repositories; tra local trước remote còn tốn thêm lookup.

Nếu có POM hợp lệ, Maven local **có thể mang dependency bắc cầu**. Điểm yếu của nó là **độ tin cậy và khả năng tái lập**, không phải mọi file trong Maven local đương nhiên không có metadata.

Sử dụng `mavenLocal()` có thể hợp lý khi một developer thử publication mới hoặc cần cầu nối tạm Maven↔Gradle. Nhưng không đưa nó thành nguồn mặc định trong CI/release, không yêu cầu người mới phải chạy một chuỗi `mvn install` bí mật trước khi build.

`publishToMavenLocal` chỉ cài publication vào local Maven repository, **không** publish lên Nexus/Artifactory/Maven Central. `--offline` cũng không tạo ra dependency còn thiếu: nó chỉ dùng dữ liệu mà Gradle đã có thể lấy được ở chế độ offline.

## 7. Maven/Ivy repository trên filesystem khác flat directory

Một Maven local directory có cấu trúc:

```text
fixture-repo/
└── com/example/api/1.0/
    ├── api-1.0.jar
    ├── api-1.0.pom
    └── api-1.0.module  (nếu producer có Gradle metadata)
```

Kotlin DSL:

```kotlin
repositories {
    maven {
        url = uri(layout.projectDirectory.dir("fixture-repo"))
    }
}
```

Gradle có thể dùng POM/`.module` ở đó để resolve module. Nhưng **`flatDir { dirs("fixture-repo") }` không tương đương**: flatDir không đọc cấu trúc đó thành Maven module. Và nếu `libs` chỉ có JAR trần, đổi sang `maven { url = uri("libs") }` không tự tạo layout hay metadata.

Local Maven/Ivy repositories thích hợp với fixture, prototyping và kiểm tra publisher trong một sandbox. Với production, chúng vẫn mutable, có rủi ro performance/cache và khó bảo đảm nội dung trên mọi CI runner.

## 8. `metadataSources { artifact() }` và `@jar` có thể bỏ metadata

Khi repository kiểu Maven không có POM, một số dự án dùng fallback:

```kotlin
repositories {
    maven {
        // URL minh họa, không phải server hoạt động.
        url = uri("https://repo.example.invalid/legacy")
        metadataSources {
            mavenPom()
            artifact()
        }
    }
}
```

`artifact()` cho phép Gradle chấp nhận artifact file và sinh metadata tối thiểu khi không tìm thấy POM. Nó **không thể biết dependency bắc cầu bị thiếu**, nên chỉ là biện pháp tương thích với repository legacy. Nếu kiểm soát publisher, hãy phát hành POM/Gradle metadata thật thay vì bật fallback rộng rãi.

Một cách khác cũng dễ gây hiểu nhầm:

```kotlin
dependencies {
    implementation("com.example:api:1.0@jar")
}
```

`@jar` là **artifact-only notation**. Nó bỏ qua module metadata và transitive dependency resolution của module đó. Nó **không tương đương** với `implementation("com.example:api:1.0")` dù hai cách có thể tải cùng file JAR. Tránh tự thêm `@jar` với suy nghĩ “ghi đầy đủ đuôi file cho rõ”.

## 9. Demo Java 17 chạy được: thiếu metadata, thiếu class runtime

Thực hành tạo hai JAR bằng JDK 17+ mà **không dùng Maven/Gradle publishing**:

- `api-1.0.jar` cung cấp method `Api.run()`.
- Method đó gọi `Helper.message()` trong `helper-1.0.jar`.
- Application chỉ khai báo API JAR qua flatDir. Gradle có thể compile, nhưng runtime thiếu helper.

### 9.1. Cây thư mục

```text
flatdir-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── src/
│   ├── main/java/Demo.java
│   └── manual/
│       ├── helper/com/example/Helper.java
│       └── api/com/example/Api.java
├── libs/                   (được tạo sau)
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
```

Sử dụng Gradle Wrapper đã có; nếu tạo project mới hoàn toàn, dùng bản Gradle cài tạm để chạy `gradle wrapper` một lần rồi sử dụng Wrapper. `src/manual` **không** nằm trong source set `main` của Java plugin.

`settings.gradle.kts`:

```kotlin
rootProject.name = "flatdir-demo"
```

`src/manual/helper/com/example/Helper.java`:

```java
package com.example;

public final class Helper {
    private Helper() {}

    public static String message() {
        return "hello from helper";
    }
}
```

`src/manual/api/com/example/Api.java`:

```java
package com.example;

public final class Api {
    private Api() {}

    public static String run() {
        return Helper.message();
    }
}
```

`src/main/java/Demo.java`:

```java
import com.example.Api;

public final class Demo {
    public static void main(String[] args) {
        System.out.println(Api.run());
    }
}
```

### 9.2. Tạo JAR trên Linux/macOS

```bash
mkdir -p libs build/manual/helper build/manual/api
javac -d build/manual/helper src/manual/helper/com/example/Helper.java
jar --create --file libs/helper-1.0.jar -C build/manual/helper .
javac -cp libs/helper-1.0.jar -d build/manual/api src/manual/api/com/example/Api.java
jar --create --file libs/api-1.0.jar -C build/manual/api .
```

Windows PowerShell (không dùng ký tự tiếp dòng):

```powershell
New-Item -ItemType Directory -Force libs, build/manual/helper, build/manual/api | Out-Null
javac -d build/manual/helper src/manual/helper/com/example/Helper.java
jar --create --file libs/helper-1.0.jar -C build/manual/helper .
javac -cp libs/helper-1.0.jar -d build/manual/api src/manual/api/com/example/Api.java
jar --create --file libs/api-1.0.jar -C build/manual/api .
```

Có thể kiểm tra bằng `jar --list --file libs/api-1.0.jar`. `api` không chứa `Helper.class`. File JAR không phải POM, và không có repository metadata cho Gradle biết API cần Helper.

### 9.3. `build.gradle.kts` chạy với flatDir

```kotlin
plugins {
    application
}

repositories {
    flatDir {
        dirs("libs")
    }
}

dependencies {
    implementation("com.example:api:1.0")
}

application {
    mainClass.set("Demo")
}
```

Chạy:

```bash
./gradlew -q compileJava
./gradlew -q run
```

`compileJava` có thể thành công: `Demo.java` chỉ gọi method `Api.run()` có chữ ký trả về `String`. Nhưng ở runtime, JVM thực thi code bên trong `Api.run()` và cần `Helper.class`, nên `run` **dự kiến FAIL**. Dòng lỗi nguyên nhân gốc thường có dạng:

```text
java.lang.NoClassDefFoundError: com/example/Helper
Caused by: java.lang.ClassNotFoundException: com.example.Helper
```

Đây là **trích đoạn stack trace điển hình**, không phải toàn bộ stdout của Gradle/JDK.

### 9.4. Sửa tạm bằng khai báo helper trực tiếp

Thay block `dependencies` bằng:

```kotlin
dependencies {
    implementation("com.example:api:1.0")
    runtimeOnly("com.example:helper:1.0")
}
```

Chạy:

```bash
./gradlew -q run
```

Stdout của ứng dụng:

```text
hello from helper
```

Lý do `runtimeOnly` đủ là `Demo` không gọi trực tiếp Helper khi compile. Tuy nhiên, đây vẫn là **sửa thủ công**: nếu API JAR có hàng chục dependencies hoặc thay phiên bản, mọi consumer có thể phải cập nhật lại classpath. Publisher nên khai báo dependencies trong POM/Gradle metadata.

### 9.5. Kiểm chứng graph

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Trước khi thêm helper, graph chỉ có `com.example:api:1.0`. Sau khi thêm `runtimeOnly`, helper xuất hiện như **dependency trực tiếp**, không phải transitive dependency Gradle suy ra từ API metadata. Trên Windows dùng `.\gradlew.bat` thay `./gradlew`.

## 10. Cách chuẩn: Maven/Ivy publication có metadata

Một Maven repository được publish đầy đủ có thể có cấu trúc:

```text
repo/com/example/api/1.0/api-1.0.jar
repo/com/example/api/1.0/api-1.0.pom
repo/com/example/api/1.0/api-1.0.module
repo/com/example/helper/1.0/helper-1.0.jar
repo/com/example/helper/1.0/helper-1.0.pom
```

POM của API có thể mô tả helper:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>api</artifactId>
  <version>1.0</version>
  <dependencies>
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>helper</artifactId>
      <version>1.0</version>
      <scope>runtime</scope>
    </dependency>
  </dependencies>
</project>
```

Đây là **mẫu POM minh họa**. Cần publish cả artifacts và metadata theo layout đúng, không chỉ tạo một XML nằm cạnh JAR trần.

Ví dụ producer dùng Groovy DSL, `java-library` và `maven-publish` (cần module helper và repository thật; **không phải project độc lập chạy ngay**):

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example'
version = '1.0'

dependencies {
    implementation 'com.example:helper:1.0'
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            artifactId = 'api'
        }
    }
    repositories {
        maven {
            url = uri('https://repo.company.example/releases')
        }
    }
}
```

Publisher nên có chính sách credentials từ secret store, quyền publish và immutable versions. Consumer ở repository khác chỉ khai báo `implementation("com.example:api:1.0")` qua repository tin cậy, Gradle có thể dùng metadata để lấy helper đúng scope.

Nếu cả API và helper là source thuộc **cùng multi-project build**, ưu tiên:

```kotlin
dependencies {
    implementation(project(":helper"))
}
```

Điều kiện là `settings.gradle.kts` đã `include(":helper")` và producer cung cấp variants phù hợp. Khi hai source repositories cần phối hợp, xem composite build và dependency substitution; tránh bắt mọi developer cài artifact thủ công vào Maven local.

## 11. Repository order, origin và dependency confusion

Gradle thường tra các repositories theo thứ tự khai báo; khi tìm metadata của một module trong repository cụ thể, Gradle cố lấy artifacts của module **từ cùng repository**, không tùy tiện ghép POM ở A với JAR ở B. Riêng `flatDir` có metadata tạm và không ưu tiên hơn metadata thật.

Một local repository trước remote repository có thể **shadow** module cùng GAV. Người A vừa cài `com.example:api:1.0` lên Maven local có bytes mới; CI không có nó và tải bytes khác. Đây là lỗi reproducibility ngay cả khi metadata local đầy đủ.

**Dependency confusion** xuất hiện khi tọa độ nội bộ có thể bị tìm ở public repository và một attacker phát hành package trùng tên. Repository content filtering giúp giới hạn nhóm private. Ví dụ:

```kotlin
repositories {
    exclusiveContent {
        forRepository {
            maven {
                url = uri("https://repo.company.example/maven")
            }
        }
        filter {
            includeGroupByRegex("com\\.example(\\..*)?")
        }
    }
    mavenCentral()
}
```

Đây là **policy minh họa** với địa chỉ placeholder, không chạy được nếu chưa có repository/credentials thật. Khi project tập trung repository declarations trong settings, áp dụng policy tại đúng scope. Đừng đưa token trực tiếp vào build script.

## 12. Rủi ro khi publish library có file dependency

Giả sử producer khai báo:

```kotlin
dependencies {
    implementation(files("libs/vendor.jar"))
}
```

Trong build hiện tại, file JAR có thể là classpath input hợp lệ. Tuy nhiên, khi publish `com.example:my-lib:2.0`, file dependency **không được biểu diễn trong published dependency descriptor** giống một external module GAV. Consumer ngoài repository build không tự lấy được `vendor.jar`; test trong monorepo pass nhưng downstream runtime có thể lỗi.

Cách nghiệm thu: publish ra **repository test có metadata**, tạo **consumer project tách biệt**, chỉ khai báo GAV của library, rồi chạy compile/test/runtime mà không copy `libs/`. Nếu consumer thiếu class, sửa publication/dependency modeling, không yêu cầu người dùng tự chép file.

Đưa binary vào fat JAR/shadow JAR cũng không phải lời giải tự động; phải xem xét license, duplicate classes, resource merging, security scanning và cách cập nhật thư viện.

## 13. Lộ trình chuyển khỏi local JAR

**Trường hợp A — source cùng build:** thay `flatDir { dirs("../lib/build/libs") }` bằng `implementation(project(":lib"))` khi `:lib` là project đã include và có plugin phù hợp. Gradle tự kết nối task/artifact dependencies.

**Trường hợp B — source ở nhiều repositories:** cân nhắc composite build `includeBuild` và dependency substitution, với path/checkout được CI cung cấp rõ ràng. Không dựa vào thư mục `../my-local-lib` chỉ có trên laptop.

**Trường hợp C — binary do nhóm nội bộ phát hành:** publish Maven/Ivy artifacts + POM/`.module` từ producer qua repository nội bộ có permission, version policy, checksum và release workflow. Consumer dùng `group:name:version`, không đọc file trực tiếp.

**Trường hợp D — vendor chỉ cấp JAR:** nếu được phép, tạo publication nội bộ với metadata được xác minh; khai báo transitive dependencies đúng. Trong thời gian chuyển tiếp ghi checksum, license, provenance, owner, ngoại lệ và test runtime. Không mạo danh tọa độ publisher.

**Trường hợp E — đang dùng `mavenLocal()` cho vòng dev:** chỉ bật trong local diagnostics khi cần, không cho CI/release lệ thuộc. Dùng staging repository hoặc source dependency thay thế.

## 14. Kiểm chứng bằng Gradle CLI

Giả định project có Java plugin:

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration compileClasspath
./gradlew dependencyInsight --dependency api --configuration runtimeClasspath
./gradlew run --stacktrace
./gradlew dependencies --configuration runtimeClasspath --info
```

- `dependencies` hiển thị graph; không tự chứng minh artifact bytes/provenance.
- `dependencyInsight` cho biết selection/version của một module có GAV; `files(...)` thuần không có cùng metadata để truy vấn.
- `runtimeClasspath` giúp tìm thiếu class chỉ xuất hiện lúc chạy; `compileClasspath` có thể vẫn đủ để build.
- `--stacktrace` chỉ ra nguyên nhân gốc của task run fail.
- `--info` có thể cho thêm resolution logs nhưng không bảo đảm đầy đủ mọi artifact origin.
- `--refresh-dependencies` kiểm tra lại metadata theo chính sách, **không sinh POM bị thiếu**.
- `--offline` dùng dữ liệu sẵn có, **không chứng minh** runner mới sẽ tải thành công từ repository.

Trong PowerShell thay `./gradlew` bằng `.\gradlew.bat`. Để kiểm tra reproducibility, clone project trong một runner sạch không cài JAR vào Maven local bằng tay. Chạy compile **và** runtime/integration tests; xác minh transitive graph, artifact checksum, repository origin và publication metadata. Đừng xóa cache của người dùng khác để mô phỏng CI.

## 15. Bảo mật và hiệu năng

Các rủi ro khác khi dùng JAR trần hoặc local repositories:

- **Provenance:** không biết chính xác artifact do ai publish, từ đâu, có license gì; tên file có thể bị giả mạo.
- **Integrity:** cùng tên `lib-1.0.jar` có thể bị thay bytes tại local/shared folder; cần checksum/signature và audit.
- **Class shadowing:** `fileTree` và nhiều JAR có duplicate classes có thể tạo kết quả phụ thuộc classpath order.
- **Transitive vulnerabilities:** thiếu graph khiến scanners/lockfiles không thấy hết modules thực sự được gọi hoặc đóng gói.
- **Security confusion:** private groups được hỏi ở public repo khi content filter sai.
- **Cache:** local artifacts mutable làm Gradle hạn chế caching dependency; remote repo có chính sách immutable thuận lợi hơn.
- **Reproducibility:** một developer có Maven local JAR mà CI không có; build pass/fail theo máy.
- **Publication:** consumer không nhận được file dependency nếu nó không được mô tả thành module dependency.

Biện pháp nên kết hợp: trusted repositories, `exclusiveContent`/group filters, immutable releases, dependency locking, dependency verification, SBOM/license scanning, runtime tests và clean CI. **Không công cụ nào tự đoán chính xác dependencies bị thiếu từ một JAR không metadata.**

## 16. Lỗi phổ biến và phương án xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Cách khắc phục |
| --- | --- | --- |
| `NoClassDefFoundError` khi chạy JAR local | Transitive dependency không được khai báo | Tra tài liệu vendor, khai báo đúng và publish metadata |
| Compile pass, `run` fail | Runtime cần helper khác mà compile không cần | Xem `runtimeClasspath`, thử runtime/integration tests |
| FlatDir đứng trước nhưng artifact remote được chọn | Metadata thật được ưu tiên hơn metadata flatDir | Không override bằng flatDir; sửa repository/publisher |
| `Could not find g:n:v` dù có file trong `libs` | Sai tên file/version hoặc folder | Kiểm tra chính xác tên artifact/`dirs` và GAV |
| Local pass, CI không thấy dependency | Chỉ có JAR ở Maven local/laptop | Publish repository nội bộ hoặc dùng source dependency |
| Cùng GAV nhưng binary khác | Maven local bị overwrite | Dùng immutable releases và integrity checks |
| `fileTree` có thêm JAR không mong muốn | Wildcard lấy toàn folder | Chỉ định files rõ hoặc external GAV |
| Bật `artifact()` nhưng thiếu helper | Fallback không tạo metadata bắc cầu | Sửa POM/`.module` hoặc metadata rule có căn cứ |
| Dùng `@jar` rồi runtime thiếu library | Artifact-only bỏ qua module metadata | Dùng GAV thường |
| `maven { url = uri("libs") }` vẫn không tìm được | Flat folder không theo Maven layout | Publish đúng cấu trúc Maven + POM |
| Publication thiếu JAR vendor ở downstream | File dependency không được publish như GAV | Publish vendor dependency có metadata, test consumer ngoài build |
| Internal dependency resolve từ public repo | Thiếu content filter | Dùng `exclusiveContent`/group allowlist |
| Build quá chậm khi tra Maven local | Local repo mutable và caching bị hạn chế | Không dùng Maven local mặc định trong CI/release |
| IDE compile được nhưng CLI fail | IDE có classpath riêng | Dùng Wrapper và clean CLI/CI test |
| `No matching variant` | Metadata/attributes producer không phù hợp | Sửa publication/variant configuration |
| Máy khác không build offline | Cache chưa có distribution/dependency | Chuẩn hóa repository/network, không dựa vào cache riêng |

## 17. Checklist trước khi commit

- [ ] Đã xác nhận artifact origin, owner, license, checksum, GAV và version policy.
- [ ] Không dùng `mavenLocal()` làm nguồn mặc định cho CI/release.
- [ ] Không dùng `flatDir` để override một module có metadata thật.
- [ ] Không dùng wildcard `fileTree` không kiểm soát cho classpath production.
- [ ] Không hardcode path của một user hoặc folder ngoài checkout.
- [ ] Biết những dependencies bắc cầu của JAR legacy, đã có runtime tests.
- [ ] Không coi `metadataSources { artifact() }`/`@jar` là giải pháp tạo metadata.
- [ ] Repositories và content filters đã bảo vệ internal groups.
- [ ] Có Gradle Wrapper, remote/staging repository phù hợp, immutable releases và verification.
- [ ] Publication có POM/Gradle Module Metadata đúng và consumer riêng có thể resolve.
- [ ] Đã thử trên CI runner sạch không cần copy JAR thủ công.
- [ ] Có kế hoạch migration nếu vẫn giữ local JAR.

## 18. Ghi nhớ

- **`flatDir`** tìm artifact file, sinh metadata tạm, **không đọc POM/Ivy** và không tự biết transitives.
- **`mavenLocal()`** có thể chứa metadata, nhưng như cache cục bộ có thể thiếu/ghi đè và không tái lập giữa các máy.
- **Local Maven/Ivy repo** có thể có POM/`.module` thật; vẫn cần đúng layout và policy, khác flat directory.
- **`files(...)`/`fileTree(...)`** không có module metadata; file dependencies không được publish ra ngoài như GAV bình thường.
- **`artifact()`/`@jar`** không sửa được metadata/transitives thiếu.
- **Metadata thật được ưu tiên hơn flatDir** trong Gradle.
- **Thay thế chuẩn:** project/composite dependency khi có source hoặc publish binary + metadata lên repository tin cậy khi phân phối thư viện.

## Tài liệu chính thức

- [Gradle — Repository Types](https://docs.gradle.org/current/userguide/supported_repository_types.html): flatDir, mavenLocal, local Maven/Ivy.
- [Gradle — Declaring Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies_basics.html): file dependencies và những giới hạn khi publish.
- [Gradle — Supported Metadata Formats](https://docs.gradle.org/current/userguide/supported_metadata_formats.html): POM, Ivy, Gradle Module Metadata, artifact fallback.
- [Gradle — Declaring Repositories](https://docs.gradle.org/current/userguide/declaring_repositories_basics.html): repository order, nguồn dependency.
- [Gradle — Securing Repositories](https://docs.gradle.org/current/userguide/securing_repositories.html): content filtering và dependency confusion.
- [Gradle — Resolving Specific Artifacts](https://docs.gradle.org/current/userguide/resolving_specific_artifacts.html): artifact-only notation.
- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html), [Maven Publish](https://docs.gradle.org/current/userguide/publishing_maven.html): cách thay binary local.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html), [Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): kiểm soát versions và integrity.
