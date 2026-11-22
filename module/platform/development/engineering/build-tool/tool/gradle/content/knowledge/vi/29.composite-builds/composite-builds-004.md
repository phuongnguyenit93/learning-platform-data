# Dùng thư viện từ source cục bộ thay artifact đã công bố với Gradle Composite Build

## 1. Bài toán: sửa thư viện và kiểm tra ứng dụng mà không publish lặp đi lặp lại

Giả sử một ứng dụng Java dùng thư viện nội bộ đã phát hành trên Maven repository:

```kotlin
dependencies {
    implementation("dev.learning:greeter-lib:1.0.0")
}
```

Thông thường Gradle tìm module `dev.learning:greeter-lib:1.0.0` trong các repository đã cấu hình, tải POM/Gradle Module Metadata và JAR rồi đưa artifact được chọn vào classpath.

Khi cần sửa nhanh code của `greeter-lib` và chạy thử ứng dụng với thay đổi chưa công bố, một vòng làm việc thủ công có thể là:

```text
Sửa source greeter-lib
    ↓
Biên dịch + publish vào Maven local / kho thử nghiệm
    ↓
Kiểm tra repository/cache/phiên bản
    ↓
Chạy lại demo-app
    ↓
Sửa thêm → lặp lại publish
```

Cách này tốn thời gian, tạo nguy cơ dùng nhầm artifact cũ trong cache và có thể ghi đè cùng một tọa độ đã công bố.

**Gradle Composite Build** giải quyết trường hợp này bằng cách **kết hợp nhiều build độc lập**, rồi áp dụng **dependency substitution**: thay một module dependency có tọa độ Maven bằng project tương ứng trong một **included build**. Nhờ vậy ứng dụng có thể giữ nguyên:

```kotlin
implementation("dev.learning:greeter-lib:1.0.0")
```

nhưng khi bật composite, Gradle build `greeter-lib` từ source cục bộ và sử dụng output project đó thay cho JAR repository. Không cần publish lại sau mỗi lần sửa.

**Điểm chính:** Composite build thay đổi **cách Gradle resolve dependency trong build đang chạy**, không chỉnh dependency declaration trong source, không thay bytes của artifact đã phát hành và không tự publish source cục bộ lên repository.

### 1.1. Mô hình trước và sau

```text
KHÔNG dùng composite:

demo-app
  implementation("dev.learning:greeter-lib:1.0.0")
                          |
                          v
                  Maven repository
                          |
                          v
                  greeter-lib-1.0.0.jar
                          |
                          v
                compileClasspath/runtimeClasspath


CÓ dùng composite:

demo-app/settings.gradle.kts
  includeBuild("../greeter-lib")
                          |
                          v
    Dependency substitution group:name
                          |
                          v
demo-app: implementation("dev.learning:greeter-lib:1.0.0")
                          |
                          v
              project source của greeter-lib
                          |
                          v
                  compileJava / jar
                          |
                          v
                compileClasspath/runtimeClasspath
```

Ở cả hai nhánh, code Java consumer import cùng lớp và gọi cùng API. Khác biệt là **producer của dependency**: artifact repository so với project output từ source cục bộ.

## 2. Composite build là gì?

Một **Gradle build** có một `settings.gradle(.kts)` riêng, một root project và có thể nhiều subprojects.

**Composite build** kết nối một build chính với một hoặc nhiều **included builds**. Những build đó vẫn giữ bản sắc và cấu hình riêng:

- Mỗi build có `settings.gradle(.kts)` riêng.
- Mỗi build có thể có `build.gradle(.kts)`, source sets, versions, repositories và plugins riêng.
- Included build **không bị biến thành một subproject** của main build.
- Gradle có thể chạy các task cần thiết của included build theo dependency graph.
- Gradle có thể thay module dependency bằng project phù hợp trong included build.
- Build chính không cần thay `implementation("group:artifact:version")` thành `project(":lib")`.

Cấu hình ở settings của build chính:

```kotlin
includeBuild("../greeter-lib")
```

Đường dẫn là đường dẫn **thư mục build được include**, thường tương đối với vị trí settings của build chính. Thư mục đích phải là một Gradle build hợp lệ với project được cấu hình đúng.

### 2.1. Phân biệt ba quan hệ thường bị nhầm

| Đặc điểm | Multi-project build | Composite build | Module artifact từ repository |
| --- | --- | --- | --- |
| Root settings | Một settings quản lý các subprojects | Nhiều builds, mỗi build có settings | Consumer chỉ cần biết repositories |
| Liên kết project | `include(":lib")` | `includeBuild("../lib")` | Không include source build |
| Dependency consumer | Thường `implementation(project(":lib"))` | Có thể giữ `implementation("g:a:v")` | `implementation("g:a:v")` |
| Source producer | Cùng một build | Build riêng được include | Không cần source tại máy consumer |
| Có cần publish trước khi dùng? | Không | Không, khi substitution thành công | Có, hoặc artifact đã có trong repository/cache |
| Tác động vào repository | Không tự publish | Không tự publish | Tải metadata/artifact |
| Dùng khi | Một repository nhiều modules thống nhất | Tích hợp builds vốn độc lập, debug thư viện local | Tiêu thụ release chính thức |

**Không đồng nhất `include(":lib")` và `includeBuild("../lib")`.** `include` đăng ký subproject trong một build; `includeBuild` đăng ký cả một Gradle build độc lập.

### 2.2. Composite build không phải Git submodule

Git submodule/worktree/monorepo là **cách lưu trữ source**. Composite build là **cách Gradle kết nối builds và resolve dependencies**. Bạn có thể đặt included build ở thư mục sibling, Git worktree khác hoặc checkout của repository riêng. Git submodule không tự làm Gradle substitution; vẫn cần cấu hình `includeBuild` phù hợp.

### 2.3. Composite build không phải Maven local

`mavenLocal()` cho phép Gradle đọc artifact đã publish vào Maven local, thường ở thư mục người dùng. Nếu muốn thử code mới với cách đó, cần publish lại JAR/metadata khi source thay đổi.

Composite build dùng **task outputs của local project** trực tiếp khi được chọn, và Gradle có thể biên dịch lại source đã sửa theo task graph. Nó tránh vòng publish thủ công cho mỗi thay đổi nhưng **không chứng minh bản artifact đã phát hành sẽ có metadata y hệt**.

## 3. Cơ chế thay module dependency bằng project

Trong trường hợp đơn giản, Gradle có thể tự nhận diện mapping cho các projects của included build theo:

```text
module group + module name
      ⇅
project.group + project.name
```

Ví dụ:

```text
Dependency request ở ứng dụng:
  dev.learning:greeter-lib:1.0.0

Project trong included build:
  group        = "dev.learning"
  project.name = "greeter-lib"

Kết quả:
  module dev.learning:greeter-lib được thay bằng project greeter-lib
```

Phần **group** và **project name** phải đúng để automatic substitution khớp. Version của request không được dùng như một điều kiện bảo đảm rằng local project có nội dung tương đương release cùng số version. Việc chọn project local có thể áp dụng cho module requests với các versions khác nhau; vì vậy phải thận trọng với compatibility và tests.

### 3.1. Substitution diễn ra trong quá trình resolution

Khi Gradle resolve một configuration của consumer, nó cần:

1. Xác định module dependency requests.
2. Xem những substitution rules, nếu có.
3. Chọn một dependency target: external module hoặc project.
4. Thực hiện variant-aware resolution từ project/module được chọn.
5. Xây task dependencies cần để cung cấp project outputs.
6. Đưa các artifacts/outputs phù hợp vào classpath.

Nếu substitution thành công, Gradle có thể tự thêm các task cần thiết của included build vào graph của consumer, ví dụ `compileJava`/`jar` của thư viện. Không nên tự viết một task shell publish JAR rồi copy file vào `lib` nếu đang dùng quan hệ project substitution chuẩn.

### 3.2. Automatic substitution và explicit substitution

**Automatic substitution** phù hợp khi tọa độ đã công bố của module trùng với `project.group` và `project.name` ở included build.

**Explicit substitution** hữu ích khi một artifact publish với `artifactId` tùy biến hoặc khi module coordinates khác project name. Ví dụ:

```kotlin
includeBuild("../greeter-lib") {
    dependencySubstitution {
        substitute(module("dev.learning:greeter-api"))
            .using(project(":"))
    }
}
```

Mảnh trên nằm trong `settings.gradle.kts` của consumer. Nó yêu cầu dependency có module identity `dev.learning:greeter-api` dùng **root project** (`project(":")`) của included build `../greeter-lib`. Dấu `:` trong `project(":")` là **đường dẫn project bên trong included build**, không phải root project của consumer.

Không dán explicit rule này vào bài lab nếu consumer đang dùng đúng `dev.learning:greeter-lib`; automatic substitution đã đáp ứng. Đây là một **phương án thay thế** khi tên Maven module khác project name.

### 3.3. Version không được coi là dấu xác thực tính tương đương

Giả sử consumer yêu cầu:

```text
dev.learning:greeter-lib:1.0.0
```

nhưng checkout local đã chứa các thay đổi chuẩn bị cho `2.0.0`. Composite build có thể vẫn thay module theo group/name. Kết quả:

- Local test pass **không chứng minh** API 1.0.0 đã phát hành có cùng khả năng.
- Breaking change ở local source có thể bị che khi developer chỉ chạy một chế độ.
- Một consumer yêu cầu 1.0.0 có thể chạy với local project đang mang `project.version=2.0.0` nếu substitution được áp dụng.
- Khi bỏ composite, consumer quay lại artifact từ repository; hành vi có thể khác.

Vì thế cần kiểm tra **cả chế độ local source lẫn published artifact** trước khi đưa thay đổi ra release.

## 4. Ví dụ hoàn chỉnh: hai Gradle builds dùng Java 17

Bài thực hành tạo một thư viện và một ứng dụng trong hai build độc lập. Ta sẽ:

1. Publish thư viện phiên bản đầu vào repository Maven **biệt lập trong thư mục lab**.
2. Chạy ứng dụng bằng artifact đã publish để lấy kết quả đối chứng.
3. Sửa source thư viện cục bộ **nhưng không republish**.
4. Bật `includeBuild` bằng một Gradle property và chạy ứng dụng.
5. Quan sát kết quả đổi ngay theo local source.
6. Tắt composite và xác nhận ứng dụng lại dùng artifact cũ.

Cấu hình này là ví dụ **thực sự có thể chạy**; không cần Maven Central hoặc credentials vì chỉ dùng Gradle built-in plugins và Java standard library. Cần Gradle tương thích và JDK 17/toolchain có sẵn.

### 4.1. Cây thư mục

```text
composite-lab/
├── greeter-lib/               (build thư viện độc lập)
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/
│       └── main/
│           └── java/
│               └── dev/
│                   └── learning/
│                       └── Greeter.java
├── demo-app/                  (build ứng dụng độc lập)
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/
│       └── main/
│           └── java/
│               └── demo/
│                   └── Main.java
└── published-repo/            (tạo sau khi publish thư viện)
```

Hai thư mục `greeter-lib` và `demo-app` có `settings.gradle.kts` riêng. **Không tạo một settings ở `composite-lab` để include chúng như subprojects**; bài lab muốn học sự khác biệt của composite builds.

### 4.2. Settings cho thư viện

**File `greeter-lib/settings.gradle.kts`:**

```kotlin
rootProject.name = "greeter-lib"
```

Tên root project là `greeter-lib`. Đây là phần quan trọng của automatic substitution khi app yêu cầu module `dev.learning:greeter-lib`.

### 4.3. Build script cho thư viện

**File `greeter-lib/build.gradle.kts`:**

```kotlin
plugins {
    `java-library`
    `maven-publish`
}

group = "dev.learning"
version = "1.0.0"

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }
    repositories {
        maven {
            name = "Lab"
            url = uri("../published-repo")
        }
    }
}
```

Giải thích:

- `java-library` tạo Java software component và các outgoing variants API/runtime.
- `maven-publish` có thể xuất bản component thành Maven POM và Gradle Module Metadata.
- `group="dev.learning"` và root name `greeter-lib` tạo identity `dev.learning:greeter-lib`.
- `version="1.0.0"` là version của published artifact.
- `url = uri("../published-repo")` đặt Maven repository file-based ở cùng cấp với hai builds, trong thư mục lab.
- Không dùng `mavenLocal()` nên không ảnh hưởng `~/.m2/repository` hoặc cache Maven local của các project khác.
- Cú pháp ``java-library`` và ``maven-publish`` dùng backticks trong Kotlin DSL vì tên plugin accessor có dấu gạch nối.

Bài thực hành này **không cần tự attach JAR** bằng `artifact(tasks.jar)` vì `from(components["java"])` đã mang đúng component artifacts.

### 4.4. Mã Java của thư viện, phiên bản đã công bố

**File `greeter-lib/src/main/java/dev/learning/Greeter.java`:**

```java
package dev.learning;

public final class Greeter {
    private Greeter() {
    }

    public static String greeting(String name) {
        return "Published artifact: " + name.strip();
    }
}
```

Java `String.strip()` có từ Java 11, dùng được với toolchain Java 17. Phần code đơn giản để khi chạy có thể dễ dàng thấy ứng dụng dùng **published version** hay **local source**.

### 4.5. Settings cho ứng dụng có thể bật/tắt composite

**File `demo-app/settings.gradle.kts`:**

```kotlin
rootProject.name = "demo-app"

val useLocalLib = providers.gradleProperty("useLocalLib")
    .map { it.equals("true", ignoreCase = true) }
    .getOrElse(false)

if (useLocalLib) {
    includeBuild("../greeter-lib")
}
```

Ý nghĩa:

- Mặc định nếu không truyền `-PuseLocalLib=true`, build chỉ dùng repositories của `demo-app`.
- Khi bật `-PuseLocalLib=true`, Gradle include `../greeter-lib`.
- Vì producer có `group=dev.learning` và `project.name=greeter-lib`, dependency substitution tự động có thể thay module cùng tên.
- Build không yêu cầu sửa `dependencies` hoặc commit những đường dẫn local cố định vào published source.

Với repository thực tế, tránh commit một đường dẫn hardcode chỉ đúng trên một máy. Trong bài lab, hai thư mục sibling được tạo cố định theo hướng dẫn; môi trường tổ chức có thể dùng một local property được validate hoặc Gradle CLI composite option và quy định checkout path riêng.

### 4.6. Build script cho ứng dụng

**File `demo-app/build.gradle.kts`:**

```kotlin
plugins {
    application
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

repositories {
    maven {
        url = uri("../published-repo")
    }
}

dependencies {
    implementation("dev.learning:greeter-lib:1.0.0")
}

application {
    mainClass.set("demo.Main")
}
```

**Giữ nguyên dòng `implementation("dev.learning:greeter-lib:1.0.0")` trong mọi thí nghiệm.** Bài học là sự thay đổi ở **resolution source** chứ không phải ở tên dependency.

Repository file-based dùng bản đã publish để tạo đối chứng và vẫn hoạt động khi composite tắt. Không dùng JAR thật ở một tổ chức khác hoặc tọa độ Maven không tồn tại.

### 4.7. Mã ứng dụng

**File `demo-app/src/main/java/demo/Main.java`:**

```java
package demo;

import dev.learning.Greeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.greeting("  Gradle  "));
    }
}
```

`String.strip()` của producer sẽ xóa dấu cách đầu/cuối chuỗi. Khi dùng bản thư viện đầu tiên, chương trình in đúng:

```text
Published artifact: Gradle
```

Ứng dụng không biết tại compile time nó lấy thư viện từ Maven repository hay local project; Gradle resolution và classpath quyết định điều đó.

### 4.8. Chuẩn bị Gradle Wrapper cho hai builds độc lập

Nếu mỗi build đã có Gradle Wrapper phù hợp, sử dụng Wrapper có sẵn. Với hai thư mục mới chưa có wrapper, máy cần một bản Gradle tương thích đã cài để tạo một lần trong từng build.

Linux/macOS:

```bash
cd composite-lab/greeter-lib
gradle wrapper
cd ../demo-app
gradle wrapper
```

Windows PowerShell với Gradle được cài trong PATH:

```powershell
Set-Location composite-lab\greeter-lib
gradle.bat wrapper
Set-Location ..\demo-app
gradle.bat wrapper
```

Các lệnh trên giả sử bạn bắt đầu từ thư mục **cha của `composite-lab`**. Nếu đang ở `composite-lab`, dùng `cd greeter-lib` thay vì `cd composite-lab/greeter-lib`.

Cần JDK 17 được Gradle tìm thấy làm toolchain. Gradle không tự bảo đảm luôn tải JDK nếu máy chưa có resolver phù hợp. Kiểm tra `./gradlew javaToolchains` khi cần.

## 5. Thực hành giai đoạn 1: publish và tiêu thụ artifact

Từ thư mục `composite-lab/greeter-lib`, chạy:

```bash
./gradlew publishMavenJavaPublicationToLabRepository --console=plain
```

PowerShell:

```powershell
.\gradlew.bat publishMavenJavaPublicationToLabRepository --console=plain
```

Từ build script, Gradle tạo repository dưới:

```text
composite-lab/published-repo/dev/learning/greeter-lib/1.0.0/
├── greeter-lib-1.0.0.jar
├── greeter-lib-1.0.0.pom
└── greeter-lib-1.0.0.module
```

Ngoài ba file chủ đạo, repository có thể còn checksum sidecars hoặc Maven metadata khác. Tên repository publication task được suy ra từ publication `mavenJava` và repository `Lab`.

**Quan trọng:** repository chứa bản thư viện có chuỗi `"Published artifact: "` tại thời điểm publish. Ta sẽ sửa source sau đó mà **không chạy publish lại**, để quan sát sự khác biệt.

### 5.1. Chạy ứng dụng khi composite tắt

Từ thư mục `composite-lab/demo-app`:

```bash
./gradlew --quiet run
```

PowerShell:

```powershell
.\gradlew.bat --quiet run
```

**Stdout do Java Main in ra:**

```text
Published artifact: Gradle
```

Ở chế độ này, settings của app không gọi `includeBuild` vì property `useLocalLib` vắng hoặc không phải `true`. Gradle tìm `dev.learning:greeter-lib:1.0.0` trong repository `../published-repo`.

### 5.2. Kiểm tra graph ở chế độ published

```bash
./gradlew dependencies --configuration runtimeClasspath --console=plain
./gradlew dependencyInsight --dependency greeter-lib --configuration runtimeClasspath
```

Tùy Gradle version, output hiển thị external module `dev.learning:greeter-lib:1.0.0`. Chúng ta không cần thuộc nguyên văn toàn bộ dependency tree: điều quan trọng là module được lấy từ repository chứ **chưa** được substitute bởi local project.

Nếu module không tìm thấy, kiểm tra đường dẫn `published-repo`, tọa độ group/name/version, task publish đã thành công và repository có JAR/POM. Đừng sửa bằng cách thêm một thư viện khác vào `implementation`.

## 6. Thực hành giai đoạn 2: đổi source nhưng không publish

Mở file **`greeter-lib/src/main/java/dev/learning/Greeter.java`** và đổi duy nhất nội dung chuỗi trả về.

**Toàn bộ file sau khi sửa:**

```java
package dev.learning;

public final class Greeter {
    private Greeter() {
    }

    public static String greeting(String name) {
        return "Local source: " + name.strip();
    }
}
```

Không đổi package, class name, method signature, group, project name hoặc version. **Không chạy `publish` sau thay đổi này**.

Tại thời điểm này:

- Source cục bộ của thư viện trả về `Local source: Gradle`.
- Artifact đã xuất bản trong `published-repo` vẫn chứa logic `Published artifact: Gradle`.
- Dependency trong `demo-app/build.gradle.kts` vẫn khai báo `dev.learning:greeter-lib:1.0.0`.
- Ứng dụng chưa biết source đã sửa nếu chế độ composite chưa bật.

Đây là trạng thái đối chứng hoàn hảo cho cơ chế substitution.

### 6.1. Bật composite và chạy ứng dụng

Từ `composite-lab/demo-app`:

```bash
./gradlew -PuseLocalLib=true --quiet run
```

PowerShell:

```powershell
.\gradlew.bat -PuseLocalLib=true --quiet run
```

**Stdout chính xác do `Main.main` in ra:**

```text
Local source: Gradle
```

Không có lệnh publish nào được chạy trong bước này. Gradle tự dùng source/project outputs của included build nhờ substitution tự động.

Nếu lần đầu chạy cần compiler JDK 17 hoặc Gradle wrapper chưa được tải, môi trường có thể cần chuẩn bị network/toolchain; điều đó không làm thay đổi nguyên lý của ví dụ.

### 6.2. Xem dependency đã được substitute

Chạy:

```bash
./gradlew -PuseLocalLib=true dependencyInsight \
    --dependency greeter-lib \
    --configuration runtimeClasspath
```

Nếu shell không hỗ trợ nối dòng bằng backslash, chạy một dòng:

```bash
./gradlew -PuseLocalLib=true dependencyInsight --dependency greeter-lib --configuration runtimeClasspath
```

PowerShell:

```powershell
.\gradlew.bat -PuseLocalLib=true dependencyInsight --dependency greeter-lib --configuration runtimeClasspath
```

Kết quả thường có dấu hiệu module `dev.learning:greeter-lib:1.0.0` được chọn qua **project trong included build**, ví dụ một dòng liên quan đến `project :greeter-lib` hoặc lý do dependency substitution. Dòng chữ cụ thể thay đổi theo Gradle release và format báo cáo.

Đừng coi `dependencyInsight` là bằng chứng duy nhất: kết hợp với sự thay đổi stdout, việc chưa republish và kiểm tra artifact đã publish còn nguyên sẽ chứng minh rõ hơn nguồn code được sử dụng.

### 6.3. Tắt composite và chạy lại

Từ `demo-app`:

```bash
./gradlew --quiet run
```

Expected stdout:

```text
Published artifact: Gradle
```

Không cần sửa lại source local. Khi property không có, settings không include build thư viện; Gradle tiêu thụ artifact đã publish ở repository, trong đó logic cũ vẫn còn.

**Kết luận thực nghiệm:**

| Chế độ | Source hiện tại trong `greeter-lib` | Published JAR | Stdout |
| --- | --- | --- | --- |
| Trước khi sửa, không composite | `Published artifact:` | `Published artifact:` | `Published artifact: Gradle` |
| Sau khi sửa, có composite | `Local source:` | `Published artifact:` | `Local source: Gradle` |
| Sau khi sửa, tắt composite | `Local source:` | `Published artifact:` | `Published artifact: Gradle` |

Không cần xóa Gradle cache thủ công để đổi giữa hai chế độ. Task inputs và dependency graph sẽ phản ánh lựa chọn module/project; nếu có custom tasks thiếu input tracking, đó là lỗi cấu hình riêng cần điều tra.

## 7. Khi tự động substitution không khớp: explicit mapping

Giả sử một thư viện publish artifact với tên Maven là `greeter-api` nhưng tên project source là `greeter-lib`.

Consumer request:

```kotlin
dependencies {
    implementation("dev.learning:greeter-api:1.0.0")
}
```

Included build có:

```text
project.group = dev.learning
project.name  = greeter-lib
```

Automatic substitution dựa trên `group:name` của project sẽ không tìm thấy **`dev.learning:greeter-api`**. Trong trường hợp này, tại **settings của consumer**:

```kotlin
rootProject.name = "demo-app"

includeBuild("../greeter-lib") {
    dependencySubstitution {
        substitute(module("dev.learning:greeter-api"))
            .using(project(":"))
    }
}
```

Đây là **phương án thay thế** cho cấu hình settings ở mục 4.5, không phải hai settings cần dán cạnh nhau. Nó yêu cầu mọi request phù hợp với module `dev.learning:greeter-api` được thay bằng root project của included build.

Nếu included build là multi-project, có thể map tới một subproject:

```kotlin
includeBuild("../library-repo") {
    dependencySubstitution {
        substitute(module("dev.learning:greeter-api"))
            .using(project(":api"))
    }
}
```

Đường dẫn `:api` ở đây thuộc **included build `library-repo`**, không phải consumer. Mảnh minh họa yêu cầu subproject `:api` thực sự tồn tại.

### 7.1. Vì sao artifactId có thể khác project.name?

Một build có thể publish:

```kotlin
publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
            artifactId = "greeter-api"
        }
    }
}
```

trong khi `project.name` vẫn là `greeter-lib`. Gradle automatic substitution dựa trên identity của **project**, không nhất thiết đọc toàn bộ publication customization để suy ra tọa độ phát hành.

Vì vậy một dự án publish nhiều artifacts hoặc cấu hình artifactId tùy biến cần explicit mapping đúng. Không cố “điều chỉnh” consumer dependency version để chữa lỗi group/name mismatch.

### 7.2. Quy tắc explicit không tự kiểm chứng tính tương đương

Bạn có thể map `dev.learning:greeter-api` sang bất kỳ project nào bằng cấu hình, nhưng chỉ nên làm vậy nếu project đó thực sự cung cấp API/ABI và runtime behavior tương đương artifact consumer mong đợi.

Nếu mapping sang project khác chứa lớp không đúng, Gradle có thể resolve thành công nhưng Java compilation vẫn báo thiếu class/method hoặc runtime gây lỗi. **Một rule substitution hợp lệ về cú pháp không chứng minh source đang được dùng là đúng thư viện.**

## 8. Phân biệt source local substitution với project dependency

Có hai cách consumer dùng source từ một Gradle project:

**Cách A — multi-project dependency:**

```kotlin
dependencies {
    implementation(project(":greeter-lib"))
}
```

Cách này phù hợp khi `greeter-lib` là **subproject của cùng build** và được đăng ký trong settings bằng `include(":greeter-lib")`.

**Cách B — composite build substitution:**

```kotlin
dependencies {
    implementation("dev.learning:greeter-lib:1.0.0")
}
```

với:

```kotlin
includeBuild("../greeter-lib")
```

ở settings build chính. Consumer giữ **module dependency** nhưng Gradle sử dụng local project nhờ substitution.

Cả hai có thể build source local, nhưng tổ chức/khả năng publish và độc lập của builds khác nhau:

| Tiêu chí | Multi-project | Composite |
| --- | --- | --- |
| Cấu hình settings | Một build chung | Mỗi build độc lập, có includeBuild |
| Dạng dependency khai báo | `project(":lib")` | `"group:artifact:version"` |
| Tính độc lập của source repository | Ít hoặc phụ thuộc layout monorepo | Có thể giữ repositories/checkouts riêng |
| Dùng published artifact khi tắt chế độ | Phải đổi dependency declaration/logic | Có thể tắt includeBuild mà giữ dependency |
| Tái sử dụng build logic | Chung các convention/central settings tùy thiết kế | Included build tự có build logic của nó |
| Mục tiêu chính | Cấu trúc một build gồm nhiều modules | Tích hợp/override module giữa các builds |

Composite không phải “cách tốt hơn trong mọi trường hợp”. Nếu mọi module đã thuộc cùng một repository, có cùng release lifecycle và settings, multi-project có thể đơn giản hơn. Khi hai dự án có release cycles độc lập, composite là công cụ rất hữu ích để phát triển cùng lúc.

## 9. Included build vẫn có settings, repositories và build logic riêng

Một trong những điểm khác nhau lớn là **isolation** giữa builds.

Ví dụ consumer dùng `repositories { mavenCentral() }` không tự khiến included build có thể giải quyết mọi plugin/dependency của nó. Included build vẫn có `settings.gradle.kts`/`build.gradle.kts` của mình và repositories do chính nó cấu hình.

Trong bài lab, included build không có third-party dependencies nên không cần Maven Central. Nhưng dự án thật có thể có:

- Build plugin repositories riêng (`pluginManagement`).
- Dependency repositories riêng, ví dụ Maven Central hoặc repository nội bộ.
- Version catalogs và dependency locking riêng.
- Toolchains/JDK requirements riêng.
- CI/testing conventions riêng.
- Java/Android/Kotlin plugin versions riêng.
- Những Gradle tasks và artifact publishing rules riêng.

**Không coi `includeBuild` là thao tác merge toàn bộ Gradle scripts thành một project duy nhất.**

### 9.1. Những thay đổi Gradle version, plugin version và JDK vẫn phải tương thích

Một composite build chạy trong cùng Gradle invocation, nên thực tế cần bảo đảm plugin APIs, Gradle wrapper được chọn và JDK/toolchain requirements của cả builds có thể hoạt động cùng nhau.

Nếu consumer Wrapper dùng Gradle không tương thích plugin của included build, việc source có ở local cũng không giải quyết lỗi. Cần kiểm tra:

```bash
./gradlew --version
./gradlew javaToolchains
./gradlew -PuseLocalLib=true help --stacktrace
```

Chạy các lệnh trong `demo-app` để xem invocation consumer. Nếu thư viện có Wrapper khác, Gradle composite **không tự chạy một Gradle daemon/Wrapper riêng cho từng included build** theo cách hai lệnh hoàn toàn tách biệt. Hãy thử cả builds độc lập và trong composite.

### 9.2. Plugin resolution không giống library substitution

`includeBuild("../greeter-lib")` trong settings để dùng **library source** khác với cách include một **plugin-producing build** qua:

```kotlin
pluginManagement {
    includeBuild("../build-logic")
}
```

Cơ chế trong `pluginManagement` phục vụ plugin resolution ở settings/plugins DSL. Nó không đồng nghĩa với việc tự thay mọi Maven dependency của ứng dụng bằng build logic plugin.

Nếu bạn đang debug lỗi `Plugin ... was not found`, cần kiểm tra plugin ID, pluginManagement và build-logic, không mặc định thêm `includeBuild` vào cuối settings sẽ sửa mọi loại plugin lỗi.

## 10. Task graph và build outputs trong composite

Khi bật substitution, Gradle có thể nhận ra consumer compile cần outputs của included library. Nó kết nối dependencies tới các tasks tạo artifact/classes phù hợp theo variant model. Ví dụ trong bài lab:

```text
:demo-app:run
    |
    v
:demo-app:classes
    |
    v
:demo-app:compileJava
    |
    v
included greeter-lib project outputs
    |
    v
:greeter-lib:compileJava / :greeter-lib:jar (tùy variant)
```

Sơ đồ minh họa quan hệ, không phải output chính xác của mọi Gradle version/variant; Gradle có thể chọn classes hoặc JAR artifacts khác nhau tùy nhu cầu/attributes.

Xem task graph mà chưa thực thi:

```bash
./gradlew -PuseLocalLib=true run --dry-run --console=plain
```

Lệnh `--dry-run` hữu ích để thấy những task của included build có thể được thêm. Nó không compile/execute thật và **không chứng minh ứng dụng chạy được**. Sau đó phải chạy `run` như mục 6.1.

### 10.1. Chạy task của included build trực tiếp

Với included build root name `greeter-lib`, bạn có thể gọi task của nó từ composite root bằng task path phù hợp:

```bash
./gradlew -PuseLocalLib=true :greeter-lib:tasks --all
```

Hoặc chạy trực tiếp trong `greeter-lib` bằng Wrapper của chính thư viện:

```bash
./gradlew tasks --all
./gradlew build
```

Khi dùng path ở composite build, nên kiểm tra tên included build trong logs và đặt root project names đủ khác nhau để tránh trùng identity.

### 10.2. Build output không bị copy vào Maven repository

Sau khi đổi source và chạy chế độ composite, output build của included project xuất hiện trong `greeter-lib/build/` (hoặc vị trí đã tùy chỉnh). **`published-repo` vẫn giữ artifact đã publish trước đó**.

Composite là cơ chế dependency resolution và task execution, không phải pipeline để publish/rewrite artifacts trên repository. Việc không thay repository là điều cần kiểm chứng trong ví dụ, tránh hiểu nhầm “Gradle đã cập nhật artifact cũ”.

## 11. Những giới hạn của source substitution so với artifact thật

Đây là phần dễ dẫn tới false confidence nhất khi phát triển thư viện.

### 11.1. Published metadata có thể khác project outgoing variants

Khi Gradle publish một module, publication có thể:

- Đổi `artifactId`, group hoặc version.
- Ánh xạ API/runtime dependencies sang Maven POM.
- Thêm hoặc bỏ variants/capabilities.
- Tạo source/Javadoc JARs.
- Thêm classifiers, artifacts đặc biệt.
- Tùy chỉnh Gradle Module Metadata, constraints hoặc version mapping.
- Áp dụng relocation/signing/provenance policy.

Composite build chủ yếu sử dụng **outgoing project variants** của included build cho substitution. Nó không nhất thiết mô phỏng mọi chi tiết của **POM/`.module` đã upload**. Nếu producer publish custom artifacts/variants, local composite có thể **không phản ánh chính xác hành vi consumer dùng release thật**.

Vì vậy cần kiểm thử **hai mode**:

1. Composite source mode cho vòng sửa/debug nhanh.
2. Published artifact mode từ repository staging/official để xác nhận metadata và packaging.

### 11.2. Version alignment có thể bị che khuất

Một thư viện local có thể là snapshot chuẩn bị version mới, còn app vẫn yêu cầu `1.0.0`. Substitution có thể khiến app dùng code mới mà không đổi dependency declaration.

Ưu điểm: thử thay đổi trước khi release.

Rủi ro: kết quả local pass không chứng minh artifact `1.0.0` đã publish hoạt động như vậy. Khi tắt composite, lỗi cũ có thể xuất hiện.

Hãy ghi rõ trong PR/CI rằng source-mode tests chỉ là một phần kiểm thử. Khi sửa breaking API, cần thay version/contract đúng và thử consumer bằng artifact mới đã publish.

### 11.3. Không thay thế hoàn toàn kiểm tra artifact integrity

Source mode có thể chạy mà không yêu cầu chữ ký/metadata/repository. Artifact mode mới giúp kiểm tra:

- JAR được đóng gói có những class/resources nào.
- Maven POM và Gradle Module Metadata đúng không.
- Repository có upload tất cả file không.
- Checksum/signatures hoặc dependency verification theo policy.
- Consumer dùng đúng Java variant/runtime classpath.
- Artifact có reproducible hoặc immutable không.

Composite hữu ích để phát triển nhưng không phải một phép kiểm chứng release supply chain đầy đủ.

## 12. Dependency substitution và version conflicts

Hãy phân biệt các khái niệm:

- **Dependency substitution**: thay một dependency request bằng một project/module khác trước hoặc trong resolution theo rules.
- **Dependency conflict resolution**: quyết định version được chọn khi graph chứa nhiều requests/constraints.
- **Dependency locking**: ghi lại versions đã resolved để hạn chế thay đổi ngoài ý muốn.
- **Dependency constraints/platform/BOM**: đưa yêu cầu version/compatibility vào graph.

Một composite substitution có thể thay một module request phù hợp thành project dependency, nhưng điều đó không đồng nghĩa lockfile tự chứng nhận local project tương đương đúng phiên bản đã khóa.

### 12.1. Khi consumer lock version 1.0.0

Nếu lockfile consumer ghi module `dev.learning:greeter-lib:1.0.0`, bật composite có thể làm dependency target trở thành project. Hành vi resolution/locking tùy configuration và Gradle version; không nên kỳ vọng lockfile sẽ tự theo dõi mọi commit của local source.

Để biết đã chọn cái gì, chạy `dependencies`/`dependencyInsight` trong chế độ tương ứng. Để tái lập chính xác source mode, cần **commit hash của included build**, không chỉ module version string.

### 12.2. Chế độ published vẫn phải cố định version hợp lý

Không thay dependency thành một dynamic version như `dev.learning:greeter-lib:+` chỉ để thử local source. Điều này có thể khiến chế độ published nhận một release khác với bản dự kiến.

Trong dự án thật nên có phiên bản được quản lý rõ và không phát hành lại nhiều bytes dưới cùng một release coordinates. Composite giúp thử code chưa publish, không phải lý do bỏ quản lý version của thư viện.

## 13. Debug khi substitution không xảy ra

Một số lỗi thường gặp và quy trình xử lý:

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| App vẫn in `Published artifact: Gradle` khi bật `useLocalLib` | Settings không include build hoặc local source chưa được sửa | Kiểm tra `-PuseLocalLib=true`, settings, đúng file source |
| Gradle báo included build path không tồn tại | Sai đường dẫn `../greeter-lib` | Đặt sibling directory như layout bài lab |
| `Could not find dev.learning:greeter-lib:1.0.0` dù có includeBuild | Group/project name khác tọa độ hoặc settings condition không bật | Kiểm tra identity, dùng explicit mapping nếu cần |
| `No matching variant` | Attributes Java usage/category/JVM không phù hợp | Xem producer `outgoingVariants` và consumer requirements |
| Không tìm class `dev.learning.Greeter` | Source path/package/class không khớp hoặc variant thiếu JAR | Kiểm tra source, compiler task và output |
| Gradle chạy producer project nhưng app vẫn dùng bản cũ | Cấu hình khác được resolve hoặc test đang chạy chế độ published | Kiểm tra graph thật, log `--info` |
| App chỉ lỗi khi tắt composite | Published artifact/metadata chưa được cập nhật hoặc bản cũ có bug | Publish version mới trong staging và test artifact |
| App chỉ lỗi khi bật composite | Local source chưa compile hoặc đang thay API không tương thích | Chạy producer tests và composite consumer tests |
| ArtifactId đã publish khác project name | Automatic mapping không match | Dùng `dependencySubstitution` explicit |
| Có hai included builds cung cấp cùng module | Identity/rules trùng hoặc ambiguous | Làm rõ owner, sửa mapping/checkout |
| Compiler JDK không tương thích | Included build có toolchain/plugin requirements khác | Kiểm tra `--version` và `javaToolchains` |
| Gradle plugin không tương thích | Hai builds dùng plugin APIs không hợp Gradle invocation | Đối chiếu plugin/Gradle versions |
| Gradle có offline cache nhưng không resolve published mode | Artifact chưa publish vào local file repo hoặc tọa độ sai | Kiểm tra repository và metadata |
| Maven local chứa JAR cũ, hành vi khó dự đoán | Dependency được lấy từ `mavenLocal` trước remote repo | Tránh dùng Maven local bừa, ưu tiên repository lab biệt lập |
| Task `run` thiếu khi chạy từ root library | Library là `java-library`, không áp dụng Application plugin | Chạy `run` ở `demo-app` |
| Task `publish` thiếu trong app | App không áp dụng `maven-publish` | Chạy publishing task ở thư viện |
| `project(":lib")` không tồn tại ở app | Nhầm composite với multi-project | Dùng module notation và `includeBuild` |

### 13.1. Checklist debug từng bước

1. Trong `demo-app`, xem `./gradlew --version` và xác nhận Gradle invocation hợp lệ.
2. Xem `demo-app/settings.gradle.kts` có điều kiện bật `includeBuild` không.
3. Xem build thư viện có `group=dev.learning` và root name `greeter-lib` hay không.
4. Xác nhận app vẫn khai báo `implementation("dev.learning:greeter-lib:1.0.0")`.
5. Chạy `./gradlew -PuseLocalLib=true dependencies --configuration runtimeClasspath`.
6. Chạy `dependencyInsight` cho `greeter-lib`.
7. Nếu không match do tọa độ, dùng explicit substitution rule đúng project path.
8. Nếu variant mismatch, xem producer `outgoingVariants` và Java toolchain/attributes.
9. Chạy app ở cả source mode và published mode, so sánh stdout.
10. Nếu lỗi chỉ xuất hiện ở CI/release, publish artifact staging rồi test consumer từ repository thật.

## 14. Các lệnh kiểm tra hữu ích

Đứng trong `demo-app`:

```bash
# Gradle và JVM invocation:
./gradlew --version

# Không bật composite:
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency greeter-lib --configuration runtimeClasspath

# Bật composite:
./gradlew -PuseLocalLib=true dependencies --configuration runtimeClasspath
./gradlew -PuseLocalLib=true dependencyInsight --dependency greeter-lib --configuration runtimeClasspath

# Xem task graph mà không thực thi:
./gradlew -PuseLocalLib=true run --dry-run --console=plain

# Thực thi và xem thông tin chi tiết:
./gradlew -PuseLocalLib=true run --info --console=plain
```

Trong `greeter-lib`:

```bash
# Library outgoing variants:
./gradlew outgoingVariants --console=plain

# Build độc lập của library:
./gradlew build --console=plain

# Metadata khi publish:
./gradlew generateMetadataFileForMavenJavaPublication
./gradlew generatePomFileForMavenJavaPublication

# Publication task của lab:
./gradlew publishMavenJavaPublicationToLabRepository
```

Lệnh `outgoingVariants` cho thấy outgoing configurations/attributes của producer project. `dependencies` và `dependencyInsight` cho thấy cách consumer đã resolve một configuration cụ thể. Hai phía giúp chẩn đoán rõ hơn thay vì chỉ nhìn log lỗi cuối.

### 14.1. Không dùng `--refresh-dependencies` như phép sửa mọi lỗi

`--refresh-dependencies` giúp Gradle kiểm tra lại dependency metadata/cache theo cơ chế của nó. Nó không sửa:

- Group/project name sai.
- `includeBuild` đặt sai thư mục.
- Project không có outgoing variant phù hợp.
- Plugin API/JDK incompatibility.
- Public Java API breaking change.
- Artifact metadata published sai.

Nếu app đang ở source mode, xóa toàn bộ `~/.gradle/caches` thường không phải bước đầu tiên cần làm. Đọc dependency graph và task graph trước.

## 15. Thiết kế workflow developer để không nhầm chế độ

Một workflow khuyến nghị:

**Chế độ bình thường — published artifact**

```bash
./gradlew check
./gradlew run
```

**Chế độ phát triển tích hợp — local source**

```bash
./gradlew -PuseLocalLib=true check
./gradlew -PuseLocalLib=true run
```

Trong ví dụ tối giản chưa có test source nên `check` có thể chỉ chạy những verification tasks sẵn có và `test` có thể `NO-SOURCE`. Với dự án thực, cần unit/integration tests đủ mạnh để quality gate có ý nghĩa.

### 15.1. Toggle bằng Gradle property có ưu/nhược điểm gì?

Ưu điểm:

- Không phải sửa file `dependencies` khi chuyển chế độ.
- Thay đổi cục bộ qua command-line hoặc developer Gradle properties.
- Dependency declaration luôn phản ánh tọa độ đã công bố mà ứng dụng định dùng.
- Dễ viết hai CI jobs so sánh.

Cần thận trọng:

- CI không nên vô tình bật source mode khi nó định kiểm thử release artifact.
- Property có thể được đặt trong user `gradle.properties` và khiến developer quên rằng local substitution đang bật.
- Phải chỉ rõ điều kiện/đường dẫn của included build; checkout thiếu source sẽ fail khi bật.
- **Không thay published artifact tests bằng source tests duy nhất.**
- Khi dùng cấu hình cache, xác minh thay đổi mode làm Gradle cấu hình lại/resolution đúng theo property; tránh đọc environment ngoài Provider API một cách mơ hồ.

Trong một đội phát triển, có thể đặt script alias rõ tên `runWithLocalLib` để tránh nhập nhầm property. Nhưng script không nên cố tình che mode đang chạy trong logs/CI.

### 15.2. Không bật composite bằng cách đổi version động

Một anti-pattern là thay `implementation("dev.learning:greeter-lib:1.0.0")` thành `implementation("dev.learning:greeter-lib:+")` khi local source thay đổi. Điều đó không cần thiết cho composite, và ở published mode có thể kéo artifact ngoài dự kiến.

Giữ module coordinates rõ ràng; dùng substitution để quyết định source hay repo. Nếu local API đã thực sự breaking, cần cập nhật version và thử một published candidate tương ứng trong release workflow.

## 16. CI và release: giữ hai vòng kiểm thử riêng

Composite rất phù hợp cho PR phát triển đồng thời app + library nhưng không phải bằng chứng đầy đủ rằng artifact có thể được tiêu thụ từ Maven repository.

Một CI workflow có thể có hai nhánh:

```text
Branch: development
    |
    +-- Java library unit tests
    |
    +-- Composite consumer tests
    |      includeBuild("../greeter-lib")
    |      dependency substitution
    |      source changes → consumer code
    |
    v
Tìm lỗi API/logic trước publish


Branch: release / artifact validation
    |
    +-- Build + quality checks library
    |
    +-- Publish vào staging Maven repository
    |      POM + .module + JAR
    |
    +-- Consumer tests từ tọa độ Maven của staging
    |      KHÔNG include local source build
    |
    +-- Verify JVM baseline/metadata/checksum
    |
    v
Cho phép promote release
```

**Composite source mode:** kiểm tra việc source của hai builds có làm việc cùng nhau không.

**Published artifact mode:** kiểm tra artifact, POM/GMM, runtime dependencies, repository, versions và cách consumer bên ngoài thực sự resolve.

Nếu một publication có custom artifactId, feature variants hoặc POM mapping đặc biệt, **published consumer test càng quan trọng** vì composite có thể không mô phỏng tất cả metadata đã upload.

### 16.1. Không tự ghi đè Maven releases

Trường hợp một thư viện cần sửa, không nên publish lại bytes khác dưới cùng một release coordinate `1.0.0` trong repository production. Proxy/cache/lockfiles có thể giữ kết quả khác nhau; người dùng có thể lấy version cùng số nhưng nội dung khác.

Với thử nghiệm local, source substitution không thay remote artifacts. Với phát hành mới, quản lý version mới theo policy. Một Maven file repo trong lab dùng để minh họa khác production artifact repository có yêu cầu bất biến.

### 16.2. Tránh source substitution vượt scope

Trong hệ thống lớn, cùng một module có thể được nhiều modules sử dụng. `includeBuild` có thể khiến các dependency requests phù hợp được thay trên nhiều configurations. Điều này hữu ích khi debug nhưng cũng có thể làm thay đổi nhiều classpaths hơn người dùng dự kiến.

Hãy đọc `dependencyInsight`/`dependencies` trên những configurations có ý nghĩa (`compileClasspath`, `runtimeClasspath`, test classpaths, custom configurations). Không giả định chỉ duy nhất một dòng `implementation` bị tác động.

## 17. Một số trường hợp cần cấu hình riêng

### 17.1. Included build có nhiều subprojects

Giả sử:

```text
library-repo/
├── settings.gradle.kts
├── api/
│   └── build.gradle.kts
└── runtime/
    └── build.gradle.kts
```

Các projects trong included build có thể được tự động thay nếu group và project name tương ứng. Khi artifact names tùy biến, mapping explicit:

```kotlin
includeBuild("../library-repo") {
    dependencySubstitution {
        substitute(module("dev.learning:api-client"))
            .using(project(":api"))

        substitute(module("dev.learning:runtime-client"))
            .using(project(":runtime"))
    }
}
```

Không dùng `project(":api")` nếu included build không có subproject `api`. Đường dẫn là project path của **included build**.

### 17.2. Thư viện local có additional feature variants

Nếu producer xuất bản một feature variant phụ thuộc custom capability/attributes, bạn phải kiểm tra liệu variant đó có sẵn và được chọn đúng khi composite. Với library dùng classifier artifact đặc biệt hoặc publication không chuẩn, automatic substitution có thể không tương đương với metadata đã publish.

Đừng kết luận “composite build báo success nghĩa là mọi consumer ngoài repository đều success”. Hãy test published mode với đúng artifact và metadata.

### 17.3. Hai included builds có identity gây trùng

Nếu hai builds có root name giống nhau, hoặc cả hai quảng bá module identity `dev.learning:greeter-lib`, Gradle có thể báo xung đột tên build hoặc resolution không rõ ràng tùy cấu trúc.

Thiết kế:

- Root build names độc nhất trong composite.
- Mỗi module identity có một owner/source rõ.
- Explicit mapping khi coordinates không suy ra được.
- Không include nhiều checkouts của cùng module một cách tùy tiện.

### 17.4. Thư viện local cần một JDK khác

Ví dụ app dùng Java 17 nhưng included build có toolchain 21. Nếu app phải chạy Java 17, việc dùng library bytecode Java 21 có thể gây variant mismatch hoặc runtime failure. Composite không tự hạ bytecode/API của thư viện.

Kiểm tra toolchains và Java target attributes ở **cả** producer và consumer; một project local đang ở nhánh phát triển Java 21 không nhất thiết tương đương release Java 17.

### 17.5. IDE import nhiều builds

Một IDE có Gradle integration thường có thể nhận composite project models và source attachments, giúp breakpoint trong source thư viện local. Tuy nhiên behavior phụ thuộc IDE/Gradle plugin version. Nếu CLI source mode chạy đúng nhưng IDE vẫn mở binary library từ cache, cần refresh/sync đúng Gradle model, kiểm tra Gradle arguments/properties IDE sử dụng và không giả định IDE đang bật cùng `useLocalLib` như terminal.

## 18. Các lỗi thực tế khi dùng local source thay artifact

| Vấn đề | Điều cần phân biệt | Hướng xử lý |
| --- | --- | --- |
| Chạy source mode vẫn dùng artifact | IncludeBuild không được kích hoạt hoặc mapping không match | Kiểm tra settings/property/group:name, dependencyInsight |
| Không tìm thấy artifact khi tắt source mode | Chưa publish hoặc repo URL sai | Publish thư viện vào file repo, xác minh POM/JAR |
| App compile được nhưng runtime lỗi | Local API/implementation/dependencies không tương thích | Kiểm tra runtimeClasspath, producer Java tests |
| Chỉ source mode pass, published mode fail | Artifact chưa có fix hoặc publication sai | Publish version mới vào staging và test consumer |
| Included build compile fail | Source đang ở trạng thái chưa hợp lệ | Chạy library build/test độc lập |
| `No matching variant` | JVM baseline hoặc attributes không tương thích | So sánh outgoingVariants và consumer attributes |
| Automatic substitution không match artifactId custom | Project name khác Maven artifactId | Explicit `dependencySubstitution` |
| Dynamic version bị thay source khác release | Substitution theo module identity không chứng minh version equivalence | Pin version, kiểm tra commit/source/API |
| Repo local chứa nhiều phiên bản thử | Cache/repo có artifacts cũ | Dùng isolated repo, immutable test versions |
| CI không có thư mục sibling | IncludeBuild chỉ hoạt động khi property bật nhưng checkout thiếu | Checkout cả builds hoặc tắt mode đúng mục đích |
| IDE vẫn debug JAR | IDE Gradle model/property khác terminal | Refresh Gradle project và cấu hình property IDE |
| App task graph không chạy producer task | Dependency không được chọn qua included build hoặc task UP-TO-DATE | Kiểm tra graph và runtimeClasspath |
| Maven POM khác composite project variants | Publication customization không được mô phỏng | Consumer test trên repository staging |
| Source mode dùng Java cao hơn production | Included build toolchain/target mới | Cấu hình Java baseline, runtime tests |
| Lỗi plugin trong included build | Separate settings/plugins và Gradle invocation không tương thích | Đọc lỗi plugin trong included build và Gradle version |
| Thay group/name để “fix” làm vỡ publication | Project identity đã ảnh hưởng module coordinates | Dùng explicit rule nếu public coordinates khác |
| Gradle dùng cache và không thấy sửa code | Task inputs/custom outputs sai hoặc chạy nhầm build | Xác nhận source path, run --info, clean đúng build khi cần |
| Chạy `publish` tưởng composite tự cập nhật | Publishing và substitution là hai việc riêng | Bỏ publish khỏi vòng thử local, xem module/project resolution |
| Consumer test chỉ chạy trong repo library | Không test đúng published dependency graph | Test app ở cả hai chế độ |

## 19. Checklist áp dụng vào dự án thật

Trước khi chọn composite build cho một thư viện local, hãy trả lời:

1. App đang tiêu thụ module coordinates nào?
2. Included project có `group` và `name` gì?
3. Automatic substitution có khớp hay phải explicit mapping?
4. Source checkout tồn tại ở path nào trên mọi máy developer/CI?
5. Gradle Wrapper, plugins và JDK requirements có tương thích?
6. Thư viện có build/test độc lập thành công không?
7. Consumer có giữ nguyên module dependency notation không?
8. Trong source mode, `dependencyInsight` cho thấy project substitution đúng chưa?
9. Output khi local source thay đổi có được dùng thực sự không?
10. Có nguy cơ bỏ qua custom published variants/metadata không?
11. Consumer Java version có phù hợp producer outgoing variant không?
12. Có cách tắt composite nhanh để trở lại published artifact không?
13. CI có tách source integration tests với published artifact tests không?
14. Publish version có được kiểm soát và bất biến sau release không?
15. Có cần đánh dấu rõ source commit hash để tái lập lỗi ở local mode không?

Không nên bật composite mặc định trên môi trường release nếu điều kiện phát hành yêu cầu kiểm chứng artifact đã được publish. Source mode phục vụ **vòng phát triển**; published mode phục vụ **hợp đồng release và khả năng tái lập**.

## 20. Bài tập thực hành

**Bài tập A — làm lab hai builds.** Tạo `greeter-lib` và `demo-app` theo mục 4. Publish bản đầu, chạy app không bật composite và ghi stdout `Published artifact: Gradle`.

**Bài tập B — thay source không publish.** Đổi thư viện sang `Local source: `, không publish lại. Chạy app với `-PuseLocalLib=true`; xác minh stdout `Local source: Gradle`.

**Bài tập C — tắt composite.** Không sửa code thư viện, chạy app không có property; giải thích vì sao stdout trở lại `Published artifact: Gradle`.

**Bài tập D — quan sát dependency graph.** So sánh `dependencyInsight`/`dependencies --configuration runtimeClasspath` ở hai chế độ. Tìm dấu hiệu external module so với project substitution.

**Bài tập E — đổi project name.** Trong bản sao `greeter-lib`, thử đổi root project name thành `local-greeter` mà giữ Maven coordinates ở app. Vì sao automatic mapping `group:name` không còn match? Thử explicit substitution đúng project.

**Bài tập F — custom artifactId.** Giả sử publication của library có `artifactId="greeter-api"` nhưng project name vẫn `greeter-lib`. Viết explicit rule để consumer request `dev.learning:greeter-api` được thay bằng included root project.

**Bài tập G — tách hai builds.** Giải thích vì sao `include(":greeter-lib")` trong app settings không tương đương `includeBuild("../greeter-lib")` khi thư viện có settings riêng.

**Bài tập H — lỗi Java compatibility.** Sửa included library để yêu cầu API/bytecode Java 21 nhưng consumer nhắm Java 17. Dự đoán variant matching/runtime outcome, rồi nêu biện pháp đúng để giữ baseline.

**Bài tập I — published metadata.** Thêm source/Javadoc variants hoặc custom artifact metadata vào producer. So sánh kết quả source mode với consumer đọc POM/.module thật sau publish. Điều gì composite không đảm bảo mô phỏng?

**Bài tập J — CI mode.** Thiết kế hai jobs: một job dùng includeBuild để test thay đổi đồng thời, một job publish version candidate vào staging Maven repository rồi test app không include source. Lý do cần cả hai?

**Bài tập K — source commit hash.** Nếu một test local pass với `greeter-lib` ở commit chưa phát hành, cần ghi những thông tin nào (commit, Gradle, JDK, dependency graph) để tái lập build?

**Bài tập L — tránh Maven local.** Thử mô tả vì sao `mavenLocal()` có thể làm developer nhận JAR cũ. Composite và file repo biệt lập trong lab xử lý vấn đề đó như thế nào?

### Câu hỏi tự kiểm tra

1. Composite build khác multi-project build ở đâu?
2. `includeBuild("../greeter-lib")` được khai báo trong file nào?
3. Vì sao `implementation("dev.learning:greeter-lib:1.0.0")` có thể giữ nguyên khi dùng source local?
4. Automatic substitution dùng những phần nào của module/project identity?
5. Vì sao version request không bảo đảm local source trùng release?
6. Khi nào cần `dependencySubstitution` explicit?
7. `project(":")` trong rule của included build chỉ project nào?
8. Included build có tự dùng settings/repositories của consumer không?
9. Vì sao cần publish artifact một lần trước khi chạy mode đối chứng trong lab?
10. Source mode có tự ghi lại bytes mới vào `published-repo` không?
11. Lệnh nào kiểm tra một module dependency đã được substitute?
12. `--dry-run` chứng minh task đã compile/run thật không?
13. `outgoingVariants` có ích cho producer ở điểm nào?
14. Vì sao test qua `project(...)` không thay thế hoàn toàn test artifact qua repository?
15. Gradle Module Metadata/POM có thể khác local outgoing project model như thế nào?
16. Java 17 app có thể dùng một local library chỉ phát hành Java 21 bytecode không?
17. Khi composite bật, Gradle có thể lên lịch task của included build ra sao?
18. Git submodule có tự tạo Gradle dependency substitution không?
19. Khi published mode lỗi mà source mode pass, nên kiểm tra những phần nào?
20. Vì sao CI nên có cả source integration và published artifact validation?
21. Có nên xuất bản lại cùng coordinates với bytes khác lên repository production không?
22. Composite có thay thế Maven repositories với những dependencies không được substitute không?
23. Nếu project name khác Maven artifactId, nên đổi public coordinates hay dùng mapping có chủ đích?
24. Khi IDE không thấy source local, cần đối chiếu property/configuration nào?
25. Vì sao một pull request local pass chưa chứng minh release artifact đã sẵn sàng?

**Tài liệu chính thức:**
- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html)
- [Gradle — Dependency Substitution](https://docs.gradle.org/current/userguide/resolution_rules.html)
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html)
- [Gradle — Variant-Aware Resolution](https://docs.gradle.org/current/userguide/variant_aware_resolution.html)
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)

**Ghi nhớ:** Để dùng **local source thay artifact đã công bố**, composite build dùng `includeBuild` và dependency substitution để ánh xạ module `group:artifact` tới project của included build. Consumer có thể giữ nguyên dependency notation; Gradle thực thi các tasks cần thiết của thư viện local mà **không publish lại mỗi lần sửa**. Nhưng source mode không bảo đảm tương đương hoàn toàn với bản release đã publish; phải thử lại **POM/GMM/JAR thực** và consumer mode từ repository trước khi phát hành.