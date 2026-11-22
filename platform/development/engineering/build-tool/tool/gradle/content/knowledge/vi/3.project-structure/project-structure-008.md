# Đọc một dự án Gradle có sẵn theo thứ tự các tệp cấu hình

## Mục tiêu bài học

Khi tiếp nhận một repository Gradle chưa quen, bạn cần xác định được: **dự án gồm những project/module nào, dùng bản Gradle và JDK nào, plugin và dependency được khai báo ở đâu, mỗi module có nhiệm vụ gì, task nào dùng để build/test/chạy, và những cấu hình nào có thể khác giữa máy cá nhân với CI**.

Bài này đưa ra **thứ tự đọc thực tế dành cho người học**. Đây không hoàn toàn là thứ tự Gradle thực thi từng script. Các ví dụ chính dùng **Kotlin DSL** (đuôi **.gradle.kts**); dự án dùng **Groovy DSL** (đuôi **.gradle**) có ý nghĩa tương tự nhưng cú pháp khác. Mục tiêu là **hiểu đúng một build hiện có** trước khi sửa hoặc nâng cấp.

Sau bài học, bạn có thể dựng bản đồ root project, subproject và included build; lần theo cấu hình Java, plugin, dependency; nhận ra build logic dùng chung; và xác minh suy luận bằng lệnh Gradle phù hợp.

## 1. Tổng quan: thứ tự nên đọc

Ví dụ cấu trúc dự án:

~~~text
sample-repo/
├── README.md
├── gradlew
├── gradlew.bat
├── gradle/
│   ├── wrapper/
│   │   ├── gradle-wrapper.jar
│   │   └── gradle-wrapper.properties
│   └── libs.versions.toml
├── gradle.properties
├── settings.gradle.kts
├── build.gradle.kts
├── app/
│   ├── build.gradle.kts
│   └── src/main/java/...
├── core/
│   ├── build.gradle.kts
│   └── src/main/java/...
├── build-logic/                # Có thể có: quy ước build dùng chung
│   ├── settings.gradle.kts
│   └── build.gradle.kts
└── .github/workflows/          # Có thể có: CI
~~~

Đây chỉ là cây minh họa. Build đơn project, build nhiều module, composite build, Android hoặc Spring Boot có thể khác đáng kể.

| Thứ tự | File cần đọc | Câu hỏi cần trả lời |
| --- | --- | --- |
| 0 | README và thư mục root | Đâu là gốc repository, đâu là gốc Gradle build? |
| 1 | **gradlew**, **gradlew.bat**, **gradle/wrapper/gradle-wrapper.properties** | Dự án dự kiến dùng Gradle phiên bản nào? |
| 2 | **settings.gradle(.kts)** | Root có tên gì, gồm project và included build nào? Kho plugin/dependency ở đâu? |
| 3 | **gradle.properties** và cấu hình Java/daemon | Những tùy chọn môi trường nào ảnh hưởng build? |
| 4 | **gradle/libs.versions.toml** và catalog khác | Version library và plugin được quản lý ở đâu? |
| 5 | **build.gradle(.kts)** ở root | Có logic dùng chung, plugin, group/version hoặc task root nào? |
| 6 | **build.gradle(.kts)** của từng project | Module nào chạy được, module nào là thư viện, quan hệ phụ thuộc là gì? |
| 7 | **buildSrc/**, **build-logic/**, script **apply(from = ...)** | Logic Gradle nào bị tách khỏi build script chính? |
| 8 | Lockfile, verification metadata, CI và init scripts | Build được khóa phiên bản, xác minh và chạy trên CI thế nào? |
| 9 | Các lệnh **projects**, **tasks**, **dependencies**, **help** | Mô hình build thực tế có khớp với suy luận hay không? |

**Lưu ý an toàn và tính đúng đắn:** file Gradle là mã thực thi. Với repository chưa được tin cậy, nên **đọc tĩnh trước** khi chạy Wrapper hoặc một task bất kỳ. Lệnh **projects**, **help** hay **tasks** vẫn có thể kích hoạt plugin và logic cấu hình. Không tự sửa file hoặc chạy **build** để “thử” khi chưa biết tác động của build.

## 2. Bước 0 — Tìm root build và phạm vi dự án

Trước hết quan sát **settings.gradle(.kts)**, **build.gradle(.kts)**, script Wrapper và vị trí mã nguồn.

- **Root build** thường là thư mục chứa settings và Wrapper.
- **Root project** là project gốc của build; thường cùng thư mục với settings.
- **Subproject** được khai báo bằng **include(...)** trong settings; ví dụ path **:app**, **:core**.
- **Included build** được khai báo bằng **includeBuild(...)**; đó là một **build độc lập** được kết nối vào composite build, không phải subproject thông thường.
- Một repository có thể chứa **nhiều build độc lập**; đừng đồng nhất root Git với mọi root Gradle.
- Build chỉ một project có thể **không có settings.gradle(.kts)**; đây là trường hợp Gradle hỗ trợ.

Không suy ra module chỉ từ tên folder. Settings có thể đổi ánh xạ project tới một thư mục vật lý khác bằng **project(":name").projectDir**. Nếu dự án chứa nhiều file settings, xác định script bạn đang dùng theo root mà lệnh Gradle/CI thực sự chọn.

## 3. Bước 1 — Đọc Gradle Wrapper để xác định công cụ chạy build

Bốn file thường gặp:

~~~text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
~~~

Ví dụ trong **gradle/wrapper/gradle-wrapper.properties**:

~~~properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.0-bin.zip
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
~~~

**Cách đọc:**

- **distributionUrl** chỉ đến bản phân phối **Gradle 9.9.0** trong ví dụ; phiên bản thực tế phải lấy từ file của repository đang đọc. Không coi phiên bản minh họa là yêu cầu nâng cấp.
- Hậu tố **-bin.zip** là phân phối cho chạy build; **-all.zip** còn có tài liệu và mã nguồn.
- **distributionSha256Sum** (nếu khai báo) được dùng để kiểm tra checksum bản phân phối.
- **GRADLE_USER_HOME**, các mục **distributionPath/zipStorePath** cho biết nơi cache phân phối.
- Script **gradlew** (Linux/macOS) hoặc **gradlew.bat** (Windows) gọi Wrapper JAR, tải Gradle nếu cần rồi chạy đúng bản được cấu hình. Dự án có Wrapper thông thường không cần Gradle toàn cục.

Đối với repository đáng tin cậy, sau khi đọc và hiểu cấu hình có thể xác minh:

~~~bash
# Linux/macOS, tại root build
./gradlew --version
~~~

~~~powershell
# Windows PowerShell, tại root build
.\gradlew.bat --version
~~~

Lần đầu có thể cần mạng vì Wrapper tải phân phối. Lệnh **gradle --version** (không có Wrapper) chỉ phản ánh bản Gradle cài trên PATH, có thể khác phiên bản dự án. **Không tự chỉnh Wrapper** khi chưa hiểu yêu cầu tương thích của dự án và plugin.

## 4. Bước 2 — Đọc settings.gradle(.kts): bản đồ cấu trúc build

Gradle đánh giá settings trong giai đoạn **initialization**, trước khi cấu hình các project. Với project nhiều module, đây là file giúp biết **cần đọc build.gradle nào tiếp theo**.

Ví dụ Kotlin DSL:

~~~kotlin
// settings.gradle.kts
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = "shop"
include(":core", ":app")

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}
~~~

Đọc từng phần:

1. **pluginManagement { repositories { ... } }**: nơi tìm plugin được yêu cầu qua plugins DSL. Block này có yêu cầu vị trí đặc biệt trong settings: phải đứng trước những khai báo thông thường.
2. **rootProject.name**: tên root hiển thị trong báo cáo project.
3. **include(":core", ":app")**: project path **:core** và **:app**. Dấu **:** thuộc cú pháp định danh Gradle, không phải đường dẫn package Java.
4. **dependencyResolutionManagement { repositories { ... } }**: kho phân giải dependency của project. Chính sách **repositoriesMode** (nếu có) có thể buộc module không khai báo thêm repo.
5. **includeBuild("build-logic")** (nếu có): một build độc lập phục vụ composite build hoặc convention plugins.
6. **project(":core").projectDir = file("modules/core")** (nếu có): địa điểm file build **:core** nằm ở **modules/core**, không nhất thiết ở thư mục **core**.
7. **versionCatalogs** (nếu có): xác định tên và nguồn catalog dùng chung.

Cùng ý tưởng root và subproject bằng Groovy DSL:

~~~groovy
// settings.gradle
rootProject.name = 'shop'
include 'core', 'app'
~~~

**Phân biệt repositories:**

| Vị trí | Phạm vi chính |
| --- | --- |
| **pluginManagement.repositories** trong settings | Phân giải plugin của plugins DSL |
| **dependencyResolutionManagement.repositories** trong settings | Phân giải dependency của project |
| **repositories** trong build script | Dependency của project đó, nếu chính sách settings cho phép |
| **buildscript.repositories** | Dependency trên classpath script build kiểu buildscript |
| Repository trong included build | Thuộc build độc lập đó, không mặc nhiên dùng chung với root build |

Vì vậy nếu gặp lỗi tải plugin, cần kiểm tra **pluginManagement**; nếu gặp lỗi dependency ứng dụng, cần kiểm tra **dependencyResolutionManagement/repositories** và cách cấu hình dependency. Không mặc định mọi repository xử lý cả hai việc.

Kết quả bước này là bản đồ đơn giản:

~~~text
Build: shop
├── Project :core
└── Project :app
Included builds: chưa có trong ví dụ
Plugin repositories: Gradle Plugin Portal, Maven Central
Dependency repositories: Maven Central
~~~

## 5. Bước 3 — Đọc gradle.properties và xác định JVM

File **gradle.properties** chứa giá trị **key=value**. Ví dụ:

~~~properties
org.gradle.jvmargs=-Xmx1g -Dfile.encoding=UTF-8
org.gradle.parallel=true
org.gradle.caching=true
~~~

- **org.gradle.jvmargs**: cấu hình JVM cho Gradle daemon, không phải cấu hình JVM của ứng dụng mặc định.
- **org.gradle.parallel**: cho phép thực thi song song các tác vụ giữa project trong tình huống phù hợp.
- **org.gradle.caching**: bật build cache, nhưng không đảm bảo mọi task đều có cache.
- **org.gradle.configuration-cache** nếu có: phục vụ tái sử dụng trạng thái cấu hình; khác build cache.
- **org.gradle.java.home** nếu có: một trong các cơ chế lựa chọn JVM chạy Gradle.
- Tên property riêng (ví dụ **deployEnv=dev**) chỉ có ý nghĩa khi script/plugin thực sự đọc nó. Cần tìm nơi sử dụng.

**Nguồn giá trị có thể nằm ngoài Git**: file trong **GRADLE_USER_HOME**, tùy chọn dòng lệnh **-P** / **-D**, biến môi trường hoặc init script. Khi hai máy chạy khác kết quả, cần kiểm tra các nguồn này. Không ghi mật khẩu, token vào bài viết hay log chia sẻ.

**Ba câu hỏi Java khác nhau:**

| Câu hỏi | Nơi cần đọc |
| --- | --- |
| JVM **chạy Gradle** | JAVA_HOME, cấu hình Gradle JVM trong IDE, **org.gradle.java.home**, tiêu chí Daemon JVM và **./gradlew --version** |
| JDK **biên dịch/chạy test** | **java.toolchain**, task JavaCompile/Test hoặc plugin liên quan |
| Bytecode **tương thích Java nào** | **options.release**, **sourceCompatibility/targetCompatibility**, Kotlin jvmTarget hoặc cấu hình tương ứng |

Nếu có **gradle/gradle-daemon-jvm.properties**, hãy xem nó vì Gradle hiện đại có thể dùng tiêu chí JVM để chọn daemon. Không suy ra target Java chỉ từ đầu ra **java -version** trên máy.

**Đừng nhầm ba nơi lưu trữ:**

- **Project root/.gradle/**: metadata/cache cục bộ của build.
- **~/.gradle/** (GRADLE_USER_HOME): cache dependency, phân phối Wrapper, init script và cấu hình người dùng.
- **Project/module/build/**: đầu ra build, thường được sinh lại; không phải source cấu hình chính.

## 6. Bước 4 — Tìm version catalog, lockfile và chính sách phiên bản

Rất nhiều dự án để alias dependency/plugin trong **gradle/libs.versions.toml**. Ví dụ:

~~~toml
# gradle/libs.versions.toml
[versions]
junit = "5.11.4"
slf4j = "2.0.16"

[libraries]
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }
slf4j-api = { module = "org.slf4j:slf4j-api", version.ref = "slf4j" }

[plugins]
spotless = { id = "com.diffplug.spotless", version = "6.25.0" }
~~~

Khi module có:

~~~kotlin
dependencies {
    testImplementation(libs.junit.jupiter)
    implementation(libs.slf4j.api)
}
~~~

hãy lần theo **alias → module coordinate → version.ref → phiên bản khai báo**. Phiên bản trong ví dụ chỉ nhằm giải thích cú pháp.

Các điểm cần hiểu:

- Alias **slf4j-api** trong TOML thường được sinh thành accessor **libs.slf4j.api**.
- Catalog **không tự thêm dependency**; module vẫn phải khai báo **implementation(...)** hoặc cấu hình phù hợp.
- Version khai báo trong TOML **không nhất thiết là phiên bản được resolve cuối cùng** nếu có platform/BOM, constraints hoặc conflict resolution. Cần task **dependencies/dependencyInsight** để xem kết quả thực tế.
- Plugin version có thể ở catalog, **pluginManagement**, block **plugins** hoặc convention plugin. Không kết luận chỉ từ một file.
- Catalog không nhất thiết tên **libs**, cũng có thể được cấu hình từ TOML khác hoặc một build bên ngoài.
- File **gradle.lockfile**/dependency lockfiles giúp khóa phiên bản được resolve; **gradle/verification-metadata.xml** phục vụ kiểm tra artifact/dependency. Cần đọc đúng vai trò, không xóa hoặc tự tạo lại khi chưa biết chính sách nhóm.

## 7. Bước 5 — Đọc build.gradle(.kts) ở root

Root build script có thể chứa plugin, group/version, repository, task chung, công bố artifact hoặc chính sách áp dụng cho project con. Với mỗi block, hỏi **nó tác động đến root, một module, tất cả project hay subprojects?**

Ví dụ:

~~~kotlin
// build.gradle.kts ở root
allprojects {
    group = "com.example"
    version = "1.0.0"
}
~~~

**allprojects** áp dụng trong build hiện tại, bao gồm root và subprojects; không tự động áp dụng cho một **included build** độc lập. **subprojects** thì áp dụng cho subprojects, không bao gồm root.

Đọc theo nhóm:

1. **plugins { ... }**: plugin được áp dụng; **apply false** (khi dùng hợp lệ cho plugin ngoài) khai báo plugin chưa áp dụng tại project hiện tại.
2. **group**, **version**, **description**: metadata của artifact/project.
3. **allprojects/subprojects** và các block điều kiện: quy ước và phạm vi kế thừa.
4. **repositories**, **dependencies**, **configurations**: cơ chế phân giải và cấu hình dependency.
5. **tasks.register**, **tasks.named**, **publishing**, **test**, **jar**: task tùy chỉnh và cách build.
6. **apply(from = "...")** / **apply(plugin = "...")**: điểm chuyển tới script hay plugin khác.

Không phải root project nào cũng chứa mã Java. Một số repository dùng root chỉ để điều phối nhiều module; khi đó **./gradlew :app:build** thường diễn đạt đúng ý hơn là đoán root **build** sẽ tạo ứng dụng.

## 8. Bước 6 — Đọc build.gradle(.kts) của từng module

Theo danh sách **include(...)** trong settings, mở **đúng build script** của từng project. Với mỗi module, trả lời:

**Module thuộc loại nào?** Plugin **java**, **java-library**, **application**, **org.springframework.boot**, **war**, **maven-publish**, plugin Kotlin/Android hoặc convention plugin thường gợi ý chức năng, nhưng cần kiểm tra cấu hình thực tế.

**Module dùng Java nào?** Xem **java.toolchain**, **options.release**, source sets, Kotlin JVM target và cấu hình task.

**Module phụ thuộc gì?** Một số cấu hình quen thuộc:

| Cấu hình | Ý nghĩa thường gặp |
| --- | --- |
| **implementation(...)** | Dependency cho phần triển khai/compile-runtime của module |
| **api(...)** | Dependency của Java library cần lộ trong API cho consumer |
| **compileOnly(...)** | Cần khi compile, không mặc nhiên vào runtime |
| **runtimeOnly(...)** | Dành cho runtime |
| **testImplementation(...)** | Dependency dùng cho test |
| **project(":core")** | Dependency đến project **:core** trong cùng build |
| **platform(...)** | Nhập ràng buộc phiên bản từ platform/BOM |

**Module có task gì?** Các plugin cung cấp task tự động: **application** thường có **run**, **java** có **compileJava**, **test**, **jar**, còn plugin khác có task riêng. Đừng kết luận “không có task” chỉ vì script không chứa lệnh **tasks.register**.

### 8.1. Ví dụ hoàn chỉnh: lần theo một dự án Java hai module

Giả sử repository có cấu trúc:

~~~text
readable-build/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── core/
│   ├── build.gradle.kts
│   └── src/main/java/com/example/core/Greeting.java
└── app/
    ├── build.gradle.kts
    └── src/main/java/com/example/app/Main.java
~~~

**settings.gradle.kts**:

~~~kotlin
rootProject.name = "readable-build"
include(":core", ":app")

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}
~~~

**build.gradle.kts** tại root:

~~~kotlin
allprojects {
    group = "com.example"
    version = "1.0.0"
}
~~~

**core/build.gradle.kts**:

~~~kotlin
plugins {
    id("java-library")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

**app/build.gradle.kts**:

~~~kotlin
plugins {
    application
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("com.example.app.Main")
}

dependencies {
    implementation(project(":core"))
}
~~~

**core/src/main/java/com/example/core/Greeting.java**:

~~~java
package com.example.core;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "Hello, Gradle!";
    }
}
~~~

**app/src/main/java/com/example/app/Main.java**:

~~~java
package com.example.app;

import com.example.core.Greeting;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
~~~

**Diễn giải theo đúng thứ tự đọc:**

1. **Wrapper** xác định Gradle version (xem nội dung file properties thực tế; ở cây minh họa chưa liệt kê số version).
2. **settings.gradle.kts** khai báo root **readable-build**, hai project **:core** và **:app**, cùng Maven Central cho dependency nếu cần.
3. Root **build.gradle.kts** gán metadata **group/version** cho các project.
4. **:core** dùng plugin **java-library**, tạo thư viện Java; khai báo toolchain 17.
5. **:app** dùng plugin **application**, main class là **com.example.app.Main**, dùng toolchain 17 và phụ thuộc **project(":core")**.
6. Source Java **Main** gọi **Greeting.message()** từ **:core**, nên khai báo project dependency là có ý nghĩa.
7. Lệnh **:app:run** sẽ cần các task cần thiết để chuẩn bị classpath, bao gồm phần của **:core**.

Với Wrapper hợp lệ và JDK 17 có sẵn (hoặc môi trường đã cấu hình toolchain resolution), trong root có thể chạy:

~~~bash
# Linux/macOS
./gradlew projects
./gradlew :app:tasks
./gradlew :app:run
~~~

~~~powershell
# Windows PowerShell
.\gradlew.bat projects
.\gradlew.bat :app:tasks
.\gradlew.bat :app:run
~~~

**Stdout của ứng dụng** trong task **:app:run**:

~~~text
Hello, Gradle!
~~~

Gradle còn có log task và thông báo build; ví dụ stdout chỉ trích dòng mà **Main** thực sự in ra. Các class Java này biên dịch được với Java 17+; ví dụ build đủ ý nghĩa để chạy khi có bộ Wrapper hợp lệ như cây thư mục, JDK/toolchain thích hợp và các file có nội dung đúng như trên. Ví dụ không dùng thư viện ngoài, nên Maven Central không phải điều kiện để compile phần mã Java minh họa.

Có thể biểu diễn dependency đã đọc được:

~~~text
:app ------> :core
  |            |
application  java-library
Main         Greeting
~~~

Chiều mũi tên thể hiện **:app cần :core**. Không có căn cứ suy ra chiều phụ thuộc ngược lại.

### 8.2. Nếu script là Groovy DSL

Một số cấu hình cùng ý nghĩa có thể viết như sau:

~~~groovy
// app/build.gradle
plugins {
    id 'application'
}
application {
    mainClass = 'com.example.app.Main'
}
dependencies {
    implementation project(':core')
}
~~~

Cú pháp **id("...")**, **project(":core")**, **mainClass.set(...)** trong Kotlin khác cú pháp chuỗi và gán property ở Groovy, nhưng cùng mô hình Gradle. Khi đọc dự án, ưu tiên hiểu **ý nghĩa API Gradle và plugin** hơn việc ghi nhớ một cách viết cố định.

## 9. Bước 7 — Lần theo logic build được tách ra

File **build.gradle(.kts)** có thể rất ngắn vì logic đã chuyển sang plugin dùng chung. Khi thấy **id("company.java-conventions")** hoặc alias plugin nội bộ, tiếp tục tìm nơi định nghĩa plugin đó.

### 9.1. buildSrc

Thư mục **buildSrc/** (nếu có) được Gradle dùng theo cơ chế build logic riêng, thường chứa mã Kotlin/Groovy/Java và plugin phục vụ build. Hãy đọc **buildSrc/build.gradle(.kts)**, sau đó các source của plugin trong **buildSrc/src/main/**. Cấu hình nằm ở đây có thể cung cấp task và convention cho tất cả module áp dụng.

### 9.2. Included build và convention plugins

Ví dụ settings:

~~~kotlin
pluginManagement {
    includeBuild("build-logic")
}

rootProject.name = "shop"
include(":app", ":core")
~~~

**build-logic/** là một included build cung cấp plugin hoặc build logic; nó có **settings/build script và project của riêng nó**. Nếu **app/build.gradle.kts** chỉ có:

~~~kotlin
plugins {
    id("company.java-application")
}
~~~

không thể kết luận bản Java, repositories, task test hoặc cấu hình publishing chỉ từ đoạn này. Cần tìm **company.java-application** trong **build-logic**, xem plugin đó áp dụng plugin nào và chỉnh thuộc tính nào. Không tự giả định plugin nội bộ giống plugin **application** mặc định.

### 9.3. apply script và plugin bên ngoài

Khi gặp **apply(from = "gradle/common.gradle.kts")**, hãy đọc chính tệp được dẫn chiếu theo vị trí/đường dẫn mà Gradle resolve. Khi gặp plugin từ Gradle Plugin Portal hoặc Maven repository, có thể tra tài liệu plugin và xem phần cấu hình trong module; việc plugin có một ID không đủ để suy ra đầy đủ hành vi, nhất là plugin tùy biến theo phiên bản.

**Nguyên tắc phân tích:** đọc nơi **plugin được áp dụng** và nơi **logic của plugin được định nghĩa**; đánh dấu đâu là cấu hình explicit, đâu là convention hay mặc định từ plugin.

## 10. Bước 8 — Đọc file ảnh hưởng khả năng tái lập và môi trường CI

Sau khi dựng được build, mở các file bổ trợ **nếu repository có**:

- **gradle.lockfile** hoặc lockfile dependency: phiên bản dependency đã được khóa.
- **gradle/verification-metadata.xml**: quy tắc xác minh artifact (checksum/chữ ký tùy thiết lập).
- **gradle/gradle-daemon-jvm.properties**: tiêu chí JVM daemon khi dự án dùng cơ chế này.
- **.github/workflows/*.yml**, **.gitlab-ci.yml**, **Jenkinsfile**: JDK, lệnh Wrapper, profile/flag và bước build/test trên CI.
- **gradle.properties** ở module/build liên quan nếu cơ chế đang dùng đọc nó; kiểm tra nơi và phạm vi property thay vì áp dụng suy đoán.
- **GRADLE_USER_HOME/init.gradle(.kts)** hoặc **init.d/** trên máy, và init script được chỉ định bằng **-I**: có thể thêm repository, listener hoặc chính sách. Đây thường là cấu hình **ngoài Git** nên cần phân biệt với nguồn đã commit.
- Cấu hình publishing, signing, credentials: đánh dấu vị trí và nguồn biến; không sao chép giá trị bí mật.

**Giữa CI và local**, kiểm tra có thật sự chạy cùng Wrapper, cùng JDK/toolchain, cùng tham số build, cùng repository/proxy và cùng credentials hay không. Không nên lý giải sự khác nhau chỉ bằng câu “Gradle lỗi cache” nếu chưa kiểm tra cấu hình.

## 11. Bước 9 — Kiểm chứng bằng câu lệnh có mục đích

Sau khi hiểu và tin cậy build script, dùng Wrapper từ root. Các lệnh dưới đây không tự ý sửa source nhưng **có thể chạy logic cấu hình của Gradle và tải dependency**.

| Lệnh | Giúp trả lời điều gì? |
| --- | --- |
| **./gradlew --version** | Gradle và JVM mà Wrapper sử dụng |
| **./gradlew projects** | Danh sách project mà Gradle nhìn thấy |
| **./gradlew tasks** | Các task phổ biến của project mặc định |
| **./gradlew :app:tasks --all** | Các task của **:app**, kể cả task ít gặp |
| **./gradlew :app:dependencies --configuration runtimeClasspath** | Dependency graph được resolve cho runtimeClasspath của **:app** |
| **./gradlew :app:dependencyInsight --dependency core --configuration runtimeClasspath** | Tại sao dependency khớp tên **core** có mặt/được chọn trong configuration đó |
| **./gradlew :app:properties** | Property hiệu lực của project; **cần thận trọng với dữ liệu nhạy cảm khi chia sẻ log** |
| **./gradlew :app:run --dry-run** | Task graph dự kiến cho **:app:run** khi hỗ trợ, không thực hiện task action |
| **./gradlew help** | Xác nhận build có thể đi qua cấu hình và chạy task help |

Trên Windows PowerShell, thay **./gradlew** bằng **.\gradlew.bat**. Khi báo cáo dependency, phải chọn **configuration tồn tại** trong project; **runtimeClasspath** quen thuộc với Java/application nhưng không phải mọi plugin đều tạo ra nó.

**--dry-run không đồng nghĩa với sandbox**: Gradle vẫn thực hiện bước initialization/configuration; plugin và init script có thể có tác động ở các giai đoạn này. **--offline** có thể giúp tránh truy cập repository trong quá trình phân giải nhưng sẽ thất bại nếu bản Gradle/dependency cần dùng chưa có trong cache. Không dùng **--scan** bừa bãi khi dự án chứa thông tin cần giữ kín vì nó có thể gửi dữ liệu build ra dịch vụ bên ngoài.

### 11.1. Chứng minh một suy luận

Ví dụ bạn nghi ngờ **:app** phụ thuộc **:core**:

1. Trong **settings.gradle.kts**, xác nhận cả **:app** và **:core** được include.
2. Trong **app/build.gradle.kts**, tìm **implementation(project(":core"))** hoặc logic tương đương.
3. Nếu có convention plugin, kiểm tra nó có thay đổi dependency/configuration không.
4. Chạy **./gradlew :app:dependencies --configuration runtimeClasspath** khi build đáng tin cậy.
5. Tìm **project :core** trong báo cáo, đối chiếu kết quả. Nếu không thấy, xem đúng configuration, điều kiện áp dụng dependency và resolution rules thay vì tự phán đoán.

### 11.2. Checklist phân tích nhanh một repository thật

Ghi ra một ghi chú kỹ thuật ngắn sau khi đọc:

~~~text
ROOT BUILD           = ...
WRAPPER VERSION      = ...
SETTINGS DSL         = Groovy / Kotlin
PROJECT PATHS        = :app, :core, ...
INCLUDED BUILDS      = ...
PLUGIN REPOSITORIES  = ...
DEPENDENCY REPOS     = ...
VERSION CATALOG      = ...
ROOT BUILD RULES     = ...
MODULE :app          = plugins, Java toolchain, mainClass, dependencies, tasks
MODULE :core         = plugins, Java toolchain, public API, dependencies
SHARED BUILD LOGIC   = buildSrc / build-logic / scripts / none
LOCK / VERIFICATION  = ...
CI BUILD COMMAND     = ...
UNRESOLVED QUESTIONS = ...
~~~

Đây là **mẫu ghi chú phân tích**, không phải file bắt buộc của Gradle. Hãy điền bằng dữ liệu quan sát được; ghi **chưa xác minh** nếu không có đủ bằng chứng. Đừng tự suy đoán plugin, repository hoặc phiên bản bị ẩn sau cấu hình môi trường.

## 12. Lỗi đọc hiểu thường gặp

| Nhầm lẫn | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| “Tên folder là tên Gradle module” | **include(...)** có thể khai báo project path khác, **projectDir** có thể ánh xạ chỗ khác | Đọc **settings** trước khi mở build script con |
| “Có thư mục build-logic nghĩa là có subproject :build-logic” | **includeBuild** tạo included build độc lập | Phân biệt **include** và **includeBuild** |
| “gradle --version là bản của repo” | Đó có thể là Gradle trên PATH | Đọc Wrapper và chạy **./gradlew --version** |
| “Mọi dependency repo đều nằm trong build.gradle” | Có thể tập trung trong **settings** hoặc do convention/enterprise init script cung cấp | Kiểm tra settings, module và môi trường |
| “Không thấy version dependency trong module nghĩa là không khóa version” | Version catalog, platform/BOM, constraints, lockfiles có thể quyết định version | Truy alias rồi xem graph được resolve |
| “Không thấy task định nghĩa trong file nghĩa là task không tồn tại” | Plugin tạo task, hoặc đăng ký lazy | Xem plugins và dùng **tasks --all** |
| “Mọi project đều dùng JDK trên PATH để compile” | Java Toolchains có thể chọn JDK khác | Xem toolchain, options.release và Gradle JVM |
| “Root build.gradle áp dụng cho included build” | Included build có cấu hình/project độc lập | Đọc settings và build scripts của included build |
| “Xóa .gradle/build sẽ giải thích source cấu hình” | Đó phần lớn là cache/output, không phải nguồn build | Bắt đầu từ settings, scripts, properties, catalog |
| “Lệnh --dry-run hoàn toàn không thực thi mã” | Gradle vẫn chạy initialization/configuration | Chỉ chạy build đã được đánh giá đáng tin cậy |
| “Mở một file build là đủ hiểu dự án” | Logic có thể nằm ở convention plugins, buildSrc và init scripts | Lần theo plugin, applied scripts và cấu hình môi trường |

## 13. Bài tập tự kiểm tra

**Tình huống A:** Settings ghi **include(":service")** nhưng không có thư mục **service/**. Bạn nên kiểm tra điều gì? — Tìm **project(":service").projectDir** hoặc logic ánh xạ project path; nếu không có, mới xem khả năng thiếu module/file. Không tạo folder ngẫu nhiên.

**Tình huống B:** **app/build.gradle.kts** chỉ có **plugins { id("company.application") }** mà vẫn xuất hiện task **run**. Vì sao? — Plugin nội bộ có thể áp dụng **application** và cấu hình task; tìm định nghĩa trong **buildSrc**, **build-logic** hoặc plugin artifact tương ứng.

**Tình huống C:** Trong TOML khai báo **slf4j=2.0.16** nhưng báo cáo runtime dependency dùng bản khác. Có mâu thuẫn không? — Không nhất thiết: cần xem constraints/platform/conflict resolution và kết quả **dependencyInsight**.

**Tình huống D:** CI chạy được, máy local báo lỗi JDK. Bạn kiểm tra theo thứ tự nào? — Bản Gradle ở Wrapper; JDK chạy Gradle và Gradle JVM; Java toolchain, **options.release**; cấu hình CI, env/gradle.properties ngoài repo và khả năng cung cấp JDK được yêu cầu.

**Tình huống E:** Root build không khai báo Java plugin, nhưng **:app:run** hoạt động. Có gì bất thường? — Không. **:app** áp dụng application plugin ở module hoặc qua convention plugin; root không nhất thiết là application.

## Tài liệu tham khảo chính thức

- [Gradle — Settings File Basics](https://docs.gradle.org/current/userguide/settings_file_basics.html): root, project path và include.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): file Wrapper và bản phân phối.
- [Gradle — Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html): initialization, configuration, execution.
- [Gradle — Anatomy of a Gradle Build](https://docs.gradle.org/current/userguide/gradle_directories.html): vai trò các file/thư mục.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): mô hình nhiều project.
- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html): alias library/plugin và TOML.
- [Gradle — Organizing Build Logic](https://docs.gradle.org/current/userguide/organizing_build_logic.html): quy tắc và plugin dùng chung.
- [Gradle — Initialization Scripts](https://docs.gradle.org/current/userguide/init_scripts.html): cấu hình ngoài repository.

**Thực hành cần nhớ:** đi từ **gốc + Wrapper → settings → properties/catalog → root build → từng module → shared build logic → lock/CI → đối chứng bằng task**. Mỗi kết luận nên chỉ ra **file hoặc lệnh** cung cấp bằng chứng; như vậy bạn sẽ hiểu dự án Gradle mới một cách có hệ thống mà không phải đoán từ tên thư mục hay phiên bản Gradle trên máy.