# `includeBuild` trong Settings và build được include: Composite build của Gradle

## 1. Composite build giải quyết vấn đề gì?

Giả sử ứng dụng Java phụ thuộc thư viện nội bộ `com.acme.learning:message-lib:1.0.0`. Ở quy trình thông thường, nhóm phát triển thư viện phải **build và publish** JAR vào Maven repository (hoặc Maven Local), rồi ứng dụng mới tải được phiên bản đã xuất bản. Khi sửa đồng thời ứng dụng và thư viện, chu trình publish–consume lặp lại làm chậm phát triển và dễ thử nhầm bản cũ.

**Composite build** cho phép Gradle kết hợp **nhiều Gradle builds vốn độc lập** trong **một build tree**. Build chính khai báo trong `settings.gradle.kts`:

~~~kotlin
includeBuild("library-kit")
~~~

Khi một project của included build có `group` và `name` phù hợp với một external module dependency trong build tiêu thụ, Gradle có thể **substitute dependency module đó bằng project nguồn**, tự nối các task tạo artifact cần thiết. Nhờ vậy, chỉnh sửa mã trong thư viện có thể được ứng dụng sử dụng ngay ở lần build sau **mà không cần publish JAR trước**.

Điều cần nhớ:

- `include("app")` thêm **subproject** vào **cùng một Gradle build**.
- `includeBuild("library-kit")` thêm **một Gradle build khác** vào composite. Build ấy có Settings, project hierarchy, repositories, plugins và properties **riêng**.
- `implementation(project(":shared"))` dùng khi `:shared` là subproject **trong cùng build**.
- `implementation("com.acme.learning:message-lib:1.0.0")` vẫn là notation phù hợp khi module đến từ một **included build**; Gradle có thể tự substitute bằng local project có tọa độ tương ứng.
- `pluginManagement { includeBuild("build-logic") }` là use case quan trọng khi included build **cung cấp Gradle plugin**, đặc biệt settings plugin hoặc convention plugin cần resolve sớm.

Composite build hữu ích cho đồng phát triển library–consumer, tổ chức monorepo thành các builds độc lập và chia sẻ build logic. Nhưng nó **không** có nghĩa mọi task trong included builds tự chạy khi bạn gọi `./gradlew build` từ root, hoặc mọi cấu hình của root được thừa hưởng bởi các builds con.

Bài học sử dụng **Gradle Kotlin DSL** và **Java 17**. Ví dụ chính đầy đủ gồm một ứng dụng Java, một thư viện được include và các JUnit tests. Phần plugin build-logic là **phương án kiến trúc khác**, được đặt riêng để tránh trộn hai mục đích.

## 2. Build, project, subproject, included build và build tree

Các thuật ngữ dễ bị nhầm:

| Thuật ngữ | Định nghĩa | Ví dụ |
| --- | --- | --- |
| Root build | Build mà Gradle Wrapper đang gọi làm điểm vào. | Thư mục `consumer-app/`. |
| Root project | Project đầu tiên của một build, có project path `:` trong build ấy. | `consumer-app` root. |
| Subproject | Project được khai báo bằng `include(...)` trong **cùng Settings**. | `:app`. |
| Included build | Một build khác được ghép bằng `includeBuild(...)`, có Settings riêng. | `library-kit/`. |
| Composite build | Build tree gồm root build và các included builds. | Consumer + library. |
| Build-tree path | Path có thêm **build identity** để nhận diện tasks/projects toàn tree. | Thường `:library-kit:jar`. |
| Dependency substitution | Đổi yêu cầu external module thành local project dependency. | Module `message-lib` → project của included build. |
| Plugin build | Included build cung cấp Gradle plugins để dùng trong build scripts. | `build-logic`. |

Một sơ đồ:

~~~text
Composite build tree
|
+-- Root build: consumer-app/
|    |-- settings.gradle.kts
|    |-- root project ":"
|    +-- subproject ":app"
|
+-- Included build: library-kit/
     |-- settings.gradle.kts (riêng)
     |-- root project ":" TRONG library-kit
     +-- build.gradle.kts của library-kit
~~~

Mỗi build có một root project path `:` **trong phạm vi build riêng**. Để Gradle CLI phân biệt, build tree sử dụng build identity/path; vì vậy task ở root của included build có thể được gọi từ root build bằng dạng `:library-kit:jar`, nhưng API `IncludedBuild.task(":jar")` lại dùng task path **bên trong included build**.

**Không gọi** một project trong included build bằng `project(":library-kit")` của root build, trừ khi bạn đã khai báo `library-kit` là subproject thật của root (điều này là cấu trúc khác). Đây là lỗi phổ biến nhất khi mới học composite build.

## 3. `include(...)` khác `includeBuild(...)` thế nào?

### 3.1. Multi-project build

~~~kotlin
// settings.gradle.kts
rootProject.name = "shop"

include("app", "shared")
~~~

Lúc này:

- `:app` và `:shared` thuộc cùng một Settings/root build.
- App có thể dùng `implementation(project(":shared"))`.
- `./gradlew :shared:build` gọi subproject shared.
- Các subprojects chịu tác động của shared/root build logic theo những plugin và configurations đã áp dụng.
- `./gradlew build` từ root thường chọn các task `build` phù hợp trong cây subproject theo task-selector semantics.

### 3.2. Composite build

~~~kotlin
// settings.gradle.kts
rootProject.name = "shop"

include("app")
includeBuild("shared-library")
~~~

Lúc này:

- `:app` là subproject của root build.
- `shared-library` là **một build độc lập**, không phải `:shared-library` subproject trong root.
- Included build có thể có `settings.gradle.kts`, nhiều subprojects, version catalog và repository configuration riêng.
- App tham chiếu thư viện đó qua tọa độ module, rồi composite dependency substitution chọn local source nếu match.
- Task của included build được gọi bằng build-tree path hoặc `gradle.includedBuild(...).task(...)`.

| Câu hỏi | `include("shared")` | `includeBuild("shared")` |
| --- | --- | --- |
| Thêm thứ gì? | Một project thuộc root build. | Một build độc lập. |
| Settings riêng bắt buộc? | Không; dùng Settings root. | Nên có Settings riêng để standalone và xác định project names. |
| Dependency ở app | `project(":shared")`. | Module GAV được substitute, ví dụ `"com.acme:shared:1.0"`. |
| Scope của project path `:` | Root project của cùng build. | Mỗi build có root project riêng. |
| Chia sẻ root repos/properties tự động? | Có thể áp chung nếu root cấu hình subprojects. | **Không** mặc định; từng build riêng. |
| Có thể chạy build độc lập? | Subproject gắn root Settings. | Included build có thể chạy riêng bằng Wrapper/Gradle phù hợp. |
| Có thể thay unpublished library? | Không cần publish vì là project dependency. | Không cần publish nhờ composite substitution. |
| Task path qua CLI | `:shared:jar`. | Thường `:shared:jar` **dưới build identity** nếu không xung đột, nhưng semantics thuộc included build. |

Dòng cuối cần hiểu theo **build-tree naming**: một included build có tên `shared` và một subproject root cùng tên sẽ bị xung đột namespace; Gradle yêu cầu build-tree paths không trùng. Đừng dùng hai cấu trúc có cùng path rồi kỳ vọng Gradle tự đoán.

## 4. Lab hoàn chỉnh: Java 17 app tiêu thụ thư viện từ included build

Mục tiêu: build chính `consumer-app` có subproject `:app`; thư viện source nằm trong included build `library-kit`. Khi app khai báo `implementation("com.acme.learning:message-lib:1.0.0")`, Gradle dùng source của local `library-kit` thay vì tải JAR `message-lib` từ repository.

### 4.1. Cấu trúc file

~~~text
consumer-app/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── app/
│   ├── build.gradle.kts
│   └── src/
│       ├── main/java/demo/app/Main.java
│       └── test/java/demo/app/MainTest.java
└── library-kit/
    ├── settings.gradle.kts
    ├── build.gradle.kts
    └── src/
        ├── main/java/demo/lib/Messages.java
        └── test/java/demo/lib/MessagesTest.java
~~~

**Điều kiện chạy:** Gradle Wrapper ở root hoạt động, một JDK 17 phù hợp được tìm thấy hoặc provisioned, và Maven Central truy cập được để lấy JUnit cho các tasks test lần đầu. Nếu chỉ chạy `:app:run`, code sản phẩm không dùng library bên thứ ba; local included library sẽ được build từ source. Không cần publish `message-lib` lên Maven Local.

### 4.2. Root `consumer-app/settings.gradle.kts`

~~~kotlin
rootProject.name = "consumer-app"

include("app")

// Đường dẫn tương đối tới root directory của build khác.
includeBuild("library-kit")
~~~

Đọc kỹ:
- `include("app")` tạo root-build subproject `:app`.
- `includeBuild("library-kit")` gắn **toàn bộ build** nằm ở thư mục `library-kit` vào build tree.
- Đường dẫn `"library-kit"` được resolve **tương đối với Settings directory** của `consumer-app`.
- `library-kit/settings.gradle.kts` là Settings độc lập; không bị thay bằng root Settings.
- Không khai báo `include("library-kit")` trong root build: đó là cấu trúc subproject khác.
- Không viết `project(":library-kit")` trong app dependencies: included build không phải root subproject.

### 4.3. Root `consumer-app/build.gradle.kts`

~~~kotlin
plugins {
    base
}

// Một root aggregator tùy chọn cho hai nhóm kiểm thử.
tasks.register("verifyComposite") {
    group = "verification"
    description = "Tests app and the independently included library"

    dependsOn(":app:test")
    dependsOn(gradle.includedBuild("library-kit").task(":test"))
}
~~~

Root áp **Base plugin** để có các lifecycle tasks như `build`, `check`, `clean`. `verifyComposite` là task được tác giả **đăng ký thêm**; nó không xuất hiện mặc định khi gọi `includeBuild`.

Điểm cần lưu ý:
- `gradle.includedBuild("library-kit")` trả về **IncludedBuild API**.
- `.task(":test")` tham chiếu task `test` tại **root project bên trong** `library-kit`.
- `dependsOn(":app:test")` dùng task path của project `:app` trong root build.
- Cả hai tasks được đưa vào graph khi gọi `./gradlew :verifyComposite`.
- Nếu không đăng ký aggregator, `./gradlew :build` ở root không tự yêu cầu toàn bộ `library-kit:build`.

### 4.4. `consumer-app/app/build.gradle.kts`

~~~kotlin
plugins {
    application
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.app.Main")
}

dependencies {
    // Vẫn dùng tọa độ external module như khi library đã publish.
    implementation("com.acme.learning:message-lib:1.0.0")

    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Ở đây version module `1.0.0` làm dependency declaration rõ và phù hợp ví dụ published release. **Composite substitution tự động dựa chủ yếu vào `group:name` của included project**, không phải chứng minh version request bằng đúng `project.version`. Các yêu cầu version khác của module cùng `group:name` cũng có thể bị substitute bằng source local. Vì thế **không xem composite substitution là một phép kiểm tra version published artifact chính xác**; điều này sẽ được giải thích kỹ ở mục 9.

`mavenCentral()` phục vụ JUnit dependencies và cũng cho phép fallback module resolution khi bỏ includeBuild; trong lab này `message-lib` **không cần** có trên Maven Central do local included build thay thế.

### 4.5. `consumer-app/app/src/main/java/demo/app/Main.java`

~~~java
package demo.app;

import demo.lib.Messages;

public final class Main {
    private Main() {
    }

    public static String message() {
        return "COMPOSITE_OK=" + Messages.text();
    }

    public static void main(String[] args) {
        System.out.println(message());
        System.out.println("ARG_COUNT=" + args.length);
    }
}
~~~

Nếu module dependency không resolve được, Java compiler sẽ báo không tìm thấy `demo.lib.Messages`. Đây là một test rõ ràng về việc app thật sự cần class của included library, không chỉ in hard-coded text.

### 4.6. `consumer-app/app/src/test/java/demo/app/MainTest.java`

~~~java
package demo.app;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MainTest {
    @Test
    void usesLocalLibraryThroughComposite() {
        assertEquals(
            "COMPOSITE_OK=hello from local source",
            Main.message()
        );
    }
}
~~~

### 4.7. Included `library-kit/settings.gradle.kts`

~~~kotlin
rootProject.name = "message-lib"
~~~

Đây là **Settings riêng** của included build. Tên `message-lib` là **project name** của root project trong build đó; nó khác tên thư mục `library-kit`, vốn thường được dùng làm build identity/path khi include.

Sự tách biệt tên này là chủ đích:
- External module name dùng để auto-substitute: `message-lib`.
- Included build directory/identity thường là `library-kit`.
- Task path bên trong included build vẫn là `:jar`/`:test`.
- Composite CLI path thường là `:library-kit:jar`/`:library-kit:test`, tùy configured build name và không có collision.

### 4.8. Included `library-kit/build.gradle.kts`

~~~kotlin
plugins {
    `java-library`
}

group = "com.acme.learning"
version = "1.0.0"

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Với Settings ở mục 4.7:
- `project.group` = `com.acme.learning`.
- `project.name` = `message-lib`.
- Gradle mặc định xác định included build có thể cung cấp module `com.acme.learning:message-lib`.
- App dependency `com.acme.learning:message-lib:1.0.0` có **group:name khớp**, được substitute bằng project nguồn.
- Build thư viện có `repositories { mavenCentral() }` riêng. Root/app repository settings **không tự thừa hưởng** vào included build.
- Build thư viện **có thể được mở/chạy độc lập** nếu có Gradle tương thích và JDK 17.

### 4.9. `library-kit/src/main/java/demo/lib/Messages.java`

~~~java
package demo.lib;

public final class Messages {
    private Messages() {
    }

    public static String text() {
        return "hello from local source";
    }
}
~~~

### 4.10. `library-kit/src/test/java/demo/lib/MessagesTest.java`

~~~java
package demo.lib;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MessagesTest {
    @Test
    void returnsMessage() {
        assertEquals("hello from local source", Messages.text());
    }
}
~~~

### 4.11. Thực hiện kiểm chứng trong composite

Từ thư mục root `consumer-app`:

~~~bash
./gradlew --version
./gradlew projects

# Xem dependency resolution: local included project được thay vào.
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --configuration runtimeClasspath --dependency message-lib

# Chạy chương trình trong app (không publish thư viện).
./gradlew -q :app:run --args="alpha beta"

# Chạy từng project/build và aggregator.
./gradlew :app:test
./gradlew :library-kit:test
./gradlew :verifyComposite

# Xem task graph thực tế trước khi chạy.
./gradlew :app:run --dry-run
./gradlew :verifyComposite --dry-run
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat projects
.\gradlew.bat :app:dependencies --configuration runtimeClasspath
.\gradlew.bat -q :app:run --args="alpha beta"
.\gradlew.bat :app:test
.\gradlew.bat :library-kit:test
.\gradlew.bat :verifyComposite
~~~

**Stdout do `Main.main` in, chính xác hai dòng:**

~~~text
COMPOSITE_OK=hello from local source
ARG_COUNT=2
~~~

Dòng báo dependency substitution trong `:app:dependencies` có thể chứa ý tưởng `com.acme.learning:message-lib:1.0.0 → project ...`, nhưng **định dạng và build-tree paths hiển thị thay đổi theo Gradle version**; không coi một dòng transcript cố định là output duy nhất hợp lệ. Quan trọng là Gradle chọn **local included project** thay vì dùng published JAR.

`:app:run` có thể trigger compile/archive tasks trong `library-kit` do app cần library artifact. Tuy nhiên nó **không mặc nhiên chạy toàn bộ `library-kit:test`**: test thuộc lifecycle riêng. `:verifyComposite` được tạo để yêu cầu cả hai nhóm tests rõ ràng.

### 4.12. Xác minh Java 17 độc lập với Gradle

Nếu muốn tách lỗi Java syntax khỏi lỗi Gradle composite, tại root trên Linux/macOS:

~~~bash
mkdir -p build/manual/lib build/manual/app

javac -encoding UTF-8 -d build/manual/lib \
    library-kit/src/main/java/demo/lib/Messages.java

javac -encoding UTF-8 -cp build/manual/lib \
    -d build/manual/app \
    app/src/main/java/demo/app/Main.java

java -cp build/manual/lib:build/manual/app demo.app.Main alpha beta
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/manual/lib | Out-Null
New-Item -ItemType Directory -Force build/manual/app | Out-Null

javac -encoding UTF-8 -d build/manual/lib library-kit/src/main/java/demo/lib/Messages.java
javac -encoding UTF-8 -cp build/manual/lib -d build/manual/app app/src/main/java/demo/app/Main.java

java -cp "build/manual/lib;build/manual/app" demo.app.Main alpha beta
~~~

Hai cách in cùng hai dòng Java nêu trên. **Dấu `:` trong Java classpath ở Linux/macOS là dấu phân tách paths, không phải Gradle project path**; Windows dùng `;`. Biên dịch thủ công **chỉ kiểm chứng mã Java và classpath**, không chứng minh Gradle đã cấu hình substitution đúng. Muốn kiểm tra cơ chế composite, dùng `:app:dependencies` và chạy Gradle.

## 5. Included build là build độc lập, không chia sẻ Settings

Mỗi included build có thể có:

~~~text
library-kit/
├── settings.gradle.kts
├── build.gradle.kts
├── gradle.properties
├── gradle/libs.versions.toml
└── src/...
~~~

Sự độc lập có nhiều hệ quả:

- **Repositories:** `repositories` và `pluginManagement.repositories` của build chính không tự trở thành repositories của included build.
- **Plugins:** áp plugin ở root build không có nghĩa included build cũng áp plugin ấy.
- **Version catalog:** `libs` của build chính không tự có trong build kia.
- **`buildSrc`:** buildSrc của build này không tự là buildSrc của build khác.
- **Gradle properties:** các user-defined properties viết trong root build's `gradle.properties` **không tự hiện** trong included build. Properties truyền qua CLI `-P...` và system properties `-D...` có thể đi vào invocation theo rules của Gradle.
- **Runtime Gradle properties:** một số `org.gradle.*` dành cho runtime/feature toàn invocation được đọc từ root build và áp dụng toàn invocation; không suy rằng mọi bản sao trong included-build `gradle.properties` đều có hiệu lực.
- **Build lifecycle:** root `:build` không tự thực thi mọi included build `:build`.
- **Toolchain/JDK:** included build có thể khai báo Java toolchain riêng; Gradle Wrapper đang chạy composite quyết định Gradle runtime version cho invocation đó.
- **Task paths:** khi gọi từ root build, phải phân biệt build-tree prefix với task path bên trong build.

Ví dụ: root build có `gradle.properties`:

~~~properties
teamFeatureFlag=enabled
~~~

Không mặc định trông đợi `providers.gradleProperty("teamFeatureFlag")` trong included build đọc được giá trị này nếu không truyền theo cơ chế được hỗ trợ. Có thể cung cấp qua CLI:

~~~bash
./gradlew -PteamFeatureFlag=enabled :library-kit:help
~~~

hoặc đặt property trong `library-kit/gradle.properties` để build đó chạy độc lập, tùy contract. Không copy secrets từ root sang included build bằng logging hoặc hard-coded build scripts; dùng CI secrets/environment khi cần.

## 6. Gradle nhận biết build identity và task paths thế nào?

Một included build có **build identity** giúp phân biệt toàn build tree. Nó thường dựa trên tên thư mục của included build. Trong lab, thư mục là `library-kit` và root project bên trong có tên `message-lib`.

Ví dụ từ root:

~~~bash
./gradlew :app:compileJava
./gradlew :library-kit:compileJava
./gradlew :library-kit:test
./gradlew :library-kit:jar
~~~

Task `:library-kit:test` là **task trong root project của included build**, không phải `:library-kit` subproject của consumer-app. Khi included build có thêm subprojects, task path mở rộng như:

~~~text
:library-kit:core:test
~~~

với `core` là subproject bên trong `library-kit`.

Khi dùng API của included build trong root `build.gradle.kts`:

~~~kotlin
tasks.register("runLibraryTests") {
    dependsOn(
        gradle.includedBuild("library-kit").task(":test")
    )
}
~~~

`task(":test")` là project-root task path **bên trong** library-kit, không phải global path `:library-kit:test`.

### Đổi build name để tránh xung đột

Gradle yêu cầu **unique build paths**, và included build path không được chồng lên project path đã có của root. Nếu thư mục `tools` xung đột với root subproject `:tools`, có thể đổi included build identity trong Settings:

~~~kotlin
includeBuild("tools") {
    name = "tools-source"
}
~~~

Đây là **phương án thay thế tên included build**, không dùng cùng lúc với `includeBuild("tools")` trùng path. Khi đó dùng build name đã đặt với `gradle.includedBuild("tools-source")` và task tree path tương ứng.

Không giải quyết namespace collision bằng cách đổi package Java hay Maven group một cách ngẫu nhiên: collision đang nằm ở **Gradle build-tree path**, không phải Java package.

### Nested composite builds

Một included build có thể include build khác. Gradle hiện hành **flatten** cấu trúc composite trong build tree: các included builds được coi cùng một parent về mặt identity/graph, không phải luôn tạo hierarchy sâu theo từng lần include. Tránh đoán task path theo số cấp thư mục trên filesystem; dùng `projects`/task report và `gradle.includedBuild(...)` với build identity thực.

## 7. Dependency substitution tự động: group và name

Gradle inspect các projects trong included builds và tạo substitution rules theo cặp:

~~~text
project.group : project.name
~~~

Trong lab:

~~~text
Library project group = com.acme.learning
Library project name  = message-lib

External request = com.acme.learning:message-lib:1.0.0
                         |          |
                         +----------+  match group:name
                                    |
                 substitute → included project source
~~~

Version `1.0.0` của app dependency hữu ích khi không chạy composite, nhưng **default substitution dựa vào group/name, không chọn published module theo version request**. Vì vậy một project dùng `com.acme.learning:message-lib:0.9.0` vẫn có thể được substitute sang local source của project version 1.0.0.

**Hệ quả:** nếu đang kiểm thử **đúng binary đã publish ở version 0.9.0**, không dùng composite substitution mặc định rồi khẳng định kết quả là binary 0.9.0. Bạn đang test **source hiện tại**. Muốn so sánh với bản published, dùng build/configuration độc lập với substitution hoặc cấu hình vô hiệu hóa substitution cho configuration kiểm thử (mục 11).

### Khi substitution không tự hoạt động

- Included project không đặt `group`; group mặc định có thể là `undefined`.
- `rootProject.name` hoặc `project.name` không khớp artifact ID đã publish.
- Thư viện publish với `artifactId` khác project name.
- Có nhiều publications cho một project và module coordinates không phản ánh default project identity.
- Custom variants/publication metadata khác project `default` configuration.
- Included build chưa được include vào build đang chạy hoặc included path không tồn tại.
- Dependency thuộc module khác group/name; chỉ chung version hoặc Java package là không đủ.

**Lỗi cần tránh:** đổi tên thư mục `library-kit` không tự đổi `rootProject.name = "message-lib"` hoặc `project.group`. Build identity và module coordinates là **hai hệ tên khác nhau**.

## 8. Explicit dependency substitution khi module name không khớp

Đôi khi thư viện local có project name `message-lib` nhưng published Maven module tên `legacy-messages`. Gradle auto-substitution không tự biết alias ấy.

Trong `consumer-app/settings.gradle.kts`, có thể viết:

~~~kotlin
rootProject.name = "consumer-app"
include("app")

includeBuild("library-kit") {
    dependencySubstitution {
        substitute(
            module("com.acme.learning:legacy-messages")
        ).using(
            project(":")
        )
    }
}
~~~

**Đây là một Settings file thay thế** cho mục 4.2, không thêm một `includeBuild("library-kit")` thứ hai. Ở bên trong block:
- `module("com.acme.learning:legacy-messages")` chỉ external module coordinate cần thay.
- `project(":")` là **root project của included build library-kit**, không phải root project của consumer-app.
- `using(project(":"))` gắn module external với local project.
- Nếu included build chứa subproject `:core` thì dùng `project(":core")` trong scope của included build.

App có thể khai báo:

~~~kotlin
dependencies {
    implementation("com.acme.learning:legacy-messages:1.0.0")
}
~~~

và Gradle sử dụng project `library-kit` đúng theo rule. Đây là **phương án minh họa**, không dán nó vào lab nguyên bản nếu app vẫn dùng `message-lib` và không cần alias.

### Version và explicit substitution

Explicit module substitution như trên thường dựa trên module group:name; nó **không mặc định đặt điều kiện phải trùng đúng version**. Nếu chính sách test đòi version-specific substitution, cần xây rule/conditional phù hợp qua resolution strategy và kiểm thử graph, không chỉ giả định Gradle sẽ so version tự động.

### Rule áp ở đâu?

Substitution khai báo trong một composite **không tự lan xuyên tất cả builds**. Khi chạy `library-kit` một mình, Settings của chính library-kit không biết alias rule mà consumer đã khai báo, trừ khi build đó tự cấu hình quy tắc tương ứng. Nên ưu tiên căn chỉnh `group`/`project.name` theo publication coordinates khi có thể, vì cho auto-substitution ít surprise hơn.

## 9. Multi-project included build: một build có thể có nhiều modules

`includeBuild` thêm **toàn bộ build**, không chỉ root project. Ví dụ cấu trúc:

~~~text
consumer-app/
├── settings.gradle.kts
└── utility-build/
    ├── settings.gradle.kts
    ├── build.gradle.kts
    ├── text-utils/build.gradle.kts
    └── number-utils/build.gradle.kts
~~~

Included Settings:

~~~kotlin
rootProject.name = "utility-build"
include("text-utils", "number-utils")
~~~

Build có thể cấu hình group trong mỗi subproject:

~~~kotlin
// utility-build/text-utils/build.gradle.kts
plugins {
    `java-library`
}

group = "com.acme.utils"
version = "1.0.0"
~~~

và tương tự `number-utils`.

Consumer dependencies:

~~~kotlin
dependencies {
    implementation("com.acme.utils:text-utils:1.0.0")
    implementation("com.acme.utils:number-utils:1.0.0")
}
~~~

Nếu cả hai included projects có group/name khớp, Gradle có thể substitute từng module riêng. Chạy task từ root composite:

~~~bash
./gradlew :utility-build:text-utils:jar
./gradlew :utility-build:number-utils:build
~~~

**Các đoạn này là mảnh cấu hình**, không phải một lab Java đầy đủ: cần source files, JDK và plugin settings thích hợp. Mục đích là mô tả cách `includeBuild` cung cấp nhiều projects và cách task paths bổ sung một build prefix.

Tuy vậy, **không** dùng:

~~~kotlin
// Phản ví dụ: included project không thuộc root project hierarchy.
dependencies {
    implementation(project(":utility-build:text-utils"))
}
~~~

Cú pháp project path này không tự tham chiếu included build. Hãy dùng external module coordinates và Gradle substitution.

## 10. Gọi task trong included build qua CLI và IncludedBuild API

Có hai trường hợp:

### 10.1. Gọi trực tiếp từ terminal

~~~bash
./gradlew :library-kit:jar
./gradlew :library-kit:test
./gradlew :library-kit:build
~~~

Các paths trên dùng build identity `library-kit` của lab. Khi included build là multi-project có `:core`, full task path có thể là `:library-kit:core:jar`.

**Không hiểu** `./gradlew build` từ consumer root như một lệnh sẽ tự chạy mọi `build` task của tất cả included builds. Task selector `build` hoạt động trong root build project hierarchy; included builds được kích hoạt khi dependency substitution/task dependencies yêu cầu. Muốn kiểm thử cả app và library, chọn task rõ hoặc dùng root aggregator `verifyComposite`.

### 10.2. Root task phụ thuộc included build task

~~~kotlin
tasks.register("runLibraryJar") {
    dependsOn(
        gradle.includedBuild("library-kit").task(":jar")
    )
}
~~~

Đây là mảnh cho root project. Chạy:

~~~bash
./gradlew :runLibraryJar
~~~

Gradle thêm task JAR của included build vào graph. API `gradle.includedBuild("library-kit")` có ích vì phụ thuộc đúng **build identity**, còn `task(":jar")` có semantics path **bên trong included build**.

### 10.3. Điều nên tránh: truy cập trực tiếp Project instance xuyên build boundaries

Không dùng `project(":library-kit")` hoặc Kotlin API như thể included build chia sẻ `Project` instances với root build. Gradle composite có cơ chế isolation và API `IncludedBuild` chuyên biệt. Cross-build task dependency dùng `gradle.includedBuild(...).task(...)`; cross-build library dependency dùng module notation và substitution. Không cố lấy subproject object rồi mutate tasks/extensions của included build từ root.

## 11. Cần lấy binary published thay vì source local thì sao?

Giả sử bạn muốn hai kiểu kiểm tra:
1. App liên kết với source local `message-lib` qua composite.
2. Một kiểm thử regression so sánh **published artifact** `message-lib:1.0.0` từ repository.

Trong composite, substitution rules có thể áp rộng và **ghi đè module resolution**, dù version request là bản published. Gradle cho phép tắt global composite substitutions **ở một configuration cụ thể**.

Ví dụ **mảnh Kotlin DSL có tính minh họa** trong project Java:

~~~kotlin
val publishedRuntimeClasspath by configurations.creating {
    isCanBeConsumed = false
    isCanBeResolved = true

    extendsFrom(configurations.runtimeClasspath.get())

    resolutionStrategy.useGlobalDependencySubstitutionRules = false

    attributes.attribute(
        Usage.USAGE_ATTRIBUTE,
        objects.named(Usage.JAVA_RUNTIME)
    )
}
~~~

Cần import `org.gradle.api.attributes.Usage` trong build script (hoặc dùng fully qualified type). Configuration này được thiết kế để thử resolve binary từ repositories, không thay đổi global `runtimeClasspath`. **Chạy được hay không phụ thuộc published module có thật, repositories có đủ và attributes/variants phù hợp.** Trong lab, `message-lib` chưa được publish nên khi tắt substitution bạn phải **mong đợi resolution thất bại** nếu không có artifact tương ứng trên repository.

Đừng gọi `--offline` rồi kết luận published artifact tồn tại nếu cache tình cờ có một bản; kiểm tra file/checksum/module metadata và CI repository provenance khi regression cần chính xác.

## 12. Những trường hợp composite substitution khác publication thật

Theo tài liệu Gradle, included project dependency substitution có những giới hạn quan trọng khi metadata/artifacts được publish khác với project `default` configuration.

Ví dụ rủi ro:

- Dự án sửa POM/Ivy descriptor bằng logic ngoài source project variants.
- Một project tạo nhiều publications có `artifactId`/variants khác nhau.
- Có artifact `sources`, `javadoc`, classifier hoặc capability custom không được model hóa đúng trong project default.
- Published Gradle Module Metadata chứa variants/capabilities đặc biệt mà local default configuration không phản ánh.
- POM published dùng dependencies khác hoặc bị custom rewrite.
- Library dùng packaging/phần metadata không trùng Gradle project default output.

Trong các trường hợp này, composite build **có thể không tái hiện chính xác hành vi dependency resolution của published artifact**, ngay cả khi explicit substitution đã chỉ đúng project.

Quy trình an toàn:
1. Test nhanh local source bằng composite để phát triển.
2. Có job kiểm tra **published artifact thật** từ repository hoặc Maven Local được kiểm soát.
3. Kiểm tra POM/Gradle Module Metadata, variants, classifiers, transitive dependencies.
4. Khi nhiều publications, xác định mỗi published coordinate mapping ra sao và liệu default project configuration có tương thích không.
5. Không tự cho rằng successful local compile chứng minh published consumer compatibility 100%.

### Performance và configuration-on-demand

Gradle cần biết included build cung cấp những module coordinates nào. Với auto-substitution, Gradle có thể phải configure nhiều projects trong included build để khám phá group/name. Khi included build có rất nhiều projects, đây là một yếu tố performance. Explicit substitution rules có thể giảm discovery trong một số modes, nhưng cũng tăng công quản lý mapping và nguy cơ thiếu module. Hãy đo configuration time và kiểm tra Gradle version thay vì thêm mọi optimization tùy tiện.

## 13. Cơ chế thứ hai: `pluginManagement { includeBuild("build-logic") }`

Một ứng dụng khác của composite builds là cung cấp **Gradle binary/convention plugins** cho build scripts. Mục này là **phương án độc lập**, không thay thế logic library dependency ở lab.

### 13.1. Vì sao plugin build khác library build?

Thư viện Java:
- Consumer code có `implementation("group:module:version")`.
- Composite Gradle thay module dependency bằng local project source.

Gradle plugin:
- Build script có `plugins { id("company.java-conventions") }`.
- Plugin phải có trên **plugin resolution classpath** **trước khi** project body được configure.
- Với project/settings plugins, Gradle docs ưu tiên include plugin-producing build qua `pluginManagement.includeBuild` để Plugin DSL resolve rõ ràng.
- Đừng chỉ viết `implementation(project(":build-logic"))`: nó không apply Gradle plugin và build-logic không phải subproject.

### 13.2. Cấu trúc của build-logic

~~~text
team-build/
├── settings.gradle.kts
├── core/
│   ├── build.gradle.kts
│   └── src/main/java/demo/core/Feature.java
└── build-logic/
    ├── settings.gradle.kts
    ├── build.gradle.kts
    └── src/main/kotlin/company.java-conventions.gradle.kts
~~~

Root `team-build/settings.gradle.kts`:

~~~kotlin
pluginManagement {
    // Phải được xử lý sớm, trước project Plugin DSL.
    includeBuild("build-logic")

    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = "team-build"
include("core")
~~~

Included `build-logic/settings.gradle.kts`:

~~~kotlin
rootProject.name = "build-logic"
~~~

Included `build-logic/build.gradle.kts`:

~~~kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
}
~~~

Precompiled script convention plugin `build-logic/src/main/kotlin/company.java-conventions.gradle.kts`:

~~~kotlin
plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Consumer `core/build.gradle.kts`:

~~~kotlin
plugins {
    id("company.java-conventions")
}
~~~

Đây là **tổ hợp file đủ để hiểu plugin resolution**; để chạy một `core:compileJava` thực tế, cần thêm Java class và một Gradle Wrapper/JDK phù hợp. Không trộn thêm root code từ lab app `message-lib` vào mô hình này. Dấu gạch trong core plugin `java-library` và `kotlin-dsl` dùng Kotlin backtick identifier trong `plugins` block.

### 13.3. Vai trò của từng lớp

- `pluginManagement { includeBuild("build-logic") }`: cho Gradle biết **nguồn plugin implementation** trước khi xử lý `plugins` của projects.
- `build-logic`: standalone Gradle build đóng gói precompiled script plugin.
- `company.java-conventions.gradle.kts`: tên file tạo plugin ID `company.java-conventions` theo convention cho precompiled script plugin.
- `core/build.gradle.kts` áp plugin bằng ID; không cần publish convention plugin ra Plugin Portal.
- `java-library` là core plugin được convention plugin apply, giúp core có Java source sets/tasks.
- `java.toolchain` bên trong convention plugin cấu hình Java 17 cho project apply plugin.

**Phân biệt:** `pluginManagement.includeBuild(...)` giải quyết **plugin DSL**; top-level `includeBuild(...)` phổ biến cho **library module dependency substitution**. Tài liệu Gradle cho phép những trường hợp plugin được cung cấp qua included builds theo nhiều cơ chế, nhưng đối với settings plugin và unpublished plugin trong `plugins { }`, **đặt include trong `pluginManagement` là lựa chọn rõ và đáng tin cậy**.

### 13.4. Settings plugin có yêu cầu gì đặc biệt?

Khi plugin phải được apply **ngay trong `settings.gradle.kts`**, Gradle cần tìm thấy nó trước khi đánh giá Settings plugins block. Mẫu:

~~~kotlin
pluginManagement {
    includeBuild("my-settings-plugin")
}

plugins {
    id("my-settings-plugin")
}

rootProject.name = "team-build"
~~~

Đây là **mảnh Settings minh họa**, chỉ dùng nếu included build `my-settings-plugin` đã cung cấp plugin ID đó và implementation phù hợp với target `Settings`. Đừng áp project-only Java plugin vào Settings rồi kỳ vọng có `compileJava`.

## 14. Composite qua CLI `--include-build` thay cho Settings

Ngoài khai báo cố định trong Settings, Gradle hỗ trợ tạo composite tạm thời khi invoke:

~~~bash
./gradlew --include-build library-kit :app:run --args="alpha beta"
~~~

**Đây là phương án thay thế:** bỏ `includeBuild("library-kit")` khỏi main Settings trước khi dùng lệnh này để quan sát sự khác biệt. Nó hữu ích khi muốn thử local checkout của library trong giai đoạn phát triển mà không commit Settings change.

Các điều cần nhớ:

- `--include-build` làm root invocation trở thành composite và bật module substitution tương ứng.
- Vẫn cần included build directory tồn tại và có Settings/build hợp lệ.
- Không bảo đảm plugin resolution qua `plugins { }` cho unpublished plugins ổn định bằng `pluginManagement.includeBuild`; ưu tiên Settings approach cho build logic.
- CI muốn build tái lập thường nên commit `includeBuild(...)` hoặc có script/policy rõ ràng, thay vì ngầm phụ thuộc một flag mà developer quên.
- Nếu muốn thay dependency bằng **published binary** trong CI, không kèm `--include-build` hoặc cấu hình published-only configuration.

### Co-development với repository bên ngoài

Ví dụ:

~~~text
workspace/
├── consumer-app/
│   └── settings.gradle.kts
└── message-lib-source/
    └── settings.gradle.kts
~~~

Trong `consumer-app/settings.gradle.kts`:

~~~kotlin
rootProject.name = "consumer-app"
include("app")
includeBuild("../message-lib-source")
~~~

Relative path bắt đầu từ **thư mục chứa main Settings file**, không phụ thuộc vị trí terminal hiện tại. Absolute path có thể dùng nhưng **không nên hard-code** đường dẫn cá nhân như `C:\Users\...` vào repository vì CI/dev khác máy.

## 15. Version, Wrapper, task graph và IDE trong composite

### 15.1. Gradle Wrapper của build nào được dùng?

Khi đứng tại root composite và gọi `./gradlew`, **Wrapper của root đang khởi chạy Gradle invocation**. Included build có thể có Wrapper riêng để chạy độc lập, nhưng không có nghĩa root invocation tự đổi Gradle runtime theo Wrapper của included build ở giữa task graph.

Nếu mỗi build đơn lẻ dùng Gradle version khác nhau, cần kiểm tra tương thích plugin/API khi chạy cùng composite. Tránh coi “included build có `gradle-wrapper.properties` khác” là cơ chế tự cô lập Gradle runtime hoàn toàn.

### 15.2. Task dependencies có thể qua build boundaries

Khi app dùng local library variant, Gradle tự yêu cầu artifact-producing tasks của included project. **Không cần** viết:

~~~kotlin
// Không cần để nối library vào app compile classpath.
tasks.named("compileJava") {
    dependsOn(gradle.includedBuild("library-kit").task(":build"))
}
~~~

Đây là **phản ví dụ**: nó ép cả library build/test trước compile app nhưng không thay thế module dependency declaration. Cần giữ:

~~~kotlin
dependencies {
    implementation("com.acme.learning:message-lib:1.0.0")
}
~~~

và để Gradle variant-aware dependency resolution nối producers cần thiết. Với tasks orchestration độc lập, dùng `IncludedBuild.task(...)` như `verifyComposite` trong lab.

### 15.3. IDE và workspace

Gradle IDE integrations thường nhận biết included builds, tạo source project mappings và hỗ trợ bước qua code giữa consumer và library. Nhưng kết quả phụ thuộc IDE/Gradle version và cài đặt import.

Nếu IDE vẫn nhìn published JAR thay vì local source:
1. Kiểm tra Settings đang dùng bởi IDE có `includeBuild(...)` chưa.
2. Refresh/reimport Gradle project với đúng Wrapper.
3. Kiểm tra `:app:dependencies --configuration runtimeClasspath` có substitution không.
4. Đảm bảo group/name match và included build áp Java plugin đúng.
5. Nếu IDE đã cache model cũ, refresh project model; không vội xóa toàn bộ cache.

### 15.4. `--dry-run` và logs

~~~bash
./gradlew :app:run --dry-run
./gradlew :app:compileJava --info
./gradlew :library-kit:tasks --all
./gradlew :verifyComposite --dry-run
~~~

`--dry-run` in task graph dự kiến nhưng không compile/run code. `--info` tăng chi tiết resolution/execution; không cố định câu chữ logs vì Gradle versions khác nhau.

Từng task có thể được đánh dấu `UP-TO-DATE`/`FROM-CACHE`, nên một lần chạy app thành công không luôn có compile task action mới. Khi kiểm tra source changes, nếu cần dùng `--rerun-tasks` có kiểm soát và xem metadata thay vì cho rằng không có dòng compile nghĩa là substitution sai.

## 16. Không trùng identity: project path và build path là hai namespace khác nhau

Gradle composite yêu cầu mỗi project có định danh duy nhất trong build tree. Hai điều kiện cần chú ý:

1. Các included builds không được có **cùng build path/identity**.
2. Included build path không được trùng project path đã tồn tại trong root build.

Ví dụ root Settings đã có:

~~~kotlin
include("tools")
~~~

và bạn thêm:

~~~kotlin
includeBuild("tools")
~~~

để chỉ cùng thư mục hoặc build khác nhưng cùng path, có thể gây collision hoặc cấu trúc không hợp lệ. Đừng kỳ vọng Gradle nhập hai đối tượng vào một. Nếu cần, đổi included build path:

~~~kotlin
includeBuild("shared-build-tools") {
    name = "team-tools-build"
}
~~~

Với nested composite, một included build có thể cũng chứa các included builds khác; Gradle thường flatten build tree, do đó names phải unique trên toàn tree, không chỉ giữa siblings trực tiếp.

### Build name không phải Maven artifact ID

Đổi `name = "team-tools-build"` giúp task path/IncludedBuild API rõ ràng hơn, **không tự đổi `group`/`project.name`** của library, cũng không đổi module coordinates mà composite auto-substitution dùng.

## 17. Tránh xung đột khi nhiều Gradle processes chạy một included build

Composite build cho phép nhiều roots dùng cùng local included build. Tuy nhiên khi **nhiều Gradle invocations độc lập** đồng thời include chung một build directory, có thể xảy ra contention về caches/build outputs/locks, nhất là ở filesystem chia sẻ. Gradle tài liệu hóa hạn chế về project locks giữa nhiều composites chạy đồng thời.

Các cách giảm rủi ro:

- Mỗi CI job dùng checkout/workspace tách biệt.
- Không cho hai builds ghi chung output directory của một included build nếu có thể.
- Dùng Gradle caches chuẩn, không tự chia sẻ `build/` files qua symlink theo kiểu mơ hồ.
- Nếu cần dùng chung một checkout, phối hợp lịch chạy/locks ở CI level.
- Không tự thay `buildDirectory` của included projects sang cùng một path global với root projects.
- Với build logic, ưu tiên included build convention plugins thay vì copy code vào nhiều root scripts và tự sửa cùng source đồng thời.

Đừng suy rằng vì composite là một Gradle invocation thì **mọi** lần gọi từ IDE/terminal khác cũng tự được serial hóa như cùng invocation.

## 18. Troubleshooting: `includeBuild` không có hiệu lực

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `Project with path ':library-kit' could not be found` | Dùng `project(":library-kit")` như subproject. | Dùng GAV external module + composite substitution. |
| App vẫn tải published JAR | group/name mismatch, included build chưa include trong Settings đang chạy. | Xem `library-kit/build.gradle.kts`, rootProject.name và `:app:dependencies`. |
| `includeBuild("...")` không tìm thấy build | Relative path không nằm ở directory chứa Settings. | Sửa path relative hoặc checkout đúng vị trí. |
| Gradle fail vì included project directory thiếu | Build path/settings/project directories không tồn tại. | Tạo directories thật, kiểm tra Gradle 9 strict validation. |
| Module name `legacy-messages` không match project `message-lib` | Auto substitution theo group:name. | Align publication name hoặc dùng explicit substitution. |
| Root `repositories` đủ nhưng library tests không resolve JUnit | Included build không thừa hưởng root repos. | Thêm repositories trong included build hoặc common convention plugin. |
| Root `gradle.properties` có flag nhưng included build không đọc được | User-defined properties không tự chia sẻ. | Dùng CLI `-P` hoặc xác định property trong included build. |
| `:library-kit:jar` bị “task not found” | Build identity/path khác, plugin Jar chưa apply hoặc task không tồn tại. | Xem `projects`, build name, `:library-kit:tasks --all`. |
| `:app:run` compile được nhưng `:library-kit:test` fail | App consumption chỉ đòi artifact producers, không đảm bảo library tests. | Gọi library tests hoặc root aggregator rõ. |
| `./gradlew build` không chạy toàn bộ included build tests | Included builds không là subprojects. | Gọi `:verifyComposite` hoặc included build task paths. |
| CLI `--include-build` chạy nhưng project `plugins` không tìm thấy unpublished plugin | Plugin DSL cần resolve sớm, CLI injection không luôn tương đương pluginManagement. | Đặt `pluginManagement { includeBuild("build-logic") }` trong Settings. |
| Included build trong pluginManagement nhưng app `implementation` vẫn không resolve library | Plugin build and library substitution là hai use cases, coordinates/source không match. | Dùng top-level includeBuild cho library hoặc cấu hình substitution thích hợp. |
| `Unknown plugin id` cho convention plugin | Tên file/ID mismatch, build-logic plugin setup chưa đúng. | Kiểm tra `build-logic`, `kotlin-dsl`, source file và Settings pluginManagement. |
| Composite module version khác request nhưng vẫn substitute | Default auto-substitution theo group:name, không bị pin vào requested version. | Test published binary riêng nếu cần version-specific behavior. |
| Một published variant chạy được nhưng local substitute fail | Default project configuration khác POM/Gradle Module Metadata published. | Kiểm tra variants/publications; dùng published artifact integration test. |
| Two included builds cùng path | Duplicate build identity hoặc trùng root subproject path. | Rename included build `name` hoặc sửa layout. |
| CI composite chạy song song gây lỗi file lock | Nhiều invocations cùng include một build directory. | Tách workspaces, giới hạn concurrency. |
| `--offline` vẫn fail khi chạy tests | JUnit/plugin/toolchain chưa cache local. | Chuẩn bị cache hoặc cho phép repository access lần đầu. |
| Java `Messages` không tìm thấy ở app | Substitution fail hoặc dependency notation sai. | Xem `:app:dependencies` và `:app:compileJava --info`. |
| Wrapper included build khác root nên compilation fail | Runtime Gradle version được chọn bởi invocation root. | Dùng compatible Gradle API/plugins/JDK cho composite invocation. |

### Quy trình debug tối thiểu

1. Đọc root `settings.gradle.kts`: có `includeBuild("library-kit")` đúng vị trí không?
2. Đọc included `settings.gradle.kts`: `rootProject.name` là `message-lib` hay tên khác?
3. Đọc included `build.gradle.kts`: `group = "com.acme.learning"` và Java plugin đã apply chưa?
4. Kiểm tra app dependency: đúng `com.acme.learning:message-lib:1.0.0` không?
5. Chạy `./gradlew projects` để thấy build tree/project structure.
6. Chạy `./gradlew :app:dependencies --configuration runtimeClasspath` và `dependencyInsight` để xem selected component/substitution.
7. Chạy `./gradlew :app:compileJava --info` để kiểm tra source artifact producers và compiler.
8. Chạy `./gradlew :app:run --args="alpha beta"` để kiểm tra Java stdout.
9. Chạy `./gradlew :library-kit:test` để tách lỗi library tests khỏi app tests.
10. Nếu là plugin build, kiểm tra `pluginManagement.includeBuild` và file plugin ID.
11. Khi cần so sánh published release, tắt substitution trên configuration kiểm thử riêng hoặc chạy consumer không include source.
12. Nếu lỗi chỉ xảy ra trong CI, so sánh checkout paths, Wrapper/JDK, repository access, permissions và task graph.

## 19. Quy trình CI khuyến nghị

Có ba nhu cầu khác nhau, không nên dùng cùng một command cho cả ba:

| Nhu cầu | Lệnh/mô hình | Kết quả mong đợi |
| --- | --- | --- |
| Dev cùng app và library nguồn local | `./gradlew :app:run` trong composite. | App dùng source library, không publish. |
| Build app cùng library producers | `./gradlew :app:build`. | App tests/build và required producers của library. |
| Test tất cả projects có liên quan | `./gradlew :verifyComposite`. | Root aggregator đòi app test + included library test. |
| Chỉ test included library | `./gradlew :library-kit:test`. | Library test độc lập theo included build. |
| Kiểm tra published module binary | Consumer không include source hoặc configuration tắt substitution. | Resolve artifact từ repository, kiểm tra published metadata. |
| Kiểm tra plugin nội bộ | `pluginManagement.includeBuild("build-logic")` + apply ID. | Consumer build script dùng convention plugin local. |
| Điều tra graph | `./gradlew :app:run --dry-run`. | Quan sát tasks, không thực thi. |
| Điều tra version selection | `dependencyInsight` + configs. | Xác nhận local project hay published module. |

**Không luôn cần** CI composite cho mọi release: nếu muốn kiểm thử module đã publish lên Maven repository, composite substitution có thể che lỗi publication. Sử dụng một job riêng kiểm thử published artifacts thực tế.

## 20. Checklist học và review một composite build

- [ ] Hiểu `includeBuild(...)` thêm một build, không thêm subproject.
- [ ] Chỉ dùng `project(":x")` cho projects thuộc cùng root build.
- [ ] Dùng external module notation cho library từ included build.
- [ ] Kiểm tra `group` và `project.name` của included project đúng module coordinate.
- [ ] Biết auto-substitution dựa vào group/name, không gate version request.
- [ ] Relative path của `includeBuild` tính từ Settings directory.
- [ ] Included build có `settings.gradle.kts`, project directories và plugins hợp lệ.
- [ ] Không giả định root repositories/version catalog/buildSrc chia sẻ với included build.
- [ ] Phân biệt build identity `library-kit` với module name `message-lib`.
- [ ] Dùng `gradle.includedBuild(name).task(":task")` cho cross-build task dependencies.
- [ ] Dùng full task paths để tránh gọi nhầm build.
- [ ] Không nghĩ `./gradlew build` tự build/test mọi included builds.
- [ ] Kiểm tra `:app:dependencies`/`dependencyInsight` để xác nhận substitution.
- [ ] Có cơ chế explicit substitution khi publication artifactId khác project name.
- [ ] Hiểu composite project default variants có thể khác published metadata.
- [ ] Có job published-artifact verification nếu cần chứng minh artifact consumers dùng được.
- [ ] Dùng `pluginManagement.includeBuild` để resolve local Gradle plugin builds.
- [ ] Settings plugin target không bị nhầm với Java project plugin.
- [ ] Khi thay build name, giữ unique build-tree paths và cập nhật task references.
- [ ] Kiểm thử CI concurrent runs với workspaces/outputs cô lập.
- [ ] Pin Gradle Wrapper/JDK/plugin versions, kiểm tra compatibility của các builds.
- [ ] Không ghi secrets vào sample build scripts/logs hoặc public repository.
- [ ] Có lệnh chạy độc lập cho included build và lệnh tổng hợp khi policy yêu cầu.

## 21. Câu hỏi tự kiểm tra

1. **`includeBuild("library-kit")` tạo project `:library-kit` trong root build không?** Không, nó thêm một build độc lập vào composite.
2. **`include("app")` có giống `includeBuild("app")` không?** Không; cái đầu thêm subproject, cái sau thêm build.
3. **Included build có Settings riêng không?** Có thể và thường nên có, để chạy độc lập và cấu hình project hierarchy riêng.
4. **App muốn dùng local included library phải khai báo dependency thế nào?** Bằng published-module notation `group:module:version` để composite substitute.
5. **`implementation(project(":library-kit"))` có đúng khi library-kit chỉ được includeBuild không?** Không.
6. **Default auto-substitution dựa trên thuộc tính nào?** `project.group` và `project.name`.
7. **Yêu cầu module version 0.9 nhưng included project version 1.0 có thể vẫn substitute không?** Có, vì matching group:name.
8. **Tên build `library-kit` có bắt buộc trùng module `message-lib` không?** Không.
9. **Muốn gọi root task `test` trong library-kit từ root CLI thế nào?** Thường `./gradlew :library-kit:test` khi build identity là library-kit.
10. **API tham chiếu included task là gì?** `gradle.includedBuild("library-kit").task(":test")`.
11. **`./gradlew build` có tự chọn `library-kit:build` không?** Không chỉ vì `includeBuild`; khi có dependency/task graph thì các task liên quan có thể được kéo vào.
12. **Muốn test app và included library chắc chắn, làm gì?** Gọi hai task paths hoặc tạo root aggregator như `verifyComposite`.
13. **Root `repositories`/`libs` có tự áp sang included build không?** Không.
14. **Root user `gradle.properties` có tự hiện trong included build không?** Không, cần hiểu property propagation/CLI hoặc khai báo riêng.
15. **Dùng `includeBuild` top-level để gì?** Thường để compose library/source builds và substitution.
16. **Dùng `pluginManagement.includeBuild` để gì?** Đưa plugin-producing build vào Plugin DSL resolution sớm.
17. **Published artifactId khác included project name thì sao?** Dùng explicit dependency substitution hoặc align group/name.
18. **Explicit substitution có tự lan sang included build khi nó chạy standalone không?** Không.
19. **Composite có chứng minh published POM/variants đúng không?** Không; cần published artifact test nếu metadata khác.
20. **Bỏ `includeBuild` để so published library cần gì?** Published module thực có trên configured repository và dependency coordinates đúng.
21. **`--include-build` trên CLI dùng được cho gì?** Compose tạm thời một source build không cần commit Settings.
22. **Vì sao nên tránh hard-coded absolute includeBuild paths?** Máy developer/CI khác layout, giảm tính tái lập.
23. **Khi có hai included builds cùng identity, Gradle làm gì?** Báo namespace conflict; cần đổi build path/name.
24. **Một included build có thể chứa nhiều subprojects không?** Có, tất cả có thể cung cấp module coordinates riêng.
25. **Khi root composite đang chạy, Gradle dùng Wrapper của library-kit riêng không?** Không tự chuyển; invocation root chọn Gradle runtime.
26. **Mã Java lab in gì khi gọi app với hai args?** `COMPOSITE_OK=hello from local source` rồi `ARG_COUNT=2`.
27. **Biên dịch bằng javac chứng minh Gradle substitution đúng không?** Không; cần Gradle dependency report.
28. **Dùng `dependencyInsight` khi nào?** Khi cần giải thích module nào được chọn và vì sao.
29. **Có thể chạy included builds song song từ hai CI jobs trong cùng thư mục an toàn tuyệt đối không?** Không nên giả định; tách workspaces.
30. **Khi nào nên chọn multi-project thay composite?** Khi modules cùng build cần share Settings/project hierarchy và dependencies dùng `project(":x")`; composite cho builds có lifecycle/configuration độc lập.

## 22. Tài liệu chính thức và tham khảo

- [Gradle — Composite Builds (Included Builds)](https://docs.gradle.org/current/userguide/composite_builds.html): `includeBuild` trong Settings/CLI, build isolation, task addressing, automatic/explicit substitution, plugin builds, limitations.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): project hierarchy, `include` và project paths.
- [Gradle — Declaring Dependencies Between Subprojects](https://docs.gradle.org/current/userguide/declaring_dependencies_between_subprojects.html): `project(":shared")` trong cùng build, Java dependencies/variants.
- [Gradle — Sharing Build Logic](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html): included `build-logic`, precompiled script/convention plugins.
- [Gradle — Convention Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_convention.html): cách định nghĩa convention plugins.
- [Gradle — Settings DSL](https://docs.gradle.org/current/dsl/org.gradle.api.initialization.Settings.html): `includeBuild(...)` và `include(...)`.
- [Gradle — IncludedBuild API](https://docs.gradle.org/current/javadoc/org/gradle/api/initialization/IncludedBuild.html): tham chiếu tasks trong included builds.
- [Gradle — Dependency Substitution](https://docs.gradle.org/current/userguide/resolution_rules.html): module/project substitution và resolution rules.
- [Gradle — Understanding Variant Selection](https://docs.gradle.org/current/userguide/variant_aware_resolution.html): vì sao local project variants có thể khác published metadata.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): task paths, `--include-build`, `--dry-run` và `--info`.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): Java source sets, outgoing variants và library dependencies.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): `run`, `mainClass` và `--args`.
